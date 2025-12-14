from aiogram import Router

router = Router()

from . import promotions, menu, stats, partners, invites, start, requests, captcha, messaging  # noqa: F401,E402

__all__ = ["router"]
