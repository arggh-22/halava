import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

# Импорт вспомогательных модулей и компонентов из приложения
from app.data.database.models import (
    ProfanityWord, BlockWordShort, BlockWord, WhiteWord, BlockWordMessage, BlockWordShortMessage, BlockWordPhoto,
    BlockWordShortPhoto
)
from app.keyboards import KeyboardCollection
from app.states import AdminStates

router = Router()
router.message.filter(F.from_user.id != F.bot.id)
logger = logging.getLogger()


@router.callback_query(F.data == 'menu_admin_stop_words',
                       StateFilter(AdminStates.menu, AdminStates.edit_stop_words, AdminStates.edit_stop_words_profanity,
                                   AdminStates.edit_stop_words_short, AdminStates.edit_stop_words_long,
                                   AdminStates.edit_white_words, AdminStates.edit_stop_words_short_message,
                                   AdminStates.edit_stop_words_long_message, AdminStates.edit_photo_stop_words,
                                   AdminStates.edit_stop_words_short_photo, AdminStates.edit_stop_words_long_look,
                                   AdminStates.edit_stop_words_short_look, AdminStates.edit_white_words_look,
                                   AdminStates.edit_stop_words_profanity_look, AdminStates.edit_stop_words_long_message_look,
                                   AdminStates.edit_stop_words_short_message_look, AdminStates.edit_photo_stop_words_look,
                                   AdminStates.edit_stop_words_short_photo_look))
async def menu_send_msg_admin_keyboard(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('menu_send_msg_admin_keyboard...')
    kbc = KeyboardCollection()

    text = (f'Меню\n\n'
            f'Выберите интересующую вас группу стоп слов\n'
            f'Длинные стоп слова - больше 5 букв\n'
            f'Короткие стоп слова - слова из 5 букв и короче\n'
            f'Матерные слова\n'
            f'Белый список')

    await state.set_state(AdminStates.edit_stop_words)
    await callback.message.answer(text=text, reply_markup=kbc.menu_admin_keyboard_stop_words())


@router.callback_query(F.data == 'stop_words_long',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_long,
                                   AdminStates.edit_stop_words_long_insert, AdminStates.edit_stop_words_long_delite,
                                   AdminStates.edit_stop_words_long_look))
async def stop_words_long(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_long_message',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_long_message,
                                   AdminStates.edit_stop_words_long_message_insert,
                                   AdminStates.edit_stop_words_long_message_delite,
                                   AdminStates.edit_stop_words_long_message_look))
async def stop_words_long_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_long_message)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short,
                                   AdminStates.edit_stop_words_short_insert, AdminStates.edit_stop_words_short_delite,
                                   AdminStates.edit_stop_words_short_look))
async def stop_words_short(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short_message',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short_message,
                                   AdminStates.edit_stop_words_short_message_insert,
                                   AdminStates.edit_stop_words_short_message_delite,
                                   AdminStates.edit_stop_words_short_message_look))
async def stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_message)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_profanity',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_profanity,
                                   AdminStates.edit_stop_words_profanity_insert,
                                   AdminStates.edit_stop_words_profanity_delite,
                                   AdminStates.edit_stop_words_profanity_look))
async def stop_words_profanity(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_profanity)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'white_words', StateFilter(AdminStates.edit_stop_words, AdminStates.edit_white_words,
                                                            AdminStates.edit_white_words_insert,
                                                            AdminStates.edit_white_words_delite,
                                                            AdminStates.edit_white_words_look))
async def white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_white_words)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_long_photo',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_photo_stop_words,
                                   AdminStates.edit_photo_stop_words_insert,
                                   AdminStates.edit_photo_stop_words_delite,
                                   AdminStates.edit_photo_stop_words_look))
async def white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_photo_stop_words)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'stop_words_short_photo',
                       StateFilter(AdminStates.edit_stop_words, AdminStates.edit_stop_words_short_photo,
                                   AdminStates.edit_stop_words_short_photo_insert,
                                   AdminStates.edit_stop_words_short_photo_delite,
                                   AdminStates.edit_stop_words_short_photo_look))
async def stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo...')
    kbc = KeyboardCollection()

    text = f'Что вы хотите сделать?'

    await state.set_state(AdminStates.edit_stop_words_short_photo)
    await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose())


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_profanity))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_profanity_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_profanity'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_long_message))
async def stop_words_long_message_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_long_message_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short_message))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_message_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_message_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_long))
async def stop_words_long_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_long_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short))
async def stop_words_short_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_white_words))
async def white_words_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_white_words_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('white_words'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_photo_stop_words))
async def stop_words_long_message_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_photo_stop_words_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_photo'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'delite', StateFilter(AdminStates.edit_stop_words_short_photo))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo_delite...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите удалить'

    await state.set_state(AdminStates.edit_stop_words_short_photo_delite)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_photo'))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_profanity_delite))
async def stop_words_profanity_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_message_delite))
async def stop_words_long_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_message_delite))
async def stop_words_short_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_delite))
async def stop_words_short_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_short_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_delite))
async def stop_words_long_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_white_words_delite))
async def stop_white_words_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_white_words_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_photo_stop_words_delite))
async def stop_words_long_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_photo_delite))
async def stop_words_short_message_delite_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_photo_delite_text...')
    kbc = KeyboardCollection()
    word_to_delite = message.text

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


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_profanity))
async def stop_words_profanity_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_profanity_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_profanity'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_long))
async def stop_words_long_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_long_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_long_message))
async def stop_words_long_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_long_message_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short_message))
async def stop_words_short_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_message_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_message'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short))
async def stop_words_short_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_white_words))
async def white_words_delite(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('white_words_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_white_words_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('white_words'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_photo_stop_words))
async def stop_words_long_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_photo_stop_words_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_long_photo'))
    await state.update_data(msg_id=msg.message_id)


@router.callback_query(F.data == 'insert', StateFilter(AdminStates.edit_stop_words_short_photo))
async def stop_words_short_message_insert(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('stop_words_short_photo_insert...')
    kbc = KeyboardCollection()

    text = f'Напишите слово, которое хотите добавить'

    await state.set_state(AdminStates.edit_stop_words_short_photo_insert)
    msg = await callback.message.answer(text=text, reply_markup=kbc.admin_back_btn('stop_words_short_photo'))
    await state.update_data(msg_id=msg.message_id)


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_profanity_insert))
async def stop_words_profanity_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_profanity_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_insert))
async def stop_words_short_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_short_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_message_insert))
async def stop_words_long_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_message_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_message_insert))
async def stop_stop_words_short_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_stop_words_short_message_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_long_insert))
async def stop_words_long_look_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_white_words_insert))
async def stop_words_long_look_text(message: Message, state: FSMContext) -> None:
    logger.debug('white_words_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_photo_stop_words_insert))
async def stop_words_long_message_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_words_long_personal_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


@router.message(F.text, StateFilter(AdminStates.edit_stop_words_short_photo_insert))
async def stop_stop_words_short_photo_insert_text(message: Message, state: FSMContext) -> None:
    logger.debug('stop_stop_words_short_photo_insert_text...')
    kbc = KeyboardCollection()
    word_to_insert = message.text

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


# ========== ОБРАБОТЧИКИ ПРОСМОТРА СТОП-СЛОВ С ПАГИНАЦИЕЙ ==========

async def show_words_page(model_class, words_type: str, page: int, state_name, state: FSMContext, 
                          title: str, callback: CallbackQuery) -> None:
    """Универсальная функция для отображения страницы со словами"""
    kbc = KeyboardCollection()
    words_per_page = 18  # Оптимальное количество слов на страницу
    
    all_words = await model_class.get_all()
    words_list = [word.word for word in all_words]
    words_list.sort()  # Сортируем по алфавиту
    
    total_words = len(words_list)
    total_pages = (total_words + words_per_page - 1) // words_per_page if total_words > 0 else 1
    
    if total_words == 0:
        text = f'<b>{title}</b>\n\n📋 <b>Список пуст</b>\n\nНет добавленных слов'
        await state.set_state(state_name)
        await callback.message.answer(text=text, reply_markup=kbc.admin_edit_chose(), parse_mode='HTML')
        return
    
    # Вычисляем слова для текущей страницы
    start_idx = page * words_per_page
    end_idx = min(start_idx + words_per_page, total_words)
    page_words = words_list[start_idx:end_idx]
    
    # Формируем красивый текст
    text = f'<b>{title}</b>\n\n'
    text += f'📊 Всего слов: <b>{total_words}</b>\n'
    text += f'📄 Страница: <b>{page + 1}</b> из <b>{total_pages}</b>\n\n'
    text += '─' * 25 + '\n\n'
    
    # Выводим слова в три колонки для красоты
    words_text = []
    for i in range(0, len(page_words), 3):
        row = []
        for j in range(3):
            if i + j < len(page_words):
                row.append(f'• {page_words[i + j]}')
        words_text.append('  '.join(row))
    
    text += '\n'.join(words_text)
    
    await state.set_state(state_name)
    await callback.message.answer(
        text=text,
        reply_markup=kbc.admin_view_words_pagination(words_type, page, total_pages),
        parse_mode='HTML'
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_long))
async def view_stop_words_long(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_long...')
    await show_words_page(
        BlockWord,
        'stop_words_long',
        0,
        AdminStates.edit_stop_words_long_look,
        state,
        '📝 Длинные стоп слова',
        callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_short))
async def view_stop_words_short(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_short...')
    await show_words_page(
        BlockWordShort,
        'stop_words_short',
        0,
        AdminStates.edit_stop_words_short_look,
        state,
        '📝 Короткие стоп слова', callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_profanity))
async def view_stop_words_profanity(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_profanity...')
    await show_words_page(
        ProfanityWord,
        'stop_words_profanity',
        0,
        AdminStates.edit_stop_words_profanity_look,
        state,
        '🚫 Матерные стоп слова', callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_white_words))
async def view_white_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_white_words...')
    await show_words_page(
        WhiteWord,
        'white_words',
        0,
        AdminStates.edit_white_words_look,
        state,
        '✅ Белый список', callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_long_message))
async def view_stop_words_long_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_long_message...')
    await show_words_page(
        BlockWordMessage,
        'stop_words_long_message',
        0,
        AdminStates.edit_stop_words_long_message_look,
        state,
        '💬 Длинные стоп слова сообщения',
        callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_short_message))
async def view_stop_words_short_message(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_short_message...')
    await show_words_page(
        BlockWordShortMessage,
        'stop_words_short_message',
        0,
        AdminStates.edit_stop_words_short_message_look,
        state,
        '💬 Короткие стоп слова сообщения',
        callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_photo_stop_words))
async def view_photo_stop_words(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_photo_stop_words...')
    await show_words_page(
        BlockWordPhoto,
        'stop_words_long_photo',
        0,
        AdminStates.edit_photo_stop_words_look,
        state,
        '📷 Длинные стоп слова фото',
        callback
    )


@router.callback_query(F.data == 'look', StateFilter(AdminStates.edit_stop_words_short_photo))
async def view_stop_words_short_photo(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('view_stop_words_short_photo...')
    await show_words_page(
        BlockWordShortPhoto,
        'stop_words_short_photo',
        0,
        AdminStates.edit_stop_words_short_photo_look,
        state,
        '📷 Короткие стоп слова фото',
        callback
    )


# Обработчики пагинации
@router.callback_query(F.data.startswith('view_words_page_'))
async def handle_words_pagination(callback: CallbackQuery, state: FSMContext) -> None:
    logger.debug('handle_words_pagination...')
    # Формат: view_words_page_{words_type}_{page}
    parts = callback.data.split('_')
    words_type = '_'.join(parts[3:-1])  # Все части кроме последней (номер страницы)
    page = int(parts[-1])
    
    # Маппинг типов на модели и состояния
    type_mapping = {
        'stop_words_long': (
            BlockWord, AdminStates.edit_stop_words_long_look, '📝 Длинные стоп слова'
        ),
        'stop_words_short': (
            BlockWordShort, AdminStates.edit_stop_words_short_look, '📝 Короткие стоп слова'
        ),
        'stop_words_profanity': (
            ProfanityWord, AdminStates.edit_stop_words_profanity_look, '🚫 Матерные стоп слова'
        ),
        'white_words': (
            WhiteWord, AdminStates.edit_white_words_look, '✅ Белый список'
        ),
        'stop_words_long_message': (
            BlockWordMessage, AdminStates.edit_stop_words_long_message_look, '💬 Длинные стоп слова сообщения'
        ),
        'stop_words_short_message': (
            BlockWordShortMessage, AdminStates.edit_stop_words_short_message_look, '💬 Короткие стоп слова сообщения'
        ),
        'stop_words_long_photo': (
            BlockWordPhoto, AdminStates.edit_photo_stop_words_look, '📷 Длинные стоп слова фото'
        ),
        'stop_words_short_photo': (
            BlockWordShortPhoto, AdminStates.edit_stop_words_short_photo_look, '📷 Короткие стоп слова фото'
        ),
    }
    
    if words_type in type_mapping:
        model_class, state_name, title = type_mapping[words_type]
        await show_words_page(model_class, words_type, page, state_name, state, title, callback)
