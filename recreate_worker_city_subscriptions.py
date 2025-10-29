"""
Скрипт для удаления и пересоздания таблицы worker_city_subscriptions
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def recreate_worker_city_subscriptions_table():
    """Удаляет старую таблицу и создает новую"""
    database_path = 'app/data/database/database.db'
    
    try:
        conn = await aiosqlite.connect(database_path)
        logger.info("Подключение к базе данных установлено")
        
        # Удаляем старую таблицу
        logger.info("Удаление старой таблицы worker_city_subscriptions...")
        await conn.execute('DROP TABLE IF EXISTS worker_city_subscriptions')
        await conn.commit()
        logger.info("Старая таблица удалена")
        
        # Создаем новую таблицу
        logger.info("Создание новой таблицы worker_city_subscriptions...")
        await conn.execute('''
            CREATE TABLE worker_city_subscriptions
            (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id           INTEGER NOT NULL,
                city_ids            TEXT    NOT NULL,
                subscription_start  TEXT    NOT NULL,
                subscription_end    TEXT    NOT NULL,
                subscription_months INTEGER NOT NULL,
                price               INTEGER NOT NULL,
                active              INTEGER DEFAULT 1,
                purchased_city_count INTEGER NOT NULL
            )
        ''')
        await conn.commit()
        logger.info("Новая таблица создана успешно!")
        
        # Проверяем, что таблица создана
        cursor = await conn.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='worker_city_subscriptions'
        ''')
        result = await cursor.fetchone()
        await cursor.close()
        
        if result:
            logger.info(f"Таблица '{result[0]}' успешно создана!")
            
            # Показываем структуру таблицы
            cursor = await conn.execute("PRAGMA table_info(worker_city_subscriptions)")
            columns = await cursor.fetchall()
            await cursor.close()
            
            logger.info("\nСтруктура таблицы:")
            for col in columns:
                logger.info(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else ''}")
        else:
            logger.error("Ошибка: таблица не найдена после создания!")
        
        await conn.close()
        logger.info("\nГотово! Таблица успешно пересоздана.")
        
    except Exception as e:
        logger.error(f"Ошибка при пересоздании таблицы: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(recreate_worker_city_subscriptions_table())

