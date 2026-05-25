from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .io import (
    infer_holding_position,
    output_trial_id,
    read_accelerometer_csv,
    read_gravity_csv,
    read_gyroscope_csv,
    read_magnetometer_csv,
    read_metadata_or_default,
    resolve_trial_dir,
)
from .plotting import plot_trajectory


def run_smartpdr_trial(
    trial_id: str,
    config: dict[str, Any],
    holding_position: str | None = None,
) -> dict[str, Path]:
    raw_dir = resolve_trial_dir(config["paths"]["raw_data_dir"], trial_id, holding_position)
    metadata = read_metadata_or_default(raw_dir / "metadata.json", trial_id)
    inferred_position = infer_holding_position(raw_dir)
    if inferred_position and metadata.get("holding_position") in {None, "", "unknown"}:
        metadata["holding_position"] = inferred_position
    output_id = output_trial_id(config["paths"]["raw_data_dir"], raw_dir, metadata)

    acc_df = read_accelerometer_csv(raw_dir / "Accelerometer.csv")
    gyro_df = read_gyroscope_csv(raw_dir / "Gyroscope.csv")
    mag_df = read_magnetometer_csv(raw_dir / "Magnetometer.csv")
    gravity_df = read_gravity_csv(raw_dir / "Gravity.csv")

    smart_cfg = config["smartpdr"]
    sensor_df = build_smartpdr_signals(acc_df, gyro_df, mag_df, gravity_df, smart_cfg)
    steps_df = detect_smartpdr_steps(sensor_df, smart_cfg)
    heading_df = estimate_smartpdr_heading(sensor_df, smart_cfg)
    trajectory_df = build_smartpdr_trajectory(steps_df, heading_df, smart_cfg)

    trial_output_dir = Path(smart_cfg["output_dir"]) / output_id
    processed_dir = trial_output_dir / "processed"
    figures_dir = trial_output_dir / "figures"
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "signals": processed_dir / "signals.csv",
        "steps": processed_dir / "steps.csv",
        "heading": processed_dir / "heading.csv",
        "trajectory": processed_dir / "trajectory.csv",
        "acc_step_figure": figures_dir / "acc_step.png",
        "heading_figure": figures_dir / "heading.png",
        "trajectory_figure": figures_dir / "trajectory.png",
    }

    sensor_df.to_csv(paths["signals"], index=False)
    steps_df.to_csv(paths["steps"], index=False)
    heading_df.to_csv(paths["heading"], index=False)
    trajectory_df.to_csv(paths["trajectory"], index=False)

    dpi = int(config["visualization"]["figure_dpi"])
    show_grid = bool(config["visualization"]["show_grid"])
    equal_axis = bool(config["visualization"]["equal_axis"])
    plot_smartpdr_acc(sensor_df, steps_df, paths["acc_step_figure"], dpi, show_grid)
    plot_smartpdr_heading(heading_df, paths["heading_figure"], dpi, show_grid)
    plot_trajectory(
        trajectory_df,
        paths["trajectory_figure"],
        title=f"SmartPDR {output_id}",
        dpi=dpi,
        equal_axis=equal_axis,
        show_grid=show_grid,
    )
    return paths


def build_smartpdr_signals(
    acc_df: pd.DataFrame,
    gyro_df: pd.DataFrame,
    mag_df: pd.DataFrame,
    gravity_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    t = acc_df["t"].to_numpy()
    df = acc_df.copy()
    for col in ["gyro_x", "gyro_y", "gyro_z"]:
        df[col] = np.interp(t, gyro_df["t"].to_numpy(), gyro_df[col].to_numpy())
    for col in ["mag_x", "mag_y", "mag_z"]:
        df[col] = np.interp(t, mag_df["t"].to_numpy(), mag_df[col].to_numpy())
    for col in ["gravity_x", "gravity_y", "gravity_z"]:
        df[col] = np.interp(t, gravity_df["t"].to_numpy(), gravity_df[col].to_numpy())

    gravity = df[["gravity_x", "gravity_y", "gravity_z"]].to_numpy(dtype=float)
    gravity_norm = np.linalg.norm(gravity, axis=1)
    gravity_unit = gravity / np.maximum(gravity_norm[:, None], 1e-9)

    acc = df[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float)
    gyro = df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=float)
    mag = df[["mag_x", "mag_y", "mag_z"]].to_numpy(dtype=float)

    # SmartPDR transforms LCS to GCS. With phyphox/iPhone CSV, Gravity.csv gives
    # the current vertical axis, so we use scalar projection as the reproducible
    # vertical component approximation.
    vertical_acc = np.sum(acc * gravity_unit, axis=1)
    gyro_vertical = np.sum(gyro * gravity_unit, axis=1)
    df["acc_vertical"] = vertical_acc
    df["gyro_vertical"] = gyro_vertical
    df["mag_heading_rad"] = tilt_compensated_mag_heading(mag, gravity)

    alpha = float(config["preprocessing"]["hpf_alpha"])
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("smartpdr.preprocessing.hpf_alpha must be between 0 and 1")
    gravity_component = np.empty_like(vertical_acc)
    gravity_component[0] = vertical_acc[0]
    for i in range(1, len(vertical_acc)):
        gravity_component[i] = alpha * gravity_component[i - 1] + (1.0 - alpha) * vertical_acc[i]
    df["acc_hpf"] = vertical_acc - gravity_component

    window = int(config["preprocessing"]["moving_average_window"])
    if window < 1:
        raise ValueError("smartpdr.preprocessing.moving_average_window must be >= 1")
    if window % 2 == 0:
        window += 1
    df["acc_step"] = (
        pd.Series(df["acc_hpf"]).rolling(window=window, center=True, min_periods=1).mean()
    )
    return df


def detect_smartpdr_steps(sensor_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    acc_step = sensor_df["acc_step"].to_numpy(dtype=float)
    t = sensor_df["t"].to_numpy(dtype=float)
    n = int(config["preprocessing"]["comparison_window_samples"])
    if n < 2:
        raise ValueError("smartpdr.preprocessing.comparison_window_samples must be >= 2")
    if n % 2 == 1:
        n += 1
    half = n // 2
    sample_interval = _median_sample_interval(t)
    distance_samples = max(
        1, int(round(float(config["step_detection"]["min_step_interval_s"]) / sample_interval))
    )
    candidates, _ = find_peaks(
        acc_step,
        height=float(config["step_detection"]["peak_threshold"]),
        distance=distance_samples,
    )

    rows: list[dict[str, float | int]] = []
    pp_threshold = float(config["step_detection"]["peak_to_peak_threshold"])
    for idx in candidates:
        if idx < half or idx + half >= len(acc_step):
            continue
        prev_window = acc_step[idx - half : idx]
        next_window = acc_step[idx + 1 : idx + half + 1]
        prev_valley_offset = int(np.argmin(prev_window))
        next_valley_offset = int(np.argmin(next_window))
        prev_valley_idx = idx - half + prev_valley_offset
        next_valley_idx = idx + 1 + next_valley_offset
        prev_pp = acc_step[idx] - acc_step[prev_valley_idx]
        next_pp = acc_step[idx] - acc_step[next_valley_idx]
        front_slope = float(np.mean(np.diff(acc_step[idx - half : idx + 1])))
        back_slope = float(np.mean(np.diff(acc_step[idx : idx + half + 1])))
        if prev_pp <= pp_threshold or next_pp <= pp_threshold:
            continue
        if front_slope <= 0.0 or back_slope >= 0.0:
            continue
        rows.append(
            {
                "step_index": len(rows),
                "step_time": t[idx],
                "peak_index": int(idx),
                "heading_time": t[prev_valley_idx],
                "heading_index": int(prev_valley_idx),
                "acc_step_peak": acc_step[idx],
                "acc_step_valley": acc_step[prev_valley_idx],
                "acc_step_peak_to_peak": prev_pp,
            }
        )
    return pd.DataFrame(rows)


def estimate_smartpdr_heading(sensor_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    t = sensor_df["t"].to_numpy(dtype=float)
    gyro_vertical = sensor_df["gyro_vertical"].to_numpy(dtype=float)
    heading_cfg = config["heading"]
    if bool(heading_cfg.get("use_bias_correction", True)):
        static_mask = t <= float(heading_cfg["bias_static_duration_s"])
        if not static_mask.any():
            raise ValueError("No samples found in SmartPDR gyro bias interval")
        bias = float(gyro_vertical[static_mask].mean())
    else:
        bias = 0.0
    gyro_corrected = (gyro_vertical - bias) * float(heading_cfg["gyro_sign"])
    mag_heading = np.unwrap(sensor_df["mag_heading_rad"].to_numpy(dtype=float))
    mag_heading -= np.deg2rad(float(heading_cfg.get("declination_deg", 0.0)))

    initial_source = str(heading_cfg.get("initial_heading_source", "magnetic"))
    if initial_source == "magnetic":
        initial_heading = float(mag_heading[0] + float(heading_cfg["initial_heading_rad"]))
    elif initial_source == "config":
        initial_heading = float(heading_cfg["initial_heading_rad"])
    else:
        raise ValueError("smartpdr.heading.initial_heading_source must be magnetic or config")

    gyro_heading = np.empty_like(gyro_corrected)
    gyro_heading[0] = initial_heading
    if len(gyro_heading) > 1:
        dt = np.diff(t)
        gyro_heading[1:] = gyro_heading[0] + np.cumsum(
            0.5 * (gyro_corrected[:-1] + gyro_corrected[1:]) * dt
        )
    gyro_heading = np.unwrap(gyro_heading)

    hcor_tau = np.deg2rad(float(heading_cfg["correlation_threshold_deg"]))
    hmag_tau = np.deg2rad(float(heading_cfg["mag_variation_threshold_deg"]))
    weights = np.array(
        [
            float(heading_cfg["weight_prev"]),
            float(heading_cfg["weight_mag"]),
            float(heading_cfg["weight_gyro"]),
        ]
    )

    fused = np.empty_like(gyro_heading)
    cases: list[str] = []
    fused[0] = _circular_mean(np.array([mag_heading[0], gyro_heading[0]]), weights[1:])
    cases.append("init")
    for i in range(1, len(t)):
        hcor = abs(_angle_diff(mag_heading[i], gyro_heading[i]))
        hmag = abs(_angle_diff(mag_heading[i], mag_heading[i - 1]))
        if hcor <= hcor_tau and hmag <= hmag_tau:
            values = np.array([fused[i - 1], mag_heading[i], gyro_heading[i]])
            fused[i] = _circular_mean(values, weights)
            cases.append("prev+mag+gyro")
        elif hcor <= hcor_tau and hmag > hmag_tau:
            fused[i] = _circular_mean(
                np.array([mag_heading[i], gyro_heading[i]]),
                np.array([weights[1], weights[2]]),
            )
            cases.append("mag+gyro")
        elif hcor > hcor_tau and hmag <= hmag_tau:
            fused[i] = fused[i - 1]
            cases.append("prev")
        else:
            fused[i] = _circular_mean(
                np.array([fused[i - 1], gyro_heading[i]]),
                np.array([weights[0], weights[2]]),
            )
            cases.append("prev+gyro")
    fused = np.unwrap(fused)
    return pd.DataFrame(
        {
            "t": t,
            "gyro_vertical": gyro_vertical,
            "gyro_vertical_corrected": gyro_corrected,
            "heading_gyro_rad": gyro_heading,
            "heading_mag_rad": mag_heading,
            "heading_rad": fused,
            "selection_case": cases,
        }
    )


def build_smartpdr_trajectory(
    steps_df: pd.DataFrame,
    heading_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    if steps_df.empty:
        return pd.DataFrame(
            columns=[
                "step_index",
                "step_time",
                "heading_time",
                "x",
                "y",
                "heading_rad",
                "step_length_m",
                "acc_step_peak_to_peak",
            ]
        )

    step_cfg = config["step_length"]
    heading_times = steps_df["heading_time"].to_numpy(dtype=float)
    headings = np.interp(
        heading_times,
        heading_df["t"].to_numpy(dtype=float),
        heading_df["heading_rad"].to_numpy(dtype=float),
    )
    if step_cfg["mode"] == "static":
        step_lengths = np.full(len(steps_df), float(step_cfg["static_length_m"]))
    else:
        step_lengths = estimate_step_lengths(
            steps_df["acc_step_peak_to_peak"].to_numpy(dtype=float),
            step_cfg,
        )

    xs: list[float] = []
    ys: list[float] = []
    x = 0.0
    y = 0.0
    for heading, step_length in zip(headings, step_lengths, strict=True):
        x += step_length * np.sin(heading)
        y += step_length * np.cos(heading)
        xs.append(x)
        ys.append(y)

    return pd.DataFrame(
        {
            "step_index": steps_df["step_index"].to_numpy(dtype=int),
            "step_time": steps_df["step_time"].to_numpy(dtype=float),
            "heading_time": heading_times,
            "x": xs,
            "y": ys,
            "heading_rad": headings,
            "step_length_m": step_lengths,
            "acc_step_peak_to_peak": steps_df["acc_step_peak_to_peak"].to_numpy(dtype=float),
        }
    )


def estimate_step_lengths(peak_to_peak: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    safe_pp = np.maximum(peak_to_peak, 1e-6)
    threshold = float(config["switch_threshold"])
    root = float(config["root_beta"]) * np.power(safe_pp, 0.25) + float(config["root_gamma"])
    log = float(config["log_beta"]) * np.log(safe_pp) + float(config["log_gamma"])
    lengths = np.where(safe_pp < threshold, root, log)
    return np.clip(lengths, float(config["min_length_m"]), float(config["max_length_m"]))


def tilt_compensated_mag_heading(mag: np.ndarray, gravity: np.ndarray) -> np.ndarray:
    gx, gy, gz = gravity[:, 0], gravity[:, 1], gravity[:, 2]
    mx, my, mz = mag[:, 0], mag[:, 1], mag[:, 2]
    roll = np.arctan2(gy, gz)
    pitch = np.arctan2(-gx, np.sqrt(gy * gy + gz * gz))
    mag_x = mx * np.cos(pitch) + mz * np.sin(pitch)
    mag_y = (
        mx * np.sin(roll) * np.sin(pitch)
        + my * np.cos(roll)
        - mz * np.sin(roll) * np.cos(pitch)
    )
    return np.unwrap(np.arctan2(-mag_y, mag_x))


def plot_smartpdr_acc(
    sensor_df: pd.DataFrame,
    steps_df: pd.DataFrame,
    output_path: str | Path,
    dpi: int,
    show_grid: bool,
) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(sensor_df["t"], sensor_df["acc_vertical"], label="vertical_acc", alpha=0.35)
    ax.plot(sensor_df["t"], sensor_df["acc_hpf"], label="hpf", alpha=0.55)
    ax.plot(sensor_df["t"], sensor_df["acc_step"], label="step_acc")
    if not steps_df.empty:
        ax.scatter(
            steps_df["step_time"],
            steps_df["acc_step_peak"],
            s=18,
            label="step peaks",
            zorder=3,
        )
        ax.scatter(
            steps_df["heading_time"],
            steps_df["acc_step_valley"],
            s=18,
            label="heading valleys",
            zorder=3,
        )
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Acceleration [m/s^2]")
    ax.legend()
    ax.grid(show_grid)
    fig.tight_layout()
    _save(fig, output_path, dpi)


def plot_smartpdr_heading(
    heading_df: pd.DataFrame,
    output_path: str | Path,
    dpi: int,
    show_grid: bool,
) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(heading_df["t"], heading_df["gyro_vertical"], label="gyro_vertical", alpha=0.4)
    axes[0].plot(
        heading_df["t"],
        heading_df["gyro_vertical_corrected"],
        label="gyro_vertical_corrected",
    )
    axes[0].set_ylabel("Angular rate [rad/s]")
    axes[0].legend()
    axes[0].grid(show_grid)

    axes[1].plot(heading_df["t"], heading_df["heading_mag_rad"], label="mag")
    axes[1].plot(heading_df["t"], heading_df["heading_gyro_rad"], label="gyro")
    axes[1].plot(heading_df["t"], heading_df["heading_rad"], label="SmartPDR", linewidth=2)
    axes[1].set_xlabel("Time [s]")
    axes[1].set_ylabel("Heading [rad]")
    axes[1].legend()
    axes[1].grid(show_grid)
    fig.tight_layout()
    _save(fig, output_path, dpi)


def _save(fig: Any, output_path: str | Path, dpi: int) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    import matplotlib.pyplot as plt

    plt.close(fig)


def _median_sample_interval(t: np.ndarray) -> float:
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) == 0:
        raise ValueError("Timestamps must be strictly increasing")
    return float(np.median(dt))


def _angle_diff(a: float, b: float) -> float:
    return float((a - b + np.pi) % (2.0 * np.pi) - np.pi)


def _circular_mean(values: np.ndarray, weights: np.ndarray) -> float:
    sin_sum = float(np.sum(weights * np.sin(values)))
    cos_sum = float(np.sum(weights * np.cos(values)))
    return float(np.arctan2(sin_sum, cos_sum))
