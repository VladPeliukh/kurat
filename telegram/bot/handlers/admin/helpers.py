from aiogram.types import Message

from ...services.admin_service import AdminService


_open_invite_toggle_locked = False


async def _is_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_admin(user_id)


async def _is_super_admin(user_id: int) -> bool:
    admin_service = AdminService()
    return await admin_service.is_super_admin(user_id)


def _is_private_chat(message: Message) -> bool:
    return message.chat.type == "private"


def is_open_invite_toggle_locked() -> bool:
    return _open_invite_toggle_locked


def lock_open_invite_toggle() -> None:
    global _open_invite_toggle_locked
    _open_invite_toggle_locked = True


__all__ = [
    "_is_admin",
    "_is_super_admin",
    "_is_private_chat",
    "is_open_invite_toggle_locked",
    "lock_open_invite_toggle",
]
