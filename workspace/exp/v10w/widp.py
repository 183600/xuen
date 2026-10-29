"""v10.0 WIDP: width-parameterized ideal-lattice DP with DP certificates.

The exact fixed-h decision problem is embedded in the ideal lattice of the
precedence poset.  A state at ideal C is

    (tau, rel)

where tau[k] is the first free time of machine k and rel[j] is the
largest finish time among the predecessors of j already in C.  Adding a
ready job i on an eligible machine k at

    s = max(tau[k], rel[i]),  f = s + p_i

is a sound and complete divide-and-conquer step over topological cuts:
every schedule can be linearized by nondecreasing start times, and the
state at each cut retains exactly the interface needed by the future.

For fixed h the DP table is itself a NO certificate: the stored Pareto
frontier at every ideal is closed under all legal transitions, starts at
the initial state, and the full ideal is absent.  A checker verifies this
without trusting the generator's search order.
"""
import sys
import time

sys.path[:0] = ['exp/v10w', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from rdf import check_schedule


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def prep(inst):
    n = inst['n']
    pm = [0] * n
    sm = [0] * n
    for i in range(n):
        for j in inst['pred'][i]:
            pm[i] |= 1 << j
        for j in inst['succ'][i]:
            sm[i] |= 1 << j
    tail = [0] * n
    indeg = [len(inst['pred'][i]) for i in range(n)]
    order = []
    stack = [i for i in range(n) if indeg[i] == 0]
    while stack:
        i = stack.pop()
        order.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                stack.append(j)
    for i in reversed(order):
        tail[i] = inst['p'][i] + max([tail[j] for j in inst['succ'][i]]
                                     or [0])
    return pm, sm, tail, order


def width(inst):
    """Maximum antichain of the precedence DAG (Dilworth + matching)."""
    n = inst['n']
    reach = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in inst['succ'][i]:
            reach[i][j] = True
    for k in range(n):
        for i in range(n):
            if reach[i][k]:
                rk = reach[k]
                ri = reach[i]
                for j in range(n):
                    if rk[j]:
                        ri[j] = True
    adj = [[j for j in range(n) if reach[i][j]] for i in range(n)]
    match = [-1] * n

    def dfs(u, seen):
        for v in adj[u]:
            if v in seen:
                continue
            seen.add(v)
            if match[v] < 0 or dfs(match[v], seen):
                match[v] = u
                return True
        return False

    mm = 0
    for u in range(n):
        if dfs(u, set()):
            mm += 1
    return n - mm


def ideals(inst):
    """Enumerate predecessor-closed sets by increasing cardinality."""
    n = inst['n']
    pm = [0] * n
    for i in range(n):
        for j in inst['pred'][i]:
            pm[i] |= 1 << j
    out = {0}
    frontier = [0]
    while frontier:
        C = frontier.pop()
        for i in range(n):
            if (C >> i) & 1:
                continue
            if pm[i] & ~C:
                continue
            D = C | (1 << i)
            if D not in out:
                out.add(D)
                frontier.append(D)
    return out


def dominates(a, b):
    return (all(x <= y for x, y in zip(a[0], b[0]))
            and all(x <= y for x, y in zip(a[1], b[1])))


def _add_pareto(arr, st):
    for x in arr:
        if dominates(x, st):
            return False
    arr[:] = [x for x in arr if not dominates(st, x)]
    arr.append(st)
    return True


def _transition(inst, h, C, tau, rel, i, k, symmetric):
    p = inst['p'][i]
    s = max(tau[k], rel[i])
    f = s + p
    if f > h:
        return None
    nt = list(tau)
    nt[k] = f
    if symmetric:
        nt = tuple(sorted(nt))
    else:
        nt = tuple(nt)
    nC = C | (1 << i)
    nr = list(rel)
    sm = inst['succ'][i]
    for j in sm:
        if (nC >> j) & 1:
            continue
        if f > nr[j]:
            nr[j] = f
    nr[i] = 0
    return nC, nt, tuple(nr), s, f


def _machine_options(inst, tau, i, symmetric):
    if symmetric:
        seen = set()
        out = []
        for k in range(inst['m']):
            if tau[k] in seen:
                continue
            seen.add(tau[k])
            out.append(k)
        return out
    return list(inst['elig'][i])


class WIDPProof(Proof):
    """A fixed-h NO certificate: closed Pareto frontiers on ideals."""

    kind = 'widp-no'

    def __init__(self, inst, h, frontiers, symmetric=False):
        super().__init__(inst, h)
        self.frontiers = frontiers
        self.symmetric = bool(symmetric)

    def audit_rdf(self):
        try:
            n, m = self.inst['n'], self.inst['m']
            full = (1 << n) - 1
            if not isinstance(self.h, int) or self.h < 0:
                return False
            if full in self.frontiers and self.frontiers[full]:
                return False
            if not self.frontiers.get(0):
                return False
            if ((0,) * m, (0,) * n) not in self.frontiers[0]:
                return False
            pm, sm, tail, _ = prep(self.inst)
            for C, states in self.frontiers.items():
                if C < 0 or C > full:
                    return False
                if not states:
                    continue
                rem = full ^ C
                remp = sum(self.inst['p'][j] for j in range(n)
                           if (rem >> j) & 1)
                for tau, rel in states:
                    if len(tau) != m or len(rel) != n:
                        return False
                    if any(x < 0 or x > self.h for x in tau):
                        return False
                    if any(x < 0 or x > self.h for x in rel):
                        return False
                    # capacity lower bound used by the generator
                    if sum(self.h - tau[k] for k in range(m)) < remp:
                        continue
                    # critical-path lower bound used by the generator
                    if max((rel[j] + tail[j] for j in range(n)
                            if (rem >> j) & 1), default=0) > self.h:
                        continue
                    for i in range(n):
                        if (rem >> i) & 1 == 0:
                            continue
                        if pm[i] & ~C:
                            continue
                        for k in _machine_options(self.inst, tau, i,
                                                  self.symmetric):
                            if k not in self.inst['elig'][i]:
                                return False
                            tr = _transition(self.inst, self.h, C, tau,
                                             rel, i, k, self.symmetric)
                            if tr is None:
                                continue
                            nC, nt, nr, _, _ = tr
                            # a child that the generator pruned by a
                            # lower bound is dead; no frontier entry needed
                            nrem = full ^ nC
                            nremp = sum(self.inst['p'][j]
                                        for j in range(n)
                                        if (nrem >> j) & 1)
                            if sum(self.h - nt[q] for q in range(m)) < nremp:
                                continue
                            if max((nr[j] + tail[j] for j in range(n)
                                    if (nrem >> j) & 1), default=0) > self.h:
                                continue
                            child = self.frontiers.get(nC)
                            if not child:
                                return False
                            if not any(dominates(x, (nt, nr))
                                       for x in child):
                                return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def decide(inst, h, state_cap=200000, max_seconds=20.0,
           return_proof=True):
    """Three-valued fixed-h decision by ideal-lattice DP.

    Returns dict(verdict, proof, schedule, machine, states, ideals,
                 width, t, capped).
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    pm, sm, tail, _ = prep(inst)
    symmetric = all(len(set(inst['elig'][i])) == m for i in range(n))
    full = (1 << n) - 1
    init = ((0,) * m, (0,) * n)
    layers = {0: {0: [init]}}
    trace = {(0, init): None}
    total = 0
    maxlayer = 0
    capped = False
    for size in range(n):
        cur = layers.get(size, {})
        if not cur:
            continue
        for C, states in cur.items():
            total += len(states)
            maxlayer = max(maxlayer, len(states))
            if total > state_cap or time.time() - t0 > max_seconds:
                capped = True
                break
            rem = full ^ C
            ready = [i for i in range(n)
                     if (rem >> i) & 1 and (pm[i] & ~C) == 0]
            if not ready:
                continue
            remp = sum(p[i] for i in range(n) if (rem >> i) & 1)
            for tau, rel in states:
                if sum(h - tau[k] for k in range(m)) < remp:
                    continue
                lb = max((rel[j] + tail[j] for j in range(n)
                          if (rem >> j) & 1), default=0)
                if lb > h:
                    continue
                for i in ready:
                    for k in _machine_options(inst, tau, i, symmetric):
                        tr = _transition(inst, h, C, tau, rel, i, k,
                                         symmetric)
                        if tr is None:
                            continue
                        nC, nt, nr, s, f = tr
                        d = layers.setdefault(size + 1, {})
                        arr = d.setdefault(nC, [])
                        if _add_pareto(arr, (nt, nr)):
                            trace[(nC, (nt, nr))] = (C, (tau, rel), i, k, s)
        if capped:
            break
    if capped:
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    states=total, maxlayer=maxlayer, width=width(inst),
                    t=round(time.time() - t0, 5), capped=True)
    fullstates = layers.get(n, {}).get(full, [])
    if fullstates:
        goal = min(fullstates, key=lambda x: max(x[0]))
        starts = [None] * n
        machs = [None] * n
        key = (full, goal)
        while key is not None:
            prev = trace.get(key)
            if prev is None:
                break
            C, st, i, k, s = prev
            starts[i] = s
            machs[i] = k
            key = (C, st)
        if any(x is None for x in starts):
            return dict(verdict=None, proof=None, schedule=None,
                        machine=None, states=total, maxlayer=maxlayer,
                        width=width(inst), t=round(time.time() - t0, 5),
                        capped=True)
        cm = cmax(inst, starts)
        if not check_schedule(inst, h, starts, machs):
            return dict(verdict=None, proof=None, schedule=None,
                        machine=None, states=total, maxlayer=maxlayer,
                        width=width(inst), t=round(time.time() - t0, 5),
                        capped=True)
        return dict(verdict=True, proof=None, schedule=starts,
                    machine=machs, cmax=cm, states=total,
                    maxlayer=maxlayer, width=width(inst),
                    t=round(time.time() - t0, 5), capped=False)
    frontiers = {}
    for layer in layers.values():
        for C, states in layer.items():
            frontiers.setdefault(C, []).extend(states)
    proof = WIDPProof(inst, h, frontiers, symmetric=symmetric) \
        if return_proof else None
    ok = bool(proof is not None and proof.audit_rdf())
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                states=total, maxlayer=maxlayer, width=width(inst),
                t=round(time.time() - t0, 5), capped=False, audit=ok)


if __name__ == '__main__':
    import json
    cases = json.load(open('exp/v10c/gap_cases.json'))
    for x in cases:
        inst = x['inst']
        for h in (x['opt'] - 1, x['opt']):
            t0 = time.time()
            r = decide(inst, h)
            print(x['case'], h, r['verdict'], r['states'],
                  r.get('width'), round(time.time() - t0, 4),
                  r.get('audit'), flush=True)
