import asyncio
from contextlib import suppress
from functools import partial

import asyncpg
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNotFound, TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage

from .config import Config
from .handlers import register_handlers
from .services import setup_services, Services
from .services.curator_service import CuratorService
from .services.admin_service import AdminService
from .utils.commands import setup_commands, delete_commands
from .middlewares import setup_middlewares
from .utils.loggers import main_bot as logger
from .utils.curator_stats import prepare_all_curators_snapshot

_NAVIGATION_MESSAGE_ID = 6523


async def _ensure_navigation_pin(bot: Bot) -> None:
    if not Config.PRIMARY_GROUP_ID:
        return

    try:
        chat = await bot.get_chat(Config.PRIMARY_GROUP_ID)
    except Exception:
        return

    pinned = getattr(chat, "pinned_message", None)
    if pinned and pinned.message_id == _NAVIGATION_MESSAGE_ID:
        return

    with suppress(Exception):
        await bot.pin_chat_message(
            Config.PRIMARY_GROUP_ID, _NAVIGATION_MESSAGE_ID, disable_notification=True
        )


async def super_admin_report_worker(bot: Bot, services: Services) -> None:
    try:
        while True:
            try:
                await send_curators_snapshot(bot, services)
                await asyncio.sleep(24 * 60 * 60)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.exception("Failed to send daily curator snapshot: %s", exc)
                await asyncio.sleep(60 * 60)
    except asyncio.CancelledError:
        return


async def send_curators_snapshot(bot: Bot, services: Services) -> None:
    if not Config.SUPER_ADMIN:
        return

    snapshot = await prepare_all_curators_snapshot(services.curator)
    if snapshot is None:
        return

    document, caption = snapshot
    await bot.send_document(Config.SUPER_ADMIN, document=document, caption=caption)


async def start_bot(bot: Bot, dp: Dispatcher, pool: asyncpg.Pool):
    try:
        # Создаём зависимости
        services = await setup_services(bot, pool)

        # Сохраняем в bot.data для глобального доступа
        dp["services"] = services

        # Ставим команды
        await setup_commands(bot, services)

        # # Настройка middleware
        setup_middlewares(dp)

        # Регистрация обработчиков
        register_handlers(dp)

        await _ensure_navigation_pin(bot)

        _, super_admins = await services.admin.list_admins()

        for admin in super_admins:
            try:
                await bot.send_message(admin.user_id, text="🚀 Бот Запущен 🚀")
            except (TelegramNotFound, TelegramBadRequest):
                pass

        if Config.SUPER_ADMIN:
            task = asyncio.create_task(
                super_admin_report_worker(bot, services), name="super_admin_daily_report"
            )
            dp["background_tasks"] = [task]

    except Exception as e:
        logger.exception(e)


async def shutdown_bot(bot: Bot, dp: Dispatcher, pool: asyncpg.Pool):
    services: Services = dp["services"]

    for task in dp.get("background_tasks", []):
        task.cancel()
    await asyncio.gather(*dp.get("background_tasks", []), return_exceptions=True)

    _, super_admins = await services.admin.list_admins()

    for admin in super_admins:
        try:
            await bot.send_message(admin.user_id, text="🛑 Бот Остановлен 🛑")
        except TelegramNotFound:
            pass

    await delete_commands(bot, services)

async def create_pool():
    return await asyncpg.create_pool(
        dsn=f"postgresql://{Config.DB_USER}:{Config.DB_PASS}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
        # или полный URL
        min_size=5,  # Минимальное число подключений
        max_size=20,  # Максимальное число подключений
        timeout=30,  # Таймаут подключения (секунды)
        command_timeout=60,  # Таймаут выполнения запроса
        max_inactive_connection_lifetime=300,  # Закрывать неиспользуемые подключения
    )

async def main():
    # Инициализация
    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()
    AdminService.configure(pool)
    await AdminService.init_storage()
    CuratorService.configure(pool)
    await CuratorService.init_storage()

    # Создаем функции запуска и окончания сеанса с параметрами
    start = partial(start_bot, bot, dp, pool)
    end = partial(shutdown_bot, bot, dp, pool)

    # Регистрируем их
    dp.startup.register(start)
    dp.shutdown.register(end)

    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await pool.close()
