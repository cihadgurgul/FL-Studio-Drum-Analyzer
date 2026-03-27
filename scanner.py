import glob
import logging
import os
import pathlib
import time

import pyflp

import db

logger = logging.getLogger("scanner")


def _detect_fl_studio_install() -> str | None:
    """Auto-detect FL Studio install folder. Returns None if not found."""
    il_dir = os.path.join(os.environ.get("ProgramFiles", "C:/Program Files"), "Image-Line")
    if not os.path.isdir(il_dir):
        return None
    matches = sorted(glob.glob(os.path.join(il_dir, "FL Studio*")), reverse=True)
    # Filter to actual FL Studio installs (have a Data/Patches folder), pick newest by mtime
    installs = [m for m in matches if os.path.isdir(os.path.join(m, "Data", "Patches"))]
    if installs:
        newest = max(installs, key=lambda p: os.path.getmtime(p))
        return newest.replace("\\", "/")
    return None


def _get_fl_path_vars() -> dict[str, str]:
    """Build FL Studio path variable mapping, lazily detecting the install."""
    fl_vars = {}
    fl_install = _detect_fl_studio_install()
    if fl_install:
        fl_vars["%FLStudioFactoryData%"] = fl_install
    user_data = os.path.expanduser("~/Documents/Image-Line/FL Studio")
    if os.path.isdir(user_data):
        fl_vars["%FLStudioUserData%"] = user_data
    return fl_vars


def resolve_fl_path(p: str) -> str:
    """Resolve FL Studio path variables like %FLStudioFactoryData%."""
    for var, real_path in _get_fl_path_vars().items():
        if p.startswith(var):
            p = real_path + p[len(var):]
            break
    return p


def normalize_path(p: str) -> str:
    return os.path.normpath(resolve_fl_path(p))


def is_under_drum_kits(sample_path: str, drum_kits_dir: str) -> bool:
    sample = normalize_path(sample_path)
    kits = normalize_path(drum_kits_dir)
    if os.name == "nt":
        sample = sample.lower()
        kits = kits.lower()
    return sample.startswith(kits + os.sep) or sample == kits


def extract_kit_folder(sample_path: str, drum_kits_dir: str) -> str:
    rel = os.path.relpath(normalize_path(sample_path), normalize_path(drum_kits_dir))
    return rel.split(os.sep)[0]


def scan_flp(flp_path: str) -> list[str]:
    """Parse a single FLP file and return sample paths from channel rack samplers."""
    try:
        project = pyflp.parse(flp_path)
        samples = []
        for sampler in project.channels.samplers:
            if sampler.sample_path is not None:
                samples.append(str(sampler.sample_path))
        return samples
    except Exception as e:
        logger.warning("Failed to parse %s: %s", flp_path, e)
        return []


def _find_matching_kit_dir(sample_path: str, drum_kits_dirs: list[str]) -> str | None:
    """Return the drum kits directory that contains this sample, or None."""
    for d in drum_kits_dirs:
        if is_under_drum_kits(sample_path, d):
            return d
    return None


def scan_all(config: dict) -> dict:
    """Scan all FLP files in the configured directory and update the database."""
    flp_directory = config["flp_directory"]
    drum_kits_dirs = config["drum_kits_directories"]

    stats = {"scanned": 0, "skipped": 0, "errors": 0, "broken_refs": 0}

    # Collect all .flp files, skipping Backup subfolders
    flp_files = []
    for root, dirs, files in os.walk(flp_directory):
        dirs[:] = [d for d in dirs if d.lower() != "backup"]
        for f in files:
            if f.lower().endswith(".flp"):
                flp_files.append(os.path.join(root, f))

    total = len(flp_files)
    if total == 0:
        print("No .flp files found in", flp_directory)
        return stats

    print(f"Found {total} FLP files. Scanning...")

    conn = db.get_connection()
    batch_count = 0

    for i, flp_file in enumerate(flp_files):
        flp_path = normalize_path(flp_file)
        print(f"  [{i + 1}/{total}] {os.path.basename(flp_path)}", end="\r")

        # Get file modification time
        try:
            mtime = os.path.getmtime(flp_path)
        except OSError as e:
            logger.warning("Cannot access %s: %s", flp_path, e)
            stats["errors"] += 1
            continue

        # Incremental scan: skip if mtime unchanged
        prev_mtime = db.get_scan_mtime(conn, flp_path)
        if prev_mtime is not None and prev_mtime == mtime:
            stats["skipped"] += 1
            continue

        # Parse the FLP
        samples = scan_flp(flp_path)

        # Clear old entries for this FLP and re-insert
        db.clear_samples_for_flp(conn, flp_path)

        for sample in samples:
            # Resolve FL Studio path variables first
            sample = resolve_fl_path(sample)

            # Resolve relative paths against FLP directory
            if not os.path.isabs(sample):
                sample = str(pathlib.Path(flp_path).parent / sample)

            matched_dir = _find_matching_kit_dir(sample, drum_kits_dirs)
            if matched_dir is None:
                continue

            # Check for broken references
            if not os.path.exists(sample):
                logger.info("Broken reference in %s: %s", flp_path, sample)
                stats["broken_refs"] += 1

            kit = extract_kit_folder(sample, matched_dir)
            db.insert_sample(conn, normalize_path(sample), kit, flp_path)

        db.upsert_scan(conn, flp_path, mtime, time.time())
        stats["scanned"] += 1
        batch_count += 1

        # Commit every 50 FLPs
        if batch_count >= 50:
            conn.commit()
            batch_count = 0

    conn.commit()
    conn.close()

    print()  # Clear the \r line
    print(
        f"Done. Scanned {stats['scanned']}, skipped {stats['skipped']} unchanged, "
        f"{stats['errors']} errors, {stats['broken_refs']} broken references."
    )
    return stats
