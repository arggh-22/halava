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


async def check_worker_statuses():
    """
    Проверяет статусы исполнителей (ИП, ООО, СЗ) каждые 6 месяцев.
    Если статус больше не действителен - снимает его.
    """
    try:
        logger.info('check_worker_statuses: Starting...')
        from app.data.database.models import WorkerStatus
        
        # Получаем все статусы, которые нужно проверить (старше 6 месяцев)
        statuses_to_check = await WorkerStatus.get_all_for_recheck()
        
        if not statuses_to_check:
            logger.info('check_worker_statuses: No statuses to check')
            return
        
        logger.info(f'check_worker_statuses: Checking {len(statuses_to_check)} statuses...')
        
        checked_count = 0
        revoked_count = 0
        
        for status in statuses_to_check:
            status_changed = False
            revoked_status_name = None
            
            # Проверяем ИП
            if status.has_ip and status.ip_number:
                result = help_defs.check_ip_status_by_ogrnip(status.ip_number)
                if not result:
                    # ИП больше не действует
                    status.has_ip = False
                    status.ip_number = None
                    status_changed = True
                    revoked_status_name = "ИП"
                    revoked_count += 1
                    logger.info(f'check_worker_statuses: Revoked IP for worker {status.worker_id}')
            
            # Проверяем ООО
            if status.has_ooo and status.ooo_number:
                result = help_defs.check_ooo(status.ooo_number)
                if result != True:  # False or "error"
                    # ООО больше не действует или ошибка
                    if result == False:  # Только если точно не действует
                        status.has_ooo = False
                        status.ooo_number = None
                        status_changed = True
                        revoked_status_name = "ООО"
                        revoked_count += 1
                        logger.info(f'check_worker_statuses: Revoked OOO for worker {status.worker_id}')
            
            # Проверяем СЗ
            if status.has_sz and status.sz_number:
                result = help_defs.check_npd(status.sz_number)
                if result != True:  # False or "error"
                    # СЗ больше не действует или ошибка
                    if result == False:  # Только если точно не действует
                        status.has_sz = False
                        status.sz_number = None
                        status_changed = True
                        revoked_status_name = "Самозанятость"
                        revoked_count += 1
                        logger.info(f'check_worker_statuses: Revoked SZ for worker {status.worker_id}')
            
            # Обновляем дату последней проверки
            status.last_status_check = datetime.now().isoformat()
            
            # Сохраняем изменения
            if status_changed or True:  # Всегда обновляем last_status_check
                await status.save()
                checked_count += 1
                
                # Отправляем уведомление исполнителю о снятии статуса
                if status_changed and revoked_status_name:
                    try:
                        from app.data.database.models import Worker
                        from loaders import bot
                        
                        worker = await Worker.get_worker(id=status.worker_id)
                        if worker:
                            notification_text = (
                                f"⚠️ **Уведомление о статусе**\n\n"
                                f"Ваш статус **{revoked_status_name}** больше не действителен.\n\n"
                                f"Статус изменен на: **Статус не подтвержден ⚠️**\n\n"
                                f"Вы можете подтвердить статус заново в разделе 'Статус' вашего профиля."
                            )
                            await bot.send_message(
                                chat_id=worker.tg_id,
                                text=notification_text,
                                parse_mode='Markdown'
                            )
                            logger.info(f'check_worker_statuses: Notification sent to worker {status.worker_id}')
                    except Exception as notify_error:
                        logger.error(f'check_worker_statuses: Failed to send notification - {notify_error}')
        
        logger.info(f'check_worker_statuses: Checked {checked_count} statuses, revoked {revoked_count} statuses')
        
    except Exception as e:
        logger.error(f'check_worker_statuses: Error - {e}')


async def update_worker_ranks():
    """
    Обновляет ранги всех исполнителей на основе заказов за последние 30 дней.
    Запускается автоматически каждый день в 00:00.
    При понижении ранга обнуляет направления, если они превышают новый лимит.
    
    ПРИМЕЧАНИЕ: Повышение рангов теперь происходит мгновенно при оценке исполнителя
    в функции update_worker_rank_instantly(). Эта функция служит запасным вариантом
    и для обработки понижения рангов.
    """
    logger.info('update_worker_ranks: Starting rank update for all workers')
    
    try:
        from app.data.database.models import Worker, WorkerRank, WorkerAndSubscription
        from loaders import bot
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Получаем всех исполнителей
        workers = await Worker.get_all()
        if not workers:
            logger.info('update_worker_ranks: No workers found')
            return
        
        updated_count = 0
        upgraded_count = 0
        downgraded_count = 0
        reset_work_types_count = 0
        
        for worker in workers:
            try:
                # Получаем старый ранг
                old_rank = await WorkerRank.get_by_worker(worker.id)
                old_rank_type = old_rank.rank_type if old_rank else None
                old_work_types_limit = old_rank.get_work_types_limit() if old_rank else 1
                
                # Обновляем ранг (пересчитываем на основе заказов за последние 30 дней)
                new_rank = await WorkerRank.get_or_create_rank(worker.id)
                new_work_types_limit = new_rank.get_work_types_limit()
                
                # Проверяем, изменился ли ранг
                if old_rank_type and old_rank_type != new_rank.rank_type:
                    rank_levels = {'bronze': 1, 'silver': 2, 'gold': 3, 'platinum': 4}
                    old_level = rank_levels.get(old_rank_type, 0)
                    new_level = rank_levels.get(new_rank.rank_type, 0)
                    
                    if new_level > old_level:
                        upgraded_count += 1
                        logger.info(f'update_worker_ranks: Worker {worker.id} upgraded from {old_rank_type} to {new_rank.rank_type}')
                    elif new_level < old_level:
                        downgraded_count += 1
                        logger.info(f'update_worker_ranks: Worker {worker.id} downgraded from {old_rank_type} to {new_rank.rank_type}')
                        
                        # При понижении ранга ВСЕГДА отправляем уведомление
                        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
                        current_work_types_count = len(worker_sub.work_type_ids) if worker_sub and worker_sub.work_type_ids else 0
                        
                        # Проверяем, нужно ли обнулять направления
                        if worker_sub and worker_sub.work_type_ids and new_work_types_limit is not None and current_work_types_count > new_work_types_limit:
                                # Сохраняем старые направления для отображения в уведомлении
                                from app.data.database.models import WorkType
                                old_work_types_names = []
                                for wt_id in worker_sub.work_type_ids:
                                    work_type = await WorkType.get_work_type(id=int(wt_id))
                                    if work_type:
                                        old_work_types_names.append(work_type.work_type)
                                
                                # Обнуляем направления
                                worker_sub.work_type_ids = []
                                await worker_sub.save()
                                reset_work_types_count += 1
                                
                                # Устанавливаем флаг ожидания выбора (не считается изменением)
                                from app.data.database.models import WorkerWorkTypeChanges
                                work_type_changes = await WorkerWorkTypeChanges.get_or_create(worker.id)
                                work_type_changes.pending_selection = True
                                await work_type_changes.save()
                                
                                logger.info(f'update_worker_ranks: Reset work types for worker {worker.id} (had {current_work_types_count}, limit now {new_work_types_limit}), set pending_selection flag')
                                
                                # Отправляем уведомление исполнителю
                                try:
                                    old_rank_name = WorkerRank.RANK_TYPES[old_rank_type]['name']
                                    old_rank_emoji = WorkerRank.RANK_TYPES[old_rank_type]['emoji']
                                    new_rank_name = new_rank.get_rank_name()
                                    new_rank_emoji = new_rank.get_rank_emoji()
                                    
                                    notification_text = (
                                        f"⚠️ **Изменение ранга**\n\n"
                                        f"Ваш ранг изменился:\n"
                                        f"{old_rank_emoji} **{old_rank_name}** → {new_rank_emoji} **{new_rank_name}**\n\n"
                                        f"📊 **Изменение лимита направлений:**\n"
                                        f"Было доступно: **{old_work_types_limit if old_work_types_limit else 'без ограничений'}**\n"
                                        f"Стало доступно: **{new_work_types_limit}**\n\n"
                                        f"❌ **Ваши направления были сброшены:**\n"
                                    )
                                    
                                    for i, wt_name in enumerate(old_work_types_names, 1):
                                        notification_text += f"{i}. {wt_name}\n"
                                    
                                    notification_text += (
                                        f"\n💡 Вам нужно выбрать до {new_work_types_limit} направлений заново.\n"
                                        f"Нажмите **ОК**, чтобы перейти к выбору направлений."
                                    )
                                    
                                    # Создаем кнопку "ОК" которая перенаправит в раздел "Мои направления"
                                    builder = InlineKeyboardBuilder()
                                    builder.button(text="✅ ОК", callback_data="rank_downgrade_ok")
                                    
                                    await bot.send_message(
                                        chat_id=worker.tg_id,
                                        text=notification_text,
                                        reply_markup=builder.as_markup(),
                                        parse_mode='Markdown'
                                    )
                                    
                                    logger.info(f'update_worker_ranks: Sent rank downgrade notification to worker {worker.id}')
                                    
                                except Exception as notify_error:
                                    logger.error(f'update_worker_ranks: Failed to send notification to worker {worker.id} - {notify_error}')
                        
                        else:
                            # Направления НЕ обнулены (в рамках лимита или нет направлений вообще)
                            # Отправляем информационное уведомление
                            try:
                                old_rank_name = WorkerRank.RANK_TYPES[old_rank_type]['name']
                                old_rank_emoji = WorkerRank.RANK_TYPES[old_rank_type]['emoji']
                                new_rank_name = new_rank.get_rank_name()
                                new_rank_emoji = new_rank.get_rank_emoji()
                                
                                notification_text = (
                                    f"⚠️ **Изменение ранга**\n\n"
                                    f"Ваш ранг изменился:\n"
                                    f"{old_rank_emoji} **{old_rank_name}** → {new_rank_emoji} **{new_rank_name}**\n\n"
                                    f"📊 **Изменение лимита направлений:**\n"
                                    f"Было доступно: **{old_work_types_limit if old_work_types_limit else 'без ограничений'}**\n"
                                    f"Стало доступно: **{new_work_types_limit}**\n\n"
                                )
                                
                                if current_work_types_count > 0:
                                    # Получаем названия текущих направлений
                                    from app.data.database.models import WorkType
                                    current_work_types_names = []
                                    for wt_id in worker_sub.work_type_ids:
                                        work_type = await WorkType.get_work_type(id=int(wt_id))
                                        if work_type:
                                            current_work_types_names.append(work_type.work_type)
                                    
                                    notification_text += (
                                        f"✅ **Ваши направления сохранены:**\n"
                                        f"У вас было выбрано **{current_work_types_count}** направлений, "
                                        f"что в рамках нового лимита (**{new_work_types_limit}**).\n\n"
                                    )
                                    
                                    for i, wt_name in enumerate(current_work_types_names, 1):
                                        notification_text += f"{i}. {wt_name}\n"
                                    
                                    # Проверяем, можно ли добавить еще направлений
                                    remaining_slots = new_work_types_limit - current_work_types_count
                                    if remaining_slots > 0:
                                        notification_text += (
                                            f"\n💡 Вы можете выбрать еще **{remaining_slots}** "
                                            f"{'направление' if remaining_slots == 1 else 'направления' if remaining_slots < 5 else 'направлений'}.\n"
                                            f"Перейдите в раздел 'Мои направления' для изменения."
                                        )
                                    else:
                                        notification_text += (
                                            f"\n🎯 Вы используете максимальное количество направлений для вашего ранга."
                                        )
                                else:
                                    notification_text += (
                                        f"💡 У вас нет выбранных направлений.\n"
                                        f"Вы можете выбрать до **{new_work_types_limit}** "
                                        f"{'направление' if new_work_types_limit == 1 else 'направления' if new_work_types_limit < 5 else 'направлений'}.\n"
                                        f"Перейдите в раздел 'Мои направления' для выбора."
                                    )
                                
                                # Кнопка без callback (просто информационное сообщение)
                                await bot.send_message(
                                    chat_id=worker.tg_id,
                                    text=notification_text,
                                    parse_mode='Markdown'
                                )
                                
                                logger.info(f'update_worker_ranks: Sent rank downgrade info (no reset) to worker {worker.id}')
                                
                            except Exception as notify_error:
                                logger.error(f'update_worker_ranks: Failed to send info notification to worker {worker.id} - {notify_error}')
                
                updated_count += 1
                
            except Exception as worker_error:
                logger.error(f'update_worker_ranks: Error updating rank for worker {worker.id} - {worker_error}')
        
        logger.info(f'update_worker_ranks: Updated {updated_count} workers. Upgraded: {upgraded_count}, Downgraded: {downgraded_count}, Reset work types: {reset_work_types_count}')
        
    except Exception as e:
        logger.error(f'update_worker_ranks: Error - {e}')


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
