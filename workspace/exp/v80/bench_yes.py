"""YES-side soundness probe at h=OPT with a hard per-case cap.

The inherited v6.1 median branch can fail to make progress when the median
falls on an already-forbidden start time (the 'hi' child then forbids
nothing and the bounds repeat).  We therefore cap nodes and wall time per
case instead of trusting the recursion to terminate.
"""
import sys, pickle, json, time, signal
sys.setrecursionlimit(100000)
sys.path[:0] = ['exp/v80', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qcm import QCM
FILES = {'holdout50': 'exp/v20/holdout_cases50.pkl',
 'synth45': 'exp/v28/synth2_45.pkl', 'large_a': 'exp/v14/large_a.pkl',
 'large_b': 'exp/v14/large_b.pkl', 'large_het': 'exp/v14/large_het.pkl',
 'hard3': 'exp/v13/hard3.pkl', 'deep8': 'exp/v18/deep.pkl'}
def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]
def handler(s, f):
    raise TimeoutError
signal.signal(signal.SIGALRM, handler)
rows = []
for name, f in FILES.items():
    for idx, (inst, opt) in enumerate(load(f)):
        signal.alarm(5)
        t = time.time()
        try:
            q = QCM(inst, opt)
            v, st = q.decide(nodecap=30, max_rounds=20)
            rows.append(dict(name=name, idx=idx, v=v, why=st['why'],
                             cover=st['cover_lp'], nodes=st['nodes']))
        except TimeoutError:
            rows.append(dict(name=name, idx=idx, v='timeout', why='timeout',
                             cover=0, nodes=30))
        except Exception as e:
            rows.append(dict(name=name, idx=idx, v='error',
                             why=type(e).__name__, cover=0, nodes=0))
        finally:
            signal.alarm(0)
json.dump(rows, open('exp/v80/yes_check.json', 'w'), indent=1)
from collections import Counter
print(Counter((r['v'], r['why']) for r in rows))
print('cover stops', sum(r['cover'] for r in rows),
      'false NO', sum(r['v'] is False for r in rows))
