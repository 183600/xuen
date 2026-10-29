"""v9.0 FTC-ALC prototype: one master LP, interval boxes, fault-tolerant leaves.

This module keeps PRISM/SAGE's outer bracket and proof store.  The new
decision layer:
  * builds one master SDLP per instance at T = initial UB;
  * every probe/branch/leaf is a bound restriction of that master;
  * a leaf certificate is first extracted from the master dual and replayed
    against the box; the direct per-h generator is the replica;
  * a failed leaf does not kill the probe: it becomes a hole, and holes are
    repaired by an independent certificate mode or by a fresh domain split.
"""
import sys
import time
import random

sys.path[:0] = ['exp/v9f', 'exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

import numpy as np

from apex import Proof
from sage import (SAGE, ga_schedule, SubsumptionProof, _elig_aware)
from prism import (root_box, tighten, box_forbid, _score, DEFAULT_POLICY,
                   IntervalBranchProof)
from sdecc import SDLP
from cert import verify, integer_certificate
from lbp import farkas_bounds
from rdf import check_schedule
from po import heads_tails


class MasterBox:
    """One T=UB master matrix, restricted by (h, box) bounds."""

    def __init__(self, inst, T):
        n = inst['n']
        est, q = heads_tails(inst, 0, [0] * n)
        self.inst = inst
        self.T = T
        self.est = est
        self.q = q
        self.elig = _elig_aware(inst)
        self.lp = SDLP(inst, T, est=est, q=q, use_dom=True,
                       elig_aware=self.elig)
        self.cols = self.lp.cols
        self.N = self.lp.N
        self.solves = 0
        self.builds = 1

    def bounds(self, h, lo, hi):
        b = [(0, 1)] * self.N
        p, q = self.inst['p'], self.q
        for c, key in enumerate(self.cols):
            i, t = key[0], key[-1]
            if t < lo[i] or t > hi[i] or t > h - q[i] - p[i]:
                b[c] = (0, 0)
        return b

    def solve(self, h, lo, hi, limit=None):
        b = self.bounds(h, lo, hi)
        self.solves += 1
        return self.lp.solve(b), b

    def cert(self, h, lo, hi, b=None):
        if b is None:
            b = self.bounds(h, lo, hi)
        return farkas_bounds(self.lp, h, b)


def interval_branch_master(inst, master, h, nodecap=96, depthcap=24,
                           policy=None, seed=0, fault=None):
    """Interval-box LP branch on a shared master matrix.

    fault: optional callable(event, ctx) -> bool.  If it returns True the
    event is treated as a fail-stop generator fault (UNKNOWN at that
    point).  Events: 'lp', 'cert_master', 'cert_direct'.
    """
    t0 = time.time()
    n, m, p = inst['n'], inst['m'], inst['p']
    pol = dict(DEFAULT_POLICY)
    if policy:
        pol.update(policy)
    use_closure = bool(pol.get('closure', True))
    elig = master.elig
    est0, q0 = master.est, master.q
    rlo, rhi = root_box(inst, h)
    root = tighten(inst, h, rlo, rhi, use_closure)
    stats = dict(nodes=0, leaves=0, depth=0, lp_solves=0, cert_lp=0,
                 branch_jobs=[], closure_empty=0, unknown=False,
                 holes=0, hole_repairs=0, master_cert=0, direct_cert=0,
                 fault_lp=0, fault_cert=0, side_unknown=0)
    if root is None:
        tree = ('empty',)
        proof = IntervalBranchProof(inst, h, tree, stats)
        stats['t'] = round(time.time() - t0, 5)
        return dict(verdict=False, proof=proof, schedule=None,
                    machine=None, **stats)
    rlo, rhi = root

    def blame(ev, ctx=None):
        if fault is None:
            return False
        try:
            return bool(fault(ev, ctx))
        except Exception:
            return False

    def solve(lo, hi):
        stats['nodes'] += 1
        stats['lp_solves'] += 1
        if stats['nodes'] > nodecap:
            stats['unknown'] = True
            return None, None
        if blame('lp', (lo, hi)):
            stats['fault_lp'] += 1
            return None, None
        return master.solve(h, lo, hi)

    def allowed_times(i, b, lo, hi):
        out = set()
        for c, key in enumerate(master.cols):
            if key[0] == i and b[c] != (0, 0):
                t = key[-1]
                if lo[i] <= t <= hi[i]:
                    out.add(t)
        return sorted(out)

    def job_mass(z, i, times, b):
        mass = 0.0
        dist = []
        for tt in times:
            v = 0.0
            for c, key in enumerate(master.cols):
                if key[0] == i and key[-1] == tt and b[c] != (0, 0):
                    v += z[c]
            dist.append((tt, v))
            mass += v
        return mass, dist

    def choose(z, b, lo, hi):
        cand = []
        for i in range(n):
            times = allowed_times(i, b, lo, hi)
            if len(times) <= 1:
                continue
            mass, dist = job_mass(z, i, times, b)
            frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
            if frac <= 1e-7:
                continue
            score = _score(pol['heur'], mass, frac, q0[i], p[i],
                           hi[i] - lo[i], len(times), len(inst['succ'][i]),
                           len(inst['pred'][i]), len(inst['elig'][i]), i,
                           pol.get('weights'))
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

    def leaf_cert(lo, hi, depth):
        F = box_forbid(inst, h, lo, hi)
        b = master.bounds(h, lo, hi)
        # replica 1: master dual
        stats['cert_lp'] += 1
        if not blame('cert_master', (lo, hi, depth)):
            c = master.cert(h, lo, hi, b)
            if c is not None and verify(inst, h, c, forbid=F):
                stats['master_cert'] += 1
                return ('leaf', c)
        else:
            stats['fault_cert'] += 1
        # replica 2: direct fixed-h generator
        if not blame('cert_direct', (lo, hi, depth)):
            c = integer_certificate(inst, h, use_dom=True,
                                    elig_aware=elig, forbid=F)
            if c is not None and verify(inst, h, c, forbid=F):
                stats['direct_cert'] += 1
                return ('leaf', c)
        else:
            stats['fault_cert'] += 1
        stats['holes'] += 1
        return ('hole', F)

    def integral_schedule(z, b):
        starts = [None] * n
        machs = [None] * n
        for c, key in enumerate(master.cols):
            if b[c] == (0, 0):
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
        res, b = solve(lo, hi)
        if res is None:
            return None
        if res.status == 2:
            stats['leaves'] += 1
            node = leaf_cert(lo, hi, depth)
            if node[0] != 'hole':
                return node
            if node[0] == 'hole':
                # fault-tolerant local repair: try a fresh split on the
                # most fractional-looking job of the infeasible box, which
                # gives two strict sub-boxes; a complete NO proof can still
                # be assembled if both children close.
                i, mid, times = choose_fractional_box(lo, hi)
                if i is not None and depth < depthcap:
                    stats['hole_repairs'] += 1
                    llo, lhi = list(lo), list(hi)
                    lhi[i] = mid
                    rlo2, rhi2 = list(lo), list(hi)
                    rlo2[i] = mid + 1
                    left = dfs(llo, lhi, depth + 1)
                    right = dfs(rlo2, rhi2, depth + 1)
                    if left is not None and right is not None \
                            and left[0] != 'yes' and right[0] != 'yes':
                        return ('node', i, mid, left, right)
            stats['unknown'] = True
            return None
        if res.status != 0:
            stats['unknown'] = True
            return None
        z = res.x
        frac = False
        for c, key in enumerate(master.cols):
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
        sides = [('L', llo, lhi), ('R', rlo2, rhi2)]
        order = pol.get('side', 'left')
        if order == 'right':
            sides = [sides[1], sides[0]]
        children = {}
        unknown = False
        for tag, slo, shi in sides:
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

    def choose_fractional_box(lo, hi):
        best = None
        for i in range(n):
            width = hi[i] - lo[i]
            if width <= 0:
                continue
            key = (width, q0[i], -i)
            if best is None or key > best[0]:
                best = (key, i)
        if best is None:
            return None, None, None
        i = best[1]
        mid = (lo[i] + hi[i]) // 2
        return i, mid, None

    tree = dfs(rlo, rhi, 0)
    stats['t'] = round(time.time() - t0, 5)
    if tree is None:
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    if tree[0] == 'yes':
        return dict(verdict=True, proof=None, schedule=tree[1],
                    machine=tree[2], **stats)
    proof = IntervalBranchProof(inst, h, tree, stats)
    if not proof.audit_rdf():
        stats['unknown'] = True
        return dict(verdict=None, proof=None, schedule=None,
                    machine=None, **stats)
    return dict(verdict=False, proof=proof, schedule=None, machine=None,
                **stats)


class FTC(SAGE):
    def __init__(self, inst, branch_policy=None, fault=None, **kw):
        super().__init__(inst, **kw)
        self.branch_policy = branch_policy or dict(DEFAULT_POLICY)
        self.fault = fault
        self.master = None
        self.master_solves = 0

    def initial_bounds(self):
        r = super().initial_bounds()
        lb, ub, s, m = r
        if ub is not None:
            self.master = MasterBox(self.inst, ub)
        return r

    def _probe(self, h):
        if self.use_bb and self.master is not None:
            r = interval_branch_master(self.inst, self.master, h,
                                       nodecap=self.bb_nodecap,
                                       depthcap=self.bb_depthcap,
                                       policy=self.branch_policy,
                                       fault=self.fault)
            self.master_solves += r.get('lp_solves', 0)
            self.bb_lp += r.get('lp_solves', 0)
            self.cert_lp_total += r.get('cert_lp', 0)
            self.branch_last = r
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
                self.stats['bb_yes_ignored'] = \
                    self.stats.get('bb_yes_ignored', 0) + 1
            else:
                self.stats['bb_unknown'] += 1
        if self.use_ga:
            got, st = ga_schedule(self.inst, h, pop=self.ga_pop,
                                  gens=self.ga_gens, budget=self.ga_budget)
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


def run(cls, inst, known, name, idx, **kw):
    t0 = time.time()
    co = cls(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None), 'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof']
                   and r['cert_h'] == known - 1)
    return r
