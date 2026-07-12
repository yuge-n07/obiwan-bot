from collections import defaultdict, deque
from config import MAX_HISTORY
from database import add_memory, get_recent_memories

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
