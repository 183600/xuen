import sys
import time
import json
import collections

sys.path[:0] = ['exp/v8s', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from sgpact import SGPACT


def corpora():
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known


def main():
    t0 = time.time()
    rows = []
    nok = 0
    for tag, name, idx, inst, known in corpora():
        co = SGPACT(inst)
        t1 = time.time()
        r = co.optimize()
        dt = time.time() - t1
        b = getattr(co, 'chip', None) or {}
        p = getattr(co, 'pin', None) or {}
        rec = dict(tag=tag, name=name, idx=idx, known=known,
                   opt=r['opt'], lb0=r.get('lb0'), ub0=r.get('ub0'),
                   t=round(dt, 4), pact_lp=co.pact_lp,
                   pact_cert_lp=co.pact_cert_lp,
                   pact_nodes=co.pact_nodes,
                   pin_lb=p.get('lb'), pin_solves=p.get('solves'),
                   pin_lp=getattr(co, 'pin_lp', 0),
                   chip_lb=b.get('lb'), chip_ub=b.get('ub'),
                   queries=r['queries'],
                   sgs_calls=co.sgs_calls, sgs_tries=co.sgs_tries,
                   sgs_yes=co.sgs_yes, sgs_time=round(co.sgs_time, 4),
                   stage1=co.stage1, stage2=co.stage2,
                   stage3=co.stage3,
                   certified=r['certified'], audit=r['audit'],
                   proof=bool(r['proof']),
                   total_audit=r['total_audit'],
                   cert_h=r.get('cert_h'),
                   engines=collections.Counter(
                       st.get('engine') for st in co.steps))
        rec['ok'] = bool(rec['certified'] and rec['opt'] == known
                         and rec['audit'] and rec['proof']
                         and rec['total_audit']
                         and rec['cert_h'] == known - 1)
        nok += rec['ok']
        rows.append(rec)
    wall = time.time() - t0
    out = dict(rows=rows, n=len(rows), ok=nok, wall=round(wall, 4),
               q=sum(r['queries'] for r in rows),
               pact_lp=sum(r['pact_lp'] for r in rows),
               pact_cert_lp=sum(r['pact_cert_lp'] for r in rows),
               pact_nodes=sum(r['pact_nodes'] for r in rows),
               sgs_yes=sum(r['sgs_yes'] for r in rows),
               sgs_tries=sum(r['sgs_tries'] for r in rows),
               sgs_time=round(sum(r['sgs_time'] for r in rows), 4),
               stage1=sum(r['stage1'] for r in rows),
               stage2=sum(r['stage2'] for r in rows),
               stage3=sum(r['stage3'] for r in rows),
               total_audit=sum(r['total_audit'] for r in rows),
               engines=dict(collections.Counter(
                   k for r in rows for k, v in r['engines'].items()
                   for _ in range(v))))
    with open('exp/v8s/bench_sgpact.json', 'w') as f:
        json.dump(out, f, indent=1)
    print(dict(n=out['n'], ok=out['ok'], wall=out['wall'],
               q=out['q'], pact_lp=out['pact_lp'],
               pact_nodes=out['pact_nodes'], sgs_yes=out['sgs_yes'],
               sgs_tries=out['sgs_tries'], sgs_time=out['sgs_time'],
               stage1=out['stage1'], stage2=out['stage2'],
               stage3=out['stage3'], total_audit=out['total_audit']))
    print('engines', out['engines'])
    bad = [r for r in rows if not r['ok']]
    print('bad', [(r['tag'], r['name'], r['idx']) for r in bad])


if __name__ == '__main__':
    main()
