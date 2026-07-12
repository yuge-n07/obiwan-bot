import discord
from discord.ext import commands
import asyncio
from datetime import datetime
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
    """Test Gemini directly with a prompt."""
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
    embed.add_field(name="Commands", value="`+help` · `+ping` · `+uptime` · `+reset` · `+relationship` · `+lore` · `+search` · `+testgemini` · `+test`", inline=False)
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
