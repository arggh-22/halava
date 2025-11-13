#!/usr/bin/env python3
"""
Скрипт для добавления администратора в таблицу admins.
При запуске спрашивает tg_id и tg_name, затем добавляет запись в БД.
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


async def add_admin(tg_id: int, tg_name: str = None):
    """Добавляет администратора в таблицу admins"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Проверяем, существует ли уже админ с таким tg_id
        cursor = await conn.execute('SELECT * FROM admins WHERE tg_id = ?', [tg_id])
        existing = await cursor.fetchone()
        await cursor.close()
        
        if existing:
            logger.warning(f"❌ Администратор с tg_id={tg_id} уже существует!")
            logger.info(f"  ID: {existing[0]}, tg_id: {existing[1]}, tg_name: {existing[2]}")
            return False
        
        # Если tg_name не указан, используем значение по умолчанию
        if not tg_name:
            tg_name = f"Admin_{tg_id}"
        
        # Добавляем нового админа
        logger.info(f"Добавление администратора: tg_id={tg_id}, tg_name={tg_name}...")
        cursor = await conn.execute(
            'INSERT INTO admins (tg_id, tg_name) VALUES (?, ?)',
            [tg_id, tg_name]
        )
        await conn.commit()
        admin_id = cursor.lastrowid
        await cursor.close()
        
        logger.info(f"✅ Администратор успешно добавлен!")
        logger.info(f"  ID в БД: {admin_id}")
        logger.info(f"  tg_id: {tg_id}")
        logger.info(f"  tg_name: {tg_name}")
        
        # Проверяем результат
        cursor = await conn.execute('SELECT * FROM admins WHERE id = ?', [admin_id])
        record = await cursor.fetchone()
        await cursor.close()
        
        if record:
            logger.info(f"✅ Запись подтверждена в БД")
            return True
        else:
            logger.error(f"❌ Ошибка: запись не найдена после добавления")
            return False
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора: {e}")
        raise
    finally:
        await conn.close()


async def list_all_admins():
    """Показывает список всех администраторов"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        cursor = await conn.execute('SELECT * FROM admins ORDER BY id')
        records = await cursor.fetchall()
        await cursor.close()
        
        if records:
            logger.info("=" * 60)
            logger.info("СПИСОК ВСЕХ АДМИНИСТРАТОРОВ:")
            logger.info("=" * 60)
            for record in records:
                logger.info(f"  ID: {record[0]}, tg_id: {record[1]}, tg_name: {record[2]}, "
                           f"deleted_abs: {record[3]}, done_abs: {record[4]}, order_price: {record[5]}")
            logger.info("=" * 60)
            logger.info(f"Всего администраторов: {len(records)}")
        else:
            logger.info("В таблице admins нет записей")
        
        return records
    except Exception as e:
        logger.error(f"Ошибка при получении списка администраторов: {e}")
        raise
    finally:
        await conn.close()


def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("СКРИПТ ДОБАВЛЕНИЯ АДМИНИСТРАТОРА")
    logger.info("=" * 60)
    
    # Показываем текущий список админов
    logger.info("")
    logger.info("Текущие администраторы:")
    asyncio.run(list_all_admins())
    logger.info("")
    
    # Запрашиваем tg_id
    while True:
        try:
            tg_id_input = input("Введите tg_id администратора (или 'q' для выхода): ").strip()
            
            if tg_id_input.lower() in ['q', 'quit', 'exit', 'выход']:
                logger.info("Выход из скрипта")
                return
            
            tg_id = int(tg_id_input)
            break
        except ValueError:
            logger.error("❌ Неверный формат. Введите число или 'q' для выхода.")
        except KeyboardInterrupt:
            logger.info("")
            logger.info("Скрипт прерван пользователем")
            return
    
    # Запрашиваем tg_name (опционально)
    tg_name_input = input("Введите имя администратора (или нажмите Enter для значения по умолчанию): ").strip()
    tg_name = tg_name_input if tg_name_input else None
    
    # Добавляем администратора
    logger.info("")
    success = asyncio.run(add_admin(tg_id, tg_name))
    
    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ АДМИНИСТРАТОР УСПЕШНО ДОБАВЛЕН")
        logger.info("=" * 60)
        
        # Показываем обновленный список
        logger.info("")
        logger.info("Обновленный список администраторов:")
        asyncio.run(list_all_admins())
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("❌ НЕ УДАЛОСЬ ДОБАВИТЬ АДМИНИСТРАТОРА")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("")
        logger.warning("Скрипт прерван пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)

