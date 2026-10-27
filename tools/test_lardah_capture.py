"""Lardah: a fighting capture keeps its claims; worm recovery never resumes stale rally paths."""
import unittest
from campaign_probe import Obj, Probe


class LardahCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Probe()

    def setUp(self):
        self.p.maps = {i: {} for i in self.p.map_ids.values()}
        self.p.handlers = {}

    def test_fighting_capture_army_refreshes_ownership(self):
        a, target = Obj(posx=100, posy=0, isFighting=True, free=False), Obj(posx=100, posy=0)
        owned = {a: 99}
        p = self.p.setup('_emit_muster', my=[a], mlen=1, ffv=target, bcmc=owned, t=100,
                         orders=[], att=False, fac=Obj(), zero=0)
        p.maps[p.map_ids['tkp']][a] = 65
        p.maps[p.map_ids['tkt']][a] = 99
        p.run(p.fb.labels['mu'] - 1, {'mud'})
        self.assertEqual(owned[a], 100, 'combat must not make an eight-second claim expire')

    def test_worm_recovery_uses_rally_paths_only_during_regroup(self):
        p = self.p
        for phase in (3, 4, 5):
            with self.subTest(phase=phase):
                p.setup('build_worm_release', o=Obj(phase=phase))
                fb, oreg = p.fb, p.frame['o']
                start = next(i for i, op in enumerate(fb.ops) if op.op == 'Field'
                             and op.df['obj'].value == oreg
                             and p.field_name(oreg, op.df['field'].value) == 'phase')
                target_call = next(i for i in range(start, len(fb.ops)) if fb.ops[i].op.startswith('Call')
                                   and p.names.get(fb.ops[i].df.get('fun').value, '').endswith('AIOrder.getTarget'))
                reached = p.run(start, {'a', target_call})
                self.assertEqual(reached, target_call if phase == 3 else 'a')


if __name__ == '__main__':
    unittest.main()
