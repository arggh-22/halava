import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, InputMediaPhoto

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import Customer, Banned, BannedAbs, Abs, Worker, WorkerAndSubscription, WorkersAndAbs, \
    SubscriptionType, UserAndSupportQueue
from app.keyboards import KeyboardCollection
from app.states import AdminStates
from app.untils import help_defs
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(lambda c: c.data.startswith('unban_'))
async def unblock_advertisement(callback: CallbackQuery) -> None:
    kbc = KeyboardCollection()
    banned_abs_id = int(callback.data.split('_')[1])
    logger.debug(f'unblock_advertisement...')

    banned_abs = await BannedAbs.get_one(id=banned_abs_id)
    customer = await Customer.get_customer(id=banned_abs.customer_id)
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

    if banned_abs.photo_path:
        photo_path = help_defs.copy_file(banned_abs.photo_path, f'app/data/photo/{customer.tg_id}/')
        help_defs.add_watermark(photo_path)
    else:
        photo_path = None

    text_path = help_defs.copy_file(banned_abs.text_path, f'app/data/text/{customer.tg_id}/')

    if not text_path:
        await banned_abs.delete(delite_photo=True)
        await callback.message.delete()
        await callback.message.answer('Пользователь разблокирован')
        await bot.send_message(chat_id=customer.tg_id,
                               text='Вы были разблокированы, приносим извинения за предоставленные неудобства.\nВызовите команду /menu чтобы продолжить работу')
        return

    new_abs = Abs(
        id=None,
        customer_id=customer.id,
        work_type_id=banned_abs.work_type_id,
        city_id=customer.city_id,
        photo_path=photo_path,
        text_path=text_path,
        date_to_delite=datetime.today() + timedelta(days=30),
        count_photo=banned_abs.photos_len
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
                        if photo_path:
                            await bot.send_photo(chat_id=worker.tg_id,
                                                 photo=FSInputFile(photo_path),
                                                 caption=text,
                                                 reply_markup=kbc.apply_btn(advertisement.id)
                                                 )
                        else:
                            await bot.send_message(chat_id=worker.tg_id,
                                                   text=text,
                                                   reply_markup=kbc.apply_btn(advertisement.id)
                                                   )
                elif worker_sub.unlimited_work_types:
                    if photo_path:
                        await bot.send_photo(chat_id=worker.tg_id,
                                             photo=FSInputFile(photo_path),
                                             caption=text,
                                             reply_markup=kbc.apply_btn(advertisement.id)
                                             )
                    else:
                        await bot.send_message(chat_id=worker.tg_id,
                                               text=text,
                                               reply_markup=kbc.apply_btn(advertisement.id)
                                               )
            except TelegramForbiddenError:
                pass

    await callback.message.delete_reply_markup()
    await banned_abs.delete(delite_photo=False)
    await callback.message.answer('Пользователь разблокирован')
    await bot.send_message(chat_id=customer.tg_id,
                           text='Вы были разблокированы, приносим извинения за предоставленные неудобства. Объявление было опубликовано\nВызовите команду /menu чтобы продолжить работу')


@router.callback_query(lambda c: c.data.startswith('unban-user_'))
async def unblock_user(callback: CallbackQuery) -> None:
    banned_abs_id = int(callback.data.split('_')[1])
    logger.debug(f'unblock_user...')

    banned_abs = await BannedAbs.get_one(id=banned_abs_id)
    if not banned_abs:
        await callback.message.answer('Пользователь разблокирован')
        return
    customer = await Customer.get_customer(id=banned_abs.customer_id)
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

    await banned_abs.delete(delite_photo=True)
    await callback.message.delete_reply_markup()
    await callback.message.answer('Пользователь разблокирован')
    await bot.send_message(chat_id=customer.tg_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.callback_query(lambda c: c.data.startswith('unban-user-msg_'))
async def unblock_user(callback: CallbackQuery) -> None:
    banned_id = int(callback.data.split('_')[1])
    logger.debug(f'unban-user-msg...')

    user = await Customer.get_customer(tg_id=banned_id)
    if user is None:
        user = await Worker.get_worker(tg_id=banned_id)

    banned = await Banned.get_banned(tg_id=user.tg_id)

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

    await callback.message.delete_reply_markup()
    await callback.message.answer('Пользователь разблокирован')
    await bot.send_message(chat_id=user.tg_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.callback_query(lambda c: c.data.startswith('block-it_'))
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    advertisement = await Abs.get_one(id=advertisement_id)
    if not advertisement:
        await callback.message.delete()
        await callback.message.answer(text=f'Объявление {advertisement_id}, было удалено')
        return
    customer = await Customer.get_customer(id=advertisement.customer_id)
    banned = await Banned.get_banned(tg_id=customer.tg_id)

    ban_end = str(datetime.now() + timedelta(hours=24))

    if banned:
        if banned.ban_counter >= 3:
            await banned.update(forever=True, ban_now=True)
            await bot.send_message(chat_id=banned.tg_id,
                                   text='Ваше объявление было с нарушением правил платформы.\nВы заблокированы навсегда',
                                   reply_markup=kbc.support_btn())
        else:
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
            await bot.send_message(chat_id=banned.tg_id, text=f'Ваше объявление было с нарушением правил платформы.\n'
                                                              f'Вы заблокированы на 24 часа.'
                                                              f'{banned.ban_counter + 1} из 3',
                                   reply_markup=kbc.support_btn())
    else:
        new_banned = Banned(id=None, tg_id=customer.tg_id,
                            ban_counter=1, ban_end=ban_end, ban_now=True,
                            forever=False, ban_reason='по решению администратора')
        await new_banned.save()
        await bot.send_message(chat_id=customer.tg_id, text='Ваше объявление было с нарушением правил платформы.\n'
                                                            'Вы заблокированы на 24 часа.\n'
                                                            'блокировка 1 из 3',
                               reply_markup=kbc.support_btn())
    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
            if sub.notification:
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление{advertisement.id} неактуально')
            await worker_and_abs.delete()

    await callback.message.delete_reply_markup()
    await advertisement.delete(delite_photo=True)
    await state.set_state(AdminStates.add_comment_to_lock_abs_chat)
    await callback.message.delete()
    msg = await callback.message.answer(text=f'Пользователь с общим ID: {customer.tg_id} заблокирован, объявление удалено\nВведите комментарий для блокировки', reply_markup=kbc.skip_btn_admin())
    await state.update_data(customer_id=customer.tg_id, msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('go-to-ban_'))
async def block_advertisement(callback: CallbackQuery) -> None:
    photo_num = int(callback.data.split('_')[1])
    advertisement_id = int(callback.data.split('_')[2])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    advertisement = await Abs.get_one(id=advertisement_id)
    if not advertisement:
        await callback.message.delete()
        await callback.message.answer(text=f'Объявление {advertisement_id}, было удалено')
        return

    if photo_num <= -1:
        photo_num = advertisement.count_photo - 1
    elif photo_num > (advertisement.count_photo - 1):
        photo_num = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(advertisement.photo_path[str(photo_num)]),
            caption=callback.message.caption),
        protect_content=False,
        reply_markup=kbc.block_abs_log(
            advertisement.id,
            photo_num=photo_num,
            photo_len=advertisement.count_photo)
    )


@router.callback_query(lambda c: c.data.startswith('go-to-unban_'))
async def block_advertisement(callback: CallbackQuery) -> None:
    photo_num = int(callback.data.split('_')[1])
    advertisement_id = int(callback.data.split('_')[2])
    logger.debug(f'block_advertisement...')

    kbc = KeyboardCollection()

    advertisement = await BannedAbs.get_one(id=advertisement_id)
    if not advertisement:
        await callback.message.delete()
        await callback.message.answer(text=f'Объявление {advertisement_id}, было удалено')
        return

    if photo_num <= -1:
        photo_num = advertisement.photos_len - 1
    elif photo_num > (advertisement.photos_len - 1):
        photo_num = 0

    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile(advertisement.photo_path[str(photo_num)]),
            caption=callback.message.caption),
        protect_content=False,
        reply_markup=kbc.unban(
            advertisement.id,
            photo_num=photo_num,
            photo_len=advertisement.photos_len)
    )


@router.callback_query(lambda c: c.data.startswith('delite-it-rep_'))
async def delite_advertisement(callback: CallbackQuery) -> None:
    advertisement_id = int(callback.data.split('_')[1])
    logger.debug(f'delite_advertisement...')

    advertisement = await Abs.get_one(id=advertisement_id)
    if not advertisement:
        await callback.message.delete()
        await callback.message.answer(text=f'Объявление {advertisement_id}, было удалено')
        return

    workers_and_abs = await WorkersAndAbs.get_by_abs(abs_id=advertisement.id)
    if workers_and_abs:
        for worker_and_abs in workers_and_abs:
            worker = await Worker.get_worker(id=worker_and_abs.worker_id)
            worker_sub = await WorkerAndSubscription.get_by_worker(worker_id=worker.id)
            sub = await SubscriptionType.get_subscription_type(id=worker_sub.subscription_id)
            if sub.notification:
                await bot.send_message(chat_id=worker.tg_id, text=f'Объявление{advertisement.id} неактуально')
            await worker_and_abs.delete()

    await callback.message.delete_reply_markup()
    await advertisement.delete(delite_photo=True)
    await callback.message.delete()
    await callback.message.answer(text=f'Объявление удалено\n')


@router.callback_query(lambda c: c.data.startswith('block-it-message_'))
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = int(callback.data.split('_')[1])
    logger.debug(f'block-it-message_...')

    kbc = KeyboardCollection()

    banned = await Banned.get_banned(tg_id=user_id)

    ban_end = str(datetime.now() + timedelta(hours=24))

    if banned:
        if banned.ban_counter >= 3:
            await banned.update(forever=True, ban_now=True)
            await bot.send_message(chat_id=banned.tg_id,
                                   text='Вы заблокированы навсегда за неоднократное нарушение правил платформы',
                                   reply_markup=kbc.support_btn())
            return
        await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end)
        await bot.send_message(chat_id=banned.tg_id, text='Вы заблокированы на 24 за нарушение правил платформы',
                               reply_markup=kbc.support_btn())
        return
    new_banned = Banned(id=None, tg_id=user_id,
                        ban_counter=1, ban_end=ban_end, ban_now=True,
                        forever=False, ban_reason='по решению администратора')
    await new_banned.save()
    await bot.send_message(chat_id=user_id, text='Вы заблокированы на 24 за нарушение правил платформы',
                           reply_markup=kbc.support_btn())

    await callback.message.delete_reply_markup()
    await state.set_state(AdminStates.add_comment_to_lock_abs_chat)
    await callback.message.delete()
    msg = await callback.message.answer(text=f'Пользователь с общим ID: {user_id} заблокирован, объявление удалено\nВведите комментарий для блокировки', reply_markup=kbc.skip_btn_admin())
    await state.update_data(customer_id=user_id, msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('delite-it-photo_'))
async def block_photo_profile(callback: CallbackQuery, state: FSMContext) -> None:
    worker_id = int(callback.data.split('_')[1])
    logger.debug(f'block_photo_profile...')

    kbc = KeyboardCollection()

    worker = await Worker.get_worker(id=worker_id)

    is_photo = True if worker.profile_photo else False

    if is_photo:
        await callback.message.answer(
            text=f'Пользователь уже сам удалил фото профиля')
        return

    await worker.update_profile_photo(profile_photo=None)
    await callback.message.delete_reply_markup()

    await state.set_state(AdminStates.add_comment_to_lock_profile_photo)
    await callback.message.delete()
    msg = await callback.message.answer(text=f'Аватарка пользователя с общим ID: {worker.tg_id} удалена\nВведите комментарий', reply_markup=kbc.skip_btn_admin())
    await state.update_data(worker_id=worker.tg_id, msg_id=msg.message_id)


@router.callback_query(F.data == 'skip_it', AdminStates.add_comment_to_lock_profile_photo)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'block_advertisement skip_it...')
    state_data = await state.get_data()
    worker_id = int(state_data.get('worker_id'))
    text = 'К сожалению фото профиля не соответствует установленным требованиям, повторите попытку пожалуйста снова 😞'
    try:
        await bot.send_message(chat_id=worker_id, text=text)
    except TelegramBadRequest:
        pass

    await state.clear()
    await callback.message.delete()


@router.message(F.text, AdminStates.add_comment_to_lock_profile_photo)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'block_advertisement text...')

    state_data = await state.get_data()
    worker_id = int(state_data.get('worker_id'))
    msg_id = int(state_data.get('msg_id'))

    msg_to_send = message.text

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    await message.answer(text='Сообщение пользователю отправлено')
    try:
        await bot.send_message(chat_id=worker_id, text=f'Сообщение от администрации бота: "{msg_to_send}"')
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == 'skip_it', AdminStates.add_comment_to_lock_abs_chat)
async def block_advertisement(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'block_advertisement skip_it...')
    await state.clear()
    await callback.message.delete()


@router.message(F.text, AdminStates.add_comment_to_lock_abs_chat)
async def msg_to_worker_text(message: Message, state: FSMContext) -> None:
    logger.debug(f'block_advertisement text...')

    state_data = await state.get_data()
    customer_id = int(state_data.get('customer_id'))
    msg_id = int(state_data.get('msg_id'))

    customer = await Customer.get_customer(tg_id=customer_id)

    msg_to_send = message.text

    banned = await Banned.get_banned(tg_id=customer.tg_id)
    await banned.update(ban_reason=msg_to_send)

    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)

    await message.answer(text='Сообщение пользователю отправлено')
    try:
        await bot.send_message(chat_id=customer.tg_id, text=f'Сообщение от администрации бота: "{msg_to_send}"')
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data.startswith('answer-it_'))
async def admin_answer_user(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug(f'admin_answer_user...')

    user_tg_id = int(callback.data.split('_')[1])

    await callback.message.delete_reply_markup()
    await state.set_state(AdminStates.admin_answer_user)

    msg = await callback.message.answer(text='Напишите ответ пользователю')
    await state.update_data(user_tg_id=user_tg_id)
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(lambda c: c.data.startswith('unban-user-support_'))
async def unblock_user(callback: CallbackQuery) -> None:
    user_id = int(callback.data.split('_')[1])
    logger.debug(f'unblock_user...')

    banned = await Banned.get_banned(tg_id=user_id)

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

    await callback.message.answer('Пользователь разблокирован')
    await callback.message.delete()
    await bot.send_message(chat_id=user_id,
                           text='Вы были разблокированы.\nВызовите команду /menu чтобы продолжить работу')


@router.callback_query(lambda c: c.data.startswith('hide-unban-button'))
async def unblock_user(callback: CallbackQuery) -> None:
    logger.debug(f'hide-unban-button...')
    await callback.message.delete()


@router.message(F.text, AdminStates.admin_answer_user)
async def send_worker_with_msg(message: Message, state: FSMContext) -> None:
    logger.debug(f'send_worker_with_msg...')
    kbc = KeyboardCollection()

    msg_to_send = message.text

    state_data = await state.get_data()
    user_tg_id = int(state_data.get('user_tg_id'))
    msg_id = int(state_data.get('msg_id'))

    await state.clear()

    queue = await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=user_tg_id)
    queue.admin_messages.append(msg_to_send)
    await queue.update(admin_messages=queue.admin_messages, turn=False)

    text = f'Ответ от поддержки: "{msg_to_send}"'

    try:
        await bot.send_message(chat_id=user_tg_id, text=text, reply_markup=kbc.support_btn())
    except TelegramForbiddenError:
        await message.answer('К сожалению пользователь заблокировал бота, сообщение не отправлено')
        return
    if banned := await Banned.get_banned(tg_id=user_tg_id):
        if banned.ban_now:
            await message.answer(text=f'Ответ пользователю ID {user_tg_id} успешно отправлен!', reply_markup=kbc.support_unban(user_tg_id))
    else:
        await message.answer(text=f'Ответ пользователю ID {user_tg_id} успешно отправлен!')
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)