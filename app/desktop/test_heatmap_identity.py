"""Observed FACEIT identity shape and strict downstream account linkage."""
import unittest
from sources import Resolver


class FixtureResolver(Resolver):
    def faceit(self,path):
        if path.endswith('/stats'):
            return {'rounds':[{'round_stats':{'Map':'de_ancient','Score':'13 / 7'},'teams':[
                {'team_id':'alpha','team_stats':{'Final Score':'13'}},
                {'team_id':'beta','team_stats':{'Final Score':'7'}}]}]}
        return {'status':'FINISHED','finished_at':1793404800,'demo_url':[], 'teams':{
            'faction1':{'faction_id':'alpha','name':'Alpha','roster':[
                {'player_id':'linked-account','nickname':'OldName','game_player_id':'76561198062530225'}]},
            'faction2':{'faction_id':'beta','name':'Beta','roster':[
                {'player_id':'other-account','nickname':'Other','game_player_id':'76561198000000002'}]}}}


class HeatmapIdentityTests(unittest.TestCase):
    def test_uuid_link_resolves_steamid_independent_of_nickname(self):
        result=FixtureResolver().faceit_match('match','NewName',player_id='linked-account')
        self.assertEqual(result['heatmap_identity']['tracked_player_id'],'76561198062530225')
        self.assertEqual(result['heatmap_identity']['mode'],'player')

    def test_esea_team_mode_is_not_classified_as_pug_from_provider(self):
        result=FixtureResolver().faceit_match('match','Alpha',team_id='alpha')
        identity=result['heatmap_identity']
        self.assertEqual(identity['mode'],'team')
        self.assertEqual(identity['selected_team_id'],'alpha')
        self.assertEqual(identity['teams'][0]['players'],['76561198062530225'])


if __name__=='__main__':unittest.main()
