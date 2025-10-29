import logging
import asyncio
import time
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, InputMediaPhoto
from aiogram.utils.markdown import link

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import (
    Customer, Banned, BannedAbs, Abs, Worker, WorkerAndSubscription, WorkersAndAbs, City,
    WorkerAndRefsAssociation, WorkType, Admin, WorkerAndBadResponse, WorkerAndReport
)
from app.keyboards import KeyboardCollection
from app.states import AdminStates, UserStates, BannedStates
from app.untils import help_defs
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()

# Simple in-memory cache for admin summary
_admin_summary_cache = {"data": None, "ts": 0.0, "ttl": 60.0}  # Кеш на 30 секунд

def clear_admin_cache():
    """Очищает кеш админской аналитики"""
    global _admin_summary_cache
    _admin_summary_cache = {"data": None, "ts": 0.0, "ttl": 60.0}

def is_cache_valid():
    """Проверяет валидность кеша"""
    import time
    current_time = time.time()
    return (_admin_summary_cache["data"] is not None and 
            current_time - _admin_summary_cache["ts"] < _admin_summary_cache["ttl"])


@router.callback_query(F.data == 'menu', StateFilter(AdminStates.menu, UserStates.menu, AdminStates.edit_stop_words, AdminStates.unblock_user, AdminStates.block_user, AdminStates.check_subscription, AdminStates.edit_subscription, AdminStates.get_customer, AdminStates.get_worker, AdminStates.check_abs, AdminStates.check_banned_abs, AdminStates.get_user, AdminStates.send_to_user))
async def admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('admin_menu...')
    kbc = KeyboardCollection()

    # Проверяем кеш
    if is_cache_valid():
        # Используем данные из кеша
        cached_data = _admin_summary_cache["data"]
        len_users = cached_data.get("len_users", 0)
        len_customer = cached_data.get("len_customer", 0)
        len_worker = cached_data.get("len_worker", 0)
        len_banned_users = cached_data.get("len_banned_users", 0)
        len_advertisement = cached_data.get("len_advertisement", 0)
        len_banned_advertisement = cached_data.get("len_banned_advertisement", 0)
        
        # Проверяем наличие admin в кеше, если нет - загружаем заново
        if "admin" in cached_data:
            admin = cached_data["admin"]
        else:
            admin = await Admin.get_by_tg_id(callback.message.chat.id)
        
        # Получаем данные админа из кеша или загружаем заново
        deleted_abs = cached_data.get("deleted_abs", admin.deleted_abs if admin else 0)
        done_abs = cached_data.get("done_abs", admin.done_abs if admin else 0)
        
        logger.debug('Using cached admin summary data')
    else:
        # Загружаем свежие данные
        logger.debug('Loading fresh admin summary data')
        try:
            # Получаем админа
            admin = await Admin.get_by_tg_id(callback.message.chat.id)
            logger.debug(f"Admin loaded: {admin.id if admin else 'None'}")
            
            # Используем оптимизированные COUNT запросы вместо загрузки всех данных
            import aiosqlite
            
            async with aiosqlite.connect(database='app/data/database/database.db') as conn:
                logger.debug("Connected to database")
                
                # Подсчет заказчиков (проверяем существование таблицы)
                try:
                    cursor = await conn.execute('SELECT COUNT(*) FROM customers')
                    len_customer = (await cursor.fetchone())[0]
                    logger.debug(f"Customers count: {len_customer}")
                except Exception as e:
                    logger.warning(f"Таблица customers не найдена: {e}")
                    len_customer = 0
                
                # Подсчет исполнителей (проверяем существование таблицы)
                try:
                    cursor = await conn.execute('SELECT COUNT(*) FROM workers')
                    len_worker = (await cursor.fetchone())[0]
                    logger.debug(f"Workers count: {len_worker}")
                except Exception as e:
                    logger.warning(f"Таблица workers не найдена: {e}")
                    len_worker = 0
                
                # Подсчет уникальных пользователей (заказчики, которые не являются исполнителями)
                try:
                    cursor = await conn.execute('''
                        SELECT COUNT(*) FROM customers c 
                        WHERE c.tg_id NOT IN (SELECT w.tg_id FROM workers w WHERE w.tg_id IS NOT NULL)
                    ''')
                    unique_customers = (await cursor.fetchone())[0]
                    len_users = len_worker + unique_customers
                    logger.debug(f"Unique customers: {unique_customers}, Total users: {len_users}")
                except Exception as e:
                    logger.warning(f"Ошибка при подсчете уникальных пользователей: {e}")
                    len_users = len_worker + len_customer
                
                # Подсчет заблокированных пользователей (проверяем существование таблицы)
                try:
                    cursor = await conn.execute('''
                        SELECT COUNT(*) FROM banned 
                        WHERE ban_now = 1 OR forever = 1
                    ''')
                    len_banned_users = (await cursor.fetchone())[0]
                    logger.debug(f"Banned users count: {len_banned_users}")
                except Exception as e:
                    logger.warning(f"Таблица banned не найдена: {e}")
                    len_banned_users = 0
                
                # Подсчет объявлений (проверяем существование таблицы)
                try:
                    cursor = await conn.execute('SELECT COUNT(*) FROM abs')
                    len_advertisement = (await cursor.fetchone())[0]
                    logger.debug(f"Ads count: {len_advertisement}")
                except Exception as e:
                    logger.warning(f"Таблица abs не найдена: {e}")
                    len_advertisement = 0
                
                # Подсчет заблокированных объявлений (проверяем существование таблицы)
                try:
                    cursor = await conn.execute('SELECT COUNT(*) FROM banned_abs')
                    len_banned_advertisement = (await cursor.fetchone())[0]
                    logger.debug(f"Banned ads count: {len_banned_advertisement}")
                except Exception as e:
                    logger.warning(f"Таблица banned_abs не найдена: {e}")
                    len_banned_advertisement = 0
                
                await cursor.close()
                logger.debug("Database connection closed")

        except Exception as e:
            logger.error(f"Ошибка при загрузке аналитики: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            logger.error(f"Детали ошибки: {str(e)}")
            
            # В случае ошибки, не используем кеш и загружаем данные заново
            clear_admin_cache()
            
            # Fallback к простым значениям в случае ошибки
            len_users = 0
            len_customer = 0
            len_worker = 0
            len_banned_users = 0
            len_advertisement = 0
            len_banned_advertisement = 0
            admin = await Admin.get_by_tg_id(callback.message.chat.id)
        
        # Сохраняем в кеш
        import time
        _admin_summary_cache["data"] = {
            "len_users": len_users,
            "len_customer": len_customer,
            "len_worker": len_worker,
            "len_banned_users": len_banned_users,
            "len_advertisement": len_advertisement,
            "len_banned_advertisement": len_banned_advertisement,
            "admin": admin,
            "deleted_abs": admin.deleted_abs if admin else 0,
            "done_abs": admin.done_abs if admin else 0
        }
        _admin_summary_cache["ts"] = time.time()

    text = (f'Меню\n\n'
            f'Всего пользователей: {len_users}\n'
            f'Заказчиков: {len_customer}\n'
            f'Исполнителей: {len_worker}\n'
            f'Заблокировано: {len_banned_users}\n'
            f'Размещено объявлений: {len_advertisement}\n'
            f'Заблокировано объявлений: {len_banned_advertisement}\n'
            f'Удалено объявлений: {admin.deleted_abs}\n'
            f'Выполнено объявлений: {admin.done_abs}\n')

    await state.set_state(AdminStates.menu)
    await callback.message.delete()
    await callback.message.answer(text=text, reply_markup=kbc.menu_admin_keyboard())


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
    
    state_data = await state.get_data()
    # msg_id = state_data.get('msg_id')
    
    try:
        new_price = int(message.text)
        if new_price <= 0:
            raise ValueError("Цена должна быть положительным числом")
        
        # Получаем админа и обновляем цену
        admin = await Admin.get_by_tg_id(message.chat.id)
        await admin.update(order_price=new_price)
        
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer(
            text=f'✅ **Цена объявлений успешно изменена!**\n\n'
                 f'💰 Новая цена: {new_price}₽',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='Markdown'
        )
        await state.set_state(AdminStates.menu)
        
    except ValueError as e:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer(
            text=f'❌ **Ошибка!**\n\n'
                 f'Пожалуйста, введите корректную цену (положительное число).\n'
                 f'Например: 50, 100, 150',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='Markdown'
        )
        await state.set_state(AdminStates.edit_order_price)
    except Exception as e:
        logger.error(f"Ошибка при изменении цены объявлений: {e}")
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer(
            text='❌ **Произошла ошибка!**\n\n'
                 'Попробуйте еще раз или обратитесь к разработчику.',
            reply_markup=kbc.admin_back_btn('menu'),
            parse_mode='Markdown'
        )
        await state.set_state(AdminStates.menu)


# ЗАКОММЕНТИРОВАНО: Админские функции для управления SubscriptionType
# TODO: Удалить после рефакторинга или реализовать новую систему
# @router.callback_query(F.data == 'edit_subscription', StateFilter(AdminStates.menu))
# async def edit_subscription(callback: CallbackQuery, state: FSMContext) -> None:
#     logger.debug('block_user...')
#     kbc = KeyboardCollection()
# 
#     text = f'Выберите подписку:'
# 
#     await state.set_state(AdminStates.check_subscription)
# 
#     subscriptions = await SubscriptionType.get_all()
#     subscriptions_ids = [sub.id for sub in subscriptions[1::]]
#     subscriptions_names = [sub.subscription_type for sub in subscriptions[1::]]
#     await callback.message.answer(text=text,
#                                      reply_markup=kbc.choose_worker_subscription(
#                                          subscriptions_ids=subscriptions_ids,
#                                          subscriptions_names=subscriptions_names)
#                                      )
# 
# 
# @router.callback_query(lambda c: c.data.startswith('subscription_'), AdminStates.check_subscription)
# async def check_subscription(callback: CallbackQuery) -> None:
#     logger.debug(f'check_subscription...')
#     sub_id = int(callback.data.split('_')[1])
#     kbc = KeyboardCollection()
#     subscription = await SubscriptionType.get_subscription_type(id=sub_id)
#     subscriptions = await SubscriptionType.get_all()
#     subscriptions_ids = [sub.id for sub in subscriptions[1::]]
#     subscriptions_ids.remove(sub_id)
#     subscriptions_names = [sub.subscription_type for sub in subscriptions[1::]]
#     subscriptions_names.remove(subscription.subscription_type)
# 
#     text = (f'Тариф <b>{subscription.subscription_type.capitalize()}</b>\n'
#             f'Количество откликов: {"неограниченно" if subscription.unlimited else subscription.count_guaranteed_orders}\n'
#             f'Количество доступных направлений: {"неограниченно" if subscription.count_work_types == 100 else str(subscription.count_work_types) + " из 18"}\n'
#             f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'
#             f'Цена: {subscription.price} ₽\n')
# 
#     await callback.message.answer(text=text,
#                                      reply_markup=kbc.admin_edit_subscription(
#                                          sub_id=subscription.id),
#                                      parse_mode='HTML'
#                                      )
# 
# 
# @router.callback_query(lambda c: c.data.startswith('edit-price-sub_'), AdminStates.check_subscription)
# async def check_subscription(callback: CallbackQuery, state: FSMContext) -> None:
#     logger.debug(f'check_subscription_price...')
#     subscription_id = int(callback.data.split('_')[1])
#     kbc = KeyboardCollection()
#     subscription = await SubscriptionType.get_subscription_type(id=subscription_id)
# 
#     text = f'Текущая цена: {subscription.price}\n\nВведите цену:'
# 
#     msg = await callback.message.answer(text=text, reply_markup=kbc.menu(), parse_mode='HTML')
#     await state.set_state(AdminStates.edit_subscription_price)
#     await state.update_data(subscription_id=subscription_id)
#     await state.update_data(msg_id=msg.message_id)
# 
# 
# @router.message(F.text, StateFilter(AdminStates.edit_subscription_price))
# async def edit_price_subscription(message: Message, state: FSMContext) -> None:
#     logger.debug(f'check_subscription_price...')
#     kbc = KeyboardCollection()
# 
#     state_data = await state.get_data()
#     subscription_id = int(state_data.get('subscription_id'))
#     # msg_id = int(state_data.get('msg_id'))
# 
#     try:
#         price = int(message.text)
#     except Exception:
#         # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
#         msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
#         await state.update_data(msg_id=msg.message_id)
#         return
# 
#     subscription = await SubscriptionType.get_subscription_type(id=subscription_id)
#     await subscription.update(price=price)
# 
#     await state.set_state(AdminStates.menu)
#     # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
#     await message.answer('Цена изменена!', reply_markup=kbc.admin_back_btn('edit_subscription'))
# 
# 
# @router.callback_query(lambda c: c.data.startswith('edit-orders-sub_'), AdminStates.check_subscription)
# async def check_subscription(callback: CallbackQuery, state: FSMContext) -> None:
#     logger.debug(f'check_subscription_order...')
#     subscription_id = int(callback.data.split('_')[1])
#     kbc = KeyboardCollection()
#     subscription = await SubscriptionType.get_subscription_type(id=subscription_id)
# 
#     text = f'Текущее количество откликов: {subscription.count_guaranteed_orders if subscription.id != 6 else "бесконечно"}\n\nВведите новое количество:'
# 
#     msg = await callback.message.answer(text=text, reply_markup=kbc.menu(), parse_mode='HTML')
#     await state.set_state(AdminStates.edit_subscription_order)
#     await state.update_data(subscription_id=subscription_id)
#     await state.update_data(msg_id=msg.message_id)
# 
# 
# @router.message(F.text, StateFilter(AdminStates.edit_subscription_order))
# async def edit_price_subscription(message: Message, state: FSMContext) -> None:
#     logger.debug(f'check_subscription_order...')
#     kbc = KeyboardCollection()
# 
#     state_data = await state.get_data()
#     subscription_id = int(state_data.get('subscription_id'))
#     # msg_id = int(state_data.get('msg_id'))
# 
#     try:
#         orders = int(message.text)
#     except Exception:
#         # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
#         msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
#         await state.update_data(msg_id=msg.message_id)
#         return
# 
#     subscription = await SubscriptionType.get_subscription_type(id=subscription_id)
#     if subscription.id != 6:
#         await subscription.update(count_guaranteed_orders=orders)

#     await state.set_state(AdminStates.menu)
#     # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
#     await message.answer('Количество откликов изменено!', reply_markup=kbc.admin_back_btn('edit_subscription'))


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
            text += '*Пользователь заблокирован*\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
        # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
        #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        text += (f'*Профиль исполнителя*\n\n'
                 f'ID: {worker.id}  {"✅" if worker.confirmed else "☑️"}\n'
                 f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 # f'Ваш тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки
                 # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += ('*Профиль заказчика*\n\n'
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
                except Exception:
                    pass
                await callback.message.answer_photo(caption=text, photo=FSInputFile(worker.profile_photo), protect_content=False,
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

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    try:
        banned_id = int(message.text)
    except Exception:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    banned = await Banned.get_banned(tg_id=banned_id)

    if banned is None:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
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

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await message.answer('Пользователь разблокирован', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=banned_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.message(F.text, StateFilter(AdminStates.send_to_user))
async def send_to_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_to_user_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))
    user_id = int(state_data.get('user_id'))

    msg_to_send = message.text

    banned = await Banned.get_banned(tg_id=user_id)
    customer = await Customer.get_customer(tg_id=user_id)
    worker = await Worker.get_worker(tg_id=user_id)

    if banned is None and customer is None and worker is None:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer('Пользователь не найден', reply_markup=kbc.admin_back_btn('menu'))
        return

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await message.answer('Сообщение пользователю отправлено', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=user_id, text=f'Сообщение от администрации бота: "{msg_to_send}"')
    await state.set_state(AdminStates.menu)


@router.message(F.text, StateFilter(AdminStates.block_user))
async def unblock_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'ban_user_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    try:
        banned_id = int(message.text)
    except Exception:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
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
            # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            await message.answer('Пользователь уже заблокирован на всегда', reply_markup=kbc.admin_back_btn('menu'))
            return
        else:
            await banned.update(ban_counter=banned.ban_counter + 1,
                                ban_now=True,
                                ban_end=str(datetime.now() + timedelta(days=30)))

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await message.answer('Пользователь заблокирован', reply_markup=kbc.admin_back_btn('menu'))
    await bot.send_message(chat_id=banned_id,
                           text='Вы были заблокированы.\nПо решению администрации', reply_markup=kbc.support_btn())


@router.message(F.text, StateFilter(AdminStates.get_customer))
async def get_customer(message: Message, state: FSMContext) -> None:
    logger.debug(f'get_customer_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    try:
        customer_id = int(message.text)
    except Exception:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    customer = await Customer.get_customer(id=customer_id)

    if customer is None:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
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

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await message.answer(text=text, reply_markup=kbc.admin_get_customer(callback_data='menu', customer_id=customer_id),
                         protect_content=False)


@router.message(F.text, StateFilter(AdminStates.get_user))
async def get_user(message: Message, state: FSMContext) -> None:
    logger.debug(f'get_user_text...')
    kbc = KeyboardCollection()

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    try:
        user_id = int(message.text)
    except Exception:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    text = ''
    worker_acc = False

    if user_blocked := await Banned.get_banned(tg_id=user_id):
        if user_blocked.ban_now or user_blocked.forever:
            text += f'*Пользователь заблокирован*\nПричина блокировки: {user_blocked.ban_reason}\n\n'
    if worker := await Worker.get_worker(tg_id=user_id):
        worker_acc = True
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
        # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
        #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None

        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        text += (f'*Профиль исполнителя*\n\n'
                 f'ID: {worker.id}  {"✅" if worker.confirmed else "☑️"}\n'
                 f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 # f'Ваш тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки
                 # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

    if customer := await Customer.get_customer(tg_id=user_id):
        if worker_acc:
            text += f'\n\n'
        city = await City.get_city(id=customer.city_id)
        user_abs = await Abs.get_all_by_customer(customer.id)
        text += ('*Профиль заказчика*\n\n'
                 f'ID: {customer.id}\n'
                 f'Общий ID: {customer.tg_id}\n'
                 f'Город заказчика: {city.city}\n'
                 f'Открыто объявлений: {len(user_abs) if user_abs else 0}\n')

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False
        await message.answer(text=text, protect_content=False,
                             reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id))
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
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
        # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
        # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
        #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None

        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        text += (f'Профиль исполнителя\n\n'
                 f'ID: {worker.id}  {"✅" if worker.confirmed else "☑️"}\n'
                 f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️\n'
                 f'{cites}'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 # f'Ваш тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
                 # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка для многострочной строки
                 # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

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
                await callback.message.answer_photo(caption=text, photo=FSInputFile(worker.profile_photo), protect_content=False,
                                                    reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id))
            else:
                await callback.message.answer(text=text, protect_content=False,
                                              reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id))

        else:
            await callback.message.answer(text=text, protect_content=False, reply_markup=kbc.admin_back_or_send(callback_data='menu', customer_id=customer_id))
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

    text = f'Объявление {abs_now.id}\n\n' + text

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
    text = f'Объявление {abs_now.id}\n\n' + text

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

    state_data = await state.get_data()
    # msg_id = int(state_data.get('msg_id'))

    try:
        worker_id = int(message.text)
    except Exception:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        msg = await message.answer('Что-то пошло не так, попробуйте, еще раз')
        await state.update_data(msg_id=msg.message_id, reply_markup=kbc.admin_back_btn('menu'))
        return

    worker = await Worker.get_worker(id=worker_id)

    if worker is None:
        # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        await message.answer('Исполнитель с таким ID не существует', reply_markup=kbc.admin_back_btn('menu'))
        return

    worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
    # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
    # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
    #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
    work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None
    city = await City.get_city(id=int(worker.city_id))

    text = (f'Профиль исполнителя\n\n'
            f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}  {"✅" if worker.confirmed else "☑️"}\n'
            f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
            f'Общий ID исполнителя: {worker.tg_id}\n'
            f'Рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
            f'Город: {city.city}\n'
            f'Выполненных заказов: {worker.order_count}\n'
            f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
            # f'Тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
            # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
            f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n'
            # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
            f'Зарегистрирован с {worker.registration_data}\n')  # Закрывающая скобка
            # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
    await message.answer(text=text, reply_markup=kbc.admin_back_btn('menu'), protect_content=False)


@router.callback_query(F.data == 'menu_send_msg_admin', StateFilter(AdminStates.menu))
async def menu_send_msg_admin_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('menu_send_msg_admin_keyboard...')
    kbc = KeyboardCollection()

    text = (f'Меню\n\n'
            f'Выберете интересующую вас группу отправки')

    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=text, reply_markup=kbc.menu_send_msg_admin_keyboard())


@router.callback_query(F.data == 'menu_admin', StateFilter(AdminStates.menu, UserStates.menu, BannedStates.banned))
async def admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('admin_menu...')
    kbc = KeyboardCollection()

    # Cache hit
    now_ts = time.time()
    if _admin_summary_cache["data"] is not None and (now_ts - _admin_summary_cache["ts"]) < _admin_summary_cache["ttl"]:
        summary = _admin_summary_cache["data"]
    else:
        # Fetch aggregated counts concurrently
        (len_customer,
         len_worker,
         len_banned_users,
         len_advertisement,
         len_banned_advertisement,
         len_users,
         admin) = await asyncio.gather(
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

    text = (f'Меню\n\n'
            f'Всего пользователей: {summary.get("len_users", 0)}\n'
            f'Заказчиков: {summary.get("len_customer", 0)}\n'
            f'Исполнителей: {summary.get("len_worker", 0)}\n'
            f'Заблокировано: {summary.get("len_banned_users", 0)}\n'
            f'Размещено объявлений: {summary.get("len_advertisement", 0)}\n'
            f'Заблокировано объявлений: {summary.get("len_banned_advertisement", 0)}\n'
            f'Удалено объявлений: {summary.get("deleted_abs", 0)}\n'
            f'Выполнено объявлений: {summary.get("done_abs", 0)}\n')

    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=text, reply_markup=kbc.menu_admin_keyboard())
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


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
    except Exception:
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
                except Exception:
                    pass
                message_to_worker = str(state_data.get('message_to_worker'))

    city = await City.get_city(id=city_id)

    # await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
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
            except Exception:
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
    except Exception:
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

    # msg = await callback.message.answer('Подождите, идет отправка')

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            if not await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                try:
                    message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                    await bot.send_message(chat_id=worker.tg_id, text=message_to_worker)
                except Exception:
                    pass
                message_to_worker = str(state_data.get('message_to_worker'))

    # await bot.delete_message(chat_id=callback.message.chat.id, message_id=msg.message_id)
    await state.set_state(AdminStates.menu)
    await callback.message.answer(text=f'Сообщение отправлено всем исполнителям!',
                                  reply_markup=kbc.menu_btn())


@router.message(F.photo, AdminStates.msg_to_worker_photo_ref)
async def msg_to_worker_photo(message: Message, state: FSMContext) -> None:
    logger.debug(f'msg_to_all_worker_photo_ref...')
    kbc = KeyboardCollection()

    photo = message.photo[-1].file_id

    state_data = await state.get_data()
    # msg = str(state_data.get('msg'))
    message_to_worker = str(state_data.get('message_to_worker'))

    # await bot.delete_message(chat_id=message.from_user.id, message_id=msg)
    msg = await message.answer('Подождите, идет отправка')

    file_path_photo = await help_defs.save_photo(id=message.from_user.id,
                                                 path='app/data/database/abs_from_admin_photo/')
    await bot.download(file=photo, destination=file_path_photo)

    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            try:
                message_to_worker = message_to_worker + f'\n\nВаша реферальная ссылка: https://t.me/Rus_haltura_bot?start={worker.ref_code}'
                await bot.send_photo(chat_id=worker.tg_id, photo=FSInputFile(file_path_photo),
                                     caption=message_to_worker)
            except Exception:
                pass
            message_to_worker = str(state_data.get('message_to_worker'))

    help_defs.delete_file(file_path_photo)
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
    except Exception:
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


    text = f'Объявление {abs_now.id}\n\n' + text
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


    text = f'Объявление {abs_now.id}\n\n' + text

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
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление {advertisement.id} неактуально')
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
        # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
        # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
        #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        text += (f'Профиль исполнителя\n\n'
                 f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}  {"✅" if worker.confirmed else "☑️"}\n'
                 f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 # f'Ваш тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n')  # Закрывающая скобка для многострочной строки
                 # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

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
        await callback.message.answer(text=text, protect_content=False,
                                      reply_markup=kbc.admin_back_or_send(callback_data='menu',
                                                                          customer_id=customer_id))
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
    # msg_id = int(state_data.get('msg_id'))

    customer = await Customer.get_customer(id=customer_id)

    msg_to_send = message.text

    # await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    banned = await Banned.get_banned(tg_id=customer.tg_id)
    await banned.update(ban_reason=msg_to_send)

    await message.answer(text='Сообщение пользователю отправлено', reply_markup=kbc.admin_back_btn(f'get-user_{customer_id}'))
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
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление {advertisement.id} неактуально')
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


@router.callback_query(lambda c: c.data.startswith('back-to-customer_'), StateFilter(AdminStates.get_user, AdminStates.check_banned_abs, AdminStates.check_abs))
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
        # subscription = await SubscriptionType.get_subscription_type(worker_sub.subscription_id)  # ЗАКОММЕНТИРОВАНО: subscription_id больше не используется
        # work_type_names = [await WorkType.get_work_type(id=int(i)) for i in
        #                    worker_sub.work_type_ids] if not worker_sub.unlimited_work_types else None  # ЗАКОММЕНТИРОВАНО: unlimited_work_types больше не используется
        work_type_names = [await WorkType.get_work_type(id=int(i)) for i in worker_sub.work_type_ids] if worker_sub.work_type_ids else None
        if len(worker.city_id) == 1:
            cites = 'Ваш город: '
            step = ''
        else:
            cites = 'Ваши города:\n'
            step = '    '
        for city_id in worker.city_id:
            city = await City.get_city(id=city_id)
            cites += f'{step}{city.city}\n'

        text += (f'Профиль исполнителя\n\n'
                 f'ID: {worker.id}  {worker.profile_name if worker.profile_name else ""}  {"✅" if worker.confirmed else "☑️"}\n'
                 f'Наличие ИП: {"✅" if worker.individual_entrepreneur else "☑️"}\n'
                 f'Общий ID исполнителя: {worker.tg_id}\n'
                 f'Ваш рейтинг: {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars} ⭐️ ({worker.count_ratings if worker.count_ratings else 0} {help_defs.get_grade_word(worker.count_ratings if worker.count_ratings else 0)})\n'
                 f'{cites}\n'
                 f'Выполненных заказов: {worker.order_count}\n'
                 f'Выполненных заказов за неделю: {worker.order_count_on_week}\n'
                 # f'Ваш тариф: {subscription.subscription_type}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'Осталось откликов: {"неограниченно" if worker_sub.unlimited_orders or worker_sub.subscription_id == 1 else worker_sub.guaranteed_orders}\n'  # ЗАКОММЕНТИРОВАНО: количество откликов теперь определяется рангом
                 f'Доступные направления: {(str(len(work_type_names)) + " из 20") if work_type_names else "20 из 20"}\n')  # Закрывающая скобка для многострочной строки
                 # f'Уведомление об актуальности заказов: {"доступно ✔" if subscription.notification else "не доступно ❌"}\n'  # ЗАКОММЕНТИРОВАНО: SubscriptionType больше не используется
                 # f'\nПодписка действует до: {worker_sub.subscription_end if worker_sub.subscription_end else "3-х выполненных заказов"}\n'  # ЗАКОММЕНТИРОВАНО: subscription_end больше не используется

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

    if text:
        if customer:
            customer_id = customer.id
        else:
            customer_id = False

        if worker:
            if worker.profile_photo:
                await callback.message.answer_photo(caption=text, photo=FSInputFile(worker.profile_photo), protect_content=False,
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
    await callback.message.answer(text=text,
                                  reply_markup=kbc.choose_obj_with_out_list_admin_var(id_now=0, btn_next=btn_next,
                                                                                      btn_back=False,
                                                                                      btn_block=True,
                                                                                      btn_delete=True,
                                                                                      abs_id=abs_now.id,
                                                                                      customer_id=customer_id))


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
    await callback.message.answer(text=text, reply_markup=kbc.choose_obj_with_out_list_admin_var(id_now=abs_list_id,
                                                                                                 btn_next=btn_next,
                                                                                                 btn_back=btn_back,
                                                                                                 btn_block=True,
                                                                                                 btn_delete=True,
                                                                                                 abs_id=abs_now.id,
                                                                                                 customer_id=customer_id))


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
                await banned.update(ban_counter=banned.ban_counter - 1,
                                    ban_now=False,
                                    ban_end=None,
                                    forever=False)
            else:
                await banned.update(ban_counter=banned.ban_counter - 1,
                                    ban_now=False,
                                    ban_end=None)

    text_path = help_defs.copy_file(banned_advertisement.text_path, f'app/data/text/{customer.tg_id}/')

    if not text_path:
        await banned_advertisement.delete(delite_photo=True)
        await callback.message.delete()
        await callback.message.answer('Пользователь разблокирован')
        try:
            await bot.send_message(chat_id=customer.tg_id,
                                   text='Вы были разблокированы, приносим извинения за предоставленные неудобства.\nВызовите команду /menu чтобы продолжить работу')
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
                    if (advertisement.work_type_id in worker_sub.work_type_ids) or worker_sub.unlimited_work_types:
                        if banned_advertisement.photo_path:
                            await bot.send_photo(chat_id=worker.tg_id,
                                                 photo=FSInputFile(banned_advertisement.photo_path['0']),
                                                 caption=text,
                                                 reply_markup=kbc.apply_btn(advertisement.id)
                                                 )
                        else:
                            await bot.send_message(chat_id=worker.tg_id,
                                                   text=text,
                                                   reply_markup=kbc.apply_btn(advertisement.id)
                                                   )
                elif worker_sub.unlimited_work_types:
                    if banned_advertisement.photo_path:
                        await bot.send_photo(chat_id=worker.tg_id,
                                             photo=FSInputFile(banned_advertisement.photo_path['0']),
                                             caption=text,
                                             reply_markup=kbc.apply_btn(advertisement.id)
                                             )
                    else:
                        await bot.send_message(chat_id=worker.tg_id,
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
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None,
                                forever=False)
        else:
            await banned.update(ban_counter=banned.ban_counter - 1,
                                ban_now=False,
                                ban_end=None)
    try:
        await bot.send_message(chat_id=customer.tg_id,
                               text='Вы были разблокированы, приносим извинения за предоставленные неудобства.\nВызовите команду /menu чтобы продолжить работу')
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
        from app.data.database.models import Banned
        
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
            
            await callback.message.answer(f"✅ Имя удалено. Исполнитель #{worker_id} заблокирован навсегда (3 нарушения)")
        
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
            
            await callback.message.answer(f"✅ Имя удалено. Исполнителю #{worker_id} отправлено предупреждение ({new_violations_count}/3)")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_delete_worker_name: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
