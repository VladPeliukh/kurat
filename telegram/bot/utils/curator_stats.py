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

CURATOR_INFO_HEADERS = CURATOR_STATS_HEADERS + ["Пригласил"]

ALL_CURATORS_HEADERS = [
    "ID",
    "Username",
    "Имя",
    "Пригласил",
    "Персональная ссылка",
    "Ссылка источника",
    "Дата и время назначения",
]


def _format_promoted_at(promoted_at: str | None) -> str:
    if not promoted_at:
        return ""
    try:
        dt = datetime.fromisoformat(str(promoted_at))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(MOSCOW_TZ)
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(promoted_at)


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
        rows.append(
            [
                stats.get("user_id") or partner_id,
                stats.get("full_name") or partner.get("full_name") or "",
                username,
                stats.get("source_link") or "",
                stats.get("invite_link") or "",
                _format_promoted_at(stats.get("promoted_at")),
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


async def prepare_curator_info_report(
    svc: CuratorService,
    curator_id: int,
    *,
    owner_label: str | None = None,
) -> tuple[BufferedInputFile, str] | None:
    record = await svc.get_curator_record(curator_id)
    if record is None:
        return None

    username = record.get("username") or ""
    if username and not str(username).startswith("@"):
        username = f"@{username}"

    promoted_text = _format_promoted_at(record.get("promoted_at"))
    inviter = await svc.get_curator_inviter(curator_id)
    inviter_display = ""
    if inviter:
        inviter_username = inviter.get("username") or ""
        if inviter_username and not str(inviter_username).startswith("@"):
            inviter_username = f"@{inviter_username}"
        inviter_parts = [part for part in [inviter.get("full_name") or "", inviter_username] if part]
        inviter_display = " | ".join(inviter_parts)
        inviter_id = inviter.get("user_id")
        if inviter_id:
            inviter_display = f"{inviter_display} (ID {inviter_id})" if inviter_display else f"ID {inviter_id}"
    rows = [
        [
            record.get("user_id") or curator_id,
            record.get("full_name") or "",
            username,
            record.get("source_link") or "",
            record.get("invite_link") or "",
            promoted_text,
            inviter_display,
        ]
    ]

    csv_bytes = build_simple_table_csv(CURATOR_INFO_HEADERS, rows)
    filename = f"curator_info_{curator_id}.csv"
    document = BufferedInputFile(csv_bytes, filename=filename)
    name_label = record.get("full_name") or f"ID {curator_id}"
    caption_label = owner_label or "Информация о кураторе"
    caption = f"{caption_label} {name_label}."
    return document, caption


async def prepare_all_curators_snapshot(
    svc: CuratorService,
) -> tuple[BufferedInputFile, str] | None:
    curators = await svc.list_all_curators()
    if not curators:
        return None

    rows: list[list[str | int]] = []
    for curator in curators:
        curator_id = curator.get("user_id")
        if curator_id is None:
            continue

        username = curator.get("username") or ""
        if username and not str(username).startswith("@"):
            username = f"@{username}"

        inviter_display = ""
        inviter = await svc.get_curator_inviter(curator_id)
        if inviter:
            inviter_username = inviter.get("username") or ""
            if inviter_username and not str(inviter_username).startswith("@"):
                inviter_username = f"@{inviter_username}"
            inviter_parts = [inviter.get("full_name") or "", inviter_username]
            inviter_display = " | ".join(part for part in inviter_parts if part)
            inviter_id = inviter.get("user_id")
            if inviter_id:
                inviter_display = (
                    f"{inviter_display} (ID {inviter_id})"
                    if inviter_display
                    else f"ID {inviter_id}"
                )

        rows.append(
            [
                curator_id,
                username,
                curator.get("full_name") or "",
                inviter_display,
                curator.get("invite_link") or "",
                curator.get("source_link") or "",
                _format_promoted_at(curator.get("promoted_at")),
            ]
        )

    csv_bytes = build_simple_table_csv(ALL_CURATORS_HEADERS, rows)
    filename = "curators_snapshot.csv"
    document = BufferedInputFile(csv_bytes, filename=filename)
    caption = "Сводка всех кураторов."
    return document, caption

