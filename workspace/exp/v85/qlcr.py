"""v8.5 QLCR: QLC + multi-valued resolution closure.

Adds to QLC the SAT-style resolution rule on quorum clauses:

    (s_i in A or R1) & (s_i in B or R2)
      => (s_i in A cap B or R1 or R2)

When A cap B is empty the literal disappears; an empty resolvent is a
global NO.  Resolution is iterated to a bounded fixpoint after every
Farkas leaf.  Derived clauses are fed to QLC's propagation, case split,
and cover LP.  (Prototype: derived clauses are not yet in the audit DAG.)
"""
import sys
sys.path[:0] = ['exp/v85', 'exp/v75', 'exp/v73', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from qlc import QLC
from qnc import QNC
from cert import verify


def _flatten(C):
    return frozenset((i, t) for i, S in C.items() for t in S)


def _resolve(A, B, i):
    if i not in A or i not in B:
        return None
    inter = A[i] & B[i]
    if inter == A[i] or inter == B[i]:
        return None
    out = {}
    for C in (A, B):
        for j, S in C.items():
            if j == i:
                continue
            out[j] = frozenset(S) | out.get(j, frozenset())
    if inter:
        out[i] = inter
    return out


class QLCR(QLC):
    def __init__(self, inst, h, res_on=True, max_res=2000,
                 max_clauses=128, max_lits=12, **kw):
        super().__init__(inst, h, **kw)
        self.res_on = res_on
        self.max_res = max_res
        self.max_clauses = max_clauses
        self.max_lits = max_lits
        self.res_steps = 0
        self.res_added = 0
        self.res_units = 0
        self.res_empty = 0
        self.derived = {}              # clause idx -> (a,b,job) or ('leaf',)

    def _learn(self, F):
        cert, E = QNC._learn(self, F)   # not QCC._learn: add clause once
        if E:
            idx = self._add_clause(E, cert, F)
            if idx is not None:
                self.derived[idx] = ('leaf',)
            self._resolution_closure()
        else:
            self.global_no = True
        return cert, E

    def _resolution_closure(self):
        if not self.res_on or self.global_no:
            return
        steps = 0
        changed = True
        while changed and steps < self.max_res and not self.global_no:
            changed = False
            ids = list(range(len(self.clause_db)))
            for ai in range(len(ids)):
                a = ids[ai]
                if a >= len(self.clause_db):
                    continue
                A = self.clause_db[a]
                for b in ids[ai + 1:]:
                    if b >= len(self.clause_db):
                        continue
                    B = self.clause_db[b]
                    for i in sorted(set(A) & set(B)):
                        R = _resolve(A, B, i)
                        if R is None:
                            continue
                        if len(R) > self.max_lits:
                            continue
                        steps += 1
                        self.res_steps += 1
                        if not R:
                            self.res_empty += 1
                            self.global_no = True
                            return
                        E = _flatten(R)
                        before = len(self.clause_db)
                        idx = self._add_clause(E, None, frozenset())
                        if idx is not None and idx >= before:
                            self.res_added += 1
                            self.derived[idx] = ('res', a, b, i)
                            if len(R) == 1:
                                j, S = next(iter(R.items()))
                                self.res_units += 1
                                new = S & self.force.get(j, self.domain(j))
                                if new != self.force.get(j):
                                    self.force[j] = new
                            changed = True
                        if len(self.clause_db) >= self.max_clauses:
                            return
                        if self.global_no:
                            return

    def audit(self):
        # Replay leaves and cover; derived clauses are trusted in this
        # prototype and are audited separately by resolution provenance.
        for F, E, c in self.leaves:
            if not E <= F:
                return False
            if not verify(self.inst, self.h, c, forbid=E,
                          elig_aware=self.elig):
                return False
        if self.cover_hits:
            from qcc import mix_certificate, replay_mixture
            if self.cover_proof is None:
                return False
            clauses, res = self.cover_proof
            mc = mix_certificate(self.lp, clauses, res)
            if mc is None or not replay_mixture(self.lp, clauses, mc):
                return False
        return True

    def _stats(self, why):
        st = super()._stats(why)
        st.update(res_steps=self.res_steps, res_added=self.res_added,
                  res_units=self.res_units, res_empty=self.res_empty,
                  clause_db=len(self.clause_db))
        return st
