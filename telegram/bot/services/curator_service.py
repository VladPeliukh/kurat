from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict
from aiogram import Bot
from ..utils.helpers import make_ref_code, build_deeplink

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
DATA_FILE = DATA_DIR / 'curators.json'
PENDING_FILE = DATA_DIR / 'pending.json'
CAPTCHA_PENDING_FILE = DATA_DIR / 'captcha_pending.json'
CAPTCHA_PASSED_FILE = DATA_DIR / 'captcha_passed.json'

@dataclass
class Curator:
    user_id: int
    username: Optional[str]
    full_name: str
    ref_code: Optional[str] = None
    invite_link: Optional[str] = None
    partners: List[int] = None

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
        )
        for file, default in defaults:
            if not file.exists():
                file.write_text(default, encoding="utf-8")

    def _load(self) -> Dict[str, dict]:
        try: return json.loads(DATA_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save(self, data: Dict[str, dict]) -> None:
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _load_pending(self) -> Dict[str, int]:
        try: return json.loads(PENDING_FILE.read_text(encoding='utf-8') or '{}')
        except Exception: return {}

    def _save_pending(self, data: Dict[str, int]) -> None:
        PENDING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

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
        if key not in data:
            data[key] = {
                "user_id": user_id, "username": username, "full_name": full_name,
                "ref_code": None, "invite_link": None, "partners": []
            }
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
        return len(v.get('partners') or [])

    async def request_join(self, curator_id: int, partner_id: int) -> None:
        pend = self._load_pending()
        pend[str(partner_id)] = curator_id
        self._save_pending(pend)

    async def resolve_request(self, partner_id: int) -> int | None:
        pend = self._load_pending()
        k = str(partner_id)
        curator_id = pend.pop(k, None)
        self._save_pending(pend)
        return curator_id

    async def register_partner(self, curator_id: int, partner_user_id: int) -> None:
        data = self._load()
        k = str(curator_id)
        if k not in data:
            data[k] = {"user_id": curator_id, "username": None, "full_name": "", "ref_code": None, "invite_link": None, "partners": []}
        v = data[k]
        partners = v.get('partners') or []
        if partner_user_id not in partners:
            partners.append(partner_user_id)
            v['partners'] = partners
            data[k] = v
            self._save(data)

    async def promote_to_curator(self, user_id: int, username: Optional[str], full_name: str) -> str:
        link = await self.get_or_create_personal_link(user_id, username, full_name)
        return link

    async def find_curator_by_code(self, code: str) -> int | None:
        data = self._load()
        for uid, v in data.items():
            if v.get('ref_code') == code:
                return int(uid)
        return None

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
