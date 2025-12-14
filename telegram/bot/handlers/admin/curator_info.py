from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...keyboards import AdminKeyboards
from ...services.curator_service import CuratorService
from ...states.admin_states import AdminCuratorInfo
from ...utils.curator_stats import (
    prepare_curator_all_time_stats,
    prepare_curator_info_report,
)
from ...utils.handlers_helpers import _is_admin, _is_private_chat
from .router import router


@router.callback_query(F.data == "adm_menu:curator_info")
async def prompt_curator_info(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_admin(call.from_user.id):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return
    await state.set_state(AdminCuratorInfo.waiting_curator_id)
    await call.message.answer(
        "Введите ID пользователя, информацию о котором хотите получить.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.message(AdminCuratorInfo.waiting_curator_id)
async def send_curator_info(message: Message, state: FSMContext) -> None:
    if not _is_private_chat(message):
        return
    if not await _is_admin(message.from_user.id):
        await message.answer("Эта функция доступна только администраторам.")
        await state.clear()
        return

    try:
        curator_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("Пожалуйста, отправьте корректный числовой ID пользователя.")
        return

    svc = CuratorService(message.bot)
    if not await svc.is_curator(curator_id):
        await message.answer("Пользователь с таким ID не найден.", reply_markup=AdminKeyboards.back_to_admin_menu())
        await state.clear()
        return

    result = await prepare_curator_info_report(svc, curator_id)
    if result is None:
        await message.answer("Не удалось найти данные по этому пользователю.", reply_markup=AdminKeyboards.back_to_admin_menu())
        await state.clear()
        return

    await message.answer(
        result,
        reply_markup=AdminKeyboards.curator_info_actions(curator_id),
        disable_web_page_preview=True,
    )
    await state.clear()


@router.callback_query(F.data.startswith("adm_curator_stats:"))
async def send_curator_stats_from_info(call: CallbackQuery) -> None:
    if not await _is_admin(call.from_user.id):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return

    try:
        curator_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Не удалось определить пользователя.", show_alert=True)
        return

    svc = CuratorService(call.bot)
    if not await svc.is_curator(curator_id):
        await call.answer("Пользователь с таким ID не найден.", show_alert=True)
        return

    record = await svc.get_curator_record(curator_id) or {}
    owner_label = "Статистика пользователя"
    if record.get("full_name"):
        owner_label = f"{owner_label} {record['full_name']}"

    result = await prepare_curator_all_time_stats(svc, curator_id, owner_label=owner_label)
    if result is None:
        await call.message.answer(
            "У этого пользователя пока нет приглашенных пользователей.",
            reply_markup=AdminKeyboards.back_to_admin_menu(),
        )
        await call.answer()
        return

    document, caption = result
    await call.message.answer_document(
        document,
        caption=caption,
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()
