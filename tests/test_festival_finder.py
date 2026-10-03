import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import festival_finder as F


def test_calendars_are_unique_and_are_urls():
    seeds = F.calendars()
    assert len(seeds) == len(set(seeds))
    assert all(u.startswith("http") for u in seeds)


def test_known_aggregator_present():
    assert any("quefaire.be" in u for u in F.calendars())


def test_only_new_drops_already_known(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "known_sources.txt").write_text("quefaire.be\n")
    seeds_all = F.calendars(only_new=False)
    seeds_new = F.calendars(only_new=True)
    assert len(seeds_new) < len(seeds_all)
    assert not any("quefaire.be" == u.split("//")[1].split("/")[0] for u in seeds_new)
