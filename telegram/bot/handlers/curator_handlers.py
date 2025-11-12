import html
import random
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..keyboards import captcha_options_keyboard, curator_request_keyboard
from ..services.curator_service import CuratorService
from ..utils.captcha import NumberCaptcha

router = Router()
_captcha_generator = NumberCaptcha()


def _build_captcha_options(correct_answer: int, total: int = 4) -> list[int]:
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
) -> None:
    await svc.request_join(curator_id, partner_id)
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


async def _finalize_request(message: Message, svc: CuratorService, curator_id: int) -> None:
    await _notify_curator(svc, curator_id, message.from_user.id, message.from_user.full_name, message.bot)
    await message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")

@router.message(Command('invite'))
async def handle_invite(message: Message) -> None:
    svc = CuratorService(message.bot)
    if not await svc.is_curator(message.from_user.id):
        await message.answer("Эта команда доступна только кураторам.")
        return
    link = await svc.get_or_create_personal_link(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    count = await svc.partners_count(message.from_user.id)
    await message.answer(f"Ваша персональная ссылка:\n{link}\n\nПриглашено: {count}")

@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message) -> None:
    payload = message.text.split(' ', 1)[1] if ' ' in message.text else ''
    if not payload:
        return
    svc = CuratorService(message.bot)
    curator_id = await svc.find_curator_by_code(payload.strip())
    if not curator_id:
        await message.answer("Ссылка недействительна или устарела.")
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await _send_captcha_challenge(message, message.from_user.id, svc, curator_id)
        return

    await _finalize_request(message, svc, curator_id)
    return


@router.callback_query(F.data.startswith("cur_req:"))
async def request_curation(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    code = call.data.split(':',1)[1]
    curator_id = await svc.find_curator_by_code(code)
    if not curator_id:
        await call.answer("Ссылка устарела.", show_alert=True)
        return
    # Создаём заявку и уведомляем куратора
    if not await svc.has_passed_captcha(call.from_user.id):
        await call.answer()
        await _send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
        return

    await _notify_curator(svc, curator_id, call.from_user.id, call.from_user.full_name, call.bot)
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
    await call.answer("Верно!", show_alert=False)
    try:
        await call.message.edit_caption("✅ Капча успешно пройдена", reply_markup=None)
    except Exception:
        try:
            await call.message.edit_text("✅ Капча успешно пройдена", reply_markup=None)
        except Exception:
            pass

    await _notify_curator(svc, curator_id, call.from_user.id, call.from_user.full_name, call.bot)
    await call.message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")

@router.callback_query(F.data.startswith("cur_acc:"))
async def approve_curator(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    partner_id = int(call.data.split(':',1)[1])
    curator_id = await svc.resolve_request(partner_id)
    if curator_id != call.from_user.id:
        await call.answer("Эта заявка не для вас или уже обработана.", show_alert=True)
        return
    await svc.register_partner(curator_id, partner_id)
    new_link = await svc.promote_to_curator(partner_id, None, "")
    await call.answer("Принято", show_alert=False)
    try:
        await call.message.edit_text(call.message.html_text + "\n\n✅ Принято")
    except Exception:
        pass
    try:
        await call.bot.send_message(partner_id, f"Ваша заявка одобрена! Теперь вы куратор.\nВаша ссылка:\n{new_link}")
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
