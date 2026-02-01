from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "bot.db")
FORCE_SUB_LINK = os.getenv("FORCE_SUB_LINK", "")

# Admin ID'lar - vergul bilan ajratilgan
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

SHARE_BOT_USERNAME = os.getenv("SHARE_BOT_USERNAME", "BgGeneratorBot")
PROMO_CHANNEL = os.getenv("PROMO_CHANNEL", "@primekin0")

RANDOM_LIST_LIMIT = int(os.getenv("RANDOM_LIST_LIMIT", "15"))
MOVIE_LIST_LIMIT = int(os.getenv("MOVIE_LIST_LIMIT", "50"))
BROADCAST_CONCURRENCY = int(os.getenv("BROADCAST_CONCURRENCY", "20"))
BROADCAST_CHUNK_SIZE = int(os.getenv("BROADCAST_CHUNK_SIZE", "50"))

DB_TIMEOUT = float(os.getenv("DB_TIMEOUT", "30"))
DB_MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "5"))
