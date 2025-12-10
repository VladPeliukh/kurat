import os
from datetime import timedelta, timezone

from dotenv import load_dotenv


load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVELOPERS_IDS = list(
        map(int, os.getenv("DEVELOPERS_IDS").replace(" ", "").split(","))
    )

    # Database
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = int(os.getenv("DB_PORT"))

    NV_LINK = os.getenv("NAVIGATION_LINK")

    TZ = timezone(timedelta(hours=int(os.getenv("TIME_ZONE"))))

    _SUPER_ADMIN_RAW = os.getenv("SUPER_ADMIN")
    try:
        SUPER_ADMIN = int(_SUPER_ADMIN_RAW) if _SUPER_ADMIN_RAW else None
    except ValueError:
        SUPER_ADMIN = None

    _PRIMARY_GROUP_RAW = os.getenv("PRIMARY_GROUP_ID")
    try:
        PRIMARY_GROUP_ID = int(_PRIMARY_GROUP_RAW) if _PRIMARY_GROUP_RAW else None
    except ValueError:
        PRIMARY_GROUP_ID = None
