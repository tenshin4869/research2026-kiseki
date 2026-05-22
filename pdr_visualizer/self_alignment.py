from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .io import (
    find_trial_dirs,
    infer_holding_position,
    output_trial_id,
    read_metadata_or_default,
)
from .plotting import plot_anchor_clusters
from .trial import run_trial


def run_self_alignment(
    config: dict[str, Any],
    holding_position: str | None,
    trajectory_kind: str,
) -> dict[str, Path]:
    if trajectory_kind not in {"raw", "v2"}:
        raise ValueError("trajectory_kind must be 'raw' or 'v2'")

    raw_data_dir = Path(config["paths"]["raw_data_dir"])
    out_root = Path("outputs") / str(config["self_alignment"]["output_subdir"]) / trajectory_kind
    processed_dir = out_root / "processed"
    figures_dir = out_root / "figures"
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    trajectories: list[tuple[str, str, pd.DataFrame]] = []
    events: list[dict[str, Any]] = []

    for trial_path in find_trial_dirs(raw_data_dir):
        metadata = read_metadata_or_default(trial_path / "metadata.json", trial_path.name)
        inferred_position = infer_holding_position(trial_path)
        if inferred_position and metadata.get("holding_position") in {None, "", "unknown"}:
            metadata["holding_position"] = inferred_position
        position = str(metadata.get("holding_position", "unknown"))
        if holding_position and position != holding_position:
            continue

        output_id = output_trial_id(raw_data_dir, trial_path, metadata)
        trajectory_path = _trajectory_path(config, output_id, trajectory_kind)
        if not trajectory_path.exists():
            run_trial(trial_path.name, config, holding_position=position)
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Trajectory not found after processing: {trajectory_path}")

        trajectory_df = pd.read_csv(trajectory_path)
        trajectories.append((output_id, position, trajectory_df))
        events.extend(_extract_events(config, output_id, position, trajectory_df, trajectory_kind))

    if not trajectories:
        label = holding_position or "all"
        raise ValueError(f"No trajectories found for self-alignment: {label}")

    event_df = pd.DataFrame(events)
    cluster_df = _cluster_events(
        event_df,
        eps_m=float(config["self_alignment"]["cluster_eps_m"]),
        min_cluster_size=int(config["self_alignment"]["min_cluster_size"]),
    )

    label = holding_position or "all"
    event_path = processed_dir / f"{label}_events.csv"
    cluster_path = processed_dir / f"{label}_anchor_clusters.csv"
    figure_path = figures_dir / f"{label}_anchor_clusters.png"
    event_df.to_csv(event_path, index=False)
    cluster_df.to_csv(cluster_path, index=False)
    plot_anchor_clusters(
        trajectories,
        event_df,
        cluster_df,
        figure_path,
        title=f"Self-alignment anchors: {label} ({trajectory_kind})",
        dpi=int(config["visualization"]["figure_dpi"]),
        equal_axis=bool(config["visualization"]["equal_axis"]),
        show_grid=bool(config["visualization"]["show_grid"]),
    )

    return {
        "events": event_path,
        "anchor_clusters": cluster_path,
        "figure": figure_path,
    }


def _trajectory_path(config: dict[str, Any], output_id: str, trajectory_kind: str) -> Path:
    if trajectory_kind == "raw":
        return Path(config["paths"]["processed_dir"]) / f"{output_id}_trajectory.csv"
    v2_subdir = str(config["turn_correction_v2"]["output_subdir"])
    return Path("outputs") / v2_subdir / "processed" / f"{output_id}_trajectory_v2.csv"


def _extract_events(
    config: dict[str, Any],
    output_id: str,
    holding_position: str,
    trajectory_df: pd.DataFrame,
    trajectory_kind: str,
) -> list[dict[str, Any]]:
    rows = [
        _event_row(output_id, holding_position, "start", 0, 0.0, 0.0, 0.0, trajectory_kind)
    ]
    if not trajectory_df.empty:
        last = trajectory_df.iloc[-1]
        rows.append(
            _event_row(
                output_id,
                holding_position,
                "end",
                int(last["step_index"]),
                float(last["step_time"]),
                float(last["x"]),
                float(last["y"]),
                trajectory_kind,
            )
        )

    segment_path = _turn_segment_path(config, output_id, trajectory_kind)
    if segment_path.exists():
        segment_df = pd.read_csv(segment_path)
        for _, segment in segment_df.iterrows():
            if trajectory_df.empty:
                continue
            target_time = float(segment["start_time"])
            nearest_idx = int((trajectory_df["step_time"] - target_time).abs().idxmin())
            point = trajectory_df.loc[nearest_idx]
            rows.append(
                _event_row(
                    output_id,
                    holding_position,
                    "turn",
                    int(point["step_index"]),
                    float(point["step_time"]),
                    float(point["x"]),
                    float(point["y"]),
                    trajectory_kind,
                    turn_angle_deg=float(segment.get("angle_delta_deg", np.nan)),
                    turn_direction=str(segment.get("direction", "")),
                )
            )
    return rows


def _turn_segment_path(config: dict[str, Any], output_id: str, trajectory_kind: str) -> Path:
    if trajectory_kind == "raw":
        return Path(config["paths"]["processed_dir"]) / f"{output_id}_turn_segments.csv"
    v2_subdir = str(config["turn_correction_v2"]["output_subdir"])
    return Path("outputs") / v2_subdir / "processed" / f"{output_id}_turn_segments_v2.csv"


def _event_row(
    output_id: str,
    holding_position: str,
    event_type: str,
    step_index: int,
    event_time: float,
    x: float,
    y: float,
    trajectory_kind: str,
    turn_angle_deg: float | None = None,
    turn_direction: str | None = None,
) -> dict[str, Any]:
    return {
        "trial_id": output_id,
        "holding_position": holding_position,
        "trajectory_kind": trajectory_kind,
        "event_type": event_type,
        "step_index": step_index,
        "event_time": event_time,
        "x": x,
        "y": y,
        "turn_angle_deg": turn_angle_deg,
        "turn_direction": turn_direction,
    }


def _cluster_events(event_df: pd.DataFrame, eps_m: float, min_cluster_size: int) -> pd.DataFrame:
    if event_df.empty:
        return pd.DataFrame(
            columns=[
                "cluster_id",
                "event_type",
                "x",
                "y",
                "n_events",
                "n_trials",
                "mean_radius_m",
                "member_trial_ids",
            ]
        )
    clusters = []
    cluster_id = 0
    for event_type, group in event_df.groupby("event_type"):
        labels = _dbscan_points(group[["x", "y"]].to_numpy(), eps_m, min_cluster_size)
        grouped = group.copy()
        grouped["cluster_label"] = labels
        for label, members in grouped[grouped["cluster_label"] >= 0].groupby("cluster_label"):
            center = members[["x", "y"]].mean()
            distances = np.linalg.norm(members[["x", "y"]].to_numpy() - center.to_numpy(), axis=1)
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "event_type": event_type,
                    "x": center["x"],
                    "y": center["y"],
                    "n_events": len(members),
                    "n_trials": members["trial_id"].nunique(),
                    "mean_radius_m": float(distances.mean()) if len(distances) else 0.0,
                    "member_trial_ids": ",".join(sorted(members["trial_id"].unique())),
                }
            )
            cluster_id += 1
    return pd.DataFrame(clusters)


def _dbscan_points(points: np.ndarray, eps_m: float, min_cluster_size: int) -> np.ndarray:
    labels = np.full(len(points), -1, dtype=int)
    visited = np.zeros(len(points), dtype=bool)
    cluster_id = 0
    for idx in range(len(points)):
        if visited[idx]:
            continue
        visited[idx] = True
        neighbors = _neighbors(points, idx, eps_m)
        if len(neighbors) < min_cluster_size:
            continue
        labels[idx] = cluster_id
        seeds = list(neighbors)
        while seeds:
            current = seeds.pop()
            if not visited[current]:
                visited[current] = True
                current_neighbors = _neighbors(points, current, eps_m)
                if len(current_neighbors) >= min_cluster_size:
                    for neighbor in current_neighbors:
                        if neighbor not in seeds:
                            seeds.append(neighbor)
            if labels[current] == -1:
                labels[current] = cluster_id
        cluster_id += 1
    return labels


def _neighbors(points: np.ndarray, idx: int, eps_m: float) -> list[int]:
    distances = np.linalg.norm(points - points[idx], axis=1)
    return [int(i) for i in np.where(distances <= eps_m)[0]]
