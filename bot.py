#!/usr/bin/env python3
import logging
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "events": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✅ Vazifalar", callback_data="menu_tasks"),
         InlineKeyboardButton("📅 Jadval", callback_data="menu_events")],
        [InlineKeyboardButton("🔍 Qidirish", callback_data="menu_search"),
         InlineKeyboardButton("📊 Umumiy", callback_data="menu_all")],
    ]
    await update.message.reply_text(
        "👋 Salom! Men sizning shaxsiy assistentingizman.\n\nNima qilishimni xohlaysiz?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Buyruqlar:*\n\n"
        "*/vazifa <matn>* — Vazifa qo'shish\n"
        "*/vazifalar* — Vazifalar ro'yxati\n"
        "*/bajarildi <raqam>* — Bajarildi\n"
        "*/jadval <sana> <vaqt> <nomi>* — Uchrashuv\n"
        "*/uchrashuvlar* — Uchrashuvlar\n"
        "*/qidir <so'rov>* — Qidirish",
        parse_mode="Markdown"
    )

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Misol: /vazifa Hisobot yozish")
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
    await update.message.reply_text(f"✅ Vazifa qo'shildi: *{task_text}*", parse_mode="Markdown")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["tasks"]:
        await update.message.reply_text("📋 Hozircha vazifalar yo'q.")
        return
    text = "📋 *Vazifalar:*\n\n"
    for t in data["tasks"]:
        status = "✅" if t["done"] else "⬜"
        text += f"{status} *{t['id']}.* {t['text']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Misol: /bajarildi 1")
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
    await update.message.reply_text("❗ Topilmadi.")

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("❗ Misol: /jadval 2024-12-25 14:00 Uchrashuv")
        return
    date_str, time_str = context.args[0], context.args[1]
    name = " ".join(context.args[2:])
    try:
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("❗ Format: YYYY-MM-DD HH:MM")
        return
    data = load_data()
    event = {
        "id": len(data["events"]) + 1,
        "name": name,
        "datetime": f"{date_str} {time_str}"
    }
    data["events"].append(event)
    save_data(data)
    await update.message.reply_text(f"📅 Uchrashuv qo'shildi: *{name}* — {date_str} {time_str}", parse_mode="Markdown")

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["events"]:
        await update.message.reply_text("📅 Hozircha uchrashuvlar yo'q.")
        return
    text = "📅 *Uchrashuvlar:*\n\n"
    now = datetime.now()
    for e in data["events"]:
        dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
        icon = "🔜" if dt >= now else "✅"
        text += f"{icon} *{e['id']}.* {e['name']} — {e['datetime']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def search_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Misol: /qidir Python")
        return
    query = " ".join(context.args)
    keyboard = [
        [InlineKeyboardButton("🔍 Google", url=f"https://www.google.com/search?q={query.replace(' ', '+')}")],
        [InlineKeyboardButton("📚 Wikipedia", url=f"https://uz.wikipedia.org/wiki/{query.replace(' ', '_')}")],
        [InlineKeyboardButton("▶️ YouTube", url=f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")],
    ]
    await update.message.reply_text(
        f"🔍 *{query}* bo'yicha qidiring:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "menu_tasks":
        data = load_data()
        text = "📋 *Vazifalar:*\n\n" + "\n".join(
            f"{'✅' if t['done'] else '⬜'} *{t['id']}.* {t['text']}" for t in data["tasks"]
        ) if data["tasks"] else "📋 Vazifalar yo'q.\n/vazifa <matn>"
        await query.edit_message_text(text, parse_mode="Markdown")
    elif query.data == "menu_events":
        data = load_data()
        text = "📅 *Uchrashuvlar:*\n\n" + "\n".join(
            f"📌 *{e['id']}.* {e['name']} — {e['datetime']}" for e in data["events"]
        ) if data["events"] else "📅 Uchrashuvlar yo'q.\n/jadval <sana> <vaqt> <nomi>"
        await query.edit_message_text(text, parse_mode="Markdown")
    elif query.data == "menu_search":
        await query.edit_message_text("🔍 Qidirish: /qidir <so'rov>")
    elif query.data == "menu_all":
        data = load_data()
        pending = sum(1 for t in data["tasks"] if not t["done"])
        await query.edit_message_text(
            f"📊 *Umumiy:*\n\n✅ Vazifalar: {pending} ta kutmoqda\n📅 Uchrashuvlar: {len(data['events'])} ta",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(w in text for w in ["salom", "assalomu", "hi", "hello"]):
        await update.message.reply_text("👋 Salom! /start — menyu, /help — yordam")
    else:
        await update.message.reply_text("🤔 /help — barcha buyruqlar")

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("vazifa", add_task))
    app.add_handler(CommandHandler("vazifalar", list_tasks))
    app.add_handler(CommandHandler("bajarildi", complete_task))
    app.add_handler(CommandHandler("jadval", add_event))
    app.add_handler(CommandHandler("uchrashuvlar", list_events))
    app.add_handler(CommandHandler("qidir", search_info))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
