"""Admin management (/admin) and data reset (/reset) commands."""
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from api import api
from config import ADMIN_TELEGRAM_IDS, ADMIN_OWNER_ID

log = logging.getLogger(__name__)
router = Router()


class AdminManage(StatesGroup):
    waiting_for_id = State()


def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_OWNER_ID


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_TELEGRAM_IDS


# ── /admin: manage admin list (owner only) ─────────────

@router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext):
    if not is_owner(msg.from_user.id):
        return

    await state.clear()
    admin_list = ", ".join(str(aid) for aid in sorted(ADMIN_TELEGRAM_IDS))

    await msg.answer(
        f"🔧 <b>Управление админами</b>\n\n"
        f"👑 Owner: <code>{ADMIN_OWNER_ID}</code>\n"
        f"👥 Админы: <code>{admin_list}</code>\n"
        f"Всего: {len(ADMIN_TELEGRAM_IDS)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin_remove")],
        ]),
    )


@router.callback_query(F.data == "admin_add")
async def cb_admin_add(cb: CallbackQuery, state: FSMContext):
    if not is_owner(cb.from_user.id):
        await cb.answer("Только owner", show_alert=True)
        return

    await state.set_state(AdminManage.waiting_for_id)
    await state.update_data(action="add")
    await cb.message.answer(
        "📝 <b>Добавление админа</b>\n\n"
        "Отправьте одним из способов:\n"
        "• Telegram ID числом (например <code>123456789</code>)\n"
        "• Перешлите любое сообщение от этого человека",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(F.data == "admin_remove")
async def cb_admin_remove(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("Только owner", show_alert=True)
        return

    others = sorted(aid for aid in ADMIN_TELEGRAM_IDS if aid != ADMIN_OWNER_ID)
    if not others:
        await cb.answer("Нет админов для удаления (кроме owner)", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=f"❌ {aid}", callback_data=f"admin_rm_{aid}")]
        for aid in others
    ]
    buttons.append([InlineKeyboardButton(text="« Отмена", callback_data="admin_cancel")])

    await cb.message.answer(
        "🗑 <b>Удаление админа</b>\n\nВыберите кого удалить:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("admin_rm_"))
async def cb_admin_do_remove(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("Только owner", show_alert=True)
        return

    tid = int(cb.data.replace("admin_rm_", ""))
    result = await api("delete", f"/api/admin/admins/{tid}")

    if result and result.get("status") == "ok":
        ADMIN_TELEGRAM_IDS.discard(tid)
        await cb.message.edit_text(
            f"✅ Админ <code>{tid}</code> удалён.\n\n"
            f"Текущие админы: {', '.join(str(x) for x in result['admin_ids'])}",
            parse_mode=ParseMode.HTML,
        )
    else:
        ADMIN_TELEGRAM_IDS.discard(tid)
        await cb.message.edit_text(
            f"✅ Админ <code>{tid}</code> удалён (локально).",
            parse_mode=ParseMode.HTML,
        )
    await cb.answer()


@router.message(AdminManage.waiting_for_id)
async def fsm_admin_id(msg: Message, state: FSMContext):
    new_id = None

    if msg.forward_from:
        new_id = msg.forward_from.id
    elif msg.text and msg.text.strip().isdigit():
        new_id = int(msg.text.strip())

    if not new_id:
        await msg.answer(
            "❌ Не удалось определить ID.\n\n"
            "Отправьте число или перешлите сообщение от пользователя.\n"
            "Отправьте /admin чтобы отменить.",
        )
        return

    await state.clear()

    if new_id in ADMIN_TELEGRAM_IDS:
        await msg.answer(
            f"ℹ️ <code>{new_id}</code> уже является админом.",
            parse_mode=ParseMode.HTML,
        )
        return

    result = await api("post", "/api/admin/admins", json={"telegram_id": new_id})

    if result and result.get("status") == "ok":
        ADMIN_TELEGRAM_IDS.add(new_id)
        await msg.answer(
            f"✅ <b>Админ добавлен!</b>\n\n"
            f"ID: <code>{new_id}</code>\n"
            f"Текущие админы: {', '.join(str(x) for x in sorted(ADMIN_TELEGRAM_IDS))}",
            parse_mode=ParseMode.HTML,
        )
    else:
        ADMIN_TELEGRAM_IDS.add(new_id)
        await msg.answer(
            f"✅ Админ <code>{new_id}</code> добавлен (локально).\n"
            "Backend API недоступен — при рестарте нужно добавить повторно.",
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data == "admin_cancel")
async def cb_admin_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()


# ── /reset: wipe own data (admins only) ───────────────

@router.message(Command("reset"))
async def cmd_reset(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return

    await state.clear()
    await msg.answer(
        "⚠️ <b>Сброс данных</b>\n\n"
        "Это удалит ВСЕ ваши данные:\n"
        "• Все расписания (включая дефолтное)\n"
        "• Все бронирования (как организатор и как гость)\n"
        "• Подключения календарей\n\n"
        "После сброса вы увидите онбординг как новый пользователь.\n\n"
        "<b>Вы уверены?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, сбросить всё", callback_data="reset_confirm"),
                InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel"),
            ],
        ]),
    )


@router.callback_query(F.data == "reset_confirm")
async def cb_reset_confirm(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Только для админов", show_alert=True)
        return

    result = await api("post", f"/api/admin/reset-user?telegram_id={cb.from_user.id}")

    if result and result.get("status") == "ok":
        deleted = result.get("deleted", {})
        await cb.message.edit_text(
            "✅ <b>Данные сброшены!</b>\n\n"
            f"Удалено:\n"
            f"• Расписаний: {deleted.get('schedules', 0)}\n"
            f"• Бронирований (организатор): {deleted.get('bookings_as_organizer', 0)}\n"
            f"• Бронирований (гость): {deleted.get('bookings_as_guest', 0)}\n\n"
            "Нажмите /start чтобы начать заново.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await cb.message.edit_text(
            "❌ Ошибка сброса. Backend API недоступен.\n"
            "Проверьте логи.",
        )
    await cb.answer()
