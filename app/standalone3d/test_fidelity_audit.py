import unittest
from unittest.mock import patch
from pathlib import Path
import fidelity_audit as audit


class FidelityAuditTests(unittest.TestCase):
    def test_new_shader_family_never_silently_counts_as_supported_pbr(self):
        result=audit.inspect_material({'name':'future','extras':{'vmat':{'ShaderName':'future_material.vfx'}}})
        self.assertIn('unmapped_source_shader',result['losses'])

    def test_water_is_not_mistaken_for_working_opaque_pbr(self):
        result=audit.inspect_material({'name':'canal','extras':{'vmat':{'ShaderName':'csgo_water_fancy.vfx'}}})
        self.assertIn('water_shader',result['losses'])
        self.assertEqual(result['status'],'requires_adapter_or_review')

    def test_layer_and_decal_requirements_survive_standard_export(self):
        result=audit.inspect_material({'name':'wall','extras':{'vmat':{'ShaderName':'csgo_static_overlay.vfx','IntParams':{'F_LAYERS':1}}}})
        self.assertEqual(set(result['losses']),{'decal_blending','layered_material'})

    def test_existing_dust_adapter_is_partial_not_full_shader_parity(self):
        result=audit.inspect_material({'name':'anubis_dust_001','extras':{'vmat':{'ShaderName':'csgo_effects.vfx'}}})
        self.assertIn('partial_atmospheric_adapter',result['losses'])

    def test_parseable_scene_does_not_satisfy_missing_gameplay_features(self):
        with patch.object(audit,'gltf_info',return_value={'materials':[]}):result=audit.audit_map(Path('fixture.glb'))
        self.assertFalse(result['fidelity_ready'])
        self.assertFalse(result['functional_pass_is_fidelity_pass'])
        self.assertEqual(result['review_features']['death_bodies']['status'],'implemented_approximate_death_animation')
        self.assertEqual(result['review_features']['first_person_hands']['status'],'implemented_native_checked')
        self.assertEqual(result['review_features']['baked_lighting']['status'],'missing')


if __name__=='__main__':unittest.main()
