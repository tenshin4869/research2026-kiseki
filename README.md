# research2026-kiseki ver4.0

phyphoxで取得したiPhoneのセンサCSVから、簡易PDRとSmartPDR再現実装で2D歩行軌跡を可視化するブランチです。

`ver4.0` は `ver3.0` を土台にしています。従来の最小PDRはそのまま残し、別系統として論文 `SmartPDR: Smartphone-Based Pedestrian Dead Reckoning for Indoor Localization` の再現実装を追加しています。

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
  Magnetometer.csv
  Gravity.csv

data/raw/pocket/001_walk/
  Accelerometer.csv
  Gyroscope.csv
  Magnetometer.csv
  Gravity.csv
```

`metadata.json` は任意です。無い場合は、親フォルダ名から `hand` / `pocket` を自動判定します。

## 最小PDRで1試行を処理する

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

## SmartPDR再現で1試行を処理する

```bash
python3 scripts/run_smartpdr_trial.py --trial-id 001_walk --holding-position hand --config config.yaml
```

出力は最小PDRと分けて保存されます。

```text
outputs/smartpdr/hand_001_walk/
  processed/
    signals.csv
    steps.csv
    heading.csv
    trajectory.csv
  figures/
    acc_step.png
    heading.png
    trajectory.png
```

SmartPDRの重ね合わせ:

```bash
python3 scripts/plot_smartpdr_trials.py --holding-position hand --config config.yaml
python3 scripts/plot_smartpdr_trials.py --holding-position pocket --config config.yaml
python3 scripts/plot_smartpdr_trials.py --compare hand pocket --config config.yaml
```

## SmartPDR再現内容

論文から再現した処理は以下です。

```text
Gravity.csvを使ってスマホ座標系の加速度を鉛直方向へ射影する
鉛直加速度からHPFで重力成分を除去する
移動平均でstep accelerationを作る
ピーク条件、peak-to-peak条件、傾き条件の3条件で歩行イベントを検出する
Magnetometer.csvとGravity.csvから傾き補償付き磁気方位を計算する
ジャイロを重力方向へ射影し、bias補正後に積分する
磁気方位とジャイロ方位の差、磁気方位の変化量から4ケースで方位を選択する
連続する歩行ピーク間の谷時刻をheading取得時刻にする
peak-to-peak加速度から4乗根モデルと対数モデルを切り替えて歩幅を推定する
歩幅と方位から2D座標を更新する
```

論文に合わせた主なパラメータ:

```text
HPF alpha: 0.9
peak threshold: 0.5 m/s^2
peak-to-peak threshold: 1.0 m/s^2
heading source weights prev:mag:gyro = 2:1:2
gyro-mag correlation threshold: 5 degrees
mag variation threshold: 2 degrees
step length switch threshold: 3.230 m/s^2
4乗根モデル beta=1.479, gamma=-1.259
対数モデル beta=1.131, gamma=0.159
```

## 完全再現できていない点

以下は論文と完全一致ではなく、phyphox/iPhoneデータに合わせた近似です。

```text
論文はAndroid端末の姿勢角と回転行列を前提にしているが、本実装ではphyphoxのGravity.csvで鉛直方向へ射影している
磁気方位は論文の回転行列そのものではなく、Gravity.csvとMagnetometer.csvによる傾き補償コンパスとして計算している
磁気偏角は地域により異なるため、config.yamlのdeclination_degで設定する。初期値は0度
論文の実験は手持ち条件中心であり、ポケット条件では端末姿勢と身体方向が一致しないため精度低下が起こりうる
歩幅推定式は論文値を使っているが、iPhone/phyphoxの加速度スケールや保持方法により、config.yamlで再調整が必要になる可能性がある
```
