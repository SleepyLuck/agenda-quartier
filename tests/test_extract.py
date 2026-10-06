from unittest.mock import patch

import extract


def test_fill_price_from_text_sets_price_from_inline_mention():
    events = [
        {"title": "Atelier", "description": "Tarif: 12€ par personne", "price_min": None},
        {"title": "Concert gratuit", "description": "Entree libre", "price_min": None},
        {"title": "Deja fixe", "description": "15€", "price_min": 5.0, "price_max": 5.0},
    ]
    extract.fill_price_from_text(events)
    assert events[0]["price_min"] == 12.0
    assert events[0]["price_max"] == 12.0
    assert events[1].get("price_min") is None
    # already-set price is never overwritten by the free text pass
    assert events[2]["price_min"] == 5.0


def test_enrich_event_detail_recovers_location_and_price_from_detail_page():
    html = """<html><body><p>Spectacle de danse</p>
    <p>Lieu: Theatre Les Tanneurs</p>
    <p>Tarif: 15€ / 10€ reduit</p>
    </body></html>"""
    ev = {
        "title": "Spectacle", "start": "2026-11-01T00:00:00+01:00", "all_day": True,
        "location": "", "price_min": None, "url": "https://example.com/event",
        "source": "Test",
    }
    with patch("extract.fetch", return_value=html), patch("extract.parse_jsonld", return_value=[]):
        updates = extract.enrich_event_detail(ev, "Europe/Brussels", True)
    assert updates.get("location") == "Theatre Les Tanneurs"
    assert updates.get("price_min") == 10.0
    assert updates.get("price_max") == 15.0


def test_enrich_event_detail_returns_empty_for_non_http_url():
    ev = {"title": "x", "start": "2026-11-01T00:00:00+01:00", "all_day": True, "url": ""}
    assert extract.enrich_event_detail(ev, "Europe/Brussels", True) == {}


def test_enrich_missing_details_uses_cache_without_refetching():
    events = [{
        "uid": "abc123", "title": "Cached", "start": "2026-11-01T00:00:00+01:00",
        "all_day": True, "location": "", "price_min": None, "url": "https://example.com/e",
        "source": "Test",
    }]
    cache = {"abc123": {"start": "2026-11-01T20:00:00+01:00", "all_day": False,
                         "location": "Cached Venue", "price_min": 8.0, "price_max": 8.0}}
    with patch("extract.fetch") as mock_fetch:
        extract.enrich_missing_details(events, "Europe/Brussels", True, 0, set(), cache)
    mock_fetch.assert_not_called()
    assert events[0]["all_day"] is False
    assert events[0]["location"] == "Cached Venue"
    assert events[0]["price_min"] == 8.0
    assert events[0]["detail_checked"] == extract.DETAIL_CACHE_VERSION
