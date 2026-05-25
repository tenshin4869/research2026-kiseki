from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdr_visualizer.config import load_config
from pdr_visualizer.smartpdr_overlay import plot_smartpdr_trials


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot SmartPDR overlay trajectories.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--holding-position", choices=["hand", "pocket"])
    group.add_argument("--compare", nargs=2, choices=["hand", "pocket"])
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    output_path = plot_smartpdr_trials(
        config,
        holding_position=args.holding_position,
        compare=tuple(args.compare) if args.compare else None,
    )
    print(f"overlay: {output_path}")


if __name__ == "__main__":
    main()
