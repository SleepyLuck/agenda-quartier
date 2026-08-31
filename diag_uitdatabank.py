"""TEMP diagnostic: find how to get GC Pianofabriek's events without scraping JS.

1. Look for any hint of an underlying API in the page's own HTML/JS (script
   src URLs, inline config, fetch() calls) - the most reliable signal, since
   whatever endpoint the page's own JS calls is guaranteed to have current data.
2. Probe a few candidate UiTdatabank (publiq) public search endpoints with a
   query for "Pianofabriek" to see which one is live and what shape it returns.

Writes nothing; only prints. Deleted after use.
"""
import re
import requests

UA = "neighbourhood-events/1.0 (personal event aggregator; contact: you@example.org)"
TIMEOUT = 20


def show(label, resp_or_exc):
    if isinstance(resp_or_exc, Exception):
        print(f"[{label}] ERROR: {type(resp_or_exc).__name__}: {resp_or_exc}")
        return
    r = resp_or_exc
    print(f"[{label}] {r.status_code} · {len(r.content)} bytes · {r.headers.get('content-type','')}")
    if r.ok:
        print(r.text[:1500])
    print()


print("=" * 78)
print("1. Scanning pianofabriek.be/activiteiten's own HTML/JS for API hints")
print("=" * 78)
r = requests.get("https://www.pianofabriek.be/activiteiten",
                  headers={"User-Agent": UA}, timeout=TIMEOUT)
html = r.text
print(f"page: {r.status_code}, {len(html)} chars")

for kw in ["uitdatabank", "uitinvlaanderen", "publiq", "widgets.uitdatabank",
           "search.uitdatabank", "io.uitdatabank"]:
    hits = [m.start() for m in re.finditer(kw, html, re.I)]
    if hits:
        print(f"  found '{kw}' at {len(hits)} position(s), e.g.:")
        for pos in hits[:3]:
            print("   ", html[max(0, pos - 80):pos + 120].replace("\n", " "))
print()

script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
print(f"{len(script_srcs)} <script src> tags:")
for s in script_srcs:
    print(" ", s)
print()

fetch_like = re.findall(r'["\']((?:https?:)?//[^"\']*(?:api|json|events|activit)[^"\']*)["\']', html, re.I)
print(f"{len(fetch_like)} inline URL-ish strings mentioning api/json/events/activit:")
for s in sorted(set(fetch_like))[:20]:
    print(" ", s)

print()
print("=" * 78)
print("2. Probing candidate UiTdatabank public search endpoints")
print("=" * 78)
candidates = [
    "https://search.uitdatabank.be/events/?q=Pianofabriek",
    "https://io.uitdatabank.be/events/?q=Pianofabriek",
    "https://search.uitdatabank.be/organizers/?q=Pianofabriek",
    "https://io.uitdatabank.be/organizers/?q=Pianofabriek",
]
for url in candidates:
    try:
        resp = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"},
                             timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        show(url, exc)
        continue
    show(url, resp)
