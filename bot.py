import discord
from discord.ext import commands
import asyncio
import os
import json
import io
from datetime import datetime, timedelta
from config import DISCORD_TOKEN, PREFIX, OWNER_ID
from utils import ensure_dir, format_uptime
from database import init_db, get_or_create_user, get_all_lore
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

# In-memory facts (key: user_id, value: dict)
facts = {}

# ===========================
# BACKGROUND TASK: DM owner with uptime every 30 min
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
        value="`+help` · `+ping` · `+uptime` · `+status` · `+reset` · `+relationship` · `+lore` · `+search` · `+testgemini` · `+fact` · `+log` · `+test`",
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

@bot.command(name="fact")
async def fact_cmd(ctx, action, key=None, *, value=None):
    """Store or retrieve a fact about a user."""
    uid = str(ctx.author.id)
    if uid not in facts:
        facts[uid] = {}
    if action.lower() == "set":
        if not key or not value:
            await ctx.reply("Usage: `+fact set <key> <value>`", mention_author=False)
            return
        facts[uid][key] = value
        await ctx.reply(f"✅ Fact stored: `{key}` → `{value}`", mention_author=False)
    elif action.lower() == "get":
        if not key:
            await ctx.reply("Usage: `+fact get <key>`", mention_author=False)
            return
        val = facts[uid].get(key)
        if val:
            await ctx.reply(f"📌 `{key}` → `{val}`", mention_author=False)
        else:
            await ctx.reply(f"❌ No fact found for `{key}`", mention_author=False)
    elif action.lower() == "list":
        if facts[uid]:
            msg = "\n".join(f"`{k}` → `{v}`" for k, v in facts[uid].items())
            await ctx.reply(f"📋 Your facts:\n{msg}", mention_author=False)
        else:
            await ctx.reply("You have no stored facts.", mention_author=False)
    else:
        await ctx.reply("Unknown action. Use `set`, `get`, or `list`.", mention_author=False)

@bot.command(name="testsearch")
async def testsearch_cmd(ctx, *, query):
    await ctx.reply(f"🔍 Testing search for: `{query}`", mention_author=False)
    result = await asyncio.to_thread(search, query)
    if result:
        await ctx.reply(f"✅ Result:\n```{result[:500]}```", mention_author=False)
    else:
        await ctx.reply("❌ No result.", mention_author=False)

@bot.command(name="search")
async def search_cmd(ctx, *, query):
    await ctx.reply("🔍 Searching...", mention_author=False)
    raw = await asyncio.to_thread(search, query)
    if not raw:
        await ctx.reply("I couldn't find any information on that.", mention_author=False)
        return
    reply = await asyncio.to_thread(generate_from_raw_info, ctx.author.id, query, raw)
    await ctx.reply(reply, mention_author=False)

@bot.command(name="log")
async def log_cmd(ctx, *, args=""):
    """Generate a detailed log of the channel. Use --all to include bot messages."""
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
