"""
Миграция: добавление полей purchased_contacts, unlimited_contacts_until, 
activity_level и name_violations_count в таблицу workers
и установка значений по умолчанию для всех существующих исполнителей
"""
import asyncio
import aiosqlite
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Добавляет поля purchased_contacts, unlimited_contacts_until, activity_level и name_violations_count 
    в таблицу workers и устанавливает значения по умолчанию для всех исполнителей"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существуют ли уже поля
        cursor = await conn.execute("PRAGMA table_info(workers)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        column_names = [col[1] for col in columns]
        
        # Поля для добавления с их типами и значениями по умолчанию
        fields_to_add = [
            ('purchased_contacts', 'INTEGER', 0),
            ('unlimited_contacts_until', 'TEXT', None),
            ('activity_level', 'INTEGER', 100),
            ('name_violations_count', 'INTEGER', 0)
        ]
        
        added_fields = []
        
        # Добавляем каждое поле, если его нет
        for field_name, field_type, default_value in fields_to_add:
            if field_name not in column_names:
                logger.info(f"Добавление поля {field_name} в таблицу workers...")
                if default_value is not None:
                    await conn.execute(
                        f"ALTER TABLE workers ADD COLUMN {field_name} {field_type} DEFAULT {default_value}"
                    )
                else:
                    await conn.execute(
                        f"ALTER TABLE workers ADD COLUMN {field_name} {field_type}"
                    )
                await conn.commit()
                logger.info(f"Поле {field_name} успешно добавлено")
                added_fields.append(field_name)
            else:
                logger.info(f"Поле {field_name} уже существует в таблице workers")
        
        # Обновляем все записи исполнителей, устанавливая значения по умолчанию
        logger.info("Обновление всех записей исполнителей...")
        
        # Сначала получаем количество записей
        cursor = await conn.execute("SELECT COUNT(*) FROM workers")
        total_count = (await cursor.fetchone())[0]
        await cursor.close()
        
        logger.info(f"Найдено исполнителей для обновления: {total_count}")
        
        # Обновляем все записи, устанавливая значения по умолчанию
        if total_count > 0:
            # Формируем UPDATE запрос для всех полей
            update_parts = []
            # purchased_contacts = 0 если NULL
            update_parts.append("purchased_contacts = COALESCE(purchased_contacts, 0)")
            # unlimited_contacts_until остается NULL (не обновляем)
            # activity_level = 100 если NULL
            update_parts.append("activity_level = COALESCE(activity_level, 100)")
            # name_violations_count = 0 если NULL
            update_parts.append("name_violations_count = COALESCE(name_violations_count, 0)")
            
            update_query = f"UPDATE workers SET {', '.join(update_parts)}"
            cursor = await conn.execute(update_query)
            rows_updated = cursor.rowcount
            await conn.commit()
            await cursor.close()
            logger.info(f"Успешно обновлено {rows_updated} записей исполнителей.")
            logger.info("Установлены значения: purchased_contacts=0, activity_level=100, name_violations_count=0")
        else:
            logger.info("Нет записей для обновления")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())

