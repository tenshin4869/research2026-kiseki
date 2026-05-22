from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "kiseki_matplotlib_cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_acc_norm(
    acc_df: pd.DataFrame,
    steps_df: pd.DataFrame,
    output_path: str | Path,
    dpi: int,
    show_grid: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(acc_df["t"], acc_df["acc_norm"], label="acc_norm", alpha=0.45)
    ax.plot(acc_df["t"], acc_df["acc_norm_smooth"], label="acc_norm_smooth")
    ax.scatter(
        steps_df["step_time"],
        steps_df["acc_norm_smooth"],
        label="detected_steps",
        color="tab:red",
        s=20,
        zorder=3,
    )
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Acceleration norm [m/s^2]")
    ax.legend()
    ax.grid(show_grid)
    _save(fig, output_path, dpi)


def plot_heading(
    heading_df: pd.DataFrame,
    gyro_axis: str,
    output_path: str | Path,
    dpi: int,
    show_grid: bool,
) -> None:
    axis_col = "gyro_vertical" if gyro_axis in {"vertical", "gravity", "auto"} else f"gyro_{gyro_axis}"
    corrected_col = f"{axis_col}_corrected"

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(heading_df["t"], heading_df[axis_col], label=axis_col, alpha=0.5)
    axes[0].plot(heading_df["t"], heading_df[corrected_col], label=corrected_col)
    axes[0].set_ylabel("Angular velocity [rad/s]")
    axes[0].legend()
    axes[0].grid(show_grid)

    axes[1].plot(heading_df["t"], heading_df["heading_rad"], label="heading_rad")
    axes[1].set_xlabel("Time [s]")
    axes[1].set_ylabel("Heading [rad]")
    axes[1].legend()
    axes[1].grid(show_grid)
    _save(fig, output_path, dpi)


def plot_trajectory(
    trajectory_df: pd.DataFrame,
    output_path: str | Path,
    title: str,
    dpi: int,
    equal_axis: bool,
    show_grid: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    _draw_trajectory(ax, trajectory_df, label=title)
    ax.set_title(title)
    _style_trajectory_axis(ax, equal_axis, show_grid)
    _save(fig, output_path, dpi)


def plot_overlay(
    trajectories: list[tuple[str, str, pd.DataFrame]],
    output_path: str | Path,
    title: str,
    dpi: int,
    equal_axis: bool,
    show_grid: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(7, 7))
    for trial_id, holding_position, trajectory_df in trajectories:
        label = f"{trial_id} ({holding_position})"
        _draw_trajectory(ax, trajectory_df, label=label, mark_end=False)
    ax.set_title(title)
    ax.legend()
    _style_trajectory_axis(ax, equal_axis, show_grid)
    _save(fig, output_path, dpi)


def _draw_trajectory(
    ax: plt.Axes,
    trajectory_df: pd.DataFrame,
    label: str,
    mark_end: bool = True,
) -> None:
    x = [0.0, *trajectory_df["x"].to_list()]
    y = [0.0, *trajectory_df["y"].to_list()]
    ax.plot(x, y, marker="o", markersize=3, linewidth=1.5, label=label)
    ax.scatter([0.0], [0.0], color="tab:green", s=45, marker="s", label="start")
    if mark_end and len(x) > 1:
        ax.scatter([x[-1]], [y[-1]], color="tab:red", s=45, marker="x", label="end")


def _style_trajectory_axis(ax: plt.Axes, equal_axis: bool, show_grid: bool) -> None:
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    if equal_axis:
        ax.axis("equal")
    ax.grid(show_grid)


def _save(fig: plt.Figure, output_path: str | Path, dpi: int) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
