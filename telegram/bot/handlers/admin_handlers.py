from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import AdminKeyboards
from ..services.admin_service import AdminService
from ..services.curator_service import CuratorService
from ..states.admin_states import AdminCuratorStats
from ..utils.curator_stats import prepare_curator_all_time_stats


router = Router()


async def _is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


@router.message(Command("admin"))
async def show_admin_menu(message: Message) -> None:
    if not await _is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администраторам.")
        return

    await message.answer(
        "АДМИН-МЕНЮ",
        reply_markup=AdminKeyboards.main_menu(),
    )


@router.callback_query(F.data == "adm_menu:open")
async def admin_menu_open(call: CallbackQuery) -> None:
    if not await _is_admin(call.from_user.id):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await call.message.answer("АДМИН-МЕНЮ", reply_markup=AdminKeyboards.main_menu())
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "adm_menu:curator_stats")
async def prompt_curator_stats(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_admin(call.from_user.id):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return
    await state.set_state(AdminCuratorStats.waiting_curator_id)
    await call.message.answer(
        "Введите ID куратора, чью статистику хотите посмотреть.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.message(AdminCuratorStats.waiting_curator_id)
async def send_curator_stats(message: Message, state: FSMContext) -> None:
    if not await _is_admin(message.from_user.id):
        await message.answer("Эта функция доступна только администраторам.")
        await state.clear()
        return

    try:
        curator_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("Пожалуйста, отправьте корректный числовой ID куратора.")
        return

    svc = CuratorService(message.bot)
    if not await svc.is_curator(curator_id):
        await message.answer("Куратор с таким ID не найден.", reply_markup=AdminKeyboards.back_to_admin_menu())
        await state.clear()
        return

    record = await svc.get_curator_record(curator_id) or {}
    owner_label = "Статистика куратора"
    if record.get("full_name"):
        owner_label = f"{owner_label} {record['full_name']}"
    result = await prepare_curator_all_time_stats(svc, curator_id, owner_label=owner_label)
    if result is None:
        await message.answer("У этого куратора пока нет приглашенных пользователей.", reply_markup=AdminKeyboards.back_to_admin_menu())
        await state.clear()
        return

    document, caption = result
    await message.answer_document(document, caption=caption, reply_markup=AdminKeyboards.back_to_admin_menu())
    await state.clear()

