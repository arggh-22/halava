import asyncio
import os
from tortoise import Tortoise
from app.untils.notification_helper import create_notification
from api.models import Notification

async def test_notification_flow():
    # Init Tortoise (needed for create_notification inside helper? 
    # Helper imports Notification from api.models. api.models uses Tortoise.
    # So we need to init Tortoise.
    
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "app", "data", "database", "database.db"))
    DB_URL = f"sqlite://{DB_PATH}"

    await Tortoise.init(
        db_url=DB_URL,
        modules={"models": ["api.models"]},
    )
    
    user_id = 123456789
    print(f"Creating notification for user {user_id}...")
    
    should_push = await create_notification(
        tg_id=user_id,
        notification_type='new_response',
        title='Test Notification',
        body='This is a test notification body.',
        payload={'test': 'data'}
    )
    
    print(f"Notification created. Push needed? {should_push}")
    
    # Verify in DB
    notif = await Notification.filter(user_id=user_id).order_by('-id').first()
    if notif:
        print(f"Found notification in DB: ID={notif.id}, Title={notif.title}")
        assert notif.title == 'Test Notification'
        print("Verification SUCCESS!")
    else:
        print("Verification FAILED: Notification not found in DB.")

    await Tortoise.close_connections()

if __name__ == "__main__":
    asyncio.run(test_notification_flow())
