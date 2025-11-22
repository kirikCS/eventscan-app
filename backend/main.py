import os
import uuid
import re
import asyncio
from datetime import datetime
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from parser import GET_EVENTS
from RAG import run_RAG

load_dotenv()

MANAGING_POSITIONS = [
    "директор", "генеральный директор", "ceo", "руководитель", 
    "заместитель директора", "вице-президент", "vp", "coo", "cto", "cfo",
    "управляющий", "управляющий директор", "начальник", "шеф",
    "владелец", "собственник", "founder", "основатель"
]

DB_PATH = str(os.getenv("DB_PATH"))
BOT_TOKEN = str(os.getenv("BOT_TOKEN"))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_email = State()
    waiting_for_company = State()
    waiting_for_position = State()
    waiting_for_search_query = State()
    waiting_for_event_query = State()
    waiting_for_employee_selection = State()
    waiting_for_event_name = State()
    waiting_for_single_employee_event = State()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                company_name TEXT NOT NULL,
                position TEXT NOT NULL,
                unique_id TEXT NOT NULL UNIQUE,
                registration_date TEXT NOT NULL,
                username TEXT,
                calendar TEXT DEFAULT ''
            )
        ''')
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN company_name TEXT DEFAULT ''")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE users ADD COLUMN calendar TEXT DEFAULT ''")
        except aiosqlite.OperationalError:
            pass
        
        await db.commit()
    print("Database initialized with company and calendar support")

def is_managing_position(position: str) -> bool:
    position_lower = position.lower().strip()
    return any(manager_pos in position_lower for manager_pos in MANAGING_POSITIONS)

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None

def format_events(events, include_index=True):
    if not events:
        return "Не удалось найти актуальные мероприятия. Попробуйте позже или уточните запрос."
    
    response = "✨ <b>Актуальные IT-мероприятия:</b>\n\n"
    for i, event in enumerate(events[:5], 1):
        index_str = f"{i}. " if include_index else ""
        event_str = f"<b>{index_str}{event.get('Event Name', 'Без названия')}</b>\n"
        start_date = event.get('Start Date', 'Не указана')
        end_date = event.get('End Date', 'Не указана')
        year = event.get('Year', '')
        event_str += f"📅 <b>Даты:</b> {start_date} - {end_date}, {year}\n"
        event_str += f"📍 <b>Место:</b> {event.get('Location', 'Не указано')}\n"
        event_str += f"🔖 <b>Тип:</b> {event.get('Event Type', 'Не указан')}\n"
        description = event.get('Description', 'Нет описания')[:150] + "..." if event.get('Description') else "Нет описания"
        event_str += f"📝 <b>Описание:</b> {description}\n"
        event_str += f"🎤 <b>Спикеры:</b> {event.get('Speakers/Organizers', 'Не указаны')}\n"
        event_str += f"👥 <b>Участники:</b> {event.get('Participants Count', 'Неизвестно')}\n"
        event_str += f"🔖 <b>Категория:</b> {event.get('Category', 'Не указана')}\n\n"
        response += event_str
    
    if include_index:
        response += "\nℹ️ Чтобы получить подробную информацию о мероприятии, используйте <b>Поиск по архиву</b>"
    return response

def format_calendar_events(calendar_str):
    if not calendar_str or calendar_str.strip() == "":
        return "Ваш календарь пуст. Запишитесь на мероприятия!"
    
    events = [event.strip() for event in calendar_str.split(';') if event.strip()]
    if not events:
        return "Ваш календарь пуст. Запишитесь на мероприятия!"
    
    response = "📅 <b>Ваш календарь мероприятий:</b>\n\n"
    for i, event in enumerate(events, 1):
        response += f"{i}. {event}\n"
    
    return response

def format_rag_results(results):
    if not results:
        return "По вашему запросу ничего не найдено в архиве."
    
    response = "📚 <b>Результаты поиска по архиву:</b>\n\n"
    for i, result in enumerate(results[:5], 1):
        if isinstance(result, dict):
            formatted = "\n".join([f"<b>{key}:</b> {value}" for key, value in result.items() if value and value != "N/A"])
            if formatted:
                response += f"{i}. {formatted}\n\n"
        else:
            response += f"{i}. {str(result)}\n\n"
    return response

def get_main_menu(is_manager=False):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔍 Поиск по архиву", callback_data="search_archive")
    keyboard.button(text="🎯 Найти мероприятия", callback_data="find_events")
    
    if is_manager:
        keyboard.button(text="📋 Записать сотрудника", callback_data="register_employee")
    
    keyboard.button(text="Мой календарь", callback_data="view_calendar")
    keyboard.button(text="👤 Мои данные", callback_data="my_data")
    keyboard.adjust(1)
    return keyboard.as_markup()

async def get_user_data(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        user = await cursor.fetchone()
        if user:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, user))
    return None

async def save_user_data(user_id: int, full_name: str, email: str, company_name: str, position: str, username: str = None):
    unique_id = str(uuid.uuid4())
    registration_date = datetime.utcnow().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        exists = await cursor.fetchone()
        
        if exists:
            await db.execute('''
                UPDATE users SET full_name = ?, email = ?, company_name = ?, position = ?, username = ?
                WHERE user_id = ?
            ''', (full_name, email, company_name, position, username, user_id))
        else:
            await db.execute('''
                INSERT INTO users 
                (user_id, full_name, email, company_name, position, unique_id, registration_date, username, calendar)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')
            ''', (user_id, full_name, email, company_name, position, unique_id, registration_date, username))
        
        await db.commit()
        
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        user = await cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, user))

async def get_company_employees(manager_user_id: int):
    manager_data = await get_user_data(manager_user_id)
    if not manager_data:
        return []
    
    company_name = manager_data['company_name']
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT user_id, full_name, position 
            FROM users 
            WHERE company_name = ? 
            AND user_id != ? 
            AND NOT EXISTS (
                SELECT 1 FROM users u2 
                WHERE u2.user_id = users.user_id 
                AND (
                    position LIKE '%директор%' OR 
                    position LIKE '%руководитель%' OR 
                    position LIKE '%начальник%' OR 
                    position LIKE '%управляющий%' OR 
                    position LIKE '%заместитель%' OR 
                    position LIKE '%ceo%' OR 
                    position LIKE '%coo%' OR 
                    position LIKE '%cto%' OR 
                    position LIKE '%cfo%' OR 
                    position LIKE '%vp%'
                )
            )
            ORDER BY full_name
        ''', (company_name, manager_user_id))
        
        employees = await cursor.fetchall()
        return [{"user_id": row[0], "full_name": row[1], "position": row[2]} for row in employees]

async def update_user_calendar(user_id: int, event_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT calendar FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = await cursor.fetchone()
        
        if result:
            current_calendar = result[0] or ""
            events = [e.strip() for e in current_calendar.split(';') if e.strip()]
            if event_name not in events:
                events.append(event_name)
                new_calendar = "; ".join(events)
                
                await db.execute(
                    "UPDATE users SET calendar = ? WHERE user_id = ?",
                    (new_calendar, user_id)
                )
                await db.commit()
                return True
    return False

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    
    if user_data:
        is_manager = is_managing_position(user_data['position'])
        await message.answer(
            f"С возвращением, {user_data['full_name']}! 👋\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu(is_manager)
        )
    else:
        await message.answer(
            "Привет! Я бот для поиска IT-мероприятий 🤖\n\n"
            "Давайте начнем регистрацию. Пожалуйста, введите ваше ФИО:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_full_name)

@dp.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    
    if len(full_name) < 3:
        await message.answer("ФИО слишком короткое. Пожалуйста, введите корректное ФИО (минимум 3 символа):")
        return
    
    await state.update_data(full_name=full_name)
    await message.answer("Отлично! Теперь введите ваш email:")
    await state.set_state(RegistrationStates.waiting_for_email)

@dp.message(RegistrationStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    email = message.text.strip()
    
    if not is_valid_email(email):
        await message.answer("Некорректный email. Пожалуйста, введите правильный email в формате example@domain.com:")
        return
    
    await state.update_data(email=email)
    await message.answer("Отлично! Теперь введите название вашей компании:")
    await state.set_state(RegistrationStates.waiting_for_company)

@dp.message(RegistrationStates.waiting_for_company)
async def process_company(message: Message, state: FSMContext):
    company_name = message.text.strip()
    
    if len(company_name) < 2:
        await message.answer("Название компании слишком короткое. Пожалуйста, введите корректное название (минимум 2 символа):")
        return
    
    await state.update_data(company_name=company_name)
    await message.answer("Отлично! Теперь введите вашу должность:")
    await state.set_state(RegistrationStates.waiting_for_position)

@dp.message(RegistrationStates.waiting_for_position)
async def process_position(message: Message, state: FSMContext):
    position = message.text.strip()
    
    if len(position) < 2:
        await message.answer("Должность слишком короткая. Пожалуйста, введите корректную должность (минимум 2 символа):")
        return
    
    data = await state.get_data()
    full_name = data['full_name']
    email = data['email']
    company_name = data['company_name']
    
    try:
        user_data = await save_user_data(
            user_id=message.from_user.id,
            full_name=full_name,
            email=email,
            company_name=company_name,
            position=position,
            username=message.from_user.username
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении данных: {str(e)}\nПопробуйте еще раз позже.")
        return
    
    await state.clear()
    
    await message.answer(
        f"✅ Регистрация успешно завершена!\n\n"
        f"<b>Ваши данные:</b>\n"
        f"👤 ФИО: {full_name}\n"
        f"📧 Почта: {email}\n"
        f"🏢 Компания: {company_name}\n"
        f"💼 Должность: {position}\n"
        f"🔖 Уникальный ID: <code>{user_data['unique_id']}</code>",
        parse_mode="HTML"
    )
    
    is_manager = is_managing_position(position)
    manager_info = ""
    if is_manager:
        manager_info = "\n\n👑 Вы являетесь руководителем компании!\n" \
                      "Вы можете записывать сотрудников на мероприятия.\n\n"
    
    await message.answer(f"{manager_info}🔍 Подбираю для вас персональные IT-мероприятия...\n(Это может занять до 30 секунд)")
    
    try:
        events = await asyncio.to_thread(GET_EVENTS, position)
        formatted_events = format_events(events)
        
        if len(formatted_events) > 4096:
            for i in range(0, len(formatted_events), 4096):
                await message.answer(
                    formatted_events[i:i+4096],
                    parse_mode="HTML"
                )
        else:
            await message.answer(formatted_events, parse_mode="HTML")
            
    except Exception as e:
        await message.answer(
            f"❌ Произошла ошибка при получении мероприятий: {str(e)}\n"
            "Попробуйте позже или воспользуйтесь поиском по архиву."
        )
    
    await message.answer(
        "🎯 <b>Выберите действие:</b>",
        reply_markup=get_main_menu(is_manager),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "register_employee")
async def register_employee_start(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    
    if not user_data:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await callback_query.message.answer(
            "Для записи сотрудников на мероприятия необходимо зарегистрироваться. Хотите начать регистрацию?",
            reply_markup=keyboard.as_markup()
        )
        return
    
    if not is_managing_position(user_data['position']):
        await callback_query.message.answer(
            "❌ У вас нет прав для записи сотрудников на мероприятия. Эта функция доступна только руководителям компаний."
        )
        return
    
    employees = await get_company_employees(user_id)
    
    if not employees:
        await callback_query.message.answer(
            "❌ В вашей компании нет сотрудников для записи на мероприятия."
        )
        return
    
    keyboard = InlineKeyboardBuilder()
    for employee in employees:
        keyboard.button(
            text=f"{employee['full_name']} ({employee['position']})",
            callback_data=f"select_employee_{employee['user_id']}"
        )
    keyboard.button(text="🏠 Вернуться в меню", callback_data="back_to_menu")
    keyboard.adjust(1)
    
    await callback_query.message.answer(
        "👥 <b>Выберите сотрудника для записи на мероприятие:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_for_employee_selection)

@dp.callback_query(lambda c: c.data.startswith("select_employee_"))
async def select_employee_for_registration(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    employee_id = int(callback_query.data.split("select_employee_")[1])
    employee_data = await get_user_data(employee_id)
    
    if not employee_data:
        await callback_query.message.answer("❌ Сотрудник не найден в базе данных.")
        return
    
    await state.update_data(selected_employee_id=employee_id, selected_employee_name=employee_data['full_name'])
    
    await callback_query.message.answer(
        f"📝 <b>Вы выбрали сотрудника:</b> {employee_data['full_name']}\n\n"
        "Введите название мероприятия, на которое хотите записать сотрудника:",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_single_employee_event)

@dp.message(RegistrationStates.waiting_for_single_employee_event)
async def process_single_employee_event(message: Message, state: FSMContext):
    event_name = message.text.strip()
    
    if len(event_name) < 5:
        await message.answer("Название мероприятия слишком короткое. Пожалуйста, введите полное название (минимум 5 символов):")
        return
    
    data = await state.get_data()
    employee_id = data['selected_employee_id']
    employee_name = data['selected_employee_name']
    
    success = await update_user_calendar(employee_id, event_name)
    
    user_data = await get_user_data(message.from_user.id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    
    if success:
        await message.answer(
            f"✅ Сотрудник <b>{employee_name}</b> успешно записан на мероприятие:\n<b>{event_name}</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ Не удалось записать сотрудника <b>{employee_name}</b> на мероприятие:\n<b>{event_name}</b>",
            parse_mode="HTML"
        )
    
    await state.clear()
    
    await message.answer(
        "🎯 <b>Выберите следующее действие:</b>",
        reply_markup=get_main_menu(is_manager),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "view_calendar")
async def view_calendar(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    
    if not user_data:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await callback_query.message.answer(
            "Для просмотра календаря необходимо зарегистрироваться. Хотите начать регистрацию?",
            reply_markup=keyboard.as_markup()
        )
        return
    
    calendar_str = user_data['calendar']
    formatted_calendar = format_calendar_events(calendar_str)
    
    keyboard = InlineKeyboardBuilder()
    if calendar_str and calendar_str.strip() != "":
        keyboard.button(text="🧹 Очистить календарь", callback_data="clear_calendar")
    keyboard.button(text="🏠 Вернуться в меню", callback_data="back_to_menu")
    keyboard.adjust(1)
    
    await callback_query.message.answer(
        formatted_calendar,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data == "clear_calendar")
async def clear_calendar(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET calendar = '' WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
    
    user_data = await get_user_data(user_id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    
    await callback_query.message.answer(
        "✅ Ваш календарь успешно очищен!",
        reply_markup=get_main_menu(is_manager)
    )

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    
    if user_data:
        is_manager = is_managing_position(user_data['position'])
        await callback_query.message.answer(
            "🎯 <b>Выберите действие:</b>",
            reply_markup=get_main_menu(is_manager),
            parse_mode="HTML"
        )
    else:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await callback_query.message.answer(
            "Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь для доступа к функциям бота.",
            reply_markup=keyboard.as_markup()
        )

@dp.callback_query(lambda c: c.data == "find_events")
async def process_find_events(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    
    if not user_data:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await callback_query.message.answer(
            "Для поиска мероприятий необходимо зарегистрироваться. Хотите начать регистрацию?",
            reply_markup=keyboard.as_markup()
        )
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔍 По моей должности", callback_data=f"search_by_position_{user_data['position']}")
    keyboard.button(text="✏️ Ввести свой запрос", callback_data="search_custom_query")
    keyboard.adjust(1)
    
    await callback_query.message.answer(
        "Выберите способ поиска актуальных мероприятий:",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("search_by_position_"))
async def search_by_position(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    position = callback_query.data.split("search_by_position_")[1]
    
    processing_msg = await callback_query.message.answer(
        f"🔍 Ищу актуальные мероприятия по запросу: <b>{position}</b>\n(Это может занять до 30 секунд)",
        parse_mode="HTML"
    )
    
    try:
        events = await asyncio.to_thread(GET_EVENTS, position)
        formatted_events = format_events(events)
        
        if len(formatted_events) > 4096:
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=processing_msg.message_id)
            for i in range(0, len(formatted_events), 4096):
                await callback_query.message.answer(
                    formatted_events[i:i+4096],
                    parse_mode="HTML"
                )
        else:
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=processing_msg.message_id,
                text=formatted_events,
                parse_mode="HTML"
            )
            
    except Exception as e:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ Произошла ошибка при поиске: {str(e)}\nПопробуйте другой запрос или повторите позже."
        )
    
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    
    await callback_query.message.answer(
        "🎯 <b>Выберите следующее действие:</b>",
        reply_markup=get_main_menu(is_manager),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "search_custom_query")
async def search_custom_query(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer(
        "Введите ключевые слова для поиска актуальных мероприятий:\n"
        "(например: 'AI conference', 'blockchain hackathon', 'web development meetup')",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_event_query)

@dp.message(RegistrationStates.waiting_for_event_query)
async def process_event_query(message: Message, state: FSMContext):
    query = message.text.strip()
    
    if len(query) < 3:
        await message.answer("Поисковый запрос слишком короткий. Пожалуйста, введите минимум 3 символа:")
        return
    
    await state.clear()
    
    processing_msg = await message.answer(
        f"🔍 Ищу актуальные мероприятия по запросу: <b>{query}</b>\n(Это может занять до 30 секунд)",
        parse_mode="HTML"
    )
    
    try:
        events = await asyncio.to_thread(GET_EVENTS, query)
        formatted_events = format_events(events)
        
        if len(formatted_events) > 4096:
            await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
            for i in range(0, len(formatted_events), 4096):
                await message.answer(
                    formatted_events[i:i+4096],
                    parse_mode="HTML"
                )
        else:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                text=formatted_events,
                parse_mode="HTML"
            )
            
    except Exception as e:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ Произошла ошибка при поиске: {str(e)}\nПопробуйте другой запрос или повторите позже."
        )
    
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    
    await message.answer(
        "🎯 <b>Выберите следующее действие:</b>",
        reply_markup=get_main_menu(is_manager),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "search_archive")
async def process_search_archive(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer(
        "Введите ваш поисковый запрос для поиска по архиву мероприятий:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_search_query)

@dp.message(RegistrationStates.waiting_for_search_query)
async def process_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    
    if len(query) < 3:
        await message.answer("Поисковый запрос слишком короткий. Пожалуйста, введите минимум 3 символа:")
        return
    
    await state.clear()
    
    processing_msg = await message.answer("🔍 Ищу информацию в архиве...\n(Это может занять до 20 секунд)")
    
    try:
        results = await asyncio.to_thread(run_RAG, query)
        formatted_results = format_rag_results(results)
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=formatted_results,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ Произошла ошибка при поиске: {str(e)}\nПопробуйте изменить запрос или повторить позже."
        )
    
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    
    await message.answer(
        "🎯 <b>Выберите следующее действие:</b>",
        reply_markup=get_main_menu(is_manager),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "my_data")
async def process_my_data(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user_data = await get_user_data(user_id)
    
    if user_data:
        reg_date = datetime.fromisoformat(user_data['registration_date']).strftime("%d.%m.%Y %H:%M")
        
        response = (
            "<b>Ваши регистрационные данные:</b>\n\n"
            f"👤 ФИО: {user_data['full_name']}\n"
            f"📧 Почта: {user_data['email']}\n"
            f"🏢 Компания: {user_data['company_name']}\n"
            f"💼 Должность: {user_data['position']}\n"
            f"🔖 Уникальный ID: <code>{user_data['unique_id']}</code>\n"
            f"📅 Дата регистрации: {reg_date}\n"
            f"🔖 Username: @{user_data['username'] if user_data['username'] else 'не указан'}"
        )
        
        is_manager = is_managing_position(user_data['position'])
        await callback_query.message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_main_menu(is_manager)
        )
    else:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await callback_query.message.answer(
            "Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь для доступа к функциям бота.",
            reply_markup=keyboard.as_markup()
        )

@dp.callback_query(lambda c: c.data == "start_registration")
async def start_registration(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer(
        "Давайте начнем регистрацию. Пожалуйста, введите ваше ФИО:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_full_name)

@dp.message(Command("mydata"))
async def cmd_mydata(message: Message):
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    
    if user_data:
        reg_date = datetime.fromisoformat(user_data['registration_date']).strftime("%d.%m.%Y %H:%M")
        
        response = (
            "<b>Ваши регистрационные данные:</b>\n\n"
            f"👤 ФИО: {user_data['full_name']}\n"
            f"📧 Почта: {user_data['email']}\n"
            f"🏢 Компания: {user_data['company_name']}\n"
            f"💼 Должность: {user_data['position']}\n"
            f"🔖 Уникальный ID: <code>{user_data['unique_id']}</code>\n"
            f"📅 Дата регистрации: {reg_date}\n"
            f"🔖 Username: @{user_data['username'] if user_data['username'] else 'не указан'}"
        )
        
        is_manager = is_managing_position(user_data['position'])
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_main_menu(is_manager)
        )
    else:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Зарегистрироваться", callback_data="start_registration")
        await message.answer(
            "Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь для доступа к функциям бота.",
            reply_markup=keyboard.as_markup()
        )

@dp.message(Command("reregister"))
async def cmd_reregister(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    
    if user_data:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Подтвердить", callback_data="confirm_reregister")
        keyboard.button(text="❌ Отмена", callback_data="cancel_reregister")
        keyboard.adjust(2)
        
        await message.answer(
            "Вы уверены, что хотите перерегистрироваться? Это удалит ваши текущие данные.",
            reply_markup=keyboard.as_markup()
        )
    else:
        await message.answer(
            "Вы еще не зарегистрированы. Используйте команду /start для регистрации.",
            reply_markup=get_main_menu(False)
        )

@dp.callback_query(lambda c: c.data == "confirm_reregister")
async def confirm_reregister(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM users WHERE user_id = ?",
            (callback_query.from_user.id,)
        )
        await db.commit()
    
    await callback_query.message.answer(
        "Ваши старые данные удалены. Давайте начнем регистрацию заново.\n\nВведите ваше ФИО:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_full_name)

@dp.callback_query(lambda c: c.data == "cancel_reregister")
async def cancel_reregister(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_data = await get_user_data(callback_query.from_user.id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    await callback_query.message.answer(
        "Перерегистрация отменена. Вы можете продолжить использовать бота.",
        reply_markup=get_main_menu(is_manager)
    )

@dp.message()
async def handle_other_messages(message: Message):
    user_data = await get_user_data(message.from_user.id)
    is_manager = is_managing_position(user_data['position']) if user_data else False
    await message.answer(
        "Я бот для поиска IT-мероприятий 🤖\n\n"
        "Пожалуйста, выберите действие из меню ниже:",
        reply_markup=get_main_menu(is_manager)
    )

async def main():
    await init_db()
    print("Бот запущен с поддержкой компаний и календаря...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
