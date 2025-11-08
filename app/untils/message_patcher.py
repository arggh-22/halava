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


async def patched_edit_text(self, text, **kwargs):
    """Патчим edit_text для автоматического сохранения ID"""
    result = await self._original_edit_text(text, **kwargs)
    
    # edit_text может вернуть True или Message объект
    # Сохраняем ID отредактированного сообщения для очистки
    try:
        chat_id = self.chat.id if hasattr(self, 'chat') else None
        message_id = None
        
        if hasattr(result, 'message_id'):
            # Если вернулся Message объект, используем его ID
            message_id = result.message_id
        elif result is True and hasattr(self, 'message_id'):
            # Если вернулось True, используем ID текущего сообщения (которое было отредактировано)
            message_id = self.message_id
        
        if message_id and chat_id:
            cleanup_middleware.save_message_id(chat_id, message_id)
            logger.debug(f"Auto-saved edit_text ID {message_id} for chat {chat_id}")
    except Exception as e:
        logger.debug(f"Could not save edit_text message ID: {e}")
    
    return result


async def patched_edit_caption(self, caption=None, **kwargs):
    """Патчим edit_caption для автоматического сохранения ID"""
    result = await self._original_edit_caption(caption=caption, **kwargs)
    
    # edit_caption может вернуть True или Message объект
    # Сохраняем ID отредактированного сообщения для очистки
    try:
        chat_id = self.chat.id if hasattr(self, 'chat') else None
        message_id = None
        
        if hasattr(result, 'message_id'):
            # Если вернулся Message объект, используем его ID
            message_id = result.message_id
        elif result is True and hasattr(self, 'message_id'):
            # Если вернулось True, используем ID текущего сообщения (которое было отредактировано)
            message_id = self.message_id
        
        if message_id and chat_id:
            cleanup_middleware.save_message_id(chat_id, message_id)
            logger.debug(f"Auto-saved edit_caption ID {message_id} for chat {chat_id}")
    except Exception as e:
        logger.debug(f"Could not save edit_caption message ID: {e}")
    
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
    
    if not hasattr(Message, '_original_edit_text'):
        Message._original_edit_text = Message.edit_text
        Message.edit_text = patched_edit_text
    
    if not hasattr(Message, '_original_edit_caption'):
        Message._original_edit_caption = Message.edit_caption
        Message.edit_caption = patched_edit_caption
    
    logger.info("Applied monkey patches for automatic message ID saving")


# def remove_patches():
#     """Удаляет патчи"""
#     Bot.send_message = _original_send_message
#
#     from aiogram.types import Message
#     if hasattr(Message, '_original_answer'):
#         Message.answer = Message._original_answer
#         del Message._original_answer
#
#     if hasattr(Message, '_original_answer_photo'):
#         Message.answer_photo = Message._original_answer_photo
#         del Message._original_answer_photo
#
#     if hasattr(Message, '_original_answer_video'):
#         Message.answer_video = Message._original_answer_video
#         del Message._original_answer_video
#
#     logger.info("Removed monkey patches")
