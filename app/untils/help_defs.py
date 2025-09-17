import os
import re
import json
import shutil
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance

from app.data.database.models import Worker


logger = logging.getLogger(__name__)


def check_ip_status_by_ogrnip(ogrnip) -> str | None:
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
    if n == 0:
        return f'{directory}//', n
    return path, n


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
    Очищает "осиротевшие" файлы портфолио, которые не связаны ни с одним исполнителем.
    Эта функция должна вызываться периодически для поддержания чистоты файловой системы.
    
    Returns:
        int: Количество удаленных файлов
    """
    portfolio_base_path = 'app/data/photo/'
    if not os.path.exists(portfolio_base_path):
        logger.info("Папка портфолио не существует, очистка не требуется")
        return 0

    logger.info("Начинаем очистку осиротевших файлов портфолио...")

    # Получаем все папки с ID пользователей
    user_folders = [f for f in os.listdir(portfolio_base_path)
                    if os.path.isdir(os.path.join(portfolio_base_path, f)) and f.isdigit()]

    cleaned_count = 0
    checked_folders = 0

    for folder in user_folders:
        folder_path = os.path.join(portfolio_base_path, folder)
        checked_folders += 1

        # Получаем все файлы в папке
        try:
            files = os.listdir(folder_path)
            for file in files:
                if file.endswith('.jpg'):
                    file_path = os.path.join(folder_path, file)

                    # Проверяем, используется ли файл в портфолио какого-либо исполнителя
                    if is_file_orphaned(file_path):
                        # Удаляем осиротевший файл
                        if delete_file(file_path):
                            cleaned_count += 1
                            logger.info(f"Удален осиротевший файл портфолио: {file_path}")
                        else:
                            logger.warning(f"Не удалось удалить осиротевший файл: {file_path}")
                    else:
                        logger.debug(f"Файл используется в портфолио: {file_path}")

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
        return content
    except FileNotFoundError as e:
        return e
    except Exception as e:
        return e


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

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
