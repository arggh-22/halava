"""
Миграция для удаления таблицы subscription_types
Удаляет таблицу subscription_types, так как она больше не используется
"""
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate():
    """Удаляет таблицу subscription_types"""
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        logger.info("Начинаем удаление таблицы subscription_types...")
        
        # Проверяем существование таблицы
        cursor = await conn.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='subscription_types'
        ''')
        table_exists = await cursor.fetchone()
        await cursor.close()
        
        if not table_exists:
            logger.info("Таблица subscription_types не существует, пропускаем удаление")
            return
        
        # Подсчитываем количество записей перед удалением
        cursor = await conn.execute("SELECT COUNT(*) FROM subscription_types")
        count = await cursor.fetchone()
        await cursor.close()
        logger.info(f"Найдено записей в subscription_types: {count[0]}")
        
        # Удаляем таблицу
        logger.info("Удаление таблицы subscription_types...")
        await conn.execute('DROP TABLE IF EXISTS subscription_types')
        await conn.commit()
        logger.info("Таблица subscription_types удалена")
        
        logger.info("✅ Миграция удаления subscription_types завершена успешно!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при миграции: {e}")
        await conn.rollback()
        raise
    finally:
        await conn.close()

if __name__ == '__main__':
    import asyncio
    asyncio.run(migrate())

