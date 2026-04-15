"""FSM flow: создание расписания (title → duration → buffer → work_days → start_time → end_time → platform)."""
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from api import api
from config import MINI_APP_URL
from keyboards import kb_duration, kb_buffer, kb_platform, kb_back_main
from formatters import DAYS_RU
from states import CreateSchedule

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "create_schedule")
async def cb_create_schedule(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(CreateSchedule.title)
    await cb.message.edit_text(
        "➕ <b>Создание нового расписания</b>\n\n"
        "Шаг 1/5: Введи название расписания.\n"
        "Например: <i>Консультация по маркетингу</i>",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.message(CreateSchedule.title)
async def fsm_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip())
    await state.set_state(CreateSchedule.duration)
    await msg.answer("Шаг 2/5: Выбери длительность встречи:", reply_markup=kb_duration)


@router.callback_query(CreateSchedule.duration, F.data.startswith("dur_"))
async def fsm_duration(cb: CallbackQuery, state: FSMContext):
    duration = int(cb.data.split("_")[1])
    await state.update_data(duration=duration)
    await state.set_state(CreateSchedule.buffer_time)
    await cb.message.edit_text(
        f"✓ Длительность: {duration} мин\n\n"
        "Шаг 3/5: Буфер между встречами\n"
        "(время на отдых/подготовку):",
        reply_markup=kb_buffer,
    )
    await cb.answer()


@router.callback_query(CreateSchedule.buffer_time, F.data.startswith("buf_"))
async def fsm_buffer(cb: CallbackQuery, state: FSMContext):
    buf = int(cb.data.split("_")[1])
    await state.update_data(buffer_time=buf)
    await state.set_state(CreateSchedule.work_days)
    await cb.message.edit_text(
        f"✓ Буфер: {buf} мин\n\n"
        "Шаг 4/5: Рабочие дни\n\n"
        "Введи числами через пробел:\n"
        "<code>0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс</code>\n\n"
        "Например: <code>0 1 2 3 4</code> — будни",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.message(CreateSchedule.work_days)
async def fsm_work_days(msg: Message, state: FSMContext):
    try:
        days = [int(d) for d in msg.text.strip().split() if d.isdigit() and 0 <= int(d) <= 6]
        if not days:
            raise ValueError
    except Exception:
        await msg.answer("Неверный формат. Введи числа от 0 до 6 через пробел. Например: 0 1 2 3 4")
        return

    await state.update_data(work_days=days)
    await state.set_state(CreateSchedule.start_time)
    days_str = ", ".join(DAYS_RU[d] for d in sorted(days))
    await msg.answer(
        f"✓ Дни: {days_str}\n\n"
        "Шаг 4б: Начало рабочего дня\n"
        "Введи время в формате <code>ЧЧ:ММ</code>, например: <code>09:00</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSchedule.start_time)
async def fsm_start_time(msg: Message, state: FSMContext):
    t = msg.text.strip()
    try:
        datetime.strptime(t, "%H:%M")
    except Exception:
        await msg.answer("Неверный формат. Введи время как 09:00")
        return
    await state.update_data(start_time=t)
    await state.set_state(CreateSchedule.end_time)
    await msg.answer(
        f"✓ Начало: {t}\n\n"
        "Конец рабочего дня (например: <code>18:00</code>):",
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSchedule.end_time)
async def fsm_end_time(msg: Message, state: FSMContext):
    t = msg.text.strip()
    try:
        datetime.strptime(t, "%H:%M")
    except Exception:
        await msg.answer("Неверный формат. Введи время как 18:00")
        return
    await state.update_data(end_time=t)
    await state.set_state(CreateSchedule.platform)
    await msg.answer(
        f"✓ Конец: {t}\n\n"
        "Шаг 5/5: Платформа для встреч:",
        reply_markup=kb_platform,
    )


@router.callback_query(CreateSchedule.platform, F.data.startswith("plat_"))
async def fsm_platform(cb: CallbackQuery, state: FSMContext):
    platform = cb.data.split("_")[1]
    data = await state.get_data()
    data["platform"] = platform
    telegram_id = cb.from_user.id

    await state.clear()

    result = await api("post", f"/api/schedules?telegram_id={telegram_id}", json=data)

    if result:
        days_str    = ", ".join(DAYS_RU[d] for d in sorted(data.get("work_days", [])))
        booking_url = f"{MINI_APP_URL}?schedule_id={result['id']}"
        await cb.message.edit_text(
            f"🎉 <b>Расписание создано!</b>\n\n"
            f"📅 {data['title']}\n"
            f"⏱ {data['duration']} мин\n"
            f"📆 {days_str}\n"
            f"🕐 {data['start_time']} — {data['end_time']}\n\n"
            f"🔗 <b>Ссылка для клиентов:</b>\n"
            f"<code>{booking_url}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")]
            ]),
        )
    else:
        await cb.message.edit_text(
            "❌ Ошибка создания расписания. Попробуй ещё раз.",
            reply_markup=kb_back_main,
        )
    await cb.answer()
