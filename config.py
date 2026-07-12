import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable not set")

GROQ_API_KEYS = []
for i in range(1, 6):
    key = os.getenv(f"GROQ_KEY_{i}")
    if key:
        GROQ_API_KEYS.append(key)
if not GROQ_API_KEYS:
    raise ValueError("At least one GROQ_KEY_* environment variable must be set")

GEMINI_KEYS = []
for i in range(1, 7):
    key = os.getenv(f"GEMINI_KEY_{i}")
    if key:
        GEMINI_KEYS.append(key)
if not GEMINI_KEYS:
    raise ValueError("At least one GEMINI_KEY_* environment variable must be set")

MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
PREFIX = os.getenv("PREFIX", "+")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 12))
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT", 20))
TEMPERATURE = float(os.getenv("TEMPERATURE", 1.0))
TOP_P = float(os.getenv("TOP_P", 0.9))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 350))
OWNER_ID = int(os.getenv("OWNER_ID", 778695192684920842))
DATABASE_PATH = os.getenv("DATABASE_PATH", "database/bot.db")
