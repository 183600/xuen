"""v8.5 QRCC: quorum resolution + cover on top of v8.4 QRC.

QRC closes an instance when resolution over the learned quorum clauses
derives the empty clause.  Resolution is incomplete as a refutation
method for multi-valued clauses, so QRCC adds the semantic cover test:
if the scheduling LP cannot put mass >= 1 on every clause simultaneously
(tau < 1), the clause family plus the LP is a multi-certificate NO proof.

Every clause in the cover family is either a leaf quorum (backed by an
integer Farkas certificate) or a resolution descendant (backed by its
parents).  Thus the cover mixture is a proof object orthogonal to the
DFS: it can close the instance at the root, and the audit replays both
the linear mixture and the resolution DAG.
"""
import sys, time
sys.path[:0] = ['exp/v85', 'exp/v84', 'exp/v73', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
import numpy as np
from scipy.optimize import linprog
from qrc import QRC, GlobalNo
from qcc import mix_certificate, replay_mixture, cols_of


class QRCC(QRC):
    def __init__(self, inst, h, use_cover=True, cover_min_k=1,
                 cover_eps=1e-6, cover_max_k=32, cover_every=True, **kw):
        super().__init__(inst, h, **kw)
        self.use_cover = use_cover
        self.cover_min_k = cover_min_k
        self.cover_eps = cover_eps
        self.cover_max_k = cover_max_k
        self.cover_every = cover_every
        self.cover_calls = 0
        self.cover_hits = 0
        self.cover_tau = None
        self.cover_proof = None
        self.cover_t = 0.0
        self._cover_dirty = True
        self._in_res = False

    def _family(self):
        fam = []
        for cid in sorted(self.active):
            C = self.db[cid]
            E = frozenset((i, t) for i, S in C.items() for t in S)
            fam.append((cid, E))
        fam.sort(key=lambda x: (len(x[1]), x[0]))
        return fam[:self.cover_max_k]

    def _cover_lp(self):
        fam = self._family()
        if len(fam) < self.cover_min_k:
            return None
        A, hi = self.lp.matrix()
        N = self.lp.base.N
        K = len(fam)
        A_ub = np.zeros((A.shape[0] + K, N + 1))
        b_ub = np.zeros(A.shape[0] + K)
        A_ub[:A.shape[0], :N] = A.toarray()
        b_ub[:A.shape[0]] = hi
        for r, (_, E) in enumerate(fam):
            for key in E:
                for cc in cols_of(self.lp, key):
                    A_ub[A.shape[0] + r, cc] -= 1.0
            A_ub[A.shape[0] + r, N] = 1.0
        A_eq = np.zeros((self.lp.n, N + 1))
        A_eq[:, :N] = A[:self.lp.n_eq].toarray()
        c = np.zeros(N + 1)
        c[N] = -1.0
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq,
                      b_eq=np.ones(self.lp.n),
                      bounds=[(0, 1)] * N + [(0, 1)], method='highs')
        self.cover_calls += 1
        if res.status != 0:
            return None
        return -res.fun, res, fam

    def _cover_check(self):
        if not self.use_cover or self.global_no:
            return False
        t0 = time.time()
        got = self._cover_lp()
        self.cover_t += time.time() - t0
        if got is None:
            return False
        tau, res, fam = got
        self.cover_tau = tau
        if tau < 1.0 - self.cover_eps:
            self.cover_hits += 1
            self.cover_proof = ([E for _, E in fam], res)
            self.conflict = (self.conflict or ('cover',))
            self.why_global = 'cover'
            self._global_empty('cover')
            return True
        return False

    def _resolve_closure(self):
        if self._in_res:
            return 0
        self._in_res = True
        try:
            steps = super()._resolve_closure()
        finally:
            self._in_res = False
        self._cover_check()
        return steps

    def _learn(self, F):
        cert, E = super()._learn(F)
        # QRC._branch calls _resolve_closure right after _learn; the cover
        # is evaluated there so that resolution descendants are included.
        return cert, E

    def _stats(self, why):
        st = super()._stats(why)
        st.update(cover_calls=self.cover_calls, cover_hits=self.cover_hits,
                  cover_tau=self.cover_tau, cover_t=self.cover_t,
                  cover_k=(len(self.cover_proof[0]) if self.cover_proof else 0))
        return st

    def audit(self):
        if not super().audit():
            return False
        if self.cover_hits:
            if self.cover_proof is None:
                return False
            clauses, res = self.cover_proof
            mc = mix_certificate(self.lp, clauses, res)
            if mc is None:
                return False
            if not replay_mixture(self.lp, clauses, mc):
                return False
        return True
