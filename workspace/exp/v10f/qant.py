"""v10.0 QANT: quantum-inspired amplitude scheduling on the BAM frontier.

QANT keeps the v9.0 ICF invariant and the v10.0 BAM live frontier.  It
changes only the *untrusted search policy*:

  * leaf selection is a Born-rule sample over open boxes,
        p(f) = |a_f|^2 / sum_g |a_g|^2,
        a_f = exp(-beta (L_f - L_min)/2) * (1 + eta * width_f)
              * (1 + gamma * pheromone_f),
    where width_f is the residual box width and pheromone_f is the
    ant-colony mass on the jobs of f.  This is a classical sampler; the
    quantum analogy is the amplitude/square rule, not a runtime claim.

  * ACO is gated by a benchmark-calibrated rule: run it only when the
    initial bracket has gap 1 (where a feasible schedule at L closes the
    bracket immediately).  Gap 0 needs no primal; gap >= 2 is where the
    sampled ACO in the 252-instance corpus never improved U.

The trusted kernel is unchanged: only pact_decide / cert.verify produce
NO leaves, only check_schedule accepts schedules, and every emitted
certificate is the same FrontierProof/BAMCertificate as BAM.
"""
import math
import random
import sys

sys.path[:0] = ['exp/v10f', 'exp/v10b', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from bam import BAM, run_bam


class QANT(BAM):
    def __init__(self, inst, **kw):
        kw.setdefault('selector', 'amp')
        kw.setdefault('aco_gate', 'gap1')
        self.aco_pilot = kw.pop('aco_pilot', False)
        self.aco_pilot_ants = int(kw.pop('aco_pilot_ants', 4))
        self.aco_pilot_gens = int(kw.pop('aco_pilot_gens', 1))
        super().__init__(inst, **kw)
        self.rng = random.Random(self.amp_seed)
        self.stats['amp_picks'] = 0
        self.stats['amp_unique'] = 0

    def _seed_aco(self, U, starts, machine):
        if not self.use_aco:
            return None
        from aco import AntColony
        aco = AntColony(self.inst, seed=self.aco_seed, rho=0.2)
        order = sorted(range(self.inst['n']), key=lambda i: (starts[i], i))
        dep = 1.0 / max(1, U)
        for ii in range(len(order)):
            for jj in range(ii + 1, len(order)):
                a, b = order[ii], order[jj]
                if b in self.inst['succ'][a]:
                    continue
                aco.tau[a][b] += dep
        self.aco = aco
        target = getattr(self, 'L', None)
        if self.aco_pilot:
            best, hit = aco.run(U, ants=self.aco_pilot_ants,
                                gens=self.aco_pilot_gens, target=target)
            self.stats['aco_calls'] += 1
            if best is None or best[2] >= U:
                return None
            U = best[2]
        best, hit = aco.run(U, ants=self.aco_ants, gens=self.aco_gens,
                            target=target)
        self.stats['aco_calls'] += 1
        if best is not None and best[2] < U:
            self.stats['aco_best'] = best[2]
            return best
        return None

    def _leaf_width(self, f):
        return sum(f.hi[i] - f.lo[i] + 1 for i in range(self.inst['n']))

    def _leaf_ant(self, f):
        aco = getattr(self, 'aco', None)
        if aco is None:
            return 0.0
        tau = aco.tau
        n = self.inst['n']
        vals = []
        for i in range(n):
            s = 0.0
            for j in range(n):
                if i != j:
                    s += tau[i][j] + tau[j][i]
            vals.append(s)
        mx = max(vals) if vals else 0.0
        if mx <= 0:
            return 0.0
        # average normalized pheromone over jobs, then over the box
        return sum(v / mx for v in vals) / max(1, n)

    def _select_leaf(self, openf):
        if self.selector == 'astar':
            return super()._select_leaf(openf)
        Lmin = min(f.L for f in openf)
        if len(openf) == 1:
            self.stats['amp_picks'] += 1
            return openf[0]
        if self.selector == 'amp_tb':
            openf = [f for f in openf if f.L == Lmin]
            if len(openf) == 1:
                self.stats['amp_picks'] += 1
                return openf[0]
        elif self.selector == 'amp_cap' and len(openf) > 4:
            self.stats['amp_picks'] += 1
            return min(openf, key=lambda x: (x.L, -x.depth, -x.created))
        widths = [self._leaf_width(f) for f in openf]
        wmax = max(widths) if widths else 1
        aco = self._leaf_ant(openf[0])
        weights = []
        for f, w in zip(openf, widths):
            amp = math.exp(-0.5 * self.amp_beta * (f.L - Lmin))
            amp *= (1.0 + self.amp_eta * (w / max(1, wmax)))
            amp *= (1.0 + self.amp_gamma * aco)
            weights.append(amp * amp)
        tot = sum(weights)
        r = self.rng.random() * tot
        acc = 0.0
        pick = openf[-1]
        for f, w in zip(openf, weights):
            acc += w
            if r <= acc:
                pick = f
                break
        self.stats['amp_picks'] += 1
        return pick


def run_qant(inst, known, name, idx, **kw):
    co = QANT(inst, **kw)
    co.name, co.idx, co.known = name, idx, known
    r = co.run()
    r.update(name=name, idx=idx, known=known)
    return r
