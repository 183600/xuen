"""v9.2 GCC-ICF: greedy cover-cut certificates on top of ICF-PACT.

The trusted outer state is unchanged:

    (L, U, s, m, pi)   with   pi : NO(L-1), Cmax(s)=U, L<=U.

The new probe oracle first tries to close h at the root with a small
branch-and-cut loop.  A cover cut is a valid inequality for integer
schedules: if a set C of jobs can each be fully placed in a window W on
one machine and sum(p_i, i in C) > |W|, then at most |C|-1 of them can be
fully placed there.  The cut is separated greedily and the LP is re-solved
until it is infeasible or no violated cover remains.  An infeasible
cut-augmented LP yields an integer Farkas certificate whose cut rows are
checked combinatorially by CutLeafProof.audit_rdf.  If the cut loop does
not close, the probe falls back to the v9.0 PACT oracle, so soundness does
not depend on the cut layer finding anything.
"""
import sys
import time

sys.path[:0] = ['exp/v9f', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from apex import Proof
from sdecc import SDLP
from po import heads_tails
from cert import _farkas_lp, _row_meta, DENS, integer_certificate
from pact import PACT, pact_decide
from icf import (PartialCertificate, ICFCertificate, CertLeafProof,
                 cmax, corpora)
from rdf import check_schedule


def _elig_aware(inst):
    return any(len(set(inst['elig'][i])) < inst['m']
               for i in range(inst['n']))


def _cut_row(base, cut):
    a, b, k, C = cut
    row = sp.lil_matrix((1, base.N))
    for i in C:
        lo = max(a, base.est[i])
        hi = min(b - base.p[i], base.T - base.q[i] - base.p[i])
        for t in range(lo, hi + 1):
            key = (i, k, t) if base.elig_aware else (i, t)
            if key in base.idx:
                row[0, base.idx[key]] = 1.0
    return row.tocsr()


class CutLP:
    """Base SDLP plus appended cover-cut rows."""

    def __init__(self, base, cuts):
        self.base = base
        for name in ('inst', 'T', 'n', 'm', 'p', 'n_eq', 'N', 'cols',
                     'idx', 'elig_aware', 'elig', 'est', 'q',
                     'use_expect', 'use_dom'):
            setattr(self, name, getattr(base, name))
        self.cuts = list(cuts)
        rows = [_cut_row(base, cut) for cut in self.cuts]
        if rows:
            self.A = sp.vstack([base.A] + rows).tocsr()
            rhs = [len(cut[3]) - 1 for cut in self.cuts]
            self.hi = np.concatenate([base.hi, np.asarray(rhs, float)])
        else:
            self.A = base.A
            self.hi = base.hi

    def solve(self, bounds=None):
        if bounds is None:
            bounds = (0, 1)
        return linprog(np.zeros(self.N), A_ub=self.A, b_ub=self.hi,
                       A_eq=self.A[:self.n_eq], b_eq=np.ones(self.n),
                       bounds=bounds, method='highs')


def verify_cut(inst, h, cert, forbid=None):
    """Exact replay of a cut-augmented Farkas certificate."""
    n, m, p = inst['n'], inst['m'], inst['p']
    forbid = set(forbid or ())
    est, q = heads_tails(inst, 0, [0] * n)
    if cert.get('kind') == 'cp':
        i = cert['job']
        return est[i] + p[i] + q[i] > h
    if cert.get('kind') != 'cut-packing':
        return False
    elig_aware = _elig_aware(inst)
    cut_coeff = {}
    cut_rhs = 0
    for a, b, k, C, mu in cert.get('cuts', []):
        if mu < 0 or not (0 <= a < b <= h):
            return False
        if len(set(C)) != len(C) or sum(p[i] for i in C) <= b - a:
            return False
        for i in C:
            if not (0 <= i < n):
                return False
            if k is not None and k not in inst['elig'][i]:
                return False
            lo = max(a, est[i])
            hi = min(b - p[i], h - q[i] - p[i])
            if lo > hi:
                return False
            for t in range(lo, hi + 1):
                if (i, t) in forbid:
                    continue
                key = (i, k, t) if elig_aware else (i, t)
                cut_coeff[key] = cut_coeff.get(key, 0) + mu
        cut_rhs += mu * (len(C) - 1)
    beta = {}
    for k, t, w in cert['beta']:
        beta[(k, t)] = beta.get((k, t), 0) + w
    lam = {}
    for i, j, t, w in cert['dom']:
        lam[(i, j, t)] = lam.get((i, j, t), 0) + w
    for i in range(n):
        lo, hi = est[i], h - q[i] - p[i]
        if lo > hi:
            return False
        for s in range(lo, hi + 1):
            if (i, s) in forbid:
                continue
            val = cert['alpha'][i]
            if elig_aware:
                for k in inst['elig'][i]:
                    val += sum(beta.get((k, u), 0)
                               for u in range(s, min(s + p[i], h)))
                    val += cut_coeff.get((i, k, s), 0)
            else:
                val += sum(beta.get((None, u), 0)
                           for u in range(s, min(s + p[i], h)))
                val += cut_coeff.get((i, s), 0)
            for j in inst['succ'][i]:
                val -= sum(w for (a, b, t), w in lam.items()
                           if a == i and b == j and t >= s)
            for k in inst['pred'][i]:
                val += sum(w for (a, b, t), w in lam.items()
                           if a == k and b == i and t >= s - p[k])
            if val < 0:
                return False
    obj = sum(cert['alpha'])
    if elig_aware:
        obj += sum(w for w in beta.values())
    else:
        obj += m * sum(w for w in beta.values())
    obj += cut_rhs
    return obj < 0 and (cert.get('obj') is None or cert.get('obj') == obj)


def integer_cut_certificate(lp, inst, h, dens=DENS):
    """Integer Farkas certificate for a CutLP, or None."""
    r = _farkas_lp(lp)
    if r.status != 0 or r.fun >= 0:
        return None
    n = lp.n
    A = lp.A.tocsr()
    meta = _row_meta(lp.base)
    rbase = A.shape[0] - lp.n_eq - len(lp.cuts)
    for D in dens:
        y = np.rint(r.x * D).astype(np.int64)
        if A.T.dot(y).min() < 0:
            continue
        bt = int(lp.hi[n:].dot(y[n:])) + int(y[:n].sum())
        if bt >= 0:
            continue
        yb = y[n:]
        cert = dict(
            kind='cut-packing', scale=D,
            beta=[(m[1], m[2], int(yb[k]))
                  for k, m in enumerate(meta) if m[0] == 'cap' and yb[k]],
            dom=[(m[1], m[2], m[3], int(yb[k]))
                 for k, m in enumerate(meta) if m[0] == 'dom' and yb[k]],
            exp=[(m[1], m[2], int(yb[k]))
                 for k, m in enumerate(meta) if m[0] == 'exp' and yb[k]],
            alpha=[int(v) for v in y[:n]], obj=bt, farkas=r.fun,
            cuts=[])
        for j, cut in enumerate(lp.cuts):
            mu = int(y[n + rbase + j])
            if mu:
                cert['cuts'].append(tuple(cut) + (mu,))
        if verify_cut(inst, h, cert):
            return cert
    return None


def _prefix_mass(base, z):
    pref = {}
    for c, key in enumerate(base.cols):
        i = key[0]
        k = key[1] if base.elig_aware else None
        t = key[-1]
        arr = pref.get((i, k))
        if arr is None:
            arr = [0.0] * (base.T + 1)
            pref[(i, k)] = arr
        arr[t + 1] += float(z[c])
    for arr in pref.values():
        for t in range(base.T):
            arr[t + 1] += arr[t]
    return pref


def _items_for(base, pref, a, b, k):
    items = []
    for i in range(base.n):
        if k is not None and k not in base.elig[i]:
            continue
        lo = max(a, base.est[i])
        hi = min(b - base.p[i], base.T - base.q[i] - base.p[i])
        if lo > hi:
            continue
        arr = pref.get((i, k))
        if arr is None:
            continue
        mass = arr[hi + 1] - arr[lo]
        if mass <= 1e-9:
            continue
        items.append((base.p[i], mass, i))
    return items


def _cover_from(items, W, order):
    seq = sorted(items, key=order)
    C = []
    total = 0.0
    lhs = 0.0
    for pi, mass, i in seq:
        C.append([pi, mass, i])
        total += pi
        lhs += mass
        if total > W:
            break
    if total <= W:
        return None
    changed = True
    while changed:
        changed = False
        best = None
        for j, (pj, vj, ij) in enumerate(C):
            if total - pj > W and vj < 1 - 1e-9:
                key = (1 - vj, -pj)
                if best is None or key > best[0]:
                    best = (key, j)
        if best is not None:
            _, j = best
            total -= C[j][0]
            lhs -= C[j][1]
            C.pop(j)
            changed = True
    C = tuple(sorted(x[2] for x in C))
    viol = lhs - (len(C) - 1)
    if viol <= 1e-5:
        return None
    return C, viol


def separate_covers(base, z, h, cap=64):
    """Greedy violated cover cuts, strongest first."""
    n, m = base.n, base.m
    pref = _prefix_mass(base, z)
    out = []
    for a in range(h):
        for b in range(a + 1, h + 1):
            W = b - a
            for k in (range(m) if base.elig_aware else [None]):
                items = _items_for(base, pref, a, b, k)
                if len(items) < 2:
                    continue
                orders = (
                    lambda x: (x[0], -x[1]),
                    lambda x: (-x[0], -x[1]),
                    lambda x: (-x[1], x[0]),
                )
                for order in orders:
                    got = _cover_from(items, W, order)
                    if got is None:
                        continue
                    C, viol = got
                    out.append((viol, a, b, k, C))
    out.sort(key=lambda x: (-x[0], x[2] - x[1], len(x[4])))
    seen = set()
    uniq = []
    for row in out:
        key = (row[1], row[2], row[3], row[4])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
        if len(uniq) >= cap:
            break
    return uniq


class CutLeafProof(Proof):
    """A NO(h) leaf closed by a cut-augmented Farkas certificate."""

    kind = 'gcc-leaf'

    def __init__(self, inst, h, F, cert):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.cert = cert

    def audit_rdf(self):
        try:
            return bool(self.cert is not None and
                        verify_cut(self.inst, self.h, self.cert,
                                   forbid=self.forbid0))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def cut_loop(inst, h, forbid0=None, max_cuts=12, cut_cap=64):
    """Try to close h at the root by greedy cover cuts."""
    t0 = time.time()
    F = frozenset(forbid0 or ())
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    ea = _elig_aware(inst)
    base = SDLP(inst, h, est, q, use_dom=True, elig_aware=ea, forbid=F)
    res = base.solve()
    stats = dict(lp_solves=1, cert_lp=0, cuts=0, closed=False,
                 status=res.status, base_res=res, base=base,
                 reason='base-infeasible' if res.status == 2 else
                        ('base-other' if res.status != 0 else 'open'))
    if res.status == 2:
        cert = integer_certificate(inst, h, use_dom=True,
                                   elig_aware=ea, forbid=F)
        stats['cert_lp'] = 1
        if cert is not None and verify_cut(inst, h, cert, forbid=F):
            stats['proof'] = CertLeafProof(inst, h, F, cert)
            stats['closed'] = True
        stats['t'] = time.time() - t0
        return stats
    if res.status != 0:
        stats['t'] = time.time() - t0
        return stats
    if not any(1e-7 < v < 1 - 1e-7 for v in res.x):
        stats['reason'] = 'base-integral'
        stats['t'] = time.time() - t0
        return stats
    pool = []
    seen = set()
    cur = res
    for _ in range(max_cuts):
        cands = separate_covers(base, cur.x, h, cap=cut_cap)
        new = None
        for viol, a, b, k, C in cands:
            key = (a, b, k, C)
            if key not in seen:
                new = (viol, a, b, k, C)
                break
        if new is None:
            break
        seen.add(new[1:])
        pool.append(new[1:])
        clp = CutLP(base, pool)
        cur = clp.solve()
        stats['lp_solves'] += 1
        stats['cuts'] = len(pool)
        if cur.status == 2:
            cert = integer_cut_certificate(clp, inst, h)
            stats['cert_lp'] = 1
            if cert is not None:
                proof = CutLeafProof(inst, h, F, cert)
                if proof.audit_rdf():
                    stats['proof'] = proof
                    stats['closed'] = True
                    stats['reason'] = 'cut-closed'
                    stats['t'] = time.time() - t0
                    return stats
            stats['reason'] = 'cut-cert-failed'
            stats['t'] = time.time() - t0
            return stats
        if cur.status != 0:
            stats['reason'] = 'cut-lp-other'
            stats['t'] = time.time() - t0
            return stats
    stats['reason'] = 'cut-budget'
    stats['t'] = time.time() - t0
    return stats


def cut_probe(inst, h, forbid0=None, max_cuts=12, cut_cap=64):
    """Root cut loop, then fallback to PACT with the base LP reused."""
    F = frozenset(forbid0 or ())
    st = cut_loop(inst, h, F, max_cuts=max_cuts, cut_cap=cut_cap)
    if st.get('closed'):
        return dict(verdict=False, proof=st['proof'], schedule=None,
                    machine=None, lp_solves=st['lp_solves'],
                    cert_lp=st['cert_lp'], nodes=st['lp_solves'],
                    cuts=st['cuts'], closed=True, reason=st['reason'],
                    t=st['t'])
    base = st['base']
    base_res = st['base_res']
    if st['status'] == 2 or st['status'] != 0:
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=F, root_lp=base, root_res=base_res)
    elif st.get('reason') == 'base-integral':
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=F, root_lp=base, root_res=base_res)
    else:
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=F, root_lp=base, root_res=base_res)
    return dict(
        verdict=r['verdict'], proof=r.get('proof'),
        schedule=r.get('schedule'), machine=r.get('machine'),
        lp_solves=st['lp_solves'] + r.get('lp_solves', 0),
        cert_lp=st['cert_lp'] + r.get('cert_lp', 0),
        nodes=st['lp_solves'] + r.get('nodes', 0),
        cuts=st['cuts'], closed=False, reason=st['reason'],
        t=st['t'] + r.get('t', 0.0))


def _choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


def run_gcc(inst, known, name, idx, policy='lower-first', max_probes=64,
            max_cuts=12, cut_cap=64, cut_gate='deep'):
    """v9.2 ICF loop with the GCC probe oracle."""
    t0 = time.time()
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

    probes = 0
    search_lp = 0
    search_nodes = 0
    search_cert_lp = 0
    cut_probes = 0
    cut_closed = 0
    cut_total = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        use_cut = (cut_gate == 'always' or
                   (cut_gate == 'deep' and U - L > 1))
        if use_cut:
            r = cut_probe(inst, h, max_cuts=max_cuts, cut_cap=cut_cap)
            cut_probes += 1
            cut_total += r.get('cuts', 0)
            cut_closed += bool(r.get('closed'))
        else:
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        search_lp += r.get('lp_solves', 0)
        search_nodes += r.get('nodes', 0)
        search_cert_lp += r.get('cert_lp', 0)

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              closed=bool(r.get('closed')),
                              cuts=r.get('cuts', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        probes=probes, search_lp=search_lp, search_nodes=search_nodes,
        search_cert_lp=search_cert_lp,
        cut_probes=cut_probes, cut_closed=cut_closed,
        cut_total=cut_total,
        pin_lp=getattr(co, 'pin_lp', 0),
        total_lp=search_lp + search_cert_lp,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final, unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )
