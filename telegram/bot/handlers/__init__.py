from aiogram import Dispatcher

from . import start


def register_handlers(dp: Dispatcher) -> None:
        """Register all bot handlers."""
        dp.include_router(start.router)


__all__ = ["register_handlers"]
