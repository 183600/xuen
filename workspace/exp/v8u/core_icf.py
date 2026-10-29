"""v10.0 Core-ICF: P-time classification + fractional-core restricted search.

The ICF state is unchanged:

    C = (L, U, s, m, pi),  pi : NO(L-1),  Cmax(s)=U,  L<=U.

The new object is a *fractional core* extracted from the root LP at the
probe horizon h:

    K(z) = { i : some x_{i,t,k} is fractional in z }.

The tiered decision procedure is

    TIER 0  root LP infeasible   -> NO in P, no branching
    TIER 1  root LP integral     -> YES/NO in P
    TIER 2  root LP fractional   -> PACT restricted to branch jobs K
    TIER 3  TIER 2 returns UNKNOWN -> full PACT fallback

A NO proof returned by TIER 2 is a valid NO proof for the full instance:
every split is on a job in K, the two children still partition the full
start-time domain of that job, and every leaf is an LP-infeasible box
(plus a Farkas/empty certificate).  The restriction only removes
branches; it never turns a feasible box into an infeasible one.

The final *computation certificate* is a CoreCertificate: the usual ICF
optimality certificate plus a sparse feasible root-LP solution z at
U-1, the fractional support K(z), and the check that every branch job
of the NO proof lies in K(z).  This is a P-time checkable witness of the
search complexity parameter k = |K(z)|.

The implementation keeps the v9.0 outer loop, initialization, audit and
certificate classes.  Only the node oracle is replaced by decide_core.
"""
import sys
import time
import numpy as np

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sdecc import SDLP
from po import heads_tails
from pact import PACT, pact_decide
from rdf import check_schedule
from icf import (PartialCertificate, ICFCertificate, cmax, _choose_h,
                 corpora)


# --------------------------------------------------------------- root LP
def _elig_aware(inst):
    n, m = inst['n'], inst['m']
    return any(len(set(inst['elig'][i])) < m for i in range(n))


def solve_root(inst, h, forbid=frozenset()):
    """Solve the root SDLP at h and return (status, lp, res, K)."""
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
              forbid=forbid)
    res = lp.solve()
    if res.status == 2:
        return 'infeasible', lp, res, frozenset()
    if res.status != 0:
        return 'unknown', lp, res, frozenset()
    K = set()
    for c, key in enumerate(lp.cols):
        if 1e-7 < res.x[c] < 1 - 1e-7:
            K.add(key[0])
    return ('integral' if not K else 'fractional'), lp, res, frozenset(K)


def sparse_solution(lp, z, tol=1e-9):
    """Nonzero (column key, value) pairs of an LP solution."""
    out = []
    for c, key in enumerate(lp.cols):
        v = float(z[c])
        if abs(v) > tol:
            out.append((key, v))
    return out


def solution_from_sparse(lp, cols):
    z = np.zeros(lp.N)
    index = {key: c for c, key in enumerate(lp.cols)}
    for key, v in cols:
        if key not in index:
            return None
        z[index[key]] = v
    return z


# --------------------------------------------------------------- oracle
def decide_core(inst, h, forbid=frozenset(), nodecap=None,
                depthcap=None, core_override=None):
    """Tiered decision at h.  Returns (result, root_info, fallback).

    root_info = dict(status, K, cols, lp_cols, h, lp_solves=1)
    The returned result is the pact_decide result whose proof/schedule is
    the one to use.  If TIER 2 is insufficient, TIER 3 is run and its
    LP/nodes/cert counters include the wasted TIER 2 work.
    """
    status, lp, res, K = solve_root(inst, h, forbid)
    root_info = dict(status=status, K=sorted(K), h=h,
                     cols=(sparse_solution(lp, res.x)
                           if res.status == 0 else []),
                     lp_cols=[key for key in lp.cols],
                     lp_solves=1)

    if status == 'unknown':
        # No trusted root result: fall through to the full oracle.
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        forbid0=forbid)
        return r, root_info, True

    if status == 'infeasible':
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        root_lp=lp, root_res=res, branch_jobs=set(),
                        forbid0=forbid)
        return r, root_info, False

    if status == 'integral':
        r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                        root_lp=lp, root_res=res, branch_jobs=set(),
                        forbid0=forbid)
        return r, root_info, False

    # fractional root: branch only on the root support K.  core_override
    # is a testing hook for forcing TIER 2 to be insufficient.
    K_used = set(K) if core_override is None else set(core_override)
    root_info['K_used'] = sorted(K_used)
    r = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                    root_lp=lp, root_res=res, branch_jobs=K_used,
                    forbid0=forbid)
    if r['verdict'] is not None:
        return r, root_info, False

    # TIER 3: the core was insufficient.  Pay for the failed core search,
    # then run the complete oracle with the same root LP.
    r2 = pact_decide(inst, h, depthcap=depthcap, nodecap=nodecap,
                     root_lp=lp, root_res=res, branch_jobs=None,
                     forbid0=forbid)
    for key in ('lp_solves', 'nodes', 'cert_lp'):
        r2[key] = r2.get(key, 0) + r.get(key, 0)
    r2['core_lp_wasted'] = r.get('lp_solves', 0)
    r2['core_nodes_wasted'] = r.get('nodes', 0)
    r2['fallback'] = True
    return r2, root_info, True


# --------------------------------------------------------------- proofs
def branch_jobs_of(proof):
    """Set of jobs used as split variables in a BranchProof tree."""
    out = set()
    if proof is None:
        return out

    def walk(node):
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag in ('node', 'split'):
            _, i, mid, F, lo, hi = node
            out.add(int(i))
            walk(lo)
            walk(hi)
        elif tag == 'leaf':
            return
        elif tag == 'empty':
            return

    walk(getattr(proof, 'tree', None))
    return out


class CoreWitness:
    """Sparse feasible root-LP solution at h=U-1.

    The checker rebuilds the SDLP, reconstructs z from ``cols``, checks
    primal feasibility, and computes K(z).  This is a P-time witness of
    the fractional support, independent of how the LP was solved.
    """

    kind = 'core-witness'

    def __init__(self, inst, h, cols, K=None):
        self.inst = inst
        self.h = int(h)
        self.cols = [(tuple(key), float(v)) for key, v in cols]
        self.K = frozenset(K) if K is not None else None

    def audit_rdf(self):
        try:
            n = self.inst['n']
            est, q = heads_tails(self.inst, 0, [0] * n)
            lp = SDLP(self.inst, self.h, est, q, use_dom=True,
                      elig_aware=_elig_aware(self.inst))
            z = solution_from_sparse(lp, self.cols)
            if z is None:
                return False
            if np.any(z < -1e-7) or np.any(z > 1 + 1e-7):
                return False
            A = lp.A.tocsr()
            rhs = np.asarray(A.dot(z)).ravel()
            if np.max(np.abs(rhs[:lp.n_eq] - 1.0)) > 1e-6:
                return False
            if np.any(rhs[lp.n_eq:] > lp.hi[lp.n_eq:] + 1e-6):
                return False
            K = {key[0] for c, key in enumerate(lp.cols)
                 if 1e-7 < z[c] < 1 - 1e-7}
            if self.K is not None and set(self.K) != K:
                return False
            self.K = frozenset(K)
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class CoreCertificate:
    """ICF optimality certificate + a fractional-core complexity witness."""

    kind = 'core-icf-opt'

    def __init__(self, inst, opt, schedule, machine, lb_proof,
                 witness=None, K=None, core_exact=True):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.witness = witness
        self.K = frozenset(K) if K is not None else None
        self.core_exact = bool(core_exact)
        self.icf = ICFCertificate(inst, opt, schedule, machine, lb_proof)

    def audit_rdf(self):
        try:
            if not self.icf.audit_rdf():
                return False
            jobs = branch_jobs_of(self.lb_proof)
            if self.witness is not None:
                if self.witness.h != self.opt - 1:
                    return False
                if not self.witness.audit_rdf():
                    return False
                if not set(self.witness.K) <= set(self.K or ()):
                    return False
                if self.core_exact and not jobs <= set(self.witness.K):
                    return False
            elif jobs:
                return False
            if self.K is not None and not jobs <= set(self.K):
                return False
            self.branch_jobs = frozenset(jobs)
            self.core_witness_k = (
                len(self.witness.K) if self.witness is not None else 0)
            self.core_k = len(self.K) if self.K is not None else (
                self.core_witness_k)
            self.core_exact = bool(self.core_exact and
                                   jobs <= set(self.witness.K)
                                   if self.witness is not None else
                                   not jobs)
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# --------------------------------------------------------------- outer loop
def run_core_icf(inst, known, name, idx, policy='lower-first',
                 max_probes=64, collect_cert=True, core_override=None,
                 initial=None):
    t0 = time.time()
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None
    else:
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
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    root_lp = 0
    fallbacks = 0
    core_status = {}
    core_k_last = None
    partial_ok = partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U
    last_no_root = None

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
        r, root, fb = decide_core(inst, h,
                                  core_override=core_override)
        probes += 1
        first = False
        root_lp += 1
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        fallbacks += int(fb)
        core_status[root['status']] = core_status.get(root['status'], 0) + 1
        if root['status'] == 'fractional':
            core_k_last = len(root['K'])

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            if collect_cert:
                last_no_root = root
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              fallback=fb, core=root['status'],
                              k=len(root['K'])))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              fallback=fb, core=root['status'],
                              k=len(root['K'])))
        else:
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U,
                              fallback=fb, core=root['status'],
                              k=len(root['K'])))
            break
        audit_state()

    final = (ICFCertificate(inst, U, sched, mach, lb_proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())

    # Complexity certificate: recover the root LP at U-1 if the final NO
    # proof uses branching.  This LP is a certificate cost, not a search
    # cost, and is reported separately.
    core_audit = None
    core_k = 0
    core_witness_k = 0
    core_exact_final = None
    core_branch_ok = None
    core_cert_lp = 0
    jobs = set()
    K = frozenset()
    if final is not None and collect_cert:
        jobs = branch_jobs_of(lb_proof)
        witness = None
        K_root = frozenset()
        if jobs:
            if last_no_root is not None and last_no_root['h'] == U - 1:
                root = last_no_root
            else:
                status, lp, res, K0 = solve_root(inst, U - 1)
                core_cert_lp += 1
                if status == 'fractional':
                    root = dict(status=status, K=sorted(K0), h=U - 1,
                                cols=sparse_solution(lp, res.x))
                else:
                    root = dict(status=status, K=[], h=U - 1, cols=[])
            if root is not None and root['status'] == 'fractional':
                witness = CoreWitness(inst, U - 1, root['cols'],
                                      K=root['K'])
                K_root = frozenset(root['K'])
        # If TIER 2 fell back, the full proof may branch outside the
        # root support.  The certificate then degrades to the union;
        # k_search is still bounded, but only K_root is witnessed by a
        # single root LP solution.
        K = frozenset(set(K_root) | set(jobs))
        core_exact = bool(not jobs or
                          (witness is not None and jobs <= K_root))
        cc = CoreCertificate(inst, U, sched, mach, lb_proof,
                             witness=witness, K=K,
                             core_exact=core_exact)
        core_audit = bool(cc.audit_rdf())
        core_k = getattr(cc, 'core_k', 0)
        core_witness_k = getattr(cc, 'core_witness_k', 0)
        core_exact_final = getattr(cc, 'core_exact', None)
        core_branch_ok = bool(jobs <= set(K))
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp, root_lp=root_lp,
        total_lp=pact_lp + root_lp + pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        fallbacks=fallbacks,
        core_status=core_status,
        core_k=core_k, core_k_last=core_k_last,
        core_audit=core_audit, core_branch_ok=core_branch_ok,
        core_exact=core_exact_final, core_witness_k=core_witness_k,
        core_cert_lp=core_cert_lp,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        unknown=(1 if L < U else 0), steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final and
                (core_audit is not False)),
    )
