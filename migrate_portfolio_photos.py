#!/usr/bin/env python3
"""
Скрипт для миграции всех фото портфолио в правильную структуру папок.
Перемещает фото из общей папки app/data/photo/ в папки пользователей:
app/data/photo/{user_id}/portfolio/
"""

import os
import json
import sqlite3
import shutil
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('portfolio_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def migrate_all_portfolios():
    """Мигрирует все фото портфолио в правильную структуру папок"""
    
    # Подключаемся к базе данных
    db_path = 'app/data/database/database.db'
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Получаем всех исполнителей с портфолио
        cursor.execute("SELECT id, tg_id, portfolio_photo FROM workers WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''")
        workers = cursor.fetchall()
        
        logger.info(f"Найдено {len(workers)} исполнителей с портфолио")
        
        migrated_count = 0
        error_count = 0
        
        for worker_id, tg_id, portfolio_json in workers:
            try:
                # Парсим JSON портфолио
                portfolio_dict = json.loads(portfolio_json)
                if not portfolio_dict:
                    continue
                
                logger.info(f"Миграция портфолио исполнителя {tg_id} (ID: {worker_id})")
                
                # Создаем папку для портфолио пользователя
                portfolio_dir = f'app/data/photo/{tg_id}/portfolio'
                os.makedirs(portfolio_dir, exist_ok=True)
                
                new_portfolio = {}
                files_moved = 0
                
                for key, old_path in portfolio_dict.items():
                    if os.path.exists(old_path):
                        # Создаем новое имя файла
                        new_filename = f'{key}.jpg'
                        new_path = os.path.join(portfolio_dir, new_filename)
                        
                        try:
                            # Перемещаем файл
                            shutil.move(old_path, new_path)
                            new_portfolio[key] = new_path
                            files_moved += 1
                            logger.info(f"  Файл перемещен: {old_path} -> {new_path}")
                        except Exception as e:
                            logger.error(f"  Ошибка перемещения файла {old_path}: {e}")
                            # Если не удалось переместить, оставляем старый путь
                            new_portfolio[key] = old_path
                    else:
                        logger.warning(f"  Файл не найден: {old_path}")
                        # Если файл не существует, не добавляем его в новый словарь
                
                # Обновляем портфолио в базе данных
                if new_portfolio:
                    new_portfolio_json = json.dumps(new_portfolio)
                    cursor.execute(
                        "UPDATE workers SET portfolio_photo = ? WHERE id = ?",
                        (new_portfolio_json, worker_id)
                    )
                    conn.commit()
                    
                    logger.info(f"  Портфолио обновлено: {files_moved} файлов перемещено")
                    migrated_count += 1
                else:
                    logger.warning(f"  Портфолио пустое после миграции")
                
            except Exception as e:
                logger.error(f"Ошибка миграции портфолио исполнителя {tg_id}: {e}")
                error_count += 1
        
        logger.info(f"Миграция завершена:")
        logger.info(f"  Успешно мигрировано: {migrated_count}")
        logger.info(f"  Ошибок: {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
    finally:
        conn.close()

def cleanup_orphaned_files():
    """Удаляет оставшиеся файлы в общей папке photo, которые не являются папками пользователей"""
    
    photo_dir = 'app/data/photo'
    if not os.path.exists(photo_dir):
        return
    
    logger.info("Очистка оставшихся файлов в общей папке...")
    
    cleaned_count = 0
    for item in os.listdir(photo_dir):
        item_path = os.path.join(photo_dir, item)
        
        # Пропускаем папки пользователей (числовые имена)
        if os.path.isdir(item_path) and item.isdigit():
            continue
        
        # Удаляем файлы и нечисловые папки
        try:
            if os.path.isfile(item_path):
                os.remove(item_path)
                logger.info(f"Удален файл: {item}")
                cleaned_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                logger.info(f"Удалена папка: {item}")
                cleaned_count += 1
        except Exception as e:
            logger.error(f"Ошибка удаления {item}: {e}")
    
    logger.info(f"Очистка завершена: удалено {cleaned_count} элементов")

if __name__ == "__main__":
    logger.info("Начинаем миграцию фото портфолио...")
    
    # Создаем резервную копию базы данных
    db_path = 'app/data/database/database.db'
    backup_path = f'{db_path}.backup'
    if os.path.exists(db_path) and not os.path.exists(backup_path):
        shutil.copy2(db_path, backup_path)
        logger.info(f"Создана резервная копия: {backup_path}")
    
    # Выполняем миграцию
    migrate_all_portfolios()
    
    # Очищаем оставшиеся файлы
    cleanup_orphaned_files()
    
    logger.info("Миграция завершена!")
