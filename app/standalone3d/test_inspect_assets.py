import unittest
from inspect_assets import choose

class InspectClipTests(unittest.TestCase):
    def test_stock_knife_does_not_pick_a_cosmetic_or_menu_clip(self):
        stock='animation/anims/viewmodel/knife/_default_knife/lookat01_knife.vnmclip_c'
        catalog=['animation/anims/ui_anims/lookat01_knife.vnmclip_c',
                 'animation/anims/viewmodel/knife/knife_bayonet/lookat01_bayonet.vnmclip_c',stock]
        self.assertEqual(choose(catalog,'knife','knife'),stock)

    def test_no_generic_pistol_inspect_is_substituted_for_a_missing_weapon(self):
        self.assertIsNone(choose(['animation/anims/viewmodel/pistol/_default_pistol/lookat01_pistol.vnmclip_c'],'glock','pistol'))

if __name__=='__main__':unittest.main()
