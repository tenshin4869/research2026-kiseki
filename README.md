# research2026-kiseki ver3.0

phyphoxで取得したiPhoneの加速度・ジャイロCSVから、簡易PDRで2D歩行軌跡を可視化する最小構成のブランチです。

この `ver3.0` ブランチでは、最初のシンプルな軌跡可視化プログラムだけを残しています。曲がり補正、自己アンカー、map matching、Orientation融合などの高度な補正は含めていません。

## セットアップ

```bash
python3 -m pip install -r requirements.txt
```

## 入力データ配置

phyphoxの出力CSVを以下のように配置します。

```text
data/raw/hand/001_walk/
  Accelerometer.csv
  Gyroscope.csv

data/raw/pocket/001_walk/
  Accelerometer.csv
  Gyroscope.csv
```

`metadata.json` は任意です。無い場合は、親フォルダ名から `hand` / `pocket` を自動判定します。

## 1試行を処理する

```bash
python3 scripts/run_trial.py --trial-id 001_walk --holding-position hand --config config.yaml
```

出力は試行ごとのフォルダにまとまります。

```text
outputs/hand_001_walk/
  processed/
    steps.csv
    heading.csv
    trajectory.csv
  figures/
    acc_norm.png
    heading.png
    trajectory.png
```

## 複数試行を重ね合わせる

handの全試行:

```bash
python3 scripts/plot_trials.py --holding-position hand --config config.yaml
```

pocketの全試行:

```bash
python3 scripts/plot_trials.py --holding-position pocket --config config.yaml
```

handとpocketの比較:

```bash
python3 scripts/plot_trials.py --compare hand pocket --config config.yaml
```

重ね合わせ図は以下に出力されます。

```text
outputs/overlays/hand/trajectory_overlay.png
outputs/overlays/pocket/trajectory_overlay.png
outputs/overlays/hand_vs_pocket/trajectory_overlay.png
```

## このブランチで行う処理

```text
Accelerometer.csvを読み込む
Gyroscope.csvを読み込む
時刻を0秒始まりにする
加速度ノルムを計算する
移動平均で平滑化する
scipy.signal.find_peaksで歩行ピークを検出する
指定ジャイロ軸を積分してheadingを推定する
固定歩幅で2D座標を更新する
1試行と複数試行の軌跡を可視化する
```

## このブランチで行わないこと

```text
曲がり区間検出
直進区間のheading固定
turn correction
turn correction v2
Gravity.csvを使った鉛直ジャイロ投影
Orientation.csv融合
自己アンカー
map matching
Kalman filter / particle filter
停止検出
着席検出
座席推定
```

このブランチは、後続の補正手法と比較するための素のPDRベースラインとして使います。
