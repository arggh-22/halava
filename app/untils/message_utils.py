"""
Утилиты для работы с сообщениями Telegram
"""

import logging
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)


async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode=None):
    """
    Безопасное редактирование сообщения - работает с текстом и фото
    
    Args:
        callback: CallbackQuery объект
        text: Текст для отображения
        reply_markup: Клавиатура (опционально)
        parse_mode: Режим парсинга (опционально)
    """
    try:
        if callback.message.photo:
            # Если сообщение содержит фото, редактируем подпись
            await callback.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            # Если сообщение текстовое, редактируем текст
            await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except Exception as e:
        logger.error(f"Error in safe_edit_message: {e}")
        # Fallback: отправляем новое сообщение
        try:
            await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as fallback_error:
            logger.error(f"Error in fallback message sending: {fallback_error}")
            # Последняя попытка - просто отвечаем на callback
            await callback.answer("❌ Ошибка отображения сообщения", show_alert=True)


async def safe_delete_message(callback: CallbackQuery):
    """
    Безопасное удаление сообщения
    
    Args:
        callback: CallbackQuery объект
    """
    try:
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Error in safe_delete_message: {e}")
        # Сообщение может быть уже удалено или недоступно для удаления
