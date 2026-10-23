import sys, pickle, time, json, statistics
sys.path[:0] = ['exp/v42', 'exp/v41', 'exp/v31', 'exp/v30', 'exp/v29',
                'exp/v13', 'exp/v20', 'exp/v25', 'exp/v16', 'exp/v15', 'exp/v24']
import root_v42, root_v30, root_v41
from bench_matrix import load, CASES

PACE_TP = {'mint_on': False, 'hpack_on': False, 'cps_on': False}
COMBO = {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE']}
POLICY = {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'], 'pace': PACE_TP}

def run(name, inst, h, stats):
    if name == 'v30':
        return root_v30.bb_solve(inst, h, stats=stats)
    if name == 'v41':
        return root_v41.bb_solve(inst, h, stats=stats)
    cfg = COMBO if name == 'combo' else POLICY
    return root_v42.bb_solve(inst, h, cfg=cfg, stats=stats)

def main():
    sets = {k: load(v) for k, v in CASES.items()}
    solvers = ['v30', 'v41', 'combo', 'policy']
    out = {s: {} for s in solvers}
    for fam, cs in sets.items():
        times = {s: [] for s in solvers}
        ver = {s: {} for s in solvers}
        for rep in range(3):
            for s in solvers:
                t0 = time.perf_counter()
                for inst, opt in cs:
                    st = {}
                    ok, st = run(s, inst, opt - 1, st)
                    ver[s][st.get('verdict')] = ver[s].get(st.get('verdict'), 0) + 1
                times[s].append(time.perf_counter() - t0)
        for s in solvers:
            out[s][fam] = dict(med=statistics.median(times[s]), raw=times[s],
                               verdicts=ver[s])
        print(fam, {s: round(out[s][fam]['med'], 4) for s in solvers}, flush=True)
    total = {s: sum(out[s][f]['med'] for f in sets) for s in solvers}
    print('TOTAL141', {s: round(v, 4) for s, v in total.items()})
    json.dump(dict(sets=out, total=total), open('exp/v42/res_final.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
