#!/usr/bin/env python3
import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from google import genai
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
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

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "tasks": [],
        "events": [],
        "chat_ids": [],
        "conversation_state": {},
        "pending_check": None
    }

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
async def ask_gemini(messages: list, system: str = "") -> str:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        if not system:
            system = (
                "Sen Nodirbek ismli o'zbek startapchisining shaxsiy aqlli assistentisan. "
                "Unga do'stona, qisqa va aniq o'zbek tilida javob ber. "
                "Emoji ishlatib yoz. Rasmiy bo'lma, do'st kabi gapir."
            )
        
        full_prompt = system + "\n\n"
        for msg in messages:
            role = "Nodirbek" if msg["role"] == "user" else "Assistant"
            full_prompt += f"{role}: {msg['content']}\n"
        full_prompt += "Assistant:"
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=full_prompt
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        return "Hozir javob bera olmayapman, keyinroq urinib ko'ring 🙏"

def get_tasks_context(data):
    pending = [t for t in data["tasks"] if not t["done"]]
    done = [t for t in data["tasks"] if t["done"]]
    today = datetime.now().strftime("%Y-%m-%d")
    today_tasks = [t for t in pending if t.get("remind_at", "").startswith(today)]
    
    ctx = f"Bajarilmagan vazifalar ({len(pending)} ta):\n"
    for t in pending[:10]:
        remind = f" (eslatma: {t['remind_at']})" if t.get("remind_at") else ""
        ctx += f"- ID:{t['id']} {t['text']}{remind}\n"
    ctx += f"\nBajarilgan vazifalar: {len(done)} ta\n"
    ctx += f"Bugungi vazifalar: {len(today_tasks)} ta\n"
    return ctx

# ========================
# SMART MESSAGE HANDLER
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    register_chat(chat_id)
    
    data = load_data()
    state = data.get("conversation_state", {})
    tasks_ctx = get_tasks_context(data)
    
    # Conversation history (oxirgi 5 ta xabar)
    history = state.get("history", [])
    history.append({"role": "user", "content": user_text})
    if len(history) > 10:
        history = history[-10:]
    
    # System prompt - barcha ma'lumotlar bilan
    system = f"""Sen Nodirbek ismli o'zbek startapchisining shaxsiy aqlli assistentisan.
    
Uning hozirgi vaziyati:
{tasks_ctx}

Sening vazifalaringiz:
1. Foydalanuvchi vazifa qo'shmoqchi bo'lsa - uni TASK_ADD:[matn]|[sana YYYY-MM-DD]|[vaqt HH:MM] formatida javob ber
2. Vazifani bajarildi desa - TASK_DONE:[id] formatida javob ber  
3. Vazifani o'chirmoqchi bo'lsa - TASK_DELETE:[id] formatida javob ber
4. Vazifalarni ko'rmoqchi bo'lsa - TASK_LIST formatida javob ber
5. Boshqa savollar uchun - oddiy do'stona javob ber

Muhim: Har doim avval do'stona javob yoz, keyin agar kerak bo'lsa quyida action yoz.
Masalan:
"Yaxshi, qo'shib qo'ydim! ✅
TASK_ADD:Hisobot yozish|2026-05-08|10:00"

Vaqt belgilashda foydalanuvchi aytmasa - so'ra.
Bugun: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({datetime.now().strftime('%A')})"""

    # AI dan javob olish
    thinking_msg = await update.message.reply_text("💭")
    
    try:
        ai_response = await ask_gemini(history, system)
    except Exception as e:
        await thinking_msg.edit_text("Hozir muammo bor, keyinroq urinib ko'ring 🙏")
        return
    
    # Action larni ajratib olish
    display_text = ai_response
    actions_text = ""
    
    for action in ["TASK_ADD:", "TASK_DONE:", "TASK_DELETE:", "TASK_LIST"]:
        if action in ai_response:
            parts = ai_response.split(action, 1)
            display_text = parts[0].strip()
            actions_text = action + parts[1].split("\n")[0] if len(parts) > 1 else action
            break
    
    # Actionlarni bajarish
    action_result = ""
    if "TASK_ADD:" in actions_text:
        try:
            params = actions_text.replace("TASK_ADD:", "").strip().split("|")
            task_text = params[0].strip()
            remind_at = None
            if len(params) >= 3:
                date_str = params[1].strip()
                time_str = params[2].strip()
                remind_at = f"{date_str} {time_str}"
            
            task = {
                "id": len(data["tasks"]) + 1,
                "text": task_text,
                "done": False,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "remind_at": remind_at,
                "reminded": False
            }
            data["tasks"].append(task)
            save_data(data)
            action_result = f"\n📌 Vazifa #{task['id']} qo'shildi"
            if remind_at:
                action_result += f" | ⏰ {remind_at}"
        except Exception as e:
            logger.error(f"Task add xato: {e}")
    
    elif "TASK_DONE:" in actions_text:
        try:
            task_id = int(actions_text.replace("TASK_DONE:", "").strip())
            for t in data["tasks"]:
                if t["id"] == task_id:
                    t["done"] = True
                    save_data(data)
                    action_result = f"\n✅ #{task_id} bajarildi!"
                    break
        except Exception as e:
            logger.error(f"Task done xato: {e}")
    
    elif "TASK_DELETE:" in actions_text:
        try:
            task_id = int(actions_text.replace("TASK_DELETE:", "").strip())
            before = len(data["tasks"])
            data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
            if len(data["tasks"]) < before:
                save_data(data)
                action_result = f"\n🗑️ #{task_id} o'chirildi"
        except Exception as e:
            logger.error(f"Task delete xato: {e}")
    
    elif "TASK_LIST" in actions_text:
        pending = [t for t in data["tasks"] if not t["done"]]
        if pending:
            action_result = "\n\n📋 Vazifalar:\n"
            for t in pending:
                remind = f" ⏰{t['remind_at']}" if t.get("remind_at") else ""
                action_result += f"#{t['id']} {t['text']}{remind}\n"
        else:
            action_result = "\n\n📋 Hozircha vazifalar yo'q!"
    
    # Javobni yuborish
    final_text = display_text + action_result if display_text else action_result
    if not final_text.strip():
        final_text = ai_response
    
    await thinking_msg.edit_text(final_text)
    
    # Historyni yangilash
    history.append({"role": "assistant", "content": display_text or ai_response})
    data["conversation_state"]["history"] = history[-10:]
    save_data(data)

# ========================
# VAZIFA VAQTI KELGANDA
# ========================
async def check_task_and_notify(bot, task, chat_id):
    """Vazifa vaqti kelganda AI orqali so'rash"""
    data = load_data()
    
    # AI orqali so'rash
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"Nodirbek startapchiga '{task['text']}' vazifasi vaqti keldi. Do'stona o'zbek tilida qisqa so'ra, bajardimi yo'qmi deb. Ha/Yo'q deb javob bersin."
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        question = response.text.strip()
    except:
        question = f"⏰ Vaqti keldi!\n\n📌 *{task['text']}*\n\nBajardingizmi?"
    
    await bot.send_message(
        chat_id=chat_id,
        text=f"⏰ *Vazifa eslatmasi!*\n\n{question}",
        parse_mode="Markdown"
    )
    
    # State ni saqlash - javob kutish uchun
    data["pending_check"] = {
        "task_id": task["id"],
        "task_text": task["text"],
        "chat_id": chat_id,
        "state": "waiting_answer"
    }
    task["reminded"] = True
    save_data(data)

async def handle_task_check_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vazifa javobini AI orqali qayta ishlash"""
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip().lower()
    data = load_data()
    pending = data.get("pending_check")
    
    if not pending or pending.get("chat_id") != chat_id:
        return False
    
    task_text = pending.get("task_text", "")
    task_id = pending.get("task_id")
    
    # AI orqali javobni tahlil qilish
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        system = f"""Nodirbek '{task_text}' vazifasi haqida javob berdi: '{user_text}'
        
Javobni tahlil qil va quyidagi formatda javob ber:
- Agar bajardi: DONE
- Agar bajarmadi yoki kechiktirmoqchi: POSTPONE  
- Agar yordam kerak: HELP

Faqat bitta so'z yoz: DONE, POSTPONE yoki HELP"""
        
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=system)
        intent = response.text.strip().upper()
    except:
        if any(w in user_text for w in ["ha", "yes", "qildim", "bajardim", "bo'ldi"]):
            intent = "DONE"
        else:
            intent = "POSTPONE"
    
    if "DONE" in intent:
        # Bajarildi
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                break
        data["pending_check"] = None
        save_data(data)
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            praise = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"Nodirbek '{task_text}' vazifasini bajardi. Qisqa (1 jumla) tabrikla va motivatsiya ber."
            ).text.strip()
        except:
            praise = "Zo'r! Davom eting! 💪"
        
        await update.message.reply_text(f"🎉 {praise}")
        return True
    
    elif "POSTPONE" in intent:
        # Kechiktirmoqchi
        data["pending_check"]["state"] = "waiting_postpone"
        save_data(data)
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            ask = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"Nodirbek '{task_text}' vazifasini bajara olmadi. Do'stona so'ra - qaysi vaqtga ko'chiray deb. Qisqa yoz."
            ).text.strip()
        except:
            ask = "Qaysi vaqtga ko'chirib qo'yay? ⏰"
        
        await update.message.reply_text(ask)
        return True
    
    elif "HELP" in intent:
        # Yordam kerak
        data["pending_check"] = None
        save_data(data)
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            help_text = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"Nodirbek '{task_text}' vazifasini bajarishda muammo bor. Qisqa (3-4 qadam) amaliy maslahat ber o'zbek tilida."
            ).text.strip()
        except:
            help_text = "Keling birga hal qilamiz! Nima qiyin bo'lyapti?"
        
        await update.message.reply_text(f"💡 {help_text}")
        return True
    
    return False

async def handle_postpone_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ko'chirish vaqtini qayta ishlash"""
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    data = load_data()
    pending = data.get("pending_check")
    
    if not pending or pending.get("state") != "waiting_postpone":
        return False
    
    task_id = pending.get("task_id")
    task_text = pending.get("task_text", "")
    
    # AI orqali vaqtni tushunish
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        parse_prompt = f"""Foydalanuvchi vaqt aytdi: '{user_text}'
Bugun: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Ertaga: {tomorrow}

Vaqtni YYYY-MM-DD HH:MM formatida yoz. Faqat shu formatda, boshqa narsa yozma.
Agar tushunmasa: {tomorrow} 09:00"""
        
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=parse_prompt)
        new_time = response.text.strip()
        
        # Validatsiya
        datetime.strptime(new_time, "%Y-%m-%d %H:%M")
    except:
        new_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") + " 09:00"
    
    # Vazifani yangilash
    for t in data["tasks"]:
        if t["id"] == task_id:
            t["remind_at"] = new_time
            t["reminded"] = False
            break
    
    data["pending_check"] = None
    save_data(data)
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        confirm = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=f"'{task_text}' vazifasi {new_time} ga ko'chirildi. Qisqa tasdiqlash xabari yoz va biroz motivatsiya ber."
        ).text.strip()
    except:
        confirm = f"✅ Ko'chirildi: {new_time}"
    
    await update.message.reply_text(confirm)
    return True

# ========================
# START COMMAND
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    data = load_data()
    data["conversation_state"] = {"history": []}
    save_data(data)
    
    await update.message.reply_text(
        "👋 Salom, Nodirbek!\n\n"
        "Men sizning aqlli assistentingizman 🤖\n\n"
        "Menga oddiygina yozing:\n"
        "• \"Bugun soat 15:00 da Qodir aka bilan uchrashuv bor\"\n"
        "• \"Vazifalarimni ko'rsat\"\n"
        "• \"Hisobot yozishni bajardim\"\n"
        "• \"Marketingni qanday o'rganaman?\"\n\n"
        "Xuddi do'stingizga yozganday yozing, men tushunaman! 💪"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 Menga shunchaki yozing:\n\n"
        "📌 *Vazifa qo'shish:*\n"
        "\"Ertaga soat 10 da hisobot yozish kerak\"\n\n"
        "✅ *Bajarildi deb belgilash:*\n"
        "\"Hisobot yozishni bajardim\"\n\n"
        "📋 *Vazifalarni ko'rish:*\n"
        "\"Vazifalarimni ko'rsat\"\n\n"
        "🤖 *Maslahat:*\n"
        "\"Targetingni qanday yaxshilayman?\"\n\n"
        "Boshqa hamma narsani ham oddiygina yozing! 😊",
        parse_mode="Markdown"
    )

# ========================
# KECHQURUN HISOBOT
# ========================
async def start_evening_report(bot, chat_id):
    data = load_data()
    pending = [t for t in data["tasks"] if not t["done"]]
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        if pending:
            task_list = "\n".join([f"- {t['text']}" for t in pending[:7]])
            prompt = f"""Nodirbek startapchining kechqurun hisoboti vaqti keldi (23:00).
Bajarilmagan vazifalar:
{task_list}

Do'stona o'zbek tilida:
1. Salomlash
2. Bajarilmagan vazifalarni sanab, qaysilarini bajardi deb so'ra (raqam bilan)
Qisqa yoz."""
        else:
            prompt = "Nodirbek kechqurun hisobot vaqti. Barcha vazifalar bajarilgan. Tabrikla va ertangi reja so'ra."
        
        message = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt).text.strip()
    except:
        if pending:
            task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(pending)])
            message = f"🌙 Kechqurun hisoboti!\n\nBajarilmagan vazifalar:\n{task_list}\n\nQaysilarini bajardingiz? (raqamlar bilan)"
        else:
            message = "🌙 Zo'r kun! Barcha vazifalar bajarildi! 🎉\n\nErtaga nima rejalashtiryapsiz?"
    
    await bot.send_message(chat_id=chat_id, text=message)
    
    data["evening_state"] = {
        "state": "waiting_done" if pending else "waiting_tomorrow",
        "pending_ids": [t["id"] for t in pending],
        "chat_id": chat_id
    }
    save_data(data)

async def handle_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kechqurun hisobot jarayoni"""
    data = load_data()
    estate = data.get("evening_state", {})
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    
    if estate.get("chat_id") != chat_id:
        return False
    
    if estate.get("state") == "waiting_done":
        pending_ids = estate.get("pending_ids", [])
        pending = [t for t in data["tasks"] if t["id"] in pending_ids]
        
        # AI orqali tushunish
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(pending)])
            parse = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"Vazifalar:\n{task_list}\n\nFoydalanuvchi: '{user_text}'\n\nQaysi raqamli vazifalar bajarildi? Faqat raqamlarni vergul bilan yoz. Agar barchasi bo'lsa: ALL. Agar hech biri bo'lsa: NONE"
            ).text.strip()
        except:
            parse = "NONE"
        
        done_ids = []
        if "ALL" in parse.upper():
            done_ids = pending_ids[:]
        elif "NONE" not in parse.upper():
            try:
                nums = [int(x.strip()) for x in parse.replace(",", " ").split() if x.strip().isdigit()]
                for num in nums:
                    if 1 <= num <= len(pending):
                        done_ids.append(pending[num-1]["id"])
            except:
                pass
        
        for t in data["tasks"]:
            if t["id"] in done_ids:
                t["done"] = True
        
        not_done = [t for t in pending if t["id"] not in done_ids]
        
        if not_done:
            task_list = "\n".join([f"• {t['text']}" for t in not_done])
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                ask = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=f"Bajarilmagan vazifalar:\n{task_list}\nQaysi kunga ko'chirib qo'yish kerakligini so'ra. Qisqa."
                ).text.strip()
            except:
                ask = f"Quyidagilar bajarilmadi:\n{task_list}\n\nQaysi kunga o'tkazay?"
            
            await update.message.reply_text(ask)
            data["evening_state"] = {
                "state": "waiting_postpone",
                "not_done_ids": [t["id"] for t in not_done],
                "chat_id": chat_id
            }
        else:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                praise = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents="Barcha vazifalar bajarildi! Tabrikla va ertangi reja so'ra."
                ).text.strip()
            except:
                praise = "🎉 Ajoyib! Ertaga nima rejalashtiryapsiz?"
            
            await update.message.reply_text(praise)
            data["evening_state"] = {"state": "waiting_tomorrow", "chat_id": chat_id}
        
        save_data(data)
        return True
    
    elif estate.get("state") == "waiting_postpone":
        not_done_ids = estate.get("not_done_ids", [])
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            parse = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"Foydalanuvchi: '{user_text}'. Bugun: {datetime.now().strftime('%Y-%m-%d')}. Ertaga: {tomorrow}. Sanani YYYY-MM-DD formatida yoz."
            ).text.strip()
            datetime.strptime(parse, "%Y-%m-%d")
            new_date = parse
        except:
            new_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        for t in data["tasks"]:
            if t["id"] in not_done_ids:
                t["remind_at"] = f"{new_date} 09:00"
                t["reminded"] = False
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            confirm = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"{new_date} ga ko'chirildi. Tasdiqlash va ertangi reja so'ra. Qisqa."
            ).text.strip()
        except:
            confirm = f"✅ {new_date} ga ko'chirildi!\n\nErtaga nima rejalashtiryapsiz?"
        
        await update.message.reply_text(confirm)
        data["evening_state"] = {"state": "waiting_tomorrow", "chat_id": chat_id}
        save_data(data)
        return True
    
    elif estate.get("state") == "waiting_tomorrow":
        # Ertangi vazifalarni qabul qilish
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            parse = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"""Foydalanuvchi ertangi vazifa yozdi: '{user_text}'
Ertaga: {tomorrow}

Vazifani ajrat va vaqtini tushun. JSON formatida yoz:
{{"task": "vazifa matni", "time": "HH:MM yoki null"}}
Faqat JSON, boshqa narsa yozma."""
            ).text.strip()
            
            import re
            json_match = re.search(r'\{.*\}', parse, re.DOTALL)
            if json_match:
                task_data = json.loads(json_match.group())
                task_text = task_data.get("task", user_text)
                task_time = task_data.get("time") or "09:00"
            else:
                task_text = user_text
                task_time = "09:00"
        except:
            task_text = user_text
            task_time = "09:00"
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        task = {
            "id": len(data["tasks"]) + 1,
            "text": task_text,
            "done": False,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "remind_at": f"{tomorrow} {task_time}",
            "reminded": False
        }
        data["tasks"].append(task)
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            confirm = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"'{task_text}' ({task_time}) qo'shildi. Yana vazifa so'ra yoki tugatish uchun 'tayyor' deb yozsin de. Qisqa."
            ).text.strip()
        except:
            confirm = f"✅ Qo'shildi: {task_text} ({task_time})\n\nYana bor? Yo'q bo'lsa 'tayyor' yozing"
        
        await update.message.reply_text(confirm)
        save_data(data)
        return True
    
    return False

async def finish_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    estate = data.get("evening_state", {})
    
    if estate.get("state") not in ["waiting_tomorrow", "waiting_postpone"]:
        await update.message.reply_text("Hozir bu buyruq kerak emas 🙂")
        return
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        goodbye = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents="Kechqurun hisobot tugadi. Xayrli tun va yaxshi uxlash tilak bildirmasi yoz. Qisqa, 1-2 jumla."
        ).text.strip()
    except:
        goodbye = "🌙 Yaxshi uxlang! Ertaga kuchli bo'lsin! 💪"
    
    await update.message.reply_text(goodbye)
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
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        if today_tasks:
            task_list = "\n".join([
                f"- {t['text']}" + (f" ({t['remind_at'].split(' ')[1]})" if t.get("remind_at") else "")
                for t in today_tasks
            ])
            prompt = f"""Nodirbek startapchiga ertalab (08:00) xabar yoz.
Bugungi vazifalar:
{task_list}

Do'stona salomlash, vazifalarni ko'rsat va eng muhimidan boshlash maslahatini ber.
Motivatsion yoz. O'zbek tilida."""
        else:
            prompt = "Nodirbek startapchiga ertalab xabar yoz. Bugun vazifalar yo'q. Yangi kun uchun motivatsiya ber va vazifa qo'shishni taklif et."
        
        message = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt).text.strip()
    except:
        if today_tasks:
            task_list = "\n".join([f"• {t['text']}" for t in today_tasks])
            message = f"☀️ Xayrli tong, Nodirbek!\n\nBugungi vazifalar:\n{task_list}\n\nSamarali kun bo'lsin! 💪"
        else:
            message = "☀️ Xayrli tong! Bugun yangi imkoniyatlar kuni! 🚀"
    
    await bot.send_message(chat_id=chat_id, text=message)

# ========================
# ASOSIY LOOP
# ========================
async def main_loop(bot):
    morning_sent = None
    evening_sent = None
    
    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            data = load_data()
            
            # Ertalab 08:00
            if now.hour == MORNING_HOUR and now.minute < 2 and morning_sent != today:
                for chat_id in data.get("chat_ids", []):
                    await send_morning_plan(bot, chat_id)
                morning_sent = today
            
            # Kechqurun 23:00
            if now.hour == EVENING_HOUR and now.minute < 2 and evening_sent != today:
                for chat_id in data.get("chat_ids", []):
                    await start_evening_report(bot, chat_id)
                evening_sent = today
            
            # Vazifa eslatmalari
            changed = False
            for task in data["tasks"]:
                if task.get("remind_at") and not task.get("reminded") and not task["done"]:
                    remind_dt = datetime.strptime(task["remind_at"], "%Y-%m-%d %H:%M")
                    diff = (remind_dt - now).total_seconds() / 60
                    if -2 <= diff <= 2:
                        for chat_id in data.get("chat_ids", []):
                            await check_task_and_notify(bot, task, chat_id)
                        changed = True
            
            # Uchrashuv eslatmalari
            for event in data.get("events", []):
                try:
                    event_dt = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
                    diff = (event_dt - now).total_seconds() / 60
                    if 28 <= diff <= 32 and not event.get("reminded_30"):
                        for chat_id in data.get("chat_ids", []):
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"⏰ *30 daqiqada uchrashuv!*\n\n📌 {event['name']}\n🗓 {event['datetime']}",
                                parse_mode="Markdown"
                            )
                        event["reminded_30"] = True
                        changed = True
                    if 3 <= diff <= 7 and not event.get("reminded_5"):
                        for chat_id in data.get("chat_ids", []):
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"🔔 *5 daqiqada uchrashuv!*\n\n📌 {event['name']}",
                                parse_mode="Markdown"
                            )
                        event["reminded_5"] = True
                        changed = True
                except:
                    pass
            
            if changed:
                save_data(data)
        
        except Exception as e:
            logger.error(f"Loop xato: {e}")
        
        await asyncio.sleep(60)

# ========================
# UNIVERSAL MESSAGE HANDLER
# ========================
async def universal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip().lower()
    data = load_data()
    
    # Tayyor buyrug'i
    if user_text in ["tayyor", "/tayyor", "tamom", "bo'ldi"]:
        await finish_evening(update, context)
        return
    
    # Kechqurun hisobot jarayoni
    estate = data.get("evening_state", {})
    if estate.get("state") in ["waiting_done", "waiting_postpone", "waiting_tomorrow"] and estate.get("chat_id") == chat_id:
        if await handle_evening(update, context):
            return
    
    # Vazifa tekshiruv jarayoni
    pending_check = data.get("pending_check")
    if pending_check and pending_check.get("chat_id") == chat_id:
        if pending_check.get("state") == "waiting_postpone":
            if await handle_postpone_response(update, context):
                return
        elif await handle_task_check_response(update, context):
            return
    
    # Oddiy AI suhbat
    await handle_message(update, context)

# ========================
# MAIN
# ========================
async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hisobot", manual_report))
    app.add_handler(CommandHandler("tayyor", finish_evening))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, universal_handler))
    
    print("🤖 Aqlli bot ishga tushdi!")
    
    async with app:
        await app.start()
        await app.updater.start_polling()
        await main_loop(app.bot)

if __name__ == "__main__":
    asyncio.run(main())
