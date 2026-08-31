"""Check a site before adding it to sources.yml.

    python probe.py https://example.be/agenda/
    python probe.py --all          # probes every url in sources.yml

Reports, for one URL: what robots.txt says, what the server actually returns,
which CMS is behind it, and which of the four extraction methods would work.
Nothing is written; this is a look-before-you-scrape tool.
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from extract import UA, fetch, parse_ics, parse_jsonld, robots_allows

TZ = "Europe/Brussels"
OK, NO, HM = "  ok  ", " no   ", " ?    "


def line(flag: str, label: str, detail: str = "") -> None:
    print(f"[{flag}] {label:<26} {detail}")


def probe(url: str) -> None:
    print("\n" + "=" * 78)
    print(url)
    print("=" * 78)
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    # --- robots -------------------------------------------------------
    allowed = robots_allows(url)
    line(OK if allowed else NO, "robots.txt",
         "crawling allowed" if allowed else "DISALLOWED — scraper will skip this page")
    try:
        rb = requests.get(root + "/robots.txt", headers={"User-Agent": UA}, timeout=15)
        rules = [ln.strip() for ln in rb.text.splitlines()[:60]
                 if ln.strip().lower().startswith(("user-agent", "disallow", "allow", "sitemap"))]
        line(HM, "robots.txt served", f"HTTP {rb.status_code}, {len(rules)} rule line(s)")
        for ln in rules[:8]:
            print(f"        {ln}")
        if rb.status_code in (401, 403):
            print("        a 401/403 on robots.txt is read as a blanket disallow, which may be")
            print("        a bot-protection layer rather than the organisation's own choice.")
    except Exception as exc:
        line(HM, "robots.txt served", f"{type(exc).__name__} — treated as allowed")

    # --- what actually comes back -------------------------------------
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr,nl,en"},
                         timeout=25)
    except Exception as exc:
        line(NO, "http", f"{type(exc).__name__}: {exc}")
        return
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    html = r.text
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.get_text(strip=True) if soup.title else "")[:70]
    line(OK if r.ok else NO, "http", f"{r.status_code} · {len(html)//1024} kB · final: {r.url}")
    line(HM, "page title", title or "(none)")

    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    cms = gen.get("content", "") if gen else ""
    if not cms:
        if "/wp-content/" in html or "wp-json" in html:
            cms = "WordPress (guessed from asset paths)"
        elif "spip.php" in html or "spip_out" in html:
            cms = "SPIP (guessed from links)"
    line(HM, "cms", cms or "unknown")

    # --- 1. ics -------------------------------------------------------
    ics_links = set()
    for a in soup.find_all(["a", "link"], href=True):
        href = a["href"]
        if ".ics" in href.lower() or "text/calendar" in (a.get("type") or ""):
            ics_links.add(href if href.startswith("http") else root + "/" + href.lstrip("/"))
    if ics_links:
        for link_url in list(ics_links)[:4]:
            try:
                n = len(parse_ics(fetch(link_url), "probe", link_url, TZ))
                line(OK if n else HM, "ics feed", f"{link_url} → {n} events")
            except Exception as exc:
                line(HM, "ics feed", f"{link_url} → {type(exc).__name__}")
    else:
        line(NO, "ics feed", "no .ics link on the page")

    # --- 2. wordpress -------------------------------------------------
    api = f"{root}/wp-json/tribe/events/v1/events?per_page=5"
    try:
        rr = requests.get(api, headers={"User-Agent": UA}, timeout=25)
        if rr.ok and "events" in rr.text[:400]:
            n = len(rr.json().get("events", []))
            line(OK, "wordpress rest", f"{n} events on page 1 → use method: wordpress")
        else:
            line(NO, "wordpress rest", f"HTTP {rr.status_code}")
    except Exception as exc:
        line(NO, "wordpress rest", type(exc).__name__)

    # --- 3. json-ld ---------------------------------------------------
    blocks = soup.find_all("script", type="application/ld+json")
    evs = parse_jsonld(html, "probe", url, TZ)
    line(OK if evs else (HM if blocks else NO), "json-ld",
         f"{len(blocks)} ld+json block(s), {len(evs)} Event node(s)")
    for e in evs[:3]:
        print(f"        · {e['start'][:16]}  {e['title'][:52]}")

    # --- 4. what the llm would see ------------------------------------
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    dates = len(re.findall(
        r"\b\d{1,2}[\s/.-](janv|févr|fev|mars|avr|mai|juin|juil|ao[uû]t|sept|oct|nov|d[ée]c"
        r"|jan|feb|maa|apr|mei|jun|jul|aug|sep|okt|dec)", text, re.I))
    line(OK if dates >= 3 else HM, "llm fallback",
         f"{len(text)//1000}k chars of text, ~{dates} date-like strings")
    if dates < 3:
        print("        the dates are probably injected by JavaScript — the LLM rung will")
        print("        see an empty page. Look for an underlying feed or API instead.")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--all":
        cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
        urls = [s["url"] for s in cfg.get("sources", [])]
    else:
        urls = args
    for u in urls:
        probe(u)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
