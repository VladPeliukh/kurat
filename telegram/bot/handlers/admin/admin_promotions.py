from contextlib import suppress

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommandScopeChat, CallbackQuery, Message

from ...keyboards import AdminKeyboards
from ...services.admin_service import AdminService
from ...services.curator_service import CuratorService
from ...states.admin_states import AdminPromoteAdmin
from ...utils.commands import ADMIN_COMMANDS
from .helpers import _is_super_admin, _is_private_chat
from .router import router


@router.callback_query(F.data == "adm_menu:promote_admin")
async def prompt_promote_admin(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return
    await state.set_state(AdminPromoteAdmin.waiting_curator_id)
    await call.message.answer(
        "Введите ID пользователя, которого нужно сделать администратором.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.message(AdminPromoteAdmin.waiting_curator_id)
async def promote_admin(message: Message, state: FSMContext) -> None:
    if not _is_private_chat(message):
        return
    if not await _is_super_admin(message.from_user.id):
        await message.answer("Эта функция доступна только супер-администратору.")
        await state.clear()
        return

    try:
        curator_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("Пожалуйста, отправьте корректный числовой ID пользователя.")
        return

    curator_service = CuratorService(message.bot)
    if not await curator_service.is_curator(curator_id):
        await message.answer(
            "Пользователь с таким ID не найден.",
            reply_markup=AdminKeyboards.back_to_admin_menu(),
        )
        await state.clear()
        return

    admin_service = AdminService()
    if await admin_service.is_admin(curator_id):
        await message.answer(
            "Этот пользователь уже является администратором.",
            reply_markup=AdminKeyboards.back_to_admin_menu(),
        )
        await state.clear()
        return

    record = await curator_service.get_curator_record(curator_id) or {}
    await admin_service.add_admin(
        user_id=curator_id,
        username=record.get("username"),
        full_name=record.get("full_name"),
        level=1,
    )

    with suppress(Exception):
        await message.bot.send_message(
            curator_id,
            "Вы назначены администратором. Вам доступна команда /admin.",
        )
        await message.bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=curator_id),
        )

    await message.answer(
        "Пользователь назначен администратором.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await state.clear()
