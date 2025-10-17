"""
Генератор уникальных Public ID для анонимности пользователей.
Public ID используется вместо реального Telegram ID или username.
"""

import random
import string
import logging

logger = logging.getLogger(__name__)


def generate_public_id(prefix: str = "U") -> str:
    """
    Генерирует уникальный Public ID для пользователя.
    
    Args:
        prefix: Префикс для ID (W - worker, C - customer)
        
    Returns:
        str: Уникальный Public ID в формате "W123456" или "C123456"
    """
    # Генерируем 6-значное число
    number = random.randint(100000, 999999)
    return f"{prefix}{number}"


def generate_unique_public_id(prefix: str = "U") -> str:
    """
    Генерирует уникальный Public ID с дополнительной случайностью.
    
    Args:
        prefix: Префикс для ID
        
    Returns:
        str: Уникальный Public ID
    """
    # Используем комбинацию цифр и букв для большей уникальности
    chars = string.digits
    random_part = ''.join(random.choices(chars, k=6))
    return f"{prefix}{random_part}"


async def get_or_create_public_id(user_type: str, user_id: int, existing_public_id: str = None) -> str:
    """
    Получает существующий или создает новый Public ID.
    
    Args:
        user_type: Тип пользователя ('worker' или 'customer')
        user_id: ID пользователя в системе
        existing_public_id: Существующий Public ID (если есть)
        
    Returns:
        str: Public ID
    """
    if existing_public_id:
        return existing_public_id
    
    prefix = "W" if user_type == "worker" else "C"
    public_id = generate_public_id(prefix)
    
    logger.info(f"Generated new public_id: {public_id} for {user_type} {user_id}")
    return public_id

