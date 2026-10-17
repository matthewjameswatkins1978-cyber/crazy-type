"""Effect discovery and catalogue tests."""

from crazy_type import catalog


def test_catalog_has_at_least_ten_effects():
    assert len(catalog.discover_effects()) >= 10


def test_catalog_includes_headline_effects():
    names = set(catalog.effect_names())
    for expected in ("decrypt", "matrix", "print", "fireworks", "rain", "waves", "burn"):
        assert expected in names


def test_catalog_sorted_and_unique():
    names = catalog.effect_names()
    assert names == sorted(names)
    assert len(names) == len(set(names))


def test_catalog_entries_have_help_text():
    infos = catalog.discover_effects()
    with_help = [i for i in infos if i.help]
    assert len(with_help) >= 10


def test_lookup_roundtrip():
    info = catalog.get_effect_info("decrypt")
    assert info is not None and info.name == "decrypt"
    assert catalog.get_effect_info("no-such-effect") is None
