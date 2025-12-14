from aiogram.filters import CommandStart
from aiogram.types import Message

from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    is_admin,
    is_private_chat,
    promote_user_to_curator,
    resolve_inviter_name,
    send_captcha_challenge,
    send_curator_personal_link,
    send_welcome_video,
)
from ...utils.helpers import build_deeplink
from . import router


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message) -> None:
    if not is_private_chat(message):
        return
    payload = message.text.split(" ", 1)[1] if " " in message.text else ""
    if not payload:
        return
    svc = CuratorService(message.bot)
    admin = await is_admin(message.from_user.id)
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
        await send_curator_personal_link(
            message,
            svc,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        return
    if admin:
        link = await promote_user_to_curator(
            svc,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            inviter_id=curator_id,
            source_link=source_link,
        )
        await message.answer(
            f"Теперь вы зарегестрированы. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
        inviter_name = await resolve_inviter_name(svc, curator_id)
        await send_welcome_video(message.bot, message.from_user.id, inviter_name, link)
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await send_captcha_challenge(message, message.from_user.id, svc, curator_id)
        return

    link = await promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=curator_id,
        source_link=source_link,
    )
    inviter_name = await resolve_inviter_name(svc, curator_id)
    await send_welcome_video(message.bot, message.from_user.id, inviter_name, link)
    return


@router.message(CommandStart())
async def start_without_payload(message: Message) -> None:
    if not is_private_chat(message):
        return
    text = message.text or ""
    if " " in text:
        return
    svc = CuratorService(message.bot)
    admin = await is_admin(message.from_user.id)
    if await svc.is_curator(message.from_user.id):
        await send_curator_personal_link(
            message,
            svc,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        return
    if admin:
        link = await promote_user_to_curator(
            svc,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            inviter_id=None,
        )
        await message.answer(
            f"Теперь вы зарегестрированы. Ваша персональная ссылка:\n{link}",
            disable_web_page_preview=True,
        )
        return
    if not await svc.has_passed_captcha(message.from_user.id):
        await send_captcha_challenge(
            message,
            message.from_user.id,
            svc,
            0,
        )
        return

    link = await promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=None,
    )
