from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from aiogram import Bot
from ..utils.helpers import make_ref_code, build_deeplink

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
DATA_FILE = DATA_DIR / 'curators.json'
PENDING_FILE = DATA_DIR / 'pending.json'
CAPTCHA_PENDING_FILE = DATA_DIR / 'captcha_pending.json'
CAPTCHA_PASSED_FILE = DATA_DIR / 'captcha_passed.json'
SOURCES_FILE = DATA_DIR / 'sources.json'

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

    def to_dict(self): return asdict(self)

class CuratorService:
    """Curator storage + approval workflow (file-based). Replace with DB in production."""
    def __init__(self, bot: Bot):
        self.bot = bot
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        defaults = (
            (DATA_FILE, "{}"),
            (PENDING_FILE, "{}"),
            (CAPTCHA_PENDING_FILE, "{}"),
            (CAPTCHA_PASSED_FILE, "[]"),
            (SOURCES_FILE, "{}"),
        )
        for file, default in defaults:
            if not file.exists():
                file.write_text(default, encoding="utf-8")

    def _load(self) -> Dict[str, dict]:
        try: return json.loads(DATA_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save(self, data: Dict[str, dict]) -> None:
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _load_pending(self) -> Dict[str, Any]:
        try: return json.loads(PENDING_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save_pending(self, data: Dict[str, Any]) -> None:
        PENDING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _load_sources(self) -> Dict[str, dict]:
        try: return json.loads(SOURCES_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save_sources(self, data: Dict[str, dict]) -> None:
        SOURCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _load_captcha_pending(self) -> Dict[str, dict]:
        try: return json.loads(CAPTCHA_PENDING_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save_captcha_pending(self, data: Dict[str, dict]) -> None:
        CAPTCHA_PENDING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _load_captcha_passed(self) -> list[int]:
        try: return json.loads(CAPTCHA_PASSED_FILE.read_text(encoding='utf-8') or '[]')
        except Exception: return []

    def _save_captcha_passed(self, data: list[int]) -> None:
        CAPTCHA_PASSED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    async def is_curator(self, user_id: int) -> bool:
        data = self._load()
        v = data.get(str(user_id))
        return bool(v and v.get('ref_code'))

    async def ensure_curator_record(self, user_id: int, username: Optional[str], full_name: str) -> Curator:
        data = self._load()
        key = str(user_id)
        created = False
        if key not in data:
            data[key] = {
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "ref_code": None,
                "invite_link": None,
                "partners": [],
                "source_link": None,
                "promoted_at": None,
            }
            created = True
        else:
            record = data[key]
            defaults = {
                "partners": [],
                "source_link": None,
                "promoted_at": None,
            }
            updated = False
            for field, default in defaults.items():
                if field not in record:
                    record[field] = default
                    updated = True
            if username and record.get("username") != username:
                record["username"] = username
                updated = True
            if full_name and record.get("full_name") != full_name:
                record["full_name"] = full_name
                updated = True
            if updated:
                data[key] = record
                created = True
        if created:
            self._save(data)
        return Curator(**data[key])

    async def get_or_create_personal_link(self, user_id: int, username: Optional[str], full_name: str) -> str:
        cur = await self.ensure_curator_record(user_id, username, full_name)
        if not cur.ref_code:
            cur.ref_code = make_ref_code(16)
            me = await self.bot.get_me()
            cur.invite_link = build_deeplink(me.username, cur.ref_code)
            data = self._load(); data[str(user_id)] = cur.to_dict(); self._save(data)
        return cur.invite_link

    async def partners_count(self, user_id: int) -> int:
        v = self._load().get(str(user_id)) or {}
        partners = self._normalize_partners(v.get('partners') or [])
        return len(partners)

    def _normalize_partners(self, partners: list) -> list[dict]:
        normalized: list[dict] = []
        for item in partners or []:
            if isinstance(item, int):
                normalized.append({"user_id": int(item), "full_name": "", "username": None})
            elif isinstance(item, dict):
                normalized.append(
                    {
                        "user_id": int(item.get("user_id", 0)),
                        "full_name": item.get("full_name") or "",
                        "username": item.get("username"),
                    }
                )
        seen: set[int] = set()
        unique: list[dict] = []
        for partner in normalized:
            uid = partner.get("user_id")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            unique.append(partner)
        return unique

    async def list_partners(self, curator_id: int) -> list[dict]:
        data = self._load()
        record = data.get(str(curator_id))
        if not record:
            return []
        partners = self._normalize_partners(record.get("partners") or [])
        if record.get("partners") != partners:
            record["partners"] = partners
            data[str(curator_id)] = record
            self._save(data)
        return partners

    async def is_partner(self, curator_id: int, partner_user_id: int) -> bool:
        partners = await self.list_partners(curator_id)
        return any(p.get("user_id") == partner_user_id for p in partners)

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
        pend_raw = self._load_pending()
        info: dict[str, Any] = {"curator_id": curator_id}
        if full_name:
            info["full_name"] = full_name
        if username:
            info["username"] = username
        source_data = self._load_sources().get(str(partner_id)) or {}
        if source_link or source_data.get("source_link"):
            info["source_link"] = source_link or source_data.get("source_link")
        if payload or source_data.get("payload"):
            info["payload"] = payload or source_data.get("payload")
        recorded_at = source_data.get("recorded_at")
        if recorded_at:
            info["recorded_at"] = recorded_at
        elif info.get("source_link"):
            info["recorded_at"] = datetime.now(timezone.utc).isoformat()
        pend_raw[str(partner_id)] = info
        self._save_pending(pend_raw)

    async def resolve_request(self, partner_id: int) -> dict | None:
        pend_raw = self._load_pending()
        k = str(partner_id)
        entry = pend_raw.pop(k, None)
        self._save_pending(pend_raw)
        if entry is None:
            return None
        result: dict[str, Any]
        if isinstance(entry, int):
            result = {"curator_id": int(entry)}
        elif isinstance(entry, dict):
            result = dict(entry)
            if "curator_id" in result:
                result["curator_id"] = int(result["curator_id"])
        else:
            return None
        source_data = self._load_sources().get(k)
        if source_data:
            for key in ("source_link", "payload", "recorded_at"):
                if source_data.get(key) and not result.get(key):
                    result[key] = source_data[key]
            self._clear_invite_source(partner_id)
        return result

    async def register_partner(self, curator_id: int, partner_user_id: int) -> None:
        data = self._load()
        k = str(curator_id)
        if k not in data:
            data[k] = {
                "user_id": curator_id,
                "username": None,
                "full_name": "",
                "ref_code": None,
                "invite_link": None,
                "partners": [],
                "source_link": None,
                "promoted_at": None,
            }
        v = data[k]
        partners = self._normalize_partners(v.get('partners') or [])
        if any(p.get("user_id") == partner_user_id for p in partners):
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
        partners.append({"user_id": partner_user_id, "full_name": full_name, "username": username})
        v['partners'] = partners
        data[k] = v
        self._save(data)

    async def promote_to_curator(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
        *,
        source_link: Optional[str] = None,
    ) -> str:
        link = await self.get_or_create_personal_link(user_id, username, full_name)
        data = self._load()
        key = str(user_id)
        record = data.get(key) or {}
        record.setdefault("user_id", user_id)
        if username is not None:
            record["username"] = username
        if full_name:
            record["full_name"] = full_name
        record["invite_link"] = link
        if "ref_code" not in record or not record.get("ref_code"):
            # get_or_create_personal_link should have set these, but ensure defaults
            cur = await self.ensure_curator_record(user_id, username, full_name)
            record["ref_code"] = cur.ref_code
        if source_link:
            record["source_link"] = source_link
        if not record.get("promoted_at"):
            record["promoted_at"] = datetime.now(timezone.utc).isoformat()
        data[key] = record
        self._save(data)
        self._clear_invite_source(user_id)
        return link

    async def find_curator_by_code(self, code: str) -> int | None:
        data = self._load()
        for uid, v in data.items():
            if v.get('ref_code') == code:
                return int(uid)
        return None

    async def record_invite_source(
        self,
        partner_id: int,
        curator_id: int,
        payload: str,
        source_link: str,
    ) -> None:
        sources = self._load_sources()
        sources[str(partner_id)] = {
            "curator_id": curator_id,
            "payload": payload,
            "source_link": source_link,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_sources(sources)

    async def get_invite_source(self, partner_id: int) -> Optional[dict]:
        sources = self._load_sources()
        data = sources.get(str(partner_id))
        return dict(data) if isinstance(data, dict) else None

    def _clear_invite_source(self, partner_id: int) -> None:
        sources = self._load_sources()
        if str(partner_id) in sources:
            sources.pop(str(partner_id), None)
            self._save_sources(sources)

    async def get_curator_record(self, user_id: int) -> Optional[dict]:
        data = self._load()
        record = data.get(str(user_id))
        if not record:
            return None
        return dict(record)

    async def get_partner_statistics(self, curator_id: int, partner_user_id: int) -> Optional[dict]:
        partners = await self.list_partners(curator_id)
        info = next((p for p in partners if p.get("user_id") == partner_user_id), None)
        if not info:
            return None
        record = await self.get_curator_record(partner_user_id)
        stats = {
            "user_id": partner_user_id,
            "full_name": (info.get("full_name") or (record or {}).get("full_name") or "").strip(),
            "username": info.get("username") or (record or {}).get("username"),
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
        pend = self._load_captcha_pending()
        pend[str(partner_id)] = {"curator_id": curator_id, "answer": answer}
        self._save_captcha_pending(pend)

    async def get_captcha_challenge(self, partner_id: int) -> tuple[int, int] | None:
        pend = self._load_captcha_pending()
        data = pend.get(str(partner_id))
        if not data:
            return None
        curator_id = int(data.get("curator_id"))
        answer = int(data.get("answer"))
        return curator_id, answer

    async def clear_captcha_challenge(self, partner_id: int) -> None:
        pend = self._load_captcha_pending()
        if str(partner_id) in pend:
            pend.pop(str(partner_id), None)
            self._save_captcha_pending(pend)

    async def has_passed_captcha(self, partner_id: int) -> bool:
        passed = self._load_captcha_passed()
        return partner_id in passed

    async def mark_captcha_passed(self, partner_id: int) -> None:
        passed = self._load_captcha_passed()
        if partner_id not in passed:
            passed.append(partner_id)
            self._save_captcha_passed(passed)
        await self.clear_captcha_challenge(partner_id)
