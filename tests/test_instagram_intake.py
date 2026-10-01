from datetime import date
import instagram_intake as I

CAP = """Brussels Climate Drinks is back! 🍻
📅 Wednesday 30 September
🕕 18:00 - 22:00
📍 Mazette, Place du Jeu de Balle 50
Come chat about climate over a beer. Free entry. Link in bio to register.
#climatedrinks @mazette.brussels"""

def test_full_post():
    ev, w = I.draft({"account": "@thegreenfix_", "posted": date(2026, 9, 20), "caption": CAP, "post_url": "https://www.instagram.com/p/AAA/"})
    assert len(ev) == 1 and not [x for x in w if "date" in x]
    e = ev[0]
    assert e["start"] == "2026-09-30T18:00" and e["end"] == "2026-09-30T22:00"
    assert e["location"].startswith("Mazette") and "free" in e["tags"] and "evening" in e["tags"]
    assert e["title"].startswith("Brussels Climate Drinks") and e["url"].endswith("/p/AAA/")
    assert "not scraped" in e["verification"] and "link in bio" in e["note"].lower()

def test_no_date_means_no_draft():
    ev, w = I.draft({"account": "x", "posted": date(2026, 9, 20), "caption": "Big news soon! Stay tuned."})
    assert ev == [] and w == ["no date found"]

def test_relative_date_warns():
    ev, w = I.draft({"account": "x", "posted": date(2026, 10, 5), "caption": "Concert demain soir à 20h au Jeu de Balle!"})
    assert ev and ev[0]["start"] == "2026-10-06T20:00" and any("relative" in x for x in w)

def test_no_time_is_all_day():
    ev, w = I.draft({"account": "x", "posted": date(2026, 9, 20), "caption": "Vide-grenier Saturday 3 October 2026, rue X"})
    assert ev[0]["all_day"] is True and any("no time" in x for x in w)
