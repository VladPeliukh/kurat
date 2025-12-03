from contextlib import suppress
from datetime import date, datetime, time, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import AdminKeyboards
from ..keyboards.calendar import (
    AdminCalendarCallback,
    CalendarState,
    CalendarView,
    CuratorCalendarKeyboard,
)
from ..services.admin_service import AdminService
from ..services.curator_service import CuratorService
from ..states.admin_states import (
    AdminBroadcast,
    AdminCuratorInfo,
    AdminPromoteAdmin,
    AdminStatsSelection,
)
from ..utils.curator_stats import (
    MOSCOW_TZ,
    prepare_all_curators_snapshot,
    prepare_curator_all_time_stats,
    prepare_curator_info_report,
)


router = Router()


_open_invite_toggle_locked = False


async def _is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


async def _is_super_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_super_admin(user_id)


def _is_private_chat(message: Message) -> bool:
    return message.chat.type == "private"


def _initial_calendar_state(reference: date | None = None) -> CalendarState:
    if reference is None:
        reference = datetime.now(MOSCOW_TZ).date()
    year_page = reference.year - (reference.year % 12 or 12)
    if year_page < 1:
        year_page = 1
    return CalendarState(
        year=reference.year,
        month=reference.month,
        view=CalendarView.DAYS,
        year_page=year_page,
    )


def _serialize_calendar_state(state: CalendarState) -> dict:
    return {
        "year": state.year,
        "month": state.month,
        "view": state.view.value,
        "year_page": state.year_page,
    }


def _deserialize_calendar_state(
    raw: CalendarState | dict | None,
    *,
    reference: date | None = None,
) -> CalendarState:
    if isinstance(raw, CalendarState):
        return raw
    if isinstance(raw, dict):
        try:
            view = CalendarView(raw.get("view", CalendarView.DAYS.value))
        except ValueError:
            view = CalendarView.DAYS
        year = int(raw.get("year")) if raw.get("year") else None
        month = int(raw.get("month")) if raw.get("month") else None
        year_page = raw.get("year_page")
        if year_page is not None:
            try:
                year_page = int(year_page)
            except (TypeError, ValueError):
                year_page = None
        if reference is None:
            reference = datetime.now(MOSCOW_TZ).date()
        return CalendarState(
            year=year or reference.year,
            month=month or reference.month,
            view=view,
            year_page=year_page,
        )
    return _initial_calendar_state(reference)


def _refresh_year_page(state: CalendarState) -> None:
    state.year_page = state.year - (state.year % 12 or 12)
    if state.year_page < 1:
        state.year_page = 1


async def _get_calendar_state(state: FSMContext, target: str) -> CalendarState:
    data = await state.get_data()
    key = f"{target}_calendar"
    return _deserialize_calendar_state(data.get(key))


async def _store_calendar_state(
    state: FSMContext,
    target: str,
    calendar_state: CalendarState,
) -> None:
    await state.update_data(**{f"{target}_calendar": _serialize_calendar_state(calendar_state)})


async def _store_selected_date(
    state: FSMContext,
    target: str,
    selected_date: date | None,
) -> None:
    await state.update_data(
        **{f"{target}_date": selected_date.isoformat() if selected_date else None}
    )


async def _get_selected_date(state: FSMContext, target: str) -> date | None:
    data = await state.get_data()
    raw = data.get(f"{target}_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


async def _refresh_calendar_markup(
    call: CallbackQuery,
    *,
    target: str,
    calendar_state: CalendarState,
) -> None:
    try:
        await call.message.edit_reply_markup(
            reply_markup=CuratorCalendarKeyboard.build(
                calendar_state,
                target=target,
                callback_factory=AdminCalendarCallback,
            )
        )
    except Exception:
        pass


@router.message(Command("admin"))
async def show_admin_menu(message: Message) -> None:
    if not _is_private_chat(message):
        return
    is_super_admin = await _is_super_admin(message.from_user.id)
    if not (is_super_admin or await _is_admin(message.from_user.id)):
        await message.answer("Эта команда доступна только администраторам.")
        return

    open_invite_enabled = None
    if is_super_admin and not _open_invite_toggle_locked:
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
                    if is_super_admin and not _open_invite_toggle_locked
                    else None
                ),
            ),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "adm_menu:toggle_open_invite")
async def toggle_open_invite(call: CallbackQuery) -> None:
    global _open_invite_toggle_locked

    if not await _is_super_admin(call.from_user.id):
        await call.answer("Эта функция доступна только супер-администратору.", show_alert=True)
        return

    if _open_invite_toggle_locked:
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
        _open_invite_toggle_locked = True

    await call.answer(status, show_alert=False)


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


@router.callback_query(F.data == "adm_menu:all_stats_all_time")
async def send_all_curators_stats_all_time(call: CallbackQuery) -> None:
    if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
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


@router.callback_query(F.data == "adm_menu:all_stats")
async def prompt_all_curators_stats_range(call: CallbackQuery, state: FSMContext) -> None:
    if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return

    await state.clear()
    start_state = _initial_calendar_state()
    await state.set_state(AdminStatsSelection.choosing_start)
    await _store_calendar_state(state, "adm_start", start_state)
    await _store_selected_date(state, "adm_start", None)
    await _store_selected_date(state, "adm_end", None)
    await _store_calendar_state(state, "adm_end", _initial_calendar_state())
    prompt = "Выберите начальную дату периода для статистики по всем кураторам:"
    markup = CuratorCalendarKeyboard.build(
        start_state, target="adm_start", callback_factory=AdminCalendarCallback
    )
    try:
        await call.message.answer(prompt, reply_markup=markup)
    except Exception:
        try:
            await call.bot.send_message(call.from_user.id, prompt, reply_markup=markup)
        except Exception:
            await call.answer("Не удалось показать календарь.", show_alert=True)
            return
    await call.answer()


@router.callback_query(AdminCalendarCallback.filter())
async def admin_stats_calendar_action(
    call: CallbackQuery, callback_data: AdminCalendarCallback, state: FSMContext
) -> None:
    current_state = await state.get_state()
    allowed_states = {
        AdminStatsSelection.choosing_start.state,
        AdminStatsSelection.choosing_end.state,
    }
    if current_state not in allowed_states:
        await call.answer("Этот календарь больше не активен.", show_alert=True)
        return
    target = callback_data.target
    if target not in {"adm_start", "adm_end"}:
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return

    calendar_state = await _get_calendar_state(state, target)
    action = callback_data.action

    if action == "noop":
        await call.answer()
        return

    if action in {"show_days", "show_months", "show_years"}:
        mapping = {
            "show_days": CalendarView.DAYS,
            "show_months": CalendarView.MONTHS,
            "show_years": CalendarView.YEARS,
        }
        calendar_state.view = mapping[action]
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_month", "next_month"}:
        calendar_state.year = callback_data.year
        calendar_state.month = callback_data.month
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_year", "next_year"}:
        calendar_state.year = callback_data.year
        calendar_state.month = callback_data.month
        calendar_state.view = CalendarView.MONTHS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "set_month":
        calendar_state.month = min(12, max(1, callback_data.month))
        calendar_state.view = CalendarView.DAYS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "back_to_days":
        calendar_state.view = CalendarView.DAYS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_year_page", "next_year_page"}:
        page = callback_data.page
        if page is None:
            page = (calendar_state.year_page or 1) + (-12 if action == "prev_year_page" else 12)
        calendar_state.year_page = max(1, page)
        calendar_state.view = CalendarView.YEARS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "set_year":
        calendar_state.year = max(1, callback_data.year)
        _refresh_year_page(calendar_state)
        calendar_state.view = CalendarView.MONTHS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "set_day":
        day = callback_data.day
        if day is None:
            await call.answer()
            return
        try:
            selected_date = date(calendar_state.year, calendar_state.month, day)
        except ValueError:
            await call.answer("Не удалось определить дату.", show_alert=True)
            return
        await _store_calendar_state(state, target, calendar_state)
        formatted = selected_date.strftime("%d.%m.%Y")
        if target == "adm_start":
            await _store_selected_date(state, "adm_start", selected_date)
            await call.message.answer(f"Начальная дата выбрана: {formatted}")
            end_state = await _get_calendar_state(state, "adm_end")
            end_state.year = selected_date.year
            end_state.month = selected_date.month
            end_state.view = CalendarView.DAYS
            _refresh_year_page(end_state)
            await _store_calendar_state(state, "adm_end", end_state)
            await state.set_state(AdminStatsSelection.choosing_end)
            prompt = "Выберите конечную дату периода:"
            markup = CuratorCalendarKeyboard.build(
                end_state, target="adm_end", callback_factory=AdminCalendarCallback
            )
            try:
                await call.message.edit_text(prompt, reply_markup=markup)
            except Exception:
                await call.message.answer(prompt, reply_markup=markup)
            await call.answer()
            return

        start_date = await _get_selected_date(state, "adm_start")
        if start_date and selected_date < start_date:
            await call.answer(
                "Конечная дата не может быть раньше начальной.",
                show_alert=True,
            )
            return
        await _store_selected_date(state, "adm_end", selected_date)
        await call.message.answer(f"Конечная дата выбрана: {formatted}")
        if start_date is None:
            start_date = selected_date
        start_dt = datetime.combine(
            start_date,
            time.min.replace(tzinfo=MOSCOW_TZ),
        ).astimezone(timezone.utc)
        end_dt = datetime.combine(
            selected_date + timedelta(days=1),
            time.min.replace(tzinfo=MOSCOW_TZ),
        ).astimezone(timezone.utc)
        svc = CuratorService(call.bot)
        snapshot = await prepare_all_curators_snapshot(
            svc, start=start_dt, end=end_dt
        )
        if snapshot is None:
            await call.message.answer(
                "В указанном периоде данных нет.",
                reply_markup=AdminKeyboards.back_to_admin_menu(),
            )
        else:
            document, caption = snapshot
            period_caption = (
                f"Период: {start_date.strftime('%d.%m.%Y')} — {selected_date.strftime('%d.%m.%Y')}."
            )
            await call.message.answer_document(
                document,
                caption=f"{caption}\n{period_caption}",
                reply_markup=AdminKeyboards.back_to_admin_menu(),
            )
        await state.clear()
        try:
            await call.message.edit_text(
                "Статистика сформирована. Нажмите «Посмотреть всю статистику»,"
                " чтобы выбрать другой период.",
            )
        except Exception:
            pass
        await call.answer()
        return

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
    if not _is_private_chat(message):
        return
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

    with suppress(Exception):
        await message.bot.send_message(
            curator_id,
            "Вы назначены администратором. Вам доступна команда /admin.",
        )

    await message.answer(
        "Куратор назначен администратором.",
        reply_markup=AdminKeyboards.back_to_admin_menu(),
    )
    await state.clear()

