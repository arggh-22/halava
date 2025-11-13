#!/usr/bin/env python3
"""
Скрипт для обновления таблицы info.
Удаляет все существующие записи и создает новые согласно указанным данным.
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def update_info_table():
    """Удаляет все записи из таблицы info и создает новые"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем текущее количество записей
        cursor = await conn.execute('SELECT COUNT(*) FROM info')
        total_records = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Найдено {total_records} записей в таблице info")
        
        # Удаляем все существующие записи
        logger.info("Удаление всех записей из таблицы info...")
        cursor = await conn.execute('DELETE FROM info')
        rows_deleted = cursor.rowcount
        await cursor.close()
        await conn.commit()
        
        logger.info(f"✅ Удалено {rows_deleted} записей")
        
        # Данные для вставки (из скриншота)
        new_records = [
            'app/data/database/WhatsApp.jpg',
            'app/data/database/info/for_customers.txt',
            'app/data/database/info/for_workers.txt',
            'app/data/database/info/status_worker.txt',
            'app/data/database/info/rating.txt',
        ]
        
        # Вставляем новые записи
        logger.info(f"Вставка {len(new_records)} новых записей...")
        for text_path in new_records:
            cursor = await conn.execute('INSERT INTO info (text_path) VALUES (?)', [text_path])
            await cursor.close()
            logger.info(f"  ✓ Добавлена запись: {text_path}")
        
        await conn.commit()
        
        # Проверяем результат
        cursor = await conn.execute('SELECT * FROM info ORDER BY id')
        records = await cursor.fetchall()
        await cursor.close()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("РЕЗУЛЬТАТ:")
        logger.info("=" * 60)
        for record in records:
            logger.info(f"  id: {record[0]}, text_path: {record[1]}")
        logger.info("=" * 60)
        logger.info(f"✅ Всего записей в таблице: {len(records)}")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("СКРИПТ ОБНОВЛЕНИЯ ТАБЛИЦЫ INFO")
    logger.info("=" * 60)
    logger.warning("ВНИМАНИЕ: Этот скрипт удалит все существующие записи!")
    logger.info("")
    
    try:
        asyncio.run(update_info_table())
        logger.info("")
        logger.info("✅ Скрипт успешно завершен")
    except KeyboardInterrupt:
        logger.info("")
        logger.warning("Скрипт прерван пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)

