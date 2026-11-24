import unittest
from stock_assets import WEAPONS,canonical

class WeaponAliasesTests(unittest.TestCase):
    def test_every_stock_label_and_event_id_resolve_to_the_same_asset(self):
        for key,definition in WEAPONS.items():
            with self.subTest(weapon=key):
                self.assertEqual(canonical(definition[0]),key)
                self.assertEqual(canonical('weapon_'+key),key)
                self.assertEqual(canonical(definition[0].replace('-',' ')),key)

    def test_grenades_and_knife_variants_keep_canonical_gameplay_identity(self):
        self.assertEqual(canonical('High Explosive Grenade'),'hegrenade')
        self.assertEqual(canonical('Smoke Grenade'),'smokegrenade')
        self.assertEqual(canonical('weapon_knife_karambit'),'knife')
        self.assertEqual(canonical('CZ75 Auto'),'cz75a')
        self.assertEqual(canonical('Five Seven'),'fiveseven')

if __name__=='__main__':unittest.main()
