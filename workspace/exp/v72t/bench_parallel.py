"""Data-parallel TCA portfolio: instances are independent jobs.

The theoretical parallel model is a portfolio of lanes; the practical
experiment distributes whole instances over processes.  Both are
embarrassingly parallel, which is the point: certificate checking makes
parallel results mergeable without trust.
"""
import sys, os, json, time, pickle, collections
from concurrent.futures import ProcessPoolExecutor
sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
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

def work(args):
    name, idx, inst, h = args
    sys.setrecursionlimit(100000)
    sys.path[:0] = ['exp/v72t', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
    from tca import TCA
    t0 = time.perf_counter()
    v, st = TCA(inst, h, primal_tries=100).decide()
    return name, idx, v, st.get('engine'), time.perf_counter() - t0

def main():
    cases = load_all()
    for side, dh in [('NO', -1), ('YES', 0)]:
        tasks = [(n, i, inst, opt + dh) for (n, i, inst, opt) in cases]
        t0 = time.perf_counter()
        serial = [work(x) for x in tasks]
        tser = time.perf_counter() - t0
        out = dict(side=side, n=len(tasks), serial=tser,
                   verdicts=dict(collections.Counter(str(x[2]) for x in serial)),
                   engines=dict(collections.Counter(x[3] for x in serial)))
        for w in [4, 8]:
            t0 = time.perf_counter()
            with ProcessPoolExecutor(max_workers=w) as ex:
                rows = list(ex.map(work, tasks, chunksize=4))
            tw = time.perf_counter() - t0
            out['w%d' % w] = dict(wall=tw, speedup=tser / tw,
                                  verdicts=dict(collections.Counter(
                                      str(x[2]) for x in rows)))
            print(side, 'workers', w, 'wall', round(tw, 3),
                  'speedup', round(tser / tw, 2), flush=True)
        print(side, 'serial', round(tser, 3), out['verdicts'], out['engines'],
              flush=True)
        json.dump(out, open('exp/v72t/parallel_%s.json' % side, 'w'), indent=0)

if __name__ == '__main__':
    main()
