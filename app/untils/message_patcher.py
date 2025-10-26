"""
Monkey patching для автоматического сохранения ID отправленных сообщений
"""
import logging
from aiogram import Bot
from app.middleware.cleanup_middleware import cleanup_middleware

logger = logging.getLogger(__name__)

# Сохраняем оригинальные методы
_original_send_message = Bot.send_message
_original_answer_message = None  # Будет установлен позже


async def patched_send_message(self, chat_id, text, **kwargs):
    """Патчим send_message для автоматического сохранения ID"""
    result = await _original_send_message(self, chat_id, text, **kwargs)
    
    # Сохраняем ID сообщения для очистки
    if hasattr(result, 'message_id'):
        cleanup_middleware.save_message_id(chat_id, result.message_id)
        logger.debug(f"Auto-saved send_message ID {result.message_id} for chat {chat_id}")
    
    return result


async def patched_answer(self, text, **kwargs):
    """Патчим answer для автоматического сохранения ID"""
    result = await self._original_answer(text, **kwargs)
    
    # Сохраняем ID сообщения для очистки
    if hasattr(result, 'message_id'):
        cleanup_middleware.save_message_id(self.chat.id, result.message_id)
        logger.debug(f"Auto-saved answer ID {result.message_id} for chat {self.chat.id}")
    
    return result


async def patched_answer_photo(self, photo, **kwargs):
    """Патчим answer_photo для автоматического сохранения ID"""
    result = await self._original_answer_photo(photo, **kwargs)
    
    # Сохраняем ID сообщения для очистки
    if hasattr(result, 'message_id'):
        cleanup_middleware.save_message_id(self.chat.id, result.message_id)
        logger.debug(f"Auto-saved answer_photo ID {result.message_id} for chat {self.chat.id}")
    
    return result


async def patched_answer_video(self, video, **kwargs):
    """Патчим answer_video для автоматического сохранения ID"""
    result = await self._original_answer_video(video, **kwargs)
    
    # Сохраняем ID сообщения для очистки
    if hasattr(result, 'message_id'):
        cleanup_middleware.save_message_id(self.chat.id, result.message_id)
        logger.debug(f"Auto-saved answer_video ID {result.message_id} for chat {self.chat.id}")
    
    return result


def apply_patches():
    """Применяет патчи для автоматического сохранения ID сообщений"""
    from aiogram.types import Message
    
    # Патчим Bot.send_message
    Bot.send_message = patched_send_message
    
    # Патчим методы Message
    if not hasattr(Message, '_original_answer'):
        Message._original_answer = Message.answer
        Message.answer = patched_answer
    
    if not hasattr(Message, '_original_answer_photo'):
        Message._original_answer_photo = Message.answer_photo
        Message.answer_photo = patched_answer_photo
    
    if not hasattr(Message, '_original_answer_video'):
        Message._original_answer_video = Message.answer_video
        Message.answer_video = patched_answer_video
    
    logger.info("Applied monkey patches for automatic message ID saving")


def remove_patches():
    """Удаляет патчи"""
    Bot.send_message = _original_send_message
    
    from aiogram.types import Message
    if hasattr(Message, '_original_answer'):
        Message.answer = Message._original_answer
        del Message._original_answer
    
    if hasattr(Message, '_original_answer_photo'):
        Message.answer_photo = Message._original_answer_photo
        del Message._original_answer_photo
    
    if hasattr(Message, '_original_answer_video'):
        Message.answer_video = Message._original_answer_video
        del Message._original_answer_video
    
    logger.info("Removed monkey patches")
