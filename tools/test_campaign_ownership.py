"""Campaign claims and objectives must survive unrelated defense and supply decisions."""
from itertools import product
from pathlib import Path
import unittest

import boot
from inject import FB


class CampaignOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = boot.load(Path(__file__).resolve().parents[1] / 'backup/hlboot.dat')
        boot._ai_log(code)
        cls.code = code
        matches = [(f, FB.BUILT[f.findex.value][1]) for f in code.functions
                   if f.findex.value in FB.BUILT and 'dr_in' in FB.BUILT[f.findex.value][1]]
        cls.function, cls.labels = matches[0]
        assert len(matches) == 1, 'expected one campaign emitter'

    def step_in_eligible(self, turret, field, drop, already_inside):
        """Execute objective selection and the real emitted drop gate with symbolic entities."""
        ops, labels = self.function.ops, self.labels
        selection = labels['dob_f'] - 3
        initial = {k: v.value for k, v in ops[selection].df.items()}
        village_reg = ops[labels['dob_f'] - 2].df['reg'].value
        field_reg = ops[labels['dob_f']].df['reg'].value
        drop_zone_reg = ops[labels['dr_in']].df['reg'].value
        base, village, enemy, zone, elsewhere = object(), object(), object(), object(), object()
        regs = {initial['src']: base, village_reg: village if turret else None,
                field_reg: enemy if field else None, drop_zone_reg: zone if drop else None}

        def advance(pc):
            op = ops[pc]
            d = {k: v.value for k, v in op.df.items()}
            jump = False
            if op.op == 'Mov':
                regs[d['dst']] = regs[d['src']]
            elif op.op in ('JNull', 'JNotNull'):
                jump = (regs[d['reg']] is None) == (op.op == 'JNull')
            elif op.op in ('JEq', 'JNotEq'):
                jump = (regs[d['a']] is regs[d['b']]) == (op.op == 'JEq')
            elif op.op == 'Call1':
                regs[d['dst']] = zone if already_inside else elsewhere
            else:
                self.fail(f'unexpected objective/gate opcode: {op.op}')
            return pc + 1 + d['offset'] if jump else pc + 1

        pc = selection
        while pc < labels['dob_d']:
            pc = advance(pc)
        pc = labels['dr_in']
        for _ in range(10):
            if pc == labels['dr_in2']:
                return False
            # Map/throttle setup starts only after all drop-eligibility guards pass.
            if ops[pc].op == 'GetGlobal':
                return True
            pc = advance(pc)
        self.fail('drop gate did not terminate')

    def test_drop_step_in_only_for_base_objective(self):
        for turret, field, drop, inside in product((False, True), repeat=4):
            with self.subTest(turret=turret, field=field, drop=drop, inside=inside):
                self.assertEqual(self.step_in_eligible(turret, field, drop, inside),
                                 drop and not inside and not turret and not field)

    def test_minor_defense_checks_live_claim_before_requiring_an_order(self):
        held = [fid for fid, (src, _, _) in FB.BUILT.items() if src == 'tasks.build_held']
        self.assertEqual(len(held), 1)
        candidates = [(f, FB.BUILT[f.findex.value][1]) for f in self.code.functions
                      if f.findex.value in FB.BUILT and FB.BUILT[f.findex.value][0] == 'picks.pick_life'
                      and 'dk_go' in FB.BUILT[f.findex.value][1]]
        self.assertEqual(len(candidates), 1, [(f.findex.value, FB.BUILT[f.findex.value][0]) for f, _ in candidates])
        f, labels = candidates[0]
        calls = [(pc, op) for pc, op in enumerate(f.ops) if labels['dk'] <= pc < labels['dk_end']
                 and op.op == 'Call2' and op.df.get('fun').value == held[0]]
        self.assertEqual(len(calls), 1, 'minor-defense filter must check claims even for orderless armies')
        call_pc, call = calls[0]
        for is_held in (False, True):
            with self.subTest(held=is_held):
                regs = {call.df['dst'].value: is_held}
                pc = call_pc + 1
                # A live higher claim must reach removal before any order lookup.
                # With no claim, keep the existing Military-order check.
                for _ in range(12):
                    op = f.ops[pc]
                    d = {k: v.value for k, v in op.df.items()}
                    if op.op in ('JTrue', 'JFalse'):
                        jump = bool(regs[d['cond']]) == (op.op == 'JTrue')
                        pc += 1 + d['offset'] if jump else 1
                    elif op.op == 'JAlways':
                        pc += 1 + d['offset']
                    elif op.op in ('Int', 'ToDyn', 'Mov'):
                        pc += 1
                    elif op.op == 'Call3':
                        target = next(fn for fn in self.code.functions if fn.findex.value == d['fun'])
                        self.assertIn('splice', boot._name(self.code, target))
                        self.assertTrue(is_held)
                        break
                    else:
                        self.assertFalse(is_held, 'held army reached an order lookup instead of removal')
                        break
                else:
                    self.fail('claim branch did not reach its ownership decision')


if __name__ == '__main__':
    unittest.main()
