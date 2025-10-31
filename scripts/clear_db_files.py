#!/usr/bin/env python3
"""
Скрипт для очистки файлов и папок, связанных с пользовательскими данными.
Удаляет все файлы пользователей перед созданием новой БД.

ВНИМАНИЕ: Этот скрипт удаляет:
- Все фото объявлений (app/data/photo/)
- Все тексты объявлений (app/data/text/)
- Все заблокированные объявления (app/data/banned/)
- Фото объявлений от админа (app/data/database/abs_from_admin_photo/)

НЕ удаляет:
- Базу данных (database.db и резервные копии остаются)
- Шаблоны (app/data/database/abs_templates/)
- Информационные файлы (app/data/database/info/)
- Медиа-файлы (watermark.png, Haltura.mp4 и т.д.)
"""

import os
import shutil
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clear_db_files.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def remove_directory(path: str) -> bool:
    """Безопасно удаляет директорию со всем содержимым"""
    if not os.path.exists(path):
        logger.debug(f"Папка не существует (пропуск): {path}")
        return False
    
    try:
        shutil.rmtree(path)
        logger.info(f"✓ Удалена папка: {path}")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка при удалении {path}: {e}")
        return False


def remove_file(path: str) -> bool:
    """Безопасно удаляет файл"""
    if not os.path.exists(path):
        logger.debug(f"Файл не существует (пропуск): {path}")
        return False
    
    try:
        os.remove(path)
        logger.info(f"✓ Удален файл: {path}")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка при удалении {path}: {e}")
        return False


def clear_user_data():
    """Очищает все пользовательские данные"""
    removed_dirs = 0
    
    # Список папок для удаления
    directories_to_remove = [
        'app/data/photo',          # Фото объявлений и портфолио
        'app/data/text',           # Тексты объявлений
        'app/data/banned',         # Заблокированные объявления
        'app/data/database/abs_from_admin_photo',  # Фото объявлений от админа
    ]
    
    for directory in directories_to_remove:
        if remove_directory(directory):
            removed_dirs += 1
    
    return removed_dirs


def count_files_in_directory(directory: str) -> int:
    """Подсчитывает количество файлов в директории (рекурсивно)"""
    if not os.path.exists(directory):
        return 0
    
    count = 0
    for root, dirs, files in os.walk(directory):
        count += len(files)
    return count


def show_statistics():
    """Показывает статистику перед очисткой"""
    logger.info("=" * 60)
    logger.info("СТАТИСТИКА ПЕРЕД ОЧИСТКОЙ")
    logger.info("=" * 60)
    
    directories = {
        'app/data/photo': 'Фото объявлений',
        'app/data/text': 'Тексты объявлений',
        'app/data/banned': 'Заблокированные объявления',
        'app/data/database/abs_from_admin_photo': 'Фото от админа',
    }
    
    total_files = 0
    for directory, description in directories.items():
        count = count_files_in_directory(directory)
        total_files += count
        if count > 0:
            logger.info(f"{description}: {count} файлов")
        else:
            logger.info(f"{description}: папка не существует или пуста")
    
    logger.info("-" * 60)
    logger.info(f"Всего файлов к удалению: {total_files}")
    logger.info("=" * 60)
    
    return total_files


def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("СКРИПТ ОЧИСТКИ ФАЙЛОВ И ПАПОК")
    logger.info("=" * 60)
    logger.warning("ВНИМАНИЕ: Этот скрипт удалит все пользовательские файлы и папки!")
    logger.info("База данных НЕ будет удалена.")
    logger.info("")
    
    # Показываем статистику
    total_files = show_statistics()
    
    if total_files == 0:
        logger.info("Нечего удалять. Все папки пусты или не существуют.")
        return
    
    # Запрашиваем подтверждение
    logger.info("")
    response = input("Продолжить очистку? (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y', 'да', 'д']:
        logger.info("Очистка отменена пользователем.")
        return
    
    logger.info("")
    logger.info("Начинаем очистку...")
    logger.info("")
    
    # Очищаем пользовательские данные
    logger.info("Очистка пользовательских файлов и папок...")
    dirs_removed = clear_user_data()
    
    # Итоговая статистика
    logger.info("")
    logger.info("=" * 60)
    logger.info("ОЧИСТКА ЗАВЕРШЕНА")
    logger.info("=" * 60)
    logger.info(f"Удалено папок с данными: {dirs_removed}")
    logger.info("")
    logger.info("База данных сохранена и не была удалена.")
    logger.info("Бот автоматически создаст нужные папки при первом использовании.")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("")
        logger.warning("Очистка прервана пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)

