"""
Миграция: удаление поля public_id из таблицы customers
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Удаляет поле public_id из таблицы customers"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существует ли поле
        cursor = await conn.execute("PRAGMA table_info(customers)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        column_names = [col[1] for col in columns]
        
        if 'public_id' not in column_names:
            logger.info("Поле public_id уже отсутствует в таблице customers")
            return
        
        # Создаем новую таблицу без поля public_id
        logger.info("Создание новой таблицы customers без поля public_id...")
        
        # Получаем структуру существующей таблицы
        cursor = await conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'")
        old_schema = await cursor.fetchone()
        await cursor.close()
        
        if not old_schema:
            logger.error("Не удалось получить схему таблицы customers")
            return
        
        # Создаем новую таблицу без public_id
        new_schema = old_schema[0].replace(', public_id TEXT', '').replace('public_id TEXT,', '').replace('public_id TEXT', '')
        
        # Переименовываем старую таблицу
        await conn.execute("ALTER TABLE customers RENAME TO customers_old")
        
        # Создаем новую таблицу
        await conn.execute(new_schema)
        
        # Копируем данные (исключая public_id)
        await conn.execute("""
            INSERT INTO customers (id, city_id, tg_id, tg_name, abs_count, access_token, author_name, contact_type, phone_number)
            SELECT id, city_id, tg_id, tg_name, abs_count, access_token, author_name, contact_type, phone_number
            FROM customers_old
        """)
        
        # Удаляем старую таблицу
        await conn.execute("DROP TABLE customers_old")
        
        await conn.commit()
        logger.info("✅ Поле public_id успешно удалено из таблицы customers")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
