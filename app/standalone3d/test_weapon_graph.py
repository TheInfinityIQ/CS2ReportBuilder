import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from graph_document import loads
from weapon_graph import Compiler, UnsupportedGraph, prepare_weapon_graph, valid_clip
from backend import CACHE, save


def pin(identifier, name, kind='Pose'):
    return {'m_ID': identifier, 'm_name': name, 'm_type': kind}


def node(identifier, kind, inputs=(), outputs=(), **extra):
    return {'m_ID': identifier, '_class': 'CNmGraphDoc'+kind, 'm_inputPins': list(inputs),
            'm_outputPins': list(outputs), **extra}


class GraphDocumentTests(unittest.TestCase):
    def test_missing_or_truncated_binary_cannot_reuse_a_valid_looking_graph_receipt(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder=Path(temporary);clip=folder/'clip.json';binary=folder/'pose.bin'
            save(clip,{'variants':[{'frames':2,'bones':['root'],'fps':30,'data':str(binary)}]})
            self.assertFalse(valid_clip(clip))
            binary.write_bytes(bytes(63));self.assertFalse(valid_clip(clip))
            binary.write_bytes(bytes(64));self.assertTrue(valid_clip(clip))

    def test_a_changed_graph_that_fails_preparation_cannot_keep_an_old_runtime_program(self):
        base=CACHE/'test-fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            folder=Path(temporary)
            actors={'models':{'ct':str(folder/'poses/id/model.json')},'identity':{'revision':'a'},
                    'weapon_graphs':{'glock':{'old':'must not survive'}}}
            with patch('weapon_graph._run',side_effect=ValueError('unsupported new version')):
                result=prepare_weapon_graph(folder,actors,['Glock-18'])
            self.assertNotIn('weapon_graphs',result)
            self.assertTrue(result['weapon_graph_gaps'])

    def test_real_string_values_are_not_stripped_as_comments(self):
        self.assertEqual(loads('<!-- kv3 --> { path = "a//b/*c*/" values=[true, false, -2.5e-2, null,] }'),
                         {'path': 'a//b/*c*/', 'values': [True, False, -.025, None]})

    def test_partial_or_unknown_documents_are_rejected(self):
        for text in ['{ a = 1 a = 2 }', '{ a = [1,2 }', '{ a = "unterminated }', '{ a=nan }', '{} {}', '{ a=resource:"a" }']:
            with self.subTest(text=text), self.assertRaises(ValueError): loads(text)

    def test_connection_not_node_order_controls_selected_clip(self):
        clip = node('clip', 'ClipNode', outputs=[pin('out', 'Pose')],
                    m_pDefaultVariationData={'m_clip': 'original.vnmclip', 'm_flSpeedMultiplier': .75}, m_bAllowLooping=False)
        result = node('result', 'PoseResultNode', inputs=[pin('in', 'Pose')])
        graph = {'m_nodes': [result, clip], 'm_connections': [
            {'m_fromNodeID': 'clip', 'm_outputPinID': 'out', 'm_toNodeID': 'result', 'm_inputPinID': 'in'}]}
        program = Compiler({}).root(graph)
        self.assertEqual((program['resource'], program['speed']), ('original.vnmclip', .75))
        for mutation in ['missing', 'duplicate', 'unknown-node', 'unknown-pin', 'override']:
            changed = copy.deepcopy(graph)
            if mutation == 'missing': changed['m_connections'] = []
            elif mutation == 'duplicate': changed['m_connections'] *= 2
            elif mutation == 'unknown-node': changed['m_nodes'][1]['_class'] = 'CNmGraphDocFutureNode'
            elif mutation == 'unknown-pin': changed['m_connections'][0]['m_outputPinID'] = 'not-a-pin'
            elif mutation == 'override': changed['m_nodes'][1]['m_overrides'] = [{'unexpected': 1}]
            with self.subTest(mutation=mutation), self.assertRaises(UnsupportedGraph): Compiler({}).root(changed)


if __name__ == '__main__': unittest.main()
