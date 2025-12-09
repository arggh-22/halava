import logging
import asyncio
import os
import shutil
from datetime import datetime, timedelta

from pydantic_core import ValidationError
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import StateFilter
from aiogram.types import (
    CallbackQuery, Message, FSInputFile, LabeledPrice, PreCheckoutQuery, InputMediaPhoto, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

import config
from app.data.database.models import (
    Customer, Worker, City, Banned, WorkType, Abs, WorkersAndAbs, Admin, BannedAbs, WorkerAndBadResponse,
    WorkerAndReport, ContactExchange
)
from app.keyboards import KeyboardCollection
from app.states import UserStates, CustomerStates, BannedStates, WorkStates
from app.untils import help_defs, checks, yandex_ocr
from app.untils.customer_proces import ban_task, same_task, close_task
from app.untils.contact_filter import ContactFilter
from loaders import bot
from aiogram.fsm.storage.base import StorageKey

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


async def check_advertisement_ocr_text(text: str) -> tuple[bool, bool]:
    """
    Проверяет OCR текст для объявлений заказчика.
    Запрещает: латиницу, номер телефона, PHONE_PATTERNS, EMAIL_PATTERNS, LINK_PATTERNS, 
               MESSENGER_PATTERNS, BROKEN_CONTACT_PATTERNS, FORBIDDEN_WORDS, LATIN_PATTERN
    Запрещает стоп-слова (fool_check)
    Разрешает: буквы (кириллицу)
    
    Returns:
        Tuple[bool, bool]: (has_stop_words, has_other_violations)
            - has_stop_words: True если найдены стоп-слова (требуется блокировка)
            - has_other_violations: True если найдены другие нарушения (требуется предупреждение)
    """
    import re
    
    if not text:
        return False, False
    
    # Проверка на стоп-слова (fool_check) - это блокировка
    if await checks.fool_check(text=text):
        return True, False
    
    has_violations = False
    
    # Проверка на латиницу (LATIN_PATTERN)
    if re.search(ContactFilter.LATIN_PATTERN, text):
        has_violations = True
    
    # Проверка на PHONE_PATTERNS
    for pattern in ContactFilter.PHONE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            has_violations = True
            break
    
    # Проверка на EMAIL_PATTERNS
    if not has_violations:
        for pattern in ContactFilter.EMAIL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                has_violations = True
                break
    
    # Проверка на LINK_PATTERNS
    if not has_violations:
        for pattern in ContactFilter.LINK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                has_violations = True
                break
    
    # Проверка на MESSENGER_PATTERNS
    if not has_violations:
        for pattern in ContactFilter.MESSENGER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                has_violations = True
                break
    
    # Проверка на BROKEN_CONTACT_PATTERNS
    if not has_violations:
        for pattern in ContactFilter.BROKEN_CONTACT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                has_violations = True
                break
    
    # Проверка на FORBIDDEN_WORDS
    if not has_violations:
        text_lower = text.lower()
        for word in ContactFilter.FORBIDDEN_WORDS:
            if word in text_lower:
                has_violations = True
                break
    
    return False, has_violations


@router.callback_query(F.data == "registration_customer", UserStates.registration_end)
async def registration_customer_from_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для регистрации заказчика из стартового меню"""
    logger.debug(f'registration_customer_from_start...')

    # Переходим к выбору города для заказчика
    await state.set_state(CustomerStates.registration_enter_city)
    await choose_city_start(callback, state)


async def choose_city_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало выбора города для заказчика"""
    logger.debug(f'choose_city_start...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    username = str(state_data.get('username'))
    await state.update_data(username=str(username))

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.answer(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities} городов',
        reply_markup=kbc.choose_obj(
            id_now=id_now,
            ids=city_ids,
            names=city_names,
            btn_next=btn_next,
            btn_back=False
        )
    )
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == "registration_customer", UserStates.registration_enter_city)
async def choose_city_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_city_main...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    username = str(state_data.get('username'))
    await state.set_state(CustomerStates.registration_enter_city)
    await state.update_data(username=str(username))

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.answer(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, CustomerStates.registration_enter_city)
async def choose_city_main(message: Message, state: FSMContext) -> None:
    logger.debug(f'choose_city_main...')
    kbc = KeyboardCollection()

    city_input = message.text
    logger.debug(f'city_input... {city_input}')

    state_data = await state.get_data()

    # msg_id = int(state_data.get('msg_id'))

    cities = await City.get_all(sort=False)
    city_names = [city.city for city in cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    found_cities = []

    for idx in city_find:
        if idx < len(cities):
            found_cities.append(cities[idx])

    city_names = [city.city for city in found_cities]
    city_ids = [city.id for city in found_cities]

    msg = await message.answer(
        text=f'Результаты поиска по: {city_input}\n'
             f'Выберите город или напишите его текстом\n',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('go_'), CustomerStates.registration_enter_city)
async def choose_city_next(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f' choose_city_next...')
    kbc = KeyboardCollection()
    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)

    id_now = int(callback.data.split('_')[1])

    btn_next = True if len(city_names) > 5 + id_now else False
    btn_back = True if id_now >= 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)
    try:
        msg = await callback.message.answer(
            text=f'Выберите город или напишите его текстом\n\n'
                 f' Показано {id_now + len(city_names)} из {count_cities}',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back))
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.registration_enter_city)
async def choose_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_city_end...')
    kbc = KeyboardCollection()
    state_data = await state.get_data()
    username = str(state_data.get('username'))
    city_id = int(callback.data.split('_')[1])

    new_customer = Customer(
        id=None,
        tg_id=callback.message.chat.id,
        city_id=city_id,
        tg_name=username
    )
    await new_customer.save()

    await callback.message.answer(
        text='''

✅ <b>Размещаются запросы только на разовые услуги: </b>

— Анонимно; 
— Без номера телефона; 
— Без ссылок; 

🚫 <b>Запрещается предлагать: </b>

— Рекламу; 
— Вакансии; 
— Работу вахтой;''',
        reply_markup=kbc.menu_btn_reg(),
        parse_mode='HTML'
    )
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(F.data == 'menu', StateFilter(
    CustomerStates.customer_menu,
    CustomerStates.customer_check_abs,
    CustomerStates.customer_change_city))
async def customer_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_menu...')

    kbc = KeyboardCollection()

    tg_id = callback.message.chat.id

    customer = await Customer.get_customer(tg_id=tg_id)
    if customer is None:
        # Сразу переходим к регистрации без промежуточного сообщения
        if worker := await Worker.get_worker(tg_id=callback.message.chat.id):
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(worker.city_id[0]), username=str(worker.tg_name))
            # Сразу вызываем регистрацию
            await registration_customer_from_start(callback, state)
            return
        else:
            # Если нет данных исполнителя, переходим к обычной регистрации
            await state.set_state(UserStates.registration_end)
            await state.update_data(username=str(callback.from_user.username or callback.from_user.first_name or "Пользователь"))
            await registration_customer_from_start(callback, state)
            return

    if user_worker := await Worker.get_worker(tg_id=tg_id):
        if user_worker.active:
            await user_worker.update_active(active=False)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    # Send customer menu
    await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(F.data == 'customer_menu')
async def customer_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_menu...')

    kbc = KeyboardCollection()

    tg_id = callback.message.chat.id

    customer = await Customer.get_customer(tg_id=tg_id)

    if customer is None:
        # Сразу переходим к регистрации без промежуточного сообщения
        if worker := await Worker.get_worker(tg_id=callback.message.chat.id):
            logger.debug('go as worker')
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(worker.city_id[0]), username=str(worker.tg_name))
            # Сразу вызываем регистрацию
            await registration_customer_from_start(callback, state)
            return
        if admin := await Admin.get_by_tg_id(tg_id=callback.message.chat.id):
            logger.debug('go as admin')
            await state.set_state(UserStates.registration_end)
            await state.update_data(username=str(admin.tg_name))
            # Сразу вызываем регистрацию
            await registration_customer_from_start(callback, state)
            return
        # Если нет данных, переходим к обычной регистрации
        await state.set_state(UserStates.registration_end)
        await state.update_data(username=str(callback.from_user.username or callback.from_user.first_name or "Пользователь"))
        await registration_customer_from_start(callback, state)
        return

    # Проверяем, была ли смена роли
    role_changed = False
    if user_worker := await Worker.get_worker(tg_id=tg_id):
        if user_worker.active:
            await user_worker.update_active(active=False)
            role_changed = True

    # Send customer menu
    await help_defs.send_customer_menu(callback, customer, state)
    
    # Показываем alert при смене роли
    if role_changed:
        from app.data.database.models import UserNotificationSettings
        settings = await UserNotificationSettings.get_or_create(tg_id)
        
        if not settings.unified_notifications:
            await callback.answer(
                "ℹ️ Вы сменили роль на заказчика.\n\n"
                "Уведомления будут приходить только для этой роли.\n\n"
                "Вы можете изменить это в разделе \n«🔔 Уведомления».",
                show_alert=True
            )


@router.callback_query(F.data == 'buy_single_ad')
async def buy_single_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    """Покупка одного объявления при достижении лимита"""
    logger.debug(f'buy_single_advertisement...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    admins = await Admin.get_all()
    admin = admins[0]

    prices = [LabeledPrice(label=f"Дополнительное размещение", amount=int(admin.order_price * 100))]
    text = f"Количество размещений: 1"

    await state.set_state(CustomerStates.customer_buy_subscription)

    # РЕАЛЬНАЯ ПЛАТЕЖНАЯ СИСТЕМА
    try:
        await callback.message.answer_invoice(
            title=f"Дополнительное размещение",
            description=text,
            provider_token=config.PAYMENTS,
            currency="RUB",
            prices=prices,
            start_parameter="single-advertisement",
            payload="invoice-payload",
            reply_markup=kbc.customer_buy_order(),
            need_email=True,
            send_email_to_provider=True
        )
        await state.update_data(customer_id=str(customer.id),
                                order_price=admin.order_price)
    except TelegramBadRequest as e:
        logger.error(f"Payment provider error: {e}")
        # Обрабатываем ошибку недоступности платежного метода
        if "PAYMENT_PROVIDER_INVALID" in str(e):
            error_text = "❌ Платежный метод недоступен\n\n"
            error_text += "🚫 К сожалению, в вашей стране недоступны платежные методы Telegram.\n\n"
            error_text += "📞 Для получения помощи обратитесь в поддержку"

            await callback.answer(
                text=error_text,
                show_alert=True,
            )
        else:
            # Другие ошибки платежа
            error_text = "❌ Ваш платеж не был выполнен!"

            await callback.answer(
                text=error_text,
                show_alert=True
            )

        # Возвращаемся в меню заказчика
        await state.set_state(CustomerStates.customer_menu)
        return


@router.callback_query(F.data == 'customer_menu')
async def back_to_customer_menu_from_limit(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в меню заказчика из экрана лимита"""
    logger.debug(f'back_to_customer_menu_from_limit...')

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Send customer menu
    await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(F.data == 'add_orders', CustomerStates.customer_menu)
async def send_invoice_buy_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'send_invoice_buy_subscription...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    admins = await Admin.get_all()
    admin = admins[0]

    prices = [LabeledPrice(label=f"Дополнительное размещение", amount=int(admin.order_price * 100))]

    text = f"Количество размещений: 1"

    await state.set_state(CustomerStates.customer_buy_subscription)

    # РЕАЛЬНАЯ ПЛАТЕЖНАЯ СИСТЕМА
    try:
        await callback.message.answer_invoice(
            title=f"Дополнительное размещение",
            description=text,
            provider_token=config.PAYMENTS,
            currency="RUB",
            prices=prices,
            start_parameter="one-month-subscription",
            payload="invoice-payload",
            reply_markup=kbc.customer_buy_order(),
            need_email=True,
            send_email_to_provider=True
        )
        await state.update_data(customer_id=str(customer.id),
                                order_price=admin.order_price)
    except TelegramBadRequest as e:
        logger.error(f"Payment provider error: {e}")
        # Обрабатываем ошибку недоступности платежного метода
        if "PAYMENT_PROVIDER_INVALID" in str(e):
            error_text = "❌ Платежный метод недоступен\n\n"
            error_text += "🚫 К сожалению, в вашей стране недоступны платежные методы Telegram.\n\n"
            error_text += "📞 Для получения помощи обратитесь в поддержку"

            await callback.answer(
                text=error_text,
                show_alert=True,
            )
        else:
            # Другие ошибки платежа
            error_text = "❌ Ваш платеж не был выполнен!"

            await callback.answer(
                text=error_text,
                show_alert=True
            )

        # Возвращаемся в меню заказчика
        await state.set_state(CustomerStates.customer_menu)
        return
    #     else:
    #         # Другие ошибки платежа
    #         error_text = "❌ Ошибка при создании платежа\n\n"
    #         error_text += "🚫 Произошла ошибка при попытке создать платеж.\n\n"
    #         error_text += "💡 Попробуйте:\n"
    #         error_text += "• Проверить интернет-соединение\n"
    #         error_text += "• Попробовать позже\n"
    #         error_text += "• Обратиться в поддержку\n\n"
    #         error_text += f"🔍 Код ошибки: {str(e)}"
    #         
    #         await callback.message.answer(
    #             text=error_text,
    #             reply_markup=kbc.menu_customer_keyboard()
    #         )
    #     
    #     # Возвращаемся в меню заказчика
    #     await state.set_state(CustomerStates.customer_menu)
    #     return


@router.pre_checkout_query(lambda query: True, CustomerStates.customer_buy_subscription)
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    logger.debug(f'pre_checkout_handler...')
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment, CustomerStates.customer_buy_subscription)
async def success_payment_handler(message: Message, state: FSMContext):
    logger.debug(f'success_payment_handler...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))
    order_price = int(state_data.get('order_price'))

    customer = await Customer.get_customer(id=customer_id)

    await customer.update_abs_count(abs_count=customer.abs_count + 1)

    await message.answer(
        text=f"Спасибо, ваш платеж на сумму {order_price}₽ успешно выполнен!\n\nДоступно размещений: {customer.abs_count + 1}",
        reply_markup=kbc.menu_customer_keyboard())
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(F.data == 'create_new_abs', CustomerStates.customer_menu)
async def create_new_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_new_abs...')

    kbc = KeyboardCollection()

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Проверяем лимит объявлений
    if customer.abs_count <= 0:
        # Показываем alert с кнопкой ОК
        await callback.answer(
            "Достигнут лимит за сегодня ⚠️",
            show_alert=True
        )

        # После нажатия "ОК" показываем меню с кнопками оплаты
        kbc = KeyboardCollection()
        text = (
            "⚠️ <b>Ваш лимит бесплатных объявлений достигнут.</b>\n\n"
            "Продолжите публикацию, оплатив размещение."
        )

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_limit_reached_menu(),
            parse_mode='HTML'
        )
        return

    await state.clear()
    await state.set_state(CustomerStates.customer_create_abs_work_type)

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    await callback.answer(
        text=f"Предусмотрена блокировка, если в тексте и фото присутствуют:\n"
             f"- Ссылки\n"
             f"- Латинские буквы\n"
             f"- Номера телефонов\n"
             f"- Названия любых агрегаторов, мессенджеров и маркетплейсов",
        show_alert=True
    )

    await callback.message.answer(
        text='Выберете направление',
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True)
    )


@router.callback_query(F.data == 'back', CustomerStates.customer_create_abs_work_type)
async def create_new_abs_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_new_abs_back...')

    tg_id = callback.message.chat.id
    customer = await Customer.get_customer(tg_id=tg_id)

    # Send customer menu
    await help_defs.send_customer_menu(callback, customer, state)


async def get_customer_ads_optimized(customer_id: int):
    """Оптимизированное получение всех данных объявлений заказчика одним запросом"""
    import aiosqlite

    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute('''
                                    SELECT a.id,
                                           a.work_type_id,
                                           a.city_id,
                                           a.text_path,
                                           a.photo_path,
                                           a.views,
                                           a.count_photo,
                                           c.city,
                                           (SELECT COUNT(*) FROM workers_and_abs wa WHERE wa.abs_id = a.id) as responses_count
                                    FROM abs a
                                             LEFT JOIN cities c ON a.city_id = c.id
                                    WHERE a.customer_id = ?
                                    ORDER BY a.id DESC
                                    ''', (customer_id,))

        results = await cursor.fetchall()
        await cursor.close()

        advertisements = []
        for result in results:
            ads_data = {
                'id': result[0],
                'work_type_id': result[1],
                'city_id': result[2],
                'text_path': result[3],
                'photo_path': result[4],
                'views': result[5],
                'count_photo': result[6],
                'city_name': result[7],
                'responses_count': result[8]
            }
            advertisements.append(ads_data)

        return advertisements
    finally:
        await conn.close()


@router.callback_query(F.data == 'my_abs')
async def my_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')

    kbc = KeyboardCollection()

    # Получаем заказчика
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Получаем все данные объявлений одним запросом
    advertisements = await get_customer_ads_optimized(customer_id=customer.id)

    if not advertisements:
        await callback.answer('У вас пока нет активных объявлений!', show_alert=True)
        await help_defs.send_customer_menu(callback, customer, state)
        return

    await state.set_state(CustomerStates.customer_check_abs)

    # Сохраняем данные объявлений в состоянии для оптимизации
    await state.update_data(advertisements=advertisements)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    # Используем данные из оптимизированного запроса
    city_name = abs_now['city_name']

    text = help_defs.read_text_file(abs_now['text_path'])

    text = f'Объявление #{abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
    logger.debug(f"text {text}")

    # Используем количество откликов из оптимизированного запроса
    has_responses = abs_now['responses_count'] > 0
    btn_responses = has_responses

    # Для кнопки "Закрыть и оценить" нужно проверить активные отклики (applyed = True)
    # Делаем отдельный запрос для этого
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now['id'])
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                break

    btn_close_name = '📌 Закрыть и оценить'

    if abs_now['photo_path']:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        # Парсим JSON строку photo_path
        import json

        def get_safe_photo_path(photo_path_str):
            """Безопасно извлекает путь к фотографии из JSON строки"""
            if not photo_path_str:
                return ''
            try:
                photo_dict = json.loads(photo_path_str)
                if isinstance(photo_dict, dict):
                    return photo_dict.get('0', '')
                return ''
            except (json.JSONDecodeError, TypeError, AttributeError):
                return ''

        photo_path = get_safe_photo_path(abs_now['photo_path'])

        logger.debug(photo_path)
        logger.debug(abs_now['photo_path'])

        # Проверяем, есть ли валидный путь к фото
        if not photo_path:
            # Нет фото - отправляем только текст
            await callback.message.answer(text=text,
                                          reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                    btn_back=False,
                                                                                    btn_close=True,
                                                                                    btn_responses=btn_responses,
                                                                                    btn_close_name=btn_close_name,
                                                                                    abs_id=abs_now['id']))
            return
        elif 'https' in photo_path:
            # Фото по ссылке - отправляем только текст (фото уже показано)
            await callback.message.answer(text=text,
                                          reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                    btn_back=False,
                                                                                    btn_close=True,
                                                                                    btn_responses=btn_responses,
                                                                                    btn_close_name=btn_close_name,
                                                                                    abs_id=abs_now['id']))
            return
        else:
            # Локальное фото - проверяем существование файла и отправляем
            import os
            if os.path.exists(photo_path) and os.path.isfile(photo_path):
                await callback.message.answer_photo(photo=FSInputFile(photo_path),
                                                    caption=text,
                                                    reply_markup=kbc.choose_obj_with_out_list(id_now=0,
                                                                                              btn_next=btn_next,
                                                                                              btn_back=False,
                                                                                              btn_close=True,
                                                                                              btn_responses=btn_responses,
                                                                                              btn_close_name=btn_close_name,
                                                                                              abs_id=abs_now['id'],
                                                                                              count_photo=abs_now[
                                                                                                  'count_photo'],
                                                                                              idk_photo=0))
            else:
                # Файл не существует - отправляем только текст
                logger.warning(f"Photo file not found: {photo_path}")
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.choose_obj_with_out_list(
                        id_now=0,
                        btn_next=btn_next,
                        btn_back=False,
                        btn_close=True,
                        btn_responses=btn_responses,
                        btn_close_name=btn_close_name,
                        abs_id=abs_now['id']
                    )
                )
    else:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=0,
                btn_next=btn_next,
                btn_back=False,
                btn_close=True,
                btn_responses=btn_responses,
                btn_close_name=btn_close_name,
                abs_id=abs_now['id']
            )
        )


@router.callback_query(lambda c: c.data.startswith('go_'), StateFilter(CustomerStates.customer_check_abs))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    # Используем оптимизированную функцию для консистентной сортировки
    advertisements = await get_customer_ads_optimized(customer_id=customer.id)

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    abs_now = advertisements[abs_list_id]

    city_name = abs_now['city_name']

    text = help_defs.read_text_file(abs_now['text_path'])

    text = f'Объявление #{abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
    logger.debug(f"text {text}")

    # Используем количество откликов из оптимизированного запроса (как в функции my_abs)
    has_responses = abs_now['responses_count'] > 0
    btn_responses = has_responses

    # Для кнопки "Закрыть и оценить" нужно проверить активные отклики (applyed = True)
    # Делаем отдельный запрос для этого
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now['id'])
    workers_applyed = False
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                break

    btn_close_name = 'Закрыть и оценить'
    await state.set_state(CustomerStates.customer_check_abs)

    if abs_now['photo_path']:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Парсим JSON строку photo_path
        import json

        def get_safe_photo_path(photo_path_str):
            """Безопасно извлекает путь к фотографии из JSON строки"""
            if not photo_path_str:
                return ''
            try:
                photo_dict = json.loads(photo_path_str)
                if isinstance(photo_dict, dict):
                    return photo_dict.get('0', '')
                return ''
            except (json.JSONDecodeError, TypeError, AttributeError):
                return ''

        photo_path = get_safe_photo_path(abs_now['photo_path'])

        if not photo_path:
            # Нет фото - отправляем только текст
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now['id']
                )
            )
            return
        elif 'https' in photo_path:
            # Фото по ссылке - отправляем только текст (фото уже показано)
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now['id']
                )
            )
            return
        else:
            # Локальное фото - проверяем существование файла и отправляем
            import os
            if os.path.exists(photo_path) and os.path.isfile(photo_path):
                # Файл существует - отправляем фото с подписью
                await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=text,
                    reply_markup=kbc.choose_obj_with_out_list(
                        id_now=abs_list_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        btn_responses=btn_responses,
                        btn_close=True,
                        btn_close_name=btn_close_name,
                        abs_id=abs_now['id'],
                        count_photo=abs_now['count_photo'],
                        idk_photo=0
                    )
                )
            else:
                # Файл не существует - отправляем только текст
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.choose_obj_with_out_list(
                        id_now=abs_list_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        btn_responses=btn_responses,
                        btn_close=True,
                        btn_close_name=btn_close_name,
                        abs_id=abs_now['id']
                    )
                )
            return


@router.callback_query(lambda c: c.data.startswith('abs_'))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await get_customer_ads_optimized(customer_id=customer.id)

    abs_list_id = 0

    for i in range(len(advertisements)):
        abs = advertisements[i]
        if abs.id == abs_id:
            abs_list_id = i
            break

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    abs_now = advertisements[abs_list_id]

    city_name = abs_now['city_name']

    text = help_defs.read_text_file(abs_now['text_path'])

    text = f'Объявление #{abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
    logger.debug(f"text {text}")

    # Используем количество откликов из оптимизированного запроса (как в функции my_abs)
    has_responses = abs_now['responses_count'] > 0
    btn_responses = has_responses

    btn_close_name = 'Закрыть и оценить'
    await state.set_state(CustomerStates.customer_check_abs)

    if abs_now['photo_path']:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Парсим JSON строку photo_path
        import json

        def get_safe_photo_path(photo_path_str):
            """Безопасно извлекает путь к фотографии из JSON строки"""
            if not photo_path_str:
                return ''
            try:
                photo_dict = json.loads(photo_path_str)
                if isinstance(photo_dict, dict):
                    return photo_dict.get('0', '')
                return ''
            except (json.JSONDecodeError, TypeError, AttributeError):
                return ''

        photo_path = get_safe_photo_path(abs_now['photo_path'])

        if not photo_path:
            # Нет фото - отправляем только текст
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now['id']
                )
            )
            return
        elif 'https' in photo_path:
            # Фото по ссылке - отправляем только текст (фото уже показано)
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now['id']
                )
            )
            return
        else:
            # Локальное фото - проверяем существование файла и отправляем
            import os
            if os.path.exists(photo_path) and os.path.isfile(photo_path):
                await callback.message.answer(
                    text=text,
                    reply_markup=kbc.choose_obj_with_out_list(
                        id_now=abs_list_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        btn_responses=btn_responses,
                        btn_close=True,
                        btn_close_name=btn_close_name,
                        abs_id=abs_now['id']
                    )
                )
            return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_obj_with_out_list(
            id_now=abs_list_id,
            btn_next=btn_next,
            btn_back=btn_back,
            btn_responses=btn_responses,
            btn_close=True,
            btn_close_name=btn_close_name,
            abs_id=abs_now['id']
        )
    )


@router.callback_query(lambda c: c.data.startswith('go-to-next_'), StateFilter(CustomerStates.customer_check_abs))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    # Используем оптимизированную функцию для консистентной сортировки
    advertisements = await get_customer_ads_optimized(customer_id=customer.id)

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    abs_now = advertisements[abs_list_id]

    # Для кнопки "Закрыть и оценить" нужно проверить активные отклики (applyed = True)
    # Делаем отдельный запрос для этого
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now['id'])
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                break

    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                btn_responses = True
                break

    btn_close_name = 'Закрыть и оценить'
    await state.set_state(CustomerStates.customer_check_abs)

    if photo_id <= -1:
        photo_id = abs_now['count_photo'] - 1
    elif photo_id > (abs_now['count_photo'] - 1):
        photo_id = 0

    if abs_now['photo_path']:
        # Парсим JSON строку photo_path
        import json

        def get_safe_photo_path(photo_path_str):
            """Безопасно извлекает путь к фотографии из JSON строки"""
            if not photo_path_str:
                return ''
            try:
                photo_dict = json.loads(photo_path_str)
                if isinstance(photo_dict, dict):
                    return photo_dict.get(str(photo_id), '')
                return ''
            except (json.JSONDecodeError, TypeError, AttributeError):
                return ''

        photo_path = get_safe_photo_path(abs_now['photo_path'])

        if photo_path:
            try:
                # Поддержка как локальных, так и https фото
                if 'https' in photo_path:
                    await callback.message.edit_media(
                        media=InputMediaPhoto(
                            media=photo_path,
                            caption=callback.message.caption
                        ),
                        reply_markup=kbc.choose_obj_with_out_list(
                            id_now=abs_list_id,
                            btn_next=btn_next,
                            btn_back=btn_back,
                            btn_responses=btn_responses,
                            btn_close=True,
                            btn_close_name=btn_close_name,
                            abs_id=abs_now['id'],
                            count_photo=abs_now['count_photo'],
                            idk_photo=photo_id
                        )
                    )
                else:
                    await callback.message.edit_media(
                        media=InputMediaPhoto(
                            media=FSInputFile(photo_path),
                            caption=callback.message.caption
                        ),
                        reply_markup=kbc.choose_obj_with_out_list(
                            id_now=abs_list_id,
                            btn_next=btn_next,
                            btn_back=btn_back,
                            btn_responses=btn_responses,
                            btn_close=True,
                            btn_close_name=btn_close_name,
                            abs_id=abs_now['id'],
                            count_photo=abs_now['count_photo'],
                            idk_photo=photo_id
                        )
                    )
            except TelegramBadRequest:
                # Сообщение уже недоступно для редактирования — отправляем новое
                if 'https' in photo_path:
                    await callback.message.answer_photo(
                        photo=photo_path,
                        caption=callback.message.caption,
                        reply_markup=kbc.choose_obj_with_out_list(
                            id_now=abs_list_id,
                            btn_next=btn_next,
                            btn_back=btn_back,
                            btn_responses=btn_responses,
                            btn_close=True,
                            btn_close_name=btn_close_name,
                            abs_id=abs_now['id'],
                            count_photo=abs_now['count_photo'],
                            idk_photo=photo_id
                        )
                    )
                else:
                    await callback.message.answer_photo(
                        photo=FSInputFile(photo_path),
                        caption=callback.message.caption,
                        reply_markup=kbc.choose_obj_with_out_list(
                            id_now=abs_list_id,
                            btn_next=btn_next,
                            btn_back=btn_back,
                            btn_responses=btn_responses,
                            btn_close=True,
                            btn_close_name=btn_close_name,
                            abs_id=abs_now['id'],
                            count_photo=abs_now['count_photo'],
                            idk_photo=photo_id
                        )
                    )
            return


@router.callback_query(
    lambda c: c.data.startswith('close_') and not c.data.startswith('close_and_rate_') and not c.data.startswith(
        'close_advertisement_'), CustomerStates.customer_check_abs)
async def close_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'close_abs...')

    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await get_customer_ads_optimized(customer_id=customer.id)

    advertisement_now = advertisements[abs_list_id]

    # Показываем подтверждение закрытия объявления
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text=f'⚠️ Вы уверены, что хотите закрыть объявление #{advertisement_now["id"]}?\n\n'
             f'После закрытия объявления, вы сможете оценить заказ выбрав исполнителя.',
        reply_markup=kbc.confirm_close_advertisement(abs_id=advertisement_now["id"])
    )


@router.callback_query(lambda c: c.data.startswith('confirm-close_'))
async def confirm_close_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение закрытия объявления с возможностью оценки исполнителей"""
    logger.debug(f'confirm_close_advertisement...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisement = await Abs.get_one(id=abs_id)

    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Находим исполнителей для оценки (купили контакты и еще не оценены)
    # Логика: если исполнитель купил контакты, значит он откликнулся И передал контакты
    workers_for_assessment = []

    from app.data.database.models import ContactExchange, WorkerRating
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)

    if contact_exchanges:
        for contact_exchange in contact_exchanges:
            if contact_exchange.contacts_purchased:  # Купил контакты
                worker = await Worker.get_worker(id=contact_exchange.worker_id)
                if worker:
                    # Проверяем, не оценен ли уже этот исполнитель
                    existing_rating = await WorkerRating.get_by_worker_and_abs(contact_exchange.worker_id, abs_id)
                    if not existing_rating:  # Только если еще не оценен
                        workers_for_assessment.append(worker)

    # НЕ удаляем объявление сразу - удалим после оценки всех исполнителей
    # await advertisement.delete(delite_photo=True)

    # НЕ удаляем связанные записи сразу - удалим после оценки
    # from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange
    # workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
    # if workers_and_bad_responses:
    #     [await bad_response.delete() for bad_response in workers_and_bad_responses]

    # workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
    # if workers_and_reports:
    #     [await report.delete() for report in workers_and_reports]

    # contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    # if contact_exchanges:
    #     [await exchange.delete() for exchange in contact_exchanges]

    # workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
    # if workers_and_abs:
    #     [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

    # НЕ обновляем статистику админов сразу - обновим после оценки
    # admins = await Admin.get_all()
    # for admin in admins:
    #     await admin.update(done_abs=admin.done_abs + 1)

    # Если есть исполнители для оценки - показываем их
    if workers_for_assessment:
        names = []
        for worker in workers_for_assessment:
            rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
            worker_name = worker.profile_name if worker.profile_name else f"ID {worker.id}"
            names.append(f'{worker_name} ⭐ {rating_display} ({count_ratings} {help_defs.get_rating_word(count_ratings)})')
        ids = [worker.id for worker in workers_for_assessment]

        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Сохраняем abs_id в состоянии для последующего удаления
        await state.update_data(pending_advertisement_id=abs_id)

        try:
            await callback.message.edit_text(
                text='✅ Объявление закрыто!\n\nВыберите исполнителей для оценки:',
                reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
            )
        except Exception:
            await callback.message.answer(
                text='✅ Объявление закрыто!\n\nВыберите исполнителей для оценки:',
                reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
            )
    elif workers_for_assessment:
        # Есть исполнители, но все уже оценены
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await advertisement.delete(delite_photo=True)
        # Удаляем связанные записи
        from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange, WorkersAndAbs
        workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
        if workers_and_bad_responses:
            [await bad_response.delete() for bad_response in workers_and_bad_responses]
        workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
        if workers_and_reports:
            [await report.delete() for report in workers_and_reports]
        contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
        if contact_exchanges:
            [await exchange.delete() for exchange in contact_exchanges]
        workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
        if workers_and_abs:
            [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]
        from app.data.database.models import Admin
        admins = await Admin.get_all()
        for admin in admins:
            await admin.update(done_abs=admin.done_abs + 1)

        await callback.answer(
            text='✅ Объявление закрыто!\n\nВсе исполнители уже оценены.',
            show_alert=True
        )
        await help_defs.send_customer_menu(callback, customer, state)
    else:
        # Нет исполнителей для оценки - удаляем объявление и закрываем
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Удаляем объявление, так как нет исполнителей для оценки
        await advertisement.delete(delite_photo=True)

        # Удаляем связанные записи
        from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange, WorkersAndAbs
        workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
        if workers_and_bad_responses:
            [await bad_response.delete() for bad_response in workers_and_bad_responses]

        workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
        if workers_and_reports:
            [await report.delete() for report in workers_and_reports]

        contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
        if contact_exchanges:
            [await exchange.delete() for exchange in contact_exchanges]

        workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
        if workers_and_abs:
            [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

        # Обновляем статистику админов
        from app.data.database.models import Admin
        admins = await Admin.get_all()
        for admin in admins:
            await admin.update(done_abs=admin.done_abs + 1)

        await callback.answer(
            "Объявление закрыто ✅\n\nИсполнителей для оценки не найдено!",
            show_alert=True
        )
        await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(lambda c: c.data.startswith('cancel-close_'))
async def cancel_close_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена закрытия объявления"""
    logger.debug(f'cancel_close_advertisement...')

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    # Возвращаемся к просмотру объявлений
    await callback.message.answer(
        text='❌ Закрытие объявления отменено.',
        reply_markup=InlineKeyboardBuilder().add(
            InlineKeyboardButton(text='В меню', callback_data='menu')
        ).adjust(1).as_markup()
    )
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(lambda c: c.data.startswith('close-by-end-time_'))
async def close_by_end_time(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'close_abs...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisement_now = await Abs.get_one(id=abs_id)

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement_now.id)
    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=advertisement_now.id)
    if workers_and_bad_responses is not None:
        [await workers_and_bad_response.delete() for workers_and_bad_response in workers_and_bad_responses]
    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=advertisement_now.id)
    if workers_and_reports is not None:
        [await workers_and_report.delete() for workers_and_report in workers_and_reports]

    # Удаляем записи ContactExchange для этого объявления
    from app.data.database.models import ContactExchange
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=advertisement_now.id)
    if contact_exchanges:
        [await contact_exchange.delete() for contact_exchange in contact_exchanges]
        logger.info(f"Deleted {len(contact_exchanges)} ContactExchange records for abs_id {advertisement_now.id}")

    workers_for_assessments = []
    if workers_and_abs:
        workers_for_assessments = await close_task(
            workers_and_abs=workers_and_abs,
            workers_for_assessments=workers_for_assessments,
            advertisement_now=advertisement_now,
            customer=customer
        )

        if workers_for_assessments:
            names = []
            for worker in workers_for_assessments:
                rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
                worker_name = worker.profile_name if worker.profile_name else f"ID {worker.id}"
                names.append(
                    f'{worker_name} ⭐ {rating_display} ({count_ratings} {help_defs.get_rating_word(count_ratings)})'
                )
            ids = [worker.id for worker in workers_for_assessments]
            await state.clear()
            await advertisement_now.delete(delite_photo=True)

            await callback.message.answer(text='Выберите исполнителя для оценки',
                                          reply_markup=kbc.get_for_staring(ids=ids, names=names,
                                                                           abs_id=advertisement_now.id))

            admins = await Admin.get_all()
            for admin in admins:
                await admin.update(done_abs=admin.done_abs + 1)
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            return

    await advertisement_now.delete(delite_photo=True)

    admins = await Admin.get_all()
    for admin in admins:
        await admin.update(deleted_abs=admin.deleted_abs + 1)

    await callback.message.answer(text='Объявление закрыто!', reply_markup=kbc.menu_customer_keyboard())


@router.callback_query(lambda c: c.data.startswith('choose-worker-for-rating_'))
async def choose_worker_for_rating(callback: CallbackQuery) -> None:
    """Новый обработчик для выбора исполнителя для оценки"""
    logger.debug(f'choose_worker_for_rating...')

    # Парсим данные: choose-worker-for-rating_worker_id_abs_id
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])

    kbc = KeyboardCollection()

    # Получаем информацию об исполнителе
    worker = await Worker.get_worker(id=worker_id)
    if not worker:
        await callback.answer("Исполнитель не найден", show_alert=True)
        return

    # Формируем информацию об исполнителе
    worker_name = worker.profile_name if worker.profile_name else "Исполнитель"
    worker_rating, _ = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
    worker_orders = worker.count_ratings if worker.count_ratings else 0

    text = (
        f'👤 <b>Информация об исполнителе:</b>\n\n'
        f'• ID: {worker_id}\n'
        f'• Имя: {worker_name}\n'
        f'• Рейтинг: {worker_rating} ⭐\n'
        f'• Выполнено заказов: {worker_orders}\n\n'
        f'📝 <b>Оцените качество работы исполнителя:</b>'
    )

    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.set_rating(worker_id=worker_id, abs_id=abs_id),
            parse_mode='HTML'
        )
    except Exception:
        try:
            await callback.message.delete()
            await callback.message.answer(
                text=text,
                reply_markup=kbc.set_rating(worker_id=worker_id, abs_id=abs_id),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.debug(f"Error in choose_worker_for_rating: {e}")
            # Если ничего не работает, просто отвечаем
            await callback.message.answer(
                text=text,
                reply_markup=kbc.set_rating(worker_id=worker_id, abs_id=abs_id),
                parse_mode='HTML'
            )


# Старая система оценки удалена - теперь используется rate_worker


@router.callback_query(F.data == 'skip-star-for-worker')
async def skip_star_for_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'skip_star_for_worker...')
    kbc = KeyboardCollection()

    # Получаем abs_id из состояния
    state_data = await state.get_data()
    abs_id = state_data.get('pending_advertisement_id')

    # Если есть abs_id, проверяем и удаляем объявление
    if abs_id:
        try:
            advertisement = await Abs.get_one(id=abs_id)
            if advertisement:
                # Объявление еще существует - удаляем его
                await advertisement.delete(delite_photo=True)

                # Удаляем связанные записи
                from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange, \
                    WorkersAndAbs
                workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
                if workers_and_bad_responses:
                    [await bad_response.delete() for bad_response in workers_and_bad_responses]

                workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
                if workers_and_reports:
                    [await report.delete() for report in workers_and_reports]

                contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
                if contact_exchanges:
                    [await exchange.delete() for exchange in contact_exchanges]

                workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
                if workers_and_abs:
                    [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

                # Обновляем статистику админов
                from app.data.database.models import Admin
                admins = await Admin.get_all()
                for admin in admins:
                    await admin.update(done_abs=admin.done_abs + 1)
        except Exception as e:
            logger.error(f"Error cleaning up advertisement in skip_star_for_worker: {e}")

    # Проверяем, есть ли еще исполнители для оценки
    state_data = await state.get_data()
    abs_id = state_data.get('pending_advertisement_id')

    if abs_id:
        # Получаем оставшихся исполнителей для оценки
        from app.data.database.models import ContactExchange
        contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
        remaining_workers = []

        for contact_exchange in contact_exchanges:
            if contact_exchange.contacts_purchased:
                worker = await Worker.get_worker(id=contact_exchange.worker_id)
                if worker:
                    remaining_workers.append(worker)

        if remaining_workers:
            # Есть еще исполнители для оценки - показываем их
            names = []
            for worker in remaining_workers:
                rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
                worker_name = worker.profile_name if worker.profile_name else f"ID {worker.id}"
                names.append(
                    f'{worker_name} ⭐ {rating_display} ({count_ratings} {help_defs.get_rating_word(count_ratings)})'
                )
            ids = [worker.id for worker in remaining_workers]

            try:
                await callback.message.edit_text(
                    text='✅ Исполнитель пропущен!\n\nВыберите следующего исполнителя для оценки:',
                    reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
                )
            except Exception:
                await callback.message.answer(
                    text='✅ Исполнитель пропущен!\n\nВыберите следующего исполнителя для оценки:',
                    reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
                )
            return

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Нет больше исполнителей для оценки - завершаем процесс
    await callback.answer(
        "✅ Оценка завершена!\n\nОбъявление закрыто. Спасибо за использование сервиса!",
        show_alert=True
    )
    await help_defs.send_customer_menu(callback, customer, state)



@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_create_abs_work_type)
async def create_abs_work_type(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type...')

    kbc = KeyboardCollection()
    work_type_id = int(callback.data.split('_')[1])
    work_type = await WorkType.get_work_type(id=work_type_id)

    template_text = help_defs.read_text_file(
        work_type.template) if work_type.template else "Пример объявления не найден"
    text = f'Пример объявления для {work_type.work_type}\n\n' + template_text

    if work_type.template_photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(photo=FSInputFile(work_type.template_photo), caption=text,
                                            parse_mode='HTML')
        return

    example_msg = await callback.message.answer(text=text, parse_mode='HTML')

    msg = await callback.message.answer('Укажите задачу, что необходимо: (не более 800 символов)',
                                        reply_markup=kbc.back_btn())
    await state.set_state(CustomerStates.customer_create_abs_task)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(example_msg_id=example_msg.message_id)


@router.callback_query(F.data == 'back', CustomerStates.customer_create_abs_task)
async def create_abs_work_type_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type_back...')
    kbc = KeyboardCollection()

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    state_data = await state.get_data()
    example_msg_id = str(state_data.get('example_msg_id'))
    msg_id = str(state_data.get('msg_id'))

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=example_msg_id)
    except TelegramBadRequest:
        pass
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
    except TelegramBadRequest:
        pass
    await state.set_state(CustomerStates.customer_create_abs_work_type)
    await callback.message.answer(text='Выберете тип работы',
                                  reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.message(F.text, CustomerStates.customer_create_abs_task)
async def customer_create_abs_price(message: Message, state: FSMContext) -> None:
    logger.debug(f'customer_create_abs_price... {message.text}')

    kbc = KeyboardCollection()

    # Проверяем контент на запрещенные элементы
    if await help_defs.handle_forbidden_content(message):
        return  # Сообщение заблокировано, обработка прекращается

    task = message.text

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    msg_id = str(state_data.get('msg_id'))
    example_msg_id = str(state_data.get('example_msg_id'))

    if len(task) < 50:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except TelegramBadRequest:
            pass
        msg = await message.answer(
            '⚠️ Упс, похоже вы пытаетесь предложить запрос без подробностей, повторите попытку снова.\n\nУкажите задачу: (не более 800 символов)',
            reply_markup=kbc.back_btn())
        await state.update_data(msg_id=msg.message_id)
        return

    if len(task) > 800:
        # try:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        # except TelegramBadRequest:
        #     pass
        msg = await message.answer('Укажите задачу: (не более 800 символов)',
                                   reply_markup=kbc.back_btn())
        await state.update_data(msg_id=msg.message_id)
        return

    # try:
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    # except TelegramBadRequest:
    #     pass

    await state.set_state(CustomerStates.customer_create_abs_choose_time)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(task=task)
    await state.update_data(example_msg_id=example_msg_id)

    if '20' in work_type_id:
        names = ['В ближайшее время', 'Завтра', 'В течении недели']
        ids = [1, 2, 3]
        await message.answer('Когда нужна услуга:\n\n',
                             reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))
        return

    names = ['В ближайшее время', 'Завтра', 'В течении недели', 'В течении месяца']
    ids = [1, 2, 3, 4]

    await message.answer('Когда нужна услуга:\n\n', reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.message(F.photo, CustomerStates.customer_create_abs_task)
async def customer_create_abs_price(message: Message, state: FSMContext) -> None:
    kbc = KeyboardCollection()
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        msg = await message.answer(
            text='⚠️ Не спешите пожалуйста, добавление фото доступно позже, напишите свой запрос текстом',
            reply_markup=kbc.back_btn()
        )
        await state.update_data(msg_id=msg.message_id, photo_except=1)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == 'back', CustomerStates.customer_create_abs_choose_time)
async def create_abs_work_type_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type_back...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    example_msg_id = str(state_data.get('example_msg_id'))

    if '20' in work_type_id:
        msg = await callback.message.answer(
            'Укажите подробности, условия, график, заработная плата: (не более 800 символов)',
            reply_markup=kbc.back_btn())
        await state.set_state(CustomerStates.customer_create_abs_task)
        await state.update_data(work_type_id=work_type_id)
        await state.update_data(task=task)
        await state.update_data(msg_id=msg.message_id)
        await state.update_data(example_msg_id=example_msg_id)
        return

    msg = await callback.message.answer(text='Укажите задачу: (не более 800 символов)', reply_markup=kbc.back_btn())
    await state.set_state(CustomerStates.customer_create_abs_price)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(task=task)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(example_msg_id=example_msg_id)


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_create_abs_choose_time)
async def create_abs_choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_choose_time...')

    kbc = KeyboardCollection()

    time_id = int(callback.data.split('_')[1])
    if time_id == 1:
        time = 'В ближайшее время'
    elif time_id == 2:
        time = 'Завтра'
    elif time_id == 3:
        time = 'В течении недели'
    else:
        time = 'В течении месяца'

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    example_msg_id = str(state_data.get('example_msg_id'))

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=example_msg_id)
    except TelegramBadRequest:
        pass
    except ValidationError:
        pass

    # Явно очищаем любые старые данные состояния (например, от загрузки портфолио)
    await state.update_data(album=[], processed_media_groups=[])

    await state.set_state(CustomerStates.customer_create_abs_add_photo)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(task=task)
    await state.update_data(time=time)
    await state.update_data(end=0)
    msg = await callback.message.answer(text='Прикрепите фото, или нажмите кнопку пропустить',
                                        reply_markup=kbc.skip_btn())
    await state.update_data(msg=msg.message_id)
    await callback.answer(
        text=f"Вы можете прикрепить до 10 фото.\n"
             f"На фото не должно быть надписей, цифр и символов, если они присутствуют - их следует замазать перед загрузкой.\n"
             f"Загрузка видео недоступна!\n",
        show_alert=True
    )


@router.callback_query(F.data == 'skip_it', CustomerStates.customer_create_abs_add_photo)
async def create_abs_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_no_photo...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg = str(state_data.get('msg'))

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg)
    except TelegramBadRequest:
        pass
    msg = await callback.message.answer('Подождите идет проверка')

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    time = str(state_data.get('time'))

    all_text = f'{task}'
    if ban_reason := await checks.fool_check(text=all_text):
        await ban_task(message=callback.message, work_type_id=work_type_id, task=task, time=time, ban_reason=ban_reason,
                       msg=msg)
        await state.set_state(BannedStates.banned)
        return

    work_type = await WorkType.get_work_type(id=int(work_type_id))
    work = work_type.work_type.capitalize()

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    except TelegramBadRequest:
        pass

    if checks.phone_finder(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            '⛔️ Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        return

    if checks.contains_invalid_chars(all_text):
        await callback.message.answer(
            'Извините, но использование иностранных символов недопустимо в объявлении, попробуйте еще раз',
            reply_markup=kbc.menu_btn())
        await state.set_state(CustomerStates.customer_menu)
        return

    if checks.contains_gibberish(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            '⛔️ Упс, похоже у вас некорректный текст, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        return

    # Проверка на повторяющиеся слова
    is_valid, repeated_word_error = checks.check_repeated_words(all_text, max_repeats=5)
    if not is_valid:
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n')

        text = help_defs.escape_markdown(text=text)

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id),
            city_id=customer.city_id,
            photo_path=None,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30),
            photos_len=0
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.id}\n'
                f'Telegram ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n'
                f'Причина: Повторяющиеся слова')

        text = help_defs.escape_markdown(text=text)

        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
        except TelegramBadRequest:
            pass

        await bot.send_message(chat_id=config.BLOCKED_CHAT, text=text, protect_content=False,
                               reply_markup=kbc.unban(banned_abs.id, photo_num=0, photo_len=0))

        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await callback.message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                              reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(
                ban_counter=banned.ban_counter + 1,
                ban_now=True,
                ban_end=ban_end,
                ban_reason="Повторяющиеся слова"
            )
            await callback.message.answer(
                ' ⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(
            id=None,
            tg_id=callback.message.chat.id,
            ban_counter=1, ban_end=ban_end, ban_now=True,
            forever=False, ban_reason="Повторяющиеся слова"
        )
        await callback.message.answer(
            '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)
        return

    text = (f'{work}\n\n'
            f'Задача: {task}\n\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации: {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text = help_defs.escape_markdown(text=text)

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    city = await City.get_city(id=customer.city_id)

    # Проверяем только объявления текущего заказчика на дубликаты
    customer_advertisements = await Abs.get_all_by_customer(customer.id)

    if customer_advertisements:
        if await same_task(message=callback.message, advertisements=customer_advertisements, text=text):
            await state.set_state(CustomerStates.customer_menu)
            return

    logger.debug('win')

    file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text)

    if time == 'В ближайшее время':
        # 12 часов = 0.5 дня
        delta = 0.5
    elif time == 'Завтра':
        # 24 часа = 1 день
        delta = 1
    elif time == 'В течении недели':
        # 7 дней
        delta = 7
    else:
        # 30 дней
        delta = 30

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id),
        city_id=city.id,
        photo_path=None,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=delta),
        count_photo=0
    )
    await new_abs.save()

    # Используем ID из объекта, а не последнее объявление из списка
    advertisement = new_abs

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text

    text = help_defs.escape_markdown(text=text)

    # Сразу отвечаем пользователю
    await callback.message.answer(text=text, reply_markup=kbc.menu_customer_keyboard())
    await state.set_state(CustomerStates.customer_menu)

    # Уменьшаем счетчик объявлений
    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    # Подготавливаем текст для рассылки
    text_for_workers = (f'{work}\n\n'
                        f'Задача: {task}\n\n'
                        f'Время: {time}\n'
                        f'\n'
                        f'Дата публикации: {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text_for_workers = help_defs.escape_markdown(text=text_for_workers)
    text_for_workers = f'Объявление {advertisement.id}\n\n' + text_for_workers

    # Отправляем в лог-канал
    text2 = f'ID пользователя: #{customer.tg_id}\n\n' + text_for_workers
    await bot.send_message(chat_id=config.ADVERTISEMENT_LOG,
                           text=text2,
                           protect_content=False,
                           reply_markup=kbc.block_abs_log(advertisement.id))

    # Даем админу 5 секунд на проверку и возможную блокировку объявления
    await asyncio.sleep(5)

    # Проверяем, не было ли объявление заблокировано за это время
    # Если объявления нет в базе, значит админ его заблокировал
    try:
        check_abs = await Abs.get_one(advertisement.id)
        if not check_abs:
            logger.info(f"[BLOCKED] Advertisement {advertisement.id} was blocked by admin, skipping send")
            return
    except Exception as e:
        logger.error(f"Error checking advertisement status: {e}")
        return

    # Запускаем фоновую рассылку исполнителям (только если объявление не было заблокировано)
    asyncio.create_task(
        send_to_workers_background(
            advertisement_id=advertisement.id,
            city_id=customer.city_id,
            work_type_id=int(work_type_id),
            text=text_for_workers,
            photo_path=None,
            photos_len=0
        )
    )


@router.callback_query(F.data == 'skip_it_photo', CustomerStates.customer_create_abs_add_photo)
async def create_abs_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_skip_photo...')

    kbc = KeyboardCollection()
    state_data = await state.get_data()

    msg_id = state_data.get('msg')
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    time = str(state_data.get('time'))
    album = state_data.get('album', [])

    try:
        if msg_id and str(msg_id) != 'None':
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=int(msg_id))
    except (TelegramBadRequest, ValueError, TypeError):
        pass
    msg = await callback.message.answer(text='Подождите идет проверка')

    text_photo_bool = False

    # Ограничиваем альбом до 10 фото максимум
    if len(album) > 10:
        album = album[:10]
        logger.info(f"[CUSTOMER_AD] Альбом обрезан до 10 фото (было больше)")

    photos = {}
    photos_len = len(album)

    # Создаем папку для всех фото объявления один раз
    file_path, _ = await help_defs.save_photo_var(id=callback.message.chat.id, n=0)

    for i, obj in enumerate(album):
        if obj.photo:
            file_id = obj.photo[-1].file_id
        else:
            file_id = obj[obj.content_type].file_id

        file_path_photo = f'{file_path}{i}.jpg'
        await bot.download(file=file_id, destination=file_path_photo)
        text_photo = yandex_ocr.analyze_file(file_path_photo)
        
        if text_photo:
            has_stop_words, has_other_violations = await check_advertisement_ocr_text(text_photo)
            
            if has_stop_words:
                # Стоп-слова - блокируем
                text_photo_bool = True
            elif has_other_violations:
                # Другие нарушения - обнуляем state и возвращаем к загрузке
                try:
                    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
                except TelegramBadRequest:
                    pass
                
                # Удаляем все скачанные фото
                for photo_key, photo_path in photos.items():
                    if os.path.exists(photo_path):
                        help_defs.delete_file(photo_path)
                if os.path.exists(file_path_photo):
                    help_defs.delete_file(file_path_photo)
                
                # Обнуляем state
                await state.update_data(album=[], processed_media_groups=[], end=0, msg=None)
                
                await callback.message.answer(
                    text="⚠️ Фото нарушает правила платформы, его следует заменить!\n\n"
                         "Загрузите другое",
                    reply_markup=kbc.done_btn()
                )
                
                await state.set_state(CustomerStates.customer_create_abs_add_photo)
                return

        photos[str(i)] = file_path_photo

    file_path_photo = None

    if text_photo_bool:
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))

        work_type = await WorkType.get_work_type(id=int(work_type_id))
        work = work_type.work_type.capitalize()

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n')

        text = help_defs.escape_markdown(text=text)

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id),
            city_id=customer.city_id,
            photo_path=photos,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30),
            photos_len=photos_len
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.id}\n'
                f'Telegram ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n'
                f'Причина: Текст на фото')

        text = help_defs.escape_markdown(text=text)

        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
        except TelegramBadRequest:
            pass

        await bot.send_photo(chat_id=config.BLOCKED_CHAT, photo=FSInputFile(photos['0']), caption=text,
                             protect_content=False,
                             reply_markup=kbc.unban(banned_abs.id, photo_num=0, photo_len=photos_len))
        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await callback.message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                              reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await callback.message.answer(
                '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(id=None, tg_id=callback.message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False, ban_reason="текст на фото")
        await callback.message.answer(
            '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)

        return

    all_text = f'{task}'

    if ban_reason := await checks.fool_check(text=all_text):
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))
        if file_path_photo:
            help_defs.delete_file(file_path_photo)

        work_type = await WorkType.get_work_type(id=int(work_type_id))
        work = work_type.work_type.capitalize()

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n')

        text = help_defs.escape_markdown(text=text)

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')
        # Удаляем этот блок кода, так как photo всегда None в этой функции
        # и скачивание None файла вызывает ошибку

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id),
            city_id=customer.city_id,
            photo_path=photos,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=10),
            photos_len=photos_len
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.id}\n'
                f'Telegram ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n'
                f'Причина блокировки: {ban_reason}')

        text = help_defs.escape_markdown(text=text)

        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
        except TelegramBadRequest:
            pass

        await bot.send_photo(chat_id=config.BLOCKED_CHAT, photo=FSInputFile(photos['0']), caption=text,
                             protect_content=False,
                             reply_markup=kbc.unban(banned_abs.id, photo_num=0, photo_len=photos_len))

        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await callback.message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                              reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await callback.message.answer(
                '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(id=None, tg_id=callback.message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False, ban_reason=ban_reason)
        await callback.message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)

        return

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

    if checks.phone_finder(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            '⛔️ Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        help_defs.delete_folder(file_path_photo)
        return

    if checks.contains_gibberish(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            '⛔️ Упс, похоже у вас некорректный текст, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        help_defs.delete_folder(file_path_photo)
        return

    if checks.contains_invalid_chars(all_text):
        await callback.message.answer(
            'Извините, но использование иностранных символов недопустимо в объявлении, попробуйте еще раз',
            reply_markup=kbc.menu_btn())
        await state.set_state(CustomerStates.customer_menu)
        help_defs.delete_folder(file_path_photo)
        return

    # Проверка на повторяющиеся слова
    is_valid, repeated_word_error = checks.check_repeated_words(all_text, max_repeats=5)
    if not is_valid:
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))

        work_type = await WorkType.get_work_type(id=int(work_type_id))
        work = work_type.work_type.capitalize()

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n')

        text = help_defs.escape_markdown(text=text)

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id),
            city_id=customer.city_id,
            photo_path=photos,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30),
            photos_len=photos_len
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.id}\n'
                f'Telegram ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n\n'
                f'Время: {time}\n'
                f'Причина: Повторяющиеся слова')

        text = help_defs.escape_markdown(text=text)

        # await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

        await bot.send_photo(chat_id=config.BLOCKED_CHAT, photo=FSInputFile(photos['0']), caption=text,
                             protect_content=False,
                             reply_markup=kbc.unban(banned_abs.id, photo_num=0, photo_len=photos_len))

        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await callback.message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                              reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(
                ban_counter=banned.ban_counter + 1,
                ban_now=True,
                ban_end=ban_end,
                ban_reason="Повторяющиеся слова"
            )
            await callback.message.answer(
                '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(
            id=None,
            tg_id=callback.message.chat.id,
            ban_counter=1, ban_end=ban_end, ban_now=True,
            forever=False, ban_reason="Повторяющиеся слова"
        )
        await callback.message.answer(
            '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)
        return

    work_type = await WorkType.get_work_type(id=int(work_type_id))
    work = work_type.work_type.capitalize()

    text = (f'{work}\n\n'
            f'Задача: {task}\n\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    city = await City.get_city(id=customer.city_id)

    advertisements_customer = await Abs.get_all_by_customer(customer_id=customer.id)

    if advertisements_customer:
        old_text = help_defs.read_text_file(advertisements_customer[-1].text_path) if advertisements_customer[
            -1].text_path else "Текст не найден"
        if await checks.are_texts_similar(old_text, text):
            await callback.message.answer(
                'Вы предлагали схожий запрос, удалите предыдущий и попробуйте снова',
                reply_markup=kbc.menu_btn())
            await state.set_state(CustomerStates.customer_menu)
            help_defs.delete_file(file_path_photo)
            return

    text = help_defs.escape_markdown(text=text)
    file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text)

    if time == 'В ближайшее время':
        # 12 часов = 0.5 дня
        delta = 0.5
    elif time == 'Завтра':
        # 24 часа = 1 день
        delta = 1
    elif time == 'В течении недели':
        # 7 дней
        delta = 7
    else:
        # 30 дней
        delta = 30

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id),
        city_id=city.id,
        photo_path=photos,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=delta),
        count_photo=photos_len
    )
    await new_abs.save()

    # Используем ID из объекта, а не последнее объявление из списка
    advertisement = new_abs

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text

    text = help_defs.escape_markdown(text=text)

    # Сразу отвечаем пользователю
    if photos and photos_len > 0 and '0' in photos:
        # Если есть фото, отправляем фото с подписью
        await callback.message.answer_photo(
            photo=FSInputFile(photos['0']),
            caption=text,
            reply_markup=kbc.menu_customer_keyboard(),
        )
    else:
        # Если нет фото, отправляем текстовое сообщение
        await callback.message.answer(text=text, reply_markup=kbc.menu_customer_keyboard())

    await state.set_state(CustomerStates.customer_menu)

    # Уменьшаем счетчик объявлений
    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    # Подготавливаем текст для рассылки
    text_for_workers = (f'{work}\n\n'
                        f'Задача: {task}\n\n'
                        f'Время: {time}\n'
                        f'\n'
                        f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text_for_workers = help_defs.escape_markdown(text=text_for_workers)
    text_for_workers = f'Объявление {advertisement.id}\n\n' + text_for_workers

    # Отправляем в лог-канал
    text2 = f'ID пользователя: #{customer.tg_id}\n\n' + text_for_workers
    if photos and photos_len > 0 and '0' in photos:
        await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG, caption=text2, photo=FSInputFile(photos['0']),
                             protect_content=False,
                             reply_markup=kbc.block_abs_log(advertisement.id, photo_num=0, photo_len=photos_len))
    else:
        # Если нет фото, отправляем только текст
        await bot.send_message(chat_id=config.ADVERTISEMENT_LOG, text=text2,
                               protect_content=False,
                               reply_markup=kbc.block_abs_log(advertisement.id, photo_num=0, photo_len=0))

    # Даем админу 5 секунд на проверку и возможную блокировку объявления
    await asyncio.sleep(5)

    # Проверяем, не было ли объявление заблокировано за это время
    # Если объявления нет в базе, значит админ его заблокировал
    try:
        check_abs = await Abs.get_one(advertisement.id)
        if not check_abs:
            logger.info(f"[BLOCKED] Advertisement {advertisement.id} was blocked by admin, skipping send")
            return
    except Exception as e:
        logger.error(f"Error checking advertisement status: {e}")
        return

    # Запускаем фоновую рассылку исполнителям с фото (только если объявление не было заблокировано)
    asyncio.create_task(
        send_to_workers_background(
            advertisement_id=advertisement.id,
            city_id=customer.city_id,
            work_type_id=int(work_type_id),
            text=text_for_workers,
            photo_path=photos,
            photos_len=photos_len
        )
    )


@router.message(F.photo, CustomerStates.customer_create_abs_add_photo)
async def create_abs_with_photo(message: Message, state: FSMContext) -> None:
    logger.info(f'[CUSTOMER_AD] create_abs_with_photo вызван для пользователя {message.chat.id}')

    kbc = KeyboardCollection()

    # КРИТИЧЕСКАЯ ПРОВЕРКА: убеждаемся, что пользователь действительно в состоянии загрузки фото объявления
    current_state = await state.get_state()
    logger.info(
        f'[CUSTOMER_AD] Текущее состояние: {current_state}, ожидаемое: {CustomerStates.customer_create_abs_add_photo}')

    if current_state != CustomerStates.customer_create_abs_add_photo:
        logger.warning(
            f"[CUSTOMER_AD] КРИТИЧНО: Пропуск обработчика фото объявления - неправильное состояние: {current_state}")
        return

    # Проверяем, что пользователь действительно является заказчиком
    customer = await Customer.get_customer(tg_id=message.chat.id)
    if not customer:
        logger.warning(f"[CUSTOMER_AD] Пропуск обработчика - пользователь не является заказчиком")
        await message.answer("❌ Для загрузки фото объявления необходимо быть зарегистрированным заказчиком")
        return

    logger.info(f'[CUSTOMER_AD] Все проверки пройдены, начинаю обработку фото для объявления')

    # Загружаем данные состояния
    data = await state.get_data()
    album = data.get('album', [])
    end = int(data.get('end', 0))
    processed_groups = data.get('processed_media_groups', [])

    # Проверяем фото через OCR перед добавлением в альбом
    photo = message.photo[-1].file_id
    file_path_photo = await help_defs.save_photo(id=message.from_user.id)
    await bot.download(file=photo, destination=file_path_photo)
    
    text_photo = yandex_ocr.analyze_file(file_path_photo)
    
    if text_photo:
        has_stop_words, has_other_violations = await check_advertisement_ocr_text(text_photo)
        
        if has_stop_words:
            # Стоп-слова - блокируем и отправляем админу (код аналогичен create_abs_skip_photo)
            logger.warning(f"[CUSTOMER_AD] Найдены стоп-слова на фото, блокирую пользователя")
            
            # Сохраняем данные для блокировки
            work_type_id = str(data.get('work_type_id', ''))
            task = str(data.get('task', ''))
            time = str(data.get('time', ''))
            
            # Сохраняем фото для блокировки
            file_path_banned, _ = await help_defs.save_photo_var(id=message.chat.id, n=0)
            banned_photo_path = f'{file_path_banned}0.jpg'
            # Копируем файл для блокировки
            shutil.copy(file_path_photo, banned_photo_path)
            
            # Блокируем пользователя (не отправляем в ADVERTISEMENT_LOG, так как пользователь автоматически блокируется)
            banned = await Banned.get_banned(tg_id=message.chat.id)
            ban_end = str(datetime.now() + timedelta(hours=24))
            
            if work_type_id and work_type_id != 'None':
                work_type = await WorkType.get_work_type(id=int(work_type_id))
                work = work_type.work_type.capitalize() if work_type else 'Не указано'
            else:
                work = 'Не указано'
            
            text = (f'{work}\n\n'
                    f'Задача: {task}\n\n'
                    f'Время: {time}\n')
            
            file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text,
                                                                          path='app/data/banned/text/')
            
            banned_abs = BannedAbs(
                id=None,
                customer_id=customer.id,
                work_type_id=int(work_type_id) if work_type_id and work_type_id != 'None' else 0,
                city_id=customer.city_id,
                photo_path={'0': banned_photo_path},
                text_path=file_path,
                date_to_delite=datetime.today() + timedelta(days=30),
                photos_len=1
            )
            await banned_abs.save()
            
            banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
            banned_abs = banned_abs[-1]
            
            text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                    f'Общий ID пользователя: #{customer.id}\n'
                    f'Telegram ID: #{customer.tg_id}\n\n'
                    f'{work}\n\n'
                    f'Задача: {task}\n\n'
                    f'Время: {time}\n'
                    f'Причина: Текст на фото')
            
            text = help_defs.escape_markdown(text=text)
            
            await bot.send_photo(chat_id=config.BLOCKED_CHAT, photo=FSInputFile(banned_photo_path), caption=text,
                                 protect_content=False,
                                 reply_markup=kbc.unban(banned_abs.id, photo_num=0, photo_len=1))
            
            if banned:
                if banned.ban_counter >= 3:
                    await banned.update(forever=True, ban_now=True)
                    await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                          reply_markup=kbc.support_btn())
                    await state.set_state(BannedStates.banned)
                    return
                await banned.update(
                    ban_counter=banned.ban_counter + 1,
                    ban_now=True,
                    ban_end=ban_end,
                    ban_reason="Текст на фото"
                )
                await message.answer(
                    '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
                    reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            else:
                banned = Banned(
                    id=None,
                    tg_id=customer.tg_id,
                    ban_now=True,
                    ban_end=ban_end,
                    ban_counter=1,
                    forever=False,
                    ban_reason="Текст на фото"
                )
                await banned.save()
                await message.answer(
                    '⛔️ Упс, к сожалению пришлось закрыть Вам доступ на сутки за подозрительную активность.',
                    reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
        
        elif has_other_violations:
            # Другие нарушения - обнуляем state и возвращаем к загрузке
            logger.warning(f"[CUSTOMER_AD] Найдены нарушения на фото, обнуляю state")
            
            # Удаляем временный файл
            help_defs.delete_file(file_path_photo)
            
            # Обнуляем все фото в state
            await state.update_data(album=[], processed_media_groups=[], end=0, msg=None)
            
            # Сообщаем пользователю
            msg_id = data.get('msg')
            if msg_id:
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                except TelegramBadRequest:
                    pass
            
            await message.answer(
                text="⚠️ Фото нарушает правила платформы, его следует заменить!\n\n"
                     "Загрузите другое",
                reply_markup=kbc.done_btn()
            )
            
            # Возвращаем к состоянию загрузки фото
            await state.set_state(CustomerStates.customer_create_abs_add_photo)
            return
    
    # Удаляем временный файл после проверки
    help_defs.delete_file(file_path_photo)
    
    # Проверяем, является ли это частью медиа-группы (альбома)
    if message.media_group_id:
        media_group_id_str = str(message.media_group_id)

        # КРИТИЧНО: Проверяем и помечаем группу атомарно для предотвращения race condition
        # Сначала проверяем, потом помечаем, потом перепроверяем
        if media_group_id_str in processed_groups:
            # Группа уже обрабатывается - только добавляем в альбом и выходим
            if len(album) < 10:
                album.append(message)
                await state.update_data(album=album)
                logger.debug(
                    f"[CUSTOMER_AD] Фото из уже обрабатываемой группы {message.media_group_id} - добавлено в альбом, обработка пропущена")
            else:
                logger.debug(
                    f"[CUSTOMER_AD] Фото из группы {message.media_group_id} пропущено - достигнут лимит 10 фото")
            return

        # Помечаем группу как обрабатываемую СРАЗУ (до добавления в альбом)
        # Это критично для предотвращения параллельной обработки нескольких фото из одного альбома
        processed_groups.append(media_group_id_str)
        await state.update_data(processed_media_groups=processed_groups)
        
        logger.info(f"[CUSTOMER_AD] Группа {media_group_id_str} заблокирована для обработки")

        # Добавляем первое сообщение из группы в альбом (после блокировки), если есть место
        if len(album) < 10:
            album.append(message)
            await state.update_data(album=album)
            logger.info(f"[CUSTOMER_AD] Первое фото из группы {media_group_id_str} добавлено в альбом")
        else:
            logger.info(f"[CUSTOMER_AD] Первое фото из группы {media_group_id_str} пропущено - достигнут лимит 10 фото")
            return
    else:
        # Одиночное фото (не альбом) - добавляем только если есть место
        if len(album) < 10:
            album.append(message)
            await state.update_data(album=album)
        else:
            logger.info(f"[CUSTOMER_AD] Одиночное фото пропущено - достигнут лимит 10 фото")
            return

    # Ограничиваем альбом до 10 фото максимум
    if len(album) > 10:
        album = album[:10]
        await state.update_data(album=album)
        logger.info(f"[CUSTOMER_AD] Альбом обрезан до 10 фото (было больше)")

    # Проверяем лимит фото
    if len(album) >= 10:
        msg_id = data.get('msg')
        try:
            if msg_id and str(msg_id) != 'None':
                try:
                    await bot.delete_message(chat_id=message.from_user.id, message_id=int(msg_id))
                except (TelegramBadRequest, ValueError, TypeError):
                    pass
            msg = await message.answer(text='Больше фото загрузить нельзя\nНажмите, чтобы закончить загрузку',
                                       reply_markup=kbc.done_btn())
            await state.update_data(msg=msg.message_id)
        except TelegramBadRequest:
            pass
        return

    # Отправляем сообщение только один раз при первом фото
    # Используем атомарную проверку и обновление end для предотвращения дублирования
    # при параллельной обработке нескольких фото
    if end == 0:
        # СРАЗУ обновляем end до отправки сообщения, чтобы другие обработчики не отправили его
        await state.update_data(end=1)
        
        # Двойная проверка: перезагружаем данные и проверяем, что мы первые
        # (на случай если другой обработчик уже обновил end между проверкой и обновлением)
        data_check = await state.get_data()
        end_check = int(data_check.get('end', 0))
        
        if end_check == 1:  # Если мы успели первыми обновить end
            msg_id = data.get('msg')
            try:
                if msg_id and str(msg_id) != 'None':
                    try:
                        await bot.delete_message(chat_id=message.from_user.id, message_id=int(msg_id))
                    except (TelegramBadRequest, ValueError, TypeError):
                        pass
                msg = await message.answer(text='Нажмите, чтобы закончить загрузку', reply_markup=kbc.done_btn())
                await state.update_data(msg=msg.message_id)
                logger.info(f"[CUSTOMER_AD] Сообщение 'Нажмите, чтобы закончить загрузку' отправлено")
            except TelegramBadRequest:
                pass
        else:
            # Другой обработчик уже отправил сообщение, просто выходим
            logger.debug(f"[CUSTOMER_AD] Сообщение уже отправлено другим обработчиком, пропускаем")


@router.callback_query(F.data == "customer_change_city", CustomerStates.customer_menu)
async def change_city_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_main...')
    kbc = KeyboardCollection()

    await state.set_state(CustomerStates.customer_change_city)

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.answer(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False, menu_btn=True)
    )
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, CustomerStates.customer_change_city)
async def choose_city_main(message: Message, state: FSMContext) -> None:
    logger.debug(f'choose_city_main...')
    kbc = KeyboardCollection()

    city_input = message.text

    # state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    cities = await City.get_all(sort=False)
    city_names = [city.city for city in cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    found_cities = []

    for idx in city_find:
        if idx < len(cities):
            found_cities.append(cities[idx])

    city_names = [city.city for city in found_cities]
    city_ids = [city.id for city in found_cities]

    msg = await message.answer(
        text=f'Результаты поиска по: {city_input}\n'
             f'Выберите город или напишите его текстом\n',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, menu_btn=True,
                                    btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('go_'), CustomerStates.customer_change_city)
async def change_city_next(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_next...')
    kbc = KeyboardCollection()

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)

    id_now = int(callback.data.split('_')[1])

    btn_next = True if len(city_names) > 5 + id_now else False
    btn_back = True if id_now >= 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.answer(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=btn_back, menu_btn=True))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_change_city)
async def change_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_end...')

    city_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    await customer.update_city(city_id=city_id)

    await callback.answer('Город успешно изменен ✅', show_alert=True)
    await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(
    lambda c: c.data.startswith('extend_') and not c.data.startswith('extend_advertisement_') and not c.data.startswith(
        'extend_24h_') and not c.data.startswith('extend_2d_') and not c.data.startswith('extend_3d_'))
async def extend_abs_time(callback: CallbackQuery, state: FSMContext) -> None:
    kbc = KeyboardCollection()

    abc_id = int(callback.data.split('_')[1])
    await state.set_state(CustomerStates.customer_extend_abc)
    await state.update_data(abc_id=abc_id)

    names = ['В ближайшее время', 'Завтра', 'В течении недели', 'В течении месяца']
    ids = [1, 2, 3, 4]

    await callback.message.answer('Выберите актуальность объявления:\n\n',
                                  reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_extend_abc)
async def create_abs_choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_choose_time...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    abc_id = int(state_data.get('abc_id'))

    advertisement = await Abs.get_one(id=abc_id)

    time_id = int(callback.data.split('_')[1])
    if time_id == 1:
        # В ближайшее время = 12 часов
        await advertisement.update(date_to_delite=datetime.today() + timedelta(hours=12))
    elif time_id == 2:
        # Завтра = 24 часа
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=1))
    elif time_id == 3:
        # В течении недели = 7 дней
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=7))
    else:
        # В течении месяца = 30 дней
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=30))

    await state.set_state(CustomerStates.customer_menu)

    await callback.message.answer('Объявление успешно продлено:\n\n',
                                  reply_markup=kbc.menu_customer_keyboard())


# Функции для оптимизированной рассылки объявлений

async def send_single_message_to_worker(worker: Worker, advertisement_id: int, text: str, photo_path: dict = None,
                                        photos_len: int = 0, retry_count: int = 0):
    """
    Отправляет сообщение одному исполнителю с обработкой ошибок.
    """
    # Проверяем, не отправляли ли уже это сообщение этому исполнителю
    message_key = f"{worker.tg_id}_{advertisement_id}"
    if message_key in _sent_messages:
        logger.warning(
            f'[DEBUG] Message already sent to worker {worker.tg_id} for advertisement {advertisement_id}, skipping')
        return

    # Проверяем активность исполнителя - если не может откликнуться, не отправляем объявление
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

    # Если исполнитель не может откликнуться (красная зона или превышен лимит), не отправляем объявление
    if not can_respond:
        logger.info(
            f'[DEBUG] Worker {worker.tg_id} cannot respond (activity_level={worker.activity_level}, responses_today={responses_today}), skipping advertisement {advertisement_id}')
        return

    # Проверяем, нужно ли отправлять уведомление исполнителю
    from app.untils.notification_helper import should_send_notification
    
    if not await should_send_notification(worker.tg_id, 'worker'):
        logger.info(f'[DEBUG] Notification disabled for worker {worker.tg_id}, skipping advertisement {advertisement_id}')
        return

    try:
        kbc = KeyboardCollection()

        logger.info(
            f'[DEBUG] send_single_message_to_worker: worker_id={worker.tg_id}, advertisement_id={advertisement_id}, retry_count={retry_count}')
        logger.info(
            f'[DEBUG] Photo check: photo_path={photo_path}, photos_len={photos_len}, has_key_0={"0" in photo_path if photo_path else False}')

        if photo_path and photos_len > 0 and '0' in photo_path:
            logger.info(f'[DEBUG] Sending photo to worker {worker.tg_id}')
            # Передаем count_photo и photo_num для возможности листания фото
            await bot.send_photo(
                chat_id=worker.tg_id,
                photo=FSInputFile(photo_path['0']),
                caption=text,
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=advertisement_id,
                    count_photo=photos_len,
                    photo_num=0,
                    abs_list_id=-1  # -1 означает, что это из рассылки (нет списка объявлений)
                )
            )
        else:
            logger.info(f'[DEBUG] Sending text message to worker {worker.tg_id}')
            await bot.send_message(
                chat_id=worker.tg_id,
                text=text,
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_id)
            )

        # Отмечаем сообщение как отправленное
        _sent_messages.add(message_key)
        logger.info(f'[DEBUG] Message sent successfully to worker {worker.tg_id} for advertisement {advertisement_id}')

    except TelegramForbiddenError:
        # Пользователь заблокировал бота - помечаем как неактивного
        logger.debug(f'Worker {worker.tg_id} blocked bot, marking as inactive')
        await worker.update_active(False)
    except TelegramRetryAfter as e:
        # Rate limit - ждем указанное время, но ограничиваем количество попыток
        if retry_count < 3:  # Максимум 3 попытки
            logger.debug(
                f'Rate limit for worker {worker.tg_id}, waiting {e.retry_after} seconds (attempt {retry_count + 1}/3)')
            await asyncio.sleep(e.retry_after)
            # Повторяем отправку с увеличенным счетчиком
            await send_single_message_to_worker(worker, advertisement_id, text, photo_path, photos_len, retry_count + 1)
        else:
            logger.error(f'Max retry attempts reached for worker {worker.tg_id}, skipping')
    except Exception as e:
        logger.error(f"Failed to send message to worker {worker.tg_id}: {e}")


# Глобальные словари для отслеживания активных рассылок и отправленных сообщений
_active_sends = set()
_sent_messages = set()  # Отслеживаем уже отправленные сообщения

# Глобальный семафор для ограничения параллельных отправок (Telegram лимит: 30 сообщений/сек)
# Ленивая инициализация для совместимости
_global_send_semaphore = None


def get_global_semaphore():
    """Получить глобальный семафор (инициализируется при первом вызове)"""
    global _global_send_semaphore
    if _global_send_semaphore is None:
        _global_send_semaphore = asyncio.Semaphore(20)  # Максимум 20 параллельных отправок
    return _global_send_semaphore


async def send_to_workers_background(advertisement_id: int, city_id: int, work_type_id: int, text: str,
                                     photo_path: dict = None, photos_len: int = 0):
    """
    Фоновая рассылка объявлений исполнителям с батчингом и обработкой ошибок.
    """
    # Проверяем, не запущена ли уже рассылка для этого объявления
    send_key = f"{advertisement_id}_{city_id}_{work_type_id}"
    if send_key in _active_sends:
        logger.warning(f'[DEBUG] Send already in progress for advertisement {advertisement_id}, skipping duplicate')
        return

    try:
        # Добавляем в активные рассылки
        _active_sends.add(send_key)

        # Записываем в файл логов
        logger.info(
            f'[DEBUG] Starting send_to_workers_background: city_id={city_id}, work_type_id={work_type_id}, advertisement_id={advertisement_id}')
        logger.info(f'[DEBUG] Photo params: photo_path={photo_path}, photos_len={photos_len}')

        # Используем оптимизированный метод для получения исполнителей
        workers = await Worker.get_active_workers_for_advertisement(city_id, work_type_id)

        if not workers:
            logger.info(f'[DEBUG] No active workers found for city {city_id} and work_type {work_type_id}')
            return

        # ДЕДУПЛИКАЦИЯ: убираем дублирующих исполнителей
        unique_workers = []
        seen_worker_ids = set()
        for worker in workers:
            if worker.tg_id not in seen_worker_ids:
                unique_workers.append(worker)
                seen_worker_ids.add(worker.tg_id)
            else:
                logger.warning(f'[DEBUG] Duplicate worker found: {worker.tg_id}, skipping')

        workers = unique_workers
        logger.info(
            f'[DEBUG] Found {len(workers)} unique workers for advertisement {advertisement_id} (removed {len(await Worker.get_active_workers_for_advertisement(city_id, work_type_id)) - len(workers)} duplicates)')
        logger.info(f'[DEBUG] Starting background send to {len(workers)} workers for advertisement {advertisement_id}')

        # Логируем всех исполнителей
        worker_ids = [worker.tg_id for worker in workers]
        logger.info(f'[DEBUG] Worker IDs: {worker_ids}')

        # Отправляем по 3 сообщения в батче с паузой (оптимизировано для Telegram: макс 30 сообщений/сек)
        # При множественных объявлениях это предотвратит превышение лимитов
        batch_size = 3
        for i in range(0, len(workers), batch_size):
            batch = workers[i:i + batch_size]
            batch_worker_ids = [worker.tg_id for worker in batch]
            logger.info(f'[DEBUG] Processing batch {i // batch_size + 1}: workers {batch_worker_ids}')

            # Создаем задачи для параллельной отправки с использованием глобального семафора
            semaphore = get_global_semaphore()

            async def send_with_semaphore(worker):
                async with semaphore:
                    return await send_single_message_to_worker(worker, advertisement_id, text, photo_path, photos_len)

            tasks = [send_with_semaphore(worker) for worker in batch]

            # Выполняем батч параллельно
            await asyncio.gather(*tasks, return_exceptions=True)

            # Пауза между батчами для соблюдения rate limits (увеличено до 1 сек для безопасности)
            if i + batch_size < len(workers):
                await asyncio.sleep(1.0)  # 1 секунда пауза между батчами

        # Обновляем счетчик просмотров один раз для всего объявления
        advertisement = await Abs.get_one(advertisement_id)
        if advertisement:
            await advertisement.update(views=len(workers))

        logger.debug(f'Completed background send to workers for advertisement {advertisement_id}')

    except Exception as e:
        logger.error(f"Error in background send to workers: {e}")
    finally:
        # Убираем из активных рассылок
        _active_sends.discard(send_key)

        # Очищаем старые записи об отправленных сообщениях для этого объявления
        # (оставляем только записи для других объявлений)
        global _sent_messages
        _sent_messages = {key for key in _sent_messages if not key.endswith(f'_{advertisement_id}')}
        logger.debug(f'[DEBUG] Cleaned up sent messages for advertisement {advertisement_id}')


# Обработчики для системы оценки исполнителей

@router.callback_query(lambda c: c.data.startswith('rate-worker_'))
async def rate_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик оценки исполнителя заказчиком"""
    logger.debug(f'rate_worker...')

    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    rating = int(parts[3])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer:
        await callback.answer("Ошибка: заказчик не найден", show_alert=True)
        return


    # Проверяем, что заказчик еще не оценивал этого исполнителя
    from app.data.database.models import WorkerRating
    existing_rating = await WorkerRating.get_by_worker_and_abs(worker_id, abs_id)

    if existing_rating:
        await callback.answer("Вы уже оценили этого исполнителя", show_alert=True)
        return

    # Создаем оценку
    worker_rating = WorkerRating(
        id=None,  # ID будет автоматически присвоен при сохранении
        worker_id=worker_id,
        customer_id=customer.id,
        abs_id=abs_id,
        rating=rating
    )
    await worker_rating.save()

    # Обновляем рейтинг исполнителя
    worker = await Worker.get_worker(id=worker_id)
    worker_prefix = worker.profile_name if worker.profile_name else 'ID ' + str(worker_id)
    if worker:
        # Проверяем, что у исполнителя есть поле activity_level
        if not hasattr(worker, 'activity_level') or worker.activity_level is None:
            worker.activity_level = 100  # Значение по умолчанию

        total_stars = worker.stars + rating
        total_ratings = worker.count_ratings + 1
        await worker.update_stars(stars=total_stars, count_ratings=total_ratings)

        # УВЕЛИЧИВАЕМ СЧЕТЧИК ВЫПОЛНЕННЫХ ЗАКАЗОВ
        # Каждая оценка = выполненный заказ (защита от двойной оценки уже есть выше)
        from app.data.database.models import WorkerAndRefsAssociation

        # Увеличиваем счетчики (каждая оценка учитывается)
        await worker.update_order_count(order_count=worker.order_count + 1)
        await worker.update_order_count_on_week(order_count_on_week=worker.order_count_on_week + 1)

        # Проверяем реферальную программу (5 заказов)
        if worker.order_count + 1 == 5:
            if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                await worker_and_ref.update(work_condition=True)
                if worker_and_ref.ref_condition:
                    await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                    from loaders import bot
                    await bot.send_message(chat_id=worker_and_ref.ref_id,
                                           text='Условия вашей реферальной программы выполнены!')
                    await bot.send_message(chat_id=worker.tg_id,
                                           text='Условия вашей реферальной программы выполнены!')
            elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                await worker_and_ref.update(ref_condition=True)
                if worker_and_ref.work_condition:
                    await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                    worker_main = await Worker.get_worker(id=worker_and_ref.worker_id)
                    from loaders import bot
                    await bot.send_message(chat_id=worker_and_ref.ref_id,
                                           text='Условия вашей реферальной программы выполнены!')
                    await bot.send_message(chat_id=worker_main.tg_id,
                                           text='Условия вашей реферальной программы выполнены!')

        # Восстанавливаем активность исполнителя (+20 за выполнение заказа)
        old_activity = worker.activity_level
        new_activity = max(0, min(100, worker.activity_level + 20))

        # Обновляем активность с fallback
        if hasattr(worker, 'change_activity_level'):
            new_activity = await worker.change_activity_level(20)
        else:
            # Fallback: используем универсальную функцию
            from app.handlers.worker import update_worker_activity_fallback
            await update_worker_activity_fallback(worker, new_activity)

        # Отправляем уведомление об изменении активности
        await send_activity_notification(worker, old_activity, new_activity)

        # МГНОВЕННОЕ ОБНОВЛЕНИЕ РАНГА при оценке исполнителя
        await update_worker_rank_instantly(worker, state)

    # Проверяем, есть ли еще исполнители для оценки
    # Используем abs_id из состояния или из callback_data
    state_data = await state.get_data()
    abs_id_from_state = state_data.get('pending_advertisement_id')
    # Если нет в состоянии, используем abs_id из callback_data (для автоматического закрытия)
    if not abs_id_from_state:
        abs_id_from_state = abs_id  # Используем abs_id из параметров функции

    # Проверяем, нужно ли удалить объявление после оценки
    # (удаляем только если нет больше исполнителей для оценки)
    should_delete_advertisement = False
    try:
        advertisement = await Abs.get_one(id=abs_id_from_state)
        if advertisement:
            # Проверяем, есть ли еще исполнители для оценки
            from app.data.database.models import ContactExchange, WorkerRating
            contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id_from_state)
            remaining_workers_count = 0

            for contact_exchange in contact_exchanges:
                if contact_exchange.contacts_purchased and contact_exchange.worker_id != worker_id:
                    existing_rating = await WorkerRating.get_by_worker_and_abs(contact_exchange.worker_id,
                                                                               abs_id_from_state)
                    if not existing_rating:
                        remaining_workers_count += 1

            # Если нет больше исполнителей для оценки - помечаем объявление для удаления
            if remaining_workers_count == 0:
                should_delete_advertisement = True
    except Exception as e:
        logger.error(f"Error checking advertisement status: {e}")

    if should_delete_advertisement:
        try:
            # Удаляем объявление после последней оценки
            await advertisement.delete(delite_photo=True)

            # Удаляем связанные записи
            from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange, WorkersAndAbs
            workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id_from_state)
            if workers_and_bad_responses:
                [await bad_response.delete() for bad_response in workers_and_bad_responses]

            workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id_from_state)
            if workers_and_reports:
                [await report.delete() for report in workers_and_reports]

            contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id_from_state)
            if contact_exchanges:
                [await exchange.delete() for exchange in contact_exchanges]

            workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id_from_state)
            if workers_and_abs:
                [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

            # Обновляем статистику админов
            from app.data.database.models import Admin
            admins = await Admin.get_all()
            for admin in admins:
                await admin.update(done_abs=admin.done_abs + 1)
        except Exception as e:
            logger.error(f"Error cleaning up advertisement after rating: {e}")

    # Проверяем, есть ли еще исполнители для оценки
    abs_id = abs_id_from_state

    if abs_id:
        # Получаем оставшихся исполнителей для оценки (купили контакты и еще не оценены)
        from app.data.database.models import ContactExchange, WorkerRating
        contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
        remaining_workers = []

        for contact_exchange in contact_exchanges:
            if contact_exchange.contacts_purchased and contact_exchange.worker_id != worker_id:
                # Проверяем, не оценен ли уже этот исполнитель
                existing_rating = await WorkerRating.get_by_worker_and_abs(contact_exchange.worker_id, abs_id)
                if not existing_rating:  # Только если еще не оценен
                    worker = await Worker.get_worker(id=contact_exchange.worker_id)
                    if worker:
                        remaining_workers.append(worker)

        if remaining_workers:
            await callback.answer(
                f"Спасибо!\n\n"
                f"Вы поставили оценку исполнителя {worker_prefix}: ⭐ {rating} из 5",
                show_alert=True
            )

            # Есть еще исполнители для оценки - показываем их
            names = []
            for worker in remaining_workers:
                rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
                worker_name = worker.profile_name if worker.profile_name else f"ID {worker.id}"
                names.append(
                    f'{worker_name} ⭐ {rating_display} ({count_ratings} {help_defs.get_rating_word(count_ratings)})'
                )
            ids = [worker.id for worker in remaining_workers]

            kbc = KeyboardCollection()
            await callback.message.answer(
                f"Выберите следующего исполнителя для оценки:",
                reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
            )
            return

    # Нет больше исполнителей для оценки - показываем финальное сообщение
    await callback.answer(
        f"Вы поставили оценку исполнителя {worker_prefix}: ⭐ {rating} из 5\n"
        f"Спасибо за обратную связь. Оценка завершена!",
    )
    await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(lambda c: c.data.startswith('view_responses_'))
async def view_responses_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'К откликам' - возвращает к списку откликов"""
    try:
        # view_responses_{abs_id}
        abs_id = int(callback.data.split('_')[2])

        # Получаем отклики на объявление
        responses = await WorkersAndAbs.get_by_abs(abs_id)

        if not responses:
            kbc = KeyboardCollection()
            await callback.message.answer(
                text="📭 <b>На это объявление пока нет откликов</b>\n\n"
                     "Ожидайте откликов от исполнителей.",
                reply_markup=kbc.menu_btn(),
                parse_mode='HTML'
            )
            return

        # Формируем список откликов для отображения
        responses_data = []
        for response in responses:
            worker = await Worker.get_worker(id=response.worker_id)
            if worker:
                # Проверяем статус контактов
                contact_exchange = await ContactExchange.get_by_worker_and_abs(response.worker_id, abs_id)

                # Получаем индикатор статуса
                from app.handlers.anonymous_chat import get_response_status_indicator
                status_indicator = await get_response_status_indicator(response, "customer")

                responses_data.append({
                    'worker_id': response.worker_id,
                    'worker_name': worker.profile_name,  # Только profile_name, не tg_name
                    'worker_stars': worker.stars,
                    'worker_ratings': worker.count_ratings,
                    'status_indicator': status_indicator,
                    'active': response.applyed  # Добавляем поле active для fallback в keyboards.py
                })

        # Получаем объявление для контекста
        advertisement = await Abs.get_one(id=abs_id)
        city_name = "Неизвестно"
        if advertisement:
            city = await City.get_city(id=advertisement.city_id)
            if city:
                city_name = city.city

        kbc = KeyboardCollection()
        text = f"📋 <b>Отклики на объявление #{abs_id}</b>\n"
        text += f"🏙️ Город: {city_name}\n"
        text += f"👥 Количество откликов: {len(responses_data)}\n\n"
        
        # Добавляем текст объявления
        if advertisement and advertisement.text_path:
            ad_text = help_defs.read_text_file(advertisement.text_path) or ""
            if ad_text:
                # Ограничиваем длину текста объявления
                MAX_AD_TEXT_LENGTH = 2000
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"
                text += f"📝 <b>Текст объявления:</b>\n{ad_text}\n"
        
        text += "Выберите отклик для просмотра:"

        # Безопасное редактирование (может быть фото)
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
            # Если было фото, удаляем и отправляем новое
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

    except Exception as e:
        logger.error(f"Error in view_responses_handler: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('customer-responses_'))
async def customer_view_responses(callback: CallbackQuery, state: FSMContext):
    """Заказчик просматривает отклики на свое объявление"""
    try:
        # customer-responses_{abs_id}_{id_now}
        # Разбиваем по дефису, затем по подчеркиванию
        main_parts = callback.data.split('-')
        if len(main_parts) < 2:
            await callback.answer("❌ Неверный формат callback данных", show_alert=True)
            return

        # Берем часть после "customer-responses_"
        data_part = main_parts[1]  # "responses_{abs_id}_{id_now}"
        parts = data_part.split('_')

        logger.info(f"[CUSTOMER_RESPONSES] Callback data: {callback.data}")
        logger.info(f"[CUSTOMER_RESPONSES] Main parts: {main_parts}")
        logger.info(f"[CUSTOMER_RESPONSES] Data part: {data_part}")
        logger.info(f"[CUSTOMER_RESPONSES] Parts: {parts}")

        if len(parts) < 3:
            await callback.answer("❌ Неверный формат callback данных", show_alert=True)
            return

        abs_id = int(parts[1])  # {abs_id}

        # Получаем отклики на объявление
        responses = await WorkersAndAbs.get_by_abs(abs_id)

        if not responses:
            kbc = KeyboardCollection()
            # Используем безопасное редактирование сообщения
            from app.untils.message_utils import safe_edit_message
            await safe_edit_message(
                callback=callback,
                text="📭 <b>На это объявление пока нет откликов</b>\n\n"
                     "Ожидайте откликов от исполнителей.",
                reply_markup=kbc.menu_btn(),
            )
            return

        # Формируем список откликов для отображения
        responses_data = []
        for response in responses:
            worker = await Worker.get_worker(id=response.worker_id)
            if worker:
                # Проверяем статус контактов
                contact_exchange = await ContactExchange.get_by_worker_and_abs(response.worker_id, abs_id)

                # Получаем индикатор статуса
                from app.handlers.anonymous_chat import get_response_status_indicator
                status_indicator = await get_response_status_indicator(response, "customer")

                responses_data.append({
                    'worker_id': response.worker_id,
                    'worker_name': worker.profile_name,  # Только profile_name, не tg_name
                    'worker_stars': worker.stars,
                    'worker_ratings': worker.count_ratings,
                    'status_indicator': status_indicator,
                    'active': response.applyed  # Добавляем поле active для fallback в keyboards.py
                })

        # Получаем объявление для контекста
        advertisement = await Abs.get_one(id=abs_id)
        city_name = "Неизвестно"
        if advertisement:
            city = await City.get_city(id=advertisement.city_id)
            if city:
                city_name = city.city

        kbc = KeyboardCollection()
        # Формируем текст с объявлением
        response_text = f"📋 <b>Отклики на объявление #{abs_id}</b>\n"
        response_text += f"🏙️ Город: {city_name}\n"
        response_text += f"👥 Количество откликов: {len(responses_data)}\n\n"
        
        # Добавляем текст объявления
        if advertisement and advertisement.text_path:
            ad_text = help_defs.read_text_file(advertisement.text_path) or ""
            if ad_text:
                # Ограничиваем длину текста объявления
                MAX_AD_TEXT_LENGTH = 2000
                if len(ad_text) > MAX_AD_TEXT_LENGTH:
                    ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"
                response_text += f"📝 <b>Текст объявления:</b>\n{ad_text}"
        
        response_text += "Выберите отклик для просмотра:"
        
        # Используем безопасное редактирование сообщения
        from app.untils.message_utils import safe_edit_message
        await safe_edit_message(
            callback=callback,
            text=response_text,
            reply_markup=kbc.customer_responses_list_buttons(
                responses_data=responses_data,
                abs_id=abs_id
            ),
        )

    except Exception as e:
        logger.error(f"Error in customer_view_responses: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def send_activity_notification(worker, old_activity: int, new_activity: int):
    """Отправляет уведомление об изменении активности исполнителя"""
    from loaders import bot

    # Определяем зоны активности
    def get_zone(activity):
        if activity >= 74:
            return "зеленую"
        elif activity >= 48:
            return "желтую"
        elif activity >= 9:
            return "оранжевую"
        else:
            return "красную"

    old_zone = get_zone(old_activity)
    new_zone = get_zone(new_activity)

    # Отправляем уведомление только при переходе между зонами
    if old_zone != new_zone:
        if old_zone == "красную" and new_zone == "оранжевую":
            message = "🟠 Хорошая новость! Ваша активность выросла, и доступ к заказам частично восстановлен. Продолжайте повышать активность, чтобы снять все ограничения."
        elif old_zone == "оранжевую" and new_zone == "желтую":
            message = "🟡 Отлично! Вы улучшили свою активность — ещё немного, и вы вернётесь в зелёную зону!"
        elif old_zone == "желтую" and new_zone == "зеленую":
            message = "🟢 Поздравляем! Вы снова в зелёной зоне активности. Теперь у вас полный доступ к заказам. Так держать!"
        else:
            message = f"📈 Ваша активность изменилась: {old_activity} → {new_activity}"

        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=message
            )
        except Exception as e:
            logger.error(f"Error sending activity notification to worker {worker.tg_id}: {e}")


async def update_worker_rank_instantly(worker: Worker, state: FSMContext):
    """
    Обновляет ранг исполнителя НЕМЕДЛЕННО после действия,
    влияющего на ранг (например, получение оценки).
    """
    try:
        from app.data.database.models import WorkerRank, WorkerAndSubscription
        from loaders import bot
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        logger.info(f'update_worker_rank_instantly: Updating rank for worker {worker.id}')

        # Получаем старый ранг
        old_rank = await WorkerRank.get_by_worker(worker.id)
        old_rank_type = old_rank.rank_type if old_rank else None
        old_work_types_limit = old_rank.get_work_types_limit() if old_rank else 1

        # Обновляем ранг (пересчитываем на основе заказов за последние 30 дней)
        new_rank = await WorkerRank.get_or_create_rank(worker.id)
        new_work_types_limit = new_rank.get_work_types_limit()

        # Проверяем, изменился ли ранг
        if old_rank_type and old_rank_type != new_rank.rank_type:
            rank_levels = {'bronze': 1, 'silver': 2, 'gold': 3, 'platinum': 4}
            old_level = rank_levels.get(old_rank_type, 0)
            new_level = rank_levels.get(new_rank.rank_type, 0)

            if new_level > old_level:
                # ПОВЫШЕНИЕ РАНГА - отправляем уведомление мгновенно
                logger.info(
                    f'update_worker_rank_instantly: Worker {worker.id} upgraded from {old_rank_type} to {new_rank.rank_type}')

                # Проверяем, может ли исполнитель выбрать больше направлений
                from app.data.database.models import WorkerAndSubscription, WorkerWorkTypeChanges
                worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                current_work_types_count = len(
                    worker_sub.work_type_ids) if worker_sub and worker_sub.work_type_ids else 0

                # Если новый лимит больше текущего количества направлений - разрешаем выбор
                if new_work_types_limit is None or current_work_types_count < new_work_types_limit:
                    # Устанавливаем флаг pending_selection для разрешения выбора направлений
                    work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)
                    work_type_changes.pending_selection = True
                    await work_type_changes.save()

                    logger.info(
                        f'update_worker_rank_instantly: Set pending_selection=True for worker {worker.id} (can choose more work types)')

                try:
                    old_rank_name = WorkerRank.RANK_TYPES[old_rank_type]['name']
                    old_rank_emoji = WorkerRank.RANK_TYPES[old_rank_type]['emoji']
                    new_rank_name = new_rank.get_rank_name()
                    new_rank_emoji = new_rank.get_rank_emoji()

                    notification_text = (
                        f"🎉 <b>Повышение ранга!</b>\n\n"
                        f"Ваш ранг изменился:\n"
                        f"{old_rank_emoji} <b>{old_rank_name}</b> → {new_rank_emoji} <b>{new_rank_name}</b>\n\n"
                        f"📊 <b>Новый лимит направлений:</b>\n"
                        f"Было доступно: <b>{old_work_types_limit if old_work_types_limit else 'без ограничений'}</b>\n"
                        f"Стало доступно: <b>{new_work_types_limit if new_work_types_limit else 'без ограничений'}</b>\n\n"
                        f"🎯 <b>Что это дает:</b>\n"
                    )

                    # Добавляем информацию о преимуществах нового ранга
                    if new_rank.rank_type == 'silver':
                        notification_text += "• Доступно до 5 направлений работы\n• Приоритет в показе объявлений"
                    elif new_rank.rank_type == 'gold':
                        notification_text += "• Доступно до 10 направлений работы\n• Высокий приоритет в показе объявлений"
                    elif new_rank.rank_type == 'platinum':
                        notification_text += "• Доступны все направления без ограничений\n• Максимальный приоритет в показе объявлений"

                    # Если можно выбрать больше направлений - добавляем информацию
                    if new_work_types_limit is None or current_work_types_count < new_work_types_limit:
                        notification_text += f"\n\n🎯 <b>Можете выбрать больше направлений!</b>\nПерейдите в 'Мои направления' для выбора новых направлений работы."

                    notification_text += f"\n\n💡 Продолжайте выполнять качественные заказы для поддержания высокого ранга!"

                    # Отправляем уведомление
                    kbc = KeyboardCollection()
                    await bot.send_message(
                        chat_id=worker.tg_id,
                        text=notification_text,
                        parse_mode='HTML',
                        reply_markup=kbc.worker_rank_up_keyboard()
                    )

                    await state.set_state(WorkStates.worker_menu)

                    # storage = state.storage
                    # worker_key = StorageKey(bot_id=bot.id, chat_id=worker.tg_id, user_id=worker.tg_id)
                    # worker_state = FSMContext(storage=storage, key=worker_key)
                    # await worker_state.set_state(WorkStates.worker_menu)

                    logger.info(f'update_worker_rank_instantly: Sent rank upgrade notification to worker {worker.id}')

                except Exception as notify_error:
                    logger.error(
                        f'update_worker_rank_instantly: Failed to send upgrade notification to worker {worker.id} - {notify_error}')

            elif new_level < old_level:
                # ПОНИЖЕНИЕ РАНГА - НЕ отправляем уведомление мгновенно
                # Оставляем это для ежедневной проверки в 00:00
                logger.info(
                    f'update_worker_rank_instantly: Worker {worker.id} downgraded from {old_rank_type} to {new_rank.rank_type} - notification will be sent at 00:00')

        else:
            logger.info(f'update_worker_rank_instantly: Worker {worker.id} rank unchanged ({new_rank.rank_type})')

    except Exception as e:
        logger.error(f'update_worker_rank_instantly: Error updating rank for worker {worker.id} - {e}')


# ========== ОБРАБОТЧИКИ ДЛЯ КОНТАКТОВ ЗАКАЗЧИКА ==========

@router.callback_query(F.data == 'customer_contacts', CustomerStates.customer_menu)
async def customer_contacts_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Меню контактов заказчика"""
    logger.debug(f'customer_contacts_menu...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    if customer.has_contacts():
        # Контакты уже настроены - показываем текущие контакты
        contact_info = customer.get_contact_info()
        text = f"<b>Ваши контакты:</b>\n\n{contact_info}"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu(),
            parse_mode='HTML'
        )
    else:
        # Контакты не настроены - показываем меню выбора
        text = "Здесь вы можете указать, какие контакты будут отправлены исполнителю:"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_menu()
        )

    await state.set_state(CustomerStates.customer_contacts)


@router.callback_query(F.data == 'customer_contacts', CustomerStates.customer_contacts)
async def customer_contacts_back_from_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из меню редактирования в основное меню контактов"""
    logger.debug(f'customer_contacts_back_from_edit...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    if customer.has_contacts():
        # Контакты уже настроены - показываем текущие контакты
        contact_info = customer.get_contact_info()
        text = f"<b>Ваши контакты:</b>\n\n{contact_info}"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu(),
            parse_mode='HTML'
        )
    else:
        # Контакты не настроены - показываем меню выбора
        text = "Здесь вы можете указать, какие контакты будут отправлены исполнителю:"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_menu()
        )

    await state.set_state(CustomerStates.customer_contacts)


@router.callback_query(F.data == 'customer_contacts', CustomerStates.customer_contacts_phone_input)
async def customer_contacts_back_from_phone_input(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из ввода номера телефона в меню контактов"""
    logger.debug(f'customer_contacts_back_from_phone_input...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    if customer.has_contacts():
        # Контакты уже настроены - показываем текущие контакты
        contact_info = customer.get_contact_info()
        text = f"<b>Ваши контакты:</b>\n\n{contact_info}"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu(),
            parse_mode='HTML'
        )
    else:
        # Контакты не настроены - показываем меню выбора
        text = "Здесь вы можете указать, какие контакты будут отправлены исполнителю:"

        await callback.message.answer(
            text=text,
            reply_markup=kbc.customer_contacts_menu()
        )

    await state.set_state(CustomerStates.customer_contacts)


@router.callback_query(F.data == 'contact_telegram_only', CustomerStates.customer_contacts)
async def set_telegram_only_contacts(callback: CallbackQuery, state: FSMContext) -> None:
    """Установка только профиля Telegram"""
    logger.debug(f'set_telegram_only_contacts...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    await customer.update_contacts(contact_type="telegram_only")

    text = "✅ Ваши контакты сохранены!\n\n Исполнители будут получать только ваш профиль Telegram 📱"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.menu_customer_keyboard()
    )

    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(F.data == 'contact_add_phone', CustomerStates.customer_contacts)
async def request_phone_number(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос номера телефона"""
    logger.debug(f'request_phone_number...')

    kbc = KeyboardCollection()

    text = "Пожалуйста, введите номер телефона в формате +7XXXXXXXXXX"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_back_menu()
    )

    await state.update_data(contact_type="phone_only")
    await state.set_state(CustomerStates.customer_contacts_phone_input)


@router.callback_query(F.data == 'contact_both', CustomerStates.customer_contacts)
async def request_phone_number_both(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос номера телефона для обоих вариантов"""
    logger.debug(f'request_phone_number_both...')

    kbc = KeyboardCollection()

    text = "Пожалуйста, введите номер телефона в формате +7XXXXXXXXXX"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_back_menu()
    )

    await state.update_data(contact_type="both")
    await state.set_state(CustomerStates.customer_contacts_phone_input)


@router.message(CustomerStates.customer_contacts_phone_input)
async def process_phone_number(message: Message, state: FSMContext) -> None:
    """Обработка введенного номера телефона"""
    logger.debug(f'process_phone_number...')

    kbc = KeyboardCollection()
    phone_number = message.text.strip()

    # Простая валидация номера телефона
    import re
    if not re.match(r'^\+7\d{10}$', phone_number):
        await message.answer(
            "❌ Неверный формат номера. Пожалуйста, введите номер в формате +7XXXXXXXXXX",
            reply_markup=kbc.customer_contacts_back_menu()
        )
        return

    # Получаем тип контактов из состояния
    data = await state.get_data()
    contact_type = data.get('contact_type', 'phone_only')

    customer = await Customer.get_customer(tg_id=message.chat.id)
    await customer.update_contacts(contact_type=contact_type, phone_number=phone_number)

    # Формируем сообщение в зависимости от типа контактов
    if contact_type == "phone_only":
        text = f"✅ Ваши контакты сохранены!\n\n Исполнители будут получать номер (который вы указали) 📞"
    else:  # both
        text = f"✅ Ваши контакты сохранены!\n\n Исполнители будут получать профиль Telegram 📱 и номер (который вы указали) 📞"

    await message.answer(
        text=text,
        reply_markup=kbc.menu_customer_keyboard()
    )

    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(F.data == 'edit_contacts', CustomerStates.customer_contacts)
async def edit_contacts_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Меню редактирования контактов"""
    logger.debug(f'edit_contacts_menu...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    text = "Выберите, что хотите изменить:"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_edit_menu(customer.contact_type)
    )

    await state.set_state(CustomerStates.customer_contacts)


@router.callback_query(F.data == 'edit_telegram_only', CustomerStates.customer_contacts)
async def edit_to_telegram_only(callback: CallbackQuery, state: FSMContext) -> None:
    """Изменение контактов на только Telegram"""
    logger.debug(f'edit_to_telegram_only...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    await customer.update_contacts(contact_type="telegram_only", phone_number=None)

    text = "✅ Контакты изменены!\n\n Теперь исполнители будут получать только ваш профиль Telegram 📱"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_display_menu()
    )


@router.callback_query(F.data == 'edit_phone_only', CustomerStates.customer_contacts)
async def edit_to_phone_only(callback: CallbackQuery, state: FSMContext) -> None:
    """Изменение контактов на только номер телефона"""
    logger.debug(f'edit_to_phone_only...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Всегда запрашиваем новый номер для изменения
    if customer.phone_number:
        text = f"Текущий номер: {customer.phone_number}\n\nВведите новый номер телефона в формате +7XXXXXXXXXX"
    else:
        text = "Введите номер телефона в формате +7XXXXXXXXXX"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_back_menu()
    )
    await state.update_data(contact_type="phone_only")
    await state.set_state(CustomerStates.customer_contacts_phone_input)


@router.callback_query(F.data == 'edit_both', CustomerStates.customer_contacts)
async def edit_to_both(callback: CallbackQuery, state: FSMContext) -> None:
    """Изменение контактов на Telegram и номер"""
    logger.debug(f'edit_to_both...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Всегда запрашиваем новый номер для изменения
    if customer.phone_number:
        text = f"Текущий номер: {customer.phone_number}\n\nВведите новый номер телефона в формате +7XXXXXXXXXX"
    else:
        text = "Введите номер телефона в формате +7XXXXXXXXXX"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_back_menu()
    )
    await state.update_data(contact_type="both")
    await state.set_state(CustomerStates.customer_contacts_phone_input)


@router.callback_query(F.data == 'confirm_delete_phone', CustomerStates.customer_contacts)
async def confirm_delete_phone(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение удаления номера телефона"""
    logger.debug(f'confirm_delete_phone...')

    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    await customer.update_contacts(contact_type="telegram_only", phone_number=None)

    text = "✅ Номер удален успешно! Теперь исполнители будут получать только ваш профиль Telegram! 📱"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.customer_contacts_back_menu()
    )


# ========== ПРОВЕРКА КОНТАКТОВ ПРИ ОТПРАВКЕ ИСПОЛНИТЕЛЮ ==========

async def check_customer_contacts(customer_id: int) -> bool:
    """Проверяет, настроены ли контакты у заказчика"""
    customer = await Customer.get_customer(id=customer_id)
    return customer.has_contacts() if customer else False


# ========== ПРОСМОТР ПОРТФОЛИО ИСПОЛНИТЕЛЯ ЗАКАЗЧИКОМ ==========

@router.callback_query(lambda c: c.data.startswith('worker-portfolio_'))
async def customer_view_worker_portfolio(callback: CallbackQuery, state: FSMContext):
    """Заказчик просматривает портфолио исполнителя"""
    try:
        # worker-portfolio_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        logger.info(f"[CUSTOMER_PORTFOLIO] Callback data: {callback.data}, parts: {parts}")

        if len(parts) < 3:
            logger.error(f"[CUSTOMER_PORTFOLIO] Invalid callback data format: {callback.data}")
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        worker_id = int(parts[1])
        abs_id = int(parts[2])

        logger.info(
            f"[CUSTOMER_PORTFOLIO] Customer {callback.from_user.id} viewing portfolio: worker_id={worker_id}, abs_id={abs_id}")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Проверяем, что заказчик имеет доступ к этому объявлению
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement or advertisement.customer_id != customer.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return

        # Проверяем наличие портфолио
        if not worker.portfolio_photo or len(worker.portfolio_photo) == 0:
            await callback.answer("❌ У исполнителя нет портфолио", show_alert=True)
            return

        # Показываем первое фото из портфолио
        kbc = KeyboardCollection()

        photo_len = len(worker.portfolio_photo)
        # Получаем первый доступный ключ из словаря портфолио
        first_photo_key = min(worker.portfolio_photo.keys(), key=int)
        first_photo_path = worker.portfolio_photo[first_photo_key]

        text = f"📸 <b>Портфолио исполнителя</b>\n\n"
        text += f"👤 <b>ID:</b> {worker.id}\n"
        text += f"📋 <b>Имя:</b> {worker.profile_name or 'Не указано'}\n"
        text += f"🖼️ <b>Фото в портфолио:</b> {photo_len}\n\n"
        text += f"Фото 1 из {photo_len}"

        try:
            # Всегда отправляем новое сообщение с фото портфолио
            await callback.message.answer_photo(
                photo=FSInputFile(first_photo_path),
                caption=text,
                reply_markup=kbc.worker_portfolio_1(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    photo_num=0,
                    photo_len=photo_len
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error sending portfolio photo: {e}")
            await callback.answer("❌ Ошибка при загрузке фото", show_alert=True)

        await callback.answer()

    except Exception as e:
        logger.error(f"Error in customer_view_worker_portfolio: {e}")
        await callback.answer("❌ Произошла ошибка при просмотре портфолио", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('go-to-portfolio_') and len(c.data.split('_')) == 4)
async def customer_navigate_worker_portfolio(callback: CallbackQuery, state: FSMContext):
    """Навигация по портфолио исполнителя заказчиком"""
    try:
        # go-to-portfolio_{photo_num}_{worker_id}_{abs_id}
        parts = callback.data.split('_')
        logger.info(f"[CUSTOMER_PORTFOLIO_NAV] Callback data: {callback.data}, parts: {parts}")

        if len(parts) < 4:
            logger.error(f"[CUSTOMER_PORTFOLIO_NAV] Invalid callback data format: {callback.data}")
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        photo_num = int(parts[1])
        worker_id = int(parts[2])
        abs_id = int(parts[3])

        logger.info(
            f"[CUSTOMER_PORTFOLIO_NAV] Customer {callback.from_user.id} navigating portfolio: worker_id={worker_id}, abs_id={abs_id}, photo_num={photo_num}")

        customer = await Customer.get_customer(tg_id=callback.from_user.id)
        if not customer:
            await callback.answer("❌ Заказчик не найден", show_alert=True)
            return

        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Проверяем, что заказчик имеет доступ к этому объявлению
        advertisement = await Abs.get_one(id=abs_id)
        if not advertisement or advertisement.customer_id != customer.id:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return

        # Проверяем наличие портфолио
        if not worker.portfolio_photo or len(worker.portfolio_photo) == 0:
            await callback.answer("❌ У исполнителя нет портфолио", show_alert=True)
            return

        photo_len = len(worker.portfolio_photo)

        # Получаем отсортированные ключи из словаря портфолио
        sorted_keys = sorted(worker.portfolio_photo.keys(), key=int)

        # Обработка циклической навигации
        if photo_num < 0:
            photo_num = len(sorted_keys) - 1
        elif photo_num >= len(sorted_keys):
            photo_num = 0

        # Получаем реальный ключ по индексу
        real_key = sorted_keys[photo_num]

        # Показываем фото
        kbc = KeyboardCollection()

        photo_path = worker.portfolio_photo[real_key]

        text = f"📸 <b>Портфолио исполнителя</b>\n\n"
        text += f"👤 <b>ID:</b> {worker.id}\n"
        text += f"📋 <b>Имя:</b> {worker.profile_name or 'Не указано'}\n"
        text += f"🖼️ <b>Фото в портфолио:</b> {photo_len}\n\n"
        text += f"Фото {photo_num + 1} из {photo_len}"

        try:
            # Пытаемся отредактировать существующее сообщение
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=text,
                    parse_mode='HTML'
                ),
                reply_markup=kbc.worker_portfolio_1(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    photo_num=photo_num,
                    photo_len=photo_len
                )
            )
        except TelegramBadRequest as e:
            # Сообщение не найдено или его нельзя отредактировать
            logger.warning(f"[CUSTOMER_PORTFOLIO_NAV] Cannot edit message: {e}. Sending new message instead.")
            try:
                # Пытаемся удалить старое сообщение (если оно еще существует)
                await callback.message.delete()
            except TelegramBadRequest:
                # Сообщение уже удалено, это нормально
                pass

            # Отправляем новое сообщение с фото
            await callback.message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=text,
                reply_markup=kbc.worker_portfolio_1(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    photo_num=photo_num,
                    photo_len=photo_len
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            # Любая другая ошибка
            logger.error(f"[CUSTOMER_PORTFOLIO_NAV] Unexpected error updating portfolio photo: {e}")
            try:
                # Пытаемся отправить новое сообщение
                await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=text,
                    reply_markup=kbc.worker_portfolio_1(
                        worker_id=worker_id,
                        abs_id=abs_id,
                        photo_num=photo_num,
                        photo_len=photo_len
                    ),
                    parse_mode='HTML'
                )
            except Exception as send_error:
                logger.error(f"[CUSTOMER_PORTFOLIO_NAV] Error sending new message: {send_error}")
                await callback.answer("❌ Произошла ошибка при отображении портфолио", show_alert=True)

        await callback.answer()

    except Exception as e:
        logger.error(f"Error in customer_navigate_worker_portfolio: {e}")
        await callback.answer("❌ Произошла ошибка при навигации по портфолио", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('extend_advertisement_'))
async def extend_advertisement_handler(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Продлить' при истечении объявления"""
    logger.debug(f'extend_advertisement_handler...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[2])

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text='⏰ Выберите период продления:',
        reply_markup=kbc.extend_advertisement_periods(abs_id)
    )


@router.callback_query(
    lambda c: c.data.startswith('extend_24h_') or c.data.startswith('extend_2d_') or c.data.startswith('extend_3d_'))
async def extend_advertisement_period_handler(callback: CallbackQuery) -> None:
    """Обработчик выбора периода продления"""
    logger.debug(f'extend_advertisement_period_handler...')

    parts = callback.data.split('_')
    period = parts[1]  # 24h, 2d, 3d
    abs_id = int(parts[2])

    # Получаем объявление
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Определяем период продления
    from datetime import timedelta
    if period == '24h':
        extension = timedelta(hours=24)
        period_text = "24 часа"
    elif period == '2d':
        extension = timedelta(days=2)
        period_text = "2 дня"
    elif period == '3d':
        extension = timedelta(days=3)
        period_text = "3 дня"
    else:
        await callback.answer("Неверный период", show_alert=True)
        return

    # Обновляем срок истечения и обнуляем флаг отправки уведомления
    new_date = advertisement.date_to_delite + extension
    await advertisement.update(date_to_delite=new_date, expiry_notification_sent=False)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    # Показываем всплывающее сообщение
    await callback.answer(f"✅ Срок актуальности объявления продлен на {period_text}!", show_alert=True)

    # Получаем данные заказчика для формирования текста меню
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    await help_defs.send_customer_menu(callback, customer)


@router.callback_query(lambda c: c.data.startswith('dont_extend_advertisement_'))
async def dont_extend_advertisement_handler(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Не продлять'"""
    logger.debug(f'dont_extend_advertisement_handler...')

    await callback.answer("❌ Вы отменили продление объявления!", show_alert=True)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    # Получаем данные заказчика для формирования текста меню
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Send customer menu
    await help_defs.send_customer_menu(callback, customer)


@router.callback_query(lambda c: c.data.startswith('close_advertisement_'))
async def close_advertisement_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Закрыть' (без оценки) - показывает подтверждение"""
    logger.debug(f'close_advertisement_handler...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[2])

    # Получаем объявление для отображения информации
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    text = help_defs.read_text_file(advertisement.text_path)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text=f'⚠️ Вы уверены, что хотите закрыть объявление #{abs_id}?\n\n'
             f'{text}\n\n'
             f'После закрытия объявление будет удалено без возможности восстановления.',
        reply_markup=kbc.confirm_close_advertisement_expiry(abs_id)
    )


@router.callback_query(lambda c: c.data.startswith('confirm_close_expiry_'))
async def confirm_close_advertisement_expiry_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение закрытия объявления при истечении"""
    logger.debug(f'confirm_close_advertisement_expiry_handler...')

    abs_id = int(callback.data.split('_')[3])

    # Получаем объявление
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Удаляем объявление
    await advertisement.delete(delite_photo=True)

    # Удаляем связанные записи
    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
    if workers_and_bad_responses:
        [await bad_response.delete() for bad_response in workers_and_bad_responses]

    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
    if workers_and_reports:
        [await report.delete() for report in workers_and_reports]

    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    if contact_exchanges:
        [await exchange.delete() for exchange in contact_exchanges]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
    if workers_and_abs:
        [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

    # Обновляем статистику админов
    admins = await Admin.get_all()
    for admin in admins:
        await admin.update(done_abs=admin.done_abs + 1)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.answer(
        text='✅ Объявление было успешно закрыто!',
    )

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(lambda c: c.data.startswith('cancel_close_expiry_'))
async def cancel_close_advertisement_expiry_handler(callback: CallbackQuery) -> None:
    """Отмена закрытия объявления при истечении"""
    logger.debug(f'cancel_close_advertisement_expiry_handler...')

    kbc = KeyboardCollection()

    await callback.answer("❌ Закрытие объявления отменено", show_alert=True)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text='Объявление остается активным.',
        reply_markup=kbc.menu_customer_keyboard()
    )


@router.callback_query(lambda c: c.data.startswith('close_and_rate_'))
async def close_and_rate_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Закрыть и оценить' - показывает подтверждение"""
    logger.debug(f'close_and_rate_handler...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[3])  # close_and_rate_abs_id

    # Получаем объявление для отображения информации
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    text = help_defs.read_text_file(advertisement.text_path)

    # Проверяем, есть ли исполнители для оценки
    from app.data.database.models import ContactExchange
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    workers_for_assessment = []

    for contact_exchange in contact_exchanges:
        if contact_exchange.contacts_purchased:  # Купил контакты
            worker = await Worker.get_worker(id=contact_exchange.worker_id)
            if worker:
                workers_for_assessment.append(worker)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if workers_for_assessment:
        await callback.message.answer(
            text=f'⚠️ Вы уверены, что хотите закрыть объявление #{abs_id} и оценить исполнителей?\n\n'
                 f'{text}\n\n'
                 f'После закрытия вы сможете оценить {len(workers_for_assessment)} исполнителей.',
            reply_markup=kbc.confirm_close_and_rate_advertisement_expiry(abs_id)
        )
    else:
        await callback.message.answer(
            text=f'⚠️ Вы уверены, что хотите закрыть объявление #{abs_id}?\n\n'
                 f'{text}\n\n'
                 f'Исполнителей для оценки не найдено.',
            reply_markup=kbc.confirm_close_advertisement_expiry(abs_id)
        )


@router.callback_query(lambda c: c.data.startswith('confirm_close_and_rate_expiry_'))
async def confirm_close_and_rate_advertisement_expiry_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение закрытия и оценки объявления при истечении"""
    logger.debug(f'confirm_close_and_rate_advertisement_expiry_handler...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[5])  # confirm_close_and_rate_expiry_abs_id

    # Получаем объявление
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Находим исполнителей для оценки (купили контакты и еще не оценены)
    from app.data.database.models import ContactExchange, WorkerRating
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    workers_for_assessment = []

    for contact_exchange in contact_exchanges:
        if contact_exchange.contacts_purchased:  # Купил контакты
            worker = await Worker.get_worker(id=contact_exchange.worker_id)
            if worker:
                # Проверяем, не оценен ли уже этот исполнитель
                existing_rating = await WorkerRating.get_by_worker_and_abs(contact_exchange.worker_id, abs_id)
                if not existing_rating:  # Только если еще не оценен
                    workers_for_assessment.append(worker)

    # НЕ удаляем объявление сразу - удалим после оценки
    # await advertisement.delete(delite_photo=True)

    # НЕ удаляем связанные записи сразу - удалим после оценки
    # from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, WorkersAndAbs
    # workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
    # if workers_and_bad_responses:
    #     [await bad_response.delete() for bad_response in workers_and_bad_responses]

    # workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
    # if workers_and_reports:
    #     [await report.delete() for report in workers_and_reports]

    # contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    # if contact_exchanges:
    #     [await exchange.delete() for exchange in contact_exchanges]

    # workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
    # if workers_and_abs:
    #     [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

    # НЕ обновляем статистику админов сразу - обновим после оценки
    # from app.data.database.models import Admin
    # admins = await Admin.get_all()
    # for admin in admins:
    #     await admin.update(done_abs=admin.done_abs + 1)

    # Если есть исполнители для оценки - показываем их
    if workers_for_assessment:
        names = []
        for worker in workers_for_assessment:
            rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
            worker_name = worker.profile_name if worker.profile_name else f"ID {worker.id}"
            names.append(
                f'{worker_name} ⭐ {rating_display} ({count_ratings} {help_defs.get_rating_word(count_ratings)})'
            )
        ids = [worker.id for worker in workers_for_assessment]

        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Сохраняем abs_id в состоянии для последующего удаления
        await state.update_data(pending_advertisement_id=abs_id)

        try:
            await callback.message.edit_text(
                text='✅ Объявление закрыто!\n\nВыберите исполнителей для оценки:',
                reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
            )
        except Exception:
            await callback.message.answer(
                text='✅ Объявление закрыто!\n\nВыберите исполнителей для оценки:',
                reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
            )
    else:
        # Нет исполнителей для оценки - удаляем объявление и закрываем
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        # Удаляем объявление, так как нет исполнителей для оценки
        await advertisement.delete(delite_photo=True)

        # Удаляем связанные записи
        from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, WorkersAndAbs
        workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
        if workers_and_bad_responses:
            [await bad_response.delete() for bad_response in workers_and_bad_responses]

        workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
        if workers_and_reports:
            [await report.delete() for report in workers_and_reports]

        contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
        if contact_exchanges:
            [await exchange.delete() for exchange in contact_exchanges]

        workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
        if workers_and_abs:
            [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]

        # Обновляем статистику админов
        from app.data.database.models import Admin
        admins = await Admin.get_all()
        for admin in admins:
            await admin.update(done_abs=admin.done_abs + 1)

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        await callback.answer(
            text='Объявление закрыто ✅\n\nИсполнителей для оценки не найдено!',
            show_alert=True
        )
        await help_defs.send_customer_menu(callback, customer, state)


@router.callback_query(lambda c: c.data.startswith('cancel_close_and_rate_expiry_'))
async def cancel_close_and_rate_advertisement_expiry_handler(callback: CallbackQuery) -> None:
    """Отмена закрытия и оценки объявления при истечении"""
    logger.debug(f'cancel_close_and_rate_advertisement_expiry_handler...')

    kbc = KeyboardCollection()

    await callback.answer("❌ Закрытие и оценка объявления отменены", show_alert=True)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text='Объявление остается активным.',
        reply_markup=kbc.menu_customer_keyboard()
    )

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
