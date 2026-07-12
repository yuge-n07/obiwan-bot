import discord
from config import MAX_CONTEXT

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
