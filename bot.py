#!/usr/bin/env python3
import logging
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = "data.json"

# Conversation states
WAITING_DATE, WAITING_TIME = range(2)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "events": [], "chat_ids": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_chat(chat_id):
    data = load_data()
    if "chat_ids" not in data:
        data["chat_ids"] = []
    if chat_id not in data["chat_ids"]:
        data["chat_ids"].append(chat_id)
        save_data(data)

# ========================
# START
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
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
        "  Misol: /jadval 2026-05-03 14:00 Uchrashuv\n"
        "*/uchrashuvlar* — Uchrashuvlar\n"
        "*/qidir <so'rov>* — Qidirish",
        parse_mode="Markdown"
    )

# ========================
# VAZIFALAR
# ========================
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❗ Misol: /vazifa Hisobot yozish")
        return ConversationHandler.END

    task_text = " ".join(context.args)
    data = load_data()
    task = {
        "id": len(data["tasks"]) + 1,
        "text": task_text,
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "remind_at": None,
        "reminded": False
    }
    data["tasks"].append(task)
    save_data(data)

    # Joriy task ID ni saqlab qo'yamiz
    context.user_data["pending_task_id"] = task["id"]

    keyboard = [
        [InlineKeyboardButton("✅ Ha, eslatma belgilayman", callback_data="set_reminder")],
        [InlineKeyboardButton("❌ Yo'q, keyinroq", callback_data="skip_reminder")],
    ]
    await update.message.reply_text(
        f"✅ Vazifa qo'shildi: *{task_text}*\n\n⏰ Eslatma belgilaymizmi?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["tasks"]:
        await update.message.reply_text("📋 Hozircha vazifalar yo'q.\n/vazifa <matn>")
        return
    text = "📋 *Vazifalar:*\n\n"
    for t in data["tasks"]:
        status = "✅" if t["done"] else "⬜"
        remind = f"\n   ⏰ *{t['remind_at']}*" if t.get("remind_at") and not t["done"] else ""
        text += f"{status} *{t['id']}.* {t['text']}{remind}\n\n"
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

# ========================
# ESLATMA QO'SHISH (Conversation)
# ========================
async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "set_reminder":
        await query.edit_message_text(
            "📅 *Qaysi sanada eslatay?*\n\n"
            "Formatda yozing: `KK.OO.YYYY`\n"
            "Misol: `03.05.2026`",
            parse_mode="Markdown"
        )
        return WAITING_DATE

    elif query.data == "skip_reminder":
        await query.edit_message_text("✅ Vazifa saqlandi. Eslatmasiz.")
        return ConversationHandler.END

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(date_text, "%d.%m.%Y")
        context.user_data["reminder_date"] = date_obj.strftime("%Y-%m-%d")
        await update.message.reply_text(
            f"✅ Sana: *{date_text}*\n\n"
            "🕐 *Soatni kiriting:*\n"
            "Misol: `09:00`",
            parse_mode="Markdown"
        )
        return WAITING_TIME
    except ValueError:
        await update.message.reply_text(
            "❗ Noto'g'ri format. Qaytadan kiriting:\n"
            "Misol: `03.05.2026`",
            parse_mode="Markdown"
        )
        return WAITING_DATE

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    try:
        time_obj = datetime.strptime(time_text, "%H:%M")
        date_str = context.user_data.get("reminder_date")
        remind_dt = datetime.strptime(f"{date_str} {time_text}", "%Y-%m-%d %H:%M")

        if remind_dt <= datetime.now():
            await update.message.reply_text(
                "❗ Bu vaqt o'tib ketgan! Kelajakdagi sana kiriting.\n\n"
                "📅 Sanani qaytadan kiriting: `03.05.2026`",
                parse_mode="Markdown"
            )
            return WAITING_DATE

        task_id = context.user_data.get("pending_task_id")
        data = load_data()
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["remind_at"] = remind_dt.strftime("%Y-%m-%d %H:%M")
                t["reminded"] = False
                save_data(data)
                await update.message.reply_text(
                    f"🔔 *Eslatma belgilandi!*\n\n"
                    f"📌 {t['text']}\n"
                    f"📅 {remind_dt.strftime('%d.%m.%Y')} soat {time_text}",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END

        await update.message.reply_text("❗ Vazifa topilmadi.")
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "❗ Noto'g'ri format. Misol: `09:00`",
            parse_mode="Markdown"
        )
        return WAITING_TIME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.")
    return ConversationHandler.END

# ========================
# JADVAL
# ========================
async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    if len(context.args) < 3:
        await update.message.reply_text("❗ Misol: /jadval 2026-05-03 14:00 Uchrashuv")
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
        "datetime": f"{date_str} {time_str}",
        "reminded_30": False,
        "reminded_5": False
    }
    data["events"].append(event)
    save_data(data)
    await update.message.reply_text(
        f"📅 Uchrashuv qo'shildi!\n\n📌 *{name}*\n🗓 {date_str} soat {time_str}\n\n"
        f"🔔 30 daqiqa va 5 daqiqa oldin eslataman!",
        parse_mode="Markdown"
    )

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

# ========================
# QIDIRISH
# ========================
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
        f"🔍 *{query}* bo'yicha:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========================
# ESLATMALAR TEKSHIRISH
# ========================
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    now = datetime.now()
    changed = False

    for task in data["tasks"]:
        if task.get("remind_at") and not task.get("reminded") and not task["done"]:
            remind_dt = datetime.strptime(task["remind_at"], "%Y-%m-%d %H:%M")
            diff = (remind_dt - now).total_seconds() / 60
            if -2 <= diff <= 2:
                for chat_id in data.get("chat_ids", []):
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🔔 *Vazifa eslatmasi!*\n\n📌 {task['text']}\n⏰ {task['remind_at']}",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Xato: {e}")
                task["reminded"] = True
                changed = True

    for event in data["events"]:
        event_dt = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
        diff = (event_dt - now).total_seconds() / 60

        if 28 <= diff <= 32 and not event.get("reminded_30"):
            for chat_id in data.get("chat_ids", []):
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⏰ *30 daqiqada uchrashuv!*\n\n📌 {event['name']}\n🗓 {event['datetime']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Xato: {e}")
            event["reminded_30"] = True
            changed = True

        if 3 <= diff <= 7 and not event.get("reminded_5"):
            for chat_id in data.get("chat_ids", []):
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔔 *5 daqiqada uchrashuv!*\n\n📌 {event['name']}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Xato: {e}")
            event["reminded_5"] = True
            changed = True

    if changed:
        save_data(data)

# ========================
# CALLBACK HANDLER
# ========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    if query.data == "menu_tasks":
        if not data["tasks"]:
            text = "📋 Vazifalar yo'q.\n/vazifa <matn>"
        else:
            text = "📋 *Vazifalar:*\n\n"
            for t in data["tasks"]:
                status = "✅" if t["done"] else "⬜"
                remind = f" ⏰{t['remind_at']}" if t.get("remind_at") and not t["done"] else ""
                text += f"{status} *{t['id']}.* {t['text']}{remind}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_events":
        if not data["events"]:
            text = "📅 Uchrashuvlar yo'q.\n/jadval <sana> <vaqt> <nomi>"
        else:
            now = datetime.now()
            text = "📅 *Uchrashuvlar:*\n\n"
            for e in data["events"]:
                dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
                icon = "🔜" if dt >= now else "✅"
                text += f"{icon} *{e['id']}.* {e['name']} — {e['datetime']}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_search":
        await query.edit_message_text("🔍 Qidirish: /qidir <so'rov>")

    elif query.data == "menu_all":
        pending = sum(1 for t in data["tasks"] if not t["done"])
        with_remind = sum(1 for t in data["tasks"] if t.get("remind_at") and not t["done"])
        now = datetime.now()
        upcoming = sum(1 for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now)
        await query.edit_message_text(
            f"📊 *Umumiy holat:*\n\n"
            f"⬜ Kutilayotgan vazifalar: {pending} ta\n"
            f"⏰ Eslatmali vazifalar: {with_remind} ta\n"
            f"📅 Kelayotgan uchrashuvlar: {upcoming} ta",
            parse_mode="Markdown"
        )

# ========================
# XABAR HANDLER
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if any(w in text for w in ["salom", "assalomu", "hi", "hello"]):
        await update.message.reply_text("👋 Salom! /start — menyu, /help — yordam")
    else:
        await update.message.reply_text("🤔 /help — barcha buyruqlar")

# ========================
# MAIN
# ========================
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return

    app = Application.builder().token(TOKEN).build()

    # Eslatma conversation handler
    reminder_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reminder_callback, pattern="^(set_reminder|skip_reminder)$")],
        states={
            WAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            WAITING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("vazifa", add_task))
    app.add_handler(CommandHandler("vazifalar", list_tasks))
    app.add_handler(CommandHandler("bajarildi", complete_task))
    app.add_handler(CommandHandler("jadval", add_event))
    app.add_handler(CommandHandler("uchrashuvlar", list_events))
    app.add_handler(CommandHandler("qidir", search_info))
    app.add_handler(reminder_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Har daqiqada eslatmalarni tekshirish
    app.job_queue.run_repeating(check_reminders, interval=60, first=10)

    print("🤖 Bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
