from datetime import date, datetime, time, timedelta, timezone

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...keyboards.calendar import CalendarView, CuratorCalendarCallback, CuratorCalendarKeyboard
from ...services.curator_service import CuratorService
from ...states.curator_states import CuratorStatsSelection
from ...utils.handlers_helpers import (
    MOSCOW_TZ,
    get_calendar_state,
    get_selected_date,
    initial_calendar_state,
    is_private_chat,
    refresh_calendar_markup,
    refresh_year_page,
    require_curator_or_admin_callback,
    require_curator_or_admin_message,
    store_calendar_state,
    store_selected_date,
)
from ...utils.curator_stats import (
    CURATOR_STATS_HEADERS,
    collect_curator_stats_rows,
    prepare_curator_all_time_stats,
)
from ...utils.csv_export import build_simple_table_csv
from . import router


@router.callback_query(F.data == "cur_menu:stats")
async def curator_show_stats(call: CallbackQuery, state: FSMContext) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    total_partners = await svc.partners_count(call.from_user.id)
    if total_partners == 0:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    await state.clear()
    start_state = initial_calendar_state()
    await state.set_state(CuratorStatsSelection.choosing_start)
    await store_calendar_state(state, "start", start_state)
    await store_selected_date(state, "start", None)
    await store_selected_date(state, "end", None)
    await store_calendar_state(state, "end", initial_calendar_state())
    prompt = "Выберите начальную дату периода:"
    markup = CuratorCalendarKeyboard.build(start_state, target="start")
    try:
        await call.message.answer(prompt, reply_markup=markup)
    except Exception:
        try:
            await call.bot.send_message(
                call.from_user.id,
                prompt,
                reply_markup=markup,
            )
        except Exception:
            await call.answer("Не удалось показать календарь.", show_alert=True)
            return
    await call.answer()


@router.callback_query(F.data == "cur_menu:stats_all")
async def curator_show_all_time_stats(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await require_curator_or_admin_callback(call, svc):
        return
    result = await prepare_curator_all_time_stats(svc, call.from_user.id)
    if result is None:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    document, caption = result
    if call.message is not None:
        await call.message.answer_document(document, caption=caption)
    else:
        try:
            await call.bot.send_document(
                call.from_user.id,
                document,
                caption=caption,
            )
        except Exception:
            await call.answer("Не удалось отправить файл.", show_alert=True)
            return
    await call.answer()


@router.callback_query(CuratorCalendarCallback.filter())
async def curator_stats_calendar_action(
    call: CallbackQuery,
    callback_data: CuratorCalendarCallback,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()
    allowed_states = {
        CuratorStatsSelection.choosing_start.state,
        CuratorStatsSelection.choosing_end.state,
    }
    if current_state not in allowed_states:
        await call.answer("Этот календарь больше не активен.", show_alert=True)
        return
    target = callback_data.target
    if target not in {"start", "end"}:
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    calendar_state = await get_calendar_state(state, target)
    action = callback_data.action
    if action == "noop":
        await call.answer()
        return

    if action in {"prev_month", "next_month"}:
        year = max(1, callback_data.year)
        month = min(12, max(1, callback_data.month))
        calendar_state.year = year
        calendar_state.month = month
        calendar_state.view = CalendarView.DAYS
        refresh_year_page(calendar_state)
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "show_months":
        calendar_state.view = CalendarView.MONTHS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "show_years":
        calendar_state.view = CalendarView.YEARS
        page = callback_data.page
        if page is not None:
            calendar_state.year_page = max(1, page)
        elif calendar_state.year_page is None:
            refresh_year_page(calendar_state)
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_year", "next_year"}:
        calendar_state.year = max(1, callback_data.year)
        refresh_year_page(calendar_state)
        calendar_state.view = CalendarView.MONTHS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "set_month":
        calendar_state.month = min(12, max(1, callback_data.month))
        calendar_state.view = CalendarView.DAYS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "back_to_days":
        calendar_state.view = CalendarView.DAYS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_year_page", "next_year_page"}:
        page = callback_data.page
        if page is None:
            page = (calendar_state.year_page or 1) + (-12 if action == "prev_year_page" else 12)
        calendar_state.year_page = max(1, page)
        calendar_state.view = CalendarView.YEARS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "set_year":
        calendar_state.year = max(1, callback_data.year)
        refresh_year_page(calendar_state)
        calendar_state.view = CalendarView.MONTHS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "back_to_months":
        calendar_state.view = CalendarView.MONTHS
        await store_calendar_state(state, target, calendar_state)
        await refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
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
        await store_calendar_state(state, target, calendar_state)
        formatted = selected_date.strftime("%d.%m.%Y")
        if target == "start":
            await store_selected_date(state, "start", selected_date)
            await call.message.answer(f"Начальная дата выбрана: {formatted}")
            end_state = await get_calendar_state(state, "end")
            end_state.year = selected_date.year
            end_state.month = selected_date.month
            end_state.view = CalendarView.DAYS
            refresh_year_page(end_state)
            await store_calendar_state(state, "end", end_state)
            await state.set_state(CuratorStatsSelection.choosing_end)
            prompt = "Выберите конечную дату периода:"
            markup = CuratorCalendarKeyboard.build(end_state, target="end")
            try:
                await call.message.edit_text(prompt, reply_markup=markup)
            except Exception:
                await call.message.answer(prompt, reply_markup=markup)
            await call.answer()
            return

        start_date = await get_selected_date(state, "start")
        if start_date and selected_date < start_date:
            await call.answer(
                "Конечная дата не может быть раньше начальной.",
                show_alert=True,
            )
            return
        await store_selected_date(state, "end", selected_date)
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
        partners = await svc.list_partners(
            call.from_user.id,
            start=start_dt,
            end=end_dt,
        )
        if not partners:
            await call.answer("За выбранный период нет данных.", show_alert=True)
            return
        csv_bytes = build_simple_table_csv(
            CURATOR_STATS_HEADERS,
            collect_curator_stats_rows(partners),
        )
        file_name = f"curator_stats_{start_date.isoformat()}_{selected_date.isoformat()}.csv"
        await call.message.answer_document(
            csv_bytes,
            caption=f"Статистика с {start_date} по {selected_date}",
            filename=file_name,
        )
        await call.answer()


@router.message(Command("static"))
async def handle_curator_full_stats(message: Message) -> None:
    if not is_private_chat(message):
        return
    svc = CuratorService(message.bot)
    if not await require_curator_or_admin_message(message, svc):
        return

    result = await prepare_curator_all_time_stats(svc, message.from_user.id)
    if result is None:
        await message.answer("У вас пока нет приглашенных пользователей.")
        return

    document, caption = result
    await message.answer_document(document, caption=caption)
