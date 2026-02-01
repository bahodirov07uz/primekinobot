from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Protocol

from db import execute, fetchall, fetchone


class TelegramUser(Protocol):
    id: int
    username: Optional[str]
    first_name: Optional[str]


@dataclass(frozen=True)
class PremiumStats:
    premium_count: int
    total_count: int


def upsert_user(user: Optional[TelegramUser]) -> None:
    if not user:
        return
    execute(
        """
        INSERT INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
        """,
        (user.id, user.username, user.first_name),
    )


def get_all_user_ids() -> list[int]:
    rows = fetchall("SELECT user_id FROM users")
    return [row["user_id"] for row in rows]


def get_user_count() -> int:
    row = fetchone("SELECT COUNT(*) AS cnt FROM users")
    return int(row["cnt"]) if row else 0


def is_user_premium(user_id: int) -> bool:
    row = fetchone(
        "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
        (user_id,),
    )
    if not row or not row["is_premium"]:
        return False

    premium_until = row["premium_until"]
    if not premium_until:
        return True

    try:
        expiry = datetime.fromisoformat(premium_until)
    except ValueError:
        return True

    if datetime.now() > expiry:
        remove_user_premium(user_id)
        return False

    return True


def set_user_premium(user_id: int, months: int = 1) -> None:
    expiry_date = datetime.now() + timedelta(days=30 * months)
    execute(
        """
        INSERT INTO users (user_id, is_premium, premium_until)
        VALUES (?, 1, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            is_premium = 1,
            premium_until = excluded.premium_until
        """,
        (user_id, expiry_date.isoformat()),
    )


def remove_user_premium(user_id: int) -> None:
    execute(
        "UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?",
        (user_id,),
    )


def get_premium_stats() -> PremiumStats:
    premium_row = fetchone("SELECT COUNT(*) AS cnt FROM users WHERE is_premium = 1")
    total_row = fetchone("SELECT COUNT(*) AS cnt FROM users")
    premium_count = int(premium_row["cnt"]) if premium_row else 0
    total_count = int(total_row["cnt"]) if total_row else 0
    return PremiumStats(premium_count=premium_count, total_count=total_count)
