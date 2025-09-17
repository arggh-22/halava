from datetime import datetime

from aiogram.client.default import DefaultBotProperties

import config
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler


dp = Dispatcher()
aiosession = AiohttpSession()
bot = Bot(token=config.BOT_TOKEN, session=aiosession, default=DefaultBotProperties(protect_content=True, parse_mode='HTML'))   # , parse_mode="HTML", "Markdown"

scheduler = AsyncIOScheduler()


time_start = datetime.now().strftime("%H:%M")


request_header = {
    'Authorization': 'Api-Key {}'.format(config.YANDEX_API_SECRET_KEY),
    'Content-Type': 'application/json'
}


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
