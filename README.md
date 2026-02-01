# Telegram Movie Bot (python-telegram-bot v20+)

## Run
- Create `.env` with:
  - `BOT_TOKEN=...`
  - `ADMIN_IDS=123456789,987654321`
  - `DB_PATH=bot.db` (optional, default `bot.db`)
  - `FORCE_SUB_LINK=` (optional, kept for compatibility)
- Install deps: `pip install -r requirements.txt`
- Start: `python app.py`

## How to migrate existing bot.db
- The bot runs automatic migrations on startup (WAL mode, missing columns, and `force_channels` primary key).
- Just keep your existing `bot.db` in place and run `python app.py`.
- If you have `movies.json`, it will be imported once (ignored if codes already exist).

## Notes
- Deep-links: `https://t.me/primekin0bot?start=cinema_<CODE>`
- Force subscribe checks are skipped for admins and premium users.
