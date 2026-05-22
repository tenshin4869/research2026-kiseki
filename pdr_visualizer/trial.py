from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import (
    infer_holding_position,
    output_trial_id,
    read_accelerometer_csv,
    read_gravity_csv,
    read_gyroscope_csv,
    read_metadata_or_default,
    resolve_trial_dir,
)
from .plotting import (
    plot_acc_norm,
    plot_heading,
    plot_trajectory,
    plot_trajectory_comparison,
)
from .processing import (
    add_acc_norm,
    build_trajectory,
    detect_steps,
    estimate_heading,
    suppress_straight_heading_drift,
    suppress_straight_heading_drift_v2,
)


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
    acc_df = read_accelerometer_csv(raw_dir / "Accelerometer.csv")
    gyro_df = read_gyroscope_csv(raw_dir / "Gyroscope.csv")
    gravity_path = raw_dir / "Gravity.csv"
    gravity_df = read_gravity_csv(gravity_path) if gravity_path.exists() else None

    gyro_axis = metadata.get("gyro_axis", config["heading"]["gyro_axis"])
    gyro_sign = metadata.get("gyro_sign", config["heading"]["gyro_sign"])
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
        gravity_df=gravity_df,
    )
    trajectory_df = build_trajectory(
        steps_df,
        heading_df,
        step_length_m=float(step_length_m),
    )
    corrected_heading_df = None
    turn_segments_df = None
    corrected_trajectory_df = None
    corrected_v2_heading_df = None
    turn_segments_v2_df = None
    corrected_v2_trajectory_df = None
    if bool(config.get("turn_correction", {}).get("enabled", False)):
        corrected_heading_df, turn_segments_df = suppress_straight_heading_drift(
            heading_df,
            angular_velocity_threshold_rad_s=float(
                config["turn_correction"]["angular_velocity_threshold_rad_s"]
            ),
            min_turn_duration_s=float(config["turn_correction"]["min_turn_duration_s"]),
            min_turn_angle_deg=float(config["turn_correction"]["min_turn_angle_deg"]),
            merge_gap_s=float(config["turn_correction"]["merge_gap_s"]),
        )
        corrected_trajectory_df = build_trajectory(
            steps_df,
            corrected_heading_df,
            step_length_m=float(step_length_m),
        )
    if bool(config.get("turn_correction_v2", {}).get("enabled", False)):
        corrected_v2_heading_df, turn_segments_v2_df = suppress_straight_heading_drift_v2(
            heading_df,
            start_threshold_rad_s=float(config["turn_correction_v2"]["start_threshold_rad_s"]),
            end_threshold_rad_s=float(config["turn_correction_v2"]["end_threshold_rad_s"]),
            pre_turn_margin_s=float(config["turn_correction_v2"]["pre_turn_margin_s"]),
            post_turn_margin_s=float(config["turn_correction_v2"]["post_turn_margin_s"]),
            min_turn_duration_s=float(config["turn_correction_v2"]["min_turn_duration_s"]),
            min_turn_angle_deg=float(config["turn_correction_v2"]["min_turn_angle_deg"]),
            merge_gap_s=float(config["turn_correction_v2"]["merge_gap_s"]),
            update_bias_from_straight=bool(
                config["turn_correction_v2"]["update_bias_from_straight"]
            ),
        )
        corrected_v2_trajectory_df = build_trajectory(
            steps_df,
            corrected_v2_heading_df,
            step_length_m=float(step_length_m),
        )

    processed_dir = Path(config["paths"]["processed_dir"])
    figures_dir = Path(config["paths"]["figures_dir"])
    v2_subdir = str(config.get("turn_correction_v2", {}).get("output_subdir", "turn_correction_v2"))
    processed_v2_dir = Path("outputs") / v2_subdir / "processed"
    figures_v2_dir = Path("outputs") / v2_subdir / "figures"
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    processed_v2_dir.mkdir(parents=True, exist_ok=True)
    figures_v2_dir.mkdir(parents=True, exist_ok=True)
    output_id = output_trial_id(config["paths"]["raw_data_dir"], raw_dir, metadata)

    paths = {
        "steps": processed_dir / f"{output_id}_steps.csv",
        "heading": processed_dir / f"{output_id}_heading.csv",
        "trajectory": processed_dir / f"{output_id}_trajectory.csv",
        "heading_corrected": processed_dir / f"{output_id}_heading_corrected.csv",
        "turn_segments": processed_dir / f"{output_id}_turn_segments.csv",
        "trajectory_corrected": processed_dir / f"{output_id}_trajectory_corrected.csv",
        "acc_norm_figure": figures_dir / f"{output_id}_acc_norm.png",
        "heading_figure": figures_dir / f"{output_id}_heading.png",
        "heading_corrected_figure": figures_dir / f"{output_id}_heading_corrected.png",
        "trajectory_figure": figures_dir / f"{output_id}_trajectory.png",
        "trajectory_corrected_figure": figures_dir / f"{output_id}_trajectory_corrected.png",
        "trajectory_comparison_figure": figures_dir / f"{output_id}_trajectory_comparison.png",
        "heading_v2": processed_v2_dir / f"{output_id}_heading_v2.csv",
        "turn_segments_v2": processed_v2_dir / f"{output_id}_turn_segments_v2.csv",
        "trajectory_v2": processed_v2_dir / f"{output_id}_trajectory_v2.csv",
        "heading_v2_figure": figures_v2_dir / f"{output_id}_heading_v2.png",
        "trajectory_v2_figure": figures_v2_dir / f"{output_id}_trajectory_v2.png",
        "trajectory_v2_comparison_figure": figures_v2_dir
        / f"{output_id}_trajectory_v2_comparison.png",
    }

    steps_df.to_csv(paths["steps"], index=False)
    heading_df[["t", "heading_rad"]].to_csv(paths["heading"], index=False)
    trajectory_df.to_csv(paths["trajectory"], index=False)
    if corrected_heading_df is not None and turn_segments_df is not None and corrected_trajectory_df is not None:
        corrected_heading_df[
            ["t", "heading_raw_rad", "heading_rad", "is_turning", "turn_rate_used"]
        ].to_csv(paths["heading_corrected"], index=False)
        turn_segments_df.to_csv(paths["turn_segments"], index=False)
        corrected_trajectory_df.to_csv(paths["trajectory_corrected"], index=False)
    if (
        corrected_v2_heading_df is not None
        and turn_segments_v2_df is not None
        and corrected_v2_trajectory_df is not None
    ):
        corrected_v2_heading_df[
            [
                "t",
                "heading_raw_rad",
                "heading_rad",
                "is_turning",
                "turn_rate_used",
                "straight_bias_delta",
            ]
        ].to_csv(paths["heading_v2"], index=False)
        turn_segments_v2_df.to_csv(paths["turn_segments_v2"], index=False)
        corrected_v2_trajectory_df.to_csv(paths["trajectory_v2"], index=False)

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
    if corrected_heading_df is not None and corrected_trajectory_df is not None:
        plot_heading(corrected_heading_df, str(gyro_axis), paths["heading_corrected_figure"], dpi, show_grid)
        plot_trajectory(
            corrected_trajectory_df,
            paths["trajectory_corrected_figure"],
            title=f"{output_id} corrected",
            dpi=dpi,
            equal_axis=equal_axis,
            show_grid=show_grid,
        )
        plot_trajectory_comparison(
            trajectory_df,
            corrected_trajectory_df,
            paths["trajectory_comparison_figure"],
            title=f"{output_id} raw vs corrected",
            dpi=dpi,
            equal_axis=equal_axis,
            show_grid=show_grid,
        )
    if corrected_v2_heading_df is not None and corrected_v2_trajectory_df is not None:
        plot_heading(corrected_v2_heading_df, str(gyro_axis), paths["heading_v2_figure"], dpi, show_grid)
        plot_trajectory(
            corrected_v2_trajectory_df,
            paths["trajectory_v2_figure"],
            title=f"{output_id} turn correction v2",
            dpi=dpi,
            equal_axis=equal_axis,
            show_grid=show_grid,
        )
        plot_trajectory_comparison(
            trajectory_df,
            corrected_v2_trajectory_df,
            paths["trajectory_v2_comparison_figure"],
            title=f"{output_id} raw vs turn correction v2",
            dpi=dpi,
            equal_axis=equal_axis,
            show_grid=show_grid,
        )
    return paths
