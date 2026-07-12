from datetime import datetime
import os

def current_time():
    return datetime.now().strftime("%A, %d %B %Y - %H:%M")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def format_uptime(start_time):
    now = datetime.utcnow()
    uptime = now - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"
