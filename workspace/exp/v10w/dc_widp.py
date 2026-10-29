"""Divide-and-conquer wrapper for WIDP.

Two independent layers:

1. The instance is split into connected components of the interaction graph
   (precedence edges plus shared eligible machines).  Components have
   disjoint machine sets, so OPT = max_c OPT_c and NO(h) globally iff one
   component is NO(h).  This is the structural divide step.
2. Each component is decided by WIDP, the ideal-lattice DP over topological
   cuts.  This is the algorithmic divide step.

The final object is a partition certificate plus one critical component's
WIDP NO proof and a global schedule.  It is auditable without rerunning the
search.
"""
import sys
import time

sys.path[:0] = ['exp/v10w', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from rdf import check_schedule
from widp import cmax, decide as widp_decide


class DSU:
    def __init__(self, n):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.r[a] < self.r[b]:
            a, b = b, a
        self.p[b] = a
        if self.r[a] == self.r[b]:
            self.r[a] += 1


def decomposition(inst):
    n, m = inst['n'], inst['m']
    d = DSU(n)
    for i in range(n):
        for j in inst['succ'][i]:
            d.union(i, j)
    by_machine = [[] for _ in range(m)]
    for i in range(n):
        for k in inst['elig'][i]:
            by_machine[k].append(i)
    for k in range(m):
        if by_machine[k]:
            a = by_machine[k][0]
            for i in by_machine[k][1:]:
                d.union(a, i)
    groups = {}
    for i in range(n):
        groups.setdefault(d.find(i), []).append(i)
    out = []
    for jobs in groups.values():
        jobs = sorted(jobs)
        machines = sorted({k for i in jobs for k in inst['elig'][i]})
        out.append((jobs, machines))
    out.sort(key=lambda x: x[0][0])
    return out


def subinstance(inst, jobs, machines):
    jidx = {i: j for j, i in enumerate(jobs)}
    midx = {k: j for j, k in enumerate(machines)}
    sub = dict(
        n=len(jobs), m=len(machines),
        p=[inst['p'][i] for i in jobs],
        pred=[[jidx[j] for j in inst['pred'][i]] for i in jobs],
        succ=[[jidx[j] for j in inst['succ'][i]] for i in jobs],
        elig=[[midx[k] for k in inst['elig'][i]] for i in jobs],
    )
    return sub, jidx, midx


def merge_schedule(inst, comps, local):
    starts = [None] * inst['n']
    machs = [None] * inst['n']
    for (jobs, machines), (s, mm) in zip(comps, local):
        for j, i in enumerate(jobs):
            starts[i] = s[j]
            machs[i] = machines[mm[j]]
    return starts, machs


def union_inst(inst, k):
    n, m = inst['n'], inst['m']
    p = list(inst['p']) * k
    pred, succ, elig = [], [], []
    for c in range(k):
        off = c * n
        for i in range(n):
            pred.append([j + off for j in inst['pred'][i]])
            succ.append([j + off for j in inst['succ'][i]])
            elig.append([mm + c * m for mm in inst['elig'][i]])
    return dict(n=n * k, m=m * k, p=p, pred=pred, succ=succ, elig=elig)


class DCWIDPCertificate(Proof):
    """Partition + one component NO proof + global schedule."""

    kind = 'dc-widp'

    def __init__(self, inst, opt, schedule, machine, comps, critical):
        super().__init__(inst, opt)
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule else None
        self.machine = list(machine) if machine else None
        self.comps = list(comps)
        self.critical = critical

    def _partition_ok(self):
        seen = set()
        used_m = set()
        for jobs, machines in self.comps:
            js = set(jobs)
            if seen & js or len(js) != len(jobs):
                return False
            seen |= js
            ms = set(machines)
            if used_m & ms:
                return False
            used_m |= ms
            for i in jobs:
                if any(j not in js for j in self.inst['succ'][i]):
                    return False
                if any(k not in ms for k in self.inst['elig'][i]):
                    return False
        return len(seen) == self.inst['n']

    def audit_rdf(self):
        try:
            if not self._partition_ok():
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.opt:
                return False
            if not check_schedule(self.inst, self.opt, self.schedule,
                                  self.machine):
                return False
            if self.critical is None:
                return False
            c, sub, proof = self.critical
            jobs, machines = self.comps[c]
            sub2, _, _ = subinstance(self.inst, jobs, machines)
            if proof is None or proof.inst is None:
                return False
            for key in ('n', 'm'):
                if proof.inst.get(key) != sub2[key]:
                    return False
            for key in ('p', 'pred', 'succ', 'elig'):
                if list(proof.inst.get(key, [])) != list(sub2[key]):
                    return False
            if proof.h != self.opt - 1:
                return False
            return bool(proof.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def dc_widp_certificate(inst, opt, state_cap=200000):
    """Build OPT schedule and a global NO(opt-1) certificate."""
    t0 = time.time()
    comps = decomposition(inst)
    local = []
    critical = None
    states = 0
    for c, (jobs, machines) in enumerate(comps):
        sub, _, _ = subinstance(inst, jobs, machines)
        ry = widp_decide(sub, opt, state_cap=state_cap)
        states += ry.get('states', 0)
        if ry['verdict'] is not True:
            return dict(ok=False, error='no-yes', comp=c,
                        t=round(time.time() - t0, 5))
        local.append((ry['schedule'], ry['machine']))
        if critical is None:
            rn = widp_decide(sub, opt - 1, state_cap=state_cap)
            states += rn.get('states', 0)
            if rn['verdict'] is False and rn.get('audit'):
                critical = (c, sub, rn['proof'])
            elif rn['verdict'] is not True:
                return dict(ok=False, error='no-no-unknown', comp=c,
                            t=round(time.time() - t0, 5))
    if critical is None:
        return dict(ok=False, error='all-components-yes-at-opt-1',
                    comps=len(comps), states=states,
                    init_t=0.0, t=round(time.time() - t0, 5))
    s, m = merge_schedule(inst, comps, local)
    cert = DCWIDPCertificate(inst, opt, s, m, comps, critical)
    ok = cert.audit_rdf()
    return dict(ok=ok, cert=cert, comps=len(comps), states=states,
                init_t=0.0, t=round(time.time() - t0, 5))
