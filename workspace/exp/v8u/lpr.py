"""v9.1 LPR-ICF: LP-guided primal rounding for invariant-carrying PACT.

The v9.0 ICF state is unchanged:

    C = (L, U, s, m, pi)

with pi : NO(L-1), (s,m) a feasible schedule of length U, and L <= U.
LPR adds three actions around that state:

    PIN    solve the fixed-h LP family once (binary search on h) and, if
           it raises L, install the Farkas proof at L-1.  This is a
           certified dual action; it reuses the v8.9 LP pin.
    ROUND  take a feasible LP solution z at some horizon >= L, turn the
           per-job start-time marginals into a priority order, and run
           serial SGS at horizon L.  A hit gives a feasible schedule of
           length <= L, so U=L and the bracket closes with no exact
           probe.  A miss changes nothing.  This is a primal heuristic:
           its output is always checked by check_schedule.
    PROBE  fall back to the complete fixed-h decision procedure, exactly
           as in v9.0.  The LPR policy probes at the current L (not at a
           binary midpoint), because after PIN the lower side is usually
           the informative one.

The guide z is *not* part of the certificate.  Soundness is still the
v9.0 bracket lemma.  The guide only decides which SGS orders to try.

The implementation is deliberately small: the LP, Farkas proofs and the
exact oracle are reused from v8.9/v9.0.  The new code is the rounding
decoder plus the budget policy.
"""
import sys
import time
import random
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from rdf import check_schedule
from po import heads_tails
from icf import cmax, PartialCertificate, ICFCertificate, corpora


def sgs(inst, order, H=None):
    """Serial SGS for one topological priority order.

    Returns (starts, machines, cmax) or None if the schedule would exceed
    H.  The result must still be checked by check_schedule; the function
    is used only as a heuristic decoder.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    elig, pred = inst['elig'], inst['pred']
    starts = [0] * n
    machine = [-1] * n
    busy = [[] for _ in range(m)]
    for i in order:
        base = 0
        for j in pred[i]:
            v = starts[j] + p[j]
            if v > base:
                base = v
        best = None
        for k in elig[i]:
            t = base
            pi = p[i]
            for a, b in busy[k]:
                if t + pi <= a:
                    break
                if t < b:
                    t = b
            cand = (t + pi, t, k)
            if best is None or cand < best:
                best = cand
        ft, t, k = best
        if H is not None and ft > H:
            return None
        starts[i] = t
        machine[i] = k
        busy[k].append((t, ft))
        busy[k].sort()
    c = max(starts[i] + inst['p'][i] for i in range(inst['n']))
    return starts, machine, c


def topo_order(inst, key):
    """Topological order by a priority key, with deterministic ties."""
    n = inst['n']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    ready = [(key(i), i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(ready)
    out = []
    while ready:
        _, i = heapq.heappop(ready)
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(ready, (key(j), j))
    return out if len(out) == n else None


def marginals(inst, ps, res):
    """Per-job start-time marginals of a feasible LP solution.

    Returns [(mean, [(t, prob), ...]), ...].  The LP is the SDLP built by
    v8.9; column keys are (job, [machine,] time).
    """
    n = inst['n']
    z = res.x
    dist = [[] for _ in range(n)]
    for c, key in enumerate(ps.cols):
        if z[c] > 1e-9:
            i, t = key[0], key[-1]
            dist[i].append((t, float(z[c])))
    out = []
    for i in range(n):
        ds = sorted(dist[i])
        tot = sum(v for _, v in ds)
        if tot <= 1e-12:
            out.append((0.0, []))
            continue
        ds = [(t, v / tot) for t, v in ds]
        mean = sum(t * v for t, v in ds)
        out.append((mean, ds))
    return out


def quantile(ds, q):
    cum = 0.0
    for t, v in ds:
        cum += v
        if cum >= q:
            return float(t)
    return float(ds[-1][0]) if ds else 0.0


def round_lp(inst, ps, res, H, restarts=50, seed=0, time_cap=0.08):
    """Try to round a fractional LP solution into a schedule of length <= H.

    Deterministic orders: quantiles of the marginal start distribution,
    the mean, latest-start and tail priorities.  Random orders: sample a
    quantile or a start time and sort ready jobs by that key.  Every
    candidate is decoded by SGS; a candidate is accepted only if it
    reaches H and passes check_schedule.
    """
    if res is None or getattr(res, 'x', None) is None:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='miss')
    t0 = time.time()
    rng = random.Random(seed)
    mrg = marginals(inst, ps, res)
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    work = 0
    best = None
    best_pair = None

    def accept(order):
        nonlocal best, best_pair, work
        if order is None:
            return False
        work += 1
        r = sgs(inst, order, H)
        if r is None:
            return False
        s, m, c = r
        if c <= H and check_schedule(inst, c, s, m):
            if best is None or c < best:
                best, best_pair = c, (s, m)
            return best <= H
        return False

    for q in (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98):
        if accept(topo_order(inst, lambda i, q=q:
                             (quantile(mrg[i][1], q) + i * 1e-6))):
            return dict(hit=True, cmax=best, schedule=best_pair[0],
                        machine=best_pair[1], work=work, kind='det')
    if accept(topo_order(inst, lambda i: (mrg[i][0] + i * 1e-6))):
        return dict(hit=True, cmax=best, schedule=best_pair[0],
                    machine=best_pair[1], work=work, kind='det')
    if accept(topo_order(inst, lambda i:
                         (-(H - tail[i] - inst['p'][i]) + i * 1e-6))):
        return dict(hit=True, cmax=best, schedule=best_pair[0],
                    machine=best_pair[1], work=work, kind='det')
    if accept(topo_order(inst, lambda i: (-tail[i] + i * 1e-6))):
        return dict(hit=True, cmax=best, schedule=best_pair[0],
                    machine=best_pair[1], work=work, kind='det')

    for it in range(restarts):
        if time.time() - t0 > time_cap:
            break
        mode = it % 5
        if mode == 0:
            q = rng.choice([0.05, 0.1, 0.2, 0.3, 0.4, 0.5,
                            0.6, 0.7, 0.8, 0.9])
            key = lambda i, q=q: (quantile(mrg[i][1], q) +
                                  rng.random() * 0.5)
        elif mode == 1:
            key = lambda i: (mrg[i][0] + rng.random() * H * 0.15)
        elif mode == 2:
            key = lambda i: (quantile(mrg[i][1], rng.random()) +
                             rng.random() * 0.1)
        elif mode == 3:
            key = lambda i: (rng.random(),)
        else:
            key = lambda i: (-tail[i] + rng.random() * 3.0)
        if accept(topo_order(inst, key)):
            return dict(hit=True, cmax=best, schedule=best_pair[0],
                        machine=best_pair[1], work=work, kind='rand')

    return dict(hit=False, cmax=None, schedule=None, machine=None,
                work=work, kind='miss')


def _pin_initial(inst):
    """Normal v8.9 initialization: chip + LP pin + LP schedule + LNS."""
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, s, m = co.initial_bounds()
    proof = co._ensure_lb_proof(L) if L <= U else None
    return co, int(L), int(U), s, m, proof


def _pin_weak(inst, L, U, s, m, proof):
    """PIN from a weak state: keep the weak upper side, install LP bound."""
    co = PACT(inst, pact_mode='complete', use_ga=False,
              use_lns=False, use_lp_sched=False)
    Lp, Up, sp, mp = co.initial_bounds()
    pin_lp = getattr(co, 'pin_lp', 0)
    if Lp > L:
        p = co._ensure_lb_proof(Lp)
        if p is not None and p.audit_rdf():
            L = int(Lp)
            proof = p
    return co, int(L), int(U), list(s), list(m), proof, pin_lp


def _guide_at(co, L):
    """Return (ps, res, extra_lp).  Reuse the last feasible LP solution.

    The guide need not be solved at L: SGS still enforces horizon L, so a
    solution at a larger horizon is only a priority hint.  If no guide
    exists, solve at L.
    """
    ps = (co.pin or {}).get('param')
    if ps is None:
        return None, None, 0
    res = co.pin.get('last_res')
    if res is not None:
        return ps, res, 0
    res = ps.solve_h(L)
    co.pin_lp += 1
    return ps, res, 1


def run_lpr(inst, known, name, idx, initial=None, mode='rand',
            pre_rand=50, post_rand=200, fresh_rand=30, time_cap=0.08,
            max_probes=8, seed=0):
    """Run LPR-ICF on one instance.

    mode:
      'rand'  deterministic + randomized rounding at L (main experiment)
      'det'   deterministic quantile rounding only
      'none'  no rounding; probe-only PIN baseline
      'fresh' retry with a fresh LP at L when the reused guide misses
    """
    t0 = time.time()
    if initial is None:
        co, L, U, s, m, proof = _pin_initial(inst)
        pin_lp = getattr(co, 'pin_lp', 0)
        L0, U0 = L, U
    else:
        L0, U0, s0, m0, proof0 = initial
        L, U = int(L0), int(U0)
        s, m, proof = list(s0), list(m0), proof0
        co, L, U, s, m, proof, pin_lp = _pin_weak(
            inst, L, U, s, m, proof)
        L0, U0 = int(L0), int(U0)

    probes = 0
    search_lp = 0
    cert_lp = 0
    round_work = 0
    partial_ok = 0
    partial_fail = 0
    steps = []

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    def use_sched(c, s2, m2):
        nonlocal U, s, m
        if c < U and check_schedule(inst, c, s2, m2):
            U = c
            s, m = list(s2), list(m2)
            return True
        return False

    def try_round(rr, fresh=False, cap=time_cap):
        nonlocal round_work, pin_lp
        ps, res, extra = _guide_at(co, L)
        pin_lp += extra
        if ps is None or res is None:
            return None
        r = round_lp(inst, ps, res, L, restarts=rr, seed=seed,
                     time_cap=cap)
        round_work += r['work']
        if r['hit']:
            return r
        if fresh:
            ps2 = (co.pin or {}).get('param')
            if ps2 is not None:
                res2 = ps2.solve_h(L)
                co.pin_lp += 1
                pin_lp += 1
                if res2 is None:
                    return None
                r2 = round_lp(inst, ps2, res2, L, restarts=rr,
                              seed=seed + 7919, time_cap=cap)
                round_work += r2['work']
                if r2['hit']:
                    return r2
        return None

    audit()

    if mode != 'none' and L < U:
        rr = 0 if mode == 'det' else pre_rand
        r = try_round(rr, fresh=(mode == 'fresh'))
        if r is not None:
            use_sched(r['cmax'], r['schedule'], r['machine'])
            steps.append(('ROUND', L, r['cmax'], r['kind']))
            audit()

    while L < U and probes < max_probes:
        h = L
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
            if L >= U:
                break
            if mode != 'none':
                rr = 0 if mode == 'det' else post_rand
                rr2 = try_round(rr, fresh=(mode == 'fresh'))
                if rr2 is not None:
                    use_sched(rr2['cmax'], rr2['schedule'],
                              rr2['machine'])
                    steps.append(('ROUND', L, rr2['cmax'], rr2['kind']))
                    audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))
            break

    if L < U and probes < max_probes:
        h = U - 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))

    final = (ICFCertificate(inst, U, s, m, proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
    partial_final = bool(pc.audit_rdf())
    total_lp = search_lp + cert_lp + pin_lp
    return dict(
        name=name, idx=idx, known=known, mode=mode,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp, total_lp=total_lp, round_work=round_work,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        certified=bool(L == U and final_ok), audit=final_ok,
        proof=final_ok, cert_h=(U - 1 if L == U else None),
        proof_kind=getattr(proof, 'kind', None),
        steps=steps, t=round(time.time() - t0, 4),
        schedule=list(s) if s is not None else None,
        machine=list(m) if m is not None else None,
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and partial_final))


def weak_rows(min_gap=4):
    from hap import weak_rows as _weak
    return _weak(min_gap)


def main_rows():
    return corpora()
