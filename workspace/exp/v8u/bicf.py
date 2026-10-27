"""v9.1 BICF-P: buffered invariant-carrying frontier portfolio.

The offline ICF state is (L, U, s, m, pi).  BICF-P adds an *online
commitment layer*: jobs are revealed in a topological order, at most b
of them are buffered, and every commitment is irrevocable.  A portfolio
of priority rules is run in parallel; each rule builds a complete
feasible schedule online, and the best one is kept.

The state is

    C_t = (P_t, B_t, S_t, L_t, U_t)

where P_t is the committed prefix, B_t the reordering buffer, S_t a
feasible tentative schedule, L_t a certified lower bound on OPT, and
U_t = Cmax(S_t).  The ratio certificate is rho_t = U_t / L_t.

The expensive exact oracle is optional: if a target ratio rho* is not
met, the ICF exact loop can be run on the bracket [L_t, U_t].  The
default BICF-P run is polynomial and uses only list scheduling plus a
combinatorial lower bound.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import check_schedule
from icf import cmax, ICFCertificate
from pact import PACT, pact_decide


# --------------------------------------------------------------- utilities
def topo_order(inst):
    n = inst['n']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    q = [i for i in range(n) if indeg[i] == 0]
    out = []
    while q:
        i = q.pop()
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    if len(out) != n:
        raise ValueError('precedence cycle')
    return out


def heads_tails(inst):
    n, p = inst['n'], inst['p']
    order = topo_order(inst)
    est = [0] * n
    for i in order:
        e = 0
        for j in inst['pred'][i]:
            e = max(e, est[j] + p[j])
        est[i] = e
    q = [0] * n
    for i in reversed(order):
        b = 0
        for j in inst['succ'][i]:
            b = max(b, p[j] + q[j])
        q[i] = b
    return est, q


def cheap_lb(inst):
    """Critical path + average load + eligibility-restricted load."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    est, q = heads_tails(inst)
    lb = max(est[i] + p[i] + q[i] for i in range(n))
    lb = max(lb, (sum(p) + m - 1) // m)
    # For m <= 8 we can enumerate all machine subsets exactly.
    if m <= 8:
        for mask in range(1, 1 << m):
            cnt = bin(mask).count('1')
            load = 0
            for i in range(n):
                if all((mask >> k) & 1 for k in elig[i]):
                    load += p[i]
            lb = max(lb, (load + cnt - 1) // cnt)
    else:
        for k in range(m):
            load = sum(p[i] for i in range(n) if elig[i] == [k])
            lb = max(lb, load)
    return int(lb)


def policy_key(inst, i, rule, est, q, rng=None):
    p = inst['p'][i]
    if rule == 'critical':
        return (q[i], p, -i)
    if rule == 'hlf':
        return (q[i] + p, q[i], -i)
    if rule == 'lpt':
        return (p, q[i], -i)
    if rule == 'spt':
        return (-p, q[i], -i)
    if rule == 'est':
        return (-est[i], q[i], -i)
    if rule == 'mixed':
        return (q[i] + 0.5 * p, p, -i)
    if rule == 'random':
        return (rng[i], -i)
    raise ValueError('unknown rule %r' % (rule,))


def make_rules(n_random=0, seed=0):
    rules = [(r, None) for r in ('critical', 'hlf', 'lpt', 'spt',
                                 'est', 'mixed')]
    for s in range(n_random):
        rng = random.Random(seed + s)
        rank = {i: rng.random() for i in range(64)}
        rules.append(('random', rank))
    return rules


# ------------------------------------------------------- buffered scheduler
def schedule(inst, order, b, rule, rank=None, est=None, q=None,
             snapshots=False):
    """One online buffered list schedule.

    The order is a topological order.  At most b revealed jobs are kept
    in the buffer.  When a job is committed, it is placed at the earliest
    feasible start on an eligible machine.  The resulting schedule is
    feasible and respects precedence.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    if est is None or q is None:
        est, q = heads_tails(inst)
    starts = [None] * n
    mach = [None] * n
    finish = [None] * n
    free = [0] * m
    committed = set()
    buffer = []
    pos = 0
    states = [] if snapshots else None
    while pos < n or buffer:
        while len(buffer) < b and pos < n:
            buffer.append(order[pos])
            pos += 1
        avail = [i for i in buffer
                 if all(j in committed for j in inst['pred'][i])]
        if not avail:
            # A topological order guarantees this cannot happen; keep a
            # defensive deterministic fallback.
            i = min(buffer, key=lambda x: order.index(x))
        else:
            i = max(avail, key=lambda x: policy_key(
                inst, x, rule, est, q, rank))
        buffer.remove(i)
        ready = 0
        for j in inst['pred'][i]:
            if finish[j] is None:
                raise ValueError('precedence violated by order')
            ready = max(ready, finish[j])
        best = None
        for k in inst['elig'][i]:
            st = max(free[k], ready)
            cand = (st + p[i], st, k)
            if best is None or cand < best:
                best = cand
        _, st, k = best
        starts[i] = st
        mach[i] = k
        finish[i] = st + p[i]
        free[k] = finish[i]
        committed.add(i)
        if snapshots:
            states.append(dict(committed=sorted(committed), job=i,
                               start=st, machine=k,
                               partial=list(starts)))
    c = cmax(inst, starts)
    if not check_schedule(inst, c, starts, mach):
        raise RuntimeError('infeasible buffered schedule')
    return dict(starts=starts, machine=mach, cmax=c, states=states)


def portfolio(inst, order, b, rules, est=None, q=None):
    """Run all rules in parallel; keep the minimum makespan schedule."""
    if est is None or q is None:
        est, q = heads_tails(inst)
    best = None
    per_rule = {}
    for rule, rank in rules:
        r = schedule(inst, order, b, rule, rank, est, q)
        per_rule[rule if rank is None else 'random'] = r['cmax']
        if best is None or r['cmax'] < best['cmax']:
            best = r
    best['per_rule'] = per_rule
    return best


# ------------------------------------------------------------- certificate
class RatioCertificate:
    """A committed prefix + a feasible completion + a certified L <= OPT.

    lb_mode = 'cheap'  : L is the combinatorial bound, recomputed by the
                         auditor from the instance.
    lb_mode = 'proof'  : L-1 has a replayable NO proof (ICF proof object).
    """

    kind = 'bicf-ratio'

    def __init__(self, inst, starts, machine, L, committed=None,
                 lb_proof=None, lb_mode='cheap', label=''):
        self.inst = inst
        self.starts = list(starts) if starts is not None else None
        self.machine = list(machine) if machine is not None else None
        self.L = int(L)
        self.U = cmax(inst, self.starts) if self.starts is not None else None
        self.committed = dict(committed or {})
        self.lb_proof = lb_proof
        self.lb_mode = lb_mode
        self.label = label

    def audit_rdf(self):
        try:
            if self.starts is None or self.machine is None:
                return False
            if self.U != cmax(self.inst, self.starts):
                return False
            if not check_schedule(self.inst, self.U, self.starts,
                                  self.machine):
                return False
            for i, (st, k) in self.committed.items():
                if self.starts[i] != st or self.machine[i] != k:
                    return False
            if self.L > self.U:
                return False
            if self.lb_mode == 'proof':
                p = self.lb_proof
                if p is None or p.h != self.L - 1:
                    return False
                return bool(p.audit_rdf())
            return self.L == cheap_lb(self.inst)
        except Exception:
            return False

    @property
    def ratio(self):
        return self.U / self.L if self.L else float('inf')


# --------------------------------------------------------------- driver
def initial_lp_bound(inst):
    """The v9.0 LP/Farkas lower bound, with a replayable proof."""
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, sched, mach = co.initial_bounds()
    if ub is None:
        return None
    lb = int(lb)
    proof = co._ensure_lb_proof(lb)
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    return dict(L=lb, U=ub, schedule=sched, machine=mach,
                proof=proof, pin_lp=getattr(co, 'pin_lp', 0))


def make_order(inst, seed=1, key='critical'):
    """A topological order with a priority key."""
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst)
    rng = random.Random(seed)
    indeg = [len(inst['pred'][i]) for i in range(n)]
    ready = [i for i in range(n) if indeg[i] == 0]

    def score(i):
        if key == 'random':
            return rng.random()
        if key == 'critical':
            return -q[i]
        if key == 'reverse-critical':
            return q[i]
        if key == 'lpt':
            return -p[i]
        if key == 'est':
            return est[i]
        raise ValueError(key)

    out = []
    while ready:
        ready.sort(key=lambda i: (score(i), i))
        i = ready.pop(0)
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
    return out


def corpora():
    from chip import base_corpus, pert_corpus, stress_corpus
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
