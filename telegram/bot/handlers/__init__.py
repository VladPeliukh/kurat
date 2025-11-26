from aiogram import Dispatcher

from . import admin_handlers, curator_handlers


def register_handlers(dp: Dispatcher) -> None:
        """Register all bot handlers."""
        dp.include_router(admin_handlers.router)
        dp.include_router(curator_handlers.router)


__all__ = ["register_handlers"]
