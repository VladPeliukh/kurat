from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import AdminKeyboards
from ..services.admin_service import AdminService
from ..services.curator_service import CuratorService
from ..states.admin_states import AdminBroadcast, AdminCuratorInfo, AdminPromoteAdmin
from ..utils.curator_stats import (
    prepare_all_curators_snapshot,
    prepare_curator_all_time_stats,
    prepare_curator_info_report,
)


router = Router()


async def _is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


async def _is_super_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_super_admin(user_id)


@router.message(Command("admin"))
async def show_admin_menu(message: Message) -> None:
    is_super_admin = await _is_super_admin(message.from_user.id)
    if not (is_super_admin or await _is_admin(message.from_user.id)):
        await message.answer("Эта команда доступна только администраторам.")
        return

    await message.answer(
        "АДМИН-МЕНЮ",
        reply_markup=AdminKeyboards.main_menu(is_super_admin=is_super_admin),
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
            reply_markup=AdminKeyboards.main_menu(is_super_admin=is_super_admin),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "adm_menu:broadcast")
async def prompt_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return
    await state.set_state(AdminBroadcast.waiting_message)
    await call.message.answer(
        "Отправьте сообщение, которое нужно разослать всем кураторам.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_menu:promote_admin")
async def prompt_promote_admin(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return
    await state.set_state(AdminPromoteAdmin.waiting_curator_id)
    await call.message.answer(
        "Введите ID куратора, которого нужно сделать администратором.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_menu:curator_info")
async def prompt_curator_info(call: CallbackQuery, state: FSMContext) -> None:
    if not await _is_admin(call.from_user.id):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return
    await state.set_state(AdminCuratorInfo.waiting_curator_id)
    await call.message.answer(
        "Введите ID куратора, информацию о котором хотите получить.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_menu:all_stats")
async def send_all_curators_stats(call: CallbackQuery) -> None:
    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return

    svc = CuratorService(call.bot)
    snapshot = await prepare_all_curators_snapshot(svc)
    if snapshot is None:
        await call.message.answer(
            "Нет данных для сводки.", reply_markup=AdminKeyboards.back_to_admin_menu()
        )
        await call.answer()
        return

    document, caption = snapshot
    await call.message.answer_document(
        document, caption=caption, reply_markup=AdminKeyboards.back_to_admin_menu()
    )
    await call.answer()


@router.message(AdminCuratorInfo.waiting_curator_id)
async def send_curator_info(message: Message, state: FSMContext) -> None:
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

    result = await prepare_curator_info_report(svc, curator_id)
    if result is None:
        await message.answer("Не удалось найти данные по этому куратору.", reply_markup=AdminKeyboards.back_to_admin_menu())
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
        await call.answer("Не удалось определить куратора.", show_alert=True)
        return

    svc = CuratorService(call.bot)
    if not await svc.is_curator(curator_id):
        await call.answer("Куратор с таким ID не найден.", show_alert=True)
        return

    record = await svc.get_curator_record(curator_id) or {}
    owner_label = "Статистика куратора"
    if record.get("full_name"):
        owner_label = f"{owner_label} {record['full_name']}"

    result = await prepare_curator_all_time_stats(svc, curator_id, owner_label=owner_label)
    if result is None:
        await call.message.answer(
            "У этого куратора пока нет приглашенных пользователей.",
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


@router.message(AdminBroadcast.waiting_message)
async def broadcast_message(message: Message, state: FSMContext) -> None:
    if not await _is_super_admin(message.from_user.id):
        await message.answer("Эта функция доступна только супер-администратору.")
        await state.clear()
        return

    svc = CuratorService(message.bot)
    curator_ids = await svc.list_curator_ids()
    if not curator_ids:
        await message.answer(
            "В базе нет зарегистрированных кураторов для рассылки.",
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


@router.message(AdminPromoteAdmin.waiting_curator_id)
async def promote_admin(message: Message, state: FSMContext) -> None:
    if not await _is_super_admin(message.from_user.id):
        await message.answer("Эта функция доступна только супер-администратору.")
        await state.clear()
        return

    try:
        curator_id = int(message.text.strip())
    except (TypeError, ValueError):
        await message.answer("Пожалуйста, отправьте корректный числовой ID куратора.")
        return

    curator_service = CuratorService(message.bot)
    if not await curator_service.is_curator(curator_id):
        await message.answer(
            "Куратор с таким ID не найден.",
            reply_markup=AdminKeyboards.back_to_admin_menu(),
        )
        await state.clear()
        return

    admin_service = AdminService()
    if await admin_service.is_admin(curator_id):
        await message.answer(
            "Этот куратор уже является администратором.",
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

    await message.answer(
        "Куратор назначен администратором.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await state.clear()

