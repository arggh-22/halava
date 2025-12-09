import logging
import asyncio
import time
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import (
    Customer, Banned, BannedAbs, Abs, Worker, WorkerAndSubscription, WorkersAndAbs, City, WorkerAndRefsAssociation,
    WorkType, Admin, WorkerAndBadResponse, WorkerAndReport, ContactTariff, CitySubscriptionTariff,
    CitySubscriptionDiscount
)
from app.keyboards import KeyboardCollection
from app.states import AdminStates, UserStates, BannedStates
from app.untils import help_defs
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()

# Simple in-memory cache for admin summary
_admin_summary_cache = {"data": {}, "ts": 0.0, "ttl": 60.0}  # Кеш на 30 секунд


def clear_admin_cache():
    """Очищает кеш админской аналитики"""
    global _admin_summary_cache
    _admin_summary_cache = {"data": {}, "ts": 0.0, "ttl": 60.0}


def is_cache_valid():
    """Проверяет валидность кеша"""
    current_time = time.time()
    return (_admin_summary_cache["data"] is not None and
            current_time - _admin_summary_cache["ts"] < _admin_summary_cache["ttl"])


@router.callback_query(F.data == 'refresh_admin_stats', StateFilter(AdminStates.menu))
async def refresh_admin_stats(callback: CallbackQuery, state: FSMContext) -> None:
    """Принудительное обновление статистики админа"""
    logger.debug('refresh_admin_stats...')

    # Очищаем кеш
    clear_admin_cache()

    # Показываем сообщение об обновлении
    await callback.answer("🔄 Статистика обновлена!", show_alert=True)

    # Вызываем admin_menu для перезагрузки данных
    await admin_menu(callback, state)


@router.callback_query(F.data == 'edit_order_price', StateFilter(AdminStates.menu))
async def edit_order_price(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик для изменения цены объявлений"""
    logger.debug('edit_order_price...')
    kbc = KeyboardCollection()

    admin = await Admin.get_by_tg_id(callback.message.chat.id)

    text = f'💰 <b>Управление ценой объявлений</b>\n\n'
    text += f'Текущая цена: {admin.order_price}₽\n\n'
    text += f'Введите новую цену в рублях:'

    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'), parse_mode='HTML')
    await state.set_state(AdminStates.edit_order_price)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, StateFilter(AdminStates.edit_order_price))
async def process_order_price(message: Message, state: FSMContext) -> None:
    """Обработка введенной цены объявлений"""
    logger.debug('process_order_price...')
    kbc = KeyboardCollection()

    try:
        new_price = int(message.text)
        if new_price <= 0:
            raise ValueError("Цена должна быть положительным числом")

        # Получаем админа и обновляем цену
        admin = await Admin.get_by_tg_id(message.chat.id)
        await admin.update(order_price=new_price)

        await message.answer(
            text=f'✅ <b>Цена объявлений успешно изменена!</b>\n\n'
                 f'💰 Новая цена: {new_price}₽',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.menu)

    except ValueError as e:
        await message.answer(
            text=f'❌ <b>Ошибка!</b>\n\n'
                 f'Пожалуйста, введите корректную цену (положительное число).\n'
                 f'Например: 50, 100, 150',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.edit_order_price)
    except Exception as e:
        logger.error(f"Ошибка при изменении цены объявлений: {e}")
        await message.answer(
            text='❌ <b>Произошла ошибка!</b>\n\n'
                 'Попробуйте еще раз или обратитесь к разработчику.',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.menu)


@router.callback_query(F.data == 'edit_user', StateFilter(AdminStates.menu))
async def edit_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('block_user...')
    kbc = KeyboardCollection()

    text = f'Выберите что хотите сделать:'

    msg = await callback.message.answer(text=text, reply_markup=kbc.menu_admin_edit_users())
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'unblock_user', StateFilter(AdminStates.menu))
async def unblock_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('block_user...')
    kbc = KeyboardCollection()

    text = f'Введите общий ID пользователя, которого хотите разблокировать'

    await state.set_state(AdminStates.unblock_user)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'block_user', StateFilter(AdminStates.menu))
async def unblock_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('unblock_user...')
    kbc = KeyboardCollection()

    text = f'Введите общий ID пользователя, которого хотите заблокировать'

    await state.set_state(AdminStates.block_user)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'get_customer', StateFilter(AdminStates.menu))
async def get_customer(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('get_customer...')
    kbc = KeyboardCollection()

    text = f'Введите ID заказчика'

    await state.set_state(AdminStates.get_customer)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'send_to_user', StateFilter(AdminStates.get_user))
async def unblock_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('block_user...')
    kbc = KeyboardCollection()
    state_data = await state.get_data()
    user_id = int(state_data.get('user_id'))

    text = f'Напишите сообщение для пользователя:'

    await state.set_state(AdminStates.send_to_user)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(user_id=user_id)


@router.callback_query(F.data == 'get_user', StateFilter(AdminStates.menu))
async def get_customer(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('get_user...')
    kbc = KeyboardCollection()

    text = f'Введите общий ID пользователя'

    await state.set_state(AdminStates.get_user)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'get_user', StateFilter(AdminStates.get_user))
async def get_customer(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'get_user_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    user_id = int(state_data.get('user_id'))

    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += '<i>Пользователь заблокирован</i>\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                           worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        status_string = await help_defs.get_worker_status_string(worker.id)

        text += (f'<i>Профиль исполнителя</i>\n\n'
                 f'ID: {worker.id}\n'
                 f'Статус: {status_string}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)[0]} ⭐️\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += ('<i>Профиль заказчика</i>\n\n'
                 f'ID: {customer.id}\n'
                 f'Общий ID: {customer.tg_id}\n'
                 f'Город заказчика: {city.city}\n'
                 f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n')

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False
        if worker:
            if worker.profile_photo:
                try:
                    await callback.message.delete()
                except TelegramBadRequest:
                    pass
                await callback.message.answer_photo(caption=text, photo=FSInputFile(worker.profile_photo),
                                                    protect_content=False,
                                                    reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                                        customer_id=customer_id))
            else:
                await callback.message.answer(text=text, protect_content=False,
                                              reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                                  customer_id=customer_id))
        else:
            await callback.message.answer(text=text, protect_content=False,
                                          reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                              customer_id=customer_id))
        await state.update_data(user_id=user_id)
        return
    else:
        await callback.message.answer(text='Упс, такого пользователя нет', reply_markup=kbc.admin_back_btn('menu'))
        return


@router.callback_query(F.data == 'get_worker', StateFilter(AdminStates.menu))
async def get_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('get_worker...')
    kbc = KeyboardCollection()

    text = f'Введите ID исполнителя'

    await state.set_state(AdminStates.get_worker)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'get_banned', StateFilter(AdminStates.menu))
async def get_worker(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('get_worker...')
    kbc = KeyboardCollection()

    banned_users = await Banned.get_all_banned_now()

    text = f'Заблокированные пользователи\n'
    if banned_users:
        for banned in banned_users:
            text += f' - Общий ID {banned.tg_id}, заблокирован {"навсегда" if banned.forever else "на сутки"}\n'
    else:
        text += 'Заблокированных пользователей нет'

    await state.set_state(AdminStates.menu)
    try:
        await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))
    except Exception:
        text = f'Заблокированные пользователи\n'
        if banned_users:
            for banned in banned_users:
                if not banned.forever:
                    text += f' - Общий ID {banned.tg_id}, заблокирован на сутки\n'
        else:
            text += 'Заблокированных пользователей нет'
        await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'))


@router.message(F.text, StateFilter(AdminStates.unblock_user))
async def unblock_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'unban_user_text...')
    kbc = KeyboardCollection()

    try:
        banned_id = int(message.text)
    except Exception:
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    banned = await Banned.get_banned(tg_id=banned_id)

    if banned is None:
        await message.answer('Пользователь не был заблокирован', reply_markup=kbc.admin_back_btn('menu'))
        return

    if banned.ban_counter == 1:
        await banned.delete()
    else:
        if banned.forever:
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None,
                                forever=False)
        else:
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None)

    await message.answer('Пользователь разблокирован', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=banned_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.message(F.text, StateFilter(AdminStates.send_to_user))
async def send_to_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_to_user_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    user_id = int(state_data.get('user_id'))

    msg_to_send = message.text

    banned = await Banned.get_banned(tg_id=user_id)
    customer = await Customer.get_customer(tg_id=user_id)
    worker = await Worker.get_worker(tg_id=user_id)

    if banned is None and customer is None and worker is None:
        await message.answer('Пользователь не найден', reply_markup=kbc.admin_back_btn('menu'))
        return

    await message.answer('Сообщение пользователю отправлено', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=user_id, text=f'Сообщение от администрации бота: "{msg_to_send}"')
    await state.set_state(AdminStates.menu)


@router.message(F.text, StateFilter(AdminStates.block_user))
async def unblock_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'ban_user_text...')
    kbc = KeyboardCollection()

    try:
        banned_id = int(message.text)
    except Exception:
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз', reply_markup=kbc.admin_back_btn('menu'))
        await state.update_data(msg_id=msg.message_id)
        return

    banned = await Banned.get_banned(tg_id=banned_id)

    if banned is None:
        banned = Banned(id=None, tg_id=banned_id, ban_counter=1, ban_end=str(datetime.now() + timedelta(days=30)),
                        ban_now=True, forever=False, ban_reason='по решению администратора')
        await banned.save()
    else:
        if banned.forever:
            await message.answer('Пользователь уже заблокирован на всегда', reply_markup=kbc.admin_back_btn('menu'))
            return
        else:
            await banned.update(ban_counter=banned.ban_counter + 1,
                                ban_now=True,
                                ban_end=str(datetime.now() + timedelta(days=30)))

    await message.answer('Пользователь заблокирован', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=banned_id,
                           text='Вы были заблокированы.\nПо решению администрации', reply_markup=kbc.support_btn())


@router.message(F.text, StateFilter(AdminStates.get_customer))
async def get_customer(message: Message, state: FSMContext) -> None:
    logger.debug(f'get_customer_text...')
    kbc = KeyboardCollection()

    try:
        customer_id = int(message.text)
    except Exception:
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    customer = await Customer.get_customer(tg_id=customer_id)

    if customer is None:
        await message.answer('Заказчик с таким ID не существует', reply_markup=kbc.admin_back_btn('menu'))
        return

    user_abs = await Abs.get_all_by_customer(customer.id)
    city = await City.get_city(id=int(customer.city_id))
    banned = await Banned.get_banned(tg_id=customer.tg_id)
    ban_now = False
    if banned:
        if banned.ban_now:
            ban_now = True

    text = ('Профиль заказчика\n\n'
            f'ID: {customer.id}\n'
            f'Общий ID: {customer.tg_id}\n'
            f'Город заказчика: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
            f'\n'
            f'Заблокирован: {"Да" if ban_now else "Нет"}')

    await message.answer(text=text, reply_markup=kbc.admin_get_customer(callback_data='menu', customer_id=customer_id),
                         protect_content=False)


@router.message(F.text, StateFilter(AdminStates.get_user))
async def get_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'get_user_text...')
    kbc = KeyboardCollection()

    try:
        user_id = int(message.text)
    except Exception:
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += f'<i>Пользователь заблокирован</i>\nПричина блокировки: {user_blocked.ban_reason}\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                           worker_sub.work_type_ids] if worker_sub.work_type_ids else None

        if len(worker.city_id) == 1:
            cites = 'Город: '
            step = ''
        else:
            cites = 'Города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        status_string = await help_defs.get_worker_status_string(worker.id)

        text += (f'<i>Профиль исполнителя</i>\n\n'
                 f'ID: {worker.id}\n'
                 f'Статус: {status_string}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)[0]} ⭐️\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += ('<i>Профиль заказчика</i>\n\n'
                 f'ID: {customer.id}\n'
                 f'Общий ID: {customer.tg_id}\n'
                 f'Город заказчика: {city.city}\n'
                 f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n')

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False
        await message.answer(
            text=text,
            protect_content=False,
            reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id)
        )
        await state.update_data(user_id=user_id)
        return
    else:
        await message.answer(text='Упс, такого пользователя нет', reply_markup=kbc.admin_back_btn('menu'))
        return


@router.callback_query(lambda c: c.data.startswith('get-user_'))
async def banned_abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'get_user_...')
    kbc = KeyboardCollection()

    try:
        customer_id = int(callback.data.split('_')[1])
        customer = await Customer.get_customer(id=customer_id)
        user_id = customer.tg_id
    except Exception as err:
        logger.debug(f'get_user_...{err}')
        msg = await callback.message.answer(text='Что-то пошло не так', reply_markup=kbc.menu_btn())
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += f'Пользователь заблокирован\nПричина блокировки: {user_blocked.ban_reason}\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                           worker_sub.work_type_ids] if worker_sub.work_type_ids else None

        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        status_string = await help_defs.get_worker_status_string(worker.id)

        text += (f'Профиль исполнителя\n\n'
                 f'ID: {worker.id}\n'
                 f'Статус: {status_string}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)[0]} ⭐️\n'
                 f'{cites}'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += ('Профиль заказчика\n\n'
                 f'ID: {customer.id}\n'
                 f'Общий ID: {customer.tg_id}\n'
                 f'Город заказчика: {city.city}\n'
                 f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n')

    await state.set_state(AdminStates.get_user)

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False
        if worker:
            if worker.profile_photo:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer_photo(caption=text, photo=FSInputFile(worker.profile_photo),
                                                    protect_content=False,
                                                    reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                                        customer_id=customer_id))
            else:
                await callback.message.answer(text=text, protect_content=False,
                                              reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                                  customer_id=customer_id))

        else:
            await callback.message.answer(text=text, protect_content=False,
                                          reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                              customer_id=customer_id))
        await callback.message.delete()
        await state.update_data(user_id=user_id)
        return
    else:
        await callback.message.answer(text='Упс, такого пользователя нет', reply_markup=kbc.admin_back_btn('menu'))
        return


@router.callback_query(lambda c: c.data.startswith('look-abs-customer_'), AdminStates.get_user)
async def abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')
    kbc = KeyboardCollection()

    customer_id = int(callback.data.split('_')[1])

    advertisements = await Abs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        customer = await Customer.get_customer(id=customer_id)
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        try:
            await callback.message.delete()
        except Exception:
            pass
        await state.set_state(AdminStates.get_user)
        await state.update_data(user_id=customer.tg_id)
        return

    await state.set_state(AdminStates.check_abs)
    await state.update_data(customer_id=customer_id)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    text = help_defs.read_text_file(abs_now.text_path)

    text = f'Объявление #{abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text,
                                          reply_markup=kbc.choose_obj_with_out_list_admin(id_now=0, btn_next=btn_next,
                                                                                          btn_back=False,
                                                                                          btn_block=True,
                                                                                          btn_delete=True,
                                                                                          abs_id=abs_now.id,
                                                                                          customer_id=customer_id))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']), caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list_admin(id_now=0, btn_next=btn_next,
                                                                                            btn_back=False,
                                                                                            btn_block=True,
                                                                                            btn_delete=True,
                                                                                            abs_id=abs_now.id,
                                                                                            customer_id=customer_id))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_obj_with_out_list_admin(id_now=0, btn_next=btn_next,
                                                                                  btn_back=False,
                                                                                  btn_block=True,
                                                                                  btn_delete=True,
                                                                                  abs_id=abs_now.id,
                                                                                  customer_id=customer_id))


@router.callback_query(lambda c: c.data.startswith('look-banned-abs-customer_'), AdminStates.get_user)
async def banned_abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')
    kbc = KeyboardCollection()

    customer_id = int(callback.data.split('_')[1])

    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        customer = await Customer.get_customer(id=customer_id)
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await state.set_state(AdminStates.get_user)
        await state.update_data(user_id=customer.tg_id)
        return

    await state.set_state(AdminStates.check_banned_abs)
    await state.update_data(customer_id=customer_id)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    text = help_defs.read_text_file(abs_now.text_path)
    text = f'Объявление #{abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        if 'https' in abs_now.photo_path['0']:
            await callback.message.answer(text=text,
                                          reply_markup=kbc.choose_obj_with_out_list_admin_var(id_now=0,
                                                                                              btn_next=btn_next,
                                                                                              btn_back=False,
                                                                                              btn_block=True,
                                                                                              btn_delete=True,
                                                                                              abs_id=abs_now.id,
                                                                                              customer_id=customer_id))
            return
        await callback.message.answer_photo(photo=FSInputFile(abs_now.photo_path['0']), caption=text,
                                            reply_markup=kbc.choose_obj_with_out_list_admin_var(id_now=0,
                                                                                                btn_next=btn_next,
                                                                                                btn_back=False,
                                                                                                btn_block=True,
                                                                                                btn_delete=True,
                                                                                                abs_id=abs_now.id,
                                                                                                customer_id=customer_id))
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_obj_with_out_list_admin_var(id_now=0, btn_next=btn_next,
                                                                                      btn_back=False,
                                                                                      btn_block=True,
                                                                                      btn_delete=True,
                                                                                      abs_id=abs_now.id,
                                                                                      customer_id=customer_id))


@router.callback_query(F.data == 'unblock_user', StateFilter(AdminStates.get_user))
async def unblock_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('block_user...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    banned_id = int(state_data.get('user_id'))

    banned = await Banned.get_banned(tg_id=banned_id)

    if banned is None:
        await callback.message.answer('Пользователь не был заблокирован',
                                      reply_markup=kbc.admin_back_btn('get_user'))

        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        return

    if banned.ban_counter == 1:
        await banned.delete()
    else:
        if banned.forever:
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None,
                                forever=False)
        else:
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None)

    await callback.message.answer('Пользователь разблокирован', reply_markup=kbc.admin_back_btn('get_user'))
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await bot.send_message(chat_id=banned_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.callback_query(F.data == 'block_user', StateFilter(AdminStates.get_user))
async def unblock_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('unblock_user...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    banned_id = int(state_data.get('user_id'))

    banned = await Banned.get_banned(tg_id=banned_id)

    if banned is None:
        banned = Banned(id=None, tg_id=banned_id, ban_counter=1, ban_end=str(datetime.now() + timedelta(days=30)),
                        ban_now=True, forever=False, ban_reason='по решению администратора')
        await banned.save()
    else:
        if banned.forever:
            await callback.message.answer('Пользователь уже заблокирован на всегда',
                                          reply_markup=kbc.admin_back_btn('menu'))
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            return
        else:
            await banned.update(ban_counter=banned.ban_counter + 1,
                                ban_now=True,
                                ban_end=str(datetime.now() + timedelta(days=30)))

    await callback.message.answer('Пользователь заблокирован', reply_markup=kbc.admin_back_btn('get_user'))
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await bot.send_message(chat_id=banned_id,
                           text='Вы были заблокированы.\nПо решению администрации', reply_markup=kbc.support_btn())


@router.message(F.text, StateFilter(AdminStates.get_worker))
async def get_worker(message: Message, state: FSMContext) -> None:
    logger.debug(f'get_worker_text...')
    kbc = KeyboardCollection()

    try:
        worker_id = int(message.text)
    except Exception:
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    worker = await Worker.get_worker(tg_id=worker_id)

    if worker is None:
        await message.answer('Исполнитель с таким ID не существует', reply_markup=kbc.admin_back_btn('menu'))
        return

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                       worker_sub.work_type_ids] if worker_sub.work_type_ids else None
    
    if len(worker.city_id) == 1:
        cites = 'Город: '
        step = ''
    else:
        cites = 'Города:\n'
        step = '    '
    for city_id in worker.city_id:
        city = await City.get_city(id=city_id)
        cites += f'{step}{city.city}\n'

    status_string = await help_defs.get_worker_status_string(worker.id)

    rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
    text = (f'Профиль исполнителя\n\n'
            f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}\n'
            f'Статус: {status_string}\n'
            f'Общий ID исполнителя: {worker.tg_id}\n'
            f'Рейтинг: {rating_display} ⭐️ ({count_ratings} {help_defs.get_grade_word(count_ratings)})\n'
            f'{cites}'
            f'Выполненных заказов: {worker.order_count}\n'
            f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
            f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка

    await message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'), protect_content=False)


@router.callback_query(F.data == 'menu_send_msg_admin', StateFilter(AdminStates.menu))
async def menu_send_msg_admin_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('menu_send_msg_admin_keyboard...')
    kbc = KeyboardCollection()

    text = (
    f'Меню\n\n'
    f'Выберите интересующую вас группу отправки'
    )

    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=text, reply_markup=kbc.menu_send_msg_admin_keyboard())


@router.callback_query(F.data == 'menu_admin', StateFilter(AdminStates.menu, UserStates.menu, BannedStates.banned,
                                                           AdminStates.manage_contact_tariffs,
                                                           AdminStates.view_contact_tariff,
                                                           AdminStates.add_contact_tariff_type,
                                                           AdminStates.manage_city_tariffs,
                                                           AdminStates.view_city_tariff,
                                                           AdminStates.manage_city_discounts,
                                                           AdminStates.view_city_discount,
                                                           AdminStates.add_city_tariff_count,
                                                           AdminStates.add_city_tariff_price,
                                                           AdminStates.add_city_discount_months,
                                                           AdminStates.add_city_discount_percent))
async def admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('admin_menu...')
    kbc = KeyboardCollection()

    # Cache hit
    now_ts = time.time()
    if _admin_summary_cache["data"] is not None and (now_ts - _admin_summary_cache["ts"]) < _admin_summary_cache["ttl"]:
        summary = _admin_summary_cache["data"]
    else:
        # Fetch aggregated counts concurrently
        (
            len_customer,
            len_worker,
            len_banned_users,
            len_advertisement,
            len_banned_advertisement,
            len_users,
            admin
        ) = await asyncio.gather(
            Customer.count(),
            Worker.count(),
            Banned.count_active(),
            Abs.count(),
            BannedAbs.count(),
            Admin.count_distinct_users(),
            Admin.get_by_tg_id(callback.message.chat.id)

        )

        summary = {
            "len_customer": len_customer,
            "len_worker": len_worker,
            "len_banned_users": len_banned_users,
            "len_advertisement": len_advertisement,
            "len_banned_advertisement": len_banned_advertisement,
            "len_users": len_users,
            "deleted_abs": admin.deleted_abs if admin else 0,
            "done_abs": admin.done_abs if admin else 0,
            "admin": admin
        }

        _admin_summary_cache["data"] = summary
        _admin_summary_cache["ts"] = now_ts

    text = (
    f'Меню\n\n'
    f'Всего пользователей: {summary.get("len_users", 0)}\n'
    f'Заказчиков: {summary.get("len_customer", 0)}\n'
    f'Исполнителей: {summary.get("len_worker", 0)}\n'
    f'Заблокировано: {summary.get("len_banned_users", 0)}\n'
    f'Размещено объявлений: {summary.get("len_advertisement", 0)}\n'
    f'Заблокировано объявлений: {summary.get("len_banned_advertisement", 0)}\n'
    f'Удалено объявлений: {summary.get("deleted_abs", 0)}\n'
    f'Выполнено объявлений: {summary.get("done_abs", 0)}\n'
    )

    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=text, reply_markup=kbc.menu_admin_keyboard())
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('close_'))
async def confirm_block(callback: CallbackQuery) -> None:
    """Подтверждение блокировки - удаляет объявление и фото, но оставляет пользователя заблокированным"""
    logger.debug(f'confirm_block...')
    
    # Парсим callback_data: close_{banned_abs_id}
    parts = callback.data.split('_')
    if len(parts) < 2:
        await callback.message.delete()
        await callback.message.answer("Ошибка: не удалось получить ID объявления.")
        return
    
    try:
        banned_abs_id = int(parts[1])
    except ValueError:
        await callback.message.delete()
        await callback.message.answer("Ошибка: неверный ID объявления.")
        return
    
    # Удаляем объявление и фото (как в unban-user_, но без разблокировки пользователя)
    banned_abs = await BannedAbs.get_one(id=banned_abs_id)
    if banned_abs:
        await banned_abs.delete(delite_photo=True)
        await callback.message.delete_reply_markup()
        await callback.message.edit_caption(
            caption=f"✅ {callback.message.caption or 'Блокировка подтверждена'}\n\nОбъявление удалено."
        )
    else:
        await callback.message.delete()
        await callback.message.answer("Объявление уже было удалено.")


@router.callback_query(F.data == 'close')
async def choose_city_end(callback: CallbackQuery) -> None:
    logger.debug(f'choose_city_end...')
    await callback.message.delete()


@router.callback_query(F.data == "admin_choose_city_for_workers_ref", AdminStates.menu)
async def admin_choose_city_for_workers_main_ref(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_workers_main_ref...')
    kbc = KeyboardCollection()

    await state.set_state(AdminStates.msg_to_worker_choose_city_ref)

    cities = await City.get_all()
    city_names = [city.city for city in cities]
    city_ids = [city.id for city in cities]
    count_cities = len(city_names)
    id_now = 0

    btn_next = True if len(city_names) > 5 else False

    city_names, city_ids = help_defs.get_obj_name_and_id_for_btn(names=city_names, ids=city_ids,
                                                                 id_now=id_now)

    await callback.message.answer(
        text=f'Пожалуйста выберите город\n'
             f'Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(id_now=id_now, ids=city_ids, names=city_names,
                                    btn_next=btn_next, btn_back=False)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.msg_to_worker_choose_city_ref)
async def admin_choose_city_for_workers_next(callback: CallbackQuery) -> None:
    logger.debug(f'admin_choose_city_for_workers_next_ref...')
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

    await callback.message.answer(
        text=f'Пожалуйста выберите город\n'
             f' Показано {id_now + len(city_names)} из {count_cities}',
        reply_markup=kbc.choose_obj(
            id_now=id_now,
            ids=city_ids,
            names=city_names,
            btn_next=btn_next,
            btn_back=btn_back
        )
    )


@router.callback_query(lambda c: c.data.startswith('obj-id_'), AdminStates.msg_to_worker_choose_city_ref)
async def admin_choose_city_for_workers_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_choose_city_for_workers_end_ref...')

    city_id = int(callback.data.split('_')[1])

    msg = await callback.message.answer(text='Напишите ваше обращение к исполнителям')
    await state.set_state(AdminStates.msg_to_worker_text_city_ref)
    await state.update_data(msg_id=msg.message_id)
    await state.update_data(city_id=city_id)


@router.message(F.text, AdminStates.msg_to_worker_text_city_ref)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_text_ref...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    city_id = str(state_data.get('city_id'))
    message_to_worker = message.text

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    except TelegramBadRequest:
        pass

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_worker_photo_city_ref)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_worker=message_to_worker)
    await state.update_data(city_id=city_id)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_worker_photo_city_ref)
async def msg_to_worker_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_skip_city_ref...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_worker = str(state_data.get('message_to_worker'))
    city_id = int(state_data.get('city_id'))

    msg = await callback.message.answer('Подождите, идет отправка')

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            if not await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                try:
                    message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                    await bot.send_message(chat_id=worker.tg_id, text=message_to_worker)
                except TelegramBadRequest:
                    pass
                message_to_worker = str(state_data.get('message_to_worker'))

    city = await City.get_city(id=city_id)

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    except TelegramBadRequest:
        pass
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=f'Сообщение отправлено всем исполнителям из {city.city}!',
                                  reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_worker_photo_city_ref)
async def msg_to_worker_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_worker_photo_city_ref...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = int(state_data.get('msg'))
    message_to_worker = str(state_data.get('message_to_worker'))
    city_id = int(state_data.get('city_id'))
    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    except TelegramBadRequest:
        pass
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    workers = await Worker.get_all_in_city(city_id=city_id)
    if workers:
        for worker in workers:
            try:
                message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_worker)
            except TelegramBadRequest:
                pass
            message_to_worker = str(state_data.get('message_to_worker'))

    help_defs.delete_file(file_path_photo)

    city = await City.get_city(id=city_id)

    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=msg.message_id)
    except TelegramBadRequest:
        pass
    await state.set_state(AdminStates.menu)
    await message.answer(text=f'Сообщение отправлено всем исполнителям из {city.city}!', reply_markup=kbc.menu_btn())


@router.callback_query(lambda c: c.data.startswith('admin_for_workers_ref'), AdminStates.menu)
async def admin_choose_city_for_workers_end(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_msg_for_all_workers_ref...')

    msg = await callback.message.answer(text='Напишите ваше обращение к исполнителям')
    await state.set_state(AdminStates.msg_to_worker_text_ref)
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, AdminStates.msg_to_worker_text_ref)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_worker_text_ref...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))
    message_to_worker = message.text

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    except TelegramBadRequest:
        pass

    msg = await message.answer(text='Прикрепите фото, или нажмите кнопку пропустить', reply_markup=kbc.skip_btn_admin())

    await state.set_state(AdminStates.msg_to_worker_photo_ref)
    await state.update_data(msg=msg.message_id)
    await state.update_data(message_to_worker=message_to_worker)


@router.callback_query(F.data == 'skip_it', AdminStates.msg_to_worker_photo_ref)
async def msg_to_worker_skip(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_worker_skip_ref...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    message_to_worker = str(state_data.get('message_to_worker'))

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            if not await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                try:
                    message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                    await bot.send_message(chat_id=worker.tg_id, text=message_to_worker)
                except TelegramBadRequest:
                    pass
                message_to_worker = str(state_data.get('message_to_worker'))

    await state.set_state(AdminStates.menu)
    await callback.message.answer(
        text=f'Сообщение отправлено всем исполнителям!',
        reply_markup=kbc.menu_btn()
    )


@router.message(F.photo, AdminStates.msg_to_worker_photo_ref)
async def msg_to_worker_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_worker_photo_ref...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    msg = str(state_data.get('msg'))
    message_to_worker = str(state_data.get('message_to_worker'))

    try:
        await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    except TelegramBadRequest:
        pass
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(
        id=message.from_user.id,
        path='app/data/database/abs_from_admin_photo/'
    )
    await bot.download(file=photo, destination=file_path_photo)

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            try:
                message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                await bot.send_photo(
                    chat_id=worker.tg_id,
                    photo=FSInputFile(file_path_photo),
                    caption=message_to_worker
                )
            except TelegramBadRequest:
                pass
            message_to_worker = str(state_data.get('message_to_worker'))

    help_defs.delete_file(file_path_photo)
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    except TelegramBadRequest:
        pass
    await state.set_state(AdminStates.menu)
    await message.answer(text=f'Сообщение отправлено всем исполнителя!', reply_markup=kbc.menu_btn())


@router.callback_query(lambda c: c.data.startswith('look-abs-customer_'), AdminStates.get_customer)
async def abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')
    kbc = KeyboardCollection()

    customer_id = int(callback.data.split('_')[1])

    advertisements = await Abs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        customer = await Customer.get_customer(id=customer_id)
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await state.set_state(AdminStates.get_user)
        await state.update_data(user_id=customer.tg_id)
        return

    await state.set_state(AdminStates.check_abs)
    await state.update_data(customer_id=customer_id)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    text = help_defs.read_text_file(abs_now.text_path)

    text = f'Объявление #{abs_now.id}\n\n' + text
    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin(
                id_now=0,
                btn_next=btn_next,
                btn_back=False,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.count_photo,
                idk_photo=0
            )
        )
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_obj_with_out_list_admin(id_now=0, btn_next=btn_next,
                                                                                  btn_back=False,
                                                                                  btn_block=True,
                                                                                  btn_delete=True,
                                                                                  abs_id=abs_now.id,
                                                                                  customer_id=customer_id))


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))

    advertisements = await Abs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await state.set_state(AdminStates.menu)
        return

    abs_now = advertisements[abs_list_id]

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    text = help_defs.read_text_file(abs_now.text_path)

    text = f'Объявление #{abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass

        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.count_photo,
                idk_photo=0
            )
        )
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text=text, reply_markup=kbc.choose_obj_with_out_list_admin(id_now=abs_list_id,
                                                                                             btn_next=btn_next,
                                                                                             btn_back=btn_back,
                                                                                             btn_block=True,
                                                                                             btn_delete=True,
                                                                                             abs_id=abs_now.id,
                                                                                             customer_id=customer_id))


@router.callback_query(lambda c: c.data.startswith('go-to-next-adm_'), AdminStates.check_abs)
async def check_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))

    advertisements = await Abs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await state.set_state(AdminStates.menu)
        return

    abs_now = advertisements[abs_list_id]

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    if photo_id <= -1:
        photo_id = abs_now.count_photo - 1
    elif photo_id > (abs_now.count_photo - 1):
        photo_id = 0

    if abs_now.photo_path:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=FSInputFile(abs_now.photo_path[str(photo_id)]),
                caption=callback.message.caption),
            reply_markup=kbc.choose_obj_with_out_list_admin(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.count_photo,
                idk_photo=photo_id
            )
        )
        return


@router.callback_query(lambda c: c.data.startswith('block-it-all_'), AdminStates.check_abs)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    advertisement = await Abs.get_one(id=advertisement_id)
    customer = await Customer.get_customer(id=advertisement.customer_id)
    banned = await Banned.get_banned(tg_id=customer.tg_id)

    ban_end = str(datetime.now() + timedelta(hours=24))

    if banned:
        if banned.ban_counter >= 3:
            await banned.update(forever=True, ban_now=True)
            try:
                await bot.send_message(chat_id=banned.tg_id,
                                       text='Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                       reply_markup=kbc.support_btn())
            except Exception:
                pass
            return
        await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
        try:
            await bot.send_message(chat_id=banned.tg_id, text='Вы заблокированы на 24 за нарушение правил платформы',
                                   reply_markup=kbc.support_btn())
        except Exception:
            pass
    else:
        new_banned = Banned(id=None, tg_id=customer.tg_id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False, ban_reason='по решению администратора')
        await new_banned.save()
        try:
            await bot.send_message(chat_id=customer.tg_id, text='Вы заблокированы на 24 за нарушение правил платформы',
                                   reply_markup=kbc.support_btn())
        except Exception:
            pass

    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=advertisement.id)
    if workers_and_bad_responses is not None:
        [await workers_and_bad_response.delete() for workers_and_bad_response in workers_and_bad_responses]
    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=advertisement.id)
    if workers_and_reports is not None:
        [await workers_and_report.delete() for workers_and_report in workers_and_reports]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            if worker is None:
                continue

            # Отправляем уведомление всем откликнувшимся исполнителям
            # (исполнитель уже откликнулся, значит город и направление подходят)
            try:
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление #{advertisement.id} неактуально')
            except Exception:
                pass
            await worker_and_abs.delete()

    await advertisement.delete(delite_photo=True)
    await state.set_state(AdminStates.add_comment_to_lock)
    await callback.message.delete()
    msg = await callback.message.answer(text='Введите комментарий для блокировки', reply_markup=kbc.skip_btn_admin())
    await state.update_data(customer_id=customer.id, msg_id=msg.message_id)


@router.callback_query(F.data == 'skip_it', AdminStates.add_comment_to_lock)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'block_advertisement skip_it...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))

    customer = await Customer.get_customer(id=customer_id)
    user_id = customer.tg_id
    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += f'Пользователь заблокирован\nПричина блокировки: {user_blocked.ban_reason}\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                           worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        status_string = await help_defs.get_worker_status_string(worker.id)

        text += (
            f'Профиль исполнителя\n\n'
            f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}\n'
            f'Статус: {status_string}\n'
            f'Общий ID исполнителя: {worker.tg_id}\n'
        )
        rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
        text += (
            f'Ваш рейтинг: {rating_display}⭐️ ({count_ratings} {help_defs.get_grade_word(count_ratings)})\n'
            f'{cites}\n'
            f'Выполненных заказов: {worker.order_count}\n'
            f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
        )  # Закрывающая скобка для многострочной строки

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += (
            'Профиль заказчика\n\n'
            f'ID: {customer.id}\n'
            f'Общий ID: {customer.tg_id}\n'
            f'Город заказчика: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
        )

    await state.set_state(AdminStates.get_user)

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False
        await callback.message.answer(
            text=text,
            protect_content=False,
            reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id)
        )
        await callback.message.delete()
        await state.update_data(user_id=user_id)
        return
    else:
        await callback.message.answer(text='Упс, такого пользователя нет', reply_markup=kbc.admin_back_btn('menu'))
        return


@router.message(F.text, AdminStates.add_comment_to_lock)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'block_advertisement text...')

    kbc = KeyboardCollection()

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))
    msg_id = int(state_data.get('msg_id'))

    customer = await Customer.get_customer(id=customer_id)
    msg_to_send = message.text

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    except TelegramBadRequest:
        pass

    banned = await Banned.get_banned(tg_id=customer.tg_id)
    await banned.update(ban_reason=msg_to_send)

    await message.answer(
        text='Сообщение пользователю отправлено',
        reply_markup=kbc.admin_back_btn(f'get-user_{customer_id}')
    )
    try:
        await bot.send_message(chat_id=customer.tg_id, text=f'Сообщение от администрации бота: "{msg_to_send}"')
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('delete-it_'), AdminStates.check_abs)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    advertisement = await Abs.get_one(id=advertisement_id)
    customer = await Customer.get_customer(id=advertisement.customer_id)

    workers_and_bad_responses = await WorkerAndBadResponse.get_by_abs(abs_id=advertisement.id)
    if workers_and_bad_responses is not None:
        [await workers_and_bad_response.delete() for workers_and_bad_response in workers_and_bad_responses]
    workers_and_reports = await WorkerAndReport.get_by_abs(abs_id=advertisement.id)
    if workers_and_reports is not None:
        [await workers_and_report.delete() for workers_and_report in workers_and_reports]

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            if worker is None:
                continue

            # Отправляем уведомление всем откликнувшимся исполнителям
            # (исполнитель уже откликнулся, значит город и направление подходят)
            try:
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление #{advertisement.id} неактуально')
            except Exception:
                pass
            await worker_and_abs.delete()

    await advertisement.delete(delite_photo=True)
    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)

    if not advertisements:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='У вас пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(AdminStates.menu)
        return

    while advertisement_id >= len(advertisements):
        advertisement_id -= 1

    if len(advertisements) - 1 > advertisement_id:
        btn_next = True
    else:
        btn_next = False

    if advertisement_id == 0:
        btn_back = False
    else:
        btn_back = True

    advertisement_now = advertisements[advertisement_id]

    text = f'Объявление{advertisement_now.id}\n\n' + help_defs.read_text_file(advertisement_now.text_path)
    logger.debug(f"text {text}")
    if advertisement_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(advertisement_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin(
                id_now=advertisement_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=advertisement_now.id,
                customer_id=customer.id,
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
        reply_markup=kbc.choose_obj_with_out_list_admin(
            id_now=advertisement_id,
            btn_next=btn_next,
            btn_back=btn_back,
            btn_block=True,
            btn_delete=True,
            abs_id=advertisement_now.id,
            customer_id=customer.id
        )
    )


@router.callback_query(lambda c: c.data.startswith('back-to-customer_'),
                       StateFilter(AdminStates.get_user, AdminStates.check_banned_abs, AdminStates.check_abs))
async def back_to_customer(callback: CallbackQuery, state: FSMContext) -> None:
    customer_id = int(callback.data.split('_')[1])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    customer = await Customer.get_customer(id=customer_id)
    user_id = customer.tg_id

    await state.set_state(AdminStates.get_user)

    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += f'Пользователь заблокирован\nПричина блокировки: {user_blocked.ban_reason}\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
                           worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        status_string = await help_defs.get_worker_status_string(worker.id)

        rating_display, count_ratings = help_defs.get_worker_rating_display(worker.stars, worker.count_ratings)
        text += (
            f'Профиль исполнителя\n\n'
            f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}\n'
            f'Статус: {status_string}\n'
            f'Общий ID исполнителя: {worker.tg_id}\n'
            f'Ваш рейтинг: {rating_display} ⭐️ ({count_ratings} {help_defs.get_grade_word(count_ratings)})\n'
            f'{cites}\n'
            f'Выполненных заказов: {worker.order_count}\n'
            f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
        )  # Закрывающая скобка для многострочной строки

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += (
            'Профиль заказчика\n\n'
            f'ID: {customer.id}\n'
            f'Общий ID: {customer.tg_id}\n'
            f'Город заказчика: {city.city}\n'
            f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n'
        )

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False

        if worker:
            if worker.profile_photo:
                await callback.message.answer_photo(
                    caption=text,
                    photo=FSInputFile(worker.profile_photo),
                    protect_content=False,
                    reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id)
                )
            else:
                await callback.message.answer(
                    text=text,
                    protect_content=False,
                    reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id)
                )
        else:
            await callback.message.answer(
                text=text,
                protect_content=False,
                reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id)
            )
        await callback.message.delete()
        await state.update_data(user_id=user_id)
        return
    else:
        await callback.message.answer(text='Упс, такого пользователя нет', reply_markup=kbc.admin_back_btn('menu'))
        await callback.message.delete()

        return


@router.callback_query(lambda c: c.data.startswith('look-banned-abs-customer_'), AdminStates.get_customer)
async def banned_abs_in_city(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'my_abs...')
    kbc = KeyboardCollection()

    customer_id = int(callback.data.split('_')[1])

    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        customer = await Customer.get_customer(id=customer_id)
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await callback.message.delete()
        await state.set_state(AdminStates.get_user)
        await state.update_data(user_id=customer.tg_id)
        return

    await state.set_state(AdminStates.check_banned_abs)
    await state.update_data(customer_id=customer_id)

    abs_now = advertisements[0]
    if len(advertisements) > 1:
        btn_next = True
    else:
        btn_next = False

    text = help_defs.read_text_file(abs_now.text_path)

    text = f'Объявление {abs_now.id}\n\n' + text
    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin_var(
                id_now=0,
                btn_next=btn_next,
                btn_back=False,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.photos_len,
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
        reply_markup=kbc.choose_obj_with_out_list_admin_var(
            id_now=0,
            btn_next=btn_next,
            btn_back=False,
            btn_block=True,
            btn_delete=True,
            abs_id=abs_now.id,
            customer_id=customer_id)
    )


@router.callback_query(lambda c: c.data.startswith('go_'), AdminStates.check_banned_abs)
async def check_banned_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()
    abs_list_id = int(callback.data.split('_')[1])
    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))

    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await state.set_state(AdminStates.menu)
        return

    abs_now = advertisements[abs_list_id]

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    text = help_defs.read_text_file(abs_now.text_path)

    text = f'Объявление {abs_now.id}\n\n' + text

    if abs_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(abs_now.photo_path['0']),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin_var(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.photos_len,
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
        reply_markup=kbc.choose_obj_with_out_list_admin_var(
            id_now=abs_list_id,
            btn_next=btn_next,
            btn_back=btn_back,
            btn_block=True,
            btn_delete=True,
            abs_id=abs_now.id,
            customer_id=customer_id)
    )


@router.callback_query(lambda c: c.data.startswith('go-to-next-adm_'), AdminStates.check_banned_abs)
async def check_banned_abs(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'check_abs...')
    kbc = KeyboardCollection()

    photo_id = int(callback.data.split('_')[1])
    abs_list_id = int(callback.data.split('_')[2])

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))

    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer_id)

    if not advertisements:
        await callback.message.answer(text='Объявлений нет', reply_markup=kbc.back_to_user(customer_id=customer_id))
        await state.set_state(AdminStates.menu)
        return

    abs_now = advertisements[abs_list_id]

    if len(advertisements) - 1 > abs_list_id:
        btn_next = True
    else:
        btn_next = False

    if abs_list_id == 0:
        btn_back = False
    else:
        btn_back = True

    if photo_id <= -1:
        photo_id = abs_now.count_photo - 1
    elif photo_id > (abs_now.count_photo - 1):
        photo_id = 0

    if abs_now.photo_path:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=FSInputFile(abs_now.photo_path[str(photo_id)]),
                caption=callback.message.caption),
            reply_markup=kbc.choose_obj_with_out_list_admin_var(
                id_now=abs_list_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=abs_now.id,
                customer_id=customer_id,
                count_photo=abs_now.photos_len,
                idk_photo=photo_id
            )
        )
        return


@router.callback_query(lambda c: c.data.startswith('unblock-it-all_'), AdminStates.check_banned_abs)
async def unblock_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'unblock_advertisement...')

    kbc = KeyboardCollection()

    banned_advertisement = await BannedAbs.get_one(id=advertisement_id)
    customer = await Customer.get_customer(id=banned_advertisement.customer_id)
    banned = await Banned.get_banned(tg_id=customer.tg_id)

    if banned:
        if banned.ban_counter == 1:
            await banned.delete()
        else:
            if banned.forever:
                await banned.update(
                    ban_counter=banned.ban_counter - 1,
                    ban_now=False,
                    ban_end=None,
                    forever=False
                )
            else:
                await banned.update(
                    ban_counter=banned.ban_counter - 1,
                    ban_now=False,
                    ban_end=None
                )

    text_path = help_defs.copy_file(banned_advertisement.text_path, f'app/data/text/{customer.tg_id}/')

    if not text_path:
        await banned_advertisement.delete(delite_photo=True)
        await callback.message.delete()
        await callback.message.answer('Пользователь разблокирован')
        try:
            await bot.send_message(
                chat_id=customer.tg_id,
                text='Вы были разблокированы, приносим извинения за предоставленные неудобства.\nВызовите команду /menu чтобы продолжить работу'
            )
        except Exception:
            pass
        return

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=banned_advertisement.work_type_id,
        city_id=customer.city_id,
        photo_path=banned_advertisement.photo_path,
        text_path=text_path,
        date_to_delite=datetime.today() + timedelta(days=30),
        count_photo=banned_advertisement.photos_len
    )
    await new_abs.save()

    advertisements = await Abs.get_all_by_customer(customer_id=customer.id)
    advertisement = advertisements[-1]

    text = help_defs.read_text_file(text_path)

    text = f'Объявление{advertisement.id}\n\n' + text

    workers = await Worker.get_all_in_city(city_id=customer.city_id)

    if workers:
        for worker in workers:
            if worker.tg_id == customer.tg_id:
                continue
            if not worker.active:
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            try:
                if worker_sub.work_type_ids:
                    if advertisement.work_type_id in worker_sub.work_type_ids:
                        if banned_advertisement.photo_path:
                            await bot.send_photo(
                                chat_id=worker.tg_id,
                                photo=FSInputFile(banned_advertisement.photo_path['0']),
                                caption=text,
                                reply_markup=kbc.apply_btn(advertisement.id)
                            )
                        else:
                            await bot.send_message(
                                chat_id=worker.tg_id,
                                text=text,
                                reply_markup=kbc.apply_btn(advertisement.id)
                            )
            except Exception:
                pass

    await banned_advertisement.delete(delite_photo=False)
    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer.id)

    if not advertisements:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(AdminStates.menu)
        return

    while advertisement_id >= len(advertisements):
        advertisement_id -= 1

    if len(advertisements) - 1 > advertisement_id:
        btn_next = True
    else:
        btn_next = False

    if advertisement_id == 0:
        btn_back = False
    else:
        btn_back = True

    advertisement_now = advertisements[advertisement_id]

    text = f'Объявление {advertisement_now.id}\n\n' + help_defs.read_text_file(advertisement_now.text_path)
    logger.debug(f"text {text}")
    if advertisement_now.photo_path:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer_photo(
            photo=FSInputFile(advertisement_now.photo_path),
            caption=text,
            reply_markup=kbc.choose_obj_with_out_list_admin_var(
                id_now=advertisement_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=advertisement_now.id,
                customer_id=customer.id
            )
        )
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_obj_with_out_list_admin_var(
            id_now=advertisement_id,
            btn_next=btn_next,
            btn_back=btn_back,
            btn_block=True,
            btn_delete=True,
            abs_id=advertisement_now.id,
            customer_id=customer.id
        )
    )


@router.callback_query(lambda c: c.data.startswith('unblock-user-it_'), AdminStates.check_banned_abs)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    banned_advertisement = await BannedAbs.get_one(id=advertisement_id)
    customer = await Customer.get_customer(id=banned_advertisement.customer_id)
    banned = await Banned.get_banned(tg_id=customer.tg_id)

    if banned.ban_counter == 1:
        await banned.delete()
    else:
        if banned.forever:
            await banned.update(
                ban_counter=banned.ban_counter - 1,
                ban_now=False,
                ban_end=None,
                forever=False
            )
        else:
            await banned.update(
                ban_counter=banned.ban_counter - 1,
                ban_now=False,
                ban_end=None
            )
    try:
        await bot.send_message(
            chat_id=customer.tg_id,
            text='Вы были разблокированы, приносим извинения за предоставленные неудобства.\nВызовите команду /menu чтобы продолжить работу'
        )
    except Exception:
        pass

    await banned_advertisement.delete(delite_photo=True)
    advertisements = await BannedAbs.get_all_by_customer(customer_id=customer.id)

    if not advertisements:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(text='Пока нет объявлений', reply_markup=kbc.menu())
        await state.set_state(AdminStates.menu)
        return

    while advertisement_id >= len(advertisements):
        advertisement_id -= 1

    if len(advertisements) - 1 > advertisement_id:
        btn_next = True
    else:
        btn_next = False

    if advertisement_id == 0:
        btn_back = False
    else:
        btn_back = True

    advertisement_now = advertisements[advertisement_id]

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
            reply_markup=kbc.choose_obj_with_out_list_admin_var(
                id_now=advertisement_id,
                btn_next=btn_next,
                btn_back=btn_back,
                btn_block=True,
                btn_delete=True,
                abs_id=advertisement_now.id,
                customer_id=customer.id
            )
        )
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(
        text=text,
        reply_markup=kbc.choose_obj_with_out_list_admin_var(
            id_now=advertisement_id,
            btn_next=btn_next,
            btn_back=btn_back,
            btn_block=True,
            btn_delete=True,
            abs_id=advertisement_now.id,
            customer_id=customer.id
        )
    )


@router.callback_query(lambda c: c.data.startswith('admin_delete_worker_name_'))
async def admin_delete_worker_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Удаление имени исполнителя администратором с системой предупреждений"""
    logger.debug(f'admin_delete_worker_name...')

    try:
        if not callback.data:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        parts = callback.data.split('_')
        logger.debug(f'admin_delete_worker_name callback.data: {callback.data}, parts: {parts}, len: {len(parts)}')

        if len(parts) < 6:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        try:
            worker_id = int(parts[4])
            worker_tg_id = int(parts[5])
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при парсинге ID из callback.data: {callback.data}, parts: {parts}, error: {e}")
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        worker = await Worker.get_worker(id=worker_id)
        if not worker:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        # Увеличиваем счетчик нарушений
        new_violations_count = (worker.name_violations_count or 0) + 1
        await worker.update_name_violations_count(new_violations_count)

        # Обнуляем имя
        await worker.update_profile_name(profile_name="")

        # Удаляем сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass

        # Система предупреждений и блокировок
        if new_violations_count == 3:
            # 3-й раз - блокировка навсегда
            banned = await Banned.get_banned(tg_id=worker_tg_id)
            ban_reason = "Повторные нарушения правил платформы (имя)"

            if banned:
                await banned.update(forever=True, ban_now=True, ban_reason=ban_reason)
            else:
                banned = Banned(
                    id=None,
                    tg_id=worker_tg_id,
                    ban_counter=3,
                    ban_end=None,
                    ban_now=True,
                    forever=True,
                    ban_reason=ban_reason
                )
                await banned.save()

            # Отправляем уведомление исполнителю
            try:
                await bot.send_message(
                    chat_id=worker_tg_id,
                    text="🚫 Ваш аккаунт заблокирован за повторные нарушения правил платформы!",
                    reply_markup=KeyboardCollection().support_btn_simple()
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления о блокировке: {e}")

            await callback.message.answer(
                f"✅ Имя удалено. Исполнитель #{worker_id} заблокирован навсегда (3 нарушения)")

        elif new_violations_count == 1 or new_violations_count == 2:
            # 1-й или 2-й раз - предупреждение и перенаправление
            try:
                kbc = KeyboardCollection()

                warning_text = f"⚠️ Укажите своё настоящее имя — рекламные или выдуманные имена не допускаются. ({new_violations_count}/3)"

                await bot.send_message(
                    chat_id=worker_tg_id,
                    text=warning_text,
                    reply_markup=kbc.change_name_button(),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке предупреждения: {e}")

            await callback.message.answer(
                f"✅ Имя удалено. Исполнителю #{worker_id} отправлено предупреждение ({new_violations_count}/3)")

    except Exception as e:
        logger.error(f"Ошибка в admin_delete_worker_name: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== УПРАВЛЕНИЕ ТАРИФАМИ КОНТАКТОВ ==========

@router.callback_query(F.data == 'manage_contact_tariffs', StateFilter(AdminStates.menu,
                                                                       AdminStates.view_contact_tariff,
                                                                       AdminStates.edit_contact_tariff_name,
                                                                       AdminStates.edit_contact_tariff_price,
                                                                       AdminStates.edit_contact_tariff_contacts_count,
                                                                       AdminStates.edit_contact_tariff_unlimited_days,
                                                                       AdminStates.add_contact_tariff_type,
                                                                       AdminStates.add_contact_tariff_name,
                                                                       AdminStates.add_contact_tariff_contacts_count,
                                                                       AdminStates.add_contact_tariff_price,
                                                                       AdminStates.add_contact_tariff_unlimited_days))
async def manage_contact_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    """Главное меню управления тарифами контактов"""
    logger.debug('manage_contact_tariffs...')
    kbc = KeyboardCollection()

    tariffs = await ContactTariff.get_all()
    text = f'💰 <b>Управление тарифами контактов</b>\n\n'
    text += f'📊 Всего тарифов: {len(tariffs)}\n\n'
    text += f'Выберите тариф для редактирования или добавьте новый:'

    await state.set_state(AdminStates.manage_contact_tariffs)
    await callback.message.answer(
        text=text,
        reply_markup=await kbc.admin_contact_tariffs_list(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_view_tariff_'),
                       StateFilter(AdminStates.manage_contact_tariffs,
                                   AdminStates.view_contact_tariff,
                                   AdminStates.edit_contact_tariff_name,
                                   AdminStates.edit_contact_tariff_price,
                                   AdminStates.edit_contact_tariff_contacts_count,
                                   AdminStates.edit_contact_tariff_unlimited_days))
async def admin_view_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    """Просмотр информации о тарифе"""
    logger.debug('admin_view_tariff...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[3])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price / 100
    text = f'💰 <b>Информация о тарифе</b>\n\n'
    text += f'📋 <b>Название:</b> {tariff.name}\n'
    text += f'💵 <b>Цена:</b> {int(price_rub)}₽ ({tariff.price} копеек)\n'

    if tariff.unlimited:
        text += f'🔥 <b>Тип:</b> Безлимитный\n'
        text += f'⏰ <b>Срок действия:</b> {tariff.unlimited_days} дней'
    else:
        text += f'📊 <b>Тип:</b> Ограниченный\n'
        text += f'📞 <b>Количество контактов:</b> {tariff.contacts_count}'

    await state.set_state(AdminStates.view_contact_tariff)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_edit_contact_tariff(tariff_id),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_edit_tariff_name_'),
                       StateFilter(AdminStates.view_contact_tariff))
async def admin_edit_tariff_name_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования названия тарифа"""
    logger.debug('admin_edit_tariff_name_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    text = f'✏️ <b>Редактирование названия тарифа</b>\n\n'
    text += f'Текущее название: <b>{tariff.name}</b>\n\n'
    text += f'Введите новое название:'

    await state.set_state(AdminStates.edit_contact_tariff_name)
    await state.update_data(tariff_id=tariff_id)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_contact_tariff_name))
async def process_edit_tariff_name(message: Message, state: FSMContext) -> None:
    """Обработка нового названия тарифа"""
    logger.debug('process_edit_tariff_name...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    tariff_id = state_data.get('tariff_id')

    try:
        new_name = message.text.strip()
        if not new_name or len(new_name) > 100:
            await message.answer('❌ Название не может быть пустым или длиннее 100 символов',
                                 reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'))
            return

        tariff = await ContactTariff.get_by_id(tariff_id)
        if not tariff:
            await message.answer('❌ Тариф не найден', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))
            await state.set_state(AdminStates.menu)
            return

        await tariff.update(name=new_name)
        await message.answer(
            text=f'✅ <b>Название успешно изменено!</b>\n\nНовое название: <b>{new_name}</b>',
            reply_markup=kbc.admin_edit_contact_tariff(tariff_id),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.view_contact_tariff)
    except Exception as e:
        logger.error(f"Ошибка при изменении названия тарифа: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))


@router.callback_query(lambda c: c.data.startswith('admin_edit_tariff_price_'),
                       StateFilter(AdminStates.view_contact_tariff))
async def admin_edit_tariff_price_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования цены тарифа"""
    logger.debug('admin_edit_tariff_price_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price / 100
    text = f'💰 <b>Редактирование цены тарифа</b>\n\n'
    text += f'Текущая цена: <b>{int(price_rub)}₽</b> ({tariff.price} копеек)\n\n'
    text += f'Введите новую цену в рублях:'

    await state.set_state(AdminStates.edit_contact_tariff_price)
    await state.update_data(tariff_id=tariff_id)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_contact_tariff_price))
async def process_edit_tariff_price(message: Message, state: FSMContext) -> None:
    """Обработка новой цены тарифа"""
    logger.debug('process_edit_tariff_price...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    tariff_id = state_data.get('tariff_id')

    try:
        price_rub = float(message.text.replace(',', '.').strip())
        if price_rub <= 0:
            raise ValueError("Цена должна быть положительным числом")

        price_kopecks = int(price_rub * 100)

        tariff = await ContactTariff.get_by_id(tariff_id)
        if not tariff:
            await message.answer('❌ Тариф не найден', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))
            await state.set_state(AdminStates.menu)
            return

        await tariff.update(price=price_kopecks)
        await message.answer(
            text=f'✅ <b>Цена успешно изменена!</b>\n\nНовая цена: <b>{int(price_rub)}₽</b> ({price_kopecks} копеек)',
            reply_markup=kbc.admin_edit_contact_tariff(tariff_id),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.view_contact_tariff)
    except ValueError as e:
        await message.answer(
            text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректную цену (положительное число).\nНапример: 190, 290, 1990',
            reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении цены тарифа: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))


@router.callback_query(lambda c: c.data.startswith('admin_edit_tariff_contacts_'),
                       StateFilter(AdminStates.view_contact_tariff))
async def admin_edit_tariff_contacts_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования количества контактов"""
    logger.debug('admin_edit_tariff_contacts_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    if tariff.unlimited:
        await callback.answer("⚠️ Для безлимитных тарифов количество контактов не редактируется", show_alert=True)
        return

    text = f'📊 <b>Редактирование количества контактов</b>\n\n'
    text += f'Текущее количество: <b>{tariff.contacts_count}</b>\n\n'
    text += f'Введите новое количество контактов (положительное число):'

    await state.set_state(AdminStates.edit_contact_tariff_contacts_count)
    await state.update_data(tariff_id=tariff_id)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_contact_tariff_contacts_count))
async def process_edit_tariff_contacts(message: Message, state: FSMContext) -> None:
    """Обработка нового количества контактов"""
    logger.debug('process_edit_tariff_contacts...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    tariff_id = state_data.get('tariff_id')

    try:
        contacts_count = int(message.text.strip())
        if contacts_count <= 0:
            raise ValueError("Количество должно быть положительным числом")

        tariff = await ContactTariff.get_by_id(tariff_id)
        if not tariff:
            await message.answer('❌ Тариф не найден', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))
            await state.set_state(AdminStates.menu)
            return

        await tariff.update(contacts_count=contacts_count)
        await message.answer(
            text=f'✅ <b>Количество контактов успешно изменено!</b>\n\nНовое количество: <b>{contacts_count}</b>',
            reply_markup=kbc.admin_edit_contact_tariff(tariff_id),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.view_contact_tariff)
    except ValueError:
        await message.answer(
            text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректное количество (положительное число).',
            reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении количества контактов: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))


@router.callback_query(lambda c: c.data.startswith('admin_edit_tariff_days_'),
                       StateFilter(AdminStates.view_contact_tariff))
async def admin_edit_tariff_days_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования срока безлимита"""
    logger.debug('admin_edit_tariff_days_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    if not tariff.unlimited:
        await callback.answer("⚠️ Это поле редактируется только для безлимитных тарифов", show_alert=True)
        return

    text = f'⏰ <b>Редактирование срока действия безлимита</b>\n\n'
    text += f'Текущий срок: <b>{tariff.unlimited_days}</b> дней ({tariff.unlimited_days // 30} месяцев)\n\n'
    text += f'Введите новое количество дней:'

    await state.set_state(AdminStates.edit_contact_tariff_unlimited_days)
    await state.update_data(tariff_id=tariff_id)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_contact_tariff_unlimited_days))
async def process_edit_tariff_days(message: Message, state: FSMContext) -> None:
    """Обработка нового срока безлимита"""
    logger.debug('process_edit_tariff_days...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    tariff_id = state_data.get('tariff_id')

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError("Количество дней должно быть положительным числом")

        tariff = await ContactTariff.get_by_id(tariff_id)
        if not tariff:
            await message.answer('❌ Тариф не найден', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))
            await state.set_state(AdminStates.menu)
            return

        await tariff.update(unlimited_days=days)
        await message.answer(
            text=f'✅ <b>Срок действия успешно изменен!</b>\n\nНовый срок: <b>{days}</b> дней ({days // 30} месяцев)',
            reply_markup=kbc.admin_edit_contact_tariff(tariff_id),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.view_contact_tariff)
    except ValueError:
        await message.answer(
            text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректное количество дней (положительное число).',
            reply_markup=kbc.admin_back_btn(f'admin_view_tariff_{tariff_id}'),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении срока безлимита: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))


@router.callback_query(lambda c: c.data.startswith('admin_delete_tariff_'),
                       StateFilter(AdminStates.view_contact_tariff))
async def admin_delete_tariff_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик удаления тарифа"""
    logger.debug('admin_delete_tariff_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[3])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price / 100
    text = f'🗑️ <b>Подтверждение удаления тарифа</b>\n\n'
    text += f'Вы действительно хотите удалить тариф:\n'
    text += f'📋 <b>{tariff.name}</b>\n'
    text += f'💵 Цена: {int(price_rub)}₽\n\n'
    text += f'⚠️ <b>Это действие нельзя отменить!</b>'

    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Да, удалить", f"admin_confirm_delete_tariff_{tariff_id}"))
    builder.add(kbc._inline("❌ Отмена", f"admin_view_tariff_{tariff_id}"))
    builder.adjust(1)

    await callback.message.answer(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_confirm_delete_tariff_'))
async def admin_confirm_delete_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение удаления тарифа"""
    logger.debug('admin_confirm_delete_tariff...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await ContactTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    try:
        tariff_name = tariff.name
        await tariff.delete()

        await callback.message.answer(
            text=f'✅ <b>Тариф "{tariff_name}" успешно удален!</b>',
            reply_markup=await kbc.admin_contact_tariffs_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_contact_tariffs)
        await callback.answer("✅ Тариф удален", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при удалении тарифа: {e}")
        await callback.answer("❌ Произошла ошибка при удалении", show_alert=True)


@router.callback_query(F.data == 'admin_add_tariff_type', StateFilter(AdminStates.manage_contact_tariffs,
                                                                      AdminStates.add_contact_tariff_name,
                                                                      AdminStates.add_contact_tariff_contacts_count,
                                                                      AdminStates.add_contact_tariff_price,
                                                                      AdminStates.add_contact_tariff_unlimited_days))
async def admin_add_tariff_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор типа нового тарифа"""
    logger.debug('admin_add_tariff_type...')
    kbc = KeyboardCollection()

    text = f'➕ <b>Добавление нового тарифа</b>\n\n'
    text += f'Выберите тип тарифа:'

    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("📊 Ограниченный (с количеством контактов)", "admin_add_tariff_limited"))
    builder.add(kbc._inline("🔥 Безлимитный (на срок)", "admin_add_tariff_unlimited"))
    builder.add(kbc._inline("🔙 Назад", "manage_contact_tariffs"))
    builder.adjust(1)

    await state.set_state(AdminStates.add_contact_tariff_type)
    await callback.message.answer(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )


@router.callback_query(F.data == 'admin_add_tariff_limited', StateFilter(AdminStates.add_contact_tariff_type))
async def admin_add_tariff_limited_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввод названия для ограниченного тарифа"""
    logger.debug('admin_add_tariff_limited_name...')
    kbc = KeyboardCollection()

    text = f'📊 <b>Добавление ограниченного тарифа</b>\n\n'
    text += f'Введите название тарифа (например: "5 контактов"):'

    await state.set_state(AdminStates.add_contact_tariff_name)
    await state.update_data(tariff_type='limited')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn('admin_add_tariff_type'),
        parse_mode='HTML'
    )


@router.callback_query(F.data == 'admin_add_tariff_unlimited', StateFilter(AdminStates.add_contact_tariff_type))
async def admin_add_tariff_unlimited_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввод названия для безлимитного тарифа"""
    logger.debug('admin_add_tariff_unlimited_name...')
    kbc = KeyboardCollection()

    text = f'🔥 <b>Добавление безлимитного тарифа</b>\n\n'
    text += f'Введите название тарифа (например: "Безлимит 1 месяц"):'

    await state.set_state(AdminStates.add_contact_tariff_name)
    await state.update_data(tariff_type='unlimited')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn('admin_add_tariff_type'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.add_contact_tariff_name))
async def process_add_tariff_name(message: Message, state: FSMContext) -> None:
    """Обработка названия нового тарифа"""
    logger.debug('process_add_tariff_name...')
    kbc = KeyboardCollection()

    tariff_name = message.text.strip()
    if not tariff_name or len(tariff_name) > 100:
        await message.answer('❌ Название не может быть пустым или длиннее 100 символов',
                             reply_markup=kbc.admin_back_btn('admin_add_tariff_type'))
        return

    state_data = await state.get_data()
    tariff_type = state_data.get('tariff_type')

    await state.update_data(tariff_name=tariff_name)

    if tariff_type == 'limited':
        text = f'📊 <b>Количество контактов</b>\n\n'
        text += f'Название: <b>{tariff_name}</b>\n\n'
        text += f'Введите количество контактов (положительное число):'

        await state.set_state(AdminStates.add_contact_tariff_contacts_count)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('admin_add_tariff_type'), parse_mode='HTML')
    else:  # unlimited
        text = f'⏰ <b>Срок действия</b>\n\n'
        text += f'Название: <b>{tariff_name}</b>\n\n'
        text += f'Введите количество дней действия безлимита (например: 30 для месяца):'

        await state.set_state(AdminStates.add_contact_tariff_unlimited_days)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('admin_add_tariff_type'), parse_mode='HTML')


@router.message(F.text, StateFilter(AdminStates.add_contact_tariff_contacts_count))
async def process_add_tariff_contacts(message: Message, state: FSMContext) -> None:
    """Обработка количества контактов для нового тарифа"""
    logger.debug('process_add_tariff_contacts...')
    kbc = KeyboardCollection()

    try:
        contacts_count = int(message.text.strip())
        if contacts_count <= 0:
            raise ValueError("Количество должно быть положительным числом")

        await state.update_data(contacts_count=contacts_count)

        state_data = await state.get_data()
        tariff_name = state_data.get('tariff_name')

        text = f'💰 <b>Цена тарифа</b>\n\n'
        text += f'Название: <b>{tariff_name}</b>\n'
        text += f'Количество контактов: <b>{contacts_count}</b>\n\n'
        text += f'Введите цену в рублях:'

        await state.set_state(AdminStates.add_contact_tariff_price)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('admin_add_tariff_type'), parse_mode='HTML')
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное количество (положительное число)',
                             reply_markup=kbc.admin_back_btn('admin_add_tariff_type'))


@router.message(F.text, StateFilter(AdminStates.add_contact_tariff_unlimited_days))
async def process_add_tariff_days(message: Message, state: FSMContext) -> None:
    """Обработка срока для нового безлимитного тарифа"""
    logger.debug('process_add_tariff_days...')
    kbc = KeyboardCollection()

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError("Количество дней должно быть положительным числом")

        await state.update_data(unlimited_days=days)

        state_data = await state.get_data()
        tariff_name = state_data.get('tariff_name')

        text = f'💰 <b>Цена тарифа</b>\n\n'
        text += f'Название: <b>{tariff_name}</b>\n'
        text += f'Срок действия: <b>{days}</b> дней ({days // 30} месяцев)\n\n'
        text += f'Введите цену в рублях:'

        await state.set_state(AdminStates.add_contact_tariff_price)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('admin_add_tariff_type'), parse_mode='HTML')
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное количество дней (положительное число)',
                             reply_markup=kbc.admin_back_btn('admin_add_tariff_type'))


@router.message(F.text, StateFilter(AdminStates.add_contact_tariff_price))
async def process_add_tariff_price(message: Message, state: FSMContext) -> None:
    """Обработка цены нового тарифа и создание"""
    logger.debug('process_add_tariff_price...')
    kbc = KeyboardCollection()

    try:
        price_rub = float(message.text.replace(',', '.').strip())
        if price_rub <= 0:
            raise ValueError("Цена должна быть положительным числом")

        price_kopecks = int(price_rub * 100)

        state_data = await state.get_data()
        tariff_name = state_data.get('tariff_name')
        tariff_type = state_data.get('tariff_type')

        if tariff_type == 'limited':
            contacts_count = state_data.get('contacts_count')
            new_tariff = ContactTariff(
                id=None,
                name=tariff_name,
                contacts_count=contacts_count,
                price=price_kopecks,
                unlimited=False,
                unlimited_days=None
            )
        else:  # unlimited
            unlimited_days = state_data.get('unlimited_days')
            new_tariff = ContactTariff(
                id=None,
                name=tariff_name,
                contacts_count=-1,
                price=price_kopecks,
                unlimited=True,
                unlimited_days=unlimited_days
            )

        await new_tariff.save()

        # Формируем дополнительную информацию для сообщения
        if tariff_type == 'limited':
            contacts_count = state_data.get('contacts_count')
            extra_info = f'📊 Контактов: <b>{contacts_count}</b>'
        else:
            unlimited_days = state_data.get('unlimited_days')
            extra_info = f'⏰ Срок: <b>{unlimited_days}</b> дней'

        await message.answer(
            text=f'✅ <b>Тариф успешно создан!</b>\n\n'
                 f'📋 Название: <b>{tariff_name}</b>\n'
                 f'💵 Цена: <b>{int(price_rub)}₽</b>\n'
                 f'{extra_info}',
            reply_markup=await kbc.admin_contact_tariffs_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_contact_tariffs)

    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректную цену (положительное число)',
                             reply_markup=kbc.admin_back_btn('admin_add_tariff_type'))
    except Exception as e:
        logger.error(f"Ошибка при создании тарифа: {e}")
        await message.answer('❌ Произошла ошибка при создании тарифа',
                             reply_markup=kbc.admin_back_btn('manage_contact_tariffs'))


# Обработка возврата к списку тарифов из просмотра
@router.callback_query(F.data == 'manage_contact_tariffs', StateFilter(AdminStates.view_contact_tariff,
                                                                       AdminStates.edit_contact_tariff_name,
                                                                       AdminStates.edit_contact_tariff_price,
                                                                       AdminStates.edit_contact_tariff_contacts_count,
                                                                       AdminStates.edit_contact_tariff_unlimited_days,
                                                                       AdminStates.add_contact_tariff_type,
                                                                       AdminStates.add_contact_tariff_name,
                                                                       AdminStates.add_contact_tariff_contacts_count,
                                                                       AdminStates.add_contact_tariff_price,
                                                                       AdminStates.add_contact_tariff_unlimited_days))
async def back_to_tariffs_list(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к списку тарифов"""
    await manage_contact_tariffs(callback, state)


# ========== УПРАВЛЕНИЕ ТАРИФАМИ ГОРОДОВ ==========

@router.callback_query(F.data == 'manage_city_tariffs', StateFilter(AdminStates.menu, AdminStates.manage_city_discounts,
                                                                    AdminStates.add_city_tariff_count,
                                                                    AdminStates.add_city_tariff_price,
                                                                    AdminStates.view_city_tariff,
                                                                    AdminStates.edit_city_tariff_price,
                                                                    AdminStates.view_city_discount))
async def manage_city_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    """Главное меню управления тарифами городов"""
    logger.debug('manage_city_tariffs...')
    kbc = KeyboardCollection()

    tariffs = await CitySubscriptionTariff.get_all()
    text = f'🏙️ <b>Управление тарифами городов</b>\n\n'
    text += f'📊 Всего тарифов: {len(tariffs)}\n\n'
    text += f'Тарифы определяют цену за месяц подписки в зависимости от количества городов.\n\n'
    text += f'Выберите тариф для редактирования или добавьте новый:'

    await state.set_state(AdminStates.manage_city_tariffs)
    await callback.message.answer(
        text=text,
        reply_markup=await kbc.admin_city_tariffs_list(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_view_city_tariff_'),
                       StateFilter(AdminStates.manage_city_tariffs, AdminStates.edit_city_tariff_price,
                                   AdminStates.view_city_tariff))
async def admin_view_city_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    """Просмотр информации о тарифе городов"""
    logger.debug('admin_view_city_tariff...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await CitySubscriptionTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price_per_month / 100

    # Показываем примеры цен с учетом скидок
    discounts = await CitySubscriptionDiscount.get_all()
    text = f'🏙️ <b>Информация о тарифе</b>\n\n'
    text += f'📊 <b>Количество городов:</b> {tariff.city_count}\n'
    text += f'💵 <b>Цена за месяц:</b> {int(price_rub)}₽ ({tariff.price_per_month} копеек)\n\n'
    text += f'<b>Примеры цен с учетом скидок:</b>\n'

    periods = [1, 2, 3, 6, 12]
    for months in periods:
        final_price = await CitySubscriptionDiscount.calculate_price(tariff.price_per_month, months)
        final_price_rub = final_price / 100
        discount = await CitySubscriptionDiscount.get_by_months(months)
        discount_text = f" (скидка {discount.discount_percent}%)" if discount and discount.discount_percent > 0 else ""
        text += f'• {months} месяц{"ев" if months > 1 else ""}: {int(final_price_rub)}₽{discount_text}\n'

    await state.set_state(AdminStates.view_city_tariff)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_edit_city_tariff(tariff_id),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_edit_city_tariff_count_'),
                       StateFilter(AdminStates.view_city_tariff))
async def admin_edit_city_tariff_count_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования количества городов"""
    logger.debug('admin_edit_city_tariff_count_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[5])
    tariff = await CitySubscriptionTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    text = f'🏙️ <b>Редактирование количества городов</b>\n\n'
    text += f'Текущее количество: <b>{tariff.city_count}</b>\n\n'
    text += f'Введите новое количество городов (положительное число):'

    await state.set_state(AdminStates.edit_city_tariff_price)  # Используем существующее состояние
    await state.update_data(tariff_id=tariff_id, editing_field='city_count')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_city_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_edit_city_tariff_price_'),
                       StateFilter(AdminStates.view_city_tariff))
async def admin_edit_city_tariff_price_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования цены тарифа городов"""
    logger.debug('admin_edit_city_tariff_price_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[5])
    tariff = await CitySubscriptionTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price_per_month / 100
    text = f'💰 <b>Редактирование цены тарифа</b>\n\n'
    text += f'Количество городов: <b>{tariff.city_count}</b>\n'
    text += f'Текущая цена за месяц: <b>{int(price_rub)}₽</b> ({tariff.price_per_month} копеек)\n\n'
    text += f'Введите новую цену в рублях за месяц:'

    await state.set_state(AdminStates.edit_city_tariff_price)
    await state.update_data(tariff_id=tariff_id, editing_field='price')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_city_tariff_{tariff_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_city_tariff_price))
async def process_edit_city_tariff(message: Message, state: FSMContext) -> None:
    """Обработка редактирования тарифа городов"""
    logger.debug('process_edit_city_tariff...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    tariff_id = state_data.get('tariff_id')
    editing_field = state_data.get('editing_field')

    try:
        tariff = await CitySubscriptionTariff.get_by_id(tariff_id)
        if not tariff:
            await message.answer('❌ Тариф не найден', reply_markup=kbc.admin_back_btn('manage_city_tariffs'))
            await state.set_state(AdminStates.menu)
            return

        if editing_field == 'city_count':
            city_count = int(message.text.strip())
            if city_count <= 0:
                raise ValueError("Количество должно быть положительным числом")

            # Проверяем, нет ли уже тарифа с таким количеством городов
            existing = await CitySubscriptionTariff.get_by_city_count(city_count)
            if existing and existing.id != tariff_id:
                await message.answer('❌ Тариф с таким количеством городов уже существует!',
                                     reply_markup=kbc.admin_back_btn(f'admin_view_city_tariff_{tariff_id}'))
                return

            await tariff.update(city_count=city_count)
            await message.answer(
                text=f'✅ <b>Количество городов успешно изменено!</b>\n\nНовое количество: <b>{city_count}</b>',
                reply_markup=kbc.admin_edit_city_tariff(tariff_id),
                parse_mode='HTML'
            )
        else:  # editing_field == 'price'
            price_rub = float(message.text.replace(',', '.').strip())
            if price_rub <= 0:
                raise ValueError("Цена должна быть положительным числом")

            price_kopecks = int(price_rub * 100)
            await tariff.update(price_per_month=price_kopecks)
            await message.answer(
                text=f'✅ <b>Цена успешно изменена!</b>\n\nНовая цена за месяц: <b>{int(price_rub)}₽</b> ({price_kopecks} копеек)',
                reply_markup=kbc.admin_edit_city_tariff(tariff_id),
                parse_mode='HTML'
            )

        await state.set_state(AdminStates.view_city_tariff)
    except ValueError as e:
        if "Количество" in str(e):
            await message.answer(
                text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректное количество городов (положительное число).',
                reply_markup=kbc.admin_back_btn(f'admin_view_city_tariff_{tariff_id}'),
                parse_mode='HTML'
            )
        else:
            await message.answer(
                text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректную цену (положительное число).\nНапример: 90, 180, 270',
                reply_markup=kbc.admin_back_btn(f'admin_view_city_tariff_{tariff_id}'),
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка при редактировании тарифа городов: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_city_tariffs'))


@router.callback_query(lambda c: c.data.startswith('admin_delete_city_tariff_'),
                       StateFilter(AdminStates.view_city_tariff))
async def admin_delete_city_tariff_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик удаления тарифа городов"""
    logger.debug('admin_delete_city_tariff_handler...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[4])
    tariff = await CitySubscriptionTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    price_rub = tariff.price_per_month / 100
    text = f'🗑️ <b>Подтверждение удаления тарифа</b>\n\n'
    text += f'Вы действительно хотите удалить тариф:\n'
    text += f'🏙️ <b>{tariff.city_count} городов</b>\n'
    text += f'💵 Цена за месяц: {int(price_rub)}₽\n\n'
    text += f'⚠️ <b>Это действие нельзя отменить!</b>'

    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Да, удалить", f"admin_confirm_delete_city_tariff_{tariff_id}"))
    builder.add(kbc._inline("❌ Отмена", f"admin_view_city_tariff_{tariff_id}"))
    builder.adjust(1)

    await callback.message.answer(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_confirm_delete_city_tariff_'))
async def admin_confirm_delete_city_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение удаления тарифа городов"""
    logger.debug('admin_confirm_delete_city_tariff...')
    kbc = KeyboardCollection()

    tariff_id = int(callback.data.split('_')[5])
    tariff = await CitySubscriptionTariff.get_by_id(tariff_id)

    if not tariff:
        await callback.answer("❌ Тариф не найден", show_alert=True)
        return

    try:
        city_count = tariff.city_count
        await tariff.delete()

        await callback.message.answer(
            text=f'✅ <b>Тариф "{city_count} городов" успешно удален!</b>',
            reply_markup=await kbc.admin_city_tariffs_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_city_tariffs)
        await callback.answer("✅ Тариф удален", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при удалении тарифа городов: {e}")
        await callback.answer("❌ Произошла ошибка при удалении", show_alert=True)


@router.callback_query(F.data == 'admin_add_city_tariff',
                       StateFilter(AdminStates.manage_city_tariffs, AdminStates.add_city_tariff_count,
                                   AdminStates.add_city_tariff_price))
async def admin_add_city_tariff_count(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввод количества городов для нового тарифа"""
    logger.debug('admin_add_city_tariff_count...')
    kbc = KeyboardCollection()

    text = f'➕ <b>Добавление нового тарифа городов</b>\n\n'
    text += f'Введите количество городов (положительное число):'

    await state.set_state(AdminStates.add_city_tariff_count)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn('manage_city_tariffs'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.add_city_tariff_count))
async def process_add_city_tariff_count(message: Message, state: FSMContext) -> None:
    """Обработка количества городов для нового тарифа"""
    logger.debug('process_add_city_tariff_count...')
    kbc = KeyboardCollection()

    try:
        city_count = int(message.text.strip())
        if city_count <= 0:
            raise ValueError("Количество должно быть положительным числом")

        # Проверяем, нет ли уже тарифа с таким количеством
        existing = await CitySubscriptionTariff.get_by_city_count(city_count)
        if existing:
            await message.answer('❌ Тариф с таким количеством городов уже существует!',
                                 reply_markup=kbc.admin_back_btn('manage_city_tariffs'))
            return

        await state.update_data(city_count=city_count)

        text = f'💰 <b>Цена за месяц</b>\n\n'
        text += f'Количество городов: <b>{city_count}</b>\n\n'
        text += f'Введите цену в рублях за месяц:'

        await state.set_state(AdminStates.add_city_tariff_price)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('manage_city_tariffs'), parse_mode='HTML')
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное количество городов (положительное число)',
                             reply_markup=kbc.admin_back_btn('manage_city_tariffs'))


@router.message(F.text, StateFilter(AdminStates.add_city_tariff_price))
async def process_add_city_tariff_price(message: Message, state: FSMContext) -> None:
    """Обработка цены нового тарифа городов и создание"""
    logger.debug('process_add_city_tariff_price...')
    kbc = KeyboardCollection()

    try:
        price_rub = float(message.text.replace(',', '.').strip())
        if price_rub <= 0:
            raise ValueError("Цена должна быть положительным числом")

        price_kopecks = int(price_rub * 100)

        state_data = await state.get_data()
        city_count = state_data.get('city_count')

        new_tariff = CitySubscriptionTariff(
            id=None,
            city_count=city_count,
            price_per_month=price_kopecks
        )

        await new_tariff.save()

        await message.answer(
            text=f'✅ <b>Тариф успешно создан!</b>\n\n'
                 f'🏙️ Количество городов: <b>{city_count}</b>\n'
                 f'💵 Цена за месяц: <b>{int(price_rub)}₽</b>',
            reply_markup=await kbc.admin_city_tariffs_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_city_tariffs)

    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректную цену (положительное число)',
                             reply_markup=kbc.admin_back_btn('manage_city_tariffs'))
    except Exception as e:
        logger.error(f"Ошибка при создании тарифа городов: {e}")
        await message.answer('❌ Произошла ошибка при создании тарифа',
                             reply_markup=kbc.admin_back_btn('manage_city_tariffs'))


# ========== УПРАВЛЕНИЕ СКИДКАМИ ГОРОДОВ ==========

@router.callback_query(F.data == 'manage_city_discounts', StateFilter(AdminStates.manage_city_tariffs,
                                                                      AdminStates.add_city_discount_months,
                                                                      AdminStates.add_city_discount_percent,
                                                                      AdminStates.view_city_discount,
                                                                      AdminStates.edit_city_discount_percent))
async def manage_city_discounts(callback: CallbackQuery, state: FSMContext) -> None:
    """Главное меню управления скидками городов"""
    logger.debug('manage_city_discounts...')
    kbc = KeyboardCollection()

    discounts = await CitySubscriptionDiscount.get_all()
    text = f'💰 <b>Управление скидками городов</b>\n\n'
    text += f'📊 Всего скидок: {len(discounts)}\n\n'
    text += f'Скидки применяются к финальной цене в зависимости от периода подписки.\n\n'
    text += f'Выберите скидку для редактирования или добавьте новую:'

    await state.set_state(AdminStates.manage_city_discounts)
    await callback.message.answer(
        text=text,
        reply_markup=await kbc.admin_city_discounts_list(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_view_city_discount_'),
                       StateFilter(AdminStates.manage_city_discounts, AdminStates.edit_city_discount_percent,
                                   AdminStates.view_city_discount))
async def admin_view_city_discount(callback: CallbackQuery, state: FSMContext) -> None:
    """Просмотр информации о скидке городов"""
    logger.debug('admin_view_city_discount...')
    kbc = KeyboardCollection()

    discount_id = int(callback.data.split('_')[4])
    discount = await CitySubscriptionDiscount.get_by_id(discount_id)

    if not discount:
        await callback.answer("❌ Скидка не найдена", show_alert=True)
        return

    text = f'💰 <b>Информация о скидке</b>\n\n'
    text += f'⏰ <b>Период:</b> {discount.months} месяц{"ев" if discount.months > 1 else ""}\n'
    text += f'💵 <b>Процент скидки:</b> {discount.discount_percent}%\n\n'

    if discount.discount_percent > 0:
        text += f'<b>Пример расчета:</b>\n'
        text += f'При базовой цене 100₽ за месяц:\n'
        text += f'• {discount.months} месяц{"ев" if discount.months > 1 else ""} = {discount.months * 100}₽ (без скидки)\n'
        final_price = int(100 * discount.months * (100 - discount.discount_percent) / 100)
        text += f'• Со скидкой {discount.discount_percent}% = {final_price}₽\n'
        text += f'• Экономия: {discount.months * 100 - final_price}₽'
    else:
        text += f'Скидка не применяется (0%)'

    await state.set_state(AdminStates.view_city_discount)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_edit_city_discount(discount_id),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_edit_city_discount_months_'),
                       StateFilter(AdminStates.view_city_discount))
async def admin_edit_city_discount_months_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования периода скидки"""
    logger.debug('admin_edit_city_discount_months_handler...')
    kbc = KeyboardCollection()

    discount_id = int(callback.data.split('_')[5])
    discount = await CitySubscriptionDiscount.get_by_id(discount_id)

    if not discount:
        await callback.answer("❌ Скидка не найдена", show_alert=True)
        return

    text = f'⏰ <b>Редактирование периода скидки</b>\n\n'
    text += f'Текущий период: <b>{discount.months}</b> месяц{"ев" if discount.months > 1 else ""}\n\n'
    text += f'Введите новое количество месяцев (положительное число):'

    await state.set_state(AdminStates.edit_city_discount_percent)  # Используем существующее состояние
    await state.update_data(discount_id=discount_id, editing_field='months')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_city_discount_{discount_id}'),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_edit_city_discount_percent_'),
                       StateFilter(AdminStates.view_city_discount))
async def admin_edit_city_discount_percent_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик начала редактирования процента скидки"""
    logger.debug('admin_edit_city_discount_percent_handler...')
    kbc = KeyboardCollection()

    discount_id = int(callback.data.split('_')[5])
    discount = await CitySubscriptionDiscount.get_by_id(discount_id)

    if not discount:
        await callback.answer("❌ Скидка не найдена", show_alert=True)
        return

    text = f'💰 <b>Редактирование процента скидки</b>\n\n'
    text += f'Период: <b>{discount.months}</b> месяц{"ев" if discount.months > 1 else ""}\n'
    text += f'Текущий процент скидки: <b>{discount.discount_percent}%</b>\n\n'
    text += f'Введите новый процент скидки (от 0 до 100):'

    await state.set_state(AdminStates.edit_city_discount_percent)
    await state.update_data(discount_id=discount_id, editing_field='percent')
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn(f'admin_view_city_discount_{discount_id}'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.edit_city_discount_percent))
async def process_edit_city_discount(message: Message, state: FSMContext) -> None:
    """Обработка редактирования скидки городов"""
    logger.debug('process_edit_city_discount...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    discount_id = state_data.get('discount_id')
    editing_field = state_data.get('editing_field')

    try:
        discount = await CitySubscriptionDiscount.get_by_id(discount_id)
        if not discount:
            await message.answer('❌ Скидка не найдена', reply_markup=kbc.admin_back_btn('manage_city_discounts'))
            await state.set_state(AdminStates.menu)
            return

        if editing_field == 'months':
            months = int(message.text.strip())
            if months <= 0:
                raise ValueError("Количество месяцев должно быть положительным числом")

            # Проверяем, нет ли уже скидки с таким периодом
            existing = await CitySubscriptionDiscount.get_by_months(months)
            if existing and existing.id != discount_id:
                await message.answer('❌ Скидка с таким периодом уже существует!',
                                     reply_markup=kbc.admin_back_btn(f'admin_view_city_discount_{discount_id}'))
                return

            await discount.update(months=months)
            await message.answer(
                text=f'✅ <b>Период успешно изменен!</b>\n\nНовый период: <b>{months}</b> месяц{"ев" if months > 1 else ""}',
                reply_markup=kbc.admin_edit_city_discount(discount_id),
                parse_mode='HTML'
            )
        else:  # editing_field == 'percent'
            discount_percent = int(message.text.strip())
            if discount_percent < 0 or discount_percent > 100:
                raise ValueError("Процент скидки должен быть от 0 до 100")

            await discount.update(discount_percent=discount_percent)
            await message.answer(
                text=f'✅ <b>Процент скидки успешно изменен!</b>\n\nНовый процент: <b>{discount_percent}%</b>',
                reply_markup=kbc.admin_edit_city_discount(discount_id),
                parse_mode='HTML'
            )

        await state.set_state(AdminStates.view_city_discount)
    except ValueError as e:
        if "месяцев" in str(e) or "положительным" in str(e):
            await message.answer(
                text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректное количество месяцев (положительное число).',
                reply_markup=kbc.admin_back_btn(f'admin_view_city_discount_{discount_id}'),
                parse_mode='HTML'
            )
        else:
            await message.answer(
                text=f'❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректный процент скидки (от 0 до 100).',
                reply_markup=kbc.admin_back_btn(f'admin_view_city_discount_{discount_id}'),
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка при редактировании скидки городов: {e}")
        await message.answer('❌ Произошла ошибка', reply_markup=kbc.admin_back_btn('manage_city_discounts'))


@router.callback_query(lambda c: c.data.startswith('admin_delete_city_discount_'),
                       StateFilter(AdminStates.view_city_discount))
async def admin_delete_city_discount_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик удаления скидки городов"""
    logger.debug('admin_delete_city_discount_handler...')
    kbc = KeyboardCollection()

    discount_id = int(callback.data.split('_')[4])
    discount = await CitySubscriptionDiscount.get_by_id(discount_id)

    if not discount:
        await callback.answer("❌ Скидка не найдена", show_alert=True)
        return

    text = f'🗑️ <b>Подтверждение удаления скидки</b>\n\n'
    text += f'Вы действительно хотите удалить скидку:\n'
    text += f'⏰ <b>{discount.months} месяц{"ев" if discount.months > 1 else ""}</b>\n'
    text += f'💵 Процент скидки: {discount.discount_percent}%\n\n'
    text += f'⚠️ <b>Это действие нельзя отменить!</b>'

    builder = InlineKeyboardBuilder()
    builder.add(kbc._inline("✅ Да, удалить", f"admin_confirm_delete_city_discount_{discount_id}"))
    builder.add(kbc._inline("❌ Отмена", f"admin_view_city_discount_{discount_id}"))
    builder.adjust(1)

    await callback.message.answer(
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )


@router.callback_query(lambda c: c.data.startswith('admin_confirm_delete_city_discount_'))
async def admin_confirm_delete_city_discount(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение удаления скидки городов"""
    logger.debug('admin_confirm_delete_city_discount...')
    kbc = KeyboardCollection()

    discount_id = int(callback.data.split('_')[5])
    discount = await CitySubscriptionDiscount.get_by_id(discount_id)

    if not discount:
        await callback.answer("❌ Скидка не найдена", show_alert=True)
        return

    try:
        months = discount.months
        await discount.delete()

        await callback.message.answer(
            text=f'✅ <b>Скидка "{months} месяц{"ев" if months > 1 else ""}" успешно удалена!</b>',
            reply_markup=await kbc.admin_city_discounts_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_city_discounts)
        await callback.answer("✅ Скидка удалена", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при удалении скидки городов: {e}")
        await callback.answer("❌ Произошла ошибка при удалении", show_alert=True)


@router.callback_query(F.data == 'admin_add_city_discount', StateFilter(AdminStates.manage_city_discounts))
async def admin_add_city_discount_months(callback: CallbackQuery, state: FSMContext) -> None:
    """Ввод периода для новой скидки"""
    logger.debug('admin_add_city_discount_months...')
    kbc = KeyboardCollection()

    text = f'➕ <b>Добавление новой скидки</b>\n\n'
    text += f'Введите количество месяцев (положительное число):'

    await state.set_state(AdminStates.add_city_discount_months)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_back_btn('manage_city_discounts'),
        parse_mode='HTML'
    )


@router.message(F.text, StateFilter(AdminStates.add_city_discount_months))
async def process_add_city_discount_months(message: Message, state: FSMContext) -> None:
    """Обработка периода для новой скидки"""
    logger.debug('process_add_city_discount_months...')
    kbc = KeyboardCollection()

    try:
        months = int(message.text.strip())
        if months <= 0:
            raise ValueError("Количество месяцев должно быть положительным числом")

        # Проверяем, нет ли уже скидки с таким периодом
        existing = await CitySubscriptionDiscount.get_by_months(months)
        if existing:
            await message.answer('❌ Скидка с таким периодом уже существует!',
                                 reply_markup=kbc.admin_back_btn('manage_city_discounts'))
            return

        await state.update_data(months=months)

        text = f'💰 <b>Процент скидки</b>\n\n'
        text += f'Период: <b>{months}</b> месяц{"ев" if months > 1 else ""}\n\n'
        text += f'Введите процент скидки (от 0 до 100):'

        await state.set_state(AdminStates.add_city_discount_percent)
        await message.answer(text=text, reply_markup=kbc.admin_back_btn('manage_city_discounts'), parse_mode='HTML')
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное количество месяцев (положительное число)',
                             reply_markup=kbc.admin_back_btn('manage_city_discounts'))


@router.message(F.text, StateFilter(AdminStates.add_city_discount_percent))
async def process_add_city_discount_percent(message: Message, state: FSMContext) -> None:
    """Обработка процента новой скидки и создание"""
    logger.debug('process_add_city_discount_percent...')
    kbc = KeyboardCollection()

    try:
        discount_percent = int(message.text.strip())
        if discount_percent < 0 or discount_percent > 100:
            raise ValueError("Процент скидки должен быть от 0 до 100")

        state_data = await state.get_data()
        months = state_data.get('months')

        new_discount = CitySubscriptionDiscount(
            id=None,
            months=months,
            discount_percent=discount_percent
        )

        await new_discount.save()

        await message.answer(
            text=f'✅ <b>Скидка успешно создана!</b>\n\n'
                 f'⏰ Период: <b>{months}</b> месяц{"ев" if months > 1 else ""}\n'
                 f'💵 Процент скидки: <b>{discount_percent}%</b>',
            reply_markup=await kbc.admin_city_discounts_list(),
            parse_mode='HTML'
        )
        await state.set_state(AdminStates.manage_city_discounts)

    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректный процент скидки (от 0 до 100)',
                             reply_markup=kbc.admin_back_btn('manage_city_discounts'))
    except Exception as e:
        logger.error(f"Ошибка при создании скидки городов: {e}")
        await message.answer('❌ Произошла ошибка при создании скидки',
                             reply_markup=kbc.admin_back_btn('manage_city_discounts'))

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
