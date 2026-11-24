import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

import map_companions as companions
import collision_assets as collision
from backend import save


class CompanionTests(unittest.TestCase):
    def test_changed_map_archive_blocks_collision_before_export(self):
        base=collision.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp, patch.object(collision,'CACHE',Path(temp)), patch.object(collision,'_run') as run:
            root=Path(temp);scene=root/'maps/de_test_revision/world.scn';scene.parent.mkdir(parents=True);scene.write_bytes(b'scene')
            archive=root/'game/csgo/maps/de_test.vpk';archive.parent.mkdir(parents=True);archive.write_bytes(b'new map archive')
            save(scene.parent/'manifest.json',{'map':'de_test','fingerprint':'old','source_files':{str(archive):'old archive digest'}})
            with self.assertRaisesRegex(ValueError,'map archive changed'):collision.prepare_collision(root/'game',scene)
            run.assert_not_called()

    def test_one_selected_map_and_unsupported_warning_is_retained(self):
        base=companions.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp, patch.object(companions,'CACHE',Path(temp)), \
                patch.object(companions,'prepare_collision') as physics, \
                patch.object(companions,'prepare_environment') as environment, \
                patch.object(companions,'prepare_sky',side_effect=ValueError('unsupported source sky')) as sky:
            root=Path(temp);scene=root/'maps/de_test_revision/world.scn';meta={'map':'de_test','fingerprint':'revision'}
            warnings=companions.ensure_companions(root/'game',scene,meta,Mock())
            self.assertIn('original sky',warnings[0]);physics.assert_called_once_with(root/'game',scene)
            self.assertEqual(companions.ensure_companions(root/'game',scene,meta,Mock()),warnings)
            sky.assert_called_once()
            companions.ensure_companions(root/'game',scene,{**meta,'fingerprint':'new revision'},Mock())
            self.assertEqual(sky.call_count,2)


if __name__=='__main__':unittest.main()
