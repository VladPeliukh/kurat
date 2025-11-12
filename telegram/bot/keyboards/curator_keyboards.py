from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def curator_request_keyboard(partner_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для одобрения или отклонения заявки нового куратора."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Принять", callback_data=f"cur_acc:{partner_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"cur_dec:{partner_id}"),
            ]
        ]
    )


def curator_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Приглашенные пользователи", callback_data="cur_menu:partners")
    builder.adjust(1)
    return builder.as_markup()


def format_partner_title(partner: dict) -> str:
    user_id = partner.get("user_id")
    full_name = (partner.get("full_name") or "").strip()
    username = (partner.get("username") or "").strip()
    if username.startswith("@"):
        username = username[1:]
    handle = f"@{username}" if username else ""

    if handle:
        secondary = full_name or "—"
        if secondary == handle:
            return handle
        return f"{handle} ({secondary})"
    if full_name:
        return full_name
    if user_id:
        return f"ID {user_id}"
    return "Неизвестный пользователь"


def curator_partners_keyboard(partners: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for partner in partners:
        user_id = partner.get("user_id")
        if not user_id:
            continue
        title = format_partner_title(partner)
        if len(title) > 64:
            title = title[:61] + "..."
        builder.button(text=title, callback_data=f"cur_partner:{user_id}")
    builder.button(text="↩️ Назад", callback_data="cur_menu:back")
    builder.adjust(1)
    return builder.as_markup()
