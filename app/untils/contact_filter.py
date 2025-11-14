"""
Усиленный фильтр для предотвращения обмена контактной информацией в анонимном чате.
Блокирует номера телефонов, email, ссылки, ID мессенджеров и "разбитые" контакты.
"""

import re
import logging
from typing import Tuple, List, Optional

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
    
    # Числительные на русском языке (включая варианты с заменой букв на цифры и опечатки)
    NUMBER_WORDS = [
        # 0 - ноль, нуль
        'ноль', 'нуль', 'н0ль', 'н0л', 'нoль', 'нoл', 'нул', 'нол',
        # 1 - один, единица
        'один', 'единица', '0дин', 'oдин', 'од1н', '0д1н',
        'единицa', 'единиц@', 'ед1ница', 'ед1ницa', 'ед1ниц@',
        '0динн@дцать', 'oдинн@дцать',
        # 2 - два
        'два', 'дв@', 'двa', 'дв@а', 'дваа',
        # 3 - три, тройка
        'три', 'тройка', 'тр1', 'трi', 'тр1йка', 'трiйка', 'трoйка',
        # 4 - четыре
        'четыре', 'ч3тыре', 'ч3тырe', 'четырe', 'четырэ', 'ч3тырэ',
        # 5 - пять, пятёрка
        'пять', 'пятёрка', 'п5ть', 'п5т', 'пятeрка', 'п5терка', 'п5тёрка',
        'пятeркa', 'п5теркa',
        # 6 - шесть
        'шесть', 'ш3сть', 'ш3ст', 'шест', 'шeсть', 'шeст',
        # 7 - семь
        'семь', 'с3мь', 'с3м', 'сем', 'сeмь', 'сeм',
        # 8 - восемь
        'восемь', 'в0семь', 'в0сем', 'восем', 'вoсемь', 'вoсем',
        'восьмь', 'в0сьмь', 'в0сьм',
        # 9 - девять
        'девять', 'д3вять', 'д3вят', 'девят', 'дeвять', 'дeвят',
        # 10 - десять
        'десять', 'д3сять', 'д3сят', 'десят', 'дeсять', 'дeсят',
        # 11 - одиннадцать
        'одиннадцать', '0диннадцать', 'oдиннадцать', 'одинн@дцать',
        'од1ннадцать', 'од1нн@дцать',
        # 12 - двенадцать
        'двенадцать', 'дв3надцать', 'двeнадцать', 'дв@надцать',
        'дв3н@дцать', 'двeн@дцать',
        # 13 - тринадцать
        'тринадцать', 'тр1надцать', 'трiнадцать', 'тр1н@дцать',
        'трiн@дцать', 'трoнадцать',
        # 14 - четырнадцать
        'четырнадцать', 'ч3тырнадцать', 'ч3тырн@дцать', 'четырн@дцать',
        'ч3тырeнадцать',
        # 15 - пятнадцать
        'пятнадцать', 'п5тнадцать', 'п5тн@дцать', 'пятн@дцать',
        'п5тeрнадцать',
        # 16 - шестнадцать
        'шестнадцать', 'ш3стнадцать', 'ш3стн@дцать', 'шестн@дцать',
        'шeстнадцать',
        # 17 - семнадцать
        'семнадцать', 'с3мнадцать', 'с3мн@дцать', 'семн@дцать',
        'сeмнадцать',
        # 18 - восемнадцать
        'восемнадцать', 'в0семнадцать', 'в0семн@дцать', 'восемн@дцать',
        'вoсемнадцать', 'восьмнадцать', 'в0сьмнадцать',
        # 19 - девятнадцать
        'девятнадцать', 'д3вятнадцать', 'д3вятн@дцать', 'девятн@дцать',
        'дeвятнадцать',
        # 20 - двадцать
        'двадцать', 'дв@дцать', 'двaдцать', 'дв@тцать', 'двaтцать',
        # 30 - тридцать
        'тридцать', 'тр1дцать', 'трiдцать', 'тр1тцать', 'трiтцать',
        'трoдцать',
        # 40 - сорок
        'сорок', 'с0рок', 'сoрок', 'сор0к',
        # 50 - пятьдесят
        'пятьдесят', 'п5тьдесят', 'п5тдесят', 'пятдесят', 'п5тeсят',
        # 60 - шестьдесят
        'шестьдесят', 'ш3стьдесят', 'ш3стдесят', 'шестдесят',
        'шeстьдесят',
        # 70 - семьдесят
        'семьдесят', 'с3мьдесят', 'с3мдесят', 'семдесят', 'сeмьдесят',
        # 80 - восемьдесят
        'восемьдесят', 'в0семьдесят', 'в0семдесят', 'восемдесят',
        'вoсемьдесят', 'восьмьдесят', 'в0сьмьдесят',
        # 90 - девяносто
        'девяносто', 'д3вяносто', 'д3в@носто', 'дев@носто', 'дeвяносто',
        # 100 - сто
        'сто', 'ст0', 'стo', 'сmо', 'сm0',
        # 200 - двести
        'двести', 'дв3ста', 'двeста', 'дв@ста', 'двaста',
        # 300 - триста
        'триста', 'тр1ста', 'трiста', 'тр1ст@', 'трiст@',
        # 400 - четыреста
        'четыреста', 'ч3тыреста', 'ч3тырeста', 'четырeста',
        # 500 - пятьсот
        'пятьсот', 'п5тьсот', 'п5тсот', 'пятсот', 'п5тcот',
        # 600 - шестьсот
        'шестьсот', 'ш3стьсот', 'ш3стсот', 'шестсот',
        # 700 - семьсот
        'семьсот', 'с3мьсот', 'с3мсот', 'семсот',
        # 800 - восемьсот
        'восемьсот', 'в0семьсот', 'в0семсот', 'восемсот',
        'вoсемьсот', 'восьмьсот', 'в0сьмьсот',
        # 900 - девятьсот
        'девятьсот', 'д3вятьсот', 'д3вятсот', 'девятсот',
        # 1000 - тысяча
        'тысяча', 'т1сяча', 'тiсяча', 'тыс@ча', 'тысaча',
        # Дополнительные варианты и опечатки
        'нольноль', 'н0льн0ль', 'нульнуль', 'н0льн0л',
        'одинодин', '0дин0дин', 'двадва', 'дв@дв@',
        'тритри', 'тр1тр1', 'четыречетыре', 'ч3тыреч3тыре',
        # Варианты с транслитерацией
        'nol', 'nul', 'odin', 'dva', 'tri', 'chetyre', 'pyat', 'shest',
        'sem', 'vosem', 'devyat', 'desyat', 'dvadcat', 'tridcat',
        # Варианты с заменой на похожие символы (латинские буквы вместо кириллицы)
        'нoль', 'нoл', 'oдин', 'двa', 'трi', 'чeтыре', 'пять', 'шeсть',
        'сeмь', 'вoсемь', 'дeвять', 'дeсять',
        # Дополнительные варианты обхода с заменой букв на цифры
        '0д1н', 'дв@', 'тр1', 'ч3тырe', 'п5т', 'ш3ст',
        'с3м', 'в0сем', 'д3вят', 'д3сят',
        # Варианты с пропущенными буквами (опечатки)
        'нль', 'нл', 'одн', 'дв', 'тр', 'четыре', 'пят', 'шест',
        'сем', 'восем', 'девят', 'десят',
        # Варианты с лишними буквами
        'нольь', 'нульь', 'одинн', 'дваа', 'трии', 'пятьь'
    ]
    
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
        
        # Проверка на комбинации цифр и числительных (более строгая)
        # Если в тексте есть и цифры, и числительные - подозрительно
        has_digits = any(c.isdigit() for c in text)
        has_number_words = any(word in text_lower for word in cls.NUMBER_WORDS)
        if has_digits and has_number_words:
            # Подсчитываем количество групп (цифры или числительные)
            # Разбиваем текст на слова и проверяем, сколько из них - цифры или числительные
            words = text_lower.split()
            number_groups = 0
            consecutive_number_groups = 0
            max_consecutive = 0

            for word in words:
                # Очищаем слово от знаков препинания
                clean_word = re.sub(r'[^\w]', '', word)

                # Проверяем, является ли слово числом или числительным
                is_number = clean_word.isdigit() or any(num_word == clean_word for num_word in cls.NUMBER_WORDS)

                if is_number:
                    number_groups += 1
                    consecutive_number_groups += 1
                    max_consecutive = max(max_consecutive, consecutive_number_groups)
                else:
                    consecutive_number_groups = 0

            # Если есть 3+ группы чисел/числительных подряд или 4+ всего - подозрительно
            if max_consecutive >= 3 or number_groups >= 4:
                logger.warning(f"Suspicious combination of digits and number words detected: {text[:50]} (groups: {number_groups}, consecutive: {max_consecutive})")
                return False, "❌ Обнаружена попытка передачи контакта. Используйте кнопку 'Запросить контакт'."

        # Проверка на номера, написанные словами (комбинации цифр и числительных)
        # Ищем комбинации: цифры + числительные + цифры (минимум 3 группы подряд)
        number_words_pattern = '|'.join(cls.NUMBER_WORDS)
        # Паттерн для обнаружения комбинаций цифр и числительных (минимум 3 подряд)
        mixed_number_pattern = rf'(?:[0-9]{{1,4}}|{number_words_pattern})[\s]+(?:[0-9]{{1,4}}|{number_words_pattern})[\s]+(?:[0-9]{{1,4}}|{number_words_pattern})'
        if re.search(mixed_number_pattern, text_lower, re.IGNORECASE):
            logger.warning(f"Phone number written in words detected: {text[:50]}")
            return False, "❌ Обнаружен номер телефона, написанный словами. Используйте кнопку 'Запросить контакт'."
        
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


def check_message_history_for_contacts(
    message_history: List[str],
    current_message: str,
    user_type: str = "worker"
) -> Tuple[bool, str]:
    """
    Проверяет историю сообщений пользователя на попытки передачи контактов через цифры.
    Анализирует только сообщения конкретного пользователя (исполнителя или заказчика).
    
    Args:
        message_history: Список предыдущих сообщений пользователя (последние N сообщений)
        current_message: Текущее сообщение для проверки
        user_type: Тип пользователя ("worker" или "customer")
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
            - is_valid: True если сообщение допустимо, False если содержит контакты
            - error_message: Описание нарушения (если есть)
    """
    if not message_history:
        message_history = []
    
    # Если история пустая, проверяем только текущее сообщение через обычный фильтр
    # (это делается в обработчиках, здесь мы проверяем только историю)
    if len(message_history) == 0:
        # Для одного сообщения не проверяем историю
        return True, ""
    
    # Добавляем текущее сообщение для анализа
    all_messages = message_history + [current_message]
    
    # Берем последние 10 сообщений для анализа
    recent_messages = all_messages[-10:] if len(all_messages) > 10 else all_messages
    
    # Ключевые слова, разрешающие цифры (контекст цены, адреса и т.д.)
    ALLOWED_CONTEXT_WORDS = [
        'цена', 'стоимость', 'рублей', 'руб', '₽', 'за работу', 'оплата', 'плата',
        'адрес', 'квартира', 'кв', 'дом', 'улица', 'подъезд', 'этаж', 'комната',
        'часов', 'в', 'до', 'после', 'время', 'когда',
        'кв.м', 'метров', 'см', 'мм', 'размер', 'площадь',
        'дней', 'день', 'неделя', 'месяц', 'год',
        'штук', 'шт', 'штука', 'экземпляр'
    ]
    
    # Функция для проверки, содержит ли сообщение разрешенный контекст
    def has_allowed_context(text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        return any(word in text_lower for word in ALLOWED_CONTEXT_WORDS)
    
    # Функция для проверки, является ли сообщение в основном цифрами
    def is_mostly_digits(text: str) -> bool:
        if not text:
            return False
        # Убираем пробелы и знаки препинания
        clean_text = re.sub(r'[\s\.,\-\(\)]', '', text)
        if not clean_text:
            return False
        # Если более 70% символов - цифры, считаем сообщение цифровым
        digit_count = sum(c.isdigit() for c in clean_text)
        return digit_count / len(clean_text) >= 0.7
    
    # Функция для извлечения всех цифр из текста
    def extract_digits(text: str) -> str:
        return ''.join(re.findall(r'\d', text))
    
    # Функция для проверки, может ли последовательность цифр быть номером телефона
    def could_be_phone_number(digits: str) -> bool:
        if len(digits) < 8:
            return False
        
        # Проверяем паттерны российских номеров
        # Формат: 7/8 + 9XX + XXX + XX + XX (11 цифр)
        # Или: 9XX + XXX + XX + XX (10 цифр)
        
        if len(digits) >= 11:
            # Полный номер (11 цифр) - строгая проверка
            if digits[0] in '78' and digits[1] == '9':
                # Проверяем, что это похоже на реальный номер
                # Вторая цифра после 9 должна быть 0-9
                if digits[2].isdigit():
                    return True
            # Также проверяем паттерн 8 + 9 + 0... (890...)
            elif digits[0] == '8' and len(digits) >= 3:
                if digits[1] == '9' and digits[2].isdigit():
                    return True
        elif len(digits) == 10:
            # Номер без первой цифры (10 цифр) - начинается с 9
            if digits[0] == '9' and digits[1].isdigit():
                return True
        elif len(digits) == 9:
            # 9 цифр - может быть номер без первых двух цифр
            if digits[0] == '9' and digits[1].isdigit():
                return True
        elif len(digits) == 8:
            # 8 цифр - подозрительно, но только если начинается с 9
            # Более строгая проверка - должна начинаться с 9XX
            if digits[0] == '9' and digits[1].isdigit() and digits[2].isdigit():
                return True
        
        return False
    
    # Проверка 1: Последовательность цифровых сообщений (3+ подряд)
    # Проверяем только последние сообщения подряд (без текста между ними)
    consecutive_digit_messages = 0
    for msg in reversed(recent_messages):
        # Если сообщение в основном цифры и без разрешенного контекста
        if is_mostly_digits(msg) and not has_allowed_context(msg):
            consecutive_digit_messages += 1
        # Если сообщение содержит значительный текст (не только цифры), прерываем счетчик
        elif len(msg.strip()) > 0 and not is_mostly_digits(msg):
            # Если в сообщении есть текст (не только цифры), это прерывает последовательность
            # Проверяем, что текст достаточно значимый
            words = msg.strip().split()
            # Если есть хотя бы одно нецифровое слово - это нормальное сообщение, прерываем
            non_digit_words = [w for w in words if not w.isdigit() and not re.match(r'^\d+$', w)]
            if len(non_digit_words) > 0:
                break
        else:
            # Пустое сообщение или с контекстом - не прерывает последовательность, но и не считается
            continue
    
    # Блокируем только если 3+ сообщения подряд ТОЛЬКО с цифрами
    # НЕ блокируем 2 сообщения - это может быть нормально (например, цена и количество)
    if consecutive_digit_messages >= 3:
        logger.warning(f"Consecutive digit messages detected: {consecutive_digit_messages} in a row")
        return False, "❌ Обнаружена попытка передачи контакта. Нельзя отправлять 3+ сообщения подряд только с цифрами. Добавьте текст к сообщению."
    
    # Проверка 2: Накопление цифр в истории (8+ цифр, которые могут быть номером)
    # Важно: проверяем только сообщения БЕЗ разрешенного контекста
    all_digits = ''
    messages_with_digits = []
    
    for msg in recent_messages:
        if has_allowed_context(msg):
            # Если есть разрешенный контекст, пропускаем это сообщение полностью
            continue
        
        msg_digits = extract_digits(msg)
        if msg_digits:
            all_digits += msg_digits
            messages_with_digits.append(msg)
    
    # Проверяем, может ли накопленная последовательность быть номером
    if len(all_digits) >= 8:
        # Проверяем последние 11 цифр (длина российского номера)
        last_digits = all_digits[-11:] if len(all_digits) >= 11 else all_digits
        
        # Строгая проверка на паттерн номера
        if could_be_phone_number(last_digits):
            logger.warning(f"Phone number pattern detected in history: {last_digits[:5]}...")
            return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
        
        # Дополнительная проверка: если накопилось 11 цифр - проверяем все возможные паттерны
        if len(all_digits) >= 11:
            # Проверяем последние 11 цифр
            last_11 = all_digits[-11:]
            # Паттерн: 8 + 9 + 0... (890...) - самый распространенный
            if last_11[0] == '8' and len(last_11) > 1 and last_11[1] == '9':
                logger.warning(f"Phone number pattern detected (890...): {last_11[:5]}...")
                return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
            # Паттерн: 7 + 9 + ... (79...)
            elif last_11[0] == '7' and len(last_11) > 1 and last_11[1] == '9':
                logger.warning(f"Phone number pattern detected (79...): {last_11[:5]}...")
                return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
            # Паттерн: начинается с 9 (9...) - номер без первой цифры
            elif last_11[0] == '9' and len(last_11) > 1 and last_11[1].isdigit():
                logger.warning(f"Phone number pattern detected (9...): {last_11[:5]}...")
                return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
        
        # Проверяем также паттерны для 10 цифр (если не 11)
        elif len(all_digits) == 10:
            last_10 = all_digits[-10:]
            # Если начинается с 9 - это номер без первой цифры
            if last_10[0] == '9' and len(last_10) > 1 and last_10[1].isdigit():
                logger.warning(f"Phone number pattern detected (10 digits): {last_10[:5]}...")
                return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
        
        # Дополнительная проверка: если накопилось 11+ цифр, проверяем все возможные комбинации
        if len(all_digits) >= 11:
            # Проверяем все возможные комбинации из 11 цифр
            for i in range(len(all_digits) - 10):  # Проверяем все возможные 11-значные комбинации
                test_digits = all_digits[i:i+11]
                if could_be_phone_number(test_digits):
                    logger.warning(f"Phone number pattern detected in sequence: {test_digits[:5]}...")
                    return False, "❌ Обнаружена попытка передачи номера телефона через несколько сообщений. Используйте кнопку 'Запросить контакт'."
        
        # Проверяем, если накопилось 8+ цифр без контекста
        # Но только если это в 2+ сообщениях и нет текста между ними
        if len(all_digits) >= 8 and len(messages_with_digits) >= 2:
            # Проверяем, нет ли разрешенного контекста в сообщениях с цифрами
            has_any_context = any(has_allowed_context(msg) for msg in messages_with_digits)
            if not has_any_context:
                # Дополнительная проверка: если между сообщениями с цифрами есть текст - это нормально
                # Проверяем, идут ли сообщения с цифрами подряд или между ними есть текст
                digit_indices = []
                for i, msg in enumerate(recent_messages):
                    if msg in messages_with_digits:
                        digit_indices.append(i)
                
                # Если сообщения с цифрами идут подряд (без текста между) - подозрительно
                if len(digit_indices) >= 2:
                    # Проверяем, идут ли индексы подряд
                    consecutive = True
                    for i in range(len(digit_indices) - 1):
                        if digit_indices[i+1] - digit_indices[i] > 1:
                            consecutive = False
                            break
                    
                    # Блокируем только если сообщения с цифрами идут подряд
                    # И если накопилось достаточно цифр (8+)
                    if consecutive and len(all_digits) >= 8:
                        # Дополнительная проверка: если это может быть номер - блокируем строже
                        # Если не похоже на номер, но все равно много цифр подряд - тоже блокируем
                        logger.warning(f"Too many digits accumulated without context: {len(all_digits)} digits in {len(messages_with_digits)} consecutive messages")
                        return False, "❌ Обнаружена попытка передачи контакта. Слишком много цифр без контекста. Используйте кнопку 'Запросить контакт'."
    
    # Проверка 3: Комбинация цифр и числительных в истории
    # Проверяем только сообщения без разрешенного контекста
    messages_to_check = [msg for msg in recent_messages if not has_allowed_context(msg)]
    
    has_digits_in_history = any(extract_digits(msg) for msg in messages_to_check)
    has_number_words = any(
        any(word in msg.lower() for word in ContactFilter.NUMBER_WORDS)
        for msg in messages_to_check
    )
    
    if has_digits_in_history and has_number_words:
        # Подсчитываем количество групп чисел/числительных
        total_number_groups = 0
        for msg in messages_to_check:
            words = msg.lower().split()
            for word in words:
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word.isdigit() or any(num_word == clean_word for num_word in ContactFilter.NUMBER_WORDS):
                    total_number_groups += 1
        
        # Снижаем порог до 5 групп для более строгой проверки
        if total_number_groups >= 5:
            logger.warning(f"Combination of digits and number words detected: {total_number_groups} groups")
            return False, "❌ Обнаружена попытка передачи контакта через комбинацию цифр и слов. Используйте кнопку 'Запросить контакт'."
    
    return True, ""

