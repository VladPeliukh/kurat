from datetime import date, datetime

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...keyboards.calendar import (
    AdminCalendarCallback,
    CalendarState,
    CalendarView,
    CuratorCalendarKeyboard,
)
from ...utils.curator_stats import MOSCOW_TZ


_CALENDAR_STATE_KEY_TEMPLATE = "{target}_calendar"
_SELECTED_DATE_KEY_TEMPLATE = "{target}_date"


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
    key = _CALENDAR_STATE_KEY_TEMPLATE.format(target=target)
    return _deserialize_calendar_state(data.get(key))


async def _store_calendar_state(
    state: FSMContext,
    target: str,
    calendar_state: CalendarState,
) -> None:
    await state.update_data(
        **{_CALENDAR_STATE_KEY_TEMPLATE.format(target=target): _serialize_calendar_state(calendar_state)}
    )


async def _store_selected_date(
    state: FSMContext,
    target: str,
    selected_date: date | None,
) -> None:
    await state.update_data(
        **{
            _SELECTED_DATE_KEY_TEMPLATE.format(target=target): (
                selected_date.isoformat() if selected_date else None
            )
        }
    )


async def _get_selected_date(state: FSMContext, target: str) -> date | None:
    data = await state.get_data()
    raw = data.get(_SELECTED_DATE_KEY_TEMPLATE.format(target=target))
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


__all__ = [
    "_initial_calendar_state",
    "_serialize_calendar_state",
    "_deserialize_calendar_state",
    "_refresh_year_page",
    "_get_calendar_state",
    "_store_calendar_state",
    "_store_selected_date",
    "_get_selected_date",
    "_refresh_calendar_markup",
]
