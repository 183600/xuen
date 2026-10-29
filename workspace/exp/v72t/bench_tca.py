import sys, os, json, time, pickle, traceback
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from tca import TCA, check_proof

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_all():
    cases = []
    def add(name, path):
        data = pickle.load(open(os.path.join(ROOT, path), 'rb'))
        for idx, x in enumerate(data):
            if isinstance(x, dict):
                inst, opt = x['inst'], x['opt']
            else:
                inst, opt = x[0], x[1]
            cases.append((name, idx, inst, opt))
    add('holdout', 'exp/v20/holdout_cases50.pkl')
    add('synth', 'exp/v28/synth2_45.pkl')
    add('large_a', 'exp/v14/large_a.pkl')
    add('large_b', 'exp/v14/large_b.pkl')
    add('large_het', 'exp/v14/large_het.pkl')
    add('hard3', 'exp/v13/hard3.pkl')
    add('deep', 'exp/v18/deep.pkl')
    return cases

def run(cases, side, out):
    rows = []
    for name, idx, inst, opt in cases:
        h = opt if side == 'YES' else opt - 1
        t0 = time.perf_counter()
        try:
            tc = TCA(inst, h, primal_tries=100, dec_cap=200000,
                     dual_first_budget=3, dual_budget=100000,
                     dual_nodecap=5000)
            v, st = tc.decide()
            dt = time.perf_counter() - t0
            row = dict(case=name, idx=idx, n=inst['n'], m=inst['m'], h=h,
                       verdict=v, engine=st.get('engine'), t=dt,
                       lp=st.get('lp'), nodes=st.get('nodes'),
                       sched_ok=None, proof_ok=None, proof_stats=None,
                       err=None)
            if v is True:
                row['sched_ok'] = True
            elif v is False:
                pv, why, pst = check_proof(inst, h, st['proof'])
                row['proof_ok'] = (pv == 'NO')
                row['proof_stats'] = pst
                row['proof_why'] = why
            rows.append(row)
        except Exception as e:
            dt = time.perf_counter() - t0
            rows.append(dict(case=name, idx=idx, n=inst['n'], m=inst['m'],
                             h=h, verdict='ERR', engine=None, t=dt,
                             lp=None, nodes=None, sched_ok=None,
                             proof_ok=None, proof_stats=None,
                             err='%s: %s' % (type(e).__name__, e),
                             trace=traceback.format_exc()))
        print(out, side, name, idx, rows[-1]['verdict'],
              rows[-1]['engine'], rows[-1]['t'], flush=True)
    json.dump(rows, open(out, 'w'), indent=0)
    return rows

if __name__ == '__main__':
    cases = load_all()
    print('cases', len(cases))
    side = sys.argv[1] if len(sys.argv) > 1 else 'NO'
    out = sys.argv[2] if len(sys.argv) > 2 else 'exp/v72t/tca_%s.json' % side
    run(cases, side, out)
