"""v9.3 O-ICF: online invariant-carrying frontier.

The offline ICF state is (L, U, s, m, pi).  This module lifts it to an
online list/assignment setting.  The state is

    (P_t, R_t, s_t, m_t, L_t, pi_t, U_t)

where P_t is an irrevocable committed prefix, R_t the not-yet-committed
jobs, (s_t, m_t) a feasible completion of the prefix plus the current
batch, pi_t a proof that the current batch cannot be completed below
L_t, and U_t the makespan of (s_t, m_t).

The main new object is the *prefix-conditional* certificate: at every
batch, the solver returns an optimal schedule for the jobs revealed so
far, with the earlier prefix fixed.  This is an optimality certificate
for the conditional problem, not for the unknown full instance.  The
full-instance regret is bracketed by a cheap global lower bound and the
current schedule.

Two schedules are provided:

  list_schedule      order-online, one pass, no oracle
  run_batches        b-lookahead, exact PACT per batch

The first is the fully online fallback.  The second is the
certificate-carrying online algorithm whose batch subproblem is NP-hard
(and is solved exactly here only because n is small).
"""
import sys
import time
import random
import collections
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from po import make_inst
from rdf import check_schedule
from sage import _domain
from pact import pact_decide


# --------------------------------------------------------------- utilities
def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def domain_empty(inst, h, forbid):
    for i in range(inst['n']):
        lo, hi = _domain(inst, h, i)
        if lo > hi:
            return True
        if all((i, t) in forbid for t in range(lo, hi + 1)):
            return True
    return False


def decide_safe(inst, h, forbid=frozenset()):
    if h < 0 or domain_empty(inst, h, forbid):
        return dict(verdict=False, proof=None, schedule=None, machine=None,
                    lp_solves=0, nodes=0, cert_lp=0, unknown=0,
                    empty_domain=True)
    try:
        return pact_decide(inst, h, depthcap=None, nodecap=None,
                           forbid0=forbid)
    except Exception:
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    lp_solves=0, nodes=0, cert_lp=0, unknown=1,
                    exception=True)


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


def heads_tails(inst, release=None):
    n, p = inst['n'], inst['p']
    if release is None:
        release = [0] * n
    order = topo_order(inst)
    est = [0] * n
    for i in order:
        e = release[i]
        for j in inst['pred'][i]:
            e = max(e, est[j] + p[j])
        est[i] = e
    q = [0] * n
    for i in reversed(order):
        b = 0
        for j in inst['succ'][i]:
            b = max(b, p[j] + q[j])
        q[i] = b
    return est, q, order


def lower_bound(inst, release=None):
    """A certified lower bound on OPT with release dates."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    est, q, order = heads_tails(inst, release)
    lb = max(est[i] + p[i] + q[i] for i in range(n))
    lb = max(lb, max((release[i] if release else 0) + p[i]
                     for i in range(n)))
    lb = max(lb, (sum(p) + m - 1) // m)
    for mask in range(1, 1 << m):
        load = 0
        cnt = bin(mask).count('1')
        for i in range(n):
            if all((mask >> k) & 1 for k in elig[i]):
                load += p[i]
        if cnt:
            lb = max(lb, (load + cnt - 1) // cnt)
    return int(lb)


def prefix_lower_bound(inst, committed, release=None):
    """Lower bound on any completion that keeps ``committed`` fixed.

    committed maps i -> (start, machine).  The set must be
    predecessor-closed.
    """
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    if release is None:
        release = [0] * n
    est, q, order = heads_tails(inst, release)
    for i, (st, k) in committed.items():
        est[i] = max(est[i], st)
    for i in order:
        if i in committed:
            continue
        e = release[i]
        for j in inst['pred'][i]:
            e = max(e, est[j] + p[j])
        est[i] = max(est[i], e)
    lb = max(est[i] + p[i] + q[i] for i in range(n))
    lb = max(lb, max((release[i] if release else 0) + p[i]
                     for i in range(n)))
    lb = max(lb, (sum(p) + m - 1) // m)
    for i, (st, k) in committed.items():
        lb = max(lb, st + p[i])
    for mask in range(1, 1 << m):
        load = 0
        cnt = bin(mask).count('1')
        for i in range(n):
            if all((mask >> k) & 1 for k in elig[i]):
                load += p[i]
        if cnt:
            lb = max(lb, (load + cnt - 1) // cnt)
    return int(lb)


def greedy_fixed(inst, committed, release=None, priority='hlf'):
    """Feasible completion that keeps committed starts/machines fixed."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    if release is None:
        release = [0] * n
    est, q, order = heads_tails(inst, release)
    starts = [None] * n
    mach = [None] * n
    finish = [None] * n
    free = [0] * m
    for i, (st, k) in committed.items():
        starts[i], mach[i] = int(st), int(k)
        finish[i] = starts[i] + p[i]
        free[k] = max(free[k], finish[i])
    for i in order:
        if i in committed:
            continue
        ready = release[i]
        for j in inst['pred'][i]:
            if finish[j] is None:
                raise ValueError('committed set is not predecessor-closed')
            ready = max(ready, finish[j])
        best = None
        for k in elig[i]:
            st = max(free[k], ready)
            key = (st + p[i], st, k)
            if best is None or key < best[0]:
                best = (key, k, st)
        if best is None:
            return None
        _, k, st = best
        starts[i], mach[i] = st, k
        finish[i] = st + p[i]
        free[k] = finish[i]
    if any(x is None for x in starts):
        return None
    c = cmax(inst, starts)
    if not check_schedule(inst, c, starts, mach):
        return None
    return starts, mach, c


# ------------------------------------------------------------ order online
def schedule_list(inst, order):
    """Schedule jobs in a fixed topological list, immediately, one pass."""
    n, m, p, elig = inst['n'], inst['m'], inst['p'], inst['elig']
    starts = [None] * n
    mach = [None] * n
    finish = [None] * n
    free = [0] * m
    for i in order:
        ready = 0
        for j in inst['pred'][i]:
            if finish[j] is None:
                raise ValueError('order is not topological')
            ready = max(ready, finish[j])
        best = None
        for k in elig[i]:
            st = max(free[k], ready)
            key = (st + p[i], st, k)
            if best is None or key < best[0]:
                best = (key, k, st)
        if best is None:
            return None
        _, k, st = best
        starts[i], mach[i] = st, k
        finish[i] = st + p[i]
        free[k] = finish[i]
    c = cmax(inst, starts)
    if not check_schedule(inst, c, starts, mach):
        return None
    return starts, mach, c


def random_topo_order(inst, seed=0, key='random'):
    """A topological order; key selects the online list policy."""
    n, p = inst['n'], inst['p']
    rng = random.Random(seed)
    est, q, _ = heads_tails(inst)
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
        if key == 'spt':
            return p[i]
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


# ------------------------------------------------------- batch subproblem
def subinstance(inst, committed, batch):
    """Sub-instance of committed + batch; all predecessors must be inside."""
    inc = sorted(set(committed) | set(batch))
    where = {i: k for k, i in enumerate(inc)}
    for i in inc:
        for j in inst['pred'][i]:
            if j not in where:
                raise ValueError('subinstance is not predecessor-closed')
    p = [inst['p'][i] for i in inc]
    pred = [[where[j] for j in inst['pred'][i]] for i in inc]
    elig = [list(inst['elig'][i]) for i in inc]
    sub = make_inst(p, inst['m'], pred, elig)
    fixed = {}
    for i, (st, k) in committed.items():
        ni = where[i]
        sub['elig'][ni] = [int(k)]
        fixed[ni] = (int(st), int(k))
    return sub, where, fixed


def _fixed_forbid(sub, fixed):
    forb = set()
    tmax = sum(sub['p']) + max([st for st, _ in fixed.values()] or [0]) + 10
    for i, (st, _) in fixed.items():
        for t in range(0, tmax + 1):
            if t != st:
                forb.add((i, t))
    return frozenset(forb)


def solve_batch(inst, committed, batch, max_calls=200, timelimit=None):
    """Exact makespan of committed+batch, with committed starts fixed.

    Returns a dict with schedule/machine on the sub-instance, the
    conditional optimum, and the NO(opt-1) proof when available.
    """
    sub, where, fixed = subinstance(inst, committed, batch)
    forb = _fixed_forbid(sub, fixed)
    g = greedy_fixed(sub, fixed)
    if g is None:
        return dict(ok=False, reason='no-greedy')
    sched, mach, ub = g
    lb = prefix_lower_bound(sub, fixed)
    lb = min(lb, ub)
    calls = lp = nodes = cert_lp = 0
    best = (sched, mach, ub)
    proof = None
    unknown = 0
    t0 = time.time()
    while lb < ub and calls < max_calls:
        if timelimit is not None and time.time() - t0 > timelimit:
            break
        mid = (lb + ub) // 2
        r = decide_safe(sub, mid, forb)
        calls += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            lb = mid + 1
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(sub, s2)
            if c2 < ub and check_schedule(sub, c2, s2, m2):
                ub = c2
                best = (list(s2), list(m2), c2)
        else:
            unknown += 1
            break
    sched, mach, ub = best
    if ub > lb:
        # certificate search at ub-1 (gives the conditional lower proof)
        r = decide_safe(sub, ub - 1, forb)
        calls += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
            lb = ub
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(sub, s2)
            if c2 < ub:
                ub = c2
                best = (list(s2), list(m2), c2)
        else:
            unknown += 1
    sched, mach, ub = best
    exact = bool(lb == ub and check_schedule(sub, ub, sched, mach))
    if proof is None and exact and ub > 0:
        r = decide_safe(sub, ub - 1, forb)
        calls += 1
        lp += r.get('lp_solves', 0)
        nodes += r.get('nodes', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
    proof_ok = bool(proof is not None and proof.audit_rdf())
    return dict(ok=True, exact=exact, sub=sub, where=where,
                fixed=fixed, schedule=sched, machine=mach, opt=ub,
                lb=lb, proof=proof, proof_ok=proof_ok,
                calls=calls, lp=lp, nodes=nodes,
                cert_lp=cert_lp, unknown=unknown)


def run_batches(inst, order, batch_size, max_calls=200,
                timelimit=None, audit=True):
    """Online b-lookahead: reveal a batch, solve it exactly, commit it."""
    n = inst['n']
    starts = [None] * n
    mach = [None] * n
    committed = {}
    states = []
    calls = lp = nodes = cert_lp = 0
    t0 = time.time()
    batches = [order[i:i + batch_size] for i in range(0, n, batch_size)]
    for bi, batch in enumerate(batches):
        if batch_size == 1:
            # one free job: earliest completion is exact
            sub, where, fixed = subinstance(inst, committed, batch)
            g = greedy_fixed(sub, fixed)
            if g is None:
                return dict(ok=False, reason='no-greedy', starts=starts,
                            machine=mach, states=states)
            s, m, c = g
            sol = dict(ok=True, exact=True, sub=sub,
                       where=where, fixed=fixed, schedule=s, machine=m,
                       opt=c, lb=c, proof=None, calls=0, lp=0, nodes=0,
                       cert_lp=0, unknown=0)
        else:
            sol = solve_batch(inst, committed, batch, max_calls=max_calls,
                              timelimit=timelimit)
            if not sol.get('ok'):
                return dict(ok=False, reason=sol.get('reason'),
                            starts=starts, machine=mach, states=states)
        calls += sol['calls']
        lp += sol['lp']
        nodes += sol['nodes']
        cert_lp += sol['cert_lp']
        if len(buffer) == n and not committed and sol.get('proof') is not None:
            full_proof = sol['proof']
        for i in batch:
            ni = sol['where'][i]
            starts[i] = sol['schedule'][ni]
            mach[i] = sol['machine'][ni]
            committed[i] = (starts[i], mach[i])
        if audit:
            # only the prefix is complete; the rest is None
            prefix_ok = all(starts[i] is not None for i in committed)
            states.append(dict(batch=bi, n_batch=len(batch),
                               opt_cond=sol['opt'], lb=sol['lb'],
                               exact=sol['exact'],
                               proof_kind=(sol['proof'].kind
                                           if sol.get('proof') else None),
                               calls=sol['calls'],
                               prefix_ok=prefix_ok))
        if not sol['exact'] and timelimit is not None:
            # keep going with a feasible fallback completion
            g = greedy_fixed(inst, committed)
            if g is not None:
                s, m, c = g
                for i in range(n):
                    if starts[i] is None:
                        starts[i], mach[i] = s[i], m[i]
            break
    for i in range(n):
        if starts[i] is None:
            g = greedy_fixed(inst, committed)
            if g is None:
                return dict(ok=False, reason='incomplete', starts=starts,
                            machine=mach, states=states)
            s, m, c = g
            for j in range(n):
                if starts[j] is None:
                    starts[j], mach[j] = s[j], m[j]
            break
    c = cmax(inst, starts)
    ok = check_schedule(inst, c, starts, mach)
    return dict(ok=ok, starts=starts, machine=mach, opt=c,
                calls=calls, lp=lp, nodes=nodes,
                cert_lp=cert_lp, states=states,
                batches=len(batches), t=round(time.time() - t0, 4),
                exact_all=all(s.get('exact') for s in states))


# ------------------------------------------------------------- certificate
class OnlinePartialCertificate:
    """A prefix plus a feasible completion and a global lower bound."""

    kind = 'oicf-online'

    def __init__(self, inst, committed, schedule, machine, lb,
                 release=None, state=None):
        self.inst = inst
        self.committed = dict(committed)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb = int(lb)
        self.release = release
        self.state = state or {}

    def audit_rdf(self):
        try:
            if self.schedule is None or self.machine is None:
                return False
            for i, (st, k) in self.committed.items():
                if self.schedule[i] != st or self.machine[i] != k:
                    return False
            u = cmax(self.inst, self.schedule)
            if not check_schedule(self.inst, u, self.schedule,
                                  self.machine):
                return False
            if self.release is not None:
                for i, r in enumerate(self.release):
                    if self.schedule[i] < r:
                        return False
            if self.lb > u:
                return False
            # the global bound is the certified expression below
            if self.state.get('lb_mode') == 'global':
                if self.lb != lower_bound(self.inst, self.release):
                    return False
            return True
        except Exception:
            return False


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


def run_rolling(inst, order, lookahead, max_calls=200, timelimit=None,
                audit=True, commit_rule='order', place='optimal'):
    """Receding-horizon online dispatch with a lookahead buffer.

    At each step the buffer contains the earliest ``lookahead`` jobs that
    have been revealed but not committed.  The buffer plus the committed
    prefix is solved exactly; only the earliest-starting buffer job is
    committed.  Then the next job in the order is revealed.  With
    lookahead = n this is an exact online scheduler (the optimal residual
    schedule is committed one job at a time).  With lookahead = 1 it is
    earliest-completion list scheduling.
    """
    n = inst['n']
    pos = {i: k for k, i in enumerate(order)}
    starts = [None] * n
    mach = [None] * n
    committed = {}
    nxt = 0
    buffer = []
    while nxt < n and len(buffer) < lookahead:
        buffer.append(order[nxt])
        nxt += 1
    states = []
    calls = lp = nodes = cert_lp = 0
    cert_ok = cert_fail = 0
    full_proof = None
    t0 = time.time()
    while buffer:
        if lookahead == 1:
            sub, where, fixed = subinstance(inst, committed, buffer)
            g = greedy_fixed(sub, fixed)
            if g is None:
                return dict(ok=False, reason='no-greedy', starts=starts,
                            machine=mach, states=states)
            sol = dict(ok=True, exact=True, sub=sub, where=where,
                       fixed=fixed, schedule=g[0], machine=g[1],
                       opt=g[2], lb=g[2], proof=None, calls=0, lp=0,
                       nodes=0, cert_lp=0, unknown=0)
        else:
            sol = solve_batch(inst, committed, buffer, max_calls=max_calls,
                              timelimit=timelimit)
            if not sol.get('ok'):
                return dict(ok=False, reason=sol.get('reason'),
                            starts=starts, machine=mach, states=states)
        calls += sol['calls']
        lp += sol['lp']
        nodes += sol['nodes']
        cert_lp += sol['cert_lp']
        if len(buffer) == n and not committed and sol.get('proof') is not None:
            full_proof = sol['proof']
        # choose one buffer job from the conditional optimum
        if commit_rule == 'earliest':
            cand = []
            for i in buffer:
                ni = sol['where'][i]
                cand.append((sol['schedule'][ni], pos[i], i))
            cand.sort()
            j = cand[0][2]
        elif commit_rule == 'order':
            j = min(buffer, key=lambda i: pos[i])
        elif commit_rule == 'critical':
            est, q, _ = heads_tails(inst)
            j = max(buffer, key=lambda i: (q[i], -pos[i]))
        elif commit_rule == 'latest':
            cand = []
            for i in buffer:
                ni = sol['where'][i]
                cand.append((sol['schedule'][ni], pos[i], i))
            cand.sort(reverse=True)
            j = cand[0][2]
        else:
            raise ValueError(commit_rule)
        nj = sol['where'][j]
        if place == 'optimal':
            starts[j], mach[j] = sol['schedule'][nj], sol['machine'][nj]
        elif place == 'greedy':
            ready = 0
            okp = True
            for pred in inst['pred'][j]:
                if pred not in committed:
                    okp = False
                    break
                ready = max(ready, committed[pred][0] + inst['p'][pred])
            if not okp:
                starts[j], mach[j] = sol['schedule'][nj], sol['machine'][nj]
            else:
                free = [0] * inst['m']
                for x, (st, k) in committed.items():
                    free[k] = max(free[k], st + inst['p'][x])
                best = None
                for k in inst['elig'][j]:
                    st = max(free[k], ready)
                    key = (st + inst['p'][j], st, k)
                    if best is None or key < best[0]:
                        best = (key, k, st)
                _, k, st = best
                starts[j], mach[j] = st, k
        else:
            raise ValueError(place)
        committed[j] = (starts[j], mach[j])
        if audit:
            states.append(dict(buffer=list(buffer), commit=j,
                               opt_cond=sol['opt'], lb=sol['lb'],
                               exact=sol['exact'],
                               proof_kind=(sol['proof'].kind
                                           if sol.get('proof') else None),
                               proof_ok=sol.get('proof_ok', False),
                               bound_ok=bool(sol['lb'] == sol['opt']),
                               calls=sol['calls'],
                               prefix_ok=all(starts[i] is not None
                                             for i in committed)))
        if audit and place == 'optimal':
            g = greedy_fixed(inst, committed)
            if g is not None:
                pc = OnlinePartialCertificate(
                    inst, committed, g[0], g[1],
                    lower_bound(inst), state={'lb_mode': 'global'})
                if pc.audit_rdf():
                    cert_ok += 1
                else:
                    cert_fail += 1
        buffer.remove(j)
        if nxt < n:
            buffer.append(order[nxt])
            nxt += 1
    for i in range(n):
        if starts[i] is None:
            return dict(ok=False, reason='incomplete', starts=starts,
                        machine=mach, states=states)
    c = cmax(inst, starts)
    ok = check_schedule(inst, c, starts, mach)
    return dict(ok=ok, starts=starts, machine=mach, opt=c,
                calls=calls, lp=lp, nodes=nodes, cert_lp=cert_lp,
                states=states, cert_ok=cert_ok, cert_fail=cert_fail,
                proof_ok=sum(1 for s in states if s.get('proof_ok')),
                bound_ok=sum(1 for s in states if s.get('bound_ok')),
                full_proof=full_proof,
                t=round(time.time() - t0, 4),
                exact_all=all(s.get('exact') for s in states))
