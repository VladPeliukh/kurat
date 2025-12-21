from datetime import date, datetime, time

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .router import router
from ...keyboards import AdminKeyboards
from ...keyboards.calendar import AdminCalendarCallback, CalendarView, CuratorCalendarKeyboard
from ...services.curator_service import CuratorService
from ...states.admin_states import AdminStatsSelection
from ...utils.curator_stats import prepare_all_curators_snapshot
from ...utils.handlers_helpers import (
	_get_calendar_state,
	_get_selected_date,
	_initial_calendar_state,
	_is_admin,
	_is_super_admin,
	_refresh_calendar_markup,
	_refresh_year_page,
	_serialize_calendar_state,
	_store_calendar_state,
	_store_selected_date,
)


@router.callback_query(F.data == "adm_menu:all_stats")
async def prompt_all_curators_stats_range(call: CallbackQuery, state: FSMContext) -> None:
	if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
		await call.answer("Эта функция доступна только администраторам.", show_alert=True)
		return
	
	await state.clear()
	start_state = _initial_calendar_state()
	await state.set_state(AdminStatsSelection.choosing_start)
	await _store_calendar_state(state, "adm_start", start_state)
	await _store_selected_date(state, "adm_start", None)
	await _store_selected_date(state, "adm_end", None)
	await _store_calendar_state(state, "adm_end", _initial_calendar_state())
	prompt = "Выберите начальную дату периода для статистики по всем пользователям:"
	markup = CuratorCalendarKeyboard.build(
		start_state, target="adm_start", callback_factory=AdminCalendarCallback
	)
	try:
		await call.message.answer(prompt, reply_markup=markup)
	except Exception:
		try:
			await call.bot.send_message(call.from_user.id, prompt, reply_markup=markup)
		except Exception:
			await call.answer("Не удалось показать календарь.", show_alert=True)
			return
	await call.answer()


@router.callback_query(AdminCalendarCallback.filter())
async def admin_stats_calendar_action(
		call: CallbackQuery,
		callback_data: AdminCalendarCallback,
		state: FSMContext,
) -> None:
	if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
		await call.answer("Эта функция доступна только администраторам.", show_alert=True)
		return
	
	target = callback_data.target
	if target not in ("adm_start", "adm_end"):
		await call.answer("Неизвестная цель календаря.", show_alert=True)
		return
	
	calendar_state = await _get_calendar_state(state, target)
	# Эта переменная не используется напрямую, но нужна для логики ниже
	# current_selected_date = await _get_selected_date(state, target)
	
	if callback_data.action == "prev":
		if calendar_state.view == CalendarView.MONTHS:
			calendar_state.year -= 1
			_refresh_year_page(calendar_state)
		elif calendar_state.view == CalendarView.DAYS:
			calendar_state.month -= 1
			if calendar_state.month < 1:
				calendar_state.month = 12
				calendar_state.year -= 1
			_refresh_year_page(calendar_state)
		else:  # YEARS
			calendar_state.year_page -= 12
			if calendar_state.year_page < 1:
				calendar_state.year_page = 1
		await _store_calendar_state(state, target, calendar_state)
		await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
		await call.answer()
		return
	
	if callback_data.action == "next":
		if calendar_state.view == CalendarView.MONTHS:
			calendar_state.year += 1
			_refresh_year_page(calendar_state)
		elif calendar_state.view == CalendarView.DAYS:
			calendar_state.month += 1
			if calendar_state.month > 12:
				calendar_state.month = 1
				calendar_state.year += 1
			_refresh_year_page(calendar_state)
		else:  # YEARS
			calendar_state.year_page += 12
		await _store_calendar_state(state, target, calendar_state)
		await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
		await call.answer()
		return
	
	if callback_data.action == "switch_view":
		match calendar_state.view:
			case CalendarView.DAYS:
				calendar_state.view = CalendarView.MONTHS
			case CalendarView.MONTHS:
				calendar_state.view = CalendarView.YEARS
			case _:
				calendar_state.view = CalendarView.DAYS
		if calendar_state.view == CalendarView.DAYS and calendar_state.month is None:
			calendar_state.month = date.today().month
		_refresh_year_page(calendar_state)
		await _store_calendar_state(state, target, calendar_state)
		await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
		await call.answer()
		return
	
	if callback_data.action == "go_today":
		today_state = _initial_calendar_state()
		await _store_calendar_state(state, target, today_state)
		await _refresh_calendar_markup(call, target=target, calendar_state=today_state)
		await call.answer()
		return
	
	if callback_data.action == "reset":
		await state.clear()
		await call.message.answer(
			"Выбор даты сброшен.", reply_markup=AdminKeyboards.back_to_admin_menu()
		)
		await call.answer()
		return
	
	if callback_data.action in {"choose_year", "choose_month", "choose_day"}:
		match callback_data.action:
			case "choose_year":
				calendar_state.view = CalendarView.MONTHS
				calendar_state.year = callback_data.year or calendar_state.year
				# При выборе года сбрасываем выбранную дату
				await _store_selected_date(state, target, None)
			
			case "choose_month":
				calendar_state.view = CalendarView.DAYS
				calendar_state.month = callback_data.month or calendar_state.month
				# При выборе месяца сбрасываем выбранную дату
				await _store_selected_date(state, target, None)
			
			case "choose_day":
				# Проверяем, что все необходимые поля есть
				year = callback_data.year or calendar_state.year
				month = callback_data.month or calendar_state.month
				day = callback_data.day
				
				if not all([year, month, day]):
					await call.answer("Неполные данные даты.", show_alert=True)
					return
				
				try:
					selected_date = date(year, month, day)
				except ValueError:
					await call.answer("Некорректная дата.", show_alert=True)
					return
				
				# Сохраняем выбранную дату
				await _store_selected_date(state, target, selected_date)
			
			case _:
				await call.answer("Неизвестное действие.", show_alert=True)
				return
		
		_refresh_year_page(calendar_state)
		await _store_calendar_state(state, target, calendar_state)
		await _refresh_calendar_markup(call, target=target, calendar_state=calendar_state)
		await call.answer()
		return
	
	if callback_data.action == "confirm":
		# Получаем выбранную дату из состояния
		selected_date = await _get_selected_date(state, target)
		if not selected_date:
			await call.answer("Пожалуйста, выберите дату.", show_alert=True)
			return
		
		# Дату уже сохранили в choose_day, можно не сохранять повторно
		# await _store_selected_date(state, target, selected_date)
		serialized_state = _serialize_calendar_state(calendar_state)
		await _store_calendar_state(state, target, serialized_state)
		
		if target == "adm_start":
			await state.set_state(AdminStatsSelection.choosing_end)
			# Сериализуем состояние календаря для сохранения
			serialized_state = _serialize_calendar_state(calendar_state)
			await _store_calendar_state(state, "adm_end", serialized_state)
			
			prompt = "Выберите конечную дату периода:"
			markup = CuratorCalendarKeyboard.build(
				calendar_state,
				target="adm_end",
				callback_factory=AdminCalendarCallback,
			)
			await call.message.answer(prompt, reply_markup=markup)
			await call.answer()
			return
		
		# target == "adm_end"
		start_date = await _get_selected_date(state, "adm_start")
		end_date = selected_date
		if not start_date:
			await call.answer("Сначала выберите начальную дату.", show_alert=True)
			return
		if end_date < start_date:
			await call.answer("Конечная дата не может быть раньше начальной.", show_alert=True)
			return
		
		await state.clear()
		svc = CuratorService(call.bot)
		
		# Преобразуем date в datetime для prepare_all_curators_snapshot
		start_datetime = datetime.combine(start_date, time.min).replace(tzinfo=None)
		end_datetime = datetime.combine(end_date, time.max).replace(tzinfo=None)
		
		# Вызываем prepare_all_curators_snapshot с datetime параметрами
		result = await prepare_all_curators_snapshot(
			svc,
			start=start_datetime,
			end=end_datetime
		)
		if result is None:
			await call.message.answer(
				"Нет данных для выбранного периода.",
				reply_markup=AdminKeyboards.back_to_admin_menu(),
			)
			await call.answer()
			return
		
		document, caption = result
		await call.message.answer_document(
			document,
			caption=caption,
			reply_markup=AdminKeyboards.back_to_admin_menu(),
		)
		await call.answer()
		return
	
	await call.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data == "adm_menu:all_stats_all_time")
async def send_all_curators_stats_all_time(call: CallbackQuery) -> None:
	if not (await _is_super_admin(call.from_user.id) or await _is_admin(call.from_user.id)):
		await call.answer("Эта функция доступна только администраторам.", show_alert=True)
		return
	
	svc = CuratorService(call.bot)
	# Для полной статистики вызываем без параметров start/end
	snapshot = await prepare_all_curators_snapshot(svc)
	if snapshot is None:
		await call.message.answer(
			"Нет данных для сводки.", reply_markup=AdminKeyboards.back_to_admin_menu()
		)
		await call.answer()
		return
	
	document, caption = snapshot
	await call.message.answer_document(
		document, caption=caption, reply_markup=AdminKeyboards.back_to_admin_menu()
	)
	await call.answer()
