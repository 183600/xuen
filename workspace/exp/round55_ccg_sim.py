#!/usr/bin/env python3
"""Round 55 mechanism simulations: concurrent speculation, leases, staleness.

Pure-stdlib toy simulations used to falsify three intuitions:
  1. more concurrent branches => higher correctness (E162: it does not);
  2. optimistic concurrency is enough (E163: hard leases needed for safety);
  3. stale action chunks are negligible (E164: they are not).

Writes round55_ccg_results.json next to this file.
"""
import json
import os
import random
import statistics


def gauss(mu=0.0, sigma=1.0):
    return random.gauss(mu, sigma)


def exp_a(trials=20000, ks=(1, 2, 4, 8, 16), shared_bias=0.35,
          eps_sd=0.5, tol=0.25, seed=20261111):
    rng = random.Random(seed)
    out = {}
    for k in ks:
        succ = 0
        agree = 0
        spread = []
        for _ in range(trials):
            true = 0.0
            vals = [true + shared_bias + rng.gauss(0, eps_sd) for _ in range(k)]
            cons = sum(vals) / k
            if abs(cons - true) <= tol:
                succ += 1
            sd = statistics.pstdev(vals) if k > 1 else 0.0
            spread.append(sd)
            if sd <= tol:
                agree += 1
        out[k] = dict(success=succ / trials,
                      agreement=agree / trials,
                      mean_spread=statistics.mean(spread))
    return out


def _make_world(rng, n, m):
    objs = []
    for _ in range(m):
        w = rng.choice([1, 1, 2, 2, 3])
        k = rng.randint(2, min(n, 3))
        elig = tuple(sorted(rng.sample(range(n), k)))
        objs.append([w, elig])
    return objs


def exp_b(n=4, m=24, delay=2, protocol='parallel', fail_agent=0,
          fail_at=3, lease=3, t_cap=300, trials=300, seed=11):
    rng = random.Random(seed)
    makes, conflicts = [], 0
    used = 0
    for _ in range(trials):
        objs = _make_world(rng, n, m)
        rem = [o[0] for o in objs]
        elig = [o[1] for o in objs]
        owner = [None] * m
        otime = [0] * m
        if protocol in ('lock', 'lease'):
            load = [0] * n
            for oi in range(m):
                a = min(elig[oi], key=lambda x: (load[x], x))
                owner[oi] = a
                load[a] += rem[oi]
        reserve = {}
        t = 0
        made = None
        while t < t_cap:
            alive = [a for a in range(n) if not (a == fail_agent and t >= fail_at)]
            if protocol == 'lease' and t >= fail_at:
                for oi in range(m):
                    if owner[oi] == fail_agent and t - otime[oi] >= lease:
                        cand = [a for a in alive if a in elig[oi]]
                        if cand:
                            owner[oi] = rng.choice(cand)
                            otime[oi] = t
            picks = [None] * n
            for a in alive:
                cand = [oi for oi in range(m) if rem[oi] > 0 and a in elig[oi]]
                if protocol in ('lock', 'lease'):
                    cand = [oi for oi in cand if owner[oi] == a]
                elif protocol == 'occ':
                    view = {oi for oi, (s, b) in reserve.items()
                            if b != a and t - s <= delay}
                    cc = [oi for oi in cand if oi not in view]
                    cand = cc if cc else []
                if cand:
                    picks[a] = rng.choice(cand)
            by_obj = {}
            for a, oi in enumerate(picks):
                if oi is not None:
                    by_obj.setdefault(oi, []).append(a)
            for oi, agents in by_obj.items():
                if len(agents) > 1:
                    conflicts += len(agents) - 1
                a = rng.choice(agents)
                rem[oi] -= 1
                reserve[oi] = (t, a)
                otime[oi] = t
            used += sum(1 for p in picks if p is not None)
            used += sum(len(v) - 1 for v in by_obj.values() if len(v) > 1)
            if all(r == 0 for r in rem):
                made = t + 1
                break
            t += 1
        makes.append(made if made else t_cap)
    return dict(conflict_rate=conflicts / max(1, used),
                makespan=statistics.mean(makes),
                p95=sorted(makes)[int(0.95 * len(makes)) - 1],
                stalled=sum(1 for x in makes if x >= t_cap) / len(makes))


def exp_c(trials=20000, sigmas=(0, 1, 2, 4, 8), tol=0.2, seed=20261111):
    rng = random.Random(seed)
    out = {}
    for s in sigmas:
        raw_succ = 0
        corr_succ = 0
        for _ in range(trials):
            v = rng.uniform(0, 1.5)
            acc = rng.uniform(-0.2, 0.2)
            true_pos = v * s + 0.5 * acc * s * s
            if abs(true_pos) <= tol:
                raw_succ += 1
            if abs(true_pos - v * s) <= tol:
                corr_succ += 1
        out[s] = dict(raw=raw_succ / trials,
                      velocity_corrected=corr_succ / trials)
    return out


def main():
    results = dict(
        expA=exp_a(),
        expB={
            'no_failure': {
                p: exp_b(protocol=p, fail_at=10 ** 9)
                for p in ('parallel', 'occ', 'lock')
            },
            'agent0_failure_t3': {
                p: exp_b(protocol=p)
                for p in ('parallel', 'occ', 'lock', 'lease')
            },
        },
        expC=exp_c(),
    )
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'round55_ccg_results.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
