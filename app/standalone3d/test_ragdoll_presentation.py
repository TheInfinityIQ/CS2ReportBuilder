import copy
import unittest
from ragdoll_presentation import join_deaths

class DeathPresentationTests(unittest.TestCase):
    def setUp(self):
        self.meta={'sha256':'original','players':[{'id':'stable-A'},{'id':'stable-B'}],
                   'gameplay':{'events':[{'kind':'player_death','player':0,'tick':100},{'kind':'player_death','player':0,'tick':300},{'kind':'player_death','player':1,'tick':100}]}}
        self.state={'kind':'player','player':'stable-A','enabled':True,'serverOrigin':[1,2,3],
                    'eyeAngles':[4,5,6],'force':[7,8,9],'damagePosition':[0,0,0],'bone':7,
                    'headshot':True,'weapon':'glock','clientSide':True,'transforms':[]}
    def recording(self,ticks):return {'source':'original','rows':[{'tick':tick,'handle':str(i),'state':copy.deepcopy(self.state)} for i,tick in enumerate(ticks)]}
    def test_stable_identity_death_tick_and_respawn_are_separate(self):
        data=self.recording([101,102,299,300,305]);data['rows'][1]['state']['serverOrigin']=[99,99,99]
        result=join_deaths(self.meta,data)
        self.assertEqual(set(result),{'0:100','0:300'})
        self.assertEqual(result['0:100']['serverOrigin'],[1,2,3])
        self.assertTrue(result['0:100']['headshot']);self.assertEqual(result['0:100']['transform_count'],0)
    def test_wrong_demo_is_rejected(self):
        with self.assertRaises(ValueError):join_deaths(self.meta,{'source':'different','rows':[]})
    def test_default_or_nonfinite_or_disabled_state_is_ignored(self):
        for changes in [{'serverOrigin':[0,0,0]},{'serverOrigin':[float('nan'),2,3]},{'enabled':False},{'player':'unknown'}]:
            data=self.recording([100]);data['rows'][0]['state'].update(changes)
            self.assertEqual(join_deaths(self.meta,data),{})
    def test_other_players_and_late_updates_do_not_steal_death(self):
        data=self.recording([105,100]);data['rows'][1]['state']['player']='stable-B'
        self.assertEqual(set(join_deaths(self.meta,data)),{'1:100'})

if __name__=='__main__':unittest.main()
