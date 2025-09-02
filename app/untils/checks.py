import re
from difflib import SequenceMatcher

from app.data.database.models import BlockWord, BlockWordShort, ProfanityWord, WhiteWord, BlockWordMessage, \
    BlockWordShortMessage, BlockWordPersonal, BlockWordShortPersonal


async def find_links_emails_and_telegram(text):
    website_pattern = r'https?://(?:www\.)?[\w-]+\.[\w.-]+/?'
    websites = re.findall(website_pattern, text)

    telegram_pattern = r'@\w+'
    telegram_usernames = re.findall(telegram_pattern, text)

    email_pattern = r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'
    emails = re.findall(email_pattern, text)

    ban_reason = websites + telegram_usernames + emails

    return ban_reason


def distance(a, b):
    """Calculates the Levenshtein distance between a and b."""
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n, m)) space
        a, b = b, a
        n, m = m, n

    current_row = range(n + 1)  # Keep current and previous row, not entire matrix
    for i in range(1, m + 1):
        previous_row, current_row = current_row, [i] + [0] * n
        for j in range(1, n + 1):
            add, delete, change = previous_row[j] + 1, current_row[j - 1] + 1, previous_row[j - 1]
            if a[j - 1] != b[i - 1]:
                change += 1
            current_row[j] = min(add, delete, change)

    return current_row[n]


def finding_leet(phrase, d):
    for key, value in d.items():
        for letter in value:
            for phr in phrase:
                if letter == phr:
                    phrase = phrase.replace(phr, key)
    return phrase


async def levenshtein_distance_check(phrase: str, words: list['str'], white_words: list['str']):
    d = {'а': ['а', 'a', '@'],
         'б': ['б', '6', 'b'],
         'в': ['в', 'b', 'v'],
         'г': ['г', 'r', 'g'],
         'д': ['д', 'd'],
         'е': ['е', 'e'],
         'ё': ['ё', 'e'],
         'ж': ['ж', 'zh', '*'],
         'з': ['з', '3', 'z'],
         'и': ['и', 'u', 'i'],
         'й': ['й', 'u', 'i'],
         'к': ['к', 'k', 'i{', '|{'],
         'л': ['л', 'l', 'ji'],
         'м': ['м', 'm'],
         'н': ['н', 'h', 'n'],
         'о': ['о', 'o', '0'],
         'п': ['п', 'n', 'p'],
         'р': ['р', 'r', 'p'],
         'с': ['с', 'c', 's'],
         'т': ['т', 'm', 't'],
         'у': ['у', 'y', 'u'],
         'ф': ['ф', 'f'],
         'х': ['х', 'x', 'h', '}{'],
         'ц': ['ц', 'c', 'u,'],
         'ч': ['ч', 'ch'],
         'ш': ['ш', 'sh'],
         'щ': ['щ', 'sch'],
         'ь': ['ь', 'b'],
         'ы': ['ы', 'bi'],
         'ъ': ['ъ'],
         'э': ['э', 'e'],
         'ю': ['ю', 'io'],
         'я': ['я', 'ya']
         }
    ds = [d]
    for i in ds:
        phrase = finding_leet(phrase, i)
        for word in words:
            word = word.lower()
            for part in range(len(phrase)):
                fragment = phrase[part: part + len(word)]
                if distance(fragment.lower(), word) <= len(word) * 0.10:
                    if fragment in white_words:
                        continue
                    find = "Найдено: " + word + "\nПохоже на: " + fragment
                    return find

    return False


async def levenshtein_distance_check_city(phrase: str, words: list):
    ids = []
    phrase = phrase.lower()
    threshold = int(len(phrase) * 0.25)  # Увеличенный порог до 25% от длины введенного слова

    for i, word in enumerate(words, start=1):
        word = word.lower()
        # Сравнение всего слова целиком
        # distance_value = distance(word, phrase)
        for part in range(len(word)):
            fragment = word[part: part + len(phrase)]
            if distance(fragment.lower(), phrase) <= threshold:
                ids.append(i)
                break

    return ids


async def levenshtein_distance_check_faq(phrase: str, words: list['str']):
    i = 1
    for word in words:
        word = word.lower()
        for part in range(len(phrase)):
            fragment = phrase[part: part + len(word)]
            if distance(fragment.lower(), word.lower()) <= len(word) * 0.25:
                return i
        i += 1

    return None


def find_phone_numbers_first(text):
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    phone_numbers = re.findall(phone_pattern, text)
    if phone_numbers:
        return True
    else:
        return False


def find_phone_numbers_second(text):
    phone_pattern = re.compile(r'\b[78]\d{10}\b')
    match = phone_pattern.search(text)
    if match:
        return True
    else:
        return False


def find_phone_numbers_third(text):
    phone_pattern = re.compile(r'\b(?:\d{3}[-.\s()]?\d{3}[-.\s()]?\d{4}|\d{10})\b')
    match = phone_pattern.search(text)
    if match:
        return True
    else:
        return False


def contains_phone_number(text):
    phone_pattern = re.compile(r'\b(?:\d{3}[-.\s()]?\d{3}[-.\s()]?\d{4}|\d{10})\b')
    match = phone_pattern.search(text)
    if match:
        return True
    else:
        return False


def check_digits_in_text(text):
    text = text.replace(" ", "")

    pattern = re.compile(r'\d{5,}')

    matches = pattern.finditer(text)

    for match in matches:
        start, end = match.span()
        if not re.search(r'[а-яА-Я]', text[start:end]):
            return True

    return False


def contains_word_phone_number(text):
    number_words = {
        'ноль': '0', 'один': '1', 'два': '2', 'три': '3', 'четыре': '4',
        'пять': '5', 'шесть': '6', 'семь': '7', 'восемь': '8', 'девять': '9', 'нуль': '0'
    }
    phone_pattern = re.compile(
        r'\b(?:нуль|ноль|один|два|три|четыре|пять|шесть|семь|восемь|девять)(?:\s(?:ноль|один|два|три|четыре|пять|шесть|семь|восемь|девять)){10}\b')

    matches = phone_pattern.findall(text)

    for match in matches:
        digits = ''.join(number_words[word] for word in match.split())
        if len(digits) == 11 and digits[0] in '78':
            return True
        elif len(digits) == 10:
            return True

    return False


def find_phone_number(text):
    patterns = [
        r'\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}',
        r'\d[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}',
        r'\d[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}',
        r'\d{3}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{2}[-\s.,/\\()\[\]{}:;\'"?!@#%^&*_+=|<>~`]\d{3}'
    ]

    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


def phone_finder(text):
    if find_phone_numbers_first(text):
        return True
    elif find_phone_numbers_second(text):
        return True
    elif contains_phone_number(text):
        return True
    elif check_digits_in_text(text):
        return True
    elif contains_word_phone_number(text):
        return True
    elif find_phone_number(text):
        return True
    return False


def find_and_remove_phone_numbers(text):
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    text_without_phones = re.sub(phone_pattern, '', text)
    return text_without_phones


def contains_invalid_chars(text):
    # Проверяем, если в тексте есть символы, которые не являются русскими буквами, цифрами или спецсимволами
    if re.search(r'[^А-Яа-яЁё0-9\s.,!?#$%^&*()\-_=+\\|;:\'\"<>/{}[\]~`]', text):
        return True
    return False


async def contains_profanity(text, profanity_list):
    lower_text = text.lower()

    for word in profanity_list:
        if re.search(r'\b' + re.escape(word) + r'\b', lower_text):
            return f'Найдено: {word}'
    return False


def replace_yo_with_e(text):
    return text.replace('ё', 'е').replace('Ё', 'Е')


async def are_texts_similar(text1, text2):
    """
    Проверяет схожесть двух текстов.

    :param text1: Первый текст для сравнения
    :param text2: Второй текст для сравнения
    :return: True, если схожесть более 90%, иначе False
    """
    matcher = SequenceMatcher(None, text1, text2)
    similarity_ratio = matcher.ratio()

    return similarity_ratio > 0.75


async def fool_check(text, is_message: bool = False, is_personal: bool = False):
    if is_message:
        block_words = await BlockWordMessage.get_all()
        short_block_words = await BlockWordShortMessage.get_all()
    elif is_personal:
        block_words = await BlockWordPersonal.get_all()
        short_block_words = await BlockWordShortPersonal.get_all()
    else:
        block_words = await BlockWord.get_all()
        short_block_words = await BlockWordShort.get_all()

    block_words = [block_word.word for block_word in block_words]
    short_block_words = [short_block_words.word for short_block_words in short_block_words]

    profanity_words = await ProfanityWord.get_all()
    profanity_words = [profanity_word.word for profanity_word in profanity_words]
    white_words = await WhiteWord.get_all()
    white_words = [white_word.word for white_word in white_words]

    text = replace_yo_with_e(text)

    if ban_reason := await contains_profanity(text, profanity_words):
        return ban_reason
    elif ban_reason := await contains_profanity(text, short_block_words):
        return ban_reason
    elif ban_reason := await levenshtein_distance_check(phrase=text, words=block_words, white_words=white_words):
        return ban_reason
    else:
        return False


def is_random_string(text: str) -> bool:
    # Проверяем, содержит ли строка достаточно разнообразные символы и нет ли осмысленных слов
    return len(set(text)) > len(text) * 0.5 and not re.search(r'\b[а-яА-Я]{3,}\b', text)


def contains_gibberish(text: str) -> bool:
    # Проверяем, является ли строка случайным набором символов
    return is_random_string(text) and bool(re.search(r'(.)\1{2,}.*(.)\2{2,}', text))


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
