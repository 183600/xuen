"""Witness for the latent v1.5 PACK-front unsoundness.

The PACK front is keyed by (R, h) and stores only the A vector, but the
relaxation pack_exact reads est as well.  Two states with the same (R, A)
and different est are therefore conflated.  Below, state E1 (est_6=18) is
genuinely infeasible; state E2 (est_6=14) is feasible.  A front entry made
by E1 wrongly prunes E2.  Setting SOUND_FRONT=False reproduces the old
v1.5 behaviour end-to-end on a 7-task instance.
"""
import sys
sys.path.insert(0, 'exp/v13'); sys.path.insert(0, 'exp/v14')
sys.path.insert(0, 'exp/v15'); sys.path.insert(0, 'exp/v16'); sys.path.insert(0, 'exp/v17')
import po, pace_omd

inst = po.make_inst([7, 8, 8, 6, 4, 7, 7], 2,
                    [[], [], [], [1, 2], [1], [0], [2]], None)
h = 24
rem = sum(1 << i for i in (3, 4, 6))
A = (16, 14)
q = po.tails(inst, rem)
E1 = (0, 0, 0, 16, 16, 0, 18)   # task 6 cannot start after 17
E2 = (0, 0, 0, 16, 14, 0, 14)   # feasible: 4@14, 6@16, 3@18
print('pack_exact(E1) =', po.pack_exact(inst, rem, A, E1, q, h))
print('pack_exact(E2) =', po.pack_exact(inst, rem, A, E2, q, h))

cfg = dict(mode='pot', nodecap=2_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=False, omd=True)
for sound in (False, True):
    pace_omd.SOUND_FRONT = sound
    (ok, _), st = pace_omd.decide(inst, h, **cfg)
    print('SOUND_FRONT=%-5s -> feasible=%s nodes=%d' % (sound, ok, st['nodes']))
pace_omd.SOUND_FRONT = True
