import os
from datetime import timedelta, timezone

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback if dependency is missing
    def load_dotenv(_path: str | None = None) -> bool:
        """Lightweight fallback that simply returns False when python-dotenv is absent."""

        return False


load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    _developers_raw = (os.getenv("DEVELOPERS_IDS") or "").replace(" ", "")
    DEVELOPERS_IDS = (
        list(map(int, filter(None, _developers_raw.split(",")))) if _developers_raw else []
    )

    # Database
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST")
    _db_port_raw = os.getenv("DB_PORT")
    DB_PORT = int(_db_port_raw) if _db_port_raw and _db_port_raw.isdigit() else None

    _time_zone_raw = os.getenv("TIME_ZONE")
    TZ = timezone(timedelta(hours=int(_time_zone_raw))) if _time_zone_raw else timezone.utc

    _SUPER_ADMIN_RAW = os.getenv("SUPER_ADMIN")
    try:
        SUPER_ADMIN = int(_SUPER_ADMIN_RAW) if _SUPER_ADMIN_RAW else None
    except ValueError:
        SUPER_ADMIN = None
