"""v9.4 EBA-ICF: evolutionary backtracking approximation for ICF.

The v9.3 PD-ICF state is kept unchanged:

    C = (L, U, s, m, pi),  pi : NO(L-1),  Cmax(s)=U,  L<=U.

EBA changes only the primal side.  It searches the *joint* space of
priority orders and machine routings, not just priority orders:

    genome = (keys, route),  route[i] in elig[i] or None (greedy).

The decoder is a routing-aware serial SGS.  Two search engines cooperate:

  LDS   iterative-deepening limited-discrepancy search around a portfolio
        of LP references (quantiles, mean, tail, latest).  The discrepancy
        budget is the approximation parameter of an anytime search scheme:
        budget 0 is the reference policy, budget 2n is the full space.

  EA    a small random-key memetic algorithm over (keys, route).  LP
        quantile orders seed the population; crossover/mutation and a
        one-move routing descent explore the joint space.  Its elites are
        also used as LDS references.

All accepted schedules pass check_schedule and Cmax <= H.  The exact
fixed-h oracle and the partial/ICF certificates are unchanged.
"""
import sys
import time
import math
import random
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import PartialCertificate, ICFCertificate, cmax
from pact import PACT, pact_decide
from lbp import ParametricSD
from lpr import sgs, topo_order, marginals, quantile, _pin_weak, _guide_at
from po import heads_tails
from rdf import check_schedule
from pdicf import decode_orders, decode_random, cfa_orders


def greedy_place(inst, starts, busy, i):
    base = 0
    for j in inst['pred'][i]:
        v = starts[j] + inst['p'][j]
        if v > base:
            base = v
    best = None
    for k in inst['elig'][i]:
        t = base
        pi = inst['p'][i]
        for a, b in busy[k]:
            if t + pi <= a:
                break
            if t < b:
                t = b
        cand = (t + pi, t, k)
        if best is None or cand < best:
            best = cand
    return best[2], best[1], best[0]


def sgs_route(inst, order, route, H=None):
    """Serial SGS with an explicit machine route.

    route[i] = None or -1 means "use the greedy earliest machine".
    A route outside elig[i] is repaired greedily; this keeps every genome
    decodable, while LDS only branches over eligible machines.
    """
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, elig = inst['pred'], inst['elig']
    starts = [0] * n
    machine = [-1] * n
    busy = [[] for _ in range(m)]
    for i in order:
        base = 0
        for j in pred[i]:
            v = starts[j] + p[j]
            if v > base:
                base = v
        k = route[i] if route is not None else -1
        if k is None or k < 0 or k >= m or k not in elig[i]:
            k, t, ft = greedy_place(inst, starts, busy, i)
        else:
            t = base
            pi = p[i]
            for a, b in busy[k]:
                if t + pi <= a:
                    break
                if t < b:
                    t = b
            ft = t + pi
        if H is not None and ft > H:
            return None
        starts[i] = t
        machine[i] = k
        busy[k].append((t, ft))
        busy[k].sort()
    c = max(starts[i] + p[i] for i in range(n))
    return starts, machine, c


def greedy_route(inst, order):
    r = sgs(inst, order, None)
    if r is None:
        return None
    return list(r[1])


def ref_portfolio(inst, ps, res, H, use_cfa=True):
    """LP reference orders and their greedy routes."""
    if res is None or getattr(res, 'x', None) is None:
        return []
    mrg = marginals(inst, ps, res)
    mean = [m for m, _ in mrg]
    est, tail = heads_tails(inst, 0, [0] * inst['n'])
    specs = []
    for q in (0.98, 0.75):
        specs.append(('q%g' % q,
                      lambda i, q=q: quantile(mrg[i][1], q) + i * 1e-6))
    specs.append(('mean', lambda i: mean[i] + i * 1e-6))
    for q in (0.5, 0.9, 0.25, 0.1, 0.02):
        specs.append(('q%g' % q,
                      lambda i, q=q: quantile(mrg[i][1], q) + i * 1e-6))
    specs.append(('tail', lambda i: -tail[i] + i * 1e-6))
    specs.append(('latest',
                  lambda i: -(H - tail[i] - inst['p'][i]) + i * 1e-6))
    if use_cfa:
        specs.extend(cfa_orders(inst, mean, tail, H))
    out = []
    for tag, key in specs:
        order = topo_order(inst, key)
        if order is None:
            continue
        route = greedy_route(inst, order)
        if route is None:
            continue
        out.append(dict(tag=tag, key=key, keys=[key(i) for i in range(inst['n'])],
                        order=order, route=route))
    return out


class LDS:
    """Iterative-deepening LDS over (job, machine) SGS decisions."""

    def __init__(self, inst, H, keys, ref_route, max_disc, node_cap,
                 time_cap, routing=True):
        self.inst = inst
        self.H = H
        self.keys = keys
        self.ref_route = ref_route
        self.max_disc = max_disc
        self.node_cap = node_cap
        self.time_cap = time_cap
        self.routing = routing
        self.nodes = 0
        self.t0 = time.time()
        self.found = None
        self.best = 10 ** 9
        self.best_sched = None
        self.starts = [0] * inst['n']
        self.machine = [-1] * inst['n']
        self.busy = [[] for _ in range(inst['m'])]
        n = inst['n']
        self.succ = inst['succ']
        self.pred = inst['pred']
        self.elig = inst['elig']
        self.p = inst['p']
        self.est, self.tail = heads_tails(inst, 0, [0] * n)
        self.base_lb = [self.est[i] + self.p[i] + self.tail[i]
                        for i in range(n)]
        self.indeg0 = [len(self.pred[i]) for i in range(n)]

    def _lb(self, indeg):
        lb = 0
        for i in range(self.inst['n']):
            if indeg[i] >= 0:
                v = self.base_lb[i]
                if v > lb:
                    lb = v
        return lb

    def run(self):
        ready = frozenset(i for i in range(self.inst['n'])
                          if self.indeg0[i] == 0)
        self._rec(ready, list(self.indeg0), 0, 0)
        return dict(found=self.found, best=(None if self.best >= 10 ** 9
                                            else self.best),
                    nodes=self.nodes, t=time.time() - self.t0,
                    schedule=(None if self.found is None
                              else self.found[0]),
                    machine=(None if self.found is None
                             else self.found[1]))

    def _place(self, i, k):
        base = 0
        for j in self.pred[i]:
            v = self.starts[j] + self.p[j]
            if v > base:
                base = v
        t = base
        pi = self.p[i]
        for a, b in self.busy[k]:
            if t + pi <= a:
                break
            if t < b:
                t = b
        return t, t + pi

    def _rec(self, ready, indeg, disc, cur):
        if self.found is not None:
            return
        self.nodes += 1
        if self.nodes > self.node_cap or time.time() - self.t0 > self.time_cap:
            return
        if not ready:
            if cur < self.best:
                self.best = cur
                self.best_sched = (list(self.starts), list(self.machine))
            if cur <= self.H:
                self.found = (list(self.starts), list(self.machine), cur)
            return
        lb = self._lb(indeg)
        if max(cur, lb) > self.H:
            return
        order = sorted(ready, key=lambda i: (self.keys[i], i))
        refjob = order[0]
        for i in order:
            gi, _, _ = greedy_place(self.inst, self.starts, self.busy, i)
            if self.routing:
                machs = sorted(self.elig[i], key=lambda k: (k != gi, k))
            else:
                machs = [gi]
            for k in machs:
                if k is None or k < 0 or k not in self.elig[i]:
                    continue
                same_m = (k == gi)
                nd = disc + (0 if i == refjob else 1) + (0 if same_m else 1)
                if nd > self.max_disc:
                    continue
                t, ft = self._place(i, k)
                if ft > self.H:
                    continue
                old = list(self.busy[k])
                self.busy[k].append((t, ft))
                self.busy[k].sort()
                self.starts[i] = t
                self.machine[i] = k
                nready = frozenset(j for j in ready if j != i)
                nind = list(indeg)
                nind[i] = -1
                for j in self.succ[i]:
                    nind[j] -= 1
                    if nind[j] == 0:
                        nready = nready | {j}
                self._rec(nready, nind, nd, cur if cur >= ft else ft)
                self.busy[k] = old
                self.starts[i] = 0
                self.machine[i] = -1
                if self.found is not None:
                    return


def lds_search(inst, H, keys, ref_route, budgets=(1, 2, 3, 4),
               node_cap=4000, time_cap=0.03, routing=False):
    total = 0
    t0 = time.time()
    best = None
    for d in budgets:
        left_nodes = node_cap - total
        if left_nodes <= 0:
            break
        left_t = time_cap - (time.time() - t0)
        if left_t <= 0:
            break
        z = LDS(inst, H, keys, ref_route, d, left_nodes, left_t,
                routing=routing).run()
        total += z['nodes']
        if z['found'] is not None:
            z['nodes'] = total
            return z
        if z['best'] is not None and (best is None or z['best'] < best):
            best = z['best']
    return dict(found=None, best=best, nodes=total,
                t=time.time() - t0, schedule=None, machine=None)


def _eval_genome(inst, keys, route, H):
    order = topo_order(inst, lambda i: keys[i])
    if order is None:
        return None
    r = sgs_route(inst, order, route, None)
    if r is None:
        return None
    s, m, c = r
    if c <= H and check_schedule(inst, c, s, m):
        return dict(hit=True, cmax=c, schedule=s, machine=m,
                    order=order, route=list(m))
    return dict(hit=False, cmax=c, schedule=s, machine=m,
                order=order, route=list(m))


def ea_search(inst, H, refs, seed=0, pop_size=16, generations=8,
              time_cap=0.04):
    """Random-key memetic EA over (keys, route)."""
    rng = random.Random(seed)
    n = inst['n']
    t0 = time.time()
    pop = []
    best = None

    def add(keys, route):
        nonlocal best
        keys = tuple(float(x) for x in keys)
        route = tuple(int(x) if x is not None else -1 for x in route)
        if len(pop) >= pop_size * 2:
            return
        ev = _eval_genome(inst, keys, route, H)
        if ev is None:
            return
        pop.append((ev['cmax'], keys, route, ev))
        if ev['hit']:
            if best is None or ev['cmax'] < best['cmax']:
                best = ev
        elif best is None or ev['cmax'] < best['cmax']:
            best = ev

    for ref in refs[:10]:
        add(ref['keys'], ref['route'])
        for _ in range(2):
            keys = [ref['keys'][i] + rng.gauss(0, 0.15 * max(1, H))
                    for i in range(n)]
            route = list(ref['route'])
            if n and rng.random() < 0.7:
                i = rng.randrange(n)
                route[i] = rng.choice(inst['elig'][i])
            add(keys, route)
    for _ in range(pop_size):
        add([rng.uniform(0, max(1, H)) for _ in range(n)],
            [rng.choice(inst['elig'][i]) for i in range(n)])

    if not pop:
        return dict(hit=False, cmax=None, schedule=None, machine=None,
                    work=0, kind='ea-miss')
    work = len(pop)
    if best is not None and best.get('hit'):
        return dict(hit=True, cmax=best['cmax'], schedule=best['schedule'],
                    machine=best['machine'], work=work, kind='ea')

    for gen in range(generations):
        if time.time() - t0 > time_cap:
            break
        pop.sort(key=lambda z: z[0])
        newpop = pop[:4]
        elite = pop[0]
        # one-move routing descent on the elite
        ekeys, eroute = elite[1], list(elite[2])
        for i in range(n):
            for k in inst['elig'][i]:
                if k == eroute[i]:
                    continue
                rr = list(eroute)
                rr[i] = k
                add(ekeys, rr)
                work += 1
                if best is not None and best.get('hit'):
                    break
            if best is not None and best.get('hit'):
                break
        if best is not None and best.get('hit'):
            break
        while len(newpop) < pop_size:
            a = min(rng.sample(pop, min(3, len(pop))),
                    key=lambda z: z[0])
            b = min(rng.sample(pop, min(3, len(pop))),
                    key=lambda z: z[0])
            keys = [a[1][i] if rng.random() < 0.5 else b[1][i]
                    for i in range(n)]
            route = [a[2][i] if rng.random() < 0.5 else b[2][i]
                     for i in range(n)]
            for i in range(n):
                if rng.random() < 0.15:
                    keys[i] += rng.gauss(0, 0.12 * max(1, H))
                if rng.random() < 0.08:
                    route[i] = rng.choice(inst['elig'][i])
                elif rng.random() < 0.03:
                    route[i] = -1
            keys_t = tuple(keys)
            route_t = tuple(route)
            ev = _eval_genome(inst, keys_t, route_t, H)
            if ev is None:
                continue
            newpop.append((ev['cmax'], keys_t, route_t, ev))
            work += 1
            if ev['hit']:
                return dict(hit=True, cmax=ev['cmax'],
                            schedule=ev['schedule'],
                            machine=ev['machine'], work=work, kind='ea')
            if best is None or ev['cmax'] < best['cmax']:
                best = ev
        pop = newpop
    return dict(hit=False,
                cmax=(best['cmax'] if best is not None else None),
                schedule=(best['schedule'] if best is not None else None),
                machine=(best['machine'] if best is not None else None),
                work=work, kind='ea-miss')


def try_eba(inst, ps, res, H, use_cfa=True, seed=0,
            det_time_cap=0.08, lds_nodes=4000, lds_time=0.03,
            ea_time=0.04, do_ea=True, do_route=True):
    """One EBA round at horizon H.  Returns a hit dict or None."""
    r = decode_orders(inst, ps, res, H, use_cfa=use_cfa)
    work = r.get('work', 0)
    if r['hit']:
        r['work'] = work
        r['kind'] = 'det:' + str(r.get('kind'))
        return r
    # full-evaluation near-miss scan
    refs = ref_portfolio(inst, ps, res, H, use_cfa=use_cfa)
    best_full = None
    for ref in refs:
        z = sgs_route(inst, ref['order'], ref['route'], None)
        work += 1
        if z is not None and (best_full is None or z[2] < best_full):
            best_full = z[2]
    if best_full is not None and best_full > H + 3:
        return None
    # order-only discrepancy search: shallow budgets first
    for d, nref, cap in ((1, 5, max(300, lds_nodes // 3)),
                         (2, 4, lds_nodes),
                         (3, 2, lds_nodes),
                         (4, 2, lds_nodes)):
        for ref in refs[:nref]:
            z = lds_search(inst, H, ref['keys'], ref['route'],
                           budgets=(d,), node_cap=cap,
                           time_cap=lds_time, routing=False)
            work += z['nodes']
            if z['found'] is not None:
                return dict(hit=True, cmax=z['found'][2],
                            schedule=z['found'][0],
                            machine=z['found'][1], work=work,
                            kind='lds:' + ref['tag'])
    if do_ea:
        z = ea_search(inst, H, refs, seed=seed, time_cap=ea_time)
        work += z.get('work', 0)
        if z['hit']:
            z['work'] = work
            return z
    if do_route:
        for ref in refs[:3]:
            z = lds_search(inst, H, ref['keys'], ref['route'],
                           budgets=(1, 2), node_cap=lds_nodes // 2,
                           time_cap=lds_time, routing=True)
            work += z['nodes']
            if z['found'] is not None:
                return dict(hit=True, cmax=z['found'][2],
                            schedule=z['found'][0],
                            machine=z['found'][1], work=work,
                            kind='lds-r:' + ref['tag'])
    return None


def run_eba(inst, known, name, idx, initial=None, use_cfa=True,
            restarts=50, time_cap=0.08, max_probes=64, seed=0,
            lds_nodes=4000, lds_time=0.03, ea_time=0.04,
            do_ea=True, do_route=True):
    t0 = time.time()
    if initial is None:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, s, m = co.initial_bounds()
        L, U = int(L), int(U)
        s, m = list(s), list(m)
        proof = co._ensure_lb_proof(L)
        if proof is None:
            r0 = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r0['verdict'] is False:
                proof = r0['proof']
        pin_lp = getattr(co, 'pin_lp', 0)
    else:
        L0, U0, s0, m0, proof0 = initial
        co, L, U, s, m, proof, pin_lp = _pin_weak(
            inst, L0, U0, s0, m0, proof0)
    if proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)

    L0, U0 = int(L), int(U)
    ps = None
    guide = None
    if L < U:
        ps, guide, extra = _guide_at(co, L)
        pin_lp += extra
        if ps is None or guide is None or getattr(guide, 'x', None) is None:
            ps = ParametricSD(inst, int(U))
            guide = ps.solve_h(L)
            pin_lp += 1

    probes = 0
    search_lp = 0
    cert_lp = 0
    round_work = 0
    eba_work = 0
    round_hits = 0
    eba_hits = 0
    lds_hits = 0
    ea_hits = 0
    route_hits = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    defect_after_round = U - L

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1

    def use_sched(c, s2, m2):
        nonlocal U, s, m
        if c < U and check_schedule(inst, c, s2, m2):
            U = c
            s, m = list(s2), list(m2)
            return True
        return False

    def try_round(target):
        nonlocal round_work, eba_work, round_hits, eba_hits
        nonlocal lds_hits, ea_hits, route_hits, search_lp
        if ps is None or target >= U:
            return None
        res = guide
        if res is None or getattr(res, 'x', None) is None:
            res = ps.solve_h(target)
            search_lp += 1
        r = try_eba(inst, ps, res, target, use_cfa=use_cfa, seed=seed,
                    lds_nodes=lds_nodes, lds_time=lds_time,
                    ea_time=ea_time, do_ea=do_ea, do_route=do_route)
        if r is None:
            return None
        work = r.get('work', 0)
        kind = str(r.get('kind', ''))
        if kind.startswith('det'):
            round_work += work
            round_hits += 1
        else:
            eba_work += work
            eba_hits += 1
            if kind.startswith('lds'):
                lds_hits += 1
                if kind.startswith('lds-r'):
                    route_hits += 1
            elif kind.startswith('ea'):
                ea_hits += 1
        return r

    audit()
    if L < U:
        r = try_round(L)
        if r is not None:
            use_sched(r['cmax'], r['schedule'], r['machine'])
            steps.append(('ROUND', L, r['cmax'], r['kind']))
            audit()
        defect_after_round = U - L

    first = True
    while L < U and probes < max_probes:
        h = L if first else (L + U) // 2
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
            if L < U and ps is not None:
                r2 = try_round(L)
                if r2 is not None:
                    use_sched(r2['cmax'], r2['schedule'], r2['machine'])
                    steps.append(('ROUND', L, r2['cmax'], r2['kind']))
                    audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))
            break

    if L < U and probes < max_probes:
        h = U - 1
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        search_lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            L = h + 1
            proof = r['proof']
            steps.append(('NO', h))
            audit()
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            use_sched(c2, s2, m2)
            steps.append(('YES', h, c2))
            audit()
        else:
            steps.append(('UNKNOWN', h))

    final = (ICFCertificate(inst, U, s, m, proof)
             if L == U else None)
    final_ok = bool(final is not None and final.audit_rdf())
    pc = PartialCertificate(inst, L, U, s, m, proof, probe=probes)
    partial_final = bool(pc.audit_rdf())
    return dict(
        name=name, idx=idx, known=known,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        defect=defect_after_round,
        probes=probes, search_lp=search_lp, cert_lp=cert_lp,
        pin_lp=pin_lp,
        round_work=round_work, eba_work=eba_work,
        round_hits=round_hits, eba_hits=eba_hits,
        lds_hits=lds_hits, ea_hits=ea_hits, route_hits=route_hits,
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        certified=bool(L == U and final_ok), audit=final_ok,
        proof=final_ok, cert_h=(U - 1 if L == U else None),
        proof_kind=getattr(proof, 'kind', None),
        steps=steps, t=round(time.time() - t0, 4),
        schedule=list(s) if s is not None else None,
        machine=list(m) if m is not None else None,
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and partial_final))
