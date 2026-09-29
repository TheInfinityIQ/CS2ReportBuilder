import copy

import pandas as pd
import pytest

from cs2di.analyst import _rate
from cs2di.digest import build_digest
from cs2di.impact import WinChance
from cs2di.report import PlanError, build_report

from conftest import HERO


def test_win_chance_edges_and_shrinkage():
    states = pd.DataFrame([{"side": "T", "own": 5, "opp": 4, "planted": False, "win": True}] * 3
                          + [{"side": "T", "own": 5, "opp": 5, "planted": False, "win": w} for w in (True, False)])
    wc = WinChance(states)
    assert wc("T", 0, 3, False) == 0.0 and wc("CT", 2, 0, True) == 1.0
    v = wc("T", 5, 4, False)
    assert 0.5 < v < 1.0  # three wins from three cases is shrunk, not taken as certain


def test_small_samples_never_become_findings():
    me = pd.DataFrame({"x": [True] * 5, "_half": [0, 1, 0, 1, 0]})
    peers = pd.DataFrame({"x": [False] * 50 + [True] * 50})
    r = _rate("t.x", "value", "x", "x", me, peers, "x")
    from cs2di.analyst import _status
    assert r["n"] == 5 and _status(r) == "too_few"


def _analysis(demo="played", rnd=1):
    f = {"id": "value.first_death", "topic": "value", "dimension_label": "Value", "situation": "Dying first",
         "plain": "Share of deaths that came first.", "kind": "rate_vs_peers", "k": 12, "n": 40, "rate": 0.3,
         "baseline_rate": 0.15, "diff_pp": 15.0, "fights_vs_baseline": 6.0, "ci": [0.18, 0.45], "p": 0.01, "q": 0.05,
         "halves_agree": True, "higher_is_good": False, "unit": "share", "status": "credible",
         "examples": [{"demo_id": demo, "round": rnd, "tick": 100, "own_alive": 5, "opp_alive": 5, "why": "first death"}]}
    return {"steamid": str(HERO), "baseline": {"peer_players": 9, "matches": 1, "subject_fights": 50, "subject_decided": 40,
                                              "subject_win_rate": 0.5, "peer_win_rate": 0.5}, "findings": [f]}


PLAN = {
    "agenda": "One thing.",
    "moments": [{"id": "m", "intent": "ACTION", "title": "t", "question": "q?", "takeaway": "k",
                 "blocks": [{"layout": "text_above", "text": "You die first more than your lobbies.",
                             "module": {"type": "FindingCard", "finding": "value.first_death"}},
                            {"layout": "module_only", "module": {"type": "KeyMoments", "finding": "value.first_death",
                             "picks": [{"example": 0, "note": "You go in alone here."}]}}]}],
}


@pytest.fixture
def ready(played_demo):
    return played_demo, build_digest(played_demo, HERO)


def test_finding_blocks_render_with_verdict_and_calculation(ready):
    root, d = ready
    html = build_report(PLAN, d, batch_dir=root, steamid=HERO, analysis=_analysis())
    assert "Clear difference from the players in your games" in html and "How is this calculated?" in html
    assert "You go in alone here." in html
    assert "Findings" in html  # analyst desk section


@pytest.mark.parametrize("change, message", [
    (lambda p: p["moments"][0]["blocks"][0]["module"].update(finding="nope"), "unknown finding"),
    (lambda p: p["moments"][0]["blocks"][1]["module"]["picks"][0].update(example=5), "example must be"),
    (lambda p: p["moments"][0]["blocks"][1]["module"]["picks"][0].update(note="You lost 73% of these."), "73%"),
    (lambda p: p["moments"][0]["blocks"][1]["module"]["picks"][0].update(color="red"), "unexpected field"),
])
def test_bad_finding_plans_are_rejected(ready, change, message):
    root, d = ready
    plan = copy.deepcopy(PLAN)
    change(plan)
    with pytest.raises(PlanError) as e:
        build_report(plan, d, batch_dir=root, steamid=HERO, analysis=_analysis())
    assert message in str(e.value)


def test_numbers_from_findings_are_allowed_in_prose(ready):
    root, d = ready
    plan = copy.deepcopy(PLAN)
    plan["moments"][0]["blocks"][0]["text"] = "12 of your 40 deaths came first, 30% against 15% in your lobbies."
    build_report(plan, d, batch_dir=root, steamid=HERO, analysis=_analysis())
