# Simple PDR Trajectory Visualizer: Implementation Status

## Purpose

This project visualizes 2D walking trajectories from phyphox iPhone inertial logs.
The current goal is to compare whether hand-held and pocket-held smartphone data
can produce stable relative walking trajectories before moving toward restaurant
seat-structure estimation.

The implementation intentionally stays lightweight. It does not load a ground
truth floor map, perform seat detection, classify seat types, estimate occupancy,
or run in real time.

## Current Data Layout

Raw phyphox exports are expected under:

```text
data/raw/{holding_position}/{trial_id}/
  Accelerometer.csv
  Gyroscope.csv
  Gravity.csv
  Orientation.csv
  Magnetometer.csv
  ...
```

Currently supported `holding_position` values:

```text
hand
pocket
```

`metadata.json` is optional. If it is missing, the tool infers `hand` or
`pocket` from the parent directory. Metadata may still be used to override
values such as `trial_id`, `step_length_m`, `gyro_axis`, or `gyro_sign`.

## Implemented Pipeline

The basic PDR pipeline is:

```text
Accelerometer.csv / Gyroscope.csv / Gravity.csv
↓
normalize column names
↓
normalize timestamps to start at 0 seconds
↓
compute acceleration norm
↓
smooth acceleration norm by moving average
↓
detect walking peaks with scipy.signal.find_peaks
↓
estimate heading from gyroscope
↓
update 2D position using fixed step length
↓
export CSV and PNG outputs
```

### Step Detection

Acceleration norm is computed as:

```text
acc_norm = sqrt(acc_x^2 + acc_y^2 + acc_z^2)
```

Then a moving average is applied. Peaks are detected with:

```text
scipy.signal.find_peaks
```

Main parameters in `config.yaml`:

```yaml
preprocessing:
  acc_smoothing_window: 10

step_detection:
  height: 12.0
  distance_s: 0.35
  prominence: 0.4
```

### Heading Estimation

The current default heading source is:

```yaml
heading:
  gyro_axis: "vertical"
  gyro_sign: -1.0
```

`vertical` means the 3-axis gyroscope vector is projected onto the gravity
direction from `Gravity.csv`. This is more robust than using only `gyro_z`,
because the phone may be tilted or held differently.

The first 2 seconds are used for initial gyro bias correction:

```yaml
heading:
  use_bias_correction: true
  bias_static_duration_s: 2.0
```

Important limitation: this still estimates the smartphone's rotational behavior,
not the true pedestrian heading. If the phone rotates relative to the body,
especially in a pocket, heading errors can remain.

### Trajectory Update

For each detected step, the position is updated by:

```text
x += step_length_m * sin(heading)
y += step_length_m * cos(heading)
```

Default step length:

```yaml
pdr:
  step_length_m: 0.65
```

This is a fixed-step-length model. It does not estimate step length dynamically.

## Outputs

For one trial, the raw PDR outputs are:

```text
outputs/processed/{output_id}_steps.csv
outputs/processed/{output_id}_heading.csv
outputs/processed/{output_id}_trajectory.csv

outputs/figures/{output_id}_acc_norm.png
outputs/figures/{output_id}_heading.png
outputs/figures/{output_id}_trajectory.png
```

`output_id` includes the holding position when data is stored under
`data/raw/hand/...` or `data/raw/pocket/...`, for example:

```text
hand_001_walk
pocket_002_turnright
```

## Implemented Correction Methods

### Raw PDR

Raw PDR continuously integrates the gyroscope-derived angular velocity. This
preserves arbitrary turn angles, but small gyro bias and noise accumulate as
heading drift. As a result, straight walking segments may appear diagonal or
curved.

Raw overlay command:

```bash
python3 scripts/plot_trials.py --holding-position hand --trajectory-kind raw --config config.yaml
```

### Turn Correction v1

Turn correction v1 detects turning intervals using a single angular-velocity
threshold.

```yaml
turn_correction:
  enabled: true
  angular_velocity_threshold_rad_s: 0.25
  min_turn_duration_s: 0.25
  min_turn_angle_deg: 10.0
  merge_gap_s: 0.20
```

Behavior:

```text
turning interval:
  integrate gyro rate

straight interval:
  hold heading fixed
```

This reduces straight-line drift without snapping turn angles to 90 degrees.
However, if the beginning or end of a turn has angular velocity below the
threshold, the turn angle may be underestimated.

Outputs:

```text
outputs/processed/{output_id}_heading_corrected.csv
outputs/processed/{output_id}_trajectory_corrected.csv
outputs/processed/{output_id}_turn_segments.csv
outputs/figures/{output_id}_heading_corrected.png
outputs/figures/{output_id}_trajectory_corrected.png
outputs/figures/{output_id}_trajectory_comparison.png
```

### Turn Correction v2

Turn correction v2 is an experimental correction that improves turn interval
detection while keeping results in a separate folder.

```yaml
turn_correction_v2:
  enabled: true
  output_subdir: "turn_correction_v2"
  start_threshold_rad_s: 0.25
  end_threshold_rad_s: 0.10
  pre_turn_margin_s: 0.30
  post_turn_margin_s: 0.30
  min_turn_duration_s: 0.25
  min_turn_angle_deg: 20.0
  merge_gap_s: 0.20
  update_bias_from_straight: false
```

Added ideas:

```text
hysteresis:
  use a higher threshold to start a turn and a lower threshold to end it

pre/post turn margins:
  include the beginning and ending tail of a turn

minimum turn angle:
  ignore small hand/pocket rotations that are unlikely to be route-level turns

straight bias update:
  implemented, but disabled by default because it was too aggressive in current data
```

v2 does not snap angles to 90 degrees. For example, if the integrated turn is
93.8 degrees, it remains 93.8 degrees.

v2 outputs are separated under:

```text
outputs/turn_correction_v2/processed/
outputs/turn_correction_v2/figures/
```

Example outputs:

```text
outputs/turn_correction_v2/processed/{output_id}_heading_v2.csv
outputs/turn_correction_v2/processed/{output_id}_trajectory_v2.csv
outputs/turn_correction_v2/processed/{output_id}_turn_segments_v2.csv
outputs/turn_correction_v2/figures/{output_id}_trajectory_v2_comparison.png
```

## Commands

Process one hand trial:

```bash
python3 scripts/run_trial.py --trial-id 001_walk --holding-position hand --config config.yaml
```

Process one pocket trial:

```bash
python3 scripts/run_trial.py --trial-id 001_walk --holding-position pocket --config config.yaml
```

Overlay hand trials with the default corrected trajectory:

```bash
python3 scripts/plot_trials.py --holding-position hand --config config.yaml
```

Overlay pocket trials with the default corrected trajectory:

```bash
python3 scripts/plot_trials.py --holding-position pocket --config config.yaml
```

Overlay raw trajectories:

```bash
python3 scripts/plot_trials.py --holding-position hand --trajectory-kind raw --config config.yaml
```

Overlay v2 trajectories:

```bash
python3 scripts/plot_trials.py --holding-position hand --trajectory-kind v2 --config config.yaml
python3 scripts/plot_trials.py --holding-position pocket --trajectory-kind v2 --config config.yaml
```

Compare hand and pocket:

```bash
python3 scripts/plot_trials.py --compare hand pocket --trajectory-kind v2 --config config.yaml
```

## Current Observations

1. Fixed step length strongly affects scale.
   For example, 10 detected steps with `step_length_m = 0.3` produces about 3 m,
   while `step_length_m = 0.65` produces about 6.5 m.

2. Gravity-projected gyro is better than raw `gyro_z`.
   It reduces dependency on phone tilt and screen orientation, but it still does
   not fully solve phone/body misalignment.

3. Turn correction reduces straight-segment drift.
   Holding heading fixed during straight segments can make trajectories more
   natural, especially after a turn.

4. Turn angle estimation remains difficult.
   Even with v2, a real 90 degree turn may appear as 80, 94, or 105 degrees,
   depending on thresholding, phone motion, and gyro bias.

5. Pocket data is harder than hand-held data.
   The phone may rotate inside the pocket or be inserted with a different
   orientation. Some pocket trials show the opposite turn sign, suggesting that
   per-condition or per-trial sign/orientation handling is still needed.

## Known Limitations

The current implementation does not yet include:

```text
dynamic step length estimation
map matching
particle filtering
Kalman filtering
magnetometer / Orientation.csv fusion
automatic phone pose classification
automatic gyro sign inference
stop detection
seat detection
restaurant floor map alignment
real-time processing
web application UI
```

## Next Candidates

Useful next steps:

1. Add per-position or per-trial heading sign handling.
   Pocket trials may need different `gyro_sign` depending on phone insertion
   direction.

2. Compare gyroscope heading with `Orientation.csv` yaw.
   This can help identify whether gyro integration or phone/body misalignment is
   the larger problem.

3. Add a calibration trial.
   A known straight walk and a known right turn can estimate step length and
   heading sign before analyzing unknown trials.

4. Add optional magnetometer/orientation complementary correction.
   This may reduce long-term drift, but must be used carefully indoors because
   magnetic interference is common.

5. Add a map or route constraint only after raw PDR behavior is understood.
   Map matching is powerful, but it can hide sensor problems if introduced too
   early.

## ver2.0 Direction: Self-Anchored Trajectory Alignment

The ver2.0 branch introduces the first step toward:

```text
Self-Anchored Trajectory Alignment for Map-Free PDR
```

The goal is not to force one trajectory to look correct. Instead, it extracts
common event points from multiple trajectories and clusters them into
self-generated anchor candidates.

This is intended to support two parallel analyses:

```text
raw trajectories:
  no single-trajectory PDR correction

v2 trajectories:
  with turn-correction v2 applied before self-alignment
```

The first implemented version extracts:

```text
start events
turn events
end events
```

and clusters nearby points using a simple distance-based DBSCAN-style method.
The outputs are:

```text
outputs/self_alignment/raw/processed/
outputs/self_alignment/raw/figures/
outputs/self_alignment/v2/processed/
outputs/self_alignment/v2/figures/
```

Example commands:

```bash
python3 scripts/self_align_trials.py --holding-position hand --trajectory-kind raw --config config.yaml
python3 scripts/self_align_trials.py --holding-position hand --trajectory-kind v2 --config config.yaml
python3 scripts/self_align_trials.py --holding-position pocket --trajectory-kind raw --config config.yaml
python3 scripts/self_align_trials.py --holding-position pocket --trajectory-kind v2 --config config.yaml
```

This is not yet full trajectory optimization. It is the visibility layer for
checking whether repeated trajectories produce stable anchor candidates. Once
anchor candidates are meaningful, the next step is to optimize per-trajectory
parameters such as:

```text
heading_offset
step_scale
turn_gain
```

so that event points align better across trajectories.
