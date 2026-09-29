"""Assemble the single-file report: Player Study tab + Analyst Desk tab, styled only by theme.py."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from . import fmt
from .fmt import esc
from .modules import STATUS_WORDS, Ctx, pfmt, render_module
from .plan import validate_plan
from .theme import CSS
from .viewer import maps_script
from .weapons import assert_all_mapped

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
            f'<span><b>{len(s["maps"])}</b> maps ({esc(maps)})</span><span>{s["demos"]}/{s["demos"]} demos passed the integrity check</span></div>')


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
    moments_section = f'<div id="moments-wrap"><div id="moments-list">{moments}</div></div>'
    return (f'{_coverage(d)}{head}<section class="agenda"><div class="label">What this study covers</div>{agenda}</section>'
            f'{moments_section}{_summary(plan.get("summary", {}))}{notes.list_html()}')


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


def _analyst_desk(plan: dict, d: dict, an: dict | None = None) -> str:
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
{_findings_desk(an)}
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


KIND_WORDS = {
    "result_vs_everyone": "Fights won, compared with players in your games",
    "result_vs_own_level": "Fights won, compared with your own usual level",
    "habit": "How often your fights happen in this situation",
    "rate_vs_peers": "Compared with players in your games",
    "mean_vs_peers": "Average, compared with players in your games",
}
CHIP = {"credible": "Supported", "leaning": "Possible", "no_difference": "No detectable difference", "unclear": "Unclear", "too_few": "Too few"}
ORDER = {"credible": 0, "leaning": 1, "no_difference": 2, "unclear": 3, "too_few": 4}


def _fv(f, v):
    if v is None:
        return "Unknown"
    return f"{v * 100:+.1f} pts" if f.get("unit") == "win_points" else f"{v * 100:.1f}%"


def _frow(f):
    cnt = f"{f['k']:,}/{f['n']:,}" if f.get("k") is not None else f"n={f['n']:,}"
    diff = "" if f.get("diff_pp") is None else f"{f['diff_pp']:+.1f}"
    q = pfmt(f.get("q"))
    halves = {True: "agree", False: "disagree", None: ""}[f.get("halves_agree")]
    ex = len(f.get("examples") or [])
    return (f'<tr><td>{esc(f["situation"])}</td><td class="num">{esc(_fv(f, f.get("rate")))}<br><span class="muted small">{cnt}</span></td>'
            f'<td class="num">{esc(_fv(f, f.get("baseline_rate")))}</td><td class="num">{diff}</td>'
            f'<td><span class="chip {esc(f["status"])}" title="{esc(STATUS_WORDS[f["status"]])}">{CHIP[f["status"]]}</span></td>'
            f'<td class="num small">{pfmt(f["p"])}</td><td class="num small">{q}</td><td class="small">{halves}</td>'
            f'<td class="small"><code>{esc(f["id"])}</code>{" · " + str(ex) + " examples" if ex else ""}</td></tr>')


def _ftable(rows):
    head = ('<thead><tr><th>Situation</th><th class="num">You</th><th class="num">Players in your games</th><th class="num">Diff (pts)</th>'
            '<th>Verdict</th><th class="num">p</th><th class="num">q</th><th>Halves</th><th>Id</th></tr></thead>')
    return f'<table>{head}<tbody>{"".join(_frow(f) for f in rows)}</tbody></table>'


def _findings_desk(an: dict | None) -> str:
    if not an:
        return ""
    b = an["baseline"]
    F = an["findings"]
    counts = {k: sum(1 for f in F if f["status"] == k) for k in CHIP}
    out = [f'''<div class="desk-sec"><h2>Findings</h2>
<p>Baseline: the other {b["peer_players"]} players in the same {b["matches"]} matches (similar level by matchmaking), and your own usual level.
No outside database is used. You were in {b["subject_fights"]:,} fights; {b["subject_decided"]:,} ended with one of you dead.
You won {b["subject_win_rate"] * 100:.1f}% of those; players in your games won {b["peer_win_rate"] * 100:.1f}%.</p>
<p class="small">{len(F)} comparisons: {counts["credible"]} supported, {counts["leaning"]} possible, {counts["no_difference"]} with no detectable difference,
{counts["unclear"]} unclear, {counts["too_few"]} with too few cases. "Supported" means it survives a correction for running this many checks (false-discovery rate under 10%) and both interleaved splits of your games (alternate games in date order, not early versus late) point the same way; results just under the threshold are still exploratory. "No detectable difference" (at least 40 cases, p at least 0.30) does not prove the two are equal; it is kept so the coach does not chase it. Tests treat each event as independent (not yet clustered by match), so borderline results deserve caution. Counts differ from the scoreboard figures because these analyses leave out kills and deaths after the round was decided and deaths to the bomb or world.</p></div>''']
    topics = [("value", "Value of kills and deaths"), ("trading", "Trading and spacing"), ("clutch", "Clutches")]
    for t, title in topics:
        rows = sorted([f for f in F if f["topic"] == t], key=lambda f: ORDER[f["status"]])
        if rows:
            out.append(f'<div class="desk-sec"><h2>{esc(title)}</h2>{_ftable(rows)}</div>')
    fights = [f for f in F if f["topic"] == "fights"]
    for kind, title in (("result_vs_everyone", "Fights won, by situation (vs players in your games)"),
                        ("result_vs_own_level", "Fights won, by situation (vs your own usual level)"),
                        ("habit", "Profile: where and how your fights happen")):
        rows = [f for f in fights if f["kind"] == kind]
        shown = sorted([f for f in rows if f["status"] != "too_few"], key=lambda f: (ORDER[f["status"]], f["p"]))
        few = [f for f in rows if f["status"] == "too_few"]
        body = _ftable(shown)
        if few:
            body += f'<details class="disc"><summary>{len(few)} situations with too few fights to judge</summary><div class="disc-body">{_ftable(few)}</div></details>'
        out.append(f'<div class="desk-sec"><h2>{esc(title)}</h2>{body}</div>')
    return "".join(out)


def _data_link(label: str, obj: dict, filename: str) -> str:
    b = base64.b64encode(json.dumps(obj, indent=2, default=str).encode()).decode()
    return f'<a download="{esc(filename)}" href="data:application/json;base64,{b}">{esc(label)}</a>'


_JS = """
document.querySelectorAll('.tab-btn').forEach(function(b){b.addEventListener('click',function(){
 document.querySelectorAll('.tab-btn').forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false')});
 document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.toggle('active',p.id===b.dataset.target)});
 window.scrollTo(0,0);});});
/* accordion: close siblings when one km-drawer opens */
document.querySelectorAll('.km-accordion').forEach(function(acc){
 acc.querySelectorAll('.km-drawer').forEach(function(d){
   d.addEventListener('toggle',function(){
     if(d.open) acc.querySelectorAll('.km-drawer').forEach(function(s){if(s!==d) s.open=false;});
   });
 });
});
/* local filters: each replay set has its own bar (.km-filters) and only filters its own drawers */
document.querySelectorAll('.mod').forEach(function(mod){
 var bar=mod.querySelector('.km-filters'); if(!bar) return;
 var items=Array.from(mod.querySelectorAll('.km-drawer')), empty=mod.querySelector('.km-empty'), reset=bar.querySelector('[data-reset]');
 var st={o:null,m:null};
 function apply(){
  var shown=0;
  items.forEach(function(d){var ok=(!st.o||d.dataset.outcome===st.o)&&(!st.m||d.dataset.map===st.m); d.hidden=!ok; if(ok) shown++;});
  bar.querySelectorAll('[data-fo],[data-fm]').forEach(function(b){b.setAttribute('aria-pressed',String((b.dataset.fo&&b.dataset.fo===st.o)||(b.dataset.fm&&b.dataset.fm===st.m)));});
  if(reset) reset.hidden=!(st.o||st.m);
  if(empty) empty.hidden=shown>0;
  var open=items.filter(function(d){return !d.hidden;});
  if(open.length&&!open.some(function(d){return d.open;})) open[0].open=true;
 }
 bar.addEventListener('click',function(e){var b=e.target.closest('button'); if(!b) return;
  if(b.dataset.reset){st.o=null;st.m=null;}
  else if(b.dataset.fo){st.o=st.o===b.dataset.fo?null:b.dataset.fo;}
  else if(b.dataset.fm){st.m=st.m===b.dataset.fm?null:b.dataset.fm;}
  apply();});
});
"""


def build_report(plan: dict, digest: dict, *, batch_dir, steamid, analysis: dict | None = None) -> str:
    """Validate the plan against the digest and findings, then render the report as one HTML string."""
    ctx = Ctx(digest=digest, batch_dir=Path(batch_dir), steamid=int(steamid), analysis=analysis)
    validate_plan(plan, ctx)
    name = digest["subject"].get("name") or "Player"
    player = _player_study(plan, digest, ctx)
    assert_all_mapped()  # an unknown weapon/item name must fail the build, not draw the wrong icon
    desk = _analyst_desk(plan, digest, analysis)
    desk = desk.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")  # phones scroll tables, not the page
    footer = (f'<div class="footer">Downloads: {_data_link("evidence digest (JSON)", digest, "evidence_digest.json")} · '
              f'{_data_link("coach plan (JSON)", plan, "coach_plan.json")}{(" · " + _data_link("all findings (JSON)", analysis, "findings.json")) if analysis else ""}<br>'
              'Every figure in this report was calculated by software from the analyzed demo files. '
              'The coach wrote the explanations and chose what to show.</div>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)} – Player Study</title><style>{CSS}</style></head><body>
<nav class="folder-tabs" role="tablist"><button class="tab-btn" role="tab" aria-selected="true" data-target="tab-study">Player Study</button>
<button class="tab-btn" role="tab" aria-selected="false" data-target="tab-desk">Analyst Desk</button></nav>
<div class="wrap"><div class="tab-panel active" id="tab-study">{player}</div>
<div class="tab-panel" id="tab-desk">{desk}</div>{footer}</div><script>{_JS}</script>{maps_script(ctx.maps)}</body></html>'''
