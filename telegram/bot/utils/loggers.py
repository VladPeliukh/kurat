import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .work_with_date import get_datetime_now
from ..config import Config


class UTCFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, Config.TZ)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")


class DailyFileHandler(logging.Handler):
    """Обработчик для записи логов в файлы с именем по текущей дате"""

    def __init__(self, log_dir: str):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)
        self.current_date = get_datetime_now().date()
        self.current_handler = self._create_handler()

    def _get_filename(self):
        """Генерирует имя файла на основе текущей даты"""
        return self.log_dir / f"{get_datetime_now().strftime('%Y_%m_%d')}.log"

    def _create_handler(self):
        """Создает FileHandler для текущей даты"""
        file_handler = logging.FileHandler(self._get_filename(), encoding='utf-8')
        formatter = UTCFormatter(
            f'%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)-101s | %(filename)s:%(lineno)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        return file_handler

    def emit(self, record):
        """Обрабатывает запись лога, проверяя смену даты"""
        today = get_datetime_now().date()
        if today != self.current_date:
            # Дата сменилась, создаем новый обработчик
            self.current_date = today
            self.current_handler.close()
            self.current_handler = self._create_handler()

        self.current_handler.emit(record)

    def close(self):
        self.current_handler.close()
        super().close()


class BotLogger:
    def __init__(self, name: str, log_dir: Optional[str] = 'logs'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if self.logger.handlers:
            return
        formatter = UTCFormatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)-101s | %(filename)s:%(lineno)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Консольный вывод
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Файловый вывод с ежедневной ротацией
        daily_handler = DailyFileHandler(log_dir)
        self.logger.addHandler(daily_handler)

        # Настройка логгера aiogram
        aiogram_logger = logging.getLogger('aiogram')
        aiogram_logger.setLevel(logging.WARNING)

        if aiogram_logger.handlers:
            return
        # Добавляем обработчики к aiogram логгеру
        aiogram_logger.addHandler(console_handler)
        aiogram_logger.addHandler(daily_handler)

    def get_logger(self):
        return self.logger


# Инициализация глобального логгера
main_bot = BotLogger("bot.main").get_logger()
services = BotLogger("bot.services").get_logger()
handlers = BotLogger("bot.handlers").get_logger()