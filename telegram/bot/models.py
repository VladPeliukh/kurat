from dataclasses import dataclass
from typing import Optional

@dataclass
class Admin:
	user_id: int
	username: Optional[str]
	full_name: str
	level: int = 1  # Уровень доступа (1 - базовый, 2 - полный)