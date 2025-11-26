import io
import os
from pathlib import Path
from typing import List, Tuple

import asyncpg

from ..config import Config
from ..models import Admin
from ..utils.loggers import services as logger


class AdminService:
    """Сервис для работы с администраторами."""

    _pool: asyncpg.Pool | None = None

    def __init__(self) -> None:
        if AdminService._pool is None:
            raise RuntimeError("AdminService is not configured with a database pool")

    @classmethod
    def configure(cls, pool: asyncpg.Pool) -> None:
        cls._pool = pool

    @classmethod
    async def init_storage(cls) -> None:
        if cls._pool is None:
            raise RuntimeError("AdminService pool is not configured")
        async with cls._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    level SMALLINT NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    @property
    def pool(self) -> asyncpg.Pool:
        assert AdminService._pool is not None
        return AdminService._pool

    async def _load_admins(self) -> list[Admin]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, username, full_name, level
                FROM admins
                """
            )
        admins: list[Admin] = []
        for row in rows:
            admins.append(
                Admin(
                    user_id=row["user_id"],
                    username=row.get("username"),
                    full_name=row.get("full_name") or "",
                    level=row.get("level") or 1,
                )
            )
        return admins

    async def list_admins(self) -> Tuple[List[Admin], List[Admin]]:
        """Получение списка администраторов."""

        admins = await self._load_admins()
        super_admins: list[Admin] = [admin for admin in admins if (admin.level or 1) >= 2]
        regular_admins: list[Admin] = [admin for admin in admins if (admin.level or 1) < 2]

        if Config.SUPER_ADMIN:
            env_super_admin = Admin(
                user_id=Config.SUPER_ADMIN,
                username=None,
                full_name="",
                level=2,
            )
            if env_super_admin.user_id not in {a.user_id for a in super_admins}:
                super_admins.append(env_super_admin)

        return regular_admins, super_admins

    async def is_admin(self, user_id: int) -> bool:
        if Config.SUPER_ADMIN and user_id == Config.SUPER_ADMIN:
            return True
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM admins WHERE user_id = $1",
                user_id,
            )
        return bool(exists)

    async def get_admin(self, user_id: int) -> Admin | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, username, full_name, level
                FROM admins
                WHERE user_id = $1
                """,
                user_id,
            )
        if row is None:
            if Config.SUPER_ADMIN and user_id == Config.SUPER_ADMIN:
                return Admin(user_id=user_id, username=None, full_name="", level=2)
            return None
        return Admin(
            user_id=row["user_id"],
            username=row.get("username"),
            full_name=row.get("full_name") or "",
            level=row.get("level") or 1,
        )

    @staticmethod
    async def get_logs() -> List | None:
        """Получение файла логов."""

        try:
            log_dir = Path("logs")
            if not log_dir.exists():
                return None

            log_files = list(
                map(
                    lambda x: x.stem,
                    sorted(log_dir.glob("*.log"), key=os.path.getmtime, reverse=True),
                )
            )
            if not log_files:
                return None

            return log_files
        except Exception as e:  # pragma: no cover - best effort logging
            logger.error(f"Error getting logs: {str(e)}")
            return None

    async def create_backup(self) -> io.BytesIO | None:
        """Создание бэкапа базы данных."""

        return None
