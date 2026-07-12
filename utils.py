import os
import aiohttp
from datetime import datetime

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

# Language codes for translation (ISO 639-1)
LANGUAGE_CODES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "ar": "Arabic",
    "hi": "Hindi",
    "nl": "Dutch",
    "pl": "Polish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "tr": "Turkish"
}

async def translate_text(text, target_lang):
    # First try LibreTranslate
    try:
        async with aiohttp.ClientSession() as session:
            # Detect source language
            detect_url = "https://libretranslate.com/detect"
            async with session.post(detect_url, json={"q": text}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        source = data[0].get("language", "en")
                    else:
                        source = "en"
                else:
                    source = "en"
            # Translate
            translate_url = "https://libretranslate.com/translate"
            payload = {
                "q": text,
                "source": source,
                "target": target_lang,
                "format": "text"
            }
            async with session.post(translate_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "translated": data.get("translatedText", ""),
                        "source": source,
                        "target": target_lang
                    }
                else:
                    print(f"[Translate] LibreTranslate returned {resp.status}, trying Gemini")
                    raise Exception(f"LibreTranslate status {resp.status}")
    except Exception as e:
        print(f"[Translate] LibreTranslate error: {e}, falling back to Gemini")
        # Fallback to Gemini
        try:
            # Lazy import to avoid circular dependency
            import ai
            model = ai._get_gemini_client()
            prompt = f"Translate the following text to {target_lang}. Only output the translation, nothing else.\n\nText: {text}"
            response = model.generate_content(prompt, generation_config={"temperature": 0.3})
            if response.candidates and response.candidates[0].content:
                translated = response.text.strip()
                return {
                    "translated": translated,
                    "source": "unknown",
                    "target": target_lang
                }
            else:
                return None
        except Exception as e2:
            print(f"[Translate] Gemini fallback error: {e2}")
            return None

async def get_language_list():
    return "\n".join(f"`{code}` → {name}" for code, name in LANGUAGE_CODES.items())
