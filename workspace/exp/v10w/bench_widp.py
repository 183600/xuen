"""Benchmark WIDP as the fixed-h oracle inside the ICF partial-certificate loop.

The main experiment is the 29 mined large-gap instances (m=2, n<=12).
The 252-instance corpus is used as a regression: its instances have m>=3,
so the dispatcher keeps the v9.0 ICF-PACT path unchanged.

Run from the workspace directory:
    .venv/bin/python exp/v10w/bench_widp.py gap
    .venv/bin/python exp/v10w/bench_widp.py main
"""
import json
import sys
import time
import collections

sys.path[:0] = ['exp/v10w', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from icf import (PartialCertificate, ICFCertificate, cmax, corpora,
                 run_icf)
from pact import PACT, pact_decide
from rdf import check_schedule
from widp import decide as widp_decide, width


def widp_eligible(inst):
    """Structural dispatcher: m<=2 and n<=14 is the WIDP regime.

    The ideal-lattice state carries m machine-availability coordinates and
    a boundary vector; for m>=3 the corpus is already served by PACT's LP
    certificate tree at a lower cost.  The threshold is a cost heuristic,
    not a correctness condition: both oracles emit the same ICF bracket.
    """
    return inst['m'] <= 2 and inst['n'] <= 14


def _initial(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return None
    proof = co._ensure_lb_proof(int(lb))
    if proof is None:
        r = pact_decide(inst, int(lb) - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    if proof is None:
        return None
    return dict(L=int(lb), U=int(ub), schedule=list(sched),
                machine=list(mach), proof=proof, co=co,
                pin_lp=int(getattr(co, 'pin_lp', 0)))


def run_widp_icf(inst, known, name, idx, policy='lower-first',
                 state_cap=200000):
    t0 = time.time()
    st = _initial(inst)
    if st is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='init', t=time.time() - t0)
    L, U = st['L'], st['U']
    sched, mach, proof = st['schedule'], st['machine'], st['proof']
    pin_lp = st['pin_lp']
    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    widp_states = 0
    widp_capped = 0
    partial_ok = partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    while L < U and probes < 64:
        L0, U0 = L, U
        use_widp = widp_eligible(inst)
        h = (U - 1) if use_widp else (L if first else (L + U) // 2)
        r = widp_decide(inst, h, state_cap=state_cap) if use_widp else None
        if use_widp:
            probes += 1
            first = False
            widp_states += r.get('states', 0)
            if r['verdict'] is False:
                proof = r['proof']
                L = h + 1
                steps.append(dict(h=h, oracle='widp', v=False,
                                  states=r.get('states'), L0=L0, U0=U0,
                                  L1=L, U1=U, audit=r.get('audit')))
            elif r['verdict'] is True:
                s2, m2 = r['schedule'], r['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
                steps.append(dict(h=h, oracle='widp', v=True, cmax=c2,
                                  states=r.get('states'), L0=L0, U0=U0,
                                  L1=L, U1=U))
            else:
                widp_capped += 1
                # fall back to the exact PACT oracle at the same h
                rr = pact_decide(inst, h, depthcap=None, nodecap=None)
                pact_lp += rr.get('lp_solves', 0)
                pact_nodes += rr.get('nodes', 0)
                pact_cert_lp += rr.get('cert_lp', 0)
                if rr['verdict'] is False:
                    proof = rr['proof']
                    L = h + 1
                elif rr['verdict'] is True:
                    s2, m2 = rr['schedule'], rr['machine']
                    c2 = cmax(inst, s2)
                    if c2 < U and check_schedule(inst, c2, s2, m2):
                        U = c2
                        sched, mach = list(s2), list(m2)
                else:
                    break
                steps.append(dict(h=h, oracle='pact-fallback', v=rr['verdict'],
                                  L0=L0, U0=U0, L1=L, U1=U))
        else:
            h = L if first else (L + U) // 2
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            probes += 1
            first = False
            pact_lp += r.get('lp_solves', 0)
            pact_nodes += r.get('nodes', 0)
            pact_cert_lp += r.get('cert_lp', 0)
            if r['verdict'] is False:
                proof = r['proof']
                L = h + 1
            elif r['verdict'] is True:
                s2, m2 = r['schedule'], r['machine']
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
            else:
                break
            steps.append(dict(h=h, oracle='pact', v=r['verdict'],
                              lp=r.get('lp_solves'), L0=L0, U0=U0,
                              L1=L, U1=U))
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(name=name, idx=idx, known=known, policy=policy,
                opt=U, lb=L, lb0=lb0, ub0=ub0,
                certified=bool(L == U and final_ok), audit=final_ok,
                queries=probes, probes=probes,
                pact_lp=pact_lp, pact_nodes=pact_nodes,
                pact_cert_lp=pact_cert_lp, pin_lp=pin_lp,
                widp_states=widp_states, widp_capped=widp_capped,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=partial_final, steps=steps,
                proof_kind=(final.lb_proof.kind if final is not None
                            else getattr(proof, 'kind', None)),
                t=round(time.time() - t0, 4),
                ok=bool(L == U and U == known and final_ok
                        and partial_fail == 0 and partial_final))


def gap_experiment():
    cases = json.load(open('exp/v10c/gap_cases.json'))
    rows = []
    for x in cases:
        inst = x['inst']
        base = run_icf(inst, x['opt'], x['case'], x['idx'],
                       policy='lower-first')
        new = run_widp_only(inst, x['opt'], x['case'], x['idx'])
        for r, tag in ((base, 'icf'), (new, 'widp')):
            r['gap_case'] = x['case']
            r['src'] = x.get('src')
            r['opt_gap'] = x.get('opt_gap')
            r['mode'] = tag
            rows.append(r)
        print('%-8s icf q=%2d lp=%4d t=%7.3f | widp q=%d st=%5d t=%7.3f '
              'cert=%s/%s'
              % (x['case'], base['queries'], base['pact_lp'], base['t'],
                 new['queries'], new['widp_states'], new['t'],
                 base['certified'], new['certified']), flush=True)
    json.dump(rows, open('exp/v10w/bench_widp_gap.json', 'w'), indent=1)
    for tag in ('icf', 'widp'):
        rs = [r for r in rows if r['mode'] == tag]
        print('\n', tag, 'n', len(rs),
              'cert', sum(r['certified'] for r in rs),
              'ok', sum(r['ok'] for r in rs),
              'partial_fail', sum(r['partial_fail'] for r in rs),
              'probes', sum(r['queries'] for r in rs),
              'lb_calls', sum(r.get('lb_calls', 0) for r in rs),
              'pact_lp', sum(r['pact_lp'] for r in rs),
              'pin_lp', sum(r['pin_lp'] for r in rs),
              'widp_states', sum(r.get('widp_states', 0) for r in rs),
              't', round(sum(r['t'] for r in rs), 2))
    return rows


def main_experiment():
    rows = []
    t0 = time.time()
    for corpus, name, idx, inst, known in corpora():
        r = run_widp_icf(inst, known, name, idx)
        r['corpus'] = corpus
        rows.append(r)
    json.dump(rows, open('exp/v10w/bench_widp_main.json', 'w'), indent=1)
    print('n', len(rows), 'cert', sum(r['certified'] for r in rows),
          'ok', sum(r['ok'] for r in rows),
          'widp_used', sum(1 for r in rows
                           if r['widp_states'] or r['widp_capped']),
          'widp_capped', sum(r['widp_capped'] for r in rows),
          'partial_fail', sum(r['partial_fail'] for r in rows),
          'probes', sum(r['queries'] for r in rows),
          'pact_lp', sum(r['pact_lp'] for r in rows),
          'pin_lp', sum(r['pin_lp'] for r in rows),
          't', round(time.time() - t0, 2))
    hist = collections.Counter((r['ub0'] - r['lb0'], r['queries'])
                               for r in rows)
    print('gap/probes', dict(sorted(hist.items())))
    return rows




def run_widp_only(inst, known, name, idx, policy='binary',
                  state_cap=200000):
    """Self-contained WIDP-ICF: cheap greedy bracket + ideal-DP probes.

    No PACT initialization is used.  The initial lower bound is the
    critical-path / machine-load bound from chip.base_bounds; the initial
    upper bound is a greedy schedule.  WIDP supplies both the lower-bound
    proof and every fixed-h decision.
    """
    from chip import base_bounds
    t0 = time.time()
    lb, ub, sched, mach, est, q = base_bounds(inst)
    if ub is None or sched is None or mach is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-greedy', t=round(time.time() - t0, 4))
    if not check_schedule(inst, ub, sched, mach):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-greedy', t=round(time.time() - t0, 4))
    L, U = int(lb), int(ub)
    sched, mach = list(sched), list(mach)
    lb0, ub0 = L, U
    init_t = time.time() - t0
    probes = 0
    lb_calls = 0
    widp_states = 0
    widp_capped = 0
    partial_ok = partial_fail = 0
    steps = []
    proof = None
    # A certified lower bound: WIDP proves NO(L-1).  The bound is sound
    # by critical path / load, so this call must be NO.
    if L > 0:
        r = widp_decide(inst, L - 1, state_cap=state_cap)
        lb_calls += 1
        widp_states += r.get('states', 0)
        if r['verdict'] is False and r.get('audit'):
            proof = r['proof']
        else:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-lb-proof', t=round(time.time() - t0, 4),
                        widp_states=widp_states)
    if proof is None:
        # L=0; an empty-domain proof is not needed for this corpus.
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='zero-lb', t=round(time.time() - t0, 4))

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    while L < U and probes < 64:
        if policy == 'binary':
            h = (L + U) // 2
        elif policy == 'lower-first':
            h = L
        else:
            h = U - 1
        r = widp_decide(inst, h, state_cap=state_cap)
        probes += 1
        widp_states += r.get('states', 0)
        L0, U0 = L, U
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(dict(h=h, v=False, states=r.get('states'),
                              L0=L0, U0=U0, L1=L, U1=U,
                              audit=r.get('audit')))
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                sched = list(r['schedule'])
                mach = list(r['machine'])
            steps.append(dict(h=h, v=True, cmax=c,
                              states=r.get('states'),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            widp_capped += 1
            rr = pact_decide(inst, h, depthcap=None, nodecap=None)
            if rr['verdict'] is False:
                L = h + 1
                proof = rr['proof']
            elif rr['verdict'] is True:
                c = cmax(inst, rr['schedule'])
                if c < U and check_schedule(inst, c, rr['schedule'],
                                            rr['machine']):
                    U = c
                    sched = list(rr['schedule'])
                    mach = list(rr['machine'])
            else:
                break
            steps.append(dict(h=h, v=rr['verdict'], oracle='pact',
                              L0=L0, U0=U0, L1=L, U1=U))
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    return dict(name=name, idx=idx, known=known, policy=policy,
                opt=U, lb=L, lb0=lb0, ub0=ub0,
                certified=bool(L == U and final_ok), audit=final_ok,
                queries=probes, probes=probes, lb_calls=lb_calls,
                pact_lp=0, pact_nodes=0, pact_cert_lp=0,
                pin_lp=0, widp_states=widp_states,
                widp_capped=widp_capped,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=partial_final, steps=steps,
                init_t=round(init_t, 4),
                probe_t=round(time.time() - t0 - init_t, 4),
                proof_kind=(final.lb_proof.kind if final is not None
                            else getattr(proof, 'kind', None)),
                t=round(time.time() - t0, 4),
                ok=bool(L == U and U == known and final_ok
                        and partial_fail == 0 and partial_final))


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'gap'
    if what == 'gap':
        gap_experiment()
    else:
        main_experiment()
