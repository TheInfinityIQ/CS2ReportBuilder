from cs2di.digest import build_digest

from conftest import HERO


def test_counts_including_kill_after_round_end(played_demo):
    d = build_digest(played_demo, HERO)
    m = d["metrics"]
    assert d["scope"]["rounds"] == 2
    assert m["kills"]["value"] == 3          # includes the kill at tick 2100, after round 1 ended
    assert m["deaths"]["value"] == 2
    assert m["headshot_kills"]["value"] == 1
    assert m["kd"]["value"] == 1.5


def test_late_kill_is_never_an_opening(played_demo):
    """Regression for the extractor's post-round kill tagging seen in the MIMY data."""
    m = build_digest(played_demo, HERO)["metrics"]
    assert m["opening_kills"]["value"] == 1
    assert m["opening_deaths"]["value"] == 1
    assert m["opening_kill_died_later"]["value"] == 1
    assert m["opening_kill_survived"]["value"] == 0


def test_damage_ignores_team_damage(played_demo):
    m = build_digest(played_demo, HERO)["metrics"]
    assert m["adr"]["value"] == 100.0        # (50+50+100) / 2 rounds
    assert m["adr"]["numerator"] == 200 and m["adr"]["denominator"] == 2


def test_unknown_is_not_zero(played_demo):
    m = build_digest(played_demo, HERO)["metrics"]
    assert m["rifle_kill_speed"]["value"] is None      # no engagement table in this demo
    assert m["rifle_death_speed"]["value"] is None


def test_every_metric_has_a_plain_definition(played_demo):
    for k, m in build_digest(played_demo, HERO)["metrics"].items():
        assert m["definition"].strip(), k
        assert m["label"].strip(), k


def test_failed_demo_is_excluded(played_demo, make_demo):
    make_demo("broken", hard=1, ok=False)              # fails the hard integrity gate
    d = build_digest(played_demo, HERO)
    assert [x["demo_id"] for x in d["demos"]] == ["played"]


def test_steamid_float_is_rejected(played_demo):
    import pytest
    with pytest.raises(ValueError):
        build_digest(played_demo, 7.6561198062530225e16)


def test_player_not_in_demo_gives_empty_digest(played_demo):
    d = build_digest(played_demo, 76561198999999999)
    assert d["scope"]["rounds"] == 0 and d["metrics"] == {}
