from aiogram import F
from aiogram.types import CallbackQuery

from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    promote_user_to_curator,
    resolve_inviter_name,
    send_captcha_challenge,
    send_welcome_video,
)
from . import router


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
        await call.message.delete()
        await send_captcha_challenge(call.message, call.from_user.id, svc, curator_id)
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
    link = await promote_user_to_curator(
        svc,
        call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
        inviter_id=inviter_id,
        source_link=(source_info or {}).get("source_link"),
        notification_context="bot",
    )
    inviter_name = await resolve_inviter_name(svc, inviter_id)
    await send_welcome_video(call.bot, call.from_user.id, inviter_name, link)
