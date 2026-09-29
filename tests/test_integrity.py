import pytest
from cs2di.evidence import check_demo, scan_batch, roster
from cs2di.ids import parse_steamid


def test_clean_demo_passes(make_demo):
    g = check_demo(make_demo())
    assert g.passed and g.map_name == "de_dust2" and g.n_rounds == 23


def test_soft_warnings_do_not_fail(make_demo):
    g = check_demo(make_demo(warnings=("scoreboard_kill_mismatch",)))
    assert g.passed and g.soft_warnings == 1


@pytest.mark.parametrize("kw,reason", [
    ({"valid": False}, "match_summary.valid_not_true"),
    ({"coaching_valid": False}, "match_summary.coaching_valid_not_true"),
    ({"ok": False}, "integrity_checks.integrity_ok_not_true"),
    ({"hard": 1}, "hard_failure_count_nonzero_or_missing"),
    ({"errors": ["round_table_empty"]}, "integrity_errors_present"),
])
def test_each_hard_failure_fails_closed(make_demo, kw, reason):
    g = check_demo(make_demo(**kw))
    assert not g.passed and reason in g.reasons


def test_missing_file_fails_closed(make_demo):
    g = check_demo(make_demo(skip=("integrity_checks.json",)))
    assert not g.passed and "missing_file:integrity_checks.json" in g.reasons


def test_malformed_json_fails_closed(make_demo):
    d = make_demo()
    (d / "match_summary.json").write_text("{not json")
    assert not check_demo(d).passed


def test_scan_batch_is_sorted_and_isolated(make_demo, tmp_path):
    make_demo("b")
    make_demo("a", valid=False)
    res = scan_batch(tmp_path)
    assert [r.demo_id for r in res] == ["a", "b"] and [r.passed for r in res] == [False, True]


def test_roster_keeps_exact_int_ids(make_demo):
    assert roster(make_demo()) == {76561198062530225: "CanadianIQ"}


def test_steamid_rejects_floats_zero_and_out_of_range():
    assert parse_steamid("76561198062530225") == 76561198062530225
    for bad in (7.6561198062530225e16, 0, "0", "abc", 123):
        with pytest.raises(ValueError):
            parse_steamid(bad)
