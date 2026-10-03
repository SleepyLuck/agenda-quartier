import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import known_sources as K

KEYS = {"circularium.be", "instagram.com/mazette.brussels", "eventbrite.be/o/the-green-fix-123", "lestanneurs.be", "luma.com/thegreenfix"}

def test_same_site_any_page_is_known():
    assert K.is_known("https://www.lestanneurs.be/fr/spectacles/x", KEYS)
    assert K.is_known("https://circularium.be/open-days", KEYS)

def test_shared_hosts_use_the_account_not_the_host():
    assert K.is_known("https://www.instagram.com/mazette.brussels/p/ABC/", KEYS)
    assert not K.is_known("https://www.instagram.com/other.account/", KEYS)
    assert K.is_known("https://www.eventbrite.be/o/the-green-fix-123", KEYS)
    assert not K.is_known("https://www.eventbrite.be/o/someone-else-999", KEYS)
    assert not K.is_known("https://luma.com/otherorg", KEYS) and K.is_known("https://luma.com/thegreenfix", KEYS)

def test_new_domain_is_new():
    assert not K.is_known("https://www.brusselsartistrun.net/map/", KEYS)

def test_garbage_is_not_known():
    assert not K.is_known("not a url", KEYS)

def test_eventbrite_event_pages_do_not_count_as_a_source():
    assert K.key_of("https://www.eventbrite.be/e/brussels-climate-drinks-tickets-123") is None
    assert not K.is_known("https://www.eventbrite.be/e/some-event-1", KEYS)
