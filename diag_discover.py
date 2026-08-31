"""TEMP diagnostic: for each candidate venue, check whether the guessed
domain resolves, grab the page title (to sanity-check it's the right site),
and look for nav links that plausibly point at an agenda/events page.

I don't have live web access to look these domains up directly, so these
are best-guess root domains from general knowledge - this script is how we
find out which guesses are right, wrong, or need a different subpage,
before anything goes into sources.yml. Writes nothing; only prints.
"""
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = "neighbourhood-events/1.0 (personal event aggregator; contact: you@example.org)"
TIMEOUT = 15

# User-confirmed URLs (real, not guessed) - still probed to determine method.
CANDIDATES = {
    "Recyclart": "https://recyclart.be/fr/agenda",
    "Maxima": "https://communa.be/les-lieux/maxima/",
    "Le Jacques Franck": "https://www.lejacquesfranck.be/",
    "Fuse": "https://www.fuse.be/",
    "Goudblommeke in Papier": "https://goudblommekeinpapier.be/",
    "Le Poche": "https://poche.be/",
    "Sounds Jazz Club": "https://www.sounds.brussels/",
    "U-Square": "https://usquare.brussels/en",
    "BRASS": "https://www.lebrass.be/",
    "WIELS": "https://wiels.org/en",

    # Best-guess root domains from general knowledge - not yet confirmed by
    # the user. This script's job is to sanity-check each one (page title,
    # CMS, any obvious agenda link) before any of them go into sources.yml.
    "Maison des Cultures de Saint-Gilles": "https://mcsaintgilles.be",
    "Maison du Peuple": "https://lamaisondupeuple.be",
    "Maison Poème": "https://maisonpoeme.be",
    "La Maison du Livre": "https://lamaisondulivre.be",
    "Cellule 133": "https://cellule133.be",
    "Petit Kings Comedy Club": "https://petitkings.be",
    "Garage Cultural": "https://garagecultural.be",
    "CCLJ": "https://cclj.be",
    "Musée Horta": "https://hortamuseum.be",
    "Maison Hannon": "https://maisonhannon.brussels",
    "Passerelle Louise": "https://passerellelouise.be",
    "CréaNova": "https://creanova.be",
    "GC Ten Weyngaert": "https://tenweyngaert.be",
    "Fondation A Stichting": "https://a-stichting.be",
    "Park Poétik": "https://parkpoetik.be",
    "Le Senghor": "https://senghor.be",
    "Flagey": "https://flagey.be",
    "Théâtre Mercelis": "https://theatremercelis.be",
    "Théâtre de la Toison d'Or": "https://tot.be",
    "CIVA": "https://civa.brussels",
    "BOZAR": "https://bozar.be",
    "KVS": "https://kvs.be",
    "Kaaitheater": "https://kaaitheater.be",
    "Ancienne Belgique": "https://abconcerts.be",
    "La Madeleine": "https://lamadeleine.be",
}

KEYWORDS = ["agenda", "calendrier", "programme", "activiteiten", "events",
            "kalender", "calendar", "what-s-on", "whats-on", "programma"]

for name, url in CANDIDATES.items():
    print("=" * 78)
    print(f"{name}  ->  {url}")
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr,nl,en"},
                          timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        continue
    if "charset" not in r.headers.get("content-type", "").lower():
        r.encoding = r.apparent_encoding or "utf-8"
    print(f"  status={r.status_code}  final={r.url}")
    soup = BeautifulSoup(r.text, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else "(none)"
    print(f"  title: {title[:90]}")

    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True).lower()
        if any(k in href.lower() or k in text for k in KEYWORDS):
            full = href if href.startswith("http") else urljoin(r.url, href)
            links.setdefault(full, text[:40])
    for full, text in list(links.items())[:6]:
        print(f"    candidate agenda link: {full}  ({text!r})")

    ldjson = len(soup.find_all("script", type="application/ld+json"))
    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    cms = gen.get("content", "") if gen else ""
    if not cms and ("/wp-content/" in r.text or "wp-json" in r.text):
        cms = "WordPress (guessed)"
    print(f"  ld+json blocks on this page: {ldjson}  |  cms: {cms or 'unknown'}")
