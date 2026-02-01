from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from config import PROMO_CHANNEL, RANDOM_LIST_LIMIT
from handlers import common
from keyboards import force_sub_keyboard, main_menu_keyboard, numbered_keyboard
from repositories import force_channels, movies, users
from services import force_subscribe, sender

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users.upsert_user(update.effective_user)
    code = common.parse_start_code(context.args)
    if code:
        await handle_code_entry(update.effective_user.id, update.effective_chat.id, code, context)
        return

    premium_text = ""
    if users.is_user_premium(update.effective_user.id):
        premium_text = "\n\n💎 Siz Premium foydalanuvchisiz!"

    text = (
        f"🎬 Salom! Kino botiga xush kelibsiz.{premium_text}\n\n"
        "Quyidagilardan foydalaning:\n"
        "🔍 Kod bo'yicha qidirish\n"
        "🎲 Tasodifiy kinolar\n"
        "💎 Premium haqida ma'lumot\n"
        "📞 Admin bilan bog'lanish\n\n"
        "📝 Kino kodini yuboring yoki menyudan foydalaning."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def handle_user_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users.upsert_user(update.effective_user)
    raw_text = update.message.text or ""
    code = common.extract_code_from_text(raw_text) or common.normalize_code(raw_text)
    if not code:
        await update.message.reply_text("⚠️ Kod bo'sh bo'lmasligi kerak.")
        return

    await handle_code_entry(update.effective_user.id, update.effective_chat.id, code, context)


async def handle_code_entry(
    user_id: int,
    chat_id: int,
    code: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not common.is_admin(user_id):
        subscribed = await force_subscribe.is_user_subscribed(
            user_id, context, is_admin=False
        )
        if not subscribed:
            context.user_data["pending_code"] = code
            channels = force_channels.get_force_channels()
            await context.bot.send_message(
                chat_id,
                "📢 Kino olishdan oldin kanalga a'zo bo'ling yoki Premium sotib oling.",
                reply_markup=force_sub_keyboard(channels),
            )
            return

    await process_code_request(chat_id, code, context)


async def process_code_request(
    chat_id: int, code: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    movie = movies.get_movie(code)
    if movie:
        await sender.send_movie_to_chat(chat_id, movie, code, context)
        return

    children = movies.get_children(code)
    if children:
        text = "📺 Qismlar ro'yxati (eski → yangi):\n\n"
        for idx, item in enumerate(children, start=1):
            name = item.name or item.desc
            text += f"{idx}. {name} | 👁️ {item.views} - 🆔 {item.code}\n"
            if idx == 9:
                text += f"\n📢 {PROMO_CHANNEL} kanaliga obuna bo'ling.\n\n"
        await context.bot.send_message(
            chat_id,
            text,
            reply_markup=numbered_keyboard(children),
        )
        return

    await sender.send_movie_by_code(chat_id, code, context)


async def handle_random_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    users.upsert_user(query.from_user)

    rows = movies.get_random_movies(RANDOM_LIST_LIMIT)
    if not rows:
        await query.edit_message_text("⚠️ Hozircha kino yo'q.")
        return

    text = "🎲 Tasodifiy kinolar:\n\n"
    for idx, item in enumerate(rows, start=1):
        name = item.name or item.desc
        text += f"{idx}. {name} | 👁️ {item.views} - 🆔 {item.code}\n"
        if idx == 9:
            text += f"\n📢 {PROMO_CHANNEL} kanaliga obuna bo'ling.\n\n"

    await query.edit_message_text(text, reply_markup=numbered_keyboard(rows))


async def random_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users.upsert_user(update.effective_user)
    rows = movies.get_random_movies(RANDOM_LIST_LIMIT)
    if not rows:
        await update.message.reply_text("⚠️ Hozircha kino yo'q.")
        return

    text = "🎲 Tasodifiy kinolar:\n\n"
    for idx, item in enumerate(rows, start=1):
        name = item.name or item.desc
        text += f"{idx}. {name} | 👁️ {item.views} - 🆔 {item.code}\n"
        if idx == 9:
            text += f"\n📢 {PROMO_CHANNEL} kanaliga obuna bo'ling.\n\n"

    await update.message.reply_text(text, reply_markup=numbered_keyboard(rows))


async def handle_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    users.upsert_user(query.from_user)
    user_id = query.from_user.id
    data = query.data
    if data.startswith("pick:"):
        code = data.split(":", 1)[1]
    elif data.startswith("pick_"):
        code = data.replace("pick_", "", 1)
    else:
        return

    if not common.is_admin(user_id):
        subscribed = await force_subscribe.is_user_subscribed(
            user_id, context, is_admin=False
        )
        if not subscribed:
            context.user_data["pending_code"] = code
            channels = force_channels.get_force_channels()
            await common.safe_edit_or_send(
                query,
                context,
                "📢 Kino olishdan oldin kanalga a'zo bo'ling.",
                reply_markup=force_sub_keyboard(channels),
            )
            return

    chat_id = query.message.chat_id if query.message else user_id
    await process_code_request(chat_id, code, context)
