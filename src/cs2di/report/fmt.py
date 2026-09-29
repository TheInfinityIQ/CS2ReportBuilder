"""Plain-language formatting owned by the software (never by the AI)."""

from __future__ import annotations

import html
import re

WEAPONS = {
    "ak47": "AK-47", "m4a1_silencer": "M4A1-S", "m4a1": "M4A4", "awp": "AWP", "glock": "Glock-18",
    "usp_silencer": "USP-S", "hkp2000": "P2000", "deagle": "Desert Eagle", "galilar": "Galil AR",
    "famas": "FAMAS", "mac10": "MAC-10", "mp9": "MP9", "mp7": "MP7", "mp5sd": "MP5-SD", "ump45": "UMP-45",
    "p250": "P250", "fiveseven": "Five-SeveN", "tec9": "Tec-9", "cz75a": "CZ75-Auto", "elite": "Dual Berettas",
    "ssg08": "SSG 08", "sg556": "SG 553", "aug": "AUG", "nova": "Nova", "xm1014": "XM1014", "mag7": "MAG-7",
    "sawedoff": "Sawed-Off", "negev": "Negev", "m249": "M249", "bizon": "PP-Bizon", "p90": "P90",
    "g3sg1": "G3SG1", "scar20": "SCAR-20", "revolver": "R8 Revolver", "knife": "Knife", "taser": "Zeus x27",
    "hegrenade": "HE grenade", "inferno": "Fire", "molotov": "Molotov", "incgrenade": "Incendiary",
    "flashbang": "Flashbang", "smokegrenade": "Smoke", "planted_c4": "Bomb",
}

MAPS = {"de_dust2": "Dust2", "de_mirage": "Mirage", "de_inferno": "Inferno", "de_anubis": "Anubis",
        "de_cache": "Cache", "de_nuke": "Nuke", "de_overpass": "Overpass", "de_ancient": "Ancient",
        "de_vertigo": "Vertigo", "de_train": "Train"}


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def weapon(name) -> str:
    return WEAPONS.get(str(name), str(name).replace("_", " ").title())


def map_name(name) -> str:
    return MAPS.get(str(name), str(name).replace("de_", "").title())


def place(name) -> str:
    """CamelCase place names to words: TopofMid -> Top of Mid, LowerTunnel -> Lower Tunnel."""
    if not name or str(name) == "nan":
        return ""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(name))
    s = re.sub(r"\bof\b", "of", s)
    return s.replace("Topof", "Top of")


def clock(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def side_name(side) -> str:
    s = str(side).upper()
    return "T" if s.startswith("T") else "CT" if s.startswith("C") else s


def value_text(v, unit: str) -> str:
    """Plain figure for the player surface."""
    if v is None:
        return "Unknown"
    if unit == "share":
        return f"{v * 100:.0f}%"
    if unit == "kd_ratio":
        return f"{v:.2f}"
    if unit in ("damage_per_round", "units_per_second"):
        return f"{v:.0f}"
    if isinstance(v, float) and v.is_integer():
        return f"{int(v):,}"
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
