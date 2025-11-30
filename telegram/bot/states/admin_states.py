from aiogram.fsm.state import State, StatesGroup


class AdminCuratorInfo(StatesGroup):
    waiting_curator_id = State()


class AdminBroadcast(StatesGroup):
    waiting_message = State()


class AdminPromoteAdmin(StatesGroup):
    waiting_curator_id = State()

