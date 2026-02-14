import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from app.data.database.models import (
    UserNotificationSettings,
    Worker,
    Customer
)
from config import BOT_TOKEN, WEB_APP_URL
from app.data.database.models import Notification

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


from datetime import datetime

async def create_notification(tg_id: int, notification_type: str, title: str, body: str, payload: dict = None, bot: Bot = None) -> bool:
    """
    Создает уведомление в БД и определяет, нужно ли отправить Push.
    
    Args:
        tg_id: Telegram ID пользователя
        notification_type: 'new_response', 'contact_bought', 'system', 'info' и т.д.
                           Типы 'contact_bought', 'payment', 'ban' считаются КРИТИЧЕСКИМИ и отправляются всегда.
        title: Заголовок уведомления
        body: Текст уведомления
        payload: Дополнительные данные (json)
        bot: Экземпляр бота (для умной отправки уведомлений)
        
    Returns:
        True - если нужно отправить Push (bot.send_message) СТАРЫМ СПОСОБОМ
        False - если уведомление сохранено "тихо" или отправлено через Smart Logic
    """

    # 1. Сохраняем в БД (без группировки - группировка при чтении)
    db_type = notification_type
    
    # Просто создаем новое уведомление
    notification = Notification(
        id=None,
        user_id=tg_id,
        type=db_type,
        title=title,
        body=body,
        payload=payload,
        is_read=False,
        created_at=None # auto set
    )
    await notification.save()

    
    MAX_AD_TEXT_LENGTH = 1200
    
    # 2. Проверяем критичность
    CRITICAL_TYPES = ['payment_success', 'ban_warning', 'unblock', 'support_message']
    
    if notification_type in CRITICAL_TYPES:
        return True
        
    # 3. Smart Logic (для некритичных типов, например new_response)
    if bot:
        try:
            settings = await UserNotificationSettings.get_or_create(tg_id)
            
            # Удаляем старое сообщение, если есть
            if settings.last_notification_message_id:
                try:
                    await bot.delete_message(chat_id=tg_id, message_id=settings.last_notification_message_id)
                except Exception:
                    pass # Сообщение могло быть удалено пользователем или слишком старое
            
            # Отправляем новое сообщение с кнопкой Web App
            # URL берется из config.py (автоматически из frontend/.env или переменной окружения)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔔 Открыть уведомления", web_app=WebAppInfo(url=WEB_APP_URL))]
            ])
            
            sent_message = await bot.send_message(
                chat_id=tg_id,
                text=f"🔔 <b>У вас новые уведомления!</b>\n\n{title}",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            
            # Сохраняем ID нового сообщения
            await settings.update(last_notification_message_id=sent_message.message_id)
            
            return False # Уведомление отправлено через Smart Logic
            
        except Exception as e:
            logger.error(f"Error in Smart Logic notification: {e}")
            # Если ошибка в Smart Logic, можно вернуть True, чтобы отправить по-старому (fallback)
            return True
            
    return False


