import unittest
from smoke_fill import fill

def at(data,x,y,z):return data[x+32*y+1024*z]

class SmokeFillTests(unittest.TestCase):
    def test_collision_cells_are_empty_and_inner_bits_are_linear(self):
        # bit 9 is (1,2,0), not its inner-block Morton coordinate.
        data=fill([(0,2,0)],{0:1<<9},steps=4)
        self.assertEqual(at(data,1,2,0),0)
        self.assertEqual(at(data,0,2,0),1)
        self.assertEqual(at(data,2,2,0),1)

    def test_flood_does_not_cross_blocked_plane(self):
        wall=sum(1<<(2+4*y+16*z) for y in range(4) for z in range(4))
        data=fill([(0,1,1)],{0:wall},steps=20)
        self.assertEqual(at(data,1,1,1),1)
        self.assertEqual(at(data,2,1,1),0)
        self.assertEqual(at(data,3,1,1),0)

    def test_unknown_blocks_and_array_edges_do_not_wrap(self):
        data=fill([(0,0,0)],{0:0},steps=20)
        self.assertEqual(sum(data),64)
        self.assertEqual(at(data,31,0,0),0)
        self.assertEqual(at(data,4,0,0),0)

    def test_blocked_seed_never_becomes_smoke(self):
        self.assertEqual(sum(fill([(0,0,0)],{0:1},steps=4)),0)

if __name__=='__main__':unittest.main()
