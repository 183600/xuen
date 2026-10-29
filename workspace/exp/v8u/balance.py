"""BALANCE-ICF: Bayesian Adaptive LNS with Certified Enclosure.

The state is an ICF partial certificate (L,U,s,m,pi) plus a belief p over
OPT in [L,U].  The certificate invariant is independent of p.  Two moves
act on the state:

  * PROBE(h): call the fixed-h decision oracle; a NO raises L, a YES
    lowers U, and both preserve the certificate.
  * LNS(k): destroy k jobs of the incumbent, repair the restriction, and
    install the result only if an independent schedule check passes.

The probe horizon is chosen by an optimal threshold decision tree for p
(unconstrained or depth-capped), or by a baseline policy.  LNS is
optional; it only changes the upper bound and cannot harm soundness.
"""
import sys
import math
import random
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate
from odc import weak_bounds
from pact import PACT, pact_decide
from rdf import check_schedule

INF = 1e18


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


# --------------------------------------------------------------- prior
def fit_prior(rows, eps=0.5):
    """Fit P(d=OPT-L0 | g=U0-L0) with Laplace smoothing."""
    tab = collections.defaultdict(collections.Counter)
    for r in rows:
        g = r['U'] - r['L']
        d = r['known'] - r['L']
        if 0 <= d <= g:
            tab[g][d] += 1
    out = {}
    for g, c in tab.items():
        w = [c.get(d, 0) + eps for d in range(g + 1)]
        z = sum(w)
        out[g] = [x / z for x in w]
    return out


def prior_weights(table, g):
    if g in table:
        return list(table[g])
    if g <= 0:
        return [1.0]
    lo = max([x for x in table if x <= g], default=None)
    hi = min([x for x in table if x >= g], default=None)
    if lo is not None and hi is not None and lo != hi:
        a = table[lo]
        b = table[hi]
        al = (g - lo) / float(hi - lo)
        w = [(1 - al) * a[min(len(a) - 1, d)] + al * b[min(len(b) - 1, d)]
             for d in range(g + 1)]
        z = sum(w)
        return [x / z for x in w]
    # hedge: tight-L, tight-U, and uniform
    w = [0.01 + 0.40 * (d == 0) + 0.40 * (d == g) for d in range(g + 1)]
    z = sum(w)
    return [x / z for x in w]


# --------------------------------------------------------------- Bayes DP
def dp_choice(w, cap=None, lam=0.0, floor=0.0):
    """Optimal threshold for belief w over consecutive OPT values.

    Returns (relative h, value).  The probe cost is
        1 + lam * (h - left) / max(1, right - left).
    cap is the remaining depth (None = unconstrained).
    """
    n = len(w)
    if n <= 1:
        return 0, 0.0
    s = sum(w)
    if s <= 0:
        w = [1.0] * n
        s = float(n)
    if floor > 0:
        w = [(1 - floor) * x / s + floor / n for x in w]
        s = 1.0
    pre = [0.0]
    for x in w:
        pre.append(pre[-1] + x)

    if cap is None:
        V = [[0.0] * n for _ in range(n)]
        C = [[-1] * n for _ in range(n)]
        for ln in range(2, n + 1):
            for i in range(n - ln + 1):
                j = i + ln - 1
                tot = pre[j + 1] - pre[i]
                best, bh = INF, -1
                for h in range(i, j):
                    pno = (pre[h + 1] - pre[i]) / tot
                    cost = 1.0 + lam * (h - i) / max(1, j - i)
                    val = cost + pno * V[i][h] + (1 - pno) * V[h + 1][j]
                    if val < best - 1e-12:
                        best, bh = val, h
                V[i][j] = best
                C[i][j] = bh
        return C[0][n - 1], V[0][n - 1]

    V = [[[INF] * n for _ in range(n)] for _ in range(cap + 1)]
    C = [[[-1] * n for _ in range(n)] for _ in range(cap + 1)]
    for d in range(cap + 1):
        for i in range(n):
            V[d][i][i] = 0.0
    for d in range(1, cap + 1):
        for ln in range(2, n + 1):
            for i in range(n - ln + 1):
                j = i + ln - 1
                tot = pre[j + 1] - pre[i]
                best, bh = INF, -1
                for h in range(i, j):
                    pno = (pre[h + 1] - pre[i]) / tot
                    cost = 1.0 + lam * (h - i) / max(1, j - i)
                    val = (cost + pno * V[d - 1][i][h]
                           + (1 - pno) * V[d - 1][h + 1][j])
                    if val < best - 1e-12:
                        best, bh = val, h
                V[d][i][j] = best
                C[d][i][j] = bh
    return C[cap][0][n - 1], V[cap][0][n - 1]


def parse_policy(policy):
    """Return (kind, cap, lam, floor) from a policy name."""
    parts = policy.split(':')
    kind = parts[0]
    cap = None
    lam = 0.0
    floor = 0.0
    for x in parts[1:]:
        if x.startswith('d'):
            cap = int(x[1:])
        elif x.startswith('l'):
            lam = float(x[1:])
        elif x.startswith('f'):
            floor = float(x[1:])
    if kind == 'bayes-cap' and cap is None:
        cap = 4
    return kind, cap, lam, floor


def choose_h(policy, L, U, L0, weights, first):
    g = U - L
    if g <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'upper-once':
        return U - 1 if first else (L + U) // 2
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if g <= 4 else (L + U) // 2
    if policy == 'bayes-oracle':
        policy = 'bayes-cap:3'
    kind, cap, lam, floor = parse_policy(policy)
    if kind not in ('bayes', 'bayes-cap', 'bayes-uniform', 'bayes-wrong'):
        raise ValueError('unknown policy %r' % policy)
    if kind == 'bayes-uniform':
        w = [1.0] * (g + 1)
    else:
        w = [weights[d] for d in range(L - L0, U - L0 + 1)]
    if cap is None and kind == 'bayes-cap':
        cap = max(1, int(math.ceil(math.log2(g + 1))) + 1)
    hrel, _ = dp_choice(w, cap=cap, lam=lam, floor=floor)
    return L + hrel


# --------------------------------------------------------------- state
class ProbeCache:
    """Deterministic cache for pact_decide at a fixed instance."""

    def __init__(self):
        self.d = {}
        self.hits = 0
        self.misses = 0

    def get(self, inst, h):
        key = int(h)
        if key in self.d:
            self.hits += 1
            return self.d[key]
        self.misses += 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        self.d[key] = r
        return r


def initial_state(inst, known, init='weak', cache=None):
    """Return a dict with the initial ICF bracket and its lower proof."""
    if init == 'pact':
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        if U is None:
            return None
        lb_proof = co._ensure_lb_proof(L)
        init_lp = 0
        if lb_proof is None:
            r = (cache.get(inst, L - 1) if cache is not None
                 else pact_decide(inst, L - 1, depthcap=None, nodecap=None))
            init_lp = r.get('lp_solves', 0)
            if r['verdict'] is False:
                lb_proof = r['proof']
        if lb_proof is None:
            return None
        return dict(L=int(L), U=int(U), s=list(s), m=list(m),
                    pi=lb_proof, init_lp=init_lp,
                    init_cert=0, init='pact')
    L, U, s, m = weak_bounds(inst)
    if U is None:
        return None
    L, U = int(L), int(U)
    r = (cache.get(inst, L - 1) if cache is not None
         else pact_decide(inst, L - 1, depthcap=None, nodecap=None))
    if r['verdict'] is not False:
        return None
    return dict(L=L, U=U, s=list(s), m=list(m), pi=r['proof'],
                init_lp=r.get('lp_solves', 0),
                init_cert=r.get('cert_lp', 0), init='weak')


def _natural_alternative(h, L, U, blocked):
    """Nearest non-blocked horizon to h inside [L,U-1]."""
    if h not in blocked and L <= h < U:
        return h
    for d in range(1, U - L + 1):
        for x in (h - d, h + d):
            if L <= x < U and x not in blocked:
                return x
    return None


def run_balance(inst, known, name, idx, init='weak', policy='bayes-cap:4',
                prior_table=None, max_probes=64, cache=None,
                lns=None, audit=True):
    """Run BALANCE and return a benchmark row.

    lns: optional dict(budget, kmax, tlim, stall, seed, trigger)
    trigger: 'never' (default), 'always', 'gap1', 'frac:30'
    """
    t0 = __import__('time').time()
    if cache is None:
        cache = ProbeCache()
    st = initial_state(inst, known, init=init, cache=cache)
    if st is None:
        return dict(name=name, idx=idx, known=known, init=init,
                    policy=policy, ok=False, error='no-initial-state',
                    t=0.0)
    L, U, s, m, pi = st['L'], st['U'], st['s'], st['m'], st['pi']
    L0, U0 = L, U
    g0 = U0 - L0
    weights = prior_weights(prior_table or {}, g0)
    probes = 0
    lp = 0
    cert_lp = 0
    unknown = 0
    blocked = set()
    first = True
    steps = []
    partial_ok = 0
    partial_fail = 0
    lns_trials = 0
    lns_ok = 0
    lns_checks = 0
    lns_lp = 0
    lns_t = 0.0
    oracle = 0 if L0 == U0 == known else (
        1 if (L0 == known) ^ (U0 == known) else 2)

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, pi, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    while L < U and probes < max_probes:
        # optional primal move
        if lns is not None:
            trig = lns.get('trigger', 'never')
            do = (trig == 'always' or
                  (trig == 'gap1' and U - L == 1) or
                  (trig.startswith('frac:') and
                   0.0 < _root_fraction(inst, L, cache) >=
                   float(trig.split(':')[1])))
            if do:
                nU, ns, nm, stats = lns_trial(
                    inst, U, s, m, budget=lns.get('budget', 12),
                    kmax=lns.get('kmax', 14), tlim=lns.get('tlim', 0.2),
                    stall=lns.get('stall', 6), seed=lns.get('seed', 0))
                lns_trials += 1
                lns_checks += stats['checks']
                lns_t += stats['t']
                if nU < U and ns is not None:
                    if check_schedule(inst, nU, ns, nm):
                        U, s, m = nU, list(ns), list(nm)
                        lns_ok += 1
                        audit_state()
                        if L == U:
                            break
        h = choose_h(policy, L, U, L0, weights, first)
        h = _natural_alternative(h, L, U, blocked)
        if h is None:
            break
        r = cache.get(inst, h)
        probes += 1
        first = False
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        L_old, U_old = L, U
        if r['verdict'] is False:
            L = h + 1
            pi = r['proof']
            steps.append(dict(h=h, v=False, lp=r.get('lp_solves', 0),
                              L0=L_old, U0=U_old, L1=L, U1=U))
        elif r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                s, m = list(r['schedule']), list(r['machine'])
            steps.append(dict(h=h, v=True, cmax=c,
                              lp=r.get('lp_solves', 0),
                              L0=L_old, U0=U_old, L1=L, U1=U))
        else:
            unknown += 1
            blocked.add(h)
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              L0=L_old, U0=U_old, L1=L, U1=U))
        audit_state()

    final = ICFCertificate(inst, U, s, m, pi) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial_final = bool(PartialCertificate(
        inst, L, U, s, m, pi, probe=probes).audit_rdf())
    dt = __import__('time').time() - t0
    return dict(name=name, idx=idx, known=known, init=init, policy=policy,
                L=L, U=U, lb0=L0, ub0=U0, g0=g0, oracle_probes=oracle,
                probes=probes, lp=lp, cert_lp=cert_lp,
                init_lp=st['init_lp'], init_cert=st['init_cert'],
                unknown=unknown, steps=steps,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=partial_final,
                certified=bool(L == U and final_ok),
                audit=final_ok, proof_kind=(getattr(pi, 'kind', None)
                                            if final is not None else None),
                lns_trials=lns_trials, lns_ok=lns_ok,
                lns_checks=lns_checks, lns_t=round(lns_t, 4),
                t=round(dt, 4),
                ok=bool(L == U == known and final_ok and
                        partial_fail == 0 and partial_final))


def _root_fraction(inst, h, cache):
    """Number of fractional LP variables at horizon h (cached)."""
    key = ('frac', int(h))
    if key in cache.d:
        return cache.d[key]
    try:
        from sage import _elig_aware
        from sdecc import SDLP
        from po import heads_tails
        n = inst['n']
        est, q = heads_tails(inst, 0, [0] * n)
        lp = SDLP(inst, h, est, q, use_dom=True,
                  elig_aware=_elig_aware(inst))
        res = lp.solve()
        if res.status != 0:
            out = -1
        else:
            out = sum(1 for v in res.x if 1e-7 < v < 1 - 1e-7)
    except Exception:
        out = -1
    cache.d[key] = out
    return out


def lns_trial(inst, U, s, m, budget=12, kmax=14, tlim=0.2, stall=6,
              seed=0):
    """One destroy-repair burst; returns (best, sched, machine, stats)."""
    from lns import lns_drop
    nU, ns, nm, stats = lns_drop(
        inst, U, s, m, budget=budget, kmax=min(kmax, inst['n']),
        tlim=tlim, stall=stall, seed=seed)
    return nU, ns, nm, stats
