"""DART-ICF: Dependency-aware Ranked Termination for ICF.

DART extends the live interval frontier of RAFA-PACT with three layers:

1. A replayable rank trace.  The frontier measure is

       rho = (U, sorted_desc{width(f): f open}, sum_{f open}(U-L_f)).

   Every transition appends a witness and the checker verifies the local
   arithmetic of the corresponding rank decrease.  The trace is part of the
   final certificate, so termination is certified, not just observed.

2. Dependency analysis.  When the complete decide oracle returns UNKNOWN,
   the split is chosen from the precedence DAG (critical tail / descendants)
   rather than from the fractional LP.  On disconnected inputs, an AND
   decomposition is used: a NO proof for one independent component is a
   global NO proof (ComponentNOProof).

3. SAT solving.  A SAT oracle produces YES schedules.  On UNSAT it returns a
   job-selector core; the core is closed under predecessors and handed to the
   LP/DPLL side.  If that restricted instance has a replayable NO proof, a
   CoreNOProof records the restriction and the sub-proof.  The SAT core is a
   heuristic: the NO claim is always certified by the LP side.
"""
import sys
import time
import collections

sys.path[:0] = ['exp/v9dart', 'exp/v9r2', 'exp/v9i', 'exp/v9m',
                'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from po import heads_tails
from rdf import check_schedule
from pact import PACT, pact_decide
from sage import _domain
from icf import cmax, corpora
from rafa import (Node, leaves, open_leaves, global_L, rank_of,
                  choose_split, arbitrary_split, _box_ok, _decode,
                  FrontierCertificate, lower_proof, choose_h,
                  root_box, box_forbid)
from dc import decomposition, subinstance, dc_decide
from satoracle import SATCoreOracle


# --------------------------------------------------------------- rank trace
class RankTrace:
    """A local well-foundedness certificate for the frontier measure.

    Each step stores the rank before/after and a witness.  audit() checks
    (a) the chain is contiguous, (b) every step strictly decreases the rank,
    and (c) the witness arithmetic matches the stated transition.
    """

    def __init__(self):
        self.initial = None
        self.final = None
        self.steps = []
        self.fail = 0
        self.kinds = collections.Counter()
        self.bad = []

    def start(self, rank):
        self.initial = rank
        self.final = rank

    def add(self, kind, before, after, witness=None):
        ok = bool(after < before)
        rec = dict(kind=kind, before=before, after=after,
                   witness=witness, ok=ok)
        if not ok:
            self.fail += 1
            if len(self.bad) < 8:
                self.bad.append(rec)
        self.steps.append(rec)
        self.final = after
        self.kinds[kind] += 1
        return ok

    @staticmethod
    def _split_ok(before, after, w):
        if before[0] != after[0] or before[2] != after[2]:
            return False
        if w is None:
            return False
        try:
            w0, w1 = int(w['w0']), int(w['w1'])
            ww = int(w['w'])
        except Exception:
            return False
        if not (0 < w0 < ww and 0 < w1 < ww and w0 + w1 == ww):
            return False
        b = list(before[1])
        try:
            b.remove(ww)
        except ValueError:
            return False
        b = sorted(b + [w0, w1], reverse=True)
        return tuple(b) == tuple(after[1])

    @staticmethod
    def _lift_ok(before, after, w):
        if before[0] != after[0] or before[1] != after[1]:
            return False
        if before[2] - after[2] <= 0:
            return False
        if w is None:
            return False
        try:
            return int(w['dL']) == before[2] - after[2]
        except Exception:
            return False

    @staticmethod
    def _drop_ok(before, after, w):
        if after[0] >= before[0]:
            return False
        if w is None:
            return False
        try:
            return (int(w['U0']) == before[0]
                    and int(w['U1']) == after[0]
                    and int(w['U1']) < int(w['U0']))
        except Exception:
            return False

    @staticmethod
    def _close_ok(before, after, w):
        if before[0] != after[0]:
            return False
        if before[2] - after[2] <= 0:
            return False
        if w is None:
            return False
        try:
            ww = int(w['w'])
        except Exception:
            return False
        b = list(before[1])
        try:
            b.remove(ww)
        except ValueError:
            return False
        return tuple(sorted(b, reverse=True)) == tuple(after[1])

    def _witness_ok(self, rec):
        kind = rec['kind']
        b, a, w = rec['before'], rec['after'], rec.get('witness')
        if kind == 'split':
            return self._split_ok(b, a, w)
        if kind == 'lift':
            return self._lift_ok(b, a, w)
        if kind == 'drop-U':
            return self._drop_ok(b, a, w)
        if kind == 'close':
            return self._close_ok(b, a, w)
        return True

    def audit(self):
        if self.initial is None:
            return False
        prev = self.initial
        for rec in self.steps:
            if rec['before'] != prev:
                return False
            if not (rec['after'] < rec['before']):
                return False
            if not self._witness_ok(rec):
                return False
            prev = rec['after']
        return self.fail == 0 and prev == self.final

    def summary(self):
        return dict(steps=len(self.steps), fail=self.fail,
                    kinds=dict(self.kinds), bad=self.bad,
                    initial=self.initial, final=self.final)


# ------------------------------------------------------- dependency proofs
def _partition_ok(inst, comps):
    seen = set()
    used_m = set()
    for jobs, machines in comps:
        js = set(jobs)
        if seen & js or len(js) != len(jobs):
            return False
        seen |= js
        ms = set(machines)
        if used_m & ms:
            return False
        used_m |= ms
        for i in jobs:
            if any(j not in js for j in inst['succ'][i]):
                return False
            if any(k not in ms for k in inst['elig'][i]):
                return False
    return len(seen) == inst['n']


def _same_sub(a, b):
    for key in ('n', 'm', 'p', 'pred', 'succ', 'elig'):
        if key in b and a.get(key) != b[key]:
            return False
    return True


class ComponentNOProof(Proof):
    """NO(h) from one infeasible independent component.

    The partition lemma says a full schedule exists iff every component has
    a schedule.  A NO proof for a single component therefore proves global
    NO(h).  The proof is global: it is valid for every box, so it can be
    reused by several frontier leaves.
    """

    kind = 'comp-no'

    def __init__(self, inst, h, comps, critical):
        super().__init__(inst, h)
        self.comps = list(comps)
        self.critical = critical
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            if not _partition_ok(self.inst, self.comps):
                return False
            c, sub, proof = self.critical
            if not (0 <= c < len(self.comps)):
                return False
            jobs, machines = self.comps[c]
            sub2, _, _ = subinstance(self.inst, jobs, machines)
            if not _same_sub(sub, sub2):
                return False
            if proof is None or proof.h < self.h:
                return False
            return bool(proof.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def restrict(inst, jobs):
    """The sub-instance induced by `jobs`, preserving machine indices."""
    jidx = {i: j for j, i in enumerate(jobs)}
    return dict(
        n=len(jobs), m=inst['m'],
        p=[inst['p'][i] for i in jobs],
        pred=[[jidx[j] for j in inst['pred'][i] if j in jidx]
              for i in jobs],
        succ=[[jidx[j] for j in inst['succ'][i] if j in jidx]
              for i in jobs],
        elig=[list(inst['elig'][i]) for i in jobs])


class CoreNOProof(Proof):
    """NO(h) for the full instance from a restricted dependency core.

    The checker verifies that `sub` is exactly `inst` restricted to `jobs`
    and that `proof` is a replayable NO(h') proof for `sub` with h' >= h.
    The restriction lemma (a schedule of the full instance restricts to a
    schedule of the sub-instance) then gives NO(h) for the full instance.
    """

    kind = 'core-no'

    def __init__(self, inst, h, jobs, sub, proof):
        super().__init__(inst, h)
        self.jobs = list(jobs)
        self.sub = sub
        self.proof = proof
        self.forbid0 = frozenset()

    def audit_rdf(self):
        try:
            n = self.inst['n']
            if not self.jobs or len(set(self.jobs)) != len(self.jobs):
                return False
            if any(not (0 <= i < n) for i in self.jobs):
                return False
            sub2 = restrict(self.inst, self.jobs)
            if not _same_sub(self.sub, sub2):
                return False
            if self.proof is None or self.proof.h < self.h:
                return False
            return bool(self.proof.audit_rdf())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class DARTProof(FrontierCertificate):
    kind = 'dart-frontier'

    def __init__(self, inst, L, U, schedule, machine, root,
                 rank_trace=None, stats=None):
        super().__init__(inst, L, U, schedule, machine, root)
        self.rank_trace = rank_trace
        self.stats = stats or {}

    def audit_rdf(self):
        return bool(super().audit_rdf()
                    and (self.rank_trace is None
                         or self.rank_trace.audit()))


# ----------------------------------------------------------- dependency split
def _desc_counts(inst):
    n = inst['n']
    out = [0] * n
    for i in range(n):
        seen = set()
        stack = list(inst['succ'][i])
        while stack:
            j = stack.pop()
            if j in seen:
                continue
            seen.add(j)
            stack.extend(inst['succ'][j])
        out[i] = len(seen)
    return out


def dep_split(inst, h, lo, hi, desc=None, mode='q'):
    n = inst['n']
    if desc is None:
        desc = _desc_counts(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    best = None
    for i in range(n):
        a, b = _domain(inst, h, i)
        times = [t for t in range(max(a, lo[i]), min(b, hi[i]) + 1)]
        if len(times) < 2:
            continue
        w = times[-1] - times[0] + 1
        if mode == 'desc':
            key = (desc[i], w, q[i] + inst['p'][i], -i)
        elif mode == 'width':
            key = (w, desc[i], q[i] + inst['p'][i], -i)
        else:
            key = (q[i] + inst['p'][i], desc[i], w, -i)
        if best is None or key > best[0]:
            best = (key, i, times)
    if best is None:
        return None
    _, i, times = best
    mid = times[len(times) // 2 - 1]
    return (i, mid)


def _close_predecessors(inst, jobs):
    out = set(jobs)
    stack = list(jobs)
    while stack:
        i = stack.pop()
        for j in inst['pred'][i]:
            if j not in out:
                out.add(j)
                stack.append(j)
    return sorted(out)


# ------------------------------------------------------------------ init
def init_state(inst, mode='pact'):
    if mode == 'pact':
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        if U is None:
            return None
        p = co._ensure_lb_proof(int(L))
        if p is None or p.h != int(L) - 1 or not p.audit_rdf():
            p, co = lower_proof(inst, int(L))
        if p is None:
            return None
        L, U = int(L), int(U)
    elif mode == 'weakub':
        from hap import init_weak
        L, U, s, m, p = init_weak(inst)
        L, U = int(L), int(U)
        if p is None or p.h != L - 1 or not p.audit_rdf():
            p, co = lower_proof(inst, L)
        if p is None:
            return None
    else:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, s, m = co.initial_bounds()
        if ub is None:
            return None
        from apex import bound_lb
        L = int(bound_lb(inst))
        U = int(ub)
        if L > U:
            L = int(lb)
        p, co = lower_proof(inst, L)
        if p is None:
            return None
    if not check_schedule(inst, U, s, m):
        return None
    if cmax(inst, s) != U:
        U = cmax(inst, s)
    lo, hi = root_box(inst, U)
    root = Node(lo, hi, L, p)
    if L >= U:
        root.dead = True
    return dict(root=root, U=U, schedule=list(s), machine=list(m),
                L0=L, U0=U, co=None)


# ------------------------------------------------------------------ decide
def dart_decide(inst, h, F, flags, comps, sat, desc, cap=None):
    stats = dict(sat_calls=0, sat_yes=0, sat_no=0, sat_unknown=0,
                 core_calls=0, core_n=0, comp_calls=0, comp_no=0,
                 proof_kind=None)
    # SAT YES is sound for every box; it only supplies an upper bound.
    if flags.get('sat_yes') and sat is not None:
        r = sat.solve(h, want_core=False)
        stats['sat_calls'] += 1
        if r['verdict'] is True:
            stats['sat_yes'] += 1
            stats['proof_kind'] = 'sat-yes'
            return dict(verdict=True, schedule=r['schedule'],
                        machine=r['machine'], proof=None,
                        lp_solves=0, cert_lp=0, nodes=0, stats=stats)
        if r['verdict'] is False:
            stats['sat_no'] += 1
        else:
            stats['sat_unknown'] += 1
    # Independent-component AND decomposition (only for the unrestricted box).
    if flags.get('comp') and comps is not None and len(comps) > 1 \
            and not F:
        r = dc_decide(inst, h, comps=comps)
        stats['comp_calls'] += 1
        if r['verdict'] is False and r.get('critical') is not None:
            p = ComponentNOProof(inst, h, comps, r['critical'])
            if p.audit_rdf():
                stats['comp_no'] += 1
                stats['proof_kind'] = 'comp-no'
                return dict(verdict=False, proof=p, schedule=None,
                            machine=None, lp_solves=r.get('lp_solves', 0),
                            cert_lp=r.get('cert_lp', 0),
                            nodes=r.get('nodes', 0), stats=stats)
        elif r['verdict'] is True:
            stats['proof_kind'] = 'comp-yes'
            return dict(verdict=True, schedule=r['schedule'],
                        machine=r['machine'], proof=None,
                        lp_solves=r.get('lp_solves', 0),
                        cert_lp=r.get('cert_lp', 0),
                        nodes=r.get('nodes', 0), stats=stats)
    # SAT UNSAT core -> restricted LP/DPLL proof.
    if flags.get('sat_core') and sat is not None:
        r = sat.solve(h, want_core=True)
        stats['sat_calls'] += 1
        if r['verdict'] is False:
            stats['sat_no'] += 1
            core = r.get('core_jobs')
            if core and len(core) < inst['n']:
                jobs = _close_predecessors(inst, core)
                if len(jobs) < inst['n']:
                    sub = restrict(inst, jobs)
                    rr = pact_decide(sub, h, depthcap=cap, nodecap=None)
                    stats['core_calls'] += 1
                    stats['core_n'] = len(jobs)
                    if rr['verdict'] is False and rr['proof'] is not None:
                        p = CoreNOProof(inst, h, jobs, sub, rr['proof'])
                        if p.audit_rdf():
                            stats['proof_kind'] = 'core-no'
                            return dict(verdict=False, proof=p,
                                        schedule=None, machine=None,
                                        lp_solves=rr.get('lp_solves', 0),
                                        cert_lp=rr.get('cert_lp', 0),
                                        nodes=rr.get('nodes', 0),
                                        stats=stats)
        elif r['verdict'] is True:
            stats['sat_yes'] += 1
            stats['proof_kind'] = 'sat-yes'
            return dict(verdict=True, schedule=r['schedule'],
                        machine=r['machine'], proof=None,
                        lp_solves=0, cert_lp=0, nodes=0, stats=stats)
        else:
            stats['sat_unknown'] += 1
    # Full complete certificate search.
    r = pact_decide(inst, h, depthcap=cap, nodecap=None, forbid0=F)
    r = dict(r)
    r['stats'] = stats
    r['proof_kind'] = getattr(r.get('proof'), 'kind', None)
    return r


# ------------------------------------------------------------------ main
def run_dart(inst, known, name, idx, policy='lower-first', eps=0.1,
             mode='pact', max_probes=256, max_leaves=512, dep=False,
             cap=None,
             dep_mode='q', sat_yes=False, sat_core=False, comp=False,
             audit_states=False, timelimit=None, max_core=0,
             sat_min_n=0):
    t0 = time.time()
    st = init_state(inst, mode=mode)
    if st is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='init', t=round(time.time() - t0, 4))
    root = st['root']
    U = st['U']
    sched, mach = st['schedule'], st['machine']
    L0, U0 = st['L0'], st['U0']
    desc = _desc_counts(inst) if dep else None
    comps = decomposition(inst) if comp else None
    sat = SATCoreOracle(inst, min_n=sat_min_n) if (sat_yes or sat_core) \
        else None
    flags = dict(sat_yes=sat_yes, sat_core=sat_core, comp=comp)
    trace = RankTrace()
    trace.start(rank_of(root, U))
    probes = lp = cert_lp = nodes = 0
    yes = no = unknown = splits = 0
    state_audits = state_fail = 0
    core_used = comp_used = 0
    phase = 0
    stop_reason = 'budget'

    def current_L():
        return global_L(root, U)

    def cleanup_dead():
        for nd in leaves(root):
            if nd.children is None and not nd.dead and nd.L >= U:
                nd.dead = True

    def audit_now():
        nonlocal state_audits, state_fail
        if not audit_states:
            return
        L = current_L()
        cert = DARTProof(inst, L, U, sched, mach, root, trace)
        state_audits += 1
        if not cert.audit_rdf():
            state_fail += 1

    def split_node(f, i, mid):
        if not (f.lo[i] <= mid < f.hi[i]):
            return False
        left_hi = list(f.hi)
        left_hi[i] = mid
        right_lo = list(f.lo)
        right_lo[i] = mid + 1
        left = Node(f.lo, left_hi, f.L, f.proof)
        right = Node(right_lo, f.hi, f.L, f.proof)
        f.children = (left, right)
        f.split = (i, mid)
        return True

    audit_now()
    while probes < max_probes:
        if timelimit is not None and time.time() - t0 > timelimit:
            stop_reason = 'time'
            break
        L = current_L()
        if L >= U:
            stop_reason = 'exact'
            break
        if len([nd for nd in leaves(root) if nd.children is None
                and not nd.dead]) > max_leaves:
            stop_reason = 'leaves'
            break
        opens = open_leaves(root, U)
        if not opens:
            stop_reason = 'exact'
            break
        f = min(opens, key=lambda nd: (nd.L, -nd.width(), id(nd)))
        Lf = f.L
        h = choose_h(policy, L, U, phase, eps)
        if h < Lf:
            h = Lf
        if h >= U:
            h = U - 1
        phase += 1
        F = box_forbid(inst, h, f.lo, f.hi)
        r = dart_decide(inst, h, F, flags, comps, sat, desc, cap=cap)
        probes += 1
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        nodes += r.get('nodes', 0)
        st2 = r.get('stats') or {}
        if st2.get('proof_kind') == 'core-no':
            core_used += 1
        if st2.get('proof_kind') == 'comp-no':
            comp_used += 1
        changed = False
        if r['verdict'] is False:
            no += 1
            proof = r['proof']
            if proof is None:
                stop_reason = 'bad-no'
                break
            # A global proof may lift every open leaf whose L <= h.
            targets = [f]
            if getattr(proof, 'kind', '') in ('core-no', 'comp-no'):
                targets = [nd for nd in leaves(root)
                           if nd.children is None and not nd.dead
                           and nd.L <= h]
            for nd in targets:
                before = rank_of(root, U)
                nd.L = max(nd.L, h + 1)
                nd.proof = proof
                if nd.L >= U:
                    nd.dead = True
                    trace.add('close', before, rank_of(root, U),
                              dict(w=nd.width()))
                else:
                    trace.add('lift', before, rank_of(root, U),
                              dict(dL=h + 1 - Lf))
                changed = True
        elif r['verdict'] is True:
            yes += 1
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                before = rank_of(root, U)
                U0_old = U
                U = c2
                sched, mach = list(s2), list(m2)
                cleanup_dead()
                trace.add('drop-U', before, rank_of(root, U),
                          dict(U0=U0_old, U1=U))
                changed = True
            else:
                unknown += 1
                changed = True
        else:
            unknown += 1
            sp = None
            if dep:
                sp = dep_split(inst, h, f.lo, f.hi, desc=desc,
                               mode=dep_mode)
            if sp is None:
                sp = choose_split(inst, h, f.lo, f.hi)
            if sp is not None and sp[0] == 'no':
                rr = pact_decide(inst, h, depthcap=cap, nodecap=None,
                                 forbid0=F)
                lp += rr.get('lp_solves', 0)
                cert_lp += rr.get('cert_lp', 0)
                nodes += rr.get('nodes', 0)
                if rr['verdict'] is False and rr['proof'] is not None:
                    before = rank_of(root, U)
                    f.L = h + 1
                    f.proof = rr['proof']
                    if f.L >= U:
                        f.dead = True
                        trace.add('close', before, rank_of(root, U),
                                  dict(w=f.width()))
                    else:
                        trace.add('lift', before, rank_of(root, U),
                                  dict(dL=h + 1 - Lf))
                    changed = True
                elif rr['verdict'] is True:
                    c2 = cmax(inst, rr['schedule'])
                    if c2 < U and check_schedule(inst, c2,
                                                 rr['schedule'],
                                                 rr['machine']):
                        before = rank_of(root, U)
                        U0_old = U
                        U = c2
                        sched, mach = list(rr['schedule']), \
                            list(rr['machine'])
                        cleanup_dead()
                        trace.add('drop-U', before, rank_of(root, U),
                                  dict(U0=U0_old, U1=U))
                        changed = True
            elif sp is not None and sp[0] == 'yes':
                s2, m2 = sp[1]
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    before = rank_of(root, U)
                    U0_old = U
                    U = c2
                    sched, mach = list(s2), list(m2)
                    cleanup_dead()
                    trace.add('drop-U', before, rank_of(root, U),
                              dict(U0=U0_old, U1=U))
                    changed = True
            elif sp is not None and sp[0] == 'split':
                i, mid = sp[1]
                before = rank_of(root, U)
                w = f.width()
                if split_node(f, i, mid):
                    a = f.children[0].width()
                    b = f.children[1].width()
                    splits += 1
                    trace.add('split', before, rank_of(root, U),
                              dict(w=w, w0=a, w1=b))
                    changed = True
            if not changed:
                fb = arbitrary_split(inst, h, f.lo, f.hi)
                if fb is None:
                    stop_reason = 'unknown'
                    break
                i, mid = fb
                before = rank_of(root, U)
                w = f.width()
                if not split_node(f, i, mid):
                    stop_reason = 'bad-split'
                    break
                a = f.children[0].width()
                b = f.children[1].width()
                splits += 1
                trace.add('split', before, rank_of(root, U),
                          dict(w=w, w0=a, w1=b))
                changed = True
        if not changed:
            stop_reason = 'no-progress'
            break
        audit_now()

    L = current_L()
    exact = bool(L == U)
    cert = DARTProof(inst, L, U, sched, mach, root, trace)
    final_ok = bool(cert.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, eps=eps,
        mode=mode, dep=dep, dep_mode=dep_mode, sat_yes=sat_yes,
        sat_core=sat_core, comp=comp,
        L=L, U=U, L0=L0, U0=U0, known_ok=bool(U == known and L == known),
        certified=bool(exact and final_ok), audit=final_ok,
        proof_kind=cert.kind, exact=exact,
        ratio=(U / L if L > 0 else None),
        probes=probes, lp=lp, cert_lp=cert_lp, nodes=nodes,
        yes=yes, no=no, unknown=unknown, splits=splits,
        leaves=len(leaves(root)),
        max_open=len(open_leaves(root, U)),
        rank_steps=len(trace.steps), rank_fail=trace.fail,
        rank_audit=trace.audit(),
        rank_kinds=dict(trace.kinds),
        core_used=core_used, comp_used=comp_used,
        sat=(sat.summary() if sat is not None else None),
        state_audits=state_audits, state_fail=state_fail,
        stop_reason=stop_reason, t=round(dt, 4),
        ok=bool(exact and U == known and final_ok
                and trace.fail == 0 and trace.audit()
                and state_fail == 0),
    )


def dart_corpora():
    for tag, name, idx, inst, known in corpora():
        yield tag, name, idx, inst, known
