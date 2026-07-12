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
# COMMANDS (unchanged except +song)
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
        value=(
            "`+help` · `+ping` · `+uptime` · `+status` · `+reset` · `+relationship` · `+lore` · "
            "`+websearch` · `+song` · `+testgemini` · `+fact` · `+log` · `+test` · `+stats` · "
            "`+define` · `+suggest` · `+image` · `+translate` · `+langs` · "
            "`+rps` · `+trivia` · `+meme` · `+roll` · `+coin` · `+deezer` · `+mood` · `+leaderboard`"
        ),
        inline=False
    )
    embed.add_field(
        name="Music Search",
        value="`+song <query>` – search Saavn, choose, download 320kbps MP3 and upload to Discord",
        inline=False
    )
    embed.set_footer(text="May the Force be with you.")
    await ctx.reply(embed=embed, mention_author=False)

# ===========================
# RELATIONSHIP / LORE / FACT / STATS / DEFINE / SUGGEST / IMAGE / TRANSLATE / LANGS
# (unchanged – keep your existing implementations)
# ===========================

# ... (keep all your existing commands from the previous version, but I'll skip copying them for brevity, as they are unchanged) ...

# ===========================
# WEBSERACH
# ===========================
@bot.command(name="websearch")
@commands.cooldown(1, 5, commands.BucketType.user)
async def websearch_cmd(ctx, *, query):
    await ctx.reply("🔍 Searching the web...", mention_author=False)
    raw = await asyncio.to_thread(search, query)
    if not raw:
        await ctx.reply("I couldn't find any information on that.", mention_author=False)
        return
    reply = await asyncio.to_thread(generate_from_raw_info, ctx.author.id, query, raw)
    await ctx.reply(reply, mention_author=False)

@websearch_cmd.error
async def websearch_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before searching again.", mention_author=False)

# ===========================
# SONG – using saavn.me API (no browser, no extra libs)
# ===========================
@bot.command(name="song")
@commands.cooldown(1, 15, commands.BucketType.user)
async def saavn_song(ctx, *, query):
    """Search for a song on Saavn, download and upload 320kbps MP3."""
    msg = await ctx.reply("🔍 Searching for songs...", mention_author=False)

    try:
        # Step 1: Search
        search_url = f"https://saavn.me/api/search?query={query.replace(' ', '+')}"
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url) as resp:
                if resp.status != 200:
                    await msg.edit(content="❌ Saavn API error. Please try again later.")
                    return
                data = await resp.json()
                results = data.get('data', {}).get('results', [])
                if not results:
                    await msg.edit(content="❌ No songs found.")
                    return

                # Limit to 10
                results = results[:10]

                # Build selection list
                lines = []
                for i, track in enumerate(results, 1):
                    title = track.get('title', 'Unknown')
                    artists = track.get('artists', [])
                    artist_names = ', '.join([a.get('name', '') for a in artists]) if artists else 'Unknown'
                    lines.append(f"`{i}.` **{title}** – {artist_names}")
                result_msg = "🎵 **Choose a song (reply with number):**\n" + "\n".join(lines)

                # Check message length
                if len(result_msg) > 4000:
                    file_obj = discord.File(io.BytesIO(result_msg.encode('utf-8')), filename="song_list.txt")
                    await msg.edit(content="🎵 **Song list is too long. See attached file.**", attachments=[file_obj])
                else:
                    await msg.edit(content=result_msg)

                # Step 2: Wait for user selection
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

                try:
                    selection_msg = await bot.wait_for('message', check=check, timeout=30)
                    choice = int(selection_msg.content) - 1
                    if choice < 0 or choice >= len(results):
                        await ctx.reply("❌ Invalid number.", mention_author=False)
                        return

                    selected = results[choice]
                    song_id = selected.get('id')
                    if not song_id:
                        await ctx.reply("❌ Song ID not available.", mention_author=False)
                        return

                    # Step 3: Get song details (including download URL)
                    detail_url = f"https://saavn.me/api/songs/{song_id}"
                    async with session.get(detail_url) as detail_resp:
                        if detail_resp.status != 200:
                            await ctx.reply("❌ Failed to fetch song details.", mention_author=False)
                            return
                        detail_data = await detail_resp.json()
                        song_data = detail_data.get('data', {})
                        # The download URL is usually in 'downloadUrl' array or directly
                        download_url = None
                        if 'downloadUrl' in song_data:
                            # It's a list of quality options
                            for item in song_data['downloadUrl']:
                                if item.get('quality') == '320kbps':
                                    download_url = item.get('url')
                                    break
                            if not download_url:
                                # fallback to first
                                download_url = song_data['downloadUrl'][0].get('url') if song_data['downloadUrl'] else None
                        if not download_url:
                            # try 'media_url'
                            download_url = song_data.get('media_url')

                        if not download_url:
                            await ctx.reply("❌ No download URL available for this song.", mention_author=False)
                            return

                        title = song_data.get('title', 'Song')
                        artists = song_data.get('artists', [])
                        artist_names = ', '.join([a.get('name', '') for a in artists]) if artists else 'Unknown'

                        await ctx.reply(f"📥 Downloading **{title}** by {artist_names} (320kbps)...", mention_author=False)

                        # Step 4: Download the file
                        async with session.get(download_url) as file_resp:
                            if file_resp.status != 200:
                                await ctx.reply("❌ Failed to download the song.", mention_author=False)
                                return
                            file_data = await file_resp.read()
                            file_size = len(file_data)

                        # Step 5: Upload to Discord
                        filename = f"{title.replace('/', '-').replace(' ', '_')}.mp3"
                        if file_size > 8 * 1024 * 1024:
                            await ctx.reply(f"⚠️ File too large ({file_size/1024/1024:.1f}MB) to upload. Direct link: {download_url}", mention_author=False)
                            return

                        await ctx.reply("📤 Uploading to Discord...", mention_author=False)
                        file_obj = discord.File(io.BytesIO(file_data), filename=filename)
                        await ctx.reply(f"✅ **{title}** by {artist_names}", file=file_obj, mention_author=False)

                except asyncio.TimeoutError:
                    await ctx.reply("⏰ Selection timed out.", mention_author=False)

    except Exception as e:
        await ctx.reply(f"❌ Error: {e}", mention_author=False)

@saavn_song.error
async def saavn_song_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Please wait {error.retry_after:.1f}s before using `+song` again.", mention_author=False)

# ===========================
# The rest of your commands (games, deezer, etc.) go here unchanged
# ===========================

# ... keep all your other commands (rps, trivia, meme, roll, coin, deezer, mood, leaderboard, testsearch, log, events) exactly as they were ...

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
