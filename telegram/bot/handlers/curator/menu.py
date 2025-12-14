from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...keyboards import CuratorKeyboards
from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    is_private_chat,
    require_curator_or_admin_callback,
    require_curator_or_admin_message,
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
