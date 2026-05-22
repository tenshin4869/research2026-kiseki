from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdr_visualizer.config import load_config
from pdr_visualizer.overlay import plot_trials


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot overlay trajectories.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--holding-position", choices=["hand", "pocket"])
    group.add_argument("--compare", nargs=2, choices=["hand", "pocket"])
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    try:
        output_path = plot_trials(
            config,
            holding_position=args.holding_position,
            compare=tuple(args.compare) if args.compare else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(f"overlay: {output_path}")


if __name__ == "__main__":
    main()
