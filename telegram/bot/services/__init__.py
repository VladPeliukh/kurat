from aiogram import Bot
import asyncpg

from .admin_service import AdminService
from .curator_service import CuratorService


class Services:
    """Контейнер для всех сервисов"""

    def __init__(self, bot: Bot, pool: asyncpg.Pool):
        self.admin = AdminService()
        self.curator = CuratorService(bot)
        self.pool = pool


async def setup_services(bot: Bot, pool: asyncpg.Pool) -> Services:
    """Инициализация всех сервисов"""
    if getattr(AdminService, "_pool", None) is None:
        AdminService.configure(pool)
        await AdminService.init_storage()
    if getattr(CuratorService, "_pool", None) is None:
        CuratorService.configure(pool)
        await CuratorService.init_storage()
    return Services(bot, pool)
