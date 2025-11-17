#!/usr/bin/env python3
"""
Скрипт для обнуления контактов и безлимита исполнителя.
При запуске спрашивает tg_id, затем обнуляет поля purchased_contacts и unlimited_contacts_until в таблице workers.
"""
import asyncio
import aiosqlite
import logging
import sys
import os

# Добавляем корневую директорию проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database.models import Worker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def reset_worker_contacts(tg_id: int):
    """Обнуляет контакты и безлимит исполнителя"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    try:
        # Получаем исполнителя по tg_id
        worker = await Worker.get_worker(tg_id=tg_id)
        
        if not worker:
            logger.warning(f"❌ Исполнитель с tg_id={tg_id} не найден!")
            return False
        
        # Показываем текущие значения
        logger.info(f"Текущие значения для исполнителя:")
        logger.info(f"  ID в БД: {worker.id}")
        logger.info(f"  tg_id: {worker.tg_id}")
        logger.info(f"  tg_name: {worker.tg_name}")
        logger.info(f"  purchased_contacts: {worker.purchased_contacts}")
        logger.info(f"  unlimited_contacts_until: {worker.unlimited_contacts_until}")
        
        # Обнуляем контакты и безлимит напрямую через SQL
        logger.info(f"Обнуление контактов и безлимита для исполнителя tg_id={tg_id}...")
        cursor = await conn.execute(
            'UPDATE workers SET purchased_contacts = 0, unlimited_contacts_until = NULL WHERE tg_id = ?',
            [tg_id]
        )
        await conn.commit()
        rows_affected = cursor.rowcount
        await cursor.close()
        
        if rows_affected == 0:
            logger.error(f"❌ Ошибка: не удалось обновить запись")
            return False
        
        logger.info(f"✅ Контакты и безлимит успешно обнулены!")
        
        # Проверяем результат
        cursor = await conn.execute(
            'SELECT purchased_contacts, unlimited_contacts_until FROM workers WHERE tg_id = ?',
            [tg_id]
        )
        record = await cursor.fetchone()
        await cursor.close()
        
        if record:
            purchased_contacts = record[0]
            unlimited_contacts_until = record[1]
            logger.info(f"Проверка результата:")
            logger.info(f"  purchased_contacts: {purchased_contacts}")
            logger.info(f"  unlimited_contacts_until: {unlimited_contacts_until}")
            
            if purchased_contacts == 0 and unlimited_contacts_until is None:
                logger.info(f"✅ Подтверждено: поля успешно обнулены")
                return True
            else:
                logger.error(f"❌ Ошибка: поля не были обнулены")
                return False
        else:
            logger.error(f"❌ Ошибка: не удалось получить обновленные данные")
            return False
        
    except Exception as e:
        logger.error(f"Ошибка при обнулении контактов: {e}", exc_info=True)
        return False
    finally:
        await conn.close()


def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("СКРИПТ ОБНУЛЕНИЯ КОНТАКТОВ И БЕЗЛИМИТА ИСПОЛНИТЕЛЯ")
    logger.info("=" * 60)
    logger.info("")
    
    # Запрашиваем tg_id
    while True:
        try:
            tg_id_input = input("Введите tg_id исполнителя (или 'q' для выхода): ").strip()
            
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
    
    # Обнуляем контакты
    logger.info("")
    success = asyncio.run(reset_worker_contacts(tg_id))
    
    logger.info("")
    if success:
        logger.info("=" * 60)
        logger.info("✅ КОНТАКТЫ И БЕЗЛИМИТ УСПЕШНО ОБНУЛЕНЫ")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("❌ НЕ УДАЛОСЬ ОБНУЛИТЬ КОНТАКТЫ И БЕЗЛИМИТ")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("")
        logger.warning("Скрипт прерван пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)

