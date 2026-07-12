FORBIDDEN_WORDS = []

def is_toxic(content):
    for word in FORBIDDEN_WORDS:
        if word.lower() in content.lower():
            return True
    return False
