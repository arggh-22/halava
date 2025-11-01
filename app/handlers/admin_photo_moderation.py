import logging
from datetime import datetime, timedelta

import os
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, FSInputFile

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
    
    # Определяем тип фото по caption
    caption = callback.message.caption or ""
    is_portfolio = "портфолио" in caption.lower()
    
    # Отправляем сообщение пользователю
    violation_text = "Ваш аккаунт заблокирован за нарушение правил при загрузке фото."
    text = f"{violation_text}\n\nСрок блокировки: {ban_text}"
    
    # Если это фото профиля - удаляем его и отправляем с уведомлением
    if not is_portfolio and worker.profile_photo:
        # Сохраняем путь к фото перед удалением
        photo_path = worker.profile_photo
        logger.info(f"[ADMIN_BLOCK_PHOTO] Блокировка и удаление фото профиля worker_id={worker_id}, photo_path={photo_path}, exists={os.path.exists(photo_path) if photo_path else False}")
        
        # Сначала отправляем уведомление с фото
        try:
            if photo_path and os.path.exists(photo_path):
                logger.info(f"[ADMIN_BLOCK_PHOTO] Отправляю уведомление с фото: {photo_path}")
                await bot.send_photo(
                    chat_id=worker.tg_id,
                    photo=FSInputFile(photo_path),
                    caption=text,
                    reply_markup=kbc.support_after_blocking_info_buttons()
                )
                logger.info(f"[ADMIN_BLOCK_PHOTO] Уведомление с фото успешно отправлено")
            else:
                logger.warning(f"[ADMIN_BLOCK_PHOTO] Фото не найдено, отправляю только текст")
                await bot.send_message(
                    chat_id=worker.tg_id, 
                    text=text,
                    reply_markup=kbc.support_after_blocking_info_buttons()
                )
        except Exception as e:
            logger.error(f"[ADMIN_BLOCK_PHOTO] Ошибка при отправке уведомления с фото: {e}", exc_info=True)
            try:
                await bot.send_message(
                    chat_id=worker.tg_id, 
                    text=text,
                    reply_markup=kbc.support_after_blocking_info_buttons()
                )
            except TelegramBadRequest:
                pass
        
        # ПОСЛЕ отправки удаляем фото из БД и файл
        await worker.update_profile_photo(profile_photo=None)
        logger.info(f"[ADMIN_BLOCK_PHOTO] Фото профиля удалено")
    else:
        # Если это не фото профиля или фото нет, отправляем только текст
        try:
            await bot.send_message(
                chat_id=worker.tg_id, 
                text=text,
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
    
    # Определяем тип фото по caption
    caption = callback.message.caption or ""
    is_portfolio = "портфолио" in caption.lower()
    
    if is_portfolio:
        # Удаляем все фото портфолио (так как не знаем, какое именно было отправлено)
        from app.untils import help_defs
        
        if worker.portfolio_photo:
            # Удаляем все файлы портфолио
            for photo_key, photo_path in worker.portfolio_photo.items():
                if photo_path and isinstance(photo_path, str):
                    help_defs.delete_file(photo_path)
                    logger.info(f"Удалено фото портфолио: {photo_path}")
            
            # Очищаем портфолио в базе данных
            await worker.update_portfolio_photo(portfolio_photo={})
            logger.info(f"Портфолио исполнителя {worker.tg_id} полностью очищено")
        
        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                chat_id=worker.tg_id, 
                text="Фото портфолио нарушает правила платформы 🚫\n\nЗагрузите другие фото!",
                reply_markup=kbc.done_btn()
            )
        except TelegramBadRequest:
            pass
        
        # Обновляем сообщение в чате логов
        await callback.message.edit_caption(
            caption=f"✅ Фото портфолио исполнителя {worker.tg_id} удалено за нарушение правил"
        )
    else:
        # Удаляем фото профиля
        if worker.profile_photo:
            # Сохраняем путь к фото перед удалением
            photo_path = worker.profile_photo
            logger.info(f"[ADMIN_DELETE_PHOTO] Удаление фото профиля worker_id={worker_id}, photo_path={photo_path}, exists={os.path.exists(photo_path) if photo_path else False}")
            
            # Сначала отправляем уведомление с фото
            text = "Фото профиля нарушает правила платформы 🚫\n\nЗагрузите другое!"
            try:
                if photo_path and os.path.exists(photo_path):
                    logger.info(f"[ADMIN_DELETE_PHOTO] Отправляю фото: {photo_path}")
                    await bot.send_photo(
                        chat_id=worker.tg_id,
                        photo=FSInputFile(photo_path),
                        caption=text,
                        reply_markup=kbc.photo_work_keyboard(is_photo=False)
                    )
                    logger.info(f"[ADMIN_DELETE_PHOTO] Фото успешно отправлено")
                else:
                    logger.warning(f"[ADMIN_DELETE_PHOTO] Фото не найдено, отправляю только текст")
                    await bot.send_message(
                        chat_id=worker.tg_id, 
                        text=text,
                        reply_markup=kbc.photo_work_keyboard(is_photo=False)
                    )
            except Exception as e:
                logger.error(f"[ADMIN_DELETE_PHOTO] Ошибка при отправке фото: {e}", exc_info=True)
                try:
                    await bot.send_message(
                        chat_id=worker.tg_id, 
                        text=text,
                        reply_markup=kbc.photo_work_keyboard(is_photo=False)
                    )
                except TelegramBadRequest:
                    pass
            
            # ПОСЛЕ отправки удаляем фото из БД и файл
            await worker.update_profile_photo(profile_photo=None)
        else:
            # Если фото нет, отправляем только текст
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
