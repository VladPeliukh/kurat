from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AdminKeyboards:
    """Фабрика клавиатур, используемых администраторами."""

    @staticmethod
    def main_menu(is_super_admin: bool = False) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Посмотреть статистику куратора",
            callback_data="adm_menu:curator_stats",
        )
        builder.button(
            text="Информация о кураторе",
            callback_data="adm_menu:curator_info",
        )
        if is_super_admin:
            builder.button(
                text="Рассылка",
                callback_data="adm_menu:broadcast",
            )
            builder.button(
                text="Назначить админа",
                callback_data="adm_menu:promote_admin",
            )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def back_to_admin_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="В меню администратора", callback_data="adm_menu:open")]
            ]
        )

