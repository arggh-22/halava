#!/usr/bin/env python3
"""
Тихий скрипт для очистки поля portfolio_photo в таблице workers.
Без запроса подтверждения - для автоматизации.
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
        logging.FileHandler('clear_portfolio_silent.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clear_portfolio_photos_silent():
    """Тихая очистка поля portfolio_photo для всех исполнителей"""
    
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
            logger.warning(f"⚠️ Осталось {remaining_portfolios} исполнителей с портфолио")
        
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при очистке портфолио: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("🚀 Запуск тихого скрипта очистки портфолио...")
    
    success = clear_portfolio_photos_silent()
    
    if success:
        logger.info("[SUCCESS] Очистка портфолио завершена успешно!")
        logger.info("[INFO] Исполнители должны будут заново загрузить фото портфолио")
    else:
        logger.error("[ERROR] Ошибка при очистке портфолио!")
        exit(1)
