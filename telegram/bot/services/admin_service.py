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

        if Config.SUPER_ADMINS:
            env_super_admins = [
                Admin(
                    user_id=super_admin_id,
                    username=None,
                    full_name="",
                    level=2,
                )
                for super_admin_id in Config.SUPER_ADMINS
            ]
            existing_ids = {admin.user_id for admin in super_admins}
            for env_super_admin in env_super_admins:
                if env_super_admin.user_id not in existing_ids:
                    super_admins.append(env_super_admin)
                    existing_ids.add(env_super_admin.user_id)

        return regular_admins, super_admins

    async def is_admin(self, user_id: int) -> bool:
        if user_id in Config.SUPER_ADMINS:
            return True
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM admins WHERE user_id = $1",
                user_id,
            )
        return bool(exists)

    async def is_super_admin(self, user_id: int) -> bool:
        if user_id in Config.SUPER_ADMINS:
            return True
        async with self.pool.acquire() as conn:
            level = await conn.fetchval(
                "SELECT level FROM admins WHERE user_id = $1",
                user_id,
            )
        return (level or 1) >= 2

    async def add_admin(
        self, user_id: int, username: str | None, full_name: str | None, level: int = 1
    ) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO admins (user_id, username, full_name, level)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET username = COALESCE(EXCLUDED.username, admins.username),
                    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), admins.full_name),
                    level = EXCLUDED.level
                RETURNING (xmax = 0) AS inserted
                """,
                user_id,
                username,
                full_name or "",
                level,
            )
        return bool(row and row.get("inserted"))

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
            if user_id in Config.SUPER_ADMINS:
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
