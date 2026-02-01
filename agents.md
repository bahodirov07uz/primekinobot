# AGENTS.md

This repository is maintained using AI-assisted development (Codex / Agents).
Agents must follow the rules and structure defined below.

---

## 🎯 Project Goal

Refactor and maintain a **Telegram movie bot** (python-telegram-bot v20+) with:
- Clean modular architecture
- SQLite database (no ORM)
- Admin panel
- Force subscribe (mandatory channels)
- Premium users (bypass force subscribe)
- Movie/series by code
- Broadcast
- Share movie via Telegram deep links

The goal is to **avoid git conflicts**, reduce hard-coded logic, and keep behavior predictable.

---

## 🧱 Architecture Rules (MANDATORY)

Agents MUST keep the following structure:

