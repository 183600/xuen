"""Canonical CNF transformation for fixed-horizon scheduling.

The encoding is the standard time-indexed one-hot model.  It is kept
deterministic so that a certificate can rebuild the CNF from (inst, h)
and compare its digest; no CNF is trusted from the generator.

Variables are numbered by a stable traversal:
    for i, for k in sorted(elig[i]), for t in [est_i, h-q_i-p_i]
A variable x[i,k,t] means job i starts on machine k at time t.

`box_assumptions(inst,h,lo,hi)` returns the negative literals that
exclude starts outside the interval box [lo_i, hi_i].  Solving the CNF
under these assumptions is exactly the fixed-h decision for the box.
"""
import hashlib
import sys

sys.path[:0] = ['exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from po import heads_tails


def domains(inst, h):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    out = []
    for i in range(n):
        lo, hi = est[i], h - q[i] - p[i]
        out.append((int(lo), int(hi)))
    return out


def encode(inst, h, forbid=()):
    """Return (clauses, var, dom).  `forbid` is a set of (i,k,t)."""
    n, m, p = inst['n'], inst['m'], inst['p']
    dom = domains(inst, h)
    var = {}
    for i in range(n):
        lo, hi = dom[i]
        if lo > hi:
            return None, None, dom
        for k in sorted(inst['elig'][i]):
            for t in range(lo, hi + 1):
                if (i, k, t) in forbid:
                    continue
                var[(i, k, t)] = len(var) + 1
    if not var:
        return None, None, dom

    clauses = []

    def add(cl):
        s = set(cl)
        if any(-l in s for l in s):
            return
        if not s:
            clauses.append([])
            return
        clauses.append(sorted(s))

    # exactly one start per job
    for i in range(n):
        lits = [v for (j, k, t), v in var.items() if j == i]
        if not lits:
            return None, None, dom
        add(lits)
        for a in range(len(lits)):
            for b in range(a + 1, len(lits)):
                add([-lits[a], -lits[b]])

    # precedence
    for i in range(n):
        vi = [(k, t, v) for (ii, k, t), v in var.items() if ii == i]
        for j in inst['succ'][i]:
            vj = [(l, u, v) for (jj, l, u), v in var.items()
                  if jj == j]
            for k, t, a in vi:
                for l, u, b in vj:
                    if u < t + p[i]:
                        add([-a, -b])

    # machine capacity
    for k in range(m):
        jobs = [i for i in range(n) if k in inst['elig'][i]]
        for x in range(len(jobs)):
            i = jobs[x]
            vi = [(t, v) for (ii, kk, t), v in var.items()
                  if ii == i and kk == k]
            for y in range(x + 1, len(jobs)):
                j = jobs[y]
                vj = [(u, v) for (jj, kk, u), v in var.items()
                      if jj == j and kk == k]
                for t, a in vi:
                    for u, b in vj:
                        if t < u + p[j] and u < t + p[i]:
                            add([-a, -b])
    return clauses, var, dom


def digest(clauses, nvars):
    h = hashlib.sha256()
    h.update(('v%d\n' % nvars).encode())
    for cl in clauses:
        h.update((' '.join(map(str, cl)) + '\n').encode())
    return h.hexdigest()


def box_assumptions(inst, h, lo, hi, var):
    """Negative literals excluding starts outside [lo_i,hi_i]."""
    ass = []
    for (i, k, t), v in var.items():
        if t < lo[i] or t > hi[i]:
            ass.append(-v)
    return sorted(ass)


def model_schedule(inst, h, var, model):
    starts = [None] * inst['n']
    mach = [None] * inst['n']
    pos = {v: k for k, v in enumerate(model, 1)}
    for (i, k, t), v in var.items():
        if pos.get(v, -1) > 0:
            if starts[i] is not None:
                return None
            starts[i] = t
            mach[i] = k
    if any(x is None for x in starts):
        return None
    return starts, mach
