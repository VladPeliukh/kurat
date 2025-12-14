from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...keyboards import AdminKeyboards
from ...services.curator_service import CuratorService
from ...states.admin_states import AdminBroadcast
from .helpers import _is_super_admin, _is_private_chat
from .router import router


@router.callback_query(F.data == "adm_menu:broadcast")
async def prompt_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return
    await state.set_state(AdminBroadcast.waiting_message)
    await call.message.answer(
        "Отправьте сообщение, которое нужно разослать всем пользователям.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.message(AdminBroadcast.waiting_message)
async def broadcast_message(message: Message, state: FSMContext) -> None:
    if not _is_private_chat(message):
        return
    if not await _is_super_admin(message.from_user.id):
        await message.answer("Эта функция доступна только супер-администратору.")
        await state.clear()
        return

    svc = CuratorService(message.bot)
    curator_ids = await svc.list_curator_ids()
    if not curator_ids:
        await message.answer(
            "В базе нет зарегистрированных пользователей для рассылки.",
            reply_markup=AdminKeyboards.back_to_admin_menu(),
        )
        await state.clear()
        return

    sent = 0
    skipped = 0
    for curator_id in curator_ids:
        try:
            await message.bot.copy_message(
                chat_id=curator_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
        except Exception:
            skipped += 1
            continue

    await message.answer(
        f"Рассылка завершена. Сообщений отправлено: {sent}. Не удалось доставить: {skipped}.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await state.clear()
