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
from .smartpdr import run_smartpdr_trial


def plot_smartpdr_trials(
    config: dict[str, Any],
    holding_position: str | None = None,
    compare: tuple[str, str] | None = None,
) -> Path:
    if holding_position and compare:
        raise ValueError("Use either holding_position or compare, not both")

    raw_data_dir = Path(config["paths"]["raw_data_dir"])
    output_root = Path(config["smartpdr"]["output_dir"])
    overlay_dir = output_root / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    target_positions = set(compare) if compare else {holding_position}
    if None in target_positions:
        raise ValueError("holding_position or compare is required")

    trajectories: list[tuple[str, str, pd.DataFrame]] = []
    for trial_path in find_trial_dirs(raw_data_dir):
        if not (trial_path / "Magnetometer.csv").exists() or not (trial_path / "Gravity.csv").exists():
            continue
        metadata = read_metadata_or_default(trial_path / "metadata.json", trial_path.name)
        inferred_position = infer_holding_position(trial_path)
        if inferred_position and metadata.get("holding_position") in {None, "", "unknown"}:
            metadata["holding_position"] = inferred_position

        position = str(metadata.get("holding_position", ""))
        if position not in target_positions:
            continue

        output_id = output_trial_id(raw_data_dir, trial_path, metadata)
        trajectory_path = output_root / output_id / "processed" / "trajectory.csv"
        if not trajectory_path.exists():
            run_smartpdr_trial(trial_path.name, config, holding_position=position)
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Processed trajectory not found: {trajectory_path}")
        trajectories.append((output_id, position, pd.read_csv(trajectory_path)))

    if not trajectories:
        positions = ", ".join(sorted(str(p) for p in target_positions))
        raise ValueError(f"No SmartPDR trials found for holding_position: {positions}")

    if compare:
        output_path = overlay_dir / f"{compare[0]}_vs_{compare[1]}" / "trajectory_overlay.png"
        title = f"SmartPDR {compare[0]} vs {compare[1]}"
    else:
        output_path = overlay_dir / str(holding_position) / "trajectory_overlay.png"
        title = f"SmartPDR {holding_position} trials"

    plot_overlay(
        trajectories,
        output_path,
        title=title,
        dpi=int(config["visualization"]["figure_dpi"]),
        equal_axis=bool(config["visualization"]["equal_axis"]),
        show_grid=bool(config["visualization"]["show_grid"]),
    )
    return output_path
