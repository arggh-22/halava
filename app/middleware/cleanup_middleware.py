"""
Middleware для автоматической очистки предыдущих сообщений и проверки блокировок
"""
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)


class DeletePreviousMiddleware(BaseMiddleware):
    """
    Middleware для автоматического удаления предыдущих сообщений бота и пользователя
    """
    
    def __init__(self):
        # Словарь для хранения ID последних сообщений бота в каждом чате
        self.last_bot_messages: Dict[int, int] = {}
        # Словарь для хранения ID последних сообщений пользователя в каждом чате
        self.last_user_messages: Dict[int, int] = {}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Основной метод middleware
        """
        logger.debug(f"Middleware called with event type: {type(event)}")
        
        # Проверка блокировок для CallbackQuery (кнопки)
        if isinstance(event, CallbackQuery):
            # Разрешенные callback_data (кнопка поддержки и другие исключения)
            allowed_callbacks = ['support', 'support_history', 'support_ask_question', 'menu', 'support_blocking_yes', 'support_blocking_no']
            
            # Проверяем, не заблокирован ли пользователь навсегда
            if event.data not in allowed_callbacks:
                try:
                    from app.data.database.models import Banned
                    banned = await Banned.get_banned(tg_id=event.from_user.id)
                    
                    if banned and banned.forever and banned.ban_now:
                        # Пользователь заблокирован навсегда
                        await event.answer(
                            "🚫 Ваш аккаунт заблокирован за повторные нарушения правил платформы!",
                            show_alert=True
                        )
                        return  # Блокируем выполнение обработчика
                except Exception as e:
                    logger.error(f"Ошибка при проверке блокировки: {e}")
        
        # Получаем бота из данных
        bot = data.get("bot")
        if not bot:
            logger.debug("No bot in data, skipping middleware")
            return await handler(event, data)
        
        # Получаем состояние FSM для проверки исключений
        state = data.get("state")
        if state:
            current_state = await state.get_state()
            logger.debug(f"Current FSM state: {current_state}")
            
            # Исключения для состояний, где не нужно удалять сообщения
            skip_cleanup_states = [
                "WorkStates:portfolio_upload_photo",  # Загрузка фото в портфолио
                # "WorkStates:create_photo_profile",    # Загрузка фото профиля
                # "WorkStates:create_portfolio",        # Просмотр портфолио
                "CustomerStates:customer_create_abs_add_photo",  # Загрузка фото в объявления
                "WorkStates:worker_choose_work_types",  # Выбор направлений работы (редактирование сообщений)
                "WorkStates:worker_choose_subscription_cities",  # Выбор городов для подписки (редактирование сообщений)
                # "CustomerStates:customer_create_abs_personal_add_photo",  # Загрузка фото в личные объявления
                # "CustomerStates:customer_create_abs_task",  # Создание объявления - ввод задачи
                # "CustomerStates:customer_create_abs_choose_time",  # Создание объявления - выбор времени
                # "CustomerStates:customer_create_abs_work_type"  # Создание объявления - выбор типа работы
            ]
            
            if current_state in skip_cleanup_states:
                logger.debug(f"Skipping cleanup for state: {current_state}")
                # Сохраняем ID сообщения пользователя, но не удаляем предыдущие
                chat_id = None
                message_id = None
                
                if hasattr(event, 'chat') and hasattr(event, 'message_id'):
                    chat_id = event.chat.id
                    message_id = event.message_id
                elif hasattr(event, 'message') and hasattr(event.message, 'chat'):
                    chat_id = event.message.chat.id
                    message_id = event.message.message_id
                
                if message_id and chat_id:
                    self.last_user_messages[chat_id] = message_id
                    logger.debug(f"Saved user message ID {message_id} for chat {chat_id} (no cleanup)")
                
                # Выполняем основное действие без очистки
                result = await handler(event, data)
                return result
        
        # Определяем chat_id и message_id в зависимости от типа события
        chat_id = None
        message_id = None
        
        if hasattr(event, 'chat') and hasattr(event, 'message_id'):
            # Это Message
            chat_id = event.chat.id
            message_id = event.message_id
            logger.debug(f"Message event, chat_id: {chat_id}, message_id: {message_id}")
        elif hasattr(event, 'message') and hasattr(event.message, 'chat'):
            # Это CallbackQuery
            chat_id = event.message.chat.id
            message_id = event.message.message_id
            logger.debug(f"CallbackQuery event, chat_id: {chat_id}, message_id: {message_id}")
        
        # Если это не личный чат, пропускаем очистку
        if not chat_id or (hasattr(chat_id, '__int__') and int(chat_id) < 0):
            logger.debug(f"Skipping cleanup for chat_id: {chat_id}")
            return await handler(event, data)
        
        # Удаляем предыдущие сообщения бота и пользователя
        await self._cleanup_previous_messages(bot, chat_id)
        
        # Сохраняем ID текущего сообщения пользователя для следующей очистки
        if message_id:
            self.last_user_messages[chat_id] = message_id
            logger.debug(f"Saved user message ID {message_id} for chat {chat_id}")
        
        # Выполняем основное действие
        result = await handler(event, data)
        
        return result
    
    async def _cleanup_previous_messages(self, bot, chat_id: int):
        """
        Удаляет предыдущие сообщения бота и пользователя в чате
        """
        # Удаляем предыдущее сообщение бота
        try:
            last_bot_message_id = self.last_bot_messages.get(chat_id)
            if last_bot_message_id:
                await bot.delete_message(chat_id=chat_id, message_id=last_bot_message_id)
                logger.debug(f"Deleted previous bot message {last_bot_message_id} in chat {chat_id}")
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            logger.debug(f"Could not delete bot message in chat {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error deleting bot message in chat {chat_id}: {e}")
        
        # Удаляем предыдущее сообщение пользователя
        try:
            last_user_message_id = self.last_user_messages.get(chat_id)
            if last_user_message_id:
                await bot.delete_message(chat_id=chat_id, message_id=last_user_message_id)
                logger.debug(f"Deleted previous user message {last_user_message_id} in chat {chat_id}")
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            logger.debug(f"Could not delete user message in chat {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error deleting user message in chat {chat_id}: {e}")
    
    def save_message_id(self, chat_id: int, message_id: int):
        """
        Публичный метод для сохранения ID сообщения бота из обработчиков
        """
        self.last_bot_messages[chat_id] = message_id
        logger.debug(f"Saved bot message ID {message_id} for chat {chat_id}")


# Глобальный экземпляр middleware
cleanup_middleware = DeletePreviousMiddleware()
