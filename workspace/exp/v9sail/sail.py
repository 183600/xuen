"""v9.1 SAIL-ICF: simulated-annealing primal search + DSU evidence closure.

The v9.0 ICF state is

    (L, U, s, m, pi),   pi : NO(L-1),   Cmax(s)=U,   L <= U.

SAIL keeps that invariant and adds two randomized/union-find layers:

1.  A Las Vegas primal search.  A priority order is decoded into a
    feasible schedule by an earliest-fit serial schedule generator whose
    slot allocation is a successor DSU.  Simulated annealing explores
    topological priority orders; a proposal is accepted only after
    check_schedule.  A hit at the certified lower bound L closes the
    bracket with no oracle call.

2.  A union-find evidence closure.  NO(h) is a downward-closed piece of
    evidence, YES(h) an upward-closed one.  The closure merges arbitrary
    batches of evidence and returns the strongest bracket.  The oracle
    and the annealer feed the same closure, so their certificates can be
    merged in any order.

Everything the annealer produces is checked; everything the oracle
produces is audited.  Randomness affects speed only, never soundness.
"""
import sys
import time
import math
import random
import heapq
import bisect
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import check_schedule
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h,
                 corpora)


# --------------------------------------------------------------- DSU slots
class SlotDSU:
    """Successor structure for occupied time slots on one machine.

    Each occupied run is a DSU component.  The root stores the first free
    slot after the run.  find/union use path compression and union by
    size, so a placement costs O(alpha(H)) amortized per occupied slot.
    """

    __slots__ = ('H', 'occ', 'parent', 'size', 'nxt', 'unions', 'finds')

    def __init__(self, H):
        self.H = int(H)
        self.occ = [False] * (self.H + 2)
        self.parent = list(range(self.H + 2))
        self.size = [1] * (self.H + 2)
        self.nxt = list(range(1, self.H + 3))
        self.unions = 0
        self.finds = 0

    def find(self, x):
        self.finds += 1
        parent = self.parent
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        if self.nxt[rb] > self.nxt[ra]:
            self.nxt[ra] = self.nxt[rb]
        self.unions += 1
        return ra

    def occupy(self, x):
        if self.occ[x]:
            return
        self.occ[x] = True
        if x > 0 and self.occ[x - 1]:
            self.union(x - 1, x)
        if x + 1 <= self.H and self.occ[x + 1]:
            self.union(x, x + 1)

    def succ(self, x):
        if x > self.H:
            return self.H + 1
        if not self.occ[x]:
            return x
        return self.nxt[self.find(x)]

    def find_block(self, release, p):
        """Earliest t >= release with [t, t+p) free, or None."""
        if release < 0:
            release = 0
        t = self.succ(release)
        while t + p <= self.H:
            d = 0
            while d < p and not self.occ[t + d]:
                d += 1
            if d == p:
                return t
            t = self.succ(t + d)
        return None

    def place(self, t, p):
        for x in range(t, t + p):
            self.occupy(x)


# --------------------------------------------------------------- decoders
def _earliest_fit(busy, base, p):
    t = base
    for a, b in busy:
        if t + p <= a:
            break
        if t < b:
            t = b
    return t


def decode_interval(order, inst, H):
    """Reference decoder: sorted busy intervals, no DSU."""
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, elig = inst['pred'], inst['elig']
    s = [0] * n
    mach = [-1] * n
    busy = [[] for _ in range(m)]
    for i in order:
        rel = 0
        for j in pred[i]:
            v = s[j] + p[j]
            if v > rel:
                rel = v
        best = None
        for k in elig[i]:
            t = _earliest_fit(busy[k], rel, p[i])
            key = (t + p[i], t, k)
            if best is None or key < best[0]:
                best = (key, t, k)
        if best is None:
            return None
        _, t, k = best
        s[i] = t
        mach[i] = k
        bisect.insort(busy[k], (t, t + p[i]))
    c = max(s[i] + p[i] for i in range(n))
    return s, mach, c


def decode_dsu(order, inst, H):
    """Earliest-fit decoder with one successor DSU per machine."""
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, elig = inst['pred'], inst['elig']
    s = [0] * n
    mach = [-1] * n
    alloc = [SlotDSU(H) for _ in range(m)]
    for i in order:
        rel = 0
        for j in pred[i]:
            v = s[j] + p[j]
            if v > rel:
                rel = v
        best = None
        for k in elig[i]:
            t = alloc[k].find_block(rel, p[i])
            if t is None:
                continue
            key = (t + p[i], t, k)
            if best is None or key < best[0]:
                best = (key, t, k)
        if best is None:
            return None
        _, t, k = best
        s[i] = t
        mach[i] = k
        alloc[k].place(t, p[i])
    c = max(s[i] + p[i] for i in range(n))
    return s, mach, c


# --------------------------------------------------------------- order
def topo_order(keys, inst):
    n, pred, succ = inst['n'], inst['pred'], inst['succ']
    indeg = [len(pred[i]) for i in range(n)]
    h = [(keys[i], i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(h)
    out = []
    while h:
        _, i = heapq.heappop(h)
        out.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(h, (keys[j], j))
    return out


def schedule_order(sched, inst, rng=None):
    """A topological order that follows the incumbent start times."""
    n = inst['n']
    if rng is None:
        keys = [float(sched[i]) + 1e-6 * i for i in range(n)]
    else:
        keys = [float(sched[i]) + rng.random() * 0.5 for i in range(n)]
    return topo_order(keys, inst)


# --------------------------------------------------------------- SA
class SAStats:
    __slots__ = ('decodes', 'iters', 'restarts', 'best', 'hit',
                 'first_hit_iter', 'time', 'dsu_unions', 'dsu_finds',
                 'greedy_hit', 'initial_c')

    def __init__(self):
        self.decodes = 0
        self.iters = 0
        self.restarts = 0
        self.best = None
        self.hit = False
        self.first_hit_iter = None
        self.time = 0.0
        self.dsu_unions = 0
        self.dsu_finds = 0
        self.greedy_hit = False
        self.initial_c = None

    def as_dict(self):
        return dict(decodes=self.decodes, iters=self.iters,
                    restarts=self.restarts, best=self.best,
                    hit=bool(self.hit),
                    first_hit_iter=self.first_hit_iter,
                    time=round(self.time, 6),
                    dsu_unions=self.dsu_unions,
                    dsu_finds=self.dsu_finds,
                    greedy_hit=bool(self.greedy_hit),
                    initial_c=self.initial_c)


def anneal(inst, init_s, init_c, target, iters=1500, restarts=2,
           seed=0, T0=None, T_end=0.05, restart_mode='best',
           decoder=decode_dsu):
    """Simulated annealing over topological priority orders.

    Returns (s, m, c, stats).  Every returned schedule is feasible; the
    caller still verifies it.  target is a certified lower bound: a hit
    means the bracket closes.
    """
    t_start = time.time()
    st = SAStats()
    st.initial_c = int(init_c)
    rng = random.Random(seed)
    n = inst['n']
    p = inst['p']
    H = max(1, sum(p))
    best_s = list(init_s) if init_s is not None else None
    best_c = int(init_c)
    best_m = None
    if best_s is not None:
        # recover a machine vector by replaying the incumbent order
        order = schedule_order(best_s, inst, rng)
        res = decoder(order, inst, H)
        st.decodes += 1
        if res is not None:
            s, mm, c = res
            st.dsu_unions += 0
            st.dsu_finds += 0
            if c < best_c:
                best_s, best_m, best_c = s, mm, c
            if best_c <= target:
                st.best = best_c
                st.hit = True
                st.greedy_hit = True
                st.first_hit_iter = 0
                st.time = time.time() - t_start
                return best_s, best_m, best_c, st

    base_keys = ([float(init_s[i]) + rng.random() * 0.5
                  for i in range(n)] if init_s is not None
                 else [rng.random() for _ in range(n)])
    per = max(1, iters // max(1, restarts))
    for r in range(max(1, restarts)):
        st.restarts = r + 1
        if r == 0:
            keys = base_keys[:]
        elif restart_mode == 'random':
            keys = [rng.random() for _ in range(n)]
        elif restart_mode == 'best' and best_s is not None:
            keys = [float(best_s[i]) + rng.random() * 0.5
                    for i in range(n)]
        else:
            keys = [rng.random() for _ in range(n)]
        order = topo_order(keys, inst)
        res = decoder(order, inst, H)
        st.decodes += 1
        if res is None:
            continue
        s, mm, c = res
        if c < best_c:
            best_s, best_m, best_c = s, mm, c
        if best_c <= target:
            st.best = best_c
            st.hit = True
            st.first_hit_iter = st.iters
            st.time = time.time() - t_start
            return best_s, best_m, best_c, st
        T = (T0 if T0 is not None
             else max(1.0, (c - target) / max(1.0, math.log(2.0))))
        alpha = (T_end / T) ** (1.0 / per) if T > 0 else 1.0
        cur_keys = keys[:]
        cur_s, cur_m, cur_c = s, mm, c
        for it in range(per):
            st.iters += 1
            nk = cur_keys[:]
            u = rng.randrange(n)
            v = rng.randrange(n)
            if u == v:
                continue
            if rng.random() < 0.7:
                nk[u], nk[v] = nk[v], nk[u]
            else:
                nk[u] = rng.random()
            no = topo_order(nk, inst)
            res = decoder(no, inst, H)
            st.decodes += 1
            if res is None:
                continue
            ns, nm, nc = res
            if nc <= cur_c or rng.random() < math.exp(
                    -(nc - cur_c) / max(1e-9, T)):
                cur_keys, cur_s, cur_m, cur_c = nk, ns, nm, nc
                if nc < best_c:
                    best_s, best_m, best_c = ns, nm, nc
                    if best_c <= target:
                        st.best = best_c
                        st.hit = True
                        st.first_hit_iter = st.iters
                        st.time = time.time() - t_start
                        return best_s, best_m, best_c, st
            T *= alpha
    st.best = best_c
    st.time = time.time() - t_start
    return best_s, best_m, best_c, st


# --------------------------------------------------------------- evidence
class EvidenceDSU:
    """Union-find closure of NO (prefix) and YES (suffix) evidence.

    Horizons 0..H are points.  NO(h) marks every t <= h; YES(h) marks
    every t >= h.  Two successor DSUs absorb only the newly marked
    points, so each point is charged once over the whole run.  A second
    DSU per side contracts the absorbed interval to its strongest
    witness; the bracket is [no_top+1, yes_bottom].
    """

    def __init__(self, H):
        self.H = int(H)
        # successor DSUs over unmarked points (prefix side) and over
        # reversed points (suffix side)
        self.no_free = list(range(self.H + 2))
        self.yes_free = list(range(self.H + 2))
        # witness components
        self.no_comp = list(range(self.H + 2))
        self.yes_comp = list(range(self.H + 2))
        self.no_mark = [False] * (self.H + 2)
        self.yes_mark = [False] * (self.H + 2)
        self.no_top = -1
        self.yes_bottom = self.H + 1
        self.no_witness = {}
        self.yes_witness = {}
        self.unions = 0
        self.finds = 0
        self.absorbed = 0

    def _find(self, parent, x):
        self.finds += 1
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _find_no_free(self, x):
        return self._find(self.no_free, x)

    def _find_yes_free(self, x):
        return self._find(self.yes_free, x)

    def add_no(self, h, proof):
        """Add NO(h); weaker NO evidence (h <= no_top) is subsumed."""
        h = int(h)
        if h < 0:
            return
        if h > self.H:
            h = self.H
        if h <= self.no_top:
            return
        t = self._find_no_free(0)
        while t <= h:
            self.no_mark[t] = True
            self.no_comp[t] = h
            self.absorbed += 1
            # remove t from the unmarked successor DSU
            self.no_free[t] = self._find_no_free(t + 1)
            t = self._find_no_free(t)
        self.no_top = h
        self.no_comp[h] = h
        self.no_witness[h] = (h, proof)
        self.unions += 1

    def add_yes(self, h, sched, mach):
        """Add YES(h); weaker YES evidence (h >= yes_bottom) is subsumed."""
        h = int(h)
        if h < 0:
            h = 0
        if h > self.H:
            h = self.H
        if h >= self.yes_bottom:
            return
        # reversed coordinate r = H - t; the suffix [h,H] is the
        # prefix [0,H-h] in reversed coordinates.
        rmax = self.H - h
        r = self._find_yes_free(0)
        while r <= rmax:
            t = self.H - r
            self.yes_mark[t] = True
            self.yes_comp[t] = h
            self.absorbed += 1
            self.yes_free[r] = self._find_yes_free(r + 1)
            r = self._find_yes_free(r)
        self.yes_bottom = h
        self.yes_comp[h] = h
        self.yes_witness[h] = (h, sched, mach)
        self.unions += 1

    def bracket(self):
        return self.no_top + 1, self.yes_bottom

    def gap(self):
        L, U = self.bracket()
        return U - L

    def audit(self, inst):
        try:
            L, U = self.bracket()
            if L > U:
                return False
            if self.no_top >= 0:
                h, proof = self.no_witness[self.no_top]
                if h != self.no_top or proof is None:
                    return False
                if getattr(proof, 'h', None) != h:
                    return False
                if not proof.audit_rdf():
                    return False
                # every point <= no_top is absorbed by this component
                if not all(self.no_mark[:self.no_top + 1]):
                    return False
            if self.yes_bottom <= self.H:
                h, sched, mach = self.yes_witness[self.yes_bottom]
                if h != self.yes_bottom or sched is None:
                    return False
                c = cmax(inst, sched)
                if c > h or not check_schedule(inst, h, sched, mach):
                    return False
                if not all(self.yes_mark[self.yes_bottom:self.H + 1]):
                    return False
            return True
        except Exception:
            return False


# --------------------------------------------------------------- initial
def weak_serial_schedule(inst, seed=0):
    """A deliberately weak but feasible serial schedule.

    A random topological order is placed on randomly chosen eligible
    machines without overlap.  Used to test bracket repair: the upper
    bound is far from OPT, so a primal search has room to work.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    rng = random.Random(seed)
    order = topo_order([rng.random() for _ in range(n)], inst)
    s = [0] * n
    mach = [-1] * n
    free = [0] * m
    for i in order:
        rel = 0
        for j in inst['pred'][i]:
            v = s[j] + p[j]
            if v > rel:
                rel = v
        k = rng.choice(inst['elig'][i])
        t = max(rel, free[k])
        s[i] = t
        mach[i] = k
        free[k] = t + p[i]
    return s, mach, max(s[i] + p[i] for i in range(n))


def serial_schedule(inst, order=None):
    """A feasible serial schedule, used for weak-upper-bound tests."""
    n, m, p = inst['n'], inst['m'], inst['p']
    if order is None:
        order = topo_order([0.0] * n, inst)
    s = [0] * n
    mach = [-1] * n
    free = [0] * m
    for i in order:
        rel = 0
        for j in inst['pred'][i]:
            v = s[j] + p[j]
            if v > rel:
                rel = v
        best = None
        for k in inst['elig'][i]:
            t = max(rel, free[k])
            key = (t + p[i], t, k)
            if best is None or key < best[0]:
                best = (key, t, k)
        _, t, k = best
        s[i] = t
        mach[i] = k
        free[k] = t + p[i]
    return s, mach, max(s[i] + p[i] for i in range(n))


# --------------------------------------------------------------- main
def run_sail(inst, known, name, idx, policy='lower-first',
             sa_iters=1500, sa_restarts=2, seed=0, max_probes=64,
             initial=None, use_sa=True, sa_gate=None, decoder=decode_dsu,
             restart_mode='best'):
    """Run SAIL-ICF on one instance and return a benchmark row."""
    t0 = time.time()
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None
    else:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, policy=policy,
                        ok=False, error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    Hmax = max(1, sum(inst['p']))
    closure = EvidenceDSU(Hmax)
    closure.add_no(L - 1, lb_proof)
    closure.add_yes(U, sched, mach)
    if closure.audit(inst) is False:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='initial-closure-audit', t=0.0)

    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    sa_iters_total = 0
    sa_decodes = 0
    sa_time = 0.0
    sa_hits = 0
    sa_greedy_hits = 0
    sa_improvements = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        Lc, Uc = closure.bracket()
        # strongest witnesses from the closure
        no_h, no_p = (closure.no_top, lb_proof)
        if closure.no_top >= 0:
            no_h, no_p = closure.no_witness[closure.no_top]
        yes_h, yes_s, yes_m = (Uc, sched, mach)
        if closure.yes_bottom <= Hmax:
            yes_h, yes_s, yes_m = closure.yes_witness[
                closure.yes_bottom]
        pc = PartialCertificate(inst, Lc, Uc, yes_s, yes_m, no_p,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    audit_state()
    first = True
    while closure.gap() > 0 and probes < max_probes:
        L, U = closure.bracket()
        # ---------------- primal phase: anneal at the certified L
        if use_sa and (sa_gate is None or (U - L) <= sa_gate):
            best_s, best_m, best_c, st = anneal(
                inst, sched, U, L, iters=sa_iters,
                restarts=sa_restarts, seed=seed + 1009 * probes,
                decoder=decoder, restart_mode=restart_mode)
            sa_iters_total += st.iters
            sa_decodes += st.decodes
            sa_time += st.time
            if st.greedy_hit:
                sa_greedy_hits += 1
            if best_s is not None and best_c < U:
                if check_schedule(inst, best_c, best_s, best_m):
                    closure.add_yes(best_c, best_s, best_m)
                    sched, mach = list(best_s), list(best_m)
                    sa_improvements += 1
            if closure.gap() <= 0:
                sa_hits += 1
                break
            L, U = closure.bracket()
        # ---------------- dual phase: oracle probe
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
            closure.add_no(h, proof)
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L, U0=U, L1=closure.bracket()[0],
                              U1=closure.bracket()[1]))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if check_schedule(inst, c2, s2, m2):
                closure.add_yes(c2, s2, m2)
                if c2 < U:
                    sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L, U0=U, L1=closure.bracket()[0],
                              U1=closure.bracket()[1]))
        else:
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L, U0=U, L1=closure.bracket()[0],
                              U1=closure.bracket()[1]))
            break
        audit_state()

    Lf, Uf = closure.bracket()
    no_h, no_p = (closure.no_top, lb_proof)
    if closure.no_top >= 0:
        no_h, no_p = closure.no_witness[closure.no_top]
    yes_h, yes_s, yes_m = (Uf, sched, mach)
    if closure.yes_bottom <= Hmax:
        yes_h, yes_s, yes_m = closure.yes_witness[closure.yes_bottom]
    final = ICFCertificate(inst, Uf, yes_s, yes_m, no_p) \
        if Lf == Uf else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, Lf, Uf, yes_s, yes_m, no_p,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    closure_ok = bool(closure.audit(inst))
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=Uf, lb=Lf, lb0=lb0, ub0=ub0,
        certified=bool(Lf == Uf and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(Uf - 1 if Lf == Uf else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        closure_audit=closure_ok,
        sa_iters=sa_iters_total, sa_decodes=sa_decodes,
        sa_time=round(sa_time, 6), sa_hits=sa_hits,
        sa_greedy_hits=sa_greedy_hits,
        sa_improvements=sa_improvements,
        unknown=0 if Lf == Uf else 1,
        steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(no_p, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(Lf == Uf and Uf == known and final_ok and
                partial_fail == 0 and partial_ok_final and closure_ok),
    )
