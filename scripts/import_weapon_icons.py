"""Import exact Valve equipment SVGs from an installed CS2 VPK (read-only source)."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from cs2di.report.weapons import _ASSETS  # noqa: E402


def entries(pak: Path):
    data = pak.read_bytes()
    signature, version, tree_size = struct.unpack_from("<III", data)
    if signature != 0x55AA1234 or version not in (1, 2):
        raise ValueError("Unsupported VPK header")
    start = offset = 28 if version == 2 else 12

    def string():
        nonlocal offset
        end = data.index(b"\0", offset)
        value = data[offset:end].decode()
        offset = end + 1
        return value

    while extension := string():
        while directory := string():
            while name := string():
                crc, preload, archive, position, length, terminator = struct.unpack_from("<IHHIIH", data, offset)
                offset += 18
                inline = data[offset:offset + preload]
                offset += preload
                if terminator != 0xffff:
                    raise ValueError("Invalid VPK entry")
                if directory != "panorama/images/icons/equipment" or extension != "vsvg_c":
                    continue
                if name not in set(_ASSETS.values()):
                    continue
                archive_path = pak if archive == 0x7fff else pak.with_name(f"pak01_{archive:03d}.vpk")
                with archive_path.open("rb") as stream:
                    stream.seek(position + (start + tree_size if archive == 0x7fff else 0))
                    content = inline + stream.read(length)
                if zlib.crc32(content) != crc:
                    raise ValueError(f"VPK CRC mismatch: {name}")
                yield name, content


def svg_source(resource: bytes) -> bytes:
    _, header_version, _, blocks_offset, count = struct.unpack_from("<IHHII", resource)
    if header_version != 12:
        raise ValueError("Unsupported resource header")
    for index in range(count):
        entry = 8 + blocks_offset + index * 12
        tag, relative, size = struct.unpack_from("<4sII", resource, entry)
        if tag != b"DATA":
            continue
        block = resource[entry + 4 + relative:entry + 4 + relative + size]
        crc, images = struct.unpack_from("<IH", block)
        if images:
            raise ValueError("Expected standalone SVG without external images")
        source = block[6:]
        if zlib.crc32(source) != crc:
            raise ValueError("SVG CRC mismatch")
        root = ElementTree.fromstring(source)
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("Expected SVG root")
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] in {"script", "image", "foreignObject"}:
                raise ValueError("Expected a static equipment silhouette")
        return source
    raise ValueError("SVG DATA block missing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pak", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=REPO / "assets/weapons")
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    sources = {name: svg_source(content) for name, content in entries(args.pak)}
    missing = set(_ASSETS.values()) - sources.keys()
    if missing:
        raise ValueError(f"Equipment graphics missing: {sorted(missing)}")
    args.out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, source in sorted(sources.items()):
        (args.out / f"{name}.svg").write_bytes(source)
        hashes[name] = hashlib.sha256(source).hexdigest()
    (args.out / "PROVENANCE.json").write_text(json.dumps({
        "owner": "Valve", "app_id": 730, "build_id": args.build_id,
        "source": "game/csgo/pak01_dir.vpk: panorama/images/icons/equipment/*.vsvg_c",
        "method": "VPK and Panorama DATA CRCs checked; original SVG source preserved",
        "svg_sha256": hashes,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(sources)} Valve equipment silhouettes")


if __name__ == "__main__":
    main()
