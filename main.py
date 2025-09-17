import os
import asyncio
import logging
import config
from app.handlers import start, worker, customer, admin, admin_send_msg, admin_edit_stop_words, admin_log_work
from app.untils import time_checker
from loaders import bot, dp, scheduler


async def run():
    if not os.path.exists("logs"):
        os.makedirs("logs")

    logging_mode = logging.DEBUG if config.DEBUG_MODE else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s => %(message)s",
        level=logging_mode,
        datefmt="[%Y-%m-%d %H:%M:%S]",
        handlers=[
            logging.FileHandler("logs/bot.txt"),
            logging.StreamHandler(),
        ],
    )

    logging.info(f"DEBUG_MODE: {config.DEBUG_MODE}")

    dp.include_routers(start.router, worker.router, admin.router, customer.router, admin_send_msg.router, admin_edit_stop_words.router, admin_log_work.router)

    scheduler.add_job(time_checker.check_time_alive, "interval", minutes=30)
    scheduler.add_job(time_checker.check_time_banned, "interval", hours=12)
    scheduler.add_job(time_checker.check_time_workers, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_customer, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_advertisement, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_banned_advertisement, "interval", hours=24)
    scheduler.add_job(time_checker.check_time_workers_stars, "interval", hours=48)
    scheduler.add_job(time_checker.cleanup_orphaned_files, "interval", days=7)  # Еженедельная очистка файлов
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
