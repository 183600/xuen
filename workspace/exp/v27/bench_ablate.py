"""Ablations for BFS-PC: ER test, clique test, anytime lower bound."""
import sys, json, time, signal, pickle
sys.path.insert(0, 'exp/v27')
sys.path.insert(0, 'exp/v25')
import bfs_pc as B


class TO(Exception):
    pass


def _alarm(sig, frm):
    raise TO()


signal.signal(signal.SIGALRM, _alarm)


def run(inst, h, budget=3000, er=True, clique=False, nodecap=300000, tl=8):
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = B.bfs_pc(inst, h, budget=budget, er=er, clique=clique,
                     nodecap=nodecap, stats=st)
        ok = True
    except TO:
        r, ok = None, False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    st['time'] = round(time.time() - t, 3)
    st['timeout'] = not ok
    st['verdict'] = 'NO' if r is False else ('YES' if r is True else 'UNK')
    return st


def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    cfgs = [('base', dict(er=False, clique=False)),
            ('er', dict(er=True, clique=False)),
            ('er_clique', dict(er=True, clique=True))]
    out = {}
    for name, kw in cfgs:
        rows = []
        for idx, (inst, opt) in enumerate(d):
            st = run(inst, opt - 1, **kw)
            rows.append(dict(idx=idx, **{k: st.get(k) for k in
                                         ('verdict', 'nodes', 'cut', 'plc',
                                          'S', 'L', 'time', 'timeout')}))
        out[name] = rows
        print(name, 'NO', sum(r['verdict'] == 'NO' for r in rows),
              'TO', sum(r['timeout'] for r in rows),
              'cut', sum(r['cut'] or 0 for r in rows),
              'nodes', sum(r['nodes'] or 0 for r in rows),
              'time', round(sum(r['time'] for r in rows), 1), flush=True)

    # anytime lower bound on a few instances
    lb = []
    for idx in [1, 4, 42]:
        inst, opt = d[idx]
        row = {'idx': idx, 'budget': []}
        for b in (1, 2, 3, 5, 10, 30):
            st = run(inst, opt - 1, budget=b, er=True)
            row['budget'].append(dict(b=b, verdict=st['verdict'],
                                      lb=st.get('lb_size'),
                                      lbd=st.get('lb_depth'),
                                      cut=st.get('cut'),
                                      nodes=st.get('nodes')))
        lb.append(row)
        print('LB', row, flush=True)
    json.dump({'ablate': out, 'lb': lb},
              open('exp/v27/res_ablate.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
