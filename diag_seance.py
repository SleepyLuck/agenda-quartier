"""TEMP diagnostic: TIME_CACHE_VERSION=3's séance/vertoning keyword addition
did NOT restore "LE JACQUES FRANCK GOES TO THE CINEMA!"'s real time - the
real run still shows all_day=True (time_checked correctly bumped to 3, so
the re-check did happen, it just found nothing). Check the actual detail
page: does it have ld+json Event data, does "séance" appear at all, and if
so how far from a HH:MM pattern - close enough for find_time_in_text's
25-char window or not.

Writes nothing; only prints.
"""
import re

import yaml
from bs4 import BeautifulSoup

from extract import (TIME_IN_TEXT_RE, TIME_KEYWORD_RE, fetch, find_time_in_text,
                      linkify, parse_jsonld)

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
robots = defaults.get("respect_robots", True)
tz = defaults["timezone"]

url = "https://lejacquesfranck.be/event/le-jacques-franck-fait-son-cinema/2026-09-06/"
html = fetch(url, robots)
print(f"fetched {len(html)} chars")
soup = BeautifulSoup(html, "lxml")
print("ld+json blocks:", len(soup.find_all("script", type="application/ld+json")))
jl = parse_jsonld(html, "Le Jacques Franck", url, tz)
print(f"parse_jsonld -> {len(jl)} events")
for e in jl:
    print(" ", e["start"], e["all_day"], e["title"][:60])

soup2 = BeautifulSoup(html, "lxml")
for tag in soup2(["script", "style", "noscript", "svg"]):
    tag.decompose()
linkify(soup2, url)
text = re.sub(r"\n{3,}", "\n\n", soup2.get_text("\n"))
print(f"\nplain text length: {len(text)}")

print("\nall time-keyword matches and what follows (60 chars):")
for kw in TIME_KEYWORD_RE.finditer(text):
    snippet = text[kw.start():kw.start()+60].replace("\n", " ")
    print(f"  kw={kw.group()!r} at {kw.start()}: {snippet!r}")

print("\nall HH:MM-shaped matches and 30 chars before them:")
for m in TIME_IN_TEXT_RE.finditer(text):
    before = text[max(0, m.start()-30):m.start()].replace("\n", " ")
    print(f"  time={m.group()!r} at {m.start()}, preceded by: {before!r}")

print("\nfind_time_in_text ->", find_time_in_text(text))
