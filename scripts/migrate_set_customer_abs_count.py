"""
Скрипт для установки abs_count = 3 для всех заказчиков
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def set_abs_count():
    """Устанавливает abs_count = 3 для всех заказчиков"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем сколько записей будет затронуто
        cursor = await conn.execute('SELECT COUNT(*) FROM customers')
        total_customers = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Найдено {total_customers} заказчиков")
        
        if total_customers == 0:
            logger.info("Нет заказчиков для обновления")
            return
        
        # Устанавливаем abs_count = 3 для всех
        logger.info("Устанавливаем abs_count = 3 для всех заказчиков...")
        cursor = await conn.execute('UPDATE customers SET abs_count = 3')
        rows_affected = cursor.rowcount
        await cursor.close()
        await conn.commit()
        
        logger.info(f"✅ Успешно обновлено {rows_affected} заказчиков")
        
        # Проверяем результат
        cursor = await conn.execute('SELECT COUNT(*) FROM customers WHERE abs_count = 3')
        count_with_3 = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Заказчиков с abs_count = 3: {count_with_3}")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    logger.info("Запуск скрипта: установка abs_count = 3 для всех заказчиков")
    asyncio.run(set_abs_count())
    logger.info("Скрипт завершен")

