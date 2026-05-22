# research2026-kiseki

Simple PDR Trajectory Visualizer for phyphox iPhone inertial sensor logs.

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
  Gravity.csv

data/raw/pocket/001_walk/
  Accelerometer.csv
  Gyroscope.csv
  Gravity.csv
```

`metadata.json` is optional. When omitted, `hand` or `pocket` is inferred from the parent folder.

## Run

Process one trial:

```bash
python3 scripts/run_trial.py --trial-id 001_walk --holding-position hand --config config.yaml
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
