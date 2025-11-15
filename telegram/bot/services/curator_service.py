from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from aiogram import Bot
from zoneinfo import ZoneInfo

from ..utils.helpers import build_deeplink, make_ref_code

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass
class Curator:
    user_id: int
    username: Optional[str]
    full_name: str
    ref_code: Optional[str] = None
    invite_link: Optional[str] = None
    partners: List[dict] | None = None
    source_link: Optional[str] = None
    promoted_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CuratorService:
    """Curator storage and approval workflow backed by PostgreSQL."""

    _pool: asyncpg.Pool | None = None

    def __init__(self, bot: Bot):
        if CuratorService._pool is None:
            raise RuntimeError("CuratorService is not configured with a database pool")
        self.bot = bot

    @property
    def pool(self) -> asyncpg.Pool:
        assert CuratorService._pool is not None
        return CuratorService._pool

    @classmethod
    def configure(cls, pool: asyncpg.Pool) -> None:
        cls._pool = pool

    @classmethod
    async def init_storage(cls) -> None:
        if cls._pool is None:
            raise RuntimeError("CuratorService pool is not configured")
        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS curators (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        full_name TEXT NOT NULL,
                        ref_code TEXT UNIQUE,
                        invite_link TEXT,
                        source_link TEXT,
                        promoted_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS curator_partners (
                        curator_id BIGINT NOT NULL REFERENCES curators(user_id) ON DELETE CASCADE,
                        partner_user_id BIGINT NOT NULL,
                        full_name TEXT NOT NULL DEFAULT '',
                        username TEXT,
                        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (curator_id, partner_user_id)
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS invite_sources (
                        partner_id BIGINT PRIMARY KEY,
                        curator_id BIGINT NOT NULL,
                        payload TEXT,
                        source_link TEXT,
                        recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS join_requests (
                        partner_id BIGINT PRIMARY KEY,
                        curator_id BIGINT NOT NULL,
                        full_name TEXT,
                        username TEXT,
                        source_link TEXT,
                        payload TEXT,
                        recorded_at TIMESTAMPTZ
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS captcha_challenges (
                        partner_id BIGINT PRIMARY KEY,
                        curator_id BIGINT NOT NULL,
                        answer INTEGER NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS captcha_passed (
                        partner_id BIGINT PRIMARY KEY,
                        passed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    async def is_curator(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT ref_code FROM curators WHERE user_id = $1",
                user_id,
            )
        return bool(record and record.get("ref_code"))

    async def list_curator_ids(self) -> list[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM curators WHERE ref_code IS NOT NULL",
            )
        return [row.get("user_id") for row in rows if row and row.get("user_id") is not None]

    async def ensure_curator_record(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
    ) -> Curator:
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(
                """
                SELECT user_id, username, full_name, ref_code, invite_link, source_link, promoted_at
                FROM curators
                WHERE user_id = $1
                """,
                user_id,
            )
            if record is None:
                record = await conn.fetchrow(
                    """
                    INSERT INTO curators (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                    RETURNING user_id, username, full_name, ref_code, invite_link, source_link, promoted_at
                    """,
                    user_id,
                    username,
                    full_name,
                )
            else:
                updates: list[str] = []
                params: list[Any] = []
                idx = 1
                if username and record.get("username") != username:
                    updates.append(f"username = ${idx}")
                    params.append(username)
                    idx += 1
                if full_name and record.get("full_name") != full_name:
                    updates.append(f"full_name = ${idx}")
                    params.append(full_name)
                    idx += 1
                if updates:
                    params.append(user_id)
                    await conn.execute(
                        f"UPDATE curators SET {', '.join(updates)} WHERE user_id = ${idx}",
                        *params,
                    )
                    record = await conn.fetchrow(
                        """
                        SELECT user_id, username, full_name, ref_code, invite_link, source_link, promoted_at
                        FROM curators
                        WHERE user_id = $1
                        """,
                        user_id,
                    )
        return Curator(
            user_id=record["user_id"],
            username=record.get("username"),
            full_name=record.get("full_name", ""),
            ref_code=record.get("ref_code"),
            invite_link=record.get("invite_link"),
            partners=None,
            source_link=record.get("source_link"),
            promoted_at=record.get("promoted_at").isoformat() if record.get("promoted_at") else None,
        )

    async def get_or_create_personal_link(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
    ) -> str:
        cur = await self.ensure_curator_record(user_id, username, full_name)
        if not cur.ref_code:
            cur.ref_code = make_ref_code(16)
            me = await self.bot.get_me()
            cur.invite_link = build_deeplink(me.username, cur.ref_code)
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE curators
                    SET ref_code = $1, invite_link = $2
                    WHERE user_id = $3
                    """,
                    cur.ref_code,
                    cur.invite_link,
                    user_id,
                )
        assert cur.invite_link is not None
        return cur.invite_link

    async def partners_count(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM curator_partners WHERE curator_id = $1",
                user_id,
            )
        return int(result or 0)

    def _normalize_partners(self, partners: list[dict]) -> list[dict]:
        seen: set[int] = set()
        unique: list[dict] = []
        for partner in partners or []:
            uid = int(partner.get("user_id", 0)) if isinstance(partner, dict) else int(partner)
            if not uid or uid in seen:
                continue
            seen.add(uid)
            if isinstance(partner, dict):
                unique.append(
                    {
                        "user_id": uid,
                        "full_name": (partner.get("full_name") or "").strip(),
                        "username": partner.get("username"),
                    }
                )
            else:
                unique.append({"user_id": uid, "full_name": "", "username": None})
        return unique

    async def list_partners(self, curator_id: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT partner_user_id, full_name, username
                FROM curator_partners
                WHERE curator_id = $1
                ORDER BY added_at DESC
                """,
                curator_id,
            )
        partners = [
            {
                "user_id": row["partner_user_id"],
                "full_name": (row.get("full_name") or "").strip(),
                "username": row.get("username"),
            }
            for row in rows
        ]
        return self._normalize_partners(partners)

    async def is_partner(self, curator_id: int, partner_user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT 1
                FROM curator_partners
                WHERE curator_id = $1 AND partner_user_id = $2
                """,
                curator_id,
                partner_user_id,
            )
        return bool(exists)

    async def request_join(
        self,
        curator_id: int,
        partner_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
        source_link: str | None = None,
        payload: str | None = None,
    ) -> None:
        source_data = await self.get_invite_source(partner_id) or {}
        recorded_at: Optional[datetime]
        if source_data.get("recorded_at"):
            recorded_at = datetime.fromisoformat(source_data["recorded_at"])
        elif source_link or source_data.get("source_link"):
            recorded_at = datetime.now(timezone.utc)
        else:
            recorded_at = None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO join_requests (partner_id, curator_id, full_name, username, source_link, payload, recorded_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (partner_id) DO UPDATE
                    SET curator_id = EXCLUDED.curator_id,
                        full_name = EXCLUDED.full_name,
                        username = EXCLUDED.username,
                        source_link = EXCLUDED.source_link,
                        payload = EXCLUDED.payload,
                        recorded_at = EXCLUDED.recorded_at
                """,
                partner_id,
                curator_id,
                full_name,
                username,
                source_link or source_data.get("source_link"),
                payload or source_data.get("payload"),
                recorded_at,
            )

    async def resolve_request(self, partner_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                DELETE FROM join_requests
                WHERE partner_id = $1
                RETURNING curator_id, full_name, username, source_link, payload, recorded_at
                """,
                partner_id,
            )
        if row is None:
            return None
        result: Dict[str, Any] = {
            "curator_id": int(row["curator_id"]),
        }
        for key in ("full_name", "username", "source_link", "payload"):
            if row.get(key) is not None:
                result[key] = row[key]
        if row.get("recorded_at"):
            recorded = row["recorded_at"]
            result["recorded_at"] = recorded.isoformat() if isinstance(recorded, datetime) else recorded
        source_data = await self.get_invite_source(partner_id)
        if source_data:
            for key in ("source_link", "payload", "recorded_at"):
                if source_data.get(key) and not result.get(key):
                    result[key] = source_data[key]
            await self._clear_invite_source(partner_id)
        return result

    async def register_partner(self, curator_id: int, partner_user_id: int) -> None:
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT 1
                FROM curator_partners
                WHERE curator_id = $1 AND partner_user_id = $2
                """,
                curator_id,
                partner_user_id,
            )
            if exists:
                return
        full_name = ""
        username = None
        try:
            chat = await self.bot.get_chat(partner_user_id)
            parts = [chat.first_name or "", chat.last_name or ""]
            full_name = " ".join(part for part in parts if part).strip()
            username = chat.username
        except Exception:
            pass
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO curator_partners (curator_id, partner_user_id, full_name, username)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (curator_id, partner_user_id) DO UPDATE
                    SET full_name = COALESCE(EXCLUDED.full_name, curator_partners.full_name),
                        username = COALESCE(EXCLUDED.username, curator_partners.username)
                """,
                curator_id,
                partner_user_id,
                full_name,
                username,
            )

    async def promote_to_curator(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
        *,
        source_link: Optional[str] = None,
    ) -> str:
        link = await self.get_or_create_personal_link(user_id, username, full_name)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE curators
                SET username = COALESCE($2, username),
                    full_name = $3,
                    invite_link = $4,
                    source_link = COALESCE($5, source_link),
                    promoted_at = COALESCE(promoted_at, $6)
                WHERE user_id = $1
                """,
                user_id,
                username,
                full_name,
                link,
                source_link,
                datetime.now(MOSCOW_TZ),
            )
        await self._clear_invite_source(user_id)
        return link

    async def find_curator_by_code(self, code: str) -> int | None:
        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT user_id FROM curators WHERE ref_code = $1",
                code,
            )
        return int(user_id) if user_id is not None else None

    async def record_invite_source(
        self,
        partner_id: int,
        curator_id: int,
        payload: str,
        source_link: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO invite_sources (partner_id, curator_id, payload, source_link, recorded_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (partner_id) DO UPDATE
                    SET curator_id = EXCLUDED.curator_id,
                        payload = EXCLUDED.payload,
                        source_link = EXCLUDED.source_link,
                        recorded_at = EXCLUDED.recorded_at
                """,
                partner_id,
                curator_id,
                payload,
                source_link,
                datetime.now(timezone.utc),
            )

    async def get_invite_source(self, partner_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT partner_id, curator_id, payload, source_link, recorded_at
                FROM invite_sources
                WHERE partner_id = $1
                """,
                partner_id,
            )
        if row is None:
            return None
        data: Dict[str, Any] = {
            "partner_id": row["partner_id"],
            "curator_id": row["curator_id"],
            "payload": row.get("payload"),
            "source_link": row.get("source_link"),
        }
        if row.get("recorded_at"):
            recorded = row["recorded_at"]
            data["recorded_at"] = recorded.isoformat() if isinstance(recorded, datetime) else recorded
        return data

    async def _clear_invite_source(self, partner_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM invite_sources WHERE partner_id = $1",
                partner_id,
            )

    async def get_curator_record(self, user_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, username, full_name, ref_code, invite_link, source_link, promoted_at
                FROM curators
                WHERE user_id = $1
                """,
                user_id,
            )
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "username": row.get("username"),
            "full_name": row.get("full_name"),
            "ref_code": row.get("ref_code"),
            "invite_link": row.get("invite_link"),
            "source_link": row.get("source_link"),
            "promoted_at": row["promoted_at"].isoformat() if row.get("promoted_at") else None,
        }

    async def get_partner_statistics(
        self,
        curator_id: int,
        partner_user_id: int,
    ) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            partner = await conn.fetchrow(
                """
                SELECT full_name, username
                FROM curator_partners
                WHERE curator_id = $1 AND partner_user_id = $2
                """,
                curator_id,
                partner_user_id,
            )
        if partner is None:
            return None
        record = await self.get_curator_record(partner_user_id)
        stats = {
            "user_id": partner_user_id,
            "full_name": (partner.get("full_name") or (record or {}).get("full_name") or "").strip(),
            "username": partner.get("username") or (record or {}).get("username"),
        }
        if record:
            stats.update(
                {
                    "source_link": record.get("source_link"),
                    "invite_link": record.get("invite_link"),
                    "promoted_at": record.get("promoted_at"),
                    "ref_code": record.get("ref_code"),
                }
            )
        return stats

    async def store_captcha_challenge(self, partner_id: int, curator_id: int, answer: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO captcha_challenges (partner_id, curator_id, answer, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (partner_id) DO UPDATE
                    SET curator_id = EXCLUDED.curator_id,
                        answer = EXCLUDED.answer,
                        created_at = EXCLUDED.created_at
                """,
                partner_id,
                curator_id,
                answer,
                datetime.now(timezone.utc),
            )

    async def get_captcha_challenge(self, partner_id: int) -> tuple[int, int] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT curator_id, answer
                FROM captcha_challenges
                WHERE partner_id = $1
                """,
                partner_id,
            )
        if row is None:
            return None
        return int(row["curator_id"]), int(row["answer"])

    async def clear_captcha_challenge(self, partner_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM captcha_challenges WHERE partner_id = $1",
                partner_id,
            )

    async def has_passed_captcha(self, partner_id: int) -> bool:
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM captcha_passed WHERE partner_id = $1",
                partner_id,
            )
        return bool(exists)

    async def mark_captcha_passed(self, partner_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO captcha_passed (partner_id, passed_at)
                VALUES ($1, $2)
                ON CONFLICT (partner_id) DO UPDATE
                    SET passed_at = EXCLUDED.passed_at
                """,
                partner_id,
                datetime.now(timezone.utc),
            )
        await self.clear_captcha_challenge(partner_id)

