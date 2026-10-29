"""v8.10 CDCL-ALC prototype: conflict-box learning on top of PRISM.

The new object is a *learned NO box*.  When a box B is LP-infeasible,
CDCL-ALC greedily widens B to a coordinate-wise maximal box B' that is
still LP-infeasible, records a Farkas certificate for B', and uses B' as
a subsumption lemma.  Any later box C with C subset B' is closed by a
single lemma lookup, without an LP solve.  The proof tree keeps the
split nodes and references the lemmas, so audit replays both the splits
and every Farkas leaf.
"""
import sys
import time

sys.path[:0] = ['exp/v8k', 'exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import SAGE, ga_schedule, SubsumptionProof, _elig_aware
from prism import (root_box, tighten, box_forbid, _score,
                   DEFAULT_POLICY, interval_branch_decide)
from sdecc import SDLP
from cert import verify, integer_certificate
from rdf import check_schedule
from po import heads_tails


class BoxProof(Proof):
    """A NO(h) proof: interval splits + Farkas lemmas + subsumption cuts."""

    kind = 'cdcl'

    def __init__(self, inst, h, tree, lemmas, stats=None):
        super().__init__(inst, h)
        self.tree = tree
        self.lemmas = lemmas
        self.stats = stats or {}

    def _lemma_ok(self, idx):
        if idx < 0 or idx >= len(self.lemmas):
            return False
        lem = self.lemmas[idx]
        F = box_forbid(self.inst, self.h, lem['lo'], lem['hi'])
        return bool(verify(self.inst, self.h, lem['cert'], forbid=F))

    def _sub(self, lo, hi, idx):
        lem = self.lemmas[idx]
        for i in range(self.inst['n']):
            if lo[i] < lem['lo'][i] or hi[i] > lem['hi'][i]:
                return False
        return self._lemma_ok(idx)

    def _check(self, node, lo, hi):
        st = tighten(self.inst, self.h, lo, hi)
        if st is None:
            return node[0] == 'empty'
        lo, hi = st
        tag = node[0]
        if tag == 'empty':
            return False
        if tag == 'leaf':
            F = box_forbid(self.inst, self.h, lo, hi)
            return bool(verify(self.inst, self.h, node[1], forbid=F))
        if tag == 'sub':
            return self._sub(lo, hi, node[1])
        if tag != 'node':
            return False
        _, i, mid, left, right = node
        if not (0 <= i < self.inst['n'] and lo[i] <= mid < hi[i]):
            return False
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo, rhi = list(lo), list(hi)
        rlo[i] = mid + 1
        return (self._check(left, llo, lhi)
                and self._check(right, rlo, rhi))

    def audit_rdf(self):
        try:
            lo, hi = root_box(self.inst, self.h)
            return self._check(self.tree, lo, hi)
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def size(self):
        nodes = [0]
        leaves = [0]
        subs = [0]

        def rec(t):
            nodes[0] += 1
            if t[0] == 'leaf':
                leaves[0] += 1
            elif t[0] == 'sub':
                subs[0] += 1
            elif t[0] == 'node':
                rec(t[3])
                rec(t[4])
        rec(self.tree)
        return dict(nodes=nodes[0], leaves=leaves[0], subs=subs[0],
                    lemmas=len(self.lemmas))


# ------------------------------------------------------------------ widening
def _box_cert(inst, h, lo, hi, elig):
    F = box_forbid(inst, h, lo, hi)
    cert = integer_certificate(inst, h, use_dom=True,
                               elig_aware=elig, forbid=F)
    if cert is not None and verify(inst, h, cert, forbid=F):
        return cert
    return None


def _widen_box(inst, h, lo, hi, est, lst, elig, budget):
    """Greedy coordinate-wise widening of an LP-infeasible interval box.

    The set of infeasible boxes is downward closed, so on one coordinate
    the feasible/infeasible boundary is monotone and can be found by
    binary search.  Every accepted expansion is certified by the same
    integer_certificate path used by the leaf checker.
    """
    n = inst['n']
    lo = list(lo)
    hi = list(hi)
    cert = _box_cert(inst, h, lo, hi, elig)
    if cert is None:
        return None
    used = 1
    if budget <= 0:
        return lo, hi, cert, used

    def test(a, b):
        nonlocal used
        if used >= budget:
            return None
        used += 1
        return _box_cert(inst, h, a, b, elig)

    for _ in range(2):
        changed = False
        for i in range(n):
            # expand the left side: find the smallest lo' with infeasible
            if lo[i] > est[i]:
                c = test([est[i]] + lo[1:] if i == 0 else lo[:i] + [est[i]] + lo[i+1:], hi)
                if c is not None:
                    lo[i] = est[i]
                    cert = c
                    changed = True
                else:
                    a, b = est[i], lo[i]        # a feasible, b infeasible
                    while a + 1 < b:
                        m = (a + b) // 2
                        cand = list(lo)
                        cand[i] = m
                        c = test(cand, hi)
                        if c is not None:
                            b = m
                            cert = c
                        else:
                            a = m
                    if b < lo[i]:
                        lo[i] = b
                        changed = True
            # expand the right side
            if hi[i] < lst[i]:
                cand = list(hi)
                cand[i] = lst[i]
                c = test(lo, cand)
                if c is not None:
                    hi[i] = lst[i]
                    cert = c
                    changed = True
                else:
                    a, b = hi[i], lst[i]        # a infeasible, b feasible
                    while a + 1 < b:
                        m = (a + b) // 2
                        cand = list(hi)
                        cand[i] = m
                        c = test(lo, cand)
                        if c is not None:
                            a = m
                            cert = c
                        else:
                            b = m
                    if a > hi[i]:
                        hi[i] = a
                        changed = True
        if not changed or used >= budget:
            break
    return lo, hi, cert, used


# ------------------------------------------------------------------- decision
def cdcl_decide(inst, h, nodecap=96, depthcap=24, policy=None, seed=0,
                learn=True, widen=True, widen_budget=64, widen_rounds=1,
                lemma_cap=256):
    """Proof-carrying DPLL(T) with conflict-box learning.

    Returns dict(verdict, proof, schedule, machine, nodes, leaves, depth,
    lp_solves, cert_lp, learn_hits, lemmas, widen_lp, t).
    verdict False = NO with a BoxProof, True = YES, None = budget hit.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    pol = dict(DEFAULT_POLICY)
    if policy:
        pol.update(policy)
    use_closure = bool(pol.get('closure', True))
    elig = _elig_aware(inst)
    rlo, rhi = root_box(inst, h)
    root = tighten(inst, h, rlo, rhi, use_closure)
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0,
                 cert_lp=0, learn_hits=0, lemmas=0, widen_lp=0,
                 branch_jobs=[], closure_empty=0, unknown=False,
                 side_unknown=0)
    lemmas = []

    if root is None:
        tree = ('empty',)
        proof = BoxProof(inst, h, tree, lemmas, stats)
        stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=False, proof=proof, schedule=None,
                    machine=None, **stats)
    rlo, rhi = root
    est0, q0 = heads_tails(inst, 0, [0] * n)
    est = list(rlo)
    lst = [h - q0[i] - p[i] for i in range(n)]
    qeff = [h - rhi[i] - p[i] for i in range(n)]
    lp = SDLP(inst, h, est=rlo, q=qeff, use_dom=True,
              elig_aware=elig)
    base = [(0, 1)] * lp.N

    def solve(bounds):
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        if stats['nodes'] > nodecap:
            stats['unknown'] = True
            return None
        return lp.solve(bounds)

    def allowed_times(i, bounds, lo, hi):
        out = set()
        for c, key in enumerate(lp.cols):
            if key[0] == i and bounds[c] != (0, 0):
                t = key[-1]
                if lo[i] <= t <= hi[i]:
                    out.add(t)
        return sorted(out)

    def job_mass(z, i, times, bounds):
        mass = 0.0
        dist = []
        for tt in times:
            v = 0.0
            for c, key in enumerate(lp.cols):
                if key[0] == i and key[-1] == tt and bounds[c] != (0, 0):
                    v += z[c]
            dist.append((tt, v))
            mass += v
        return mass, dist

    def choose(z, bounds, lo, hi):
        cand = []
        for i in range(n):
            times = allowed_times(i, bounds, lo, hi)
            if len(times) <= 1:
                continue
            mass, dist = job_mass(z, i, times, bounds)
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            score = _score(pol['heur'], mass, frac, q0[i],
                           p[i], hi[i] - lo[i], len(times),
                           len(inst['succ'][i]), len(inst['pred'][i]),
                           len(inst['elig'][i]), i, pol.get('weights'))
            cand.append((score, i, dist, times))
        if not cand:
            return None, None, None
        cand.sort(reverse=True)
        _, i, dist, times = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = times[0]
        for tt, v in dist:
            acc += v
            if acc >= pol.get('split', 0.5) * total:
                mid = tt
                break
        left = [tt for tt in times if tt <= mid]
        right = [tt for tt in times if tt > mid]
        if not left or not right:
            mid = times[len(times) // 2 - 1]
            left = [tt for tt in times if tt <= mid]
            right = [tt for tt in times if tt > mid]
        if not left or not right:
            return None, None, None
        return i, mid, times

    def find_lemma(lo, hi):
        for idx, lem in enumerate(lemmas):
            ok = True
            for j in range(n):
                if lo[j] < lem['lo'][j] or hi[j] > lem['hi'][j]:
                    ok = False
                    break
            if ok:
                return idx
        return None

    def leaf_cert(lo, hi):
        stats['cert_lp'] += 1
        cert = _box_cert(inst, h, lo, hi, elig)
        if cert is not None:
            return ('leaf', cert)
        return None

    def integral_schedule(z, bounds):
        starts = [None] * n
        machs = [None] * n
        for c, key in enumerate(lp.cols):
            if bounds[c] == (0, 0):
                continue
            if z[c] > 1 - 1e-7:
                i, t = key[0], key[-1]
                if starts[i] is not None:
                    return None
                starts[i] = t
                if elig:
                    machs[i] = key[1]
        if any(x is None for x in starts):
            return None
        if not elig:
            busy = [[] for _ in range(m)]
            for i in sorted(range(n), key=lambda i: (starts[i], i)):
                for k in inst['elig'][i]:
                    if all(starts[i] + p[i] <= a or starts[i] >= b
                           for a, b in busy[k]):
                        machs[i] = k
                        busy[k].append((starts[i], starts[i] + p[i]))
                        break
                if machs[i] is None:
                    return None
        cmax = max(starts[i] + p[i] for i in range(n))
        if check_schedule(inst, cmax, starts, machs):
            return starts, machs
        return None

    def dfs(lo, hi, depth):
        st = tighten(inst, h, lo, hi, use_closure)
        if st is None:
            stats['closure_empty'] += 1
            return ('empty',)
        lo, hi = st
        if depth > depthcap:
            stats['unknown'] = True
            return None
        if learn:
            idx = find_lemma(lo, hi)
            if idx is not None:
                stats['learn_hits'] += 1
                return ('sub', idx)
        b = list(base)
        for c, key in enumerate(lp.cols):
            i, t = key[0], key[-1]
            if t < lo[i] or t > hi[i]:
                b[c] = (0, 0)
        res = solve(b)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            got = leaf_cert(lo, hi)
            if got is None:
                stats['unknown'] = True
                return None
            if learn and len(lemmas) < lemma_cap:
                wlo, whi, wcert, used = lo, hi, got[1], 0
                if widen:
                    wr = _widen_box(inst, h, lo, hi, est, lst, elig,
                                    max(0, min(widen_budget,
                                               widen_budget - stats['widen_lp'])))
                    stats['widen_lp'] += wr[3] if wr is not None else 0
                    if wr is not None and wr[2] is not None:
                        wlo, whi, wcert = wr[0], wr[1], wr[2]
                lemmas.append(dict(lo=list(wlo), hi=list(whi), cert=wcert))
                stats['lemmas'] = len(lemmas)
                return ('sub', len(lemmas) - 1)
            return got
        if res.status != 0:
            stats['unknown'] = True
            return None
        z = res.x
        frac = False
        for c, key in enumerate(lp.cols):
            if b[c] != (0, 0) and 1e-7 < z[c] < 1 - 1e-7:
                frac = True
                break
        if not frac:
            got = integral_schedule(z, b)
            if got is None:
                stats['unknown'] = True
                return None
            return ('yes', got[0], got[1])
        i, mid, times = choose(z, b, lo, hi)
        if i is None:
            stats['unknown'] = True
            return None
        stats['depth'] = max(stats['depth'], depth)
        stats['branch_jobs'].append((i, mid))
        llo, lhi = list(lo), list(hi)
        lhi[i] = mid
        rlo2, rhi2 = list(lo), list(hi)
        rlo2[i] = mid + 1
        sides = [('L', llo, lhi, left_mass(z, i, mid, times, b)),
                 ('R', rlo2, rhi2, right_mass(z, i, mid, times, b))]
        order = pol.get('side', 'left')
        if order == 'right':
            sides = [sides[1], sides[0]]
        elif order == 'mass':
            sides.sort(key=lambda x: -x[3])
        children = {}
        unknown = False
        for tag, slo, shi, _ in sides:
            r = dfs(slo, shi, depth + 1)
            if r is None:
                unknown = True
                continue
            if r[0] == 'yes':
                return r
            children[tag] = r
        if unknown:
            stats['side_unknown'] += 1
            return None
        return ('node', i, mid, children['L'], children['R'])

    def left_mass(z, i, mid, times, bounds):
        return job_mass(z, i, [t for t in times if t <= mid], bounds)[0]

    def right_mass(z, i, mid, times, bounds):
        return job_mass(z, i, [t for t in times if t > mid], bounds)[0]

    tree = dfs(rlo, rhi, 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=tree[1],
                    machine=tree[2], **stats)
    proof = BoxProof(inst, h, tree, lemmas, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


class CDCL(SAGE):
    def __init__(self, inst, cdcl_nodecap=96, cdcl_depthcap=24,
                 cdcl_learn=True, cdcl_widen=True, cdcl_widen_budget=64,
                 cdcl_lemma_cap=256, **kw):
        super().__init__(inst, **kw)
        self.cdcl_nodecap = cdcl_nodecap
        self.cdcl_depthcap = cdcl_depthcap
        self.cdcl_learn = cdcl_learn
        self.cdcl_widen = cdcl_widen
        self.cdcl_widen_budget = cdcl_widen_budget
        self.cdcl_lemma_cap = cdcl_lemma_cap
        self.cdcl_stats = []

    def _probe(self, h):
        r = cdcl_decide(self.inst, h, nodecap=self.cdcl_nodecap,
                        depthcap=self.cdcl_depthcap,
                        learn=self.cdcl_learn, widen=self.cdcl_widen,
                        widen_budget=self.cdcl_widen_budget,
                        lemma_cap=self.cdcl_lemma_cap)
        self.cdcl_stats.append(r)
        self.bb_lp += r['lp_solves']
        self.cert_lp_total += r.get('cert_lp', 0)
        if r['verdict'] is False:
            self.stats['bb_no'] += 1
            self._record_proof(r['proof'])
            return False, r['proof']
        if r['verdict'] is True and self.bb_yes:
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            if check_schedule(self.inst, h, s, m):
                self.stats['bb_yes'] += 1
                return True, (s, m, cmax)
        if r['verdict'] is True:
            self.stats['bb_yes_ignored'] = self.stats.get('bb_yes_ignored', 0) + 1
        else:
            self.stats['bb_unknown'] += 1
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens,
                                  budget=self.ga_budget)
            self.ga_stats.append(st)
            if got is not None:
                s, m = got
                cmax = max(s[i] + self.inst['p'][i]
                           for i in range(self.inst['n']))
                self.stats['ga_yes'] += 1
                return True, (s, m, cmax)
            self.stats['ga_no'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        return v, rdf
