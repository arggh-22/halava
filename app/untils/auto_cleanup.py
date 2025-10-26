"""
Декоратор для автоматического сохранения ID отправленных сообщений
"""
import logging
from functools import wraps
from aiogram.types import Message
from app.middleware.cleanup_middleware import cleanup_middleware

logger = logging.getLogger(__name__)


def auto_cleanup(func):
    """
    Декоратор для автоматического сохранения ID отправленных сообщений
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Выполняем оригинальную функцию
        result = await func(*args, **kwargs)
        
        # Если результат - это Message (отправленное сообщение), сохраняем его ID
        if isinstance(result, Message):
            cleanup_middleware.save_message_id(result.chat.id, result.message_id)
            logger.debug(f"Auto-saved message ID {result.message_id} for chat {result.chat.id}")
        
        return result
    
    return wrapper


async def send_with_cleanup(message: Message, text: str, reply_markup=None, parse_mode=None):
    """
    Отправляет сообщение и автоматически сохраняет его ID для очистки
    """
    sent_message = await message.answer(
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    cleanup_middleware.save_message_id(message.chat.id, sent_message.message_id)
    logger.debug(f"Sent and saved message ID {sent_message.message_id} for chat {message.chat.id}")
    return sent_message


async def send_photo_with_cleanup(message: Message, photo, caption: str = None, reply_markup=None, parse_mode=None):
    """
    Отправляет фото и автоматически сохраняет его ID для очистки
    """
    sent_message = await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    cleanup_middleware.save_message_id(message.chat.id, sent_message.message_id)
    logger.debug(f"Sent photo and saved message ID {sent_message.message_id} for chat {message.chat.id}")
    return sent_message


async def send_video_with_cleanup(message: Message, video, caption: str = None, reply_markup=None, parse_mode=None):
    """
    Отправляет видео и автоматически сохраняет его ID для очистки
    """
    sent_message = await message.answer_video(
        video=video,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    cleanup_middleware.save_message_id(message.chat.id, sent_message.message_id)
    logger.debug(f"Sent video and saved message ID {sent_message.message_id} for chat {message.chat.id}")
    return sent_message
