import datetime
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery, FSInputFile, \
    InputMediaPhoto
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

import config
from app.data.database.models import Customer, Worker, City, SubscriptionType, WorkerAndSubscription, \
    WorkType, Banned, Abs, WorkersAndAbs, Admin, \
    WorkerAndRefsAssociation, WorkerAndReport, WorkerAndBadResponse
from app.keyboards import KeyboardCollection
from app.states import WorkStates, UserStates, BannedStates
from app.untils import help_defs, checks, yandex_ocr
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(F.data == "registration_worker", WorkStates.verification_worker)
async def registration_new_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'registration_new_worker...')
    kbc = KeyboardCollection()
    state_data = await state.get_data()
    city_id = int(state_data.get('city_id'))
    username = str(state_data.get('username'))

    registration_date = datetime.date.today().strftime("%d.%m.%Y")

    new_worker = Worker(tg_id=callback.message.chat.id,
                        city_id=[str(city_id)],
                        tg_name=username,
                        registration_data=registration_date)
    await new_worker.save()
    new_worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    new_worker_and_subscription = WorkerAndSubscription(worker_id=new_worker.id)
    await new_worker_and_subscription.save()
    await callback.message.edit_text('Вы успешно зарегистрированы!')
    await callback.message.answer(text='Верифицируйте ваш аккаунт',
                                  reply_markup=kbc.verification_worker())
    await state.set_state(WorkStates.verification_worker)


@router.callback_query(F.data == "registration_worker", UserStates.registration_enter_city)
async def choose_city_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_city_main...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    username = str(state_data.get('username'))
    await state.set_state(WorkStates.registration_enter_city)
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
             f'Показано {id_now + len(city_names)} из {count_cities} городов',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, WorkStates.registration_enter_city)
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
             f'Выберите город или напишите его текстом\n\n',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.registration_enter_city)
async def choose_city_next(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_city_next...')
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
                 f'Показано {id_now + len(city_names)} из {count_cities} городов',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back))
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.registration_enter_city)
async def choose_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_city_end...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    username = str(state_data.get('username'))

    city_id = int(callback.data.split('_')[1])

    registration_date = datetime.date.today().strftime("%d.%m.%Y")

    new_worker = Worker(tg_id=callback.message.chat.id,
                        city_id=[city_id],
                        tg_name=username,
                        registration_data=registration_date,
                        stars=5)

    await new_worker.save()
    new_worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    new_worker_and_subscription = WorkerAndSubscription(worker_id=new_worker.id)

    await new_worker_and_subscription.save()
    await callback.message.edit_text('Вы успешно зарегистрированы!')
    await callback.message.answer(text='Верифицируйте ваш аккаунт',
                                  reply_markup=kbc.verification_worker())
    await state.set_state(WorkStates.verification_worker)


@router.callback_query(F.data == "verification_yes", StateFilter(WorkStates.verification_worker, WorkStates.worker_menu))
async def verification_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'verification_worker...')
    kbs = KeyboardCollection()
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text='Отправьте ваш номер телефона с помощью кнопки ниже',
                                  reply_markup=kbs.contact_keyboard())
    await state.set_state(WorkStates.verification_send_contact)


@router.callback_query(F.data == "verification_no", WorkStates.verification_worker)
async def verification_stop_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'verification_stop_worker...')
    kbc = KeyboardCollection()
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text='Вы всегда можете продолжить верификацию позже через меню',
                                  reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_menu)


@router.message(F.contact, WorkStates.verification_send_contact)
async def handle_contact(message: Message, state: FSMContext) -> None:
    logger.debug(f'handle_contact...')
    phone = help_defs.get_pure_phone(message.contact.phone_number)
    worker = await Worker.get_worker(tg_id=message.from_user.id)

    await worker.update_phone_number(phone_number=phone)
    await message.answer(f'Отлично, ваш код подтверждения {worker.confirmation_code} введите его боту',
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(WorkStates.verification_enter_code)


@router.message(F.text, WorkStates.verification_enter_code)
async def handle_enter_verification_code(message: Message, state: FSMContext) -> None:
    logger.debug(f'handle_enter_verification_code...')
    kbc = KeyboardCollection()
    code = message.text
    if code.isdigit():
        worker = await Worker.get_worker(tg_id=message.from_user.id)
        if int(code) == worker.confirmation_code:
            await worker.update_confirmed(confirmed=True)
            await message.answer(text='Ваш аккаунт успешно верифицирован!', reply_markup=kbc.menu())
            await state.set_state(WorkStates.worker_menu)
            return

    await message.answer(text='Некорректный ввод, попробуйте еще раз')


@router.callback_query(F.data == "worker_menu", UserStates.menu)
async def menu_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'menu_worker...')
    kbc = KeyboardCollection()
    if user_baned := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_baned.ban_now or user_baned.forever:
            await callback.message.answer(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return
    user_worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    if not user_worker:
        await (callback.message.edit_text(
            text=f'''Упс, вы пока не зарегистрированы, как исполнитель''',
            reply_markup=kbc.registration_worker(),
        ))
        if customer := await Customer.get_customer(tg_id=callback.message.chat.id):
            await state.set_state(WorkStates.verification_worker)
            await state.update_data(city_id=str(customer.city_id), username=str(customer.tg_name))
            return
        await state.set_state(UserStates.registration_enter_city)
        if admin := await Admin.get_by_tg_id(tg_id=callback.message.chat.id):
            await state.update_data(username=str(admin.tg_name))
        return

    if not user_worker.active:
        await user_worker.update_active(active=True)

    if not user_worker.profile_name:
        text = f'Перед продолжением работы, укажите ваше имя'
        await state.set_state(WorkStates.create_name_profile)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        msg = await callback.message.answer(
            text=text
        )
        await state.update_data(msg_id=msg.message_id)
        return

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=user_worker.id)
    subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)
    work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                       worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None

    if len(user_worker.city_id) == 1:
        cites = 'Ваш город: '
        step = ''
    else:
        cites = 'Ваши города:\n'
        step = '    '
    for city_id in user_worker.city_id:
        city = await City.get_city(id=city_id)
        cites += f'{step}{city.city}\n'

    end = '\n' if subscription.count_cites == 1 else ""

    text = (f'Ваш профиль\n\n'
            f'ID: {user_worker.id} {user_worker.profile_name} {"✅" if user_worker.confirmed else "☑️"}\n'
            f'Ваш рейтинг: {round(user_worker.stars / user_worker.count_ratings, 1) if user_worker.count_ratings else user_worker.stars} ⭐️ ({user_worker.count_ratings if user_worker.count_ratings else 0} {help_defs.get_grade_word(user_worker.count_ratings if user_worker.count_ratings else 0)})\n'
            f'Наличие ИП: {"✅" if user_worker.individual_entrepreneur else "☑️"}\n'
            f'{cites + end if subscription.count_cites == 1 else ""}'
            f'Выполненных заказов: {user_worker.order_count}\n'
            f'Выполненных заказов за неделю: {user_worker.order_count_on_week}\n'
            f'Ваш тариф: {subscription.subscription_type}\n'
            f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
            f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'
            f'Зарегистрирован с {user_worker.registration_data}\n'
            f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'
            f'{cites + end if subscription.count_cites != 1 else ""}')

    choose_works = True if worker_sub.unlimited_work_types else False

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    profile_name = True if user_worker.profile_name else False

    if user_worker.profile_photo:
        await callback.message.answer_photo(
            photo=FSInputFile(user_worker.profile_photo),
            caption=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=user_worker.confirmed,
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name
            )
        )
    else:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=user_worker.confirmed,
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=True,
                create_name=profile_name
            )
        )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "menu", StateFilter(WorkStates.worker_menu, WorkStates.worker_check_abs, WorkStates.worker_check_subscription, WorkStates.worker_change_city, WorkStates.worker_responses, WorkStates.create_portfolio, WorkStates.create_name_profile, WorkStates.create_photo_profile, WorkStates.portfolio_upload_photo))
async def menu_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'menu_worker...')
    kbc = KeyboardCollection()
    if user_baned := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_baned.ban_now or user_baned.forever:
            await callback.message.answer(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return
    user_worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    if not user_worker:

        await (callback.message.edit_text(
            text=f'''Упс, вы пока не зарегистрированы, как исполнитель''',
            reply_markup=kbc.registration_worker(),
        ))

        if customer := await Customer.get_customer(tg_id=callback.message.chat.id):
            await state.set_state(UserStates.registration_end)
            await state.update_data(city_id=str(customer.city_id), username=str(customer.tg_name))
            return

        await state.set_state(WorkStates.registration_enter_city)
        return

    if not user_worker.active:
        await user_worker.update_active(active=True)

    if not user_worker.profile_name:
        text = f'Перед продолжением работы, укажите ваше имя'
        await state.set_state(WorkStates.create_name_profile)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        msg = await callback.message.answer(
            text=text
        )
        await state.update_data(msg_id=msg.message_id)
        return

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=user_worker.id)
    subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)
    work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                       worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None

    if len(user_worker.city_id) == 1:
        cites = 'Ваш город: '
        step = ''
        city = await City.get_city(id=user_worker.city_id[0])
        cites += f'{step}{city.city}\n'

    else:
        cites = 'Ваши города: '
        cites_temp = []
        for city_id in user_worker.city_id:
            city = await City.get_city(id=city_id)
            cites_temp.append(city.city)
        cites += ', '.join(cites_temp)

    end = '\n' if subscription.count_cites == 1 else ""

    text = (f'Ваш профиль\n\n'
            f'ID: {user_worker.id} {user_worker.profile_name} {"✅" if user_worker.confirmed else "☑️"}\n'
            f'Ваш рейтинг: {round(user_worker.stars / user_worker.count_ratings, 1) if user_worker.count_ratings else user_worker.stars} ⭐️ ({user_worker.count_ratings if user_worker.count_ratings else 0} {help_defs.get_grade_word(user_worker.count_ratings if user_worker.count_ratings else 0)})\n'
            f'Наличие ИП: {"✅" if user_worker.individual_entrepreneur else "☑️"}\n'
            f'{cites + end if subscription.count_cites == 1 else ""}'
            f'Выполненных заказов: {user_worker.order_count}\n'
            f'Выполненных заказов за неделю: {user_worker.order_count_on_week}\n'
            f'Ваш тариф: {subscription.subscription_type}\n'
            f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
            f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'
            f'Зарегистрирован с {user_worker.registration_data}\n'
            f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'
            f'{cites + end if subscription.count_cites != 1 else ""}')

    choose_works = True if worker_sub.unlimited_work_types else False

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    profile_name = True if user_worker.profile_name else False

    if user_worker.profile_photo:
        await callback.message.answer_photo(
            photo=FSInputFile(user_worker.profile_photo),
            caption=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=user_worker.confirmed,
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name
            )
        )
    else:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=user_worker.confirmed,
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=True,
                create_name=profile_name
            )
        )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "my_portfolio", WorkStates.worker_menu)
async def my_portfolio(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_portfolio...')

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    if worker.portfolio_photo:

        photo_len = len(worker.portfolio_photo)
        logger.debug(f'my_portfolio...{photo_len}')

        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo['0']),
            reply_markup=kbc.my_portfolio(
                photo_len=photo_len,
                new_photo=True if photo_len < 10 else False
            )
        )
    else:
        await callback.message.answer(
            text='У вас пока нет фото в портфолио',
            reply_markup=kbc.my_portfolio()
        )

    await state.set_state(WorkStates.create_portfolio)


@router.callback_query(lambda c: c.data.startswith("go-to-portfolio_"), WorkStates.create_portfolio)
async def my_portfolio(callback: CallbackQuery) -> None:
    logger.debug(f'my_portfolio...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    photo_len = len(worker.portfolio_photo)

    if photo_id <= -1:
        photo_id = photo_len - 1
    elif photo_id > (photo_len - 1):
        photo_id = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(worker.portfolio_photo[str(photo_id)])),
        reply_markup=kbc.my_portfolio(
            photo_num=photo_id,
            photo_len=photo_len,
            new_photo=True if photo_len < 10 else False
        )
    )


@router.callback_query(lambda c: c.data.startswith("delite-photo-portfolio_"), WorkStates.create_portfolio)
async def my_portfolio(callback: CallbackQuery) -> None:
    logger.debug(f'my_portfolio...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    new_portfolio = help_defs.reorder_dict(d=worker.portfolio_photo, removed_key=photo_id)

    await worker.update_portfolio_photo(new_portfolio)

    photo_len = len(new_portfolio)

    if photo_len == 0:
        await callback.message.answer(
            text='У вас пока нет фото в портфолио',
            reply_markup=kbc.my_portfolio()
        )
        return

    if photo_id <= -1:
        photo_id = photo_len - 1
    elif photo_id > (photo_len - 1):
        photo_id = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(worker.portfolio_photo[str(photo_id)])),
        reply_markup=kbc.my_portfolio(
            photo_num=photo_id,
            photo_len=photo_len,
            new_photo=True if photo_len < 10 else False
        )
    )


@router.callback_query(F.data == "upload_photo", WorkStates.create_portfolio)
async def upload_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'upload_photo...')
    kbc = KeyboardCollection()

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    text = f'Загрузите фото'

    msg = await callback.message.answer(
        text=text, reply_markup=kbc.menu()
    )

    await callback.answer(
        text=f"Вы можете прикрепить до 10 фото.\n"
             f"На фото не должно быть надписей, цифр и символов, если они присутствуют - их следует замазать перед загрузкой.\n"
             f"Загрузка видео недоступна!\n",
        show_alert=True
    )

    await state.set_state(WorkStates.portfolio_upload_photo)
    await state.update_data(msg=msg.message_id)


@router.message(F.photo, WorkStates.portfolio_upload_photo)
async def upload_photo_portfolio(message: Message, state: FSMContext) -> None:
    logger.debug(f'upload_photo_portfolio...')

    kbc = KeyboardCollection()

    # Загружаем данные состояния
    data = await state.get_data()
    album = data.get('album', [])

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


@router.callback_query(F.data == 'skip_it_photo', WorkStates.portfolio_upload_photo)
async def create_abs_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_with_photo_end...')

    kbc = KeyboardCollection()
    state_data = await state.get_data()

    msg = str(state_data.get('msg'))
    album = state_data.get('album', [])

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg)
    msg = await callback.message.answer(text='Подождите идет проверка')

    photos = {}
    photo_len = len(album)

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    portfolio_len = 0

    if worker.portfolio_photo:
        portfolio_len = len(worker.portfolio_photo)

    for i, obj in enumerate(album):
        if obj.photo:
            file_id = obj.photo[-1].file_id
        else:
            file_id = obj[obj.content_type].file_id

        file_path, _ = await help_defs.save_photo_var(id=callback.message.chat.id, n=portfolio_len + i)
        file_path_photo = f'{file_path}{portfolio_len + i}.jpg'
        await bot.download(file=file_id, destination=file_path_photo)
        text_photo = yandex_ocr.analyze_file(file_path_photo)

        if text_photo:
            if await checks.fool_check(text=text_photo):
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
                await callback.message.answer(text='На фото содержится недопустимый текст!\nПопробуйте еще раз')
                await state.clear()
                await state.set_state(WorkStates.portfolio_upload_photo)
                return

        print(file_path_photo)

        help_defs.add_watermark(file_path_photo)
        photos[str(portfolio_len + i)] = file_path_photo

    if worker.portfolio_photo:
        worker.portfolio_photo = worker.portfolio_photo | photos
        photo_len = len(worker.portfolio_photo)
    else:
        worker.portfolio_photo = photos

    await worker.update_portfolio_photo(portfolio_photo=worker.portfolio_photo)

    await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)

    await callback.message.answer_photo(
        photo=FSInputFile(worker.portfolio_photo['0']),
        reply_markup=kbc.my_portfolio(
            photo_len=photo_len,
            new_photo=True if photo_len < 10 else False
        )
    )
    await state.set_state(WorkStates.create_portfolio)


@router.callback_query(F.data == "create_photo_profile", WorkStates.worker_menu)
async def create_photo_profile(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_photo_profile...')
    kbc = KeyboardCollection()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    text = f'Загрузите фото'

    is_photo = True if worker.profile_photo else False

    msg = await callback.message.answer(
        text=text, reply_markup=kbc.photo_work_keyboard(is_photo=is_photo)
    )
    if not is_photo:
        await callback.answer(
            text=f"На снимке должно быть хорошо видно ваше лицо;\n\n"
                 f"В кадре нет других людей.\nСамое главное на фотографии — Вы!",
            show_alert=True
        )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(WorkStates.create_photo_profile)
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('photo_delite'))
async def block_photo_profile(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'block_photo_profile...')

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    await worker.update_profile_photo(profile_photo=None)
    await callback.message.delete_reply_markup()

    await state.set_state(WorkStates.worker_menu)
    await callback.message.delete()
    msg = await callback.message.answer(text=f'Фото профиля удалено!', reply_markup=kbc.menu())
    await state.update_data(worker_id=worker.tg_id, msg_id=msg.message_id)


@router.message(F.photo, WorkStates.create_photo_profile)
async def process_photos(message: Message, state: FSMContext):
    logger.debug(f"process_photos")

    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id
    file_path_photo = await help_defs.save_photo(id=message.from_user.id)
    await bot.download(file=photo, destination=file_path_photo)

    worker = await Worker.get_worker(tg_id=message.chat.id)

    text_photo = yandex_ocr.analyze_file(file_path_photo)
    logger.info(f'{text_photo}')
    if text_photo:
        if await checks.fool_check(text=text_photo):
            is_photo = True if worker.profile_photo else False
            await message.answer(text='Упс, похоже вы пытались прикрепить не соответствующее фото, повторите попытку снова 😌', reply_markup=kbc.photo_work_keyboard(is_photo=is_photo))
            return
        if checks.contains_invalid_chars(text=text_photo):
            is_photo = True if worker.profile_photo else False
            await message.answer(
                text='Упс, похоже вы пытались прикрепить не соответствующее фото, повторите попытку снова 😌',
                reply_markup=kbc.photo_work_keyboard(is_photo=is_photo))
            return

    await worker.update_profile_photo(profile_photo=file_path_photo)

    await state.set_state(WorkStates.worker_menu)

    await message.answer(text='Фото профиля успешно загружено!', reply_markup=kbc.menu_btn())

    await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG,
                         caption=f'ID #{message.chat.id}\nЗагружено новое фото профиля', photo=FSInputFile(file_path_photo),
                         protect_content=False, reply_markup=kbc.delite_it_photo(worker_id=worker.id))


@router.callback_query(F.data == "add_worker_name", WorkStates.worker_menu)
async def add_worker_name(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_photo_profile...')
    kbc = KeyboardCollection()

    text = f'Укажите ваше имя'

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    msg = await callback.message.answer(
        text=text, reply_markup=kbc.photo_name_keyboard()
    )
    await state.set_state(WorkStates.create_name_profile)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, WorkStates.create_name_profile)
async def process_photos(message: Message, state: FSMContext):
    logger.debug(f"process_photos")

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = state_data.get('msg_id')

    name = message.text

    if await checks.fool_check(name):
        text = f'Упс, кажется Вы ввели не корректно свое имя, попробуйте пожалуйста еще раз.'

        msg = await message.answer(
            text=text
        )
        await state.update_data(msg_id=msg.message_id)
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        return

    worker = await Worker.get_worker(tg_id=message.chat.id)
    await worker.update_profile_name(profile_name=name)

    await state.set_state(WorkStates.worker_menu)

    await message.answer(text='Ваше имя успешно загружено!', reply_markup=kbc.menu_btn())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(F.data == "individual_entrepreneur", WorkStates.worker_menu)
async def individual_entrepreneur(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'individual_entrepreneur...')

    kbc = KeyboardCollection()

    text = 'Введите ваш ОГРНИП'

    await state.set_state(WorkStates.individual_entrepreneur)

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.back_btn()
        )

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, WorkStates.individual_entrepreneur)
async def individual_entrepreneur_yes(message: Message, state: FSMContext) -> None:
    logger.debug(f'individual_entrepreneur_yes...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = state_data.get('msg_id')

    ogrnip = message.text

    result = help_defs.check_ip_status_by_ogrnip(ogrnip=ogrnip)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    await state.set_state(WorkStates.worker_menu)

    if result:
        worker = await Worker.get_worker(tg_id=message.chat.id)
        await worker.update_individual_entrepreneur(individual_entrepreneur=True)
        await message.answer(text=f'Ваше ИП {result}\nСтатус ИП подтвержден', reply_markup=kbc.menu())
    else:
        await message.answer(text='ИП не найдено', reply_markup=kbc.menu())


@router.callback_query(F.data == "back", WorkStates.individual_entrepreneur)
async def individual_entrepreneur_no(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'individual_entrepreneur_no...')

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    await worker.update_individual_entrepreneur(individual_entrepreneur=False)

    await state.set_state(WorkStates.worker_menu)

    await callback.message.answer(text='Вернуться в меню', reply_markup=kbc.menu())

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == 'look-abs-in-city', WorkStates.worker_menu)
async def abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    advertisements = []
    for city_id in worker.city_id:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:
            advertisements += advertisements_temp

    bad_abs = []

    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    if worker_and_reports is not None:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses is not None:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs is not None:
        bad_abs += [response.abs_id for response in worker_and_abs]

    advertisements_final = []

    if not advertisements:
        await callback.message.answer(text='Пока нет объявлений', reply_markup=kbc.menu())
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            logger.debug(f'double')
            continue
        if advertisement.id in bad_abs:
            logger.debug(f'has_reaction')
            continue
        if worker_sub.work_type_ids:
            logger.debug(f'worker_sub.work_type_ids: {worker_sub.work_type_ids}')
            logger.debug(f'advertisement.work_type_id: {advertisement.work_type_id}')
            if str(advertisement.work_type_id) in worker_sub.work_type_ids:
                if advertisement.relevance:
                    advertisements_final.append(advertisement)
        elif worker_sub.unlimited_work_types:
            logger.debug(f'worker_sub.unlimited_work_types')
            if advertisement.relevance:
                advertisements_final.append(advertisement)
        else:
            logger.debug(f'no one')

    if not advertisements_final:
        await callback.message.answer(text='По вашим выбранным направлениям, пока нет объявлений',
                                         reply_markup=kbc.menu())
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await state.set_state(WorkStates.worker_menu)
        return

    await state.set_state(WorkStates.worker_check_abs)

    abs_now : Abs = advertisements_final[0]
    await abs_now.update(views=1)
    if len(advertisements_final) > 1:
        btn_next = True
    else:
        btn_next = False

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=abs_now.id):
        btn_apply = False
        report_btn = False
    else:
        btn_apply = True
        report_btn = True

    text = help_defs.read_text_file(abs_now.text_path)

    if abs_now.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0]

    text = f'Объявление {abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text,
                                          reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                    btn_back=False,
                                                                                    btn_apply=btn_apply,
                                                                                    abs_id=abs_now.id,
                                                                                    report_btn=report_btn))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']), caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list(
                                                id_now=0,
                                                btn_next=btn_next,
                                                btn_back=False,
                                                btn_apply=btn_apply,
                                                abs_id=abs_now.id,
                                                report_btn=report_btn,
                                                count_photo=abs_now.count_photo,
                                                idk_photo=0
                                            ))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text, reply_markup=kbc.choose_obj_with_out_list(id_now=0, btn_next=btn_next,
                                                                                       btn_back=False,
                                                                                       btn_apply=btn_apply,
                                                                                       abs_id=abs_now.id,
                                                                                       report_btn=report_btn))


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    advertisements = []
    for city_id in worker.city_id:
        advertisements += await Abs.get_all_in_city(city_id=city_id)

    advertisements_final = []

    if not advertisements:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        if worker_sub.work_type_ids:
            if (advertisement.work_type_id in worker_sub.work_type_ids) or worker_sub.unlimited_work_types:
                advertisements_final.append(advertisement)
        elif worker_sub.unlimited_work_types:
            advertisements_final.append(advertisement)

    if not advertisements_final:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    abs_now = advertisements_final[abs_list_id]

    if len(advertisements_final) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=abs_now.id):
        btn_apply = False
        report_btn = False
    else:
        btn_apply = True
        report_btn = True

    text = help_defs.read_text_file(abs_now.text_path)

    if abs_now.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0]

    text = f'Объявление {abs_now.id}\n\n' + text

    await abs_now.update(views=1)

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text, reply_markup=kbc.choose_obj_with_out_list(id_now=abs_list_id,
                                                                                               btn_next=btn_next,
                                                                                               btn_back=btn_back,
                                                                                               btn_apply=btn_apply,
                                                                                               report_btn=report_btn,
                                                                                               abs_id=abs_now.id))
            return

        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']),
                                            caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list(
                                                id_now=abs_list_id,
                                                btn_next=btn_next,
                                                btn_back=btn_back,
                                                btn_apply=btn_apply,
                                                report_btn=report_btn,
                                                abs_id=abs_now.id,
                                                count_photo=abs_now.count_photo,
                                                idk_photo=0
                                            ))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text, reply_markup=kbc.choose_obj_with_out_list(id_now=abs_list_id,
                                                                                       btn_next=btn_next,
                                                                                       btn_back=btn_back,
                                                                                       btn_apply=btn_apply,
                                                                                       report_btn=report_btn,
                                                                                       abs_id=abs_now.id))


@router.callback_query(lambda c: c.data.startswith('go-to-next_'), WorkStates.worker_check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    advertisements = []
    for city_id in worker.city_id:
        advertisements += await Abs.get_all_in_city(city_id=city_id)

    advertisements_final = []

    if not advertisements:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        if worker_sub.work_type_ids:
            if (advertisement.work_type_id in worker_sub.work_type_ids) or worker_sub.unlimited_work_types:
                advertisements_final.append(advertisement)
        elif worker_sub.unlimited_work_types:
            advertisements_final.append(advertisement)

    if not advertisements_final:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    advertisement_now = advertisements_final[abs_list_id]

    btn_next = True if (len(advertisements_final) - 1 > abs_list_id) else False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_now.id):
        btn_apply = False
        report_btn = False
    else:
        btn_apply = True
        report_btn = True

    await advertisement_now.update(views=1)

    if photo_id <= -1:
        photo_id = advertisement_now.count_photo - 1
    elif photo_id > (advertisement_now.count_photo - 1):
        photo_id = 0

    if advertisement_now.photo_path:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=FSInputFile(advertisement_now.photo_path[str(photo_id)]),
                caption=callback.message.caption),
            reply_markup=kbc.choose_obj_with_out_list(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_apply=btn_apply,
                report_btn=report_btn,
                abs_id=advertisement_now.id,
                count_photo=advertisement_now.count_photo,
                idk_photo=photo_id
            )
        )
        return


@router.callback_query(F.data == "worker_type_subscription", WorkStates.worker_menu, WorkStates.worker_buy_subscription)
async def subscription_look(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'subscription_look...')
    kbc = KeyboardCollection()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_subscription_detail = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    current_subscription = await SubscriptionType.get_subscription_type(id=worker_subscription_detail.subscription_id)
    text = f"Ваш тариф {current_subscription.subscription_type}.\nВнимание, при смене любого тарифа, текущий тариф будет аннулирован" if worker_subscription_detail.subscription_id != 1 else f'Ваш тариф {current_subscription.subscription_type}\n'
    subscriptions = await SubscriptionType.get_all()
    subscriptions_ids = [sub.id for sub in subscriptions[1::]]
    subscriptions_names = [sub.subscription_type for sub in subscriptions[1::]]
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_worker_subscription(
                                      subscriptions_ids=subscriptions_ids,
                                      subscriptions_names=subscriptions_names)
                                  )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(WorkStates.worker_check_subscription)
    return


@router.callback_query(F.data == "worker_type_subscription")
async def subscription_look(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'subscription_look...')
    kbc = KeyboardCollection()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_subscription_detail = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    current_subscription = await SubscriptionType.get_subscription_type(id=worker_subscription_detail.subscription_id)
    text = f"Ваш тариф {current_subscription.subscription_type}.\nВнимание, при смене любого тарифа, текущий тариф будет аннулирован" if worker_subscription_detail.subscription_id != 1 else f'Ваш тариф {current_subscription.subscription_type}\n'
    subscriptions = await SubscriptionType.get_all()
    subscriptions_ids = [sub.id for sub in subscriptions[1::]]
    subscriptions_names = [sub.subscription_type for sub in subscriptions[1::]]
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_worker_subscription(
                                      subscriptions_ids=subscriptions_ids,
                                      subscriptions_names=subscriptions_names)
                                  )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(WorkStates.worker_check_subscription)
    return


@router.callback_query(lambda c: c.data.startswith('subscription_'), WorkStates.worker_check_subscription)
async def check_subscription(callback: CallbackQuery) -> None:
    logger.debug(f'check_subscription...')
    sub_id = int(callback.data.split('_')[1])
    kbc = KeyboardCollection()
    subscription = await SubscriptionType.get_subscription_type(id=sub_id)
    subscriptions = await SubscriptionType.get_all()
    subscriptions_ids = [sub.id for sub in subscriptions[1::]]
    subscriptions_ids.remove(sub_id)
    subscriptions_names = [sub.subscription_type for sub in subscriptions[1::]]
    subscriptions_names.remove(subscription.subscription_type)

    text = (f'Тариф <b>{subscription.subscription_type}</b>\n\n'
            f'Количество откликов: {"неограниченно" if subscription.unlimited else subscription.count_guaranteed_orders}\n'
            f'Доступные направления: {"неограниченно" if subscription.count_work_types == 100 else str(subscription.count_work_types) + " из 20"}\n'
            f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'
            f'Доступно количество городов: {subscription.count_cites}\n'
            f'Цена: {subscription.price} ₽\n')

    await callback.message.edit_text(text=text,
                                     reply_markup=kbc.choose_worker_subscription_and_buy(
                                         cur_sub_id=subscription.id,
                                         cur_sub_name=subscription.subscription_type,
                                         subscriptions_ids=subscriptions_ids,
                                         subscriptions_names=subscriptions_names),
                                     parse_mode='HTML'
                                     )


@router.callback_query(lambda c: c.data.startswith('subscription-buy_'), WorkStates.worker_check_subscription)
async def send_invoice_buy_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'send_invoice_buy_subscription...')
    sub_id = int(callback.data.split('_')[1])
    kbc = KeyboardCollection()
    subscription = await SubscriptionType.get_subscription_type(id=sub_id)
    if not subscription:
        logger.debug('Error: subscription not found')
        return
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    prices = [LabeledPrice(label=f"{subscription.subscription_type}",
                           amount=int(subscription.price * 100))]

    text = f"Активация доступа на отклики на 1 месяц по тарифу {subscription.subscription_type}"

    await state.set_state(WorkStates.worker_buy_subscription)

    await callback.message.answer_invoice(
        title=f"Тариф {subscription.subscription_type}",
        description=text,
        provider_token=config.PAYMENTS,
        currency="RUB",  # Валюта в верхнем регистре
        prices=prices,
        start_parameter="one-month-subscription",
        payload="invoice-payload",
        reply_markup=kbc.worker_buy_subscription(),
        need_email=True,
        send_email_to_provider=True
    )
    await state.update_data(worker_id=str(worker.id),
                            subscription_id=str(subscription.id))


@router.pre_checkout_query(lambda query: True, WorkStates.worker_buy_subscription)
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    logger.debug(f'pre_checkout_handler...')
    await pre_checkout_query.answer(ok=True)


@router.callback_query(F.data == 'use-bonus')
async def success_payment_handler(callback: CallbackQuery, state: FSMContext):
    logger.debug(f'success_payment_handler...')
    kbc = KeyboardCollection()

    subscription_id = 6

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
        if worker_and_ref.worker_bonus:
            await worker_and_ref.update(worker_bonus=False)
        else:
            return
    elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
        if worker_and_ref.ref_bonus:
            await worker_and_ref.update(ref_bonus=False)
        else:
            return
    else:
        return

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=subscription_id)

    await worker_sub.update(
        guaranteed_orders=subscription.count_guaranteed_orders,
        subscription_end=datetime.date.today() + datetime.timedelta(days=30),
        subscription_id=subscription_id,
        unlimited_orders=True if subscription.count_guaranteed_orders == 10000 else False,
        unlimited_work_types=True if subscription.count_work_types == 18 else False
    )

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    btn_back = True

    await callback.message.edit_text(
        text=f"Бонус успешно использован!\n\nВыберите направления!\nВыбрано 0 из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )
    await state.set_state(WorkStates.worker_choose_work_types)
    await state.update_data(subscription_id=str(subscription_id))
    await state.update_data(count_work_types=str(subscription.count_work_types))
    await state.update_data(work_type_ids='')


@router.message(F.successful_payment, WorkStates.worker_buy_subscription)
async def success_payment_handler(message: Message, state: FSMContext):
    logger.debug(f'success_payment_handler...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    worker_id = int(state_data.get('worker_id'))
    subscription_id = int(state_data.get('subscription_id'))

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker_id)
    subscription = await SubscriptionType.get_subscription_type(id=subscription_id)

    await worker_sub.update(
        guaranteed_orders=subscription.count_guaranteed_orders,
        subscription_end=datetime.date.today() + datetime.timedelta(days=30),
        subscription_id=subscription_id,
        unlimited_orders=True if subscription.count_guaranteed_orders == 10000 else False,
        unlimited_work_types=True if subscription.count_work_types == 20 else False
    )

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False

    await message.answer(
        text=f"Спасибо, ваш платеж на сумму {subscription.price}₽ успешно выполнен!\n\nВыберите направления!\nВыбрано 0 из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )
    await state.set_state(WorkStates.worker_choose_work_types)
    await state.update_data(subscription_id=str(subscription_id))
    await state.update_data(count_work_types=str(subscription.count_work_types))
    await state.update_data(work_type_ids='')


@router.callback_query(F.data == 'choose_work_types', WorkStates.worker_menu)
async def choose_work_types(callback: CallbackQuery, state: FSMContext):
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

    work_types = await WorkType.get_all()

    names = [work_type.work_type for work_type in work_types]
    ids = [work_type.id for work_type in work_types]

    await callback.message.answer(
        text=f"Выберете направления! Выбрано 0 из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=True)
    )

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await state.set_state(WorkStates.worker_choose_work_types)
    await state.update_data(subscription_id=str(subscription.id))
    await state.update_data(count_work_types=str(subscription.count_work_types))
    await state.update_data(work_type_ids='')


@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_choose_work_types)
async def choose_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    count_work_types = int(state_data.get('count_work_types'))
    subscription_id = int(state_data.get('subscription_id'))
    work_type_ids = str(state_data.get('work_type_ids'))

    work_type_id_str = work_type_ids + '|' + str(callback.data.split('_')[1])
    work_type_id_list = work_type_id_str.split('|')
    while '' in work_type_id_list:
        work_type_id_list.remove('')
    work_type_id_str = '|'.join(work_type_id_list)

    await state.update_data(count_work_types=str(count_work_types))
    await state.update_data(work_type_ids=str(work_type_id_str))

    if int(callback.data.split('_')[1]) == 20:
        await callback.message.edit_text(text='*В этом направлении:* \n\n - Бармен\n - Официант\n - Повар\n - Хостес\n - Уборщица\n - Охрана\n - Курьер\n - Кальянщик',
                                         reply_markup=kbc.worker_apply_work_type()
                                         )
        return

    work_types = await WorkType.get_all()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    if len(work_type_id_list) == count_work_types:
        if len(work_type_id_list) == 1:
            text = 'Отлично, направление выбрано'
        else:
            text = 'Отлично, направления выбраны'
        await worker_sub.update(work_type_ids=work_type_id_list)
        await callback.message.edit_text(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    subscription = await SubscriptionType.get_subscription_type(id=subscription_id)

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False

    await callback.message.edit_text(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)} из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )


@router.callback_query(lambda c: c.data.startswith('good'), WorkStates.worker_choose_work_types)
async def choose_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    count_work_types = int(state_data.get('count_work_types'))
    subscription_id = int(state_data.get('subscription_id'))
    work_type_ids = str(state_data.get('work_type_ids'))

    work_type_id_list = work_type_ids.split('|')
    while '' in work_type_id_list:
        work_type_id_list.remove('')

    work_types = await WorkType.get_all()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    if len(work_type_id_list) == count_work_types:
        if len(work_type_id_list) == 1:
            text = 'Отлично, направление выбрано'
        else:
            text = 'Отлично, направления выбраны'
        await worker_sub.update(work_type_ids=work_type_id_list)
        await callback.message.edit_text(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    subscription = await SubscriptionType.get_subscription_type(id=subscription_id)

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False

    await callback.message.edit_text(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)} из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )


@router.callback_query(lambda c: c.data.startswith('bad'), WorkStates.worker_choose_work_types)
async def choose_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    count_work_types = int(state_data.get('count_work_types'))
    subscription_id = int(state_data.get('subscription_id'))
    work_type_ids = str(state_data.get('work_type_ids'))

    work_type_id_list = work_type_ids.split('|')
    work_type_id_list.remove('20')
    while '' in work_type_id_list:
        work_type_id_list.remove('')
    work_type_id_str = '|'.join(work_type_id_list)

    await state.update_data(count_work_types=str(count_work_types))
    await state.update_data(work_type_ids=str(work_type_id_str))

    work_types = await WorkType.get_all()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    if len(work_type_id_list) == count_work_types:
        if len(work_type_id_list) == 1:
            text = 'Отлично, направление выбрано'
        else:
            text = 'Отлично, направления выбраны'
        await worker_sub.update(work_type_ids=work_type_id_list)
        await callback.message.edit_text(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    subscription = await SubscriptionType.get_subscription_type(id=subscription_id)

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False

    await callback.message.edit_text(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)} из {subscription.count_work_types}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )


@router.callback_query(F.data == 'back', WorkStates.worker_choose_work_types)
async def choose_work_types_end(callback: CallbackQuery, state: FSMContext) -> None:
    kbc = KeyboardCollection()
    logger.debug(f'choose_work_types_end...')

    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids'))

    work_type_id_str = work_type_ids
    work_type_id_list = work_type_id_str.split('|')

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    await worker_sub.update(work_type_ids=work_type_id_list)

    logger.debug(f'work_type_id_str...{work_type_id_str}')
    logger.debug(f'work_type_id_list...{work_type_id_list}')

    while '' in work_type_id_list:
        work_type_id_list.remove('')

    if len(work_type_id_list) != 0:
        await callback.message.edit_text(f'Выбраны {len(work_type_id_list)} из 18 направлений!',
                                         reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    await callback.message.edit_text('Выбраны 20 из 20 направлений!', reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_menu)
    return


@router.callback_query(lambda c: c.data.startswith('apply-it-first_'))
async def apply_order(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order...')
    kbc = KeyboardCollection()

    if user_blocked := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_blocked.ban_now or user_blocked.forever:
            await callback.message.edit_text(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    if worker_sub.guaranteed_orders <= 0 and not worker_sub.unlimited_orders:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Упс, у вас закончились отклики', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return
    elif worker_sub.subscription_end:
        if datetime.datetime.strptime(worker_sub.subscription_end, "%d.%m.%Y") <= datetime.datetime.now():
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(text='Упс, у истек срок подписки')
            return

    await state.clear()
    advertisement_id = int(callback.data.split('_')[1])
    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Похоже объявление больше не актуально',
                                      reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    if advertisement.work_type_id == 20:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        worker_and_abs = WorkersAndAbs(worker_id=worker.id, abs_id=advertisement_id)
        await worker_and_abs.save()
        worker_and_abs.worker_messages.append('Отправлен отклик')
        worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id)
        await worker_and_abs.update(worker_messages=worker_and_abs.worker_messages,
                                    send_by_worker=worker_and_abs.send_by_worker - 1, turn=True)

        text = help_defs.read_text_file(advertisement.text_path)

        text_list = text.split(' ||| ')
        text = text_list[0]

        text = f'Отклик по объявлению ID{advertisement_id}\n\n' + text
        if user_worker := await Worker.get_worker(tg_id=customer.tg_id):
            if not user_worker.active:
                await bot.send_message(chat_id=customer.tg_id, text=text, reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id))
        else:
            await bot.send_message(chat_id=customer.tg_id, text=text, reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id))
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await state.set_state(WorkStates.worker_menu)
        await callback.message.answer('Ваш отклик успешно отправлен', reply_markup=kbc.menu())
        return

    text = f'Вы можете указать свою цену за работу или задать вопрос по заказу'
    if worker_sub.subscription_id not in [1, 6, 7, 8, 9]:
        await worker_sub.update(guaranteed_orders=worker_sub.guaranteed_orders - 1)

    await state.set_state(WorkStates.worker_apply_order)
    await state.update_data(abs_id=advertisement_id)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    msg = await callback.message.answer(text=text,
                                        reply_markup=kbc.apply_final_btn_var(idk=advertisement_id, name='Пропустить',
                                                                             send_btn_name='Написать заказчику',
                                                                             send_btn=True,
                                                                             skip_btn=False, role='worker'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('go-to-apply_'))
async def apply_order_next_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order...')
    kbc = KeyboardCollection()

    if user_blocked := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_blocked.ban_now or user_blocked.forever:
            await callback.message.edit_text(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return

    photo_id = int(callback.data.split('_')[1])
    advertisement_id = int(callback.data.split('_')[2])

    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Похоже объявление больше не актуально',
                                      reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    if photo_id <= -1:
        photo_id = advertisement.count_photo - 1
    elif photo_id > (advertisement.count_photo - 1):
        photo_id = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(advertisement.photo_path[str(photo_id)]),
            caption=callback.message.caption),
        protect_content=False,
        reply_markup=kbc.apply_btn(
            abs_id=advertisement.id,
            photo_num=photo_id,
            photo_len=advertisement.count_photo)
    )


@router.callback_query(F.data == 'my_responses', StateFilter(WorkStates.worker_menu,  WorkStates.worker_responses))
async def my_responses(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_responses...')

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    if not worker_and_abs:
        await callback.message.answer(text='У вас нет активных откликов', reply_markup=kbc.menu())
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        return

    btn_names = []
    btn_ids = []

    for response in worker_and_abs:
        advertisement = await Abs.get_one(id=response.abs_id)
        btn_name = f'Объявление ID {advertisement.id}'
        btn_names.append(btn_name)
        btn_ids.append(advertisement.id)

    await state.set_state(WorkStates.worker_responses)
    await callback.message.answer(text='Выберите отклик',
                                     reply_markup=kbc.choose_response_worker(ids=btn_ids, names=btn_names))
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('worker-response_'), WorkStates.worker_responses)
async def worker_response(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'worker_response...')

    kbc = KeyboardCollection()

    advertisement_id = int(callback.data.split('_')[1])

    advertisement = await Abs.get_one(id=advertisement_id)
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement.id)

    text = help_defs.read_text_file(advertisement.text_path)

    send_btn = True if worker_and_abs.send_by_worker > 0 and not worker_and_abs.turn else False

    skip_btn = True

    if advertisement.work_type_id == 20:
        text_list = text.split(' ||| ')
        text = text_list[0]
        send_btn = False
        skip_btn = False

    text = f'{text}\n\n'

    count_messages = max([len(worker_and_abs.worker_messages), len(worker_and_abs.customer_messages)])

    for i in range(count_messages):
        if i < len(worker_and_abs.worker_messages):
            if worker_and_abs.worker_messages[i] == 'Исполнитель не отправил сообщение':
                text += f' - {worker_and_abs.worker_messages[i]}\n'
            else:
                text += f' - Вы: "{worker_and_abs.worker_messages[i]}"\n'

        if i < len(worker_and_abs.customer_messages):
            text += f' - Заказчик: "{worker_and_abs.customer_messages[i]}"\n'

    await state.set_state(WorkStates.worker_responses)
    if advertisement.work_type_id == 20:
        text = help_defs.read_text_file(advertisement.text_path)
        text_list = text.split(' ||| ')
        text = text_list[0]
        text = f'{text}\n\n'
        if len(worker_and_abs.customer_messages) > 0:
            text += f' - Заказчик: "{worker_and_abs.customer_messages[0]}"\n'
    try:
        msg = await callback.message.edit_text(text=text,
                                               reply_markup=kbc.apply_final_btn(idk=advertisement_id, skip_btn=skip_btn,
                                                                                send_btn=send_btn,
                                                                                send_btn_name='Ответить заказчику',
                                                                                skip_btn_name='Отказаться и удалить',
                                                                                role='worker', btn_back=True))
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('apply-it_'))
async def apply_order(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order...')
    kbc = KeyboardCollection()

    if user_blocked := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_blocked.ban_now or user_blocked.forever:
            await callback.message.edit_text(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    if worker_sub.guaranteed_orders <= 0 and not worker_sub.unlimited_orders:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Упс, у вас закончились отклики', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return
    elif worker_sub.subscription_end:
        if datetime.datetime.strptime(worker_sub.subscription_end, "%d.%m.%Y")  <= datetime.datetime.now():
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(text='Упс, у истек срок подписки')
            return

    await state.clear()
    advertisement_id = int(callback.data.split('_')[1])
    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Похоже объявление больше не актуально',
                                      reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id):
        if not worker_and_abs.applyed:
            if worker_and_abs.send_by_worker > 0:
                text = f'Отправьте вопрос к заказчику или примите объявление сразу.\n\nВы можете отправить: ещё {worker_and_abs.send_by_worker}/4 сообщений'
            else:
                text = 'Примите объявление или откажитесь'
        else:
            text = 'Ваш отклик уже принят'
    else:
        text = f'Отправьте вопрос к заказчику или примите объявление сразу.\n\nВы можете отправить еще {4}/4 сообщений'

    await state.set_state(WorkStates.worker_apply_order)
    await state.update_data(abs_id=advertisement_id)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    if worker_and_abs.applyed:
        await callback.message.answer(text='Ваш отклик уже принят', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
    msg = await callback.message.answer(text=text,
                                        reply_markup=kbc.apply_final_btn(idk=advertisement_id,
                                                                         send_btn_name='Ответить заказчику',
                                                                         send_btn=True,
                                                                         skip_btn=True, skip_btn_name='Удалить отклик',
                                                                         role='worker'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('report-it_'))
async def report_order(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'report_order...')
    if user_blocked := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_blocked.ban_now or user_blocked.forever:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(text='Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)
            return

    kbc = KeyboardCollection()
    await state.clear()
    advertisement_id = int(callback.data.split('_')[1])
    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Похоже объявление больше не актуально',
                                      reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    await state.set_state(WorkStates.worker_menu)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text='Ваша жалоба будет рассмотрена',
                                  reply_markup=kbc.menu())

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    if not await WorkerAndReport.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id):
        worker_and_report = WorkerAndReport(worker_id=worker.id, abs_id=advertisement_id)
        await worker_and_report.save()

    customer = await Customer.get_customer(id=advertisement.customer_id)

    text = f'Заказчик ID {customer.tg_id}\nОбъявление {advertisement.id}\n\n' + help_defs.read_text_file(advertisement.text_path)
    if advertisement.photo_path:
        await bot.send_photo(chat_id=config.REPORT_LOG,
                             photo=FSInputFile(advertisement.photo_path),
                             caption=text,
                             reply_markup=kbc.block_abs(advertisement_id), protect_content=False)
    else:
        await bot.send_message(chat_id=config.REPORT_LOG,
                               text=text,
                               reply_markup=kbc.block_abs(advertisement_id), protect_content=False)


@router.callback_query(lambda c: c.data.startswith('apply-final-it_'), WorkStates.worker_apply_order)
async def apply_order_with_out_msg(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order_with_out_msg...')
    kbc = KeyboardCollection()
    advertisement_id = int(callback.data.split('_')[1])
    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        await callback.message.edit_text(text='Похоже объявление больше не актуально',
                                         reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    customer = await Customer.get_customer(id=advertisement.customer_id)
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    text = (f'Исполнитель {worker.id} {"✅" if worker.confirmed else "☑️"}\n'
            f'Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️\n'
            f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
            f'Выполненных заказов: {worker.order_count}\n'
            f'Объявление {advertisement.id}\n\n'
            f'{help_defs.read_text_file(advertisement.text_path)}')

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id):
        if worker_and_abs.applyed:
            await callback.message.edit_text(text='Ваш отклик уже был отправлен и принят',
                                             reply_markup=kbc.menu())
            await state.set_state(WorkStates.worker_menu)
            return
    else:
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        worker_and_abs = WorkersAndAbs(worker_id=worker.id, abs_id=advertisement_id)
        await worker_and_abs.save()
        if not worker_sub.unlimited_orders:
            if worker_sub.subscription_id != 1:
                await worker_sub.update(guaranteed_orders=worker_sub.guaranteed_orders - 1)

    try:
        if user_worker := await Worker.get_worker(tg_id=customer.tg_id):
            if not user_worker.active:
                await bot.send_message(chat_id=customer.tg_id, text=text,
                                       reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id))
        else:
            await bot.send_message(chat_id=customer.tg_id, text=text,
                                   reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id))
    except Exception:
        text = (f'Исполнитель {worker.id} {"✅" if worker.confirmed else "☑️"}\n'
                f'Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️\n'
                f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                f'Выполненных заказов: {worker.order_count}')
        await bot.send_message(chat_id=customer.tg_id, text=text,
                               reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id))

    await callback.message.edit_text(text='Отклик успешно отправлен!', reply_markup=kbc.btn_back_to_responses())
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(lambda c: c.data.startswith('hide-obj-worker_'))
async def hide_order(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'hide_order...')
    kbc = KeyboardCollection()
    advertisement_id = int(callback.data.split('_')[1])

    if banned := await Banned.get_banned(callback.message.chat.id):
        if banned.ban_now:
            await callback.message.edit_text('Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)

    advertisement = await Abs.get_one(id=advertisement_id)
    if not advertisement:
        await callback.message.edit_text(text='Похоже объявление больше не актуально',
                                         reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    customer = await Customer.get_customer(id=advertisement.customer_id)
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)

    worker_and_advertisement = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id)
    await worker_and_advertisement.delete()
    worker_and_bad_report = WorkerAndBadResponse(abs_id=advertisement_id, worker_id=worker.id)
    await worker_and_bad_report.save()

    await bot.send_message(
        chat_id=customer.tg_id,
        text=f'К сожалению, исполнитель ID {worker.id} отменил отклик на ваш заказ',
        reply_markup=kbc.customer_menu(
            abs_id=advertisement_id
        )
    )

    await callback.message.edit_text(text='Отклик удален!', reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(lambda c: c.data.startswith('answer-obj-worker_'))
async def apply_order_with_out_msg(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_order_with_msg...')
    advertisement_id = int(callback.data.split('_')[1])
    if banned := await Banned.get_banned(callback.message.chat.id):
        if banned.ban_now:
            await callback.message.edit_text('Упс, вы заблокированы')
            await state.set_state(BannedStates.banned)

    await callback.answer(
        text=f"Чтобы избежать блокировку, не используйте в переписке с заказчиком:\n"
             f"- Ссылки\n"
             f"- Латинские буквы\n"
             f"- Названия любых агрегаторов, мессенджеров и маркетплейсов",
        show_alert=True
    )

    await state.set_state(WorkStates.worker_apply_order)
    await state.update_data(abs_id=advertisement_id)
    msg = await callback.message.edit_text('Напишите вопрос заказчику')
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, WorkStates.worker_apply_order)
async def apply_order_with_msg(message: Message, state: FSMContext) -> None:
    logger.debug(f'apply_order_with_msg...')

    kbc = KeyboardCollection()

    msg_to_send = message.text

    state_data = await state.get_data()
    advertisement_id = int(state_data.get('abs_id'))
    msg_id = int(state_data.get('msg_id'))

    advertisement = await Abs.get_one(id=advertisement_id)

    if not advertisement:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer(text='Похоже объявление больше не актуально',
                             reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    customer = await Customer.get_customer(id=advertisement.customer_id)
    worker = await Worker.get_worker(tg_id=message.chat.id)

    if worker_and_abs := await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id):
        text = (f'Новое сообщение\n\n'
                f'<b>Исполнитель</b> {worker.id} {worker.profile_name if worker.profile_name else ""}\n'
                f'<b>Рейтинг</b>: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
                f'<b>Верификация</b>: {"✅" if worker.confirmed else "☑️"}\n'
                f'<b>Наличие ИП</b>: {"✅" if worker.individual_entrepreneur else "☑️"}\n\n'
                f'<b>Выполненных заказов</b>: {worker.order_count}\n\n'
                f'Объявление {advertisement.id}\n\n{help_defs.read_text_file(advertisement.text_path)}')
    else:
        worker_and_abs = WorkersAndAbs(worker_id=worker.id, abs_id=advertisement_id)
        await worker_and_abs.save()
        worker_and_abs = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_id)
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        if not worker_sub.unlimited_orders:
            if worker_sub.subscription_id != 1:
                await worker_sub.update(guaranteed_orders=worker_sub.guaranteed_orders - 1)
        text = (f'Новый отклик \n\n<b>Исполнитель</b> {worker.id} {worker.profile_name if worker.profile_name else ""}\n'
                f'<b>Рейтинг</b>: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
                f'<b>Верификация</b>: {"✅" if worker.confirmed else "☑️"}\n'
                f'<b>Наличие ИП</b>: {"✅" if worker.individual_entrepreneur else "☑️"}\n\n'
                f'<b>Выполненных заказов</b>: {worker.order_count}\n\n'
                f'Объявление {advertisement.id}\n\n{help_defs.read_text_file(advertisement.text_path)}')

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

    if len(msg_to_send) > 200:
        await message.answer(
            text=f'В сообщении должно быть не более 200 символов')
        return
    try:
        await bot.send_message(chat_id=config.MESSAGE_LOG,
                               text=f'Исполнитель #{message.chat.id} отправил сообщение заказчику #{customer.tg_id}: "{message.text}"',
                               protect_content=False, reply_markup=kbc.block_message_log(user_id=message.chat.id))
    except TelegramBadRequest:
        pass

    try:
        if user_worker := await Worker.get_worker(tg_id=customer.tg_id):
            if not user_worker.active:
                await bot.send_message(chat_id=customer.tg_id, text=text,
                                       reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id),
                                       parse_mode='HTML')
        else:
            await bot.send_message(chat_id=customer.tg_id, text=text,
                                   reply_markup=kbc.look_worker(worker_id=worker.id, abs_id=advertisement_id),
                                   parse_mode='HTML')

    except Exception as e:
        logger.info(f'apply_order_with_msg... Except: {e}')

    await message.answer(
        text=f'Сообщение успешно отправлено!',
        reply_markup=kbc.btn_back_to_responses())

    if worker_and_abs.send_by_worker == 100 and worker_and_abs.send_by_customer == 100:
        await worker_and_abs.update(worker_messages=[msg_to_send], send_by_worker=worker_and_abs.send_by_worker - 1)
    else:
        worker_and_abs.worker_messages.append(msg_to_send)
        await worker_and_abs.update(worker_messages=worker_and_abs.worker_messages,
                                    send_by_worker=worker_and_abs.send_by_worker - 1, turn=True)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "worker_change_city", WorkStates.worker_menu)
async def change_city_main(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_main...')
    kbc = KeyboardCollection()

    await state.set_state(WorkStates.worker_change_city)

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.answer(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}\n\n'
             f'По вашей подписке доступно количество городов: {subscription.count_cites}, выбрано 0',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False, menu_btn=True)
    )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, WorkStates.worker_change_city)
async def choose_city_main(message: Message, state: FSMContext) -> None:
    logger.debug(f'choose_city_main...')
    kbc = KeyboardCollection()

    city_input = message.text

    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id'))
    cites = state_data.get('cites')

    cities = await City.get_all(sort=False)
    city_names = [city.city for city in cities]

    worker = await Worker.get_worker(tg_id=message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

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

    if cites is None:
        cites = []
    else:
        cites = [int(x) for x in cites.split(' | ')]
        for city_id in cites:
            city = await City.get_city(id=city_id)
            try:
                city_names.remove(city.city)
                city_ids.remove(city.id)
            except ValueError:
                pass

    msg = await message.answer(
        text=f'Результаты поиска по: {city_input}\n'
             f'Выберите город или напишите его текстом\n\n'
             f'По вашей подписке доступно количество городов: {subscription.count_cites}, выбрано {len(cites)}',
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=False, menu_btn=True, btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_change_city)
async def change_city_next(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_next...')

    kbc = KeyboardCollection()

    id_now = int(callback.data.split('_')[1])

    state_data = await state.get_data()
    cites = state_data.get('cites')

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

    if cites is None:
        cites = []
    else:
        cites = [int(x) for x in cites.split(' | ')]
        for city_id in cites:
            city = await City.get_city(id=city_id)
            city_names.remove(city.city)
            city_ids.remove(city.id)

    count_cities = len(city_names)

    btn_next = True if count_cities > 5 + id_now else False
    btn_back = True if id_now >= 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    try:
        msg = await callback.message.edit_text(
            text=f'Выберите город или напишите его текстом\n\n'
                 f' Показано {id_now + len(city_names)} из {count_cities}\n\n'
                 f'По вашей подписке доступно количество городов: {subscription.count_cites} городов, выбрано {len(cites)}\n',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back, menu_btn=True))
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_change_city)
async def change_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'change_city_end...')
    kbc = KeyboardCollection()

    city_id = int(callback.data.split('_')[1])

    state_data = await state.get_data()
    cites = state_data.get('cites')
    if cites is None:
        cites_list = [city_id]
    else:
        cites_list = [int(x) for x in cites.split(' | ')]
        cites_list.append(city_id)

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

    if len(cites_list) >= subscription.count_cites:
        await worker.update_city(city_id=cites_list)
        await callback.message.edit_text('Вы успешно сменили город!', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    id_now = int(callback.data.split('_')[2])

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]

    for city_id in cites_list:
        city = await City.get_city(id=city_id)
        city_names.remove(city.city)
        city_ids.remove(city.id)

    count_cities = len(city_names)

    btn_next = True if count_cities > 5 + id_now else False
    btn_back = True if id_now >= 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    msg = await callback.message.edit_text(
        text=f'Выберите город или напишите его текстом\n\n'
             f'Показано {id_now + len(city_names)} из {count_cities}\n\n'
             f'По вашей подписке доступно количество городов: {subscription.count_cites} городов, выбрано {len(cites_list)}\n',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=btn_back, menu_btn=True))
    await state.update_data(msg_id=msg.message_id)
    cites_list = [str(x) for x in cites_list]
    await state.update_data(cites=' | '.join(cites_list))


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
