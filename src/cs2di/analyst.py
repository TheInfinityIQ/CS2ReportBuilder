"""The Analyst: every finding for one player from one batch, against lobby peers and own level.

Combines fight-situation findings (findings.py) with round-impact findings (impact.py), then runs
one false-discovery control over all of them so the number of tests can't manufacture a result.
Each finding carries example rounds so the coach can show moments, not just numbers.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import binomtest, ttest_ind

from .findings import MIN_N, NULL_N, Q, _bh, _wilson, analyse

TOPICS = {
    "fights": "Fights",
    "value": "Value of kills and deaths",
    "trading": "Trading and spacing",
    "clutch": "Clutches",
}


def _half_map(demos):
    return {d: i % 2 for i, d in enumerate(sorted(demos))}


def _rate(fid, topic, label, plain, me, peers, flag, examples=None, higher_is_good=True, unit="share"):
    """Binomial comparison of a yes/no event: player's rate vs pooled lobby-peer rate."""
    n, k = len(me), int(me[flag].sum())
    base = float(peers[flag].mean()) if len(peers) else None
    p = binomtest(k, n, base).pvalue if n and base not in (None, 0.0, 1.0) else 1.0
    halves = []
    for h in (0, 1):
        s = me[me._half == h]
        if len(s) >= 8 and base is not None:
            halves.append(s[flag].mean() - base)
    rate = k / n if n else None
    return {
        "id": fid, "topic": topic, "dimension_label": TOPICS[topic], "situation": label, "plain": plain,
        "kind": "rate_vs_peers", "k": k, "n": n, "rate": rate, "baseline_rate": base,
        "diff_pp": None if rate is None or base is None else (rate - base) * 100,
        "fights_vs_baseline": None if base is None else k - base * n, "ci": _wilson(k, n), "p": float(p), "q": None,
        "halves_agree": len(halves) == 2 and rate is not None and np.sign(halves[0]) == np.sign(halves[1]) == np.sign(rate - base),
        "higher_is_good": higher_is_good, "unit": unit, "examples": examples or [],
    }


def _mean(fid, topic, label, plain, me, peers, col, examples=None, higher_is_good=True, unit="points"):
    a, b = me[col].dropna(), peers[col].dropna()
    p = float(ttest_ind(a, b, equal_var=False).pvalue) if len(a) > 2 and len(b) > 2 else 1.0
    halves = [me[me._half == h][col].mean() - b.mean() for h in (0, 1) if (me._half == h).sum() >= 8]
    d = a.mean() - b.mean() if len(a) and len(b) else None
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) if len(a) > 2 and len(b) > 2 else None
    return {
        "id": fid, "topic": topic, "dimension_label": TOPICS[topic], "situation": label, "plain": plain,
        "kind": "mean_vs_peers", "k": None, "n": len(a), "rate": float(a.mean()) if len(a) else None,
        "baseline_rate": float(b.mean()) if len(b) else None, "diff_pp": None if d is None else d * 100,
        "fights_vs_baseline": None if d is None else d * len(a),
        "ci": (None, None) if se is None else (d - 1.96 * se, d + 1.96 * se), "p": p if not math.isnan(p) else 1.0,
        "q": None, "halves_agree": len(halves) == 2 and d is not None and np.sign(halves[0]) == np.sign(halves[1]) == np.sign(d),
        "higher_is_good": higher_is_good, "unit": unit, "examples": examples or [],
    }


def _ex(df, why, n=6):
    cols = [c for c in ("demo_id", "map", "round", "tick", "round_time_s", "swing", "own_alive", "opp_alive",
                        "teammate_distance", "round_won", "vs") if c in df.columns]
    out = []
    for _, r in df.head(n).iterrows():
        e = {c: (None if pd.isna(r[c]) else (r[c].item() if hasattr(r[c], "item") else r[c])) for c in cols}
        e["why"] = why
        out.append(e)
    return out


def impact_findings(imp: dict, steamid: int) -> list[dict]:
    K, D, C, L = (imp[k].copy() for k in ("kills", "deaths", "trade_chances", "clutches"))
    demos = sorted(set(D[D.steamid == steamid].demo_id) | set(K[K.steamid == steamid].demo_id))
    half = _half_map(demos)
    K, D, C, L = (x[x.demo_id.isin(demos)].assign(_half=lambda z: z.demo_id.map(half)) for x in (K, D, C, L))
    live_d = D[~D.after_round_end]
    pvp_d = live_d[live_d.pvp]
    live_k = K[~K.after_round_end]
    mk, pk = live_k[live_k.steamid == steamid], live_k[live_k.steamid != steamid]
    md, pd_ = pvp_d[pvp_d.steamid == steamid], pvp_d[pvp_d.steamid != steamid]
    mad, pad = live_d[live_d.steamid == steamid], live_d[live_d.steamid != steamid]
    rows = []
    rows.append(_mean("value.kill_swing", "value", "How much your kills changed the round",
                      "Average change in your team's chance to win the round from each of your kills.",
                      mk, pk, "swing", _ex(mk.sort_values("swing"), "your kills that changed the round least"), unit="win_points"))
    rows.append(_mean("value.death_swing", "value", "How much your deaths cost the round",
                      "Average change in your team's chance to win from each of your deaths (closer to zero is better).",
                      mad, pad, "swing", _ex(mad[mad.own_alive >= 2].sort_values("swing"), "your costliest deaths while teammates were alive"), unit="win_points"))
    rows.append(_rate("value.low_swing_kills", "value", "Kills that barely changed the round",
                      "Share of your kills that moved the round by under 5 win points, e.g. kills in rounds already decided.",
                      mk, pk, "low_swing", _ex(mk[mk.low_swing], "kill that barely changed the round"), higher_is_good=False))
    rows.append(_rate("value.first_death", "value", "Dying first",
                      "Share of your deaths that were the first death of the round.",
                      mad, pad, "first_death", _ex(mad[mad.first_death & ~mad.traded], "first death, not traded"), higher_is_good=False))
    rows.append(_rate("value.opening_kill", "value", "Opening kills",
                      "Share of your kills that were the first kill of the round.", mk, pk, "opening",
                      _ex(mk[mk.opening], "opening kill")))
    rows.append(_rate("value.died_ahead", "value", "Dying while your team had more players",
                      "Share of your deaths that happened while your team was up players (giving back an advantage).",
                      mad, pad, "team_ahead", _ex(mad[mad.team_ahead].sort_values("swing"), "died with the team ahead"), higher_is_good=False))
    rows.append(_rate("trading.traded", "trading", "Your deaths that got traded",
                      "Share of your deaths where a teammate killed your killer within 5 seconds.",
                      md, pd_, "traded", _ex(md[~md.traded].sort_values("swing"), "death not traded")))
    # only deaths where teammates were still alive and their positions are known
    def _with_mates(x):
        x = x[(x.own_alive >= 2) & x.teammate_distance.notna()]
        return x.assign(alone=x.teammate_distance > 900)
    mdm, pdm = _with_mates(md), _with_mates(pd_)
    rows.append(_rate("trading.alone", "trading", "Dying with no teammate close enough to trade",
                      "Of your deaths while teammates were still alive, the share where none of them was within about 900 units (walls ignored).",
                      mdm, pdm, "alone", _ex(mdm[mdm.alone].sort_values("swing"), "died with nobody near"), higher_is_good=False))
    mc, pc = C[C.steamid == steamid], C[C.steamid != steamid]
    rows.append(_rate("trading.converted", "trading", "Trading a teammate who died near you",
                      "When a teammate died within about 900 units of you, how often you killed their killer within 5 seconds.",
                      mc, pc, "traded_by_me", _ex(mc[~mc.traded_by_me], "teammate died near you, no trade")))
    ml, pl = L[L.steamid == steamid], L[L.steamid != steamid]
    if len(ml):
        exp = ml.vs.map(pl.groupby("vs").won.mean()).fillna(0.0)
        k, n = int(ml.won.sum()), len(ml)
        var = float((exp * (1 - exp)).sum())
        z = (k - exp.sum()) / math.sqrt(var) if var > 0 else 0.0
        p = float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))))
        rows.append({"id": "clutch.won", "topic": "clutch", "dimension_label": TOPICS["clutch"],
                     "situation": "Clutches won (last player alive)",
                     "plain": "Rounds won when you were the last one alive, against what lobby peers win from the same numbers.",
                     "kind": "rate_vs_peers", "k": k, "n": n, "rate": k / n, "baseline_rate": float(exp.mean()),
                     "diff_pp": (k / n - exp.mean()) * 100, "fights_vs_baseline": k - float(exp.sum()),
                     "ci": _wilson(k, n), "p": p, "q": None, "halves_agree": None, "higher_is_good": True, "unit": "share",
                     "examples": _ex(ml.sort_values("vs"), "clutch")})
    return rows


def player_analysis(fights: pd.DataFrame, imp: dict, steamid: int) -> dict:
    fa = analyse(fights, steamid)
    rows = []
    for r in fa["findings"]:
        r = dict(r)
        r["topic"] = "fights"
        r["id"] = f"fight.{r['kind']}.{r['dimension']}.{r['situation']}"
        r["plain"] = None
        r["higher_is_good"] = r["kind"] != "habit" and True
        r["examples"] = [{**e, "why": "fight lost in this situation"} for e in r.pop("example_losses", [])]
        rows.append(r)
    rows += impact_findings(imp, steamid)
    tested = [r for r in rows if r["n"] and r["n"] >= MIN_N]
    for r, q in zip(tested, _bh([r["p"] for r in tested])):
        r["q"] = float(q)
    for r in rows:
        r["status"] = _status(r)
    return {"steamid": str(steamid), "baseline": fa["baseline"], "findings": rows}


def _status(r):
    if not r["n"] or r["n"] < MIN_N:
        return "too_few"
    stable = r["halves_agree"] if r["halves_agree"] is not None else True
    if r["q"] is not None and r["q"] < Q and stable:
        return "credible"
    if r["p"] < 0.05:
        return "leaning"
    if r["n"] >= NULL_N and r["p"] >= 0.30:
        return "no_difference"
    return "unclear"


def jsonable(x):
    """Plain JSON types (numpy scalars, tuples, NaN -> None)."""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def analyse_batch(batch_dir, steamid) -> dict:
    """Full analyst run for one player on one batch (the only data the product has)."""
    from .fights import batch_fights
    from .ids import parse_steamid
    from .impact import batch_impact

    sid = parse_steamid(steamid)
    return jsonable(player_analysis(batch_fights(batch_dir), batch_impact(batch_dir), sid))
