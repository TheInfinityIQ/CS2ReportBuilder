"""Fail-open and activation gates for the optional world optimization."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import visibility_assets as visibility
from backend import digest, read, save


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        scratch = visibility.CACHE/'validation/visibility-tests'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.assertTrue(Path(self.temporary.name).resolve().is_relative_to(scratch.resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(visibility, 'CACHE', self.cache).start()
        self.scene = self.cache/'maps/de_test_revision/world.scn'
        self.scene.parent.mkdir(parents=True);self.scene.write_bytes(b'prepared scene')
        save(self.scene.parent/'fidelity.json', {'materials': []})
        self.direct = self.cache/'lighting'/self.scene.parent.name/'direct.json'
        save(self.direct, {'lights': []})
        self.folder = self.cache/'visibility'/self.scene.parent.name/'12345678901234567890'
        self.folder.mkdir(parents=True)
        sizes = {'nodes.bin': 12, 'regions.bin': 8, 'masks.bin': 8,
                 'pvs.bin': 512*4098, 'object-visibility.bin': 4096}
        for name, size in sizes.items():(self.folder/name).write_bytes(bytes(size))
        self.data = {'schema': 2, 'algorithm': 2, 'clusters': 4096, 'nodes': 1, 'regions': 1,
                     'masks': 1, 'objects': ['Solid'], 'row_bytes': 1,
                     'source_fingerprint': 'source', 'scene': visibility.scene_identity(self.scene),
                     'material_sha256': digest(self.scene.parent/'fidelity.json'),
                     'light_sha256': digest(self.direct), 'revision': 'revision',
                     'files': {name: digest(self.folder/name) for name in sizes}}
        self.manifest = self.folder/'manifest.json';save(self.manifest, self.data)
        self.report = self.cache/'report.json'

    def report_data(self):
        return {'ok': True, 'playback': {'world_render_audit': {'ok': True, 'revision': 'revision',
                'comparison': 'full_viewport_every_pixel',
                'samples': [{'tick': tick, 'mode': tick % 2, 'player': 0, 'changed_pixels': 0} for tick in range(5)]}}}

    def test_prepared_but_unaudited_cache_is_not_activated(self):
        with self.assertRaisesRegex(ValueError, 'audit required'):
            visibility.validate(self.folder, 'source', self.scene)
        self.assertFalse((self.folder.parent/'active.json').exists())

    def test_matching_full_render_comparison_activates_shared_companion(self):
        save(self.report, self.report_data());visibility.certify(self.manifest, self.report)
        visibility.validate(self.folder, 'source', self.scene)
        self.assertEqual(read(self.folder.parent/'active.json')['manifest'], self.folder.name+'/manifest.json')

    def test_partial_or_failed_comparisons_cannot_activate(self):
        for change in ('failed', 'revision', 'region', 'repeated', 'pixels'):
            with self.subTest(change=change):
                report = self.report_data();audit = report['playback']['world_render_audit']
                if change == 'failed':report['ok'] = False
                if change == 'revision':audit['revision'] = 'old'
                if change == 'region':audit['comparison'] = 'cropped_region'
                if change == 'repeated':audit['samples'] = [audit['samples'][0]]*5
                if change == 'pixels':audit['samples'][0]['changed_pixels'] = 7
                save(self.report, report)
                with self.assertRaises(ValueError):visibility.certify(self.manifest, self.report)
                self.assertFalse((self.folder.parent/'active.json').exists())

    def test_changed_scene_or_lighting_rejects_prior_visibility(self):
        with self.assertRaises(ValueError):visibility.validate(self.folder, 'updated-source', self.scene, verified=False)
        self.direct.write_text('changed lighting')
        with self.assertRaisesRegex(ValueError, 'lighting revision'):
            visibility.validate(self.folder, 'source', self.scene, verified=False)

    def test_changed_binary_is_rejected(self):
        (self.folder/'nodes.bin').write_bytes(bytes([1])+bytes(11))
        with self.assertRaisesRegex(ValueError, 'integrity failure'):
            visibility.validate(self.folder, 'source', self.scene, verified=False)

    def test_light_bounds_cover_supported_clamped_influence(self):
        bounds = visibility.light_bounds({'lights': [
            {'kind': 'unsupported', 'origin': [0, 0, 0], 'range': 1},
            {'kind': 'light_omni2', 'origin': [10, 20, 30], 'range': 100000}]})
        self.assertEqual(len(bounds), 1);self.assertEqual(bounds[0]['path'], '!light:0')
        self.assertAlmostEqual(bounds[0]['max'][0]-10, 60/.0254)


if __name__ == '__main__':unittest.main()
