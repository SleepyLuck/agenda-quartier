"""Turn a web page into a list of events.

Four strategies, tried in order of reliability:
  1. ics       - the site publishes an iCalendar feed
  2. wordpress - the site runs The Events Calendar plugin (REST API)
  3. jsonld    - the page embeds schema.org Event data
  4. llm       - last resort: send the page text to a model and ask for JSON

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
    ev = {
        "title": title,
        "start": start,
        "end": end,
        "all_day": bool(raw.get("all_day")) or len(str(raw.get("start", ""))) == 10,
        "location": clean_text(raw.get("location") or "")[:200],
        "description": clean_text(raw.get("description") or "")[:600],
        "url": url,
        "source": source,
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

LLM_PROMPT = """You are reading the events page of a local organisation.
Return ONLY a JSON array, no prose, no markdown fences.

Each element: {"title": str, "start": "YYYY-MM-DDTHH:MM" or "YYYY-MM-DD",
"end": same or null, "location": str, "description": str (max 200 chars),
"url": absolute link to the event page or null}

Rules:
- Only real, dated events. Skip navigation, past-event archives and opening hours.
- If a year is missing, assume the next occurrence after {today}.
- If you find no events, return [].

Page URL: {url}
Page text:
{text}"""


def parse_llm(html: str, source: str, page_url: str, tz: str, model: str) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))[:18000]

    body = {
        "model": model,
        "max_tokens": 4000,
        "messages": [{
            "role": "user",
            "content": LLM_PROMPT.format(
                today=datetime.now().date().isoformat(), url=page_url, text=text),
        }],
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=120)
    r.raise_for_status()
    reply = "".join(b.get("text", "") for b in r.json().get("content", [])
                    if b.get("type") == "text").strip()
    reply = re.sub(r"^```(?:json)?|```$", "", reply, flags=re.M).strip()
    try:
        items = json.loads(reply)
    except json.JSONDecodeError:
        return []
    events = []
    for item in items if isinstance(items, list) else []:
        ev = normalise_event(item, source, page_url, tz)
        if ev:
            events.append(ev)
    return events


# ------------------------------------------------------------ orchestration

def extract(source_cfg: dict, defaults: dict) -> tuple[list[dict], str, str]:
    """Returns (events, method_used, note)."""
    name = source_cfg["name"]
    url = source_cfg["url"]
    tz = source_cfg.get("tz") or defaults.get("timezone", "Europe/Brussels")
    method = source_cfg.get("method", "auto")
    robots = source_cfg.get("respect_robots", defaults.get("respect_robots", True))
    model = defaults.get("llm_model", "claude-haiku-4-5-20251001")

    order = [method] if method != "auto" else ["ics", "wordpress", "jsonld", "llm"]
    last_error = ""

    for step in order:
        try:
            if step == "ics":
                if not (url.endswith(".ics") or method == "ics"):
                    continue
                events = parse_ics(fetch(url, robots), name, url, tz)
            elif step == "wordpress":
                events = parse_wordpress(url, name, tz, robots)
            elif step == "jsonld":
                events = parse_jsonld(fetch(url, robots), name, url, tz)
            elif step == "llm":
                events = parse_llm(fetch(url, robots), name, url, tz, model)
            else:
                continue
            if events:
                return events, step, ""
            last_error = last_error or f"{step}: nothing found"
        except Exception as exc:  # keep going; one bad source must not stop the run
            last_error = f"{step}: {type(exc).__name__}: {exc}"[:200]
            time.sleep(0.5)

    return [], "none", last_error
