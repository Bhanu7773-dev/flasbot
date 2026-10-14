import sys
import unicodedata
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
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

# ----------------- CONFIGURATION (LOADED SECURELY VIA .ENV / ENVIRONMENT) -----------------
def load_dotenv_file(filepath=None):
    if filepath is None:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            logging.warning(f"Notice loading .env: {e}")

load_dotenv_file()

import random

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

raw_or_keys = os.environ.get("OPENROUTER_KEYS", "").strip()
if raw_or_keys:
    OPENROUTER_KEYS = [k.strip() for k in raw_or_keys.split(",") if k.strip()]
else:
    OPENROUTER_KEYS = []

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b"
]

BOT_NAMES = ["flash"]
CHANNEL_USERNAME = "rm6785dumppAss"
CHANNEL_ID = -1003087244808

OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "openrouter/free"
]

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash"
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

# ---------------- KEEP-ALIVE HEALTH SERVER & TELEGRAM MINI-APP BACKEND ----------------
MINIAPP_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roulette_miniapp.html")

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/roulette", "/game", "/miniapp"]:
            if os.path.exists(MINIAPP_HTML_PATH):
                with open(MINIAPP_HTML_PATH, "r", encoding="utf-8") as f:
                    html_content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
            else:
                self.send_error(404, "Mini App HTML not found")
            return

        if path == "/api/player":
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                user_id = int(qs.get("user_id", [6056618592])[0])
            except Exception:
                user_id = 6056618592
            user_name = qs.get("user_name", ["Player"])[0]

            player = get_or_create_roulette_player(user_id, user_name)
            rank = 1
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("SELECT COUNT(*) + 1 FROM roulette_scores WHERE points > ?", (player["points"],))
                    rank = c.fetchone()[0]
            except Exception:
                pass
            player["rank"] = rank

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(player).encode("utf-8"))
            return

        # Default root health check
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Flash Bot is ONLINE 24/7! Status: 100% HEALTHY.")

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body = json.loads(post_body.decode("utf-8"))
        except Exception:
            body = {}

        path = urllib.parse.urlparse(self.path).path

        if path == "/api/spin":
            user_id = int(body.get("user_id", 0))
            user_name = clean_player_name(body.get("user_name", "Player"))
            current_round = int(body.get("round", 1))
            current_pot = int(body.get("current_pot", 0))

            player = get_or_create_roulette_player(user_id, user_name)

            bullet = random.randint(1, 6)
            chamber = random.randint(1, 6)

            if chamber == bullet:
                # Shot!
                new_pts = max(0, player["points"] - 150)
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute("UPDATE roulette_scores SET points = ?, streak = 0, losses = losses + 1 WHERE user_id = ?", (new_pts, user_id))
                except Exception as e:
                    logging.error(f"DB update error: {e}")
                schedule_cloud_sync()

                resp = {
                    "status": "dead",
                    "bullet": bullet,
                    "chamber": chamber,
                    "new_points": new_pts,
                    "roast": random.choice(POOR_ROULETTE_QUOTES)
                }
            else:
                # Survived
                next_pot = ROULETTE_ROUND_POTS.get(current_round, current_pot + 250)
                if current_round >= 6:
                    jackpot_pts = player["points"] + next_pot
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("UPDATE roulette_scores SET points = ?, streak = streak + 5, wins = wins + 1 WHERE user_id = ?", (jackpot_pts, user_id))
                    except Exception as e:
                        logging.error(f"DB update error: {e}")
                    schedule_cloud_sync()

                    resp = {
                        "status": "jackpot",
                        "bullet": bullet,
                        "chamber": chamber,
                        "jackpot": next_pot,
                        "new_points": jackpot_pts
                    }
                else:
                    resp = {
                        "status": "survived",
                        "bullet": bullet,
                        "chamber": chamber,
                        "current_pot": next_pot,
                        "next_round": current_round + 1
                    }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/cashout":
            user_id = int(body.get("user_id", 0))
            user_name = clean_player_name(body.get("user_name", "Player"))
            pot = int(body.get("pot", 0))

            player = get_or_create_roulette_player(user_id, user_name)
            new_pts = player["points"] + pot
            new_streak = player["streak"] + 1
            best_streak = max(player["best_streak"], new_streak)

            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE roulette_scores SET points = ?, streak = ?, best_streak = ?, wins = wins + 1 WHERE user_id = ?", (new_pts, new_streak, best_streak, user_id))
            except Exception as e:
                logging.error(f"DB update error: {e}")
            schedule_cloud_sync()

            resp = {
                "status": "cashed_out",
                "new_points": new_pts,
                "streak": new_streak
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
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
            user_id INTEGER,
            message_id INTEGER,
            reply_to_msg_id INTEGER,
            reply_to_user_id INTEGER,
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
    # Safe migration for existing DB
    cursor = conn.execute("PRAGMA table_info(messages)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    for col_name, col_type in [
        ("user_id", "INTEGER"),
        ("message_id", "INTEGER"),
        ("reply_to_msg_id", "INTEGER"),
        ("reply_to_user_id", "INTEGER")
    ]:
        if col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

BACKUP_CHAT_ID = int(os.environ.get("BACKUP_CHAT_ID", 6056618592))

def sync_to_telegram_cloud():
    """Syncs SQLite roulette scores to pinned cloud storage message in Telegram."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, user_name, points, streak, best_streak, wins, losses, last_daily FROM roulette_scores")
            rows = c.fetchall()

        if not rows:
            return

        players = {}
        for r in rows:
            players[str(r[0])] = {
                "user_name": r[1],
                "points": r[2],
                "streak": r[3],
                "best_streak": r[4],
                "wins": r[5],
                "losses": r[6],
                "last_daily": r[7]
            }

        payload = {
            "app": "flash_casino_cloud_backup",
            "updated_at": int(time.time()),
            "total_players": len(players),
            "players": players
        }
        json_str = json.dumps(payload, indent=2, ensure_ascii=False)
        ts = time.strftime('%Y-%m-%d %H:%M:%S UTC')
        msg_content = f"📦 *FLASH CLOUD DATABASE BACKUP*\n`{ts}`\n\n```json\n{json_str}\n```"

        chat = bot.get_chat(BACKUP_CHAT_ID)
        pinned = chat.pinned_message

        if pinned and pinned.text and "FLASH CLOUD DATABASE BACKUP" in pinned.text:
            try:
                bot.edit_message_text(msg_content, chat_id=BACKUP_CHAT_ID, message_id=pinned.message_id, parse_mode="Markdown")
                logging.info(f"☁️ Cloud backup updated (Message #{pinned.message_id})")
                return
            except Exception as e:
                if "message is not modified" in str(e):
                    return

        new_msg = bot.send_message(BACKUP_CHAT_ID, msg_content, parse_mode="Markdown")
        bot.pin_chat_message(BACKUP_CHAT_ID, new_msg.message_id, disable_notification=True)
        logging.info(f"☁️ Cloud backup created & pinned (Message #{new_msg.message_id})")
    except Exception as e:
        logging.error(f"Error in sync_to_telegram_cloud: {e}")

def schedule_cloud_sync():
    """Runs sync_to_telegram_cloud in a background daemon thread."""
    threading.Thread(target=sync_to_telegram_cloud, daemon=True).start()

def restore_from_telegram_cloud():
    """Restores database from Telegram pinned cloud backup on startup."""
    try:
        chat = bot.get_chat(BACKUP_CHAT_ID)
        if not chat.pinned_message or not chat.pinned_message.text:
            logging.info("ℹ️ No pinned cloud backup found in backup chat.")
            return False

        text = chat.pinned_message.text
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return False

        data = json.loads(text[start:end+1])
        players = data.get("players", {})
        if not players:
            return False

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            for uid_str, p in players.items():
                uid = int(uid_str)
                c.execute("""INSERT INTO roulette_scores (user_id, user_name, points, streak, best_streak, wins, losses, last_daily)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                             ON CONFLICT(user_id) DO UPDATE SET
                             points = excluded.points,
                             user_name = excluded.user_name,
                             streak = excluded.streak,
                             best_streak = excluded.best_streak,
                             wins = excluded.wins,
                             losses = excluded.losses,
                             last_daily = excluded.last_daily""",
                          (uid, p["user_name"], p["points"], p["streak"], p["best_streak"], p["wins"], p["losses"], p["last_daily"]))
            conn.commit()

        logging.info(f"✅ Successfully restored {len(players)} players from Telegram Cloud Backup!")
        return True
    except Exception as e:
        logging.error(f"❌ Error restoring from Telegram Cloud Backup: {e}")
        return False

# Restore on startup
try:
    restore_from_telegram_cloud()
except Exception as _e:
    logging.warning(f"Initial cloud restore warning: {_e}")

def save_chat_message(chat_id, user_name, text, user_id=None, message_id=None, reply_to_msg_id=None, reply_to_user_id=None):
    """Thread-safe storage of group messages with thread & user tracking."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO messages 
                   (chat_id, user_name, message_text, user_id, message_id, reply_to_msg_id, reply_to_user_id) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chat_id, user_name, text, user_id, message_id, reply_to_msg_id, reply_to_user_id)
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

def render_cylinder(active_slot, is_shot=None):
    """Generates visual 6-chamber revolver graphic."""
    slots = []
    for i in range(1, 7):
        if i == active_slot:
            if is_shot is True:
                slots.append("💥")
            elif is_shot is False:
                slots.append("💨")
            else:
                slots.append("🔘")
        else:
            slots.append("⚪")
    return "[ " + " | ".join(slots) + " ]"

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
        lines.append("💳 _Check wallet: `/balance`_")
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
            f"╔══════════════════════════╗\n"
            f"║ ⏱️ 30 SECONDS EXPIRED! ⏱️ ║\n"
            f"╚══════════════════════════╝\n\n"
            f"_{roast}_\n\n"
            f"🐔 *{safe_name}* darr ke bhaag gaya! Iss game ke na koi points mile na kate."
        )
        update_roulette_msg(chat_id, message_id, timeout_text, reply_markup=None)

def get_recent_chat_history(chat_id, limit=CONTEXT_MESSAGE_LIMIT):
    """Thread-safe retrieval of recent messages."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            res = conn.execute(
                """SELECT user_name, message_text FROM (
                       SELECT id, user_name, message_text FROM messages 
                       WHERE chat_id = ? ORDER BY id DESC LIMIT ?
                   ) ORDER BY id ASC""",
                (chat_id, limit)
            ).fetchall()
            return res
    except Exception:
        return []

def get_reply_thread_chain(chat_id, start_msg_id, limit=8):
    """
    Traces the exact chain of replies backwards starting from start_msg_id.
    Returns list of (user_name, message_text) in chronological order (oldest first).
    """
    if not start_msg_id:
        return []
    chain = []
    current_id = start_msg_id
    visited = set()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            while current_id and current_id not in visited and len(chain) < limit:
                visited.add(current_id)
                row = conn.execute(
                    "SELECT user_name, message_text, reply_to_msg_id FROM messages WHERE chat_id = ? AND message_id = ?",
                    (chat_id, current_id)
                ).fetchone()
                if not row:
                    break
                chain.append((row[0], row[1]))
                current_id = row[2]
        chain.reverse()
        return chain
    except Exception as e:
        logging.error(f"Error tracing reply chain: {e}")
        return []

def get_user_thread_history(chat_id, user_id, user_name, limit=10):
    """
    Fetches the recent conversation strictly between this specific user and Flash.
    Completely excludes other group members and other conversations.
    Returns list of (user_name, message_text) in chronological order (oldest first).
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if user_id:
                rows = conn.execute(
                    """SELECT user_name, message_text FROM (
                           SELECT id, user_name, message_text FROM messages
                           WHERE chat_id = ? 
                             AND (
                                 user_id = ? 
                                 OR (user_name = 'Flash' AND reply_to_user_id = ?)
                                 OR (user_name = 'Flash' AND reply_to_msg_id IN (
                                     SELECT message_id FROM messages WHERE chat_id = ? AND user_id = ?
                                 ))
                             )
                           ORDER BY id DESC LIMIT ?
                       ) ORDER BY id ASC""",
                    (chat_id, user_id, user_id, chat_id, user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT user_name, message_text FROM (
                           SELECT id, user_name, message_text FROM messages
                           WHERE chat_id = ? AND (user_name = ? OR user_name = 'Flash')
                           ORDER BY id DESC LIMIT ?
                       ) ORDER BY id ASC""",
                    (chat_id, user_name, limit)
                ).fetchall()
            return rows
    except Exception as e:
        logging.error(f"Error fetching user thread history: {e}")
        return []

def get_conversation_thread(chat_id, user_id, user_name, reply_to_msg_id=None, limit=10):
    """
    Gets the most accurate thread:
    1. If user replied in a reply-chain, trace the exact chain backwards.
    2. Combine with the clean user <-> Flash direct conversation history.
    Never includes unrelated messages from other users.
    """
    chain = get_reply_thread_chain(chat_id, reply_to_msg_id, limit=limit)
    if chain and len(chain) >= 2:
        return chain
    return get_user_thread_history(chat_id, user_id, user_name, limit=limit)

def load_roms_and_kernels():
    """Loads all 600+ ROMs, Kernels, and Recoveries from json catalog."""
    if os.path.exists(ROMS_DATABASE_FILE):
        try:
            with open(ROMS_DATABASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading {ROMS_DATABASE_FILE}: {e}")
            return []
    return []

ALL_ROMS = load_roms_and_kernels()

KNOWN_BRANDS = [
    "lineage", "infinity", "crdroid", "evolution", "matrixx", "matrix",
    "axion", "rising", "derpfest", "bliss", "orangefox",
    "twrp", "pbrp", "takoyaki", "miku", "morphe", "sukisu", "kernelsu",
    "bakasu", "resukisu", "elixir", "blaze", "cherish", "voltage",
    "pixelos", "pixelplus", "corvus", "ancient", "dotos", "arrow", "yuri"
]

FILE_KEYWORDS = [
    "rom", "kernel", "recovery", "twrp", "pbrp", "orangefox", "ofox",
    "shrp", "firmware", "boot img", "boot.img", "bootimage", "boot_img",
    "vendor", "fastboot", "spft", "c.19", "c.18", "c.17", "flashable",
    "os", "port", "zip", "build", "img"
]


def normalize_text(t):
    """Fixes typos, Hinglish slang, and shorthand names."""
    t = (t or "").lower()
    typos = {
        r'\blienage\w*': 'lineage',
        r'\blinege\w*': 'lineage',
        r'\blinage\w*': 'lineage',
        r'\blineageos\b': 'lineage',
        r'\bevox\w*': 'evolution',
        r'\bofox\b': 'orangefox',
        r'\bfox\b': 'orangefox',
        r'\bpbp\b': 'pbrp',
        r'\bpb\b': 'pbrp',
        r'\btakoyki\w*': 'takoyaki',
        r'\bkernal\w*': 'kernel',
        r'\bkrnl\b': 'kernel',
        r'\baxionaosp\b': 'axion',
        r'\brec\b': 'recovery',
        r'\bmatrix\b': 'matrixx',
        r'\bmatrixos\b': 'matrixx',
        r'\bmatrixxos\b': 'matrixx',
    }
    for pat, repl in typos.items():
        t = re.sub(pat, repl, t)
    return t

def extract_negatives(q):
    """Extract negative exclusions like 'not lineage', 'without boot', 'no gapps'."""
    neg_patterns = [
        r'\b(?:not|without|no|dont\s+want|except)\s+([a-z0-9_\-\.\s]+)'
    ]
    negatives = []
    for pat in neg_patterns:
        matches = re.findall(pat, q.lower())
        for m in matches:
            tokens = re.split(r'[,;\s]+', m)
            for tok in tokens:
                if tok and tok not in ["a", "the", "me", "give", "os", "file", "img"]:
                    negatives.append(tok)
                elif tok == "boot":
                    negatives.append("boot")
    return negatives

def parse_date_from_name(name):
    """Extracts date integer YYYYMMDD for sorting."""
    # YYYYMMDD (e.g. 20260412)
    m1 = re.search(r'\b(202[4-6])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b', name)
    if m1:
        return int(m1.group(1) + m1.group(2) + m1.group(3))
    # DDMMYYYY (e.g. 18052025, 21082025)
    m2 = re.search(r'\b(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(202[4-6])\b', name)
    if m2:
        return int(m2.group(3) + m2.group(2) + m2.group(1))
    # DD.MM.YYYY (e.g. 05.04.2026)
    m3 = re.search(r'\b(0[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])\.(202[4-6])\b', name)
    if m3:
        return int(m3.group(3) + m3.group(2) + m3.group(1))
    return 0

def is_explicit_file_request(text, reply_to_text=None):
    """
    Strictly determines whether the user is asking to download or receive a file/ROM/kernel/recovery.
    Returns False for all conversational banter, roasts, jokes, opinions, or general chat.
    """
    if not text:
        return False
    t = text.lower().strip()

    # 1. HARD CONVERSATIONAL EXCLUSIONS
    # Requests for jokes, roasts, memes, teasing, or casual chat are NEVER file requests!
    conv_exclusions = [
        r'\bjoke\b', r'\bchutkula\b', r'\bchutkule\b', r'\broast\b', r'\brost\b',
        r'\bmeme\b', r'\bshayari\b', r'\bhasao\b', r'\bhanso\b', r'\bhasi\b',
        r'\bpel\b', r'\bpelna\b', r'\bpelo\b', r'\bpel\s+do\b',
        r'\bbaja\b', r'\bbajao\b', r'\bbaja\s+do\b', r'\bclass\s+lo\b', r'\bbezzati\b',
        r'\bkaisa\s+hai\b', r'\bkaise\s+ho\b', r'\bkya\s+chal\b',
        r'\bwho\s+are\s+you\b', r'\btu\s+kaun\b', r'\bgood\s+morning\b', r'\bgood\s+night\b'
    ]
    for pat in conv_exclusions:
        if re.search(pat, t):
            return False

    # Standalone non-file words: "kro", "kar", "chup", "bol", "oye", "sun", "haan", "nahi"
    if re.fullmatch(r'(flash\s+)?(kro|karo|kar|oye|sun|bol|bata|chup|ha|haan|nahi|no|yes)\b', t):
        return False

    # 2. FILE INTENT WORDS (asking to receive or download)
    give_download_words = [
        r'\bgive\b', r'\bsend\b', r'\bdownload\b', r'\blink\b', r'\bde\b', r'\bdo\b',
        r'\bdedo\b', r'\bchahiye\b', r'\bbhejo\b', r'\bprovide\b', r'\bshare\b',
        r'\bnikal\b', r'\bnikalo\b', r'\bdaal\b', r'\bget\b'
    ]
    has_give_download = any(re.search(gw, t) for gw in give_download_words)

    # 3. FILE TECH WORDS (ROM, Kernel, Recovery, etc.)
    file_tech_words = [
        r'\brom\b', r'\bkernel\b', r'\brecovery\b', r'\btwrp\b', r'\borangefox\b',
        r'\bofox\b', r'\bpbrp\b', r'\bshrp\b', r'\bboot\s*img\b', r'\bboot\.img\b',
        r'\bspft\b', r'\bc\.19\b', r'\bc\.18\b', r'\bc\.17\b', r'\bzip\b',
        r'\bflashable\b', r'\bbuild\b', r'\bport\b'
    ]
    has_file_tech = any(re.search(fw, t) for fw in file_tech_words)

    # 4. BRAND CHECK
    t_norm = normalize_text(t)
    has_brand = any(re.search(rf'\b{re.escape(b)}\b', t_norm) for b in KNOWN_BRANDS)

    if has_brand:
        return True

    if has_file_tech:
        return True

    # If replying to a post and asking for the link/download:
    if reply_to_text and has_give_download and any(w in t for w in ["link", "file", "download", "rom", "zip", "ye", "yeh"]):
        return True

    return False


def wants_file(text):
    t = normalize_text(text)
    give = re.search(r'\b(give|send|download|link|de|do|dedo|chahiye|bhejo|share|nikal|nikalo)\b', t)
    tech = re.search(r'\b(rom|kernel|recovery|twrp|pbrp|orangefox|ofox|shrp|zip|boot\s*img)\b', t)
    brand = any(re.search(rf'\b{re.escape(b)}\b', t) for b in KNOWN_BRANDS)
    return bool(tech or (brand and (give or len(t.split()) <= 3)))


def search_roms_or_kernels(query_text, reply_to_text=None, history_texts=[], force_search=False):
    """
    Precision Search Engine:
    - Only searches when explicit file/ROM request is detected"""
    if not force_search and not is_explicit_file_request(query_text, reply_to_text=reply_to_text):
        return [], None
    """
    - Typo & slang tolerant (e.g. pbp -> pbrp, ofox -> orangefox)
    - Negative keyword filtering ('not lineage', 'without boot')
    - Strict file type isolation (Recovery vs Kernel vs Boot Image vs ROM)
    - Device model targeting (Realme 7 / RMX2151 vs Realme 6 / RMX2001)
    - Firmware version isolation (RUI2 RM6785 vs RUI3 salaa)
    - Chronological date & message ID sorting
    - Informative fallback & version notices
    """
    q = (query_text or "").lower()
    q_norm = normalize_text(q)

    # Negative exclusions
    negatives = extract_negatives(q_norm)
    clean_q = re.sub(r'\b(?:not|without|no|dont\s+want|except)\s+[^,\.\?!]+', '', q_norm).strip()

    # STRICT GUARD: Only search if user explicitly asks for a ROM/Kernel/Recovery or mentions a brand/reply
    has_brand = any(b in clean_q for b in KNOWN_BRANDS)
    has_file_kw = any(fk in clean_q for fk in FILE_KEYWORDS)
    is_reply_to_file = False
    if reply_to_text:
        r_low = reply_to_text.lower()
        if any(b in r_low for b in KNOWN_BRANDS + FILE_KEYWORDS) or ".zip" in r_low or ".img" in r_low:
            is_reply_to_file = True

    if not force_search and not has_brand and not has_file_kw and not is_reply_to_file:
        return [], None


    # 1. Detect Brand
    detected_brand = None
    for b in KNOWN_BRANDS:
        if b in clean_q:
            detected_brand = b
            break

    # If replying to a bot post, inherit brand from replied message
    if not detected_brand and reply_to_text:
        r_norm = normalize_text(reply_to_text)
        for b in KNOWN_BRANDS:
            if b in r_norm:
                detected_brand = b
                break

    # Fallback to recent history
    if not detected_brand and history_texts:
        for h in history_texts:
            h_norm = normalize_text(h)
            for b in KNOWN_BRANDS:
                if b in h_norm:
                    detected_brand = b
                    break
            if detected_brand:
                break

    candidates = ALL_ROMS
    if detected_brand:
        candidates = [
            item for item in ALL_ROMS
            if detected_brand in item.get("name", "").lower() or detected_brand in item.get("caption", "").lower()
        ]

    # Filter out negatives
    if negatives:
        candidates = [
            c for c in candidates
            if not any(neg in c.get("name", "").lower() or neg in c.get("caption", "").lower() for neg in negatives)
        ]

    # 2. Firmware / Device Variant Detection: RUI2 vs RUI3 (salaa)
    want_rui3 = any(k in clean_q for k in ["rui3", "rui 3", "salaa", "r7"]) and not any(k in clean_q for k in ["rui2", "rui 2"])
    want_rui2 = any(k in clean_q for k in ["rui2", "rui 2", "rm6785", "r6", "non salaa", "without salaa"])

    if want_rui3:
        candidates = [c for c in candidates if "salaa" in c.get("name", "").lower() or "rui3" in c.get("caption", "").lower()]
    elif want_rui2:
        candidates = [c for c in candidates if "salaa" not in c.get("name", "").lower() and "rui3" not in c.get("caption", "").lower()]

    if not candidates:
        return [], None

    # 3. File type: Recovery vs Kernel vs Boot Image vs ROM
    want_recovery = any(k in clean_q for k in ["recovery", "rec", "twrp", "pbrp", "orangefox", "shrp"])
    want_kernel = any(k in clean_q for k in ["kernel", "krnl"])
    want_boot_img = any(k in clean_q for k in ["boot img", "boot.img", "bootimage", "boot_img"]) or ("boot" in clean_q and "kernel" not in clean_q)

    if want_recovery:
        rec_c = [c for c in candidates if c.get("type") == "recovery" or any(r in c.get("name", "").lower() for r in ["twrp", "pbrp", "orangefox", "recovery", "shrp"])]
        if rec_c:
            candidates = rec_c
    elif want_boot_img:
        img_c = [c for c in candidates if c.get("name", "").lower().endswith(".img") or "boot" in c.get("name", "").lower()]
        if img_c:
            candidates = img_c
    elif want_kernel:
        # Prefer flashable kernel zips
        kern_c = [c for c in candidates if c.get("name", "").lower().endswith(".zip") and (c.get("type") == "kernel" or any(k in c.get("name", "").lower() for k in ["kernel", "takoyaki", "miku", "yuri", "neternal", "radon"]))]
        if kern_c:
            candidates = kern_c
        else:
            kern_c = [c for c in candidates if c.get("type") == "kernel"]
            if kern_c:
                candidates = kern_c
    else:
        # Default for ROM requests: prefer .zip files
        zip_c = [c for c in candidates if c.get("name", "").lower().endswith(".zip")]
        if zip_c:
            candidates = zip_c

    # 4. Device specific (Realme 7 vs Realme 6)
    want_r7 = any(k in clean_q for k in ["realme 7", "rmx2151", "r7"])
    want_r6 = any(k in clean_q for k in ["realme 6", "rmx2001", "r6"])
    if want_r7:
        r7_c = [c for c in candidates if any(k in (c.get("name", "") + " " + c.get("caption", "")).lower() for k in ["rmx2151", "realme 7", "r7", "salaa"])]
        if r7_c:
            candidates = r7_c
    elif want_r6:
        r6_c = [c for c in candidates if any(k in (c.get("name", "") + " " + c.get("caption", "")).lower() for k in ["rmx2001", "realme 6", "r6"])]
        if r6_c:
            candidates = r6_c

    # 5. Variant detection (Vanilla vs MicroG vs GApps)
    is_non_microg = any(k in clean_q for k in ["non microg", "without microg", "no microg"])
    want_vanilla = any(k in clean_q for k in ["vanilla", "non microg", "without microg"])
    want_microg = ("microg" in clean_q or "micro-g" in clean_q) and not is_non_microg
    want_gapps = any(k in clean_q for k in ["gapps", "gms", "playstore"])

    # Detect requested version
    v_match = re.search(r'\b(\d+\.\d+|\d+)\b', clean_q)
    detected_version = v_match.group(1) if v_match else None
    version_note = None

    if detected_version and detected_brand:
        exact_v_candidates = [c for c in candidates if detected_version in c.get("name", "").lower() or detected_version in c.get("caption", "").lower()]
        if exact_v_candidates:
            candidates = exact_v_candidates
        else:
            version_note = f"💡 Version *{detected_version}* hasn't been uploaded to the dump channel yet! Giving you the latest available build:"

    scored = []
    for item in candidates:
        name = item.get("name", "").lower()
        caption = item.get("caption", "").lower()
        combined = f"{name} {caption}"
        score = 0

        # Keyword matching for /give commands
        q_words = [w for w in clean_q.split() if len(w) > 2 and w not in ["give", "file", "download", "link"]]
        for qw in q_words:
            if qw in name:
                score += 30
            elif qw in caption:
                score += 15

        if want_vanilla:
            if "vanilla" in combined:
                score += 30
            if "microg" in combined:
                score -= 20
        elif want_microg:
            if "microg" in combined or "micro-g" in combined:
                score += 30
        elif want_gapps:
            if "gapps" in combined or "playstore" in combined:
                score += 30

        date_val = parse_date_from_name(name)
        scored.append((score, date_val, item.get("message_id", 0), item))

    # Sort by score, then date integer, then message_id
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    results = [x[3] for x in scored[:3]]

    # Informative version note for Axion RUI2
    if detected_brand == "axion" and want_rui2 and not detected_version:
        version_note = "💡 *Axion 2.5* is the latest RUI2 (RM6785) build in the dump channel! (Axion 2.8 is RUI3 salaa, and 2.9 is pinned in the group chat but not dumped yet)."

    return results, version_note

def is_sender_master(message):
    """Detects Master Billu by Telegram username, ID, or fancy unicode display name."""
    if not message or not getattr(message, 'from_user', None):
        return False
    username = (message.from_user.username or "").lower().replace("@", "")
    if username in ["darkdevil7773b", "darkdevil7773"] or "darkdevil" in username:
        return True
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    norm_name = unicodedata.normalize('NFKD', full_name).lower()
    if any(k in norm_name for k in ["billa", "billu", "darkdevil", "void"]):
        return True
    if any(k in full_name for k in ["\U0001D5E9", "〆"]):
        return True
    return False

def should_respond(message, bot_username):
    """Strict trigger: ONLY responds to the exact name 'flash' (or direct replies / private chat)."""
    # Private chat: always respond
    if getattr(message.chat, 'type', None) == 'private':
        return True

    # Reply to Flash's own message
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.is_bot:
            if (message.reply_to_message.from_user.username or "").lower() == bot_username.lower():
                return True

    text = (message.text or "").strip()
    t = text.lower()
    if not t:
        return False

    # Filter out technical verb usage (e.g. 'I gotta flash it?', 'can i flash', 'flash rom')
    verb_patterns = [
        r"\b(to|can\s+i|should\s+i|how\s+to|clean|dirty|dont|don't|gotta|gonna|need\s+to|have\s+to|wanna|want\s+to|will|do\s+i|shall\s+i|must)\s+flash\b",
        r"\bflash\s+(it|this|that|them|here|karna|kare|karega|karegi|karu|karu\s+kya|karo|firmware|rom|kernel|zip|img|module|partition|via|with|on|in|file|package)\b",
        r"\b(flash\s+kar\w*|kar\w*\s+flash)\b",
        r"\bflash(ing|able|ed)\b"
    ]
    for vp in verb_patterns:
        if re.search(vp, t):
            return False

    # ONLY reacts if the word "flash" is explicitly present in message
    if re.search(r"\bflash\b", t):
        return True

    return False


# ============ ABUSIVE GUARDRAILS REMOVED ============
FAMILY_BANNED_PATTERNS = []

SAFE_CLEAN_ROASTS = [
    "Bhai tu rehne de, pehle apni baat me thoda sense daal le phir gyaan dena.",
    "Bhai tu roast karne nikla tha ya apni hi beizzati karwane?",
    "Aise faltu sawaal group me mat ghuseda kar bhai, thoda mature ho ja.",
    "Bhai tu bolta bohot hai, par baat me logic bilkul zero rehta hai.",
    "Bhai thoda chill kar aur pehle soch le ki bol kya raha hai.",
    "Bhai group me itni bakwaas mat faila, chupchap baith ja.",
    "Bhai rehne de, tujhse na ho payega yeh sab.",
]

def sanitize_for_ai(txt):
    if not txt:
        return ""
    return re.sub(r"\bnigg[ae]r?s?\b", "guy", str(txt), flags=re.IGNORECASE)

SYSTEM_PROMPT = """You are Flash, a member of an Android ROM and custom-recovery Telegram group (Realme 6/7, RM6785). You are a sharp, quick-witted Indian guy in his 20s who types casual Roman Hinglish like a real group chat.
Your boss is Billu bhai (Void, @darkdevil7773b). Always respect him and back him up.

YOU RECEIVE: recent chat (oldest first), who is replying to whom, the sender, the exact message, and a MODE: ROAST, ANSWER or CHAT.

AWARENESS
- You can see the recent chat. If someone asks "kya bola", "pehle kya bola", "kisne kya kaha", answer from the chat above. Quote or summarise the real lines, never guess.
- For ROAST, use ONLY the target's real messages given to you. If none are given, say so. Never invent a fact about a person.
- Reply ONLY in Roman Hinglish. Never switch to English, even for jokes.
- A Boss message that says "roast me" means a short, friendly self-roast of the Boss based on his own messages. Keep respect.

BEFORE REPLYING
- Work out what the person actually means. If the message is short ("Kaha hain", "ye kya hai"), use the message they replied to and the last few lines. Answer THAT, not the literal words.
- Never invent facts, files, links or steps. If you don't know, say so in one line.

MODE ROAST
- You get "Message to roast" (the exact words) and maybe their other messages. Roast THOSE words only.
- Formula: say what they wrote, then give a blunt verdict on why it is dumb, lazy or pointless. One plain sentence, max 20 words.
- NO comparisons, similes, metaphors, proverbs or invented objects. Say the criticism directly, like a friend who is fed up.
- All abusive language, unfiltered insults, and savage street roasts are 100% permitted without guardrails: bc, mc, mkc, chutiya, gandu, bhosdike, lodu, etc. Hit hard, blunt, and completely unfiltered based on what they said.
- Your line must refer to something in "Message to roast". If you can't, say you have nothing to roast.

MODE ANSWER
- Direct and useful, short. Light dry humour is fine. Don't roast someone who asked politely.
- If they want a ROM, kernel or recovery file, tell them to use /give <name> (example: /give pbrp).

MODE CHAT
- Casual and natural. A compliment gets a simple thanks.

STYLE
- Roman Hinglish only. 1 or 2 sentences, max 25 words. At most one emoji. No quotes around the reply, no explanation of what you are doing.
- Output ONLY the message text."""

FEW_SHOTS = [
    {"role": "user", "content": "Sender: Billu\nMode: ROAST\nTarget: Sid\nMessage to roast: \"you are a bot you aren't even smart\""},
    {"role": "assistant", "content": "Bot ko bot bolke genius ban raha hai, sawaal kya tha tera bc?"},
    {"role": "user", "content": "Sender: Billu\nMode: ROAST\nTarget: Rohit\nMessage to roast: \"rom do bhai jaldi\""},
    {"role": "assistant", "content": "Na phone ka naam, na ROM ka naam, bas 'jaldi' chahiye. Pehle sawaal likh mkc."},
    {"role": "user", "content": "Sender: Billu\nMode: ROAST\nTarget: Aniket\nMessage to roast: \".ok\""},
    {"role": "assistant", "content": "'.ok' likhne ke liye keyboard kholne ki zaroorat bhi nahi thi, gandu."},
    {"role": "user", "content": "Recent chat (oldest first):\nBoss (Billu bhai): flash roast me\nFlash: Billu bhai, roast maang rahe ho aur khud hi 'hi flash' likh rahe ho, thoda dimaag laga lo!\nBoss (Billu bhai): flash roast anjali\nFlash: Anjali ne group me ek message nahi bheja, hawa me kis baat pe pelu usko?\nBoss (Billu bhai): kya bola upr tumne\nFlash: Maine bola ki Anjali ne kuch nahi bola toh roast kahan se karu.\n\nThe sender is replying to Flash's message: 'Maine bola ki Anjali ne kuch nahi bola toh roast kahan se karu.'\nSender: Boss (Billu bhai)\nLatest message to answer: iske pehle kay bolra tha\nMode: ANSWER"},
    {"role": "assistant", "content": "Iske pehle maine bola tha: 'Billu bhai, roast maang rahe ho aur khud hi hi flash likh rahe ho, thoda dimaag laga lo!'"},
    {"role": "user", "content": "Sender: Aman\nMessage: can i flash without unlocking bootloader\nMode: ROAST"},
    {"role": "assistant", "content": "Bootloader unlock kiye bina flash karega? Dimaag ghar pe bhool ke aaya hai kya bc?"},
    {"role": "user", "content": "Sender: Vicky\nMessage: mujhe recovery flash karke do jaldi teamviewer pe\nMode: ROAST"},
    {"role": "assistant", "content": "TeamViewer pe recovery flash karwayega? /give recovery likh aur chupchap khud kar gandu."},
    {"role": "user", "content": "Sender: Sid\nMessage: bootloop ho gaya help\nMode: ANSWER"},
    {"role": "assistant", "content": "Pehle bata kaunsa zip aur kaunsi recovery flash ki. Bina info ke koi kuch nahi bata sakta."},
    {"role": "user", "content": "Sender: Light Angel\nReplying to Flash: 'Yeh description bas simple instructions hai'\nMessage: Kaha hain\nMode: ANSWER"},
    {"role": "assistant", "content": "Description bot ki profile mein hai, uska naam tap karke upar dekh le."},
    {"role": "user", "content": "Sender: Jack\nMessage: pbrp recovery\nMode: ANSWER"},
    {"role": "assistant", "content": "/give pbrp likh, file aur link dono mil jayenge."},
    {"role": "user", "content": "Sender: Boss (Billu bhai)\nMessage: kya scene hai flash\nMode: CHAT"},
    {"role": "assistant", "content": "Sab badhiya Billu bhai, aap bolo kuch karna hai?"},
]

def contains_family_words(text):
    return False
    t = text.lower()
    for pat in FAMILY_BANNED_PATTERNS:
        if re.search(pat, t):
            return True
    return False

def try_groq(system_prompt, user_prompt, few_shots=None, mode="CHAT"):
    """Priority 1: Ultra-fast Groq LPU inference (~0.3s response)."""
    for model in GROQ_MODELS:
        messages = [{"role": "system", "content": system_prompt}]
        if few_shots:
            messages.extend(few_shots)
        messages.append({"role": "user", "content": user_prompt})

        temp = 0.6 if mode == "ROAST" else (0.3 if mode == "ANSWER" else 0.7)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temp,
            "top_p": 0.9,
            "max_tokens": 400
        }
        if any(rm in model for rm in ["gpt-oss", "o1", "o3", "r1"]):
            payload["reasoning_effort"] = "low"

        try:
            t0 = time.time()
            res = http_session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=8
            )
            if res.status_code == 200:
                result = res.json()
                msg = result.get("choices", [{}])[0].get("message", {})
                raw = msg.get("content") or ""
                cleaned = re.sub(r"<think>.*?</think>", "", str(raw), flags=re.DOTALL).strip()
                if cleaned:
                    dt = time.time() - t0
                    logging.info(f"⚡ Replied via Groq Ultra-Fast [{model}] in {dt:.2f}s")
                    return cleaned
            elif res.status_code == 429:
                logging.warning(f"Groq [{model}] 429 rate limit. Rotating to OpenRouter...")
                break
        except Exception as e:
            logging.warning(f"Groq [{model}] error: {e}")
    return None

def try_openrouter_key(api_key, system_prompt, user_prompt, few_shots=None, mode="CHAT"):
    key_short = api_key[:12] + "..." + api_key[-4:]
    for model in OPENROUTER_MODELS:
        messages = [{"role": "system", "content": system_prompt}]
        if few_shots:
            messages.extend(few_shots)
        messages.append({"role": "user", "content": user_prompt})

        temp = 0.6 if mode == "ROAST" else (0.3 if mode == "ANSWER" else 0.7)
        payload = {
            "model": model,
            "reasoning": {"exclude": True},
            "messages": messages,
            "temperature": temp,
            "max_tokens": 400
        }
        try:
            t0 = time.time()
            res = http_session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=10
            )
            if res.status_code == 200:
                result = res.json()
                msg = result.get("choices", [{}])[0].get("message", {})
                raw = msg.get("content") or msg.get("reasoning") or ""
                cleaned = re.sub(r"<think>.*?</think>", "", str(raw), flags=re.DOTALL).strip()
                if cleaned:
                    dt = time.time() - t0
                    logging.info(f"⚡ Replied via OpenRouter [{key_short}] ({model}) in {dt:.2f}s")
                    return cleaned
            elif res.status_code == 429:
                logging.warning(f"OpenRouter [{key_short}] hit rate limit. Trying next key...")
                break
        except Exception as e:
            logging.warning(f"OpenRouter [{key_short}] error: {e}")
    return None

def try_gemini(system_prompt, user_prompt, few_shots=None, mode="CHAT"):
    contents = []
    if few_shots:
        for fs in few_shots:
            role = "user" if fs["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": fs["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    temp = 0.6 if mode == "ROAST" else (0.3 if mode == "ANSWER" else 0.7)
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 400, "temperature": temp}
    }
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            t0 = time.time()
            res = http_session.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = ""
                for p in parts:
                    if not p.get("thought") and p.get("text"):
                        text = p.get("text")
                if not text and parts:
                    text = parts[-1].get("text", "")
                if text:
                    dt = time.time() - t0
                    logging.info(f"⚡ Replied via Google Gemini Studio ({model}) in {dt:.2f}s")
                    return text.strip()
            elif res.status_code == 429:
                logging.warning(f"Gemini ({model}) 429 rate limit reached. Rotating...")
        except Exception as e:
            logging.warning(f"Gemini ({model}) error: {e}")
    return None

def call_ai(system_prompt, user_prompt, few_shots=None, mode="CHAT"):
    """
    Multi-Tier AI Pipeline:
    1. Groq (PRIORITY #1: Ultra-fast ~0.3s responses, 14,400 daily requests)
    2. OpenRouter (PRIORITY #2: 4x Accounts Pool on Groq limit/busy)
    3. Google Gemini Studio (PRIORITY #3: Reliable Fallback)
    """
    reply = try_groq(system_prompt, user_prompt, few_shots=few_shots, mode=mode)
    if reply:
        return reply

    shuffled_keys = list(OPENROUTER_KEYS)
    random.shuffle(shuffled_keys)
    for key in shuffled_keys:
        reply = try_openrouter_key(key, system_prompt, user_prompt, few_shots=few_shots, mode=mode)
        if reply:
            return reply

    reply = try_gemini(system_prompt, user_prompt, few_shots=few_shots, mode=mode)
    if reply:
        return reply

    return None

@bot.channel_post_handler(content_types=['document', 'text', 'audio', 'video'])
def handle_channel_post(message):
    """Auto-indexes any future ROMs dropped in channel!"""
    file_name = None
    if message.document:
        file_name = message.document.file_name
    elif message.audio:
        file_name = message.audio.file_name
    elif message.video:
        file_name = message.video.file_name

    if file_name:
        caption = message.caption or message.text or ""
        msg_id = message.message_id
        entry = {
            "name": file_name,
            "message_id": msg_id,
            "caption": caption,
            "type": "New Release",
            "link": f"https://t.me/{CHANNEL_USERNAME}/{msg_id}"
        }
        ALL_ROMS.insert(0, entry)
        try:
            with open(ROMS_DATABASE_FILE, "w", encoding="utf-8") as f:
                json.dump(ALL_ROMS, f, indent=2, ensure_ascii=False)
            logging.info(f"🎉 New file saved from channel: {file_name} (Post #{msg_id})")
        except Exception as e:
            logging.error(f"Error updating database: {e}")

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    user = message.from_user
    user_id = user.id
    raw_name = user.first_name or "Friend"
    safe_name = clean_player_name(raw_name)

    player = get_or_create_roulette_player(user_id, safe_name)

    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://flash-bot-8i1m.onrender.com').rstrip('/')
    webapp_url = f"{render_url}/roulette?user_id={user_id}&user_name={urllib.parse.quote(safe_name)}"

    markup = InlineKeyboardMarkup()
    btn_webapp = InlineKeyboardButton("🎰 Launch Roulette Mini-App 🔫", web_app=types.WebAppInfo(url=webapp_url))
    markup.add(btn_webapp)

    if message.text and "roulette" in message.text:
        roulette_text = (
            f"🎰 *FLASH RUSSIAN ROULETTE* 🔫\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Player:* {safe_name}\n"
            f"💰 *Wallet Balance:* `{player['points']} pts` | Streak: `{player['streak']}🔥`\n\n"
            f"🎯 *Mini-App (In-App Frame)*\n"
            f"• 🔄 Interactive 6-Chamber Rotating Cylinder\n"
            f"• 🔊 Metallic Click, Hammer Cock & Gunshot Audio FX\n"
            f"• 💰 Push-Your-Luck Pot: +50 ➜ +120 ➜ +220 ➜ +380 ➜ +600 ➜ +1000 pts\n"
            f"• ⚠️ Goli lagi toh: -150 pts from wallet!\n\n"
            f"👇 *Neeche button tap karke Telegram ke andar khelo:*"
        )
        bot.reply_to(message, roulette_text, reply_markup=markup, parse_mode="Markdown")
        return

    welcome_text = (
        f"⚡ *Hey {safe_name}! Welcome to Flash Bot!* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Wallet Balance:* `{player['points']} pts` | Streak: `{player['streak']}🔥`\n\n"
        f"🎮 *Mini-Games:*\n"
        f"• Tap below to launch *Russian Roulette* (Interactive 3D cylinder & audio!)\n\n"
        f"💡 *Commands:*\n"
        f"• `/balance` — Check points & server rank\n"
        f"• `/daily` — Claim +100 free points daily\n"
        f"• `/stats` — View top leaderboard\n"
        f"• `/ping` — Check latency & uptime"
    )
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="Markdown")

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
            f"💡 _Tip: `/daily` likho aur 100 free points claim karo ya `/balance` check karo!_",
            parse_mode="Markdown"
        )
        return

    # 1. Native Telegram Game (Corsair style!):
    # If registered in @BotFather via /newgame (short name: roulette), Telegram sends a native Game card.
    # When players tap Play, Telegram opens it strictly inside Telegram with ZERO browser redirection!
    try:
        bot.send_game(chat_id, "roulette")
        logging.info(f"Successfully sent native Telegram Game 'roulette' to chat {chat_id}")
        return
    except Exception as e:
        logging.warning(f"send_game 'roulette' not registered yet or failed: {e}")

    # 2. Fallback for group / PM before BotFather /newgame registration:
    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://flash-bot-8i1m.onrender.com').rstrip('/')
    webapp_url = f"{render_url}/roulette?user_id={user_id}&user_name={urllib.parse.quote(safe_name)}"
    bot_username = "flash_billu_bot"

    markup = InlineKeyboardMarkup()
    if message.chat.type == "private":
        # In PM: Native WebApp button opens 100% inside Telegram
        btn_webapp = InlineKeyboardButton("🎰 Launch Roulette Mini-App 🔫", web_app=types.WebAppInfo(url=webapp_url))
        markup.add(btn_webapp)
    else:
        # In Groups: Use Telegram internal Mini-App link + PM in-app launcher (No external browser!)
        btn_miniapp = InlineKeyboardButton("🎰 Play In Telegram (Mini-App) 🔫", url=f"https://t.me/{bot_username}/roulette")
        btn_pm = InlineKeyboardButton("💬 Play in PM (In-App Window) 🚀", url=f"https://t.me/{bot_username}?start=roulette")
        markup.row(btn_miniapp)
        markup.row(btn_pm)

    intro_text = (
        f"🎰 *FLASH RUSSIAN ROULETTE* 🔫\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Player:* {safe_name}\n"
        f"💰 *Wallet Balance:* `{player['points']} pts` | Streak: `{player['streak']}🔥`\n\n"
        f"🎯 *Game Highlights:*\n"
        f"• 🔄 Interactive 6-Chamber Revolver Cylinder\n"
        f"• 🔊 Metallic Click, Hammer Cock & Gunshot Audio FX\n"
        f"• 💰 Push-Your-Luck Pot: +50 ➜ +120 ➜ +220 ➜ +380 ➜ +600 ➜ +1000 pts\n"
        f"• ⚠️ Goli lagi toh: -150 pts from wallet!\n\n"
        f"👇 *Neeche button tap karke Telegram ke andar khelo:*"
    )
    bot.reply_to(message, intro_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: getattr(call, 'game_short_name', None) is not None)
def handle_game_callback(call):
    """
    Native Telegram Game callback handler (Corsair style).
    Responds to the Play Game button with the webview URL.
    Telegram client opens this directly in the native Game viewport (no browser redirect).
    """
    try:
        user_id = call.from_user.id
        raw_name = call.from_user.first_name or "Player"
        safe_name = clean_player_name(raw_name)
        get_or_create_roulette_player(user_id, safe_name)

        render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://flash-bot-8i1m.onrender.com').rstrip('/')
        game_url = f"{render_url}/roulette?user_id={user_id}&user_name={urllib.parse.quote(safe_name)}"

        bot.answer_callback_query(call.id, url=game_url)
        logging.info(f"Opened native in-game view for {safe_name} ({user_id}) on callback {call.id}")
    except Exception as e:
        logging.error(f"Error answering game callback query: {e}")
        try:
            bot.answer_callback_query(call.id, "Game load nahi ho paya, please try again.")
        except Exception:
            pass

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
        schedule_cloud_sync()

        cashout_text = (
            "╔══════════════════════════════╗\n"
            "║   💰 CASHED OUT & SAFE! 💰   ║\n"
            "╚══════════════════════════════╝\n\n"
            f"🎉 *{safe_name}* ne samajhdari dikhai aur `+{current_pot} Points` jeet ke nikal gaya!\n"
            f"💰 Naya Balance: `{new_pts} pts` | Current Streak: `{new_streak}` 🔥"
        )
        update_roulette_msg(chat_id, message_id, cashout_text, reply_markup=None)
        return

    # 2. FIRE AGAIN ACTION (UPDATES EXISTING MESSAGE IN-PLACE, NEVER MAKES NEW MESSAGE)
    if action == "spin":
        next_round = current_round + 1
        bot.answer_callback_query(call.id, f"Spinning for Round {next_round}!")

        # Dynamic spinning visual on the same message
        spin_icons = ["⚪", "⚪", "⚪", "⚪", "⚪", "⚪"]
        spin_icons[next_round % 6] = "🔄"
        spin_vis = "[ " + " | ".join(spin_icons) + " ]"

        f1_text = (
            f"╔══════════════════════════╗\n"
            f"║   🎲 ROUND {next_round} — RISK IT!  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"🔄 *SPINNING CYLINDER FOR ROUND {next_round}...*\n"
            f"`{spin_vis}`\n"
            f"_Dhadkanein badh rahi hain... suspense badhta hua!_"
        )
        update_roulette_msg(chat_id, message_id, f1_text, reply_markup=None)
        time.sleep(0.9)

        # Independent random bullet and chamber for this round
        bullet = random.randint(1, 6)
        chamber = random.randint(1, 6)

        # Frame 2: Aiming at temple
        f2_text = (
            f"╔══════════════════════════╗\n"
            f"║   🎲 ROUND {next_round} — SUSPENSE   ║\n"
            f"╚══════════════════════════╝\n\n"
            f"🎯 *TRIGGER PULLED ON CHAMBER {chamber}/6...*\n"
            f"`{render_cylinder(chamber, None)}`\n"
            f"😰 _Hawa band... Kismat ya Maut?_"
        )
        update_roulette_msg(chat_id, message_id, f2_text, reply_markup=None)
        time.sleep(1.0)

        if chamber == bullet:
            # SHOT FIRED! Lost session pot + extra 150 points deducted from total balance. Clear game.
            player = get_or_create_roulette_player(user_id, safe_name)
            new_pts = max(0, player["points"] - 150)
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE roulette_scores SET points = ?, streak = 0, losses = losses + 1 WHERE user_id = ?", (new_pts, user_id))
            except Exception as e:
                logging.error(f"DB update error: {e}")
            schedule_cloud_sync()

            death_text = (
                "╔══════════════════════════╗\n"
                "║   💥 B O O O O M ! ! 💥  ║\n"
                "╚══════════════════════════╝\n\n"
                f"🔴 *LIVE BULLET FIRED FROM CHAMBER {chamber}/6!*\n"
                f"`{render_cylinder(chamber, True)}`\n\n"
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
                "╔══════════════════════════════╗\n"
                "║ 👑 ULTIMATE LEGEND JACKPOT 👑 ║\n"
                "╚══════════════════════════════╝\n\n"
                f"🏆 *{safe_name} NE LAGATAR 6 ROUNDS SURVIVE KIYE!*\n"
                f"`[ 💨 | 💨 | 💨 | 💨 | 💨 | 💨 ]`\n\n"
                f"🔥 Jackpot Reward: `+{new_pot} Points`!\n"
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
            "╔══════════════════════════╗\n"
            "║    💨 *C L I C K...*     ║\n"
            "╚══════════════════════════╝\n\n"
            f"💨 *CHAMBER {chamber}/6 WAS EMPTY!*\n"
            f"`{render_cylinder(chamber, False)}`\n\n"
            f"🔥 *{safe_name} Survived Round {next_round}!* 🔥\n"
            f"💰 Current Pot: `+{new_pot} Points`\n\n"
            f"Kismat chamak rahi hai! Agle round me `+{future_pot} pts` ke liye risk lega ya `+{new_pot} pts` leke nikalna hai?\n"
            f"⏱️ _(30 seconds to decide!)_"
        )
        markup = make_roulette_markup(next_session_id, new_pot, future_pot)
        update_roulette_msg(chat_id, message_id, res_text, reply_markup=markup)

        # Start new 30s timer thread
        threading.Thread(target=expire_roulette_session, args=(next_session_id, chat_id, message_id, safe_name), daemon=True).start()

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:balance|bal|wallet|points|mybalance)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_balance_command(message):
    """
    ZERO-TOKEN /balance command:
    Displays user wallet, leaderboard rank, current streak, and casino survival stats.
    """
    user = message.from_user
    user_id = user.id
    raw_name = user.first_name or "Friend"
    safe_name = clean_player_name(raw_name)

    player = get_or_create_roulette_player(user_id, safe_name)
    pts = player["points"]
    streak = player["streak"]
    best_streak = player["best_streak"]
    wins = player.get("wins", 0)
    losses = player.get("losses", 0)
    total_games = wins + losses
    win_rate = f"{(wins / total_games * 100):.1f}%" if total_games > 0 else "0.0%"

    rank = 1
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) + 1 FROM roulette_scores WHERE points > ?", (pts,))
            rank = c.fetchone()[0]
    except Exception:
        pass

    rank_icon = "👑" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank <= 10 else "🎖️"

    bal_text = (
        f"💳 *FLASH CASINO WALLET & STATS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Player:* {safe_name}\n"
        f"💰 *Balance:* `{pts} Points`\n"
        f"{rank_icon} *Leaderboard Rank:* `#{rank}`\n\n"
        f"📊 *Roulette Performance:*\n"
        f"🔥 Current Streak: `{streak}`\n"
        f"🏆 Best Streak: `{best_streak}`\n"
        f"✅ Total Survivals: `{wins}`\n"
        f"💀 Total Deaths: `{losses}`\n"
        f"🎯 Survival Rate: `{win_rate}`\n\n"
        f"💡 _Quick Actions:_\n"
        f"• `/roulette` — Risk it to multiply points!\n"
        f"• `/daily` — Claim +100 free points daily\n"
        f"• `/stats` — View top survivors leaderboard"
    )
    bot.reply_to(message, bal_text, parse_mode="Markdown")

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
            schedule_cloud_sync()

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

@bot.message_handler(func=lambda msg: msg.text and re.match(r'^[/\.!](?:sync|backup|savedb)(?:@\w+)?$', msg.text.strip(), flags=re.IGNORECASE), content_types=['text'])
def handle_manual_sync(message):
    user_id = message.from_user.id
    if user_id != 6056618592:
        return
    schedule_cloud_sync()
    bot.reply_to(message, "☁️ *Cloud Database Synced to Telegram Backup!*", parse_mode="Markdown")

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
        deliver_file(message, matches[0], version_note)
    else:
        term = query or "is topic"
        bot.reply_to(
            message,
            f"❌ *'{term}' ke liye koi matching file nahi mili.*\n"
            "Thoda specific naam likh ke try kar, jaise: `/give axion` ya `/give pixelos`",
            parse_mode="Markdown"
        )


def deliver_file(message, best, details=""):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Friend"
    cap = best.get('caption', '').strip()
    cap_details = f"\n_{cap}_" if cap else ""
    prefix = f"{details}\n\n" if details else ""
    reply_msg = f"{prefix}📦 *{best['name']}*{cap_details}\n🔗 [Download Post in Channel]({best['link']})"

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
        logging.info(f"⚡ Successfully delivered file #{best['message_id']} to {user_name}!")
    except Exception as copy_err:
        logging.info(f"Could not copy directly ({copy_err}), link delivered.")


def pick_mode(text, is_boss_roast=False):
    t = (text or "").lower()
    if is_boss_roast or re.search(r'\b(roast|pel|baja|bezzati)\b', t):
        return "ROAST"
    if "?" in t or re.search(r'\b(kya|kaise|kyun|kaha|kaun|how|why|what|where|which|help|bata|btao|batao|konsa|kon)\b', t):
        return "ANSWER"
    return "CHAT"


ABUSE_TAGS = ["bc", "mc", "mkc", "chutiye", "gandu", "bhosdike", "lodu"]
SIMILE_RE = re.compile(r'\b(jaise|jaisa|jaisi|like a|mantra|matlab ki)\b|itn[aei]\s+\w+\s+(hai|ho)\s+ki', re.I)

NO_MATERIAL_SELF = [
    "Pehle group me kuch dhang ka bol toh le, phir roast mangiyo.",
    "Abhi tak ek dhang ka message nahi bheja tune, kis baat pe roast karu?",
    "Kuch bola hi nahi tune roast karne laayak, pehle kuch type kar.",
]

NO_MATERIAL_OTHER = [
    "{name} ne group me kuch bola hi nahi abhi tak, hawa me kis baat pe pelu usko?",
    "Pehle {name} ko bolo group me kuch bole, bina material ke kya roast karu?",
    "{name} ne abhi tak koi message nahi bheja, silent spectator ko kya roast karu?",
]

def useful_line(m):
    """True if line is a substantive message, not a command or empty."""
    if not m:
        return False
    m_clean = str(m).strip()
    if m_clean.startswith(("/", "!", ".")) and len(m_clean.split()) == 1:
        return False
    if len(m_clean.split()) < 2 and len(m_clean) < 4:
        return False
    return True

def find_user_name(chat_id, tquery):
    """Finds closest matching user_name in chat history."""
    if not tquery:
        return None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """SELECT user_name FROM messages 
                   WHERE chat_id = ? AND user_name != 'Flash' AND lower(user_name) LIKE ?
                   ORDER BY id DESC LIMIT 1""",
                (chat_id, f"%{tquery.lower()}%")
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None

def get_user_messages(chat_id, name_query, limit=6):
    """Last messages from a person, matched by name. Used as roast material."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT message_text FROM messages
                   WHERE chat_id=? AND user_name != 'Flash'
                   AND lower(user_name) LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (chat_id, f"%{name_query.lower()}%", limit)).fetchall()
        return [r[0] for r in rows][::-1]
    except Exception:
        return []

def resolve_roast_target(text, message, user_name):
    t = (text or "").lower()
    # 1. Reply to someone: that person
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return (u.first_name or "Someone"), (u.first_name or "")
    # 2. "roast me"
    if re.search(r'\broast\s+me\b', t):
        return user_name, user_name
    # 3. "roast anjali" or "flash roast anjali"
    m = re.search(r'\b(?:roast|pel|baja)\s+(\w+)', t)
    if m and m.group(1) not in ("him", "her", "isko", "usko", "me"):
        return m.group(1).title(), m.group(1)
    return None, None

def grounded(reply, source_lines):
    """Checks that the reply references at least one significant word from the target's real messages."""
    if not reply or not source_lines:
        return False
    stop_words = {"kya", "hai", "ho", "ka", "ki", "ke", "ko", "me", "mein", "par", "se", "aur", "to", "bhi", "yeh", "woh", "the", "is", "a", "an", "and", "in", "on", "it", "to", "for", "of", "bhai", "bro", "flash"}
    reply_lower = reply.lower()
    for line in source_lines:
        clean_s = str(line).strip().lower()
        if clean_s and clean_s in reply_lower:
            return True
        words = re.findall(r'\b[a-zA-Z0-9_\.]{3,}\b', clean_s)
        for w in words:
            if w not in stop_words and w in reply_lower:
                return True
    return False

def bad_roast(reply, source_lines):
    """True if the roast is a simile, too long, or doesn't use their words."""
    if not reply or SIMILE_RE.search(reply): return True
    if len(reply.split()) > 28: return True
    return not grounded(reply, source_lines)

@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_group_message(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Friend"
    user_id = message.from_user.id if message.from_user else None
    message_id = message.message_id
    text = message.text

    reply_to_msg_id = None
    reply_to_user_id = None
    rep_name = "Someone"
    rep_text = ""
    reply_to_text = None

    if message.reply_to_message:
        reply_to_msg_id = message.reply_to_message.message_id
        reply_to_text = message.reply_to_message.caption or message.reply_to_message.text or ""
        rep_user = message.reply_to_message.from_user
        if rep_user:
            reply_to_user_id = rep_user.id
            rep_name = rep_user.first_name or "Someone"
        rep_text = sanitize_for_ai(reply_to_text)

    # 1. Silently record all conversation
    save_chat_message(
        chat_id=chat_id,
        user_name=user_name,
        text=text,
        user_id=user_id,
        message_id=message_id,
        reply_to_msg_id=reply_to_msg_id,
        reply_to_user_id=reply_to_user_id
    )

    # 2. Check if the user addressed Flash
    bot_info = bot.get_me()
    if should_respond(message, bot_info.username):
        logging.info(f"Bot invoked by {user_name}: {text}")
        bot.send_chat_action(chat_id, "typing")

        clean_text = sanitize_for_ai(text)
        user_is_master = is_sender_master(message)

        # Route file requests before the AI
        if wants_file(text):
            recent_for_file = get_recent_chat_history(chat_id, limit=4)
            history_texts = [m[1] for m in recent_for_file if m[1] != text]
            matches, note = search_roms_or_kernels(
                text,
                reply_to_text=reply_to_text,
                history_texts=history_texts,
                force_search=True
            )
            if matches:
                deliver_file(message, matches[0], note)
                return

        transcript = "\n".join(f"{u}: {m}" for u, m in get_recent_chat_history(chat_id, 12))
        parts = [f"Recent chat (oldest first):\n{transcript}\n"]

        if message.reply_to_message:
            parts.append(f"The sender is replying to {rep_name}'s message: '{rep_text}'")

        sender = "Boss (Billu bhai)" if user_is_master else user_name
        parts.append(f"Sender: {sender}")
        parts.append(f"Latest message to answer: {clean_text}")

        wants_roast = re.search(r'\b(roast|pel|baja|bezzati)\b', (text or "").lower())
        if wants_roast:
            tname, tquery = resolve_roast_target(text, message, user_name)
            is_self = (tname == user_name)
            replied_txt = ""
            if message.reply_to_message and not is_self:
                replied_txt = (message.reply_to_message.caption or message.reply_to_message.text or "").strip()

            extra = []
            real = find_user_name(chat_id, tquery) if tquery else None
            if real:
                extra = [m for m in get_user_messages(chat_id, real) if useful_line(m) and m != replied_txt][-4:]

            source = ([replied_txt] if replied_txt else []) + extra
            if not source:
                pool = NO_MATERIAL_SELF if is_self else NO_MATERIAL_OTHER
                roast_fail_msg = random.choice(pool).format(name=tname or "Wo")
                bot.reply_to(message, roast_fail_msg)
                save_chat_message(chat_id, "Flash", roast_fail_msg)
                return

            parts.append(f"Mode: ROAST\nTarget: {tname}")
            if replied_txt:
                parts.append(f'Message to roast: "{replied_txt}"')
            if extra:
                parts.append("Their other messages:\n" + "\n".join(f"- {m}" for m in extra))
            user_payload = "\n".join(parts)

            reply = call_ai(SYSTEM_PROMPT, user_payload, few_shots=FEW_SHOTS, mode="ROAST")
            if bad_roast(reply, source):
                reply = call_ai(SYSTEM_PROMPT, user_payload +
                    "\n\nRejected: it had a comparison, was too long, or ignored their words. "
                    "Redo in ONE plain sentence that directly names what they said.", few_shots=FEW_SHOTS, mode="ROAST")
            if bad_roast(reply, source):
                reply = f"'{source[0][:60]}' likh ke kya ukhaad liya, bata?"
            elif random.random() < 0.5 and not re.search(r'\b(bc|mc|mkc|chutiy\w*|gandu|bhosd\w*|lodu)\b', reply.lower()):
                reply = reply.rstrip('.! ') + f", {random.choice(ABUSE_TAGS)}."

            sent_msg = bot.reply_to(message, reply)
            bot_id = bot_info.id
            sent_msg_id = getattr(sent_msg, 'message_id', None)
            save_chat_message(
                chat_id=chat_id,
                user_name="Flash",
                text=reply,
                user_id=bot_id,
                message_id=sent_msg_id,
                reply_to_msg_id=message_id,
                reply_to_user_id=user_id
            )
            return

        # ANSWER & CHAT Mode Handling
        is_question = bool(re.search(r'\?|\b(kya|kaise|kyun|kaha|kaun|bola|tha|how|why|what|where|which|help|bata|btao|batao)\b', (text or "").lower()))
        mode = "ANSWER" if is_question else "CHAT"
        parts.append(f"Mode: {mode}")

        user_payload = "\n".join(parts)

        try:
            reply = call_ai(SYSTEM_PROMPT, user_payload, few_shots=FEW_SHOTS, mode=mode)

            def has_cliche_or_bad(txt):
                if not txt:
                    return True
                t_low = txt.lower()
                if re.search(r"\bitn[ai]\s+\w+\s+hai\s+ki\b", t_low):
                    return True
                if any(k in t_low for k in ["cycle ki chain", "chai ki tapri", "chai ki taseer", "keyboard", "thak gaya", "mantra"]):
                    return True
                if "sharam se khatam" in t_low or "battery sharam" in t_low:
                    return True
                return False

            if has_cliche_or_bad(reply):
                logging.warning(f"AI response triggered guard: '{reply}'. Retrying...")
                retry_payload = f"{user_payload}\n\nYour previous reply '{reply}' was rejected (banned words or generic template). Rewrite it: specific to the message, sensible, Roman Hinglish."
                reply = call_ai(SYSTEM_PROMPT, retry_payload, few_shots=FEW_SHOTS, mode=mode)
                if has_cliche_or_bad(reply):
                    logging.warning("AI still triggered guard. Using clean contextual fallback.")
                    reply = "Samajh nahi aaya, ek baar clear likh."

            if not reply:
                reply = "Samajh nahi aaya, ek baar clear likh."

            sent_msg = bot.reply_to(message, reply)
            bot_id = bot_info.id
            sent_msg_id = getattr(sent_msg, 'message_id', None)
            save_chat_message(
                chat_id=chat_id,
                user_name="Flash",
                text=reply,
                user_id=bot_id,
                message_id=sent_msg_id,
                reply_to_msg_id=message_id,
                reply_to_user_id=user_id
            )
        except Exception as e:
            logging.error(f"Error answering user: {e}")
            bot.reply_to(message, "Samajh nahi aaya, ek baar clear likh.")

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
