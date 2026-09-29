import shutil
import subprocess
from pathlib import Path

import pytest

from cs2di.report import weapons

# every item name seen in the 30-game MIMY and 30-game iTrilogy batches (active_weapon_name) plus kill-event codes
SEEN = """AK-47|M4A1-S|M9 Bayonet|USP-S|Glock-18|Butterfly Knife|AWP|knife|M4A4|Smoke Grenade|Desert Eagle|knife_t|Karambit|
Flashbang|Galil AR|High Explosive Grenade|MP9|Talon Knife|MAC-10|Skeleton Knife|C4 Explosive|Stiletto Knife|Incendiary Grenade|
Huntsman Knife|Nomad Knife|Five-SeveN|Tec-9|Bayonet|Gut Knife|FAMAS|Molotov|Flip Knife|Paracord Knife|SSG 08|P2000|P250|
Shadow Daggers|Kukri Knife|Classic Knife|Ursus Knife|Falchion Knife|MP7|Dual Berettas|Navaja Knife|MAG-7|CZ75-Auto|
Decoy Grenade|XM1014|Nova|R8 Revolver|MP5-SD|Survival Knife|Zeus x27|UMP-45|Sawed-Off|SG 553|P90""".replace("\n", "").split("|")
CODES = "ak47 m4a1_silencer awp m4a1 usp_silencer glock deagle galilar mac10 mp9 famas fiveseven tec9 hegrenade ssg08 p250 world inferno mp7 hkp2000 planted_c4 elite mag7 ump45 xm1014 nova mp5sd revolver taser knife knife_skeleton cz75a sg556 sawedoff".split()


def test_every_seen_name_is_mapped():
    weapons.UNMAPPED.clear()
    assert len(SEEN) == 57  # the 58th "name" in the batches is an empty value (no active item)
    for n in SEEN + CODES:
        assert weapons.icon_id(n) != "unknown", n
    assert not weapons.UNMAPPED


def test_he_grenade_is_not_a_rifle():
    assert weapons.icon_id("High Explosive Grenade") == "he"
    assert weapons.icon_id("hegrenade") == "he"
    assert weapons.icon_id("AWP") == "sniper"


def test_unmapped_name_becomes_unknown_and_fails_the_build():
    weapons.UNMAPPED.clear()
    assert weapons.icon_id("Some New Item") == "unknown"
    with pytest.raises(ValueError, match="Some New Item"):
        weapons.assert_all_mapped()
    weapons.UNMAPPED.clear()


def test_empty_names_are_no_icon():
    assert weapons.icon_id(None) == "" and weapons.icon_id("") == "" and weapons.icon_id(float("nan")) == ""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_viewer_js_parses():
    js = Path(weapons.__file__).with_name("viewer.js")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
