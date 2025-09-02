from datetime import datetime, timedelta

from aiogram.exceptions import TelegramForbiddenError

import config
from app.data.database.models import Banned, WorkType, WorkSubType, Customer, BannedAbs, Worker, WorkerAndSubscription, \
    SubscriptionType, City, WorkerAndCustomer, WorkerAndRefsAssociation
from app.keyboards import KeyboardCollection
from app.untils import help_defs, checks
from loaders import bot


async def ban_task(message, work_type_id, task, time, ban_reason, msg):
    kbc = KeyboardCollection()

    banned = await Banned.get_banned(tg_id=message.chat.id)
    ban_end = str(datetime.now() + timedelta(hours=24))

    work_type_id_list = work_type_id.split('|')
    work_type = await WorkType.get_work_type(id=int(work_type_id_list[0]))
    work = work_type.work_type.capitalize()

    if len(work_type_id_list) > 1:
        work_sub_type = await WorkSubType.get_work_type(id=int(work_type_id_list[1]))
        work += " | " + work_sub_type.work_type

    customer = await Customer.get_customer(tg_id=message.chat.id)

    text = (f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n')

    text = help_defs.escape_markdown(text=text)  # todo: moment

    file_path = help_defs.create_file_in_directory_with_timestamp(id=message.chat.id, text=text,
                                                                  path='app/data/banned/text/')

    banned_abs = BannedAbs(
        id=None,
        customer_id=customer.id,
        work_type_id=int(work_type_id_list[0]),
        city_id=customer.city_id,
        photo_path=None,
        text_path=file_path,
        date_to_delite=datetime.today() + timedelta(days=30),
        photos_len=0
    )
    await banned_abs.save()

    banned_abs = await BannedAbs.get_all_by_customer(customer_id=customer.id)

    banned_abs = banned_abs[-1]

    text = (f'Заблокирован пользователь @{customer.tg_name}\n'
            f'Общий ID пользователя: #{customer.tg_id}\n\n'
            f'{work}\n\n'
            f'Задача: {task}\n'
            f'Время: {time}\n'
            f'\n'
            f'{ban_reason}')

    text = help_defs.escape_markdown(text=text)  # todo: moment

    await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)

    await bot.send_message(chat_id=config.BLOCKED_CHAT,
                           text=text,
                           protect_content=False, reply_markup=kbc.unban(banned_abs.id))

    if banned:
        if banned.ban_counter >= 3:
            await banned.update(forever=True, ban_now=True)
            await message.answer('Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                          reply_markup=kbc.support_btn())
            return
        await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
        await message.answer(
            'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
            reply_markup=kbc.support_btn())
        return
    new_banned = Banned(id=None, tg_id=message.chat.id,
                        ban_counter=1, ban_end=ban_end, ban_now=True,
                        forever=False, ban_reason=ban_reason)
    await new_banned.save()
    await message.answer(
        'Упс, к сожалению пришлось закрыть Вам доступ на сутки за нарушение правил, если считаете, что это не так, Вы можете это обжаловать написав нам.',
        reply_markup=kbc.support_btn())


async def same_task(message, advertisements, text):
    kbc = KeyboardCollection()

    double = False

    if advertisements:
        for advertisement in advertisements:
            text_old = help_defs.read_text_file(advertisement.text_path)
            if await checks.are_texts_similar(text_old, text):
                await message.answer(
                    'Вы предлагали схожий запрос, удалите предыдущий и попробуйте снова',
                    reply_markup=kbc.menu_btn())
                double = True
    return double


async def close_task(workers_and_abs, advertisement_now, workers_for_assessments, customer):
    for worker_and_abs in workers_and_abs:
        worker = await Worker.get_worker(id=worker_and_abs.worker_id)
        if worker is None:
            continue
        worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
        sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
        if sub.notification:

            city = await City.get_city(id=advertisement_now.city_id)
            if advertisement_now.work_type_id == 20:
                text = help_defs.read_text_file(advertisement_now.text_path)
                text = text.split(' ||| ')
                text = f'Заказчик закрыл объявление {advertisement_now.id}\nг. {city.city}\n' + text[0]
            else:
                text = f'Заказчик закрыл объявление {advertisement_now.id}\nг. {city.city}\n' + help_defs.read_text_file(
                    advertisement_now.text_path)

            try:
                await bot.send_message(chat_id=worker.tg_id, text=text)
            except TelegramForbiddenError:
                await worker.delete()
                pass
        if worker_and_abs.applyed:
            if await WorkerAndCustomer.get_by_worker_and_customer(worker_id=worker.id, customer_id=customer.id):
                await worker_and_abs.delete()
                if worker.order_count + 1 == 5:
                    if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                        await worker_and_ref.update(work_condition=True)
                        if worker_and_ref.ref_condition:
                            await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                            await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                            await bot.send_message(chat_id=worker.tg_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                    elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                        await worker_and_ref.update(ref_condition=True)
                        if worker_and_ref.work_condition:
                            await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                            worker_main = await Worker.get_worker(id=worker_and_ref.worker_id)
                            await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                            await bot.send_message(chat_id=worker_main.tg_id,
                                                   text='Условия вашей реферальной программы выполнены!')

                continue
            else:
                workers_for_assessments.append(worker)
                worker_and_customer = WorkerAndCustomer(worker_id=worker.id, customer_id=customer.id)
                await worker_and_customer.save()
                await worker.update_order_count(order_count=worker.order_count + 1)
                await worker.update_order_count_on_week(order_count_on_week=worker.order_count_on_week + 1)
                if worker.order_count + 1 == 5:
                    if worker_and_ref := await WorkerAndRefsAssociation.get_refs_by_worker(worker_id=worker.id):
                        await worker_and_ref.update(work_condition=True)
                        if worker_and_ref.ref_condition:
                            await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                            await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                            await bot.send_message(chat_id=worker.tg_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                    elif worker_and_ref := await WorkerAndRefsAssociation.get_by_ref(ref_id=worker.tg_id):
                        await worker_and_ref.update(ref_condition=True)
                        if worker_and_ref.work_condition:
                            await worker_and_ref.update(worker_bonus=True, ref_bonus=True)
                            worker_main = await Worker.get_worker(id=worker_and_ref.worker_id)
                            await bot.send_message(chat_id=worker_and_ref.ref_id,
                                                   text='Условия вашей реферальной программы выполнены!')
                            await bot.send_message(chat_id=worker_main.tg_id,
                                                   text='Условия вашей реферальной программы выполнены!')

        await worker_and_abs.delete()
    return workers_for_assessments
