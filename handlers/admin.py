from __future__ import annotations

import asyncio
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import BROADCAST_CHUNK_SIZE, BROADCAST_CONCURRENCY, MOVIE_LIST_LIMIT
from handlers import common, user as user_handlers
from keyboards import (
    admin_delete_channels_keyboard,
    admin_delete_movies_keyboard,
    admin_panel_keyboard,
    edit_fields_keyboard,
    premium_prices_keyboard,
)
from logging_conf import get_logger
from repositories import force_channels, movies, users

logger = get_logger(__name__)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users.upsert_user(update.effective_user)
    user_id = update.effective_user.id

    if not common.is_admin(user_id):
        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q.\n\n"
            "Agar admin bo'lmoqchi bo'lsangiz, bot egasi bilan bog'laning."
        )
        return

    await update.message.reply_text("✅ Admin paneli:", reply_markup=admin_panel_keyboard())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    logger.info("Callback received: %s", query.data if query else "none")
    await query.answer()
    users.upsert_user(query.from_user)
    user_id = query.from_user.id
    data = query.data

    if data.startswith("pick:") or data.startswith("pick_"):
        return await user_handlers.handle_pick_callback(update, context)

    if data == "check_sub":
        return await common.handle_check_sub(update, context)
    if data == "search_movie":
        return await common.search_movie(update, context)
    if data == "contact_admin":
        return await common.contact_admin(update, context)
    if data == "main_menu":
        return await common.main_menu(update, context)
    if data == "random_movies":
        return await user_handlers.handle_random_movies(update, context)

    if data == "buy_premium":
        await common.safe_edit_or_send(
            query,
            context,
            "💎 Premium obuna\n\n"
            "Premium foydalanuvchilar uchun imtiyozlar:\n"
            "✅ Majburiy kanallarga obuna bo'lmasdan kinolar\n"
            "✅ Reklama yo'q\n"
            "✅ Yangi kinolar birinchi bo'lib\n\n"
            "Narxlarni tanlang:",
            reply_markup=premium_prices_keyboard(),
        )
        return

    if data.startswith("premium:"):
        months = int(data.split(":", 1)[1])
        prices = {1: 5000, 3: 14000, 6: 27000, 12: 50000}
        price = prices.get(months, 5000)
        premium_actions = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📞 Admin", callback_data="contact_admin")],
                [InlineKeyboardButton("◀️ Orqaga", callback_data="buy_premium")],
            ]
        )
        await common.safe_edit_or_send(
            query,
            context,
            f"💎 Premium obuna - {months} oy\n\n"
            f"💰 Narx: {price:,} so'm\n\n"
            f"To'lov uchun admin bilan bog'laning:\n"
            f"🆔 Sizning ID: {user_id}\n\n"
            "To'lov qilgandan keyin adminlarga xabar bering.",
            reply_markup=premium_actions,
        )
        return

    if data.startswith("premium_price_"):
        months = int(data.split("_")[2])
        prices = {1: 5000, 3: 14000, 6: 27000, 12: 50000}
        price = prices.get(months, 5000)
        premium_actions = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📞 Admin", callback_data="contact_admin")],
                [InlineKeyboardButton("◀️ Orqaga", callback_data="buy_premium")],
            ]
        )
        await common.safe_edit_or_send(
            query,
            context,
            f"💎 Premium obuna - {months} oy\n\n"
            f"💰 Narx: {price:,} so'm\n\n"
            f"To'lov uchun admin bilan bog'laning:\n"
            f"🆔 Sizning ID: {user_id}\n\n"
            "To'lov qilgandan keyin adminlarga xabar bering.",
            reply_markup=premium_actions,
        )
        return

    if not common.is_admin(user_id):
        await common.safe_edit_or_send(query, context, "⚠️ Bu bo'lim faqat adminlar uchun.")
        return

    if data == "add_movie":
        context.user_data["admin_mode"] = "add_code"
        await common.safe_edit_or_send(query, context, "📝 Yangi kino kodi (masalan: A123):")
        return

    if data == "edit_movie":
        context.user_data["admin_mode"] = "edit_code"
        context.user_data.pop("edit_code", None)
        await common.safe_edit_or_send(
            query, context, "✏️ Tahrirlamoqchi bo'lgan kino kodini kiriting:"
        )
        return

    if data == "delete_movie":
        context.user_data["admin_mode"] = "delete"
        rows = movies.list_movies()
        if not rows:
            await common.safe_edit_or_send(query, context, "⚠️ Hozircha kino yo'q.")
            return
        await common.safe_edit_or_send(
            query,
            context,
            "🗑 O'chirmoqchi bo'lgan kino kodini tanlang:",
            reply_markup=admin_delete_movies_keyboard(rows),
        )
        return

    if data.startswith("delmovie:") or data.startswith("delete_"):
        if data.startswith("delmovie:"):
            code = data.split(":", 1)[1]
        else:
            code = data.replace("delete_", "", 1)
        deleted = movies.delete_movie(code)
        if deleted:
            await common.safe_edit_or_send(query, context, f"✅ Kino o'chirildi: {code}")
        else:
            await common.safe_edit_or_send(query, context, "⚠️ Bunday kod topilmadi.")
        return

    if data == "list_movies":
        rows = movies.list_movies()
        if not rows:
            await common.safe_edit_or_send(query, context, "⚠️ Hozircha kino yo'q.")
            return
        text = "📋 Kinolar ro'yxati (yangi → eski):\n\n"
        for item in rows[:MOVIE_LIST_LIMIT]:
            name = item.name or (item.desc[:30] if item.desc else "")
            text += f"🆔 {item.code} - {name} | 👁️ {item.views}\n"
        if len(rows) > MOVIE_LIST_LIMIT:
            text += f"\n...va yana {len(rows) - MOVIE_LIST_LIMIT} ta kino"
        await common.safe_edit_or_send(query, context, text)
        return

    if data == "admin_stats":
        total, counts = movies.movie_stats()
        user_count = users.get_user_count()
        premium_stats = users.get_premium_stats()
        stats_text = (
            "📊 Admin statistikasi\n\n"
            f"👥 Foydalanuvchilar: {user_count}\n"
            f"💎 Premium: {premium_stats.premium_count}\n"
            f"📁 Jami kinolar: {total}\n"
            f"🎥 Videolar: {counts.get('video', 0)}\n"
            f"📄 Hujjatlar: {counts.get('document', 0)}\n"
            f"🖼 Rasmlar: {counts.get('photo', 0)}\n"
            f"📝 Matnlar: {counts.get('text', 0)}"
        )
        await common.safe_edit_or_send(query, context, stats_text)
        return

    if data == "user_stats":
        premium_stats = users.get_premium_stats()
        await common.safe_edit_or_send(
            query,
            context,
            "👥 Foydalanuvchilar statistikasi\n\n"
            f"Jami foydalanuvchilar: {premium_stats.total_count}\n"
            f"💎 Premium foydalanuvchilar: {premium_stats.premium_count}\n"
            f"👤 Oddiy foydalanuvchilar: {premium_stats.total_count - premium_stats.premium_count}",
        )
        return

    if data == "give_premium":
        context.user_data["admin_mode"] = "give_premium_id"
        await common.safe_edit_or_send(
            query,
            context,
            "💎 Premium berish\n\n"
            "Foydalanuvchi ID yoki username kiriting:\n"
            "Masalan: 123456789 yoki @username",
        )
        return

    if data == "remove_premium":
        context.user_data["admin_mode"] = "remove_premium_id"
        await common.safe_edit_or_send(
            query,
            context,
            "🚫 Premium olish\n\n"
            "Foydalanuvchi ID kiriting:\n"
            "Masalan: 123456789",
        )
        return

    if data == "add_channel":
        context.user_data["admin_mode"] = "add_channel_id"
        await common.safe_edit_or_send(
            query,
            context,
            "📢 Majburiy kanal ID'sini kiriting:\n\n"
            "Masalan: @primekin0 yoki -1001234567890",
        )
        return

    if data == "delete_channel":
        channels = force_channels.get_force_channels()
        if not channels:
            await common.safe_edit_or_send(query, context, "⚠️ Majburiy kanallar yo'q.")
            return
        await common.safe_edit_or_send(
            query,
            context,
            "🗑 O'chirmoqchi bo'lgan kanalni tanlang:",
            reply_markup=admin_delete_channels_keyboard(channels),
        )
        return

    if data.startswith("delchan:") or data.startswith("delchan_"):
        if data.startswith("delchan:"):
            channel_id = int(data.split(":", 1)[1])
            removed = force_channels.remove_force_channel_by_id(channel_id)
        else:
            encoded_id = data.replace("delchan_", "", 1)
            channel_id = urllib.parse.unquote(encoded_id)
            removed = force_channels.remove_force_channel_by_channel_id(channel_id)
        if removed:
            await common.safe_edit_or_send(
                query,
                context,
                "✅ Kanal o'chirildi.",
                reply_markup=admin_panel_keyboard(),
            )
        else:
            await common.safe_edit_or_send(
                query,
                context,
                "⚠️ Kanal topilmadi.",
                reply_markup=admin_panel_keyboard(),
            )
        return

    if data == "broadcast":
        context.user_data["admin_mode"] = "broadcast"
        await common.safe_edit_or_send(
            query, context, "📢 Broadcast uchun xabar yuboring (matn yoki media)."
        )
        return

    if data == "back_to_admin":
        await common.safe_edit_or_send(query, context, "⚙️ Admin paneli:", admin_panel_keyboard())
        return

    if data.startswith("editfield:"):
        field = data.split(":", 1)[1]
        edit_code = context.user_data.get("edit_code")
        if not edit_code:
            context.user_data["admin_mode"] = "edit_code"
            await common.safe_edit_or_send(
                query,
                context,
                "⚠️ Avval kino kodini kiriting:",
            )
            return
        context.user_data["admin_mode"] = "edit_value"
        context.user_data["edit_field"] = field

        hint = "Yangi qiymatni yuboring:"
        if field == "type":
            hint = "Kino turi (video, document, photo yoki text):"
        elif field == "parent_code":
            hint = "Parent kod (bo'sh qilish uchun '-' yuboring):"

        await common.safe_edit_or_send(query, context, f"✏️ {hint}")
        return


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not common.is_admin(user_id):
        return await user_handlers.handle_user_code(update, context)

    mode = context.user_data.get("admin_mode")

    if mode == "add_code":
        code = common.normalize_code(update.message.text)
        if not code:
            await update.message.reply_text("⚠️ Kod bo'sh bo'lmasligi kerak.")
            return
        if movies.get_movie(code):
            await update.message.reply_text(
                "⚠️ Bu kod allaqachon mavjud. Boshqa kod kiriting."
            )
            return
        context.user_data["new_code"] = code
        context.user_data["admin_mode"] = "add_name"
        await update.message.reply_text("📝 Kino nomini yozing:")
        return

    if mode == "add_name":
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("⚠️ Nom bo'sh bo'lmasligi kerak.")
            return
        context.user_data["new_name"] = name
        context.user_data["admin_mode"] = "add_desc"
        await update.message.reply_text("📝 Kino tavsifini yozing:")
        return

    if mode == "add_desc":
        desc = update.message.text.strip()
        if not desc:
            await update.message.reply_text("⚠️ Tavsif bo'sh bo'lmasligi kerak.")
            return
        context.user_data["new_desc"] = desc
        context.user_data["admin_mode"] = "add_parent"
        await update.message.reply_text(
            "🎬 Agar serial bo'lsa, asosiy kodini yuboring. Aks holda '-' yuboring:"
        )
        return

    if mode == "add_parent":
        raw_parent = update.message.text.strip()
        if raw_parent == "-" or not raw_parent:
            parent_code = None
        else:
            parent_code = common.normalize_code(raw_parent)
        context.user_data["new_parent"] = parent_code
        context.user_data["admin_mode"] = "add_file"
        await update.message.reply_text(
            "📤 Endi videoni (yoki hujjat ko'rinishidagi videoni) yuboring.\n\n"
            "Bot file_id ni o'zi ajratib oladi."
        )
        return

    if mode == "add_file":
        await update.message.reply_text("⚠️ Iltimos, video fayl yuboring.")
        return

    if mode == "delete":
        code = common.normalize_code(update.message.text)
        deleted = movies.delete_movie(code)
        context.user_data["admin_mode"] = None
        if deleted:
            await update.message.reply_text(f"✅ Kino o'chirildi: {code}")
        else:
            await update.message.reply_text("⚠️ Bunday kod topilmadi.")
        return

    if mode == "edit_code":
        code = common.normalize_code(update.message.text)
        if not code:
            await update.message.reply_text("⚠️ Kod bo'sh bo'lmasligi kerak.")
            return
        movie = movies.get_movie(code)
        if not movie:
            await update.message.reply_text("⚠️ Bunday kod topilmadi.")
            return
        context.user_data["edit_code"] = code
        context.user_data["admin_mode"] = "edit_field"
        await update.message.reply_text(
            "✏️ Qaysi maydonni tahrirlamoqchisiz?", reply_markup=edit_fields_keyboard()
        )
        return

    if mode == "edit_value":
        edit_code = context.user_data.get("edit_code")
        field = context.user_data.get("edit_field")
        if not edit_code or not field:
            context.user_data["admin_mode"] = None
            await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")
            return

        new_value = update.message.text.strip()
        if field in {"name", "desc", "file_id"} and not new_value:
            await update.message.reply_text("⚠️ Qiymat bo'sh bo'lmasligi kerak.")
            return

        if field == "type":
            new_value = new_value.lower()
            if new_value not in {"video", "document", "photo", "text"}:
                await update.message.reply_text(
                    "⚠️ Turi noto'g'ri. video, document, photo yoki text kiriting."
                )
                return
        elif field == "parent_code":
            if not new_value or new_value in {"-", "none", "null"}:
                new_value = None
            else:
                new_value = common.normalize_code(new_value)

        try:
            updated = movies.update_movie_field(edit_code, field, new_value)
            if not updated:
                await update.message.reply_text("⚠️ Kino topilmadi.")
            else:
                await update.message.reply_text(
                    f"✅ Kino yangilandi!\n\n🆔 Kod: {edit_code}\n🔧 Maydon: {field}",
                    reply_markup=admin_panel_keyboard(),
                )
            context.user_data["admin_mode"] = None
            context.user_data.pop("edit_field", None)
            return
        except Exception as exc:
            logger.error("Kino tahrirlashda xatolik: %s", exc)
            await update.message.reply_text("❌ Kino tahrirlashda xatolik yuz berdi.")
            return

    if mode == "add_channel_id":
        channel_id = update.message.text.strip()
        if not channel_id:
            await update.message.reply_text("⚠️ Kanal ID bo'sh bo'lmasligi kerak.")
            return
        context.user_data["new_channel_id"] = channel_id
        context.user_data["admin_mode"] = "add_channel_link"
        await update.message.reply_text(
            "🔗 Kanal linkini kiriting:\n\nMasalan: https://t.me/primekin0"
        )
        return

    if mode == "add_channel_link":
        channel_link = update.message.text.strip()
        if not channel_link:
            await update.message.reply_text("⚠️ Link bo'sh bo'lmasligi kerak.")
            return
        channel_id = context.user_data.get("new_channel_id")
        if not channel_id:
            context.user_data["admin_mode"] = None
            await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")
            return
        try:
            force_channels.add_force_channel(channel_id, channel_link)
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
            await update.message.reply_text("⚠️ ID yoki username kiriting.")
            return
        if user_input.startswith("@"):
            context.user_data["premium_target"] = user_input
        else:
            try:
                context.user_data["premium_target"] = int(user_input)
            except ValueError:
                await update.message.reply_text(
                    "⚠️ Noto'g'ri ID format. Raqam yoki @username kiriting."
                )
                return
        context.user_data["admin_mode"] = "give_premium_months"
        await update.message.reply_text(
            "📅 Necha oyga premium bermoqchisiz?\n\nMasalan: 1, 3, 6, 12"
        )
        return

    if mode == "give_premium_months":
        try:
            months = int(update.message.text.strip())
            if months < 1 or months > 120:
                await update.message.reply_text("⚠️ 1 dan 120 oygacha kiriting.")
                return
        except ValueError:
            await update.message.reply_text("⚠️ Raqam kiriting.")
            return

        target = context.user_data.get("premium_target")
        if not target:
            context.user_data["admin_mode"] = None
            await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")
            return

        if isinstance(target, str) and target.startswith("@"):
            await update.message.reply_text(
                "⚠️ Username orqali qo'shish hozircha qo'llab-quvvatlanmaydi.\n"
                "Iltimos, foydalanuvchi ID'sini kiriting.\n\n"
                "User o'zini /start qilsa, ID ni olishingiz mumkin."
            )
            context.user_data["admin_mode"] = None
            return

        try:
            users.set_user_premium(int(target), months)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Premium berildi!\n\n"
                f"🆔 User ID: {target}\n"
                f"📅 Davomiyligi: {months} oy",
                reply_markup=admin_panel_keyboard(),
            )
            try:
                await context.bot.send_message(
                    int(target),
                    "🎉 Tabriklaymiz!\n\n"
                    f"Sizga {months} oylik Premium obuna berildi!\n\n"
                    "💎 Endi siz majburiy kanallarga obuna bo'lmasdan kinolardan foydalanishingiz mumkin.",
                )
            except Exception:
                pass
        except Exception as exc:
            logger.error("Premium berishda xatolik: %s", exc)
            await update.message.reply_text("❌ Premium berishda xatolik yuz berdi.")
        return

    if mode == "remove_premium_id":
        user_input = update.message.text.strip()
        if not user_input:
            await update.message.reply_text("⚠️ ID kiriting.")
            return
        try:
            target_user_id = int(user_input)
        except ValueError:
            await update.message.reply_text("⚠️ Noto'g'ri ID format. Raqam kiriting.")
            return
        try:
            users.remove_user_premium(target_user_id)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Premium o'chirildi!\n\n🆔 User ID: {target_user_id}",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Premium o'chirishda xatolik: %s", exc)
            await update.message.reply_text("❌ Premium o'chirishda xatolik yuz berdi.")
        return

    if mode == "broadcast":
        await broadcast_message(update, context)
        return

    await user_handlers.handle_user_code(update, context)


async def handle_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not common.is_admin(user_id):
        return

    mode = context.user_data.get("admin_mode")
    if mode == "add_file":
        message = update.message
        file_id = None
        content_type = None
        if message.video:
            file_id = message.video.file_id
            content_type = "video"
        elif message.document:
            file_id = message.document.file_id
            content_type = "document"

        if not file_id or not content_type:
            await update.message.reply_text("⚠️ Iltimos, video fayl yuboring.")
            return

        code = context.user_data.get("new_code")
        name = context.user_data.get("new_name")
        desc = context.user_data.get("new_desc")
        parent_code = context.user_data.get("new_parent")

        if not code or not name or not desc:
            context.user_data["admin_mode"] = None
            await update.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan boshlang.")
            return

        try:
            movies.add_movie(code, name, content_type, file_id, desc, parent_code)
            context.user_data["admin_mode"] = None
            await update.message.reply_text(
                f"✅ Kino qo'shildi!\n\n"
                f"🆔 Kod: {code}\n"
                f"📝 Nom: {name}\n"
                f"📄 Tavsif: {desc}\n"
                f"📁 Turi: {content_type}",
                reply_markup=admin_panel_keyboard(),
            )
        except Exception as exc:
            logger.error("Kino qo'shishda xatolik: %s", exc)
            await update.message.reply_text("❌ Kino qo'shishda xatolik yuz berdi.")
        return

    if mode == "broadcast":
        await broadcast_message(update, context)
        return


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not common.is_admin(update.effective_user.id):
        return

    user_ids = users.get_all_user_ids()
    if not user_ids:
        context.user_data["admin_mode"] = None
        await update.message.reply_text("⚠️ Foydalanuvchilar topilmadi.")
        return

    context.user_data["admin_mode"] = None
    source_chat_id = update.effective_chat.id
    source_message_id = update.message.message_id

    sent = 0
    failed = 0
    semaphore = asyncio.Semaphore(BROADCAST_CONCURRENCY)

    async def send_one(uid: int) -> bool:
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

    for i in range(0, len(user_ids), BROADCAST_CHUNK_SIZE):
        chunk = user_ids[i : i + BROADCAST_CHUNK_SIZE]
        results = await asyncio.gather(*(send_one(uid) for uid in chunk))
        sent += sum(1 for r in results if r)
        failed += sum(1 for r in results if not r)

    await update.message.reply_text(
        f"✅ Broadcast yakunlandi.\n📤 Yuborildi: {sent}\n❌ Xatolik: {failed}"
    )
