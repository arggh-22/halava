"""
Миграция: добавление полей contact_type и phone_number в таблицу customers
и установка значения NULL для всех существующих заказчиков
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Добавляет поля contact_type и phone_number в таблицу customers"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существуют ли уже поля
        cursor = await conn.execute("PRAGMA table_info(customers)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        column_names = [col[1] for col in columns]
        contact_type_exists = 'contact_type' in column_names
        phone_number_exists = 'phone_number' in column_names
        
        # Добавляем поле contact_type, если его нет
        if not contact_type_exists:
            logger.info("Добавление поля contact_type в таблицу customers...")
            await conn.execute(
                "ALTER TABLE customers ADD COLUMN contact_type TEXT"
            )
            await conn.commit()
            logger.info("Поле contact_type успешно добавлено")
        else:
            logger.info("Поле contact_type уже существует в таблице customers")
        
        # Добавляем поле phone_number, если его нет
        if not phone_number_exists:
            logger.info("Добавление поля phone_number в таблицу customers...")
            await conn.execute(
                "ALTER TABLE customers ADD COLUMN phone_number TEXT"
            )
            await conn.commit()
            logger.info("Поле phone_number успешно добавлено")
        else:
            logger.info("Поле phone_number уже существует в таблице customers")
        
        # Получаем количество записей для информации
        cursor = await conn.execute("SELECT COUNT(*) FROM customers")
        total_count = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Всего заказчиков в базе: {total_count}")
        logger.info("Поля contact_type и phone_number готовы к использованию (значения NULL по умолчанию)")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())

