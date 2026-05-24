import os
from dotenv import load_dotenv

load_dotenv()

API_ID: int = int(os.environ["TELEGRAM_API_ID"])
API_HASH: str = os.environ["TELEGRAM_API_HASH"]
BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]

RESULTS_PER_PAGE: int = 5
DB_PATH: str = "bot_data.db"
