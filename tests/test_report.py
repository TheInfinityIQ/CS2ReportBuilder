import copy
import re

import pytest

from cs2di.digest import build_digest
from cs2di.report import PlanError, build_report

from conftest import HERO

PLAN = {
    "report": {"player": "Hero", "subtitle": "Two rounds"},
    "agenda": "One thing stands out.",
    "moments": [{
        "id": "m1", "intent": "UNDERSTAND", "title": "First fights", "question": "Do you win them?",
        "blocks": [
            {"layout": "text_above", "text": "You took the first kill once.[[note:n]]",
             "module": {"type": "MetricPair", "left": {"metric": "opening_kills", "caption": "Got it"},
                        "right": {"metric": "opening_deaths", "caption": "Lost it", "tone": "bad"}}},
            {"layout": "module_only", "module": {"type": "SituationContrast",
             "left": {"demo": "played", "round": 1, "label": "Won", "why": "You opened and the round was won."},
             "right": {"demo": "played", "round": 2, "label": "Lost", "why": "You were first to die."}}},
        ],
        "takeaway": "Keep going.",
    }],
    "notes": {"n": "A short caveat."},
}


@pytest.fixture
def ready(played_demo):
    return played_demo, build_digest(played_demo, HERO)


def build(ready, plan=PLAN):
    root, digest = ready
    return build_report(plan, digest, batch_dir=root, steamid=HERO)


def mutate(fn):
    p = copy.deepcopy(PLAN)
    fn(p)
    return p


def test_builds_with_both_tabs_and_shell(ready):
    html = build(ready)
    assert 'data-target="tab-study"' in html and 'data-target="tab-desk"' in html
    assert 'id="tab-study"' in html and 'id="tab-desk"' in html
    for part in ("coverage", "agenda", "moment", "takeaway", "notes", "footer"):
        assert part in html


def test_css_is_single_source_and_ai_cannot_style(ready):
    html = build(ready)
    assert html.count("<style>") == 1
    # inline style attributes are only software-computed bar widths, never coach input
    for attr in re.findall(r'style="([^"]*)"', html):
        assert attr.startswith(("width:", "font-weight")), attr
    with pytest.raises(PlanError, match="styling"):
        build(ready, mutate(lambda p: p["moments"][0]["blocks"][0].__setitem__("style", "color:red")))


def test_player_surface_has_no_math_terms(ready):
    html = build(ready)
    study = html.split('id="tab-desk"')[0]
    for word in ("numerator", "denominator", "confidence interval", "p-value", "median"):
        assert word not in study.lower()


def test_math_is_behind_the_calculation_control(ready):
    html = build(ready)
    assert "How is this calculated?" in html and "<details" in html


def test_unknown_module_and_viewer_are_rejected_with_guidance(ready):
    with pytest.raises(PlanError, match="unknown module"):
        build(ready, mutate(lambda p: p["moments"][0]["blocks"][0].__setitem__("module", {"type": "Galaxy3D"})))
    with pytest.raises(PlanError, match="not available yet"):
        build(ready, mutate(lambda p: p["moments"][0]["blocks"][0].__setitem__("module", {"type": "Viewer2D"})))


def test_invented_numbers_in_prose_are_rejected(ready):
    with pytest.raises(PlanError, match="not in the evidence digest"):
        build(ready, mutate(lambda p: p["moments"][0].__setitem__("takeaway", "You got 73 kills and won 91%.")))


def test_problems_are_all_reported_at_once(ready):
    def bad(p):
        p["moments"][0]["intent"] = "FIX"
        p["moments"][0]["blocks"][0]["module"]["left"]["metric"] = "nope"
    with pytest.raises(PlanError) as e:
        build(ready, mutate(bad))
    assert len(e.value.problems) >= 2


def test_html_in_coach_text_is_escaped(ready):
    html = build(ready, mutate(lambda p: p.__setitem__("agenda", "<script>alert(1)</script> hello")))
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_missing_round_is_rejected(ready):
    with pytest.raises(PlanError, match="not found"):
        build(ready, mutate(lambda p: p["moments"][0]["blocks"][1]["module"]["left"].__setitem__("round", 9)))


def test_timeline_uses_literal_names_and_marks_the_player(ready):
    html = build(ready)
    assert "Hero" in html and "Foe1" in html
    assert 'class="me"' in html and "FOCAL" not in html


def test_footnotes_are_numbered_in_order(ready):
    html = build(ready)
    assert 'id="fn1"' in html and "A short caveat." in html


def test_digest_numbers_reach_the_page(ready):
    html = build(ready)
    assert '<div class="val">1</div>' in html      # one opening kill, one opening death


@pytest.mark.parametrize("count", [1, 7, 12])
def test_no_cap_or_minimum_on_teaching_moments(ready, count):
    """Owner ruling 2026-09-29: the evidence sets the number of Teaching Moments, never a rule."""
    def many(p):
        base = p["moments"][0]
        p["moments"] = []
        for i in range(count):
            m = copy.deepcopy(base)
            m["id"] = f"m{i + 1}"
            m["title"] = "Lesson " + "x" * i
            p["moments"].append(m)
    html = build(ready, mutate(many))
    assert html.count('class="moment"') + html.count("class=\"moment ") >= count
