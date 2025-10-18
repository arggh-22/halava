"""
Handlers для работы с откликами исполнителя:
- Инициация отклика
- Анонимный чат
- Запрос контактов
- Покупка жетонов
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.states import WorkStates, CustomerStates
from app.keyboards import KeyboardCollection
from app.data.database.models import Worker, Customer, Abs, WorkersAndAbs, ContactExchange
from loaders import bot
from app.untils.contact_filter import check_message_for_contacts

logger = logging.getLogger(__name__)
router = Router()

# Логируем при импорте модуля
print("[WORKER_RESPONSES] Module imported!")
logger.info("[WORKER_RESPONSES] Router initialized!")
print(f"[WORKER_RESPONSES] Router object: {router}")


# Универсальная функция для безопасного редактирования сообщений
async def safe_edit_or_send(callback: CallbackQuery, text: str, reply_markup=None, parse_mode: str = 'Markdown'):
    """Пытается отредактировать сообщение, если не получается - удаляет и отправляет новое"""
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception:
        # Если не получилось (было фото или другая ошибка), удаляем старое и отправляем новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )


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


# Универсальная функция для отправки сообщения с фото профиля или без
async def send_with_worker_photo(chat_id, worker, text: str, reply_markup=None, parse_mode: str = 'Markdown'):
    """Отправляет сообщение с фото исполнителя (если есть) или просто текст"""
    from loaders import bot
    from aiogram.types import FSInputFile
    
    if worker.profile_photo:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(worker.profile_photo),
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception:
            # Если фото не загрузилось, отправляем текстом
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

# Текст правил чата
CHAT_RULES_TEXT = """
⚠️ **ВАЖНО: Правила Анонимного Чата**

🚫 **СТРОГО ЗАПРЕЩЕНО:**
• Передавать номера телефонов (в любом виде)
• Отправлять email адреса
• Делиться ссылками на соцсети/мессенджеры  
• Использовать латинские буквы
• Отправлять медиафайлы (фото, видео, документы)
• Пытаться обойти фильтр (разбивать контакты)

✅ **ДЛЯ ОБМЕНА КОНТАКТАМИ:**
Используйте кнопку **"📞 Запросить контакт"**

⚠️ **При нарушении:**
Сообщение будет заблокировано, возможна блокировка аккаунта!

**Вы ознакомились с правилами и готовы продолжить?**
"""


# ========== 1. ИНИЦИАЦИЯ ОТКЛИКА ==========

# Тестовый handler удален - он перехватывал все respond_to_ad callback'и

# Тестовый handler удален - он перехватывал все callback'и

# Handler для просмотра отклика заказчиком
@router.callback_query(lambda c: c.data.startswith('view_response_'))
async def view_response_by_customer(callback: CallbackQuery, state: FSMContext):
    """Заказчик просматривает отклик исполнителя"""
    try:
        # view_response_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[2])
        abs_id = int(parts[3])
        
        print(f"[CUSTOMER_VIEW] Customer {callback.from_user.id} viewing response: worker_id={worker_id}, abs_id={abs_id}")
        logger.info(f"[CUSTOMER_VIEW] Customer viewing response: worker_id={worker_id}, abs_id={abs_id}")
        
        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return
        
        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement or advertisement.customer_id != customer.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return
        
        # Формируем текст с информацией об исполнителе
        text = f"📋 **Отклик на объявление #{abs_id}**\n\n"
        
        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        text += f"👤 **ID:** {worker.public_id or f'#{worker.id}'} {worker_name}\n"
        
        # Рейтинг
        if worker.count_ratings > 0:
            text += f"⭐ **Рейтинг:** {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            text += f"⭐ **Рейтинг:** Нет оценок\n"
        
        # Статус верификации и регистрации
        status_string = await get_worker_status_string(worker.id)
        text += f"📋 **Статус:** {status_string}\n"
        
        # Выполнено заказов
        text += f"📦 **Выполнено заказов:** {worker.order_count}\n"
        
        # Дата регистрации
        text += f"📅 **Зарегистрирован:** {worker.registration_data}\n\n"
        
        # Показываем сообщения
        if response.worker_messages:
            text += "💬 **Сообщения исполнителя:**\n"
            for msg in response.worker_messages:
                text += f"• {msg}\n"
            text += "\n"
        
        if response.customer_messages:
            text += "💬 **Ваши сообщения:**\n"
            for msg in response.customer_messages:
                text += f"• {msg}\n"
            text += "\n"
        
        # Проверяем статус контактов и чата
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        contact_requested = contact_exchange is not None
        contacts_purchased = contact_exchange and contact_exchange.contacts_purchased
        contacts_sent = contact_exchange and contact_exchange.contacts_sent
        
        # Если контакты переданы (куплены), показываем что чат закрыт
        if contacts_purchased:
            text += "\n\n🔒 **Чат закрыт** - контакты переданы.\n\n"
            text += "ℹ️ Вы сможете оценить исполнителя после завершения срока объявления."
            kbc = KeyboardCollection()
            builder = InlineKeyboardBuilder()
            builder.add(kbc._inline(button_text="◀️ К откликам", 
                                   callback_data=f"view_responses_{abs_id}"))
            builder.adjust(1)
            
            # Показываем с фото если есть
            if worker.profile_photo:
                try:
                    from aiogram.types import FSInputFile
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo=FSInputFile(worker.profile_photo),
                        caption=text,
                        reply_markup=builder.as_markup(),
                        parse_mode='Markdown'
                    )
                except Exception:
                    # Если фото не загрузилось, показываем текстом
                    await callback.message.edit_text(
                        text=text,
                        reply_markup=builder.as_markup(),
                        parse_mode='Markdown'
                    )
            else:
                await callback.message.edit_text(
                    text=text,
                    reply_markup=builder.as_markup(),
                    parse_mode='Markdown'
                )
        else:
            # Чат активен - показываем обычные кнопки
            kbc = KeyboardCollection()
            
            # Показываем с фото если есть
            if worker.profile_photo:
                try:
                    from aiogram.types import FSInputFile
                    await callback.message.delete()
                    await callback.message.answer_photo(
                        photo=FSInputFile(worker.profile_photo),
                        caption=text,
                        reply_markup=kbc.anonymous_chat_customer_buttons(
                            worker_id=worker_id,
                            abs_id=abs_id,
                            contact_requested=contact_requested,
                            contact_sent=contacts_sent,
                            contacts_purchased=contacts_purchased
                        ),
                        parse_mode='Markdown'
                    )
                except Exception:
                    # Если фото не загрузилось, показываем текстом
                    await callback.message.edit_text(
                        text=text,
                        reply_markup=kbc.anonymous_chat_customer_buttons(
                            worker_id=worker_id,
                            abs_id=abs_id,
                            contact_requested=contact_requested,
                            contact_sent=contacts_sent,
                            contacts_purchased=contacts_purchased
                        ),
                        parse_mode='Markdown'
                    )
            else:
                await callback.message.edit_text(
                    text=text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=contacts_sent,
                        contact_sent=contacts_sent,
                        contacts_purchased=contacts_purchased
                    ),
                    parse_mode='Markdown'
                )
        
        await state.update_data(current_chat_abs_id=abs_id, current_chat_worker_id=worker_id)
        await state.set_state(CustomerStates.customer_anonymous_chat)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in view_response_by_customer: {e}")
        await callback.answer("❌ Произошла ошибка при просмотре отклика", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('reject_customer_response_'))
async def reject_customer_response_confirm(callback: CallbackQuery, state: FSMContext):
    """Показывает подтверждение отклонения отклика заказчиком"""
    try:
        # reject_customer_response_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])
        
        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return
        
        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement or advertisement.customer_id != customer.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        # Проверяем, что отклик существует
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return
        
        # Проверяем, что контакты еще не переданы
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if contact_exchange and contact_exchange.contacts_sent:
            await callback.answer("❌ Нельзя отклонить отклик после передачи контактов", show_alert=True)
            return
        
        # Показываем подтверждение
        confirmation_text = f"⚠️ **Подтверждение отклонения отклика**\n\n"
        confirmation_text += f"Вы действительно хотите отклонить отклик исполнителя на объявление #{abs_id}?\n\n"
        confirmation_text += f"**Последствия:**\n"
        confirmation_text += f"✅ Исполнитель получит уведомление об отклонении\n"
        confirmation_text += f"✅ Активность исполнителя НЕ изменится\n"
        confirmation_text += f"✅ Отклик будет удален из списка\n\n"
        confirmation_text += f"Нажмите «Подтвердить», если согласны."
        
        # Создаем клавиатуру подтверждения
        from app.keyboards import KeyboardCollection
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        kbc = KeyboardCollection()
        builder = InlineKeyboardBuilder()
        
        builder.add(kbc._inline("✅ Подтвердить", f"confirm_reject_customer_response_{worker_id}_{abs_id}"))
        builder.add(kbc._inline("❌ Отмена", f"view_response_{worker_id}_{abs_id}"))
        builder.adjust(1)
        
        await safe_edit_or_send(
            callback=callback,
            text=confirmation_text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in reject_customer_response_confirm: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_reject_customer_response_'))
async def confirm_reject_customer_response(callback: CallbackQuery, state: FSMContext):
    """Подтвержденное отклонение отклика заказчиком (НЕ влияет на активность исполнителя)"""
    try:
        # confirm_reject_customer_response_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[4])
        abs_id = int(parts[5])
        
        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return
        
        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement or advertisement.customer_id != customer.id:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        # Проверяем, что отклик существует
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return
        
        # Проверяем, что контакты еще не переданы
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        if contact_exchange and contact_exchange.contacts_sent:
            await callback.answer("❌ Нельзя отклонить отклик после передачи контактов", show_alert=True)
            return
        
        # Удаляем отклик
        await response.delete()
        
        # Удаляем связанные записи
        if contact_exchange:
            await contact_exchange.delete()
        
        # ВАЖНО: НЕ записываем в worker_response_cancellations
        # НЕ снижаем активность исполнителя
        # Это отклонение заказчиком, не отмена исполнителем        
        # Отправляем уведомление исполнителю
        from loaders import bot
        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=f"📨 Заказчик отклонил ваш отклик на объявление #{abs_id}\n\n"
                     f"Это не влияет на вашу активность."
            )
        except Exception as e:
            logger.error(f"Error sending rejection notification to worker {worker.tg_id}: {e}")
        
        # Возвращаемся к списку откликов
        kbc = KeyboardCollection()
        await callback.message.edit_text(
            text="✅ Отклик отклонен\n\nВы вернулись к списку откликов",
            reply_markup=kbc.menu_btn()
        )
        await state.set_state(CustomerStates.customer_menu)
        
    except Exception as e:
        logger.error(f"Error in reject_customer_response: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('reply_in_chat_'))
async def reply_in_chat(callback: CallbackQuery, state: FSMContext):
    """Заказчик начинает отвечать в чате"""
    try:
        # reply_in_chat_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        worker_id = int(parts[3])
        abs_id = int(parts[4])
        
        print(f"[REPLY_CHAT] Customer {callback.from_user.id} wants to reply in chat")
        logger.info(f"[REPLY_CHAT] Customer wants to reply in chat")
        
        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        worker = await Worker.get_worker(id=worker_id)
        
        if not customer or not worker:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, не закрыт ли чат (только если контакты куплены)
        response = await WorkersAndAbs.get_by_worker_and_abs(worker_id, abs_id)
        if not response:
            await callback.answer("❌ Отклик не найден", show_alert=True)
            return
        
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        print(f"[DEBUG] contact_exchange: {contact_exchange}")
        if contact_exchange:
            print(f"[DEBUG] contacts_purchased: {contact_exchange.contacts_purchased}")
            if contact_exchange.contacts_purchased:
                await callback.answer("❌ Чат закрыт - контакты переданы", show_alert=True)
                return
        else:
            print(f"[DEBUG] No contact_exchange record found - chat is open")
        
        # Переводим заказчика в режим чата
        await state.update_data(current_chat_abs_id=abs_id, current_chat_worker_id=worker_id)
        await state.set_state(CustomerStates.customer_anonymous_chat)
        
        text = f"💬 **Чат с исполнителем**\n\n"
        text += f"📋 Объявление: #{abs_id}\n"
        text += f"👤 Исполнитель: {worker.public_id or f'ID#{worker.id}'}\n\n"
        text += f"Напишите сообщение исполнителю:"
        
        # Безопасное редактирование (может быть фото)
        await safe_edit_or_send(
            callback=callback,
            text=text,
            parse_mode='Markdown'
        )
        
        await callback.answer("💬 Напишите сообщение исполнителю")
        
    except Exception as e:
        logger.error(f"Error in reply_in_chat: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

# Старый handler для apply-it-first_ удален - теперь используются новые кнопки respond_to_ad_
@router.callback_query(lambda c: c.data.startswith('respond_to_ad_'))
async def initiate_response(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Откликнуться'"""
    print(f"[RESPONSE] MAIN HANDLER TRIGGERED! Data: {callback.data}")
    logger.info(f"[RESPONSE] MAIN HANDLER TRIGGERED! Data: {callback.data}")
    current_state = await state.get_state()
    logger.info(f"[RESPONSE] Current state: {current_state}")
    try:
        abs_id = int(callback.data.split('_')[3])
        logger.info(f"[RESPONSE] Parsed abs_id: {abs_id}")
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        # Проверяем, не откликался ли уже
        existing_response = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
        if existing_response:
            for response in existing_response:
                if response.worker_id == worker.id:
                    await callback.answer("❌ Вы уже откликнулись на это объявление", show_alert=True)
                    return
        
        # Показываем правила чата
        kbc = KeyboardCollection()
        await state.update_data(pending_response_abs_id=abs_id)
        await state.set_state(WorkStates.worker_response_chat_rules)
        
        await callback.message.edit_text(
            text=CHAT_RULES_TEXT,
            reply_markup=kbc.chat_rules_confirmation(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in initiate_response: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "confirm_chat_rules", StateFilter(WorkStates.worker_response_chat_rules))
async def confirm_rules(callback: CallbackQuery, state: FSMContext):
    """Подтверждение правил чата"""
    try:
        data = await state.get_data()
        abs_id = data.get('pending_response_abs_id')
        
        kbc = KeyboardCollection()
        await callback.message.edit_text(
            text="📝 **Выберите тип отклика:**\n\n"
                 "• Напишите сообщение, чтобы представиться\n"
                 "• Или откликнитесь без сообщения",
            reply_markup=kbc.response_type_choice(abs_id=abs_id),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in confirm_rules: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_response")
async def cancel_response(callback: CallbackQuery, state: FSMContext):
    """Отмена отклика"""
    kbc = KeyboardCollection()
    await state.set_state(WorkStates.worker_menu)
    await callback.message.edit_text(
        text="❌ Отклик отменен",
        reply_markup=kbc.menu()
    )


# ========== 2. ОТКЛИК БЕЗ ТЕКСТА ==========

@router.callback_query(lambda c: c.data.startswith('response_without_text_'))
async def response_without_text(callback: CallbackQuery, state: FSMContext):
    """Отклик без текста"""
    try:
        abs_id = int(callback.data.split('_')[3])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        advertisement = await Abs.get_one(id=abs_id)
        
        if not advertisement:
            await callback.answer("❌ Объявление не найдено", show_alert=True)
            return
        
        # Проверяем активность исполнителя
        from app.data.database.models import WorkerDailyResponses
        from datetime import date
        
        # Проверяем, что у исполнителя есть поле activity_level
        if not hasattr(worker, 'activity_level') or worker.activity_level is None:
            worker.activity_level = 100  # Значение по умолчанию
        
        today = date.today().isoformat()
        responses_today = await WorkerDailyResponses.get_responses_count(worker.id, today)
        
        # Проверяем возможность отклика с fallback
        if not hasattr(worker, 'can_make_response'):
            # Fallback логика
            if worker.activity_level >= 74:
                can_respond = True
            elif worker.activity_level >= 48:
                can_respond = responses_today < 3
            elif worker.activity_level >= 9:
                can_respond = responses_today < 1
            else:
                can_respond = False
        else:
            can_respond = worker.can_make_response(responses_today)
        
        if not can_respond:
            # Получаем информацию об активности с fallback
            if not hasattr(worker, 'get_responses_limit_per_day'):
                if worker.activity_level >= 74:
                    limit = -1
                elif worker.activity_level >= 48:
                    limit = 3
                elif worker.activity_level >= 9:
                    limit = 1
                else:
                    limit = 0
            else:
                limit = worker.get_responses_limit_per_day()
            
            if not hasattr(worker, 'get_activity_zone'):
                if worker.activity_level >= 74:
                    zone_emoji, zone_message = "🟢", "Все в порядке, доступ полный"
                elif worker.activity_level >= 48:
                    zone_emoji, zone_message = "🟡", "Ваша активность снижается, ограничения: можно откликнуться только на 3 заказа в день"
                elif worker.activity_level >= 9:
                    zone_emoji, zone_message = "🟠", "Ограничения: можно откликнуться только на 1 заказ в день"
                else:
                    zone_emoji, zone_message = "🔴", "Блокировка откликов: Ваш уровень активности слишком низкий. Чтобы продолжить работу, восстановите активность!"
            else:
                zone_emoji, zone_message = worker.get_activity_zone()
            
            kbc = KeyboardCollection()
            if limit == 0:
                error_text = f"{zone_emoji} {zone_message}"
            else:
                error_text = f"{zone_emoji} {zone_message}\n\nИспользовано откликов сегодня: {responses_today}/{limit}"
            
            await state.set_state(WorkStates.worker_menu)
            await callback.message.edit_text(
                text=error_text,
                reply_markup=kbc.menu()
            )
            return
        
        customer = await Customer.get_customer(id=advertisement.customer_id)
        
        # Увеличиваем счетчик откликов за день
        await WorkerDailyResponses.increment_responses_count(worker.id, today)
        
        # Создаем отклик в БД
        worker_and_abs = WorkersAndAbs(
            worker_id=worker.id,
            abs_id=abs_id
        )
        await worker_and_abs.save()
        
        # Обновляем с сообщением
        await worker_and_abs.update(
            worker_messages=["Исполнитель откликнулся без сообщения"],
            applyed=True
        )
        
        # Формируем уведомление с профилем исполнителя
        notification_text = f"📨 **Новый отклик на ваше объявление!**\n\n"
        notification_text += f"📋 Объявление: #{abs_id}\n\n"
        
        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 **ID:** {worker.public_id or f'#{worker.id}'} {worker_name}\n"
        
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
        
        notification_text += "💬 Исполнитель откликнулся без сообщения."
        
        # Отправляем уведомление заказчику с кнопками для взаимодействия
        kbc = KeyboardCollection()
        await send_with_worker_photo(
            chat_id=customer.tg_id,
            worker=worker,
            text=notification_text,
            reply_markup=kbc.anonymous_chat_customer_buttons(
                worker_id=worker.id,
                abs_id=abs_id,
                contact_requested=False,
                contact_sent=False,
                contacts_purchased=False
            ),
            parse_mode='Markdown'
        )
        
        # Подтверждение исполнителю
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await callback.message.edit_text(
            text="✅ **Ваш отклик отправлен!**\n\n"
                 "Заказчик получил уведомление о вашем отклике.\n"
                 "Когда он ответит, вы получите уведомление.",
            reply_markup=kbc.menu(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in response_without_text: {e}")
        await callback.answer("❌ Произошла ошибка при отправке отклика", show_alert=True)


# ========== 3. ОТКЛИК С ТЕКСТОМ ==========

@router.callback_query(lambda c: c.data.startswith('response_with_text_'))
async def response_with_text_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос текста отклика"""
    try:
        abs_id = int(callback.data.split('_')[3])
        
        await state.update_data(response_abs_id=abs_id)
        await state.set_state(WorkStates.worker_response_write_text)
        
        await callback.message.edit_text(
            text="✍️ **Напишите ваше сообщение заказчику:**\n\n"
                 "⚠️ Помните о правилах чата!\n"
                 "🚫 Нельзя передавать контакты напрямую",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in response_with_text_prompt: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(F.text, StateFilter(WorkStates.worker_response_write_text))
async def process_response_text(message: Message, state: FSMContext):
    """Обработка текста отклика"""
    try:
        # Проверяем сообщение на контакты через усиленный фильтр
        is_valid, error_message = check_message_for_contacts(message.text)
        
        if not is_valid:
            kbc = KeyboardCollection()
            await message.answer(
                text=f"🚫 **Сообщение заблокировано!**\n\n{error_message}\n\n"
                     "Попробуйте еще раз или откликнитесь без текста.",
                reply_markup=kbc.menu(),
                parse_mode='Markdown'
            )
            return
        
        # Проверка длины сообщения
        if len(message.text) > 500:
            await message.answer(
                text="❌ Сообщение слишком длинное. Максимум 500 символов.\n"
                     f"Ваше сообщение: {len(message.text)} символов"
            )
            return
        
        data = await state.get_data()
        abs_id = data.get('response_abs_id')
        
        worker = await Worker.get_worker(tg_id=message.from_user.id)
        
        if not worker:
            await message.answer("❌ Исполнитель не найден")
            await state.clear()
            return
        
        advertisement = await Abs.get_one(id=abs_id)
        
        if not advertisement:
            await message.answer("❌ Объявление не найдено")
            await state.clear()
            return
        
        # Проверяем активность исполнителя
        from app.data.database.models import WorkerDailyResponses
        from datetime import date
        
        # Проверяем, что у исполнителя есть поле activity_level
        if not hasattr(worker, 'activity_level') or worker.activity_level is None:
            worker.activity_level = 100  # Значение по умолчанию
        
        today = date.today().isoformat()
        responses_today = await WorkerDailyResponses.get_responses_count(worker.id, today)
        
        # Проверяем возможность отклика с fallback
        if not hasattr(worker, 'can_make_response'):
            # Fallback логика
            if worker.activity_level >= 74:
                can_respond = True
            elif worker.activity_level >= 48:
                can_respond = responses_today < 3
            elif worker.activity_level >= 9:
                can_respond = responses_today < 1
            else:
                can_respond = False
        else:
            can_respond = worker.can_make_response(responses_today)
        
        if not can_respond:
            # Получаем информацию об активности с fallback
            if not hasattr(worker, 'get_responses_limit_per_day'):
                if worker.activity_level >= 74:
                    limit = -1
                elif worker.activity_level >= 48:
                    limit = 3
                elif worker.activity_level >= 9:
                    limit = 1
                else:
                    limit = 0
            else:
                limit = worker.get_responses_limit_per_day()
            
            if not hasattr(worker, 'get_activity_zone'):
                if worker.activity_level >= 74:
                    zone_emoji, zone_message = "🟢", "Все в порядке, доступ полный"
                elif worker.activity_level >= 48:
                    zone_emoji, zone_message = "🟡", "Ваша активность снижается, ограничения: можно откликнуться только на 3 заказа в день"
                elif worker.activity_level >= 9:
                    zone_emoji, zone_message = "🟠", "Ограничения: можно откликнуться только на 1 заказ в день"
                else:
                    zone_emoji, zone_message = "🔴", "Блокировка откликов: Ваш уровень активности слишком низкий. Чтобы продолжить работу, восстановите активность!"
            else:
                zone_emoji, zone_message = worker.get_activity_zone()
            
            kbc = KeyboardCollection()
            if limit == 0:
                error_text = f"{zone_emoji} {zone_message}"
            else:
                error_text = f"{zone_emoji} {zone_message}\n\nИспользовано откликов сегодня: {responses_today}/{limit}"
            
            await state.set_state(WorkStates.worker_menu)
            await message.answer(
                text=error_text,
                reply_markup=kbc.menu()
            )
            return
        
        customer = await Customer.get_customer(id=advertisement.customer_id)
        
        # Увеличиваем счетчик откликов за день
        await WorkerDailyResponses.increment_responses_count(worker.id, today)
        
        # Создаем отклик в БД
        worker_and_abs = WorkersAndAbs(
            worker_id=worker.id,
            abs_id=abs_id
        )
        await worker_and_abs.save()
        
        # Обновляем с сообщением
        await worker_and_abs.update(
            worker_messages=[message.text],
            applyed=True
        )
        
        # Формируем уведомление с профилем исполнителя
        notification_text = f"📨 **Новый отклик на ваше объявление!**\n\n"
        notification_text += f"📋 Объявление: #{abs_id}\n\n"
        
        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        notification_text += f"👤 **ID:** {worker.public_id or f'#{worker.id}'} {worker_name}\n"
        
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
        
        # Отправляем уведомление заказчику с кнопками для взаимодействия
        kbc = KeyboardCollection()
        await send_with_worker_photo(
            chat_id=customer.tg_id,
            worker=worker,
            text=notification_text,
            reply_markup=kbc.anonymous_chat_customer_buttons(
                worker_id=worker.id,
                abs_id=abs_id,
                contact_requested=False,
                contact_sent=False,
                contacts_purchased=False
            ),
            parse_mode='Markdown'
        )
        
        # Подтверждение исполнителю
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await message.answer(
            text="✅ **Ваш отклик отправлен!**\n\n"
                 "Заказчик получил ваше сообщение.\n"
                 "Когда он ответит, вы получите уведомление.",
            reply_markup=kbc.menu(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in process_response_text: {e}")
        await message.answer("❌ Произошла ошибка при отправке отклика")
        await state.clear()


# ========== 4. ОТКЛОНЕНИЕ И ЖАЛОБА ==========

@router.callback_query(lambda c: c.data.startswith('decline_ad_'))
async def decline_ad(callback: CallbackQuery, state: FSMContext):
    """Отклонение объявления"""
    try:
        abs_id = int(callback.data.split('_')[2])
        
        # Добавляем объявление в список "не показывать"
        from app.data.database.models import WorkerAndBadResponse
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        
        bad_response = WorkerAndBadResponse(worker_id=worker.id, abs_id=abs_id)
        await bad_response.save()
        
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await callback.message.edit_text(
            text="✅ Объявление скрыто и больше не будет показываться",
            reply_markup=kbc.menu()
        )
        
    except Exception as e:
        logger.error(f"Error in decline_ad: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "back_to_ads")
async def back_to_ads(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню исполнителя"""
    # Импортируем функцию menu_worker
    from app.handlers.worker import menu_worker
    # Вызываем функцию меню исполнителя напрямую
    await menu_worker(callback, state)


@router.callback_query(lambda c: c.data.startswith('report_ad_'))
async def report_ad(callback: CallbackQuery, state: FSMContext):
    """Жалоба на объявление"""
    try:
        abs_id = int(callback.data.split('_')[2])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        
        from app.data.database.models import WorkerAndReport
        
        # Проверяем, не отправлял ли уже жалобу
        existing_report = await WorkerAndReport.get_by_worker(worker_id=worker.id)
        if existing_report:
            for report in existing_report:
                if report.abs_id == abs_id:
                    await callback.answer("❌ Вы уже отправили жалобу на это объявление", show_alert=True)
                    return
        
        # Создаем жалобу
        report = WorkerAndReport(worker_id=worker.id, abs_id=abs_id)
        await report.save()
        
        # Уведомляем админов
        import config
        await bot.send_message(
            chat_id=config.REPORT_LOG,
            text=f"⚠️ Получена жалоба на объявление #{abs_id}\n"
                 f"От исполнителя: {worker.tg_id} ({worker.public_id})"
        )
        
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await callback.message.edit_text(
            text="✅ Жалоба отправлена администрации.\n"
                 "Мы проверим объявление в ближайшее время.",
            reply_markup=kbc.menu()
        )
        
    except Exception as e:
        logger.error(f"Error in report_ad: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

