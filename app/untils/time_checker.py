import logging
from datetime import datetime, timedelta

from app.data.database.models import Customer, Worker, Banned, WorkerAndSubscription, Abs, WorkersAndAbs, \
    SubscriptionType, BannedAbs, City, WorkerAndRefsAssociation
from app.keyboards import KeyboardCollection
from app.untils import help_defs
from loaders import bot

logger = logging.getLogger()


async def check_time_alive():
    logger.info('check_time_alive')
    customers = await Customer.get_all()
    workers = await Worker.get_all()
    users = []

    users += workers
    for customer in customers:
        if await Worker.get_worker(tg_id=customer.tg_id) is None:
            users.append(customer)
    len_users = len(users) if users else 0

    await bot.send_message(chat_id=-4215934637, text=f'Bot alive\n\nВсего пользователей {len_users}')


async def check_time_banned():
    logger.info('check_time_banned')
    banned_users = await Banned.get_all_banned_now()
    if banned_users:
        for banned_user in banned_users:
            if banned_user.forever:
                continue
            if banned_user.ban_end <= datetime.now():
                await banned_user.update(ban_now=False)
                try:
                    await bot.send_message(chat_id=banned_user.tg_id,
                                           text='Вы были разблокированы, чтобы продолжить работу вызовите команду /menu')
                except Exception:
                    pass


async def check_time_workers_stars():
    logger.info('check_time_workers_stars')
    workers = await Worker.get_all()
    if workers:
        for worker in workers:
            if not await Banned.get_banned(tg_id=worker.tg_id):
                if worker.stars/worker.count_ratings < 2:
                    if worker.count_ratings > 5:
                        banned = Banned(id=None, tg_id=worker.tg_id, ban_counter=1, ban_end=str(datetime.now()+timedelta(days=1000)), ban_now=True, forever=True, ban_reason='Низкий рейтинг')
                        await banned.save()
                        banned = await Banned.get_banned(tg_id=worker.tg_id)
                        await banned.update(forever=True)
                        await worker.delete()
                        if customer := await Customer.get_customer(tg_id=worker.tg_id):
                            await customer.delete()
                        try:
                            await bot.send_message(chat_id=worker.tg_id, text='Увы, к сожалению нам пришлось закрыть вам доступ за низкий рейтинг 😢')
                        except Exception:
                            pass


async def check_time_workers():
    logger.info('check_time_workers')
    workers = await Worker.get_all()
    kbc = KeyboardCollection()
    if workers:
        for worker in workers:
            if not await Banned.get_banned(tg_id=worker.tg_id):
                worker_subscription = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                if worker_subscription.subscription_end:
                    if worker_subscription.date_end <= datetime.now() + timedelta(days=1):
                        btn_bonus = False
                        if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                            if worker_and_ref.worker_bonus:
                                btn_bonus = True
                        elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                            if worker_and_ref.ref_bonus:
                                btn_bonus = True

                        try:
                            await bot.send_message(chat_id=worker.tg_id, text='У вас в скором времени закончится подписка', reply_markup=kbc.subscription_btn(btn_bonus=btn_bonus))
                        except Exception:
                            pass


async def check_time_customer():
    logger.info('check_time_customer')
    customers = await Customer.get_all()
    if customers:
        for customer in customers:
            await customer.update_abs_count(abs_count=3)
            if customer.abs_count != 3:
                if worker := await Worker.get_worker(tg_id=customer.tg_id):
                    if not worker.active:
                        try:
                            await bot.send_message(chat_id=customer.tg_id, text='Обновлен лимит объявлений на сегодня 0 из 3')
                        except Exception:
                            pass
                else:
                    try:
                        await bot.send_message(chat_id=customer.tg_id, text='Обновлен лимит объявлений на сегодня 0 из 3')
                    except Exception:
                        pass


async def check_time_advertisement():
    """Проверка срока актуальности объявлений с адаптивной логикой"""
    logger.info('check_time_advertisement')
    advertisements = await Abs.get_all()
    kbc = KeyboardCollection()
    if advertisements:
        for advertisement in advertisements:
            await check_single_advertisement_expiry(advertisement, kbc)


async def check_single_advertisement_expiry(advertisement, kbc):
    """Проверка одного объявления с учетом его срока актуальности"""
    now = datetime.now()
    expiry_time = advertisement.date_to_delite
    
    # Рассчитываем время до истечения
    time_until_expiry = expiry_time - now
    
    # Определяем тип объявления по времени до истечения
    if time_until_expiry.total_seconds() <= 0:
        # ИСТЕК - автоматическое закрытие
        await handle_expired_advertisement(advertisement, kbc)
    elif time_until_expiry.total_seconds() <= 2 * 3600:  # <= 2 часа
        # Скоро истекает (для коротких сроков)
        await handle_expiring_soon_advertisement(advertisement, kbc)
    elif time_until_expiry.total_seconds() <= 24 * 3600:  # <= 24 часа
        # Истекает завтра (для длинных сроков)
        await handle_expiring_tomorrow_advertisement(advertisement, kbc)


async def handle_expired_advertisement(advertisement, kbc):
    """Обработка истекшего объявления - автоматическое закрытие"""
    logger.info(f'Handling expired advertisement {advertisement.id}')
    
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
    customer = await Customer.get_customer(id=advertisement.customer_id)
    text = help_defs.read_text_file(advertisement.text_path)

    if workers_and_abs:
        workers_for_assessments = []
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            if worker is None:
                continue
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
            if sub.notification:
                city = await City.get_city(id=advertisement.city_id)
                text = f'Объявление {advertisement.id} г. {city.city}\n' + help_defs.read_text_file(
                    advertisement.text_path)
                try:
                    await bot.send_message(chat_id=worker.tg_id,
                                           text=f'Объявление закрыто за истечением срока давности\n\nОбъявление неактуально\n\n{text}')
                except Exception:
                    pass
            if worker_and_abs.applyed:
                workers_for_assessments.append(worker)
            await worker_and_abs.delete()

        if workers_for_assessments:
            names = [
                f'Исполнитель ID {worker.id} ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.count_ratings else worker.stars}'
                for worker in workers_for_assessments]
            ids = [worker.id for worker in workers_for_assessments]

            try:
                await bot.send_message(
                    chat_id=customer.tg_id,
                    text=f'Срок актуальность объявления #{advertisement.id} истек!\n\n'
                         f'{text}\n\n'
                         f'Выберите исполнителя для оценки',
                    reply_markup=kbc.get_for_staring(ids=ids, names=names, abs_id=advertisement.id)
                )
            except Exception as e:
                logger.info(e)

    else:
        try:
            await bot.send_message(
                chat_id=customer.tg_id,
                text=f'Срок актуальность объявления #{advertisement.id} истек!\n\n'
                     f'{text}'
            )
        except Exception as e:
            logger.info(e)

    await advertisement.delete(delite_photo=True if advertisement.photo_path else False)


async def handle_expiring_soon_advertisement(advertisement, kbc):
    """Обработка объявления, которое скоро истекает (для коротких сроков)"""
    logger.info(f'Handling expiring soon advertisement {advertisement.id}')
    
    customer = await Customer.get_customer(id=advertisement.customer_id)
    text = help_defs.read_text_file(advertisement.text_path)
    
    try:
        await bot.send_message(
            chat_id=customer.tg_id,
            text=f'⚠️ Объявление #{advertisement.id} истекает через 2 часа!\n\n'
                 f'{text}\n\n'
                 f'Объявление будет автоматически закрыто при истечении срока.'
        )
    except Exception as e:
        logger.info(e)


async def handle_expiring_tomorrow_advertisement(advertisement, kbc):
    """Обработка объявления, которое истекает завтра (для длинных сроков)"""
    logger.info(f'Handling expiring tomorrow advertisement {advertisement.id}')
    
    customer = await Customer.get_customer(id=advertisement.customer_id)
    
    try:
        await bot.send_message(
            chat_id=customer.tg_id,
            text=f'📅 Завтра истекает срок вашего объявления #{advertisement.id}!'
        )
    except Exception as e:
        logger.info(e)
# Старая логика удалена - теперь используется новая адаптивная система


async def check_time_banned_advertisement():
    logger.info('check_time_banned_advertisement')
    banned_advertisements = await BannedAbs.get_all()
    if banned_advertisements:
        for banned_advertisement in banned_advertisements:
            if banned_advertisement.date_to_delite <= datetime.now():
                await banned_advertisement.delete(delite_photo=True if banned_advertisement.photo_path else False)


async def cleanup_orphaned_files():
    """Очистка осиротевших файлов портфолио - запускается еженедельно"""
    logger.info('cleanup_orphaned_files')
    try:
        cleaned_count = help_defs.cleanup_orphaned_portfolio_files()
        logger.info(f'Очистка файлов завершена. Обработано файлов: {cleaned_count}')
    except Exception as e:
        logger.error(f'Ошибка при очистке файлов: {e}')


async def restore_weekly_activity():
    """Восстанавливает +1 активность всем исполнителям за неделю без нарушений"""
    logger.info('restore_weekly_activity: Starting weekly activity restoration')
    
    try:
        import aiosqlite
        
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            # Получаем всех активных исполнителей
            cursor = await conn.execute('SELECT id, activity_level FROM workers WHERE active = 1')
            workers = await cursor.fetchall()
            await cursor.close()
            
            updated_count = 0
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            
            for worker_id, current_activity in workers:
                # Проверяем наличие отмен откликов за последнюю неделю
                cursor = await conn.execute('''
                    SELECT COUNT(*) FROM worker_response_cancellations 
                    WHERE worker_id = ? AND cancelled_at >= ?
                ''', (worker_id, week_ago))
                cancelled_responses_count = (await cursor.fetchone())[0]
                await cursor.close()
                
                # Если нет отмен откликов за неделю, увеличиваем активность
                if cancelled_responses_count == 0 and current_activity < 100:
                    new_activity = min(100, current_activity + 1)
                    cursor = await conn.execute(
                        'UPDATE workers SET activity_level = ? WHERE id = ?',
                        (new_activity, worker_id)
                    )
                    await cursor.close()
                    updated_count += 1
                    logger.debug(f'Worker {worker_id}: {current_activity} -> {new_activity}')
            
            await conn.commit()
            logger.info(f'restore_weekly_activity: Updated {updated_count} workers')
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f'restore_weekly_activity: Error - {e}')


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
