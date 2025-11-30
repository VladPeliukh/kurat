from __future__ import annotations

from contextlib import suppress
from typing import Any, Callable, Awaitable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from ..config import Config


class PrimaryGroupOnlyMiddleware(BaseMiddleware):
    def __init__(self, primary_group_id: int | None):
        self.primary_group_id = primary_group_id

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery | ChatMemberUpdated | Any,
        data: dict[str, Any],
    ) -> Any:
        if not self.primary_group_id:
            return await handler(event, data)

        chat = self._get_chat_from_event(event, data)
        if chat and chat.type in {"group", "supergroup"}:
            if chat.id != self.primary_group_id:
                bot: Bot = data["bot"]
                with suppress(Exception):
                    await bot.leave_chat(chat.id)
                return None

        return await handler(event, data)

    @staticmethod
    def _get_chat_from_event(event: Any, data: dict[str, Any]):
        if isinstance(event, Message):
            return event.chat

        if isinstance(event, CallbackQuery):
            return event.message.chat if event.message else None

        if isinstance(event, ChatMemberUpdated):
            return event.chat

        return data.get("event_chat")


primary_group_only_middleware = PrimaryGroupOnlyMiddleware(Config.PRIMARY_GROUP_ID)
