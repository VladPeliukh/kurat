from aiogram import Router

router = Router()

from . import promotions, menu, stats, start, requests, captcha  # noqa: F401,E402

__all__ = ["router"]
