"""Negative result: two-child LP solves on threads are slower than sequential."""
import sys, pickle, json, time
from concurrent.futures import ThreadPoolExecutor
sys.path[:0] = ['exp/v70', 'exp/v61', 'exp/v60', 'exp/v13']
from dcs import DCS

def scopes(inst, h):
    a = DCS(inst, h, cert_on=False)
    root, _ = a.build_look(frozenset(), 500000, look_budget=8)
    return root.split, a._split_scopes(frozenset(), *root.split)

def run(inst, h, i, mid, workers, reps=5):
    scopes = [frozenset({(i, t) for t in range(mid + 1, h)}),
              frozenset({(i, t) for t in range(0, mid + 1)})]
    # split_scopes gives actual possible starts; use the same helper
    a = DCS(inst, h, cert_on=False)
    ls, rs = a._split_scopes(frozenset(), i, mid)
    scopes = [ls, rs]
    def solve(sc):
        b = DCS(inst, h, cert_on=False)
        b.solve_scope(sc)
        return b.lp_solves
    seq = []
    par = []
    for _ in range(reps):
        t0 = time.perf_counter()
        for sc in scopes:
            solve(sc)
        seq.append(time.perf_counter() - t0)
    for _ in range(reps):
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(solve, scopes))
        par.append(time.perf_counter() - t0)
    return min(seq), min(par)

def main():
    cases = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    out = {}
    for idx in (5, 47):
        inst, opt = cases[idx]; h = opt - 1
        a = DCS(inst, h, cert_on=False)
        root, _ = a.build_look(frozenset(), 500000, look_budget=8)
        i, mid = root.split
        seq, par = run(inst, h, i, mid, 2)
        out[str(idx)] = dict(split=[i, mid], seq=seq, par=par, speedup=seq / par)
        print(idx, out[str(idx)])
    json.dump(out, open('exp/v70/thread_test.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
