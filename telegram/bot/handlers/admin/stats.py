from datetime import date

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...keyboards import AdminKeyboards
from ...keyboards.calendar import AdminCalendarCallback, CalendarView, CuratorCalendarKeyboard
from ...services.curator_service import CuratorService
from ...states.admin_states import AdminStatsSelection
from ...utils.curator_stats import prepare_all_curators_stats
from .calendar_helpers import (
    _deserialize_calendar_state,
    _get_calendar_state,
    _get_selected_date,
    _initial_calendar_state,
    _refresh_calendar_markup,
    _refresh_year_page,
    _serialize_calendar_state,
    _store_calendar_state,
    _store_selected_date,
)
from .helpers import _is_admin, _is_super_admin
from .router import router


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
    prompt = "Выберите начальную дату периода для статистики по всем пользователям:"
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
    call: CallbackQuery,
    callback_data: AdminCalendarCallback,
    state: FSMContext,
) -> None:
    if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return

    target = callback_data.target
    if target not in ("adm_start", "adm_end"):
        await call.answer("Неизвестная цель календаря.", show_alert=True)
        return

    calendar_state = await _get_calendar_state(state, target)
    selected_date = await _get_selected_date(state, target)

    if callback_data.action == "prev":
        if calendar_state.view == CalendarView.MONTHS:
            calendar_state.year -= 1
            _refresh_year_page(calendar_state)
        elif calendar_state.view == CalendarView.DAYS:
            calendar_state.month -= 1
            if calendar_state.month < 1:
                calendar_state.month = 12
                calendar_state.year -= 1
            _refresh_year_page(calendar_state)
        else:  # YEARS
            calendar_state.year_page -= 12
            if calendar_state.year_page < 1:
                calendar_state.year_page = 1
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if callback_data.action == "next":
        if calendar_state.view == CalendarView.MONTHS:
            calendar_state.year += 1
            _refresh_year_page(calendar_state)
        elif calendar_state.view == CalendarView.DAYS:
            calendar_state.month += 1
            if calendar_state.month > 12:
                calendar_state.month = 1
                calendar_state.year += 1
            _refresh_year_page(calendar_state)
        else:  # YEARS
            calendar_state.year_page += 12
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if callback_data.action == "switch_view":
        match calendar_state.view:
            case CalendarView.DAYS:
                calendar_state.view = CalendarView.MONTHS
            case CalendarView.MONTHS:
                calendar_state.view = CalendarView.YEARS
            case _:
                calendar_state.view = CalendarView.DAYS
        if calendar_state.view == CalendarView.DAYS and calendar_state.month is None:
            calendar_state.month = date.today().month
        _refresh_year_page(calendar_state)
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if callback_data.action == "go_today":
        today_state = _initial_calendar_state()
        await _store_calendar_state(state, target, today_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=today_state)
        await call.answer()
        return

    if callback_data.action == "reset":
        await state.clear()
        await call.message.answer(
            "Выбор даты сброшен.", reply_markup=AdminKeyboards.back_to_admin_menu()
        )
        await call.answer()
        return

    if callback_data.action in {"choose_year", "choose_month", "choose_day"}:
        match callback_data.action:
            case "choose_year":
                calendar_state.view = CalendarView.MONTHS
                calendar_state.year = callback_data.year or calendar_state.year
            case "choose_month":
                calendar_state.view = CalendarView.DAYS
                calendar_state.month = callback_data.month or calendar_state.month
            case "choose_day":
                try:
                    selected_date = date(
                        callback_data.year or calendar_state.year,
                        callback_data.month or calendar_state.month,
                        callback_data.day or 1,
                    )
                except Exception:
                    await call.answer("Некорректная дата.", show_alert=True)
                    return
                await _store_selected_date(state, target, selected_date)
            case _:
                await call.answer("Неизвестное действие.", show_alert=True)
                return

        _refresh_year_page(calendar_state)
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if callback_data.action == "confirm":
        selected_date = await _get_selected_date(state, target)
        if not selected_date:
            await call.answer("Пожалуйста, выберите дату.", show_alert=True)
            return

        await _store_selected_date(state, target, selected_date)
        await _store_calendar_state(state, target, calendar_state)

        if target == "adm_start":
            await state.set_state(AdminStatsSelection.choosing_end)
            await _store_calendar_state(state, "adm_end", _serialize_calendar_state(calendar_state))
            prompt = "Выберите конечную дату периода:"
            markup = CuratorCalendarKeyboard.build(
                _deserialize_calendar_state(calendar_state),
                target="adm_end",
                callback_factory=AdminCalendarCallback,
            )
            await call.message.answer(prompt, reply_markup=markup)
            await call.answer()
            return

        # target == "adm_end"
        start_date = await _get_selected_date(state, "adm_start")
        end_date = selected_date
        if not start_date:
            await call.answer("Сначала выберите начальную дату.", show_alert=True)
            return
        if end_date < start_date:
            await call.answer("Конечная дата не может быть раньше начальной.", show_alert=True)
            return

        await state.clear()
        svc = CuratorService(call.bot)
        result = await prepare_all_curators_stats(svc, start_date=start_date, end_date=end_date)
        if result is None:
            await call.message.answer(
                "Нет данных для выбранного периода.",
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
        return

    await call.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data == "adm_menu:all_stats_all_time")
async def send_all_curators_stats_all_time(call: CallbackQuery) -> None:
    if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
        await call.answer("Эта функция доступна только администраторам.", show_alert=True)
        return

    svc = CuratorService(call.bot)
    snapshot = await prepare_all_curators_stats(svc)
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
