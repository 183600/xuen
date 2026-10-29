import sys, pickle, time
sys.path[:0] = ['exp/v82', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from fullqnc import FullQNC

def run(inst, h, cuts, budget=100000):
    q = FullQNC(inst, h)
    q.lp.cuts = list(cuts)
    q.lp.cutset = set(cuts)
    t0 = time.time()
    v, st = q.decide(budget, 5000, 60, 100)
    return v, st, q, time.time() - t0

def greedy(inst, h, verbose=False):
    q0 = FullQNC(inst, h)
    rows = list(q0.lp.cuts)
    v, st, q, t = run(inst, h, rows)
    assert v is False and q.audit() and q.cert_fail == 0, (v, q.audit(), q.cert_fail)
    best_lp, best_rows, best_t = st['lp_solves'], rows, t
    n0 = len(rows)
    for r in list(rows):
        trial = [x for x in best_rows if x != r]
        v2, st2, q2, t2 = run(inst, h, trial)
        if (v2 is False and q2.audit() and q2.cert_fail == 0
                and st2['lp_solves'] <= best_lp):
            best_rows, best_lp, best_t = trial, st2['lp_solves'], t2
            if verbose:
                print('  drop', r, 'rows', len(best_rows), 'lp', best_lp, 't', round(t2, 3))
    return dict(n0=n0, n1=len(best_rows), lp=best_lp, t=best_t,
                rows=best_rows)

if __name__ == '__main__':
    FILES = {'holdout50': 'exp/v20/holdout_cases50.pkl'}
    def load(f):
        d = pickle.load(open(f, 'rb'))
        return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]
    d = load('exp/v20/holdout_cases50.pkl')
    for idx in [5, 47]:
        inst, opt = d[idx]; h = opt - 1
        r = greedy(inst, h)
        print('holdout50', idx, 'rows', r['n0'], '->', r['n1'], 'lp', r['lp'], 't', round(r['t'], 3))
    for (name, k, inst, opt, an, al) in pickle.load(open('exp/v71/perturb60.pkl', 'rb')):
        if name == 'h47' and k == 6:
            r = greedy(inst, opt - 1)
            print('h47-p6', 'rows', r['n0'], '->', r['n1'], 'lp', r['lp'], 't', round(r['t'], 3))
    d = load('exp/v14/large_b.pkl')
    for idx in [4, 7]:
        inst, opt = d[idx]; h = opt - 1
        r = greedy(inst, h)
        print('large_b', idx, 'rows', r['n0'], '->', r['n1'], 'lp', r['lp'], 't', round(r['t'], 3))
