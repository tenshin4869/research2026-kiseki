from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .io import (
    find_trial_dirs,
    infer_holding_position,
    output_trial_id,
    read_metadata_or_default,
)
from .plotting import plot_overlay
from .trial import run_trial


def plot_trials(
    config: dict[str, Any],
    holding_position: str | None = None,
    compare: tuple[str, str] | None = None,
    trajectory_kind: str = "corrected",
) -> Path:
    if holding_position and compare:
        raise ValueError("Use either holding_position or compare, not both")
    if trajectory_kind not in {"raw", "corrected", "v2"}:
        raise ValueError("trajectory_kind must be 'raw', 'corrected', or 'v2'")

    raw_data_dir = Path(config["paths"]["raw_data_dir"])
    processed_dir = Path(config["paths"]["processed_dir"])
    figures_dir = Path(config["paths"]["figures_dir"])
    v2_subdir = str(config.get("turn_correction_v2", {}).get("output_subdir", "turn_correction_v2"))
    processed_v2_dir = Path("outputs") / v2_subdir / "processed"
    figures_v2_dir = Path("outputs") / v2_subdir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures_v2_dir.mkdir(parents=True, exist_ok=True)

    target_positions = set(compare) if compare else {holding_position}
    if None in target_positions:
        raise ValueError("holding_position or compare is required")

    trajectories: list[tuple[str, str, pd.DataFrame]] = []
    for trial_path in find_trial_dirs(raw_data_dir):
        metadata = read_metadata_or_default(trial_path / "metadata.json", trial_path.name)
        inferred_position = infer_holding_position(trial_path)
        if inferred_position and metadata.get("holding_position") in {None, "", "unknown"}:
            metadata["holding_position"] = inferred_position

        trial_id = trial_path.name
        position = str(metadata.get("holding_position", ""))
        if position not in target_positions:
            continue

        output_id = output_trial_id(raw_data_dir, trial_path, metadata)
        if trajectory_kind == "v2":
            trajectory_path = processed_v2_dir / f"{output_id}_trajectory_v2.csv"
        else:
            suffix = "trajectory_corrected" if trajectory_kind == "corrected" else "trajectory"
            trajectory_path = processed_dir / f"{output_id}_{suffix}.csv"
        if not trajectory_path.exists():
            run_trial(trial_id, config, holding_position=position)
        if not trajectory_path.exists():
            raise FileNotFoundError(
                f"Processed {trajectory_kind} trajectory not found for {output_id}: "
                f"{trajectory_path}"
            )
        trajectories.append((output_id, position, pd.read_csv(trajectory_path)))

    if not trajectories:
        positions = ", ".join(sorted(str(p) for p in target_positions))
        raise ValueError(f"No trials found for holding_position: {positions}")

    if compare:
        kind_suffix = "" if trajectory_kind == "corrected" else f"_{trajectory_kind}"
        output_dir = figures_v2_dir if trajectory_kind == "v2" else figures_dir
        output_path = output_dir / f"overlay_{compare[0]}_vs_{compare[1]}{kind_suffix}.png"
        title = f"{compare[0]} vs {compare[1]} ({trajectory_kind})"
    else:
        kind_suffix = "" if trajectory_kind == "corrected" else f"_{trajectory_kind}"
        output_dir = figures_v2_dir if trajectory_kind == "v2" else figures_dir
        output_path = output_dir / f"overlay_{holding_position}_trials{kind_suffix}.png"
        title = f"{holding_position} trials ({trajectory_kind})"

    plot_overlay(
        trajectories,
        output_path,
        title=title,
        dpi=int(config["visualization"]["figure_dpi"]),
        equal_axis=bool(config["visualization"]["equal_axis"]),
        show_grid=bool(config["visualization"]["show_grid"]),
    )
    return output_path
