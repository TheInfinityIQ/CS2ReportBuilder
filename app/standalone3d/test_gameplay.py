"""Identity, event reconstruction, asset boundaries and prepared-cache reuse."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock

import backend
import gameplay
import stock_assets


class StockGameplayTests(unittest.TestCase):
    def setUp(self):
        base=backend.CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def test_cosmetic_knives_resolve_to_one_stock_asset(self):
        for value in ['M9 Bayonet','Butterfly Knife','Shadow Daggers','weapon_knife_tactical','knife_t']:
            with self.subTest(value=value):self.assertEqual(stock_assets.canonical(value),'knife')
        self.assertEqual(stock_assets.canonical('M4A4'),'m4a1')
        self.assertEqual(stock_assets.canonical('weapon_m4a1_silencer'),'m4a1_silencer')
        self.assertEqual(stock_assets.canonical('Glock-18'),'glock')

    def test_model_header_rejects_invalid_and_excessive_metadata(self):
        file=self.root/'model.glb'
        for payload in [b'not a model',b'glTF'+b'\0'*8+struct.pack('<II',200*1024**2,0x4e4f534a)]:
            file.write_bytes(payload)
            with self.assertRaises(ValueError):stock_assets.gltf_info(file)

    def test_prepared_states_reuse_without_parsing(self):
        states=self.root/'gameplay.bin'
        states.write_bytes(struct.pack('<4sIII',b'GSA1',2,1,8)+b'\0'*(2*8*4))
        parser=Mock();version={'name':'demoparser2','version':'0.42.0'}
        receipt={'version':gameplay.VERSION,'source':'abc','parser':version,'fields':gameplay.FIELDS,'states':str(states),'events':[]}
        (self.root/'gameplay.json').write_text(json.dumps(receipt))
        meta={'frames':2,'players':[{'id':'76561198000000001'}],'sha256':'abc','parser':version}
        result=gameplay.prepare_gameplay(parser,meta,self.root,Mock())
        self.assertEqual(result,receipt);parser.parse_ticks.assert_not_called();parser.parse_events.assert_not_called()

    def test_recorded_sound_events_have_valid_players_and_chronology(self):
        files=list((backend.CACHE/'replays').glob('*/gameplay.json'))
        if not files:self.skipTest('No local prepared gameplay fixture')
        sample=json.loads(files[0].read_text(encoding='utf-8'))
        meta=json.loads((files[0].parent/'replay.json').read_text(encoding='utf-8'))
        events=sample['events']
        self.assertTrue(events)
        self.assertEqual([e['tick'] for e in events],sorted(e['tick'] for e in events))
        self.assertTrue(all(0<=e['player']<len(meta['players']) for e in events))
        self.assertTrue(all(len(e['position'])==3 for e in events))
        self.assertTrue(all(e['weapon'] for e in events if e['kind']=='weapon_reload'))


if __name__=='__main__':unittest.main()
