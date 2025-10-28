import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.data.database.models import Banned, Worker, UserAndSupportQueue
from app.keyboards import KeyboardCollection
from app.states import WorkStates
from loaders import bot
import config

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data.startswith('admin_block_photo_'))
async def admin_block_photo_violation(callback: CallbackQuery, state: FSMContext) -> None:
    """Блокировка за нарушение правил при загрузке фото"""
    logger.debug(f'admin_block_photo_violation...')
    
    worker_id = int(callback.data.split('_')[3])
    kbc = KeyboardCollection()
    
    # Получаем исполнителя
    worker = await Worker.get_worker(id=worker_id)
    if not worker:
        await callback.message.edit_text("❌ Исполнитель не найден")
        return
    
    # Проверяем, есть ли уже блокировка
    banned = await Banned.get_banned(tg_id=worker.tg_id)
    
    if banned:
        if banned.ban_counter >= 3:
            # Блокируем навсегда
            await banned.update(forever=True, ban_now=True, ban_reason="Нарушение правил при загрузке фото")
            ban_text = "навсегда"
        else:
            # Блокируем на 24 часа
            ban_end = str(datetime.now() + timedelta(hours=24))
            await banned.update(ban_counter=banned.ban_counter + 1, ban_now=True, ban_end=ban_end, ban_reason="Нарушение правил при загрузке фото")
            ban_text = "24 часа"
    else:
        # Создаем новую блокировку
        ban_end = str(datetime.now() + timedelta(hours=24))
        new_banned = Banned(
            id=None, 
            tg_id=worker.tg_id,
            ban_counter=1, 
            ban_end=ban_end, 
            ban_now=True,
            forever=False, 
            ban_reason="Нарушение правил при загрузке фото"
        )
        await new_banned.save()
        ban_text = "24 часа"
    
    # Удаляем запись из таблицы поддержки при блокировке
    if user_and_support_queue := await UserAndSupportQueue.get_one_by_tg_id(user_tg_id=worker.tg_id):
        await user_and_support_queue.delete()
        logger.debug(f"Deleted support queue for blocked worker {worker.tg_id}")
    
    # Отправляем сообщение пользователю
    violation_text = "Ваш аккаунт заблокирован за нарушение правил при загрузке фото."
    
    try:
        await bot.send_message(
            chat_id=worker.tg_id, 
            text=f"{violation_text}\n\nСрок блокировки: {ban_text}",
            reply_markup=kbc.support_after_blocking_info_buttons()
        )
    except TelegramBadRequest:
        pass
    
    # Обновляем сообщение в чате логов
    await callback.message.edit_caption(
        caption=f"✅ Исполнитель {worker.tg_id} заблокирован за нарушение правил при загрузке фото\nСрок: {ban_text}"
    )


@router.callback_query(lambda c: c.data.startswith('admin_delete_photo_'))
async def admin_delete_photo_violation(callback: CallbackQuery, state: FSMContext) -> None:
    """Удаление фото с нарушением правил"""
    logger.debug(f'admin_delete_photo_violation...')
    
    worker_id = int(callback.data.split('_')[3])
    kbc = KeyboardCollection()
    
    # Получаем исполнителя
    worker = await Worker.get_worker(id=worker_id)
    if not worker:
        await callback.message.edit_text("❌ Исполнитель не найден")
        return
    
    # Удаляем фото профиля
    if worker.profile_photo:
        await worker.update_profile_photo(profile_photo=None)
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            chat_id=worker.tg_id, 
            text="Фото профиля нарушает правила платформы 🚫\n\nЗагрузите другое!",
            reply_markup=kbc.photo_work_keyboard(is_photo=False)
        )
    except TelegramBadRequest:
        pass
    
    # Обновляем сообщение в чате логов
    await callback.message.edit_caption(
        caption=f"✅ Фото профиля исполнителя {worker.tg_id} удалено за нарушение правил"
    )
