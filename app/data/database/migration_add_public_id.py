"""
Миграция для добавления поля public_id в таблицы workers и customers.
Запустите этот скрипт один раз для обновления БД.
"""

import sqlite3
import asyncio
import aiosqlite
import logging
from app.untils.public_id_generator import generate_public_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_public_id_columns():
    """Добавляет колонки public_id в таблицы workers и customers"""
    conn = await aiosqlite.connect('app/data/database/database.db')
    
    try:
        # Проверяем, существует ли колонка public_id в customers
        cursor = await conn.execute("PRAGMA table_info(customers)")
        columns = await cursor.fetchall()
        customer_columns = [col[1] for col in columns]
        
        if 'public_id' not in customer_columns:
            logger.info("Adding public_id column to customers table...")
            await conn.execute("ALTER TABLE customers ADD COLUMN public_id TEXT")
            await conn.commit()
            logger.info("✅ Added public_id to customers")
        else:
            logger.info("public_id already exists in customers table")
        
        # Проверяем, существует ли колонка public_id в workers
        cursor = await conn.execute("PRAGMA table_info(workers)")
        columns = await cursor.fetchall()
        worker_columns = [col[1] for col in columns]
        
        if 'public_id' not in worker_columns:
            logger.info("Adding public_id column to workers table...")
            await conn.execute("ALTER TABLE workers ADD COLUMN public_id TEXT")
            await conn.commit()
            logger.info("✅ Added public_id to workers")
        else:
            logger.info("public_id already exists in workers table")
        
        # Генерируем public_id для существующих пользователей
        await generate_public_ids_for_existing_users(conn)
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        await conn.close()


async def generate_public_ids_for_existing_users(conn):
    """Генерирует public_id для пользователей, у которых его нет"""
    
    # Для заказчиков
    logger.info("Generating public_ids for customers...")
    cursor = await conn.execute("SELECT id FROM customers WHERE public_id IS NULL OR public_id = ''")
    customers = await cursor.fetchall()
    
    for customer in customers:
        customer_id = customer[0]
        public_id = generate_public_id("C")
        await conn.execute("UPDATE customers SET public_id = ? WHERE id = ?", (public_id, customer_id))
        logger.info(f"Generated public_id {public_id} for customer {customer_id}")
    
    await conn.commit()
    logger.info(f"✅ Generated public_ids for {len(customers)} customers")
    
    # Для исполнителей
    logger.info("Generating public_ids for workers...")
    cursor = await conn.execute("SELECT id FROM workers WHERE public_id IS NULL OR public_id = ''")
    workers = await cursor.fetchall()
    
    for worker in workers:
        worker_id = worker[0]
        public_id = generate_public_id("W")
        await conn.execute("UPDATE workers SET public_id = ? WHERE id = ?", (public_id, worker_id))
        logger.info(f"Generated public_id {public_id} for worker {worker_id}")
    
    await conn.commit()
    logger.info(f"✅ Generated public_ids for {len(workers)} workers")


async def main():
    """Запуск миграции"""
    logger.info("Starting migration: Adding public_id fields...")
    await add_public_id_columns()
    logger.info("✅ Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())

