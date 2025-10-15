import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

import config
from app.data.database.models import Admin, Customer, Worker, City, Banned, Abs, InfoHaltura, UserAndSupportQueue, \
    WorkerAndRefsAssociation, BannedAbs, AskAnswer, WorkerAndSubscription, SubscriptionType, WorkType
from app.keyboards import KeyboardCollection
from app.states import WorkStates, UserStates, BannedStates, CustomerStates, AdminStates
from app.untils import help_defs, checks
from loaders import bot

router = Router()
logger = logging.getLogger()
router.message.filter(F.from_user.id != F.bot.id)


@router.message(Command("ping"))
async def ping_cmd(message: Message) -> None:
    await message.answer(text='''⊂ヽ
  ＼＼ Λ＿Λ
   ＼( ˇωˇ) 
     ⌒ヽ
   /   へ＼
   /  / ＼＼
   ﾚ ノ   ヽつWeb Tech
  / /
  / /|
 ( (ヽ
 | |、＼
 | 丿 ＼ ⌒)
 | |  ) /
`ノ )  Lﾉ
(_／''')


async def get_user_data_optimized(tg_id: int):
    """Оптимизированное получение всех данных пользователя одним запросом"""
    import aiosqlite

    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute('''
                                    SELECT (SELECT id FROM ban_list WHERE tg_id = ? AND (ban_now = 1 OR forever = 1)) as banned_id,
                                           (SELECT id FROM admins WHERE tg_id = ?)                                    as admin_id,
                                           (SELECT id FROM workers WHERE tg_id = ?)                                   as worker_id,
                                           (SELECT id FROM customers WHERE tg_id = ?)                                 as customer_id
                                    ''', (tg_id, tg_id, tg_id, tg_id))

        result = await cursor.fetchone()
        await cursor.close()

        return {
            'banned_id': result[0],
            'admin_id': result[1],
            'worker_id': result[2],
            'customer_id': result[3]
        }
    finally:
        await conn.close()


@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext) -> None:
    logger.debug(f'start_cmd... chat_id: {message.chat.id}')

    if message.chat.id < 0:
        await message.answer('Пользоваться ботом можно только из ЛС')
        return

    # Удаляем клавиатуры
    msg = await message.answer(f'Удаляю клавиатуры',
                               reply_markup=ReplyKeyboardRemove())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    await state.clear()
    kbc = KeyboardCollection()

    # Получаем все данные пользователя одним запросом
    user_data = await get_user_data_optimized(message.chat.id)

    # Проверяем блокировку
    if user_data['banned_id']:
        await message.answer(text='Упс, вы заблокированы')
        await state.set_state(BannedStates.banned)
        return

    # Проверяем админа
    if user_data['admin_id']:
        user_admin = await Admin.get_by_tg_id(tg_id=message.chat.id)
        await state.set_state(UserStates.menu)
        await message.answer(
            text=f'Добро пожаловать, {user_admin.tg_name}',
            reply_markup=kbc.menu_keyboard(admin=True),
        )
        return

    # Проверяем исполнителя
    elif user_data['worker_id']:
        user_worker = await Worker.get_worker(tg_id=message.chat.id)
        await message.answer(
            text=f'Добро пожаловать, {user_worker.tg_name}',
            reply_markup=kbc.menu(),
        )
        await state.set_state(WorkStates.worker_menu)
        return

    # Проверяем заказчика
    elif user_data['customer_id']:
        user_customer = await Customer.get_customer(tg_id=message.chat.id)
        await message.answer(
            text=f'Добро пожаловать, {user_customer.tg_name}',
            reply_markup=kbc.menu(),
        )
        await state.set_state(CustomerStates.customer_menu)
        return

    else:
        # Новый пользователь - показываем приветствие
        text = '''Размещаются запросы только на услуги:

 — анонимно;
 — без ссылок;
 — номера телефона;

После успешной публикации, заказчику поступают в личку отклики от исполнителей с рейтингом и количеством выполненных заказов.

Заказчику остается только выбрать подходящего и связаться лично.

После завершения работы - заказчик закрывает заказ и оставляет отзыв.

Исполнителям поступают запросы в личку по направлениям, которые они выбрали и совершают отклики.

<b>Запросы на услуги размещаются бесплатно без ограничений.</b>

<b>За попытку предложений не по теме предусмотрена блокировка.</b>
'''

        # Обрабатываем параметры команды /start
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            param = args[1]
            logger.debug(f'start param: {param}')

            # Проверяем, является ли параметр городом
            city = await City.get_city(city_en=param)
            if city is not None:
                await state.set_state(UserStates.registration_end)
                await state.update_data(city_id=str(city.id), username=str(message.from_user.username))
                return

            # Проверяем, является ли параметр ID исполнителя (реферальная ссылка)
            try:
                worker_id = int(param)
                worker = await Worker.get_worker(tg_id=worker_id)
                if worker is not None:
                    logger.debug(f'Referral link activated for worker {worker_id}')
                    # Проверяем, не активирована ли уже реферальная ссылка
                    existing_ref = await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id)
                    if not existing_ref:
                        worker_and_ref = WorkerAndRefsAssociation(id=None,
                                                                  worker_id=worker.id,
                                                                  ref_id=message.chat.id,
                                                                  work_condition=True if worker.order_count >= 5 else False,
                                                                  ref_condition=False)
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=f'Ваша реферальная ссылка была успешно активирована!')
                        await message.answer(
                            'Реферальная ссылка была успешно активирована, для получения бонуса выполните 5 заказов',
                            reply_markup=kbc.btn_ok())
                        await worker_and_ref.save()
                        await state.set_state(UserStates.registration_enter_city)
                        await state.update_data(username=str(message.from_user.username))
                        return
            except ValueError:
                # Параметр не является числом, игнорируем
                pass

        # Показываем приветственное сообщение новому пользователю
        await message.answer_photo(
            photo=FSInputFile('app/data/database/WhatsApp.jpg'),
            caption=text,
            reply_markup=kbc.apply_user_agreement(),
            parse_mode='HTML'
        )
        await state.set_state(UserStates.registration_enter_city)
        await state.update_data(username=str(message.from_user.username))


@router.callback_query(F.data == 'ok', StateFilter(UserStates.registration_enter_city))
async def apply_user_agreement(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'apply_user_agreement...')
    state_data = await state.get_data()
    username = str(state_data.get('username'))
    text = '''Размещаются запросы только на услуги:

     — анонимно;
     — без ссылок;
     — номера телефона;

    После успешной публикации, заказчику поступают в личку отклики от исполнителей с рейтингом и количеством выполненных заказов. 

    Заказчику остается только выбрать подходящего и связаться лично. 

    После завершения работы - заказчик закрывает заказ и оставляет отзыв. 

    Исполнителям поступают запросы в личку по направлениям, которые они выбрали и совершают отклики.

    <b>Запросы на услуги размещаются бесплатно без ограничений.</b>

    <b>За попытку предложений не по теме предусмотрена блокировка.</b>
    '''
    kbc = KeyboardCollection()
    await callback.message.answer_video(
        video=FSInputFile('app/data/database/Haltura.mp4'),
        caption=text,
        reply_markup=kbc.apply_user_agreement(),
        parse_mode='HTML'
    )
    await state.set_state(UserStates.registration_enter_city)
    await state.update_data(username=username)
    return


@router.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext) -> None:
    logger.debug('admin_menu...')
    kbc = KeyboardCollection()

    admins = await Admin.get_all()

    admins_tg_ids = [admin.tg_id for admin in admins]
    if message.chat.id not in admins_tg_ids:
        await message.answer('У вас недостаточно прав для этой команды')
        return

    customers = await Customer.get_all()
    workers = await Worker.get_all()
    banned_users = await Banned.get_all()
    admin = await Admin.get_by_tg_id(message.chat.id)
    users = []

    users += workers
    for customer in customers:
        if await Worker.get_worker(tg_id=customer.tg_id) is None:
            users.append(customer)

    banned_now = []
    len_banned_users = 0
    if banned_users:
        for banned in banned_users:
            if banned.ban_now or banned.forever:
                banned_now.append(banned)
        len_banned_users = len(banned_now)

    len_worker = len(workers) if workers else 0
    len_customer = len(customers) if customers else 0
    advertisement = await Abs.get_all()
    banned_advertisement = await BannedAbs.get_all()
    len_banned_advertisement = len(banned_advertisement) if banned_advertisement else 0
    len_advertisement = len(advertisement) if advertisement else 0
    len_users = len(users) if users else 0

    text = (f'Меню\n\n'
            f'Всего пользователей: {len_users}\n'
            f'Заказчиков: {len_customer}\n'
            f'Исполнителей: {len_worker}\n'
            f'Заблокировано: {len_banned_users}\n'
            f'Размещено объявлений: {len_advertisement}\n'
            f'Заблокировано объявлений: {len_banned_advertisement}\n'
            f'Удалено объявлений: {admin.deleted_abs}\n'
            f'Выполнено объявлений: {admin.done_abs}')

    await state.set_state(AdminStates.menu)
    await message.answer(text=text, reply_markup=kbc.menu_admin_keyboard())


@router.callback_query(F.data == 'apply_and_continue',
                       StateFilter(UserStates.registration_end, UserStates.registration_enter_city))
async def apply_user_agreement(callback: CallbackQuery) -> None:
    logger.debug(f'apply_user_agreement...')
    kbc = KeyboardCollection()
    await callback.message.delete()
    await callback.message.answer(text='Выберите вашу роль', reply_markup=kbc.registration())


@router.message(Command("menu"))
async def menu_cmd(message: Message, state: FSMContext) -> None:
    logger.debug(f'menu_cmd...')
    print(state)
    print("sssssssssaaaaaaaaasssssss")

    if message.chat.id < 0:
        await message.answer('Пользоваться ботом можно только из ЛС')
        return

    msg = await message.answer(f'Удаляю клавиатуры',
                               reply_markup=ReplyKeyboardRemove())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    await state.clear()
    kbc = KeyboardCollection()
    logger.debug(f"user_name: {message.from_user.username}")
    if user_baned := await Banned.get_banned(tg_id=message.chat.id):
        if user_baned.ban_now or user_baned.forever:
            await message.answer(text='Упс, вы заблокированы', reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return
    await state.set_state(UserStates.menu)
    if worker := await Worker.get_worker(tg_id=message.chat.id):
        if worker.active:
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)
            work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                               worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None

            if len(worker.city_id) == 1:
                cites = 'Ваш город: '
                step = ''
                city = await City.get_city(id=worker.city_id[0])
                cites += f'{step}{city.city}\n'

            else:
                cites = 'Ваши города: '
                cites_temp = []
                for city_id in worker.city_id:
                    city = await City.get_city(id=city_id)
                    cites_temp.append(city.city)
                cites += ', '.join(cites_temp)

            end = '\n' if subscription.count_cites == 1 else ""

            text = (f'Ваш профиль\n\n'
                    f'ID: {worker.id} {worker.profile_name} {"✅" if worker.confirmed else "☑️"}\n'
                    f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.stars else 0} ⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
                    f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                    f'{cites + end if subscription.count_cites == 1 else ""}'
                    f'Выполненных заказов: {worker.order_count}\n'
                    f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                    f'Ваш тариф: {subscription.subscription_type}\n'
                    f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'
                    f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                    f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'
                    f'Зарегистрирован с {worker.registration_data}\n'
                    f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'
                    f'{cites + end if subscription.count_cites != 1 else ""}')

            choose_works = True if worker_sub.unlimited_work_types else False
            profile_name = True if worker.profile_name else False

            if worker.profile_photo:
                await message.answer_photo(
                    photo=FSInputFile(worker.profile_photo),
                    caption=text,
                    reply_markup=kbc.menu_worker_keyboard(
                        confirmed=worker.confirmed,
                        choose_works=choose_works,
                        individual_entrepreneur=worker.individual_entrepreneur,
                        create_photo=False,
                        create_name=profile_name
                    )
                )
            else:
                await message.answer(
                    text=text,
                    reply_markup=kbc.menu_worker_keyboard(
                        confirmed=worker.confirmed,
                        choose_works=choose_works,
                        individual_entrepreneur=worker.individual_entrepreneur,
                        create_photo=True,
                        create_name=profile_name
                    )
                )
            await state.set_state(WorkStates.worker_menu)
        else:
            customer = await Customer.get_customer(tg_id=message.chat.id)
            if customer is None:
                await state.set_state(UserStates.menu)
                await message.answer(
                    text=f'Меню\n\nВыберите интересующий вас пункт',
                    reply_markup=kbc.command_menu_keyboard(),
                )
                return
            logger.debug(f'customer_menu...')

            kbc = KeyboardCollection()

            user_abs = await Abs.get_all_by_customer(customer.id)
            city = await City.get_city(id=int(customer.city_id))

            text = ('Ваш профиль\n\n'
                    f'ID: {customer.id}\n'
                    f'Ваш город: {city.city}\n'
                    f'Открыто объявлений: {len(user_abs) if user_abs else 0}')

            await state.set_state(CustomerStates.customer_menu)
            await message.answer(text=text,
                                 reply_markup=kbc.menu_customer_keyboard())
            return
    elif customer := await Customer.get_customer(tg_id=message.chat.id):
        logger.debug(f'customer_menu...')

        kbc = KeyboardCollection()

        user_abs = await Abs.get_all_by_customer(customer.id)
        city = await City.get_city(id=int(customer.city_id))

        text = ('Ваш профиль\n\n'
                f'ID: {customer.id}\n'
                f'Ваш город: {city.city}\n'
                f'Открыто объявлений: {len(user_abs) if user_abs else 0}')

        await state.set_state(CustomerStates.customer_menu)
        await message.answer(
            text=text,
            reply_markup=kbc.menu_customer_keyboard()
        )
        return
    else:
        text = ('Размещаются запросы только на услуги:\n'
                ' — анонимно;\n'
                ' — без ссылок;\n'
                ' — номера телефона;\n\n'
                'После успешной публикации, заказчику поступают в личку отклики от исполнителей с рейтингом и количеством выполненных заказов. \n\n'
                'Заказчику остается только выбрать подходящего и связаться лично. \n\n'
                'После завершения работы - заказчик закрывает заказ и оставляет отзыв. \n\n'
                'Исполнителям поступают запросы в личку по направлениям, которые они выбрали и совершают отклики.\n\n'
                '<b>Запросы на услуги размещаются бесплатно без ограничений.</b>\n\n'
                '<b>За попытку предложений не по теме предусмотрена блокировка.</b>')
        await message.answer_video(
            video=FSInputFile('app/data/database/WhatsApp.jpg'),
            caption=text,
            reply_markup=kbc.apply_user_agreement(),
            parse_mode='HTML'
        )
        await state.set_state(UserStates.registration_enter_city)
        await state.update_data(username=str(message.from_user.username))
        return


@router.callback_query(F.data == 'menu', StateFilter(UserStates.menu, UserStates.user_info))
async def menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'menu_cmd...')
    print("ssssxxxccvvvvv")

    await state.clear()
    kbc = KeyboardCollection()
    if user_baned := await Banned.get_banned(tg_id=callback.message.chat.id):
        if user_baned.ban_now or user_baned.forever:
            await callback.message.edit_text(text='Упс, вы заблокированы', reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return
    if await Worker.get_worker(tg_id=callback.message.chat.id) or Customer.get_customer(
            tg_id=callback.message.chat.id) or await Admin.get_by_tg_id(tg_id=callback.message.chat.id):
        await state.set_state(UserStates.menu)
        await callback.message.edit_text(
            text=f'Меню\n\nВыберите интересующий вас пункт',
            reply_markup=kbc.command_menu_keyboard(),
        )
        return


@router.callback_query(F.data == 'role', StateFilter(UserStates.menu))
async def user_change_role(callback: CallbackQuery) -> None:
    logger.debug(f'user_change_role...')
    kbc = KeyboardCollection()
    if await Admin.get_by_tg_id(tg_id=callback.message.chat.id):
        admin_btn = True
    else:
        admin_btn = False
    await callback.message.edit_text(text='Выберите роль', reply_markup=kbc.menu_keyboard(admin=admin_btn))


@router.message(Command("role"))
async def user_change_role(message: Message, state: FSMContext) -> None:
    logger.debug(f'user_change_role...')
    kbc = KeyboardCollection()

    if message.chat.id < 0:
        await message.answer('Пользоваться ботом можно только из ЛС')
        return

    if user_baned := await Banned.get_banned(tg_id=message.chat.id):
        if user_baned.ban_now or user_baned.forever:
            await message.answer(text='Упс, вы заблокированы', reply_markup=kbc.support_btn())
            await state.set_state(BannedStates.banned)
            return
    if await Worker.get_worker(tg_id=message.chat.id) or await Customer.get_customer(
            tg_id=message.chat.id) or await Admin.get_by_tg_id(tg_id=message.chat.id):
        msg = await message.answer(f'Удаляю клавиатуры',
                                   reply_markup=ReplyKeyboardRemove())
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

        await state.set_state(UserStates.menu)
        if await Admin.get_by_tg_id(tg_id=message.chat.id):
            admin_btn = True
        else:
            admin_btn = False
        await message.answer(text='Выберите роль', reply_markup=kbc.menu_keyboard(admin=admin_btn))
    else:
        await message.answer(
            text=f'Вы еще не зарегистрированы, вызовите команду /start'
        )
        await state.set_state(UserStates.registration_enter_city)
        await state.update_data(username=str(message.from_user.username))
        return


@router.callback_query(F.data == 'info', StateFilter(UserStates.menu))
async def user_look_info(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'user_look_info...')
    kbc = KeyboardCollection()
    await state.set_state(UserStates.user_info)

    info_messages = await InfoHaltura.get_all()

    info_now = info_messages[0]

    if len(info_messages) > 1:
        btn_next = True
    else:
        btn_next = False

    if 'txt' in info_now.text_path:
        await callback.message.delete()
        text = help_defs.read_text_file(info_now.text_path)
        await callback.message.answer(text=text, parse_mode='HTML',
                                      reply_markup=kbc.choose_obj_with_out_list(id_now=0,
                                                                                btn_next=btn_next,
                                                                                btn_back=False,
                                                                                abs_id=info_now.id))
    else:
        text = ('✅ <b>Размещаются запросы только на разовые услуги:</b>\n'
                '\n- Анонимно;\n'
                '- Без ссылок;\n'
                '- Номера телефона;\n'
                '\nПосле успешной публикации, заказчику в личку поступают отклики от исполнителей - остается только выбрать подходящего.\n'
                '\n🚫 <b>Запрещается предлагать:</b>\n\n'
                '- Рекламу;\n'
                '- Вакансии;\n'
                '- Работу вахтой;\n'
                '- Бригаду на объемы;\n\n'
                'И другие запросы, которые не связанные с тематикой сервиса — предусмотрена блокировка профиля.')
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=FSInputFile('app/data/database/Haltura_info.jpg'),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(id_now=0,
                                                      btn_next=btn_next,
                                                      btn_back=False,
                                                      abs_id=info_now.id),
            parse_mode='HTML'
        )


@router.message(Command("info"))
async def user_look_info(message: Message, state: FSMContext) -> None:
    logger.debug(f'user_look_info...')

    if message.chat.id < 0:
        await message.answer('Пользоваться ботом можно только из ЛС')
        return

    msg = await message.answer(f'Удаляю клавиатуры',
                               reply_markup=ReplyKeyboardRemove())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    kbc = KeyboardCollection()
    await state.set_state(UserStates.user_info)

    info_messages = await InfoHaltura.get_all()

    info_now = info_messages[0]

    if len(info_messages) > 1:
        btn_next = True
    else:
        btn_next = False

    if 'txt' in info_now.text_path:
        text = help_defs.read_text_file(info_now.text_path)
        await message.answer(text=text, parse_mode='HTML',
                             reply_markup=kbc.choose_obj_with_out_list(id_now=0,
                                                                       btn_next=btn_next,
                                                                       btn_back=False,
                                                                       abs_id=info_now.id))
    else:
        text = ('✅ <b>Размещаются запросы только на разовые услуги:</b>\n'
                '\n- Анонимно;\n'
                '- Без ссылок;\n'
                '- Номера телефона;\n'
                '\nПосле успешной публикации, заказчику в личку поступают отклики от исполнителей - остается только выбрать подходящего.\n'
                '\n🚫 <b>Запрещается предлагать:</b>\n\n'
                '- Рекламу;\n'
                '- Вакансии;\n'
                '- Работу вахтой;\n'
                '- Бригаду на объемы;\n\n'
                'И другие запросы, которые не связанные с тематикой сервиса — предусмотрена блокировка профиля.')
        await message.answer_photo(
            photo=FSInputFile('app/data/database/Haltura_info.jpg'),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(id_now=0,
                                                      btn_next=btn_next,
                                                      btn_back=False,
                                                      abs_id=info_now.id),
            parse_mode='HTML'
        )


@router.callback_query(lambda c: c.data.startswith('go_'), UserStates.user_info)
async def check_abs(callback: CallbackQuery) -> None:
    logger.debug(f'user_info...')
    kbc = KeyboardCollection()
    info_list_id = int(callback.data.split('_')[1])

    info_messages = await InfoHaltura.get_all()

    info_now = info_messages[info_list_id]

    if len(info_messages) - 1 > info_list_id:
        btn_next = True
    else:
        btn_next = False

    if info_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    if 'txt' in info_now.text_path:
        await callback.message.delete()
        text = help_defs.read_text_file(info_now.text_path)
        await callback.message.answer(text=text, parse_mode='HTML',
                                      reply_markup=kbc.choose_obj_with_out_list(id_now=info_list_id,
                                                                                btn_next=btn_next,
                                                                                btn_back=btn_back,
                                                                                abs_id=info_now.id))
    else:
        text = ('✅ <b>Размещаются запросы только на разовые услуги:</b>\n'
                '\n- Анонимно;\n'
                '- Без ссылок;\n'
                '- Номера телефона;\n'
                '\nПосле успешной публикации, заказчику в личку поступают отклики от исполнителей - остается только выбрать подходящего.\n'
                '\n🚫 <b>Запрещается предлагать:</b>\n\n'
                '- Рекламу;\n'
                '- Вакансии;\n'
                '- Работу вахтой;\n'
                '- Бригаду на объемы;\n\n'
                'И другие запросы, которые не связанные с тематикой сервиса — предусмотрена блокировка профиля.')
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=FSInputFile('app/data/database/Haltura_info.jpg'),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list(id_now=info_list_id,
                                                      btn_next=btn_next,
                                                      btn_back=btn_back,
                                                      abs_id=info_now.id),
            parse_mode='HTML'
        )


@router.callback_query(F.data == 'support', StateFilter(UserStates.menu, BannedStates.banned))
async def user_ask_support(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'user_ask_support...')

    kbc = KeyboardCollection()

    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=callback.message.chat.id):
        if user_and_support_queue.turn:
            await callback.message.edit_text('Ваш вопрос принят, ожидайте пожалуйста ответа.',
                                             reply_markup=kbc.menu_btn())
            return

    await state.set_state(UserStates.ask_support)
    msg = await callback.message.edit_text('Напишите ваш вопрос')
    await state.update_data(msg_id=msg.message_id)
    return


@router.callback_query(F.data == 'support')
async def user_ask_support(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'user_ask_support...')

    kbc = KeyboardCollection()

    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=callback.message.chat.id):
        if user_and_support_queue.turn:
            await callback.message.edit_text('Ваш вопрос принят, ожидайте пожалуйста ответа.',
                                             reply_markup=kbc.menu_btn())
            return

    await state.set_state(UserStates.ask_support)
    msg = await callback.message.edit_text('Напишите ваш вопрос')
    await state.update_data(msg_id=msg.message_id)
    return


@router.message(Command("support"))
async def user_ask_support(message: Message, state: FSMContext) -> None:
    logger.debug(f'user_ask_support...')

    if message.chat.id < 0:
        await message.answer('Пользоваться ботом можно только из ЛС')
        return

    msg = await message.answer(f'Удаляю клавиатуры',
                               reply_markup=ReplyKeyboardRemove())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    kbc = KeyboardCollection()

    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=message.chat.id):
        if user_and_support_queue.turn:
            await message.answer('Ваш вопрос принят, ожидайте пожалуйста ответа.', reply_markup=kbc.menu_btn())
            return

    await state.set_state(UserStates.ask_support)
    msg = await message.answer('Напишите ваш вопрос')
    await state.update_data(msg_id=msg.message_id)
    return


@router.message(F.text, StateFilter(UserStates.ask_support))
async def user_ask_support_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'user_ask_support_text...')

    kbc = KeyboardCollection()
    msg_to_send = message.text

    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id'))

    if worker := await Worker.get_worker(tg_id=message.chat.id):
        if worker.active:

            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)

            if len(worker.city_id) == 1:
                cites = 'Ваш город: '
                step = ''
            else:
                cites = 'Ваши города:\n'
                step = '    '
            for city_id in worker.city_id:
                city = await City.get_city(id=city_id)
                cites += f'{step}{city.city}\n'

            end = '\n' if subscription.count_cites == 1 else ""

            text = (
                f'Сообщение от исполнителя #{message.chat.id}\n\n'
                f'Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.stars else 0} ⭐️\n'
                f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                f'{cites + end if subscription.count_cites == 1 else ""}'
                f'Выполненных заказов: {worker.order_count}\n'
                f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                f'Тариф: {subscription.subscription_type}\n'
                f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'
            )
        else:
            if customer := await Customer.get_customer(tg_id=message.chat.id):
                city = await City.get_city(id=int(customer.city_id))
                user_abs = await Abs.get_all_by_customer(customer.id)
                text = (
                    f'Сообщение от заказчика #{message.chat.id}\n\n'
                    f'Ваш город: {city.city}\n'
                    f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
                )
            else:
                text = f'Сообщение от пользователя #{message.chat.id}\n\n'
    elif customer := await Customer.get_customer(tg_id=message.chat.id):
        city = await City.get_city(id=int(customer.city_id))
        user_abs = await Abs.get_all_by_customer(customer.id)
        text = (
            f'Сообщение от заказчика #{message.chat.id}\n\n'
            f'Город: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
        )
    else:
        text = f'Сообщение от пользователя #{message.chat.id}\n\n'

    await state.set_state(UserStates.ask_support_photo)
    await state.update_data(text=text, ask=msg_to_send)

    msg = await message.answer('Прикрепите фото или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.from_user.id, message_id=msg_id)


@router.callback_query(F.data == 'skip_it', UserStates.ask_support_photo)
async def skip_send_photo(callback: CallbackQuery, state: FSMContext):
    logger.debug(f'support_no_photo...')

    kbc = KeyboardCollection()
    state_data = await state.get_data()
    text = str(state_data.get('text'))
    ask = str(state_data.get('ask'))

    ask_answers = await AskAnswer.get_all()

    for ask_answer in ask_answers:
        if await checks.levenshtein_distance_check_faq(phrase=ask, words=ask_answer.questions):
            answer = f'Ответ от поддержки: "{ask_answer.answer}"'
            await callback.message.answer(text=answer, reply_markup=kbc.support_btn())
            await callback.message.edit_text('Ваш вопрос отправлен', reply_markup=kbc.menu_btn())
            await state.set_state(UserStates.menu)
            if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(
                    user_tg_id=callback.message.chat.id):
                user_and_support_queue.user_messages.append(ask)
                user_and_support_queue.admin_messages.append(ask_answer.answer)
                await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages,
                                                    admin_messages=user_and_support_queue.admin_messages, turn=False)
            else:
                new_ask = UserAndSupportQueue(id=None, user_tg_id=callback.message.chat.id, user_messages=ask)
                await new_ask.save()
                user_and_support_queue = await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=callback.message.chat.id)
                user_and_support_queue.admin_messages.append(ask_answer.answer)
                await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages,
                                                    admin_messages=user_and_support_queue.admin_messages, turn=False)
            return

    await state.set_state(UserStates.menu)
    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=callback.message.chat.id):
        user_and_support_queue.user_messages.append(ask)
        await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages, turn=True)
    else:
        new_ask = UserAndSupportQueue(id=None, user_tg_id=callback.message.chat.id, user_messages=ask)
        await new_ask.save()
        user_and_support_queue = await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=callback.message.chat.id)

    count_messages = max([len(user_and_support_queue.user_messages), len(user_and_support_queue.admin_messages)])

    for i in range(count_messages):
        if i < len(user_and_support_queue.user_messages):
            text += f' - Исполнитель: "{user_and_support_queue.user_messages[i]}"\n'

        if i < len(user_and_support_queue.admin_messages):
            text += f' - Вы: "{user_and_support_queue.admin_messages[i]}"\n'
    if banned := await Banned.get_banned(tg_id=callback.message.chat.id):
        if banned.ban_now:
            text += f'\n\nЭтот пользователь заблокирован\nПричина блокировки: {banned.ban_reason}'
    await bot.send_message(chat_id=config.SUPPORT_CHAT, text=text,
                           reply_markup=kbc.admin_answer_user(tg_id=callback.message.chat.id), protect_content=False)
    await callback.message.edit_text('Ваш вопрос отправлен', reply_markup=kbc.menu_btn())


@router.message(F.photo, UserStates.ask_support_photo)
async def create_abs_with_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'create_abs_with_photo...')

    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()

    text = str(state_data.get('text'))
    msg = int(state_data.get('msg_id'))
    ask = str(state_data.get('ask'))

    ask_answers = await AskAnswer.get_all()

    for ask_answer in ask_answers:
        if await checks.levenshtein_distance_check_faq(phrase=ask, words=ask_answer.questions):
            answer = f'Ответ от поддержки: "{ask_answer.answer}"'
            await bot.delete_message(chat_id=message.from_user.id, message_id=msg, )
            await message.answer('Ваш вопрос отправлен', reply_markup=kbc.menu_btn())
            await message.answer(text=answer, reply_markup=kbc.support_btn())
            await state.set_state(UserStates.menu)
            if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=message.chat.id):
                user_and_support_queue.user_messages.append(ask)
                user_and_support_queue.admin_messages.append(ask_answer.answer)
                await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages,
                                                    admin_messages=user_and_support_queue.admin_messages, turn=False)
            else:
                new_ask = UserAndSupportQueue(id=None, user_tg_id=message.chat.id, user_messages=ask)
                await new_ask.save()
                user_and_support_queue = await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=message.chat.id)
                user_and_support_queue.admin_messages.append(ask_answer.answer)
                await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages,
                                                    admin_messages=user_and_support_queue.admin_messages, turn=False)
            return

    await bot.delete_message(chat_id=message.from_user.id, message_id=msg, )

    await state.set_state(UserStates.menu)
    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=message.chat.id):
        user_and_support_queue.user_messages.append(ask)
        await user_and_support_queue.update(user_messages=user_and_support_queue.user_messages, turn=True)
    else:
        new_ask = UserAndSupportQueue(id=None, user_tg_id=message.chat.id, user_messages=ask)
        await new_ask.save()
        user_and_support_queue = await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=message.chat.id)

    count_messages = max([len(user_and_support_queue.user_messages), len(user_and_support_queue.admin_messages)])

    for i in range(count_messages):
        if i < len(user_and_support_queue.user_messages):
            text += f' - Исполнитель: "{user_and_support_queue.user_messages[i]}"\n'

        if i < len(user_and_support_queue.admin_messages):
            text += f' - Вы: "{user_and_support_queue.admin_messages[i]}"\n'

    if banned := await Banned.get_banned(tg_id=message.chat.id):
        if banned.ban_now:
            text += f'\n\nЭтот пользователь заблокирован\nПричина блокировки: {banned.ban_reason}'
    await bot.send_photo(chat_id=config.SUPPORT_CHAT, photo=photo, caption=text,
                         reply_markup=kbc.admin_answer_user(tg_id=message.chat.id), protect_content=False)
    await message.answer('Ваш вопрос отправлен', reply_markup=kbc.menu_btn())

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
