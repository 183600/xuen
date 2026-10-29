"""v9.1 ODC-PACT: online dependency-compiled frontier decision.

The inner oracle of ICF is replaced by a non-recursive, core-sharing
frontier.  Every leaf is a certified box; a completed frontier is a
FrontierProof at the probe horizon.  Cores learned from Farkas leaves are
reused as subsumption facts across leaves, and split variables are chosen
with a dependency-aware score.  The outer ICF loop is unchanged.
"""
import sys
import time
import heapq
import collections
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _domain
from sdecc import SDLP
from cert import verify, _row_meta, DENS
from rdf import check_schedule
from po import heads_tails
from pact import PACT, pact_decide, _assign_machines
from icf import (CertLeafProof, FrontierProof, PartialCertificate,
                 ICFCertificate, cmax, corpora)
from chip import base_bounds, order_portfolio
from cab import _greedy_rank


def _pair(key):
    return (key[0], key[-1])


def _bounds_for(lp, F):
    b = [(0, 1)] * lp.N
    if F:
        for c, key in enumerate(lp.cols):
            if _pair(key) in F:
                b[c] = (0, 0)
    return b


def _farkas_core(lp, forbid):
    """Integer Farkas certificate for an SDLP, plus the column slack."""
    A = lp.A.tocsr()
    hi = lp.hi
    n_eq, n, N = lp.n_eq, lp.n, lp.N
    r = A.shape[0] - n_eq
    present = np.array([c for c, key in enumerate(lp.cols)
                        if _pair(key) not in forbid], dtype=np.int64)
    if len(present) == 0:
        return None, None
    B = sp.hstack([A[:n_eq].T, A[n_eq:].T]).tocsr()[present]
    c = np.zeros(n_eq + r)
    c[:n_eq] = 1.0
    c[n_eq:] = hi[n_eq:]
    A_eq = np.zeros((1, n_eq + r))
    A_eq[0, n_eq:] = 1.0
    res = linprog(c, A_ub=-B, b_ub=np.zeros(len(present)),
                  A_eq=A_eq, b_eq=[1.0],
                  bounds=[(None, None)] * n_eq + [(0, None)] * r,
                  method='highs')
    if res.status != 0 or res.fun >= 0:
        return None, None
    meta = _row_meta(lp)
    for D in DENS:
        y = np.rint(res.x * D).astype(np.int64)
        s = np.asarray(A.T.dot(y)).ravel()
        bt = int(hi[n:].dot(y[n:])) + int(y[:n].sum())
        if s[present].min() >= 0 and bt < 0:
            yb = y[n:]
            cert = dict(
                kind='packing', scale=D,
                beta=[(m[1], m[2], int(yb[k]))
                      for k, m in enumerate(meta) if m[0] == 'cap' and yb[k]],
                dom=[(m[1], m[2], m[3], int(yb[k]))
                     for k, m in enumerate(meta) if m[0] == 'dom' and yb[k]],
                exp=[(m[1], m[2], int(yb[k]))
                     for k, m in enumerate(meta) if m[0] == 'exp' and yb[k]],
                alpha=[int(v) for v in y[:n]], obj=bt, farkas=res.fun,
                cuts=[])
            return cert, s
    return None, None


def _decode(lp, z, h, F):
    inst = lp.inst
    n, p, m = inst['n'], inst['p'], inst['m']
    starts = [None] * n
    machs = [None] * n
    for c, key in enumerate(lp.cols):
        if z[c] <= 1 - 1e-7:
            continue
        i, t = key[0], key[-1]
        if starts[i] is not None and starts[i] != t:
            return None
        starts[i] = t
        if lp.elig_aware:
            k = key[1]
            if machs[i] is not None and machs[i] != k:
                return None
            machs[i] = k
    if any(x is None for x in starts):
        return None
    if not lp.elig_aware:
        machs = _assign_machines(inst, starts)
    if machs is None or any(x is None for x in machs):
        return None
    c = max(starts[i] + p[i] for i in range(n))
    if c <= h and check_schedule(inst, h, starts, machs):
        return starts, machs, c
    return None


def _job_mass(lp, z):
    n = lp.n
    out = [dict() for _ in range(n)]
    for c, key in enumerate(lp.cols):
        v = float(z[c])
        if v <= 1e-9:
            continue
        d = out[key[0]]
        t = key[-1]
        d[t] = d.get(t, 0.0) + v
    return out


def _choose_split(lp, z, h, F, policy, est, q):
    n, p = lp.n, lp.p
    mass = _job_mass(lp, z)
    cand = []
    for i in range(n):
        times = sorted({key[-1] for key in lp.cols
                        if key[0] == i and _pair(key) not in F})
        if len(times) <= 1:
            continue
        frac = sum(v for t, v in mass[i].items()
                   if 1e-7 < v < 1 - 1e-7 and (i, t) not in F)
        if frac <= 1e-7:
            frac = 0.0
        if frac <= 0.0:
            continue
        crit = est[i] + p[i] + q[i]
        slack = h - crit
        deg = len(lp.inst['pred'][i]) + len(lp.inst['succ'][i])
        if policy == 'dep':
            score = frac * (1.0 + 1.5 * crit / max(1.0, h)
                            + 0.5 * deg / max(1, n)
                            + 1.0 / (1.0 + max(0, slack)))
        elif policy == 'mass':
            score = frac
        elif policy == 'crit':
            score = crit + frac
        else:
            score = frac
        cand.append((score, len(times), i, times, mass[i]))
    if not cand:
        return None
    if policy == 'mass':
        cand.sort(key=lambda x: (-x[0], -q[x[2]],
                                 -len(lp.inst['succ'][x[2]]), x[2]))
    else:
        cand.sort(key=lambda x: (-x[0], x[1], -x[2]))
    _, _, i, times, d = cand[0]
    total = sum(d.get(t, 0.0) for t in times)
    acc = 0.0
    mid = times[0]
    for t in times:
        acc += d.get(t, 0.0)
        if acc >= 0.5 * total:
            mid = t
            break
    lo = [t for t in times if t > mid]
    hi = [t for t in times if t <= mid]
    if not lo or not hi:
        mid = times[max(0, len(times) // 2 - 1)]
        lo = [t for t in times if t > mid]
        hi = [t for t in times if t <= mid]
    if not lo or not hi:
        return None
    return i, mid, times


class _Node:
    __slots__ = ('F', 'parent', 'left', 'right', 'i', 'mid', 'proof',
                 'closed', 'depth', 'key')

    def __init__(self, F, parent=None, depth=0, proof=None):
        self.F = frozenset(F)
        self.parent = parent
        self.left = None
        self.right = None
        self.i = None
        self.mid = None
        self.proof = proof
        self.closed = False
        self.depth = depth
        self.key = 0


def _empty_job(lp, F):
    seen = set()
    for key in lp.cols:
        if _pair(key) not in F:
            seen.add(key[0])
    for i in range(lp.n):
        if i not in seen:
            return i
    return None


def _priority(node, mode):
    if mode == 'dfs':
        return (-node.depth, len(node.F))
    if mode == 'bfs':
        return (node.depth, len(node.F))
    return (len(node.F), -node.depth)


def frontier_decide(inst, h, forbid0=None, policy='dep', sharing=True,
                    order='dfs', nodecap=4000, timelimit=None,
                    lp=None, core_bank=None, debug=False):
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = any(len(set(inst['elig'][i])) < m for i in range(n))
    if lp is None:
        lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    root = _Node(forbid0 or frozenset())
    open_nodes = [root]
    cores = list(core_bank or [])
    closed = []
    stats = dict(nodes=0, leaves=0, lp_solves=0, cert_lp=0,
                 split_nodes=0, core_hits=0, empty_hits=0,
                 max_depth=0, verdict=None, cores=len(cores), unknown=0,
                 bank_hits=0)
    counter = 0

    def close(node, proof):
        node.closed = True
        node.proof = proof
        closed.append(node)

    def pop_node():
        nonlocal counter
        if not open_nodes:
            return None
        if order == 'dfs':
            return open_nodes.pop()
        if order == 'bfs':
            return open_nodes.pop(0)
        best = min(range(len(open_nodes)),
                   key=lambda k: _priority(open_nodes[k], order))
        return open_nodes.pop(best)

    def pact_root():
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        stats['fallback'] = stats.get('fallback', 0) + 1
        stats['fallback_lp'] = stats.get('fallback_lp', 0) + r.get('lp_solves', 0)
        stats['fallback_nodes'] = stats.get('fallback_nodes', 0) + r.get('nodes', 0)
        if r['verdict'] is False:
            stats['verdict'] = False
            return dict(verdict=False, proof=r['proof'], schedule=None,
                        machine=None, cmax=None, stats=stats,
                        t=round(time.time() - t0, 5))
        if r['verdict'] is True:
            s, mm = r['schedule'], r['machine']
            c = cmax(inst, s)
            stats['verdict'] = True
            return dict(verdict=True, proof=None, schedule=s, machine=mm,
                        cmax=c, stats=stats, t=round(time.time() - t0, 5))
        stats['unknown'] = 1
        stats['verdict'] = None
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    cmax=None, stats=stats, t=round(time.time() - t0, 5))

    while open_nodes:
        if timelimit is not None and time.time() - t0 > timelimit:
            stats['unknown'] = 1
            stats['verdict'] = None
            return dict(verdict=None, proof=None, schedule=None,
                        machine=None, cmax=None, stats=stats,
                        t=round(time.time() - t0, 5))
        if len(closed) + len(open_nodes) > nodecap:
            stats['unknown'] = 1
            stats['verdict'] = None
            return dict(verdict=None, proof=None, schedule=None,
                        machine=None, cmax=None, stats=stats,
                        t=round(time.time() - t0, 5))
        node = pop_node()
        F = node.F
        stats['nodes'] += 1
        if debug:
            print('node', stats['nodes'], 'F', len(F), 'depth', node.depth)
        stats['max_depth'] = max(stats['max_depth'], node.depth)
        ej = _empty_job(lp, F)
        if ej is not None:
            close(node, CertLeafProof(inst, h, F,
                                      {'kind': 'empty', 'job': ej}))
            stats['empty_hits'] += 1
            continue
        if sharing:
            hit = None
            for E, proof, hc in cores:
                if hc >= h and E <= F:
                    hit = proof
                    break
            if hit is not None:
                if debug:
                    print('  core hit', len(hit[0] if isinstance(hit, tuple) else ()))
                close(node, hit)
                stats['core_hits'] += 1
                if hc > h:
                    stats['bank_hits'] += 1
                continue
        bounds = _bounds_for(lp, F)
        stats['lp_solves'] += 1
        res = lp.solve(bounds)
        if debug:
            print('  lp status', res.status)
        if res.status == 2:
            cert, slack = _farkas_core(lp, F)
            if debug:
                print('  farkas cert', cert is not None)
            stats['cert_lp'] += 1
            if cert is not None:
                E = frozenset(_pair(lp.cols[c])
                              for c in range(len(lp.cols))
                              if slack[c] < 0)
                proof = CertLeafProof(inst, h, E, cert)
                if not proof.audit_rdf():
                    E = frozenset(F)
                    proof = CertLeafProof(inst, h, E, cert)
                if not proof.audit_rdf():
                    cert = None
            if cert is None:
                r = pact_decide(inst, h, depthcap=None, nodecap=None,
                                forbid0=F)
                if r['verdict'] is False:
                    close(node, r['proof'])
                    continue
                if r['verdict'] is True:
                    s, mm = r['schedule'], r['machine']
                    c = cmax(inst, s)
                    stats['verdict'] = True
                    return dict(verdict=True, proof=None, schedule=s,
                                machine=mm, cmax=c, stats=stats,
                                t=round(time.time() - t0, 5))
                return pact_root()
            close(node, proof)
            if sharing:
                if core_bank is not None:
                    core_bank.append((E, proof, h))
                else:
                    cores.append((E, proof, h))
                stats['cores'] = len(cores)
            continue
        if res.status != 0:
            return pact_root()
        got = _decode(lp, res.x, h, F)
        if debug and got is None:
            print('  fractional, split')
        if got is not None:
            s, mm, c = got
            stats['verdict'] = True
            return dict(verdict=True, proof=None, schedule=s, machine=mm,
                        cmax=c, stats=stats, t=round(time.time() - t0, 5))
        split = _choose_split(lp, res.x, h, F, policy, est, q)
        if split is None:
            if debug:
                print('  no split, fallback pact')
            r = pact_decide(inst, h, depthcap=None, nodecap=None,
                            forbid0=F)
            if r['verdict'] is False:
                close(node, r['proof'])
                if sharing:
                    if core_bank is not None:
                        core_bank.append((frozenset(F), r['proof'], h))
                    else:
                        cores.append((frozenset(F), r['proof'], h))
                    stats['cores'] = len(cores)
                continue
            if r['verdict'] is True:
                s, mm = r['schedule'], r['machine']
                c = cmax(inst, s)
                stats['verdict'] = True
                return dict(verdict=True, proof=None, schedule=s,
                            machine=mm, cmax=c, stats=stats,
                            t=round(time.time() - t0, 5))
            return pact_root()
        i, mid, times = split
        node.i, node.mid = i, mid
        F0 = F | frozenset((i, t) for t in times if t > mid)
        F1 = F | frozenset((i, t) for t in times if t <= mid)
        node.left = _Node(F0, node, node.depth + 1, node.proof)
        node.right = _Node(F1, node, node.depth + 1, node.proof)
        open_nodes.append(node.right)
        open_nodes.append(node.left)
        stats['split_nodes'] += 1

    stats['leaves'] = len(closed)
    stats['verdict'] = False

    def build(node):
        if node.left is None:
            return ('leaf', node.F, h, node.proof)
        return ('split', node.i, node.mid, node.F,
                build(node.left), build(node.right))

    proof = FrontierProof(inst, h, build(root))
    if not proof.audit_rdf():
        return pact_root()
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                cmax=None, stats=stats, t=round(time.time() - t0, 5))


def weak_bounds(inst):
    lb0, ub0, s, mm, est, q = base_bounds(inst)
    if ub0 is None:
        return lb0, None, None, None
    lb, ub, sched, mach = lb0, ub0, s, mm
    for name, rank in order_portfolio(inst, est, q, ub):
        g = _greedy_rank(inst, rank)
        if g is not None and g[2] < ub:
            ub, sched, mach = g[2], g[0], g[1]
    return lb, ub, sched, mach


def _choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'upper-once':
        return U - 1 if first else (L + U) // 2
    if policy == 'lower-once':
        return L if first else (L + U) // 2
    if policy.startswith('ratio'):
        a = float(policy.split(':')[1]) if ':' in policy else 0.4
        h = L + int(a * (U - L))
        return min(U - 1, max(L, h))
    raise ValueError(policy)


def run_odc(inst, known, name, idx, init='pact', policy='lower-first',
            inner='frontier', split_policy='dep', sharing=True,
            order='dfs', max_probes=64, nodecap=4000, timelimit=None):
    t0 = time.time()
    if init == 'pact':
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-initial-ub', t=0.0)
        L, U = int(lb), int(ub)
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                lb_proof = r['proof']
    else:
        L, U, sched, mach = weak_bounds(inst)
        if U is None:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='no-initial-ub', t=0.0)
        L, U = int(L), int(U)
        co = None
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
        else:
            lb_proof = None
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    probes = 0
    core_bank = []
    lp_solves = 0
    cert_lp = 0
    nodes = 0
    leaves = 0
    cores = 0
    core_hits = 0
    bank_hits = 0
    empty_hits = 0
    splits = 0
    fallbacks = 0
    fallback_lp = 0
    partial_ok = 0
    partial_fail = 0
    unknown = 0
    unknown_h = set()
    escape = 0
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

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        if not (L <= h < U) or h in unknown_h:
            cand = None
            for d in range(0, U - L):
                for x in (h - d, h + d):
                    if L <= x < U and x not in unknown_h:
                        cand = x
                        break
                if cand is not None:
                    break
            if cand is None:
                break
            h = cand
            escape += 1
        if inner == 'pact':
            r = pact_decide(inst, h, depthcap=None, nodecap=None)
            st = dict(lp_solves=r.get('lp_solves', 0),
                      nodes=r.get('nodes', 0),
                      cert_lp=r.get('cert_lp', 0), leaves=0,
                      split_nodes=0, core_hits=0, empty_hits=0,
                      cores=0, verdict=r['verdict'])
        else:
            r = frontier_decide(inst, h, policy=split_policy,
                                sharing=sharing, order=order,
                                nodecap=nodecap, timelimit=timelimit,
                                core_bank=core_bank)
            st = r['stats']
            r = dict(verdict=r['verdict'], proof=r.get('proof'),
                     schedule=r.get('schedule'),
                     machine=r.get('machine'), cmax=r.get('cmax'))
        probes += 1
        first = False
        lp_solves += st.get('lp_solves', 0)
        cert_lp += st.get('cert_lp', 0)
        nodes += st.get('nodes', 0)
        leaves += st.get('leaves', 0)
        cores += st.get('cores', 0)
        core_hits += st.get('core_hits', 0)
        bank_hits += st.get('bank_hits', 0)
        empty_hits += st.get('empty_hits', 0)
        splits += st.get('split_nodes', 0)
        fallbacks += st.get('fallback', 0)
        fallback_lp += st.get('fallback_lp', 0)
        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None and hasattr(co, '_record_proof'):
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, L0=L0, U0=U0, L1=L, U1=U,
                              kind=getattr(proof, 'kind', None)))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2, L0=L0, U0=U0,
                              L1=L, U1=U))
        else:
            unknown += 1
            unknown_h.add(h)
            steps.append(dict(h=h, v=None, L0=L0, U0=U0, L1=L, U1=U))
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial_final = bool(PartialCertificate(
        inst, L, U, sched, mach, lb_proof, probe=probes).audit_rdf())
    dt = time.time() - t0
    return dict(name=name, idx=idx, known=known, opt=U, lb=L,
                lb0=lb0, ub0=ub0, certified=bool(L == U and final_ok),
                audit=final_ok, proof=final_ok,
                cert_h=(U - 1 if L == U else None), probes=probes,
                lp_solves=lp_solves, cert_lp=cert_lp, nodes=nodes,
                leaves=leaves, cores=cores, core_hits=core_hits,
                bank_hits=bank_hits, empty_hits=empty_hits,
                split_nodes=splits,
                fallbacks=fallbacks, fallback_lp=fallback_lp,
                escape=escape,
                partial_ok=partial_ok, partial_fail=partial_fail,
                partial_final=partial_final, unknown=unknown,
                steps=steps,
                partial=bool(partial_final and partial_fail == 0),
                t=round(dt, 4),
                ok=bool(L == U and U == known and final_ok and
                        partial_fail == 0 and partial_final))


def hard_corpora():
    import pickle
    files = [
        ('large_a', 'exp/v14/large_a.pkl'),
        ('large_b', 'exp/v14/large_b.pkl'),
        ('large_het', 'exp/v14/large_het.pkl'),
        ('hard3', 'exp/v13/hard3.pkl'),
        ('deep', 'exp/v18/deep.pkl'),
        ('holdout50', 'exp/v20/holdout_cases50.pkl'),
        ('synth2', 'exp/v28/synth2_45.pkl'),
    ]
    out = []
    for tag, path in files:
        d = pickle.load(open(path, 'rb'))
        for k, x in enumerate(d):
            if isinstance(x, dict):
                inst, opt = x['inst'], x['opt']
            else:
                inst, opt = x[0], x[1]
            out.append((tag, k, inst, opt))
    return out
