from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Callable, Iterable, Optional, Sequence, TypeVar

from config import DB_MAX_RETRIES, DB_PATH, DB_TIMEOUT
from logging_conf import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session() -> Iterable[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run_with_retry(op: Callable[[sqlite3.Connection], T]) -> T:
    delay = 0.05
    for attempt in range(DB_MAX_RETRIES):
        try:
            with db_session() as conn:
                return op(conn)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < DB_MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise


def execute(query: str, params: Sequence[object] = ()) -> int:
    def op(conn: sqlite3.Connection) -> int:
        cur = conn.execute(query, params)
        return cur.rowcount

    return _run_with_retry(op)


def executemany(query: str, params_seq: Iterable[Sequence[object]]) -> int:
    def op(conn: sqlite3.Connection) -> int:
        cur = conn.executemany(query, params_seq)
        return cur.rowcount

    return _run_with_retry(op)


def fetchone(query: str, params: Sequence[object] = ()) -> Optional[sqlite3.Row]:
    def op(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
        return conn.execute(query, params).fetchone()

    return _run_with_retry(op)


def fetchall(query: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
    def op(conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return conn.execute(query, params).fetchall()

    return _run_with_retry(op)


def init_db() -> None:
    with db_session() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                desc TEXT NOT NULL,
                parent_code TEXT,
                views INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_premium INTEGER DEFAULT 0,
                premium_until TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS force_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL UNIQUE,
                channel_link TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    ensure_columns()
    migrate_force_channels_id()
    migrate_legacy_json()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def ensure_columns() -> None:
    with db_session() as conn:
        movie_columns = _table_columns(conn, "movies")
        if "name" not in movie_columns:
            conn.execute("ALTER TABLE movies ADD COLUMN name TEXT DEFAULT ''")
        if "parent_code" not in movie_columns:
            conn.execute("ALTER TABLE movies ADD COLUMN parent_code TEXT")
        if "views" not in movie_columns:
            conn.execute("ALTER TABLE movies ADD COLUMN views INTEGER DEFAULT 0")

        user_columns = _table_columns(conn, "users")
        if "is_premium" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
        if "premium_until" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN premium_until TEXT")


def migrate_force_channels_id() -> None:
    with db_session() as conn:
        columns = _table_columns(conn, "force_channels")
        if not columns:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS force_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL UNIQUE,
                    channel_link TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            return

        if "id" in columns:
            return

        conn.execute("ALTER TABLE force_channels RENAME TO force_channels_old")
        conn.execute(
            """
            CREATE TABLE force_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL UNIQUE,
                channel_link TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO force_channels (channel_id, channel_link, created_at)
            SELECT channel_id, channel_link, created_at FROM force_channels_old
            """
        )
        conn.execute("DROP TABLE force_channels_old")


def migrate_legacy_json() -> None:
    if not os.path.exists("movies.json"):
        return

    try:
        with open("movies.json", "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except Exception as exc:
        logger.error("movies.json migratsiyasida xatolik: %s", exc)
        return

    rows: list[tuple[str, str, str, str, str, Optional[str], int]] = []
    for code, movie in data.items():
        rows.append(
            (
                str(code).upper(),
                movie.get("name", ""),
                movie.get("type", "video"),
                movie.get("file_id", ""),
                movie.get("desc", ""),
                movie.get("parent_code"),
                movie.get("views", 0),
            )
        )

    if not rows:
        return

    def op(conn: sqlite3.Connection) -> int:
        cur = conn.executemany(
            """
            INSERT OR IGNORE INTO movies (code, name, type, file_id, desc, parent_code, views)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return cur.rowcount

    try:
        _run_with_retry(op)
        logger.info("movies.json dan ma'lumotlar ko'chirildi.")
    except Exception as exc:
        logger.error("movies.json migratsiyasida xatolik: %s", exc)
