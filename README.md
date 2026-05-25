# research2026-kiseki ver3.0

Minimal Simple PDR Trajectory Visualizer for phyphox iPhone inertial sensor logs.

This branch intentionally keeps only the first, simple trajectory visualization
program. It does not include turn correction, self-alignment, map matching, or
other advanced correction methods.

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Data Layout

Place phyphox exports under `data/raw/{holding_position}/{trial_id}/`.

```text
data/raw/hand/001_walk/
  Accelerometer.csv
  Gyroscope.csv

data/raw/pocket/001_walk/
  Accelerometer.csv
  Gyroscope.csv
```

`metadata.json` is optional. When omitted, `hand` or `pocket` is inferred from the parent folder.

## Run

Process one trial:

```bash
python3 scripts/run_trial.py --trial-id 001_walk --holding-position hand --config config.yaml
```

This writes simple raw PDR outputs:

```text
outputs/processed/hand_001_walk_steps.csv
outputs/processed/hand_001_walk_heading.csv
outputs/processed/hand_001_walk_trajectory.csv
outputs/figures/hand_001_walk_acc_norm.png
outputs/figures/hand_001_walk_heading.png
outputs/figures/hand_001_walk_trajectory.png
```

Overlay all hand trials:

```bash
python3 scripts/plot_trials.py --holding-position hand --config config.yaml
```

Overlay all pocket trials:

```bash
python3 scripts/plot_trials.py --holding-position pocket --config config.yaml
```

Compare hand and pocket trials:

```bash
python3 scripts/plot_trials.py --compare hand pocket --config config.yaml
```

## What This Branch Does Not Include

```text
turn correction
turn interval detection
heading drift suppression during straight walking
gravity-projected gyro heading
Orientation.csv fusion
self-anchored trajectory alignment
map matching
Kalman / particle filtering
seat or stop detection
```

The purpose of this branch is to keep a clean baseline for comparing later
correction methods against the original simple PDR behavior.
