import sys
import unicodedata
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
import os
import re
import json
import sqlite3
import logging
import requests
from telebot import TeleBot, apihelper, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Prevent socket hangs on Windows
apihelper.READ_TIMEOUT = 25
apihelper.CONNECT_TIMEOUT = 15
apihelper.RETRY_ON_ERROR = True

# ----------------- CONFIGURATION -----------------
TELEGRAM_BOT_TOKEN = "8613504216:AAEn_PHleVmn7BAnBPKhz8qpwI-5t-h2LxQ"
import random

GROQ_API_KEY = "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"
GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b"
]

OPENROUTER_KEYS = [
    "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",
    "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",
    "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",
    "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",
]
GEMINI_API_KEY = "AIzaSyCKjp_GVr-ntsYT-bZGSd-Gn_30DeEzrs8"

BOT_NAMES = ["flash"]
CHANNEL_USERNAME = "rm6785dumppAss"
CHANNEL_ID = -1003087244808

OPENROUTER_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/free"
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.8-flash"
]

CONTEXT_MESSAGE_LIMIT = 15
ROMS_DATABASE_FILE = "roms_database.json"
BOT_START_TIME = time.time()

# ----------------- ROM COMPARISON KNOWLEDGE BASE -----------------
ROM_PATTERNS = [
    ("axion", r"\b(axion|axionos|axn)\b"),
    ("pixelos", r"\b(pixel|pixelos|pos|pixelrom)\b"),
    ("crdroid", r"\b(crdroid|cr\s*droid|crd|crdroidos)\b"),
    ("lineage", r"\b(lineage|lineageos|lienage|lienageos|los)\b"),
    ("derpfest", r"\b(derp|derpfest|derpfestos)\b"),
    ("evolution", r"\b(evo|evox|evolution|evolutionx|evolutionos)\b"),
    ("rising", r"\b(rising|risingos)\b"),
    ("superior", r"\b(superior|superioros)\b"),
    ("voltage", r"\b(voltage|voltageos)\b"),
    ("bliss", r"\b(bliss|blissroms|blissos)\b"),
    ("cherish", r"\b(cherish|cherishos)\b"),
    ("matrixx", r"\b(matrixx|matrix)\b")
]

def extract_roms_from_query(raw_text):
    """
    Super-smart, typo-tolerant ROM extractor:
    - Handles 'axionos', 'lineageos', 'lienageos'
    - Handles spaces: 'axion os', 'lineage os', 'os axion'
    - Handles case: 'AxionOS', 'Lineage OS'
    - Strips 'vs', 'and', 'with', '&'
    """
    clean = re.sub(r'^[/\.!](?:compare)(?:@\w+)?\s*', '', raw_text.strip(), flags=re.IGNORECASE).lower()
    clean = re.sub(r'\b(vs|and|aur|with|v/s|&)\b', ' ', clean)
    clean = re.sub(r'\bos\b', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    found = []
    # 1. Direct Regex Match
    for rom_key, pat in ROM_PATTERNS:
        if re.search(pat, clean):
            if rom_key not in found:
                found.append(rom_key)

    # 2. Fuzzy / Typo / Attached 'os' cleanup
    if len(found) < 2:
        tokens = clean.split()
        for tok in tokens:
            t = re.sub(r'[^a-z0-9]', '', tok)
            if t.endswith('os') and len(t) > 4:
                t = t[:-2]
            if t.startswith('os') and len(t) > 4:
                t = t[2:]

            for rom_key, _ in ROM_PATTERNS:
                if rom_key not in found:
                    if rom_key.startswith(t) and len(t) >= 3:
                        found.append(rom_key)
                    elif t.startswith(rom_key[:4]) and len(t) >= 4:
                        found.append(rom_key)
                    elif 'lienag' in t or 'lineag' in t:
                        if 'lineage' not in found:
                            found.append('lineage')

    return found[:2]

ROM_PROFILES = {
    "axion": {
        "name": "Axion OS",
        "type": "Gaming & Customization",
        "customization": "9.5/10 (Deep Tweaks & Theming)",
        "perf": "9.5/10 (Top FPS, Thermal Tweaks)",
        "battery": "8/10 (Decent for daily gaming)",
        "features": "Gaming Mode, Custom QS styles, RUI2 & RUI3 builds",
        "verdict": "Hardcore Gamers aur Customization Lovers ke liye No. 1 choice!"
    },
    "pixelos": {
        "name": "PixelOS",
        "type": "Pure Pixel Experience",
        "customization": "6/10 (Clean, minimal Pixel look)",
        "perf": "8.5/10 (Smooth 90Hz)",
        "battery": "9/10 (Solid daily endurance)",
        "features": "Unlimited Google Photos, Pixel Launcher, Zero Bloat",
        "verdict": "Clean, smooth aur stable daily driver ke liye best!"
    },
    "crdroid": {
        "name": "crDroid",
        "type": "Max Customization King",
        "customization": "10/10 (Infinite crDroid Settings)",
        "perf": "8.5/10 (Stable & Snappy)",
        "battery": "8.5/10 (Good standby)",
        "features": "Control har ek pixel pe, LineageOS stability base",
        "verdict": "Har cheez customize karne ke shaukeen logon ke liye!"
    },
    "lineage": {
        "name": "LineageOS",
        "type": "Pure Open Source",
        "customization": "4/10 (Minimal AOSP Baseline)",
        "perf": "8.5/10 (Lightweight & responsive)",
        "battery": "9.5/10 (Maximum standby)",
        "features": "Zero telemetry, lightweight, rock solid stability",
        "verdict": "Privacy aur maximum battery life ke liye!"
    },
    "derpfest": {
        "name": "DerpFest",
        "type": "Aesthetic & Modern",
        "customization": "9/10 (DerpSpace Goodies)",
        "perf": "9/10 (Fluid UI & responsive)",
        "battery": "8/10 (Moderate)",
        "features": "Sleek UI fonts, lockscreen clock styles, modern icons",
        "verdict": "Sundar UI aur smooth animations ke liye!"
    },
    "evolution": {
        "name": "Evolution X",
        "type": "Pixel + Heavy Tweaks",
        "customization": "9.5/10 (The Evolver Hub)",
        "perf": "9/10 (Great performance)",
        "battery": "8/10 (Good)",
        "features": "Pixel look ke sath crDroid jaisi customization",
        "verdict": "Pixel Look aur bhar-bhar ke features dono chahiye toh!"
    },
    "rising": {
        "name": "RisingOS",
        "type": "HyperOS / iOS Hybrid",
        "customization": "9.5/10 (Personalization Labs)",
        "perf": "8.5/10 (Smooth)",
        "battery": "8/10 (Good)",
        "features": "Unique QS headers, custom volume panels, lockscreens",
        "verdict": "Modern iOS/HyperOS style aesthetic lovers ke liye!"
    },
    "superior": {
        "name": "SuperiorOS",
        "type": "Balanced Performance",
        "customization": "8/10 (Superior Lab)",
        "perf": "9/10 (Very Snappy)",
        "battery": "8.5/10 (Great daily backup)",
        "features": "Clean AOSP base with essential tweaks only",
        "verdict": "Bina kisi lag ke balance performance chahiye toh!"
    },
    "voltage": {
        "name": "VoltageOS",
        "type": "Lightweight & Battery Focused",
        "customization": "7.5/10 (Power Hub)",
        "perf": "8.5/10 (Smooth)",
        "battery": "9.5/10 (Outstanding Battery)",
        "features": "Minimalist, power-efficient, quick app opening",
        "verdict": "Heavy battery backup aur clean setup ke liye!"
    }
}


def get_uptime_string():
    uptime_sec = int(time.time() - BOT_START_TIME)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)
DB_PATH = "flash_memory.db"
# -------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = TeleBot(TELEGRAM_BOT_TOKEN)
http_session = requests.Session()

# ---------------- KEEP-ALIVE HEALTH SERVER (FOR RENDER 24/7) ----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Flash Bot is ONLINE 24/7! Status: 100% HEALTHY.")

    def log_message(self, format, *args):
        # Silence HTTP access logs
        return

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logging.info(f"Keep-Alive Health server running on port {port}")
        server.serve_forever()
    except Exception as e:
        logging.warning(f"Health server notice: {e}")

threading.Thread(target=run_health_server, daemon=True).start()

def self_ping_keeper():
    time.sleep(30)
    while True:
        try:
            url = os.environ.get('RENDER_EXTERNAL_URL', 'https://flash-bot-8i1m.onrender.com')
            if url:
                http_session.get(url, timeout=10)
                logging.info('Keep-alive ping sent to prevent Render sleep.')
        except Exception:
            pass
        time.sleep(300) # Ping every 5 minutes

threading.Thread(target=self_ping_keeper, daemon=True).start()

# ----------------------------------------------------------------------------


# Initialize local SQLite database
with sqlite3.connect(DB_PATH) as conn:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_name TEXT,
            message_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS roulette_scores (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            points INTEGER DEFAULT 200,
            streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_daily INTEGER DEFAULT 0
        );
    """)

def save_chat_message(chat_id, user_name, text):
    """Thread-safe storage of group messages for conversational context."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO messages (chat_id, user_name, message_text) VALUES (?, ?, ?)",
                (chat_id, user_name, text)
            )
    except Exception as e:
        logging.error(f"Error saving message: {e}")


# ----------------- RUSSIAN ROULETTE V2 ENGINE (PUSH-YOUR-LUCK) -----------------
# STRICT ANTI-FLOOD: All animations, rounds, cashouts, deaths, and timeouts update
# THE SAME MESSAGE in-place via edit_message_text. ZERO NEW MESSAGES CREATED!

ROULETTE_ROUND_POTS = {
    1: 50,
    2: 120,
    3: 220,
    4: 380,
    5: 600,
    6: 1000
}

POOR_ROULETTE_QUOTES = [
    "Abe gareeb, jeb me 150 points nahi hain aur chala hai maut se khelne. Go away poor kid!",
    "Chillar party detected! Jeb me 150 points ka kaffan khareedne ke paise nahi hain, pehle chanda maango!",
    "Group walon, koi is bhikhari ko do-chaar chillar phenk ke maaro re, zero balance leke roulette khelne aagaya!",
    "Abe tu phone recharge karne ke paise bacha le pehle, roulette baad me khelna!",
    "Bhai pehle katora leke group me bheek maang le, 150 points poore honge tab aana!",
    "Error 404: Points not found. Go away poor kid, dosto se udhaar leke aaja!",
    "Zindagi me itna gareeb koi kaise ho sakta hai? 150 points kama ke aa pehle!"
]

TIMEOUT_ROASTS = [
    "Itna darpok hai tu ki decision lene me haath kaanp gaye? 30s timeout ho gaya, chal nikal!",
    "Bhai ki pant geeli ho gayi trigger dekh ke! Light-hearted coward detected, game expired!",
    "Abe itna darr lag raha tha toh roulette shuru hi kyun kiya tha? Time expired, chal nikal!",
    "30 second mein darr ke maare phone chhod ke bhaag gaya! Game cancelled, zero points for coward!",
    "Darr ke aage jeet hoti hai, par tu toh darr ke pehle hi behosh ho gaya! Timeout!"
]

ACTIVE_ROULETTE_GAMES = {}

def clean_player_name(name):
    """Sanitizes username so Telegram Markdown formatting never crashes edits."""
    if not name:
        return "Player"
    for ch in ['*', '_', '`', '[', ']', '(', ')', '~']:
        name = name.replace(ch, '')
    return name.strip() or "Player"

def update_roulette_msg(chat_id, message_id, text, reply_markup=None):
    """
    STRICT ANTI-FLOOD HELPER:
    Updates the single existing roulette message in-place.
    Never sends new messages into the chat.
    """
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        # Fallback to plain text if Markdown parse error occurred (e.g. strange username)
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            bot.edit_message_text(clean_text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except Exception as e2:
            logging.error(f"Error editing roulette message: {e2}")

def get_or_create_roulette_player(user_id, user_name):
    safe_name = clean_player_name(user_name)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT points, streak, best_streak, wins, losses, last_daily FROM roulette_scores WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO roulette_scores (user_id, user_name, points, streak, best_streak, wins, losses, last_daily) VALUES (?, ?, 200, 0, 0, 0, 0, 0)", (user_id, safe_name))
                conn.commit()
                row = (200, 0, 0, 0, 0, 0)
            else:
                c.execute("UPDATE roulette_scores SET user_name = ? WHERE user_id = ?", (safe_name, user_id))
                conn.commit()
            return {
                "user_id": user_id,
                "user_name": safe_name,
                "points": row[0],
                "streak": row[1],
                "best_streak": row[2],
                "wins": row[3],
                "losses": row[4],
                "last_daily": row[5]
            }
    except Exception as e:
        logging.error(f"Error getting roulette player: {e}")
        return {"user_id": user_id, "user_name": safe_name, "points": 200, "streak": 0, "best_streak": 0, "wins": 0, "losses": 0, "last_daily": 0}

def get_roulette_leaderboard(caller_id=None):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT user_name, points, streak, best_streak, user_id FROM roulette_scores ORDER BY points DESC LIMIT 10")
            rows = c.fetchall()

        medals = ["🥇", "🥈", "🥉", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
        lines = ["🏆 *RUSSIAN ROULETTE LEADERBOARD (Top Survivors):*\n"]
        for i, r in enumerate(rows):
            m = medals[i]
            star = " 👑" if i == 0 else ""
            clean_name = clean_player_name(r[0])
            lines.append(f"{m} *{clean_name}*{star} — `{r[1]} pts` (Streak: {r[2]} 🔥)")

        lines.append("\n🎲 _Play: Type `/roulette` (Push your luck! Cash out or risk it)_")
        lines.append("🎁 _Claim daily 100 pts: `/daily`_")
        return "\n".join(lines)
    except Exception as e:
        return f"Error loading leaderboard: {e}"

def make_roulette_markup(session_id, current_pot, next_pot):
    markup = InlineKeyboardMarkup()
    btn_spin = InlineKeyboardButton(f"🔫 Fire Again (Risk it for +{next_pot} pts)", callback_data=f"rr_spin_{session_id}")
    btn_leave = InlineKeyboardButton(f"💰 Cash Out (+{current_pot} pts)", callback_data=f"rr_leave_{session_id}")
    markup.row(btn_spin)
    markup.row(btn_leave)
    return markup

def expire_roulette_session(session_id, chat_id, message_id, user_name):
    """Handles 30-second decision timeout in-place. Updates existing message, ZERO new messages."""
    time.sleep(30)
    session = ACTIVE_ROULETTE_GAMES.get(session_id)
    if session and session.get("is_active"):
        session["is_active"] = False
        if session_id in ACTIVE_ROULETTE_GAMES:
            del ACTIVE_ROULETTE_GAMES[session_id]
        roast = random.choice(TIMEOUT_ROASTS)
        safe_name = clean_player_name(user_name)
        timeout_text = (
            f"⏱️ *30 Seconds Expired!* (Game Cancelled)\n\n"
            f"_{roast}_\n\n"
            f"🐔 *{safe_name}* darr ke bhaag gaya! Iss game ke na koi points mile na kate."
        )
        update_roulette_msg(chat_id, message_id, timeout_text, reply_markup=None)

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:roulette|russianroulette)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_roulette_command(message):
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id
    raw_name = user.first_name or "Friend"
    safe_name = clean_player_name(raw_name)

    player = get_or_create_roulette_player(user_id, safe_name)

    # Check bankruptcy (needs at least 150 points to risk)
    if player["points"] < 150:
        quote = random.choice(POOR_ROULETTE_QUOTES)
        bot.reply_to(
            message,
            f"🚫 *Khelna Band, Gareeb!* (Balance: `{player['points']} pts`)\n\n"
            f"_{quote}_\n\n"
            f"💡 _Tip: `/daily` likho aur 100 free points claim karo ya group walon se bheek maango!_",
            parse_mode="Markdown"
        )
        return

    # ANTI-FLOOD: Cancel and remove any previous uncompleted game message by this user
    for s_id, s_data in list(ACTIVE_ROULETTE_GAMES.items()):
        if s_data.get("user_id") == user_id and s_data.get("is_active"):
            s_data["is_active"] = False
            try:
                bot.delete_message(s_data["chat_id"], s_data["message_id"])
            except Exception:
                pass
            ACTIVE_ROULETTE_GAMES.pop(s_id, None)

    # Exactly ONE single message created for this entire game
    try:
        msg = bot.reply_to(message, "🌀 *Spinning cylinder & cocking the hammer...* 🔄", parse_mode="Markdown")
        time.sleep(1.0)
    except Exception:
        msg = message

    # Chamber probability: random bullet chamber and random spin chamber (independent every single game)
    bullet = random.randint(1, 6)
    chamber = random.randint(1, 6)

    if chamber == bullet:
        # Shot on Round 1: lose 150 from total balance, clear game
        new_pts = max(0, player["points"] - 150)
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE roulette_scores SET points = ?, streak = 0, losses = losses + 1 WHERE user_id = ?", (new_pts, user_id))
        except Exception as e:
            logging.error(f"DB update error: {e}")

        res_text = (
            f"💥 *BANG!!* Bullet fired from Chamber `{chamber}/6`!\n\n"
            f"💀 *Khel Khatam! {safe_name} Got Shot on Round 1!*\n"
            f"💸 Total Balance se `-150 Points` kat gaye!\n"
            f"💰 Naya Balance: `{new_pts} pts` ❌"
        )
        update_roulette_msg(chat_id, msg.message_id, res_text, reply_markup=None)
        return

    # Survived Round 1!
    current_pot = ROULETTE_ROUND_POTS[1]
    next_pot = ROULETTE_ROUND_POTS[2]
    session_id = f"{user_id}_{int(time.time()*1000)}"

    ACTIVE_ROULETTE_GAMES[session_id] = {
        "user_id": user_id,
        "user_name": safe_name,
        "round": 1,
        "current_pot": current_pot,
        "chat_id": chat_id,
        "message_id": msg.message_id,
        "is_active": True
    }

    res_text = (
        f"💨 *CLICK...* Chamber `{chamber}/6` was EMPTY!\n\n"
        f"🎉 *{safe_name} Survived Round 1!*\n"
        f"💰 Current Pot: `+{current_pot} Points`\n\n"
        f"Ab batao: Risk leke agle round me `+{next_pot} pts` ke liye fire karega ya `+{current_pot} pts` leke bhaagega?\n"
        f"⏱️ _(30 seconds to decide!)_"
    )
    markup = make_roulette_markup(session_id, current_pot, next_pot)
    update_roulette_msg(chat_id, msg.message_id, res_text, reply_markup=markup)

    # Start 30s timer thread
    threading.Thread(target=expire_roulette_session, args=(session_id, chat_id, msg.message_id, safe_name), daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('rr_'))
def handle_roulette_callback(call):
    parts = call.data.split("_", 2)
    if len(parts) < 3:
        return
    action = parts[1]
    session_id = parts[2]

    session = ACTIVE_ROULETTE_GAMES.get(session_id)
    if not session or not session.get("is_active"):
        bot.answer_callback_query(call.id, "Game expire ho chuka hai bhai ya finish ho gaya!", show_alert=True)
        return

    # Strictly only the player can press the buttons
    if call.from_user.id != session["user_id"]:
        bot.answer_callback_query(call.id, "Abe ye tumhara game nahi hai! Apna /roulette shuru karo.", show_alert=True)
        return

    # Inactivate immediately to prevent double-click race conditions
    session["is_active"] = False
    if session_id in ACTIVE_ROULETTE_GAMES:
        del ACTIVE_ROULETTE_GAMES[session_id]

    chat_id = session["chat_id"]
    message_id = session["message_id"]
    user_id = session["user_id"]
    safe_name = clean_player_name(session["user_name"])
    current_pot = session["current_pot"]
    current_round = session["round"]

    # 1. CASH OUT ACTION (UPDATES EXISTING MESSAGE, REMOVES BUTTONS)
    if action == "leave":
        bot.answer_callback_query(call.id, f"Cashed out +{current_pot} pts!")
        player = get_or_create_roulette_player(user_id, safe_name)
        new_pts = player["points"] + current_pot
        new_streak = player["streak"] + 1
        best_streak = max(player["best_streak"], new_streak)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE roulette_scores SET points = ?, streak = ?, best_streak = ?, wins = wins + 1 WHERE user_id = ?", (new_pts, new_streak, best_streak, user_id))
        except Exception as e:
            logging.error(f"DB update error: {e}")

        cashout_text = (
            f"💰 *CASHED OUT & SURVIVED!*\n\n"
            f"🎉 *{safe_name}* ne samajhdari dikhai aur `+{current_pot} Points` jeet ke nikal gaya!\n"
            f"💰 Naya Balance: `{new_pts} pts` | Current Streak: `{new_streak}` 🔥"
        )
        update_roulette_msg(chat_id, message_id, cashout_text, reply_markup=None)
        return

    # 2. FIRE AGAIN ACTION (UPDATES EXISTING MESSAGE IN-PLACE, NEVER MAKES NEW MESSAGE)
    if action == "spin":
        next_round = current_round + 1
        bot.answer_callback_query(call.id, f"Spinning for Round {next_round}!")

        # In-place animation on the SAME message
        update_roulette_msg(chat_id, message_id, f"🌀 *Spinning cylinder for Round {next_round}...* 🔄", reply_markup=None)
        time.sleep(1.0)

        # Independent random bullet and chamber for this round
        bullet = random.randint(1, 6)
        chamber = random.randint(1, 6)

        if chamber == bullet:
            # SHOT FIRED! Lost session pot + extra 150 points deducted from total balance. Clear game.
            player = get_or_create_roulette_player(user_id, safe_name)
            new_pts = max(0, player["points"] - 150)
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE roulette_scores SET points = ?, streak = 0, losses = losses + 1 WHERE user_id = ?", (new_pts, user_id))
            except Exception as e:
                logging.error(f"DB update error: {e}")

            death_text = (
                f"💥 *BANG!!* Bullet fired from Chamber `{chamber}/6`!\n\n"
                f"💀 *Khel Khatam! {safe_name} Got Shot in Round {next_round}!*\n"
                f"💸 Iss game ke saare `+{current_pot} pts` paani me gaye!\n"
                f"⚠️ Aur total wallet se extra `-150 Points` kat gaye!\n"
                f"💰 Naya Balance: `{new_pts} pts` | Streak Broken ❌"
            )
            update_roulette_msg(chat_id, message_id, death_text, reply_markup=None)
            return

        # SURVIVED NEXT ROUND!
        new_pot = ROULETTE_ROUND_POTS.get(next_round, current_pot + 250)

        # If beat final Round 6: JACKPOT!
        if next_round >= 6:
            player = get_or_create_roulette_player(user_id, safe_name)
            jackpot_pts = player["points"] + new_pot
            new_streak = player["streak"] + 5
            best_streak = max(player["best_streak"], new_streak)
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE roulette_scores SET points = ?, streak = ?, best_streak = ?, wins = wins + 1 WHERE user_id = ?", (jackpot_pts, new_streak, best_streak, user_id))
            except Exception as e:
                logging.error(f"DB update error: {e}")

            jackpot_text = (
                f"👑 *ULTIMATE LEGEND! JACKPOT WON!*\n\n"
                f"🔥 *{safe_name}* ne lagatar 6 ke 6 rounds survive kar liye!\n"
                f"🏆 Jackpot Reward: `+{new_pot} Points`!\n"
                f"💰 Naya Balance: `{jackpot_pts} pts` | Streak: `{new_streak}` 🔥"
            )
            update_roulette_msg(chat_id, message_id, jackpot_text, reply_markup=None)
            return

        # Advance session to next round in the SAME message
        next_session_id = f"{user_id}_{int(time.time()*1000)}"
        future_pot = ROULETTE_ROUND_POTS.get(next_round + 1, new_pot + 250)

        ACTIVE_ROULETTE_GAMES[next_session_id] = {
            "user_id": user_id,
            "user_name": safe_name,
            "round": next_round,
            "current_pot": new_pot,
            "chat_id": chat_id,
            "message_id": message_id,
            "is_active": True
        }

        res_text = (
            f"💨 *CLICK...* Chamber `{chamber}/6` was EMPTY!\n\n"
            f"🔥 *{safe_name} Survived Round {next_round}!*\n"
            f"💰 Current Pot: `+{new_pot} Points`\n\n"
            f"Kismat chamak rahi hai! Agle round me `+{future_pot} pts` ke liye risk lega ya `+{new_pot} pts` leke nikalna hai?\n"
            f"⏱️ _(30 seconds to decide!)_"
        )
        markup = make_roulette_markup(next_session_id, new_pot, future_pot)
        update_roulette_msg(chat_id, message_id, res_text, reply_markup=markup)

        # Start new 30s timer thread
        threading.Thread(target=expire_roulette_session, args=(next_session_id, chat_id, message_id, safe_name), daemon=True).start()

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:stats|leaderboard|top)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_roulette_stats(message):
    user_id = message.from_user.id
    leaderboard_text = get_roulette_leaderboard(caller_id=user_id)
    bot.reply_to(message, leaderboard_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:daily)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_daily_points(message):
    user = message.from_user
    user_id = user.id
    raw_name = user.first_name or "Friend"
    safe_name = clean_player_name(raw_name)
    now_ts = int(time.time())

    player = get_or_create_roulette_player(user_id, safe_name)
    last_daily = player.get("last_daily", 0)

    # 24 hours cooldown = 86400 seconds
    if now_ts - last_daily < 86400:
        remaining_sec = 86400 - (now_ts - last_daily)
        hours = remaining_sec // 3600
        mins = (remaining_sec % 3600) // 60
        bot.reply_to(
            message,
            f"⏳ *Itni jaldi kya hai bhai?*\n"
            f"Tum already aaj ka daily reward le chuke ho.\n"
            f"Agla bonus `{hours}h {mins}m` baad milega! (Balance: `{player['points']} pts`)",
            parse_mode="Markdown"
        )
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            new_pts = player["points"] + 100
            c.execute("UPDATE roulette_scores SET points = ?, last_daily = ? WHERE user_id = ?", (new_pts, now_ts, user_id))
            conn.commit()

        bot.reply_to(
            message,
            f"🎁 *Daily Bonus Claimed!*\n\n"
            f"*{safe_name}* ko mile `+100 Free Points`!\n"
            f"💰 Naya Balance: `{new_pts} pts`\n\n"
            f"Ab jao aur `/roulette` khel ke kismat aazmao!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error claiming daily: {e}")

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:compare)(?:@\w+)?(?:\s+.*)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_compare_command(message):
    """
    ZERO-TOKEN SMART ROM COMPARISON ENGINE:
    Handles capital/small, attached 'os' (axionos, lineageos), typos (lienageos), spaces (axion os vs lineage os).
    """
    text = (message.text or "").strip()
    detected_roms = extract_roms_from_query(text)

    # Case 1: No recognized ROM found
    if not detected_roms:
        available = ", ".join([v["name"] for v in ROM_PROFILES.values()])
        bot.reply_to(
            message,
            "⚖️ *Kaunsi 2 ROMs compare karni hain bhai?*\n\n"
            "*Usage Examples:*\n"
            "• `/compare axion pixelos`\n"
            "• `/compare axionos lineageos`\n"
            "• `/compare crdroid lineage`\n"
            "• `/compare derpfest evox`\n"
            "• `/compare risingos superior`\n\n"
            f"📋 *Available ROMs:* {available}",
            parse_mode="Markdown"
        )
        return

    # Case 2: Only 1 ROM detected -> Show deep profile
    if len(detected_roms) == 1:
        rom1_key = detected_roms[0]
        r = ROM_PROFILES[rom1_key]
        card = (
            f"📊 *{r['name']} Profile* ({r['type']})\n\n"
            f"• *Customization:* {r['customization']}\n"
            f"• *Performance:* {r['perf']}\n"
            f"• *Battery Life:* {r['battery']}\n"
            f"• *Highlights:* {r['features']}\n\n"
            f"🎯 *Verdict:* {r['verdict']}\n\n"
            f"💡 _Doosri ROM ke sath compare karne ke liye likho: `/compare {rom1_key} pixelos`_"
        )
        bot.reply_to(message, card, parse_mode="Markdown")
        return

    # Case 3: 2 ROMs detected -> Side-by-side comparison
    rom1_key, rom2_key = detected_roms[0], detected_roms[1]
    r1 = ROM_PROFILES[rom1_key]
    r2 = ROM_PROFILES[rom2_key]

    card = (
        f"⚖️ *ROM COMPARISON:* {r1['name']} *vs* {r2['name']}\n\n"
        f"🎨 *Customization:*\n"
        f"• *{r1['name']}:* {r1['customization']}\n"
        f"• *{r2['name']}:* {r2['customization']}\n\n"
        f"🚀 *Gaming & Performance:*\n"
        f"• *{r1['name']}:* {r1['perf']}\n"
        f"• *{r2['name']}:* {r2['perf']}\n\n"
        f"🔋 *Battery Life:*\n"
        f"• *{r1['name']}:* {r1['battery']}\n"
        f"• *{r2['name']}:* {r2['battery']}\n\n"
        f"✨ *Key Features:*\n"
        f"• *{r1['name']}:* {r1['features']}\n"
        f"• *{r2['name']}:* {r2['features']}\n\n"
        f"🎯 *Final Verdict:*\n"
        f"👉 *{r1['name']}:* {r1['verdict']}\n"
        f"👉 *{r2['name']}:* {r2['verdict']}\n\n"
        f"💡 _Download: `/give {rom1_key}` ya `/give {rom2_key}` likho!_"
    )
    bot.reply_to(message, card, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:ping)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_ping_command(message):
    start = time.time()
    try:
        msg = bot.reply_to(message, "⚡ *Pinging...*", parse_mode="Markdown")
        latency_ms = max(1, int((time.time() - start) * 1000))
        uptime_str = get_uptime_string()
        catalog_count = len(ALL_ROMS)

        status_text = (
            "🏓 *Pong!*\n\n"
            f"• *Latency:* `{latency_ms} ms`\n"
            f"• *Uptime:* `{uptime_str}`\n"
            f"• *Cataloged Files:* `{catalog_count}`\n"
            "• *Status:* `100% ONLINE (24/7)`\n"
            "• *AI Engine:* `Groq 120B (Ultra-Fast)`\n\n"
            "💡 _Tip: Use `/give <name>` to fetch any ROM or kernel._"
        )
        bot.edit_message_text(status_text, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in /ping handler: {e}")

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:give)(?:@\w+)?(?:\s+.*)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_give_command(message):
    """
    STRICT COMMAND DISPATCH: Files/ROMs are ONLY delivered when user explicitly issues /give command.
    Examples:
    /give axion
    /give pixelos
    /give kernel
    /give (in reply to a message)
    """
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Friend"
    text = (message.text or "").strip()

    save_chat_message(chat_id, user_name, text)
    bot.send_chat_action(chat_id, "upload_document")

    # Extract query after /give or /give@bot_username
    query = re.sub(r'^[/\.!](?:give)(?:@\w+)?\s*', '', text, flags=re.IGNORECASE).strip()

    reply_to_text = None
    if message.reply_to_message:
        reply_to_text = message.reply_to_message.caption or message.reply_to_message.text or ""

    recent_history = get_recent_chat_history(chat_id, limit=4)
    history_texts = [m[1] for m in recent_history if m[1] != text]

    # If neither query nor reply_to_text exists
    if not query and not reply_to_text:
        bot.reply_to(
            message,
            "📦 *Kaunsi ROM ya file chahiye bhai?*\n\n"
            "Usage:\n"
            "• `/give axion`\n"
            "• `/give pixelos`\n"
            "• `/give kernel`\n"
            "• `/give recovery`\n\n"
            "Ya kisi message pe reply karke `/give` likho!",
            parse_mode="Markdown"
        )
        return

    # Perform search
    search_query = query if query else (reply_to_text or "")
    matches, version_note = search_roms_or_kernels(
        search_query,
        reply_to_text=reply_to_text,
        history_texts=history_texts,
        force_search=True
    )

    if matches:
        best = matches[0]
        cap = best.get('caption', '').strip()
        details = f"\n_{cap}_" if cap else ""
        prefix = f"{version_note}\n\n" if version_note else ""
        reply_msg = f"{prefix}📦 *{best['name']}*{details}\n🔗 [Download Post in Channel]({best['link']})"

        try:
            bot.reply_to(message, reply_msg, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, f"{prefix}📦 {best['name']}\n🔗 {best['link']}")

        try:
            bot.copy_message(
                chat_id=chat_id,
                from_chat_id=f"@{CHANNEL_USERNAME}",
                message_id=best['message_id']
            )
            logging.info(f"⚡ Successfully delivered file #{best['message_id']} via /give command to {user_name}!")
        except Exception as copy_err:
            logging.info(f"Could not copy directly ({copy_err}), link delivered.")
    else:
        term = query or "is topic"
        bot.reply_to(
            message,
            f"❌ *'{term}' ke liye koi matching file nahi mili.*\n"
            "Thoda specific naam likh ke try kar, jaise: `/give axion` ya `/give pixelos`",
            parse_mode="Markdown"
        )

@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_group_message(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Friend"
    text = message.text

    # 1. Silently record all conversation
    save_chat_message(chat_id, user_name, text)

    # 2. Check if the user addressed Flash
    bot_info = bot.get_me()
    if should_respond(message, bot_info.username):
        logging.info(f"Bot invoked by {user_name}: {text}")
        bot.send_chat_action(chat_id, "typing")

        # Get replied-to message text if any
        reply_to_text = None
        if message.reply_to_message:
            reply_to_text = message.reply_to_message.caption or message.reply_to_message.text or ""

        # Fetch recent chat context for follow-up detection
        recent_history = get_recent_chat_history(chat_id, limit=4)
        history_texts = [m[1] for m in recent_history if m[1] != text]

        # CONVERSATIONAL BANTER / ROASTING (CONTEXTUAL, DRY SARCASM & NO FAKE OBJECTS)
        clean_text = sanitize_for_ai(text)
        user_is_master = is_sender_master(message)

        target_name = user_name
        target_message = clean_text
        boss_command = "None"
        task_desc = f"Reply to {user_name}"

        if message.reply_to_message:
            rep_user = message.reply_to_message.from_user
            rep_name = rep_user.first_name if rep_user else "Someone"
            rep_text = sanitize_for_ai(message.reply_to_message.caption or message.reply_to_message.text or "")

            if user_is_master:
                t_lower = (text or "").lower()
                if any(w in t_lower for w in ["ask flash", "puch flash", "bol flash"]):
                    target_name = rep_name
                    target_message = rep_text
                    boss_command = "ask flash"
                    task_desc = f"Answer {rep_name} about their question/topic directly"
                elif any(w in t_lower for w in ["roast", "pel", "kro", "baja"]):
                    target_name = rep_name
                    target_message = rep_text
                    boss_command = "Flash roast him"
                    task_desc = f"Roast {rep_name} directly on their message"
                else:
                    target_name = "Boss (Billu bhai)"
                    target_message = clean_text
                    boss_command = "None"
                    task_desc = "Reply respectfully and casually to Boss Billu bhai"
            else:
                t_lower = (text or "").lower()
                if any(w in t_lower for w in ["roast", "pel", "kro", "baja"]):
                    target_name = rep_name
                    target_message = rep_text
                    boss_command = "None"
                    task_desc = f"Roast {rep_name} directly on their message"
                else:
                    target_name = user_name
                    target_message = f"{clean_text} (In reply to {rep_name}: '{rep_text}')"
                    boss_command = "None"
                    task_desc = f"Reply to {user_name}"
        else:
            if user_is_master:
                target_name = "Boss (Billu bhai)"
                target_message = clean_text
                boss_command = "None"
                task_desc = "Reply respectfully and casually to Boss Billu bhai"
            else:
                target_name = user_name
                target_message = clean_text
                boss_command = "None"
                task_desc = f"Reply to {user_name}"

        user_payload = f"Target: {target_name}\nMessage: {target_message}\nBoss Command: {boss_command}\nTask: {task_desc}"

        try:
            reply = call_ai(SYSTEM_PROMPT, user_payload, few_shots=FEW_SHOTS)

            def has_cliche_or_bad(txt):
                t_low = (txt or "").lower()
                if contains_family_words(txt):
                    return True
                if re.search(r"\bitn[ai]\s+\w+\s+hai\s+ki\b", t_low):
                    return True
                if any(k in t_low for k in ["cycle ki chain", "chai ki tapri", "chai ki taseer"]):
                    return True
                if "sharam se khatam" in t_low or "battery sharam" in t_low:
                    return True
                return False

            if has_cliche_or_bad(reply):
                logging.warning(f"AI response triggered guard: '{reply}'. Regenerating...")
                retry_payload = f"{user_payload}\n\n[CRITICAL: Reply had banned words or nonsense template. Reply in 1 short dry sarcastic line under 15 words in Roman Hinglish:]"
                reply = call_ai(SYSTEM_PROMPT, retry_payload, few_shots=FEW_SHOTS)
                if has_cliche_or_bad(reply):
                    logging.warning("AI still triggered guard. Using clean fallback.")
                    reply = random.choice(SAFE_CLEAN_ROASTS)

            bot.reply_to(message, reply)
            save_chat_message(chat_id, "Flash", reply)
        except Exception as e:
            logging.error(f"Error answering user: {e}")
            bot.reply_to(message, "Dimag ka fuse udd gaya ek second ke liye, dubara pooch!")

if __name__ == "__main__":
    bot_info = bot.get_me()
    print("=" * 50)
    print(f"  Bot Name     : {bot_info.first_name}")
    print(f"  Bot Username : @{bot_info.username}")
    print(f"  Cataloged    : {len(ALL_ROMS)} files from @{CHANNEL_USERNAME}")
    print("  AI Engines   : Groq LPU (Primary) + 4x OpenRouter + Google Gemini (Triple Fallback)")
    print(f"  Trigger Names: {', '.join(BOT_NAMES)}")
    print("  Verb Filter  : Active ('to flash', 'flash firmware' ignored)")
    print("  Firmware     : RUI2 (RM6785) vs RUI3 (salaa) Strict Matcher")
    print("=" * 50)
    print("Flash is running at 100% MAXIMUM ACCURACY! [ONLINE]")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            logging.warning(f"Connection dropped ({e}), reconnecting in 2s...")
            time.sleep(2)
