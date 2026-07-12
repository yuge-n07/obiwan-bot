from database import get_lore, set_lore, get_all_lore

def seed_lore():
    initial = {
        "master": "Qui-Gon Jinn",
        "padawan": "Anakin Skywalker",
        "apprentice": "Ahsoka Tano",
        "love": "Satine Kryze",
        "brother": "Anakin Skywalker",
        "enemy": "Darth Maul",
        "order_66": "I survived the purge.",
        "mustafar": "I left Anakin to die. I still regret it.",
        "death_star": "I became one with the Force on that station.",
        "twin_sun": "I watch over Luke from afar."
    }
    for key, value in initial.items():
        if get_lore(key) is None:
            set_lore(key, value, "seed")

def get_lore_context():
    rows = get_all_lore()
    return "\n".join(f"{row['key']}: {row['value']}" for row in rows)
