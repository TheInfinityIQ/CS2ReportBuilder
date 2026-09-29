"""Analyst findings from the fight table: where and in what situations a player wins or loses
fights, compared with a stated baseline. Every comparison is kept, including "no difference".

Baseline (ADR-013): the other players in the player's own matches, and the player's own level.
Nothing outside the batch is ever used; the finished product will not have a database.

Two questions per situation (a "cell", e.g. "you were moving when the fight started"):

- RESULT: of the fights decided in this situation (someone died), how many did the player win?
  Compared with (a) the other players in the same matches (lobby peers) in the same situation, and
  (b) the player's own usual level: the population rate shifted by the player's overall edge.
  (b) is the coaching question, "where do you play below yourself?".
- HABIT: how often the player's fights happen in this situation, compared with everyone else.

Statistics: exact binomial test against the baseline rate; Benjamini-Hochberg false-discovery
control across every test run for the player; split-half check (odd vs even games must point
the same way). Status:
  credible      FDR q < 0.10 and both halves agree
  leaning       p < 0.05 but not credible
  no_difference enough fights (>= 40) and p >= 0.30: a real null result
  too_few       fewer than 20 fights
  unclear       everything else
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import binomtest

MIN_N = 20
PROFILE_ONLY = {"s_map", "s_side"}  # map pool and side split are context, not habits
HABIT_MIN = 15  # a habit needs at least this many fights (observed or expected) in the cell
NULL_N = 40
Q = 0.10


def family(source: str | None) -> str:
    s = str(source or "").lower()
    return "tournament" if "tournament" in s or "hltv" in s else "pug"


def add_situations(f: pd.DataFrame) -> pd.DataFrame:
    """Plain-language situation labels for every fight row."""
    f = f.copy()
    f["family"] = f["source"].map(family)
    f["s_initiative"] = np.where(f.initiative, "you hit first", "they hit first")
    f["s_movement"] = pd.cut(f.my_speed, [-1, 40, 130, 1e9], labels=["standing still", "moving slowly", "running"]).astype(str)
    f["s_opp_movement"] = pd.cut(f.opp_speed, [-1, 40, 130, 1e9], labels=["enemy still", "enemy moving slowly", "enemy running"]).astype(str)
    f["s_distance"] = pd.cut(f.distance, [-1, 600, 1400, 1e9], labels=["close range", "mid range", "long range"]).astype(str)
    f["s_health"] = pd.cut(f.my_hp, [-1, 49, 99, 100], labels=["under 50 health", "damaged (50-99)", "full health"]).astype(str)
    diff = f.alive_me - f.alive_opp
    f["s_numbers"] = np.select([diff > 0, diff < 0], ["your team up players", "your team down players"], "even numbers")
    f["s_phase"] = np.where(f.post_plant, "after the plant",
                            pd.cut(f.round_time_s, [-1, 25, 60, 1e9], labels=["first 25 s", "25-60 s", "after 60 s"]).astype(str))
    gap = f.opp_equip - f.my_equip
    f["s_equipment"] = np.select([gap > 1500, gap < -1500], ["enemy better equipped", "you better equipped"], "similar equipment")
    f["s_weapon"] = f.my_weapon
    f["s_matchup"] = f.my_weapon + " vs " + f.opp_weapon
    f["s_side"] = f.side.fillna("unknown")
    f["s_map"] = f["map"].astype(str).str.replace("de_", "", regex=False).str.title()
    f["s_place"] = f.s_map + " / " + f.s_side + " / " + f.place.fillna("unknown place").astype(str)
    f["s_init_move"] = f.s_initiative + ", " + f.s_movement
    for c in [c for c in f.columns if c.startswith("s_")]:
        f.loc[f[c].isin(["nan", "None"]), c] = "unknown"
    return f


DIMENSIONS = {
    "s_initiative": "Who landed damage first",
    "s_movement": "Your movement when the fight started",
    "s_opp_movement": "Enemy movement when the fight started",
    "s_init_move": "First damage and your movement",
    "s_distance": "Fight distance",
    "s_health": "Your health going in",
    "s_numbers": "Players alive",
    "s_phase": "Time in the round",
    "s_equipment": "Equipment",
    "s_weapon": "Your weapon",
    "s_matchup": "Weapon matchup",
    "s_side": "Side",
    "s_map": "Map",
    "s_place": "Where the fight started (your position)",
}


def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + math.exp(-x))


def _wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def _bh(ps):
    ps = np.asarray(ps, float)
    n = len(ps)
    order = np.argsort(ps)
    q = np.empty(n)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, ps[i] * n / rank)
        q[i] = prev
    return q


def analyse(fights: pd.DataFrame, steamid: int) -> dict:
    """Findings for one player. ``fights`` must contain the population (all players)."""
    f = add_situations(fights)
    me = f[f.steamid == steamid]
    if me.empty:
        return {"steamid": str(steamid), "findings": [], "baseline": {}}
    fam = me.family.mode().iloc[0]
    # ADR-013: the only baseline is the other players in the SAME matches (lobby peers, matched to
    # a similar skill by matchmaking) plus the player's own level. Never an outside database.
    demos = sorted(me.demo_id.unique())
    pop = f[f.demo_id.isin(demos) & (f.steamid != steamid)]
    half = {d: i % 2 for i, d in enumerate(demos)}
    me = me.assign(_half=me.demo_id.map(half))

    dec_me = me[me.outcome != "none"]
    dec_pop = pop[pop.outcome != "none"]
    my_rate = (dec_me.outcome == "win").mean()
    pop_rate = (dec_pop.outcome == "win").mean()
    lift = _logit(my_rate) - _logit(pop_rate)

    baseline = {
        "family": fam,
        "baseline": "other players in the same matches (lobby peers) and the player's own level",
        "peer_players": int(pop.steamid.nunique()),
        "matches": int(pop.demo_id.nunique()),
        "peer_fight_rows": int(len(pop) // 1),
        "subject_demos": len(demos),
        "subject_fights": int(len(me)),
        "subject_decided": int(len(dec_me)),
        "subject_win_rate": my_rate,
        "peer_win_rate": pop_rate,
        "subject_initiative_rate": float(me.initiative.mean()),
        "peer_initiative_rate": float(pop.initiative.mean()),
        "subject_no_death_share": float((me.outcome == "none").mean()),
        "peer_no_death_share": float((pop.outcome == "none").mean()),
        "overall_edge_logit": lift,
    }

    rows = []
    for dim, title in DIMENSIONS.items():
        pop_dec_rate = dec_pop.groupby(dim).outcome.agg(lambda s: (s == "win").mean())
        pop_share = pop[dim].value_counts(normalize=True)
        for cell, g in me.groupby(dim):
            if dim == "s_place":  # where you fight: compare within the same map and side, not across map pools
                mp_side = cell.rsplit(" / ", 1)[0]
                ref = pop[pop.s_place.str.startswith(mp_side + " / ")]
                mine = me[me.s_place.str.startswith(mp_side + " / ")]
                share_base, share_den = (ref.s_place == cell).mean() if len(ref) else None, len(mine)
            else:
                share_base, share_den = pop_share.get(cell), len(me)
            if cell == "unknown":
                continue
            gd = g[g.outcome != "none"]
            n, k = len(gd), int((gd.outcome == "win").sum())
            base = pop_dec_rate.get(cell)
            if base is not None and not pd.isna(base) and n:
                for kind, exp in (("result_vs_everyone", base), ("result_vs_own_level", _expit(_logit(base) + lift))):
                    rows.append(_cell(dim, title, cell, kind, k, n, exp, gd, g))
            if dim in PROFILE_ONLY:
                continue
            sh = share_base
            if sh is not None and max(len(g), sh * share_den) >= HABIT_MIN:
                rows.append(_cell(dim, title, cell, "habit", len(g), share_den, float(sh), g, g, share=True))
    tested = [r for r in rows if r["n"] >= MIN_N]
    if tested:
        for r, q in zip(tested, _bh([r["p"] for r in tested])):
            r["q"] = float(q)
    for r in rows:
        r["status"] = _status(r)
    return {"steamid": str(steamid), "baseline": baseline, "findings": rows}


def _cell(dim, title, cell, kind, k, n, exp, gd, g, share=False):
    p = binomtest(k, n, exp).pvalue if n else 1.0
    rate = k / n if n else None
    halves = []
    for h in (0, 1):
        if share:
            continue
        s = gd[gd._half == h]
        if len(s) >= 8:
            halves.append(((s.outcome == "win").mean() - exp))
    losses = gd[gd.outcome == "loss"] if not share else g.iloc[0:0]
    return {
        "dimension": dim, "dimension_label": title, "situation": cell, "kind": kind,
        "k": k, "n": n, "rate": rate, "baseline_rate": exp,
        "diff_pp": None if rate is None else (rate - exp) * 100,
        "fights_vs_baseline": None if share else k - exp * n,
        "ci": _wilson(k, n), "p": float(p), "q": None,
        "halves_agree": (len(halves) == 2 and np.sign(halves[0]) == np.sign(halves[1]) == np.sign(rate - exp)) if not share else None,
        "fights_total": len(g),
        "example_losses": [
            {"demo_id": r.demo_id, "round": int(r["round"]), "tick": int(r.start_tick)}
            for _, r in losses.sort_values("start_tick").head(6).iterrows()
        ],
    }


def _status(r):
    if r["n"] < MIN_N:
        return "too_few"
    q = r.get("q")
    stable = r["halves_agree"] if r["halves_agree"] is not None else True
    if q is not None and q < Q and stable:
        return "credible"
    if r["p"] < 0.05:
        return "leaning"
    if r["n"] >= NULL_N and r["p"] >= 0.30:
        return "no_difference"
    return "unclear"
