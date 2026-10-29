"""Benchmark v9.0 PACT-R: residual contracts, ledgers, resumption.

Outputs (all under exp/v8p/):
  bench_pact_r.json       -- 252-instance main run
  paired_baseline.json    -- PACT-C vs PACT-R in one process
  residual_budget.json    -- node-budget sweep on the 58 NO probes
  resume_compare.json     -- restart vs resume on the same 58 probes
  ledger_tamper.json      -- checker mutations

Run:  .venv/bin/python exp/v8p/bench_pact_r.py
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import run_pact
from pact_r import run_pact_r
from residual import decide, resume_proof


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


def summarize(rows, label):
    print('\n==', label, '==')
    print('n', len(rows), 'ok', sum(r['ok'] for r in rows),
          'cert', sum(r['certified'] for r in rows),
          'q', sum(r['queries'] for r in rows),
          'audit', sum(r['total_audit'] for r in rows))
    for c in ('base', 'pert', 'stress'):
        rs = [r for r in rows if r['corpus'] == c]
        print(c, len(rs), 'ok', sum(r['ok'] for r in rs),
              'res_no', sum(r['res_no'] for r in rs),
              'res_yes', sum(r['res_yes'] for r in rs),
              'res_open', sum(r['res_open'] for r in rs),
              'lp', sum(r['res_lp'] for r in rs),
              'cert', sum(r['res_cert_lp'] for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    print('kinds', dict(collections.Counter(r['proof_kind']
                                            for r in rows)))


def main_run():
    rows = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        r = run_pact_r(inst, known, name, idx, mode='complete')
        r['corpus'] = tag
        r['uid'] = k
        rows.append(r)
    wall = round(time.time() - t0, 2)
    with open('exp/v8p/bench_pact_r.json', 'w') as f:
        json.dump(rows, f, indent=1)
    print('\nmain wall', wall)
    summarize(rows, 'PACT-R complete')
    return rows


def no_probes(rows):
    """Yield each NO probe with its corpus row identity.

    The stress corpus deliberately repeats ``(name, idx, known)`` for
    different instances, so metadata alone is not a key.  ``uid`` is the
    position in the deterministic corpus order.
    """
    for k, (tag, name, idx, inst, known) in enumerate(corpora()):
        if k >= len(rows):
            continue
        r = rows[k]
        if r.get('uid') != k:
            raise ValueError('main rows are not in corpus order')
        for p in r['probe_log']:
            if p['v'] is False:
                yield k, tag, name, idx, known, inst, p['h'], p['engine']


def budget_sweep(rows):
    budgets = [0, 1, 2, 3, 4, 5, 6, 8, 9]
    out = []
    agg = {B: dict(open=0, closed=0, audit=0, holes=0, lp=0,
                   nodes=0) for B in budgets}
    for B in budgets:
        for uid, tag, name, idx, known, inst, h, eng in no_probes(rows):
            r = decide(inst, h, nodecap=B)
            p = r['proof']
            led = dict(p.ledger) if p is not None else {}
            au = bool(p is not None and p.audit_rdf())
            rec = dict(uid=uid, corpus=tag, name=name, idx=idx,
                       known=known, h=h, budget=B, verdict=r['verdict'],
                       nodes=r['nodes'], lp=r['lp_solves'],
                       cert_lp=r['cert_lp'], holes=r['holes'],
                       ledger=led, audit=au,
                       reason=r.get('reason'))
            out.append(rec)
            a = agg[B]
            a['open'] += int(r['verdict'] is None)
            a['closed'] += int(r['verdict'] is False)
            a['audit'] += int(au)
            a['holes'] += led.get('open_leaves', 0)
            a['lp'] += r['lp_solves']
            a['nodes'] += r['nodes']
    with open('exp/v8p/residual_budget.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n== residual budget sweep (58 NO probes) ==')
    for B in budgets:
        a = agg[B]
        print(B, 'open', a['open'], 'closed', a['closed'],
              'audit', a['audit'], 'holes', a['holes'],
              'lp', a['lp'], 'nodes', a['nodes'])
    return out, agg


def resume_compare(rows):
    out = []
    for uid, tag, name, idx, known, inst, h, eng in no_probes(rows):
        t0 = time.time()
        restart = []
        closed_d = None
        for d in range(0, 9):
            rr = decide(inst, h, depthcap=d)
            restart.append(rr['lp_solves'])
            if rr['verdict'] is not None:
                closed_d = d
                break
        rt = time.time() - t0

        t0 = time.time()
        rr = decide(inst, h, depthcap=0)
        resume = [rr['lp_solves']]
        ok = False
        steps = 1
        for d in range(1, 9):
            if rr['verdict'] is not None:
                ok = True
                break
            z = resume_proof(inst, h, rr['proof'], depthcap=d)
            steps += 1
            resume.append(z['lp_solves'])
            if z['proof'] is not None:
                rr = z
            if z['verdict'] is not None:
                ok = True
                break
        rt2 = time.time() - t0
        out.append(dict(uid=uid, corpus=tag, name=name, idx=idx,
                        known=known, h=h, engine=eng,
                        closed_depth=closed_d,
                        restart_lp=sum(restart),
                        restart_nodes=restart,
                        resume_lp=sum(resume),
                        resume_nodes=resume,
                        restart_steps=len(restart),
                        resume_steps=len(resume),
                        ok=ok, restart_t=round(rt, 4),
                        resume_t=round(rt2, 4)))
    with open('exp/v8p/resume_compare.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n== restart vs resume (58 NO probes) ==')
    print('restart_lp', sum(x['restart_lp'] for x in out),
          'resume_lp', sum(x['resume_lp'] for x in out),
          'ratio', round(sum(x['restart_lp'] for x in out)
                         / max(1, sum(x['resume_lp'] for x in out)), 2),
          'restart_t', round(sum(x['restart_t'] for x in out), 2),
          'resume_t', round(sum(x['resume_t'] for x in out), 2),
          'ok', sum(x['ok'] for x in out))
    for k in sorted({x['closed_depth'] for x in out
                     if x['closed_depth'] is not None}):
        xs = [x for x in out if x['closed_depth'] == k]
        print('k', k, 'n', len(xs),
              'restart', sum(x['restart_lp'] for x in xs),
              'resume', sum(x['resume_lp'] for x in xs),
              'shapes', collections.Counter(
                  tuple(x['restart_nodes']) for x in xs).most_common(3))
    return out


def tamper(rows):
    """Mutate ledgers and residuals; the checker must reject all."""
    tests = []
    _uid, tag, name, idx, known, inst, h, eng = next(no_probes(rows))
    p = decide(inst, h)['proof']
    base = p.audit_rdf()
    tests.append(dict(target='closed', mutation='none', result=base))
    for k in ('height', 'nodes', 'lp', 'cert_lp', 'open_leaves'):
        old = p.ledger[k]
        p.ledger[k] = old + 1
        tests.append(dict(target='closed', mutation=k,
                          result=p.audit_rdf()))
        p.ledger[k] = old
    p2 = decide(inst, h, nodecap=1)['proof']
    tests.append(dict(target='residual', mutation='none',
                      result=p2.audit_rdf()))
    hole = p2.holes()[0][0]
    hole.reason = 'bogus'
    tests.append(dict(target='residual', mutation='bad-reason',
                      result=p2.audit_rdf()))
    hole.reason = 'budget'
    hole.tag = 'leaf'
    tests.append(dict(target='residual', mutation='open-to-leaf',
                      result=p2.audit_rdf()))
    hole.tag = 'open'
    tests.append(dict(target='residual', mutation='restored',
                      result=p2.audit_rdf()))
    with open('exp/v8p/ledger_tamper.json', 'w') as f:
        json.dump(tests, f, indent=1)
    print('\n== ledger / residual tamper ==')
    for t in tests:
        print(t)
    return tests


def paired_baseline():
    cas = list(corpora())
    res = {}
    for which in ('C', 'R'):
        t0 = time.time()
        ok = q = audit = lp = cert = 0
        ts = []
        for tag, name, idx, inst, known in cas:
            if which == 'C':
                r = run_pact(inst, known, name, idx, pact_depth=None,
                             use_ga=False, complete_fallback=True)
            else:
                r = run_pact_r(inst, known, name, idx, mode='complete')
            ts.append(r['t'])
            ok += int(r['ok'])
            q += r['queries']
            audit += int(r['total_audit'])
            lp += (r.get('pact_lp', 0) if which == 'C'
                   else r['res_lp'])
            cert += (r.get('pact_cert_lp', 0) if which == 'C'
                     else r['res_cert_lp'])
        res[which] = dict(wall=round(time.time() - t0, 2),
                          sum_t=round(sum(ts), 2), ok=ok, q=q,
                          audit=audit, lp=lp, cert=cert)
        print(which, res[which])
    with open('exp/v8p/paired_baseline.json', 'w') as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == '__main__':
    rows = main_run()
    paired_baseline()
    budget_sweep(rows)
    resume_compare(rows)
    tamper(rows)
