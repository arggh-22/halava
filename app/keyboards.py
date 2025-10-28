from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
# from aiogram_widgets.types import AdditionalButtonsType


class KeyboardCollection:
    def __init__(self, lang: str = "ru") -> None:
        self._language = lang

    @staticmethod
    def _inline(button_text: str, callback_data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=button_text, callback_data=callback_data)

    def inline_return_button(self) -> InlineKeyboardButton:
        return self._inline(button_text="button/RETURN", callback_data="return")

    # def return_button_row(self) -> AdditionalButtonsType:
    #     return [[self.inline_return_button()]]

    def registration(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Заказчик", callback_data="registration_customer"))
        builder.add(self._inline(button_text="Исполнитель", callback_data="registration_worker"))
        builder.adjust(1)
        return builder.as_markup()

    def registration_worker(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Принять и продолжить", callback_data="registration_worker"))
        builder.adjust(1)
        return builder.as_markup()

    def registration_customer(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Принять и продолжить", callback_data="registration_customer"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_keyboard(self, admin: bool = False, btn_menu: bool = False) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if admin:
            builder.add(self._inline(button_text="Админ", callback_data="menu_admin"))
        builder.add(self._inline(button_text="Заказчик", callback_data="customer_menu"))
        builder.add(self._inline(button_text="Исполнитель", callback_data="worker_menu"))
        if btn_menu:
            builder.add(self._inline(button_text="Меню", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def menu(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Меню", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_menu(self, abs_id) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="К объявлению", callback_data=f"abs_{abs_id}"))
        builder.add(self._inline(button_text="Меню", callback_data="customer_menu"))
        builder.adjust(1)
        return builder.as_markup()

    def photo_work_keyboard(self, is_photo) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if is_photo:
            builder.add(self._inline(button_text="Удалить", callback_data="photo_delite"))
        builder.add(self._inline(button_text="Назад", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def photo_name_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Назад", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def photo_done(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Закончить", callback_data="photo_end"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_send_msg_admin_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="SMS для исполнителей", callback_data="msg_to_worker"))
        builder.add(self._inline(button_text="SMS для заказчиков", callback_data="msg_to_customer"))
        builder.add(self._inline(button_text="SMS для всех пользователей", callback_data="msg_to_all"))
        builder.add(self._inline(button_text="SMS для исполнителей в городе", callback_data="admin_choose_city_for_workers"))
        builder.add(self._inline(button_text="SMS для заказчиков в городе", callback_data="admin_choose_city_for_customer"))
        builder.add(self._inline(button_text="SMS для всех пользователей в городе", callback_data="admin_choose_city_for_all"))
        builder.add(self._inline(button_text="Реф. ссылку всем исполнителям", callback_data='admin_for_workers_ref'))
        builder.add(self._inline(button_text="Реф. ссылку исполнителям в городе", callback_data="admin_choose_city_for_workers_ref"))
        builder.add(self._inline(button_text="Назад", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_admin_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Отправить сообщение в бота", callback_data="menu_send_msg_admin"))
        builder.add(self._inline(button_text="Редактировать списки стоп слов", callback_data="menu_admin_stop_words"))
        builder.add(self._inline(button_text="Работа с пользователями", callback_data="edit_user"))
        builder.add(self._inline(button_text="Редактировать подписки", callback_data="edit_subscription"))
        builder.add(self._inline(button_text="Изменить цену объявлений", callback_data="edit_order_price"))
        builder.add(self._inline(button_text="🔄 Обновить статистику", callback_data="refresh_admin_stats"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_admin_edit_users(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Найти пользователя", callback_data="get_user"))
        builder.add(self._inline(button_text="Поиск по ID заказчика", callback_data="get_customer"))
        builder.add(self._inline(button_text="Поиск по ID исполнителя", callback_data="get_worker"))
        builder.add(self._inline(button_text="Заблокированные пользователи", callback_data="get_banned"))
        builder.add(self._inline(button_text="Меню", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def admin_edit_subscription(self, sub_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Изменить цену", callback_data=f"edit-price-sub_{sub_id}"))
        builder.add(self._inline(button_text="Изменить количество откликов", callback_data=f"edit-orders-sub_{sub_id}"))
        builder.add(self._inline(button_text="Меню", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_admin_keyboard_stop_words(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Длинные стоп слова", callback_data="stop_words_long"))
        builder.add(self._inline(button_text="Длинные стоп слова сообщения", callback_data="stop_words_long_message"))
        builder.add(self._inline(button_text="Длинные стоп слова персонала", callback_data="stop_words_long_personal"))
        builder.add(self._inline(button_text="Длинные стоп слова фото", callback_data="stop_words_long_photo"))
        builder.add(self._inline(button_text="Короткие стоп слова", callback_data="stop_words_short"))
        builder.add(self._inline(button_text="Короткие стоп слова сообщения", callback_data="stop_words_short_message"))
        builder.add(self._inline(button_text="Короткие стоп слова персонала", callback_data="stop_words_short_personal"))
        builder.add(self._inline(button_text="Короткие стоп слова фото", callback_data="stop_words_short_photo"))
        builder.add(self._inline(button_text="Матерные стоп слова", callback_data="stop_words_profanity"))
        builder.add(self._inline(button_text="Назад", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def admin_edit_chose(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Удалить", callback_data="delite"))
        builder.add(self._inline(button_text="Добавить", callback_data="insert"))
        # builder.add(self._inline(button_text="Посмотреть", callback_data="look"))
        builder.add(self._inline(button_text="Назад", callback_data="menu_admin_stop_words"))
        builder.adjust(1)
        return builder.as_markup()

    def admin_back_btn(self, callback_data) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Назад", callback_data=callback_data))
        builder.adjust(1)
        return builder.as_markup()

    def admin_back_or_send(self, callback_data, customer_id) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Написать", callback_data='send_to_user'))
        if customer_id:
            builder.add(self._inline(button_text="Размещенные объявления", callback_data=f'look-abs-customer_{customer_id}'))
            builder.add(self._inline(button_text="Заблокированные объявления", callback_data=f'look-banned-abs-customer_{customer_id}'))

        builder.add(self._inline(button_text="Разблокировать пользователя", callback_data="unblock_user"))
        builder.add(self._inline(button_text="Заблокировать пользователя", callback_data="block_user"))
        builder.add(self._inline(button_text="Назад", callback_data=callback_data))
        builder.adjust(1)
        return builder.as_markup()

    def admin_get_customer(self, callback_data, customer_id) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(
            self._inline(button_text="Размещенные объявления", callback_data=f'look-abs-customer_{customer_id}'))
        builder.add(self._inline(button_text="Заблокированные объявления", callback_data=f'look-banned-abs-customer_{customer_id}'))
        builder.add(self._inline(button_text="Назад", callback_data=callback_data))
        builder.adjust(1)
        return builder.as_markup()

    def menu_worker_keyboard(self, confirmed, choose_works, individual_entrepreneur,
                             create_photo, create_name, has_status=False) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        # Основные функции
        builder.add(self._inline(button_text="Объявления", callback_data="look-abs-in-city"))
        builder.add(self._inline(button_text="Ваши отклики", callback_data="my_responses"))
        
        # Новые кнопки
        builder.add(self._inline(button_text="Ранг", callback_data="worker_rank"))
        builder.add(self._inline(button_text="Активность", callback_data="worker_activity"))
        
        # Кнопка "Статус" показывается только если НЕТ подтвержденного статуса
        if not has_status:
            builder.add(self._inline(button_text="Статус", callback_data="worker_status"))
        
        # Направления работ
        builder.add(self._inline(button_text="Мои направления", callback_data="choose_work_types"))
        
        # Города
        builder.add(self._inline(button_text="Сменить город", callback_data="worker_change_city_menu"))
        builder.add(self._inline(button_text="Добавить город ₽", callback_data="add_city"))
        
        # Контакты
        builder.add(self._inline(button_text="Купить контакты ₽", callback_data="worker_purchased_contacts"))
        
        # Профиль
        builder.add(self._inline(button_text="Фото профиля", callback_data="create_photo_profile"))
        builder.add(self._inline(button_text="Портфолио", callback_data="my_portfolio"))
        
        builder.adjust(1)
        return builder.as_markup()

    def get_worker_name(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Указать Имя", callback_data="add_worker_name"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_customer_keyboard(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Разместить объявление", callback_data="create_new_abs"))
        builder.add(self._inline(button_text="Мои объявления", callback_data="my_abs"))
        builder.add(self._inline(button_text="Мои контакты", callback_data="customer_contacts"))
        builder.add(self._inline(button_text="Сменить город", callback_data="customer_change_city"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_limit_reached_menu(self) -> InlineKeyboardMarkup:
        """Клавиатура когда достигнут лимит объявлений"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="💳 Оплатить объявление", callback_data="buy_single_ad"))
        builder.add(self._inline(button_text="◀️ Назад в меню", callback_data="customer_menu"))
        builder.adjust(1)
        return builder.as_markup()

    def choose_worker_subscription(self, subscriptions_ids: list, subscriptions_names: list) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for id, name in zip(subscriptions_ids, subscriptions_names):
            builder.add(self._inline(button_text=name.capitalize(), callback_data=f'subscription_{id}'))
        builder.add(self._inline(button_text='Назад', callback_data='menu'))
        builder.adjust(1)
        return builder.as_markup()

    def menu_btn(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="В меню", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_btn_reg(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Принять и продолжить", callback_data="menu"))
        builder.adjust(1)
        return builder.as_markup()

    def choose_worker_subscription_and_buy(self, cur_sub_id: int, cur_sub_name: str,  subscriptions_ids: list, subscriptions_names: list) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Купить {cur_sub_name.capitalize()}', callback_data=f'subscription-buy_{cur_sub_id}'))
        for id, name in zip(subscriptions_ids, subscriptions_names):
            builder.add(self._inline(button_text=name.capitalize(), callback_data=f'subscription_{id}'))
        builder.add(self._inline(button_text='Назад', callback_data='menu'))
        builder.adjust(1)
        return builder.as_markup()

    def choose_obj(self, id_now: int, ids: list, names: list, btn_next: bool, btn_back: bool, step: int = 5, menu_btn: bool = False, btn_next_name: str = 'Дальше ➡️') -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'obj-id_{id}_{id_now}'))
        if btn_back:
            builder.add(self._inline(button_text=f'⬅️ Назад',
                                     callback_data=f'go_{id_now - step}'))
        if btn_next:
            builder.add(self._inline(button_text=btn_next_name,
                                     callback_data=f'go_{id_now + step}'))

        if menu_btn:
            builder.add(self._inline(button_text=f'В меню',
                                     callback_data=f'menu'))
        if btn_back and btn_next and menu_btn:
            builder.adjust(1, 1, 1, 1, 1, 2, 1)
        elif btn_back and btn_next:
            builder.adjust(1, 1, 1, 1, 1, 2)
        elif btn_back or btn_next:
            builder.adjust(1)
        return builder.as_markup()

    def choose_responses(self, id_now: int, ids: list, names: list, abs_list_id:  int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'customer-response_{id}_{id_now}'))

        builder.add(self._inline(button_text=f'Назад',
                                 callback_data=f'go_{abs_list_id}'))

        builder.adjust(1)
        return builder.as_markup()

    def choose_response_worker(self, ids: list, names: list) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'worker-response_{id}'))

        builder.add(self._inline(button_text=f'В меню',
                                 callback_data=f'menu'))

        builder.adjust(1)
        return builder.as_markup()

    def choose_obj_with_out_list(self, id_now: int, btn_next: bool, btn_back: bool, btn_close: bool = False,
                                 btn_apply: bool = False, step: int = 1, abs_id: int = None,
                                 btn_close_name: 'str' = 'Закрыть', btn_responses: bool = False, count_photo: int = 0, idk_photo: int = None) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if count_photo > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-next_{idk_photo - 1}_{id_now}'))
            builder.add(self._inline(button_text=f'{idk_photo + 1}/{count_photo}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-next_{idk_photo + 1}_{id_now}'))
        if btn_close:
            builder.add(self._inline(button_text=btn_close_name,
                                     callback_data=f'close_{id_now}'))
        if btn_apply:
            builder.add(self._inline(button_text=f'Откликнуться',
                                     callback_data=f'apply-it-first_{abs_id}'))
        # Старые кнопки report-it_ удалены - теперь используется единая система report_ad
        if btn_responses:
            builder.add(self._inline(button_text=f'Просмотреть отклики',
                                     callback_data=f'customer-responses_{abs_id}_{id_now}'))
        if btn_next:
            builder.add(self._inline(button_text=f'Дальше',
                                     callback_data=f'go_{id_now + step}'))
        if btn_back:
            builder.add(self._inline(button_text=f'Назад',
                                     callback_data=f'go_{id_now - step}'))

        builder.add(self._inline(button_text=f'В меню',
                                 callback_data=f'menu'))
        if count_photo > 1:

            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def choose_obj_with_out_list_admin(self, id_now: int, btn_next: bool, btn_back: bool, customer_id: int,
                                       btn_block: bool = False, step: int = 1, abs_id: int = None,
                                       btn_delete: bool = False, count_photo: int = 0, idk_photo: int = None) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if count_photo > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-next-adm_{idk_photo - 1}_{id_now}'))
            builder.add(self._inline(button_text=f'{idk_photo + 1}/{count_photo}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-next-adm_{idk_photo + 1}_{id_now}'))
        if btn_block:
            builder.add(self._inline(button_text=f'Заблокировать и удалить',
                                     callback_data=f'block-it-all_{abs_id}'))
        if btn_delete:
            if btn_block:
                builder.add(self._inline(button_text=f'Удалить',
                                         callback_data=f'delete-it_{abs_id}'))
        if btn_next:
            builder.add(self._inline(button_text=f'Дальше',
                                     callback_data=f'go_{id_now + step}'))
        if btn_back:
            builder.add(self._inline(button_text=f'Назад',
                                     callback_data=f'go_{id_now - step}'))
        builder.add(self._inline(button_text=f'В меню',
                                 callback_data=f'back-to-customer_{customer_id}'))
        if count_photo > 1:

            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def back_to_user(self, customer_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Назад',
                                 callback_data=f'get-user_{customer_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def choose_obj_with_out_list_admin_var(self, id_now: int, btn_next: bool, btn_back: bool, customer_id: int,
                                           btn_block: bool = False, step: int = 1, abs_id: int = None,
                                           btn_delete: bool = False, count_photo: int = 0, idk_photo: int = None) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        if count_photo > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-next-adm_{idk_photo - 1}_{id_now}'))
            builder.add(self._inline(button_text=f'{idk_photo + 1}/{count_photo}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-next-adm_{idk_photo + 1}_{id_now}'))

        if btn_block:
            builder.add(self._inline(button_text=f'Разблокировать и разместить',
                                     callback_data=f'unblock-it-all_{abs_id}'))
        if btn_delete:
            if btn_block:
                builder.add(self._inline(button_text=f'Разблокировать пользователя',
                                         callback_data=f'unblock-user-it_{abs_id}'))
        if btn_next:
            builder.add(self._inline(button_text=f'Дальше',
                                     callback_data=f'go_{id_now + step}'))
        if btn_back:
            builder.add(self._inline(button_text=f'Назад',
                                     callback_data=f'go_{id_now - step}'))
        builder.add(self._inline(button_text=f'В меню',
                                 callback_data=f'back-to-customer_{customer_id}'))
        if count_photo > 1:

            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def choose_type(self, ids: list, names: list,  btn_back: bool = False, name_btn_back: str = 'Назад') -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'obj-id_{id}'))
        if btn_back:
            builder.add(self._inline(button_text=name_btn_back,
                                     callback_data=f'back'))
        builder.adjust(1)
        return builder.as_markup()

    def choose_work_types_improved(self, all_work_types: list, selected_ids: list, 
                                 count_work_types: int, page: int = 0, btn_back: bool = False, 
                                 name_btn_back: str = 'Назад', removal_blocked: bool = False) -> InlineKeyboardMarkup:
        """Улучшенная клавиатура для выбора направлений работы с пагинацией"""
        builder = InlineKeyboardBuilder()
        
        # Показываем выбранные направления с возможностью удаления
        if selected_ids:
            builder.add(self._inline(button_text=f"✅ Выбрано: {len(selected_ids)}/{count_work_types}",
                                     callback_data="selected_info"))
            builder.add(self._inline(button_text="📋 Показать выбранные",
                                     callback_data="show_selected"))
            
            # Показываем кнопку "Очистить все" только если удаление не заблокировано
            if not removal_blocked:
                builder.add(self._inline(button_text="🗑 Очистить все",
                                         callback_data="clear_all"))
            
            builder.add(self._inline(button_text="─" * 20,
                                     callback_data="separator"))
        
        # Пагинация - показываем по 8 направлений на странице
        ITEMS_PER_PAGE = 8
        start_index = page * ITEMS_PER_PAGE
        end_index = start_index + ITEMS_PER_PAGE
        page_work_types = all_work_types[start_index:end_index]
        total_pages = (len(all_work_types) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        # Показываем доступные направления на текущей странице
        for work_type in page_work_types:
            if str(work_type.id) in selected_ids:
                # Уже выбранное направление
                if removal_blocked and len(selected_ids) >= count_work_types:
                    # Удаление заблокировано И достигнут лимит - показываем заблокированную кнопку
                    builder.add(self._inline(button_text=f"🔒 {work_type.work_type}",
                                             callback_data=f"removal_blocked_{work_type.id}"))
                elif removal_blocked:
                    # Удаление заблокировано, но есть место для выбора - показываем обычную кнопку
                    builder.add(self._inline(button_text=f"✅ {work_type.work_type}",
                                             callback_data=f"removal_blocked_{work_type.id}"))
                else:
                    # Удаление разрешено
                    builder.add(self._inline(button_text=f"✅ {work_type.work_type}",
                                             callback_data=f"remove_work_type_{work_type.id}"))
            else:
                # Доступное для выбора направление
                if len(selected_ids) < count_work_types:
                    builder.add(self._inline(button_text=f"➕ {work_type.work_type}",
                                             callback_data=f"add_work_type_{work_type.id}"))
                else:
                    # Лимит достигнут
                    builder.add(self._inline(button_text=f"🔒 {work_type.work_type}",
                                             callback_data=f"limit_reached"))
        
        # Кнопки навигации по страницам
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(self._inline("◀️", f"page_{page-1}"))
            nav_buttons.append(self._inline(f"{page+1}/{total_pages}", "current_page"))
            if page < total_pages - 1:
                nav_buttons.append(self._inline("▶️", f"page_{page+1}"))
            
            for btn in nav_buttons:
                builder.add(btn)
            builder.adjust(len(nav_buttons))
        
        if btn_back:
            builder.add(self._inline(button_text=name_btn_back,
                                     callback_data=f'back'))
        
        builder.adjust(1)
        return builder.as_markup()

    def show_selected_work_types(self, selected_work_types: list, count_work_types: int) -> InlineKeyboardMarkup:
        """Клавиатура для показа выбранных направлений"""
        builder = InlineKeyboardBuilder()
        
        builder.add(self._inline(button_text=f"📊 Выбрано: {len(selected_work_types)}/{count_work_types}",
                                 callback_data="selected_info"))
        
        for work_type in selected_work_types:
            builder.add(self._inline(button_text=f"❌ {work_type.work_type}",
                                     callback_data=f"remove_work_type_{work_type.id}"))
        
        builder.add(self._inline(button_text="🔙 Назад к выбору",
                                 callback_data="back_to_selection"))
        
        builder.adjust(1)
        return builder.as_markup()

    def skip_btn(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Пропустить',
                                 callback_data=f'skip_it'))
        # builder.add(self._inline(button_text=f'Завершить загрузку',
        #                          callback_data=f'skip_it_photo'))
        builder.adjust(1)
        return builder.as_markup()

    def done_btn(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Завершить загрузку',
                                 callback_data=f'skip_it_photo'))
        builder.adjust(1)
        return builder.as_markup()

    def skip_btn_admin(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Пропустить',
                                 callback_data=f'skip_it'))
        builder.adjust(1)
        return builder.as_markup()

    def subscription_btn(self, btn_bonus: bool = False):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Выбрать подписку',
                                 callback_data=f'worker_type_subscription'))
        if btn_bonus:
            builder.add(self._inline(button_text=f'Использовать бонус',
                                     callback_data=f'use-bonus'))
        builder.adjust(1)
        return builder.as_markup()

    def apply_btn(self, abs_id, send_btn: bool = False, photo_num=None, photo_len=0):
        builder = InlineKeyboardBuilder()
        if photo_len > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-apply_{photo_num - 1}_{abs_id}'))
            builder.add(self._inline(button_text=f'{photo_num+1}/{photo_len}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-apply_{photo_num + 1}_{abs_id}'))
        builder.add(self._inline(button_text=f'Откликнуться',
                                 callback_data=f'apply-it-first_{abs_id}'))
        if send_btn:
            builder.add(self._inline(button_text=f'Ответить заказчику',
                                     callback_data=f'answer-obj_{abs_id}'))
        # Старые кнопки report-it_ удалены - теперь используется единая система report_ad

        if photo_len > 1:

            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def btn_ok(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Продолжить',
                                 callback_data=f'ok'))
        builder.adjust(1)
        return builder.as_markup()

    def block_abs(self, abs_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Заблокировать и удалить',
                                 callback_data=f'block-it_{abs_id}'))
        builder.add(self._inline(button_text=f'Удалить',
                                 callback_data=f'delite-it-rep_{abs_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def block_abs_log(self, abs_id, photo_num: int = None, photo_len: int = 0):
        builder = InlineKeyboardBuilder()
        if photo_len > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-ban_{photo_num - 1}_{abs_id}'))
            builder.add(self._inline(button_text=f'{photo_num+1}/{photo_len}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-ban_{photo_num + 1}_{abs_id}'))

        builder.add(self._inline(button_text=f'Заблокировать',
                                 callback_data=f'block-it_{abs_id}'))

        if photo_len > 1:
            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def my_portfolio(self, photo_num: int = 0, photo_len: int = 0, new_photo: bool = True):
        builder = InlineKeyboardBuilder()
        if photo_len > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-portfolio_{photo_num - 1}'))
            builder.add(self._inline(button_text=f'{photo_num + 1}/{photo_len}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-portfolio_{photo_num + 1}'))
        
        # Кнопка удаления фото показывается всегда, если есть хотя бы одно фото
        if photo_len > 0:
            builder.add(self._inline(button_text=f'Удалить фото',
                                     callback_data=f'delite-photo-portfolio_{photo_num}'))

        if new_photo:
            builder.add(self._inline(button_text=f'Загрузить фото',
                                     callback_data=f'upload_photo'))

        builder.add(self._inline(button_text=f'Назад', callback_data=f'menu'))

        if photo_len > 1:
            builder.adjust(3, 1, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def worker_portfolio_1(self, worker_id, abs_id, photo_num: int = 0, photo_len: int = 0):
        builder = InlineKeyboardBuilder()
        if photo_len > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-portfolio_{photo_num - 1}_{worker_id}_{abs_id}'))
            builder.add(self._inline(button_text=f'{photo_num + 1}/{photo_len}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-portfolio_{photo_num + 1}_{worker_id}_{abs_id}'))

        builder.add(self._inline(button_text=f'Назад', callback_data=f'view_responses_{abs_id}'))

        if photo_len > 1:
            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def delite_it_photo(self, worker_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Заблокировать и удалить', callback_data=f'admin_block_photo_{worker_id}'))
        builder.add(self._inline(button_text='Удалить', callback_data=f'admin_delete_photo_{worker_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def block_message_log(self, user_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Заблокировать',
                                 callback_data=f'block-it-message_{user_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def look_worker(self, worker_id, abs_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Продолжить',
                                 callback_data=f'look-worker-it_{worker_id}_{abs_id}'))
        builder.adjust(1)
        return builder.as_markup()

    # def apply_final_btn(self, idk, role: str, name: str = None, id_now: int = None, skip_btn: bool = True, send_btn: bool = False, send_btn_name: str = f'Написать исполнителю', skip_btn_name: str = 'Отклонить отклик', btn_back: bool = False, abs_id: int = None, buy_btn: bool = False, portfolio: bool = False, send_contacts_btn: bool = False, request_contacts_btn: bool = False, chat_closed: bool = False):
    #     builder = InlineKeyboardBuilder()
    #     if name:
    #         builder.add(self._inline(button_text=f'{name}',
    #                                  callback_data=f'apply-final-it_{idk}'))
    #     # Если чат закрыт для заказчика, скрываем кнопки отправки сообщений и отклонения
    #     if not chat_closed:
    #         if send_btn:
    #             builder.add(self._inline(button_text=send_btn_name,
    #                                      callback_data=f'answer-obj-{role}_{idk}'))
    #         if buy_btn:
    #             # Показываем кнопки для покупки контакта после обмена контактами
    #             builder.add(self._inline(button_text='💰 Купить контакт',
    #                                      callback_data=f'buy-contact_{idk}_{abs_id}'))
    #         if skip_btn:
    #             # Для работников после обмена контактами показываем "Отклонить отклик"
    #             if role == 'worker' and buy_btn:
    #                 builder.add(self._inline(button_text='❌ Отклонить отклик',
    #                                          callback_data=f'hide-obj-{role}_{idk}'))
    #             else:
    #                 builder.add(self._inline(button_text=skip_btn_name,
    #                                          callback_data=f'hide-obj-{role}_{idk}'))
    #
    #     if portfolio:
    #         builder.add(self._inline(button_text='Портфолио исполнителя',
    #                                  callback_data=f'worker-portfolio_{idk}_{abs_id}'))
    #     if send_contacts_btn:
    #         builder.add(self._inline(button_text='📞 Отправить контакты',
    #                                  callback_data=f'send-contacts_{idk}_{abs_id}'))
    #
    #     if request_contacts_btn:
    #         builder.add(self._inline(button_text='📞 Запросить контакты',
    #                                  callback_data=f'request-contacts_{idk}_{abs_id}'))
    #
    #     if btn_back:
    #         if role == 'worker':
    #             builder.add(self._inline(button_text='Назад',
    #                                      callback_data=f'my_responses'))
    #         else:
    #             builder.add(self._inline(button_text='Назад',
    #                                      callback_data=f'customer-responses_{abs_id}_{id_now}'))
    #     builder.adjust(1)
    #     return builder.as_markup()

    def back_to_responses(self, abs_id, id_now):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Продолжить', callback_data=f'customer-responses_{abs_id}_{id_now}'))
        builder.adjust(1)
        return builder.as_markup()

    def apply_final_btn_var(self, idk, role: str, name: str = None, skip_btn: bool = True, send_btn: bool = False, send_btn_name: str = f'Написать исполнителю', skip_btn_name: str = 'Отклонить отклик'):
        builder = InlineKeyboardBuilder()
        if send_btn:
            builder.add(self._inline(button_text=send_btn_name,
                                     callback_data=f'answer-obj-{role}_{idk}'))
        if name:
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'apply-final-it_{idk}'))
        if skip_btn:
            builder.add(self._inline(button_text=skip_btn_name,
                                     callback_data=f'hide-obj-{role}_{idk}'))
        builder.adjust(1)
        return builder.as_markup()

    def end_time(self, idk: int, workers: bool):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Оставить',
                                 callback_data=f'extend_{idk}'))
        if workers:
            builder.add(self._inline(button_text=f'Оценить и удалить',
                                     callback_data=f'close-by-end-time_{idk}'))
        else:
            builder.add(self._inline(button_text=f'Удалить',
                                     callback_data=f'close-by-end-time_{idk}'))
        builder.adjust(1)
        return builder.as_markup()

    def get_for_staring(self, ids, names, abs_id):
        """Функция для выбора исполнителей для оценки (новая система)"""
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'choose-worker-for-rating_{id}_{abs_id}'))
        builder.add(self._inline(button_text=f'Завершить оценку',
                                 callback_data=f'skip-star-for-worker'))
        builder.adjust(1)
        return builder.as_markup()

# Старая функция set_star удалена - теперь используется set_rating

    def advertisement_expiry_actions(self, abs_id, has_purchased_contacts=False):
        """Клавиатура действий при истечении объявления"""
        builder = InlineKeyboardBuilder()
        
        builder.add(self._inline(button_text="⏰ Продлить", callback_data=f"extend_advertisement_{abs_id}"))
        builder.add(self._inline(button_text="❌ Не продлять", callback_data=f"dont_extend_advertisement_{abs_id}"))
        
        if has_purchased_contacts:
            builder.add(self._inline(button_text="✅ Закрыть и оценить", callback_data=f"close_and_rate_{abs_id}"))
        else:
            builder.add(self._inline(button_text="✅ Закрыть", callback_data=f"close_advertisement_{abs_id}"))
        
        builder.adjust(1)
        return builder.as_markup()

    def confirm_close_advertisement(self, abs_id):
        """Клавиатура подтверждения закрытия объявления вручную"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Подтвердить закрытие", callback_data=f"confirm-close_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отменить", callback_data=f"cancel-close_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def confirm_close_advertisement_expiry(self, abs_id):
        """Клавиатура подтверждения закрытия объявления при истечении"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Подтвердить закрытие", callback_data=f"confirm_close_expiry_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отменить", callback_data=f"cancel_close_expiry_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def confirm_close_and_rate_advertisement_expiry(self, abs_id):
        """Клавиатура подтверждения закрытия и оценки объявления при истечении"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Подтвердить закрытие и оценку", callback_data=f"confirm_close_and_rate_expiry_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отменить", callback_data=f"cancel_close_and_rate_expiry_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def extend_advertisement_periods(self, abs_id):
        """Клавиатура выбора периода продления"""
        builder = InlineKeyboardBuilder()
        
        builder.add(self._inline(button_text="24 часа", callback_data=f"extend_24h_{abs_id}"))
        builder.add(self._inline(button_text="2 дня", callback_data=f"extend_2d_{abs_id}"))
        builder.add(self._inline(button_text="3 дня", callback_data=f"extend_3d_{abs_id}"))
        
        builder.adjust(1)
        return builder.as_markup()

    def set_rating(self, worker_id, abs_id):
        """Новая система оценки исполнителей"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'⭐️',
                                 callback_data=f'rate-worker_{worker_id}_{abs_id}_1'))
        builder.add(self._inline(button_text=f'⭐️⭐️',
                                 callback_data=f'rate-worker_{worker_id}_{abs_id}_2'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️',
                                 callback_data=f'rate-worker_{worker_id}_{abs_id}_3'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️⭐️',
                                 callback_data=f'rate-worker_{worker_id}_{abs_id}_4'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️⭐️⭐️',
                                 callback_data=f'rate-worker_{worker_id}_{abs_id}_5'))
        builder.add(self._inline(button_text=f'Пропустить',
                                 callback_data=f'skip-star-for-worker'))
        builder.adjust(1)
        return builder.as_markup()

    def apply_user_agreement(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Принять и продолжить',
                                 callback_data=f'apply_and_continue'))
        builder.adjust(1)
        return builder.as_markup()

    def unban(self, user_id, is_abs=True, photo_num: int = None, photo_len: int = 0):
        builder = InlineKeyboardBuilder()
        if photo_len > 1:
            builder.add(self._inline(button_text=f'<',
                                     callback_data=f'go-to-unban_{photo_num - 1}_{user_id}'))
            builder.add(self._inline(button_text=f'{photo_num+1}/{photo_len}',
                                     callback_data=f'do_nothing'))
            builder.add(self._inline(button_text=f'>',
                                     callback_data=f'go-to-unban_{photo_num + 1}_{user_id}'))
        if is_abs:
            builder.add(self._inline(button_text=f'Разблокировать и разместить',
                                     callback_data=f'unban_{user_id}'))
        builder.add(self._inline(button_text=f'Разблокировать и удалить',
                                 callback_data=f'unban-user_{user_id}'))
        builder.add(self._inline(button_text=f'Подтвердить блокировку',
                                 callback_data=f'close'))

        if photo_len > 1:
            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def back_btn(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Назад',
                                 callback_data=f'back'))
        builder.adjust(1)
        return builder.as_markup()

    def btn_back_to_responses(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Продолжить", callback_data="my_responses"))
        return builder.as_markup()

    def command_menu_keyboard(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Роль', callback_data=f'role'))
        builder.add(self._inline(button_text='Информация', callback_data='info'))
        builder.add(self._inline(button_text='Поддержка 24/7', callback_data='support'))
        builder.adjust(1)
        return builder.as_markup()

    def support_btn_simple(self):
        """Простая кнопка поддержки без истории запросов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Поддержка 24/7', callback_data='support'))
        builder.adjust(1)
        return builder.as_markup()

    def support_btn(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Поддержка 24/7', callback_data='support'))
        builder.add(self._inline(button_text='История запросов', callback_data='support_history'))
        builder.adjust(1)
        return builder.as_markup()

    def support_blocking_question_buttons(self):
        """Кнопки для вопроса о блокировке"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Да', callback_data='support_blocking_yes'))
        builder.add(self._inline(button_text='Нет', callback_data='support_blocking_no'))
        builder.adjust(2)
        return builder.as_markup()

    def support_after_blocking_info_buttons(self):
        """Кнопки после показа информации о блокировке"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Задать вопрос', callback_data='support_ask_question'))
        builder.add(self._inline(button_text='В меню', callback_data='menu'))
        builder.adjust(1)
        return builder.as_markup()

    def support_admin_buttons(self, user_tg_id: int):
        """Кнопки для админов в чате поддержки"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Заблокировать или удалить', callback_data=f'admin_block_user_{user_tg_id}'))
        builder.add(self._inline(button_text='Ответить', callback_data=f'answer-it_{user_tg_id}'))
        builder.add(self._inline(button_text='Удалить', callback_data=f'admin_delete_dialog_{user_tg_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def support_admin_block_buttons(self, user_tg_id: int):
        """Кнопки для выбора причины блокировки"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Реклама', callback_data=f'admin_block_reason_ad_{user_tg_id}'))
        builder.add(self._inline(button_text='Вакансия', callback_data=f'admin_block_reason_job_{user_tg_id}'))
        builder.add(self._inline(button_text='Правила', callback_data=f'admin_block_reason_rules_{user_tg_id}'))
        builder.add(self._inline(button_text='Стоп слова', callback_data=f'admin_block_reason_stopwords_{user_tg_id}'))
        builder.adjust(2)
        return builder.as_markup()

    def admin_answer_user(self, tg_id: int):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Ответить', callback_data=f'answer-it_{tg_id}'))
        builder.adjust(1)
        return builder.as_markup()

    def support_unban(self, tg_id: int):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Разблокировать', callback_data=f'unban-user-support_{tg_id}'))
        builder.add(self._inline(button_text=f'Скрыть', callback_data=f'hide-unban-button'))
        builder.adjust(1)
        return builder.as_markup()

    def worker_apply_work_type(self, btn_good: str = f'Принять', btn_bad: str = f'Отмена'):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=btn_good, callback_data=f'good'))
        builder.add(self._inline(button_text=btn_bad, callback_data=f'bad'))
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def worker_buy_subscription() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"Оплатить", pay=True)
        builder.button(text='Назад', callback_data='worker_type_subscription')
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def customer_buy_response(abs_id, id_now) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"Оплатить", pay=True)
        builder.button(text='Назад', callback_data=f'customer-responses_{abs_id}_{id_now}')
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def customer_buy_order() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"Оплатить", pay=True)
        builder.button(text='Назад', callback_data='menu')
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def contact_keyboard() -> ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        builder.row(
            KeyboardButton(
                text="Отправить номер телефона",
                request_contact=True,
            )
        )
        return builder.as_markup(resize_keyboard=True)

    # Новые кнопки для системы покупки контактов

    def buy_contact_btn(self, customer_id: int, abs_id: int):
        """Кнопки для покупки контакта исполнителем"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="💰 Купить контакт", 
                                 callback_data=f"buy-contact_{customer_id}_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отклонить отклик", 
                                 callback_data=f"reject-response_{customer_id}_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    # def customer_response_to_contact_request(self, worker_id: int, abs_id: int):
    #     """Кнопки для ответа заказчика на запрос контактов от исполнителя"""
    #     builder = InlineKeyboardBuilder()
    #     builder.add(self._inline(button_text="✅ Отправить контакты",
    #                              callback_data=f"send-contacts-to-worker_{worker_id}_{abs_id}"))
    #     builder.add(self._inline(button_text="❌ Отклонить запрос",
    #                              callback_data=f"reject-contact-request_{worker_id}_{abs_id}"))
    #     builder.adjust(1)
    #     return builder.as_markup()

    def contact_purchase_tariffs(self):
        """Тарифы на покупку контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="190 ₽ — 1 контакт", callback_data="contact-tariff_1_190"))
        builder.add(self._inline(button_text="290 ₽ — 2 контакта", callback_data="contact-tariff_2_290"))
        builder.add(self._inline(button_text="690 ₽ — 5 контактов", callback_data="contact-tariff_5_690"))
        builder.add(self._inline(button_text="1190 ₽ — 10 контактов", callback_data="contact-tariff_10_1190"))
        builder.add(self._inline(button_text="1990 ₽ — Безлимит 1 месяц", callback_data="contact-tariff_unlimited_1_1990"))
        builder.add(self._inline(button_text="4490 ₽ — Безлимит 3 месяца", callback_data="contact-tariff_unlimited_3_4490"))
        builder.add(self._inline(button_text="6990 ₽ — Безлимит 6 месяцев", callback_data="contact-tariff_unlimited_6_6990"))
        builder.add(self._inline(button_text="10990 ₽ — Безлимит 12 месяцев", callback_data="contact-tariff_unlimited_12_10990"))
        builder.add(self._inline(button_text="Назад", callback_data="worker_purchased_contacts"))
        builder.adjust(1)
        return builder.as_markup()

    # def send_contacts_request(self, worker_id: int, abs_id: int):
    #     """Кнопки для запроса контактов от заказчика"""
    #     builder = InlineKeyboardBuilder()
    #     builder.add(self._inline(button_text="📞 Отправить контакты",
    #                              callback_data=f"send-contacts_{worker_id}_{abs_id}"))
    #     builder.add(self._inline(button_text="⬅️ Назад к откликам",
    #                              callback_data=f"back-to-responses_{abs_id}"))
    #     builder.adjust(1)
    #     return builder.as_markup()

    def contact_request_response(self, worker_id: int, abs_id: int):
        """Кнопки ответа на запрос контактов для исполнителя"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="💰 Купить контакт", 
                                 callback_data=f"buy-contact_{worker_id}_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отклонить отклик", 
                                 callback_data=f"reject-response_{worker_id}_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def contact_sent_confirmation(self):
        """Кнопка подтверждения отправки контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Контакты отправлены", 
                                 callback_data="contacts-sent-confirmed"))
        builder.adjust(1)
        return builder.as_markup()

    def contact_purchased_confirmation(self):
        """Кнопка подтверждения покупки контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Контакт получен", 
                                 callback_data="contact-purchased-confirmed"))
        builder.adjust(1)
        return builder.as_markup()

    def chat_closed_buttons(self, abs_id: int):
        """Кнопки для закрытого чата"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="⬅️ Назад к откликам", 
                                 callback_data=f"back-to-responses_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()


    def new_contact_tariffs(self):
        """Новые клавиатуры для тарифов контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="190 ₽ — 1 контакт", callback_data="contact-tariff_1_190"))
        builder.add(self._inline(button_text="290 ₽ — 2 контакта", callback_data="contact-tariff_2_290"))
        builder.add(self._inline(button_text="690 ₽ — 5 контактов", callback_data="contact-tariff_5_690"))
        builder.add(self._inline(button_text="1190 ₽ — 10 контактов", callback_data="contact-tariff_10_1190"))
        builder.add(self._inline(button_text="1990 ₽ — Безлимит 1 месяц", callback_data="contact-tariff_unlimited_1_1990"))
        builder.add(self._inline(button_text="4490 ₽ — Безлимит 3 месяца", callback_data="contact-tariff_unlimited_3_4490"))
        builder.add(self._inline(button_text="6990 ₽ — Безлимит 6 месяцев", callback_data="contact-tariff_unlimited_6_6990"))
        builder.add(self._inline(button_text="10990 ₽ — Безлимит 12 месяцев", callback_data="contact-tariff_unlimited_12_10990"))
        builder.adjust(1)
        return builder.as_markup()

    def send_contacts_customer_btn(self, worker_id: int, abs_id: int):
        """Кнопка отправки контактов для заказчика"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="📞 Отправить контакты", 
                                 callback_data=f"send-contacts-new_{worker_id}_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def buy_contact_worker_btn(self, customer_id: int, abs_id: int):
        """Кнопки для исполнителя после получения уведомления о контактах"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="💰 Купить контакт", 
                                 callback_data=f"buy-contact-new_{customer_id}_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отклонить отклик", 
                                 callback_data=f"reject-contact-new_{customer_id}_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def rating_buttons(self, worker_id: int, abs_id: int):
        """Кнопки для оценки исполнителя заказчиком"""
        builder = InlineKeyboardBuilder()
        for i in range(1, 6):
            builder.add(self._inline(button_text="⭐" * i, 
                                     callback_data=f"rate-worker_{worker_id}_{abs_id}_{i}"))
        builder.adjust(5)
        return builder.as_markup()

    def chat_closed_buttons(self, role: str, abs_id: int):
        """Кнопки для закрытого чата"""
        builder = InlineKeyboardBuilder()
        if role == 'customer':
            builder.add(self._inline(button_text="⬅️ Назад к откликам", 
                                     callback_data=f"back-to-responses_{abs_id}"))
        else:
            builder.add(self._inline(button_text="⬅️ Назад к объявлениям", 
                                     callback_data="worker_menu"))
        builder.adjust(1)
        return builder.as_markup()

    # ========== КЛАВИАТУРЫ ДЛЯ КОНТАКТОВ ЗАКАЗЧИКА ==========
    
    def customer_contacts_menu(self) -> InlineKeyboardMarkup:
        """Меню выбора типа контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="📱 Профиль Telegram", callback_data="contact_telegram_only"))
        builder.add(self._inline(button_text="📞 Добавить номер", callback_data="contact_add_phone"))
        builder.add(self._inline(button_text="📱📞 Профиль Telegram и номер", callback_data="contact_both"))
        builder.add(self._inline(button_text="◀️ Назад", callback_data="customer_menu"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_contacts_edit_menu(self, contact_type: str) -> InlineKeyboardMarkup:
        """Меню редактирования контактов в зависимости от текущего типа"""
        builder = InlineKeyboardBuilder()
        
        if contact_type == "telegram_only":
            builder.add(self._inline(button_text="📞 Добавить номер (убрав telegram)",
                                     callback_data="edit_phone_only"))
            builder.add(self._inline(button_text="📞 Добавить номер (оставив telegram)",
                                     callback_data="edit_both"))
        elif contact_type == "phone_only":
            builder.add(self._inline(button_text="📱 Изменить номер (добавив telegram)",
                                     callback_data="edit_both"))
            builder.add(self._inline(button_text="📱 Удалить номер (оставив telegram)",
                                     callback_data="edit_telegram_only"))
        elif contact_type == "both":
            builder.add(self._inline(button_text="📞 Изменить номер (оставив telegram)",
                                     callback_data="edit_both"))
            builder.add(self._inline(button_text="📞 Изменить номер (убрав telegram)",
                                     callback_data="edit_phone_only"))
            builder.add(self._inline(button_text="📱 Удалить номер (оставив telegram)",
                                     callback_data="edit_telegram_only"))
        
        builder.add(self._inline(button_text="◀️ Назад", callback_data="customer_contacts"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_contacts_display_menu(self) -> InlineKeyboardMarkup:
        """Меню отображения текущих контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✏️ Редактировать", callback_data="edit_contacts"))
        builder.add(self._inline(button_text="◀️ Назад", callback_data="customer_menu"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_contacts_back_menu(self) -> InlineKeyboardMarkup:
        """Кнопка назад в меню контактов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="◀️ Назад", callback_data="customer_contacts"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_contacts_confirm_delete(self) -> InlineKeyboardMarkup:
        """Подтверждение удаления номера"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Да", callback_data="confirm_delete_phone"))
        builder.add(self._inline(button_text="❌ Отмена", callback_data="customer_contacts"))
        builder.adjust(1)
        return builder.as_markup()

    # ========== НОВЫЕ КНОПКИ ДЛЯ ОТКЛИКОВ И АНОНИМНОГО ЧАТА ==========
    
    def advertisement_response_buttons(self, abs_id: int, btn_next: bool = False, btn_back: bool = False, abs_list_id: int = 0, count_photo: int = 0, photo_num: int = 0) -> InlineKeyboardMarkup:
        """Кнопки под объявлением для исполнителя с навигацией"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки листания фотографий (если их больше одной)
        if count_photo > 1:
            builder.add(self._inline(button_text="◀️", 
                                     callback_data=f"go-to-photo-worker_{photo_num - 1}_{abs_id}_{abs_list_id}"))
            builder.add(self._inline(button_text=f"{photo_num + 1}/{count_photo}", 
                                     callback_data="do_nothing"))
            builder.add(self._inline(button_text="▶️", 
                                     callback_data=f"go-to-photo-worker_{photo_num + 1}_{abs_id}_{abs_list_id}"))
        
        builder.add(self._inline(button_text="✅ Откликнуться", 
                                 callback_data=f"respond_to_ad_{abs_id}"))
        builder.add(self._inline(button_text="⚠️ Пожаловаться", 
                                 callback_data=f"report_ad_{abs_id}"))
        builder.add(self._inline(button_text="❌ Скрыть объявление", 
                                 callback_data=f"decline_ad_{abs_id}"))
        
        # Кнопки навигации
        if btn_next:
            builder.add(self._inline(button_text="▶️ Дальше", 
                                     callback_data=f"go_worker_{abs_list_id + 1}"))
        if btn_back:
            builder.add(self._inline(button_text="◀️ Назад", 
                                     callback_data=f"go_worker_{abs_list_id - 1}"))
        
        builder.add(self._inline(button_text="🏠 В меню", 
                                 callback_data="back_to_ads"))
        
        if count_photo > 1:
            builder.adjust(3, 1)  # 3 кнопки в первом ряду (навигация по фото), остальные по 1
        else:
            builder.adjust(1)
        return builder.as_markup()

    def chat_rules_confirmation(self) -> InlineKeyboardMarkup:
        """Кнопка подтверждения правил чата"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="✅ Ознакомлен, Продолжить", 
                                 callback_data="confirm_chat_rules"))
        builder.add(self._inline(button_text="❌ Отмена", 
                                 callback_data="cancel_response"))
        builder.adjust(1)
        return builder.as_markup()

    def response_type_choice(self, abs_id: int) -> InlineKeyboardMarkup:
        """Выбор типа отклика"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="📝 Написать сообщение", 
                                 callback_data=f"response_with_text_{abs_id}"))
        builder.add(self._inline(button_text="✅ Откликнуться без сообщения", 
                                 callback_data=f"response_without_text_{abs_id}"))
        builder.add(self._inline(button_text="❌ Отмена", 
                                 callback_data="cancel_response"))
        builder.adjust(1)
        return builder.as_markup()

    def anonymous_chat_worker_buttons(self, abs_id: int, has_contacts: bool = False, 
                                     contacts_requested: bool = False, contacts_sent: bool = False,
                                     count_photo: int = 0, photo_num: int = 0) -> InlineKeyboardMarkup:
        """Кнопки для анонимного чата исполнителя"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки навигации по фотографиям объявления
        if count_photo > 1:
            builder.add(self._inline(button_text="◀️", 
                                     callback_data=f"go-to-photo-worker-response_{photo_num - 1}_{abs_id}"))
            builder.add(self._inline(button_text=f"{photo_num + 1}/{count_photo}", 
                                     callback_data="do_nothing"))
            builder.add(self._inline(button_text="▶️", 
                                     callback_data=f"go-to-photo-worker-response_{photo_num + 1}_{abs_id}"))
        
        if has_contacts:
            # Контакты уже куплены - показываем только назад
            builder.add(self._inline(button_text="◀️ К моим откликам", 
                                     callback_data="my_responses"))
        elif contacts_requested:
            # Контакты переданы, но не куплены - нужно покупать
            builder.add(self._inline(button_text="💳 Купить контакты", 
                                     callback_data=f"buy_contacts_for_abs_{abs_id}"))
            builder.add(self._inline(button_text="❌ Отказаться", 
                                     callback_data=f"reject_contact_offer_{abs_id}"))
        elif contacts_sent:
            # Контакты запрошены, ждем подтверждения
            builder.add(self._inline(button_text="⏳ Ожидание подтверждения", 
                                     callback_data="noop"))
            builder.add(self._inline(button_text="❌ Отменить запрос", 
                                     callback_data=f"cancel_contact_request_{abs_id}"))
        else:
            # Можно запросить контакты
            builder.add(self._inline(button_text="📞 Запросить контакт", 
                                     callback_data=f"request_contact_{abs_id}"))
        
        # Кнопка для ответа в чате (только если контакты не куплены)
        if not has_contacts:
            builder.add(self._inline(button_text="💬 Ответить в чате", 
                                     callback_data=f"reply_in_worker_chat_{abs_id}"))
        
        # Кнопка отмены отклика (только если контакты НЕ куплены)
        if not has_contacts:
            builder.add(self._inline(button_text="❌ Отменить отклик", 
                                     callback_data=f"cancel_worker_response_{abs_id}"))
        
        # Кнопка "К моим откликам" только если контакты НЕ куплены
        if not has_contacts:
            builder.add(self._inline(button_text="◀️ К моим откликам", 
                                     callback_data="my_responses"))
        builder.adjust(1)
        return builder.as_markup()

    def anonymous_chat_customer_buttons(self, worker_id: int, abs_id: int, 
                                       contact_requested: bool = False,
                                       contact_sent: bool = False,
                                       contacts_purchased: bool = False,
                                       has_portfolio: bool = False) -> InlineKeyboardMarkup:
        """Кнопки для анонимного чата заказчика - показывает кнопки в зависимости от состояния контактов"""
        builder = InlineKeyboardBuilder()
        
        # Показываем кнопки в зависимости от состояния контактов
        
        # Кнопка подтверждения/статуса контактов
        if contact_sent:
            # Контакты уже отправлены - убираем кнопку подтверждения
            builder.add(self._inline(button_text="✅ Контакты отправлены", 
                                     callback_data="noop"))
        elif contact_requested:
            # Исполнитель запросил контакты
            builder.add(self._inline(button_text="✅ Подтвердить передачу", 
                                     callback_data=f"confirm_contact_share_{worker_id}_{abs_id}"))
        else:
            # Можно предложить контакты
            builder.add(self._inline(button_text="📞 Отправить контакты",
                                     callback_data=f"offer_contact_share_{worker_id}_{abs_id}"))
        
        # Кнопка просмотра портфолио (показываем только если есть портфолио)
        if has_portfolio:
            builder.add(self._inline(button_text="📸 Портфолио исполнителя", 
                                     callback_data=f"worker-portfolio_{worker_id}_{abs_id}"))
        
        # Кнопка отклонения передачи контактов (показываем только если есть что отклонять)
        if contact_requested or contact_sent:
            builder.add(self._inline(button_text="❌ Отклонить передачу контактов", 
                                     callback_data=f"decline_contact_share_{worker_id}_{abs_id}"))
        
        # Кнопка ответа в чате (всегда показываем)
        builder.add(self._inline(button_text="💬 Ответить в чате", 
                                 callback_data=f"reply_in_chat_{worker_id}_{abs_id}"))
        
        # Кнопка отклонения отклика (всегда показываем)
        builder.add(self._inline(button_text="❌ Отклонить отклик", 
                                 callback_data=f"reject_customer_response_{worker_id}_{abs_id}"))
        
        # Кнопка возврата к откликам (всегда показываем)
        builder.add(self._inline(button_text="◀️ К откликам", 
                                 callback_data=f"view_responses_{abs_id}"))
        builder.adjust(1)
        return builder.as_markup()

    def buy_tokens_tariffs(self) -> InlineKeyboardMarkup:
        """Тарифы покупки жетонов"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="1 жетон — 190₽", 
                                 callback_data="buy_tokens_1_190"))
        builder.add(self._inline(button_text="2 жетона — 290₽ (-24%)", 
                                 callback_data="buy_tokens_2_290"))
        builder.add(self._inline(button_text="5 жетонов — 690₽ (-27%)", 
                                 callback_data="buy_tokens_5_690"))
        builder.add(self._inline(button_text="10 жетонов — 1190₽ (-37%)", 
                                 callback_data="buy_tokens_10_1190"))
        builder.add(self._inline(button_text="🔥 Безлимит 1 месяц — 1990₽", 
                                 callback_data="buy_tokens_unlimited_1_1990"))
        builder.add(self._inline(button_text="🔥 Безлимит 3 месяца — 4490₽", 
                                 callback_data="buy_tokens_unlimited_3_4490"))
        builder.add(self._inline(button_text="🔥 Безлимит 6 месяцев — 6990₽", 
                                 callback_data="buy_tokens_unlimited_6_6990"))
        builder.add(self._inline(button_text="🔥 Безлимит 12 месяцев — 10990₽", 
                                 callback_data="buy_tokens_unlimited_12_10990"))
        builder.add(self._inline(button_text="◀️ Отмена", 
                                 callback_data="cancel_token_purchase"))
        builder.adjust(1)
        return builder.as_markup()

    def my_responses_list_buttons(self, responses_data: list) -> InlineKeyboardMarkup:
        """Кнопки списка откликов исполнителя"""
        builder = InlineKeyboardBuilder()
        
        for response in responses_data:
            abs_id = response['abs_id']
            # Используем индикатор из данных или fallback на старую логику
            status_emoji = response.get('status_indicator', "💬" if response['active'] else "✅")
            text = f"{status_emoji} Объявление #{abs_id}"
            builder.add(self._inline(button_text=text, 
                                     callback_data=f"view_my_response_{abs_id}"))
        
        builder.add(self._inline(button_text="◀️ В меню", 
                                 callback_data="worker_menu"))
        builder.adjust(1)
        return builder.as_markup()

    def customer_responses_list_buttons(self, responses_data: list, abs_id: int) -> InlineKeyboardMarkup:
        """Кнопки списка откликов на объявление заказчика"""
        builder = InlineKeyboardBuilder()
        
        for response in responses_data:
            worker_public_id = response['worker_public_id']
            # Используем индикатор из данных или fallback на старую логику
            status_emoji = response.get('status_indicator', "💬" if response['active'] else "✅")
            text = f"{status_emoji} {worker_public_id}"
            builder.add(self._inline(button_text=text, 
                                     callback_data=f"view_response_{response['worker_id']}_{abs_id}"))
        
        builder.add(self._inline(button_text="◀️ К объявлениям", 
                                 callback_data="my_abs"))
        builder.adjust(1)
        return builder.as_markup()

    def contact_purchase_confirmation(self, worker_id: int, abs_id: int, price: int) -> InlineKeyboardMarkup:
        """Подтверждение покупки контакта"""
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f"✅ Купить за {price}₽", 
                                 callback_data=f"confirm_purchase_{worker_id}_{abs_id}_{price}"))
        builder.add(self._inline(button_text="💰 Выбрать другой тариф", 
                                 callback_data="buy_tokens_menu"))
        builder.add(self._inline(button_text="❌ Отмена", 
                                 callback_data="my_responses"))
        builder.adjust(1)
        return builder.as_markup()


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
