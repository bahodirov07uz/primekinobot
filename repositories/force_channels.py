from __future__ import annotations

from dataclasses import dataclass

from db import execute, fetchall


@dataclass(frozen=True)
class ForceChannel:
    id: int
    channel_id: str
    channel_link: str


def add_force_channel(channel_id: str, channel_link: str) -> None:
    execute(
        "INSERT OR IGNORE INTO force_channels (channel_id, channel_link) VALUES (?, ?)",
        (channel_id, channel_link),
    )


def remove_force_channel_by_id(channel_id: int) -> int:
    return execute("DELETE FROM force_channels WHERE id = ?", (channel_id,))


def remove_force_channel_by_channel_id(channel_id: str) -> int:
    return execute("DELETE FROM force_channels WHERE channel_id = ?", (channel_id,))


def get_force_channels() -> list[ForceChannel]:
    rows = fetchall(
        "SELECT id, channel_id, channel_link FROM force_channels ORDER BY created_at ASC"
    )
    return [
        ForceChannel(
            id=row["id"],
            channel_id=row["channel_id"],
            channel_link=row["channel_link"],
        )
        for row in rows
    ]
