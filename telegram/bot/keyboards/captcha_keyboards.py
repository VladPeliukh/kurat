from typing import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class CaptchaKeyboards:
    """Фабрика клавиатур, связанных с капчей."""

    @staticmethod
    def options(options: Iterable[int]) -> InlineKeyboardMarkup:
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
