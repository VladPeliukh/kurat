from aiogram import Bot
import asyncpg

from .admin_service import AdminService
from .curator_service import CuratorService


class Services:
    """Контейнер для всех сервисов"""

    __slots__ = ("admin", "curator", "pool")

    def __init__(self, admin: AdminService, curator: CuratorService, pool: asyncpg.Pool):
        self.admin = admin
        self.curator = curator
        self.pool = pool

    @classmethod
    async def create(cls, bot: Bot, pool: asyncpg.Pool) -> "Services":
        """Настройка сервисов и сборка контейнера."""

        if getattr(AdminService, "_pool", None) is None:
            AdminService.configure(pool)
            await AdminService.init_storage()
        if getattr(CuratorService, "_pool", None) is None:
            CuratorService.configure(pool)
            await CuratorService.init_storage()

        return cls(AdminService(), CuratorService(bot), pool)


async def setup_services(bot: Bot, pool: asyncpg.Pool) -> Services:
    """Инициализация всех сервисов"""

    return await Services.create(bot, pool)
