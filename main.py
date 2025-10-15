import os
import asyncio
import logging

print("[MAIN] Importing worker_responses...")
try:
    from app.handlers import worker_responses
    print("[MAIN] worker_responses imported successfully!")
except Exception as e:
    print(f"[MAIN] ERROR importing worker_responses: {e}")
    import traceback
    traceback.print_exc()
    raise

print("[MAIN] Importing anonymous_chat...")
try:
    from app.handlers import anonymous_chat
    print("[MAIN] anonymous_chat imported successfully!")
except Exception as e:
    print(f"[MAIN] ERROR importing anonymous_chat: {e}")
    import traceback
    traceback.print_exc()
    raise

import config
from aiogram.types import BotCommand
from app.handlers import start, worker, customer, admin, admin_send_msg, admin_edit_stop_words, admin_log_work
from app.untils import time_checker
from app.untils.time_checker import restore_weekly_activity
from app.handlers.worker import send_city_subscription_expiry_notifications
from loaders import bot, dp, scheduler
from aiogram.types import CallbackQuery


async def run():
    if not os.path.exists("logs"):
        os.makedirs("logs")

    logging_mode = logging.DEBUG if config.DEBUG_MODE else logging.INFO
    # Настройка файлового хендлера с UTF-8
    file_handler = logging.FileHandler("logs/bot.txt", encoding='utf-8')
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s => %(message)s", datefmt="[%Y-%m-%d %H:%M:%S]"))
    
    # Настройка консольного хендлера с UTF-8
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s => %(message)s", datefmt="[%Y-%m-%d %H:%M:%S]"))
    
    logging.basicConfig(
        level=logging_mode,
        handlers=[file_handler, console_handler],
    )

    logging.info(f"DEBUG_MODE: {config.DEBUG_MODE}")

    # Настройка команд бота
    commands = [
        BotCommand(command="menu", description="меню"),
        BotCommand(command="role", description="выбрать роль"),
        BotCommand(command="info", description="информация"),
        BotCommand(command="support", description="поддержка 24/7"),
    ]
    await bot.set_my_commands(commands)

    logging.info("[MAIN] Including routers...")
    logging.info(f"[MAIN] worker_responses.router: {worker_responses.router}")
    logging.info(f"[MAIN] Number of handlers in worker_responses: {len(worker_responses.router.observers)}")
    dp.include_routers(start.router, worker_responses.router, anonymous_chat.router, worker.router, admin.router, customer.router, admin_send_msg.router, admin_edit_stop_words.router, admin_log_work.router)
    logging.info("[MAIN] Routers included!")

    scheduler.add_job(time_checker.check_time_alive, "interval", minutes=30)
    scheduler.add_job(time_checker.check_time_banned, "interval", hours=12)
    scheduler.add_job(time_checker.check_time_workers, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_customer, "interval", hours=24)
    # Основная проверка объявлений каждые 2 часа для коротких сроков
    scheduler.add_job(time_checker.check_time_advertisement, "interval", hours=2)
    scheduler.add_job(time_checker.check_time_banned_advertisement, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_workers_stars, "interval", hours=48)
    scheduler.add_job(time_checker.cleanup_orphaned_files, "interval", days=7)  # Еженедельная очистка файлов
    scheduler.add_job(send_city_subscription_expiry_notifications, "interval", hours=24)  # Ежедневная проверка истекающих подписок на города
    scheduler.add_job(restore_weekly_activity, "interval", days=7)  # Еженедельное восстановление активности исполнителей
    # scheduler.add_job(time_checker.check_time_workers_top, "interval", days=30)    # minutes=1

    await bot.delete_webhook(drop_pending_updates=False)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())

#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
