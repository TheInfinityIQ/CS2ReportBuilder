"""SteamID64 handling. IDs are strings/ints only, never floats (KNOWN_PITFALLS #3)."""
from __future__ import annotations

_MIN, _MAX = 76561197960265728, 76561202255233023  # SteamID64 individual-account range


def parse_steamid(value: object) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"SteamID must not be a float/bool: {value!r}")
    try:
        sid = int(str(value).strip())
    except ValueError as e:
        raise ValueError(f"Not a SteamID64: {value!r}") from e
    if sid == 0:
        raise ValueError("SteamID 0 is the world/no-player sentinel, not a player")
    if not _MIN <= sid <= _MAX:
        raise ValueError(f"SteamID64 out of range: {sid}")
    return sid
