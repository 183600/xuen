"""v9.2 TDC-PACT: trie-guided decrease-and-conquer probes for ICF-PACT.

The trusted outer state is the v9.0 ICF partial certificate

    C = (L, U, s, m, pi),   pi : NO(L-1),   Cmax(s)=U,   L<=U.

TDC adds an untrusted primal stage in front of each fixed-h oracle call.
The primal stage is a serial-SGS decrease-and-conquer search:

  * a partial schedule is a canonical state (scheduled mask, machine
    busy intervals, predecessor finish times);
  * a trie/DAG merges equal states reached by different prefixes;
  * a beam keeps the best W states, and a rollout completes each child
    with a priority policy;
  * a particle swarm searches the priority-policy space; its global best
    seeds the rollout, and the trie's best schedules feed back to it.

Only an audited schedule with Cmax <= h may lower U.  A failed primal
search changes nothing and falls back to the exact oracle.  Thus the
soundness of the bracket never depends on the heuristic.
"""
from __future__ import annotations

import sys
import time
import math
import random

sys.path[:0] = ['exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8u', 'exp/v8o',
                'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g',
                'exp/v8c', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax,
                 _choose_h, corpora)
from po import heads_tails
from rdf import check_schedule, _earliest
from pact import PACT, pact_decide
from cab import _greedy_rank


def _clip(x, a, b):
    return a if x < a else (b if x > b else x)


def _available(inst, mask):
    return [i for i in range(inst['n'])
            if not (mask >> i) & 1
            and all((mask >> j) & 1 for j in inst['pred'][i])]


def _tails(inst):
    return heads_tails(inst, 0, [0] * inst['n'])[1]


def _lower_bound(inst, mask, predfin, cm, tails):
    n, p = inst['n'], inst['p']
    est = list(predfin)
    for i in range(n):
        if (mask >> i) & 1:
            continue
        e = est[i]
        for j in inst['pred'][i]:
            if not (mask >> j) & 1:
                v = est[j] + p[j]
                if v > e:
                    e = v
        est[i] = e
    lb = cm
    for i in range(n):
        if not (mask >> i) & 1:
            v = est[i] + p[i] + tails[i]
            if v > lb:
                lb = v
    return lb


def _state_key(st):
    mask, starts, machs, busy, predfin, cm = st
    return (mask, tuple(tuple(x) for x in busy), tuple(predfin))


class StateTrie:
    """Hash-consed partial-schedule DAG used by the beam search."""

    def __init__(self, max_states=200000):
        self.best = {}
        self.max_states = int(max_states)
        self.admitted = 0
        self.merged = 0
        self.clears = 0

    def admit(self, st):
        key = _state_key(st)
        old = self.best.get(key)
        if old is not None:
            self.merged += 1
            if old[0] <= st[5]:
                return False
        if len(self.best) >= self.max_states:
            self.best.clear()
            self.clears += 1
        self.best[key] = (st[5], st)
        self.admitted += 1
        return True


class PolicySwarm:
    """A small random-key PSO whose decoder is a serial SGS."""

    def __init__(self, inst, ub, schedule, machine, n_particles=8,
                 iters=12, seed=7, w=0.6, c1=1.5, c2=1.5, vmax=0.5,
                 stall=4):
        self.inst = inst
        self.n = inst['n']
        self.p = inst['p']
        self.ub = int(ub)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.n_particles = int(n_particles)
        self.iters = int(iters)
        self.rng = random.Random(seed)
        self.w, self.c1, self.c2, self.vmax = w, c1, c2, vmax
        self.stall = int(stall)
        self.cache = {}
        self.evals = 0
        self.audit_fail = 0
        self.archive = []
        self.best = None
        self.best_fit = None
        self.t = 0.0

    def _decode(self, x):
        rank = {i: float(x[i]) + 1e-9 * i for i in range(self.n)}
        g = _greedy_rank(self.inst, rank)
        if g is None:
            return None
        s, m, c = g
        if not check_schedule(self.inst, c, s, m):
            self.audit_fail += 1
            return None
        return c, s, m

    def _eval(self, x):
        key = tuple(round(float(v), 6) for v in x)
        if key in self.cache:
            return self.cache[key]
        g = self._decode(x)
        if g is None:
            val = (1e9, None)
        else:
            c, s, m = g
            fit = c + 1e-6 * sum(s[i] + self.p[i] for i in range(self.n))
            val = (fit, g)
            self.archive.append((c, s, m))
        self.cache[key] = val
        self.evals += 1
        return val

    def _seed_positions(self):
        n = self.n
        est, q = heads_tails(self.inst, 0, [0] * n)
        latest = [self.ub - q[i] - self.p[i] for i in range(n)]
        keys = [
            lambda i: est[i],
            lambda i: latest[i],
            lambda i: -q[i],
            lambda i: est[i] - 0.5 * q[i],
        ]
        out = []
        for key in keys:
            order = sorted(range(n), key=lambda i: (key(i), i))
            x = [0.0] * n
            den = max(1, n - 1)
            for pos, i in enumerate(order):
                x[i] = pos / den
            out.append(x)
        if self.schedule is not None:
            order = sorted(range(n), key=lambda i: (self.schedule[i], i))
            x = [0.0] * n
            den = max(1, n - 1)
            for pos, i in enumerate(order):
                x[i] = pos / den
            out.append(x)
        return out

    def run(self):
        t0 = time.time()
        n = self.n
        seeds = self._seed_positions()
        X, V = [], []
        for i in range(self.n_particles):
            if i < len(seeds):
                x = list(seeds[i])
            elif i == len(seeds):
                x = [self.rng.random() for _ in range(n)]
            else:
                base = seeds[self.rng.randrange(len(seeds))]
                x = [_clip(base[d] + self.rng.gauss(0.0, 0.25), 0.0, 1.0)
                     for d in range(n)]
            X.append(x)
            V.append([self.rng.uniform(-0.2, 0.2) for _ in range(n)])
        pbest = [list(x) for x in X]
        pfit = [self._eval(x)[0] for x in X]
        gi = min(range(self.n_particles), key=lambda i: pfit[i])
        gbest, gfit = list(pbest[gi]), pfit[gi]
        gsched = self._eval(gbest)[1]
        since = 0
        for _ in range(1, self.iters + 1):
            improved = False
            for i in range(self.n_particles):
                for d in range(n):
                    r1 = self.rng.random()
                    r2 = self.rng.random()
                    V[i][d] = (self.w * V[i][d]
                               + self.c1 * r1 * (pbest[i][d] - X[i][d])
                               + self.c2 * r2 * (gbest[d] - X[i][d]))
                    V[i][d] = _clip(V[i][d], -self.vmax, self.vmax)
                    X[i][d] = _clip(X[i][d] + V[i][d], 0.0, 1.0)
                fit, val = self._eval(X[i])
                if fit < pfit[i] - 1e-12:
                    pfit[i] = fit
                    pbest[i] = list(X[i])
                    if fit < gfit - 1e-12:
                        gfit = fit
                        gbest = list(X[i])
                        gsched = val
                        improved = True
            since = 0 if improved else since + 1
            if self.stall > 0 and since >= self.stall and self.n_particles >= 4:
                order = sorted(range(self.n_particles),
                               key=lambda i: pfit[i], reverse=True)
                for i in order[:max(1, self.n_particles // 2)]:
                    if i == 0:
                        continue
                    X[i] = [self.rng.random() for _ in range(n)]
                    V[i] = [self.rng.uniform(-0.1, 0.1) for _ in range(n)]
                    pbest[i] = list(X[i])
                    pfit[i] = self._eval(X[i])[0]
                since = 0
        if gsched is None:
            gsched = (self.ub, self.schedule, self.machine)
        self.best = gsched
        self.best_fit = gfit
        self.t = time.time() - t0
        return self.best


class TDC:
    """Trie-guided decrease-and-conquer primal stage."""

    def __init__(self, inst, U, schedule, machine, width=20, nodecap=5000,
                 timelimit=0.02, n_particles=8, iters=12, seed=7,
                 stall=4, use_pso=True, use_trie=True, max_states=200000,
                 n_ranks=1):
        self.inst = inst
        self.width = int(width)
        self.nodecap = int(nodecap)
        self.timelimit = timelimit
        self.use_pso = bool(use_pso)
        self.use_trie = bool(use_trie)
        self.n_ranks = int(n_ranks)
        self.trie = StateTrie(max_states=max_states)
        self.swarm = PolicySwarm(inst, U, schedule, machine,
                                 n_particles=n_particles, iters=iters,
                                 seed=seed, stall=stall)
        self.tails = _tails(inst)
        self.ranks = None
        self.best_schedule = None
        self.best_cmax = int(U)
        self.calls = 0
        self.success = 0
        self.nodes = 0
        self.rollouts = 0
        self.t = 0.0
        self.pso_evals = 0
        self.pso_t = 0.0

    def _prepare(self):
        if self.ranks is not None:
            return
        n = self.inst['n']
        if self.use_pso:
            c, s, m = self.swarm.run()
            self.pso_evals += self.swarm.evals
            self.pso_t += self.swarm.t
            self.best_cmax = min(self.best_cmax, int(c))
            self.best_schedule = (list(s), list(m), int(c))
            rank = {i: s[i] + 1e-6 * i for i in range(n)}
        else:
            est, _ = heads_tails(self.inst, 0, [0] * n)
            rank = {i: est[i] + 1e-6 * i for i in range(n)}
        est, q = heads_tails(self.inst, 0, [0] * n)
        rank2 = {i: est[i] + 1e-6 * i for i in range(n)}
        self.ranks = [rank, rank2]

    def _expand(self, st, target):
        n, p = self.inst['n'], self.inst['p']
        mask, starts, machs, busy, predfin, cm = st
        out = []
        for i in _available(self.inst, mask):
            base = predfin[i]
            best = None
            for k in self.inst['elig'][i]:
                t = _earliest(busy[k], base, p[i])
                cand = (t + p[i], t, k)
                if best is None or cand < best:
                    best = cand
            if best is None:
                continue
            ft, t, k = best
            if ft > target:
                continue
            nm = mask | (1 << i)
            ns = list(starts)
            ns[i] = t
            nmach = list(machs)
            nmach[i] = k
            nb = [list(x) for x in busy]
            nb[k].append((t, ft))
            nb[k].sort()
            npf = list(predfin)
            for j in self.inst['succ'][i]:
                if ft > npf[j]:
                    npf[j] = ft
            lb = _lower_bound(self.inst, nm, npf, max(cm, ft), self.tails)
            if lb > target:
                continue
            out.append((nm, ns, nmach, nb, npf, max(cm, ft)))
        return out

    def _complete(self, st, rank, target):
        n, p = self.inst['n'], self.inst['p']
        mask, starts, machs, busy, predfin, cm = st
        starts = list(starts)
        machs = list(machs)
        busy = [list(x) for x in busy]
        predfin = list(predfin)
        while mask != (1 << n) - 1:
            av = _available(self.inst, mask)
            if not av:
                return None
            av.sort(key=lambda i: (rank[i], i))
            i = av[0]
            base = predfin[i]
            best = None
            for k in self.inst['elig'][i]:
                t = _earliest(busy[k], base, p[i])
                cand = (t + p[i], t, k)
                if best is None or cand < best:
                    best = cand
            if best is None:
                return None
            ft, t, k = best
            if ft > target:
                return None
            mask |= 1 << i
            starts[i] = t
            machs[i] = k
            busy[k].append((t, ft))
            busy[k].sort()
            for j in self.inst['succ'][i]:
                if ft > predfin[j]:
                    predfin[j] = ft
            cm = max(cm, ft)
        return starts, machs, cm

    def probe(self, h):
        t0 = time.time()
        self.calls += 1
        self._prepare()
        if self.best_schedule is not None and self.best_cmax <= h:
            self.success += 1
            self.t += time.time() - t0
            return self.best_schedule
        if self.width <= 0:
            self.t += time.time() - t0
            return None
        n = self.inst['n']
        root = (0, [None] * n, [None] * n,
                [[] for _ in range(self.inst['m'])], [0] * n, 0)
        beam = [root]
        nodes = 0
        rollouts = 0
        for _ in range(n):
            if (self.timelimit is not None
                    and time.time() - t0 > self.timelimit):
                break
            cand = []
            for st in beam:
                ch = self._expand(st, h)
                nodes += len(ch)
                for c in ch:
                    if self.use_trie:
                        if self.trie.admit(c):
                            cand.append(c)
                    else:
                        cand.append(c)
                if nodes > self.nodecap:
                    break
            if nodes > self.nodecap or not cand:
                break
            cand.sort(key=lambda s: (
                _lower_bound(self.inst, s[0], s[4], s[5], self.tails),
                s[5], s[0]))
            cand = cand[:self.width]
            for c in cand:
                for rank in self.ranks[:max(1, self.n_ranks)]:
                    r = self._complete(c, rank, h)
                    rollouts += 1
                    if r is not None:
                        ss, mm, cc = r
                        if check_schedule(self.inst, cc, ss, mm):
                            self.success += 1
                            self.nodes += nodes
                            self.rollouts += rollouts
                            self.t += time.time() - t0
                            self.best_cmax = min(self.best_cmax, cc)
                            self.best_schedule = (list(ss), list(mm), int(cc))
                            return ss, mm, cc
            beam = cand
        self.nodes += nodes
        self.rollouts += rollouts
        self.t += time.time() - t0
        return None


def run_tdc_icf(inst, known, name, idx, policy='lower-first',
                max_probes=64, initial=None, use_pact_init=True,
                use_tdc=True, mode='tdc', width=20, nodecap=5000,
                timelimit=0.02, n_particles=8, iters=12, seed=7,
                stall=4, tdc_max_gap=99, use_trie=True, n_ranks=1):
    t0 = time.time()
    co = None
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        pin_lp = 0
    elif use_pact_init:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        L, U, sched, mach = co.initial_bounds()
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        pin_lp = getattr(co, 'pin_lp', 0)
    else:
        from hap import init_weak
        L, U, sched, mach, lb_proof = init_weak(inst)
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        pin_lp = 0
    if U is None or sched is None or mach is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-initial-ub', t=0.0)
    if lb_proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='no-lb-proof', t=0.0)

    tdc = None
    if use_tdc and mode != 'off':
        tdc = TDC(inst, U, sched, mach, width=width, nodecap=nodecap,
                  timelimit=timelimit, n_particles=n_particles,
                  iters=iters, seed=seed, stall=stall,
                  use_pso=(mode in ('tdc', 'pso')),
                  use_trie=use_trie, n_ranks=n_ranks)
    probes = 0
    pact_lp = 0
    cert_lp = 0
    nodes = 0
    partial_ok = 0
    partial_fail = 0
    tdc_calls = 0
    tdc_success = 0
    first = True
    lb0, ub0 = L, U
    steps = []

    def audit():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        if (tdc is not None and (U - L) <= tdc_max_gap):
            tdc_calls += 1
            r = tdc.probe(h)
            if r is not None:
                s2, m2, c2 = r
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = int(c2)
                    sched = list(s2)
                    mach = list(m2)
                    tdc_success += 1
                    steps.append(dict(h=h, v=True, cmax=c2, tdc=True,
                                      L0=L0, U0=U0, L1=L, U1=U))
                    audit()
                    first = False
                    continue
        probes += 1
        first = False
        rr = pact_decide(inst, h, depthcap=None, nodecap=None)
        pact_lp += rr.get('lp_solves', 0)
        cert_lp += rr.get('cert_lp', 0)
        nodes += rr.get('nodes', 0)
        if rr['verdict'] is False:
            proof = rr['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif rr['verdict'] is True:
            s2, m2 = rr['schedule'], rr['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched = list(s2)
                mach = list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            steps.append(dict(h=h, v=None, lp=rr.get('lp_solves', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            audit()
            break
        audit()
    final = ICFCertificate(inst, U, sched, mach, lb_proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, mode=mode,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok), audit=final_ok,
        proof=final_ok, cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=nodes, pact_cert_lp=cert_lp,
        pin_lp=pin_lp, partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final,
        tdc_calls=tdc_calls, tdc_success=tdc_success,
        tdc_nodes=(tdc.nodes if tdc else 0),
        tdc_rollouts=(tdc.rollouts if tdc else 0),
        tdc_t=round(tdc.t, 4) if tdc else 0.0,
        trie_admitted=(tdc.trie.admitted if tdc else 0),
        trie_merged=(tdc.trie.merged if tdc else 0),
        trie_clears=(tdc.trie.clears if tdc else 0),
        pso_evals=(tdc.pso_evals if tdc else 0),
        pso_t=round(tdc.pso_t, 4) if tdc else 0.0,
        steps=steps, total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )
