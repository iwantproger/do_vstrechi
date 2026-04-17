"""FSM flow: ��оздание расписания (title → duration → buffer → work_days → start_time → end_time → platform)."""
import logging
from datetime import datetime
from urllib.parse import quote

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

from api import api
from config import MINI_APP_URL
from keyboards import kb_duration, kb_buffer, kb_platform, kb_back_main, kb_work_days, kb_fsm_nav
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


@router.callback_query(F.data == "create_schedule_chat")
async def cb_create_schedule_chat(cb: CallbackQuery, state: FSMContext):
    """Fallback: создание расписания в чате, если Mini App недоступен."""
    await state.clear()
    await state.set_state(CreateSchedule.title)
    await cb.message.edit_text(
        "➕ <b>Создание расписания в чате</b>\n\n"
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
    await state.update_data(buffer_time=buf, selected_days=[])
    await state.set_state(CreateSchedule.work_days)
    await cb.message.edit_text(
        f"✓ Буфер: {buf} мин\n\n"
        "Шаг 4/5: Рабочие дни\n\n"
        "Выбрано: <b>не выбраны</b>\n\n"
        "Нажимай на дни, чтобы выбрать/убрать:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_work_days([]),
    )
    await cb.answer()


@router.callback_query(CreateSchedule.work_days, F.data.startswith("day_"))
async def fsm_toggle_day(cb: CallbackQuery, state: FSMContext):
    """Toggle отдельного дня."""
    day = int(cb.data.split("_")[1])
    data = await state.get_data()
    selected = data.get("selected_days", [])

    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
        selected.sort()

    await state.update_data(selected_days=selected)
    days_str = ", ".join(DAYS_RU[d] for d in selected) if selected else "не выбраны"
    await cb.message.edit_text(
        "Шаг 4/5: Рабочие дни\n\n"
        f"Выбрано: <b>{days_str}</b>\n\n"
        "Нажимай на дни, чтобы выбрать/убрать:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_work_days(selected),
    )
    await cb.answer()


@router.callback_query(CreateSchedule.work_days, F.data == "days_weekdays")
async def fsm_weekdays(cb: CallbackQuery, state: FSMContext):
    selected = [0, 1, 2, 3, 4]
    await state.update_data(selected_days=selected)
    days_str = ", ".join(DAYS_RU[d] for d in selected)
    await cb.message.edit_text(
        "Шаг 4/5: Рабочие дни\n\n"
        f"Выбрано: <b>{days_str}</b>\n\n"
        "Нажимай на дни, чтобы выбрать/убрать:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_work_days(selected),
    )
    await cb.answer()


@router.callback_query(CreateSchedule.work_days, F.data == "days_all")
async def fsm_all_days(cb: CallbackQuery, state: FSMContext):
    selected = [0, 1, 2, 3, 4, 5, 6]
    await state.update_data(selected_days=selected)
    days_str = ", ".join(DAYS_RU[d] for d in selected)
    await cb.message.edit_text(
        "Шаг 4/5: Рабочие дни\n\n"
        f"Выбрано: <b>{days_str}</b>\n\n"
        "Нажимай на дни, чтобы выбрать/убрать:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_work_days(selected),
    )
    await cb.answer()


@router.callback_query(CreateSchedule.work_days, F.data == "days_done")
async def fsm_days_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_days", [])
    if not selected:
        await cb.answer("Выбери хотя бы один день", show_alert=True)
        return

    await state.update_data(work_days=selected)
    await state.set_state(CreateSchedule.start_time)
    days_str = ", ".join(DAYS_RU[d] for d in sorted(selected))
    await cb.message.edit_text(
        f"✓ Дни: {days_str}\n\n"
        "Шаг 4б: Начало рабочего дня\n"
        "Введи время в формате <code>ЧЧ:ММ</code>, например: <code>09:00</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_fsm_nav,
    )
    await cb.answer()


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
        reply_markup=kb_fsm_nav,
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
        sid = str(result["id"])
        days_str = ", ".join(DAYS_RU[d] for d in sorted(data.get("work_days", [])))
        buffer_time = data.get("buffer_time", 0)
        booking_url = f"https://t.me/do_vstrechi_bot/app?startapp={sid}"
        share_text = f"Запишись на встречу: {data['title']}"
        tg_share = f"https://t.me/share/url?url={quote(booking_url)}&text={quote(share_text)}"

        await cb.message.edit_text(
            f"🎉 <b>Расписание создано!</b>\n\n"
            f"📅 {data['title']}\n"
            f"⏱ {data['duration']} мин · перерыв {buffer_time} мин\n"
            f"📆 {days_str}\n"
            f"🕐 {data['start_time']} — {data['end_time']}\n\n"
            f"🔗 <b>Ваша ссылка на бронирование:</b>\n"
            f"<code>{booking_url}</code>\n\n"
            "💡 Также можно использовать inline-режим: в любом чате введите @do_vstrechi_bot",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться в Telegram", url=tg_share)],
                [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data=f"copy_link_{sid}")],
                [InlineKeyboardButton(
                    text="🌐 Открыть в приложении",
                    url=f"https://t.me/do_vstrechi_bot/app?startapp=view_{sid}",
                )],
                [InlineKeyboardButton(
                    text="👁 Как видят другие",
                    url=f"https://t.me/do_vstrechi_bot/app?startapp={sid}",
                )],
                [InlineKeyboardButton(text="🔍 Проверить inline-режим", callback_data="check_inline")],
                [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")],
            ]),
        )
    else:
        await cb.message.edit_text(
            "❌ Ошибка создания расписания. Попробуй ещё раз.",
            reply_markup=kb_back_main,
        )
    await cb.answer()


# ── FSM navigation ─────────────────────────────────────

@router.callback_query(F.data == "fsm_cancel")
async def fsm_cancel(cb: CallbackQuery, state: FSMContext):
    """Отмена создания расписания."""
    await state.clear()
    await cb.message.edit_text(
        "❌ Создание расписания отменено.",
        reply_markup=kb_back_main,
    )
    await cb.answer()


@router.callback_query(F.data == "fsm_back")
async def fsm_back(cb: CallbackQuery, state: FSMContext):
    """Возврат на предыдущий шаг."""
    current = await state.get_state()
    data = await state.get_data()

    if current == CreateSchedule.duration.state:
        await state.set_state(CreateSchedule.title)
        await cb.message.edit_text(
            "➕ <b>Создание расписания</b>\n\n"
            "Шаг 1/5: Введи название расписания.\n"
            "Например: <i>Консультация по маркетингу</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_fsm_nav,
        )
    elif current == CreateSchedule.buffer_time.state:
        await state.set_state(CreateSchedule.duration)
        await cb.message.edit_text(
            "Шаг 2/5: Выбери длительность встречи:",
            reply_markup=kb_duration,
        )
    elif current == CreateSchedule.work_days.state:
        await state.set_state(CreateSchedule.buffer_time)
        dur = data.get("duration", "?")
        await cb.message.edit_text(
            f"✓ Длительность: {dur} мин\n\n"
            "Шаг 3/5: Буфер между встречами\n"
            "(время на отдых/подготовку):",
            reply_markup=kb_buffer,
        )
    elif current == CreateSchedule.start_time.state:
        selected = data.get("selected_days", [])
        await state.set_state(CreateSchedule.work_days)
        days_str = ", ".join(DAYS_RU[d] for d in selected) if selected else "не выбраны"
        await cb.message.edit_text(
            "Шаг 4/5: Рабочие дни\n\n"
            f"Выбрано: <b>{days_str}</b>\n\n"
            "Нажимай на дни, чтобы выбрать/убрать:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_work_days(selected),
        )
    elif current == CreateSchedule.end_time.state:
        await state.set_state(CreateSchedule.start_time)
        await cb.message.edit_text(
            "Шаг 4б: Начало рабочего дня\n"
            "Введи время в формате <code>ЧЧ:ММ</code>, например: <code>09:00</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_fsm_nav,
        )
    elif current == CreateSchedule.platform.state:
        await state.set_state(CreateSchedule.end_time)
        start = data.get("start_time", "?")
        await cb.message.edit_text(
            f"✓ Начало: {start}\n\n"
            "Конец рабочего дня (например: <code>18:00</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_fsm_nav,
        )
    else:
        await cb.answer("Вы на первом шаге")
        return

    await cb.answer()


# ── Inline mode check ──────────────────────────────────

@router.callback_query(F.data == "check_inline")
async def cb_check_inline(cb: CallbackQuery):
    """Проверить доступность inline-режима."""
    try:
        me = await cb.bot.get_me()
        if me.supports_inline_queries:
            await cb.message.answer(
                "✅ <b>Inline-режим работает!</b>\n\n"
                "В любом чате введите <code>@do_vstrechi_bot</code> "
                "и выберите расписание для отправки.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await cb.message.answer(
                "⚠️ <b>Inline-режим не включён</b>\n\n"
                "Чтобы включить:\n"
                "1. Откройте @BotFather\n"
                "2. Выберите бота\n"
                "3. Bot Settings → Inline Mode → Turn on\n\n"
                "После включения попробуйте снова.",
                parse_mode=ParseMode.HTML,
            )
            log.warning(f"Inline mode disabled for bot, user {cb.from_user.id} checked")
    except Exception as e:
        log.error(f"Inline check error: {e}")
        await cb.message.answer("❌ Не удалось проверить inline-режим.")
    await cb.answer()
