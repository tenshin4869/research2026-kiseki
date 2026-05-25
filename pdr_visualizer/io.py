from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ACC_COLUMNS = {
    "Time (s)": "t",
    "X (m/s^2)": "acc_x",
    "Y (m/s^2)": "acc_y",
    "Z (m/s^2)": "acc_z",
}

GYRO_COLUMNS = {
    "Time (s)": "t",
    "X (rad/s)": "gyro_x",
    "Y (rad/s)": "gyro_y",
    "Z (rad/s)": "gyro_z",
}

MAG_COLUMNS = {
    "Time (s)": "t",
    "X (µT)": "mag_x",
    "Y (µT)": "mag_y",
    "Z (µT)": "mag_z",
}

GRAVITY_COLUMNS = {
    "Time (s)": "t",
    "Gravity X (m/s^2)": "gravity_x",
    "Gravity Y (m/s^2)": "gravity_y",
    "Gravity Z (m/s^2)": "gravity_z",
}


def read_accelerometer_csv(path: str | Path) -> pd.DataFrame:
    return _read_phyphox_csv(path, ACC_COLUMNS, "accelerometer")


def read_gyroscope_csv(path: str | Path) -> pd.DataFrame:
    return _read_phyphox_csv(path, GYRO_COLUMNS, "gyroscope")


def read_magnetometer_csv(path: str | Path) -> pd.DataFrame:
    return _read_phyphox_csv(path, MAG_COLUMNS, "magnetometer")


def read_gravity_csv(path: str | Path) -> pd.DataFrame:
    return _read_phyphox_csv(path, GRAVITY_COLUMNS, "gravity")


def read_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"metadata.json not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    if not isinstance(metadata, dict):
        raise ValueError(f"metadata.json must contain a JSON object: {path}")
    return metadata


def read_metadata_or_default(path: str | Path, trial_id: str) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        return read_metadata(path)
    holding_position = infer_holding_position(path.parent)
    return {
        "trial_id": trial_id,
        "holding_position": holding_position or "unknown",
        "route": "",
        "device": "",
        "notes": "metadata.json was not found; default metadata was used.",
    }


def infer_holding_position(path: str | Path) -> str | None:
    for part in Path(path).parts:
        if part in {"hand", "pocket"}:
            return part
    return None


def output_trial_id(raw_data_dir: str | Path, trial_path: str | Path, metadata: dict[str, Any]) -> str:
    trial_path = Path(trial_path)
    raw_data_dir = Path(raw_data_dir)
    if metadata.get("trial_id") and metadata.get("trial_id") != trial_path.name:
        return str(metadata["trial_id"])
    holding_position = str(metadata.get("holding_position") or "")
    if holding_position in {"hand", "pocket"}:
        return f"{holding_position}_{trial_path.name}"
    try:
        relative = trial_path.relative_to(raw_data_dir)
        if len(relative.parts) > 1:
            return "_".join(relative.parts)
    except ValueError:
        pass
    return trial_path.name


def find_trial_dirs(raw_data_dir: str | Path) -> list[Path]:
    raw_data_dir = Path(raw_data_dir)
    if not raw_data_dir.exists():
        return []
    return sorted(
        path
        for path in raw_data_dir.rglob("*")
        if path.is_dir()
        and (path / "Accelerometer.csv").exists()
        and (path / "Gyroscope.csv").exists()
    )


def resolve_trial_dir(
    raw_data_dir: str | Path,
    trial_id: str,
    holding_position: str | None = None,
) -> Path:
    raw_data_dir = Path(raw_data_dir)
    direct = raw_data_dir / trial_id
    if direct.exists():
        return direct

    if holding_position:
        positioned = raw_data_dir / holding_position / trial_id
        if positioned.exists():
            return positioned

    matches = [
        path
        for path in find_trial_dirs(raw_data_dir)
        if path.name == trial_id
        and (holding_position is None or infer_holding_position(path) == holding_position)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        options = ", ".join(str(path) for path in matches)
        raise ValueError(
            f"Multiple trials named {trial_id!r} found. "
            f"Pass --holding-position hand/pocket. Matches: {options}"
        )
    raise FileNotFoundError(
        f"Trial {trial_id!r} not found under {raw_data_dir}. "
        "Expected data/raw/{trial_id} or data/raw/{hand|pocket}/{trial_id}."
    )


def _read_phyphox_csv(
    path: str | Path, column_map: dict[str, str], sensor_name: str
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{sensor_name} CSV not found: {path}")

    df = pd.read_csv(path)
    missing = [col for col in column_map if col not in df.columns]
    if missing:
        expected = ", ".join(column_map)
        actual = ", ".join(str(col) for col in df.columns)
        raise ValueError(
            f"Unexpected {sensor_name} CSV columns in {path}. "
            f"Missing: {missing}. Expected columns: {expected}. Actual columns: {actual}"
        )

    df = df.rename(columns=column_map)[list(column_map.values())].copy()
    df = df.apply(pd.to_numeric, errors="raise")
    df["t"] = df["t"] - df["t"].iloc[0]
    return df
