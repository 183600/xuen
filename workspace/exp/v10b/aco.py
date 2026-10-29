"""Compact ant-colony upper-bound constructor for scheduling instances.

Only feasible schedules are produced; the caller must replay them with
check_schedule before using them in a certificate.  Pheromone lives on
ordered task pairs (O(n^2) space), not on the time-indexed LP columns.
"""
import math
import random


def _ready(inst, done):
    return [i for i in range(inst['n'])
            if not done[i] and all(done[j] for j in inst['pred'][i])]


def _earliest(busy, base, p):
    t = base
    for a, b in busy:
        if t + p <= a:
            break
        if t < b:
            t = b
    return t


def construct(inst, rng, tau, alpha=1.0, beta=1.5, eta_mode='tail'):
    n, m, p = inst['n'], inst['m'], inst['p']
    pred, succ = inst['pred'], inst['succ']
    est, q = inst.get('_est'), inst.get('_q')
    if est is None or q is None:
        from po import heads_tails
        est, q = heads_tails(inst, 0, [0] * n)
        inst['_est'], inst['_q'] = est, q
    done = [False] * n
    starts = [None] * n
    machs = [None] * n
    busy = [[] for _ in range(m)]
    order = []
    while True:
        ready = _ready(inst, done)
        if not ready:
            break
        mass = []
        for i in ready:
            pin = 0.0
            for j in ready:
                if j != i:
                    pin += tau[j][i]
            if eta_mode == 'tail':
                eta = (q[i] + p[i]) ** 1.0
            elif eta_mode == 'lpt':
                eta = p[i]
            elif eta_mode == 'spt':
                eta = 1.0 / max(p[i], 1)
            elif eta_mode == 'slack':
                eta = 1.0 / max(1, len(inst['elig'][i]))
            else:
                eta = 1.0
            mass.append((pin ** alpha) * (eta ** beta))
        tot = sum(mass)
        i = ready[-1]
        if tot > 0:
            r = rng.random() * tot
            acc = 0.0
            for x, w in zip(ready, mass):
                acc += w
                if r <= acc:
                    i = x
                    break
        base = 0
        for j in pred[i]:
            v = starts[j] + p[j]
            if v > base:
                base = v
        best = None
        for k in inst['elig'][i]:
            t = _earliest(busy[k], base, p[i])
            cand = (t, sum(b - a for a, b in busy[k]), k)
            if best is None or cand < best:
                best = cand
        t, _, k = best
        starts[i] = t
        machs[i] = k
        busy[k].append((t, t + p[i]))
        busy[k].sort()
        done[i] = True
        order.append(i)
    if any(x is None for x in starts):
        return None
    cmax = max(starts[i] + p[i] for i in range(n))
    return starts, machs, cmax, order


class AntColony:
    def __init__(self, inst, seed=0, alpha=1.0, beta=1.5, rho=0.2,
                 tau0=1.0, eta_mode='tail'):
        self.inst = inst
        self.n = inst['n']
        self.rng = random.Random(seed)
        self.alpha, self.beta, self.rho = alpha, beta, rho
        self.tau0 = tau0
        self.eta_mode = eta_mode
        self.tau = [[tau0] * self.n for _ in range(self.n)]
        self.best = None
        self.best_order = None
        self.history = []

    def run(self, U, ants=8, gens=3, seed=None, target=None):
        if seed is not None:
            self.rng = random.Random(seed)
        inst = self.inst
        best = self.best
        best_order = self.best_order
        for g in range(gens):
            tours = []
            for a in range(ants):
                got = construct(inst, self.rng, self.tau,
                                self.alpha, self.beta, self.eta_mode)
                if got is None:
                    continue
                starts, machs, cmax, order = got
                tours.append((cmax, starts, machs, order))
                if cmax < U and (best is None or cmax < best[2]):
                    best = (starts, machs, cmax)
                    best_order = order
                    U = cmax
                if target is not None and cmax <= target:
                    self.best, self.best_order = best, best_order
                    return best, True
            if best is not None:
                for i in range(self.n):
                    for j in range(self.n):
                        if i != j:
                            self.tau[i][j] *= (1.0 - self.rho)
                # deposit on ordered pairs in the best order (precedence
                # pairs are fixed; incomparable pairs are the free choices)
                qdep = 1.0 / max(1, best[2])
                for ii in range(len(best_order)):
                    i = best_order[ii]
                    for jj in range(ii + 1, len(best_order)):
                        j = best_order[jj]
                        self.tau[i][j] += qdep
                        self.tau[j][i] = max(self.tau[j][i],
                                              self.tau0 * 0.1)
            self.history.append(U)
        self.best, self.best_order = best, best_order
        return best, (best is not None and target is not None
                      and best[2] <= target)
