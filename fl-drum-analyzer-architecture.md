# FL Studio Drum Usage Analyzer — Architecture

## Overview

CLI tool that scans FL Studio projects, identifies which drum samples you actually use, ranks them by frequency, and moves unused drum kits to an archive directory.

---

## Project Structure

```
fl-drum-analyzer/
├── config.json              # User paths + settings
├── main.py                  # CLI entry point
├── scanner.py               # FLP parsing + sample extraction
├── analyzer.py              # Usage stats + ranking logic
├── cleanup.py               # Move unused kits + undo
├── db.py                    # SQLite read/write
├── drum_usage.db            # Auto-generated SQLite database
├── requirements.txt         # Dependencies
└── README.md
```

---

## Config (config.json)

```json
{
  "flp_directory": "D:/FL Studio Projects",
  "drum_kits_directory": "D:/Drum Kits",
  "unused_directory": "D:/Drum Kits/_unused",
  "unused_threshold_days": 90
}
```

- `flp_directory` — Root folder of your FL projects (scanned recursively)
- `drum_kits_directory` — Root folder where your drum kits live
- `unused_directory` — Where unused kits get moved to
- `unused_threshold_days` — Kits not used in any FLP modified within this window get flagged

---

## Module Breakdown

### 1. main.py — CLI Entry Point

Uses `argparse` with subcommands:

```
python main.py scan            # Parse all FLPs, update the database
python main.py stats           # Print usage rankings
python main.py stats --top 20  # Top 20 most used samples
python main.py kits            # Show kit-level usage summary
python main.py unused          # List kits eligible for archival
python main.py cleanup         # Move unused kits (dry-run by default)
python main.py cleanup --confirm  # Actually move them
python main.py undo            # Restore last cleanup from move log
```

### 2. scanner.py — FLP Parsing

**Dependency:** `pyflp`

```python
import pyflp

def scan_flp(flp_path: str) -> list[str]:
    """
    Parse a single FLP file.
    Return list of sample file paths from Channel Rack samplers.
    """
    project = pyflp.parse(flp_path)
    samples = []
    for channel in project.channels:
        # Channel Rack samplers store a sample_path attribute
        if hasattr(channel, 'sample_path') and channel.sample_path:
            samples.append(str(channel.sample_path))
    return samples
```

**Key logic:**
- Walk `flp_directory` recursively for all `.flp` files
- For each FLP, extract sample paths from Channel Rack
- Filter: only keep samples whose path starts with `drum_kits_directory`
- Record the FLP's last-modified time (`os.path.getmtime`) as "last used" date
- Store results in SQLite via `db.py`

**Edge cases to handle:**
- FLP files that fail to parse (corrupted, very old format) — log warning, skip
- Samples with relative paths — resolve against FLP location or FL Studio data folder
- Duplicate FLP scans — upsert, don't double-count

### 3. db.py — SQLite Storage

**Tables:**

```sql
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    flp_path TEXT UNIQUE,
    last_modified REAL,        -- FLP file mtime (epoch)
    scanned_at REAL            -- When we scanned it
);

CREATE TABLE IF NOT EXISTS sample_usage (
    id INTEGER PRIMARY KEY,
    sample_path TEXT,           -- Full path to the .wav/.mp3
    kit_folder TEXT,            -- Parent directory name (the "kit")
    flp_path TEXT,              -- Which FLP references it
    UNIQUE(sample_path, flp_path)
);
```

**Key queries the other modules will use:**

```sql
-- Most used samples (across all projects)
SELECT sample_path, COUNT(DISTINCT flp_path) AS project_count
FROM sample_usage
GROUP BY sample_path
ORDER BY project_count DESC;

-- Most used kits
SELECT kit_folder, COUNT(DISTINCT flp_path) AS project_count
FROM sample_usage
GROUP BY kit_folder
ORDER BY project_count DESC;

-- Last used date per kit
SELECT su.kit_folder,
       MAX(s.last_modified) AS last_used
FROM sample_usage su
JOIN scans s ON su.flp_path = s.flp_path
GROUP BY su.kit_folder
ORDER BY last_used ASC;

-- Unused kits (not referenced by any FLP modified within threshold)
SELECT kit_folder, MAX(s.last_modified) AS last_used
FROM sample_usage su
JOIN scans s ON su.flp_path = s.flp_path
GROUP BY su.kit_folder
HAVING last_used < :cutoff_epoch;
```

### 4. analyzer.py — Stats & Ranking

Reads from SQLite and formats output:

- **Top samples** — most referenced individual samples across projects
- **Top kits** — most referenced kit folders
- **Kit timeline** — each kit with its last-used date, sorted oldest first
- **Unused kits** — kits below the threshold, candidates for archival

Output format: simple table printed to terminal (use `tabulate` library for clean formatting).

### 5. cleanup.py — Move Unused Kits

```python
import shutil, json, time

def cleanup(unused_kits: list[str], config: dict, dry_run: bool = True):
    """
    Move kit folders from drum_kits_directory to unused_directory.
    Writes a move_log.json for undo capability.
    """
    log = []
    for kit_name in unused_kits:
        src = os.path.join(config["drum_kits_directory"], kit_name)
        dst = os.path.join(config["unused_directory"], kit_name)

        if dry_run:
            print(f"[DRY RUN] Would move: {src} -> {dst}")
        else:
            shutil.move(src, dst)
            log.append({"src": src, "dst": dst, "timestamp": time.time()})
            print(f"Moved: {src} -> {dst}")

    if not dry_run and log:
        with open("move_log.json", "w") as f:
            json.dump(log, f, indent=2)
```

**Undo** reads `move_log.json` and reverses each move.

**Safety:**
- Default is always dry-run
- Requires `--confirm` flag to actually move files
- Never deletes anything, only moves
- Log file enables full reversal

---

## Data Flow

```
[FLP Projects Dir]
        |
        v
   scanner.py  ──── pyflp parses each .flp
        |              extracts Channel Rack sample paths
        |              filters by drum_kits_directory prefix
        v
     db.py  ────── SQLite stores (sample, kit, flp, last_modified)
        |
        v
   analyzer.py ─── queries DB for rankings + unused detection
        |
        v
   cleanup.py ──── moves unused kit folders + logs for undo
```

---

## Dependencies (requirements.txt)

```
pyflp>=2.0.0
tabulate
```

That's it. SQLite and everything else is stdlib.

---

## Implementation Order

1. **db.py** — Set up SQLite schema, write helper functions
2. **scanner.py** — Get pyflp parsing working on one FLP first, then batch
3. **analyzer.py** — Query + format stats
4. **cleanup.py** — Move logic with dry-run + undo
5. **main.py** — Wire up CLI subcommands
6. **Test** — Point at a small folder of FLPs, verify sample extraction is correct

---

## Gotchas & Notes

- **pyflp version**: API may vary between versions. Check `channel.sample_path` or equivalent attribute name in the version you install. Run `dir(channel)` on a parsed channel to inspect available attributes.
- **Kit detection**: A "kit" = the immediate subfolder under `drum_kits_directory`. If your structure is deeper (e.g., `Drum Kits/Producer/Kit Name/samples/`), adjust the kit extraction logic to grab the right folder level.
- **Path normalization**: FL Studio stores paths with mixed separators. Normalize everything with `os.path.normpath()` and do case-insensitive comparison on Windows.
- **Incremental scanning**: After first full scan, you can skip FLPs whose mtime hasn't changed (compare against `scans.last_modified` in DB). Saves time on large project libraries.
- **Broken references**: If a sample path in an FLP points to a file that doesn't exist on disk, log it separately — useful for knowing which projects have missing samples.
