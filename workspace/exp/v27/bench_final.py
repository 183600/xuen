"""Final held-out comparison: v2.2 CPS vs v2.3 BFS-PC at h=OPT-1 and h=OPT."""
import sys, json, time, signal, pickle
sys.path.insert(0, 'exp/v27')
sys.path.insert(0, 'exp/v25')
import bfs_pc as B
import cps_lib as C


class TO(Exception):
    pass


def _alarm(sig, frm):
    raise TO()


signal.signal(signal.SIGALRM, _alarm)


def timed(fn, tl):
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = fn()
        ok = True
    except TO:
        r, ok = None, False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return r, ok, time.time() - t


def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    rows = []
    for idx, (inst, opt) in enumerate(d):
        row = {'idx': idx, 'n': inst['n'], 'm': inst['m'], 'opt': opt}
        # baseline CPS at h=OPT-1
        st = {}
        def f1():
            return C.cps_certify(inst, (1 << inst['n']) - 1, (0,) * inst['m'],
                                 [0] * inst['n'], B.tails(inst), opt - 1,
                                 tau=10 ** 9, nodecap=300000, stats=st)
        r1, ok1, t1 = timed(f1, 20)
        row['cps'] = dict(v='NO' if r1 is False else ('YES' if r1 is True else 'UNK'),
                          ok=ok1, plc=st.get('cps_placements'),
                          rn=st.get('cps_res_nodes'), t=round(t1, 3),
                          S=st.get('cps_S'), L=st.get('cps_len'))
        # BFS-PC at h=OPT-1
        st2 = {}
        def f2():
            return B.bfs_pc(inst, opt - 1, budget=3000, nodecap=300000,
                            stats=st2)
        r2, ok2, t2 = timed(f2, 20)
        row['bfs'] = dict(v='NO' if r2 is False else ('YES' if r2 is True else 'UNK'),
                          ok=ok2, nodes=st2.get('nodes'), cut=st2.get('cut'),
                          plc=st2.get('placements_total'),
                          rn=st2.get('cps_res_nodes'), t=round(t2, 3),
                          S=st2.get('S'), L=st2.get('L'),
                          levels=st2.get('level_widths'))
        # BFS-PC at h=OPT: must never be NO
        st3 = {}
        r3, ok3, t3 = timed(lambda: B.bfs_pc(inst, opt, budget=3000,
                                             nodecap=300000, stats=st3), 20)
        row['bfs_opt'] = dict(v='NO' if r3 is False else ('YES' if r3 is True else 'UNK'),
                              ok=ok3, nodes=st3.get('nodes'), t=round(t3, 3))
        rows.append(row)
        print(json.dumps(row), flush=True)
    json.dump(rows, open('exp/v27/res_final.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
