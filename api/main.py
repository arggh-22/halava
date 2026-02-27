from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise
from api.routes import notifications, user
import os

app = FastAPI(title="Halava Notifications API")

# Register routes
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(user.router, prefix="/api/user", tags=["user"])

# Database configuration
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "data", "database", "database.db"))
# Database URL for Tortoise ORM (sqlite)
DB_URL = f"sqlite://{DB_PATH}"

# Register Tortoise ORM
register_tortoise(
    app,
    db_url=DB_URL,
    modules={"models": ["api.models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)

@app.get("/")
async def root():
    return {"message": "Halava Notification API is running"}
