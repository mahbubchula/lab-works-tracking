from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "labworks.db"


def get_connection() -> sqlite3.Connection:
    """Return a sqlite connection with sensible defaults."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables when they do not exist."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('student', 'mentor')),
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Not started',
                visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                entry_text TEXT NOT NULL,
                progress INTEGER,
                ai_generated INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in rows]


def create_user(name: str, email: str, role: str, password_hash: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (name, email, role, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), email.strip().lower(), role, password_hash),
        )
        conn.commit()
        return cursor.lastrowid


def fetch_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = ?",
            (email.strip().lower(),),
        ).fetchone()
    return _row_to_dict(row)


def fetch_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def create_goal(
    user_id: int,
    title: str,
    description: Optional[str],
    due_date: Optional[str],
    status: str,
    visibility: str,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO goals (user_id, title, description, due_date, status, visibility)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, title.strip(), description.strip() if description else None, due_date, status, visibility),
        )
        conn.commit()
        return cursor.lastrowid


def update_goal_status(goal_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE goals SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
            (status, goal_id),
        )
        conn.commit()


def list_goals_for_user(user_id: int) -> List[Dict[str, Any]]:
    query = """
        SELECT goals.*,
               COALESCE(activity_counts.total_updates, 0) AS updates_count,
               COALESCE(activity_counts.latest_update, goals.last_updated) AS latest_update
        FROM goals
        LEFT JOIN (
            SELECT goal_id, COUNT(*) AS total_updates, MAX(created_at) AS latest_update
            FROM activities
            GROUP BY goal_id
        ) AS activity_counts ON activity_counts.goal_id = goals.id
        WHERE goals.user_id = ?
        ORDER BY goals.last_updated DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (user_id,)).fetchall()
    return _rows_to_dicts(rows)


def list_public_goals() -> List[Dict[str, Any]]:
    query = """
        SELECT goals.*, users.name AS user_name, users.role AS user_role,
               COALESCE(activity_counts.total_updates, 0) AS updates_count
        FROM goals
        JOIN users ON users.id = goals.user_id
        LEFT JOIN (
            SELECT goal_id, COUNT(*) AS total_updates
            FROM activities
            GROUP BY goal_id
        ) AS activity_counts ON activity_counts.goal_id = goals.id
        WHERE goals.visibility = 'public'
        ORDER BY goals.last_updated DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return _rows_to_dicts(rows)


def get_all_goals(viewer_role: str = "student", viewer_id: Optional[int] = None) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if viewer_role != "mentor":
        if viewer_id is None:
            clauses.append("goals.visibility = 'public'")
        else:
            clauses.append("(goals.visibility = 'public' OR goals.user_id = ?)")
            params.append(viewer_id)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT goals.*, users.name AS user_name, users.role AS user_role,
               COALESCE(activity_counts.total_updates, 0) AS updates_count,
               COALESCE(activity_counts.latest_update, goals.last_updated) AS latest_update
        FROM goals
        JOIN users ON users.id = goals.user_id
        LEFT JOIN (
            SELECT goal_id, COUNT(*) AS total_updates, MAX(created_at) AS latest_update
            FROM activities
            GROUP BY goal_id
        ) AS activity_counts ON activity_counts.goal_id = goals.id
        {where_sql}
        ORDER BY goals.last_updated DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)


def log_activity(
    goal_id: int,
    user_id: int,
    entry_text: str,
    progress: Optional[int],
    ai_generated: bool = False,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO activities (goal_id, user_id, entry_text, progress, ai_generated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (goal_id, user_id, entry_text.strip(), progress, int(ai_generated)),
        )
        conn.execute("UPDATE goals SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (goal_id,))
        if progress is not None and progress >= 100:
            conn.execute(
                "UPDATE goals SET status = 'Completed' WHERE id = ? AND status != 'Completed'",
                (goal_id,),
            )
        conn.commit()
        return cursor.lastrowid


def get_goal_activity(goal_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    query = """
        SELECT activities.*, users.name AS user_name
        FROM activities
        JOIN users ON users.id = activities.user_id
        WHERE activities.goal_id = ?
        ORDER BY activities.created_at DESC
        LIMIT ?
    """
    with get_connection() as conn:
        rows = conn.execute(query, (goal_id, limit)).fetchall()
    return _rows_to_dicts(rows)


def get_recent_activity(
    limit: int = 25,
    viewer_id: Optional[int] = None,
    viewer_role: str = "student",
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if viewer_role != "mentor":
        if viewer_id is None:
            clauses.append("goals.visibility = 'public'")
        else:
            clauses.append("(goals.visibility = 'public' OR activities.user_id = ?)")
            params.append(viewer_id)
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT activities.*, goals.title AS goal_title,
               users.name AS user_name, users.role AS user_role
        FROM activities
        JOIN goals ON goals.id = activities.goal_id
        JOIN users ON users.id = activities.user_id
        {where_sql}
        ORDER BY activities.created_at DESC
        LIMIT ?
    """
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)
