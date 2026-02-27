from typing import Optional, Dict, Any
from app.data.database.models import Worker, Customer, Abs, ContactExchange, WorkersAndAbs, WorkerAndBadResponse, WorkerAndReport, City
from app.untils import help_defs

class NotificationContext:
    def __init__(self):
        self.worker: Optional[Worker] = None        # The Worker involved (Sender or Receiver)
        self.customer: Optional[Customer] = None    # The Customer involved (Sender or Receiver)
        self.advertisement: Optional[Abs] = None
        self.contact_exchange: Optional[ContactExchange] = None
        self.response: Optional[WorkersAndAbs] = None
        
        self.error_message: Optional[str] = None
        self.status: str = "ok"         
        self.has_history: bool = False
        self.ad_text: str = ""
        self.city_name: str = "Не указан"
        
        # Role flags for the viewer (user_id)
        self.is_viewer_worker: bool = False
        self.is_viewer_customer: bool = False

class NotificationValidator:
    """
    Centralized validation logic for notifications.
    Eliminates code duplication in api/routes/notifications.py
    """
    
    @staticmethod
    async def validate(user_id: int, payload: Dict[str, Any], notification_type: str) -> NotificationContext:
        ctx = NotificationContext()
        abs_id = payload.get('abs_id')
        
        # 1. Base Validation: Abs ID (Except for types that might not need it, but mostly all do)
        if not abs_id:
             # Basic payload error
             return ctx

        # 2. Get Advertisement
        ctx.advertisement = await Abs.get_one(id=abs_id)
        if not ctx.advertisement:
             ctx.error_message = "❌ <b>Объявление закрыто или удалено.</b>"
             return ctx
        
        # Load Ad Text & City (Common needs)
        if ctx.advertisement.text_path:
            ctx.ad_text = help_defs.read_text_file(ctx.advertisement.text_path)
        city = await City.get_city(id=ctx.advertisement.city_id)
        if city:
            ctx.city_name = city.city

        # 3. Determine Viewer Role & Load Context
        # We try to load both profiles for the viewer if they exist
        viewer_worker = await Worker.get_worker(tg_id=user_id)
        viewer_customer = await Customer.get_customer(tg_id=user_id)
        
        # Initialize flags (will be set based on context)
        ctx.is_viewer_worker = False
        ctx.is_viewer_customer = False

        # 4. Type-Specific Loading & Validation logic with strictly defined roles

        # --- A. Explicit WORKER Context types ---
        # Viewer is Worker. Target is Customer (Ad Owner).
        if notification_type in ['contact_offer', 'contact_reject', 'response_rejected', 'contact_bought', 'order']:
             ctx.is_viewer_worker = True
             ctx.worker = viewer_worker
             
             if not ctx.worker:
                  ctx.error_message = "❌ <b>Ошибка авторизации.</b>\nВы не найдены как исполнитель."
                  return ctx
             
             ctx.customer = await Customer.get_customer(id=ctx.advertisement.customer_id)
             if not ctx.customer:
                  ctx.error_message = "❌ <b>Заказчик не найден.</b>"
                  return ctx

             # Special Checks for 'order'
             if notification_type == 'order':
                 # Check if hidden
                 is_hidden = await WorkerAndBadResponse.get_by_worker_and_abs(ctx.worker.id, abs_id)
                 if is_hidden:
                     ctx.error_message = f"❌ <b>Объявление #{abs_id} скрыто.</b>\n\nВы скрыли это объявление из ленты."
                     return ctx
                 # Check if reported
                 is_reported = await WorkerAndReport.get_by_worker_and_abs(ctx.worker.id, abs_id)
                 if is_reported:
                     ctx.error_message = f"⚠️ <b>Жалоба на объявление #{abs_id}.</b>\n\nВы уже отправили жалобу на это объявление."
                     return ctx
                 
                 # Check if closed (relevance)
                 if not ctx.advertisement.relevance:
                      # Allow viewing if already responded
                      has_responded = await WorkersAndAbs.get_by_worker_and_abs(ctx.worker.id, abs_id)
                      if not has_responded:
                           ctx.error_message = f"🔒 <b>Объявление #{abs_id} закрыто заказчиком.</b>\nВы не успели откликнуться."
                           return ctx


        # --- B. Explicit CUSTOMER Context types ---
        # Viewer is Customer (Ad Owner). Target is Worker (Sender).
        elif notification_type in ['contact_request', 'new_response', 'worker', 'customer']:
             ctx.is_viewer_customer = True
             ctx.customer = viewer_customer
             
             # Verify viewer is owner (or authorized customer)
             if not ctx.customer:
                  ctx.error_message = "❌ <b>Ошибка авторизации.</b>\nВы не найдены как заказчик."
                  return ctx
             
             if ctx.advertisement.customer_id != ctx.customer.id:
                  # Strict check: only Ad Owner sees these notifications
                  ctx.error_message = "❌ <b>Доступ запрещен.</b>\nВы не являетесь владельцем этого объявления."
                  return ctx
             
             worker_id = payload.get('worker_id')
             if not worker_id:
                  ctx.error_message = "❌ <b>Некорректные данные (worker_id).</b>"
                  return ctx
             
             ctx.worker = await Worker.get_worker(id=worker_id)
             if not ctx.worker:
                  ctx.error_message = "❌ <b>Исполнитель не найден.</b>"
                  return ctx

             # Special Check for 'new_response'
             if notification_type == 'new_response':
                  ctx.response = await WorkersAndAbs.get_by_worker_and_abs(worker_id=worker_id, abs_id=abs_id)
                  if not ctx.response:
                       ctx.error_message = "❌ <b>Отклик больше не актуален.</b>\nИсполнитель удалил его или вы его отклонили."
                       return ctx


        # --- C. Ambiguous Context types (Chat / Message) ---
        # Viewer determines role based on Ad Ownership.
        elif notification_type in ['anonymous_chat', 'message', 'chat_message']:
             
             # Priority 1: Check if Viewer is the Ad Owner -> CUSTOMER Role
             if viewer_customer and ctx.advertisement.customer_id == viewer_customer.id:
                   ctx.is_viewer_customer = True
                   ctx.customer = viewer_customer
                   
                   worker_id = payload.get('worker_id')
                   if worker_id:
                        ctx.worker = await Worker.get_worker(id=worker_id)
                   else:
                        ctx.error_message = "❌ <b>Некорректные данные (worker_id).</b>"
                        return ctx

             # Priority 2: Check if Viewer is a Worker -> WORKER Role
             elif viewer_worker:
                  ctx.is_viewer_worker = True
                  ctx.worker = viewer_worker
                  ctx.customer = await Customer.get_customer(id=ctx.advertisement.customer_id)
             
             else:
                  # Fallback/Error
                  ctx.error_message = "❌ <b>Доступ запрещен.</b>\nОшибка определения роли."
                  return ctx

        # 5. Load Common Data (ContactExchange, Response) if Worker & Customer are identified
        if ctx.worker and ctx.customer:
             ctx.contact_exchange = await ContactExchange.get_by_worker_and_abs(ctx.worker.id, abs_id)
             
             # If we haven't loaded response yet
             if not ctx.response:
                 ctx.response = await WorkersAndAbs.get_by_worker_and_abs(ctx.worker.id, abs_id)
             
             # Calc History flag
             if ctx.response:
                w_msgs = [m for m in (ctx.response.worker_messages or []) if m and m.strip() and m != "Исполнитель не отправил сообщение"]
                c_msgs = [m for m in (ctx.response.customer_messages or []) if m and m.strip()]
                ctx.has_history = len(w_msgs) > 0 or len(c_msgs) > 0

        # 6. Final Specific Validations (Contact Offer)
        if notification_type == 'contact_offer':
             if not ctx.contact_exchange:
                  ctx.error_message = "❌ <b>Предложение не найдено или было отменено.</b>"
                  return ctx
             
             if ctx.contact_exchange.contacts_purchased:
                  contacts_info = ctx.customer.get_contact_info()
                  ctx.error_message = f"✅ <b>Вы уже купили контакты по этому объявлению!</b>\n\n{contacts_info}"
                  return ctx
             
             if not ctx.contact_exchange.contacts_sent:
                  ctx.error_message = "❌ <b>Предложение больше не актуально.</b>\nЗаказчик мог отменить его или вы уже отказались."
                  return ctx

        return ctx
