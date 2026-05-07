#!/usr/bin/env python3
import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from google import genai
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
EVENING_HOUR = 23
MORNING_HOUR = 8

# Conversation states
WAITING_DATE, WAITING_TIME = range(2)
WAITING_TOMORROW_TASK, WAITING_TOMORROW_TIME = range(2, 4)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "events": [], "chat_ids": [], "tomorrow_tasks": [], "evening_state": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_chat(chat_id):
    data = load_data()
    if chat_id not in data.get("chat_ids", []):
        data.setdefault("chat_ids", []).append(chat_id)
        save_data(data)

# ========================
# GEMINI AI
# ========================
async def ask_gemini(question: str, context_info: str = "") -> str:
    try:
        prompt = (
            "Sen Nodirbek ismli startapchi yigitning shaxsiy aqlli assistentisan. "
            "O'zbek tilida qisqa, aniq va foydali javob ber. "
            "Agar vazifalar haqida so'ralsa, ularni tahlil qilib maslahat ber."
        )
        if context_info:
            prompt += f"\n\nFoydalanuvchi haqida ma'lumot:\n{context_info}"
        prompt += f"\n\nSavol: {question}"

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        return "❗ AI hozir javob bera olmayapti. Keyinroq urinib ko'ring."

def get_context_for_ai():
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]
    today = datetime.now().strftime("%Y-%m-%d")
    today_tasks = [t for t in pending if not t.get("remind_at") or t.get("remind_at", "").startswith(today)]
    context = f"Bajarilmagan vazifalar ({len(pending)} ta): {[t['text'] for t in pending[:5]]}"
    if today_tasks:
        context += f"\nBugungi vazifalar: {[t['text'] for t in today_tasks]}"
    return context

# ========================
# START & HELP
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    keyboard = [
        [
            InlineKeyboardButton("✅ Vazifalar", callback_data="menu_tasks"),
            InlineKeyboardButton("📅 Jadval", callback_data="menu_events"),
        ],
        [
            InlineKeyboardButton("🤖 AI Maslahat", callback_data="menu_ai"),
            InlineKeyboardButton("📊 Statistika", callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton("📋 Bugungi reja", callback_data="menu_today"),
            InlineKeyboardButton("🌙 Hisobot", callback_data="menu_report"),
        ],
    ]
    await update.message.reply_text(
        "👋 *Salom, Nodirbek!*\n\n"
        "Men sizning aqlli shaxsiy assistentingizman 🤖\n\n"
        "🔹 Vazifalar & eslatmalar\n"
        "🔹 Jadval boshqaruvi\n"
        "🔹 AI maslahat & yordam\n"
        "🔹 Kechqurun hisobot (23:00)\n"
        "🔹 Ertalab reja (08:00)\n\n"
        "Nima qilishimni xohlaysiz?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Buyruqlar ro'yxati:*\n\n"
        "━━━ 📝 VAZIFALAR ━━━\n"
        "*/vazifa <matn>* — Yangi vazifa\n"
        "*/vazifalar* — Barcha vazifalar\n"
        "*/bajarildi <raqam>* — Bajarildi deb belgilash\n"
        "*/ochir <raqam>* — Vazifani o'chirish\n\n"
        "━━━ 📅 JADVAL ━━━\n"
        "*/jadval <sana> <vaqt> <nomi>* — Uchrashuv\n"
        "*/uchrashuvlar* — Uchrashuvlar\n\n"
        "━━━ 🤖 AI ━━━\n"
        "*/ai <savol>* — AI dan so'rash\n"
        "*/tahlil* — Vazifalarni AI tahlil qilsin\n\n"
        "━━━ 📊 BOSHQALAR ━━━\n"
        "*/hisobot* — Kechqurun hisobotni boshlash\n"
        "*/bugun* — Bugungi vazifalar\n"
        "*/bekor* — Amalni bekor qilish",
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
    context.user_data["pending_task_id"] = task["id"]

    keyboard = [
        [InlineKeyboardButton("⏰ Ha, vaqt belgilayman", callback_data="set_reminder")],
        [InlineKeyboardButton("➡️ Keyinroq", callback_data="skip_reminder")],
    ]
    await update.message.reply_text(
        f"✅ Vazifa qo'shildi!\n\n📌 *{task_text}*\n\n⏰ Eslatma vaqtini belgilaymizmi?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data["tasks"]
    if not tasks:
        await update.message.reply_text("📋 Hozircha vazifalar yo'q.\n\n/vazifa <matn> — yangi vazifa qo'shing")
        return

    pending = [t for t in tasks if not t["done"]]
    done = [t for t in tasks if t["done"]]

    text = "📋 *Vazifalar ro'yxati:*\n\n"
    if pending:
        text += "🔸 *Bajarilmaganlar:*\n"
        for t in pending:
            remind = f" ⏰ {t['remind_at']}" if t.get("remind_at") else ""
            text += f"  ⬜ *{t['id']}.* {t['text']}{remind}\n"
    if done:
        text += f"\n✅ *Bajarilganlar:* {len(done)} ta\n"
        for t in done[-3:]:
            text += f"  ✅ {t['text']}\n"

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
            await update.message.reply_text(
                f"✅ *{t['text']}* — bajarildi! 🎉",
                parse_mode="Markdown"
            )
            return
    await update.message.reply_text("❗ Bunday vazifa topilmadi.")

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Misol: /ochir 1")
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
        await update.message.reply_text(f"🗑️ Vazifa o'chirildi.")
    else:
        await update.message.reply_text("❗ Topilmadi.")

async def today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_list = [
        t for t in data["tasks"]
        if not t["done"] and (
            not t.get("remind_at") or t.get("remind_at", "").startswith(today)
        )
    ]
    if not today_list:
        await update.message.reply_text("☀️ Bugun uchun vazifalar yo'q!\n\n/vazifa <matn> — yangi qo'shing")
        return
    text = f"☀️ *Bugungi vazifalar ({len(today_list)} ta):*\n\n"
    for i, t in enumerate(today_list, 1):
        time_str = ""
        if t.get("remind_at"):
            time_str = f" — ⏰ {t['remind_at'].split(' ')[1]}"
        text += f"{i}. {t['text']}{time_str}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ========================
# AI TAHLIL
# ========================
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🤖 AI dan so'rash:\n/ai <savolingiz>\n\nMisol: /ai Bugun qaysi vazifadan boshlasam?"
        )
        return
    question = " ".join(context.args)
    msg = await update.message.reply_text("🤔 O'ylamoqda...")
    ctx = get_context_for_ai()
    answer = await ask_gemini(question, ctx)
    await msg.edit_text(f"🤖 *AI javobi:*\n\n{answer}", parse_mode="Markdown")

async def ai_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]
    if not pending:
        await update.message.reply_text("✅ Hozircha bajarilmagan vazifalar yo'q!")
        return
    msg = await update.message.reply_text("🤔 Vazifalarni tahlil qilyapman...")
    task_list = "\n".join([f"- {t['text']}" for t in pending])
    question = f"Mening bajarilmagan vazifalarim:\n{task_list}\n\nQaysi biridan boshlashimni maslahat bering va har biri uchun qisqa yo'riqnoma bering."
    answer = await ask_gemini(question)
    await msg.edit_text(f"🤖 *AI tahlili:*\n\n{answer}", parse_mode="Markdown")

# ========================
# ESLATMA CONVERSATION
# ========================
async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "set_reminder":
        await query.edit_message_text(
            "📅 *Qaysi sanada eslatay?*\n\n"
            "Format: `KK.OO.YYYY`\n"
            "Misol: `05.05.2026`\n\n"
            "Yoki: `bugun` / `ertaga`",
            parse_mode="Markdown"
        )
        return WAITING_DATE
    elif query.data == "skip_reminder":
        await query.edit_message_text("✅ Vazifa saqlandi. Eslatmasiz.")
        return ConversationHandler.END

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip().lower()
    try:
        if date_text == "bugun":
            date_obj = datetime.now()
        elif date_text == "ertaga":
            date_obj = datetime.now() + timedelta(days=1)
        else:
            date_obj = datetime.strptime(date_text, "%d.%m.%Y")
        context.user_data["reminder_date"] = date_obj.strftime("%Y-%m-%d")
        await update.message.reply_text(
            f"✅ Sana: *{date_obj.strftime('%d.%m.%Y')}*\n\n🕐 Soatni kiriting:\nMisol: `09:00`",
            parse_mode="Markdown"
        )
        return WAITING_TIME
    except ValueError:
        await update.message.reply_text(
            "❗ Format: `05.05.2026` yoki `bugun` / `ertaga`",
            parse_mode="Markdown"
        )
        return WAITING_DATE

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
        date_str = context.user_data.get("reminder_date")
        remind_dt = datetime.strptime(f"{date_str} {time_text}", "%Y-%m-%d %H:%M")
        if remind_dt <= datetime.now():
            await update.message.reply_text(
                f"❗ Bu vaqt o'tib ketgan! (Hozir {datetime.now().strftime('%H:%M')})"
                f"\nBoshqa vaqt kiriting: `{(datetime.now().strftime('%H:%M'))}`dan keyin",
                parse_mode="Markdown"
            )
            return WAITING_TIME
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
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❗ Format: `09:00`", parse_mode="Markdown")
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
        await update.message.reply_text(
            "❗ Format: /jadval <sana> <vaqt> <nomi>\n"
            "Misol: /jadval 2026-05-05 14:00 Qodir aka bilan uchrashuv"
        )
        return
    date_str, time_str = context.args[0], context.args[1]
    name = " ".join(context.args[2:])
    try:
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("❗ Sana: YYYY-MM-DD, vaqt: HH:MM")
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
        f"📅 *Uchrashuv qo'shildi!*\n\n"
        f"📌 {name}\n"
        f"🗓 {date_str} soat {time_str}\n\n"
        f"🔔 30 va 5 daqiqa oldin eslataman!",
        parse_mode="Markdown"
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["events"]:
        await update.message.reply_text("📅 Hozircha uchrashuvlar yo'q.")
        return
    now = datetime.now()
    text = "📅 *Uchrashuvlar:*\n\n"
    upcoming = [e for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now]
    past = [e for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") < now]
    if upcoming:
        text += "🔜 *Kelayotganlar:*\n"
        for e in upcoming:
            dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
            diff = dt - now
            hours = int(diff.total_seconds() // 3600)
            text += f"  📌 *{e['id']}.* {e['name']}\n  🗓 {e['datetime']} (⏳ {hours} soat)\n\n"
    if past:
        text += "✅ *O'tganlar (oxirgi 3):*\n"
        for e in past[-3:]:
            text += f"  ✔️ {e['name']} — {e['datetime']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ========================
# KECHQURUN HISOBOT
# ========================
async def start_evening_report(bot, chat_id):
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]

    if not pending:
        await bot.send_message(
            chat_id=chat_id,
            text="🌙 *Kechqurun hisoboti*\n\n"
                 "✅ Ajoyib! Bugun barcha vazifalarni bajardingiz!\n\n"
                 "Ertaga nima rejalashtiryapsiz?\n"
                 "Har bir vazifani yozing — men vaqtini ham so'rayman.\n"
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
             f"📋 Bugun bajarilmagan vazifalar:\n\n{task_list}\n\n"
             f"Qaysilarini *bajardingiz*?\n"
             f"Raqamlarini yozing: `1 3` yoki `barchasi` yoki `hech biri`",
        parse_mode="Markdown"
    )
    data["evening_state"] = {
        "state": "waiting_done",
        "chat_id": chat_id,
        "pending_ids": [t["id"] for t in pending]
    }
    save_data(data)

async def handle_evening_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})
    if state.get("state") != "waiting_done":
        return False

    text = update.message.text.strip().lower()
    pending_ids = state.get("pending_ids", [])
    pending = [t for t in data["tasks"] if t["id"] in pending_ids]

    done_ids = []
    if text == "barchasi":
        done_ids = pending_ids[:]
    elif text == "hech biri":
        done_ids = []
    else:
        try:
            numbers = [int(x) for x in text.split()]
            for num in numbers:
                if 1 <= num <= len(pending):
                    done_ids.append(pending[num-1]["id"])
        except:
            await update.message.reply_text(
                "❗ Raqamlarni yozing.\nMisol: `1 3` yoki `barchasi` yoki `hech biri`",
                parse_mode="Markdown"
            )
            return True

    for t in data["tasks"]:
        if t["id"] in done_ids:
            t["done"] = True

    not_done = [t for t in pending if t["id"] not in done_ids]

    if not_done:
        task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(not_done)])
        await update.message.reply_text(
            f"✅ Bajarildi deb belgilandi!\n\n"
            f"📋 Bajarilmaganlar:\n{task_list}\n\n"
            f"Qaysi kunga o'tkazamiz?\n"
            f"`ertaga` yoki `05.05.2026`",
            parse_mode="Markdown"
        )
        data["evening_state"] = {
            "state": "waiting_postpone",
            "chat_id": state["chat_id"],
            "not_done_ids": [t["id"] for t in not_done]
        }
    else:
        # AI motivatsiya
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            motivation = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents="Bugun barcha vazifalarini bajargan startapchi yigitga qisqa (2 jumlada) o'zbek tilida motivatsion so'z ayt."
            ).text
        except:
            motivation = "Zo'r ish! Davom eting! 💪"

        await update.message.reply_text(
            f"🎉 *Zo'r! Barchasi bajarildi!*\n\n"
            f"🤖 {motivation}\n\n"
            f"🌟 Ertaga nima rejalashtiryapsiz?\n"
            f"Vazifalarni yozing — men vaqtini so'rayman.\n"
            f"Tugatgach /tayyor yozing.",
            parse_mode="Markdown"
        )
        data["evening_state"] = {"state": "waiting_tomorrow", "chat_id": state["chat_id"]}

    save_data(data)
    return True

async def handle_evening_postpone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})
    if state.get("state") != "waiting_postpone":
        return False

    text = update.message.text.strip().lower()
    not_done_ids = state.get("not_done_ids", [])

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
                "❗ Format: `ertaga` yoki `05.05.2026`",
                parse_mode="Markdown"
            )
            return True

    for t in data["tasks"]:
        if t["id"] in not_done_ids:
            t["remind_at"] = f"{new_date} 09:00"
            t["reminded"] = False

    await update.message.reply_text(
        f"📅 Bajarilmagan vazifalar *{date_display}* ga o'tkazildi!\n\n"
        f"🌟 Ertaga nima rejalashtiryapsiz?\n"
        f"Vazifalarni yozing — men vaqtini so'rayman.\n"
        f"Tugatgach /tayyor yozing.",
        parse_mode="Markdown"
    )
    data["evening_state"] = {"state": "waiting_tomorrow", "chat_id": state["chat_id"]}
    save_data(data)
    return True

async def handle_tomorrow_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})

    # Vaqtni qabul qilish
    if state.get("state") == "waiting_tomorrow_time":
        time_text = update.message.text.strip()
        try:
            datetime.strptime(time_text, "%H:%M")
            pending_task = state.get("pending_task", "")
            if not isinstance(data.get("tomorrow_tasks"), list):
                data["tomorrow_tasks"] = []
            data["tomorrow_tasks"].append({"text": pending_task, "time": time_text})
            data["evening_state"]["state"] = "waiting_tomorrow"
            save_data(data)
            await update.message.reply_text(
                f"✅ *{pending_task}* — soat {time_text}\n\n"
                f"Yana vazifa yozing yoki /tayyor",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text(
                "❗ Vaqt formati: `09:00`",
                parse_mode="Markdown"
            )
        return True

    # Yangi vazifa qabul qilish
    if state.get("state") != "waiting_tomorrow":
        return False

    task_text = update.message.text.strip()
    data["evening_state"]["state"] = "waiting_tomorrow_time"
    data["evening_state"]["pending_task"] = task_text
    save_data(data)
    await update.message.reply_text(
        f"📌 *{task_text}*\n\n⏰ Soat nechada bajarasiz?\nMisol: `10:00`",
        parse_mode="Markdown"
    )
    return True

async def finish_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})
    if state.get("state") not in ["waiting_tomorrow", "waiting_tomorrow_time"]:
        await update.message.reply_text("❗ Hozir bu buyruq kerak emas.")
        return

    tomorrow_tasks = data.get("tomorrow_tasks", [])
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    if tomorrow_tasks:
        for item in tomorrow_tasks:
            if isinstance(item, dict):
                task_text = item["text"]
                task_time = item.get("time", "09:00")
            else:
                task_text = str(item)
                task_time = "09:00"
            task = {
                "id": len(data["tasks"]) + 1,
                "text": task_text,
                "done": False,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "remind_at": f"{tomorrow_date} {task_time}",
                "reminded": False
            }
            data["tasks"].append(task)

        task_list = "\n".join([
            f"• {item['text']} — ⏰ {item.get('time', '09:00')}" if isinstance(item, dict) else f"• {item}"
            for item in tomorrow_tasks
        ])
        await update.message.reply_text(
            f"🌙 *Kechqurun hisoboti tugadi!*\n\n"
            f"📋 Ertangi vazifalar:\n{task_list}\n\n"
            f"Yaxshi uxlang! 😴",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🌙 Yaxshi uxlang! 😴")

    data["tomorrow_tasks"] = []
    data["evening_state"] = {"state": "done"}
    save_data(data)

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    await start_evening_report(context.bot, update.effective_chat.id)

# ========================
# ERTALAB REJA
# ========================
async def send_morning_plan(bot, chat_id):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_tasks = [
        t for t in data["tasks"]
        if not t["done"] and (
            not t.get("remind_at") or t.get("remind_at", "").startswith(today)
        )
    ]

    if not today_tasks:
        await bot.send_message(
            chat_id=chat_id,
            text="☀️ *Xayrli tong, Nodirbek!*\n\nBugun uchun maxsus vazifa yo'q.\n/vazifa — yangi vazifa qo'shing",
            parse_mode="Markdown"
        )
        return

    task_list = "\n".join([
        f"{i+1}. {t['text']}" + (f" — ⏰ {t['remind_at'].split(' ')[1]}" if t.get("remind_at") else "")
        for i, t in enumerate(today_tasks)
    ])

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        tasks_str = "\n".join([t["text"] for t in today_tasks])
        motivation = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=f"Startapchi yigitning bugungi vazifalari: {tasks_str}\n\nQisqa (1-2 jumla) motivatsion so'z va eng muhim vazifadan boshlash maslahatini o'zbek tilida ber."
        ).text
    except:
        motivation = "Samarali kun bo'lsin! 💪"

    await bot.send_message(
        chat_id=chat_id,
        text=f"☀️ *Xayrli tong, Nodirbek!*\n\n"
             f"📋 *Bugungi {len(today_tasks)} ta vazifa:*\n\n{task_list}\n\n"
             f"🤖 {motivation}",
        parse_mode="Markdown"
    )

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

            if now.hour == MORNING_HOUR and now.minute < 2 and morning_sent_today != today:
                for chat_id in data.get("chat_ids", []):
                    await send_morning_plan(bot, chat_id)
                morning_sent_today = today

            if now.hour == EVENING_HOUR and now.minute < 2 and evening_sent_today != today:
                for chat_id in data.get("chat_ids", []):
                    await start_evening_report(bot, chat_id)
                evening_sent_today = today

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
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"⏰ *30 daqiqada uchrashuv!*\n\n📌 {event['name']}\n🗓 {event['datetime']}",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
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
                        except:
                            pass
                    event["reminded_5"] = True
                    changed = True

            if changed:
                save_data(data)

        except Exception as e:
            logger.error(f"Loop xato: {e}")

        await asyncio.sleep(60)

# ========================
# CALLBACK HANDLER
# ========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    if query.data == "menu_tasks":
        pending = [t for t in data["tasks"] if not t["done"]]
        done_count = sum(1 for t in data["tasks"] if t["done"])
        if not pending:
            text = "📋 *Vazifalar yo'q*\n\n/vazifa <matn> — yangi qo'shing"
        else:
            text = f"📋 *Bajarilmaganlar ({len(pending)} ta):*\n\n"
            for t in pending:
                remind = f"\n   ⏰ {t['remind_at']}" if t.get("remind_at") else ""
                text += f"⬜ *{t['id']}.* {t['text']}{remind}\n"
            if done_count:
                text += f"\n✅ Bajarilganlar: {done_count} ta"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_events":
        now = datetime.now()
        upcoming = [e for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now]
        if not upcoming:
            text = "📅 *Kelayotgan uchrashuvlar yo'q*\n\n/jadval YYYY-MM-DD HH:MM nomi"
        else:
            text = "📅 *Kelayotgan uchrashuvlar:*\n\n"
            for e in upcoming:
                text += f"🔜 *{e['id']}.* {e['name']}\n   🗓 {e['datetime']}\n\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_ai":
        await query.edit_message_text(
            "🤖 *AI Maslahat:*\n\n"
            "*/ai <savol>* — Istalgan savol\n"
            "*/tahlil* — Vazifalarni tahlil qilish\n\n"
            "Misol:\n"
            "• /ai Bugun qaysi vazifadan boshlasam?\n"
            "• /ai Presentation qanday tayyorlanadi?\n"
            "• /ai Meni motivatsiya qil",
            parse_mode="Markdown"
        )

    elif query.data == "menu_stats":
        pending = [t for t in data["tasks"] if not t["done"]]
        done = [t for t in data["tasks"] if t["done"]]
        now = datetime.now()
        upcoming = [e for e in data["events"] if datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M") >= now]
        total = len(data["tasks"])
        percent = int(len(done) / total * 100) if total > 0 else 0
        bar = "█" * (percent // 10) + "░" * (10 - percent // 10)

        await query.edit_message_text(
            f"📊 *Statistika:*\n\n"
            f"✅ Bajarilgan: {len(done)} ta\n"
            f"⬜ Bajarilmagan: {len(pending)} ta\n"
            f"📈 Samaradorlik: {percent}%\n"
            f"[{bar}]\n\n"
            f"📅 Kelayotgan uchrashuvlar: {len(upcoming)} ta\n"
            f"🤖 AI: Gemini 3 Flash",
            parse_mode="Markdown"
        )

    elif query.data == "menu_today":
        today = datetime.now().strftime("%Y-%m-%d")
        today_list = [
            t for t in data["tasks"]
            if not t["done"] and (
                not t.get("remind_at") or t.get("remind_at", "").startswith(today)
            )
        ]
        if not today_list:
            text = "☀️ *Bugun uchun vazifalar yo'q!*\n\n/vazifa — yangi qo'shing"
        else:
            text = f"☀️ *Bugungi vazifalar ({len(today_list)} ta):*\n\n"
            for i, t in enumerate(today_list, 1):
                time_str = f" ⏰ {t['remind_at'].split(' ')[1]}" if t.get("remind_at") else ""
                text += f"{i}. {t['text']}{time_str}\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "menu_report":
        await query.edit_message_text("🌙 Kechqurun hisoboti boshlanmoqda...")
        await start_evening_report(context.bot, query.message.chat_id)

# ========================
# XABAR HANDLER
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    state = data.get("evening_state", {})

    if state.get("state") == "waiting_done":
        if await handle_evening_done(update, context):
            return
    elif state.get("state") == "waiting_postpone":
        if await handle_evening_postpone(update, context):
            return
    elif state.get("state") in ["waiting_tomorrow", "waiting_tomorrow_time"]:
        if await handle_tomorrow_input(update, context):
            return

    text = update.message.text
    if any(w in text.lower() for w in ["salom", "assalomu", "hi", "hello"]):
        await update.message.reply_text(
            "👋 Salom! /start — menyu, /help — barcha buyruqlar\n\n🤖 Savolingiz bo'lsa yozing!"
        )
    else:
        msg = await update.message.reply_text("🤔 O'ylamoqda...")
        ctx = get_context_for_ai()
        answer = await ask_gemini(text, ctx)
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
    app.add_handler(CommandHandler("tahlil", ai_analyze))
    app.add_handler(CommandHandler("vazifa", add_task))
    app.add_handler(CommandHandler("vazifalar", list_tasks))
    app.add_handler(CommandHandler("bajarildi", complete_task))
    app.add_handler(CommandHandler("ochir", delete_task))
    app.add_handler(CommandHandler("bugun", today_tasks))
    app.add_handler(CommandHandler("jadval", add_event))
    app.add_handler(CommandHandler("uchrashuvlar", list_events))
    app.add_handler(CommandHandler("hisobot", manual_report))
    app.add_handler(CommandHandler("tayyor", finish_tomorrow))
    app.add_handler(CommandHandler("bekor", cancel))
    app.add_handler(reminder_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot ishga tushdi! Barcha funksiyalar yoqildi.")

    async with app:
        await app.start()
        await app.updater.start_polling()
        await main_loop(app.bot)

if __name__ == "__main__":
    asyncio.run(main())
