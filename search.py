import requests
import google.generativeai as genai
from config import GEMINI_KEYS

_gemini_index = 0

def _get_gemini_client():
    global _gemini_index
    key = GEMINI_KEYS[_gemini_index % len(GEMINI_KEYS)]
    _gemini_index += 1
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-3.5-flash")

def gemini_search(query):
    try:
        model = _get_gemini_client()
        # Use Google Search grounding
        response = model.generate_content(
            query,
            generation_config={"temperature": 0.2},
            tools=[{"google_search": {}}]
        )
        if response.candidates and response.candidates[0].content:
            return response.text
        else:
            print("[Gemini] No search result.")
            return None
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None

def duckduckgo_search(query):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        if data.get("RelatedTopics"):
            for topic in data["RelatedTopics"]:
                if "Text" in topic:
                    return topic["Text"]
                if "Result" in topic:
                    return topic["Result"]
        return None
    except Exception as e:
        print(f"[DuckDuckGo] Error: {e}")
        return None

def search(query):
    # Try Gemini first
    result = gemini_search(query)
    if result:
        return result
    # Fallback
    return duckduckgo_search(query)
