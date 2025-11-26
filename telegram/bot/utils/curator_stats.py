from datetime import datetime, timezone
from typing import Iterable

from aiogram.types import BufferedInputFile
from zoneinfo import ZoneInfo

from ..services.curator_service import CuratorService
from .csv_export import build_simple_table_csv

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

CURATOR_STATS_HEADERS = [
    "ID",
    "Имя",
    "Username",
    "Ссылка приглашения",
    "Персональная ссылка",
    "Дата и время назначения",
]


async def collect_curator_stats_rows(
    svc: CuratorService,
    curator_id: int,
    partners: Iterable[dict],
) -> list[list[str | int]]:
    rows: list[list[str | int]] = []
    for partner in partners:
        partner_id = partner.get("user_id")
        if not partner_id:
            continue
        stats = await svc.get_partner_statistics(curator_id, partner_id)
        if not stats:
            stats = {
                "user_id": partner_id,
                "full_name": partner.get("full_name") or "",
                "username": partner.get("username"),
                "source_link": None,
                "invite_link": None,
                "promoted_at": None,
            }
        username = stats.get("username") or partner.get("username") or ""
        if username and not str(username).startswith("@"):
            username = f"@{username}"
        promoted_at = stats.get("promoted_at")
        promoted_text = ""
        if promoted_at:
            try:
                dt = datetime.fromisoformat(str(promoted_at))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(MOSCOW_TZ)
                promoted_text = dt.strftime("%d.%m.%Y %H:%M:%S")
            except Exception:
                promoted_text = str(promoted_at)
        rows.append(
            [
                stats.get("user_id") or partner_id,
                stats.get("full_name") or partner.get("full_name") or "",
                username,
                stats.get("source_link") or "",
                stats.get("invite_link") or "",
                promoted_text,
            ]
        )
    return rows


async def prepare_curator_all_time_stats(
    svc: CuratorService,
    curator_id: int,
    *,
    owner_label: str = "Ваша статистика",
) -> tuple[BufferedInputFile, str] | None:
    partners = await svc.list_partners(curator_id)
    if not partners:
        return None
    rows = await collect_curator_stats_rows(svc, curator_id, partners)
    if not rows:
        return None
    csv_bytes = build_simple_table_csv(CURATOR_STATS_HEADERS, rows)
    filename = f"curator_stats_{curator_id}_all_time.csv"
    document = BufferedInputFile(csv_bytes, filename=filename)
    caption = f"{owner_label} приглашенных пользователей за всё время."
    return document, caption

