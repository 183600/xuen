"""v7.2 TCA-ALC: total-correctness ALC with two certified engines.

v7.1 QNC is a dual engine: it proves NO with integer Farkas/quorum
certificates.  Its YES side is accidental (an integral LP solution) and was
never measured: at h = OPT the start-time LP is usually fractional and the
threshold DFS can spend hundreds of LPs before finding an integral point.

TCA makes the decision procedure total in the certificate sense:

  * YES is returned only with an independently checked schedule witness;
  * NO  is returned only with a proof tree: Farkas leaves at essential
    scopes, exhaustive splits, global force reductions, and clause leaves;
  * UNKNOWN returns the open frontier.

The primal engine is a decrease-and-conquer schedule constructor: DEC
removes one ready job at a time, propagates its finish time, and recurses on
the remaining job set with a packing frontier.  A cheap multi-start list
scheduler is the first lane; DEC is the complete lane.  The dual engine is
ProofQNC, a v7.1 QNC whose DFS is instrumented to emit a checkable proof
tree.  The two engines can run as a portfolio; both outputs are verified by
check_certificate, so a bug in either engine cannot produce a wrong verdict.
"""
import sys, time, json, hashlib, random
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
import numpy as np
import cert as v60cert
from cert import verify
from qnc import QNC, Budget, farkas_int
from po import heads_tails, decide as dec_decide


# --------------------------------------------------------------------------
# schedule utility
# --------------------------------------------------------------------------
def make_domains(inst, h):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    dom = {}
    for i in range(n):
        lo, hi = est[i], h - q[i] - p[i]
        dom[i] = set(range(lo, hi + 1))
    return dom, est, q


def verify_schedule(inst, h, sched):
    """Independent schedule checker.  `sched` is [(job, machine, start)].

    Checks exactly the original instance data: eligibility, precedence,
    horizon, and per-machine non-overlap.  Returns (ok, reason).
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    if sched is None:
        return False, 'missing'
    start = [None] * n
    mach = [None] * n
    for item in sched:
        if not (isinstance(item, (tuple, list)) and len(item) == 3):
            return False, 'shape'
        i, k, t = int(item[0]), int(item[1]), int(item[2])
        if not (0 <= i < n) or not (0 <= k < m):
            return False, 'range'
        if start[i] is not None:
            return False, 'duplicate job %d' % i
        if k not in inst['elig'][i]:
            return False, 'eligibility'
        if t < 0 or t + p[i] > h:
            return False, 'horizon'
        start[i], mach[i] = t, k
    if any(x is None for x in start):
        return False, 'missing jobs'
    for i in range(n):
        for j in inst['pred'][i]:
            if start[i] < start[j] + p[j]:
                return False, 'precedence %d->%d' % (j, i)
    for k in range(m):
        jobs = sorted((start[i], start[i] + p[i])
                      for i in range(n) if mach[i] == k)
        for a, b in zip(jobs, jobs[1:]):
            if b[0] < a[1]:
                return False, 'machine overlap'
    return True, None


def _from_start_mach(start, mach):
    return [(i, mach[i], start[i]) for i in range(len(start))]


def _topo(inst, key):
    n = inst['n']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    ready = [i for i in range(n) if indeg[i] == 0]
    out = []
    while ready:
        ready.sort(key=key)
        i = ready.pop(0)
        out.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
    return out


def _list_schedule(inst, h, order):
    """Earliest-start serial schedule generation for a fixed job order."""
    n, m, p = inst['n'], inst['m'], inst['p']
    fin = [0] * n
    start = [None] * n
    mach = [None] * n
    avail = [0] * m
    for i in order:
        es = max([fin[j] for j in inst['pred'][i]] or [0])
        best = None
        for k in inst['elig'][i]:
            s = max(es, avail[k])
            if s + p[i] <= h:
                cand = (s, k)
                if best is None or cand < best:
                    best = cand
        if best is None:
            return None
        s, k = best
        start[i] = s
        mach[i] = k
        fin[i] = s + p[i]
        avail[k] = s + p[i]
    return start, mach


def greedy_schedule(inst, h, tries=200, seed=0):
    """Multi-start decrease-and-conquer list scheduling.

    Lanes are deterministic priority rules; the remaining lanes are a
    deterministic random topological order (seeded).  A lane is a complete
    schedule construction; lanes are independent, i.e. embarrassingly
    parallel.  The first lane whose schedule passes verify_schedule wins.
    """
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    keys = [
        lambda i: (-q[i], -p[i], i),
        lambda i: (-p[i], -q[i], i),
        lambda i: (h - q[i] - p[i], -q[i], i),
        lambda i: (est[i], -q[i], i),
        lambda i: (i,),
    ]
    for key in keys:
        order = _topo(inst, key)
        sm = _list_schedule(inst, h, order)
        if sm is not None:
            ok, _ = verify_schedule(inst, h, _from_start_mach(*sm))
            if ok:
                return _from_start_mach(*sm), 'greedy-det'
    rng = random.Random(seed)
    for t in range(tries):
        noise = {i: rng.random() for i in range(n)}
        key = lambda i: (-q[i] + 3.0 * (noise[i] - 0.5), -p[i], i)
        order = _topo(inst, key)
        sm = _list_schedule(inst, h, order)
        if sm is not None:
            ok, _ = verify_schedule(inst, h, _from_start_mach(*sm))
            if ok:
                return _from_start_mach(*sm), 'greedy-rand%d' % t
    return None, None


def dec_schedule(inst, h, nodecap=200000):
    """Complete decrease-and-conquer lane (v13 DEC, ladder_front).

    DEC recursively schedules one ready job, removes it from the remaining
    set, and uses a packing frontier for the capacity layer.  It returns a
    schedule witness or None.  This lane is *complete* when nodecap is not
    hit; it is used only for YES (it has no NO certificate).
    """
    inst = dict(inst)
    n, m = inst['n'], inst['m']
    inst.setdefault('full', (1 << n) - 1)
    inst.setdefault('pmask', [sum(1 << j for j in inst['pred'][i])
                              for i in range(n)])
    inst.setdefault('elig', [list(range(m)) for _ in range(n)])
    try:
        (ok, sched), st = dec_decide(inst, h, mode='ladder_front',
                                     nodecap=nodecap)
    except Exception:
        return None, {'nodes': 0, 'error': True}
    if not ok or sched is None:
        return None, st
    sched = [(int(i), int(k), int(t)) for (i, k, t) in sched]
    ok2, _ = verify_schedule(inst, h, sched)
    if not ok2:
        return None, st
    return sched, st


# --------------------------------------------------------------------------
# instrumented dual engine
# --------------------------------------------------------------------------
def _jobs(E):
    return {i for (i, t) in E}


class ProofQNC(QNC):
    """v7.1 QNC with a proof log.

    The log is a tree of split decisions plus globally valid force events.
    It is deliberately independent of the mutable DFS `bounds`: leaves store
    the Farkas certificate and its essential scope E, and the checker replays
    the final global force set on the root, then walks the splits.
    """

    def __init__(self, inst, h, **kw):
        super().__init__(inst, h, **kw)
        self.pnodes = []
        self.forces = []          # (job, frozenset(times), cert)
        self.clause_cert = {}
        self._stack = []
        self.schedule_yes = None

    # -- logging helpers ---------------------------------------------------
    def _new_node(self, depth):
        node = dict(id=len(self.pnodes), parent=self._stack[-1]
                    if self._stack else None, depth=depth,
                    kind='open', split=None, children=[],
                    cert=None, E=None, clause=None, clause_cert=None,
                    sched=None, reason=None)
        self.pnodes.append(node)
        if node['parent'] is not None:
            self.pnodes[node['parent']]['children'].append(node['id'])
        return node

    def _learn(self, F):
        before = {i: frozenset(S) for i, S in self.force.items()}
        got = super()._learn(F)
        cert, E = got
        if cert is not None and E:
            self.clause_cert[frozenset(E)] = cert
            js = _jobs(E)
            if len(js) == 1:
                i = next(iter(js))
                times = frozenset(t for (_, t) in E)
                if before.get(i) != self.force.get(i):
                    # normalize to (job, start) pairs; force is start-based
                    self.forces.append(
                        (i, frozenset((c[0], c[-1]) for c in E), cert))
        return got

    def _open_times(self, i, F):
        return [t for t in sorted(self.domain(i)) if (i, t) not in F]

    def _schedule_from_z(self, z):
        """Extract an integral schedule from an integral LP point."""
        n = self.n
        start = [None] * n
        mach = [None] * n
        for cc, key in enumerate(self.lp.cols):
            if z[cc] > 1.0 - 1e-7:
                i, t = key[0], key[-1]
                k = key[1] if self.elig else 0
                if start[i] is not None:
                    return None
                start[i], mach[i] = t, k
        if any(x is None for x in start):
            return None
        sched = _from_start_mach(start, mach)
        ok, _ = verify_schedule(self.inst, self.h, sched)
        return sched if ok else None

    # -- DFS with proof recording ------------------------------------------
    def _branch(self, bounds, depth, nodecap, max_rounds, topk):
        node = self._new_node(depth)
        self._stack.append(node['id'])
        try:
            bounds, _ = self._apply_force(bounds)
            i0 = self._empty_job(bounds) if self.use_empty else None
            if i0 is not None:
                self.empty_prunes += 1
                node['kind'] = 'empty'
                node['reason'] = 'empty job %d' % i0
                return False, 'empty'
            F = self._forbids(bounds)
            for E in self.clauses:
                if E <= F:
                    self.prunes += 1
                    node['kind'] = 'clause'
                    node['clause'] = frozenset(E)
                    node['clause_cert'] = self.clause_cert.get(frozenset(E))
                    node['reason'] = 'clause'
                    return False, 'clause'
            self.nodes += 1
            if self.nodes > nodecap:
                raise Budget
            res, z = self._solve(bounds, max_rounds, topk)
            if res.status == 2:
                cert, E = self._learn(F)
                node['kind'] = 'no'
                node['cert'] = cert
                node['E'] = frozenset(E) if E is not None else None
                node['reason'] = 'infeasible'
                return False, 'no'
            if z is None:
                node['reason'] = 'roundcap'
                return None, 'roundcap'

            frac = []
            for cc, key in enumerate(self.lp.cols):
                if 1e-7 < z[cc] < 1 - 1e-7:
                    frac.append((abs(z[cc] - 0.5), cc, key[0], key[-1]))
            if not frac:
                sched = self._schedule_from_z(z)
                if sched is not None:
                    node['kind'] = 'yes'
                    node['sched'] = sched
                    self.schedule_yes = sched
                    return True, 'yes'
                node['reason'] = 'integral but no schedule'
                return None, 'roundcap'

            # weighted median over OPEN starts; guarantees progress
            frac.sort()
            _, cc, i, t = frac[0]
            open_times = self._open_times(i, F)
            if len(open_times) < 2:
                node['reason'] = 'degenerate split'
                return None, 'roundcap'
            s = 0.0
            mid = open_times[0]
            for tt in open_times:
                if self.elig:
                    s += sum(z[self.lp.idx[(i, k, tt)]]
                             for k in self.lp.base.elig[i]
                             if (i, k, tt) in self.lp.idx)
                else:
                    s += z[self.lp.idx[(i, tt)]]
                if s >= 0.5:
                    mid = tt
                    break
            if mid <= open_times[0]:
                mid = open_times[0]
            if mid >= open_times[-1]:
                mid = open_times[-2]
            node['kind'] = 'split'
            node['split'] = (i, mid)
            lo = list(bounds)
            hi2 = list(bounds)
            for tt in self.domain(i):
                if self.elig:
                    for k in self.lp.base.elig[i]:
                        if (i, k, tt) in self.lp.idx:
                            c2 = self.lp.idx[(i, k, tt)]
                            if tt > mid:
                                lo[c2] = (0, 0)
                            else:
                                hi2[c2] = (0, 0)
                else:
                    c2 = self.lp.idx[(i, tt)]
                    if tt > mid:
                        lo[c2] = (0, 0)
                    else:
                        hi2[c2] = (0, 0)
            a, why = self._branch(lo, depth + 1, nodecap, max_rounds, topk)
            if a is not False:
                return a, why
            return self._branch(hi2, depth + 1, nodecap, max_rounds, topk)
        except Budget:
            node['kind'] = 'open'
            node['reason'] = 'budget'
            raise
        finally:
            self._stack.pop()


# --------------------------------------------------------------------------
# proof checker
# --------------------------------------------------------------------------
def _dom_size(dom):
    return sum(len(S) for S in dom.values())


def _col_forbidden(c, dom):
    """A display column (i,t) or (i,k,t) is forbidden iff t is absent."""
    return c[-1] not in dom[c[0]]


def check_proof(inst, h, bundle, verbose=False):
    """Check a ProofQNC proof tree.

    bundle = {nodes, forces, root}.  Returns (verdict, msg, stats).
    verdict is 'NO', 'YES', or 'UNKNOWN'.
    """
    nodes = {nd['id']: nd for nd in bundle['nodes']}
    full, est, q = make_domains(inst, h)
    allowed = {i: set(S) for i, S in full.items()}
    force_stats = 0

    # 1. global force chain
    for (i, times, cert) in bundle.get('forces', []):
        times = frozenset(times)
        if not times:
            continue
        if cert is None:
            return 'UNKNOWN', 'force without certificate', {}
        if not verify(inst, h, cert, forbid=times):
            return 'UNKNOWN', 'force cert replay failed', {}
        allowed[i] &= {t for (ii, t) in times if ii == i}
        force_stats += 1
        if not allowed[i]:
            return 'NO', 'force chain empty', {'forces': force_stats}

    # 2. tree walk
    seen_yes = [False]
    open_nodes = []
    stats = dict(nodes=0, splits=0, leaves_no=0, leaves_empty=0,
                 leaves_clause=0, leaves_yes=0, open=0, forces=force_stats,
                 max_depth=0, checked_force=force_stats)
    fullset = {(i, t): None for i in full for t in full[i]}

    def forbidden(dom):
        return {(i, t) for i in full for t in full[i] if t not in dom[i]}

    def walk(nid, dom, depth):
        nd = nodes.get(nid)
        if nd is None:
            return 'UNKNOWN', 'missing node'
        stats['nodes'] += 1
        stats['max_depth'] = max(stats['max_depth'], depth)
        kind = nd['kind']
        if kind == 'yes':
            ok, why = verify_schedule(inst, h, nd.get('sched'))
            if not ok:
                return 'UNKNOWN', 'YES schedule invalid: %s' % why
            seen_yes[0] = True
            stats['leaves_yes'] += 1
            return 'YES', None
        if kind == 'open':
            open_nodes.append(nid)
            stats['open'] += 1
            return 'UNKNOWN', None
        if kind == 'empty':
            if any(not dom[i] for i in range(inst['n'])):
                stats['leaves_empty'] += 1
                return 'NO', None
            return 'UNKNOWN', 'empty leaf without empty domain'
        if kind == 'clause':
            E = nd.get('clause')
            if not E:
                return 'UNKNOWN', 'clause leaf without clause'
            if not all(_col_forbidden(c, dom) for c in E):
                return 'UNKNOWN', 'clause not falsified by node'
            cert = nd.get('clause_cert')
            if cert is None:
                return 'UNKNOWN', 'clause certificate missing'
            if not verify(inst, h, cert, forbid=E):
                return 'UNKNOWN', 'clause certificate replay failed'
            stats['leaves_clause'] += 1
            return 'NO', None
        if kind == 'no':
            E = nd.get('E')
            cert = nd.get('cert')
            if cert is None or E is None:
                return 'UNKNOWN', 'NO leaf without certificate'
            if not all(_col_forbidden(c, dom) for c in E):
                return 'UNKNOWN', 'essential scope not forbidden at node'
            if not verify(inst, h, cert, forbid=E):
                return 'UNKNOWN', 'Farkas certificate replay failed'
            stats['leaves_no'] += 1
            return 'NO', None
        if kind == 'split':
            if not nd.get('split') or len(nd.get('children', [])) != 2:
                return 'UNKNOWN', 'malformed split'
            i, mid = nd['split']
            left, right = nd['children']
            ldom = {j: set(S) for j, S in dom.items()}
            rdom = {j: set(S) for j, S in dom.items()}
            ldom[i] = {t for t in ldom[i] if t <= mid}
            rdom[i] = {t for t in rdom[i] if t > mid}
            # partition of the current domain
            if ldom[i] | rdom[i] != dom[i] or ldom[i] & rdom[i]:
                return 'UNKNOWN', 'split does not partition'
            if not ldom[i] and not rdom[i]:
                return 'UNKNOWN', 'split on empty job'
            # A later global force may have made one side empty.  That is
            # sound: the other side still covers the canonical parent domain,
            # and the empty side is a NO leaf.  Strict decrease is only
            # needed in the *search* domain, which the force chain records.
            stats['splits'] += 1
            vl, ml = walk(left, ldom, depth + 1)
            if vl == 'YES':
                return 'YES', None
            if vl == 'UNKNOWN':
                return 'UNKNOWN', ml
            vr, mr = walk(right, rdom, depth + 1)
            if vr == 'YES':
                return 'YES', None
            if vr == 'UNKNOWN':
                return 'UNKNOWN', mr
            return 'NO', None
        return 'UNKNOWN', 'unknown node kind %r' % kind

    if seen_yes[0]:
        return 'YES', None, stats
    if not nodes:
        return 'UNKNOWN', 'empty proof', stats
    v, why = walk(bundle['root'], allowed, 0)
    if v == 'NO':
        return 'NO', None, stats
    if v == 'YES':
        return 'YES', None, stats
    return 'UNKNOWN', why, stats


# --------------------------------------------------------------------------
# two-sided decision procedure
# --------------------------------------------------------------------------
class TCA:
    def __init__(self, inst, h, primal_tries=200, dec_cap=200000,
                 dec_hint_cap=20000,
                 dual_budget=100000, dual_nodecap=5000,
                 dual_first_budget=3, use_greedy=True, use_dec=True):
        self.inst = inst
        self.h = h
        self.primal_tries = primal_tries
        self.dec_cap = dec_cap
        self.dec_hint_cap = dec_hint_cap
        self.dual_budget = dual_budget
        self.dual_nodecap = dual_nodecap
        self.dual_first_budget = dual_first_budget
        self.use_greedy = use_greedy
        self.use_dec = use_dec
        self.events = []

    def _yes(self, sched, engine, stats=None):
        ok, why = verify_schedule(self.inst, self.h, sched)
        if not ok:
            raise RuntimeError('primal emitted invalid schedule: %s' % why)
        stats = stats or {}
        return True, dict(verdict=True, engine=engine, schedule=sched,
                          sched_stats=stats,
                          lp=stats.get('lp_solves', 0),
                          nodes=stats.get('nodes', 0))

    def decide(self):
        t0 = time.time()
        # Lane 1: cheap primal decrease-and-conquer (multi-start list).
        if self.use_greedy:
            sched, why = greedy_schedule(self.inst, self.h,
                                         tries=self.primal_tries)
            if sched is not None:
                v, st = self._yes(sched, 'greedy')
                st['t'] = time.time() - t0
                st['why'] = why
                return v, st

        # Lane 2: dual with a short budget.  On NO this closes almost all
        # instances at the root (1 LP); on YES it is stopped early.
        q = ProofQNC(self.inst, self.h)
        v, st = q.decide(budget=self.dual_first_budget,
                         nodecap=self.dual_nodecap)
        if v is False:
            verdict, why, pst = check_proof(self.inst, self.h,
                                            dict(nodes=q.pnodes,
                                                 forces=q.forces,
                                                 root=0))
            if verdict != 'NO':
                raise RuntimeError('dual proof failed: %s' % why)
            return False, dict(verdict=False, engine='dual-qnc',
                              proof=dict(nodes=q.pnodes, forces=q.forces,
                                         root=0),
                              proof_stats=pst, lp=st['lp_solves'],
                              nodes=st['nodes'], t=time.time() - t0,
                              why='dual')
        if v is True:
            return self._yes(q.schedule_yes, 'dual-qnc', st)

        # Lane 3: a cheap primal hint.  DEC is exact: if it returns NO
        # without hitting its cap, prioritize the full dual check; if it
        # returns YES, the schedule witness decides.  The hint never decides
        # the answer by itself.
        dec_stats = {}
        hint_no = False
        if self.use_dec:
            sched, dec_stats = dec_schedule(self.inst, self.h,
                                            nodecap=self.dec_hint_cap)
            if sched is not None:
                v, st2 = self._yes(sched, 'dec', dec_stats)
                st2['t'] = time.time() - t0
                st2['dual_lp'] = st['lp_solves']
                return v, st2
            hint_no = not dec_stats.get('timeout')

        # Lane 4: dual with full budget, early when the primal hint says NO.
        if hint_no:
            q = ProofQNC(self.inst, self.h)
            v, st = q.decide(budget=self.dual_budget,
                             nodecap=self.dual_nodecap)
            if v is False:
                verdict, why, pst = check_proof(self.inst, self.h,
                                                dict(nodes=q.pnodes,
                                                     forces=q.forces,
                                                     root=0))
                if verdict != 'NO':
                    raise RuntimeError('dual proof failed: %s' % why)
                return False, dict(verdict=False, engine='dual-qnc',
                                  proof=dict(nodes=q.pnodes,
                                             forces=q.forces, root=0),
                                  proof_stats=pst, lp=st['lp_solves'],
                                  nodes=st['nodes'], t=time.time() - t0,
                                  why='dual')
            if v is True:
                return self._yes(q.schedule_yes, 'dual-qnc', st)

        # Lane 5: complete primal decrease-and-conquer for YES.
        if self.use_dec:
            sched, dec_stats = dec_schedule(self.inst, self.h,
                                            nodecap=self.dec_cap)
            if sched is not None:
                v, st2 = self._yes(sched, 'dec', dec_stats)
                st2['t'] = time.time() - t0
                st2['dual_lp'] = st['lp_solves']
                return v, st2

        # Lane 6: dual with full budget.
        q = ProofQNC(self.inst, self.h)
        v, st = q.decide(budget=self.dual_budget,
                         nodecap=self.dual_nodecap)
        if v is False:
            verdict, why, pst = check_proof(self.inst, self.h,
                                            dict(nodes=q.pnodes,
                                                 forces=q.forces,
                                                 root=0))
            if verdict != 'NO':
                raise RuntimeError('dual proof failed: %s' % why)
            return False, dict(verdict=False, engine='dual-qnc',
                              proof=dict(nodes=q.pnodes, forces=q.forces,
                                         root=0),
                              proof_stats=pst, lp=st['lp_solves'],
                              nodes=st['nodes'], t=time.time() - t0,
                              why='dual')
        if v is True:
            return self._yes(q.schedule_yes, 'dual-qnc', st)
        return None, dict(verdict=None, engine='tca',
                          proof=dict(nodes=q.pnodes, forces=q.forces,
                                     root=0),
                          lp=st['lp_solves'], nodes=st['nodes'],
                          t=time.time() - t0, why='unknown')


# --------------------------------------------------------------------------
# certificate serialization helpers (for the experiment log)
# --------------------------------------------------------------------------
def check_certificate(inst, h, cert):
    if cert['verdict'] is True or cert.get('verdict') == 'YES':
        return verify_schedule(inst, h, cert['schedule'])[0]
    if cert['verdict'] is False or cert.get('verdict') == 'NO':
        v, why, _ = check_proof(inst, h, cert['proof'])
        return v == 'NO'
    return False
