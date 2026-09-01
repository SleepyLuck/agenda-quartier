"""TEMP diagnostic: user reports a BRASS event happening every Wednesday is
missing from the calendar. Current source config points at the BRASS
homepage (https://www.lebrass.be/), not a dedicated agenda page - check
whether that's the problem, whether a weekly Wednesday listing exists
somewhere on the site, and what parse_llm actually returns from the
homepage today (including the "recurring" field, so we can tell if a
recurring listing is being found but mis-classified/filtered, vs. never
found at all).

Writes nothing; only prints.
"""
import re

import yaml
from bs4 import BeautifulSoup

from extract import fetch, linkify, parse_jsonld, parse_llm

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
by_name = {s["name"]: s for s in cfg["sources"]}
tz = defaults["timezone"]
model = defaults["llm_model"]
robots = defaults.get("respect_robots", True)

src = by_name["BRASS"]
url = src["url"]
print("=" * 78)
print(f"1. BRASS homepage as currently configured ({url})")
print("=" * 78)
html = fetch(url, robots)
soup = BeautifulSoup(html, "lxml")
print(f"fetched {len(html)} chars, ld+json blocks: {len(soup.find_all('script', type='application/ld+json'))}")
jl = parse_jsonld(html, "BRASS", url, tz)
print(f"parse_jsonld -> {len(jl)} events")

# raw-text scan for "mercredi"/"wednesday" before any LLM call, so we know if
# the word even reaches the page the scraper fetches.
soup2 = BeautifulSoup(html, "lxml")
for tag in soup2(["script", "style", "noscript", "svg"]):
    tag.decompose()
linkify(soup2, url)
text = re.sub(r"\n{3,}", "\n\n", soup2.get_text("\n"))
print(f"plain text length: {len(text)}")
for m in re.finditer(r"mercredi|woensdag|wednesday", text, re.I):
    start = max(0, m.start() - 120)
    end = min(len(text), m.end() + 120)
    print(f"  ...match at {m.start()}: {text[start:end]!r}")

print()
evs = parse_llm(html, "BRASS", url, tz, model)
print(f"parse_llm on homepage -> {len(evs)} events")
for e in sorted(evs, key=lambda e: e["start"]):
    print(f"  {e['start'][:16]}  all_day={e['all_day']!s:<5}  recurring={e.get('llm_recurring')!s:<5}  {e['title'][:55]}")

print()
print("=" * 78)
print("2. candidate dedicated agenda/programme URLs on lebrass.be")
print("=" * 78)
for guess in ["/agenda", "/agenda/", "/programme", "/programme/", "/activites",
              "/activites/", "/calendrier", "/calendrier/", "/events", "/events/",
              "/fr/agenda", "/fr/programme", "/ateliers", "/ateliers/", "/cours", "/cours/"]:
    try:
        r = fetch(url.rstrip("/") + guess, robots)
        t = BeautifulSoup(r, "lxml")
        title = t.title.get_text(strip=True) if t.title else "?"
        print(f"guess {guess:20s} -> {len(r)} chars, title: {title}")
    except Exception as exc:  # noqa: BLE001
        print(f"guess {guess:20s} -> ERROR {type(exc).__name__}: {exc}")

print()
print("candidate agenda links found in homepage nav/menu:")
candidates = set()
for a in soup.find_all("a", href=True):
    href = a["href"]
    label = a.get_text(strip=True).lower()
    if re.search(r"agenda|programme|activit|calendrier|events|ateliers|cours", href, re.I) or \
       re.search(r"agenda|programme|activit|calendrier|events|ateliers|cours", label):
        full = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
        candidates.add((full, label[:40]))
for full, label in sorted(candidates):
    print(f"  {full}  (label: {label!r})")
