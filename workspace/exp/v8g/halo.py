"""v8.2 HALO-ALC: Hall-certified Operational Lower-bound Orchestration.

HALO builds on v8.1 CRISP-ALC.  The bracket [LB, UB] is kept, but the
lower side is computed by a *coalition* of preemptive relaxations, one
per non-empty machine subset M'.  For a fixed h and M', jobs whose
eligibility is contained in M' must run on M' inside their precedence
windows [est_i, h-q_i).  Allowing preemption and migration is a
relaxation.  Its feasibility is a bipartite b-matching (max-flow):

    source -> job i          capacity p_i
    job i -> slot t          capacity 1     (t in window)
    slot t -> sink           capacity |M'|

If the flow is short, the min cut yields a witness B (a set of time
slots) with

    sum_i max(0, p_i - |window_i minus B|) > |M'| * |B|.

This is a *Hall certificate*.  A single interval B is exactly the v8.1
energy certificate; a union of intervals is strictly more general.  The
checker recomputes the demand and capacity with integer arithmetic, so
the certificate is independent of the flow solver.

The outer optimizer is a small-step operational semantics over
configurations (lb, ub, incumbent, proof store).  Every transition is
guarded by a replayable certificate:

  HALL_LIFT   verify_hall(inst, h, c)  =>  lb := h+1
  ORACLE_NO   audit_rdf / proof_complete =>  lb := h+1
  ORACLE_YES  check_schedule             =>  ub := min(ub, Cmax)
  FINAL_HALL  verify_hall(inst, ub-1, c)  =>  certified

The proof store is first-class: a verified Hall/energy certificate at
UB-1 is just as good as an oracle NO.  This is what lets HALO skip the
final oracle call on instances where the preemptive relaxation is tight.

The coalition decomposition is embarrassingly parallel: coalition M'
only sees the jobs forced onto M', and the global lower bound is the max
of the coalition thresholds.  The implementation below runs them
sequentially, but no information is exchanged between coalitions except
the final maximum.
"""
import sys
import time
from collections import deque

sys.path[:0] = ['exp/v13', 'exp/v9c', 'exp/v8c', 'exp/v9d', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60']

from cab import CABOpt, _greedy_rank
from chip import chip_bounds, base_bounds, order_portfolio
from chd import CHD
from po import heads_tails
from rdf import check_schedule
from scale import verify_prep, energy_cert, windows


# ------------------------------------------------------------------ dinic
class Dinic:
    __slots__ = ('n', 'g')

    def __init__(self, n):
        self.n = n
        self.g = [[] for _ in range(n)]

    def add(self, u, v, c):
        self.g[u].append([v, c, len(self.g[v])])
        self.g[v].append([u, 0, len(self.g[u]) - 1])

    def flow(self, s, t):
        res = 0
        while True:
            lvl = [-1] * self.n
            lvl[s] = 0
            q = deque([s])
            while q:
                u = q.popleft()
                for v, c, r in self.g[u]:
                    if c > 0 and lvl[v] < 0:
                        lvl[v] = lvl[u] + 1
                        q.append(v)
            if lvl[t] < 0:
                return res
            it = [0] * self.n

            def dfs(u, f):
                if u == t:
                    return f
                gu = self.g[u]
                while it[u] < len(gu):
                    e = gu[it[u]]
                    v, c, r = e
                    if c > 0 and lvl[v] == lvl[u] + 1:
                        d = dfs(v, min(f, c))
                        if d > 0:
                            e[1] -= d
                            self.g[v][r][1] += d
                            return d
                    it[u] += 1
                return 0

            while True:
                f = dfs(s, 10 ** 9)
                if not f:
                    break
                res += f

    def reach(self, s):
        seen = [False] * self.n
        seen[s] = True
        st = [s]
        while st:
            u = st.pop()
            for v, c, r in self.g[u]:
                if c > 0 and not seen[v]:
                    seen[v] = True
                    st.append(v)
        return seen


# --------------------------------------------------------------- coalitions
def coalitions(inst):
    """Non-empty machine subsets with the jobs that are forced onto them."""
    n, m = inst['n'], inst['m']
    out = []
    for mask in range(1, 1 << m):
        M = tuple(k for k in range(m) if (mask >> k) & 1)
        Ms = set(M)
        js = [i for i in range(n)
              if set(inst['elig'][i]) <= Ms]
        if js:
            out.append((M, js))
    # The full set is always the largest coalition and is enough for the
    # corpus used here; the others only matter for heterogeneous eligibility.
    return out


def hall_cert(inst, h, max_coalitions=64):
    """Return a verified Hall certificate at h, or None if all coalitions fit.

    The flow is a relaxation: every non-preemptive schedule with makespan
    <= h induces a feasible flow.  Thus a short flow is a valid NO.
    """
    if h <= 0:
        return None
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    T = h
    for M, js in coalitions(inst)[:max_coalitions]:
        r = len(M)
        S = 0
        off = 1
        toff = off + len(js)
        sink = toff + T
        din = Dinic(sink + 1)
        tot = 0
        for a, i in enumerate(js):
            din.add(S, off + a, p[i])
            tot += p[i]
            lo = max(0, est[i])
            hi = min(T, h - q[i])
            for t in range(lo, hi):
                din.add(off + a, toff + t, 1)
        for t in range(T):
            din.add(toff + t, sink, r)
        f = din.flow(S, sink)
        if f < tot:
            seen = din.reach(S)
            B = [t for t in range(T) if seen[toff + t]]
            Bs = set(B)
            demand = 0
            for i in js:
                lo = max(0, est[i])
                hi = min(T, h - q[i])
                outside = sum(1 for t in range(lo, hi) if t not in Bs)
                demand += max(0, p[i] - outside)
            if demand > r * len(B):
                return dict(kind='hall', M=list(M), jobs=js, B=B,
                            demand=demand, cap=r * len(B), h=h,
                            total=tot, flow=f)
    return None


def hall_intervals(cert):
    """Compress a Hall witness into maximal integer intervals [a,b)."""
    if cert is None or cert.get('kind') != 'hall':
        return []
    out = []
    for t in sorted(cert['B']):
        if out and t == out[-1][1]:
            out[-1][1] = t + 1
        else:
            out.append([t, t + 1])
    return out


def verify_hall(inst, h, cert):
    """Independent replay of a Hall or energy/window NO certificate."""
    if cert is None:
        return False
    kind = cert.get('kind')
    if kind in ('energy', 'window'):
        return verify_prep(inst, h, cert)
    if kind != 'hall':
        return False
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    T = h
    M = set(cert['M'])
    B = set(cert['B'])
    js = [i for i in range(n) if set(inst['elig'][i]) <= M]
    if js != list(cert['jobs']):
        return False
    demand = 0
    for i in js:
        lo = max(0, est[i])
        hi = min(T, h - q[i])
        outside = sum(1 for t in range(lo, hi) if t not in B)
        demand += max(0, p[i] - outside)
    cap = len(M) * len(B)
    return (demand == cert['demand'] and cap == cert['cap']
            and demand > cap and h == cert['h'])


# ------------------------------------------------------------------ bounds
def energy_boundary_cert(inst, h):
    """The v8.1 energy/window certificate at the lower boundary H-1.

    This is the ablation counterpart of `hall_cert`: it does not add a
    stronger bound, it only materializes the certificate that v8.1 would
    have produced if H-1 were below the initial lower bound.
    """
    if h < 0:
        return None
    c = energy_cert(inst, h, 64, 20000)
    if c is None:
        ee, ll, _ = windows(inst, h)
        if not any(ee[i] > ll[i] for i in range(inst['n'])):
            return None
        c = dict(kind='window')
    if c['kind'] == 'energy':
        good = verify_prep(inst, h, c)
    else:
        ee, ll, _ = windows(inst, h)
        good = any(ee[i] > ll[i] for i in range(inst['n']))
    return c if good else None


def halo_bounds(inst, verify=True):
    """Compute the CRISP bracket and add a Hall certificate at lb-1."""
    t0 = time.time()
    b = chip_bounds(inst, verify=verify)
    b['chip_t'] = time.time() - t0
    if not b.get('ok'):
        return b
    t0 = time.time()
    h = b['lb'] - 1
    c = None
    if h >= 0:
        c = hall_cert(inst, h)
        if verify and c is not None and not verify_hall(inst, h, c):
            c = None
            b['hall_bad'] = 1
        else:
            b['hall_bad'] = 0
    b['hall_cert'] = c
    b['hall_h'] = h if c is not None else None
    b['hall_t'] = time.time() - t0
    return b


# ------------------------------------------------------------------ HALO
class HALO(CABOpt):
    """Proof-carrying bracket with a Hall lower-bound engine.

    mode='proof': binary search; a verified Hall certificate at opt-1 is
                  accepted as the final NO proof.
    mode='probe': the same, plus one tightness probe at h=lb before the
                  binary search.  A YES at lb closes the instance in one
                  query; a NO raises lb by one.
    """

    def __init__(self, inst, mode='proof', engine='hall', **kw):
        super().__init__(inst, **kw)
        self.mode = mode
        self.engine = engine
        self.chip = None
        self.certs = {}
        self.cert_h = None
        self.zero = 0
        self.hall_final = 0
        self.probe_yes = 0
        self.probe_no = 0
        self.flow_calls = 0
        self.chip_time = 0.0
        self.flow_time = 0.0
        self.oracle_time = 0.0
        self.init_lb = self.init_ub = None
        self.init_schedule = self.init_machine = None
        self.steps = []

    # --------------------------------------------------------- bounds
    def initial_bounds(self):
        t0 = time.time()
        if self.engine == 'energy':
            b = chip_bounds(self.inst)
            h = b['lb'] - 1
            if h >= 0 and h not in dict(b.get('certs', [])):
                c = energy_boundary_cert(self.inst, h)
                if c is not None:
                    b = dict(b)
                    b['certs'] = list(b.get('certs', [])) + [(h, c)]
        else:
            b = halo_bounds(self.inst)
        self.chip_time += time.time() - t0
        self.chip = b
        self.init_lb, self.init_ub = b['lb0'], b['ub0']
        self.init_schedule = b.get('schedule')
        self.init_machine = b.get('machine')
        for h, c in b.get('certs', []):
            self.certs[h] = c
        if self.engine != 'energy' and b.get('hall_cert') is not None:
            self.certs[b['hall_h']] = b['hall_cert']
        self.flow_calls += 1 if b.get('hall_cert') is not None else 0
        return b['lb'], b['ub'], b.get('schedule'), b.get('machine')

    def _cert(self, h):
        if h in self.certs:
            return self.certs[h]
        if self.engine == 'energy':
            return None
        t0 = time.time()
        c = hall_cert(self.inst, h)
        self.flow_calls += 1
        self.flow_time += time.time() - t0
        if c is not None and verify_hall(self.inst, h, c):
            self.certs[h] = c
            return c
        return None

    # --------------------------------------------------------- oracle
    def _decide(self, h):
        t0 = time.time()
        rdf = CHD(self.inst, h, yes_scan=True, cheap_disc=2,
                  hull_disc=4, hull_on=True)
        try:
            v, st = rdf.decide(budget=self.per_query_lp,
                               nodecap=self.per_query_nodes)
        except Exception:
            v, st = None, rdf._stats('exception')
        self.oracle_time += time.time() - t0
        self.last_oracle = rdf
        return v, st, rdf

    def _oracle(self, h, rule):
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        rec = dict(h=h, v=v, rule=rule, lb=self.lb, ub=self.opt,
                   lb_before=self.lb, ub_before=self.opt,
                   lp=st.get('lp_solves', 0),
                   yes_nodes=st.get('yes_nodes', 0),
                   mc_evals=st.get('mc_evals', 0),
                   rdf=rdf, schedule=None, machine=None, cmax=None,
                   cert=None)
        if v is True:
            cmax = max(rdf.schedule[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            rec['cmax'] = cmax
            rec['schedule'] = list(rdf.schedule)
            rec['machine'] = list(rdf.machine)
            if cmax < self.opt:
                self.opt = cmax
                self.schedule = list(rdf.schedule)
                self.machine = list(rdf.machine)
        elif v is False:
            self.lb = max(self.lb, h + 1)
            self.no_states[h] = rdf
            self.lb_proof = rdf
        else:
            self.unknown += 1
        rec['lb_after'] = self.lb
        rec['ub_after'] = self.opt
        self.steps.append(rec)
        self.trace.append(dict(h=h, v=v, lb=self.lb, ub=self.opt,
                               lp=rec['lp'], nodes=rec['yes_nodes'],
                               yes_nodes=rec['yes_nodes'],
                               mc_evals=rec['mc_evals']))
        return v, rdf

    # --------------------------------------------------------- main loop
    def optimize(self):
        lb, ub, starts, machs = self.initial_bounds()
        self.lb0, self.ub0 = lb, ub
        self.lb = lb
        if ub is None:
            self.certified = False
            return self._result()
        self.schedule, self.machine, self.opt = starts, machs, ub

        # certify the lower boundary H-1 (this is a proof, not a search step)
        if lb > 0 and (lb - 1) not in self.certs:
            self._cert(lb - 1)
        # zero-query boundary test at the incumbent
        if self.opt - 1 >= 0:
            c = self.certs.get(self.opt - 1)
            if c is None:
                c = self._cert(self.opt - 1)
            if c is not None:
                self.lb = self.opt
                self.certified = True
                self.zero = 1
                return self._result()

        # one tightness probe at lb: tests whether the preemptive
        # threshold is already the integer optimum.
        if self.mode == 'probe' and self.lb < self.opt \
                and (self.lb - 1) in self.certs:
            v, rdf = self._oracle(self.lb, 'probe')
            if v is True:
                self.certified = True
                self.probe_yes = 1
                return self._result()
            if v is False:
                self.probe_no = 1
            elif self.lb < self.opt:
                pass

        while self.lb < self.opt and self.queries < self.max_queries:
            h = (self.lb + self.opt) // 2
            if h in self.certs:
                self.lb = max(self.lb, h + 1)
                self.steps.append(dict(h=h, v=False, rule='stored-cert',
                                       lb_before=self.lb, ub_before=self.opt,
                                       lb_after=self.lb,
                                       ub_after=self.opt, cert=self.certs[h],
                                       rdf=None, schedule=None,
                                       machine=None, cmax=None, lp=0,
                                       yes_nodes=0, mc_evals=0))
                continue
            v, rdf = self._oracle(h, 'bisect')
            if v is None:
                v2, rdf2 = self._oracle(h, 'retry')
                if v2 is None:
                    break

        self.certified = (self.lb == self.opt and self.opt is not None)
        if self.certified:
            h = self.opt - 1
            if h not in self.no_states:
                c = self.certs.get(h)
                if c is None:
                    c = self._cert(h)
                if c is None and h >= 0:
                    v, rdf = self._oracle(h, 'final')
                    if v is not False:
                        self.certified = False
                else:
                    self.hall_final = 1
        return self._result()

    # --------------------------------------------------------- result
    def _result(self):
        audit = False
        proof = False
        cert_h = None
        kind = None
        cert = None
        if self.lb_proof is not None:
            cert_h = self.lb_proof.h
            audit = bool(self.lb_proof.audit_rdf())
            proof = bool(self.lb_proof.proof_complete())
            kind = 'rdf'
        h = None if self.opt is None else self.opt - 1
        if self.certified and h is not None and h in self.certs:
            c = self.certs[h]
            if verify_hall(self.inst, h, c):
                cert = c
                cert_h = h
                audit = True
                proof = True
                kind = c.get('kind', 'hall')
        if self.schedule is not None:
            audit = audit and check_schedule(self.inst, self.opt,
                                             self.schedule, self.machine)
        gap = None if self.opt is None else self.opt - self.lb
        ratio = (None if self.opt is None or not self.lb
                 else self.opt / self.lb)
        span = (None if self.ub0 is None or self.lb0 is None
                else self.ub0 - self.lb0)
        return dict(opt=self.opt, lb=self.lb, certified=self.certified,
                    gap=gap, ratio=ratio, queries=self.queries,
                    lb0=self.lb0, ub0=self.ub0,
                    lp=self.lp_total, yes_nodes=self.yes_nodes_total,
                    mc_evals=self.mc_evals_total, unknown=self.unknown,
                    audit=audit, proof=proof, cert_h=cert_h,
                    proof_kind=kind, cert=cert,
                    schedule=self.schedule, machine=self.machine,
                    trace=self.trace, steps=self.steps,
                    zero=self.zero, hall_final=self.hall_final,
                    probe_yes=self.probe_yes, probe_no=self.probe_no,
                    flow_calls=self.flow_calls,
                    chip=dict(lb0=self.chip.get('lb0'),
                              ub0=self.chip.get('ub0'),
                              lb=self.chip.get('lb'),
                              ub=self.chip.get('ub'),
                              lifts=self.chip.get('lifts'),
                              drops=self.chip.get('drops'),
                              cert_bad=self.chip.get('cert_bad'),
                              hall_h=self.chip.get('hall_h')),
                    chip_time=self.chip_time,
                    flow_time=self.flow_time,
                    oracle_time=self.oracle_time)


# ------------------------------------------------------------------ replay
def replay(inst, r, co):
    """Independent replay of the operational-semantics trace.

    Returns (ok, reason).  This is a second checker, not a re-run of the
    optimizer: it only consumes the recorded steps and certificates.
    """
    if not hasattr(co, 'init_schedule'):
        return True, 'not a HALO trace'
    steps = r.get('steps') or []
    lb, ub = r['lb0'], r['ub0']
    if lb is None or ub is None:
        return False, 'missing initial bounds'
    sched = co.init_schedule
    mach = co.init_machine
    if sched is not None and not check_schedule(inst, ub, sched, mach):
        return False, 'initial schedule'
    for st in steps:
        if st['lb_before'] != lb or st['ub_before'] != ub:
            return False, 'state mismatch'
        rule = st.get('rule')
        if rule == 'stored-cert':
            c = st.get('cert')
            if not verify_hall(inst, st['h'], c):
                return False, 'stored certificate'
            lb = max(lb, st['h'] + 1)
        elif st.get('v') is True:
            if st.get('schedule') is None:
                return False, 'missing schedule'
            if not check_schedule(inst, st['cmax'], st['schedule'],
                                  st['machine']):
                return False, 'YES schedule'
            ub = min(ub, st['cmax'])
            sched, mach = st['schedule'], st['machine']
        elif st.get('v') is False:
            rdf = st.get('rdf')
            if rdf is None:
                return False, 'missing NO state'
            if not (rdf.audit_rdf() and rdf.proof_complete()):
                return False, 'NO proof'
            lb = max(lb, st['h'] + 1)
        else:
            return False, 'UNKNOWN in trace'
        if st.get('lb_after') not in (None, lb):
            return False, 'lb after'
        if st.get('ub_after') not in (None, ub):
            return False, 'ub after'
    if lb > ub:
        return False, 'empty bracket'
    if r.get('certified'):
        if lb != ub:
            return False, 'not closed'
        if not check_schedule(inst, ub, r['schedule'], r['machine']):
            return False, 'final schedule'
        h = ub - 1
        ok = False
        if h in co.no_states:
            rdf = co.no_states[h]
            ok = bool(rdf.audit_rdf() and rdf.proof_complete())
        if h in co.certs:
            ok = ok or verify_hall(inst, h, co.certs[h])
        if not ok:
            return False, 'final NO proof'
    return True, 'ok'
