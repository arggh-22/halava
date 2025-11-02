"""
Декоратор для автоматического сохранения ID отправленных сообщений
"""
import logging
from functools import wraps
from aiogram.types import Message
from app.middleware.cleanup_middleware import cleanup_middleware

logger = logging.getLogger(__name__)


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
