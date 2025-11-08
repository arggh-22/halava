"""
Handlers для работы с откликами исполнителя:
- Инициация отклика
- Анонимный чат
- Запрос контактов
- Покупка жетонов
"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.states import WorkStates, CustomerStates
from app.keyboards import KeyboardCollection
from app.data.database.models import Worker, Customer, Abs, WorkersAndAbs, ContactExchange, City
from loaders import bot
from app.untils.contact_filter import check_message_for_contacts
from app.untils.message_utils import safe_edit_message

logger = logging.getLogger(__name__)
router = Router()

# Логируем при импорте модуля
print("[WORKER_RESPONSES] Module imported!")
logger.info("[WORKER_RESPONSES] Router initialized!")
print(f"[WORKER_RESPONSES] Router object: {router}")

# Текст правил чата
CHAT_RULES_TEXT = """
🚫 Внимание!

В чате запрещено передавать любые свои контакты: 📞 номера, ✉️ email, 🔗 ссылки, а также использовать латинские буквы, фото и видео.
"""


# """
# ⚠️ <b>ВАЖНО: Правила Анонимного Чата</b>
#
# 🚫 <b>СТРОГО ЗАПРЕЩЕНО:</b>
# • Передавать номера телефонов (в любом виде)
# • Отправлять email адреса
# • Делиться ссылками на соцсети/мессенджеры
# • Использовать латинские буквы
# • Отправлять медиафайлы (фото, видео, документы)
# • Пытаться обойти фильтр (разбивать контакты)
#
# ✅ <b>ДЛЯ ОБМЕНА КОНТАКТАМИ:</b>
# Используйте кнопку <b>"📞 Запросить контакт"</b>
#
# ⚠️ <b>При нарушении:</b>
# Сообщение будет заблокировано, возможна блокировка аккаунта!
#
# <b>Вы ознакомились с правилами и готовы продолжить?</b>
# """


# Универсальная функция для безопасного редактирования сообщений
async def safe_edit_or_send(callback: CallbackQuery, text: str, reply_markup=None, parse_mode: str = 'HTML'):
    """Пытается отредактировать сообщение, если не получается - удаляет и отправляет новое"""
    try:
        if callback.message.photo:
            # Если сообщение содержит фото, редактируем подпись
            await callback.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                # parse_mode=parse_mode
            )
        else:
            # Если сообщение текстовое, редактируем текст
            await safe_edit_message(
                callback=callback,
                text=text,
                reply_markup=reply_markup,
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
async def send_with_worker_photo(chat_id, worker, text: str, reply_markup=None, parse_mode: str = 'HTML'):
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
                # parse_mode=parse_mode
            )
        except Exception:
            # Если фото не загрузилось, отправляем текстом
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                # parse_mode=parse_mode
            )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            # parse_mode=parse_mode
        )


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

        print(
            f"[CUSTOMER_VIEW] Customer {callback.from_user.id} viewing response: worker_id={worker_id}, abs_id={abs_id}")
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

        # Получаем количество сообщений от исполнителя
        worker_messages_list = []
        if response.worker_messages:
            worker_messages_list = [
                msg for msg in response.worker_messages
                if msg and msg.strip() and msg != "Исполнитель не отправил сообщение"
            ]

        # Обновляем счетчик прочитанных сообщений для заказчика
        # Заказчик видел все сообщения от исполнителя
        last_read_by_customer = len(worker_messages_list)
        if response.last_read_by_customer != last_read_by_customer:
            await response.update(last_read_by_customer=last_read_by_customer)

        # Обновляем счетчик последнего сообщения исполнителя
        last_message_by_worker = len(worker_messages_list)
        if response.last_message_by_worker != last_message_by_worker:
            await response.update(last_message_by_worker=last_message_by_worker)

        # Формируем текст с информацией об исполнителе
        text = f"📋 <b>Отклик на объявление #{abs_id}</b>\n\n"

        # ID и имя
        worker_name = worker.profile_name or worker.tg_name
        text += f"👤 <b>ID:</b> {worker.id} {worker_name}\n"

        # Рейтинг
        if worker.count_ratings > 0:
            text += f"⭐ <b>Рейтинг:</b> {worker.stars / worker.count_ratings:.1f}/5 ({worker.count_ratings} оценок)\n"
        else:
            text += f"⭐ <b>Рейтинг:</b> Нет оценок\n"

        # Статус верификации и регистрации
        status_string = await get_worker_status_string(worker.id)
        text += f"📋 <b>Статус:</b> {status_string}\n"

        # Выполнено заказов
        text += f"📦 <b>Выполнено заказов:</b> {worker.order_count}\n"

        # Дата регистрации
        text += f"📅 <b>Зарегистрирован:</b> {worker.registration_data}\n\n"

        # Показываем историю переписки
        from app.handlers.anonymous_chat import format_chat_history_for_display
        chat_history = await format_chat_history_for_display("customer", abs_id, worker, customer)

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
                    if len(truncated_history) + len(line) + 1 <= remaining_chars:
                        truncated_history = line + '\n' + truncated_history
                    else:
                        break

                if truncated_history:
                    text += "📝 <b>История переписки:</b>\n\n"
                    text += truncated_history
                    text += f"\n... (показаны последние сообщения)\n"
            else:
                text += "📝 <b>История переписки:</b>\n\n"
                text += chat_history
                text += "\n"

        # Проверяем статус контактов и чата
        contact_exchange = await ContactExchange.get_by_worker_and_abs(worker_id, abs_id)
        # contact_requested = True если исполнитель запросил контакты (есть ContactExchange)
        contact_requested = contact_exchange is not None
        # contacts_sent = True если заказчик подтвердил передачу контактов
        contacts_sent = contact_exchange and contact_exchange.contacts_sent
        # contacts_purchased = True если контакты куплены/получены исполнителем
        contacts_purchased = contact_exchange and contact_exchange.contacts_purchased

        # Проверяем наличие портфолио у исполнителя
        has_portfolio = worker.portfolio_photo is not None and len(worker.portfolio_photo) > 0

        # Если контакты предложены/подтверждены, но еще не куплены, показываем статус
        if contacts_sent and not contacts_purchased:
            text += "\n✅ <b>Контакты переданы исполнителю!</b>\n\n"

        # Если контакты переданы (куплены), показываем что чат закрыт
        if contacts_purchased:
            text += "\n\n🔒 <b>Чат закрыт</b> - контакты переданы.\n\n"
            text += "ℹ️ Вы сможете оценить исполнителя после закрытия заказа (вручную или по истечении срока актуальности объявления)."
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
                        parse_mode='HTML'
                    )
                except Exception:
                    # Если фото не загрузилось, показываем текстом
                    from app.untils.message_utils import safe_edit_message
                    await safe_edit_message(
                        callback=callback,
                        text=text,
                        reply_markup=builder.as_markup(),
                    )
            else:
                from app.untils.message_utils import safe_edit_message
                await safe_edit_message(
                    callback=callback,
                    text=text,
                    reply_markup=builder.as_markup(),
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
                            contacts_purchased=contacts_purchased,
                            has_portfolio=has_portfolio
                        ),
                        parse_mode='HTML'
                    )
                except Exception:
                    # Если фото не загрузилось, показываем текстом
                    from app.untils.message_utils import safe_edit_message
                    await safe_edit_message(
                        callback=callback,
                        text=text,
                        reply_markup=kbc.anonymous_chat_customer_buttons(
                            worker_id=worker_id,
                            abs_id=abs_id,
                            contact_requested=contact_requested,
                            contact_sent=contacts_sent,
                            contacts_purchased=contacts_purchased,
                            has_portfolio=has_portfolio
                        ),
                    )
            else:
                from app.untils.message_utils import safe_edit_message
                await safe_edit_message(
                    callback=callback,
                    text=text,
                    reply_markup=kbc.anonymous_chat_customer_buttons(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        contact_requested=contact_requested,
                        contact_sent=contacts_sent,
                        contacts_purchased=contacts_purchased,
                        has_portfolio=has_portfolio
                    ),
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
        confirmation_text = f"⚠️ <b>Подтверждение отклонения отклика</b>\n\n"
        confirmation_text += f"Вы действительно хотите отклонить отклик исполнителя на объявление #{abs_id}?\n\n"
        confirmation_text += f"<b>Последствия:</b>\n"
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
            parse_mode='HTML'
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
        kbc = KeyboardCollection()

        from loaders import bot
        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=f"📨 Заказчик отклонил ваш отклик на объявление #{abs_id}\n\n"
                     f"Это не влияет на вашу активность.",
                reply_markup=kbc.worker_menu()
            )
        except Exception as e:
            logger.error(f"Error sending rejection notification to worker {worker.tg_id}: {e}")


        # Возвращаемся к списку откликов
        remaining_responses = await WorkersAndAbs.get_by_abs(abs_id)

        await callback.answer("✅ Отклик отклонен\n\nВы вернулись к списку откликов", show_alert=True)

        if remaining_responses:
            responses_data = []
            from app.handlers.anonymous_chat import get_response_status_indicator

            for resp_item in remaining_responses:
                worker_obj = await Worker.get_worker(id=resp_item.worker_id)
                if not worker_obj:
                    continue

                status_indicator = await get_response_status_indicator(resp_item, "customer")

                responses_data.append({
                    'worker_id': resp_item.worker_id,
                    'worker_public_id': f'ID#{worker_obj.id}',
                    'worker_name': worker_obj.profile_name or worker_obj.tg_name or f'ID#{worker_obj.id}',
                    'worker_stars': worker_obj.stars,
                    'worker_ratings': worker_obj.count_ratings,
                    'active': resp_item.applyed,
                    'status_indicator': status_indicator
                })

            # Формируем текст списка
            city_name = "Неизвестно"
            if advertisement and advertisement.city_id:
                city = await City.get_city(id=advertisement.city_id)
                if city:
                    city_name = city.city

            text = (
                f"📋 <b>Отклики на объявление #{abs_id}</b>\n"
                f"🏙️ Город: {city_name}\n"
                f"👥 Количество откликов: {len(responses_data)}\n\n"
                "Выберите отклик для просмотра:"
            )

            try:
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=responses_data,
                        abs_id=abs_id
                    ),
                    parse_mode='HTML'
                )
            except Exception:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.customer_responses_list_buttons(
                        responses_data=responses_data,
                        abs_id=abs_id
                    ),
                    parse_mode='HTML'
                )

            await state.set_state(CustomerStates.customer_view_responses)
        else:
            # Если откликов больше нет, возвращаем в меню заказчика
            from app.untils import help_defs
            await help_defs.send_customer_menu(callback, customer, state=state)

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

        text = f"💬 <b>Чат с исполнителем</b>\n\n"
        text += f"📋 Объявление: #{abs_id}\n"
        text += f"👤 Исполнитель: {worker.id}\n\n"
        text += f"Напишите сообщение исполнителю:"

        # Безопасное редактирование (может быть фото)
        await safe_edit_or_send(
            callback=callback,
            text=text,
            parse_mode='HTML'
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

        await callback.answer(CHAT_RULES_TEXT, show_alert=True)

        kbc = KeyboardCollection()
        await safe_edit_message(
            callback=callback,
            text="📝 <b>Выберите тип отклика:</b>\n\n"
                 "Вы можете отправить отклик с сообщением и вопросами или без сообщения.",
            reply_markup=kbc.response_type_choice(abs_id=abs_id)
        )

    except Exception as e:
        logger.error(f"Error in initiate_response: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# @router.callback_query(F.data == "confirm_chat_rules", StateFilter(WorkStates.worker_response_chat_rules))
# async def confirm_rules(callback: CallbackQuery, state: FSMContext):
#     """Подтверждение правил чата"""
#     try:
#         data = await state.get_data()
#         abs_id = data.get('pending_response_abs_id')
#
#         kbc = KeyboardCollection()
#         await safe_edit_message(
#             callback=callback,
#             text="📝 <b>Выберите тип отклика:</b>\n\n"
#                  "• Напишите сообщение, чтобы представиться\n"
#                  "• Или откликнитесь без сообщения",
#             reply_markup=kbc.response_type_choice(abs_id=abs_id)
#         )
#
#     except Exception as e:
#         logger.error(f"Error in confirm_rules: {e}")
#         await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_response")
async def cancel_response(callback: CallbackQuery, state: FSMContext):
    """Отмена отклика"""
    kbc = KeyboardCollection()
    await state.set_state(WorkStates.worker_menu)
    await safe_edit_message(
        callback=callback,
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
            await safe_edit_message(
                callback=callback,
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

        # Обновляем без сохранения служебного сообщения в истории чата
        # (это сообщение будет только в уведомлении заказчику)
        await worker_and_abs.update(
            applyed=True
        )

        # Формируем уведомление с профилем исполнителя
        notification_text = f"📨 <b>Новый отклик на ваше объявление!</b>\n\n"
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

        notification_text += "💬 Исполнитель откликнулся без сообщения."

        # Проверяем наличие портфолио у исполнителя
        has_portfolio = worker.portfolio_photo is not None and len(worker.portfolio_photo) > 0

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
                contacts_purchased=False,
                has_portfolio=has_portfolio
            ),
            parse_mode='HTML'
        )

        # Подтверждение исполнителю
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await safe_edit_message(
            callback=callback,
            text="✅ <b>Ваш отклик отправлен!</b>\n\n"
                 "Заказчик получил уведомление о вашем отклике.\n"
                 "Когда он ответит, вы получите уведомление.",
            reply_markup=kbc.menu()
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

        await safe_edit_message(
            callback=callback,
            text="✍️ <b>Напишите ваше сообщение заказчику:</b>\n\n"
                 "⚠️ Помните о правилах чата!\n"
                 "🚫 Нельзя передавать контакты напрямую"
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
                text=f"🚫 <b>Сообщение заблокировано!</b>\n\n{error_message}\n\n"
                     "Попробуйте еще раз или откликнитесь без текста.",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
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

        # Добавляем временную метку для сообщения
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_timestamps = [{"sender": "worker", "timestamp": current_timestamp}]

        # Обновляем с сообщением и временной меткой
        await worker_and_abs.update(
            worker_messages=[message.text],
            applyed=True,
            message_timestamps=message_timestamps
        )

        # Формируем уведомление с профилем исполнителя
        notification_text = f"📨 <b>Новый отклик на ваше объявление!</b>\n\n"
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

        notification_text += f"💬 <b>Сообщение:</b>\n{message.text}"

        # Проверяем наличие портфолио у исполнителя
        has_portfolio = worker.portfolio_photo is not None and len(worker.portfolio_photo) > 0

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
                contacts_purchased=False,
                has_portfolio=has_portfolio
            ),
            parse_mode='HTML'
        )

        # Подтверждение исполнителю
        kbc = KeyboardCollection()
        await state.set_state(WorkStates.worker_menu)
        await message.answer(
            text="✅ <b>Ваш отклик отправлен!</b>\n\n"
                 "Заказчик получил ваше сообщение.\n"
                 "Когда он ответит, вы получите уведомление.",
            reply_markup=kbc.menu(),
            parse_mode='HTML'
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

        # Показываем всплывающее окно с подтверждением
        await callback.answer("✅ Объявление успешно скрыто и больше не будет отображаться!", show_alert=True)

        # Возвращаемся в раздел объявлений исполнителя
        from app.handlers.worker import abs_in_city
        await abs_in_city(callback, state)

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
    """Жалоба на объявление - единая система"""
    try:
        abs_id = int(callback.data.split('_')[2])
        worker = await Worker.get_worker(tg_id=callback.from_user.id)

        from app.data.database.models import WorkerAndReport, Abs, Customer
        from app.untils import help_defs
        from app.keyboards import KeyboardCollection
        from aiogram.types import FSInputFile
        import config

        # Проверяем, не отправлял ли уже жалобу
        existing_report = await WorkerAndReport.get_by_worker(worker_id=worker.id)
        if existing_report:
            for report in existing_report:
                if report.abs_id == abs_id:
                    await callback.answer("❌ Вы уже отправили жалобу на это объявление", show_alert=True)
                    return

        # Получаем объявление
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement:
            await callback.answer("❌ Объявление больше не актуально", show_alert=True)
            return

        # Создаем жалобу
        report = WorkerAndReport(worker_id=worker.id, abs_id=abs_id)
        await report.save()

        # Получаем информацию о заказчике
        customer = await Customer.get_customer(id=advertisement.customer_id)

        # Формируем детальный текст жалобы
        text = f'Заказчик ID {customer.tg_id}\nОбъявление #{advertisement.id}\n\n' + help_defs.read_text_file(
            advertisement.text_path)

        kbc = KeyboardCollection()

        # Отправляем детальную информацию админам с кнопками управления
        if advertisement.photo_path and isinstance(advertisement.photo_path, dict) and '0' in advertisement.photo_path:
            # photo_path может быть словарем с несколькими фотографиями
            first_photo = advertisement.photo_path['0']
            if 'https' in first_photo:
                await bot.send_photo(chat_id=config.REPORT_LOG,
                                     photo=first_photo,
                                     caption=text,
                                     reply_markup=kbc.block_abs(abs_id),
                                     protect_content=False)
            else:
                await bot.send_photo(chat_id=config.REPORT_LOG,
                                     photo=FSInputFile(first_photo),
                                     caption=text,
                                     reply_markup=kbc.block_abs(abs_id),
                                     protect_content=False)
        else:
            await bot.send_message(chat_id=config.REPORT_LOG,
                                   text=text,
                                   reply_markup=kbc.block_abs(abs_id),
                                   protect_content=False)

        # Показываем всплывающее окно с подтверждением
        await callback.answer("✅ Ваша жалоба успешно отправлена!", show_alert=True)

        # Возвращаемся в раздел объявлений
        from app.handlers.worker import menu_worker
        await menu_worker(callback, state)

    except Exception as e:
        logger.error(f"Error in report_ad: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
