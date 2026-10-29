"""v8.3 QCDCL-ALC: quorum-clause-driven CDCL on top of v7.1 QNC.

The v7.1 leaf certificate is a globally valid *quorum clause*

    C(E) = OR_i (s_i in E_i),     LP(D \\ E) infeasible.

v7.1 only uses it for (a) full falsification checks and (b) single-job
force.  This module treats the set of quorum clauses as a real clause
database over a multi-valued variable s_i:

  * unit propagation: if all literals but one are falsified by the current
    domains, intersect that job's domain with its literal;
  * multi-valued resolution: two clauses with disjoint literals on one job
    resolve on that job (same-job literals are merged by union);
  * clause-guided branching: split a job exactly at a clause literal, so
    one branch satisfies it and the other falsifies it (and therefore
    makes the clause unit or empty on the other literals);
  * conflict-directed backjumping: every forbidden column carries a set of
    decision levels; a conflict returns that set instead of chronologically
    backtracking.

The search is deterministic: clause insertion order, job order, literal
choice and branch order are all fixed by keys, never by a clock or RNG.
"""
import sys, collections, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
from qnc import QNC, Budget, farkas_int
from cert import verify


class QCDCL(QNC):
    def __init__(self, inst, h, use_prop=True, use_res=True, use_guide=True,
                 use_backjump=True, max_clauses=256, max_res=64,
                 max_res_lits=4, branch_policy='small', guide_policy='tight',
                 probe_on=True, probe_cap=6, probe_jobs=3, probe_gate=False,
                 probe_mode='unit', probe_forbid='probe',
                 **kw):
        super().__init__(inst, h, **kw)
        self.use_prop = use_prop
        self.use_res = use_res
        self.use_guide = use_guide
        self.use_backjump = use_backjump
        self.max_clauses = max_clauses
        self.max_res = max_res
        self.max_res_lits = max_res_lits
        self.branch_policy = branch_policy
        self.guide_policy = guide_policy
        self.probe_on = probe_on
        self.probe_cap = probe_cap
        self.probe_jobs = probe_jobs
        self.probe_gate = probe_gate
        self.probe_mode = probe_mode
        self.probe_forbid = probe_forbid
        self.probes = 0
        self.probe_units = 0
        self.probe_clauses = 0
        self.probe_leaves = []
        self.probe_tried = set()
        self.probe_off = False
        self._start_cols = collections.defaultdict(list)
        for c, key in enumerate(self.lp.cols):
            self._start_cols[(key[0], key[-1])].append(c)

        self.clause_db = []                 # normalized dict job -> frozenset
        self.clause_src = []                # provenance records
        self.clause_key = []                # canonical key
        self.clause_key_set = set()
        self.by_job = collections.defaultdict(list)
        self.res_steps = []                 # (a,b,job,child)
        self.unit_steps = []                # (clause_idx, job, forced_set)
        self.global_empty = False

        self.unit_props = 0
        self.prop_conflicts = 0
        self.clause_conflicts = 0
        self.backjumps = 0
        self.branch_clause = 0
        self.branch_median = 0
        self.empty_branches = 0
        self._root_dom = {i: frozenset(S) for i, S in self._dom.items()}

    # ------------------------------------------------------------- clauses
    def _norm(self, terms):
        d = {}
        for (i, t) in terms:
            d.setdefault(i, set()).add(t)
        out = {}
        for i, S in d.items():
            S = frozenset(S)
            if not S:
                continue
            if S >= self._root_dom[i]:
                return None          # tautology: s_i in E_i always
            out[i] = S
        return out

    def _ckey(self, C):
        return tuple(sorted((i, tuple(sorted(S))) for i, S in C.items()))

    def _subsumes(self, A, B):
        if not set(A) <= set(B):
            return False
        return all(S <= B[i] for i, S in A.items())

    def _add_clause(self, C, src, do_res=True):
        if C is None:
            return None
        if not C:
            self.global_empty = True
            return None
        k = self._ckey(C)
        if k in self.clause_key_set:
            return None
        if any(self._subsumes(A, C) for A in self.clause_db):
            return None
        if len(self.clause_db) >= self.max_clauses:
            return None
        idx = len(self.clause_db)
        self.clause_db.append(C)
        self.clause_src.append(src)
        self.clause_key.append(k)
        self.clause_key_set.add(k)
        for i in C:
            self.by_job[i].append(idx)
        if len(C) == 1:
            i, S = next(iter(C.items()))
            new = S & self.force.get(i, self.domain(i))
            self.unit_steps.append((idx, i, frozenset(new)))
            self.force[i] = frozenset(new)
            if not new:
                self.global_empty = True
        if do_res and self.use_res:
            self._resolve_closure(idx)
        return idx

    def _resolve_closure(self, start_idx):
        if self.global_empty:
            return
        queue = collections.deque([start_idx])
        done = set()
        budget = self.max_res
        while queue and budget > 0 and not self.global_empty:
            a = queue.popleft()
            if a in done:
                continue
            done.add(a)
            A = self.clause_db[a]
            for i in sorted(A):
                Ai = A[i]
                for b in list(self.by_job.get(i, ())):
                    if b == a or budget <= 0:
                        continue
                    B = self.clause_db[b]
                    if i not in B:
                        continue
                    if Ai & B[i]:
                        continue                    # not disjoint
                    terms = []
                    for j, S in A.items():
                        if j != i:
                            terms.extend((j, t) for t in S)
                    for j, S in B.items():
                        if j != i:
                            terms.extend((j, t) for t in S)
                    R = self._norm(terms)
                    if R is None:
                        continue
                    if not R:
                        self.res_steps.append((a, b, i, -1))
                        self.global_empty = True
                        break
                    if len(R) > self.max_res_lits:
                        continue
                    k = self._ckey(R)
                    if k in self.clause_key_set:
                        continue
                    if any(self._subsumes(D, R) for D in self.clause_db):
                        continue
                    if len(self.clause_db) >= self.max_clauses:
                        continue
                    budget -= 1
                    c = len(self.clause_db)
                    self.clause_db.append(R)
                    self.clause_src.append(('res', a, b, i))
                    self.clause_key.append(k)
                    self.clause_key_set.add(k)
                    for j in R:
                        self.by_job[j].append(c)
                    self.res_steps.append((a, b, i, c))
                    if len(R) == 1:
                        i2, S2 = next(iter(R.items()))
                        new = S2 & self.force.get(i2, self.domain(i2))
                        self.unit_steps.append((c, i2, frozenset(new)))
                        self.force[i2] = frozenset(new)
                        if not new:
                            self.global_empty = True
                            break
                    queue.append(c)
                if self.global_empty:
                    break

    # ---------------------------------------------------------- propagate
    def _propagate(self, dom, reason):
        """Domain propagation fixpoint.  Returns ('ok',) or ('conflict', R, cause)."""
        changed = True
        for i, S in self.force.items():
            rem = dom[i] - S
            if rem:
                for t in rem:
                    reason[(i, t)] = 0
                    dom[i].discard(t)
                if not dom[i]:
                    return ('conflict', 0, ('force', i))
        while changed:
            changed = False
            for ci, C in enumerate(self.clause_db):
                live = []
                sat = False
                for i, S in C.items():
                    inter = dom[i] & S
                    if not inter:
                        continue
                    if dom[i] <= S:
                        sat = True
                        break
                    live.append((i, S))
                if sat:
                    continue
                if not live:
                    R = 0
                    for i, S in C.items():
                        for t in S:
                            R |= reason.get((i, t), 0)
                    self.clause_conflicts += 1
                    return ('conflict', R, ('clause', ci))
                if len(live) == 1:
                    i, S = live[0]
                    newD = dom[i] & S
                    rem = dom[i] - newD
                    if not rem:
                        continue
                    r = 0
                    for j, Sj in C.items():
                        if j == i:
                            continue
                        for t in Sj:
                            r |= reason.get((j, t), 0)
                    for t in rem:
                        reason[(i, t)] = r
                        dom[i].discard(t)
                    self.unit_props += 1
                    if not dom[i]:
                        R = 0
                        for t in self._root_dom[i]:
                            R |= reason.get((i, t), 0)
                        self.prop_conflicts += 1
                        return ('conflict', R, ('empty', i))
                    changed = True
                    break
        return ('ok', 0, None)

    def _bounds(self, dom):
        b = []
        for key in self.lp.cols:
            b.append((0, 1) if key[-1] in dom[key[0]] else (0, 0))
        return b

    def _forbid_set(self, dom):
        return {(i, t) for i in self._root_dom for t in self._root_dom[i]
                if t not in dom[i]}

    # ------------------------------------------------------------- analyse
    def _analyse(self, F):
        t0 = time.time()
        self.cert_calls += 1
        cert, s = farkas_int(self.lp, F)
        self.cert_t += time.time() - t0
        if cert is None:
            self.cert_fail += 1
            return None
        E = frozenset((key[0], key[-1]) for cc, key in enumerate(self.lp.cols)
                      if (key[0], key[-1]) in F and s[cc] < 0)
        if E != frozenset(F) and not verify(self.inst, self.h, cert,
                                            forbid=E, elig_aware=self.elig):
            E = frozenset(F)
        return cert, E

    def _learn(self, F):
        got = self._analyse(F)
        if got is None:
            return None, frozenset(F)
        cert, E = got
        self.leaves.append((frozenset(F), E, cert))
        if E:
            self.clauses.append(E)
            self._add_clause(self._norm(E), ('cert', len(self.leaves) - 1))
        else:
            self.global_empty = True
        return cert, E

    # -------------------------------------------------------------- branch
    def _median_split(self, dom, z):
        frac = []
        for cc, key in enumerate(self.lp.cols):
            if key[-1] not in dom[key[0]]:
                continue
            if 1e-7 < z[cc] < 1 - 1e-7:
                frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
        if not frac:
            return None
        frac.sort()
        _, cc, i, t = frac[0]
        times = sorted(dom[i])
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
        A = frozenset(tt for tt in times if tt <= mid)
        B = frozenset(tt for tt in times if tt > mid)
        if not A or not B:
            return None
        return i, A, B

    def _clause_split(self, dom):
        cand = []
        for ci, C in enumerate(self.clause_db):
            live = []
            sat = False
            for i, S in C.items():
                inter = dom[i] & S
                if not inter:
                    continue
                if dom[i] <= S:
                    sat = True
                    break
                live.append((i, inter, S))
            if sat or len(live) < 2:
                continue
            for i, inter, S in live:
                A = inter
                B = dom[i] - S
                if not A or not B:
                    continue
                cand.append((len(live), min(len(A), len(B)),
                             ci, i, frozenset(A), frozenset(B)))
        if not cand:
            return None
        if self.guide_policy == 'tight':
            tight = [c for c in cand if c[0] <= 2 and c[1] <= 2]
            if tight:
                cand = tight
        cand.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        _, _, ci, i, A, B = cand[0]
        return i, A, B

    def _cut_degree(self):
        inc = collections.Counter()
        for (i, j, t) in self.lp.cuts:
            inc[i] += 1
            inc[j] += 1
        return inc

    def _rank_jobs(self, dom, z):
        supp = collections.defaultdict(list)
        for c, key in enumerate(self.lp.cols):
            i, t = key[0], key[-1]
            if t not in dom[i]:
                continue
            if 1e-7 < z[c] < 1 - 1e-7:
                supp[i].append((float(z[c]), t))
        inc = self._cut_degree()
        cand = []
        for i, atoms in supp.items():
            if len(atoms) < 2:
                continue
            atoms.sort(key=lambda a: (-a[0], a[1]))
            cand.append((len(atoms) != 2, -inc[i], i, atoms))
        cand.sort(key=lambda x: (x[0], x[1], x[2]))
        return cand

    def _probe_delete(self, dom, E):
        if self.lp_solves >= self.budget:
            raise Budget
        b = []
        for key in self.lp.cols:
            i, t = key[0], key[-1]
            b.append((0, 1) if (t in dom[i] and (i, t) not in E) else (0, 0))
        res = self.lp.solve(b)
        self.lp_solves += 1
        self.probes += 1
        if res.status != 2:
            return False, None, None
        if self.probe_forbid == 'probe':
            F = set(E)
        else:
            F = self._forbid_set(dom) | set(E)
        cert, s = farkas_int(self.lp, F)
        if cert is None:
            return True, None, None
        Ep = frozenset((key[0], key[-1]) for cc, key in enumerate(self.lp.cols)
                       if (key[0], key[-1]) in F and s[cc] < 0)
        if Ep != frozenset(F) and not verify(self.inst, self.h, cert,
                                             forbid=Ep, elig_aware=self.elig):
            if self.probe_forbid == 'probe':
                return True, None, None
            Ep = frozenset(F)
        return True, cert, Ep

    def _root_probe(self, dom, z):
        if self.probe_mode == 'unit':
            return self._root_probe_unit(dom, z)
        added = False
        for _, _, i, atoms in self._rank_jobs(dom, z)[:self.probe_jobs]:
            for mass, t in atoms[:2]:
                if self.probes >= self.probe_cap or self.probe_off:
                    return ('clause' if added else None)
                key = (i, t)
                if key in self.probe_tried:
                    continue
                self.probe_tried.add(key)
                ok, cert, Ep = self._probe_delete(dom, {key})
                if not ok:
                    if self.probe_gate and not added:
                        self.probe_off = True
                        return None
                    continue
                if cert is None or Ep is None:
                    continue
                self.probe_leaves.append((frozenset(Ep), cert))
                before = len(self.clause_db)
                self._add_clause(self._norm(Ep), ('probe', len(self.probe_leaves) - 1))
                if self.global_empty:
                    return 'refuted'
                if len(self.clause_db) > before:
                    added = True
                    self.probe_clauses += 1
                jobs = {j for j, _ in Ep}
                if len(jobs) == 1:
                    j = next(iter(jobs))
                    S = frozenset(tt for (jj, tt) in Ep if jj == j)
                    if S & self.force.get(j, self.domain(j)) != self.force.get(j, self.domain(j)):
                        self.probe_units += 1
                        return 'unit'
        return ('clause' if added else None)

    def _root_probe_unit(self, dom, z):
        added = False
        for _, _, i, atoms in self._rank_jobs(dom, z)[:self.probe_jobs]:
            units = []
            for mass, t in atoms[:2]:
                if self.probes >= self.probe_cap or self.probe_off:
                    return ('clause' if added else None)
                key = (i, t)
                if key in self.probe_tried:
                    continue
                self.probe_tried.add(key)
                ok, cert, Ep = self._probe_delete(dom, {key})
                if not ok:
                    if self.probe_gate and not units and not added:
                        self.probe_off = True
                        return None
                    continue
                if cert is None or Ep is None or len(Ep) != 1:
                    continue
                units.append((t, cert, Ep))
            if len(units) == 2 and units[0][0] != units[1][0]:
                for t, cert, Ep in units:
                    self.probe_leaves.append((frozenset(Ep), cert))
                    before = len(self.clause_db)
                    self._add_clause(self._norm(Ep), ('probe', len(self.probe_leaves) - 1))
                    if len(self.clause_db) > before:
                        added = True
                        self.probe_clauses += 1
                    if self.global_empty:
                        return 'refuted'
                continue
            if units:
                t, cert, Ep = units[0]
                self.probe_leaves.append((frozenset(Ep), cert))
                before = len(self.clause_db)
                self._add_clause(self._norm(Ep), ('probe', len(self.probe_leaves) - 1))
                if self.global_empty:
                    return 'refuted'
                if len(self.clause_db) > before:
                    added = True
                    self.probe_clauses += 1
                S = frozenset(tt for (jj, tt) in Ep if jj == i)
                if S & self.force.get(i, self.domain(i)) != self.force.get(i, self.domain(i)):
                    self.probe_units += 1
                    return 'unit'
        return ('clause' if added else None)

    def _choose_split(self, dom, z):
        if self.use_guide:
            sp = self._clause_split(dom)
            if sp is not None:
                self.branch_clause += 1
                return sp
        sp = self._median_split(dom, z)
        if sp is not None:
            self.branch_median += 1
        return sp

    # -------------------------------------------------------------- search
    def _search(self, dom, reason, level, nodecap, max_rounds, topk):
        counted = False
        while True:
            if self.global_empty:
                return 0
            for i in range(self.n):
                if not dom.get(i):
                    return 0
            st = self._propagate(dom, reason) if self.use_prop else ('ok', 0, None)
            if st[0] == 'conflict':
                R = st[1]
                if R == 0:
                    return 0
                if self.use_backjump:
                    self.backjumps += 1
                    return R
                return 0 if level == 0 else (1 << level)
            if not counted:
                self.nodes += 1
                if self.nodes > nodecap:
                    raise Budget
                counted = True
            bounds = self._bounds(dom)
            res, z = self._solve(bounds, max_rounds, topk)
            if res.status == 2:
                F = self._forbid_set(dom)
                cert, E = self._learn(F)
                if self.global_empty:
                    return 0
                R = 0
                for (i, t) in E:
                    R |= reason.get((i, t), 0)
                if R == 0:
                    return 0
                if self.use_backjump:
                    self.backjumps += 1
                    return R
                return 0 if level == 0 else (1 << level)
            if z is None:
                return 0
            frac = False
            for cc, key in enumerate(self.lp.cols):
                if key[-1] not in dom[key[0]]:
                    continue
                if 1e-7 < z[cc] < 1 - 1e-7:
                    frac = True
                    break
            if not frac:
                return -1                       # YES
            if level == 0 and self.probe_on and not self.probe_off \
                    and self.probes < self.probe_cap:
                act = self._root_probe(dom, z)
                if act == 'refuted':
                    return 0
                if act == 'unit':
                    continue
            break
        sp = self._choose_split(dom, z)
        if sp is None:
            return -1
        i, A, B = sp
        d = level + 1
        bit = 1 << d

        # branch 0: forbid B, i.e. satisfy the literal (s_i in A)
        dom0 = {j: set(S) for j, S in dom.items()}
        r0 = dict(reason)
        for t in B:
            r0[(i, t)] = bit
        dom0[i] = set(A)
        if not dom0[i]:
            self.empty_branches += 1
            r0 = 0
        else:
            rr = self._search(dom0, r0, d, nodecap, max_rounds, topk)
            if rr == -1:
                return -1
            if rr == 0:
                return 0
            if not (rr & bit):
                # first branch fails independently of decision d; the
                # whole node is infeasible, skip the second branch.
                return rr
            r0 = rr
        # branch 1: forbid A, i.e. falsify the literal (s_i in B)
        dom1 = {j: set(S) for j, S in dom.items()}
        r1 = dict(reason)
        for t in A:
            r1[(i, t)] = bit
        dom1[i] = set(B)
        if not dom1[i]:
            self.empty_branches += 1
            rr1 = 0
        else:
            # re-propagate the base state: branch 0 may have learned global
            # unit clauses that shrink it.
            base = {j: set(S) for j, S in dom.items()}
            base_r = dict(reason)
            st1 = self._propagate(base, base_r) if self.use_prop else ('ok', 0, None)
            if st1[0] == 'conflict':
                rr1 = st1[1] if st1[1] else 0
                if self.use_backjump and (rr1 & bit):
                    rr1 &= ~bit
            else:
                for t in A:
                    base_r[(i, t)] = bit
                base[i] = set(B)
                rr1 = self._search(base, base_r, d, nodecap, max_rounds, topk)
        if rr1 == -1:
            return -1
        if rr1 == 0:
            if self.use_backjump and (r0 & bit):
                rr = r0 & ~bit
                return rr if rr else 0
            return 0
        if not (rr1 & bit):
            return rr1
        if self.use_backjump:
            rr = (r0 | rr1) & ~bit
            return rr if rr else 0
        return 0

    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        self.budget = budget
        try:
            root = {i: set(S) for i, S in self._root_dom.items()}
            v = self._search(root, {}, 0, nodecap, max_rounds, topk)
            if v == -1:
                verdict, why = True, 'yes'
            else:
                verdict, why = False, 'no'
        except Budget:
            verdict, why = None, 'budget'
        return verdict, self._stats(why)

    def _stats(self, why):
        st = super()._stats(why)
        st.update(unit_props=self.unit_props, prop_conflicts=self.prop_conflicts,
                  clause_conflicts=self.clause_conflicts,
                  backjumps=self.backjumps, branch_clause=self.branch_clause,
                  branch_median=self.branch_median,
                  empty_branches=self.empty_branches,
                  db=len(self.clause_db), res_steps=len(self.res_steps),
                  unit_steps=len(self.unit_steps),
                  probes=self.probes, probe_units=self.probe_units,
                  probe_clauses=self.probe_clauses,
                  probe_off=self.probe_off,
                  global_empty=self.global_empty)
        return st

    def audit(self):
        """Replay all theory leaves and all resolution steps."""
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        for E, c in self.probe_leaves:
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        for a, b, i, c in self.res_steps:
            if c < 0:
                continue
            A, B = self.clause_db[a], self.clause_db[b]
            terms = []
            for j, S in A.items():
                if j != i:
                    terms.extend((j, t) for t in S)
            for j, S in B.items():
                if j != i:
                    terms.extend((j, t) for t in S)
            R = self._norm(terms)
            if R is None or R != self.clause_db[c]:
                return False
        return True
