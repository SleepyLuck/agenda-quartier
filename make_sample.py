"""Generate demo data so the page has something to show before the first real run."""
import json, hashlib, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, ".")
from scrape import build_ics, PALETTE

TZ = ZoneInfo("Europe/Brussels")
base = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)

SRC = [("Maison de quartier", "https://example.org/agenda/"),
       ("Bibliothèque communale", "https://example.org/bib/"),
       ("Comité de quartier", "https://example.org/comite/"),
       ("Salle de concert", "https://example.org/concerts/")]

RAW = [
    (0, 1, 18, 30, "Repair Café", "Rue de l'Église 12", "Apportez un appareil cassé, on le répare ensemble."),
    (1, 2, 10, 0, "Heure du conte en français et en néerlandais", "Section jeunesse", "Pour les 3–6 ans, entrée libre."),
    (2, 3, 19, 0, "Assemblée de quartier sur le plan de circulation", "Salle communale", "Présentation puis questions."),
    (3, 5, 20, 30, "Concert : trio de jazz", "Grande salle", "Portes à 20h."),
    (0, 8, 14, 0, "Atelier vélo participatif", "Cour intérieure", "Outils et pièces d'occasion sur place."),
    (1, 9, 18, 0, "Rencontre avec une autrice bruxelloise", "Salle de lecture", ""),
    (2, 12, None, None, "Brocante annuelle", "Parvis", "De 7h à 16h, une centaine d'exposants."),
    (3, 15, 21, 0, "Soirée électro", "Grande salle", ""),
    (0, 17, 12, 0, "Repas de quartier", "Rue piétonne", "Chacun apporte un plat."),
    (1, 22, 19, 30, "Club de lecture", "Salle de lecture", ""),
    (2, 26, 9, 0, "Nettoyage du square", "Square Bethléem", "Gants et sacs fournis."),
    (3, 30, 20, 0, "Projection documentaire et débat", "Petite salle", ""),
]

events = []
for src_i, offset, hh, mm, title, loc, desc in RAW:
    name, url = SRC[src_i]
    all_day = hh is None
    start = base + timedelta(days=offset, hours=hh or 0, minutes=mm or 0)
    end = None if all_day else (start + timedelta(hours=2))
    uid = hashlib.sha1(f"{name}|{title.lower()}|{start.date()}".encode()).hexdigest()[:16]
    events.append({"title": title, "start": start.isoformat(),
                   "end": end.isoformat() if end else None, "all_day": all_day,
                   "location": loc, "description": desc, "url": url,
                   "source": name, "uid": uid, "colour": PALETTE[src_i]})

payload = {"generated": datetime.now(TZ).isoformat(), "timezone": "Europe/Brussels",
           "sample": True,
           "sources": [{"name": n, "url": u, "colour": PALETTE[i],
                        "count": sum(1 for e in events if e["source"] == n), "method": "sample"}
                       for i, (n, u) in enumerate(SRC)],
           "report": [], "events": sorted(events, key=lambda e: e["start"])}

open("docs/events.json", "w", encoding="utf-8").write(json.dumps(payload, indent=2, ensure_ascii=False))
open("docs/events.ics", "w", encoding="utf-8").write(build_ics(payload["events"], "Europe/Brussels"))
print(f"sample: {len(events)} events")
