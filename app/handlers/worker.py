import datetime
from datetime import timedelta, datetime
import logging
from functools import lru_cache
from typing import List, Optional

def get_activity_info_fallback(worker):
    """Fallback функция для получения информации об активности исполнителя"""
    activity_level = getattr(worker, 'activity_level', 100)
    
    # Определяем зону
    if activity_level >= 74:
        zone_emoji = "🟢"
        zone_message = "Все в порядке, доступ полный"
        can_respond = True
        limit = -1
    elif activity_level >= 48:
        zone_emoji = "🟡"
        zone_message = "Ваша активность снижается, ограничения: можно откликнуться только на 3 заказа в день"
        can_respond = True  # Будет проверяться по responses_today
        limit = 3
    elif activity_level >= 9:
        zone_emoji = "🟠"
        zone_message = "Ограничения: можно откликнуться только на 1 заказ в день"
        can_respond = True  # Будет проверяться по responses_today
        limit = 1
    else:
        zone_emoji = "🔴"
        zone_message = "Блокировка откликов: Ваш уровень активности слишком низкий. Чтобы продолжить работу, восстановите активность!"
        can_respond = False
        limit = 0
    
    return zone_emoji, zone_message, can_respond, limit

async def update_worker_activity_fallback(worker, new_activity):
    """Fallback функция для обновления активности исполнителя"""
    if hasattr(worker, 'update_activity_level'):
        await worker.update_activity_level(new_activity)
    else:
        # Fallback: обновляем напрямую через SQL
        import aiosqlite
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'UPDATE workers SET activity_level = ? WHERE id = ?',
                (new_activity, worker.id)
            )
            await conn.commit()
            await cursor.close()
            worker.activity_level = new_activity
        finally:
            await conn.close()

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge
from aiogram.types import (
    CallbackQuery, Message, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery, FSInputFile, InputMediaPhoto,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

import config
import aiosqlite
from app.data.database.models import (
    Customer, Worker, City, SubscriptionType, WorkerAndSubscription, WorkType, Banned, Abs, WorkersAndAbs, Admin,
    WorkerAndRefsAssociation, WorkerAndReport, WorkerAndBadResponse, WorkerCitySubscription
)
from app.keyboards import KeyboardCollection
from app.states import WorkStates, UserStates, BannedStates
from app.untils import help_defs, checks, yandex_ocr
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()

# Кэш для оптимизации запросов к БД
_work_types_cache = None
_cache_timestamp = None
CACHE_DURATION = 300  # 5 минут


async def check_worker_has_unlimited_contacts(worker_id: int) -> bool:
    """
    Проверяет, есть ли у исполнителя активный доступ к контактам (безлимитный или ограниченный).
    
    Args:
        worker_id: ID исполнителя
        
    Returns:
        bool: True если есть доступ к контактам, False в противном случае
    """
    try:
        # Получаем данные исполнителя
        from app.data.database.models import Worker
        worker = await Worker.get_worker(id=worker_id)
        
        if not worker:
            return False
        
        # Проверяем безлимитный доступ
        if worker.unlimited_contacts_until:
            from datetime import datetime, timedelta
            try:
                end_date = datetime.strptime(worker.unlimited_contacts_until, "%Y-%m-%d")
                if end_date > datetime.now():
                    return True  # Безлимитный доступ активен
            except ValueError:
                pass  # Неверный формат даты
        
        # Проверяем ограниченные контакты
        if worker.purchased_contacts > 0:
            return True  # Есть купленные контакты
        
        return False
    except Exception as e:
        logger.error(f"Error checking unlimited contacts for worker {worker_id}: {e}")
        return False


async def get_cached_work_types() -> List[WorkType]:
    """Получить кэшированный список типов работ"""
    global _work_types_cache, _cache_timestamp

    current_time = datetime.now().timestamp()

    # Проверяем, нужно ли обновить кэш
    if (_work_types_cache is None or
            _cache_timestamp is None or
            current_time - _cache_timestamp > CACHE_DURATION):
        _work_types_cache = await WorkType.get_all()
        _cache_timestamp = current_time
        logger.debug(f"Work types cache updated: {len(_work_types_cache)} items")

    return _work_types_cache


def clear_work_types_cache():
    """Очистить кэш типов работ"""
    global _work_types_cache, _cache_timestamp
    _work_types_cache = None
    _cache_timestamp = None
    logger.debug("Work types cache cleared")


@router.callback_query(F.data == "registration_worker", WorkStates.worker_choose_work_types)
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
                        registration_data=registration_date,
                        confirmed=True)  # Убираем верификацию - сразу подтверждаем
    await new_worker.save()
    new_worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    new_worker_and_subscription = WorkerAndSubscription(worker_id=new_worker.id)
    await new_worker_and_subscription.save()
    await callback.message.edit_text('Вы успешно зарегистрированы!')
    await callback.message.answer(text='Добро пожаловать! Выберите направления работ.',
                                  reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_choose_work_types)


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
    await callback.message.answer(text='Добро пожаловать! Выберите направления работ.',
                                  reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_choose_work_types)


# Верификация убрана согласно ТЗ


@router.callback_query(F.data == "worker_menu")
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
            await state.set_state(WorkStates.worker_choose_work_types)
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
            f'ID: {user_worker.id} {user_worker.profile_name}\n'
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
                confirmed=True,  # Верификация убрана
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
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=True,
                create_name=profile_name
            )
        )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "menu", StateFilter(WorkStates.worker_menu, WorkStates.worker_check_abs,
                                                     WorkStates.worker_check_subscription,
                                                     WorkStates.worker_change_city,
                                                     WorkStates.worker_choose_city,
                                                     WorkStates.worker_change_main_city,
                                                     WorkStates.create_portfolio, WorkStates.create_name_profile,
                                                     WorkStates.create_photo_profile,
                                                     WorkStates.portfolio_upload_photo,
                                                     WorkStates.worker_choose_work_types))
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
            f'ID: {user_worker.id} {user_worker.profile_name}\n'
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
                confirmed=True,  # Верификация убрана
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
                confirmed=True,  # Верификация убрана
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

    # Удаляем фото из словаря и получаем путь к файлу для удаления
    new_portfolio, removed_file_path = help_defs.reorder_dict(d=worker.portfolio_photo, removed_key=str(photo_id))
    
    # Удаляем физический файл с диска
    if removed_file_path:
        file_deleted = help_defs.delete_file(removed_file_path)
        if file_deleted:
            logger.info(f"Фото портфолио удалено: {removed_file_path}")
        else:
            logger.warning(f"Не удалось удалить файл портфолио: {removed_file_path}")

    # Обновляем портфолио в базе данных
    await worker.update_portfolio_photo(new_portfolio)
    photo_len = len(new_portfolio)

    if photo_len == 0:
        await callback.message.answer(
            text='У вас пока нет фото в портфолио',
            reply_markup=kbc.my_portfolio()
        )
        return

    # Корректируем photo_id для отображения
    if photo_id <= -1:
        photo_id = photo_len - 1
    elif photo_id > (photo_len - 1):
        photo_id = 0

    # Обновляем интерфейс
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(new_portfolio[str(photo_id)])),
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
            await message.answer(
                text='Упс, похоже вы пытались прикрепить не соответствующее фото, повторите попытку снова 😌',
                reply_markup=kbc.photo_work_keyboard(is_photo=is_photo))
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
                         caption=f'ID #{message.chat.id}\nЗагружено новое фото профиля',
                         photo=FSInputFile(file_path_photo),
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
    
    # Получаем все города исполнителя (основной + дополнительные из подписок)
    all_city_ids = list(worker.city_id)  # Основной город
    
    # Добавляем дополнительные города из активных подписок
    from app.data.database.models import WorkerCitySubscription
    city_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in city_subscriptions:
        all_city_ids.extend(subscription.city_ids)
    
    # Убираем дубликаты
    all_city_ids = list(set(all_city_ids))
    
    advertisements = []
    for city_id in all_city_ids:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:
            advertisements += advertisements_temp
    
    # Сортируем по дате создания (самые свежие первыми)
    advertisements.sort(key=lambda x: x.date_to_delite, reverse=True)

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
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids and not worker_sub.unlimited_work_types:
            continue
            
        is_unlimited = (worker_sub.unlimited_work_types or 
                       (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
        
        if is_unlimited or (worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids):
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

    abs_now: Abs = advertisements_final[0]
    await abs_now.update(views=1)
    if len(advertisements_final) > 1:
        btn_next = True
    else:
        btn_next = False

    btn_back = False  # В первом объявлении кнопка "Назад" не нужна

    # Проверка на уже откликнутые объявления убрана - теперь используется новая система откликов

    text = help_defs.read_text_file(abs_now.text_path)


    text = f'Объявление {abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text,
                                          reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=0))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']), caption=text,
                                            reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=0))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text, reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=0))


@router.callback_query(lambda c: c.data.startswith('go_worker_'), WorkStates.worker_check_abs)
async def check_abs_navigation(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик навигации между объявлениями для исполнителей"""
    logger.debug(f'check_abs_navigation...')
    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[2])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    
    # Получаем все города исполнителя (основной + дополнительные из подписок)
    all_city_ids = list(worker.city_id)  # Основной город
    
    # Добавляем дополнительные города из активных подписок
    from app.data.database.models import WorkerCitySubscription
    city_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in city_subscriptions:
        all_city_ids.extend(subscription.city_ids)
    
    # Убираем дубликаты
    all_city_ids = list(set(all_city_ids))
    
    advertisements = []
    for city_id in all_city_ids:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:  # Проверяем, что не None
            advertisements += advertisements_temp
    
    # Сортируем по дате создания (самые свежие первыми)
    advertisements.sort(key=lambda x: x.date_to_delite, reverse=True)

    advertisements_final = []

    if not advertisements:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids and not worker_sub.unlimited_work_types:
            continue
            
        is_unlimited = (worker_sub.unlimited_work_types or 
                       (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
        
        if is_unlimited or (worker_sub.work_type_ids and advertisement.work_type_id in worker_sub.work_type_ids):
            advertisements_final.append(advertisement)

    if not advertisements_final or abs_list_id >= len(advertisements_final):
        await callback.message.edit_text(text='Объявление не найдено', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    advertisement_now = advertisements_final[abs_list_id]

    btn_next = True if (len(advertisements_final) - 1 > abs_list_id) else False
    btn_back = True if abs_list_id > 0 else False

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_now.id):
        btn_apply = False
        report_btn = False
    else:
        btn_apply = True
        report_btn = True

    await advertisement_now.update(views=1)

    text = help_defs.read_text_file(advertisement_now.text_path)
    text = f'Объявление {advertisement_now.id}\n\n' + text

    # Проверяем, есть ли фото в объявлении и в текущем сообщении
    has_photo_in_ad = advertisement_now.photo_path is not None
    has_photo_in_msg = callback.message.photo is not None
    
    # Если нужно перейти от фото к тексту или наоборот - удаляем и создаем новое
    if has_photo_in_ad != has_photo_in_msg:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        
        if has_photo_in_ad:
            if 'https' in advertisement_now.photo_path['0']:
                await callback.message.answer_photo(
                    photo=advertisement_now.photo_path['0'],
                    caption=text,
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
                )
            else:
                await callback.message.answer_photo(
                    photo=FSInputFile(advertisement_now.photo_path['0']),
                    caption=text,
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
                )
        else:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
            )
        return
    
    # Если тип контента одинаковый - редактируем
    if has_photo_in_ad and has_photo_in_msg:
        # Фото к фото
        if 'https' in advertisement_now.photo_path['0']:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=advertisement_now.photo_path['0'],
                    caption=text),
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
            )
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(advertisement_now.photo_path['0']),
                    caption=text),
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
            )
    else:
        # Текст к тексту
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id)
        )


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    
    # Получаем все города исполнителя (основной + дополнительные из подписок)
    all_city_ids = list(worker.city_id)  # Основной город
    
    # Добавляем дополнительные города из активных подписок
    from app.data.database.models import WorkerCitySubscription
    city_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in city_subscriptions:
        all_city_ids.extend(subscription.city_ids)
    
    # Убираем дубликаты
    all_city_ids = list(set(all_city_ids))
    
    advertisements = []
    for city_id in all_city_ids:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:  # Проверяем, что не None
            advertisements += advertisements_temp
    
    # Сортируем по дате создания (самые свежие первыми)
    advertisements.sort(key=lambda x: x.date_to_delite, reverse=True)

    advertisements_final = []

    if not advertisements:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids and not worker_sub.unlimited_work_types:
            continue
            
        is_unlimited = (worker_sub.unlimited_work_types or 
                       (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
        
        if is_unlimited or (worker_sub.work_type_ids and advertisement.work_type_id in worker_sub.work_type_ids):
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

    # Проверка на уже откликнутые объявления убрана - теперь используется новая система откликов

    text = help_defs.read_text_file(abs_now.text_path)


    text = f'Объявление {abs_now.id}\n\n' + text

    await abs_now.update(views=1)

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer_photo(photo=abs_now.photo_path['0'],
                                               caption=text,
                                               reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id))
            return

        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']),
                                            caption=text,
                                            reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text, reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next, btn_back=btn_back, abs_list_id=abs_list_id))


@router.callback_query(lambda c: c.data.startswith('go-to-next_'), WorkStates.worker_check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    
    # Получаем все города исполнителя (основной + дополнительные из подписок)
    all_city_ids = list(worker.city_id)  # Основной город
    
    # Добавляем дополнительные города из активных подписок
    from app.data.database.models import WorkerCitySubscription
    city_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in city_subscriptions:
        all_city_ids.extend(subscription.city_ids)
    
    # Убираем дубликаты
    all_city_ids = list(set(all_city_ids))
    
    advertisements = []
    for city_id in all_city_ids:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:  # Проверяем, что не None
            advertisements += advertisements_temp
    
    # Сортируем по дате создания (самые свежие первыми)
    advertisements.sort(key=lambda x: x.date_to_delite, reverse=True)

    advertisements_final = []

    if not advertisements:
        await callback.message.edit_text(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids and not worker_sub.unlimited_work_types:
            continue
            
        is_unlimited = (worker_sub.unlimited_work_types or 
                       (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
        
        if is_unlimited or (worker_sub.work_type_ids and advertisement.work_type_id in worker_sub.work_type_ids):
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
        photo_path = advertisement_now.photo_path[str(photo_id)]
        
        if 'https' in photo_path:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=photo_path,
                    caption=callback.message.caption),
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id)
            )
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=callback.message.caption),
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id)
            )
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


async def get_worker_selected_work_types(worker_sub) -> List[WorkType]:
    """Получить список выбранных направлений работы исполнителя"""
    if worker_sub.work_type_ids:
        selected_ids = [int(id) for id in worker_sub.work_type_ids if id]
        work_types = await get_cached_work_types()
        return [wt for wt in work_types if wt.id in selected_ids]
    return []


async def get_worker_selected_ids(worker_sub) -> list:
    """Получить список ID выбранных направлений"""
    if worker_sub.work_type_ids:
        return [id for id in worker_sub.work_type_ids if id]
    return []


@router.callback_query(F.data == 'choose_work_types', WorkStates.worker_menu)
async def choose_work_types(callback: CallbackQuery, state: FSMContext):
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)

    # Получаем ранг исполнителя
    from app.data.database.models import WorkerRank
    rank = await WorkerRank.get_or_create_rank(worker.id)
    
    # Получаем лимит направлений на основе ранга
    work_types_limit = rank.get_work_types_limit()

    # Используем кэшированные данные
    work_types = await get_cached_work_types()
    selected_ids = await get_worker_selected_ids(worker_sub)

    # Формируем текст с информацией о выборе
    selected_count = len(selected_ids)
    
    # Определяем доступное количество направлений на основе ранга
    if work_types_limit is None:
        # Платина - все направления без ограничений
        available_count = len(work_types)
        limit_text = "без ограничений"
    else:
        available_count = min(work_types_limit, len(work_types))
        limit_text = f"до {work_types_limit}"

    text = f"🎯 Выберите направления работы\n\n"
    text += f"🏆 **Ваш ранг:** {rank.current_rank} {rank.get_rank_name()}\n"
    text += f"📊 Выбрано: {selected_count}/{available_count} {limit_text}\n"

    if selected_count > 0:
        selected_work_types = await get_worker_selected_work_types(worker_sub)
        text += f"✅ Текущие направления:\n"
        for wt in selected_work_types:
            text += f"• {wt.work_type}\n"
        text += f"\n"

    if selected_count < available_count:
        text += f"💡 Можете выбрать еще {available_count - selected_count} направлений"
    elif selected_count == available_count and work_types_limit is not None:
        text += f"🎉 Достигнут лимит вашего ранга! Повысьте ранг для выбора большего количества направлений."
    elif selected_count == available_count:
        text += f"🎉 Выбрано максимальное количество направлений!"

    await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_work_types_improved(
            all_work_types=work_types,
            selected_ids=selected_ids,
            count_work_types=available_count,
            page=0,
            btn_back=True
        ),
        parse_mode='Markdown'
    )

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await state.set_state(WorkStates.worker_choose_work_types)
    await state.update_data(subscription_id=str(subscription.id))
    await state.update_data(count_work_types=str(subscription.count_work_types))
    await state.update_data(work_type_ids='|'.join(selected_ids))
    await state.update_data(current_page=0)


# Новые обработчики для улучшенного интерфейса
@router.callback_query(lambda c: c.data.startswith('add_work_type_'), WorkStates.worker_choose_work_types)
async def add_work_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Добавить направление работы"""
    logger.debug(f'add_work_type...')
    kbc = KeyboardCollection()

    work_type_id = callback.data.split('_')[3]
    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))
    
    # Получаем ранг исполнителя для проверки лимитов
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerRank
    rank = await WorkerRank.get_or_create_rank(worker.id)
    work_types_limit = rank.get_work_types_limit()

    # Добавляем новое направление
    current_ids = work_type_ids.split('|') if work_type_ids else []
    
    # Проверяем лимиты ранга
    if work_types_limit is not None and len(current_ids) >= work_types_limit:
        await callback.answer(
            f"❌ Достигнут лимит вашего ранга! Можно выбрать только {work_types_limit} направлений.", 
            show_alert=True
        )
        return
    
    if work_type_id not in current_ids:
        current_ids.append(work_type_id)

    # Обновляем состояние
    await state.update_data(work_type_ids='|'.join(current_ids))

    # Обновляем интерфейс (сохраняем текущую страницу)
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    await update_work_types_interface(callback, state, kbc, current_page)


@router.callback_query(lambda c: c.data.startswith('remove_work_type_'), WorkStates.worker_choose_work_types)
async def remove_work_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Удалить направление работы"""
    logger.debug(f'remove_work_type...')
    kbc = KeyboardCollection()

    work_type_id = callback.data.split('_')[3]
    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))

    # Удаляем направление
    current_ids = work_type_ids.split('|') if work_type_ids else []
    if work_type_id in current_ids:
        current_ids.remove(work_type_id)

    # Обновляем состояние
    await state.update_data(work_type_ids='|'.join(current_ids))

    # Обновляем интерфейс (сохраняем текущую страницу)
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    await update_work_types_interface(callback, state, kbc, current_page)


@router.callback_query(F.data == 'clear_all', WorkStates.worker_choose_work_types)
async def clear_all_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    """Очистить все выбранные направления"""
    logger.debug(f'clear_all_work_types...')
    kbc = KeyboardCollection()

    # Очищаем все выбранные направления
    await state.update_data(work_type_ids='')

    # Обновляем интерфейс (сохраняем текущую страницу)
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    await update_work_types_interface(callback, state, kbc, current_page)


@router.callback_query(F.data == 'show_selected', WorkStates.worker_choose_work_types)
async def show_selected_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать выбранные направления"""
    logger.debug(f'show_selected_work_types...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))
    count_work_types = int(state_data.get('count_work_types'))

    if not work_type_ids:
        await callback.answer("Вы еще не выбрали ни одного направления", show_alert=True)
        return

    # Получаем выбранные направления
    selected_ids = [int(id) for id in work_type_ids.split('|') if id]
    work_types = await get_cached_work_types()
    selected_work_types = [wt for wt in work_types if wt.id in selected_ids]

    text = f"📋 Ваши выбранные направления:\n\n"
    for i, wt in enumerate(selected_work_types, 1):
            text += f"{i}. {wt.work_type}\n"

    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.show_selected_work_types(selected_work_types, count_work_types)
    )


@router.callback_query(F.data == 'back_to_selection', WorkStates.worker_choose_work_types)
async def back_to_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Вернуться к выбору направлений"""
    logger.debug(f'back_to_selection...')
    kbc = KeyboardCollection()

    # Обновляем интерфейс (сохраняем текущую страницу)
    state_data = await state.get_data()
    current_page = state_data.get('current_page', 0)
    await update_work_types_interface(callback, state, kbc, current_page)


@router.callback_query(F.data == 'limit_reached', WorkStates.worker_choose_work_types)
async def limit_reached(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка попытки выбрать направление при достижении лимита"""
    await callback.answer("Достигнут лимит выбранных направлений. Сначала удалите одно из выбранных.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('page_'), WorkStates.worker_choose_work_types)
async def navigate_page(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка навигации по страницам"""
    logger.debug(f'navigate_page...')
    kbc = KeyboardCollection()

    page = int(callback.data.split('_')[1])
    
    # Сохраняем текущую страницу в состоянии
    await state.update_data(current_page=page)
    
    # Обновляем интерфейс с новой страницей
    await update_work_types_interface(callback, state, kbc, page)




async def update_work_types_interface(callback: CallbackQuery, state: FSMContext, kbc: KeyboardCollection, page: int = 0) -> None:
    """Обновить интерфейс выбора направлений с пагинацией"""
    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))

    # Получаем ранг исполнителя для проверки лимитов
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerRank
    rank = await WorkerRank.get_or_create_rank(worker.id)
    work_types_limit = rank.get_work_types_limit()

    # Получаем данные из кэша
    work_types = await get_cached_work_types()
    selected_ids = work_type_ids.split('|') if work_type_ids else []
    selected_ids = [id for id in selected_ids if id]  # Убираем пустые строки

    # Формируем текст
    selected_count = len(selected_ids)
    
    # Определяем доступное количество направлений на основе ранга
    if work_types_limit is None:
        # Платина - все направления без ограничений
        available_count = len(work_types)
        limit_text = "без ограничений"
    else:
        available_count = min(work_types_limit, len(work_types))
        limit_text = f"до {work_types_limit}"

    text = f"🎯 Выберите направления работы\n\n"
    text += f"🏆 **Ваш ранг:** {rank.current_rank} {rank.get_rank_name()}\n"
    text += f"📊 Выбрано: {selected_count}/{available_count} {limit_text}\n"

    if selected_count > 0:
        selected_work_types = [wt for wt in work_types if str(wt.id) in selected_ids]
        text += f"✅ Текущие направления:\n"
        for wt in selected_work_types:
                text += f"• {wt.work_type}\n"
        text += f"\n"

    if selected_count < available_count:
        text += f"💡 Можете выбрать еще {available_count - selected_count} направлений"
    elif selected_count == available_count and work_types_limit is not None:
        text += f"🎉 Достигнут лимит вашего ранга! Повысьте ранг для выбора большего количества направлений."
    elif selected_count == available_count:
        text += f"🎉 Выбрано максимальное количество направлений!"

    # Обновляем сообщение
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.choose_work_types_improved(
            all_work_types=work_types,
            selected_ids=selected_ids,
            count_work_types=available_count,
            page=page,
            btn_back=True
        ),
        parse_mode='Markdown'
    )


# Старый обработчик (оставляем для совместимости)
@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_choose_work_types)
async def choose_work_types_old(callback: CallbackQuery, state: FSMContext) -> None:
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
        await callback.message.edit_text(
            text='*В этом направлении:* \n\n - Бармен\n - Официант\n - Повар\n - Хостес\n - Уборщица\n - Охрана\n - Курьер\n - Кальянщик',
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
    work_type_ids = str(state_data.get('work_type_ids', ''))

    # Обрабатываем выбранные направления
    work_type_id_list = work_type_ids.split('|') if work_type_ids else []
    work_type_id_list = [id for id in work_type_id_list if id]  # Убираем пустые строки

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    # Сохраняем выбранные направления в БД
    await worker_sub.update(work_type_ids=work_type_id_list)

    logger.debug(f'work_type_id_list...{work_type_id_list}')

    # Формируем сообщение о результате
    selected_count = len(work_type_id_list)
    if selected_count > 0:
        # Получаем названия выбранных направлений из кэша
        work_types = await get_cached_work_types()
        selected_work_types = [wt for wt in work_types if str(wt.id) in work_type_id_list]

        text = f"✅ Направления успешно сохранены!\n\n"
        text += f"📊 Выбрано: {selected_count} направлений\n\n"
        text += f"🎯 Ваши направления:\n"
        for i, wt in enumerate(selected_work_types, 1):
                text += f"{i}. {wt.work_type}\n"
    else:
        text = "⚠️ Вы не выбрали ни одного направления.\nВы можете выбрать их позже в меню."

    await callback.message.edit_text(text, reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_menu)


# Функция откликов удалена - функционал переписывается с нуля


# Функция навигации по фото при отклике удалена


# Функция "Мои отклики" удалена


# Функция просмотра отклика удалена


# Функция apply-it_ полностью удалена


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

    text = f'Заказчик ID {customer.tg_id}\nОбъявление {advertisement.id}\n\n' + help_defs.read_text_file(
        advertisement.text_path)
    if advertisement.photo_path:
        await bot.send_photo(chat_id=config.REPORT_LOG,
                             photo=FSInputFile(advertisement.photo_path),
                             caption=text,
                             reply_markup=kbc.block_abs(advertisement_id), protect_content=False)
    else:
        await bot.send_message(chat_id=config.REPORT_LOG,
                               text=text,
                               reply_markup=kbc.block_abs(advertisement_id), protect_content=False)


# Функция apply-final-it_ полностью удалена


# Функция отклонения отклика hide-obj-worker_ удалена


# Функция ответа исполнителя заказчику удалена


# Функция обработки сообщений от исполнителя удалена




@router.callback_query(F.data == "worker_activity", WorkStates.worker_menu)
async def worker_activity(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать активность исполнителя"""
    logger.debug(f'worker_activity...')
    kbc = KeyboardCollection()
    
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    
    # Проверяем, что у исполнителя есть поле activity_level
    if not hasattr(worker, 'activity_level') or worker.activity_level is None:
        worker.activity_level = 100  # Значение по умолчанию
    
    # Получаем информацию об активности (используем fallback если методы отсутствуют)
    if not hasattr(worker, 'get_activity_zone'):
        zone_emoji, zone_message, _, _ = get_activity_info_fallback(worker)
    else:
        zone_emoji, zone_message = worker.get_activity_zone()
    
    text = f"📈 **Ваша активность: {worker.activity_level}**\n\n"
    text += f"{zone_emoji} {zone_message}\n\n"
    
    # Добавляем информацию о восстановлении активности
    text += "**Как восстановить активность?**\n"
    text += "✅ Выполнение заказов = +20\n"
    text += "✅ Каждую неделю без нарушений = +1\n\n"
    
    if worker.activity_level < 9:
        text += "⚠️ При красной зоне можно потерять временно доступ к сервису\n\n"
    
    text += "💡 Оставайтесь активными для получения больше заказов!"
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_btn(),
        parse_mode='Markdown'
    )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "worker_status", WorkStates.worker_menu)
async def worker_status(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать статус исполнителя"""
    logger.debug(f'worker_status...')
    kbc = KeyboardCollection()
    
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    
    text = f"📋 **Ваш статус**\n\n"
    text += f"👤 ИП: {'✅ Есть' if worker.individual_entrepreneur else '❌ Нет'}\n"
    text += f"🏢 ООО: {'✅ Есть' if hasattr(worker, 'ooo') and worker.ooo else '❌ Нет'}\n"
    text += f"🏭 СЗ: {'✅ Есть' if hasattr(worker, 'sz') and worker.sz else '❌ Нет'}\n\n"
    text += f"💡 Указание статуса поможет заказчикам лучше вас найти!"
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_btn(),
        parse_mode='Markdown'
    )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(F.data == "add_city", WorkStates.worker_menu)
async def add_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Добавить город (платная функция)"""
    logger.debug(f'add_city...')
    kbc = KeyboardCollection()
    
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    
    text = "🏙️ **Добавить город ₽**\n\n"
    
    if active_subscriptions:
        text += "**Активные города:**\n"
        for subscription in active_subscriptions:
            # Получаем названия городов
            city_names = []
            for city_id in subscription.city_ids:
                city = await City.get_city(id=city_id)
                if city:
                    city_names.append(city.city)
            
            end_date = datetime.strptime(subscription.subscription_end, '%Y-%m-%d').strftime('%d.%m.%Y')
            text += f"• {', '.join(city_names)} до {end_date}\n"
        text += "\n"
    
    text += "Выберите дополнительное количество городов для получения заказов:"
    
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("+1 city", "city_count_1"))
    builder.add(kbc._inline("+2 city", "city_count_2"))
    builder.add(kbc._inline("+3 city", "city_count_3"))
    builder.add(kbc._inline("+4 city", "city_count_4"))
    builder.add(kbc._inline("+5 city", "city_count_5"))
    builder.add(kbc._inline("+10 city", "city_count_10"))
    builder.add(kbc._inline("+20 city", "city_count_20"))
    builder.add(kbc._inline("🏠 В меню", "worker_menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('city_count_'))
async def city_count_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор количества городов"""
    logger.debug(f'city_count_selected...')
    kbc = KeyboardCollection()
    
    # Парсим количество городов из callback_data: city_count_1, city_count_2, etc.
    city_count = int(callback.data.split('_')[2])
    
    # Сохраняем количество городов в состояние
    await state.update_data(city_count=city_count)
    
    # Цены за месяц для каждого количества городов
    prices = {
        1: 90,    # 1 месяц = 90₽
        2: 180,   # 2 месяца = 171₽, но за месяц = 90₽
        3: 270,   # 3 месяца = 243₽, но за месяц = 90₽
        4: 360,   # 4 месяца = 360₽ за месяц
        5: 450,   # 5 месяцев = 450₽ за месяц
        10: 900,  # 10 месяцев = 900₽ за месяц
        20: 1800  # 20 месяцев = 1800₽ за месяц
    }
    
    base_price = prices[city_count]
    
    text = f"🏙️ **+{city_count} city**\n\n"
    text += f"Выберите срок рассылки:\n\n"
    text += f"💰 Цены за {city_count} город(ов):\n"
    text += f"• 1 месяц: {base_price}₽\n"
    text += f"• 2 месяца: {int(base_price * 2 * 0.95)}₽ (скидка 5%)\n"
    text += f"• 3 месяца: {int(base_price * 3 * 0.9)}₽ (скидка 10%)\n"
    text += f"• 6 месяцев: {int(base_price * 6 * 0.8)}₽ (скидка 20%)\n"
    text += f"• 12 месяцев: {int(base_price * 12 * 0.7)}₽ (скидка 30%)"
    
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline(f"Купить 1 месяц {base_price}₽", f"city_period_1_{base_price}"))
    builder.add(kbc._inline(f"Купить 2 месяца {int(base_price * 2 * 0.95)}₽", f"city_period_2_{int(base_price * 2 * 0.95)}"))
    builder.add(kbc._inline(f"Купить 3 месяца {int(base_price * 3 * 0.9)}₽", f"city_period_3_{int(base_price * 3 * 0.9)}"))
    builder.add(kbc._inline(f"Купить 6 месяцев {int(base_price * 6 * 0.8)}₽", f"city_period_6_{int(base_price * 6 * 0.8)}"))
    builder.add(kbc._inline(f"Купить 12 месяцев {int(base_price * 12 * 0.7)}₽", f"city_period_12_{int(base_price * 12 * 0.7)}"))
    builder.add(kbc._inline("◀️ К выбору количества городов", "add_city"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('city_period_'))
async def city_period_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор периода подписки на города"""
    logger.debug(f'city_period_selected...')
    kbc = KeyboardCollection()
    
    # Парсим данные: city_period_{months}_{price}
    parts = callback.data.split('_')
    months = int(parts[2])
    price = int(parts[3])
    
    # Получаем данные из состояния
    data = await state.get_data()
    city_count = data.get('city_count', 1)
    
    text = f"💰 **Подтверждение покупки**\n\n"
    text += f"🏙️ Количество городов: {city_count}\n"
    text += f"📅 Период: {months} месяц(ев)\n"
    text += f"💵 Стоимость: {price}₽\n\n"
    text += f"После покупки вы будете получать заказы из дополнительных городов в течение {months} месяца(ев).\n\n"
    text += f"Подтвердить покупку?"
    
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Подтвердить покупку", f"confirm_city_purchase_{city_count}_{months}_{price}"))
    builder.add(kbc._inline("❌ Отмена", "add_city"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('confirm_city_purchase_'))
async def confirm_city_purchase(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение покупки подписки на города"""
    logger.debug(f'confirm_city_purchase...')
    kbc = KeyboardCollection()
    
    # Парсим данные: confirm_city_purchase_{city_count}_{months}_{price}
    parts = callback.data.split('_')
    city_count = int(parts[3])
    months = int(parts[4])
    price = int(parts[5])
    
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    try:
        # Здесь должна быть интеграция с платежной системой
        # Пока что просто создаем подписку (имитация успешной оплаты)
        
        # Вычисляем даты
        start_date = datetime.now()
        end_date = start_date + timedelta(days=months * 30)
        
        # Создаем подписку с пустыми city_ids (будут выбраны позже)
        subscription = WorkerCitySubscription(
            id=None,  # Для новой записи
            worker_id=worker.id,
            city_ids=[],  # Пока пустой список, будет заполнен при выборе городов
            subscription_start=start_date.strftime('%Y-%m-%d'),
            subscription_end=end_date.strftime('%Y-%m-%d'),
            subscription_months=months,
            price=price
        )
        await subscription.save()
        
        # Проверяем, есть ли доступные города для выбора
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        all_cities = await City.get_all()
        
        # Получаем все города из всех активных подписок исполнителя
        all_active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        all_subscription_cities = []
        for subscription in all_active_subscriptions:
            all_subscription_cities.extend(subscription.city_ids)
        
        # Исключаем: основной город, города из других подписок
        excluded_cities = worker.city_id + all_subscription_cities
        available_cities = [city for city in all_cities if city.id not in excluded_cities]
        
        # Сохраняем данные в состоянии для выбора городов
        await state.update_data(
            subscription_id=subscription.id,
            city_count=city_count,
            selected_cities=[]
        )
        
        text = f"✅ **Покупка успешно выполнена!**\n\n"
        text += f"🎉 Подписка на {city_count} город(ов) активирована!\n"
        text += f"📅 Период: {months} месяц(ев)\n"
        text += f"⏰ Действует до: {end_date.strftime('%d.%m.%Y')}\n\n"
        
        if len(available_cities) == 0:
            text += f"⚠️ **Нет доступных городов для выбора!**\n"
            text += f"Все города уже выбраны в других подписках или являются основными.\n"
            text += f"Подписка сохранена, вы сможете выбрать города позже."
            
            await callback.message.edit_text(
                text=text,
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )
            await state.set_state(WorkStates.worker_menu)
        else:
            text += f"📍 Теперь выберите города для получения заказов"
            
            # Переходим к выбору городов
            await state.set_state(WorkStates.worker_choose_subscription_cities)
            await choose_subscription_cities(callback, state)
        
    except Exception as e:
        logger.error(f"Error in confirm_city_purchase: {e}")
        await callback.answer("❌ Произошла ошибка при покупке", show_alert=True)


async def choose_subscription_cities(callback: CallbackQuery, state: FSMContext) -> None:
    """Интерфейс выбора городов для подписки"""
    kbc = KeyboardCollection()
    data = await state.get_data()
    city_count = data.get('city_count', 1)
    selected_cities = data.get('selected_cities', [])
    
    # Получаем все города кроме уже выбранных и основного города исполнителя
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    all_cities = await City.get_all()
    
    # Получаем исключенные города из состояния (для продолжения выбора) или вычисляем заново
    excluded_from_state = data.get('excluded_cities', [])
    if excluded_from_state:
        # Это продолжение выбора - используем исключенные города из состояния
        excluded_cities = selected_cities + worker.city_id + excluded_from_state
    else:
        # Это новый выбор - получаем все города из всех активных подписок
        all_active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        all_subscription_cities = []
        for subscription in all_active_subscriptions:
            all_subscription_cities.extend(subscription.city_ids)
        
        # Исключаем: уже выбранные в текущей подписке, основной город, города из других подписок
        excluded_cities = selected_cities + worker.city_id + all_subscription_cities
    
    available_cities = [city for city in all_cities if city.id not in excluded_cities]
    
    # Получаем названия основных городов (оптимизировано)
    cities_dict = {city.id: city.city for city in all_cities}
    main_city_names = [cities_dict.get(city_id, f"Город {city_id}") for city_id in worker.city_id]
    
    text = f"🏙️ **Выберите города для подписки**\n\n"
    text += f"📊 Выбрано: {len(selected_cities)} из {city_count}\n\n"
    
    if len(available_cities) == 0:
        text += f"❌ **Нет доступных городов для выбора!**\n"
        text += f"Все города уже выбраны в других подписках или являются основными."
    elif len(selected_cities) >= city_count:
        text += f"✅ Вы выбрали максимальное количество городов!\n"
        text += f"Нажмите 'Подтвердить выбор' для завершения."
    else:
        text += f"💡 **Напишите название города** для поиска или выберите из списка ниже:\n"
        text += f"Выберите еще {city_count - len(selected_cities)} город(ов)"
    
    builder = InlineKeyboardBuilder()
    
    # Показываем доступные города с пагинацией только если есть доступные города
    if len(available_cities) > 0:
        page = data.get('city_page', 0)
        cities_per_page = 8
        start_idx = page * cities_per_page
        end_idx = start_idx + cities_per_page
        page_cities = available_cities[start_idx:end_idx]
        
        for city in page_cities:
            city_name = city.city
            if city.id in selected_cities:
                builder.add(kbc._inline(f"✅ {city_name}", f"subscription_city_select_{city.id}"))
            else:
                builder.add(kbc._inline(f"❌ {city_name}", f"subscription_city_select_{city.id}"))
        
        # Навигация по страницам
        nav_buttons = []
        if page > 0:
            nav_buttons.append(kbc._inline("◀️", f"subscription_city_page_{page-1}"))
        
        total_pages = (len(available_cities) + cities_per_page - 1) // cities_per_page
        if total_pages > 1:
            nav_buttons.append(kbc._inline(f"{page+1}/{total_pages}", "subscription_city_noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(kbc._inline("▶️", f"subscription_city_page_{page+1}"))
        
        if nav_buttons:
            builder.row(*nav_buttons)
    
    # Кнопки управления
    if len(selected_cities) >= city_count and len(available_cities) > 0:
        builder.add(kbc._inline("✅ Подтвердить выбор", "subscription_cities_confirm"))
    
    builder.add(kbc._inline("🏠 В меню", "worker_menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('subscription_city_select_'))
async def subscription_city_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор/отмена выбора города для подписки"""
    city_id = int(callback.data.split('_')[3])
    data = await state.get_data()
    selected_cities = data.get('selected_cities', [])
    city_count = data.get('city_count', 1)
    
    if city_id in selected_cities:
        # Убираем город из выбранных
        selected_cities.remove(city_id)
        await callback.answer("❌ Город убран из выбора")
    else:
        # Добавляем город в выбранные (если не превышен лимит)
        if len(selected_cities) < city_count:
            selected_cities.append(city_id)
            await callback.answer("✅ Город добавлен в выбор")
        else:
            await callback.answer(f"❌ Максимум {city_count} городов", show_alert=True)
            return
    
    await state.update_data(selected_cities=selected_cities)
    await choose_subscription_cities(callback, state)


@router.callback_query(lambda c: c.data.startswith('subscription_city_page_'))
async def subscription_city_page(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход на другую страницу выбора городов"""
    page = int(callback.data.split('_')[3])
    await state.update_data(city_page=page)
    await choose_subscription_cities(callback, state)


@router.callback_query(F.data == "subscription_cities_confirm")
async def subscription_cities_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение выбора городов для подписки"""
    kbc = KeyboardCollection()
    data = await state.get_data()
    selected_cities = data.get('selected_cities', [])
    subscription_id = data.get('subscription_id')
    city_count = data.get('city_count', 1)
    
    if len(selected_cities) != city_count:
        await callback.answer("❌ Выберите все города", show_alert=True)
        return
    
    # Получаем названия выбранных городов
    city_names = []
    for city_id in selected_cities:
        city = await City.get_city(id=city_id)
        if city:
            city_names.append(city.city)
    
    text = f"✅ **Подтверждение выбора**\n\n"
    text += f"🏙️ Выбранные города:\n"
    for name in city_names:
        text += f"• {name}\n"
    text += f"\n📊 Всего: {len(selected_cities)} городов\n\n"
    text += f"Подтвердить выбор?"
    
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Подтвердить", "subscription_cities_final_confirm"))
    builder.add(kbc._inline("❌ Отмена", "subscription_cities_back"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(F.data == "subscription_cities_final_confirm")
async def subscription_cities_final_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Финальное подтверждение и сохранение выбранных городов"""
    kbc = KeyboardCollection()
    data = await state.get_data()
    selected_cities = data.get('selected_cities', [])
    subscription_id = data.get('subscription_id')
    
    try:
        # Получаем текущую подписку, чтобы объединить с уже выбранными городами
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        
        existing_subscription = None
        for subscription in active_subscriptions:
            if subscription.id == subscription_id:
                existing_subscription = subscription
                break
        
        if existing_subscription:
            # Объединяем уже выбранные города с новыми
            all_selected_cities = existing_subscription.city_ids + selected_cities
            # Убираем дубликаты
            all_selected_cities = list(set(all_selected_cities))
        else:
            all_selected_cities = selected_cities
        
        # Обновляем подписку с объединенными городами
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        city_ids_str = '|'.join(map(str, all_selected_cities))
        await conn.execute(
            'UPDATE worker_city_subscriptions SET city_ids = ? WHERE id = ?',
            [city_ids_str, subscription_id])
        await conn.commit()
        await conn.close()
        
        # Получаем названия всех городов для сообщения
        all_city_names = []
        for city_id in all_selected_cities:
            city = await City.get_city(id=city_id)
            if city:
                all_city_names.append(city.city)
        
        # Получаем названия только что добавленных городов
        new_city_names = []
        for city_id in selected_cities:
            city = await City.get_city(id=city_id)
            if city:
                new_city_names.append(city.city)
        
        text = f"🎉 **Города добавлены в подписку!**\n\n"
        if new_city_names:
            text += f"🆕 Добавленные города:\n"
            for name in new_city_names:
                text += f"• {name}\n"
            text += f"\n"
        
        text += f"🏙️ Все города в подписке:\n"
        for name in all_city_names:
            text += f"• {name}\n"
        text += f"\n💡 Теперь вы будете получать заказы из всех этих городов!"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.menu_btn(),
            parse_mode='Markdown'
        )
        await state.set_state(WorkStates.worker_menu)
        
    except Exception as e:
        logger.error(f"Error in subscription_cities_final_confirm: {e}")
        await callback.answer("❌ Произошла ошибка при сохранении", show_alert=True)


@router.callback_query(F.data == "subscription_cities_back")
async def subscription_cities_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к выбору городов"""
    await choose_subscription_cities(callback, state)


@router.callback_query(F.data == "subscription_city_noop")
async def subscription_city_noop(callback: CallbackQuery, state: FSMContext) -> None:
    """Заглушка для кнопки номера страницы"""
    await callback.answer()


@router.message(F.text, WorkStates.worker_choose_subscription_cities)
async def subscription_city_search(message: Message, state: FSMContext) -> None:
    """Поиск городов по названию"""
    kbc = KeyboardCollection()
    city_input = message.text
    logger.debug(f'subscription_city_search: {city_input}')

    # Получаем данные из состояния
    data = await state.get_data()
    selected_cities = data.get('selected_cities', [])
    city_count = data.get('city_count', 1)
    
    # Получаем все доступные города
    worker = await Worker.get_worker(tg_id=message.from_user.id)
    all_cities = await City.get_all(sort=False)
    
    # Получаем исключенные города из состояния (для продолжения выбора) или вычисляем заново
    excluded_from_state = data.get('excluded_cities', [])
    if excluded_from_state:
        # Это продолжение выбора - используем исключенные города из состояния
        excluded_cities = selected_cities + worker.city_id + excluded_from_state
    else:
        # Это новый выбор - получаем все города из всех активных подписок
        all_active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        all_subscription_cities = []
        for subscription in all_active_subscriptions:
            all_subscription_cities.extend(subscription.city_ids)
        
        # Исключаем: уже выбранные в текущей подписке, основной город, города из других подписок
        excluded_cities = selected_cities + worker.city_id + all_subscription_cities
    
    available_cities = [city for city in all_cities if city.id not in excluded_cities]
    
    city_names = [city.city for city in available_cities]

    # Ищем города по названию
    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'❌ Город "{city_input}" не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    # Получаем найденные города
    found_cities = []
    for i in city_find:
        if i <= len(available_cities):
            found_cities.append(available_cities[i-1])

    city_names = [city.city for city in found_cities]
    city_ids = [city.id for city in found_cities]

    # Получаем названия основных городов
    main_city_names = []
    for city_id in worker.city_id:
        city = await City.get_city(id=city_id)
        if city:
            main_city_names.append(city.city)

    text = f"🔍 **Результаты поиска по: {city_input}**\n\n"
    text += f"📊 Выбрано: {len(selected_cities)} из {city_count}\n"
    text += f"📍 Основной город: {', '.join(main_city_names)}\n\n"
    text += f"Выберите город из результатов поиска:"

    builder = InlineKeyboardBuilder()
    
    for city in found_cities:
        city_name = city.city
        if city.id in selected_cities:
            builder.add(kbc._inline(f"✅ {city_name}", f"subscription_city_select_{city.id}"))
        else:
            builder.add(kbc._inline(f"❌ {city_name}", f"subscription_city_select_{city.id}"))
    
    builder.add(kbc._inline("◀️ Отменить поиск", "subscription_city_cancel_search"))
    builder.adjust(1)

    await message.answer(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(F.data == "subscription_city_cancel_search")
async def subscription_city_cancel_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена поиска и возврат к основному списку"""
    await state.update_data(city_page=0)  # Сбрасываем страницу
    await choose_subscription_cities(callback, state)


@router.callback_query(lambda c: c.data.startswith('city_subscription_'))
async def city_subscription_management(callback: CallbackQuery, state: FSMContext) -> None:
    """Управление подпиской на города"""
    logger.debug(f'city_subscription_management...')
    kbc = KeyboardCollection()
    
    # Парсим данные: city_subscription_{action}_{subscription_id}
    parts = callback.data.split('_')
    action = parts[2]  # renew, change, cancel
    subscription_id = int(parts[3])
    
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    if action == "renew":
        # Продление подписки - показываем те же тарифы
        text = f"🔄 **Продление подписки**\n\n"
        text += f"Выберите новый срок подписки:"
        
        # Получаем количество городов из подписки
        subscription = await WorkerCitySubscription.get_active_by_worker(worker.id)
        if not subscription:
            await callback.answer("❌ Подписка не найдена", show_alert=True)
            return
            
        city_count = len(subscription[0].city_ids) if subscription else 1
        
        # Цены за месяц для каждого количества городов
        prices = {
            1: 90, 2: 180, 3: 270, 4: 360, 5: 450, 10: 900, 20: 1800
        }
        base_price = prices.get(city_count, 90)
        
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline(f"Продлить на 1 месяц {base_price}₽", f"city_period_1_{base_price}"))
        builder.add(kbc._inline(f"Продлить на 2 месяца {int(base_price * 2 * 0.95)}₽", f"city_period_2_{int(base_price * 2 * 0.95)}"))
        builder.add(kbc._inline(f"Продлить на 3 месяца {int(base_price * 3 * 0.9)}₽", f"city_period_3_{int(base_price * 3 * 0.9)}"))
        builder.add(kbc._inline(f"Продлить на 6 месяцев {int(base_price * 6 * 0.8)}₽", f"city_period_6_{int(base_price * 6 * 0.8)}"))
        builder.add(kbc._inline(f"Продлить на 12 месяцев {int(base_price * 12 * 0.7)}₽", f"city_period_12_{int(base_price * 12 * 0.7)}"))
        builder.add(kbc._inline("◀️ Назад", "add_city"))
        builder.adjust(1)
        
    elif action == "change":
        # Смена тарифа - переход к выбору количества городов
        await add_city(callback, state)
        return
        
    elif action == "cancel":
        # Отказ от подписки
        text = f"❌ **Отказ от подписки**\n\n"
        text += f"Подписка будет отключена, вы всегда сможете подключить её снова в удобное для вас время!"
        
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("✅ Подтвердить отказ", f"confirm_cancel_subscription_{subscription_id}"))
        builder.add(kbc._inline("◀️ Отмена", "add_city"))
        builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('confirm_cancel_subscription_'))
async def confirm_cancel_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение отмены подписки"""
    logger.debug(f'confirm_cancel_subscription...')
    kbc = KeyboardCollection()
    
    subscription_id = int(callback.data.split('_')[3])
    
    try:
        # Деактивируем подписку
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        await conn.execute(
            'UPDATE worker_city_subscriptions SET active = 0 WHERE id = ?',
            [subscription_id])
        await conn.commit()
        await conn.close()
        
        text = f"✅ **Подписка отменена**\n\n"
        text += f"Подписка на дополнительные города деактивирована.\n"
        text += f"Вы можете снова подключить её в любое время через меню."
        
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.menu_btn(),
            parse_mode='Markdown'
        )
        await state.set_state(WorkStates.worker_menu)
        
    except Exception as e:
        logger.error(f"Error in confirm_cancel_subscription: {e}")
        await callback.answer("❌ Произошла ошибка при отмене", show_alert=True)


async def send_city_subscription_expiry_notifications():
    """Отправляет уведомления об истечении подписок на города"""
    try:
        from app.keyboards import KeyboardCollection
        kbc = KeyboardCollection()
        
        expiring_subscriptions = await WorkerCitySubscription.get_expiring_tomorrow()
        
        for subscription in expiring_subscriptions:
            worker = await Worker.get_worker(id=subscription.worker_id)
            if not worker:
                continue
            
            # Получаем названия городов
            city_names = []
            for city_id in subscription.city_ids:
                city = await City.get_city(id=city_id)
                if city:
                    city_names.append(city.city)
            
            # Вычисляем количество городов из цены
            prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
            city_count = prices.get(subscription.price, 1)
            
            text = f"⚠️ **Завтра истекает срок подписки**\n\n"
            text += f"🏙️ **+{city_count} city**\n"
            for city_name in city_names:
                text += f"{city_name}\n"
            text += f"📅 Срок {subscription.subscription_months} месяц.\n\n"
            text += f"Продлите её, чтобы продолжать получать заказы."
            
            builder = InlineKeyboardBuilder()
            builder.add(kbc._inline("🔄 Продлить", f"city_subscription_renew_{subscription.id}"))
            builder.add(kbc._inline("🔄 Сменить тариф", f"city_subscription_change_{subscription.id}"))
            builder.add(kbc._inline("❌ Отказаться", f"city_subscription_cancel_{subscription.id}"))
            builder.adjust(1)
            
            try:
                await bot.send_message(
                    chat_id=worker.tg_id,
                    text=text,
                    reply_markup=builder.as_markup(),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send notification to worker {worker.tg_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_city_subscription_expiry_notifications: {e}")


@router.callback_query(F.data == "worker_purchased_contacts", WorkStates.worker_menu)
async def worker_purchased_contacts(callback: CallbackQuery, state: FSMContext) -> None:
    """Покупка контактов"""
    logger.debug(f'worker_purchased_contacts...')
    kbc = KeyboardCollection()
    
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    
    text = f"💳 **Купить контакты**\n\n"
    text += f"📊 У вас сейчас: {worker.purchased_contacts} контактов\n"
    text += f"🔓 Безлимитный доступ: {'✅ Активен' if worker.unlimited_contacts_until else '❌ Нет'}\n\n"
    
    if worker.unlimited_contacts_until:
        try:
            until_date = datetime.fromisoformat(worker.unlimited_contacts_until)
            if until_date > datetime.now():
                text += f"⏰ Безлимит действует до: {until_date.strftime('%d.%m.%Y %H:%M')}\n\n"
            else:
                text += f"⏰ Безлимит истек\n\n"
        except ValueError:
            text += f"⏰ Безлимит истек\n\n"
    
    text += f"📦 **Доступные тарифы:**\n\n"
    text += f"🔸 1 контакт - 190₽\n"
    text += f"🔸 2 контакта - 290₽ (-24%)\n"
    text += f"🔸 5 контактов - 690₽ (-27%)\n"
    text += f"🔸 10 контактов - 1190₽ (-37%)\n"
    text += f"🔸 Безлимит 1 месяц - 1990₽\n"
    text += f"🔸 Безлимит 3 месяца - 4490₽\n"
    text += f"🔸 Безлимит 6 месяцев - 6990₽\n"
    text += f"🔸 Безлимит 12 месяцев - 10990₽\n\n"
    text += f"💡 Контакты нужны для получения телефонов заказчиков"
    
    # Используем существующую клавиатуру с тарифами
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("190 ₽ — 1 контакт", "contact-tariff_1_190"))
    builder.add(kbc._inline("290 ₽ — 2 контакта", "contact-tariff_2_290"))
    builder.add(kbc._inline("690 ₽ — 5 контактов", "contact-tariff_5_690"))
    builder.add(kbc._inline("1190 ₽ — 10 контактов", "contact-tariff_10_1190"))
    builder.add(kbc._inline("1990 ₽ — Безлимит 1 месяц", "contact-tariff_unlimited_1_1990"))
    builder.add(kbc._inline("4490 ₽ — Безлимит 3 месяца", "contact-tariff_unlimited_3_4490"))
    builder.add(kbc._inline("6990 ₽ — Безлимит 6 месяцев", "contact-tariff_unlimited_6_6990"))
    builder.add(kbc._inline("10990 ₽ — Безлимит 12 месяцев", "contact-tariff_unlimited_12_10990"))
    builder.add(kbc._inline("🏠 В меню", "worker_menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('contact-tariff_'), WorkStates.worker_menu)
async def buy_contacts_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик покупки контактов"""
    logger.debug(f'buy_contacts_handler...')
    kbc = KeyboardCollection()
    
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    # Парсим callback_data: contact-tariff_{tokens}_{price} или contact-tariff_unlimited_{months}_{price}
    parts = callback.data.split('_')
    logger.debug(f"Callback data: {callback.data}")
    logger.debug(f"Parts: {parts}")
    
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат тарифа", show_alert=True)
        return
    
    if parts[1] == "unlimited":
        # Безлимитный тариф: contact-tariff_unlimited_{months}_{price}
        months = int(parts[2])
        price = int(parts[3])
        tokens = -1  # Безлимит
        tariff_name = f"Безлимит {months} месяц(ев)"
    else:
        # Обычный тариф: contact-tariff_{tokens}_{price}
        tokens = int(parts[1])
        price = int(parts[2])
        tariff_name = f"{tokens} контакт(ов)"
        months = 0  # Для обычных тарифов months = 0
    
    # Создаем инвойс для оплаты
    text = f"""
💰 **Подтверждение покупки**

📦 Тариф: {tariff_name}
💵 Цена: {price}₽

{f'После покупки у вас будет {worker.purchased_contacts + tokens} контакт(ов)' if tokens > 0 else f'Безлимитный доступ к контактам на {months} месяц(ев)'}

Подтвердить покупку?
        """
    
    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Подтвердить", f"confirm_contact_purchase_{tokens}_{price}_{months}"))
    builder.add(kbc._inline("❌ Отмена", "worker_purchased_contacts"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('confirm_contact_purchase_'), WorkStates.worker_menu)
async def confirm_contact_purchase(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение покупки контактов"""
    logger.debug(f'confirm_contact_purchase...')
    kbc = KeyboardCollection()
    
    # Парсим данные: confirm_contact_purchase_{tokens}_{price}_{months}
    parts = callback.data.split('_')
    tokens = int(parts[3])
    price = int(parts[4])
    months = int(parts[5]) if len(parts) > 5 else 0
    
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    # Здесь должна быть интеграция с платежной системой
    # Пока что просто добавляем контакты (имитация успешной оплаты)
    
    try:
        if tokens == -1:  # Безлимит
            # Устанавливаем безлимитный доступ на указанное количество месяцев
            until_date = datetime.now() + timedelta(days=months * 30)
            await worker.update_unlimited_contacts(unlimited_contacts_until=until_date.isoformat())
            
            text = f"""
✅ **Покупка успешно выполнена!**

🎉 У вас теперь безлимитный доступ к контактам!
⏰ Действует до: {until_date.strftime('%d.%m.%Y %H:%M')}
📅 Период: {months} месяц(ев)

💡 Теперь вы можете получать контакты заказчиков без ограничений!
            """
        else:
            # Добавляем обычные контакты
            new_count = worker.purchased_contacts + tokens
            await worker.update_purchased_contacts(purchased_contacts=new_count)
            
            text = f"""
✅ **Покупка успешно выполнена!**

🎉 Добавлено {tokens} контактов!
📊 У вас теперь: {new_count} контактов

💡 Используйте их для получения телефонов заказчиков!
            """
        
        await callback.message.edit_text(
            text=text,
            reply_markup=kbc.menu_btn(),
            parse_mode='Markdown'
        )
        await state.set_state(WorkStates.worker_menu)
        
    except Exception as e:
        logger.error(f"Error in confirm_contact_purchase: {e}")
        await callback.answer("❌ Произошла ошибка при покупке", show_alert=True)


@router.callback_query(F.data == "worker_change_city_menu", WorkStates.worker_menu)
async def worker_change_city_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Меню смены города - показывает опции в зависимости от наличия купленных городов"""
    logger.debug(f'worker_change_city_menu...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    
    # Проверяем, есть ли у исполнителя купленные города
    has_purchased_cities = len(active_subscriptions) > 0
    
    text = "🏙️ **Сменить город**\n\n"
    
    if has_purchased_cities:
        # Если есть купленные города - показываем опции
        text += "Выберите действие:\n\n"
        text += "📋 **Мои города** - просмотр и управление купленными городами\n"
        text += "🔄 **Сменить основной город** - изменить основной город из доступных"
        
        # Создаем клавиатуру с опциями
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        builder.add(kbc._inline("📋 Мои города", "worker_my_cities"))
        builder.add(kbc._inline("🔄 Сменить основной город", "worker_change_main_city"))
        builder.add(kbc._inline("◀️ Назад", "worker_menu"))
        builder.adjust(1)
        
        await callback.message.edit_text(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    else:
        # Если нет купленных городов - показываем опцию выбора города из всех доступных
        text += "У вас нет купленных городов.\n\n"
        text += "Выберите действие:\n\n"
        text += "🔄 **Сменить основной город** - выбрать из всех доступных городов\n"
        text += "📍 **Выбрать город** - выбрать любой город (станет основным)"
        
        # Создаем клавиатуру с опциями
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        builder.add(kbc._inline("🔄 Сменить основной город", "worker_change_main_city"))
        builder.add(kbc._inline("📍 Выбрать город", "worker_choose_city"))
        builder.add(kbc._inline("◀️ Назад", "worker_menu"))
        builder.adjust(1)
        
        await callback.message.edit_text(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )


@router.callback_query(F.data == "worker_change_main_city", WorkStates.worker_menu)
async def worker_change_main_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Смена основного города исполнителя с пагинацией и поиском"""
    logger.debug(f'worker_change_main_city...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    # Получаем ВСЕ города для смены основного города
    # Исполнитель может выбрать любой город как основной
    all_cities = await City.get_all()
    cities_dict = {city.id: city.city for city in all_cities}
    
    city_names = [city.city for city in all_cities]
    city_ids = [city.id for city in all_cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    current_main_city = cities_dict.get(worker.city_id[0], f"Город {worker.city_id[0]}")
    
    text = f"🔄 **Смена основного города**\n\n"
    text += f"📍 **Текущий основной город:** {current_main_city}\n\n"
    text += f"Выберите город или напишите его текстом\n\n"
    text += f'Показано {id_now + len(city_names)} из {count_cities} городов'

    msg = await callback.message.edit_text(
        text=text,
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=True,),
        parse_mode='Markdown'
    )
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(WorkStates.worker_change_main_city)


@router.callback_query(F.data == "worker_choose_city", WorkStates.worker_menu)
async def worker_choose_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор города из всех доступных городов"""
    logger.debug(f'worker_choose_city...')
    kbc = KeyboardCollection()

    # Получаем все города
    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    text = f"📍 **Выберите город**\n\n"
    text += f"Выберите город или напишите его текстом\n\n"
    text += f'Показано {id_now + len(city_names)} из {count_cities} городов'

    msg = await callback.message.edit_text(
        text=text,
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=True,),
        parse_mode='Markdown'
    )
    await state.update_data(msg_id=msg.message_id)
    await state.set_state(WorkStates.worker_choose_city)


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_change_main_city)
async def change_main_city_next(callback: CallbackQuery, state: FSMContext) -> None:
    """Навигация по городам для смены основного города"""
    logger.debug(f'change_main_city_next...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    
    # Получаем ВСЕ города для смены основного города
    all_cities = await City.get_all()
    city_names = [city.city for city in all_cities]
    city_ids = [city.id for city in all_cities]
    count_cities = len(city_names)

    id_now = int(callback.data.split('_')[1])
    
    # Если пытаемся пойти назад с первой страницы - возвращаемся в меню смены города
    if id_now < 0:
        await state.clear()  # Очищаем состояние
        await state.set_state(WorkStates.worker_menu)
        await worker_change_city_menu(callback, state)
        return

    btn_next = True if len(city_names) > 5 + id_now else False
    btn_back = True if id_now > 0 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    cities_dict = {city.id: city.city for city in all_cities}
    current_main_city = cities_dict.get(worker.city_id[0], f"Город {worker.city_id[0]}")

    try:
        msg = await callback.message.edit_text(
            text=f"🔄 **Смена основного города**\n\n"
                 f"📍 **Текущий основной город:** {current_main_city}\n\n"
                 f"Выберите город или напишите его текстом\n\n"
                 f'Показано {id_now + len(city_names)} из {count_cities} городов',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back,),
            parse_mode='Markdown'
        )
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.message(F.text, WorkStates.worker_change_main_city)
async def change_main_city_search(message: Message, state: FSMContext) -> None:
    """Поиск города по тексту для смены основного города"""
    logger.debug(f'change_main_city_search...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=message.from_user.id)
    city_input = message.text
    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id'))

    # Получаем ВСЕ города для поиска
    all_cities = await City.get_all()
    city_names = [city.city for city in all_cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    cities_result = []
    for city_id in city_find:
        city = await City.get_city(id=city_id)
        cities_result.append(city)

    city_names = [city.city for city in cities_result]
    city_ids = [city.id for city in cities_result]

    cities_dict = {city.id: city.city for city in all_cities}
    current_main_city = cities_dict.get(worker.city_id[0], f"Город {worker.city_id[0]}")

    msg = await message.answer(
        text=f"🔄 **Результаты поиска по: {city_input}**\n\n"
             f"📍 **Текущий основной город:** {current_main_city}\n\n"
             f"Выберите город или напишите его текстом\n\n",
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=True, 
                                    btn_next_name='Отменить результаты поиска'),
        parse_mode='Markdown'
    )
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_change_main_city)
async def change_main_city_end(callback: CallbackQuery, state: FSMContext) -> None:
    """Завершение выбора города для смены основного города"""
    logger.debug(f'change_main_city_end...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    new_city_id = int(callback.data.split('_')[1])
    
    # Проверяем, что город существует в базе данных
    city_exists = await City.get_city(id=new_city_id)
    if not city_exists:
        await callback.answer("❌ Город не найден", show_alert=True)
        return
    
    # Получаем названия городов
    all_cities = await City.get_all()
    cities_dict = {city.id: city.city for city in all_cities}
    
    new_city_name = cities_dict.get(new_city_id, f"Город {new_city_id}")
    old_city_id = worker.city_id[0]
    old_city_name = cities_dict.get(old_city_id, f"Город {old_city_id}")
    
    # Меняем основной город
    worker.city_id[0] = new_city_id
    
    # Если старый город был в списке, перемещаем его на второе место
    if len(worker.city_id) > 1 and old_city_id in worker.city_id[1:]:
        worker.city_id.remove(old_city_id)
        worker.city_id.insert(1, old_city_id)
    
    await worker.update_city(worker.city_id)
    
    text = f"✅ **Основной город изменен**\n\n"
    text += f"📍 **Новый основной город:** {new_city_name}\n"
    text += f"📍 **Предыдущий город:** {old_city_name}\n\n"
    text += "Изменения вступят в силу немедленно."
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_btn(),
        parse_mode='Markdown'
    )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_choose_city)
async def choose_city_next_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Навигация по городам для исполнителя"""
    logger.debug(f'choose_city_next_worker...')
    kbc = KeyboardCollection()

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)

    id_now = int(callback.data.split('_')[1])
    
    # Если пытаемся пойти назад с первой страницы - возвращаемся в меню смены города
    if id_now < 0:
        await state.clear()  # Очищаем состояние
        await state.set_state(WorkStates.worker_menu)
        await worker_change_city_menu(callback, state)
        return

    btn_next = True if len(city_names) > 5 + id_now else False
    btn_back = True if id_now > 0 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    try:
        msg = await callback.message.edit_text(
            text=f"📍 **Выберите город**\n\n"
                 f"Выберите город или напишите его текстом\n\n"
                 f'Показано {id_now + len(city_names)} из {count_cities} городов',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back,),
            parse_mode='Markdown'
        )
        await state.update_data(msg_id=msg.message_id)
    except TelegramBadRequest:
        pass


@router.message(F.text, WorkStates.worker_choose_city)
async def choose_city_search_worker(message: Message, state: FSMContext) -> None:
    """Поиск города по тексту для исполнителя"""
    logger.debug(f'choose_city_search_worker...')
    kbc = KeyboardCollection()

    city_input = message.text
    state_data = await state.get_data()
    msg_id = int(state_data.get('msg_id'))

    cities = await City.get_all()
    city_names = [city.city for city in cities]

    city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
    if not city_find:
        await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
        return

    cities_result = []
    for city_id in city_find:
        city = await City.get_city(id=city_id)
        cities_result.append(city)

    city_names = [city.city for city in cities_result]
    city_ids = [city.id for city in cities_result]

    msg = await message.answer(
        text=f"📍 **Результаты поиска по: {city_input}**\n\n"
             f"Выберите город или напишите его текстом\n\n",
        reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
                                    btn_next=True, btn_back=True, 
                                    btn_next_name='Отменить результаты поиска'),
        parse_mode='Markdown'
    )
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_choose_city)
async def choose_city_end_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Завершение выбора города для исполнителя"""
    logger.debug(f'choose_city_end_worker...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    new_city_id = int(callback.data.split('_')[1])

    # Получаем название нового города
    new_city = await City.get_city(id=new_city_id)
    new_city_name = new_city.city if new_city else f"Город {new_city_id}"

    # Получаем название старого города
    old_city_id = worker.city_id[0]
    old_city = await City.get_city(id=old_city_id)
    old_city_name = old_city.city if old_city else f"Город {old_city_id}"

    # Меняем основной город
    worker.city_id[0] = new_city_id

    # Если старый город был в списке, перемещаем его на второе место
    if len(worker.city_id) > 1 and old_city_id in worker.city_id[1:]:
        worker.city_id.remove(old_city_id)
        worker.city_id.insert(1, old_city_id)

    await worker.update_city(worker.city_id)

    text = f"✅ **Основной город изменен**\n\n"
    text += f"📍 **Новый основной город:** {new_city_name}\n"
    text += f"📍 **Предыдущий город:** {old_city_name}\n\n"
    text += "Изменения вступят в силу немедленно."

    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_btn(),
        parse_mode='Markdown'
    )
    await state.set_state(WorkStates.worker_menu)


@router.callback_query(lambda c: c.data.startswith('set_main_city_'))
async def set_main_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Установка нового основного города"""
    logger.debug(f'set_main_city...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    new_city_id = int(callback.data.split('_')[-1])
    
    # Проверяем, что город доступен исполнителю
    available_city_ids = list(worker.city_id)
    active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in active_subscriptions:
        available_city_ids.extend(subscription.city_ids)
    
    if new_city_id not in available_city_ids:
        await callback.answer("❌ Этот город недоступен", show_alert=True)
        return
    
    # Меняем основной город
    old_city_id = worker.city_id[0]
    worker.city_id[0] = new_city_id
    
    # Если старый город был в списке, перемещаем его на второе место
    if len(worker.city_id) > 1 and old_city_id in worker.city_id[1:]:
        worker.city_id.remove(old_city_id)
        worker.city_id.insert(1, old_city_id)
    
    await worker.update_city(worker.city_id)
    
    # Получаем названия городов для уведомления
    all_cities = await City.get_all()
    cities_dict = {city.id: city.city for city in all_cities}
    
    old_city_name = cities_dict.get(old_city_id, f"Город {old_city_id}")
    new_city_name = cities_dict.get(new_city_id, f"Город {new_city_id}")
    
    text = f"✅ **Основной город изменен**\n\n"
    text += f"📍 **Новый основной город:** {new_city_name}\n"
    text += f"📍 **Предыдущий город:** {old_city_name}\n\n"
    text += "Изменения вступят в силу немедленно."
    
    await callback.message.edit_text(
        text=text,
        reply_markup=kbc.menu_btn(),
        parse_mode='Markdown'
    )


@router.callback_query(F.data == "worker_my_cities", WorkStates.worker_menu)
async def worker_my_cities(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'worker_my_cities...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    
    text = "🏙️ **Мои города**\n\n"
    
    # Получаем все города одним запросом для оптимизации
    all_cities = await City.get_all()
    cities_dict = {city.id: city.city for city in all_cities}
    
    # Показываем основной город (оптимизировано)
    main_city_names = [cities_dict.get(city_id, f"Город {city_id}") for city_id in worker.city_id]
    
    text += f"📍 **Основной город:** {', '.join(main_city_names)}\n\n"
    
    # Проверяем незавершенные подписки
    incomplete_subscriptions = []
    for subscription in active_subscriptions:
        prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
        purchased_cities = prices.get(subscription.price, 1)
        if len(subscription.city_ids) < purchased_cities:
            incomplete_subscriptions.append(subscription)
    
    # Показываем активные подписки
    if active_subscriptions:
        text += "🏷️ **Активные подписки на города:**\n\n"
        for subscription in active_subscriptions:
            # Вычисляем количество купленных городов из цены
            prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
            total_count = prices.get(subscription.price, 1)
            selected_count = len(subscription.city_ids)
            remaining = total_count - selected_count
            
            # Получаем названия уже выбранных городов (оптимизировано)
            selected_city_names = [cities_dict.get(city_id, f"Город {city_id}") for city_id in subscription.city_ids]
            
            # Форматируем дату окончания
            end_date = datetime.strptime(subscription.subscription_end, '%Y-%m-%d').strftime('%d.%m.%Y')
            
            text += f"📦 **Подписка на {total_count} городов** (до {end_date}):\n"
            if selected_city_names:
                text += f"• Выбрано: {', '.join(selected_city_names)}\n"
            else:
                text += f"• Выбрано: 0 городов\n"
            
            if remaining > 0:
                text += f"• ⚠️ Осталось выбрать: {remaining} городов\n"
            else:
                text += f"• ✅ Все города выбраны\n"
            text += "\n"
    else:
        text += "📭 **У вас нет активных подписок на дополнительные города**\n\n"
    
    # Проверяем незавершенные подписки
    if incomplete_subscriptions:
        text += "⚠️ **У вас есть незавершенные подписки:**\n"
        for subscription in incomplete_subscriptions:
            prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
            total_count = prices.get(subscription.price, 1)
            selected_count = len(subscription.city_ids)
            remaining = total_count - selected_count
            text += f"• Осталось выбрать {remaining} из {total_count} городов\n"
        text += "\n"
    
    builder = InlineKeyboardBuilder()
    
    # Если есть незавершенные подписки, показываем кнопку для их завершения
    if incomplete_subscriptions:
        for subscription in incomplete_subscriptions:
            prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
            total_count = prices.get(subscription.price, 1)
            selected_count = len(subscription.city_ids)
            remaining = total_count - selected_count
            
            builder.add(kbc._inline(
                f"✅ Выбрать города ({remaining} осталось)", 
                f"continue_subscription_cities_{subscription.id}"
            ))
    
    builder.add(kbc._inline("◀️ Назад", "worker_change_city_menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@router.callback_query(lambda c: c.data.startswith('continue_subscription_cities_'))
async def continue_subscription_cities(callback: CallbackQuery, state: FSMContext) -> None:
    """Продолжение выбора городов для незавершенной подписки"""
    logger.debug(f'continue_subscription_cities...')
    
    subscription_id = int(callback.data.split('_')[3])
    
    # Получаем подписку
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    
    target_subscription = None
    for subscription in active_subscriptions:
        if subscription.id == subscription_id:
            target_subscription = subscription
            break
    
    if not target_subscription:
        await callback.answer("❌ Подписка не найдена", show_alert=True)
        return
    
    # Вычисляем количество купленных городов
    prices = {90: 1, 180: 2, 270: 3, 360: 4, 450: 5, 900: 10, 1800: 20}
    purchased_cities = prices.get(target_subscription.price, 1)
    remaining_cities = purchased_cities - len(target_subscription.city_ids)
    
    # Получаем все города из других активных подписок (кроме текущей)
    other_subscription_cities = []
    for subscription in active_subscriptions:
        if subscription.id != subscription_id:
            other_subscription_cities.extend(subscription.city_ids)
    
    # Сохраняем данные в состоянии
    await state.update_data(
        subscription_id=subscription_id,
        city_count=remaining_cities,  # Количество городов, которые еще нужно выбрать
        selected_cities=target_subscription.city_ids.copy(),  # Уже выбранные города в текущей подписке
        excluded_cities=other_subscription_cities  # Города из других подписок
    )
    
    # Переходим к выбору городов
    await state.set_state(WorkStates.worker_choose_subscription_cities)
    await choose_subscription_cities(callback, state)


# @router.message(F.text, WorkStates.worker_change_city)
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
                                    btn_next=True, btn_back=False, menu_btn=True,
                                    btn_next_name='Отменить результаты поиска'))
    await state.update_data(msg_id=msg.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


# @router.callback_query(lambda c: c.data.startswith('go_'), WorkStates.worker_change_city)
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


# @router.callback_query(lambda c: c.data.startswith('obj-id_'), WorkStates.worker_change_city)
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


# Функции обмена контактами удалены


# Функция buy_contact_handler полностью удалена


# Функция просмотра купленных контактов полностью удалена


# Функция меню покупки контактов полностью удалена


# Функция отклонения отклика удалена


# Функция обработки тарифов контактов полностью удалена


# Новые обработчики для системы покупки контактов

# Все функции обмена контактами полностью удалены


@router.callback_query(F.data == "worker_rank", WorkStates.worker_menu)
async def worker_rank(callback: CallbackQuery, state: FSMContext) -> None:
    """Отображение ранга исполнителя"""
    logger.debug(f'worker_rank...')
    kbc = KeyboardCollection()
    
    try:
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        # Получаем или создаем ранг исполнителя
        from app.data.database.models import WorkerRank
        rank = await WorkerRank.get_or_create_rank(worker.id)
        
        # Формируем текст с информацией о ранге
        text = f"🏆 **Ваш ранг: {rank.current_rank} {rank.get_rank_name()}**\n\n"
        text += f"📊 **Статистика:**\n"
        text += f"• Выполнено заказов в этом месяце: {rank.orders_this_month}\n"
        text += f"• Всего выполнено заказов: {rank.completed_orders_count}\n\n"
        
        # Добавляем информацию о всех рангах
        text += "📋 **Система рангов:**\n\n"
        
        for rank_type, rank_info in WorkerRank.RANK_TYPES.items():
            emoji = rank_info['emoji']
            name = rank_info['name']
            orders_required = rank_info['orders_required']
            work_types_limit = rank_info['work_types_limit']
            
            # Выделяем текущий ранг
            if rank_type == rank.rank_type:
                text += f"**{emoji} {name}** (ваш ранг) — выполнено {orders_required} заказов за месяц"
            else:
                text += f"{emoji} {name} — выполнено {orders_required} заказов за месяц"
            
            if work_types_limit is None:
                text += ", доступны все направления без ограничений.\n"
            else:
                text += f", можно выбрать до {work_types_limit} направлений.\n"
            
            text += "\n"
        
        # Кнопка назад
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("◀️ Назад", "worker_menu"))
        builder.adjust(1)
        
        await callback.message.edit_text(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in worker_rank: {e}")
        await callback.answer("❌ Ошибка при получении информации о ранге", show_alert=True)


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
