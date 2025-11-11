from aiogram import Bot
from aiogram.exceptions import TelegramNotFound, TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from ..config import Config
from ..services import Services

base_commands = [
                BotCommand(command='/start', description="Запуск бота"),
                BotCommand(command='/cancel', description="Отменить текущее действие"),
        ]

regular_admin_commands = [
	BotCommand(command='/admin', description="Админ панель")
]

super_admin_commands = [
]

developer_commands = [
		BotCommand(command='/logs', description='Получить Логи'),
]

commands_list = [base_commands, regular_admin_commands, super_admin_commands, developer_commands]

async def setup_commands(bot: Bot, services: Services):

	try:
		await bot.set_my_commands(commands=base_commands, scope=BotCommandScopeDefault())
	except Exception as e:
		print(e)

	regular_admins, super_admins = await services.admin.list_admins()

	for regular_admin in regular_admins:
		try:
			await bot.set_my_commands(base_commands + regular_admin_commands,
									  scope=BotCommandScopeChat(chat_id=regular_admin.user_id))
		except (TelegramNotFound, TelegramBadRequest, Exception):
			pass

	for super_admin in super_admins:
		try:
			await bot.set_my_commands(base_commands + regular_admin_commands + super_admin_commands,
									  scope=BotCommandScopeChat(chat_id=super_admin.user_id)
									  )
		except (TelegramNotFound, TelegramBadRequest, Exception):
			pass

	for developer_id in Config.DEVELOPERS_IDS:
		try:
			await bot.set_my_commands(base_commands + regular_admin_commands + super_admin_commands + developer_commands,
									  scope=BotCommandScopeChat(chat_id=developer_id)
									  )
		except (TelegramNotFound, TelegramBadRequest, Exception):
			pass

async def delete_commands(bot: Bot, services: Services):
	try:
		await bot.set_my_commands([], scope=BotCommandScopeDefault())
		regular_admins, super_admins = await services.admin.list_admins()

		for admin in regular_admins + super_admins:
			await bot.set_my_commands([], scope=BotCommandScopeChat(chat_id=admin.user_id))
	except Exception:
		pass