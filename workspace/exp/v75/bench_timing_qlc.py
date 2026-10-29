"""Split solve/audit timing for QNC/QCC/QLC (cover included)."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v75', 'exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from qcc import QCC
from qlc import QLC
from bench_qlc import corpus, perturb, branch51

METHODS = [
    ('qnc', QNC, {}),
    ('qcc', QCC, dict(use_cover=True, cover_min_k=1)),
    ('qlc', QLC, dict(use_cover=True, cover_min_k=1)),
]


def run(cases):
    out = {}
    for tag, cls, kw in METHODS:
        solve_t = audit_t = 0.0
        lp = nodes = cover = 0
        audit_ok = 0
        for name, idx, inst, h in cases:
            q = cls(inst, h, **kw)
            t0 = time.time()
            v, st = q.decide(budget=30000, nodecap=10000)
            solve_t += time.time() - t0
            t0 = time.time()
            ok = q.audit()
            audit_t += time.time() - t0
            lp += st.get('lp_solves', 0)
            nodes += st.get('nodes', 0)
            cover += st.get('cover_calls', 0)
            audit_ok += int(ok)
        out[tag] = dict(solve_t=round(solve_t, 3),
                        audit_t=round(audit_t, 3),
                        total_t=round(solve_t + audit_t, 3),
                        lp=lp, nodes=nodes, cover=cover,
                        total_lp=lp + cover, audit_ok=audit_ok,
                        n=len(cases))
    return out


if __name__ == '__main__':
    out = {}
    for tag, cases in [('corpus201', corpus() + perturb()),
                       ('branch51', branch51())]:
        out[tag] = run(cases)
        print(tag, out[tag], flush=True)
    json.dump(out, open('exp/v75/timing_qlc.json', 'w'), indent=1)
    print('saved exp/v75/timing_qlc.json')
