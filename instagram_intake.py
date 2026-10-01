"""Turn Instagram/Facebook posts that a HUMAN pasted into draft events.

Why this exists: Instagram cannot be scraped (login wall, terms of use) so the pipeline never opens it.
A person (or Claude Code reading a screenshot) supplies the caption; this script does the rest.

Input  instagram_inbox.yml:
  posts:
    - account: thegreenfix_            # handle without @
      post_url: https://www.instagram.com/p/XXXX/     # optional but keep it: it is the audit trail
      posted: 2026-09-20               # date the post went up (needed for 'this Friday', 'demain')
      caption: |                       # paste the caption, or the text you read off the screenshot
        ...
      title: Brussels Climate Drinks   # optional override
      location: Mazette, Place du Jeu de Balle 50   # optional override

Usage:
  python instagram_intake.py instagram_inbox.yml            -> prints drafts + warnings, writes instagram_drafts.yml
  python instagram_intake.py instagram_inbox.yml --accept   -> also appends drafts WITHOUT blocking warnings to manual_events.yml

Rules: nothing is guessed. Missing date -> no draft. Relative or low-confidence date -> draft + warning.
Never put personal names or phone numbers from a caption into the output.
"""
from __future__ import annotations
import re, sys
from datetime import date, datetime
import yaml
import discovery as D

CATEGORY_WORDS = [
    ("activism-justice", ["manif", "march", "rebellion", "activis", "climate march", "grève", "strike"]),
    ("environment", ["climat", "climate", "clean-up", "cleanup", "repair", "zero waste", "biodiversit"]),
    ("music", ["concert", "live music", "dj", "jam", "gig"]),
    ("film-cinema", ["film", "cinema", "cinéma", "screening", "projection"]),
    ("workshops-creative", ["workshop", "atelier", "stage", "cours"]),
    ("talks-discussions", ["talk", "conférence", "conference", "débat", "debate", "lecture", "rencontre", "discussion"]),
    ("markets-fairs", ["brocante", "vide-grenier", "market", "marché", "fair"]),
    ("food-drink", ["drinks", "apéro", "brunch", "dinner", "beer", "bière"]),
    ("culture-arts", ["expo", "exhibition", "vernissage", "théâtre", "theatre", "performance"]),
    ("community-social", ["meetup", "social", "quiz", "game night", "club"]),
]
BLOCKING = {"no date found"}


def _title(caption: str) -> str:
    for line in caption.splitlines():
        t = re.sub(r"[^\w\s'’&:,.()/-]", " ", line, flags=re.UNICODE)
        t = re.sub(r"\s+", " ", t).strip(" .!-:")
        if len(t) >= 4 and not t.startswith(("#", "@")):
            return t[:90]
    return ""


def _category(text: str) -> str:
    f = D.fold(text)
    for cat, words in CATEGORY_WORDS:
        if any(D.fold(w) in f for w in words):
            return cat
    return "other"


def draft(post: dict) -> tuple[list[dict], list[str]]:
    cap = post.get("caption", "")
    posted = post.get("posted")
    posted = posted if isinstance(posted, date) else (date.fromisoformat(str(posted)) if posted else date.today())
    p = D.parse_caption(cap, posted)
    warns: list[str] = []
    if not p["dates"]:
        return [], ["no date found"]
    # keep the strongest date(s); relative/low ones only if nothing better
    firm = [d for d in p["dates"] if d["confidence"] in ("high", "medium") and d["how"] != "relative"]
    dates = firm or p["dates"]
    seen, uniq = set(), []
    for d in dates:
        if d["start"] not in seen:
            seen.add(d["start"]); uniq.append(d)
    if not firm:
        warns.append("date is relative or low confidence: check against the post date")
    if len(uniq) > 1:
        warns.append(f"{len(uniq)} different dates in the caption: one draft each, check they are all real occurrences")
    times = p.get("times", [])
    if not times:
        warns.append("no time found: saved as all-day")
    place = post.get("location") or p.get("place")
    if not place:
        warns.append("no place found")
    title = post.get("title") or _title(cap)
    if not title:
        warns.append("no title found")
    acct = post["account"].lstrip("@")
    base_ver = (f"Instagram post by @{acct}" + (f" ({post['post_url']})" if post.get("post_url") else "")
                + f", posted {posted.isoformat()}; caption supplied by hand, not scraped")
    out = []
    for d in uniq:
        e = {"title": title, "description": re.sub(r"\s+", " ", re.sub(r"[#@]\S+", "", cap)).strip()[:500],
             "source": f"Instagram @{acct}", "category": _category(cap + " " + title),
             "verification": base_ver, "social": {"instagram": f"https://www.instagram.com/{acct}/"}}
        if post.get("post_url"):
            e["url"] = post["post_url"]
        if times:
            e["start"] = f"{d['start']}T{times[0]}"
            if len(times) > 1 and times[1] > times[0]:
                e["end"] = f"{d['start']}T{times[1]}"
        else:
            e["start"] = d["start"]; e["all_day"] = True
        if d.get("end"):
            e["end"] = d["end"]
        if place:
            e["location"] = place
        tags = []
        if p["attributes"].get("free"): tags.append("free")
        if p["attributes"].get("booking"): tags.append("registration-required")
        if times and times[0] >= "18:00": tags.append("evening")
        if tags: e["tags"] = tags
        if p["link_in_bio"]:
            e["note"] = "Caption says 'link in bio': the registration link is not in the caption"
        out.append(e)
    return out, warns


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__); return 2
    posts = yaml.safe_load(open(argv[1], encoding="utf-8"))["posts"]
    drafts, accepted = [], []
    for post in posts:
        evs, warns = draft(post)
        print(f"@{post['account']}: {len(evs)} draft(s)" + ("; WARN: " + " | ".join(warns) if warns else ""))
        for e in evs:
            drafts.append({"event": e, "warnings": warns})
            if not (set(warns) & BLOCKING):
                accepted.append(e)
    yaml.safe_dump({"drafts": drafts}, open("instagram_drafts.yml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=140)
    if "--accept" in argv:
        # manual_events.yml is a bare YAML list, not {"events": [...]}
        existing = yaml.safe_load(open("manual_events.yml", encoding="utf-8")) or []
        have = {(e["title"].lower(), str(e["start"])[:10]) for e in existing}
        added = 0
        for e in accepted:
            if (e["title"].lower(), str(e["start"])[:10]) in have:
                print("skip duplicate:", e["title"], e["start"]); continue
            existing.append(e); added += 1
        yaml.safe_dump(existing, open("manual_events.yml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=140)
        print(f"appended {added} event(s) to manual_events.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
