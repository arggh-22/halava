import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, FSInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

import config
import loaders
from app.data.database.models import Customer, Worker, City, Banned, WorkType, Abs, WorkSubType, BlockWord, \
    WorkerAndSubscription, WorkersAndAbs, SubscriptionType, Admin, BannedAbs, BlockWordShort, WorkerAndCustomer, \
    ProfanityWord, WhiteWord, WorkerAndRefsAssociation
from app.keyboards import KeyboardCollection
from app.states import UserStates, CustomerStates, BannedStates
from app.untils import help_defs, checks, yandex_ocr
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

    await callback.message.edit_text(
        text=f'Пожалуйста выберите ваш город\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), CustomerStates.registration_enter_city)
async def choose_city_next(callback: CallbackQuery) -> None:
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

    await callback.message.edit_text(
        text=f'Пожалуйста выберите ваш город\n'
             f' Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=btn_back))


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


@router.callback_query(F.data == 'menu', StateFilter(CustomerStates.customer_menu, CustomerStates.customer_check_abs,
                                                     CustomerStates.customer_change_city))
async def customer_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'customer_menu...')
    print(state)
    print("sssssssssssssssssss")

    kbc = KeyboardCollection()

    tg_id = callback.message.chat.id

    customer = await Customer.get_customer(tg_id=tg_id)
    if customer is None:
        text = '''Упс, вы еще не зарегистрированы как заказчик'''
        await callback.message.edit_text(text=text, reply_markup=kbc.registration_customer())
        if worker := await Worker.get_worker(tg_id=callback.message.chat.id):
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(worker.city_id), username=str(worker.tg_name))
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
                                  reply_markup=kbc.menu_customer_keyboard())


@router.callback_query(F.data == 'customer_menu', UserStates.menu)
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
            await state.update_data(city_id=str(worker.city_id), username=str(worker.tg_name))
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
                                     reply_markup=kbc.menu_customer_keyboard())


@router.callback_query(F.data == 'create_new_abs', CustomerStates.customer_menu)
async def create_new_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_new_abs...')

    kbc = KeyboardCollection()

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)

    if customer.abs_count <= 0:
        await callback.answer(
            text=f"Достигнут лимит объявлений\n"
                 f"Лимит обновится в {loaders.time_start}",
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


@router.callback_query(F.data == 'my_abs', CustomerStates.customer_menu)
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
    text = f'Объявление {abs_now.id} г. {city.city}\n\n' + text
    logger.debug(f"text {text}")
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False

    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path), caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                      btn_back=False,
                                                                                      btn_close=True,
                                                                                      btn_close_name=btn_close_name))
    else:
        await callback.message.edit_text(text=text,
                                         reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                   btn_back=False,
                                                                                   btn_close=True,
                                                                                   btn_close_name=btn_close_name))


@router.callback_query(lambda c: c.data.startswith('go_'), CustomerStates.customer_check_abs)
async def check_abs(callback: CallbackQuery) -> None:
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
    text = f'Объявление {abs_now.id} г. {city.city}\n\n' + text
    logger.debug(f"text {text}")

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=abs_now.id)

    workers_applyed = False

    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_close=True,
                btn_close_name=btn_close_name
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
            btn_close_name=btn_close_name
        )
    )


@router.callback_query(lambda c: c.data.startswith('close_'), CustomerStates.customer_check_abs)
async def close_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'close_abs...')

    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    advertisement_now = advertisements[abs_list_id]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement_now.id)
    workers_for_assessments = []
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
            if sub.notification:

                city = await City.get_city(id=advertisement_now.city_id)
                text = f'Заказчик закрыл объявление {advertisement_now.id}\nг. {city.city}\n' + help_defs.read_text_file(
                    advertisement_now.text_path)

                try:
                    await bot.send_message(chat_id=worker.tg_id, text=text)
                except TelegramForbiddenError:
                    pass
            if worker_and_abs.applyed:
                if await WorkerAndCustomer.get_by_worker_and_customer(worker_id=worker.id, customer_id=customer.id):
                    await worker_and_abs.delete()
                    if worker.order_count + 1 == 5:
                        if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                            await worker_and_ref.update(work_condition=True)
                            if worker_and_ref.ref_condition:
                                await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                                await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                                await bot.send_message(chat_id=worker.tg_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                        elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                            await worker_and_ref.update(ref_condition=True)
                            if worker_and_ref.work_condition:
                                await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                                worker_main = await Worker.get_worker(id=worker_and_ref.worker_id)
                                await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                                await bot.send_message(chat_id=worker_main.tg_id,
                                                       text='Условия вашей реферальной программы выполнены!')

                    continue
                else:
                    workers_for_assessments.append(worker)
                    worker_and_customer = WorkerAndCustomer(worker_id=worker.id, customer_id=customer.id)
                    await worker_and_customer.save()
                    await worker.update_order_count(order_count=worker.order_count + 1)
                    await worker.update_order_count_on_week(order_count_on_week=worker.order_count_on_week + 1)
                    if worker.order_count + 1 == 5:
                        if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                            await worker_and_ref.update(work_condition=True)
                            if worker_and_ref.ref_condition:
                                await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                                await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                                await bot.send_message(chat_id=worker.tg_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                        elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                            await worker_and_ref.update(ref_condition=True)
                            if worker_and_ref.work_condition:
                                await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                                worker_main = await Worker.get_worker(id=worker_and_ref.worker_id)
                                await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                       text='Условия вашей реферальной программы выполнены!')
                                await bot.send_message(chat_id=worker_main.tg_id,
                                                       text='Условия вашей реферальной программы выполнены!')

            await worker_and_abs.delete()
        for worker in workers_for_assessments:
            await callback.message.answer(text=f'Оцените работу Исполнителя {worker.id}',
                                          reply_markup=kbc.set_star(worker_id=worker.id))

        if workers_for_assessments:
            await state.clear()
            await advertisement_now.delete()
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            return

    await advertisement_now.delete()
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

    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            if worker_and_abs.applyed:
                workers_applyed = True
                break

    btn_close_name = 'Закрыть и оценить' if workers_applyed else 'Отменить и удалить'

    text = f'Объявление{advertisement_now.id}\n\n' + help_defs.read_text_file(advertisement_now.text_path)
    logger.debug(f"text {text}")
    if advertisement_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(advertisement_now.photo_path),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_close=True,
                btn_close_name=btn_close_name
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
            btn_close_name=btn_close_name
        )
    )


@router.callback_query(lambda c: c.data.startswith('star_'))
async def staring_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'staring_worker...')

    count_star = int(callback.data.split('_')[1])
    worker_id = int(callback.data.split('_')[2])

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(id=worker_id)

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
    await callback.message.answer(text='Выберете тип работы', reply_markup=kbc.choose_type(ids=ids, names=names))


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
        banned = await Banned.get_banned(tg_id=message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await bot.send_message(chat_id=-4206742054,
                               text=f'#{message.chat.id} текст заблокированной задачи: "{message.text}"',
                               protect_content=False)
        await bot.send_message(chat_id=config.BLOCKED_CHAT,
                               text=f'ID пользователя: {message.chat.id}, причина блокировки: слишком короткий текст задачи',
                               protect_content=False)
        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                     reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await message.answer(
                'Вы заблокированы на 24 ч. за подозрительную активность, если Вы считаете, что произошла ошибка, обратитесь в поддержку.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return
        new_banned = Banned(id=None, tg_id=message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False)
        await new_banned.save()
        await message.answer(
            'Вы заблокированы на 24 ч. за подозрительную активность, если Вы считаете, что произошла ошибка, обратитесь в поддержку.',
            reply_markup=kbc.support_btn())
        await state.set_state(BannedStates.banned)
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

    names = ['В ближайшее время', 'Завтра', 'В течении недели', 'В течении месяца']
    ids = [1, 2, 3, 4]
    await message.answer('Когда нужна услуга:\n\n', reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True))


@router.callback_query(F.data == 'back', CustomerStates.customer_create_abs_choose_time)
async def create_abs_work_type_back(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_work_type_back...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    example_msg_id = str(state_data.get('example_msg_id'))

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

    await state.set_state(CustomerStates.customer_create_abs_add_photo)
    await state.update_data(work_type_id=work_type_id)
    await state.update_data(task=task)
    await state.update_data(time=time)
    msg = await callback.message.edit_text(text='Прикрепите фото, или нажмите кнопку пропустить',
                                           reply_markup=kbc.skip_btn())
    await state.update_data(msg=msg.message_id)
    await callback.answer(
        text=f"Вы можете прикрепить 1 фото.\n"
             f"На фото не должно быть надписей, цифр и символов, если они присутствуют - их следует замазать перед загрузкой.\n"
             f"Загрузка видео недоступна!\n",
        show_alert=True
    )


@router.message(F.video, CustomerStates.customer_create_abs_add_photo)
async def video_error(message: Message, state: FSMContext):
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    kbc = KeyboardCollection()

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Вы не можете отправить видео.\n\nПрикрепите фото, или нажмите кнопку пропустить',
                               reply_markup=kbc.skip_btn())
    await state.update_data(msg=msg.message_id)


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
    block_words = await BlockWord.get_all()
    block_words = [block_word.word for block_word in block_words]
    short_block_words = await BlockWordShort.get_all()
    short_block_words = [short_block_words.word for short_block_words in short_block_words]
    profanity_words = await ProfanityWord.get_all()
    profanity_words = [profanity_word.word for profanity_word in profanity_words]
    white_words = await WhiteWord.get_all()
    white_words = [white_word.word for white_word in white_words]

    if ban_reason := await checks.fool_check(text=all_text, block_words=block_words,
                                             short_block_words=short_block_words, profanity_words=profanity_words,
                                             white_words=white_words):
        banned = await Banned.get_banned(tg_id=callback.message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))

        await bot.send_message(chat_id=config.BLOCKED_CHAT,
                               text=f'ID пользователя: {callback.message.chat.id}, причина блокировки: {ban_reason}',
                               protect_content=False)

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

        file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text,
                                                                      path='app/data/banned/text/')

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id_list[0]),
            city_id=customer.city_id,
            photo_path=None,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30)
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)

        banned_abs = banned_abs[-1]

        admins = await Admin.get_all()

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f'\n'
                f'{ban_reason}')

        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

        await bot.send_message(chat_id=-4206742054,
                               text=text,
                               protect_content=False)

        for admin in admins:
            try:
                await bot.send_message(chat_id=admin.tg_id, text=text, reply_markup=kbc.unban(banned_abs.id))
            except TelegramForbiddenError:
                pass
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
                            forever=False)
        await new_banned.save()
        await callback.message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        await state.set_state(BannedStates.banned)
        return

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

    if checks.phone_finder(all_text):
        await state.set_state(CustomerStates.customer_menu)
        if banned := await Banned.get_banned(tg_id=callback.message.chat.id):
            if banned.warning == 3:
                await bot.send_message(chat_id=config.BLOCKED_CHAT,
                                       text=f'ID пользователя: {callback.message.chat.id}, причина блокировки: неоднократное использование номера телефона в сообщении',
                                       protect_content=False)
                ban_end = str(datetime.now() + timedelta(days=24000))
                await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, forever=True)
                await callback.message.answer(
                    'Вы заблокированы навсегда за неоднократное нарушение правил платформы, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                    reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await callback.message.answer(
                f'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔\n\nПредупреждение {banned.warning + 1} из 3',
                reply_markup=kbc.menu_btn())
            await banned.update(warning=banned.warning + 1)
        else:
            await callback.message.answer(
                'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔\n\nПредупреждение 1 из 3',
                reply_markup=kbc.menu_btn())
            new_banned = Banned(id=None, tg_id=callback.message.chat.id,
                                ban_counter=1, ban_end=str(datetime.now() - timedelta(days=1)), ban_now=False,
                                forever=False, warning=1)
            await new_banned.save_war()
        return

    if checks.contains_invalid_chars(all_text):
        await callback.message.answer(
            'Извините, но использование иностранных символов недопустимо в объявлении, попробуйте еще раз',
            reply_markup=kbc.menu_btn())
        await state.set_state(CustomerStates.customer_menu)
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
        text_old = help_defs.read_text_file(advertisements_customer[-1].text_path)
        if await checks.are_texts_similar(text_old, text):
            await callback.message.answer(
                'Вы предлагали схожий запрос, удалите предыдущий и попробуйте снова',
                reply_markup=kbc.menu_btn())
            await state.set_state(CustomerStates.customer_menu)
            return

    file_path = help_defs.create_file_in_directory_with_timestamp(id=callback.message.chat.id, text=text)

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=city.id,
        photo_path=None,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=30)
    )
    await new_abs.save()

    # Используем ID из объекта, а не последнее объявление из списка
    advertisement = new_abs

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text + f'\n\n Осталось размещений на сегодня {customer.abs_count - 1}'

    await callback.message.answer(text=text, reply_markup=kbc.menu())

    await state.set_state(CustomerStates.customer_menu)

    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    if workers:
        text = (f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f'\n'
                f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')
        text2 = f'ID пользователя: #{customer.tg_id}\n\nОбъявление {advertisement.id}\n\n' + text
        text = f'Объявление {advertisement.id}\n\n' + text
        await bot.send_message(chat_id=-4206742054,
                               text=text2,
                               protect_content=False)
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                continue
            if not worker.active:
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            if worker_sub.work_type_ids:
                if (work_type_id_list[0] in worker_sub.work_type_ids) or worker_sub.unlimited_work_types:
                    try:
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=text,
                                               reply_markup=kbc.apply_btn(advertisement.id)
                                               )
                    except TelegramForbiddenError:
                        pass
            elif worker_sub.unlimited_work_types:
                try:
                    await bot.send_message(chat_id=worker.tg_id,
                                           text=text,
                                           reply_markup=kbc.apply_btn(advertisement.id)
                                           )
                except TelegramForbiddenError:
                    pass


@router.message(F.photo, CustomerStates.customer_create_abs_add_photo)
async def create_abs_with_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'create_abs_with_photo...')

    kbc = KeyboardCollection()
    photo = message.photo[-1].file_id
    state_data = await state.get_data()

    msg = str(state_data.get('msg'))
    work_type_id = str(state_data.get('work_type_id'))
    task = str(state_data.get('task'))
    time = str(state_data.get('time'))

    await bot.delete_message(chat_id=message.from_user.id, message_id=msg, )

    msg = await message.answer(text='Подождите идет проверка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id)

    await bot.download(file=photo, destination=file_path_photo)

    logger.debug(f"start ocr")

    text_photo = yandex_ocr.analyze_file(file_path_photo)
    logger.debug(f"text_photo: {text_photo}")
    if text_photo:
        banned = await Banned.get_banned(tg_id=message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))
        help_defs.delete_file(file_path_photo)

        await bot.send_message(chat_id=config.BLOCKED_CHAT,
                               text=f'ID пользователя: #{message.chat.id}, причина блокировки: текст на фото\n\nНайденный текст: {text_photo}',
                               protect_content=False)

        work_type_id_list = work_type_id.split('|')
        work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))
        work = work_type.work_type.capitalize()

        if len(work_type_id_list) > 1:
            work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
            work += " | " + work_sub_type.work_type

        customer = await Customer.get_customer(tg_id=message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n')

        file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text,
                                                                      path='app/data/banned/text/')
        file_path_photo = await help_defs.save_photo(id=message.from_user.id, path='app/data/banned/photo/')
        await bot.download(file=photo, destination=file_path_photo)

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id_list[0]),
            city_id=customer.city_id,
            photo_path=file_path_photo,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30)
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        admins = await Admin.get_all()

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'Общий ID пользователя: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f''
                f'Текст на фото')

        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

        await bot.send_photo(chat_id=-4206742054,
                             caption=text, photo=FSInputFile(file_path_photo),
                             protect_content=False)

        for admin in admins:
            try:
                await bot.send_photo(chat_id=admin.tg_id, caption=text, photo=FSInputFile(file_path_photo),
                                     reply_markup=kbc.unban(banned_abs.id))
            except TelegramForbiddenError:
                pass

        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                     reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await message.answer(
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(id=None, tg_id=message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False)
        await message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)

        return

    all_text = f'{task}'
    block_words = await BlockWord.get_all()
    block_words = [block_word.word for block_word in block_words]
    short_block_words = await BlockWordShort.get_all()
    short_block_words = [short_block_words.word for short_block_words in short_block_words]
    profanity_words = await ProfanityWord.get_all()
    profanity_words = [profanity_word.word for profanity_word in profanity_words]
    white_words = await WhiteWord.get_all()
    white_words = [white_word.word for white_word in white_words]

    if ban_reason := await checks.fool_check(text=all_text, block_words=block_words,
                                             short_block_words=short_block_words, profanity_words=profanity_words,
                                             white_words=white_words):
        banned = await Banned.get_banned(tg_id=message.chat.id)
        ban_end = str(datetime.now() + timedelta(hours=24))
        help_defs.delete_file(file_path_photo)

        await bot.send_message(chat_id=config.BLOCKED_CHAT,
                               text=f'ID пользователя: #{message.chat.id}, причина блокировки: {ban_reason}',
                               protect_content=False)

        work_type_id_list = work_type_id.split('|')
        work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))
        work = work_type.work_type.capitalize()

        if len(work_type_id_list) > 1:
            work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
            work += " | " + work_sub_type.work_type

        customer = await Customer.get_customer(tg_id=message.chat.id)

        text = (f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n')

        file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text,
                                                                      path='app/data/banned/text/')
        file_path_photo = await help_defs.save_photo(id=message.from_user.id, path='app/data/banned/photo/')
        await bot.download(file=photo, destination=file_path_photo)

        banned_abs = BannedAbs(
            id=None,
            customer_id=customer.id,
            work_type_id=int(work_type_id_list[0]),
            city_id=customer.city_id,
            photo_path=file_path_photo,
            text_path=file_path,
            date_to_delite=datetime.today() + timedelta(days=30)
        )
        await banned_abs.save()

        banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)
        banned_abs = banned_abs[-1]

        admins = await Admin.get_all()

        text = (f'Заблокирован пользователь @{customer.tg_name}\n'
                f'ID: #{customer.tg_id}\n\n'
                f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f''
                f'{ban_reason}')

        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

        await bot.send_photo(chat_id=-4206742054,
                             caption=text, photo=FSInputFile(file_path_photo),
                             protect_content=False)

        for admin in admins:
            try:
                await bot.send_photo(chat_id=admin.tg_id, caption=text, photo=FSInputFile(file_path_photo),
                                     reply_markup=kbc.unban(banned_abs.id))
            except TelegramForbiddenError:
                pass

        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                     reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await message.answer(
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return

        new_banned = Banned(id=None, tg_id=message.chat.id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False)
        await message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        await new_banned.save()
        await state.set_state(BannedStates.banned)

        return

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    if checks.phone_finder(all_text):
        help_defs.delete_folder(file_path_photo)
        await state.set_state(CustomerStates.customer_menu)
        if banned := await Banned.get_banned(tg_id=message.chat.id):
            if banned.warning == 3:
                await bot.send_message(chat_id=config.BLOCKED_CHAT,
                                       text=f'ID пользователя: {message.chat.id}, причина блокировки: неоднократное указывание номера телефона в объявлении',
                                       protect_content=False)
                ban_end = str(datetime.now() + timedelta(days=24000))
                await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, forever=True)
                await message.answer(
                    'Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                    reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                return
            await message.answer(
                f'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔\n\nПредупреждение {banned.warning + 1} из 3',
                reply_markup=kbc.menu_btn())
            await banned.update(warning=banned.warning + 1)
        else:
            await message.answer(
                'Упс, похоже вы указали номер телефона, вернитесь в меню и создайте объявление заново 🤔\n\nПредупреждение 1 из 3',
                reply_markup=kbc.menu_btn())
            new_banned = Banned(id=None, tg_id=message.chat.id,
                                ban_counter=1, ban_end=str(datetime.now() - timedelta(days=1)), ban_now=False,
                                forever=False, warning=1)
            await new_banned.save_war()
        return

    all_text = f'{task}'

    if checks.contains_invalid_chars(all_text):
        await message.answer(
            'Извините, но использование иностранных символов недопустимо в объявлении, попробуйте еще раз',
            reply_markup=kbc.menu_btn())
        await state.set_state(CustomerStates.customer_menu)
        help_defs.delete_folder(file_path_photo)
        return

    help_defs.add_watermark(file_path_photo)

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

    customer = await Customer.get_customer(tg_id=message.chat.id)
    city = await City.get_city(id=customer.city_id)

    advertisements_customer = await Abs.get_all_by_customer(customer_id=customer.id)

    if advertisements_customer:
        old_text = help_defs.read_text_file(advertisements_customer[-1].text_path)
        if await checks.are_texts_similar(old_text, text):
            await message.answer(
                'Вы предлагали схожий запрос, удалите предыдущий и попробуйте снова',
                reply_markup=kbc.menu_btn())
            await state.set_state(CustomerStates.customer_menu)
            help_defs.delete_file(file_path_photo)
            return

    file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text)

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=city.id,
        photo_path=file_path_photo,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=30)
    )
    await new_abs.save()

    # Используем ID из объекта, а не последнее объявление из списка
    advertisement = new_abs

    text = f'Объявление загружено\n\nОбъявление {advertisement.id}\n\n' + text + f'\n\n Осталось размещений на сегодня {customer.abs_count - 1}'

    await message.answer_photo(photo=FSInputFile(file_path_photo), caption=text, reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)

    await customer.update_abs_count(abs_count=customer.abs_count - 1)

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    if workers:
        text = (f'{work}\n\n'
                f'Задача: {task}\n'
                f'Время: {time}\n'
                f'\n'
                f'Дата публикации {datetime.now().strftime("%d.%m.%Y")} в {datetime.now().strftime("%H:%M")}')
        text2 = f'ID пользователя: #{customer.tg_id}\n\nОбъявление {advertisement.id}\n\n' + text
        text = f'Объявление {advertisement.id}\n\n' + text

        await bot.send_photo(chat_id=-4206742054,
                             caption=text2, photo=FSInputFile(file_path_photo),
                             protect_content=False)
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                continue
            if not worker.active:
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            if worker_sub.work_type_ids:
                if (work_type_id_list[0] in worker_sub.work_type_ids) or worker_sub.unlimited_work_types:
                    try:
                        await bot.send_photo(chat_id=worker.tg_id,
                                             photo=FSInputFile(file_path_photo),
                                             caption=text,
                                             reply_markup=kbc.apply_btn(advertisement.id)
                                             )
                    except TelegramForbiddenError:
                        pass
            elif worker_sub.unlimited_work_types:
                try:
                    await bot.send_photo(chat_id=worker.tg_id,
                                         photo=FSInputFile(file_path_photo),
                                         caption=text,
                                         reply_markup=kbc.apply_btn(advertisement.id)
                                         )
                except TelegramForbiddenError:
                    pass


@router.callback_query(lambda c: c.data.startswith('look-worker-it_'))
async def apply_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_worker...')

    kbc = KeyboardCollection()

    if user_blocked := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_blocked.ban_now or user_blocked.forever:
            await callback.message.edit_text(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return

    worker_id = int(callback.data.split('_')[1])
    abs_id = int(callback.data.split('_')[2])

    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id)
    name = 'Принять отклик'
    text = f'''Вы можете принять отклик и отправить свои контакты исполнителю - в этом случае заказ будет закрыт и станет неактуальным. 

Вы можете написать исполнителю и обсудить заказ - после обсуждения, сможете отправить свои контакты и закрыть заказ, который станет неактуальным. 

Вы можете отклонить отклик и отказаться от исполнителя.'''
    send_btn = True if worker_and_abs.send_by_customer > 0 else False

    await state.set_state(CustomerStates.customer_apply_worker)
    await state.update_data(worker_id=worker_id)
    await state.update_data(abs_id=abs_id)
    msg = await callback.message.edit_text(text=text,
                                           reply_markup=kbc.apply_final_btn(idk=worker_id, name=name, send_btn=send_btn,
                                                                            role='customer'))
    await state.update_data(msg_id=msg.message_id)
    await callback.answer(
        text=f"Внимание: необходимо сразу принять решение по исполнителю, в противном случае вернуться к отклику будет нельзя!",
        show_alert=True
    )


@router.callback_query(lambda c: c.data.startswith('apply-final-it_'), CustomerStates.customer_apply_worker)
async def apply_worker_with_out_msg(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_worker_with_out_msg...')

    kbc = KeyboardCollection()
    worker_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    abs_id = int(state_data.get('abs_id'))

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    msg = await callback.message.answer(text='Отправьте контакты для связи с вами', reply_markup=kbc.contact_keyboard())
    await state.set_state(CustomerStates.send_contact_to_worker)
    await state.update_data(worker_id=worker_id)
    await state.update_data(abs_id=abs_id)
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('hide-obj_'), CustomerStates.customer_apply_worker)
async def apply_order_hide(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order_hide...')
    kbc = KeyboardCollection()
    await callback.message.edit_text(text='Отклик отклонен!', reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)


@router.callback_query(lambda c: c.data.startswith('answer-obj-customer_'), CustomerStates.customer_apply_worker)
async def apply_worker_with_out_msg(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_worker_with_out_msg...')

    worker_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    abs_id = int(state_data.get('abs_id'))

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id):
        if worker_and_abs.send_by_customer == 4:
            await callback.answer(
                text=f"Предусмотрена блокировка, если в тексте и фото присутствуют:\n"
                     f"- Ссылки\n"
                     f"- Латинские буквы\n"
                     f"- Номера телефонов\n"
                     f"- Названия любых агрегаторов, мессенджеров и маркетплейсов",
                show_alert=True
            )

    msg = await callback.message.answer(text='Напишите ваш вопрос исполнителю:')

    await state.set_state(CustomerStates.customer_apply_worker_text)
    await state.update_data(worker_id=worker_id)
    await state.update_data(abs_id=abs_id)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, CustomerStates.customer_apply_worker_text)
async def send_worker_with_msg(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_worker_with_msg...')
    await bot.send_message(chat_id=-4206742054, text=f'#{message.chat.id} сообщение исполнителю: "{message.text}"')
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
                                                                  skip_btn=False, role='customer'))
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            return
        else:
            await worker_and_abs.update(send_by_customer=worker_and_abs.send_by_customer - 1)

    block_words = await BlockWord.get_all()
    block_words = [block_word.word for block_word in block_words]
    short_block_words = await BlockWordShort.get_all()
    short_block_words = [short_block_words.word for short_block_words in short_block_words]
    profanity_words = await ProfanityWord.get_all()
    profanity_words = [profanity_word.word for profanity_word in profanity_words]
    white_words = await WhiteWord.get_all()
    white_words = [white_word.word for white_word in white_words]

    if ban_reason := await checks.fool_check(text=msg_to_send,
                                             block_words=block_words,
                                             short_block_words=short_block_words,
                                             profanity_words=profanity_words,
                                             white_words=white_words):
        banned = await Banned.get_banned(tg_id=message.chat.id)
        await bot.send_message(chat_id=config.BLOCKED_CHAT,
                               text=f'ID пользователя: {message.chat.id}, причина блокировки: запрещенные слова в переписке с исполнителем - {ban_reason}',
                               protect_content=False)

        ban_end = datetime.now() + timedelta(hours=24)
        if banned:
            if banned.ban_counter >= 3:
                await banned.update(forever=True, ban_now=True)
                await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы')
                await state.set_state(BannedStates.banned)
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=str(ban_end))
            await message.answer(
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.')
            await state.set_state(BannedStates.banned)
        else:
            new_banned = Banned(id=None, tg_id=message.chat.id,
                                ban_counter=1, ban_end=ban_end, ban_now=True,
                                forever=False)
            await new_banned.save()
            await message.answer(
                'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.')
            await state.set_state(BannedStates.banned)

        text = f'Сообщение пользователя: "{msg_to_send}"\n\nПричина блокировки: "{ban_reason}"'

        admins = await Admin.get_all()
        for admin in admins:
            try:
                await bot.send_message(chat_id=admin.tg_id, text=text, reply_markup=kbc.unban(message.chat.id))
            except TelegramForbiddenError:
                pass

        advertisement = await Abs.get_one(abs_id)
        workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)

        if workers_and_abs:
            for worker_and_abs in workers_and_abs:
                worker = await Worker.get_worker(id=worker_and_abs.worker_id)
                worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
                if sub.notification:
                    city = await City.get_city(id=advertisement.city_id)
                    text = f'Объявление {advertisement.id} неактуально г. {city.city}\n' + help_defs.read_text_file(
                        advertisement.text_path)
                    try:
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=text)
                    except TelegramForbiddenError:
                        pass
                await worker_and_abs.delete()
        await advertisement.delete()
        return
    elif checks.phone_finder(msg_to_send):
        if banned := await Banned.get_banned(tg_id=message.chat.id):
            if banned.warning == 3:
                await bot.send_message(chat_id=config.BLOCKED_CHAT,
                                       text=f'ID пользователя: {message.chat.id}, причина блокировки: неоднократное указывание номера телефона в сообщении исполнителю',
                                       protect_content=False)

                ban_end = str(datetime.now() + timedelta(days=1000))
                await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, forever=True)
                await message.answer(
                    'Вы заблокированы навсегда за неоднократное нарушение правил платформы, если считаете, что это не так, Вы можете это обжаловать написав нам.',
                    reply_markup=kbc.support_btn())
                await state.set_state(BannedStates.banned)
                advertisement = await Abs.get_one(abs_id)
                workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)

                if workers_and_abs:
                    for worker_and_abs in workers_and_abs:
                        worker = await Worker.get_worker(id=worker_and_abs.worker_id)
                        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                        sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
                        if sub.notification:
                            city = await City.get_city(id=advertisement.city_id)
                            text = f'Объявление {advertisement.id} неактуально г. {city.city}\n' + help_defs.read_text_file(
                                advertisement.text_path)
                            try:
                                await bot.send_message(chat_id=worker.tg_id,
                                                       text=text)
                            except TelegramForbiddenError:
                                pass
                        await worker_and_abs.delete()
                await advertisement.delete()
                return
            await message.answer(
                f'Публикация объявлений с номером телефона запрещена 🚫\n\nПредупреждение {banned.warning + 1} из 3',
                reply_markup=kbc.menu_btn())
            await banned.update(warning=banned.warning + 1)
        else:
            await message.answer(
                'Публикация объявлений с номером телефона запрещена 🚫\n\nПредупреждение 1 из 3',
                reply_markup=kbc.menu_btn())
            new_banned = Banned(id=None, tg_id=message.chat.id,
                                ban_counter=1, ban_end=None, ban_now=False,
                                forever=False, warning=1)
            await new_banned.save_war()
        return

    advertisement = await Abs.get_one(id=abs_id)

    if len(msg_to_send) > 400:
        await message.answer(
            text=f'В сообщении должно быть не более 400 символов')
        return

    text = f'Объявление {abs_id}\n\n' + help_defs.read_text_file(advertisement.text_path)
    text += f'Ответ по Объявлению {abs_id}: "{msg_to_send}"\n\nОсталось {worker_and_abs.send_by_worker}/4 сообщений'
    try:
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker'))
    except Exception:
        text = f'Ответ по Объявлению {abs_id}: "{msg_to_send}"\n\nОсталось {worker_and_abs.send_by_worker}/4 сообщений'
        await bot.send_message(chat_id=worker.tg_id, text=text,
                               reply_markup=kbc.apply_final_btn(idk=abs_id, skip_btn=True, send_btn=True,
                                                                send_btn_name='Ответить заказчику',
                                                                skip_btn_name='Отказаться и удалить', role='worker'))
    await message.answer(
        text=f'Сообщение  по объявлению {abs_id} успешно отправлено!\n\nОсталось {worker_and_abs.send_by_customer - 1}/4 сообщений',
        reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)


# Старые функции отправки контактов удалены - используется новая система ContactExchange


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

    await callback.message.edit_text(
        text=f'Пожалуйста выберите город\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False, menu_btn=True)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), CustomerStates.customer_change_city)
async def change_city_next(callback: CallbackQuery) -> None:
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

    await callback.message.edit_text(
        text=f'Пожалуйста выберите город\n'
             f' Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=btn_back, menu_btn=True))


@router.callback_query(lambda c: c.data.startswith('obj-id_'), CustomerStates.customer_change_city)
async def change_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_end...')
    kbc = KeyboardCollection()

    city_id = int(callback.data.split('_')[1])

    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    await customer.update_city(city_id=city_id)

    await callback.message.edit_text('Вы успешно сменили город!', reply_markup=kbc.menu())
    await state.set_state(CustomerStates.customer_menu)

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
