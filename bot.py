import discord
from discord.ext import commands
import asyncio
import os
import io
import aiohttp
import random
import re
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

user_moods = {}

# ===========================
# BACKGROUND TASK (unchanged)
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
# ALL COMMANDS (keep your existing ones – I'll only show the changed +song)
# ===========================

# ... (all your other commands: test, testgemini, ping, uptime, status, reset, help, relationship, lore, fact, stats, define, suggest, image, translate, langs, websearch, deezer, rps, trivia, meme, roll, coin, mood, leaderboard, testsearch, log) remain exactly as they were.

# ===========================
# SONG – using jiosaavn-api (reliable, no browser)
# ===========================
@bot.command(name="song")
@commands.cooldown(1, 15, commands.BucketType.user)
async def saavn_song(ctx, *, query):
    """Search for a song on JioSaavn, download and upload 320kbps MP3."""
    msg = await ctx.reply("🔍 Searching for songs...", mention_author=False)

    try:
        from jiosaavn import JioSaavn
        api = JioSaavn()
        results = api.search(query, type="song")

        if not results or not results.get("results"):
            await msg.edit(content="❌ No songs found.")
            return

        songs = results["results"][:10]

        # Build selection list
        lines = []
        for i, track in enumerate(songs, 1):
            title = track.get("title", "Unknown")
            artist = track.get("artist", "Unknown")
            lines.append(f"`{i}.` **{title}** – {artist}")
        result_msg = "🎵 **Choose a song (reply with number):**\n" + "\n".join(lines)

        # Check length (Discord limit 4000 chars)
        if len(result_msg) > 4000:
            file_obj = discord.File(io.BytesIO(result_msg.encode('utf-8')), filename="song_list.txt")
            await msg.edit(content="🎵 **Song list is too long. See attached file.**", attachments=[file_obj])
        else:
            await msg.edit(content=result_msg)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            selection_msg = await bot.wait_for('message', check=check, timeout=30)
            choice = int(selection_msg.content) - 1
            if choice < 0 or choice >= len(songs):
                await ctx.reply("❌ Invalid number.", mention_author=False)
                return

            selected = songs[choice]
            title = selected.get("title", "Song")
            artist = selected.get("artist", "Unknown")

            # Get download URL – library provides a dict for each quality
            download_url = selected.get("download_url", {}).get("320kbps")
            if not download_url:
                # fallback to other qualities
                for quality in ["320kbps", "190kbps", "128kbps"]:
                    if selected.get("download_url", {}).get(quality):
                        download_url = selected["download_url"][quality]
                        break
            if not download_url:
                await ctx.reply("❌ No download URL available for this song.", mention_author=False)
                return

            await ctx.reply(f"📥 Downloading **{title}** by {artist} (320kbps)...", mention_author=False)

            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as file_resp:
                    if file_resp.status != 200:
                        await ctx.reply("❌ Failed to download the song.", mention_author=False)
                        return
                    file_data = await file_resp.read()
                    file_size = len(file_data)

            filename = f"{title.replace('/', '-').replace(' ', '_')}.mp3"
            if file_size > 8 * 1024 * 1024:
                await ctx.reply(f"⚠️ File too large ({file_size/1024/1024:.1f}MB) to upload. Direct link: {download_url}", mention_author=False)
                return

            await ctx.reply("📤 Uploading to Discord...", mention_author=False)
            file_obj = discord.File(io.BytesIO(file_data), filename=filename)
            await ctx.reply(f"✅ **{title}** by {artist}", file=file_obj, mention_author=False)

        except asyncio.TimeoutError:
            await ctx.reply("⏰ Selection timed out.", mention_author=False)

    except ImportError:
        await msg.edit(content="❌ `jiosaavn-api` not installed. Ask the owner to add it to `requirements.txt`.")
    except Exception as e:
        await ctx.reply(f"❌ Error: {e}", mention_author=False)

@saavn_song.error
async def saavn_song_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before using `+song` again.", mention_author=False)

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
