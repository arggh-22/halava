"""
Удаляет устаревшие таблицы, если они существуют.

Целевые таблицы (с вариантами написания):
 - abs
 - worker_and_report
 - worker_and_customer / worker_and_customer
 - workers_and_abs
 - user_and_support_queue
 - work_sub_types / worker_sub_types
"""
import asyncio
import logging
from typing import Iterable

import aiosqlite


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


LEGACY_TABLE_NAMES: list[str] = [
    # as provided
    "abs",
    "worker_and_report",
    "worker_and_customer",
    "workers_and_abs",
    "user_and_spport_queue",
    "work_sub_types",
    "user_and_support_queue",
    "worker_sub_types",
]


async def drop_tables_if_exist(table_names: Iterable[str]) -> None:
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        for name in table_names:
            try:
                logger.info(f"DROP TABLE IF EXISTS {name}")
                await conn.execute(f"DROP TABLE IF EXISTS {name}")
            except Exception as e:
                logger.error(f"Ошибка при удалении таблицы {name}: {e}")
        await conn.commit()
        logger.info("✅ Удаление таблиц завершено")
    finally:
        await conn.close()


async def migrate() -> None:
    await drop_tables_if_exist(LEGACY_TABLE_NAMES)


if __name__ == '__main__':
    asyncio.run(migrate())


