import html

from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...keyboards import CuratorKeyboards
from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    is_private_chat,
    require_curator_or_admin_callback,
)
from . import router
from .state import pending_curator_messages


@router.callback_query(F.data == "cur_msg:cancel")
async def cancel_curator_message(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    active = pending_curator_messages.pop(call.from_user.id, None)
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    if active is None:
        await call.answer("Нет активного действия.", show_alert=True)
        return
    if call.message:
        try:
            await call.message.answer("Действие отменено.")
        except Exception:
            pass
    await call.answer()


@router.message(Command("cancel"))
async def cancel_curator_action(message: Message) -> None:
    if not is_private_chat(message):
        return
    if pending_curator_messages.pop(message.from_user.id, None) is not None:
        await message.answer("Действие отменено.")
    else:
        await message.answer("Нет активного действия.")


@router.message(F.text)
async def handle_curator_outgoing_message(message: Message) -> None:
    if not is_private_chat(message):
        return
    partner_id = pending_curator_messages.get(message.from_user.id)
    if not partner_id:
        return
    trimmed = message.text.strip()
    if trimmed == "/cancel":
        return
    if trimmed.startswith("/"):
        return
    if not trimmed:
        await message.answer("Пожалуйста, отправьте текстовое сообщение или нажмите кнопку «Отменить».")
        return
    svc = CuratorService(message.bot)
    if not await svc.is_partner(message.from_user.id, partner_id):
        pending_curator_messages.pop(message.from_user.id, None)
        await message.answer("Этот пользователь больше не связан с вами.")
        return
    curator_name = html.escape(message.from_user.full_name or "Зарегестрированны пользователь")
    text = html.escape(message.text)
    body = f"Сообщение от пользователя, который вас пригласил {curator_name}:\n\n{text}"
    try:
        await message.bot.send_message(partner_id, body)
    except Exception:
        await message.answer("Не удалось отправить сообщение этому пользователю.")
    else:
        await message.answer(
            "Сообщение отправлено.",
            reply_markup=CuratorKeyboards.back_to_menu(),
        )
    finally:
        pending_curator_messages.pop(message.from_user.id, None)
