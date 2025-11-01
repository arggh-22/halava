import asyncio
import inspect
from typing import Awaitable, Callable

import aiosqlite


async def _call_safely(coro: Awaitable | Callable) -> None:
    try:
        if inspect.iscoroutine(coro):
            await coro
        elif callable(coro):
            result = coro()
            if inspect.iscoroutine(result):
                await result
    except Exception:
        # Silently ignore individual table init errors to not block startup
        pass


async def init_db() -> None:
    """Ensure all tables that expose create_table_if_not_exists are present.

    Scans app.data.database.models for classes with async/sync
    create_table_if_not_exists and calls them. Also applies basic PRAGMAs.
    """
    import app.data.database.models as models

    # Iterate over all attributes in models module and call table creators
    for _name, attr in inspect.getmembers(models):
        if inspect.isclass(attr) and hasattr(attr, 'create_table_if_not_exists'):
            creator = getattr(attr, 'create_table_if_not_exists')
            await _call_safely(creator)

    # Optional: ensure basic PRAGMAs (no-op if DB missing; connection creates file)
    try:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('PRAGMA journal_mode=WAL;')
            await conn.execute('PRAGMA foreign_keys=ON;')
            await conn.commit()
        finally:
            await conn.close()
    except Exception:
        pass

    # Инициализация тарифов контактов по умолчанию
    try:
        await models.ContactTariff.init_default_tariffs()
    except Exception as e:
        # Silently ignore if tariffs already exist or other init errors
        pass

    # Инициализация тарифов городов по умолчанию
    try:
        await models.CitySubscriptionTariff.init_default_tariffs()
    except Exception as e:
        # Silently ignore if tariffs already exist or other init errors
        pass

    # Инициализация скидок городов по умолчанию
    try:
        await models.CitySubscriptionDiscount.init_default_discounts()
    except Exception as e:
        # Silently ignore if discounts already exist or other init errors
        pass


def init_db_sync() -> None:
    asyncio.run(init_db())


