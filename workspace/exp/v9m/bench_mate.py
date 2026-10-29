"""Fixed-h and end-to-end benchmarks for matching-guided MATE branching."""
import json
import sys
import time

sys.path[:0] = ['exp/v9m', 'exp/v8u', 'exp/v8j', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import icf
from icf import corpora, run_icf
from mate import pact_decide as mate_decide
from pact import pact_decide

POL = {'matching': 'unmatched', 'split': 0.25}


def fixed_h(rows):
    out = []
    for corpus, name, idx, inst, known in rows:
        h = known - 1
        d = pact_decide(inst, h, depthcap=None, nodecap=None)
        t0 = time.time()
        m = mate_decide(inst, h, depthcap=None, nodecap=None, policy=POL)
        dt = time.time() - t0
        out.append(dict(
            corpus=corpus, name=name, idx=idx, n=inst['n'], h=h,
            d_nodes=d['nodes'], d_lp=d['lp_solves'],
            d_audit=bool(d['proof'].audit_rdf()),
            m_nodes=m['nodes'], m_lp=m['lp_solves'], m_depth=m['depth'],
            m_audit=bool(m['proof'].audit_rdf()), m_t=round(dt, 5)))
    print('fixed-h default', sum(x['d_nodes'] for x in out),
          'match25', sum(x['m_nodes'] for x in out),
          'audit', sum(x['m_audit'] for x in out),
          'better/equal/worse',
          sum(x['m_nodes'] < x['d_nodes'] for x in out),
          sum(x['m_nodes'] == x['d_nodes'] for x in out),
          sum(x['m_nodes'] > x['d_nodes'] for x in out))
    json.dump(out, open('exp/v9m/match25_per_case.json', 'w'), indent=1)


def end_to_end(rows):
    base = json.load(open('exp/v8u/bench_icf_lower-first.json'))
    base_lp = sum(x['pact_lp'] for x in base)
    base_t = sum(x['t'] for x in base)
    orig = icf.pact_decide

    def dec(inst, h, **kw):
        kw = dict(kw)
        kw.pop('nodecap', None)
        kw.pop('depthcap', None)
        return mate_decide(inst, h, depthcap=None, nodecap=None,
                           policy=POL, **kw)

    icf.pact_decide = dec
    out = []
    t0 = time.time()
    for corpus, name, idx, inst, known in rows:
        r = run_icf(inst, known, name, idx, policy='lower-first')
        out.append(dict(name=name, idx=idx, corpus=corpus, ok=r['ok'],
                        certified=r['certified'], audit=r['audit'],
                        pact_lp=r['pact_lp'], pact_nodes=r['pact_nodes'],
                        pact_cert_lp=r['pact_cert_lp'],
                        pin_lp=r['pin_lp'], probes=r['probes'],
                        t=r['t'], partial_fail=r['partial_fail']))
    icf.pact_decide = orig
    print('end-to-end base', base_lp, round(base_t, 2), 'match25',
          sum(x['pact_lp'] for x in out), round(time.time() - t0, 2))
    print('ok', sum(x['ok'] for x in out),
          'audit', sum(x['audit'] for x in out),
          'partial_fail', sum(x['partial_fail'] for x in out))
    json.dump(out, open('exp/v9m/bench_mate_icf.json', 'w'), indent=1)


if __name__ == '__main__':
    rows = list(corpora())
    fixed_h(rows)
    end_to_end(rows)
