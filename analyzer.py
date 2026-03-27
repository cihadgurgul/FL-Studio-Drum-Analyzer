import datetime
import os
import time

from tabulate import tabulate

import db


def show_top_samples(limit: int | None = 10) -> None:
    conn = db.get_connection()
    rows = db.get_top_samples(conn, limit)
    conn.close()

    if not rows:
        print("No sample data found. Run 'scan' first.")
        return

    data = []
    for i, (sample_path, count) in enumerate(rows, 1):
        # Show kit/filename for readability
        parts = sample_path.replace("\\", "/").split("/")
        short = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        data.append([i, short, count])

    print("\nTop Samples by Project Count:")
    print(tabulate(data, headers=["#", "Sample", "Projects"], tablefmt="simple"))
    print()


def show_top_kits(limit: int | None = 10) -> None:
    conn = db.get_connection()
    rows = db.get_top_kits(conn, limit)
    conn.close()

    if not rows:
        print("No kit data found. Run 'scan' first.")
        return

    data = []
    for i, (kit, count) in enumerate(rows, 1):
        data.append([i, kit, count])

    print("\nTop Kits by Project Count:")
    print(tabulate(data, headers=["#", "Kit", "Projects"], tablefmt="simple"))
    print()


def show_kit_timeline() -> None:
    conn = db.get_connection()
    rows = db.get_kit_timeline(conn)
    conn.close()

    if not rows:
        print("No kit data found. Run 'scan' first.")
        return

    data = []
    for kit, last_used_epoch in rows:
        date_str = datetime.datetime.fromtimestamp(last_used_epoch).strftime("%Y-%m-%d")
        data.append([kit, date_str])

    print("\nKit Timeline (oldest first):")
    print(tabulate(data, headers=["Kit", "Last Used"], tablefmt="simple"))
    print()


def show_unused_kits(config: dict) -> list[str]:
    """Show unused kits and return list of kit folder names for cleanup."""
    drum_kits_dirs = config["drum_kits_directories"]
    unused_dir = os.path.normpath(config["unused_directory"])
    cutoff = time.time() - config["unused_threshold_days"] * 86400

    conn = db.get_connection()
    stale_rows = db.get_unused_kits(conn, cutoff)
    known_kits = db.get_all_known_kits(conn)
    conn.close()

    # Find kits on disk that were never referenced
    never_used = []
    for drum_kits_dir in drum_kits_dirs:
        if not os.path.isdir(drum_kits_dir):
            continue
        for entry in os.listdir(drum_kits_dir):
            entry_path = os.path.normpath(os.path.join(drum_kits_dir, entry))
            if not os.path.isdir(entry_path):
                continue
            # Exclude the unused/archive directory itself
            if entry_path == unused_dir:
                continue
            if entry not in known_kits:
                never_used.append(entry)

    # Build output
    data = []
    unused_kit_names = []

    for kit, last_used_epoch in stale_rows:
        date_str = datetime.datetime.fromtimestamp(last_used_epoch).strftime("%Y-%m-%d")
        data.append([kit, date_str, "Stale"])
        unused_kit_names.append(kit)

    for kit in sorted(never_used):
        data.append([kit, "—", "Never used"])
        unused_kit_names.append(kit)

    if not data:
        print(f"\nNo unused kits found (threshold: {config['unused_threshold_days']} days).")
        return []

    print(f"\nUnused Kits (threshold: {config['unused_threshold_days']} days):")
    print(tabulate(data, headers=["Kit", "Last Used", "Status"], tablefmt="simple"))
    print(f"\n{len(unused_kit_names)} kit(s) eligible for archival.")
    return unused_kit_names
