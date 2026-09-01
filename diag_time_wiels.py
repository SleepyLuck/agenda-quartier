"""TEMP diagnostic: WIELS returns 0 events, and several llm-rung sources
return events with no time (all_day=true for basically everything) even
though these are real ticketed shows, not day-long events.

For WIELS: fetch the real page, check length, search for "Free Nocturne"
(a real upcoming event the user named), check ld+json block count, and
run parse_llm directly to see the actual model output.

For the all-day sources: fetch (or render) the same text parse_llm sees,
print a slice around the first few date-like matches to check whether a
time is actually present in the text near the date, then run parse_llm
and print exactly what "start" values come back.

Writes nothing; only prints.
"""
import re

import yaml
from bs4 import BeautifulSoup

from extract import fetch, fetch_rendered, parse_jsonld, parse_llm

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
by_name = {s["name"]: s for s in cfg["sources"]}
tz = defaults["timezone"]
model = defaults["llm_model"]

print("=" * 78)
print("1. WIELS")
print("=" * 78)
src = by_name["WIELS"]
url = src["url"]
html = fetch(url, defaults.get("respect_robots", True))
print(f"fetched {len(html)} chars from {url}")
soup = BeautifulSoup(html, "lxml")
blocks = soup.find_all("script", type="application/ld+json")
print(f"ld+json blocks: {len(blocks)}")
lower = html.lower()
for needle in ["free nocturne", "nocturne"]:
    idx = lower.find(needle)
    print(f'  "{needle}" found in raw HTML at index {idx}' if idx >= 0
          else f'  "{needle}" NOT found in raw HTML')
    if idx >= 0:
        print("    context:", re.sub(r"\s+", " ", html[max(0, idx-200):idx+200]))

for tag in soup(["script", "style", "noscript", "svg"]):
    tag.decompose()
text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
print(f"plain text length: {len(text)} chars (parse_llm sends the first 24000)")
idx = text.lower().find("nocturne")
print(f'"nocturne" in plain text at index {idx}' if idx >= 0 else '"nocturne" NOT in plain text at all')
if idx >= 0:
    print("  context:", repr(text[max(0, idx-150):idx+150]))
print("  is that within the first 24000 chars sent to the model?", idx >= 0 and idx < 24000)

evs = parse_jsonld(html, "WIELS", url, tz)
print(f"parse_jsonld -> {len(evs)} events")
evs = parse_llm(html, "WIELS", url, tz, model)
print(f"parse_llm -> {len(evs)} events")
for e in evs[:10]:
    print(f"    {e['start']}  {e['title'][:60]}")

print()
print("=" * 78)
print("2. Sources where every (or nearly every) event lost its time")
print("=" * 78)
for name in ["Ancienne Belgique", "Fuse", "KVS", "Le Jacques Franck", "Le Poche",
             "Recyclart", "U-Square"]:
    src = by_name[name]
    url = src["url"]
    print(f"\n--- {name} ({url}) ---")
    try:
        html = fetch(url, defaults.get("respect_robots", True))
    except Exception as exc:  # noqa: BLE001
        print(f"  fetch ERROR: {type(exc).__name__}: {exc}")
        continue
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    # find a few date-like spots and show what's around them
    date_re = re.compile(
        r"\b\d{1,2}[\s/.-](janv|f[ée]vr|mars|avr|mai|juin|juil|ao[ûu]t|sept|oct|nov|d[ée]c"
        r"|jan|feb|maa|apr|mei|jun|jul|aug|sep|okt|dec)\w*", re.I)
    matches = list(date_re.finditer(text))
    print(f"  text length: {len(text)}, date-like matches: {len(matches)}")
    time_re = re.compile(r"\b\d{1,2}[:h]\d{2}\b")
    for m in matches[:3]:
        window = text[max(0, m.start()-60):m.start()+120]
        has_time = bool(time_re.search(window))
        print(f"    ...{repr(window)}... [time-like nearby: {has_time}]")

    evs = parse_llm(html, name, url, tz, model)
    print(f"  parse_llm -> {len(evs)} events, sample starts:")
    for e in evs[:5]:
        print(f"    {e['start']}  {e['title'][:55]}")
