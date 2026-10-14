"""Command-line entry point for the local driver monitor."""

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .app import run_monitor
from .config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EE6008 local camera-based facial fatigue monitor"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.yaml"),
        help="YAML configuration file (default: configs/default.yaml)",
    )
    parser.add_argument(
        "--video",
        type=Path,
        help="Read a local video instead of the configured camera",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Process without opening the preview window",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    config_path = args.config.expanduser().resolve()
    config = load_config(config_path)
    project_root = config_path.parent.parent
    run_monitor(
        config=config,
        project_root=project_root,
        video_path=args.video,
        show_window=False if args.headless else None,
    )


if __name__ == "__main__":
    main()
