"""A small standard particle-swarm optimizer for policy synthesis."""
import math
import random
import time


def _clip(x, a, b):
    return a if x < a else (b if x > b else x)


class PSO:
    def __init__(self, dim, bounds, n_particles=8, iters=8, seed=0,
                 w=0.6, c1=1.5, c2=1.5, vmax=0.8):
        self.dim = dim
        self.bounds = list(bounds)
        self.n = int(n_particles)
        self.iters = int(iters)
        self.rng = random.Random(seed)
        self.w, self.c1, self.c2, self.vmax = w, c1, c2, vmax
        self.cache = {}
        self.evals = 0
        self.t_eval = 0.0
        self.history = []

    def _key(self, x):
        return tuple(round(float(v), 5) for v in x)

    def _f(self, fit, x):
        k = self._key(x)
        if k in self.cache:
            return self.cache[k]
        t = time.time()
        v = float(fit(x))
        self.t_eval += time.time() - t
        self.evals += 1
        self.cache[k] = v
        return v

    def run(self, fit, seeds=None):
        seeds = list(seeds or [])
        X, V = [], []
        for i in range(self.n):
            if i < len(seeds):
                x = [float(v) for v in seeds[i]]
            elif i == len(seeds):
                x = [self.rng.uniform(a, b) for a, b in self.bounds]
            else:
                base = seeds[self.rng.randrange(len(seeds))] if seeds else \
                    [self.rng.uniform(a, b) for a, b in self.bounds]
                x = [_clip(float(base[d]) +
                           self.rng.gauss(0.0, 0.25), *self.bounds[d])
                     for d in range(self.dim)]
            X.append(x)
            V.append([self.rng.uniform(-0.2, 0.2) for _ in range(self.dim)])

        pbest = [list(x) for x in X]
        pfit = [self._f(fit, x) for x in X]
        gi = min(range(self.n), key=lambda i: pfit[i])
        gbest, gfit = list(pbest[gi]), pfit[gi]
        self.history.append(dict(iter=0, best=gfit, evals=self.evals))

        for it in range(1, self.iters + 1):
            for i in range(self.n):
                for d in range(self.dim):
                    r1 = self.rng.random()
                    r2 = self.rng.random()
                    V[i][d] = (self.w * V[i][d]
                               + self.c1 * r1 * (pbest[i][d] - X[i][d])
                               + self.c2 * r2 * (gbest[d] - X[i][d]))
                    V[i][d] = _clip(V[i][d], -self.vmax, self.vmax)
                    X[i][d] = _clip(X[i][d] + V[i][d],
                                    self.bounds[d][0], self.bounds[d][1])
                f = self._f(fit, X[i])
                if f < pfit[i] - 1e-12:
                    pfit[i] = f
                    pbest[i] = list(X[i])
                    if f < gfit - 1e-12:
                        gfit = f
                        gbest = list(X[i])
            self.history.append(dict(iter=it, best=gfit, evals=self.evals))

        return dict(x=gbest, fit=gfit, evals=self.evals,
                    t_eval=round(self.t_eval, 2), history=self.history,
                    cache=len(self.cache))
