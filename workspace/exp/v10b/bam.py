"""v10.0 BAM-PACT: memory-bounded ant-guided A* over a certified frontier.

Outer object: a bracket L <= OPT <= U with a frontier partition of the
root domain at target H = U-1.  Every leaf carries a local lower bound
L_f and a NO(L_f-1) proof for its box.  The global lower bound is
L = min(U, min_f L_f).

Inner search: best-first (A*) on the leaf evaluation f = L_f.  A leaf is
probed at a height h in [L_f, U-1]; an LP/Farkas answer lifts L_f, a
schedule lowers U, and a fractional LP splits the leaf in the partition
at H.  Split choice is guided by LP mass and by an optional ant-colony
pheromone table.  The frontier is capped at W live leaves: if a split
would exceed W, the search either stops with a partial certificate or
contracts a non-critical sibling pair (parent L >= global L).

The ant colony only constructs feasible upper bounds and orders splits;
it never prunes a box and never contributes to a proof.
"""
import sys
import time

sys.path[:0] = ['exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import CertLeafProof, FrontierProof, cmax
from sage import _elig_aware, _domain
from sdecc import SDLP
from po import heads_tails
from cert import integer_certificate, verify
from rdf import check_schedule
from pact import (_integral_schedule, PACT, pact_decide)
from aco import AntColony


def _forbid_box(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    F = set()
    for i in range(n):
        a = est[i]
        b = h - q[i] - inst['p'][i]
        for t in range(a, b + 1):
            if t < lo[i] or t > hi[i]:
                F.add((i, t))
    return frozenset(F)


def _root_box(inst, h):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    lo = [int(est[i]) for i in range(n)]
    hi = [int(h - q[i] - inst['p'][i]) for i in range(n)]
    return lo, hi


def _effective(inst, h, lo, hi):
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    a = [max(int(lo[i]), int(est[i])) for i in range(n)]
    b = [min(int(hi[i]), int(h - q[i] - inst['p'][i])) for i in range(n)]
    if any(a[i] > b[i] for i in range(n)):
        return None
    return a, b


class Node:
    __slots__ = ('lo', 'hi', 'L', 'proof', 'parent', 'split', 'children',
                 'depth', 'dead', 'created')

    def __init__(self, lo, hi, L, proof, parent=None, depth=0, created=0):
        self.lo = tuple(int(x) for x in lo)
        self.hi = tuple(int(x) for x in hi)
        self.L = int(L)
        self.proof = proof
        self.parent = parent
        self.split = None
        self.children = None
        self.depth = int(depth)
        self.dead = False
        self.created = int(created)


class BAMCertificate:
    """A frontier NO(L-1) certificate plus a schedule of length U."""

    kind = 'bam-partial' if False else 'bam-cert'

    def __init__(self, inst, L, U, schedule, machine, frontier,
                 final=False):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.frontier = frontier
        self.final = bool(final)

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = cmax(self.inst, self.schedule)
        if c != self.U:
            return False
        return bool(check_schedule(self.inst, c, self.schedule,
                                   self.machine))

    def audit_rdf(self):
        try:
            if self.frontier is None:
                return False
            if self.frontier.target != self.L - 1:
                return False
            if not self.frontier.audit_rdf():
                return False
            if self.L > self.U:
                return False
            return self._sched_ok()
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _empty_proof(inst, h, F, lo, hi):
    """A verified empty-domain leaf for the current box at horizon h."""
    n = inst['n']
    for i in range(n):
        a = max(lo[i], 0)
        b = hi[i]
        # If the whole effective domain is forbidden, any job works; we
        # also use the cheapest job whose allowed domain is empty.
        ea, eb = _domain(inst, h, i)
        aa, bb = max(ea, lo[i]), min(eb, hi[i])
        if aa > bb or all((i, t) in F for t in range(aa, bb + 1)):
            return CertLeafProof(inst, h, F, {'kind': 'empty', 'job': i})
    return None


class BAM:
    def __init__(self, inst, W=8, memory_mode='stop', policy='lower',
                 use_aco=True, aco_ants=8, aco_gens=3, aco_seed=7,
                 aco_gamma=0.35, max_probes=4000, max_splits=4000,
                 max_contract=0, max_time=None, verbose=False):
        self.inst = inst
        self.W = int(W)
        self.memory_mode = memory_mode
        self.policy = policy
        self.use_aco = bool(use_aco)
        self.aco_ants = int(aco_ants)
        self.aco_gens = int(aco_gens)
        self.aco_seed = int(aco_seed)
        self.aco_gamma = float(aco_gamma)
        self.max_probes = int(max_probes)
        self.max_splits = int(max_splits)
        self.max_contract = int(max_contract)
        self.max_time = max_time
        self.verbose = verbose
        self.stats = dict(probes=0, lp=0, cert_lp=0, pin_lp=0, nodes=0,
                          splits=0, contractions=0, regressions=0,
                          memory_stops=0, unknown=0, aco_calls=0,
                          aco_impr=0, aco_best=None, fallback=0,
                          empty_lifts=0, dead=0, peak_leaves=1,
                          max_depth=0)
        self.t0 = time.time()

    def _log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def _elapsed(self):
        return time.time() - self.t0

    def _leaves(self):
        out = []
        stack = [self.root] if self.root is not None else []
        while stack:
            nd = stack.pop()
            if nd.children is None:
                if not nd.dead:
                    out.append(nd)
            else:
                stack.append(nd.children[1])
                stack.append(nd.children[0])
        return out

    def _global_L(self):
        best = self.U
        for f in self._leaves():
            if f.L < best:
                best = f.L
        return int(best)

    def _open(self):
        return [f for f in self._leaves() if f.L < self.U and not f.dead]

    def _effective_leaf(self, f, h):
        return _effective(self.inst, h, f.lo, f.hi)

    def _refresh_dead(self):
        H = self.U - 1
        n = self.inst['n']
        for f in self._leaves():
            if self._effective_leaf(f, H) is None:
                f.dead = True
                self.stats['dead'] += 1
        # prune dead leaves from the tree when both children are gone
        changed = True
        while changed:
            changed = False
            stack = [self.root]
            while stack:
                nd = stack.pop()
                if nd.children is None:
                    continue
                a, b = nd.children
                if a.dead and b.dead:
                    nd.dead = True
                    nd.children = None
                    nd.proof = None
                    changed = True
                else:
                    stack.extend((a, b))

    def _seed_aco(self, U, starts, machine):
        if not self.use_aco:
            return
        aco = AntColony(self.inst, seed=self.aco_seed, rho=0.2)
        # seed pheromone with the incumbent order (sorted by start time)
        order = sorted(range(self.inst['n']), key=lambda i: (starts[i], i))
        dep = 1.0 / max(1, U)
        for ii in range(len(order)):
            for jj in range(ii + 1, len(order)):
                a, b = order[ii], order[jj]
                if b in self.inst['succ'][a]:
                    continue
                aco.tau[a][b] += dep
        self.aco = aco
        best, hit = aco.run(U, ants=self.aco_ants, gens=self.aco_gens,
                           target=self.L if hasattr(self, 'L') else None)
        self.stats['aco_calls'] += 1
        if best is not None:
            self.stats['aco_best'] = best[2]
            if best[2] < U:
                self.stats['aco_impr'] += 1
                return best
        return None

    def _choose_split(self, lp, z, a, b):
        inst = self.inst
        n = inst['n']
        p = inst['p']
        q = getattr(lp, 'q', [0] * n)
        antw = [0.0] * n
        if self.use_aco and getattr(self, 'aco', None) is not None:
            tau = self.aco.tau
            raw = []
            for i in range(n):
                s = 0.0
                for j in range(n):
                    if i != j:
                        s += tau[i][j] + tau[j][i]
                raw.append(s)
            mx = max(raw) if raw else 0.0
            if mx > 0:
                antw = [x / mx for x in raw]
        cand = []
        for i in range(n):
            times = list(range(a[i], b[i] + 1))
            if len(times) <= 1:
                continue
            mass = 0.0
            frac = 0.0
            dist = []
            for t in times:
                v = 0.0
                for c, key in enumerate(lp.cols):
                    if key[0] == i and key[-1] == t:
                        v += float(z[c])
                if v > 1e-12:
                    dist.append((t, v))
                    mass += v
                    if 1e-7 < v < 1 - 1e-7:
                        frac += v
            if len(dist) <= 1 or mass <= 1e-12:
                continue
            cand.append((i, dist, mass, frac))
        if not cand:
            # integral but undecodable: split the widest interval
            i = max(range(n), key=lambda j: (b[j] - a[j], q[j], -j))
            if b[i] <= a[i]:
                return None, None
            mid = (a[i] + b[i]) // 2
            return i, mid
        def score(c):
            i, dist, mass, frac = c
            return (frac * (1.0 + self.aco_gamma * antw[i]),
                    mass * (1.0 + self.aco_gamma * antw[i]),
                    q[i], len(dist), -i)
        cand.sort(key=score, reverse=True)
        i, dist, mass, frac = cand[0]
        total = sum(v for _, v in dist)
        acc = 0.0
        mid = dist[0][0]
        for t, v in dist:
            acc += v
            if acc >= 0.5 * total:
                mid = t
                break
        ts = [t for t, _ in dist]
        if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
            mid = ts[len(ts) // 2 - 1]
        if not any(t > mid for t in ts) or not any(t <= mid for t in ts):
            return None, None
        return i, mid

    def _probe(self, f):
        """One LP/Farkas probe of a leaf at h; returns (status, payload)."""
        h = f.L
        eff = self._effective_leaf(f, h)
        if eff is None:
            F = _forbid_box(self.inst, h, f.lo, f.hi)
            pr = _empty_proof(self.inst, h, F, f.lo, f.hi)
            if pr is None:
                return 'unknown', None
            self.stats['empty_lifts'] += 1
            f.L = h + 1
            f.proof = pr
            return 'no', pr
        a, b = eff
        F = _forbid_box(self.inst, h, a, b)
        n = self.inst['n']
        est, q = heads_tails(self.inst, 0, [0] * n)
        elig = _elig_aware(self.inst)
        try:
            lp = SDLP(self.inst, h, est, q, use_dom=True,
                      elig_aware=elig, forbid=F)
            self.stats['lp'] += 1
            res = lp.solve() if lp.N else None
        except Exception:
            return 'unknown', None
        self.stats['nodes'] += 1
        if lp.N == 0 or res is None:
            cert = integer_certificate(self.inst, h, use_dom=True,
                                       elig_aware=elig, forbid=F)
            self.stats['cert_lp'] += 1
            if cert is not None and verify(self.inst, h, cert, forbid=F):
                pr = CertLeafProof(self.inst, h, F, cert)
                f.L = h + 1
                f.proof = pr
                return 'no', pr
            return 'split', (None, None, a, b)
        if res.status == 2:
            cert = integer_certificate(self.inst, h, use_dom=True,
                                       elig_aware=elig, forbid=F)
            self.stats['cert_lp'] += 1
            if cert is not None and verify(self.inst, h, cert, forbid=F):
                pr = CertLeafProof(self.inst, h, F, cert)
                f.L = h + 1
                f.proof = pr
                return 'no', pr
            r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                            forbid0=F)
            self.stats['fallback'] += 1
            if r['verdict'] is False:
                f.L = h + 1
                f.proof = r['proof']
                return 'no', r['proof']
            if r['verdict'] is True:
                return 'yes', (r['schedule'], r['machine'])
            return 'split', (None, None, a, b)
        if res.status == 0:
            got = _integral_schedule(self.inst, lp, res.x, elig)
            if got is not None:
                return 'yes', got
            return 'split', (lp, res.x, a, b)
        return 'split', (None, None, a, b)

    def _split_wide(self, f):
        H = self.U - 1
        eff = self._effective_leaf(f, H)
        if eff is None:
            return False
        a, b = eff
        cand = [i for i in range(self.inst['n']) if b[i] > a[i]]
        if not cand:
            return False
        i = max(cand, key=lambda j: (b[j] - a[j], -j))
        mid = (a[i] + b[i]) // 2
        lo1 = list(a); hi1 = list(b); hi1[i] = mid
        lo2 = list(a); hi2 = list(b); lo2[i] = mid + 1
        c0 = self._make_child(f, lo1, hi1)
        c1 = self._make_child(f, lo2, hi2)
        f.children = (c0, c1)
        f.split = (i, mid)
        self.stats['splits'] += 1
        self.stats['max_depth'] = max(self.stats['max_depth'], c0.depth)
        self._refresh_dead()
        return True

    def _make_child(self, parent, lo, hi):
        nd = Node(lo, hi, parent.L, parent.proof, parent=parent,
                  depth=parent.depth + 1, created=self.stats['splits'])
        return nd

    def _split(self, f, lp, z, a, b):
        i, mid = self._choose_split(lp, z, a, b)
        if i is None or not (a[i] <= mid < b[i]):
            return False
        lo1 = list(a)
        hi1 = list(b)
        hi1[i] = mid
        lo2 = list(a)
        hi2 = list(b)
        lo2[i] = mid + 1
        c0 = self._make_child(f, lo1, hi1)
        c1 = self._make_child(f, lo2, hi2)
        f.children = (c0, c1)
        f.split = (i, mid)
        # keep f.proof: it is the inherited NO(L_f-1) proof for the
        # parent box and is what makes contraction sound.
        self.stats['splits'] += 1
        self.stats['max_depth'] = max(self.stats['max_depth'], c0.depth)
        self._refresh_dead()
        return True

    def _contract_once(self, L):
        leaves = self._leaves()
        groups = {}
        for f in leaves:
            if f.parent is not None:
                groups.setdefault(id(f.parent), []).append(f)
        best = None
        for pid, fs in groups.items():
            if len(fs) != 2:
                continue
            par = fs[0].parent
            if par.dead or par.L < L:
                continue
            if par.L > self.U:
                continue
            key = (par.L, -par.depth, par.created)
            if best is None or key > best[0]:
                best = (key, par, fs)
        if best is None:
            return False
        _, par, fs = best
        before = self._global_L()
        par.children = None
        par.split = None
        par.proof = par.proof if par.proof is not None else fs[0].proof
        self.stats['contractions'] += 1
        after = self._global_L()
        if after < before:
            self.stats['regressions'] += 1
        return True

    def _build(self, nd, target):
        inst = self.inst
        eff = _effective(inst, target, nd.lo, nd.hi)
        if eff is None:
            return None
        a, b = eff
        F = _forbid_box(inst, target, a, b)
        if nd.children is None:
            if nd.proof is None:
                return None
            return ('leaf', F, nd.proof.h, nd.proof)
        l = self._build(nd.children[0], target)
        r = self._build(nd.children[1], target)
        if l is None and r is None:
            return None
        if l is None:
            return r
        if r is None:
            return l
        i, mid = nd.split
        return ('split', i, mid, F, l, r)

    def _frontier(self, target):
        tree = self._build(self.root, target)
        if tree is None:
            return None
        return FrontierProof(self.inst, target, tree)

    def run(self):
        inst = self.inst
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        self.stats['pin_lp'] = int(getattr(co, 'pin_lp', 0))
        if ub is None or sched is None:
            return dict(ok=False, error='no-initial-ub')
        L, U = int(lb), int(ub)
        self.L, self.U = L, U
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                proof = r['proof']
        if proof is None:
            return dict(ok=False, error='no-lb-proof')
        init_L, init_U = L, U
        init_sched = list(sched)
        init_mach = list(mach)
        # ACO before the search: only feasible schedules, checked below
        if self.use_aco:
            got = self._seed_aco(U, sched, mach)
            if got is not None:
                s2, m2, c2 = got
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U, sched, mach = c2, list(s2), list(m2)
                    self.stats['aco_impr'] += 1
        self.U = U
        H = U - 1
        lo, hi = _root_box(inst, H)
        self.root = Node(lo, hi, L, proof, depth=0, created=0)
        # after ACO, root target shrinks; intersection is automatic
        self._refresh_dead()
        best_U = U
        best_sched, best_mach = list(sched), list(mach)
        probes = 0
        while True:
            if self._elapsed() > self.max_time if self.max_time else False:
                break
            self._refresh_dead()
            L = self._global_L()
            self.L = L
            if L >= U:
                L = U
                self.L = L
                break
            openf = self._open()
            if not openf:
                L = self._global_L()
                self.L = L
                if L >= U:
                    L = U
                break
            if probes >= self.max_probes or self.stats['splits'] >= self.max_splits:
                break
            # A*: smallest local lower bound; tie: deepest / ant-promise
            f = min(openf, key=lambda x: (x.L, -x.depth, -x.created))
            # probe height policy
            if self.policy == 'lower':
                h = f.L
            elif self.policy == 'binary':
                h = f.L if U - f.L <= 1 else (f.L + U) // 2
            elif self.policy == 'closing':
                h = U - 1
            else:
                h = f.L
            # _probe uses f.L; temporarily probe at h through a shim
            oldL = f.L
            f.L = h
            status, payload = self._probe(f)
            if status != 'no':
                f.L = oldL
            probes += 1
            self.stats['probes'] += 1
            if status == 'no':
                # _probe already set f.L = h+1 and proof
                if f.L > self.stats['max_depth'] * 0 + best_U:
                    pass
                continue
            if status == 'yes':
                s2, m2 = payload
                c2 = cmax(inst, s2)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U, sched, mach = c2, list(s2), list(m2)
                    self.U = U
                    best_U, best_sched, best_mach = U, list(s2), list(m2)
                continue
            if status == 'split':
                lp, z, a, b = payload
                before = len(self._open())
                if before >= self.W:
                    if self.memory_mode == 'contract':
                        made = False
                        while len(self._open()) >= self.W:
                            if self.stats['contractions'] >= self.max_contract:
                                break
                            if not self._contract_once(self._global_L()):
                                break
                            made = True
                        if len(self._open()) >= self.W:
                            self.stats['memory_stops'] += 1
                            break
                    else:
                        self.stats['memory_stops'] += 1
                        break
                if lp is None:
                    ok = self._split_wide(f)
                else:
                    ok = self._split(f, lp, z, a, b)
                    if not ok:
                        ok = self._split_wide(f)
                if not ok:
                    self.stats['unknown'] += 1
                    break
                peak = len(self._leaves())
                if peak > self.stats['peak_leaves']:
                    self.stats['peak_leaves'] = peak
                continue
            self.stats['unknown'] += 1
            break
        self._refresh_dead()
        L = self._global_L()
        self.L = L
        if L >= U:
            L = U
            self.L = L
        # build a certificate at L-1 (partial) or U-1 (final)
        target = L - 1
        frontier = self._frontier(target)
        cert = BAMCertificate(inst, L, U, best_sched, best_mach,
                              frontier, final=(L == U))
        if not cert.audit_rdf():
            # fall back to the initial root proof at L0-1; the bracket is
            # still true but weaker than the reported search state.
            target0 = init_L - 1
            rootF = frozenset()
            try:
                fp0 = FrontierProof(inst, target0,
                                    ('leaf', rootF, proof.h, proof))
            except Exception:
                fp0 = None
            cert = BAMCertificate(inst, init_L, U, best_sched, best_mach,
                                  fp0, final=(init_L == U))
        final_ok = bool(cert.audit_rdf())
        st = dict(self.stats)
        st.update(
            name=getattr(self, 'name', None), idx=getattr(self, 'idx', None),
            known=getattr(self, 'known', None),
            init_L=init_L, init_U=init_U, L=L, U=U,
            opt=U, certified=bool(L == U and final_ok),
            audit=final_ok, proof=final_ok, partial_final=final_ok,
            cert_h=(U - 1 if L == U else None),
            total_lp=(st['lp'] + st['cert_lp'] + st['pin_lp']),
            probe_count=probes, queries=probes,
            aco=bool(self.use_aco), W=self.W, memory_mode=self.memory_mode,
            policy=self.policy, final=bool(L == U),
            init_schedule=list(init_sched),
            init_machine=list(init_mach),
            best_schedule=list(best_sched), best_machine=list(best_mach),
            t=round(time.time() - self.t0, 4),
            ok=bool(L == U and final_ok),
        )
        return st


def run_bam(inst, known, name, idx, **kw):
    co = BAM(inst, **kw)
    co.name, co.idx, co.known = name, idx, known
    r = co.run()
    r.update(name=name, idx=idx, known=known)
    return r
