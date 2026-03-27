import json
import os
import shutil
import time

MOVE_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "move_log.json")


def _find_kit_src(kit_name: str, drum_kits_dirs: list[str]) -> str | None:
    """Find which drum kits directory contains this kit folder."""
    for d in drum_kits_dirs:
        path = os.path.join(d, kit_name)
        if os.path.isdir(path):
            return path
    return None


def cleanup(unused_kits: list[str], config: dict, dry_run: bool = True) -> None:
    """Move unused kit folders to the archive directory."""
    drum_kits_dirs = config["drum_kits_directories"]
    dst_base = config["unused_directory"]

    if not dry_run:
        os.makedirs(dst_base, exist_ok=True)

    log = []

    for kit_name in unused_kits:
        src = _find_kit_src(kit_name, drum_kits_dirs)

        if src is None:
            print(f"  Warning: {kit_name} not found in any drum kits directory, skipping.")
            continue

        dst = os.path.join(dst_base, kit_name)

        if os.path.exists(dst):
            print(f"  Warning: {dst} already exists, skipping to avoid overwrite.")
            continue

        if dry_run:
            print(f"  [DRY RUN] Would move: {src} -> {dst}")
        else:
            try:
                shutil.move(src, dst)
                log.append({"src": src, "dst": dst, "timestamp": time.time()})
                print(f"  Moved: {src} -> {dst}")
            except Exception as e:
                print(f"  Error moving {kit_name}: {e}")

    if not dry_run and log:
        # Append to existing log if present
        existing = []
        if os.path.exists(MOVE_LOG_PATH):
            with open(MOVE_LOG_PATH, "r") as f:
                existing = json.load(f)

        existing.extend(log)
        with open(MOVE_LOG_PATH, "w") as f:
            json.dump(existing, f, indent=2)

        print(f"\nMoved {len(log)} kit(s). Undo available via 'python main.py undo'.")

    if dry_run:
        print(f"\nDry run complete. Use --confirm to actually move {len(unused_kits)} kit(s).")


def undo() -> None:
    """Reverse the last cleanup operation using the move log."""
    if not os.path.exists(MOVE_LOG_PATH):
        print("No move log found. Nothing to undo.")
        return

    with open(MOVE_LOG_PATH, "r") as f:
        log = json.load(f)

    if not log:
        print("Move log is empty. Nothing to undo.")
        return

    # Find the last batch (entries sharing the most recent timestamp within 60s)
    last_ts = log[-1]["timestamp"]
    batch = [e for e in log if last_ts - e["timestamp"] < 60]
    remaining = [e for e in log if last_ts - e["timestamp"] >= 60]

    failed = []

    # Reverse the last batch
    for entry in reversed(batch):
        src = entry["src"]
        dst = entry["dst"]
        try:
            if not os.path.exists(dst):
                print(f"  Warning: {dst} no longer exists, cannot undo.")
                failed.append(entry)
                continue
            if os.path.exists(src):
                print(f"  Warning: {src} already exists, cannot restore.")
                failed.append(entry)
                continue
            shutil.move(dst, src)
            print(f"  Restored: {dst} -> {src}")
        except Exception as e:
            print(f"  Error restoring {dst}: {e}")
            failed.append(entry)

    kept = remaining + failed
    if kept:
        with open(MOVE_LOG_PATH, "w") as f:
            json.dump(kept, f, indent=2)
        restored = len(batch) - len(failed)
        print(f"\n{restored} kit(s) restored. {len(failed)} could not be undone." if failed
              else f"\n{restored} kit(s) restored. {len(remaining)} earlier move(s) still in log.")
    else:
        os.remove(MOVE_LOG_PATH)
        print(f"\nAll {len(batch)} kit(s) restored. Move log cleared.")
