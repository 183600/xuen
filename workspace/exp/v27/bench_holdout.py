"""Benchmark BFS-PC (v2.3) against the v2.2 CPS leaf enumeration."""
import sys, os, json, time, signal, pickle
sys.path.insert(0, 'exp/v27')
sys.path.insert(0, 'exp/v25')
import bfs_pc as B
import cps_lib as C

HOLDOUT = 'exp/v20/holdout_cases50.pkl'


class TO(Exception):
    pass


def _alarm(sig, frm):
    raise TO()


signal.signal(signal.SIGALRM, _alarm)


def run_case(inst, h, budget=3000, nodecap=300000, tl=15):
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = B.bfs_pc(inst, h, budget=budget, nodecap=nodecap, stats=st)
        status = 'ok'
    except TO:
        r, status = None, 'timeout'
    except RecursionError:
        r, status = None, 'recursion'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    st['time'] = time.time() - t
    st['status'] = status
    return r, st


def baseline_cps(inst, h, nodecap=300000, tl=15):
    """v2.2 CPS at the root, gate forced open (tau=h)."""
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = C.cps_certify(inst, (1 << inst['n']) - 1, (0,) * inst['m'],
                          [0] * inst['n'], B.tails(inst), h,
                          tau=10 ** 9, nodecap=nodecap, stats=st)
        status = 'ok'
    except TO:
        r, status = None, 'timeout'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    st['time'] = time.time() - t
    st['status'] = status
    return r, st


def main():
    d = pickle.load(open(HOLDOUT, 'rb'))
    out = []
    for idx, (inst, opt) in enumerate(d):
        row = {'idx': idx, 'n': inst['n'], 'm': inst['m'], 'opt': opt}
        for tag, h in (('lo', opt - 1), ('opt', opt)):
            r, st = run_case(inst, h, budget=3000)
            row[tag] = {'verdict': ('NO' if r is False else
                                    'YES' if r is True else 'UNK'),
                        'S': st.get('S'), 'L': st.get('L'),
                        'nodes': st.get('nodes'), 'cut': st.get('cut'),
                        'plc': st.get('placements_total'),
                        'levels': st.get('level_widths'),
                        'status': st['status'],
                        'time': round(st['time'], 3)}
        out.append(row)
        print(json.dumps(row), flush=True)
    json.dump(out, open('exp/v27/res_holdout.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
