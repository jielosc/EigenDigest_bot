"""SQLite database operations for multi-user source management."""

import secrets
import sqlite3
from datetime import datetime
from typing import Optional

import config


def _get_conn() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Initialize database tables."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                created_by INTEGER NOT NULL,
                used_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('rss', 'web', 'wechat')),
                group_name TEXT NOT NULL DEFAULT '默认',
                enabled BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            );

            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            );
        """)

        # Ensure admin user exists
        if config.ADMIN_USER_ID:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'admin')",
                (config.ADMIN_USER_ID,),
            )

        conn.commit()
    finally:
        conn.close()


# ─── User Management ─────────────────────────────────────────


def get_user(user_id: int) -> Optional[dict]:
    """Get a user by ID. Returns None if not found."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, username, role, joined_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def is_authorized(user_id: int) -> bool:
    """Check if a user is authorized (exists in users table)."""
    return get_user(user_id) is not None


def is_admin(user_id: int) -> bool:
    """Check if a user is admin."""
    user = get_user(user_id)
    return user is not None and user["role"] == "admin"


def add_user(user_id: int, username: str = "", role: str = "user") -> bool:
    """Add a new user."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role) VALUES (?, ?, ?)",
            (user_id, username, role),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_user(user_id: int) -> bool:
    """Remove a user and all their sources/settings."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM sources WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        cursor = conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_users() -> list[dict]:
    """List all users."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT u.user_id, u.username, u.role, u.joined_at, "
            "(SELECT COUNT(*) FROM sources WHERE user_id = u.user_id) as source_count "
            "FROM users u ORDER BY u.joined_at"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_user_ids() -> list[int]:
    """Get all user IDs (for scheduled digest)."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [row["user_id"] for row in rows]
    finally:
        conn.close()


# ─── Invite Codes ─────────────────────────────────────────────


def create_invite_code(created_by: int) -> str:
    """Generate a new invite code."""
    code = secrets.token_urlsafe(8)  # ~11 chars, e.g. "aB3x_Y7z-kQ"
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
            (code, created_by),
        )
        conn.commit()
    finally:
        conn.close()
    return code


def use_invite_code(code: str, user_id: int) -> bool:
    """Use an invite code. Returns True if valid and unused."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT code, used_by FROM invite_codes WHERE code = ?", (code,)
        ).fetchone()
        if not row or row["used_by"] is not None:
            return False
        conn.execute(
            "UPDATE invite_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?",
            (user_id, code),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_invite_codes(created_by: int) -> list[dict]:
    """List invite codes created by a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT code, used_by, created_at, used_at FROM invite_codes "
            "WHERE created_by = ? ORDER BY created_at DESC",
            (created_by,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ─── Sources (per-user) ──────────────────────────────────────


def add_source(user_id: int, name: str, url: str, source_type: str, group_name: str = "默认") -> bool:
    """Add a source for a specific user."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO sources (user_id, name, url, source_type, group_name) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, url, source_type, group_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_sources_batch(user_id: int, sources: list[dict]) -> tuple[int, int]:
    """Batch add sources for a user. Returns (success_count, skip_count)."""
    conn = _get_conn()
    success = 0
    skipped = 0
    try:
        for s in sources:
            try:
                conn.execute(
                    "INSERT INTO sources (user_id, name, url, source_type, group_name) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, s["name"], s["url"], s["source_type"], s.get("group_name", "默认")),
                )
                success += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return success, skipped


def remove_source(user_id: int, name: str) -> bool:
    """Remove a source by name for a user."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM sources WHERE user_id = ? AND name = ?", (user_id, name)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def remove_group(user_id: int, group_name: str) -> int:
    """Remove all sources in a group for a user."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM sources WHERE user_id = ? AND group_name = ?",
            (user_id, group_name),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def list_sources(user_id: int) -> list[dict]:
    """List all sources for a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, group_name, enabled, created_at "
            "FROM sources WHERE user_id = ? ORDER BY group_name, id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_groups(user_id: int) -> list[dict]:
    """List distinct groups with counts for a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT group_name, COUNT(*) as count, "
            "SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) as enabled_count "
            "FROM sources WHERE user_id = ? GROUP BY group_name ORDER BY group_name",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_enabled_sources(user_id: int) -> list[dict]:
    """List only enabled sources for a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, group_name "
            "FROM sources WHERE user_id = ? AND enabled = 1 ORDER BY group_name, id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def toggle_source(user_id: int, name: str) -> Optional[bool]:
    """Toggle a source for a user. Returns new state or None."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, enabled FROM sources WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if not row:
            return None
        new_state = not row["enabled"]
        conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (new_state, row["id"]))
        conn.commit()
        return new_state
    finally:
        conn.close()


def toggle_group(user_id: int, group_name: str) -> Optional[bool]:
    """Toggle all sources in a group for a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, enabled FROM sources WHERE user_id = ? AND group_name = ?",
            (user_id, group_name),
        ).fetchall()
        if not rows:
            return None
        any_enabled = any(r["enabled"] for r in rows)
        new_state = not any_enabled
        conn.execute(
            "UPDATE sources SET enabled = ? WHERE user_id = ? AND group_name = ?",
            (new_state, user_id, group_name),
        )
        conn.commit()
        return new_state
    finally:
        conn.close()


# ─── Settings (per-user) ─────────────────────────────────────


def get_setting(user_id: int, key: str, default: str = "") -> str:
    """Get a per-user setting value."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(user_id: int, key: str, value: str) -> None:
    """Set a per-user setting value (upsert)."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, value),
        )
        conn.commit()
    finally:
        conn.close()
