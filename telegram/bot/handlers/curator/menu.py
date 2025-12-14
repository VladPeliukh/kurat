import html

from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...keyboards import CuratorKeyboards
from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    CURATOR_PARTNERS_PAGE_SIZE,
    is_private_chat,
    render_partners_list,
    require_curator_or_admin_callback,
    require_curator_or_admin_message,
    send_curator_personal_link,
)
from . import router
from .state import pending_curator_messages


@router.message(Command("menu"))
async def show_curator_menu(message: Message) -> None:
    if not is_private_chat(message):
        return
    svc = CuratorService(message.bot)
    if not await require_curator_or_admin_message(message, svc):
        return
    pending_curator_messages.pop(message.from_user.id, None)
    await message.answer(
        "Основное меню",
        reply_markup=CuratorKeyboards.main_menu(),
    )


@router.callback_query(F.data == "cur_menu:open")
async def curator_menu_open(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    pending_curator_messages.pop(call.from_user.id, None)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await call.message.answer(
            "Основное мню",
            reply_markup=CuratorKeyboards.main_menu(),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "cur_menu:back")
async def curator_menu_back(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    pending_curator_messages.pop(call.from_user.id, None)
    keyboard = CuratorKeyboards.main_menu()
    try:
        await call.message.edit_text("Основное меню", reply_markup=keyboard)
    except Exception:
        await call.message.answer("Основное меню", reply_markup=keyboard)
    await call.answer()


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
