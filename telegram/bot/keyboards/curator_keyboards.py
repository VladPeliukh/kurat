from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CuratorKeyboards:
    """Фабрика клавиатур, используемых кураторами."""

    @staticmethod
    def request(partner_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для одобрения или отклонения заявки нового куратора."""

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Принять", callback_data=f"cur_acc:{partner_id}"
                    ),
                    InlineKeyboardButton(
                        text="Отклонить", callback_data=f"cur_dec:{partner_id}"
                    ),
                ]
            ]
        )

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="Ваша ссылка", callback_data="cur_menu:invite")
        builder.button(text="Приглашенные пользователи", callback_data="cur_menu:partners")
        builder.button(text="Посмотреть свою статистику", callback_data="cur_menu:stats")
        builder.button(
            text="Посмотреть статистику за все время",
            callback_data="cur_menu:stats_all",
        )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def invite() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Ваше меню куратора", callback_data="cur_menu:open"
                    )
                ]
            ]
        )

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="В меню куратора", callback_data="cur_menu:open")]
            ]
        )

    @staticmethod
    def cancel_message() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отменить", callback_data="cur_msg:cancel")]
            ]
        )

    @staticmethod
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

    @staticmethod
    def _sanitize_offset(offset: int, total: int, page_size: int) -> int:
        if offset < 0:
            return 0
        if offset >= total:
            if total == 0:
                return 0
            return max(0, total - page_size)
        return offset

    @classmethod
    def partners(
        cls, partners: list[dict], *, offset: int = 0, page_size: int = 10
    ) -> InlineKeyboardMarkup:
        total = len(partners)
        offset = cls._sanitize_offset(offset, total, page_size)

        builder = InlineKeyboardBuilder()
        for partner in partners[offset : offset + page_size]:
            user_id = partner.get("user_id")
            if not user_id:
                continue
            title = cls.format_partner_title(partner)
            if len(title) > 64:
                title = title[:61] + "..."
            builder.row(
                InlineKeyboardButton(text=title, callback_data=f"cur_partner:{user_id}"),
                width=1,
            )

        navigation_buttons: list[InlineKeyboardButton] = []
        if offset > 0:
            prev_offset = max(0, offset - page_size)
            navigation_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Обратно", callback_data=f"cur_partners_page:{prev_offset}"
                )
            )
        if offset + page_size < total:
            next_offset = offset + page_size
            navigation_buttons.append(
                InlineKeyboardButton(
                    text="➡️ Далее", callback_data=f"cur_partners_page:{next_offset}"
                )
            )
        if navigation_buttons:
            builder.row(*navigation_buttons, width=len(navigation_buttons))

        builder.row(
            InlineKeyboardButton(text="↩️ Назад", callback_data="cur_menu:back"),
            width=1,
        )
        return builder.as_markup()


