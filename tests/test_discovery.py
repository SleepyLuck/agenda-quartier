import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from datetime import date
import discovery as D

TODAY = date(2026, 10, 1)


def first(text):
    return D.find_dates(text, TODAY)[0]


# ---- dates: formats seen on the real pages / posters ------------------------------------
def test_theatre_national_format():
    h = first("Vendredi 11.12.2026 à 19h30")
    assert h["start"] == date(2026, 12, 11) and h["time"] == "19:30"

def test_rideau_abbreviated_french_no_year():
    h = first("ven. 11 déc. 18:45")
    assert h["start"] == date(2026, 12, 11) and h["time"] == "18:45" and "weekday-match" in h["how"]

def test_english_month_first_with_pm():
    h = first("Saturday, December 12 at 7:00 PM")
    assert h["start"] == date(2026, 12, 12) and h["time"] == "19:00"

def test_next_year_resolved_by_weekday():
    assert first("mercredi 20 janvier 17h")["start"] == date(2027, 1, 20)

def test_impossible_weekday_is_rejected_not_guessed():
    assert D.find_dates("vendredi 12 octobre", TODAY) == []     # 12 Oct 2026 is a Monday

def test_dutch():
    assert first("vr 16 oktober 11:00")["start"] == date(2026, 10, 16)

def test_ordinal_and_explicit_year():
    assert first("1er novembre 2026 de 8h à 19h")["start"] == date(2026, 11, 1)

def test_range_fr():
    h = first("du 8 au 29 octobre")
    assert h["start"] == date(2026, 10, 8) and h["end"] == date(2026, 10, 29)

def test_range_abbrev_across_months():
    h = first("15 Oct – 6 Nov")
    assert h["start"] == date(2026, 10, 15) and h["end"] == date(2026, 11, 6)

def test_range_en_month_first():
    h = first("October 15 – November 6")
    assert h["start"] == date(2026, 10, 15) and h["end"] == date(2026, 11, 6)

def test_range_over_new_year():
    h = first("15 déc - 6 janv 2027")
    assert h["start"] == date(2026, 12, 15) and h["end"] == date(2027, 1, 6)

def test_time_variants():
    ts = {(h, m) for h, m, _ in D.find_times("19h, 19:30, 7:30 PM, 2pm, 20u15")}
    assert {(19, 0), (19, 30), (14, 0), (20, 15)} <= ts

def test_prices_are_not_times():
    assert D.find_times("Tarif 10€ > 21€") == []


# ---- attributes ---------------------------------------------------------------------------
def test_attributes_theatre_page():
    a = D.extract_attributes("Lieu : Studio\nDurée : 52'\nLangue : fr surtitrage en\nTarif : 10€ > 21€\nKids 12+")
    assert a["price_min"] == 10 and a["price_max"] == 21 and a["duration_min"] == 52
    assert a["min_age"] == 12 and a["labelled"]["venue"] == "Studio"
    assert "surtitles" in a

def test_free_booking_soldout_recurring():
    a = D.extract_attributes("Entrée libre, sur réservation. Complet. Tous les mercredis")
    assert a["free"] and a["booking"] and a["sold_out"] and a["recurring"]

def test_free_with_price_needs_review():
    a = D.extract_attributes("Free for under 12. Adults 10 €")
    assert "free" not in a and a.get("free_mentioned_with_price")


# ---- links / listing blocks / signals ------------------------------------------------------
LISTING = """
<html><head><link rel="alternate" type="application/rss+xml" href="/feed"></head><body>
<nav><a href="/contact">Contact</a><a href="/agenda">Agenda</a></nav>
<div class="list">
 <article class="ev"><a href="/spectacle/kabylifornie">Kabylifornie</a><span>ven. 11 déc. 19:30</span></article>
 <article class="ev"><a href="/spectacle/ravage">Ravage tout court</a><span>sam. 12 déc. 19:00</span></article>
 <article class="ev"><a href="/spectacle/traversee">Une traversée</a><span>ven. 11 déc. 21:15</span></article>
</div>
<a href="https://shop.utick.net/?pos=X">Tickets</a>
<a href="https://www.instagram.com/lerideau.brussels/">IG</a><a href="https://www.facebook.com/sharer/sharer.php?u=x">share</a>
<a href="/page/2">Suivant</a></body></html>"""

def test_event_links_and_noise():
    urls = [l["url"] for l in D.find_event_links(LISTING, "https://x.be/agenda")]
    assert "https://x.be/spectacle/kabylifornie" in urls and "https://x.be/contact" not in urls

def test_agenda_links_from_home():
    assert D.find_agenda_links(LISTING, "https://x.be/")[0]["url"] == "https://x.be/agenda"

def test_listing_block_detected():
    b = D.find_listing_blocks(LISTING, TODAY)
    assert b and b[0]["items"] == 3 and b[0]["item"].startswith("article.ev")

def test_extract_recipe_events():
    evs = D.extract_recipe_events(LISTING, "https://x.be/agenda", TODAY)
    assert len(evs) == 3
    by_title = {e["title"]: e for e in evs}
    assert by_title["Kabylifornie"]["url"] == "https://x.be/spectacle/kabylifornie"
    assert by_title["Kabylifornie"]["start"] == "2026-12-11" and by_title["Kabylifornie"]["time"] == "19:30"
    assert by_title["Ravage tout court"]["start"] == "2026-12-12"

def test_extract_recipe_events_skips_undated_items():
    html = """<div class="list">
      <article class="ev"><a href="/a">Dated show</a><span>ven. 11 déc. 19:30</span></article>
      <article class="ev"><a href="/b">No date here</a><span>Coming soon</span></article>
      <article class="ev"><a href="/c">Another dated show</a><span>sam. 12 déc. 19:00</span></article>
      <article class="ev"><a href="/d">Third dated show</a><span>dim. 13 déc. 15:00</span></article>
    </div>"""
    evs = D.extract_recipe_events(html, "https://x.be/", TODAY)
    assert {e["title"] for e in evs} == {"Dated show", "Another dated show", "Third dated show"}

def test_extract_recipe_events_no_listing_returns_empty():
    assert D.extract_recipe_events("<html><body><p>Nothing here</p></body></html>", "https://x.be/", TODAY) == []

def test_signals():
    s = D.extract_signals(LISTING, "https://x.be/")
    assert "utick" in s["ticket_platforms"] and "instagram" in s["social"] and "facebook" not in s["social"]
    assert s["feeds"]

def test_pagination():
    assert D.find_pagination(LISTING, "https://x.be/agenda")

def test_recommend_recipe():
    assert D.recommend_method(LISTING, "https://x.be/agenda", TODAY)["method"] == "recipe"

def test_recommend_jsonld():
    h = '<script type="application/ld+json">{"@type":"MusicEvent","name":"a","startDate":"2026-10-10"}</script>'
    assert D.recommend_method(h, "https://x.be/", TODAY)["method"] == "jsonld"

def test_recommend_ics():
    assert D.recommend_method('<a href="/cal.ics">ical</a>', "https://x.be/", TODAY)["method"] == "ics"

def test_empty_static_page_is_flagged():
    assert D.recommend_method("<html><body><div id=app></div></body></html>", "https://x.be/", TODAY)["method"] == "none-or-browser"


# ---- captions ----------------------------------------------------------------------------
CAP = """🎭 Ce vendredi, on vous attend !
📅 Vendredi 9 octobre
🕖 19h30
📍 Mazette, Place du Jeu de Balle 50
Entrée libre, sur réservation. Avec @lesamisdumazette #vernissage
Lien en bio"""

def test_caption():
    c = D.parse_caption(CAP, date(2026, 10, 5))
    assert any(d["start"] == "2026-10-09" for d in c["dates"])
    assert "19:30" in c["times"] and "Mazette" in c["place"] and c["link_in_bio"]
    assert "lesamisdumazette" in c["handles"] and c["is_event_like"]
    assert c["attributes"]["free"]

def test_caption_relative():
    c = D.parse_caption("Demain soir concert à 20h!", date(2026, 10, 5))
    assert any(d["start"] == "2026-10-06" for d in c["dates"])


# ---- false positives and neighbour-time leakage ------------------------------------------
def test_no_dates_in_addresses_prices_phones():
    junk = "Rue du Viaduc 122, 1050 Ixelles. Tel +32 2 737 16 01, Tickets from EUR 9.90. Durée 1h30. Ref 10-12-14"
    assert D.find_dates(junk, TODAY) == []

def test_time_not_stolen_from_next_date():
    hs = D.find_dates("3-11 octobre ; Zaterdag 17 oktober om 14u00", TODAY)
    assert hs[0]["time"] is None and hs[1]["time"] == "14:00"
