"""Event discovery helpers: find agenda pages, event links, dates, attributes, ticket/social
signals, repeated listing blocks and social-media captions.  Pure functions (no network) except
the CLI at the bottom, which reuses extract.fetch.  No API/LLM calls anywhere in this module.

Usage:
    python discovery.py https://example.org/agenda            # report on one page
    python discovery.py https://example.org/agenda --yaml     # + sources.yml snippet
    python discovery.py --caption post.txt --posted 2026-10-01 # parse a pasted Instagram caption
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import lexicon as L


def fold(s: str) -> str:
    """lower-case + strip accents, so 'Événements' == 'evenements'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def has_any(text: str, words: list[str]) -> list[str]:
    t = fold(text)
    return [w for w in words if re.search(r"(?<![a-z0-9])" + re.escape(fold(w)) + r"(?![a-z0-9])", t)]


# ------------------------------------------------------------------ dates and times
_M = "|".join(sorted(L.MONTHS, key=len, reverse=True))
_W = "|".join(sorted(L.WEEKDAYS, key=len, reverse=True))
_WD = rf"(?:(?P<wd>{_W})\.?,?\s+)?"
RE_NUM_FULL = re.compile(rf"{_WD}(?P<d>\d{{1,2}})[./-](?P<m>\d{{1,2}})[./-](?P<y>20\d{{2}}|\d{{2}})(?!\d)")
RE_NUM_SHORT = re.compile(rf"{_WD}(?<![\d./])(?P<d>\d{{1,2}})/(?P<m>\d{{1,2}})(?![\d/])")
RE_TEXT_DMY = re.compile(
    rf"{_WD}(?P<d>\d{{1,2}})(?:er|e|st|nd|rd|th)?\.?\s*(?P<mon>{_M})\.?(?:\s+(?P<y>20\d{{2}}))?(?![a-z])", re.I)
RE_TEXT_MDY = re.compile(
    rf"{_WD}(?P<mon>{_M})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<y>20\d{{2}}))?(?![\d:a-z])", re.I)
RE_RANGE = re.compile(
    rf"(?:du|van|from)?\s*(?<!['’])(?<!['’]\d)(?P<d1>\d{{1,2}})(?:er)?\.?\s*(?P<m1>{_M})?\.?\s*(?:au|tot|to|-|–|—|>|→)\s*"
    rf"(?P<d2>\d{{1,2}})(?:er)?\.?\s*(?P<m2>{_M})\.?(?:\s+(?P<y>20\d{{2}}))?(?![a-z])", re.I)
RE_RANGE_EN = re.compile(
    rf"(?P<m1>{_M})\.?\s+(?<!['’])(?<!['’]\d)(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|>|→|to|until|through)\s*"
    rf"(?:(?P<m2>{_M})\.?\s+)?(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<y>20\d{{2}}))?(?![\d:a-z])", re.I)
RE_TIME = re.compile(
    r"(?<![\d.,])(?P<h>[01]?\d|2[0-3])\s*(?:h|:|u(?=\d))\s*(?P<min>[0-5]\d)?(?:\s*(?P<ap>am|pm))?(?![\d])"
    r"|(?<![\d.,:])(?P<h12>1[0-2]|0?[1-9])(?::(?P<m12>[0-5]\d))?\s*(?P<ap2>am|pm)\b", re.I)


def _mon(s: str) -> int:
    return L.MONTHS[fold(s).rstrip(".")]


def _wd(s: str | None) -> int | None:
    return L.WEEKDAYS.get(fold(s).rstrip(".")) if s else None


def _resolve_year(day: int, month: int, today: date, weekday: int | None, year: int | None) -> tuple[date | None, str]:
    """Return (date, how). With an explicit year trust it; otherwise use the weekday to pick the
    year (checks year-1..year+1), else the next occurrence within ~60 days back."""
    def mk(y):
        try:
            return date(y, month, day)
        except ValueError:
            return None
    if year:
        d = mk(year + 2000 if year < 100 else year)
        if d and not (-400 <= (d - today).days <= 1100):
            return None, "year-out-of-window"
        return d, "explicit-year"
    cands = [(y, mk(y)) for y in (today.year - 1, today.year, today.year + 1)]
    cands = [(y, d) for y, d in cands if d]
    if weekday is not None:
        ok = [d for y, d in cands if d.weekday() == weekday and -60 <= (d - today).days <= 420]
        if ok:
            return min(ok, key=lambda d: abs((d - today).days)), "weekday-match"
        return None, "weekday-mismatch"      # e.g. 'vendredi 12 octobre' that is not a Friday: reject
    ok = [d for y, d in cands if -60 <= (d - today).days <= 365]
    if ok:
        return min(ok, key=lambda d: d if d >= today - timedelta(days=60) else date.max), "inferred-year"
    return None, "no-window"


def find_times(text: str) -> list[tuple[int, int, int]]:
    """[(hour, minute, position)] 24h; supports 19h30, 19:30, 19h, 7:30 PM, 7pm."""
    out = []
    for m in RE_TIME.finditer(text):
        if m.group("h") is not None:
            h, mi, ap = int(m.group("h")), int(m.group("min") or 0), (m.group("ap") or "").lower()
            if m.group("min") is None and ":" not in m.group(0) and "h" not in m.group(0).lower() and "u" not in m.group(0).lower():
                continue
        else:
            h, mi, ap = int(m.group("h12")), int(m.group("m12") or 0), m.group("ap2").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.append((h, mi, m.start()))
    return out


def find_dates(text: str, today: date | None = None) -> list[dict]:
    """Find dates / date ranges in free text (FR, NL, EN).  Each hit:
    {start: date, end: date|None, time: 'HH:MM'|None, raw, how, confidence}.
    A weekday word next to a day-month is used to pick the right year and to REJECT impossible
    dates (typo or wrong year) instead of guessing."""
    today = today or date.today()
    orig = text
    ft = fold(text)
    text = ft if len(ft) == len(orig) else orig       # accent-insensitive; positions stay aligned
    hits, taken = [], []

    def free(a, b):
        return all(b <= x or a >= y for x, y in taken)

    def add(m, start, end, how, conf):
        taken.append((m.start(), m.end()))
        hits.append({"start": start, "end": end, "time": None, "raw": orig[m.start():m.end()].strip(),
                     "how": how, "confidence": conf, "pos": m.start(), "_end": m.end()})

    for m in list(RE_RANGE.finditer(text)) + list(RE_RANGE_EN.finditer(text)):
        d1, d2 = int(m.group("d1")), int(m.group("d2"))
        m2 = _mon(m.group("m2") or m.group("m1")); m1 = _mon(m.group("m1")) if m.group("m1") else m2
        y = int(m.group("y")) if m.group("y") else None
        end, how = _resolve_year(d2, m2, today, None, y)
        if not end:
            continue
        start, _ = _resolve_year(d1, m1, today, None, y)
        if start and start > end and not m.group("m1"):
            continue
        if not free(m.start(), m.end()):
            continue
        if start and start > end:            # 15 Dec - 6 Jan
            start = date(start.year - 1, start.month, start.day)
        if start and free(m.start(), m.end()) and 0 <= (end - start).days <= 200:
            add(m, start, end, "range", "high" if y else "medium")
    for rx, kind in ((RE_NUM_FULL, "num"), (RE_TEXT_DMY, "text"), (RE_TEXT_MDY, "text-en"), (RE_NUM_SHORT, "num-short")):
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            d = int(m.group("d"))
            mo = int(m.group("m")) if "m" in m.groupdict() and m.group("m") else _mon(m.group("mon"))
            if not 1 <= mo <= 12 or not 1 <= d <= 31:
                continue
            y = int(m.group("y")) if m.groupdict().get("y") else None
            res, how = _resolve_year(d, mo, today, _wd(m.group("wd")), y)
            if not res:
                continue
            conf = "high" if how in ("explicit-year", "weekday-match") else "low" if kind == "num-short" else "medium"
            add(m, res, None, f"{kind}:{how}", conf)
    hits.sort(key=lambda h: h["pos"])
    for i, h in enumerate(hits):          # attach a time, but never one that belongs to the neighbouring date
        nxt = hits[i + 1]["pos"] if i + 1 < len(hits) else len(text)
        prv = hits[i - 1]["_end"] if i else 0
        tail = re.split(r"[\n;|]| / ", text[h["_end"]: min(h["_end"] + 45, nxt)])[0]
        head = re.split(r"[\n;|]| / ", text[max(prv, h["pos"] - 20): h["pos"]])[-1]
        t = next(iter(find_times(tail)), None) or next(iter(find_times(head)), None)
        h["time"] = f"{t[0]:02d}:{t[1]:02d}" if t else None
    for h in hits:
        del h["_end"]
    return hits


# ------------------------------------------------------------------ attributes
def extract_attributes(text: str) -> dict:
    """Pull structured attributes from event text.  Every value is optional."""
    t = fold(text)
    out: dict = {}
    prices = []
    for m in re.finditer(r"(?:€|eur(?:o)?s?)\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:€|eur(?:o)?s?\b)", t):
        prices.append(float((m.group(1) or m.group(2)).replace(",", ".")))
    rng = re.search(r"(\d+(?:[.,]\d+)?)\s*€?\s*(?:>|-|–|a|tot|to)\s*(\d+(?:[.,]\d+)?)\s*€", t)
    if rng:
        prices += [float(rng.group(1).replace(",", ".")), float(rng.group(2).replace(",", "."))]
    if prices:
        out["price_min"], out["price_max"] = min(prices), max(prices)
    free_hits = [w for w in has_any(text, L.FREE_WORDS) if w != "free" or "free" in t.split()]
    if free_hits and not prices:
        out["free"] = True
    elif free_hits and prices:
        out["free_mentioned_with_price"] = True        # e.g. "free for under 12": needs human/LLM check
    if has_any(text, L.PAY_WHAT_WORDS):
        out["pay_what_you_want"] = True
    if has_any(text, L.BOOKING_WORDS):
        out["booking"] = has_any(text, L.BOOKING_WORDS)[0]
    if has_any(text, L.SOLD_OUT_WORDS):
        out["sold_out"] = True
    if has_any(text, L.CANCELLED_WORDS):
        out["cancelled_or_postponed"] = True
    if has_any(text, L.RECURRING_WORDS):
        out["recurring"] = True
    m = re.search(r"(?:des|a partir de|vanaf|from|ab|age|leeftijd)\s*(\d{1,2})\s*(?:ans|jaar|years|yrs|\+)?|(\d{1,2})\s*(?:\+|ans\s*et\s*plus|jaar\+)", t)
    if m:
        out["min_age"] = int(m.group(1) or m.group(2))
    if has_any(text, L.AUDIENCE_KIDS):
        out["audience_kids"] = True
    if has_any(text, L.AUDIENCE_ADULTS):
        out["audience_adults"] = True
    if has_any(text, L.ACCESSIBLE_WORDS):
        out["accessibility_hint"] = has_any(text, L.ACCESSIBLE_WORDS)[0]
    m = re.search(r"(?:duree|duur|duration)\s*[:\s]\s*(\d{1,2})\s*(?:h|u)\s*(\d{2})?|(?:duree|duur|duration)\s*[:\s]\s*(\d{2,3})\s*(?:'|min)", t)
    if m:
        out["duration_min"] = (int(m.group(1)) * 60 + int(m.group(2) or 0)) if m.group(1) else int(m.group(3))
    m = re.search(r"surtitr\w*\s*(?:en)?\s*(anglais|english|francais|french|neerlandais|nederlands|dutch|\ben\b|\bfr\b|\bnl\b)", t)
    if m:
        out["surtitles"] = m.group(1)
    langs = set(re.findall(r"\b(fr|nl|en)\s*[/&+]\s*(fr|nl|en)\b", t))
    if langs:
        out["languages"] = sorted({x for p in langs for x in p})
    labels = {}
    for line in re.split(r"[\n|]", text):
        mm = re.match(r"\s*([A-Za-zÀ-ÿ' ]{2,22})\s*[:：]\s*(.{2,120})$", line)
        if mm:
            key = fold(mm.group(1)).strip()
            for field, names in L.LABELS.items():
                if key in [fold(n) for n in names]:
                    labels.setdefault(field, mm.group(2).strip())
    if labels:
        out["labelled"] = labels
    return out


# ------------------------------------------------------------------ links
def _anchor_text(a) -> str:
    return " ".join(a.get_text(" ", strip=True).split())


def score_link(href: str, text: str, base: str) -> tuple[int, list[str]]:
    """Score a link: how likely is it an individual event page? Returns (score, reasons)."""
    full = urljoin(base, href)
    pu, bu = urlparse(full), urlparse(base)
    if pu.scheme not in ("http", "https"):
        return -99, ["not http"]
    f = fold(full)
    score, why = 0, []
    if any(x in f for x in L.LINK_EXCLUDE if x != "#") and "agenda" not in f.rsplit("/", 1)[-1]:
        return -5, ["boilerplate path"]
    segs = [s for s in pu.path.lower().split("/") if s]
    for i, s in enumerate(segs[:-1]):
        if fold(s) in L.EVENT_PATH_SEGMENTS and len(segs) > i + 1 and len(segs[-1]) > 3:
            score += 3; why.append(f"/{s}/<slug>"); break
    if re.search(r"/20\d{2}[-/]\d{2}[-/]\d{2}|/\d{4,}-|[?&](?:event|id|eid)=\d+", f):
        score += 2; why.append("date/id in url")
    if find_dates(text) or find_dates(href.replace("-", " ")):
        score += 2; why.append("date in anchor/url")
    if has_any(text, L.EVENT_TYPE_WORDS):
        score += 1; why.append("event word in anchor")
    if len(text) < 4:
        score -= 1; why.append("tiny anchor")
    if any(n in f for n in L.LISTING_NOISE):
        score -= 3; why.append("listing noise")
    if pu.netloc != bu.netloc:
        host = pu.netloc.lower()
        if any(k in host for k in L.TICKET_PLATFORMS):
            score += 2; why.append("ticket platform")
        else:
            score -= 2; why.append("other host")
    return score, why


def find_event_links(html: str, base: str, min_score: int = 3) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"]).split("#")[0]
        if full in seen:
            continue
        s, why = score_link(a["href"], _anchor_text(a), base)
        if s >= min_score:
            seen.add(full)
            out.append({"url": full, "text": _anchor_text(a)[:120], "score": s, "why": why})
    return sorted(out, key=lambda x: -x["score"])


def find_agenda_links(html: str, base: str) -> list[dict]:
    """Links that lead to a LISTING of events (use on a homepage to locate the agenda page)."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"]).split("#")[0]
        if full in seen or urlparse(full).netloc != urlparse(base).netloc:
            continue
        txt, path = _anchor_text(a), fold(urlparse(full).path)
        hit_t, hit_p = has_any(txt, L.AGENDA_WORDS), [w for w in L.AGENDA_WORDS if fold(w).replace(" ", "-") in path]
        s = 2 * bool(hit_t) + 2 * bool(hit_p) + (1 if a.find_parent(["nav", "header"]) else 0)
        if s >= 2 and not any(n in path for n in L.LINK_EXCLUDE if n != "#"):
            seen.add(full)
            out.append({"url": full, "text": txt[:80], "score": s, "why": hit_t[:2] + hit_p[:2]})
    return sorted(out, key=lambda x: (-x["score"], len(x["url"])))


def find_pagination(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tag in soup.find_all(["link", "a", "button"]):
        href = tag.get("href") or tag.get("data-href") or tag.get("data-url")
        txt = _anchor_text(tag) if tag.name != "link" else ""
        rel = " ".join(tag.get("rel", [])) if tag.get("rel") else ""
        why = None
        if "next" in rel:
            why = "rel=next"
        elif txt and has_any(txt, L.PAGINATION_WORDS):
            why = f"text '{txt[:30]}'"
        elif href and re.search(r"[?&](?:page|paged|p|pg|month|mois|maand|offset)=\d+|/page/\d+", href):
            why = "page/month param"
        if why and href:
            out.append({"url": urljoin(base, href), "why": why})
    # JS 'load more' buttons carry no href: flag them so a browser/XHR step is considered
    if soup.find(string=lambda s: s and has_any(s, ["load more", "charger plus", "voir plus", "meer laden"])) and not out:
        out.append({"url": None, "why": "load-more button without href -> need browser or XHR"})
    return out


# ------------------------------------------------------------------ signals
def extract_signals(html: str, base: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    sig: dict = {"ticket_platforms": {}, "social": {}, "feeds": [], "ics": [], "jsonld_event_types": [],
                 "microdata_events": 0, "fingerprints": [], "mailto": []}
    for a in soup.find_all("a", href=True):
        href, host = urljoin(base, a["href"]), urlparse(urljoin(base, a["href"])).netloc.lower()
        for frag, name in L.TICKET_PLATFORMS.items():
            if frag in host or (frag.endswith(".") and host.startswith(frag)):
                if name in ("tickets-subdomain", "shop-subdomain") and urlparse(base).netloc.split(".", 1)[-1] in host:
                    continue
                sig["ticket_platforms"].setdefault(name, []).append(href)
        for frag, name in L.SOCIAL_DOMAINS.items():
            if frag in host:
                path = urlparse(href).path.strip("/")
                if path and path.split("/")[0] not in ("sharer", "share", "intent", "plugins", "tr", "dialog"):
                    sig["social"].setdefault(name, [])
                    if href not in sig["social"][name]:
                        sig["social"][name].append(href)
        if href.lower().split("?")[0].endswith(".ics") or "ical=1" in href or "webcal:" in href or "outlook-ical" in href:
            sig["ics"].append(href)
        if href.startswith("mailto:"):
            sig["mailto"].append(href[7:])
    for l in soup.find_all("link", href=True):
        t = (l.get("type") or "").lower()
        if "rss" in t or "atom" in t or "calendar" in t:
            sig["feeds"].append({"url": urljoin(base, l["href"]), "type": t, "title": l.get("title")})
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(s.string or "")
        except Exception:
            continue
        stack = [blob]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack += n
            elif isinstance(n, dict):
                ty = n.get("@type")
                for x in (ty if isinstance(ty, list) else [ty]):
                    if isinstance(x, str) and x.endswith("Event"):
                        sig["jsonld_event_types"].append(x)
                stack += [v for v in n.values() if isinstance(v, (dict, list))]
    sig["microdata_events"] = len(soup.select('[itemtype*="schema.org/Event"]'))
    raw = html.lower()
    sig["fingerprints"] = sorted({v for k, v in L.FINGERPRINTS.items() if k in raw})
    for k in ("ticket_platforms", "social"):
        sig[k] = {n: v[:3] for n, v in sig[k].items()}
    return sig


def instagram_handles(html_or_text: str) -> list[str]:
    return sorted(set(re.findall(r"instagram\.com/([A-Za-z0-9._]{2,30})/?(?![A-Za-z0-9._/])", html_or_text)) - {"p", "reel", "explore", "accounts"})


# ------------------------------------------------------------------ repeated listing blocks
def _listing_candidates(soup, today: date | None, min_items: int) -> list[tuple]:
    """Shared core for find_listing_blocks()/extract_recipe_events(): containers whose
    children repeat and mostly carry a date. Returns (parent_tag, item_tags, with_date, with_link)."""
    out = []
    for parent in soup.find_all(True):
        kids = [c for c in parent.find_all(True, recursive=False)]
        if len(kids) < min_items:
            continue
        sigs = Counter((k.name, tuple(sorted(k.get("class", [])))) for k in kids)
        (name, cls), n = sigs.most_common(1)[0]
        if n < min_items:
            continue
        items = [k for k in kids if (k.name, tuple(sorted(k.get("class", [])))) == (name, cls)]
        dated = [k for k in items if find_dates(k.get_text(" ", strip=True), today) or k.find("time")]
        linked = [k for k in items if k.find("a", href=True)]
        if len(dated) >= max(min_items, int(0.6 * n)):
            out.append((parent, items, len(dated), len(linked)))
    return sorted(out, key=lambda b: (-b[2], -b[3]))


def find_listing_blocks(html: str, today: date | None = None, min_items: int = 3) -> list[dict]:
    """Detect containers whose children repeat and each carry a date + link: the 'event list'.
    Returns candidates with a CSS-ish signature to use as a selector recipe."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer"]):
        t.decompose()
    best = []
    for parent, items, with_date, with_link in _listing_candidates(soup, today, min_items):
        k = items[0]
        cls = k.get("class", [])
        best.append({"parent": _css(parent), "item": k.name + ("." + ".".join(cls) if cls else ""),
                     "items": len(items), "with_date": with_date, "with_link": with_link,
                     "sample": k.get_text(" ", strip=True)[:100]})
    return best[:5]


def extract_recipe_events(html: str, base: str, today: date | None = None, min_items: int = 3) -> list[dict]:
    """Extract events from the page's best repeated listing block, no LLM involved: picks the
    highest-scoring container from _listing_candidates(), then per item takes the first link
    (title + url), the first date/time found in the item's own text, and the item's text as a
    short description. Items with no parsable date are skipped, never guessed."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer"]):
        t.decompose()
    candidates = _listing_candidates(soup, today, min_items)
    if not candidates:
        return []
    _, items, _, _ = candidates[0]
    out = []
    for item in items:
        text = item.get_text(" ", strip=True)
        dates = find_dates(text, today)
        if not dates:
            continue
        d = dates[0]
        times = find_times(text)
        a = item.find("a", href=True)
        title = (a.get_text(" ", strip=True) if a else None) or next(
            (item.find(h).get_text(" ", strip=True) for h in ("h1", "h2", "h3", "h4") if item.find(h)), None)
        if not title:
            continue
        ev = {"title": title[:140], "url": urljoin(base, a["href"]) if a else base,
              "start": d["start"].isoformat(), "description": text[:300]}
        if d.get("end"):
            ev["end"] = d["end"].isoformat()
        t = d.get("time") or (f"{times[0][0]:02d}:{times[0][1]:02d}" if times else None)
        if t:
            ev["time"] = t
        out.append(ev)
    return out


def _css(node) -> str:
    parts = []
    while node is not None and node.name not in (None, "[document]", "html"):
        cls = node.get("class", [])
        parts.append(node.name + (f"#{node['id']}" if node.get("id") else "") + ("." + ".".join(cls[:2]) if cls else ""))
        node = node.parent
        if len(parts) >= 4:
            break
    return " > ".join(reversed(parts))


# ------------------------------------------------------------------ method recommendation
def recommend_method(html: str, base: str, today: date | None = None) -> dict:
    sig = extract_signals(html, base)
    blocks = find_listing_blocks(html, today)
    pag = find_pagination(html, base)
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    n_dates = len(find_dates(text, today))
    if sig["ics"]:
        method, why = "ics", f"ics link: {sig['ics'][0]}"
    elif sig["feeds"] and any("calendar" in f["type"] or "event" in (f["title"] or "").lower() for f in sig["feeds"]):
        method, why = "feed", f"feed: {sig['feeds'][0]['url']}"
    elif any("tribe" in f for f in sig["fingerprints"]) or "wordpress (The Events" in " ".join(sig["fingerprints"]):
        method, why = "wordpress", "The Events Calendar plugin detected"
    elif sig["jsonld_event_types"]:
        method, why = "jsonld", f"{len(sig['jsonld_event_types'])} schema.org Event node(s)"
    elif blocks:
        method, why = "recipe", f"repeated block {blocks[0]['item']} ({blocks[0]['with_date']} dated items)"
    elif n_dates >= 3:
        method, why = "llm", f"{n_dates} dates in text but no repeated structure"
    elif pag and pag[0]["url"] is None:
        method, why = "browser", "load-more without href"
    else:
        method, why = "none-or-browser", "no dates found in static HTML: likely JS-rendered, social-only or not an agenda page"
    return {"method": method, "why": why, "pagination": pag[:3], "n_dates_in_text": n_dates,
            "ticket_platforms": list(sig["ticket_platforms"]), "social": sig["social"], "fingerprints": sig["fingerprints"]}


# ------------------------------------------------------------------ social captions (pasted by hand)
REL_DAYS = {"aujourd'hui": 0, "ce soir": 0, "ce jour": 0, "demain": 1, "apres-demain": 2, "tonight": 0, "today": 0,
            "tomorrow": 1, "vanavond": 0, "vandaag": 0, "morgen": 1, "overmorgen": 2}


def parse_caption(text: str, posted: date | None = None) -> dict:
    """Parse an Instagram/Facebook caption pasted by a human.  Understands emoji-led fields
    (📅 📍 🕖 🎟 💶), relative days ('ce vendredi', 'demain', 'this Friday', 'morgen'), 'link in bio'.
    Returns what was found; unresolved things are left out, never guessed."""
    posted = posted or date.today()
    f = fold(text)
    out: dict = {"dates": [], "handles": sorted(set(re.findall(r"(?<![\w.])@([A-Za-z0-9._]{2,30})", text))),
                 "hashtags": sorted(set(re.findall(r"#(\w{3,40})", text))),
                 "urls": sorted(set(re.findall(r"https?://[^\s)]+", text)))}
    out["dates"] = [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items() if k != "pos"}
                    for d in find_dates(text, posted)]
    for k, n in REL_DAYS.items():
        if re.search(r"(?<![a-z])" + re.escape(fold(k)) + r"(?![a-z])", f):
            out["dates"].append({"start": (posted + timedelta(days=n)).isoformat(), "raw": k, "how": "relative", "confidence": "medium", "time": None})
    for m in re.finditer(rf"(?:ce|cette|this|deze|next|prochain|volgende|dit)\s+({_W})\b|\b({_W})\s+(?:prochain|next|volgende)", f):
        wd = L.WEEKDAYS[m.group(1) or m.group(2)]
        delta = (wd - posted.weekday()) % 7 or 7
        out["dates"].append({"start": (posted + timedelta(days=delta)).isoformat(), "raw": m.group(0), "how": "relative-weekday", "confidence": "low", "time": None})
    times = find_times(text)
    out["times"] = [f"{h:02d}:{m:02d}" for h, m, _ in times]
    place = re.search(r"(?:📍|lieu\s*:|locatie\s*:|where\s*:|@\s)\s*([^\n]{3,100})", text, re.I)
    if place:
        out["place"] = place.group(1).strip()
    out["link_in_bio"] = bool(re.search(r"link in bio|lien en bio|lien dans la bio|link in profiel|link in bio", f))
    out["attributes"] = extract_attributes(text)
    out["event_words"] = has_any(text, L.EVENT_TYPE_WORDS)[:6]
    out["is_event_like"] = bool(out["dates"]) and bool(out["event_words"] or out["times"])
    return out


# ------------------------------------------------------------------ CLI
def _yaml_snippet(name: str, url: str, rec: dict) -> str:
    m = {"ics": "ics", "wordpress": "wordpress", "jsonld": "jsonld", "llm": "llm", "browser": "browser"}.get(rec["method"], "auto")
    return f"- name: {name}\n  url: {url}\n  method: {m}   # discovery: {rec['why']}\n"


def main(argv: list[str]) -> int:
    if "--caption" in argv:
        path = argv[argv.index("--caption") + 1]
        posted = date.fromisoformat(argv[argv.index("--posted") + 1]) if "--posted" in argv else None
        print(json.dumps(parse_caption(open(path, encoding="utf-8").read(), posted), indent=2, ensure_ascii=False, default=str))
        return 0
    if len(argv) < 2:
        print(__doc__); return 2
    from extract import fetch, fetch_rendered   # reuses robots.txt handling of the repo
    url = argv[1]
    html = fetch_rendered(url) if "--render" in argv else fetch(url)
    rec = recommend_method(html, url)
    report = {"url": url, "recommendation": rec,
              "agenda_links": find_agenda_links(html, url)[:8],
              "event_links": find_event_links(html, url)[:15],
              "listing_blocks": find_listing_blocks(html),
              "signals": extract_signals(html, url)}
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    if "--yaml" in argv:
        print("\n" + _yaml_snippet(urlparse(url).netloc, url, rec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
