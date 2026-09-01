"""Turn a web page into a list of events.

Four strategies, tried in order of reliability when method is "auto":
  1. ics       - the site publishes an iCalendar feed
  2. wordpress - the site runs The Events Calendar plugin (REST API)
  3. jsonld    - the page embeds schema.org Event data
  4. llm       - last resort: send the page text to a model and ask for JSON

A fifth strategy, "browser", is opt-in only (not part of "auto"): it renders
the page with a headless browser first, for agendas filled in by JavaScript
after load where the plain HTML has no event data at all. Set it explicitly
per source in sources.yml when probe.py shows ~0 date-like strings in the
page text but the site clearly has an agenda.

Every strategy returns the same dict shape, see normalise_event().
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

UA = "neighbourhood-events/1.0 (personal event aggregator; contact: you@example.org)"
TIMEOUT = 25

_robots_cache: dict[str, RobotFileParser | None] = {}


# ---------------------------------------------------------------- fetching

def robots_allows(url: str) -> bool:
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if root not in _robots_cache:
        rp = RobotFileParser()
        rp.set_url(root + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots_cache[root] = rp
    rp = _robots_cache[root]
    if rp is None:
        return True
    try:
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def fetch(url: str, respect_robots: bool = True) -> str:
    if respect_robots and not robots_allows(url):
        raise PermissionError(f"robots.txt disallows {url}")
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr,nl,en"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"   # accents break without this
    return r.text


def fetch_rendered(url: str, respect_robots: bool = True, wait_ms: int = 3000) -> str:
    """Like fetch(), but executes the page's JavaScript first via a headless
    browser. For agendas where the plain HTML has no event data at all -
    only reach for this when probe.py confirms that's actually the case."""
    if respect_robots and not robots_allows(url):
        raise PermissionError(f"robots.txt disallows {url}")
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page(user_agent=UA)
            try:
                page.goto(url, wait_until="networkidle", timeout=TIMEOUT * 1000)
            except PlaywrightError:
                pass  # sites that poll continuously never reach networkidle; use what loaded
            page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            browser.close()


# ---------------------------------------------------------------- helpers

def normalise_event(raw: dict, source: str, page_url: str, tz: str) -> dict | None:
    """Coerce a loose dict into the canonical event shape. None = unusable."""
    title = clean_text(raw.get("title") or raw.get("name") or "")
    start = to_iso(raw.get("start") or raw.get("startDate") or raw.get("start_date"), tz)
    if not title or not start:
        return None
    end = to_iso(raw.get("end") or raw.get("endDate") or raw.get("end_date"), tz)
    url = raw.get("url") or page_url
    if url and not url.startswith("http"):
        url = urljoin(page_url, url)
    image = image_of(raw.get("image"))
    if image and not image.startswith("http"):
        image = urljoin(page_url, image)
    ev = {
        "title": title,
        "start": start,
        "end": end,
        "all_day": bool(raw.get("all_day")) or len(str(raw.get("start", ""))) == 10,
        "location": clean_text(raw.get("location") or "")[:200],
        "description": clean_text(raw.get("description") or "")[:600],
        "url": url,
        "image": image or None,
        "source": source,
        "llm_recurring": bool(raw.get("recurring")),
    }
    ev["uid"] = hashlib.sha1(
        f"{source}|{ev['title'].lower()}|{ev['start'][:10]}".encode()
    ).hexdigest()[:16]
    return ev


def clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    if isinstance(value, dict):
        value = value.get("name") or value.get("text") or ""
    text = BeautifulSoup(str(value), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def to_iso(value, tz: str) -> str | None:
    """Return an ISO 8601 string with an offset, or None."""
    if not value:
        return None
    if isinstance(value, dict):
        value = value.get("@value") or value.get("startDate") or ""
    text = str(value).strip()
    if not text:
        return None
    # dayfirst only for free-text European dates; never for ISO 8601 strings
    is_iso = bool(re.match(r"^\d{4}-?\d{2}-?\d{2}", text))
    try:
        dt = dateparser.parse(text, dayfirst=not is_iso)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.isoformat()


def image_of(value) -> str:
    """schema.org's `image` (and The Events Calendar's) is a string, an ImageObject
    dict, or a list of either - collapse it down to one URL, or ''."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("@id") or ""
    return str(value or "").strip()


def og_image(html: str, page_url: str) -> str | None:
    """Fallback for sources with no per-event image: the page's own og:image,
    used as a shared illustration so a card still looks like something real."""
    soup = BeautifulSoup(html, "lxml")
    tag = (soup.find("meta", property="og:image")
           or soup.find("meta", attrs={"name": "twitter:image"}))
    content = (tag.get("content") or "").strip() if tag else ""
    if not content:
        return None
    return content if content.startswith("http") else urljoin(page_url, content)


def location_of(node) -> str:
    loc = node.get("location")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        parts = [loc.get("name")]
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts += [addr.get("streetAddress"), addr.get("addressLocality")]
        elif isinstance(addr, str):
            parts.append(addr)
        return ", ".join(clean_text(p) for p in parts if p)
    return clean_text(loc)


# ---------------------------------------------------------------- 1. ICS

def parse_ics(text: str, source: str, page_url: str, tz: str) -> list[dict]:
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold continuation lines
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.split(";")[0].strip().upper()] = value.strip()
        raw = {
            "title": unescape_ics(fields.get("SUMMARY", "")),
            "start": fields.get("DTSTART"),
            "end": fields.get("DTEND"),
            "location": unescape_ics(fields.get("LOCATION", "")),
            "description": unescape_ics(fields.get("DESCRIPTION", "")),
            "url": fields.get("URL") or page_url,
            "all_day": len(fields.get("DTSTART", "")) == 8,
        }
        ev = normalise_event(raw, source, page_url, tz)
        if ev:
            events.append(ev)
    return events


def unescape_ics(value: str) -> str:
    return (value.replace("\\n", " ").replace("\\,", ",")
                 .replace("\\;", ";").replace("\\\\", "\\")).strip()


# ---------------------------------------------------------- 2. WordPress

def parse_wordpress(base_url: str, source: str, tz: str, respect_robots: bool) -> list[dict]:
    """The Events Calendar plugin exposes /wp-json/tribe/events/v1/events."""
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    api = f"{root}/wp-json/tribe/events/v1/events?per_page=50"
    data = json.loads(fetch(api, respect_robots))
    events = []
    for item in data.get("events", []):
        raw = {
            "title": item.get("title"),
            "start": item.get("start_date"),
            "end": item.get("end_date"),
            "url": item.get("url"),
            "description": item.get("excerpt") or item.get("description"),
            "location": (item.get("venue") or {}).get("venue"),
            "all_day": item.get("all_day"),
            "image": item.get("image"),
        }
        ev = normalise_event(raw, source, base_url, tz)
        if ev:
            events.append(ev)
    return events


# ------------------------------------------------------------- 3. JSON-LD

EVENT_TYPES = {"event", "festival", "musicevent", "theaterevent", "screeningevent",
               "exhibitionevent", "socialevent", "educationevent", "foodevent",
               "sportsevent", "businessevent", "childrensevent", "comedyevent",
               "danceevent", "literaryevent", "visualartsevent", "courseinstance"}


def parse_jsonld(html: str, source: str, page_url: str, tz: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        payload = tag.string or tag.get_text()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", payload))
            except json.JSONDecodeError:
                continue
        collect_events(data, found)

    events = []
    for node in found:
        raw = {
            "title": node.get("name"),
            "start": node.get("startDate"),
            "end": node.get("endDate"),
            "url": node.get("url"),
            "description": node.get("description"),
            "location": location_of(node),
            "image": node.get("image"),
        }
        ev = normalise_event(raw, source, page_url, tz)
        if ev:
            events.append(ev)
    return events


def collect_events(node, out: list[dict]) -> None:
    """Walk arbitrary JSON-LD (including @graph and ItemList) for Event nodes."""
    if isinstance(node, list):
        for child in node:
            collect_events(child, out)
        return
    if not isinstance(node, dict):
        return
    types = node.get("@type") or node.get("type") or ""
    types = [types] if isinstance(types, str) else list(types)
    if any(str(t).split("/")[-1].lower() in EVENT_TYPES for t in types):
        out.append(node)
    for key in ("@graph", "itemListElement", "item", "subEvent", "hasPart", "event"):
        if key in node:
            collect_events(node[key], out)


# ----------------------------------------------------------------- 4. LLM

LLM_PROMPT = """You are reading the events page of a local neighbourhood organisation.

Extract EVERY distinct event mentioned in the text below - all of them, no matter
how many there are. Do not filter, sample, shorten the list, or pick only some of
them - if the text lists 30 events, your JSON array must have 30 elements. Never
skip an event just because it's a weekday, a matinee, or during the day: daytime
and weekday events belong in the list exactly as much as evening and weekend ones.
Use every relevant detail that's actually present (exact start and end time,
room/hall name if given, price or "free" wording) rather than leaving a field
blank when the page states it.

(Only in the extreme case where the text is so long you truly cannot fit every
event in your reply - which should be rare - list evening and weekend events
first. This is a last-resort tiebreaker, never a reason to leave out daytime or
weekday events when you have room for them.)

Before including something, check that it's an actual event a visitor could
show up to - a specific dated happening with a real title, not a site
announcement. Skip things like "closed for summer", "new agenda out", "back
in September", newsletter/membership prompts, and opening-hours notices -
these are administrative text that sometimes gets mixed in among real
listings, not events themselves.

Return ONLY a JSON array, no prose, no markdown fences.

Each element: {{"title": str, "start": "YYYY-MM-DDTHH:MM" or "YYYY-MM-DD",
"end": same or null, "location": str, "description": str (max 200 chars),
"url": absolute link to the event's own page if one is given (not just the
listing page) or null, "recurring": bool}}

"recurring" is true for something on a repeating schedule (a weekly class,
"every Tuesday", a standing open mic) or an exhibition/installation running
across a date range rather than a single sitting - false for a normal
one-off dated show, screening, or talk, even if it's part of a season or
festival with many other one-off entries.

Rules:
- Today's date is {today}. Only real, dated events. Skip navigation, past-event
  archives and opening hours.
- If a year is missing, use the SAME year as today unless that date has
  already passed, in which case use the next year. Do not skip further ahead
  than that - a local venue's page almost never lists anything more than a
  few months out.
- The listing page often only states a date, not a time - if no time is
  genuinely stated anywhere near that event, use "YYYY-MM-DD" with no time
  rather than guessing one. Don't default to midnight or invent a time.
- If you find no events, return [].

Page URL: {url}
Page text:
{text}"""


def call_anthropic(body: dict, api_key: str) -> dict:
    """POST to the Messages API. Raises with the response body included, so a
    4xx (bad model name, no credit, etc.) is diagnosable from the log alone."""
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id
    r = requests.post("https://api.anthropic.com/v1/messages",
                       headers=headers, json=body, timeout=120)
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text[:300]}", response=r)
    return r.json()


def parse_llm(html: str, source: str, page_url: str, tz: str, model: str,
              horizon_days: int = 120, keep_past_days: int = 1) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))[:24000]

    body = {
        "model": model,
        # Generous on purpose: asking the model for every event on the page,
        # not a sample, means a busy venue's page can genuinely need this -
        # 4000 was cutting replies short on exactly the sources with the most
        # events to list (a truncated reply fails json.loads() and silently
        # returns nothing for that source).
        "max_tokens": 8000,
        "messages": [{
            "role": "user",
            "content": LLM_PROMPT.format(
                today=datetime.now().date().isoformat(), url=page_url, text=text),
        }],
    }
    data = call_anthropic(body, api_key)
    reply = "".join(b.get("text", "") for b in data.get("content", [])
                    if b.get("type") == "text").strip()
    reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.M).strip()
    try:
        items = json.loads(reply)
    except json.JSONDecodeError:
        return []
    now = datetime.now(ZoneInfo(tz))
    window_start = now - timedelta(days=keep_past_days)
    window_end = now + timedelta(days=horizon_days)
    events = []
    for item in items if isinstance(items, list) else []:
        ev = normalise_event(item, source, page_url, tz)
        if ev:
            events.append(_fix_year_overshoot(ev, window_start, window_end))
    return events


def _fix_year_overshoot(ev: dict, window_start: datetime, window_end: datetime) -> dict:
    """Seen in production: the model sometimes reports a year-less date one
    year further out than it should be (e.g. "2027" for a page showing
    "04.09" with no year, when today is still in 2026) - the event then
    gets silently dropped by the horizon-days window instead of shown. If a
    date falls outside that window as given, but shifting it back exactly
    one year lands it inside, assume that's what happened - a genuine event
    that far out on a small local-venue page would be dropped anyway, so
    there's nothing to lose by trying the correction first."""
    try:
        dt = datetime.fromisoformat(ev["start"])
    except ValueError:
        return ev
    if window_start <= dt <= window_end:
        return ev
    shifted = str(dt.year - 1) + ev["start"][4:]
    try:
        shifted_dt = datetime.fromisoformat(shifted)
    except ValueError:
        return ev
    if window_start <= shifted_dt <= window_end:
        ev["start"] = shifted
        if ev["end"]:
            end_year = int(ev["end"][:4])
            ev["end"] = str(end_year - 1) + ev["end"][4:]
        ev["uid"] = hashlib.sha1(
            f"{ev['source']}|{ev['title'].lower()}|{ev['start'][:10]}".encode()
        ).hexdigest()[:16]
    return ev


# -------------------------------------------------------------- categories

CATEGORIES = [
    {"id": "culture-arts", "emoji": "🎭", "label": "Culture & Arts",
     "hint": "Theatre, dance, exhibitions, performances, art events"},
    {"id": "music", "emoji": "🎵", "label": "Music",
     "hint": "Concerts, live music, DJ sets, open mics, jam sessions"},
    {"id": "film-cinema", "emoji": "🎬", "label": "Film & Cinema",
     "hint": "Film screenings, documentaries, cinema clubs"},
    {"id": "workshops-creative", "emoji": "🎨", "label": "Workshops & Creative",
     "hint": "Arts & crafts, cooking, ceramics, creative workshops, making"},
    {"id": "talks-discussions", "emoji": "🗣️", "label": "Talks & Discussions",
     "hint": "Debates, panels, lectures, discussions, public conversations"},
    {"id": "sport-wellbeing", "emoji": "🧘", "label": "Sport & Wellbeing",
     "hint": "Yoga, fitness, running, climbing, meditation, recreational activities"},
    {"id": "family-children", "emoji": "👨‍👩‍👧", "label": "Family & Children",
     "hint": "Children's activities, family events, storytelling, kids' entertainment"},
    {"id": "food-drink", "emoji": "🍴", "label": "Food & Drink",
     "hint": "Tastings, communal meals, cooking events, food-related gatherings"},
    {"id": "markets-fairs", "emoji": "🛍️", "label": "Markets & Fairs",
     "hint": "Flea markets, artisan markets, brocantes, local markets"},
    {"id": "community-social", "emoji": "🏘️", "label": "Community & Social",
     "hint": "Neighbourhood gatherings, social events, community meals, meetups"},
    {"id": "environment", "emoji": "🌱", "label": "Environment",
     "hint": "Repair cafés, urban gardening, clean-ups, sustainability events"},
    {"id": "activism-justice", "emoji": "✊", "label": "Activism & Social Justice",
     "hint": "Demonstrations, protests, activist meetings, solidarity events, campaigns, "
             "political/social justice organising"},
    {"id": "festivals-celebrations", "emoji": "🎉", "label": "Festivals & Celebrations",
     "hint": "Street parties, neighbourhood fêtes, seasonal celebrations, festivals"},
    {"id": "professional-networking", "emoji": "💼", "label": "Professional & Networking",
     "hint": "Networking events, entrepreneur meetups, professional gatherings"},
    {"id": "civic-politics", "emoji": "🏛️", "label": "Civic & Local Politics",
     "hint": "Municipal meetings, neighbourhood consultations, local political events"},
    {"id": "other", "emoji": "•", "label": "Other",
     "hint": "Anything that doesn't fit the above"},
]
CATEGORY_IDS = {c["id"] for c in CATEGORIES}

CATEGORY_PROMPT = """Classify each neighbourhood event below into exactly one category id
from this list:

{cat_list}

Return ONLY a JSON object mapping each event's "uid" to a category id, no prose, no
markdown fences. Use "other" if nothing fits well.

Events:
{events_json}"""


def classify_categories(events: list[dict], model: str, cache: dict[str, str]) -> None:
    """Assign a category id to each event, in place. Reuses `cache` (uid -> category id)
    for events already classified on a previous run, so a run only pays for new events."""
    todo = [e for e in events if e["uid"] not in cache]
    for e in events:
        if e["uid"] in cache:
            e["category"] = cache[e["uid"]]

    if not todo:
        return
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        for e in todo:
            e["category"] = "other"
        return

    cat_list = "\n".join(f'- {c["id"]}: {c["label"]} — {c["hint"]}' for c in CATEGORIES)
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        items = [{"uid": e["uid"], "title": e["title"], "description": e["description"][:200]}
                  for e in chunk]
        body = {
            "model": model,
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": CATEGORY_PROMPT.format(
                    cat_list=cat_list, events_json=json.dumps(items, ensure_ascii=False)),
            }],
        }
        mapping: dict = {}
        try:
            data = call_anthropic(body, api_key)
            reply = "".join(b.get("text", "") for b in data.get("content", [])
                            if b.get("type") == "text").strip()
            reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.M).strip()
            mapping = json.loads(reply)
        except Exception:
            mapping = {}
        for e in chunk:
            cat = mapping.get(e["uid"])
            e["category"] = cat if cat in CATEGORY_IDS else "other"


# -------------------------------------------------------------------- tags

# id -> label -> hint. "free"/"evening"/"late-night"/"recurring" are (also, or
# entirely) derived deterministically below - see deterministic_tags() - so the
# LLM is only ever asked to choose among LLM_TAG_IDS, the genuinely subjective ones.
TAGS = [
    {"id": "free", "label": "Free"},
    {"id": "kids", "label": "Kids"},
    {"id": "family", "label": "Family"},
    {"id": "late-night", "label": "Late Night"},
    {"id": "evening", "label": "Evening"},
    {"id": "outdoor", "label": "Outdoor"},
    {"id": "drop-in", "label": "Drop-in"},
    {"id": "registration-required", "label": "Registration Required"},
    {"id": "live", "label": "Live"},
    {"id": "dance", "label": "Dance"},
    {"id": "food-drink", "label": "Food & Drink"},
    {"id": "activism", "label": "Activism"},
    {"id": "sustainability", "label": "Sustainability"},
    {"id": "accessible", "label": "Accessible"},
    {"id": "recurring", "label": "Recurring"},
    {"id": "adults", "label": "18+"},
]
TAG_IDS = {t["id"] for t in TAGS}
TAG_HINTS = {
    "kids": "aimed at or suitable for children on their own",
    "family": "family-friendly, suitable for all ages together",
    "outdoor": "takes place outside - a park, street, square, garden",
    "drop-in": "no booking needed, just show up",
    "registration-required": "needs a ticket, booking, or signing up in advance",
    "live": "a live performance - music, theatre, spoken word, comedy",
    "dance": "dancing, a dance performance, or a dance floor/club night",
    "food-drink": "food, drinks, tastings, a communal meal",
    "activism": "a protest, campaign, organising meeting, solidarity action",
    "sustainability": "environment, repair, upcycling, ecology, gardening",
    "accessible": "explicitly wheelchair-accessible or accessibility-focused",
    "recurring": "happens on a repeating schedule (weekly, monthly) rather than once",
    "adults": "explicitly 18+ / adults-only - an age restriction is actually stated, or the "
              "content is explicitly sexual/erotic/adult in nature. Do not guess from a late "
              "time slot, alcohol being served, or mature themes alone - only tag this when "
              "the text itself says so (e.g. \"18+\", \"adults only\", \"not suitable for minors\").",
}
LLM_TAG_IDS = set(TAG_HINTS)  # the deterministic ones (free/evening/late-night) are excluded

FREE_RE = re.compile(
    r"\b(free|no charge|free admission|free entry|complimentary"
    r"|gratuit|gratis|entr[ée]e libre|toegang vrij)\b", re.I)

TAG_PROMPT = """Tag each neighbourhood event below with zero or more tags from this list -
most events will only get one or two, many will get none. Only apply a tag when the
text actually supports it; don't guess.

{tag_list}

Return ONLY a JSON object mapping each event's "uid" to an array of tag ids (possibly
empty), no prose, no markdown fences.

Events:
{events_json}"""


def deterministic_tags(e: dict) -> set[str]:
    """Tags computed from the event's own data rather than guessed by a model -
    free/evening/late-night from the clock, recurring from either a multi-day
    span (an exhibition "10 Sep - 20 Oct" rather than a single date) or the
    llm rung's own recurring/false-vs-true call at extraction time, when it
    made one (see LLM_PROMPT's "recurring" field - that pass sees the full
    page context, e.g. "every Tuesday" phrasing, that a later uid-only tag
    pass never gets to look at)."""
    tags: set[str] = set()
    if FREE_RE.search(f"{e.get('title', '')} {e.get('description', '')}"):
        tags.add("free")
    if not e.get("all_day") and e.get("start"):
        try:
            hour = datetime.fromisoformat(e["start"]).hour
        except ValueError:
            hour = None
        if hour is not None:
            if 17 <= hour < 22:
                tags.add("evening")
            if hour >= 22 or hour < 5:
                tags.add("late-night")
    if e.get("start") and e.get("end"):
        try:
            span = datetime.fromisoformat(e["end"]) - datetime.fromisoformat(e["start"])
            if span.days >= 3:
                tags.add("recurring")
        except ValueError:
            pass
    if e.get("llm_recurring"):
        tags.add("recurring")
    return tags


def classify_tags(events: list[dict], model: str, cache: dict[str, list[str]]) -> None:
    """Assign tags to each event, in place. `cache` (uid -> tag id list) is the
    previous run's full tag list per event; deterministic tags are always
    recomputed fresh (cheap, and harmless if the logic above ever changes), the
    LLM-chosen ones are only asked for once per event."""
    todo = []
    for e in events:
        det = deterministic_tags(e)
        e.pop("llm_recurring", None)  # internal-only, folded into det already
        if e["uid"] in cache:
            e["tags"] = sorted(det | set(cache[e["uid"]]))
        else:
            e["_pending_det_tags"] = det
            todo.append(e)

    if not todo:
        return
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        for e in todo:
            e["tags"] = sorted(e.pop("_pending_det_tags"))
        return

    tag_list = "\n".join(f'- {tid}: {TAG_HINTS[tid]}' for tid in LLM_TAG_IDS)
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        items = [{"uid": e["uid"], "title": e["title"], "description": e["description"][:200]}
                  for e in chunk]
        body = {
            "model": model,
            "max_tokens": 3000,
            "messages": [{
                "role": "user",
                "content": TAG_PROMPT.format(
                    tag_list=tag_list, events_json=json.dumps(items, ensure_ascii=False)),
            }],
        }
        mapping: dict = {}
        try:
            data = call_anthropic(body, api_key)
            reply = "".join(b.get("text", "") for b in data.get("content", [])
                            if b.get("type") == "text").strip()
            reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.M).strip()
            mapping = json.loads(reply)
        except Exception:
            mapping = {}
        for e in chunk:
            det = e.pop("_pending_det_tags")
            picked = mapping.get(e["uid"])
            valid = {t for t in picked if t in LLM_TAG_IDS} if isinstance(picked, list) else set()
            e["tags"] = sorted(det | valid)


# --------------------------------------------------------------- translation

TRANSLATE_PROMPT = """Translate each event's title, description and location into natural,
idiomatic English - not a literal word-for-word translation. Leave a field unchanged if
it's already in English, or if it's a proper noun that shouldn't be translated (a venue
name, a person's name, a street name). If a field is an empty string, return it unchanged.

Return ONLY a JSON object mapping each event's "uid" to
{{"title": str, "description": str, "location": str}}, no prose, no markdown fences.

Events:
{events_json}"""


def translate_events(events: list[dict], model: str, cache: dict[str, dict]) -> None:
    """Translate title/description/location to English, in place. `cache` (uid ->
    {{title, description, location}}) holds the previous run's already-translated
    text - scrape.py only populates it from events that were themselves marked
    `translated`, so this can't mistake original-language text left over from a
    run before translation existed for something already done. A run only pays
    to translate events it hasn't seen before."""
    todo = []
    for e in events:
        cached = cache.get(e["uid"])
        if cached:
            e["title"] = cached.get("title") or e["title"]
            e["description"] = cached.get("description", e["description"])
            e["location"] = cached.get("location", e["location"])
            e["translated"] = True
        else:
            todo.append(e)

    if not todo:
        return
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return  # no key: leave the original-language text rather than fail the run

    for i in range(0, len(todo), 25):
        chunk = todo[i:i + 25]
        items = [{"uid": e["uid"], "title": e["title"], "description": e["description"],
                   "location": e["location"]} for e in chunk]
        body = {
            "model": model,
            "max_tokens": 8000,
            "messages": [{
                "role": "user",
                "content": TRANSLATE_PROMPT.format(
                    events_json=json.dumps(items, ensure_ascii=False)),
            }],
        }
        try:
            data = call_anthropic(body, api_key)
            reply = "".join(b.get("text", "") for b in data.get("content", [])
                            if b.get("type") == "text").strip()
            reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.M).strip()
            mapping = json.loads(reply)
        except Exception:
            mapping = {}
        for e in chunk:
            t = mapping.get(e["uid"])
            if not isinstance(t, dict):
                continue  # leave e["translated"] unset so a failed batch retries next run
            if t.get("title"):
                e["title"] = clean_text(t["title"])
            if "description" in t:
                e["description"] = clean_text(t.get("description") or "")
            if t.get("location"):
                e["location"] = clean_text(t["location"])
            e["translated"] = True


# --------------------------------------------------------- time enrichment

TIME_IN_TEXT_RE = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b")


def find_time_in_text(text: str) -> tuple[int, int] | None:
    """First plausible HH:MM (or HHhMM) in text."""
    m = TIME_IN_TEXT_RE.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def enrich_event_time(ev: dict, tz: str, respect_robots: bool) -> str | None:
    """Confirmed via a live diagnostic (01/09/2026) that several listing
    pages simply never state a time next to the date at all - not a
    parsing bug, the information isn't on that page. But the event's own
    detail page usually has it, either as schema.org Event data or as
    plain text ("Doors 20:00" etc.). Returns a new ISO start with a real
    time, or None if the detail page has nothing better either."""
    if not ev.get("url") or not ev["url"].startswith("http"):
        return None
    try:
        html = fetch(ev["url"], respect_robots)
    except Exception:
        return None
    for node in parse_jsonld(html, ev["source"], ev["url"], tz):
        if node["start"][:10] == ev["start"][:10] and not node["all_day"]:
            return node["start"]
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    found = find_time_in_text(soup.get_text(" "))
    if not found:
        return None
    hour, minute = found
    try:
        base = datetime.fromisoformat(ev["start"])
    except ValueError:
        return None
    return base.replace(hour=hour, minute=minute).isoformat()


def enrich_missing_times(events: list[dict], tz: str, respect_robots: bool,
                          delay: float, listing_urls: set[str],
                          cache: dict[str, dict], max_new: int = 60) -> None:
    """For all_day events, try to recover a real time from their own detail
    page - skipped when an event's "url" is just the venue's listing page
    (nothing new to fetch there), and capped per run since this is one
    extra HTTP request per event; whatever's left over just tries again
    next run. `cache` (uid -> {{start, all_day}}) holds every event this has
    ever been tried for, success or not, so a page confirmed to have no
    time isn't refetched forever."""
    fetched = 0
    for e in events:
        if not e.get("all_day"):
            continue
        cached = cache.get(e["uid"])
        if cached:
            e["start"], e["all_day"] = cached["start"], cached["all_day"]
            e["time_checked"] = True
            continue
        if fetched >= max_new or e.get("url") in listing_urls:
            continue
        fetched += 1
        new_start = enrich_event_time(e, tz, respect_robots)
        if new_start:
            e["start"] = new_start
            e["all_day"] = False
        e["time_checked"] = True
        time.sleep(delay)


# ------------------------------------------------------------ orchestration

def fill_fallback_images(events: list[dict], page_html: str | None, url: str, robots: bool) -> None:
    """Sources without a per-event image (most llm-rung ones, since the image is
    stripped along with every other tag before the text reaches the model) still
    get *a* real photo: the page's own og:image, shared across that source's cards
    rather than left as a plain colour block. Only fetches the page if we don't
    already have it in hand and it's actually needed."""
    if all(e.get("image") for e in events):
        return
    try:
        html = page_html if page_html is not None else fetch(url, robots)
        fallback = og_image(html, url)
    except Exception:
        fallback = None
    if not fallback:
        return
    for e in events:
        if not e.get("image"):
            e["image"] = fallback


def extract(source_cfg: dict, defaults: dict) -> tuple[list[dict], str, str]:
    """Returns (events, method_used, note)."""
    name = source_cfg["name"]
    url = source_cfg["url"]
    tz = source_cfg.get("tz") or defaults.get("timezone", "Europe/Brussels")
    method = source_cfg.get("method", "auto")
    robots = source_cfg.get("respect_robots", defaults.get("respect_robots", True))
    model = defaults.get("llm_model", "claude-haiku-4-5")
    horizon_days = int(defaults.get("horizon_days", 120))
    keep_past_days = int(defaults.get("keep_past_days", 1))

    order = [method] if method != "auto" else ["ics", "wordpress", "jsonld", "llm"]
    last_error = ""

    for step in order:
        page_html = None  # kept when we already have it, so the image fallback is free
        try:
            if step == "ics":
                if not (url.endswith(".ics") or method == "ics"):
                    continue
                page_html = fetch(url, robots)
                events = parse_ics(page_html, name, url, tz)
            elif step == "wordpress":
                events = parse_wordpress(url, name, tz, robots)
            elif step == "jsonld":
                page_html = fetch(url, robots)
                events = parse_jsonld(page_html, name, url, tz)
            elif step == "llm":
                page_html = fetch(url, robots)
                events = parse_llm(page_html, name, url, tz, model,
                                    horizon_days, keep_past_days)
            elif step == "browser":
                page_html = fetch_rendered(url, robots)
                events = parse_jsonld(page_html, name, url, tz)
                if not events:
                    events = parse_llm(page_html, name, url, tz, model,
                                        horizon_days, keep_past_days)
            else:
                continue
            if events:
                fill_fallback_images(events, page_html, url, robots)
                return events, step, ""
            last_error = last_error or f"{step}: nothing found"
        except Exception as exc:  # keep going; one bad source must not stop the run
            last_error = f"{step}: {type(exc).__name__}: {exc}"[:200]
            time.sleep(0.5)

    return [], "none", last_error
