"""Code-proven campaign failures. Run with the project's Python and unittest."""
import unittest
from campaign_probe import Obj, Probe


class CampaignReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Probe()

    def setUp(self):
        self.p.maps = {i: {} for i in self.p.map_ids.values()}
        self.p.handlers = {}

    def test_short_staging_gathers_at_home_instead_of_village(self):
        p = self.p.setup('_emit_muster', ffv=Obj(posx=500, posy=0), stg=Obj(posx=350, posy=0), zero=0, t=100)
        p.run('fs_go', {'ffg_k', 'ffg_d'})
        self.assertEqual((p.regs[p.frame['gpx']], p.regs[p.frame['gpy']]), (350, 0))

    def test_distant_staging_keeps_the_existing_approach_distance(self):
        p = self.p.setup('_emit_muster', ffv=Obj(posx=500, posy=0), stg=Obj(posx=0, posy=0), zero=0, t=100)
        p.run('fs_go', {'ffg_k', 'ffg_d'})
        self.assertEqual((p.regs[p.frame['gpx']], p.regs[p.frame['gpy']]), (320, 0))

    def test_busy_army_does_not_launch_the_foothold_pack(self):
        p = self.p.setup('_emit_muster', my=[Obj(posx=500, posy=0, power=300000, free=False)], mlen=1,
                         ffv=Obj(posx=500, posy=0), gpx=320, gpy=0, zero=0, ffneed=225000,
                         ffgo=True, orders=[], t=100, bcmc={}, ffgm={}, fac=Obj(kind='Fremen'))
        p.run('ffg_k', {'ffg_d'}, before_op='New')
        self.assertFalse(p.regs[p.frame['ffgo']])

    def test_continuous_column_wait_is_capped_once_per_go(self):
        a, fac = Obj(), Obj()
        a['zone'] = Obj(owner=fac)
        p = self.p.setup('_emit_raze', drear=700, dq=400, dx_=a, fac=fac, t=230, gt=50)
        p.maps[p.map_ids['bccw']][a] = 100
        self.assertEqual(p.run('dr_cc', {'dr_mv', 'dr_actn'}), 'dr_mv')

    def test_recent_column_wait_still_holds(self):
        a, fac = Obj(), Obj()
        a['zone'] = Obj(owner=fac)
        p = self.p.setup('_emit_raze', drear=700, dq=400, dx_=a, fac=fac, t=130, gt=50)
        p.maps[p.map_ids['bccw']][a] = 100
        self.assertEqual(p.run('dr_cc', {'dr_mv', 'dr_actn'}), 'dr_actn')

    def test_phase_hold_restarts_when_desired_transition_changes(self):
        fac, base = Obj(), Obj()
        p = self.p.setup('_emit_phase', fac=fac, be=base, bccs={base: 100}, ph=1, nph=0, t=125)
        p.maps[p.map_ids['bccp']][fac] = {base: 1}
        # The old timer belongs to muster -> go, not the newly requested muster -> attrition.
        if 'bccn' in p.map_ids:
            p.maps[p.map_ids['bccn']][fac] = {base: 2}
        self.assertEqual(p.run('p_cond', {'p_start', 'p_set', 'act'}), 'p_start')

    def test_unchanged_phase_condition_can_complete_its_hold(self):
        fac, base = Obj(), Obj()
        p = self.p.setup('_emit_phase', fac=fac, be=base, bccs={base: 100}, ph=1, nph=0, t=125)
        p.maps[p.map_ids['bccp']][fac] = {base: 1}
        if 'bccn' in p.map_ids:
            p.maps[p.map_ids['bccn']][fac] = {base: 0}
        self.assertEqual(p.run('p_cond', {'p_start', 'p_set', 'act'}), 'p_set')

    def test_denied_raze_claim_stops_before_command_or_ownership_marks(self):
        p = self.p.setup('_emit_raze', dx_=Obj(claim_ok=False), t=100, bcmc={})
        fb = p.fb
        claim = p.frame['helpers']['claim']
        pc = next(i for i in range(fb.labels['drb_d'], fb.labels['dr_nf'])
                  if fb.ops[i].op == 'Call2' and fb.ops[i].df['fun'].value == claim)
        result_reg = fb.ops[pc].df['dst'].value
        p.regs[result_reg] = False
        # A refusal must branch back to the army loop before the strike/worm query.
        self.assertEqual(fb.ops[pc + 1].op, 'JFalse')
        self.assertEqual(pc + 2 + fb.ops[pc + 1].df['offset'].value, fb.labels['dr'])

    def test_defense_readings_are_bound_to_the_base(self):
        fac, partner, base, previous_base = Obj(), Obj(), Obj(), Obj()
        p = self.p.setup('_emit_numbers', fac=fac, dfx=partner, be=base, bcd={partner: 999000},
                         bcdt={partner: 99}, t=100, dn=0, dsum=0, dmax=0, dmin=1 << 30)
        if 'bcdb' in p.map_ids:
            p.maps[p.map_ids['bcdb']][partner] = previous_base
        p.run('dd_m', {'dd'})
        self.assertEqual(p.regs[p.frame['dn']], 0, 'a fresh reading of another base entered the mean')

    def test_current_base_defense_readings_still_count(self):
        fac, partner, base = Obj(), Obj(), Obj()
        p = self.p.setup('_emit_numbers', fac=fac, dfx=partner, be=base, bcd={partner: 999000},
                         bcdt={partner: 99}, t=100, dn=0, dsum=0, dmax=0, dmin=1 << 30)
        if 'bcdb' in p.map_ids:
            p.maps[p.map_ids['bcdb']][partner] = base
        p.run('dd_m', {'dd'})
        self.assertEqual(p.regs[p.frame['dn']], 1)
        self.assertEqual(p.regs[p.frame['dsum']], 999000)

    def test_campaign_checks_war_before_posting_or_taking_armies(self):
        p = self.p
        frame = p.frames['build_bk_campaign']
        fb = frame['fb']
        calls = [(i, op) for i, op in enumerate(fb.ops[:fb.labels['sg']])
                 if op.op.startswith('Call') and p.names.get(op.df.get('fun').value, '').endswith('areAtWar')]
        self.assertEqual(len(calls), 1, 'assault level does not guarantee declareWar succeeded')

    def test_campaign_reads_enemy_power_without_partner_discount(self):
        fac, target = Obj(), Obj(zone=None)
        p = self.p.setup('build_forecast', theirs=1000000, ours=700000, jh=350000, zero=0)
        p.regs.update({0: fac, 1: target})
        p.run('nojoint', {'end'})
        self.assertEqual(p.maps[p.map_ids['fct']][fac], 650000,
                         'ordinary forecast callers retain their existing partner credit')
        stored = p.maps[p.map_ids.get('fct_raw', p.map_ids['fct'])][fac]
        self.assertEqual(stored, 1000000, 'campaign must count coalition support only in its own M')
        frame = p.frames['_emit_numbers']
        fb = frame['fb']
        selected = [op.df['global'].value for op in fb.ops[:fb.labels['dd']]
                    if op.op == 'GetGlobal']
        self.assertIn(p.map_ids['fct_raw'], selected)

    def test_active_foothold_keeps_its_target_during_candidate_scan(self):
        active, nearer = Obj(), Obj()
        p = self.p.setup('_emit_muster', ffc=active, oce=active, ocap=True, ffq=200, ffbd=10,
                         ffv=nearer, ffst=False)
        p.run('ffl_pick', {'ffl', 'ffl_d'})
        self.assertIs(p.regs[p.frame['ffv']], active)

    def test_inactive_foothold_keeps_the_nearer_candidate(self):
        candidate, nearer = Obj(), Obj()
        p = self.p.setup('_emit_muster', ffc=candidate, oce=candidate, ocap=False, ffq=200, ffbd=10,
                         ffv=nearer, ffst=False)
        p.run('ffl_pick', {'ffl', 'ffl_d'})
        self.assertIs(p.regs[p.frame['ffv']], nearer)

    def test_prelaunch_route_uses_the_gathering_point(self):
        p = self.p
        f = p.frames['_emit_muster']
        fb = f['fb']
        # The route's target coordinates must be the gathering point, before any ArmySiege launch.
        start, end = fb.labels['mu_att'], fb.labels['mu_ffgd']
        writes = [(op.df['dst'].value, op.df['src'].value) for op in fb.ops[start:end] if op.op == 'Mov']
        self.assertTrue(any(src == f['gpx'] for _, src in writes), 'route currently heads for the village zone')


if __name__ == '__main__':
    unittest.main()
