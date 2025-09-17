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
    logger.info('check_time_advertisement')
    advertisements = await Abs.get_all()
    kbc = KeyboardCollection()
    if advertisements:
        for advertisement in advertisements:
            if advertisement.date_to_delite < datetime.now():
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
                            f'Исполнитель ID {worker.id} ⭐️ {round(worker.stars / worker.count_ratings, 1) if worker.stars else 0}'
                            for worker in
                            workers_for_assessments]
                        ids = [worker.id for worker in workers_for_assessments]

                        try:
                            await bot.send_message(
                                chat_id=customer.tg_id,
                                text=f'Срок актуальность объявления #{advertisement.id} истек!'
                                     f'{text}\n\n'
                                     f'Выберите исполнителя для оценки',
                                reply_markup=kbc.get_for_staring(ids=ids, names=names)
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
            elif advertisement.date_to_delite <= datetime.now():
                workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
                customer = await Customer.get_customer(id=advertisement.customer_id)

                text = help_defs.read_text_file(advertisement.text_path)

                if workers_and_abs:
                    workers_for_assessments = []
                    for worker_and_abs in workers_and_abs:
                        worker = await Worker.get_worker(id=worker_and_abs.worker_id)
                        if worker is None:
                            continue
                        if worker_and_abs.applyed:
                            workers_for_assessments.append(worker)

                    if workers_for_assessments:
                        try:
                            await bot.send_message(
                                chat_id=customer.tg_id,
                                text=f'Срок актуальности истек!\n\n'
                                     f'{text}',
                                reply_markup=kbc.end_time(idk=advertisement.id, workers=True)
                            )
                        except Exception as e:
                            logger.info(e)

                else:
                    try:
                        await bot.send_message(
                            chat_id=customer.tg_id,
                            text=f'Срок актуальности истек!\n\n'
                                 f'{text}',
                            reply_markup=kbc.end_time(idk=advertisement.id, workers=False)
                        )
                    except Exception as e:
                        logger.info(e)

                await advertisement.delete(delite_photo=True if advertisement.photo_path else False)
            elif advertisement.date_to_delite + timedelta(days=1) <= datetime.now():
                customer = await Customer.get_customer(id=advertisement.customer_id)
                try:
                    await bot.send_message(
                        chat_id=customer.tg_id,
                        text='Завтра истекает срок вашего объявления!'
                    )
                except Exception as e:
                    logger.info(e)


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


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
