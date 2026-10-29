"""Fair wall-clock comparison QNC v7.1 vs QUC v7.2 on the 201 NO cases."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from quc import QUC
from qnc import QNC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def main():
    cases = []
    for name, f in FILES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            cases.append((name, idx, inst, opt - 1))
    pert = pickle.load(open('exp/v71/perturb60.pkl', 'rb'))
    for (name, k, inst, opt, an, al) in pert:
        cases.append((name, k, inst, opt - 1))
    tq = tqc = 0.0
    rows = []
    for name, idx, inst, h in cases:
        t0 = time.time(); a = QNC(inst, h); va, sa = a.decide(); ta = time.time() - t0
        t0 = time.time(); b = QUC(inst, h); vb, sb = b.decide(); tb = time.time() - t0
        tq += ta; tqc += tb
        rows.append(dict(name=name, idx=idx, qnc_v=va, quc_v=vb,
                         qnc_lp=sa['lp_solves'], quc_lp=sb['lp_solves'],
                         qnc_nodes=sa['nodes'], quc_nodes=sb['nodes'],
                         qnc_t=ta, quc_t=tb, audit=b.audit_quc(),
                         trap=sb['trap']))
    out = dict(n=len(rows), qnc_t=tq, quc_t=tqc,
               qnc_no=sum(r['qnc_v'] is False for r in rows),
               quc_no=sum(r['quc_v'] is False for r in rows),
               audit=sum(r['audit'] for r in rows),
               rows=rows)
    json.dump(out, open('exp/v72/time.json', 'w'), indent=1)
    print({k: v for k, v in out.items() if k != 'rows'})
    for r in rows:
        if r['trap'] is not None:
            print('branch', r['name'], r['idx'], 'qnc', round(r['qnc_t'], 3),
                  'quc', round(r['quc_t'], 3), 'lp', r['qnc_lp'], r['quc_lp'],
                  'nodes', r['qnc_nodes'], r['quc_nodes'], 'trap', r['trap'])


if __name__ == '__main__':
    main()
