from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AdminKeyboards:
    """Фабрика клавиатур, используемых администраторами."""

    @staticmethod
    def main_menu(
        *, is_super_admin: bool = False, open_invite_enabled: bool | None = None
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Информация о пользователе",
            callback_data="adm_menu:curator_info",
        )
        builder.button(
            text="Посмотреть всю статистику за период",
            callback_data="adm_menu:all_stats",
        )
        builder.button(
            text="Посмотреть всю статистику за все время",
            callback_data="adm_menu:all_stats_all_time",
        )
        if is_super_admin:
            builder.button(
                text="Рассылка всем пользователям",
                callback_data="adm_menu:broadcast",
            )
            builder.button(
                text="Назначить администратора",
                callback_data="adm_menu:promote_admin",
            )
            if open_invite_enabled is not None:
                builder.button(
                    text=(
                        "Отключить приглашение"
                        if open_invite_enabled
                        else "Включить приглашение"
                    ),
                    callback_data="adm_menu:toggle_open_invite",
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

    @staticmethod
    def curator_info_actions(curator_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="Посмотреть статистику этого пользователя",
            callback_data=f"adm_curator_stats:{curator_id}",
        )
        builder.button(
            text="В меню администратора",
            callback_data="adm_menu:open",
        )
        builder.adjust(1)
        return builder.as_markup()

