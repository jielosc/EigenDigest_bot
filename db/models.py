"""SQLite database operations for source management and settings."""

import sqlite3
from datetime import datetime
from typing import Optional

import config


def _get_conn() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL CHECK(source_type IN ('rss', 'web', 'wechat')),
                group_name TEXT NOT NULL DEFAULT '默认',
                enabled BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # Migration: add group_name column if it doesn't exist (for existing DBs)
        try:
            conn.execute("SELECT group_name FROM sources LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE sources ADD COLUMN group_name TEXT NOT NULL DEFAULT '默认'")

        conn.commit()
    finally:
        conn.close()


def add_source(name: str, url: str, source_type: str, group_name: str = "默认") -> bool:
    """Add a new information source. Returns True if successful."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO sources (name, url, source_type, group_name) VALUES (?, ?, ?, ?)",
            (name, url, source_type, group_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_sources_batch(sources: list[dict]) -> tuple[int, int]:
    """Batch add sources. Returns (success_count, skip_count)."""
    conn = _get_conn()
    success = 0
    skipped = 0
    try:
        for s in sources:
            try:
                conn.execute(
                    "INSERT INTO sources (name, url, source_type, group_name) VALUES (?, ?, ?, ?)",
                    (s["name"], s["url"], s["source_type"], s.get("group_name", "默认")),
                )
                success += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return success, skipped


def remove_source(name: str) -> bool:
    """Remove a source by name. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM sources WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def remove_group(group_name: str) -> int:
    """Remove all sources in a group. Returns number of deleted rows."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM sources WHERE group_name = ?", (group_name,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def list_sources() -> list[dict]:
    """List all sources."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, group_name, enabled, created_at "
            "FROM sources ORDER BY group_name, id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_groups() -> list[dict]:
    """List distinct groups with counts."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT group_name, COUNT(*) as count, "
            "SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) as enabled_count "
            "FROM sources GROUP BY group_name ORDER BY group_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_enabled_sources() -> list[dict]:
    """List only enabled sources."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, group_name FROM sources WHERE enabled = 1 ORDER BY group_name, id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def toggle_source(name: str) -> Optional[bool]:
    """Toggle a source's enabled state. Returns new state or None if not found."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, enabled FROM sources WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        new_state = not row["enabled"]
        conn.execute(
            "UPDATE sources SET enabled = ? WHERE id = ?", (new_state, row["id"])
        )
        conn.commit()
        return new_state
    finally:
        conn.close()


def toggle_group(group_name: str) -> Optional[bool]:
    """Toggle all sources in a group. Returns new state or None if group not found."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, enabled FROM sources WHERE group_name = ?", (group_name,)
        ).fetchall()
        if not rows:
            return None
        # If any are enabled, disable all; otherwise enable all
        any_enabled = any(r["enabled"] for r in rows)
        new_state = not any_enabled
        conn.execute(
            "UPDATE sources SET enabled = ? WHERE group_name = ?",
            (new_state, group_name),
        )
        conn.commit()
        return new_state
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    """Get a setting value."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """Set a setting value (upsert)."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()
