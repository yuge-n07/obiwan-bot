import sqlite3
from config import DATABASE_PATH

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT,
        display_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        relationship_score INTEGER DEFAULT 0,
        trust_score INTEGER DEFAULT 0,
        metadata TEXT
    )''')
    # memories table
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
    # relationships table
    c.execute('''CREATE TABLE IF NOT EXISTS relationships (
        user_id INTEGER PRIMARY KEY,
        friendliness INTEGER DEFAULT 0,
        respect INTEGER DEFAULT 0,
        trust INTEGER DEFAULT 0,
        inside_jokes TEXT,
        nicknames TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    # lore table
    c.execute('''CREATE TABLE IF NOT EXISTS lore (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        value TEXT,
        source TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # NEW: facts table
    c.execute('''CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        key TEXT,
        value TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, key)
    )''')
    # NEW: suggestions table
    c.execute('''CREATE TABLE IF NOT EXISTS suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending'
    )''')
    conn.commit()
    conn.close()

# ... keep all existing user/memory/relationship/lore functions unchanged ...

# NEW: Fact functions
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

# NEW: Suggestion function
def add_suggestion(user_id, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO suggestions (user_id, content) VALUES (?, ?)", (user_id, content))
    conn.commit()
    conn.close()y
