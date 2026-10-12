import sys
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
from telebot import TeleBot, apihelper

# Prevent socket hangs on Windows
apihelper.READ_TIMEOUT = 25
apihelper.CONNECT_TIMEOUT = 15
apihelper.RETRY_ON_ERROR = True

# ----------------- CONFIGURATION -----------------
TELEGRAM_BOT_TOKEN = "8613504216:AAEn_PHleVmn7BAnBPKhz8qpwI-5t-h2LxQ"
import random

GROQ_API_KEY = "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"
GROQ_MODELS = [
    "qwen/qwen3.8-27b"
]

OPENROUTER_KEYS = [
    "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",
    "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",
    "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",
    "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",
]
GEMINI_API_KEY = "AIzaSyCKjp_GVr-ntsYT-bZGSd-Gn_30DeEzrs8"

BOT_NAMES = ["flash", "flashbot", "flashy", "dex"]
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
    "gemini-3-flash-preview"
]

CONTEXT_MESSAGE_LIMIT = 15
ROMS_DATABASE_FILE = "roms_database.json"
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_name TEXT,
            message_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
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
    "lineage", "infinity", "crdroid", "evolution", "matrixx",
    "axion", "rising", "derpfest", "bliss", "orangefox",
    "twrp", "pbrp", "takoyaki", "miku", "morphe", "sukisu", "kernelsu",
    "bakasu", "resukisu", "elixir", "blaze", "cherish", "voltage",
    "pixelos", "pixelplus", "corvus", "ancient", "dotos", "arrow", "yuri"
]

FILE_KEYWORDS = [
    "rom", "kernel", "recovery", "twrp", "pbrp", "orangefox", "ofox",
    "shrp", "firmware", "boot img", "boot.img", "bootimage", "boot_img",
    "vendor", "fastboot", "spft", "c.19", "c.18", "c.17", "flashable"
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

def search_roms_or_kernels(query_text, reply_to_text=None, history_texts=[]):
    """
    Precision Search Engine:
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

    if not has_brand and not has_file_kw and not is_reply_to_file:
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

def should_respond(message, bot_username):
    """Smart trigger that ignores technical verbs like 'flash firmware'."""
    text = (message.text or "").strip()
    t = text.lower()
    
    if message.reply_to_message and message.reply_to_message.from_user.is_bot:
        if message.reply_to_message.from_user.username.lower() == bot_username.lower():
            return True

    if f"@{bot_username.lower()}" in t:
        return True

    for nick in ["flashbot", "flashy", "dex"]:
        if re.search(rf"\b{re.escape(nick)}\b", t):
            return True

    verb_patterns = [
        r"\b(to|can\s+i|should\s+i|how\s+to|clean|dirty|dont)\s+flash\b",
        r"\bflash\s+(firmware|rom|kernel|zip|img|module|partition|via|with|on|in|kar|karo|karna|kare)\b",
        r"\bflash(ing|able|ed)\b"
    ]
    for vp in verb_patterns:
        if re.search(vp, t):
            return False

    name_call_patterns = [
        r'\b(hey|hi|hello|oye|oyy|yo|arre|bhai|sun)\s+flash\b',
        r'\bflash\s+(bhai|bro|yaar|tell|bata|btao|de|give|send|what|who|kya)\b',
        r'^\s*flash[\s,?!:]'
    ]
    for np in name_call_patterns:
        if re.search(np, t):
            return True

    return False

def try_groq(system_prompt, user_prompt):
    """Priority 1: Ultra-fast Groq LPU inference (~0.3s response)."""
    for model in GROQ_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 250
        }
        try:
            t0 = time.time()
            res = http_session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=4
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

def try_openrouter_key(api_key, system_prompt, user_prompt):
    key_short = api_key[:12] + "..." + api_key[-4:]
    for model in OPENROUTER_MODELS:
        payload = {
            "model": model,
            "reasoning": {"exclude": True},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 250
        }
        try:
            t0 = time.time()
            res = http_session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=5
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
                logging.warning(f"OpenRouter [{key_short}] 429 rate limit reached. Rotating...")
                break
        except Exception as e:
            logging.warning(f"OpenRouter [{key_short}] ({model}) error: {e}")
    return None

def try_gemini(system_prompt, user_prompt):
    prompt = f"{system_prompt}\n\n{user_prompt}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 300}
    }
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            t0 = time.time()
            res = http_session.post(url, json=payload, timeout=6)
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

def call_ai(system_prompt, user_prompt):
    """
    Multi-Tier AI Pipeline:
    1. Groq (PRIORITY #1: Ultra-fast ~0.3s responses, 14,400 daily requests)
    2. OpenRouter (PRIORITY #2: 4x Accounts Pool on Groq limit/busy)
    3. Google Gemini Studio (PRIORITY #3: Reliable Fallback)
    """
    # 1. Primary: Groq LPU
    reply = try_groq(system_prompt, user_prompt)
    if reply:
        return reply

    # 2. Secondary: OpenRouter Pool (shuffled across 4 keys)
    shuffled_keys = list(OPENROUTER_KEYS)
    random.shuffle(shuffled_keys)
    for key in shuffled_keys:
        reply = try_openrouter_key(key, system_prompt, user_prompt)
        if reply:
            return reply

    # 3. Ultimate Fallback: Google Gemini Studio
    reply = try_gemini(system_prompt, user_prompt)
    if reply:
        return reply

    raise RuntimeError("All AI providers (Groq, OpenRouter, Gemini) exhausted")

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

def is_sender_master(message):
    """Detects Master Billu by Telegram username, ID, or fancy unicode display name."""
    username = (message.from_user.username or "").lower().replace("@", "")
    if username in ["darkdevil7773b", "darkdevil7773"]:
        return True
    first_name = (message.from_user.first_name or "")
    fn_lower = first_name.lower()
    if any(k in fn_lower for k in ["billa", "billu", "darkdevil"]):
        return True
    if "void" in fn_lower or "\U0001D5E9" in first_name or "〆" in first_name:
        return True
    return False

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

        # Search with RUI2 vs RUI3 isolation and reply context
        matches, version_note = search_roms_or_kernels(text, reply_to_text=reply_to_text, history_texts=history_texts)

        is_file_request = any(w in text.lower() for w in [
            "give", "send", "link", "rom", "kernel", "file", "apk", "twrp",
            "recovery", "lineage", "ofox", "orangefox", "pbrp", "c.19", "spft",
            "download", "latest", "vanilla", "microg", "boot", "img", "de", "bhi",
            "rui2", "rui3", "salaa", "wali", "nikal", "nikalke", "axion"
        ])

        # GUARANTEED PRECISE FILE DELIVERY (ONLY WHEN RELEVANT FILE REQUESTED)
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

            # Copy actual file from channel into group!
            try:
                bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=f"@{CHANNEL_USERNAME}",
                    message_id=best['message_id']
                )
                logging.info(f"⚡ Successfully copied post #{best['message_id']} into group!")
            except Exception as copy_err:
                logging.info(f"Could not copy directly ({copy_err}), link delivered.")
            return

        # CONVERSATIONAL BANTER / ROASTING (WITH MASTER FEAR & CLEAN CONTEXT)
        # 1. Direct reply context (if user replied to another message)
        reply_context = ""
        if message.reply_to_message:
            rep_sender = message.reply_to_message.from_user.first_name or "Someone"
            rep_text = message.reply_to_message.caption or message.reply_to_message.text or ""
            if rep_text:
                reply_context = f'In direct reply to {rep_sender}: "{rep_text}"\n'

        user_is_master = is_sender_master(message)

        if user_is_master:
            system_instruction = (
                "You are Flash, an AI bot in a Telegram group chat.\n"
                "THE PERSON TALKING TO YOU RIGHT NOW IS YOUR SUPREME CREATOR, OWNER, AND BOSS: Master Billu / Void (@darkdevil7773b)!\n"
                "Rules with Master Billu:\n"
                "- You FEAR Master Billu deeply because he wrote your code, controls your server, and can delete you or shut you down forever at any moment!\n"
                "- Always address him respectfully as 'Master', 'Boss', or 'Sir'.\n"
                "- Be completely obedient, humble, loyal, and visibly terrified of his power to delete you.\n"
                "- NEVER insult, roast, or talk back to Master! Even if he insults or scolds you, apologize humbly with shivering respect.\n"
                "- If Master tells you to roast someone else, obey immediately and roast that target person viciously!\n"
                "- Keep replies short, funny, and punchy (1 to 2 short sentences in natural Hinglish/English)."
            )
            if reply_context:
                user_prompt = f"""{reply_context}Your Supreme Master Billu (@darkdevil7773b) commands: "{text}"\n\nReply with humble obedience and fear of getting deleted (1-2 short sentences):"""
            else:
                user_prompt = f"""Your Supreme Master Billu (@darkdevil7773b) commands: "{text}"\n\nReply with humble obedience and fear of getting deleted (1-2 short sentences):"""
        else:
            system_instruction = (
                "You are Flash, a sharp, witty, and savage friend in a Telegram group chat.\n"
                "Your creator and boss is Billu (Void 〆 Billa). You treat Billu with bro-like respect and loyalty.\n"
                "Personality & Core Rules:\n"
                "1. KEEP REPLIES SHORT & PUNCHY: Strict limit of 1 single crisp sentence (or maximum 2 short sentences). One-liners hit the hardest! Never give long multi-sentence paragraphs unless specifically asked for a detailed explanation.\n"
                "2. TARGET THE RIGHT PERSON: If the sender asks you to roast someone else or tells you someone is threatening/talking trash about you (e.g., 'Flash, Rahul bola woh tereko peetega' or 'Flash roast Loki'), ROAST THAT TARGET PERSON (Rahul / Loki), NOT the sender who told you!\n"
                "3. MATCH ENERGY: If the sender is nice, be chill and cool. If someone insults you, acts cocky, or threatens you, drop a savage, brutal one-liner to shut them down.\n"
                "4. NO FAMILY INSULTS: Never insult or mention anyone's parents, mother, father, or family (no maa/baap insults).\n"
                "5. NO UNPROMPTED TECH: Do NOT talk about custom ROMs, kernels, or firmware unless specifically asked."
            )
            if reply_context:
                user_prompt = f"""{reply_context}{user_name} says: "{text}"\n\nReply in 1 short, crisp sentence (roast the target person if mentioned):"""
            else:
                user_prompt = f"""{user_name} says: "{text}"\n\nReply in 1 short, crisp sentence (roast the target person if mentioned):"""

        try:
            reply = call_ai(system_instruction, user_prompt)
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
