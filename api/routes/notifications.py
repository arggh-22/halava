from fastapi import APIRouter, HTTPException, Depends
from api.models import Notification
from tortoise.expressions import Q
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from api.auth import get_current_user
from loaders import bot
from app.data.database.models import Worker, Customer, Abs, WorkersAndAbs, ContactExchange, City, WorkerAndBadResponse, WorkerAndReport
from app.keyboards import KeyboardCollection
from app.handlers.worker_responses import send_with_worker_photo, get_worker_status_string, get_worker_rating_display, get_rating_word
from app.handlers.anonymous_chat import get_response_status_indicator, format_chat_history_for_display, parse_contacts_message
from app.untils import help_defs
from app.untils.notification_context import NotificationValidator
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class NotificationOut(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    body: str
    payload: Optional[dict]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

@router.get("", response_model=List[NotificationOut])
async def get_notifications(
    limit: Optional[int] = None, 
    offset: int = 0, 
    filter_type: str = 'all', # 'all', 'chats', 'system'
    user_id: int = Depends(get_current_user)
):
    """
    Get notifications for the authenticated user with filtering.
    filter_type: 'all' (default), 'chats' (messages), 'system' (others)
    Default limit: 100 for 'all', 50 for others.
    """
    # Set dynamic default limit
    if limit is None:
        limit = 100 if filter_type == 'all' else 50
        
    query = Notification.filter(user_id=user_id)
    chat_types = ['anonymous_chat', 'chat_message', 'message']
    contact_types = ['new_response', 'response_rejected', 'contact_request', 
                     'contact_reject', 'worker_contact_reject', 'contact_offer', 'contact_bought', 'info'] # info used for contact_share
    
    if filter_type == 'chats':
        query = query.filter(type__in=chat_types)
    elif filter_type == 'contacts':
        query = query.filter(type__in=contact_types)
    elif filter_type == 'system':
        # Filter OUT chat types AND contact types (pure system messages)
        query = query.exclude(type__in=chat_types + contact_types)

    # ... (rest of function) ...


        
    # Read-Time Grouping Implementation
    # We fetch more items than requested to account for duplicate chat threads
    fetch_limit = limit * 3 
    notifications = await query.order_by('-created_at').offset(offset).limit(fetch_limit).all()
    
    results = []
    seen_threads = set()
    
    for n in notifications:
        # Check if this is a chat notification that needs grouping
        if n.type in chat_types and n.payload:
            # Extract thread identifiers robustly (handle int/str diffs)
            abs_id = str(n.payload.get('abs_id', ''))
            worker_id = str(n.payload.get('worker_id', ''))
            
            # If identifiers are present, use them for grouping
            if abs_id and worker_id:
                thread_key = (abs_id, worker_id)
                
                if thread_key in seen_threads:
                    continue # Skip older duplicate
                
                seen_threads.add(thread_key)
        
        # Add to results (either unique chat msg or non-chat msg)
        results.append(n)
        
        if len(results) >= limit:
            break
            
    return results

@router.post("/read/{notification_id}")
async def mark_as_read(
    notification_id: int,
    user_id: int = Depends(get_current_user)
):
    """Mark a notification as read"""
    notification = await Notification.get_or_none(id=notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    if notification.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this notification")
    
    notification.is_read = True
    await notification.save()
    return {"status": "ok"}

@router.post("/read_all")
async def mark_all_as_read(user_id: int = Depends(get_current_user)):
    """Mark all notifications as read for the authenticated user"""
    await Notification.filter(user_id=user_id, is_read=False).update(is_read=True)
    return {"status": "ok"}

@router.post("/{notification_id}/open")
async def open_notification(
    notification_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Открытие уведомления:
    1. Получение из БД и проверка прав
    2. Пометка как прочитанное
    3. Валидация через NotificationValidator
    4. Маршрутизация
    """
    try:
        notification = await Notification.get_or_none(id=notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        if notification.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Mark as read
        notification.is_read = True
        await notification.save()

        payload = notification.payload or {}
        notif_type = notification.type
        kbc = KeyboardCollection()

        # 1. Centralized Validation
        ctx = await NotificationValidator.validate(user_id, payload, notif_type)
        
        if ctx.error_message:
             await bot.send_message(
                chat_id=user_id,
                text=ctx.error_message,
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
             return {"status": "ok"}


        # 2. Routing based on Type & Role
        
        # --- A. Contact Request (Customer View) ---
        if notif_type == 'contact_request':
            # Logic: Customer sees request from Worker
            
            # Reconstruct notification text
            worker = ctx.worker
            worker_name = worker.profile_name or "Исполнитель"
            
            notification_text = f"📞 <b>Запрос контакта от исполнителя</b>\n\n"
            notification_text += f"📋 Объявление: #{ctx.advertisement.id}\n\n"
            notification_text += f"👤 <b>ID:</b> {worker.id} {worker_name}\n"

            if worker.count_ratings > 0:
                rating_display, count_ratings = get_worker_rating_display(worker.stars, worker.count_ratings)
                notification_text += f"⭐ <b>Рейтинг:</b> {rating_display} ({count_ratings} {get_rating_word(count_ratings)})\n"
            else:
                 rating_display, count_ratings = get_worker_rating_display(worker.stars, worker.count_ratings)
                 notification_text += f"⭐ <b>Рейтинг:</b> {rating_display} ({count_ratings} {get_rating_word(count_ratings)})\n"

            status_string = await get_worker_status_string(worker.id)
            notification_text += f"📋 <b>Статус:</b> {status_string}\n"
            notification_text += f"📦 <b>Выполнено заказов:</b> {worker.order_count}\n"
            notification_text += f"📅 <b>Зарегистрирован:</b> {worker.registration_data}\n\n"
            notification_text += "❓ <b>Подтвердить передачу контакта?</b>"
            
            # Buttons
            contacts_purchased = ctx.contact_exchange.contacts_purchased if ctx.contact_exchange else False
            contacts_sent = ctx.contact_exchange.contacts_sent if ctx.contact_exchange else False
            
            reply_markup = kbc.anonymous_chat_customer_buttons(
                worker_id=worker.id,
                abs_id=ctx.advertisement.id,
                contact_requested=True,
                contact_sent=contacts_sent,
                contacts_purchased=contacts_purchased
            )
            
            # Send with/without photo
            if worker.profile_photo:
                try:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=FSInputFile(worker.profile_photo),
                        caption=notification_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception:
                    await bot.send_message(chat_id=user_id, text=notification_text, reply_markup=reply_markup, parse_mode='HTML')
            else:
                await bot.send_message(chat_id=user_id, text=notification_text, reply_markup=reply_markup, parse_mode='HTML')
            return {"status": "ok"}


        # --- B. Contact Offer (Worker View) ---
        elif notif_type == 'contact_offer':
             # Validated logic
             MAX_AD_TEXT_LENGTH = 2000
             ad_text = ctx.ad_text
             if len(ad_text) > MAX_AD_TEXT_LENGTH:
                ad_text = ad_text[:MAX_AD_TEXT_LENGTH] + "\n... (текст обрезан, полный текст в объявлении)"

             notification_text = (
                f"🔔 <b>Заказчик предлагает передать контакты!</b>\n\n"
                f"📋 Объявление: #{ctx.advertisement.id}\n"
                f"👤 Заказчик: {f'ID#{ctx.customer.id}'}\n\n"
                f"{ad_text}"
             )

             sent_message = await bot.send_message(
                chat_id=user_id,
                text=notification_text,
                reply_markup=kbc.accept_contact_offer_keyboard(ctx.has_history, ctx.worker.id, ctx.advertisement.id),
                parse_mode='HTML'
            )
             
             
             if ctx.contact_exchange:
                await ctx.contact_exchange.update(message_id=sent_message.message_id)

             return {"status": "ok"}


        # --- C. Contact Bought / Sold ---
        elif notif_type == 'contact_bought':
             # Use existing helper
             history_text = await format_chat_history_for_display("worker", ctx.advertisement.id, ctx.worker, ctx.customer)
             await help_defs.send_full_contacts_message_to_worker(
                worker=ctx.worker, 
                customer=ctx.customer, 
                abs_id=ctx.advertisement.id, 
                ad_text=ctx.ad_text, 
                event=None,
                history_text=history_text
            )
             return {"status": "ok"}


        # --- D. Rejections ---
        elif notif_type == 'contact_reject':
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ <b>Передача контактов отклонена заказчиком.</b>\n📋 Объявление #{ctx.advertisement.id}",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
            return {"status": "ok"}

        elif notif_type == 'response_rejected':
            await bot.send_message(
                chat_id=user_id,
                text=f"📨 <b>Заказчик отклонил ваш отклик на объявление #{ctx.advertisement.id}</b>\n\n"
                     f"Это не влияет на вашу активность.",
                reply_markup=kbc.worker_menu(),
                parse_mode='HTML'
            )
            return {"status": "ok"}


        # --- E. Customer Viewing Response (New Response, etc.) ---
        elif ctx.is_viewer_customer and notif_type in ['new_response', 'worker', 'customer', 'anonymous_chat']:
             # Show Response Summary
             worker = ctx.worker
             if not worker: # Should be caught by validator but safe check
                 return {"status": "ok"}
                 
             text = f"📋 <b>Уведомление: Отклик на объявление #{ctx.advertisement.id}</b>\n\n"
             status_string = await get_worker_status_string(worker.id)
             rating_display, count_ratings = get_worker_rating_display(worker.stars, worker.count_ratings)
             
             text += f"👤 <b>Исполнитель:</b> {worker.profile_name or worker.id}\n"
             text += f"⭐ <b>Рейтинг:</b> {rating_display} ({count_ratings})\n"
             text += f"📋 <b>Статус:</b> {status_string}\n\n"
             text += f"<i>Нажмите кнопку ниже, чтобы открыть чат или просмотреть детали в боте.</i>"
             
             builder = InlineKeyboardBuilder()
             builder.add(kbc._inline(button_text="👀 Посмотреть в боте", callback_data=f"view_response_{worker.id}_{ctx.advertisement.id}"))
             
             await bot.send_message(chat_id=user_id, text=text, reply_markup=builder.as_markup(), parse_mode='HTML')
             return {"status": "ok"}


        # --- F. Worker Viewing Ad/Chat (Order, Anonymous Chat, etc.) ---
        elif ctx.is_viewer_worker and (notif_type in ['new_response', 'worker', 'customer', 'anonymous_chat', 'message'] or notif_type == 'order'):
             
             # Determine Content: Chat vs Ad Response
             if notif_type == 'order' and not ctx.response:
                 # Worker viewing Ad to Respond
                 text = f"📋 <b>Объявление #{ctx.advertisement.id}</b>\n\n"
                 text += f"г. {ctx.city_name}\n"
                 text += f"<b>Текст:</b> {ctx.ad_text}\n"
                 
                 reply_markup = kbc.advertisement_response_buttons(abs_id=ctx.advertisement.id)
                 await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
                 return {"status": "ok"}
             
             else:
                 # Worker viewing Chat/Response
                 history_text = await format_chat_history_for_display("worker", ctx.advertisement.id, ctx.worker, ctx.customer)
                 
                 # Check contact status
                 contact_exchange = ctx.contact_exchange 
                 contacts_purchased = contact_exchange.contacts_purchased if contact_exchange else False
                 
                 text = f"📋 <b>Объявление #{ctx.advertisement.id}</b>\n\n"
                 text += f"г. {ctx.city_name}\n"
                 
                 if contacts_purchased:
                      # Show Full details + Contacts
                      text += f"{ctx.ad_text}\n\n"
                      if history_text:
                            text += f"📝 <b>История переписки:</b>\n{history_text}\n\n"
                      
                      contacts_info = await parse_contacts_message(ctx.customer)
                      text += f"✅ <b>Контакты получены:</b>\n\n{contacts_info}\n\n"
                      text += "🔒 Чат закрыт — теперь вы можете продолжить общение напрямую."
                 else:
                      # Show Truncated details
                      text += f"<b>Задача:</b> {ctx.ad_text[:200]}...\n\n"
                      
                      if history_text:
                          text += f"📝 <b>История переписки:</b>\n{history_text}\n"
                      
                      text += "\nВы можете написать сообщение заказчику или запросить контакт."

                 # Buttons
                 contacts_purchased = ctx.contact_exchange.contacts_purchased if ctx.contact_exchange else False
                 contacts_sent = ctx.contact_exchange.contacts_sent if ctx.contact_exchange else False
                 contact_requested = ctx.contact_exchange is not None
                 worker_initiated = ctx.contact_exchange and not ctx.contact_exchange.contacts_sent

                 reply_markup = kbc.anonymous_chat_worker_buttons(
                     abs_id=ctx.advertisement.id,
                     has_contacts=contacts_purchased,
                     contacts_requested=contacts_sent,
                     contacts_sent=contact_requested and not contacts_sent,
                     worker_initiated=worker_initiated
                 )

                 await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
                 return {"status": "ok"}


        # --- G. Info / Fallback ---
        elif notif_type == 'info':
             title = payload.get('title', 'Уведомление')
             body = payload.get('body', '')
             await bot.send_message(
                chat_id=user_id,
                text=f"🔔 <b>{title}</b>\n\n{body}",
                reply_markup=kbc.menu(),
                parse_mode='HTML'
            )
             return {"status": "ok"}

        else:
             # Generic fallback
             title = payload.get('title', 'Уведомление')
             body = payload.get('body', '')
             if title or body:
                 await bot.send_message(
                    chat_id=user_id,
                    text=f"🔔 <b>{title}</b>\n\n{body}",
                    reply_markup=kbc.menu(),
                    parse_mode='HTML'
                )
             else:
                 # Just open generic menu
                 await bot.send_message(chat_id=user_id, text="🔔 Уведомление", reply_markup=kbc.menu())

        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error opening notification: {e}")
        return {"status": "error", "detail": str(e)}

