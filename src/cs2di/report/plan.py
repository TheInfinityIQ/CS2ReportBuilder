"""Validate a coach's report plan before anything renders.

The plan is content only: words, and choices from the software's module list. It has no fields
for styling, HTML or raw numbers. Any number the coach writes in prose must exist in the digest.
"""

from __future__ import annotations

import re

from .modules import Ctx, ModuleError, check_module

INTENTS = {"ACTION", "UNDERSTAND", "REINFORCE", "WATCH"}
LAYOUTS = {"text_above", "side_by_side", "text_only", "module_only"}
TOP = {"report", "agenda", "moments", "summary", "notes", "analyst"}


class PlanError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(f"- {p}" for p in problems))


def _num_leaves(x, out: set):
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.add(round(float(x), 2))
        out.add(float(round(x)))
        out.add(round(float(x) * 100))
        out.add(round(float(x) * 100, 1))
    elif isinstance(x, dict):
        for v in x.values():
            _num_leaves(v, out)
    elif isinstance(x, list):
        for v in x:
            _num_leaves(v, out)


# Fixed game facts a coach may cite (never player data): full rifle run speed in units per second.
GAME_CONSTANTS = {215.0}


def allowed_numbers(digest: dict, analysis: dict | None = None) -> set:
    out: set = set(GAME_CONSTANTS)
    for f in (analysis or {}).get("findings", []):
        if f.get("status") in ("credible", "leaning", "no_difference"):
            _num_leaves({k: f.get(k) for k in ("k", "n", "rate", "baseline_rate")}, out)
            if f.get("diff_pp") is not None:
                out.add(float(round(abs(f["diff_pp"]))))
    _num_leaves((analysis or {}).get("baseline", {}), out)
    _num_leaves(digest.get("metrics", {}), out)
    _num_leaves(digest.get("per_map", []), out)
    _num_leaves(digest.get("per_side", []), out)
    _num_leaves(digest.get("scope", {}), out)
    return out


_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(%?)")
_SKIP = re.compile(r"(?:round|rounds|r)\s*\d+|\d+:\d\d", re.I)


def stray_numbers(text: str, allowed: set) -> list[str]:
    """Numbers in prose (>=10, decimals or percentages) that are not in the digest."""
    text = _SKIP.sub(" ", text)
    bad = []
    for m in _NUM.finditer(text):
        raw = m.group(1).replace(",", "")
        val = float(raw)
        pct = bool(m.group(2))
        if val < 10 and not pct and "." not in raw:
            continue
        if val in allowed or round(val) in allowed:
            continue
        bad.append(m.group(0))
    return bad


def _texts(plan: dict):
    yield "agenda", plan.get("agenda", "")
    for i, m in enumerate(plan.get("moments", [])):
        w = f"moments[{i}]"
        for k in ("title", "question", "takeaway"):
            yield f"{w}.{k}", m.get(k, "")
        for j, b in enumerate(m.get("blocks", [])):
            yield f"{w}.blocks[{j}].text", b.get("text", "")
            mod = b.get("module") if isinstance(b, dict) else None
            if isinstance(mod, dict):
                for x, pk in enumerate(mod.get("picks", []) if isinstance(mod.get("picks"), list) else []):
                    if isinstance(pk, dict):
                        yield f"{w}.blocks[{j}].module.picks[{x}].note", pk.get("note", "")
        a = m.get("analyst", {})
        for k in ("alternatives", "limitations"):
            for j, t in enumerate(a.get(k, [])):
                yield f"{w}.analyst.{k}[{j}]", t
    s = plan.get("summary", {})
    for k in ("covered", "watch", "retest"):
        for j, t in enumerate(s.get(k, [])):
            yield f"summary.{k}[{j}]", t
    for k, t in plan.get("notes", {}).items():
        yield f"notes.{k}", t
    for j, t in enumerate(plan.get("analyst", {}).get("open_questions", [])):
        yield f"analyst.open_questions[{j}]", t


def validate_plan(plan: dict, ctx: Ctx) -> None:
    """Raise PlanError listing every problem found (not just the first)."""
    p: list[str] = []
    if not isinstance(plan, dict):
        raise PlanError(["plan must be a JSON object"])
    extra = set(plan) - TOP
    if extra:
        p.append(f"unexpected top-level field(s) {sorted(extra)} (allowed: {sorted(TOP)})")
    if not isinstance(plan.get("agenda"), str) or not plan.get("agenda", "").strip():
        p.append("agenda is required (a short coach-written preview)")
    moments = plan.get("moments")
    if not isinstance(moments, list) or not moments:
        p.append("moments is required and needs at least one Teaching Moment")
        moments = []
    notes = plan.get("notes", {})
    if not isinstance(notes, dict):
        p.append("notes must be an object of key -> text")
        notes = {}
    used_notes: set = set()
    ids: set = set()
    for i, m in enumerate(moments):
        w = f"moments[{i}]"
        if not isinstance(m, dict):
            p.append(f"{w} must be an object")
            continue
        bad = set(m) - {"id", "intent", "title", "question", "blocks", "takeaway", "analyst"}
        if bad:
            p.append(f"{w}: unexpected field(s) {sorted(bad)}")
        if m.get("id") in ids:
            p.append(f"{w}: duplicate id '{m.get('id')}'")
        ids.add(m.get("id"))
        if m.get("intent") not in INTENTS:
            p.append(f"{w}: intent must be one of {sorted(INTENTS)}")
        for k in ("title", "question", "takeaway"):
            if not isinstance(m.get(k), str) or not m.get(k).strip():
                p.append(f"{w}: '{k}' is required")
        blocks = m.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            p.append(f"{w}: needs at least one block")
            continue
        for j, b in enumerate(blocks):
            bw = f"{w}.blocks[{j}]"
            if not isinstance(b, dict):
                p.append(f"{bw} must be an object")
                continue
            bad = set(b) - {"layout", "text", "module"}
            if bad:
                p.append(f"{bw}: unexpected field(s) {sorted(bad)} (styling is not the coach's job)")
            lay = b.get("layout")
            if lay not in LAYOUTS:
                p.append(f"{bw}: layout must be one of {sorted(LAYOUTS)}")
            has_t, has_m = bool(str(b.get("text", "")).strip()), "module" in b
            if lay in ("text_above", "side_by_side") and not (has_t and has_m):
                p.append(f"{bw}: layout '{lay}' needs both text and module")
            if lay == "text_only" and (not has_t or has_m):
                p.append(f"{bw}: layout 'text_only' needs text and no module")
            if lay == "module_only" and (not has_m or has_t):
                p.append(f"{bw}: layout 'module_only' needs a module and no text")
            if has_m:
                try:
                    check_module(b["module"], ctx, f"{bw}.module")
                except (ModuleError, KeyError) as e:
                    p.append(str(e))
            used_notes |= set(re.findall(r"\[\[note:([\w-]+)\]\]", str(b.get("text", ""))))
        used_notes |= set(re.findall(r"\[\[note:([\w-]+)\]\]", str(m.get("takeaway", ""))))
    for k in used_notes - set(notes):
        p.append(f"a text refers to note '{k}' which is not defined in notes")
    allowed = allowed_numbers(ctx.digest, ctx.analysis)
    for where, text in _texts(plan):
        if isinstance(text, str):
            bad = stray_numbers(text, allowed)
            if bad:
                p.append(f"{where}: number(s) {bad} are not in the evidence digest or findings; show numbers with a block instead")
    if p:
        raise PlanError(p)
