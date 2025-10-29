"""
Миграция: удаление поля public_id из таблицы workers
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Удаляет поле public_id из таблицы workers"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существует ли поле
        cursor = await conn.execute("PRAGMA table_info(workers)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        column_names = [col[1] for col in columns]
        
        if 'public_id' not in column_names:
            logger.info("Поле public_id уже отсутствует в таблице workers")
            return
        
        # Создаем новую таблицу без поля public_id
        logger.info("Создание новой таблицы workers без поля public_id...")
        
        # Получаем структуру существующей таблицы
        cursor = await conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workers'")
        old_schema = await cursor.fetchone()
        await cursor.close()
        
        if not old_schema:
            logger.error("Не удалось получить схему таблицы workers")
            return
        
        # Создаем новую таблицу без public_id
        new_schema = old_schema[0].replace(', public_id TEXT', '').replace('public_id TEXT,', '').replace('public_id TEXT', '')
        
        # Переименовываем старую таблицу
        await conn.execute("ALTER TABLE workers RENAME TO workers_old")
        
        # Создаем новую таблицу
        await conn.execute(new_schema)
        
        # Копируем данные (исключая public_id)
        await conn.execute("""
            INSERT INTO workers (id, tg_id, tg_name, city_id, phone_number, confirmed, stars, count_ratings, order_count, order_count_on_week, confirmation_code, ref_code, active, access_token, author_name, individual_entrepreneur, registration_data, profile_photo, profile_name, portfolio_photo, purchased_contacts, unlimited_contacts_until, activity_level, name_violations_count)
            SELECT id, tg_id, tg_name, city_id, phone_number, confirmed, stars, count_ratings, order_count, order_count_on_week, confirmation_code, ref_code, active, access_token, author_name, individual_entrepreneur, registration_data, profile_photo, profile_name, portfolio_photo, purchased_contacts, unlimited_contacts_until, activity_level, name_violations_count
            FROM workers_old
        """)
        
        # Удаляем старую таблицу
        await conn.execute("DROP TABLE workers_old")
        
        await conn.commit()
        logger.info("✅ Поле public_id успешно удалено из таблицы workers")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
