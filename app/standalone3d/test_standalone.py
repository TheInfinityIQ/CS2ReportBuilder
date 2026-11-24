"""Recording integrity, cache boundaries and a real recorded-player fixture."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import backend
import launcher
from asset_support import repair_optional_textures


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def completed_demo():
    payload = b'\x0d' + struct.pack('<f', 60) + b'\x10' + varint(3840)
    return b'PBDEMS2\0' + struct.pack('<II', 16, 0) + b'\x02\0' + varint(len(payload)) + payload


def glb_with_images(path, images):
    payload = json.dumps({'asset': {'version': '2.0'}, 'images': images}).encode()
    payload += b' ' * (-len(payload) % 4)
    path.write_bytes(b'glTF' + struct.pack('<III', 2, 20 + len(payload), len(payload))
                     + b'JSON' + payload)


class RecordingTests(unittest.TestCase):
    def setUp(self):
        fixtures = backend.CACHE / 'test-fixtures'
        fixtures.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_completed_cs2_duration(self):
        path = self.root / 'match.dem'; path.write_bytes(completed_demo())
        self.assertEqual(backend.file_info(path), {'seconds': 60, 'ticks': 3840, 'tickrate': 64})

    def test_truncated_and_legacy_recordings_fail(self):
        path = self.root / 'match.dem'
        for contents in [b'HL2DEMO\0' + b'\0' * 100, completed_demo()[:-2], b'PBDEMS2\0']:
            with self.subTest(contents=contents[:8]):
                path.write_bytes(contents)
                with self.assertRaises(ValueError): backend.file_info(path)

    def test_unterminated_integer_is_bounded(self):
        with self.assertRaises(ValueError): backend.variable(io.BytesIO(b'\xff' * 100))

    def test_library_excludes_missing_partial_and_non_demo_files(self):
        (self.root / 'map/player').mkdir(parents=True)
        good = self.root / 'map/player/game.dem'; good.write_bytes(completed_demo())
        (self.root / 'partial.dem.part').write_bytes(completed_demo())
        (self.root / 'legacy.dem').write_bytes(b'HL2DEMO\0')
        (self.root / 'missing-analysis.json').write_text('{}')
        result = backend.downloaded_demos(self.root)
        self.assertEqual([r['path'] for r in result], [str(good.resolve())])
        good.unlink()
        self.assertEqual(backend.downloaded_demos(self.root), [])

    def test_map_names_cannot_escape_installation(self):
        for name in ['../secrets', 'de_dust2/../../escape', 'C:\\escape', 'x' * 65]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                backend.asset_identity(self.root, name)

    def test_texture_grant_expires_after_asset_change(self):
        maps = self.root / 'csgo/maps'; maps.mkdir(parents=True)
        source = maps / 'de_dust2.vpk'; source.write_bytes(b'asset revision 1')
        with patch.object(backend, 'CACHE', self.root / 'cache'):
            _, geometry_key, evidence = backend.asset_identity(self.root, 'de_dust2')
            backend.save(backend.CACHE / 'settings.json', {
                'texture_grants': {'de_dust2': backend.asset_stamp(evidence)}})
            _, textured_key, _ = backend.asset_identity(self.root, 'de_dust2')
            self.assertNotEqual(geometry_key, textured_key)
            self.assertTrue(backend.texture_granted('de_dust2', evidence))
            source.write_bytes(b'asset revision 2')
            _, changed_key, new_evidence = backend.asset_identity(self.root, 'de_dust2')
            self.assertFalse(backend.texture_granted('de_dust2', new_evidence))
            self.assertNotEqual(changed_key, textured_key)

    def test_optional_orm_fallback_is_valid_and_idempotent(self):
        glb = self.root / 'world.glb'
        glb_with_images(glb, [{'uri': 'test_orm_123.png'}])
        self.assertEqual(repair_optional_textures(glb), ['test_orm_123.png'])
        png = (self.root / 'test_orm_123.png').read_bytes()
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(repair_optional_textures(glb), [])

    def test_missing_color_and_escaping_textures_fail(self):
        glb = self.root / 'world.glb'
        for uri in ['missing_color.png', '../escape_orm_123.png']:
            with self.subTest(uri=uri):
                glb_with_images(glb, [{'uri': uri}])
                with self.assertRaises(ValueError): repair_optional_textures(glb)

    def test_progress_rejects_nan(self):
        with self.assertRaises(ValueError): backend.save(self.root / 'progress.json', {'value': float('nan')})
        self.assertFalse((self.root / 'progress.json').exists())

    def test_renderer_cannot_launch_without_a_toolbox_host(self):
        with patch.object(launcher.subprocess,'Popen') as process:
            with self.assertRaisesRegex(ValueError,'inside CS2 Toolbox'):
                launcher.launch('recording.dem')
            process.assert_not_called()

    def test_steam_runtime_is_preferred_to_an_older_configured_runtime(self):
        steam=self.root/'steam_godot.exe';steam.touch()
        old=self.root/'older_godot.exe';old.touch()
        with patch.object(launcher,'steam_runtimes',return_value=[steam]), \
             patch.object(launcher,'read',return_value={'godot_executable':str(old)}):
            self.assertEqual(launcher.find_godot(),steam.resolve())

    def test_runtime_version_rechecks_after_same_size_update_and_removal(self):
        runtime=self.root/'godot.exe';runtime.write_bytes(b'old')
        launcher._runtime_version.cache_clear()
        self.addCleanup(launcher._runtime_version.cache_clear)
        with patch.object(launcher.subprocess,'check_output',side_effect=['4.7.old\n','4.7.new\n']) as probe:
            self.assertEqual(launcher.runtime_version(runtime),'4.7.old')
            self.assertEqual(launcher.runtime_version(runtime),'4.7.old')
            self.assertEqual(probe.call_count,1)
            stamp=runtime.stat();runtime.write_bytes(b'new')
            os.utime(runtime,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1_000_000_000))
            self.assertEqual(launcher.runtime_version(runtime),'4.7.new')
            self.assertEqual(probe.call_count,2)
            runtime.unlink()
            with self.assertRaises(FileNotFoundError):launcher.runtime_version(runtime)

    def test_failed_runtime_probe_is_not_cached(self):
        runtime=self.root/'godot.exe';runtime.touch()
        launcher._runtime_version.cache_clear()
        self.addCleanup(launcher._runtime_version.cache_clear)
        with patch.object(launcher.subprocess,'check_output',side_effect=[TimeoutError('fixture'),'4.7.ready']) as probe:
            with self.assertRaises(TimeoutError):launcher.runtime_version(runtime)
            self.assertEqual(launcher.runtime_version(runtime),'4.7.ready')
            self.assertEqual(probe.call_count,2)


class RecordedFixtureTests(unittest.TestCase):
    def test_binary_tracks_match_real_demo_ticks_and_stable_identities(self):
        candidates = list((backend.CACHE / 'replays').glob('*/replay.json'))
        if not candidates: self.skipTest('Local recorded fixture is not installed')
        meta = json.loads(max(candidates, key=lambda p: p.stat().st_mtime).read_text(encoding='utf-8'))
        if not Path(meta['source']).is_file(): self.skipTest('Original local recording unavailable')
        sys.path.insert(0, str(backend.ROOT / 'app/extractor/.deps'))
        import numpy as np
        from demoparser2 import DemoParser
        rows = DemoParser(meta['source']).parse_ticks(['X', 'Y', 'Z', 'yaw', 'pitch', 'health', 'team_num', 'is_alive'], ticks=[7000, 7001])
        players = {p['id']: i for i, p in enumerate(meta['players'])}
        self.assertTrue(all(isinstance(identifier, str) and identifier.isdecimal() for identifier in players))
        tracks = Path(meta['tracks']); expected = 24 + meta['frames'] * len(players) * 11 * 4
        self.assertEqual(tracks.stat().st_size, expected)
        data = np.memmap(tracks, dtype='<f4', mode='r', offset=24, shape=(meta['frames'], len(players), 11))
        compared = 0
        for row in rows.to_dict('records'):
            index = int(row['tick']) // meta['step']
            if int(row['tick']) % meta['step']: continue
            slot = players[str(row['steamid'])]
            for field in ['X', 'Y', 'Z', 'yaw', 'pitch', 'health', 'team_num', 'is_alive']:
                self.assertAlmostEqual(float(data[index, slot, backend.FIELDS.index(field)]), float(row[field]), places=3)
            self.assertEqual(float(data[index, slot, 9]), 1)
            compared += 1
        self.assertGreater(compared, 0)
        self.assertFalse(meta['cs2_process_required'])


if __name__ == '__main__': unittest.main()
