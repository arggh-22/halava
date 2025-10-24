"""
Миграция для добавления поля message_timestamps в таблицу workers_and_abs
Это поле будет хранить временные метки для каждого сообщения в формате JSON
"""

import sqlite3

def migrate():
    conn = sqlite3.connect('app/data/database/database.db')
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли уже поле
        cursor.execute("PRAGMA table_info(workers_and_abs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'message_timestamps' not in columns:
            print("Adding message_timestamps field...")
            cursor.execute("""
                ALTER TABLE workers_and_abs 
                ADD COLUMN message_timestamps TEXT
            """)
            
            # Инициализируем существующие записи пустым JSON
            cursor.execute("UPDATE workers_and_abs SET message_timestamps = '[]' WHERE message_timestamps IS NULL")
            
            conn.commit()
            print("SUCCESS: message_timestamps field added!")
        else:
            print("WARNING: message_timestamps field already exists")
        
        # Показываем структуру таблицы
        cursor.execute("PRAGMA table_info(workers_and_abs)")
        print("\nTable structure workers_and_abs:")
        for column in cursor.fetchall():
            print(f"  - {column[1]} ({column[2]})")
            
    except Exception as e:
        print(f"ERROR during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("Start migration for chat timestamps...")
    migrate()
    print("Migration completed!")

