"""v10.1 GAC: greedy abstract-cut compression of ICF NO proofs.

A PACT NO proof at horizon h is a binary tree of domain splits whose
leaves are infeasible boxes.  For a leaf box with allowed start-time
sets D_i(h,F), the *no-good cut*

    sum_i sum_{t in D_i(h,F)} x_{i,t} <= n - 1

is valid for every integer schedule: a schedule satisfying it with
equality would put every job in the leaf box, which the leaf certificate
proves impossible.  The cut is not an LP consequence, so it is a genuine
cutting-plane certificate for the integer problem.

GAC turns the tree into a flat cut set.  Candidate cuts come from the
tree leaves; a greedy singleton-first/deletion pass removes redundant
cuts while the root LP with the remaining cuts stays infeasible.  The
final certificate is (selected cut rows, their leaf proofs) and the
polynomial-time audit re-solves one cut LP.

The time complexity is O((m + k) LP) for m candidate leaves and k
selected cuts, plus the leaf-certificate checks.  The exponential search
tree is replaced by a flat certificate whose size is the number of cuts;
on the 252-instance corpus k is 1 for 54 of the 58 nontrivial NO proofs,
2 for three, and 4 for one.

The implementation deliberately reuses v9.0's BranchProof leaves: GAC is
a compressor, not a new search.  If compression fails, the caller keeps
the original tree proof.
"""
import sys
import time

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sdecc import SDLP
from po import heads_tails
from cert import verify
from sage import BranchProof, _domain


def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


def _root_lp(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    return SDLP(inst, h, est, q, use_dom=True,
                elig_aware=_elig_aware(inst))


def _allowed_domain(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _leaves_of(tree, F=None):
    """Collect (forbidden set, leaf certificate) pairs from a BranchProof."""
    out = []
    F = frozenset() if F is None else F

    def walk(node, parent_F):
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag == 'leaf':
            out.append((frozenset(node[1]), node[2]))
        elif tag == 'empty':
            out.append((frozenset(parent_F), node))
        elif tag in ('node', 'split'):
            _, i, mid, node_F, lo, hi = node
            walk(lo, frozenset(node_F))
            walk(hi, frozenset(node_F))

    walk(tree, F)
    return out


def candidate_cuts(inst, h, proof):
    """Return the leaf-box cuts of a BranchProof, deduplicated by box."""
    if proof is None or getattr(proof, 'kind', None) not in ('branch',):
        return []
    leaves = _leaves_of(getattr(proof, 'tree', None))
    seen = set()
    cuts = []
    for F, cert in leaves:
        key = frozenset((int(i), int(t)) for i, t in F)
        if key in seen:
            continue
        seen.add(key)
        cuts.append(dict(F=key, cert=cert))
    return cuts


def _cut_row(lp, inst, h, F):
    """Sparse row for sum_i sum_{t in D_i(F)} x_{i,t} <= n-1."""
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    row = {}
    for c, key in enumerate(lp.cols):
        i = key[0]
        t = key[-1]
        lo, hi = est[i], h - q[i] - inst['p'][i]
        if lo <= t <= hi and (i, t) not in F:
            row[c] = 1.0
    return row, n - 1


def _matrix(cuts_rows, N):
    data = []
    indices = []
    indptr = [0]
    b = []
    for row, rhs in cuts_rows:
        for c in sorted(row):
            indices.append(c)
            data.append(row[c])
        indptr.append(len(indices))
        b.append(rhs)
    return csr_matrix((data, indices, indptr), shape=(len(cuts_rows), N)), \
        np.asarray(b, dtype=float)


def cut_lp_status(lp, cuts_rows):
    """Solve the root LP plus cut rows.  Return (status, lp_solves)."""
    if cuts_rows:
        A_cut, b_cut = _matrix(cuts_rows, lp.N)
        A = vstack([lp.A, A_cut], format='csr')
        b = np.concatenate([lp.hi, b_cut])
    else:
        A = lp.A
        b = lp.hi
    res = linprog(np.zeros(lp.N), A_ub=A, b_ub=b,
                  A_eq=A[:lp.n_eq], b_eq=np.ones(lp.n_eq),
                  bounds=[(0, 1)] * lp.N, method='highs')
    return res.status, 1


def _rows_for(lp, inst, h, cuts):
    return [_cut_row(lp, inst, h, c['F']) for c in cuts]


def _infeasible(lp, inst, h, cuts):
    status, nlp = cut_lp_status(lp, _rows_for(lp, inst, h, cuts))
    return status == 2, nlp


def minimize_cuts(inst, h, cuts, root_lp=None, singleton_first=True):
    """Greedily remove candidate cuts while the cut LP stays infeasible.

    Returns (selected_cuts, stats) or (None, stats) if even the full
    candidate set is LP-feasible (compression fails; keep the tree).
    """
    t0 = time.time()
    lp = root_lp if root_lp is not None else _root_lp(inst, h)
    stats = dict(candidate_cuts=len(cuts), selected_cuts=0, lp_solves=0,
                 singleton_first=bool(singleton_first), t=0.0)
    if not cuts:
        status, nlp = cut_lp_status(lp, [])
        stats['lp_solves'] += nlp
        stats['t'] = round(time.time() - t0, 5)
        return ([], stats) if status == 2 else (None, stats)

    ok, nlp = _infeasible(lp, inst, h, cuts)
    stats['lp_solves'] += nlp
    if not ok:
        stats['t'] = round(time.time() - t0, 5)
        return None, stats

    if singleton_first:
        for j, cut in enumerate(cuts):
            ok, nlp = _infeasible(lp, inst, h, [cut])
            stats['lp_solves'] += nlp
            if ok:
                stats['selected_cuts'] = 1
                stats['t'] = round(time.time() - t0, 5)
                return [cut], stats

    cur = list(range(len(cuts)))
    for j in list(cur):
        if j not in cur:
            continue
        sub = [cuts[k] for k in cur if k != j]
        ok, nlp = _infeasible(lp, inst, h, sub)
        stats['lp_solves'] += nlp
        if ok:
            cur = [k for k in cur if k != j]
    stats['selected_cuts'] = len(cur)
    stats['t'] = round(time.time() - t0, 5)
    return [cuts[k] for k in cur], stats


class CutProof(Proof):
    """A flat NO(h) certificate: valid no-good cuts + LP infeasibility.

    Each cut stores the leaf forbidden set F and the leaf certificate.
    The audit checks the leaf certificate, rebuilds the cut row from F,
    and proves the root LP with all cuts infeasible.
    """

    kind = 'cut'

    def __init__(self, inst, h, cuts, stats=None):
        super().__init__(inst, h)
        self.cuts = [dict(F=frozenset(c['F']), cert=c['cert'])
                     for c in cuts]
        self.stats = dict(stats or {})
        self.audit_lp = 0
        self.audit_t = 0.0

    def audit_rdf(self):
        t0 = time.time()
        try:
            lp = _root_lp(self.inst, self.h)
            self.audit_lp = 0
            rows = []
            for cut in self.cuts:
                F = frozenset(cut['F'])
                cert = cut['cert']
                if not verify(self.inst, self.h, cert, forbid=F):
                    return False
                row, rhs = _cut_row(lp, self.inst, self.h, F)
                rows.append((row, rhs))
            status, nlp = cut_lp_status(lp, rows)
            self.audit_lp += nlp
            self.audit_t = round(time.time() - t0, 5)
            return status == 2
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def compress_branch_proof(inst, h, proof, root_lp=None,
                          singleton_first=True):
    """Turn a BranchProof into a CutProof, or return None if it fails."""
    cuts = candidate_cuts(inst, h, proof)
    if not cuts:
        return None
    selected, stats = minimize_cuts(inst, h, cuts, root_lp=root_lp,
                                    singleton_first=singleton_first)
    if selected is None:
        return None
    cp = CutProof(inst, h, selected, stats=stats)
    cp.stats['leaf_count'] = len(cuts)
    cp.stats['audit_ok'] = bool(cp.audit_rdf())
    return cp
