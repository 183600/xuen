"""v10.0 AEGIS-PACT: abstract-evidence-guarded invariant synthesis.

AEGIS keeps the v9.0 ICF state

    (L, U, s, m, pi)   with   pi : NO(L-1),  Cmax(s)=U,  L<=U,

and replaces the fixed inner branching heuristic of PACT by a synthesized
policy theta.  The trusted kernel is unchanged: any theta only changes the
order in which valid domain splits are tried.  A static analyzer provides

  * a sound box-aware window/energy pre-filter (cheap NO certificates),
  * the split-safety mask used by the policy,
  * the feature map consumed by the particle swarm.

The guarded oracle is

    Decide_theta(F,h) = static-close(F,h), if a static certificate exists,
                        else PACT(F,h,policy=theta),
                        else PACT(F,h,default)       [certified fallback].

Thus theta can never compromise soundness or completeness (the fallback is
the complete PACT search); it can only save or waste LP work.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v10c', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from po import heads_tails
from scale import _machine_subsets
from rdf import check_schedule
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h)


FEATURES = ('frac', 'mass', 'q', 'p', 'succ', 'pred', 'slack', 'width',
            'peak', 'entropy', 'spread')
SEARCH_FEATURES = ('p', 'q', 'spread', 'entropy', 'width', 'frac', 'mass')


# --------------------------------------------------------------- boxes
def root_box(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = [int(est[i]) for i in range(n)]
    hi = [int(h - q[i] - inst['p'][i]) for i in range(n)]
    return lo, hi


def box_forbid(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    F = set()
    for i in range(n):
        a = int(est[i])
        b = int(h - q[i] - inst['p'][i])
        for t in range(a, b + 1):
            if t < lo[i] or t > hi[i]:
                F.add((i, t))
    return frozenset(F)


def box_windows(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    a = [max(int(est[i]), int(lo[i])) for i in range(n)]
    b = [min(int(h - q[i] - inst['p'][i]), int(hi[i]))
         for i in range(n)]
    return a, b, est, q


def box_energy_cert(inst, h, lo, hi, max_subsets=64, max_intervals=20000):
    """Sound box-aware energy overload certificate.  None if not found."""
    n, p, m = inst['n'], inst['p'], inst['m']
    a, b, _, _ = box_windows(inst, h, lo, hi)
    for i in range(n):
        if a[i] > b[i]:
            return dict(kind='window', job=i, est=a[i], lst=b[i])
    pts = sorted(set(a + [b[i] + p[i] for i in range(n)]))
    pairs = [(0, h)] if 0 < h else []
    for ai, x in enumerate(pts):
        for y in pts[ai + 1:]:
            if (x, y) != (0, h):
                pairs.append((x, y))
            if len(pairs) >= max_intervals:
                break
        if len(pairs) >= max_intervals:
            break
    for M in _machine_subsets(inst, max_subsets):
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if not js:
            continue
        cap = len(M)
        for x, y in pairs:
            if y <= x:
                continue
            demand = 0
            for i in js:
                demand += max(0, p[i] - max(0, x - a[i])
                              - max(0, b[i] + p[i] - y))
            if demand > cap * (y - x):
                return dict(kind='energy', M=sorted(M), a=x, b=y,
                            jobs=js, demand=demand, cap=cap * (y - x))
    return None


def verify_box_cert(inst, h, lo, hi, cert):
    if cert is None:
        return False
    n, p, m = inst['n'], inst['p'], inst['m']
    a, b, _, _ = box_windows(inst, h, lo, hi)
    if cert.get('kind') == 'window':
        i = cert.get('job', -1)
        return (0 <= i < n and a[i] > b[i]
                and cert.get('est') == a[i]
                and cert.get('lst') == b[i])
    if cert.get('kind') == 'energy':
        M = set(cert.get('M', ()))
        x, y = cert.get('a'), cert.get('b')
        if not M or x is None or y is None or x >= y:
            return False
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if js != list(cert.get('jobs', ())):
            return False
        demand = 0
        for i in js:
            demand += max(0, p[i] - max(0, x - a[i])
                          - max(0, b[i] + p[i] - y))
        return (demand == cert.get('demand')
                and demand > len(M) * (y - x))
    return False


class BoxEnergyProof(Proof):
    """A box-aware window/energy NO proof at horizon h."""

    kind = 'box-energy'

    def __init__(self, inst, h, lo, hi, cert):
        super().__init__(inst, h)
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.cert = cert
        self.kind = 'box-' + str(cert.get('kind', 'energy')) \
            if cert else 'box-energy'
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            return verify_box_cert(self.inst, self.h, self.lo, self.hi,
                                    self.cert)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class StaticAnalyzer:
    """Cheap, sound abstract evidence for a box at a horizon."""

    def __init__(self, inst, max_subsets=64, max_intervals=20000):
        self.inst = inst
        self.max_subsets = max_subsets
        self.max_intervals = max_intervals
        self.est, self.q = heads_tails(inst, 0, [0] * inst['n'])

    def close(self, h, lo, hi):
        cert = box_energy_cert(self.inst, h, lo, hi,
                                self.max_subsets, self.max_intervals)
        if cert is None:
            return None
        return BoxEnergyProof(self.inst, h, lo, hi, cert)

    def lift(self, U, lo, hi, start, steps=4):
        """Largest h in [start, start+steps-1] with a static NO proof."""
        best_h, best_p = None, None
        for h in range(int(start), min(int(U) - 1, int(start) + steps - 1) + 1):
            p = self.close(h, lo, hi)
            if p is not None:
                best_h, best_p = h, p
        return best_h, best_p

    def candidate_jobs(self, lo, hi, min_width=1):
        out = []
        for i in range(self.inst['n']):
            if int(hi[i]) - int(lo[i]) >= min_width:
                out.append(i)
        return out

    def safe_mid(self, lo, hi, i, mid):
        """A split is safe iff both children are non-empty at this box."""
        mid = int(mid)
        left = int(lo[i]) <= mid
        right = mid + 1 <= int(hi[i])
        return left and right


# ---------------------------------------------------------- policy theta
def clip(x, a, b):
    return a if x < a else (b if x > b else x)


def policy_from_vector(x, names=SEARCH_FEATURES):
    weights = {name: float(x[k]) for k, name in enumerate(names)}
    split = clip(float(x[len(names)]), 0.15, 0.85)
    return dict(weights=weights, split=split)


def policy_to_vector(pol, names=SEARCH_FEATURES):
    w = pol.get('weights', {}) if pol else {}
    return [float(w.get(name, 0.0)) for name in names] + \
        [float(pol.get('split', 0.5)) if pol else 0.5]


# -------------------------------------------------------- guarded oracle
def decide_shielded(inst, h, theta=None, lo=None, hi=None,
                    nodecap=None, timelimit=None, forbid0=None,
                    use_static=True, fallback=True, fallback_policies=None):
    """Static pre-filter + theta-search + certified fallback.

    Returns a pact_decide-shaped dict with extra keys:
      static, fallback, first_nodes, first_lp, attempts, shield.
    """
    t0 = time.time()
    if lo is None or hi is None:
        lo, hi = root_box(inst, h)
    sa = StaticAnalyzer(inst)
    if use_static:
        p = sa.close(h, lo, hi)
        if p is not None:
            return dict(verdict=False, proof=p, schedule=None, machine=None,
                        nodes=0, leaves=0, depth=0, lp_solves=0,
                        cert_lp=0, unknown=False, holes=0, branch_jobs=[],
                        static=True, fallback=False, first_nodes=0,
                        first_lp=0, attempts=0, shield='static',
                        t=round(time.time() - t0, 5))

    pol = policy_from_vector(theta) if theta is not None else None
    r = pact_decide(inst, h, depthcap=None, nodecap=nodecap,
                    timelimit=timelimit, policy=pol, forbid0=forbid0)
    r['static'] = False
    r['fallback'] = False
    r['first_nodes'] = r.get('nodes', 0)
    r['first_lp'] = r.get('lp_solves', 0)
    r['attempts'] = 1
    r['shield'] = 'theta'
    if r['verdict'] is not None or not fallback:
        r['t'] = round(time.time() - t0, 5)
        return r

    if fallback_policies is None:
        fallback_policies = [{}, {'weights': {'spread': 1.0}}]
    first_nodes = r.get('nodes', 0)
    first_lp = r.get('lp_solves', 0)
    first_cert = r.get('cert_lp', 0)
    first_t = r.get('t', 0.0)
    for fp in fallback_policies:
        r2 = pact_decide(inst, h, depthcap=None, nodecap=None,
                         policy=fp, forbid0=forbid0)
        if r2['verdict'] is not None:
            r2['static'] = False
            r2['fallback'] = True
            r2['first_nodes'] = first_nodes
            r2['first_lp'] = first_lp
            r2['first_cert_lp'] = first_cert
            r2['first_t'] = first_t
            r2['attempts'] = 2
            r2['shield'] = 'fallback'
            r2['nodes'] = r2.get('nodes', 0) + first_nodes
            r2['lp_solves'] = r2.get('lp_solves', 0) + first_lp
            r2['cert_lp'] = r2.get('cert_lp', 0) + first_cert
            r2['t'] = round(float(r2.get('t', 0.0)) + first_t, 5)
            return r2
    r['fallback'] = False
    r['attempts'] = 1
    r['shield'] = 'failed'
    r['t'] = round(time.time() - t0, 5)
    return r


# ------------------------------------------------------------- outer ICF
def run_aegis(inst, known, name, idx, theta=None, policy='lower-first',
              max_probes=64, use_static=True, fallback=True,
              use_pact_init=True, nodecap=None, timelimit=None,
              theta_gap=2):
    """ICF outer loop with the shielded synthesized inner oracle."""
    t0 = time.time()
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return dict(name=name, idx=idx, known=known, theta=theta,
                    ok=False, error='no-initial-ub', t=0.0)

    L, U = int(lb), int(ub)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    lb_proof = co._ensure_lb_proof(L)
    if lb_proof is None:
        r = decide_shielded(inst, L - 1, theta, use_static=use_static,
                            fallback=fallback)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, theta=theta,
                    ok=False, error='no-lb-proof', t=0.0)

    probes = 0
    search_lp = 0
    search_nodes = 0
    cert_lp = 0
    static_closed = 0
    fallbacks = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U
    # The gate is decided once, from the initial bracket.  A hard NO proof
    # at U-1 remains hard even when the current gap has shrunk to 1, so a
    # current-gap gate would switch off the synthesized policy exactly at
    # the critical horizon.
    wide = (ub0 - lb0) >= int(theta_gap)

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        lo, hi = root_box(inst, h)
        # Static gate: the synthesized branching is only used on wide
        # brackets, where the NO proof has room to branch.  Narrow
        # brackets use the default PACT order, which is already cheap.
        th = theta if wide else None
        r = decide_shielded(inst, h, th, lo=lo, hi=hi,
                            use_static=use_static, fallback=fallback,
                            nodecap=nodecap, timelimit=timelimit)
        probes += 1
        first = False
        search_lp += r.get('lp_solves', 0)
        search_nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        static_closed += int(bool(r.get('static')))
        fallbacks += int(bool(r.get('fallback')))

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              static=bool(r.get('static')),
                              fallback=bool(r.get('fallback')),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              static=bool(r.get('static')),
                              fallback=bool(r.get('fallback')),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              static=bool(r.get('static')),
                              fallback=bool(r.get('fallback')),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, theta=theta, outer_policy=policy,
        theta_gap=theta_gap,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=search_lp, pact_nodes=search_nodes,
        pact_cert_lp=cert_lp, pin_lp=getattr(co, 'pin_lp', 0),
        total_lp=search_lp + cert_lp + getattr(co, 'pin_lp', 0),
        static_closed=static_closed, fallbacks=fallbacks,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )


# --------------------------------------------------------- case helpers
def load_gap_cases(path='exp/v10c/gap_cases.json'):
    import json
    return json.load(open(path))


def eval_policy(theta, cases, names=SEARCH_FEATURES, cap=700,
                timelimit=8.0, fallback=True, use_static=True):
    """Evaluate theta at h=OPT-1 on a list of gap cases."""
    rows = []
    for d in cases:
        inst = d['inst']
        h = int(d.get('opt', d.get('ub0'))) - 1
        lo, hi = root_box(inst, h)
        t = time.time()
        r = decide_shielded(inst, h, theta, lo=lo, hi=hi,
                            nodecap=cap, timelimit=timelimit,
                            use_static=use_static, fallback=fallback)
        proof = r.get('proof')
        audit = bool(proof is not None and proof.audit_rdf())
        rows.append(dict(
            case=d.get('case'), kind=d.get('kind'), src=d.get('src'),
            idx=d.get('idx'), h=h, opt=d.get('opt'),
            verdict=r.get('verdict'), audit=audit,
            nodes=r.get('nodes', 0), lp=r.get('lp_solves', 0),
            cert=r.get('cert_lp', 0), static=bool(r.get('static')),
            fallback=bool(r.get('fallback')),
            attempts=r.get('attempts', 0),
            wall=round(time.time() - t, 4),
            ok=bool(r.get('verdict') is False and audit)))
    return rows


def summarize(rows):
    return dict(
        n=len(rows),
        ok=sum(r['ok'] for r in rows),
        fails=[r['case'] for r in rows if not r['ok']],
        nodes=sum(r['nodes'] for r in rows),
        lp=sum(r['lp'] for r in rows),
        cert=sum(r['cert'] for r in rows),
        total_lp=sum(r['lp'] + r['cert'] for r in rows),
        static=sum(r['static'] for r in rows),
        fallback=sum(r['fallback'] for r in rows),
        wall=round(sum(r['wall'] for r in rows), 3),
    )


# ---------------------------------------------------- flat cover certificates
def _allowed_times(inst, h, i):
    from sage import _domain
    lo, hi = _domain(inst, h, i)
    return list(range(lo, hi + 1))


class CoverCertificate:
    """A flat NO(h) cover: boxes need only cover, not form a tree.

    Leaves are (F, proof) with proof : NO(h_leaf | F) and h_leaf >= h.
    Overlap is allowed.  This is strictly more permissive than the v9.0
    FrontierProof tree: every tree is a cover, but covers tolerate empty
    children, pruning, and merging without rebuilding a partition tree.
    """

    kind = 'cover'

    def __init__(self, inst, target, leaves, schedule=None, machine=None,
                 U=None):
        self.inst = inst
        self.target = int(target)
        self.leaves = list(leaves)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.U = U

    def _cover_ok(self):
        n = self.inst['n']
        for i in range(n):
            for t in _allowed_times(self.inst, self.target, i):
                if not any((i, t) not in set(F) for F, _ in self.leaves):
                    return False
        return True

    def audit_rdf(self):
        try:
            if not self.leaves:
                return False
            for F, p in self.leaves:
                if p is None or p.h < self.target:
                    return False
                if not p.audit_rdf():
                    return False
                if not set(_proof_forbid(p)) <= set(F):
                    return False
            if not self._cover_ok():
                return False
            if self.U is not None:
                if self.schedule is None or self.machine is None:
                    return False
                if cmax(self.inst, self.schedule) != self.U:
                    return False
                if not check_schedule(self.inst, self.U, self.schedule,
                                      self.machine):
                    return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def run_cover_frontier(inst, h, theta=None, leaf_cap=150, max_leaves=32,
                       use_static=True):
    """Bounded-oracle frontier: split only when a leaf exceeds leaf_cap.

    Returns a dict; if every leaf closes, `cover` is an audited NO(h)
    certificate.  If a YES schedule is found, `schedule` is returned.
    """
    from icf import _proof_forbid
    n = inst['n']
    lo, hi = root_box(inst, h)
    F0 = box_forbid(inst, h, lo, hi)
    open_leaves = [(F0, lo, hi)]
    closed = []
    total_nodes = total_lp = total_cert = 0
    peak = 1
    splits = 0
    schedule = machine = None
    yes = False
    t0 = time.time()

    while open_leaves and len(open_leaves) + len(closed) <= max_leaves:
        F, lo, hi = open_leaves.pop()
        r = decide_shielded(inst, h, theta, lo=lo, hi=hi,
                            nodecap=leaf_cap, timelimit=None,
                            use_static=use_static, fallback=False)
        total_nodes += r.get('nodes', 0)
        total_lp += r.get('lp_solves', 0)
        total_cert += r.get('cert_lp', 0)
        if r['verdict'] is False:
            closed.append((F, r['proof']))
            continue
        if r['verdict'] is True:
            schedule, machine = r['schedule'], r['machine']
            yes = True
            break
        # UNKNOWN: use the oracle's own root split as the refinement.
        bj = r.get('branch_jobs', [])
        if bj:
            i, mid, _ = bj[0]
        else:
            i = max(range(n), key=lambda j: int(hi[j]) - int(lo[j]))
            mid = (int(lo[i]) + int(hi[i])) // 2
        if not (int(lo[i]) <= int(mid) < int(hi[i])):
            i = max(range(n), key=lambda j: int(hi[j]) - int(lo[j]))
            mid = (int(lo[i]) + int(hi[i])) // 2
        if not (int(lo[i]) <= int(mid) < int(hi[i])):
            # Cannot split; leave it open.
            open_leaves.append((F, lo, hi))
            break
        splits += 1
        loL = list(lo)
        hiL = list(hi)
        hiL[i] = int(mid)
        loR = list(lo)
        hiR = list(hi)
        loR[i] = int(mid) + 1
        for lo2, hi2 in ((loL, hiL), (loR, hiR)):
            if all(int(lo2[j]) <= int(hi2[j]) for j in range(n)):
                F2 = box_forbid(inst, h, lo2, hi2)
                if not any(F2 == F3 for F3, _, _ in open_leaves):
                    open_leaves.append((F2, lo2, hi2))
        peak = max(peak, len(open_leaves) + len(closed))

    target = int(h)
    if not open_leaves:
        cover = CoverCertificate(inst, target,
                                 [(F, p) for F, p in closed],
                                 schedule=schedule, machine=machine,
                                 U=(cmax(inst, schedule) if yes else None))
        ok = bool(cover.audit_rdf())
    else:
        cover = None
        ok = False
    return dict(
        h=int(h), ok=ok, yes=bool(yes), open=len(open_leaves),
        closed=len(closed), peak=peak, splits=splits,
        nodes=total_nodes, lp=total_lp, cert_lp=total_cert,
        total_lp=total_lp + total_cert, cover=cover,
        schedule=schedule, machine=machine,
        t=round(time.time() - t0, 4))
