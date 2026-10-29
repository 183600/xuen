"""PBC-ICF: parallel backtracking certificate complex for ICF-PACT.

Round 2 extends the v9.0 one-leaf state

    (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U

by keeping *every* audited probe result, not only the current bracket.
The resulting object is a certificate complex

    K = ({ (h, NO(pi_h)) }, { (c, YES(s_c)) })

with derived bracket

    L(K) = 1 + max{ h : NO(h) in K }
    U(K) = min{ c : YES(c) in K }.

The key observation is that a probe result covers a half-line:

    NO(h)  => NO(h') for every h' <= h
    YES(h) with Cmax=c => YES(h') for every h' >= c.

Therefore the unresolved horizons always form one interval [L,U-1], and
a batch of independent probes can be merged by max/min.  A batch is
executed in BSP fashion.  A NO backjumps over the lower half of the
interval, a YES backjumps over the upper half, and an UNKNOWN leaves
the point as a hole to be retried at another horizon.

The implementation uses the complete PACT oracle in the experiments.
The one-leaf ICF is the special case P=1 with a lower-first split rule.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax,
                 _choose_h)
from pact import PACT, pact_decide
from rdf import check_schedule


# --------------------------------------------------------------- oracle
def _probe_task(task):
    """Top-level worker: one independent fixed-horizon decision."""
    inst, h = task
    r = pact_decide(inst, h, depthcap=None, nodecap=None,
                    forbid0=frozenset())
    v = r.get('verdict')
    if v is not None:
        r['verdict'] = bool(v)
    return r


# ------------------------------------------------------- certificate complex
class CertificateComplex:
    """A monotone set of audited NO/YES certificates.

    ``no`` maps h -> proof with proof.h == h.
    ``yes`` maps c -> (schedule, machine) with Cmax(schedule) == c.
    The derived bracket is (max(no)+1, min(yes)).
    """

    def __init__(self, inst, L, U, schedule, machine, lb_proof):
        self.inst = inst
        self.no = {int(L) - 1: lb_proof}
        self.yes = {int(U): (list(schedule), list(machine))}
        self.checks = 0
        self.fail = 0

    def add_no(self, h, proof):
        h = int(h)
        if proof is None or getattr(proof, 'h', None) != h:
            return False
        if not proof.audit_rdf():
            return False
        self.no[h] = proof
        return True

    def add_yes(self, h, schedule, machine):
        h = int(h)
        if schedule is None or machine is None:
            return False
        c = cmax(self.inst, schedule)
        if c > h:
            return False
        if not check_schedule(self.inst, c, schedule, machine):
            return False
        if c not in self.yes:
            self.yes[c] = (list(schedule), list(machine))
        return True

    def bracket(self):
        L = max(self.no) + 1 if self.no else 0
        U = min(self.yes) if self.yes else 10 ** 18
        return int(L), int(U)

    def current(self):
        L, U = self.bracket()
        if L - 1 not in self.no or U not in self.yes:
            return None
        s, m = self.yes[U]
        return L, U, self.no[L - 1], list(s), list(m)

    def audit_rdf(self):
        self.checks += 1
        try:
            for h, p in self.no.items():
                if p is None or getattr(p, 'h', None) != h:
                    self.fail += 1
                    return False
                if not p.audit_rdf():
                    self.fail += 1
                    return False
            for c, (s, m) in self.yes.items():
                if cmax(self.inst, s) != c:
                    self.fail += 1
                    return False
                if not check_schedule(self.inst, c, s, m):
                    self.fail += 1
                    return False
            L, U = self.bracket()
            if L > U:
                self.fail += 1
                return False
            return True
        except Exception:
            self.fail += 1
            return False


# ------------------------------------------------------------- interval stack
class IntervalStack:
    """Disjoint unresolved intervals, sorted by left endpoint.

    Invariant: the union of intervals is exactly the unresolved part of
    [L, U-1].  Adjacent intervals are merged.
    """

    def __init__(self, L, U):
        self.intervals = [[int(L), int(U) - 1]] if int(L) < int(U) else []
        self.first = True
        self.unknown = set()

    def clamp(self, L, U):
        out = []
        for a, b in self.intervals:
            a = max(int(a), int(L))
            b = min(int(b), int(U) - 1)
            if a > b:
                continue
            if out and out[-1][1] + 1 >= a:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        self.intervals = out

    def _h(self, a, b, policy):
        if policy == 'lower':
            base = a
        elif policy == 'upper':
            base = b
        elif policy in ('mid', 'binary'):
            base = (a + b + 1) // 2
        elif policy == 'lower-first':
            if self.first:
                self.first = False
                base = a
            else:
                base = (a + b + 1) // 2
        else:
            base = (a + b + 1) // 2
        if base not in self.unknown:
            return base
        for d in range(1, b - a + 1):
            for h in (base - d, base + d):
                if a <= h <= b and h not in self.unknown:
                    return h
        return base

    def untried(self):
        for a, b in self.intervals:
            for h in range(a, b + 1):
                if h not in self.unknown:
                    return True
        return False

    def build_batch(self, P, policy):
        """Choose up to P independent (iid, a, b, h) tasks.

        The first pass takes one point from each of the largest
        intervals.  Remaining worker slots are filled with additional
        quantiles of the largest intervals.  With P=1 this is exactly
        the sequential policy; with P>1 it is a parallel backtracking
        batch.
        """
        P = max(1, int(P))
        if not self.intervals:
            return []
        order = sorted(range(len(self.intervals)),
                       key=lambda i: (-(self.intervals[i][1] -
                                        self.intervals[i][0] + 1), i))
        tasks = []
        used = set()
        for i in order[:P]:
            a, b = self.intervals[i]
            h = self._h(a, b, policy)
            tasks.append((i, a, b, h))
            used.add((i, h))
        k = 0
        while len(tasks) < P:
            i = order[k % len(order)]
            a, b = self.intervals[i]
            g = b - a + 1
            added = False
            for j in range(1, P + 1):
                h = a + (j * g) // (P + 1)
                if h < a:
                    h = a
                if h > b:
                    h = b
                if (i, h) not in used and h not in self.unknown:
                    tasks.append((i, a, b, h))
                    used.add((i, h))
                    added = True
                    break
            if not added:
                for h in range(a, b + 1):
                    if (i, h) not in used and h not in self.unknown:
                        tasks.append((i, a, b, h))
                        used.add((i, h))
                        added = True
                        break
            k += 1
            if k > 4 * P and not added:
                break
        return tasks

    def update(self, inst, old_intervals, tasks, results, L, U):
        """Replace the intervals by their unresolved parts."""
        by_iid = {}
        for (iid, a, b, h), r in zip(tasks, results):
            by_iid.setdefault(iid, []).append((a, b, h, r))
        out = []
        for iid, (a, b) in enumerate(old_intervals):
            if iid not in by_iid:
                out.append([a, b])
                continue
            lo, hi = a, b
            for _, _, h, r in by_iid[iid]:
                if not r.get('_accepted'):
                    continue
                v = r.get('verdict')
                if v is False:
                    lo = max(lo, h + 1)
                elif v is True:
                    c = cmax(inst, r['schedule'])
                    hi = min(hi, c - 1)
            if lo <= hi:
                out.append([lo, hi])
        self.intervals = out
        self.clamp(L, U)

# --------------------------------------------------------------- initial state
def initial_state(inst, initial=None):
    if initial is not None:
        L, U, s, m, pi = initial
        return int(L), int(U), list(s), list(m), pi
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, s, m = co.initial_bounds()
    if U is None:
        return None
    L, U = int(L), int(U)
    s, m = list(s), list(m)
    pi = co._ensure_lb_proof(L)
    if pi is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r.get('verdict') is False:
            pi = r['proof']
    if pi is None:
        return None
    return L, U, s, m, pi


# --------------------------------------------------------------- main loop
def run_pbc(inst, known, name, idx, policy='batch-mid', P=2,
            initial=None, max_rounds=128, max_probes=1024,
            pool=None, audit_every=True, collect_steps=False):
    """Run PBC-ICF and return one benchmark row."""
    t0 = time.time()
    init = initial_state(inst, initial)
    if init is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    P=P, ok=False, error='no-initial-state', t=0.0)
    L0, U0, s0, m0, pi0 = init
    if not check_schedule(inst, cmax(inst, s0), s0, m0):
        return dict(name=name, idx=idx, known=known, policy=policy,
                    P=P, ok=False, error='bad-initial-schedule', t=0.0)
    if pi0 is None or getattr(pi0, 'h', None) != L0 - 1:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    P=P, ok=False, error='bad-initial-proof', t=0.0)

    cx = CertificateComplex(inst, L0, U0, s0, m0, pi0)
    stack = IntervalStack(L0, U0)

    probes = rounds = 0
    lp = nodes = cert_lp = 0
    span_lp = span_nodes = 0
    useful = dominated = unknown = invalid = stalls = 0
    partial_ok = partial_fail = 0
    complex_checks = complex_fail = 0
    steps = []
    L, U = L0, U0

    def audit_state():
        nonlocal partial_ok, partial_fail, complex_checks, complex_fail
        if not audit_every:
            return
        cur = cx.current()
        if cur is None:
            partial_fail += 1
            complex_fail += 1
            return
        Lx, Ux, pi, s, m = cur
        pc = PartialCertificate(inst, Lx, Ux, s, m, pi, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        before = cx.fail
        ok = cx.audit_rdf()
        complex_checks += 1
        if not ok:
            complex_fail += 1
        else:
            # cx.audit_rdf already counted its own check; keep the
            # benchmark counter in sync with the class counter.
            pass

    audit_state()
    while L < U and probes < max_probes and rounds < max_rounds:
        tasks = stack.build_batch(P, policy)
        if not tasks:
            break
        old_intervals = [list(x) for x in stack.intervals]
        if pool is not None and len(tasks) > 1:
            rs = pool.map(_probe_task, [(inst, h) for _, _, _, h in tasks])
        else:
            rs = [_probe_task((inst, h)) for _, _, _, h in tasks]
        probes += len(tasks)
        rounds += 1
        round_lp = [r.get('lp_solves', 0) for r in rs]
        round_nodes = [r.get('nodes', 0) for r in rs]
        lp += sum(round_lp)
        nodes += sum(round_nodes)
        cert_lp += sum(r.get('cert_lp', 0) for r in rs)
        span_lp += max(round_lp) if round_lp else 0
        span_nodes += max(round_nodes) if round_nodes else 0

        for (iid, a, b, h), r in zip(tasks, rs):
            v = r.get('verdict')
            r['_accepted'] = False
            if v is False:
                if cx.add_no(h, r['proof']):
                    r['_accepted'] = True
                else:
                    invalid += 1
            elif v is True:
                if cx.add_yes(h, r['schedule'], r['machine']):
                    r['_accepted'] = True
                else:
                    invalid += 1
            else:
                unknown += 1
                stack.unknown.add(h)
        stack.update(inst, old_intervals, tasks, rs, *cx.bracket())
        L, U = cx.bracket()
        max_no = max(cx.no) if cx.no else -1
        min_yes = min(cx.yes) if cx.yes else 10 ** 18
        for (iid, a, b, h), r in zip(tasks, rs):
            if not r.get('_accepted'):
                continue
            v = r.get('verdict')
            if v is False:
                if h == max_no:
                    useful += 1
                else:
                    dominated += 1
            elif v is True:
                c = cmax(inst, r['schedule'])
                if c == min_yes:
                    useful += 1
                else:
                    dominated += 1
        if collect_steps:
            steps.append(dict(
                round=rounds, tasks=len(tasks), L=L, U=U,
                lp=sum(round_lp), nodes=sum(round_nodes),
                verdicts=[r.get('verdict') for r in rs]))
        accepted_any = any(r.get('_accepted') for r in rs)
        if not accepted_any and not stack.untried():
            stalls += 1
            audit_state()
            break
        audit_state()

    cur = cx.current()
    if cur is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    P=P, ok=False, error='no-current-certificate',
                    probes=probes, rounds=rounds, t=round(time.time()-t0, 4))
    L, U, pi, s, m = cur
    final = ICFCertificate(inst, U, s, m, pi) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, s, m, pi, probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, policy=policy, P=P,
        L0=L0, U0=U0, gap0=U0 - L0, L=L, U=U, opt=U,
        probes=probes, rounds=rounds,
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        span_lp=span_lp, span_nodes=span_nodes,
        useful=useful, dominated=dominated, unknown=unknown,
        invalid=invalid, stalls=stalls,
        partial_ok=partial_ok, partial_fail=partial_fail,
        complex_checks=complex_checks, complex_fail=complex_fail,
        certified=bool(L == U and final_ok),
        audit=final_ok, partial_final=partial_final,
        cert_h=(U - 1 if L == U else None),
        t=round(dt, 4),
        ok=bool(L == U == known and final_ok and
                partial_fail == 0 and complex_fail == 0 and
                partial_final),
    )
    if collect_steps:
        out['steps'] = steps
    return out


# --------------------------------------------------------------- corpora
def normal_items():
    from icf import corpora
    return [('normal', name, idx, inst, known, None)
            for _, name, idx, inst, known in corpora()]


def weak_items(min_gap=4):
    from hap import weak_rows
    return [('weak', name, idx, inst, known, ini)
            for _, name, idx, inst, known, ini in weak_rows(min_gap)]
