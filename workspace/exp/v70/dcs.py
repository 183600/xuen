"""v7.0 DCS-ALC: divide-and-conquer split proof trees + compression.

The v6.1 ALC returns the first Farkas certificate it finds.  For a branch
node that certificate is *conditional* on the branch scope: it proves one
child, not the root.  DCS-ALC makes the proof object explicit:

    Proof = LeafNO(scope, Farkas) | LeafYES(scope, schedule)
          | Split(scope, i, t0, left, right)

A Split partitions the integer start times of job i into s_i <= t0 and
s_i > t0.  If both children are NO, the parent is NO.  The tree is the
certificate; a leaf certificate is only valid inside its scope.

Compression: after building a default tree, a split found deeper in the
tree is promoted to an ancestor.  If both children of the promoted split
are infeasible under the ancestor's scope, the whole subtree is replaced
by a two-leaf proof.  Promotion is a proof-tree rotation, not a heuristic
cut: the new tree is re-verified from scratch.
"""
import sys, time
import numpy as np
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
import cert as v60cert
from lazy import LazySD
from po import heads_tails


def verify_cert_strict(inst, h, c, forbid=None, elig_aware=None):
    """Certificate replay plus structural checks on the dual rows."""
    if c is None:
        return False
    if c.get('kind') == 'packing':
        n, m = inst['n'], inst['m']
        for k, t, w in c.get('beta', []):
            if t < 0 or t >= h:
                return False
            if elig_aware and (k is None or k < 0 or k >= m):
                return False
        for i, j, t, w in c.get('dom', []):
            if j not in inst['succ'][i] or t < 0 or t >= h:
                return False
        for i, j, w in c.get('exp', []):
            if j not in inst['succ'][i]:
                return False
    return v60cert.verify(inst, h, c, forbid=forbid, elig_aware=elig_aware)


class Node:
    __slots__ = ('scope', 'status', 'split', 'children', 'cert', 'kind',
                 'schedule', 'compressed')

    def __init__(self, scope):
        self.scope = frozenset(scope)
        self.status = 'open'
        self.split = None
        self.children = None
        self.cert = None
        self.kind = None
        self.schedule = None
        self.compressed = False


class DCS:
    def __init__(self, inst, h, cert_on=True, elig_aware=None,
                 max_rounds=60, topk=100):
        self.inst = inst
        self.h = h
        self.n = inst['n']
        self.cert_on = cert_on
        if elig_aware is None:
            elig_aware = any(len(set(inst['elig'][i])) < inst['m']
                             for i in range(self.n))
        self.elig_aware = elig_aware
        self.lp = LazySD(inst, h, elig_aware=elig_aware)
        self.N = self.lp.base.N
        self.max_rounds = max_rounds
        self.topk = topk
        self.lp_solves = 0
        self.cert_calls = 0
        self.cert_ok = 0
        self.cert_t = 0.0
        self.extract_t = 0.0
        self.budget = 10**18

    def bounds(self, scope):
        b = [(0, 1)] * self.N
        if scope:
            for cc, key in enumerate(self.lp.cols):
                if (key[0], key[-1]) in scope:
                    b[cc] = (0, 0)
        return b

    def _schedule(self, z, tol=1e-6):
        """Return ({i: t}, {i: k}) if z is integral, else None."""
        starts = {}
        mach = {}
        for cc, key in enumerate(self.lp.cols):
            if z[cc] > 1 - tol:
                i, t = key[0], key[-1]
                starts[i] = t
                mach[i] = key[1] if len(key) == 3 else None
            elif z[cc] > tol:
                return None
        if len(starts) != self.n:
            return None
        return starts, mach

    def _valid_schedule(self, starts, mach):
        n, m, p = self.n, self.inst['m'], self.inst['p']
        for i in range(n):
            if starts[i] + p[i] > self.h:
                return False
            for j in self.inst['succ'][i]:
                if starts[i] + p[i] > starts[j]:
                    return False
        if self.elig_aware:
            for k in range(m):
                for t in range(self.h):
                    load = sum(1 for i in range(n)
                               if mach[i] == k and starts[i] <= t < starts[i] + p[i])
                    if load > 1:
                        return False
        else:
            for t in range(self.h):
                load = sum(1 for i in range(n)
                           if starts[i] <= t < starts[i] + p[i])
                if load > m:
                    return False
        return True

    def _prec_cuts(self, z):
        sch = self._schedule(z)
        if sch is None:
            return []
        starts, _ = sch
        out = []
        for i in range(self.n):
            for j in self.inst['succ'][i]:
                if starts[i] + self.inst['p'][i] > starts[j]:
                    t = starts[j] - self.inst['p'][i]
                    if 0 <= t:
                        out.append((i, j, t))
        return out

    def solve_scope(self, scope):
        b = self.bounds(scope)
        res = None
        for rnd in range(self.max_rounds):
            if self.lp_solves >= self.budget:
                return None, None
            res = self.lp.solve(b)
            self.lp_solves += 1
            if res.status != 0:
                return res, None
            viol = self.lp.separate(res.x, topk=self.topk)
            if not viol:
                sch = self._schedule(res.x)
                if sch is not None and self._valid_schedule(*sch):
                    return res, res.x
                cuts = self._prec_cuts(res.x) if sch is not None else []
                if not cuts:
                    return res, res.x
                viol = [(0.0, i, j, t) for (i, j, t) in cuts]
            for _, i, j, t in viol:
                if (i, j, t) not in self.lp.cutset:
                    self.lp.cutset.add((i, j, t))
                    self.lp.cuts.append((i, j, t))
        return res, None

    def _cert(self, scope):
        self.cert_calls += 1
        t0 = time.time()
        if not scope:
            self.lp.A, self.lp.hi = self.lp.matrix()
            c = v60cert.integer_certificate_from_lp(self.lp, self.inst, self.h)
        else:
            c = v60cert.integer_certificate(self.inst, self.h, forbid=scope,
                                            elig_aware=self.elig_aware)
        ok = c is not None and verify_cert_strict(
            self.inst, self.h, c, forbid=scope,
            elig_aware=self.elig_aware)
        self.cert_t += time.time() - t0
        if ok:
            self.cert_ok += 1
        return c, ok

    def _pick(self, z):
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return None
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(set(key[-1] for key in self.lp.idx if key[0] == i))
        s, mid = 0.0, t
        for tt in times:
            s += z[self.lp.idx[(i, tt)]]
            if s >= 0.5:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        return i, mid

    def _split_scopes(self, scope, i, mid):
        times = sorted(set(k[-1] for k in self.lp.idx if k[0] == i))
        left = set(scope)
        right = set(scope)
        for tt in times:
            if tt > mid:
                left.add((i, tt))
            else:
                right.add((i, tt))
        return frozenset(left), frozenset(right)

    def build(self, scope, budget):
        self.budget = budget
        node = Node(scope)
        if self.lp_solves >= budget:
            return node, 'budget'
        res, z = self.solve_scope(scope)
        if self.lp_solves > budget:
            return node, 'budget'
        if res is None:
            return node, 'budget'
        if res.status == 2:
            node.status = 'no'
            node.kind = 'leaf'
            if self.cert_on:
                c, ok = self._cert(scope)
                node.cert = c
                node.status = 'no' if ok else 'no-unaudited'
            return node, 'ok'
        if res.status != 0 or z is None:
            return node, 'unknown'
        split = self._pick(z)
        if split is None:
            node.status = 'yes'
            node.kind = 'leaf'
            return node, 'ok'
        i, mid = split
        ls, rs = self._split_scopes(scope, i, mid)
        left, wl = self.build(ls, budget)
        right, wr = self.build(rs, budget)
        node.split = (i, mid)
        node.children = (left, right)
        node.kind = 'split'
        if left.status == 'no' and right.status == 'no':
            node.status = 'no'
        elif left.status == 'yes' or right.status == 'yes':
            node.status = 'yes'
        else:
            node.status = 'open'
        return node, 'ok'

    def _frac_mass(self, z):
        return sum(min(z[c], 1 - z[c]) for c in range(self.N)
                   if 1e-7 < z[c] < 1 - 1e-7)

    def _candidates(self, z):
        """Fractional jobs ordered by critical path est+p+q (longest first).

        The order is permutation invariant.  It is only a scheduling
        heuristic: the proof is rebuilt from the chosen split, so a bad
        order costs LP solves but cannot affect soundness.
        """
        jobs = {}
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                i = key[0]
                jobs.setdefault(i, []).append(cc)
        out = []
        for i, cols in jobs.items():
            mass = sum(min(z[c], 1 - z[c]) for c in cols)
            crit = self.lp.est[i] + self.inst['p'][i] + self.lp.q[i]
            out.append((-crit, -mass, i))
        out.sort()
        seq = []
        for _, _, i in out:
            times = sorted(set(k[-1] for k in self.lp.idx if k[0] == i))
            if len(times) < 2:
                continue
            s, mid = 0.0, times[0]
            for tt in times:
                s += z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt
                    break
            if mid >= times[-1]:
                mid = times[-1] - 1
            seq.append((i, mid))
            # also try the neighbouring midpoint; cheap and robust
            if mid - 1 >= times[0]:
                seq.append((i, mid - 1))
            if mid + 1 < times[-1]:
                seq.append((i, mid + 1))
        return seq

    def build_look(self, scope, budget, look_budget=6):
        self.budget = budget
        node = Node(scope)
        if self.lp_solves >= budget:
            return node, 'budget'
        res, z = self.solve_scope(scope)
        if self.lp_solves > budget:
            return node, 'budget'
        if res is None:
            return node, 'budget'
        if res.status == 2:
            node.status = 'no'; node.kind = 'leaf'
            if self.cert_on:
                c, ok = self._cert(scope)
                node.cert = c
                node.status = 'no' if ok else 'no-unaudited'
            return node, 'ok'
        if res.status != 0 or z is None:
            return node, 'unknown'
        if self._pick(z) is None:
            node.status = 'yes'; node.kind = 'leaf'
            return node, 'ok'
        cands = self._candidates(z)
        fallback = None
        for k, (i, mid) in enumerate(cands[:look_budget]):
            ls, rs = self._split_scopes(scope, i, mid)
            rl, zl = self.solve_scope(ls)
            rr, zr = self.solve_scope(rs)
            if rl is None or rr is None:
                break
            if rl.status == 2 and rr.status == 2:
                cl, okl = self._cert(ls) if self.cert_on else (None, True)
                cr, okr = self._cert(rs) if self.cert_on else (None, True)
                if okl and okr:
                    a = Node(ls); a.status = 'no'; a.kind = 'leaf'; a.cert = cl
                    b = Node(rs); b.status = 'no'; b.kind = 'leaf'; b.cert = cr
                    node.split = (i, mid); node.children = (a, b)
                    node.status = 'no'; node.kind = 'split'
                    return node, 'ok'
            elif rl.status == 2 or rr.status == 2:
                other = rr if rl.status == 2 else rl
                other_z = zr if rl.status == 2 else zl
                if other.status == 0 and self._pick(other_z) is None:
                    # one side already YES: the parent is YES
                    node.split = (i, mid); node.kind = 'split'
                    node.status = 'yes'; node.children = (Node(ls), Node(rs))
                    return node, 'ok'
                fm = self._frac_mass(other_z) if other.status == 0 else 0.0
                if fallback is None or fm < fallback[0]:
                    fallback = (fm, i, mid, ls, rs)
            elif rl.status == 0 and rr.status == 0:
                fm = self._frac_mass(zl) + self._frac_mass(zr)
                if fallback is None or fm < fallback[0]:
                    fallback = (fm, i, mid, ls, rs)
            if self.lp_solves >= budget:
                break
        # no two-leaf proof: use the best lookahead split, else the default
        if fallback is not None:
            _, i, mid, ls, rs = fallback
        else:
            i, mid = self._pick(z)
            ls, rs = self._split_scopes(scope, i, mid)
        left, _ = self.build_look(ls, budget, look_budget)
        right, _ = self.build_look(rs, budget, look_budget)
        node.split = (i, mid); node.children = (left, right); node.kind = 'split'
        if left.status == 'no' and right.status == 'no':
            node.status = 'no'
        elif left.status == 'yes' or right.status == 'yes':
            node.status = 'yes'
        else:
            node.status = 'open'
        return node, 'ok'

    def _collect_splits(self, node, out):
        if node.kind == 'split':
            out.append((node.split[0], node.split[1]))
            self._collect_splits(node.children[0], out)
            self._collect_splits(node.children[1], out)
        return out

    def compress(self, node, budget, order='deep'):
        if node.kind != 'split':
            return
        self.compress(node.children[0], budget)
        self.compress(node.children[1], budget)
        if node.status != 'no' or self.lp_solves >= budget:
            return
        cand = self._collect_splits(node, [])
        # distinct, deepest-first (reverse discovery order), skip current
        seen = set()
        seq = []
        for s in reversed(cand):
            if s not in seen and s != node.split:
                seen.add(s)
                seq.append(s)
        for i, mid in seq:
            ls, rs = self._split_scopes(node.scope, i, mid)
            if not ls or not rs:
                continue
            rl, _ = self.solve_scope(ls)
            rr, _ = self.solve_scope(rs)
            if rl.status == 2 and rr.status == 2:
                cl, okl = self._cert(ls) if self.cert_on else (None, True)
                cr, okr = self._cert(rs) if self.cert_on else (None, True)
                if not (okl and okr):
                    continue
                a = Node(ls); a.status = 'no'; a.kind = 'leaf'; a.cert = cl
                b = Node(rs); b.status = 'no'; b.kind = 'leaf'; b.cert = cr
                node.split = (i, mid)
                node.children = (a, b)
                node.compressed = True
                return
            if self.lp_solves >= budget:
                return

    def stats(self, root):
        nodes = leaves = splits = depth = 0
        stack = [(root, 0)]
        while stack:
            u, d = stack.pop()
            nodes += 1
            depth = max(depth, d)
            if u.kind == 'split':
                splits += 1
                stack.append((u.children[0], d + 1))
                stack.append((u.children[1], d + 1))
            else:
                leaves += 1
        return dict(nodes=nodes, leaves=leaves, splits=splits, depth=depth,
                    lp=self.lp_solves, certs=self.cert_calls,
                    cert_ok=self.cert_ok, cert_t=self.cert_t,
                    cuts=len(self.lp.cuts), status=root.status,
                    compressed=root.compressed)


def verify_tree(inst, h, node, expected_scope, elig_aware=None):
    """Replay the full divide-and-conquer proof tree."""
    if set(node.scope) != set(expected_scope):
        return False, 'scope'
    if node.kind == 'leaf':
        if node.status == 'yes':
            return True, 'yes'
        if node.cert is None:
            return False, 'no-cert'
        if not verify_cert_strict(inst, h, node.cert, forbid=node.scope,
                              elig_aware=elig_aware):
            return False, 'cert'
        return True, 'no'
    if node.kind != 'split' or node.children is None:
        return False, 'open'
    i, mid = node.split
    # the split must partition exactly the possible starts of i in this scope
    from po import heads_tails
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    times = set(range(est[i], h - q[i] - inst['p'][i] + 1))
    ls = set(node.scope) | {(i, t) for t in times if t > mid}
    rs = set(node.scope) | {(i, t) for t in times if t <= mid}
    if set(node.children[0].scope) != ls or set(node.children[1].scope) != rs:
        return False, 'partition'
    if ls == set(node.scope) or rs == set(node.scope) or ls == rs:
        return False, 'empty-side'
    okl, sl = verify_tree(inst, h, node.children[0], ls, elig_aware)
    if not okl:
        return False, 'left:' + sl
    okr, sr = verify_tree(inst, h, node.children[1], rs, elig_aware)
    if not okr:
        return False, 'right:' + sr
    if sl == 'no' and sr == 'no':
        return True, 'no'
    if sl == 'yes' or sr == 'yes':
        return True, 'yes'
    return False, 'open'
