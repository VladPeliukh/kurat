from aiogram import Dispatcher

from .group_restriction import primary_group_only_middleware


def setup_middlewares(dp: Dispatcher) -> None:
    """Инициализация всех мидлварей"""

    dp.update.middleware(primary_group_only_middleware)
