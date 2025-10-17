"""
Усиленный фильтр для предотвращения обмена контактной информацией в анонимном чате.
Блокирует номера телефонов, email, ссылки, ID мессенджеров и "разбитые" контакты.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class ContactFilter:
    """Фильтр для обнаружения контактной информации в сообщениях"""
    
    # Паттерны для обнаружения контактов
    PHONE_PATTERNS = [
        # Российские номера
        r'(?:\+7|8|7)[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}',
        # Международные номера
        r'(?:\+|00)[1-9]\d{1,14}',
        # Разбитые номера с пробелами/тире/точками
        r'\b[0-9]{1,4}[\s\.\-_][0-9]{1,4}[\s\.\-_][0-9]{1,4}[\s\.\-_][0-9]{1,4}',
        # Номера в тексте
        r'\b[0-9]{10,15}\b',
    ]
    
    EMAIL_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r'\b[A-Za-z0-9._%+-]+\s*[@собака]\s*[A-Za-z0-9.-]+\s*[\.точка]\s*[A-Z|a-z]{2,}\b',
    ]
    
    LINK_PATTERNS = [
        r'(?:https?://|www\.)[^\s]+',
        r'\b[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r't\.me/[A-Za-z0-9_]+',
    ]
    
    MESSENGER_PATTERNS = [
        r'@[A-Za-z0-9_]{5,}',  # Telegram username
        r'viber|whatsapp|vk\.com|vkontakte|instagram|facebook|skype',
        r'вайбер|ватсап|вацап|инста|фейсбук|скайп|телега',
    ]
    
    # Паттерны для обнаружения "разбитых" контактов
    BROKEN_CONTACT_PATTERNS = [
        r'[0-9]{2,}[\s\-_\.\,]+[0-9]{2,}[\s\-_\.\,]+[0-9]{2,}',  # Числа с разделителями
        r'[A-Za-z0-9]{3,}[\s]+собака[\s]+[A-Za-z0-9]{3,}',  # email через "собака"
        r'[A-Za-z0-9]{3,}[\s]+точка[\s]+[A-Za-z]{2,}',  # домены через "точка"
    ]
    
    # Запрещенные слова, связанные с контактами
    FORBIDDEN_WORDS = [
        'номер', 'телефон', 'позвони', 'позвоните', 'звони', 'напиши',
        'пиши', 'свяжись', 'связаться', 'контакт', 'почта', 'email',
        'мейл', 'whatsapp', 'viber', 'telegram', 'вайбер', 'ватсап',
        'вацап', 'телега', 'инста', 'вк', 'вконтакте'
    ]
    
    # Паттерны для латиницы (запрещена в чате)
    LATIN_PATTERN = r'[A-Za-z]{3,}'
    
    @classmethod
    def check_message(cls, text: str) -> Tuple[bool, str]:
        """
        Проверяет сообщение на наличие контактной информации.
        
        Args:
            text: Текст сообщения для проверки
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
                - is_valid: True если сообщение допустимо, False если содержит контакты
                - error_message: Описание нарушения (если есть)
        """
        if not text:
            return True, ""
        
        text_lower = text.lower()
        
        # Проверка на номера телефонов
        for pattern in cls.PHONE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Phone number detected in message: {text[:50]}")
                return False, "❌ Обнаружен номер телефона. Используйте кнопку 'Запросить контакт'."
        
        # Проверка на email
        for pattern in cls.EMAIL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Email detected in message: {text[:50]}")
                return False, "❌ Обнаружен email. Используйте кнопку 'Запросить контакт'."
        
        # Проверка на ссылки
        for pattern in cls.LINK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Link detected in message: {text[:50]}")
                return False, "❌ Обнаружена ссылка. Обмен контактами запрещен в чате."
        
        # Проверка на мессенджеры
        for pattern in cls.MESSENGER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Messenger detected in message: {text[:50]}")
                return False, "❌ Обнаружено упоминание мессенджера. Используйте кнопку 'Запросить контакт'."
        
        # Проверка на "разбитые" контакты
        for pattern in cls.BROKEN_CONTACT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Broken contact detected in message: {text[:50]}")
                return False, "❌ Обнаружена попытка передачи контакта. Используйте кнопку 'Запросить контакт'."
        
        # Проверка на запрещенные слова
        for word in cls.FORBIDDEN_WORDS:
            if word in text_lower:
                logger.warning(f"Forbidden word '{word}' detected in message: {text[:50]}")
                return False, f"❌ Обнаружено запрещенное слово '{word}'. Используйте кнопку 'Запросить контакт'."
        
        # Проверка на латиницу (более 2 латинских букв подряд)
        if re.search(cls.LATIN_PATTERN, text):
            logger.warning(f"Latin text detected in message: {text[:50]}")
            return False, "❌ Использование латиницы в чате запрещено."
        
        # Проверка на цифры (подозрительное количество)
        digit_count = sum(c.isdigit() for c in text)
        if digit_count > 7:
            logger.warning(f"Too many digits in message: {text[:50]}")
            return False, "❌ Сообщение содержит слишком много цифр. Возможна попытка передачи контакта."
        
        return True, ""


def check_message_for_contacts(text: str) -> Tuple[bool, str]:
    """
    Удобная функция-обертка для проверки сообщения.
    
    Args:
        text: Текст сообщения
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    return ContactFilter.check_message(text)

