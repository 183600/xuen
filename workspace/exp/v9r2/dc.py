"""v9.2 ICF-DC: decompositional certification.

The observation is a proof rule, not a heuristic.  Suppose the job set is
partitioned into independent components: no precedence edge crosses a
component, and the eligible machine sets of different components are
disjoint.  Then

    OPT(inst) = max_c OPT(inst_c),

and, for every h, a global schedule of length h exists iff every
component has a schedule of length h.

Consequently a global NO(h) proof needs only *one* component NO(h)
proof: the other components cannot repair the infeasible one.  PACT's
monolithic BranchProof cannot use this rule; its leaf certificate must
make the full LP infeasible, so on a disjoint union of k copies it keeps
branching over all copies.  ICF-DC keeps the ICF state (L,U,s,m,pi), but
pi is now a component-local proof plus a partition certificate.

Search is also local: the decision at h is an AND over components, with
short-circuit on the first NO.  A disjoint union of k identical
components therefore costs one component decision on the NO side,
independent of k, while a global PACT decision grows with k.

The data structure is a union-find over jobs: union precedence endpoints
and all jobs eligible for the same machine.  Each component has a
disjoint machine set by construction, which is exactly the independence
condition used by the proof rule.
"""
import sys
import time

sys.path[:0] = ['exp/v9r2', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from pact import PACT, pact_decide
from rdf import check_schedule


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


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
    """Return [(jobs, machines)] with pairwise disjoint machine sets."""
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
    """Component instance with local job and machine indices."""
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
    """local[c] = (starts, machines) in component coordinates."""
    starts = [None] * inst['n']
    machs = [None] * inst['n']
    for (jobs, machines), (s, mm) in zip(comps, local):
        for j, i in enumerate(jobs):
            starts[i] = s[j]
            machs[i] = machines[mm[j]]
    return starts, machs


def dc_decide(inst, h, comps=None, timelimit=None, nodecap=None):
    """AND over independent components, short-circuiting on the first NO.

    Returns dict(verdict, critical, schedule, machine, comps, nodes,
    lp_solves, cert_lp, t, stopped).
    """
    t0 = time.time()
    if comps is None:
        comps = decomposition(inst)
    nodes = lp = cert = 0
    local_s = []
    for c, (jobs, machines) in enumerate(comps):
        sub, _, _ = subinstance(inst, jobs, machines)
        r = pact_decide(sub, h, depthcap=None, nodecap=nodecap,
                        timelimit=timelimit)
        nodes += r.get('nodes', 0)
        lp += r.get('lp_solves', 0)
        cert += r.get('cert_lp', 0)
        if r['verdict'] is False:
            return dict(verdict=False, critical=(c, sub, r['proof']),
                        schedule=None, machine=None, comps=comps,
                        nodes=nodes, lp_solves=lp, cert_lp=cert,
                        stopped=c + 1, t=round(time.time() - t0, 5))
        if r['verdict'] is True:
            local_s.append((r['schedule'], r['machine']))
            continue
        return dict(verdict=None, critical=None, schedule=None,
                    machine=None, comps=comps, nodes=nodes,
                    lp_solves=lp, cert_lp=cert, stopped=c + 1,
                    t=round(time.time() - t0, 5))
    s, m = merge_schedule(inst, comps, local_s)
    if not check_schedule(inst, h, s, m):
        return dict(verdict=None, critical=None, schedule=None,
                    machine=None, comps=comps, nodes=nodes,
                    lp_solves=lp, cert_lp=cert, stopped=len(comps),
                    t=round(time.time() - t0, 5))
    return dict(verdict=True, critical=None, schedule=s, machine=m,
                comps=comps, nodes=nodes, lp_solves=lp, cert_lp=cert,
                stopped=len(comps), t=round(time.time() - t0, 5))


class DCCertificate(Proof):
    """U-optimal schedule plus one component NO(U-1) proof.

    Audit:
      1. comps is a partition of all jobs with pairwise disjoint machine
         sets and no cross precedence edge;
      2. the global schedule is feasible and has makespan U;
      3. the critical component's proof is NO(U-1) (or NO(h) with
         h >= U-1) on that component.
    By the decomposition lemma, (3) implies global NO(U-1).
    """
    kind = 'icf-dc'

    def __init__(self, inst, opt, schedule, machine, comps, critical):
        super().__init__(inst, opt)
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
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
            if sub2['n'] != sub['n'] or sub2['p'] != list(sub['p']):
                return False
            if proof is None or proof.h < self.opt - 1:
                return False
            return bool(proof.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def dc_init(inst, comps=None):
    """Build the initial bracket from component-local PACT inits.

    Returns (L, U, schedule, machine, L_proof, critical, stats).  The
    L proof is the local proof of the component that attains max L_c.
    """
    if comps is None:
        comps = decomposition(inst)
    Ls, Us, local = [], [], []
    best = None
    lp = 0
    t0 = time.time()
    for c, (jobs, machines) in enumerate(comps):
        sub, _, _ = subinstance(inst, jobs, machines)
        co = PACT(sub, pact_mode='complete', use_ga=False)
        Lc, Uc, sc, mc = co.initial_bounds()
        lp += int(getattr(co, 'pin_lp', 0))
        pi = co._ensure_lb_proof(Lc)
        Ls.append(int(Lc))
        Us.append(int(Uc))
        local.append((list(sc), list(mc)))
        if best is None or Lc > best[0]:
            best = (int(Lc), c, sub, pi)
    L = max(Ls)
    U = max(Us)
    s, m = merge_schedule(inst, comps, local)
    if not check_schedule(inst, U, s, m):
        return None
    return dict(L=L, U=U, schedule=s, machine=m,
                critical=(best[1], best[2], best[3]),
                comps=comps, init_lp=lp,
                t=round(time.time() - t0, 5))


def solve_dc(inst, timelimit=None, nodecap=None, max_rounds=64,
             comps=None):
    """Run the component-local decision loop and return a certificate."""
    t0 = time.time()
    if comps is None:
        comps = decomposition(inst)
    st = dc_init(inst, comps)
    if st is None:
        return dict(ok=False, error='init', t=round(time.time() - t0, 5))
    L, U = st['L'], st['U']
    s, m = st['schedule'], st['machine']
    critical = st['critical']
    rounds = 0
    nodes = lp = cert = 0
    history = []
    while L < U and rounds < max_rounds:
        h = U - 1
        r = dc_decide(inst, h, comps=comps, timelimit=timelimit,
                      nodecap=nodecap)
        rounds += 1
        nodes += r['nodes']
        lp += r['lp_solves']
        cert += r['cert_lp']
        history.append(dict(h=h, v=r['verdict'],
                            stopped=r.get('stopped'),
                            nodes=r['nodes'], t=r['t']))
        if r['verdict'] is False:
            L = U
            critical = r['critical']
            break
        if r['verdict'] is True:
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U, s, m = c, r['schedule'], r['machine']
            else:
                break
            continue
        break
    final = DCCertificate(inst, U, s, m, comps, critical) \
        if L == U else None
    ok = bool(final is not None and final.audit_rdf())
    return dict(ok=ok, L=L, U=U, rounds=rounds, nodes=nodes, lp_solves=lp,
                cert_lp=cert, init_lp=st['init_lp'], history=history,
                cert=final if ok else None,
                t=round(time.time() - t0, 5))


def union_inst(inst, k, gap=0):
    """k disjoint copies of inst on disjoint machine sets."""
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
