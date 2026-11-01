import aiosqlite

DB_NAME = "repetly.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей (роли)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT
            )
        """)
        # Таблица учеников
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tutor_id INTEGER,
                name TEXT,
                student_chat_id INTEGER,
                parent_chat_id INTEGER
            )
        """)
        await db.commit()

async def set_user_role(user_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, role) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET role = excluded.role
        """, (user_id, role))
        await db.commit()

async def get_user_role(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def add_student(tutor_id: int, name: str):
    """Добавляет ученика и возвращает его уникальный ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO students (tutor_id, name) VALUES (?, ?)", 
            (tutor_id, name)
        )
        await db.commit()
        return cursor.lastrowid # Возвращаем ID нового ученика

async def get_students_by_tutor(tutor_id: int):
    """Получает список всех учеников конкретного репетитора"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name FROM students WHERE tutor_id = ?", (tutor_id,)) as cursor:
            return await cursor.fetchall()

async def bind_student(student_id: int, chat_id: int, is_parent: bool = False):
    """Привязывает Telegram-аккаунт ученика или родителя к записи в базе"""
    async with aiosqlite.connect(DB_NAME) as db:
        if is_parent:
            await db.execute("UPDATE students SET parent_chat_id = ? WHERE id = ?", (chat_id, student_id))
        else:
            await db.execute("UPDATE students SET student_chat_id = ? WHERE id = ?", (chat_id, student_id))
        await db.commit()

async def get_student_by_id(student_id: int):
    """Получает данные ученика по его ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name, tutor_id FROM students WHERE id = ?", (student_id,)) as cursor:
            return await cursor.fetchone()