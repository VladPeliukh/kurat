from aiogram import F
from aiogram.types import CallbackQuery

from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    is_admin,
    promote_user_to_curator,
    resolve_inviter_name,
    send_captcha_challenge,
    send_welcome_video,
    set_curator_commands,
)
from ...utils.helpers import build_deeplink
from . import router


@router.callback_query(F.data.startswith("cur_req:"))
async def request_curation(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    code = call.data.split(":", 1)[1]
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
    admin = await is_admin(call.from_user.id)
    if is_curator or admin:
        if not is_curator:
            link = await promote_user_to_curator(
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
                    f"Теперь вы зарегестрированы. Ваша персональная ссылка:\n{link}",
                    disable_web_page_preview=True,
                )
                inviter_name = await resolve_inviter_name(svc, curator_id)
                await send_welcome_video(call.bot, call.from_user.id, inviter_name, link)
            except Exception:
                pass
        await svc.register_partner(curator_id, call.from_user.id)
        await call.answer("Вы уже являетесь зарегестрированным пользователем.", show_alert=True)
        return
    if not await svc.has_passed_captcha(call.from_user.id):
        await call.answer()
        await send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
        return

    link = await promote_user_to_curator(
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
            f"Теперь вы зарегестрированы. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            await call.message.answer(
                f"Теперь вы зарегестрированы. Ваша персональная ссылка:\n{link}",
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    inviter_name = await resolve_inviter_name(svc, curator_id)
    await send_welcome_video(call.bot, call.from_user.id, inviter_name, link)


@router.callback_query(F.data.startswith("cur_acc:"))
async def approve_curator(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    partner_id = int(call.data.split(":", 1)[1])
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
    await set_curator_commands(call.bot, partner_id)
    try:
        await call.bot.send_message(
            partner_id,
            f"Ваша заявка одобрена! Теперь вы зарегестрированы.\nВаша ссылка:\n{new_link}",
            disable_web_page_preview=True,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("cur_dec:"))
async def decline_curator(call: CallbackQuery):
    svc = CuratorService(call.message.bot)
    partner_id = int(call.data.split(":", 1)[1])
    await svc.resolve_request(partner_id)
    await call.answer("Отклонено", show_alert=False)
    try:
        await call.message.edit_text(call.message.html_text + "\n\n❌ Отклонено")
    except Exception:
        pass
    try:
        await call.bot.send_message(partner_id, "К сожалению, ваша заявка отклонена.")
    except Exception:
        pass
