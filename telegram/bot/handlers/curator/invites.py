from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    is_private_chat,
    require_curator_or_admin_callback,
    require_curator_or_admin_message,
    send_curator_personal_link,
)
from . import router
from .state import pending_curator_messages


@router.callback_query(F.data == "cur_menu:invite")
async def curator_show_invite(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    if call.message is None:
        await call.answer("Не удалось отправить ссылку.", show_alert=True)
        return
    pending_curator_messages.pop(call.from_user.id, None)
    await send_curator_personal_link(
        call.message,
        svc,
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
    )
    await call.answer()


@router.message(Command("invite"))
async def handle_invite(message: Message) -> None:
    if not is_private_chat(message):
        return
    svc = CuratorService(message.bot)
    if not await require_curator_or_admin_message(message, svc):
        return
    await send_curator_personal_link(
        message,
        svc,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
