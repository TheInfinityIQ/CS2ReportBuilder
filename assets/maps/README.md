# Report map assets

The viewer has 1024 × 1024 base radars and world-coordinate calibration for
Mirage, Nuke, Ancient, Anubis, Overpass, Inferno, Dust2, Vertigo and Train.
`viewer.background()` embeds `<map>.png` using `map-data.json`; new coaching
packets copy this entire assets directory. Rebuild old packets and reports to
include assets added after their creation.

[PROVENANCE.json](PROVENANCE.json) records pinned download URLs, SHA-256 hashes
and the calibration used for the nine base radars and three lower radars.
These are Valve game assets mirrored by
[MurkyYT/cs2-map-icons](https://github.com/MurkyYT/cs2-map-icons), verified against
commit `068761900db687827aae7ea48428296717dbf89d` on 2026-10-07.
Existing base images matched that source byte for byte. Anubis was missing;
its overview specifies origin (-2796, 3328) and scale 5.22.

Nuke, Vertigo and Train also have `_lower.png` files with the same coordinate
transform as their base image. The current viewer does not automatically select
a floor: asset availability is not a floor-selection feature. Train retains
the existing rounded scale 4.082 (upstream 4.082077), including its lower image.
Older demos can contain geometry from earlier map revisions; these assets do
not establish a demo's map version. Cache, Ancient v1 and raw-name aliases are
legacy assets outside this verification.

When replacing an asset, verify its overview coordinates, dimensions and hash,
update provenance and run the map asset checks in `tests/test_viewer.py`.
