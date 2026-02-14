import os
import re
import json
import time
import shutil
import logging
import requests
from aiogram.exceptions import TelegramBadRequest
from bs4 import BeautifulSoup
from datetime import datetime, date
from PIL import Image, ImageEnhance
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.data.database.models import Abs, City, WorkerStatus
from app.keyboards import KeyboardCollection
from app.states import CustomerStates
from loaders import bot

logger = logging.getLogger(__name__)


def check_ip_status_by_ogrnip(ogrnip) -> str | None:
    """Проверка ИП по ОГРНИП"""
    url = f"https://www.rusprofile.ru/ip/{ogrnip}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        status_element = soup.find('h2', class_='company-name')
        if status_element:
            company_name = status_element.text.strip()
            return company_name
        else:
            return None

    except requests.exceptions.RequestException:
        return None


def check_ooo(query) -> bool | str:
    """Проверка ООО по ОГРН"""
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Referer": "https://egrul.nalog.ru/index.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        response = requests.post("https://egrul.nalog.ru/", data={"query": query}, headers=headers)
        response.raise_for_status()

        data = response.json()  # вернёт строку с ID
        request_id = data.get("t")
        if request_id:
            time.sleep(1.5)

            params = {
                "r": str(int(time.time() * 1000)),
                "_": str(int(time.time() * 1000)),
            }
            result = requests.get(
                f"https://egrul.nalog.ru/search-result/{request_id}",
                headers=headers,
                params=params,
                timeout=10
            )
            result.raise_for_status()

            data = result.json()
            rows = data.get("rows", [])
            for row in rows:
                if row.get("k") == "ul" and row.get("cnt", 0) != 0:
                    return True
        return False
    except Exception as e:
        logger.warning(f"Error in check_ooo: {e}")
        return "error"


def check_npd(inn) -> bool | str:
    """Проверка самозанятого (НПД) по ИНН"""
    url = "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status"

    payload = {
        "inn": inn,
        "requestDate": str(date.today())
    }

    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return data.get("status", False)
        return False
    except Exception as e:
        logger.warning(f"Error in check_npd: {e}")
        return "error"


def get_obj_name_and_id_for_btn(names: list, ids: list, id_now: int):
    if len(names) > 5:
        names = names[id_now:]
        ids = ids[id_now:]
        if len(names) > 5:
            names = names[:5]
            ids = ids[:5]
            return names, ids
    return names, ids


def get_pure_phone(raw: str) -> str:
    """
    Функция для получения чистого номера телефона без дополнительных символов.

    Args:
        raw (str): Исходная строка с номером телефона.

    Returns:
        str: Очищенный номер телефона.
    """
    ban_symbols = ["+", "(", ")", "-", " "]
    for symbol in ban_symbols:
        raw = raw.replace(symbol, "")
    if raw[0] == "8":
        raw = "7" + raw[1: len(raw)]
    return raw


def create_file_in_directory_with_timestamp(id, text, path: str = 'app/data/text/'):
    # Создаем имя папки на основе id
    directory = path + str(id)

    # Проверяем, существует ли папка, если нет, создаем ее
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Получаем текущий timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Формируем имя файла
    filename = f"{id}_{timestamp}.txt"

    # Полный путь к файлу
    filepath = os.path.join(directory, filename)

    # Создаем и открываем файл для записи
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(text)

    return f'{directory}/{filename}'


async def save_photo(id: int, path: str = 'app/data/photo/'):
    # Создаем имя папки на основе id
    directory = path + str(id)

    # Проверяем, существует ли папка, если нет, создаем ее
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Получаем текущий timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Формируем имя файла
    filename = f"{id}_{timestamp}.jpg"

    return f'{directory}/{filename}'


def get_grade_word(number: int) -> str:
    # Выделяем последние две цифры числа
    last_two_digits = number % 100
    last_digit = number % 10

    # Проверяем исключения для 11-14
    if 11 <= last_two_digits <= 14:
        return "оценок"

    # Определяем окончание на основе последней цифры
    if last_digit == 1:
        return "оценка"
    elif 2 <= last_digit <= 4:
        return "оценки"
    else:
        return "оценок"


async def save_photo_var(id: int, path: str = 'app//data//photo//', n: int = 0):
    if path == 'app//data//photo//':
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{id}_{timestamp}"
        directory = path + str(id)
        directory = f'{directory}//{filename}//'
    else:
        directory = path

    if not os.path.exists(directory):
        os.makedirs(directory)

    while os.path.exists(f'{directory}//{n}.jpg'):
        n += 1
    return f'{directory}//', n


async def save_portfolio_photo(user_id: int, photo_key: int):
    """
    Сохраняет фото портфолио в правильную структуру папок:
    app/data/photo/{user_id}/portfolio/{photo_key}.jpg
    """
    # Создаем путь для портфолио пользователя
    portfolio_dir = f'app/data/photo/{user_id}/portfolio'

    # Создаем папку если не существует
    if not os.path.exists(portfolio_dir):
        os.makedirs(portfolio_dir)

    # Возвращаем путь к папке и имя файла
    return portfolio_dir, f'{photo_key}.jpg'


def migrate_portfolio_to_user_folder(portfolio_dict: dict, user_id: int):
    """
    Мигрирует существующие фото портфолио в папку пользователя.
    Перемещает файлы из общей папки в app/data/photo/{user_id}/portfolio/
    
    Args:
        portfolio_dict: Словарь с путями к фото портфолио
        user_id: ID пользователя
        
    Returns:
        dict: Обновленный словарь с новыми путями
    """
    if not portfolio_dict:
        return portfolio_dict

    # Создаем папку для портфолио пользователя
    portfolio_dir = f'app/data/photo/{user_id}/portfolio'
    if not os.path.exists(portfolio_dir):
        os.makedirs(portfolio_dir)

    new_portfolio = {}

    for key, old_path in portfolio_dict.items():
        if os.path.exists(old_path):
            # Создаем новое имя файла
            new_filename = f'{key}.jpg'
            new_path = os.path.join(portfolio_dir, new_filename)

            try:
                # Перемещаем файл
                import shutil
                shutil.move(old_path, new_path)
                new_portfolio[key] = new_path
                logger.info(f"[PORTFOLIO_MIGRATION] Файл перемещен: {old_path} -> {new_path}")
            except Exception as e:
                logger.error(f"[PORTFOLIO_MIGRATION] Ошибка перемещения файла {old_path}: {e}")
                # Если не удалось переместить, оставляем старый путь
                new_portfolio[key] = old_path
        else:
            logger.warning(f"[PORTFOLIO_MIGRATION] Файл не найден: {old_path}")
            # Если файл не существует, не добавляем его в новый словарь

    return new_portfolio


def delete_file(file_path):
    """
    Безопасно удаляет файл с диска с логированием.
    
    Args:
        file_path: Путь к файлу для удаления
        
    Returns:
        bool: True если файл успешно удален, False в противном случае
    """
    if not file_path:
        return False

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Файл успешно удален: {file_path}")
            return True
        else:
            logger.warning(f"Файл не найден для удаления: {file_path}")
            return False
    except PermissionError:
        logger.error(f"Нет прав для удаления файла: {file_path}")
        return False
    except OSError as e:
        logger.error(f"Ошибка ОС при удалении файла {file_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при удалении файла {file_path}: {e}")
        return False


def delete_folder(folder_path):
    try:
        for root, dirs, files in os.walk(folder_path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(folder_path)
    except Exception:
        pass


def cleanup_orphaned_portfolio_files():
    """
    Очищает "осиротевшие" файлы (фото профиля и портфолио), которые не связаны ни с одним исполнителем.
    Проверяет:
    - Файлы в папке пользователя (app/data/photo/{user_id}/) - фото профиля и старые файлы портфолио
    - Файлы в папке portfolio (app/data/photo/{user_id}/portfolio/) - новые файлы портфолио
    
    Эта функция должна вызываться периодически для поддержания чистоты файловой системы.
    
    Returns:
        int: Количество удаленных файлов
    """
    portfolio_base_path = 'app/data/photo/'
    if not os.path.exists(portfolio_base_path):
        logger.info("Папка фото не существует, очистка не требуется")
        return 0

    logger.info("Начинаем очистку осиротевших файлов (профиль и портфолио)...")

    # Получаем все папки с ID пользователей
    user_folders = [f for f in os.listdir(portfolio_base_path)
                    if os.path.isdir(os.path.join(portfolio_base_path, f)) and f.isdigit()]

    cleaned_count = 0
    checked_folders = 0

    for folder in user_folders:
        folder_path = os.path.join(portfolio_base_path, folder)
        checked_folders += 1

        try:
            # 1. Проверяем файлы в самой папке пользователя (фото профиля и старые файлы портфолио)
            files = os.listdir(folder_path)
            for item in files:
                item_path = os.path.join(folder_path, item)

                # Пропускаем папки (например, portfolio)
                if os.path.isdir(item_path):
                    continue

                # Проверяем только .jpg файлы
                if item.endswith('.jpg'):
                    # Проверяем, используется ли файл (profile_photo или старое portfolio_photo)
                    if is_file_orphaned(item_path):
                        # Удаляем осиротевший файл
                        if delete_file(item_path):
                            cleaned_count += 1
                            logger.info(f"Удален осиротевший файл из папки пользователя: {item_path}")
                        else:
                            logger.warning(f"Не удалось удалить файл: {item_path}")
                    else:
                        logger.debug(f"Файл используется: {item_path}")

            # 2. Проверяем файлы в подпапке portfolio (новые файлы портфолио)
            portfolio_folder = os.path.join(folder_path, 'portfolio')
            if os.path.exists(portfolio_folder) and os.path.isdir(portfolio_folder):
                try:
                    portfolio_files = os.listdir(portfolio_folder)
                    for file in portfolio_files:
                        if file.endswith('.jpg'):
                            file_path = os.path.join(portfolio_folder, file)

                            # Проверяем, используется ли файл в портфолио
                            if is_file_orphaned(file_path):
                                # Удаляем осиротевший файл
                                if delete_file(file_path):
                                    cleaned_count += 1
                                    logger.info(f"Удален осиротевший файл портфолио: {file_path}")
                                else:
                                    logger.warning(f"Не удалось удалить файл портфолио: {file_path}")
                            else:
                                logger.debug(f"Файл портфолио используется: {file_path}")
                except Exception as e:
                    logger.error(f"Ошибка при проверке папки portfolio {portfolio_folder}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при проверке папки {folder_path}: {e}")

    logger.info(f"Очистка завершена. Проверено папок: {checked_folders}, удалено файлов: {cleaned_count}")
    return cleaned_count


def is_file_orphaned(file_path):
    """
    Проверяет, является ли файл "осиротевшим" (не используется в портфолио исполнителей).
    
    Args:
        file_path: Путь к файлу для проверки
        
    Returns:
        bool: True если файл осиротевший, False если используется
    """
    try:
        # Импортируем модель Worker для проверки БД
        import asyncio

        # Создаем новый event loop для синхронного вызова
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Выполняем асинхронную проверку синхронно
        return loop.run_until_complete(_check_file_in_database(file_path))

    except Exception as e:
        logger.error(f"Ошибка при проверке файла {file_path}: {e}")
        # В случае ошибки считаем файл не осиротевшим (безопасный подход)
        return False


async def _check_file_in_database(file_path):
    """
    Асинхронная проверка использования файла в базе данных.
    
    Args:
        file_path: Путь к файлу для проверки
        
    Returns:
        bool: True если файл осиротевший, False если используется
    """
    try:
        # Локальный импорт для избежания циклических зависимостей
        from app.data.database.models import Worker

        # Получаем всех исполнителей
        workers = await Worker.get_all()

        for worker in workers:
            if worker.portfolio_photo:
                # Проверяем, используется ли файл в портфолио этого исполнителя
                for photo_path in worker.portfolio_photo.values():
                    if photo_path == file_path:
                        return False  # Файл используется

            # Также проверяем фото профиля
            if worker.profile_photo == file_path:
                return False  # Файл используется как фото профиля

        # Если файл не найден ни в одном портфолио
        return True

    except Exception as e:
        logger.error(f"Ошибка при проверке файла в БД {file_path}: {e}")
        return False


def read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return f"{content}\n\n"
    except FileNotFoundError:
        return "Файл не найден"
    except Exception:
        return "Ошибка чтения файла"


def add_watermark(input_image_path, transparency=0.5):
    output_image_path = input_image_path
    watermark_image_path = 'app/data/database/watermark.png'
    base_image = Image.open(input_image_path).convert("RGBA")
    watermark = Image.open(watermark_image_path).convert("RGBA")

    # Установка прозрачности водяного знака
    watermark = ImageEnhance.Brightness(watermark).enhance(transparency)

    base_width, base_height = base_image.size
    watermark_width, watermark_height = watermark.size

    # Координаты для правого нижнего угла
    position = (
        base_width - watermark_width,
        base_height - watermark_height
    )

    # Создание нового изображения с прозрачным фоном
    transparent = Image.new('RGBA', (base_width, base_height), (0, 0, 0, 0))

    # Копирование базового изображения и водяного знака на новое изображение
    transparent.paste(base_image, (0, 0))
    transparent.paste(watermark, position, mask=watermark)

    # Конвертация изображения в формат RGB и сохранение результата
    result = transparent.convert("RGB")
    result.save(output_image_path)


def copy_file(source_path: str, destination_dir: str):
    """
    Копирует файл из source_path в destination_dir, сохраняя имя файла.

    :param source_path: Путь к исходному файлу.
    :param destination_dir: Путь к целевой директории.
    """
    try:
        file_name = os.path.basename(source_path)
        destination_path = os.path.join(destination_dir, file_name)
        shutil.copy(source_path, destination_path)
        return destination_path
    except Exception:
        return False


def telegraph_file_upload(path_to_file):
    """
    Sends a file to telegra.ph storage and returns its URL.
    Works ONLY with 'gif', 'jpeg', 'jpg', 'png', 'mp4'.

    Parameters:
    ---------------
    path_to_file : str
        Path to a local file.

    Returns:
    ---------------
    str : URL of the uploaded file, or an error message.
    """
    file_types = {'gif': 'image/gif', 'jpeg': 'image/jpeg', 'jpg': 'image/jpg', 'png': 'image/png', 'mp4': 'video/mp4'}
    file_ext = path_to_file.split('.')[-1].lower()

    if file_ext not in file_types:
        return f'Error: {file_ext}-file cannot be processed.'

    file_type = file_types[file_ext]

    try:
        with open(path_to_file, 'rb') as f:
            url = 'https://telegra.ph/upload'
            response = requests.post(url, files={'file': ('file', f, file_type)}, timeout=5)

        # Проверяем статус ответа
        if response.status_code != 200:
            return f"Error: Upload failed with status {response.status_code}. Response: {response.text}"

        # Проверяем формат данных
        try:
            telegraph_url = json.loads(response.content)
            if isinstance(telegraph_url, list) and "src" in telegraph_url[0]:
                telegraph_url = telegraph_url[0]['src']
                return f'https://telegra.ph{telegraph_url}'
            else:
                return f"Error: Unexpected response format: {telegraph_url}"
        except json.JSONDecodeError:
            return f"Error: Failed to decode JSON response: {response.text}"

    except requests.exceptions.RequestException as e:
        return f"Error: Request to Telegraph failed: {e}"


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы в тексте для использования в Telegram с Markdown.

    :param text: Исходный текст.
    :return: Экранированный текст.
    """
    escape_chars = r'_*~'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)


def is_content_forbidden(text: str, ann: bool = None) -> bool:
    """
    Проверяет, содержит ли текст запрещенный контент (ссылки, упоминания, номера прописью).
    
    Args:
        text: Текст для проверки
        ann: Если размешаем объявление не нужно проверить комбинации цифр и слов (например: "8 девять")
        
    Returns:
        bool: True если контент запрещен, False если разрешен
    """
    if not text:
        return False

    text_lower = text.lower().strip()

    # Проверка на ссылки (http, https, www, домены)
    url_patterns = [
        r'https?://',  # http:// или https://
        r'www\.',  # www.
        r'\.(com|ru|org|net|info|biz|co|io|me|tv|cc|tk|ml|ga|cf)',  # домены
        r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # общий паттерн доменов
    ]

    for pattern in url_patterns:
        if re.search(pattern, text_lower):
            return True

    # Проверка на упоминания через @ (только латиница)
    if re.search(r'@[a-zA-Z0-9_]+', text_lower):
        return True

    if not ann:
        # Проверка на номера прописью (русские)
        forbidden_numbers = [
            'ноль', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять',
            'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать',
            'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать', 'двадцать',
            'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто',
            'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот',
            'тысяча', 'тысяч', 'миллион', 'миллионов'
        ]

        # Разбиваем текст на слова и проверяем каждое
        words = re.findall(r'\b\w+\b', text_lower)
        for word in words:
            if word in forbidden_numbers:
                return True

        # Проверка на комбинации цифр и слов (например: "8 девять")
        if re.search(r'\d+\s+(ноль|один|два|три|четыре|пять|шесть|семь|восемь|девять)', text_lower):
            return True

    return False


async def check_contact_already_sent(worker_id: int, abs_id: int) -> bool:
    """
    Проверяет, были ли уже отправлены контакты заказчика исполнителю.
    
    Args:
        worker_id: ID исполнителя
        abs_id: ID объявления
        
    Returns:
        bool: True если контакты уже отправлены, False если нет
    """
    try:
        # Локальный импорт для избежания циклических зависимостей
        from app.data.database.models import ContactExchange

        # Используем новую модель ContactExchange
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)

        if contact_exchange and contact_exchange.contacts_sent:
            return True

        return False

    except Exception as e:
        logger.error(f"Ошибка при проверке отправки контактов: {e}")
        return False


async def process_contact_purchase(worker_id: int, tariff_type: str, tariff_value: int, tariff_price: int) -> bool:
    """
    Обрабатывает покупку контактов исполнителем.
    
    Args:
        worker_id: ID исполнителя
        tariff_type: Тип тарифа ('limited' или 'unlimited')
        tariff_value: Значение тарифа (количество контактов или месяцев)
        tariff_price: Цена тарифа в копейках
        
    Returns:
        bool: True если покупка успешна, False если нет
    """
    try:
        from app.data.database.models import Worker
        from datetime import datetime, timedelta

        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            logger.error(f"Worker not found: {worker_id}")
            return False

        if tariff_type == 'unlimited':
            # Безлимитный тариф
            days = tariff_value * 30 if tariff_value == 1 else tariff_value * 90 if tariff_value == 3 else tariff_value * 180 if tariff_value == 6 else 365

            end_date = datetime.now() + timedelta(days=days)
            end_date_str = end_date.strftime("%Y-%m-%d")

            await worker.update_purchased_contacts(unlimited_contacts_until=end_date_str)
            logger.info(f"Unlimited contacts activated for worker {worker_id} until {end_date_str}")

        else:
            # Ограниченный тариф
            current_contacts = worker.purchased_contacts or 0
            new_contacts = current_contacts + tariff_value

            await worker.update_purchased_contacts(purchased_contacts=new_contacts)
            logger.info(f"Added {tariff_value} contacts to worker {worker_id}. Total: {new_contacts}")

        return True

    except Exception as e:
        logger.error(f"Error processing contact purchase: {e}")
        return False


def is_unlimited_active(worker) -> tuple[bool, str | None]:
    """
    Проверяет, активен ли безлимитный доступ у исполнителя.
    
    Args:
        worker: Объект Worker
        
    Returns:
        tuple[bool, str | None]: (is_active, unlimited_until)
            - is_active: True если безлимит активен, False если нет или истек
            - unlimited_until: строка с датой окончания или None
    """
    if not worker or not worker.unlimited_contacts_until:
        return False, None

    from datetime import datetime

    try:
        # Пробуем разные форматы даты
        date_str = str(worker.unlimited_contacts_until).strip()
        end_date = None

        # Пробуем fromisoformat (основной метод)
        try:
            end_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # Если не получилось, пробуем strptime с разными форматами
            formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]
            for fmt in formats:
                try:
                    end_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        if end_date:
            # Проверяем, что дата не истекла (>= для включения текущего дня)
            is_active = end_date >= datetime.now()
            return is_active, worker.unlimited_contacts_until
        else:
            return False, worker.unlimited_contacts_until

    except Exception as e:
        logger.error(f"Error parsing unlimited_contacts_until: {e}, value: {worker.unlimited_contacts_until}")
        return False, worker.unlimited_contacts_until


async def check_worker_has_unlimited_contacts(worker_id: int) -> bool:
    """
    Проверяет, есть ли у исполнителя активный безлимитный доступ к контактам.
    
    Args:
        worker_id: ID исполнителя
        
    Returns:
        bool: True если есть безлимитный доступ, False если нет
    """
    try:
        # Локальный импорт для избежания циклических зависимостей
        from app.data.database.models import Worker

        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            return False

        # Проверяем безлимитный доступ
        is_active, _ = is_unlimited_active(worker)
        if is_active:
            return True

        # Проверяем количество купленных контактов
        if worker.purchased_contacts and worker.purchased_contacts > 0:
            return True

        return False

    except Exception as e:
        logger.error(f"Error checking unlimited contacts for worker {worker_id}: {e}")
        return False


async def handle_forbidden_content(message) -> bool:
    """
    Обрабатывает сообщение с запрещенным контентом.
    
    Args:
        message: Сообщение пользователя

    Returns:
        bool: True если контент запрещен и обработан, False если разрешен
    """
    try:
        if is_content_forbidden(message.text, ann=True):
            # Отправляем уведомление о запрещенном контенте
            await message.answer(
                "Запрещённый контент или контактные данные. Исправьте и отправьте снова 🚫",
                reply_markup=None
            )
            logger.warning(f"Запрещенный контент от пользователя {message.chat.id}: {message.text}")
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при обработке запрещенного контента: {e}")
        return False


def reorder_dict(d, removed_key):
    """
    Переупорядочивает словарь, удаляя указанный ключ и перенумеровывая остальные.
    
    Args:
        d: Словарь для переупорядочивания
        removed_key: Ключ для удаления
        
    Returns:
        tuple: (новый_словарь, путь_к_удаленному_файлу) или (новый_словарь, None)
    """
    keys = sorted(d.keys(), key=int)  # Сортируем ключи как числа
    if removed_key not in keys:
        return d, None  # Если ключа нет, возвращаем словарь без изменений

    new_dict = {}
    index = 1  # Начинаем нумерацию с "1"
    removed_file_path = None

    for key in keys:
        if key == removed_key:
            removed_file_path = d[key]  # Сохраняем путь к удаляемому файлу
            continue  # Пропускаем удаляемый ключ
        new_dict[str(index)] = d[key]
        index += 1  # Увеличиваем индекс

    return new_dict, removed_file_path


def remove_portfolio_photo(d, removed_key):
    """
    Удаляет фото из портфолио без перенумерации ключей.
    
    Args:
        d: Словарь портфолио
        removed_key: Ключ для удаления
        
    Returns:
        tuple: (новый_словарь, путь_к_удаленному_файлу) или (новый_словарь, None)
    """
    if removed_key not in d:
        return d, None  # Если ключа нет, возвращаем словарь без изменений

    # Создаем копию словаря и удаляем нужный ключ
    new_dict = d.copy()
    removed_file_path = new_dict.pop(removed_key, None)

    return new_dict, removed_file_path


def calculate_worker_rating(stars: int, count_ratings: int) -> float:
    """
    Рассчитывает рейтинг исполнителя с учетом стартового фонда 25 звезд.
    
    Стартовый фонд: 25 звезд (эквивалент 5 оценок по 5 звезд)
    Если нет оценок (count_ratings = 0), возвращает 5.0
    Если есть оценки, считает: (stars + 25) / (count_ratings + 5)
    Максимальный рейтинг ограничен 5.0
    
    Args:
        stars: Количество звезд в БД (реальные оценки)
        count_ratings: Количество оценок в БД (реальные оценки)
    
    Returns:
        float: Рассчитанный рейтинг с учетом стартового фонда (максимум 5.0)
    """
    if count_ratings == 0:
        return 5.0

    # Стартовый фонд: 25 звезд (5 оценок по 5 звезд)
    STARTING_STARS = 25
    STARTING_RATINGS = 5

    total_stars = stars + STARTING_STARS
    total_ratings = count_ratings + STARTING_RATINGS

    rating = total_stars / total_ratings

    # Ограничиваем максимальный рейтинг 5.0
    if rating > 5.0:
        return 5.0

    return rating


def format_rating(rating: float) -> str:
    """
    Форматирует рейтинг для отображения.
    Если рейтинг круглый (например 4.0), возвращает "4"
    Если не круглый (например 4.3), возвращает "4.3" (один знак после запятой)
    
    Args:
        rating: Рейтинг как float
    
    Returns:
        str: Отформатированный рейтинг
    """
    # Округляем до одного знака после запятой
    rounded = round(rating, 1)

    # Если круглое число (например 4.0), убираем .0
    if rounded == int(rounded):
        return str(int(rounded))
    else:
        return f"{rounded:.1f}"


def get_worker_rating_display(stars: int, count_ratings: int) -> tuple[str, int]:
    """
    Получает отображаемый рейтинг и количество оценок для исполнителя.
    
    Args:
        stars: Количество звезд в БД
        count_ratings: Количество оценок в БД
    
    Returns:
        tuple[str, int]: (отформатированный рейтинг, реальное количество оценок)
    """
    rating = calculate_worker_rating(stars, count_ratings)
    formatted_rating = format_rating(rating)
    return formatted_rating, count_ratings


def get_month_word(months):
    # Формируем правильное склонение для месяца

    if months == 1:
        month_word = "месяц"
    elif months in [2, 3, 4]:
        month_word = "месяца"
    else:
        month_word = "месяцев"

    return month_word


def get_contact_word(contacts: int) -> str:
    # Берём последние две цифры (на случай чисел типа 11–14)
    last_two = contacts % 100
    last_one = contacts % 10

    if 11 <= last_two <= 14:
        return "контактов"
    elif last_one == 1:
        return "контакт"
    elif 2 <= last_one <= 4:
        return "контакта"
    else:
        return "контактов"


def get_rating_word(ratings: int) -> str:
    """
    Возвращает правильное склонение слова "оценка" в зависимости от числа.
    
    Правила:
    - 1, 21, 31, 41... → "оценка"
    - 2, 3, 4, 22, 23, 24, 32, 33, 34... → "оценки"
    - 5-20, 25-30... → "оценок"
    
    Args:
        ratings: Количество оценок
    
    Returns:
        str: Правильно склоненное слово "оценка"
    """
    # Берём последние две цифры (на случай чисел типа 11–14)
    last_two = ratings % 100
    last_one = ratings % 10

    if 11 <= last_two <= 14:
        return "оценок"
    elif last_one == 1:
        return "оценка"
    elif 2 <= last_one <= 4:
        return "оценки"
    else:
        return "оценок"


async def send_customer_menu(event, customer, state=None, message=None):
    kbc = KeyboardCollection()
    user_abs = await Abs.get_all_by_customer(customer.id)
    city = await City.get_city(id=int(customer.city_id))

    text = (
        'Ваш профиль\n\n'
        f'ID: {customer.id}\n'
        f'Ваш город: {city.city}\n'
        f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
        f'Осталось объявлений на сегодня: {customer.abs_count}'
    )
    if not message:
        await event.message.answer(text=text, reply_markup=kbc.menu_customer_keyboard())
    else:
        await event.answer(text=text, reply_markup=kbc.menu_customer_keyboard())

    if state:
        await state.set_state(CustomerStates.customer_menu)


async def update_worker_or_customer_chat_status(message, data, state, worker=None):
    kbc = KeyboardCollection()

    if worker:
        # Перед отправкой нового статуса пытаемся удалить предыдущий, чтобы не копить уведомления
        worker_status_message_id = data.get('worker_chat_status_message_id')
        if worker_status_message_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=worker_status_message_id)
            except TelegramBadRequest:
                logger.debug(
                    f"[WORKER_CHAT] Could not delete previous status message {worker_status_message_id} in chat {message.chat.id}"
                )
            except Exception as delete_error:
                logger.error(f"[WORKER_CHAT] Unexpected error deleting status message: {delete_error}")

        # Кнопка "Продолжить" открывает карточку отклика с историей и кнопками
        abs_id = data.get('current_chat_abs_id')
        reply_markup = None
        if abs_id:
            builder = InlineKeyboardBuilder()
            # Открываем экран моего отклика (включает историю и действия)
            builder.add(kbc._inline(button_text="Продолжить", callback_data=f"view_my_response_{abs_id}"))
            builder.adjust(1)
            reply_markup = builder.as_markup()

        sent_status_message = await message.answer("Сообщение успешно отправлено ✅", reply_markup=reply_markup)
        await state.update_data(worker_chat_status_message_id=sent_status_message.message_id)
    else:
        # Перед отправкой нового статуса пытаемся удалить предыдущий, чтобы не копить уведомления
        customer_status_message_id = data.get('customer_chat_status_message_id')
        if customer_status_message_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=customer_status_message_id)
            except TelegramBadRequest:
                logger.debug(
                    f"[CUSTOMER_CHAT] Could not delete previous status message {customer_status_message_id} in chat {message.chat.id}"
                )
            except Exception as delete_error:
                logger.error(f"[CUSTOMER_CHAT] Unexpected error deleting status message: {delete_error}")

        # Кнопка "Продолжить" возвращает заказчика к истории отклика (просмотр отклика)
        abs_id = data.get('current_chat_abs_id')
        worker_id = data.get('current_chat_worker_id')
        reply_markup = None
        if abs_id and worker_id:
            builder = InlineKeyboardBuilder()
            # Показываем карточку отклика, где выводится история переписки
            builder.add(kbc._inline(button_text="Продолжить", callback_data=f"view_response_{worker_id}_{abs_id}"))
            builder.adjust(1)
            reply_markup = builder.as_markup()

        sent_status_message = await message.answer("Сообщение успешно отправлено ✅", reply_markup=reply_markup)
        await state.update_data(customer_chat_status_message_id=sent_status_message.message_id)


async def send_notification_to_customer(customer, worker, abs_id: int, ad_text: str | None = None):
    """
    Отправляет заказчику уведомление о передаче контактов исполнителю.

    :param customer: Объект заказчика (должен содержать tg_id)
    :param worker: Объект исполнителя (должен содержать id)
    :param abs_id: ID объявления
    :param ad_text: Текст объявления (необязательно)
    """
    from app.untils.notification_helper import create_notification

    kbc = KeyboardCollection()

    # Формируем текст уведомления
    notification_text = (
        f"✅ <b>Контакты переданы исполнителю!</b>\n\n"
        f"📋 Объявление: #{abs_id}\n"
        f"👤 Исполнитель: ID#{worker.id}\n\n"
    )
    if ad_text:
        notification_text += f"📝 <b>Текст объявления:</b>\n{ad_text}"
    notification_text += "🔒 Чат закрыт — теперь вы можете продолжить общение напрямую."

    # Создаем уведомление (Smart Logic)
    # Используем тип 'info' или 'contact_shared', который НЕ критичный, чтобы использовать умную логику
    should_push = await create_notification(
        tg_id=customer.tg_id,
        notification_type='info',
        title=f"Контакты переданы исполнителю (Заказ #{abs_id})",
        body=notification_text,
        payload={'abs_id': abs_id, 'worker_id': worker.id},
        bot=bot
    )

    if should_push:
        # Отправляем сообщение только если вернулось True (или для критичных, или ошибка)
        await bot.send_message(
            chat_id=customer.tg_id,
            text=notification_text,
            parse_mode="HTML",
            reply_markup=kbc.menu()
        )


async def send_full_contacts_message_to_worker(worker, customer, abs_id: int, ad_text: str | None, event=None,
                                               history_text: str | None = None):
    """
    Отправляет исполнителю полное сообщение с объявлением и контактами, как на картинке.
    
    :param worker: Объект исполнителя (должен содержать tg_id)
    :param customer: Объект заказчика
    :param abs_id: ID объявления
    :param ad_text: Текст объявления
    :param event: Событие (CallbackQuery или Message) для удаления предыдущего сообщения
    :param history_text: История переписки (опционально)
    """
    from app.handlers.anonymous_chat import parse_contacts_message
    from aiogram.types import CallbackQuery

    # Пытаемся удалить предыдущее сообщение, если это CallbackQuery
    if event and isinstance(event, CallbackQuery):
        try:
            await event.message.delete()
        except Exception as delete_error:
            logger.debug(f"Error deleting previous message: {delete_error}")

    # Получаем только контакты без заголовка
    contacts_only = await parse_contacts_message(customer)

    # Формируем полное сообщение с объявлением
    message_text = f"📋 <b>Объявление #{abs_id}</b>\n\n"

    if ad_text:
        message_text += ad_text

    if history_text:
        message_text += f"\n\n📝 <b>История переписки:</b>\n{history_text}"

    message_text += f"\n\n✅ <b>Контакты получены:</b>\n\n{contacts_only}"
    message_text += "\n\n🔒 Чат закрыт — теперь вы можете продолжить общение напрямую."

    kbc = KeyboardCollection()

    # Отправляем сообщение через bot
    await bot.send_message(
        chat_id=worker.tg_id,
        text=message_text,
        parse_mode='HTML',
        reply_markup=kbc.menu()
    )


async def send_contacts_to_worker(event, worker, customer, abs_id: int, ad_text: str | None, is_msg=None,
                                  with_bot=None):
    from app.untils.notification_helper import create_notification

    # Это КРИТИЧНОЕ уведомление (покупка/получение контактов), поэтому type='contact_bought'
    # Оно должно приходить всегда.

    # Сначала формируем контент (нужен для сохранения в истории уведомлений)
    # Но тут структура сложная (разные способы отправки).
    # Упростим: просто логируем сам факт "Покупка успешна" в уведомлениях

    should_push = await create_notification(
        tg_id=worker.tg_id,
        notification_type='contact_bought',  # Critical -> returns True
        title=f"Контакты получены (Заказ #{abs_id})",
        body="Вы успешно получили контакты заказчика.",
        payload={'abs_id': abs_id, 'customer_id': customer.id},
        bot=bot
    )

    kbc = KeyboardCollection()

    if with_bot and should_push:
        await bot.send_message(
            chat_id=worker.tg_id,
            text="✅ <b>Покупка успешна! Контакты получены!</b>",
            parse_mode='HTML',
            reply_markup=kbc.get_worker_keyboard(abs_id)
        )
    elif is_msg and should_push:
        await event.answer(
            text="✅ <b>Покупка успешна! Контакты получены!</b>",
            parse_mode='HTML',
            reply_markup=kbc.get_worker_keyboard(abs_id)
        )
    else:
        # Callback query case - always show alert regardless of notif settings
        # This is immediate feedback for user action (clicking Buy button)
        await event.answer(
            text="✅ Покупка успешна! Контакты получены!",
            show_alert=True
        )

    # Отправляем полное сообщение с объявлением и контактами
    if not with_bot and not is_msg:
        await send_full_contacts_message_to_worker(worker, customer, abs_id, ad_text, event)


# Функция для получения строки статусов исполнителя
async def get_worker_status_string(worker_id: int) -> str:
    """Возвращает строку с подтвержденными статусами исполнителя"""
    worker_status = await WorkerStatus.get_by_worker(worker_id)

    if not worker_status:
        return "⚠️ Статус не подтвержден"

    statuses = []
    if worker_status.has_ip:
        statuses.append("ИП ✅")
    if worker_status.has_ooo:
        statuses.append("ООО ✅")
    if worker_status.has_sz:
        statuses.append("Самозанятость ✅")

    if not statuses:
        return "⚠️ Статус не подтвержден"

    return " | ".join(statuses)


async def log_message_to_admin_chat(worker, customer, abs_id: int, message_text: str, sender: str):
    """
    Отправляет лог сообщения в MESSAGE_LOG чат с кнопкой "Заблокировать".
    
    :param worker: Объект исполнителя
    :param customer: Объект заказчика
    :param abs_id: ID объявления
    :param message_text: Текст сообщения
    :param sender: Отправитель ("worker" или "customer")
    """
    try:
        import config
        from app.keyboards import KeyboardCollection

        kbc = KeyboardCollection()

        # Определяем отправителя и получателя
        if sender == "worker":
            sender_id = worker.id
            sender_tg_id = worker.tg_id
            receiver_id = customer.id
            receiver_tg_id = customer.tg_id
            sender_type = "исполнитель"
            receiver_type = "заказчику"
        else:  # customer
            sender_id = customer.id
            sender_tg_id = customer.tg_id
            receiver_id = worker.id
            receiver_tg_id = worker.tg_id
            sender_type = "заказчик"
            receiver_type = "исполнителю"

        # Формируем текст сообщения для лога
        log_text = (
            f"{sender_type.capitalize()} #{sender_tg_id} отправил сообщение {receiver_type} #{receiver_tg_id}:\n"
            f'"{message_text}"'
        )

        # Создаем клавиатуру с кнопкой "Заблокировать"
        # Используем sender_tg_id для блокировки отправителя сообщения
        reply_markup = kbc.message_log_block_button(sender_tg_id, abs_id)

        # Отправляем сообщение в лог-чат
        await bot.send_message(
            chat_id=config.MESSAGE_LOG,
            text=log_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error logging message to admin chat: {e}")

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
