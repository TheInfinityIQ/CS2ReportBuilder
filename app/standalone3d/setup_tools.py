"""Explicit, pinned setup for the offline map reader. Does not start a game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
CACHE = HERE.parents[1] / 'data/.desktop/standalone3d/tools/Source2Viewer-20.1'
URL = 'https://github.com/ValveResourceFormat/ValveResourceFormat/releases/download/20.1/cli-windows-x64.zip'
SHA256 = '67aaf8a67a85ca60fd09ff343e62103a4cdf3a2d177fc656231d7d734c5b3aa3'
SIZE = 52773073
REQUIRED = {'Source2Viewer-CLI.exe', 'libSkiaSharp.dll', 'spirv-cross.dll'}


def verify(archive):
    sha = hashlib.sha256()
    with Path(archive).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            sha.update(block)
    if sha.hexdigest() != SHA256:
        raise ValueError('Map reader checksum mismatch. Nothing was installed.')
    with zipfile.ZipFile(archive) as bundle:
        if not REQUIRED.issubset(bundle.namelist()):
            raise ValueError('Incomplete map reader archive.')


def install():
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / 'cli-windows-x64.zip'
    if not archive.is_file():
        temporary = archive.with_suffix('.download')
        try:
            with urllib.request.urlopen(URL, timeout=30) as source, temporary.open('wb') as target:
                count = 0
                while block := source.read(1024**2):
                    count += len(block)
                    if count > SIZE:
                        raise ValueError('Unexpected map reader download size.')
                    target.write(block)
            verify(temporary)
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    verify(archive)
    with zipfile.ZipFile(archive) as bundle:
        # Explicit names prevent archive paths from escaping this private folder.
        for name in sorted(REQUIRED):
            if bundle.getinfo(name).file_size > 250 * 1024**2:
                raise ValueError('Unexpected reader component size.')
            target = CACHE / name
            temporary = target.with_suffix(target.suffix + '.pending')
            with bundle.open(name) as source, temporary.open('wb') as destination:
                shutil.copyfileobj(source, destination)
            os.replace(temporary, target)
    (CACHE / 'provenance.json').write_text(json.dumps({
        'name': 'Source2Viewer CLI', 'version': '20.1', 'source': URL,
        'archive_sha256': SHA256,
        'license': 'https://github.com/ValveResourceFormat/ValveResourceFormat/blob/20.1/LICENSE',
    }, indent=2), encoding='utf-8')
    print('Verified offline map reader is ready:', CACHE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        verify(CACHE / 'cli-windows-x64.zip')
        print('Pinned reader archive verified.')
    else:
        install()
