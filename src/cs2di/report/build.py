"""Assemble the single-file report: Player Study tab + Analyst Desk tab, styled only by theme.py."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from . import fmt
from .fmt import esc
from .modules import Ctx, render_module
from .plan import validate_plan
from .theme import CSS

_NOTE = re.compile(r"\[\[note:([\w-]+)\]\]")


class _Notes:
    def __init__(self, notes: dict):
        self.notes, self.order = notes, []

    def text(self, raw: str) -> str:
        """Escape, paragraph-split, and turn [[note:key]] markers into numbered footnote links."""
        out = []
        for para in re.split(r"\n\s*\n", str(raw).strip()):
            parts, last = [], 0
            for m in _NOTE.finditer(para):
                parts.append(esc(para[last:m.start()]))
                k = m.group(1)
                if k not in self.order:
                    self.order.append(k)
                n = self.order.index(k) + 1
                parts.append(f'<sup class="fn"><a href="#fn{n}" id="ref{n}" title="See note {n}">{n}</a></sup>')
                last = m.end()
            parts.append(esc(para[last:]))
            out.append(f"<p>{''.join(parts)}</p>")
        return "".join(out)

    def list_html(self) -> str:
        if not self.order:
            return ""
        li = "".join(f'<li id="fn{i + 1}">{esc(self.notes[k])} <a href="#ref{i + 1}">↩</a></li>' for i, k in enumerate(self.order))
        return f'<section class="notes"><div class="eyebrow">Notes</div><ol>{li}</ol></section>'


def _block(b: dict, ctx: Ctx, notes: _Notes) -> str:
    lay = b["layout"]
    text = notes.text(b["text"]) if b.get("text") else ""
    mod = render_module(b["module"], ctx) if b.get("module") else ""
    if lay == "text_only":
        return f'<div class="block text_only">{text}</div>'
    if lay == "module_only":
        return f'<div class="block module_only">{mod}</div>'
    if lay == "side_by_side":
        return f'<div class="block side_by_side"><div>{text}</div><div>{mod}</div></div>'
    return f'<div class="block text_above">{text}{mod}</div>'


def _moment(m: dict, ctx: Ctx, notes: _Notes) -> str:
    blocks = "".join(_block(b, ctx, notes) for b in m["blocks"])
    labels = {"ACTION": "Something to change", "UNDERSTAND": "Something to understand",
              "REINFORCE": "Keep doing this", "WATCH": "Something to watch"}
    return (f'<section class="moment" id="{esc(m["id"])}"><div class="moment-head">'
            f'<span class="intent {esc(m["intent"])}">{esc(labels[m["intent"]])}</span><h2>{esc(m["title"])}</h2></div>'
            f'<p class="question">{esc(m["question"])}</p>{blocks}'
            f'<div class="takeaway"><div class="eyebrow">What to take away</div>{notes.text(m["takeaway"])}</div></section>')


def _coverage(d: dict) -> str:
    s = d["scope"]
    maps = ", ".join(fmt.map_name(x) for x in s["maps"])
    return (f'<div class="coverage"><span><b>{s["demos"]}</b> games</span><span><b>{s["rounds"]}</b> rounds</span>'
            f'<span><b>{len(s["maps"])}</b> maps ({esc(maps)})</span><span>Complete for this study</span></div>')


def _summary(s: dict) -> str:
    def sec(title, items):
        if not items:
            return ""
        return f'<div class="eyebrow">{esc(title)}</div><ul>{"".join(f"<li>{esc(i)}</li>" for i in items)}</ul>'
    inner = sec("What we covered", s.get("covered")) + sec("Keep an eye on", s.get("watch")) + sec("Re-check next time", s.get("retest"))
    return f'<section class="summary"><h2>Summary</h2>{inner}</section>' if inner else ""


def _player_study(plan: dict, d: dict, ctx: Ctx) -> str:
    notes = _Notes(plan.get("notes", {}))
    rep = plan.get("report", {})
    name = esc(d["subject"].get("name") or rep.get("player") or "Player")
    agenda = notes.text(plan["agenda"])
    moments = "".join(_moment(m, ctx, notes) for m in plan["moments"])
    head = (f'<div class="header"><div class="eyebrow">Player Study</div><h1>{name}</h1>'
            f'<div class="sub">{esc(rep.get("subtitle", ""))}</div></div>')
    return (f'{_coverage(d)}{head}<section class="agenda"><div class="label">What this study covers</div>{agenda}</section>'
            f'{moments}{_summary(plan.get("summary", {}))}{notes.list_html()}')


def _c(v):
    return "" if v is None else f"{v:,}"


def _fmt_metric_val(m):
    v = m["value"]
    if v is None:
        return "Unknown"
    if m["unit"] == "share":
        return f"{v * 100:.1f}%"
    if m["unit"] == "kd_ratio":
        return f"{v:.3f}"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.2f}"
    return f"{int(v):,}"


def _analyst_desk(plan: dict, d: dict) -> str:
    s = d["scope"]
    demo_rows = "".join(f'<tr><td><code>{esc(x["demo_id"])}</code></td><td>{esc(fmt.map_name(x["map"]))}</td><td class="num">{x["rounds"]}</td></tr>' for x in d["demos"])
    mrows = "".join(
        f'<tr><td>{esc(m["label"])}<br><span class="muted small">{esc(m["definition"])}</span></td>'
        f'<td class="num">{esc(_fmt_metric_val(m))}</td>'
        f'<td class="num">{_c(m["numerator"])}</td>'
        f'<td class="num">{_c(m["denominator"])}</td>'
        f'<td>{esc(m["scope"])}</td><td><code>{esc(k)}</code></td></tr>' for k, m in d["metrics"].items())
    def n(v, f="{:.2f}"):
        return "Unknown" if v is None else f.format(v)
    maprows = "".join(
        f'<tr><td>{esc(fmt.map_name(x["map"]))}</td><td class="num">{x["rounds"]}</td><td class="num">{x["wins"]}</td>'
        f'<td class="num">{x["kills"]}</td><td class="num">{x["deaths"]}</td><td class="num">{n(x["kd"])}</td>'
        f'<td class="num">{n(x["adr"], "{:.1f}")}</td><td class="num">{x["opening_kills"]}</td><td class="num">{x["opening_deaths"]}</td>'
        f'<td class="num">{n(x["enemy_utility_damage_per_round"])}</td></tr>' for x in d["per_map"])
    siderows = "".join(f'<tr><td>{esc(x["side"])}</td><td class="num">{x["rounds"]}</td><td class="num">{x["wins"]}</td><td class="num">{x["kills"]}</td><td class="num">{x["deaths"]}</td></tr>' for x in d["per_side"])
    findings = ""
    for m in plan["moments"]:
        a = m.get("analyst", {})
        if not a:
            continue
        li = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)  # noqa: E731
        findings += (f'<div class="finding"><h3>{esc(m["title"])} <span class="pill">{esc(m["intent"])}</span></h3>'
                     + (f'<div class="eyebrow">Other explanations</div><ul>{li(a["alternatives"])}</ul>' if a.get("alternatives") else "")
                     + (f'<div class="eyebrow">Limits</div><ul>{li(a["limitations"])}</ul>' if a.get("limitations") else "") + "</div>")
    oq = plan.get("analyst", {}).get("open_questions", [])
    open_q = f'<div class="desk-sec"><h2>Open questions</h2><ul>{"".join(f"<li>{esc(q)}</li>" for q in oq)}</ul></div>' if oq else ""
    return f'''
<div class="header"><div class="eyebrow">Analyst Desk</div><h1>{esc(d["subject"].get("name") or "Player")}</h1>
<div class="sub">Every figure, how it was built, and what it cannot tell us.</div></div>
<div class="desk-sec"><h2>Scope</h2><p>{s["demos"]} games, {s["rounds"]} rounds. Only games that passed the integrity check are used.</p>
<details class="disc"><summary>Show the {s["demos"]} games</summary><table><thead><tr><th>Game</th><th>Map</th><th class="num">Rounds</th></tr></thead><tbody>{demo_rows}</tbody></table></details></div>
<div class="desk-sec"><h2>All figures</h2><table><thead><tr><th>Measure</th><th class="num">Value</th><th class="num">Count</th><th class="num">Out of</th><th>Scope</th><th>Id</th></tr></thead><tbody>{mrows}</tbody></table></div>
<div class="desk-sec"><h2>By map</h2><table><thead><tr><th>Map</th><th class="num">Rounds</th><th class="num">Won</th><th class="num">Kills</th><th class="num">Deaths</th><th class="num">K/D</th><th class="num">Damage/rd</th><th class="num">Open kills</th><th class="num">Open deaths</th><th class="num">Grenade dmg/rd</th></tr></thead><tbody>{maprows}</tbody></table></div>
<div class="desk-sec"><h2>By side</h2><table><thead><tr><th>Side</th><th class="num">Rounds</th><th class="num">Won</th><th class="num">Kills</th><th class="num">Deaths</th></tr></thead><tbody>{siderows}</tbody></table></div>
<div class="desk-sec"><h2>Findings: other explanations and limits</h2>{findings or '<p class="muted">None recorded.</p>'}</div>
{open_q}
<div class="desk-sec"><h2>How to read these figures</h2><ul>
<li>A missing value is shown as <b>Unknown</b>, never as zero.</li>
<li>Kills and deaths include any kill that lands just after the round-end tick, matching the scoreboard.</li>
<li>Speed figures are game units per second. Kill speed is measured when this player first fired; death speed when the enemy first fired, so the two are measured at different moments.</li>
<li>Examples show what a pattern looks like. They do not show how often it happens.</li></ul></div>'''


def _data_link(label: str, obj: dict, filename: str) -> str:
    b = base64.b64encode(json.dumps(obj, indent=2, default=str).encode()).decode()
    return f'<a download="{esc(filename)}" href="data:application/json;base64,{b}">{esc(label)}</a>'


_JS = """
document.querySelectorAll('.tab-btn').forEach(function(b){b.addEventListener('click',function(){
 document.querySelectorAll('.tab-btn').forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false')});
 document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.toggle('active',p.id===b.dataset.target)});
 window.scrollTo(0,0);});});
"""


def build_report(plan: dict, digest: dict, *, batch_dir, steamid) -> str:
    """Validate the plan against the digest, then render the whole report as one HTML string."""
    ctx = Ctx(digest=digest, batch_dir=Path(batch_dir), steamid=int(steamid))
    validate_plan(plan, ctx)
    name = digest["subject"].get("name") or "Player"
    player = _player_study(plan, digest, ctx)
    desk = _analyst_desk(plan, digest)
    footer = (f'<div class="footer">Downloads: {_data_link("evidence digest (JSON)", digest, "evidence_digest.json")} · '
              f'{_data_link("coach plan (JSON)", plan, "coach_plan.json")}<br>'
              'Every figure in this report was calculated by software from the analyzed demo files. '
              'The coach wrote the explanations and chose what to show.</div>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)} – Player Study</title><style>{CSS}</style></head><body>
<nav class="folder-tabs" role="tablist"><button class="tab-btn" role="tab" aria-selected="true" data-target="tab-study">Player Study</button>
<button class="tab-btn" role="tab" aria-selected="false" data-target="tab-desk">Analyst Desk</button></nav>
<div class="wrap"><div class="tab-panel active" id="tab-study">{player}</div>
<div class="tab-panel" id="tab-desk">{desk}</div>{footer}</div><script>{_JS}</script></body></html>'''
