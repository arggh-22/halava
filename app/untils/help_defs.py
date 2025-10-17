import os
import re
import json
import shutil
import logging
import requests
import time
from datetime import datetime, date
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance
from aiogram.types import Message


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
        return content
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


def is_content_forbidden(text: str) -> bool:
    """
    Проверяет, содержит ли текст запрещенный контент (ссылки, упоминания, номера прописью).
    
    Args:
        text: Текст для проверки
        
    Returns:
        bool: True если контент запрещен, False если разрешен
    """
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    # Проверка на ссылки (http, https, www, домены)
    url_patterns = [
        r'https?://',  # http:// или https://
        r'www\.',      # www.
        r'\.(com|ru|org|net|info|biz|co|io|me|tv|cc|tk|ml|ga|cf)',  # домены
        r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # общий паттерн доменов
    ]
    
    for pattern in url_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # Проверка на упоминания через @ (только латиница)
    if re.search(r'@[a-zA-Z0-9_]+', text_lower):
        return True
    
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


# Функция check_dialog_active удалена - использовалась только для откликов


async def process_contact_exchange(worker_id: int, customer_id: int, abs_id: int, action: str) -> dict:
    """
    Унифицированная функция для обработки обмена контактами.
    
    Args:
        worker_id: ID исполнителя
        customer_id: ID заказчика  
        abs_id: ID объявления
        action: "send_contacts" или "buy_contacts"
    
    Returns:
        dict: Результат операции с статусом и сообщениями
    """
    try:
        from app.data.database.models import ContactExchange, Worker, Customer, Abs
        from loaders import bot
        from app.keyboards import KeyboardCollection
        
        # Получаем текущий статус
        status = await ContactExchange.get_status(worker_id, abs_id)
        
        # Проверяем возможность выполнения действия
        if action == "send_contacts":
            if status['contacts_sent']:
                return {
                    'success': False,
                    'message': 'Контакты уже были отправлены',
                    'status': status
                }
        elif action == "buy_contacts":
            if status['contacts_purchased']:
                return {
                    'success': False,
                    'message': 'Контакты уже были куплены',
                    'status': status
                }
        
        # Получаем данные
        worker = await Worker.get_worker(id=worker_id)
        customer = await Customer.get_customer(id=customer_id)
        advertisement = await Abs.get_one(id=abs_id)
        
        if not worker or not customer or not advertisement:
            return {
                'success': False,
                'message': 'Данные не найдены',
                'status': status
            }
        
        kbc = KeyboardCollection()
        
        if action == "send_contacts":
            # Заказчик отправляет контакты
            try:
                await ContactExchange.create_or_update(
                    worker_id=worker_id,
                    customer_id=customer_id,
                    abs_id=abs_id,
                    contacts_sent=True,
                    contacts_purchased=False
                )
                
                # Проверяем, есть ли у исполнителя купленные контакты
                has_contacts = await check_worker_has_unlimited_contacts(worker_id)
                
                if has_contacts:
                    # У исполнителя есть контакты - сразу показываем контакты
                    await show_worker_purchased_contacts(worker_id, customer_id, abs_id)
                    
                    # Вычитаем контакт из лимита (если не безлимитный)
                    if not worker.unlimited_contacts_until:
                        if worker.purchased_contacts > 0:
                            new_contacts = worker.purchased_contacts - 1
                            await worker.update_purchased_contacts(purchased_contacts=new_contacts)
                    
                    # Обновляем статус как завершенный
                    await ContactExchange.create_or_update(
                        worker_id=worker_id,
                        customer_id=customer_id,
                        abs_id=abs_id,
                        contacts_sent=True,
                        contacts_purchased=True
                    )
                    
                    # Уведомляем заказчика
                    customer_message = (
                        "🔒 **Чат закрыт**\n\n"
                        "✅ Контакты были успешно переданы исполнителю\n"
                        "💬 Диалог завершен\n\n"
                        f"📋 Объявление #{abs_id}\n"
                        f"👤 Исполнитель ID: {worker_id}"
                    )
                    
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=customer_message,
                        reply_markup=kbc.chat_closed_buttons('customer', abs_id),
                        parse_mode='Markdown'
                    )
                    
                    return {
                        'success': True,
                        'message': 'Контакты переданы исполнителю',
                        'status': 'completed',
                        'contacts_shown': True
                    }
                else:
                    # У исполнителя нет контактов - показываем уведомление о покупке
                    worker_message = (
                        "📞 **Заказчик отправил свои контакты**\n\n"
                        f"📋 Объявление #{abs_id}\n"
                        f"💰 Размер: {advertisement.price} ₽\n\n"
                        "💡 Для получения контактов заказчика необходимо приобрести доступ"
                    )
                    
                    await bot.send_message(
                        chat_id=worker.tg_id,
                        text=worker_message,
                        reply_markup=kbc.buy_contact_worker_btn(customer_id, abs_id)
                    )
                    
                    # Уведомляем заказчика
                    customer_message = (
                        "🔒 **Чат закрыт**\n\n"
                        "✅ Контакты были отправлены исполнителю\n"
                        "💬 Диалог завершен\n\n"
                        f"📋 Объявление #{abs_id}\n"
                        f"👤 Исполнитель ID: {worker_id}\n\n"
                        "⏳ Ожидается покупка контактов исполнителем"
                    )
                    
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=customer_message,
                        reply_markup=kbc.chat_closed_buttons('customer', abs_id),
                        parse_mode='Markdown'
                    )
                    
                    return {
                        'success': True,
                        'message': 'Контакты отправлены, ожидается покупка',
                        'status': 'pending_purchase',
                        'contacts_shown': False
                    }
                    
            except ValueError as e:
                return {
                    'success': False,
                    'message': str(e),
                    'status': status
                }
        
        elif action == "buy_contacts":
            # Исполнитель покупает контакты
            try:
                # Проверяем, есть ли у исполнителя купленные контакты
                has_contacts = await check_worker_has_unlimited_contacts(worker_id)
                
                if not has_contacts:
                    return {
                        'success': False,
                        'message': 'У вас нет купленных контактов для получения',
                        'status': status
                    }
                
                # Проверяем, были ли контакты отправлены заказчиком
                if not status['contacts_sent']:
                    return {
                        'success': False,
                        'message': 'Заказчик еще не отправил контакты',
                        'status': status
                    }
                
                # Обновляем статус как завершенный
                await ContactExchange.create_or_update(
                    worker_id=worker_id,
                    customer_id=customer_id,
                    abs_id=abs_id,
                    contacts_sent=True,
                    contacts_purchased=True
                )
                
                # Вычитаем контакт из лимита (если не безлимитный)
                if not worker.unlimited_contacts_until:
                    if worker.purchased_contacts > 0:
                        new_contacts = worker.purchased_contacts - 1
                        await worker.update_purchased_contacts(purchased_contacts=new_contacts)
                
                # Показываем контакты исполнителю
                await show_worker_purchased_contacts(worker_id, customer_id, abs_id)
                
                # Уведомляем заказчика
                customer_message = (
                    "🔒 **Чат закрыт**\n\n"
                    "💰 Исполнитель получил ваши контакты\n"
                    "💬 Диалог завершен\n\n"
                    f"📋 Объявление #{abs_id}\n"
                    f"👤 Исполнитель ID: {worker_id}"
                )
                
                await bot.send_message(
                    chat_id=customer.tg_id,
                    text=customer_message,
                    reply_markup=kbc.chat_closed_buttons('customer', abs_id),
                    parse_mode='Markdown'
                )
                
                return {
                    'success': True,
                    'message': 'Контакты успешно получены',
                    'status': 'completed',
                    'contacts_shown': True
                }
                
            except ValueError as e:
                return {
                    'success': False,
                    'message': str(e),
                    'status': status
                }
        
        return {
            'success': False,
            'message': 'Неизвестное действие',
            'status': status
        }
        
    except Exception as e:
        logger.error(f"Error in process_contact_exchange: {e}")
        return {
            'success': False,
            'message': f'Ошибка: {str(e)}',
            'status': {'contacts_sent': False, 'contacts_purchased': False, 'status': 'error'}
        }


# Функция add_contact_exchange_to_history удалена - использовалась только для откликов


# Функция close_chat_after_contact_exchange удалена - использовалась только для откликов


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


async def send_targeted_notifications_to_workers(advertisement_id: int, customer_id: int) -> None:
    """
    Отправляет уведомления исполнителям по городу и направлению объявления.
    
    Args:
        advertisement_id: ID объявления
        customer_id: ID заказчика
    """
    try:
        from app.data.database.models import Abs, Worker, City, WorkType
        
        # Получаем объявление
        advertisement = await Abs.get_one(id=advertisement_id)
        if not advertisement:
            logger.error(f"Advertisement not found: {advertisement_id}")
            return
        
        # Получаем город заказчика
        from app.data.database.models import Customer
        customer = await Customer.get_customer(id=customer_id)
        if not customer:
            logger.error(f"Customer not found: {customer_id}")
            return
        
        city = await City.get_city(id=customer.city_id)
        if not city:
            logger.error(f"City not found: {customer.city_id}")
            return
        
        # Получаем направление работы
        work_type = await WorkType.get_work_type(id=advertisement.work_type_id)
        if not work_type:
            logger.error(f"Work type not found: {advertisement.work_type_id}")
            return
        
        # Используем правильную функцию для получения исполнителей с учетом подписок
        matching_workers = await Worker.get_active_workers_for_advertisement(
            city_id=customer.city_id, 
            work_type_id=advertisement.work_type_id
        )
        
        if not matching_workers:
            logger.info(f"No matching workers found for city {city.city} and work type {work_type.work_type}")
            return
        
        logger.info(f"Found {len(matching_workers)} matching workers for city {city.city} and work type {work_type.work_type}")
        
        # Отправляем уведомления
        from loaders import bot
        notification_text = (
            f"🔔 Новое объявление в вашем городе!\n\n"
            f"📍 Город: {city.city}\n"
            f"💼 Направление: {work_type.work_type}\n"
            f"📋 Описание: {read_text_file(advertisement.text_path)}\n\n"
            f"💰 Размер: {advertisement.price} ₽\n"
            f"📅 Срок: {advertisement.date_end}\n\n"
            f"Нажмите /menu чтобы откликнуться!"
        )
        
        sent_count = 0
        for worker in matching_workers:
            try:
                await bot.send_message(
                    chat_id=worker.tg_id,
                    text=notification_text
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending notification to worker {worker.tg_id}: {e}")
        
        logger.info(f"Sent notifications to {sent_count} workers")
        
    except Exception as e:
        logger.error(f"Error sending targeted notifications: {e}")


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


async def show_worker_purchased_contacts(worker_id: int, customer_id: int, abs_id: int) -> None:
    """
    Показывает исполнителю купленные контакты заказчика.
    
    Args:
        worker_id: ID исполнителя
        customer_id: ID заказчика
        abs_id: ID объявления
    """
    try:
        from app.data.database.models import Worker, Customer, Abs
        from loaders import bot
        from app.keyboards import KeyboardCollection
        
        worker = await Worker.get_worker(id=worker_id)
        customer = await Customer.get_customer(id=customer_id)
        advertisement = await Abs.get_one(id=abs_id)
        
        if not worker or not customer or not advertisement:
            logger.error(f"Не найдены данные для показа контактов: worker_id={worker_id}, customer_id={customer_id}, abs_id={abs_id}")
            return
        
        # Формируем сообщение с контактами
        customer_contacts = f"Telegram: @{customer.tg_name}\nID: {customer.tg_id}"
        
        contacts_message = (
            "🎉 **Контакты получены!**\n\n"
            f"📞 **Контакты заказчика:**\n{customer_contacts}\n\n"
            f"📋 **Объявление #{abs_id}**\n"
            f"💰 **Размер:** {advertisement.price} ₽\n"
            f"📅 **Срок:** {advertisement.date_end}\n\n"
            "✅ Теперь вы можете связаться с заказчиком напрямую!"
        )
        
        kbc = KeyboardCollection()
        
        # Отправляем сообщение исполнителю
        await bot.send_message(
            chat_id=worker.tg_id,
            text=contacts_message,
            reply_markup=kbc.chat_closed_buttons('worker', abs_id),
            parse_mode='Markdown'
        )
        
        logger.info(f"Contacts shown to worker {worker_id} for advertisement {abs_id}")
        
    except Exception as e:
        logger.error(f"Error showing contacts to worker: {e}")


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
        
        # Проверяем безлимитный доступ по дате окончания
        if worker.unlimited_contacts_until:
            from datetime import datetime
            try:
                end_date = datetime.strptime(worker.unlimited_contacts_until, "%Y-%m-%d")
                if end_date > datetime.now():
                    return True
            except ValueError:
                # Неверный формат даты
                pass
        
        # Проверяем количество купленных контактов
        if worker.purchased_contacts and worker.purchased_contacts > 0:
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking unlimited contacts for worker {worker_id}: {e}")
        return False


async def handle_forbidden_content(message, bot) -> bool:
    """
    Обрабатывает сообщение с запрещенным контентом.
    
    Args:
        message: Сообщение пользователя
        bot: Экземпляр бота
        
    Returns:
        bool: True если контент запрещен и обработан, False если разрешен
    """
    try:
        if is_content_forbidden(message.text):
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

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
