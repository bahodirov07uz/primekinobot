from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from db import execute, fetchall, fetchone


@dataclass(frozen=True)
class Movie:
    code: str
    name: str
    type: str
    file_id: str
    desc: str
    parent_code: Optional[str]
    views: int


@dataclass(frozen=True)
class MovieListItem:
    code: str
    name: str
    desc: str
    type: str
    views: int
    parent_code: Optional[str]


def _row_to_movie(row) -> Movie:
    return Movie(
        code=row["code"],
        name=row["name"],
        type=row["type"],
        file_id=row["file_id"],
        desc=row["desc"],
        parent_code=row["parent_code"],
        views=row["views"] or 0,
    )


def _row_to_list_item(row) -> MovieListItem:
    return MovieListItem(
        code=row["code"],
        name=row["name"],
        desc=row["desc"],
        type=row["type"],
        views=row["views"] or 0,
        parent_code=row["parent_code"],
    )


def get_movie(code: str) -> Optional[Movie]:
    row = fetchone(
        """
        SELECT code, name, type, file_id, desc, parent_code, views
        FROM movies WHERE code = ?
        """,
        (code,),
    )
    return _row_to_movie(row) if row else None


def add_movie(
    code: str,
    name: str,
    content_type: str,
    file_id: str,
    desc: str,
    parent_code: Optional[str] = None,
) -> None:
    execute(
        """
        INSERT INTO movies (code, name, type, file_id, desc, parent_code)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (code, name, content_type, file_id, desc, parent_code),
    )


def update_movie_field(code: str, field: str, value: Optional[str]) -> int:
    if field not in {"name", "desc", "file_id", "type", "parent_code"}:
        raise ValueError("Invalid field")
    return execute(f"UPDATE movies SET {field} = ? WHERE code = ?", (value, code))


def delete_movie(code: str) -> int:
    return execute("DELETE FROM movies WHERE code = ?", (code,))


def list_movies(limit: Optional[int] = None) -> list[MovieListItem]:
    query = """
        SELECT code, name, desc, type, views, parent_code
        FROM movies
        ORDER BY created_at DESC
    """
    if limit:
        query += " LIMIT ?"
        rows = fetchall(query, (limit,))
    else:
        rows = fetchall(query)
    return [_row_to_list_item(row) for row in rows]


def movie_stats() -> tuple[int, dict[str, int]]:
    total_row = fetchone("SELECT COUNT(*) AS cnt FROM movies")
    total = total_row["cnt"] if total_row else 0
    rows = fetchall("SELECT type, COUNT(*) AS cnt FROM movies GROUP BY type")
    counts = {row["type"]: row["cnt"] for row in rows}
    return total, counts


def get_random_movies(limit: int) -> list[MovieListItem]:
    rows = fetchall(
        """
        SELECT code, name, desc, type, views, parent_code
        FROM movies ORDER BY RANDOM() LIMIT ?
        """,
        (limit,),
    )
    return [_row_to_list_item(row) for row in rows]


def get_children(parent_code: str) -> list[MovieListItem]:
    rows = fetchall(
        """
        SELECT code, name, desc, type, views, parent_code
        FROM movies
        WHERE parent_code = ?
        ORDER BY created_at ASC
        """,
        (parent_code,),
    )
    return [_row_to_list_item(row) for row in rows]


def increment_views(code: str) -> None:
    execute("UPDATE movies SET views = COALESCE(views, 0) + 1 WHERE code = ?", (code,))
