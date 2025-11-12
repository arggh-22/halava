"""
Handlers для анонимного чата между исполнителем и заказчиком
- Обмен сообщениями
- Запрос контактов
- Подтверждение передачи контактов
- Покупка контактов (монетизация)
"""

import html
import logging
import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest

from app.states import WorkStates, CustomerStates
from app.keyboards import KeyboardCollection
from app.data.database.models import (
    Worker, Customer, Abs, WorkersAndAbs, ContactExchange, ContactTransaction
)
from loaders import bot
from app.untils.contact_filter import check_message_for_contacts
from app.untils.checks import fool_check
from app.untils.help_defs import (
    is_content_forbidden, get_contact_word, update_worker_or_customer_chat_status, send_notification_to_customer,
    read_text_file, send_contacts_to_worker
)

logger = logging.getLogger(__name__)
router = Router()


async def parse_contacts_message(customer):
    """
    Возвращает контакты заказчика исполнителю и уведомляет заказчика.

    :param customer: объект заказчика (должен содержать tg_id, tg_name, phone_number, contact_type, id)
    """

    # Экранируем HTML-символы, чтобы не ломалась разметка
    tg_name = html.escape(customer.tg_name) if customer.tg_name else "Профиль"
    phone = html.escape(customer.phone_number) if getattr(customer, "phone_number", None) else ""

    # --- Формируем текст контактов ---
    # contacts_text = "📞 <b>Контакты заказчика:</b>\n\n"

    if customer.contact_type == "telegram_only":
        contacts_text = (
            f"📱 <b>Telegram:</b> "
            f"<a href='tg://user?id={customer.tg_id}'>@{tg_name}</a>\n"
        )
    elif customer.contact_type == "phone_only":
        contacts_text = (
            f"📞 <b>Номер телефона:</b> "
            f"<a href='tel:{phone}'>{phone}</a>"
        )
    elif customer.contact_type == "both":
        contacts_text = (
            f"📱 <b>Telegram:</b> "
            f"<a href='tg://user?id={customer.tg_id}'>@{tg_name}</a>\n"
            f"📞 <b>Номер телефона:</b> "
            f"<a href='tel:{phone}'>{phone}</a>"
        )
    else:
        # fallback — показываем только Telegram, если контакты не настроены
        contacts_text = (
            f"📱 <b>Telegram:</b> "
            f"<a href='tg://user?id={customer.tg_id}'>@{tg_name}</a>\n"
        )

    return contacts_text


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

# Функция для получения строки статусов исполнителя
async def get_worker_status_string(worker_id: int) -> str:
    """Возвращает строку с подтвержденными статусами исполнителя"""
    from app.data.database.models import WorkerStatus
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


async def get_response_status_indicator(response, user_type: str) -> str:
    """
    Определяет индикатор статуса для отклика в списке
    Возвращает: "•" (непрочитанное/неотвеченное), "✅" (закрыт), "💬" (активный)
    """
    try:
        # Проверяем, закрыт ли чат (контакты переданы)
        from app.data.database.models import ContactExchange
        contact_exchange = await ContactExchange.get_by_worker_and_abs(response.worker_id, response.abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            return "✅"  # Чат закрыт

        if user_type == "worker":
            # Для исполнителя: показываем "•" если исполнитель написал последним
            # Используем поле turn: True = очередь исполнителя (исполнитель написал последним)
            if response.turn:
                return " • "
            return "💬"  # Активный чат
        else:  # customer
            # Для заказчика: показываем "•" если заказчик написал последним
            # Используем поле turn: False = очередь заказчика (заказчик написал последним)
            if not response.turn:
                return " • "
            return "💬"  # Активный чат

    except Exception as e:
        logger.error(f"Error in get_response_status_indicator: {e}")
        return "💬"  # По умолчанию активный чат


def get_sender_name(sender_type: str, user_type: str, worker, customer) -> str:
    """
    Возвращает правильное имя отправителя в зависимости от того, кто читает чат
    
    Args:
        sender_type: 'worker' или 'customer' - кто отправил сообщение
        user_type: 'worker' или 'customer' - кто читает чат
        worker: объект Worker
        customer: объект Customer
    
    Returns:
        str: имя отправителя для отображения
    """
    if sender_type == user_type:
        return "Вы"
    elif sender_type == "worker" and user_type == "customer":
        # Заказчик читает, исполнитель отправил
        return worker.profile_name or worker.tg_name or "Исполнитель"
    elif sender_type == "customer" and user_type == "worker":
        # Исполнитель читает, заказчик отправил
        return "Заказчик"
    else:
        return "Неизвестно"


async def format_chat_history_for_display(user_type: str, abs_id: int, worker, customer,
                                          show_unread_indicators: bool = True) -> str:
    """
    Форматирует историю чата для отображения в просмотре отклика
    Возвращает текст истории переписки с индикаторами непрочитанных сообщений
    
    Args:
        user_type: "worker" или "customer"
        abs_id: ID объявления
        worker: объект Worker
        customer: объект Customer
        show_unread_indicators: Показывать ли индикаторы непрочитанных сообщений (по умолчанию True)
    """
    try:
        # Получаем WorkersAndAbs для истории сообщений
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
        if not response:
            return ""

        # Получаем индексы последних прочитанных сообщений
        last_read_by_worker = getattr(response, 'last_read_by_worker', 0)
        last_read_by_customer = getattr(response, 'last_read_by_customer', 0)

        # Получаем списки сообщений
        worker_messages_list = []
        customer_messages_list = []

        # Фильтруем worker_messages: убираем служебное сообщение и пустые
        if response.worker_messages:
            worker_messages_list = [
                msg for msg in response.worker_messages
                if msg and msg.strip() and msg != "Исполнитель не отправил сообщение"
            ]

        # Фильтруем customer_messages: убираем пустые
        if response.customer_messages:
            customer_messages_list = [
                msg for msg in response.customer_messages
                if msg and msg.strip()
            ]

        ordered_messages = []

        # Получаем временные метки из БД
        timestamps_list = response.message_timestamps if hasattr(response, 'message_timestamps') else []

        # Если есть временные метки - используем их для сортировки
        if timestamps_list and len(timestamps_list) > 0:
            # Создаем единый список всех сообщений с временными метками
            all_messages_with_timestamps = []

            # Индексы для сообщений каждого типа
            worker_msg_idx = 0
            customer_msg_idx = 0

            # Проходим по временным меткам один раз и сопоставляем с сообщениями
            for ts_data in timestamps_list:
                if ts_data['sender'] == 'worker' and worker_msg_idx < len(worker_messages_list):
                    msg = worker_messages_list[worker_msg_idx]
                    # Сообщения уже отфильтрованы при загрузке из БД
                    all_messages_with_timestamps.append({
                        'text': msg,
                        'sender': 'worker',
                        'timestamp': ts_data['timestamp'],
                        'worker_msg_index': worker_msg_idx
                    })
                    worker_msg_idx += 1
                elif ts_data['sender'] == 'customer' and customer_msg_idx < len(customer_messages_list):
                    msg = customer_messages_list[customer_msg_idx]
                    # Сообщения уже отфильтрованы при загрузке из БД
                    all_messages_with_timestamps.append({
                        'text': msg,
                        'sender': 'customer',
                        'timestamp': ts_data['timestamp'],
                        'customer_msg_index': customer_msg_idx
                    })
                    customer_msg_idx += 1

            # Сортируем по временным меткам
            sorted_messages = sorted(all_messages_with_timestamps, key=lambda x: x['timestamp'])

            # Формируем финальный список
            for msg_data in sorted_messages:
                ordered_messages.append({
                    'text': msg_data['text'],
                    'sender': msg_data['sender'],
                    'worker_msg_index': msg_data.get('worker_msg_index', -1),
                    'customer_msg_index': msg_data.get('customer_msg_index', -1)
                })
        else:
            # Старая логика чередования (для совместимости)
            worker_count = len(worker_messages_list)
            customer_count = len(customer_messages_list)

            if abs(worker_count - customer_count) <= 1:
                worker_idx = 0
                customer_idx = 0
                while worker_idx < worker_count or customer_idx < customer_count:
                    if worker_idx < worker_count:
                        msg = worker_messages_list[worker_idx]
                        ordered_messages.append({
                            'text': msg,
                            'sender': 'worker',
                            'worker_msg_index': worker_idx,
                            'customer_msg_index': -1
                        })
                        worker_idx += 1
                    if customer_idx < customer_count:
                        msg = customer_messages_list[customer_idx]
                        ordered_messages.append({
                            'text': msg,
                            'sender': 'customer',
                            'worker_msg_index': -1,
                            'customer_msg_index': customer_idx
                        })
                        customer_idx += 1

        # Формируем историю
        chat_history = ""

        if ordered_messages:
            # Показываем последние 10 сообщений для просмотра отклика
            for msg_data in ordered_messages[-10:]:
                msg_text = msg_data['text']
                msg_sender = msg_data['sender']
                worker_msg_index = msg_data.get('worker_msg_index', -1)
                customer_msg_index = msg_data.get('customer_msg_index', -1)

                # Определяем, нужно ли показать индикатор "•" рядом с СОБСТВЕННЫМИ сообщениями
                # Только если show_unread_indicators=True
                unread_indicator = ""
                if show_unread_indicators:
                    show_indicator = False
                    if user_type == "customer":
                        # Для заказчика: показываем "•" рядом с СОБСТВЕННЫМИ сообщениями,
                        # которые исполнитель НЕ ПРОЧИТАЛ
                        if msg_sender == "customer" and customer_msg_index >= 0:
                            # Показываем "•" если исполнитель не прочитал это сообщение
                            show_indicator = customer_msg_index >= last_read_by_worker
                    else:  # worker
                        # Для исполнителя: показываем "•" рядом с СОБСТВЕННЫМИ сообщениями,
                        # которые заказчик НЕ ПРОЧИТАЛ
                        if msg_sender == "worker" and worker_msg_index >= 0:
                            # Показываем "•" если заказчик не прочитал это сообщение
                            show_indicator = worker_msg_index >= last_read_by_customer

                    # Добавляем индикатор неотвеченного сообщения
                    unread_indicator = " • " if show_indicator else ""

                sender_name = get_sender_name(msg_sender, user_type, worker, customer)
                chat_history += f"{unread_indicator} <b>{sender_name}:</b> {msg_text}\n"

        return chat_history

    except Exception as e:
        logger.error(f"Error in format_chat_history_for_display: {e}")
        return ""


async def send_or_update_chat_message(user_id: int, user_type: str, abs_id: int,
                                      worker, customer, message_text: str, sender: str):
    """
    Отправляет новое сообщение или обновляет существующее сообщение чата
    с полной историей диалога
    
    ВАЖНО: НЕ обновляет счетчики прочитанных сообщений при отправке,
    т.к.нельзя узнать, открыл ли пользователь уведомление или нет.
    Счетчики обновляются только при открытии раздела "Отклики".
    """
    try:
        # Небольшая задержка для обеспечения консистентности БД
        import asyncio
        await asyncio.sleep(0.1)

        # Получаем WorkersAndAbs для истории сообщений
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
        if not response:
            logger.warning(f"[CHAT_HISTORY] WorkersAndAbs not found for worker_id={worker.id}, abs_id={abs_id}")
            return

        logger.info(
            f"[CHAT_HISTORY] Loading chat history. Worker messages: {len(response.worker_messages) if response.worker_messages else 0}, Customer messages: {len(response.customer_messages) if response.customer_messages else 0}")

        # Получаем списки сообщений
        worker_messages_list = []
        customer_messages_list = []

        # Фильтруем worker_messages: убираем служебное сообщение и пустые
        if response.worker_messages:
            worker_messages_list = [
                msg for msg in response.worker_messages
                if msg and msg.strip() and msg != "Исполнитель не отправил сообщение"
            ]

        # Фильтруем customer_messages: убираем пустые
        if response.customer_messages:
            customer_messages_list = [
                msg for msg in response.customer_messages
                if msg and msg.strip()
            ]

        # Создаем единый список всех сообщений с их индексами и отправителем
        all_messages = []

        # Добавляем сообщения исполнителя с индексами
        for i, msg in enumerate(worker_messages_list):
            if msg and msg.strip():
                all_messages.append({
                    'text': msg,
                    'sender': 'worker',
                    'index': i,
                    'sender_type': 'worker'
                })

        # Добавляем сообщения заказчика с индексами
        for i, msg in enumerate(customer_messages_list):
            if msg and msg.strip():
                all_messages.append({
                    'text': msg,
                    'sender': 'customer',
                    'index': i,
                    'sender_type': 'customer'
                })

        # НОВОЕ РЕШЕНИЕ: Используем временные метки для правильной сортировки

        ordered_messages = []

        # Получаем временные метки из БД
        timestamps_list = response.message_timestamps if hasattr(response, 'message_timestamps') else []

        # Если есть временные метки - используем их для сортировки
        if timestamps_list and len(timestamps_list) > 0:
            logger.info(f"[CHAT_HISTORY] Using timestamps for sorting: {len(timestamps_list)} timestamps")

            # Создаем единый список всех сообщений с временными метками
            all_messages_with_timestamps = []

            # Индексы для сообщений каждого типа
            worker_msg_idx = 0
            customer_msg_idx = 0

            # Проходим по временным меткам один раз и сопоставляем с сообщениями
            for ts_data in timestamps_list:
                if ts_data['sender'] == 'worker' and worker_msg_idx < len(worker_messages_list):
                    msg = worker_messages_list[worker_msg_idx]
                    # Сообщения уже отфильтрованы при загрузке из БД
                    all_messages_with_timestamps.append({
                        'text': msg,
                        'sender': 'worker',
                        'timestamp': ts_data['timestamp']
                    })
                    worker_msg_idx += 1
                elif ts_data['sender'] == 'customer' and customer_msg_idx < len(customer_messages_list):
                    msg = customer_messages_list[customer_msg_idx]
                    # Сообщения уже отфильтрованы при загрузке из БД
                    all_messages_with_timestamps.append({
                        'text': msg,
                        'sender': 'customer',
                        'timestamp': ts_data['timestamp']
                    })
                    customer_msg_idx += 1

            # Сортируем по временным меткам
            sorted_messages = sorted(all_messages_with_timestamps, key=lambda x: x['timestamp'])

            # Формируем финальный список
            for msg_data in sorted_messages:
                ordered_messages.append({
                    'text': msg_data['text'],
                    'sender': msg_data['sender']
                })
        else:
            # Если временных меток нет - используем старую логику (для обратной совместимости)
            logger.info(f"[CHAT_HISTORY] No timestamps, using fallback logic")

            worker_count = len(worker_messages_list)
            customer_count = len(customer_messages_list)

            # Старая логика чередования
            if abs(worker_count - customer_count) <= 1:
                worker_idx = 0
                customer_idx = 0
                while worker_idx < worker_count or customer_idx < customer_count:
                    if worker_idx < worker_count:
                        msg = worker_messages_list[worker_idx]
                        # Сообщения уже отфильтрованы при загрузке из БД
                        ordered_messages.append({'text': msg, 'sender': 'worker'})
                        worker_idx += 1
                    if customer_idx < customer_count:
                        msg = customer_messages_list[customer_idx]
                        # Сообщения уже отфильтрованы при загрузке из БД
                        ordered_messages.append({'text': msg, 'sender': 'customer'})
                        customer_idx += 1

        # Формируем заголовок
        if user_type == "customer":
            worker_name = worker.profile_name or worker.tg_name or "Исполнитель"
            header = f"💬 <b>Чат с исполнителем</b>\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {worker_name}\n\n"
        else:  # worker
            header = f"💬 <b>Чат с заказчиком</b>\n\n📋 Объявление: #{abs_id}\n👤 Заказчик: ID#{customer.id}\n\n"

        # Проверяем, есть ли вообще сообщения
        if not ordered_messages:
            full_text = header + "💬 Начните диалог, отправив сообщение."
        else:
            # Динамически подбираем количество сообщений с учетом лимита Telegram (4096 символов)
            MAX_MESSAGE_LENGTH = 4000  # Оставляем запас
            MAX_MESSAGES_INITIAL = min(15, len(ordered_messages))

            full_text = ""
            messages_shown = 0

            # Пытаемся показать максимальное количество сообщений
            for limit in range(MAX_MESSAGES_INITIAL, 0, -1):
                # Берем последние N сообщений
                selected_messages = ordered_messages[-limit:]

                # Формируем историю переписки
                chat_history = ""
                for msg_data in selected_messages:
                    msg_text = msg_data['text']
                    msg_sender = msg_data['sender']

                    sender_name = get_sender_name(msg_sender, user_type, worker, customer)
                    chat_history += f" <b>{sender_name}:</b> {msg_text}\n"

                # Формируем полный текст
                full_text = header + "📝 <b>История переписки:</b>\n" + chat_history

                # Проверяем длину
                if len(full_text) <= MAX_MESSAGE_LENGTH:
                    messages_shown = limit
                    break

            # Если прошли все итерации и ничего не влезло, показываем специальное сообщение
            if messages_shown == 0:
                full_text = header + "💬 История переписки слишком длинная.\n\nОтправьте новое сообщение, чтобы продолжить диалог."

        # Проверяем статус контактов для кнопок
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        # contact_requested = True если исполнитель запросил контакты (есть ContactExchange)
        contact_requested = contact_exchange is not None
        # contacts_sent = True если заказчик подтвердил передачу контактов
        contacts_sent = contact_exchange and contact_exchange.contacts_sent
        # contacts_purchased = True если контакты куплены/получены исполнителем
        contacts_purchased = contact_exchange and contact_exchange.contacts_purchased

        # Отладочная информация
        logger.info(f"[CHAT_STATUS] ContactExchange found: {contact_exchange is not None}")
        if contact_exchange:
            logger.info(f"[CHAT_STATUS] contacts_purchased: {contact_exchange.contacts_purchased}")
            logger.info(f"[CHAT_STATUS] contacts_sent: {contact_exchange.contacts_sent}")
            logger.info(f"[CHAT_STATUS] ContactExchange ID: {contact_exchange.id}")
            logger.info(f"[CHAT_STATUS] Worker ID: {contact_exchange.worker_id}, ABS ID: {contact_exchange.abs_id}")

        kbc = KeyboardCollection()

        if user_type == "customer":
            # Кнопки для заказчика
            reply_markup = kbc.anonymous_chat_customer_buttons(
                worker_id=worker.id,
                abs_id=abs_id,
                contact_requested=contact_requested,
                contact_sent=contacts_sent,
                contacts_purchased=contacts_purchased
            )
        else:  # worker
            # Кнопки для исполнителя
            # worker_initiated = True если исполнитель сам запросил контакты (contacts_sent=False в ContactExchange)
            # worker_initiated = False если заказчик предложил контакты (contacts_sent=True в ContactExchange)
            worker_initiated = contact_exchange and not contact_exchange.contacts_sent
            reply_markup = kbc.anonymous_chat_worker_buttons(
                abs_id=abs_id,
                has_contacts=contacts_purchased,
                contacts_requested=contacts_sent,  # Заказчик подтвердил/предложил
                contacts_sent=contact_requested and not contacts_sent,  # Исполнитель запросил, ждет
                worker_initiated=worker_initiated
            )

        # Проверяем, есть ли уже сообщение чата для этого пользователя
        # Для простоты пока отправляем новое сообщение каждый раз
        # В будущем можно добавить сохранение message_id в базе данных
        await bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Error in send_or_update_chat_message: {e}")
        # Fallback - отправляем простое уведомление
        if user_type == "customer":
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 <b>Новое сообщение от исполнителя</b>\n\n📋 Объявление: #{abs_id}\n\n💬 <b>Сообщение:</b>\n{message_text}",
                parse_mode='HTML'
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 <b>Новое сообщение от заказчика</b>\n\n📋 Объявление: #{abs_id}\n\n💬 <b>Сообщение:</b>\n{message_text}",
                parse_mode='HTML'
            )


async def format_contact_transactions_history(worker_id: int, limit: int = 20) -> str:
    """
    Формирует текстовую историю покупок и списаний контактов исполнителя.
    """
    try:
        transactions = await ContactTransaction.get_by_worker(worker_id, limit)
        if not transactions:
            return (
                "📜 <b>История списаний пуста</b>\n\n"
                "Как только вы купите или используете контакты, записи появятся здесь."
            )

        lines: list[str] = []
        for tx in transactions:
            try:
                timestamp = datetime.strptime(tx.created_at, "%Y-%m-%d %H:%M:%S")
                date_str = timestamp.strftime("%d.%m.%Y %H:%M")
            except ValueError:
                date_str = tx.created_at

            details = tx.details or {}
            if tx.action == "purchase":
                amount = tx.change_amount
                tariff_name = details.get("tariff_name")
                price_rub = details.get("price_rub")
                tariff_text = f" (тариф: {tariff_name})" if tariff_name else ""
                price_text = f" за {price_rub}₽" if price_rub is not None else ""
                contacts_text = f"{amount} {get_contact_word(amount)}" if amount else "Покупка контактов"
                lines.append(f"🟢 {date_str} — Куплено {contacts_text}{tariff_text}{price_text}")
            elif tx.action == "unlimited_purchase":
                tariff_name = details.get("tariff_name")
                valid_until = details.get("valid_until")
                price_rub = details.get("price_rub")
                price_text = f" за {price_rub}₽" if price_rub is not None else ""
                if valid_until:
                    try:
                        until_dt = datetime.strptime(valid_until, "%Y-%m-%d")
                        until_text = f" до {until_dt.strftime('%d.%m.%Y')}"
                    except ValueError:
                        until_text = f" до {valid_until}"
                else:
                    until_text = ""
                name_text = f"{tariff_name}" if tariff_name else "Безлимит"
                lines.append(f"🟢 {date_str} — Оформлен безлимит {name_text}{until_text}{price_text}")
            elif tx.action == "usage":
                abs_id = tx.abs_id or details.get("abs_id")
                source = details.get("source", "purchased")
                spent = details.get("contacts_spent") or abs(tx.change_amount) or 1
                abs_text = f"объявлению #{abs_id}" if abs_id else "объявлению (ID не указан)"
                if source == "unlimited":
                    lines.append(f"⚪ {date_str} — Контакт передан по {abs_text} (безлимит)")
                else:
                    contact_word = get_contact_word(spent)
                    lines.append(f"🔻 {date_str} — Списано {spent} {contact_word} для {abs_text}")
            else:
                lines.append(f"• {date_str} — {tx.action}")

        history_text = "📜 <b>История списаний</b>\n\n" + "\n".join(lines)
        if len(transactions) == limit:
            history_text += f"\n\nПоказаны последние {limit} операций."
        return history_text
    except Exception as error:
        logger.error(f"Error while formatting contact transactions history: {error}")
        return (
            "📜 <b>История списаний недоступна</b>\n\n"
            "Попробуйте позже."
        )


# ========== HANDLERS ДЛЯ ЗАКАЗЧИКА ==========

@router.callback_query(lambda c: c.data == "noop")
async def handle_noop_button(callback: CallbackQuery):
    """Обработчик для неактивных кнопок"""
    await callback.answer("ℹ️ Действие недоступно", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_contact_share_'))
async def confirm_contact_share(callback: CallbackQuery, state: FSMContext):
    """Заказчик подтверждает передачу контактов"""
    try:
        # confirm_contact_share_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(
            f"[CONTACT_SHARE] Customer {callback.from_user.id} confirmed contact share for worker {worker_id}, abs {abs_id}")
        logger.info(f"[CONTACT_SHARE] Customer confirmed contact share")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        worker = await Worker.get_worker(id=worker_id)
        advertisement = await Abs.get_one(id=abs_id)

        if not customer or not worker or not advertisement:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Проверяем, что запрос контакта все еще активен
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if not contact_exchange:
            await callback.answer("❌ Запрос контакта уже отменен исполнителем", show_alert=True)
            return

        # Проверяем, не подтвердил ли уже заказчик передачу контактов
        if contact_exchange.contacts_sent:
            await callback.answer("⚠️ Контакты уже подтверждены для передачи!", show_alert=True)
            return

        # Получаем текст объявления
        ad_text = ""
        try:
            advertisement = await Abs.get_one(id=abs_id)
            if advertisement and advertisement.text_path:
                ad_text = read_text_file(advertisement.text_path) or ""
                # Ограничиваем длину текста объявления
                MAX_AD_TEXT_LENGTH = 1500
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"
        except Exception as e:
            print(e)

        # Обновляем запись - заказчик подтвердил
        await contact_exchange.update(contacts_sent=True)

        kbc = KeyboardCollection()

        # СЦЕНАРИЙ 1: Исполнитель имеет безлимитную подписку
        if worker.unlimited_contacts_until:
            try:
                end_date = datetime.strptime(worker.unlimited_contacts_until, "%Y-%m-%d")
                if end_date > datetime.now():
                    # Безлимит активен - сразу передаем контакты
                    await contact_exchange.update(contacts_purchased=True)

                    await ContactTransaction.log_usage(worker_id=worker.id, abs_id=abs_id, source="unlimited")

                    # Передаем контакты исполнителю с учетом нового функционала
                    contacts_text = (
                        f"📞 <b>Контакты заказчика:</b>\n\n"
                        f"{await parse_contacts_message(customer)}"
                    )

                    # Отправляем уведомление исполнителя
                    await send_contacts_to_worker(worker, customer, abs_id, ad_text, contacts_text)

                    # Отправляем уведомление заказчику
                    await send_notification_to_customer(customer, worker, abs_id, ad_text)

                    # Закрываем чат
                    response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
                    if response:
                        await response.update(applyed=False)

                    # Обновляем исходное сообщение заказчика
                    try:
                        # Получаем исходный текст сообщения
                        original_text = "Запрос контакта от исполнителя\n\n"
                        original_text += f"Объявление: #{abs_id}\n"
                        original_text += f"ID: {worker.id}\n"
                        original_text += f"Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}/5 ({worker.count_ratings} оценок)\n"
                        original_text += f"Статус: {'ИП ✅' if worker.individual_entrepreneur else 'Не подтвержден ⚠️'}\n"
                        original_text += f"Выполнено заказов: {worker.order_count}\n"
                        original_text += f"Зарегистрирован: {worker.registration_data}\n\n"
                        original_text += "✅ <b>Контакты переданы исполнителю!</b>"

                        # Проверяем, есть ли фото в сообщении
                        if callback.message.photo:
                            # Если есть фото, редактируем caption
                            await callback.message.edit_caption(
                                caption=original_text,
                                reply_markup=kbc.anonymous_chat_customer_buttons(
                                    worker_id=worker_id,
                                    abs_id=abs_id,
                                    contact_requested=True,
                                    contact_sent=True,
                                    contacts_purchased=True
                                ),
                                parse_mode='HTML'
                            )
                        else:
                            # Если нет фото, редактируем текст
                            await callback.message.answer(
                                text=original_text,
                                reply_markup=kbc.anonymous_chat_customer_buttons(
                                    worker_id=worker_id,
                                    abs_id=abs_id,
                                    contact_requested=True,
                                    contact_sent=True,
                                    contacts_purchased=True
                                ),
                                parse_mode='HTML'
                            )
                    except Exception as edit_error:
                        # Если не можем отредактировать, отправляем новое сообщение
                        await callback.message.answer(
                            text="✅ <b>Контакты переданы исполнителю!</b>",
                            reply_markup=kbc.anonymous_chat_customer_buttons(
                                worker_id=worker_id,
                                abs_id=abs_id,
                                contact_requested=True,
                                contact_sent=True,
                                contacts_purchased=True
                            ),
                            parse_mode='HTML'
                        )

                    await callback.answer("✅ Контакты переданы исполнителю!")
                    return
            except ValueError:
                pass  # Неверный формат даты

        # СЦЕНАРИЙ 2: Исполнитель имеет купленные контакты
        if worker.purchased_contacts > 0:
            # Есть купленные контакты - сразу списываем и передаем
            new_count = worker.purchased_contacts - 1
            await worker.update_purchased_contacts(purchased_contacts=new_count)

            # Обновляем ContactExchange
            await contact_exchange.update(contacts_purchased=True)

            await ContactTransaction.log_usage(worker_id=worker.id, abs_id=abs_id, source="purchased")

            # Передаем контакты исполнителю с учетом нового функционала
            contacts_text = f"📞 <b>Контакты заказчика:</b>\n\n {await parse_contacts_message(customer)}"

            # Уведомляем исполнителя
            await send_contacts_to_worker(worker, customer, abs_id, ad_text, contacts_text)

            # Уведомляем заказчика
            await send_notification_to_customer(customer, worker, abs_id, ad_text)

            # Закрываем чат
            response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
            if response:
                await response.update(applyed=False)

            await callback.answer("✅ Контакты переданы исполнителю!")
            return

        notification_text = (
            f"🔔 <b>Заказчик подтвердил передачу контактов!</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
        )

        # Добавляем текст объявления, если есть
        if ad_text:
            notification_text += f"📝 <b>Текст объявления:</b>\n{ad_text}"

        notification_text += (
            f"💰 У вас нет купленных контактов.\n"
            f"Для получения контактов вам необходимо купить контакты."
        )

        # Показываем кнопки покупки контактов
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline(button_text="💳 Купить контакты",
                                callback_data=f"buy_contacts_for_abs_{abs_id}"))
        builder.add(kbc._inline(button_text="❌ Отказаться",
                                callback_data=f"reject_contact_offer_{abs_id}"))
        builder.adjust(1)

        await bot.send_message(
            chat_id=worker.tg_id,
            text=notification_text,
            reply_markup=builder.as_markup(),
            parse_mode='HTML'
        )

        # Обновляем исходное сообщение заказчика
        try:
            # Получаем исходный текст сообщения
            original_text = "Запрос контакта от исполнителя\n\n"
            original_text += f"Объявление: #{abs_id}\n"
            original_text += f"ID: {worker.id}\n"
            original_text += f"Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}/5 ({worker.count_ratings} оценок)\n"
            original_text += f"Статус: {'ИП ✅' if worker.individual_entrepreneur else 'Не подтвержден ⚠️'}\n"
            original_text += f"Выполнено заказов: {worker.order_count}\n"
            original_text += f"Зарегистрирован: {worker.registration_data}\n\n"
            original_text += "⏳ <b>Ожидаем решения исполнителя...</b>"

            # Проверяем, есть ли фото в сообщении
            if callback.message.photo:
                # Если есть фото, редактируем caption
                await callback.message.edit_caption(
                    caption=original_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=True,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
            else:
                # Если нет фото, редактируем текст
                await callback.message.answer(
                    text=original_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=True,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
        except Exception as edit_error:
            # Если не можем отредактировать, отправляем новое сообщение
            await callback.message.answer(
                text="⏳ <b>Ожидаем решения исполнителя...</b>",
                reply_markup=kbc.anonymous_chat_customer_buttons(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    contact_requested=True,
                    contact_sent=True,
                    contacts_purchased=False
                ),
                parse_mode='HTML'
            )

        await callback.answer("✅ Контакты подтверждены для передачи!")

    except Exception as e:
        logger.error(f"Error in confirm_contact_share: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('buy_contacts_for_abs_'))
async def buy_contacts_for_abs(callback: CallbackQuery, state: FSMContext):
    """Покупка контактов для конкретного объявления"""
    try:
        # buy_contacts_for_abs_{abs_id}
        parts = callback.data.split('_')
        abs_id = int(parts[4])

        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        if not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Получаем объявление
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        # Проверяем, что заказчик подтвердил передачу контактов
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if not contact_exchange or not contact_exchange.contacts_sent:
            await callback.answer("❌ Заказчик еще не подтвердил передачу контактов", show_alert=True)
            return

        # Проверяем, не куплены ли уже контакты
        if contact_exchange.contacts_purchased:
            await callback.answer("✅ Контакты уже получены", show_alert=True)
            return

        # Проверяем, есть ли у исполнителя купленные контакты
        if worker.purchased_contacts > 0:
            # Есть купленные контакты - сразу списываем и передаем
            new_count = worker.purchased_contacts - 1
            await worker.update_purchased_contacts(purchased_contacts=new_count)

            # Обновляем ContactExchange
            await contact_exchange.update(contacts_purchased=True)

            await ContactTransaction.log_usage(worker_id=worker.id, abs_id=abs_id, source="purchased")

            # Передаем контакты исполнителю с учетом нового функционала
            contacts_text = f"📞 <b>Контакты заказчика:</b>\n\n {await parse_contacts_message(customer)}"

            # Получаем текст объявления
            advertisement = await Abs.get_one(id=abs_id)
            ad_text = ""
            if advertisement and advertisement.text_path:
                ad_text = read_text_file(advertisement.text_path) or ""
                # Ограничиваем длину текста объявления
                MAX_AD_TEXT_LENGTH = 1500
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

            # Уведомляем исполнителя
            await send_contacts_to_worker(worker, customer, abs_id, ad_text, contacts_text)

            # Уведомляем заказчика
            await  send_notification_to_customer(customer, worker, abs_id, ad_text)

            # Закрываем чат
            response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
            if response:
                await response.update(applyed=False)

            # Устанавливаем правильное состояние
            await state.set_state(WorkStates.worker_menu)

            await callback.answer("✅ Контакты получены!")
            return

        # Нет купленных контактов - показываем тарифы покупки
        kbc = KeyboardCollection()
        try:
            await callback.message.answer(
                text="💰 <b>Тарифы на покупку контактов</b>\n\nВыберите подходящий тариф:",
                reply_markup=await kbc.buy_tokens_tariffs(abs_id),
                parse_mode='HTML'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text="💰 <b>Тарифы на покупку контактов</b>\n\nВыберите подходящий тариф:",
                reply_markup=await kbc.buy_tokens_tariffs(abs_id),
                parse_mode='HTML'
            )

        # Сохраняем данные для последующей покупки
        await state.update_data(
            buying_contacts_for_abs=True,
            target_worker_id=worker.id,
            target_abs_id=abs_id
        )

    except Exception as e:
        logger.error(f"Error in buy_contacts_for_abs: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('reject_contact_offer_') and len(c.data.split('_')) == 4)
async def reject_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Исполнитель отказывается от покупки контактов (когда заказчик подтвердил передачу)"""
    try:
        # reject_contact_offer_{abs_id}
        parts = callback.data.split('_')
        abs_id = int(parts[3])

        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        if not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Получаем заказчика из объявления
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)

        # Уведомляем заказчика об отказе
        ad_text = read_text_file(advertisement.text_path) if advertisement.text_path else ""
        if ad_text:
            MAX_AD_TEXT_LENGTH = 1500
            if len(ad_text) > MAX_AD_TEXT_LENGTH:
                ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

        customer_notification = (
            f"❌ <b>Исполнитель отказался от покупки контактов</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
        )
        if ad_text:
            customer_notification += f"📝 <b>Текст объявления:</b>\n{ad_text}\n"
        customer_notification += "Отклик возвращен в обычный режим."

        kbc = KeyboardCollection()
        await bot.send_message(
            chat_id=customer.tg_id,
            text=customer_notification,
            parse_mode='HTML',
            reply_markup=kbc.get_customer_keyboard(worker.id, abs_id),
        )

        # Удаляем запись ContactExchange
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange:
            await contact_exchange.delete()

        # Обновляем сообщение исполнителя
        await callback.answer("❌ Вы отказались от покупки контактов", show_alert=True)

        # Возвращаем исполнителя к отклику
        new_callback = callback.model_copy(update={'data': f"view_my_response_{abs_id}"})
        await view_my_response(new_callback, state)

    except Exception as e:
        logger.error(f"Error in reject_contact_offer: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('decline_contact_share_'))
async def decline_contact_share(callback: CallbackQuery, state: FSMContext):
    """Заказчик отклоняет передачу контактов"""
    try:
        # decline_contact_share_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(
            f"[CONTACT_SHARE] Customer {callback.from_user.id} declined contact share for worker {worker_id}, abs {abs_id}"
        )
        logger.info(f"[CONTACT_SHARE] Customer declined contact share")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        worker = await Worker.get_worker(id=worker_id)
        advertisement = await Abs.get_one(id=abs_id)

        if not customer or not worker or not advertisement:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Проверяем, что запрос контакта все еще активен
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if not contact_exchange:
            await callback.answer("❌ Запрос контакта уже отменен исполнителем", show_alert=True)
            return

        kbc = KeyboardCollection()

        # Сохраняем message_id перед удалением contact_exchange
        message_id_to_delete = None
        if contact_exchange.message_id:
            message_id_to_delete = contact_exchange.message_id

        # Удаляем запись ContactExchange
        await contact_exchange.delete()

        ad_text = ""
        if advertisement and advertisement.text_path:
            ad_text = read_text_file(advertisement.text_path) or ""
            MAX_AD_TEXT_LENGTH = 1200
            if len(ad_text) > MAX_AD_TEXT_LENGTH:
                ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

        # Уведомляем исполнителя
        notification_text = (
            f"❌ <b>Заказчик отклонил передачу контактов</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
        )

        if ad_text:
            notification_text += f"📝 <b>Текст объявления:</b>\n{ad_text}\n\n"

        notification_text += (
            "К сожалению, заказчик не готов поделиться контактами.\n"
            "Вы можете запросить контакт позже."
        )

        await bot.send_message(
            chat_id=worker.tg_id,
            text=notification_text,
            parse_mode='HTML',
            reply_markup=kbc.get_worker_keyboard(abs_id),
        )

        # Удаляем сообщение с предложением контактов, если оно есть
        if message_id_to_delete:
            try:
                await bot.delete_message(chat_id=worker.tg_id, message_id=message_id_to_delete)
                print(
                    f"[MESSAGE_DELETE] Deleted contact offer message {message_id_to_delete} for worker {worker.tg_id}")
            except Exception as e:
                logger.error(f"Error deleting contact offer message: {e}")
                print(f"[MESSAGE_DELETE] Failed to delete contact offer message {message_id_to_delete}: {e}")

        # Возвращаем заказчика к списку откликов
        kbc = KeyboardCollection()

        # Получаем текст из сообщения (может быть text или caption)
        current_text = callback.message.text or callback.message.caption or ""
        new_text = current_text + "\n\n❌ <b>Передача контактов отклонена.</b>"

        # Безопасное редактирование (может быть фото)
        try:
            if callback.message.text:
                await callback.message.answer(
                    text=new_text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=[{
                            'worker_id': worker_id,
                            'worker_public_id': f'ID#{worker.id}',
                            'worker_name': worker.profile_name,  # Только profile_name, не tg_name
                            'worker_stars': worker.stars,
                            'worker_ratings': worker.count_ratings,
                            'active': True
                        }],
                        abs_id=abs_id
                    ),
                    parse_mode='HTML'
                )
            else:
                # Если было фото с caption
                await callback.message.edit_caption(
                    caption=new_text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=[{
                            'worker_id': worker_id,
                            'worker_public_id': f'ID#{worker.id}',
                            'worker_name': worker.profile_name,  # Только profile_name, не tg_name
                            'worker_stars': worker.stars,
                            'worker_ratings': worker.count_ratings,
                            'active': True
                        }],
                        abs_id=abs_id
                    ),
                    parse_mode='HTML'
                )
        except Exception:
            # Если не получилось, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=new_text,
                reply_markup=kbc.customer_responses_list_buttons(
                    responses_data=[{
                        'worker_id': worker_id,
                        'worker_public_id': f'ID#{worker.id}',
                        'worker_name': worker.profile_name or worker.tg_name,
                        'worker_stars': worker.stars,
                        'worker_ratings': worker.count_ratings,
                        'active': True
                    }],
                    abs_id=abs_id
                ),
                parse_mode='HTML'
            )

        await callback.answer("❌ Передача контактов отклонена")

    except Exception as e:
        logger.error(f"Error in decline_contact_share: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('offer_contact_share_'))
async def offer_contact_share(callback: CallbackQuery, state: FSMContext):
    """Заказчик предлагает передать контакты исполнителю"""
    try:
        # offer_contact_share_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(
            f"[CONTACT_OFFER] Customer {callback.from_user.id} offers contact share for worker {worker_id}, abs {abs_id}")
        logger.info(f"[CONTACT_OFFER] Customer offers contact share")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        worker = await Worker.get_worker(id=worker_id)

        if not customer or not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Создаем или обновляем запись о том, что заказчик предложил контакты
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if not contact_exchange:
            # Получаем customer_id
            customer_id = customer.id
            contact_exchange = ContactExchange(
                id=None,
                worker_id=worker_id,
                customer_id=customer_id,
                abs_id=abs_id,
                contacts_sent=True,  # Заказчик предложил
                contacts_purchased=False,
                message_id=None  # Будет обновлено после отправки сообщения
            )
            await contact_exchange.save()
        else:
            # Проверяем, не было ли уже отправлено сообщение
            if contact_exchange.contacts_sent and contact_exchange.message_id:
                await callback.answer("⚠️ Контакты уже предложены исполнителю!", show_alert=True)
                return

            # Обновляем существующую запись
            await contact_exchange.update(contacts_sent=True)
            # message_id будет обновлен после отправки сообщения

        # Получаем текст объявления
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        ad_text = read_text_file(
            advertisement.text_path) if advertisement.text_path else "Текст объявления не найден"

        # Ограничиваем длину текста объявления (оставляем запас для остального текста)
        MAX_AD_TEXT_LENGTH = 2000  # Максимальная длина текста объявления в уведомлении
        if len(ad_text) > MAX_AD_TEXT_LENGTH:
            ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

        # Проверяем, есть ли история переписки
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
        has_history = False
        if response:
            worker_messages_list = []
            customer_messages_list = []

            if response.worker_messages:
                worker_messages_list = [
                    msg for msg in response.worker_messages
                    if msg and msg.strip() and msg != "Исполнитель не отправил сообщение"
                ]

            if response.customer_messages:
                customer_messages_list = [
                    msg for msg in response.customer_messages
                    if msg and msg.strip()
                ]

            has_history = len(worker_messages_list) > 0 or len(customer_messages_list) > 0

        # Уведомляем исполнителя с кнопками принятия/отклонения
        notification_text = (
            f"🔔 <b>Заказчик предлагает передать контакты!</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
            f"📝 <b>Текст объявления:</b>\n{ad_text}"
            f"Хотите получить контакты заказчика?"
        )

        kbc = KeyboardCollection()
        message = await bot.send_message(
            chat_id=worker.tg_id,
            text=notification_text,
            reply_markup=kbc.accept_contact_offer_keyboard(has_history, worker_id, abs_id),
            parse_mode='HTML'
        )

        # Сохраняем message_id в ContactExchange
        await contact_exchange.update(message_id=message.message_id)

        # Обновляем кнопки заказчика
        # Получаем текст или caption (если было фото)
        current_text = callback.message.text or callback.message.caption or ""
        new_text = current_text + "\n\n✅ <b>Контакты предложены исполнителю!</b>"

        # Безопасное редактирование
        try:
            if callback.message.text:
                await callback.message.answer(
                    text=new_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=True,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
            else:
                # Если было фото, редактируем caption
                await callback.message.edit_caption(
                    caption=new_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=True,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
        except Exception:
            # Если не получилось, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=new_text,
                reply_markup=kbc.anonymous_chat_customer_buttons(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    contact_requested=True,
                    contact_sent=True,
                    contacts_purchased=False
                ),
                parse_mode='HTML'
            )

        await callback.answer("✅ Контакты предложены исполнителю!")

    except Exception as e:
        logger.error(f"Error in offer_contact_share: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('accept_contact_offer_'))
async def accept_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Исполнитель принимает предложение контактов"""
    try:
        # accept_contact_offer_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(f"[CONTACT_ACCEPT] Worker {callback.from_user.id} accepts contact offer for abs {abs_id}")
        logger.info(f"[CONTACT_ACCEPT] Worker accepts contact offer")

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker or worker.id != worker_id:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        customer = await Customer.get_customer(id=(await Abs.get_one(id=abs_id)).customer_id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        # Проверяем есть ли у исполнителя безлимит или купленные контакты
        has_unlimited = worker.unlimited_contacts_until and datetime.now() < datetime.fromisoformat(
            worker.unlimited_contacts_until)
        has_purchased = worker.purchased_contacts > 0

        kbc = KeyboardCollection()

        if has_unlimited or has_purchased:
            # Передаем контакты
            if has_purchased and not has_unlimited:
                # Уменьшаем количество купленных контактов
                new_count = worker.purchased_contacts - 1
                await worker.update_purchased_contacts(purchased_contacts=new_count)

            # Обновляем статус в БД
            contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
            if contact_exchange:
                await contact_exchange.update(contacts_purchased=True)

            usage_source = "unlimited" if has_unlimited else "purchased"
            await ContactTransaction.log_usage(worker_id=worker.id, abs_id=abs_id, source=usage_source)

            # Закрываем чат - обновляем WorkersAndAbs
            response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
            if response:
                await response.update(applyed=False)  # Закрываем чат

            # Получаем текст объявления
            ad_text = ""
            try:
                advertisement = await Abs.get_one(id=abs_id)
                if advertisement and advertisement.text_path:
                    ad_text = read_text_file(advertisement.text_path) or ""
                    # Ограничиваем длину текста объявления
                    MAX_AD_TEXT_LENGTH = 1500
                    if len(ad_text) > MAX_AD_TEXT_LENGTH:
                        ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"
            except Exception as e:
                print(e)

            # Уведомляем заказчика о закрытии чата
            await send_notification_to_customer(customer, worker, abs_id, ad_text)

            # Уведомляем исполнителя
            contacts_text = f"📞 <b>Контакты заказчика:</b>\n\n {await parse_contacts_message(customer)}"
            await send_contacts_to_worker(worker, customer, abs_id, ad_text, contacts_text)
            await callback.answer("✅ Контакты получены! Чат закрыт.")
        else:
            # Показываем тарифы для покупки
            try:
                await callback.message.answer(
                    text=f"💰 <b>Для получения контактов необходимо оплатить</b>\n\n"
                         f"📋 Объявление: #{abs_id}\n"
                         f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                         f"Выберите тариф:",
                    reply_markup=await kbc.buy_tokens_tariffs(abs_id),
                    parse_mode='HTML'
                )
            except TelegramBadRequest:
                # Если сообщение недоступно для редактирования, отправляем новое
                await callback.message.answer(
                    text=f"💰 <b>Для получения контактов необходимо оплатить</b>\n\n"
                         f"📋 Объявление: #{abs_id}\n"
                         f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                         f"Выберите тариф:",
                    reply_markup=await kbc.buy_tokens_tariffs(abs_id),
                    parse_mode='HTML'
                )

            # Сохраняем данные для последующей покупки
            await state.update_data(
                buying_contacts_for_abs=True,
                target_worker_id=worker.id,
                target_abs_id=abs_id
            )

            await callback.answer("💰 Выберите тариф для покупки контактов")

    except Exception as e:
        logger.error(f"Error in accept_contact_offer: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('show_chat_history_'))
async def show_chat_history(callback: CallbackQuery, state: FSMContext):
    """Показывает историю переписки для исполнителя из уведомления о предложении контактов"""
    try:
        # show_chat_history_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker or worker.id != worker_id:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        # Получаем историю переписки без индикаторов читаемость (все как прочитанные)
        chat_history = await format_chat_history_for_display(
            "worker",
            abs_id,
            worker,
            customer,
            show_unread_indicators=False
        )

        if chat_history:
            history_text = (
                f"📝 <b>История переписки</b>\n\n"
                f"📋 Объявление: #{abs_id}\n"
                f"👤 Заказчик: ID#{customer.id}\n\n"
                f"{chat_history}"
            )
        else:
            history_text = (
                f"📝 <b>История переписки</b>\n\n"
                f"📋 Объявление: #{abs_id}\n"
                f"👤 Заказчик: ID#{customer.id}\n\n"
                f"💬 Переписка еще не началась."
            )

        kbc = KeyboardCollection()

        try:
            await callback.message.answer(
                text=history_text,
                reply_markup=kbc.back_to_contact_offer_keyboard(worker_id, abs_id),
                parse_mode='HTML'
            )
        except TelegramBadRequest:
            await callback.message.answer(
                text=history_text,
                reply_markup=kbc.back_to_contact_offer_keyboard(worker_id, abs_id),
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Error in show_chat_history: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('back_to_contact_offer_'))
async def back_to_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Возврат к уведомлению о предложении контактов"""
    try:
        # back_to_contact_offer_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[4])
        abs_id = int(parts[5])

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker or worker.id != worker_id:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        # Получаем текст объявления
        ad_text = read_text_file(
            advertisement.text_path) if advertisement.text_path else "Текст объявления не найден"

        # Ограничиваем длину текста объявления (оставляем запас для остального текста)
        MAX_AD_TEXT_LENGTH = 2000  # Максимальная длина текста объявления в уведомлении
        if len(ad_text) > MAX_AD_TEXT_LENGTH:
            ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

        # Проверяем, есть ли история переписки
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
        has_history = False
        if response:
            worker_messages_list = []
            customer_messages_list = []

            if response.worker_messages:
                worker_messages_list = [
                    msg for msg in response.worker_messages
                    if msg and msg.strip() and msg != "Исполнитель не отправил сообщение"
                ]

            if response.customer_messages:
                customer_messages_list = [
                    msg for msg in response.customer_messages
                    if msg and msg.strip()
                ]

            has_history = len(worker_messages_list) > 0 or len(customer_messages_list) > 0

        # Формируем текст уведомления
        notification_text = (
            f"🔔 <b>Заказчик предлагает передать контакты!</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
            f"📝 <b>Текст объявления:</b>\n{ad_text}"
            f"Хотите получить контакты заказчика?"
        )

        kbc = KeyboardCollection()

        try:
            await callback.message.answer(
                text=notification_text,
                reply_markup=kbc.accept_contact_offer_keyboard(has_history, worker_id, abs_id),
                parse_mode='HTML'
            )
        except TelegramBadRequest:
            await callback.message.answer(
                text=notification_text,
                reply_markup=kbc.accept_contact_offer_keyboard(has_history, worker_id, abs_id),
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Error in back_to_contact_offer: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('reject_contact_offer_') and len(c.data.split('_')) == 5)
async def reject_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Исполнитель отклоняет предложение контактов (когда заказчик предложил контакты)"""
    try:
        # reject_contact_offer_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(f"[CONTACT_REJECT] Worker {callback.from_user.id} rejects contact offer for abs {abs_id}")
        logger.info(f"[CONTACT_REJECT] Worker rejects contact offer")

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Проверяем, что worker_id в callback_data соответствует текущему исполнителю
        if worker.id != worker_id:
            await callback.answer("❌ Неверный запрос", show_alert=True)
            return

        # Проверяем, что объявление существует (может быть уже удалено)
        advertisement = await Abs.get_one(id=abs_id)

        if advertisement:
            customer = await Customer.get_customer(id=advertisement.customer_id)
            if customer:
                # Получаем текст объявления
                ad_text = read_text_file(
                    advertisement.text_path) if advertisement.text_path else "Текст объявления не найден"

                # Ограничиваем длину текста объявления
                MAX_AD_TEXT_LENGTH = 2000
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

                # Уведомляем заказчика только если объявление и заказчик еще существуют
                try:
                    kbc = KeyboardCollection()

                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=f"❌ <b>Исполнитель отклонил получение контактов</b>\n\n"
                             f"📋 Объявление: #{abs_id}\n"
                             f"👤 Исполнитель: ID#{worker.id}\n\n"
                             f"📝 <b>Текст объявления:</b>\n{ad_text}"
                             f"Исполнитель не готов получить контакты в данный момент.",
                        parse_mode='HTML',
                        reply_markup=kbc.get_customer_keyboard(worker.id, abs_id),
                    )
                except Exception as e:
                    logger.warning(f"Could not notify customer about contact rejection: {e}")

        # Удаляем запись ContactExchange если она существует
        try:
            contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
            if contact_exchange:
                await contact_exchange.delete()
                logger.info(f"[CONTACT_REJECT] Deleted ContactExchange for worker {worker.id}, abs {abs_id}")
        except Exception as e:
            logger.warning(f"Could not delete ContactExchange: {e}")

        # Отправляем подтверждение исполнителю (даже если объявление уже удалено)
        try:
            await callback.answer(
                text="❌ Предложение контактов отклонено\n\n"
                     "Вы отклонили получение контактов заказчика.",
                show_alert=True
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text="❌ Предложение контактов отклонено\n\n"
                     "Вы отклонили получение контактов заказчика.",
                show_alert=True
            )

        # Возвращаем исполнителя к отклику
        new_callback = callback.model_copy(update={'data': f"view_my_response_{abs_id}"})
        await view_my_response(new_callback, state)

    except Exception as e:
        logger.error(f"Error in reject_contact_offer: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== HANDLERS ДЛЯ ЧАТА ==========

@router.message(StateFilter(WorkStates.worker_anonymous_chat))
async def handle_worker_chat_message(message: Message, state: FSMContext):
    """Обработка сообщений исполнителя в анонимном чате"""
    try:
        print(f"[WORKER_CHAT] Worker {message.from_user.id} sent message in chat")
        logger.info(f"[WORKER_CHAT] Worker sent message in chat")

        # Проверяем на контакты
        is_valid, _ = check_message_for_contacts(message.text)
        if not is_valid:
            await message.answer(
                "🚫 <b>Сообщение заблокировано!</b>\n\n"
                "Используйте кнопку «Запросить контакт» для получения контактов заказчика.",
                parse_mode='HTML'
            )
            return

        # Проверяем на запрещенный контент (ссылки, упоминания, номера прописью)
        if is_content_forbidden(message.text):
            await message.answer(
                "🚫 <b>Сообщение заблокировано!</b>\n\n"
                "Запрещённый контент или контактные данные. Исправьте и отправьте снова.",
                parse_mode='HTML'
            )
            return

        # Проверяем на стоп-слова (для сообщений в чате)
        if ban_reason := await fool_check(message.text, is_message=True):
            await message.answer(
                f"🚫 <b>Сообщение заблокировано!</b>\n\n"
                f"Причина: {ban_reason}\n\n"
                "Пожалуйста, переформулируйте сообщение.",
                parse_mode='HTML'
            )
            return

        # Получаем данные чата
        data = await state.get_data()
        abs_id = data.get('current_chat_abs_id')
        customer_id = data.get('current_chat_customer_id')

        if not abs_id or not customer_id:
            await message.answer("❌ Ошибка: данные чата не найдены")
            return

        worker = await Worker.get_worker(tg_id=message.from_user.id)
        customer = await Customer.get_customer(id=customer_id)

        if not worker or not customer:
            await message.answer("❌ Ошибка: пользователь не найден")
            return

        # Получаем запись WorkersAndAbs
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
        if not response:
            await message.answer("❌ Ошибка: отклик не найден")
            return

        # Проверяем, не закрыт ли чат (только если контакты куплены)
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            await message.answer(
                "🔒 <b>Чат закрыт</b> - контакты уже переданы.\nТеперь общайтесь напрямую.",
                parse_mode='HTML'
            )
            return

        # Добавляем сообщение исполнителя
        if response.worker_messages == ['Исполнитель не отправил сообщение']:
            new_worker_messages = [message.text]
        else:
            worker_messages_list = list(response.worker_messages) if response.worker_messages else []
            new_worker_messages = worker_messages_list + [message.text]

        # Получаем сообщения заказчика для обновления счетчика прочитанных
        customer_messages_list = list(response.customer_messages) if response.customer_messages else []

        # Добавляем временную метку
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Получаем текущие метки или создаем пустой список
        current_timestamps = response.message_timestamps if hasattr(response,
                                                                    'message_timestamps') and response.message_timestamps else []

        # Добавляем новую метку
        new_timestamps = current_timestamps + [{"sender": "worker", "timestamp": current_timestamp}]

        # Обновляем в БД
        await response.update(
            worker_messages=new_worker_messages,
            turn=False,  # теперь очередь заказчика
            message_timestamps=new_timestamps,
            last_message_by_worker=len(new_worker_messages),  # обновляем счетчик последнего сообщения
            last_read_by_worker=len(customer_messages_list) # исполнитель "прочитал" сообщения заказчика, отправив ответ
        )

        # Обновляем объект в памяти после сохранения в БД
        response.worker_messages = new_worker_messages
        response.message_timestamps = new_timestamps
        response.turn = False
        response.last_message_by_worker = len(new_worker_messages)
        response.last_read_by_worker = len(customer_messages_list)

        # Отправляем или обновляем сообщение заказчику
        await send_or_update_chat_message(
            user_id=customer.tg_id,
            user_type="customer",
            abs_id=abs_id,
            worker=worker,
            customer=customer,
            message_text=message.text,
            sender="worker"
        )

        await update_worker_or_customer_chat_status(message, data, state, worker=True)

    except Exception as e:
        logger.error(f"Error in handle_worker_chat_message: {e}")
        await message.answer("❌ Произошла ошибка при отправке сообщения")


@router.message(StateFilter(CustomerStates.customer_anonymous_chat))
async def handle_customer_chat_message(message: Message, state: FSMContext):
    """Обработка сообщений заказчика в анонимном чате"""
    try:
        print(f"[CUSTOMER_CHAT] Customer {message.from_user.id} sent message in chat")
        logger.info(f"[CUSTOMER_CHAT] Customer sent message in chat")

        # Проверяем на контакты
        is_valid, _ = check_message_for_contacts(message.text)
        if not is_valid:
            await message.answer(
                "🚫 <b>Сообщение заблокировано!</b>\n\n"
                "Используйте кнопку «Предложить контакты» для передачи контактов исполнителю.",
                parse_mode='HTML'
            )
            return

        # Проверяем на запрещенный контент (ссылки, упоминания, номера прописью)
        if is_content_forbidden(message.text):
            await message.answer(
                f"🚫 <b>Сообщение заблокировано!</b>\n\n"
                f"Запрещённый контент или контактные данные. Исправьте и отправьте снова.",
                parse_mode='HTML'
            )
            return

        # Проверяем на стоп-слова (для сообщений в чате)
        if ban_reason := await fool_check(message.text, is_message=True):
            await message.answer(
                f"🚫 <b>Сообщение заблокировано!</b>\n\n"
                f"Причина: {ban_reason}\n\n"
                "Пожалуйста, переформулируйте сообщение.",
                parse_mode='HTML'
            )
            return

        # Получаем данные чата
        data = await state.get_data()
        abs_id = data.get('current_chat_abs_id')
        worker_id = data.get('current_chat_worker_id')

        if not abs_id or not worker_id:
            await message.answer("❌ Ошибка: данные чата не найдены")
            return

        customer = await Customer.get_customer(tg_id=message.from_user.id)
        worker = await Worker.get_worker(id=worker_id)

        if not customer or not worker:
            await message.answer("❌ Ошибка: пользователь не найден")
            return

        # Получаем запись WorkersAndAbs
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
        if not response:
            await message.answer("❌ Ошибка: отклик не найден")
            return

        # Проверяем, не закрыт ли чат (только если контакты куплены)
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            await message.answer(
                "🔒 <b>Чат закрыт</b> - контакты уже переданы.\nТеперь общайтесь напрямую.",
                parse_mode='HTML'
            )
            return

        # Добавляем сообщение заказчика
        customer_messages_list = list(response.customer_messages) if response.customer_messages else []
        new_customer_messages = customer_messages_list + [message.text]

        # Получаем сообщения исполнителя для обновления счетчика прочитанных
        worker_messages_list = list(response.worker_messages) if response.worker_messages else []

        # Добавляем временную метку
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Получаем текущие метки или создаем пустой список
        current_timestamps = response.message_timestamps if hasattr(response,
                                                                    'message_timestamps') and response.message_timestamps else []

        # Добавляем новую метку
        new_timestamps = current_timestamps + [{"sender": "customer", "timestamp": current_timestamp}]

        # Обновляем в БД
        await response.update(
            customer_messages=new_customer_messages,
            turn=True,  # теперь очередь исполнителя
            message_timestamps=new_timestamps,
            last_message_by_customer=len(new_customer_messages),  # обновляем счетчик последнего сообщения
            last_read_by_customer=len(worker_messages_list)  # заказчик "прочитал" сообщения исполнителя, отправив ответ
        )

        # Обновляем объект в памяти после сохранения в БД
        response.customer_messages = new_customer_messages
        response.message_timestamps = new_timestamps
        response.turn = True
        response.last_message_by_customer = len(new_customer_messages)
        response.last_read_by_customer = len(worker_messages_list)

        # Отправляем или обновляем сообщение исполнителю
        await send_or_update_chat_message(
            user_id=worker.tg_id,
            user_type="worker",
            abs_id=abs_id,
            worker=worker,
            customer=customer,
            message_text=message.text,
            sender="customer"
        )

        # Перед отправкой нового статуса пытаемся удалить предыдущий, чтобы не копить уведомления
        await update_worker_or_customer_chat_status(message, data, state, worker=False)

    except Exception as e:
        logger.error(f"Error in handle_customer_chat_message: {e}")
        await message.answer("❌ Произошла ошибка при отправке сообщения")


@router.callback_query(lambda c: c.data.startswith('reply_in_worker_chat_'))
async def reply_in_worker_chat(callback: CallbackQuery, state: FSMContext):
    """Исполнитель начинает отвечать в чате"""
    try:
        # reply_in_worker_chat_{abs_id}
        parts = callback.data.split('_')
        abs_id = int(parts[4])  # parts[0]=reply, parts[1]=in, parts[2]=worker, parts[3]=chat, parts[4]=abs_id

        print(f"[WORKER_REPLY_CHAT] Worker {callback.from_user.id} wants to reply in chat for abs {abs_id}")
        logger.info(f"[WORKER_REPLY_CHAT] Worker wants to reply in chat")

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Получаем объявление и заказчика
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        # Проверяем, не закрыт ли чат (только если контакты куплены)
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            await callback.answer("❌ Чат закрыт - контакты переданы", show_alert=True)
            return

        # Переводим исполнителя в режим чата
        await state.update_data(current_chat_abs_id=abs_id, current_chat_customer_id=customer.id)
        await state.set_state(WorkStates.worker_anonymous_chat)

        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text=f"💬 <b>Чат с заказчиком</b>\n\n"
                 f"📋 Объявление: #{abs_id}\n"
                 f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                 f"Напишите сообщение заказчику:",
        )

        await callback.answer("💬 Напишите сообщение заказчику")

    except Exception as e:
        logger.error(f"Error in reply_in_worker_chat: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== 1. ПРОСМОТР ОТКЛИКОВ ИСПОЛНИТЕЛЯ ("Мои Отклики") ==========

@router.callback_query(F.data == "my_responses")
async def my_responses(callback: CallbackQuery, state: FSMContext):
    """Просмотр всех откликов исполнителя"""
    try:
        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Получаем все отклики исполнителя
        responses = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

        if not responses:
            kbc = KeyboardCollection()
            text = "📭 <b>У вас пока нет откликов</b>\n\n"
            text += "Откликайтесь на объявления, чтобы найти работу!"

            # Безопасное редактирование
            try:
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.menu_btn(),
                    parse_mode='HTML'
                )
            except Exception:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.menu_btn(),
                    parse_mode='HTML'
                )

            await state.set_state(WorkStates.worker_menu)
            return

        # Формируем список откликов
        responses_data = []
        for response in responses:
            # Проверяем статус контактов
            contact_exchange = await ContactExchange.get_by_worker_and_abs(
                worker.id, response.abs_id
            )

            active = not (contact_exchange and contact_exchange.contacts_purchased)

            # Получаем индикатор статуса
            status_indicator = await get_response_status_indicator(response, "worker")

            responses_data.append({
                'abs_id': response.abs_id,
                'active': active,
                'status_indicator': status_indicator
            })

        kbc = KeyboardCollection()
        text = f"📋 <b>Ваши Отклики ({len(responses_data)})</b>\n\n"
        text += "💬 - активный чат\n"
        text += "✅ - контакты получены"

        # Безопасное редактирование
        try:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.my_responses_list_buttons(responses_data),
                parse_mode='HTML'
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=text,
                reply_markup=kbc.my_responses_list_buttons(responses_data),
                parse_mode='HTML'
            )

        await state.set_state(WorkStates.worker_my_responses)

    except Exception as e:
        logger.error(f"Error in my_responses: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('view_my_response_'))
async def view_my_response(callback: CallbackQuery, state: FSMContext):
    """Просмотр конкретного отклика"""
    try:
        abs_id = int(callback.data.split('_')[3])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        advertisement = await Abs.get_one(id=abs_id)

        # Сбрасываем данные о покупке контактов (если были сохранены ранее)
        await state.update_data(
            buying_contacts_for_abs=False,
            target_worker_id=None,
            target_abs_id=None
        )

        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        # Получаем response для обновления счетчика прочитанных сообщений
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)

        # Получаем количество сообщений от заказчика
        customer_messages_list = []
        if response and response.customer_messages:
            customer_messages_list = [
                msg for msg in response.customer_messages
                if msg and msg.strip()
            ]

        # Обновляем счетчик прочитанных сообщений для исполнителя
        # Исполнитель видел все сообщения от заказчика
        if response:
            last_read_by_worker = len(customer_messages_list)
            if response.last_read_by_worker != last_read_by_worker:
                await response.update(last_read_by_worker=last_read_by_worker)

            # Обновляем счетчик последнего сообщения заказчика
            last_message_by_customer = len(customer_messages_list)
            if response.last_message_by_customer != last_message_by_customer:
                await response.update(last_message_by_customer=last_message_by_customer)

        # Получаем статус обмена контактами
        contact_exchange = await ContactExchange.get_by_worker_and_abs(
            worker.id, abs_id
        )

        # Определяем статусы
        has_contacts = contact_exchange and contact_exchange.contacts_purchased

        # Заказчик подтвердил передачу (contacts_sent=True), но исполнитель еще не купил
        customer_confirmed = contact_exchange and contact_exchange.contacts_sent and not contact_exchange.contacts_purchased

        # Исполнитель запросил контакты (запись существует), но заказчик еще не подтвердил
        waiting_confirmation = contact_exchange and not contact_exchange.contacts_sent and not contact_exchange.contacts_purchased

        # Парсим фотографии объявления
        import json
        photo_dict = {}
        try:
            if advertisement.photo_path:
                if isinstance(advertisement.photo_path, str):
                    photo_dict = json.loads(advertisement.photo_path)
                else:
                    photo_dict = advertisement.photo_path
            # Используем count_photo из модели, если есть, иначе считаем из словаря
            if hasattr(advertisement, 'count_photo') and advertisement.count_photo:
                count_photo = advertisement.count_photo
            else:
                count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
            logger.info(
                f"[VIEW_MY_RESPONSE] abs_id={abs_id}, count_photo={count_photo}, model_count_photo={getattr(advertisement, 'count_photo', None)}, photo_dict keys={list(photo_dict.keys()) if photo_dict else []}, photo_dict_len={len(photo_dict) if isinstance(photo_dict, dict) else 0}")
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing photo_path in view_my_response: {e}, photo_path={advertisement.photo_path}")
            photo_dict = {}
            # Используем count_photo из модели, если есть
            if hasattr(advertisement, 'count_photo') and advertisement.count_photo:
                count_photo = advertisement.count_photo
            else:
                count_photo = 0

        # Формируем текст
        text = f"📋 <b>Объявление #{abs_id}</b>\n\n"
        text += read_text_file(advertisement.text_path)

        # Показываем историю переписки
        customer = await Customer.get_customer(id=advertisement.customer_id)
        chat_history = await format_chat_history_for_display("worker", abs_id, worker, customer)

        if chat_history:
            # Проверяем длину текста перед добавлением истории
            temp_text = text + "📝 <b>История переписки:</b>\n\n" + chat_history

            # Если текст слишком длинный (больше 4000 символов), обрезаем историю
            if len(temp_text) > 4000:
                # Урезаем историю до тех пор, пока текст не влезет
                history_lines = chat_history.split('\n')
                remaining_chars = 4000 - len(text) - 100  # Оставляем запас
                truncated_history = ""
                for line in reversed(history_lines):
                    if line.strip():  # Пропускаем пустые строки
                        if len(truncated_history) + len(line) + 1 <= remaining_chars:
                            truncated_history = line + '\n' + truncated_history
                        else:
                            break

                if truncated_history:
                    text += "📝 <b>История переписки:</b>\n\n"
                    text += truncated_history
                    text += f"\n... (показаны последние сообщения)\n"
                else:
                    # Если даже одна строка не влезла, не показываем историю
                    text += "\n📝 История переписки слишком длинная для отображения.\n"
            else:
                text += "📝 <b>История переписки:</b>\n\n"
                text += chat_history

        if has_contacts:
            # Контакты уже куплены
            customer = await Customer.get_customer(id=advertisement.customer_id)
            text += f"✅ <b>Контакты получены:</b>\n\n {await parse_contacts_message(customer)}"

            text += "\n\n🔒 Чат закрыт"
        elif customer_confirmed:
            # Заказчик подтвердил, исполнитель может покупать
            text += "\n💰 <b>Заказчик подтвердил передачу контактов</b>\n\n"
            text += "Для получения контактов необходимо их купить."
        elif waiting_confirmation:
            # Ожидаем подтверждения от заказчика
            text += (
                "⏳ <b>Статус:</b> Ожидание подтверждения заказчика\n\n"
                "Вы запросили контакт заказчика.\n"
                "Вы запросили контакт заказчика.\n"
                "Заказчик должен подтвердить передачу контакта.\n"
                "После подтверждения вам будет предложено приобрести контакт."
            )
        else:
            # Можно запросить контакты
            text += "💬 <b>Чат активен</b>\n\n Вы можете написать сообщение заказчику или запросить контакт."

        kbc = KeyboardCollection()

        # Устанавливаем состояние анонимного чата
        await state.update_data(current_chat_abs_id=abs_id)
        await state.set_state(WorkStates.worker_anonymous_chat)

        # Показываем с фото если есть
        if count_photo > 0 and isinstance(photo_dict, dict) and len(photo_dict) > 0:
            try:
                from aiogram.types import FSInputFile, InputMediaPhoto

                # Берем первое фото (ключ '0' или минимальный числовой ключ)
                if '0' in photo_dict:
                    photo_path = photo_dict['0']
                else:
                    # Если нет ключа '0', ищем минимальный числовой ключ
                    numeric_keys = [k for k in photo_dict.keys() if str(k).isdigit()]
                    if numeric_keys:
                        first_key = min(numeric_keys, key=lambda x: int(str(x)))
                        photo_path = photo_dict[first_key]
                    else:
                        # Если нет числовых ключей, берем первый доступный
                        photo_path = list(photo_dict.values())[0]

                if not photo_path:
                    raise ValueError("Empty photo path")

                logger.info(
                    f"[VIEW_MY_RESPONSE] Trying to show photo, path={photo_path[:100] if len(str(photo_path)) > 100 else photo_path}")

                # Проверяем локальные файлы
                if 'https' not in str(photo_path):
                    if not os.path.exists(str(photo_path)):
                        logger.error(f"[VIEW_MY_RESPONSE] Photo file not found: {photo_path}")
                        raise FileNotFoundError(f"Photo file not found: {photo_path}")

                try:
                    await callback.message.delete()
                except:
                    pass

                if 'https' in str(photo_path):
                    await callback.message.answer_photo(
                        photo=str(photo_path),
                        caption=text,
                        reply_markup=kbc.anonymous_chat_worker_buttons(
                            abs_id=abs_id,
                            has_contacts=has_contacts,
                            contacts_requested=customer_confirmed,
                            contacts_sent=waiting_confirmation,
                            worker_initiated=waiting_confirmation,  # True если исполнитель запросил
                            count_photo=count_photo,
                            photo_num=0
                        ),
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.answer_photo(
                        photo=FSInputFile(str(photo_path)),
                        caption=text,
                        reply_markup=kbc.anonymous_chat_worker_buttons(
                            abs_id=abs_id,
                            has_contacts=has_contacts,
                            contacts_requested=customer_confirmed,
                            contacts_sent=waiting_confirmation,
                            worker_initiated=waiting_confirmation,  # True если исполнитель запросил
                            count_photo=count_photo,
                            photo_num=0
                        ),
                        parse_mode='HTML'
                    )
                logger.info(f"[VIEW_MY_RESPONSE] Photo sent successfully for abs_id={abs_id}")
            except Exception as e:
                logger.error(f"[VIEW_MY_RESPONSE] Error showing photo for abs_id={abs_id}: {e}", exc_info=True)
                # Если фото не загрузилось, показываем текстом с безопасным редактированием
                from app.untils.message_utils import safe_edit_message
                await safe_edit_message(
                    callback=callback,
                    text=text,
                    reply_markup=kbc.anonymous_chat_worker_buttons(
                        abs_id=abs_id,
                        has_contacts=has_contacts,
                        contacts_requested=customer_confirmed,
                        contacts_sent=waiting_confirmation,
                        count_photo=count_photo,
                        photo_num=0
                    ),
                )
        else:
            # Нет фото или ошибка парсинга
            logger.warning(
                f"[VIEW_MY_RESPONSE] No photo to show: abs_id={abs_id}, count_photo={count_photo}, photo_dict={photo_dict}")
            # Используем безопасное редактирование сообщения
            from app.untils.message_utils import safe_edit_message
            await safe_edit_message(
                callback=callback,
                text=text,
                reply_markup=kbc.anonymous_chat_worker_buttons(
                    abs_id=abs_id,
                    has_contacts=has_contacts,
                    contacts_requested=customer_confirmed,
                    contacts_sent=waiting_confirmation,
                    count_photo=count_photo,
                    photo_num=0
                ),
            )

    except Exception as e:
        logger.error(f"Error in view_my_response: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('cancel_worker_response_'))
async def cancel_worker_response_confirm(callback: CallbackQuery, state: FSMContext):
    """Показывает подтверждение отмены отклика с предупреждением о -13 активности"""
    try:
        abs_id = int(callback.data.split('_')[3])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Проверяем, что отклик существует
        from app.data.database.models import WorkersAndAbs
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return

        # Проверяем, что контакты еще не куплены
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            await callback.answer("❌ Нельзя отменить отклик после покупки контактов", show_alert=True)
            return

        # Показываем подтверждение с предупреждением
        current_activity = getattr(worker, 'activity_level', 100)
        new_activity = max(0, current_activity - 13)

        # Определяем зону активности
        if new_activity >= 74:
            zone_emoji = "🟢"
            zone_name = "зеленой"
        elif new_activity >= 48:
            zone_emoji = "🟡"
            zone_name = "желтой"
        elif new_activity >= 9:
            zone_emoji = "🟠"
            zone_name = "оранжевой"
        else:
            zone_emoji = "🔴"
            zone_name = "красной"

        confirmation_text = (
            f"⚠️ <b>Подтверждение отмены отклика</b>\n\n"
            f"Вы действительно хотите отменить отклик на объявление #{abs_id}?\n\n"
            "<b>Последствия:</b>\n"
            f"❌ Активность снизится: {current_activity} → {new_activity} (-13)\n"
            f"{zone_emoji} Вы перейдете в {zone_name} зону активности\n\n"
        )

        if new_activity < 74:
            confirmation_text += f"⚠️ <b>Внимание!</b> При снижении активности могут быть ограничения на отклики.\n\n"

        confirmation_text += f"Нажмите «Подтвердить», если согласны с последствиями."

        # Создаем клавиатуру подтверждения
        from app.keyboards import KeyboardCollection
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kbc = KeyboardCollection()
        builder = InlineKeyboardBuilder()

        builder.add(kbc._inline("✅ Подтвердить", f"confirm_cancel_response_{abs_id}"))
        builder.add(kbc._inline("❌ Отмена", f"view_my_response_{abs_id}"))
        builder.adjust(1)

        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text=confirmation_text,
            reply_markup=builder.as_markup(),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in cancel_worker_response_confirm: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_cancel_response_'))
async def confirm_cancel_worker_response(callback: CallbackQuery, state: FSMContext):
    """Подтвержденная отмена отклика исполнителем с снижением активности на -13"""
    try:
        abs_id = int(callback.data.split('_')[3])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Проверяем, что отклик существует
        from app.data.database.models import WorkersAndAbs
        response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return

        # Проверяем, что контакты еще не куплены
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange and contact_exchange.contacts_purchased:
            await callback.answer("❌ Нельзя отменить отклик после покупки контактов", show_alert=True)
            return

        # Удаляем отклик
        await response.delete()

        # Удаляем связанные записи
        if contact_exchange:
            await contact_exchange.delete()

        # Записываем отмену в таблицу отслеживания
        from app.data.database.models import WorkerResponseCancellation
        cancellation = WorkerResponseCancellation(
            worker_id=worker.id,
            abs_id=abs_id
        )
        await cancellation.save()

        # Снижаем активность на -13
        if not hasattr(worker, 'activity_level') or worker.activity_level is None:
            worker.activity_level = 100

        old_activity = worker.activity_level
        new_activity = max(0, min(100, worker.activity_level - 13))

        # Обновляем активность с fallback
        from app.handlers.worker import update_worker_activity_fallback
        await update_worker_activity_fallback(worker, new_activity)

        # Получаем информацию о зоне активности
        if new_activity >= 74:
            zone_emoji = "🟢"
        elif new_activity >= 48:
            zone_emoji = "🟡"
        elif new_activity >= 9:
            zone_emoji = "🟠"
        else:
            zone_emoji = "🔴"

        # Отправляем уведомление исполнителю
        from loaders import bot
        notification_text = (
            f"Отмена отклика:\n\n—13 активность\n\n"
            f"{zone_emoji} Текущая активность: {new_activity}\n\n"
            "Вы вернулись к списку откликов"
        )

        await callback.answer(notification_text, show_alert=True)
        kbc = KeyboardCollection()

        # Отправляем уведомление заказчику
        from app.data.database.models import Abs, Customer
        advertisement = await Abs.get_one(id=abs_id)
        if advertisement:
            customer = await Customer.get_customer(id=advertisement.customer_id)
            if customer:
                ad_text = read_text_file(advertisement.text_path) or ""
                MAX_AD_TEXT_LENGTH = 1500
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

                notification_to_customer = (
                    f"📨 Исполнитель отменил отклик на объявление #{abs_id}\n\n"
                )
                if ad_text:
                    notification_to_customer += f"📝 <b>Текст объявления:</b>\n{ad_text}"

                try:
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=notification_to_customer,
                        reply_markup=kbc.menu_btn(),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error sending cancellation notification to customer {customer.tg_id}: {e}")

        # Возвращаемся к списку откликов

        from app.untils.message_utils import safe_edit_message
        responses = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

        if responses:
            responses_data = []
            for resp in responses:
                # Пропускаем текущий отклик (он уже удален, но на всякий случай)
                contact_exchange_resp = await ContactExchange.get_by_worker_and_abs(worker.id, resp.abs_id)
                status_indicator = await get_response_status_indicator(resp, "worker")
                responses_data.append({
                    'abs_id': resp.abs_id,
                    'active': not (contact_exchange_resp and contact_exchange_resp.contacts_purchased),
                    'status_indicator': status_indicator
                })

            text = (
                f"📋 <b>Ваши Отклики ({len(responses_data)})</b>\n\n"
                "💬 — Активный чат\n"
                "✅ — Контакты получены"
            )

            await safe_edit_message(
                callback=callback,
                text=text,
                reply_markup=kbc.my_responses_list_buttons(responses_data)
            )
            await state.set_state(WorkStates.worker_my_responses)
        else:
            text = "📭 <b>У вас пока нет откликов</b>\n\nОткликайтесь на объявления, чтобы найти работу!"
            await safe_edit_message(
                callback=callback,
                text=text,
                reply_markup=kbc.menu_btn()
            )
            await state.set_state(WorkStates.worker_menu)

    except Exception as e:
        logger.error(f"Error in cancel_worker_response: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== 2. АНОНИМНЫЙ ЧАТ - СООБЩЕНИЯ ОТ ИСПОЛНИТЕЛЯ ==========

@router.message(F.text, StateFilter(WorkStates.worker_anonymous_chat))
async def worker_chat_message(message: Message, state: FSMContext):
    """Обработка сообщения от исполнителя в анонимном чате"""
    try:
        # Проверяем сообщение на контакты
        is_valid, _ = check_message_for_contacts(message.text)

        if not is_valid:
            kbc = KeyboardCollection()
            await message.answer(
                text="🚫 <b>Сообщение заблокировано!</b>\n\n"
                     "Используйте кнопку «Предложить контакты» для передачи контактов исполнителю.",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
            return

        # Проверяем на запрещенный контент (ссылки, упоминания, номера прописью)
        if is_content_forbidden(message.text):
            kbc = KeyboardCollection()
            await message.answer(
                text=f"🚫 <b>Сообщение заблокировано!</b>\n\nЗапрещённый контент или контактные данные. Исправьте и отправьте снова.",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
            return

        # Проверяем на стоп-слова (для сообщений в чате)
        if ban_reason := await fool_check(message.text, is_message=True):
            kbc = KeyboardCollection()
            await message.answer(
                text=f"🚫 <b>Сообщение заблокировано!</b>\n\nПричина: {ban_reason}",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
            return

        # Проверка длины
        if len(message.text) > 500:
            await message.answer(
                text="❌ Сообщение слишком длинное. Максимум 500 символов."
            )
            return

        data = await state.get_data()
        abs_id = data.get('current_chat_abs_id')

        if not abs_id:
            await message.answer("❌ Сессия чата истекла. Вернитесь к откликам.")
            return

        worker = await Worker.get_worker(tg_id=message.from_user.id)
        advertisement = await Abs.get_one(id=abs_id)
        customer = await Customer.get_customer(id=advertisement.customer_id)

        # Сохраняем сообщение в историю
        worker_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
        for response in worker_and_abs:
            if response.worker_id == worker.id:
                # Обновляем историю сообщений
                if isinstance(response.worker_messages, str):
                    messages = response.worker_messages.split(" | ") if response.worker_messages else []
                else:
                    messages = response.worker_messages or []

                messages.append(message.text)

                # Добавляем временную метку
                current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_timestamps = response.message_timestamps if hasattr(response,
                                                                            'message_timestamps') and response.message_timestamps else []
                new_timestamps = current_timestamps + [{"sender": "worker", "timestamp": current_timestamp}]

                await response.update(
                    worker_messages=messages,
                    message_timestamps=new_timestamps
                )

                # Обновляем объект в памяти после сохранения в БД
                response.worker_messages = messages
                response.message_timestamps = new_timestamps

                break

        # Отправляем заказчику с полным профилем исполнителя
        notification_text = (
            f"💬 <b>Новое сообщение от исполнителя</b>\n\n"
            f"📋 Объявление: #{abs_id}\n\n"
        )

        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 <b>ID:</b> {worker.id} {worker_name}\n"

        # Рейтинг
        if worker.count_ratings > 0:
            notification_text += f"⭐ <b>Рейтинг:</b> {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            notification_text += f"⭐ <b>Рейтинг:</b> Нет оценок\n"

        # Статус верификации и регистрации (всегда показываем)
        status_string = await get_worker_status_string(worker.id)
        notification_text += f"📋 <b>Статус:</b> {status_string}\n"

        # Выполнено заказов
        notification_text += f"📦 <b>Выполнено заказов:</b> {worker.order_count}\n"

        # Дата регистрации
        notification_text += f"📅 <b>Зарегистрирован:</b> {worker.registration_data}\n\n"

        notification_text += f"💬 <b>Сообщение:</b>\n{message.text}"

        # Отправляем с фото или без
        if worker.profile_photo:
            try:
                from aiogram.types import FSInputFile
                await bot.send_photo(
                    chat_id=customer.tg_id,
                    photo=FSInputFile(worker.profile_photo),
                    caption=notification_text,
                    parse_mode='HTML'
                )
            except Exception:
                # Если фото не загрузилось, отправляем текстом
                await bot.send_message(
                    chat_id=customer.tg_id,
                    text=notification_text,
                    parse_mode='HTML'
                )
        else:
            await bot.send_message(
                chat_id=customer.tg_id,
                text=notification_text,
                parse_mode='HTML'
            )

        # Перед отправкой нового статуса пытаемся удалить предыдущий, чтобы не копить уведомления
        await update_worker_or_customer_chat_status(message, data, state, worker=True)

    except Exception as e:
        logger.error(f"Error in worker_chat_message: {e}")
        await message.answer("❌ Произошла ошибка при отправке сообщения")


# ========== 3. ЗАПРОС КОНТАКТА ОТ ИСПОЛНИТЕЛЯ ==========

@router.callback_query(lambda c: c.data.startswith('request_contact_'))
async def request_contact(callback: CallbackQuery, state: FSMContext):
    """Исполнитель запрашивает контакт заказчика"""
    try:
        abs_id = int(callback.data.split('_')[2])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        advertisement = await Abs.get_one(id=abs_id)
        customer = await Customer.get_customer(id=advertisement.customer_id)

        # Создаем или обновляем запись в ContactExchange
        # contacts_sent=False означает, что заказчик еще не подтвердил
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if not contact_exchange:
            contact_exchange = ContactExchange(
                id=None,
                worker_id=worker.id,
                customer_id=customer.id,
                abs_id=abs_id,
                contacts_sent=False,  # Заказчик еще не подтвердил
                contacts_purchased=False,
                message_id=None
            )
            await contact_exchange.save()
        else:
            # Если запись уже есть, но заказчик отклонил - сбрасываем
            await contact_exchange.update(contacts_sent=False, contacts_purchased=False)

        # Уведомляем заказчика с полным профилем исполнителя
        notification_text = f"📞 <b>Запрос контакта от исполнителя</b>\n\n"
        notification_text += f"📋 Объявление: #{abs_id}\n\n"

        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 <b>ID:</b> {worker.id} {worker_name}\n"

        # Рейтинг
        if worker.count_ratings > 0:
            notification_text += f"⭐ <b>Рейтинг:</b> {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            notification_text += f"⭐ <b>Рейтинг:</b> Нет оценок\n"

        # Статус верификации и регистрации (всегда показываем)
        status_string = await get_worker_status_string(worker.id)
        notification_text += f"📋 <b>Статус:</b> {status_string}\n"

        # Выполнено заказов
        notification_text += f"📦 <b>Выполнено заказов:</b> {worker.order_count}\n"

        # Дата регистрации
        notification_text += f"📅 <b>Зарегистрирован:</b> {worker.registration_data}\n\n"

        notification_text += "❓ <b>Подтвердить передачу контакта?</b>"

        kbc = KeyboardCollection()

        # Отправляем с фото или без
        if worker.profile_photo:
            try:
                from aiogram.types import FSInputFile
                await bot.send_photo(
                    chat_id=customer.tg_id,
                    photo=FSInputFile(worker.profile_photo),
                    caption=notification_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker.id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=False,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
            except Exception:
                # Если фото не загрузилось, отправляем текстом
                await bot.send_message(
                    chat_id=customer.tg_id,
                    text=notification_text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker.id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=False,
                        contacts_purchased=False
                    ),
                    parse_mode='HTML'
                )
        else:
            await bot.send_message(
                chat_id=customer.tg_id,
                text=notification_text,
                reply_markup=kbc.anonymous_chat_customer_buttons(
                    worker_id=worker.id,
                    abs_id=abs_id,
                    contact_requested=True,
                    contact_sent=False,
                    contacts_purchased=False
                ),
                parse_mode='HTML'
            )

        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text="📞 <b>Запрос отправлен заказчику</b>\n\n"
                 "⏳ Ожидайте подтверждения.\n"
                 "Вы получите уведомление, когда заказчик ответит.",
            reply_markup=kbc.anonymous_chat_worker_buttons(
                abs_id=abs_id,
                contacts_requested=False,  # Исполнитель запросил, ждет подтверждения
                contacts_sent=True,  # Исполнитель запросил
                worker_initiated=True  # Исполнитель сам запросил
            ),
        )

    except Exception as e:
        logger.error(f"Error in request_contact: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== 4. ПОДТВЕРЖДЕНИЕ ПЕРЕДАЧИ КОНТАКТА ЗАКАЗЧИКОМ ==========
# ========== 5. ПОКУПКА ЖЕТОНОВ (МОНЕТИЗАЦИЯ) ==========

@router.callback_query(lambda c: c.data.startswith('buy_tokens_'))
async def buy_tokens(callback: CallbackQuery, state: FSMContext):
    """Выбор тарифа для покупки жетонов"""
    try:
        parts = callback.data.split('_')

        # Парсим тариф: buy_tokens_{tariff_id}
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат тарифа", show_alert=True)
            return

        tariff_id = int(parts[2])

        # Получаем тариф из БД
        from app.data.database.models import ContactTariff
        tariff = await ContactTariff.get_by_id(tariff_id)

        if not tariff:
            await callback.answer("❌ Тариф не найден", show_alert=True)
            return

        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        price_rub = tariff.price / 100

        # Формируем информацию о тарифе
        if tariff.unlimited:
            tokens = -1
            tariff_name = tariff.name
            info_text = 'Безлимитный доступ к контактам'
        else:
            tokens = tariff.contacts_count
            tariff_name = tariff.name
            all_contacts = worker.purchased_contacts + tokens
            contact_word = f"{all_contacts} {get_contact_word(all_contacts)}"
            info_text = f'После покупки у вас будет {contact_word}'

        # Сохраняем выбор в state
        await state.update_data(
            purchase_tokens=tokens,
            purchase_price=int(price_rub),
            purchase_tariff=tariff_name,
            purchase_tariff_id=tariff_id
        )
        await state.set_state(WorkStates.worker_buy_tokens)

        confirmation_text = f"""
💰 <b>Подтверждение покупки</b>

📦 Тариф: {tariff_name}
💵 Цена: {int(price_rub)}₽

{info_text}

Подтвердить покупку?
        """

        kbc = KeyboardCollection()
        # Здесь должна быть интеграция с платежной системой
        # Пока заглушка
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        keyboard_builder = InlineKeyboardBuilder()
        keyboard_builder.add(kbc._inline(
            button_text=f"✅ Оплатить {int(price_rub)}₽",
            callback_data=f"confirm_token_purchase_{tariff_id}"
        ))

        state_data = await state.get_data()
        buying_for_abs = state_data.get('buying_contacts_for_abs')
        target_abs_id = state_data.get('target_abs_id')
        if buying_for_abs and target_abs_id:
            keyboard_builder.add(kbc._inline(
                button_text="⏪ Назад",
                callback_data=f"view_my_response_{target_abs_id}"
            ))
        else:
            keyboard_builder.add(kbc._inline(
                button_text="◀️ Отмена",
                callback_data="cancel_token_purchase"
            ))
        keyboard_builder.adjust(1)

        try:
            await callback.message.answer(
                text=confirmation_text,
                reply_markup=keyboard_builder.as_markup(),
                parse_mode='HTML'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text=confirmation_text,
                reply_markup=keyboard_builder.as_markup(),
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Error in buy_tokens: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_token_purchase_'))
async def confirm_token_purchase(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и обработка покупки жетонов"""
    try:
        parts = callback.data.split('_')
        tariff_id = int(parts[3])

        # Получаем тариф из БД
        from app.data.database.models import ContactTariff
        tariff = await ContactTariff.get_by_id(tariff_id)

        if not tariff:
            await callback.answer("❌ Тариф не найден", show_alert=True)
            return

        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        # Проверяем, покупаем ли контакты для конкретного объявления
        data = await state.get_data()
        buying_for_abs = data.get('buying_contacts_for_abs', False)

        # ВАЖНО: Здесь должна быть интеграция с платежной системой
        # Сейчас - заглушка для демонстрации атомарности

        # Атомарное списание и обновление
        import aiosqlite
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            unlimited_until = None
            price_rub_value = int(tariff.price / 100)

            if tariff.unlimited:
                # Безлимит
                until_date = (datetime.now() + timedelta(days=tariff.unlimited_days)).strftime('%Y-%m-%d')

                await conn.execute(
                    'UPDATE workers SET unlimited_contacts_until = ? WHERE id = ?',
                    (until_date, worker.id)
                )
                tokens = -1
                unlimited_until = until_date
            else:
                # Обычные жетоны
                await conn.execute(
                    'UPDATE workers SET purchased_contacts = purchased_contacts + ? WHERE id = ?',
                    (tariff.contacts_count, worker.id)
                )
                tokens = tariff.contacts_count

            await conn.commit()

            await ContactTransaction.log_purchase(
                worker_id=worker.id,
                contacts_count=tariff.contacts_count if not tariff.unlimited else 0,
                tariff_name=tariff.name,
                price_rub=price_rub_value,
                tariff_id=tariff_id,
                unlimited=tariff.unlimited,
                unlimited_until=unlimited_until,
                unlimited_days=tariff.unlimited_days
            )

            kbc = KeyboardCollection()

            if buying_for_abs:
                # Покупаем контакты для конкретного объявления
                target_worker_id = data.get('target_worker_id')
                target_abs_id = data.get('target_abs_id')

                # Получаем обновленные данные исполнителя
                worker = await Worker.get_worker(id=target_worker_id)

                # Получаем заказчика из объявления
                advertisement = await Abs.get_one(id=target_abs_id)
                if not advertisement:
                    await callback.answer("❌ Объявление не найдено", show_alert=True)
                    return

                # Получаем текст объявления
                ad_text = ""
                if advertisement and advertisement.text_path:
                    ad_text = read_text_file(advertisement.text_path) or ""
                    # Ограничиваем длину текста объявления
                    MAX_AD_TEXT_LENGTH = 1500
                    if len(ad_text) > MAX_AD_TEXT_LENGTH:
                        ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

                customer = await Customer.get_customer(id=advertisement.customer_id)

                if worker and customer:
                    # Списываем один контакт
                    if tokens != -1:
                        new_count = worker.purchased_contacts - 1
                        await worker.update_purchased_contacts(purchased_contacts=new_count)

                    # Обновляем ContactExchange
                    contact_exchange = await ContactExchange.get_by_worker_and_abs(target_worker_id, target_abs_id)
                    if contact_exchange:
                        await contact_exchange.update(contacts_purchased=True)

                    usage_source = "unlimited" if tokens == -1 else "purchased"
                    await ContactTransaction.log_usage(worker_id=worker.id, abs_id=target_abs_id, source=usage_source)

                    # Передаем контакты исполнителю с учетом нового функционала
                    contacts_text = f"📞 <b>Контакты заказчика:</b>\n\n {await parse_contacts_message(customer)}"

                    await send_contacts_to_worker(worker, customer, target_abs_id, ad_text, contacts_text)

                    # # Формируем текст сообщения с объявлением
                    # message_text = f"🎉 <b>Контакты получены!</b>\n\n📋 Объявление: #{target_abs_id}\n👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                    # if ad_text:
                    #     message_text += f"📝 <b>Текст объявления:</b>\n{ad_text}"
                    # message_text += contacts_text
                    #
                    # worker_keyboard = InlineKeyboardBuilder()
                    # worker_keyboard.add(kbc._inline(
                    #     button_text="⏪ Перейти к отклику",
                    #     callback_data=f"view_my_response_{target_abs_id}"
                    # ))
                    # worker_keyboard.add(kbc._inline(
                    #     button_text="🏠 В меню",
                    #     callback_data="worker_menu"
                    # ))
                    # worker_keyboard.adjust(1)
                    #
                    # await bot.send_message(
                    #     chat_id=worker.tg_id,
                    #     text=message_text,
                    #     parse_mode='HTML',
                    #     reply_markup=worker_keyboard.as_markup()
                    # )

                    # Формируем текст сообщения с объявлением
                    await send_notification_to_customer(customer, worker, target_abs_id, ad_text)
                    # notification_text = f"✅ <b>Контакты переданы исполнителю!</b>\n\n📋 Объявление: #{target_abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
                    # if ad_text:
                    #     notification_text += f"📝 <b>Текст объявления:</b>\n{ad_text}\n\n"
                    # notification_text += "💬 Чат закрыт - теперь общайтесь напрямую."
                    #
                    # customer_keyboard = InlineKeyboardBuilder()
                    # customer_keyboard.add(kbc._inline(
                    #     button_text="⏪ Перейти к отклику",
                    #     callback_data=f"view_response_{worker.id}_{target_abs_id}"
                    # ))
                    # customer_keyboard.add(kbc._inline(
                    #     button_text="🏠 В меню",
                    #     callback_data="customer_menu"
                    # ))
                    # customer_keyboard.adjust(1)
                    #
                    # kbc = KeyboardCollection()
                    # await bot.send_message(
                    #     chat_id=customer.tg_id,
                    #     text=notification_text,
                    #     parse_mode='HTML',
                    #     reply_markup=customer_keyboard.as_markup()
                    # )

                    # Закрываем чат
                    response = await WorkersAndAbs.get_by_worker_and_abs(target_worker_id, target_abs_id)
                    if response:
                        await response.update(applyed=False)
                else:
                    try:
                        await callback.message.answer(
                            text=f"✅ <b>Покупка успешна!</b>\n\n"
                                 f"{'Безлимит активирован!' if tokens == -1 else
                                 f'Добавлено {tokens} {get_contact_word(tokens)}'}",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='HTML'
                        )
                    except TelegramBadRequest:
                        # Если сообщение недоступно для редактирования, отправляем новое
                        await callback.message.answer(
                            text=f"✅ <b>Покупка успешна!</b>\n\n"
                                 f"{'Безлимит активирован!' if tokens == -1 else
                                 f'Добавлено {tokens} {get_contact_word(tokens)}'}",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='HTML'
                        )
            else:
                # Обычная покупка токенов
                try:
                    await callback.message.answer(
                        text=f"✅ <b>Покупка успешна!</b>\n\n"
                             f"{'Безлимит активирован!' if tokens == -1 else
                             f'Добавлено {tokens} {get_contact_word(tokens)}'}",
                        reply_markup=kbc.menu_btn(),
                        parse_mode='HTML'
                    )
                except TelegramBadRequest:
                    # Если сообщение недоступно для редактирования, отправляем новое
                    await callback.message.answer(
                        text=f"✅ <b>Покупка успешна!</b>\n\n"
                             f"{'Безлимит активирован!' if tokens == -1 else
                             f'Добавлено {tokens} {get_contact_word(tokens)}'}",
                        reply_markup=kbc.menu_btn(),
                        parse_mode='HTML'
                    )

            # Устанавливаем правильное состояние вместо clear()
            await state.set_state(WorkStates.worker_menu)

        except Exception as e:
            await conn.rollback()
            logger.error(f"Error in atomic purchase: {e}")
            await callback.answer("❌ Ошибка при обработке платежа", show_alert=True)
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error in confirm_token_purchase: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_token_purchase")
async def cancel_token_purchase(callback: CallbackQuery, state: FSMContext):
    """Отмена покупки жетонов"""
    kbc = KeyboardCollection()
    try:
        await callback.message.answer(
            text="❌ Покупка отменена",
            reply_markup=kbc.menu_btn()
        )
    except TelegramBadRequest:
        # Если сообщение недоступно для редактирования, отправляем новое
        await callback.message.answer(
            text="❌ Покупка отменена",
            reply_markup=kbc.menu_btn()
        )
    await state.set_state(WorkStates.worker_menu)


# ========== 6. ОТМЕНА ЗАПРОСА КОНТАКТА ==========

@router.callback_query(lambda c: c.data.startswith('cancel_contact_request_'))
async def cancel_contact_request(callback: CallbackQuery):
    """Отмена запроса контакта"""
    try:
        abs_id = int(callback.data.split('_')[3])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        # Получаем объявление и заказчика
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return

        customer = await Customer.get_customer(id=advertisement.customer_id)

        # Удаляем запись ContactExchange
        contact_exchange = await ContactExchange.get_by_worker_and_abs(
            worker.id, abs_id
        )

        if contact_exchange:
            await contact_exchange.delete()

        # Уведомляем заказчика об отмене запроса
        notification_text = (
            f"ℹ️ <b>Исполнитель отменил запрос контакта</b>\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
            f"Запрос на передачу контакта отменен."
        )

        await bot.send_message(
            chat_id=customer.tg_id,
            text=notification_text,
            parse_mode='HTML'
        )

        # Обновляем сообщение исполнителя
        kbc = KeyboardCollection()
        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text="❌ <b>Запрос контакта отменен</b>\n\nВы можете запросить контакт позже.",
            reply_markup=kbc.anonymous_chat_worker_buttons(abs_id=abs_id),
        )

        await callback.answer("❌ Запрос контакта отменен")

    except Exception as e:
        logger.error(f"Error in cancel_contact_request: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# Заглушка для неактивных кнопок
@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Обработчик для неактивных кнопок"""
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith('go-to-photo-worker-response_'))
async def navigate_photo_worker_response(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик листания фотографий в откликах для исполнителей"""
    logger.debug(f'navigate_photo_worker_response...')
    kbc = KeyboardCollection()

    # Парсим данные: go-to-photo-worker-response_{photo_num}_{abs_id}
    parts = callback.data.split('_')
    photo_num = int(parts[1])
    abs_id = int(parts[2])

    # Получаем объявление
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Парсим JSON строку photo_path для получения количества фото
    import json
    photo_dict = {}
    try:
        if advertisement.photo_path:
            if isinstance(advertisement.photo_path, str):
                photo_dict = json.loads(advertisement.photo_path)
            else:
                photo_dict = advertisement.photo_path
        count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        logger.error(
            f"Error parsing photo_path in navigate_photo_worker_response: {e}, photo_path={advertisement.photo_path}")
        photo_dict = {}
        count_photo = 0

    # Проверяем что есть фото для навигации
    if count_photo == 0 or not isinstance(photo_dict, dict) or len(photo_dict) == 0:
        await callback.answer("❌ Фотографии не найдены", show_alert=True)
        return

    # Циклическая навигация
    if photo_num <= -1:
        photo_num = count_photo - 1
    elif photo_num >= count_photo:
        photo_num = 0

    # Получаем путь к фото из словаря (нормализуем ключ к строке)
    photo_key = str(photo_num)
    if photo_key not in photo_dict:
        # Пробуем найти ближайший ключ
        all_keys = [str(k) for k in photo_dict.keys()]
        numeric_keys = [k for k in all_keys if k.isdigit()]
        if numeric_keys:
            # Берем ближайший числовой ключ
            try:
                photo_key = min(numeric_keys, key=lambda x: abs(int(x) - photo_num))
            except:
                photo_key = numeric_keys[0]
        else:
            # Если нет числовых ключей, берем первый
            photo_key = all_keys[0]

    photo_path = photo_dict[photo_key]

    if not photo_path:
        await callback.answer("❌ Фотография не найдена", show_alert=True)
        return

    # Получаем данные для кнопок
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    if not worker:
        await callback.answer("Ошибка получения данных", show_alert=True)
        return

    # Получаем статус обмена контактами
    contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)

    # Определяем статусы
    has_contacts = contact_exchange and contact_exchange.contacts_purchased
    customer_confirmed = contact_exchange and contact_exchange.contacts_sent and not contact_exchange.contacts_purchased
    waiting_confirmation = contact_exchange and not contact_exchange.contacts_sent and not contact_exchange.contacts_purchased

    # Формируем текст (используем тот же текст что и в view_my_response)
    text = f"📋 <b>Объявление #{abs_id}</b>\n\n"
    text += read_text_file(advertisement.text_path)

    if has_contacts:
        # Контакты уже куплены
        customer = await Customer.get_customer(id=advertisement.customer_id)
        text += f"✅ <b>Контакты получены:</b>\n\n {await parse_contacts_message(customer)}"

        text += "\n\n🔒 Чат закрыт"
    elif customer_confirmed:
        # Заказчик подтвердил, исполнитель может покупать
        text += "\n💰 <b>Заказчик подтвердил передачу контактов</b>\n\n"
        text += "Для получения контактов необходимо их купить."
    elif waiting_confirmation:
        # Ожидаем подтверждения от заказчика
        text += "⏳ <b>Статус:</b> Ожидание подтверждения заказчика\n\n"
        text += "Вы запросили контакт заказчика.\n"
        text += "Заказчик должен подтвердить передачу контакта.\n"
        text += "После подтверждения вам будет предложено приобрести контакт."
    else:
        # Можно запросить контакты
        text += "💬 <b>Чат активен</b>\n\n"
        text += "Вы можете написать сообщение заказчику или запросить контакт."

    # Обновляем медиа
    try:
        # Проверяем локальные файлы
        if 'https' not in str(photo_path):
            if not os.path.exists(str(photo_path)):
                logger.error(f"[NAVIGATE_PHOTO] Photo file not found: {photo_path}")
                await callback.answer("❌ Файл не найден", show_alert=True)
                return

        # Пытаемся отредактировать медиа
        try:
            if 'https' in str(photo_path):
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=str(photo_path),
                        caption=text
                    ),
                    reply_markup=kbc.anonymous_chat_worker_buttons(
                        abs_id=abs_id,
                        has_contacts=has_contacts,
                        contacts_requested=customer_confirmed,
                        contacts_sent=waiting_confirmation,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
            else:
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=FSInputFile(str(photo_path)),
                        caption=text),
                    reply_markup=kbc.anonymous_chat_worker_buttons(
                        abs_id=abs_id,
                        has_contacts=has_contacts,
                        contacts_requested=customer_confirmed,
                        contacts_sent=waiting_confirmation,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
        except TelegramBadRequest as e:
            # Если не удалось отредактировать (сообщение не найдено или недоступно), отправляем новое
            logger.warning(f"[NAVIGATE_PHOTO] Cannot edit message, sending new: {e}")
            try:
                await callback.message.delete()
            except:
                pass

            if 'https' in str(photo_path):
                await callback.message.answer_photo(
                    photo=str(photo_path),
                    caption=text,
                    reply_markup=kbc.anonymous_chat_worker_buttons(
                        abs_id=abs_id,
                        has_contacts=has_contacts,
                        contacts_requested=customer_confirmed,
                        contacts_sent=waiting_confirmation,
                        count_photo=count_photo,
                        photo_num=photo_num
                    ),
                    parse_mode='HTML'
                )
            else:
                await callback.message.answer_photo(
                    photo=FSInputFile(str(photo_path)),
                    caption=text,
                    reply_markup=kbc.anonymous_chat_worker_buttons(
                        abs_id=abs_id,
                        has_contacts=has_contacts,
                        contacts_requested=customer_confirmed,
                        contacts_sent=waiting_confirmation,
                        count_photo=count_photo,
                        photo_num=photo_num
                    ),
                    parse_mode='HTML'
                )
    except Exception as e:
        logger.error(f"[NAVIGATE_PHOTO] Error updating photo in navigate_photo_worker_response: {e}", exc_info=True)
        await callback.answer("❌ Ошибка обновления фото", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('contacts_history_'))
async def show_contact_transactions_history(callback: CallbackQuery, state: FSMContext):
    """Показывает историю покупок и списаний контактов исполнителя."""
    try:
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        parts = callback.data.split('_')
        context = parts[2] if len(parts) > 2 else "general"
        target_abs_id = None
        if context == "abs" and len(parts) > 3:
            try:
                target_abs_id = int(parts[3])
            except ValueError:
                target_abs_id = None

        history_text = await format_contact_transactions_history(worker.id)

        kbc = KeyboardCollection()
        await callback.message.answer(
            text=history_text,
            reply_markup=kbc.contact_history_keyboard(target_abs_id),
            parse_mode='HTML'
        )
        await callback.answer()
    except Exception as error:
        logger.error(f"Error in show_contact_transactions_history: {error}")
        await callback.answer("❌ Не удалось показать историю", show_alert=True)
