import logging
import asyncio
from datetime import datetime, timedelta

from pydantic_core import ValidationError
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, FSInputFile, LabeledPrice, PreCheckoutQuery, InputMediaPhoto, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

import config
import loaders
from app.data.database.models import Customer, Worker, City, Banned, WorkType, Abs, \
    WorkerAndSubscription, WorkersAndAbs, Admin, BannedAbs, WorkerAndBadResponse, WorkerAndReport, ContactExchange
from app.keyboards import KeyboardCollection
from app.states import UserStates, CustomerStates, BannedStates
from app.untils import help_defs, checks, yandex_ocr
from app.untils.customer_proces import ban_task, same_task, close_task
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(F.data == "registration_customer", UserStates.registration_end)
async def registration_new_customer(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'registration_new_customer...')
    kbc = KeyboardCollection()
    state_data = await state.get_data()
    city_id = int(state_data.get('city_id'))
    username = str(state_data.get('username'))

    new_customer = Customer(
        id=None,
        tg_id=callback.message.chat.id,
        city_id=city_id,
        tg_name=username)
    await new_customer.save()
    await callback.message.edit_text(
        text='''Вы успешно зарегистрированы''',
        reply_markup=kbc.menu_btn()
    )
    await state.set_state(CustomerStates.customer_menu)


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

    msg = await callback.message.edit_text(
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

    msg_id = int(state_data.get('msg_id'))

    cities = await City.get_all(sort=False)
    city_names = [city.city for city in cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    cities = []

    for city_id in city_find:
        city = await City.get_city(id=city_id)
        cities.append(city)

    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]

    msg = await message.answer(
        text=f'Результаты поиска по: {city_input}\n'
             f'Выберите город или напишите его текстом\n',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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
        msg = await callback.message.edit_text(
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

    await callback.message.edit_text(
        text='''Вы успешно зарегистрированы''',
        reply_markup=kbc.menu_btn_reg()
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
        text = '''Упс, вы еще не зарегистрированы как заказчик'''
        await callback.message.edit_text(text=text, reply_markup=kbc.registration_customer())
        if worker := await Worker.get_worker(tg_id=callback.message.chat.id):
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(worker.city_id[0]), username=str(worker.tg_name))
            return

    user_abs = await Abs.get_all_by_customer(customer.id)
    city = await City.get_city(id=int(customer.city_id))

    if user_worker := await Worker.get_worker(tg_id=tg_id):
        if user_worker.active:
            await user_worker.update_active(active=False)

    text = ('Ваш профиль\n\n'
            f'ID: {customer.id}\n'
            f'Ваш город: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
            f'Осталось объявлений на сегодня: {customer.abs_count}')

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(CustomerStates.customer_menu)
    await callback.message.answer(text=text,
                                  reply_markup=kbc.menu_customer_keyboard())  # Кнопка покупки объявлений убрана - размещение всегда бесплатно


@router.callback_query(F.data == 'customer_menu')
async def customer_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_menu...')

    kbc = KeyboardCollection()

    tg_id = callback.message.chat.id

    customer = await Customer.get_customer(tg_id=tg_id)

    if customer is None:
        text = 'Упс, вы еще не зарегистрированы как заказчик'
        await callback.message.edit_text(text=text, reply_markup=kbc.registration_customer())
        if worker := await Worker.get_worker(tg_id=callback.message.chat.id):
            logger.debug('go as worker')
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(worker.city_id[0]), username=str(worker.tg_name))
            return
        if admin := await Admin.get_by_tg_id(tg_id=callback.message.chat.id):
            logger.debug('go as admin')
            await state.set_state(UserStates.registration_enter_city)
            await state.update_data(username=str(admin.tg_name))
            return
        return

    if user_worker := await Worker.get_worker(tg_id=tg_id):
        if user_worker.active:
            await user_worker.update_active(active=False)

    user_abs = await Abs.get_all_by_customer(customer.id)
    city = await City.get_city(id=int(customer.city_id))

    text = ('Ваш профиль\n\n'
            f'ID: {customer.id}\n'
            f'Ваш город: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
            f'Осталось объявлений на сегодня: {customer.abs_count}')

    await state.set_state(CustomerStates.customer_menu)
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_customer_keyboard()
    )


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

    # ВРЕМЕННОЕ РЕШЕНИЕ ДЛЯ РАЗРАБОТКИ - обходим платежную систему
    # В продакшене замените на реальную платежную систему
    try:
        # Симулируем успешную покупку
        await customer.update_abs_count(abs_count=customer.abs_count + 1)
        
        await callback.message.answer(
            text=f"✅ **Разработка: Покупка успешна!**\n\n"
                 f"💰 Стоимость: {admin.order_price}₽ (симуляция)\n"
                 f"📊 Количество: 1 объявление\n"
                 f"📈 Доступно размещений: {customer.abs_count}\n\n"
                 f"⚠️ *Это временное решение для разработки*",
            reply_markup=kbc.menu_customer_keyboard(),
            parse_mode='Markdown'
        )
        await state.set_state(CustomerStates.customer_menu)
        return
        
    except Exception as e:
        logger.error(f"Ошибка при симуляции покупки: {e}")
        await callback.message.answer(
            text="❌ Ошибка при обработке покупки",
            reply_markup=kbc.menu_customer_keyboard()
        )
        await state.set_state(CustomerStates.customer_menu)
        return

    # ОРИГИНАЛЬНЫЙ КОД ДЛЯ ПРОДАКШЕНА (закомментирован)
    # try:
    #     await callback.message.answer_invoice(
    #         title=f"Дополнительное размещение",
    #         description=text,
    #         provider_token=config.PAYMENTS,
    #         currency="RUB",  # Валюта в верхнем регистре
    #         prices=prices,
    #         start_parameter="one-month-subscription",
    #         payload="invoice-payload",
    #         reply_markup=kbc.customer_buy_order(),
    #         need_email=True,
    #         send_email_to_provider=True
    #     )
    #     await state.update_data(customer_id=str(customer.id),
    #                            order_price=admin.order_price)
    # except TelegramBadRequest as e:
    #     logger.error(f"Payment provider error: {e}")
    #     # Обрабатываем ошибку недоступности платежного метода
    #     if "PAYMENT_PROVIDER_INVALID" in str(e):
    #         error_text = "❌ Платежный метод недоступен\n\n"
    #         error_text += "🚫 К сожалению, в вашей стране недоступны платежные методы Telegram.\n\n"
    #         error_text += "💡 Возможные решения:\n"
    #         error_text += "• Используйте VPN для смены региона\n"
    #         error_text += "• Обратитесь к администратору для альтернативной оплаты\n"
    #         error_text += "• Попробуйте позже\n\n"
    #         error_text += "📞 Для получения помощи обратитесь в поддержку"
    #         
    #         await callback.message.answer(
    #             text=error_text,
    #             reply_markup=kbc.menu_customer_keyboard()
    #         )
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
        reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(F.data == 'create_new_abs', CustomerStates.customer_menu)
async def create_new_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_new_abs...')

    kbc = KeyboardCollection()

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    # Проверяем лимит объявлений
    if customer.abs_count <= 0:
        await callback.answer(
            "❌ Лимит бесплатных объявлений исчерпан!\n\n"
            "У вас осталось 0 объявлений на сегодня.\n"
            "Для размещения дополнительного объявления необходимо его приобрести.",
            show_alert=True
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

    await callback.message.edit_text(text='Выберете направление',
                                     reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.callback_query(F.data == 'back', CustomerStates.customer_create_abs_work_type)
async def create_new_abs_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_new_abs_back...')

    kbc = KeyboardCollection()

    tg_id = callback.message.chat.id

    customer = await Customer.get_customer(tg_id=tg_id)

    user_abs = await Abs.get_all_by_customer(customer.id)
    city = await City.get_city(id=int(customer.city_id))

    text = ('Ваш профиль\n\n'
            f'ID: {customer.id}\n'
            f'Ваш город: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
            f'Осталось объявлений на сегодня: {customer.abs_count}')

    await state.set_state(CustomerStates.customer_menu)
    await callback.message.edit_text(text=text,
                                     reply_markup=kbc.menu_customer_keyboard())


async def get_customer_ads_optimized(customer_id: int):
    """Оптимизированное получение всех данных объявлений заказчика одним запросом"""
    import aiosqlite
    
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute('''
            SELECT 
                a.id, a.work_type_id, a.city_id, a.text_path, a.photo_path, 
                a.views, a.count_photo,
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
        await callback.message.edit_text(text='У вас пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(CustomerStates.customer_menu)
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


    text = f'Объявление {abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
    logger.debug(f"text {text}")
    
    # Используем количество откликов из оптимизированного запроса
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
                                            reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                      btn_back=False,
                                                                                      btn_close=True,
                                                                                      btn_responses=btn_responses,
                                                                                      btn_close_name=btn_close_name,
                                                                                      abs_id=abs_now['id'],
                                                                                      count_photo=abs_now['count_photo'],
                                                                                      idk_photo=0))
            else:
                # Файл не существует - отправляем только текст
                logger.warning(f"Photo file not found: {photo_path}")
                await callback.message.answer(text=text,
                                              reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                        btn_back=False,
                                                                                        btn_close=True,
                                                                                        btn_responses=btn_responses,
                                                                                        btn_close_name=btn_close_name,
                                                                                        abs_id=abs_now['id']))
    else:
        await callback.message.edit_text(text=text,
                                         reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                   btn_back=False,
                                                                                   btn_close=True,
                                                                                   btn_responses=btn_responses,
                                                                                   btn_close_name=btn_close_name,
                                                                                   abs_id=abs_now['id']))


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


    text = f'Объявление {abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
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


    text = f'Объявление {abs_now["id"]} г. {city_name}\n\n' + text + f'\n\nПросмотров: {abs_now["views"]}'
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

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now['id'])

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

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
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
        return


# Функция просмотра откликов полностью удалена


# Функция просмотра конкретного отклика полностью удалена


# Функции обработки платежей за отклики полностью удалены


# Функция отклонения отклика заказчиком полностью удалена


# Функция ответа заказчика исполнителю полностью удалена


# Функция обработки сообщений от заказчика полностью удалена


@router.callback_query(lambda c: c.data.startswith('close_'), CustomerStates.customer_check_abs)
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
             f'После закрытия вы сможете оценить исполнителей, которые откликнулись и купили ваши контакты.',
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
    
    # Находим исполнителей для оценки (купили контакты)
    # Логика: если исполнитель купил контакты, значит он откликнулся И передал контакты
    workers_for_assessment = []
    
    from app.data.database.models import ContactExchange
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    
    if contact_exchanges:
        for contact_exchange in contact_exchanges:
            if contact_exchange.contacts_purchased:  # Купил контакты
                worker = await Worker.get_worker(id=contact_exchange.worker_id)
                if worker:
                    workers_for_assessment.append(worker)
    
    # Удаляем объявление сразу после подтверждения закрытия
    await advertisement.delete(delite_photo=True)
    
    # Удаляем связанные записи
    from app.data.database.models import WorkerAndBadResponse, WorkerAndReport, ContactExchange
    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=abs_id)
    if workers_and_bad_responses:
        [await bad_response.delete() for bad_response in workers_and_bad_responses]
    
    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=abs_id)
    if workers_and_reports:
        [await report.delete() for report in workers_and_reports]
    
    contact_exchanges = await ContactExchange.get_by_abs(abs_id=abs_id)
    if contact_exchanges:
        [await exchange.delete() for exchange in contact_exchanges]
    
    # Удаляем записи откликов
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)
    if workers_and_abs:
        [await worker_and_abs.delete() for worker_and_abs in workers_and_abs]
    
    # Обновляем статистику админов
    admins = await Admin.get_all()
    for admin in admins:
        await admin.update(done_abs=admin.done_abs + 1)
    
    # Если есть исполнители для оценки - показываем их
    if workers_for_assessment:
        names = [
            f'{worker.profile_name if worker.profile_name else "Исполнитель"} ID {worker.id} ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}'
            for worker in workers_for_assessment
        ]
        ids = [worker.id for worker in workers_for_assessment]
        
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        
        # Сохраняем abs_id в состоянии для последующего удаления
        await state.update_data(pending_advertisement_id=abs_id)
        
        await callback.message.answer(
            text='✅ Объявление закрыто!\n\nВыберите исполнителей для оценки:',
            reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=abs_id)
        )
    else:
        # Нет исполнителей для оценки - просто закрываем
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        
        await callback.message.answer(
            text='✅ Объявление закрыто!\n\nИсполнителей для оценки не найдено.',
            reply_markup=kbc.menu()
        )
        await state.set_state(CustomerStates.customer_menu)


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
            names = [
                f'{worker.profile_name if worker.profile_name else "Исполнитель"} ID {worker.id} ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} '
                for worker in
                workers_for_assessments]
            ids = [worker.id for worker in workers_for_assessments]
            await state.clear()
            await advertisement_now.delete(delite_photo=True)

            await callback.message.answer(text='Выберите исполнителя для оценки',
                                          reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=advertisement_now.id))

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

    await callback.message.answer(text='Объявление закрыто!', reply_markup=kbc.menu())


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
    worker_rating = round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars
    worker_orders = worker.count_ratings if worker.count_ratings else 0
    
    text = f'👤 **Информация об исполнителе:**\n\n'
    text += f'• ID: {worker_id}\n'
    text += f'• Имя: {worker_name}\n'
    text += f'• Рейтинг: {worker_rating} ⭐\n'
    text += f'• Выполнено заказов: {worker_orders}\n\n'
    text += f'📝 **Оцените качество работы исполнителя:**'
    
    try:
        await callback.message.delete()
        await callback.message.answer(
            text=text,
            reply_markup=kbc.set_rating(worker_id=worker_id, abs_id=abs_id),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.debug(e)


# Старая система оценки удалена - теперь используется rate_worker


@router.callback_query(F.data == 'skip-star-for-worker')
async def skip_star_for_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'skip_star_for_worker...')
    kbc = KeyboardCollection()
    
    # Объявление уже удалено в confirm_close_advertisement
    
    await state.set_state(CustomerStates.customer_menu)
    await callback.message.edit_text(
        text='✅ Оценка завершена!\n\nОбъявление закрыто. Спасибо за использование сервиса!',
        reply_markup=kbc.menu()
    )


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_create_abs_work_type)
async def create_abs_work_type(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type...')

    kbc = KeyboardCollection()
    work_type_id = int(callback.data.split('_')[1])
    work_type = await WorkType.get_work_type(id=work_type_id)

    template_text = help_defs.read_text_file(work_type.template) if work_type.template else "Пример объявления не найден"
    text = f'Пример объявления для {work_type.work_type}\n\n' + template_text

    if work_type.template_photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(photo=FSInputFile(work_type.template_photo), caption=text,
                                            parse_mode='HTML')
        return

    example_msg = await callback.message.edit_text(text=text, parse_mode='HTML')

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
    await callback.message.answer(text='Выберете тип работы', reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.message(F.text, CustomerStates.customer_create_abs_task)
async def customer_create_abs_price(message: Message, state: FSMContext) -> None:
    logger.debug(f'customer_create_abs_price... {message.text}')

    kbc = KeyboardCollection()

    # Проверяем контент на запрещенные элементы
    from app.untils.help_defs import handle_forbidden_content
    if await handle_forbidden_content(message, bot):
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
        msg = await message.answer('⚠️ Упс, похоже вы пытаетесь предложить запрос без подробностей, повторите попытку снова.\n\nУкажите задачу: (не более 800 символов)',
                                   reply_markup=kbc.back_btn())
        await state.update_data(msg_id=msg.message_id)
        return

    if len(task) > 800:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except TelegramBadRequest:
            pass
        msg = await message.answer('Укажите задачу: (не более 800 символов)',
                                   reply_markup=kbc.back_btn())
        await state.update_data(msg_id=msg.message_id)
        return

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

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

    msg = await callback.message.edit_text(text='Укажите задачу: (не более 800 символов)', reply_markup=kbc.back_btn())
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

    await state.set_state(CustomerStates.customer_create_abs_add_photo)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(task=task)
    await state.update_data(time=time)
    await state.update_data(end=0)
    msg = await callback.message.edit_text(text='Прикрепите фото, или нажмите кнопку пропустить',
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

    try:
        msg = await callback.message.edit_text('Подождите идет проверка')
    except TelegramBadRequest:
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

    if checks.phone_finder(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔',
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
            'Упс, похоже у вас некорректный текст, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        return

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
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
    await callback.message.answer(text=text, reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)
    
    # Уменьшаем счетчик объявлений
    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    # Подготавливаем текст для рассылки
    text_for_workers = (f'{work}\n\n'
                       f'Задача: {task}\n'
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

    # Запускаем фоновую рассылку исполнителям
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

    msg = str(state_data.get('msg'))
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    time = str(state_data.get('time'))
    album = state_data.get('album', [])

    photo = None

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg, )
    msg = await callback.message.answer(text='Подождите идет проверка')

    text_photo_bool = False

    photos = {}
    photos_len = len(album)

    for i, obj in enumerate(album):
        if obj.photo:
            file_id = obj.photo[-1].file_id
        else:
            file_id = obj[obj.content_type].file_id

        file_path, _ = await help_defs.save_photo_var(id=callback.message.chat.id, n=i)
        file_path_photo = f'{file_path}{i}.jpg'
        await bot.download(file=file_id, destination=file_path_photo)
        text_photo = yandex_ocr.analyze_file(file_path_photo)

        if text_photo:
            if await checks.fool_check(text=text_photo):
                text_photo_bool = True

        print(file_path_photo)

        help_defs.add_watermark(file_path_photo)
        photos[str(i)] = file_path_photo

    file_path_photo = None

    if text_photo_bool:
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))

        work_type = await WorkType.get_work_type(id=int(work_type_id))
        work = work_type.work_type.capitalize()

        customer = await Customer.get_customer(tg_id=callback.message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n'
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
                f'Общий ID пользователя: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f''
                f'Причина: Текст на фото')

        text = help_defs.escape_markdown(text=text)

        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

        await bot.send_photo(chat_id=config.BLOCKED_CHAT, photo=FSInputFile(photos['0']), caption=text, protect_content=False,
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
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(id=None, tg_id=callback.message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False, ban_reason="текст на фото")
        await callback.message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
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
                f'Задача: {task}\n'
                f'Время: {time}\n')

        text = help_defs.escape_markdown(text=text)

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')
        if not photo:
            file_path_photo = await help_defs.save_photo(id=callback.message.from_user.id,
                                                         path='app/data/banned/photo/')
            await bot.download(file=photo, destination=file_path_photo)

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
                f'ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f''
                f'Причина блокировки: {ban_reason}')

        text = help_defs.escape_markdown(text=text)

        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

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
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
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
            'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        help_defs.delete_folder(file_path_photo)
        return

    if checks.contains_gibberish(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await callback.message.answer(
            'Упс, похоже у вас некорректный текст, вернитесь в меню и создайте объявление заново 🤔',
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

    work_type = await WorkType.get_work_type(id=int(work_type_id))
    work = work_type.work_type.capitalize()

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    city = await City.get_city(id=customer.city_id)

    advertisements_customer = await Abs.get_all_by_customer(customer_id=customer.id)

    if advertisements_customer:
        old_text = help_defs.read_text_file(advertisements_customer[-1].text_path) if advertisements_customer[-1].text_path else "Текст не найден"
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
    await callback.message.answer(text=text, reply_markup=kbc.menu_customer_keyboard())
    await state.set_state(CustomerStates.customer_menu)
    
    # Уменьшаем счетчик объявлений
    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    # Подготавливаем текст для рассылки
    text_for_workers = (f'{work}\n\n'
                       f'Задача: {task}\n'
                       f'Время: {time}\n'
                       f'\n'
                       f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text_for_workers = help_defs.escape_markdown(text=text_for_workers)
    text_for_workers = f'Объявление {advertisement.id}\n\n' + text_for_workers

    # Отправляем в лог-канал
    text2 = f'ID пользователя: #{customer.tg_id}\n\n' + text_for_workers
    await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG, caption=text2, photo=FSInputFile(photos['0']), protect_content=False,
                           reply_markup=kbc.block_abs_log(advertisement.id, photo_num=0, photo_len=photos_len))

    # Запускаем фоновую рассылку исполнителям с фото
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
    logger.debug(f'create_abs_with_photo...')

    kbc = KeyboardCollection()

    # Загружаем данные состояния
    data = await state.get_data()
    album = data.get('album', [])
    end = int(data.get('end'))

    if len(album) == 10:
        msg = str(data.get('msg'))
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
            msg = await message.answer(text='Больше фото загрузить нельзя\nНажмите, чтобы закончить загрузку',
                                       reply_markup=kbc.done_btn())
            await state.update_data(msg=msg.message_id)
        except TelegramBadRequest:
            pass
        return

    album.append(message)
    await state.update_data(album=album)
    if end == 0:
        msg = str(data.get('msg'))
        try:
            await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
            msg = await message.answer(text='Нажмите, чтобы закончить загрузку', reply_markup=kbc.done_btn())
            await state.update_data(msg=msg.message_id)
        except TelegramBadRequest:
            pass

    if len(album) < 10:
        return

    if len(album) > 10:
        return


# Функция принятия отклика look-worker-it_ полностью удалена


# Функция worker_portfolio удалена - использовалась только для откликов


# Функция worker_portfolio (go-to-portfolio) удалена - использовалась только для откликов


# Функция send_worker_with_msg удалена - использовалась только для откликов


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

    msg = await callback.message.edit_text(
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

    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id'))

    cities = await City.get_all(sort=False)
    city_names = [city.city for city in cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    cities = []

    for city_id in city_find:
        city = await City.get_city(id=city_id)
        cities.append(city)

    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]

    msg = await message.answer(
        text=f'Результаты поиска по: {city_input}\n'
             f'Выберите город или напишите его текстом\n',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, menu_btn=True,
                                    btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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

    msg = await callback.message.edit_text(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=btn_back, menu_btn=True))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_change_city)
async def change_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_end...')
    kbc = KeyboardCollection()

    city_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    await customer.update_city(city_id=city_id)

    await callback.message.edit_text('Вы успешно сменили город!', reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(lambda c: c.data.startswith('extend_'))
async def extend_abs_time(callback: CallbackQuery, state: FSMContext) -> None:
    kbc = KeyboardCollection()

    abc_id = int(callback.data.split('_')[1])
    await state.set_state(CustomerStates.customer_extend_abc)
    await state.update_data(abc_id=abc_id)

    names = ['В ближайшее время', 'Завтра', 'В течении недели', 'В течении месяца']
    ids = [1, 2, 3, 4]

    await callback.message.answer('Выберите актуальность объявления:\n\n', reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


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
                                  reply_markup=kbc.menu())


# Функции для оптимизированной рассылки объявлений

async def send_single_message_to_worker(worker: Worker, advertisement_id: int, text: str, photo_path: dict = None, photos_len: int = 0):
    """
    Отправляет сообщение одному исполнителю с обработкой ошибок.
    """
    try:
        kbc = KeyboardCollection()
        
        logger.info(f'[DEBUG] send_single_message_to_worker: worker_id={worker.tg_id}, advertisement_id={advertisement_id}')
        logger.info(f'[DEBUG] Photo check: photo_path={photo_path}, photos_len={photos_len}, has_key_0={"0" in photo_path if photo_path else False}')
        
        if photo_path and photos_len > 0 and '0' in photo_path:
            logger.info(f'[DEBUG] Sending photo to worker {worker.tg_id}')
            await bot.send_photo(
                chat_id=worker.tg_id,
                photo=FSInputFile(photo_path['0']),
                caption=text,
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_id)
            )
        else:
            logger.info(f'[DEBUG] Sending text message to worker {worker.tg_id}')
            await bot.send_message(
                chat_id=worker.tg_id,
                text=text,
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_id)
            )
        
        # Обновляем счетчик просмотров
        advertisement = await Abs.get_one(advertisement_id)
        if advertisement:
            await advertisement.update(views=1)
            
    except TelegramForbiddenError:
        # Пользователь заблокировал бота - помечаем как неактивного
        logger.debug(f'Worker {worker.tg_id} blocked bot, marking as inactive')
        await worker.update_active(False)
    except TelegramRetryAfter as e:
        # Rate limit - ждем указанное время
        logger.debug(f'Rate limit for worker {worker.tg_id}, waiting {e.retry_after} seconds')
        await asyncio.sleep(e.retry_after)
        # Повторяем отправку
        await send_single_message_to_worker(worker, advertisement_id, text, photo_path, photos_len)
    except Exception as e:
        logger.error(f"Failed to send message to worker {worker.tg_id}: {e}")


async def send_to_workers_background(advertisement_id: int, city_id: int, work_type_id: int, text: str, photo_path: dict = None, photos_len: int = 0):
    """
    Фоновая рассылка объявлений исполнителям с батчингом и обработкой ошибок.
    """
    try:
        # Записываем в файл логов
        logger.info(f'[DEBUG] Starting send_to_workers_background: city_id={city_id}, work_type_id={work_type_id}, advertisement_id={advertisement_id}')
        logger.info(f'[DEBUG] Photo params: photo_path={photo_path}, photos_len={photos_len}')
        
        # Используем оптимизированный метод для получения исполнителей
        workers = await Worker.get_active_workers_for_advertisement(city_id, work_type_id)
        
        if not workers:
            logger.info(f'[DEBUG] No active workers found for city {city_id} and work_type {work_type_id}')
            return
        
        logger.info(f'[DEBUG] Found {len(workers)} workers for advertisement {advertisement_id}')
        logger.info(f'[DEBUG] Starting background send to {len(workers)} workers for advertisement {advertisement_id}')
        
        # Отправляем по 5 сообщений в батче с паузой
        batch_size = 5
        for i in range(0, len(workers), batch_size):
            batch = workers[i:i + batch_size]
            
            # Создаем задачи для параллельной отправки
            tasks = [
                send_single_message_to_worker(worker, advertisement_id, text, photo_path, photos_len)
                for worker in batch
            ]
            
            # Выполняем батч параллельно
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Пауза между батчами для соблюдения rate limits
            if i + batch_size < len(workers):
                await asyncio.sleep(0.5)  # 500ms пауза
        
        logger.debug(f'Completed background send to workers for advertisement {advertisement_id}')
        
    except Exception as e:
        logger.error(f"Error in background send to workers: {e}")


# Новые обработчики для системы покупки контактов
@router.callback_query(lambda c: c.data.startswith('send-contacts-to-worker_'))
async def send_contacts_to_worker_from_request(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик отправки контактов заказчиком в ответ на запрос исполнителя"""
    logger.debug(f'send_contacts_to_worker_from_request...')
    kbc = KeyboardCollection()
    
    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    
    # Проверяем, настроены ли контакты у заказчика
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer.has_contacts():
        await callback.answer("⚠️ Укажите контакты в разделе: «Мои контакты», чтобы их можно было отправить!", show_alert=True)
        return
    
    # Получаем данные
    worker = await Worker.get_worker(id=worker_id)
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisement = await Abs.get_one(id=abs_id)
    
    if not worker or not customer or not advertisement:
        await callback.answer("Ошибка: данные не найдены", show_alert=True)
        return
    
    # Проверяем, есть ли у исполнителя купленные контакты
    from app.handlers.worker import check_worker_has_unlimited_contacts
    has_unlimited_contacts = await check_worker_has_unlimited_contacts(worker.id)
    
    if not has_unlimited_contacts:
        # У исполнителя нет купленных контактов
        # Уведомляем заказчика
        await callback.answer("У исполнителя нет купленных контактов для получения ваших контактов", show_alert=True)
        
        # Уведомляем исполнителя о необходимости купить контакты
        worker_message = f"Заказчик хочет отправить вам контакты, но у вас нет купленных контактов.\n\nОбъявление #{abs_id}\n{help_defs.read_text_file(advertisement.text_path) if advertisement.text_path else 'Текст не найден'}\n\nКупите контакты, чтобы получить контактные данные заказчика."
        
        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=worker_message,
                reply_markup=kbc.contact_purchase_tariffs()
            )
        except Exception as e:
            logger.error(f"Error sending message to worker: {e}")
        
        # Удаляем сообщение с кнопками, чтобы заказчик не мог нажать повторно
        try:
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
        
        return
    
    # У исполнителя есть купленные контакты - вычитаем контакт и отправляем
    # Формируем контакты в зависимости от настроек заказчика
    customer_contacts = ""
    if customer.contact_type == "telegram_only":
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})"
    elif customer.contact_type == "phone_only":
        customer_contacts = f"📞 [Номер телефона](tel:{customer.phone_number}) - {customer.phone_number}"
    elif customer.contact_type == "both":
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})\n📞 [Номер телефона](tel:{customer.phone_number}) - {customer.phone_number}"
    else:
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})"  # Fallback
    
    # Вычитаем контакт из лимита (если не безлимитный)
    if worker.unlimited_contacts_until:
        # Безлимитный тариф - не вычитаем
        message_text = f"У вас есть безлимитный доступ к контактам! ✅\n\nКонтакты заказчика:\n{customer_contacts}"
    else:
        # Ограниченный тариф - вычитаем контакт
        if worker.purchased_contacts > 0:
            new_contacts = worker.purchased_contacts - 1
            await worker.update_purchased_contacts(purchased_contacts=new_contacts)
            message_text = f"Покупка контакта успешно выполнена ✅\n\nКонтакты заказчика:\n{customer_contacts}"
        else:
            # Нет контактов для вычета
            await callback.answer("У исполнителя нет доступных контактов", show_alert=True)
            return
        
        try:
            await bot.send_message(
                chat_id=worker.tg_id,
                text=message_text,
                reply_markup=kbc.menu(),
                parse_mode='Markdown'
            )
        
            # Уведомляем заказчика
            await callback.answer("Контакты отправлены исполнителю ✅", show_alert=True)
            
            # Добавляем запись о передаче контактов в историю
            await help_defs.add_contact_exchange_to_history(
                worker_id=worker_id,
                customer_id=customer.id,
                abs_id=abs_id,
                direction="customer_to_worker"
            )
            
            # Закрываем чат после передачи контактов
            await help_defs.close_chat_after_contact_exchange(
                worker_id=worker_id,
                customer_id=customer.id,
                abs_id=abs_id,
                direction="customer_to_worker"
            )
            
        except Exception as e:
            logger.error(f"Error sending contacts to worker: {e}")
            await callback.answer("Ошибка при отправке контактов", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('reject-contact-request_'))
async def reject_contact_request_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик отклонения запроса контактов заказчиком"""
    logger.debug(f'reject_contact_request_handler...')
    
    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    
    # Получаем данные
    worker = await Worker.get_worker(id=worker_id)
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    
    if not worker or not customer:
        await callback.answer("Ошибка: данные не найдены", show_alert=True)
        return
    
    try:
        # Уведомляем исполнителя об отклонении
        await bot.send_message(
            chat_id=worker.tg_id,
            text="Заказчик отклонил ваш запрос на получение контактов"
        )
        
        # Уведомляем заказчика
        await callback.answer("Запрос контактов отклонен", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error rejecting contact request: {e}")
        await callback.answer("Ошибка при отклонении запроса", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('send-contacts-new_'))
async def send_contacts_to_worker_new(callback: CallbackQuery, state: FSMContext) -> None:
    """Новый обработчик отправки контактов заказчиком исполнителю"""
    logger.debug(f'send_contacts_to_worker_new...')
    kbc = KeyboardCollection()
    
    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    
    # Проверяем, настроены ли контакты у заказчика
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer.has_contacts():
        await callback.answer("⚠️ Укажите контакты в разделе: «Мои контакты», чтобы их можно было отправить!", show_alert=True)
        return
    
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer:
        await callback.answer("Ошибка: заказчик не найден", show_alert=True)
        return
    
    # Проверяем, что контакты еще не отправлены
    if await help_defs.check_contact_already_sent(worker_id, abs_id):
        await callback.answer("Контакты уже отправлены этому исполнителю", show_alert=True)
        return
    
    # Получаем исполнителя
    worker = await Worker.get_worker(id=worker_id)
    if not worker:
        await callback.answer("Исполнитель не найден", show_alert=True)
        return
    
    # Отправляем контакты заказчика исполнителю
    # Формируем контакты в зависимости от настроек заказчика
    customer_contacts = ""
    if customer.contact_type == "telegram_only":
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})"
    elif customer.contact_type == "phone_only":
        customer_contacts = f"📞 [Номер телефона](tel:{customer.phone_number}) - {customer.phone_number}"
    elif customer.contact_type == "both":
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})\n📞 [Номер телефона](tel:{customer.phone_number}) - {customer.phone_number}"
    else:
        customer_contacts = f"📱 [Профиль заказчика](tg://user?id={customer.tg_id}) (@{customer.tg_name})"  # Fallback
    
    try:
        # Используем унифицированную функцию для обработки обмена контактами
        result = await help_defs.process_contact_exchange(
            worker_id=worker.id,
            customer_id=customer.id,
            abs_id=abs_id,
            action="send_contacts"
        )
        
        if result['success']:
            # Уведомляем заказчика об успехе
            await callback.answer("Контакт успешно был отправлен ✅", show_alert=True)
            
            # Удаляем текущее сообщение с кнопками
            try:
                await callback.message.delete()
            except Exception as e:
                logger.error(f"Error deleting customer message: {e}")
        else:
            # Показываем ошибку
            await callback.answer(f"Ошибка: {result['message']}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error sending contacts to worker: {e}")
        await callback.answer("Ошибка при отправке контактов", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('send-contacts_'))
async def send_contacts_to_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик отправки контактов заказчиком исполнителю"""
    logger.debug(f'send_contacts_to_worker...')
    kbc = KeyboardCollection()
    
    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    
    # Проверяем, настроены ли контакты у заказчика
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer.has_contacts():
        await callback.answer("⚠️ Укажите контакты в разделе: «Мои контакты», чтобы их можно было отправить!", show_alert=True)
        return
    
    # Получаем данные
    worker = await Worker.get_worker(id=worker_id)
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisement = await Abs.get_one(id=abs_id)
    
    if not worker or not customer or not advertisement:
        await callback.answer("Ошибка: данные не найдены", show_alert=True)
        return
    
    # Отправляем уведомление исполнителю
    text = f"Заказчик отправил свои контакты\n\nОбъявление #{abs_id}\n{help_defs.read_text_file(advertisement.text_path) if advertisement.text_path else 'Текст не найден'}"
    
    try:
        await bot.send_message(
            chat_id=worker.tg_id,
            text=text,
            reply_markup=kbc.buy_contact_btn(customer_id=customer.id, abs_id=abs_id)
        )
        
        # Уведомляем заказчика
        await callback.answer("Контакт успешно был отправлен ✅", show_alert=True)
        
        # Добавляем запись о передаче контактов в историю
        await help_defs.add_contact_exchange_to_history(
            worker_id=worker_id,
            customer_id=customer.id,
            abs_id=abs_id,
            direction="customer_to_worker"
        )
        
        # Закрываем чат после передачи контактов
        await help_defs.close_chat_after_contact_exchange(
            worker_id=worker_id,
            customer_id=customer.id,
            abs_id=abs_id,
            direction="customer_to_worker"
        )
        
        # Закрываем чат для заказчика - убираем кнопки отправки сообщений
        # Оставляем только кнопку "Назад в отклики"
        await callback.message.edit_reply_markup(
            reply_markup=kbc.back_to_responses(abs_id=abs_id, id_now=0)
        )
        
    except Exception as e:
        logger.error(f"Error sending contacts: {e}")
        await callback.answer("Ошибка при отправке контактов", show_alert=True)




# Обработчики для системы оценки исполнителей

@router.callback_query(lambda c: c.data.startswith('rate-worker_'))
async def rate_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик оценки исполнителя заказчиком"""
    logger.debug(f'rate_worker...')
    kbc = KeyboardCollection()
    
    # Парсим данные из callback_data
    parts = callback.data.split('_')
    worker_id = int(parts[1])
    abs_id = int(parts[2])
    rating = int(parts[3])
    
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if not customer:
        await callback.answer("Ошибка: заказчик не найден", show_alert=True)
        return
    
    # Проверка на покупку контактов не нужна, так как исполнители попадают в список
    # для оценки только если они уже купили контакты (проверка в confirm_close_advertisement)
    
    # Проверяем, что заказчик еще не оценивал этого исполнителя
    from app.data.database.models import WorkerRating
    existing_rating = await WorkerRating.get_by_worker_and_abs(worker_id, abs_id)
    
    if existing_rating:
        await callback.answer("Вы уже оценили этого исполнителя", show_alert=True)
        return
    
    # Убираем проверку объявления, так как оно может быть уже удалено
    # но это не должно мешать оценке исполнителя
    
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
        await update_worker_rank_instantly(worker)
    
    # Уведомляем исполнителя об оценке
    from loaders import bot
    try:
        await bot.send_message(
            chat_id=worker.tg_id,
            text=f"⭐ Вам поставили оценку {rating}/5!\n\nОбъявление #{abs_id}\nСпасибо за качественную работу!"
        )
    except Exception as e:
        logger.error(f"Error sending rating notification to worker: {e}")
    
    await callback.answer(f"Спасибо! Вы оценили исполнителя на {rating} звезд", show_alert=True)
    
    # Объявление уже удалено в confirm_close_advertisement
    
    # Показываем сообщение об успешной оценке
    await callback.message.edit_text(
        f"✅ Оценка {rating} ⭐ поставлена исполнителю {worker.profile_name if worker.profile_name else 'ID ' + str(worker_id)}!\n\n"
        f"Спасибо за обратную связь.",
        reply_markup=InlineKeyboardBuilder().add(
            InlineKeyboardButton(text='В меню', callback_data='menu')
        ).adjust(1).as_markup()
    )


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
            await callback.message.edit_text(
                text="📭 **На это объявление пока нет откликов**\n\n"
                     "Ожидайте откликов от исполнителей.",
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )
            return
        
        # Формируем список откликов для отображения
        responses_data = []
        for response in responses:
            worker = await Worker.get_worker(id=response.worker_id)
            if worker:
                # Проверяем статус контактов
                contact_exchange = await ContactExchange.get_by_worker_and_abs(response.worker_id, abs_id)
                
                responses_data.append({
                    'worker_id': response.worker_id,
                    'worker_public_id': worker.public_id or f'ID#{worker.id}',
                    'worker_name': worker.profile_name or worker.tg_name,
                    'worker_stars': worker.stars,
                    'worker_ratings': worker.count_ratings,
                    'worker_verified': worker.confirmed,
                    'worker_ie': worker.individual_entrepreneur,
                    'worker_orders': worker.order_count,
                    'worker_message': response.worker_messages[0] if response.worker_messages else "Исполнитель не отправил сообщение",
                    'contact_requested': contact_exchange is not None,
                    'contact_confirmed': contact_exchange and contact_exchange.contacts_sent,
                    'contact_purchased': contact_exchange and contact_exchange.contacts_purchased,
                    'active': response.applyed
                })
        
        # Получаем объявление для контекста
        advertisement = await Abs.get_one(id=abs_id)
        city_name = "Неизвестно"
        if advertisement:
            city = await City.get_city(id=advertisement.city_id)
            if city:
                city_name = city.city
        
        kbc = KeyboardCollection()
        text = f"📋 **Отклики на объявление #{abs_id}**\n"
        text += f"🏙️ Город: {city_name}\n"
        text += f"👥 Количество откликов: {len(responses_data)}\n\n"
        text += "Выберите отклик для просмотра:"
        
        # Безопасное редактирование (может быть фото)
        try:
            await callback.message.edit_text(
                text=text,
                reply_markup=kbc.customer_responses_list_buttons(
                    responses_data=responses_data,
                    abs_id=abs_id
                ),
                parse_mode='Markdown'
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
                parse_mode='Markdown'
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
        id_now = int(parts[2])  # {id_now}
        
        # Получаем отклики на объявление
        responses = await WorkersAndAbs.get_by_abs(abs_id)
        
        if not responses:
            kbc = KeyboardCollection()
            await callback.message.edit_text(
                text="📭 **На это объявление пока нет откликов**\n\n"
                     "Ожидайте откликов от исполнителей.",
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )
            return
        
        # Формируем список откликов для отображения
        responses_data = []
        for response in responses:
            worker = await Worker.get_worker(id=response.worker_id)
            if worker:
                # Проверяем статус контактов
                contact_exchange = await ContactExchange.get_by_worker_and_abs(response.worker_id, abs_id)
                
                responses_data.append({
                    'worker_id': response.worker_id,
                    'worker_public_id': worker.public_id or f'ID#{worker.id}',
                    'worker_name': worker.profile_name or worker.tg_name,
                    'worker_stars': worker.stars,
                    'worker_ratings': worker.count_ratings,
                    'worker_verified': worker.confirmed,
                    'worker_ie': worker.individual_entrepreneur,
                    'worker_orders': worker.order_count,
                    'worker_message': response.worker_messages[0] if response.worker_messages else "Исполнитель не отправил сообщение",
                    'contact_requested': contact_exchange is not None,
                    'contact_confirmed': contact_exchange and contact_exchange.contacts_sent,
                    'contact_purchased': contact_exchange and contact_exchange.contacts_purchased,
                    'active': response.applyed
                })
        
        # Получаем объявление для контекста
        advertisement = await Abs.get_one(id=abs_id)
        city_name = "Неизвестно"
        if advertisement:
            city = await City.get_city(id=advertisement.city_id)
            if city:
                city_name = city.city
        
        kbc = KeyboardCollection()
        await callback.message.edit_text(
            text=f"📋 **Отклики на объявление #{abs_id}**\n"
                 f"🏙️ Город: {city_name}\n"
                 f"👥 Количество откликов: {len(responses_data)}\n\n"
                 "Выберите отклик для просмотра:",
            reply_markup=kbc.customer_responses_list_buttons(
                responses_data=responses_data,
                abs_id=abs_id
            ),
            parse_mode='Markdown'
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


async def update_worker_rank_instantly(worker: Worker):
    """
    Мгновенное обновление ранга исполнителя при получении оценки.
    Проверяет, изменился ли ранг, и отправляет уведомление при повышении.
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
                logger.info(f'update_worker_rank_instantly: Worker {worker.id} upgraded from {old_rank_type} to {new_rank.rank_type}')
                
                # Проверяем, может ли исполнитель выбрать больше направлений
                from app.data.database.models import WorkerAndSubscription, WorkerWorkTypeChanges
                worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                current_work_types_count = len(worker_sub.work_type_ids) if worker_sub and worker_sub.work_type_ids else 0
                
                # Если новый лимит больше текущего количества направлений - разрешаем выбор
                if new_work_types_limit is None or current_work_types_count < new_work_types_limit:
                    # Устанавливаем флаг pending_selection для разрешения выбора направлений
                    work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)
                    work_type_changes.pending_selection = True
                    await work_type_changes.save()
                    
                    logger.info(f'update_worker_rank_instantly: Set pending_selection=True for worker {worker.id} (can choose more work types)')
                
                try:
                    old_rank_name = WorkerRank.RANK_TYPES[old_rank_type]['name']
                    old_rank_emoji = WorkerRank.RANK_TYPES[old_rank_type]['emoji']
                    new_rank_name = new_rank.get_rank_name()
                    new_rank_emoji = new_rank.get_rank_emoji()
                    
                    notification_text = (
                        f"🎉 **Повышение ранга!**\n\n"
                        f"Ваш ранг изменился:\n"
                        f"{old_rank_emoji} **{old_rank_name}** → {new_rank_emoji} **{new_rank_name}**\n\n"
                        f"📊 **Новый лимит направлений:**\n"
                        f"Было доступно: **{old_work_types_limit if old_work_types_limit else 'без ограничений'}**\n"
                        f"Стало доступно: **{new_work_types_limit if new_work_types_limit else 'без ограничений'}**\n\n"
                        f"🎯 **Что это дает:**\n"
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
                        notification_text += f"\n\n🎯 **Можете выбрать больше направлений!**\nПерейдите в 'Мои направления' для выбора новых направлений работы."
                    
                    notification_text += f"\n\n💡 Продолжайте выполнять качественные заказы для поддержания высокого ранга!"
                    
                    # Отправляем уведомление
                    await bot.send_message(
                        chat_id=worker.tg_id,
                        text=notification_text,
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f'update_worker_rank_instantly: Sent rank upgrade notification to worker {worker.id}')
                    
                except Exception as notify_error:
                    logger.error(f'update_worker_rank_instantly: Failed to send upgrade notification to worker {worker.id} - {notify_error}')
            
            elif new_level < old_level:
                # ПОНИЖЕНИЕ РАНГА - НЕ отправляем уведомление мгновенно
                # Оставляем это для ежедневной проверки в 00:00
                logger.info(f'update_worker_rank_instantly: Worker {worker.id} downgraded from {old_rank_type} to {new_rank.rank_type} - notification will be sent at 00:00')
        
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
        text = f"Ваши контакты:\n\n{contact_info}"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu(),
            parse_mode='Markdown'
        )
    else:
        # Контакты не настроены - показываем меню выбора
        text = "Здесь вы можете указать, какие контакты будут отправлены исполнителю:"
        
        await callback.message.edit_text(
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
    
    text = "✅ Ваши контакты сохранены! Исполнители будут получать только ваш профиль Telegram 📱"
    
    await callback.message.edit_text(
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
    
    await callback.message.edit_text(
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
    
    await callback.message.edit_text(
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
        text = f"✅ Ваши контакты сохранены! Исполнители будут получать: номер (который вы указали) 📞"
    else:  # both
        text = f"✅ Ваши контакты сохранены! Исполнители будут получать: профиль Telegram и номер (который вы указали) 📱📞"
    
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
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.customer_contacts_edit_menu(customer.contact_type)
    )


@router.callback_query(F.data == 'edit_telegram_only', CustomerStates.customer_contacts)
async def edit_to_telegram_only(callback: CallbackQuery, state: FSMContext) -> None:
    """Изменение контактов на только Telegram"""
    logger.debug(f'edit_to_telegram_only...')
    
    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    
    await customer.update_contacts(contact_type="telegram_only", phone_number=None)
    
    text = "✅ Контакты изменены! Теперь исполнители будут получать только ваш профиль Telegram 📱"
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.customer_contacts_display_menu()
    )


@router.callback_query(F.data == 'edit_phone_only', CustomerStates.customer_contacts)
async def edit_to_phone_only(callback: CallbackQuery, state: FSMContext) -> None:
    """Изменение контактов на только номер телефона"""
    logger.debug(f'edit_to_phone_only...')
    
    kbc = KeyboardCollection()
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    
    # Если у заказчика уже есть номер, используем его, иначе запрашиваем новый
    if customer.phone_number:
        await customer.update_contacts(contact_type="phone_only")
        text = "✅ Контакты изменены! Теперь исполнители будут получать только номер телефона 📞"
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu()
        )
    else:
        text = "Введите новый номер телефона в формате +7XXXXXXXXXX"
        await callback.message.edit_text(
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
    
    # Если у заказчика уже есть номер, используем его, иначе запрашиваем новый
    if customer.phone_number:
        await customer.update_contacts(contact_type="both")
        text = "✅ Контакты изменены! Теперь исполнители будут получать: профиль Telegram и номер 📱📞"
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.customer_contacts_display_menu()
        )
    else:
        text = "Введите новый номер телефона в формате +7XXXXXXXXXX"
        await callback.message.edit_text(
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
    
    await callback.message.edit_text(
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
        
        logger.info(f"[CUSTOMER_PORTFOLIO] Customer {callback.from_user.id} viewing portfolio: worker_id={worker_id}, abs_id={abs_id}")
        
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
        from aiogram.types import FSInputFile
        kbc = KeyboardCollection()
        
        photo_len = len(worker.portfolio_photo)
        first_photo_path = worker.portfolio_photo['0']
        
        text = f"📸 **Портфолио исполнителя**\n\n"
        text += f"👤 **ID:** {worker.public_id or f'#{worker.id}'}\n"
        text += f"📋 **Имя:** {worker.profile_name or worker.tg_name}\n"
        text += f"🖼️ **Фото в портфолио:** {photo_len}\n\n"
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
                parse_mode='Markdown'
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
        
        logger.info(f"[CUSTOMER_PORTFOLIO_NAV] Customer {callback.from_user.id} navigating portfolio: worker_id={worker_id}, abs_id={abs_id}, photo_num={photo_num}")
        
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
        
        # Обработка циклической навигации
        if photo_num < 0:
            photo_num = photo_len - 1
        elif photo_num >= photo_len:
            photo_num = 0
        
        # Показываем фото
        from aiogram.types import FSInputFile
        kbc = KeyboardCollection()
        
        photo_path = worker.portfolio_photo[str(photo_num)]
        
        text = f"📸 **Портфолио исполнителя**\n\n"
        text += f"👤 **ID:** {worker.public_id or f'#{worker.id}'}\n"
        text += f"📋 **Имя:** {worker.profile_name or worker.tg_name}\n"
        text += f"🖼️ **Фото в портфолио:** {photo_len}\n\n"
        text += f"Фото {photo_num + 1} из {photo_len}"
        
        try:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=text,
                    parse_mode='Markdown'
                ),
                reply_markup=kbc.worker_portfolio_1(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    photo_num=photo_num,
                    photo_len=photo_len
                )
            )
        except Exception as e:
            logger.error(f"Error updating portfolio photo: {e}")
            # Fallback - отправляем новое сообщение
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=text,
                reply_markup=kbc.worker_portfolio_1(
                    worker_id=worker_id,
                    abs_id=abs_id,
                    photo_num=photo_num,
                    photo_len=photo_len
                ),
                parse_mode='Markdown'
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in customer_navigate_worker_portfolio: {e}")
        await callback.answer("❌ Произошла ошибка при навигации по портфолио", show_alert=True)


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
