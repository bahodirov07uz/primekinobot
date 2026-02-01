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
DB_PATH = os.getenv("DB_PATH", "bot.db")
FORCE_SUB_LINK = os.getenv("FORCE_SUB_LINK", "")

# Admin ID'lar - vergul bilan ajratilgan
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

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
        # Movies table with 'name' column
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
        # Users table - tracks all users with premium status
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
        # Force subscribe channels table
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
    migrate_legacy_json()


def ensure_columns():
    with get_db() as conn:
        # Check movies table
        rows = conn.execute("PRAGMA table_info(movies)").fetchall()
        columns = {row["name"] for row in rows}
        
        if "name" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN name TEXT DEFAULT ''")
        if "parent_code" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN parent_code TEXT")
        if "views" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN views INTEGER DEFAULT 0")
        
        # Check users table for premium columns
        user_rows = conn.execute("PRAGMA table_info(users)").fetchall()
        user_columns = {row["name"] for row in user_rows}
        
        if "is_premium" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
        if "premium_until" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN premium_until TEXT")


def migrate_legacy_json():
    if os.path.exists("movies.json"):
        try:
            with open("movies.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            with get_db() as conn:
                for code, movie in data.items():
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO movies (code, name, type, file_id, desc, parent_code, views)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(code).upper(),
                            movie.get("name", ""),
                            movie.get("type", "video"),  # Default to video
                            movie.get("file_id", ""),
                            movie.get("desc", ""),
                            movie.get("parent_code"),
                            movie.get("views", 0),
                        ),
                    )
            logger.info("movies.json dan ma'lumotlar ko'chirildi.")
        except Exception as exc:
            logger.error("movies.json migratsiyasida xatolik: %s", exc)


def upsert_user(user):
    """Track all users who interact with bot"""
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
    """Check if user is admin based on ADMIN_IDS from .env"""
    return user_id in ADMIN_IDS


def get_all_user_ids():
    with get_db() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [row["user_id"] for row in rows]


def get_user_count():
    """Get total number of users"""
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return count


def is_user_premium(user_id):
    """Check if user has active premium"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    
    if not row:
        return False
    
    if not row["is_premium"]:
        return False
    
    # Check expiration
    if row["premium_until"]:
        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(row["premium_until"])
            if datetime.now() > expiry:
                # Premium expired
                return False
        except:
            pass
    
    return True


def set_user_premium(user_id, months=1):
    """Set user as premium for given months"""
    from datetime import datetime, timedelta
    
    expiry_date = datetime.now() + timedelta(days=30 * months)
    
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, is_premium, premium_until)
            VALUES (?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                is_premium = 1,
                premium_until = excluded.premium_until
            """,
            (user_id, expiry_date.isoformat()),
        )


def remove_user_premium(user_id):
    """Remove premium from user"""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?",
            (user_id,),
        )


def get_premium_stats():
    """Get premium statistics"""
    with get_db() as conn:
        premium_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_premium = 1"
        ).fetchone()[0]
        total_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return premium_count, total_count


def get_movie(code):
    with get_db() as conn:
        row = conn.execute(
            "SELECT code, name, type, file_id, desc, parent_code, views FROM movies WHERE code = ?",
            (code,),
        ).fetchone()
    return dict(row) if row else None


def add_movie(code, name, content_type, file_id, desc, parent_code=None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO movies (code, name, type, file_id, desc, parent_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, name, content_type, file_id, desc, parent_code),
        )


def delete_movie(code):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM movies WHERE code = ?", (code,))
    return cur.rowcount


def list_movies():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, name, desc, type, views, parent_code FROM movies ORDER BY created_at DESC"
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


def get_random_movies(limit=15):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, name, desc, views FROM movies ORDER BY RANDOM() LIMIT ?",
            (limit,),
        ).fetchall()
    return rows


def get_children(parent_code):
    """Get series episodes - OLDEST FIRST (created_at ASC)"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT code, name, desc, views FROM movies
            WHERE parent_code = ?
            ORDER BY created_at ASC
            """,
            (parent_code,),
        ).fetchall()
    return rows


def increment_views(code):
    with get_db() as conn:
        conn.execute(
            "UPDATE movies SET views = COALESCE(views, 0) + 1 WHERE code = ?",
            (code,),
        )


# Force subscribe channels management
def add_force_channel(channel_id, channel_link):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO force_channels (channel_id, channel_link) VALUES (?, ?)",
            (channel_id, channel_link),
        )


def remove_force_channel(channel_id):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM force_channels WHERE channel_id = ?", (channel_id,))
        conn.commit()
    return cur.rowcount


def get_force_channels():
    with get_db() as conn:
        rows = conn.execute("SELECT channel_id, channel_link FROM force_channels").fetchall()
    return [(row["channel_id"], row["channel_link"]) for row in rows]


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔍 Kino qidirish", callback_data="search_movie"),
            ],
            [
                InlineKeyboardButton("🎲 Tasodifiy kinolar", callback_data="random_movies"),
            ],
        ]
    )


def admin_panel_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Kino qo'shish", callback_data="add_movie"),
                InlineKeyboardButton("🗑 Kino o'chirish", callback_data="delete_movie"),
            ],
            [
                InlineKeyboardButton("📋 Kinolar ro'yxati", callback_data="list_movies"),
                InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
            ],
            [
                InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel"),
                InlineKeyboardButton("🗑 Kanal o'chirish", callback_data="delete_channel"),
            ],
            [
                InlineKeyboardButton("💎 Premium berish", callback_data="give_premium"),
                InlineKeyboardButton("🚫 Premium olish", callback_data="remove_premium"),
            ],
            [
                InlineKeyboardButton("📢 Xabar yuborish", callback_data="broadcast"),
                InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="user_stats"),
            ],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
        ]
    )


def not_found_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔍 Boshqa kod", callback_data="search_movie"),
                InlineKeyboardButton("📞 Admin", callback_data="contact_admin"),
            ],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
        ]
    )


def numbered_keyboard(items, prefix="pick"):
    buttons = []
    row = []
    for idx, item in enumerate(items, start=1):
        row.append(InlineKeyboardButton(str(idx), callback_data=f"{prefix}_{item['code']}"))
        if idx % 5 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def force_sub_keyboard():
    """Force subscribe keyboard with premium option at the bottom"""
    buttons = []
    channels = get_force_channels()
    
    for channel_id, channel_link in channels:
        buttons.append([InlineKeyboardButton(f"📢 {channel_id} ga qo'shilish", url=channel_link)])
    
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    
    # Premium purchase options at the bottom
    buttons.append([InlineKeyboardButton("💎 Premium sotib olish", callback_data="buy_premium")])
    
    return InlineKeyboardMarkup(buttons)


def premium_prices_keyboard():
    """Premium purchase options with prices"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 1 oy - 5,000 so'm", callback_data="premium_price_1")],
        [InlineKeyboardButton("💎 3 oy - 14,000 so'm", callback_data="premium_price_3")],
        [InlineKeyboardButton("💎 6 oy - 27,000 so'm", callback_data="premium_price_6")],
        [InlineKeyboardButton("💎 12 oy - 50,000 so'm", callback_data="premium_price_12")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
    ])


async def is_user_subscribed(user_id, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to all force channels OR has premium"""
    
    # Premium users skip force subscribe
    if is_user_premium(user_id):
        return True
    
    channels = get_force_channels()
    
    if not channels:
        return True
    
    for channel_id, _ in channels:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as exc:
            logger.error(f"Force subscribe tekshiruvida xatolik ({channel_id}): %s", exc)
            return False
    
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    
    # Show premium status if user has it
    premium_text = ""
    if is_user_premium(update.effective_user.id):
        premium_text = "\n\n💎 Siz Premium foydalanuvchisiz!"
    
    text = (
        f"🎬 Salom! Kino botiga xush kelibsiz.{premium_text}\n\n"
        "📝 Kino kodini yuboring yoki quyidagi menyudan foydalaning."
    )
    await update.message.reply_text(
        text, reply_markup=main_menu_keyboard()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel - only for ADMIN_IDS from .env"""
    upsert_user(update.effective_user)
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q.\n\n"
            "Agar admin bo'lmoqchi bo'lsangiz, bot egasi bilan bog'laning."
        )
        return
    
    await update.message.reply_text(
        "✅ Admin paneli:", reply_markup=admin_panel_keyboard()
    )


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    await query.edit_message_text(
        "🏠 Bosh menyu:", reply_markup=main_menu_keyboard()
    )


async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 Kino kodini kiriting:")


async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    
    if not ADMIN_IDS:
        await query.edit_message_text("⚠️ Adminlar ro'yxati bo'sh.")
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

    await query.edit_message_text(
        "✅ So'rovingiz adminlarga yuborildi. Tez orada bog'lanishadi."
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
                await query.edit_message_text("✅ A'zo bo'ldingiz. Kino yuborilmoqda...")
            except Exception:
                await context.bot.send_message(
                    user_id, "✅ A'zo bo'ldingiz. Kino yuborilmoqda..."
                )
            await send_movie_by_code(user_id, code, context)
        else:
            await query.edit_message_text("✅ A'zo bo'ldingiz. Endi kino kodini yuboring.")
    else:
        try:
            await query.edit_message_text(
                "❌ Hali kanalga a'zo emassiz. A'zo bo'lib, qayta tekshiring.",
                reply_markup=force_sub_keyboard(),
            )
        except Exception:
            await context.bot.send_message(
                user_id,
                "❌ Hali kanalga a'zo emassiz. A'zo bo'lib, qayta tekshiring.",
                reply_markup=force_sub_keyboard(),
            )


async def handle_random_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    rows = get_random_movies(15)
    if not rows:
        await query.edit_message_text("⚠️ Hozircha kino yo'q.")
        return

    text = "🎲 Tasodifiy kinolar:\n\n"
    for idx, item in enumerate(rows, start=1):
        name = item['name'] or item['desc']
        text += f"{idx}. {name} | 👁️ {item['views']} - 🆔 {item['code']}\n"
        if idx == 9:
            text += "\n📢 @primekin0 kanaliga obuna bo'ling.\n\n"

    await query.edit_message_text(
        text, reply_markup=numbered_keyboard(rows)
    )


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upsert_user(query.from_user)
    user_id = query.from_user.id
    data = query.data

    if data.startswith("pick_"):
        code = data.replace("pick_", "", 1)
        if not is_admin(user_id):
            subscribed = await is_user_subscribed(user_id, context)
            if not subscribed:
                context.user_data["pending_code"] = code
                await query.edit_message_text(
                    "📢 Kino olishdan oldin kanalga a'zo bo'ling.",
                    reply_markup=force_sub_keyboard(),
                )
                return
        await send_movie_by_code(user_id, code, context)
        return

    if data == "check_sub":
        return await handle_check_sub(update, context)
    if data == "search_movie":
        return await search_movie(update, context)
    if data == "contact_admin":
        return await contact_admin(update, context)
    if data == "main_menu":
        return await main_menu(update, context)
    if data == "random_movies":
        return await handle_random_movies(update, context)

    # Premium purchase for regular users
    if data == "buy_premium":
        await query.edit_message_text(
            "💎 Premium obuna\n\n"
            "Premium foydalanuvchilar uchun imtiyozlar:\n"
            "✅ Majburiy kanallarga obuna bo'lmasdan kinolar\n"
            "✅ Reklama yo'q\n"
            "✅ Yangi kinolar birinchi bo'lib\n\n"
            "Narxlarni tanlang:",
            reply_markup=premium_prices_keyboard()
        )
        return

    if data.startswith("premium_price_"):
        months = int(data.split("_")[2])
        prices = {1: 5000, 3: 14000, 6: 27000, 12: 50000}
        price = prices.get(months, 5000)
        
        await query.edit_message_text(
            f"💎 Premium obuna - {months} oy\n\n"
            f"💰 Narx: {price:,} so'm\n\n"
            f"To'lov uchun admin bilan bog'laning:\n"
            f"🆔 Sizning ID: {user_id}\n\n"
            "To'lov qilgandan keyin adminlarga xabar bering.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Admin", callback_data="contact_admin")],
                [InlineKeyboardButton("◀️ Orqaga", callback_data="buy_premium")]
            ])
        )
        return

    # Admin-only callbacks below
    if not is_admin(user_id):
        await query.edit_message_text("⚠️ Bu bo'lim faqat adminlar uchun.")
        return

    if data == "add_movie":
        context.user_data["admin_mode"] = "add_code"
        await query.edit_message_text("📝 Yangi kino kodi (masalan: A123):")
        return

    if data == "delete_movie":
        context.user_data["admin_mode"] = "delete"
        rows = list_movies()
        if not rows:
            await query.edit_message_text("⚠️ Hozircha kino yo'q.")
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
        keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_admin")])

        await query.edit_message_text(
            "🗑 O'chirmoqchi bo'lgan kino kodini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("delete_"):
        code = data.replace("delete_", "")
        deleted = delete_movie(code)
        if deleted:
            await query.edit_message_text(f"✅ Kino o'chirildi: {code}")
        else:
            await query.edit_message_text("⚠️ Bunday kod topilmadi.")
        return

    if data == "list_movies":
        rows = list_movies()
        if not rows:
            await query.edit_message_text("⚠️ Hozircha kino yo'q.")
            return
        text = "📋 Kinolar ro'yxati (yangi → eski):\n\n"
        for item in rows[:50]:  # First 50
            name = item["name"] or item["desc"][:30]
            text += f"🆔 {item['code']} - {name} | 👁️ {item['views']}\n"
        if len(rows) > 50:
            text += f"\n...va yana {len(rows) - 50} ta kino"
        await query.edit_message_text(text)
        return

    if data == "admin_stats":
        total, counts = movie_stats()
        user_count = get_user_count()
        premium_count, _ = get_premium_stats()
        stats_text = (
            "📊 Admin statistikasi\n\n"
            f"👥 Foydalanuvchilar: {user_count}\n"
            f"💎 Premium: {premium_count}\n"
            f"📁 Jami kinolar: {total}\n"
            f"🎥 Videolar: {counts.get('video', 0)}\n"
            f"📄 Hujjatlar: {counts.get('document', 0)}\n"
            f"🖼 Rasmlar: {counts.get('photo', 0)}\n"
            f"📝 Matnlar: {counts.get('text', 0)}"
        )
        await query.edit_message_text(stats_text)
        return

    if data == "user_stats":
        user_count = get_user_count()
        premium_count, total = get_premium_stats()
        await query.edit_message_text(
            f"👥 Foydalanuvchilar statistikasi\n\n"
            f"Jami foydalanuvchilar: {total}\n"
            f"💎 Premium foydalanuvchilar: {premium_count}\n"
            f"👤 Oddiy foydalanuvchilar: {total - premium_count}"
        )
        return

    if data == "give_premium":
        context.user_data["admin_mode"] = "give_premium_id"
        await query.edit_message_text(
            "💎 Premium berish\n\n"
            "Foydalanuvchi ID yoki username kiriting:\n"
            "Masalan: 123456789 yoki @username"
        )
        return

    if data == "remove_premium":
        context.user_data["admin_mode"] = "remove_premium_id"
        await query.edit_message_text(
            "🚫 Premium olish\n\n"
            "Foydalanuvchi ID kiriting:\n"
            "Masalan: 123456789"
        )
        return

    if data == "add_channel":
        context.user_data["admin_mode"] = "add_channel_id"
        await query.edit_message_text(
            "📢 Majburiy kanal ID'sini kiriting:\n\n"
            "Masalan: @primekin0 yoki -1001234567890"
        )
        return

    if data == "delete_channel":
        channels = get_force_channels()
        if not channels:
            await query.edit_message_text("⚠️ Majburiy kanallar yo'q.")
            return
        
        keyboard = []
        for channel_id, _ in channels:
            # URL encode the channel_id to handle special characters
            import urllib.parse
            encoded_id = urllib.parse.quote(channel_id, safe='')
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {channel_id}", 
                    callback_data=f"delchan_{encoded_id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_admin")])
        
        await query.edit_message_text(
            "🗑 O'chirmoqchi bo'lgan kanalni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("delchan_"):
        # Decode the channel_id
        import urllib.parse
        encoded_id = data[8:]  # Remove "delchan_" prefix
        channel_id = urllib.parse.unquote(encoded_id)
        
        removed = remove_force_channel(channel_id)
        if removed:
            await query.edit_message_text(
                f"✅ Kanal o'chirildi: {channel_id}",
                reply_markup=admin_panel_keyboard()
            )
        else:
            await query.edit_message_text(
                "⚠️ Kanal topilmadi.",
                reply_markup=admin_panel_keyboard()
            )
        return

    if data == "broadcast":
        context.user_data["admin_mode"] = "broadcast"
        await query.edit_message_text(
            "📢 Broadcast uchun xabar yuboring (matn yoki media)."
        )
        return

    if data == "back_to_admin":
        await query.edit_message_text(
            "⚙️ Admin paneli:", reply_markup=admin_panel_keyboard()
        )


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await handle_user_code(update, context)

    mode = context.user_data.get("admin_mode")

    if mode == "add_code":
        code = update.message.text.strip().upper()
        if not code:
            return await update.message.reply_text("⚠️ Kod bo'sh bo'lmasligi kerak.")
        if get_movie(code):
            return await update.message.reply_text(
                "⚠️ Bu kod allaqachon mavjud. Boshqa kod kiriting."
            )
        context.user_data["new_code"] = code
        context.user_data["admin_mode"] = "add_name"
        return await update.message.reply_text("📝 Kino nomini yozing:")

    if mode == "add_name":
        name = update.message.text.strip()
        if not name:
            return await update.message.reply_text("⚠️ Nom bo'sh bo'lmasligi kerak.")
        context.user_data["new_name"] = name
        context.user_data["admin_mode"] = "add_desc"
        return await update.message.reply_text("📝 Kino tavsifini yozing:")

    if mode == "add_desc":
        desc = update.message.text.strip()
        if not desc:
            return await update.message.reply_text("⚠️ Tavsif bo'sh bo'lmasligi kerak.")
        context.user_data["new_desc"] = desc
        context.user_data["admin_mode"] = "add_parent"
        return await update.message.reply_text(
            "🎬 Agar serial bo'lsa, asosiy kodini yuboring. Aks holda '-' yuboring:"
        )

    if mode == "add_parent":
        parent_code = update.message.text.strip().upper()
        if parent_code == "-":
            parent_code = None
        if parent_code and not parent_code.strip():
            parent_code = None
        context.user_data["new_parent"] = parent_code
        context.user_data["admin_mode"] = "add_file"
        return await update.message.reply_text(
            "📤 Endi video FILE_ID ni matn sifatida yuboring:\n\n"
            "Masalan: BAACAgIAAxkBAAFBjGdpfaHOG3hd3yWFIPZ3-nhmkhZEHQAC2pkAArZd6EtLDMX_kNng_DgE"
        )

    if mode == "add_file":
        # Admin file_id matn sifatida yuborsa
        file_id_text = update.message.text.strip()
        if not file_id_text:
            return await update.message.reply_text("⚠️ File_id bo'sh bo'lmasligi kerak.")

        code = context.user_data.get("new_code")
        name = context.user_data.get("new_name")
        desc = context.user_data.get("new_desc")
        parent_code = context.user_data.get("new_parent")

        if not code or not name or not desc:
            context.user_data["admin_mode"] = None
            return await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")

        try:
            # Default: video (faqat video type ishlatamiz!)
            add_movie(code, name, "video", file_id_text, desc, parent_code)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Kino qo'shildi!\n\n"
                f"🆔 Kod: {code}\n"
                f"📝 Nom: {name}\n"
                f"📄 Tavsif: {desc}\n"
                f"📁 Turi: video",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Kino qo'shishda xatolik: %s", exc)
            await update.message.reply_text("❌ Kino qo'shishda xatolik yuz berdi.")
        return

    if mode == "delete":
        code = update.message.text.strip().upper()
        deleted = delete_movie(code)
        context.user_data["admin_mode"] = None
        if deleted:
            return await update.message.reply_text(f"✅ Kino o'chirildi: {code}")
        return await update.message.reply_text("⚠️ Bunday kod topilmadi.")

    if mode == "add_channel_id":
        channel_id = update.message.text.strip()
        if not channel_id:
            return await update.message.reply_text("⚠️ Kanal ID bo'sh bo'lmasligi kerak.")
        context.user_data["new_channel_id"] = channel_id
        context.user_data["admin_mode"] = "add_channel_link"
        return await update.message.reply_text(
            "🔗 Kanal linkini kiriting:\n\n"
            "Masalan: https://t.me/primekin0"
        )

    if mode == "add_channel_link":
        channel_link = update.message.text.strip()
        if not channel_link:
            return await update.message.reply_text("⚠️ Link bo'sh bo'lmasligi kerak.")

        channel_id = context.user_data.get("new_channel_id")
        if not channel_id:
            context.user_data["admin_mode"] = None
            return await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")

        try:
            add_force_channel(channel_id, channel_link)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Majburiy kanal qo'shildi!\n\n"
                f"📢 Kanal: {channel_id}\n"
                f"🔗 Link: {channel_link}",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Kanal qo'shishda xatolik: %s", exc)
            await update.message.reply_text("❌ Kanal qo'shishda xatolik yuz berdi.")
        return

    if mode == "give_premium_id":
        user_input = update.message.text.strip()
        if not user_input:
            return await update.message.reply_text("⚠️ ID yoki username kiriting.")
        
        # Try to extract user_id
        target_user_id = None
        if user_input.startswith("@"):
            context.user_data["premium_target"] = user_input
        else:
            try:
                target_user_id = int(user_input)
                context.user_data["premium_target"] = target_user_id
            except ValueError:
                return await update.message.reply_text("⚠️ Noto'g'ri ID format. Raqam yoki @username kiriting.")
        
        context.user_data["admin_mode"] = "give_premium_months"
        return await update.message.reply_text(
            "📅 Necha oyga premium bermoqchisiz?\n\n"
            "Masalan: 1, 3, 6, 12"
        )

    if mode == "give_premium_months":
        try:
            months = int(update.message.text.strip())
            if months < 1 or months > 120:
                return await update.message.reply_text("⚠️ 1 dan 120 oygacha kiriting.")
        except ValueError:
            return await update.message.reply_text("⚠️ Raqam kiriting.")
        
        target = context.user_data.get("premium_target")
        if not target:
            context.user_data["admin_mode"] = None
            return await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")
        
        # If username, try to resolve it
        if isinstance(target, str) and target.startswith("@"):
            await update.message.reply_text(
                f"⚠️ Username orqali qo'shish hozircha qo'llab-quvvatlanmaydi.\n"
                f"Iltimos, foydalanuvchi ID'sini kiriting.\n\n"
                f"User o'zini /start qilsa, ID ni olishingiz mumkin."
            )
            context.user_data["admin_mode"] = None
            return
        
        try:
            set_user_premium(target, months)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Premium berildi!\n\n"
                f"🆔 User ID: {target}\n"
                f"📅 Davomiyligi: {months} oy",
                reply_markup=admin_panel_keyboard(),
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    target,
                    f"🎉 Tabriklaymiz!\n\n"
                    f"Sizga {months} oylik Premium obuna berildi!\n\n"
                    f"💎 Endi siz majburiy kanallarga obuna bo'lmasdan kinolardan foydalanishingiz mumkin."
                )
            except:
                pass
                
        except Exception as exc:
            logger.error("Premium berishda xatolik: %s", exc)
            await update.message.reply_text("❌ Premium berishda xatolik yuz berdi.")
        return

    if mode == "remove_premium_id":
        user_input = update.message.text.strip()
        if not user_input:
            return await update.message.reply_text("⚠️ ID kiriting.")
        
        try:
            target_user_id = int(user_input)
        except ValueError:
            return await update.message.reply_text("⚠️ Noto'g'ri ID format. Raqam kiriting.")
        
        try:
            remove_user_premium(target_user_id)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Premium o'chirildi!\n\n"
                f"🆔 User ID: {target_user_id}",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Premium o'chirishda xatolik: %s", exc)
            await update.message.reply_text("❌ Premium o'chirishda xatolik yuz berdi.")
        return

    if mode == "broadcast":
        return await broadcast_message(update, context)

    return await handle_user_code(update, context)


async def handle_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media for broadcast only - file_id orqali qabul qilamiz"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    mode = context.user_data.get("admin_mode")

    if mode == "broadcast":
        return await broadcast_message(update, context)
    
    # Kino qo'shish uchun file_id matn sifatida yuborilishi kerak
    return


async def send_movie_by_code(chat_id, code, context: ContextTypes.DEFAULT_TYPE):
    movie = get_movie(code)
    if not movie:
        await context.bot.send_message(
            chat_id,
            f"⚠️ Bunday koddagi kino topilmadi.\n🆔 Kod: {code}",
            reply_markup=not_found_keyboard(),
        )
        return
    await send_movie_to_chat(chat_id, movie, code, context)


async def send_movie_to_chat(chat_id, movie, code, context: ContextTypes.DEFAULT_TYPE):
    name = movie.get('name') or movie.get('desc', 'Nom mavjud emas')
    caption = (
        f"🎬 {name}\n\n"
        f"🆔 Kod: {code}\n"
        f"📝 {movie.get('desc', '')}\n"
        f"📥 Yuklab olingan: {movie.get('views', 0) + 1}\n\n"
        f"@PrimeKin0Bot - 🎬 Eng zo'r kino va seriallar shu yerda"
    )

    try:
        # Faqat video sifatida yuborish
        await context.bot.send_video(chat_id, movie["file_id"], caption=caption)
        increment_views(code)

    except Exception as exc:
        logger.error("Kontentni yuborishda xatolik: %s", exc)
        await context.bot.send_message(
            chat_id,
            "❌ Kontentni yuborishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.",
        )


async def handle_user_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    code = update.message.text.strip().upper()
    if not code:
        return await update.message.reply_text("⚠️ Kod bo'sh bo'lmasligi kerak.")

    if not is_admin(update.effective_user.id):
        subscribed = await is_user_subscribed(update.effective_user.id, context)
        if not subscribed:
            context.user_data["pending_code"] = code
            await update.message.reply_text(
                "📢 Kino olishdan oldin kanalga a'zo bo'ling yoki Premium sotib oling.",
                reply_markup=force_sub_keyboard(),
            )
            return

    movie = get_movie(code)
    if movie:
        return await send_movie_to_chat(update.effective_chat.id, movie, code, context)

    children = get_children(code)
    if children:
        text = "📺 Qismlar ro'yxati (eski → yangi):\n\n"
        for idx, item in enumerate(children, start=1):
            name = item['name'] or item['desc']
            text += f"{idx}. {name} | 👁️ {item['views']} - 🆔 {item['code']}\n"
            if idx == 9:
                text += "\n📢 @primekin0 kanaliga obuna bo'ling.\n\n"
        await update.message.reply_text(
            text, reply_markup=numbered_keyboard(children)
        )
        return

    await send_movie_by_code(update.effective_chat.id, code, context)


async def random_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_random_movies(15)
    if not rows:
        return await update.message.reply_text("⚠️ Hozircha kino yo'q.")

    text = "🎲 Tasodifiy kinolar:\n\n"
    for idx, item in enumerate(rows, start=1):
        name = item['name'] or item['desc']
        text += f"{idx}. {name} | 👁️ {item['views']} - 🆔 {item['code']}\n"
        if idx == 9:
            text += "\n📢 @primekin0 kanaliga obuna bo'ling.\n\n"

    await update.message.reply_text(
        text, reply_markup=numbered_keyboard(rows)
    )


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    user_ids = get_all_user_ids()
    if not user_ids:
        context.user_data["admin_mode"] = None
        return await update.message.reply_text("⚠️ Foydalanuvchilar topilmadi.")

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
        f"✅ Broadcast yakunlandi.\n📤 Yuborildi: {sent}\n❌ Xatolik: {failed}"
    )


async def handle_other_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    await update.message.reply_text(
        "🔍 Kino topish uchun kod yuboring yoki menyudan foydalaning.",
        reply_markup=main_menu_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    return await handle_admin_text(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN .env faylida yo'q.")
    if not ADMIN_IDS:
        logger.warning("⚠️ ADMIN_IDS .env faylida yo'q. Hech kim admin bo'lmaydi!")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("rand", random_movies))
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

    logger.info("🚀 Bot ishga tushdi...")
    logger.info(f"👥 Adminlar: {ADMIN_IDS}")
    app.run_polling()


if __name__ == "__main__":
    main()