"""Presentation modules. One implementation each; the AI only chooses one and supplies data refs.

Every module: ``check(spec, ctx)`` validates the request, ``render(spec, ctx)`` returns HTML.
Evidence modules always carry their own "How is this calculated" / "Why this example" detail so
the player surface stays free of maths until someone asks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import fmt
from .fmt import esc
from .situation import load_situation


class ModuleError(ValueError):
    pass


@dataclass
class Ctx:
    digest: dict
    batch_dir: Path
    steamid: int
    analysis: dict | None = None
    _sit: dict = field(default_factory=dict)
    maps: dict = field(default_factory=dict)  # map backgrounds used by viewers (emitted once per page)
    weapon_assets: set = field(default_factory=set)

    def finding(self, fid: str) -> dict:
        for f in (self.analysis or {}).get("findings", []):
            if f["id"] == fid:
                return f
        known = [f["id"] for f in (self.analysis or {}).get("findings", []) if f["status"] in ("credible", "leaning", "no_difference")]
        raise ModuleError(f"unknown finding '{fid}' (usable ids include: {', '.join(known[:40])})")

    def metric(self, mid: str) -> dict:
        m = self.digest["metrics"].get(mid)
        if m is None:
            raise ModuleError(f"unknown metric '{mid}' (available: {', '.join(sorted(self.digest['metrics']))})")
        return m

    def situation(self, demo: str, rnd: int) -> dict:
        key = (demo, rnd)
        if key not in self._sit:
            try:
                self._sit[key] = load_situation(self.batch_dir, demo, rnd, self.steamid)
            except KeyError as e:
                raise ModuleError(str(e)) from None
        return self._sit[key]


def _req(spec: dict, key: str, kind: type, where: str):
    if key not in spec or not isinstance(spec[key], kind):
        raise ModuleError(f"{where}: '{key}' is required and must be {kind.__name__}")
    return spec[key]


def _only(spec: dict, allowed: set, where: str):
    extra = set(spec) - allowed - {"type"}
    if extra:
        raise ModuleError(f"{where}: unexpected field(s) {sorted(extra)} (allowed: {sorted(allowed)})")


def _disclosure(title: str, rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)
    return f'<details class="disc"><summary>{esc(title)}</summary><div class="disc-body"><dl>{body}</dl></div></details>'


def _calc_rows(m: dict) -> list[tuple[str, str]]:
    rows = [(m["label"], m["definition"])]
    n, d = m["numerator"], m["denominator"]
    if n is not None and d is not None:
        rows.append(("Count behind it", f"{n:,} out of {d:,} ({m['scope']})"))
    elif d is not None:
        rows.append(("Count behind it", f"based on {d:,} cases ({m['scope']})"))
    else:
        rows.append(("Scope", m["scope"]))
    return rows


# ---------------------------------------------------------------- MetricPair
TONES = {"neutral", "good", "bad"}


def _metric_card(ctx: Ctx, ref: dict, where: str) -> str:
    _only(ref, {"metric", "caption", "tone"}, where)
    m = ctx.metric(_req(ref, "metric", str, where))
    tone = ref.get("tone", "neutral")
    if tone not in TONES:
        raise ModuleError(f"{where}: tone must be one of {sorted(TONES)}")
    cap = ref.get("caption") or m["label"]
    return (f'<div class="metric {esc(tone)}"><div class="val">{esc(fmt.value_text(m["value"], m["unit"]))}</div>'
            f'<div class="cap">{esc(cap)}</div></div>')


def _pair_check(spec, ctx):
    _only(spec, {"title", "left", "right"}, "MetricPair")
    for side in ("left", "right"):
        _metric_card(ctx, _req(spec, side, dict, "MetricPair"), f"MetricPair.{side}")


def _pair_render(spec, ctx):
    refs = [spec["left"], spec["right"]]
    title = f'<div class="mod-title">{esc(spec["title"])}</div>' if spec.get("title") else ""
    cards = "".join(_metric_card(ctx, r, "MetricPair") for r in refs)
    rows = [row for r in refs for row in _calc_rows(ctx.metric(r["metric"]))]
    return f'<div class="mod">{title}<div class="metric-pair">{cards}</div>{_disclosure("How is this calculated?", rows)}</div>'


# -------------------------------------------------------------- MetricCluster
def _cluster_check(spec, ctx):
    _only(spec, {"title", "metrics"}, "MetricCluster")
    ms = _req(spec, "metrics", list, "MetricCluster")
    if not 2 <= len(ms) <= 4:
        raise ModuleError("MetricCluster: 'metrics' needs 2 to 4 entries")
    for i, r in enumerate(ms):
        if not isinstance(r, dict):
            raise ModuleError(f"MetricCluster.metrics[{i}] must be an object")
        _metric_card(ctx, r, f"MetricCluster.metrics[{i}]")


def _cluster_render(spec, ctx):
    title = f'<div class="mod-title">{esc(spec["title"])}</div>' if spec.get("title") else ""
    cards = "".join(_metric_card(ctx, r, "MetricCluster") for r in spec["metrics"])
    rows = [row for r in spec["metrics"] for row in _calc_rows(ctx.metric(r["metric"]))]
    return f'<div class="mod">{title}<div class="cluster">{cards}</div>{_disclosure("How is this calculated?", rows)}</div>'


# ----------------------------------------------------------- ContextBreakdown
MEASURES = {
    "opening_balance": ("First fights by map", "Opening kills (green) against opening deaths (red) on each map.",
                        "An opening fight is the first kill of a round. Counted per map across the included games."),
    "kd": ("Kill/death ratio by map", "Kills divided by deaths on each map.", "Kills divided by deaths, per map."),
    "adr": ("Damage per round by map", "Average damage dealt to enemies per round.", "Damage to enemies (health only) divided by rounds, per map."),
    "utility_damage": ("Grenade damage by map", "Average damage to enemies from HE and fire per round.",
                       "HE grenade and fire (molotov/incendiary) damage to enemies divided by rounds, per map."),
}


def _bar(kind: str, frac: float, label: str) -> str:
    return (f'<div class="bar-line"><div class="bar {kind}" style="width:{max(frac, 0.01) * 100:.1f}%"></div>'
            f'<span class="bar-num">{esc(label)}</span></div>')


def _bars(ctx: Ctx, measure: str, highlight: set) -> str:
    pm = ctx.digest["per_map"]
    rows = []
    if measure == "opening_balance":
        top = max([max(x["opening_kills"], x["opening_deaths"]) for x in pm] + [1])
        for x in pm:
            rows.append((x["map"], _bar("k", x["opening_kills"] / top, f'{x["opening_kills"]} kills') + _bar("d", x["opening_deaths"] / top, f'{x["opening_deaths"]} deaths')))
    else:
        key = {"kd": "kd", "adr": "adr", "utility_damage": "enemy_utility_damage_per_round"}[measure]
        vals = [x[key] for x in pm if x[key] is not None]
        top = max(vals + [0.0001])
        for x in pm:
            v = x[key]
            if v is None:
                rows.append((x["map"], '<span class="bar-num">Unknown</span>'))
                continue
            txt = (f"{v:.2f}" if measure == "kd" else f"{v:.1f} a round" if measure == "utility_damage"
                   else f"{v:.0f} a round")
            rows.append((x["map"], _bar("", v / top, txt)))
    out = []
    for mp, inner in rows:
        strong = ' style="font-weight:800"' if mp in highlight else ""
        out.append(f'<div class="bar-row"><div class="bar-label"{strong}>{esc(fmt.map_name(mp))}</div><div class="bar-track">{inner}</div></div>')
    return f'<div class="bars">{"".join(out)}</div>'


def _ctx_check(spec, ctx):
    _only(spec, {"title", "measure", "highlight"}, "ContextBreakdown")
    m = _req(spec, "measure", str, "ContextBreakdown")
    if m not in MEASURES:
        raise ModuleError(f"ContextBreakdown: measure must be one of {sorted(MEASURES)}")
    known = {x["map"] for x in ctx.digest["per_map"]}
    bad = set(spec.get("highlight", [])) - known
    if bad:
        raise ModuleError(f"ContextBreakdown: unknown map(s) {sorted(bad)}")


def _ctx_render(spec, ctx):
    default_title, blurb, calc = MEASURES[spec["measure"]]
    title = esc(spec.get("title") or default_title)
    rounds = "; ".join(f"{fmt.map_name(x['map'])} {x['rounds']} rounds" for x in ctx.digest["per_map"])
    body = _bars(ctx, spec["measure"], set(spec.get("highlight", [])))
    disc = _disclosure("How is this calculated?", [("What it shows", blurb), ("Calculation", calc), ("Sample per map", rounds)])
    return f'<div class="mod"><div class="mod-title">{title}</div>{body}{disc}</div>'


# ------------------------------------------------------------ Situation cards
def _sit_ref_check(ref: dict, where: str, ctx: Ctx):
    _only(ref, {"demo", "round", "label", "why"}, where)
    demo = _req(ref, "demo", str, where)
    rnd = _req(ref, "round", int, where)
    _req(ref, "why", str, where)
    ctx.situation(demo, rnd)


def _name(n, side):
    if not n:
        return "the bomb / world"
    return f'<span class="{esc(side or "")}">{esc(n)}</span>'


def _timeline(s: dict, focus_tick: int | None = None) -> str:
    items = []
    for e in s["events"]:
        killer = _name(e["killer"], e["killer_side"]) if not e["self_or_world"] else "the bomb / world"
        text = f'{killer} killed {_name(e["victim"], e["victim_side"])}' if not e["self_or_world"] else f'{_name(e["victim"], e["victim_side"])} died to the bomb / world'
        extra = []
        if e["weapon"] and not e["self_or_world"]:
            extra.append(fmt.weapon(e["weapon"]) + (", headshot" if e["headshot"] else ""))
        if e["place"]:
            extra.append("at " + e["place"])
        tail = f' <span class="muted small">({esc(" ".join(extra))})</span>' if extra else ""
        classes = [c for c in ("me" if e["role"] else "", "focus" if focus_tick is not None and e.get("tick") == focus_tick else "") if c]
        cls = f' class="{" ".join(classes)}"' if classes else ""
        items.append((e["t"], f'<li{cls}><span class="tm">{fmt.clock(e["t"])}</span><span>{text}{tail}</span></li>'))
    if s["bomb"]:
        site = f' at {esc(s["bomb"]["site"])}' if s["bomb"]["site"] else ""
        items.append((s["bomb"]["t"], f'<li><span class="tm">{fmt.clock(s["bomb"]["t"])}</span><span class="muted">Bomb planted{site}</span></li>'))
    items.sort(key=lambda x: x[0])
    if not items:
        return '<p class="muted small">No kills this round.</p>'
    return f'<ul class="timeline">{"".join(h for _, h in items)}</ul>'


def _sit_card(ref: dict, ctx: Ctx) -> str:
    s = ctx.situation(ref["demo"], ref["round"])
    label = ref.get("label") or f"Round {s['round']}"
    res = '<span class="tag win">Round won</span>' if s["win"] else '<span class="tag loss">Round lost</span>'
    return (f'<div class="sit"><div class="sit-head"><strong>{esc(label)}</strong><span>'
            f'<span class="tag">{esc(fmt.map_name(s["map"]))} · {esc(s["side"])} · round {s["round"]}</span> {res}</span></div>'
            f'<p class="why"><b>Why this one:</b> {esc(ref["why"])}</p>{_timeline(s)}</div>')


def _contrast_check(spec, ctx):
    _only(spec, {"title", "left", "right"}, "SituationContrast")
    for side in ("left", "right"):
        _sit_ref_check(_req(spec, side, dict, "SituationContrast"), f"SituationContrast.{side}", ctx)


def _contrast_render(spec, ctx):
    title = f'<div class="mod-title">{esc(spec["title"])}</div>' if spec.get("title") else ""
    disc = _disclosure("How were these chosen?", [
        ("Selection", "Each example is a real round from the included games, picked to illustrate the point above."),
        ("Caution", "Two rounds show what a pattern looks like. They do not prove how often it happens.")])
    return f'<div class="mod">{title}<div class="contrast">{_sit_card(spec["left"], ctx)}{_sit_card(spec["right"], ctx)}</div>{disc}</div>'


def _timeline_check(spec, ctx):
    _only(spec, {"title", "situation"}, "EventTimeline")
    _sit_ref_check(_req(spec, "situation", dict, "EventTimeline"), "EventTimeline.situation", ctx)


def _timeline_render(spec, ctx):
    title = f'<div class="mod-title">{esc(spec["title"])}</div>' if spec.get("title") else ""
    return f'<div class="mod">{title}{_sit_card(spec["situation"], ctx)}</div>'


# ---------------------------------------------------------------- FindingCard
STATUS_WORDS = {
    "credible": "Supported in this sample: a difference from the players in your games",
    "leaning": "Possible difference, not proven",
    "no_difference": "No detectable difference from the players in your games in this sample",
    "unclear": "Not enough to tell",
    "too_few": "Too few cases to tell",
}


def _fval(f: dict, v) -> str:
    if v is None:
        return "Unknown"
    if f.get("unit") == "win_points":
        return f"{v * 100:+.0f} win points"
    return f"{v * 100:.0f}%"


def _finding_check(spec, ctx):
    _only(spec, {"finding", "caption"}, "FindingCard")
    ctx.finding(_req(spec, "finding", str, "FindingCard"))


def pfmt(v) -> str:
    return "<0.001" if v is not None and v < 0.001 else "" if v is None else f"{v:.3f}"


def _finding_calc(f: dict) -> list[tuple[str, str]]:
    rows = [("What it measures", f.get("plain") or f"{f['dimension_label']}: {f['situation']}")]
    if f.get("k") is not None:
        rows.append(("Your count", f"{f['k']:,} out of {f['n']:,}"))
    else:
        rows.append(("Your cases", f"{f['n']:,}"))
    rows.append(("Compared with", "the other players in the same matches (same lobbies, similar level)"
                 if f["kind"] != "result_vs_own_level" else "the players in your games, adjusted to your own overall level"))
    lo, hi = f.get("ci") or (None, None)
    if lo is not None:
        rows.append(("Uncertainty", f"95% interval {lo * 100:.0f} to {hi * 100:.0f}" + (" points" if f.get("kind") == "mean_vs_peers" else "%")))
    q = f.get("q")
    rows.append(("Test", f"p = {pfmt(f['p'])}" + (f", after correcting for the number of checks q = {pfmt(q)}" if q is not None else "")
                 + ("; both interleaved splits of your games agree" if f.get("halves_agree") else "; the two interleaved splits of your games do not clearly agree" if f.get("halves_agree") is False else "")))
    rows.append(("Verdict", STATUS_WORDS[f["status"]]))
    return rows


def _finding_render(spec, ctx):
    f = ctx.finding(spec["finding"])
    you, base = f.get("rate"), f.get("baseline_rate")
    def row(label, v, cls):
        if f.get("unit") == "win_points":  # centred scale: -50..+50 win points
            w = min(abs(v or 0) * 100, 50) / 100
            return (f'<div class="bar-row"><div class="bar-label">{label}</div><div class="bar-track">'
                    f'{_bar(cls, w, _fval(f, v))}</div></div>')
        return (f'<div class="bar-row"><div class="bar-label">{label}</div><div class="bar-track">'
                f'{_bar(cls, min(max(v or 0, 0), 1), _fval(f, v))}</div></div>')
    bars = row("You", you, "you") + row("Players in your games", base, "peer")
    scale = '<div class="bar-row"><div class="bar-label"></div><div class="bar-scale"><span>0%</span><span>50%</span><span>100%</span></div></div>' if f.get("unit") != "win_points" else ""
    bars += scale
    cap = spec.get("caption") or f["situation"]
    return (f'<div class="mod"><div class="mod-title">{esc(cap)}</div><div class="bars">{bars}</div>'
            f'<p class="verdict {esc(f["status"])}">{esc(STATUS_WORDS[f["status"]])}</p>'
            f'{_disclosure("How is this calculated?", _finding_calc(f))}</div>')


# ----------------------------------------------------------------- KeyMoments
def _moments_check(spec, ctx):
    _only(spec, {"title", "finding", "picks"}, "KeyMoments")
    f = ctx.finding(_req(spec, "finding", str, "KeyMoments"))
    picks = _req(spec, "picks", list, "KeyMoments")
    if not 1 <= len(picks) <= 6:
        raise ModuleError("KeyMoments: choose 1 to 6 picks")
    for i, pk in enumerate(picks):
        w = f"KeyMoments.picks[{i}]"
        if not isinstance(pk, dict):
            raise ModuleError(f"{w} must be an object")
        _only(pk, {"example", "note"}, w)
        ix = _req(pk, "example", int, w)
        if not 0 <= ix < len(f["examples"]):
            raise ModuleError(f"{w}: example must be 0..{len(f['examples']) - 1} for this finding")
        _req(pk, "note", str, w)
        e = f["examples"][ix]
        ctx.situation(e["demo_id"], int(e["round"]))


def _moment_context(e: dict) -> str:
    bits = []
    if e.get("own_alive") is not None and e.get("opp_alive") is not None:
        bits.append(f"{e['own_alive']} of your team alive against {e['opp_alive']}")
    td = e.get("teammate_distance")
    if "teammate_distance" in e:
        bits.append("no teammate close by" if td is None or td > 900 else "a teammate close by")
    if e.get("round_time_s") is not None:
        bits.append(f"{fmt.clock(e['round_time_s'])} into the round")
    return " · ".join(bits)


def _km_filters(sits) -> str:
    """Filter buttons that belong to ONE set of example replays (not the whole report). Shown only when there is a choice."""
    outcomes = [o for o in ("win", "loss") if any(x[0] == o for x in sits)]
    maps = sorted({x[1] for x in sits if x[1]})
    if len(sits) < 2 or (len(outcomes) < 2 and len(maps) < 2):
        return ""
    g1 = ""
    if len(outcomes) > 1:
        g1 = ('<span class="fgrp"><span class="filter-label">Result</span>'
              + "".join(f'<button type="button" class="filter-btn {o}" data-fo="{o}" aria-pressed="false">'
                        f'{"Won" if o == "win" else "Lost"} ({sum(1 for x in sits if x[0] == o)})</button>' for o in outcomes)
              + "</span>")
    g2 = ""
    if len(maps) > 1:
        g2 = ('<span class="fgrp"><span class="filter-label">Map</span>'
              + "".join(f'<button type="button" class="filter-btn" data-fm="{esc(mp)}" aria-pressed="false">'
                        f'{esc(fmt.map_name(mp))} ({sum(1 for x in sits if x[1] == mp)})</button>' for mp in maps)
              + "</span>")
    return (f'<div class="km-filters" role="group" aria-label="Filter example replays">'
            f'<span class="filter-label">Filter example replays</span>{g1}{g2}'
            f'<button type="button" class="filter-btn" data-reset="1" hidden>Show all</button></div>')


def _moments_render(spec, ctx):
    from .viewer import observed_facts, viewer_html

    f = ctx.finding(spec["finding"])
    title = f'<div class="mod-title">{esc(spec["title"])}</div>' if spec.get("title") else ""
    drawers, sits = [], []
    for i, pk in enumerate(spec["picks"]):
        e = f["examples"][pk["example"]]
        demo, rnd, tick = e["demo_id"], int(e["round"]), e.get("tick")
        s = ctx.situation(demo, rnd)
        res = '<span class="tag win">Round won</span>' if s["win"] else '<span class="tag loss">Round lost</span>'
        facts = observed_facts(ctx.batch_dir, demo, rnd, ctx.steamid, tick)
        view = viewer_html(ctx.batch_dir, demo, rnd, ctx.steamid, tick, ctx.maps, ctx.weapon_assets)
        outcome = "win" if s["win"] else "loss"
        sits.append((outcome, s["map"]))
        clock_str = fmt.clock(e["round_time_s"]) if e.get("round_time_s") is not None else ""
        summary_label = (f'{esc(fmt.map_name(s["map"]))} · round {s["round"]}'
                         + (f' · {clock_str}' if clock_str else "")
                         + f' · {esc(s["side"])}')
        open_attr = " open" if i == 0 else ""
        card_inner = (
            f'<div class="observed"><div class="eyebrow">What happened (from the demo)</div>'
            f'<ul>{"".join(f"<li class=sub>{esc(x.strip())}</li>" if x.startswith("  ") else f"<li>{esc(x)}</li>" for x in facts)}</ul></div>'
            f'{view}<p class="why"><b>Coach\'s read:</b> {esc(pk["note"])}</p>'
            f'<details class="disc"><summary>Show every kill in the round</summary>'
            f'<div class="disc-body">{_timeline(s, tick)}</div></details>')
        drawers.append(
            f'<details class="km-drawer" data-outcome="{outcome}" data-map="{esc(s["map"])}"{open_attr}>'
            f'<summary class="km-summary"><span class="km-label">{summary_label}</span>'
            f'<span class="km-res">{res}</span></summary>'
            f'<div class="sit">{card_inner}</div>'
            f'</details>')
    disc = _disclosure("Why these rounds?", [
        ("Where they come from", f"Rounds from your games that fit: {f['situation'].lower()}."),
        ("What is fact and what is opinion", "'What happened' is computed from the demo. 'Coach's read' is interpretation."),
        ("Caution", "A few rounds show what the pattern looks like; the card above shows how often it happens.")])
    return (f'<div class="mod">{title}{_km_filters(sits)}<div class="moments km-accordion">{"".join(drawers)}</div>'
            f'<p class="km-empty" hidden>No example replays match this filter.</p>{disc}</div>')


# ------------------------------------------------------------------- Registry
@dataclass(frozen=True)
class Module:
    check: Callable
    render: Callable


REGISTRY: dict[str, Module] = {
    "MetricPair": Module(_pair_check, _pair_render),
    "MetricCluster": Module(_cluster_check, _cluster_render),
    "ContextBreakdown": Module(_ctx_check, _ctx_render),
    "SituationContrast": Module(_contrast_check, _contrast_render),
    "EventTimeline": Module(_timeline_check, _timeline_render),
    "FindingCard": Module(_finding_check, _finding_render),
    "KeyMoments": Module(_moments_check, _moments_render),
}

# Deliberately not offered yet; the message tells the coach what to do instead.
NOT_YET = {
    "Viewer2D": "the map viewer is not available yet (it needs verified map radar images); use EventTimeline or SituationContrast for now",
}


def check_module(spec: dict, ctx: Ctx, where: str):
    if not isinstance(spec, dict) or "type" not in spec:
        raise ModuleError(f"{where}: module must be an object with a 'type'")
    t = spec["type"]
    if t in NOT_YET:
        raise ModuleError(f"{where}: {NOT_YET[t]}")
    if t not in REGISTRY:
        raise ModuleError(f"{where}: unknown module '{t}' (available: {', '.join(sorted(REGISTRY))})")
    REGISTRY[t].check(spec, ctx)


def render_module(spec: dict, ctx: Ctx) -> str:
    return REGISTRY[spec["type"]].render(spec, ctx)
