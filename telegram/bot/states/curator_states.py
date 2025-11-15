from aiogram.fsm.state import State, StatesGroup


class CuratorStatsSelection(StatesGroup):
    choosing_start = State()
    choosing_end = State()


__all__ = ["CuratorStatsSelection"]
