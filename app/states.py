from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    ask_support_photo = State()
    registration_enter_city = State()
    registration_end = State()
    menu = State()
    ask_support = State()
    user_info = State()


class WorkStates(StatesGroup):
    portfolio_upload_photo = State()
    create_name_profile = State()
    create_photo_profile = State()
    individual_entrepreneur = State()
    confirm_ooo_status = State()
    confirm_sz_status = State()
    registration_enter_city = State()
    registration_enter_name = State()
    # Верификация убрана согласно ТЗ
    worker_menu = State()
    worker_check_subscription = State()
    worker_buy_subscription = State()
    worker_choose_work_types = State()
    worker_check_abs = State()
    worker_change_city = State()
    worker_choose_city = State()
    worker_change_main_city = State()
    create_portfolio = State()
    # Новые стейты для откликов и анонимного чата
    worker_response_init = State()  # Инициализация отклика
    worker_response_chat_rules = State()  # Подтверждение правил чата
    worker_response_write_text = State()  # Ввод текста отклика
    worker_anonymous_chat = State()  # Анонимный чат
    worker_my_responses = State()  # Просмотр откликов
    worker_request_contact = State()  # Запрос контакта
    worker_buy_tokens = State()  # Покупка жетонов
    worker_choose_subscription_cities = State()  # Выбор городов для подписки


class CustomerStates(StatesGroup):
    customer_extend_abc = State()
    customer_buy_subscription = State()
    registration_enter_city = State()
    # Верификация убрана согласно ТЗ
    customer_menu = State()
    worker_check_abs = State()
    customer_create_abs = State()
    customer_create_abs_work_type = State()
    customer_create_abs_task = State()
    customer_create_abs_volume = State()
    customer_create_abs_details = State()
    customer_create_abs_address = State()
    customer_create_abs_price = State()
    customer_create_abs_choose_time = State()
    customer_create_abs_add_photo = State()
    customer_check_abs = State()
    starring_worker = State()
    customer_change_city = State()
    customer_create_abs_personal_add_photo =State()
    # Новые стейты для откликов и анонимного чата
    customer_view_responses = State()  # Просмотр откликов
    customer_anonymous_chat = State()  # Анонимный чат
    customer_confirm_contact_share = State()  # Подтверждение передачи контакта
    # Стейты для работы с контактами
    customer_contacts = State()  # Меню контактов
    customer_contacts_phone_input = State()  # Ввод номера телефона


class AdminStates(StatesGroup):
    add_comment_to_lock_profile_photo = State()
    edit_stop_words_short_photo_delite = State()
    edit_stop_words_short_photo_insert = State()
    edit_stop_words_short_photo = State()
    edit_photo_stop_words_delite = State()
    edit_photo_stop_words_insert = State()
    edit_photo_stop_words = State()
    edit_stop_words_short_personal_delite = State()
    edit_stop_words_short_personal_insert = State()
    edit_stop_words_short_personal = State()
    edit_personal_stop_words_delite = State()
    edit_personal_stop_words_insert = State()
    edit_personal_stop_words = State()
    edit_stop_words_short_message_insert = State()
    edit_stop_words_long_message_insert = State()
    edit_stop_words_short_message_delite = State()
    edit_stop_words_short_message = State()
    edit_stop_words_long_message = State()
    edit_stop_words_long_message_delite = State()
    send_to_user = State()
    get_user = State()
    get_worker = State()
    get_customer = State()
    menu = State()
    msg_to_worker_text = State()
    msg_to_worker_photo = State()
    msg_to_customer_text = State()
    msg_to_customer_photo = State()
    msg_to_all_text = State()
    msg_to_all_photo = State()
    msg_to_worker_choose_city = State()
    msg_to_worker_text_city = State()
    msg_to_worker_photo_city = State()
    msg_to_customer_text_city = State()
    msg_to_customer_choose_city = State()
    msg_to_customer_photo_city = State()
    msg_to_all_choose_city = State()
    msg_to_all_text_city = State()
    msg_to_all_photo_city = State()
    add_account = State()
    account_role = State()
    enter_rework = State()
    edit_stop_words = State()
    edit_stop_words_long = State()
    edit_stop_words_short = State()
    edit_white_words = State()
    edit_stop_words_profanity = State()
    edit_stop_words_long_insert = State()
    edit_stop_words_short_insert = State()
    edit_white_words_insert = State()
    edit_stop_words_profanity_insert = State()
    edit_stop_words_long_delite = State()
    edit_stop_words_short_delite = State()
    edit_white_words_delite = State()
    edit_stop_words_profanity_delite = State()
    edit_stop_words_long_look = State()
    edit_stop_words_short_look = State()
    edit_white_words_look = State()
    edit_stop_words_profanity_look = State()
    admin_answer_user = State()
    unblock_user = State()
    block_user = State()
    check_subscription = State()
    edit_subscription = State()
    msg_to_worker_choose_city_ref = State()
    msg_to_worker_text_city_ref = State()
    msg_to_worker_photo_city_ref = State()
    msg_to_worker_ref = State()
    msg_to_worker_text_ref = State()
    msg_to_worker_photo_ref = State()
    edit_subscription_price = State()
    edit_subscription_order = State()
    edit_order_price = State()  # Состояние для изменения цены объявлений
    check_abs = State()
    check_banned_abs = State()
    add_comment_to_lock = State()
    add_comment_to_lock_abs_chat = State()


class BannedStates(StatesGroup):
    banned = State()


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
