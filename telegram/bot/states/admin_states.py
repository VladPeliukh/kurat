from aiogram.fsm.state import State, StatesGroup


class AdminCuratorStats(StatesGroup):
    waiting_curator_id = State()


class AdminCuratorInfo(StatesGroup):
    waiting_curator_id = State()

