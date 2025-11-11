from aiogram import Bot

from .admin_service import AdminService

class Services:
	"""Контейнер для всех сервисов"""

	def __init__(self, bot: Bot):
		self.admin =AdminService()


def setup_services(bot: Bot) -> Services:
	"""Инициализация всех сервисов"""
	return Services(bot)