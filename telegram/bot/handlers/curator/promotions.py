from aiogram import F
from aiogram.types import Message

from ...config import Config
from ...services.curator_service import CuratorService
from ...utils.handlers_helpers import (
    answer_with_group_timeout,
    delete_group_message,
    is_primary_group,
    promote_user_to_curator,
    send_plus_invite_package,
)
from . import router


async def _promote_by_group_trigger(
    message: Message,
    *,
    inviter_id: int | None,
    source_link: str,
    require_open_invite: bool = True,
) -> None:
    if not is_primary_group(message):
        return

    svc = CuratorService(message.bot)

    source_data = await svc.get_invite_source(message.from_user.id)
    if inviter_id is None:
        inviter_id = (source_data or {}).get("curator_id")
    if source_data and source_data.get("source_link"):
        source_link = source_data["source_link"]

    if require_open_invite and not await svc.is_open_invite_enabled():
        return

    if await svc.is_curator(message.from_user.id):
        await answer_with_group_timeout(
            message, "Вы уже являетесь зарегестрированным пользователем."
        )
        return

    link = await promote_user_to_curator(
        svc,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        inviter_id=inviter_id,
        source_link=source_link,
        is_group_member=True,
        notification_context="plus" if source_link == "self_plus_invite" else "group",
        group_chat=message.chat,
    )

    await answer_with_group_timeout(
        message,
        (
            "Теперь вы зарегестрированы. Ваша персональная ссылка:\n"
            f"{link}\n\nМеню доступно в личном чате с ботом."
        ),
        disable_web_page_preview=True,
    )

    if source_link == "self_plus_invite":
        await send_plus_invite_package(message.bot, message.from_user.id, link)


@router.message(
    F.text.func(
        lambda text: text is not None
        and text.strip().casefold() == "рег"
    )
)
async def promote_by_message(message: Message) -> None:
    try:
        inviter_id = Config.PRIMARY_SUPER_ADMIN
        if inviter_id is None:
            await answer_with_group_timeout(
                message, "Функция временно недоступна: не задан супер-администратор."
            )
            return

        await _promote_by_group_trigger(
            message,
            inviter_id=inviter_id,
            source_link="super_admin_invite",
            require_open_invite=True,
        )
    finally:
        delete_group_message(message)


@router.message(F.text.func(lambda text: text is not None and text.strip() == "+"))
async def promote_by_plus_sign(message: Message) -> None:
    try:
        await _promote_by_group_trigger(
            message,
            inviter_id=None,
            source_link="self_plus_invite",
            require_open_invite=False,
        )
    finally:
        delete_group_message(message)
