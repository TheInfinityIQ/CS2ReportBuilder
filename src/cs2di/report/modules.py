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
    _sit: dict = field(default_factory=dict)

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


def _timeline(s: dict) -> str:
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
        cls = ' class="me"' if e["role"] else ""
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
