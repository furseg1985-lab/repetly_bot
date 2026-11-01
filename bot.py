import asyncio
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import aiosqlite

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "RepetlyAssistantBot" 

logging.basicConfig(level=logging.INFO)
router = Router()

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
DB_NAME = "repetly.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, name TEXT, 
                student_chat_id INTEGER, parent_chat_id INTEGER
            )
        """)
        # Добавили is_paid (0 - не оплачено, 1 - оплачено)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, 
                student_id INTEGER, lesson_time TEXT, 
                reminded_24h INTEGER DEFAULT 0, reminded_2h INTEGER DEFAULT 0,
                is_paid INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def set_user_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO users (user_id, role) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET role = excluded.role", (user_id, role))
        await db.commit()

async def get_user_role(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def add_student(tutor_id: int, name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO students (tutor_id, name) VALUES (?, ?)", (tutor_id, name))
        await db.commit()
        return cursor.lastrowid 

async def delete_student_from_db(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM lessons WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        await db.commit()

async def get_students_by_tutor(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name FROM students WHERE tutor_id = ?", (tutor_id,)) as cursor:
            return await cursor.fetchall()

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
        query = "SELECT id, name, tutor_id FROM students WHERE parent_chat_id = ?" if role == "parent" else "SELECT id, name, tutor_id FROM students WHERE student_chat_id = ?"
        async with db.execute(query, (chat_id,)) as cursor:
            return await cursor.fetchone()

async def add_lesson(tutor_id: int, student_id: int, lesson_time: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO lessons (tutor_id, student_id, lesson_time) VALUES (?, ?, ?)", (tutor_id, student_id, lesson_time))
        await db.commit()

async def get_lessons_for_tutor(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.lesson_time, s.name FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.tutor_id = ? ORDER BY l.lesson_time ASC"
        async with db.execute(query, (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def get_lessons_for_student(student_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.lesson_time FROM lessons l WHERE l.student_id = ? ORDER BY l.lesson_time ASC"
        async with db.execute(query, (student_id,)) as cursor:
            return await cursor.fetchall()

# --- ФУНКЦИИ ДЛЯ ОПЛАТ ---
async def get_unpaid_lessons(tutor_id: int):
    """Берет все занятия, которые уже прошли (или проходят сегодня), но не оплачены"""
    async with aiosqlite.connect(DB_NAME) as db:
        query = """
            SELECT l.id, l.lesson_time, s.name 
            FROM lessons l 
            JOIN students s ON l.student_id = s.id 
            WHERE l.tutor_id = ? AND l.is_paid = 0 
            ORDER BY l.lesson_time ASC
        """
        async with db.execute(query, (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def mark_lesson_paid(lesson_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE lessons SET is_paid = 1 WHERE id = ?", (lesson_id,))
        await db.commit()

# ==========================================
# ФОНОВАЯ ЗАДАЧА: НАПОМИНАНИЯ
# ==========================================
async def check_reminders(bot: Bot):
    now = datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        query = """
            SELECT l.id, l.lesson_time, l.reminded_24h, l.reminded_2h, s.name, s.student_chat_id, s.parent_chat_id
            FROM lessons l JOIN students s ON l.student_id = s.id
        """
        async with db.execute(query) as cursor:
            lessons = await cursor.fetchall()
            
        for l_id, l_time_str, r24, r2, s_name, s_chat, p_chat in lessons:
            try:
                lesson_time = datetime.strptime(l_time_str, "%d.%m.%Y %H:%M")
            except ValueError:
                continue 
                
            time_diff = lesson_time - now
            
            if 23 <= time_diff.total_seconds() / 3600 <= 25 and r24 == 0:
                text = f"🔔 Напоминаем: завтра в {lesson_time.strftime('%H:%M')} у вас занятие с репетитором ({s_name})."
                if s_chat: await bot.send_message(s_chat, text)
                if p_chat: await bot.send_message(p_chat, text)
                await db.execute("UPDATE lessons SET reminded_24h = 1 WHERE id = ?", (l_id,))
            elif 1 <= time_diff.total_seconds() / 3600 <= 3 and r2 == 0:
                text = f"⏰ Напоминаем: через 2 часа ({lesson_time.strftime('%H:%M')}) у вас занятие!"
                if s_chat: await bot.send_message(s_chat, text)
                if p_chat: await bot.send_message(p_chat, text)
                await db.execute("UPDATE lessons SET reminded_2h = 1 WHERE id = ?", (l_id,))
        await db.commit()

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
class AddStudent(StatesGroup):
    waiting_for_name = State()

class AddLesson(StatesGroup):
    waiting_for_student = State()
    waiting_for_time = State()

# ==========================================
# КЛАВИАТУРЫ
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
    builder.button(text="🔙 Сменить роль", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_students_menu(students):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ученика", callback_data="add_student")
    for s_id, name in students:
        builder.button(text=f"❌ Удалить {name}", callback_data=f"del_student_{s_id}")
    builder.button(text="🔙 Назад", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_delete_menu(student_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_del_{student_id}")
    builder.button(text="🔙 Отмена", callback_data="tutor_students")
    builder.adjust(1)
    return builder.as_markup()

def get_schedule_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Назначить занятие", callback_data="add_lesson")
    builder.button(text="🔙 Назад", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

# Клавиатура для долгов
def get_payments_menu(unpaid_lessons):
    builder = InlineKeyboardBuilder()
    if not unpaid_lessons:
        builder.button(text="🔙 Назад", callback_data="tutor_menu_back")
    else:
        for l_id, l_time, s_name in unpaid_lessons:
            builder.button(text=f"💵 Оплатить: {s_name} ({l_time})", callback_data=f"pay_{l_id}")
        builder.button(text="🔙 Назад", callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_student_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Мое расписание", callback_data="student_schedule")
    builder.button(text="🔙 Сменить роль", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_parent_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Расписание ребенка", callback_data="parent_schedule")
    builder.button(text="🔙 Сменить роль", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_cancel_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="tutor_menu_back")
    return builder.as_markup()

# ==========================================
# ОБРАБОТЧИКИ СТАРТА
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
        await callback.message.edit_text("⚠️ Чтобы стать учеником или родителем, перейдите по ссылке от репетитора.", reply_markup=get_main_menu())
    else:
        await set_user_role(callback.from_user.id, role)
        await callback.message.edit_text("🎓 Вы вошли как репетитор.", reply_markup=get_tutor_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def process_back_button(callback: CallbackQuery):
    await callback.message.edit_text("Выберите роль заново:", reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "tutor_menu_back")
async def process_tutor_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню репетитора:", reply_markup=get_tutor_menu())
    await callback.answer()

# ==========================================
# ЛОГИКА РЕПЕТИТОРА (УЧЕНИКИ)
# ==========================================
@router.callback_query(F.data == "tutor_students")
async def show_students(callback: CallbackQuery):
    students = await get_students_by_tutor(callback.from_user.id)
    text = "👤 **Ваши ученики:**\n\nНажмите на крестик рядом с именем, чтобы удалить ученика." if students else "У вас пока нет учеников."
    await callback.message.edit_text(text, reply_markup=get_students_menu(students), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "add_student")
async def start_add_student(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите имя нового ученика:", reply_markup=get_cancel_menu())
    await state.set_state(AddStudent.waiting_for_name)
    await callback.answer()

@router.message(AddStudent.waiting_for_name)
async def process_student_name(message: Message, state: FSMContext):
    student_id = await add_student(message.from_user.id, message.text)
    await state.clear() 
    link_student = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_student"
    link_parent = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_parent"
    text = f"✅ Ученик **{message.text}** добавлен!\n\nСсылка для **ученика**:\n`{link_student}`\n\nСсылка для **родителя**:\n`{link_parent}`"
    await message.answer(text, reply_markup=get_tutor_menu(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("del_student_"))
async def ask_delete_student(callback: CallbackQuery):
    student_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить этого ученика?\nВсе его занятия также будут удалены.",
        reply_markup=get_confirm_delete_menu(student_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_del_"))
async def process_delete_student(callback: CallbackQuery):
    await delete_student_from_db(int(callback.data.split("_")[2]))
    await callback.answer("Ученик успешно удален!", show_alert=True)
    students = await get_students_by_tutor(callback.from_user.id)
    text = "👤 **Ваши ученики:**\n\nНажмите на крестик, чтобы удалить." if students else "У вас пока нет учеников."
    await callback.message.edit_text(text, reply_markup=get_students_menu(students), parse_mode="Markdown")

# ==========================================
# ЛОГИКА РАСПИСАНИЯ
# ==========================================
@router.callback_query(F.data == "tutor_schedule")
async def show_tutor_schedule(callback: CallbackQuery):
    lessons = await get_lessons_for_tutor(callback.from_user.id)
    text = "📅 **Ваше расписание:**\n\n" if lessons else "📅 У вас пока нет назначенных занятий."
    if lessons:
        for time, s_name in lessons: text += f"🕒 {time} — {s_name}\n"
    await callback.message.edit_text(text, reply_markup=get_schedule_menu(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "add_lesson")
async def start_add_lesson(callback: CallbackQuery, state: FSMContext):
    students = await get_students_by_tutor(callback.from_user.id)
    if not students:
        await callback.answer("Сначала добавьте ученика!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for s_id, name in students: builder.button(text=name, callback_data=f"lesson_student_{s_id}")
    builder.button(text="❌ Отмена", callback_data="tutor_menu_back")
    builder.adjust(1)
    await callback.message.edit_text("Выберите ученика:", reply_markup=builder.as_markup())
    await state.set_state(AddLesson.waiting_for_student)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_student, F.data.startswith("lesson_student_"))
async def process_lesson_student(callback: CallbackQuery, state: FSMContext):
    await state.update_data(student_id=int(callback.data.split("_")[2]))
    await callback.message.edit_text(
        "Введите дату и время занятия строго в формате:\n`ДД.ММ.ГГГГ ЧЧ:ММ`\n\nНапример: `05.11.2026 15:30`",
        reply_markup=get_cancel_menu(), parse_mode="Markdown"
    )
    await state.set_state(AddLesson.waiting_for_time)
    await callback.answer()

@router.message(AddLesson.waiting_for_time)
async def process_lesson_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("❌ Ошибка формата! Пожалуйста, введите точно так: `05.11.2026 15:30`", parse_mode="Markdown")
        return

    data = await state.get_data()
    await add_lesson(message.from_user.id, data.get("student_id"), message.text)
    await state.clear()
    await message.answer(f"✅ Занятие на **{message.text}** добавлено! Бот сам пришлет напоминания.", reply_markup=get_tutor_menu(), parse_mode="Markdown")

# ==========================================
# ЛОГИКА ОПЛАТ (ДОЛГИ)
# ==========================================
@router.callback_query(F.data == "tutor_payments")
async def show_payments(callback: CallbackQuery):
    unpaid = await get_unpaid_lessons(callback.from_user.id)
    
    if not unpaid:
        text = "💵 **Учет оплат**\n\nУра! Все занятия оплачены. Долгов нет."
    else:
        text = "💵 **Учет оплат**\n\nНиже список занятий, которые ожидают оплаты. Нажмите на кнопку, чтобы отметить оплату (наличными или переводом):"
        
    await callback.message.edit_text(text, reply_markup=get_payments_menu(unpaid), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    lesson_id = int(callback.data.split("_")[1])
    await mark_lesson_paid(lesson_id)
    await callback.answer("✅ Оплата успешно зафиксирована!", show_alert=True)
    
    # Обновляем список долгов
    unpaid = await get_unpaid_lessons(callback.from_user.id)
    if not unpaid:
        text = "💵 **Учет оплат**\n\nУра! Все занятия оплачены. Долгов нет."
    else:
        text = "💵 **Учет оплат**\n\nНиже список занятий, которые ожидают оплаты:"
        
    await callback.message.edit_text(text, reply_markup=get_payments_menu(unpaid), parse_mode="Markdown")

# ==========================================
# МЕНЮ УЧЕНИКА И РОДИТЕЛЯ
# ==========================================
@router.callback_query(F.data.in_({"student_schedule", "parent_schedule"}))
async def show_any_schedule(callback: CallbackQuery):
    role = "parent" if callback.data == "parent_schedule" else "student"
    student = await get_student_by_chat_id(callback.from_user.id, role)
    
    if not student:
        await callback.answer("Ошибка привязки.", show_alert=True)
        return
        
    lessons = await get_lessons_for_student(student[0])
    name = student[1] if role == "parent" else "вас"
    
    text = f"📅 **Расписание для {name}:**\n\n" if lessons else "📅 Пока нет назначенных занятий."
    if lessons:
        for (time,) in lessons: text += f"🕒 {time}\n"
        
    reply_menu = get_parent_menu() if role == "parent" else get_student_menu()
    await callback.message.edit_text(text, reply_markup=reply_menu, parse_mode="Markdown")
    await callback.answer()

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    if not BOT_TOKEN:
        print("ОШИБКА: Токен не найден!")
        return

    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders, 'interval', minutes=1, args=(bot,))
    scheduler.start()
    
    print("Бот запущен! Тестируем учет оплат...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())