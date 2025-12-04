"""
Утилита для проверки и управления уведомлениями пользователей.
Определяет, нужно ли отправлять уведомление в зависимости от настроек пользователя и его текущей роли.
"""

import logging
from typing import Optional

from app.data.database.models import (
    UserNotificationSettings,
    Worker,
    Customer
)

logger = logging.getLogger(__name__)


async def get_user_current_role(tg_id: int) -> Optional[str]:
    """
    Определяет текущую роль пользователя
    
    Args:
        tg_id: Telegram ID пользователя
        
    Returns:
        'worker' - если worker.active = 1
        'customer' - если worker.active = 0 или нет worker, но есть customer
        None - если пользователь не зарегистрирован
    """
    worker = await Worker.get_worker(tg_id=tg_id)
    customer = await Customer.get_customer(tg_id=tg_id)
    
    if worker and worker.active == 1:
        return 'worker'
    elif customer:
        return 'customer'
    else:
        return None


async def should_send_notification(tg_id: int, notification_type: str) -> bool:
    """
    Проверяет, нужно ли отправлять уведомление пользователю
    
    Args:
        tg_id: Telegram ID пользователя
        notification_type: 'worker' или 'customer' - тип уведомления
        
    Returns:
        True если нужно отправить, False если нет
    """
    try:
        # Получаем настройки пользователя (если нет - создаем с default=False)
        settings = await UserNotificationSettings.get_or_create(tg_id)
        
        # Если unified_notifications = True -> отправляем всегда (если пользователь зарегистрирован)
        if settings.unified_notifications:
            # Проверяем, что пользователь хотя бы в одной таблице
            worker = await Worker.get_worker(tg_id=tg_id)
            customer = await Customer.get_customer(tg_id=tg_id)
            
            if not worker and not customer:
                # Пользователь не зарегистрирован - не отправляем
                return False
            
            # Пользователь зарегистрирован - отправляем для обеих ролей
            return True
        
        # Если unified_notifications = False -> отправляем только для текущей роли
        if notification_type == 'customer':
            # Уведомление для заказчика
            customer = await Customer.get_customer(tg_id=tg_id)
            if not customer:
                return False  # Нет в таблице customers
            
            # Проверяем, активен ли пользователь как исполнитель
            worker = await Worker.get_worker(tg_id=tg_id)
            if worker and worker.active == 1:
                # Пользователь активен как исполнитель - не отправляем уведомление заказчика
                return False
            
            # Пользователь в роли заказчика - отправляем
            return True
        
        elif notification_type == 'worker':
            # Уведомление для исполнителя
            worker = await Worker.get_worker(tg_id=tg_id)
            if not worker:
                return False  # Нет в таблице workers
            
            # Проверяем активность
            if worker.active == 0:
                # Пользователь неактивен как исполнитель (в роли заказчика) - не отправляем
                return False
            
            # Пользователь активен как исполнитель - отправляем
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in should_send_notification for tg_id={tg_id}, type={notification_type}: {e}")
        # В случае ошибки отправляем уведомление (безопасный вариант)
        return True


async def get_notification_status_text(tg_id: int) -> tuple[str, bool]:
    """
    Получает текст статуса уведомлений и текущее значение
    
    Args:
        tg_id: Telegram ID пользователя
        
    Returns:
        tuple: (текст статуса, текущее значение unified_notifications)
    """
    settings = await UserNotificationSettings.get_or_create(tg_id)

    if settings.unified_notifications:
        status_text = "✅ <b>ВКЛ</b>"
    else:
        status_text = "❌ <b>ВЫКЛ</b>"
    
    return status_text, settings.unified_notifications

