"""TEMP diagnostic: re-check every source the user flagged as "events exist but not found",
using discovery.py's recommend_method() to see if any has a non-LLM path (ics/feed/wordpress/
jsonld/recipe) that the simple auto cascade in extract.py missed. Sources already configured
as method: browser are rendered first (discovery.py's static analysis can't see JS-injected
content on the raw fetch).

Writes nothing; only prints.
"""
import yaml

import discovery as D
from extract import fetch, fetch_rendered

sources = yaml.safe_load(open("sources.yml", encoding="utf-8"))["sources"]
names = ['GC Pianofabriek', 'La Tricoterie', 'Recyclart', 'Le Jacques Franck', 'Fuse', 'Le Poche',
         'Sounds Jazz Club', 'U-Square', 'BRASS', 'WIELS', 'CCLJ', 'GC Ten Weyngaert', 'Park Poétik',
         'Le Senghor', 'Flagey', 'BOZAR', 'KVS', 'Kaaitheater', 'Ancienne Belgique',
         'Saint-Gilles brocantes & braderies (commune)', 'Maison des Cultures de Saint-Gilles',
         'Le Rideau', 'Théâtre National Wallonie-Bruxelles', 'La Bellone',
         'FTI Brussel (programme page)', 'Agenda engagé (Syndicats magazine)', 'Protestbase Bruxelles',
         'Stuut', 'Conférences gesticulées (network catalogue)', 'Conférences gesticulées (per-day pages)',
         "Centre d'Action Laïque events", 'English Comedy Brussels', 'Club Carré agenda']
by_name = {s["name"]: s for s in sources}

for name in names:
    src = by_name.get(name)
    if not src:
        print(f"\n{name}: NOT IN sources.yml")
        continue
    url, method = src["url"], src.get("method", "auto")
    print(f"\n\n########## {name} ({url}) — current method: {method} ##########")
    try:
        html = fetch_rendered(url) if method == "browser" else fetch(url)
        rec = D.recommend_method(html, url)
        print(f"  discovery recommends: {rec['method']}  ({rec['why']})")
        if rec["method"] not in ("llm", "none-or-browser"):
            print(f"  *** POSSIBLE NON-LLM PATH — investigate ***")
        if rec["pagination"]:
            print(f"  pagination hints: {rec['pagination']}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {type(exc).__name__}: {exc}")
