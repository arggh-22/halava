"""
Скрипт для обнуления полей profile_photo и portfolio_photo в таблице workers
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_worker_photos():
    """Обнуляет profile_photo и portfolio_photo для всех исполнителей"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Сначала проверяем сколько записей будет затронуто
        cursor = await conn.execute(
            'SELECT COUNT(*) FROM workers WHERE profile_photo IS NOT NULL OR portfolio_photo IS NOT NULL'
        )
        count_before = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Найдено {count_before} исполнителей с фото")
        
        if count_before == 0:
            logger.info("Нет исполнителей с фото для обнуления")
            return
        
        # Подтверждение
        logger.info("Начинаем обнуление profile_photo и portfolio_photo...")
        
        # Обнуляем оба поля
        cursor = await conn.execute(
            'UPDATE workers SET profile_photo = NULL, portfolio_photo = NULL'
        )
        rows_affected = cursor.rowcount
        await cursor.close()
        await conn.commit()
        
        logger.info(f"Успешно обнулено фото для {rows_affected} исполнителей")
        
        # Проверяем результат
        cursor = await conn.execute(
            'SELECT COUNT(*) FROM workers WHERE profile_photo IS NOT NULL OR portfolio_photo IS NOT NULL'
        )
        count_after = (await cursor.fetchone())[0]
        await cursor.close()
        
        if count_after == 0:
            logger.info("✅ Все фото успешно обнулены")
        else:
            logger.warning(f"⚠️ Осталось {count_after} записей с фото (возможно NULL не установился)")
        
    except Exception as e:
        logger.error(f"Ошибка при обнулении фото: {e}")
        raise
    finally:
        await conn.close()


async def clear_worker_photos_by_ids(worker_ids: list = None):
    """
    Обнуляет profile_photo и portfolio_photo для конкретных исполнителей
    
    Args:
        worker_ids: Список ID исполнителей (если None - обнуляет всех)
    """
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        if worker_ids:
            # Обнуляем для конкретных ID
            placeholders = ','.join('?' * len(worker_ids))
            query = f'UPDATE workers SET profile_photo = NULL, portfolio_photo = NULL WHERE id IN ({placeholders})'
            cursor = await conn.execute(query, worker_ids)
            rows_affected = cursor.rowcount
            await cursor.close()
            await conn.commit()
            logger.info(f"Обнулено фото для {rows_affected} исполнителей с ID: {worker_ids}")
        else:
            # Обнуляем всех
            await clear_worker_photos()
            
    except Exception as e:
        logger.error(f"Ошибка при обнулении фото: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    import sys
    
    # Если переданы ID через аргументы командной строки
    if len(sys.argv) > 1:
        worker_ids = [int(x) for x in sys.argv[1:]]
        logger.info(f"Обнуление фото для конкретных исполнителей: {worker_ids}")
        asyncio.run(clear_worker_photos_by_ids(worker_ids))
    else:
        # Обнуляем всех
        logger.info("Обнуление фото для всех исполнителей")
        asyncio.run(clear_worker_photos())

