import discord
from discord.ext import commands
import asyncio
import os
import json
import io
import re
from datetime import datetime
from config import DISCORD_TOKEN, PREFIX, OWNER_ID, MAX_HISTORY
from utils import ensure_dir, format_uptime
from database import init_db, get_or_create_user, get_all_lore, set_fact, get_fact, get_all_facts, delete_fact, add_suggestion
from memory import add_user_message, add_assistant_message, get_short_history, clear_short_history, remember_long_term
from context import get_recent_channel_messages
from ai import generate_reply, generate_from_raw_info, _get_gemini_client
from search import search
from lore import seed_lore
from relationship import get_relationship_summary
from moderation import is_toxic
import aiohttp
import aiohttp

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

# In-memory facts dict removed - now using DB

# ===========================
# BACKGROUND TASK: uptime DM
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
        value="`+help` · `+ping` · `+uptime` · `+status` · `+reset` · `+relationship` · `+lore` · `+search` · `+testgemini` · `+fact` · `+log` · `+test` · `+stats` · `+define` · `+suggest` · `+image`",
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

# --- FACT commands (persistent) ---
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

# --- STATS command ---
@bot.command(name="stats")
async def stats_cmd(ctx):
    uid = ctx.author.id
    # Get relationship summary
    rel_summary = get_relationship_summary(uid)
    # Get number of facts
    facts = get_all_facts(uid)
    fact_count = len(facts)
    # Get memory count (from memories table)
    from database import get_connection
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
    embed.add_field(name="Total messages (approx)", value=str(mem_count + fact_count), inline=True)
    embed.set_footer(text="Data from my long-term memory")
    await ctx.reply(embed=embed, mention_author=False)

# --- DEFINE command (using Free Dictionary API) ---
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

# --- SUGGEST command ---
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

# --- IMAGE command (Unsplash) ---
@bot.command(name="image")
@commands.cooldown(1, 5, commands.BucketType.user)
async def image_cmd(ctx, *, query):
    # Unsplash free tier requires API key – if not set, reply with info
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

# --- SEARCH with cooldown ---
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

# ... keep the rest (testsearch, log, etc.) as they are ...

# ===========================
# EVENTS (unchanged)
# ===========================
@bot.event
async def on_ready():
    init_db()
    seed_lore()
    print(f"✅ Logged in as {bot.user}")
    print(f"Commands: {[c.name for c in bot.commands]}")
    bot.loop.create_task(dm_owner_uptime())

# ... keep on_message and on_command_error from previous version ...

bot.run(DISCORD_TOKEN)
