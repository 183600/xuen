"""v9.0 SCALE-ID: scalable preprocessing, component aggregation, iterative deepening.

SCALE-ID keeps the v8.0 BRC-ALC core (QSP downward search, verified
Farkas certificates, fault-tolerant recovery, randomized SGS upward
search) and adds a preprocessing/decomposition layer:

  * window closure: est/lst longest-path domains; empty domain => NO;
  * energy filter: for any machine subset M and time interval [a,b), the
    jobs eligible only on M must fit in |M|(b-a); overload => NO;
  * forced starts: est_i = lst_i are installed as certified force;
  * component decomposition: jobs connected by precedence or a shared
    eligible machine are independent of the rest;
  * isomorphism: isomorphic components are solved once and the schedule
    is mapped to every copy (with an explicit mapping check);
  * machine symmetry: SGS tries one representative per (start, busy,
    eligibility-profile) class;
  * iterative deepening: a bounded LDS ladder around the LP mean order,
    used after the small random constructor stalls.

The NO core is unchanged.  The upward constructor is still only trusted
after check_schedule.  Every preprocessing verdict has a replayable
certificate.
"""
import sys
import math
import heapq
import random
import numpy as np

sys.path[:0] = ['exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from rdf import RDF, check_schedule, _heads_latest, _insert, _earliest
from po import make_inst, heads_tails


# --------------------------------------------------------------- windows
def windows(inst, h):
    n, p = inst['n'], inst['p']
    est, q = heads_tails(inst, 0, [0] * n)
    lst = [h - q[i] - p[i] for i in range(n)]
    return est, lst, q


def verify_prep(inst, h, cert):
    """Independent replay of a window or energy NO certificate."""
    if cert is None:
        return False
    est, lst, _ = windows(inst, h)
    n, p = inst['n'], inst['p']
    kind = cert.get('kind')
    if kind == 'window':
        i = cert['job']
        return (0 <= i < n and est[i] == cert['est']
                and lst[i] == cert['lst'] and est[i] > lst[i])
    if kind == 'energy':
        M = set(cert['M'])
        a, b = cert['a'], cert['b']
        if not M or a >= b:
            return False
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if js != list(cert['jobs']):
            return False
        demand = 0
        for i in js:
            demand += max(0, p[i] - max(0, a - est[i])
                          - max(0, lst[i] + p[i] - b))
        return demand == cert['demand'] and demand > len(M) * (b - a)
    return False


def _machine_subsets(inst, max_subsets=64):
    m = inst['m']
    n = inst['n']
    out = [frozenset(range(m))]
    if m <= 6:
        for mask in range(1, 1 << m):
            out.append(frozenset(k for k in range(m) if mask & (1 << k)))
    else:
        for k in range(m):
            out.append(frozenset({k}))
        for i in range(n):
            out.append(frozenset(inst['elig'][i]))
    seen, uniq = set(), []
    for M in out:
        if M and M not in seen:
            seen.add(M)
            uniq.append(M)
    return uniq[:max_subsets]


def energy_cert(inst, h, max_subsets=64, max_intervals=20000):
    """Return a sound energy-overload certificate, or None.

    The scan is a filter, not a decision procedure: stopping early only
    loses a cheap NO, never changes correctness.
    """
    n, p, m = inst['n'], inst['p'], inst['m']
    est, lst, _ = windows(inst, h)
    for i in range(n):
        if est[i] > lst[i]:
            return dict(kind='window', job=i, est=est[i], lst=lst[i])
    pts = sorted(set(est + [lst[i] + p[i] for i in range(n)]))
    pairs = [(0, h)] if 0 < h else []
    for ai, a in enumerate(pts):
        for b in pts[ai + 1:]:
            if (a, b) != (0, h):
                pairs.append((a, b))
            if len(pairs) >= max_intervals:
                break
        if len(pairs) >= max_intervals:
            break
    for M in _machine_subsets(inst, max_subsets):
        js = [i for i in range(n) if set(inst['elig'][i]) <= M]
        if not js:
            continue
        cap = len(M)
        for a, b in pairs:
            if b <= a:
                continue
            demand = 0
            for i in js:
                demand += max(0, p[i] - max(0, a - est[i])
                              - max(0, lst[i] + p[i] - b))
            if demand > cap * (b - a):
                return dict(kind='energy', M=sorted(M), a=a, b=b,
                            jobs=js, demand=demand, cap=cap * (b - a))
    return None


# ------------------------------------------------------------ components
def _union_find(n):
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra
    return find, union


def component_jobs(inst):
    n = inst['n']
    find, union = _union_find(n)
    for i in range(n):
        for j in inst['succ'][i]:
            union(i, j)
    owner = {}
    for i in range(n):
        for k in inst['elig'][i]:
            if k in owner:
                union(i, owner[k])
            else:
                owner[k] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values()]


def subinstance(inst, jobs):
    jobs = sorted(jobs)
    jmap = {j: i for i, j in enumerate(jobs)}
    machines = sorted(set(k for j in jobs for k in inst['elig'][j]))
    mmap = {k: i for i, k in enumerate(machines)}
    p = [inst['p'][j] for j in jobs]
    pred = [[jmap[x] for x in inst['pred'][j]] for j in jobs]
    elig = [[mmap[k] for k in inst['elig'][j]] for j in jobs]
    return make_inst(p, len(machines), pred, elig), jobs, machines


def canonical_label(inst):
    """A sound-but-incomplete isomorphism label.

    If two components get the same label, isomorphic_map() still verifies
    the explicit job/machine mapping before any schedule is reused.
    """
    n, m = inst['n'], inst['m']
    prof = [frozenset(i for i in range(n) if k in inst['elig'][i])
            for k in range(m)]

    def mkey(k):
        ps = sorted(inst['p'][i] for i in prof[k])
        sizes = sorted(len(inst['elig'][i]) for i in prof[k])
        return (len(prof[k]), tuple(ps), tuple(sizes), k)

    morder = sorted(range(m), key=mkey)
    mmap = {k: i for i, k in enumerate(morder)}
    indeg = [len(inst['pred'][i]) for i in range(n)]
    succ = inst['succ']

    def jkey(i):
        return (inst['p'][i],
                tuple(sorted(mmap[k] for k in inst['elig'][i])), i)

    heap = [(jkey(i), i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(heap)
    jorder = []
    while heap:
        _, i = heapq.heappop(heap)
        jorder.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(heap, (jkey(j), j))
    if len(jorder) < n:
        seen = set(jorder)
        jorder += [i for i in range(n) if i not in seen]
    jmap = {j: i for i, j in enumerate(jorder)}
    ps = tuple(inst['p'][j] for j in jorder)
    edges = tuple(sorted((jmap[i], jmap[j]) for i in range(n)
                         for j in succ[i]))
    elig = tuple(tuple(sorted(mmap[k] for k in inst['elig'][j]))
                 for j in jorder)
    return (n, m, ps, edges, elig), jorder, morder


def isomorphic_map(rep, mem):
    """Return (job_map, machine_map) member->representative, or None."""
    if rep['key'] != mem['key']:
        return None
    jmap = {mem['jorder'][pos]: rep['jorder'][pos]
            for pos in range(rep['sub']['n'])}
    mmap = {mem['morder'][pos]: rep['morder'][pos]
            for pos in range(rep['sub']['m'])}
    rs, ms = rep['sub'], mem['sub']
    for jm, jr in jmap.items():
        if rs['p'][jr] != ms['p'][jm]:
            return None
        if set(jmap[x] for x in ms['pred'][jm]) != set(rs['pred'][jr]):
            return None
        if set(mmap[k] for k in ms['elig'][jm]) != set(rs['elig'][jr]):
            return None
    return jmap, mmap


# ------------------------------------------------------------------ SCALE
class SCALE(RDF):
    def __init__(self, inst, h, decompose=True, prep_energy=True,
                 prep_force=True, sym=True, id_lds=True, iso_on=True,
                 id_discs=(0, 1, 2), id_caps=(200, 400, 800),
                 id_node_budget=5000, energy_max_subsets=64,
                 energy_max_intervals=20000, deep_on=True,
                 small_budget2=20, small_nodes2=200, **kw):
        super().__init__(inst, h, **kw)
        self.decompose = decompose
        self.prep_energy = prep_energy
        self.prep_force = prep_force
        self.sym = sym
        self.id_lds = id_lds
        self.iso_on = iso_on
        self.id_discs = tuple(id_discs)
        self.id_caps = tuple(id_caps)
        self.id_node_budget = id_node_budget
        self.energy_max_subsets = energy_max_subsets
        self.energy_max_intervals = energy_max_intervals
        self.deep_on = deep_on
        self.small_budget2 = small_budget2
        self.small_nodes2 = small_nodes2
        self.deep_calls = 0
        self.deep_lp = 0
        self.prep_cert = None
        self.prep_no = False
        self.component_no = None
        self.components = []
        self.iso_classes = 0
        self.iso_saved = 0
        self.window_forces = {}
        self.id_calls = 0
        self.id_nodes = 0
        self._in_component = False

    # ------------------------------------------------------- preprocessing
    def _preprocess(self):
        est, lst, _ = windows(self.inst, self.h)
        for i in range(self.inst['n']):
            if est[i] > lst[i]:
                self.prep_cert = dict(kind='window', job=i,
                                      est=est[i], lst=lst[i])
                self.prep_no = True
                return False
        if self.prep_force:
            self.window_forces = {i: est[i] for i in range(self.inst['n'])
                                  if est[i] == lst[i]}
        if not self.decompose:
            if self.prep_energy:
                cert = energy_cert(self.inst, self.h,
                                   self.energy_max_subsets,
                                   self.energy_max_intervals)
                if cert is not None:
                    self.prep_cert = cert
                    self.prep_no = True
                    return False
            return True
        groups = component_jobs(self.inst)
        if len(groups) <= 1:
            if self.prep_energy:
                cert = energy_cert(self.inst, self.h,
                                   self.energy_max_subsets,
                                   self.energy_max_intervals)
                if cert is not None:
                    self.prep_cert = cert
                    self.prep_no = True
                    return False
            return True
        comps = []
        for jobs in groups:
            sub, full_jobs, machines = subinstance(self.inst, jobs)
            key, jorder, morder = canonical_label(sub)
            comps.append(dict(sub=sub, jobs=full_jobs,
                              machines=machines, key=key,
                              jorder=jorder, morder=morder))
        self.components = comps
        return True

    def _install_forced(self):
        for i, t in self.window_forces.items():
            self.force[i] = frozenset({t})

    def _decide_core(self, budget, nodecap, max_rounds, topk):
        if not self.yes_scan:
            self.budget = budget
            self.nodecap = nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Exception:
                v, why = None, 'budget'
            return v, why
        self.budget = min(budget, self.small_budget)
        self.nodecap = min(nodecap, self.small_nodes)
        try:
            v, why = self._search([(0, 1)] * self.lp.base.N, 0)
        except Exception:
            v, why = None, 'budget-small'
        if v is None and self.yes_scan and self.root_z is None:
            res = self.lp.solve([(0, 1)] * self.lp.base.N)
            self.lp_solves += 1
            if res.status == 2:
                v, why = False, 'root-core'
            elif res.status == 0:
                self.root_z = np.array(res.x, copy=True)
        if v is None and self.yes_scan and self.root_z is not None:
            if self._yes_construct(self.root_z, self.yes_trials1,
                                   self.yes_nodecap1):
                v, why = True, 'yes-lp-small'
        if v is None and self.yes_scan and self.deep_on:
            before = self.lp_solves
            self.budget = max(self.lp_solves + 1, self.small_budget2)
            self.nodecap = self.nodes + self.small_nodes2
            try:
                v2, why2 = self._search([(0, 1)] * self.lp.base.N, 0)
            except Exception:
                v2, why2 = None, 'budget-deep'
            self.deep_calls += 1
            self.deep_lp += self.lp_solves - before
            if v2 is not None:
                v, why = v2, ('yes-deep' if v2 is True else 'no-deep')
        if v is None and self.yes_scan and self.id_lds \
                and self.root_z is not None:
            if self._id_construct(self.root_z):
                v, why = True, 'yes-id'
        if v is None and self.yes_scan and self.root_z is not None \
                and self.yes_nodes < self.yes_node_budget:
            if self._yes_construct(self.root_z, self.yes_trials2,
                                   self.yes_nodecap2):
                v, why = True, 'yes-lp'
        if v is None:
            self.budget = budget
            self.nodecap = self.nodes + nodecap
            try:
                v, why = self._search([(0, 1)] * self.lp.base.N, 0)
            except Exception:
                v, why = None, 'budget'
        return v, why

    # ---------------------------------------------------------- components
    def _decide_components(self, budget, nodecap, max_rounds, topk):
        classes = []
        for comp in self.components:
            placed = False
            if self.iso_on:
                for cl in classes:
                    mp = isomorphic_map(cl['rep'], comp)
                    if mp is not None:
                        cl['members'].append((comp, mp))
                        placed = True
                        break
            if not placed:
                classes.append(dict(rep=comp, members=[(comp, None)]))
        self.iso_classes = len(classes)
        self.iso_saved = len(self.components) - len(classes)
        starts = [None] * self.inst['n']
        machs = [None] * self.inst['n']
        yes_used = 0
        for cl in classes:
            rep = cl['rep']
            left = budget - self.lp_solves
            if left <= 0:
                return None, 'component-budget'
            sub = SCALE(rep['sub'], self.h, decompose=self.decompose,
                        prep_energy=self.prep_energy,
                        prep_force=self.prep_force, sym=self.sym,
                        id_lds=self.id_lds, iso_on=self.iso_on,
                        deep_on=self.deep_on,
                        small_budget2=self.small_budget2,
                        small_nodes2=self.small_nodes2,
                        id_discs=self.id_discs,
                        id_caps=self.id_caps,
                        id_node_budget=max(0, self.id_node_budget - 0),
                        energy_max_subsets=self.energy_max_subsets,
                        energy_max_intervals=self.energy_max_intervals,
                        yes_scan=self.yes_scan,
                        yes_trials1=self.yes_trials1,
                        yes_nodecap1=self.yes_nodecap1,
                        yes_trials2=self.yes_trials2,
                        yes_nodecap2=self.yes_nodecap2,
                        small_budget=self.small_budget,
                        small_nodes=self.small_nodes,
                        yes_node_budget=max(0, self.yes_node_budget
                                            - yes_used))
            sub._in_component = True
            v, st = sub.decide(budget=left, nodecap=nodecap,
                               max_rounds=max_rounds, topk=topk)
            self.lp_solves += sub.lp_solves
            self.nodes += sub.nodes
            self.yes_nodes += sub.yes_nodes
            self.yes_trials_used += sub.yes_trials_used
            self.yes_calls += sub.yes_calls
            self.id_nodes += sub.id_nodes
            self.id_calls += sub.id_calls
            yes_used += sub.yes_nodes
            if v is False:
                self.component_no = dict(rep=rep, sub=sub)
                return False, 'component-no'
            if v is None:
                return None, 'component-unknown'
            rep_starts, rep_machs = sub.schedule, sub.machine
            if rep_starts is None:
                return None, 'component-no-schedule'
            for mem, mp in cl['members']:
                if mem is rep:
                    jm2r = {i: i for i in range(rep['sub']['n'])}
                    mm2r = {k: k for k in range(rep['sub']['m'])}
                else:
                    jm2r, mm2r = mp
                jr2m = {jr: jm for jm, jr in jm2r.items()}
                mr2m = {mr: mm for mm, mr in mm2r.items()}
                for jm, jr in jm2r.items():
                    full_j = mem['jobs'][jm]
                    starts[full_j] = rep_starts[jr]
                for jm, jr in jm2r.items():
                    full_j = mem['jobs'][jm]
                    k_rep = rep_machs[jr]
                    k_mem = mr2m[k_rep]
                    machs[full_j] = mem['machines'][k_mem]
        if not self.yes_scan:
            return None, 'component-yes-pure-no'
        if check_schedule(self.inst, self.h, starts, machs):
            self.schedule, self.machine = starts, machs
            self.yes_ok = True
            return True, 'component-yes'
        return None, 'component-replay'

    # ------------------------------------------------------------ decide
    def decide(self, budget=100000, nodecap=5000, max_rounds=60, topk=100):
        if not self.decompose or self._in_component:
            self._install_forced()
            v, why = self._decide_core(budget, nodecap, max_rounds, topk)
            return v, self._stats(why)
        ok = self._preprocess()
        if not ok:
            return False, self._stats('prep-no')
        if self.components:
            v, why = self._decide_components(budget, nodecap,
                                             max_rounds, topk)
            return v, self._stats(why)
        self._install_forced()
        v, why = self._decide_core(budget, nodecap, max_rounds, topk)
        return v, self._stats(why)

    # ------------------------------------------------------- symmetry SGS
    def _sgs_dfs(self, rank, nodecap, seed=0, sym=None):
        sym = self.sym if sym is None else sym
        rng = random.Random(seed)
        inst, h = self.inst, self.h
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q, latest = _heads_latest(inst, h)
        starts = [None] * n
        machs = [None] * n
        busy = [[] for _ in range(m)]
        rem = [len(inst['pred'][i]) for i in range(n)]
        predfin = [0] * n
        done = [False] * n
        nodes = [0]
        prof = [frozenset(j for j in range(n) if k in inst['elig'][j])
                for k in range(m)]

        def rec():
            nodes[0] += 1
            if nodes[0] > nodecap:
                return False
            if all(done):
                return True
            av = [i for i in range(n) if not done[i] and rem[i] == 0]
            if not av:
                return False
            av.sort(key=lambda i: (rank[i], i))
            for i in av:
                base = max(est[i], predfin[i])
                opts = []
                seen = set()
                for k in inst['elig'][i]:
                    tt = _earliest(busy[k], base, p[i])
                    if tt > latest[i]:
                        continue
                    if sym:
                        key = (tt, prof[k], tuple(busy[k]))
                        if key in seen:
                            continue
                        seen.add(key)
                    opts.append((tt, k))
                opts.sort()
                for tt, k in opts:
                    starts[i] = tt
                    machs[i] = k
                    done[i] = True
                    _insert(busy, k, tt, tt + p[i])
                    old = [(j, predfin[j]) for j in inst['succ'][i]]
                    for j in inst['succ'][i]:
                        predfin[j] = max(predfin[j], tt + p[i])
                        rem[j] -= 1
                    if rec():
                        return True
                    for j, v in old:
                        predfin[j] = v
                        rem[j] += 1
                    busy[k].remove((tt, tt + p[i]))
                    done[i] = False
                    starts[i] = None
                    machs[i] = None
                    if nodes[0] > nodecap:
                        return False
            return False

        ok = rec()
        self.yes_nodes += nodes[0]
        if ok and check_schedule(inst, h, starts, machs):
            return starts, machs
        return None

    def _mean_rank(self, z):
        dist = self._lp_distribution(z)
        return {i: sum(t * v for t, v in d) for i, d in dist.items()}

    def _lds_sgs(self, rank, disc_cap, nodecap, sym=None):
        sym = self.sym if sym is None else sym
        inst, h = self.inst, self.h
        n, m, p = inst['n'], inst['m'], inst['p']
        est, q, latest = _heads_latest(inst, h)
        starts = [None] * n
        machs = [None] * n
        busy = [[] for _ in range(m)]
        rem = [len(inst['pred'][i]) for i in range(n)]
        predfin = [0] * n
        done = [False] * n
        nodes = [0]
        prof = [frozenset(j for j in range(n) if k in inst['elig'][j])
                for k in range(m)]

        def rec(disc):
            nodes[0] += 1
            if nodes[0] > nodecap:
                return False
            if all(done):
                return True
            av = [i for i in range(n) if not done[i] and rem[i] == 0]
            if not av:
                return False
            av.sort(key=lambda i: (rank[i], i))
            for ai, i in enumerate(av):
                nd = disc + ai
                if nd > disc_cap:
                    break
                base = max(est[i], predfin[i])
                opts = []
                seen = set()
                for k in inst['elig'][i]:
                    tt = _earliest(busy[k], base, p[i])
                    if tt > latest[i]:
                        continue
                    if sym:
                        key = (tt, prof[k], tuple(busy[k]))
                        if key in seen:
                            continue
                        seen.add(key)
                    opts.append((tt, k))
                opts.sort()
                for bi, (tt, k) in enumerate(opts):
                    nd2 = nd + bi
                    if nd2 > disc_cap:
                        break
                    starts[i] = tt
                    machs[i] = k
                    done[i] = True
                    _insert(busy, k, tt, tt + p[i])
                    old = [(j, predfin[j]) for j in inst['succ'][i]]
                    for j in inst['succ'][i]:
                        predfin[j] = max(predfin[j], tt + p[i])
                        rem[j] -= 1
                    if rec(nd2):
                        return True
                    for j, v in old:
                        predfin[j] = v
                        rem[j] += 1
                    busy[k].remove((tt, tt + p[i]))
                    done[i] = False
                    starts[i] = None
                    machs[i] = None
                    if nodes[0] > nodecap:
                        return False
            return False

        ok = rec(0)
        self.yes_nodes += nodes[0]
        if ok and check_schedule(inst, h, starts, machs):
            return starts, machs
        return None

    def _id_construct(self, z):
        if not self.id_lds or self.id_nodes >= self.id_node_budget:
            return False
        self.id_calls += 1
        rank = self._mean_rank(z)
        start = self.yes_nodes
        for d, cap in zip(self.id_discs, self.id_caps):
            rem = min(self.id_node_budget - self.id_nodes,
                      self.yes_node_budget - self.yes_nodes)
            if rem <= 0:
                return False
            self.yes_trials_used += 1
            got = self._lds_sgs(rank, d, min(rem, cap))
            self.id_nodes += self.yes_nodes - start
            start = self.yes_nodes
            if got is not None:
                self.schedule, self.machine = got
                self.yes_ok = True
                return True
        return False

    # ------------------------------------------------------------- audit
    def _stats(self, why):
        st = super()._stats(why)
        st.update(prep_no=self.prep_no,
                  prep_cert=self.prep_cert,
                  components=len(self.components),
                  iso_classes=self.iso_classes,
                  iso_saved=self.iso_saved,
                  window_forces={i: t for i, t in self.window_forces.items()},
                  sym=self.sym, decompose=self.decompose,
                  iso_on=self.iso_on,
                  id_calls=self.id_calls, id_nodes=self.id_nodes,
                  deep_calls=self.deep_calls, deep_lp=self.deep_lp,
                  component_no=(self.component_no is not None))
        return st

    def audit_scale(self):
        if self.prep_cert is not None:
            if not verify_prep(self.inst, self.h, self.prep_cert):
                return False
        if self.component_no is not None:
            sub = self.component_no['sub']
            if not sub.audit_scale():
                return False
            if not sub.proof_complete():
                return False
        if self.window_forces:
            est, lst, _ = windows(self.inst, self.h)
            for i, t in self.window_forces.items():
                if est[i] != t or lst[i] != t:
                    return False
        if not self.audit_rdf():
            return False
        if self.schedule is not None:
            if not check_schedule(self.inst, self.h, self.schedule,
                                  self.machine):
                return False
        return True

    def proof_complete(self):
        if self.prep_cert is not None:
            return verify_prep(self.inst, self.h, self.prep_cert)
        if self.component_no is not None:
            sub = self.component_no['sub']
            return sub.proof_complete() and sub.audit_scale()
        if self.window_forces:
            est, lst, _ = windows(self.inst, self.h)
            for i, t in self.window_forces.items():
                if est[i] != t or lst[i] != t:
                    return False
        return super().proof_complete()
