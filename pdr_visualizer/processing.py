from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def add_acc_norm(acc_df: pd.DataFrame, window_size: int) -> pd.DataFrame:
    if window_size < 1:
        raise ValueError("acc_smoothing_window must be >= 1")

    df = acc_df.copy()
    df["acc_norm"] = np.sqrt(df["acc_x"] ** 2 + df["acc_y"] ** 2 + df["acc_z"] ** 2)
    df["acc_norm_smooth"] = (
        df["acc_norm"].rolling(window=window_size, center=True, min_periods=1).mean()
    )
    return df


def detect_steps(
    acc_df: pd.DataFrame,
    height: float | None,
    distance_s: float,
    prominence: float | None,
) -> pd.DataFrame:
    sample_interval = _median_sample_interval(acc_df["t"].to_numpy())
    distance_samples = max(1, int(round(distance_s / sample_interval)))
    peaks, _ = find_peaks(
        acc_df["acc_norm_smooth"].to_numpy(),
        height=height,
        distance=distance_samples,
        prominence=prominence,
    )
    steps = pd.DataFrame(
        {
            "step_index": np.arange(len(peaks), dtype=int),
            "step_time": acc_df["t"].iloc[peaks].to_numpy(),
            "acc_norm_smooth": acc_df["acc_norm_smooth"].iloc[peaks].to_numpy(),
        }
    )
    return steps


def estimate_heading(
    gyro_df: pd.DataFrame,
    gyro_axis: str,
    gyro_sign: float,
    initial_heading_rad: float,
    use_bias_correction: bool,
    bias_static_duration_s: float,
    gravity_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = gyro_df.copy()
    axis_col, raw = _gyro_rate_for_heading(df, gyro_axis, gravity_df)
    if use_bias_correction:
        static_mask = df["t"].to_numpy() <= bias_static_duration_s
        if not static_mask.any():
            raise ValueError(
                "No gyro samples found in bias_static_duration_s interval. "
                "Check timestamps or reduce heading.bias_static_duration_s."
            )
        bias = float(raw[static_mask].mean())
    else:
        bias = 0.0

    if gyro_sign not in (-1.0, 1.0):
        raise ValueError("gyro_sign must be 1.0 or -1.0")

    corrected = (raw - bias) * gyro_sign
    t = df["t"].to_numpy()
    heading = np.empty_like(corrected, dtype=float)
    heading[0] = initial_heading_rad
    if len(heading) > 1:
        dt = np.diff(t)
        trapezoids = 0.5 * (corrected[:-1] + corrected[1:]) * dt
        heading[1:] = initial_heading_rad + np.cumsum(trapezoids)

    return pd.DataFrame(
        {
            "t": t,
            axis_col: raw,
            f"{axis_col}_corrected": corrected,
            "heading_rad": heading,
        }
    )


def build_trajectory(
    steps_df: pd.DataFrame, heading_df: pd.DataFrame, step_length_m: float
) -> pd.DataFrame:
    if step_length_m <= 0:
        raise ValueError("step_length_m must be > 0")

    step_times = steps_df["step_time"].to_numpy()
    headings = np.interp(
        step_times,
        heading_df["t"].to_numpy(),
        heading_df["heading_rad"].to_numpy(),
    )

    xs: list[float] = []
    ys: list[float] = []
    x = 0.0
    y = 0.0
    for heading in headings:
        x += step_length_m * np.sin(heading)
        y += step_length_m * np.cos(heading)
        xs.append(x)
        ys.append(y)

    return pd.DataFrame(
        {
            "step_index": steps_df["step_index"].to_numpy(dtype=int),
            "step_time": step_times,
            "x": xs,
            "y": ys,
            "heading_rad": headings,
        }
    )


def _median_sample_interval(t: np.ndarray) -> float:
    if len(t) < 2:
        raise ValueError("At least two samples are required")
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) == 0:
        raise ValueError("Timestamps must be strictly increasing")
    return float(np.median(dt))


def _gyro_rate_for_heading(
    gyro_df: pd.DataFrame, gyro_axis: str, gravity_df: pd.DataFrame | None
) -> tuple[str, np.ndarray]:
    if gyro_axis in {"vertical", "gravity", "auto"}:
        if gravity_df is None:
            raise ValueError(
                "gyro_axis='vertical' requires Gravity.csv. "
                "Use gyro_axis x, y, or z if Gravity.csv is unavailable."
            )
        t = gyro_df["t"].to_numpy()
        gravity = np.column_stack(
            [
                np.interp(t, gravity_df["t"], gravity_df["gravity_x"]),
                np.interp(t, gravity_df["t"], gravity_df["gravity_y"]),
                np.interp(t, gravity_df["t"], gravity_df["gravity_z"]),
            ]
        )
        norm = np.linalg.norm(gravity, axis=1)
        if np.any(norm == 0):
            raise ValueError("Gravity.csv contains zero-length gravity samples")
        gravity_unit = gravity / norm[:, None]
        omega = gyro_df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy()
        # Project device angular velocity onto the gravity direction. The final
        # sign convention is controlled by heading.gyro_sign.
        return "gyro_vertical", np.sum(omega * gravity_unit, axis=1)

    axis_col = f"gyro_{gyro_axis}"
    if axis_col not in gyro_df.columns:
        raise ValueError("gyro_axis must be one of: vertical, x, y, z")
    return axis_col, gyro_df[axis_col].to_numpy()
