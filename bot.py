import os
import json
import asyncio
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from openai import OpenAI

# =========================
# ===== ПЕРЕМЕННЫЕ ========
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SCHEDULE_URL = os.getenv("SCHEDULE_URL")
APPLICATION_URL = os.getenv("APPLICATION_URL")
COMMAND_CHAT_ID = os.getenv("COMMAND_CHAT_ID")

UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 300))
INVITE_SCORE = int(os.getenv("TRAINING_INVITE_SCORE", 60))

if not TELEGRAM_TOKEN:
    raise ValueError("Нет TELEGRAM_BOT_TOKEN")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# ===== CRM ===============
# =========================

def load_crm():
    try:
        with open("crm.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"candidates": [], "priority_candidates": []}

def save_crm(crm):
    with open("crm.json", "w", encoding="utf-8") as f:
        json.dump(crm, f, ensure_ascii=False, indent=2)

crm = load_crm()

# =========================
# ===== TELEGRAM ==========
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Strikeball Bot v2.0 запущен.\n"
        "/nearest — ближайшая игра\n"
        "/priority — приоритетные кандидаты"
    )

async def nearest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    games = get_schedule()
    if games:
        await update.message.reply_text(f"Ближайшая игра: {games[0]}")
    else:
        await update.message.reply_text("Игры не найдены.")

async def priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if crm["priority_candidates"]:
        text = "\n".join(crm["priority_candidates"])
        await update.message.reply_text("Приоритетные кандидаты:\n" + text)
    else:
        await update.message.reply_text("Пока нет приоритетных.")

# =========================
# ===== ПАРСИНГ ===========
# =========================

def get_schedule():
    try:
        r = requests.get(SCHEDULE_URL, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        return [a.text.strip() for a in soup.find_all("a", class_="subject")]
    except:
        return []

def get_applications():
    try:
        r = requests.get(APPLICATION_URL, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        apps = []
        for a in soup.find_all("a", class_="subject"):
            apps.append({
                "name": a.text.strip(),
                "text": a.text.strip()
            })
        return apps
    except:
        return []

# =========================
# ===== AI АНАЛИЗ =========
# =========================

def analyze_candidate(text):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты анализируешь анкету кандидата в страйкбольную команду. Оцени по шкале 0-100 и объясни кратко."},
                {"role": "user", "content": text}
            ]
        )
        result = response.choices[0].message.content
        score = extract_score(result)
        return score, result
    except Exception as e:
        print("AI error:", e)
        return 0, "AI анализ недоступен"

def extract_score(text):
    import re
    match = re.search(r"\b(\d{1,3})\b", text)
    return int(match.group(1)) if match else 0

# =========================
# ===== ЛОГИКА ============
# =========================

def is_duplicate(name):
    return any(c["name"] == name for c in crm["candidates"])

async def process_applications(app):
    apps = get_applications()

    for a in apps:
        if is_duplicate(a["name"]):
            continue

        score, analysis = analyze_candidate(a["text"])

        candidate = {
            "name": a["name"],
            "score": score,
            "analysis": analysis
        }

        crm["candidates"].append(candidate)

        if score >= INVITE_SCORE:
            crm["priority_candidates"].append(a["name"])

            await app.bot.send_message(
                chat_id=COMMAND_CHAT_ID,
                text=f"🔥 Новый кандидат!\n\nИмя: {a['name']}\nОценка: {score}\n\n{analysis}"
            )

    save_crm(crm)

# =========================
# ===== ПЛАНИРОВЩИК =======
# =========================

async def scheduler(app):
    while True:
        await process_applications(app)
        await asyncio.sleep(UPDATE_INTERVAL)

# =========================
# ===== ЗАПУСК ============
# =========================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("nearest", nearest))
app.add_handler(CommandHandler("priority", priority))

async def main():
    asyncio.create_task(scheduler(app))
    await app.run_polling()

print("Strikeball Bot v2.0 запущен")
asyncio.run(main())