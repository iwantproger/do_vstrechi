"""FSM States для создания расписания."""
from aiogram.fsm.state import State, StatesGroup


class CreateSchedule(StatesGroup):
    title       = State()
    duration    = State()
    buffer_time = State()
    work_days   = State()
    start_time  = State()
    end_time    = State()
    platform    = State()
