"""Effective health damage from ``player_hurt`` rows.

``player_hurt.health`` is the victim's health AFTER the hit and the extractor's event-time
``user_health`` is the health at the start of the tick. When one victim takes several hits
on the same tick, every row shares that start-of-tick ``user_health``, so the legacy
``dmg_health_capped = user_health - health`` counts earlier same-tick damage again.

Health never goes up within a tick, so ordering the victim's same-tick rows by remaining
health (highest first) recovers the hit order: each hit starts where the previous one left
off. Single-hit ticks are unchanged. Unknown inputs stay unknown (NaN), never zero.

The extractor (v7.8+) carries an identical copy of ``effective_damage``; a test checks the
two agree.
"""

from __future__ import annotations

import pandas as pd

KEYS = ["user_steamid", "tick"]


def effective_damage(h: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (effective damage, same-tick-multi flag), aligned to ``h.index``."""
    if h.empty or not {"user_health", "health", *KEYS}.issubset(h.columns):
        nan = pd.Series(float("nan"), index=h.index)
        return nan, pd.Series(False, index=h.index)
    pre = pd.to_numeric(h["user_health"], errors="coerce")
    post = pd.to_numeric(h["health"], errors="coerce")
    w = pd.DataFrame({"u": h["user_steamid"], "t": h["tick"], "pre": pre, "post": post})
    w = w.sort_values(["u", "t", "post"], ascending=[True, True, False], kind="mergesort")
    g = w.groupby(["u", "t"], dropna=False, sort=False)
    known = w["u"].notna()  # an unidentified victim cannot be chained to another row
    prev = g["post"].shift(1).where(known)
    start = prev.where(prev.notna(), w["pre"])
    eff = (start - w["post"]).clip(lower=0)
    multi = (g["post"].transform("size") > 1) & known
    return eff.reindex(h.index), multi.reindex(h.index).fillna(False).astype(bool)
