import asyncio
import logging
import os
import threading
import html
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.exceptions import TelegramBadRequest
import aiosqlite

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "RepetlyAssistantBot" 

# ==========================================
# ⚠️ ОБЯЗАТЕЛЬНО ЗАМЕНИ НА СВОИ ДАННЫЕ!
# ==========================================
ADMIN_USERNAME = "@furseg" 
ADMIN_TG_LINK = "https://t.me/furseg" 
ADMIN_ID = 123456789 # ВСТАВЬ СЮДА СВОЙ ID ИЗ @userinfobot!

logging.basicConfig(level=logging.INFO)
router = Router()

# ==========================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ БЕЗОПАСНОГО РЕДАКТИРОВАНИЯ
# ==========================================
async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.error(f"Ошибка при редактировании: {e}")

# ==========================================
# 1. БАЗА ДАННЫХ
# ==========================================
DB_NAME = "repetly.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT, payment_details TEXT DEFAULT '', is_pro INTEGER DEFAULT 0, pro_until TEXT DEFAULT NULL)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, name TEXT, 
                student_chat_id INTEGER, parent_chat_id INTEGER,
                subject TEXT, price INTEGER DEFAULT 0, schedule TEXT,
                sub_total INTEGER DEFAULT 0, sub_left INTEGER DEFAULT 0,
                karma INTEGER DEFAULT 100
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, 
                student_id INTEGER, lesson_time TEXT, 
                reminded_24h INTEGER DEFAULT 0, reminded_2h INTEGER DEFAULT 0,
                is_paid INTEGER DEFAULT 0, price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending', is_reminded INTEGER DEFAULT 0
            )
        """)
        await db.commit()

# --- ФУНКЦИИ БАЗЫ ---
async def set_user_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO users (user_id, role) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET role = excluded.role", (user_id, role))
        await db.commit()

async def get_user_role(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_user_pro(user_id: int, days: int = 30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_pro = 1, pro_until = ? WHERE user_id = ?", (expiry_date, user_id))
        await db.commit()
    return expiry_date

async def get_user_pro(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT is_pro, pro_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 1:
                if row[1]:
                    pro_until = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    if pro_until > datetime.now():
                        return 1
                    else:
                        await db.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (user_id,))
                        await db.commit()
                        return 0
                return 1
            return 0

async def update_payment_details(tutor_id: int, details: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET payment_details = ? WHERE user_id = ?", (details, tutor_id))
        await db.commit()

async def get_payment_details(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT payment_details FROM users WHERE user_id = ?", (tutor_id,)) as cursor:
            row = await cursor.fetchone()
            return html.escape(row[0]) if row and row[0] else "Реквизиты пока не указаны."

async def add_student(tutor_id: int, name: str, subject: str, price: int, schedule: str, sub_total: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO students (tutor_id, name, subject, price, schedule, sub_total, sub_left) VALUES (?, ?, ?, ?, ?, ?, ?)", (tutor_id, html.escape(name), html.escape(subject), price, html.escape(schedule), sub_total, sub_total))
        await db.commit()
        return cursor.lastrowid 

async def delete_student_from_db(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM lessons WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        await db.commit()

async def get_students_by_tutor(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name, subject, price, schedule, sub_left, sub_total, karma FROM students WHERE tutor_id = ?", (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def get_student_info(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name, tutor_id, subject, price, sub_left, sub_total, karma, parent_chat_id FROM students WHERE id = ?", (student_id,)) as cursor:
            return await cursor.fetchone()

async def get_student_price(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT price FROM students WHERE id = ?", (student_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def bind_user(student_id: int, chat_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        if role == "parent":
            await db.execute("UPDATE students SET parent_chat_id = ? WHERE id = ?", (chat_id, student_id))
        else:
            await db.execute("UPDATE students SET student_chat_id = ? WHERE id = ?", (chat_id, student_id))
        await db.commit()
    await set_user_role(chat_id, role)

async def get_student_by_chat_id(chat_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT id, name, tutor_id, subject, schedule, sub_left, sub_total, karma FROM students WHERE parent_chat_id = ?" if role == "parent" else "SELECT id, name, tutor_id, subject, schedule, sub_left, sub_total, karma FROM students WHERE student_chat_id = ?"
        async with db.execute(query, (chat_id,)) as cursor:
            return await cursor.fetchone()

async def add_lesson(tutor_id: int, student_id: int, lesson_time: str):
    price = await get_student_price(student_id)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO lessons (tutor_id, student_id, lesson_time, price) VALUES (?, ?, ?, ?)", (tutor_id, student_id, lesson_time, price))
        await db.commit()

async def get_lessons_for_tutor(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.id, l.lesson_time, s.name, s.subject, l.status FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.tutor_id = ? ORDER BY l.lesson_time ASC"
        async with db.execute(query, (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def get_lessons_for_student(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.id, l.lesson_time, s.subject FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.student_id = ? ORDER BY l.lesson_time ASC"
        async with db.execute(query, (student_id,)) as cursor:
            return await cursor.fetchall()

async def get_unpaid_lessons(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.id, l.lesson_time, s.name, l.price, s.parent_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.tutor_id = ? AND l.is_paid = 0 AND l.status != 'canceled' ORDER BY l.lesson_time ASC"
        async with db.execute(query, (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def mark_lesson_paid(lesson_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE lessons SET is_paid = 1 WHERE id = ?", (lesson_id,))
        await db.commit()

async def deduct_subscription(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE students SET sub_left = sub_left - 1 WHERE id = ? AND sub_left > 0", (student_id,))
        await db.commit()

async def lower_karma(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE students SET karma = karma - 10 WHERE id = ? AND karma > 10", (student_id,))
        await db.commit()

async def cancel_lessons_in_period(tutor_id: int, start_date: datetime, end_date: datetime):
    canceled_count = 0
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT id, lesson_time FROM lessons WHERE tutor_id = ? AND status != 'canceled'"
        async with db.execute(query, (tutor_id,)) as cursor:
            lessons = await cursor.fetchall()
        for l_id, time_str in lessons:
            try:
                l_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
                if start_date <= l_time <= end_date:
                    await db.execute("UPDATE lessons SET status = 'canceled' WHERE id = ?", (l_id,))
                    canceled_count += 1
            except ValueError:
                continue
        await db.commit()
    return canceled_count

async def get_all_students_for_tutor(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT student_chat_id, parent_chat_id FROM students WHERE tutor_id = ?", (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def get_monthly_earnings(tutor_id: int):
    now = datetime.now()
    month_str = now.strftime("%m.%Y")
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT SUM(price), COUNT(id) FROM lessons WHERE tutor_id = ? AND is_paid = 1 AND lesson_time LIKE ?"
        async with db.execute(query, (tutor_id, f"%{month_str}%")) as cursor:
            row = await cursor.fetchone()
            return row[0] or 0, row[1] or 0 

async def get_reminders_count(tutor_id: int):
    now = datetime.now()
    month_str = now.strftime("%m.%Y")
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT COUNT(id) FROM lessons WHERE tutor_id = ? AND is_reminded = 1 AND lesson_time LIKE ?"
        async with db.execute(query, (tutor_id, f"%{month_str}%")) as cursor:
            row = await cursor.fetchone()
            return row[0] or 0

async def update_lesson_status(lesson_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE lessons SET status = ? WHERE id = ?", (status, lesson_id))
        await db.commit()

async def change_lesson_time(lesson_id: int, new_time: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE lessons SET lesson_time = ?, status = 'confirmed', reminded_24h = 0, reminded_2h = 0 WHERE id = ?", (new_time, lesson_id))
        await db.commit()

async def get_parent_journal(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(id) FROM lessons WHERE student_id = ? AND status != 'canceled'", (student_id,)) as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(id) FROM lessons WHERE student_id = ? AND is_paid = 1", (student_id,)) as cursor:
            paid = (await cursor.fetchone())[0]
        return total, paid

# ==========================================
# 2. ФОНОВЫЕ ЗАДАЧИ
# ==========================================
async def check_reminders(bot: Bot):
    now = datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.id, l.lesson_time, l.reminded_24h, l.reminded_2h, s.name, s.subject, s.student_chat_id, s.parent_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.status != 'canceled'"
        async with db.execute(query) as cursor:
            lessons = await cursor.fetchall()
            
        for l_id, l_time_str, r24, r2, s_name, subject, s_chat, p_chat in lessons:
            try:
                lesson_time = datetime.strptime(l_time_str, "%d.%m.%Y %H:%M")
            except ValueError:
                continue 
                
            time_diff = lesson_time - now
            hours_left = time_diff.total_seconds() / 3600
            
            if 20 <= hours_left <= 24 and r24 == 0:
                text = f"🔔 Напоминаем: завтра в {lesson_time.strftime('%H:%M')} у вас занятие по предмету {subject}.\nВы придете?"
                builder = InlineKeyboardBuilder()
                builder.button(text="✅ Буду", callback_data=f"confirm_l_{l_id}")
                builder.button(text="❌ Не смогу", callback_data=f"cancel_l_{l_id}")
                builder.adjust(2)

                if s_chat: await bot.send_message(s_chat, text, reply_markup=builder.as_markup())
                if p_chat: await bot.send_message(p_chat, f"🔔 Напоминаем: завтра в {lesson_time.strftime('%H:%M')} у {s_name} занятие по предмету {subject}.")
                
                await db.execute("UPDATE lessons SET reminded_24h = 1, is_reminded = 1 WHERE id = ?", (l_id,))
                
            elif 0 < hours_left <= 2 and r2 == 0:
                if s_chat: await bot.send_message(s_chat, f"⏰ Напоминаем: через 2 часа ({lesson_time.strftime('%H:%M')}) у вас занятие по предмету {subject}!")
                if p_chat: await bot.send_message(p_chat, f"⏰ Напоминаем: через 2 часа ({lesson_time.strftime('%H:%M')}) у {s_name} занятие по предмету {subject}!")
                await db.execute("UPDATE lessons SET reminded_2h = 1 WHERE id = ?", (l_id,))
        await db.commit()

async def check_subscriptions(bot: Bot):
    now = datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, pro_until FROM users WHERE is_pro = 1") as cursor:
            users = await cursor.fetchall()
        for user_id, pro_until in users:
            if pro_until:
                expiry = datetime.strptime(pro_until, "%Y-%m-%d %H:%M:%S")
                if expiry < now:
                    await db.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (user_id,))
                    await db.commit()
                    try:
                        await bot.send_message(user_id, "⚠️ <b>Ваша подписка PRO истекла!</b>\n\nТеперь вам снова доступно только 3 бесплатных ученика. Чтобы продлить тариф, зайдите в «💎 Тарифы и Подписка».", parse_mode="HTML")
                    except Exception:
                        pass

# ==========================================
# 3. СЕКРЕТНАЯ КОМАНДА АДМИНА
# ==========================================
@router.message(Command("activate"))
async def activate_pro(message: Message):
    if message.from_user.id != ADMIN_ID:
        return 
    try:
        args = message.text.split()
        target_id = int(args[1])
        months = int(args[2]) if len(args) > 2 else 1
        days = months * 30
        expiry = await set_user_pro(target_id, days)
        await message.answer(f"✅ Пользователь {target_id} переведен на PRO на {months} мес. до {expiry}!")
        try:
            await message.bot.send_message(target_id, f"🎉 <b>Ваша оплата получена!</b>\nВам активирован тариф PRO на {months} мес.\nДата окончания: <b>{expiry.split(' ')[0]}</b>\n\nСпасибо, что выбрали Repetly!", parse_mode="HTML")
        except: pass
    except Exception:
        await message.answer(f"❌ Ошибка. Используй: /activate ID [Кол-во месяцев]")

# ==========================================
# 4. СОСТОЯНИЯ (FSM)
# ==========================================
class AddStudent(StatesGroup):
    waiting_for_name = State()
    waiting_for_subject = State()
    waiting_for_price = State()
    waiting_for_schedule = State()
    waiting_for_sub = State()

class AddLesson(StatesGroup):
    waiting_for_student = State()
    waiting_for_day = State()
    waiting_for_time = State()

class SettingsState(StatesGroup):
    waiting_for_details = State()

class MoveLesson(StatesGroup):
    waiting_for_lesson = State()
    waiting_for_day = State()
    waiting_for_time = State()

class VacationState(StatesGroup):
    waiting_for_dates = State()

class ReportState(StatesGroup):
    waiting_for_student = State()

# ==========================================
# 5. КЛАВИАТУРЫ
# ==========================================
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎓 Я репетитор", callback_data="role_tutor")
    builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
    builder.button(text="👩‍👦 Я родитель", callback_data="role_parent")
    builder.adjust(1)
    return builder.as_markup()

def get_tutor_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Мое расписание", callback_data="tutor_schedule")
    builder.button(text="👤 Мои ученики", callback_data="tutor_students")
    builder.button(text="💵 Учет оплат", callback_data="tutor_payments")
    builder.button(text="📊 Статистика", callback_data="tutor_stats")
    builder.button(text="📝 Отчет родителю", callback_data="tutor_report")
    builder.button(text="🌴 Отпуск / Болезнь", callback_data="tutor_vacation")
    builder.button(text="💎 Тарифы и Подписка", callback_data="tutor_tariffs")
    builder.button(text="🎁 Пригласить коллегу", callback_data="tutor_share")
    builder.button(text="⚙️ Настройки", callback_data="tutor_settings")
    builder.button(text="🔙 Сменить роль", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_students_menu(students):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ученика", callback_data="add_student")
    for s_id, name, subject, price, schedule, sub_left, sub_total, karma in students:
        builder.button(text=f"❌ Удалить {name} ({subject})", callback_data=f"del_student_{s_id}")
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_subject_menu():
    builder = InlineKeyboardBuilder()
    subjects = ["Математика", "Физика", "Русский язык", "Английский язык", "Химия", "Информатика", "Биология", "История"]
    for i, subj in enumerate(subjects):
        builder.button(text=subj, callback_data=f"subj_{i}")
    builder.button(text="🌐 Другой предмет", callback_data="subj_other")
    builder.button(text="🏠 Отмена (в меню)", callback_data="tutor_menu_back")
    builder.adjust(2)
    return builder.as_markup()

def get_subscription_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Разово (без абонемента)", callback_data="sub_1")
    builder.button(text="🎟 Абонемент на 4 занятия", callback_data="sub_4")
    builder.button(text="🎟 Абонемент на 8 занятий", callback_data="sub_8")
    builder.button(text="🏠 Отмена (в меню)", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_delete_menu(student_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_del_{student_id}")
    builder.button(text="🔙 Отмена", callback_data="tutor_students")
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_schedule_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Назначить занятие", callback_data="add_lesson")
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_payments_menu(unpaid_lessons):
    builder = InlineKeyboardBuilder()
    if unpaid_lessons:
        for l_id, l_time, s_name, price, parent_chat in unpaid_lessons:
            builder.button(text=f"💵 {s_name} ({price} руб.) - {l_time}", callback_data=f"pay_{l_id}")
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_student_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Мое расписание", callback_data="student_schedule")
    builder.button(text="🔄 Перенести урок", callback_data="student_move")
    builder.button(text="ℹ️ Мои данные", callback_data="student_info")
    builder.button(text="🏠 В главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_parent_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Расписание ребенка", callback_data="parent_schedule")
    builder.button(text="📊 Журнал и оплаты", callback_data="parent_journal")
    builder.button(text="🏠 В главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_cancel_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Отмена (в меню)", callback_data="tutor_menu_back")
    return builder.as_markup()

def get_skip_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="skip_schedule")
    builder.button(text="🏠 Отмена (в меню)", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_days_menu():
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        if i == 0: day_name = "Сегодня"
        elif i == 1: day_name = "Завтра"
        else: day_name = days_ru[date.weekday()]
        btn_text = f"{day_name} ({date.strftime('%d.%m')})"
        builder.button(text=btn_text, callback_data=f"day_{date_str}")
    builder.button(text="🏠 Отмена", callback_data="back_to_main")
    builder.adjust(2)
    return builder.as_markup()

def get_time_menu(selected_date):
    builder = InlineKeyboardBuilder()
    times = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"]
    for t in times:
        builder.button(text=t, callback_data=f"time_{selected_date}_{t}")
    builder.button(text="🏠 Отмена", callback_data="back_to_main")
    builder.adjust(3)
    return builder.as_markup()

# ==========================================
# 6. ОБРАБОТЧИКИ СТАРТА
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    if command.args and command.args.startswith("bind_"):
        parts = command.args.split("_")
        student_id = int(parts[1])
        role = parts[2]
        await bind_user(student_id, user_id, role)
        if role == "student":
            await message.answer("✅ Успешно! Вы привязаны к репетитору.", reply_markup=get_student_menu())
        else:
            await message.answer("✅ Успешно! Вы привязаны как родитель.", reply_markup=get_parent_menu())
        return

    role = await get_user_role(user_id)
    if role == "tutor":
        await message.answer("С возвращением! Меню репетитора:", reply_markup=get_tutor_menu())
    elif role == "student":
        await message.answer("С возвращением! Меню ученика:", reply_markup=get_student_menu())
    elif role == "parent":
        await message.answer("С возвращением! Меню родителя:", reply_markup=get_parent_menu())
    else:
        await message.answer("👋 Здравствуйте! Выберите вашу роль:", reply_markup=get_main_menu())

@router.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    if role in ["student", "parent"]:
        await safe_edit_text(callback.message, "⚠️ Чтобы стать учеником или родителем, перейдите по ссылке от репетитора.", reply_markup=get_main_menu())
    else:
        await set_user_role(callback.from_user.id, role)
        text = (
            "🎓 <b>Добро пожаловать в Repetly!</b>\n\n"
            "1️⃣ Зайдите в <b>«⚙️ Настройки»</b> и укажите реквизиты.\n"
            "2️⃣ Добавьте первого ученика в <b>«👤 Мои ученики»</b> (до 3-х бесплатно).\n"
            "3️⃣ Назначьте занятие в <b>«📅 Мое расписание»</b>.\n\n"
            "⚠️ <i>Все уроки по вашему местному времени.</i>"
        )
        await safe_edit_text(callback.message, text, reply_markup=get_tutor_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def process_back_button(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    role = await get_user_role(callback.from_user.id)
    if role == "tutor": await safe_edit_text(callback.message, "Главное меню:", reply_markup=get_tutor_menu())
    elif role == "parent": await safe_edit_text(callback.message, "Главное меню:", reply_markup=get_parent_menu())
    else: await safe_edit_text(callback.message, "Главное меню:", reply_markup=get_student_menu())
    await callback.answer()

@router.callback_query(F.data == "tutor_menu_back")
async def process_tutor_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(callback.message, "Главное меню репетитора:", reply_markup=get_tutor_menu())
    await callback.answer()

# ==========================================
# 7. ТАРИФЫ И УВЕДОМЛЕНИЕ АДМИНА
# ==========================================
@router.callback_query(F.data == "tutor_tariffs")
async def show_tariffs(callback: CallbackQuery, bot: Bot):
    text = (
        "💎 <b>Тарифная сетка Repetly</b>\n\n"
        "👤 <b>Бесплатно:</b> до 3 активных учеников.\n"
        "🚀 <b>PRO:</b> безлимит учеников + все функции.\n\n"
        "📅 <b>1 месяц:</b>\n"
        "🇷🇺 490 ₽ | 🇧🇾 15 BYN | 🇰🇿 2500 ₸\n\n"
        "📦 <b>6 месяцев (-15%):</b>\n"
        "🇷🇺 2200 ₽ | 🇧🇾 76.5 BYN | 🇰🇿 11250 ₸\n\n"
        "🎓 <b>9 месяцев (-25%):</b>\n"
        "🇷🇺 3300 ₽ | 🇧🇾 101 BYN | 🇰🇿 16850 ₸\n\n"
        f"Для оплаты напишите нам: {ADMIN_USERNAME}"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Написать для оплаты", url=ADMIN_TG_LINK)
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    
    client_id = callback.from_user.id
    client_name = html.escape(callback.from_user.full_name)
    client_username = f"@{callback.from_user.username}" if callback.from_user.username else "нет"
    
    try:
        await bot.send_message(ADMIN_ID, f"🔔 <b>Клиент хочет купить Premium!</b>\n\n👤 Имя: {client_name}\n🔗 Юзернейм: {client_username}\n🆔 ID: <code>{client_id}</code>\n\nЧтобы активировать на 1 месяц, отправь:\n<code>/activate {client_id} 1</code>", parse_mode="HTML")
    except Exception: pass

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# 8. ДОБАВЛЕНИЕ УЧЕНИКА
# ==========================================
@router.callback_query(F.data == "tutor_students")
async def show_students(callback: CallbackQuery):
    students = await get_students_by_tutor(callback.from_user.id)
    text = "У вас пока нет учеников." if not students else "👤 Ваши ученики:\n\n"
    if students:
        for s_id, name, subject, price, schedule, sub_left, sub_total, karma in students:
            sched_text = f" ({schedule})" if schedule else ""
            sub_text = f" | Абонемент: {sub_left}/{sub_total}" if sub_total > 1 else ""
            text += f"• {name} — {subject} — {price} руб.{sched_text}{sub_text} | Карма: {karma}%\n"
        text += "\nНажмите на крестик, чтобы удалить."
    await safe_edit_text(callback.message, text, reply_markup=get_students_menu(students))
    await callback.answer()

@router.callback_query(F.data == "add_student")
async def start_add_student(callback: CallbackQuery, state: FSMContext):
    students = await get_students_by_tutor(callback.from_user.id)
    is_pro = await get_user_pro(callback.from_user.id)
    if len(students) >= 3 and not is_pro:
        text = (
            "⚠️ <b>Вы достигли лимита бесплатного тарифа (3 ученика).</b>\n\n"
            "Перейдите на тариф <b>PRO</b>, чтобы добавлять учеников без ограничений.\n\n"
            f"Для активации напишите админу: {ADMIN_USERNAME}"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="💬 Написать для оплаты", url=ADMIN_TG_LINK)
        builder.button(text="💎 Посмотреть тарифы", callback_data="tutor_tariffs")
        builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
        builder.adjust(1)
        await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return
    await safe_edit_text(callback.message, "Шаг 1 из 5. Введите имя нового ученика:", reply_markup=get_cancel_menu())
    await state.set_state(AddStudent.waiting_for_name)
    await callback.answer()

@router.message(AddStudent.waiting_for_name)
async def process_student_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(f"Отлично, {message.text}!\nШаг 2 из 5. Выберите предмет из списка:", reply_markup=get_subject_menu())
    await state.set_state(AddStudent.waiting_for_subject)

@router.callback_query(AddStudent.waiting_for_subject, F.data.startswith("subj_"))
async def process_student_subject(callback: CallbackQuery, state: FSMContext):
    subj_code = callback.data.split("_")[1]
    if subj_code == "other":
        await safe_edit_text(callback.message, "Введите название предмета текстом:")
        return
    subjects = ["Математика", "Физика", "Русский язык", "Английский язык", "Химия", "Информатика", "Биология", "История"]
    subject = subjects[int(subj_code)]
    await state.update_data(subject=subject)
    await safe_edit_text(callback.message, f"Выбран предмет: {subject}.\nШаг 3 из 5. Введите стоимость занятия (в рублях):")
    await state.set_state(AddStudent.waiting_for_price)
    await callback.answer()

@router.message(AddStudent.waiting_for_subject)
async def process_custom_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await message.answer(f"Выбран предмет: {message.text}.\nШаг 3 из 5. Введите стоимость занятия (в рублях):")
    await state.set_state(AddStudent.waiting_for_price)

@router.message(AddStudent.waiting_for_price)
async def process_student_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(price=price)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите только число. Например: 60")
        return
    await message.answer("Шаг 4 из 5. Напишите расписание текстом. Или нажмите Пропустить.", reply_markup=get_skip_menu())
    await state.set_state(AddStudent.waiting_for_schedule)

@router.message(AddStudent.waiting_for_schedule)
async def process_student_schedule(message: Message, state: FSMContext):
    await state.update_data(schedule=message.text)
    await message.answer("Шаг 5 из 5. Выберите формат оплаты:", reply_markup=get_subscription_menu())
    await state.set_state(AddStudent.waiting_for_sub)

@router.callback_query(AddStudent.waiting_for_schedule, F.data == "skip_schedule")
async def process_skip_schedule(callback: CallbackQuery, state: FSMContext):
    await state.update_data(schedule="")
    await safe_edit_text(callback.message, "Шаг 5 из 5. Выберите формат оплаты:", reply_markup=get_subscription_menu())
    await state.set_state(AddStudent.waiting_for_sub)
    await callback.answer()

@router.callback_query(AddStudent.waiting_for_sub, F.data.startswith("sub_"))
async def process_student_sub(callback: CallbackQuery, state: FSMContext):
    sub_total = int(callback.data.split("_")[1])
    data = await state.get_data()
    await finish_add_student(callback.from_user.id, data['name'], data['subject'], data['price'], data['schedule'], sub_total, callback.message)
    await state.clear()
    await callback.answer()

async def finish_add_student(tutor_id, name, subject, price, schedule, sub_total, message_obj):
    student_id = await add_student(tutor_id, name, subject, price, schedule, sub_total)
    link_student = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_student"
    link_parent = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_parent"
    text = f"✅ Ученик {html.escape(name)} добавлен!\n📚 Предмет: {html.escape(subject)}\n💰 Цена: {price} руб.\n\nСсылка для ученика:\n{link_student}\n\nСсылка для родителя:\n{link_parent}"
    await message_obj.answer(text, reply_markup=get_tutor_menu())

@router.callback_query(F.data.startswith("del_student_"))
async def ask_delete_student(callback: CallbackQuery):
    student_id = int(callback.data.split("_")[2])
    await safe_edit_text(callback.message, "⚠️ Удалить ученика?", reply_markup=get_confirm_delete_menu(student_id))
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_del_"))
async def process_delete_student(callback: CallbackQuery):
    await delete_student_from_db(int(callback.data.split("_")[2]))
    await callback.answer("Ученик удален!", show_alert=True)
    await show_students(callback)

# ==========================================
# 9. РАСПИСАНИЕ, ОПЛАТЫ И СТАТИСТИКА
# ==========================================
@router.callback_query(F.data == "tutor_report")
async def start_report(callback: CallbackQuery, state: FSMContext):
    students = await get_students_by_tutor(callback.from_user.id)
    if not students:
        await callback.answer("Сначала добавьте ученика!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for s_id, name, subject, price, schedule, sub_l, sub_t, karma in students: 
        builder.button(text=f"{name} ({subject})", callback_data=f"rep_student_{s_id}")
    builder.button(text="🏠 Отмена", callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, "Кому отправить отчет об успехах?", reply_markup=builder.as_markup())
    await state.set_state(ReportState.waiting_for_student)
    await callback.answer()

@router.callback_query(ReportState.waiting_for_student, F.data.startswith("rep_student_"))
async def process_report_student(callback: CallbackQuery, state: FSMContext, bot: Bot):
    student_id = int(callback.data.split("_")[2])
    student = await get_student_info(student_id)
    if not student:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    s_id, s_name, tutor_id, subject, price, sub_left, sub_total, karma, parent_chat = student
    total, paid = await get_parent_journal(s_id)
    text = (
        f"📝 <b>Ежемесячный отчет об успехах!</b>\n\n"
        f"👤 Ученик: {s_name}\n📚 Предмет: {subject}\n\n"
        f"📅 Проведено уроков: {total}\n✅ Оплачено уроков: {paid}\n📈 Индекс дисциплины: {karma}%\n"
    )
    if sub_total > 1: text += f"🎟 Остаток абонемента: {sub_left} из {sub_total}\n"
    text += f"\n<i>Отчет сгенерирован в Repetly.</i>"
    
    if parent_chat:
        try:
            await bot.send_message(parent_chat, text, parse_mode="HTML")
            await safe_edit_text(callback.message, "✅ Отчет отправлен родителю!", reply_markup=get_tutor_menu())
        except Exception:
            await safe_edit_text(callback.message, "❌ Ошибка! Родитель не привязал аккаунт.", reply_markup=get_tutor_menu())
    else:
        await safe_edit_text(callback.message, "❌ Ошибка! Родитель не привязан.", reply_markup=get_tutor_menu())
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "tutor_schedule")
async def show_tutor_schedule(callback: CallbackQuery):
    lessons = await get_lessons_for_tutor(callback.from_user.id)
    text = "📅 Ваше расписание:\n\n" if lessons else "📅 У вас пока нет назначенных занятий."
    if lessons:
        for l_id, time, s_name, subject, status in lessons:
            status_icon = "✅" if status == "confirmed" else ("❌" if status == "canceled" else "⏳")
            text += f"{status_icon} {time} — {s_name} ({subject})\n"
    await safe_edit_text(callback.message, text, reply_markup=get_schedule_menu())
    await callback.answer()

@router.callback_query(F.data == "add_lesson")
async def start_add_lesson(callback: CallbackQuery, state: FSMContext):
    students = await get_students_by_tutor(callback.from_user.id)
    if not students:
        await callback.answer("Сначала добавьте ученика!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for s_id, name, subject, price, schedule, sub_l, sub_t, karma in students: 
        builder.button(text=f"{name} ({subject})", callback_data=f"lesson_student_{s_id}")
    builder.button(text="🏠 Отмена", callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, "Выберите ученика:", reply_markup=builder.as_markup())
    await state.set_state(AddLesson.waiting_for_student)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_student, F.data.startswith("lesson_student_"))
async def process_lesson_student(callback: CallbackQuery, state: FSMContext):
    await state.update_data(student_id=int(callback.data.split("_")[2]))
    await safe_edit_text(callback.message, "Выберите день (на неделю вперед):", reply_markup=get_days_menu())
    await state.set_state(AddLesson.waiting_for_day)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_day, F.data.startswith("day_"))
async def process_lesson_day(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split("_")[1]
    await state.update_data(selected_date=selected_date)
    await safe_edit_text(callback.message, f"Выбран день: {selected_date}.\nВыберите время:", reply_markup=get_time_menu(selected_date))
    await state.set_state(AddLesson.waiting_for_time)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_time, F.data.startswith("time_"))
async def process_lesson_time(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    selected_date = parts[1]
    selected_time = parts[2]
    data = await state.get_data()
    await add_lesson(callback.from_user.id, data.get("student_id"), f"{selected_date} {selected_time}")
    await state.clear()
    await safe_edit_text(callback.message, f"✅ Занятие на {selected_date} {selected_time} добавлено!", reply_markup=get_tutor_menu())
    await callback.answer()

@router.callback_query(F.data == "tutor_payments")
async def show_payments(callback: CallbackQuery):
    unpaid = await get_unpaid_lessons(callback.from_user.id)
    text = "💵 Учет оплат\n\nУра! Все занятия оплачены." if not unpaid else "💵 Учет оплат\n\nНажмите, чтобы отметить оплату:"
    await safe_edit_text(callback.message, text, reply_markup=get_payments_menu(unpaid))
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, bot: Bot):
    lesson_id = int(callback.data.split("_")[1])
    unpaid = await get_unpaid_lessons(callback.from_user.id)
    parent_chat, s_name, price, student_id = None, "", 0, None
    for l_id, l_time, name, p, p_chat in unpaid:
        if l_id == lesson_id:
            parent_chat, s_name, price = p_chat, name, p
            break

    await mark_lesson_paid(lesson_id)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT student_id FROM lessons WHERE id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row: student_id = row[0]
                
    if student_id:
        await deduct_subscription(student_id)
        student = await get_student_info(student_id)
        if student and student[6] > 1: 
            sub_left = student[5]
            if sub_left == 0 and parent_chat:
                try: await bot.send_message(parent_chat, f"🎟 Внимание! У ученика {s_name} закончился абонемент (0 из {student[6]} занятий).")
                except Exception: pass

    await callback.answer("✅ Оплата зафиксирована!", show_alert=True)
    
    if parent_chat:
        try: await bot.send_message(parent_chat, f"💵 Репетитор подтвердил получение {price} руб. за занятие {s_name}.")
        except Exception: pass

    unpaid = await get_unpaid_lessons(callback.from_user.id)
    text = "💵 Учет оплат\n\nУра! Все занятия оплачены." if not unpaid else "💵 Учет оплат\n\nНажмите, чтобы отметить оплату:"
    await safe_edit_text(callback.message, text, reply_markup=get_payments_menu(unpaid))

@router.callback_query(F.data == "tutor_stats")
async def show_stats(callback: CallbackQuery):
    total_money, total_lessons = await get_monthly_earnings(callback.from_user.id)
    reminders_count = await get_reminders_count(callback.from_user.id)
    current_month = datetime.now().strftime("%m.%Y")
    saved_hours = round(reminders_count * 5 / 60, 1)
    text = f"📊 <b>Статистика ({current_month})</b>\n\n💰 Заработано: <b>{total_money} руб.</b>\n✅ Оплачено уроков: <b>{total_lessons}</b>\n🔔 Отправлено напоминаний: <b>{reminders_count}</b>\n⏳ Сэкономлено времени: <b>~{saved_hours} ч.</b>\n"
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 В главное меню", callback_data="tutor_menu_back")
    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# 10. ОТПУСК, НАСТРОЙКИ И ВИРАЛЬНОСТЬ
# ==========================================
@router.callback_query(F.data == "tutor_vacation")
async def start_vacation(callback: CallbackQuery, state: FSMContext):
    await safe_edit_text(callback.message, "Введите период в формате:\nДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n\nНапример: 05.11.2026 - 12.11.2026", reply_markup=get_cancel_menu())
    await state.set_state(VacationState.waiting_for_dates)
    await callback.answer()

@router.message(VacationState.waiting_for_dates)
async def process_vacation_dates(message: Message, state: FSMContext, bot: Bot):
    try:
        parts = message.text.split(" - ")
        start_date = datetime.strptime(parts[0].strip(), "%d.%m.%Y")
        end_date = datetime.strptime(parts[1].strip(), "%d.%m.%Y").replace(hour=23, minute=59)
    except Exception:
        await message.answer("❌ Ошибка формата. Введите точно так: 05.11.2026 - 12.11.2026")
        return
    await state.clear()
    await message.answer("⏳ Отменяю уроки и рассылаю уведомления...")
    canceled_count = await cancel_lessons_in_period(message.from_user.id, start_date, end_date)
    students = await get_all_students_for_tutor(message.from_user.id)
    text = f"⚠️ Внимание! Занятия с {parts[0].strip()} по {parts[1].strip()} отменяются."
    for s_chat, p_chat in students:
        if s_chat: 
            try: 
                await bot.send_message(s_chat, text)
                await asyncio.sleep(0.05)
            except: pass
        if p_chat: 
            try: 
                await bot.send_message(p_chat, text)
                await asyncio.sleep(0.05)
            except: pass
    await message.answer(f"✅ Готово! Отменено уроков: {canceled_count}.", reply_markup=get_tutor_menu())

@router.callback_query(F.data == "tutor_share")
async def share_bot(callback: CallbackQuery):
    share_link = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}&text=Привет! Пользуюсь ботом Repetly для расписания и оплат. Советую!"
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Поделиться", url=share_link)
    builder.button(text="🏠 В меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, "🎁 Пригласите коллегу!\nОтправьте ссылку другу.", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "tutor_settings")
async def show_settings(callback: CallbackQuery):
    details = await get_payment_details(callback.from_user.id)
    user_id = callback.from_user.id
    is_pro = await get_user_pro(user_id)
    pro_status = ""
    if is_pro:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT pro_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    pro_status = f"\n💎 <b>Тариф PRO</b> (до {row[0].split(' ')[0]})\n"
    text = f"⚙️ <b>Настройки профиля</b>\n{pro_status}\n🆔 Ваш ID: <code>{user_id}</code>\n<i>(Сообщите его админу)</i>\n\n💳 Реквизиты:\n{details}"
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить реквизиты", callback_data="edit_details")
    builder.button(text="🏠 В меню", callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "edit_details")
async def edit_settings(callback: CallbackQuery, state: FSMContext):
    await safe_edit_text(callback.message, "Введите реквизиты:", reply_markup=get_cancel_menu())
    await state.set_state(SettingsState.waiting_for_details)
    await callback.answer()

@router.message(SettingsState.waiting_for_details)
async def save_settings(message: Message, state: FSMContext):
    await update_payment_details(message.from_user.id, message.text)
    await state.clear()
    await message.answer("✅ Обновлено!", reply_markup=get_tutor_menu())

# ==========================================
# 11. УВЕДОМЛЕНИЯ ОБ ОТМЕНЕ (УЧЕНИК)
# ==========================================
@router.callback_query(F.data.startswith("confirm_l_"))
async def confirm_lesson(callback: CallbackQuery, bot: Bot):
    lesson_id = int(callback.data.split("_")[2])
    await update_lesson_status(lesson_id, "confirmed")
    await safe_edit_text(callback.message, callback.message.text + "\n\n✅ Вы подтвердили участие.")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT tutor_id, s.name, l.lesson_time FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                try: await bot.send_message(row[0], f"🟢 Ученик {row[1]} ПОДТВЕРДИЛ урок на {row[2]}!")
                except Exception: pass
    await callback.answer("Отлично!")

@router.callback_query(F.data.startswith("cancel_l_"))
async def cancel_lesson(callback: CallbackQuery, bot: Bot):
    lesson_id = int(callback.data.split("_")[2])
    await update_lesson_status(lesson_id, "canceled")
    await safe_edit_text(callback.message, callback.message.text + "\n\n❌ Вы отменили занятие.")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT tutor_id, s.name, l.lesson_time, s.id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                tutor_id, s_name, l_time, s_id = row
                await lower_karma(s_id)
                try:
                    lesson_dt = datetime.strptime(l_time, "%d.%m.%Y %H:%M")
                    is_late = (lesson_dt - datetime.now()).total_seconds() < 86400
                except: is_late = False
                alert_icon = "🚨" if is_late else "🔴"
                extra_text = " (ПОЗДНЯЯ ОТМЕНА!)" if is_late else ""
                try: await bot.send_message(tutor_id, f"{alert_icon} Ученик {s_name} ОТМЕНИЛ урок на {l_time}!{extra_text}")
                except Exception: pass
    await callback.answer("Жаль. Мы сообщили.")

# ==========================================
# 12. МЕНЮ УЧЕНИКА И РОДИТЕЛЯ
# ==========================================
@router.callback_query(F.data.in_({"student_schedule", "parent_schedule"}))
async def show_any_schedule(callback: CallbackQuery):
    role = "parent" if callback.data == "parent_schedule" else "student"
    student = await get_student_by_chat_id(callback.from_user.id, role)
    if not student:
        await callback.answer("Ошибка привязки.", show_alert=True)
        return
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    lessons = await get_lessons_for_student(s_id)
    title = f"📅 Информация для {s_name}:" if role == "parent" else "📅 Ваша информация:"
    text = f"{title}\n📚 Предмет: {subject}\n"
    if sub_total > 1: text += f"🎟 Абонемент: {sub_left} из {sub_total}\n"
    text += f"⏰ Расписание: {text_schedule or 'не указано'}\n📈 Индекс дисциплины: {karma}%\n\n"
    now = datetime.now()
    next_lesson_diff = None
    if lessons:
        text += "🗓 Ближайшие занятия:\n"
        for l_id, time_str, subj in lessons: 
            text += f"🕒 {time_str}\n"
            if not next_lesson_diff:
                try:
                    l_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
                    if l_time > now: next_lesson_diff = l_time - now
                except: pass
    else: text += "Точных дат пока нет."
    if next_lesson_diff:
        days = next_lesson_diff.days
        hours = next_lesson_diff.seconds // 3600
        text += f"\n⏳ До следующего урока: {days} д. {hours} ч."
    reply_menu = get_parent_menu() if role == "parent" else get_student_menu()
    await safe_edit_text(callback.message, text, reply_markup=reply_menu)
    await callback.answer()

@router.callback_query(F.data == "student_move")
async def start_move_lesson(callback: CallbackQuery, state: FSMContext):
    student = await get_student_by_chat_id(callback.from_user.id, "student")
    if not student: return
    lessons = await get_lessons_for_student(student[0])
    if not lessons:
        await callback.answer("У вас нет уроков.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for l_id, time_str, subj in lessons:
        builder.button(text=time_str, callback_data=f"move_l_{l_id}")
    builder.button(text="🔙 Отмена", callback_data="back_to_main")
    builder.adjust(1)
    await safe_edit_text(callback.message, "Какой урок вы хотите перенести?", reply_markup=builder.as_markup())
    await state.set_state(MoveLesson.waiting_for_lesson)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_lesson, F.data.startswith("move_l_"))
async def process_move_lesson(callback: CallbackQuery, state: FSMContext):
    await state.update_data(lesson_id=int(callback.data.split("_")[2]))
    await safe_edit_text(callback.message, "На какой день?", reply_markup=get_days_menu())
    await state.set_state(MoveLesson.waiting_for_day)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_day, F.data.startswith("day_"))
async def process_move_day(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split("_")[1]
    await state.update_data(selected_date=selected_date)
    await safe_edit_text(callback.message, f"На какое время?", reply_markup=get_time_menu(selected_date))
    await state.set_state(MoveLesson.waiting_for_time)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_time, F.data.startswith("time_"))
async def process_move_time(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    new_date, new_time = parts[1], parts[2]
    new_full_time = f"{new_date} {new_time}"
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT l.tutor_id, s.name, l.lesson_time FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
    await state.clear()
    if row:
        tutor_id, s_name, old_time = row
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Разрешить", callback_data=f"appr_mv_{lesson_id}_{new_date}_{new_time}")
        builder.button(text="❌ Отказать", callback_data=f"rej_mv_{lesson_id}")
        builder.adjust(2)
        try:
            await bot.send_message(tutor_id, f"🔄 Запрос на перенос!\n\nУченик {s_name} просит перенести урок с {old_time} на {new_full_time}.", reply_markup=builder.as_markup())
            await safe_edit_text(callback.message, "✅ Запрос отправлен!", reply_markup=get_student_menu())
        except Exception: pass
    await callback.answer()

@router.callback_query(F.data.startswith("appr_mv_"))
async def approve_move(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    lesson_id = int(parts[2])
    new_full_time = f"{parts[3]} {parts[4]}"
    await change_lesson_time(lesson_id, new_full_time)
    await safe_edit_text(callback.message, callback.message.text + "\n\n✅ Вы РАЗРЕШИЛИ перенос.")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT s.student_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try: await bot.send_message(row[0], f"🎉 Репетитор разрешил перенос! Ждем вас {new_full_time}.")
                except: pass
    await callback.answer("Подтверждено!")

@router.callback_query(F.data.startswith("rej_mv_"))
async def reject_move(callback: CallbackQuery, bot: Bot):
    lesson_id = int(callback.data.split("_")[2])
    await safe_edit_text(callback.message, callback.message.text + "\n\n❌ Вы ОТКАЗАЛИ в переносе.")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT s.student_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try: await bot.send_message(row[0], "😔 К сожалению, репетитор не может перенести этот урок.")
                except: pass
    await callback.answer("Отказано.")

@router.callback_query(F.data == "student_info")
async def show_student_info(callback: CallbackQuery):
    student = await get_student_by_chat_id(callback.from_user.id, "student")
    if not student: return
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    text = f"ℹ️ Профиль:\n\n👤 Имя: {s_name}\n📚 Предмет: {subject}\n⏰ Расписание: {text_schedule or 'не указано'}"
    if sub_total > 1: text += f"\n🎟 Абонемент: {sub_left} из {sub_total}"
    text += f"\n📈 Карма: {karma}%"
    await safe_edit_text(callback.message, text, reply_markup=get_student_menu())
    await callback.answer()

@router.callback_query(F.data == "parent_journal")
async def show_parent_journal(callback: CallbackQuery):
    student = await get_student_by_chat_id(callback.from_user.id, "parent")
    if not student: return
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    total, paid = await get_parent_journal(s_id)
    debt = total - paid
    details = await get_payment_details(tutor_id)
    sub_text = ""
    if sub_total > 1:
        green = "🟢" * sub_left
        red = "🔴" * (sub_total - sub_left)
        sub_text = f"\n🎟 Абонемент: {sub_left} из {sub_total}\n{green}{red}\n"
    text = f"📊 Журнал ({s_name}):\n\n📅 Проведено: {total} | Оплачено: {paid}\n❌ Долг: {debt}\n📈 Карма: {karma}%\n{sub_text}\n💳 Реквизиты:\n{details}"
    await safe_edit_text(callback.message, text, reply_markup=get_parent_menu())
    await callback.answer()

# ==========================================
# 13. ВЕБ-СЕРВЕР И ЗАПУСК
# ==========================================
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

async def main():
    threading.Thread(target=run_web).start() 
    if not BOT_TOKEN:
        print("ОШИБКА: Токен не найден!")
        return
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders, 'interval', minutes=1, args=(bot,))
    scheduler.add_job(check_subscriptions, 'interval', hours=1, args=(bot,))
    scheduler.start()
    
    print("Бот запущен! Тестируем...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())