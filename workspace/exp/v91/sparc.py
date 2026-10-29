"""v9.1 SPARC: sampling-proposed, audit-refined certificates.

SPARC keeps the v9.0 ICF trusted state

    (L, U, s, m, pi)   with   pi : NO(L-1), Cmax(s)=U, L<=U,

and adds an untrusted particle-swarm layer.  Particles live in random-key
space; the decoder is a serial SGS followed by check_schedule.  Only an
audited schedule may lower U.  The swarm never writes pi, so it cannot
create a false NO fact.  This is the one-sided heuristic contract.

The primal heuristic makes U tight; the exact loop then runs an
incumbent-first policy (probe U-1) with a binary fallback.  The policy is
a certified bracket contraction rule, not a source of soundness.
"""
import sys
import time
import math
import random

sys.path[:0] = ['exp/v91', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import BoundProof, bound_lb
from cab import _greedy_rank
from chip import base_bounds
from icf import (PartialCertificate, ICFCertificate, cmax, corpora)
from pact import PACT, pact_decide
from po import heads_tails
from rdf import check_schedule


def _clip(x, a, b):
    return a if x < a else (b if x > b else x)


def _seed_from_key(inst, key):
    n = inst['n']
    order = sorted(range(n), key=lambda i: (key(i), i))
    x = [0.0] * n
    den = max(1, n - 1)
    for pos, i in enumerate(order):
        x[i] = pos / den
    return x


class Swarm:
    """A small random-key PSO whose every decode is SGS-feasible."""

    def __init__(self, inst, ub, sched, mach, n_particles=8, iters=12,
                 seed=7, w=0.6, c1=1.5, c2=1.5, vmax=0.5, stall=4):
        self.inst = inst
        self.n = inst['n']
        self.p = inst['p']
        self.ub = int(ub)
        self.sched = list(sched) if sched is not None else None
        self.mach = list(mach) if mach is not None else None
        self.n_particles = int(n_particles)
        self.iters = int(iters)
        self.rng = random.Random(seed)
        self.w, self.c1, self.c2, self.vmax = w, c1, c2, vmax
        self.stall = int(stall)
        self.cache = {}
        self.evals = 0
        self.unique = 0
        self.audit_fail = 0
        self.accepted = 0
        self.archive = []
        self.history = []
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
            fit = 1e9
            val = (fit, None)
        else:
            c, s, m = g
            fit = c + 1e-6 * sum(s[i] + self.p[i]
                                 for i in range(self.n))
            val = (fit, g)
            self.archive.append((c, s, m))
        self.cache[key] = val
        self.evals += 1
        self.unique = len(self.cache)
        return val

    def _seeds(self):
        n = self.n
        est, q = heads_tails(self.inst, 0, [0] * n)
        latest = [self.ub - q[i] - self.p[i] for i in range(n)]
        out = []
        for key in (lambda i: est[i],
                    lambda i: latest[i],
                    lambda i: -q[i],
                    lambda i: est[i] - 0.5 * q[i]):
            out.append(_seed_from_key(self.inst, key))
        if self.sched is not None:
            out.append(_seed_from_key(
                self.inst, lambda i: (self.sched[i], i)))
        return out

    def run(self):
        t0 = time.time()
        n = self.n
        seeds = self._seeds()
        X, V = [], []
        for i in range(self.n_particles):
            if i < len(seeds):
                x = list(seeds[i])
            elif i == len(seeds):
                x = [self.rng.random() for _ in range(n)]
            else:
                base = seeds[self.rng.randrange(len(seeds))]
                x = [_clip(float(base[d]) + self.rng.gauss(0.0, 0.20),
                           0.0, 1.0) for d in range(n)]
            X.append(x)
            V.append([self.rng.uniform(-0.1, 0.1) for _ in range(n)])

        pbest = [list(x) for x in X]
        pfit = [self._eval(x)[0] for x in X]
        gi = min(range(self.n_particles), key=lambda i: pfit[i])
        gbest = list(pbest[gi])
        gfit = pfit[gi]
        gsched = self._eval(gbest)[1]
        self.history.append(dict(it=0, best=gfit, evals=self.evals))
        since = 0

        for it in range(1, self.iters + 1):
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
            self.history.append(dict(it=it, best=gfit, evals=self.evals))
            since = 0 if improved else since + 1
            if since >= self.stall and self.n_particles >= 4:
                order = sorted(range(self.n_particles),
                               key=lambda i: pfit[i], reverse=True)
                for i in order[:max(1, self.n_particles // 2)]:
                    if i == 0:
                        continue
                    X[i] = [self.rng.random() for _ in range(n)]
                    V[i] = [self.rng.uniform(-0.1, 0.1)
                            for _ in range(n)]
                    pbest[i] = list(X[i])
                    pfit[i] = self._eval(X[i])[0]
                since = 0

        if gsched is None:
            self.best = (self.ub, self.sched, self.mach)
        else:
            self.best = gsched
        self.best_fit = gfit
        self.t = time.time() - t0
        vals = sorted(c for c, _, _ in self.archive)
        self.stats = dict(
            evals=self.evals, unique=self.unique,
            audit_fail=self.audit_fail, accepted=0,
            best=int(vals[0]) if vals else self.ub,
            second=int(vals[1]) if len(vals) > 1 else self.ub,
            median=int(vals[len(vals) // 2]) if vals else self.ub,
            q25=int(vals[len(vals) // 4]) if vals else self.ub,
            spread=(int(vals[len(vals) // 2]) - int(vals[0])
                    if vals else 0),
            t=round(self.t, 4))
        return self.best, self.stats


def _weak_init(inst):
    lb, ub, s, m, est, q = base_bounds(inst)
    proof = None
    if ub is not None and bound_lb(inst) == lb:
        proof = BoundProof(inst, lb - 1, lb)
        if not proof.audit_rdf():
            proof = None
    if proof is None:
        r = pact_decide(inst, lb - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            proof = r['proof']
    return lb, ub, s, m, proof, 0


def _strong_init(inst):
    co = PACT(inst, pact_mode='complete', use_ga=False)
    lb, ub, s, m = co.initial_bounds()
    proof = co._ensure_lb_proof(lb)
    return lb, ub, s, m, proof, getattr(co, 'pin_lp', 0)


def _choose_h(policy, L, U, first, inc_left):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'incumbent-1':
        return U - 1 if inc_left > 0 else (L + U) // 2
    if policy == 'incumbent-3':
        return U - 1 if inc_left > 0 else (L + U) // 2
    if policy in ('adaptive', 'adaptive-gap', 'adaptive-init'):
        return U - 1 if inc_left > 0 else (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


def _inc_budget(policy):
    if policy == 'incumbent-1':
        return 1
    if policy == 'incumbent-3':
        return 3
    if policy in ('adaptive', 'adaptive-gap', 'adaptive-init'):
        return 1
    return 0


def run_sparc(inst, known, name, idx, init='weak', pso_on=True,
              policy='incumbent-1', n_particles=8, iters=12, seed=7,
              max_probes=64, pso_stall=4, max_unknown=2):
    t0 = time.time()
    if init == 'weak':
        L, U, s, m, lb_proof, pin_lp = _weak_init(inst)
    elif init == 'strong':
        L, U, s, m, lb_proof, pin_lp = _strong_init(inst)
    else:
        raise ValueError('unknown init %r' % (init,))
    if U is None or lb_proof is None:
        return dict(corpus=None, name=name, idx=idx, known=known,
                    init=init, policy=policy, pso=bool(pso_on),
                    ok=False, error='no-init', t=0.0)

    L, U = int(L), int(U)
    s = list(s) if s is not None else None
    m = list(m) if m is not None else None
    lb0, ub0 = L, U
    pso_stats = None
    pso_lp = 0
    pso_evals = 0
    pso_time = 0.0
    ub_pso = U
    audit_ok = 0
    audit_fail = 0
    steps = []

    def audit_state():
        nonlocal audit_ok, audit_fail
        pc = PartialCertificate(inst, L, U, s, m, lb_proof, probe=len(steps))
        if pc.audit_rdf():
            audit_ok += 1
        else:
            audit_fail += 1
        return pc

    audit_state()

    if pso_on:
        sw = Swarm(inst, U, s, m, n_particles=n_particles, iters=iters,
                   seed=seed, stall=pso_stall)
        best, pso_stats = sw.run()
        pso_evals = pso_stats['evals']
        pso_time = pso_stats['t']
        c, s2, m2 = best
        if c < U and check_schedule(inst, c, s2, m2):
            U = int(c)
            s, m = list(s2), list(m2)
            pso_stats['accepted'] = 1
            ub_pso = U
            steps.append(dict(phase='pso', cmax=U, L=L, U=U))
            audit_state()

    if policy == 'adaptive':
        spread = pso_stats.get('spread', 10 ** 9) if pso_stats else 10 ** 9
        pol = 'incumbent-1' if spread <= 1 else 'binary'
    elif policy == 'adaptive-gap':
        pol = 'lower-first' if (ub0 - lb0) <= 1 else 'incumbent-1'
    elif policy == 'adaptive-init':
        pol = 'lower-first' if init in ('strong', 'mid') else 'incumbent-1'
    else:
        pol = policy
    inc_left = _inc_budget(pol)
    first = True
    probes = 0
    pact_lp = 0
    pact_cert_lp = 0
    pact_nodes = 0
    unknown = 0
    fallback = False

    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(pol, L, U, first, inc_left)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        if _inc_budget(pol) and inc_left > 0:
            inc_left -= 1
        pact_lp += r.get('lp_solves', 0)
        pact_cert_lp += r.get('cert_lp', 0)
        pact_nodes += r.get('nodes', 0)
        if r['verdict'] is False:
            L = h + 1
            lb_proof = r['proof']
            steps.append(dict(phase='probe', h=h, v=False,
                              kind=lb_proof.kind, L0=L0, U0=U0,
                              L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                s, m = list(s2), list(m2)
            steps.append(dict(phase='probe', h=h, v=True, cmax=c2,
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(phase='probe', h=h, v=None,
                              L0=L0, U0=U0, L1=L, U1=U))
            if unknown >= max_unknown:
                break
            if not fallback:
                fallback = True
                pol = 'binary'
                inc_left = 0
                first = False
        audit_state()

    final = ICFCertificate(inst, U, s, m, lb_proof) if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, s, m, lb_proof,
                                 probe=probes)
    partial_ok = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, init=init, policy=policy,
        pso=bool(pso_on), pol_used=pol,
        lb0=lb0, ub0=ub0, ub_pso=ub_pso, lb=L, ub=U, opt=U,
        certified=bool(L == U and final_ok),
        audit=final_ok, cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_cert_lp=pact_cert_lp,
        pact_nodes=pact_nodes, pin_lp=pin_lp,
        total_lp=pact_lp + pact_cert_lp + pin_lp,
        pso_evals=pso_evals, pso_time=pso_time,
        pso_stats=pso_stats,
        partial_ok=audit_ok, partial_fail=audit_fail,
        partial_final=partial_ok,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                audit_fail == 0 and partial_ok),
    )
