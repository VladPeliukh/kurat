from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...keyboards import AdminKeyboards
from ...services.curator_service import CuratorService
from .helpers import (
    _is_admin,
    _is_super_admin,
    _is_private_chat,
    is_open_invite_toggle_locked,
    lock_open_invite_toggle,
)
from .router import router


@router.message(Command("admin"))
async def show_admin_menu(message: Message) -> None:
    if not _is_private_chat(message):
        return
    is_super_admin = await _is_super_admin(message.from_user.id)
    if not (is_super_admin or await _is_admin(message.from_user.id)):
        await message.answer("Эта команда доступна только администраторам.")
        return

    open_invite_enabled = None
    if is_super_admin and not is_open_invite_toggle_locked():
        open_invite_enabled = await CuratorService(message.bot).is_open_invite_enabled()

    await message.answer(
        "АДМИН-МЕНЮ",
        reply_markup=AdminKeyboards.main_menu(
            is_super_admin=is_super_admin,
            open_invite_enabled=open_invite_enabled,
        ),
    )


@router.callback_query(F.data == "adm_menu:open")
async def admin_menu_open(call: CallbackQuery) -> None:
    is_super_admin = await _is_super_admin(call.from_user.id)
    if not (is_super_admin or await _is_admin(call.from_user.id)):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await call.message.answer(
            "АДМИН-МЕНЮ",
            reply_markup=AdminKeyboards.main_menu(
                is_super_admin=is_super_admin,
                open_invite_enabled=(
                    await CuratorService(call.bot).is_open_invite_enabled()
                    if is_super_admin and not is_open_invite_toggle_locked()
                    else None
                ),
            ),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "adm_menu:toggle_open_invite")
async def toggle_open_invite(call: CallbackQuery) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return

    if is_open_invite_toggle_locked():
        await call.answer(
            "Повторное включение возможно только после перезапуска бота.",
            show_alert=True,
        )
        return

    svc = CuratorService(call.bot)
    enabled = await svc.is_open_invite_enabled()
    new_value = not enabled
    await svc.set_open_invite_enabled(new_value)

    status = "Автоматическое приглашение включено." if new_value else "Автоматическое приглашение отключено."

    try:
        await call.message.edit_reply_markup(
            reply_markup=AdminKeyboards.main_menu(
                is_super_admin=True,
                open_invite_enabled=None if not new_value else new_value,
            )
        )
    except Exception:
        pass

    if not new_value:
        lock_open_invite_toggle()

    await call.answer(status, show_alert=False)
