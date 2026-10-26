"""Certified hull-energetic consistency for fixed-horizon scheduling.

The abstract state is a vector of start-time sets D_i.  Two transfer
functions are iterated to a fixpoint:

  * precedence hull propagation on every edge;
  * energetic pruning on every machine subset and every interval.

The energy test uses only the interval hull [min D_j, max D_j] of each
other job.  It is therefore a convex-hull (outer) relaxation, and every
removed value is a valid domain cut x_{i,t}=0.  If a domain becomes
empty the event log is a replayable NO(h) certificate.
"""
import sys

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from po import heads_tails


def overlap(s, p, a, b):
    lo = s if s > a else a
    hi = s + p if s + p < b else b
    return hi - lo if hi > lo else 0


def hull_min_overlap(r, u, p, a, b):
    v = b - a
    if p < v:
        v = p
    if r + p - a < v:
        v = r + p - a
    if b - u < v:
        v = b - u
    return v if v > 0 else 0


def _machine_subsets(inst):
    n, m, elig = inst['n'], inst['m'], inst['elig']
    sets = [set(e) for e in elig]
    out = []
    for mask in range(1, 1 << m):
        K = {k for k in range(m) if (mask >> k) & 1}
        J = [i for i in range(n) if sets[i] <= K]
        if J:
            out.append((mask, len(K), J))
    return out


def _endpoints(D, p, h, J):
    E = {0, h}
    for j in J:
        d = D[j]
        r = min(d)
        u = max(d)
        for v in (r, u, r + p[j], u + p[j]):
            if 0 <= v <= h:
                E.add(v)
    return sorted(E)


def propagate(inst, h, use_prec=True, use_energy=True):
    """Run hull-energetic consistency.  Returns (D, info).

    D is None iff the fixpoint proves NO(h).  info['events'] is a replay
    log; info['initial_empty'] is set when the initial window is empty.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    D = []
    for i in range(n):
        lo = est[i]
        hi = h - q[i] - p[i]
        if lo > hi:
            return None, dict(empty=True, initial_empty=i,
                              events=[], iters=0)
        D.append(set(range(lo, hi + 1)))
    subsets = _machine_subsets(inst) if use_energy else []
    events = []
    it = 0
    while True:
        it += 1
        changed = 0
        if use_prec:
            for i in range(n):
                if not D[i]:
                    return None, dict(empty=True, reason=('prec', i),
                                      events=events, iters=it)
                for j in inst['succ'][i]:
                    if not D[j]:
                        return None, dict(empty=True, reason=('prec', j),
                                          events=events, iters=it)
                    lo = min(D[i]) + p[i]
                    if lo > max(D[j]):
                        return None, dict(empty=True,
                                          reason=('prec', i, j),
                                          events=events, iters=it)
                    rem = [t for t in D[j] if t < lo]
                    if rem:
                        D[j].difference_update(rem)
                        for t in rem:
                            events.append(('p', j, t, i))
                        changed += len(rem)
                    hi = max(D[j]) - p[i]
                    rem = [t for t in D[i] if t > hi]
                    if rem:
                        D[i].difference_update(rem)
                        for t in rem:
                            events.append(('p', i, t, j))
                        changed += len(rem)
                    if not D[i] or not D[j]:
                        return None, dict(empty=True,
                                          reason=('prec', i, j),
                                          events=events, iters=it)
        if use_energy:
            for mask, cap, J in subsets:
                E = _endpoints(D, p, h, J)
                ints = [(E[u], E[v]) for u in range(len(E))
                        for v in range(u + 1, len(E))]
                theta = {}
                for j in J:
                    d = D[j]
                    r = min(d)
                    u = max(d)
                    pj = p[j]
                    theta[j] = [hull_min_overlap(r, u, pj, a, b)
                                for a, b in ints]
                tot = [0] * len(ints)
                for j in J:
                    tj = theta[j]
                    for q in range(len(ints)):
                        tot[q] += tj[q]
                for i in J:
                    ti = theta[i]
                    pi = p[i]
                    for t in list(D[i]):
                        hit = None
                        for q, (a, b) in enumerate(ints):
                            total = tot[q] - ti[q] + overlap(t, pi, a, b)
                            if total > cap * (b - a):
                                hit = (a, b)
                                break
                        if hit is not None:
                            D[i].discard(t)
                            events.append(('e', i, t, mask, hit[0], hit[1]))
                            changed += 1
                        if not D[i]:
                            return None, dict(empty=True,
                                              reason=('energy', i, t),
                                              events=events, iters=it)
        if not changed:
            break
        if it > 2 * n * (h + 1) + 8:
            break
    return D, dict(empty=False, events=events, iters=it,
                   sizes=[len(d) for d in D])


class EhcProof(Proof):
    """Replayable NO(h) certificate from the hull-energetic fixpoint."""

    kind = 'ehc'

    def __init__(self, inst, h, events, initial_empty=None):
        super().__init__(inst, h)
        self.events = list(events)
        self.initial_empty = initial_empty

    def audit_rdf(self):
        try:
            n, m, p = self.inst['n'], self.inst['m'], self.inst['p']
            h = self.h
            est, q = heads_tails(self.inst, 0, [0] * n)
            if self.initial_empty is not None:
                i = self.initial_empty
                return est[i] > h - q[i] - p[i]
            D = []
            for i in range(n):
                lo = est[i]
                hi = h - q[i] - p[i]
                if lo > hi:
                    return False
                D.append(set(range(lo, hi + 1)))
            succ = [set(s) for s in self.inst['succ']]
            elig = [set(e) for e in self.inst['elig']]
            for ev in self.events:
                if ev[0] == 'p':
                    _, i, t, src = ev
                    if t not in D[i]:
                        continue
                    if src in succ[i]:
                        if not D[src]:
                            return True
                        if not t > max(D[src]) - p[i]:
                            return False
                    elif i in succ[src]:
                        if not D[src]:
                            return True
                        if not t < min(D[src]) + p[src]:
                            return False
                    else:
                        return False
                    D[i].discard(t)
                elif ev[0] == 'e':
                    _, i, t, mask, a, b = ev
                    if t not in D[i]:
                        continue
                    K = {k for k in range(m) if (mask >> k) & 1}
                    if not K or not (0 <= a < b <= h):
                        return False
                    J = [j for j in range(n) if elig[j] <= K]
                    if i not in J:
                        return False
                    total = overlap(t, p[i], a, b)
                    for j in J:
                        if j == i:
                            continue
                        if not D[j]:
                            return True
                        total += hull_min_overlap(min(D[j]), max(D[j]),
                                                  p[j], a, b)
                    if total <= len(K) * (b - a):
                        return False
                    D[i].discard(t)
                else:
                    return False
                if not D[i]:
                    return True
            return any(not d for d in D)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()
