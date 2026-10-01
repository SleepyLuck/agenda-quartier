"""Read sources.yml, collect events, write docs/events.json and docs/events.ics.

    python scrape.py            # normal run
    python scrape.py --dry-run  # print a report, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dateutil import parser as dateparser

from extract import (CATEGORIES, CATEGORY_IDS, TAG_IDS, TAGS, TIME_CACHE_VERSION,
                      classify_categories, classify_tags, enrich_missing_times,
                      extract, translate_events)

ROOT = Path(__file__).parent
OUT = ROOT / "docs"

# Riso-ink palette, assigned in order to sources without an explicit colour.
PALETTE = ["#E8336D", "#1B6FE0", "#00937A", "#E07A00",
           "#7B49D6", "#C0392B", "#0F8CA8", "#8A7500"]


def load_config() -> tuple[dict, list[dict]]:
    cfg = yaml.safe_load((ROOT / "sources.yml").read_text(encoding="utf-8"))
    return cfg.get("defaults", {}) or {}, cfg.get("sources", []) or []


def _manual_date(value, tz: str) -> tuple[str | None, bool]:
    """Returns (iso_string, is_date_only). manual_events.yml is hand-edited
    YAML - PyYAML quietly turns an unquoted bare date (2026-10-19) into a
    real date object while an unquoted date+time (2026-10-16T11:00) stays a
    plain string, so this accepts either. Always attaches a real Brussels
    UTC offset, matching extract.py's to_iso() for scraped events - a bare
    "2026-12-11T15:30" with no offset at all isn't wrong exactly, but
    new Date() in the browser interprets a timezone-less ISO string as the
    VIEWER's own local time, not Brussels time, so the same manual event
    silently displayed a different wall-clock time depending on where the
    page happened to be loaded (caught via a headless-browser screenshot:
    15:30 in the data rendered as 16:30)."""
    if value is None:
        return None, False
    if isinstance(value, datetime):
        dt, date_only = value, False
    elif isinstance(value, date):
        dt, date_only = datetime(value.year, value.month, value.day), True
    else:
        text = str(value).strip()
        if not text:
            return None, False
        date_only = "T" not in text and len(text) <= 10
        try:
            dt = dateparser.parse(text)
        except (ValueError, TypeError, OverflowError):
            return None, False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.isoformat(), date_only


def _fold_title(title: str) -> str:
    """lower-case + strip accents/punctuation, so a scraped and a hand-typed
    version of the same title ("Kabylifornie" vs "Kabylifornie ") compare
    equal for the dedupe rule below."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", title or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def load_manual_events(tz: str) -> tuple[list[dict], dict[str, str], dict[str, list[str]], dict[str, dict]]:
    """Events gathered by hand - printed flyers, photographed programmes,
    festival pages with no scrapable agenda, sites this sandbox can't reach
    - kept in manual_events.yml rather than any sources.yml entry, since
    there's nothing here to automate. Without this, adding one would be a
    one-run fluke: the main loop below only rebuilds `events` from
    sources.yml's configured sources (plus carry-forward for ones that
    already exist there), so anything else would vanish the very next run.
    This re-reads and re-merges the whole file every run instead, aged out
    by the same date window as scraped events - add a new entry to the
    file, don't hand-edit docs/events.json.

    Also returns category/tag/translation "cache seed" dicts: a human
    already chose the category and tags when curating the file (at least as
    trustworthy as a model's answer) and wrote the description in English
    already, so classify_categories()/classify_tags()/translate_events()
    should all treat these as a cache hit (setting category_llm/
    tags_llm_done/translated exactly as a real model answer would) rather
    than spending an API call re-deciding or re-translating a hand-picked
    value."""
    path = ROOT / "manual_events.yml"
    if not path.exists():
        return [], {}, {}, {}
    raw_list = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    events, cat_seed, tag_seed, translation_seed = [], {}, {}, {}
    for raw in raw_list:
        start, start_date_only = _manual_date(raw.get("start"), tz)
        if not start or not raw.get("title") or not raw.get("source"):
            continue
        end, _ = _manual_date(raw.get("end"), tz)
        source = raw["source"]
        title = raw["title"]
        location = str(raw.get("location") or "")[:200]
        description = str(raw.get("description") or "")[:600]
        # Full `start`, not just its date: scraped events truncate to the
        # date so a model re-wording the same time slightly differently
        # across runs doesn't orphan that event's cache, but this file has
        # no such churn, and truncating caused a real collision here - two
        # same-titled showings on the same day at different times (CRUSH
        # festival's "Kabylifornie", 15:30 and 19:30 on 2026-12-11) hashed
        # to the same uid and silently dropped one.
        uid = hashlib.sha1(f"{source}|{title.lower()}|{start}".encode()).hexdigest()[:16]
        events.append({
            "title": title,
            "start": start,
            "end": end,
            "all_day": bool(raw.get("all_day")) or start_date_only,
            "location": location,
            "description": description,
            "url": raw.get("url"),
            "image": None,
            "source": source,
            "tickets": raw.get("tickets"),
            "social": raw.get("social") or {},
            "uid": uid,
            "manual": True,
            "_fold_title": _fold_title(title),
        })
        if raw.get("category") in CATEGORY_IDS:
            cat_seed[uid] = raw["category"]
        tag_seed[uid] = [t for t in (raw.get("tags") or []) if t in TAG_IDS]
        translation_seed[uid] = {"title": title, "description": description, "location": location}
    return events, cat_seed, tag_seed, translation_seed


def manual_in_window(ev: dict, tz: str, past: int, horizon: int) -> bool:
    """Scraped events' within_window() only looks at `start`, which is fine
    there (they're never more than a day or two old by the time a run sees
    them) but wrong for a multi-day manual entry that's already under way -
    a run partway through "Copenhagen" (15 Oct - 6 Nov) would compare its
    15 Oct start against today and drop a show that's still running. Keep
    it as long as it HASN'T ENDED yet (or started, if there's no end), and
    still cap how far into the future a start can be."""
    now = datetime.now(ZoneInfo(tz))
    try:
        start_dt = dateparser.parse(ev["start"])
    except (ValueError, TypeError):
        return False
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ZoneInfo(tz))
    end_dt = start_dt
    if ev.get("end"):
        try:
            parsed_end = dateparser.parse(ev["end"])
            if parsed_end.tzinfo is None:
                parsed_end = parsed_end.replace(tzinfo=ZoneInfo(tz))
            end_dt = parsed_end
        except (ValueError, TypeError):
            pass
    return end_dt >= (now - timedelta(days=past)) and start_dt <= (now + timedelta(days=horizon))


def _previous_payload() -> dict:
    path = OUT / "events.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _previous_events() -> list[dict]:
    return _previous_payload().get("events", [])


def load_category_cache() -> dict[str, str]:
    """uid -> category id, from the previously published events.json, so a run only
    asks the LLM to classify events it hasn't seen before. Only trusts entries the
    model actually classified (category_llm) - a failed or partial batch falls back
    to "other" for display without that marker (see classify_categories), so it's
    correctly treated as not-yet-classified here instead of caching the fallback
    forever (confirmed in production: a billing outage permanently mis-filed events
    into "Other" before this marker existed)."""
    return {e["uid"]: e["category"] for e in _previous_events() if e.get("category_llm")}


def load_tag_cache() -> dict[str, list[str]]:
    """uid -> tag id list, from the previously published events.json. Only trusts
    entries the model actually reviewed (tags_llm_done) - a failed or partial batch
    falls back to deterministic-only tags for display without that marker (see
    classify_tags), so it's correctly retried here instead of caching bare
    free/evening-style tags as if the LLM-only ones had been considered and found
    not to apply."""
    return {e["uid"]: e["tags"] for e in _previous_events() if e.get("tags_llm_done")}


def load_translation_cache() -> dict[str, dict]:
    """uid -> already-translated {title, description, location}, from the
    previously published events.json, so a run only pays to translate events
    it hasn't seen before. Only events actually marked `translated` count -
    otherwise, the very first run after adding translation would mistake
    every event's original-language text for already-done work and never
    translate it."""
    return {e["uid"]: {"title": e.get("title", ""), "description": e.get("description", ""),
                        "location": e.get("location", "")}
            for e in _previous_events() if e.get("translated")}


def load_time_cache() -> dict[str, dict]:
    """uid -> {start, all_day}, for events whose detail page has already been
    checked for a time (successfully or not) - see enrich_missing_times().
    Only trusts entries stamped with the current TIME_CACHE_VERSION, so a fix
    to the time-extraction logic invalidates stale cached results (a bare
    `time_checked: true` from before versioning existed doesn't match either,
    so it's treated as unchecked too) instead of replaying old garbage forever."""
    return {e["uid"]: {"start": e["start"], "all_day": e["all_day"]}
            for e in _previous_events() if e.get("time_checked") == TIME_CACHE_VERSION}


def within_window(iso: str, tz: str, past_days: int, horizon_days: int) -> bool:
    now = datetime.now(ZoneInfo(tz))
    try:
        dt = dateparser.parse(iso)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return (now - timedelta(days=past_days)) <= dt <= (now + timedelta(days=horizon_days))


def ics_stamp(iso: str, all_day: bool, tz: str) -> str:
    dt = dateparser.parse(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    if all_day:
        return f";VALUE=DATE:{dt.strftime('%Y%m%d')}"
    return f":{dt.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}"


def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    """RFC 5545: no content line longer than 75 octets."""
    out, current = [], line
    while len(current.encode()) > 73:
        cut = 73
        while len(current[:cut].encode()) > 73:
            cut -= 1
        out.append(current[:cut])
        current = " " + current[cut:]
    out.append(current)
    return "\r\n".join(out)


def build_ics(events: list[dict], tz: str, alarm_minutes: int = 120) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//neighbourhood-events//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Neighbourhood events",
             f"X-WR-TIMEZONE:{tz}"]
    now = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    tag_by_id = {t["id"]: t["label"] for t in TAGS}
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}@neighbourhood-events",
            f"DTSTAMP:{now}",
            "DTSTART" + ics_stamp(ev["start"], ev["all_day"], tz),
        ]
        if ev.get("end"):
            lines.append("DTEND" + ics_stamp(ev["end"], ev["all_day"], tz))
        lines.append(fold("SUMMARY:" + ics_escape(ev["title"])))
        if ev.get("location"):
            lines.append(fold("LOCATION:" + ics_escape(ev["location"])))
        body = ev.get("description", "")
        if ev.get("url"):
            lines.append(fold("URL:" + ev["url"]))
            if body:
                body = body + "\n" + ev["url"]
        if body:
            lines.append(fold("DESCRIPTION:" + ics_escape(body)))
        cats = [ev["source"]]
        cat_meta = next((c for c in CATEGORIES if c["id"] == ev.get("category")), None)
        if cat_meta:
            cats.append(cat_meta["label"])
        cats += [tag_by_id[t] for t in ev.get("tags", []) if t in tag_by_id]
        lines.append(fold("CATEGORIES:" + ics_escape(",".join(cats))))
        if not ev["all_day"]:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"TRIGGER:-PT{alarm_minutes}M",
                      fold("DESCRIPTION:" + ics_escape(ev["title"])), "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    defaults, sources = load_config()
    tz = defaults.get("timezone", "Europe/Brussels")
    delay = float(defaults.get("request_delay_seconds", 1.5))
    horizon = int(defaults.get("horizon_days", 120))
    past = int(defaults.get("keep_past_days", 1))

    # Carry-forward: a source that fails outright this run (site down, robots
    # changed, billing) shouldn't make its events vanish from the page - keep
    # showing whatever it last actually delivered, marked stale, until it
    # recovers. Indexed by source name against the previously PUBLISHED
    # payload, not this run's in-progress one.
    prev_payload = _previous_payload()
    prev_events_by_source: dict[str, list[dict]] = {}
    for e in prev_payload.get("events", []):
        # Manual events are never dropped and need no carry-forward of their
        # own (load_manual_events() re-adds them every run regardless of
        # scraper health) - pooling them in here by source name would let a
        # scraped source that happens to share a manual source's display name
        # (e.g. both called "FTI Brussel") "carry forward" the manual
        # events as if they were its own stale results, which then makes the
        # real manual batch look like a duplicate of an already-scraped event
        # and get silently dropped by the dedup-against-scraped rule.
        if e.get("manual"):
            continue
        prev_events_by_source.setdefault(e.get("source", ""), []).append(e)
    prev_source_meta_by_name = {s["name"]: s for s in prev_payload.get("sources", [])
                                 if s.get("method") != "manual"}
    today_iso = datetime.now(ZoneInfo(tz)).date().isoformat()

    all_events: dict[str, dict] = {}
    report, source_meta = [], []
    # Set on the first billing/auth failure from the API itself - every other
    # llm/browser source this run is doomed the same way, so stop paying for
    # (and logging) 15+ more identical failures. See extract()'s skip_llm.
    billing_broken = False

    for i, src in enumerate(sources):
        colour = src.get("colour") or PALETTE[i % len(PALETTE)]
        if not src.get("enabled", True):
            print(f"{src['name']:<38} skipped (enabled: false)")
            continue
        events, method, note, error_class = extract(src, defaults, skip_llm=billing_broken)
        if error_class == "billing":
            billing_broken = True
        kept = 0
        for ev in events:
            if not within_window(ev["start"], tz, past, horizon):
                continue
            ev["colour"] = colour
            all_events.setdefault(ev["uid"], ev)
            kept += 1

        carried = 0
        stale = False
        last_ok = today_iso
        if kept == 0:
            prev_meta = prev_source_meta_by_name.get(src["name"], {})
            prev_last_ok = prev_meta.get("last_ok")
            if prev_events_by_source.get(src["name"]) or prev_last_ok:
                stale = True
                last_ok = prev_last_ok or (prev_payload.get("generated", today_iso) or today_iso)[:10]
                for ev in prev_events_by_source.get(src["name"], []):
                    if not within_window(ev["start"], tz, past, horizon):
                        continue
                    ev = dict(ev)
                    ev["colour"] = colour
                    ev["stale"] = True
                    all_events.setdefault(ev["uid"], ev)
                    carried += 1
            else:
                stale = False
                last_ok = None

        source_meta.append({"name": src["name"], "url": src["url"], "colour": colour,
                            "count": kept + carried, "method": method,
                            "stale": stale, "last_ok": last_ok})
        report.append({"source": src["name"], "method": method, "found": len(events),
                       "kept": kept, "carried": carried, "stale": stale,
                       "error_class": error_class, "note": note})
        line = f"{src['name']:<38} {method:<10} found={len(events):<4} kept={kept}"
        if carried:
            line += f"  carried={carried} (stale since {last_ok})"
        if error_class:
            line += f"  [{error_class}] {note}"
        elif note:
            line += f"  [{note}]"
        print(line)
        time.sleep(delay)

    # Same (normalised title, date) already covered by a scraped event this
    # run - a manual entry describing the same real-world event as a source
    # that's actually online loses to the live one, since that one will
    # keep itself current without anyone hand-editing a YAML file.
    scraped_title_dates = {(_fold_title(ev["title"]), ev["start"][:10]) for ev in all_events.values()}

    manual_events, manual_cat_seed, manual_tag_seed, manual_translation_seed = load_manual_events(tz)
    manual_source_order: list[str] = []
    for ev in manual_events:
        if ev["source"] not in manual_source_order:
            manual_source_order.append(ev["source"])
    # Offset past the configured sources' own palette range so a manual
    # source's colour doesn't just happen to repeat a scraped one, and keep
    # it stable across runs (based on first-seen order in the file, not
    # Python's hash() - which is randomised per process and would make the
    # colour flicker between runs).
    manual_colours = {name: PALETTE[(len(sources) + i) % len(PALETTE)]
                       for i, name in enumerate(manual_source_order)}
    manual_kept_by_source = {name: 0 for name in manual_source_order}
    for ev in manual_events:
        if (ev["_fold_title"], ev["start"][:10]) in scraped_title_dates:
            continue  # the live scraper already has this one - prefer it
        # Multi-day manual entries use end (not just start) against the
        # window - see manual_in_window()'s own docstring for why
        # within_window() alone is wrong for something like a 3-week run.
        if not manual_in_window(ev, tz, past, horizon):
            continue
        ev["colour"] = manual_colours[ev["source"]]
        del ev["_fold_title"]
        all_events.setdefault(ev["uid"], ev)
        manual_kept_by_source[ev["source"]] += 1
    for name in manual_source_order:
        kept = manual_kept_by_source[name]
        url = next((e["url"] for e in manual_events if e["source"] == name and e.get("url")), "")
        source_meta.append({"name": name, "url": url, "colour": manual_colours[name],
                            "count": kept, "method": "manual", "stale": False, "last_ok": today_iso})
        report.append({"source": name, "method": "manual", "found": kept, "kept": kept,
                       "carried": 0, "stale": False, "error_class": "", "note": "hand-curated"})
        print(f"{name:<38} {'manual':<10} found={kept:<4} kept={kept}")

    events = sorted(all_events.values(), key=lambda e: e["start"])
    model = defaults.get("llm_model", "claude-haiku-4-5")
    # Several listing pages state a date but no time at all (confirmed live,
    # not a parsing bug) - the event's own detail page usually has it.
    listing_urls = {src["url"] for src in sources}
    enrich_missing_times(events, tz, defaults.get("respect_robots", True), delay,
                          listing_urls, load_time_cache())
    # Translate first so categorising/tagging both work from the same clean
    # English text as the published page, instead of a mix of languages.
    translation_cache = load_translation_cache()
    translation_cache.update(manual_translation_seed)
    translate_events(events, model, translation_cache)
    cat_cache = load_category_cache()
    cat_cache.update(manual_cat_seed)
    tag_cache = load_tag_cache()
    tag_cache.update(manual_tag_seed)
    classify_categories(events, model, cat_cache)
    classify_tags(events, model, tag_cache)
    payload = {
        "generated": datetime.now(ZoneInfo(tz)).isoformat(),
        "timezone": tz,
        "sources": source_meta,
        "categories": CATEGORIES,
        "tags": TAGS,
        "report": report,
        "events": events,
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
        return 0

    OUT.mkdir(exist_ok=True)
    (OUT / "events.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "events.ics").write_text(build_ics(events, tz), encoding="utf-8")
    print(f"\n{len(events)} events -> docs/events.json + docs/events.ics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
