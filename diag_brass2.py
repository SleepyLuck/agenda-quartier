"""TEMP follow-up to diag_brass.py: the homepage's own text already surfaces
two genuinely recurring Wednesday series ("Mercredis numeriques [8-12 ans]"
and "Cafes numeriques [seniors]"), both correctly tagged recurring=True and
already published - so recurring-event filtering isn't the problem. Check
whether /activites (a real page found in the first diagnostic, NOT a 404)
holds a fuller weekly programme the homepage teaser omits - e.g. an
every-single-Wednesday drop-in activity described qualitatively rather than
as specific dated occurrences.

Writes nothing; only prints.
"""
import re

import yaml
from bs4 import BeautifulSoup

from extract import fetch, linkify, parse_jsonld, parse_llm

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
tz = defaults["timezone"]
model = defaults["llm_model"]
robots = defaults.get("respect_robots", True)

for url in ["https://www.lebrass.be/activites", "https://www.lebrass.be/apropos/activites/"]:
    print("=" * 78)
    print(url)
    print("=" * 78)
    try:
        html = fetch(url, robots)
    except Exception as exc:  # noqa: BLE001
        print(f"  fetch ERROR: {type(exc).__name__}: {exc}")
        continue
    soup = BeautifulSoup(html, "lxml")
    print(f"fetched {len(html)} chars, ld+json blocks: {len(soup.find_all('script', type='application/ld+json'))}")
    jl = parse_jsonld(html, "BRASS", url, tz)
    print(f"parse_jsonld -> {len(jl)} events")

    soup2 = BeautifulSoup(html, "lxml")
    for tag in soup2(["script", "style", "noscript", "svg"]):
        tag.decompose()
    linkify(soup2, url)
    text = re.sub(r"\n{3,}", "\n\n", soup2.get_text("\n"))
    print(f"plain text length: {len(text)}")
    hits = list(re.finditer(r"mercredi|woensdag|wednesday|chaque semaine|tous les|every week", text, re.I))
    print(f"'mercredi/every week'-type mentions: {len(hits)}")
    for m in hits[:15]:
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 150)
        print(f"  ...match: {text[start:end]!r}")

    print()
    evs = parse_llm(html, "BRASS", url, tz, model)
    print(f"parse_llm -> {len(evs)} events")
    for e in sorted(evs, key=lambda e: e["start"]):
        print(f"  {e['start'][:16]}  all_day={e['all_day']!s:<5}  recurring={e.get('llm_recurring')!s:<5}  {e['title'][:55]}")
    print()
