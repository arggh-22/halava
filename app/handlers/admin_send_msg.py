import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import Customer, Worker, City
from app.keyboards import KeyboardCollection
from app.states import AdminStates
from app.untils import help_defs
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(F.data == 'msg_to_worker', AdminStates.menu)
async def msg_to_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker...')

    msg = await callback.message.edit_text(text='Напишите ваше обращение к исполнителям')
    await state.set_state(AdminStates.msg_to_worker_text)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, AdminStates.msg_to_worker_text)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    message_to_worker = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_worker_photo)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_worker=message_to_worker)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_worker_photo)
async def msg_to_worker_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_skip...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_worker = str(state_data.get('message_to_worker'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            try:
                await bot.send_message(chat_id=worker.tg_id, text=message_to_worker)
            except Exception:
                pass

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text='Сообщение отправлено всем исполнителям!', reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_worker_photo)
async def msg_to_worker_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_photo...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_worker = str(state_data.get('message_to_worker'))

    await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            try:
                await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_worker)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text='Сообщение отправлено всем исполнителям!', reply_markup=kbc.menu_btn())


@router.callback_query(F.data == 'msg_to_customer', AdminStates.menu)
async def msg_to_customer(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer...')

    msg = await callback.message.edit_text(text='Напишите ваше обращение к заказчикам')
    await state.set_state(AdminStates.msg_to_customer_text)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, AdminStates.msg_to_customer_text)
async def msg_to_customer_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    message_to_customer = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_customer_photo)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_customer=message_to_customer)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_customer_photo)
async def msg_to_customer_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_skip...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_customer = str(state_data.get('message_to_customer'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    customer = await Customer.get_all()
    if customer:
        for customer in customer:
            try:
                await bot.send_message(chat_id=customer.tg_id, text=message_to_customer)
            except Exception:
                pass

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text='Сообщение отправлено всем заказчикам!', reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_customer_photo)
async def msg_to_customer_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_photo...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_customer = str(state_data.get('message_to_customer'))

    await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    customers = await Customer.get_all()
    if customers:
        for customer in customers:
            try:
                await bot.send_photo(chat_id=customer.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_customer)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text='Сообщение отправлено всем заказчикам!', reply_markup=kbc.menu_btn())


@router.callback_query(F.data == 'msg_to_all', AdminStates.menu)
async def msg_to_all(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_all...')

    msg = await callback.message.edit_text(text='Напишите ваше обращение к пользователям')
    await state.set_state(AdminStates.msg_to_all_text)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, AdminStates.msg_to_all_text)
async def msg_to_all_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    message_to_all = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_all_photo)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_all=message_to_all)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_all_photo)
async def msg_to_all_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_skip...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_all = str(state_data.get('message_to_all'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    user_send = []

    customer = await Customer.get_all()
    if customer:
        for customer in customer:
            try:
                await bot.send_message(chat_id=customer.tg_id, text=message_to_all)
                user_send.append(customer.tg_id)
            except Exception:
                pass

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            if worker.tg_id not in user_send:
                try:
                    await bot.send_message(chat_id=worker.tg_id, text=message_to_all)
                except Exception:
                    pass

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text='Сообщение отправлено всем пользователям!', reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_all_photo)
async def msg_to_all_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_photo...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_all = str(state_data.get('message_to_all'))
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg)
    except Exception:
        pass
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    user_send = []

    customers = await Customer.get_all()
    if customers:
        for customer in customers:
            try:
                await bot.send_photo(chat_id=customer.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_all)
                user_send.append(customer.tg_id)
            except Exception:
                pass

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            try:
                if worker.tg_id not in user_send:
                    await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                         caption=message_to_all)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text='Сообщение отправлено всем пользователям!', reply_markup=kbc.menu_btn())


@router.callback_query(F.data == "admin_choose_city_for_workers", AdminStates.menu)
async def admin_choose_city_for_workers_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_workers_main...')
    kbc = KeyboardCollection()

    await state.set_state(AdminStates.msg_to_worker_choose_city)

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
             f'Показано {id_now + len(city_names)} {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.msg_to_worker_choose_city)
async def admin_choose_city_for_workers_next(callback: CallbackQuery) -> None:
    logger.debug(f'admin_choose_city_for_workers_next...')
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
                                    btn_next=btn_next, btn_back=btn_back))


@router.callback_query(lambda c: c.data.startswith('obj-id_'), AdminStates.msg_to_worker_choose_city)
async def admin_choose_city_for_workers_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_workers_end...')

    city_id = int(callback.data.split('_')[1])

    msg = await callback.message.edit_text(text='Напишите ваше обращение к исполнителям')
    await state.set_state(AdminStates.msg_to_worker_text_city)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(city_id=city_id)


@router.message(F.text, AdminStates.msg_to_worker_text_city)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    city_id = str(state_data.get('city_id'))
    message_to_worker = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_worker_photo_city)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_worker=message_to_worker)
    await state.update_data(city_id=city_id)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_worker_photo_city)
async def msg_to_worker_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_skip_city...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_worker = str(state_data.get('message_to_worker'))
    city_id = int(state_data.get('city_id'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            try:
                await bot.send_message(chat_id=worker.tg_id, text=message_to_worker)
            except Exception:
                pass

    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=f'Сообщение отправлено всем исполнителям из {city.city}!',
                                  reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_worker_photo_city)
async def msg_to_worker_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_photo_city...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_worker = str(state_data.get('message_to_worker'))
    city_id = int(state_data.get('city_id'))

    await bot.delete_message(chat_id=message.сhat.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            try:
                await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_worker)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)

    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text=f'Сообщение отправлено всем исполнителям из {city.city}!', reply_markup=kbc.menu_btn())


@router.callback_query(F.data == "admin_choose_city_for_customer", AdminStates.menu)
async def admin_choose_city_for_customer_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_customer_main...')
    kbc = KeyboardCollection()

    await state.set_state(AdminStates.msg_to_customer_choose_city)

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
                                    btn_next=btn_next, btn_back=False)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.msg_to_customer_choose_city)
async def admin_choose_city_for_customer_next(callback: CallbackQuery) -> None:
    logger.debug(f'admin_choose_city_for_customer_next...')
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
                                    btn_next=btn_next, btn_back=btn_back))


@router.callback_query(lambda c: c.data.startswith('obj-id_'), AdminStates.msg_to_customer_choose_city)
async def admin_choose_city_for_customer_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_customer_end...')

    city_id = int(callback.data.split('_')[1])

    msg = await callback.message.edit_text(text='Напишите ваше обращение к заказчикам')
    await state.set_state(AdminStates.msg_to_customer_text_city)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(city_id=city_id)


@router.message(F.text, AdminStates.msg_to_customer_text_city)
async def msg_to_customer_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_text_city...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    city_id = int(state_data.get('city_id'))
    message_to_customer = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_customer_photo_city)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_customer=message_to_customer)
    await state.update_data(city_id=city_id)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_customer_photo_city)
async def msg_to_customer_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_skip_city...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_customer = str(state_data.get('message_to_customer'))
    city_id = int(state_data.get('city_id'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    customers = await Customer.get_all_in_city(city_id=city_id)
    if customers:
        for customer in customers:
            try:
                await bot.send_message(chat_id=customer.tg_id, text=message_to_customer)
            except Exception:
                pass

    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=f'Сообщение отправлено всем заказчикам! из {city.city}',
                                  reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_customer_photo_city)
async def msg_to_customer_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_customer_photo...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_customer = str(state_data.get('message_to_customer'))
    city_id = int(state_data.get('city_id'))

    await bot.delete_message(chat_id=message.сhat.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    customers = await Customer.get_all_in_city(city_id=city_id)
    if customers:
        for customer in customers:
            try:
                await bot.send_photo(chat_id=customer.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_customer)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)
    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text=f'Сообщение отправлено всем заказчикам из {city.city}!', reply_markup=kbc.menu_btn())


@router.callback_query(F.data == "admin_choose_city_for_all", AdminStates.menu)
async def admin_choose_city_for_all_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_all_main...')
    kbc = KeyboardCollection()

    await state.set_state(AdminStates.msg_to_all_choose_city)

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


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.msg_to_all_choose_city)
async def admin_choose_city_for_all_next(callback: CallbackQuery) -> None:
    logger.debug(f'admin_choose_city_for_all_next...')
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


@router.callback_query(lambda c: c.data.startswith('obj-id_'), AdminStates.msg_to_all_choose_city)
async def admin_choose_city_for_all_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_all_end...')

    city_id = int(callback.data.split('_')[1])

    msg = await callback.message.edit_text(text='Напишите ваше обращение к пользователям')
    await state.set_state(AdminStates.msg_to_all_text_city)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(city_id=city_id)


@router.message(F.text, AdminStates.msg_to_all_text_city)
async def msg_to_all_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_text_city...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    city_id = int(state_data.get('city_id'))
    message_to_all = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_all_photo_city)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_all=message_to_all)
    await state.update_data(city_id=city_id)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_all_photo_city)
async def msg_to_all_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_skip_city...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_all = str(state_data.get('message_to_all'))
    city_id = int(state_data.get('city_id'))

    msg = await callback.message.edit_text('Подождите, идет отправка')

    user_send = []

    customer = await Customer.get_all_in_city(city_id=city_id)
    if customer:
        for customer in customer:
            try:
                await bot.send_message(chat_id=customer.tg_id, text=message_to_all)
                user_send.append(customer.tg_id)
            except Exception:
                pass

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            try:
                if worker.tg_id not in user_send:
                    await bot.send_message(chat_id=worker.tg_id, text=message_to_all)
            except Exception:
                pass

    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=f'Сообщение отправлено всем пользователям из {city.city}!',
                                  reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_all_photo_city)
async def msg_to_all_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_photo_city...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_all = str(state_data.get('message_to_all'))
    city_id = int(state_data.get('city_id'))

    await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    user_send = []

    customers = await Customer.get_all_in_city(city_id=city_id)
    if customers:
        for customer in customers:
            try:
                await bot.send_photo(chat_id=customer.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_all)
                user_send.append(customer.tg_id)
            except Exception:
                pass

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            try:
                if worker.tg_id not in user_send:
                    await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                         caption=message_to_all)
            except Exception:
                pass

    help_defs.delete_file(file_path_photo)

    city = await City.get_city(id=city_id)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await message.answer(text=f'Сообщение отправлено всем пользователям! из {city.city}', reply_markup=kbc.menu_btn())
