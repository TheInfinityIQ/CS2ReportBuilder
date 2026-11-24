from unittest import TestCase

from soundscape_assets import bed_events, resolve_bed


class SoundscapeTests(TestCase):
    def test_declared_reference_uses_persistent_bed_and_rejects_cycles(self):
        script = (
            '{\n\troom =\n\t{\n\t\tsoundevent_01 =\n\t\t[\n'
            '\t\t\t"cycle", "airplane", "inside",\n\t\t]\n\t}\n'
            '\tcycle =\n\t{\n\t\tsoundevent_01 =\n\t\t[\n'
            '\t\t\t"room",\n\t\t]\n\t}\n'
            '\tairplane =\n\t{\n\t\tretrigger_interval_min = 5.0\n'
            '\t\tvsnd_files_track_01 =\n\t\t[\n\t\t\t"sounds/ambient/exterior_01.vsnd",\n\t\t]\n\t}\n'
            '\tinside =\n\t{\n\t\tvsnd_files_track_01 =\n\t\t[\n'
            '\t\t\t"sounds/ambient/interior_02.vsnd",\n\t\t]\n\t}\n}'
        )
        entries = {'sounds/ambient/exterior_01.vsnd_c', 'sounds/ambient/interior_02.vsnd_c'}
        self.assertEqual(resolve_bed('room',bed_events(script),entries),'sounds/ambient/interior_02.vsnd')
