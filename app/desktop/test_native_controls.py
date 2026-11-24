import struct
import unittest
from unittest.mock import Mock,patch
import native_controls as controls


class ControlTests(unittest.TestCase):
    def test_only_structured_playback_commands_can_be_sent(self):
        self.assertEqual(controls.command('seek',0),'demo_gototick 0 P')
        self.assertEqual(controls.command('skip',-640),'demo_gototick -640 R P')
        self.assertEqual(controls.command('speed',.5),'demo_timescale 0.5')
        self.assertEqual(controls.command('pause'),'demo_pause')
        self.assertEqual(controls.command('camera','first_person'),'spec_mode 2')
        self.assertEqual(controls.command('camera','chase'),'spec_mode 3')
        self.assertEqual(controls.command('camera','free'),'spec_mode 4')
        self.assertEqual(controls.command('player_name','SmoodAimder'),'spec_player "SmoodAimder"')
        for action,value in [('connect','server'),('seek','1; quit'),('seek',True),('speed',float('nan')),
                             ('camera','chase; quit'),('skip',5000000000),('pause','quit'),
                             ('player_name','SmoodAimder; quit'),('player_name','"Smood"'),('lock_account',-1)]:
            with self.subTest(action=action,value=value),self.assertRaises(ValueError):controls.command(action,value)

    def test_framing_uses_the_current_cmnd_discriminator_and_total_length(self):
        data=controls.packet('demo_pause')
        self.assertEqual(struct.unpack('>4sHIH',data[:12]),(b'CMND',0xd4,len(data),0))
        self.assertEqual(data[12:],b'demo_pause\0')

    def test_fragmented_and_batched_output_is_decoded_without_losing_boundaries(self):
        body=b'\0'*28+b'tick response\0'
        data=controls.HEADER.pack(b'PRNT',0xd4,12+len(body),0)+body
        d=controls.Decoder()
        self.assertEqual(d.feed(data[:5]),[])
        self.assertEqual(d.feed(data[5:]+data),['tick response','tick response'])
        self.assertEqual(d.buffer,b'')
        with self.assertRaises(ValueError):d.feed(controls.HEADER.pack(b'PRNT',0,2,0))

    def test_large_schema_packet_does_not_desynchronize_later_print_output(self):
        schema=b'\0\0\0\x0e'*20000
        body=b'\0'*28+b'acknowledged\0'
        data=controls.HEADER.pack(b'CHAN',0xd4,len(schema)+12,0)+schema
        data+=controls.HEADER.pack(b'PRNT',0xd4,len(body)+12,0)+body
        self.assertEqual(controls.Decoder().feed(data),['acknowledged'])

    def test_no_commands_without_guard_and_owned_listener(self):
        session=Mock();session.process.poll.return_value=None;session.process.pid=17
        guard=Mock();guard.healthy.return_value=False;guard.port=59287
        conn=controls.Connection(session,guard)
        with patch.object(controls.socket,'create_connection') as connect:
            with self.assertRaises(ValueError):conn.connect()
            connect.assert_not_called()
        guard.healthy.return_value=True
        with patch.object(controls,'listeners',return_value=[{'pid':18,'address':'0.0.0.0'}]), \
             patch.object(controls.socket,'create_connection') as connect:
            with self.assertRaises(ValueError):conn.connect()
            connect.assert_not_called()
        with self.assertRaises(ValueError):conn.send('pause')

    def test_guard_cannot_be_removed_while_the_engine_is_alive(self):
        guard=controls.LocalGuard('fixture');guard.process=Mock();guard.process.poll.return_value=None
        with self.assertRaisesRegex(ValueError,'Stop the owned engine'):guard.close()

    def test_engine_timeline_has_an_explicit_server_tick_origin(self):
        info=controls.playback_info('server_start_tick: 36562\nplayback_ticks: 102934\nplayback_time: 1608.34375')
        self.assertEqual(info['start_tick'],36562);self.assertEqual(info['end'],102934)
        self.assertAlmostEqual(info['rate'],64,places=4)
        with self.assertRaises(ValueError):controls.playback_info('playback_ticks: 4\nplayback_time: 0')


if __name__=='__main__':unittest.main()
