from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_user
from app.untils.notification_helper import get_user_current_role
from app.data.database.models import Worker, Customer

router = APIRouter()

@router.get("/profile")
async def get_profile(user_id: int = Depends(get_current_user)):
    """
    Returns user profile information, including current active role.
    """
    role = await get_user_current_role(user_id)
    
    # Get basic info based on role
    name = "User"
    if role == 'worker':
        worker = await Worker.get_worker(tg_id=user_id)
        name = worker.profile_name or worker.tg_name
    elif role == 'customer':
        customer = await Customer.get_customer(tg_id=user_id)
        name = customer.tg_name

    return {
        "user_id": user_id,
        "role": role,
        "name": name,
        "is_registered": role is not None
    }
