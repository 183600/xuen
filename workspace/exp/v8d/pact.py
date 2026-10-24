"""v8.2 PACT-ALC: proof-carrying adaptive certificate tightening.

PACT builds on the v8.1 CRISP bracket and adds three layers:

  * proof-carrying bracket: a verified NO proof at LB-1 (analytic bound,
    energy, or window) is a first-class object, so an exact preprocessing
    bracket needs no oracle call at OPT-1;
  * randomized UB racing: K i.i.d. priority orders are sampled from a
    fixed distribution and the best replayed schedule is kept; the
    best-of-K bound gives a probabilistic statement about the remaining
    chance that a fresh order improves UB;
  * a lexicographic termination potential Phi = (W, U), where W = UB-LB
    and U is the remaining UNKNOWN budget.  Every decisive answer
    decreases W; every UNKNOWN decreases U; hence Phi is well-founded.

The fixed-h oracle is unchanged.  Every accepted schedule still passes
check_schedule; every accepted NO proof still replays through
verify_prep or replay_lb.
"""
import sys
import random
import math

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import (CRISP, base_bounds, order_portfolio,
                  base_corpus, pert_corpus, stress_corpus)
from ccb import ProofCarrying, PrepProof, BoundProof
from scale import energy_cert, windows, verify_prep
from cab import _greedy_rank
from rdf import check_schedule


# ------------------------------------------------------------ random orders
def sample_order(inst, est, q, ub_ref, rng):
    """One draw from the fixed UB-racing distribution.

    The distribution is deliberately broad: tail-heavy, head-heavy, convex
    combinations with latest starts, Gaussian jitter around est, and a
    uniform random priority.  The point is not that one mode is good; it is
    that the mixture has a non-zero chance of escaping the four
    deterministic orders.
    """
    n = inst['n']
    latest = [ub_ref - q[i] - inst['p'][i] for i in range(n)]
    mode = rng.randrange(4)
    if mode == 0:
        lam = rng.uniform(-1.5, 1.5)
        return {i: est[i] - lam * q[i] + rng.random() * 1e-6
                for i in range(n)}
    if mode == 1:
        w = [rng.random() for _ in range(3)]
        s = sum(w) or 1.0
        w = [x / s for x in w]
        return {i: w[0] * est[i] + w[1] * latest[i]
                - w[2] * q[i] + rng.random() * 1e-6
                for i in range(n)}
    if mode == 2:
        span = max(1.0, ub_ref - max(est))
        sig = rng.uniform(0.05, 0.60) * span
        return {i: est[i] + rng.gauss(0.0, sig) for i in range(n)}
    return {i: rng.random() for i in range(n)}


def random_ub_drop(inst, ub, sched, mach, est, q, K, seed,
                   record_curve=False):
    """Best-of-K randomized greedy portfolio.

    Returns (ub, sched, mach, drops, curve).  ``curve[k-1]`` is the best
    makespan after the first k random draws (plus the deterministic
    warm start).  The curve is monotone non-increasing.
    """
    if K <= 0:
        return ub, sched, mach, 0, ([] if record_curve else None)
    rng = random.Random(seed)
    ub_ref = ub
    drops = 0
    curve = [] if record_curve else None
    for _ in range(K):
        rank = sample_order(inst, est, q, ub_ref, rng)
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub \
                and check_schedule(inst, g[2], g[0], g[1]):
            ub, sched, mach = g[2], g[0], g[1]
            drops += 1
        if record_curve:
            curve.append(ub)
    return ub, sched, mach, drops, curve


def lift_certs(inst, lb0, ub0, energy_max_subsets=64,
               energy_max_intervals=20000, verify=True):
    """All replayable NO certificates on the contiguous prefix [lb0, h).

    The energy/window test at h does not depend on UB, so one scan gives
    the certificates for every possible bracket upper bound.  Returns
    (certs, lb_max, cert_bad), where lb_max is the first h with no
    certificate (or ub0 if the whole prefix is certified).
    """
    h = lb0
    certs = []
    cert_bad = 0
    while h < ub0:
        cert = energy_cert(inst, h, energy_max_subsets,
                           energy_max_intervals)
        if cert is None:
            ee, ll, _ = windows(inst, h)
            bad = [i for i in range(inst['n']) if ee[i] > ll[i]]
            if not bad:
                break
            i = bad[0]
            cert = dict(kind='window', job=i, est=ee[i], lst=ll[i])
        if verify and not verify_prep(inst, h, cert):
            cert_bad += 1
            break
        certs.append((h, cert))
        h += 1
    return certs, h, cert_bad


def pact_bounds(inst, K=32, seed=20261024, energy_max_subsets=64,
                energy_max_intervals=20000, verify=True,
                record_curve=False):
    """CRISP preprocessing plus randomized UB racing.

    The returned bracket is the v8.1 bracket, except that the upper bound
    is the minimum over the four deterministic orders and K i.i.d. random
    orders.  The lower-bound certificates are stored as first-class proofs,
    not just as a number.
    """
    lb0, ub0, starts, machs, est, q = base_bounds(inst)
    if ub0 is None:
        return dict(ok=False, lb0=lb0, ub0=None)
    lb, ub = lb0, ub0
    sched, mach = starts, machs

    drops = 0
    for name, rank in order_portfolio(inst, est, q, ub):
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub \
                and check_schedule(inst, g[2], g[0], g[1]):
            ub, sched, mach = g[2], g[0], g[1]
            drops += 1

    ub, sched, mach, rand_drops, curve = random_ub_drop(
        inst, ub, sched, mach, est, q, K, seed,
        record_curve=record_curve)

    certs_all, lb_max, cert_bad = lift_certs(
        inst, lb0, ub0, energy_max_subsets, energy_max_intervals, verify)
    lb = min(ub, lb_max)
    certs = [(h, c) for h, c in certs_all if h < lb]

    return dict(ok=True, lb0=lb0, ub0=ub0, lb=lb, ub=ub,
                schedule=sched, machine=mach, lifts=len(certs),
                drops=drops, rand_drops=rand_drops, K=K,
                certs=certs, certs_all=certs_all, lb_max=lb_max,
                cert_bad=cert_bad, curve=curve,
                ratio0=ub0 / lb0 if lb0 > 0 else None,
                ratio=ub / lb if lb > 0 else None)


def simulate_bracket(lb, ub, opt, prep_proofs=(), bound_h=None):
    """Query count of the inherited binary search with a perfect oracle.

    This is the v8.1 `simulate_queries` plus the proof-carrying final
    lookup: if OPT-1 already has a replayable proof, no final oracle call
    is made.  It is used only for the offline K-ablation; the online
    algorithm always uses the real oracle.
    """
    q = 0
    no = set(prep_proofs)
    if bound_h is not None:
        no.add(bound_h)
    while lb < ub:
        h = (lb + ub) // 2
        q += 1
        if opt <= h:
            ub = h
        else:
            lb = h + 1
            no.add(h)
    if lb == ub and lb == opt and (opt - 1) not in no:
        q += 1
    return q


# --------------------------------------------------------------- algorithm
class PACT(ProofCarrying, CRISP):
    """Proof-carrying bracket + randomized UB racing + CHD oracle."""

    def __init__(self, inst, K=32, seed=20261024, unknown_budget=64,
                 **kw):
        self.K = K
        self.seed = seed
        self.unknown_budget = unknown_budget
        super().__init__(inst, **kw)

    def _record(self, h, v, st):
        """Record the post-decision bounds as well as the raw trace.

        CABOpt._record is called before a YES updates self.opt, so the raw
        trace's `ub` is the pre-decision value.  The potential proof needs
        the post-decision value; for a YES this is min(self.opt, cmax) and
        for a NO it is already self.lb.
        """
        super()._record(h, v, st)
        lb_after = self.lb
        ub_after = self.opt
        if v is True and st.get('schedule') is not None:
            cmax = max(st['schedule'][i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            ub_after = min(ub_after, cmax)
        elif v is False:
            lb_after = max(lb_after, h + 1)
        t = self.trace[-1]
        t['lb_after'] = lb_after
        t['ub_after'] = ub_after
        t['w_after'] = (None if ub_after is None or lb_after is None
                        else ub_after - lb_after)

    def optimize(self):
        """Search loop with an explicit lexicographic termination potential.

        Phi = (W, U, F).  A decisive answer decreases W.  An UNKNOWN
        decreases U.  The final proof at OPT-1 decreases F (and is the
        only step allowed to leave W unchanged).  The loop is therefore
        well-founded even if the oracle returns UNKNOWN forever: the
        UNKNOWN budget is finite and the query budget is finite.
        """
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        while self.lb < self.opt and self.queries < self.max_queries:
            w = self.opt - self.lb
            h = (self.opt - 1 if (self.probe_ub1 and w <= self.probe_width)
                 else (self.lb + self.opt) // 2)
            p = self._cached_no(h)
            if p is not None:
                self.cache_hits += 1
                self.lb = max(self.lb, h + 1)
                self._record(h, False, p._stats('cache'))
                continue
            v, st, rdf = self._decide(h)
            self.queries += 1
            self._absorb(st)
            self._record(h, v, st)
            if v is True:
                cmax = max(rdf.schedule[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                if cmax < self.opt:
                    self.opt = cmax
                    self.schedule = list(rdf.schedule)
                    self.machine = list(rdf.machine)
            elif v is False:
                self.lb = max(self.lb, h + 1)
                self.no_states[h] = rdf
                self.lb_proof = rdf
            else:
                self.unknown += 1
                self._recover_unknown(h)
        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified and (self.opt - 1) not in self.no_states:
            p = self._cached_no(self.opt - 1)
            if p is not None:
                self.cache_hits += 1
                self.no_states[self.opt - 1] = p
            else:
                while self.queries < self.max_queries:
                    v, st, rdf = self._decide(self.opt - 1)
                    self.queries += 1
                    self._absorb(st)
                    self._record(self.opt - 1, v, st)
                    if v is False:
                        self.no_states[self.opt - 1] = rdf
                        self.lb_proof = rdf
                        break
                    if v is True:
                        self.certified = False
                        break
                    self.unknown += 1
                    if self.unknown >= self.unknown_budget:
                        self.certified = False
                        break
                if (self.opt - 1) not in self.no_states:
                    self.certified = False
        if self.certified:
            self.lb_proof = self.no_states.get(self.opt - 1)
            if self.lb_proof is None:
                self.certified = False
        return self._result()

    def initial_bounds(self):
        b = pact_bounds(self.inst, K=self.K, seed=self.seed)
        self.chip = b
        self.prep_proofs = {}
        self.cache_hits = 0
        self.cache_kinds = {}
        self.bound_proofs = 0
        self.energy_proofs = 0
        self.window_proofs = 0
        if not b.get('ok', False) or b.get('ub') is None:
            return b['lb0'], None, None, None
        for h, cert in b.get('certs', []):
            p = PrepProof(self.inst, h, cert)
            if p.audit_rdf():
                self.prep_proofs[h] = p
                if p.kind == 'energy':
                    self.energy_proofs += 1
                elif p.kind == 'window':
                    self.window_proofs += 1
        bp = BoundProof(self.inst, b['lb0'] - 1)
        if bp.audit_rdf():
            self.prep_proofs.setdefault(b['lb0'] - 1, bp)
            self.bound_proofs = 1
        if b['lb'] == b['ub']:
            p = self.prep_proofs.get(b['ub'] - 1)
            if p is not None and p.audit_rdf():
                self.no_states[b['ub'] - 1] = p
                self.lb_proof = p
        return b['lb'], b['ub'], b['schedule'], b['machine']


# ------------------------------------------------------------- termination
def potential_trace(trace, final_opt=None):
    """Replay a trace and check the lexicographic termination potential.

    Phi = (W, U, F):
      * a YES or NO decision must strictly decrease W = UB-LB;
      * an UNKNOWN decision must consume one unit of U;
      * the final proof at OPT-1, if it is not cached, is the only step
        allowed to leave W unchanged; it consumes F.

    The raw CABOpt trace stores `ub` before a YES updates self.opt, so we
    prefer the `lb_after`/`ub_after` fields written by PACT._record.
    """
    prev_lb = None
    prev_ub = None
    for pos, t in enumerate(trace):
        lb = t.get('lb_after', t['lb'])
        ub = t.get('ub_after', t['ub'])
        v = t['v']
        if prev_lb is not None:
            if v is True:
                if not (ub < prev_ub):
                    return False
            elif v is False:
                if not (lb > prev_lb):
                    # The only exception is the terminal proof at OPT-1,
                    # which may be a cache hit with LB already at OPT.
                    terminal = (pos == len(trace) - 1
                                and final_opt is not None
                                and t['h'] == final_opt - 1
                                and lb == ub == final_opt)
                    if not terminal:
                        return False
            # v is None: W may be unchanged; U is charged by the caller
        prev_lb, prev_ub = lb, ub
    return True


def best_of_k_tail(p, K):
    """P(no improvement in K i.i.d. draws) when one draw improves w.p. p."""
    return (1.0 - p) ** K


def improvement_upper_bound(K, delta=0.05):
    """One-sided Clopper-Pearson upper bound for 0 successes in K trials."""
    if K <= 0:
        return 1.0
    return 1.0 - delta ** (1.0 / K)
