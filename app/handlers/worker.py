import os
import json
import config
import logging
import aiosqlite
import html

from datetime import timedelta, datetime, date
from typing import List
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery, Message, FSInputFile, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from app.data.database.models import (
    Customer, Worker, City, WorkerAndSubscription, WorkType, Banned, Abs, WorkersAndAbs, Admin,
    WorkerAndReport, WorkerAndBadResponse, WorkerCitySubscription, WorkerRank, WorkerStatus, ContactExchange
)
from app.keyboards import KeyboardCollection
from app.states import WorkStates, UserStates, BannedStates
from app.untils import help_defs, checks, yandex_ocr
from loaders import bot
from app.untils.checks import validate_worker_name

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()

# Кэш для оптимизации запросов к БД
_work_types_cache = None
_cache_timestamp = None
CACHE_DURATION = 300  # 5 минут


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


# Старый обработчик удален - регистрация теперь происходит в enter_worker_name


@router.callback_query(F.data == "registration_worker", UserStates.registration_end)
async def registration_worker_from_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для регистрации исполнителя из стартового меню"""
    logger.debug(f'registration_worker_from_start...')
    kbc = KeyboardCollection()

    # Переходим к выбору города для исполнителя
    await state.set_state(WorkStates.registration_enter_city)
    await choose_city_callback(callback, state)


@router.callback_query(F.data == "registration_worker")
async def registration_worker_from_customer(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для регистрации исполнителя когда пользователь уже заказчик"""
    logger.debug(f'registration_worker_from_customer...')

    # Проверяем, есть ли уже данные заказчика
    customer = await Customer.get_customer(tg_id=callback.message.chat.id)
    if customer:
        # Используем данные заказчика
        await state.set_state(WorkStates.registration_enter_city)
        await state.update_data(city_id=str(customer.city_id), username=str(customer.tg_name))
        await choose_city_callback(callback, state)
    else:
        # Если нет данных заказчика, переходим к обычной регистрации
        await state.set_state(WorkStates.registration_enter_city)
        await choose_city_callback(callback, state)


async def choose_city_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало выбора города для исполнителя через callback"""
    logger.debug(f'choose_city_callback...')
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
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )
    await state.update_data(msg_id=msg.message_id)


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

    msg = await callback.message.answer(
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
    # msg_id = int(state_data.get('msg_id'))

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
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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
        msg = await callback.message.answer(
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

    city_id = int(callback.data.split('_')[1])

    # Сохраняем выбранный город и переходим к вводу имени
    await state.update_data(city_id=city_id)
    await state.set_state(WorkStates.registration_enter_name)

    await callback.message.answer(
        text='Укажите ваше имя:'
    )


@router.message(F.text, WorkStates.registration_enter_name)
async def enter_worker_name(message: Message, state: FSMContext) -> None:
    """Обработка ввода имени исполнителя с валидацией и модерацией"""
    logger.debug(f'enter_worker_name...')

    kbc = KeyboardCollection()
    worker_name = message.text.strip()

    # Валидация имени
    is_valid, error_message = await validate_worker_name(worker_name)

    if not is_valid:
        await message.answer(error_message)
        return

    # Сохраняем имя и завершаем регистрацию
    await state.update_data(username=worker_name)

    state_data = await state.get_data()
    city_id = int(state_data.get('city_id'))

    registration_date = date.today().strftime("%d.%m.%Y")

    new_worker = Worker(tg_id=message.chat.id,
                        city_id=[city_id],
                        tg_name=message.from_user.username or message.from_user.first_name or "Пользователь",
                        profile_name=worker_name,
                        registration_data=registration_date,
                        stars=5)

    await new_worker.save()
    new_worker = await Worker.get_worker(tg_id=message.chat.id)

    # Проверяем, существует ли уже запись для этого исполнителя
    existing_subscription = await WorkerAndSubscription.get_by_worker(worker_id=new_worker.id)
    if not existing_subscription:
        new_worker_and_subscription = WorkerAndSubscription(worker_id=new_worker.id)
        await new_worker_and_subscription.save()

    # Отправляем имя на модерацию в админ-чат
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("❌ Удалить", f"admin_delete_worker_name_{new_worker.id}_{new_worker.tg_id}"))
        builder.adjust(1)

        admin_text = f"👤 **Новое имя исполнителя**\n\n"
        admin_text += f"ID: {new_worker.id}\n"
        admin_text += f"TG ID: {new_worker.tg_id}\n"
        admin_text += f"Имя: {worker_name}\n"
        admin_text += f"Город: {city_id}"

        await bot.send_message(
            chat_id=config.NAME_MODERATION_CHAT,
            text=admin_text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке имени на модерацию: {e}")

    # Показываем всплывающее окно с подтверждением
    await message.answer('✅ Вы успешно зарегистрированы!', show_alert=True)

    # Создаем специальную клавиатуру с кнопкой "Выбрать"
    choose_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выбрать", callback_data="choose_work_types")]
    ])

    await message.answer(
        text='Выберите направления работ.',
        reply_markup=choose_keyboard
    )
    await state.set_state(WorkStates.worker_choose_work_types)


@router.callback_query(F.data == "choose_work_types", WorkStates.worker_choose_work_types)
async def choose_work_types_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Выбрать' для перехода к выбору направлений"""
    logger.debug(f'choose_work_types_start...')

    kbc = KeyboardCollection()

    # Переходим к выбору направлений работ
    # Получаем все типы работ для отображения
    from app.data.database.models import WorkType
    work_types = await WorkType.get_all()

    msg = await callback.message.answer(
        text='🎯 Выберите направления работы',
        reply_markup=kbc.choose_work_types_improved(
            all_work_types=work_types,
            selected_ids=[],
            count_work_types=len(work_types),
            page=0,
            btn_back=False
        )
    )
    await state.update_data(msg_id=msg.message_id)


# Верификация убрана согласно ТЗ


async def show_worker_menu_for_callback(callback: CallbackQuery, state: FSMContext, user_worker: 'Worker') -> None:
    """Общая функция для отображения меню исполнителя (для CallbackQuery)"""
    kbc = KeyboardCollection()

    # Получаем подписку
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=user_worker.id)

    # Ранг
    worker_rank = await WorkerRank.get_or_create_rank(user_worker.id)
    rank_name = worker_rank.get_rank_name()
    rank_emoji = worker_rank.get_rank_emoji()

    # Активность
    activity_level = user_worker.activity_level if hasattr(user_worker, 'activity_level') else 100
    # Используем правильные цветные круги вместо огня
    if activity_level >= 74:
        activity_emoji = "🟢"
    elif activity_level >= 48:
        activity_emoji = "🟡"
    elif activity_level >= 9:
        activity_emoji = "🟠"
    else:
        activity_emoji = "🔴"

    # Статус (ИП/ООО/СЗ)
    worker_status_obj = await WorkerStatus.get_by_worker(user_worker.id)
    if worker_status_obj and (worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz):
        if worker_status_obj.has_ip:
            status_text = "ИП ✅"
        elif worker_status_obj.has_ooo:
            status_text = "ООО ✅"
        else:
            status_text = "Самозанятость ✅"
    else:
        status_text = "Статус не подтвержден ⚠️"

    # Город и купленные города
    main_city = await City.get_city(id=user_worker.city_id[0])

    # Получаем ВСЕ подписки (активные и неактивные) для подсчета купленных городов
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute(
            'SELECT city_ids, active, purchased_city_count FROM worker_city_subscriptions WHERE worker_id = ?',
            [user_worker.id])
        all_subscriptions = await cursor.fetchall()
        await cursor.close()
    finally:
        await conn.close()

    # Подсчитываем купленные и выбранные города
    total_purchased_cities = 1  # Основной город
    total_selected_cities = 1  # Основной город

    for sub_data in all_subscriptions:
        city_ids_str = sub_data[0]
        is_active = bool(sub_data[1])
        purchased_count = sub_data[2] if sub_data[2] is not None else 1  # Используем purchased_city_count из БД

        # Определяем КУПЛЕННОЕ количество городов
        total_purchased_cities += purchased_count

        # Определяем ВЫБРАННОЕ количество городов
        if city_ids_str:
            selected_count = len(city_ids_str.split('|'))
            if is_active:
                total_selected_cities += selected_count

    if total_selected_cities == 1:
        city_text = f"Ваш город: {main_city.city}"
    else:
        additional = total_selected_cities - 1
        city_text = f"Ваш город: {main_city.city} +{additional} {'город' if additional == 1 else 'города' if additional < 5 else 'городов'}"

    # Количество контактов
    contacts_purchased = await ContactExchange.count_by_worker(user_worker.id)

    # Рейтинг
    if user_worker.count_ratings > 0:
        rating = round(user_worker.stars / user_worker.count_ratings, 1)
        rating_text = f"Рейтинг: {rating} ⭐ ({user_worker.count_ratings} {'оценка' if user_worker.count_ratings == 1 else 'оценки' if user_worker.count_ratings < 5 else 'оценок'})"
    else:
        rating_text = f"Рейтинг: 0 ⭐ (0 оценок)"

    # Формируем текст профиля
    text = f"**Ваш профиль**\n\n"
    text += f"ID: {user_worker.id} {user_worker.profile_name or user_worker.tg_name}\n"
    text += f"{rating_text}\n"
    text += f"Ранг: {rank_name} {rank_emoji}\n"
    text += f"Активность: {activity_level} {activity_emoji}\n"
    text += f"{status_text}\n"
    text += f"{city_text}\n\n"
    text += f"Количество контактов: {contacts_purchased}\n"

    # Если купил больше городов, чем выбрал - показываем "не выбрано"
    if total_purchased_cities > total_selected_cities:
        not_selected = total_purchased_cities - total_selected_cities
        text += f"Количество городов: {total_selected_cities} (не выбрано: {not_selected})\n"
    else:
        text += f"Количество городов: {total_selected_cities}\n"

    text += f"Выполненных заказов: {user_worker.order_count}\n"
    text += f"Зарегистрирован: {user_worker.registration_data}"

    # Выбор направлений доступен, если нет направлений или есть безлимит ('0')
    is_unlimited = (not worker_sub.work_type_ids or
                    (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
    choose_works = is_unlimited

    profile_name = True if (user_worker.profile_name or user_worker.tg_name) else False

    # has_status уже определен выше при формировании текста статуса
    has_status = False
    if worker_status_obj:
        has_status = worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz

    if user_worker.profile_photo:
        await callback.message.answer_photo(
            photo=FSInputFile(user_worker.profile_photo),
            caption=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )
    else:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )

    await state.set_state(WorkStates.worker_menu)


async def show_worker_menu_for_message(message: Message, state: FSMContext, user_worker: 'Worker') -> None:
    """Общая функция для отображения меню исполнителя (для Message)"""
    kbc = KeyboardCollection()

    # Получаем данные для профиля
    from app.data.database.models import WorkerRank, WorkerStatus, ContactExchange, WorkerCitySubscription
    import aiosqlite

    # Получаем подписку
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=user_worker.id)

    # Ранг
    worker_rank = await WorkerRank.get_or_create_rank(user_worker.id)
    rank_name = worker_rank.get_rank_name()
    rank_emoji = worker_rank.get_rank_emoji()

    # Активность
    activity_level = user_worker.activity_level if hasattr(user_worker, 'activity_level') else 100
    # Используем правильные цветные круги вместо огня
    if activity_level >= 74:
        activity_emoji = "🟢"
    elif activity_level >= 48:
        activity_emoji = "🟡"
    elif activity_level >= 9:
        activity_emoji = "🟠"
    else:
        activity_emoji = "🔴"

    # Статус (ИП/ООО/СЗ)
    worker_status_obj = await WorkerStatus.get_by_worker(user_worker.id)
    if worker_status_obj and (worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz):
        if worker_status_obj.has_ip:
            status_text = "ИП ✅"
        elif worker_status_obj.has_ooo:
            status_text = "ООО ✅"
        else:
            status_text = "Самозанятость ✅"
    else:
        status_text = "Статус не подтвержден ⚠️"

    # Город и купленные города
    main_city = await City.get_city(id=user_worker.city_id[0])

    # Получаем ВСЕ подписки (активные и неактивные) для подсчета купленных городов
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute(
            'SELECT city_ids, active, purchased_city_count FROM worker_city_subscriptions WHERE worker_id = ?',
            [user_worker.id])
        all_subscriptions = await cursor.fetchall()
        await cursor.close()
    finally:
        await conn.close()

    # Подсчитываем купленные и выбранные города
    total_purchased_cities = 1  # Основной город
    total_selected_cities = 1  # Основной город

    for sub_data in all_subscriptions:
        city_ids_str = sub_data[0]
        is_active = bool(sub_data[1])
        purchased_count = sub_data[2] if sub_data[2] is not None else 1  # Используем purchased_city_count из БД

        # Определяем КУПЛЕННОЕ количество городов
        total_purchased_cities += purchased_count

        # Определяем ВЫБРАННОЕ количество городов
        if city_ids_str:
            selected_count = len(city_ids_str.split('|'))
            if is_active:
                total_selected_cities += selected_count

    if total_selected_cities == 1:
        city_text = f"Ваш город: {main_city.city}"
    else:
        additional = total_selected_cities - 1
        city_text = f"Ваш город: {main_city.city} +{additional} {'город' if additional == 1 else 'города' if additional < 5 else 'городов'}"

    # Количество контактов
    contacts_purchased = await ContactExchange.count_by_worker(user_worker.id)

    # Рейтинг
    if user_worker.count_ratings > 0:
        rating = round(user_worker.stars / user_worker.count_ratings, 1)
        rating_text = f"Рейтинг: {rating} ⭐ ({user_worker.count_ratings} {'оценка' if user_worker.count_ratings == 1 else 'оценки' if user_worker.count_ratings < 5 else 'оценок'})"
    else:
        rating_text = f"Рейтинг: 0 ⭐ (0 оценок)"

    # Формируем текст профиля
    text = f"**Ваш профиль**\n\n"
    text += f"ID: {user_worker.id} {user_worker.profile_name or user_worker.tg_name}\n"
    text += f"{rating_text}\n"
    text += f"Ранг: {rank_name} {rank_emoji}\n"
    text += f"Активность: {activity_level} {activity_emoji}\n"
    text += f"{status_text}\n"
    text += f"{city_text}\n\n"
    text += f"Количество контактов: {contacts_purchased}\n"

    # Если купил больше городов, чем выбрал - показываем "не выбрано"
    if total_purchased_cities > total_selected_cities:
        not_selected = total_purchased_cities - total_selected_cities
        text += f"Количество городов: {total_selected_cities} (не выбрано: {not_selected})\n"
    else:
        text += f"Количество городов: {total_selected_cities}\n"

    text += f"Выполненных заказов: {user_worker.order_count}\n"
    text += f"Зарегистрирован: {user_worker.registration_data}"

    # Выбор направлений доступен, если нет направлений или есть безлимит ('0')
    is_unlimited = (not worker_sub.work_type_ids or
                    (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
    choose_works = is_unlimited

    profile_name = True if (user_worker.profile_name or user_worker.tg_name) else False

    # has_status уже определен выше при формировании текста статуса
    has_status = False
    if worker_status_obj:
        has_status = worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz

    if user_worker.profile_photo:
        await message.answer_photo(
            photo=FSInputFile(user_worker.profile_photo),
            caption=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )
    else:
        await message.answer(
            text=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=True,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )
    await state.set_state(WorkStates.worker_menu)


async def show_worker_menu(callback: CallbackQuery, state: FSMContext, user_worker: 'Worker') -> None:
    """Общая функция для отображения меню исполнителя (для CallbackQuery)"""
    kbc = KeyboardCollection()

    # Получаем данные для профиля

    # Получаем подписку
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=user_worker.id)

    # Ранг
    worker_rank = await WorkerRank.get_or_create_rank(user_worker.id)
    rank_name = worker_rank.get_rank_name()
    rank_emoji = worker_rank.get_rank_emoji()

    # Активность
    activity_level = user_worker.activity_level if hasattr(user_worker, 'activity_level') else 100
    # Используем правильные цветные круги вместо огня
    if activity_level >= 74:
        activity_emoji = "🟢"
    elif activity_level >= 48:
        activity_emoji = "🟡"
    elif activity_level >= 9:
        activity_emoji = "🟠"
    else:
        activity_emoji = "🔴"

    # Статус (ИП/ООО/СЗ)
    worker_status_obj = await WorkerStatus.get_by_worker(user_worker.id)
    if worker_status_obj and (worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz):
        if worker_status_obj.has_ip:
            status_text = "ИП ✅"
        elif worker_status_obj.has_ooo:
            status_text = "ООО ✅"
        else:
            status_text = "Самозанятость ✅"
    else:
        status_text = "Статус не подтвержден ⚠️"

    # Город и купленные города
    main_city = await City.get_city(id=user_worker.city_id[0])

    # Получаем ВСЕ подписки (активные и неактивные) для подсчета купленных городов
    conn = await aiosqlite.connect(database='app/data/database/database.db')
    try:
        cursor = await conn.execute(
            'SELECT city_ids, active, purchased_city_count FROM worker_city_subscriptions WHERE worker_id = ?',
            [user_worker.id])
        all_subscriptions = await cursor.fetchall()
        await cursor.close()
    finally:
        await conn.close()

    # Подсчитываем купленные и выбранные города
    total_purchased_cities = 1  # Основной город
    total_selected_cities = 1  # Основной город

    for sub_data in all_subscriptions:
        city_ids_str = sub_data[0]
        is_active = bool(sub_data[1])
        purchased_count = sub_data[2] if sub_data[2] is not None else 1  # Используем purchased_city_count из БД

        # Определяем КУПЛЕННОЕ количество городов
        total_purchased_cities += purchased_count

        # Определяем ВЫБРАННОЕ количество городов
        if city_ids_str:
            selected_count = len(city_ids_str.split('|'))
            if is_active:
                total_selected_cities += selected_count

    if total_selected_cities == 1:
        city_text = f"Ваш город: {main_city.city}"
    else:
        additional = total_selected_cities - 1
        city_text = f"Ваш город: {main_city.city} +{additional} {'город' if additional == 1 else 'города' if additional < 5 else 'городов'}"

    # Количество контактов
    contacts_purchased = await ContactExchange.count_by_worker(user_worker.id)

    # Рейтинг
    if user_worker.count_ratings > 0:
        rating = round(user_worker.stars / user_worker.count_ratings, 1)
        rating_text = f"Рейтинг: {rating} ⭐ ({user_worker.count_ratings} {'оценка' if user_worker.count_ratings == 1 else 'оценки' if user_worker.count_ratings < 5 else 'оценок'})"
    else:
        rating_text = f"Рейтинг: 0 ⭐ (0 оценок)"

    # Формируем текст профиля
    text = f"**Ваш профиль**\n\n"
    text += f"ID: {user_worker.id} {user_worker.profile_name or user_worker.tg_name}\n"
    text += f"{rating_text}\n"
    text += f"Ранг: {rank_name} {rank_emoji}\n"
    text += f"Активность: {activity_level} {activity_emoji}\n"
    text += f"{status_text}\n"
    text += f"{city_text}\n\n"
    text += f"Количество контактов: {contacts_purchased}\n"

    # Если купил больше городов, чем выбрал - показываем "не выбрано"
    if total_purchased_cities > total_selected_cities:
        not_selected = total_purchased_cities - total_selected_cities
        text += f"Количество городов: {total_selected_cities} (не выбрано: {not_selected})\n"
    else:
        text += f"Количество городов: {total_selected_cities}\n"

    text += f"Выполненных заказов: {user_worker.order_count}\n"
    text += f"Зарегистрирован: {user_worker.registration_data}"

    # Выбор направлений доступен, если нет направлений или есть безлимит ('0')
    is_unlimited = (not worker_sub.work_type_ids or
                    (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0'))
    choose_works = is_unlimited

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    profile_name = True if (user_worker.profile_name or user_worker.tg_name) else False

    # has_status уже определен выше при формировании текста статуса
    has_status = False
    if worker_status_obj:
        has_status = worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz

    if user_worker.profile_photo:
        await callback.message.answer_photo(
            photo=FSInputFile(user_worker.profile_photo),
            caption=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=False,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )
    else:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_worker_keyboard(
                confirmed=True,  # Верификация убрана
                choose_works=choose_works,
                individual_entrepreneur=user_worker.individual_entrepreneur,
                create_photo=True,
                create_name=profile_name,
                has_status=has_status
            ),
            parse_mode='Markdown'
        )
    await state.set_state(WorkStates.worker_menu)


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
        await (callback.message.answer(
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
        logger.debug(f'profile_name is empty: {user_worker.profile_name}')
        logger.debug(f'tg_name: {user_worker.tg_name}')
        # Если profile_name пустое, но tg_name есть, используем tg_name
        if user_worker.tg_name:
            await user_worker.update_profile_name(user_worker.tg_name)
            logger.debug(f'Updated profile_name to: {user_worker.tg_name}')
        else:
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

    # Используем общую функцию для отображения меню
    await show_worker_menu(callback, state, user_worker)


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

        await (callback.message.answer(
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
        logger.debug(f'profile_name is empty: {user_worker.profile_name}')
        logger.debug(f'tg_name: {user_worker.tg_name}')
        # Если profile_name пустое, но tg_name есть, используем tg_name
        if user_worker.tg_name:
            await user_worker.update_profile_name(user_worker.tg_name)
            logger.debug(f'Updated profile_name to: {user_worker.tg_name}')
        else:
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

    # Используем общую функцию для отображения меню
    await show_worker_menu(callback, state, user_worker)


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
        # Мигрируем существующие фото в правильную структуру папок
        logger.info(f"[PORTFOLIO_VIEW] Проверка миграции портфолио...")
        worker.portfolio_photo = help_defs.migrate_portfolio_to_user_folder(
            worker.portfolio_photo,
            callback.message.chat.id
        )
        # Обновляем портфолио в базе данных после миграции
        await worker.update_portfolio_photo(portfolio_photo=worker.portfolio_photo)

        photo_len = len(worker.portfolio_photo)
        logger.debug(f'my_portfolio...{photo_len}')

        # Получаем первый доступный ключ из словаря портфолио
        first_photo_key = min(worker.portfolio_photo.keys(), key=int)

        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo[first_photo_key]),
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

    try:
        photo_id = int(callback.data.split('_')[1])

        worker = await Worker.get_worker(tg_id=callback.message.chat.id)

        photo_len = len(worker.portfolio_photo)

        # Получаем отсортированные ключи из словаря портфолио
        sorted_keys = sorted(worker.portfolio_photo.keys(), key=int)

        # Корректируем photo_id для работы с реальными ключами
        if photo_id <= -1:
            photo_id = len(sorted_keys) - 1
        elif photo_id >= len(sorted_keys):
            photo_id = 0

        # Получаем реальный ключ по индексу
        real_key = sorted_keys[photo_id]

        try:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(worker.portfolio_photo[real_key])),
                reply_markup=kbc.my_portfolio(
                    photo_num=photo_id,
                    photo_len=photo_len,
                    new_photo=True if photo_len < 10 else False
                )
            )
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit media, sending new message: {e}")
            # Если не можем отредактировать, отправляем новое сообщение
            await callback.message.answer_photo(
                photo=FSInputFile(worker.portfolio_photo[real_key]),
                reply_markup=kbc.my_portfolio(
                    photo_num=photo_id,
                    photo_len=photo_len,
                    new_photo=True if photo_len < 10 else False
                )
            )

    except Exception as e:
        logger.error(f"Error in portfolio navigation: {e}")
        await callback.message.answer(text=f'❌ Произошла ошибка при просмотре портфолио: {str(e)}')


@router.callback_query(lambda c: c.data.startswith("delite-photo-portfolio_"), WorkStates.create_portfolio)
async def my_portfolio(callback: CallbackQuery) -> None:
    logger.debug(f'my_portfolio...')
    kbc = KeyboardCollection()

    try:
        photo_id = int(callback.data.split('_')[1])
        worker = await Worker.get_worker(tg_id=callback.message.chat.id)

        # Получаем отсортированные ключи из словаря портфолио
        sorted_keys = sorted(worker.portfolio_photo.keys(), key=int)

        # Получаем реальный ключ по индексу
        real_key = sorted_keys[photo_id]

        logger.info(f"[PORTFOLIO_DELETE] Удаляем фото: индекс={photo_id}, ключ={real_key}")
        logger.info(f"[PORTFOLIO_DELETE] Портфолио до удаления: {worker.portfolio_photo}")

        # Удаляем фото из словаря и получаем путь к файлу для удаления
        new_portfolio, removed_file_path = help_defs.remove_portfolio_photo(
            d=worker.portfolio_photo,
            removed_key=real_key
        )

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

        logger.info(f"[PORTFOLIO_DELETE] Портфолио после удаления: {new_portfolio}")
        logger.info(f"[PORTFOLIO_DELETE] Количество фото после удаления: {photo_len}")

        if photo_len == 0:
            await callback.message.answer(
                text='У вас пока нет фото в портфолио',
                reply_markup=kbc.my_portfolio()
            )
            return

        # Получаем отсортированные ключи из обновленного портфолио
        sorted_keys = sorted(new_portfolio.keys(), key=int)

        # Корректируем photo_id для отображения
        if photo_id <= -1:
            photo_id = len(sorted_keys) - 1
        elif photo_id >= len(sorted_keys):
            photo_id = 0

        # Получаем реальный ключ по индексу
        real_key = sorted_keys[photo_id]

        # Обновляем интерфейс
        try:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(new_portfolio[real_key])),
                reply_markup=kbc.my_portfolio(
                    photo_num=photo_id,
                    photo_len=photo_len,
                    new_photo=True if photo_len < 10 else False
                )
            )
        except TelegramBadRequest as e:
            logger.warning(f"Could not edit media after delete, sending new message: {e}")
            # Если не можем отредактировать, отправляем новое сообщение
            await callback.message.answer_photo(
                photo=FSInputFile(new_portfolio[real_key]),
                reply_markup=kbc.my_portfolio(
                    photo_num=photo_id,
                    photo_len=photo_len,
                    new_photo=True if photo_len < 10 else False
                )
            )

    except Exception as e:
        logger.error(f"Error in portfolio photo deletion: {e}")
        await callback.message.answer(text=f'❌ Произошла ошибка при удалении фото: {str(e)}')


@router.callback_query(F.data == "upload_photo", WorkStates.create_portfolio)
async def upload_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'upload_photo...')
    kbc = KeyboardCollection()

    try:
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

    except Exception as e:
        logger.error(f"Error in upload_photo: {e}")
        await callback.message.answer(text=f'❌ Произошла ошибка при инициализации загрузки фото: {str(e)}')


@router.message(F.photo, WorkStates.portfolio_upload_photo)
async def upload_photo_portfolio(message: Message, state: FSMContext) -> None:
    logger.debug(f'upload_photo_portfolio...')

    kbc = KeyboardCollection()

    try:
        import asyncio
        
        # Получаем текущее портфолио исполнителя для проверки общего лимита
        worker = await Worker.get_worker(tg_id=message.chat.id)
        existing_portfolio_count = len(worker.portfolio_photo) if worker.portfolio_photo else 0
        max_portfolio_photos = 10
        available_slots = max_portfolio_photos - existing_portfolio_count
        
        logger.info(f"[PORTFOLIO] Существующих фото в портфолио: {existing_portfolio_count}, доступно слотов: {available_slots}")
        
        # Загружаем данные состояния
        data = await state.get_data()
        album = data.get('album', [])
        processed_groups = data.get('processed_media_groups', [])

        # Проверяем, является ли это частью медиа-группы
        if message.media_group_id:
            media_group_id_str = str(message.media_group_id)
            
            # Атомарная проверка и блокировка: сначала проверяем, потом помечаем
            # Это критично для предотвращения параллельной обработки
            if media_group_id_str not in processed_groups:
                # Помечаем группу как обрабатываемую СРАЗУ (до добавления в альбом)
                processed_groups.append(media_group_id_str)
                await state.update_data(processed_media_groups=processed_groups)
                logger.info(f"[PORTFOLIO] Группа {media_group_id_str} заблокирована для обработки")
            else:
                # Группа уже обрабатывается - только добавляем в альбом и выходим
                album.append(message)
                await state.update_data(album=album)
                logger.debug(f"[PORTFOLIO] Фото из уже обрабатываемой группы {message.media_group_id} - добавлено в альбом, обработка пропущена")
                return
            
            # Добавляем первое сообщение из группы в альбом (после блокировки)
            album.append(message)
            await state.update_data(album=album)
            
            logger.info(f"[PORTFOLIO] Начинаю обработку медиа-группы {message.media_group_id}")
            
            # Ждем немного, чтобы получить все сообщения из группы
            await asyncio.sleep(2.0)  # Увеличиваем время ожидания до 2 секунд
            
            # Перезагружаем данные состояния после ожидания
            data = await state.get_data()
            album = data.get('album', [])
            
            # Получаем все сообщения из этой медиа-группы
            # Фильтруем по media_group_id
            media_group_messages = []
            for msg in album:
                if hasattr(msg, 'media_group_id') and str(msg.media_group_id) == media_group_id_str:
                    media_group_messages.append(msg)
            logger.info(f"[PORTFOLIO] Найдено {len(media_group_messages)} фото в медиа-группе {message.media_group_id}")
            
            # Проверяем общий лимит (существующие + новые)
            total_after_upload = existing_portfolio_count + len(album)
            if total_after_upload > max_portfolio_photos:
                # Ограничиваем количество новых фото до доступных слотов
                max_new_photos = available_slots
                if max_new_photos <= 0:
                    # Нет свободных слотов
                    msg_id = data.get('msg')
                    if msg_id:
                        try:
                            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                        except TelegramBadRequest:
                            pass
                    await message.answer(
                        text=f'❌ Достигнут лимит портфолио!\n\nУ вас уже {existing_portfolio_count} фото. Максимум 10 фото.\n\nУдалите старые фото, чтобы добавить новые.'
                    )
                    return
                
                # Обрезаем альбом до доступных слотов
                album = album[:max_new_photos]
                await state.update_data(album=album)
                msg_id = data.get('msg')
                if msg_id:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                    except TelegramBadRequest:
                        pass
                # Отправляем новое сообщение
                total_count = existing_portfolio_count + len(album)
                msg = await message.answer(
                    text=f'Загружено фото: {len(album)}/{available_slots}\n\nВсего в портфолио будет: {total_count}/10\n\nБольше фото загрузить нельзя\nНажмите, чтобы закончить загрузку',
                    reply_markup=kbc.done_btn()
                )
                await state.update_data(msg=msg.message_id)
                return
            
            # Обрабатываем все фото из медиа-группы (проверка OCR)
            invalid_photos_count = 0
            
            for photo_msg in media_group_messages:
                photo = photo_msg.photo[-1].file_id
                # Сохраняем временно для проверки OCR
                file_path_photo = await help_defs.save_photo(id=message.from_user.id)
                await bot.download(file=photo, destination=file_path_photo)
                
                text_photo = yandex_ocr.analyze_file(file_path_photo)
                if text_photo:
                    invalid_photos_count += 1
                    worker = await Worker.get_worker(tg_id=message.chat.id)
                    # Экранируем HTML символы в тексте OCR для безопасной отправки
                    escaped_text = html.escape(str(text_photo))
                    # Формируем базовый текст caption
                    base_text = f'ID #{message.chat.id}\nЗагружено фото портфолио с текстом\nТекст: '
                    max_text_length = 1024 - len(base_text) - 50  # Оставляем запас для "... (обрезано)"
                    if len(escaped_text) > max_text_length:
                        escaped_text = escaped_text[:max_text_length] + '... (обрезано)'
                    caption = base_text + escaped_text
                    await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG,
                                       caption=caption,
                                       photo=FSInputFile(file_path_photo),
                                       protect_content=False,
                                       reply_markup=kbc.delite_it_photo(worker_id=worker.id))
                    # Удаляем невалидное фото из альбома
                    album = [msg for msg in album if not (hasattr(msg, 'message_id') and msg.message_id == photo_msg.message_id)]
                    # Удаляем временный файл
                    help_defs.delete_file(file_path_photo)
                else:
                    # Фото валидное - удаляем временный файл
                    try:
                        if os.path.exists(file_path_photo):
                            help_defs.delete_file(file_path_photo)
                    except Exception as e:
                        logger.debug(f"[PORTFOLIO] Ошибка при удалении временного файла {file_path_photo}: {e}")
            
            await state.update_data(album=album)
            
            # Сообщаем об ошибках если есть
            if invalid_photos_count > 0:
                await message.answer(
                    text=f"❌ {invalid_photos_count} фото нарушают правила платформы (содержат текст) 🚫\n\nОстальные фото добавлены."
                )
            
            # Отправляем новое сообщение о загрузке (вместо редактирования)
            # Это нужно, чтобы сообщение было после всех загруженных фото
            album_count = len(album)
            msg_id = data.get('msg')
            
            # Удаляем старое сообщение, если оно есть
            if msg_id:
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                except TelegramBadRequest:
                    pass  # Сообщение уже удалено или недоступно
            
            # Отправляем новое сообщение (будет после всех фото)
            # Показываем сколько загружено новых и сколько всего будет
            total_count = existing_portfolio_count + album_count
            if existing_portfolio_count > 0:
                status_text = f'Загружено новых фото: {album_count}/{available_slots}\nВсего в портфолио будет: {total_count}/10\n\nНажмите, чтобы закончить загрузку'
            else:
                status_text = f'Загружено фото: {album_count}/10\n\nНажмите, чтобы закончить загрузку'
            
            msg = await message.answer(
                text=status_text,
                reply_markup=kbc.done_btn()
            )
            await state.update_data(msg=msg.message_id)
            logger.info(f"[PORTFOLIO] Отправлено новое сообщение о загрузке (медиа-группа): новых {album_count}, всего будет {total_count}/10")
            
            return

        # Если это одиночное фото (не медиа-группа)
        # Проверяем общий лимит (существующие + новые)
        total_after_upload = existing_portfolio_count + len(album) + 1  # +1 для текущего фото
        if total_after_upload > max_portfolio_photos:
            if available_slots <= 0:
                # Нет свободных слотов вообще
                msg_id = data.get('msg')
                if msg_id:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                    except TelegramBadRequest:
                        pass
                await message.answer(f'❌ Достигнут лимит портфолио!\n\nУ вас уже {existing_portfolio_count} фото. Максимум 10 фото.\n\nУдалите старые фото, чтобы добавить новые.')
                msg = await message.answer(
                    text=f'Всего в портфолио: {existing_portfolio_count}/10\n\nБольше фото загрузить нельзя\nНажмите, чтобы закончить загрузку',
                    reply_markup=kbc.done_btn()
                )
                await state.update_data(msg=msg.message_id)
                return
            else:
                # Есть свободные слоты, но не хватает для всех новых фото
                msg_id = data.get('msg')
                if msg_id:
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                    except TelegramBadRequest:
                        pass
                await message.answer(f'❌ Можно загрузить только {available_slots} фото (у вас уже {existing_portfolio_count} фото в портфолио)')
                msg = await message.answer(
                    text=f'Загружено фото: {len(album)}/{available_slots}\n\nВсего будет: {existing_portfolio_count + len(album)}/10\n\nНажмите, чтобы закончить загрузку',
                    reply_markup=kbc.done_btn()
                )
                await state.update_data(msg=msg.message_id)
                return

        # Проверяем фото на текст через Яндекс OCR
        # Используем временный файл для проверки OCR (будет удален после проверки)
        photo = message.photo[-1].file_id
        file_path_photo = await help_defs.save_photo(id=message.from_user.id)
        logger.debug(f"[PORTFOLIO] Временный файл для OCR проверки: {file_path_photo}")
        
        await bot.download(file=photo, destination=file_path_photo)

        text_photo = yandex_ocr.analyze_file(file_path_photo)
        logger.info(f'Portfolio OCR result: {text_photo}')

        if text_photo:
            # Если найден текст на фото - показываем всплывающее окно
            await message.answer(
                text="Фото нарушает правила платформы 🚫\n\nЗагрузите другое!",
                reply_markup=kbc.done_btn()
            )

            # Отправляем в лог админам
            worker = await Worker.get_worker(tg_id=message.chat.id)
            # Экранируем HTML символы в тексте OCR для безопасной отправки
            escaped_text = html.escape(str(text_photo))
            # Формируем базовый текст caption
            base_text = f'ID #{message.chat.id}\nЗагружено фото портфолио с текстом\nТекст: '
            max_text_length = 1024 - len(base_text) - 50  # Оставляем запас для "... (обрезано)"
            if len(escaped_text) > max_text_length:
                escaped_text = escaped_text[:max_text_length] + '... (обрезано)'
            caption = base_text + escaped_text
            await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG,
                                 caption=caption,
                                 photo=FSInputFile(file_path_photo),
                                 protect_content=False,
                                 reply_markup=kbc.delite_it_photo(worker_id=worker.id))
            # Удаляем временный файл (это нормально - это только для проверки OCR)
            logger.debug(f"[PORTFOLIO] Удаляю временный файл после проверки OCR (текст найден): {file_path_photo}")
            help_defs.delete_file(file_path_photo)
            return

        # Удаляем временный файл (OCR проверка прошла успешно)
        # Финальное сохранение будет в portfolio/ при завершении загрузки
        logger.debug(f"[PORTFOLIO] Удаляю временный файл после проверки OCR (текст не найден): {file_path_photo}")
        try:
            if os.path.exists(file_path_photo):
                help_defs.delete_file(file_path_photo)
        except Exception as e:
            logger.debug(f"[PORTFOLIO] Ошибка при удалении временного файла {file_path_photo}: {e}")

        # Если текст не найден - проверяем лимит перед добавлением
        # Проверяем, не превысит ли добавление этого фото общий лимит
        total_after_add = existing_portfolio_count + len(album) + 1  # +1 для текущего фото
        
        if total_after_add > max_portfolio_photos:
            # Превышен лимит - не добавляем это фото
            msg_id = data.get('msg')
            if msg_id:
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                except TelegramBadRequest:
                    pass
            await message.answer(
                text=f'❌ Лимит портфолио достигнут!\n\nУ вас уже {existing_portfolio_count} фото.\nПосле загрузки будет {existing_portfolio_count + len(album)} фото.\nМаксимум 10 фото.\n\nУдалите старые фото, чтобы добавить новые.',
                reply_markup=kbc.done_btn()
            )
            return
        
        # Добавляем фото в альбом (лимит не превышен)
        album.append(message)
        await state.update_data(album=album)

        # Отправляем новое сообщение о загрузке (вместо редактирования)
        # Это нужно, чтобы сообщение было после всех загруженных фото
        album_count = len(album)
        msg_id = data.get('msg')
        
        # Удаляем старое сообщение, если оно есть
        if msg_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            except TelegramBadRequest:
                pass  # Сообщение уже удалено или недоступно
        
        # Отправляем новое сообщение (будет после всех фото)
        # Показываем сколько загружено новых и сколько всего будет
        total_count = existing_portfolio_count + album_count
        if existing_portfolio_count > 0:
            status_text = f'Загружено новых фото: {album_count}/{available_slots}\nВсего в портфолио будет: {total_count}/10\n\nНажмите, чтобы закончить загрузку'
        else:
            status_text = f'Загружено фото: {album_count}/10\n\nНажмите, чтобы закончить загрузку'
        
        msg = await message.answer(
            text=status_text,
            reply_markup=kbc.done_btn()
        )
        await state.update_data(msg=msg.message_id)
        logger.info(f"[PORTFOLIO] Отправлено новое сообщение о загрузке: новых {album_count}, всего будет {total_count}/10")

    except Exception as e:
        logger.error(f"Error in upload_photo_portfolio: {e}")
        await message.answer(text=f'❌ Произошла ошибка при загрузке фото: {str(e)}')


@router.callback_query(F.data == 'skip_it_photo', WorkStates.portfolio_upload_photo)
async def create_abs_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'create_abs_with_photo_end...')

    kbc = KeyboardCollection()

    try:
        state_data = await state.get_data()
        msg = str(state_data.get('msg'))
        album = state_data.get('album', [])

        # Удаляем сообщение о статусе загрузки
        try:
            if msg and msg != 'None':
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=int(msg))
        except (TelegramBadRequest, ValueError):
            pass

        # Проверяем, есть ли фото для загрузки
        if not album:
            # Если альбом пустой, просто возвращаем пользователя в меню портфолио
            await state.clear()
            
            worker = await Worker.get_worker(tg_id=callback.message.chat.id)
            kbc = KeyboardCollection()
            
            if worker.portfolio_photo:
                # Показываем портфолио
                photo_len = len(worker.portfolio_photo)
                first_photo_key = min(worker.portfolio_photo.keys(), key=int)
                
                await callback.message.answer_photo(
                    photo=FSInputFile(worker.portfolio_photo[first_photo_key]),
                    reply_markup=kbc.my_portfolio(
                        photo_len=photo_len,
                        new_photo=True if photo_len < 10 else False
                    )
                )
            else:
                # Если портфолио пустое, показываем меню для загрузки
                await callback.message.answer(
                    text='У вас пока нет фото в портфолио',
                    reply_markup=kbc.my_portfolio()
                )
            
            await state.set_state(WorkStates.create_portfolio)
            return

        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg)
        except TelegramBadRequest:
            pass

        msg = await callback.message.answer(text='Подождите идет проверка')

        photos = {}
        worker = await Worker.get_worker(tg_id=callback.message.chat.id)

        # Мигрируем существующие фото в правильную структуру папок
        if worker.portfolio_photo:
            logger.info(f"[PORTFOLIO_UPLOAD] Миграция существующего портфолио...")
            worker.portfolio_photo = help_defs.migrate_portfolio_to_user_folder(
                worker.portfolio_photo,
                callback.message.chat.id
            )
            # Обновляем портфолио в базе данных после миграции
            await worker.update_portfolio_photo(portfolio_photo=worker.portfolio_photo)
            logger.info(f"[PORTFOLIO_UPLOAD] Миграция завершена: {worker.portfolio_photo}")

        # Проверяем общий лимит перед сохранением
        existing_count = len(worker.portfolio_photo) if worker.portfolio_photo else 0
        new_photos_count = len(album)
        total_after_save = existing_count + new_photos_count
        
        if total_after_save > 10:
            # Ограничиваем количество новых фото до доступных слотов
            available_slots = 10 - existing_count
            if available_slots <= 0:
                await callback.message.answer(
                    text=f'❌ Достигнут лимит портфолио!\n\nУ вас уже {existing_count} фото. Максимум 10 фото.\n\nУдалите старые фото, чтобы добавить новые.'
                )
                return
            
            # Обрезаем альбом до доступных слотов
            album = album[:available_slots]
            logger.info(f"[PORTFOLIO_UPLOAD] Альбом обрезан до {available_slots} фото из-за лимита")
        
        # Получаем максимальный ключ из существующего портфолио
        max_key = 0
        if worker.portfolio_photo:
            max_key = max(int(k) for k in worker.portfolio_photo.keys())
            logger.info(f"[PORTFOLIO_UPLOAD] Существующее портфолио: {worker.portfolio_photo}")
            logger.info(f"[PORTFOLIO_UPLOAD] Максимальный ключ: {max_key}")

        for i, obj in enumerate(album):
            if obj.photo:
                file_id = obj.photo[-1].file_id
            else:
                file_id = obj[obj.content_type].file_id

            # Используем последовательную нумерацию начиная с max_key + 1
            new_key = max_key + i + 1

            # Создаем правильную структуру папок для портфолио
            portfolio_dir, filename = await help_defs.save_portfolio_photo(
                user_id=callback.message.chat.id,
                photo_key=new_key
            )
            file_path_photo = os.path.join(portfolio_dir, filename)
            logger.info(f"[PORTFOLIO_UPLOAD] Сохраняю фото в portfolio: {file_path_photo}")
            
            await bot.download(file=file_id, destination=file_path_photo)
            logger.info(f"[PORTFOLIO_UPLOAD] Фото скачано в: {file_path_photo}")
            
            # Проверяем файл на наличие после скачивания
            if not os.path.exists(file_path_photo):
                logger.error(f"[PORTFOLIO_UPLOAD] ОШИБКА: Файл не найден после скачивания: {file_path_photo}")
            else:
                file_size = os.path.getsize(file_path_photo)
                logger.info(f"[PORTFOLIO_UPLOAD] Файл успешно сохранен: {file_path_photo}, размер: {file_size} байт")
            
            text_photo = yandex_ocr.analyze_file(file_path_photo)

            if text_photo:
                if await checks.fool_check(text=text_photo):
                    # Удаляем невалидный файл из portfolio/
                    logger.warning(f"[PORTFOLIO_UPLOAD] Удаляю невалидное фото из portfolio: {file_path_photo}")
                    help_defs.delete_file(file_path_photo)
                    try:
                        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
                    except TelegramBadRequest:
                        pass
                    await callback.message.answer(text='На фото содержится недопустимый текст!\nПопробуйте еще раз')
                    await state.clear()
                    await state.set_state(WorkStates.portfolio_upload_photo)
                    return

            # Файл валидный - сохраняем путь к нему
            photos[str(new_key)] = file_path_photo
            logger.info(f"[PORTFOLIO_UPLOAD] ✅ Добавлено фото в портфолио: ключ={new_key}, путь={file_path_photo}")

        # Объединяем портфолио правильно
        if worker.portfolio_photo:
            worker.portfolio_photo.update(photos)
            photo_len = len(worker.portfolio_photo)
        else:
            worker.portfolio_photo = photos
            photo_len = len(worker.portfolio_photo)

        logger.info(f"[PORTFOLIO_UPLOAD] Итоговое портфолио: {worker.portfolio_photo}")
        logger.info(f"[PORTFOLIO_UPLOAD] Количество фото: {photo_len}")

        await worker.update_portfolio_photo(portfolio_photo=worker.portfolio_photo)

        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
        except TelegramBadRequest:
            pass

        # Очищаем состояние после успешной загрузки
        await state.clear()

        # Получаем первый доступный ключ из словаря портфолио
        first_photo_key = min(worker.portfolio_photo.keys(), key=int)

        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo[first_photo_key]),
            reply_markup=kbc.my_portfolio(
                photo_len=photo_len,
                new_photo=True if photo_len < 10 else False
            )
        )
        await state.set_state(WorkStates.create_portfolio)

    except Exception as e:
        logger.error(f"[PORTFOLIO_UPLOAD] Ошибка при загрузке фото: {e}")
        await state.clear()
        await callback.message.answer(
            text='❌ Произошла ошибка при загрузке фото. Попробуйте еще раз.',
            reply_markup=kbc.my_portfolio()
        )
        await state.set_state(WorkStates.create_portfolio)


@router.callback_query(F.data == 'skip_it_photo', WorkStates.create_portfolio)
async def skip_it_photo_in_portfolio_view(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Завершить загрузку' при просмотре портфолио (после удаления фото админом)"""
    logger.debug(f'skip_it_photo_in_portfolio_view...')
    
    kbc = KeyboardCollection()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    
    if worker.portfolio_photo:
        # Показываем портфолио
        photo_len = len(worker.portfolio_photo)
        first_photo_key = min(worker.portfolio_photo.keys(), key=int)
        
        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo[first_photo_key]),
            reply_markup=kbc.my_portfolio(
                photo_len=photo_len,
                new_photo=True if photo_len < 10 else False
            )
        )
    else:
        # Если портфолио пустое, показываем меню для загрузки
        await callback.message.answer(
            text='У вас пока нет фото в портфолио',
            reply_markup=kbc.my_portfolio()
        )
    
    await state.set_state(WorkStates.create_portfolio)


@router.callback_query(F.data == 'skip_it_photo')
async def skip_it_photo_universal(callback: CallbackQuery, state: FSMContext) -> None:
    """Универсальный обработчик кнопки 'Завершить загрузку' для любого состояния (когда админ удаляет фото)"""
    logger.debug(f'skip_it_photo_universal (состояние: {await state.get_state()})...')
    
    # Проверяем, не обрабатывается ли это уже другими обработчиками с фильтрами состояния
    current_state = await state.get_state()
    
    # Если уже есть обработчики для конкретных состояний, пропускаем
    if current_state == WorkStates.portfolio_upload_photo.state or \
       current_state == WorkStates.create_portfolio.state:
        return  # Пусть обрабатывают специализированные обработчики
    
    kbc = KeyboardCollection()
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    
    if not worker:
        await callback.message.answer(text='❌ Исполнитель не найден')
        return
    
    # Показываем меню портфолио
    if worker.portfolio_photo:
        # Показываем портфолио
        photo_len = len(worker.portfolio_photo)
        first_photo_key = min(worker.portfolio_photo.keys(), key=int)
        
        await callback.message.answer_photo(
            photo=FSInputFile(worker.portfolio_photo[first_photo_key]),
            reply_markup=kbc.my_portfolio(
                photo_len=photo_len,
                new_photo=True if photo_len < 10 else False
            )
        )
        await state.set_state(WorkStates.create_portfolio)
    else:
        # Если портфолио пустое, сразу переводим в состояние загрузки фото
        await callback.message.answer(
            text='У вас пока нет фото в портфолио\n\nЗагрузите фото портфолио:',
            reply_markup=kbc.photo_work_keyboard(is_photo=False)
        )
        await state.set_state(WorkStates.portfolio_upload_photo)


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

    # Проверяем фото на текст через Яндекс OCR
    text_photo = yandex_ocr.analyze_file(file_path_photo)
    logger.info(f'OCR result: {text_photo}')

    if text_photo:
        # Если найден текст на фото - удаляем фото и показываем всплывающее окно
        await message.answer(
            text="Фото нарушает правила платформы 🚫\n\nЗагрузите другое!",
            reply_markup=kbc.photo_work_keyboard(is_photo=False)
        )

        # Отправляем в лог админам с кнопками управления
        # Экранируем HTML символы в тексте OCR для безопасной отправки
        escaped_text = html.escape(str(text_photo))
        # Формируем базовый текст caption
        base_text = f'ID #{message.chat.id}\nЗагружено фото профиля с текстом\nТекст: '
        max_text_length = 1024 - len(base_text) - 50  # Оставляем запас для "... (обрезано)"
        if len(escaped_text) > max_text_length:
            escaped_text = escaped_text[:max_text_length] + '... (обрезано)'
        caption = base_text + escaped_text
        await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG,
                             caption=caption,
                             photo=FSInputFile(file_path_photo),
                             protect_content=False,
                             reply_markup=kbc.delite_it_photo(worker_id=worker.id))
        return

    # Если текст не найден - сохраняем фото
    await worker.update_profile_photo(profile_photo=file_path_photo)

    await state.set_state(WorkStates.worker_menu)

    await message.answer(text='Фото профиля успешно загружено!', reply_markup=kbc.menu_btn())

    await bot.send_photo(chat_id=config.ADVERTISEMENT_LOG,
                         caption=f'ID #{message.chat.id}\nЗагружено новое фото профиля',
                         photo=FSInputFile(file_path_photo),
                         protect_content=False, reply_markup=kbc.delite_it_photo(worker_id=worker.id))


@router.callback_query(F.data == "add_worker_name", WorkStates.worker_menu)
async def add_worker_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Старый обработчик - перенаправляем на новый"""
    await worker_change_name_handler(callback, state)


@router.callback_query(F.data == "worker_change_name")
async def worker_change_name_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для изменения имени исполнителя"""
    logger.debug(f'worker_change_name_handler...')

    # Проверяем блокировку
    banned = await Banned.get_banned(tg_id=callback.from_user.id)
    if banned and banned.forever:
        await callback.answer("🚫 Ваш аккаунт заблокирован за повторные нарушения правил платформы!", show_alert=True)
        return

    kbc = KeyboardCollection()
    max_length = getattr(config, 'MAX_WORKER_NAME_LENGTH', 15)

    text = f'✏️ Укажите ваше имя\n\n'
    text += f'⚠️ Требования:\n'
    text += f'• Только русские буквы\n'
    text += f'• Без цифр и символов\n'
    text += f'• Максимум {max_length} символов'

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
async def process_worker_name(message: Message, state: FSMContext):
    """Обработка ввода имени с валидацией и модерацией"""
    logger.debug(f"process_worker_name")

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = state_data.get('msg_id')

    name = message.text.strip()

    # Валидация имени
    is_valid, error_message = await validate_worker_name(name)

    if not is_valid:
        msg = await message.answer(text=error_message)
        await state.update_data(msg_id=msg.message_id)
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except Exception:
            pass
        return

    worker = await Worker.get_worker(tg_id=message.chat.id)
    if not worker:
        await message.answer("❌ Исполнитель не найден")
        await state.set_state(WorkStates.worker_menu)
        return

    # Проверяем блокировку
    from app.data.database.models import Banned
    banned = await Banned.get_banned(tg_id=worker.tg_id)
    if banned and banned.forever:
        await message.answer("🚫 Ваш аккаунт заблокирован за повторные нарушения правил платформы!", show_alert=True)
        await state.set_state(WorkStates.worker_menu)
        return

    # Сохраняем имя
    await worker.update_profile_name(profile_name=name)

    # Отправляем имя на модерацию в админ-чат
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("❌ Удалить", f"admin_delete_worker_name_{worker.id}_{worker.tg_id}"))
        builder.adjust(1)

        admin_text = f"✏️ **Исполнитель изменил имя**\n\n"
        admin_text += f"ID: {worker.id}\n"
        admin_text += f"TG ID: {worker.tg_id}\n"
        admin_text += f"Новое имя: {name}\n"
        if worker.name_violations_count > 0:
            admin_text += f"⚠️ Нарушений имени: {worker.name_violations_count}"

        await bot.send_message(
            chat_id=config.NAME_MODERATION_CHAT,
            text=admin_text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке имени на модерацию: {e}")

    await state.set_state(WorkStates.worker_menu)

    await message.answer(text='✅ Ваше имя успешно изменено!\n\nИмя будет проверено модератором.',
                         reply_markup=kbc.menu_btn())
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    except:
        pass


# Старые обработчики ИП удалены - заменены на новую систему подтверждения статусов


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

    # Сортируем по ID (самые новые первыми, так как ID автоинкрементный)
    advertisements.sort(key=lambda x: x.id, reverse=True)

    bad_abs = []

    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    # Собираем ID объявлений, на которые исполнитель уже откликнулся или которые заблокированы
    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    # Убираем дубликаты и преобразуем в set для быстрого поиска
    bad_abs = set(bad_abs)
    print(f"[ABS_FILTER] Worker {worker.id} bad_abs: {bad_abs}")

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
            print(f"[ABS_FILTER] Skipping own ad: {advertisement.id}")
            continue
        if advertisement.id in bad_abs:
            print(f"[ABS_FILTER] Skipping already responded ad: {advertisement.id}")
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений - пропускаем
        if not worker_sub.work_type_ids:
            continue

        # Проверяем безлимит (work_type_ids == ['0']) или конкретный тип
        is_unlimited = (len(worker_sub.work_type_ids) == 1 and worker_sub.work_type_ids[0] == '0')

        if is_unlimited or (worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids):
            if advertisement.relevance:
                advertisements_final.append(advertisement)

    print(f"[ABS_FILTER] Total ads found: {len(advertisements)}, after filtering: {len(advertisements_final)}")

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

        # Парсим JSON строку photo_path для получения количества фото
        try:
            photo_dict = json.loads(abs_now.photo_path) if isinstance(abs_now.photo_path, str) else abs_now.photo_path
            count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
        except (json.JSONDecodeError, TypeError, AttributeError):
            count_photo = 1

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text,
                                          reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id,
                                                                                          btn_next=btn_next,
                                                                                          btn_back=btn_back,
                                                                                          abs_list_id=0,
                                                                                          count_photo=count_photo,
                                                                                          photo_num=0))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']), caption=text,
                                            reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id,
                                                                                            btn_next=btn_next,
                                                                                            btn_back=btn_back,
                                                                                            abs_list_id=0,
                                                                                            count_photo=count_photo,
                                                                                            photo_num=0))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text,
                                  reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next,
                                                                                  btn_back=btn_back, abs_list_id=0))


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
    advertisements.sort(key=lambda x: x.id, reverse=True)

    # Получаем списки скрытых объявлений и жалоб
    from app.data.database.models import WorkerAndReport, WorkerAndBadResponse
    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    # Собираем ID объявлений, которые не должны показываться
    bad_abs = []
    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    # Убираем дубликаты и преобразуем в set для быстрого поиска
    bad_abs = set(bad_abs)
    print(f"[ABS_FILTER_NAV] Worker {worker.id} bad_abs: {bad_abs}")

    advertisements_final = []

    if not advertisements:
        await callback.message.answer(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            print(f"[ABS_FILTER_NAV] Skipping own ad: {advertisement.id}")
            continue
        if advertisement.id in bad_abs:
            print(f"[ABS_FILTER_NAV] Skipping hidden/responded ad: {advertisement.id}")
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids:
            if advertisement.relevance:
                advertisements_final.append(advertisement)

    if not advertisements_final or abs_list_id >= len(advertisements_final):
        await callback.message.answer(text='Объявление не найдено', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    advertisement_now = advertisements_final[abs_list_id]

    btn_next = True if (len(advertisements_final) - 1 > abs_list_id) else False
    btn_back = True if abs_list_id > 0 else False

    if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement_now.id):
        btn_apply = False
        # report_btn удален - теперь используется единая система report_ad
    else:
        btn_apply = True
        # report_btn удален - теперь используется единая система report_ad

    await advertisement_now.update(views=1)

    text = help_defs.read_text_file(advertisement_now.text_path)
    text = f'Объявление {advertisement_now.id}\n\n' + text

    # Парсим JSON строку photo_path для получения количества фото
    import json
    try:
        photo_dict = json.loads(advertisement_now.photo_path) if isinstance(advertisement_now.photo_path,
                                                                            str) else advertisement_now.photo_path
        count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
    except (json.JSONDecodeError, TypeError, AttributeError):
        count_photo = 1

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
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
            else:
                await callback.message.answer_photo(
                    photo=FSInputFile(advertisement_now.photo_path['0']),
                    caption=text,
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
        else:
            await callback.message.answer(
                text=text,
                reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                btn_back=btn_back, abs_list_id=abs_list_id,
                                                                count_photo=count_photo, photo_num=0)
            )
        return

    # Если тип контента одинаковый - редактируем (с безопасным fallback)
    if has_photo_in_ad and has_photo_in_msg:
        try:
            if 'https' in advertisement_now.photo_path['0']:
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=advertisement_now.photo_path['0'],
                        caption=text),
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
            else:
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=FSInputFile(advertisement_now.photo_path['0']),
                        caption=text),
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
        except TelegramBadRequest:
            # Сообщение уже недоступно для редактирования — отправляем новое
            if 'https' in advertisement_now.photo_path['0']:
                await callback.message.answer_photo(
                    photo=advertisement_now.photo_path['0'],
                    caption=text,
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
            else:
                await callback.message.answer_photo(
                    photo=FSInputFile(advertisement_now.photo_path['0']),
                    caption=text,
                    reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                                    btn_back=btn_back, abs_list_id=abs_list_id,
                                                                    count_photo=count_photo, photo_num=0)
                )
    else:
        # Текст к тексту
        await callback.message.answer(
            text=text,
            reply_markup=kbc.advertisement_response_buttons(abs_id=advertisement_now.id, btn_next=btn_next,
                                                            btn_back=btn_back, abs_list_id=abs_list_id,
                                                            count_photo=count_photo, photo_num=0)
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
    advertisements.sort(key=lambda x: x.id, reverse=True)

    advertisements_final = []

    if not advertisements:
        await callback.message.answer(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        # Проверяем, не откликался ли уже исполнитель на это объявление
        if await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker.id, abs_id=advertisement.id):
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and advertisement.work_type_id in worker_sub.work_type_ids:
            advertisements_final.append(advertisement)

    if not advertisements_final:
        await callback.message.answer(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
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

    # Парсим JSON строку photo_path для получения количества фото
    import json
    try:
        photo_dict = json.loads(abs_now.photo_path) if isinstance(abs_now.photo_path, str) else abs_now.photo_path
        count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
    except (json.JSONDecodeError, TypeError, AttributeError):
        count_photo = 1

    await abs_now.update(views=1)

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer_photo(photo=abs_now.photo_path['0'],
                                                caption=text,
                                                reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id,
                                                                                                btn_next=btn_next,
                                                                                                btn_back=btn_back,
                                                                                                abs_list_id=abs_list_id,
                                                                                                count_photo=count_photo,
                                                                                                photo_num=0))
            return

        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']),
                                            caption=text,
                                            reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id,
                                                                                            btn_next=btn_next,
                                                                                            btn_back=btn_back,
                                                                                            abs_list_id=abs_list_id,
                                                                                            count_photo=count_photo,
                                                                                            photo_num=0))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text,
                                  reply_markup=kbc.advertisement_response_buttons(abs_id=abs_now.id, btn_next=btn_next,
                                                                                  btn_back=btn_back,
                                                                                  abs_list_id=abs_list_id,
                                                                                  count_photo=count_photo, photo_num=0))


@router.callback_query(lambda c: c.data.startswith('go-to-next_'), WorkStates.worker_check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.info(f'check_abs...')
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
    advertisements.sort(key=lambda x: x.id, reverse=True)

    # Получаем списки скрытых объявлений и жалоб
    from app.data.database.models import WorkerAndReport, WorkerAndBadResponse
    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    # Собираем ID объявлений, которые не должны показываться
    bad_abs = []
    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    # Убираем дубликаты и преобразуем в set для быстрого поиска
    bad_abs = set(bad_abs)
    print(f"[ABS_FILTER_NEXT] Worker {worker.id} bad_abs: {bad_abs}")

    advertisements_final = []

    if not advertisements:
        await callback.message.answer(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            print(f"[ABS_FILTER_NEXT] Skipping own ad: {advertisement.id}")
            continue
        if advertisement.id in bad_abs:
            print(f"[ABS_FILTER_NEXT] Skipping hidden/responded ad: {advertisement.id}")
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений - пропускаем
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids:
            if advertisement.relevance:
                advertisements_final.append(advertisement)

    if not advertisements_final:
        await callback.message.answer(text='У вас в городе пока нет объявлений', reply_markup=kbc.menu())
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
        # report_btn удален - теперь используется единая система report_ad
    else:
        btn_apply = True
        # report_btn удален - теперь используется единая система report_ad

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
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=advertisement_now.id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                )
            )
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=callback.message.caption),
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=advertisement_now.id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                )
            )
        return


@router.callback_query(lambda c: c.data.startswith('go-to-photo-worker_'))
async def navigate_photo_worker(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик листания фотографий в объявлениях для исполнителей
    Работает как в разделе объявлений, так и в рассылке (когда abs_list_id == -1)
    """
    logger.debug(f'navigate_photo_worker...')
    kbc = KeyboardCollection()

    # Парсим данные: go-to-photo-worker_{photo_num}_{abs_id}_{abs_list_id}
    parts = callback.data.split('_')
    photo_num = int(parts[1])
    abs_id = int(parts[2])
    abs_list_id = int(parts[3])

    # Получаем объявление
    advertisement = await Abs.get_one(id=abs_id)
    if not advertisement:
        await callback.answer("Объявление не найдено", show_alert=True)
        return

    # Парсим JSON строку photo_path для получения количества фото
    import json
    try:
        photo_dict = json.loads(advertisement.photo_path) if isinstance(advertisement.photo_path,
                                                                        str) else advertisement.photo_path
        count_photo = len(photo_dict) if isinstance(photo_dict, dict) else 0
    except (json.JSONDecodeError, TypeError, AttributeError):
        count_photo = 1

    # Циклическая навигация
    if photo_num <= -1:
        photo_num = count_photo - 1
    elif photo_num >= count_photo:
        photo_num = 0

    # Получаем путь к фото
    photo_path = advertisement.photo_path[str(photo_num)]

    # Если abs_list_id == -1, значит это из рассылки - упрощенная логика
    if abs_list_id == -1:
        # Для рассылки не нужна навигация по объявлениям
        btn_next = False
        btn_back = False
        
        # Обновляем медиа (безопасно: если сообщение уже удалено, отправляем новое)
        try:
            if 'https' in photo_path:
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_path,
                        caption=callback.message.caption),
                    reply_markup=kbc.advertisement_response_buttons(
                        abs_id=abs_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        abs_list_id=abs_list_id,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
            else:
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=FSInputFile(photo_path),
                        caption=callback.message.caption),
                    reply_markup=kbc.advertisement_response_buttons(
                        abs_id=abs_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        abs_list_id=abs_list_id,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
        except TelegramBadRequest:
            if 'https' in photo_path:
                await callback.message.answer_photo(
                    photo=photo_path,
                    caption=callback.message.caption,
                    reply_markup=kbc.advertisement_response_buttons(
                        abs_id=abs_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        abs_list_id=abs_list_id,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
            else:
                await callback.message.answer_photo(
                    photo=FSInputFile(photo_path),
                    caption=callback.message.caption,
                    reply_markup=kbc.advertisement_response_buttons(
                        abs_id=abs_id,
                        btn_next=btn_next,
                        btn_back=btn_back,
                        abs_list_id=abs_list_id,
                        count_photo=count_photo,
                        photo_num=photo_num
                    )
                )
        return

    # Оригинальная логика для раздела объявлений
    # Определяем кнопки навигации для объявлений
    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    # Получаем все города исполнителя
    all_city_ids = list(worker.city_id)
    from app.data.database.models import WorkerCitySubscription
    city_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
    for subscription in city_subscriptions:
        all_city_ids.extend(subscription.city_ids)
    all_city_ids = list(set(all_city_ids))

    # Получаем все объявления для определения навигации
    advertisements = []
    for city_id in all_city_ids:
        advertisements_temp = await Abs.get_all_in_city(city_id=city_id)
        if advertisements_temp:
            advertisements += advertisements_temp

    advertisements.sort(key=lambda x: x.id, reverse=True)

    # Фильтруем объявления
    from app.data.database.models import WorkerAndReport, WorkerAndBadResponse
    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    bad_abs = []
    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    bad_abs = set(bad_abs)

    advertisements_final = []
    for ad in advertisements:
        customer = await Customer.get_customer(id=ad.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        if ad.id in bad_abs:
            continue
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and str(ad.work_type_id) in worker_sub.work_type_ids:
            if ad.relevance:
                advertisements_final.append(ad)

    # Определяем кнопки навигации
    btn_next = abs_list_id < len(advertisements_final) - 1
    btn_back = abs_list_id > 0

    # Обновляем медиа (безопасно: если сообщение уже удалено, отправляем новое)
    try:
        if 'https' in photo_path:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=photo_path,
                    caption=callback.message.caption),
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=abs_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    abs_list_id=abs_list_id,
                    count_photo=count_photo,
                    photo_num=photo_num
                )
            )
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=callback.message.caption),
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=abs_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    abs_list_id=abs_list_id,
                    count_photo=count_photo,
                    photo_num=photo_num
                )
            )
    except TelegramBadRequest:
        if 'https' in photo_path:
            await callback.message.answer_photo(
                photo=photo_path,
                caption=callback.message.caption,
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=abs_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    abs_list_id=abs_list_id,
                    count_photo=count_photo,
                    photo_num=photo_num
                )
            )
        else:
            await callback.message.answer_photo(
                photo=FSInputFile(photo_path),
                caption=callback.message.caption,
                reply_markup=kbc.advertisement_response_buttons(
                    abs_id=abs_id,
                    btn_next=btn_next,
                    btn_back=btn_back,
                    abs_list_id=abs_list_id,
                    count_photo=count_photo,
                    photo_num=photo_num
                )
            )


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


async def get_filtered_advertisements_for_worker(worker, worker_sub):
    """
    Получить отфильтрованный список объявлений для исполнителя
    Исключает: собственные объявления, скрытые, жалобы, уже откликнутые
    """
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
    advertisements.sort(key=lambda x: x.id, reverse=True)

    # Получаем списки скрытых объявлений и жалоб
    from app.data.database.models import WorkerAndReport, WorkerAndBadResponse
    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    # Собираем ID объявлений, которые не должны показываться
    bad_abs = []
    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    # Убираем дубликаты и преобразуем в set для быстрого поиска
    bad_abs = set(bad_abs)
    print(f"[ABS_FILTER] Worker {worker.id} bad_abs: {bad_abs}")

    advertisements_final = []

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            print(f"[ABS_FILTER] Skipping own ad: {advertisement.id}")
            continue
        if advertisement.id in bad_abs:
            print(f"[ABS_FILTER] Skipping hidden/responded ad: {advertisement.id}")
            continue
        # Проверяем, подходит ли объявление по типу работы
        # Если нет направлений и нет безлимитного доступа - пропускаем
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids:
            if advertisement.relevance:
                advertisements_final.append(advertisement)

    return advertisements_final


@router.callback_query(F.data == 'choose_work_types', WorkStates.worker_menu)
async def choose_work_types(callback: CallbackQuery, state: FSMContext):
    logger.debug(f'choose_work_types...')
    kbc = KeyboardCollection()

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    # subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется

    # ИЗМЕНЕНО: Убраны лимиты на изменения направлений
    # Исполнители могут менять направления без ограничений

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

    # ИЗМЕНЕНО: Убрана информация о лимитах изменений
    # Исполнители могут менять направления без ограничений

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

    msg = await callback.message.answer(
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

    # Сохраняем исходные направления для сравнения при выходе
    await state.update_data(original_work_types=selected_ids.copy())

    # Сохраняем msg_id для редактирования сообщения при выборе направлений
    await state.update_data(msg_id=msg.message_id)

    await state.set_state(WorkStates.worker_choose_work_types)
    # await state.update_data(subscription_id=str(subscription.id))  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
    # await state.update_data(count_work_types=str(subscription.count_work_types))  # ЗАКОММЕНТИРОВАНО: Используется ранг
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
    if not worker:
        await callback.answer("❌ Исполнитель не найден", show_alert=True)
        return
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

    # Проверяем, достигнут ли максимальный лимит направлений
    if work_types_limit is not None and len(current_ids) >= work_types_limit:
        # Достигнут максимальный лимит - сбрасываем pending_selection
        from app.data.database.models import WorkerWorkTypeChanges
        work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

        if work_type_changes.pending_selection:
            work_type_changes.pending_selection = False
            await work_type_changes.save()
            logger.info(
                f'[WORK_TYPES] Worker {worker.id}: pending_selection flag cleared (reached max limit: {len(current_ids)}/{work_types_limit})')

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

    # Получаем информацию о лимитах изменений
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerWorkTypeChanges
    work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

    # Получаем текущие выбранные направления
    current_ids = work_type_ids.split('|') if work_type_ids else []

    # Получаем информацию о лимитах ранга
    from app.data.database.models import WorkerRank
    rank = await WorkerRank.get_or_create_rank(worker.id)
    work_types_limit = rank.get_work_types_limit()

    # ИЗМЕНЕНО: Убрана проверка лимитов изменений
    # Исполнители могут удалять направления без ограничений

    # ИЗМЕНЕНО: Убрана проверка лимита ранга при удалении направлений
    # Исполнители могут удалять направления без ограничений

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


@router.callback_query(lambda c: c.data.startswith('removal_blocked_'), WorkStates.worker_choose_work_types)
async def removal_blocked_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для заблокированных кнопок удаления направлений"""
    logger.debug(f'removal_blocked_handler...')

    await callback.answer(
        "❌ Нельзя снимать направления! Вы можете только добавлять новые направления до максимального лимита вашего ранга.",
        show_alert=True
    )


@router.callback_query(F.data == 'clear_all', WorkStates.worker_choose_work_types)
async def clear_all_work_types(callback: CallbackQuery, state: FSMContext) -> None:
    """Очистить все выбранные направления"""
    logger.debug(f'clear_all_work_types...')
    kbc = KeyboardCollection()

    # ИЗМЕНЕНО: Убрана проверка лимитов изменений
    # Исполнители могут очищать направления без ограничений

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

    await callback.message.answer(
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


async def update_work_types_interface(callback: CallbackQuery, state: FSMContext, kbc: KeyboardCollection,
                                      page: int = 0) -> None:
    """Обновить интерфейс выбора направлений с пагинацией"""
    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))

    # Получаем ранг исполнителя для проверки лимитов
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerRank
    rank = await WorkerRank.get_or_create_rank(worker.id)
    work_types_limit = rank.get_work_types_limit()

    # Получаем информацию о лимитах изменений
    from app.data.database.models import WorkerWorkTypeChanges
    work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

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

    # ИЗМЕНЕНО: Убрана информация о лимитах изменений
    # Исполнители могут менять направления без ограничений

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

    # ИЗМЕНЕНО: Убрана проверка лимитов изменений и блокировка удаления
    # Исполнители могут удалять направления без ограничений
    removal_blocked = False

    # Редактируем сообщение вместо создания нового
    msg_id = state_data.get('msg_id')
    try:
        if msg_id:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=kbc.choose_work_types_improved(
                    all_work_types=work_types,
                    selected_ids=selected_ids,
                    count_work_types=available_count,
                    page=page,
                    btn_back=True,
                    name_btn_back='Сохранить',
                    removal_blocked=removal_blocked
                ),
                parse_mode='Markdown'
            )
        else:
            # Первый раз отправляем сообщение и сохраняем ID
            msg = await callback.message.answer(
                text=text,
                reply_markup=kbc.choose_work_types_improved(
                    all_work_types=work_types,
                    selected_ids=selected_ids,
                    count_work_types=available_count,
                    page=page,
                    btn_back=True,
                    name_btn_back='Сохранить',
                    removal_blocked=removal_blocked
                ),
                parse_mode='Markdown'
            )
            await state.update_data(msg_id=msg.message_id)
    except Exception as e:
        # Если не удалось отредактировать, отправляем новое сообщение
        logger.debug(f"Could not edit message: {e}")
        msg = await callback.message.answer(
            text=text,
            reply_markup=kbc.choose_work_types_improved(
                all_work_types=work_types,
                selected_ids=selected_ids,
                count_work_types=available_count,
                page=page,
                btn_back=True,
                name_btn_back='Сохранить',
                removal_blocked=removal_blocked
            ),
            parse_mode='Markdown'
        )
        await state.update_data(msg_id=msg.message_id)


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
        await callback.message.answer(
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
        await callback.message.answer(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    # subscription = await SubscriptionType.get_subscription_type(id=subscription_id)  # УДАЛЕНО: SubscriptionType больше не используется

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    # btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
    btn_back = True  # Всегда показываем кнопку назад

    await callback.message.answer(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)}",
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
        await callback.message.answer(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    # subscription = await SubscriptionType.get_subscription_type(id=subscription_id)  # УДАЛЕНО: SubscriptionType больше не используется

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    # btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
    btn_back = True  # Всегда показываем кнопку назад

    await callback.message.answer(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)}",
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
        await callback.message.answer(text=text, reply_markup=kbc.menu())
        await state.set_state(WorkStates.worker_menu)
        return

    work_type_id_list = [int(id) for id in work_type_id_list]

    new_work_types = []

    for work_type in work_types:
        if work_type.id not in work_type_id_list:
            new_work_types.append(work_type)

    # subscription = await SubscriptionType.get_subscription_type(id=subscription_id)  # УДАЛЕНО: SubscriptionType больше не используется

    names = [work_type.work_type for work_type in new_work_types]
    ids = [work_type.id for work_type in new_work_types]

    # btn_back = True if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else False  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
    btn_back = True  # Всегда показываем кнопку назад

    await callback.message.answer(
        text=f"Вам нужно выбрать направления!\nВыбрано {len(work_type_id_list)}",
        reply_markup=kbc.choose_type(ids=ids, names=names, btn_back=btn_back, name_btn_back='Назад')
    )


async def is_selection_not_change(original_ids: set, current_ids: set, pending_selection: bool) -> bool:
    """
    Определяет, было ли это ВЫБОРОМ или ИЗМЕНЕНИЕМ направлений.
    
    ВЫБОР (не считается изменением, возвращает True):
    - Если было 0 направлений (первый выбор)
    - Если только добавлялись направления без удаления (все старые есть + новые)
    
    ИЗМЕНЕНИЕ (считается изменением, возвращает False):
    - Если удалялись направления (даже одно)
    - Если заменялись направления
    - Если количество после < количества до
    """

    # Если было 0 - это выбор (первый раз)
    if len(original_ids) == 0:
        logger.info(f'[WORK_TYPES] Selection detected: first time selection (was 0)')
        return True  # ВЫБОР

    # Если только добавляли (все старые есть + новые)
    if original_ids.issubset(current_ids):
        added_count = len(current_ids) - len(original_ids)
        logger.info(f'[WORK_TYPES] Selection detected: only adding new work types (added {added_count})')
        return True  # ВЫБОР (добавление)

    # Во всех остальных случаях - изменение
    removed = original_ids - current_ids
    added = current_ids - original_ids
    logger.info(f'[WORK_TYPES] Change detected: removed {len(removed)}, added {len(added)}')
    return False  # ИЗМЕНЕНИЕ


@router.callback_query(F.data == 'back', WorkStates.worker_choose_work_types)
async def choose_work_types_end(callback: CallbackQuery, state: FSMContext) -> None:
    kbc = KeyboardCollection()
    logger.debug(f'choose_work_types_end...')

    state_data = await state.get_data()
    work_type_ids = str(state_data.get('work_type_ids', ''))
    original_work_types = set(state_data.get('original_work_types', []))

    # Обрабатываем выбранные направления
    work_type_id_list = work_type_ids.split('|') if work_type_ids else []
    work_type_id_list = [id for id in work_type_id_list if id]  # Убираем пустые строки

    worker = await Worker.get_worker(tg_id=callback.message.chat.id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    # Сохраняем выбранные направления в БД
    await worker_sub.update(work_type_ids=work_type_id_list)

    # Проверяем, были ли изменения
    current_work_types = set(work_type_id_list)

    if original_work_types != current_work_types:
        # Что-то изменилось - нужно определить, ВЫБОР или ИЗМЕНЕНИЕ
        from app.data.database.models import WorkerWorkTypeChanges
        work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

        logger.info(
            f'[WORK_TYPES] Worker {worker.id} work types changed. Original: {original_work_types}, Current: {current_work_types}')

        # Определяем тип действия
        was_selection = await is_selection_not_change(
            original_work_types,
            current_work_types,
            work_type_changes.pending_selection
        )

        if was_selection:
            # Это был ВЫБОР - не регистрируем изменение
            logger.info(f'[WORK_TYPES] Worker {worker.id}: SELECTION (not counted as change)')

            if work_type_changes.pending_selection:
                # Проверяем, выбрано ли максимальное количество направлений по рангу
                from app.data.database.models import WorkerRank
                rank = await WorkerRank.get_or_create_rank(worker.id)
                work_types_limit = rank.get_work_types_limit()

                current_count = len(current_work_types)

                # Сбрасываем pending_selection только если выбрано максимальное количество направлений по рангу
                should_reset = False

                if work_types_limit is None:
                    # Платина - без ограничений, НЕ сбрасываем pending_selection
                    should_reset = False
                else:
                    # Есть лимит - сбрасываем только если достигнут
                    should_reset = current_count >= work_types_limit

                if should_reset:
                    work_type_changes.pending_selection = False
                    await work_type_changes.save()
                    logger.info(
                        f'[WORK_TYPES] Worker {worker.id}: pending_selection flag cleared (reached max limit: {current_count}/{work_types_limit})')
                else:
                    logger.info(
                        f'[WORK_TYPES] Worker {worker.id}: pending_selection remains True (can select more: {current_count}/{work_types_limit})')

            await callback.answer(
                f"✅ Направления успешно выбраны!",
                show_alert=False
            )
        else:
            # Это было ИЗМЕНЕНИЕ - регистрируем
            logger.info(f'[WORK_TYPES] Worker {worker.id}: CHANGE (counted as change)')

            # При изменении проверяем, нужно ли сбрасывать pending_selection
            if work_type_changes.pending_selection:
                # Проверяем, достигнут ли максимальный лимит направлений по рангу
                from app.data.database.models import WorkerRank
                rank = await WorkerRank.get_or_create_rank(worker.id)
                work_types_limit = rank.get_work_types_limit()

                current_count = len(current_work_types)

                # Сбрасываем pending_selection только если достигнут максимальный лимит
                if work_types_limit is not None and current_count >= work_types_limit:
                    work_type_changes.pending_selection = False
                    await work_type_changes.save()
                    logger.info(
                        f'[WORK_TYPES] Worker {worker.id}: pending_selection flag cleared (change + reached max limit: {current_count}/{work_types_limit})')
                else:
                    logger.info(
                        f'[WORK_TYPES] Worker {worker.id}: pending_selection remains True (change but not reached max limit: {current_count}/{work_types_limit})')

            # ИЗМЕНЕНО: Убрана регистрация изменений и уведомления о лимитах
            # Исполнители могут менять направления без ограничений

            logger.info(f'[WORK_TYPES] Worker {worker.id} work types updated successfully')

            await callback.answer(
                "✅ Изменения сохранены!",
                show_alert=False
            )
    else:
        logger.info(f'[WORK_TYPES] Worker {worker.id} exited without changes')

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

    # pending_selection сбрасывается только при достижении максимального лимита направлений по рангу
    # При ручном завершении (кнопка "Сохранить") флаг НЕ сбрасывается

    await callback.message.answer(text, reply_markup=kbc.menu())
    await state.set_state(WorkStates.worker_menu)


# Функция откликов удалена - функционал переписывается с нуля


# Функция навигации по фото при отклике удалена


# Функция "Мои отклики" удалена


# Функция просмотра отклика удалена


# Функция apply-it_ полностью удалена


# Старая функция report_order удалена - теперь используется единая система report_ad


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

    # Безопасное редактирование
    try:
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_btn(),
            parse_mode='Markdown'
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
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

    # Получаем статус исполнителя
    from app.data.database.models import WorkerStatus
    worker_status_obj = await WorkerStatus.get_or_create(worker.id)

    text = "📋 **Подтверждение статуса исполнителя**\n\n"
    text += "Для повышения доверия заказчиков вы можете подтвердить наличие:\n\n"
    text += "✅ **ИП** (Индивидуального предпринимателя)\n"
    text += "✅ **ООО** (Общество с ограниченной ответственностью)\n"
    text += "✅ **СЗ** (Самозанятости)\n\n"
    text += "После подтверждения в вашем профиле появится соответствующая отметка — это увеличивает шансы получить заказ.\n\n"

    # Проверяем, есть ли уже подтвержденный статус
    has_any_status = worker_status_obj.has_ip or worker_status_obj.has_ooo or worker_status_obj.has_sz

    # Показываем текущий статус
    if worker_status_obj.has_ip:
        text += "**Ваш статус:**\n✅ ИП подтвержден\n"
    elif worker_status_obj.has_ooo:
        text += "**Ваш статус:**\n✅ ООО подтверждено\n"
    elif worker_status_obj.has_sz:
        text += "**Ваш статус:**\n✅ Самозанятость подтверждена\n"
    else:
        text += "⚠️ Статус не подтвержден\n"

    # Создаем кнопки
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    # Показываем кнопки выбора ТОЛЬКО если НЕТ подтвержденного статуса
    if not has_any_status:
        builder.add(kbc._inline("👤 ИП", "confirm_ip_status"))
        builder.add(kbc._inline("🏢 ООО", "confirm_ooo_status"))
        builder.add(kbc._inline("🏭 СЗ", "confirm_sz_status"))

    builder.add(kbc._inline("◀️ Назад", "worker_menu"))
    builder.adjust(1)

    # Безопасное редактирование
    try:
        await callback.message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    await state.set_state(WorkStates.worker_menu)


# ========== ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЯ СТАТУСОВ ==========

@router.callback_query(F.data == "confirm_ip_status", WorkStates.worker_menu)
async def confirm_ip_status(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос ОГРНИП для подтверждения ИП"""
    logger.debug(f'confirm_ip_status...')
    kbc = KeyboardCollection()

    # Проверяем, нет ли уже подтвержденного статуса
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerStatus
    worker_status = await WorkerStatus.get_or_create(worker.id)

    if worker_status.has_ip or worker_status.has_ooo or worker_status.has_sz:
        await callback.answer("❌ У вас уже есть подтвержденный статус", show_alert=True)
        return

    text = "👤 **Подтверждение ИП**\n\n"
    text += "Введите Ваш **ОГРНИП**\n\n"
    text += "💡 ОГРНИП — это 15-значный номер индивидуального предпринимателя"

    await state.set_state(WorkStates.individual_entrepreneur)

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.back_btn(),
        parse_mode='Markdown'
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == "confirm_ooo_status", WorkStates.worker_menu)
async def confirm_ooo_status(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос ОГРН для подтверждения ООО"""
    logger.debug(f'confirm_ooo_status...')
    kbc = KeyboardCollection()

    # Проверяем, нет ли уже подтвержденного статуса
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerStatus
    worker_status = await WorkerStatus.get_or_create(worker.id)

    if worker_status.has_ip or worker_status.has_ooo or worker_status.has_sz:
        await callback.answer("❌ У вас уже есть подтвержденный статус", show_alert=True)
        return

    text = "🏢 **Подтверждение ООО**\n\n"
    text += "Введите Ваш **ОГРН**\n\n"
    text += "💡 ОГРН — это 13-значный номер юридического лица"

    await state.set_state(WorkStates.confirm_ooo_status)

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.back_btn(),
        parse_mode='Markdown'
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == "confirm_sz_status", WorkStates.worker_menu)
async def confirm_sz_status(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос ИНН для подтверждения СЗ"""
    logger.debug(f'confirm_sz_status...')
    kbc = KeyboardCollection()

    # Проверяем, нет ли уже подтвержденного статуса
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    from app.data.database.models import WorkerStatus
    worker_status = await WorkerStatus.get_or_create(worker.id)

    if worker_status.has_ip or worker_status.has_ooo or worker_status.has_sz:
        await callback.answer("❌ У вас уже есть подтвержденный статус", show_alert=True)
        return

    text = "🏭 **Подтверждение Самозанятости**\n\n"
    text += "Введите Ваш **ИНН**\n\n"
    text += "💡 ИНН — это 12-значный номер налогоплательщика"

    await state.set_state(WorkStates.confirm_sz_status)

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.back_btn(),
        parse_mode='Markdown'
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(msg_id=msg.message_id)


# Обработчик ввода ОГРНИП (ИП) - обновляем существующий
@router.message(F.text, WorkStates.individual_entrepreneur)
async def process_ip_confirmation(message: Message, state: FSMContext) -> None:
    """Обработка подтверждения ИП"""
    logger.debug(f'process_ip_confirmation...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')

    ogrnip = message.text.strip()

    # Проверяем, что введены только цифры
    if not ogrnip.isdigit():
        await message.answer(
            text="❌ ОГРНИП должен содержать только цифры!\n\n"
                 "Пожалуйста, введите номер без букв и символов.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем длину ОГРНИП (должен быть 15 цифр)
    if len(ogrnip) != 15:
        await message.answer(
            text="❌ ОГРНИП должен состоять из 15 цифр!\n\n"
                 f"Вы ввели {len(ogrnip)} цифр. Проверьте номер и попробуйте снова.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем ОГРНИП
    from app.untils import help_defs
    result = help_defs.check_ip_status_by_ogrnip(ogrnip=ogrnip)

    # if msg_id:
    #     try:
    #         await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    #     except Exception:
    #         pass

    await state.set_state(WorkStates.worker_menu)

    if result:
        # Сохраняем статус
        worker = await Worker.get_worker(tg_id=message.chat.id)
        from app.data.database.models import WorkerStatus
        from datetime import datetime
        worker_status = await WorkerStatus.get_or_create(worker.id)
        worker_status.has_ip = True
        worker_status.ip_number = ogrnip
        worker_status.last_status_check = datetime.now().isoformat()
        await worker_status.save()

        # Также обновляем старое поле для обратной совместимости
        await worker.update_individual_entrepreneur(individual_entrepreneur=True)

        await message.answer(
            text=f"✅ **Ваш статус ИП подтвержден!**\n\n{result}",
            reply_markup=kbc.menu(),
            parse_mode='Markdown'
        )
    else:
        await message.answer(
            text="❌ Введен неверный номер, повторите пожалуйста попытку...\n\n"
                 "Нажмите 'Статус' в меню, чтобы попробовать снова.",
            reply_markup=kbc.menu()
        )


# Обработчик ввода ОГРН (ООО)
@router.message(F.text, WorkStates.confirm_ooo_status)
async def process_ooo_confirmation(message: Message, state: FSMContext) -> None:
    """Обработка подтверждения ООО"""
    logger.debug(f'process_ooo_confirmation...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')

    ogrn = message.text.strip()

    # Проверяем, что введены только цифры
    if not ogrn.isdigit():
        await message.answer(
            text="❌ ОГРН должен содержать только цифры!\n\n"
                 "Пожалуйста, введите номер без букв и символов.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем длину ОГРН (должен быть 13 цифр)
    if len(ogrn) != 13:
        await message.answer(
            text="❌ ОГРН должен состоять из 13 цифр!\n\n"
                 f"Вы ввели {len(ogrn)} цифр. Проверьте номер и попробуйте снова.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем ОГРН
    from app.untils import help_defs
    result = help_defs.check_ooo(query=ogrn)

    # if msg_id:
    #     try:
    #         await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    #     except Exception:
    #         pass

    await state.set_state(WorkStates.worker_menu)

    if result == "error":
        await message.answer(
            text="⚠️ К сожалению произошла ошибка, повторите попытку пожалуйста позже...",
            reply_markup=kbc.menu()
        )
    elif result:
        # Сохраняем статус
        worker = await Worker.get_worker(tg_id=message.chat.id)
        from app.data.database.models import WorkerStatus
        from datetime import datetime
        worker_status = await WorkerStatus.get_or_create(worker.id)
        worker_status.has_ooo = True
        worker_status.ooo_number = ogrn
        worker_status.last_status_check = datetime.now().isoformat()
        await worker_status.save()

        await message.answer(
            text="✅ **Ваш статус ООО подтвержден!**",
            reply_markup=kbc.menu(),
            parse_mode='Markdown'
        )
    else:
        await message.answer(
            text="❌ Введен неверный номер, повторите пожалуйста попытку...\n\n"
                 "Нажмите 'Статус' в меню, чтобы попробовать снова.",
            reply_markup=kbc.menu()
        )


# Обработчик ввода ИНН (СЗ)
@router.message(F.text, WorkStates.confirm_sz_status)
async def process_sz_confirmation(message: Message, state: FSMContext) -> None:
    """Обработка подтверждения самозанятости"""
    logger.debug(f'process_sz_confirmation...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = state_data.get('msg_id')

    inn = message.text.strip()

    # Проверяем, что введены только цифры
    if not inn.isdigit():
        await message.answer(
            text="❌ ИНН должен содержать только цифры!\n\n"
                 "Пожалуйста, введите номер без букв и символов.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем длину ИНН (должен быть 12 цифр)
    if len(inn) != 12:
        await message.answer(
            text="❌ ИНН должен состоять из 12 цифр!\n\n"
                 f"Вы ввели {len(inn)} цифр. Проверьте номер и попробуйте снова.",
            reply_markup=kbc.back_btn()
        )
        return

    # Проверяем ИНН
    from app.untils import help_defs
    result = help_defs.check_npd(inn=inn)

    if msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except Exception:
            pass

    await state.set_state(WorkStates.worker_menu)

    if result == "error":
        await message.answer(
            text="⚠️ К сожалению произошла ошибка, повторите попытку пожалуйста позже...",
            reply_markup=kbc.menu()
        )
    elif result:
        # Сохраняем статус
        worker = await Worker.get_worker(tg_id=message.chat.id)
        from app.data.database.models import WorkerStatus
        from datetime import datetime
        worker_status = await WorkerStatus.get_or_create(worker.id)
        worker_status.has_sz = True
        worker_status.sz_number = inn
        worker_status.last_status_check = datetime.now().isoformat()
        await worker_status.save()

        await message.answer(
            text="✅ **Ваш статус Самозанятости подтвержден!**",
            reply_markup=kbc.menu(),
            parse_mode='Markdown'
        )
    else:
        await message.answer(
            text="❌ Введен неверный номер, повторите пожалуйста попытку...\n\n"
                 "Нажмите 'Статус' в меню, чтобы попробовать снова.",
            reply_markup=kbc.menu()
        )


# Обработчики кнопки "Назад" для всех статусов
@router.callback_query(F.data == "back", WorkStates.individual_entrepreneur)
async def back_from_ip_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из подтверждения ИП"""
    logger.debug(f'back_from_ip_confirmation...')

    # Удаляем сообщение с запросом ОГРНИП
    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')
    # if msg_id:
    #     try:
    #         await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
    #     except Exception:
    #         pass

    # Возвращаемся в меню статусов
    await state.set_state(WorkStates.worker_menu)
    await worker_status(callback, state)


@router.callback_query(F.data == "back", WorkStates.confirm_ooo_status)
async def back_from_ooo_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из подтверждения ООО"""
    logger.debug(f'back_from_ooo_confirmation...')

    # Удаляем сообщение с запросом ОГРН
    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')
    # if msg_id:
    #     try:
    #         await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
    #     except Exception:
    #         pass

    # Возвращаемся в меню статусов
    await state.set_state(WorkStates.worker_menu)
    await worker_status(callback, state)


@router.callback_query(F.data == "back", WorkStates.confirm_sz_status)
async def back_from_sz_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат из подтверждения СЗ"""
    logger.debug(f'back_from_sz_confirmation...')

    # Удаляем сообщение с запросом ИНН
    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')
    # if msg_id:
    #     try:
    #         await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
    #     except Exception:
    #         pass

    # Возвращаемся в меню статусов
    await state.set_state(WorkStates.worker_menu)
    await worker_status(callback, state)


# # ========== ОБРАБОТЧИКИ НАПРАВЛЕНИЙ РАБОТЫ ==========

# @router.callback_query(F.data == "choose_work_types", WorkStates.worker_menu)
# async def choose_work_types_handler(callback: CallbackQuery, state: FSMContext) -> None:
#     """Обработчик кнопки 'Мои направления'"""
#     logger.debug(f'choose_work_types_handler...')
#     kbc = KeyboardCollection()

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем запись об изменениях направлений
#     from app.data.database.models import WorkerWorkTypeChanges

#     # Создаем таблицу если её нет
#     await WorkerWorkTypeChanges.create_table_if_not_exists()

#     # Получаем или создаем запись для исполнителя
#     work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

#     # Проверяем, может ли исполнитель изменить направления
#     can_change, message = work_type_changes.can_change_work_types()

#     if not can_change:
#         # Показываем сообщение об ограничении
#         try:
#             await callback.message.answer(
#                 text=message + "\n\n💡 Вы сможете изменить направления после истечения периода ожидания.",
#                 reply_markup=kbc.menu_btn(),
#                 parse_mode='Markdown'
#             )
#         except Exception:
#             try:
#                 await callback.message.delete()
#             except Exception:
#                 pass
#             await callback.message.answer(
#                 text=message + "\n\n💡 Вы сможете изменить направления после истечения периода ожидания.",
#                 reply_markup=kbc.menu_btn(),
#                 parse_mode='Markdown'
#             )
#         return

#     # Получаем лимит направлений из ранга
#     from app.data.database.models import WorkerRank
#     worker_rank = await WorkerRank.get_or_create_rank(worker.id)
#     rank_work_types_limit = worker_rank.get_work_types_limit()

#     # Определяем лимит направлений
#     if worker_sub.unlimited_work_types:
#         count_work_types = 100  # Безлимит
#         limit_text = "неограниченно"
#     else:
#         # Используем лимит из ранга
#         count_work_types = rank_work_types_limit or 1
#         limit_text = f"{count_work_types} из 20"

#     # Получаем все направления
#     all_work_types = await WorkType.get_all()

#     # Получаем выбранные направления
#     selected_ids = worker_sub.work_type_ids if worker_sub.work_type_ids else []

#     # Сохраняем исходное состояние для проверки изменений при выходе
#     original_work_types = set(selected_ids) if selected_ids else set()

#     # Формируем текст
#     text = "🎯 **Мои направления работ**\n\n"
#     text += f"📊 Доступно направлений: {limit_text}\n"

#     # Показываем информацию о лимите изменений
#     if work_type_changes.changes_count > 0:
#         remaining = 3 - work_type_changes.changes_count
#         if remaining > 0:
#             text += f"⚙️ Изменений использовано: {work_type_changes.changes_count}/3 (осталось: {remaining})\n"
#         else:
#             text += f"⚠️ Изменений использовано: {work_type_changes.changes_count}/3 (лимит исчерпан)\n"

#     if message:  # Если есть сообщение об оставшихся изменениях
#         text += f"{message}\n"

#     text += f"\n"

#     if selected_ids:
#         text += f"**Выбрано:** {len(selected_ids)} направлений\n\n"
#         text += "Нажмите на направление, чтобы удалить его из списка.\n"
#         text += "Или выберите новое направление из списка доступных."
#     else:
#         text += "**У вас пока нет выбранных направлений.**\n\n"
#         text += "Выберите направления из списка ниже."

#     # Показываем клавиатуру с пагинацией
#     await state.set_state(WorkStates.worker_choose_work_types)
#     await state.update_data(page=0, original_work_types=list(original_work_types))

#     try:
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.choose_work_types_improved(
#                 all_work_types=all_work_types,
#                 selected_ids=selected_ids,
#                 count_work_types=count_work_types,
#                 page=0,
#                 btn_back=True,
#                 name_btn_back='◀️ Назад в меню'
#             ),
#             parse_mode='Markdown'
#         )
#     except Exception:
#         try:
#             await callback.message.delete()
#         except Exception:
#             pass
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.choose_work_types_improved(
#                 all_work_types=all_work_types,
#                 selected_ids=selected_ids,
#                 count_work_types=count_work_types,
#                 page=0,
#                 btn_back=True,
#                 name_btn_back='◀️ Назад в меню'
#             ),
#             parse_mode='Markdown'
#         )


# @router.callback_query(lambda c: c.data.startswith('add_work_type_'), WorkStates.worker_choose_work_types)
# async def add_work_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
#     """Добавить направление работы"""
#     logger.debug(f'add_work_type_handler...')
#     kbc = KeyboardCollection()

#     work_type_id = int(callback.data.split('_')[3])

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем лимит направлений из ранга
#     from app.data.database.models import WorkerRank
#     worker_rank = await WorkerRank.get_or_create_rank(worker.id)
#     rank_work_types_limit = worker_rank.get_work_types_limit()

#     # Определяем лимит направлений
#     if worker_sub.unlimited_work_types:
#         count_work_types = 100
#     else:
#         count_work_types = rank_work_types_limit or 1

#     # Получаем текущие выбранные направления
#     selected_ids = worker_sub.work_type_ids if worker_sub.work_type_ids else []

#     # Добавляем новое направление
#     if str(work_type_id) not in selected_ids:
#         selected_ids.append(str(work_type_id))

#         # Сохраняем в БД
#         await worker_sub.update_work_type_ids(work_type_ids=selected_ids)

#     # Обновляем отображение
#     all_work_types = await WorkType.get_all()
#     state_data = await state.get_data()
#     page = state_data.get('page', 0)

#     text = "🎯 **Мои направления работ**\n\n"
#     text += f"📊 Доступно направлений: {count_work_types if count_work_types < 100 else 'неограниченно'}\n"
#     text += f"**Выбрано:** {len(selected_ids)} направлений\n\n"
#     text += "✅ **Направление добавлено!**\n\n"
#     text += "Нажмите на направление, чтобы удалить его из списка."

#     try:
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.choose_work_types_improved(
#                 all_work_types=all_work_types,
#                 selected_ids=selected_ids,
#                 count_work_types=count_work_types,
#                 page=page,
#                 btn_back=True,
#                 name_btn_back='◀️ Назад в меню'
#             ),
#             parse_mode='Markdown'
#         )
#     except Exception:
#         await callback.answer("✅ Направление добавлено!")


# @router.callback_query(lambda c: c.data.startswith('remove_work_type_'), WorkStates.worker_choose_work_types)
# async def remove_work_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
#     """Удалить направление работы"""
#     logger.debug(f'remove_work_type_handler...')
#     kbc = KeyboardCollection()

#     work_type_id = int(callback.data.split('_')[3])

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем лимит направлений из ранга
#     from app.data.database.models import WorkerRank
#     worker_rank = await WorkerRank.get_or_create_rank(worker.id)
#     rank_work_types_limit = worker_rank.get_work_types_limit()

#     # Определяем лимит направлений
#     if worker_sub.unlimited_work_types:
#         count_work_types = 100
#     else:
#         count_work_types = rank_work_types_limit or 1

#     # Получаем текущие выбранные направления
#     selected_ids = worker_sub.work_type_ids if worker_sub.work_type_ids else []

#     # Удаляем направление
#     if str(work_type_id) in selected_ids:
#         selected_ids.remove(str(work_type_id))

#         # Сохраняем в БД
#         await worker_sub.update_work_type_ids(work_type_ids=selected_ids)

#     # Обновляем отображение
#     all_work_types = await WorkType.get_all()
#     state_data = await state.get_data()
#     page = state_data.get('page', 0)

#     text = "🎯 **Мои направления работ**\n\n"
#     text += f"📊 Доступно направлений: {count_work_types if count_work_types < 100 else 'неограниченно'}\n"

#     if selected_ids:
#         text += f"**Выбрано:** {len(selected_ids)} направлений\n\n"
#         text += "❌ **Направление удалено!**\n\n"
#         text += "Нажмите на направление, чтобы удалить его из списка."
#     else:
#         text += "**У вас нет выбранных направлений.**\n\n"
#         text += "Выберите направления из списка ниже."

#     try:
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.choose_work_types_improved(
#                 all_work_types=all_work_types,
#                 selected_ids=selected_ids,
#                 count_work_types=count_work_types,
#                 page=page,
#                 btn_back=True,
#                 name_btn_back='◀️ Назад в меню'
#             ),
#             parse_mode='Markdown'
#         )
#     except Exception:
#         await callback.answer("❌ Направление удалено!")


# @router.callback_query(lambda c: c.data.startswith('work_types_page_'), WorkStates.worker_choose_work_types)
# async def work_types_pagination_handler(callback: CallbackQuery, state: FSMContext) -> None:
#     """Пагинация по направлениям"""
#     logger.debug(f'work_types_pagination_handler...')
#     kbc = KeyboardCollection()

#     page = int(callback.data.split('_')[3])

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем лимит направлений из ранга
#     from app.data.database.models import WorkerRank
#     worker_rank = await WorkerRank.get_or_create_rank(worker.id)
#     rank_work_types_limit = worker_rank.get_work_types_limit()

#     # Определяем лимит направлений
#     if worker_sub.unlimited_work_types:
#         count_work_types = 100
#     else:
#         count_work_types = rank_work_types_limit or 1

#     # Получаем все направления и выбранные
#     all_work_types = await WorkType.get_all()
#     selected_ids = worker_sub.work_type_ids if worker_sub.work_type_ids else []

#     # Сохраняем текущую страницу
#     await state.update_data(page=page)

#     text = "🎯 **Мои направления работ**\n\n"
#     text += f"📊 Доступно направлений: {count_work_types if count_work_types < 100 else 'неограниченно'}\n"

#     if selected_ids:
#         text += f"**Выбрано:** {len(selected_ids)} направлений\n\n"
#         text += "Нажмите на направление, чтобы удалить его из списка."
#     else:
#         text += "**У вас нет выбранных направлений.**\n\n"
#         text += "Выберите направления из списка ниже."

#     try:
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.choose_work_types_improved(
#                 all_work_types=all_work_types,
#                 selected_ids=selected_ids,
#                 count_work_types=count_work_types,
#                 page=page,
#                 btn_back=True,
#                 name_btn_back='◀️ Назад в меню'
#             ),
#             parse_mode='Markdown'
#         )
#     except Exception:
#         pass


# @router.callback_query(F.data == "show_selected_work_types", WorkStates.worker_choose_work_types)
# async def show_selected_work_types_handler(callback: CallbackQuery, state: FSMContext) -> None:
#     """Показать выбранные направления"""
#     logger.debug(f'show_selected_work_types_handler...')
#     kbc = KeyboardCollection()

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем лимит направлений из ранга
#     from app.data.database.models import WorkerRank
#     worker_rank = await WorkerRank.get_or_create_rank(worker.id)
#     rank_work_types_limit = worker_rank.get_work_types_limit()

#     # Определяем лимит направлений
#     if worker_sub.unlimited_work_types:
#         count_work_types = 100
#     else:
#         count_work_types = rank_work_types_limit or 1

#     # Получаем выбранные направления
#     selected_ids = worker_sub.work_type_ids if worker_sub.work_type_ids else []

#     if not selected_ids:
#         await callback.answer("У вас нет выбранных направлений", show_alert=True)
#         return

#     # Получаем объекты выбранных направлений
#     selected_work_types = []
#     for work_type_id in selected_ids:
#         work_type = await WorkType.get_work_type(id=int(work_type_id))
#         if work_type:
#             selected_work_types.append(work_type)

#     text = "📋 **Выбранные направления работ**\n\n"
#     text += f"**Всего выбрано:** {len(selected_work_types)}/{count_work_types if count_work_types < 100 else '∞'}\n\n"
#     text += "Нажмите на направление, чтобы удалить его:"

#     try:
#         await callback.message.answer(
#             text=text,
#             reply_markup=kbc.show_selected_work_types(
#                 selected_work_types=selected_work_types,
#                 count_work_types=count_work_types
#             ),
#             parse_mode='Markdown'
#         )
#     except Exception:
#         pass


# @router.callback_query(F.data == "back", WorkStates.worker_choose_work_types)
# async def back_from_work_types(callback: CallbackQuery, state: FSMContext) -> None:
#     """Возврат из выбора направлений в меню"""
#     logger.debug(f'back_from_work_types...')

#     worker = await Worker.get_worker(tg_id=callback.from_user.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

#     # Получаем исходное состояние направлений
#     state_data = await state.get_data()
#     original_work_types = set(state_data.get('original_work_types', []))

#     # Получаем текущее состояние
#     current_work_types = set(worker_sub.work_type_ids if worker_sub.work_type_ids else [])

#     # Проверяем, были ли изменения
#     if original_work_types != current_work_types:
#         # Были изменения - регистрируем
#         from app.data.database.models import WorkerWorkTypeChanges
#         work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)

#         logger.info(f'[WORK_TYPES] Worker {worker.id} changing work types. Original: {original_work_types}, Current: {current_work_types}')

#         await work_type_changes.register_change()

#         logger.info(f'[WORK_TYPES] Worker {worker.id} registered change. Total changes: {work_type_changes.changes_count}/3')

#         # Если достигли лимита - покажем уведомление
#         if work_type_changes.changes_count >= 3:
#             from datetime import datetime
#             if work_type_changes.reset_date:
#                 reset_date = datetime.strptime(work_type_changes.reset_date, '%Y-%m-%d %H:%M:%S')
#                 days_left = (reset_date - datetime.now()).days + 1
#                 await callback.answer(
#                     f"⚠️ Вы использовали все 3 изменения направлений.\nСледующее изменение будет доступно через {days_left} дней.",
#                     show_alert=True
#                 )
#         else:
#             remaining = 3 - work_type_changes.changes_count
#             await callback.answer(
#                 f"✅ Изменения сохранены!\nОсталось изменений: {remaining}/3",
#                 show_alert=False
#             )
#     else:
#         logger.info(f'[WORK_TYPES] Worker {worker.id} exited without changes')

#     # Возвращаемся в меню
#     await state.set_state(WorkStates.worker_menu)
#     await show_worker_menu(callback, state, worker)


@router.callback_query(F.data == "add_city", WorkStates.worker_menu)
async def add_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Добавить город (платная функция)"""
    logger.debug(f'add_city...')
    kbc = KeyboardCollection()

    # Очищаем данные продления и смены тарифа при начале новой покупки
    await state.update_data(
        renew_subscription_id=None,
        renew_city_count=None,
        renew_city_ids=None,
        change_subscription_id=None
    )

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

    # Безопасное редактирование
    try:
        await callback.message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
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

    # Сохраняем количество городов в состояние, сохраняя change_subscription_id если он есть
    data = await state.get_data()
    change_subscription_id = data.get('change_subscription_id')
    await state.update_data(city_count=city_count)
    
    # Восстанавливаем change_subscription_id если он был
    if change_subscription_id:
        await state.update_data(change_subscription_id=change_subscription_id)

    # Цены за месяц для каждого количества городов
    prices = {
        1: 90,  # 1 месяц = 90₽
        2: 180,  # 2 месяца = 171₽, но за месяц = 90₽
        3: 270,  # 3 месяца = 243₽, но за месяц = 90₽
        4: 360,  # 4 месяца = 360₽ за месяц
        5: 450,  # 5 месяцев = 450₽ за месяц
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
    builder.add(
        kbc._inline(f"Купить 2 месяца {int(base_price * 2 * 0.95)}₽", f"city_period_2_{int(base_price * 2 * 0.95)}"))
    builder.add(
        kbc._inline(f"Купить 3 месяца {int(base_price * 3 * 0.9)}₽", f"city_period_3_{int(base_price * 3 * 0.9)}"))
    builder.add(
        kbc._inline(f"Купить 6 месяцев {int(base_price * 6 * 0.8)}₽", f"city_period_6_{int(base_price * 6 * 0.8)}"))
    builder.add(
        kbc._inline(f"Купить 12 месяцев {int(base_price * 12 * 0.7)}₽", f"city_period_12_{int(base_price * 12 * 0.7)}"))
    builder.add(kbc._inline("◀️ К выбору количества городов", "add_city"))
    builder.adjust(1)

    await callback.message.answer(
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
    renew_subscription_id = data.get('renew_subscription_id')
    change_subscription_id = data.get('change_subscription_id')
    
    # Сохраняем change_subscription_id явно, чтобы не потерялся
    if change_subscription_id:
        await state.update_data(change_subscription_id=change_subscription_id)
    
    # Проверяем, это продление или новая покупка
    if renew_subscription_id:
        # Это продление - используем данные из состояния
        city_count = data.get('renew_city_count', 1)
        renew_city_ids = data.get('renew_city_ids', [])
        
        text = f"💰 **Подтверждение продления подписки**\n\n"
        text += f"🏙️ Количество городов: {city_count}\n"
        text += f"📅 Период: {months} месяц(ев)\n"
        text += f"💵 Стоимость: {price}₽\n\n"
        
        # Показываем существующие города
        if renew_city_ids:
            city_names = []
            for city_id in renew_city_ids:
                city = await City.get_city(id=city_id)
                if city:
                    city_names.append(city.city)
            if city_names:
                text += f"📍 Города остаются прежними:\n"
                for name in city_names:
                    text += f"• {name}\n"
                text += "\n"
        
        text += f"После продления вы будете продолжать получать заказы из этих городов в течение {months} месяца(ев).\n\n"
        text += f"Подтвердить продление?"

        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("✅ Подтвердить продление", f"confirm_city_renew_{renew_subscription_id}_{months}_{price}"))
        builder.add(kbc._inline("❌ Отмена", "add_city"))
        builder.adjust(1)
    else:
        # Это новая покупка или смена тарифа
        city_count = data.get('city_count', 1)
        
        # Проверяем, это смена тарифа или новая покупка
        if change_subscription_id:
            # Смена тарифа
            text = f"💰 **Подтверждение смены тарифа**\n\n"
            text += f"🏙️ Новое количество городов: {city_count}\n"
            text += f"📅 Период: {months} месяц(ев)\n"
            text += f"💵 Стоимость: {price}₽\n\n"
            text += f"После смены тарифа вы сможете выбрать города заново.\n\n"
            text += f"Подтвердить смену тарифа?"

            builder = InlineKeyboardBuilder()
            builder.add(kbc._inline("✅ Подтвердить смену тарифа", f"confirm_city_purchase_{city_count}_{months}_{price}"))
        else:
            # Новая покупка
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

    await callback.message.answer(
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

    # Проверяем, не является ли это продлением (защита от случайного вызова)
    data = await state.get_data()
    renew_subscription_id = data.get('renew_subscription_id')
    if renew_subscription_id:
        # Это должно быть продление - отклоняем вызов
        logger.warning(f"confirm_city_purchase called during renewal. subscription_id: {renew_subscription_id}. This should not happen!")
        await callback.answer("❌ Ошибка: используйте кнопку продления для этой подписки", show_alert=True)
        return

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    change_subscription_id = data.get('change_subscription_id')

    # Логируем для отладки
    logger.info(f'confirm_city_purchase: change_subscription_id={change_subscription_id}, city_count={city_count}, months={months}, price={price}, worker_id={worker.id}')

    try:
        # Проверяем, это смена тарифа или новая покупка
        if change_subscription_id:
            logger.info(f'Changing tariff for subscription {change_subscription_id}')
            # Это смена тарифа - обновляем существующую подписку
            # Получаем текущую подписку
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            cursor = await conn.execute(
                'SELECT * FROM worker_city_subscriptions WHERE id = ?',
                [change_subscription_id])
            record = await cursor.fetchone()
            await cursor.close()
            
            if not record:
                await conn.close()
                await callback.answer("❌ Подписка не найдена", show_alert=True)
                return
            
            # Вычисляем новые даты (начинаем с сегодня)
            start_date = datetime.now()
            end_date = start_date + timedelta(days=months * 30)
            
            # Обновляем подписку (пока без городов, они будут выбраны позже)
            logger.info(f'Updating subscription {change_subscription_id}: start={start_date.strftime("%Y-%m-%d")}, end={end_date.strftime("%Y-%m-%d")}, months={months}, price={price}, city_count={city_count}')
            cursor = await conn.execute(
                '''UPDATE worker_city_subscriptions 
                   SET subscription_start = ?, 
                       subscription_end = ?, 
                       subscription_months = ?, 
                       price = ?,
                       purchased_city_count = ?,
                       active = 1
                   WHERE id = ?''',
                [start_date.strftime('%Y-%m-%d'), 
                 end_date.strftime('%Y-%m-%d'), 
                 months, 
                 price,
                 city_count,
                 change_subscription_id])
            rows_affected = cursor.rowcount
            await conn.commit()
            await cursor.close()
            await conn.close()
            
            logger.info(f'Subscription {change_subscription_id} updated. Rows affected: {rows_affected}')
            
            if rows_affected == 0:
                logger.error(f'Failed to update subscription {change_subscription_id} - no rows affected!')
                await callback.answer("❌ Ошибка: не удалось обновить подписку", show_alert=True)
                return
            
            # Сохраняем subscription_id для последующего выбора городов
            subscription_id = change_subscription_id
        else:
            # Это новая покупка - создаем новую подписку
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
                price=price,
                purchased_city_count=city_count  # Сохраняем количество купленных городов
            )
            await subscription.save()
            subscription_id = subscription.id

        # Проверяем, есть ли доступные города для выбора
        all_cities = await City.get_all()

        # Получаем все города из всех активных подписок исполнителя
        all_active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        all_subscription_cities = []
        for subscription in all_active_subscriptions:
            # При смене тарифа исключаем города из текущей подписки, которую мы обновляем
            if change_subscription_id and subscription.id == change_subscription_id:
                continue  # Пропускаем текущую подписку, города можно будет выбрать заново
            all_subscription_cities.extend(subscription.city_ids)

        # Исключаем: основной город, города из других подписок
        excluded_cities = worker.city_id + all_subscription_cities
        available_cities = [city for city in all_cities if city.id not in excluded_cities]

        # Сохраняем флаг смены тарифа до очистки состояния
        is_tariff_change = change_subscription_id is not None

        # Сохраняем данные в состоянии для выбора городов
        # Сохраняем change_subscription_id для определения смены тарифа при сохранении городов
        await state.update_data(
            subscription_id=subscription_id,
            city_count=city_count,
            selected_cities=[],
            change_subscription_id=change_subscription_id if change_subscription_id else None  # Сохраняем для определения смены тарифа
        )

        if is_tariff_change:
            text = f"✅ **Тариф успешно изменён!**\n\n"
            text += f"🔄 Подписка обновлена на {city_count} город(ов)\n"
        else:
            text = f"✅ **Покупка успешно выполнена!**\n\n"
            text += f"🎉 Подписка на {city_count} город(ов) активирована!\n"
        text += f"📅 Период: {months} месяц(ев)\n"
        text += f"⏰ Действует до: {end_date.strftime('%d.%m.%Y')}\n\n"

        if len(available_cities) == 0:
            text += f"⚠️ **Нет доступных городов для выбора!**\n"
            text += f"Все города уже выбраны в других подписках или являются основными.\n"
            text += f"Подписка сохранена, вы сможете выбрать города позже."

            await callback.message.answer(
                text=text,
                reply_markup=kbc.menu_btn(),
                parse_mode='Markdown'
            )
            await state.set_state(WorkStates.worker_menu)
        else:
            text += f"📍 Теперь выберите города для получения заказов"

            # Переходим к выбору городов
            await state.set_state(WorkStates.worker_choose_subscription_cities)
            # Сохраняем msg_id для редактирования сообщения
            await state.update_data(msg_id=None)  # Сбрасываем msg_id для нового сообщения
            await choose_subscription_cities(callback, state)

    except Exception as e:
        logger.error(f"Error in confirm_city_purchase: {e}")
        await callback.answer("❌ Произошла ошибка при покупке", show_alert=True)


@router.callback_query(lambda c: c.data.startswith('confirm_city_renew_'))
async def confirm_city_renew(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение продления подписки на города"""
    logger.debug(f'confirm_city_renew...')
    kbc = KeyboardCollection()

    # Парсим данные: confirm_city_renew_{subscription_id}_{months}_{price}
    parts = callback.data.split('_')
    subscription_id = int(parts[3])
    months = int(parts[4])
    price = int(parts[5])

    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    data = await state.get_data()
    renew_city_ids = data.get('renew_city_ids', [])
    renew_city_count = data.get('renew_city_count', 1)

    try:
        # Получаем текущую подписку
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        cursor = await conn.execute(
            'SELECT * FROM worker_city_subscriptions WHERE id = ?',
            [subscription_id])
        record = await cursor.fetchone()
        await cursor.close()
        
        if not record:
            await conn.close()
            await callback.answer("❌ Подписка не найдена", show_alert=True)
            return
        
        # Используем существующие города из подписки или из состояния
        existing_city_ids = [int(x) for x in record[2].split('|')] if record[2] else []
        city_ids_to_use = renew_city_ids if renew_city_ids else existing_city_ids
        
        # Вычисляем новые даты (продлеваем от текущей даты окончания или от сегодня)
        current_end_date = datetime.strptime(record[4], '%Y-%m-%d')
        # Продлеваем от сегодня, если подписка уже истекла, или от текущей даты окончания
        if current_end_date < datetime.now():
            start_date = datetime.now()
        else:
            start_date = current_end_date
        
        end_date = start_date + timedelta(days=months * 30)
        
        # Обновляем подписку (НЕ создаем новую!)
        city_ids_str = '|'.join(map(str, city_ids_to_use))
        await conn.execute(
            '''UPDATE worker_city_subscriptions 
               SET city_ids = ?, 
                   subscription_start = ?, 
                   subscription_end = ?, 
                   subscription_months = ?, 
                   price = ?,
                   purchased_city_count = ?,
                   active = 1
               WHERE id = ?''',
            [city_ids_str, 
             start_date.strftime('%Y-%m-%d'), 
             end_date.strftime('%Y-%m-%d'), 
             months, 
             price,
             renew_city_count,  # Обновляем количество городов
             subscription_id])
        await conn.commit()
        await conn.close()
        
        # Получаем названия городов для сообщения
        city_names = []
        for city_id in city_ids_to_use:
            city = await City.get_city(id=city_id)
            if city:
                city_names.append(city.city)
        
        text = f"✅ **Подписка успешно продлена!**\n\n"
        text += f"🏙️ Количество городов: {renew_city_count}\n"
        text += f"📅 Период: {months} месяц(ев)\n"
        text += f"⏰ Действует до: {end_date.strftime('%d.%m.%Y')}\n\n"
        
        if city_names:
            text += f"📍 Города:\n"
            for name in city_names:
                text += f"• {name}\n"
            text += f"\n💡 Вы будете продолжать получать заказы из этих городов!"
        
        await callback.message.answer(
            text=text,
            reply_markup=kbc.menu_btn(),
            parse_mode='Markdown'
        )
        
        # Очищаем данные продления из состояния
        await state.update_data(
            renew_subscription_id=None,
            renew_city_count=None,
            renew_city_ids=None
        )
        await state.set_state(WorkStates.worker_menu)

    except Exception as e:
        logger.error(f"Error in confirm_city_renew: {e}")
        await callback.answer("❌ Произошла ошибка при продлении", show_alert=True)


async def choose_subscription_cities(callback: CallbackQuery, state: FSMContext) -> None:
    """Интерфейс выбора городов для подписки"""
    kbc = KeyboardCollection()
    data = await state.get_data()
    city_count = data.get('city_count', 1)
    selected_cities = data.get('selected_cities', [])
    
    # Проверяем, это смена тарифа - если да, гарантируем что selected_cities пустой
    change_subscription_id = data.get('change_subscription_id')
    subscription_id = data.get('subscription_id')
    if change_subscription_id and change_subscription_id == subscription_id and not selected_cities:
        # При смене тарифа начинаем с пустого списка городов
        await state.update_data(selected_cities=[])
        selected_cities = []

    # Получаем все города кроме основного города исполнителя и городов из других подписок
    worker = await Worker.get_worker(tg_id=callback.from_user.id)
    all_cities = await City.get_all()

    # Получаем исключенные города из состояния (для продолжения выбора) или вычисляем заново
    excluded_from_state = data.get('excluded_cities', [])
    if excluded_from_state:
        # Это продолжение выбора - используем исключенные города из состояния
        # НЕ исключаем selected_cities - они должны отображаться для возможности снятия выбора
        excluded_cities = worker.city_id + excluded_from_state
    else:
        # Это новый выбор - получаем все города из всех активных подписок
        all_active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)
        all_subscription_cities = []
        subscription_id = data.get('subscription_id')
        for subscription in all_active_subscriptions:
            # Исключаем только города из других подписок, не текущей
            if subscription.id != subscription_id:
                all_subscription_cities.extend(subscription.city_ids)

        # Исключаем: основной город, города из других подписок
        # НЕ исключаем selected_cities - они должны отображаться для возможности снятия выбора
        excluded_cities = worker.city_id + all_subscription_cities

    # Включаем в список все города, кроме исключенных (включая выбранные, чтобы можно было их видеть и снимать выбор)
    available_cities = [city for city in all_cities if city.id not in excluded_cities]

    # Получаем названия основных городов (оптимизировано)
    cities_dict = {city.id: city.city for city in all_cities}
    main_city_names = [cities_dict.get(city_id, f"Город {city_id}") for city_id in worker.city_id]

    # Определяем доступные невыбранные города
    unselected_available = [city for city in available_cities if city.id not in selected_cities]
    
    text = f"🏙️ **Выберите города для подписки**\n\n"
    text += f"📊 Выбрано: {len(selected_cities)} из {city_count}\n\n"

    if len(unselected_available) == 0 and len(selected_cities) == 0:
        text += f"❌ **Нет доступных городов для выбора!**\n"
        text += f"Все города уже выбраны в других подписках или являются основными."
    elif len(selected_cities) >= city_count:
        text += f"✅ Вы выбрали максимальное количество городов!\n"
        if selected_cities:
            text += f"💡 Нажмите на выбранный город, чтобы убрать его из выбора.\n"
        text += f"Нажмите 'Подтвердить выбор' для завершения."
    else:
        text += f"💡 **Напишите название города** для поиска или выберите из списка ниже:\n"
        if selected_cities:
            text += f"💡 Нажмите на выбранный город (✅), чтобы убрать его из выбора.\n"
        text += f"Выберите еще {city_count - len(selected_cities)} город(ов)"

    builder = InlineKeyboardBuilder()

    # Показываем выбранные города первыми (они всегда видны)
    if selected_cities:
        # Получаем объекты выбранных городов
        selected_city_objects = [city for city in all_cities if city.id in selected_cities]
        for city in selected_city_objects:
            city_name = city.city
            builder.add(kbc._inline(f"✅ {city_name}", f"subscription_city_select_{city.id}"))

    # Показываем доступные города с пагинацией (кроме уже выбранных)
    # unselected_available уже вычислено выше
    if len(unselected_available) > 0:
        # Если есть выбранные города, добавляем разделитель
        if selected_cities:
            # Можно добавить пустую строку для визуального разделения (если нужно)
            pass
        
        page = data.get('city_page', 0)
        cities_per_page = 8 - len(selected_cities)  # Учитываем место для выбранных городов
        if cities_per_page < 1:
            cities_per_page = 1
        start_idx = page * cities_per_page
        end_idx = start_idx + cities_per_page
        page_cities = unselected_available[start_idx:end_idx]

        for city in page_cities:
            city_name = city.city
            builder.add(kbc._inline(f"❌ {city_name}", f"subscription_city_select_{city.id}"))

        # Навигация по страницам (только для невыбранных городов)
        nav_buttons = []
        total_pages = (len(unselected_available) + cities_per_page - 1) // cities_per_page
        if total_pages > 1:
            if page > 0:
                nav_buttons.append(kbc._inline("◀️", f"subscription_city_page_{page - 1}"))
            nav_buttons.append(kbc._inline(f"{page + 1}/{total_pages}", "subscription_city_noop"))
            if page < total_pages - 1:
                nav_buttons.append(kbc._inline("▶️", f"subscription_city_page_{page + 1}"))

        if nav_buttons:
            builder.row(*nav_buttons)

    # Кнопки управления
    if len(selected_cities) >= city_count:
        builder.add(kbc._inline("✅ Подтвердить выбор", "subscription_cities_confirm"))

    builder.add(kbc._inline("🏠 В меню", "worker_menu"))
    builder.adjust(1)

    # Редактируем сообщение вместо создания нового
    msg_id = data.get('msg_id')
    try:
        if msg_id:
            await callback.message.edit_text(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
        else:
            # Первый раз отправляем сообщение и сохраняем ID
            msg = await callback.message.answer(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
            await state.update_data(msg_id=msg.message_id)
    except Exception as e:
        # Если не удалось отредактировать, отправляем новое сообщение
        logger.debug(f"Could not edit message: {e}")
        msg = await callback.message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
        await state.update_data(msg_id=msg.message_id)


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

    await callback.message.answer(
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
        # Проверяем, это смена тарифа или новая покупка
        change_subscription_id = data.get('change_subscription_id')
        
        # Получаем текущую подписку
        worker = await Worker.get_worker(tg_id=callback.from_user.id)
        active_subscriptions = await WorkerCitySubscription.get_active_by_worker(worker.id)

        existing_subscription = None
        for subscription in active_subscriptions:
            if subscription.id == subscription_id:
                existing_subscription = subscription
                break

        if existing_subscription:
            # Если это смена тарифа - полностью заменяем города новыми
            # Если это новая покупка или добавление к существующей - объединяем
            if change_subscription_id and change_subscription_id == subscription_id:
                # Смена тарифа - заменяем города полностью
                all_selected_cities = selected_cities
                logger.info(f'Tariff change: replacing cities completely. New cities: {selected_cities}')
            else:
                # Новая покупка или добавление - объединяем города
                all_selected_cities = existing_subscription.city_ids + selected_cities
                # Убираем дубликаты
                all_selected_cities = list(set(all_selected_cities))
                logger.info(f'New purchase: merging cities. Old: {existing_subscription.city_ids}, New: {selected_cities}, Result: {all_selected_cities}')
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

        # Разные сообщения для смены тарифа и новой покупки
        change_subscription_id = data.get('change_subscription_id')
        if change_subscription_id and change_subscription_id == subscription_id:
            text = f"✅ **Тариф успешно изменён!**\n\n"
            text += f"🔄 Города обновлены:\n"
            for name in all_city_names:
                text += f"• {name}\n"
            text += f"\n💡 Теперь вы будете получать заказы из этих городов!"
        else:
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

        await callback.message.answer(
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
            found_cities.append(available_cities[i - 1])

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
        # Получаем подписку по ID
        subscription = None
        try:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            cursor = await conn.execute(
                'SELECT * FROM worker_city_subscriptions WHERE id = ?',
                [subscription_id])
            record = await cursor.fetchone()
            await cursor.close()
            await conn.close()
            
            if record:
                city_ids = [int(x) for x in record[2].split('|')] if record[2] else []
                subscription = WorkerCitySubscription(
                    id=record[0],
                    worker_id=record[1],
                    city_ids=city_ids,
                    subscription_start=record[3],
                    subscription_end=record[4],
                    subscription_months=record[5],
                    price=record[6],
                    active=bool(record[7]),
                    purchased_city_count=record[8]
                )
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
        
        if not subscription:
            await callback.answer("❌ Подписка не найдена", show_alert=True)
            return

        # Используем purchased_city_count для правильного расчёта цены
        city_count = subscription.purchased_city_count
        
        # Сохраняем subscription_id в состояние для последующего продления
        await state.update_data(
            renew_subscription_id=subscription_id,
            renew_city_count=city_count,
            renew_city_ids=subscription.city_ids  # Сохраняем существующие города
        )

        text = f"🔄 **Продление подписки**\n\n"
        text += f"🏙️ Количество городов: {city_count}\n"
        
        # Получаем названия городов
        city_names = []
        for city_id in subscription.city_ids[:3]:
            city = await City.get_city(id=city_id)
            if city:
                city_names.append(city.city)
        
        if city_names:
            text += f"📍 Города: {', '.join(city_names)}"
            if len(subscription.city_ids) > 3:
                text += f" и ещё {len(subscription.city_ids) - 3}\n"
            else:
                text += "\n"
        else:
            text += "📍 Города не выбраны\n"
        
        text += f"\nВыберите новый срок подписки:"

        # Цены за месяц для каждого количества городов
        prices = {
            1: 90, 2: 180, 3: 270, 4: 360, 5: 450, 10: 900, 20: 1800
        }
        base_price = prices.get(city_count, 90)

        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline(f"Продлить на 1 месяц {base_price}₽", f"city_period_1_{base_price}"))
        builder.add(kbc._inline(f"Продлить на 2 месяца {int(base_price * 2 * 0.95)}₽",
                                f"city_period_2_{int(base_price * 2 * 0.95)}"))
        builder.add(kbc._inline(f"Продлить на 3 месяца {int(base_price * 3 * 0.9)}₽",
                                f"city_period_3_{int(base_price * 3 * 0.9)}"))
        builder.add(kbc._inline(f"Продлить на 6 месяцев {int(base_price * 6 * 0.8)}₽",
                                f"city_period_6_{int(base_price * 6 * 0.8)}"))
        builder.add(kbc._inline(f"Продлить на 12 месяцев {int(base_price * 12 * 0.7)}₽",
                                f"city_period_12_{int(base_price * 12 * 0.7)}"))
        builder.add(kbc._inline("◀️ Назад", "add_city"))
        builder.adjust(1)

    elif action == "change":
        # Смена тарифа - переход к выбору количества городов
        # Сначала сохраняем subscription_id для последующего обновления
        change_sub_id = subscription_id
        
        # Вызываем add_city (он очистит change_subscription_id, но мы восстановим)
        await add_city(callback, state)
        
        # Восстанавливаем change_subscription_id ПОСЛЕ вызова add_city
        await state.update_data(
            change_subscription_id=change_sub_id  # Восстанавливаем ID подписки для смены тарифа
        )
        return

    elif action == "cancel":
        # Отказ от подписки
        text = f"❌ **Отказ от подписки**\n\n"
        text += f"Подписка будет отключена, вы всегда сможете подключить её снова в удобное для вас время!"

        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("✅ Подтвердить отказ", f"confirm_cancel_subscription_{subscription_id}"))
        builder.add(kbc._inline("◀️ Отмена", "add_city"))
        builder.adjust(1)

    await callback.message.answer(
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

        await callback.message.answer(
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

            # Используем purchased_city_count вместо вычисления из цены
            city_count = subscription.purchased_city_count

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

    # Безопасное редактирование
    try:
        await callback.message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
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

    await callback.message.answer(
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
            await worker.update_purchased_contacts(unlimited_contacts_until=until_date.isoformat())

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

        await callback.message.answer(
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

        # Безопасное редактирование
        try:
            await callback.message.answer(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
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

        # Безопасное редактирование
        try:
            await callback.message.answer(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
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

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=True, ),
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

    msg = await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=True, ),
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
        msg = await callback.message.answer(
            text=f"🔄 **Смена основного города**\n\n"
                 f"📍 **Текущий основной город:** {current_main_city}\n\n"
                 f"Выберите город или напишите его текстом\n\n"
                 f'Показано {id_now + len(city_names)} из {count_cities} городов',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back, ),
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
    # msg_id = int(state_data.get('msg_id'))

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
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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

    await callback.message.answer(
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
        msg = await callback.message.answer(
            text=f"📍 **Выберите город**\n\n"
                 f"Выберите город или напишите его текстом\n\n"
                 f'Показано {id_now + len(city_names)} из {count_cities} городов',
            reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                        btn_next=btn_next, btn_back=btn_back, ),
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
    # msg_id = int(state_data.get('msg_id'))

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
    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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

    await callback.message.answer(
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

    await callback.message.answer(
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
        purchased_cities = subscription.purchased_city_count
        if len(subscription.city_ids) < purchased_cities:
            incomplete_subscriptions.append(subscription)

    # Показываем активные подписки
    if active_subscriptions:
        text += "🏷️ **Активные подписки на города:**\n\n"
        for subscription in active_subscriptions:
            # Используем purchased_city_count вместо вычисления из цены
            total_count = subscription.purchased_city_count
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
            total_count = subscription.purchased_city_count
            selected_count = len(subscription.city_ids)
            remaining = total_count - selected_count
            text += f"• Осталось выбрать {remaining} из {total_count} городов\n"
        text += "\n"

    builder = InlineKeyboardBuilder()

    # Если есть незавершенные подписки, показываем кнопку для их завершения
    if incomplete_subscriptions:
        for subscription in incomplete_subscriptions:
            total_count = subscription.purchased_city_count
            selected_count = len(subscription.city_ids)
            remaining = total_count - selected_count

            builder.add(kbc._inline(
                f"✅ Выбрать города ({remaining} осталось)",
                f"continue_subscription_cities_{subscription.id}"
            ))

    builder.add(kbc._inline("◀️ Назад", "worker_change_city_menu"))
    builder.adjust(1)

    await callback.message.answer(
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

    # Используем purchased_city_count вместо вычисления из цены
    purchased_cities = target_subscription.purchased_city_count
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
        excluded_cities=other_subscription_cities,  # Города из других подписок
        msg_id=None  # Сбрасываем msg_id для нового сообщения
    )

    # Переходим к выбору городов
    await state.set_state(WorkStates.worker_choose_subscription_cities)
    await choose_subscription_cities(callback, state)


# @router.message(F.text, WorkStates.worker_change_city)
# async def choose_city_main(message: Message, state: FSMContext) -> None:
#     logger.debug(f'choose_city_main...')
#     kbc = KeyboardCollection()
#
#     city_input = message.text
#
#     state_data = await state.get_data()
#     # msg_id = int(state_data.get('msg_id'))
#     cites = state_data.get('cites')
#
#     cities = await City.get_all(sort=False)
#     city_names = [city.city for city in cities]
#
#     worker = await Worker.get_worker(tg_id=message.chat.id)
#     worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
#     subscription = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
#
#     city_find = await checks.levenshtein_distance_check_city(phrase=city_input, words=city_names)
#     if not city_find:
#         await message.answer(text=f'Город не найден, попробуйте еще раз или воспользуйтесь кнопками')
#         return
#
#     cities = []
#
#     for city_id in city_find:
#         city = await City.get_city(id=city_id)
#         cities.append(city)
#
#     city_names = [city.city for city in cities]
#     city_ids = [city.id for city in cities]
#
#     if cites is None:
#         cites = []
#     else:
#         cites = [int(x) for x in cites.split(' | ')]
#         for city_id in cites:
#             city = await City.get_city(id=city_id)
#             try:
#                 city_names.remove(city.city)
#                 city_ids.remove(city.id)
#             except ValueError:
#                 pass
#
#     msg = await message.answer(
#         text=f'Результаты поиска по: {city_input}\n'
#              f'Выберите город или напишите его текстом\n\n'
#              f'По вашей подписке доступно количество городов: {subscription.count_cites}, выбрано {len(cites)}',
#         reply_markup=kbc.choose_obj(id_now=0, ids=city_ids, names=city_names,
#                                     btn_next=True, btn_back=False, menu_btn=True,
#                                     btn_next_name='Отменить результаты поиска'))
#     await state.update_data(msg_id=msg.message_id)
#     # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


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

        # Используем метод get_rank_description() для получения полного описания
        text = rank.get_rank_description()
        text += f"\n\n📊 **Статистика:**\n"
        text += f"• Всего выполнено заказов: {rank.completed_orders_count}\n"
        text += f"• Выполнено заказов за 30 дней: {rank.orders_this_month}"

        # Кнопка назад
        builder = InlineKeyboardBuilder()
        builder.add(kbc._inline("◀️ Назад", "worker_menu"))
        builder.adjust(1)

        # Пробуем отредактировать текст, если не получится - удаляем и отправляем новое
        try:
            await callback.message.answer(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
        except Exception:
            # Если сообщение было с фото, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Error in worker_rank: {e}")
        await callback.answer("❌ Ошибка при получении информации о ранге", show_alert=True)


@router.callback_query(F.data == "rank_downgrade_ok")
async def rank_downgrade_ok(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик кнопки OK после уведомления о понижении ранга.
    Перенаправляет исполнителя в раздел "Мои направления" для выбора новых направлений.
    """
    logger.debug(f'rank_downgrade_ok...')

    try:
        # Удаляем сообщение с уведомлением
        try:
            await callback.message.delete()
        except Exception:
            pass

        # Устанавливаем состояние меню
        await state.set_state(WorkStates.worker_menu)

        # Вызываем обработчик "Мои направления" напрямую
        # Создаем фейковый callback с нужным data
        from copy import copy

        # Создаем копию callback с новым data
        fake_callback = copy(callback)
        fake_callback._data = "choose_work_types"

        # Вызываем обработчик выбора направлений (функция на строке 1709)
        await choose_work_types(fake_callback, state)

    except Exception as e:
        logger.error(f"Error in rank_downgrade_ok: {e}")
        await callback.answer("❌ Ошибка при переходе к выбору направлений", show_alert=True)


async def filter_worker_advertisements(worker_id: int, advertisements: list) -> list:
    """Фильтрует объявления для исполнителя, исключая уже откликнувшиеся"""
    worker = await Worker.get_worker(id=worker_id)
    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)

    # Собираем ID объявлений, на которые исполнитель уже откликнулся или которые заблокированы
    bad_abs = []
    worker_and_reports = await WorkerAndReport.get_by_worker(worker_id=worker.id)
    worker_and_bad_responses = await WorkerAndBadResponse.get_by_worker(worker_id=worker.id)
    worker_and_abs = await WorkersAndAbs.get_by_worker(worker_id=worker.id)

    if worker_and_reports:
        bad_abs += [worker_and_report.abs_id for worker_and_report in worker_and_reports]
    if worker_and_bad_responses:
        bad_abs += [worker_and_bad_response.abs_id for worker_and_bad_response in worker_and_bad_responses]
    if worker_and_abs:
        bad_abs += [response.abs_id for response in worker_and_abs]

    # Убираем дубликаты и преобразуем в set для быстрого поиска
    bad_abs = set(bad_abs)

    advertisements_final = []

    for advertisement in advertisements:
        customer = await Customer.get_customer(id=advertisement.customer_id)
        if customer.tg_id == worker.tg_id:
            continue
        if advertisement.id in bad_abs:
            continue

        # Проверяем, подходит ли объявление по типу работы
        if not worker_sub.work_type_ids:
            continue

        if worker_sub.work_type_ids and str(advertisement.work_type_id) in worker_sub.work_type_ids:
            if advertisement.relevance:
                advertisements_final.append(advertisement)

    return advertisements_final

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
