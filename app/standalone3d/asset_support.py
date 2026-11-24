"""Repair optional export omissions in our cache; never write installed assets."""
import json
from pathlib import Path
import struct
import zlib


def repair_optional_textures(glb):
    """A missing packed ORM can safely use occlusion=1, roughness=1, metal=0.

    Source2Viewer occasionally references an ORM image it did not emit. Keep
    actual color/normal omissions as errors rather than silently inventing art.
    """
    glb = Path(glb)
    with glb.open('rb') as stream:
        if stream.read(4) != b'glTF':
            raise ValueError('Invalid exported map.')
        stream.seek(12)
        size, kind = struct.unpack('<II', stream.read(8))
        if kind != 0x4E4F534A or size > 64 * 1024**2:
            raise ValueError('Invalid map metadata.')
        document = json.loads(stream.read(size))
    repaired = []
    for item in document.get('images', []):
        uri = item.get('uri', '')
        if not uri or uri.startswith('data:'):
            continue
        target = (glb.parent / uri).resolve()
        if not target.is_relative_to(glb.parent.resolve()):
            raise ValueError('An exported texture escapes the private map cache.')
        if target.is_file():
            continue
        if '_orm_' not in target.name or target.suffix.lower() != '.png':
            raise ValueError('The map reader did not export texture ' + target.name)
        def chunk(tag, data):
            return (struct.pack('>I', len(data)) + tag + data
                    + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'\x89PNG\r\n\x1a\n'
                          + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress(b'\0\xff\xff\0'))
                          + chunk(b'IEND', b''))
        repaired.append(uri)
    return repaired
