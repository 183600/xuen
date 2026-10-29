"""v10.0 DIP: Decomposition-Invariant Pseudocode for certified scheduling.

The state of every module is the ICF partial certificate

    C = (L, U, s, m, pi),   pi : NO(L-1), Cmax(s)=U, L<=U.

A module is either a leaf (solved by ICF-PACT) or an internal node
with one of two composition rules:

    SERIES(A, B)     every job of A precedes every job of B
    PARALLEL(A, B)   A and B are conflict-free (no precedence edge and
                     disjoint eligible-machine sets)

The composition rules are the *pseudocode* of the certificate.  Each
rule has a local precondition and a postcondition; its proof is a
constructor of ICF certificates.  The root object is an auditable
partial or final certificate.  The decomposition tree is built before
any probe; leaves are solved independently and the root is assembled
bottom-up.

The implementation is deliberately additive: it calls v9.0 ICF-PACT
unchanged for every leaf and never builds a global LP for a decomposed
instance.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v10d', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from po import make_inst
from rdf import check_schedule
from icf import run_icf, cmax, corpora


# ------------------------------------------------------------------ helpers
def _topo(inst):
    n = inst['n']
    indeg = [0] * n
    for j in range(n):
        for i in inst['pred'][j]:
            indeg[j] += 1
    q = [i for i in range(n) if indeg[i] == 0]
    heapq.heapify(q)
    out = []
    while q:
        i = heapq.heappop(q)
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(q, j)
    return out if len(out) == n else None


def _desc_masks(inst, order):
    n = inst['n']
    desc = [0] * n
    for i in reversed(order):
        m = 0
        for j in inst['succ'][i]:
            m |= (1 << j) | desc[j]
        desc[i] = m
    return desc


def _subinst(inst, jobs, remap_machines=False):
    """Induced subinstance; optionally remap used machines to 0..k-1."""
    jobs = list(jobs)
    n = len(jobs)
    mp = {j: c for c, j in enumerate(jobs)}
    pred = [[mp[i] for i in inst['pred'][j] if i in mp] for j in jobs]
    used = sorted({k for j in jobs for k in inst['elig'][j]})
    if remap_machines:
        km = {k: c for c, k in enumerate(used)}
        m = max(1, len(used))
        elig = [[km[k] for k in inst['elig'][j]] for j in jobs]
    else:
        km = {k: k for k in used}
        m = inst['m']
        elig = [list(inst['elig'][j]) for j in jobs]
    p = [inst['p'][j] for j in jobs]
    sub = make_inst(p, m, pred, elig)
    sub['_parent_ids'] = jobs
    sub['_mach_map'] = km
    sub['_mach_inv'] = {v: k for k, v in km.items()}
    sub['_root_m'] = inst['m']
    return sub


def _components(inst):
    """Conflict components: share a machine or a precedence edge."""
    n = inst['n']
    par = list(range(n))

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def u(a, b):
        a, b = f(a), f(b)
        if a != b:
            par[a] = b

    bym = {}
    for i in range(n):
        for k in inst['elig'][i]:
            bym.setdefault(k, []).append(i)
    for js in bym.values():
        for a in js[1:]:
            u(js[0], a)
    for i in range(n):
        for j in inst['succ'][i]:
            u(i, j)
    out = {}
    for i in range(n):
        out.setdefault(f(i), []).append(i)
    return list(out.values())


def _series_cuts(inst):
    """All prefix cuts A < B in one topological order.

    Because every job of A precedes every job of B, A is contiguous in
    every topological order; one order suffices.
    """
    order = _topo(inst)
    if order is None:
        return [], order
    n = inst['n']
    desc = _desc_masks(inst, order)
    cuts = []
    allmask = (1 << n) - 1
    for k in range(1, n):
        A = order[:k]
        Bmask = allmask ^ ((1 << k) - 1) if order == list(range(n)) else None
        # the bitmask above is only valid when the order is the identity;
        # build Bmask explicitly to stay correct for arbitrary orders.
        Bset = set(order[k:])
        Bmask = 0
        for j in Bset:
            Bmask |= 1 << j
        ok = True
        for i in A:
            if (desc[i] & Bmask) != Bmask:
                ok = False
                break
        if ok:
            cuts.append(k)
    return cuts, order


# ------------------------------------------------------------ proof objects
class SingletonLowerProof(Proof):
    """NO(p-1) for a one-job instance: no schedule can be shorter."""

    kind = 'dip-singleton-lb'

    def __init__(self, inst, h):
        super().__init__(inst, h)

    def audit_rdf(self):
        try:
            return bool(self.inst['n'] == 1 and
                        self.h == self.inst['p'][0] - 1)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class SeriesLowerProof(Proof):
    """NO(L_A + L_B - 1) from NO(L_A-1) and NO(L_B-1)."""

    kind = 'dip-series-lb'

    def __init__(self, inst, h, left, right):
        super().__init__(inst, h)
        self.left = left
        self.right = right

    def audit_rdf(self):
        try:
            if self.left is None or self.right is None:
                return False
            if self.h != self.left.L + self.right.L - 1:
                return False
            return bool(self.left.lower_audit() and
                        self.right.lower_audit())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class ParallelLowerProof(Proof):
    """NO(max_c L_c - 1) from the lower-bound proof of the strongest child."""

    kind = 'dip-parallel-lb'

    def __init__(self, inst, h, children):
        super().__init__(inst, h)
        self.children = list(children)

    def audit_rdf(self):
        try:
            if not self.children:
                return False
            L = max(c.L for c in self.children)
            if self.h != L - 1:
                return False
            strong = [c for c in self.children if c.L == L]
            return all(c.lower_audit() for c in self.children) and \
                any(c.lower_audit() for c in strong[:1])
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class Node:
    """A DIP module: partial certificate plus its composition tree."""

    def __init__(self, inst, kind, L, U, sched, mach, proof,
                 children=None, job_ids=None, mach_map=None,
                 leaf_row=None, depth=0):
        self.inst = inst
        self.kind = kind
        self.L = int(L)
        self.U = int(U)
        self.sched = list(sched) if sched is not None else None
        self.mach = list(mach) if mach is not None else None
        self.proof = proof
        self.children = list(children or [])
        self.job_ids = list(job_ids if job_ids is not None
                            else range(inst['n']))
        self.mach_map = dict(mach_map or {})
        self.leaf_row = leaf_row
        self.depth = int(depth)

    def _sched_ok(self):
        if self.sched is None or self.mach is None:
            return False
        if cmax(self.inst, self.sched) != self.U:
            return False
        return bool(check_schedule(self.inst, self.U, self.sched,
                                   self.mach))

    def lower_audit(self):
        try:
            if self.L > self.U:
                return False
            if self.kind == 'leaf':
                p = self.proof
                return bool(p is not None and p.h == self.L - 1 and
                            p.audit_rdf())
            if self.kind == 'series':
                a, b = self.children
                if self.L != a.L + b.L:
                    return False
                if not (a.lower_audit() and b.lower_audit()):
                    return False
                return bool(self.proof is not None and
                            self.proof.h == self.L - 1 and
                            self.proof.audit_rdf())
            if self.kind == 'parallel':
                L = max(c.L for c in self.children)
                if self.L != L:
                    return False
                if not all(c.lower_audit() for c in self.children):
                    return False
                return bool(self.proof is not None and
                            self.proof.h == self.L - 1 and
                            self.proof.audit_rdf())
            return False
        except Exception:
            return False

    def audit_rdf(self):
        try:
            if not self._sched_ok():
                return False
            if not self.lower_audit():
                return False
            if self.kind == 'series':
                a, b = self.children
                if self.U != a.U + b.U:
                    return False
                if self.sched != a.sched + [x + a.U for x in b.sched]:
                    return False
                if self.mach != a.mach + b.mach:
                    return False
                return a.audit_rdf() and b.audit_rdf()
            if self.kind == 'parallel':
                if self.U != max(c.U for c in self.children):
                    return False
                # schedules are unioned in root-machine coordinates.
                n = self.inst['n']
                s = [None] * n
                mm = [None] * n
                seen = set()
                for c in self.children:
                    for pos, j in enumerate(c.job_ids):
                        if j in seen:
                            return False
                        seen.add(j)
                        s[j] = c.sched[pos]
                        mm[j] = c.mach_map.get(c.mach[pos], c.mach[pos])
                if any(x is None for x in s) or len(seen) != n:
                    return False
                if s != self.sched or mm != self.mach:
                    return False
                return all(c.audit_rdf() for c in self.children)
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


# ------------------------------------------------------------------ builder
def _parallel_ok(inst, comps):
    """Check the independence precondition for a parallel partition."""
    if len(comps) < 2:
        return False
    jobsets = [set(c) for c in comps]
    # partition
    if sum(len(s) for s in jobsets) != inst['n']:
        return False
    if set().union(*jobsets) != set(range(inst['n'])):
        return False
    # no precedence across components
    comp_of = {}
    for c, js in enumerate(jobsets):
        for j in js:
            comp_of[j] = c
    for i in range(inst['n']):
        for j in inst['succ'][i]:
            if comp_of[i] != comp_of[j]:
                return False
    # disjoint machine sets
    used = []
    for js in jobsets:
        used.append({k for j in js for k in inst['elig'][j]})
    for a in range(len(used)):
        for b in range(a + 1, len(used)):
            if used[a] & used[b]:
                return False
    return True


def plan_cost(plan):
    inst = plan['inst']
    n = inst['n']
    if plan['kind'] == 'leaf':
        used = len({k for i in range(n) for k in inst['elig'][i]})
        return max(1, n * max(1, used) * max(1, sum(inst['p'])))
    return sum(plan_cost(c) for c in plan['children'])


def build_tree(inst, order_mode='balanced', depth=0, auto=True,
               alpha=0.65):
    """Return a decomposition plan (nested dict) without solving leaves."""
    n = inst['n']
    if n <= 1:
        return dict(kind='leaf', inst=inst, depth=depth)
    comps = _components(inst)
    if len(comps) > 1 and _parallel_ok(inst, comps):
        children = []
        for js in comps:
            sub = _subinst(inst, js, remap_machines=True)
            ch = build_tree(sub, order_mode=order_mode, depth=depth + 1,
                            auto=auto, alpha=alpha)
            ch['parent_ids'] = list(js)
            ch['mach_map'] = sub['_mach_inv']
            children.append(ch)
        cand = dict(kind='parallel', inst=inst, children=children,
                    depth=depth)
        if auto and plan_cost(cand) > alpha * plan_cost(
                dict(kind='leaf', inst=inst, depth=depth)):
            return dict(kind='leaf', inst=inst, depth=depth)
        return cand
    cuts, order = _series_cuts(inst)
    if cuts:
        if order_mode == 'first':
            k = cuts[0]
        elif order_mode == 'last':
            k = cuts[-1]
        else:
            k = min(cuts, key=lambda c: (max(c, n - c), c))
        A = order[:k]
        B = order[k:]
        sa = _subinst(inst, A, remap_machines=False)
        sb = _subinst(inst, B, remap_machines=False)
        ca = build_tree(sa, order_mode=order_mode, depth=depth + 1,
                        auto=auto, alpha=alpha)
        cb = build_tree(sb, order_mode=order_mode, depth=depth + 1,
                        auto=auto, alpha=alpha)
        ca['parent_ids'] = list(A)
        cb['parent_ids'] = list(B)
        cand = dict(kind='series', inst=inst, children=[ca, cb],
                    cut=k, depth=depth)
        if auto and plan_cost(cand) > alpha * plan_cost(
                dict(kind='leaf', inst=inst, depth=depth)):
            return dict(kind='leaf', inst=inst, depth=depth)
        return cand
    return dict(kind='leaf', inst=inst, depth=depth)


# ------------------------------------------------------------------ solver
def solve_plan(plan, policy='lower-first', max_probes=64,
               use_decomposition=True, stats=None):
    if stats is None:
        stats = dict(probes=0, pact_lp=0, cert_lp=0, pin_lp=0,
                     leaves=0, series=0, parallel=0, t=0.0,
                     leaf_rows=[])
    kind = plan['kind']
    inst = plan['inst']
    if not use_decomposition:
        kind = 'leaf'
    if kind == 'leaf' and inst['n'] == 1:
        L = U = inst['p'][0]
        sched = [0]
        mach = [min(inst['elig'][0])]
        proof = SingletonLowerProof(inst, L - 1)
        stats['leaves'] += 1
        return Node(inst, 'leaf', L, U, sched, mach, proof,
                    job_ids=plan.get('parent_ids'),
                    mach_map=plan.get('mach_map'),
                    depth=plan.get('depth', 0))
    if kind == 'leaf':
        t0 = time.time()
        r = run_icf(inst, None, 'leaf', -1, policy=policy,
                    max_probes=max_probes, collect_proof=True)
        stats['t'] += time.time() - t0
        stats['leaves'] += 1
        stats['probes'] += r.get('queries', 0)
        stats['pact_lp'] += r.get('pact_lp', 0)
        stats['cert_lp'] += r.get('pact_cert_lp', 0)
        stats['pin_lp'] += r.get('pin_lp', 0)
        stats['leaf_rows'].append(r)
        if r.get('error') or r.get('lb') is None:
            return None
        L, U = r['lb'], r['opt']
        if not r.get('partial_final'):
            return None
        return Node(inst, 'leaf', L, U, r['schedule'], r['machine'],
                    r['lb_proof'], job_ids=plan.get('parent_ids'),
                    mach_map=plan.get('mach_map'), leaf_row=r,
                    depth=plan.get('depth', 0))
    if kind == 'series':
        stats['series'] += 1
        a = solve_plan(plan['children'][0], policy, max_probes,
                       use_decomposition, stats)
        b = solve_plan(plan['children'][1], policy, max_probes,
                       use_decomposition, stats)
        if a is None or b is None:
            return None
        L = a.L + b.L
        U = a.U + b.U
        sched = a.sched + [x + a.U for x in b.sched]
        mach = a.mach + b.mach
        proof = SeriesLowerProof(inst, L - 1, a, b)
        return Node(inst, 'series', L, U, sched, mach, proof,
                    children=[a, b], job_ids=plan.get('parent_ids'),
                    mach_map=plan.get('mach_map'),
                    depth=plan.get('depth', 0))
    if kind == 'parallel':
        stats['parallel'] += 1
        children = []
        for ch in plan['children']:
            node = solve_plan(ch, policy, max_probes,
                              use_decomposition, stats)
            if node is None:
                return None
            children.append(node)
        L = max(c.L for c in children)
        U = max(c.U for c in children)
        n = inst['n']
        sched = [None] * n
        mach = [None] * n
        for c in children:
            for pos, j in enumerate(c.job_ids):
                sched[j] = c.sched[pos]
                mach[j] = c.mach_map.get(c.mach[pos], c.mach[pos])
        proof = ParallelLowerProof(inst, L - 1, children)
        return Node(inst, 'parallel', L, U, sched, mach, proof,
                    children=children, job_ids=plan.get('parent_ids'),
                    mach_map=plan.get('mach_map'),
                    depth=plan.get('depth', 0))
    return None


def run_dip(inst, known, name, idx, policy='lower-first',
            max_probes=64, use_decomposition=True, order_mode='balanced',
            auto=True, alpha=0.65):
    t0 = time.time()
    plan = build_tree(inst, order_mode=order_mode, auto=auto,
                      alpha=alpha) \
        if use_decomposition else dict(kind='leaf', inst=inst, depth=0)
    build_t = time.time() - t0
    stats = dict(probes=0, pact_lp=0, cert_lp=0, pin_lp=0,
                 leaves=0, series=0, parallel=0, t=0.0, leaf_rows=[])
    root = solve_plan(plan, policy=policy, max_probes=max_probes,
                      use_decomposition=use_decomposition, stats=stats)
    final_ok = bool(root is not None and root.audit_rdf())
    certified = bool(root is not None and root.L == root.U and final_ok)
    return dict(name=name, idx=idx, known=known, policy=policy,
                opt=(root.U if root is not None else None),
                lb=(root.L if root is not None else None),
                certified=certified, audit=final_ok, proof=final_ok,
                ok=bool(certified and root.U == known),
                probes=stats['probes'], pact_lp=stats['pact_lp'],
                cert_lp=stats['cert_lp'], pin_lp=stats['pin_lp'],
                total_lp=stats['pact_lp'] + stats['cert_lp'] +
                stats['pin_lp'],
                leaves=stats['leaves'], series=stats['series'],
                parallel=stats['parallel'],
                build_t=round(build_t, 5),
                t=round(time.time() - t0, 4),
                tree_kind=plan['kind'],
                root=(root if root is not None else None))
