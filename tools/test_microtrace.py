"""All logging-gate paths must still call vanilla changeArmyMicro exactly once."""
from pathlib import Path
import unittest

import boot
import inject


class MicroWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cx = inject.Ctx(boot.load(Path(__file__).resolve().parents[1] / 'backup/hlboot.dat'))
        cls.helpers = {'log': inject.build_log(cls.cx), 'ent': inject.build_ent(cls.cx)}

    def test_changes_and_verbose_modes_cannot_skip_or_repeat_vanilla(self):
        for repeats in (False, True):
            with self.subTest(repeats=repeats):
                cx = self.cx
                target = cx.fn('logic.ai.AIUnits.changeArmyMicro')
                fid = inject.wrapper(cx, target, 'micro', inject._micro_before, None,
                                     self.helpers, micro_repeats=repeats)
                f = next(f for f in cx.code.functions if f.findex.value == fid)
                original = target.findex.value
                pending, seen, exits = [(0, 0)], set(), []
                while pending:
                    i, calls = pending.pop()
                    if (i, calls) in seen:
                        continue
                    seen.add((i, calls))
                    op = f.ops[i]
                    d = {k: v.value for k, v in op.df.items()}
                    if op.op.startswith('Call') and d.get('fun') == original:
                        calls += 1
                    self.assertLessEqual(calls, 1)
                    if op.op == 'Ret':
                        exits.append(calls)
                        continue
                    if op.op == 'JAlways':
                        pending.append((i + 1 + d['offset'], calls))
                    else:
                        pending.append((i + 1, calls))
                        if op.op.startswith('J') or op.op == 'Trap':
                            pending.append((i + 1 + d['offset'], calls))
                self.assertTrue(exits)
                self.assertEqual(set(exits), {1})


if __name__ == '__main__':
    unittest.main()
