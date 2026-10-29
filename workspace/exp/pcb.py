"""X-DUB/PCB experiments (round 4).

Denotational interface states + semantic certificate front + memoized
backtracking + ant-colony guide, for P|prec|Cmax (m=2 unless stated).

Core object is the interface  iota = (R, r, A):
  R : remaining tasks (bitmask), an up-set of the precedence DAG
  r : release lower bounds induced by *scheduled* predecessors
  A : sorted machine availability vector
The scheduled completion vector c is NOT part of the state: the future
depends on it only through r.  This is the denotational quotient.

Lower-bound kernel: L0 (heads/tails + work) plus a two-family
window-packing test at a deadline H (release windows and deadline
windows), exact 2-bin packing by bitset subset-sum.
"""
import random, time, json, sys, math, heapq
from collections import defaultdict

INF = 10 ** 9


# ------------------------------------------------------------------ instances
def gen_instance(n, ep, pmax, rng, m=2):
    p = [rng.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < ep:
                pred[j].append(i)
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': ep, 'pmax': pmax}
    finish_inst(inst)
    return inst


def finish_inst(inst):
    n = inst['n']
    pmask = [0] * n
    for i in range(n):
        for j in inst['pred'][i]:
            pmask[i] |= 1 << j
    inst['pmask'] = pmask
    desc = [0] * n
    for i in range(n - 1, -1, -1):
        d = 0
        for j in inst['succ'][i]:
            d |= (1 << j) | desc[j]
        desc[i] = d
    inst['desc'] = desc
    inst['full'] = (1 << n) - 1
    # static critical tail on the full DAG (guide only)
    q = [0] * n
    for i in range(n - 1, -1, -1):
        b = 0
        for j in inst['succ'][i]:
            t = inst['p'][j] + q[j]
            if t > b:
                b = t
        q[i] = b
    inst['q_static'] = q


# ------------------------------------------------------------------ interface math
def est_q(inst, R, r):
    n, p, pred, succ = inst['n'], inst['p'], inst['pred'], inst['succ']
    est = [0] * n
    q = [0] * n
    for i in range(n):
        if not (R >> i) & 1:
            continue
        e = r[i]
        for j in pred[i]:
            if (R >> j) & 1:
                t = est[j] + p[j]
                if t > e:
                    e = t
        est[i] = e
    for i in range(n - 1, -1, -1):
        if not (R >> i) & 1:
            continue
        b = 0
        for j in succ[i]:
            if (R >> j) & 1:
                t = p[j] + q[j]
                if t > b:
                    b = t
        q[i] = b
    return est, q


def lb0(inst, R, r, A):
    if R == 0:
        return max(A)
    est, q = est_q(inst, R, r)
    n, p, m = inst['n'], inst['p'], inst['m']
    C = max(A)
    W = 0
    crit = C
    for i in range(n):
        if (R >> i) & 1:
            W += p[i]
            t = est[i] + p[i] + q[i]
            if t > crit:
                crit = t
    return max(C, crit, (W + m - 1) // m)


def packable(sizes, caps, m):
    """Return True if feasible / unknown; False only if *proved* infeasible."""
    if not sizes:
        return True
    if m == 1:
        return sum(sizes) <= caps[0]
    if m == 2:
        c1, c2 = sorted(caps, reverse=True)
        tot = sum(sizes)
        if tot > c1 + c2:
            return False
        if c1 < 0 or c2 < 0:
            return False
        bits = 1
        for s in sizes:
            bits |= bits << s
        lo = max(0, tot - c2)
        hi = c1
        if lo > hi:
            return False
        mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
        return (bits & mask) != 0
    # m >= 3: only the aggregate energy test (sound but weak)
    return sum(sizes) <= sum(caps)


def infeasible_at(inst, R, r, A, H):
    """Deadline H: is there *no* schedule of R with makespan <= H?"""
    if R == 0:
        return False
    n, p, m = inst['n'], inst['p'], inst['m']
    est, q = est_q(inst, R, r)
    Rlist = [i for i in range(n) if (R >> i) & 1]

    def test(a, b):
        caps = [max(0, b - max(a, A[k])) for k in range(m)]
        X = [p[i] for i in Rlist if est[i] >= a and H - q[i] <= b]
        if not X:
            return False
        return not packable(X, caps, m)

    # family 1: release windows [a, H)
    for a in sorted({0} | {est[i] for i in Rlist}):
        if a >= H:
            continue
        if test(a, H):
            return True
    # family 2: deadline windows [0, b)
    for b in sorted({H} | {H - q[i] for i in Rlist if 0 < H - q[i] < H}):
        if b <= 0:
            continue
        if test(0, b):
            return True
    return False


def lb_local(inst, R, r, A, U):
    v = lb0(inst, R, r, A)
    if v >= U:
        return v
    if infeasible_at(inst, R, r, A, U - 1):
        return U
    return v


def lb_ge(inst, R, r, A, h):
    """Sound test D(R,r,A) >= h using the cheap kernel."""
    if lb0(inst, R, r, A) >= h:
        return True
    if h - 1 >= max(A) and infeasible_at(inst, R, r, A, h - 1):
        return True
    return False


def children(inst, R, r, A):
    """All distinct successor interfaces, with one witness action each."""
    n, p, pmask, succ = inst['n'], inst['p'], inst['pmask'], inst['succ']
    out = {}
    for i in range(n):
        if not (R >> i) & 1:
            continue
        if pmask[i] & R:
            continue
        base = r[i]
        R2 = R & ~(1 << i)
        for k in range(len(A)):
            t = max(A[k], base)
            A2 = list(A)
            A2[k] = t + p[i]
            A2 = tuple(sorted(A2))
            r2 = list(r)
            c = t + p[i]
            for j in succ[i]:
                if (R >> j) & 1 and c > r2[j]:
                    r2[j] = c
            key = (R2, tuple(r2), A2)
            if key not in out:
                out[key] = (i, k)
    return [(key[0], key[1], key[2], act[0], act[1])
            for key, act in out.items()]


# ------------------------------------------------------------------ primal heuristics
def greedy(inst, R, r, A, rule, want_path=False):
    R, r, A = R, list(r), list(A)
    path = []
    n, p, pmask, succ, m = inst['n'], inst['p'], inst['pmask'], inst['succ'], inst['m']
    while R:
        ready = [i for i in range(n) if (R >> i) & 1 and not (pmask[i] & R)]
        if rule == 'CP':
            est, q = est_q(inst, R, r)
            i = max(ready, key=lambda x: (q[x], p[x], -x))
        elif rule == 'LPT':
            i = max(ready, key=lambda x: (p[x], -x))
        elif rule == 'MWKR':
            best = None
            for x in ready:
                w = 0
                for y in range(n):
                    if (R >> y) & 1 and (inst['desc'][x] >> y) & 1:
                        w += p[y]
                if best is None or (w, p[x]) > best[0]:
                    best = ((w, p[x]), x)
            i = best[1]
        else:
            i = max(ready, key=lambda x: (p[x], -x))
        base = r[i]
        k = min(range(m), key=lambda kk: (max(A[kk], base), kk))
        t = max(A[k], base)
        c = t + p[i]
        A[k] = c
        for j in succ[i]:
            if (R >> j) & 1 and c > r[j]:
                r[j] = c
        R &= ~(1 << i)
        path.append((i, k))
    return (max(A), tuple(path)) if want_path else max(A)


def upper_bound(inst):
    R, r, A = inst['full'], [0] * inst['n'], [0] * inst['m']
    return min(greedy(inst, R, r, A, rule) for rule in ('CP', 'LPT', 'MWKR'))


def best_primal(inst, tau=None):
    best = None
    for rule in ('CP', 'LPT', 'MWKR'):
        c, p = greedy(inst, inst['full'], [0] * inst['n'],
                      tuple([0] * inst['m']), rule, want_path=True)
        if best is None or c < best[0]:
            best = (c, p)
    return best


# ------------------------------------------------------------------ ACO guide
def canonical_r(r, R, n):
    # r restricted to R, rounded to a coarse bucket to let pheromone share
    return tuple(r[i] for i in range(n) if (R >> i) & 1)


def aco(inst, iters=12, ants=8, alpha=1.0, beta=2.0, rho=0.25, seed=0,
        elite=3):
    """Rank-based ant system on the interface quotient.  Returns
    (best_U, pheromone dict keyed by (R, A, i, k))."""
    rng = random.Random(seed)
    n, p, pmask, succ, m = inst['n'], inst['p'], inst['pmask'], inst['succ'], inst['m']
    tau = defaultdict(lambda: 1.0)
    best = upper_bound(inst)
    best_path = None
    for it in range(iters):
        sols = []
        for ant in range(ants):
            R, r, A = inst['full'], [0] * n, tuple([0] * m)
            path = []
            keys = []
            while R:
                ready = [i for i in range(n) if (R >> i) & 1 and not (pmask[i] & R)]
                cand = []
                for i in ready:
                    base = r[i]
                    for k in range(m):
                        t = max(A[k], base)
                        key = (R, A, i, k)
                        w = tau[key] ** alpha
                        eta = 1.0 / (1.0 + (t + p[i]))
                        cand.append((w * eta ** beta, i, k, key, t))
                if not cand:
                    break
                tot = sum(c[0] for c in cand)
                x = rng.random() * tot
                acc = 0.0
                pick = cand[-1]
                for c in cand:
                    acc += c[0]
                    if x <= acc:
                        pick = c
                        break
                _, i, k, key, t = pick
                c = t + p[i]
                Al = list(A)
                Al[k] = c
                A = tuple(sorted(Al))
                for j in succ[i]:
                    if (R >> j) & 1 and c > r[j]:
                        r[j] = c
                R &= ~(1 << i)
                path.append((i, k))
                keys.append(key)
            C = max(A)
            sols.append((C, keys))
            if C < best or (C == best and best_path is None):
                best = C
                best_path = path
        # evaporation
        for key in list(tau.keys()):
            tau[key] *= (1.0 - rho)
            if tau[key] < 1e-3:
                del tau[key]
        sols.sort(key=lambda z: z[0])
        for rank, (C, path) in enumerate(sols[:elite]):
            for key in path:
                tau[key] += (elite - rank) / max(1.0, C - 1.0)
    return best, best_path, dict(tau)


# ------------------------------------------------------------------ certificate front
class Box:
    __slots__ = ('R0', 'pairs', 'A0', 'h', 'pid')

    def __init__(self, R0, pairs, A0, h, pid):
        self.R0 = R0
        self.pairs = pairs          # tuple of (task, r0) for tasks in R0
        self.A0 = A0                # tuple length m
        self.h = h
        self.pid = pid


def region_superset(R1, pairs1, A1, R2, pairs2, A2):
    """Is region(box1) >= region(box2)?  region = {R>=R0, r>=r0, A>=A0}."""
    if R1 & ~R2:
        return False
    d2 = dict(pairs2)
    for i, ri in pairs1:
        v = d2.get(i)
        if v is None or v < ri:
            return False
    return all(A1[k] <= A2[k] for k in range(len(A1)))


class Front:
    def __init__(self, inst, K=300):
        self.inst = inst
        self.K = K
        self.boxes = []
        self.hits = 0
        self.queries = 0

    def query(self, R, r, A, U):
        """Max h over boxes containing (R,r,A), ignoring boxes with h<U."""
        self.queries += 1
        best = -1
        bid = -1
        for b in self.boxes:
            if b.h <= best or b.h < U:
                continue
            if b.R0 & ~R:
                continue
            ok = True
            for i, ri in b.pairs:
                if r[i] < ri:
                    ok = False
                    break
            if not ok:
                continue
            for k in range(len(A)):
                if A[k] < b.A0[k]:
                    ok = False
                    break
            if ok:
                best = b.h
                bid = b.pid
        return best, bid

    def add(self, R0, pairs, A0, h, pid):
        pairs = tuple(sorted(pairs))
        for b in self.boxes:
            if region_superset(b.R0, b.pairs, b.A0, R0, pairs, A0) and b.h >= h:
                return False        # subsumed
        self.boxes = [b for b in self.boxes
                      if not (region_superset(R0, pairs, A0, b.R0, b.pairs, b.A0)
                              and h >= b.h)]
        self.boxes.append(Box(R0, pairs, A0, h, pid))
        if len(self.boxes) > self.K:
            self.boxes.sort(key=lambda b: b.h, reverse=True)
            del self.boxes[self.K:]
        return True


def bits(mask, n):
    return [i for i in range(n) if (mask >> i) & 1]


def generalize(inst, R, r, A, h):
    """Deletion-based minimal point inside the level set {D >= h}.
    Only used for LOCAL certificates (whose test is a function of the point)."""
    n, m = inst['n'], inst['m']
    R0 = R
    r0 = list(r)
    A0 = list(A)
    removed = 0
    lowered_r = 0
    lowered_A = 0
    # 1. drop tasks (biggest region gain); cheap heuristic order
    for i in sorted(bits(R0, n), key=lambda x: inst['p'][x]):
        R1 = R0 & ~(1 << i)
        if lb_ge(inst, R1, r0, A0, h):
            R0 = R1
            removed += 1
    # 2. lower releases
    for i in bits(R0, n):
        lo, hi = 0, r0[i]
        while lo < hi:
            mid = (lo + hi) // 2
            old = r0[i]
            r0[i] = mid
            good = lb_ge(inst, R0, r0, A0, h)
            r0[i] = old
            if good:
                hi = mid
            else:
                lo = mid + 1
        if lo < r0[i]:
            r0[i] = lo
            lowered_r += 1
    # 3. lower capacities
    for k in range(m):
        lo, hi = 0, A0[k]
        while lo < hi:
            mid = (lo + hi) // 2
            old = A0[k]
            A0[k] = mid
            good = lb_ge(inst, R0, r0, A0, h)
            A0[k] = old
            if good:
                hi = mid
            else:
                lo = mid + 1
        if lo < A0[k]:
            A0[k] = lo
            lowered_A += 1
    return R0, [(i, r0[i]) for i in bits(R0, n)], tuple(A0), removed, lowered_r, lowered_A


# ------------------------------------------------------------------ solver
class Budget(Exception):
    pass


class Solver:
    def __init__(self, inst, engine='dfs', dom=True, front='weak', memo=True,
                 guide='static', tau=None, K=300, weaken=True, U0=None,
                 refute_exact=True):
        self.inst = inst
        self.engine = engine
        self.dom = dom
        self.front_mode = front
        self.use_front = front != 'off'
        self.memo_on = memo
        self.guide = guide
        self.tau = tau or {}
        self.K = K
        self.weaken = weaken
        if U0 is None:
            self.U, self.inc_path = best_primal(inst)
        else:
            self.U = U0
            self.inc_path = None
        self.U0 = self.U
        self.nodes = 0
        self.expanded = 0
        self.budget = INF
        self.front = Front(inst, K)
        self.memo = {}
        self.proof = []
        self.lemmas = 0
        self.learn_calls = 0
        self.hits = 0
        self.anytime = {}
        self.removed = 0
        self.lowered_r = 0
        self.lowered_A = 0
        self.max_depth = 0
        self.front_drops = 0

    # ---- proof objects
    def new_proof(self, obj):
        obj['id'] = len(self.proof)
        self.proof.append(obj)
        return obj['id']

    def record(self, k):
        if k in (10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400):
            self.anytime[k] = self.U

    # ---- learning
    def learn_local(self, R, r, A, h):
        self.learn_calls += 1
        if self.weaken:
            R0, pairs, A0, rm, lr, lA = generalize(self.inst, R, r, A, h)
            self.removed += rm
            self.lowered_r += lr
            self.lowered_A += lA
        else:
            R0 = R
            pairs = tuple((i, r[i]) for i in bits(R, self.inst['n']))
            A0 = tuple(A)
        pid = self.new_proof({'type': 'LOCAL', 'R0': R0, 'pairs': pairs,
                              'A0': A0, 'h': h})
        added = self.front.add(R0, pairs, A0, h, pid) if self.use_front else False
        if added:
            self.lemmas += 1
        return pid

    def learn_close(self, R, r, A, h, local, kids):
        # kids: list of (i,k,pid,childR,childr,childA)
        pid = self.new_proof({'type': 'CLOSE', 'R': R, 'r': tuple(r),
                              'A': A, 'h': h, 'local': local,
                              'R0': R, 'pairs': tuple((i, r[i]) for i in bits(R, self.inst['n'])),
                              'A0': tuple(A),
                              'kids': [(i, k, p) for (i, k, p, _, _, _) in kids]})
        added = (self.front.add(R, tuple((i, r[i]) for i in bits(R, self.inst['n'])),
                                tuple(A), h, pid) if self.use_front else False)
        if added:
            self.lemmas += 1
        return pid

    # ---- child ordering
    def order(self, kids):
        inst = self.inst
        if self.guide == 'aco' and self.tau:
            def score(kd):
                R2, r2, A2, i, k = kd
                return -(self.tau.get((R2, A2, i, k), 1.0))
            return sorted(kids, key=score)
        # static CP: largest tail first, then earliest completion
        q = inst['q_static']
        def score(kd):
            R2, r2, A2, i, k = kd
            return (-q[i], max(A2), i)
        return sorted(kids, key=score)

    # ---- DFS
    def dfs(self, R, r, A, depth=0, path=()):
        self.nodes += 1
        if self.nodes > self.budget:
            raise Budget
        self.record(self.nodes)
        if depth > self.max_depth:
            self.max_depth = depth
        key = (R, tuple(r), A)
        if self.memo_on and key in self.memo:
            return self.memo[key]
        self.expanded += 1
        C = max(A)
        if R == 0:
            if C < self.U:
                self.U = C
                self.inc_path = path
                self.record(self.nodes)
            pid = self.new_proof({'type': 'TERMINAL', 'C': C, 'path': path,
                                  'exact': True, 'R0': 0, 'pairs': (),
                                  'A0': tuple(A), 'h': C})
            self.memo[key] = (C, pid)
            return C, pid
        # front query (only boxes strong enough to matter)
        qv, qid = (-1, -1)
        if self.use_front:
            qv, qid = self.front.query(R, r, A, self.U)
            if qv >= self.U:
                self.hits += 1
                return qv, qid
        lv = lb_local(self.inst, R, r, A, self.U)
        if lv >= self.U:
            pid = self.learn_local(R, r, A, lv)
            self.memo[key] = (lv, pid)
            return lv, pid
        kids = children(self.inst, R, r, A)
        kids = self.order(kids)
        vals = []
        certs = []
        used = []
        for (R2, r2, A2, i, k) in kids:
            v, p = self.dfs(R2, r2, A2, depth + 1, path + ((i, k),))
            vals.append(v)
            certs.append(p)
            used.append((i, k, p, R2, r2, A2))
        mval = min(vals)
        h = max(lv, mval)
        pid = None
        if h >= self.U:
            if mval >= h:
                pid = self.learn_close(R, r, A, h, lv, used)
            else:
                pid = self.learn_local(R, r, A, h)
        self.memo[key] = (h, pid if pid is not None else -1)
        return h, pid

    def search(self, budget=200000):
        self.budget = budget
        self._root_R = self.inst['full']
        self._root_r = [0] * self.inst['n']
        try:
            v, pid = self.dfs(self.inst['full'], [0] * self.inst['n'],
                              tuple([0] * self.inst['m']))
            exhausted = True
        except Budget:
            v, pid, exhausted = -1, -1, False
        return {'U': self.U, 'U0': self.U0, 'nodes': self.nodes,
                'L': v, 'exhausted': exhausted, 'lemmas': self.lemmas,
                'learn_calls': self.learn_calls, 'front_hits': self.hits,
                'front_size': len(self.front.boxes),
                'removed': self.removed, 'lowered_r': self.lowered_r,
                'lowered_A': self.lowered_A, 'anytime': self.anytime,
                'max_depth': self.max_depth, 'expanded': self.expanded,
                'proof': len(self.proof),
                'root_pid': pid}

    # ---- best-first (baseline)
    def search_bf(self, budget=200000, inherit=True):
        inst = self.inst
        n, m, full = inst['n'], inst['m'], inst['full']
        U = self.U
        r0 = [0] * n
        A0 = tuple([0] * m)
        heap = [(max(A0), 0, (full, tuple(r0), A0), 0)]
        counter = 1
        dom = defaultdict(list)
        dom[full].append((A0, tuple(r0)))
        nodes = 0
        uniq = 0
        maxopen = 0
        anytime = {}
        seen = {}
        while heap and nodes < budget:
            f, _, (R, r, A), F = heapq.heappop(heap)
            if f >= U:
                break
            # re-key with the *current* incumbent (U only decreases)
            lv0 = lb_local(inst, R, r, A, U)
            if lv0 >= U:
                continue
            Fn = max(F, lv0) if inherit else lv0
            nf = max(max(A), Fn)
            if nf > f:
                heapq.heappush(heap, (nf, counter, (R, r, A), Fn))
                counter += 1
                continue
            if (R, r, A) not in seen:
                uniq += 1
            seen[(R, r, A)] = f
            nodes += 1
            if len(heap) > maxopen:
                maxopen = len(heap)
            if nodes in (10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400):
                anytime[nodes] = U
            lv = lb_local(inst, R, r, A, U)
            if lv >= U:
                continue
            if R == 0:
                if max(A) < U:
                    U = max(A)
                continue
            for (R2, r2, A2, i, k) in children(inst, R, r, A):
                if max(A2) >= U:
                    continue
                l2 = lb_local(inst, R2, r2, A2, U)
                F2 = max(F, l2) if inherit else l2
                f2 = max(max(A2), F2)
                if f2 >= U:
                    continue
                if self.dom:
                    bucket = dom[R2]
                    dominated = False
                    for (A3, r3) in bucket:
                        if all(A3[t] <= A2[t] for t in range(m)) and \
                           all(r3[t] <= r2[t] for t in range(n)):
                            dominated = True
                            break
                    if dominated:
                        continue
                    bucket[:] = [(A3, r3) for (A3, r3) in bucket
                                 if not (all(A2[t] <= A3[t] for t in range(m)) and
                                         all(r2[t] <= r3[t] for t in range(n)))]
                    if len(bucket) < 40:
                        bucket.append((A2, tuple(r2)))
                heapq.heappush(heap, (f2, counter, (R2, tuple(r2), A2), F2))
                counter += 1
        return {'U': U, 'U0': self.U0, 'nodes': nodes, 'uniq': uniq,
                'maxopen': maxopen, 'anytime': anytime,
                'open': len(heap), 'L': min((x[0] for x in heap), default=-1)}


# ------------------------------------------------------------------ checker
def apply_action(inst, R, r, A, i, k):
    t = max(A[k], r[i])
    A2 = list(A)
    A2[k] = t + inst['p'][i]
    A2 = tuple(sorted(A2))
    r2 = list(r)
    c = t + inst['p'][i]
    for j in inst['succ'][i]:
        if (R >> j) & 1 and c > r2[j]:
            r2[j] = c
    return R & ~(1 << i), tuple(r2), A2


def in_region(box, R, r, A):
    if box.get('exact'):
        return R == 0 and tuple(A) == box['A0']
    if box['R0'] & ~R:
        return False
    for i, ri in box['pairs']:
        if r[i] < ri:
            return False
    return all(A[k] >= box['A0'][k] for k in range(len(A)))


def check_proof(inst, proof, root_pid, U, inc_path=None):
    """Independent checker for the CLOSE/LOCAL/TERMINAL proof DAG."""
    n, m, full = inst['n'], inst['m'], inst['full']
    state = {}

    def box_ok(pid, stack):
        if pid in state:
            return state[pid]
        if pid < 0 or pid >= len(proof):
            return False
        if pid in stack:
            return False
        stack.add(pid)
        b = proof[pid]
        t = b['type']
        ok = False
        if t == 'TERMINAL':
            R, r, A = full, [0] * n, tuple([0] * m)
            bp = b.get('path', ())
            good = True
            for (i, k) in bp:
                if not (R >> i) & 1 or (inst['pmask'][i] & R):
                    good = False
                    break
                R, r, A = apply_action(inst, R, r, A, i, k)
            ok = good and R == 0 and max(A) == b['C']
        elif t == 'LOCAL':
            r0 = [0] * n
            for i, ri in b['pairs']:
                r0[i] = ri
            ok = lb_ge(inst, b['R0'], r0, tuple(b['A0']), b['h'])
        elif t == 'CLOSE':
            R, r, A = b['R'], list(b['r']), tuple(b['A'])
            ok = lb_ge(inst, R, r, A, b['local'])
            if ok:
                expected = children(inst, R, r, A)
                kidmap = {(i, k): p for (i, k, p) in b['kids']}
                minh = 10 ** 9
                for (R2, r2, A2, i, k) in expected:
                    p = kidmap.get((i, k))
                    if p is None:
                        # a different action may lead to the same interface
                        p = None
                        for (ii, kk, pp) in b['kids']:
                            RR, rr, AA = apply_action(inst, R, r, A, ii, kk)
                            if (RR, rr, AA) == (R2, r2, A2):
                                p = pp
                                break
                        if p is None:
                            ok = False
                            break
                    if not box_ok(p, stack):
                        ok = False
                        break
                    if not in_region(proof[p], R2, r2, A2):
                        ok = False
                        break
                    minh = min(minh, proof[p].get('h', 10 ** 9))
                if ok and minh < 10 ** 9:
                    ok = b['h'] <= max(b['local'], minh)
                elif ok:
                    ok = b['h'] <= b['local']
        stack.discard(pid)
        state[pid] = ok
        return ok

    ok = box_ok(root_pid, set())
    if ok and root_pid >= 0:
        ok = proof[root_pid].get('h', -1) >= U
    inc_ok = True
    if inc_path is not None:
        R, r, A = full, [0] * n, tuple([0] * m)
        for (i, k) in inc_path:
            if not (R >> i) & 1 or (inst['pmask'][i] & R):
                inc_ok = False
                break
            R, r, A = apply_action(inst, R, r, A, i, k)
        inc_ok = inc_ok and R == 0 and max(A) == U
    return ok and inc_ok, {'root_ok': ok, 'inc_ok': inc_ok,
                           'checked': sum(1 for v in state.values() if v),
                           'total': len(state)}


def exact_dp_iface(inst, cap=2_000_000):
    """Unpruned DP over the interface DAG: independent ground truth."""
    n, m, full = inst['n'], inst['m'], inst['full']
    memo = {}
    cnt = [0]

    def f(R, r, A):
        key = (R, tuple(r), A)
        if key in memo:
            return memo[key]
        cnt[0] += 1
        if cnt[0] > cap:
            raise RuntimeError
        if R == 0:
            memo[key] = max(A)
            return max(A)
        best = INF
        for (R2, r2, A2, i, k) in children(inst, R, r, A):
            v = f(R2, r2, A2)
            if v < best:
                best = v
        memo[key] = best
        return best

    try:
        v = f(full, [0] * n, tuple([0] * m))
        return v, cnt[0], True
    except RuntimeError:
        return INF, cnt[0], False
