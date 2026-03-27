import glob
import logging
import os
import pathlib
import tempfile
import time
import zipfile

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


def scan_flp_from_zip(zip_path: str, flp_name: str) -> list[str]:
    """Extract an FLP from a zip archive and return its sample paths."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(flp_name) as flp_data:
                with tempfile.NamedTemporaryFile(suffix=".flp", delete=False) as tmp:
                    tmp.write(flp_data.read())
                    tmp_path = tmp.name
        try:
            return scan_flp(tmp_path)
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning("Failed to read %s from %s: %s", flp_name, zip_path, e)
        return []


def _list_flps_in_zip(zip_path: str) -> list[str]:
    """Return names of .flp files inside a zip archive."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return [n for n in zf.namelist() if n.lower().endswith(".flp")]
    except Exception as e:
        logger.warning("Failed to open zip %s: %s", zip_path, e)
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

    # Collect all .flp and .zip files, skipping Backup subfolders
    flp_files = []
    zip_files = []
    for root, dirs, files in os.walk(flp_directory):
        dirs[:] = [d for d in dirs if d.lower() != "backup"]
        for f in files:
            if f.lower().endswith(".flp"):
                flp_files.append(os.path.join(root, f))
            elif f.lower().endswith(".zip"):
                zip_files.append(os.path.join(root, f))

    # Expand zips: find .flp files inside each zip
    zip_entries = []  # list of (zip_path, flp_name_inside_zip)
    for zf in zip_files:
        for flp_name in _list_flps_in_zip(zf):
            zip_entries.append((zf, flp_name))

    total = len(flp_files) + len(zip_entries)
    if total == 0:
        print("No .flp files found in", flp_directory)
        return stats

    zip_msg = f" + {len(zip_entries)} in {len(zip_files)} zip(s)" if zip_entries else ""
    print(f"Found {len(flp_files)} FLP files{zip_msg}. Scanning...")

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

    # Scan .flp files inside .zip archives
    for j, (zip_path, flp_name) in enumerate(zip_entries):
        idx = len(flp_files) + j + 1
        display_name = f"{os.path.basename(zip_path)}:{flp_name}"
        print(f"  [{idx}/{total}] {display_name}", end="\r")

        # Use zip path + internal name as the identifier
        virtual_path = normalize_path(zip_path) + "::" + flp_name

        try:
            mtime = os.path.getmtime(zip_path)
        except OSError as e:
            logger.warning("Cannot access %s: %s", zip_path, e)
            stats["errors"] += 1
            continue

        # Incremental scan: skip if zip mtime unchanged
        prev_mtime = db.get_scan_mtime(conn, virtual_path)
        if prev_mtime is not None and prev_mtime == mtime:
            stats["skipped"] += 1
            continue

        samples = scan_flp_from_zip(zip_path, flp_name)

        db.clear_samples_for_flp(conn, virtual_path)

        for sample in samples:
            sample = resolve_fl_path(sample)

            if not os.path.isabs(sample):
                sample = str(pathlib.Path(zip_path).parent / sample)

            matched_dir = _find_matching_kit_dir(sample, drum_kits_dirs)
            if matched_dir is None:
                continue

            if not os.path.exists(sample):
                logger.info("Broken reference in %s: %s", virtual_path, sample)
                stats["broken_refs"] += 1

            kit = extract_kit_folder(sample, matched_dir)
            db.insert_sample(conn, normalize_path(sample), kit, virtual_path)

        db.upsert_scan(conn, virtual_path, mtime, time.time())
        stats["scanned"] += 1
        batch_count += 1

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
