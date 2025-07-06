import logging
import json
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАЛАШТУВАННЯ ---
# Беремо токен та ID групи зі змінних середовища (це безпечніше)
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", -1001234567890)) # За замовчуванням - приклад

REPORT_HOUR = int(os.getenv("REPORT_HOUR", 21))  # Година для звіту (21:00)
WEEKLY_REPORT_DAY = os.getenv("WEEKLY_REPORT_DAY", 'sun') # неділя

# Шлях до файлу даних. Якщо змінна DATA_PATH не задана, використовуємо поточну папку.
DATA_DIR = os.getenv("DATA_PATH", ".")
DATA_FILE = os.path.join(DATA_DIR, "user_data.json")

# Перевірка, чи задані обов'язкові змінні
if not TOKEN:
    raise ValueError("Не знайдено змінну середовища TELEGRAM_TOKEN!")
if not GROUP_CHAT_ID:
    raise ValueError("Не знайдено змінну середовища GROUP_CHAT_ID!")

# Налаштування логування для відстеження помилок
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- ФУНКЦІЇ ДЛЯ РОБОТИ З ДАНИМИ ---
def load_data():
    """Завантажує дані користувачів з файлу."""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Якщо файл не існує або порожній, створюємо папку (якщо треба) і повертаємо порожню структуру
        os.makedirs(DATA_DIR, exist_ok=True)
        return {"daily": {}, "weekly": {}}

def save_data(data):
    """Зберігає дані у файл."""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- ОСНОВНА ЛОГІКА БОТА (залишається без змін) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text or '+' not in message.text:
        return

    user = message.from_user
    user_id = str(user.id)
    user_name = user.full_name

    data = load_data()
    
    # Оновлюємо щоденний лічильник
    daily_stats = data.get("daily", {})
    daily_stats.setdefault(user_id, {"name": user_name, "count": 0})
    daily_stats[user_id]["name"] = user_name
    daily_stats[user_id]["count"] += message.text.count('+')
    data["daily"] = daily_stats

    # Оновлюємо тижневий лічильник
    weekly_stats = data.get("weekly", {})
    weekly_stats.setdefault(user_id, {"name": user_name, "count": 0})
    weekly_stats[user_id]["name"] = user_name
    weekly_stats[user_id]["count"] += message.text.count('+')
    data["weekly"] = weekly_stats

    save_data(data)
    logger.info(f"User {user_name} added a plus. Daily: {data['daily'].get(user_id, {}).get('count', 0)}, Weekly: {data['weekly'].get(user_id, {}).get('count', 0)}")


async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    daily_stats = data.get("daily", {})
    if not daily_stats:
        report_text = "✨ **Щоденний звіт** ✨\n\nЗа сьогодні ніхто не ставив плюси."
    else:
        report_text = "✨ **Щоденний звіт по плюсах** ✨\n\n"
        total_pluses = 0
        sorted_users = sorted(daily_stats.items(), key=lambda item: item[1]['count'], reverse=True)
        for user_id, user_data in sorted_users:
            report_text += f"▪️ {user_data['name']}: **{user_data['count']}**\n"
            total_pluses += user_data['count']
        report_text += f"\n**Всього за день:** {total_pluses}"

    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=report_text, parse_mode='Markdown')
    logger.info("Daily report sent.")
    
    data["daily"] = {}
    save_data(data)

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    weekly_stats = data.get("weekly", {})
    if not weekly_stats:
        report_text = "🗓️ **Тижневий звіт** 🗓️\n\nЗа весь тиждень плюсиків не було."
    else:
        report_text = "🗓️ **Великий тижневий звіт!** 🗓️\n\nРезультати за весь тиждень:\n"
        total_pluses = 0
        sorted_users = sorted(weekly_stats.items(), key=lambda item: item[1]['count'], reverse=True)
        for user_id, user_data in sorted_users:
            report_text += f"🏆 {user_data['name']}: **{user_data['count']}**\n"
            total_pluses += user_data['count']
        report_text += f"\n**Загалом за тиждень:** {total_pluses}!"
        report_text += "\n\nПочинаємо новий тиждень! Статистику обнулено."
        
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=report_text, parse_mode='Markdown')
    logger.info("Weekly report sent.")

    data["daily"] = {}
    data["weekly"] = {}
    save_data(data)


def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_message))

    scheduler = AsyncIOScheduler(timezone="Europe/Kiev")
    scheduler.add_job(send_daily_report, 'cron', hour=REPORT_HOUR, minute=0, args=[application])
    scheduler.add_job(send_weekly_report, 'cron', day_of_week=WEEKLY_REPORT_DAY, hour=REPORT_HOUR, minute=5, args=[application]) # щотижневий звіт через 5хв
    scheduler.start()

    logger.info("Бот запущений і готовий до роботи!")
    application.run_polling()

if __name__ == "__main__":
    main()
