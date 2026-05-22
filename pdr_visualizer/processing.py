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


def suppress_straight_heading_drift(
    heading_df: pd.DataFrame,
    angular_velocity_threshold_rad_s: float,
    min_turn_duration_s: float,
    min_turn_angle_deg: float,
    merge_gap_s: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if angular_velocity_threshold_rad_s <= 0:
        raise ValueError("angular_velocity_threshold_rad_s must be > 0")
    if min_turn_duration_s < 0:
        raise ValueError("min_turn_duration_s must be >= 0")
    if merge_gap_s < 0:
        raise ValueError("merge_gap_s must be >= 0")
    if min_turn_angle_deg < 0:
        raise ValueError("min_turn_angle_deg must be >= 0")

    t = heading_df["t"].to_numpy()
    if len(t) < 2:
        raise ValueError("At least two heading samples are required")

    rate_col = _corrected_rate_column(heading_df)
    rate = heading_df[rate_col].to_numpy()
    turn_mask = np.abs(rate) >= angular_velocity_threshold_rad_s
    turn_mask = _merge_short_false_gaps(t, turn_mask, merge_gap_s)
    turn_mask = _remove_short_true_runs(t, turn_mask, min_turn_duration_s)
    turn_mask = _remove_small_angle_true_runs(t, rate, turn_mask, min_turn_angle_deg)

    used_rate = np.where(turn_mask, rate, 0.0)
    corrected_heading = np.empty_like(used_rate, dtype=float)
    corrected_heading[0] = float(heading_df["heading_rad"].iloc[0])
    dt = np.diff(t)
    trapezoids = 0.5 * (used_rate[:-1] + used_rate[1:]) * dt
    corrected_heading[1:] = corrected_heading[0] + np.cumsum(trapezoids)

    corrected_df = heading_df.copy()
    corrected_df["is_turning"] = turn_mask
    corrected_df["turn_rate_used"] = used_rate
    corrected_df["heading_raw_rad"] = corrected_df["heading_rad"]
    corrected_df["heading_rad"] = corrected_heading

    segments_df = _turn_segments(t, turn_mask, corrected_heading)
    return corrected_df, segments_df


def suppress_straight_heading_drift_v2(
    heading_df: pd.DataFrame,
    start_threshold_rad_s: float,
    end_threshold_rad_s: float,
    pre_turn_margin_s: float,
    post_turn_margin_s: float,
    min_turn_duration_s: float,
    min_turn_angle_deg: float,
    merge_gap_s: float,
    update_bias_from_straight: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if start_threshold_rad_s <= 0:
        raise ValueError("start_threshold_rad_s must be > 0")
    if end_threshold_rad_s <= 0:
        raise ValueError("end_threshold_rad_s must be > 0")
    if end_threshold_rad_s > start_threshold_rad_s:
        raise ValueError("end_threshold_rad_s must be <= start_threshold_rad_s")
    if pre_turn_margin_s < 0 or post_turn_margin_s < 0:
        raise ValueError("turn margins must be >= 0")

    t = heading_df["t"].to_numpy()
    if len(t) < 2:
        raise ValueError("At least two heading samples are required")

    rate_col = _corrected_rate_column(heading_df)
    rate = heading_df[rate_col].to_numpy()
    turn_mask = _hysteresis_turn_mask(rate, start_threshold_rad_s, end_threshold_rad_s)
    turn_mask = _merge_short_false_gaps(t, turn_mask, merge_gap_s)
    turn_mask = _expand_mask_by_time(t, turn_mask, pre_turn_margin_s, post_turn_margin_s)
    turn_mask = _remove_short_true_runs(t, turn_mask, min_turn_duration_s)

    bias_delta = 0.0
    if update_bias_from_straight and np.any(~turn_mask):
        bias_delta = float(np.median(rate[~turn_mask]))
    rate_bias_corrected = rate - bias_delta
    turn_mask = _remove_small_angle_true_runs(
        t, rate_bias_corrected, turn_mask, min_turn_angle_deg
    )

    used_rate = np.where(turn_mask, rate_bias_corrected, 0.0)
    corrected_heading = np.empty_like(used_rate, dtype=float)
    corrected_heading[0] = float(heading_df["heading_rad"].iloc[0])
    dt = np.diff(t)
    trapezoids = 0.5 * (used_rate[:-1] + used_rate[1:]) * dt
    corrected_heading[1:] = corrected_heading[0] + np.cumsum(trapezoids)

    corrected_df = heading_df.copy()
    corrected_df["is_turning"] = turn_mask
    corrected_df["turn_rate_used"] = used_rate
    corrected_df["straight_bias_delta"] = bias_delta
    corrected_df["heading_raw_rad"] = corrected_df["heading_rad"]
    corrected_df["heading_rad"] = corrected_heading

    segments_df = _turn_segments(t, turn_mask, corrected_heading)
    if not segments_df.empty:
        segments_df["straight_bias_delta_rad_s"] = bias_delta
    return corrected_df, segments_df


def _median_sample_interval(t: np.ndarray) -> float:
    if len(t) < 2:
        raise ValueError("At least two samples are required")
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) == 0:
        raise ValueError("Timestamps must be strictly increasing")
    return float(np.median(dt))


def _corrected_rate_column(heading_df: pd.DataFrame) -> str:
    matches = [col for col in heading_df.columns if col.startswith("gyro_") and col.endswith("_corrected")]
    if len(matches) != 1:
        raise ValueError(
            "Expected exactly one corrected gyro column in heading_df, "
            f"found {matches}"
        )
    return matches[0]


def _merge_short_false_gaps(t: np.ndarray, mask: np.ndarray, max_gap_s: float) -> np.ndarray:
    if max_gap_s == 0:
        return mask.copy()
    result = mask.copy()
    for value, start, end in _runs(mask):
        if value:
            continue
        gap_duration = _run_duration(t, start, end)
        touches_edge = start == 0 or end == len(mask)
        if not touches_edge and gap_duration <= max_gap_s:
            result[start:end] = True
    return result


def _hysteresis_turn_mask(
    rate: np.ndarray, start_threshold: float, end_threshold: float
) -> np.ndarray:
    mask = np.zeros(len(rate), dtype=bool)
    in_turn = False
    for i, value in enumerate(np.abs(rate)):
        if in_turn:
            if value <= end_threshold:
                in_turn = False
            else:
                mask[i] = True
        elif value >= start_threshold:
            in_turn = True
            mask[i] = True
    return mask


def _expand_mask_by_time(
    t: np.ndarray, mask: np.ndarray, pre_margin_s: float, post_margin_s: float
) -> np.ndarray:
    if pre_margin_s == 0 and post_margin_s == 0:
        return mask.copy()
    result = mask.copy()
    for value, start, end in _runs(mask):
        if not value:
            continue
        start_time = t[start] - pre_margin_s
        end_time = t[end - 1] + post_margin_s
        expanded_start = int(np.searchsorted(t, start_time, side="left"))
        expanded_end = int(np.searchsorted(t, end_time, side="right"))
        result[expanded_start:expanded_end] = True
    return result


def _remove_short_true_runs(t: np.ndarray, mask: np.ndarray, min_duration_s: float) -> np.ndarray:
    if min_duration_s == 0:
        return mask.copy()
    result = mask.copy()
    for value, start, end in _runs(mask):
        if not value:
            continue
        if _run_duration(t, start, end) < min_duration_s:
            result[start:end] = False
    return result


def _remove_small_angle_true_runs(
    t: np.ndarray, rate: np.ndarray, mask: np.ndarray, min_angle_deg: float
) -> np.ndarray:
    if min_angle_deg == 0:
        return mask.copy()
    result = mask.copy()
    min_angle_rad = np.radians(min_angle_deg)
    for value, start, end in _runs(mask):
        if not value:
            continue
        if end - start < 2:
            result[start:end] = False
            continue
        angle = np.trapz(rate[start:end], t[start:end])
        if abs(angle) < min_angle_rad:
            result[start:end] = False
    return result


def _turn_segments(t: np.ndarray, mask: np.ndarray, heading: np.ndarray) -> pd.DataFrame:
    columns = [
        "turn_index",
        "start_time",
        "end_time",
        "duration_s",
        "angle_delta_rad",
        "angle_delta_deg",
        "direction",
    ]
    rows = []
    segment_index = 0
    for value, start, end in _runs(mask):
        if not value:
            continue
        start_idx = start
        end_idx = end - 1
        angle_delta = heading[end_idx] - heading[start_idx]
        rows.append(
            {
                "turn_index": segment_index,
                "start_time": t[start_idx],
                "end_time": t[end_idx],
                "duration_s": t[end_idx] - t[start_idx],
                "angle_delta_rad": angle_delta,
                "angle_delta_deg": np.degrees(angle_delta),
                "direction": "right" if angle_delta > 0 else "left",
            }
        )
        segment_index += 1
    return pd.DataFrame(rows, columns=columns)


def _runs(mask: np.ndarray) -> list[tuple[bool, int, int]]:
    if len(mask) == 0:
        return []
    runs = []
    start = 0
    current = bool(mask[0])
    for i in range(1, len(mask)):
        value = bool(mask[i])
        if value != current:
            runs.append((current, start, i))
            start = i
            current = value
    runs.append((current, start, len(mask)))
    return runs


def _run_duration(t: np.ndarray, start: int, end: int) -> float:
    if end <= start:
        return 0.0
    return float(t[end - 1] - t[start])


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
