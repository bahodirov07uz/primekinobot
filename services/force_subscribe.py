from __future__ import annotations

from telegram.ext import ContextTypes

from logging_conf import get_logger
from repositories import force_channels, users

logger = get_logger(__name__)


async def is_user_subscribed(
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_admin: bool,
) -> bool:
    if is_admin:
        return True

    if users.is_user_premium(user_id):
        return True

    channels = force_channels.get_force_channels()
    if not channels:
        return True

    for channel in channels:
        try:
            member = await context.bot.get_chat_member(channel.channel_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as exc:
            logger.error(
                "Force subscribe tekshiruvida xatolik (%s): %s",
                channel.channel_id,
                exc,
            )
            return False

    return True
