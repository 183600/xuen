"""v8.4 QRC-ALC: quorum resolution closure on top of v7.1 QNC.

A leaf certificate yields a globally valid clause

    OR_i (s_i in E_i).

v7.1 only exploits the case where one E_i is the whole clause (force) or
where a whole clause is falsified (prune).  Clauses can also be *resolved*:

    (s_i in A or R1) and (s_i in B or R2)
      =>  (s_i in A cap B) or R1 or R2.

When A cap B is empty the literal disappears.  Iterating this rule on the
learned quorum clauses derives unit clauses and the empty clause, i.e. a
multi-certificate refutation, without any further LP.  Each derived clause
keeps a resolution proof (parents, pivot job), so audit can replay the
whole DAG from the integer Farkas leaves.

A union-find over the proof DAG stores the transitive leaf support of a
component.  This is the fault-tolerance hook: a clause is usable only if
every leaf certificate in its support replays; otherwise it is quarantined
and the search falls back to the ordinary QNC behaviour.
"""
import sys, time
sys.path[:0] = ['exp/v84', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC, Budget
from cert import verify


class GlobalNo(Exception):
    pass


def _norm(E):
    d = {}
    for (i, t) in E:
        d.setdefault(i, set()).add(t)
    return {i: frozenset(S) for i, S in d.items()}


def _key(C):
    return tuple(sorted((i, tuple(sorted(S))) for i, S in C.items()))


def _subsumes(A, B):
    return set(A) <= set(B) and all(A[i] <= B[i] for i in A)


def _resolve(A, B, i):
    if i not in A or i not in B:
        return None
    inter = A[i] & B[i]
    if inter == A[i] or inter == B[i]:
        return None                  # resolvent is subsumed by a parent
    out = {}
    for C in (A, B):
        for j, S in C.items():
            if j == i:
                continue
            out[j] = out.get(j, frozenset()) | S
    if inter:
        out[i] = inter
    return out


class DSU:
    """Union-find over clause ids with a shared support set at the root."""
    def __init__(self):
        self.p = []
        self.support = []

    def add(self, sup):
        k = len(self.p)
        self.p.append(k)
        self.support.append(frozenset(sup))
        return k

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return a
        self.p[b] = a
        self.support[a] = self.support[a] | self.support[b]
        return a


class QRC(QNC):
    def __init__(self, inst, h, res_on=True, max_clauses=256,
                 max_steps=4000, max_lits=8, use_prop=True,
                 disjoint_only=False, **kw):
        super().__init__(inst, h, **kw)
        self.res_on = res_on
        self.max_clauses = max_clauses
        self.max_steps = max_steps
        self.max_lits = max_lits
        self.use_prop = use_prop
        self.disjoint_only = disjoint_only
        self.db = {}                 # id -> normalized clause
        self.active = set()
        self.key_id = {}
        self.src = {}                # id -> ('leaf', lid) or ('res', a, b, job)
        self.dsu = DSU()
        self.res_steps = 0
        self.res_units = 0
        self.res_empty = 0
        self.global_no = False
        self._leaf_cert = []
        self.why_global = None
        self.local_steps = 0
        self.local_conflicts = 0
        self.force_reason = {}
        self.conflict = None
        self.heals = 0

    # ------------------------------------------------------------- learning
    def _learn(self, F):
        got = self._analyse(F)
        if got is None:
            return None, None
        cert, E = got
        self.leaves.append((frozenset(F), E, cert))
        lid = len(self._leaf_cert)
        self._leaf_cert.append(cert)
        if self.cert is None and self.cert_on:
            self.cert, self.cert_ok = cert, True
        if self.use_quorum:
            self.clauses.append(E)
            self._add_clause(_norm(E), ('leaf', lid), frozenset([lid]))
        return cert, E

    def _curdom(self, i):
        return self.force.get(i, self.domain(i))

    def _force_job(self, i, S, reason=None):
        new = S & self._curdom(i)
        if new != self.force.get(i):
            old = self.force_reason.get(i)
            self.force[i] = new
            if reason is not None:
                self.force_reason[i] = reason
            if not new:
                self.conflict = ('force-empty', i, reason, old)
                self._global_empty('force')

    def _global_empty(self, why):
        if not self.global_no:
            self.global_no = True
            self.why_global = why
            self.res_empty += 1
        raise GlobalNo

    def _satisfied(self, C):
        return any(self._curdom(i) <= S for i, S in C.items())

    def _add_clause(self, C, src, support):
        if not C:
            if src[0] == 'leaf':
                self.conflict = ('leaf-empty', src[1])
            elif src[0] == 'res':
                self.conflict = ('res-empty', src[1], src[2], src[3])
            self._global_empty('empty-clause')
        if self._satisfied(C):
            return None
        k = _key(C)
        if k in self.key_id:
            old = self.key_id[k]
            self.dsu.union(old, len(self.dsu.p) - 1) if support else None
            return old
        if any(_subsumes(self.db[j], C) for j in self.active):
            return None
        dead = [j for j in self.active if _subsumes(C, self.db[j])]
        for j in dead:
            self.active.discard(j)
            self.key_id.pop(_key(self.db[j]), None)
        if len(self.db) >= self.max_clauses:
            return None
        idx = len(self.db)
        self.db[idx] = C
        self.active.add(idx)
        self.key_id[k] = idx
        self.src[idx] = src
        self.dsu.add(support)
        if len(C) == 1:
            i, S = next(iter(C.items()))
            self.res_units += 1
            self._force_job(i, S, idx)
        return idx

    # ------------------------------------------------------------ resolution
    def _propagate_clauses(self):
        if not self.use_prop:
            return
        changed = True
        while changed and not self.global_no:
            changed = False
            for cid in sorted(self.active):
                C = self.db[cid]
                if self._satisfied(C):
                    continue
                live = [(i, S & self._curdom(i)) for i, S in C.items()
                        if S & self._curdom(i)]
                if not live:
                    self._global_empty('propagation')
                if len(live) == 1:
                    i, inter = live[0]
                    if inter != self._curdom(i):
                        self._force_job(i, inter, cid)
                        changed = True

    def _resolve_closure(self):
        if not self.res_on or self.global_no:
            return
        steps = 0
        changed = True
        while changed and steps < self.max_steps:
            changed = False
            ids = sorted(self.active)
            pairs = []
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    A, B = self.db[ids[a]], self.db[ids[b]]
                    for i in sorted(set(A) & set(B)):
                        disjoint = not (A[i] & B[i])
                        if not disjoint and (self.disjoint_only or
                                             len(A) + len(B) - 1 > self.max_lits):
                            continue
                        pairs.append((0 if disjoint else 1,
                                      ids[a], ids[b], i))
            pairs.sort()
            for _, a, b, i in pairs:
                if steps >= self.max_steps:
                    break
                if a not in self.active or b not in self.active:
                    continue
                A, B = self.db[a], self.db[b]
                if i not in A or i not in B:
                    continue
                R = _resolve(A, B, i)
                if R is None:
                    continue
                steps += 1
                self.res_steps += 1
                if not R:
                    self.conflict = ('res-empty', a, b, i)
                sup = (self.dsu.support[self.dsu.find(a)] |
                       self.dsu.support[self.dsu.find(b)])
                idx = self._add_clause(R, ('res', a, b, i), sup)
                if idx is not None:
                    self.dsu.union(idx, a)
                    self.dsu.union(idx, b)
                    if self.use_prop:
                        self._propagate_clauses()
                    changed = True
        return steps

    # --------------------------------------------------------------- search
    def _local_propagate(self, bounds):
        """Clause propagation inside a node: only the node's forbid set is
        used, so the derived restrictions are local, not global force."""
        if not self.use_prop or not self.db:
            return bounds, False
        b = list(bounds)
        dom = {i: set(self.domain(i)) for i in range(self.n)}
        for cc, key in enumerate(self.lp.cols):
            if b[cc] == (0, 0):
                dom[key[0]].discard(key[-1])
        changed = True
        while changed:
            changed = False
            for cid in sorted(self.active):
                C = self.db[cid]
                live = []
                sat = False
                for i, S in C.items():
                    inter = S & dom[i]
                    if not inter:
                        continue
                    if dom[i] <= S:
                        sat = True
                        break
                    live.append((i, inter))
                if sat:
                    continue
                if not live:
                    self.local_conflicts += 1
                    return b, True
                if len(live) == 1:
                    i, inter = live[0]
                    if inter != dom[i]:
                        for t in dom[i] - inter:
                            for cc, key in enumerate(self.lp.cols):
                                if key[0] == i and key[-1] == t and b[cc] != (0, 0):
                                    b[cc] = (0, 0)
                                    self.local_steps += 1
                        dom[i] = inter
                        changed = True
        return b, False

    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        if self.global_no:
            return False, 'resolution'
        bounds, _ = self._apply_force(bounds)
        if self.use_prop:
            self._propagate_clauses()
        bounds, confl = self._local_propagate(bounds)
        if confl:
            return False, 'local-clause'
        i0 = self._empty_job(bounds) if self.use_empty else None
        if i0 is not None:
            self.empty_prunes += 1
            if not self._dom.get(i0):
                self.conflict = ('cp-empty', i0)
            return False, 'empty'
        F = self._forbids(bounds)
        for E in self.clauses:
            if E <= F:
                self.prunes += 1
                return False, 'clause'
        self.nodes += 1
        if self.nodes > nodecap:
            raise Budget
        res, z = self._solve(bounds, max_rounds, topk)
        if res.status == 2:
            cert, E = self._learn(F)
            if cert is None and getattr(self, 'heal_on_missing', False):
                return self._heal(bounds, depth, nodecap, max_rounds, topk)
            if self.res_on:
                self._resolve_closure()
            return False, 'no'
        if z is None:
            return None, 'roundcap'
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return True, 'yes'
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(self.domain(i))
        s = 0.0
        mid = t
        for tt in times:
            if self.elig:
                s += sum(z[self.lp.idx[(i, k, tt)]]
                         for k in self.lp.base.elig[i]
                         if (i, k, tt) in self.lp.idx)
            else:
                s += z[self.lp.idx[(i, tt)]]
            if s >= 0.5:
                mid = tt
                break
        if mid >= times[-1]:
            mid = times[-1] - 1
        lo = list(bounds)
        hi2 = list(bounds)
        for tt in times:
            if self.elig:
                for k in self.lp.base.elig[i]:
                    if (i, k, tt) in self.lp.idx:
                        c2 = self.lp.idx[(i, k, tt)]
                        if tt > mid:
                            lo[c2] = (0, 0)
                        else:
                            hi2[c2] = (0, 0)
            else:
                c2 = self.lp.idx[(i, tt)]
                if tt > mid:
                    lo[c2] = (0, 0)
                else:
                    hi2[c2] = (0, 0)
        a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
        if a is not False:
            return a, why
        return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)

    def _heal(self, bounds, depth, nodecap, max_rounds, topk):
        """Split a node whose LP is infeasible but whose certificate was
        lost.  Both children remain infeasible, so the decision stays sound;
        we only pay extra LP until a certifiable region is reached."""
        times = {}
        for key, cc in self.lp.idx.items():
            if bounds[cc] != (0, 0):
                times.setdefault(key[0], set()).add(key[-1])
        cand = [(len(S), i, S) for i, S in times.items() if len(S) > 1]
        if not cand:
            return None, 'uncertified'
        cand.sort()
        _, i, S = cand[0]
        ts = sorted(S)
        mid = ts[len(ts) // 2 - 1]
        lo = list(bounds); hi2 = list(bounds)
        for tt in ts:
            if self.elig:
                for k in self.lp.base.elig[i]:
                    if (i, k, tt) in self.lp.idx:
                        c2 = self.lp.idx[(i, k, tt)]
                        if tt > mid:
                            lo[c2] = (0, 0)
                        else:
                            hi2[c2] = (0, 0)
            else:
                c2 = self.lp.idx[(i, tt)]
                if tt > mid:
                    lo[c2] = (0, 0)
                else:
                    hi2[c2] = (0, 0)
        self.heals += 1
        a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
        if a is not False:
            return a, why
        return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            v, why = self._branch([(0, 1)] * self.lp.base.N, 0, nodecap,
                                  max_rounds, topk)
        except GlobalNo:
            v, why = False, 'resolution'
        except Budget:
            v, why = None, 'budget'
        return v, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(res_steps=self.res_steps, res_units=self.res_units,
                  res_empty=self.res_empty, clause_db=len(self.active),
                  heals=self.heals,
                  global_no=self.global_no, why_global=self.why_global,
                  local_steps=self.local_steps,
                  local_conflicts=self.local_conflicts)
        return st

    # ------------------------------------------------------------- proof core
    def proof_core(self):
        """Leaf ids used by the recorded global conflict."""
        if self.conflict is None:
            return set()
        kind = self.conflict[0]
        if kind == 'cp-empty':
            return set()
        if kind == 'res-empty':
            _, a, b, i = self.conflict
            ids = {a, b}
        elif kind == 'force-empty':
            ids = {x for x in self.conflict[2:] if x is not None}
        elif kind == 'leaf-empty':
            return {self.conflict[1]}
        else:
            return set()
        out = set()
        for cid in ids:
            if cid is not None and cid < len(self.dsu.p):
                out |= set(self.dsu.support[self.dsu.find(cid)])
        return out

    def audit_core(self):
        core = self.proof_core()
        if self.conflict is None:
            return self.audit()
        if self.conflict[0] == 'cp-empty':
            i = self.conflict[1]
            return (self.lp.est[i] + self.lp.p[i] + self.lp.q[i] > self.h)
        if self.conflict[0] == 'force-empty':
            i, a, b = self.conflict[1:]
            if a is None or b is None or a not in self.db or b not in self.db:
                return False
            for cid in (a, b):
                C = self.db[cid]
                if i not in C:
                    return False
                for j, S in C.items():
                    if j != i and (S & self.force.get(j, self.domain(j))):
                        return False
            if self.db[a][i] & self.db[b][i]:
                return False
        for lid in core:
            F, E, c = self.leaves[lid]
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        # replay only the clauses reachable from the conflict
        stack = []
        c = self.conflict
        if c[0] == 'res-empty':
            stack += [c[1], c[2]]
        elif c[0] == 'force-empty':
            stack += [x for x in c[2:] if x is not None]
        elif c[0] == 'leaf-empty':
            stack += []
        seen = set()
        while stack:
            cid = stack.pop()
            if cid in seen:
                continue
            if cid not in self.db:
                return False
            seen.add(cid)
            src = self.src[cid]
            if src[0] == 'leaf':
                lid = src[1]
                if _norm(self.leaves[lid][1]) != self.db[cid]:
                    return False
                continue
            _, a, b, i = src
            if a not in self.db or b not in self.db:
                return False
            if _resolve(self.db[a], self.db[b], i) != self.db[cid]:
                return False
            stack += [a, b]
        return True

    # ---------------------------------------------------------------- audit
    def audit(self):
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E, elig_aware=self.elig):
                return False
        for cid, C in self.db.items():
            src = self.src[cid]
            if src[0] == 'leaf':
                lid = src[1]
                if _norm(self.leaves[lid][1]) != C:
                    return False
                continue
            _, a, b, i = src
            if a not in self.db or b not in self.db:
                return False
            if i not in self.db[a] or i not in self.db[b]:
                return False
            if _resolve(self.db[a], self.db[b], i) != C:
                return False
        return True
