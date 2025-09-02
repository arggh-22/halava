import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import ProfanityWord, BlockWordShort, BlockWord, WhiteWord, BlockWordMessage, \
    BlockWordShortMessage, BlockWordPersonal, BlockWordShortPersonal, BlockWordPhoto, BlockWordShortPhoto
from app.keyboards import KeyboardCollection
from app.states import AdminStates
from loaders import bot

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(F.data == 'menu_admin_stop_words',
                       StateFilter(AdminStates.menu, AdminStates.edit_stop_words, AdminStates.edit_stop_words_profanity,
                                   AdminStates.edit_stop_words_short, AdminStates.edit_stop_words_long,
                                   AdminStates.edit_white_words, AdminStates.edit_stop_words_short_message,
                                   AdminStates.edit_stop_words_long_message, AdminStates.edit_personal_stop_words,
                                   AdminStates.edit_stop_words_short_personal, AdminStates.edit_photo_stop_words,
                                   AdminStates.edit_stop_words_short_photo))
async def menu_send_msg_admin_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('menu_send_msg_admin_keyboard...')
    kbc = KeyboardCollection()

    text = (f'Меню\n\n'
            f'Выберете интересующую вас группу стоп слов\n'
            f'Длинные стоп слова - больше 5 букв\n'
            f'Короткие стоп слова - слова из 5 букв и короче\n'
            f'Матерные слова\n'
            f'Белый список')

    await state.set_state(AdminStates.edit_stop_words)
    await callback.message.edit_text(text=text, reply_markup=kbc.menu_admin_keyboard_stop_words())


@router.callback_query(F.data == 'stop_words_long',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_long,
                                   AdminStates.edit_stop_words_long_insert, AdminStates.edit_stop_words_long_delite))
async def stop_words_long(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_long_message',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_long_message,
                                   AdminStates.edit_stop_words_long_message_insert,
                                   AdminStates.edit_stop_words_long_message_delite))
async def stop_words_long_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long_message)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short,
                                   AdminStates.edit_stop_words_short_insert, AdminStates.edit_stop_words_short_delite))
async def stop_words_short(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short_message',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short_message,
                                   AdminStates.edit_stop_words_short_message_insert,
                                   AdminStates.edit_stop_words_short_message_delite))
async def stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_message)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_profanity',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_profanity,
                                   AdminStates.edit_stop_words_profanity_insert,
                                   AdminStates.edit_stop_words_profanity_delite))
async def stop_words_profanity(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_profanity)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'white_words', StateFilter(AdminStates.edit_stop_words, AdminStates.edit_white_words,
                                                            AdminStates.edit_white_words_insert,
                                                            AdminStates.edit_white_words_delite))
async def white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_white_words)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_long_personal',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_personal_stop_words,
                                   AdminStates.edit_personal_stop_words_insert,
                                   AdminStates.edit_personal_stop_words_delite))
async def white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_personal_stop_words)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short_personal',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short_personal,
                                   AdminStates.edit_stop_words_short_personal_insert,
                                   AdminStates.edit_stop_words_short_personal_delite))
async def stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_personal...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_personal)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_long_photo',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_photo_stop_words,
                                   AdminStates.edit_photo_stop_words_insert,
                                   AdminStates.edit_photo_stop_words_delite))
async def white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_photo_stop_words)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short_photo',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short_photo,
                                   AdminStates.edit_stop_words_short_photo_insert,
                                   AdminStates.edit_stop_words_short_photo_delite))
async def stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_photo)
    await callback.message.edit_text(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_profanity))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_profanity_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_profanity'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_long_message))
async def stop_words_long_message_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_long_message_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_personal_stop_words))
async def stop_words_long_message_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_personal_stop_words_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short_message))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_message_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_message_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_long))
async def stop_words_long_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_long_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short))
async def stop_words_short_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_white_words))
async def white_words_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_white_words_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('white_words'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short_personal))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_personal_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_personal_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_photo_stop_words))
async def stop_words_long_message_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_photo_stop_words_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short_photo))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_photo_delite)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_profanity_delite))
async def stop_words_profanity_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await ProfanityWord.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_profanity)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_message_delite))
async def stop_words_long_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordMessage.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long_message)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_personal_stop_words_delite))
async def stop_words_long_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordPersonal.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_personal_stop_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_message_delite))
async def stop_words_short_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordShortMessage.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_message)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_delite))
async def stop_words_short_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_short_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordShort.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_delite.lower():
            target_word = short_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_delite))
async def stop_words_long_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    long_words = await BlockWord.get_all()

    target_word = None

    for long_word in long_words:
        if long_word.word.lower() == word_to_delite.lower():
            target_word = long_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_white_words_delite))
async def stop_white_words_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_white_words_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    white_words_list = await WhiteWord.get_all()

    target_word = None

    for white_word in white_words_list:
        if white_word.word.lower() == word_to_delite.lower():
            target_word = white_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_white_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_personal_delite))
async def stop_words_short_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordShortPersonal.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_personal)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_photo_stop_words_delite))
async def stop_words_long_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordPhoto.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_photo_stop_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_photo_delite))
async def stop_words_short_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await BlockWordShortPhoto.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_delite.lower():
            target_word = profanity_word

    if target_word:
        await target_word.delete()
        text = f'Слово {word_to_delite} удалено\nЧто вы хотите сделать?'
    else:
        text = f'Слово {word_to_delite} Не найдено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_photo)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_profanity))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_profanity_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_profanity'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_long))
async def stop_words_long_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_long_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_long_message))
async def stop_words_long_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_long_message_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_personal_stop_words))
async def stop_words_long_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_personal_stop_words_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short_message))
async def stop_words_short_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_message_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short_personal))
async def stop_words_short_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_personal_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_personal_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short))
async def stop_words_short_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_white_words))
async def white_words_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_white_words_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('white_words'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_photo_stop_words))
async def stop_words_long_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_photo_stop_words_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short_photo))
async def stop_words_short_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_photo_insert)
    msg = await callback.message.edit_text(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_personal'))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_profanity_insert))
async def stop_words_profanity_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    profanity_words = await ProfanityWord.get_all()

    target_word = None

    for profanity_word in profanity_words:
        if profanity_word.word.lower() == word_to_insert.lower():
            target_word = profanity_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = ProfanityWord(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_profanity)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_insert))
async def stop_words_short_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_short_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordShort.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordShort(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_message_insert))
async def stop_words_long_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordMessage.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordMessage(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long_message)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_personal_stop_words_insert))
async def stop_words_long_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordPersonal.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordPersonal(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_personal_stop_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_message_insert))
async def stop_stop_words_short_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_stop_words_short_message_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordShortMessage.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordShortMessage(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_message)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_personal_insert))
async def stop_stop_words_short_personal_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_stop_words_short_personal_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordShortPersonal.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordShortPersonal(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_personal)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_insert))
async def stop_words_long_look_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    long_words = await BlockWord.get_all()

    target_word = None

    for long_word in long_words:
        if long_word.word.lower() == word_to_insert.lower():
            target_word = long_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWord(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_white_words_insert))
async def stop_words_long_look_text(message: Message, state: FSMContext) -> None:
    logger.debug('white_words_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    white_words_list = await WhiteWord.get_all()

    target_word = None

    for white_word in white_words_list:
        if white_word.word.lower() == word_to_insert.lower():
            target_word = white_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWord(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_white_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_photo_stop_words_insert))
async def stop_words_long_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordPhoto.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordPhoto(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_photo_stop_words)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_photo_insert))
async def stop_stop_words_short_photo_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_stop_words_short_photo_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text
    state_data = await state.get_data()
    msg_id = str(state_data.get('msg_id'))

    short_words = await BlockWordShortPhoto.get_all()

    target_word = None

    for short_word in short_words:
        if short_word.word.lower() == word_to_insert.lower():
            target_word = short_word

    if target_word:
        text = f'Слово {word_to_insert} уже есть\nЧто вы хотите сделать?'
    else:
        target_word = BlockWordShortPhoto(id=None, word=word_to_insert.lower())
        await target_word.save()
        text = f'Слово {word_to_insert} Добавлено\nЧто вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_photo)
    await message.answer(text=text, reply_markup=kbc.admin_edit_chose())
    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
