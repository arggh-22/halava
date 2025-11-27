"""
Миграция: пересоздание таблицы work_types
1. Читает записи из reference БД (app/data/database/database.db)
2. Удаляет таблицу в целевой БД (database.db)
3. Создает таблицу заново
4. Вставляет все записи из reference БД 1 в 1
"""
import asyncio
import aiosqlite
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к reference БД (откуда берем записи)
REFERENCE_DB = 'app/data/database/database.db'
# Путь к целевой БД (куда вставляем записи)
TARGET_DB = 'database.db'


async def migrate():
    """Пересоздает таблицу work_types, копируя данные из reference БД"""
    
    # Проверяем существование reference БД
    if not os.path.exists(REFERENCE_DB):
        logger.error(f"Reference БД не найдена: {REFERENCE_DB}")
        logger.error("Не могу продолжить миграцию без исходных данных")
        return
    
    logger.info(f"Шаг 1: Подключение к reference БД: {REFERENCE_DB}")
    # Читаем данные из reference БД
    ref_conn = await aiosqlite.connect(REFERENCE_DB)
    try:
        # Проверяем существование таблицы в reference БД
        cursor = await ref_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='work_types'")
        ref_table_exists = await cursor.fetchone()
        await cursor.close()
        
        if not ref_table_exists:
            logger.error(f"Таблица work_types не найдена в reference БД: {REFERENCE_DB}")
            return
        
        # Получаем информацию о колонках в reference БД
        cursor = await ref_conn.execute("PRAGMA table_info(work_types)")
        ref_columns_info = await cursor.fetchall()
        await cursor.close()
        
        logger.info(f"Структура таблицы work_types в reference БД: {len(ref_columns_info)} колонок")
        for col in ref_columns_info:
            logger.info(f"  - {col[1]} ({col[2]})")
        
        # Получаем все записи из reference БД
        logger.info("Шаг 2: Чтение всех записей из reference БД...")
        cursor = await ref_conn.execute("SELECT * FROM work_types ORDER BY id")
        all_ref_records = await cursor.fetchall()
        await cursor.close()
        
        # Сохраняем данные
        num_columns = len(ref_columns_info)
        reference_data = []
        
        for record in all_ref_records:
            if num_columns >= 4:
                # id, work_type, template, template_photo
                reference_data.append({
                    'id': record[0],
                    'work_type': record[1],
                    'template': record[2] if len(record) > 2 else None,
                    'template_photo': record[3] if len(record) > 3 else None
                })
            elif num_columns == 2:
                # Только id и work_type (старая структура)
                reference_data.append({
                    'id': record[0],
                    'work_type': record[1],
                    'template': None,
                    'template_photo': None
                })
        
        logger.info(f"Прочитано {len(reference_data)} записей из reference БД")
        
        # Выводим информацию о прочитанных данных
        for item in reference_data:
            logger.debug(f"  ID: {item['id']}, work_type: {item['work_type']}, "
                        f"template: {item['template']}, template_photo: {item['template_photo']}")
        
    finally:
        await ref_conn.close()
    
    # Теперь работаем с целевой БД
    logger.info(f"Шаг 3: Подключение к целевой БД: {TARGET_DB}")
    conn = await aiosqlite.connect(TARGET_DB)
    try:
        # Шаг 4: Удаляем таблицу в целевой БД
        logger.info("Шаг 4: Удаление таблицы work_types в целевой БД...")
        await conn.execute("DROP TABLE IF EXISTS work_types")
        await conn.commit()
        logger.info("Таблица work_types успешно удалена")
        
        # Шаг 5: Создаем таблицу заново
        logger.info("Шаг 5: Создание новой таблицы work_types...")
        await _create_work_types_table(conn)
        logger.info("Таблица work_types успешно создана")
        
        # Шаг 6: Вставляем все данные из reference БД с сохранением оригинальных ID
        logger.info(f"Шаг 6: Вставка {len(reference_data)} записей из reference БД...")
        restored_count = 0
        max_id = 0
        
        for item in reference_data:
            try:
                # Вставляем запись со всеми полями, включая оригинальный ID
                cursor = await conn.execute(
                    "INSERT INTO work_types (id, work_type, template, template_photo) VALUES (?, ?, ?, ?)",
                    (item['id'], item['work_type'], item['template'], item['template_photo'])
                )
                await cursor.close()
                restored_count += 1
                max_id = max(max_id, item['id'])
                logger.debug(f"Восстановлена запись: ID={item['id']}, work_type='{item['work_type']}'")
            except Exception as e:
                # Если не удалось вставить с оригинальным id, пробуем без id
                logger.warning(f"Не удалось вставить запись с id={item['id']} (work_type='{item['work_type']}'): {e}. Пробуем без id...")
                try:
                    cursor = await conn.execute(
                        "INSERT INTO work_types (work_type, template, template_photo) VALUES (?, ?, ?)",
                        (item['work_type'], item['template'], item['template_photo'])
                    )
                    new_id = cursor.lastrowid
                    await cursor.close()
                    restored_count += 1
                    max_id = max(max_id, new_id)
                    logger.warning(f"Запись восстановлена с новым id={new_id} вместо {item['id']}. work_type: {item['work_type']}")
                except Exception as e2:
                    logger.error(f"Не удалось вставить запись work_type='{item['work_type']}': {e2}")
        
        await conn.commit()
        
        # Обновляем sqlite_sequence для правильной работы автоинкремента в будущем
        if max_id > 0:
            await conn.execute("DELETE FROM sqlite_sequence WHERE name='work_types'")
            await conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('work_types', ?)", (max_id,))
            await conn.commit()
            logger.info(f"Обновлен sqlite_sequence для work_types: установлено значение {max_id}")
        
        logger.info(f"Успешно вставлено {restored_count} из {len(reference_data)} записей из reference БД")
        
        # Проверяем результат
        cursor = await conn.execute("SELECT COUNT(*) FROM work_types")
        final_count = (await cursor.fetchone())[0]
        await cursor.close()
        logger.info(f"Итоговое количество записей в таблице: {final_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()


async def _create_work_types_table(conn):
    """Создает таблицу work_types с правильной структурой"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS work_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_type TEXT NOT NULL,
            template TEXT,
            template_photo TEXT
        )
    """)
    await conn.commit()


if __name__ == "__main__":
    asyncio.run(migrate())

