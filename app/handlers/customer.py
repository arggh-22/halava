import logging
from datetime import datetime, timedelta

from pydantic_core import ValidationError
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, FSInputFile, LabeledPrice, PreCheckoutQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

import config
import loaders
from app.data.database.models import Customer, Worker, City, Banned, WorkType, Abs, WorkSubType, \
    WorkerAndSubscription, WorkersAndAbs, Admin, BannedAbs, WorkerAndBadResponse, WorkerAndReport
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
    CustomerStates.customer_change_city,
    CustomerStates.customer_buy_subscription,
    CustomerStates.customer_check_abs,
    CustomerStates.customer_response))
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
                                  reply_markup=kbc.menu_customer_keyboard(
                                      btn_bue=True if customer.abs_count == 0 else False))


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
    await callback.message.edit_text(text=text,
                                     reply_markup=kbc.menu_customer_keyboard(
                                         btn_bue=True if customer.abs_count == 0 else False))


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

    await callback.message.answer_invoice(
        title=f"Дополнительное размещение",
        description=text,
        provider_token=config.PAYMENTS,
        currency="RUB",  # Валюта в верхнем регистре
        prices=prices,
        start_parameter="one-month-subscription",
        payload="invoice-payload",
        reply_markup=kbc.customer_buy_order(),
        need_email=True,
        send_email_to_provider=True
    )
    await state.update_data(customer_id=str(customer.id), order_price=admin.order_price)


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

    if customer.abs_count <= 0:
        await callback.answer(
            text=f"⚠️ Достигнут лимит бесплатных объявлений\n\n"
                 f"Лимит обновится в  {loaders.time_start}",
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
                                     reply_markup=kbc.menu_customer_keyboard(
                                         btn_bue=True if customer.abs_count == 0 else False))


@router.callback_query(F.data == 'my_abs', StateFilter(CustomerStates.customer_menu, CustomerStates.customer_check_abs,
                                                       CustomerStates.customer_response))
async def my_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')

    kbc = KeyboardCollection()

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    if not advertisements:
        await callback.message.edit_text(text='У вас пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(CustomerStates.customer_menu)
        return

    await state.set_state(CustomerStates.customer_check_abs)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    city = await City.get_city(id=abs_now.city_id)

    text = help_defs.read_text_file(abs_now.text_path)

    if abs_now.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0] + f'\nНомер телефона: {text_list[1]}'

    text = f'Объявление {abs_now.id} г. {city.city}\n\n' + text + f'\n\nПросмотров: {abs_now.views}'
    logger.debug(f"text {text}")
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                btn_responses = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        logger.debug(abs_now.photo_path['0'])
        logger.debug(abs_now.photo_path)
        if 'https' in abs_now.photo_path['0']:
            await callback.message.edit_text(text=text,
                                             reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                       btn_back=False,
                                                                                       btn_close=True,
                                                                                       btn_responses=btn_responses,
                                                                                       btn_close_name=btn_close_name,
                                                                                       abs_id=abs_now.id))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']),
                                            caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                      btn_back=False,
                                                                                      btn_close=True,
                                                                                      btn_responses=btn_responses,
                                                                                      btn_close_name=btn_close_name,
                                                                                      abs_id=abs_now.id,
                                                                                      count_photo=abs_now.count_photo,
                                                                                      idk_photo=0))
    else:
        await callback.message.edit_text(text=text,
                                         reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                   btn_back=False,
                                                                                   btn_close=True,
                                                                                   btn_responses=btn_responses,
                                                                                   btn_close_name=btn_close_name,
                                                                                   abs_id=abs_now.id))


@router.callback_query(lambda c: c.data.startswith('go_'), StateFilter(CustomerStates.customer_check_abs, CustomerStates.customer_response))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    abs_now = advertisements[abs_list_id]

    city = await City.get_city(id=abs_now.city_id)

    text = help_defs.read_text_file(abs_now.text_path)

    if abs_now.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0] + f'\nНомер телефона: {text_list[1]}'

    text = f'Объявление {abs_now.id} г. {city.city}\n\n' + text + f'\n\nПросмотров: {abs_now.views}'
    logger.debug(f"text {text}")

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                btn_responses = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'
    await state.set_state(CustomerStates.customer_check_abs)

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now.id
                )
            )
            return

        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_responses=btn_responses,
                btn_close=True,
                btn_close_name=btn_close_name,
                abs_id=abs_now.id,
                count_photo=abs_now.count_photo,
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
            abs_id=abs_now.id
        )
    )


@router.callback_query(lambda c: c.data.startswith('abs_'))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    abs_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

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

    city = await City.get_city(id=abs_now.city_id)

    text = help_defs.read_text_file(abs_now.text_path)

    if abs_now.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0] + f'\nНомер телефона: {text_list[1]}'

    text = f'Объявление {abs_now.id} г. {city.city}\n\n' + text + f'\n\nПросмотров: {abs_now.views}'
    logger.debug(f"text {text}")

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                btn_responses = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'
    await state.set_state(CustomerStates.customer_check_abs)

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_obj_with_out_list(
                    id_now=abs_list_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    btn_responses=btn_responses,
                    btn_close=True,
                    btn_close_name=btn_close_name,
                    abs_id=abs_now.id
                )
            )
            return

        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_responses=btn_responses,
                btn_close=True,
                btn_close_name=btn_close_name,
                abs_id=abs_now.id,
                count_photo=abs_now.count_photo,
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
            abs_id=abs_now.id
        )
    )


@router.callback_query(lambda c: c.data.startswith('go-to-next_'), StateFilter(CustomerStates.customer_check_abs, CustomerStates.customer_response))
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')

    kbc = KeyboardCollection()
    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    abs_now = advertisements[abs_list_id]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                btn_responses = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'
    await state.set_state(CustomerStates.customer_check_abs)

    if photo_id <= -1:
        photo_id = abs_now.count_photo - 1
    elif photo_id > (abs_now.count_photo - 1):
        photo_id = 0

    if abs_now.photo_path:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=FSInputFile(abs_now.photo_path[str(photo_id)]),
                caption=callback.message.caption
            ),
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_responses=btn_responses,
                btn_close=True,
                btn_close_name=btn_close_name,
                abs_id=abs_now.id,
                count_photo=abs_now.count_photo,
                idk_photo=photo_id
            )
        )
        return


@router.callback_query(lambda c: c.data.startswith('customer-responses_'), StateFilter(CustomerStates.customer_check_abs, CustomerStates.customer_response))
async def customer_responses(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_response...')

    kbc = KeyboardCollection()

    abs_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_id)

    names = []
    worker_ids = []

    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            unread = True
            count_messages = max([len(worker_and_abs.worker_messages), len(worker_and_abs.customer_messages)])

            for i in range(count_messages):
                if i < len(worker_and_abs.worker_messages):
                    unread = True
                if i < len(worker_and_abs.customer_messages):
                    unread = False
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            text = f'{"• " if unread else ""}{worker.profile_name if worker.profile_name else "Исполнитель"} ID {worker.id} ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}'
            names.append(text)
            worker_ids.append(worker.id)
    else:
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    msg = await callback.message.answer(
        text='Выберете интересующий вас отклик',
        reply_markup=kbc.choose_responses(
            id_now=abs_id,
            ids=worker_ids,
            names=names,
            abs_list_id=abs_list_id
        )
    )
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('customer-response_'),
                       StateFilter(CustomerStates.customer_check_abs, CustomerStates.customer_response))
async def customer_response(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_response...')

    kbc = KeyboardCollection()
    worker_id = int(callback.data.split('_')[1])
    abs_id = int(callback.data.split('_')[2])

    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id')) if state_data.get('msg_id') is not None else None

    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(abs_id=abs_id, worker_id=worker_id)
    worker = await Worker.get_worker(id=worker_id)

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisements = [advertisement.id for advertisement in advertisements]

    id_now = advertisements.index(abs_id)
    advertisement = await Abs.get_one(id=abs_id)

    text = (f'Исполнитель ID {worker.id} {worker.profile_name if worker.profile_name else ""}\n'
            f'Рейтинг: ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
            f'Верификация: {"✅" if worker.confirmed else "☑️"}\n'
            f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
            f'Зарегистрирован с {worker.registration_data}\n'
            f'Выполненных заказов: {worker.order_count}\n\n')

    count_messages = max([len(worker_and_abs.worker_messages), len(worker_and_abs.customer_messages)])

    send_btn = True if worker_and_abs.turn else False

    for i in range(count_messages):
        if i < len(worker_and_abs.worker_messages):
            if worker_and_abs.worker_messages[i] == 'Исполнитель не отправил сообщение':
                text += f' - {worker_and_abs.worker_messages[i]}\n'
            else:
                text += f' - Исполнитель: "{worker_and_abs.worker_messages[i]}"\n'

        if i < len(worker_and_abs.customer_messages):
            text += f' - Вы: "{worker_and_abs.customer_messages[i]}"\n'

    await state.set_state(CustomerStates.customer_response)

    try:
        if msg_id:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
    except TelegramBadRequest:
        pass

    if advertisement.work_type_id == 20 and not worker_and_abs.applyed:
        text = help_defs.read_text_file(advertisement.text_path)
        text = text.split('\n')
        text = text[0].split(' | ')
        prices = [LabeledPrice(label=f"Вызывной персонал", amount=int(config.PRICE * 100))]
        text = f"Оплата отклика, на объявление о вызывном персонале: {text[1]}"

        await callback.message.answer_invoice(
            title=f"Оплата отклика",
            description=text,
            provider_token=config.PAYMENTS,
            currency="RUB",  # Валюта в верхнем регистре
            prices=prices,
            start_parameter="buy-response",
            payload="invoice-payload",
            reply_markup=kbc.customer_buy_response(abs_id=abs_id, id_now=id_now),
            need_email=True,
            send_email_to_provider=True
        )
        await state.update_data(worker_id=worker_id, abs_id=abs_id)
        return
    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.apply_final_btn(
            idk=worker_id,
            send_btn=send_btn,
            role='customer',
            btn_back=True,
            id_now=id_now,
            abs_id=abs_id,
            portfolio=True if worker.portfolio_photo else False
        )
    )
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(abs_id=abs_id)


@router.pre_checkout_query(lambda query: True, CustomerStates.customer_response)
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    logger.debug(f'pre_checkout_handler...')
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment, CustomerStates.customer_response)
async def success_payment_handler(message: Message, state: FSMContext):
    logger.debug(f'success_payment_handler...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    abs_id = int(state_data.get('abs_id'))
    worker_id = int(state_data.get('worker_id'))

    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(abs_id=abs_id, worker_id=worker_id)
    worker = await Worker.get_worker(id=worker_id)

    customer = await Customer.get_customer(tg_id=message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisements = [advertisement.id for advertisement in advertisements]

    id_now = advertisements.index(abs_id)
    advertisement = await Abs.get_one(id=abs_id)

    text_msg = help_defs.read_text_file(advertisement.text_path)
    text_msg = text_msg.split(' ||| ')

    await worker_and_abs.update(applyed=True)
    worker_and_abs.customer_messages.append(text_msg[1])
    await worker_and_abs.update(customer_messages=worker_and_abs.customer_messages, turn=False)
    await bot.send_message(chat_id=worker.tg_id,
                           text=f"Заказчик принял ваш отклик на объявление ID{advertisement.id}\n\n{text_msg[0]}\n\nСвяжитесь с ним: {text_msg[1]}")

    text = f'{worker.profile_name if worker.profile_name else "Исполнитель"} ID {worker.id} ⭐️{round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n\n'

    count_messages = max([len(worker_and_abs.worker_messages), len(worker_and_abs.customer_messages)])

    for i in range(count_messages):
        if i < len(worker_and_abs.worker_messages):
            if worker_and_abs.worker_messages[i] == 'Исполнитель не отправил сообщение':
                text += f' - {worker_and_abs.worker_messages[i]}\n'
            else:
                text += f' - Исполнитель: "{worker_and_abs.worker_messages[i]}"\n'

        if i < len(worker_and_abs.customer_messages):
            text += f' - Вы: "{worker_and_abs.customer_messages[i]}"\n'

    await state.set_state(CustomerStates.customer_response)
    try:
        msg = await message.answer(
            text=text,
            reply_markup=kbc.apply_final_btn(
                idk=worker_id,
                send_btn=False,
                role='customer',
                btn_back=True,
                id_now=id_now,
                abs_id=abs_id,
                portfolio=True if worker.portfolio_photo else False
            )
        )
        await state.update_data(msg_id=msg.message_id)
        await state.update_data(abs_id=abs_id)
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('hide-obj-customer_'), CustomerStates.customer_response)
async def apply_order_hide(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order_hide...')

    worker_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    abs_id = int(state_data.get('abs_id'))

    kbc = KeyboardCollection()

    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(abs_id=abs_id, worker_id=worker_id)
    await worker_and_abs.delete()
    worker_and_bad_report = WorkerAndBadResponse(abs_id=abs_id, worker_id=worker_id)
    await worker_and_bad_report.save()

    worker = await Worker.get_worker(id=worker_id)

    advertisement = await Abs.get_one(id=abs_id)

    if advertisement.work_type_id == 20:
        text = help_defs.read_text_file(advertisement.text_path)
        text = text.split(' ||| ')
        text = f'К сожалению, заказчик *отклонил* ваш *отклик* на объявление {advertisement.id}:\n' + text[0]
    else:
        text = f'К сожалению, заказчик *отклонил* ваш *отклик* на объявление {advertisement.id}:\n' + help_defs.read_text_file(advertisement.text_path)

    await bot.send_message(chat_id=worker.tg_id, text=text)

    await callback.message.edit_text(text='Отклик отклонен!', reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(lambda c: c.data.startswith('answer-obj-customer_'), CustomerStates.customer_response)
async def apply_worker_with_out_msg(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_worker_with_out_msg...')

    worker_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    abs_id = int(state_data.get('abs_id'))

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id):
        await callback.answer(
            text=f"Предусмотрена блокировка, если в тексте и фото присутствуют:\n"
                 f"- Ссылки\n"
                 f"- Латинские буквы\n"
                 f"- Названия любых агрегаторов, мессенджеров и маркетплейсов",
            show_alert=True
        )

    msg = await callback.message.answer(text='Напишите ваш вопрос исполнителю:')

    await state.set_state(CustomerStates.customer_response_apply_worker_text)
    await state.update_data(worker_id=worker_id)
    await state.update_data(abs_id=abs_id)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, CustomerStates.customer_response_apply_worker_text)
async def send_worker_with_msg(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_worker_with_msg...')

    kbc = KeyboardCollection()

    msg_to_send = message.text

    state_data = await state.get_data()
    customer = await Customer.get_customer(tg_id=message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisements = [advertisement.id for advertisement in advertisements]
    worker_id = int(state_data.get('worker_id'))
    abs_id = int(state_data.get('abs_id'))

    worker = await Worker.get_worker(id=worker_id)

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=abs_id):
        pass
    else:
        await state.set_state(CustomerStates.customer_menu)
        await message.answer(
            text=f'Пользователь отклонил ваш отклик',
            reply_markup=kbc.menu_btn())
        return

    if await checks.fool_check(text=msg_to_send, is_message=True):
        await message.answer(
            'Упс, ваше сообщение содержит недопустимые слова, пожалуйста перепишите сообщение')
        return
    elif checks.contains_invalid_chars(text=msg_to_send):
        await message.answer(
            'Упс, ваше сообщение содержит недопустимые символы, пожалуйста перепишите сообщение')
        return
    elif checks.phone_finder(msg_to_send):
        if not worker_and_abs.applyed:
            await worker_and_abs.update(applyed=True)

    advertisement = await Abs.get_one(id=abs_id)

    if len(msg_to_send) > 200:
        await message.answer(
            text=f'В сообщении должно быть не более 200 символов')
        return
    try:
        await bot.send_message(chat_id=config.MESSAGE_LOG,
                               text=f' заказчик #{message.chat.id} отправил сообщение исполнителю #{worker.tg_id}: "{message.text}"',
                               protect_content=False, reply_markup=kbc.block_message_log(user_id=message.chat.id))
    except TelegramBadRequest:
        pass

    text = f'Ответ по Объявлению {abs_id}: "{msg_to_send}"\n\nОбъявление {abs_id}\n\n{help_defs.read_text_file(advertisement.text_path)}'

    id_now = advertisements.index(abs_id)

    try:
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker',
                                                                id_now=0))
    except Exception:
        text = f'Ответ по Объявлению {abs_id}: "{msg_to_send}"'
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker',
                                                                id_now=0))
    await message.answer(
        text=f'Сообщение успешно отправлено!',
        reply_markup=kbc.back_to_responses(abs_id=abs_id, id_now=id_now))

    worker_and_abs.customer_messages.append(msg_to_send)
    await worker_and_abs.update(customer_messages=worker_and_abs.customer_messages, turn=False)

    await state.set_state(CustomerStates.customer_check_abs)


@router.callback_query(lambda c: c.data.startswith('close_'), CustomerStates.customer_check_abs)
async def close_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'close_abs...')

    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    advertisement_now = advertisements[abs_list_id]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement_now.id)
    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=advertisement_now.id)
    if workers_and_bad_responses is not None:
        [await workers_and_bad_response.delete() for workers_and_bad_response in workers_and_bad_responses]
    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=advertisement_now.id)
    if workers_and_reports is not None:
        [await workers_and_report.delete() for workers_and_report in workers_and_reports]
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
                                          reply_markup=kbc.get_for_staring(ids=ids, names=names))

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

    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    if not advertisements:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='У вас пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(CustomerStates.customer_menu)
        return

    if abs_list_id >= len(advertisements):
        abs_list_id -= 1

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    advertisement_now = advertisements[abs_list_id]

    workers_applyed = False
    btn_responses = False

    if workers_and_abs:
        btn_responses = True
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                btn_responses = False
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'

    text = f'Объявление{advertisement_now.id}\n\n' + help_defs.read_text_file(
        advertisement_now.text_path) + f'\n\nПросмотров: {advertisement_now.views}'
    logger.debug(f"text {text}")
    if advertisement_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await callback.message.answer_photo(
            photo=FSInputFile(advertisement_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_responses=btn_responses,
                btn_close=True,
                btn_close_name=btn_close_name,
                abs_id=advertisement_now.id,
                count_photo=advertisement_now.count_photo,
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
            btn_close=True,
            btn_close_name=btn_close_name,
            btn_responses=btn_responses,
            abs_id=advertisement_now.id
        )
    )


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
                                          reply_markup=kbc.get_for_staring(ids=ids, names=names))

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


@router.callback_query(lambda c: c.data.startswith('choose-worker-for-staring_'))
async def staring_worker(callback: CallbackQuery) -> None:
    logger.debug(f'staring_worker...')

    worker_id = int(callback.data.split('_')[1])

    kbc = KeyboardCollection()
    try:
        await callback.message.delite()
        await callback.message.answer(text=f'Оцените работу Исполнителя {worker_id}',
                                      reply_markup=kbc.set_star(worker_id=worker_id))
    except Exception as e:
        logger.debug(e)


@router.callback_query(lambda c: c.data.startswith('star_'))
async def staring_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'staring_worker...')

    count_star = int(callback.data.split('_')[1])
    worker_id = int(callback.data.split('_')[2])

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(id=worker_id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker_id)

    if worker_sub.subscription_id == 1:
        await worker_sub.update(guaranteed_orders=worker_sub.guaranteed_orders - 1)

    await worker.update_stars(stars=worker.stars + count_star, count_ratings=worker.count_ratings + 1)

    await state.set_state(CustomerStates.customer_menu)

    await callback.message.edit_text(text=f'Оценка {count_star} ⭐️ Исполнителю ID {worker_id} выставлена',
                                     reply_markup=kbc.menu())


@router.callback_query(F.data == 'skip-star-for-worker')
async def skip_star_for_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'skip_star_for_worker...')
    kbc = KeyboardCollection()
    await state.set_state(CustomerStates.customer_menu)
    await callback.message.edit_text(text=f'Выставление оценки отменено', reply_markup=kbc.menu())


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_create_abs_work_type)
async def create_abs_work_type(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type...')

    kbc = KeyboardCollection()
    work_type_id = int(callback.data.split('_')[1])
    work_sub_type = await WorkSubType.get_work_sub_types(work_mine_type_id=work_type_id)

    if work_sub_type:
        names = [work_type.work_type for work_type in work_sub_type]
        ids = [work_type.id for work_type in work_sub_type]
        await callback.message.edit_text(text='Выберете категорию',
                                         reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))
        await state.set_state(CustomerStates.customer_choose_work_sub_types)
        await state.update_data(work_type_id=work_type_id)
        return

    work_type = await WorkType.get_work_type(id=work_type_id)

    text = help_defs.read_text_file(work_type.template)
    text = f'Пример объявления для {work_type.work_type}\n\n' + text

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


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_choose_work_sub_types)
async def create_abs_work_sub_type(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_sub_type...')
    kbc = KeyboardCollection()

    work_sub_type_id = str(callback.data.split('_')[1])
    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))

    work_type_id = work_type_id + '|' + work_sub_type_id

    work_sub_type = await WorkSubType.get_work_type(id=int(work_sub_type_id))

    text = help_defs.read_text_file(work_sub_type.template)
    text = f'Пример объявления для {work_sub_type.work_type}\n\n' + text
    if work_sub_type.template_photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(photo=FSInputFile(work_sub_type.template_photo), caption=text,
                                            parse_mode='HTML')
        return

    if '20' in work_type_id:
        await callback.message.delete()
        msg = await callback.message.answer(
            'Укажите подробности, условия, график, заработная плата: (не более 800 символов)',
            reply_markup=kbc.back_btn())
        await state.set_state(CustomerStates.customer_create_abs_task)
        await state.update_data(work_type_id=work_type_id)
        await state.update_data(msg_id=msg.message_id)
        return

    example_msg = await callback.message.edit_text(text=text, parse_mode='HTML')

    msg = await callback.message.answer('Укажите задачу, что необходимо: (не более 800 символов)',
                                        reply_markup=kbc.back_btn())
    await state.set_state(CustomerStates.customer_create_abs_task)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(example_msg_id=example_msg.message_id)


@router.callback_query(lambda c: c.data.startswith('back'), CustomerStates.customer_choose_work_sub_types)
async def create_abs_work_sub_type_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_sub_type_back...')
    kbc = KeyboardCollection()

    await state.clear()
    await state.set_state(CustomerStates.customer_create_abs_work_type)

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    await callback.message.edit_text(text='Выберете направление',
                                     reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


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
    work_type_id = str(state_data.get('work_type_id'))
    work_type_id_list = work_type_id.split('|')

    if len(work_type_id_list) == 2:
        work_sub_type = await WorkSubType.get_work_sub_types(work_mine_type_id=int(work_type_id_list[0]))
        names = [work_type.work_type for work_type in work_sub_type]
        ids = [work_type.id for work_type in work_sub_type]
        await callback.message.edit_text(text='Выберете категорию',
                                         reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))
        await state.set_state(CustomerStates.customer_choose_work_sub_types)
        await state.update_data(work_type_id=work_type_id_list[0])
        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=example_msg_id)
        except TelegramBadRequest:
            pass
        except ValidationError:
            pass
        return

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

    if '20' in work_type_id:
        await state.set_state(CustomerStates.enter_phone_number)
        await state.update_data(work_type_id=work_type_id)
        await state.update_data(task=task)
        await state.update_data(time=time)
        await state.update_data(end=0)
        msg = await callback.message.edit_text(text='Укажите ваш контактный номер телефона и имя контактного лица',
                                               reply_markup=kbc.back_btn())
        await state.update_data(msg=msg.message_id)
        return

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


@router.message(F.text, CustomerStates.enter_phone_number)
async def handle_send_contact(message: Message, state: FSMContext) -> None:
    logger.debug(f'handle_send_contact...')

    kbc = KeyboardCollection()

    phone = message.text

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    time = str(state_data.get('time'))
    msg = str(state_data.get('msg'))

    await bot.delete_message(chat_id=message.chat.id, message_id=msg)

    msg = await message.answer('Подождите идет проверка')

    all_text = f'{task}'

    if ban_reason := await checks.fool_check(text=all_text, is_personal=True):
        await ban_task(message=message, work_type_id=work_type_id, task=task, time=time, ban_reason=ban_reason, msg=msg)
        await state.set_state(BannedStates.banned)
        return

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    if checks.phone_finder(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await message.answer(
            'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        return

    if checks.contains_invalid_chars(all_text):
        await message.answer(
            'Извините, но использование иностранных символов недопустимо в объявлении, попробуйте еще раз',
            reply_markup=kbc.menu_btn())
        await state.set_state(CustomerStates.customer_menu)
        return

    if checks.contains_gibberish(all_text):
        await state.set_state(CustomerStates.customer_menu)
        await message.answer(
            'Упс, похоже у вас некорректный текст, вернитесь в меню и создайте объявление заново 🤔',
            reply_markup=kbc.menu_btn())
        return

    work_type_id_list = work_type_id.split('|')

    work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))

    work = work_type.work_type.capitalize()

    if len(work_type_id_list) > 1:
        work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
        work += ' | ' + work_sub_type.work_type

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}\n'
            f' ||| {phone}')

    text = help_defs.escape_markdown(text=text)

    customer = await Customer.get_customer(tg_id=message.chat.id)
    city = await City.get_city(id=customer.city_id)

    advertisements = await Abs.get_all()

    if advertisements:
        await same_task(message=message, advertisements=advertisements, text=text)
        await state.set_state(CustomerStates.customer_menu)
        return

    file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text)

    if time == 'В ближайшее время':
        delta = 1
    elif time == 'Завтра':
        delta = 2
    elif time == 'В течении недели':
        delta = 8
    else:
        delta = 30

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=city.id,
        photo_path=None,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=delta),
        count_photo=0
    )
    await new_abs.save()

    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisement = advertisements[-1]

    text = text.split(' ||| ')
    text = text[0]

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text + f'\nНомер телефона: {phone}'

    await message.answer(text=text, reply_markup=kbc.menu())

    await state.set_state(CustomerStates.customer_menu)

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text = help_defs.escape_markdown(text=text)

    text2 = f'ID пользователя: #{customer.tg_id}\n\nОбъявление {advertisement.id}\n\n' + text + f'\n\nНомер телефона: {phone}'
    text = f'Объявление {advertisement.id}\n\n' + text
    await bot.send_message(chat_id=config.ADVERTISEMENT_LOG,
                           text=text2,
                           protect_content=False,
                           reply_markup=kbc.block_abs_log(advertisement.id))

    logger.debug(f'workers {workers}')

    if workers:
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                logger.debug(f'workers double')
                continue
            if not worker.active:
                logger.debug(f'workers not active')
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            logger.debug(f'work type {worker_sub.work_type_ids}')
            if worker_sub.work_type_ids:
                if work_type_id_list[0] in worker_sub.work_type_ids:
                    try:
                        await advertisement.update(views=1)
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=text,
                                               reply_markup=kbc.apply_btn(advertisement.id)
                                               )
                    except TelegramForbiddenError:
                        logger.debug(f'workers gg send')
                        pass
            elif worker_sub.unlimited_work_types:
                try:
                    await advertisement.update(views=1)
                    await bot.send_message(chat_id=worker.tg_id,
                                           text=text,
                                           reply_markup=kbc.apply_btn(advertisement.id)
                                           )
                except TelegramForbiddenError:
                    logger.debug(f'workers gg send')
                    pass


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

    work_type_id_list = work_type_id.split('|')

    work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))

    work = work_type.work_type.capitalize()

    if len(work_type_id_list) > 1:
        work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
        work += ' | ' + work_sub_type.work_type

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

    advertisements = await Abs.get_all()

    if advertisements:
        if await same_task(message=callback.message, advertisements=advertisements, text=text):
            await state.set_state(CustomerStates.customer_menu)
            return

    logger.debug('win')

    file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text)

    if time == 'В ближайшее время':
        delta = 1
    elif time == 'Завтра':
        delta = 2
    elif time == 'В течении недели':
        delta = 8
    else:
        delta = 30

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=city.id,
        photo_path=None,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=delta),
        count_photo=0
    )
    await new_abs.save()

    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisement = advertisements[-1]

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text + f'\n\n Осталось размещений на сегодня {customer.abs_count - 1}'

    text = help_defs.escape_markdown(text=text)

    await callback.message.answer(text=text, reply_markup=kbc.menu())

    await state.set_state(CustomerStates.customer_menu)

    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации: {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text = help_defs.escape_markdown(text=text)

    text2 = f'ID пользователя: #{customer.tg_id}\n\nОбъявление {advertisement.id}\n\n' + text
    text = f'Объявление {advertisement.id}\n\n' + text

    await bot.send_message(chat_id=config.ADVERTISEMENT_LOG,
                           text=text2,
                           protect_content=False,
                           reply_markup=kbc.block_abs_log(advertisement.id))

    logger.debug(f'workers {workers}')

    if workers:
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                logger.debug(f'workers double')
                continue
            if not worker.active:
                logger.debug(f'workers not active')
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            logger.debug(f'work type {worker_sub.work_type_ids}')
            if worker_sub.work_type_ids:
                logger.debug(f'all right')
                if work_type_id_list[0] in worker_sub.work_type_ids:
                    try:
                        await advertisement.update(views=1)
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=text,
                                               reply_markup=kbc.apply_btn(advertisement.id)
                                               )
                    except TelegramForbiddenError:
                        await worker.delete()
                        logger.debug(f'workers gg send')
                        pass
            elif worker_sub.unlimited_work_types:
                logger.debug(f'bad')
                try:
                    await advertisement.update(views=1)
                    await bot.send_message(chat_id=worker.tg_id,
                                           text=text,
                                           reply_markup=kbc.apply_btn(advertisement.id)
                                           )
                except TelegramForbiddenError:
                    await worker.delete()
                    logger.debug(f'workers gg send')
                    pass


@router.callback_query(F.data == 'skip_it_photo', CustomerStates.customer_create_abs_add_photo)
async def create_abs_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_with_photo_end...')

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

        work_type_id_list = work_type_id.split('|')
        work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))
        work = work_type.work_type.capitalize()

        if len(work_type_id_list) > 1:
            work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
            work += " | " + work_sub_type.work_type

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
            work_type_id=int(work_type_id_list[0]),
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

        work_type_id_list = work_type_id.split('|')
        work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))
        work = work_type.work_type.capitalize()

        if len(work_type_id_list) > 1:
            work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
            work += " | " + work_sub_type.work_type

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
            work_type_id=int(work_type_id_list[0]),
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

    work_type_id_list = work_type_id.split('|')

    work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))

    work = work_type.work_type.capitalize()

    if len(work_type_id_list) > 1:
        work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
        work += ' | ' + work_sub_type.work_type

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    city = await City.get_city(id=customer.city_id)

    advertisements_customer = await Abs.get_all_by_customer(customer_id=customer.id)

    if advertisements_customer:
        old_text = help_defs.read_text_file(advertisements_customer[-1].text_path)
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
        delta = 1
    elif time == 'Завтра':
        delta = 2
    elif time == 'В течении недели':
        delta = 8
    else:
        delta = 30

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=city.id,
        photo_path=photos,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=delta),
        count_photo=photos_len
    )
    await new_abs.save()

    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisement = advertisements[-1]

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text + f'\n\n Осталось размещений на сегодня {customer.abs_count - 1}'

    text = help_defs.escape_markdown(text=text)

    await callback.message.answer(text=text, reply_markup=kbc.menu())

    await state.set_state(CustomerStates.customer_menu)

    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')

    text = help_defs.escape_markdown(text=text)

    text2 = f'ID пользователя: #{customer.tg_id}\n\nОбъявление {advertisement.id}\n\n' + text
    text = f'Объявление {advertisement.id}\n\n' + text

    await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG, caption=text2, photo=FSInputFile(photos['0']), protect_content=False,
                           reply_markup=kbc.block_abs_log(advertisement.id, photo_num=0, photo_len=photos_len))

    if workers:
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                continue
            if not worker.active:
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            logger.debug(f'work type {worker_sub.work_type_ids}')
            if worker_sub.work_type_ids:
                if work_type_id_list[0] in worker_sub.work_type_ids:
                    try:
                        await advertisement.update(views=1)
                        await bot.send_photo(
                            chat_id=worker.tg_id,
                            photo=FSInputFile(photos['0']),
                            caption=text,
                            reply_markup=kbc.apply_btn(advertisement.id, photo_num=0, photo_len=photos_len)
                        )

                    except TelegramForbiddenError:
                        await worker.delete()
                        pass
            elif worker_sub.unlimited_work_types:
                try:
                    await advertisement.update(views=1)
                    await bot.send_photo(
                            chat_id=worker.tg_id,
                            photo=FSInputFile(photos['0']),
                            caption=text,
                            reply_markup=kbc.apply_btn(advertisement.id, photo_num=0, photo_len=photos_len)
                    )
                except TelegramForbiddenError:
                    await worker.delete()
                    pass


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


@router.callback_query(lambda c: c.data.startswith('look-worker-it_'))
async def apply_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_worker...')

    kbc = KeyboardCollection()
    worker_id = int(callback.data.split('_')[1])
    abs_id = int(callback.data.split('_')[2])

    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(abs_id=abs_id, worker_id=worker_id)
    worker = await Worker.get_worker(id=worker_id)

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisements = [advertisement.id for advertisement in advertisements]
    advertisement = await Abs.get_one(id=abs_id)

    id_now = advertisements.index(abs_id)

    text = (f'Исполнитель ID {worker.id} {worker.profile_name if worker.profile_name else ""}\n'
            f'Рейтинг: ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
            f'Верификация: {"✅" if worker.confirmed else "☑️"}\n'
            f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
            f'Зарегистрирован с {worker.registration_data}\n'
            f'Выполненных заказов: {worker.order_count}\n\n')

    count_messages = max([len(worker_and_abs.worker_messages), len(worker_and_abs.customer_messages)])

    send_btn = True if worker_and_abs.turn else False

    for i in range(count_messages):
        if i < len(worker_and_abs.worker_messages):
            if worker_and_abs.worker_messages[i] == 'Исполнитель не отправил сообщение':
                text += f' - {worker_and_abs.worker_messages[i]}\n'
            else:
                text += f' - {worker.profile_name if worker.profile_name else "Исполнитель"}: "{worker_and_abs.worker_messages[i]}"\n'

        if i < len(worker_and_abs.customer_messages):
            text += f' - Вы: "{worker_and_abs.customer_messages[i]}"\n'

    await state.set_state(CustomerStates.customer_response)

    if advertisement.work_type_id == 20 and not worker_and_abs.applyed:
        await callback.message.delete()
        text = help_defs.read_text_file(advertisement.text_path)
        text = text.split('\n')
        text = text[0].split(' | ')
        prices = [LabeledPrice(label=f"Вызывной персонал", amount=int(config.PRICE * 100))]
        text = f"Оплата отклика, на объявление о вызывном персонале: {text[1]}"

        await callback.message.answer_invoice(
            title=f"Оплата отклика",
            description=text,
            provider_token=config.PAYMENTS,
            currency="RUB",  # Валюта в верхнем регистре
            prices=prices,
            start_parameter="buy-response",
            payload="invoice-payload",
            reply_markup=kbc.customer_buy_response(abs_id=abs_id, id_now=id_now),
            need_email=True,
            send_email_to_provider=True
        )
        await state.update_data(worker_id=worker_id, abs_id=abs_id)
        return

    if advertisement.work_type_id == 20:
        text = (f'Исполнитель ID {worker.id}\n'
                f'Рейтинг: ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.stars else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)}\n'
                f'Верификация: {"✅" if worker.confirmed else "☑️"}\n'
                f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                f'Зарегистрирован с {worker.registration_data}\n'
                f'Выполненных заказов: {worker.order_count}\n\n')
        text += f' - Вы: "{worker_and_abs.customer_messages[0]}"\n'

    if worker.profile_photo:

        try:
            await callback.message.delete()
        except Exception as e:
            logger.debug(f'apply_worker...{e}')
        try:
            msg = await callback.message.answer_photo(
                photo=FSInputFile(worker.profile_photo),
                caption=text,
                reply_markup=kbc.apply_final_btn(idk=worker_id,
                                                 send_btn=send_btn,
                                                 role='customer',
                                                 btn_back=True,
                                                 id_now=id_now,
                                                 abs_id=abs_id,
                                                 portfolio=True if worker.portfolio_photo else False
                                                 )
            )
        except Exception as e:
            logger.debug(f'apply_worker...{e}')
            msg = await callback.message.answer(
                text=text,
                reply_markup=kbc.apply_final_btn(idk=worker_id,
                                                 send_btn=send_btn,
                                                 role='customer',
                                                 btn_back=True,
                                                 id_now=id_now,
                                                 abs_id=abs_id,
                                                 portfolio=True if worker.portfolio_photo else False
                                                 )
            )
    else:
        try:
            await callback.message.delete()
        except Exception as e:
            logger.debug(f'apply_worker...{e}')

        msg = await callback.message.answer(
            text=text,
            reply_markup=kbc.apply_final_btn(idk=worker_id,
                                             send_btn=send_btn,
                                             role='customer',
                                             btn_back=True,
                                             id_now=id_now,
                                             abs_id=abs_id,
                                             portfolio=True if worker.portfolio_photo else False
                                             )
        )
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(abs_id=abs_id)


@router.callback_query(lambda c: c.data.startswith('worker-portfolio_'), CustomerStates.customer_response)
async def worker_portfolio(callback: CallbackQuery) -> None:
    logger.debug(f'worker-portfolio_...')

    kbc = KeyboardCollection()

    worker_id = int(callback.data.split('_')[1])
    abs_id = int(callback.data.split('_')[2])

    worker = await Worker.get_worker(id=worker_id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if worker.portfolio_photo:
        photo_len = len(worker.portfolio_photo)
        logger.debug(f'my_portfolio...{photo_len}')

        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo['0']),
            reply_markup=kbc.worker_portfolio_1(
                worker_id=worker_id,
                abs_id=abs_id,
                photo_len=photo_len
            )
        )


@router.callback_query(lambda c: c.data.startswith("go-to-portfolio_"), CustomerStates.customer_response)
async def worker_portfolio(callback: CallbackQuery) -> None:
    logger.debug(f'worker_portfolio...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])
    worker_id = int(callback.data.split('_')[2])
    abs_id = int(callback.data.split('_')[3])

    worker = await Worker.get_worker(id=worker_id)

    photo_len = len(worker.portfolio_photo)

    if photo_id <= -1:
        photo_id = photo_len - 1
    elif photo_id > (photo_len - 1):
        photo_id = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(worker.portfolio_photo[str(photo_id)])),
        reply_markup=kbc.worker_portfolio_1(
            worker_id=worker_id,
            abs_id=abs_id,
            photo_num=photo_id,
            photo_len=photo_len
        )
    )


@router.message(F.text, CustomerStates.customer_apply_worker_text)
async def send_worker_with_msg(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_worker_with_msg...')

    kbc = KeyboardCollection()

    msg_to_send = message.text

    state_data = await state.get_data()
    worker_id = int(state_data.get('worker_id'))
    abs_id = int(state_data.get('abs_id'))
    msg_id = int(state_data.get('msg_id'))

    worker = await Worker.get_worker(id=worker_id)

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=abs_id):
        if worker_and_abs.send_by_customer <= 0:
            await message.answer(text='У вас не осталось сообщений',
                                 reply_markup=kbc.apply_final_btn(idk=abs_id, name='Принять отклик',
                                                                  skip_btn=False, role='customer', id_now=0))
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            return
        else:
            await worker_and_abs.update(send_by_customer=worker_and_abs.send_by_customer - 1)

    if await checks.fool_check(text=msg_to_send, is_message=True):
        await message.answer(
            'Упс, ваше сообщение содержит недопустимые слова, пожалуйста перепишите сообщение')
        return
    elif checks.phone_finder(msg_to_send):
        if not worker_and_abs.applyed:
            await worker_and_abs.update(applyed=True)

    advertisement = await Abs.get_one(id=abs_id)

    if len(msg_to_send) > 200:
        await message.answer(
            text=f'В сообщении должно быть не более 200 символов')
        return

    await bot.send_message(chat_id=config.MESSAGE_LOG,
                           text=f' заказчик #{message.chat.id} отправил сообщение исполнителю #{worker.tg_id}: "{message.text}"',
                           protect_content=False, reply_markup=kbc.block_message_log(user_id=message.chat.id))

    text = f'Ответ по Объявлению {abs_id}: "{msg_to_send}"\n\nОбъявление {abs_id}\n\n{help_defs.read_text_file(advertisement.text_path)}'
    try:
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker',
                                                                id_now=0))
    except Exception:
        text = f'Ответ по Объявлению {abs_id}: "{msg_to_send}"\n\nОсталось {worker_and_abs.send_by_worker}/4 сообщений'
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker',
                                                                id_now=0))
    await message.answer(
        text=f'Сообщение успешно отправлено!',
        reply_markup=kbc.menu())

    worker_and_abs.customer_messages.append(msg_to_send)
    await worker_and_abs.update(customer_messages=worker_and_abs.customer_messages, turn=False)

    await state.set_state(CustomerStates.customer_menu)


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
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=1))
    elif time_id == 2:
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=2))
    elif time_id == 3:
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=8))
    else:
        await advertisement.update(date_to_delite=datetime.today() + timedelta(days=30))

    await state.set_state(CustomerStates.customer_menu)

    await callback.message.answer('Объявление успешно продлено:\n\n',
                                  reply_markup=kbc.menu())


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
