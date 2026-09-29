import numpy as np
import pandas as pd

from cs2di.fights import load_fights, weapon_class
from cs2di.findings import _bh, analyse


def test_weapon_display_and_event_names_agree():  # pitfall 24
    for a, b in [("AK-47", "ak47"), ("M4A1-S", "m4a1_silencer"), ("USP-S", "usp_silencer"), ("SSG 08", "ssg08"),
                 ("Desert Eagle", "deagle"), ("Glock-18", "glock"), ("CZ75-Auto", "cz75a"), ("PP-Bizon", "bizon")]:
        assert weapon_class(a) == weapon_class(b) != "other"
    assert weapon_class("Butterfly Knife") == "knife" and weapon_class("Smoke Grenade") == "utility"
    assert weapon_class(None) == "unknown"


def _fights(demo, n=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        a, b = 1 + i % 10, 11 + i % 10
        win = rng.random() < 0.5
        for me, opp, init, out in ((a, b, True, "win" if win else "loss"), (b, a, False, "loss" if win else "win")):
            rows.append({"demo_id": demo, "map": "de_mirage", "source": "faceit_sourcetv", "round": 1, "start_tick": 100 * i,
                         "steamid": me, "opponent": opp, "side": "T" if me < 11 else "CT", "outcome": out, "initiative": init,
                         "my_speed": 10.0, "opp_speed": 200.0, "distance": 500.0, "my_hp": 100, "opp_hp": 100,
                         "my_weapon": "rifle", "opp_weapon": "rifle", "my_equip": 4000, "opp_equip": 4000, "place": "Mid",
                         "alive_me": 5, "alive_opp": 5, "round_time_s": 30.0, "post_plant": False})
    return pd.DataFrame(rows)


def test_same_match_in_two_batches_is_kept_once(tmp_path):  # pitfall 28
    f = _fights("m1")
    for name in ("fights_a.csv.gz", "fights_b.csv.gz"):
        f.to_csv(tmp_path / name, index=False)
    _fights("m2", seed=1).assign(start_tick=lambda d: d.start_tick + 7).to_csv(tmp_path / "fights_c.csv.gz", index=False)
    out = load_fights(sorted(tmp_path.glob("*.csv.gz")))
    assert out.groupby(["batch", "demo_id"]).ngroups == 2 and len(out) == 2 * len(f)


def test_bh_is_monotone_and_bounded():
    q = _bh([0.001, 0.02, 0.03, 0.5])
    assert all(0 <= x <= 1 for x in q) and q[0] <= q[1] <= q[2] <= q[3]


def test_small_samples_are_never_findings():
    f = pd.concat([_fights(f"d{i}", seed=i).assign(start_tick=lambda d, i=i: d.start_tick + i) for i in range(3)])
    r = analyse(f, 1)
    small = [x for x in r["findings"] if x["n"] < 20]
    assert small and all(x["status"] == "too_few" for x in small)
    assert r["baseline"]["family"] == "pug"
