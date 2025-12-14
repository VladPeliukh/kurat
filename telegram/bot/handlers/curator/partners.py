import html

from aiogram import F
from aiogram.types import CallbackQuery

from ...keyboards import CuratorKeyboards
from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    CURATOR_PARTNERS_PAGE_SIZE,
    render_partners_list,
    require_curator_or_admin_callback,
)
from . import router
from .state import pending_curator_messages


@router.callback_query(F.data == "cur_menu:partners")
async def curator_show_partners(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    partners = await svc.list_partners(call.from_user.id)
    if not partners:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    text = (
        "Ваши приглашенные пользователи.\n"
        "Выберите пользователя, чтобы написать ему сообщение."
    )
    await render_partners_list(
        call,
        partners,
        offset=0,
        text=text,
        keyboard_builder=CuratorKeyboards.partners,
    )


@router.callback_query(F.data.startswith("cur_partners_page:"))
async def curator_partners_next_page(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    try:
        offset = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        offset = CURATOR_PARTNERS_PAGE_SIZE
    else:
        offset = max(0, offset)
    partners = await svc.list_partners(call.from_user.id)
    if not partners:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    text = (
        "Ваши приглашенные пользователи.\n"
        "Выберите пользователя, чтобы написать ему сообщение."
    )
    await render_partners_list(
        call,
        partners,
        offset=offset,
        text=text,
        keyboard_builder=CuratorKeyboards.partners,
    )


@router.callback_query(F.data.startswith("cur_partner:"))
async def curator_message_prompt(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    try:
        partner_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Не удалось определить пользователя.", show_alert=True)
        return
    if not await svc.is_partner(call.from_user.id, partner_id):
        await call.answer("Этот пользователь больше не связан с вами.", show_alert=True)
        return
    partners = await svc.list_partners(call.from_user.id)
    info = next((p for p in partners if p.get("user_id") == partner_id), None)
    display_name = CuratorKeyboards.format_partner_title(info) if info else f"ID {partner_id}"
    pending_curator_messages[call.from_user.id] = partner_id
    prompt = (
        f"Напишите сообщение для {html.escape(display_name)}.\n"
        "Используйте кнопку «Отменить», чтобы прекратить отправку."
    )
    try:
        await call.message.answer(
            prompt,
            reply_markup=CuratorKeyboards.cancel_message(),
        )
    except Exception:
        pass
    await call.answer("Введите сообщение", show_alert=False)
