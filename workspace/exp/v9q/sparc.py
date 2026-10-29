"""v9.5 SPARC: singleton probing with replayable reduced certificates.

SPARC is a reduction layer on top of PACT-ALC.  At a fixed horizon h it
first solves the root SDLP.  If the root LP is fractional, it probes
start-time pins: for a job i and a time t it restricts i to start at t
(any eligible machine) and solves the SDLP again.  An infeasible pin is a
certified statement "s_i != t"; the time is removed.  The residual
instance is exactly equivalent, so PACT can decide it.  A NO proof is a
ProbeProof: the set of removed times plus a PACT NO proof of the residual
instance.  The checker either replays the pin LPs (lazy) or verifies
stored Farkas certificates (eager); it never trusts the generator.

The quantum layer is deliberately kept out of the implementation: the
artifact treats amplitude amplification over the residual leaves as a
query-complexity bound, not as a runtime claim.
"""
import sys
import time
import math

sys.path[:0] = ['exp/v9q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import BranchProof
from sdecc import SDLP
from cert import integer_certificate, verify
from pact import pact_decide
from po import heads_tails


# --------------------------------------------------------------- helpers
def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


def _times(inst, h, i, est=None, q=None):
    if est is None or q is None:
        est, q = heads_tails(inst, 0, [0] * inst['n'])
    lo = est[i]
    hi = h - q[i] - inst['p'][i]
    return list(range(lo, hi + 1))


def _build_lp(inst, h, est=None, q=None):
    if est is None or q is None:
        est, q = heads_tails(inst, 0, [0] * inst['n'])
    return SDLP(inst, h, est, q, use_dom=True,
                elig_aware=_elig_aware(inst))


def _pin_bounds(lp, i, t):
    """Bounds that fix job i at time t, leaving the machine free."""
    b = [(0, 1)] * lp.N
    for c, key in enumerate(lp.cols):
        if key[0] == i:
            b[c] = (0, 0) if key[-1] != t else (0, 1)
    return b


def _pin_feasible(inst, h, i, t):
    """Lazy replay: is the SDLP with s_i = t feasible?"""
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    if not (est[i] <= t <= h - q[i] - inst['p'][i]):
        return False
    lp = _build_lp(inst, h, est, q)
    res = lp.solve(_pin_bounds(lp, i, t))
    return res.status != 2


def probe_pins(inst, h, budget=None, lp=None, root_res=None,
               policy='index'):
    """Return (removed, stats).  A removed (i,t) is certified infeasible.

    Only pins with LP status 2 are removed; a numeric failure or a
    feasible pin is kept.  The search is exact: the residual feasible set
    is unchanged.
    """
    t0 = time.time()
    n, m = inst['n'], inst['m']
    est, q = heads_tails(inst, 0, [0] * n)
    if lp is None:
        lp = _build_lp(inst, h, est, q)
    removed = []
    calls = 0
    cand_jobs = list(range(n))
    if policy == 'fractional' and root_res is not None and \
            root_res.status == 0:
        mass = {}
        for c, key in enumerate(lp.cols):
            i = key[0]
            z = root_res.x[c]
            if 1e-7 < z < 1 - 1e-7:
                mass[i] = mass.get(i, 0.0) + z
        cand_jobs.sort(key=lambda i: (-mass.get(i, 0.0), i))
    for i in cand_jobs:
        times = _times(inst, h, i, est, q)
        if len(times) <= 1:
            continue
        if policy == 'fractional' and root_res is not None and \
                root_res.status == 0:
            m_i = {}
            for c, key in enumerate(lp.cols):
                if key[0] == i:
                    m_i[key[-1]] = m_i.get(key[-1], 0.0) + root_res.x[c]
            times = sorted(times, key=lambda t: m_i.get(t, 0.0))
        for t in times:
            if budget is not None and len(removed) >= budget:
                break
            res = lp.solve(_pin_bounds(lp, i, t))
            calls += 1
            if res.status == 2:
                removed.append((i, t))
        if budget is not None and len(removed) >= budget:
            break
    stats = dict(calls=calls, removed=len(removed),
                 t=round(time.time() - t0, 5), policy=policy)
    return removed, stats


# ----------------------------------------------------------- probe proof
class ProbeProof(Proof):
    """NO(h): removed times + a PACT proof of the residual instance.

    The removed set is a cover of the original domains: every feasible
    schedule of I must use a removed time (contradiction) or lie in the
    residual (contradiction).  Audit checks both halves.  In lazy mode it
    re-solves every pin LP; in eager mode it verifies stored Farkas
    certificates.  It never trusts the generator's verdict.
    """
    kind = 'probe'

    def __init__(self, inst, h, removed, residual, pin_certs=None):
        super().__init__(inst, h)
        self.removed = tuple(sorted((int(i), int(t)) for i, t in removed))
        self.residual = residual
        self.pin_certs = None if pin_certs is None else dict(pin_certs)

    def audit_rdf(self):
        try:
            if self.residual is None:
                return False
            if self.residual.h != self.h:
                return False
            if set(getattr(self.residual, 'forbid0', ())) != set(self.removed):
                return False
            if not self.residual.audit_rdf():
                return False
            est, q = heads_tails(self.inst, 0, [0] * self.inst['n'])
            seen = set()
            for i, t in self.removed:
                if (i, t) in seen:
                    return False
                seen.add((i, t))
                if not (0 <= i < self.inst['n']):
                    return False
                lo = est[i]
                hi = self.h - q[i] - self.inst['p'][i]
                if not (lo <= t <= hi):
                    return False
                if self.pin_certs is None:
                    if _pin_feasible(self.inst, self.h, i, t):
                        return False
                else:
                    cert = self.pin_certs.get((i, t))
                    if cert is None:
                        return False
                    F = frozenset((i, u) for u in range(lo, hi + 1)
                                  if u != t)
                    if not verify(self.inst, self.h, cert, forbid=F):
                        return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# -------------------------------------------------------------- decision
def sparc_decide(inst, h, probe_budget=16, policy='index',
                 cert_mode='lazy', quantum_stats=False):
    """Three-valued fixed-h decision: NO(proof), YES(schedule), UNKNOWN.

    Fast path: root LP infeasible/integral.  Fractional: probe up to
    ``probe_budget`` infeasible pins, then ask PACT for the residual.
    """
    t0 = time.time()
    n, m = inst['n'], inst['m']
    est, q = heads_tails(inst, 0, [0] * n)
    lp = _build_lp(inst, h, est, q)
    root_res = lp.solve()
    stats = dict(root_status=root_res.status, probe_calls=0,
                 removed=0, pact_lp=0, pact_cert=0, pact_nodes=0,
                 t=0.0, quantum_leaves=None, quantum_sqrt=None)
    if root_res.status == 2:
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        r['probe'] = stats
        return r
    removed = []
    if root_res.status == 0 and probe_budget:
        # Only probe if the root is fractional; an integral root is YES.
        frac = any(1e-7 < root_res.x[c] < 1 - 1e-7
                   for c in range(lp.N))
        if frac:
            removed, ps = probe_pins(inst, h, budget=probe_budget,
                                     lp=lp, root_res=root_res,
                                     policy=policy)
            stats.update(probe_calls=ps['calls'], removed=len(removed),
                         probe_t=ps['t'])
    r = pact_decide(inst, h, depthcap=None, nodecap=None,
                    forbid0=removed if removed else None)
    stats['pact_lp'] = r.get('lp_solves', 0)
    stats['pact_cert'] = r.get('cert_lp', 0)
    stats['pact_nodes'] = r.get('nodes', 0)
    r['probe'] = stats
    if r['verdict'] is False and removed:
        proof = ProbeProof(inst, h, removed, r['proof'])
        if proof.audit_rdf():
            r['proof'] = proof
            r['reduced'] = True
        else:
            # Never expose a BranchProof whose root forbid set is nonempty:
            # it proves NO(h | removed), not NO(h).  Fall back to a complete
            # search on the original instance.
            stats['probe_audit_fail'] = True
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            stats['pact_lp'] = r.get('lp_solves', 0)
            stats['pact_cert'] = r.get('cert_lp', 0)
            stats['pact_nodes'] = r.get('nodes', 0)
            r['probe'] = stats
            r['reduced'] = False
    stats['t'] = round(time.time() - t0, 5)
    return r


def sparc_decide_demand(inst, h, node_budget=16, probe_budget=16,
                        policy='index', cert_mode='lazy'):
    """Demand-driven SPARC: fast PACT first, probe only on a hole.

    The first PACT call is capped at ``node_budget`` nodes.  If it closes
    the probe (YES or NO), return it.  If it hits the cap, pay the probe
    budget and retry on the reduced instance.  This keeps the fast path
    identical to PACT-C on shallow instances and invokes the reduction
    only when the proof tree threatens to grow.
    """
    t0 = time.time()
    r0 = pact_decide(inst, h, depthcap=None, nodecap=node_budget)
    if r0['verdict'] is not None:
        r0['probe'] = dict(mode='fast', node_budget=node_budget,
                           probe_calls=0, removed=0,
                           t=round(time.time() - t0, 5))
        return r0
    r = sparc_decide(inst, h, probe_budget=probe_budget, policy=policy,
                     cert_mode=cert_mode)
    r.setdefault('probe', {})
    r['probe']['mode'] = 'demand'
    r['probe']['node_budget'] = node_budget
    r['probe']['t'] = round(time.time() - t0, 5)
    return r


def run_sparc(inst, known, name, idx, **kw):
    t0 = time.time()
    r = sparc_decide(inst, known - 1, **kw)
    h = known - 1
    dt = time.time() - t0
    out = dict(name=name, idx=idx, known=known, h=h,
               verdict=r['verdict'], t=round(dt, 5),
               nodes=r.get('nodes', 0), depth=r.get('depth', 0),
               lp=r.get('lp_solves', 0), cert=r.get('cert_lp', 0),
               proof_kind=getattr(r.get('proof'), 'kind', None),
               reduced=r.get('reduced', False),
               probe=r.get('probe', {}))
    return out


# --------------------------------------------------------------- PACT shell
class SPARC:
    """Compatibility shell: instantiate with the PACT class at runtime.

    Kept as a factory to avoid importing PACT's SAGE base twice in the
    benchmark process.
    """
    pass


def make_sparc(PACT):
    class _SPARC(PACT):
        def __init__(self, inst, probe_budget=16, probe_policy='index',
                     demand_budget=None, **kw):
            kw.setdefault('pact_mode', 'complete')
            kw.setdefault('use_ga', False)
            super().__init__(inst, **kw)
            self.probe_budget = probe_budget
            self.probe_policy = probe_policy
            self.demand_budget = demand_budget
            self.probe_lp = 0
            self.probe_calls = 0
            self.probe_removed = 0
            self.probe_steps = 0
            self.stats.update(probe_calls=0, probe_removed=0,
                              probe_steps=0, probe_lp=0)

        def _probe(self, h):
            # Aggressive probing at the lower bracket endpoint; lazy at
            # midpoints.  The endpoint probe is the NO-likely one.
            B = self.probe_budget if h == self.lb else 0
            if self.demand_budget is not None and B:
                r = sparc_decide_demand(
                    self.inst, h, node_budget=self.demand_budget,
                    probe_budget=B, policy=self.probe_policy)
            else:
                r = sparc_decide(self.inst, h, probe_budget=B,
                                 policy=self.probe_policy)
            ps = r.get('probe', {})
            self.probe_calls += ps.get('probe_calls', 0)
            self.probe_removed += ps.get('removed', 0)
            self.probe_lp += ps.get('probe_calls', 0)
            self.pact_lp += r.get('lp_solves', 0)
            self.pact_cert_lp += r.get('cert_lp', 0)
            self.pact_nodes += r.get('nodes', 0)
            self.stats['probe_calls'] += ps.get('probe_calls', 0)
            self.stats['probe_removed'] += ps.get('removed', 0)
            self.stats['probe_lp'] += ps.get('probe_calls', 0)
            if r['verdict'] is False:
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='sparc',
                                       probe=ps.get('removed', 0)))
                if ps.get('removed', 0):
                    self.probe_steps += 1
                    self.stats['probe_steps'] += 1
                return False, r['proof']
            if r['verdict'] is True:
                self.pact_yes += 1
                self.stats['pact_yes'] += 1
                s, m = r['schedule'], r['machine']
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.steps.append(dict(h=h, v=True, schedule=s,
                                       machine=m, cmax=cmax,
                                       engine='sparc',
                                       probe=ps.get('removed', 0)))
                return True, (s, m, cmax)
            self.pact_unknown += 1
            self.stats['pact_unknown'] += 1
            self.steps.append(dict(h=h, v=None, engine='sparc'))
            return None, None

        def _result(self):
            r = super()._result()
            r['probe_lp'] = self.probe_lp
            r['probe_calls'] = self.probe_calls
            r['probe_removed'] = self.probe_removed
            r['probe_steps'] = self.probe_steps
            return r

    return _SPARC
