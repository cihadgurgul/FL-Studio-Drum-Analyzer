import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drum_usage.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flp_path TEXT UNIQUE,
            last_modified REAL,
            scanned_at REAL
        );

        CREATE TABLE IF NOT EXISTS sample_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_path TEXT,
            kit_folder TEXT,
            flp_path TEXT,
            UNIQUE(sample_path, flp_path)
        );

        CREATE INDEX IF NOT EXISTS idx_sample_usage_kit
            ON sample_usage(kit_folder);

        CREATE INDEX IF NOT EXISTS idx_sample_usage_flp
            ON sample_usage(flp_path);
    """)


def upsert_scan(conn: sqlite3.Connection, flp_path: str, last_modified: float, scanned_at: float) -> None:
    conn.execute(
        """INSERT INTO scans (flp_path, last_modified, scanned_at)
           VALUES (?, ?, ?)
           ON CONFLICT(flp_path) DO UPDATE SET
               last_modified = excluded.last_modified,
               scanned_at = excluded.scanned_at""",
        (flp_path, last_modified, scanned_at),
    )


def get_scan_mtime(conn: sqlite3.Connection, flp_path: str) -> float | None:
    row = conn.execute(
        "SELECT last_modified FROM scans WHERE flp_path = ?", (flp_path,)
    ).fetchone()
    return row[0] if row else None


def clear_samples_for_flp(conn: sqlite3.Connection, flp_path: str) -> None:
    conn.execute("DELETE FROM sample_usage WHERE flp_path = ?", (flp_path,))


def insert_sample(conn: sqlite3.Connection, sample_path: str, kit_folder: str, flp_path: str) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO sample_usage (sample_path, kit_folder, flp_path)
           VALUES (?, ?, ?)""",
        (sample_path, kit_folder, flp_path),
    )


def get_top_samples(conn: sqlite3.Connection, limit: int | None = 10) -> list[tuple[str, int]]:
    query = """SELECT sample_path, COUNT(DISTINCT flp_path) AS project_count
               FROM sample_usage
               GROUP BY sample_path
               ORDER BY project_count DESC"""
    if limit is not None:
        query += " LIMIT ?"
        return conn.execute(query, (limit,)).fetchall()
    return conn.execute(query).fetchall()


def get_top_kits(conn: sqlite3.Connection, limit: int | None = 10) -> list[tuple[str, int]]:
    query = """SELECT kit_folder, COUNT(DISTINCT flp_path) AS project_count
               FROM sample_usage
               GROUP BY kit_folder
               ORDER BY project_count DESC"""
    if limit is not None:
        query += " LIMIT ?"
        return conn.execute(query, (limit,)).fetchall()
    return conn.execute(query).fetchall()


def get_kit_timeline(conn: sqlite3.Connection) -> list[tuple[str, float]]:
    return conn.execute(
        """SELECT su.kit_folder, MAX(s.last_modified) AS last_used
           FROM sample_usage su
           JOIN scans s ON su.flp_path = s.flp_path
           GROUP BY su.kit_folder
           ORDER BY last_used ASC"""
    ).fetchall()


def get_unused_kits(conn: sqlite3.Connection, cutoff_epoch: float) -> list[tuple[str, float]]:
    return conn.execute(
        """SELECT su.kit_folder, MAX(s.last_modified) AS last_used
           FROM sample_usage su
           JOIN scans s ON su.flp_path = s.flp_path
           GROUP BY su.kit_folder
           HAVING last_used < ?
           ORDER BY last_used ASC""",
        (cutoff_epoch,),
    ).fetchall()


def get_all_known_kits(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT kit_folder FROM sample_usage").fetchall()
    return {row[0] for row in rows}
