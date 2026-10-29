"""v9.3 EHC-2: certified hull-energetic kernelization.

This module extends the v9h prototype in three ways:

  * terminal precedence events are logged, so every NO proof is replayable;
  * reduction plans can be budgeted (energy checks) and ordered by a
    synthesis policy;
  * the event log can be greedily minimized into a small reduction kernel.

The state is a vector of start-time domains D_i.  Each event removes one
value from one domain and carries a local, independently checkable
justification.  A precedence terminal event or an empty domain is a
complete NO(h) certificate.
"""
import sys
import time

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


def _machine_subsets(inst, mode='all'):
    """Machine subsets used by the energy rule.

    mode='all'    : every nonempty mask with at least one eligible job
    mode='global' : only the full machine set
    mode='single' : singleton masks plus the full set
    mode='elig'   : distinct eligibility masks plus the full set
    """
    n, m, elig = inst['n'], inst['m'], inst['elig']
    sets = [set(e) for e in elig]
    masks = []
    full = (1 << m) - 1
    if mode == 'global':
        masks = [full]
    elif mode == 'single':
        masks = [1 << k for k in range(m)] + [full]
    elif mode == 'elig':
        masks = sorted({sum(1 << k for k in e) for e in elig} | {full})
    else:
        masks = list(range(1, 1 << m))
    out = []
    seen = set()
    for mask in masks:
        if mask in seen:
            continue
        seen.add(mask)
        K = {k for k in range(m) if (mask >> k) & 1}
        J = [i for i in range(n) if sets[i] <= K]
        if J:
            out.append((mask, len(K), J))
    return out


def _endpoints(D, p, h, J):
    E = {0, h}
    for j in J:
        d = D[j]
        if not d:
            continue
        r = min(d)
        u = max(d)
        for v in (r, u, r + p[j], u + p[j]):
            if 0 <= v <= h:
                E.add(v)
    return sorted(E)


def initial_domains(inst, h):
    """Initial sound start-time domains for horizon h, or None."""
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    D = []
    for i in range(n):
        lo = est[i]
        hi = h - q[i] - p[i]
        if lo > hi:
            return None
        D.append(set(range(lo, hi + 1)))
    return D


def propagate(inst, h, use_prec=True, use_energy=True,
              energy_mode='all', max_energy_checks=None, max_iters=None,
              stop_on_empty=True):
    """Run hull-energetic consistency to a fixpoint or a budget.

    Returns (D, info).  D is None iff the reduction proves NO(h).
    A partial reduction is returned as a list of nonempty domains;
    info['events'] is always a valid replay log for the reduction done.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    D = initial_domains(inst, h)
    if D is None:
        est, q = heads_tails(inst, 0, [0] * n)
        i = next(i for i in range(n)
                 if est[i] > h - q[i] - p[i])
        return None, dict(empty=True, initial_empty=i, events=[],
                          iters=0, energy_checks=0, budget_hit=False,
                          t=time.time() - t0)
    subsets = _machine_subsets(inst, energy_mode) if use_energy else []
    events = []
    it = 0
    checks = 0
    budget_hit = False
    while True:
        it += 1
        changed = 0
        if use_prec:
            for i in range(n):
                if not D[i]:
                    return None, dict(empty=True, reason=('prec', i),
                                      events=events, iters=it,
                                      energy_checks=checks,
                                      budget_hit=budget_hit,
                                      t=time.time() - t0)
                for j in inst['succ'][i]:
                    if not D[j]:
                        return None, dict(empty=True, reason=('prec', j),
                                          events=events, iters=it,
                                          energy_checks=checks,
                                          budget_hit=budget_hit,
                                          t=time.time() - t0)
                    lo = min(D[i]) + p[i]
                    if lo > max(D[j]):
                        events.append(('x', i, j, 'succ'))
                        return None, dict(empty=True,
                                          reason=('prec', i, j),
                                          events=events, iters=it,
                                          energy_checks=checks,
                                          budget_hit=budget_hit,
                                          t=time.time() - t0)
                    rem = [t for t in D[j] if t < lo]
                    if rem:
                        D[j].difference_update(rem)
                        for t in rem:
                            events.append(('p', j, t, i))
                        changed += len(rem)
                    hi = max(D[j]) - p[i]
                    if min(D[i]) > hi:
                        events.append(('x', i, j, 'pred'))
                        return None, dict(empty=True,
                                          reason=('prec', i, j),
                                          events=events, iters=it,
                                          energy_checks=checks,
                                          budget_hit=budget_hit,
                                          t=time.time() - t0)
                    rem = [t for t in D[i] if t > hi]
                    if rem:
                        D[i].difference_update(rem)
                        for t in rem:
                            events.append(('p', i, t, j))
                        changed += len(rem)
                    if not D[i] or not D[j]:
                        if not D[i]:
                            events.append(('z', i))
                        else:
                            events.append(('z', j))
                        return None, dict(empty=True,
                                          reason=('prec', i, j),
                                          events=events, iters=it,
                                          energy_checks=checks,
                                          budget_hit=budget_hit,
                                          t=time.time() - t0)
        if use_energy and not budget_hit:
            for mask, cap, J in subsets:
                E = _endpoints(D, p, h, J)
                ints = [(E[u], E[v]) for u in range(len(E))
                        for v in range(u + 1, len(E))]
                theta = {}
                for j in J:
                    d = D[j]
                    if not d:
                        events.append(('z', j))
                        return None, dict(empty=True, reason=('prec', j),
                                          events=events, iters=it,
                                          energy_checks=checks,
                                          budget_hit=budget_hit,
                                          t=time.time() - t0)
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
                        if max_energy_checks is not None \
                                and checks >= max_energy_checks:
                            budget_hit = True
                            break
                        hit = None
                        for q, (a, b) in enumerate(ints):
                            checks += 1
                            total = tot[q] - ti[q] + overlap(t, pi, a, b)
                            if total > cap * (b - a):
                                hit = (a, b)
                                break
                        if hit is not None:
                            D[i].discard(t)
                            events.append(('e', i, t, mask, hit[0], hit[1]))
                            changed += 1
                        if not D[i]:
                            events.append(('z', i))
                            return None, dict(empty=True,
                                              reason=('energy', i, t),
                                              events=events, iters=it,
                                              energy_checks=checks,
                                              budget_hit=budget_hit,
                                              t=time.time() - t0)
                    if budget_hit:
                        break
                if budget_hit:
                    break
        if not changed:
            break
        if max_iters is not None and it >= max_iters:
            break
        if it > n * (h + 1) + 8:
            break
    return D, dict(empty=False, events=events, iters=it,
                   sizes=[len(d) for d in D], energy_checks=checks,
                   budget_hit=budget_hit, t=time.time() - t0)


def _replay(inst, h, events, initial_empty=None):
    """Replay a reduction log.  Returns (D, proved_empty)."""
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    if initial_empty is not None:
        i = initial_empty
        return None, bool(est[i] > h - q[i] - p[i])
    D = []
    for i in range(n):
        lo = est[i]
        hi = h - q[i] - p[i]
        if lo > hi:
            return None, False
        D.append(set(range(lo, hi + 1)))
    succ = [set(s) for s in inst['succ']]
    elig = [set(e) for e in inst['elig']]
    for ev in events:
        tag = ev[0]
        if tag == 'p':
            _, i, t, src = ev
            if t not in D[i]:
                continue
            if src in succ[i]:
                if not D[src]:
                    return None, True
                if not t > max(D[src]) - p[i]:
                    return None, False
            elif i in succ[src]:
                if not D[src]:
                    return None, True
                if not t < min(D[src]) + p[src]:
                    return None, False
            else:
                return None, False
            D[i].discard(t)
        elif tag == 'e':
            _, i, t, mask, a, b = ev
            if t not in D[i]:
                continue
            K = {k for k in range(m) if (mask >> k) & 1}
            if not K or not (0 <= a < b <= h):
                return None, False
            J = [j for j in range(n) if elig[j] <= K]
            if i not in J:
                return None, False
            total = overlap(t, p[i], a, b)
            for j in J:
                if j == i:
                    continue
                if not D[j]:
                    return None, True
                total += hull_min_overlap(min(D[j]), max(D[j]),
                                          p[j], a, b)
            if total <= len(K) * (b - a):
                return None, False
            D[i].discard(t)
        elif tag == 'x':
            _, i, j, side = ev
            if not D[i] or not D[j]:
                return None, True
            if side == 'succ':
                if not min(D[i]) + p[i] > max(D[j]):
                    return None, False
            elif side == 'pred':
                if not min(D[i]) > max(D[j]) - p[i]:
                    return None, False
            else:
                return None, False
            return None, True
        elif tag == 'z':
            _, i = ev
            if D[i]:
                return None, False
            return None, True
        else:
            return None, False
        if not D[i]:
            return None, True
    return D, any(not d for d in D)


class EhcProof(Proof):
    """Replayable NO(h) certificate from a hull-energetic reduction."""

    kind = 'ehc2'

    def __init__(self, inst, h, events, initial_empty=None):
        super().__init__(inst, h)
        self.events = list(events)
        self.initial_empty = initial_empty

    def audit_rdf(self):
        try:
            D, empty = _replay(self.inst, self.h, self.events,
                               self.initial_empty)
            return bool(empty)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class ReducedNOProof(Proof):
    """NO(h) obtained after a certified domain reduction.

    The reduction events justify removing a set F of start-time values.
    The inner proof is a NO(h) proof for a domain that forbids at most F;
    it therefore also proves NO(h) for the reduced domain.  This object
    deliberately exposes no root forbids, because its justifications are
    the replayable reduction events rather than a frontier box.
    """

    kind = 'ehc2-reduced'
    forbid0 = frozenset()

    def __init__(self, inst, h, events, inner, initial_empty=None):
        super().__init__(inst, h)
        self.events = list(events)
        self.inner = inner
        self.initial_empty = initial_empty

    def audit_rdf(self):
        try:
            D, empty = _replay(self.inst, self.h, self.events,
                               self.initial_empty)
            if empty or D is None:
                return False
            init = initial_domains(self.inst, self.h)
            if init is None:
                return False
            F = frozenset((i, t) for i in range(self.inst['n'])
                          for t in init[i] if t not in D[i])
            inner_forbid = frozenset(getattr(self.inner, 'forbid0',
                                             frozenset()))
            if not inner_forbid <= F:
                return False
            return bool(self.inner is not None
                        and self.inner.h == self.h
                        and self.inner.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def minimize_events(inst, h, events, initial_empty=None):
    """Greedily delete events while the log still proves NO(h).

    The result is an inclusion-minimal reduction kernel for this replay
    order.  Energy events remain valid when other removals are dropped
    because hull overlap is monotone in the domain hull; precedence events
    are rechecked by the replay.  Dropping events can therefore only make
    later justifications harder, never easier.
    """
    if initial_empty is not None:
        return []
    keep = list(events)
    if not EhcProof(inst, h, keep).audit_rdf():
        return keep
    changed = True
    while changed:
        changed = False
        for i in range(len(keep) - 1, -1, -1):
            cand = keep[:i] + keep[i + 1:]
            if EhcProof(inst, h, cand).audit_rdf():
                keep = cand
                changed = True
                break
    return keep


def reduce_domains(inst, h, events, initial_empty=None):
    """Return the reduced domains after a replay, or None if NO(h)."""
    D, empty = _replay(inst, h, events, initial_empty)
    return None if empty else D


def removed_literals(inst, h, D):
    """Start-time literals removed by a sound reduction."""
    init = initial_domains(inst, h)
    if init is None:
        return frozenset()
    return frozenset((i, t) for i in range(inst['n'])
                     for t in init[i] if t not in D[i])
