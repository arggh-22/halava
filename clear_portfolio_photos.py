#!/usr/bin/env python3
"""
Скрипт для очистки поля portfolio_photo в таблице workers.
Устанавливает NULL для всех исполнителей, чтобы они заново загрузили фото портфолио.
"""

import os
import sqlite3
import shutil
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clear_portfolio.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clear_portfolio_photos():
    """Очищает поле portfolio_photo для всех исполнителей"""
    
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
        # Получаем количество исполнителей с портфолио
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''")
        workers_with_portfolio = cursor.fetchone()[0]
        
        logger.info(f"Найдено {workers_with_portfolio} исполнителей с портфолио")
        
        if workers_with_portfolio == 0:
            logger.info("Нет исполнителей с портфолио для очистки")
            return True
        
        # Очищаем поле portfolio_photo для всех исполнителей
        cursor.execute("UPDATE workers SET portfolio_photo = NULL")
        affected_rows = cursor.rowcount
        
        # Подтверждаем изменения
        conn.commit()
        
        logger.info(f"[SUCCESS] Поле portfolio_photo очищено для {affected_rows} исполнителей")
        
        # Проверяем результат
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''")
        remaining_portfolios = cursor.fetchone()[0]
        
        if remaining_portfolios == 0:
            logger.info("[SUCCESS] Очистка завершена успешно - все поля portfolio_photo установлены в NULL")
        else:
            logger.warning(f"[WARNING] Осталось {remaining_portfolios} исполнителей с портфолио")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при очистке портфолио: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def show_portfolio_statistics():
    """Показывает статистику по портфолио"""
    
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
        
        # Исполнители с портфолио
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''")
        workers_with_portfolio = cursor.fetchone()[0]
        
        # Исполнители без портфолио
        workers_without_portfolio = total_workers - workers_with_portfolio
        
        logger.info("[STATS] Статистика портфолио:")
        logger.info(f"  Всего исполнителей: {total_workers}")
        logger.info(f"  С портфолио: {workers_with_portfolio}")
        logger.info(f"  Без портфолио: {workers_without_portfolio}")
        
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
    print("1. Удалит ВСЕ данные портфолио из базы данных")
    print("2. Исполнители должны будут заново загрузить фото")
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
    logger.info("🚀 Запуск скрипта очистки портфолио...")
    
    # Показываем текущую статистику
    show_portfolio_statistics()
    
    # Запрашиваем подтверждение
    if not confirm_action():
        logger.info("[CANCELLED] Операция отменена пользователем")
        exit(0)
    
    # Выполняем очистку
    success = clear_portfolio_photos()
    
    if success:
        logger.info("[SUCCESS] Очистка портфолио завершена успешно!")
        logger.info("[INFO] Исполнители должны будут заново загрузить фото портфолио")
        
        # Показываем финальную статистику
        print("\n" + "="*60)
        print("ФИНАЛЬНАЯ СТАТИСТИКА:")
        print("="*60)
        show_portfolio_statistics()
    else:
        logger.error("[ERROR] Ошибка при очистке портфолио!")
        logger.error("[INFO] Резервная копия базы данных сохранена")
        exit(1)
