"""Anytime frontier experiment: suspend/resume a fixed-h NO search.

For every gap-1 instance whose lower-first probe is a NO at h=OPT-1,
run the AID-Frontier with a sequence of LP budgets.  Each interrupted
state is converted into a PartialFrontierCertificate (schedule from the
outer initial bounds) and audited.  The experiment records the frontier
lower bound, the number of open leaves, and whether L moves monotonically.
"""
import json
import sys
import collections

sys.path[:0] = ['exp/v9ai', 'exp/v9a', 'exp/v8j', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from icf import corpora, cmax
from pact import PACT
from aidf import (search, PartialFrontierCertificate, LiftedFrontierProof,
                  leaves, Open)
from icfaid import choose_h


BUDGETS = (0, 1, 2, 4, 8, 16, 10000)


def selected_rows():
    base = json.load(open('exp/v8u/bench_icf_lower-first.json'))
    keys = {(r['corpus'], r['name'], r['idx']):
            (r['lb0'], r['ub0']) for r in base}
    for corpus, name, idx, inst, known in corpora():
        L, U = keys[(corpus, name, idx)]
        if U - L == 1 and L == known - 1:
            yield corpus, name, idx, inst, known, L, U


def main():
    rows = []
    for corpus, name, idx, inst, known, L, U in selected_rows():
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        assert ub == known and cmax(inst, sched) == known
        seq = []
        prev_L = None
        mono = True
        for B in BUDGETS:
            s = search(inst, L, budget=B)
            pc = PartialFrontierCertificate(inst, L, s.local_L(), U,
                                             sched, mach, s.tree)
            audit = bool(pc.audit_rdf())
            Lf = s.local_L()
            if prev_L is not None and Lf < prev_L:
                mono = False
            prev_L = Lf
            proof_ok = None
            if s.verdict is False:
                p = s.proof()
                proof_ok = bool(p is not None and p.audit_rdf())
            lift_ok = bool(LiftedFrontierProof(
                inst, Lf - 1, L, s.tree).audit_rdf())
            seq.append(dict(B=B, verdict=s.verdict, L=Lf,
                            open=s.stats['open_leaves'],
                            leaves=s.stats['leaves'],
                            lp=s.stats['lp_solves'],
                            cert_lp=s.stats['cert_lp'],
                            audit=audit, proof=proof_ok,
                            lift=lift_ok, t=s.stats['t']))
        rows.append(dict(corpus=corpus, name=name, idx=idx,
                         known=known, h=L, U=U, mono=mono,
                         seq=seq))
    out = dict(instances=len(rows),
               budgets=list(BUDGETS),
               audit_pass=sum(1 for r in rows for x in r['seq']
                              if x['audit']),
               audit_total=sum(len(r['seq']) for r in rows),
               lift_pass=sum(1 for r in rows for x in r['seq']
                             if x['lift']),
               lift_total=sum(len(r['seq']) for r in rows),
               mono=sum(r['mono'] for r in rows),
               completed=sum(1 for r in rows
                             if r['seq'][-1]['verdict'] is False
                             and r['seq'][-1]['proof']),
               rows=rows)
    with open('exp/v9ai/frontier_budget.json', 'w') as f:
        json.dump(out, f, indent=1)
    print({k: v for k, v in out.items() if k != 'rows'})
    # aggregate by budget
    for pos, B in enumerate(BUDGETS):
        xs = [r['seq'][pos] for r in rows]
        print('B', B, 'L', round(sum(x['L'] for x in xs) / len(xs), 3),
              'open', round(sum(x['open'] for x in xs) / len(xs), 3),
              'audit', sum(x['audit'] for x in xs), '/', len(xs),
              'done', sum(x['verdict'] is False for x in xs),
              'lp', sum(x['lp'] for x in xs))
    # representative sequence
    rep = max(rows, key=lambda r: max(x['leaves'] for x in r['seq']))
    print('representative', rep['corpus'], rep['name'], rep['idx'],
          'h', rep['h'], 'U', rep['U'])
    for x in rep['seq']:
        print(x)


if __name__ == '__main__':
    main()
