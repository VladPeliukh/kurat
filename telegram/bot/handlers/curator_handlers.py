from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ..services.curator_service import CuratorService

router = Router()

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
    await svc.request_join(curator_id, message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять", callback_data=f"cur_acc:{message.from_user.id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"cur_dec:{message.from_user.id}")
    ]])
    try:
        await message.bot.send_message(
            curator_id,
            f"Заявка от <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a> стать куратором.",
            reply_markup=kb
        )
    except Exception:
        pass
    await message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")
    if not payload:
        return
    svc = CuratorService(message.bot)
    curator_id = await svc.find_curator_by_code(payload.strip())
    if not curator_id:
        await message.answer("Ссылка недействительна или устарела.")
        return
    # Показываем пользователю кнопку "Подать заявку"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Подать заявку", callback_data=f"cur_req:{payload.strip()}")
    ]])
    await message.answer(
        "Вы пришли по пригласительной ссылке куратора.\nНажмите «Подать заявку», чтобы отправить запрос стать куратором.",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("cur_req:"))
async def request_curation(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    code = call.data.split(':',1)[1]
    curator_id = await svc.find_curator_by_code(code)
    if not curator_id:
        await call.answer("Ссылка устарела.", show_alert=True)
        return
    # Создаём заявку и уведомляем куратора
    await svc.request_join(curator_id, call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять", callback_data=f"cur_acc:{call.from_user.id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"cur_dec:{call.from_user.id}")
    ]])
    try:
        await call.bot.send_message(
            curator_id,
            f"Заявка от <a href='tg://user?id={call.from_user.id}'>{call.from_user.full_name}</a> стать куратором.",
            reply_markup=kb
        )
    except Exception:
        pass
    await call.answer()  # закрыть "часики"
    try:
        await call.message.edit_text("Заявка отправлена вашему куратору. Ожидайте решения.")
    except Exception:
        try:
            await call.message.answer("Заявка отправлена вашему куратору. Ожидайте решения.")
        except Exception:
            pass

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