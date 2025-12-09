from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNotFound
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from ..services import Services

CURATOR_COMMANDS: list[BotCommand] = [
    BotCommand(command="invite", description="Моя пригласительная ссылка"),
    BotCommand(command="menu", description="Основное меню"),
    BotCommand(command="static", description="Моя статистика за всё время"),
]
ADMIN_COMMANDS: list[BotCommand] = [
    BotCommand(command="admin", description="Меню администратора"),
    *CURATOR_COMMANDS,
]

WELCOME_MESSAGE = (
    "Привет!\n\n"
    "Спасибо, что вы перешли по ссылке.\n"
    "Нажмите «Старт», решите простую капчу —\n"
    "и добро пожаловать в гостевой чат\n"
    "с интересными людьми. 👇"
)


def _extract_admin_ids(admins: list) -> set[int]:
    ids: set[int] = set()
    for admin in admins:
        if isinstance(admin, int):
            ids.add(admin)
            continue
        admin_id = getattr(admin, "user_id", None)
        if isinstance(admin_id, int):
            ids.add(admin_id)
    return ids


async def setup_commands(bot: Bot, services: Services) -> None:
    try:
        await bot.set_my_description(WELCOME_MESSAGE)
        await bot.set_my_short_description("Привет!")
    except Exception as error:  # pragma: no cover - fallback logging
        print(error)

    try:
        await bot.set_my_commands([], scope=BotCommandScopeDefault())
    except Exception as error:  # pragma: no cover - fallback logging
        print(error)

    regular_admins, super_admins = await services.admin.list_admins()
    admin_ids = _extract_admin_ids(list(regular_admins) + list(super_admins))

    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except (TelegramNotFound, TelegramBadRequest, Exception):
            continue

    curator_ids = await services.curator.list_curator_ids()
    for curator_id in curator_ids:
        if curator_id in admin_ids:
            continue
        try:
            await bot.set_my_commands(
                CURATOR_COMMANDS,
                scope=BotCommandScopeChat(chat_id=curator_id),
            )
        except (TelegramNotFound, TelegramBadRequest, Exception):
            continue


async def delete_commands(bot: Bot, services: Services) -> None:
    try:
        await bot.set_my_commands([], scope=BotCommandScopeDefault())
        regular_admins, super_admins = await services.admin.list_admins()
        admin_ids = _extract_admin_ids(list(regular_admins) + list(super_admins))
        for admin_id in admin_ids:
            try:
                await bot.set_my_commands(
                    [],
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except (TelegramNotFound, TelegramBadRequest, Exception):
                continue
        curator_ids = await services.curator.list_curator_ids()
        for curator_id in curator_ids:
            try:
                await bot.set_my_commands(
                    [],
                    scope=BotCommandScopeChat(chat_id=curator_id),
                )
            except (TelegramNotFound, TelegramBadRequest, Exception):
                continue
    except Exception:
        pass
