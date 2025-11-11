from datetime import datetime, timezone, timedelta
from ..config import Config



def get_datetime_now() -> datetime:
	return datetime.now(Config.TZ).replace(tzinfo=None)