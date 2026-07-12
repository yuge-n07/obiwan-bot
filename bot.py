import discord
from discord.ext import commands
import asyncio
import os
import io
import aiohttp
from datetime import datetime
from config import DISCORD_TOKEN, PREFIX, OWNER_ID, MAX_HISTORY
import utils
from utils import ensure_dir, format_uptime, translate_text, get_language_list
from database import init_db, get_or_create_user, get_all_lore, set_fact, get_fact, get_all_facts, delete_fact, add_suggestion, get_connection
from memory import add_user_message, add_assistant_message, get_short_history, clear_short_history, remember_long_term
from context import get_recent_channel_messages
from ai import generate_reply, generate_from_raw_info, _get_gemini_client
from search import search
from lore import seed_lore
from relationship import get_relationship_summary
from moderation import is_toxic

ensure_dir("database")
ensure_dir("logs")
ensure_dir("memories")
ensure_dir("cache")

START_TIME = datetime.utcnow()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ===========================
# BACKGROUND TASK
# ===========================
async def dm_owner_uptime():
    await bot.wait_until_ready()
    owner = bot.get_user(OWNER_ID)
    if not owner:
        print(f"⚠️ Owner not found: {OWNER_ID}")
        return
    print(f"✅ Owner found: {owner.name}")
    await send_uptime_dm(owner)
    while not bot.is_closed():
        await asyncio.sleep(1800)
        await send_uptime_dm(owner)

async def send_uptime_dm(user):
    uptime_str = format_uptime(START_TIME)
    msg = f"⏰ **Uptime Report**\nI've been online for **{uptime_str}**.\nDeployed: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    try:
        await user.send(msg)
        print("[Uptime] DM sent.")
    except Exception as e:
        print(f"[Uptime] Failed: {e}")

# ===========================
# COMMANDS
# ===========================
@bot.command(name="test")
async def test(ctx):
    await ctx.reply("Test command works!", mention_author=False)

@bot.command(name="testgemini")
async def testgemini(ctx, *, prompt):
    await ctx.reply(f"🧪 Testing Gemini with: `{prompt}`", mention_author=False)
    try:
        model = _get_gemini_client()
        response = model.generate_content(prompt, generation_config={"temperature": 0.7})
        if response.candidates and response.candidates[0].content:
            await ctx.reply(f"✅ Gemini response:\n```{response.text[:500]}```", mention_author=False)
        else:
            await ctx.reply("❌ Gemini returned no response.", mention_author=False)
    except Exception as e:
        await ctx.reply(f"❌ Gemini error: {e}", mention_author=False)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! {round(bot.latency * 1000)} ms", mention_author=False)

@bot.command(name="uptime")
async def uptime_cmd(ctx):
    await ctx.reply(f"⏱️ Online for **{format_uptime(START_TIME)}**.", mention_author=False)

@bot.command(name="status")
async def status_cmd(ctx):
    embed = discord.Embed(
        title="Obi-Wan Kenobi – Status",
        color=0x3498db
    )
    embed.add_field(name="Uptime", value=format_uptime(START_TIME), inline=False)
    embed.add_field(name="Model", value="Gemini 3.5 Flash (primary) / Groq (fallback)", inline=False)
    embed.add_field(name="Prefix", value=PREFIX, inline=True)
    embed.add_field(name="History limit", value=f"{len(get_short_history(ctx.channel.id))}/{MAX_HISTORY}", inline=True)
    embed.set_footer(text="May the Force be with you.")
    await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="reset")
async def reset(ctx):
    clear_short_history(ctx.channel.id)
    await ctx.reply("🧹 Conversation cleared.", mention_author=False)

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="Obi-Wan Kenobi",
        description="I speak calmly and carry a lightsaber.",
        color=0x3498db
    )
    embed.add_field(
        name="Commands",
        value="`+help` · `+ping` · `+uptime` · `+status` · `+reset` · `+relationship` · `+lore` · `+search` · `+testgemini` · `+fact` · `+log` · `+test` · `+stats` · `+define` · `+suggest` · `+image` · `+translate` · `+langs`",
        inline=False
    )
    embed.add_field(
        name="Translate",
        value="Reply to a message and use `+translate <lang>` to translate that message, or type `+translate <lang> <text>` directly.",
        inline=False
    )
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

# --- FACT ---
@bot.command(name="fact")
@commands.cooldown(1, 5, commands.BucketType.user)
async def fact_cmd(ctx, action, key=None, *, value=None):
    uid = ctx.author.id
    if action.lower() == "set":
        if not key or not value:
            await ctx.reply("Usage: `+fact set <key> <value>`", mention_author=False)
            return
        set_fact(uid, key, value)
        await ctx.reply(f"✅ Fact stored: `{key}` → `{value}`", mention_author=False)
    elif action.lower() == "get":
        if not key:
            await ctx.reply("Usage: `+fact get <key>`", mention_author=False)
            return
        val = get_fact(uid, key)
        if val:
            await ctx.reply(f"📌 `{key}` → `{val}`", mention_author=False)
        else:
            await ctx.reply(f"❌ No fact found for `{key}`", mention_author=False)
    elif action.lower() == "list":
        facts = get_all_facts(uid)
        if facts:
            msg = "\n".join(f"`{f['key']}` → `{f['value']}`" for f in facts)
            await ctx.reply(f"📋 Your facts:\n{msg}", mention_author=False)
        else:
            await ctx.reply("You have no stored facts.", mention_author=False)
    elif action.lower() == "delete":
        if not key:
            await ctx.reply("Usage: `+fact delete <key>`", mention_author=False)
            return
        delete_fact(uid, key)
        await ctx.reply(f"🗑️ Deleted fact `{key}`", mention_author=False)
    else:
        await ctx.reply("Unknown action. Use `set`, `get`, `list`, or `delete`.", mention_author=False)

@fact_cmd.error
async def fact_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before using `+fact` again.", mention_author=False)

# --- STATS ---
@bot.command(name="stats")
async def stats_cmd(ctx):
    uid = ctx.author.id
    rel_summary = get_relationship_summary(uid)
    facts = get_all_facts(uid)
    fact_count = len(facts)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM memories WHERE user_id = ?", (uid,))
    mem_count = c.fetchone()['count']
    conn.close()
    embed = discord.Embed(
        title=f"📊 Stats for {ctx.author.display_name}",
        color=0x3498db
    )
    embed.add_field(name="Relationship", value=rel_summary, inline=False)
    embed.add_field(name="Facts stored", value=str(fact_count), inline=True)
    embed.add_field(name="Memories saved", value=str(mem_count), inline=True)
    embed.add_field(name="Total messages", value=str(mem_count + fact_count), inline=True)
    embed.set_footer(text="Data from my long-term memory")
    await ctx.reply(embed=embed, mention_author=False)

# --- DEFINE ---
@bot.command(name="define")
@commands.cooldown(1, 3, commands.BucketType.user)
async def define_cmd(ctx, *, word):
    await ctx.reply(f"📖 Looking up `{word}`...", mention_author=False)
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        entry = data[0]
                        meanings = entry.get("meanings", [])
                        if meanings:
                            definitions = []
                            for m in meanings[:2]:
                                part = m.get("partOfSpeech", "unknown")
                                for d in m.get("definitions", [])[:1]:
                                    def_text = d.get("definition", "")
                                    if def_text:
                                        definitions.append(f"*{part}*: {def_text}")
                            if definitions:
                                reply = f"**{word}**:\n" + "\n".join(definitions)
                                await ctx.reply(reply, mention_author=False)
                            else:
                                await ctx.reply(f"❌ No definition found for `{word}`.", mention_author=False)
                        else:
                            await ctx.reply(f"❌ No definition found for `{word}`.", mention_author=False)
                    else:
                        await ctx.reply(f"❌ No definition found for `{word}`.", mention_author=False)
                else:
                    await ctx.reply(f"❌ Could not fetch definition for `{word}`.", mention_author=False)
    except Exception as e:
        await ctx.reply(f"❌ Error: {e}", mention_author=False)

@define_cmd.error
async def define_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before using `+define` again.", mention_author=False)

# --- SUGGEST ---
@bot.command(name="suggest")
@commands.cooldown(1, 30, commands.BucketType.user)
async def suggest_cmd(ctx, *, suggestion):
    owner = bot.get_user(OWNER_ID)
    if owner:
        try:
            await owner.send(f"💡 **New suggestion from {ctx.author.display_name}** (`{ctx.author.id}`):\n{suggestion}")
        except:
            pass
    add_suggestion(ctx.author.id, suggestion)
    await ctx.reply("✅ Thank you! Your suggestion has been sent to the developer.", mention_author=False)

@suggest_cmd.error
async def suggest_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before suggesting again.", mention_author=False)

# --- IMAGE ---
@bot.command(name="image")
@commands.cooldown(1, 5, commands.BucketType.user)
async def image_cmd(ctx, *, query):
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not unsplash_key:
        await ctx.reply("🔑 Unsplash API key not set. Ask the owner to add `UNSPLASH_ACCESS_KEY` to env.", mention_author=False)
        return
    await ctx.reply(f"🖼️ Searching for `{query}`...", mention_author=False)
    try:
        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {unsplash_key}"}
        params = {"query": query, "per_page": 1, "orientation": "landscape"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("results"):
                        img_url = data["results"][0]["urls"]["regular"]
                        await ctx.reply(img_url, mention_author=False)
                    else:
                        await ctx.reply("❌ No images found.", mention_author=False)
                else:
                    await ctx.reply(f"❌ Unsplash API error: {resp.status}", mention_author=False)
    except Exception as e:
        await ctx.reply(f"❌ Error: {e}", mention_author=False)

@image_cmd.error
async def image_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before using `+image` again.", mention_author=False)

# --- TRANSLATE (with reply detection) ---
@bot.command(name="translate")
@commands.cooldown(1, 5, commands.BucketType.user)
async def translate_cmd(ctx, target_lang: str, *, text: str = None):
    target = target_lang.lower()
    if target not in utils.LANGUAGE_CODES:
        await ctx.reply(f"❌ Unknown language code. Use `+langs` to see supported codes.", mention_author=False)
        return

    # If text is not provided, try to fetch from replied message
    if text is None:
        if ctx.message.reference:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                text = ref_msg.clean_content
                if not text:
                    await ctx.reply("❌ The replied message has no text to translate.", mention_author=False)
                    return
            except Exception as e:
                await ctx.reply(f"❌ Could not fetch referenced message: {e}", mention_author=False)
                return
        else:
            await ctx.reply("❌ Please provide text to translate or reply to a message.", mention_author=False)
            return

    await ctx.reply(f"🔄 Translating to `{utils.LANGUAGE_CODES[target]}`...", mention_author=False)
    result = await translate_text(text, target)
    if not result:
        await ctx.reply("❌ Translation failed. Please try again later.", mention_author=False)
        return
    source_name = utils.LANGUAGE_CODES.get(result['source'], result['source'])
    target_name = utils.LANGUAGE_CODES.get(result['target'], result['target'])
    reply = f"**{source_name} → {target_name}**\n{result['translated']}"
    await ctx.reply(reply, mention_author=False)

@translate_cmd.error
async def translate_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before translating again.", mention_author=False)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("Usage: `+translate <language_code> <text>` or reply to a message and use `+translate <language_code>`", mention_author=False)

# --- LANGS ---
@bot.command(name="langs")
async def langs_cmd(ctx):
    msg = await get_language_list()
    await ctx.reply(f"🌐 **Supported languages**:\n{msg}", mention_author=False)

# --- SEARCH ---
@bot.command(name="search")
@commands.cooldown(1, 5, commands.BucketType.user)
async def search_cmd(ctx, *, query):
    await ctx.reply("🔍 Searching...", mention_author=False)
    raw = await asyncio.to_thread(search, query)
    if not raw:
        await ctx.reply("I couldn't find any information on that.", mention_author=False)
        return
    reply = await asyncio.to_thread(generate_from_raw_info, ctx.author.id, query, raw)
    await ctx.reply(reply, mention_author=False)

@search_cmd.error
async def search_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before searching again.", mention_author=False)

# --- TESTSEARCH ---
@bot.command(name="testsearch")
async def testsearch_cmd(ctx, *, query):
    await ctx.reply(f"🔍 Testing search for: `{query}`", mention_author=False)
    result = await asyncio.to_thread(search, query)
    if result:
        await ctx.reply(f"✅ Result:\n```{result[:500]}```", mention_author=False)
    else:
        await ctx.reply("❌ No result.", mention_author=False)

# --- LOG ---
@bot.command(name="log")
async def log_cmd(ctx, *, args=""):
    include_bots = "--all" in args
    await ctx.reply("📋 Generating channel log... please wait.", mention_author=False)
    try:
        messages = []
        async for msg in ctx.channel.history(limit=1000):
            if not include_bots and msg.author.bot:
                continue
            messages.append({
                "timestamp": msg.created_at.isoformat(),
                "author": msg.author.display_name,
                "author_id": str(msg.author.id),
                "is_bot": msg.author.bot,
                "content": msg.clean_content,
                "attachments": [a.url for a in msg.attachments],
                "embeds": [e.title for e in msg.embeds],
                "reactions": [str(r) for r in msg.reactions]
            })
        messages.reverse()
        report = []
        report.append("=" * 60)
        report.append(f"CHANNEL LOG: {ctx.channel.name} (ID: {ctx.channel.id})")
        report.append(f"Generated: {datetime.utcnow().isoformat()}")
        report.append(f"Include bot messages: {include_bots}")
        report.append("=" * 60)
        report.append(f"Total messages: {len(messages)}")
        report.append("")
        for i, m in enumerate(messages, 1):
            report.append(f"--- Message {i} ---")
            report.append(f"Timestamp: {m['timestamp']}")
            report.append(f"Author: {m['author']} (ID: {m['author_id']}) {'[BOT]' if m['is_bot'] else ''}")
            report.append(f"Content: {m['content']}")
            if m['attachments']:
                report.append(f"Attachments: {', '.join(m['attachments'])}")
            if m['embeds']:
                report.append(f"Embeds: {', '.join(m['embeds'])}")
            if m['reactions']:
                report.append(f"Reactions: {', '.join(m['reactions'])}")
            report.append("")
        report.append("=" * 60)
        report.append("END OF LOG")
        filename = f"log_{ctx.channel.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        with io.StringIO() as f:
            f.write("\n".join(report))
            await ctx.reply(
                file=discord.File(
                    fp=io.BytesIO(f.getvalue().encode('utf-8')),
                    filename=filename
                ),
                mention_author=False
            )
    except Exception as e:
        await ctx.reply(f"❌ Error generating log: {e}", mention_author=False)

# ===========================
# EVENTS
# ===========================
@bot.event
async def on_ready():
    init_db()
    seed_lore()
    print(f"✅ Logged in as {bot.user}")
    print(f"Commands: {[c.name for c in bot.commands]}")
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
    print(f"[ERROR] {error}")
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.reply(f"Error: {error}", mention_author=False)

bot.run(DISCORD_TOKEN)
