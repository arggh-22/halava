#!/usr/bin/env python3
"""
Скрипт для проверки состояния портфолио в базе данных.
Показывает статистику и детальную информацию о портфолио исполнителей.
"""

import os
import sqlite3
import json
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('portfolio_status.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def check_portfolio_status():
    """Проверяет состояние портфолио в базе данных"""
    
    # Подключаемся к базе данных
    db_path = 'app/data/database/database.db'
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Общая статистика
        cursor.execute("SELECT COUNT(*) FROM workers")
        total_workers = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''")
        workers_with_portfolio = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo IS NULL")
        workers_without_portfolio = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM workers WHERE portfolio_photo = ''")
        workers_empty_portfolio = cursor.fetchone()[0]
        
        print("\n" + "="*80)
        print("📊 СТАТИСТИКА ПОРТФОЛИО")
        print("="*80)
        print(f"Всего исполнителей: {total_workers}")
        print(f"С портфолио: {workers_with_portfolio}")
        print(f"Без портфолио (NULL): {workers_without_portfolio}")
        print(f"С пустым портфолио ('') : {workers_empty_portfolio}")
        print("="*80)
        
        # Детальная информация о портфолио
        if workers_with_portfolio > 0:
            print("\n📋 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ПОРТФОЛИО:")
            print("-" * 80)
            
            cursor.execute("""
                SELECT id, tg_id, tg_name, portfolio_photo 
                FROM workers 
                WHERE portfolio_photo IS NOT NULL AND portfolio_photo != ''
                ORDER BY id
            """)
            
            workers = cursor.fetchall()
            
            for worker_id, tg_id, tg_name, portfolio_json in workers:
                try:
                    portfolio_dict = json.loads(portfolio_json)
                    photo_count = len(portfolio_dict)
                    
                    print(f"ID: {worker_id} | TG: {tg_id} | Имя: {tg_name} | Фото: {photo_count}")
                    
                    # Показываем пути к файлам
                    for key, path in portfolio_dict.items():
                        file_exists = os.path.exists(path) if path else False
                        status = "✅" if file_exists else "❌"
                        print(f"  {status} Ключ {key}: {path}")
                    
                    print()
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON для исполнителя {tg_id}: {e}")
                    print(f"   Данные: {portfolio_json[:100]}...")
                    print()
        
        # Проверяем файловую систему
        print("\n📁 ПРОВЕРКА ФАЙЛОВОЙ СИСТЕМЫ:")
        print("-" * 80)
        
        photo_dir = 'app/data/photo'
        if os.path.exists(photo_dir):
            # Считаем папки пользователей
            user_folders = []
            portfolio_folders = []
            
            for item in os.listdir(photo_dir):
                item_path = os.path.join(photo_dir, item)
                if os.path.isdir(item_path) and item.isdigit():
                    user_folders.append(item)
                    
                    # Проверяем папку portfolio
                    portfolio_path = os.path.join(item_path, 'portfolio')
                    if os.path.exists(portfolio_path):
                        portfolio_folders.append(item)
                        # Считаем файлы в папке portfolio
                        portfolio_files = [f for f in os.listdir(portfolio_path) if f.endswith('.jpg')]
                        print(f"👤 Пользователь {item}: {len(portfolio_files)} фото в portfolio/")
            
            print(f"\n📊 Файловая система:")
            print(f"  Папок пользователей: {len(user_folders)}")
            print(f"  Папок с portfolio: {len(portfolio_folders)}")
        else:
            print("❌ Папка app/data/photo не найдена")
        
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {e}")
    finally:
        conn.close()

def check_specific_worker(tg_id):
    """Проверяет портфолио конкретного исполнителя"""
    
    db_path = 'app/data/database/database.db'
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, tg_id, tg_name, portfolio_photo 
            FROM workers 
            WHERE tg_id = ?
        """, (tg_id,))
        
        worker = cursor.fetchone()
        
        if not worker:
            print(f"❌ Исполнитель с TG ID {tg_id} не найден")
            return
        
        worker_id, tg_id, tg_name, portfolio_json = worker
        
        print(f"\n👤 ИСПОЛНИТЕЛЬ: {tg_name} (TG: {tg_id}, ID: {worker_id})")
        print("-" * 60)
        
        if portfolio_json:
            try:
                portfolio_dict = json.loads(portfolio_json)
                photo_count = len(portfolio_dict)
                
                print(f"📸 Портфолио: {photo_count} фото")
                
                for key, path in portfolio_dict.items():
                    file_exists = os.path.exists(path) if path else False
                    status = "✅" if file_exists else "❌"
                    print(f"  {status} Ключ {key}: {path}")
                    
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                print(f"Данные: {portfolio_json}")
        else:
            print("📸 Портфолио: отсутствует")
        
    except Exception as e:
        logger.error(f"Ошибка при проверке исполнителя: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Проверяем конкретного исполнителя
        try:
            tg_id = int(sys.argv[1])
            check_specific_worker(tg_id)
        except ValueError:
            print("❌ Неверный TG ID. Используйте число.")
    else:
        # Показываем общую статистику
        check_portfolio_status()
