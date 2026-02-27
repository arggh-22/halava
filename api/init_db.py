import asyncio
from tortoise import Tortoise
from api.models import Notification
import os

async def init():
    # Database configuration
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "data", "database", "database.db"))
    DB_URL = f"sqlite://{DB_PATH}"

    await Tortoise.init(
        db_url=DB_URL,
        modules={"models": ["api.models"]},
    )
    # Generate the schema
    await Tortoise.generate_schemas()
    print("Schema generated successfully.")

if __name__ == "__main__":
    asyncio.run(init())
