from __future__ import annotations

from typing import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import SHARE_BOT_USERNAME
from repositories.force_channels import ForceChannel
from repositories.movies import MovieListItem


def _get_item_code(item) -> str:
    return getattr(item, "code", None) or item["code"]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔍 Kod bo'yicha qidirish", callback_data="search_movie"),
                InlineKeyboardButton("🎲 Tasodifiy kinolar", callback_data="random_movies"),
            ],
            [
                InlineKeyboardButton("💎 Premium", callback_data="buy_premium"),
                InlineKeyboardButton("📞 Admin", callback_data="contact_admin"),
            ],
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Kino qo'shish", callback_data="add_movie"),
                InlineKeyboardButton("✏️ Kino tahrirlash", callback_data="edit_movie"),
            ],
            [
                InlineKeyboardButton("🗑 Kino o'chirish", callback_data="delete_movie"),
                InlineKeyboardButton("📋 Kinolar ro'yxati", callback_data="list_movies"),
            ],
            [
                InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
                InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="user_stats"),
            ],
            [
                InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel"),
                InlineKeyboardButton("🗑 Kanal o'chirish", callback_data="delete_channel"),
            ],
            [
                InlineKeyboardButton("💎 Premium berish", callback_data="give_premium"),
                InlineKeyboardButton("🚫 Premium olish", callback_data="remove_premium"),
            ],
            [InlineKeyboardButton("📢 Xabar yuborish", callback_data="broadcast")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
        ]
    )


def not_found_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔍 Boshqa kod", callback_data="search_movie"),
                InlineKeyboardButton("📞 Admin", callback_data="contact_admin"),
            ],
            [InlineKeyboardButton("💎 Premium", callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")],
        ]
    )


def numbered_keyboard(items: Iterable[MovieListItem], prefix: str = "pick") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for idx, item in enumerate(items, start=1):
        code = _get_item_code(item)
        row.append(InlineKeyboardButton(str(idx), callback_data=f"{prefix}:{code}"))
        if idx % 5 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def force_sub_keyboard(channels: Iterable[ForceChannel]) -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"📢 {channel.channel_id} ga qo'shilish", url=channel.channel_link
                )
            ]
        )

    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    buttons.append([InlineKeyboardButton("💎 Premium sotib olish", callback_data="buy_premium")])
    buttons.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def premium_prices_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💎 1 oy - 5,000 so'm", callback_data="premium:1")],
            [InlineKeyboardButton("💎 3 oy - 14,000 so'm", callback_data="premium:3")],
            [InlineKeyboardButton("💎 6 oy - 27,000 so'm", callback_data="premium:6")],
            [InlineKeyboardButton("💎 12 oy - 50,000 so'm", callback_data="premium:12")],
            [InlineKeyboardButton("◀️ Orqaga", callback_data="main_menu")],
        ]
    )


def movie_action_keyboard(code: str, include_menu: bool = True) -> InlineKeyboardMarkup:
    normalized_code = code.upper()
    from urllib.parse import quote

    deep_link = f"https://t.me/{SHARE_BOT_USERNAME}?start=cinema_{normalized_code}"
    share_url = f"https://t.me/share/url?url={quote(deep_link, safe='')}"
    buttons = [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]]
    
    return InlineKeyboardMarkup(buttons)


def admin_delete_movies_keyboard(items: Iterable[MovieListItem]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for idx, item in enumerate(items, start=1):
        code = _get_item_code(item)
        row.append(InlineKeyboardButton(code, callback_data=f"delmovie:{code}"))
        if idx % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(buttons)


def admin_delete_channels_keyboard(channels: Iterable[ForceChannel]) -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"🗑 {channel.channel_id}", callback_data=f"delchan:{channel.id}"
                )
            ]
        )
    buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(buttons)


def edit_fields_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📝 Nom", callback_data="editfield:name"),
                InlineKeyboardButton("📄 Tavsif", callback_data="editfield:desc"),
            ],
            [
                InlineKeyboardButton("📁 File ID", callback_data="editfield:file_id"),
                InlineKeyboardButton("🎞 Turi", callback_data="editfield:type"),
            ],
            [
                InlineKeyboardButton("🔗 Parent kod", callback_data="editfield:parent_code"),
            ],
            [InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_admin")],
        ]
    )
