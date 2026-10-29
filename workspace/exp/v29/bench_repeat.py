"""Stable timing: v2.4 vs v2.5, 3 repetitions, same process."""
import sys, time, json, pickle, statistics
sys.path[:0] = ['exp/v28', 'exp/v29', 'exp/v13', 'exp/v15', 'exp/v16',
                'exp/v20', 'exp/v24', 'exp/v25']
import root_pc, root_bb


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]


def bench(fn, cases, reps=3):
    ts = []
    for _ in range(reps):
        t0 = time.time()
        for inst, opt in cases:
            fn(inst, opt - 1)
        ts.append(time.time() - t0)
    return [round(t, 4) for t in ts], round(statistics.median(ts), 4)


def main():
    cs = load('exp/v20/holdout_cases50.pkl')
    core = load('exp/v13/hard3.pkl') + load('exp/v14/large_a.pkl') + \
        load('exp/v14/large_b.pkl') + load('exp/v14/large_het.pkl')
    out = {}
    for name, cases in [('holdout50', cs), ('core38', core)]:
        for tag, fn in [('v24', root_pc.pc_solve), ('v25', root_bb.bb_solve)]:
            out[name + '_' + tag] = bench(fn, cases)
            print(name, tag, out[name + '_' + tag], flush=True)
    json.dump(out, open('exp/v29/res_repeat.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
