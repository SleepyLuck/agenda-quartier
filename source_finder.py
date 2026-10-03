"""Helpers for the 'find related sites' hunt (find-related-sites-instructions.md).

    python source_finder.py queries --month "October 2026" --family theatre-performing
        -> search queries (FR/NL/EN) for that family x the priority communes

    python source_finder.py harvest <url>
        -> distinct external-domain links found on an aggregator/listing page
           (needs network — run via the probe GitHub Actions workflow, not locally)

    python source_finder.py score <url>
        -> robots/method/neighbourhood/group verdict for one candidate, per the
           instructions' pass rule (needs network — same as above)

No Anthropic API calls anywhere in this file: everything here is the
deterministic-first step: run this before ever reaching for the LLM method.
"""
from __future__ import annotations
import sys
from datetime import date
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

import discovery as D
import known_sources as K
from extract import UA, robots_allows
from keyword_classify import classify

COMMUNES = [
    ("Saint-Gilles", "Sint-Gillis"),
    ("Forest", "Vorst"),
    ("Ixelles", "Elsene"),
    ("Anderlecht", "Anderlecht"),
    ("Marolles", "Brussels centre"),
]

AGENDA_WORDS = ["agenda", "programme", "events", "calendrier", "programma", "kalender"]


def build_queries(family: str, month: str) -> list[str]:
    try:
        from keyword_classify import GROUPS
    except ImportError:
        GROUPS = {}
    words = GROUPS.get(family, [family])[:4]
    out = []
    for fr, nl in COMMUNES:
        for w in words:
            for ag in AGENDA_WORDS[:2]:
                out.append(f"{w} {fr} {month} {ag}")
                if nl != fr:
                    out.append(f"{w} {nl} {month} {ag}")
    # de-dupe, keep order
    seen = set()
    uniq = []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr,nl,en"}, timeout=25)
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    r.raise_for_status()
    return r.text


def harvest(url: str) -> list[str]:
    html = _get(url)
    soup = BeautifulSoup(html, "lxml")
    base_host = urlparse(url).netloc.lower().removeprefix("www.")
    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        host = urlparse(href).netloc.lower().removeprefix("www.")
        if not host or host == base_host:
            continue
        seen.setdefault(host, href)
    return sorted(seen.values())


def score(url: str, keys: set[str] | None = None) -> dict:
    import os
    if keys is None:
        keys = set(open("known_sources.txt").read().split()) if os.path.exists("known_sources.txt") else set()
    allowed = robots_allows(url)
    html = _get(url)
    today = date.today()
    rec = D.recommend_method(html, url, today)
    blocks = D.find_listing_blocks(html, today)
    n_listed_events = blocks[0]["items"] if blocks else 0
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    groups = classify(text)
    tl = text.lower()
    commune_hits = sum(1 for fr, nl in COMMUNES if fr.lower() in tl or nl.lower() in tl)
    already_known = K.is_known(url, keys)
    enough_events = max(n_listed_events, rec["n_dates_in_text"] // 3) >= 3
    verdict = allowed and not already_known and enough_events and commune_hits >= 1 and bool(groups)
    return {
        "url": url,
        "robots_ok": allowed,
        "already_known": already_known,
        "recommended_method": rec["method"],
        "why": rec["why"],
        "n_listed_events": n_listed_events,
        "n_dates_in_text": rec["n_dates_in_text"],
        "commune_hits": commune_hits,
        "groups": groups,
        "pass": bool(verdict),
    }


def _print_score(s: dict) -> None:
    print(f"\n{s['url']}")
    print(f"  robots_ok={s['robots_ok']}  already_known={s['already_known']}  pass={s['pass']}")
    print(f"  method={s['recommended_method']} ({s['why']})")
    print(f"  listed_events={s['n_listed_events']}  dates_in_text={s['n_dates_in_text']}  commune_hits={s['commune_hits']}")
    print(f"  groups={s['groups']}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "queries":
        month, family = "", ""
        args = argv[2:]
        for i, a in enumerate(args):
            if a == "--month" and i + 1 < len(args):
                month = args[i + 1]
            if a == "--family" and i + 1 < len(args):
                family = args[i + 1]
        for q in build_queries(family, month):
            print(q)
        return 0
    if cmd == "harvest":
        for u in harvest(argv[2]):
            print(u)
        return 0
    if cmd == "score":
        for u in argv[2:]:
            try:
                _print_score(score(u))
            except Exception as exc:
                print(f"\n{u}\n  ERROR: {type(exc).__name__}: {exc}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
