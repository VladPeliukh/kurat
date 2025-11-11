import io
import os
from pathlib import Path
from typing import List, Tuple

from ..models import Admin
from ..utils.loggers import services as logger


class AdminService:
	"""Сервис для работы с администраторами"""

	async def list_admins(self) -> Tuple[List[Admin], List[Admin]]:
		"""Получение списка администраторов"""
		return ([940925120], [940925120])


	@staticmethod
	async def get_logs() -> List | None:
		"""Получение файла логов"""
		try:
			log_dir = Path("logs")
			if not log_dir.exists():
				return None

			log_files = list(map(lambda x: x.stem, sorted(log_dir.glob("*.log"), key=os.path.getmtime, reverse=True)))
			if not log_files:
				return None

			return log_files
		except Exception as e:
			logger.error(f"Error getting logs: {str(e)}")
			return None

	async def create_backup(self) -> io.BytesIO | None:
		"""Создание бэкапа базы данных"""
		pass
