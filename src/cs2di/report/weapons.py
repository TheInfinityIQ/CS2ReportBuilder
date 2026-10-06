"""Validate item categories and map raw demo names to exact Valve equipment graphics.

Two spellings exist in the demo files: the display name in `active_weapon_name` ("High Explosive Grenade",
"M4A1-S") and the code in kill events ("hegrenade", "m4a1_silencer"). Both go through `icon_id`.

An unmapped name never falls back to a guess (the v3.3 regex called an HE grenade a rifle). It becomes the
`unknown` icon and is recorded in UNMAPPED; `assert_all_mapped()` makes the report build fail on it, so a new
item shows up as a build error instead of a wrong picture.
"""

from __future__ import annotations

import base64
from pathlib import Path

ICON_IDS = ("rifle", "sniper", "lmg", "smg", "shotgun", "pistol", "knife", "smoke", "flash", "he", "fire",
            "decoy", "zeus", "c4", "gear", "unknown")

# short text chip shown instead of a glyph when the map is displayed small (and in the roster)
CHIP = {"rifle": "RIFLE", "sniper": "SNIPER", "lmg": "LMG", "smg": "SMG", "shotgun": "SHOTGUN", "pistol": "PISTOL",
        "knife": "KNIFE", "smoke": "SMOKE", "flash": "FLASH", "he": "HE", "fire": "FIRE", "decoy": "DECOY",
        "zeus": "ZEUS", "c4": "BOMB", "gear": "ITEM", "unknown": "?"}

_TABLE: dict[str, str] = {}


def _add(icon: str, *names: str) -> None:
    for n in names:
        _TABLE[n.lower()] = icon


# display names (active_weapon_name) and kill-event codes, one line per icon
_add("rifle", "AK-47", "ak47", "M4A1-S", "m4a1_silencer", "M4A4", "m4a1", "Galil AR", "galilar", "FAMAS", "famas",
     "AUG", "aug", "SG 553", "sg556")
_add("sniper", "AWP", "awp", "SSG 08", "ssg08", "SCAR-20", "scar20", "G3SG1", "g3sg1")
_add("lmg", "Negev", "negev", "M249", "m249")
_add("smg", "MP9", "mp9", "MAC-10", "mac10", "MP7", "mp7", "MP5-SD", "mp5sd", "UMP-45", "ump45", "P90", "p90",
     "PP-Bizon", "bizon")
_add("shotgun", "Nova", "nova", "XM1014", "xm1014", "MAG-7", "mag7", "Sawed-Off", "sawedoff")
_add("pistol", "Glock-18", "glock", "USP-S", "usp_silencer", "P2000", "hkp2000", "P250", "p250", "Desert Eagle",
     "deagle", "Five-SeveN", "fiveseven", "Tec-9", "tec9", "CZ75-Auto", "cz75a", "Dual Berettas", "elite",
     "R8 Revolver", "revolver")
_add("knife", "knife", "knife_t", "Bayonet", "M9 Bayonet", "Butterfly Knife", "Karambit", "Bowie Knife",
     "Talon Knife", "Skeleton Knife", "Stiletto Knife", "Huntsman Knife", "Nomad Knife", "Gut Knife", "Flip Knife",
     "Paracord Knife", "Shadow Daggers", "Kukri Knife", "Classic Knife", "Ursus Knife", "Falchion Knife",
     "Navaja Knife", "Survival Knife", "knife_skeleton", "knife_butterfly", "knife_karambit", "knife_m9_bayonet",
     "knife_tactical", "knife_gut", "knife_flip", "knife_falchion", "knife_push", "knife_survival_bowie",
     "knife_ursus", "knife_gypsy_jackknife", "knife_stiletto", "knife_widowmaker", "knife_css", "knife_cord",
     "knife_canis", "knife_outdoor", "knife_kukri", "bayonet")
_add("smoke", "Smoke Grenade", "smokegrenade")
_add("flash", "Flashbang", "flashbang")
_add("he", "High Explosive Grenade", "hegrenade")
_add("fire", "Molotov", "molotov", "Incendiary Grenade", "incgrenade", "inferno")
_add("decoy", "Decoy Grenade", "decoy")
_add("zeus", "Zeus x27", "taser")
_add("c4", "C4 Explosive", "planted_c4", "c4")
# items that are real but have no picture worth drawing: shown as a generic item chip, not as an error
_add("gear", "Health Shot", "healthshot", "Tactical Awareness Grenade", "tagrenade", "Breach Charge", "breachcharge",
     "Bump Mine", "bumpmine", "Riot Shield", "shield", "Defuse Kit", "defuser", "world", "trigger_hurt", "worldspawn")

UNMAPPED: set[str] = set()

# Valve's equipment filenames, kept distinct from category ids above.
_ASSETS: dict[str, str] = {}
for _display, _code in (
    ("AK-47", "ak47"), ("M4A1-S", "m4a1_silencer"), ("M4A4", "m4a1"),
    ("Galil AR", "galilar"), ("FAMAS", "famas"), ("AUG", "aug"), ("SG 553", "sg556"),
    ("AWP", "awp"), ("SSG 08", "ssg08"), ("SCAR-20", "scar20"), ("G3SG1", "g3sg1"),
    ("Negev", "negev"), ("M249", "m249"), ("MP9", "mp9"), ("MAC-10", "mac10"),
    ("MP7", "mp7"), ("MP5-SD", "mp5sd"), ("UMP-45", "ump45"), ("P90", "p90"), ("PP-Bizon", "bizon"),
    ("Nova", "nova"), ("XM1014", "xm1014"), ("MAG-7", "mag7"), ("Sawed-Off", "sawedoff"),
    ("Glock-18", "glock"), ("USP-S", "usp_silencer"), ("P2000", "hkp2000"), ("P250", "p250"),
    ("Desert Eagle", "deagle"), ("Five-SeveN", "fiveseven"), ("Tec-9", "tec9"),
    ("CZ75-Auto", "cz75a"), ("Dual Berettas", "elite"), ("R8 Revolver", "revolver"),
    ("Smoke Grenade", "smokegrenade"), ("Flashbang", "flashbang"), ("High Explosive Grenade", "hegrenade"),
    ("Molotov", "molotov"), ("Incendiary Grenade", "incgrenade"), ("Decoy Grenade", "decoy"),
    ("Zeus x27", "taser"), ("C4 Explosive", "c4"), ("Bayonet", "bayonet"),
    ("M9 Bayonet", "knife_m9_bayonet"), ("Butterfly Knife", "knife_butterfly"), ("Karambit", "knife_karambit"),
    ("Bowie Knife", "knife_survival_bowie"), ("Talon Knife", "knife_widowmaker"),
    ("Skeleton Knife", "knife_skeleton"), ("Stiletto Knife", "knife_stiletto"),
    ("Huntsman Knife", "knife_tactical"), ("Nomad Knife", "knife_canis"), ("Gut Knife", "knife_gut"),
    ("Flip Knife", "knife_flip"), ("Paracord Knife", "knife_cord"), ("Shadow Daggers", "knife_push"),
    ("Kukri Knife", "knife_kukri"), ("Classic Knife", "knife_css"), ("Ursus Knife", "knife_ursus"),
    ("Falchion Knife", "knife_falchion"), ("Navaja Knife", "knife_gypsy_jackknife"),
    ("Survival Knife", "knife_outdoor"), ("knife", "knife"), ("knife_t", "knife_t"),
):
    _ASSETS[_display.lower()] = _code
    _ASSETS[_code] = _code
_ASSETS["planted_c4"] = "c4"


def asset_id(raw) -> str:
    """Exact equipment graphic; empty means text only, never a substitute gun."""
    return _ASSETS.get(str(raw).lower(), "")


def image_payload(asset_ids=None) -> dict[str, str]:
    """Embed Valve SVGs so reports and ZIP handoffs need no network connection."""
    folder = Path(__file__).resolve().parents[3] / "assets/weapons"
    result = {}
    for name in sorted(set(_ASSETS.values()) if asset_ids is None else set(asset_ids)):
        svg = folder / f"{name}.svg"
        if not svg.is_file():
            raise ValueError(f"Missing weapon graphic: {svg}")
        result[name] = "data:image/svg+xml;base64," + base64.b64encode(svg.read_bytes()).decode()
    return result


def icon_id(raw) -> str:
    """Canonical icon id for a raw item name; '' for none. Unmapped names return 'unknown' and are recorded."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    hit = _TABLE.get(s.lower())
    if hit:
        return hit
    UNMAPPED.add(s)
    return "unknown"


def assert_all_mapped() -> None:
    if UNMAPPED:
        raise ValueError("unmapped weapon / item names (add them to report/weapons.py): " + ", ".join(sorted(UNMAPPED)))
