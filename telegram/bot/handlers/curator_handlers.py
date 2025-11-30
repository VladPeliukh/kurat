import html
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)
from zoneinfo import ZoneInfo

from ..config import Config
from ..keyboards import CaptchaKeyboards, CuratorKeyboards
from ..services.admin_service import AdminService
from ..keyboards.calendar import (
    CalendarState,
    CalendarView,
    CuratorCalendarCallback,
    CuratorCalendarKeyboard,
)
from ..services.curator_service import CuratorService
from ..utils.curator_stats import (
    CURATOR_STATS_HEADERS,
    collect_curator_stats_rows,
    prepare_curator_all_time_stats,
)
from ..utils.captcha import NumberCaptcha
from ..utils.csv_export import build_simple_table_csv
from ..utils.commands import CURATOR_COMMANDS
from ..utils.helpers import build_deeplink
from ..states.curator_states import CuratorStatsSelection

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

router = Router()
_captcha_generator = NumberCaptcha()
_pending_curator_messages: dict[int, int] = {}
_CURATOR_PARTNERS_PAGE_SIZE = 10


async def _is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


async def _has_curator_access(bot: Bot, user_id: int, svc: CuratorService | None = None) -> bool:
    if await _is_admin(user_id):
        return True
    if svc is not None:
        return await svc.is_curator(user_id)
    return await CuratorService(bot).is_curator(user_id)


async def _require_curator_or_admin_message(message: Message, svc: CuratorService) -> bool:
    if await _has_curator_access(message.bot, message.from_user.id, svc):
        return True
    await message.answer("Эта команда доступна только кураторам и администраторам.")
    return False


async def _require_curator_or_admin_callback(call: CallbackQuery, svc: CuratorService) -> bool:
    if await _has_curator_access(call.bot, call.from_user.id, svc):
        return True
    await call.answer("Эта функция доступна только кураторам и администраторам.", show_alert=True)
    return False


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
        **{
            f"{target}_date": selected_date.isoformat() if selected_date else None,
        }
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
            reply_markup=CuratorCalendarKeyboard.build(calendar_state, target=target)
        )
    except Exception:
        pass


async def _send_curator_personal_link(
    target: Message,
    svc: CuratorService,
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
) -> None:
    link = await svc.get_or_create_personal_link(
        user_id,
        username,
        full_name or "",
    )
    count = await svc.partners_count(user_id)
    text = f"Ваша персональная ссылка:\n{link}\n\nПриглашено: {count}"
    await target.answer(
        text,
        reply_markup=CuratorKeyboards.invite(),
        disable_web_page_preview=True,
    )


def _build_captcha_options(correct_answer: int, total: int = 9) -> list[int]:
    options = {correct_answer}
    spread = max(3, abs(correct_answer) + 5)
    while len(options) < total:
        candidate = correct_answer + random.randint(-spread, spread)
        if candidate < 0:
            continue
        options.add(candidate)
    result = list(options)
    random.shuffle(result)
    return result

async def _render_partners_list(
    call: CallbackQuery,
    partners: list[dict],
    *,
    offset: int,
    text: str,
    keyboard_builder: Callable[..., InlineKeyboardMarkup],
) -> None:
    keyboard = keyboard_builder(
        partners,
        offset=offset,
        page_size=_CURATOR_PARTNERS_PAGE_SIZE,
    )
    try:
        await call.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await call.message.answer(text, reply_markup=keyboard)
    await call.answer()


async def _send_captcha_challenge(message: Message, user_id: int, svc: CuratorService, curator_id: int) -> None:
    answer, image_bytes = await _captcha_generator.random_captcha()
    options = _build_captcha_options(answer)
    await svc.store_captcha_challenge(user_id, curator_id, answer)
    keyboard = CaptchaKeyboards.options(options)
    captcha_image = BufferedInputFile(image_bytes, filename="captcha.png")
    await message.answer_photo(
        captcha_image,
        caption=(
            "Подтвердите, что вы человек. Решите пример на изображении и выберите верный ответ."
        ),
        reply_markup=keyboard,
    )


async def _notify_curator(
    svc: CuratorService,
    curator_id: int,
    partner_id: int,
    full_name: str,
    bot: Bot,
    *,
    username: str | None = None,
    source_link: str | None = None,
    payload: str | None = None,
) -> None:
    await svc.request_join(
        curator_id,
        partner_id,
        full_name=full_name,
        username=username,
        source_link=source_link,
        payload=payload,
    )
    keyboard = CuratorKeyboards.request(partner_id)
    safe_name = html.escape(full_name or "")
    try:
        await bot.send_message(
            curator_id,
            f"Заявка от <a href='tg://user?id={partner_id}'>{safe_name}</a> стать куратором.",
            reply_markup=keyboard,
        )
    except Exception:
        pass


async def _finalize_request(
    message: Message,
    svc: CuratorService,
    curator_id: int,
    *,
    source_link: str | None = None,
    payload: str | None = None,
) -> None:
    await _notify_curator(
        svc,
        curator_id,
        message.from_user.id,
        message.from_user.full_name,
        message.bot,
        username=message.from_user.username,
        source_link=source_link,
        payload=payload,
    )
    await message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")


async def _ensure_inviter_record(
    svc: CuratorService, bot: Bot, inviter_id: int | None
) -> None:
    if not inviter_id:
        return
    full_name = ""
    username = None
    try:
        chat = await bot.get_chat(inviter_id)
        parts = [chat.first_name or "", chat.last_name or ""]
        full_name = " ".join(part for part in parts if part).strip()
        username = chat.username
    except Exception:
        pass
    await svc.ensure_curator_record(inviter_id, username, full_name)


async def _promote_user_to_curator(
    svc: CuratorService,
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    inviter_id: int | None = None,
    source_link: str | None = None,
) -> str:
    await _ensure_inviter_record(svc, bot, inviter_id)
    if inviter_id:
        await svc.register_partner(inviter_id, user_id)
    link = await svc.promote_to_curator(
        user_id,
        username,
        full_name or "",
        source_link=source_link,
    )
    try:
        await bot.set_my_commands(
            CURATOR_COMMANDS,
            scope=BotCommandScopeChat(chat_id=user_id),
        )
    except Exception:
        pass
    if inviter_id:
        safe_name = html.escape(full_name or "")
        try:
            await bot.send_message(
                inviter_id,
                (
                    "Пользователь по вашей ссылке стал куратором: "
                    f"<a href='tg://user?id={user_id}'>{safe_name}</a>."
                ),
            )
        except Exception:
        pass
    return link


@router.message(F.text.func(lambda text: text and text.strip().lower() == "стать куратором"))
async def promote_by_message(message: Message) -> None:
    if message.chat.type in {"group", "supergroup"}:
        if Config.PRIMARY_GROUP_ID and message.chat.id != Config.PRIMARY_GROUP_ID:
            return

    svc = CuratorService(message.bot)

    if not await svc.is_open_invite_enabled():
        await message.answer("Автоматическое приглашение сейчас отключено супер-администратором.")
        return

    if await svc.is_curator(message.from_user.id):
        await message.answer("Вы уже являетесь куратором.")
        return

    inviter_id = Config.SUPER_ADMIN
    if inviter_id is None:
        await message.answer("Функция временно недоступна: не задан супер-администратор.")
        return

    link = await _promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=inviter_id,
        source_link="super_admin_invite",
    )

    await message.answer(
        f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
        disable_web_page_preview=True,
        reply_markup=CuratorKeyboards.invite(),
    )


@router.message(Command('curator'))
async def show_curator_menu(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await _require_curator_or_admin_message(message, svc):
        return
    _pending_curator_messages.pop(message.from_user.id, None)
    await message.answer(
        "МЕНЮ КУРАТОРА",
        reply_markup=CuratorKeyboards.main_menu(),
    )


@router.callback_query(F.data == "cur_menu:open")
async def curator_menu_open(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    _pending_curator_messages.pop(call.from_user.id, None)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await call.message.answer(
            "МЕНЮ КУРАТОРА",
            reply_markup=CuratorKeyboards.main_menu(),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "cur_menu:back")
async def curator_menu_back(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    _pending_curator_messages.pop(call.from_user.id, None)
    keyboard = CuratorKeyboards.main_menu()
    try:
        await call.message.edit_text("МЕНЮ КУРАТОРА", reply_markup=keyboard)
    except Exception:
        await call.message.answer("МЕНЮ КУРАТОРА", reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data == "cur_menu:partners")
async def curator_show_partners(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    partners = await svc.list_partners(call.from_user.id)
    if not partners:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    text = (
        "Ваши приглашенные пользователи.\n"
        "Выберите пользователя, чтобы написать ему сообщение."
    )
    await _render_partners_list(
        call,
        partners,
        offset=0,
        text=text,
        keyboard_builder=CuratorKeyboards.partners,
    )


@router.callback_query(F.data == "cur_menu:invite")
async def curator_show_invite(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    if call.message is None:
        await call.answer("Не удалось отправить ссылку.", show_alert=True)
        return
    _pending_curator_messages.pop(call.from_user.id, None)
    await _send_curator_personal_link(
        call.message,
        svc,
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
    )
    await call.answer()


@router.callback_query(F.data == "cur_menu:stats")
async def curator_show_stats(call: CallbackQuery, state: FSMContext) -> None:
    svc = CuratorService(call.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    total_partners = await svc.partners_count(call.from_user.id)
    if total_partners == 0:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    await state.clear()
    start_state = _initial_calendar_state()
    await state.set_state(CuratorStatsSelection.choosing_start)
    await _store_calendar_state(state, "start", start_state)
    await _store_selected_date(state, "start", None)
    await _store_selected_date(state, "end", None)
    await _store_calendar_state(state, "end", _initial_calendar_state())
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
    if not await _require_curator_or_admin_callback(call, svc):
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
    calendar_state = await _get_calendar_state(state, target)
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
        _refresh_year_page(calendar_state)
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "show_months":
        calendar_state.view = CalendarView.MONTHS
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action == "show_years":
        calendar_state.view = CalendarView.YEARS
        page = callback_data.page
        if page is not None:
            calendar_state.year_page = max(1, page)
        elif calendar_state.year_page is None:
            _refresh_year_page(calendar_state)
        await _store_calendar_state(state, target, calendar_state)
        await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
        await call.answer()
        return

    if action in {"prev_year", "next_year"}:
        calendar_state.year = max(1, callback_data.year)
        _refresh_year_page(calendar_state)
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

    if action == "back_to_months":
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
        if target == "start":
            await _store_selected_date(state, "start", selected_date)
            await call.message.answer(f"Начальная дата выбрана: {formatted}")
            end_state = await _get_calendar_state(state, "end")
            end_state.year = selected_date.year
            end_state.month = selected_date.month
            end_state.view = CalendarView.DAYS
            _refresh_year_page(end_state)
            await _store_calendar_state(state, "end", end_state)
            await state.set_state(CuratorStatsSelection.choosing_end)
            prompt = "Выберите конечную дату периода:"
            markup = CuratorCalendarKeyboard.build(end_state, target="end")
            try:
                await call.message.edit_text(prompt, reply_markup=markup)
            except Exception:
                await call.message.answer(prompt, reply_markup=markup)
            await call.answer()
            return

        # target == "end"
        start_date = await _get_selected_date(state, "start")
        if start_date and selected_date < start_date:
            await call.answer(
                "Конечная дата не может быть раньше начальной.",
                show_alert=True,
            )
            return
        await _store_selected_date(state, "end", selected_date)
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
        rows = await collect_curator_stats_rows(svc, call.from_user.id, partners)
        if not rows:
            await call.message.answer("В указанном периоде приглашенных пользователей нет.")
        else:
            csv_bytes = build_simple_table_csv(CURATOR_STATS_HEADERS, rows)
            start_text = start_date.strftime("%d.%m.%Y")
            end_text = selected_date.strftime("%d.%m.%Y")
            filename = (
                f"curator_stats_{call.from_user.id}_{start_date.strftime('%Y%m%d')}"
                f"_{selected_date.strftime('%Y%m%d')}.csv"
            )
            document = BufferedInputFile(csv_bytes, filename=filename)
            caption = (
                "Ваша статистика приглашенных пользователей.\n"
                f"Период: {start_text} — {end_text}."
            )
            await call.message.answer_document(document, caption=caption)
        await state.clear()
        try:
            await call.message.edit_text(
                "Статистика сформирована. Нажмите «Посмотреть свою статистику»,"
                " чтобы выбрать другой период.",
            )
        except Exception:
            pass
        await call.answer()
        return

    await call.answer()

@router.callback_query(F.data.startswith("cur_partners_page:"))
async def curator_partners_next_page(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    try:
        offset = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        offset = _CURATOR_PARTNERS_PAGE_SIZE
    else:
        offset = max(0, offset)
    partners = await svc.list_partners(call.from_user.id)
    if not partners:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    text = (
        "Ваши приглашенные пользователи.\n"
        "Выберите пользователя, чтобы написать ему сообщение."
    )
    await _render_partners_list(
        call,
        partners,
        offset=offset,
        text=text,
        keyboard_builder=CuratorKeyboards.partners,
    )


@router.callback_query(F.data.startswith("cur_partner:"))
async def curator_message_prompt(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    try:
        partner_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Не удалось определить пользователя.", show_alert=True)
        return
    if not await svc.is_partner(call.from_user.id, partner_id):
        await call.answer("Этот пользователь больше не связан с вами.", show_alert=True)
        return
    partners = await svc.list_partners(call.from_user.id)
    info = next((p for p in partners if p.get("user_id") == partner_id), None)
    display_name = CuratorKeyboards.format_partner_title(info) if info else f"ID {partner_id}"
    _pending_curator_messages[call.from_user.id] = partner_id
    prompt = (
        f"Напишите сообщение для {html.escape(display_name)}.\n"
        "Используйте кнопку «Отменить», чтобы прекратить отправку."
    )
    try:
        await call.message.answer(
            prompt,
            reply_markup=CuratorKeyboards.cancel_message(),
        )
    except Exception:
        pass
    await call.answer("Введите сообщение", show_alert=False)
@router.message(Command('invite'))
async def handle_invite(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await _require_curator_or_admin_message(message, svc):
        return
    await _send_curator_personal_link(
        message,
        svc,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )


@router.message(Command('static'))
async def handle_curator_full_stats(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await _require_curator_or_admin_message(message, svc):
        return

    result = await prepare_curator_all_time_stats(svc, message.from_user.id)
    if result is None:
        await message.answer("У вас пока нет приглашенных пользователей.")
        return

    document, caption = result
    await message.answer_document(document, caption=caption)

@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message) -> None:
    payload = message.text.split(' ', 1)[1] if ' ' in message.text else ''
    if not payload:
        return
    svc = CuratorService(message.bot)
    is_admin = await _is_admin(message.from_user.id)
    clean_payload = payload.strip()
    curator_id = await svc.find_curator_by_code(clean_payload)
    if not curator_id:
        await message.answer("Ссылка недействительна или устарела.")
        return
    me = await message.bot.get_me()
    source_link = None
    if me.username:
        source_link = build_deeplink(me.username, clean_payload)
    await svc.record_invite_source(
        message.from_user.id,
        curator_id,
        clean_payload,
        source_link or clean_payload,
    )
    if await svc.is_curator(message.from_user.id):
        await svc.register_partner(curator_id, message.from_user.id)
        await _send_curator_personal_link(
            message,
            svc,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        return
    if is_admin:
        link = await _promote_user_to_curator(
            svc,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            inviter_id=curator_id,
            source_link=source_link,
        )
        await message.answer(
            f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await _send_captcha_challenge(message, message.from_user.id, svc, curator_id)
        return

    link = await _promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=curator_id,
        source_link=source_link,
    )
    await message.answer(
        f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
        disable_web_page_preview=True,
    )
    return


@router.message(CommandStart())
async def start_without_payload(message: Message) -> None:
    text = message.text or ""
    if " " in text:
        return
    svc = CuratorService(message.bot)
    is_admin = await _is_admin(message.from_user.id)
    if await svc.is_curator(message.from_user.id):
        await _send_curator_personal_link(
            message,
            svc,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        return
    if is_admin:
        link = await _promote_user_to_curator(
            svc,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            inviter_id=None,
        )
        await message.answer(
            f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await _send_captcha_challenge(
            message,
            message.from_user.id,
            svc,
            0,
        )
        return

    link = await _promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=None,
    )
    await message.answer(
        f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("cur_req:"))
async def request_curation(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    code = call.data.split(':',1)[1]
    curator_id = await svc.find_curator_by_code(code)
    if not curator_id:
        await call.answer("Ссылка устарела.", show_alert=True)
        return
    me = await call.bot.get_me()
    source_link = None
    if me.username:
        source_link = build_deeplink(me.username, code)
    await svc.record_invite_source(
        call.from_user.id,
        curator_id,
        code,
        source_link or code,
    )
    is_curator = await svc.is_curator(call.from_user.id)
    is_admin = await _is_admin(call.from_user.id)
    # Создаём заявку и уведомляем куратора
    if is_curator or is_admin:
        if not is_curator:
            link = await _promote_user_to_curator(
                svc,
                call.bot,
                user_id=call.from_user.id,
                username=call.from_user.username,
                full_name=call.from_user.full_name,
                inviter_id=curator_id,
                source_link=source_link,
            )
            try:
                await call.message.answer(
                    f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
        await svc.register_partner(curator_id, call.from_user.id)
        await call.answer("Вы уже являетесь куратором.", show_alert=True)
        return
    if not await svc.has_passed_captcha(call.from_user.id):
        await call.answer()
        await _send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
        return

    link = await _promote_user_to_curator(
        svc,
        call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
        inviter_id=curator_id,
        source_link=source_link,
    )
    await call.answer()
    try:
        await call.message.edit_text(
            f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            await call.message.answer(
                f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
                disable_web_page_preview=True,
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("cur_cap:"))
async def verify_captcha(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    selected = int(call.data.split(":", 1)[1])
    challenge = await svc.get_captcha_challenge(call.from_user.id)
    if not challenge:
        if await svc.has_passed_captcha(call.from_user.id):
            await call.answer("Капча уже пройдена.")
        else:
            await call.answer("Капча устарела. Пожалуйста, запросите новую ссылку.", show_alert=True)
        return

    curator_id, correct = challenge
    if selected != correct:
        await call.answer("Неверный ответ. Попробуйте ещё раз.", show_alert=True)
        try:
            await call.message.edit_caption(
                "Ответ неверный. Мы отправили новую капчу.", reply_markup=None
            )
        except Exception:
            try:
                await call.message.edit_text(
                    "Ответ неверный. Мы отправили новую капчу.", reply_markup=None
                )
            except Exception:
                pass
        await _send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
        return

    await svc.mark_captcha_passed(call.from_user.id)
    source_info = await svc.get_invite_source(call.from_user.id)
    await call.answer("Верно!", show_alert=False)
    captcha_deleted = False
    try:
        await call.message.delete()
    except Exception:
        try:
            await call.message.edit_caption("✅ Капча успешно пройдена", reply_markup=None)
        except Exception:
            try:
                await call.message.edit_text("✅ Капча успешно пройдена", reply_markup=None)
            except Exception:
                pass
    else:
        captcha_deleted = True

    if captcha_deleted:
        try:
            await call.message.answer("✅ Капча успешно пройдена")
        except Exception:
            pass
    inviter_id = (source_info or {}).get("curator_id") or curator_id
    if inviter_id == 0:
        inviter_id = None
    link = await _promote_user_to_curator(
        svc,
        call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
        inviter_id=inviter_id,
        source_link=(source_info or {}).get("source_link"),
    )
    await call.message.answer(
        f"Теперь вы куратор. Ваша персональная ссылка:\n{link}",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "cur_msg:cancel")
async def cancel_curator_message(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await _require_curator_or_admin_callback(call, svc):
        return
    active = _pending_curator_messages.pop(call.from_user.id, None)
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    if active is None:
        await call.answer("Нет активного действия.", show_alert=True)
        return
    if call.message:
        try:
            await call.message.answer("Действие отменено.")
        except Exception:
            pass
    await call.answer()


@router.message(Command("cancel"))
async def cancel_curator_action(message: Message) -> None:
    if _pending_curator_messages.pop(message.from_user.id, None) is not None:
        await message.answer("Действие отменено.")
    else:
        await message.answer("Нет активного действия.")


@router.message(F.text)
async def handle_curator_outgoing_message(message: Message) -> None:
    partner_id = _pending_curator_messages.get(message.from_user.id)
    if not partner_id:
        return
    trimmed = message.text.strip()
    if trimmed == "/cancel":
        return
    if trimmed.startswith("/"):
        return
    if not trimmed:
        await message.answer("Пожалуйста, отправьте текстовое сообщение или нажмите кнопку «Отменить».")
        return
    svc = CuratorService(message.bot)
    if not await svc.is_partner(message.from_user.id, partner_id):
        _pending_curator_messages.pop(message.from_user.id, None)
        await message.answer("Этот пользователь больше не связан с вами.")
        return
    curator_name = html.escape(message.from_user.full_name or "Куратор")
    text = html.escape(message.text)
    body = f"Сообщение от вашего куратора {curator_name}:\n\n{text}"
    try:
        await message.bot.send_message(partner_id, body)
    except Exception:
        await message.answer("Не удалось отправить сообщение этому пользователю.")
    else:
        await message.answer(
            "Сообщение отправлено.",
            reply_markup=CuratorKeyboards.back_to_menu(),
        )
    finally:
        _pending_curator_messages.pop(message.from_user.id, None)

@router.callback_query(F.data.startswith("cur_acc:"))
async def approve_curator(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    partner_id = int(call.data.split(':',1)[1])
    request_info = await svc.resolve_request(partner_id)
    curator_id = request_info.get("curator_id") if request_info else None
    if curator_id != call.from_user.id:
        await call.answer("Эта заявка не для вас или уже обработана.", show_alert=True)
        return
    await svc.register_partner(curator_id, partner_id)
    username = (request_info or {}).get("username")
    full_name = (request_info or {}).get("full_name") or ""
    if (not username) or (not full_name):
        try:
            chat = await call.bot.get_chat(partner_id)
            username = username or chat.username
            parts = [chat.first_name or "", chat.last_name or ""]
            full_name = full_name or " ".join(part for part in parts if part).strip()
        except Exception:
            pass
    new_link = await svc.promote_to_curator(
        partner_id,
        username,
        full_name,
        source_link=(request_info or {}).get("source_link"),
    )
    await call.answer("Принято", show_alert=False)
    try:
        await call.message.edit_text(call.message.html_text + "\n\n✅ Принято")
    except Exception:
        pass
    try:
        await call.bot.set_my_commands(
            CURATOR_COMMANDS,
            scope=BotCommandScopeChat(chat_id=partner_id),
        )
    except Exception:
        pass
    try:
        await call.bot.send_message(
            partner_id,
            f"Ваша заявка одобрена! Теперь вы куратор.\nВаша ссылка:\n{new_link}",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("cur_dec:"))
async def decline_curator(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    partner_id = int(call.data.split(':',1)[1])
    _ = await svc.resolve_request(partner_id)
    await call.answer("Отклонено", show_alert=False)
    try:
        await call.message.edit_text(call.message.html_text + "\n\n❌ Отклонено")
    except Exception:
        pass
    try:
        await call.bot.send_message(partner_id, "К сожалению, ваша заявка отклонена.")
    except Exception:
        pass
