"""End-to-end AEGIS vs v9.0 ICF lower-first on the 29 gap cases."""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10c', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from aegis import run_aegis, load_gap_cases
from icf import run_icf


def main():
    meta = json.load(open('exp/v10c/bench_aegis.json'))
    theta = meta['selected_x']
    cases = load_gap_cases()
    print('theta', [round(v, 4) for v in theta], flush=True)
    rows = []
    for d in cases:
        inst = d['inst']
        opt = int(d['opt'])
        name = d['case']
        t = time.time()
        a = run_aegis(inst, opt, name, d.get('idx'), theta=theta,
                      policy='lower-first', theta_gap=2)
        ta = time.time() - t
        t = time.time()
        b = run_icf(inst, opt, name, d.get('idx'), policy='lower-first')
        tb = time.time() - t
        rows.append(dict(case=name, src=d['src'], kind=d['kind'],
                         opt=opt, gap0=int(d['ub0']) - int(d['lb0']),
                         aegis=a, icf=b, t_aegis=round(ta, 3),
                         t_icf=round(tb, 3)))
        print(name, 'gap', d['ub0'] - d['lb0'],
              '| aegis q/lp/cert/fb', a['queries'], a['pact_lp'],
              a['pact_cert_lp'], a['fallbacks'],
              '| icf q/lp/cert', b['queries'], b['pact_lp'],
              b['pact_cert_lp'],
              '| ok', a['ok'], b['ok'], flush=True)
    with open('exp/v10c/bench_gap_e2e.json', 'w') as f:
        json.dump(rows, f, indent=1)

    for kind in ('orig', 'pert', 'all'):
        rs = rows if kind == 'all' else [r for r in rows if r['kind'] == kind]
        print('\n==', kind, len(rs))
        for tag in ('aegis', 'icf'):
            print(tag,
                  'cert', sum(r[tag]['certified'] for r in rs),
                  'ok', sum(r[tag]['ok'] for r in rs),
                  'q', sum(r[tag]['queries'] for r in rs),
                  'searchLP', sum(r[tag]['pact_lp'] for r in rs),
                  'certLP', sum(r[tag]['pact_cert_lp'] for r in rs),
                  'totalLP', sum(r[tag]['pact_lp'] + r[tag]['pact_cert_lp']
                                 for r in rs),
                  'static', sum(r[tag]['static_closed'] for r in rs),
                  'fallback', sum(r[tag]['fallbacks'] for r in rs),
                  'partial_fail', sum(r[tag]['partial_fail'] for r in rs),
                  't', round(sum(r['t_' + tag] for r in rs), 2))
        hard = [r for r in rs if r['gap0'] >= 2 and r['icf']['pact_lp'] >= 60]
        print('hard n', len(hard),
              'aegisLP', sum(r['aegis']['pact_lp'] + r['aegis']['pact_cert_lp']
                             for r in hard),
              'icfLP', sum(r['icf']['pact_lp'] + r['icf']['pact_cert_lp']
                           for r in hard))


if __name__ == '__main__':
    main()
