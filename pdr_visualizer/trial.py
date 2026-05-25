from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import (
    infer_holding_position,
    output_trial_id,
    read_accelerometer_csv,
    read_gyroscope_csv,
    read_metadata_or_default,
    resolve_trial_dir,
)
from .plotting import plot_acc_norm, plot_heading, plot_trajectory
from .processing import add_acc_norm, build_trajectory, detect_steps, estimate_heading


def run_trial(
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

    gyro_axis = metadata.get("gyro_axis", config["heading"]["gyro_axis"])
    gyro_sign = metadata.get("gyro_sign", config["heading"]["gyro_sign"])
    gyro_sign = config["heading"].get("gyro_sign_overrides", {}).get(output_id, gyro_sign)
    step_length_m = metadata.get("step_length_m", config["pdr"]["step_length_m"])

    acc_df = add_acc_norm(
        acc_df,
        window_size=int(config["preprocessing"]["acc_smoothing_window"]),
    )
    steps_df = detect_steps(
        acc_df,
        height=config["step_detection"].get("height"),
        distance_s=float(config["step_detection"]["distance_s"]),
        prominence=config["step_detection"].get("prominence"),
    )
    heading_df = estimate_heading(
        gyro_df,
        gyro_axis=str(gyro_axis),
        gyro_sign=float(gyro_sign),
        initial_heading_rad=float(config["heading"]["initial_heading_rad"]),
        use_bias_correction=bool(config["heading"].get("use_bias_correction", True)),
        bias_static_duration_s=float(config["heading"]["bias_static_duration_s"]),
    )
    trajectory_df = build_trajectory(
        steps_df,
        heading_df,
        step_length_m=float(step_length_m),
    )

    trial_output_dir = Path("outputs") / output_id
    processed_dir = trial_output_dir / "processed"
    figures_dir = trial_output_dir / "figures"
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "steps": processed_dir / "steps.csv",
        "heading": processed_dir / "heading.csv",
        "trajectory": processed_dir / "trajectory.csv",
        "acc_norm_figure": figures_dir / "acc_norm.png",
        "heading_figure": figures_dir / "heading.png",
        "trajectory_figure": figures_dir / "trajectory.png",
    }

    steps_df.to_csv(paths["steps"], index=False)
    heading_df[["t", "heading_rad"]].to_csv(paths["heading"], index=False)
    trajectory_df.to_csv(paths["trajectory"], index=False)

    dpi = int(config["visualization"]["figure_dpi"])
    show_grid = bool(config["visualization"]["show_grid"])
    equal_axis = bool(config["visualization"]["equal_axis"])
    plot_acc_norm(acc_df, steps_df, paths["acc_norm_figure"], dpi, show_grid)
    plot_heading(heading_df, str(gyro_axis), paths["heading_figure"], dpi, show_grid)
    plot_trajectory(
        trajectory_df,
        paths["trajectory_figure"],
        title=output_id,
        dpi=dpi,
        equal_axis=equal_axis,
        show_grid=show_grid,
    )
    return paths
