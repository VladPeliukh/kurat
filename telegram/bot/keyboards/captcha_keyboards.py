from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Iterable


def captcha_options_keyboard(options: Iterable[int]) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответов для капчи."""

    option_list = list(options)
    row_size = 3 if len(option_list) >= 6 else 2

    rows = []
    row: list[InlineKeyboardButton] = []
    for index, value in enumerate(option_list, start=1):
        row.append(
            InlineKeyboardButton(text=str(value), callback_data=f"cur_cap:{value}")
        )
        if index % row_size == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
