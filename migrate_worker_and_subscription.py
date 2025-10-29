"""
Миграция для упрощения таблицы worker_and_subscription
Удаляет поля: subscription_id, guaranteed_orders, subscription_end, unlimited_orders, unlimited_work_types, notification
Оставляет только: id, worker_id, work_type_ids
"""
import aiosqlite
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate():
    """Выполняет миграцию таблицы worker_and_subscription"""
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        logger.info("Начинаем миграцию worker_and_subscription...")
        
        # 1. Создаем временную таблицу с новой структурой
        logger.info("Создание временной таблицы...")
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS worker_and_subscription_new
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL UNIQUE,
                work_type_ids TEXT
            )
        ''')
        await conn.commit()
        logger.info("Временная таблица создана")
        
        # 2. Копируем данные из старой таблицы в новую (только work_type_ids)
        logger.info("Копирование данных...")
        cursor = await conn.execute('''
            SELECT worker_id, work_type_ids 
            FROM worker_and_subscription
        ''')
        old_records = await cursor.fetchall()
        await cursor.close()
        
        migrated_count = 0
        for worker_id, work_type_ids in old_records:
            try:
                await conn.execute('''
                    INSERT INTO worker_and_subscription_new (worker_id, work_type_ids)
                    VALUES (?, ?)
                ''', [worker_id, work_type_ids])
                migrated_count += 1
            except aiosqlite.IntegrityError as e:
                # Если worker_id уже существует, обновляем запись
                logger.warning(f"Дубликат worker_id {worker_id}, обновляем...")
                await conn.execute('''
                    UPDATE worker_and_subscription_new
                    SET work_type_ids = ?
                    WHERE worker_id = ?
                ''', [work_type_ids, worker_id])
        
        await conn.commit()
        logger.info(f"Скопировано {migrated_count} записей")
        
        # 3. Удаляем старую таблицу
        logger.info("Удаление старой таблицы...")
        await conn.execute('DROP TABLE IF EXISTS worker_and_subscription')
        await conn.commit()
        logger.info("Старая таблица удалена")
        
        # 4. Переименовываем новую таблицу
        logger.info("Переименование таблицы...")
        await conn.execute('ALTER TABLE worker_and_subscription_new RENAME TO worker_and_subscription')
        await conn.commit()
        logger.info("Таблица переименована")
        
        # 5. Проверка структуры
        cursor = await conn.execute("PRAGMA table_info(worker_and_subscription)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        logger.info("\nФинальная структура таблицы worker_and_subscription:")
        for col in columns:
            logger.info(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else ''}")
        
        # 6. Проверка количества записей
        cursor = await conn.execute("SELECT COUNT(*) FROM worker_and_subscription")
        count = await cursor.fetchone()
        await cursor.close()
        logger.info(f"\nВсего записей в таблице: {count[0]}")
        
        logger.info("\n✅ Миграция worker_and_subscription завершена успешно!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при миграции: {e}")
        await conn.rollback()
        raise
    finally:
        await conn.close()

if __name__ == '__main__':
    import asyncio
    asyncio.run(migrate())

