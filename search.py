import requests
import re

def duckduckgo_search(query):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("AbstractText"):
            return data["AbstractText"]
        if data.get("RelatedTopics"):
            for topic in data["RelatedTopics"]:
                if "Text" in topic:
                    return topic["Text"]
                if "Result" in topic:
                    return re.sub(r'<[^>]+>', '', topic["Result"])
        return None
    except Exception as e:
        print(f"[DuckDuckGo] Error: {e}")
        return None

def wikipedia_search(query):
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
        page = query.strip().replace(" ", "_")
        r = requests.get(url + page, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("extract"):
                return data["extract"]
        return None
    except Exception as e:
        print(f"[Wikipedia] Error: {e}")
        return None

def search(query):
    result = duckduckgo_search(query)
    if result:
        return result
    print("[Search] Falling back to Wikipedia")
    return wikipedia_search(query)
