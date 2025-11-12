from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Iterable


def captcha_options_keyboard(options: Iterable[int]) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответов для капчи."""

    rows = []
    row: list[InlineKeyboardButton] = []
    for index, value in enumerate(options, start=1):
        row.append(
            InlineKeyboardButton(text=str(value), callback_data=f"cur_cap:{value}")
        )
        if index % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
