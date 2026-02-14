#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Профессиональный тест для проверки защиты от передачи контактов через цифры.
Тестирует функции check_message_history_for_contacts и связанные фильтры.
"""

import sys
import os
import re
import io

# Настраиваем кодировку для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Импортируем только необходимые функции без зависимостей от БД
try:
    from app.untils.contact_filter import check_message_history_for_contacts, ContactFilter
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все зависимости установлены и путь к проекту правильный.")
    sys.exit(1)


class TestResult:
    """Класс для хранения результатов теста"""
    def __init__(self, name, passed, message=""):
        self.name = name
        self.passed = passed
        self.message = message


class ContactProtectionTester:
    """Тестер защиты от передачи контактов"""
    
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
        
    def add_test(self, test_name, message_history, current_message, expected_blocked, user_type="worker"):
        """Добавляет тест"""
        try:
            is_valid, error_message = check_message_history_for_contacts(
                message_history=message_history,
                current_message=current_message,
                user_type=user_type
            )
            
            # Если ожидаем блокировку, то is_valid должен быть False
            # Если ожидаем разрешение, то is_valid должен быть True
            passed = (expected_blocked and not is_valid) or (not expected_blocked and is_valid)
            
            if passed:
                self.passed += 1
                status = "✅ PASS"
            else:
                self.failed += 1
                status = "❌ FAIL"
                
            result = TestResult(
                name=test_name,
                passed=passed,
                message=f"{status} | Expected: {'BLOCKED' if expected_blocked else 'ALLOWED'} | Got: {'BLOCKED' if not is_valid else 'ALLOWED'} | Error: {error_message if not is_valid else 'OK'}"
            )
            self.tests.append(result)
            
        except Exception as e:
            self.failed += 1
            result = TestResult(
                name=test_name,
                passed=False,
                message=f"❌ ERROR: {str(e)}"
            )
            self.tests.append(result)
    
    def run_all_tests(self):
        """Запускает все тесты"""
        print("=" * 80)
        print("🧪 ПРОФЕССИОНАЛЬНЫЙ ТЕСТ ЗАЩИТЫ ОТ ПЕРЕДАЧИ КОНТАКТОВ")
        print("=" * 80)
        print()
        
        # ========== ТЕСТ 1: ПОСЛЕДОВАТЕЛЬНОСТЬ ЦИФРОВЫХ СООБЩЕНИЙ ==========
        print("📋 ТЕСТ 1: Последовательность цифровых сообщений (3+ подряд)")
        print("-" * 80)
        
        # Тест 1.1: 3 сообщения подряд только с цифрами - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "1.1: 3 сообщения подряд только с цифрами",
            message_history=["890", "123", "4567"],
            current_message="8901",
            expected_blocked=True
        )
        
        # Тест 1.2: 2 сообщения подряд только с цифрами - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "1.2: 2 сообщения подряд только с цифрами",
            message_history=["890", "123"],
            current_message="4567",
            expected_blocked=False
        )
        
        # Тест 1.3: 3 сообщения с цифрами, но с текстом между ними - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "1.3: 3 сообщения с цифрами, но с текстом между",
            message_history=["890", "Привет, как дела?", "123"],
            current_message="4567",
            expected_blocked=False
        )
        
        # Тест 1.4: 3 сообщения подряд, но с контекстом цены - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "1.4: 3 сообщения подряд с контекстом цены",
            message_history=["цена 5000", "стоимость 3000", "оплата 2000"],
            current_message="рублей 1000",
            expected_blocked=False
        )
        
        print()
        
        # ========== ТЕСТ 2: НАКОПЛЕНИЕ ЦИФР (НОМЕР ТЕЛЕФОНА) ==========
        print("📋 ТЕСТ 2: Накопление цифр (формирование номера телефона)")
        print("-" * 80)
        
        # Тест 2.1: Накопление 11 цифр, похожих на номер - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "2.1: Накопление 11 цифр (89012345678)",
            message_history=["890", "123", "45", "67", "8"],
            current_message="9",
            expected_blocked=True
        )
        
        # Тест 2.2: Накопление 8+ цифр без контекста - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "2.2: Накопление 8+ цифр без контекста",
            message_history=["123", "456", "789"],
            current_message="012",
            expected_blocked=True
        )
        
        # Тест 2.3: Накопление 8+ цифр с контекстом цены - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "2.3: Накопление 8+ цифр с контекстом цены",
            message_history=["цена 5000", "стоимость 3000"],
            current_message="оплата 2000",
            expected_blocked=False
        )
        
        # Тест 2.4: Накопление цифр с контекстом адреса - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "2.4: Накопление цифр с контекстом адреса",
            message_history=["квартира 25", "дом 10", "подъезд 3"],
            current_message="этаж 5",
            expected_blocked=False
        )
        
        # Тест 2.5: Российский номер (8 901 234 56 78) - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "2.5: Российский номер разбитый на части",
            message_history=["8", "901", "234", "56"],
            current_message="78",
            expected_blocked=True
        )
        
        print()
        
        # ========== ТЕСТ 3: КОМБИНАЦИИ ЦИФР И ЧИСЛИТЕЛЬНЫХ ==========
        print("📋 ТЕСТ 3: Комбинации цифр и числительных")
        print("-" * 80)
        
        # Тест 3.1: Комбинация цифр и числительных (6+ групп) - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "3.1: Комбинация цифр и числительных (890 пять 85 восемь)",
            message_history=["890", "пять", "85", "восемь", "тридцать"],
            current_message="семь",
            expected_blocked=True
        )
        
        # Тест 3.2: Комбинация с контекстом - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "3.2: Комбинация с контекстом цены",
            message_history=["цена пять тысяч", "стоимость три тысячи"],
            current_message="оплата два",
            expected_blocked=False
        )
        
        print()
        
        # ========== ТЕСТ 4: ОБХОД ЗАЩИТЫ ==========
        print("📋 ТЕСТ 4: Попытки обхода защиты")
        print("-" * 80)
        
        # Тест 4.1: Номер с заменой букв на цифры (н0ль вместо ноль) - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "4.1: Номер с заменой букв (890 н0ль 85)",
            message_history=["890", "н0ль", "85"],
            current_message="восемь",
            expected_blocked=True
        )
        
        # Тест 4.2: Номер с латинскими буквами (oдин вместо один) - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "4.2: Номер с латинскими буквами",
            message_history=["890", "oдин", "85"],
            current_message="восемь",
            expected_blocked=True
        )
        
        # Тест 4.3: Разбивка номера с текстом между - ДОЛЖНО РАЗРЕШИТЬ (если есть текст)
        self.add_test(
            "4.3: Разбивка номера с текстом между",
            message_history=["890", "Привет", "123", "Как дела?", "456"],
            current_message="789",
            expected_blocked=False
        )
        
        # Тест 4.4: Номер с опечатками - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "4.4: Номер с опечатками (нль вместо ноль)",
            message_history=["890", "нль", "85"],
            current_message="восемь",
            expected_blocked=True
        )
        
        print()
        
        # ========== ТЕСТ 5: НОРМАЛЬНОЕ ОБЩЕНИЕ ==========
        print("📋 ТЕСТ 5: Нормальное общение (должно разрешать)")
        print("-" * 80)
        
        # Тест 5.1: Обсуждение цены
        self.add_test(
            "5.1: Обсуждение цены",
            message_history=["Сколько стоит работа?", "Цена 5000 рублей"],
            current_message="Могу сделать за 4000",
            expected_blocked=False
        )
        
        # Тест 5.2: Обсуждение адреса
        self.add_test(
            "5.2: Обсуждение адреса",
            message_history=["Где находится объект?", "Адрес: улица Ленина, дом 10"],
            current_message="Квартира 25, подъезд 3",
            expected_blocked=False
        )
        
        # Тест 5.3: Обсуждение времени
        self.add_test(
            "5.3: Обсуждение времени",
            message_history=["Во сколько приехать?", "В 15:00"],
            current_message="До 18:00",
            expected_blocked=False
        )
        
        # Тест 5.4: Обсуждение размеров
        self.add_test(
            "5.4: Обсуждение размеров",
            message_history=["Какая площадь?", "5 квадратных метров"],
            current_message="Высота 2.5 метра",
            expected_blocked=False
        )
        
        # Тест 5.5: Смешанное общение
        self.add_test(
            "5.5: Смешанное общение",
            message_history=["Привет", "Как дела?", "Цена 5000", "Адрес: дом 10"],
            current_message="Встретимся в 15:00",
            expected_blocked=False
        )
        
        print()
        
        # ========== ТЕСТ 6: ГРАНИЧНЫЕ СЛУЧАИ ==========
        print("📋 ТЕСТ 6: Граничные случаи")
        print("-" * 80)
        
        # Тест 6.1: Ровно 2 сообщения подряд с цифрами - ДОЛЖНО РАЗРЕШИТЬ
        self.add_test(
            "6.1: Ровно 2 сообщения подряд с цифрами",
            message_history=["890"],
            current_message="123",
            expected_blocked=False
        )
        
        # Тест 6.2: Ровно 7 цифр без контекста - ДОЛЖНО РАЗРЕШИТЬ (граница)
        self.add_test(
            "6.2: Ровно 7 цифр без контекста",
            message_history=["123", "456"],
            current_message="7",
            expected_blocked=False
        )
        
        # Тест 6.3: Ровно 8 цифр без контекста - ДОЛЖНО БЛОКИРОВАТЬ
        self.add_test(
            "6.3: Ровно 8 цифр без контекста",
            message_history=["123", "456"],
            current_message="78",
            expected_blocked=True
        )
        
        # Тест 6.4: Пустая история
        self.add_test(
            "6.4: Пустая история",
            message_history=[],
            current_message="89012345678",
            expected_blocked=False  # Одно сообщение не блокируется историей
        )
        
        print()
        
        # ========== ТЕСТ 7: РЕАЛЬНЫЕ СЦЕНАРИИ ОБХОДА ==========
        print("📋 ТЕСТ 7: Реальные сценарии обхода")
        print("-" * 80)
        
        # Тест 7.1: Номер через слова и цифры
        self.add_test(
            "7.1: Номер через слова и цифры (890 пять 85 восемь)",
            message_history=["890", "пять", "85", "восемь"],
            current_message="тридцать семь",
            expected_blocked=True
        )
        
        # Тест 7.2: Номер с пробелами в тексте
        self.add_test(
            "7.2: Номер с пробелами в тексте",
            message_history=["890", "Привет 123", "Как дела 456"],
            current_message="789",
            expected_blocked=True
        )
        
        # Тест 7.3: Номер с контекстом, но подозрительный
        self.add_test(
            "7.3: Номер с контекстом, но подозрительный",
            message_history=["890", "цена 123", "стоимость 456"],
            current_message="789",
            expected_blocked=True  # Все равно подозрительно
        )
        
        print()
        
        # Выводим результаты
        self.print_results()
    
    def print_results(self):
        """Выводит результаты тестирования"""
        print("=" * 80)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("=" * 80)
        print()
        
        for test in self.tests:
            print(f"{test.message}")
        
        print()
        print("=" * 80)
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"✅ Пройдено: {self.passed}")
        print(f"❌ Провалено: {self.failed}")
        print(f"📈 Всего тестов: {total}")
        print(f"🎯 Успешность: {success_rate:.1f}%")
        print("=" * 80)
        print()
        
        # Анализ эффективности защиты
        print("🔍 АНАЛИЗ ЭФФЕКТИВНОСТИ ЗАЩИТЫ:")
        print("-" * 80)
        
        # Подсчитываем тесты по категориям
        block_tests = [t for t in self.tests if "BLOCKED" in t.message and "Expected: BLOCKED" in t.message]
        allow_tests = [t for t in self.tests if "ALLOWED" in t.message and "Expected: ALLOWED" in t.message]
        
        blocked_passed = sum(1 for t in block_tests if t.passed)
        allowed_passed = sum(1 for t in allow_tests if t.passed)
        
        block_rate = (blocked_passed / len(block_tests) * 100) if block_tests else 0
        allow_rate = (allowed_passed / len(allow_tests) * 100) if allow_tests else 0
        
        print(f"🛡️  Блокировка атак: {blocked_passed}/{len(block_tests)} ({block_rate:.1f}%)")
        print(f"✅ Разрешение нормального общения: {allowed_passed}/{len(allow_tests)} ({allow_rate:.1f}%)")
        print()
        
        # Общая оценка
        overall_effectiveness = (block_rate * 0.7 + allow_rate * 0.3)  # Блокировка важнее
        print(f"⭐ ОБЩАЯ ЭФФЕКТИВНОСТЬ ЗАЩИТЫ: {overall_effectiveness:.1f}%")
        print()
        
        if overall_effectiveness >= 90:
            print("🎉 ОТЛИЧНО! Защита работает на высоком уровне!")
        elif overall_effectiveness >= 75:
            print("👍 ХОРОШО! Защита работает, но есть место для улучшений.")
        elif overall_effectiveness >= 60:
            print("⚠️  УДОВЛЕТВОРИТЕЛЬНО! Защита работает, но нужны доработки.")
        else:
            print("❌ ТРЕБУЕТСЯ ДОРАБОТКА! Защита работает недостаточно эффективно.")
        
        print("=" * 80)


def main():
    """Главная функция"""
    tester = ContactProtectionTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()

