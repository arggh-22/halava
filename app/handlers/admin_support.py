import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.data.database.models import Banned, UserAndSupportQueue
from app.keyboards import KeyboardCollection
from loaders import bot

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data == 'hide_chat_closed')
async def hide_chat_closed(callback: CallbackQuery) -> None:
    """Скрыть сообщение о закрытом чате поддержки"""
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        # Если сообщение уже удалено или недоступно, просто отвечаем
        await callback.answer()
    except Exception as e:
        logger.error(f"Error hiding chat closed message: {e}")
        await callback.answer()


@router.callback_query(lambda c: c.data.startswith('admin_delete_dialog_'))
async def admin_delete_dialog(callback: CallbackQuery, state: FSMContext) -> None:
    """Удаление диалога с пользователем"""
    logger.debug(f'admin_delete_dialog...')
    
    user_tg_id = int(callback.data.split('_')[3])
    kbc = KeyboardCollection()
    
    # Удаляем запись из таблицы поддержки
    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=user_tg_id):
        await user_and_support_queue.delete()
        logger.debug(f"Deleted support queue for user {user_tg_id}")
    
    # Отправляем сообщение пользователю о закрытии чата
    try:
        await bot.send_message(
            chat_id=user_tg_id, 
            text="💬 Чат с поддержкой закрыт. Если у вас возникнут вопросы, вы можете обратиться в поддержку снова.",
            reply_markup=kbc.chat_closed_buttons()
        )
    except TelegramBadRequest as e:
        logger.error(f"Failed to send message to user {user_tg_id}: {e}")
    
    # Обновляем сообщение в чате поддержки
    await callback.message.edit_text(
        f"✅ Диалог с пользователем {user_tg_id} удален. Чат закрыт.",
    )


@router.callback_query(lambda c: c.data.startswith('admin_block_user_'))
async def admin_block_user(callback: CallbackQuery, state: FSMContext) -> None:
    """Админ выбирает заблокировать пользователя"""
    logger.debug(f'admin_block_user...')
    
    user_tg_id = int(callback.data.split('_')[3])
    kbc = KeyboardCollection()
    
    # Показываем кнопки для выбора причины блокировки
    await callback.message.edit_reply_markup(
        reply_markup=kbc.support_admin_block_buttons(user_tg_id)
    )


@router.callback_query(lambda c: c.data.startswith('admin_block_reason_ad_'))
async def admin_block_reason_ad(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокировка за рекламу"""
    logger.debug(f'admin_block_reason_ad...')
    
    user_tg_id = int(callback.data.split('_')[4])
    await block_user_with_reason(callback, user_tg_id, 'реклама', get_ad_violation_text())


@router.callback_query(lambda c: c.data.startswith('admin_block_reason_job_'))
async def admin_block_reason_job(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокировка за вакансию"""
    logger.debug(f'admin_block_reason_job...')
    
    user_tg_id = int(callback.data.split('_')[4])
    await block_user_with_reason(callback, user_tg_id, 'вакансия', get_job_violation_text())


@router.callback_query(lambda c: c.data.startswith('admin_block_reason_rules_'))
async def admin_block_reason_rules(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокировка за нарушение правил"""
    logger.debug(f'admin_block_reason_rules...')
    
    user_tg_id = int(callback.data.split('_')[4])
    await block_user_with_reason(callback, user_tg_id, 'правила', get_rules_violation_text())


@router.callback_query(lambda c: c.data.startswith('admin_block_reason_stopwords_'))
async def admin_block_reason_stopwords(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокировка за стоп слова"""
    logger.debug(f'admin_block_reason_stopwords...')
    
    user_tg_id = int(callback.data.split('_')[4])
    await block_user_with_reason(callback, user_tg_id, 'стоп слова', get_stopwords_violation_text())


async def block_user_with_reason(callback: CallbackQuery, user_tg_id: int, reason: str, violation_text: str) -> None:
    """Блокирует пользователя с указанной причиной"""
    logger.debug(f'block_user_with_reason: {user_tg_id}, {reason}')
    
    kbc = KeyboardCollection()
    
    # Проверяем, есть ли уже блокировка
    banned = await Banned.get_banned(tg_id=user_tg_id)
    
    if banned:
        if banned.ban_counter >= 3:
            # Блокируем навсегда
            await banned.update(forever=True, ban_now=True, ban_reason=reason)
            ban_text = "навсегда"
        else:
            # Блокируем на 24 часа
            ban_end = str(datetime.now() + timedelta(hours=24))
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, ban_reason=reason)
            ban_text = "24 часа"
    else:
        # Создаем новую блокировку
        ban_end = str(datetime.now() + timedelta(hours=24))
        new_banned = Banned(
            id=None, 
            tg_id=user_tg_id,
            ban_counter=1, 
            ban_end=ban_end, 
            ban_now=True,
            forever=False, 
            ban_reason=reason
        )
        await new_banned.save()
        ban_text = "24 часа"
    
    # Отправляем сообщение пользователю
    try:
        await bot.send_message(
            chat_id=user_tg_id, 
            text=f"{violation_text}\n\nСрок блокировки: {ban_text}",
            reply_markup=kbc.support_btn_simple()
        )
    except TelegramBadRequest:
        pass
    
    # Удаляем запись из таблицы поддержки при блокировке
    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=user_tg_id):
        await user_and_support_queue.delete()
        logger.debug(f"Deleted support queue for blocked user {user_tg_id}")
    
    # Обновляем сообщение в чате поддержки
    await callback.message.edit_text(
        f"✅ Пользователь {user_tg_id} заблокирован за {reason}\nСрок: {ban_text}",
        # reply_markup=kbc.support_admin_buttons(user_tg_id)
    )


def get_ad_violation_text() -> str:
    """Текст для нарушения 'реклама'"""
    return """Размещаются только запросы на услуги, реклама запрещена 🚫 

При повторных нарушениях — доступ к сервису может быть закрыт!"""


def get_job_violation_text() -> str:
    """Текст для нарушения 'вакансия'"""
    return """Вакансии запрещены 🚫 

При повторных нарушениях — доступ к сервису может быть закрыт!"""


def get_rules_violation_text() -> str:
    """Текст для нарушения 'правила'"""
    return """Запрос не несет никакой смысловой нагрузки 🚫 

Изучите пожалуйста форму во время заполнения запроса!"""


def get_stopwords_violation_text() -> str:
    """Текст для нарушения 'стоп слова'"""
    return """Вы пытались предложить запрос не правилам сервиса 🚫"""


@router.callback_query(lambda c: c.data.startswith('block_message_log_'))
async def block_user_from_message_log(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокирует пользователя из лога сообщений за попытку обойти платный обмен контактами"""
    logger.debug(f'block_user_from_message_log...')
    
    try:
        # Парсим данные из callback_data: block_message_log_{user_tg_id}_{abs_id}
        parts = callback.data.split('_')
        user_tg_id = int(parts[3])
        abs_id = int(parts[4]) if len(parts) > 4 else None
        
        kbc = KeyboardCollection()
        
        # Проверяем, есть ли уже блокировка
        banned = await Banned.get_banned(tg_id=user_tg_id)
        
        reason = "попытка обойти платный обмен контактами"
        violation_text = (
            "⛔ <b>Аккаунт временно заблокирован на 24 часа.</b>\n\n"
            f"Причина: попытка обойти платный обмен контактами.\n\n"
            "Повторные попытки обхода платного обмена контактами приведут к блокировке аккаунта навсегда."
        )
        if banned:
            if banned.ban_counter >= 3:
                # Блокируем навсегда
                await banned.update(forever=True, ban_now=True, ban_reason=reason)
                ban_text = "навсегда"
                violation_text = (
                    "⛔ <b>Аккаунт заблокирован навсегда за повторные нарушения правил платного обмена контактами. </b>\n\n"
                    "Доступ к боту закрыт."
                )
            else:
                # Блокируем на 24 часа
                ban_end = str(datetime.now() + timedelta(hours=24))
                await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, ban_reason=reason)
                ban_text = "24 часа"
        else:
            # Создаем новую блокировку
            ban_end = str(datetime.now() + timedelta(hours=24))
            new_banned = Banned(
                id=None, 
                tg_id=user_tg_id,
                ban_counter=1, 
                ban_end=ban_end, 
                ban_now=True,
                forever=False, 
                ban_reason=reason
            )
            await new_banned.save()
            ban_text = "24 часа"
        
        # Отправляем сообщение пользователю
        try:
            await bot.send_message(
                chat_id=user_tg_id, 
                text=violation_text,
                parse_mode='HTML',
                reply_markup=kbc.support_btn_simple()
            )
        except TelegramBadRequest:
            pass
        
        # Отправляем уведомление в чат логов о успешной блокировке
        import config
        success_message = (
            f"✅ <b>Пользователь успешно заблокирован</b>\n\n"
            f"ID пользователя: {user_tg_id}\n"
            f"Срок блокировки: {ban_text}\n"
            f"Причина: {reason}"
        )
        
        # Отправляем reply на исходное сообщение в логе
        try:
            await bot.send_message(
                chat_id=config.MESSAGE_LOG,
                text=success_message,
                parse_mode='HTML',
                reply_to_message_id=callback.message.message_id
            )
        except Exception as e:
            logger.error(f"Error sending success message to log chat: {e}")
            # Если не удалось отправить reply, отправляем обычное сообщение
            try:
                await bot.send_message(
                    chat_id=config.MESSAGE_LOG,
                    text=success_message,
                    parse_mode='HTML'
                )
            except Exception as e2:
                logger.error(f"Error sending success message to log chat (fallback): {e2}")
        
        # Удаляем кнопку из исходного сообщения
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        
        await callback.answer("Пользователь заблокирован")
        
    except Exception as e:
        logger.error(f"Error in block_user_from_message_log: {e}")
        await callback.answer("Ошибка при блокировке пользователя", show_alert=True)