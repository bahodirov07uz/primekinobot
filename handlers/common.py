from __future__ import annotations

from typing import Optional
import re

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from keyboards import force_sub_keyboard, main_menu_keyboard
from logging_conf import get_logger
from repositories import force_channels, users
from services import force_subscribe

logger = get_logger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def normalize_code(value: str) -> str:
    return value.strip().upper()


def parse_start_code(args: list[str]) -> Optional[str]:
    if not args:
        return None
    token = args[0].strip()
    if not token:
        return None
    if token.lower().startswith("cinema_"):
        code = token.split("_", 1)[1]
        if code:
            return normalize_code(code)
    return None


def extract_code_from_text(text: str) -> Optional[str]:
    match = re.search(r"cinema_([a-zA-Z0-9]+)", text)
    if not match:
        return None
    return normalize_code(match.group(1))


async def safe_edit_or_send(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(query.from_user.id, text, reply_markup=reply_markup)


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    users.upsert_user(query.from_user)
    await safe_edit_or_send(query, context, "🏠 Bosh menyu:", main_menu_keyboard())


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await safe_edit_or_send(query, context, "🔍 Kino kodini kiriting:")


async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    users.upsert_user(query.from_user)

    if not ADMIN_IDS:
        await safe_edit_or_send(query, context, "⚠️ Adminlar ro'yxati bo'sh.")
        return

    user = query.from_user
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                (
                    "📞 Yangi bog'lanish so'rovi\n\n"
                    f"👤 Foydalanuvchi: {user.first_name}\n"
                    f"🆔 ID: {user.id}\n"
                    f"📱 Username: @{user.username if user.username else 'mavjud emas'}"
                ),
            )
        except Exception as exc:
            logger.error("Adminga xabar yuborishda xatolik: %s", exc)

    await safe_edit_or_send(
        query,
        context,
        "✅ So'rovingiz adminlarga yuborildi. Tez orada bog'lanishadi.",
    )


async def handle_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    subscribed = await force_subscribe.is_user_subscribed(
        user_id, context, is_admin=is_admin(user_id)
    )

    if subscribed:
        code = context.user_data.pop("pending_code", None)
        if code:
            await safe_edit_or_send(
                query, context, "✅ A'zo bo'ldingiz. Kino yuborilmoqda..."
            )
            from handlers import user as user_handlers

            chat_id = query.message.chat_id if query.message else user_id
            await user_handlers.process_code_request(chat_id, code, context)
        else:
            await safe_edit_or_send(
                query, context, "✅ A'zo bo'ldingiz. Endi kino kodini yuboring."
            )
        return

    channels = force_channels.get_force_channels()
    await safe_edit_or_send(
        query,
        context,
        "❌ Hali kanalga a'zo emassiz. A'zo bo'lib, qayta tekshiring.",
        reply_markup=force_sub_keyboard(channels),
    )


async def handle_other_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users.upsert_user(update.effective_user)
    await update.message.reply_text(
        "🔍 Kino topish uchun kod yuboring yoki menyudan foydalaning.\n"
        "🟢 /start - bosh menyu",
        reply_markup=main_menu_keyboard(),
    )
