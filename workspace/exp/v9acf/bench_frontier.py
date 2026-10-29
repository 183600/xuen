"""Live multi-leaf frontier snapshots as DACS certificates.

For every gap instance and both ends h=L and h=U-1, run the AID frontier
with increasing LP budgets.  Each snapshot is converted into a
PartialCertificate and audited.  This is the round-3 live-frontier
experiment: it is not a replay of an old tree, but a tree that grows
under an LP budget and is audited at every snapshot.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9acf', 'exp/v9ai', 'exp/v9a', 'exp/v8j', 'exp/v8u',
                'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from aidf import search, LiftedFrontierProof, PartialFrontierCertificate
from dacs import initial_cert, Cert
from icf import PartialCertificate

BUDGETS = (0, 1, 2, 4, 8, 16, 32)


def snapshot_cert(inst, h, snap, base):
    if snap.verdict is False:
        proof = snap.proof()
        L = h + 1
    else:
        L = snap.local_L()
        proof = LiftedFrontierProof(inst, L - 1, h, snap.tree) \
            if L > 0 else None
    c = Cert(inst, L, base.U, base.schedule, base.machine, proof,
             source='frontier', h=h,
             lp=snap.stats.get('lp_solves', 0),
             cert_lp=snap.stats.get('cert_lp', 0),
             t=snap.stats.get('t', 0.0), workers=('F',))
    return c


def main():
    rows = []
    for d in json.load(open('exp/v10b/gap_stress.json')):
        inst = d['inst']
        base = initial_cert(inst)
        assert base is not None
        ends = sorted(set([base.L, base.U - 1]))
        for h in ends:
            seq = []
            for B in BUDGETS:
                t0 = time.time()
                s = search(inst, h, budget=B)
                c = snapshot_cert(inst, h, s, base)
                pc_ok = bool(c.audit()) if c.proof is not None else False
                pfc = PartialFrontierCertificate(
                    inst, h, s.local_L(), base.U, base.schedule,
                    base.machine, s.tree)
                pfc_ok = bool(pfc.audit_rdf())
                lift_ok = False
                if s.local_L() > 0:
                    lift_ok = bool(LiftedFrontierProof(
                        inst, s.local_L() - 1, h, s.tree).audit_rdf())
                seq.append(dict(B=B, verdict=s.verdict,
                                L=s.local_L(),
                                leaves=s.stats.get('leaves', 0),
                                open=s.stats.get('open_leaves', 0),
                                splits=s.stats.get('splits', 0),
                                lp=s.stats.get('lp_solves', 0),
                                cert_lp=s.stats.get('cert_lp', 0),
                                cert_ok=pc_ok, frontier_ok=pfc_ok,
                                lift_ok=lift_ok,
                                t=round(time.time() - t0, 4)))
            rows.append(dict(idx=d['idx'], opt=d['opt'], h=h,
                             L0=base.L, U0=base.U, seq=seq))
        print('done', d['idx'], flush=True)
    out = dict(instances=len(rows),
               budgets=list(BUDGETS),
               cert_pass=sum(1 for r in rows for x in r['seq']
                             if x['cert_ok']),
               cert_total=sum(len(r['seq']) for r in rows),
               frontier_pass=sum(1 for r in rows for x in r['seq']
                                 if x['frontier_ok']),
               frontier_total=sum(len(r['seq']) for r in rows),
               lift_pass=sum(1 for r in rows for x in r['seq']
                             if x['B'] > 0 and x['lift_ok']),
               lift_total=sum(1 for r in rows for x in r['seq']
                              if x['B'] > 0),
               max_leaves=max(x['leaves'] for r in rows for x in r['seq']),
               nontrivial=sum(1 for r in rows for x in r['seq']
                              if x['B'] == 8 and x['leaves'] > 1),
               rows=rows)
    with open('exp/v9acf/frontier_snapshots.json', 'w') as f:
        json.dump(out, f, indent=1)
    print({k: v for k, v in out.items() if k != 'rows'})


if __name__ == '__main__':
    main()
