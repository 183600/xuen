"""Candidate-split race: rank of the first closing split under orders."""
import sys, pickle, json, random, math
sys.path[:0] = ['exp/v70', 'exp/v61', 'exp/v60', 'exp/v13']
from dcs import DCS

def candidate_table(inst, h):
    a = DCS(inst, h)
    res, z = a.solve_scope(frozenset())
    jobs = sorted(set(a.lp.cols[c][0] for c in range(a.N)
                      if 1e-7 < z[c] < 1 - 1e-7))
    tab = []
    for i in jobs:
        times = sorted(set(k[-1] for k in a.lp.idx if k[0] == i))
        for mid in times[:-1]:
            ls, rs = a._split_scopes(frozenset(), i, mid)
            rl, _ = a.solve_scope(ls)
            rr, _ = a.solve_scope(rs)
            tab.append(dict(i=i, mid=mid,
                            close=(rl.status == 2 and rr.status == 2)))
    return a, tab

def waves(order, B):
    for k in range(0, len(order), B):
        batch = order[k:k + B]
        if any(c['close'] for c in batch):
            return (k // B) + 1, min(k + B, len(order))
    return None, len(order)

def main():
    cases = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    out = {}
    random.seed(0)
    for idx in [5, 47]:
        inst, opt = cases[idx]
        a, tab = candidate_table(inst, opt - 1)
        N = len(tab); C = sum(c['close'] for c in tab)
        # critical-path order
        res, z = a.solve_scope(frozenset())
        crit = a._candidates(z)
        rank_crit = None
        for k, (i, mid) in enumerate(crit):
            if any(c['i'] == i and c['mid'] == mid and c['close'] for c in tab):
                rank_crit = k + 1
                break
        # ALC default split
        i0, m0 = a._pick(z)
        alc_close = any(c['i'] == i0 and c['mid'] == m0 and c['close']
                        for c in tab)
        # random order statistics
        trials = 20000
        ranks = []
        wave_stats = {B: [0, 0.0] for B in (1, 2, 4, 8)}
        for _ in range(trials):
            order = list(range(N)); random.shuffle(order)
            labels = [tab[j]['close'] for j in order]
            r = next(k + 1 for k, x in enumerate(labels) if x)
            ranks.append(r)
            for B in wave_stats:
                w, ev = waves([tab[j] for j in order], B)
                wave_stats[B][0] += w
                wave_stats[B][1] += ev
        out[idx] = dict(
            N=N, closing=C, crit_rank=rank_crit,
            alc_split=[i0, m0], alc_close=alc_close,
            random_expected_rank=sum(ranks) / trials,
            random_theory=(N + 1) / (C + 1),
            waves={str(B): dict(mean_waves=v[0] / trials,
                                mean_candidates=v[1] / trials)
                   for B, v in wave_stats.items()},
        )
        print(idx, out[idx])
    json.dump(out, open('exp/v70/candidate_race.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
