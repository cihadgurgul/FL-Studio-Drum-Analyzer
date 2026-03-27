import argparse
import json
import os
import sys

# Fix Unicode output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import analyzer
import cleanup
import scanner

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

REQUIRED_KEYS = ["flp_directory", "drum_kits_directories", "unused_directory", "unused_threshold_days"]

CONFIG_TEMPLATE = """\
{
    "flp_directory": "C:/Users/YourName/Documents/Image-Line/FL Studio/Projects",
    "drum_kits_directories": [
        "C:/Users/YourName/Drum Kits"
    ],
    "unused_directory": "C:/Users/YourName/Drum Kits/_unused",
    "unused_threshold_days": 90
}

See config.example.json for a full example."""


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: config.json not found at {CONFIG_PATH}")
        print(f"\nCreate one with the following format:\n{CONFIG_TEMPLATE}")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        print(f"Error: config.json is missing keys: {', '.join(missing)}")
        sys.exit(1)

    if not os.path.isdir(config["flp_directory"]):
        print(f"Warning: flp_directory does not exist: {config['flp_directory']}")

    for d in config["drum_kits_directories"]:
        if not os.path.isdir(d):
            print(f"Warning: drum_kits_directory does not exist: {d}")

    return config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fl-drum-analyzer",
        description="Analyze drum sample usage across FL Studio projects",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan", help="Scan FLP files and update database")

    stats_parser = subparsers.add_parser("stats", help="Show sample usage rankings")
    stats_parser.add_argument("--top", type=int, default=10, help="Number of results (default: 10)")
    stats_parser.add_argument("--all", action="store_true", help="Show all samples")

    kits_parser = subparsers.add_parser("kits", help="Show kit-level usage summary")
    kits_parser.add_argument("--all", action="store_true", help="Show all kits")

    subparsers.add_parser("unused", help="List kits eligible for archival")

    cleanup_parser = subparsers.add_parser("cleanup", help="Move unused kits to archive")
    cleanup_parser.add_argument("--confirm", action="store_true", help="Actually move files (default is dry-run)")

    subparsers.add_parser("undo", help="Reverse last cleanup operation")

    args = parser.parse_args()
    config = load_config()

    if args.command == "scan":
        scanner.scan_all(config)
    elif args.command == "stats":
        analyzer.show_top_samples(limit=None if args.all else args.top)
    elif args.command == "kits":
        analyzer.show_top_kits(limit=None if args.all else 10)
    elif args.command == "unused":
        analyzer.show_unused_kits(config)
    elif args.command == "cleanup":
        unused = analyzer.show_unused_kits(config)
        if unused:
            print()  # Separator between list and cleanup output
            cleanup.cleanup(unused, config, dry_run=not args.confirm)
    elif args.command == "undo":
        cleanup.undo()


if __name__ == "__main__":
    main()
