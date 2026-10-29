"""v8.2 EAGER-ALC: Evolutionary Approximation-Guaranteed Resource allocation.

EAGER keeps the v8.1 CRISP bracket and adds three things:

  * an evolutionary incumbent generator over priority permutations;
  * promotion of replayable preprocessing NO certificates (window /
    energy) to first-class final proofs;
  * a width-aware oracle allocator: certify the incumbent from the top
    (probe UB-1) for a bounded number of calls, then bisect.

Every accepted schedule passes check_schedule.  Every lower-bound lift
passes verify_prep.  The evolutionary part is only an incumbent
generator: the approximation guarantee always comes from the bracket
LB <= OPT <= UB, never from the population.
"""
import sys
import math
import random
import time

sys.path[:0] = ['exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a',
                'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60',
                'exp/v13']

from cab import CABOpt, _greedy_rank
from chd import CHD
from scale import energy_cert, windows, verify_prep
from po import heads_tails
from rdf import check_schedule

from chip import base_bounds, order_portfolio


# --------------------------------------------------------------- certificates
class BaseProof:
    """Analytic lower-bound witness promoted to a final-proof object.

    At h = LB0-1 the critical-path or eligibility-load argument already
    proves NO.  Replaying that argument is cheaper than any oracle call.
    """

    def __init__(self, inst, h, lb0):
        self.inst = inst
        self.h = h
        self.lb0 = lb0
        self._ok = None

    def audit_rdf(self):
        if self._ok is None:
            n, m, p = self.inst['n'], self.inst['m'], self.inst['p']
            est, q = heads_tails(self.inst, 0, [0] * n)
            lb = max(est[i] + p[i] + q[i] for i in range(n))
            for mask in range(1, 1 << m):
                jobs = [i for i in range(n)
                        if all((mask >> k) & 1 for k in self.inst['elig'][i])]
                cnt = bin(mask).count('1')
                lb = max(lb, (sum(p[i] for i in jobs) + cnt - 1) // cnt)
            self._ok = (lb > self.h)
        return bool(self._ok)

    def proof_complete(self):
        return self.audit_rdf()

    def stats(self):
        return dict(why='base-proof', lp_solves=0, nodes=0,
                    yes_nodes=0, mc_evals=0, free_cert=True,
                    kind='base')


class PrepProof:
    """A window/energy NO certificate promoted to a final-proof object."""

    def __init__(self, inst, h, cert):
        self.inst = inst
        self.h = h
        self.cert = cert
        self.kind = cert.get('kind')
        self._ok = None
        self.verify_prep = verify_prep

    def audit_rdf(self):
        if self._ok is None:
            self._ok = verify_prep(self.inst, self.h, self.cert)
        return bool(self._ok)

    def proof_complete(self):
        return self.audit_rdf()

    def _stats(self, why):
        return dict(why=why, lp_solves=0, nodes=0, yes_nodes=0,
                    mc_evals=0, free_cert=True, kind=self.kind)

    def stats(self):
        return self._stats('prep-cert')


def lift_bounds(inst, lb, ub, max_subsets=64, max_intervals=20000):
    """Raise lb by replayable window/energy NO certificates."""
    certs = []
    bad = 0
    h = lb
    while h < ub:
        cert = energy_cert(inst, h, max_subsets, max_intervals)
        if cert is None:
            est, lst, _ = windows(inst, h)
            bad_jobs = [i for i in range(inst['n'])
                        if est[i] > lst[i]]
            if not bad_jobs:
                break
            i = bad_jobs[0]
            cert = dict(kind='window', job=i, est=est[i], lst=lst[i])
        if not verify_prep(inst, h, cert):
            bad += 1
            break
        certs.append((h, cert))
        h += 1
    return h, certs, bad


# ------------------------------------------------------------- evolutionary
def _perm_rank(perm):
    return {i: k for k, i in enumerate(perm)}


def _decode(inst, perm):
    g = _greedy_rank(inst, _perm_rank(perm))
    if g is None:
        return None
    return g[2], g[0], g[1]


def _ox(p1, p2, rng):
    n = len(p1)
    a = rng.randrange(n)
    b = rng.randrange(n)
    if a > b:
        a, b = b, a
    child = [None] * n
    child[a:b + 1] = p1[a:b + 1]
    used = set(child[a:b + 1])
    rest = [x for x in p2 if x not in used]
    j = 0
    for k in range(n):
        if child[k] is None:
            child[k] = rest[j]
            j += 1
    return child


def _mutate(p, rng, pm):
    q = list(p)
    n = len(q)
    if rng.random() < pm:
        i = rng.randrange(n)
        j = rng.randrange(n)
        q[i], q[j] = q[j], q[i]
    if rng.random() < pm:
        i = rng.randrange(n)
        j = rng.randrange(n)
        x = q.pop(i)
        q.insert(j, x)
    return q


def _seed_population(inst, ub, rng, popsize):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    latest = [ub - q[i] - inst['p'][i] for i in range(n)]
    keys = [
        est,
        latest,
        [-q[i] for i in range(n)],
        [est[i] - 0.5 * q[i] for i in range(n)],
        [inst['p'][i] for i in range(n)],
        [-inst['p'][i] for i in range(n)],
        [est[i] + q[i] for i in range(n)],
        [est[i] - q[i] for i in range(n)],
    ]
    pop = [sorted(range(n), key=lambda i: (key[i], i)) for key in keys]
    while len(pop) < popsize:
        p = list(range(n))
        rng.shuffle(p)
        pop.append(p)
    return pop


def evolve(inst, ub0, lb, budget=256, popsize=24, seed=20261024,
           block=64, patience=2, mode='ea'):
    """(mu+lambda) EA on priority permutations.

    The budget is released in blocks.  A block that does not improve the
    incumbent ends the evolutionary phase (resource allocation by
    observed marginal return).  The first block is always spent.
    """
    rng = random.Random(seed)
    n = inst['n']
    ub = ub0
    best = None
    evals = 0
    first = None
    improved = 0
    blocks = 0
    pop = _seed_population(inst, ub, rng, popsize)
    scored = []
    for p in pop:
        r = _decode(inst, p)
        evals += 1
        c = None if r is None else r[0]
        scored.append((10 ** 9 if c is None else c, p))
        if c is not None and c < ub \
                and check_schedule(inst, c, r[1], r[2]):
            ub = c
            best = (list(r[1]), list(r[2]), list(p))
            first = evals if first is None else first
            improved += 1
    scored.sort(key=lambda x: (x[0], x[1]))
    if mode == 'random':
        while evals < budget and ub > lb:
            p = list(range(n))
            rng.shuffle(p)
            r = _decode(inst, p)
            evals += 1
            c = None if r is None else r[0]
            if c is not None and c < ub \
                    and check_schedule(inst, c, r[1], r[2]):
                ub = c
                best = (list(r[1]), list(r[2]), list(p))
                first = evals if first is None else first
                improved += 1
        return dict(ub=ub, best=best, evals=evals, first=first,
                    improved=improved, blocks=0, pop=[])
    stag = 0
    no_imp_blocks = 0

    def tournament():
        cand = [scored[rng.randrange(len(scored))] for _ in range(3)]
        return min(cand, key=lambda x: (x[0], x[1]))

    block_end = min(budget, block)
    block_best = ub
    while evals < budget and ub > lb:
        new = scored[:max(2, popsize // 4)]
        while len(new) < popsize:
            p1 = tournament()[1]
            p2 = tournament()[1]
            child = _ox(p1, p2, rng) if rng.random() < 0.8 else list(p1)
            child = _mutate(child, rng, 0.35 if stag < 10 else 0.6)
            r = _decode(inst, child)
            evals += 1
            c = None if r is None else r[0]
            if c is not None and c < ub \
                    and check_schedule(inst, c, r[1], r[2]):
                ub = c
                best = (list(r[1]), list(r[2]), list(child))
                first = evals if first is None else first
                improved += 1
                stag = 0
            new.append((10 ** 9 if c is None else c, child))
        new.sort(key=lambda x: (x[0], x[1]))
        seen = set()
        uniq = []
        for c, p in new:
            key = tuple(p)
            if key in seen:
                continue
            seen.add(key)
            uniq.append((c, p))
        while len(uniq) < popsize:
            p = list(range(n))
            rng.shuffle(p)
            r = _decode(inst, p)
            evals += 1
            c = None if r is None else r[0]
            if c is not None and c < ub \
                    and check_schedule(inst, c, r[1], r[2]):
                ub = c
                best = (list(r[1]), list(r[2]), list(p))
                first = evals if first is None else first
                improved += 1
            uniq.append((10 ** 9 if c is None else c, p))
        scored = sorted(uniq, key=lambda x: (x[0], x[1]))
        stag += 1
        if stag > 25:
            for k in range(max(2, popsize // 4)):
                p = list(range(n))
                rng.shuffle(p)
                r = _decode(inst, p)
                evals += 1
                c = None if r is None else r[0]
                if c is not None and c < ub \
                        and check_schedule(inst, c, r[1], r[2]):
                    ub = c
                    best = (list(r[1]), list(r[2]), list(p))
                    first = evals if first is None else first
                    improved += 1
                    stag = 0
                scored[-(k + 1)] = (10 ** 9 if c is None else c, p)
            scored.sort(key=lambda x: (x[0], x[1]))
            stag = 0
        if evals >= block_end:
            blocks += 1
            if ub < block_best:
                no_imp_blocks = 0
            else:
                no_imp_blocks += 1
            block_best = ub
            if no_imp_blocks >= patience:
                break
            block_end = min(budget, evals + block)
    return dict(ub=ub, best=best, evals=evals, first=first,
                improved=improved, blocks=blocks,
                pop=[(c, p) for c, p in scored[:popsize]])


# ------------------------------------------------------------------ bracket
def eager_bounds(inst, ea_budget=256, ea_block=64, ea_patience=2,
                 max_subsets=64, max_intervals=20000, ea_mode='ea'):
    lb0, ub0, starts, machs, est, q = base_bounds(inst)
    if ub0 is None or not check_schedule(inst, ub0, starts, machs):
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
    ea = dict(ub=ub, evals=0, first=None, improved=0, blocks=0)
    if ea_budget > 0 and ub > lb:
        ea = evolve(inst, ub, lb, budget=ea_budget,
                    block=ea_block, patience=ea_patience, mode=ea_mode)
        if ea['best'] is not None and ea['ub'] < ub:
            sched, mach = ea['best'][0], ea['best'][1]
            ub = ea['ub']
    lb, certs, cert_bad = lift_bounds(inst, lb, ub, max_subsets,
                                      max_intervals)
    return dict(ok=True, lb0=lb0, ub0=ub0, lb=lb, ub=ub,
                schedule=sched, machine=mach,
                lifts=len(certs), certs=certs, cert_bad=cert_bad,
                drops=drops, ea=ea,
                ratio0=ub0 / lb0 if lb0 > 0 else None,
                ratio=ub / lb if lb > 0 else None)


# ----------------------------------------------------------------- optimizer
class EAGER(CABOpt):
    """Evolutionary incumbent + certified bracket + promoted prep proofs."""

    def __init__(self, inst, ea_budget=256, ea_block=64, ea_patience=2,
                 probe_budget=2, promote=True, ea_mode='ea', **kw):
        super().__init__(inst, **kw)
        self.ea_budget = ea_budget
        self.ea_block = ea_block
        self.ea_patience = ea_patience
        self.probe_budget = probe_budget
        self.promote = promote
        self.ea_mode = ea_mode
        self.probe_left = probe_budget
        self.prep = None
        self.prep_proofs = {}
        self.base_lb0 = None
        self.base_proof = None
        self.free_queries = 0
        self.probes = 0
        self.bisect = 0
        self.ea_evals = 0
        self.ea_improved = 0

    def initial_bounds(self):
        b = eager_bounds(self.inst, ea_budget=self.ea_budget,
                         ea_block=self.ea_block,
                         ea_patience=self.ea_patience,
                         ea_mode=self.ea_mode)
        self.prep = b
        if not b.get('ok'):
            return b['lb0'], None, None, None
        if self.promote:
            self.base_lb0 = b['lb0']
            self.base_proof = BaseProof(self.inst, b['lb0'] - 1, b['lb0'])
            for h, cert in b.get('certs', []):
                self.prep_proofs[h] = PrepProof(self.inst, h, cert)
        self.ea_evals = b['ea'].get('evals', 0)
        self.ea_improved = b['ea'].get('improved', 0)
        return b['lb'], b['ub'], b['schedule'], b['machine']

    def _decide(self, h):
        if h in self.prep_proofs:
            p = self.prep_proofs[h]
            return False, p.stats(), p
        if self.base_lb0 is not None and h < self.base_lb0:
            return False, self.base_proof.stats(), self.base_proof
        rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.last_oracle = rdf
        return v, st, rdf

    def _oracle(self, h):
        """One oracle call; prep certificates are free."""
        if h in self.prep_proofs:
            self.free_queries += 1
            p = self.prep_proofs[h]
            return False, p.stats(), p, True
        if self.base_lb0 is not None and h < self.base_lb0:
            self.free_queries += 1
            p = self.base_proof
            return False, p.stats(), p, True
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, st, rdf, False

    def _choose_h(self):
        d = self.opt - self.lb
        if d <= 1:
            return self.opt - 1
        if self.probe_left > 0:
            h = self.opt - 1
            if h in self.prep_proofs or (
                    self.base_lb0 is not None and h < self.base_lb0):
                return h
            self.probe_left -= 1
            self.probes += 1
            return h
        self.bisect += 1
        return (self.lb + self.opt) // 2

    def _apply(self, h, v, rdf):
        if v is True:
            if rdf.schedule is None or rdf.machine is None:
                return
            cmax = max(rdf.schedule[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if cmax < self.opt and check_schedule(
                    self.inst, cmax, rdf.schedule, rdf.machine):
                self.opt = cmax
                self.schedule = list(rdf.schedule)
                self.machine = list(rdf.machine)
        elif v is False:
            self.lb = max(self.lb, h + 1)
            self.no_states[h] = rdf
            self.lb_proof = rdf

    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is not None:
            self.schedule, self.machine, self.opt = starts, machs, ub
        # probe the incumbent first; if it is already optimal, this is one call.
        while self.lb < self.opt and self.queries < self.max_queries:
            h = self._choose_h()
            v, st, rdf, free = self._oracle(h)
            self._apply(h, v, rdf)
            if v is None:
                # UNKNOWN: do not change the bracket; retry a neighbour.
                self.unknown += 1
                for probe in (h, max(self.lb, h - 1)):
                    if self.queries >= self.max_queries:
                        break
                    v2, st2, rdf2, free2 = self._oracle(probe)
                    self._apply(probe, v2, rdf2)
                    if v2 is not None:
                        break
        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified and (self.opt - 1) not in self.no_states:
            h = self.opt - 1
            if h in self.prep_proofs:
                p = self.prep_proofs[h]
                self.no_states[h] = p
                self.lb_proof = p
                self.free_queries += 1
            elif self.base_lb0 is not None and h < self.base_lb0:
                p = self.base_proof
                self.no_states[h] = p
                self.lb_proof = p
                self.free_queries += 1
            else:
                v, st, rdf, free = self._oracle(h)
                self._apply(h, v, rdf)
                if v is True:
                    # the incumbent was not optimal; continue from the
                    # improved schedule with whatever budget remains.
                    self.certified = False
                    while self.lb < self.opt \
                            and self.queries < self.max_queries:
                        h2 = self._choose_h()
                        v2, st2, rdf2, free2 = self._oracle(h2)
                        self._apply(h2, v2, rdf2)
                    self.certified = (self.lb == self.opt)
        return self._result()

    def _result(self):
        r = super()._result()
        r['free_queries'] = self.free_queries
        r['probes'] = self.probes
        r['bisect'] = self.bisect
        r['ea_evals'] = self.ea_evals
        r['ea_improved'] = self.ea_improved
        if self.prep:
            r['prep'] = dict(lb0=self.prep.get('lb0'),
                             ub0=self.prep.get('ub0'),
                             lb=self.prep.get('lb'),
                             ub=self.prep.get('ub'),
                             lifts=self.prep.get('lifts'),
                             drops=self.prep.get('drops'),
                             cert_bad=self.prep.get('cert_bad'),
                             ea=dict(evals=self.prep['ea'].get('evals'),
                                     improved=self.prep['ea'].get('improved'),
                                     first=self.prep['ea'].get('first'),
                                     blocks=self.prep['ea'].get('blocks')))
        return r
