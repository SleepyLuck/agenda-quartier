"""TEMP diagnostic covering two separate user reports:

1. Le Poche and Le Jacques Franck seem to be missing most of their upcoming
   events - check what parse_llm actually returns today vs. what's really
   on the page (has the site changed? is our horizon_days=120 window
   legitimately excluding a lot? is anything getting mis-filtered?).

2. Maxima (communa.be) doesn't publish events on its own agenda page -
   events show up as individual blog-style posts on an "actualites"/news
   section instead (the user gave one real example URL). Find the actual
   listing page for these posts and inspect one real post's structure, so
   a "blog" extraction method can be designed against real data.

Writes nothing; only prints.
"""
import re

import yaml
from bs4 import BeautifulSoup

from extract import fetch, find_time_in_text, linkify, parse_jsonld, parse_llm

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
by_name = {s["name"]: s for s in cfg["sources"]}
tz = defaults["timezone"]
model = defaults["llm_model"]
robots = defaults.get("respect_robots", True)

print("=" * 78)
print("1. Le Poche and Le Jacques Franck - full current extraction")
print("=" * 78)
for name in ["Le Poche", "Le Jacques Franck"]:
    src = by_name[name]
    url = src["url"]
    print(f"\n--- {name} ({url}) ---")
    try:
        html = fetch(url, robots)
    except Exception as exc:  # noqa: BLE001
        print(f"  fetch ERROR: {type(exc).__name__}: {exc}")
        continue
    soup = BeautifulSoup(html, "lxml")
    print(f"  fetched {len(html)} chars, ld+json blocks: {len(soup.find_all('script', type='application/ld+json'))}")
    jl = parse_jsonld(html, name, url, tz)
    print(f"  parse_jsonld -> {len(jl)} events")
    evs = parse_llm(html, name, url, tz, model)
    print(f"  parse_llm -> {len(evs)} events (today's prompt, with linkify)")
    for e in sorted(evs, key=lambda e: e["start"]):
        print(f"    {e['start'][:16]}  all_day={e['all_day']!s:<5}  {e['title'][:55]}  url={e['url'][:70]}")

print()
print("=" * 78)
print("2. Maxima / Communa - find the real posts listing")
print("=" * 78)
base = "https://communa.be"
try:
    home = fetch(base + "/", robots)
    print(f"homepage fetched: {len(home)} chars")
    soup = BeautifulSoup(home, "lxml")
    candidates = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(strip=True).lower()
        if re.search(r"actualit|news|blog|maxima|le-mag|magazine", href, re.I) or \
           re.search(r"actualit|news|blog|maxima|updates", label):
            candidates.add(href if href.startswith("http") else base + "/" + href.lstrip("/"))
    print(f"candidate listing links found on homepage: {len(candidates)}")
    for c in sorted(candidates)[:20]:
        print(" ", c)
except Exception as exc:  # noqa: BLE001
    print(f"homepage fetch ERROR: {type(exc).__name__}: {exc}")

for guess in ["/actualites/", "/blog/", "/news/", "/category/actualites/", "/le-mag/", "/magazine/"]:
    try:
        r = fetch(base + guess, robots)
        print(f"guess {guess} -> {len(r)} chars, title: "
              f"{BeautifulSoup(r, 'lxml').title.get_text(strip=True) if BeautifulSoup(r, 'lxml').title else '?'}")
    except Exception as exc:  # noqa: BLE001
        print(f"guess {guess} -> ERROR {type(exc).__name__}: {exc}")

print()
print("--- the example post the user gave ---")
post_url = "https://communa.be/maxima-focus-septembre-collectif-marthe-florence-verney/"
try:
    html = fetch(post_url, robots)
    print(f"fetched {len(html)} chars")
    soup = BeautifulSoup(html, "lxml")
    print("title:", soup.title.get_text(strip=True) if soup.title else "?")
    print("ld+json blocks:", len(soup.find_all("script", type="application/ld+json")))
    jl = parse_jsonld(html, "Maxima", post_url, tz)
    print(f"parse_jsonld on this single post -> {len(jl)} events")
    linkify(soup, post_url)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    print(f"plain text length: {len(text)}")
    print("first 1500 chars of text:")
    print(text[:1500])
    print("...")
    found_time = find_time_in_text(text)
    print("find_time_in_text ->", found_time)
    evs = parse_llm(html, "Maxima", post_url, tz, model)
    print(f"parse_llm on this single post -> {len(evs)} events")
    for e in evs:
        print(f"    {e['start']}  {e['title'][:60]}")
except Exception as exc:  # noqa: BLE001
    print(f"post fetch ERROR: {type(exc).__name__}: {exc}")
