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

        _, super_admins = await services.admin.list_admins()

        for admin in super_admins:
            try:
                await bot.send_message(admin, text="🚀 Бот Запущен 🚀")
            except (TelegramNotFound, TelegramBadRequest):
                pass

    except Exception as e:
        logger.exception(e)


async def shutdown_bot(bot: Bot, dp: Dispatcher, pool: asyncpg.Pool):
    services: Services = dp["services"]

    _, super_admins = await services.admin.list_admins()

    for admin in super_admins:
        try:
            await bot.send_message(admin, text="🛑 Бот Остановлен 🛑")
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
