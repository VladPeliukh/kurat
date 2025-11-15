import html
import random
from datetime import datetime, timezone
from typing import Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)
from zoneinfo import ZoneInfo

from ..keyboards import (
    captcha_options_keyboard,
    curator_cancel_message_keyboard,
    curator_back_to_menu_keyboard,
    curator_invite_keyboard,
    curator_main_menu_keyboard,
    curator_partners_keyboard,
    curator_request_keyboard,
    format_partner_title,
)
from ..services.curator_service import CuratorService
from ..utils.captcha import NumberCaptcha
from ..utils.commands import CURATOR_COMMANDS
from ..utils.helpers import build_deeplink
from ..utils.csv_export import build_simple_table_csv

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

router = Router()
_captcha_generator = NumberCaptcha()
_pending_curator_messages: dict[int, int] = {}
_CURATOR_PARTNERS_PAGE_SIZE = 10


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
        reply_markup=curator_invite_keyboard(),
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
    keyboard = captcha_options_keyboard(options)
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
    keyboard = curator_request_keyboard(partner_id)
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


@router.message(Command('curator'))
async def show_curator_menu(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await svc.is_curator(message.from_user.id):
        await message.answer("Эта команда доступна только кураторам.")
        return
    _pending_curator_messages.pop(message.from_user.id, None)
    await message.answer(
        "МЕНЮ КУРАТОРА",
        reply_markup=curator_main_menu_keyboard(),
    )


@router.callback_query(F.data == "cur_menu:open")
async def curator_menu_open(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
        return
    _pending_curator_messages.pop(call.from_user.id, None)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await call.message.answer(
            "МЕНЮ КУРАТОРА",
            reply_markup=curator_main_menu_keyboard(),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "cur_menu:back")
async def curator_menu_back(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
        return
    _pending_curator_messages.pop(call.from_user.id, None)
    keyboard = curator_main_menu_keyboard()
    try:
        await call.message.edit_text("МЕНЮ КУРАТОРА", reply_markup=keyboard)
    except Exception:
        await call.message.answer("МЕНЮ КУРАТОРА", reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data == "cur_menu:partners")
async def curator_show_partners(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
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
        keyboard_builder=curator_partners_keyboard,
    )


@router.callback_query(F.data == "cur_menu:invite")
async def curator_show_invite(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
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
async def curator_show_stats(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
        return
    partners = await svc.list_partners(call.from_user.id)
    if not partners:
        await call.answer("У вас пока нет приглашенных пользователей.", show_alert=True)
        return
    headers = [
        "ID",
        "Имя",
        "Username",
        "Ссылка приглашения",
        "Персональная ссылка",
        "Дата и время назначения",
    ]
    rows: list[list[str | int]] = []
    for partner in partners:
        partner_id = partner.get("user_id")
        if not partner_id:
            continue
        stats = await svc.get_partner_statistics(call.from_user.id, partner_id)
        if not stats:
            stats = {
                "user_id": partner_id,
                "full_name": partner.get("full_name") or "",
                "username": partner.get("username"),
                "source_link": None,
                "invite_link": None,
                "promoted_at": None,
            }
        username = stats.get("username") or partner.get("username") or ""
        if username and not username.startswith("@"):
            username = f"@{username}"
        promoted_at = stats.get("promoted_at")
        promoted_text = ""
        if promoted_at:
            try:
                dt = datetime.fromisoformat(promoted_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(MOSCOW_TZ)
                promoted_text = dt.strftime("%d.%m.%Y %H:%M:%S")
            except Exception:
                promoted_text = promoted_at
        rows.append(
            [
                stats.get("user_id") or partner_id,
                stats.get("full_name") or partner.get("full_name") or "",
                username,
                stats.get("source_link") or "",
                stats.get("invite_link") or "",
                promoted_text,
            ]
        )
    if not rows:
        await call.answer("Не удалось подготовить данные.", show_alert=True)
        return
    csv_bytes = build_simple_table_csv(headers, rows)
    document = BufferedInputFile(
        csv_bytes,
        filename=f"curator_stats_{call.from_user.id}.csv",
    )
    await call.message.answer_document(
        document,
        caption="Ваша статистика приглашенных пользователей.",
    )
    await call.answer()


@router.callback_query(F.data.startswith("cur_partners_page:"))
async def curator_partners_next_page(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
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
        keyboard_builder=curator_partners_keyboard,
    )


@router.callback_query(F.data.startswith("cur_partner:"))
async def curator_message_prompt(call: CallbackQuery) -> None:
    svc = CuratorService(call.message.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
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
    display_name = format_partner_title(info) if info else f"ID {partner_id}"
    _pending_curator_messages[call.from_user.id] = partner_id
    prompt = (
        f"Напишите сообщение для {html.escape(display_name)}.\n"
        "Используйте кнопку «Отменить», чтобы прекратить отправку."
    )
    try:
        await call.message.answer(
            prompt,
            reply_markup=curator_cancel_message_keyboard(),
        )
    except Exception:
        pass
    await call.answer("Введите сообщение", show_alert=False)
@router.message(Command('invite'))
async def handle_invite(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await svc.is_curator(message.from_user.id):
        await message.answer("Эта команда доступна только кураторам.")
        return
    await _send_curator_personal_link(
        message,
        svc,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message) -> None:
    payload = message.text.split(' ', 1)[1] if ' ' in message.text else ''
    if not payload:
        return
    svc = CuratorService(message.bot)
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
        await message.answer("Вы уже являетесь куратором.")
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await _send_captcha_challenge(message, message.from_user.id, svc, curator_id)
        return

    await _finalize_request(
        message,
        svc,
        curator_id,
        source_link=source_link,
        payload=clean_payload,
    )
    return


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
    # Создаём заявку и уведомляем куратора
    if await svc.is_curator(call.from_user.id):
        await call.answer("Вы уже являетесь куратором.", show_alert=True)
        return
    if not await svc.has_passed_captcha(call.from_user.id):
        await call.answer()
        await _send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
        return

    await _notify_curator(
        svc,
        curator_id,
        call.from_user.id,
        call.from_user.full_name,
        call.bot,
        username=call.from_user.username,
        source_link=source_link,
        payload=code,
    )
    await call.answer()  # закрыть "часики"
    try:
        await call.message.edit_text("Заявка отправлена вашему куратору. Ожидайте решения.")
    except Exception:
        try:
            await call.message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")
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

    await _notify_curator(
        svc,
        curator_id,
        call.from_user.id,
        call.from_user.full_name,
        call.bot,
        username=call.from_user.username,
        source_link=(source_info or {}).get("source_link"),
        payload=(source_info or {}).get("payload"),
    )
    await call.message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")


@router.callback_query(F.data == "cur_msg:cancel")
async def cancel_curator_message(call: CallbackQuery) -> None:
    svc = CuratorService(call.bot)
    if not await svc.is_curator(call.from_user.id):
        await call.answer("Эта функция доступна только кураторам.", show_alert=True)
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
            reply_markup=curator_back_to_menu_keyboard(),
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
