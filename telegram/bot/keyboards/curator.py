from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
