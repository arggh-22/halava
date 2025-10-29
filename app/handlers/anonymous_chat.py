"""
Handlers для анонимного чата между исполнителем и заказчиком
- Обмен сообщениями
- Запрос контактов
- Подтверждение передачи контактов
- Покупка контактов (монетизация)
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest

from app.states import WorkStates, CustomerStates
from app.keyboards import KeyboardCollection
from app.data.database.models import (
    Worker, Customer, Abs, WorkersAndAbs,
    ContactExchange, ContactTariff
)
from loaders import bot
from app.untils.contact_filter import check_message_for_contacts
from app.untils.checks import fool_check

logger = logging.getLogger(__name__)
router = Router()


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
        
        # Получаем количество сообщений каждого типа
        worker_messages_count = len(response.worker_messages) if response.worker_messages else 0
        customer_messages_count = len(response.customer_messages) if response.customer_messages else 0
        
        # Получаем счетчики прочитанных сообщений
        last_read_by_worker = getattr(response, 'last_read_by_worker', 0)
        last_read_by_customer = getattr(response, 'last_read_by_customer', 0)
        
        # Получаем счетчики последних сообщений
        last_message_by_worker = getattr(response, 'last_message_by_worker', 0)
        last_message_by_customer = getattr(response, 'last_message_by_customer', 0)
        
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

async def format_chat_history_for_display(user_type: str, abs_id: int, worker, customer) -> str:
    """
    Форматирует историю чата для отображения в просмотре отклика
    Возвращает текст истории переписки с индикаторами непрочитанных сообщений
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
                chat_history += f"{unread_indicator} **{sender_name}:** {msg_text}\n"
        
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
    т.к. нельзя узнать, открыл ли пользователь уведомление или нет.
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
        
        logger.info(f"[CHAT_HISTORY] Loading chat history. Worker messages: {len(response.worker_messages) if response.worker_messages else 0}, Customer messages: {len(response.customer_messages) if response.customer_messages else 0}")

        # Собираем историю диалога в хронологическом порядке
        chat_history = ""

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
            header = f"💬 **Чат с исполнителем**\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {worker_name}\n\n"
        else:  # worker
            header = f"💬 **Чат с заказчиком**\n\n📋 Объявление: #{abs_id}\n👤 Заказчик: ID#{customer.id}\n\n"
        
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
                    chat_history += f" **{sender_name}:** {msg_text}\n"
                
                # Формируем полный текст
                full_text = header + "📝 **История переписки:**\n" + chat_history
                
                # Проверяем длину
                if len(full_text) <= MAX_MESSAGE_LENGTH:
                    messages_shown = limit
                    break
            
            # Если прошли все итерации и ничего не влезло, показываем специальное сообщение
            if messages_shown == 0:
                full_text = header + "💬 История переписки слишком длинная.\n\nОтправьте новое сообщение, чтобы продолжить диалог."

        # Проверяем статус контактов для кнопок
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        contacts_purchased = contact_exchange and contact_exchange.contacts_purchased
        contacts_sent = contact_exchange and contact_exchange.contacts_sent

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
                contact_requested=contacts_sent,
                contact_sent=contacts_sent,
                contacts_purchased=contacts_purchased
            )
        else:  # worker
            # Кнопки для исполнителя
            reply_markup = kbc.anonymous_chat_worker_buttons(
                abs_id=abs_id,
                has_contacts=contacts_purchased,
                contacts_requested=contacts_sent
            )

        # Проверяем, есть ли уже сообщение чата для этого пользователя
        # Для простоты пока отправляем новое сообщение каждый раз
        # В будущем можно добавить сохранение message_id в базе данных
        await bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in send_or_update_chat_message: {e}")
        # Fallback - отправляем простое уведомление
        if user_type == "customer":
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 **Новое сообщение от исполнителя**\n\n📋 Объявление: #{abs_id}\n\n💬 **Сообщение:**\n{message_text}",
                parse_mode='Markdown'
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 **Новое сообщение от заказчика**\n\n📋 Объявление: #{abs_id}\n\n💬 **Сообщение:**\n{message_text}",
                parse_mode='Markdown'
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

        if not customer or not worker:
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

        # Обновляем запись - заказчик подтвердил
        await contact_exchange.update(contacts_sent=True)

        kbc = KeyboardCollection()

        # СЦЕНАРИЙ 1: Исполнитель имеет безлимитную подписку
        if worker.unlimited_contacts_until:
            from datetime import datetime
            try:
                end_date = datetime.strptime(worker.unlimited_contacts_until, "%Y-%m-%d")
                if end_date > datetime.now():
                    # Безлимит активен - сразу передаем контакты
                    await contact_exchange.update(contacts_purchased=True)

                    # Передаем контакты исполнителю с учетом нового функционала
                    contacts_text = f"📞 <b>Контакты заказчика:</b>\n\n"
                    
                    # Формируем контакты в зависимости от настроек заказчика
                    if customer.contact_type == "telegram_only":
                        contacts_text += f"📱 <b>Telegram:</b> [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 <b>ID:</b> {customer.tg_id}"
                    elif customer.contact_type == "phone_only":
                        contacts_text += f"📞 <b>Номер телефона:</b> [{customer.phone_number}](tel:{customer.phone_number})"
                    elif customer.contact_type == "both":
                        contacts_text += f"📱 <b>Telegram:</b> [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 <b>ID:</b> {customer.tg_id}\n"
                        contacts_text += f"📞 <b>Номер телефона:</b> [{customer.phone_number}](tel:{customer.phone_number})"
                    else:
                        # Fallback - показываем только Telegram если контакты не настроены
                        contacts_text += f"📱 <b>Telegram:</b> [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 <b>ID:</b> {customer.tg_id}"

                    await bot.send_message(
                        chat_id=worker.tg_id,
                        text=f"🎉 <b>Контакты получены!</b>\n\n📋 Объявление: #{abs_id}\n👤 Заказчик: {f'ID#{customer.id}'}\n\n{contacts_text}",
                        parse_mode='HTML'
                    )

                    # Уведомляем заказчика
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=f"✅ <b>Контакты переданы исполнителю!</b>\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\n💬 Чат закрыт - теперь общайтесь напрямую.",
                        parse_mode='HTML'
                    )

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
            # Списываем один контакт
            new_count = worker.purchased_contacts - 1
            await worker.update_purchased_contacts(purchased_contacts=new_count)
            await contact_exchange.update(contacts_purchased=True)

            # Передаем контакты исполнителю с учетом нового функционала
            contacts_text = f"📞 **Контакты заказчика:**\n\n"
            contacts_text += f"👤 **Имя:** {customer.tg_name}\n"
            
            # Формируем контакты в зависимости от настроек заказчика
            if customer.contact_type == "telegram_only":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}"
            elif customer.contact_type == "phone_only":
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
            elif customer.contact_type == "both":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}\n"
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
            else:
                # Fallback - показываем только Telegram если контакты не настроены
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}"

            await bot.send_message(
                chat_id=worker.tg_id,
                text=f"🎉 **Контакты получены!**\n\n📋 Объявление: #{abs_id}\n👤 Заказчик: {f'ID#{customer.id}'}\n\n{contacts_text}",
                parse_mode='Markdown'
            )

            # Уведомляем заказчика
            await bot.send_message(
                chat_id=customer.tg_id,
                text=f"✅ **Контакты переданы исполнителю!**\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\n💬 Чат закрыт - теперь общайтесь напрямую.",
                parse_mode='Markdown'
            )

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
                original_text += "✅ **Контакты переданы исполнителю!**"

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
                        parse_mode='Markdown'
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
                        parse_mode='Markdown'
                    )
            except Exception as edit_error:
                # Если не можем отредактировать, отправляем новое сообщение
                await callback.message.answer(
                    text="✅ **Контакты переданы исполнителю!**",
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=True,
                        contact_sent=True,
                        contacts_purchased=True
                    ),
                    parse_mode='Markdown'
                )

            await callback.answer("✅ Контакты переданы исполнителю!")
            return

        # СЦЕНАРИЙ 3: Исполнитель не имеет контактов - нужно покупать
        # Отправляем уведомление исполнителю (только один раз, так как есть проверка выше)
        notification_text = (
            f"🔔 **Заказчик подтвердил передачу контактов!**\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
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
            parse_mode='Markdown'
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
            original_text += "⏳ **Ожидаем решения исполнителя...**"

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
                    parse_mode='Markdown'
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
                    parse_mode='Markdown'
                )
        except Exception as edit_error:
            # Если не можем отредактировать, отправляем новое сообщение
            await callback.message.answer(
                text="⏳ **Ожидаем решения исполнителя...**",
                reply_markup=kbc.anonymous_chat_customer_buttons(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    contact_requested=True,
                    contact_sent=True,
                    contacts_purchased=False
                ),
                parse_mode='Markdown'
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

            # Передаем контакты исполнителю с учетом нового функционала
            contacts_text = f"📞 **Контакты заказчика:**\n\n"
            contacts_text += f"👤 **Имя:** {customer.tg_name}\n"
            
            # Формируем контакты в зависимости от настроек заказчика
            if customer.contact_type == "telegram_only":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}"
            elif customer.contact_type == "phone_only":
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
            elif customer.contact_type == "both":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}\n"
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
            else:
                # Fallback - показываем только Telegram если контакты не настроены
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}"

            await bot.send_message(
                chat_id=worker.tg_id,
                text=f"🎉 **Контакты получены!**\n\n📋 Объявление: #{abs_id}\n👤 Заказчик: {f'ID#{customer.id}'}\n\n{contacts_text}\n\n💰 Осталось контактов: {new_count}",
                parse_mode='Markdown'
            )

            # Уведомляем заказчика
            await bot.send_message(
                chat_id=customer.tg_id,
                text=f"✅ **Контакты переданы исполнителю!**\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\n💬 Чат закрыт - теперь общайтесь напрямую.",
                parse_mode='Markdown'
            )

            # Закрываем чат
            response = await WorkersAndAbs.get_by_worker_and_abs(worker.id, abs_id)
            if response:
                await response.update(applyed=False)

            # Обновляем сообщение
            kbc = KeyboardCollection()
            try:
                await callback.message.answer(
                    text=f"✅ **Контакты переданы!**\n\n📋 Объявление: #{abs_id}\n\n{contacts_text}\n\n💰 Осталось контактов: {new_count}",
                    reply_markup=kbc.menu_btn(),
                    parse_mode='Markdown'
                )
            except TelegramBadRequest:
                # Если сообщение недоступно для редактирования, отправляем новое
                await callback.message.answer(
                    text=f"✅ **Контакты переданы!**\n\n📋 Объявление: #{abs_id}\n\n{contacts_text}\n\n💰 Осталось контактов: {new_count}",
                    reply_markup=kbc.menu_btn(),
                    parse_mode='Markdown'
                )

            # Устанавливаем правильное состояние
            await state.set_state(WorkStates.worker_menu)

            await callback.answer("✅ Контакты получены!")
            return

        # Нет купленных контактов - показываем тарифы покупки
        kbc = KeyboardCollection()
        try:
            await callback.message.answer(
                text="💰 **Тарифы на покупку контактов**\n\nВыберите подходящий тариф:",
                reply_markup=kbc.buy_tokens_tariffs(),
                parse_mode='Markdown'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text="💰 **Тарифы на покупку контактов**\n\nВыберите подходящий тариф:",
                reply_markup=kbc.buy_tokens_tariffs(),
                parse_mode='Markdown'
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


@router.callback_query(lambda c: c.data.startswith('reject_contact_offer_'))
async def reject_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Исполнитель отказывается от покупки контактов"""
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
        await bot.send_message(
            chat_id=customer.tg_id,
            text=f"❌ **Исполнитель отказался от покупки контактов**\n\n📋 Объявление: #{abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\nОтклик возвращен в обычный режим.",
            parse_mode='Markdown'
        )

        # Удаляем запись ContactExchange
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker.id, abs_id)
        if contact_exchange:
            await contact_exchange.delete()

        # Обновляем сообщение исполнителя
        kbc = KeyboardCollection()
        try:
            await callback.message.answer(
                text="❌ **Вы отказались от покупки контактов**\n\nОтклик возвращен в обычный режим.",
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text="❌ **Вы отказались от покупки контактов**\n\nОтклик возвращен в обычный режим.",
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )

        # Устанавливаем правильное состояние
        await state.set_state(WorkStates.worker_menu)

        await callback.answer("❌ Вы отказались от покупки контактов")

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
            f"[CONTACT_SHARE] Customer {callback.from_user.id} declined contact share for worker {worker_id}, abs {abs_id}")
        logger.info(f"[CONTACT_SHARE] Customer declined contact share")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        worker = await Worker.get_worker(id=worker_id)

        if not customer or not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Проверяем, что запрос контакта все еще активен
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if not contact_exchange:
            await callback.answer("❌ Запрос контакта уже отменен исполнителем", show_alert=True)
            return

        # Сохраняем message_id перед удалением contact_exchange
        message_id_to_delete = None
        if contact_exchange.message_id:
            message_id_to_delete = contact_exchange.message_id

        # Удаляем запись ContactExchange
        await contact_exchange.delete()

        # Уведомляем исполнителя
        notification_text = (
            f"❌ **Заказчик отклонил передачу контактов**\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
            f"К сожалению, заказчик не готов поделиться контактами.\n"
            f"Вы можете запросить контакт позже."
        )

        await bot.send_message(
            chat_id=worker.tg_id,
            text=notification_text,
            parse_mode='Markdown'
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
        new_text = current_text + "\n\n❌ **Передача контактов отклонена.**"

        # Безопасное редактирование (может быть фото)
        try:
            if callback.message.text:
                await callback.message.answer(
                    text=new_text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=[{
                            'worker_id': worker_id,
                            'worker_public_id': f'ID#{worker.id}',
                            'active': True
                        }],
                        abs_id=abs_id
                    ),
                    parse_mode='Markdown'
                )
            else:
                # Если было фото с caption
                await callback.message.edit_caption(
                    caption=new_text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=[{
                            'worker_id': worker_id,
                            'worker_public_id': f'ID#{worker.id}',
                            'active': True
                        }],
                        abs_id=abs_id
                    ),
                    parse_mode='Markdown'
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
                        'active': True
                    }],
                    abs_id=abs_id
                ),
                parse_mode='Markdown'
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

        # Уведомляем исполнителя с кнопками принятия/отклонения
        notification_text = (
            f"🔔 **Заказчик предлагает передать контакты!**\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
            f"Хотите получить контакты заказчика?"
        )

        kbc = KeyboardCollection()
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline(button_text="✅ Принять",
                                callback_data=f"accept_contact_offer_{worker_id}_{abs_id}"))
        builder.add(kbc._inline(button_text="❌ Отклонить",
                                callback_data=f"reject_contact_offer_{worker_id}_{abs_id}"))
        builder.adjust(1)

        message = await bot.send_message(
            chat_id=worker.tg_id,
            text=notification_text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )

        print(message.message_id)

        # Сохраняем message_id в ContactExchange
        await contact_exchange.update(message_id=message.message_id)

        # Обновляем кнопки заказчика
        # Получаем текст или caption (если было фото)
        current_text = callback.message.text or callback.message.caption or ""
        new_text = current_text + "\n\n✅ **Контакты предложены исполнителю!**"

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
                    parse_mode='Markdown'
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
                    parse_mode='Markdown'
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
                parse_mode='Markdown'
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

            # Закрываем чат - обновляем WorkersAndAbs
            response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
            if response:
                await response.update(applyed=False)  # Закрываем чат

            # Уведомляем заказчика о закрытии чата
            await bot.send_message(
                chat_id=customer.tg_id,
                text=f"✅ **Исполнитель получил ваши контакты!**\n\n"
                     f"📋 Объявление: #{abs_id}\n"
                     f"👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
                     f"🔒 **Чат закрыт** - контакты переданы.",
                parse_mode='Markdown'
            )

            # Отправляем контакты исполнителю с учетом нового функционала
            contacts_text = f"📞 **Контакты заказчика получены!**\n\n"
            contacts_text += f"📋 Объявление: #{abs_id}\n"
            contacts_text += f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
            
            # Формируем контакты в зависимости от настроек заказчика
            if customer.contact_type == "telegram_only":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}\n\n"
            elif customer.contact_type == "phone_only":
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
            elif customer.contact_type == "both":
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}\n"
                contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
            else:
                # Fallback - показываем только Telegram если контакты не настроены
                contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                contacts_text += f"🆔 **ID:** {customer.tg_id}\n\n"
            
            contacts_text += f"🔒 **Чат закрыт** - теперь можете общаться напрямую."

            try:
                await callback.message.answer(
                    text=contacts_text,
                    parse_mode='Markdown'
                )
            except TelegramBadRequest:
                # Если сообщение недоступно для редактирования, отправляем новое
                await callback.message.answer(
                    text=contacts_text,
                    parse_mode='Markdown'
                )

            await callback.answer("✅ Контакты получены! Чат закрыт.")

        else:
            # Показываем тарифы для покупки
            kbc = KeyboardCollection()
            try:
                await callback.message.answer(
                    text=f"💰 **Для получения контактов необходимо оплатить**\n\n"
                         f"📋 Объявление: #{abs_id}\n"
                         f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                         f"Выберите тариф:",
                    reply_markup=kbc.buy_tokens_tariffs(),
                    parse_mode='Markdown'
                )
            except TelegramBadRequest:
                # Если сообщение недоступно для редактирования, отправляем новое
                await callback.message.answer(
                    text=f"💰 **Для получения контактов необходимо оплатить**\n\n"
                         f"📋 Объявление: #{abs_id}\n"
                         f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                         f"Выберите тариф:",
                    reply_markup=kbc.buy_tokens_tariffs(),
                    parse_mode='Markdown'
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


@router.callback_query(lambda c: c.data.startswith('reject_contact_offer_'))
async def reject_contact_offer(callback: CallbackQuery, state: FSMContext):
    """Исполнитель отклоняет предложение контактов"""
    try:
        # reject_contact_offer_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])

        print(f"[CONTACT_REJECT] Worker {callback.from_user.id} rejects contact offer for abs {abs_id}")
        logger.info(f"[CONTACT_REJECT] Worker rejects contact offer")

        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        customer = await Customer.get_customer(id=(await Abs.get_one(id=abs_id)).customer_id)

        if not worker or not customer:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Уведомляем заказчика
        await bot.send_message(
            chat_id=customer.tg_id,
            text=f"❌ **Исполнитель отклонил получение контактов**\n\n"
                 f"📋 Объявление: #{abs_id}\n"
                 f"👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
                 f"Исполнитель не готов получить контакты в данный момент.",
            parse_mode='Markdown'
        )

        try:
            await callback.message.answer(
                text="❌ **Предложение контактов отклонено**\n\n"
                     "Вы отклонили получение контактов заказчика.",
                parse_mode='Markdown'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text="❌ **Предложение контактов отклонено**\n\n"
                     "Вы отклонили получение контактов заказчика.",
                parse_mode='Markdown'
            )

        await callback.answer("❌ Предложение отклонено")

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
        is_valid, error_message = check_message_for_contacts(message.text)
        if not is_valid:
            await message.answer(
                f"🚫 <b>Сообщение заблокировано!</b>\n\n"
                f"{error_message}\n\n"
                "Используйте кнопку 'Запросить контакт' для получения контактов заказчика.",
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
            await message.answer("🔒 **Чат закрыт** - контакты уже переданы.\nТеперь общайтесь напрямую.")
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
        current_timestamps = response.message_timestamps if hasattr(response, 'message_timestamps') and response.message_timestamps else []
        
        # Добавляем новую метку
        new_timestamps = current_timestamps + [{"sender": "worker", "timestamp": current_timestamp}]
        
        # Обновляем в БД
        await response.update(
            worker_messages=new_worker_messages,
            turn=False,  # теперь очередь заказчика
            message_timestamps=new_timestamps,
            last_message_by_worker=len(new_worker_messages),  # обновляем счетчик последнего сообщения
            last_read_by_worker=len(customer_messages_list)  # исполнитель "прочитал" сообщения заказчика, отправив ответ
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

        await message.answer("✅ Сообщение отправлено заказчику!")
        
        # Возвращаем исполнителя в меню
        from app.handlers.worker import menu_worker
        from aiogram.types import CallbackQuery
        fake_callback = CallbackQuery(
            id="fake_callback_id",
            message=message,
            from_user=message.from_user,
            data="menu",
            chat_instance=""
        )
        await menu_worker(fake_callback, state)

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
        is_valid, error_message = check_message_for_contacts(message.text)
        if not is_valid:
            await message.answer(
                f"🚫 <b>Сообщение заблокировано!</b>\n\n"
                f"{error_message}\n\n"
                "Используйте кнопку 'Предложить контакты' для передачи контактов исполнителю.",
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
            await message.answer("🔒 **Чат закрыт** - контакты уже переданы.\nТеперь общайтесь напрямую.")
            return

        # Добавляем сообщение заказчика
        customer_messages_list = list(response.customer_messages) if response.customer_messages else []
        new_customer_messages = customer_messages_list + [message.text]
        
        # Получаем сообщения исполнителя для обновления счетчика прочитанных
        worker_messages_list = list(response.worker_messages) if response.worker_messages else []
        
        # Добавляем временную метку
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Получаем текущие метки или создаем пустой список
        current_timestamps = response.message_timestamps if hasattr(response, 'message_timestamps') and response.message_timestamps else []
        
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

        await message.answer("✅ Сообщение отправлено исполнителю!")

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
            text=f"💬 **Чат с заказчиком**\n\n"
                 f"📋 Объявление: #{abs_id}\n"
                 f"👤 Заказчик: {f'ID#{customer.id}'}\n\n"
                 f"Напишите сообщение заказчику:",
            parse_mode='Markdown'
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
            text = "📭 **У вас пока нет откликов**\n\n"
            text += "Откликайтесь на объявления, чтобы найти работу!"

            # Безопасное редактирование
            try:
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.menu_btn(),
                    parse_mode='Markdown'
                )
            except Exception:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.menu_btn(),
                    parse_mode='Markdown'
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
        text = f"📋 **Ваши Отклики ({len(responses_data)})**\n\n"
        text += "💬 - активный чат\n"
        text += "✅ - контакты получены"

        # Безопасное редактирование
        try:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.my_responses_list_buttons(responses_data),
                parse_mode='Markdown'
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=text,
                reply_markup=kbc.my_responses_list_buttons(responses_data),
                parse_mode='Markdown'
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
        try:
            photo_dict = json.loads(advertisement.photo_path) if isinstance(advertisement.photo_path, str) else advertisement.photo_path
            count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
        except (json.JSONDecodeError, TypeError, AttributeError):
            count_photo = 0
        
        # Формируем текст
        from app.untils import help_defs
        text = f"📋 **Объявление #{abs_id}**\n\n"
        text += help_defs.read_text_file(advertisement.text_path)
        text += "\n\n" + "=" * 30 + "\n\n"
        
        # Показываем историю переписки
        customer = await Customer.get_customer(id=advertisement.customer_id)
        chat_history = await format_chat_history_for_display("worker", abs_id, worker, customer)
        
        if chat_history:
            # Проверяем длину текста перед добавлением истории
            temp_text = text + "📝 **История переписки:**\n\n" + chat_history
            
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
                    text += "📝 **История переписки:**\n\n"
                    text += truncated_history
                    text += f"\n... (показаны последние сообщения)\n"
                    text += "\n" + "=" * 30 + "\n\n"
                else:
                    # Если даже одна строка не влезла, не показываем историю
                    text += "\n📝 История переписки слишком длинная для отображения.\n"
                    text += "\n" + "=" * 30 + "\n\n"
            else:
                text += "📝 **История переписки:**\n\n"
                text += chat_history
                text += "\n" + "=" * 30 + "\n\n"

        if has_contacts:
            # Контакты уже куплены
            customer = await Customer.get_customer(id=advertisement.customer_id)
            text += "✅ **Контакты получены:**\n\n"
            
            # Формируем контакты в зависимости от настроек заказчика
            if customer.contact_type == "telegram_only":
                text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                text += f"🆔 **ID:** {customer.tg_id}\n\n"
            elif customer.contact_type == "phone_only":
                text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
            elif customer.contact_type == "both":
                text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                text += f"🆔 **ID:** {customer.tg_id}\n"
                text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
            else:
                # Fallback - показываем только Telegram если контакты не настроены
                text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                text += f"🆔 **ID:** {customer.tg_id}\n\n"
            
            text += "🔒 Чат закрыт"
        elif customer_confirmed:
            # Заказчик подтвердил, исполнитель может покупать
            text += "💰 **Заказчик подтвердил передачу контактов**\n\n"
            text += "Для получения контактов необходимо их купить."
        elif waiting_confirmation:
            # Ожидаем подтверждения от заказчика
            text += "⏳ **Статус:** Ожидание подтверждения заказчика\n\n"
            text += "Вы запросили контакт заказчика.\n"
            text += "Заказчик должен подтвердить передачу контакта.\n"
            text += "После подтверждения вам будет предложено приобрести контакт."
        else:
            # Можно запросить контакты
            text += "💬 **Чат активен**\n\n"
            text += "Вы можете написать сообщение заказчику или запросить контакт."

        kbc = KeyboardCollection()

        # Устанавливаем состояние анонимного чата
        await state.update_data(current_chat_abs_id=abs_id)
        await state.set_state(WorkStates.worker_anonymous_chat)

        # Показываем с фото если есть
        if count_photo > 0:
            try:
                from aiogram.types import FSInputFile, InputMediaPhoto
                photo_path = advertisement.photo_path['0']
                
                if 'https' in photo_path:
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo=photo_path,
                        caption=text,
                        reply_markup=kbc.anonymous_chat_worker_buttons(
                            abs_id=abs_id,
                            has_contacts=has_contacts,
                            contacts_requested=customer_confirmed,
                            contacts_sent=waiting_confirmation,
                            count_photo=count_photo,
                            photo_num=0
                        ),
                        parse_mode='Markdown'
                    )
                else:
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo=FSInputFile(photo_path),
                        caption=text,
                        reply_markup=kbc.anonymous_chat_worker_buttons(
                            abs_id=abs_id,
                            has_contacts=has_contacts,
                            contacts_requested=customer_confirmed,
                            contacts_sent=waiting_confirmation,
                            count_photo=count_photo,
                            photo_num=0
                        ),
                        parse_mode='Markdown'
                    )
            except Exception:
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
                    parse_mode='Markdown'
                )
        else:
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
                parse_mode='Markdown'
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

        confirmation_text = f"⚠️ **Подтверждение отмены отклика**\n\n"
        confirmation_text += f"Вы действительно хотите отменить отклик на объявление #{abs_id}?\n\n"
        confirmation_text += f"**Последствия:**\n"
        confirmation_text += f"❌ Активность снизится: {current_activity} → {new_activity} (-13)\n"
        confirmation_text += f"{zone_emoji} Вы перейдете в {zone_name} зону активности\n\n"

        if new_activity < 74:
            confirmation_text += f"⚠️ **Внимание!** При снижении активности могут быть ограничения на отклики.\n\n"

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
            parse_mode='Markdown'
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
        notification_text = f"Отмена отклика:\n\n—13 активность\n\n{zone_emoji} Текущая активность: {new_activity}"

        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=notification_text
            )
        except Exception as e:
            logger.error(f"Error sending cancellation notification to worker {worker.tg_id}: {e}")

        # Отправляем уведомление заказчику
        from app.data.database.models import Abs, Customer
        advertisement = await Abs.get_one(id=abs_id)
        if advertisement:
            customer = await Customer.get_customer(id=advertisement.customer_id)
            if customer:
                try:
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=f"📨 Исполнитель отменил отклик на объявление #{abs_id}"
                    )
                except Exception as e:
                    logger.error(f"Error sending cancellation notification to customer {customer.tg_id}: {e}")

        # Возвращаемся к списку откликов
        kbc = KeyboardCollection()
        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text="✅ Отклик отменен\n\nВы вернулись к списку откликов",
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
        is_valid, error_message = check_message_for_contacts(message.text)

        if not is_valid:
            kbc = KeyboardCollection()
            await message.answer(
                text=f"🚫 <b>Сообщение заблокировано!</b>\n\n{error_message}",
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
                current_timestamps = response.message_timestamps if hasattr(response, 'message_timestamps') and response.message_timestamps else []
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
        notification_text = f"💬 **Новое сообщение от исполнителя**\n\n"
        notification_text += f"📋 Объявление: #{abs_id}\n\n"

        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 **ID:** {worker.id} {worker_name}\n"

        # Рейтинг
        if worker.count_ratings > 0:
            notification_text += f"⭐ **Рейтинг:** {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            notification_text += f"⭐ **Рейтинг:** Нет оценок\n"

        # Статус верификации и регистрации (всегда показываем)
        status_string = await get_worker_status_string(worker.id)
        notification_text += f"📋 **Статус:** {status_string}\n"

        # Выполнено заказов
        notification_text += f"📦 **Выполнено заказов:** {worker.order_count}\n"

        # Дата регистрации
        notification_text += f"📅 **Зарегистрирован:** {worker.registration_data}\n\n"

        notification_text += f"💬 **Сообщение:**\n{message.text}"

        # Отправляем с фото или без
        if worker.profile_photo:
            try:
                from aiogram.types import FSInputFile
                await bot.send_photo(
                    chat_id=customer.tg_id,
                    photo=FSInputFile(worker.profile_photo),
                    caption=notification_text,
                    parse_mode='Markdown'
                )
            except Exception:
                # Если фото не загрузилось, отправляем текстом
                await bot.send_message(
                    chat_id=customer.tg_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
        else:
            await bot.send_message(
                chat_id=customer.tg_id,
                text=notification_text,
                parse_mode='Markdown'
            )

        await message.answer("✅ Сообщение отправлено заказчику")
        
        # Возвращаем исполнителя в меню
        from app.handlers.worker import menu_worker
        from aiogram.types import CallbackQuery
        fake_callback = CallbackQuery(
            id="fake_callback_id",
            message=message,
            from_user=message.from_user,
            data="menu",
            chat_instance=""
        )
        await menu_worker(fake_callback, state)

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
        notification_text = f"📞 **Запрос контакта от исполнителя**\n\n"
        notification_text += f"📋 Объявление: #{abs_id}\n\n"

        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 **ID:** {worker.id} {worker_name}\n"

        # Рейтинг
        if worker.count_ratings > 0:
            notification_text += f"⭐ **Рейтинг:** {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            notification_text += f"⭐ **Рейтинг:** Нет оценок\n"

        # Статус верификации и регистрации (всегда показываем)
        status_string = await get_worker_status_string(worker.id)
        notification_text += f"📋 **Статус:** {status_string}\n"

        # Выполнено заказов
        notification_text += f"📦 **Выполнено заказов:** {worker.order_count}\n"

        # Дата регистрации
        notification_text += f"📅 **Зарегистрирован:** {worker.registration_data}\n\n"

        notification_text += "❓ **Подтвердить передачу контакта?**"

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
                    parse_mode='Markdown'
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
                    parse_mode='Markdown'
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
                parse_mode='Markdown'
            )

        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text="📞 **Запрос отправлен заказчику**\n\n"
                 "⏳ Ожидайте подтверждения.\n"
                 "Вы получите уведомление, когда заказчик ответит.",
            reply_markup=kbc.anonymous_chat_worker_buttons(
                abs_id=abs_id,
                contacts_requested=True
            ),
            parse_mode='Markdown'
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

        # Парсим тариф
        if len(parts) >= 4:
            if parts[2] == 'unlimited':
                # Безлимит
                months = int(parts[3])
                price = int(parts[4])
                tokens = -1  # -1 означает безлимит
                tariff_name = f"Безлимит {months} мес."
            else:
                # Обычные жетоны
                tokens = int(parts[2])
                price = int(parts[3])
                tariff_name = f"{tokens} жетон(ов)"
        else:
            await callback.answer("❌ Неверный формат тарифа", show_alert=True)
            return

        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        # Сохраняем выбор в state
        await state.update_data(
            purchase_tokens=tokens,
            purchase_price=price,
            purchase_tariff=tariff_name
        )
        await state.set_state(WorkStates.worker_buy_tokens)

        confirmation_text = f"""
💰 **Подтверждение покупки**

📦 Тариф: {tariff_name}
💵 Цена: {price}₽

{f'После покупки у вас будет {worker.purchased_contacts + tokens} жетон(ов)' if tokens > 0 else 'Безлимитный доступ к контактам'}

Подтвердить покупку?
        """

        kbc = KeyboardCollection()
        # Здесь должна быть интеграция с платежной системой
        # Пока заглушка
        builder = kbc._inline
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        keyboard_builder = InlineKeyboardBuilder()
        keyboard_builder.add(kbc._inline(
            button_text=f"✅ Оплатить {price}₽",
            callback_data=f"confirm_token_purchase_{tokens}_{price}"
        ))
        keyboard_builder.add(kbc._inline(
            button_text="❌ Отмена",
            callback_data="cancel_token_purchase"
        ))
        keyboard_builder.adjust(1)

        try:
            await callback.message.answer(
                text=confirmation_text,
                reply_markup=keyboard_builder.as_markup(),
                parse_mode='Markdown'
            )
        except TelegramBadRequest:
            # Если сообщение недоступно для редактирования, отправляем новое
            await callback.message.answer(
                text=confirmation_text,
                reply_markup=keyboard_builder.as_markup(),
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Error in buy_tokens: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_token_purchase_'))
async def confirm_token_purchase(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и обработка покупки жетонов"""
    try:
        parts = callback.data.split('_')
        tokens = int(parts[3])
        price = int(parts[4])

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
            if tokens == -1:
                # Безлимит
                from datetime import datetime, timedelta
                months = 1  # Извлекаем из данных
                until_date = (datetime.now() + timedelta(days=30 * months)).strftime('%Y-%m-%d')

                await conn.execute(
                    'UPDATE workers SET unlimited_contacts_until = ? WHERE id = ?',
                    (until_date, worker.id)
                )
            else:
                # Обычные жетоны
                await conn.execute(
                    'UPDATE workers SET purchased_contacts = purchased_contacts + ? WHERE id = ?',
                    (tokens, worker.id)
                )

            await conn.commit()

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

                    # Передаем контакты исполнителю с учетом нового функционала
                    contacts_text = f"📞 **Контакты заказчика:**\n\n"
                    
                    # Формируем контакты в зависимости от настроек заказчика
                    if customer.contact_type == "telegram_only":
                        contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 **ID:** {customer.tg_id}"
                    elif customer.contact_type == "phone_only":
                        contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
                    elif customer.contact_type == "both":
                        contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 **ID:** {customer.tg_id}\n"
                        contacts_text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})"
                    else:
                        # Fallback - показываем только Telegram если контакты не настроены
                        contacts_text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
                        contacts_text += f"🆔 **ID:** {customer.tg_id}"

                    await bot.send_message(
                        chat_id=worker.tg_id,
                        text=f"🎉 **Контакты получены!**\n\n📋 Объявление: #{target_abs_id}\n👤 Заказчик: {f'ID#{customer.id}'}\n\n{contacts_text}",
                        parse_mode='Markdown'
                    )

                    # Уведомляем заказчика
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text=f"✅ **Контакты переданы исполнителю!**\n\n📋 Объявление: #{target_abs_id}\n👤 Исполнитель: {f'ID#{worker.id}'}\n\n💬 Чат закрыт - теперь общайтесь напрямую.",
                        parse_mode='Markdown'
                    )

                    # Закрываем чат
                    response = await WorkersAndAbs.get_by_worker_and_abs(target_worker_id, target_abs_id)
                    if response:
                        await response.update(applyed=False)

                    try:
                        await callback.message.answer(
                            text=f"✅ **Покупка успешна!**\n\nКонтакты заказчика переданы!",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='Markdown'
                        )
                    except TelegramBadRequest:
                        # Если сообщение недоступно для редактирования, отправляем новое
                        await callback.message.answer(
                            text=f"✅ **Покупка успешна!**\n\nКонтакты заказчика переданы!",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='Markdown'
                        )
                else:
                    try:
                        await callback.message.answer(
                            text=f"✅ **Покупка успешна!**\n\n"
                                 f"{'Безлимит активирован!' if tokens == -1 else f'Добавлено {tokens} жетон(ов)'}",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='Markdown'
                        )
                    except TelegramBadRequest:
                        # Если сообщение недоступно для редактирования, отправляем новое
                        await callback.message.answer(
                            text=f"✅ **Покупка успешна!**\n\n"
                                 f"{'Безлимит активирован!' if tokens == -1 else f'Добавлено {tokens} жетон(ов)'}",
                            reply_markup=kbc.menu_btn(),
                            parse_mode='Markdown'
                        )
            else:
                # Обычная покупка токенов
                try:
                    await callback.message.answer(
                        text=f"✅ **Покупка успешна!**\n\n"
                             f"{'Безлимит активирован!' if tokens == -1 else f'Добавлено {tokens} жетон(ов)'}",
                        reply_markup=kbc.menu_btn(),
                        parse_mode='Markdown'
                    )
                except TelegramBadRequest:
                    # Если сообщение недоступно для редактирования, отправляем новое
                    await callback.message.answer(
                        text=f"✅ **Покупка успешна!**\n\n"
                             f"{'Безлимит активирован!' if tokens == -1 else f'Добавлено {tokens} жетон(ов)'}",
                        reply_markup=kbc.menu_btn(),
                        parse_mode='Markdown'
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
            f"ℹ️ **Исполнитель отменил запрос контакта**\n\n"
            f"📋 Объявление: #{abs_id}\n"
            f"👤 Исполнитель: {f'ID#{worker.id}'}\n\n"
            f"Запрос на передачу контакта отменен."
        )

        await bot.send_message(
            chat_id=customer.tg_id,
            text=notification_text,
            parse_mode='Markdown'
        )

        # Обновляем сообщение исполнителя
        kbc = KeyboardCollection()
        # Безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text="❌ **Запрос контакта отменен**\n\nВы можете запросить контакт позже.",
            reply_markup=kbc.anonymous_chat_worker_buttons(abs_id=abs_id),
            parse_mode='Markdown'
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
    try:
        photo_dict = json.loads(advertisement.photo_path) if isinstance(advertisement.photo_path, str) else advertisement.photo_path
        count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
    except (json.JSONDecodeError, TypeError, AttributeError):
        count_photo = 1
    
    # Циклическая навигация
    if photo_num <= -1:
        photo_num = count_photo - 1
    elif photo_num >= count_photo:
        photo_num = 0
    
    # Получаем путь к фото
    photo_path = advertisement.photo_path[str(photo_num)]
    
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
    from app.untils import help_defs
    text = f"📋 **Объявление #{abs_id}**\n\n"
    text += help_defs.read_text_file(advertisement.text_path)
    text += "\n\n" + "=" * 30 + "\n\n"
    
    if has_contacts:
        # Контакты уже куплены
        customer = await Customer.get_customer(id=advertisement.customer_id)
        text += "✅ **Контакты получены:**\n\n"
        
        # Формируем контакты в зависимости от настроек заказчика
        if customer.contact_type == "telegram_only":
            text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
            text += f"🆔 **ID:** {customer.tg_id}\n\n"
        elif customer.contact_type == "phone_only":
            text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
        elif customer.contact_type == "both":
            text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
            text += f"🆔 **ID:** {customer.tg_id}\n"
            text += f"📞 **Номер телефона:** [{customer.phone_number}](tel:{customer.phone_number})\n\n"
        else:
            # Fallback - показываем только Telegram если контакты не настроены
            text += f"📱 **Telegram:** [@{customer.tg_name}](tg://user?id={customer.tg_id})\n"
            text += f"🆔 **ID:** {customer.tg_id}\n\n"
        
        text += "🔒 Чат закрыт"
    elif customer_confirmed:
        # Заказчик подтвердил, исполнитель может покупать
        text += "💰 **Заказчик подтвердил передачу контактов**\n\n"
        text += "Для получения контактов необходимо их купить."
    elif waiting_confirmation:
        # Ожидаем подтверждения от заказчика
        text += "⏳ **Статус:** Ожидание подтверждения заказчика\n\n"
        text += "Вы запросили контакт заказчика.\n"
        text += "Заказчик должен подтвердить передачу контакта.\n"
        text += "После подтверждения вам будет предложено приобрести контакт."
    else:
        # Можно запросить контакты
        text += "💬 **Чат активен**\n\n"
        text += "Вы можете написать сообщение заказчику или запросить контакт."
    
    # Обновляем медиа
    try:
        from aiogram.types import FSInputFile, InputMediaPhoto
        
        if 'https' in photo_path:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=photo_path,
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
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
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
    except Exception as e:
        logger.error(f"Error updating photo in navigate_photo_worker_response: {e}")
        await callback.answer("Ошибка обновления фото", show_alert=True)
