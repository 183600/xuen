import sys, os, json, time, pickle, collections
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from tca import greedy_schedule, dec_schedule, ProofQNC, check_proof
from qnc import QNC
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_all():
    out = []
    for name, path in [
        ('holdout', 'exp/v20/holdout_cases50.pkl'),
        ('synth', 'exp/v28/synth2_45.pkl'),
        ('large_a', 'exp/v14/large_a.pkl'),
        ('large_b', 'exp/v14/large_b.pkl'),
        ('large_het', 'exp/v14/large_het.pkl'),
        ('hard3', 'exp/v13/hard3.pkl'),
        ('deep', 'exp/v18/deep.pkl')]:
        data = pickle.load(open(os.path.join(ROOT, path), 'rb'))
        for idx, x in enumerate(data):
            if isinstance(x, dict):
                inst, opt = x['inst'], x['opt']
            else:
                inst, opt = x[0], x[1]
            out.append((name, idx, inst, opt))
    return out

def main():
    cases = load_all()
    res = {}
    # greedy on YES
    rows = []
    for name, idx, inst, opt in cases:
        t = time.perf_counter()
        s, why = greedy_schedule(inst, opt, tries=100)
        rows.append(dict(case=name, idx=idx, ok=s is not None,
                         why=why, t=time.perf_counter() - t))
    res['greedy_yes'] = rows
    print('greedy YES', collections.Counter(r['ok'] for r in rows),
          round(sum(r['t'] for r in rows), 3), flush=True)
    # DEC on YES and NO
    for side, dh in [('yes', 0), ('no', -1)]:
        rows = []
        for name, idx, inst, opt in cases:
            t = time.perf_counter()
            s, st = dec_schedule(inst, opt + dh, nodecap=200000)
            rows.append(dict(case=name, idx=idx, yes=s is not None,
                             nodes=st.get('nodes'), timeout=st.get('timeout'),
                             t=time.perf_counter() - t))
        res['dec_' + side] = rows
        print('DEC', side, collections.Counter(r['yes'] for r in rows),
              'nodes', sum(r['nodes'] or 0 for r in rows),
              't', round(sum(r['t'] for r in rows), 3),
              'timeouts', sum(bool(r['timeout']) for r in rows), flush=True)
    # QNC-only NO
    rows = []
    for name, idx, inst, opt in cases:
        t = time.perf_counter()
        q = QNC(inst, opt - 1)
        v, st = q.decide(budget=100000, nodecap=5000)
        dt = time.perf_counter() - t
        pv, why, pst = check_proof(inst, opt - 1,
                                   dict(nodes=q.pnodes, forces=q.forces, root=0)) \
            if hasattr(q, 'pnodes') else (None, None, None)
        rows.append(dict(case=name, idx=idx, verdict=v,
                         lp=st['lp_solves'], nodes=st['nodes'], t=dt))
    res['qnc_no'] = rows
    print('QNC NO', collections.Counter(r['verdict'] for r in rows),
          'lp', sum(r['lp'] for r in rows),
          'nodes', sum(r['nodes'] for r in rows),
          't', round(sum(r['t'] for r in rows), 3), flush=True)
    json.dump(res, open('exp/v72t/engines.json', 'w'), indent=0)

if __name__ == '__main__':
    main()
