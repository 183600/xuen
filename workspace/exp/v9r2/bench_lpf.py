"""Benchmark v9.1 ICF-LPF against the v9.0 one-leaf ICF loop.

Two corpora:
  * exp/v10c/gap_cases.json : 29 mined instances with LP-pin gap 2..6
    (the regime where the one-leaf lower-first scan is expensive);
  * the 252-instance v8u corpus : gap 0/1/5, where ICF lower-first is
    already one-probe.

LP accounting for LPF: target_solves are the SDLP solves at the current
target; pin_solves are SDLP solves inside the per-leaf binary pin; cert_lp
are integer_certificate/verify calls; init_pin_lp is PACT's initial LP
pin.  The one-leaf row adds pact_lp + pact_cert_lp + pin_lp.
"""
import json
import sys
import time

sys.path[:0] = ['exp/v9r2', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import icf
from lpf import LPFrontier, cmax
from pact import PACT


def _init(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, s, m = co.initial_bounds()
    proof = co._ensure_lb_proof(L)
    init_pin = int(getattr(co, 'pin_lp', 0))
    return co, int(L), int(U), list(s), list(m), proof, init_pin


def run_lpf(inst, max_steps=5000, max_lp=5000):
    t0 = time.time()
    co, L, U, s, m, proof, init_pin = _init(inst)
    fr = LPFrontier(inst, L, U, s, m, proof)
    fr.run(max_steps=max_steps, max_lp=max_lp)
    cert = fr.certificate()
    ok = bool(cert is not None and cert.audit_rdf())
    lp = (fr.stats['target_solves'] + fr.stats['pin_solves']
          + fr.stats['cert_lp'] + init_pin)
    return dict(
        L0=L, U0=U, L=fr.L(), U=fr.U, opt=(cert.opt if cert else None),
        certified=ok, audit=ok, nodes=fr.stats['nodes'],
        splits=fr.stats['splits'], closed=fr.stats['closed'],
        prunes=fr.stats['prunes'], empty=fr.stats['empty'],
        yes=fr.stats['yes'], open=fr.stats['open'],
        target_lp=fr.stats['target_solves'],
        pin_lp=fr.stats['pin_solves'] + init_pin,
        cert_lp=fr.stats['cert_lp'], lp=lp,
        pin_fail=fr.stats['pin_fail'], queue_steps=fr.stats['queue_steps'],
        t=round(time.time() - t0, 4),
    )


def run_one_leaf(inst, known, name, idx, policy):
    r = icf.run_icf(inst, known, name, idx, policy=policy)
    r['lp'] = r['pact_lp'] + r['pact_cert_lp'] + r['pin_lp']
    return r


def gap_cases():
    for x in json.load(open('exp/v10c/gap_cases.json')):
        yield x['case'], x['inst'], x['opt']


def corpus252():
    for tag, name, idx, inst, known in icf.corpora():
        yield '%s/%s/%s' % (tag, name, idx), inst, known


def bench(rows, policies=('lower-first', 'pact', 'binary', 'upper-first')):
    out = []
    t0 = time.time()
    for j, (name, inst, known) in enumerate(rows):
        row = dict(name=name, known=known)
        row['lpf'] = run_lpf(inst)
        for pol in policies:
            row[pol] = run_one_leaf(inst, known, name, 0, pol)
        out.append(row)
        print('%3d %-22s lpf %4d LP %7.3fs  lf %4d LP %7.3fs'
              % (j, name, row['lpf']['lp'], row['lpf']['t'],
                 row['lower-first']['lp'], row['lower-first']['t']),
              flush=True)
    print('total wall %.2fs' % (time.time() - t0), flush=True)
    return out


def summarize(out, label):
    print('\n==', label, 'n=', len(out))
    ans = {}
    for key in ('lpf', 'lower-first', 'pact', 'binary', 'upper-first'):
        rs = [r[key] for r in out]
        ans[key] = dict(
            certified=sum(1 for r in rs if r.get('certified')),
            lp=sum(r['lp'] for r in rs),
            probes=sum(r.get('probes', 0) for r in rs),
            nodes=sum(r.get('nodes', 0) for r in rs),
            t=round(sum(r['t'] for r in rs), 3),
            max_lp=max((r['lp'] for r in rs), default=0),
            max_t=max((r['t'] for r in rs), default=0),
        )
        print('%-12s cert %2d/%2d  LP %6d  probes %4d  nodes %5d  t %7.2fs'
              % (key, ans[key]['certified'], len(rs), ans[key]['lp'],
                 ans[key]['probes'], ans[key]['nodes'], ans[key]['t']))
    lpf = ans['lpf']
    lf = ans['lower-first']
    print('LP ratio lpf/lower-first = %.3f  time ratio = %.3f'
          % (lpf['lp'] / max(lf['lp'], 1), lpf['t'] / max(lf['t'], 1e-9)))
    return ans


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'gap'
    rows = gap_cases() if which == 'gap' else corpus252()
    out = bench(rows)
    ans = summarize(out, which)
    json.dump(dict(rows=out, summary=ans),
              open('exp/v9r2/%s_bench.json' % which, 'w'), indent=1)
