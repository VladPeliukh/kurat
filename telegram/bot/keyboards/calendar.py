from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Type

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CalendarView(str, Enum):
    DAYS = "days"
    MONTHS = "months"
    YEARS = "years"


class CuratorCalendarCallback(CallbackData, prefix="curcal"):
    target: str
    action: str
    year: int
    month: int
    day: int | None = None
    page: int | None = None


class AdminCalendarCallback(CallbackData, prefix="admcal"):
    target: str
    action: str
    year: int
    month: int
    day: int | None = None
    page: int | None = None


@dataclass(slots=True)
class CalendarState:
    year: int
    month: int
    view: CalendarView = CalendarView.DAYS
    year_page: int | None = None


class CuratorCalendarKeyboard:
    MONTH_NAMES = (
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    )

    MONTH_SHORT_NAMES = (
        "Янв",
        "Фев",
        "Мар",
        "Апр",
        "Май",
        "Июн",
        "Июл",
        "Авг",
        "Сен",
        "Окт",
        "Ноя",
        "Дек",
    )

    WEEKDAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

    @staticmethod
    def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
        month += offset
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        if year < 1:
            year = 1
        return year, month

    @staticmethod
    def _year_page_bounds(year_page: int) -> tuple[int, int]:
        start = max(1, year_page)
        end = start + 11
        return start, end

    @staticmethod
    def _noop_button(
        target: str,
        year: int,
        month: int,
        text: str,
        *,
        callback_factory: Type[CallbackData],
    ) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=callback_factory(
                target=target,
                action="noop",
                year=year,
                month=month,
            ).pack(),
        )

    @staticmethod
    def _rows(
        builder: InlineKeyboardBuilder, buttons: Iterable[InlineKeyboardButton], width: int
    ) -> None:
        row: list[InlineKeyboardButton] = []
        for button in buttons:
            row.append(button)
            if len(row) == width:
                builder.row(*row, width=width)
                row = []
        if row:
            builder.row(*row, width=len(row))

    @classmethod
    def build(
        cls,
        state: CalendarState,
        *,
        target: str,
        callback_factory: Type[CallbackData] = CuratorCalendarCallback,
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        year = state.year
        month = state.month
        view = state.view

        if view is CalendarView.DAYS:
            prev_year, prev_month = cls._shift_month(year, month, -1)
            next_year, next_month = cls._shift_month(year, month, 1)
            builder.row(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=callback_factory(
                        target=target,
                        action="prev_month",
                        year=prev_year,
                        month=prev_month,
                    ).pack(),
                ),
                cls._noop_button(
                    target,
                    year,
                    month,
                    f"{cls.MONTH_NAMES[month - 1]} {year}",
                    callback_factory=callback_factory,
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=callback_factory(
                        target=target,
                        action="next_month",
                        year=next_year,
                        month=next_month,
                    ).pack(),
                ),
                width=3,
            )
            builder.row(
                InlineKeyboardButton(
                    text="📅 Месяц",
                    callback_data=callback_factory(
                        target=target,
                        action="show_months",
                        year=year,
                        month=month,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📆 Год",
                    callback_data=callback_factory(
                        target=target,
                        action="show_years",
                        year=year,
                        month=month,
                        page=(state.year_page or year - year % 12),
                    ).pack(),
                ),
                width=2,
            )
            builder.row(
                *[
                    cls._noop_button(
                        target,
                        year,
                        month,
                        name,
                        callback_factory=callback_factory,
                    )
                    for name in cls.WEEKDAY_NAMES
                ],
                width=7,
            )
            cal = calendar.Calendar(firstweekday=0)
            for week in cal.monthdayscalendar(year, month):
                buttons: list[InlineKeyboardButton] = []
                for day in week:
                    if day == 0:
                        buttons.append(cls._noop_button(target, year, month, " "))
                    else:
                        buttons.append(
                            InlineKeyboardButton(
                                text=f"{day:02d}",
                                callback_data=callback_factory(
                                    target=target,
                                    action="set_day",
                                    year=year,
                                    month=month,
                                    day=day,
                                ).pack(),
                            )
                        )
                builder.row(*buttons, width=7)
        elif view is CalendarView.MONTHS:
            builder.row(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=callback_factory(
                        target=target,
                        action="prev_year",
                        year=year - 1,
                        month=month,
                    ).pack(),
                ),
                cls._noop_button(
                    target,
                    year,
                    month,
                    f"{year}",
                    callback_factory=callback_factory,
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=callback_factory(
                        target=target,
                        action="next_year",
                        year=year + 1,
                        month=month,
                    ).pack(),
                ),
                width=3,
            )
            cls._rows(
                builder,
                (
                    InlineKeyboardButton(
                        text=cls.MONTH_SHORT_NAMES[index],
                        callback_data=callback_factory(
                            target=target,
                            action="set_month",
                            year=year,
                            month=index + 1,
                        ).pack(),
                    )
                    for index in range(12)
                ),
                width=3,
            )
            builder.row(
                InlineKeyboardButton(
                    text="📅 Дни",
                    callback_data=callback_factory(
                        target=target,
                        action="show_days",
                        year=year,
                        month=month,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📆 Год",
                    callback_data=callback_factory(
                        target=target,
                        action="show_years",
                        year=year,
                        month=month,
                        page=(state.year_page or year - year % 12),
                    ).pack(),
                ),
                width=2,
            )
        elif view is CalendarView.YEARS:
            year_page = state.year_page or year
            start_year, end_year = cls._year_page_bounds(year_page)
            builder.row(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=callback_factory(
                        target=target,
                        action="prev_year_page",
                        year=start_year - 12,
                        month=month,
                        page=max(1, year_page - 12),
                    ).pack(),
                ),
                cls._noop_button(
                    target,
                    year,
                    month,
                    f"{start_year} — {end_year}",
                    callback_factory=callback_factory,
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=callback_factory(
                        target=target,
                        action="next_year_page",
                        year=end_year + 1,
                        month=month,
                        page=year_page + 12,
                    ).pack(),
                ),
                width=3,
            )
            cls._rows(
                builder,
                (
                    InlineKeyboardButton(
                        text=str(current_year),
                        callback_data=callback_factory(
                            target=target,
                            action="set_year",
                            year=current_year,
                            month=month,
                        ).pack(),
                    )
                    for current_year in range(start_year, end_year + 1)
                ),
                width=3,
            )
            builder.row(
                InlineKeyboardButton(
                    text="📅 Дни",
                    callback_data=callback_factory(
                        target=target,
                        action="show_days",
                        year=year,
                        month=month,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📅 Месяц",
                    callback_data=callback_factory(
                        target=target,
                        action="show_months",
                        year=year,
                        month=month,
                    ).pack(),
                ),
                width=2,
            )
        return builder.as_markup()


def _coerce_calendar_state(raw: CalendarState | dict | None) -> CalendarState:
    if isinstance(raw, CalendarState):
        return raw

    today = datetime.now().date()
    if isinstance(raw, dict):
        try:
            view_value = raw.get("view")
            view = CalendarView(view_value) if view_value else CalendarView.DAYS
        except ValueError:
            view = CalendarView.DAYS

        year = raw.get("year")
        month = raw.get("month")
        year_page = raw.get("year_page")

        try:
            year = int(year) if year else today.year
        except (TypeError, ValueError):
            year = today.year

        try:
            month = int(month) if month else today.month
        except (TypeError, ValueError):
            month = today.month

        try:
            year_page = int(year_page) if year_page is not None else None
        except (TypeError, ValueError):
            year_page = None

        return CalendarState(year=year, month=month, view=view, year_page=year_page)

    return CalendarState(year=today.year, month=today.month)


def build_calendar_keyboard(
    calendar_state: CalendarState | dict | None,
    *,
    target: str,
) -> InlineKeyboardMarkup:
    state = _coerce_calendar_state(calendar_state)
    return CuratorCalendarKeyboard.build(state, target=target)


__all__ = [
    "CalendarState",
    "CalendarView",
    "AdminCalendarCallback",
    "CuratorCalendarCallback",
    "CuratorCalendarKeyboard",
    "build_calendar_keyboard",
]
