#!/usr/bin/env python3
"""
Shaxsiy Assistent Telegram Bot
- Jadval va uchrashuv boshqaruvi
- Eslatmalar va vazifalar
- Ma'lumot qidirish
"""

import logging
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Logging sozlash
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ma'lumotlar fayli
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "events": [], "notes": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========================
# ASOSIY MENYU
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✅ Vazifalar", callback_data="menu_tasks"),
         InlineKeyboardButton("📅 Jadval", callback_data="menu_events")],
        [InlineKeyboardButton("🔍 Ma'lumot qidirish", callback_data="menu_search"),
         InlineKeyboardButton("📋 Barcha eslatmalar", callback_data="menu_all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Salom! Men sizning shaxsiy assistentingizman.\n\n"
        "Nima qilishimni xohlaysiz?",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Buyruqlar ro'yxati:*\n\n"
        "*/start* — Bosh menyu\n"
        "*/vazifa <matn>* — Yangi vazifa qo'shish\n"
        "*/vazifalar* — Barcha vazifalar\n"
        "*/bajarildi <raqam>* — Vazifani bajarilgan deb belgilash\n"
        "*/jadval <sana> <vaqt> <nomi>* — Uchrashuv qo'shish\n"
        "  Misol: /jadval 2024-12-25 14:00 Do'stlar bilan uchrashuv\n"
        "*/uchrashuvlar* — Barcha uchrashuvlar\n"
        "*/qidir <so'rov>* — Ma'lumot qidirish\n"
        "*/ochirishv <raqam>* — Vazifani o'chirish\n"
        "*/ochirish_u <raqam>* — Uchrashuvni o'chirish\n"
        "*/tozala* — Bajarilgan vazifalarni o'chirish\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ========================
# VAZIFALAR (TASKS)
# ========================
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Vazifa matnini kiriting.\nMisol: /vazifa Hisobot yozish")
        return
    task_text = " ".join(context.args)
    data = load_data()
    task = {
        "id": len(data["tasks"]) + 1,
        "text": task_text,
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data["tasks"].append(task)
    save_data(data)
    await update.message.reply_text(f"✅ Vazifa qo'shildi:\n📌 *{task_text}*", parse_mode="Markdown")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data["tasks"]
    if not tasks:
        await update.message.reply_text("📋 Hozircha vazifalar yo'q.")
        return
    text = "📋 *Vazifalar ro'yxati:*\n\n"
    for t in tasks:
        status = "✅" if t["done"] else "⬜"
        text += f"{status} *{t['id']}.* {t['text']}\n   🕐 {t['created']}\n\n"
    keyboard = [[InlineKeyboardButton("➕ Vazifa qo'shish", callback_data="add_task_prompt")]]
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Vazifa raqamini kiriting.\nMisol: /bajarildi 1")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ Raqam kiriting.")
        return
    data = load_data()
    for t in data["tasks"]:
        if t["id"] == task_id:
            t["done"] = True
            save_data(data)
            await update.message.reply_text(f"✅ *{t['text']}* — bajarildi!", parse_mode="Markdown")
            return
    await update.message.reply_text("❗ Bunday raqamli vazifa topilmadi.")

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Vazifa raqamini kiriting.\nMisol: /ochirishv 1")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ Raqam kiriting.")
        return
    data = load_data()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
    if len(data["tasks"]) < before:
        save_data(data)
        await update.message.reply_text(f"🗑️ {task_id}-vazifa o'chirildi.")
    else:
        await update.message.reply_text("❗ Bunday raqamli vazifa topilmadi.")

async def clean_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if not t["done"]]
    save_data(data)
    cleaned = before - len(data["tasks"])
    await update.message.reply_text(f"🧹 {cleaned} ta bajarilgan vazifa o'chirildi.")

# ========================
# JADVAL (EVENTS)
# ========================
async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "❗ To'g'ri format:\n/jadval <sana> <vaqt> <nomi>\n"
            "Misol: /jadval 2024-12-25 14:00 Do'stlar bilan uchrashuv"
        )
        return
    date_str = context.args[0]
    time_str = context.args[1]
    name = " ".join(context.args[2:])
    try:
        event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("❗ Sana formati: YYYY-MM-DD, vaqt formati: HH:MM")
        return
    data = load_data()
    event = {
        "id": len(data["events"]) + 1,
        "name": name,
        "datetime": event_dt.strftime("%Y-%m-%d %H:%M"),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data["events"].append(event)
    # Vaqt bo'yicha tartibla
    data["events"].sort(key=lambda x: x["datetime"])
    save_data(data)
    await update.message.reply_text(
        f"📅 Uchrashuv qo'shildi:\n"
        f"📌 *{name}*\n"
        f"🗓 {date_str} soat {time_str}",
        parse_mode="Markdown"
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    events = data["events"]
    now = datetime.now()
    upcoming = [e for e in events if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now]
    past = [e for e in events if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") < now]

    text = "📅 *Uchrashuvlar:*\n\n"
    if upcoming:
        text += "🔜 *Kelayotganlar:*\n"
        for e in upcoming:
            dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
            diff = dt - now
            days = diff.days
            hours = diff.seconds // 3600
            time_left = f"{days} kun " if days > 0 else ""
            time_left += f"{hours} soat"
            text += f"  📌 *{e['id']}.* {e['name']}\n  🗓 {e['datetime']} (⏳ {time_left})\n\n"
    if past:
        text += "✅ *O'tganlar:*\n"
        for e in past[-3:]:  # Oxirgi 3 tasi
            text += f"  ✔️ *{e['id']}.* {e['name']} — {e['datetime']}\n"

    if not events:
        text = "📅 Hozircha uchrashuvlar yo'q."

    await update.message.reply_text(text, parse_mode="Markdown")

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Uchrashuv raqamini kiriting.\nMisol: /ochirish_u 1")
        return
    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ Raqam kiriting.")
        return
    data = load_data()
    before = len(data["events"])
    data["events"] = [e for e in data["events"] if e["id"] != event_id]
    if len(data["events"]) < before:
        save_data(data)
        await update.message.reply_text(f"🗑️ {event_id}-uchrashuv o'chirildi.")
    else:
        await update.message.reply_text("❗ Bunday raqamli uchrashuv topilmadi.")

# ========================
# MA'LUMOT QIDIRISH
# ========================
async def search_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Qidiruv so'rovini kiriting.\nMisol: /qidir Python dasturlash")
        return
    query = " ".join(context.args)
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    wiki_url = f"https://uz.wikipedia.org/wiki/{query.replace(' ', '_')}"
    youtube_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"

    keyboard = [
        [InlineKeyboardButton("🔍 Google", url=search_url)],
        [InlineKeyboardButton("📚 Wikipedia (UZ)", url=wiki_url)],
        [InlineKeyboardButton("▶️ YouTube", url=youtube_url)],
    ]
    await update.message.reply_text(
        f"🔍 *\"{query}\"* bo'yicha qidiruv natijalari:\n\nQuyidagi manbalardan foydalaning:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========================
# CALLBACK HANDLER
# ========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    if data_cb == "menu_tasks":
        data = load_data()
        tasks = data["tasks"]
        if not tasks:
            text = "📋 Hozircha vazifalar yo'q.\n\n/vazifa <matn> — yangi vazifa qo'shish"
        else:
            text = "📋 *Vazifalar:*\n\n"
            for t in tasks:
                status = "✅" if t["done"] else "⬜"
                text += f"{status} *{t['id']}.* {t['text']}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data_cb == "menu_events":
        data = load_data()
        events = data["events"]
        now = datetime.now()
        if not events:
            text = "📅 Hozircha uchrashuvlar yo'q.\n\n/jadval <sana> <vaqt> <nomi> — yangi uchrashuv"
        else:
            text = "📅 *Uchrashuvlar:*\n\n"
            for e in events:
                dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
                icon = "🔜" if dt >= now else "✅"
                text += f"{icon} *{e['id']}.* {e['name']} — {e['datetime']}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data_cb == "menu_search":
        await query.edit_message_text(
            "🔍 Ma'lumot qidirish uchun:\n\n/qidir <so'rov>\n\nMisol: /qidir Toshkent ob-havo"
        )

    elif data_cb == "menu_all":
        data = load_data()
        tasks = data["tasks"]
        events = data["events"]
        text = "📊 *Umumiy holat:*\n\n"
        pending = [t for t in tasks if not t["done"]]
        done = [t for t in tasks if t["done"]]
        text += f"✅ Vazifalar: {len(pending)} ta kutmoqda, {len(done)} ta bajarildi\n"
        now = datetime.now()
        upcoming = [e for e in events if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now]
        text += f"📅 Kelayotgan uchrashuvlar: {len(upcoming)} ta\n"
        await query.edit_message_text(text, parse_mode="Markdown")

# ========================
# ODDIY XABAR HANDLER
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(w in text for w in ["salom", "assalomu alaykum", "hi", "hello"]):
        await update.message.reply_text(
            "👋 Salom! Bugun sizga qanday yordam bera olaman?\n\n"
            "/start — Menyuni ochish\n"
            "/help — Barcha buyruqlar"
        )
    elif any(w in text for w in ["rahmat", "raxmat", "thanks", "thank you"]):
        await update.message.reply_text("😊 Arzimaydi! Yana yordam kerak bo'lsa, doim shu yerdaman.")
    else:
        await update.message.reply_text(
            "🤔 Tushunmadim. Quyidagi buyruqlardan foydalaning:\n\n"
            "/start — Menyu\n"
            "/help — Yordam\n"
            "/vazifa <matn> — Vazifa qo'shish\n"
            "/jadval <sana> <vaqt> <nomi> — Uchrashuv\n"
            "/qidir <so'rov> — Qidirish"
        )

# ========================
# ESLATMALAR (REMINDERS)
# ========================
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 daqiqada uchrashuvlarni tekshiradi"""
    data = load_data()
    now = datetime.now()
    chat_id = context.job.data

    for event in data["events"]:
        event_dt = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
        diff = event_dt - now
        minutes = diff.total_seconds() / 60

        # 30 daqiqa oldin eslatma
        if 28 <= minutes <= 32:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ *Eslatma!*\n\n"
                     f"📌 {event['name']}\n"
                     f"🗓 {event['datetime']}\n\n"
                     f"⏳ 30 daqiqadan so'ng boshlanadi!",
                parse_mode="Markdown"
            )
        # 5 daqiqa oldin eslatma
        elif 3 <= minutes <= 7:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 *Tez orada!*\n\n"
                     f"📌 {event['name']}\n"
                     f"⏳ 5 daqiqadan so'ng boshlanadi!",
                parse_mode="Markdown"
            )

async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eslatmalarni yoqish"""
    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        check_reminders,
        interval=300,  # har 5 daqiqada
        first=10,
        data=chat_id,
        name=str(chat_id)
    )
    await update.message.reply_text(
        "🔔 Eslatmalar yoqildi! Uchrashuv vaqti kelganda xabar beraman.\n"
        "(30 daqiqa va 5 daqiqa oldin)"
    )

# ========================
# MAIN
# ========================
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi topilmadi!")
        print("   export TELEGRAM_BOT_TOKEN='your_token_here' deb belgilang")
        return

    app = Application.builder().token(TOKEN).build()

    # Buyruqlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Vazifalar
    app.add_handler(CommandHandler("vazifa", add_task))
    app.add_handler(CommandHandler("vazifalar", list_tasks))
    app.add_handler(CommandHandler("bajarildi", complete_task))
    app.add_handler(CommandHandler("ochirishv", delete_task))
    app.add_handler(CommandHandler("tozala", clean_tasks))

    # Jadval
    app.add_handler(CommandHandler("jadval", add_event))
    app.add_handler(CommandHandler("uchrashuvlar", list_events))
    app.add_handler(CommandHandler("ochirish_u", delete_event))

    # Qidirish
    app.add_handler(CommandHandler("qidir", search_info))

    # Eslatmalar
    app.add_handler(CommandHandler("eslatmalar_yoq", setup_reminders))

    # Callback va xabarlar
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
