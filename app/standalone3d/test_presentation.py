import struct
import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend import CACHE
from presentation import prepare_travel,prepare_gait_phase,scalar

class PresentationTests(unittest.TestCase):
    def test_direction_changes_do_not_restart_or_jump_the_gait_cycle(self):
        root=CACHE/'test-fixtures';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            folder=Path(directory);states=np.zeros((64,1,8),dtype='<f4');tracks=np.zeros((64,1,11),dtype='<f4')
            states[:32,0,0]=64;states[32:,0,1]=64;tracks[:,:,7]=1;tracks[:,:,9]=1;states[48,0,3]=1
            state=folder/'state.bin';track=folder/'track.bin'
            state.write_bytes(bytes(16)+states.tobytes());track.write_bytes(bytes(24)+tracks.tobytes())
            meta={'sha256':'demo','frames':64,'players':[{'id':'7'}],'gameplay':{'states':str(state)},'tracks':str(track),'step':1,'info':{'tickrate':64},'weapons':['glock'],
                  'stock':{'weapons':{'glock':{'class':'pistol'}},'gait_strides':{'bank_walk_n_pistol':64,'bank_walk_w_pistol':128}}}
            path=Path(prepare_gait_phase(meta,folder));phase=np.frombuffer(path.read_bytes(),dtype='<f4',offset=16)
            self.assertAlmostEqual(float(phase[31]),.5)
            self.assertAlmostEqual(float(phase[32]-phase[31]),1/128)
            self.assertEqual(float(phase[48]-phase[47]),0)
            self.assertTrue(np.all(np.diff(phase)>=0));self.assertLessEqual(float(np.max(np.diff(phase))),1/64)
            # A backward seek reads the same phase; playback history is absent.
            self.assertEqual(path.read_bytes(),Path(prepare_gait_phase(meta,folder)).read_bytes())

    def test_ground_distance_excludes_absence_death_and_air(self):
        root=CACHE/'test-fixtures';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            folder=Path(directory);states=np.zeros((5,1,8),dtype='<f4');tracks=np.zeros((5,1,11),dtype='<f4')
            states[:,:,0]=64;tracks[:,:,7]=1;tracks[:,:,9]=1
            tracks[1,0,9]=0;tracks[2,0,7]=0;states[3,0,3]=1
            state=folder/'state.bin';track=folder/'track.bin'
            state.write_bytes(bytes(16)+states.tobytes());track.write_bytes(bytes(24)+tracks.tobytes())
            meta={'frames':5,'players':[{'id':'7'}],'gameplay':{'states':str(state)},'tracks':str(track),'step':1,'info':{'tickrate':64}}
            path=Path(prepare_travel(meta,folder))
            self.assertEqual(struct.unpack('<4sIII',path.read_bytes()[:16]),(b'GDT1',5,1,1))
            self.assertEqual(np.frombuffer(path.read_bytes(),dtype='<f4',offset=16).tolist(),[1,1,1,1,2])

    def test_nonfinite_presentation_fields_stay_unknown(self):
        for value in [None,float('nan'),float('inf'),'invalid']:
            self.assertIsNone(scalar(value))
        self.assertEqual(scalar(0),0)

if __name__=='__main__':unittest.main()
