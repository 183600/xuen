"""v8.2 PACT: controlled UNKNOWN-injection experiment.

The oracle is wrapped by an independent Bernoulli coin: with probability
p the call returns UNKNOWN without running CHD.  Otherwise it runs the
real CHD.  The bracket must still terminate and certify; the query count
should follow the geometric prediction Q ~ Q0/(1-p), because each
decisive query is preceded by a geometric number of UNKNOWNs.
"""
import sys
import json
import random
import statistics

sys.path[:0] = ['exp/v8d', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']

from chip import base_corpus, pert_corpus, stress_corpus
from pact import PACT, potential_trace


ZERO = dict(why='injected-unknown', lp_solves=0, nodes=0, yes_nodes=0,
            mc_evals=0, schedule=None, machine=None, yes_ok=False,
            phase='injected')


class InjectedUnknownPACT(PACT):
    def __init__(self, inst, unknown_p=0.0, coin_seed=0, **kw):
        self.unknown_p = unknown_p
        self.coin_seed = coin_seed
        self.coin_calls = 0
        super().__init__(inst, **kw)

    def _decide(self, h):
        self.coin_calls += 1
        rng = random.Random(self.coin_seed * 1000003 + self.coin_calls)
        if rng.random() < self.unknown_p:
            return None, dict(ZERO), None
        return super()._decide(h)


def subset():
    out = []
    for tag, rows, take in [('base', base_corpus(), 10),
                            ('pert', pert_corpus(), 10),
                            ('stress', stress_corpus(), 10)]:
        for rec in rows[:take]:
            if tag == 'stress':
                idx, opt, inst = rec
            else:
                _, idx, inst, opt = rec
            out.append((tag, idx, inst, opt))
    return out


def run(inst, opt, p, seed):
    co = InjectedUnknownPACT(inst, unknown_p=p, coin_seed=seed,
                             K=32, seed=20261024,
                             unknown_retries=0, max_queries=300,
                             unknown_budget=200)
    r = co.optimize()
    final_unknown = sum(1 for t in r['trace']
                        if t['h'] == opt - 1 and t['v'] is None)
    return dict(q=r['queries'], u=r['unknown'], cert=r['certified'],
                opt=r['opt'], known=opt,
                final_unknown=final_unknown,
                pot=potential_trace(r['trace'], r['opt']),
                q0=None)


def main():
    rows = subset()
    out = []
    for tag, idx, inst, opt in rows:
        base = run(inst, opt, 0.0, 0)
        base['q0'] = base['q']
        out.append(dict(tag=tag, idx=idx, p=0.0, seed=0, **base))
        for p in (0.25, 0.50):
            for seed in range(5):
                r = run(inst, opt, p, seed)
                r['q0'] = base['q']
                r['ratio'] = r['q'] / max(1, base['q'])
                out.append(dict(tag=tag, idx=idx, p=p, seed=seed, **r))
        print(tag, idx, 'done', flush=True)

    json.dump(out, open('exp/v8d/bench_pact_unknown.json', 'w'), indent=1)
    print('\n== by p')
    for p in (0.0, 0.25, 0.50):
        rs = [r for r in out if r['p'] == p]
        qs = [r['q'] for r in rs]
        us = [r['u'] for r in rs]
        ratios = [r.get('ratio', 1.0) for r in rs]
        print('p', p, 'n', len(rs),
              'cert', sum(bool(r['cert']) for r in rs),
              'q_sum', sum(qs), 'u_sum', sum(us),
              'q_mean', round(statistics.mean(qs), 3),
              'ratio_mean', round(statistics.mean(ratios), 3),
              'ratio_max', round(max(ratios), 3),
              'pot', sum(bool(r['pot']) for r in rs),
              'final_unknown', sum(r['final_unknown'] for r in rs))
    print('\n== geometric check (p>0)')
    for p in (0.25, 0.50):
        rs = [r for r in out if r['p'] == p]
        # Each instance contributes 5 seeds; compare the mean over seeds
        # to the prediction Q0/(1-p).
        pred = [r['q0'] / (1 - p) for r in rs]
        obs = [r['q'] for r in rs]
        print('p', p, 'mean_obs', round(statistics.mean(obs), 3),
              'mean_pred', round(statistics.mean(pred), 3),
              'max_obs', max(obs), 'max_pred', round(max(pred), 3))


if __name__ == '__main__':
    main()
