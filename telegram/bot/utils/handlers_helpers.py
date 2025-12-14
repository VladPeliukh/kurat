import asyncio
import html
import random
from contextlib import suppress
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Literal

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
)
from zoneinfo import ZoneInfo

from ..config import Config
from ..keyboards import CaptchaKeyboards, CuratorKeyboards
from ..keyboards.calendar import (
    AdminCalendarCallback,
    CalendarState,
    CalendarView,
    CuratorCalendarCallback,
    CuratorCalendarKeyboard,
)
from ..services.admin_service import AdminService
from ..services.curator_service import CuratorService
from ..utils.commands import ADMIN_COMMANDS, CURATOR_COMMANDS
from .captcha import NumberCaptcha

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
CURATOR_PARTNERS_PAGE_SIZE = 10
GROUP_MESSAGE_LIFETIME_SECONDS = 15
WELCOME_VIDEO_FILENAME = "вид.mp4"
PLUS_INVITE_IMAGE_FILENAME = "img1.jpeg"

NOTIFICATION_TEXT = """
<a href='tg://user?id={user_id}'><b>{notification_msg}</b></a>
{user_username}
<b>Ник:</b> <i>{user_fullname}</i>
<b>Время Подписки:</b> <code>{invite_time}</code>
<b>User ID:</b> <code>{user_id}</code>
<b>Всего партнёров: {partners_count}</b>
"""

_open_invite_toggle_locked = False

_captcha_generator = NumberCaptcha()


async def is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


async def is_super_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_super_admin(user_id)


async def has_curator_access(bot: Bot, user_id: int, svc: CuratorService | None = None) -> bool:
    if await is_admin(user_id):
        return True
    if svc is not None:
        return await svc.is_curator(user_id)
    return await CuratorService(bot).is_curator(user_id)


async def require_curator_or_admin_message(message: Message, svc: CuratorService) -> bool:
    if await has_curator_access(message.bot, message.from_user.id, svc):
        return True
    await message.answer("Эта команда доступна только зарегестрированным пользователям и администраторам.")
    return False


async def require_curator_or_admin_callback(call: CallbackQuery, svc: CuratorService) -> bool:
    if await has_curator_access(call.bot, call.from_user.id, svc):
        return True
    await call.answer(
        "Эта функция доступна только зарегестрированным пользователям и администраторам.",
        show_alert=True,
    )
    return False


def is_private_chat(message: Message) -> bool:
    return message.chat.type == "private"


_is_admin = is_admin
_is_super_admin = is_super_admin
_is_private_chat = is_private_chat


def is_open_invite_toggle_locked() -> bool:
    return _open_invite_toggle_locked


def lock_open_invite_toggle() -> None:
    global _open_invite_toggle_locked
    _open_invite_toggle_locked = True


# Calendar helpers

def initial_calendar_state(reference: date | None = None) -> CalendarState:
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


def serialize_calendar_state(state: CalendarState) -> dict:
    return {
        "year": state.year,
        "month": state.month,
        "view": state.view.value,
        "year_page": state.year_page,
    }


def deserialize_calendar_state(
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
    return initial_calendar_state(reference)


def refresh_year_page(state: CalendarState) -> None:
    state.year_page = state.year - (state.year % 12 or 12)
    if state.year_page < 1:
        state.year_page = 1


async def get_calendar_state(state: FSMContext, target: str) -> CalendarState:
    data = await state.get_data()
    key = f"{target}_calendar"
    return deserialize_calendar_state(data.get(key))


async def store_calendar_state(
    state: FSMContext,
    target: str,
    calendar_state: CalendarState,
) -> None:
    await state.update_data(**{f"{target}_calendar": serialize_calendar_state(calendar_state)})


async def store_selected_date(
    state: FSMContext,
    target: str,
    selected_date: date | None,
) -> None:
    await state.update_data(
        **{
            f"{target}_date": selected_date.isoformat() if selected_date else None,
        }
    )


async def get_selected_date(state: FSMContext, target: str) -> date | None:
    data = await state.get_data()
    raw = data.get(f"{target}_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


async def refresh_calendar_markup(
    call: CallbackQuery,
    *,
    target: str,
    calendar_state: CalendarState,
    callback_factory: type[AdminCalendarCallback] | None = None,
) -> None:
    try:
        await call.message.edit_reply_markup(
            reply_markup=CuratorCalendarKeyboard.build(
                calendar_state,
                target=target,
                callback_factory=callback_factory or CuratorCalendarCallback,
            )
        )
    except Exception:
        pass


_initial_calendar_state = initial_calendar_state
_serialize_calendar_state = serialize_calendar_state
_deserialize_calendar_state = deserialize_calendar_state
_refresh_year_page = refresh_year_page
_get_calendar_state = get_calendar_state
_store_calendar_state = store_calendar_state
_store_selected_date = store_selected_date
_get_selected_date = get_selected_date
_refresh_calendar_markup = refresh_calendar_markup


# Invite helpers

async def send_curator_personal_link(
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


# Captcha helpers

def build_captcha_options(correct_answer: int, total: int = 9) -> list[int]:
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


async def send_captcha_challenge(message: Message, user_id: int, svc: CuratorService, curator_id: int) -> None:
    answer, image_bytes = await _captcha_generator.random_captcha()
    options = build_captcha_options(answer)
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


async def render_partners_list(
    call: CallbackQuery,
    partners: list[dict],
    *,
    offset: int,
    text: str,
    keyboard_builder: Callable[..., InlineKeyboardMarkup],
) -> None:
    keyboard_markup = keyboard_builder(
        partners,
        offset=offset,
        page_size=CURATOR_PARTNERS_PAGE_SIZE,
    )
    try:
        await call.message.edit_text(text, reply_markup=keyboard_markup)
    except Exception:
        await call.message.answer(text, reply_markup=keyboard_markup)
    await call.answer()


def _format_notification_base(
    *,
    notification_msg: str,
    user_id: int,
    username: str | None,
    full_name: str | None,
    invite_time: datetime,
    partners_count: int,
    invite_link: str | None = None,
) -> str:
    formatted = NOTIFICATION_TEXT.format(
        user_id=user_id,
        user_username=f"@{username}" if username else "—",
        invite_time=invite_time.strftime("%d.%m.%Y"),
        notification_msg=notification_msg,
        user_fullname=full_name or "—",
        partners_count=partners_count,
    )
    if invite_link:
        formatted = (
            formatted
            + "\n"
            + f"<b>Использованная ссылка:</b> <code>{html.escape(invite_link)}</code>"
        )
    return formatted


def format_group_notification_text(
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    chat: Chat,
    partners_count: int,
    invite_time: datetime,
    invite_link: str | None,
) -> str:
    notification_msg = "🎉У ВАС НОВЫЙ КАНДИДАТ В ЧАТЕ🎉"
    base = _format_notification_base(
        notification_msg=notification_msg,
        user_id=user_id,
        username=username,
        full_name=full_name,
        invite_time=invite_time,
        partners_count=partners_count,
        invite_link=invite_link,
    )
    return (
        f"<a href='tg://group?id={chat.id}'><b>Группа {chat.full_name}</b></a>\n"
        + base
    )


def format_bot_notification_text(
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    partners_count: int,
    invite_time: datetime,
    invite_link: str | None,
    is_in_table: bool,
) -> str:
    notification_msg = "🎉У ВАС НОВЫЙ КАНДИДАТ ПО ССЫЛКЕ🎉"
    if is_in_table:
        notification_msg = "ℹ️ ПОЛЬЗОВАТЕЛЬ УЖЕ В ВАШЕЙ БАЗЕ"
    base = _format_notification_base(
        notification_msg=notification_msg,
        user_id=user_id,
        username=username,
        full_name=full_name,
        invite_time=invite_time,
        partners_count=partners_count,
        invite_link=invite_link,
    )
    if is_in_table:
        return base + "\n\nПользователь уже есть в вашей партнёрской таблице."
    return base


def format_plus_notification_text(
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    partners_count: int,
    invite_time: datetime,
    invite_link: str | None,
) -> str:
    notification_msg = "🎉 У ВАС НОВЫЙ ПЛЮС 🎉"
    return _format_notification_base(
        notification_msg=notification_msg,
        user_id=user_id,
        username=username,
        full_name=full_name,
        invite_time=invite_time,
        partners_count=partners_count,
        invite_link=invite_link,
    )


async def send_message_notification(
    svc: CuratorService,
    *,
    curator_id: int,
    partner_id: int,
    username: str | None,
    full_name: str | None,
    where: Literal["bot", "group", "plus"],
    chat: Chat | None = None,
    invite_link: str | None = None,
    is_in_table: bool = False,
) -> None:
    partners_count = await svc.partners_count(curator_id)
    invite_time = datetime.now(MOSCOW_TZ)
    text: str | None = None

    if where == "group" and chat is not None:
        text = format_group_notification_text(
            user_id=partner_id,
            username=username,
            full_name=full_name,
            chat=chat,
            partners_count=partners_count,
            invite_time=invite_time,
            invite_link=invite_link,
        )
    elif where == "plus":
        text = format_plus_notification_text(
            user_id=partner_id,
            username=username,
            full_name=full_name,
            partners_count=partners_count,
            invite_time=invite_time,
            invite_link=invite_link,
        )
    else:
        text = format_bot_notification_text(
            user_id=partner_id,
            username=username,
            full_name=full_name,
            partners_count=partners_count,
            invite_time=invite_time,
            invite_link=invite_link,
            is_in_table=is_in_table,
        )

    try:
        await svc.bot.send_message(
            curator_id,
            text,
            reply_markup=CuratorKeyboards.notification_actions(partner_id),
        )
    except Exception:
        pass


async def notify_curator(
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
    keyboard_markup = CuratorKeyboards.request(partner_id)
    safe_name = html.escape(full_name or "")
    try:
        await bot.send_message(
            curator_id,
            f"Заявка от <a href='tg://user?id={partner_id}'>{safe_name}</a>.",
            reply_markup=keyboard_markup,
        )
    except Exception:
        pass


async def finalize_request(
    message: Message,
    svc: CuratorService,
    curator_id: int,
    *,
    source_link: str | None = None,
    payload: str | None = None,
) -> None:
    await notify_curator(
        svc,
        curator_id,
        message.from_user.id,
        message.from_user.full_name,
        message.bot,
        username=message.from_user.username,
        source_link=source_link,
        payload=payload,
    )
    await message.answer("Заявка отправлена пользователю, который вас пригласил. Ожидайте решения.")


async def ensure_inviter_record(svc: CuratorService, bot: Bot, inviter_id: int | None) -> None:
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


async def set_curator_commands(bot: Bot, user_id: int) -> None:
    admin_service = AdminService()
    try:
        if await admin_service.is_admin(user_id):
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=user_id),
            )
            return
        await bot.set_my_commands(
            CURATOR_COMMANDS,
            scope=BotCommandScopeChat(chat_id=user_id),
        )
    except Exception:
        pass


async def resolve_inviter_name(svc: CuratorService, inviter_id: int | None) -> str:
    if not inviter_id:
        return "Неизвестно"

    record = await svc.get_curator_record(inviter_id)
    if record:
        full_name = (record.get("full_name") or "").strip()
        username = record.get("username")
        if full_name:
            return full_name
        if username:
            return f"@{username}"

    try:
        chat = await svc.bot.get_chat(inviter_id)
        name_parts = [chat.first_name or "", chat.last_name or ""]
        full_name = " ".join(part for part in name_parts if part).strip()
        if full_name:
            return full_name
        if chat.username:
            return f"@{chat.username}"
    except Exception:
        pass

    return "Неизвестно"


async def send_welcome_video(bot: Bot, user_id: int, inviter_name: str, invite_link: str) -> None:
    caption = (
        "Добро пожаловать в чат СТЭП-БРЭЙФИНГ!\n\n"
        f"👤 Ваш пригласитель: {inviter_name}\n"
        f"🔗 Ваша ссылка для приглашения в этот чат: {invite_link}\n\n"
        "Изучите возможности СТЭП-БРЭЙФИНГ .\n"
        "Кнопка в закрепе 'НАВИГАЦИЯ'"
    )
    try:
        await bot.send_video(
            user_id,
            'BAACAgIAAxkDAAMQaTmZiYTz_rR4Zse5SmD7-6QOduAAAsSPAAIU18lJGFU7p5fNe6o2BA',
            caption=caption,
            reply_markup=CuratorKeyboards.navigation(),
        )
    except FileNotFoundError:
        with suppress(Exception):
            await bot.send_message(user_id, caption)
    except Exception:
        with suppress(Exception):
            await bot.send_message(user_id, caption)


async def send_plus_invite_package(bot: Bot, user_id: int, invite_link: str) -> None:
    caption = (
        "Здравствуйте! 🌿\n"
        "Вы нажали «+».\n\n"
        f"🔗 Ваша персона. ссылка для приглашения: {invite_link}\n\n"
    )
    try:
        await bot.send_photo(
            user_id,
            'AgACAgIAAxkDAAMWaTmbji9m9l5D9vgFiUJIaixUcz4AAvYRaxsU18lJiu4PT7wgLD4BAAMCAANtAAM2BA',
            caption=caption,
        )
    except Exception:
        with suppress(Exception):
            await bot.send_message(user_id, caption)


async def promote_user_to_curator(
    svc: CuratorService,
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    inviter_id: int | None = None,
    source_link: str | None = None,
    is_group_member: bool | None = None,
    notification_context: Literal["bot", "group", "plus"] | None = None,
    group_chat: Chat | None = None,
) -> str:
    await ensure_inviter_record(svc, bot, inviter_id)
    is_in_table = False
    if inviter_id:
        is_in_table = await svc.is_partner(inviter_id, user_id)
        await svc.register_partner(inviter_id, user_id)
    link = await svc.promote_to_curator(
        user_id,
        username,
        full_name or "",
        source_link=source_link,
        is_group_member=is_group_member,
    )
    await set_curator_commands(bot, user_id)
    if inviter_id:
        await send_message_notification(
            svc,
            curator_id=inviter_id,
            partner_id=user_id,
            username=username,
            full_name=full_name,
            where=notification_context or "bot",
            chat=group_chat,
            invite_link=source_link,
            is_in_table=is_in_table,
        )
    return link


# Group helpers

def is_primary_group(message: Message) -> bool:
    if Config.PRIMARY_GROUP_ID:
        return message.chat.id == Config.PRIMARY_GROUP_ID
    return message.chat.type in {"group", "supergroup"}


def delete_group_message(message: Message) -> None:
    if not is_primary_group(message):
        return

    with suppress(Exception):
        asyncio.create_task(
            message.bot.delete_message(message.chat.id, message.message_id)
        )


def schedule_group_message_deletion(message: Message) -> None:
    async def _delete_later() -> None:
        await asyncio.sleep(GROUP_MESSAGE_LIFETIME_SECONDS)
        with suppress(Exception):
            await message.bot.delete_message(message.chat.id, message.message_id)

    asyncio.create_task(_delete_later())


async def answer_with_group_timeout(message: Message, *args, **kwargs) -> Message:
    response = await message.answer(*args, **kwargs)
    if is_primary_group(message):
        schedule_group_message_deletion(response)
    return response


__all__ = [
    "MOSCOW_TZ",
    "CURATOR_PARTNERS_PAGE_SIZE",
    "GROUP_MESSAGE_LIFETIME_SECONDS",
    "WELCOME_VIDEO_FILENAME",
    "PLUS_INVITE_IMAGE_FILENAME",
    "NOTIFICATION_TEXT",
    "_deserialize_calendar_state",
    "_get_calendar_state",
    "_get_selected_date",
    "_initial_calendar_state",
    "_is_admin",
    "_is_private_chat",
    "_is_super_admin",
    "_refresh_calendar_markup",
    "_refresh_year_page",
    "_serialize_calendar_state",
    "_store_calendar_state",
    "_store_selected_date",
    "answer_with_group_timeout",
    "build_captcha_options",
    "delete_group_message",
    "deserialize_calendar_state",
    "ensure_inviter_record",
    "finalize_request",
    "get_calendar_state",
    "get_selected_date",
    "has_curator_access",
    "initial_calendar_state",
    "is_admin",
    "is_open_invite_toggle_locked",
    "is_primary_group",
    "is_private_chat",
    "is_super_admin",
    "lock_open_invite_toggle",
    "notify_curator",
    "promote_user_to_curator",
    "send_message_notification",
    "format_bot_notification_text",
    "format_group_notification_text",
    "format_plus_notification_text",
    "refresh_calendar_markup",
    "refresh_year_page",
    "render_partners_list",
    "require_curator_or_admin_callback",
    "require_curator_or_admin_message",
    "resolve_inviter_name",
    "schedule_group_message_deletion",
    "send_captcha_challenge",
    "send_curator_personal_link",
    "send_plus_invite_package",
    "send_welcome_video",
    "serialize_calendar_state",
    "set_curator_commands",
    "store_calendar_state",
    "store_selected_date",
]
