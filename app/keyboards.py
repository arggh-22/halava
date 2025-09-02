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

    def verification_worker(self) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Да", callback_data="verification_yes"))
        builder.add(self._inline(button_text="Возможно позже", callback_data="verification_no"))
        builder.adjust(2, 1)
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
                             create_photo, create_name) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Объявления", callback_data="look-abs-in-city"))
        builder.add(self._inline(button_text="Ваши отклики", callback_data="my_responses"))
        builder.add(self._inline(button_text="Тарифы", callback_data="worker_type_subscription"))
        builder.add(self._inline(button_text="Сменить город", callback_data="worker_change_city"))
        if not confirmed:
            builder.add(self._inline(button_text="Верификация", callback_data="verification_yes"))
        if not individual_entrepreneur:
            builder.add(self._inline(button_text="Указать наличие ИП", callback_data="individual_entrepreneur"))
        if choose_works:
            builder.add(self._inline(button_text="Выбрать направления", callback_data="choose_work_types"))
        if create_photo:
            builder.add(self._inline(button_text="Фото профиля", callback_data="create_photo_profile"))
        else:
            builder.add(self._inline(button_text="Фото профиля", callback_data="create_photo_profile"))
        if not create_name:
            builder.add(self._inline(button_text="Указать имя", callback_data="add_worker_name"))
        builder.add(self._inline(button_text="Портфолио", callback_data="my_portfolio"))
        builder.adjust(1)
        return builder.as_markup()

    def get_worker_name(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Указать Имя", callback_data="add_worker_name"))
        builder.adjust(1)
        return builder.as_markup()

    def menu_customer_keyboard(self, btn_bue: bool) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text="Разместить объявление", callback_data="create_new_abs"))
        builder.add(self._inline(button_text="Мои объявления", callback_data="my_abs"))
        if btn_bue:
            builder.add(self._inline(button_text="Оплатить размещение", callback_data="add_orders"))
        builder.add(self._inline(button_text="Сменить город", callback_data="customer_change_city"))
        builder.adjust(1)
        return builder.as_markup()

    def choose_worker_subscription(self, subscriptions_ids: list['int'], subscriptions_names: list['str']) -> InlineKeyboardMarkup:
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

    def choose_worker_subscription_and_buy(self, cur_sub_id: int, cur_sub_name: str,  subscriptions_ids: list['int'], subscriptions_names: list['str']) -> InlineKeyboardMarkup:
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
                                 btn_apply: bool = False, step: int = 1, abs_id: int = None, report_btn: bool = False,
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
        if report_btn:
            if btn_apply:
                builder.add(self._inline(button_text=f'Пожаловаться',
                                         callback_data=f'report-it_{abs_id}'))
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

    def apply_btn(self, abs_id, report_btn: bool = True, send_btn: bool = False, photo_num=None, photo_len=0):
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
        if report_btn:
            builder.add(self._inline(button_text=f'Пожаловаться',
                                     callback_data=f'report-it_{abs_id}'))

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

        builder.add(self._inline(button_text=f'Назад', callback_data=f'customer-response_{worker_id}_{abs_id}'))

        if photo_len > 1:
            builder.adjust(3, 1)
        else:
            builder.adjust(1)

        return builder.as_markup()

    def delite_it_photo(self, worker_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'Заблокировать',
                                 callback_data=f'delite-it-photo_{worker_id}'))
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

    def apply_final_btn(self, idk, role: str, name: str = None, id_now: int = None, skip_btn: bool = True, send_btn: bool = False, send_btn_name: str = f'Написать исполнителю', skip_btn_name: str = 'Отклонить отклик', btn_back: bool = False, abs_id: int = None, buy_btn: bool = False, portfolio: bool = False):
        builder = InlineKeyboardBuilder()
        if name:
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'apply-final-it_{idk}'))
        if send_btn:
            builder.add(self._inline(button_text=send_btn_name,
                                     callback_data=f'answer-obj-{role}_{idk}'))
        if buy_btn:
            builder.add(self._inline(button_text=skip_btn_name,
                                     callback_data=f'buy-response_{idk}'))
        if skip_btn:
            builder.add(self._inline(button_text=skip_btn_name,
                                     callback_data=f'hide-obj-{role}_{idk}'))

        if portfolio:
            builder.add(self._inline(button_text='Портфолио исполнителя',
                                     callback_data=f'worker-portfolio_{idk}_{abs_id}'))

        if btn_back:
            if role == 'worker':
                builder.add(self._inline(button_text='Назад',
                                         callback_data=f'my_responses'))
            else:
                builder.add(self._inline(button_text='Назад',
                                         callback_data=f'customer-responses_{abs_id}_{id_now}'))
        builder.adjust(1)
        return builder.as_markup()

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

    def get_for_staring(self, ids, names):
        builder = InlineKeyboardBuilder()
        for id, name in zip(ids, names):
            builder.add(self._inline(button_text=f'{name}',
                                     callback_data=f'choose-worker-for-staring_{id}'))
        builder.add(self._inline(button_text=f'Не оценивать',
                                 callback_data=f'skip-star-for-worker'))
        builder.adjust(1)
        return builder.as_markup()

    def set_star(self, worker_id):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text=f'⭐️',
                                 callback_data=f'star_1_{worker_id}'))
        builder.add(self._inline(button_text=f'⭐️⭐️',
                                 callback_data=f'star_2_{worker_id}'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️',
                                 callback_data=f'star_3_{worker_id}'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️⭐️',
                                 callback_data=f'star_4_{worker_id}'))
        builder.add(self._inline(button_text=f'⭐️⭐️⭐️⭐️⭐️',
                                 callback_data=f'star_5_{worker_id}'))
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

    def support_btn(self):
        builder = InlineKeyboardBuilder()
        builder.add(self._inline(button_text='Поддержка 24/7', callback_data='support'))
        builder.adjust(1)
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


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
