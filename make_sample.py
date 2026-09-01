"""Generate demo data so the page has something to show before the first real run."""
import json, hashlib, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, ".")
from scrape import build_ics, PALETTE
from extract import CATEGORIES, TAGS, deterministic_tags

TZ = ZoneInfo("Europe/Brussels")
base = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)

SRC = [("Neighbourhood Community Centre", "https://example.org/agenda/"),
       ("Public Library", "https://example.org/library/"),
       ("Residents' Committee", "https://example.org/committee/"),
       ("Concert Hall", "https://example.org/concerts/")]

IMG = "https://picsum.photos/seed/{seed}/640/360"

# (source index, day offset, hour, minute, end hour offset in days (None = same-day),
#  title, location, description, category, extra tag ids, image seed or None)
RAW = [
    (0, 1, 18, 30, None, "Repair Café", "Church Street 12",
     "Bring a broken appliance and we'll fix it together.", "environment", ["drop-in", "sustainability"], "repair"),
    (1, 2, 10, 0, None, "Storytime in French and Dutch", "Children's section",
     "For ages 3-6, free admission.", "family-children", ["kids", "family", "drop-in"], "storytime"),
    (2, 3, 19, 0, None, "Neighbourhood meeting on the new traffic plan", "Community hall",
     "Presentation followed by questions.", "civic-politics", ["registration-required", "accessible"], None),
    (3, 5, 20, 30, None, "Concert: jazz trio", "Main hall",
     "Doors at 8pm.", "music", ["live", "food-drink"], "jazz"),
    (0, 8, 14, 0, None, "Community bike repair workshop", "Inner courtyard",
     "Tools and second-hand parts on site.", "workshops-creative", ["drop-in", "outdoor", "sustainability"], "bikes"),
    (1, 9, 18, 0, None, "Meet a Brussels author", "Reading room",
     "", "talks-discussions", ["registration-required"], None),
    (2, 12, None, None, None, "Annual flea market", "Church square",
     "7am to 4pm, around a hundred stalls.", "markets-fairs", ["free", "outdoor", "family"], "market"),
    (3, 15, 23, 0, None, "Electro night", "Main hall",
     "", "music", ["dance", "live"], "electro"),
    (3, 16, 21, 0, None, "Late-night cabaret (18+)", "Main hall",
     "Adults only - explicit content.", "culture-arts", ["live", "adults"], None),
    (0, 17, 12, 0, None, "Neighbourhood shared meal", "Pedestrian street",
     "Everyone brings a dish.", "community-social", ["free", "food-drink", "outdoor", "family"], "meal"),
    (1, 22, 19, 30, None, "Book club", "Reading room",
     "", "talks-discussions", ["drop-in"], None),
    (2, 26, 9, 0, None, "Park clean-up", "Bethlehem Square",
     "Gloves and bags provided.", "environment", ["free", "drop-in", "outdoor", "sustainability"], "cleanup"),
    (3, 30, 20, 0, None, "Documentary screening and discussion", "Small hall",
     "", "film-cinema", ["live"], "cinema"),
    (1, 4, None, None, 32, "Photo exhibition: \"Our Street, Then and Now\"", "Library gallery",
     "A recurring exhibition running for several weeks - drop in any time during opening hours.",
     "culture-arts", ["free", "drop-in"], "exhibition"),
]

events = []
for src_i, offset, hh, mm, end_offset, title, loc, desc, category, extra_tags, seed in RAW:
    name, url = SRC[src_i]
    all_day = hh is None
    start = base + timedelta(days=offset, hours=hh or 0, minutes=mm or 0)
    if end_offset is not None:
        end = base + timedelta(days=end_offset)
    else:
        end = None if all_day else (start + timedelta(hours=2))
    uid = hashlib.sha1(f"{name}|{title.lower()}|{start.date()}".encode()).hexdigest()[:16]
    ev = {"title": title, "start": start.isoformat(),
          "end": end.isoformat() if end else None, "all_day": all_day,
          "location": loc, "description": desc,
          "image": IMG.format(seed=seed) if seed else None,
          "url": url, "source": name, "uid": uid, "colour": PALETTE[src_i], "category": category}
    ev["tags"] = sorted(deterministic_tags(ev) | set(extra_tags))
    events.append(ev)

payload = {"generated": datetime.now(TZ).isoformat(), "timezone": "Europe/Brussels",
           "sample": True,
           "sources": [{"name": n, "url": u, "colour": PALETTE[i],
                        "count": sum(1 for e in events if e["source"] == n), "method": "sample"}
                       for i, (n, u) in enumerate(SRC)],
           "categories": CATEGORIES,
           "tags": TAGS,
           "report": [], "events": sorted(events, key=lambda e: e["start"])}

open("docs/events.json", "w", encoding="utf-8").write(json.dumps(payload, indent=2, ensure_ascii=False))
open("docs/events.ics", "w", encoding="utf-8").write(build_ics(payload["events"], "Europe/Brussels"))
print(f"sample: {len(events)} events")
