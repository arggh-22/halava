#!/usr/bin/env python3
"""
Скрипт для проверки и обнуления невалидных profile_name исполнителей.
Проверяет соответствие требованиям:
- Только русские буквы (без цифр, латиницы и символов, кроме пробелов и дефиса)
- Максимум 15 символов
- Без цифр и символов

Если profile_name не соответствует требованиям, обнуляет его (устанавливает NULL).
"""

import os
import sqlite3
import shutil
import logging
import re
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('validate_worker_names.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы из требований
MAX_NAME_LENGTH = 15
RUSSIAN_PATTERN = r'^[А-Яа-яЁё\s\-]+$'


def is_valid_profile_name(name: str) -> bool:
    """
    Проверяет соответствие имени требованиям:
    - Только русские буквы (без цифр, латиницы и символов, кроме пробелов и дефиса)
    - Максимум 15 символов
    - Без цифр и символов
    """
    if not name or not name.strip():
        return False
    
    name = name.strip()
    
    # Проверка длины
    if len(name) > MAX_NAME_LENGTH:
        return False
    
    # Проверка на только русские буквы, пробелы и дефис
    if not re.match(RUSSIAN_PATTERN, name):
        return False
    
    # Проверка на цифры (дополнительная проверка)
    if re.search(r'\d', name):
        return False
    
    # Проверка на латиницу (дополнительная проверка)
    if re.search(r'[A-Za-z]', name):
        return False
    
    return True


def validate_and_clear_worker_names():
    """Проверяет и обнуляет невалидные profile_name исполнителей"""
    
    # Подключаемся к базе данных
    db_path = 'app/data/database/database.db'
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return False
    
    # Создаем резервную копию базы данных
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f'{db_path}.backup_{timestamp}'
    
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"Создана резервная копия: {backup_path}")
    except Exception as e:
        logger.error(f"Ошибка создания резервной копии: {e}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Получаем всех исполнителей с profile_name
        cursor.execute("""
            SELECT id, tg_id, profile_name, tg_name 
            FROM workers 
            WHERE profile_name IS NOT NULL AND profile_name != ''
        """)
        workers = cursor.fetchall()
        
        total_workers = len(workers)
        logger.info(f"Найдено {total_workers} исполнителей с profile_name")
        
        if total_workers == 0:
            logger.info("Нет исполнителей с profile_name для проверки")
            return True
        
        # Статистика
        valid_count = 0
        invalid_count = 0
        cleared_count = 0
        invalid_names = []
        
        # Проверяем каждого исполнителя
        for worker_id, tg_id, profile_name, tg_name in workers:
            if is_valid_profile_name(profile_name):
                valid_count += 1
            else:
                invalid_count += 1
                invalid_names.append({
                    'id': worker_id,
                    'tg_id': tg_id,
                    'profile_name': profile_name,
                    'tg_name': tg_name
                })
                
                # Обнуляем невалидное имя
                cursor.execute(
                    "UPDATE workers SET profile_name = NULL WHERE id = ?",
                    [worker_id]
                )
                cleared_count += 1
                logger.debug(f"Обнулено profile_name для исполнителя ID={worker_id}, tg_id={tg_id}, имя='{profile_name}'")
        
        # Подтверждаем изменения
        conn.commit()
        
        # Выводим статистику
        logger.info("=" * 60)
        logger.info("РЕЗУЛЬТАТЫ ПРОВЕРКИ:")
        logger.info("=" * 60)
        logger.info(f"Всего проверено: {total_workers}")
        logger.info(f"Валидных имен: {valid_count}")
        logger.info(f"Невалидных имен: {invalid_count}")
        logger.info(f"Обнулено имен: {cleared_count}")
        logger.info("=" * 60)
        
        # Выводим примеры невалидных имен (первые 10)
        if invalid_names:
            logger.info("\nПримеры невалидных имен (первые 10):")
            for i, worker in enumerate(invalid_names[:10], 1):
                logger.info(f"  {i}. ID={worker['id']}, tg_id={worker['tg_id']}, "
                          f"profile_name='{worker['profile_name']}', tg_name='{worker['tg_name']}'")
            if len(invalid_names) > 10:
                logger.info(f"  ... и еще {len(invalid_names) - 10} невалидных имен")
        
        # Проверяем результат
        cursor.execute("SELECT COUNT(*) FROM workers WHERE profile_name IS NOT NULL AND profile_name != ''")
        remaining_names = cursor.fetchone()[0]
        
        logger.info(f"\nОсталось исполнителей с profile_name: {remaining_names}")
        
        if remaining_names == valid_count:
            logger.info("[SUCCESS] Проверка завершена успешно - все невалидные имена обнулены")
        else:
            logger.warning(f"[WARNING] Несоответствие: осталось {remaining_names}, ожидалось {valid_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при проверке имен: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()


def show_name_statistics():
    """Показывает статистику по именам исполнителей"""
    
    db_path = 'app/data/database/database.db'
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Общее количество исполнителей
        cursor.execute("SELECT COUNT(*) FROM workers")
        total_workers = cursor.fetchone()[0]
        
        # Исполнители с profile_name
        cursor.execute("SELECT COUNT(*) FROM workers WHERE profile_name IS NOT NULL AND profile_name != ''")
        workers_with_name = cursor.fetchone()[0]
        
        # Исполнители без profile_name
        workers_without_name = total_workers - workers_with_name
        
        logger.info("[STATS] Статистика имен исполнителей:")
        logger.info(f"  Всего исполнителей: {total_workers}")
        logger.info(f"  С profile_name: {workers_with_name}")
        logger.info(f"  Без profile_name: {workers_without_name}")
        
        # Проверяем валидность существующих имен
        if workers_with_name > 0:
            cursor.execute("""
                SELECT id, profile_name 
                FROM workers 
                WHERE profile_name IS NOT NULL AND profile_name != ''
            """)
            names = cursor.fetchall()
            
            valid = 0
            invalid = 0
            for worker_id, profile_name in names:
                if is_valid_profile_name(profile_name):
                    valid += 1
                else:
                    invalid += 1
            
            logger.info(f"  Валидных имен: {valid}")
            logger.info(f"  Невалидных имен: {invalid}")
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
    finally:
        conn.close()


def confirm_action():
    """Запрашивает подтверждение у пользователя"""
    
    print("\n" + "="*60)
    print("WARNING! ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!")
    print("="*60)
    print("Этот скрипт:")
    print("1. Проверит все profile_name исполнителей на соответствие требованиям:")
    print("   - Только русские буквы (без цифр, латиницы и символов)")
    print("   - Максимум 15 символов")
    print("2. Обнулит (установит NULL) все невалидные имена")
    print("3. Создаст резервную копию базы данных")
    print("="*60)
    
    while True:
        response = input("\nПродолжить? (yes/no): ").lower().strip()
        if response in ['yes', 'y', 'да', 'д']:
            return True
        elif response in ['no', 'n', 'нет', 'н']:
            return False
        else:
            print("Пожалуйста, введите 'yes' или 'no'")


if __name__ == "__main__":
    logger.info("🚀 Запуск скрипта проверки и обнуления невалидных имен исполнителей...")
    
    # Показываем текущую статистику
    show_name_statistics()
    
    # Запрашиваем подтверждение
    if not confirm_action():
        logger.info("[CANCELLED] Операция отменена пользователем")
        exit(0)
    
    # Выполняем проверку и обнуление
    success = validate_and_clear_worker_names()
    
    if success:
        logger.info("[SUCCESS] Проверка и обнуление имен завершены успешно!")
        logger.info("[INFO] Исполнители с обнуленными именами должны будут указать новое имя")
        
        # Показываем финальную статистику
        print("\n" + "="*60)
        print("ФИНАЛЬНАЯ СТАТИСТИКА:")
        print("="*60)
        show_name_statistics()
    else:
        logger.error("[ERROR] Ошибка при проверке и обнулении имен!")
        logger.error("[INFO] Резервная копия базы данных сохранена")
        exit(1)


