from __future__ import annotations

from telegram.ext import ContextTypes

from logging_conf import get_logger
from repositories import movies
from keyboards import movie_action_keyboard, not_found_keyboard

logger = get_logger(__name__)


def _build_caption(movie: movies.Movie, code: str) -> str:
    name = movie.name or movie.desc or "Nom mavjud emas"
    desc = movie.desc or ""
    return (
        f"🎬 {name}\n\n"
        f"🆔 Kod: {code}\n"
        f"📝 {desc}\n"
        f"📥 Yuklab olingan: {movie.views + 1}\n\n"
        f"@PrimeKin0Bot - 🎬 Eng zo'r kino va seriallar shu yerda"
    )


async def send_movie_by_code(
    chat_id: int,
    code: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    movie = movies.get_movie(code)
    if not movie:
        await context.bot.send_message(
            chat_id,
            f"⚠️ Bunday koddagi kino topilmadi.\n🆔 Kod: {code}",
            reply_markup=not_found_keyboard(),
        )
        return
    await send_movie_to_chat(chat_id, movie, code, context)


async def send_movie_to_chat(
    chat_id: int,
    movie: movies.Movie,
    code: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    caption = _build_caption(movie, code)
    keyboard = movie_action_keyboard(code, include_menu=True)
    content_type = (movie.type or "document").lower()

    try:
        if content_type == "video":
            await context.bot.send_video(
                chat_id,
                movie.file_id,
                caption=caption,
                reply_markup=keyboard,
            )
        elif content_type == "photo":
            await context.bot.send_photo(
                chat_id,
                movie.file_id,
                caption=caption,
                reply_markup=keyboard,
            )
        elif content_type == "document":
            await context.bot.send_document(
                chat_id,
                movie.file_id,
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            await context.bot.send_document(
                chat_id,
                movie.file_id,
                caption=caption,
                reply_markup=keyboard,
            )

        movies.increment_views(code)
    except Exception as exc:
        logger.error("Kontentni yuborishda xatolik: %s", exc)
        await context.bot.send_message(
            chat_id,
            "❌ Kontentni yuborishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.",
        )
