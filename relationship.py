from database import get_relationship, update_relationship

def get_relationship_summary(user_id):
    rel = get_relationship(user_id)
    if not rel:
        return "I don't know you well yet."
    parts = []
    if rel['friendliness'] > 5:
        parts.append("friendly")
    elif rel['friendliness'] < -5:
        parts.append("distant")
    if rel['trust'] > 5:
        parts.append("trustworthy")
    elif rel['trust'] < -5:
        parts.append("untrustworthy")
    return f"You are {', '.join(parts)}." if parts else "Neutral."
