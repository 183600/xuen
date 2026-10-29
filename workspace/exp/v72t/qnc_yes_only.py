"""Measure the YES side of the dual engine alone (v7.1 QNC).

QNC was designed as a NO engine.  This script quantifies the gap that TCA
closes: with a generous LP budget, QNC still returns UNKNOWN on several
satisfiable instances because the start-time LP is fractional and the
threshold DFS is not a complete schedule constructor.
"""
import sys, os, json, time, pickle, signal, collections
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC

class Timeout(Exception):
    pass

def _alarm(signum, frame):
    raise Timeout()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_all():
    cases = []
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
            cases.append((name, idx, inst, opt))
    return cases

def run(budget=1000, cap=20.0):
    rows = []
    for name, idx, inst, opt in load_all():
        h = opt
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, cap)
        t0 = time.perf_counter()
        try:
            q = QNC(inst, h)
            v, st = q.decide(budget=budget, nodecap=5000)
            dt = time.perf_counter() - t0
            row = dict(case=name, idx=idx, n=inst['n'], h=h, verdict=v,
                       lp=st['lp_solves'], nodes=st['nodes'], t=dt,
                       timeout=False)
        except Timeout:
            row = dict(case=name, idx=idx, n=inst['n'], h=h,
                       verdict=None, lp=None, nodes=None,
                       t=time.perf_counter() - t0, timeout=True)
        except Exception as e:
            row = dict(case=name, idx=idx, n=inst['n'], h=h,
                       verdict='ERR', lp=None, nodes=None,
                       t=time.perf_counter() - t0, timeout=False,
                       err=repr(e))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        rows.append(row)
        print(name, idx, row['verdict'], row['lp'], row['nodes'],
              round(row['t'], 3), flush=True)
    return rows

if __name__ == '__main__':
    rows = run()
    json.dump(rows, open('exp/v72t/qnc_yes_only.json', 'w'), indent=0)
    print('SUMMARY', collections.Counter(r['verdict'] for r in rows),
          'timeout', sum(r['timeout'] for r in rows),
          'lp', sum(r['lp'] or 0 for r in rows),
          't', round(sum(r['t'] for r in rows), 3))
    for r in rows:
        if r['verdict'] is not True:
            print('GAP', r)
