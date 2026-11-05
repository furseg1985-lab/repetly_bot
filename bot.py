import asyncio
import logging
import os
import threading
import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

ADMIN_USERNAME = "@furseg" 
ADMIN_TG_LINK = "https://t.me/furseg" 
ADMIN_ID = 5278271346

TZ = ZoneInfo("Europe/Minsk")
logging.basicConfig(level=logging.INFO)
router = Router()

# ==========================================
# ПОЛНЫЙ СЛОВАРЬ ПЕРЕВОДОВ
# ==========================================
TEXTS = {
    "ru": {
        "choose_lang": "Пожалуйста, выберите язык:",
        "lang_set": "🇷🇺 Язык установлен: Русский",
        "choose_role": "👋 Здравствуйте! Выберите вашу роль:",
        "role_tutor": "🎓 Я репетитор",
        "role_student": "👨‍🎓 Я ученик",
        "role_parent": "👩‍👦 Я родитель",
        "tutor_menu": "Меню репетитора:",
        "student_menu": "Меню ученика:",
        "parent_menu": "Меню родителя:",
        "btn_schedule": "📅 Мое расписание",
        "btn_students": "👤 Мои ученики",
        "btn_payments": "💵 Учет оплат",
        "btn_stats": "📊 Статистика",
        "btn_report": "📝 Отчет родителю",
        "btn_vacation": "🌴 Отпуск / Болезнь",
        "btn_tariffs": "💎 Тарифы и Подписка",
        "btn_share": "🎁 Пригласить коллегу",
        "btn_settings": "⚙️ Настройки",
        "btn_back": "🔙 Сменить роль",
        "btn_to_main": "🏠 В главное меню",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_edit_details": "✏️ Изменить реквизиты",
        "btn_my_schedule": "📅 Мое расписание",
        "btn_move_lesson": "🔄 Перенести урок",
        "btn_my_info": "ℹ️ Мои данные",
        "btn_child_schedule": "📅 Расписание ребенка",
        "btn_journal": "📊 Журнал и оплаты",
        "btn_cancel": "🏠 Отмена",
        "btn_skip": "⏭️ Пропустить",
        "btn_share": "📤 Поделиться",
        
        "payments_title": "💵 <b>Учет оплат</b>",
        "payments_all_paid": "Ура! Все занятия оплачены.",
        "payments_click": "Нажмите, чтобы отметить оплату:",
        
        "settings_title": "⚙️ <b>Настройки профиля</b>",
        "settings_id": "🆔 Ваш ID: <code>{id}</code>\n<i>(Сообщите его админу для оплаты)</i>",
        "settings_details": "💳 Реквизиты:\n{details}",
        "settings_ask_details": "Введите реквизиты:",
        "settings_updated": "✅ Реквизиты обновлены!",
        
        "schedule_title": "📅 <b>Ваше расписание:</b>\n\n",
        "schedule_empty": "📅 У вас пока нет назначенных занятий.",
        "schedule_choose_student": "Выберите ученика:",
        "schedule_choose_day": "Выберите день (на неделю вперед):",
        "schedule_selected_day": "Выбран день: {date}.\nВыберите время:",
        "schedule_added": "✅ Занятие на {date} {time} добавлено!",
        
        "stats_title": "📊 <b>Статистика ({month})</b>\n\n💰 Заработано: <b>{money} руб.</b>\n✅ Оплачено уроков: <b>{lessons}</b>\n🔔 Отправлено напоминаний: <b>{reminders}</b>\n⏳ Сэкономлено времени: <b>~{hours} ч.</b>\n",
        
        "tariffs_text": "💎 <b>Тарифная сетка Repetly</b>\n\n👤 <b>Бесплатно:</b> до 3 активных учеников.\n🚀 <b>PRO:</b> безлимит учеников + все функции.\n\n📅 <b>1 месяц:</b>\n🇷🇺 490 ₽ | 🇧🇾 15 BYN | 🇰🇿 2500 ₸ | 🇪🇺 4.55 EUR\n\n📦 <b>6 месяцев (-15%):</b>\n🇷🇺 2200 ₽ | 🇧🇾 76.5 BYN | 🇰🇿 11250 ₸ | 🇪🇺 22.75 EUR\n\n🎓 <b>9 месяцев (-25%):</b>\n🇷🇺 3300 ₽ | 🇧🇾 101 BYN | 🇰🇿 16850 ₸ | 🇪🇺 36.5 EUR\n\nДля оплаты напишите нам: {admin}",
        "btn_contact": "💬 Написать для оплаты",
        
        "students_empty": "У вас пока нет учеников.",
        "students_list": "👤 <b>Ваши ученики:</b>\n\n",
        "students_delete_hint": "\nНажмите на крестик, чтобы удалить.",
        "students_ask_delete": "⚠️ Удалить ученика?",
        "students_yes_delete": "✅ Да, удалить",
        "students_deleted": "Ученик удален!",
        
        "add_step1": "Шаг 1 из 5. Введите имя нового ученика:",
        "add_step2": "Отлично, {name}!\nШаг 2 из 5. Выберите предмет из списка:",
        "add_step2_text": "Введите название предмета текстом:",
        "add_step3": "Выбран предмет: {subject}.\nШаг 3 из 5. Введите стоимость занятия (в рублях):",
        "add_step4": "Шаг 4 из 5. Напишите расписание текстом (например: Вт 16:00). Или нажмите Пропустить.",
        "add_step5": "Шаг 5 из 5. Выберите формат оплаты:",
        "add_error_price": "❌ Пожалуйста, введите только число. Например: 60",
        "add_success": "✅ Ученик {name} добавлен!\n📚 Предмет: {subject}\n💰 Цена: {price} руб.\n\nСсылка для ученика:\n{link_student}\n\nСсылка для родителя:\n{link_parent}",
        "add_limit": "⚠️ <b>Вы достигли лимита бесплатного тарифа (3 ученика).</b>\n\nПерейдите на тариф <b>PRO</b>, чтобы добавлять учеников без ограничений.\n\nДля активации напишите админу: {admin}",
        "add_need_student": "Сначала добавьте ученика!",
        
        "report_choose": "Кому отправить отчет об успехах?",
        "report_sent": "✅ Отчет отправлен родителю!",
        "report_error": "❌ Ошибка! Родитель не привязал аккаунт.",
        
        "vacation_prompt": "Введите период в формате:\nДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n\nНапример: 05.11.2026 - 12.11.2026",
        "vacation_error": "❌ Ошибка формата. Введите точно так: 05.11.2026 - 12.11.2026",
        "vacation_processing": "⏳ Отменяю уроки и рассылаю уведомления...",
        "vacation_done": "✅ Готово! Отменено уроков: {count}.",
        "vacation_notify": "⚠️ Внимание! Занятия с {start} по {end} отменяются.",
        
        "share_text": "🎁 Пригласите коллегу!\nОтправьте ссылку другу.",
        
        "student_info_title": "ℹ️ <b>Профиль:</b>",
        "student_info_text": "👤 Имя: {name}\n📚 Предмет: {subject}\n⏰ Расписание: {schedule}\n",
        "parent_journal_title": "📊 <b>Журнал ({name}):</b>",
        "parent_journal_text": "📅 Проведено: {total} | Оплачено: {paid}\n❌ Долг: {debt}\n📈 Карма: {karma}%\n",
        
        "schedule_info": "📅 Информация для {name}:",
        "schedule_my_info": "📅 Ваша информация:",
        "schedule_subject": "📚 Предмет: {subject}",
        "schedule_sub": "🎟 Абонемент: {left} из {total}",
        "schedule_time": "⏰ Расписание: {schedule}",
        "schedule_karma": "📈 Индекс дисциплины: {karma}%",
        "schedule_upcoming": "🗓 <b>Ближайшие занятия:</b>",
        "schedule_no_dates": "Точных дат пока нет.",
        
        "move_choose": "Какой урок вы хотите перенести?",
        "move_day": "На какой день?",
        "move_time": "На какое время?",
        "move_sent": "✅ Запрос отправлен!",
        "move_request": "🔄 <b>Запрос на перенос!</b>\n\nУченик {name} просит перенести урок с {old} на {new}.",
        "move_allow": "✅ Разрешить",
        "move_deny": "❌ Отказать",
        "move_allowed": "✅ Вы РАЗРЕШИЛИ перенос.",
        "move_denied": "❌ Вы ОТКАЗАЛИ в переносе.",
        "move_approved_notify": "🎉 Репетитор разрешил перенос! Ждем вас {time}.",
        "move_rejected_notify": "😔 К сожалению, репетитор не может перенести этот урок.",
        
        "remind_24h": "🔔 Напоминаем: завтра в {time} у вас занятие по предмету {subject}.\nВы придете?",
        "remind_24h_parent": "🔔 Напоминаем: завтра в {time} у {name} занятие по предмету {subject}.",
        "remind_2h": "⏰ Напоминаем: через 2 часа ({time}) у вас занятие по предмету {subject}!",
        "remind_2h_parent": "⏰ Напоминаем: через 2 часа ({time}) у {name} занятие по предмету {subject}!",
        "btn_yes": "✅ Буду",
        "btn_no": "❌ Не смогу",
        
        "confirm_lesson": "✅ Вы подтвердили участие.",
        "cancel_lesson": "❌ Вы отменили занятие.",
        "tutor_notify_confirm": "🟢 Ученик {name} ПОДТВЕРДИЛ урок на {time}!",
        "tutor_notify_cancel": "{icon} Ученик {name} ОТМЕНИЛ урок на {time}!{late}",
        "late_cancel": " (ПОЗДНЯЯ ОТМЕНА!)"
    },
    "en": {
        "choose_lang": "Please choose a language:",
        "lang_set": "🇬🇧 Language set: English",
        "choose_role": "👋 Hello! Please choose your role:",
        "role_tutor": "🎓 I am a tutor",
        "role_student": "👨‍🎓 I am a student",
        "role_parent": "👩‍👦 I am a parent",
        "tutor_menu": "Tutor menu:",
        "student_menu": "Student menu:",
        "parent_menu": "Parent menu:",
        "btn_schedule": "📅 Schedule",
        "btn_students": "👤 My students",
        "btn_payments": "💵 Payments",
        "btn_stats": "📊 Statistics",
        "btn_report": "📝 Report to parent",
        "btn_vacation": "🌴 Vacation / Sick",
        "btn_tariffs": "💎 Pricing",
        "btn_share": "🎁 Invite colleague",
        "btn_settings": "⚙️ Settings",
        "btn_back": "🔙 Change role",
        "btn_to_main": "🏠 Main menu",
        "btn_change_lang": "🌐 Change language",
        "btn_edit_details": "✏️ Edit payment details",
        "btn_my_schedule": "📅 My schedule",
        "btn_move_lesson": "🔄 Move lesson",
        "btn_my_info": "ℹ️ My info",
        "btn_child_schedule": "📅 Child's schedule",
        "btn_journal": "📊 Journal & payments",
        "btn_cancel": "🏠 Cancel",
        "btn_skip": "⏭️ Skip",
        "btn_share": "📤 Share",
        
        "payments_title": "💵 <b>Payments</b>",
        "payments_all_paid": "Hooray! All lessons are paid.",
        "payments_click": "Click to mark as paid:",
        
        "settings_title": "⚙️ <b>Profile Settings</b>",
        "settings_id": "🆔 Your ID: <code>{id}</code>\n<i>(Send it to admin for payment)</i>",
        "settings_details": "💳 Payment details:\n{details}",
        "settings_ask_details": "Enter payment details:",
        "settings_updated": "✅ Details updated!",
        
        "schedule_title": "📅 <b>Your schedule:</b>\n\n",
        "schedule_empty": "📅 You have no scheduled lessons yet.",
        "schedule_choose_student": "Choose a student:",
        "schedule_choose_day": "Choose a day (next 7 days):",
        "schedule_selected_day": "Selected day: {date}.\nChoose time:",
        "schedule_added": "✅ Lesson on {date} {time} added!",
        
        "stats_title": "📊 <b>Statistics ({month})</b>\n\n💰 Earned: <b>{money} RUB</b>\n✅ Paid lessons: <b>{lessons}</b>\n🔔 Reminders sent: <b>{reminders}</b>\n⏳ Time saved: <b>~{hours} h.</b>\n",
        
        "tariffs_text": "💎 <b>Repetly Pricing</b>\n\n👤 <b>Free:</b> up to 3 active students.\n🚀 <b>PRO:</b> unlimited students + all features.\n\n📅 <b>1 month:</b>\n🇷🇺 490 RUB | 🇧🇾 15 BYN | 🇰🇿 2500 KZT | 🇪🇺 4.55 EUR\n\n📦 <b>6 months (-15%):</b>\n🇷🇺 2200 RUB | 🇧🇾 76.5 BYN | 🇰🇿 11250 KZT | 🇪🇺 22.75 EUR\n\n🎓 <b>9 months (-25%):</b>\n🇷🇺 3300 RUB | 🇧🇾 101 BYN | 🇰🇿 16850 KZT | 🇪🇺 36.5 EUR\n\nTo pay, contact: {admin}",
        "btn_contact": "💬 Contact for payment",
        
        "students_empty": "You don't have students yet.",
        "students_list": "👤 <b>Your students:</b>\n\n",
        "students_delete_hint": "\nClick the cross to delete.",
        "students_ask_delete": "⚠️ Delete student?",
        "students_yes_delete": "✅ Yes, delete",
        "students_deleted": "Student deleted!",
        
        "add_step1": "Step 1 of 5. Enter new student's name:",
        "add_step2": "Great, {name}!\nStep 2 of 5. Choose a subject from the list:",
        "add_step2_text": "Enter the subject name:",
        "add_step3": "Subject chosen: {subject}.\nStep 3 of 5. Enter lesson price (in RUB):",
        "add_step4": "Step 4 of 5. Enter schedule (e.g. Tue 16:00). Or click Skip.",
        "add_step5": "Step 5 of 5. Choose payment format:",
        "add_error_price": "❌ Please enter only numbers. E.g. 60",
        "add_success": "✅ Student {name} added!\n📚 Subject: {subject}\n💰 Price: {price} RUB\n\nStudent link:\n{link_student}\n\nParent link:\n{link_parent}",
        "add_limit": "⚠️ <b>You reached the free tier limit (3 students).</b>\n\nUpgrade to <b>PRO</b> to add unlimited students.\n\nTo activate, contact admin: {admin}",
        "add_need_student": "Add a student first!",
        
        "report_choose": "Who to send the progress report to?",
        "report_sent": "✅ Report sent to parent!",
        "report_error": "❌ Error! Parent is not linked.",
        
        "vacation_prompt": "Enter period in format:\nDD.MM.YYYY - DD.MM.YYYY\n\nExample: 05.11.2026 - 12.11.2026",
        "vacation_error": "❌ Format error. Enter like this: 05.11.2026 - 12.11.2026",
        "vacation_processing": "⏳ Canceling lessons and sending notifications...",
        "vacation_done": "✅ Done! Lessons canceled: {count}.",
        "vacation_notify": "⚠️ Attention! Lessons from {start} to {end} are canceled.",
        
        "share_text": "🎁 Invite a colleague!\nSend the link to a friend.",
        
        "student_info_title": "ℹ️ <b>Profile:</b>",
        "student_info_text": "👤 Name: {name}\n📚 Subject: {subject}\n⏰ Schedule: {schedule}\n",
        "parent_journal_title": "📊 <b>Journal ({name}):</b>",
        "parent_journal_text": "📅 Conducted: {total} | Paid: {paid}\n❌ Debt: {debt}\n📈 Karma: {karma}%\n",
        
        "schedule_info": "📅 Info for {name}:",
        "schedule_my_info": "📅 Your info:",
        "schedule_subject": "📚 Subject: {subject}",
        "schedule_sub": "🎟 Subscription: {left} of {total}",
        "schedule_time": "⏰ Schedule: {schedule}",
        "schedule_karma": "📈 Discipline index: {karma}%",
        "schedule_upcoming": "🗓 <b>Upcoming lessons:</b>",
        "schedule_no_dates": "No exact dates yet.",
        
        "move_choose": "Which lesson do you want to move?",
        "move_day": "To which day?",
        "move_time": "To what time?",
        "move_sent": "✅ Request sent!",
        "move_request": "🔄 <b>Move request!</b>\n\nStudent {name} asks to move lesson from {old} to {new}.",
        "move_allow": "✅ Allow",
        "move_deny": "❌ Deny",
        "move_allowed": "✅ You ALLOWED the move.",
        "move_denied": "❌ You DENIED the move.",
        "move_approved_notify": "🎉 Tutor allowed the move! See you at {time}.",
        "move_rejected_notify": "😔 Unfortunately, tutor cannot move this lesson.",
        
        "remind_24h": "🔔 Reminder: tomorrow at {time} you have a lesson in {subject}.\nWill you come?",
        "remind_24h_parent": "🔔 Reminder: tomorrow at {time} {name} has a lesson in {subject}.",
        "remind_2h": "⏰ Reminder: in 2 hours ({time}) you have a lesson in {subject}!",
        "remind_2h_parent": "⏰ Reminder: in 2 hours ({time}) {name} has a lesson in {subject}!",
        "btn_yes": "✅ I will",
        "btn_no": "❌ I can't",
        
        "confirm_lesson": "✅ You confirmed participation.",
        "cancel_lesson": "❌ You canceled the lesson.",
        "tutor_notify_confirm": "🟢 Student {name} CONFIRMED lesson on {time}!",
        "tutor_notify_cancel": "{icon} Student {name} CANCELED lesson on {time}!{late}",
        "late_cancel": " (LATE CANCEL!)"
    },
    "lv": {
        "choose_lang": "Lūdzu, izvēlieties valodu:",
        "lang_set": "🇱🇻 Valoda iestatīta: Latviešu",
        "choose_role": "👋 Sveiki! Lūdzu, izvēlieties savu lomu:",
        "role_tutor": "🎓 Esmu pasniedzējs",
        "role_student": "👨‍🎓 Esmu skolēns",
        "role_parent": "👩‍👦 Esmu vecāks",
        "tutor_menu": "Pasniedzēja izvēlne:",
        "student_menu": "Skolēna izvēlne:",
        "parent_menu": "Vecāku izvēlne:",
        "btn_schedule": "📅 Grafiks",
        "btn_students": "👤 Mani skolēni",
        "btn_payments": "💵 Maksājumi",
        "btn_stats": "📊 Statistika",
        "btn_report": "📝 Ziņojums vecākiem",
        "btn_vacation": "🌴 Atvaļinājums",
        "btn_tariffs": "💎 Tarifi",
        "btn_share": "🎁 Uzaicināt kolēģi",
        "btn_settings": "⚙️ Iestatījumi",
        "btn_back": "🔙 Mainīt lomu",
        "btn_to_main": "🏠 Galvenā izvēlne",
        "btn_change_lang": "🌐 Mainīt valodu",
        "btn_edit_details": "✏️ Mainīt rekvizītus",
        "btn_my_schedule": "📅 Mans grafiks",
        "btn_move_lesson": "🔄 Pārcelt nodarbību",
        "btn_my_info": "ℹ️ Mana informācija",
        "btn_child_schedule": "📅 Bērna grafiks",
        "btn_journal": "📊 Žurnāls un maksājumi",
        "btn_cancel": "🏠 Atcelt",
        "btn_skip": "⏭️ Izlaist",
        "btn_share": "📤 Dalīties",
        
        "payments_title": "💵 <b>Maksājumi</b>",
        "payments_all_paid": "Urrā! Visi maksājumi veikti.",
        "payments_click": "Noklikšķiniet, lai atzīmētu kā apmaksātu:",
        
        "settings_title": "⚙️ <b>Profila iestatījumi</b>",
        "settings_id": "🆔 Jūsu ID: <code>{id}</code>\n<i>(Nosūtiet to administratoram)</i>",
        "settings_details": "💳 Rekvizīti:\n{details}",
        "settings_ask_details": "Ievadiet rekvizītus:",
        "settings_updated": "✅ Rekvizīti atjaunināti!",
        
        "schedule_title": "📅 <b>Jūsu grafiks:</b>\n\n",
        "schedule_empty": "📅 Jums vēl nav ieplānotu nodarbību.",
        "schedule_choose_student": "Izvēlieties skolēnu:",
        "schedule_choose_day": "Izvēlieties dienu (nākamās 7 dienas):",
        "schedule_selected_day": "Izvēlētā diena: {date}.\nIzvēlieties laiku:",
        "schedule_added": "✅ Nodarbība {date} {time} pievienota!",
        
        "stats_title": "📊 <b>Statistika ({month})</b>\n\n💰 Nopelnīts: <b>{money} RUB</b>\n✅ Apmaksātas nodarbības: <b>{lessons}</b>\n🔔 Nosūtīti atgādinājumi: <b>{reminders}</b>\n⏳ Ietaupīts laiks: <b>~{hours} h.</b>\n",
        
        "tariffs_text": "💎 <b>Repetly Tarifi</b>\n\n👤 <b>Bezmaksas:</b> līdz 3 aktīviem skolēniem.\n🚀 <b>PRO:</b> neierobežots skolēnu skaits.\n\n📅 <b>1 mēnesis:</b>\n🇷🇺 490 RUB | 🇧🇾 15 BYN | 🇰🇿 2500 KZT | 🇪🇺 4.55 EUR\n\n📦 <b>6 mēneši (-15%):</b>\n🇷🇺 2200 RUB | 🇧🇾 76.5 BYN | 🇰🇿 11250 KZT | 🇪🇺 22.75 EUR\n\n🎓 <b>9 mēneši (-25%):</b>\n🇷🇺 3300 RUB | 🇧🇾 101 BYN | 🇰🇿 16850 KZT | 🇪🇺 36.5 EUR\n\nLai samaksātu, sazinieties: {admin}",
        "btn_contact": "💬 Sazināties par samaksu",
        
        "students_empty": "Jums vēl nav skolēnu.",
        "students_list": "👤 <b>Jūsu skolēni:</b>\n\n",
        "students_delete_hint": "\nNoklikšķiniet uz krustiņa, lai dzēstu.",
        "students_ask_delete": "⚠️ Dzēst skolēnu?",
        "students_yes_delete": "✅ Jā, dzēst",
        "students_deleted": "Skolēns dzēsts!",
        
        "add_step1": "1. solis no 5. Ievadiet jaunā skolēna vārdu:",
        "add_step2": "Lieliski, {name}!\n2. solis no 5. Izvēlieties priekšmetu no saraksta:",
        "add_step2_text": "Ievadiet priekšmeta nosaukumu:",
        "add_step3": "Izvēlēts priekšmets: {subject}.\n3. solis no 5. Ievadiet nodarbības cenu (RUB):",
        "add_step4": "4. solis no 5. Ievadiet grafiku (piem., Otr 16:00). Vai noklikšķiniet Izlaist.",
        "add_step5": "5. solis no 5. Izvēlieties maksājuma formātu:",
        "add_error_price": "❌ Lūdzu, ievadiet tikai skaitļus. Piem., 60",
        "add_success": "✅ Skolēns {name} pievienots!\n📚 Priekšmets: {subject}\n💰 Cena: {price} RUB\n\nSkolēna saite:\n{link_student}\n\nVecāku saite:\n{link_parent}",
        "add_limit": "⚠️ <b>Jūs sasniedzāt bezmaksas limitu (3 skolēni).</b>\n\nPārejiet uz <b>PRO</b>, lai pievienotu neierobežotu skaitu skolēnu.\n\nLai aktivizētu, sazinieties ar administratoru: {admin}",
        "add_need_student": "Vispirms pievienojiet skolēnu!",
        
        "report_choose": "Kam nosūtīt progresa ziņojumu?",
        "report_sent": "✅ Ziņojums nosūtīts vecākiem!",
        "report_error": "❌ Kļūda! Vecāks nav piesaistīts.",
        
        "vacation_prompt": "Ievadiet periodu formātā:\nDD.MM.YYYY - DD.MM.YYYY\n\nPiemērs: 05.11.2026 - 12.11.2026",
        "vacation_error": "❌ Formāta kļūda. Ievadiet šādi: 05.11.2026 - 12.11.2026",
        "vacation_processing": "⏳ Atceļu nodarbības un sūtu paziņojumus...",
        "vacation_done": "✅ Gatavs! Atceltas nodarbības: {count}.",
        "vacation_notify": "⚠️ Uzmanību! Nodarbības no {start} līdz {end} tiek atceltas.",
        
        "share_text": "🎁 Uzaiciniet kolēģi!\nNosūtiet saiti draugam.",
        
        "student_info_title": "ℹ️ <b>Profils:</b>",
        "student_info_text": "👤 Vārds: {name}\n📚 Priekšmets: {subject}\n⏰ Grafiks: {schedule}\n",
        "parent_journal_title": "📊 <b>Žurnāls ({name}):</b>",
        "parent_journal_text": "📅 Novadīts: {total} | Apmaksāts: {paid}\n❌ Parāds: {debt}\n📈 Karma: {karma}%\n",
        
        "schedule_info": "📅 Informācija par {name}:",
        "schedule_my_info": "📅 Jūsu informācija:",
        "schedule_subject": "📚 Priekšmets: {subject}",
        "schedule_sub": "🎟 Abonements: {left} no {total}",
        "schedule_time": "⏰ Grafiks: {schedule}",
        "schedule_karma": "📈 Disciplīnas indekss: {karma}%",
        "schedule_upcoming": "🗓 <b>Tuvākās nodarbības:</b>",
        "schedule_no_dates": "Precīzu datumu vēl nav.",
        
        "move_choose": "Kuru nodarbību vēlaties pārcelt?",
        "move_day": "Uz kuru dienu?",
        "move_time": "Uz cikiem?",
        "move_sent": "✅ Pieprasījums nosūtīts!",
        "move_request": "🔄 <b>Pārcelšanas pieprasījums!</b>\n\nSkolēns {name} lūdz pārcelt nodarbību no {old} uz {new}.",
        "move_allow": "✅ Atļaut",
        "move_deny": "❌ Liegt",
        "move_allowed": "✅ Jūs ATĻĀVĀT pārcelšanu.",
        "move_denied": "❌ Jūs LIEDZĀT pārcelšanu.",
        "move_approved_notify": "🎉 Pasniedzējs atļāva pārcelšanu! Tiekamies {time}.",
        "move_rejected_notify": "😔 Diemžēl pasniedzējs nevar pārcelt šo nodarbību.",
        
        "remind_24h": "🔔 Atgādinājums: rīt plkst. {time} jums ir nodarbība priekšmetā {subject}.\nVai jūs nāksiet?",
        "remind_24h_parent": "🔔 Atgādinājums: rīt plkst. {time} {name} ir nodarbība priekšmetā {subject}.",
        "remind_2h": "⏰ Atgādinājums: pēc 2 stundām ({time}) jums ir nodarbība priekšmetā {subject}!",
        "remind_2h_parent": "⏰ Atgādinājums: pēc 2 stundām ({time}) {name} ir nodarbība priekšmetā {subject}!",
        "btn_yes": "✅ Būšu",
        "btn_no": "❌ Nevarēšu",
        
        "confirm_lesson": "✅ Jūs apstiprinājāt dalību.",
        "cancel_lesson": "❌ Jūs atcēlāt nodarbību.",
        "tutor_notify_confirm": "🟢 Skolēns {name} APSTIPRINĀJA nodarbību {time}!",
        "tutor_notify_cancel": "{icon} Skolēns {name} ATCĒLA nodarbību {time}!{late}",
        "late_cancel": " (VĒLA ATCELŠANA!)"
    }
}

async def safe_edit_text(message: Message, text: str, reply_markup=None, parse_mode=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.error(f"Ошибка при редактировании: {e}")

DB_NAME = "repetly.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT, language TEXT DEFAULT 'ru', payment_details TEXT DEFAULT '', is_pro INTEGER DEFAULT 0, pro_until TEXT DEFAULT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, name TEXT, student_chat_id INTEGER, parent_chat_id INTEGER, subject TEXT, price INTEGER DEFAULT 0, schedule TEXT, sub_total INTEGER DEFAULT 0, sub_left INTEGER DEFAULT 0, karma INTEGER DEFAULT 100)")
        await db.execute("CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY AUTOINCREMENT, tutor_id INTEGER, student_id INTEGER, lesson_time TEXT, reminded_24h INTEGER DEFAULT 0, reminded_2h INTEGER DEFAULT 0, is_paid INTEGER DEFAULT 0, price INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', is_reminded INTEGER DEFAULT 0)")
        await db.commit()

async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO users (user_id, language) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET language = excluded.language", (user_id, lang))
        await db.commit()

async def get_user_lang(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else "ru"

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
    expiry_date = (datetime.now(TZ) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
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
                    pro_until = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
                    if pro_until > datetime.now(TZ):
                        return 1
                    else:
                        await db.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (user_id,))
                        await db.commit()
                        return 0
                return 1
            return 0

async def update_payment_details(tutor_id: int, details: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET payment_details = ? WHERE user_id = ?", (html.escape(details), tutor_id))
        await db.commit()

async def get_payment_details(tutor_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT payment_details FROM users WHERE user_id = ?", (tutor_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else "-"

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
                l_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
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
    now = datetime.now(TZ)
    month_str = now.strftime("%m.%Y")
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT SUM(price), COUNT(id) FROM lessons WHERE tutor_id = ? AND is_paid = 1 AND lesson_time LIKE ?"
        async with db.execute(query, (tutor_id, f"%{month_str}%")) as cursor:
            row = await cursor.fetchone()
            return row[0] or 0, row[1] or 0 

async def get_reminders_count(tutor_id: int):
    now = datetime.now(TZ)
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

async def check_reminders(bot: Bot):
    now = datetime.now(TZ)
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT l.id, l.lesson_time, l.reminded_24h, l.reminded_2h, s.name, s.subject, s.student_chat_id, s.parent_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.status != 'canceled'"
        async with db.execute(query) as cursor:
            lessons = await cursor.fetchall()
        for l_id, l_time_str, r24, r2, s_name, subject, s_chat, p_chat in lessons:
            try:
                lesson_time = datetime.strptime(l_time_str, "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
            except ValueError:
                continue 
            time_diff = lesson_time - now
            hours_left = time_diff.total_seconds() / 3600
            if 20 <= hours_left <= 24 and r24 == 0:
                if s_chat:
                    lang = await get_user_lang(s_chat)
                    text = TEXTS[lang]["remind_24h"].format(time=lesson_time.strftime('%H:%M'), subject=subject)
                    builder = InlineKeyboardBuilder()
                    builder.button(text=TEXTS[lang]["btn_yes"], callback_data=f"confirm_l_{l_id}")
                    builder.button(text=TEXTS[lang]["btn_no"], callback_data=f"cancel_l_{l_id}")
                    builder.adjust(2)
                    await bot.send_message(s_chat, text, reply_markup=builder.as_markup())
                if p_chat:
                    p_lang = await get_user_lang(p_chat)
                    p_text = TEXTS[p_lang]["remind_24h_parent"].format(time=lesson_time.strftime('%H:%M'), name=s_name, subject=subject)
                    await bot.send_message(p_chat, p_text)
                await db.execute("UPDATE lessons SET reminded_24h = 1, is_reminded = 1 WHERE id = ?", (l_id,))
            elif 0 < hours_left <= 2 and r2 == 0:
                if s_chat:
                    lang = await get_user_lang(s_chat)
                    await bot.send_message(s_chat, TEXTS[lang]["remind_2h"].format(time=lesson_time.strftime('%H:%M'), subject=subject))
                if p_chat:
                    p_lang = await get_user_lang(p_chat)
                    await bot.send_message(p_chat, TEXTS[p_lang]["remind_2h_parent"].format(time=lesson_time.strftime('%H:%M'), name=s_name, subject=subject))
                await db.execute("UPDATE lessons SET reminded_2h = 1 WHERE id = ?", (l_id,))
        await db.commit()

async def check_subscriptions(bot: Bot):
    now = datetime.now(TZ)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, pro_until FROM users WHERE is_pro = 1") as cursor:
            users = await cursor.fetchall()
        for user_id, pro_until in users:
            if pro_until:
                expiry = datetime.strptime(pro_until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
                if expiry < now:
                    await db.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (user_id,))
                    await db.commit()
                    try: await bot.send_message(user_id, "⚠️ <b>Ваша подписка PRO истекла!</b>\n\nПродлите тариф в «💎 Тарифы и Подписка».", parse_mode="HTML")
                    except Exception: pass

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

def get_lang_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang_ru")
    builder.button(text="🇬🇧 English", callback_data="lang_en")
    builder.button(text="🇱🇻 Latviešu", callback_data="lang_lv")
    builder.adjust(1)
    return builder.as_markup()

def get_main_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["role_tutor"], callback_data="role_tutor")
    builder.button(text=TEXTS[lang]["role_student"], callback_data="role_student")
    builder.button(text=TEXTS[lang]["role_parent"], callback_data="role_parent")
    builder.adjust(1)
    return builder.as_markup()

def get_tutor_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_schedule"], callback_data="tutor_schedule")
    builder.button(text=TEXTS[lang]["btn_students"], callback_data="tutor_students")
    builder.button(text=TEXTS[lang]["btn_payments"], callback_data="tutor_payments")
    builder.button(text=TEXTS[lang]["btn_stats"], callback_data="tutor_stats")
    builder.button(text=TEXTS[lang]["btn_report"], callback_data="tutor_report")
    builder.button(text=TEXTS[lang]["btn_vacation"], callback_data="tutor_vacation")
    builder.button(text=TEXTS[lang]["btn_tariffs"], callback_data="tutor_tariffs")
    builder.button(text=TEXTS[lang]["btn_share"], callback_data="tutor_share")
    builder.button(text=TEXTS[lang]["btn_settings"], callback_data="tutor_settings")
    builder.button(text=TEXTS[lang]["btn_back"], callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_student_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_my_schedule"], callback_data="student_schedule")
    builder.button(text=TEXTS[lang]["btn_move_lesson"], callback_data="student_move")
    builder.button(text=TEXTS[lang]["btn_my_info"], callback_data="student_info")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_parent_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_child_schedule"], callback_data="parent_schedule")
    builder.button(text=TEXTS[lang]["btn_journal"], callback_data="parent_journal")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_students_menu(students, lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ " + TEXTS[lang]["btn_students"].split(" ")[-1], callback_data="add_student")
    for s_id, name, subject, price, schedule, sub_left, sub_total, karma in students:
        builder.button(text=f"❌ {name} ({subject})", callback_data=f"del_student_{s_id}")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_subject_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    subjects = ["Math", "Physics", "Russian", "English", "Chemistry", "IT", "Biology", "History"] if lang != "ru" else ["Математика", "Физика", "Русский язык", "Английский язык", "Химия", "Информатика", "Биология", "История"]
    for i, subj in enumerate(subjects):
        builder.button(text=subj, callback_data=f"subj_{i}")
    builder.button(text="🌐 " + TEXTS[lang]["add_step2_text"], callback_data="subj_other")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    builder.adjust(2)
    return builder.as_markup()

def get_subscription_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣", callback_data="sub_1")
    builder.button(text="🎟 4", callback_data="sub_4")
    builder.button(text="🎟 8", callback_data="sub_8")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_delete_menu(student_id, lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["students_yes_delete"], callback_data=f"confirm_del_{student_id}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_students")
    builder.adjust(1)
    return builder.as_markup()

def get_schedule_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ " + TEXTS[lang]["btn_schedule"].split(" ")[-1], callback_data="add_lesson")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_payments_menu(unpaid_lessons, lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    if unpaid_lessons:
        for l_id, l_time, s_name, price, parent_chat in unpaid_lessons:
            builder.button(text=f"💵 {s_name} ({price} RUB) - {l_time}", callback_data=f"pay_{l_id}")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_cancel_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    return builder.as_markup()

def get_skip_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_skip"], callback_data="skip_schedule")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    builder.adjust(1)
    return builder.as_markup()

def get_days_menu(lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    today = datetime.now(TZ)
    days = {"ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "lv": ["Pr", "Ot", "Tr", "Ce", "Pk", "Se", "Sv"]}
    today_str = {"ru": "Сегодня", "en": "Today", "lv": "Šodien"}
    tomorrow_str = {"ru": "Завтра", "en": "Tomorrow", "lv": "Rīt"}
    
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        if i == 0: day_name = today_str[lang]
        elif i == 1: day_name = tomorrow_str[lang]
        else: day_name = days[lang][date.weekday()]
        btn_text = f"{day_name} ({date.strftime('%d.%m')})"
        builder.button(text=btn_text, callback_data=f"day_{date_str}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="back_to_main")
    builder.adjust(2)
    return builder.as_markup()

def get_time_menu(selected_date, lang):
    lang = lang if lang in TEXTS else "ru"
    builder = InlineKeyboardBuilder()
    times = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"]
    for t in times:
        builder.button(text=t, callback_data=f"time_{selected_date}_{t}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="back_to_main")
    builder.adjust(3)
    return builder.as_markup() 
# ==========================================
# ОБРАБОТЧИКИ КОМАНД
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    
    # 1. Обработка пригласительных ссылок (ученики и родители)
    if command.args and command.args.startswith("bind_"):
        parts = command.args.split("_")
        student_id = int(parts[1])
        role = parts[2]
        await bind_user(student_id, user_id, role)
        
        # Проверяем, выбран ли язык
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row or not row[0]:
                    await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=get_lang_menu())
                    return
        
        lang = await get_user_lang(user_id)
        if role == "student":
            await message.answer(TEXTS[lang]["student_menu"], reply_markup=get_student_menu(lang))
        else:
            await message.answer(TEXTS[lang]["parent_menu"], reply_markup=get_parent_menu(lang))
        return

    # 2. Обычный запуск (проверка языка и роли)
    role = await get_user_role(user_id)
    lang = await get_user_lang(user_id)
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=get_lang_menu())
                return

    if role == "tutor":
        await message.answer(TEXTS[lang]["tutor_menu"], reply_markup=get_tutor_menu(lang))
    elif role == "student":
        await message.answer(TEXTS[lang]["student_menu"], reply_markup=get_student_menu(lang))
    elif role == "parent":
        await message.answer(TEXTS[lang]["parent_menu"], reply_markup=get_parent_menu(lang))
    else:
        await message.answer(TEXTS[lang]["choose_role"], reply_markup=get_main_menu(lang))

@router.callback_query(F.data.startswith("lang_"))
async def process_lang_selection(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    await set_user_lang(user_id, lang)
    
    role = await get_user_role(user_id)
    if role == "tutor":
        await safe_edit_text(callback.message, TEXTS[lang]["tutor_menu"], reply_markup=get_tutor_menu(lang))
    elif role == "student":
        await safe_edit_text(callback.message, TEXTS[lang]["student_menu"], reply_markup=get_student_menu(lang))
    elif role == "parent":
        await safe_edit_text(callback.message, TEXTS[lang]["parent_menu"], reply_markup=get_parent_menu(lang))
    else:
        await safe_edit_text(callback.message, TEXTS[lang]["lang_set"] + "\n\n" + TEXTS[lang]["choose_role"], reply_markup=get_main_menu(lang))
    await callback.answer()

@router.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    lang = await get_user_lang(callback.from_user.id)
    
    if role in ["student", "parent"]:
        await safe_edit_text(callback.message, "⚠️ Перейдите по ссылке от репетитора / Use tutor's link", reply_markup=get_main_menu(lang))
    else:
        await set_user_role(callback.from_user.id, role)
        await safe_edit_text(callback.message, TEXTS[lang]["tutor_menu"], reply_markup=get_tutor_menu(lang))
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def process_back_button(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    role = await get_user_role(callback.from_user.id)
    
    if role == "tutor":
        await safe_edit_text(callback.message, TEXTS[lang]["tutor_menu"], reply_markup=get_tutor_menu(lang))
    elif role == "student":
        await safe_edit_text(callback.message, TEXTS[lang]["student_menu"], reply_markup=get_student_menu(lang))
    elif role == "parent":
        await safe_edit_text(callback.message, TEXTS[lang]["parent_menu"], reply_markup=get_parent_menu(lang))
    else:
        await safe_edit_text(callback.message, TEXTS[lang]["choose_role"], reply_markup=get_main_menu(lang))
    await callback.answer()

@router.callback_query(F.data == "tutor_menu_back")
async def process_tutor_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(callback.from_user.id)
    await safe_edit_text(callback.message, TEXTS[lang]["tutor_menu"], reply_markup=get_tutor_menu(lang))
    await callback.answer()

# ==========================================
# АДМИН-ПАНЕЛЬ
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
            lang = await get_user_lang(target_id)
            success_text = {
                "ru": f"🎉 <b>Ваша оплата получена!</b>\nВам активирован тариф PRO на {months} мес.\nДата окончания: <b>{expiry.split(' ')[0]}</b>\n\nСпасибо, что выбрали Repetly!",
                "en": f"🎉 <b>Payment received!</b>\nPRO activated for {months} months.\nExpires: <b>{expiry.split(' ')[0]}</b>\n\nThanks for choosing Repetly!",
                "lv": f"🎉 <b>Maksājums saņemts!</b>\nPRO aktivizēts uz {months} mēnešiem.\nBeidzas: <b>{expiry.split(' ')[0]}</b>\n\nPaldies, ka izvēlējāties Repetly!"
            }
            await message.bot.send_message(target_id, success_text.get(lang, success_text["ru"]), parse_mode="HTML")
        except: pass
    except Exception:
        await message.answer(f"❌ Ошибка. Используй: /activate ID [Кол-во месяцев]")

# ==========================================
# ТАРИФЫ
# ==========================================
@router.callback_query(F.data == "tutor_tariffs")
async def show_tariffs(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    text = TEXTS[lang]["tariffs_text"].format(admin=ADMIN_USERNAME)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_contact"], url=ADMIN_TG_LINK)
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    
    client_id = callback.from_user.id
    client_name = html.escape(callback.from_user.full_name)
    
    try:
        await bot.send_message(ADMIN_ID, f"🔔 <b>Клиент хочет купить Premium!</b>\n\n👤 Имя: {client_name}\n🆔 ID: <code>{client_id}</code>\n\nЯзык: {lang}\nАктивация: <code>/activate {client_id} 1</code>", parse_mode="HTML")
    except Exception: pass

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# УЧЕНИКИ (ДОБАВЛЕНИЕ И УДАЛЕНИЕ)
# ==========================================
@router.callback_query(F.data == "tutor_students")
async def show_students(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    students = await get_students_by_tutor(callback.from_user.id)
    text = TEXTS[lang]["students_empty"] if not students else TEXTS[lang]["students_list"]
    
    if students:
        for s_id, name, subject, price, schedule, sub_left, sub_total, karma in students:
            sched_text = f" ({schedule})" if schedule else ""
            sub_text = f" | 🎟 {sub_left}/{sub_total}" if sub_total > 1 else ""
            text += f"• {name} — {subject} — {price} RUB{sched_text}{sub_text} | Karma: {karma}%\n"
        text += TEXTS[lang]["students_delete_hint"]
        
    await safe_edit_text(callback.message, text, reply_markup=get_students_menu(students, lang))
    await callback.answer()

@router.callback_query(F.data == "add_student")
async def start_add_student(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    students = await get_students_by_tutor(callback.from_user.id)
    is_pro = await get_user_pro(callback.from_user.id)
    
    if len(students) >= 3 and not is_pro:
        text = TEXTS[lang]["add_limit"].format(admin=ADMIN_USERNAME)
        builder = InlineKeyboardBuilder()
        builder.button(text=TEXTS[lang]["btn_contact"], url=ADMIN_TG_LINK)
        builder.button(text=TEXTS[lang]["btn_tariffs"], callback_data="tutor_tariffs")
        builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
        builder.adjust(1)
        await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return
        
    await safe_edit_text(callback.message, TEXTS[lang]["add_step1"], reply_markup=get_cancel_menu(lang))
    await state.set_state(AddStudent.waiting_for_name)
    await callback.answer()

@router.message(AddStudent.waiting_for_name)
async def process_student_name(message: Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    await state.update_data(name=message.text, lang=lang)
    await message.answer(TEXTS[lang]["add_step2"].format(name=message.text), reply_markup=get_subject_menu(lang))
    await state.set_state(AddStudent.waiting_for_subject)

@router.callback_query(AddStudent.waiting_for_subject, F.data.startswith("subj_"))
async def process_student_subject(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    subj_code = callback.data.split("_")[1]
    if subj_code == "other":
        await safe_edit_text(callback.message, TEXTS[lang]["add_step2_text"])
        return
    
    subjects_ru = ["Математика", "Физика", "Русский язык", "Английский язык", "Химия", "Информатика", "Биология", "История"]
    subjects_en = ["Math", "Physics", "Russian", "English", "Chemistry", "IT", "Biology", "History"]
    subject = subjects_ru[int(subj_code)] if lang == "ru" else subjects_en[int(subj_code)]
    
    await state.update_data(subject=subject)
    await safe_edit_text(callback.message, TEXTS[lang]["add_step3"].format(subject=subject))
    await state.set_state(AddStudent.waiting_for_price)
    await callback.answer()

@router.message(AddStudent.waiting_for_subject)
async def process_custom_subject(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(subject=message.text)
    await message.answer(TEXTS[lang]["add_step3"].format(subject=message.text))
    await state.set_state(AddStudent.waiting_for_price)

@router.message(AddStudent.waiting_for_price)
async def process_student_price(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    try:
        price = int(message.text)
        await state.update_data(price=price)
    except ValueError:
        await message.answer(TEXTS[lang]["add_error_price"])
        return
    await message.answer(TEXTS[lang]["add_step4"], reply_markup=get_skip_menu(lang))
    await state.set_state(AddStudent.waiting_for_schedule)

@router.message(AddStudent.waiting_for_schedule)
async def process_student_schedule(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(schedule=message.text)
    await message.answer(TEXTS[lang]["add_step5"], reply_markup=get_subscription_menu(lang))
    await state.set_state(AddStudent.waiting_for_sub)

@router.callback_query(AddStudent.waiting_for_schedule, F.data == "skip_schedule")
async def process_skip_schedule(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(schedule="")
    await safe_edit_text(callback.message, TEXTS[lang]["add_step5"], reply_markup=get_subscription_menu(lang))
    await state.set_state(AddStudent.waiting_for_sub)
    await callback.answer()

@router.callback_query(AddStudent.waiting_for_sub, F.data.startswith("sub_"))
async def process_student_sub(callback: CallbackQuery, state: FSMContext):
    sub_total = int(callback.data.split("_")[1])
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await finish_add_student(callback.from_user.id, data['name'], data['subject'], data['price'], data['schedule'], sub_total, callback.message, lang)
    await state.clear()
    await callback.answer()

async def finish_add_student(tutor_id, name, subject, price, schedule, sub_total, message_obj, lang):
    student_id = await add_student(tutor_id, name, subject, price, schedule, sub_total)
    link_student = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_student"
    link_parent = f"https://t.me/{BOT_USERNAME}?start=bind_{student_id}_parent"
    text = TEXTS[lang]["add_success"].format(name=html.escape(name), subject=html.escape(subject), price=price, link_student=link_student, link_parent=link_parent)
    await message_obj.answer(text, reply_markup=get_tutor_menu(lang))

@router.callback_query(F.data.startswith("del_student_"))
async def ask_delete_student(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    student_id = int(callback.data.split("_")[2])
    await safe_edit_text(callback.message, TEXTS[lang]["students_ask_delete"], reply_markup=get_confirm_delete_menu(student_id, lang))
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_del_"))
async def process_delete_student(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    await delete_student_from_db(int(callback.data.split("_")[2]))
    await callback.answer(TEXTS[lang]["students_deleted"], show_alert=True)
    await show_students(callback)

# ==========================================
# РАСПИСАНИЕ И ОПЛАТЫ
# ==========================================
@router.callback_query(F.data == "tutor_schedule")
async def show_tutor_schedule(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    lessons = await get_lessons_for_tutor(callback.from_user.id)
    text = TEXTS[lang]["schedule_title"] if lessons else TEXTS[lang]["schedule_empty"]
    if lessons:
        for l_id, time, s_name, subject, status in lessons:
            status_icon = "✅" if status == "confirmed" else ("❌" if status == "canceled" else "⏳")
            text += f"{status_icon} {time} — {s_name} ({subject})\n"
    await safe_edit_text(callback.message, text, reply_markup=get_schedule_menu(lang), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "add_lesson")
async def start_add_lesson(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    students = await get_students_by_tutor(callback.from_user.id)
    if not students:
        await callback.answer(TEXTS[lang]["add_need_student"], show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for s_id, name, subject, price, schedule, sub_l, sub_t, karma in students: 
        builder.button(text=f"{name} ({subject})", callback_data=f"lesson_student_{s_id}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, TEXTS[lang]["schedule_choose_student"], reply_markup=builder.as_markup())
    await state.set_state(AddLesson.waiting_for_student)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_student, F.data.startswith("lesson_student_"))
async def process_lesson_student(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    await state.update_data(student_id=int(callback.data.split("_")[2]), lang=lang)
    await safe_edit_text(callback.message, TEXTS[lang]["schedule_choose_day"], reply_markup=get_days_menu(lang))
    await state.set_state(AddLesson.waiting_for_day)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_day, F.data.startswith("day_"))
async def process_lesson_day(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    selected_date = callback.data.split("_")[1]
    await state.update_data(selected_date=selected_date)
    await safe_edit_text(callback.message, TEXTS[lang]["schedule_selected_day"].format(date=selected_date), reply_markup=get_time_menu(selected_date, lang))
    await state.set_state(AddLesson.waiting_for_time)
    await callback.answer()

@router.callback_query(AddLesson.waiting_for_time, F.data.startswith("time_"))
async def process_lesson_time(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    parts = callback.data.split("_")
    selected_date, selected_time = parts[1], parts[2]
    data = await state.get_data()
    await add_lesson(callback.from_user.id, data.get("student_id"), f"{selected_date} {selected_time}")
    await state.clear()
    await safe_edit_text(callback.message, TEXTS[lang]["schedule_added"].format(date=selected_date, time=selected_time), reply_markup=get_tutor_menu(lang))
    await callback.answer()

@router.callback_query(F.data == "tutor_payments")
async def show_payments(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    unpaid = await get_unpaid_lessons(callback.from_user.id)
    text = f"{TEXTS[lang]['payments_title']}\n\n{TEXTS[lang]['payments_all_paid'] if not unpaid else TEXTS[lang]['payments_click']}"
    await safe_edit_text(callback.message, text, reply_markup=get_payments_menu(unpaid, lang), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
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
                try:
                    p_lang = await get_user_lang(parent_chat)
                    await bot.send_message(parent_chat, f"🎟 {s_name} 0/{student[6]}")
                except Exception: pass

    await callback.answer("✅", show_alert=False)
    
    if parent_chat:
        try:
            p_lang = await get_user_lang(parent_chat)
            pay_msg = {
                "ru": f"💵 Репетитор подтвердил получение {price} руб. за занятие {s_name}.",
                "en": f"💵 Tutor confirmed receipt of {price} RUB for {s_name}'s lesson.",
                "lv": f"💵 Pasniedzējs apstiprināja {price} RUB saņemšanu par {s_name} nodarbību."
            }
            await bot.send_message(parent_chat, pay_msg[p_lang])
        except Exception: pass

    unpaid = await get_unpaid_lessons(callback.from_user.id)
    text = f"{TEXTS[lang]['payments_title']}\n\n{TEXTS[lang]['payments_all_paid'] if not unpaid else TEXTS[lang]['payments_click']}"
    await safe_edit_text(callback.message, text, reply_markup=get_payments_menu(unpaid, lang), parse_mode="HTML")

# ==========================================
# СТАТИСТИКА И ОТЧЕТЫ
# ==========================================
@router.callback_query(F.data == "tutor_stats")
async def show_stats(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    total_money, total_lessons = await get_monthly_earnings(callback.from_user.id)
    reminders_count = await get_reminders_count(callback.from_user.id)
    current_month = datetime.now(TZ).strftime("%m.%Y")
    saved_hours = round(reminders_count * 5 / 60, 1)
    
    text = TEXTS[lang]["stats_title"].format(
        month=current_month, money=total_money, lessons=total_lessons, 
        reminders=reminders_count, hours=saved_hours
    )
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "tutor_report")
async def start_report(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    students = await get_students_by_tutor(callback.from_user.id)
    if not students:
        await callback.answer(TEXTS[lang]["add_need_student"], show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for s_id, name, subject, price, schedule, sub_l, sub_t, karma in students: 
        builder.button(text=f"{name} ({subject})", callback_data=f"rep_student_{s_id}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, TEXTS[lang]["report_choose"], reply_markup=builder.as_markup())
    await state.set_state(ReportState.waiting_for_student)
    await callback.answer()

@router.callback_query(ReportState.waiting_for_student, F.data.startswith("rep_student_"))
async def process_report_student(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    student_id = int(callback.data.split("_")[2])
    student = await get_student_info(student_id)
    if not student:
        await callback.answer("Error", show_alert=True)
        return
    s_id, s_name, tutor_id, subject, price, sub_left, sub_total, karma, parent_chat = student
    total, paid = await get_parent_journal(s_id)
    
    text = (
        f"📝 <b>Ежемесячный отчет / Report:</b>\n\n"
        f"👤 {s_name}\n📚 {subject}\n\n"
        f"📅 Проведено/Conducted: {total}\n✅ Оплачено/Paid: {paid}\n📈 Karma: {karma}%\n"
    )
    if sub_total > 1: text += f"🎟 Остаток/Left: {sub_left} / {sub_total}\n"
    
    if parent_chat:
        try:
            p_lang = await get_user_lang(parent_chat)
            await bot.send_message(parent_chat, text, parse_mode="HTML")
            await safe_edit_text(callback.message, TEXTS[lang]["report_sent"], reply_markup=get_tutor_menu(lang))
        except Exception:
            await safe_edit_text(callback.message, TEXTS[lang]["report_error"], reply_markup=get_tutor_menu(lang))
    else:
        await safe_edit_text(callback.message, TEXTS[lang]["report_error"], reply_markup=get_tutor_menu(lang))
    await state.clear()
    await callback.answer()

# ==========================================
# ОТПУСК, НАСТРОЙКИ И ВИРАЛЬНОСТЬ
# ==========================================
@router.callback_query(F.data == "tutor_vacation")
async def start_vacation(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    await safe_edit_text(callback.message, TEXTS[lang]["vacation_prompt"], reply_markup=get_cancel_menu(lang))
    await state.set_state(VacationState.waiting_for_dates)
    await callback.answer()

@router.message(VacationState.waiting_for_dates)
async def process_vacation_dates(message: Message, state: FSMContext, bot: Bot):
    lang = await get_user_lang(message.from_user.id)
    try:
        parts = message.text.split(" - ")
        start_date = datetime.strptime(parts[0].strip(), "%d.%m.%Y").replace(tzinfo=TZ)
        end_date = datetime.strptime(parts[1].strip(), "%d.%m.%Y").replace(hour=23, minute=59, tzinfo=TZ)
    except Exception:
        await message.answer(TEXTS[lang]["vacation_error"])
        return
    await state.clear()
    await message.answer(TEXTS[lang]["vacation_processing"])
    
    canceled_count = await cancel_lessons_in_period(message.from_user.id, start_date, end_date)
    students = await get_all_students_for_tutor(message.from_user.id)
    
    for s_chat, p_chat in students:
        if s_chat: 
            try: 
                s_lang = await get_user_lang(s_chat)
                await bot.send_message(s_chat, TEXTS[s_lang]["vacation_notify"].format(start=parts[0].strip(), end=parts[1].strip()))
                await asyncio.sleep(0.1)
            except: pass
        if p_chat: 
            try: 
                p_lang = await get_user_lang(p_chat)
                await bot.send_message(p_chat, TEXTS[p_lang]["vacation_notify"].format(start=parts[0].strip(), end=parts[1].strip()))
                await asyncio.sleep(0.1)
            except: pass
            
    await message.answer(TEXTS[lang]["vacation_done"].format(count=canceled_count), reply_markup=get_tutor_menu(lang))

@router.callback_query(F.data == "tutor_share")
async def share_bot(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    share_link = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}&text=Repetly!"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_share"], url=share_link)
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, TEXTS[lang]["share_text"], reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "tutor_settings")
async def show_settings(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    details = await get_payment_details(callback.from_user.id)
    user_id = callback.from_user.id
    is_pro = await get_user_pro(user_id)
    
    pro_status = ""
    if is_pro:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT pro_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    pro_status = f"\n💎 <b>PRO</b> ({row[0].split(' ')[0]})\n"

    text = f"{TEXTS[lang]['settings_title']}\n{pro_status}\n{TEXTS[lang]['settings_id'].format(id=user_id)}\n\n{TEXTS[lang]['settings_details'].format(details=details)}"
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS[lang]["btn_change_lang"], callback_data="settings_change_lang")
    builder.button(text=TEXTS[lang]["btn_edit_details"], callback_data="edit_details")
    builder.button(text=TEXTS[lang]["btn_to_main"], callback_data="tutor_menu_back")
    builder.adjust(1)
    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "settings_change_lang")
async def settings_change_lang(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    await safe_edit_text(callback.message, TEXTS[lang]["choose_lang"], reply_markup=get_lang_menu())
    await callback.answer()

@router.callback_query(F.data == "edit_details")
async def edit_settings(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    await safe_edit_text(callback.message, TEXTS[lang]["settings_ask_details"], reply_markup=get_cancel_menu(lang))
    await state.set_state(SettingsState.waiting_for_details)
    await callback.answer()

@router.message(SettingsState.waiting_for_details)
async def save_settings(message: Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    await update_payment_details(message.from_user.id, message.text)
    await state.clear()
    await message.answer(TEXTS[lang]["settings_updated"], reply_markup=get_tutor_menu(lang))

# ==========================================
# УВЕДОМЛЕНИЯ УЧЕНИКА (ПОДТВЕРЖДЕНИЕ/ОТМЕНА)
# ==========================================
@router.callback_query(F.data.startswith("confirm_l_"))
async def confirm_lesson(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    lesson_id = int(callback.data.split("_")[2])
    await update_lesson_status(lesson_id, "confirmed")
    await safe_edit_text(callback.message, callback.message.text + f"\n\n{TEXTS[lang]['confirm_lesson']}")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT tutor_id, s.name, l.lesson_time FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    t_lang = await get_user_lang(row[0])
                    await bot.send_message(row[0], TEXTS[t_lang]["tutor_notify_confirm"].format(name=row[1], time=row[2]))
                except Exception: pass
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_l_"))
async def cancel_lesson(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    lesson_id = int(callback.data.split("_")[2])
    await update_lesson_status(lesson_id, "canceled")
    await safe_edit_text(callback.message, callback.message.text + f"\n\n{TEXTS[lang]['cancel_lesson']}")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT tutor_id, s.name, l.lesson_time, s.id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                tutor_id, s_name, l_time, s_id = row
                await lower_karma(s_id)
                try:
                    lesson_dt = datetime.strptime(l_time, "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
                    is_late = (lesson_dt - datetime.now(TZ)).total_seconds() < 86400
                except: is_late = False
                
                try:
                    t_lang = await get_user_lang(tutor_id)
                    alert_icon = "🚨" if is_late else "🔴"
                    extra_text = TEXTS[t_lang]["late_cancel"] if is_late else ""
                    await bot.send_message(tutor_id, TEXTS[t_lang]["tutor_notify_cancel"].format(icon=alert_icon, name=s_name, time=l_time, late=extra_text))
                except Exception: pass
    await callback.answer()

# ==========================================
# МЕНЮ УЧЕНИКА И РОДИТЕЛЯ
# ==========================================
@router.callback_query(F.data.in_({"student_schedule", "parent_schedule"}))
async def show_any_schedule(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    role = "parent" if callback.data == "parent_schedule" else "student"
    student = await get_student_by_chat_id(callback.from_user.id, role)
    
    if not student:
        await callback.answer("Error", show_alert=True)
        await safe_edit_text(callback.message, TEXTS[lang]["choose_role"], reply_markup=get_main_menu(lang))
        return
        
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    lessons = await get_lessons_for_student(s_id)
    
    title = TEXTS[lang]["schedule_info"].format(name=s_name) if role == "parent" else TEXTS[lang]["schedule_my_info"]
    text = f"{title}\n{TEXTS[lang]['schedule_subject'].format(subject=subject)}\n"
    if sub_total > 1: text += f"{TEXTS[lang]['schedule_sub'].format(left=sub_left, total=sub_total)}\n"
    text += f"{TEXTS[lang]['schedule_time'].format(schedule=text_schedule or '-')}\n"
    text += f"{TEXTS[lang]['schedule_karma'].format(karma=karma)}\n\n"
    
    if lessons:
        text += f"{TEXTS[lang]['schedule_upcoming']}\n"
        for l_id, time_str, subj in lessons: 
            text += f"🕒 {time_str}\n"
    else: text += TEXTS[lang]["schedule_no_dates"]
    
    reply_menu = get_parent_menu(lang) if role == "parent" else get_student_menu(lang)
    await safe_edit_text(callback.message, text, reply_markup=reply_menu, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "student_move")
async def start_move_lesson(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    student = await get_student_by_chat_id(callback.from_user.id, "student")
    if not student: return
    lessons = await get_lessons_for_student(student[0])
    if not lessons:
        await callback.answer(TEXTS[lang]["schedule_empty"], show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for l_id, time_str, subj in lessons:
        builder.button(text=time_str, callback_data=f"move_l_{l_id}")
    builder.button(text=TEXTS[lang]["btn_cancel"], callback_data="back_to_main")
    builder.adjust(1)
    await safe_edit_text(callback.message, TEXTS[lang]["move_choose"], reply_markup=builder.as_markup())
    await state.set_state(MoveLesson.waiting_for_lesson)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_lesson, F.data.startswith("move_l_"))
async def process_move_lesson(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    await state.update_data(lesson_id=int(callback.data.split("_")[2]), lang=lang)
    await safe_edit_text(callback.message, TEXTS[lang]["move_day"], reply_markup=get_days_menu(lang))
    await state.set_state(MoveLesson.waiting_for_day)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_day, F.data.startswith("day_"))
async def process_move_day(callback: CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    selected_date = callback.data.split("_")[1]
    await state.update_data(selected_date=selected_date)
    await safe_edit_text(callback.message, TEXTS[lang]["move_time"], reply_markup=get_time_menu(selected_date, lang))
    await state.set_state(MoveLesson.waiting_for_time)
    await callback.answer()

@router.callback_query(MoveLesson.waiting_for_time, F.data.startswith("time_"))
async def process_move_time(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    new_date, new_time = parts[1], parts[2]
    new_full_time = f"{new_date} {new_time}"
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    lang = data.get("lang", "ru")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT l.tutor_id, s.name, l.lesson_time FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
    await state.clear()
    
    if row:
        tutor_id, s_name, old_time = row
        builder = InlineKeyboardBuilder()
        builder.button(text=TEXTS[lang]["move_allow"], callback_data=f"appr_mv_{lesson_id}_{new_date}_{new_time}")
        builder.button(text=TEXTS[lang]["move_deny"], callback_data=f"rej_mv_{lesson_id}")
        builder.adjust(2)
        try:
            t_lang = await get_user_lang(tutor_id)
            req_text = TEXTS[t_lang]["move_request"].format(name=s_name, old=old_time, new=new_full_time)
            await bot.send_message(tutor_id, req_text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await safe_edit_text(callback.message, TEXTS[lang]["move_sent"], reply_markup=get_student_menu(lang))
        except Exception: pass
    await callback.answer()

@router.callback_query(F.data.startswith("appr_mv_"))
async def approve_move(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    parts = callback.data.split("_")
    lesson_id = int(parts[2])
    new_full_time = f"{parts[3]} {parts[4]}"
    await change_lesson_time(lesson_id, new_full_time)
    await safe_edit_text(callback.message, callback.message.text + f"\n\n{TEXTS[lang]['move_allowed']}")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT s.student_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    s_lang = await get_user_lang(row[0])
                    await bot.send_message(row[0], TEXTS[s_lang]["move_approved_notify"].format(time=new_full_time))
                except: pass
    await callback.answer()

@router.callback_query(F.data.startswith("rej_mv_"))
async def reject_move(callback: CallbackQuery, bot: Bot):
    lang = await get_user_lang(callback.from_user.id)
    lesson_id = int(callback.data.split("_")[2])
    await safe_edit_text(callback.message, callback.message.text + f"\n\n{TEXTS[lang]['move_denied']}")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT s.student_chat_id FROM lessons l JOIN students s ON l.student_id = s.id WHERE l.id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    s_lang = await get_user_lang(row[0])
                    await bot.send_message(row[0], TEXTS[s_lang]["move_rejected_notify"])
                except: pass
    await callback.answer()

@router.callback_query(F.data == "student_info")
async def show_student_info(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    student = await get_student_by_chat_id(callback.from_user.id, "student")
    if not student: return
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    
    text = f"{TEXTS[lang]['student_info_title']}\n\n"
    text += TEXTS[lang]["student_info_text"].format(name=s_name, subject=subject, schedule=text_schedule or '-')
    if sub_total > 1: text += f"🎟 {sub_left}/{sub_total}\n"
    text += f"📈 Karma: {karma}%"
    
    await safe_edit_text(callback.message, text, reply_markup=get_student_menu(lang), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "parent_journal")
async def show_parent_journal(callback: CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    student = await get_student_by_chat_id(callback.from_user.id, "parent")
    if not student: return
    s_id, s_name, tutor_id, subject, text_schedule, sub_left, sub_total, karma = student
    total, paid = await get_parent_journal(s_id)
    debt = total - paid
    details = await get_payment_details(tutor_id)
    
    text = f"{TEXTS[lang]['parent_journal_title'].format(name=s_name)}\n\n"
    text += TEXTS[lang]["parent_journal_text"].format(total=total, paid=paid, debt=debt, karma=karma)
    
    if sub_total > 1:
        green = "🟢" * sub_left
        red = "🔴" * (sub_total - sub_left)
        text += f"\n🎟 {sub_left}/{sub_total}\n{green}{red}\n"
        
    text += f"\n💳 {details}"
    await safe_edit_text(callback.message, text, reply_markup=get_parent_menu(lang), parse_mode="HTML")
    await callback.answer()

# ==========================================
# ВЕБ-СЕРВЕР И ЗАПУСК
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
    
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(check_reminders, 'interval', minutes=1, args=(bot,))
    scheduler.add_job(check_subscriptions, 'interval', hours=1, args=(bot,))
    scheduler.start()
    
    print("Бот запущен! Тестируем...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())