#!/usr/bin/env python3
import logging
import json
import os
import asyncio
import urllib.request
from google import genai
from datetime import datetime, timedelta
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"

# Conversation states
WAITING_DATE, WAITING_TIME = range(2)
WAITING_DONE_TASKS, WAITING_POSTPONE_DATE, WAITING_TOMORROW_TASKS = range(3, 6)

EVENING_HOUR = 23   # Kechqurun hisobot vaqti
MORNING_HOUR = 8    # Ertalab reja vaqti

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "tasks": [],
        "events": [],
        "chat_ids": [],
        "tomorrow_tasks": [],
        "pending_postpone": []
    }

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

async def ask_gemini(question: str, context_info: str = "") -> str:
    try:
        prompt = f"Sen o'zbek tilida javob beradigan aqlli assistentsan. Qisqa va aniq javob ber."
        if context_info:
            prompt += f"\n\nFoydalanuvchi ma'lumotlari:\n{context_info}"
        prompt += f"\n\nSavol: {question}"

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}
        }).encode("utf-8")

        req = urllib.request.Request(
            GEMINI_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "candidates" in result and result["candidates"]:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                logger.error(f"Gemini kutilmagan javob: {result}")
                return "❗ AI javob bera olmadi."
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        logger.error(f"Gemini HTTP {e.code}: {body}")
        return f"❗ AI xizmatida xatolik ({e.code})."
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        return "❗ Hozir javob bera olmayapman."

# ========================
# START
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    keyboard = [
        [InlineKeyboardButton("✅ Vazifalar", callback_data="menu_tasks"),
         InlineKeyboardButton("📅 Jadval", callback_data="menu_events")],
        [InlineKeyboardButton("🤖 AI ga so'ra", callback_data="menu_ai"),
         InlineKeyboardButton("📊 Umumiy", callback_data="menu_all")],
    ]
    await update.message.reply_text(
        "👋 Salom! Men sizning aqlli shaxsiy assistentingizman.\n\n"
        "✅ Vazifalar va eslatmalar\n"
        "📅 Jadval boshqaruvi\n"
        "🤖 AI javoblari (Gemini)\n"
        "🌙 Kechqurun hisobot (23:00)\n"
        "☀️ Ertalab reja (08:00)\n\n"
        "Nima qilishimni xohlaysiz?",
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
        "*/ai <savol>* — AI dan so'rash\n"
        "*/hisobot* — Kechqurun hisobotni boshlash\n"
        "*/bekor* — Amalni bekor qilish",
        parse_mode="Markdown"
    )

# ========================
# AI BUYRUG'I
# ========================
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🤖 Misol: /ai Bugun nima qilsam bo'ladi?")
        return
    question = " ".join(context.args)
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]
    context_info = f"Bajarilmagan vazifalar: {[t['text'] for t in pending]}"
    msg = await update.message.reply_text("🤔 O'ylamoqda...")
    answer = await ask_gemini(question, context_info)
    await msg.edit_text(f"🤖 *AI javobi:*\n\n{answer}", parse_mode="Markdown")

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
    return ConversationHandler.END

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["tasks"]:
        await update.message.reply_text("📋 Hozircha vazifalar yo'q.\n/vazifa <matn>")
        return
    text = "📋 *Vazifalar:*\n\n"
    for t in data["tasks"]:
        status = "✅" if t["done"] else "⬜"
        remind = f"\n   ⏰ {t['remind_at']}" if t.get("remind_at") and not t["done"] else ""
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
# ESLATMA CONVERSATION
# ========================
async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "set_reminder":
        await query.edit_message_text(
            "📅 *Qaysi sanada eslatay?*\n\nFormat: `KK.OO.YYYY`\nMisol: `03.05.2026`",
            parse_mode="Markdown"
        )
        return WAITING_DATE
    elif query.data == "skip_reminder":
        await query.edit_message_text("✅ Vazifa saqlandi.")
        return ConversationHandler.END

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(date_text, "%d.%m.%Y")
        context.user_data["reminder_date"] = date_obj.strftime("%Y-%m-%d")
        await update.message.reply_text(
            f"✅ Sana: *{date_text}*\n\n🕐 *Soatni kiriting:*\nMisol: `09:00`",
            parse_mode="Markdown"
        )
        return WAITING_TIME
    except ValueError:
        await update.message.reply_text("❗ Format: `03.05.2026`", parse_mode="Markdown")
        return WAITING_DATE

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
        date_str = context.user_data.get("reminder_date")
        remind_dt = datetime.strptime(f"{date_str} {time_text}", "%Y-%m-%d %H:%M")
        if remind_dt <= datetime.now():
            await update.message.reply_text("❗ Vaqt o'tib ketgan! Sanani qaytadan kiriting: `03.05.2026`", parse_mode="Markdown")
            return WAITING_DATE
        task_id = context.user_data.get("pending_task_id")
        data = load_data()
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["remind_at"] = remind_dt.strftime("%Y-%m-%d %H:%M")
                t["reminded"] = False
                save_data(data)
                await update.message.reply_text(
                    f"🔔 *Eslatma belgilandi!*\n\n📌 {t['text']}\n📅 {remind_dt.strftime('%d.%m.%Y')} soat {time_text}",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❗ Format: `09:00`", parse_mode="Markdown")
        return WAITING_TIME

# ========================
# KECHQURUN HISOBOT SYSTEM
# ========================
async def start_evening_report(bot, chat_id):
    """Kechqurun 23:00 da avtomatik ishga tushadi"""
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]

    if not pending:
        await bot.send_message(
            chat_id=chat_id,
            text="🌙 *Kechqurun hisoboti*\n\n"
                 "✅ Zo'r! Bugun barcha vazifalarni bajardingiz!\n\n"
                 "Ertaga nima rejalashtiryapsiz?\n"
                 "Yangi vazifalarni yozing (har birini alohida qatorda).\n"
                 "Tugatgach /tayyor yozing.",
            parse_mode="Markdown"
        )
        data["evening_state"] = {"state": "waiting_tomorrow", "chat_id": chat_id}
        save_data(data)
        return

    task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(pending)])
    await bot.send_message(
        chat_id=chat_id,
        text=f"🌙 *Kechqurun hisoboti*\n\n"
             f"Bugun quyidagi vazifalar bajarilmadi:\n\n{task_list}\n\n"
             f"Qaysilarini *bajardingiz*? Raqamlarini yozing.\n"
             f"Misol: `1 3` yoki `barchasi` yoki `hech biri`",
        parse_mode="Markdown"
    )
    data["evening_state"] = {
        "state": "waiting_done",
        "chat_id": chat_id,
        "pending_ids": [t["id"] for t in pending]
    }
    save_data(data)

async def handle_evening_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi bajargan vazifalarni belgilaydi"""
    data = load_data()
    state = data.get("evening_state", {})

    if state.get("state") != "waiting_done":
        return False

    text = update.message.text.strip().lower()
    pending_ids = state.get("pending_ids", [])
    pending = [t for t in data["tasks"] if t["id"] in pending_ids]

    done_ids = []
    if text == "barchasi":
        done_ids = pending_ids
    elif text == "hech biri":
        done_ids = []
    else:
        try:
            numbers = [int(x) for x in text.split()]
            for num in numbers:
                if 1 <= num <= len(pending):
                    done_ids.append(pending[num-1]["id"])
        except:
            await update.message.reply_text("❗ Raqamlarni yozing. Misol: `1 3` yoki `barchasi`", parse_mode="Markdown")
            return True

    # Bajarilganlarni belgilash
    for t in data["tasks"]:
        if t["id"] in done_ids:
            t["done"] = True

    # Bajarilmaganlar
    not_done = [t for t in pending if t["id"] not in done_ids]

    if not_done:
        task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(not_done)])
        await update.message.reply_text(
            f"✅ Bajarildi deb belgilandi!\n\n"
            f"Quyidagilar bajarilmadi:\n{task_list}\n\n"
            f"Qaysi kunga o'tkazamiz?\n"
            f"Format: `KK.OO.YYYY` — barchasi uchun\n"
            f"Yoki `ertaga` deb yozing",
            parse_mode="Markdown"
        )
        data["evening_state"] = {
            "state": "waiting_postpone",
            "chat_id": state["chat_id"],
            "not_done_ids": [t["id"] for t in not_done]
        }
    else:
        await update.message.reply_text(
            "✅ Ajoyib! Barchasi bajarildi!\n\n"
            "🌟 Ertaga nima rejalashtiryapsiz?\n"
            "Vazifalarni yozing (har biri yangi qatorda).\n"
            "Tugatgach /tayyor yozing.",
            parse_mode="Markdown"
        )
        data["evening_state"] = {
            "state": "waiting_tomorrow",
            "chat_id": state["chat_id"]
        }

    save_data(data)
    return True

async def handle_evening_postpone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bajarilmagan vazifalarni qaysi kunga o'tkazish"""
    data = load_data()
    state = data.get("evening_state", {})

    if state.get("state") != "waiting_postpone":
        return False

    text = update.message.text.strip().lower()
    not_done_ids = state.get("not_done_ids", [])

    # Sanani aniqlash
    if text == "ertaga":
        new_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        date_display = "ertaga"
    else:
        try:
            date_obj = datetime.strptime(text, "%d.%m.%Y")
            new_date = date_obj.strftime("%Y-%m-%d")
            date_display = text
        except:
            await update.message.reply_text(
                "❗ Format: `ertaga` yoki `04.05.2026`",
                parse_mode="Markdown"
            )
            return True

    # Vazifalarni yangilash
    for t in data["tasks"]:
        if t["id"] in not_done_ids:
            t["remind_at"] = f"{new_date} 09:00"
            t["reminded"] = False

    await update.message.reply_text(
        f"📅 Bajarilmagan vazifalar *{date_display}* ga o'tkazildi!\n\n"
        f"🌟 Ertaga nima rejalashtiryapsiz?\n"
        f"Yangi vazifalarni yozing (har biri yangi qatorda).\n"
        f"Tugatgach /tayyor yozing.",
        parse_mode="Markdown"
    )
    data["evening_state"] = {
        "state": "waiting_tomorrow",
        "chat_id": state["chat_id"]
    }
    save_data(data)
    return True

async def handle_tomorrow_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ertangi vazifalarni qabul qilish"""
    data = load_data()
    state = data.get("evening_state", {})

    if state.get("state") != "waiting_tomorrow":
        return False

    task_text = update.message.text.strip()
    if not data.get("tomorrow_tasks"):
        data["tomorrow_tasks"] = []
    data["tomorrow_tasks"].append(task_text)
    save_data(data)

    await update.message.reply_text(
        f"✅ Qo'shildi: *{task_text}*\n\nYana qo'shish uchun yozing yoki /tayyor",
        parse_mode="Markdown"
    )
    return True

async def finish_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ertangi vazifalar tugadi"""
    data = load_data()
    state = data.get("evening_state", {})

    if state.get("state") != "waiting_tomorrow":
        await update.message.reply_text("❗ Hozir bu buyruq kerak emas.")
        return

    tomorrow_tasks = data.get("tomorrow_tasks", [])
    if tomorrow_tasks:
        # Ertangi vazifalarni asosiy ro'yxatga qo'shish
        for task_text in tomorrow_tasks:
            task = {
                "id": len(data["tasks"]) + 1,
                "text": task_text,
                "done": False,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "remind_at": None,
                "reminded": False
            }
            data["tasks"].append(task)

        task_list = "\n".join([f"• {t}" for t in tomorrow_tasks])
        await update.message.reply_text(
            f"🌙 *Kechqurun hisoboti tugadi!*\n\n"
            f"Ertangi vazifalar:\n{task_list}\n\n"
            f"Yaxshi uxlang! 😴",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🌙 Yaxshi uxlang! 😴")

    data["tomorrow_tasks"] = []
    data["evening_state"] = {"state": "done"}
    save_data(data)

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'lda hisobotni boshlash"""
    chat_id = update.effective_chat.id
    register_chat(chat_id)
    await start_evening_report(context.bot, chat_id)

# ========================
# ERTALAB REJA
# ========================
async def send_morning_plan(bot, chat_id):
    """Ertalab 08:00 da avtomatik yuboriladi"""
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")

    # Bugungi vazifalar (eslatma sanasi bugun bo'lganlar + umumiy bajarilmaganlar)
    today_tasks = [
        t for t in data["tasks"]
        if not t["done"] and (
            not t.get("remind_at") or
            t.get("remind_at", "").startswith(today)
        )
    ]

    if not today_tasks:
        await bot.send_message(
            chat_id=chat_id,
            text="☀️ *Xayrli tong!*\n\n"
                 "Bugun uchun vazifalar yo'q.\n"
                 "Yangi vazifa qo'shish: /vazifa <matn>",
            parse_mode="Markdown"
        )
        return

    task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(today_tasks)])
    await bot.send_message(
        chat_id=chat_id,
        text=f"☀️ *Xayrli tong!*\n\n"
             f"📋 *Bugungi vazifalaringiz:*\n\n{task_list}\n\n"
             f"Samarali kun bo'lsin! 💪",
        parse_mode="Markdown"
    )

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
        f"📅 Uchrashuv qo'shildi!\n\n📌 *{name}*\n🗓 {date_str} soat {time_str}",
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
# ASOSIY LOOP
# ========================
async def main_loop(bot):
    morning_sent_today = None
    evening_sent_today = None

    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            data = load_data()

            # Ertalab 08:00 reja
            if now.hour == MORNING_HOUR and now.minute < 2 and morning_sent_today != today:
                for chat_id in data.get("chat_ids", []):
                    await send_morning_plan(bot, chat_id)
                morning_sent_today = today

            # Kechqurun 23:00 hisobot
            if now.hour == EVENING_HOUR and now.minute < 2 and evening_sent_today != today:
                for chat_id in data.get("chat_ids", []):
                    await start_evening_report(bot, chat_id)
                evening_sent_today = today

            # Vazifa eslatmalari
            changed = False
            for task in data["tasks"]:
                if task.get("remind_at") and not task.get("reminded") and not task["done"]:
                    remind_dt = datetime.strptime(task["remind_at"], "%Y-%m-%d %H:%M")
                    diff = (remind_dt - now).total_seconds() / 60
                    if -2 <= diff <= 2:
                        for chat_id in data.get("chat_ids", []):
                            try:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=f"🔔 *Vazifa eslatmasi!*\n\n📌 {task['text']}",
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                logger.error(f"Xato: {e}")
                        task["reminded"] = True
                        changed = True

            # Uchrashuv eslatmalari
            for event in data["events"]:
                event_dt = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
                diff = (event_dt - now).total_seconds() / 60
                if 28 <= diff <= 32 and not event.get("reminded_30"):
                    for chat_id in data.get("chat_ids", []):
                        try:
                            await bot.send_message(
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
                            await bot.send_message(
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

        except Exception as e:
            logger.error(f"Main loop xato: {e}")

        await asyncio.sleep(60)

# ========================
# CALLBACK
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
            text = "📅 Uchrashuvlar yo'q."
        else:
            now = datetime.now()
            text = "📅 *Uchrashuvlar:*\n\n"
            for e in data["events"]:
                dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
                icon = "🔜" if dt >= now else "✅"
                text += f"{icon} *{e['id']}.* {e['name']} — {e['datetime']}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_ai":
        await query.edit_message_text(
            "🤖 *AI dan so'rash:*\n\n/ai <savolingiz>\n\nMisol: /ai Bugun nima qilsam bo'ladi?",
            parse_mode="Markdown"
        )

    elif query.data == "menu_all":
        pending = sum(1 for t in data["tasks"] if not t["done"])
        now = datetime.now()
        upcoming = sum(1 for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now)
        await query.edit_message_text(
            f"📊 *Umumiy holat:*\n\n"
            f"⬜ Bajarilmagan vazifalar: {pending} ta\n"
            f"📅 Kelayotgan uchrashuvlar: {upcoming} ta\n"
            f"🌙 Kechqurun hisobot: 23:00\n"
            f"☀️ Ertalab reja: 08:00",
            parse_mode="Markdown"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.")
    return ConversationHandler.END

# ========================
# XABAR HANDLER
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})

    # Kechqurun hisobot jarayonida
    if state.get("state") == "waiting_done":
        if await handle_evening_done(update, context):
            return
    elif state.get("state") == "waiting_postpone":
        if await handle_evening_postpone(update, context):
            return
    elif state.get("state") == "waiting_tomorrow":
        if await handle_tomorrow_tasks(update, context):
            return

    # Oddiy xabar — AI ga yuborish
    text = update.message.text.lower()
    if any(w in text for w in ["salom", "assalomu", "hi", "hello"]):
        await update.message.reply_text("👋 Salom! /start — menyu, /help — yordam")
    else:
        msg = await update.message.reply_text("🤔 O'ylamoqda...")
        answer = await ask_gemini(update.message.text)
        await msg.edit_text(f"🤖 {answer}")

# ========================
# MAIN
# ========================
async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return

    app = Application.builder().token(TOKEN).build()

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
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("vazifa", add_task))
    app.add_handler(CommandHandler("vazifalar", list_tasks))
    app.add_handler(CommandHandler("bajarildi", complete_task))
    app.add_handler(CommandHandler("jadval", add_event))
    app.add_handler(CommandHandler("uchrashuvlar", list_events))
    app.add_handler(CommandHandler("hisobot", manual_report))
    app.add_handler(CommandHandler("tayyor", finish_tomorrow))
    app.add_handler(CommandHandler("bekor", cancel))
    app.add_handler(reminder_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot ishga tushdi!")

    async with app:
        await app.start()
        await app.updater.start_polling()
        await main_loop(app.bot)

if __name__ == "__main__":
    asyncio.run(main())

