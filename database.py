import sqlite3
from config import DATABASE_PATH

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
    c.execute('''CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        key TEXT,
        value TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, key)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending'
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

# ----- Fact functions -----
def set_fact(user_id, key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO facts (user_id, key, value) VALUES (?, ?, ?)",
              (user_id, key, value))
    conn.commit()
    conn.close()

def get_fact(user_id, key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM facts WHERE user_id = ? AND key = ?", (user_id, key))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else None

def get_all_facts(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM facts WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_fact(user_id, key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM facts WHERE user_id = ? AND key = ?", (user_id, key))
    conn.commit()
    conn.close()

# ----- Suggestion functions -----
def add_suggestion(user_id, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO suggestions (user_id, content) VALUES (?, ?)", (user_id, content))
    conn.commit()
    conn.close()
