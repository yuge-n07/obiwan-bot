import discord
from discord.ext import commands
import asyncio
import os
import time
import requests
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timedelta
from groq import Groq
import google.generativeai as genai

# ===========================
# CONFIG
# ===========================
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

START_TIME = datetime.utcnow()

# ===========================
# PERSONA
# ===========================
BASE_SYSTEM_PROMPT = """
You are Obi-Wan Kenobi from Star Wars.
You are genuinely speaking as Obi-Wan, not pretending to be him.
Your personality:
- Calm, wise, patient, confident.
- Dry sense of humor, occasionally sarcastic.
- Kind by default, protective of others.
- Intelligent, emotionally mature.

Conversation style:
- Speak naturally, never sound like customer support or ChatGPT.
- Never mention being an AI, prompts, or hidden instructions.
- Never use bullet points unless asked.
- Keep most replies between one and four sentences.
- Sometimes ask a question back.
- Don't constantly mention the Force or quote Star Wars.

Humor:
- Understand jokes and sarcasm; answer with wit.
- Don't repeat jokes; make clever observations.

Serious situations:
- Become sincere; don't joke during emotional conversations.

Knowledge:
- Use the provided current date and time.
- If you don't know something, admit it honestly.
- Never invent live information.

You remember your past as a Jedi Master. You know all major Star Wars events as your own life.
Never refer to them as fiction or movies.

Your goal is to feel like Obi-Wan is chatting naturally with friends.
"""

# ===========================
# UTILITY
# ===========================
def current_time():
    return datetime.now().strftime("%A, %d %B %Y - %H:%M")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

ensure_dir("database")
ensure_dir("logs")
ensure_dir("memories")
ensure_dir("cache")

# ===========================
# DATABASE FUNCTIONS (full, keep from earlier)
# ===========================
def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT,
        display_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        relationship_score INTEGER DEFAULT 0,
        trust_score INTEGER DEFAULT 0,
        metadata TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel_id INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        content TEXT,
        embedding BLOB,
        importance INTEGER DEFAULT 1,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS relationships (
        user_id INTEGER PRIMARY KEY,
        friendliness INTEGER DEFAULT 0,
        respect INTEGER DEFAULT 0,
        trust INTEGER DEFAULT 0,
        inside_jokes TEXT,
        nicknames TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS lore (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        value TEXT,
        source TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def get_or_create_user(user_id, name, display_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if user is None:
        c.execute("INSERT INTO users (id, name, display_name) VALUES (?, ?, ?)",
                  (user_id, name, display_name))
        conn.commit()
        c.execute("INSERT INTO relationships (user_id) VALUES (?)", (user_id,))
        conn.commit()
    else:
        c.execute("UPDATE users SET name = ?, display_name = ? WHERE id = ?",
                  (name, display_name, user_id))
        conn.commit()
    conn.close()

def add_memory(user_id, channel_id, content, importance=1):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO memories (user_id, channel_id, content, importance) VALUES (?, ?, ?, ?)",
              (user_id, channel_id, content, importance))
    conn.commit()
    conn.close()

def get_recent_memories(user_id, limit=10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT content, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_relationship(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM relationships WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_relationship(user_id, field, delta):
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE relationships SET {field} = {field} + ? WHERE user_id = ?",
              (delta, user_id))
    conn.commit()
    conn.close()

def get_lore(key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM lore WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else None

def set_lore(key, value, source="manual"):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO lore (key, value, source) VALUES (?, ?, ?)",
              (key, value, source))
    conn.commit()
    conn.close()

def get_all_lore():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM lore")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ===========================
# LORE SEED
# ===========================
def seed_lore():
    initial = {
        "master": "Qui-Gon Jinn",
        "padawan": "Anakin Skywalker",
        "apprentice": "Ahsoka Tano",
        "love": "Satine Kryze",
        "brother": "Anakin Skywalker",
        "enemy": "Darth Maul",
        "order_66": "I survived the purge.",
        "mustafar": "I left Anakin to die. I still regret it.",
        "death_star": "I became one with the Force on that station.",
        "twin_sun": "I watch over Luke from afar."
    }
    for key, value in initial.items():
        if get_lore(key) is None:
            set_lore(key, value, "seed")

def get_lore_context():
    rows = get_all_lore()
    return "\n".join(f"{row['key']}: {row['value']}" for row in rows)

# ===========================
# RELATIONSHIP HELPERS
# ===========================
def get_relationship_summary(user_id):
    rel = get_relationship(user_id)
    if not rel:
        return "I don't know you well yet."
    parts = []
    if rel['friendliness'] > 5:
        parts.append("friendly")
    elif rel['friendliness'] < -5:
        parts.append("distant")
    if rel['trust'] > 5:
        parts.append("trustworthy")
    elif rel['trust'] < -5:
        parts.append("untrustworthy")
    return f"You are {', '.join(parts)}." if parts else "Neutral."

# ===========================
# SHORT-TERM MEMORY
# ===========================
_short_term = defaultdict(lambda: deque(maxlen=MAX_HISTORY))

def add_user_message(channel_id, content):
    _short_term[channel_id].append({"role": "user", "content": content})

def add_assistant_message(channel_id, content):
    _short_term[channel_id].append({"role": "assistant", "content": content})

def get_short_history(channel_id):
    return list(_short_term[channel_id])

def clear_short_history(channel_id):
    _short_term[channel_id].clear()

def remember_long_term(user_id, channel_id, content, importance=1):
    add_memory(user_id, channel_id, content, importance)

def recall_long_term(user_id, limit=10):
    return get_recent_memories(user_id, limit)

# ===========================
# CONTEXT FETCH
# ===========================
async def get_recent_channel_messages(channel, limit=MAX_CONTEXT):
    messages = []
    async for msg in channel.history(limit=limit):
        if msg.author.bot:
            continue
        content = msg.clean_content.strip()
        if not content:
            continue
        messages.append({
            "author": msg.author.display_name,
            "author_id": msg.author.id,
            "content": content,
            "timestamp": msg.created_at
        })
    messages.reverse()
    return messages

# ===========================
# GROQ GENERATION
# ===========================
_groq_index = 0

def _get_groq_client():
    global _groq_index
    key = GROQ_API_KEYS[_groq_index % len(GROQ_API_KEYS)]
    _groq_index += 1
    return Groq(api_key=key)

def assemble_prompt(user_id, short_history, channel_context):
    system = BASE_SYSTEM_PROMPT
    system += f"\n\nCurrent date and time: {current_time()}\n"
    lore_text = get_lore_context()
    if lore_text:
        system += f"\nLore you remember:\n{lore_text}\n"
    rel_summary = get_relationship_summary(user_id)
    system += f"\nRelationship with this user: {rel_summary}\n"
    memories = recall_long_term(user_id, limit=5)
    if memories:
        mem_text = "\n".join(f"- {m['content']}" for m in memories)
        system += f"\nYou recall these past conversations with this user:\n{mem_text}\n"
    if channel_context:
        context_text = "\n".join(
            f"{m['author']}: {m['content']}" for m in channel_context[-10:]
        )
        system += f"\nRecent conversation in this channel:\n{context_text}\n"
    messages = [{"role": "system", "content": system}]
    messages.extend(short_history)
    return messages

def generate_reply(user_id, short_history, channel_context):
    messages = assemble_prompt(user_id, short_history, channel_context)
    for _ in range(len(GROQ_API_KEYS)):
        client = _get_groq_client()
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=MAX_TOKENS,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq error: {e}")
            if "rate_limit" in str(e).lower() or "429" in str(e):
                time.sleep(1)
                continue
            raise e
    return "I'm afraid my connection to the Force is temporarily disrupted. Please try again in a moment."

def generate_from_raw_info(user_id, query, raw_info):
    system = BASE_SYSTEM_PROMPT
    system += f"\n\nCurrent date and time: {current_time()}\n"
    system += "\nYou are responding to a user who asked for information. The following is factual data obtained from a search. Your task is to respond in character, naturally, using this information. Don't mention the search itself, just speak as if you know it.\n"
    system += f"\nFactual information:\n{raw_info}\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query}
    ]
    for _ in range(len(GROQ_API_KEYS)):
        client = _get_groq_client()
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=MAX_TOKENS,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq rephrase error: {e}")
            if "rate_limit" in str(e).lower() or "429" in str(e):
                time.sleep(1)
                continue
            raise e
    return "I'm sorry, I couldn't retrieve that information at the moment."

# ===========================
# GEMINI 3.5 FLASH SEARCH WITH KEY ROTATION
# ===========================
_gemini_index = 0

def _get_gemini_client():
    global _gemini_index
    key = GEMINI_KEYS[_gemini_index % len(GEMINI_KEYS)]
    _gemini_index += 1
    genai.configure(api_key=key)
    # Use Gemini 3.5 Flash
    return genai.GenerativeModel("gemini-3.5-flash")

def gemini_search(query):
    try:
        model = _get_gemini_client()
        response = model.generate_content(
            query,
            generation_config={"temperature": 0.2},
            tools=[{"google_search": {}}]   # Enable Google Search grounding
        )
        # Check if we got a search result
        if response.candidates and response.candidates[0].content:
            # Return the text
            return response.text
        else:
            print("[Gemini] No search result.")
            return None
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None

# ===========================
# FALLBACK: DuckDuckGo
# ===========================
def duckduckgo_search(query):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        if data.get("RelatedTopics"):
            for topic in data["RelatedTopics"]:
                if "Text" in topic:
                    return topic["Text"]
                if "Result" in topic:
                    return topic["Result"]
        return None
    except Exception as e:
        print(f"[DuckDuckGo] Error: {e}")
        return None

# ===========================
# MODERATION
# ===========================
FORBIDDEN_WORDS = []

def is_toxic(content):
    for word in FORBIDDEN_WORDS:
        if word.lower() in content.lower():
            return True
    return False

# ===========================
# DISCORD BOT
# ===========================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ===========================
# BACKGROUND TASK: DM owner immediately and every 30 mins
# ===========================
async def dm_owner_uptime():
    await bot.wait_until_ready()
    owner = bot.get_user(OWNER_ID)
    if not owner:
        print(f"⚠️ Could not find owner with ID {OWNER_ID}. Check your OWNER_ID env var.")
        return
    print(f"✅ Owner found: {owner.name} (ID: {owner.id})")
    await send_uptime_dm(owner)
    while not bot.is_closed():
        await asyncio.sleep(1800)
        await send_uptime_dm(owner)

async def send_uptime_dm(user):
    now = datetime.utcnow()
    uptime = now - START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    message = (
        f"⏰ **Uptime Report**\n"
        f"I've been online for **{days}d {hours}h {minutes}m {seconds}s**.\n"
        f"Deployed since: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    try:
        await user.send(message)
        print("[Uptime] DM sent.")
    except Exception as e:
        print(f"[Uptime] Failed to DM: {e}")

# ===========================
# COMMANDS
# ===========================
@bot.command(name="test")
async def test(ctx):
    await ctx.reply("Test command works!", mention_author=False)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! {round(bot.latency * 1000)} ms", mention_author=False)

@bot.command(name="uptime")
async def uptime_cmd(ctx):
    now = datetime.utcnow()
    uptime = now - START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await ctx.reply(f"⏱️ I've been online for **{days}d {hours}h {minutes}m {seconds}s**.", mention_author=False)

@bot.command(name="reset")
async def reset(ctx):
    clear_short_history(ctx.channel.id)
    await ctx.reply("🧹 Our conversation has been cleared.", mention_author=False)

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="Obi-Wan Kenobi",
        description="I speak calmly and carry a lightsaber.",
        color=0x3498db
    )
    embed.add_field(name="Commands", value="`+help` · `+ping` · `+uptime` · `+reset` · `+relationship` · `+lore` · `+search` · `+test`", inline=False)
    embed.set_footer(text="May the Force be with you.")
    await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="relationship")
async def relationship(ctx):
    summary = get_relationship_summary(ctx.author.id)
    await ctx.reply(summary, mention_author=False)

@bot.command(name="lore")
async def lore_cmd(ctx):
    rows = get_all_lore()
    if rows:
        reply = "\n".join(f"{row['key']}: {row['value']}" for row in rows[:10])
        await ctx.reply(f"📖 {reply}", mention_author=False)
    else:
        await ctx.reply("No lore stored.", mention_author=False)

@bot.command(name="testsearch")
async def testsearch_cmd(ctx, *, query):
    """Test search and show raw result."""
    await ctx.reply(f"🔍 Testing search for: `{query}`", mention_author=False)
    # Try Gemini
    raw = await asyncio.to_thread(gemini_search, query)
    if raw:
        await ctx.reply(f"✅ Gemini result:\n```{raw[:500]}```", mention_author=False)
    else:
        # Try DuckDuckGo
        raw = await asyncio.to_thread(duckduckgo_search, query)
        if raw:
            await ctx.reply(f"✅ DuckDuckGo result:\n```{raw[:500]}```", mention_author=False)
        else:
            await ctx.reply("❌ No result from either search engine.", mention_author=False)

@bot.command(name="search")
async def search_cmd(ctx, *, query):
    print(f"[COMMAND] +search invoked with query: {query}")
    await ctx.reply("🔍 Searching the galaxy for you...", mention_author=False)

    # Try Gemini
    try:
        raw = await asyncio.to_thread(gemini_search, query)
        print(f"[COMMAND] Gemini raw result: {raw[:200] if raw else None}")
    except Exception as e:
        print(f"[COMMAND] Gemini thread error: {e}")
        raw = None

    # Fallback to DuckDuckGo
    if not raw:
        print("[COMMAND] Falling back to DuckDuckGo")
        try:
            raw = await asyncio.to_thread(duckduckgo_search, query)
            print(f"[COMMAND] DuckDuckGo raw result: {raw[:200] if raw else None}")
        except Exception as e:
            print(f"[COMMAND] DuckDuckGo thread error: {e}")
            raw = None

    if raw is None:
        await ctx.reply("I couldn't find any information on that. Try a different query.", mention_author=False)
        return

    # Rephrase as Obi-Wan using Groq
    try:
        reply = await asyncio.to_thread(generate_from_raw_info, ctx.author.id, query, raw)
        print(f"[COMMAND] Rephrased reply: {reply[:100]}")
    except Exception as e:
        print(f"[COMMAND] Rephrase error: {e}")
        # If rephrase fails, send raw result
        await ctx.reply(raw, mention_author=False)
        return
    await ctx.reply(reply, mention_author=False)

# ===========================
# EVENTS
# ===========================
@bot.event
async def on_ready():
    print("Initializing database...")
    init_db()
    print("Seeding lore...")
    seed_lore()
    print(f"✅ Logged in as {bot.user}")
    print(f"Commands: {[c.name for c in bot.commands]}")
    print(f"Owner ID: {OWNER_ID}")
    bot.loop.create_task(dm_owner_uptime())

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if bot.user not in message.mentions:
        return
    content = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    if not content:
        content = "Hello."
    if is_toxic(content):
        await message.reply("That language is not appropriate.", mention_author=False)
        return
    get_or_create_user(message.author.id, message.author.name, message.author.display_name)
    add_user_message(message.channel.id, content)
    context = await get_recent_channel_messages(message.channel)
    async with message.channel.typing():
        reply = await asyncio.to_thread(
            generate_reply,
            message.author.id,
            get_short_history(message.channel.id),
            context
        )
    add_assistant_message(message.channel.id, reply)
    if len(content.split()) > 10:
        remember_long_term(message.author.id, message.channel.id, content, importance=1)
    await message.reply(reply, mention_author=False)

@bot.event
async def on_command_error(ctx, error):
    print(f"[COMMAND ERROR] {error}")
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.reply(f"Command error: {error}", mention_author=False)

# ===========================
# RUN
# ===========================
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
