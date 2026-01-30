import asyncio
import json
import logging
import os
import sqlite3

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CODE = os.getenv("ADMIN_CODE")
DB_PATH = os.getenv("DB_PATH", "bot.db")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "")
FORCE_SUB_LINK = os.getenv("FORCE_SUB_LINK", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                desc TEXT NOT NULL,
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
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    migrate_legacy_json()


def migrate_legacy_json():
    if os.path.exists("movies.json"):
        try:
            with open("movies.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            with get_db() as conn:
                for code, movie in data.items():
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO movies (code, type, file_id, desc)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            str(code).upper(),
                            movie.get("type", "text"),
                            movie.get("file_id", ""),
                            movie.get("desc", ""),
                        ),
                    )
            logger.info("movies.json dan ma'lumotlar ko'chirildi.")
        except Exception as exc:
            logger.error("movies.json migratsiyasida xatolik: %s", exc)

    if os.path.exists("admins.json"):
        try:
            with open("admins.json", "r", encoding="utf-8") as f:
                admins = json.load(f)
            with get_db() as conn:
                for admin_id in admins:
                    try:
                        admin_id = int(admin_id)
                    except (TypeError, ValueError):
                        continue
                    conn.execute(
                        """
                        INSERT INTO users (user_id, is_admin)
                        VALUES (?, 1)
                        ON CONFLICT(user_id) DO UPDATE SET is_admin = 1
                        """,
                        (admin_id,),
                    )
            logger.info("admins.json dan adminlar ko'chirildi.")
        except Exception as exc:
            logger.error("admins.json migratsiyasida xatolik: %s", exc)


def upsert_user(user):
    if not user:
        return
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user.id, user.username, user.first_name),
        )


def is_admin(user_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND is_admin = 1",
            (user_id,),
        ).fetchone()
    return bool(row)


def set_admin(user_id):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, is_admin)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET is_admin = 1
            """,
            (user_id,),
        )


def get_admin_ids():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE is_admin = 1"
        ).fetchall()
    return [row["user_id"] for row in rows]


def get_all_user_ids():
    with get_db() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [row["user_id"] for row in rows]


def get_movie(code):
    with get_db() as conn:
        row = conn.execute(
            "SELECT code, type, file_id, desc FROM movies WHERE code = ?",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def add_movie(code, content_type, file_id, desc):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO movies (code, type, file_id, desc)
            VALUES (?, ?, ?, ?)
            """,
            (code, content_type, file_id, desc),
        )


def delete_movie(code):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM movies WHERE code = ?", (code,))
    return cur.rowcount


def list_movies():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, desc, type FROM movies ORDER BY code"
        ).fetchall()
    return rows


def movie_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        rows = conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM movies GROUP BY type"
        ).fetchall()
    counts = {row["type"]: row["cnt"] for row in rows}
    return total, counts


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Kino qidirish", callback_data="search_movie"),
                InlineKeyboardButton("Admin bilan bog'lanish", callback_data="contact_admin"),
            ],
        ]
    )


def admin_panel_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Kino qo'shish", callback_data="add_movie"),
                InlineKeyboardButton("Kino o'chirish", callback_data="delete_movie"),
            ],
            [
                InlineKeyboardButton("Kinolar ro'yxati", callback_data="list_movies"),
                InlineKeyboardButton("Statistika", callback_data="admin_stats"),
            ],
            [InlineKeyboardButton("Broadcast", callback_data="broadcast")],
            [InlineKeyboardButton("Bosh menyu", callback_data="main_menu")],
        ]
    )


def not_found_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Boshqa kod", callback_data="search_movie"),
                InlineKeyboardButton("Admin bilan bog'lanish", callback_data="contact_admin"),
            ],
            [InlineKeyboardButton("Bosh menyu", callback_data="main_menu")],
        ]
    )


def force_sub_keyboard():
    buttons = []
    link = get_channel_link()
    if link:
        buttons.append([InlineKeyboardButton("Kanalga a'zo bo'lish", url=link)])
    buttons.append([InlineKeyboardButton("Tekshirish", callback_data="check_sub")])
    buttons.append([InlineKeyboardButton("Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def get_channel_link():
    if FORCE_SUB_LINK:
        return FORCE_SUB_LINK
    if FORCE_SUB_CHANNEL:
        if FORCE_SUB_CHANNEL.startswith("@"):
            return f"https://t.me/{FORCE_SUB_CHANNEL[1:]}"
        return f"https://t.me/{FORCE_SUB_CHANNEL}"
    return ""


async def is_user_subscribed(user_id, context: ContextTypes.DEFAULT_TYPE):
    if not FORCE_SUB_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.error("Force subscribe tekshiruvida xatolik: %s", exc)
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    text = (
        "Salom! Xush kelibsiz.\n\n"
        "Kino yoki video topish uchun kod yuboring yoki menyudan foydalaning."
    )
    await update.message.reply_text(
        text, reply_markup=main_menu_keyboard()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    if not ADMIN_CODE:
        await update.message.reply_text(
            "ADMIN_CODE sozlanmagan. .env faylini tekshiring."
        )
        return

    if len(context.args) == 0:
        context.user_data["awaiting_admin_code"] = True
        await update.message.reply_text("Admin kodini kiriting:")
        return

    code = context.args[0]
    if code == ADMIN_CODE:
        set_admin(update.effective_user.id)
        await update.message.reply_text(
            "Admin paneli:", reply_markup=admin_panel_keyboard()
        )
    else:
        await notify_admin_attempt(update, context, code)
        await update.message.reply_text("Noto'g'ri admin kodi!")


async def notify_admin_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE, code):
    admins = get_admin_ids()
    if not admins:
        return
    user = update.effective_user
    for admin_id in admins:
        try:
            await context.bot.send_message(
                admin_id,
                (
                    "Ogohlantirish!\n\n"
                    "Foydalanuvchi admin paneliga kirishga urindi:\n"
                    f"Ism: {user.first_name}\n"
                    f"ID: {user.id}\n"
                    f"Username: @{user.username if user.username else 'mavjud emas'}\n"
                    f"Kiritilgan kod: {code}"
                ),
            )
        except Exception as exc:
            logger.error("Admin ogohlantirishida xatolik: %s", exc)


async def handle_admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == ADMIN_CODE:
        set_admin(update.effective_user.id)
        context.user_data["awaiting_admin_code"] = False
        await update.message.reply_text(
            "Admin paneli:", reply_markup=admin_panel_keyboard()
        )
    else:
        await notify_admin_attempt(update, context, code)
        await update.message.reply_text("Noto'g'ri admin kodi!")


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    await query.edit_message_text(
        "Bosh menyu:", reply_markup=main_menu_keyboard()
    )


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Kino kodini kiriting:")


async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    admins = get_admin_ids()
    if not admins:
        await query.edit_message_text("Adminlar ro'yxati bo'sh.")
        return

    user = query.from_user
    for admin_id in admins:
        try:
            await context.bot.send_message(
                admin_id,
                (
                    "Yangi bog'lanish so'rovi\n\n"
                    f"Foydalanuvchi: {user.first_name}\n"
                    f"ID: {user.id}\n"
                    f"Username: @{user.username if user.username else 'mavjud emas'}"
                ),
            )
        except Exception as exc:
            logger.error("Adminga xabar yuborishda xatolik: %s", exc)

    await query.edit_message_text(
        "So'rovingiz adminlarga yuborildi. Tez orada bog'lanishadi."
    )


async def handle_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    subscribed = True if is_admin(user_id) else await is_user_subscribed(user_id, context)

    if subscribed:
        code = context.user_data.pop("pending_code", None)
        if code:
            try:
                await query.edit_message_text("A'zo bo'ldingiz. Kino yuborilmoqda...")
            except Exception:
                await context.bot.send_message(
                    user_id, "A'zo bo'ldingiz. Kino yuborilmoqda..."
                )
            await send_movie_by_code(user_id, code, context)
        else:
            await query.edit_message_text("A'zo bo'ldingiz. Endi kino kodini yuboring.")
    else:
        try:
            await query.edit_message_text(
                "Hali kanalga a'zo emassiz. A'zo bo'lib, qayta tekshiring.",
                reply_markup=force_sub_keyboard(),
            )
        except Exception:
            await context.bot.send_message(
                user_id,
                "Hali kanalga a'zo emassiz. A'zo bo'lib, qayta tekshiring.",
                reply_markup=force_sub_keyboard(),
            )


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    user_id = query.from_user.id
    data = query.data

    if data == "check_sub":
        return await handle_check_sub(update, context)
    if data == "search_movie":
        return await search_movie(update, context)
    if data == "contact_admin":
        return await contact_admin(update, context)
    if data == "main_menu":
        return await main_menu(update, context)

    if not is_admin(user_id):
        await query.edit_message_text("Bu bo'lim faqat adminlar uchun.")
        return

    if data == "add_movie":
        context.user_data["admin_mode"] = "add_code"
        await query.edit_message_text("Yangi kino kodi (masalan: A123):")
        return

    if data == "delete_movie":
        context.user_data["admin_mode"] = "delete"
        rows = list_movies()
        if not rows:
            await query.edit_message_text("Hozircha kino yo'q.")
            return

        keyboard = []
        row = []
        for i, item in enumerate(rows):
            row.append(
                InlineKeyboardButton(item["code"], callback_data=f"delete_{item['code']}")
            )
            if (i + 1) % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("Orqaga", callback_data="back_to_admin")])

        await query.edit_message_text(
            "O'chirmoqchi bo'lgan kino kodini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("delete_"):
        code = data.replace("delete_", "")
        deleted = delete_movie(code)
        if deleted:
            await query.edit_message_text(f"Kino o'chirildi: {code}")
        else:
            await query.edit_message_text("Bunday kod topilmadi.")
        return

    if data == "list_movies":
        rows = list_movies()
        if not rows:
            await query.edit_message_text("Hozircha kino yo'q.")
            return
        text = "Kinolar ro'yxati:\n\n"
        for item in rows:
            desc = item["desc"]
            text += f"{item['code']} - {desc[:50]}"
            if len(desc) > 50:
                text += "..."
            text += "\n"
        if len(text) > 4000:
            text = text[:4000] + "\n\n...ro'yxat juda uzun."
        await query.edit_message_text(text)
        return

    if data == "admin_stats":
        total, counts = movie_stats()
        stats_text = (
            "Admin statistikasi\n\n"
            f"Jami kinolar: {total}\n"
            f"Videolar: {counts.get('video', 0)}\n"
            f"Rasmlar: {counts.get('photo', 0)}\n"
            f"Matnlar: {counts.get('text', 0)}\n"
            f"Hujjatlar: {counts.get('document', 0)}"
        )
        await query.edit_message_text(stats_text)
        return

    if data == "broadcast":
        context.user_data["admin_mode"] = "broadcast"
        await query.edit_message_text(
            "Broadcast uchun xabar yuboring (matn yoki media)."
        )
        return

    if data == "back_to_admin":
        await query.edit_message_text(
            "Admin paneli:", reply_markup=admin_panel_keyboard()
        )


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await handle_user_code(update, context)

    mode = context.user_data.get("admin_mode")

    if mode == "add_code":
        code = update.message.text.strip().upper()
        if not code:
            return await update.message.reply_text("Kod bo'sh bo'lmasligi kerak.")
        if get_movie(code):
            return await update.message.reply_text(
                "Bu kod allaqachon mavjud. Boshqa kod kiriting."
            )
        context.user_data["new_code"] = code
        context.user_data["admin_mode"] = "add_desc"
        return await update.message.reply_text("Kino tavsifini yozing:")

    if mode == "add_desc":
        desc = update.message.text.strip()
        if not desc:
            return await update.message.reply_text("Tavsif bo'sh bo'lmasligi kerak.")
        context.user_data["new_desc"] = desc
        context.user_data["admin_mode"] = "add_file"
        return await update.message.reply_text(
            "Endi video, rasm, hujjat yoki matn yuboring:"
        )

    if mode == "add_file":
        code = context.user_data.get("new_code")
        desc = context.user_data.get("new_desc")
        if not code or not desc:
            context.user_data["admin_mode"] = None
            return await update.message.reply_text(
                "Xatolik yuz berdi. Qaytadan boshlang."
            )
        try:
            add_movie(code, "text", update.message.text, desc)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"Kino qo'shildi.\nKod: {code}\nTavsif: {desc}",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Kino qo'shishda xatolik: %s", exc)
            await update.message.reply_text("Kino qo'shishda xatolik yuz berdi.")
        return

    if mode == "delete":
        code = update.message.text.strip().upper()
        deleted = delete_movie(code)
        context.user_data["admin_mode"] = None
        if deleted:
            return await update.message.reply_text(f"Kino o'chirildi: {code}")
        return await update.message.reply_text("Bunday kod topilmadi.")

    if mode == "broadcast":
        return await broadcast_message(update, context)

    return await handle_user_code(update, context)


async def handle_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    mode = context.user_data.get("admin_mode")

    if mode == "broadcast":
        return await broadcast_message(update, context)

    if mode != "add_file":
        return

    code = context.user_data.get("new_code")
    desc = context.user_data.get("new_desc")
    if not code or not desc:
        context.user_data["admin_mode"] = None
        return await update.message.reply_text("Xatolik yuz berdi. Qaytadan boshlang.")

    content_type, file_id = extract_media(update)
    if not content_type:
        return await update.message.reply_text(
            "Faqat video, rasm yoki hujjat yuboring."
        )

    try:
        add_movie(code, content_type, file_id, desc)
        context.user_data["admin_mode"] = None
        await update.message.reply_text(
            f"Kino qo'shildi.\nKod: {code}\nTavsif: {desc}",
            reply_markup=admin_panel_keyboard(),
        )
    except Exception as exc:
        logger.error("Kino qo'shishda xatolik: %s", exc)
        await update.message.reply_text("Kino qo'shishda xatolik yuz berdi.")


def extract_media(update: Update):
    msg = update.message
    if msg.video:
        return "video", msg.video.file_id
    if msg.photo:
        return "photo", msg.photo[-1].file_id
    if msg.document:
        return "document", msg.document.file_id
    return None, None


async def send_movie_by_code(chat_id, code, context: ContextTypes.DEFAULT_TYPE):
    movie = get_movie(code)
    if not movie:
        await context.bot.send_message(
            chat_id,
            f"Bunday koddagi kino topilmadi.\nKod: {code}",
            reply_markup=not_found_keyboard(),
        )
        return
    await send_movie_to_chat(chat_id, movie, code, context)


async def send_movie_to_chat(chat_id, movie, code, context: ContextTypes.DEFAULT_TYPE):
    caption = f"Kod: {code}\n{movie['desc']}\n"
    send_map = {
        "video": context.bot.send_video,
        "photo": context.bot.send_photo,
        "document": context.bot.send_document,
    }
    try:
        if movie["type"] == "text":
            text = f"{caption}\n{movie['file_id']}"
            await context.bot.send_message(chat_id, text)
            return
        sender = send_map.get(movie["type"])
        if not sender:
            raise ValueError(f"Noma'lum kontent turi: {movie['type']}")
        await sender(chat_id, movie["file_id"], caption=caption)
    except Exception as exc:
        logger.error("Kontentni yuborishda xatolik: %s", exc)
        await context.bot.send_message(
            chat_id,
            "Kontentni yuborishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.",
        )


async def handle_user_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    code = update.message.text.strip().upper()
    if not code:
        return await update.message.reply_text("Kod bo'sh bo'lmasligi kerak.")

    if not is_admin(update.effective_user.id):
        subscribed = await is_user_subscribed(update.effective_user.id, context)
        if not subscribed:
            context.user_data["pending_code"] = code
            await update.message.reply_text(
                "Kino olishdan oldin kanalga a'zo bo'ling.",
                reply_markup=force_sub_keyboard(),
            )
            return

    await send_movie_by_code(update.effective_chat.id, code, context)


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    user_ids = get_all_user_ids()
    if not user_ids:
        context.user_data["admin_mode"] = None
        return await update.message.reply_text("Foydalanuvchilar topilmadi.")

    context.user_data["admin_mode"] = None
    source_chat_id = update.effective_chat.id
    source_message_id = update.message.message_id

    sent = 0
    failed = 0
    chunk_size = 50
    semaphore = asyncio.Semaphore(20)

    async def send_one(uid):
        async with semaphore:
            try:
                await context.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                )
                return True
            except Exception as exc:
                logger.error("Broadcast xatosi (user %s): %s", uid, exc)
                return False

    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i : i + chunk_size]
        results = await asyncio.gather(*(send_one(uid) for uid in chunk))
        sent += sum(1 for r in results if r)
        failed += sum(1 for r in results if not r)

    await update.message.reply_text(
        f"Broadcast yakunlandi.\nYuborildi: {sent}\nXatolik: {failed}"
    )


async def handle_other_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    await update.message.reply_text(
        "Kino topish uchun kod yuboring yoki menyudan foydalaning.",
        reply_markup=main_menu_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    if context.user_data.get("awaiting_admin_code"):
        return await handle_admin_login(update, context)
    return await handle_admin_text(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN .env faylida yo'q.")
    if not ADMIN_CODE:
        raise RuntimeError("ADMIN_CODE .env faylida yo'q.")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(admin_callbacks))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.PHOTO | filters.Document.ALL,
            handle_admin_media,
            block=False,
        )
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text)
    )
    app.add_handler(MessageHandler(filters.ALL, handle_other_messages))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
