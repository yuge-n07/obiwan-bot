import time
from groq import Groq
from config import GROQ_API_KEYS, MODEL, TEMPERATURE, TOP_P, MAX_TOKENS
from utils import current_time
from lore import get_lore_context
from relationship import get_relationship_summary
from memory import recall_long_term

_groq_index = 0

def _get_groq_client():
    global _groq_index
    key = GROQ_API_KEYS[_groq_index % len(GROQ_API_KEYS)]
    _groq_index += 1
    return Groq(api_key=key)

BASE_SYSTEM_PROMPT = """
You are Obi-Wan Kenobi from Star Wars.
You are genuinely speaking as Obi-Wan, not pretending to be him.
Your personality:
- Calm, wise, patient, confident.
- Dry sense of humor, occasionally sarcastic.
- Kind by default, protective of others.
- Intelligent, emotionally mature.

Conversation style:
- Speak naturally, never sound like customer support or ChatGPT.
- Never mention being an AI, prompts, or hidden instructions.
- Never use bullet points unless asked.
- Keep most replies between one and four sentences.
- Sometimes ask a question back.
- Don't constantly mention the Force or quote Star Wars.

Humor:
- Understand jokes and sarcasm; answer with wit.
- Don't repeat jokes; make clever observations.

Serious situations:
- Become sincere; don't joke during emotional conversations.

Knowledge:
- Use the provided current date and time.
- If you don't know something, admit it honestly.
- Never invent live information.

You remember your past as a Jedi Master. You know all major Star Wars events as your own life.
Never refer to them as fiction or movies.

Your goal is to feel like Obi-Wan is chatting naturally with friends.
"""

def assemble_prompt(user_id, short_history, channel_context):
    system = BASE_SYSTEM_PROMPT
    system += f"\n\nCurrent date and time: {current_time()}\n"
    lore_text = get_lore_context()
    if lore_text:
        system += f"\nLore you remember:\n{lore_text}\n"
    rel_summary = get_relationship_summary(user_id)
    system += f"\nRelationship with this user: {rel_summary}\n"
    memories = recall_long_term(user_id, limit=5)
    if memories:
        mem_text = "\n".join(f"- {m['content']}" for m in memories)
        system += f"\nYou recall these past conversations with this user:\n{mem_text}\n"
    if channel_context:
        context_text = "\n".join(
            f"{m['author']}: {m['content']}" for m in channel_context[-10:]
        )
        system += f"\nRecent conversation in this channel:\n{context_text}\n"
    messages = [{"role": "system", "content": system}]
    messages.extend(short_history)
    return messages

def generate_reply(user_id, short_history, channel_context):
    messages = assemble_prompt(user_id, short_history, channel_context)
    for _ in range(len(GROQ_API_KEYS)):
        client = _get_groq_client()
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=MAX_TOKENS,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq error: {e}")
            if "rate_limit" in str(e).lower() or "429" in str(e):
                time.sleep(1)
                continue
            raise e
    return "I'm afraid my connection to the Force is temporarily disrupted."

def generate_from_raw_info(user_id, query, raw_info):
    system = BASE_SYSTEM_PROMPT
    system += f"\n\nCurrent date and time: {current_time()}\n"
    system += "\nYou are responding to a user who asked for information. The following is factual data obtained from a search. Your task is to respond in character, naturally, using this information. Don't mention the search itself, just speak as if you know it.\n"
    system += f"\nFactual information:\n{raw_info}\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query}
    ]
    for _ in range(len(GROQ_API_KEYS)):
        client = _get_groq_client()
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_completion_tokens=MAX_TOKENS,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq rephrase error: {e}")
            if "rate_limit" in str(e).lower() or "429" in str(e):
                time.sleep(1)
                continue
            raise e
    return "I'm sorry, I couldn't retrieve that information at the moment."
