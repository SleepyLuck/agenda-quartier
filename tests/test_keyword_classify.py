import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import keyword_classify as C


def test_theatre_text_matches_theatre_group():
    hits = dict(C.classify("Notre nouvelle saison culturelle: spectacles de danse et théâtre contemporain"))
    assert "theatre-performing" in hits and hits["theatre-performing"] >= 2


def test_brocante_text_matches_markets_group():
    hits = dict(C.classify("Grande braderie et vide-grenier du quartier, comité de quartier organisateur"))
    assert "neighbourhood-markets" in hits


def test_multi_group_text_scores_both():
    hits = dict(C.classify("Atelier de gravure et vernissage à la galerie d'artiste"))
    assert "workshops-creative" in hits and "art-spaces" in hits


def test_unrelated_text_matches_nothing():
    assert C.classify("Politique tarifaire et conditions générales de vente") == []


def test_best_match_is_sorted_first():
    hits = C.classify("Pub quiz anglophone puis soirée clubbing techno jusqu'au bout de la nuit")
    assert hits[0][0] in {"social-english", "nightlife"}
