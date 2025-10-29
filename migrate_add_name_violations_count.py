"""
Миграция: добавление поля name_violations_count в таблицу workers
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Добавляет поле name_violations_count в таблицу workers"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существует ли уже поле
        cursor = await conn.execute("PRAGMA table_info(workers)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        column_names = [col[1] for col in columns]
        
        if 'name_violations_count' in column_names:
            logger.info("Поле name_violations_count уже существует в таблице workers")
            return
        
        # Добавляем поле
        logger.info("Добавление поля name_violations_count в таблицу workers...")
        await conn.execute(
            "ALTER TABLE workers ADD COLUMN name_violations_count INTEGER DEFAULT 0"
        )
        await conn.commit()
        logger.info("Поле name_violations_count успешно добавлено")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())

