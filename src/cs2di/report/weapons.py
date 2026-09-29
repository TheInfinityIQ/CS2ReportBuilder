"""Exact map from every raw item name the demo uses to one canonical icon id.

Two spellings exist in the demo files: the display name in `active_weapon_name` ("High Explosive Grenade",
"M4A1-S") and the code in kill events ("hegrenade", "m4a1_silencer"). Both go through `icon_id`.

An unmapped name never falls back to a guess (the v3.3 regex called an HE grenade a rifle). It becomes the
`unknown` icon and is recorded in UNMAPPED; `assert_all_mapped()` makes the report build fail on it, so a new
item shows up as a build error instead of a wrong picture.
"""

from __future__ import annotations

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
