"""
CS2 demo extraction for coaching analysis — v7.8 / schema 3.8

v7.8 (2026-09-28), behaviour change limited to damage; everything else is v7.7 verbatim:
  - player_hurt gains dmg_health_effective + same_tick_multi_hurt. The legacy
    dmg_health_capped (= user_health - health) is kept unchanged for comparability, but it
    double-counts when one victim takes several hits on the same tick, because every row
    shares the start-of-tick user_health. Verified on 179 sampled demos across 8 batches:
    0.1-0.9% excess damage, 3.3% on Premier. See docs/KNOWN_PITFALLS.md row 27.
  - utility_effectiveness HE/fire damage now uses dmg_health_effective.
  - Paths follow PROJECT_ROOT/01_Demos/<folder> -> PROJECT_ROOT/02_Analysis/analyzed_<folder>.
  Damage dealt after the round-end tick is still counted: FACEIT's ADR includes it.

Changes from previous v5 (schema 2.2):

FULL-MATCH / TARGETLESS MODE
  TARGET_PLAYER = None or "" now means "extract the entire match with no
  privileged player".  The round table is always match-centric (winner,
  reason, ticks, bomb info).  Target-centric columns (my_side, result,
  my_score, opp_score) appear only when a real target name is supplied.
  A new player_rounds.csv gives every player's side/result per round so
  any player can be analysed later without re-parsing.

  When TARGET_PLAYER is set the behaviour is identical to schema 2.2
  (including the strict valid-flag rules).  When it is None/"" the match
  is marked valid as long as a usable round table was built.

All earlier correctness fixes (SteamID repair, match-start fallback,
per-round freeze-end fallback, capped damage, silent-prop logging,
FACEIT-unavailable props dropped, etc.) are preserved.

Usage:
    Put .dem files in DEMO_DIR.
    Set TARGET_PLAYER = "SomeName"          → classic single-target mode
    Set TARGET_PLAYER = None or ""          → full-match mode
    Then: python extract_demos_v7_7_hardened.py
"""

from pathlib import Path
import json
import traceback
import math
import ast
import hashlib
import sys
import shutil
import importlib.metadata
from collections import defaultdict

import pandas as pd
import demoparser2
from demoparser2 import DemoParser


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays\demoparser"
)

DEMO_FOLDER = "iTrilogy"

DEMO_DIR = PROJECT_ROOT / "01_Demos" / DEMO_FOLDER
OUTPUT_DIR = PROJECT_ROOT / "02_Analysis" / f"analyzed_{DEMO_FOLDER}"

# Set to a player name for classic single-target mode.
# Set to None or "" for full-match (all-player) extraction.
TARGET_PLAYER = None

SCHEMA_VERSION = "3.8"   # v7.8: same-tick effective damage (dmg_health_effective)
TICKRATE = 64

# ------------------------------------------------------------------
# OUTPUT / PERFORMANCE PROFILE
# ------------------------------------------------------------------
# "batch" is the recommended default for 20+ game coaching batches. It keeps
# all v6 core evidence plus compact v7 coaching tables, but does NOT write giant
# raw 64 Hz telemetry dumps. "deep" is for selected demos where full forensic
# mechanics/user-command evidence is worth the cost.
COACHING_PROFILE = "batch"          # "batch" or "deep"
if COACHING_PROFILE not in {"batch", "deep"}:
    raise ValueError("COACHING_PROFILE must be 'batch' or 'deep'")
DEEP_MODE = COACHING_PROFILE == "deep"
RUN_INTERNAL_SELF_TESTS = True

TICK_SAMPLE_EVERY = 32      # player_positions sampling (32 = 2 Hz)

# Profile-derived settings.  Do not toggle these independently: batch mode is
# intentionally coherent so a size-saving switch cannot accidentally disable a
# derived coaching table or leave another expensive parser path enabled.
ENABLE_ENGAGEMENT_SUMMARIES = True
SAVE_RAW_DENSE_TICKS = DEEP_MODE
ENABLE_GRENADE_ENTITY_PARSE = DEEP_MODE
GRENADE_PATH_EVERY = 4 if DEEP_MODE else None
ENABLE_ITEM_EQUIP_EVENT = DEEP_MODE
ENABLE_ECON_ITEM_DROP_PARSE = DEEP_MODE

# Batch engagement reconstruction uses only the three seconds BEFORE deaths.
# The full-rate dataframe exists transiently in memory to build engagements.csv
# and is discarded; only deep mode serializes it.
DENSE_PRE_DEATH_S = 3.0
DENSE_POST_DEATH_S = 0.0
DENSE_WINDOW_FIRE_S = 1.0    # deep mode only
DENSE_WINDOW_HURT_S = 1.5    # deep mode only
DENSE_WINDOW_DEATH_S = 2.0   # deep mode only
DENSE_MAX_TICKS = None

# User-command telemetry: batch mode performs a tiny independent 32-tick
# capability probe.  Deep mode parses the engagement ticks and may serialize
# scalar command telemetry.  Heavy nested input-history remains opt-in.
ENABLE_USERCMD_PROBE = True
USERCMD_MODE = "dense" if DEEP_MODE else "probe"
USERCMD_PROBE_COUNT = 32
SAVE_RAW_USERCMD_TICKS = DEEP_MODE
ENABLE_HEAVY_USERCMD_HISTORY = False

# Fail loudly if somebody later edits the profile-derived switches into an
# internally contradictory batch configuration.
if not DEEP_MODE:
    if SAVE_RAW_DENSE_TICKS or SAVE_RAW_USERCMD_TICKS or ENABLE_GRENADE_ENTITY_PARSE:
        raise ValueError("Batch profile must not save raw dense/usercmd telemetry or parse grenade entities")
    if USERCMD_MODE != "probe":
        raise ValueError("Batch profile must use the lightweight usercmd probe")

# Transparent economy heuristics. These are analytical labels, not engine-native
# states. Objective money/equipment columns are always retained alongside them.
TEAM_BUY_FULL_AVG_EQUIP = 4000
TEAM_BUY_FORCE_AVG_EQUIP = 2500
TEAM_BUY_ECO_AVG_EQUIP = 1500

# Geometry policy: do not silently hard-code legacy CS:GO dimensions as CS2 truth.
# Horizontal (yaw) crosshair error is exact from demo XY + view yaw. Vertical/3D
# aim error requires a verified eye/target-height model and is therefore not
# fabricated here. Raw crouch/hull-related state is saved so this can be added
# later when a current CS2 constant is independently verified.
GEOMETRY_POLICY = {
    "horizontal_crosshair_error": "enabled_exact_from_demo_xy_yaw",
    "vertical_crosshair_error": "disabled_pending_verified_current_cs2_eye_height",
    "distance_units": "source2_world_units_unconverted",
}

# Game-state props stamped onto every event via other=.
GAME_STATE_OTHER = [
    "is_warmup_period",
    "is_match_started",
    "total_rounds_played",
    "game_phase",
    "team_clan_name",        # -> ct_team_clan_name / t_team_clan_name
    "game_time",             # with round_start_time gives the exact round clock
    "round_start_time",
    "is_bomb_planted",       # post-plant flag, free, on every event
    "is_freeze_period",
    "round_in_progress",
    "team_rounds_total",     # -> ct_/t_team_rounds_total, live score
    "is_bomb_dropped",
    "ct_losing_streak",
    "t_losing_streak",
]

# Per-player props stamped onto player-involved events via player=.
# Dual-player events return these prefixed attacker_/user_/assister_.
#
# is_strafing, buttons, and aim_punch_angle are deliberately NOT requested.
# Verified absent on 57/57 FACEIT demos tested (two independent batches, many
# different servers/regions/patches): FACEIT appears to strip raw per-tick
# input state from the demos it serves, almost certainly to stop input timing
# from being reverse-engineered for cheat development. This is a platform
# property, not a per-demo fluke, so requesting them only adds a dead
# dropped_props entry and a few wasted milliseconds on every single parse.
# They resolve fine on Valve MM / HLTV demos (verified against the repo's own
# test_demo.dem) — if a non-FACEIT source is ever in the mix, add them back
# for that source specifically rather than globally.
BUTTON_UNAVAILABLE_ON_FACEIT = ["is_strafing", "buttons", "aim_punch_angle"]

PLAYER_EXTRA = [
    # position and motion
    "X", "Y", "Z",
    "velocity_X", "velocity_Y", "velocity_Z",
    "pitch", "yaw", "last_place_name",
    "is_airborne", "is_walking", "duck_amount", "max_speed",
    "velo_modifier",         # <1.0 means slowed (walking, hit, unscoping)
    "move_type",
    # survival state
    "health", "armor_value", "is_alive", "has_defuser", "has_helmet",
    "flash_duration", "flash_max_alpha",   # 0-255; 255 is fully blind
    # weapon state
    "active_weapon_name", "active_weapon_ammo", "total_ammo_left",
    "is_in_reload", "is_scoped", "zoom_lvl", "accuracy_penalty", "shots_fired",
    "i_recoil_idx", "fl_recoil_idx", "last_shot_time",
    "next_primary_attack_tick", "next_primary_attack_tick_ratio",
    "ducked", "ducking", "duck_speed", "last_duck_time", "fall_velo",
    # context
    "inventory",             # readable list, e.g. [knife, AK-47, Flashbang]
    "approximate_spotted_by",  # list of steamids who can see this player
    "spotted",
    "is_defusing", "in_bomb_zone", "in_buy_zone",
    # economy
    "balance", "cash_spent_this_round", "total_cash_spent",
    "round_start_equip_value", "current_equip_value",
    # identity / misc
    "team_name", "team_num", "entity_id", "ping",
]

# Events that reference one or two players and deserve full PLAYER_EXTRA.
RICH_EVENTS = ["player_death", "player_hurt", "player_blind", "weapon_fire"]

# Events that get a smaller player context (position is enough).
PLACE_EVENTS = [
    "bomb_beginplant", "bomb_planted", "bomb_begindefuse", "bomb_defused",
    "bomb_dropped", "bomb_pickup", "bomb_exploded",
    "flashbang_detonate", "smokegrenade_detonate", "hegrenade_detonate",
    "inferno_startburn", "inferno_expire", "decoy_detonate",
    "smokegrenade_expired", "molotov_detonate",
    "item_equip", "item_pickup", "item_remove", "weapon_reload", "weapon_zoom",
    "player_spawn", "player_jump", "player_footstep", "round_mvp",
]
PLACE_PROPS = ["X", "Y", "Z", "last_place_name", "health", "is_alive",
               "active_weapon_name", "inventory"]

if not ENABLE_ITEM_EQUIP_EVENT:
    PLACE_EVENTS = [e for e in PLACE_EVENTS if e != "item_equip"]

# Always parsed regardless of what list_game_events() reports.
CORE_EVENTS = {
    # Round/combat events required for structural correctness.
    "round_start", "round_end", "round_freeze_end",
    "player_death", "player_hurt", "player_blind", "weapon_fire",
    # Coaching-critical utility/objective events are always attempted because
    # list_game_events() is known to under-report on some demo sources.
    "bomb_beginplant", "bomb_planted", "bomb_begindefuse", "bomb_defused",
    "bomb_dropped", "bomb_pickup", "bomb_exploded",
    "flashbang_detonate", "smokegrenade_detonate", "hegrenade_detonate",
    "inferno_startburn", "inferno_expire", "smokegrenade_expired",
    "molotov_detonate", "item_pickup", "item_remove",
    "weapon_reload", "weapon_zoom", "player_spawn", "round_mvp",
}

# Events with no player context worth requesting.
PLAIN_EVENTS = [
    "round_start", "round_freeze_end", "round_end", "round_officially_ended",
    "round_prestart", "round_poststart", "buytime_ended", "begin_new_match",
    "round_announce_match_start", "cs_win_panel_match", "cs_win_panel_round",
    "player_disconnect", "rank_update", "other_death", "fire_bullets",
]

# Engine-maintained aggregates. Updated once per round; sampled at the final
# tick they reproduce the in-game scoreboard exactly.
SCOREBOARD_PROPS = [
    "kills_total", "deaths_total", "assists_total", "damage_total",
    "headshot_kills_total", "utility_damage_total", "enemies_flashed_total",
    "alive_time_total", "objective_total",
    "3k_rounds_total", "4k_rounds_total", "ace_rounds_total",
    "mvps", "score", "rank", "comp_wins",
    "cash_earned_total", "money_saved_total", "kill_reward_total",
    "equipment_value_total", "team_name", "team_clan_name",
]

SCOREBOARD_DELTA_PROPS = [
    "kills_total", "deaths_total", "assists_total", "damage_total",
    "headshot_kills_total", "utility_damage_total", "enemies_flashed_total",
    "alive_time_total", "objective_total", "3k_rounds_total", "4k_rounds_total",
    "ace_rounds_total", "mvps", "score", "cash_earned_total",
    "money_saved_total", "kill_reward_total", "equipment_value_total",
]

# Freeze-end snapshot: what everyone bought, every round.
ECONOMY_PROPS = [
    "balance", "current_equip_value", "round_start_equip_value",
    "total_cash_spent", "cash_spent_this_round",
    "inventory", "has_defuser", "has_helmet", "armor_value",
    "team_name", "team_clan_name", "total_rounds_played", "is_alive",
]

TICK_PROPS = [
    "X", "Y", "Z", "health", "armor_value", "is_alive",
    "team_name", "active_weapon_name", "last_place_name",
    "flash_duration", "is_scoped", "is_walking",
    "is_warmup_period", "is_match_started", "total_rounds_played",
]

# v7 dense mechanical state.  All names below are present in the bundled
# demoparser2 property map/README. Unsupported per-source fields are surfaced in
# match_summary.json instead of being treated as zero.
DENSE_PLAYER_PROPS_DEEP = [
    "X", "Y", "Z", "velocity_X", "velocity_Y", "velocity_Z",
    "pitch", "yaw", "health", "armor_value", "is_alive", "team_name",
    "last_place_name", "active_weapon_name", "active_weapon_ammo",
    "total_ammo_left", "inventory", "flash_duration", "flash_max_alpha",
    "is_scoped", "zoom_lvl", "is_walking", "is_airborne",
    "duck_amount", "duck_time_ms", "duck_speed", "in_crouch",
    "crouch_state", "ducked", "ducking", "jump_time_ms", "last_duck_time",
    "fall_velo", "stamina", "move_state", "max_speed", "velo_modifier",
    "accuracy_penalty", "shots_fired", "is_in_reload",
    "i_recoil_idx", "fl_recoil_idx", "last_shot_time",
    "fire_seq_start_time", "is_burst_mode", "burst_shots_remaining",
    "needs_bolt_action", "next_primary_attack_tick",
    "next_primary_attack_tick_ratio", "time_last_injury",
    "direction_last_injury", "approximate_spotted_by", "spotted",
    "CCSPlayerPawn.m_vecMaxs",  # raw per-demo collision max; do not assume legacy hull height
    "total_rounds_played", "is_bomb_planted",
]

# Batch mode asks only for properties consumed by engagement reconstruction.
# Discrete rich events already contain inventory/ammo/weapon/economy state.
DENSE_PLAYER_PROPS_BATCH = [
    "X", "Y", "Z", "velocity_X", "velocity_Y", "velocity_Z",
    "pitch", "yaw", "health", "is_alive", "team_name",
    "active_weapon_name", "is_scoped", "is_walking", "is_airborne",
    "duck_amount", "velo_modifier", "accuracy_penalty", "shots_fired",
    "approximate_spotted_by", "total_rounds_played",
]
DENSE_PLAYER_PROPS = DENSE_PLAYER_PROPS_DEEP if DEEP_MODE else DENSE_PLAYER_PROPS_BATCH

# Parsed separately so missing user commands cannot degrade ordinary state.
USERCMD_PROPS_ALL = [
    "usercmd_viewangle_x", "usercmd_viewangle_y", "usercmd_viewangle_z",
    "usercmd_buttonstate_1", "usercmd_buttonstate_2", "usercmd_buttonstate_3",
    "usercmd_buttons_held", "usercmd_buttons_pressed", "usercmd_buttons_released",
    "usercmd_consumed_server_angle_changes", "usercmd_forward_move",
    "usercmd_left_move", "usercmd_impulse", "usercmd_mouse_dx",
    "usercmd_mouse_dy", "usercmd_left_hand_desired", "usercmd_weapon_select",
    "usercmd_input_history", "usercmd_subtick_moves",
]
USERCMD_HEAVY_PROPS = ["usercmd_input_history", "usercmd_subtick_moves"]
USERCMD_PROPS_LIGHT = [p for p in USERCMD_PROPS_ALL if p not in USERCMD_HEAVY_PROPS]
# Probe mode checks all known fields on just 32 ticks. Dense/deep mode defaults
# to scalar command state; enable heavy history explicitly only when needed.
USERCMD_PROPS = (USERCMD_PROPS_ALL if ENABLE_HEAVY_USERCMD_HISTORY
                 else USERCMD_PROPS_LIGHT)

# From the parser's own buttons_bitfield example. `buttons` is a bitfield of
# keys held at that tick; IN_MOVELEFT/IN_MOVERIGHT against velocity is how you
# detect a counter-strafe rather than inferring it from speed alone.
BUTTON_BITS = {
    "IN_ATTACK": 1 << 0, "IN_JUMP": 1 << 1, "IN_DUCK": 1 << 2,
    "IN_FORWARD": 1 << 3, "IN_BACK": 1 << 4, "IN_USE": 1 << 5,
    "IN_TURNLEFT": 1 << 7, "IN_TURNRIGHT": 1 << 8,
    "IN_MOVELEFT": 1 << 9, "IN_MOVERIGHT": 1 << 10, "IN_ATTACK2": 1 << 11,
    "IN_RELOAD": 1 << 13, "IN_SPEED": 1 << 16, "IN_WALK": 1 << 17,
    "IN_ZOOM": 1 << 18, "IN_SCORE": 1 << 33, "IN_INSPECT": 1 << 35,
}


# ============================================================
# HELPERS
# ============================================================

def normalize_dataframe(value) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, list):
        return pd.DataFrame(value)
    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


def _is_missing_scalar(value) -> bool:
    """True for scalar missing values; never coerce arrays/lists to bool."""
    if value is None or value is pd.NA:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    try:
        if getattr(result, "ndim", 1) == 0 and hasattr(result, "item"):
            return bool(result.item())
    except Exception:
        pass
    return False


def _exact_int_scalar(value):
    """Integer conversion without an unnecessary float64 round-trip."""
    if _is_missing_scalar(value):
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        # Decimal/scientific text means precision has already been represented as
        # a float; int(value) is the best observable integer at this point.
        if any(ch in text.lower() for ch in (".", "e")):
            return int(float(value))
        return int(text)
    except Exception:
        try:
            return int(value)
        except Exception:
            return None


def _coalesce(*values):
    """First non-missing scalar; unlike Python `or`, safe for pd.NA/NaN."""
    for value in values:
        if not _is_missing_scalar(value):
            return value
    return None


def repair_steamids(df: pd.DataFrame, roster=None) -> pd.DataFrame:
    """Repair nullable SteamID64 columns with a tightly bounded roster snap.

    Exact object/int values are converted scalar-by-scalar so pandas cannot first
    promote them to float64. Already-float values may be quantized; at SteamID64
    magnitude float64 spacing is 16, so a nearest-roster correction within 16 is
    sufficient. Equidistant candidates are deliberately left unresolved so the
    later roster audit catches them rather than silently choosing a player.
    """
    if df.empty:
        return df
    roster = sorted({int(r) for r in (roster or []) if r is not None})
    for col in df.columns:
        if "steamid" not in str(col).lower():
            continue
        original = df[col]
        observed = original.map(_exact_int_scalar)
        if roster:
            def snap(iv):
                if iv is None or _is_missing_scalar(iv):
                    return pd.NA
                iv = int(iv)
                nearest = sorted((abs(r - iv), r) for r in roster)
                if not nearest or nearest[0][0] > 16:
                    return iv
                if len(nearest) > 1 and nearest[1][0] == nearest[0][0]:
                    return iv
                return nearest[0][1]
            observed = observed.map(snap)
        try:
            df[col] = pd.Series(observed, index=df.index, dtype="Int64")
        except Exception:
            df[col] = observed
    return df


# Valve demos return round_end winner/reason as ints; FACEIT/get5 demos return
# strings. Normalise so downstream logic works on both.
WINNER_MAP = {2: "T", 3: "CT", "TERRORIST": "T", "T": "T", "CT": "CT"}

# Source 2 RoundEndReason enum -> one canonical vocabulary shared with the
# string form FACEIT/get5 demos emit, so both sources compare cleanly.
# Note 8/9 read as the LOSER: reason 8 (ct_win) means the Ts were killed.
REASON_MAP = {
    1: "bomb_exploded", 7: "bomb_defused", 8: "t_killed", 9: "ct_killed",
    10: "draw", 11: "hostages_rescued", 12: "time_ran_out",
    13: "hostages_not_rescued", 16: "game_start",
    17: "t_surrender", 18: "ct_surrender", 19: "t_planted",
    # FACEIT/get5 string forms, normalised onto the same vocabulary
    "target_bombed": "bomb_exploded", "bomb_exploded": "bomb_exploded",
    "bomb_defused": "bomb_defused", "t_killed": "t_killed",
    "ct_killed": "ct_killed", "target_saved": "time_ran_out",
    "time_ran_out": "time_ran_out",
}


def normalize_round_end(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "winner" in df.columns:
        df = df.copy()
        df["winner"] = df["winner"].map(lambda v: WINNER_MAP.get(v, v))
    if "reason" in df.columns:
        df["reason"] = df["reason"].map(lambda v: REASON_MAP.get(v, v))
    return df


def report_dropped_props(df: pd.DataFrame, requested, label: str) -> list:
    """demoparser2 silently omits props it cannot resolve. Surface that."""
    if df.empty:
        return list(requested)
    cols = set(str(c) for c in df.columns)
    missing = [p for p in requested if not any(p in c for c in cols)]
    if missing:
        print(f"    NOTE: {label}: props not present in this demo: {missing}")
    return missing


def add_effective_damage(df: pd.DataFrame) -> pd.DataFrame:
    """player_hurt.dmg_health is UNCAPPED overdamage: a 117-damage AK hit on a
    74 HP player is recorded as 117. Summing it inflates ADR by ~35% (verified
    against 30 FACEIT matches: mean error 24.1 ADR using dmg_health, 1.9 using
    the capped value). Actual damage dealt is pre-hit health minus post-hit
    health, i.e. user_health - health.
    """
    if df.empty or not {"user_health", "health"}.issubset(df.columns):
        return df
    df = df.copy()
    df["dmg_health_capped"] = (df["user_health"] - df["health"]).clip(lower=0)  # legacy, kept
    eff, multi = effective_damage(df)
    df["dmg_health_effective"] = eff
    df["same_tick_multi_hurt"] = multi
    return df


def effective_damage(h: pd.DataFrame):
    """Kept identical to cs2di.damage.effective_damage (a repo test enforces it).

    Several hits on one victim in one tick share the start-of-tick user_health; health never
    rises within a tick, so ordering those rows by remaining health recovers the hit order and
    each hit starts where the previous one ended. Unknown stays NaN.
    """
    KEYS = ["user_steamid", "tick"]
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


def is_live_match(df: pd.DataFrame) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if "is_warmup_period" in df.columns:
        mask &= (df["is_warmup_period"] != True)  # noqa: E712
    if "is_match_started" in df.columns:
        mask &= (df["is_match_started"] == True)  # noqa: E712
    return mask


def safe_parse_event(parser, event_name, player=None, other=None) -> pd.DataFrame:
    """Parse one event, degrading context rather than failing the demo."""
    attempts = []
    if player is not None:
        attempts.append(dict(player=player, other=other))
    if other is not None:
        attempts.append(dict(other=other))
    attempts.append(dict())

    last_exc = None
    for kwargs in attempts:
        try:
            return normalize_dataframe(parser.parse_event(event_name, **kwargs))
        except Exception as exc:
            last_exc = exc
    print(f"    WARNING: {event_name}: {last_exc}")
    return pd.DataFrame()


def safe_parse_events(parser, event_names, player=None, other=None) -> dict:
    """Batch parse (one demo pass for the whole group), falling back to
    per-event parsing if the batch call fails."""
    try:
        out = parser.parse_events(event_names, player=player, other=other)
        return {name: normalize_dataframe(df) for name, df in out}
    except Exception as exc:
        print(f"    NOTE: batch parse failed ({exc}); falling back per-event.")
        return {e: safe_parse_event(parser, e, player=player, other=other)
                for e in event_names}


ROSTER = []   # set per demo, used to repair float-mangled steamids


def save_df(df: pd.DataFrame, path: Path) -> None:
    """Write CSV without allowing a later default read_csv() to corrupt 64-bit IDs.

    CSV has no nullable-integer type.  A column containing 17-digit SteamID64
    values plus blank/null cells is commonly inferred as float64 when read back,
    which destroys exact identity above 2^53.  The in-memory representation
    remains nullable Int64, but on disk missing 64-bit identity values are written
    as integer 0 (the standard non-player/world sentinel) so ordinary CSV readers
    infer int64 and preserve every real ID exactly.

    This applies to SteamID columns and XUID-style identity columns.  Consumers
    should interpret 0 as "no player / world / unavailable", never as a player.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    out = repair_steamids(df.copy(), ROSTER)

    for col in out.columns:
        lc = str(col).lower()
        is_identity64 = ("steamid" in lc or lc == "xuid" or lc.endswith("_xuid"))
        if not is_identity64:
            continue

        # SteamID columns have already been repaired exactly.  XUID columns are
        # converted scalar-by-scalar to avoid an intermediate float64 round-trip.
        if "steamid" not in lc:
            vals = out[col].map(_exact_int_scalar)
            try:
                out[col] = pd.Series(vals, index=out.index, dtype="Int64")
            except Exception:
                out[col] = vals

        try:
            out[col] = out[col].astype("Int64").fillna(0).astype("int64")
        except Exception:
            # If a future parser exposes a non-numeric XUID-like field, preserve
            # it rather than coercing invented data.
            pass

    out.to_csv(path, index=False)


def json_safe(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=json_safe)

def runtime_environment_metadata() -> dict:
    try:
        script_path = Path(__file__).resolve()
        script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()
    except Exception:
        script_path = Path(__file__) if "__file__" in globals() else None
        script_sha = None
    try:
        demoparser_version = getattr(demoparser2, "__version__", None)
        if not demoparser_version:
            demoparser_version = importlib.metadata.version("demoparser2")
    except Exception:
        demoparser_version = None
    return {
        "extractor_file": script_path.name if script_path else None,
        "extractor_sha256": script_sha,
        "python_version": sys.version.split()[0],
        "pandas_version": getattr(pd, "__version__", None),
        "demoparser2_version": demoparser_version,
        "identity_csv_null_sentinel": 0,
    }



# ============================================================
# V7 COACHING-ENRICHMENT HELPERS
# ============================================================

def _as_sid(value):
    return _exact_int_scalar(value)


def _parse_sid_list(value):
    """Normalize approximate_spotted_by/list-like cells without inventing data."""
    if value is None:
        return set()
    try:
        if pd.isna(value):
            return set()
    except (TypeError, ValueError):
        pass
    if isinstance(value, (list, tuple, set)):
        seq = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return set()
        try:
            parsed = ast.literal_eval(s)
            seq = parsed if isinstance(parsed, (list, tuple, set)) else [parsed]
        except Exception:
            seq = [x.strip() for x in s.strip("[]").split(",") if x.strip()]
    else:
        seq = [value]
    out = set()
    for x in seq:
        sid = _as_sid(x)
        if sid is not None:
            out.add(sid)
    return out


def _angle_delta_deg(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return ((float(a) - float(b) + 180.0) % 360.0) - 180.0


def _yaw_to(x1, y1, x2, y2):
    vals = (x1, y1, x2, y2)
    if any(pd.isna(v) for v in vals):
        return None
    return math.degrees(math.atan2(float(y2) - float(y1), float(x2) - float(x1)))


def _dist3(a, b):
    try:
        return math.sqrt((float(a["X"])-float(b["X"]))**2 +
                         (float(a["Y"])-float(b["Y"]))**2 +
                         (float(a["Z"])-float(b["Z"]))**2)
    except Exception:
        return None


def build_dense_tick_list(all_events, start_tick, end_tick):
    """Build full-rate ticks needed for engagement reconstruction.

    Batch: three seconds before each death only. Deep: original broad windows
    around fire/hurt/death for forensic mechanics review.
    """
    if start_tick is None or end_tick is None:
        return []
    windows = []
    if DEEP_MODE:
        specs = [
            ("weapon_fire", DENSE_WINDOW_FIRE_S),
            ("player_hurt", DENSE_WINDOW_HURT_S),
            ("player_death", DENSE_WINDOW_DEATH_S),
        ]
        for name, seconds in specs:
            df = all_events.get(name, pd.DataFrame())
            if df.empty or "tick" not in df.columns:
                continue
            r = int(round(seconds * TICKRATE))
            for t in pd.to_numeric(df["tick"], errors="coerce").dropna().astype(int):
                windows.append((max(int(start_tick), t-r), min(int(end_tick), t+r)))
    else:
        deaths = all_events.get("player_death", pd.DataFrame())
        if not deaths.empty and "tick" in deaths.columns:
            pre = int(round(DENSE_PRE_DEATH_S * TICKRATE))
            post = int(round(DENSE_POST_DEATH_S * TICKRATE))
            for t in pd.to_numeric(deaths["tick"], errors="coerce").dropna().astype(int):
                windows.append((max(int(start_tick), t-pre), min(int(end_tick), t+post)))
    if not windows:
        return []
    windows.sort()
    merged = []
    for lo, hi in windows:
        if not merged or lo > merged[-1][1] + 1:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    ticks = [t for lo, hi in merged for t in range(lo, hi+1)]
    if DENSE_MAX_TICKS is not None and len(ticks) > int(DENSE_MAX_TICKS):
        raise RuntimeError(
            f"Dense tick request has {len(ticks):,} ticks, above explicit "
            f"DENSE_MAX_TICKS={DENSE_MAX_TICKS:,}. Increase/remove the cap; "
            "the extractor will not silently subsample engagement mechanics.")
    return ticks


def parse_dense_state(parser, ticks, notes):
    if not ticks:
        return pd.DataFrame()
    try:
        df = normalize_dataframe(parser.parse_ticks(DENSE_PLAYER_PROPS, ticks=ticks))
        df = filter_competitive_rows(df)
        notes["dropped_props"]["dense_state"] = report_dropped_props(
            df, DENSE_PLAYER_PROPS, "dense engagement state")
        return df
    except Exception as exc:
        notes["warnings"].append(f"dense engagement parse failed: {exc}")
        return pd.DataFrame()


def _representative_probe_ticks(start_tick, end_tick, count):
    if start_tick is None or end_tick is None or end_tick < start_tick or count <= 0:
        return []
    if end_tick == start_tick:
        return [int(start_tick)]
    count = max(2, int(count))
    span = int(end_tick) - int(start_tick)
    return sorted(set(int(start_tick) + round(i * span / (count - 1)) for i in range(count)))


def parse_usercmd_state(parser, dense_ticks, start_tick, end_tick, notes):
    status = {
        "requested": bool(ENABLE_USERCMD_PROBE and USERCMD_MODE != "off"),
        "mode": USERCMD_MODE, "ticks_requested": 0, "rows": 0,
        "available_props": [], "missing_props": [],
        "heavy_history_enabled": ENABLE_HEAVY_USERCMD_HISTORY,
        "warning": None,
    }
    if not ENABLE_USERCMD_PROBE or USERCMD_MODE == "off":
        return pd.DataFrame(), status
    query_ticks = (dense_ticks if USERCMD_MODE == "dense"
                   else _representative_probe_ticks(start_tick, end_tick, USERCMD_PROBE_COUNT))
    status["ticks_requested"] = len(query_ticks)
    if not query_ticks:
        return pd.DataFrame(), status
    try:
        requested_props = (USERCMD_PROPS_ALL if USERCMD_MODE == "probe" else USERCMD_PROPS)
        status["requested_props"] = requested_props
        df = normalize_dataframe(parser.parse_ticks(requested_props, ticks=query_ticks))
        df = filter_competitive_rows(df)
        status["rows"] = len(df)
        cols = set(str(c) for c in df.columns)
        available = [p for p in requested_props if any(p in c for c in cols)]
        status["available_props"] = available
        status["missing_props"] = [p for p in requested_props if p not in available]
        status["availability_definition"] = (
            "available_props means the requested property resolved to an output column; "
            "probe_stats shows whether representative rows actually contained values/variation"
        )
        probe_stats = {}
        for p in available:
            matching = [c for c in df.columns if p in str(c)]
            if not matching:
                continue
            # Prefer the exact property name where possible; otherwise report the
            # first resolved column containing the requested property.
            c = p if p in df.columns else matching[0]
            s = df[c]
            non_null = int(s.notna().sum())
            stat = {"column": str(c), "non_null": non_null}
            if non_null:
                try:
                    num = pd.to_numeric(s, errors="coerce")
                    stat["numeric_non_null"] = int(num.notna().sum())
                    stat["numeric_nonzero"] = int((num.fillna(0) != 0).sum())
                    stat["unique_non_null"] = int(s.dropna().astype(str).nunique())
                except Exception:
                    stat["unique_non_null"] = int(s.dropna().astype(str).nunique())
            probe_stats[p] = stat
        status["probe_stats"] = probe_stats
        if not available:
            status["warning"] = "No requested user-command properties resolved in this demo/source."
        return df, status
    except Exception as exc:
        status["warning"] = str(exc)
        notes["warnings"].append(f"usercmd probe failed: {exc}")
        return pd.DataFrame(), status


def _nearest_tick_rows(dense, tick, tolerance=2):
    if dense.empty or "tick" not in dense.columns:
        return pd.DataFrame()
    ticks = pd.to_numeric(dense["tick"], errors="coerce")
    valid = ticks.dropna()
    if valid.empty:
        return pd.DataFrame()
    nearest = int(valid.iloc[(valid - int(tick)).abs().argmin()])
    if abs(nearest - int(tick)) > tolerance:
        return pd.DataFrame()
    return dense[ticks == nearest]


def _row_for_sid(rows, sid):
    if rows.empty or "steamid" not in rows.columns or sid is None:
        return None
    m = rows[rows["steamid"].map(_as_sid) == int(sid)]
    return None if m.empty else m.iloc[0]


def _kill_category(death_row, attacker_sid, victim_sid):
    weapon = str(_coalesce(death_row.get("weapon"), "")).casefold()
    if attacker_sid is None:
        return "world_or_unattributed"
    if victim_sid is not None and attacker_sid == victim_sid:
        return "self"
    at = death_row.get("attacker_team_name")
    vt = death_row.get("user_team_name")
    if not _is_missing_scalar(at) and not _is_missing_scalar(vt) and str(at) == str(vt):
        return "teamkill"
    if any(x in weapon for x in ("hegrenade", "inferno", "molotov", "incgrenade")):
        return "utility"
    if any(x in weapon for x in ("planted_c4", "c4", "bomb")):
        return "bomb"
    if "knife" in weapon or "bayonet" in weapon:
        return "melee"
    if "taser" in weapon or "zeus" in weapon:
        return "taser"
    return "direct_weapon"


def _attacker_fire_ticks(fires, attacker_sid, lo, hi):
    if fires.empty or "tick" not in fires.columns or attacker_sid is None:
        return []
    sid_col = "user_steamid" if "user_steamid" in fires.columns else (
        "attacker_steamid" if "attacker_steamid" in fires.columns else None)
    if sid_col is None:
        return []
    ticks = pd.to_numeric(fires["tick"], errors="coerce")
    m = fires[(ticks >= int(lo)) & (ticks <= int(hi)) &
              (fires[sid_col].map(_as_sid) == int(attacker_sid))]
    if m.empty:
        return []
    return sorted(set(pd.to_numeric(m["tick"], errors="coerce").dropna().astype(int).tolist()))


def _relevant_burst_start(fires, attacker_sid, lo, target_tick, burst_gap_s=0.60):
    """Start of the last contiguous attacker burst at/before target_tick.

    This avoids assigning an unrelated early shot from the 3-second window to the
    kill.  Returns (start_tick, left_censored).
    """
    fire_ticks = _attacker_fire_ticks(fires, attacker_sid, lo, target_tick)
    if not fire_ticks:
        return None, False
    gap = max(1, int(round(float(burst_gap_s) * TICKRATE)))
    idx = len(fire_ticks) - 1
    start = fire_ticks[idx]
    while idx > 0 and fire_ticks[idx] - fire_ticks[idx - 1] <= gap:
        idx -= 1
        start = fire_ticks[idx]
    prior = _attacker_fire_ticks(fires, attacker_sid, max(0, lo-gap), lo-1)
    left_censored = bool(idx == 0 and prior and start - prior[-1] <= gap)
    return int(start), left_censored


def build_engagements(dense, all_events, players):
    """One row per attributed non-self death with conservative mechanics evidence.

    Dense batch windows begin three seconds before death.  If approximate visual
    contact is already true on the first jointly-observed tick, contact is marked
    left-censored and exact contact latency is deliberately left null. Utility and
    bomb kills are retained for positional context but never borrow unrelated gun
    fire as their shooting sequence.
    """
    deaths = all_events.get("player_death", pd.DataFrame())
    fires = all_events.get("weapon_fire", pd.DataFrame())
    hurts = all_events.get("player_hurt", pd.DataFrame())
    if dense.empty or deaths.empty:
        return pd.DataFrame()

    name_by_sid = {}
    if not players.empty and {"steamid", "name"}.issubset(players.columns):
        for sid, name in zip(players["steamid"], players["name"]):
            ss = _as_sid(sid)
            if ss is not None and not _is_missing_scalar(name):
                name_by_sid[ss] = name

    out = []
    dense_ticks = pd.to_numeric(dense["tick"], errors="coerce")
    visibility_available = "approximate_spotted_by" in dense.columns

    for _, d in deaths.iterrows():
        if _is_missing_scalar(d.get("tick")):
            continue
        death_tick = int(d["tick"])
        a = _as_sid(d.get("attacker_steamid"))
        v = _as_sid(d.get("user_steamid"))
        if a is None or v is None or a == v:
            continue

        category = _kill_category(d, a, v)
        lo = max(0, death_tick - int(round(DENSE_PRE_DEATH_S * TICKRATE)))

        first_damage = None
        if not hurts.empty and {"attacker_steamid", "user_steamid", "tick"}.issubset(hurts.columns):
            htick = pd.to_numeric(hurts["tick"], errors="coerce")
            hm = hurts[(htick >= lo) & (htick <= death_tick) &
                       (hurts["attacker_steamid"].map(_as_sid) == a) &
                       (hurts["user_steamid"].map(_as_sid) == v)]
            if not hm.empty:
                first_damage = int(pd.to_numeric(hm["tick"], errors="coerce").min())

        direct_duel = category in {"direct_weapon", "melee", "taser", "teamkill"}
        first_shot = None
        shot_left_censored = False
        if direct_duel:
            shot_target = first_damage if first_damage is not None else death_tick
            first_shot, shot_left_censored = _relevant_burst_start(fires, a, lo, shot_target)

        contact_a_sees_v = contact_v_sees_a = mutual_contact = None
        a_contact_left_censored = v_contact_left_censored = mutual_left_censored = None
        window = dense[(dense_ticks >= lo) & (dense_ticks <= death_tick)]
        if visibility_available and not window.empty:
            first_common_checked = False
            for t, grp in window.groupby("tick", sort=True):
                ar = _row_for_sid(grp, a)
                vr = _row_for_sid(grp, v)
                if ar is None or vr is None:
                    continue
                # approximate_spotted_by on player X lists observers who can see X.
                a_sees_v = a in _parse_sid_list(vr.get("approximate_spotted_by"))
                v_sees_a = v in _parse_sid_list(ar.get("approximate_spotted_by"))
                if not first_common_checked:
                    a_contact_left_censored = bool(a_sees_v)
                    v_contact_left_censored = bool(v_sees_a)
                    mutual_left_censored = bool(a_sees_v and v_sees_a)
                    first_common_checked = True
                if a_sees_v and contact_a_sees_v is None:
                    contact_a_sees_v = int(t)
                if v_sees_a and contact_v_sees_a is None:
                    contact_v_sees_a = int(t)
                if a_sees_v and v_sees_a and mutual_contact is None:
                    mutual_contact = int(t)

        probe_tick = _coalesce(first_shot, first_damage, mutual_contact, death_tick)
        rows = _nearest_tick_rows(dense, int(probe_tick)) if probe_tick is not None else pd.DataFrame()
        ar = _row_for_sid(rows, a)
        vr = _row_for_sid(rows, v)

        distance = _dist3(ar, vr) if ar is not None and vr is not None else None
        yaw_error = None
        attacker_speed = victim_speed = None
        attacker_visible_by = victim_visible_by = None
        nearest_attacker_tm = nearest_victim_tm = None

        if ar is not None and vr is not None:
            target_yaw = _yaw_to(ar.get("X"), ar.get("Y"), vr.get("X"), vr.get("Y"))
            yaw_error = abs(_angle_delta_deg(ar.get("yaw"), target_yaw)) if target_yaw is not None else None

            def speed(r):
                vx, vy = r.get("velocity_X"), r.get("velocity_Y")
                if _is_missing_scalar(vx) or _is_missing_scalar(vy):
                    return None
                try:
                    return math.hypot(float(vx), float(vy))
                except Exception:
                    return None

            attacker_speed = speed(ar)
            victim_speed = speed(vr)
            if visibility_available:
                attacker_visible_by = len(_parse_sid_list(ar.get("approximate_spotted_by")))
                victim_visible_by = len(_parse_sid_list(vr.get("approximate_spotted_by")))

            for who, row in (("a", ar), ("v", vr)):
                team = row.get("team_name")
                if _is_missing_scalar(team):
                    continue
                ds = []
                for _, rr in rows.iterrows():
                    rsid = _as_sid(rr.get("steamid"))
                    rr_team = rr.get("team_name")
                    alive = rr.get("is_alive")
                    is_dead = False
                    if not _is_missing_scalar(alive):
                        try:
                            is_dead = not bool(alive)
                        except Exception:
                            pass
                    if rsid in (a, v) or _is_missing_scalar(rr_team) or str(rr_team) != str(team) or is_dead:
                        continue
                    dd = _dist3(row, rr)
                    if dd is not None:
                        ds.append(dd)
                val = min(ds) if ds else None
                if who == "a": nearest_attacker_tm = val
                else: nearest_victim_tm = val

        attacker_latency = None
        if (first_shot is not None and contact_a_sees_v is not None and
                not bool(a_contact_left_censored) and not shot_left_censored and
                first_shot >= contact_a_sees_v):
            attacker_latency = round((first_shot-contact_a_sees_v)*1000/TICKRATE, 1)
        victim_contact_to_death = None
        if contact_v_sees_a is not None and not bool(v_contact_left_censored):
            victim_contact_to_death = round((death_tick-contact_v_sees_a)*1000/TICKRATE, 1)

        out.append({
            "death_tick": death_tick,
            "parser_round": d.get("total_rounds_played"),
            "attacker_steamid": a,
            "attacker_name": _coalesce(d.get("attacker_name"), name_by_sid.get(a)),
            "victim_steamid": v,
            "victim_name": _coalesce(d.get("user_name"), name_by_sid.get(v)),
            "attacker_team_name": d.get("attacker_team_name"),
            "victim_team_name": d.get("user_team_name"),
            "attacker_place_name": d.get("attacker_last_place_name"),
            "victim_place_name": d.get("user_last_place_name"),
            "weapon": d.get("weapon"),
            "headshot": d.get("headshot"),
            "kill_category": category,
            "first_damage_tick": first_damage,
            "first_shot_tick": first_shot,
            "shot_window_left_censored": bool(shot_left_censored),
            "attacker_first_approx_spots_victim_tick": contact_a_sees_v,
            "victim_first_approx_spots_attacker_tick": contact_v_sees_a,
            "first_mutual_approx_contact_tick": mutual_contact,
            "attacker_contact_left_censored": a_contact_left_censored,
            "victim_contact_left_censored": v_contact_left_censored,
            "mutual_contact_left_censored": mutual_left_censored,
            "attacker_contact_to_first_shot_ms": attacker_latency,
            "victim_contact_to_death_ms": victim_contact_to_death,
            "contact_search_window_start_tick": lo,
            "visibility_property_available": bool(visibility_available),
            "probe_tick": probe_tick,
            "distance_units": distance,
            "attacker_speed_2d": attacker_speed,
            "victim_speed_2d": victim_speed,
            "attacker_yaw_error_to_victim_deg": yaw_error,
            "attacker_visible_by_count_approx": attacker_visible_by,
            "victim_visible_by_count_approx": victim_visible_by,
            "attacker_nearest_teammate_distance": nearest_attacker_tm,
            "victim_nearest_teammate_distance": nearest_victim_tm,
            "geometry_note": (
                "yaw error exact from XY+yaw; visibility uses approximate_spotted_by; "
                "contact latency is null when the extraction window is left-censored; "
                "no vertical aim error without verified CS2 eye height"
            ),
        })
    return pd.DataFrame(out)


def _player_relation(row, attacker_sid, victim_sid):
    if attacker_sid is not None and victim_sid is not None and attacker_sid == victim_sid:
        return "self"
    at = row.get("attacker_team_name")
    vt = row.get("user_team_name")
    if not _is_missing_scalar(at) and not _is_missing_scalar(vt):
        return "team" if str(at) == str(vt) else "enemy"
    return "unknown"


def build_utility_effectiveness(all_events):
    """Per-player/per-round utility evidence with relation-safe damage semantics."""
    blinds = all_events.get("player_blind", pd.DataFrame())
    hurts = all_events.get("player_hurt", pd.DataFrame())
    dets = {k: all_events.get(k, pd.DataFrame()) for k in
            ("flashbang_detonate", "hegrenade_detonate", "inferno_startburn", "molotov_detonate")}

    blind_stream_available = "player_blind" in all_events

    def blank():
        return {
            "blind_event_stream_available": bool(blind_stream_available),
            "flash_outcomes_available": bool(blind_stream_available),
            "flash_detonations": 0,
            "blind_events_all": 0,
            "enemy_blind_events": 0,
            "team_blind_events": 0,
            "self_blind_events": 0,
            "unknown_relation_blind_events": 0,
            "enemy_blind_duration_sum": 0.0,
            "blind_duration_sum_all": 0.0,
            "he_damage_all": 0.0,
            "fire_damage_all": 0.0,
            "he_enemy_damage": 0.0,
            "fire_enemy_damage": 0.0,
            "team_utility_damage": 0.0,
            "self_utility_damage": 0.0,
            "unknown_relation_utility_damage": 0.0,
        }

    rows = defaultdict(blank)
    for name, df in dets.items():
        if df.empty: continue
        for _, r in df.iterrows():
            sid = _as_sid(_coalesce(r.get("user_steamid"), r.get("attacker_steamid")))
            rnd = r.get("total_rounds_played")
            if sid is None or _is_missing_scalar(rnd): continue
            rec = rows[(sid, int(rnd))]
            if name == "flashbang_detonate": rec["flash_detonations"] += 1

    if not blinds.empty:
        for _, r in blinds.iterrows():
            sid = _as_sid(r.get("attacker_steamid")); victim_sid = _as_sid(r.get("user_steamid"))
            rnd = r.get("total_rounds_played")
            if sid is None or _is_missing_scalar(rnd): continue
            rec = rows[(sid, int(rnd))]
            rec["blind_events_all"] += 1
            dur = _coalesce(r.get("blind_duration"), r.get("duration"), 0.0)
            try: dur = float(dur)
            except Exception: dur = 0.0
            rec["blind_duration_sum_all"] += dur
            relation = _player_relation(r, sid, victim_sid)
            if relation == "enemy":
                rec["enemy_blind_events"] += 1; rec["enemy_blind_duration_sum"] += dur
            elif relation == "team": rec["team_blind_events"] += 1
            elif relation == "self": rec["self_blind_events"] += 1
            else: rec["unknown_relation_blind_events"] += 1

    if not hurts.empty:
        dmgcol = next(c for c in ("dmg_health_effective", "dmg_health_capped", "dmg_health") if c in hurts.columns or c == "dmg_health")
        for _, r in hurts.iterrows():
            sid = _as_sid(r.get("attacker_steamid")); victim_sid = _as_sid(r.get("user_steamid"))
            rnd = r.get("total_rounds_played")
            if sid is None or _is_missing_scalar(rnd): continue
            weapon = str(_coalesce(r.get("weapon"), "")).casefold()
            is_he = "hegrenade" in weapon
            is_fire = any(x in weapon for x in ("inferno", "molotov", "incgrenade"))
            if not (is_he or is_fire): continue
            dmg = r.get(dmgcol, 0)
            try: dmg = float(dmg) if not _is_missing_scalar(dmg) else 0.0
            except Exception: dmg = 0.0
            rec = rows[(sid, int(rnd))]
            if is_he: rec["he_damage_all"] += dmg
            if is_fire: rec["fire_damage_all"] += dmg
            relation = _player_relation(r, sid, victim_sid)
            if relation == "enemy":
                if is_he: rec["he_enemy_damage"] += dmg
                if is_fire: rec["fire_enemy_damage"] += dmg
            elif relation == "team": rec["team_utility_damage"] += dmg
            elif relation == "self": rec["self_utility_damage"] += dmg
            else: rec["unknown_relation_utility_damage"] += dmg

    out = []
    for (sid, rnd), rec in rows.items():
        rec = dict(rec)
        rec["enemy_utility_damage"] = rec["he_enemy_damage"] + rec["fire_enemy_damage"]
        rec["utility_damage_all"] = rec["he_damage_all"] + rec["fire_damage_all"]
        out.append({"steamid": sid, "parser_round": rnd, **rec})
    return pd.DataFrame(out)


def build_source_capabilities(all_events: dict, usercmd_status: dict | None = None) -> dict:
    """Describe what this concrete demo actually exposed; never infer from source label.

    `parsed` means the event key was returned by demoparser, even if this match
    happened to contain zero rows. `rows` is occurrence count. This is safer than
    list_game_events(), which is known to under-report valid streams.
    """
    event_names = [
        "player_death", "player_hurt", "weapon_fire", "fire_bullets",
        "player_blind", "player_footstep", "weapon_reload", "weapon_zoom",
        "flashbang_detonate", "smokegrenade_detonate", "hegrenade_detonate",
        "inferno_startburn", "bomb_beginplant", "bomb_planted",
        "bomb_begindefuse", "bomb_defused", "bomb_exploded",
        "round_start", "round_freeze_end", "round_end",
    ]
    streams = {}
    for name in event_names:
        present = name in all_events
        df = all_events.get(name, pd.DataFrame())
        streams[name] = {"parsed": bool(present), "rows": int(len(df)) if present else 0}
    return {
        "event_streams": streams,
        "player_blind_outcomes_available": bool("player_blind" in all_events),
        "footstep_stream_available": bool("player_footstep" in all_events),
        "reload_stream_available": bool("weapon_reload" in all_events),
        "zoom_stream_available": bool("weapon_zoom" in all_events),
        "bomb_beginplant_stream_available": bool("bomb_beginplant" in all_events),
        "bomb_begindefuse_stream_available": bool("bomb_begindefuse" in all_events),
        "usercmd_probe": usercmd_status or {},
        "interpretation": (
            "A missing/unsupported stream is UNKNOWN, never zero. "
            "Use row counts only when parsed=true."
        ),
    }


def build_economy_coaching(econ):
    if econ.empty: return pd.DataFrame()
    df=econ.copy()
    equip_col="current_equip_value" if "current_equip_value" in df.columns else "round_start_equip_value"
    if equip_col not in df.columns: return df
    keys=[k for k in ("tick","total_rounds_played","team_name") if k in df.columns]
    if "team_name" not in keys: return df
    grp=df.groupby(keys,dropna=False)[equip_col]
    df["team_avg_equip_value"]=grp.transform("mean")
    def classify(v):
        if pd.isna(v): return None
        if v>=TEAM_BUY_FULL_AVG_EQUIP: return "full_buy_heuristic"
        if v>=TEAM_BUY_FORCE_AVG_EQUIP: return "force_buy_heuristic"
        if v<TEAM_BUY_ECO_AVG_EQUIP: return "eco_heuristic"
        return "half_buy_heuristic"
    df["team_buy_class_heuristic"]=df["team_avg_equip_value"].map(classify)
    df["buy_class_note"]="heuristic thresholds; use objective balance/equip/inventory columns for final coaching judgment"
    return df


def parse_item_drop_evidence(parser, all_events, notes):
    """Capture item-drop messages plus physical pickup evidence without overclaiming.

    demoparser2 parse_item_drops() exposes CS_UM_SendPlayerItemDrops econ-item
    messages; those are NOT assumed to equal physical weapon transfers. Physical
    item_pickup events are copied separately as evidence for downstream inference.
    """
    try:
        raw=normalize_dataframe(parser.parse_item_drops())
    except Exception as exc:
        raw=pd.DataFrame(); notes["warnings"].append(f"parse_item_drops failed: {exc}")
    pickups=all_events.get("item_pickup",pd.DataFrame()).copy()
    return raw,pickups


# ============================================================
# PLAYER IDENTITY
# ============================================================

def normalize_competitive_players(players: pd.DataFrame) -> pd.DataFrame:
    """Keep exact, nonzero competitive-player identities only."""
    if players is None or players.empty or "steamid" not in players.columns:
        return pd.DataFrame()
    out = players.copy()
    out["steamid"] = pd.Series(out["steamid"].map(_exact_int_scalar), index=out.index, dtype="Int64")
    out = out[out["steamid"].notna() & (out["steamid"] != 0)]
    if "team_number" in out.columns:
        tn = pd.to_numeric(out["team_number"], errors="coerce")
        competitive = tn.isin([2, 3])
        if competitive.any():
            out = out[competitive]
    elif "team_num" in out.columns:
        tn = pd.to_numeric(out["team_num"], errors="coerce")
        competitive = tn.isin([2, 3])
        if competitive.any():
            out = out[competitive]
    return out.drop_duplicates(subset=["steamid"], keep="last").reset_index(drop=True)


def filter_competitive_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Filter tick-state tables to the authoritative competitive roster."""
    if df is None or df.empty or "steamid" not in df.columns or not ROSTER:
        return df
    out = repair_steamids(df.copy(), ROSTER)
    return out[out["steamid"].isin(ROSTER)].copy()


def get_players(parser: DemoParser) -> pd.DataFrame:
    try:
        return normalize_competitive_players(normalize_dataframe(parser.parse_player_info()))
    except Exception as exc:
        print(f"    ERROR: parse_player_info() failed: {exc}")
        return pd.DataFrame()


def fallback_players_from_ticks(parser: DemoParser, base_events: dict, notes: dict) -> pd.DataFrame:
    """Recover/verify the live CT/T competitive roster from round probe ticks."""
    probe_ticks = []
    for name in ("round_freeze_end", "round_start", "round_end"):
        df = base_events.get(name, pd.DataFrame())
        if df.empty or "tick" not in df.columns:
            continue
        vals = pd.to_numeric(df["tick"], errors="coerce").dropna().astype(int).tolist()
        probe_ticks.extend(vals)
    probe_ticks = sorted(set(probe_ticks))
    if not probe_ticks:
        notes["warnings"].append("player roster tick verification unavailable: no round probe ticks")
        return pd.DataFrame()

    try:
        snap = normalize_dataframe(parser.parse_ticks(["team_name"], ticks=probe_ticks))
    except Exception as exc:
        notes["warnings"].append(f"player roster tick verification failed: {exc}")
        return pd.DataFrame()
    if snap.empty or "steamid" not in snap.columns:
        notes["warnings"].append("player roster tick verification returned no steamids")
        return pd.DataFrame()

    snap = snap.copy()
    snap["steamid"] = pd.Series(snap["steamid"].map(_exact_int_scalar), index=snap.index, dtype="Int64")
    snap = snap[snap["steamid"].notna() & (snap["steamid"] != 0)]
    if "team_name" in snap.columns:
        snap = snap[snap["team_name"].isin(["CT", "TERRORIST"])]

    rows = []
    for sid, grp in snap.groupby("steamid", dropna=True):
        names = grp["name"].dropna().astype(str) if "name" in grp.columns else pd.Series(dtype=str)
        teams = grp["team_name"].dropna().astype(str) if "team_name" in grp.columns else pd.Series(dtype=str)
        name = names.iloc[-1] if len(names) else None
        team = teams.iloc[-1] if len(teams) else None
        rows.append({
            "steamid": int(sid), "name": name,
            "team_number": 3 if team == "CT" else (2 if team == "TERRORIST" else None),
        })
    out = normalize_competitive_players(pd.DataFrame(rows))
    notes["roster_fallback_probe_ticks"] = len(probe_ticks)
    notes["roster_fallback_rows"] = len(out)
    return out


def audit_event_steamids(all_events: dict, roster: list[int]) -> list[str]:
    """Return nonzero *competitive coaching-event* IDs outside the roster.

    Plain SourceTV metadata events can legitimately mention non-playing
    controllers. Restrict the invariant to events whose player identities feed
    coaching calculations.
    """
    known = {int(x) for x in roster}
    unexpected = set()
    if not known:
        return []
    relevant = set(RICH_EVENTS) | set(PLACE_EVENTS) | {"bomb_planted"}
    for name, df in all_events.items():
        if name not in relevant or df.empty:
            continue
        for c in df.columns:
            if "steamid" not in str(c).lower():
                continue
            for value in df[c]:
                iv = _as_sid(value)
                if iv not in (None, 0) and iv not in known:
                    unexpected.add(str(iv))
    return sorted(unexpected)


def find_target_steamid(players: pd.DataFrame, target_name: str | None):
    """Return steamid or None.

    Empty / None name → None (full-match mode).
    """
    if not target_name or not str(target_name).strip():
        return None
    if not {"name", "steamid"}.issubset(players.columns):
        print("    ERROR: parse_player_info() missing name/steamid columns.")
        return None
    matches = players[players["name"].astype(str).str.casefold()
                      == target_name.strip().casefold()]
    if matches.empty:
        print(f"    WARNING: could not find player '{target_name}'.")
        return None
    return int(str(matches.iloc[0]["steamid"]))


# ============================================================
# MATCH START / ROUND TABLE
# ============================================================

def find_true_match_start_tick(rs: pd.DataFrame, re_df: pd.DataFrame | None = None) -> tuple:
    """Return the real match/segment boundary from round structure.

    The key segment test is not merely a short 1->N gap: it is a short gap with
    *no completed round in between*.  That prevents an unusually short but real
    round/forfeit from being mistaken for a SourceTV continuation snapshot.
    """
    if rs.empty or "tick" not in rs.columns:
        return None, "none"
    s = rs.sort_values("tick").copy()
    short_gap_ticks = int(5 * TICKRATE)

    def completed_between(lo, hi):
        if re_df is None or re_df.empty or "tick" not in re_df.columns:
            return False
        q = re_df[(pd.to_numeric(re_df["tick"], errors="coerce") > lo) &
                  (pd.to_numeric(re_df["tick"], errors="coerce") < hi)]
        if "winner" in q.columns:
            q = q[q["winner"].isin(["CT", "T"])]
        return not q.empty

    if "round" in s.columns:
        rnum = pd.to_numeric(s["round"], errors="coerce")
        ones = s[rnum == 1]
        if not ones.empty:
            # SourceTV split files can append a synthetic round-1 reset AFTER
            # the final completed round of the segment.  Such a row is a state
            # handoff marker, not the beginning of playable data. Prefer the
            # latest round-1 candidate that actually has a completed round_end
            # after it; this still chooses the final FACEIT restart when several
            # round-1 resets exist before live play.
            eligible = ones
            if re_df is not None and not re_df.empty and "tick" in re_df.columns:
                completed = re_df.copy()
                if "winner" in completed.columns:
                    completed = completed[completed["winner"].isin(["CT", "T"])]
                if not completed.empty:
                    max_completed_tick = pd.to_numeric(completed["tick"], errors="coerce").max()
                    q = ones[pd.to_numeric(ones["tick"], errors="coerce") < max_completed_tick]
                    if not q.empty:
                        eligible = q
            candidate_tick = int(eligible.iloc[-1]["tick"])
            after = s[(pd.to_numeric(s["tick"], errors="coerce") > candidate_tick) &
                      (pd.to_numeric(s["round"], errors="coerce") > 1)]
            if not after.empty:
                nxt_tick = int(after.iloc[0]["tick"])
                if (0 <= nxt_tick-candidate_tick <= short_gap_ticks and
                        not completed_between(candidate_tick, nxt_tick)):
                    return nxt_tick, "continued segment: stale round-1 snapshot skipped"
            return candidate_tick, "last round==1 restart/reset"

    if "total_rounds_played" in s.columns:
        trp = pd.to_numeric(s["total_rounds_played"], errors="coerce")
        zeros = s[trp == 0]
        if not zeros.empty:
            eligible = zeros
            if re_df is not None and not re_df.empty and "tick" in re_df.columns:
                completed = re_df.copy()
                if "winner" in completed.columns:
                    completed = completed[completed["winner"].isin(["CT", "T"])]
                if not completed.empty:
                    max_completed_tick = pd.to_numeric(completed["tick"], errors="coerce").max()
                    q = zeros[pd.to_numeric(zeros["tick"], errors="coerce") < max_completed_tick]
                    if not q.empty:
                        eligible = q
            candidate_tick = int(eligible.iloc[-1]["tick"])
            after = s[(pd.to_numeric(s["tick"], errors="coerce") > candidate_tick) &
                      (pd.to_numeric(s["total_rounds_played"], errors="coerce") > 0)]
            if not after.empty:
                nxt_tick = int(after.iloc[0]["tick"])
                if (0 <= nxt_tick-candidate_tick <= short_gap_ticks and
                        not completed_between(candidate_tick, nxt_tick)):
                    return nxt_tick, "continued segment: stale TRP=0 snapshot skipped"
            return candidate_tick, "last total_rounds_played==0 round_start"
        return int(s["tick"].iloc[0]), "first recorded round_start (nonzero round offset)"

    live = s[is_live_match(s)]
    if not live.empty:
        return int(live["tick"].min()), "first live round_start (weak fallback)"
    return int(s["tick"].min()), "first round_start (weakest fallback)"


def infer_parser_rounds_from_round_ends(re2: pd.DataFrame) -> list[int]:
    """Infer absolute parser-round indices while preserving continued segments.

    Explicit round_end.total_rounds_played is authoritative (minus one because
    round_end is post-round). Missing values are filled from neighboring explicit
    indices rather than falling back to zero-based position, which would silently
    renumber a continued SourceTV segment.
    """
    vals = []
    if "total_rounds_played" in re2.columns:
        for v in re2["total_rounds_played"]:
            vals.append(None if _is_missing_scalar(v) else int(v) - 1)
    else:
        vals = [None] * len(re2)
    explicit = [i for i,v in enumerate(vals) if v is not None]
    if not explicit:
        return list(range(len(vals)))
    first = explicit[0]
    for i in range(first-1, -1, -1):
        vals[i] = vals[i+1] - 1
    for i in range(first+1, len(vals)):
        if vals[i] is None:
            vals[i] = vals[i-1] + 1
    return [int(v) for v in vals]


def build_round_table(parser, target_steamid, base_events: dict):
    """Build a match-centric round table, including continued SourceTV segments.

    `parser_round` is the absolute `total_rounds_played` index used by ordinary
    events.  For a normal demo it begins at 0.  For a continued segment it can
    begin above 0; `segment_round` is always 1..N within the current file.
    """
    rs = base_events.get("round_start", pd.DataFrame())
    rf = base_events.get("round_freeze_end", pd.DataFrame())
    re_ = base_events.get("round_end", pd.DataFrame())

    meta = dict(
        schema_version=SCHEMA_VERSION,
        tickrate=TICKRATE,
        start_tick=None,
        end_tick=None,
        n_rounds=0,
        match_start_method=None,
        segment_start_parser_round=None,
        segment_end_parser_round=None,
        is_continued_segment=False,
        my_score=None,
        opp_score=None,
        target_steamid=str(target_steamid) if target_steamid else None,
    )

    if rs.empty or re_.empty:
        print("    WARNING: round_start/round_end missing — cannot build round table.")
        return pd.DataFrame(), meta, {}

    match_start_tick, method = find_true_match_start_tick(rs, re_)
    meta["match_start_method"] = method
    if match_start_tick is None:
        print("    WARNING: could not locate match/segment start — aborting round table.")
        return pd.DataFrame(), meta, {}

    re2 = re_[re_["tick"] >= match_start_tick].copy()
    if "winner" in re2.columns:
        re2 = re2[re2["winner"].isin(["CT", "T"])]
    re2 = (re2.sort_values("tick")
              .drop_duplicates(subset="tick", keep="first")
              .reset_index(drop=True))
    if re2.empty:
        return pd.DataFrame(), meta, {}

    rs2 = rs[rs["tick"] >= match_start_tick].sort_values("tick").reset_index(drop=True)
    rf2 = (rf[rf["tick"] >= match_start_tick].sort_values("tick").reset_index(drop=True)
           if not rf.empty else pd.DataFrame())

    # round_end.total_rounds_played is post-round; ordinary events in that round
    # use one less.  This gives us an absolute parser-round index even when a
    # SourceTV file begins in the middle of a map.
    parser_rounds = infer_parser_rounds_from_round_ends(re2)

    start_by_round = (dict(zip(pd.to_numeric(rs2["total_rounds_played"], errors="coerce"),
                               pd.to_numeric(rs2["tick"], errors="coerce")))
                      if not rs2.empty and "total_rounds_played" in rs2.columns else {})
    freeze_by_round = (dict(zip(pd.to_numeric(rf2["total_rounds_played"], errors="coerce"),
                                pd.to_numeric(rf2["tick"], errors="coerce")))
                       if not rf2.empty and "total_rounds_played" in rf2.columns else {})

    probe_by_round = {}
    for ridx in parser_rounds:
        t = freeze_by_round.get(ridx, start_by_round.get(ridx))
        if pd.notna(t) if t is not None else False:
            probe_by_round[ridx] = int(t)
    missing_probe = [r for r in parser_rounds if r not in probe_by_round]
    if missing_probe:
        print(f"    NOTE: no freeze_end or round_start tick for parser round(s) "
              f"{missing_probe} — side/result cannot be resolved there.")

    side_by_round_player = {}
    my_clan = None
    if probe_by_round:
        try:
            side_df = normalize_dataframe(parser.parse_ticks(
                ["team_name", "team_clan_name", "total_rounds_played"],
                ticks=list(probe_by_round.values())))
            if not side_df.empty and "steamid" in side_df.columns:
                side_df = filter_competitive_rows(side_df)
                for _, row in side_df.iterrows():
                    if pd.isna(row.get("steamid")) or pd.isna(row.get("total_rounds_played")):
                        continue
                    ridx = int(row["total_rounds_played"])
                    sid = int(row["steamid"])
                    team = row.get("team_name")
                    if pd.notna(team) and team in ("CT", "TERRORIST"):
                        side_by_round_player[(ridx, sid)] = team
                if target_steamid and "team_clan_name" in side_df.columns:
                    tgt_rows = side_df[side_df["steamid"] == target_steamid]
                    vals = tgt_rows["team_clan_name"].dropna().unique()
                    my_clan = vals[0] if len(vals) else None
        except Exception as exc:
            print(f"    WARNING: could not resolve sides for players: {exc}")

    plants = base_events.get("bomb_planted", pd.DataFrame())
    plant_by_round = {}
    if not plants.empty and "total_rounds_played" in plants.columns:
        for _, pr in plants[plants["tick"] >= match_start_tick].iterrows():
            site = _coalesce(pr.get("user_last_place_name"), pr.get("site"))
            plant_by_round[int(pr["total_rounds_played"])] = (int(pr["tick"]), site)

    rows = []
    my_wins = opp_wins = 0
    for segment_idx, (_, end_row) in enumerate(re2.iterrows(), start=1):
        winner = end_row.get("winner")
        if pd.isna(winner):
            continue
        ridx = parser_rounds[segment_idx - 1]
        start_tick = start_by_round.get(ridx)
        freeze_tick = freeze_by_round.get(ridx)
        end_tick = int(end_row["tick"])
        plant_tick, plant_site = plant_by_round.get(ridx, (None, None))

        ct_after = end_row.get("ct_team_rounds_total")
        t_after = end_row.get("t_team_rounds_total")
        ct_before = ct_after
        t_before = t_after
        try:
            if winner == "CT" and pd.notna(ct_before):
                ct_before = int(ct_before) - 1
            elif winner == "T" and pd.notna(t_before):
                t_before = int(t_before) - 1
        except Exception:
            pass

        row = dict(
            round=ridx + 1,              # absolute match round when TRP is available
            segment_round=segment_idx,   # 1..N inside this demo file
            parser_round=ridx,           # join key for ordinary events
            start_tick=int(start_tick) if pd.notna(start_tick) else None,
            freeze_end_tick=int(freeze_tick) if pd.notna(freeze_tick) else None,
            end_tick=end_tick,
            duration_s=round((end_tick - freeze_tick) / TICKRATE, 2)
                       if freeze_tick is not None and pd.notna(freeze_tick) else None,
            winner=winner,
            reason=end_row.get("reason"),
            bomb_plant_tick=plant_tick,
            bomb_plant_site=plant_site,
            ct_score_before=ct_before,
            t_score_before=t_before,
            ct_score_after=ct_after,
            t_score_after=t_after,
            ct_team_clan_name=end_row.get("ct_team_clan_name"),
            t_team_clan_name=end_row.get("t_team_clan_name"),
            round_observation_complete=(
                not _is_missing_scalar(start_tick) and not _is_missing_scalar(freeze_tick)
            ),
        )

        if target_steamid is not None:
            side = side_by_round_player.get((ridx, target_steamid))
            result = None
            if pd.notna(side) and pd.notna(winner):
                won = (side == "CT" and winner == "CT") or (side == "TERRORIST" and winner == "T")
                result = "WIN" if won else "LOSS"
                my_wins += 1 if won else 0
                opp_wins += 0 if won else 1
            row["my_side"] = side
            row["result"] = result

        rows.append(row)

    rounds_df = pd.DataFrame(rows)
    if not rounds_df.empty:
        start_pr = int(rounds_df["parser_round"].min())
        end_pr = int(rounds_df["parser_round"].max())
        meta.update(
            start_tick=match_start_tick,
            end_tick=int(re2.iloc[-1]["tick"]),
            n_rounds=len(rounds_df),
            my_team_clan=my_clan,
            segment_start_parser_round=start_pr,
            segment_end_parser_round=end_pr,
            is_continued_segment=bool(start_pr > 0),
            side_score_semantics=(
                "ct/t score columns belong to the team currently occupying that side; "
                "they can swap at halftime/overtime. Use ct_team_clan_name/"
                "t_team_clan_name when fixed team identity is available."
            ),
        )
    if target_steamid is not None:
        meta["my_score"] = my_wins
        meta["opp_score"] = opp_wins
    return rounds_df, meta, side_by_round_player


def build_player_rounds(rounds_df: pd.DataFrame,
                        side_by_round_player: dict,
                        players: pd.DataFrame) -> pd.DataFrame:
    """One explicit row per roster player per extracted round.

    Missing side information is represented as observed_at_probe=False with
    side/result null, rather than silently omitting the player-round pair.
    """
    if rounds_df.empty or players.empty or "steamid" not in players.columns:
        return pd.DataFrame()
    roster = []
    seen = set()
    for _, p in players.iterrows():
        sid = _as_sid(p.get("steamid"))
        if sid is None or sid in seen:
            continue
        seen.add(sid)
        roster.append((sid, p.get("name")))
    rows=[]
    for _, rnd in rounds_df.iterrows():
        ridx=int(rnd["parser_round"]); winner=rnd.get("winner")
        for sid,name in roster:
            team=side_by_round_player.get((ridx,sid))
            observed=pd.notna(team)
            result=None
            if observed and pd.notna(winner):
                won=(team=="CT" and winner=="CT") or (team=="TERRORIST" and winner=="T")
                result="WIN" if won else "LOSS"
            rows.append({
                "round":rnd["round"], "segment_round":rnd.get("segment_round"),
                "parser_round":ridx, "steamid":sid, "name":name,
                "observed_at_probe":bool(observed), "side":team if observed else None,
                "result":result,
            })
    return pd.DataFrame(rows)


# ============================================================
# GRENADES -> compact throw table
# ============================================================

def build_grenade_tables(parser, start_tick, end_tick):
    """Compact projectile trajectories, splitting recycled entity IDs into runs.

    Entity IDs can be recycled for the same grenade type later in a match, so
    `(entity_id, type)` alone is not a unique throw key. A new throw instance is
    started whenever the same key has a tick gap >2.
    """
    try:
        g = normalize_dataframe(parser.parse_grenades())
    except Exception as exc:
        print(f"    WARNING: parse_grenades() failed: {exc}")
        return pd.DataFrame(), pd.DataFrame()
    if g.empty:
        return pd.DataFrame(), pd.DataFrame()
    if start_tick is not None and end_tick is not None and "tick" in g.columns:
        g = g[(g["tick"] >= start_tick) & (g["tick"] <= end_tick)]
    needed = {"grenade_type", "grenade_entity_id", "tick", "x", "y", "z"}
    if not needed.issubset(g.columns):
        return pd.DataFrame(), pd.DataFrame()
    proj = g[g["grenade_type"].astype(str).str.endswith("Projectile") & g["x"].notna()].copy()
    if proj.empty:
        return pd.DataFrame(), pd.DataFrame()
    proj = proj.sort_values(["grenade_entity_id", "grenade_type", "tick"]).reset_index(drop=True)
    base = ["grenade_entity_id", "grenade_type"]
    gap = proj.groupby(base)["tick"].diff()
    new_run = gap.isna() | (gap > 2) | (gap <= 0)
    proj["throw_instance"] = new_run.groupby([proj[c] for c in base]).cumsum().astype(int)
    key = base + ["throw_instance"]
    first = proj.groupby(key, as_index=False).first()
    last = proj.groupby(key, as_index=False).last()
    first_cols = key + [c for c in ("steamid", "name", "tick", "x", "y", "z") if c in first.columns]
    throws = first[first_cols].rename(columns={
        "tick":"throw_tick", "x":"throw_x", "y":"throw_y", "z":"throw_z"})
    last_cols = key + [c for c in ("tick", "x", "y", "z") if c in last.columns]
    throws = throws.merge(last[last_cols].rename(columns={
        "tick":"land_tick", "x":"land_x", "y":"land_y", "z":"land_z"}), on=key, how="left")
    if {"throw_tick", "land_tick"}.issubset(throws.columns):
        throws["flight_s"] = ((throws["land_tick"] - throws["throw_tick"]) / TICKRATE).round(2)
    paths = pd.DataFrame()
    if GRENADE_PATH_EVERY:
        paths = proj[proj["tick"] % GRENADE_PATH_EVERY == 0].copy()
    return throws, paths



def clean_segment_snapshot_artifacts(events: dict, meta: dict, notes: dict) -> dict:
    """Remove non-gameplay entity-snapshot events at a continued SourceTV boundary.

    Observed in a real HLTV p2 segment: at the first segment tick the demo emitted
    ten self/world deaths, ten one-point self-hurts, twenty spawns, dozens of item
    pickups, and bomb ownership transitions simultaneously.  These reconstruct
    entity state; they are not ten real kills at the start of the round.

    Cleanup is intentionally conservative.  It activates only for a continued
    segment and only when >=5 same-tick self/world death rows prove that a bulk
    snapshot artifact is present.
    """
    if not meta.get("is_continued_segment") or meta.get("start_tick") is None:
        return events

    out = {k: v.copy() for k, v in events.items()}
    deaths = out.get("player_death", pd.DataFrame())
    if deaths.empty or "tick" not in deaths.columns:
        return out

    start_tick = int(meta["start_tick"])
    at_start = deaths[pd.to_numeric(deaths["tick"], errors="coerce") == start_tick].copy()
    if at_start.empty:
        return out

    artifact_mask = []
    for _, row in at_start.iterrows():
        weapon = str(row.get("weapon", "") or "").casefold()
        a_sid = _as_sid(row.get("attacker_steamid"))
        u_sid = _as_sid(row.get("user_steamid"))
        a_name = row.get("attacker_name")
        u_name = row.get("user_name")
        same_identity = (
            (a_sid is not None and u_sid is not None and a_sid == u_sid) or
            (pd.notna(a_name) and pd.notna(u_name) and str(a_name) == str(u_name))
        )
        artifact_mask.append(weapon == "world" and same_identity)

    artifact_count = int(sum(artifact_mask))
    if artifact_count < 5:
        return out

    removable_at_boundary = {
        "player_death", "player_hurt", "player_spawn", "item_pickup",
        "item_equip", "bomb_dropped", "bomb_pickup",
    }
    removed = {}
    for name in removable_at_boundary:
        d = out.get(name, pd.DataFrame())
        if d.empty or "tick" not in d.columns:
            continue
        tickmask = pd.to_numeric(d["tick"], errors="coerce") == start_tick
        n = int(tickmask.sum())
        if n:
            out[name] = d.loc[~tickmask].copy()
            removed[name] = n

    # Winner-less round_end at the same tick is also a snapshot placeholder.
    re_df = out.get("round_end", pd.DataFrame())
    if not re_df.empty and "tick" in re_df.columns:
        tickmask = pd.to_numeric(re_df["tick"], errors="coerce") == start_tick
        nullwinner = re_df["winner"].isna() if "winner" in re_df.columns else pd.Series(False, index=re_df.index)
        rm = tickmask & nullwinner
        n = int(rm.sum())
        if n:
            out["round_end"] = re_df.loc[~rm].copy()
            removed["round_end_null_winner"] = n

    notes["segment_snapshot_artifact_tick"] = start_tick
    notes["segment_snapshot_artifact_signature_world_self_deaths"] = artifact_count
    notes["segment_snapshot_rows_removed"] = removed
    return out




def sanitize_clipped_events(events: dict, notes: dict) -> dict:
    """Remove known non-gameplay round_end placeholders/duplicates universally."""
    out = {k: v.copy() for k, v in events.items()}
    re_df = out.get("round_end", pd.DataFrame())
    if not re_df.empty and "tick" in re_df.columns:
        before = len(re_df)
        if "winner" in re_df.columns:
            re_df = re_df[re_df["winner"].notna()]
        re_df = re_df.sort_values("tick").drop_duplicates(subset=["tick"], keep="first")
        removed = before - len(re_df)
        if removed:
            notes["round_end_placeholder_rows_removed"] = int(removed)
        out["round_end"] = re_df.reset_index(drop=True)
    return out


def parse_scoreboard_snapshots(parser, rounds_df: pd.DataFrame, end_tick, notes: dict):
    """Return pre-segment baseline, end scoreboard, and cumulative segment deltas."""
    if rounds_df.empty or end_tick is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    first = rounds_df.iloc[0]
    baseline_tick = _coalesce(first.get("freeze_end_tick"), first.get("start_tick"))
    if baseline_tick is None:
        notes["warnings"].append("scoreboard segment baseline unavailable: no first-round probe tick")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        start = normalize_dataframe(parser.parse_ticks(SCOREBOARD_PROPS, ticks=[int(baseline_tick)]))
        end = normalize_dataframe(parser.parse_ticks(SCOREBOARD_PROPS, ticks=[int(end_tick)]))
        start = filter_competitive_rows(start)
        end = filter_competitive_rows(end)
        notes["dropped_props"]["scoreboard"] = report_dropped_props(end, SCOREBOARD_PROPS, "scoreboard")
    except Exception as exc:
        notes["warnings"].append(f"scoreboard snapshots failed: {exc}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if start.empty or end.empty or "steamid" not in start.columns or "steamid" not in end.columns:
        return start, end, pd.DataFrame()
    base_cols = [c for c in ("steamid", "name", "team_name", "team_clan_name") if c in end.columns]
    delta = end[base_cols].copy()
    start_idx = start.set_index("steamid")
    end_idx = end.set_index("steamid")
    for prop in SCOREBOARD_DELTA_PROPS:
        if prop not in end_idx.columns or prop not in start_idx.columns:
            continue
        end_vals = pd.to_numeric(end_idx[prop], errors="coerce")
        start_vals = pd.to_numeric(start_idx[prop], errors="coerce")
        d = end_vals.subtract(start_vals, fill_value=0)
        mapper = d.to_dict()
        delta[f"{prop}_segment"] = delta["steamid"].map(mapper)
    delta["segment_baseline_tick"] = int(baseline_tick)
    delta["segment_end_tick"] = int(end_tick)
    return start, end, delta


def estimate_demo_tickrate(event_tables: dict):
    """Estimate ticks/second from event tick and game_time deltas when available."""
    samples = []
    for name in ("weapon_fire", "player_hurt", "player_death"):
        df = event_tables.get(name, pd.DataFrame())
        if df.empty or not {"tick", "game_time"}.issubset(df.columns):
            continue
        q = df[["tick", "game_time"]].copy()
        q["tick"] = pd.to_numeric(q["tick"], errors="coerce")
        q["game_time"] = pd.to_numeric(q["game_time"], errors="coerce")
        q = q.dropna().drop_duplicates().sort_values("tick")
        if len(q) < 2:
            continue
        dtick = q["tick"].diff()
        dtime = q["game_time"].diff()
        ratios = (dtick / dtime).where((dtick > 0) & (dtime > 0.05))
        samples.extend(ratios.dropna().tolist())
    if not samples:
        return None
    s = pd.Series(samples, dtype="float64")
    s = s[(s > 1) & (s < 512)]
    return None if s.empty else float(s.median())

def classify_demo_source(header: dict) -> str:
    """Conservative source-family label from header strings."""
    server = str(header.get("server_name", "") or "").casefold()
    client = str(header.get("client_name", "") or "").casefold()
    if "faceit" in server:
        return "faceit_sourcetv"
    if "valve counter-strike 2" in server:
        return "valve_premier_or_mm_sourcetv"
    if "sourceTV".casefold() in client or "sourcetv" in client:
        if any(x in server for x in ("esl", "blast", "pgl", "starladder")):
            return "tournament_sourcetv"
        return "sourcetv_unknown"
    return "unknown"


def infer_map_completion(rounds_df: pd.DataFrame, source_family: str = "unknown") -> tuple:
    """Return (complete_likely, method) with source-aware overtime semantics."""
    if rounds_df.empty:
        return None, "no_rounds"
    last=rounds_df.iloc[-1]
    reason=str(_coalesce(last.get("reason"), ""))
    if reason in ("t_surrender","ct_surrender"):
        return True,"surrender"
    ct=last.get("ct_score_after"); tt=last.get("t_score_after")
    if pd.isna(ct) or pd.isna(tt):
        return None,"score_unavailable"
    hi,lo=max(int(ct),int(tt)),min(int(ct),int(tt))
    if hi==13 and lo<=11:
        return True,"regulation_score"
    if hi<13:
        if source_family == "valve_premier_or_mm_sourcetv" and hi==12 and lo==12:
            return None,"valve_12_12_mode_ambiguous"
        return False,"score_below_regulation_win"
    # Valve Premier has one MR3 overtime; 15-15 is a completed draw.  Valve's
    # original CS2 announcement specifies a six-round overtime for Premier, and
    # current Premier references continue to describe the 15-15 draw endpoint.
    if source_family == "valve_premier_or_mm_sourcetv" and hi==15 and lo==15:
        return True,"premier_15_15_draw"
    if lo>=12:
        if hi==lo and source_family not in ("faceit_sourcetv","tournament_sourcetv","valve_premier_or_mm_sourcetv"):
            return None,"unknown_source_overtime_tie"
        block=max(0,(lo-12)//3)
        threshold=16+3*block; losing_ceiling=14+3*block
        if hi>=threshold and lo<=losing_ceiling:
            return True,"overtime_score"
        return False,"overtime_not_finished"
    return None,"unrecognized_score_state"


def validate_extraction(rounds_df, player_rounds, players, clipped_events, positions,
                        scoreboard_delta, econ, engagements, meta, unexpected_ids):
    """Adversarial structural/identity audit before player-level coaching is trusted."""
    errors = []; warnings = []; metrics = {}
    def err(code, detail): errors.append({"code": code, "detail": detail})
    def warn(code, detail): warnings.append({"code": code, "detail": detail})

    roster = []
    if not players.empty and "steamid" in players.columns:
        roster = sorted({_as_sid(x) for x in players["steamid"] if _as_sid(x) is not None})
    metrics["roster_size"] = len(roster)
    if not roster: err("roster_empty", "No exact competitive roster available")
    if len(roster) != 10:
        warn("roster_size_not_10", f"{len(roster)} unique competitive SteamIDs; substitution/partial metadata may explain this")

    if rounds_df.empty:
        err("round_table_empty", "No completed competitive rounds were reconstructed")
    else:
        prs = pd.to_numeric(rounds_df["parser_round"], errors="coerce").dropna().astype(int).tolist()
        if prs and prs != list(range(prs[0], prs[0] + len(prs))):
            err("parser_round_gap", f"parser_round sequence is not consecutive: {prs}")
        ends = pd.to_numeric(rounds_df["end_tick"], errors="coerce")
        if ends.isna().any() or not ends.is_monotonic_increasing or ends.duplicated().any():
            err("round_end_tick_order", "round end ticks must be unique and strictly increasing")
        for _, r in rounds_df.iterrows():
            st, fr, en = r.get("start_tick"), r.get("freeze_end_tick"), r.get("end_tick")
            if not _is_missing_scalar(st) and not _is_missing_scalar(en) and int(st) > int(en):
                err("round_tick_order", f"start>end in parser_round {r.get('parser_round')}")
            if not _is_missing_scalar(fr) and not _is_missing_scalar(en) and int(fr) > int(en):
                err("round_tick_order", f"freeze_end>end in parser_round {r.get('parser_round')}")
            winner = r.get("winner")
            if winner not in ("CT", "T"):
                err("invalid_round_winner", f"winner={winner!r} in parser_round {r.get('parser_round')}")

            # Each row's before/after score must differ by exactly the winning
            # side. This remains valid across halftime because both before/after
            # refer to the side labels *for this round*, not fixed team identity.
            cb, tb = r.get("ct_score_before"), r.get("t_score_before")
            ca, ta = r.get("ct_score_after"), r.get("t_score_after")
            if all(not _is_missing_scalar(x) for x in (cb, tb, ca, ta)) and winner in ("CT", "T"):
                cb, tb, ca, ta = map(int, (cb, tb, ca, ta))
                expected_ca = cb + (1 if winner == "CT" else 0)
                expected_ta = tb + (1 if winner == "T" else 0)
                if (ca, ta) != (expected_ca, expected_ta):
                    err("round_score_progression",
                        f"parser_round {r.get('parser_round')}: before={cb}-{tb}, winner={winner}, after={ca}-{ta}")
                pr = r.get("parser_round")
                if not _is_missing_scalar(pr) and ca + ta != int(pr) + 1:
                    err("round_score_total",
                        f"parser_round {pr}: side scores sum to {ca+ta}, expected {int(pr)+1}")

    if unexpected_ids:
        err("unexpected_event_steamids", f"non-roster event IDs remain after precision repair: {unexpected_ids}")

    if not rounds_df.empty and roster:
        expected = len(roster) * len(rounds_df)
        metrics["player_round_rows_expected"] = expected
        metrics["player_round_rows_actual"] = len(player_rounds)
        if len(player_rounds) != expected:
            err("player_round_coverage", f"expected {expected} roster×round rows, got {len(player_rounds)}")
        if not player_rounds.empty:
            dup = int(player_rounds.duplicated(["parser_round", "steamid"]).sum())
            if dup: err("player_round_duplicates", f"{dup} duplicate player-round keys")
            bad = player_rounds[player_rounds["side"].isna() & player_rounds["result"].notna()]
            if len(bad): err("result_without_side", f"{len(bad)} rows have a result with unresolved side")
            winners = dict(zip(rounds_df["parser_round"], rounds_df["winner"]))
            inconsistent = 0
            for _, prr in player_rounds[player_rounds["side"].notna() & player_rounds["result"].notna()].iterrows():
                winner = winners.get(prr.get("parser_round"))
                side = prr.get("side")
                expected_result = "WIN" if ((side == "CT" and winner == "CT") or
                                             (side == "TERRORIST" and winner == "T")) else "LOSS"
                if prr.get("result") != expected_result:
                    inconsistent += 1
            if inconsistent:
                err("player_round_result_inconsistent", f"{inconsistent} player-round rows contradict side + round winner")
            if "observed_at_probe" in player_rounds.columns:
                obs = player_rounds.groupby("parser_round")["observed_at_probe"].sum()
                under = obs[obs < min(10, len(roster))]
                if len(under):
                    warn("round_player_probe_undercoverage", f"{len(under)} rounds observe fewer than {min(10,len(roster))} competitive players at probe tick")

    start, end = meta.get("start_tick"), meta.get("end_tick")
    out_of_window = 0
    if start is not None and end is not None:
        for df in clipped_events.values():
            if df.empty or "tick" not in df.columns: continue
            ticks = pd.to_numeric(df["tick"], errors="coerce")
            out_of_window += int(((ticks < int(start)) | (ticks > int(end))).fillna(False).sum())
    metrics["event_rows_outside_match_window"] = out_of_window
    if out_of_window: err("event_clip_failure", f"{out_of_window} event rows remain outside match window")

    # Critical event schema: plausible-looking empty columns are more dangerous than a crash.
    deaths = clipped_events.get("player_death", pd.DataFrame())
    if not deaths.empty:
        needed = {"tick", "attacker_steamid", "user_steamid", "weapon"}
        missing = sorted(needed - set(deaths.columns))
        if missing: err("player_death_schema", f"missing critical columns: {missing}")

    hurts = clipped_events.get("player_hurt", pd.DataFrame())
    if not hurts.empty:
        needed = {"tick", "attacker_steamid", "user_steamid"}
        missing = sorted(needed - set(hurts.columns))
        if missing: err("player_hurt_schema", f"missing critical columns: {missing}")
        if not ({"dmg_health_capped"}.issubset(hurts.columns) or {"user_health", "health"}.issubset(hurts.columns)):
            err("player_hurt_damage_schema", "cannot reconstruct capped effective damage")

    fires = clipped_events.get("weapon_fire", pd.DataFrame())
    if not fires.empty:
        needed = {"tick", "user_steamid"}
        missing = sorted(needed - set(fires.columns))
        if missing: err("weapon_fire_schema", f"missing critical columns: {missing}")

    if not positions.empty and "steamid" in positions.columns and roster:
        posids = {_as_sid(x) for x in positions["steamid"] if _as_sid(x) is not None}
        extra = sorted(posids - set(roster))
        if extra: err("position_non_roster_ids", f"position table contains non-roster IDs: {extra}")
        if "tick" in positions.columns and len(positions):
            mx = int(positions.groupby("tick")["steamid"].nunique().max())
            metrics["max_unique_position_players_per_tick"] = mx
            if mx > len(roster): err("position_player_count", f"position tick has {mx} players but roster has {len(roster)}")

    pvp = 0
    event_kills = defaultdict(int)          # scoreboard-creditable enemy kills
    event_deaths = defaultdict(int)
    teamkill_count = 0
    unknown_relation_kills = 0
    if not deaths.empty:
        for _, d in deaths.iterrows():
            a = _as_sid(d.get("attacker_steamid")); v = _as_sid(d.get("user_steamid"))
            if v in roster:
                event_deaths[v] += 1
            if a is not None and v is not None and a != v and a in roster and v in roster:
                pvp += 1
                at = d.get("attacker_team_name")
                vt = d.get("user_team_name")
                if pd.notna(at) and pd.notna(vt):
                    if at == vt:
                        teamkill_count += 1
                    else:
                        event_kills[a] += 1
                else:
                    # Relation is genuinely unresolved. Count it for engagement
                    # coverage but do not pretend the engine scoreboard credits it.
                    unknown_relation_kills += 1
    metrics["pvp_deaths"] = pvp
    metrics["teamkills"] = teamkill_count
    metrics["pvp_kills_unknown_team_relation"] = unknown_relation_kills

    if engagements is not None and not engagements.empty:
        if {"death_tick", "victim_steamid"}.issubset(engagements.columns):
            dup = int(engagements.duplicated(["death_tick", "victim_steamid"]).sum())
            if dup: err("engagement_duplicate_death", f"{dup} duplicate engagement death keys")
    if pvp and (engagements is None or len(engagements) != pvp):
        warn("engagement_coverage", f"{0 if engagements is None else len(engagements)} engagement rows for {pvp} attributed non-self deaths")

    # Segment scoreboard deltas are the only fair comparison for HLTV p2-style files.
    if scoreboard_delta is None or scoreboard_delta.empty:
        warn("scoreboard_segment_delta_unavailable", "No segment scoreboard delta available for event cross-check")
    else:
        neg = 0
        for c in scoreboard_delta.columns:
            if c.endswith("_segment"):
                vals = pd.to_numeric(scoreboard_delta[c], errors="coerce")
                # score can legitimately fall after penalties; other cumulative counters should not.
                if c != "score_segment": neg += int((vals < 0).fillna(False).sum())
        if neg: warn("negative_scoreboard_delta", f"{neg} negative cumulative scoreboard delta cells")
        kill_mismatch = death_mismatch = 0
        if "steamid" in scoreboard_delta.columns:
            for _, r in scoreboard_delta.iterrows():
                sid = _as_sid(r.get("steamid"))
                if sid is None: continue
                if "kills_total_segment" in r.index and not _is_missing_scalar(r.get("kills_total_segment")):
                    if int(round(float(r["kills_total_segment"]))) != event_kills.get(sid, 0): kill_mismatch += 1
                if "deaths_total_segment" in r.index and not _is_missing_scalar(r.get("deaths_total_segment")):
                    if int(round(float(r["deaths_total_segment"]))) != event_deaths.get(sid, 0): death_mismatch += 1
        if kill_mismatch:
            detail = f"{kill_mismatch} player kill deltas differ from reconstructed enemy-kill events"
            if unknown_relation_kills:
                detail += f"; {unknown_relation_kills} PvP kills had unresolved team relation"
            warn("scoreboard_kill_mismatch", detail)
        if death_mismatch: warn("scoreboard_death_mismatch", f"{death_mismatch} player death deltas differ from reconstructed death events")

    tickrate_est = estimate_demo_tickrate(clipped_events)
    metrics["estimated_tickrate_from_events"] = tickrate_est
    if tickrate_est is None:
        warn("tickrate_unverified", "Could not independently estimate tickrate from event game_time")
    elif abs(tickrate_est - TICKRATE) > 0.05:
        err("tickrate_mismatch", f"configured {TICKRATE}, event-derived median {tickrate_est:.4f}")

    metrics["hard_error_count"] = len(errors)
    metrics["warning_count"] = len(warnings)
    return {"integrity_ok": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def run_internal_self_tests():
    """Fast deterministic regression tests for previously observed failure modes."""
    # Missing-side result bug.
    rr=pd.DataFrame([{"round":1,"segment_round":1,"parser_round":0,"winner":"CT"}])
    pp=pd.DataFrame([{"steamid":1,"name":"p"}])
    out=build_player_rounds(rr,{(0,1):float("nan")},pp)
    assert len(out)==1 and pd.isna(out.iloc[0]["result"]) and not bool(out.iloc[0]["observed_at_probe"])

    # SteamID precision: preserve exact text and repair one float-rounded value.
    sid=76561198058500492
    x=repair_steamids(pd.DataFrame({"steamid":[str(sid),float(sid),None]}),[sid])
    assert int(x.iloc[0]["steamid"])==sid and int(x.iloc[1]["steamid"])==sid and pd.isna(x.iloc[2]["steamid"])

    # Premier-style genuine round 1: is_match_started is irrelevant structurally.
    rs=pd.DataFrame([{"tick":65,"round":1,"total_rounds_played":0,"is_match_started":False},
                     {"tick":5000,"round":2,"total_rounds_played":1,"is_match_started":True}])
    re=pd.DataFrame([{"tick":4000,"winner":"CT","total_rounds_played":1}])
    assert find_true_match_start_tick(rs,re)[0]==65

    # Continued SourceTV snapshot: stale round 1 followed immediately by round 3,
    # with no completed round in between.
    rs2=pd.DataFrame([{"tick":1,"round":1,"total_rounds_played":0},
                      {"tick":5,"round":3,"total_rounds_played":2}])
    assert find_true_match_start_tick(rs2,pd.DataFrame(columns=["tick","winner"]))[0]==5

    # A genuinely very short round must not be mistaken for a segment if a
    # completed round_end exists between the starts.
    rs3=pd.DataFrame([{"tick":1,"round":1,"total_rounds_played":0},
                      {"tick":100,"round":2,"total_rounds_played":1}])
    re3=pd.DataFrame([{"tick":50,"winner":"CT","total_rounds_played":1}])
    assert find_true_match_start_tick(rs3,re3)[0]==1

    # SourceTV p1 can append a synthetic round-1 reset after the final completed
    # round. It must not replace the real segment start.
    rs4=pd.DataFrame([
        {"tick":1,"round":1,"total_rounds_played":0},
        {"tick":6247,"round":2,"total_rounds_played":1},
        {"tick":12473,"round":3,"total_rounds_played":2},
        {"tick":21080,"round":4,"total_rounds_played":3},
        {"tick":26158,"round":5,"total_rounds_played":4},
        {"tick":30663,"round":1,"total_rounds_played":0},
    ])
    re4=pd.DataFrame([
        {"tick":5927,"winner":"CT","total_rounds_played":1},
        {"tick":12153,"winner":"CT","total_rounds_played":2},
        {"tick":20760,"winner":"CT","total_rounds_played":3},
        {"tick":25838,"winner":"CT","total_rounds_played":4},
    ])
    assert find_true_match_start_tick(rs4,re4)[0]==1

    assert _coalesce(pd.NA,"fallback")=="fallback"
    assert infer_map_completion(pd.DataFrame([{"reason":"","ct_score_after":15,"t_score_after":15}]),
                                "valve_premier_or_mm_sourcetv")[0] is True
    return True


def write_batch_validation_summary(output_dir: Path):
    rows=[]
    for p in sorted(output_dir.glob("*/match_summary.json")):
        try:
            m=json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"demo":p.parent.name,"read_error":str(exc),"valid":False,"integrity_ok":False})
            continue
        rows.append({
            "demo":p.parent.name,
            "source":m.get("demo_source_family"),
            "map":m.get("map_name"),
            "rounds":m.get("n_rounds"),
            "valid":m.get("valid"),
            "integrity_ok":m.get("integrity_ok"),
            "map_complete_likely":m.get("map_complete_likely"),
            "contains_full_match_likely":m.get("contains_full_match_likely"),
            "continued_segment":m.get("is_continued_segment"),
            "integrity_error_count":len(m.get("integrity_errors") or []),
            "integrity_warning_count":len(m.get("integrity_warnings") or []),
            "general_warning_count":len((m.get("notes") or {}).get("warnings") or []),
        })
    failed=[r for r in rows if not r.get("valid") or not r.get("integrity_ok")]
    summary={
        "schema_version":SCHEMA_VERSION,
        "demos_seen":len(rows),
        "valid_demos":sum(bool(r.get("valid")) for r in rows),
        "integrity_ok_demos":sum(bool(r.get("integrity_ok")) for r in rows),
        "failed_or_invalid_demos":[r.get("demo") for r in failed],
        "all_clear":bool(rows) and not failed,
        "demos":rows,
    }
    write_json(summary,output_dir/"batch_validation_summary.json")
    return summary


# ============================================================
# MAIN PER-DEMO PIPELINE
# ============================================================

def analyze_demo(demo_path: Path) -> bool:
    print(f"\n{'='*80}\nDEMO: {demo_path.name}\n{'='*80}")
    final_out_dir = OUTPUT_DIR / demo_path.stem
    out_dir = OUTPUT_DIR / f".{demo_path.stem}.v75_tmp"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    invalid_out_dir = OUTPUT_DIR / f"{demo_path.stem}__INVALID_v77"
    if invalid_out_dir.exists():
        shutil.rmtree(invalid_out_dir)
    # Parse transactionally into a temporary directory.  A failed rerun must
    # not destroy the last known-good extraction for this demo.  The previous
    # directory is replaced only after every parse + integrity check succeeds.
    out_dir.mkdir(parents=True, exist_ok=True)

    notes = {"dropped_props": {}, "empty_events": [], "warnings": []}
    econ = pd.DataFrame(); ticks = pd.DataFrame()
    scoreboard_start = scoreboard = scoreboard_delta = pd.DataFrame()
    engagements = pd.DataFrame()

    try:
        parser = DemoParser(str(demo_path))
        try:
            header = parser.parse_header()
            write_json(header, out_dir / "header.json")
            print(f"Map: {header.get('map_name','?')}  Patch: {header.get('patch_version','?')}")
        except Exception as exc:
            print(f"ERROR: header parse failed: {exc}")
            shutil.rmtree(out_dir, ignore_errors=True)
            return False

        try:
            available = sorted(parser.list_game_events())
            write_json(available, out_dir / "available_events.json")
        except Exception:
            available = None

        global ROSTER
        primary_players = get_players(parser)
        ROSTER = ([int(x) for x in primary_players["steamid"].dropna()]
                  if "steamid" in primary_players.columns else [])
        notes["roster_source"] = "parse_player_info" if ROSTER else "pending_tick_verification"

        print("Parsing rich events...")
        rich = safe_parse_events(parser, RICH_EVENTS, player=PLAYER_EXTRA, other=GAME_STATE_OTHER)
        if "player_death" in rich:
            notes["dropped_props"]["player_extra"] = report_dropped_props(
                rich["player_death"], PLAYER_EXTRA, "player_death player=")
            notes["dropped_props"]["game_state"] = report_dropped_props(
                rich["player_death"], GAME_STATE_OTHER, "player_death other=")

        print("Parsing positional events...")
        place_wanted = [e for e in PLACE_EVENTS
                        if e in CORE_EVENTS or available is None or e in available]
        place = safe_parse_events(parser, place_wanted, player=PLACE_PROPS, other=GAME_STATE_OTHER)

        print("Parsing plain events...")
        plain_wanted = [e for e in PLAIN_EVENTS
                        if e in CORE_EVENTS or available is None or e in available]
        plain = safe_parse_events(parser, plain_wanted, other=GAME_STATE_OTHER)

        all_events = {**rich, **place, **plain}
        if "round_end" in all_events:
            all_events["round_end"] = normalize_round_end(all_events["round_end"])

        # Live CT/T state is the authoritative competitive roster when available.
        # End-of-match metadata can be absent on HLTV segments or theoretically
        # contain non-playing observers/coaches. Use metadata only to fill names.
        tick_players = fallback_players_from_ticks(parser, all_events, notes)
        players = primary_players.copy()
        if not tick_players.empty:
            primary_names = {}
            if not primary_players.empty and {"steamid", "name"}.issubset(primary_players.columns):
                for sid, name in zip(primary_players["steamid"], primary_players["name"]):
                    ss = _as_sid(sid)
                    if ss is not None and not _is_missing_scalar(name): primary_names[ss] = name
            for idx, row in tick_players.iterrows():
                if _is_missing_scalar(row.get("name")):
                    sid = _as_sid(row.get("steamid"))
                    if sid in primary_names: tick_players.at[idx, "name"] = primary_names[sid]
            primary_ids = set(int(x) for x in primary_players.get("steamid", pd.Series(dtype="Int64")).dropna())
            tick_ids = set(int(x) for x in tick_players["steamid"].dropna())
            notes["primary_roster_only_ids"] = sorted(str(x) for x in primary_ids - tick_ids)
            notes["tick_roster_only_ids"] = sorted(str(x) for x in tick_ids - primary_ids)
            players = normalize_competitive_players(tick_players)
            notes["roster_source"] = ("parse_ticks_fallback" if primary_players.empty
                                      else "parse_ticks_competitive_verified")
        else:
            players = normalize_competitive_players(primary_players)
        ROSTER = [int(x) for x in players.get("steamid", pd.Series(dtype="Int64")).dropna()]
        notes["roster_size"] = len(ROSTER)
        save_df(players, out_dir / "players.csv")
        print(f"  competitive roster: {len(ROSTER)} players ({notes['roster_source']})")

        target_steamid = find_target_steamid(players, TARGET_PLAYER)
        if TARGET_PLAYER and str(TARGET_PLAYER).strip():
            print(f"Target: {TARGET_PLAYER} ({target_steamid or 'NOT FOUND'})")
        else:
            print("Target: (full-match mode — no privileged player)")

        all_events = {k: repair_steamids(v, ROSTER) for k, v in all_events.items()}
        unexpected_ids = []  # audited only after match clipping/snapshot cleanup
        all_events["player_hurt"] = add_effective_damage(all_events.get("player_hurt", pd.DataFrame()))

        rounds_df, meta, side_by_round_player = build_round_table(parser, target_steamid, all_events)
        source_family = classify_demo_source(header)
        complete_likely, completion_method = infer_map_completion(rounds_df, source_family)
        meta["map_complete_likely"] = complete_likely
        meta["map_completion_method"] = completion_method
        meta["contains_full_match_likely"] = bool(complete_likely) and not bool(meta.get("is_continued_segment"))
        meta["demo_source_family"] = source_family
        save_df(rounds_df, out_dir / "rounds.csv")
        start_tick, end_tick = meta.get("start_tick"), meta.get("end_tick")
        print(f"Rounds: {meta.get('n_rounds',0)}  (start via {meta.get('match_start_method')})")

        player_rounds = build_player_rounds(rounds_df, side_by_round_player, players)
        save_df(player_rounds, out_dir / "player_rounds.csv")
        print(f"  player_rounds: {len(player_rounds):,} rows")

        def clip(df):
            if df.empty or "tick" not in df.columns or start_tick is None or end_tick is None:
                return df
            t = pd.to_numeric(df["tick"], errors="coerce")
            return df[(t >= int(start_tick)) & (t <= int(end_tick))].copy()

        clipped_events = {name: clip(df) for name, df in all_events.items()}
        clipped_events = clean_segment_snapshot_artifacts(clipped_events, meta, notes)
        clipped_events = sanitize_clipped_events(clipped_events, notes)
        unexpected_ids = audit_event_steamids(clipped_events, ROSTER)
        notes["unexpected_non_roster_event_steamids"] = unexpected_ids
        if unexpected_ids:
            notes["warnings"].append(
                f"{len(unexpected_ids)} nonzero coaching-event SteamID(s) are not in the competitive roster")
        for name, df in clipped_events.items():
            if df.empty: notes["empty_events"].append(name)
            save_df(df, out_dir / "events" / f"{name}.csv.gz")
            print(f"  {name}: {len(df):,} rows")

        scoreboard_start, scoreboard, scoreboard_delta = parse_scoreboard_snapshots(
            parser, rounds_df, end_tick, notes)
        save_df(scoreboard, out_dir / "scoreboard.csv")
        if not scoreboard_start.empty: save_df(scoreboard_start, out_dir / "scoreboard_segment_start.csv")
        if not scoreboard_delta.empty: save_df(scoreboard_delta, out_dir / "scoreboard_segment_delta.csv")
        print(f"  scoreboard: end={len(scoreboard)} | segment_delta={len(scoreboard_delta)}")

        try:
            rf = clipped_events.get("round_freeze_end", pd.DataFrame())
            if not rf.empty and "tick" in rf.columns:
                econ = normalize_dataframe(parser.parse_ticks(
                    ECONOMY_PROPS, ticks=pd.to_numeric(rf["tick"], errors="coerce").dropna().astype(int).tolist()))
                econ = filter_competitive_rows(econ)
                save_df(econ, out_dir / "economy.csv")
                print(f"  economy: {len(econ):,} rows")
        except Exception as exc:
            notes["warnings"].append(f"economy snapshot failed: {exc}")

        if ENABLE_GRENADE_ENTITY_PARSE:
            throws, paths = build_grenade_tables(parser, start_tick, end_tick)
            save_df(throws, out_dir / "grenade_throws.csv")
            if not paths.empty: save_df(paths, out_dir / "grenade_paths.csv.gz")
            print(f"  grenade_throws: {len(throws):,} | paths: {len(paths):,}")
        else:
            print("  grenade entity trajectories: skipped in batch profile")

        try:
            if start_tick is not None and end_tick is not None:
                first_sample = int(start_tick) + ((-int(start_tick)) % TICK_SAMPLE_EVERY)
                sample_ids = list(range(first_sample, int(end_tick)+1, TICK_SAMPLE_EVERY))
                ticks = normalize_dataframe(parser.parse_ticks(TICK_PROPS, ticks=sample_ids))
                ticks = filter_competitive_rows(ticks)
                ticks = clip(ticks)
            save_df(ticks, out_dir / "player_positions.csv.gz")
            print(f"  player_positions: {len(ticks):,} rows")
        except Exception as exc:
            notes["warnings"].append(f"player_positions parse failed: {exc}")

        dense_ticks = build_dense_tick_list(clipped_events, start_tick, end_tick) if ENABLE_ENGAGEMENT_SUMMARIES else []
        notes["dense_ticks_requested"] = len(dense_ticks)
        dense = parse_dense_state(parser, dense_ticks, notes) if ENABLE_ENGAGEMENT_SUMMARIES else pd.DataFrame()
        if SAVE_RAW_DENSE_TICKS: save_df(dense, out_dir / "dense_engagement_ticks.csv.gz")
        print(f"  dense engagement state: {len(dense):,} rows across {len(dense_ticks):,} ticks"
              + (" [saved]" if SAVE_RAW_DENSE_TICKS else " [derived only]"))

        usercmd_df, usercmd_status = parse_usercmd_state(parser, dense_ticks, start_tick, end_tick, notes)
        if SAVE_RAW_USERCMD_TICKS: save_df(usercmd_df, out_dir / "usercmd_ticks.csv.gz")
        write_json(usercmd_status, out_dir / "usercmd_availability.json")
        notes["usercmd"] = usercmd_status
        write_json(build_source_capabilities(clipped_events, usercmd_status),
                   out_dir / "source_capabilities.json")
        print(f"  usercmd {USERCMD_MODE}: {len(usercmd_df):,} rows | props "
              f"{len(usercmd_status.get('available_props',[]))}/{len(usercmd_status.get('requested_props',[]))}")

        engagements = build_engagements(dense, clipped_events, players)
        save_df(engagements, out_dir / "coaching" / "engagements.csv")
        utility = build_utility_effectiveness(clipped_events)
        save_df(utility, out_dir / "coaching" / "utility_effectiveness.csv")
        econ_coaching = build_economy_coaching(econ)
        save_df(econ_coaching, out_dir / "coaching" / "economy_decisions.csv")
        if ENABLE_ECON_ITEM_DROP_PARSE:
            item_drop_raw, physical_pickups = parse_item_drop_evidence(parser, clipped_events, notes)
            save_df(item_drop_raw, out_dir / "coaching" / "econ_item_drops_raw.csv")
            if DEEP_MODE: save_df(physical_pickups, out_dir / "coaching" / "physical_item_pickups.csv")
        else:
            print("  econ item-drop message parse: skipped in batch profile")

        write_json({
            "geometry_policy": GEOMETRY_POLICY,
            "coaching_profile": COACHING_PROFILE,
            "raw_dense_saved": SAVE_RAW_DENSE_TICKS,
            "usercmd_mode": USERCMD_MODE,
            "raw_usercmd_saved": SAVE_RAW_USERCMD_TICKS,
            "grenade_entity_parse": ENABLE_GRENADE_ENTITY_PARSE,
            "engagement_visibility_semantics": "approximate_spotted_by is approximate; missing visibility is unknown, not zero",
            "engagement_window_semantics": "3-second pre-death windows are left-censored; exact latency is null when contact/burst may predate the window",
            "utility_semantics": "enemy/team/self/unknown utility outcomes are separated; enemy_utility_damage is coaching-relevant confirmed enemy HE+fire damage",
            "scoreboard_semantics": "scoreboard.csv is cumulative engine state at segment end; scoreboard_segment_delta subtracts first-round pre-combat state",
            "item_drop_semantics": "batch skips CS_UM_SendPlayerItemDrops; physical item_pickup/item_remove events remain under events/",
            "economy_semantics": "buy classes are transparent heuristics; raw balance/equipment/inventory remain authoritative",
        }, out_dir / "coaching" / "methodology.json")
        print(f"  coaching: engagements={len(engagements):,} utility={len(utility):,} economy={len(econ_coaching):,}")

        validation = validate_extraction(
            rounds_df, player_rounds, players, clipped_events, ticks,
            scoreboard_delta, econ, engagements, meta, unexpected_ids)
        write_json(validation, out_dir / "integrity_checks.json")
        meta["coaching_valid"] = bool(validation["integrity_ok"])
        meta["integrity_hard_failure_count"] = len(validation["errors"])
        meta["integrity_soft_warning_count"] = len(validation["warnings"])
        if validation["errors"]:
            notes["warnings"].append(
                f"integrity audit has {len(validation['errors'])} hard failure(s); player-level coaching unsafe")
        print(f"  integrity: hard={len(validation['errors'])} warnings={len(validation['warnings'])}")

        round_table_valid = bool(meta.get("n_rounds"))
        target_valid = True
        if target_steamid is not None:
            resolved = int(player_rounds[(player_rounds["steamid"] == target_steamid) &
                                         player_rounds["result"].notna()].shape[0]) if not player_rounds.empty else 0
            target_valid = resolved == int(meta.get("n_rounds", 0))
        elif TARGET_PLAYER and str(TARGET_PLAYER).strip():
            target_valid = False
        meta["round_table_valid"] = round_table_valid
        meta["valid"] = bool(round_table_valid and validation["integrity_ok"] and target_valid)
        if not meta["valid"]:
            notes["warnings"].append("demo failed final validity gate; do not aggregate as canonical coaching data")

        meta["target_player"] = TARGET_PLAYER if (TARGET_PLAYER and str(TARGET_PLAYER).strip()) else None
        meta["target_steamid"] = str(target_steamid) if target_steamid else None
        meta["map_name"] = header.get("map_name")
        meta["runtime_environment"] = runtime_environment_metadata()
        meta["notes"] = notes
        write_json(meta, out_dir / "match_summary.json")

        if not meta["valid"]:
            invalid_out_dir = OUTPUT_DIR / f"{demo_path.stem}__INVALID_v77"
            if invalid_out_dir.exists():
                shutil.rmtree(invalid_out_dir)
            out_dir.replace(invalid_out_dir)
            print(f"INVALID OUTPUT (canonical output preserved): {invalid_out_dir}")
            return False

        if final_out_dir.exists():
            shutil.rmtree(final_out_dir)
        out_dir.replace(final_out_dir)
        print(f"Output: {final_out_dir}")
        return True

    except Exception as exc:
        print(f"\nERROR ANALYZING {demo_path.name}\n{type(exc).__name__}: {exc}")
        traceback.print_exc()
        shutil.rmtree(out_dir, ignore_errors=True)
        return False


def main():
    if RUN_INTERNAL_SELF_TESTS:
        run_internal_self_tests()
        print("Internal regression self-tests: PASS")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    demos = sorted(DEMO_DIR.glob("*.dem"))
    if not demos:
        print(f"No .dem files found in: {DEMO_DIR.resolve()}")
        return

    # Clean stale temporary directories only.  Never delete completed match
    # outputs merely because the current DEMO_DIR contains a subset of demos.
    for child in OUTPUT_DIR.iterdir():
        if child.is_dir() and child.name.startswith(".") and ".v75_tmp" in child.name:
            shutil.rmtree(child, ignore_errors=True)

    print(f"Found {len(demos)} demo(s). Mode: " +
          (f"target={TARGET_PLAYER}" if TARGET_PLAYER else "full-match"))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "runtime_environment": runtime_environment_metadata(),
        "tickrate": TICKRATE,
        "target_player": TARGET_PLAYER if TARGET_PLAYER else None,
        "extraction_mode": "single-target" if TARGET_PLAYER else "full-match",
        "tick_sample_every": TICK_SAMPLE_EVERY,
        "round_clock": "t_into_round = game_time - round_start_time (seconds)",
        "round_join_key": (
            "Combat/objective/in-round events generally use total_rounds_played == rounds.parser_round. "
            "Post-round lifecycle events such as round_end/round_officially_ended report parser_round+1. "
            "Prefer rounds.csv tick bounds or event-specific semantics."),
        "steamid_warning": "SteamID64 must remain string/Int64; float64 is rejected/repaired only against the exact roster.",
        "full_match_mode_note": "player_rounds.csv carries explicit roster×round rows; unresolved side/result remains null.",
        "multisource_note": "live CT/T tick state verifies the competitive roster; continued SourceTV segments preserve absolute parser rounds.",
        "map_completeness_note": "valid/coaching_valid are distinct from contains_full_match_likely.",
        "segment_snapshot_note": "continued SourceTV boundary reconstruction rows are removed only under a conservative bulk self/world-death signature.",
        "scoreboard_segment_note": "segment deltas subtract the first-round pre-combat snapshot to avoid inheriting earlier rounds in p2-style files.",
        "integrity_note": "Every match writes integrity_checks.json; hard failures set match_summary.valid=false.",
        "v7_coaching_profile": COACHING_PROFILE,
        "v7_dense_engagements": {"enabled": ENABLE_ENGAGEMENT_SUMMARIES, "save_raw": SAVE_RAW_DENSE_TICKS,
                                  "batch_pre_death_s": DENSE_PRE_DEATH_S, "props": DENSE_PLAYER_PROPS},
        "v7_usercmd_probe": {"enabled": ENABLE_USERCMD_PROBE, "mode": USERCMD_MODE,
                              "probe_tick_count": USERCMD_PROBE_COUNT, "save_raw": SAVE_RAW_USERCMD_TICKS,
                              "heavy_history_enabled": ENABLE_HEAVY_USERCMD_HISTORY,
                              "probe_props": USERCMD_PROPS_ALL},
        "v7_grenade_entity_parse": {"enabled": ENABLE_GRENADE_ENTITY_PARSE, "path_downsample_every": GRENADE_PATH_EVERY},
        "geometry_policy": GEOMETRY_POLICY,
    }
    write_json(manifest, OUTPUT_DIR / "manifest.json")

    results = []
    for demo in demos:
        ok = bool(analyze_demo(demo))
        rec = {"demo": demo.name, "stem": demo.stem, "success": ok}
        canonical_sm = OUTPUT_DIR / demo.stem / "match_summary.json"
        invalid_dir = OUTPUT_DIR / f"{demo.stem}__INVALID_v77"
        invalid_sm = invalid_dir / "match_summary.json"

        # Read only the output produced by *this* run.  If current extraction
        # failed integrity, do not accidentally report an older canonical
        # directory that was intentionally preserved.
        sm_path = canonical_sm if ok else (invalid_sm if invalid_sm.exists() else None)
        if sm_path is not None and sm_path.exists():
            try:
                sm = json.loads(sm_path.read_text(encoding="utf-8"))
                rec["output_kind"] = "canonical" if ok else "invalid_quarantine"
                rec["output_path"] = str(sm_path.parent)
                for key in ("valid", "round_table_valid", "coaching_valid", "map_complete_likely",
                            "contains_full_match_likely", "integrity_hard_failure_count",
                            "integrity_soft_warning_count", "demo_source_family"):
                    rec[key] = sm.get(key)
            except Exception as exc:
                rec["summary_read_error"] = str(exc)
        elif not ok:
            rec["output_kind"] = "parse_exception_or_abort"
        results.append(rec)

    failures = [r for r in results if not r["success"] and r.get("output_kind") == "parse_exception_or_abort"]
    invalid = [r for r in results if r.get("output_kind") == "invalid_quarantine"]
    write_json({
        "schema_version": SCHEMA_VERSION,
        "runtime_environment": runtime_environment_metadata(),
        "demo_count": len(results),
        "success_count": len([r for r in results if r.get("success")]),
        "failure_count": len(failures),
        "invalid_count": len(invalid),
        "results": results,
    }, OUTPUT_DIR / "batch_run_summary.json")

    canonical_count = len([r for r in results if r.get("success")])
    print(f"\n{'='*80}\nBATCH CANONICAL: {canonical_count}/{len(results)} valid outputs\n{'='*80}")
    if failures:
        print("FAILED DEMOS: " + ", ".join(r["demo"] for r in failures))
    if invalid:
        print("INVALID/COACHING-UNSAFE DEMOS: " + ", ".join(r["demo"] for r in invalid))
    if not failures and not invalid:
        print("ALL CURRENT-RUN DEMOS PASSED HARD INTEGRITY GATES")
        print(f"Zip it up with:  zip -r {OUTPUT_DIR}.zip {OUTPUT_DIR}/")
    else:
        print("DO NOT TREAT THIS BATCH AS CANONICAL until FAILED/INVALID demos are reviewed.")


if __name__ == "__main__":
    main()
