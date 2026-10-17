"""Auto Director selection + deterministic seeded randomness tests."""

from crazy_type import catalog, director


def test_auto_error():
    name, _ = director.auto_select("ERROR: failure in module X")
    assert name == "errorcorrect"


def test_auto_warning():
    name, _ = director.auto_select("Warning: deprecated flag")
    assert name == "burn"


def test_auto_success():
    name, _ = director.auto_select("All tests passed!")
    assert name == "fireworks"


def test_auto_startup():
    name, _ = director.auto_select("Hello world")
    assert name == "pour"


def test_auto_ordinary_default():
    name, _ = director.auto_select("The quick brown fox")
    assert name == director.DEFAULT_EFFECT == "decrypt"


def test_auto_error_beats_success():
    # Precedence: an error mention wins even with happy words nearby.
    name, _ = director.auto_select("Build passed but error in post-step")
    assert name == "errorcorrect"


def test_auto_selection_always_valid_effect():
    names = set(catalog.effect_names())
    for sample in ["boom", "ERROR", "warn", "ok done", "hi there", "", "12345"]:
        effect, _ = director.auto_select(sample)
        assert effect in names


def test_seeded_selection_deterministic():
    first, seed = director.pick_random(42)
    second, seed2 = director.pick_random(42)
    assert first == second and seed == seed2 == 42


def test_presets_use_known_effects():
    names = set(catalog.effect_names())
    assert set(director.CALM_EFFECTS) <= names
    assert set(director.CHAOS_EFFECTS) <= names
    calm, _ = director.pick_preset("calm", seed=1)
    chaos, _ = director.pick_preset("chaos", seed=1)
    assert calm in director.CALM_EFFECTS
    assert chaos in director.CHAOS_EFFECTS
    # Same seed replays.
    assert director.pick_preset("calm", seed=1) == director.pick_preset("calm", seed=1)
