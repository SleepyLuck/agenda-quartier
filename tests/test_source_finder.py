import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import source_finder as S

LISTING_PAGE = """
<html><head></head><body>
<nav><a href="/contact">Contact</a></nav>
<p>Rejoignez notre comité de quartier pour la grande braderie annuelle à Saint-Gilles.</p>
<div class="list">
 <article class="ev"><a href="/e/1">Braderie 1</a><span>ven. 11 déc. 19:30</span></article>
 <article class="ev"><a href="/e/2">Braderie 2</a><span>sam. 12 déc. 19:00</span></article>
 <article class="ev"><a href="/e/3">Braderie 3</a><span>dim. 13 déc. 15:00</span></article>
</div>
<a href="https://www.instagram.com/someorg/">IG</a>
<a href="https://partner-venue.be/agenda">Partner venue</a>
</body></html>"""


def test_build_queries_combines_family_and_communes():
    qs = S.build_queries("neighbourhood-markets", "October 2026")
    assert qs and any("Saint-Gilles" in q and "October 2026" in q for q in qs)
    assert len(qs) == len(set(qs))


def test_score_passes_a_good_candidate(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda url: LISTING_PAGE)
    monkeypatch.setattr(S, "robots_allows", lambda url: True)
    result = S.score("https://new-quartier-site.be/agenda", keys=set())
    assert result["pass"] is True
    assert result["commune_hits"] >= 1
    assert "neighbourhood-markets" in dict(result["groups"])


def test_score_rejects_already_known(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda url: LISTING_PAGE)
    monkeypatch.setattr(S, "robots_allows", lambda url: True)
    result = S.score("https://new-quartier-site.be/agenda", keys={"new-quartier-site.be"})
    assert result["pass"] is False and result["already_known"] is True


def test_score_rejects_when_robots_disallow(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda url: LISTING_PAGE)
    monkeypatch.setattr(S, "robots_allows", lambda url: False)
    result = S.score("https://new-quartier-site.be/agenda", keys=set())
    assert result["pass"] is False


def test_harvest_returns_external_domains_only(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda url: LISTING_PAGE)
    links = S.harvest("https://aggregator.be/page")
    hosts = {l.split("/")[2] for l in links}
    assert "partner-venue.be" in hosts
    assert "aggregator.be" not in hosts
