from dotenv import load_dotenv
import os

# Загружаем переменные из .env файла
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '7470851575:AAH7uCMP-FGWHAcj2LmSzNeQBQCSJHf6xk8')

# Режим отладки
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() in ('true', '1', 'yes')

# Платежи
PAYMENTS = os.getenv('PAYMENTS', 'DISABLED')

# ID чатов
BLOCKED_CHAT = int(os.getenv('BLOCKED_CHAT', '-4965406464'))
SUPPORT_CHAT = int(os.getenv('SUPPORT_CHAT', '-4897467103'))
ADVERTISEMENT_LOG = int(os.getenv('ADVERTISEMENT_LOG', '-4835007907'))
MESSAGE_LOG = int(os.getenv('MESSAGE_LOG', '-4887694437'))
REPORT_LOG = int(os.getenv('REPORT_LOG', '-4975004306'))
NAME_MODERATION_CHAT = int(os.getenv('NAME_MODERATION_CHAT', os.getenv('REPORT_LOG', '-4975004306')))

# Цена
PRICE = int(os.getenv('PRICE', '90'))

# Максимальная длина имени исполнителя
MAX_WORKER_NAME_LENGTH = int(os.getenv('MAX_WORKER_NAME_LENGTH', '15'))
# Минимальная длина имени исполнителя
MIN_WORKER_NAME_LENGTH = int(os.getenv('MIN_WORKER_NAME_LENGTH', '2'))

# API ключи (необязательные)
API_KEY = os.getenv('API_KEY', 'ключ')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN', 'токен')

# Yandex Cloud настройки
FOLDER_ID = os.getenv('FOLDER_ID', 'b1g65bqsr2f2p2k3p1jk')
URL_VISION_API = os.getenv('URL_VISION_API', 'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze')
YANDEX_API_SECRET_KEY = os.getenv('YANDEX_API_SECRET_KEY', '')


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
