#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы скриптов портфолио.
Проверяет, что все скрипты работают без ошибок кодировки.
"""

import os
import sys
import subprocess
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_portfolio_scripts.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def test_script(script_name, description):
    """Тестирует выполнение скрипта"""
    logger.info(f"Тестирование: {description}")
    
    try:
        # Проверяем, что файл существует
        if not os.path.exists(script_name):
            logger.error(f"Файл {script_name} не найден")
            return False
        
        # Запускаем скрипт с таймаутом
        result = subprocess.run(
            [sys.executable, script_name, '--help'] if '--help' in script_name else [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            logger.info(f"[SUCCESS] {description} - OK")
            return True
        else:
            logger.error(f"[ERROR] {description} - Код возврата: {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"[TIMEOUT] {description} - Превышен таймаут")
        return False
    except Exception as e:
        logger.error(f"[EXCEPTION] {description} - Ошибка: {e}")
        return False

def main():
    """Основная функция тестирования"""
    logger.info("Запуск тестирования скриптов портфолио...")
    
    # Список скриптов для тестирования
    scripts_to_test = [
        ("check_portfolio_status.py", "Проверка статуса портфолио"),
        ("clear_portfolio_photos_silent.py", "Тихая очистка портфолио"),
    ]
    
    passed = 0
    failed = 0
    
    for script_name, description in scripts_to_test:
        if test_script(script_name, description):
            passed += 1
        else:
            failed += 1
    
    logger.info("="*60)
    logger.info(f"РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    logger.info(f"  Успешно: {passed}")
    logger.info(f"  Ошибок: {failed}")
    logger.info(f"  Всего: {passed + failed}")
    
    if failed == 0:
        logger.info("[SUCCESS] Все тесты прошли успешно!")
        return True
    else:
        logger.error("[ERROR] Некоторые тесты не прошли!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
