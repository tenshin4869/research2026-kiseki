from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdr_visualizer.config import load_config
from pdr_visualizer.self_alignment import run_self_alignment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract self-generated anchor candidates from multiple PDR trajectories."
    )
    parser.add_argument("--holding-position", choices=["hand", "pocket"])
    parser.add_argument("--trajectory-kind", choices=["raw", "v2"], required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    try:
        outputs = run_self_alignment(
            config,
            holding_position=args.holding_position,
            trajectory_kind=args.trajectory_kind,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}") from exc
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
