"""Randomised soundness and S>=5 coverage tests for BFS-PC (v2.3)."""
import sys, json, time, signal, random
sys.path.insert(0, 'exp/v27')
sys.path.insert(0, 'exp/v25')
sys.path.insert(0, 'exp/v24')
sys.path.insert(0, 'exp/v16')
sys.path.insert(0, 'exp/v13')
sys.path.insert(0, 'exp/v15')
import bfs_pc as B
import cps_lib as C
import pace_v25 as P
import po


class TO(Exception):
    pass


def _alarm(sig, frm):
    raise TO()


signal.signal(signal.SIGALRM, _alarm)


def gen(n, m, seed, pedge, pmax=4):
    rnd = random.Random(seed)
    p = [rnd.randint(1, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rnd.random() < pedge:
                pred[j].append(i)
    return po.make_inst(p, m, pred)


def opt_of(inst, nodecap=200000, tl=10):
    lo, hi = max(inst['p']), sum(inst['p'])
    signal.setitimer(signal.ITIMER_REAL, tl)
    try:
        while lo < hi:
            mid = (lo + hi) // 2
            (ok, _), _st = P.decide(inst, mid, nodecap=nodecap, dhd=True,
                                    dcd=True, hpack_on=True, map_on=True,
                                    cps_on=False, packset_on=True,
                                    sop_on=False, omd=False)
            if ok:
                hi = mid
            else:
                lo = mid + 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return lo


def exact(inst, h, nodecap=200000, tl=10):
    signal.setitimer(signal.ITIMER_REAL, tl)
    try:
        (ok, _), _st = P.decide(inst, h, nodecap=nodecap, dhd=True, dcd=True,
                                hpack_on=True, map_on=True, cps_on=False,
                                packset_on=True, sop_on=False, omd=False)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return ok


def bfs(inst, h, budget=5000, nodecap=50000, tl=10):
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = B.bfs_pc(inst, h, budget=budget, nodecap=nodecap, stats=st)
        status = 'ok'
    except TO:
        r, status = None, 'timeout'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    st['time'] = time.time() - t
    st['status'] = status
    return r, st


def soundness(ncase=40):
    rows = []
    for s in range(ncase):
        n = 8 + s % 3
        m = 2 + s % 2
        inst = gen(n, m, seed=5000 + s, pedge=0.3)
        try:
            opt = opt_of(inst)
        except TO:
            continue
        for h in (opt - 1, opt, opt + 1):
            try:
                ex = exact(inst, h)
            except TO:
                continue
            r, st = bfs(inst, h)
            bf = (r is False)
            rows.append({'s': s, 'n': n, 'm': m, 'h_off': h - opt,
                         'bfs': 'NO' if bf else ('YES' if r else 'UNK'),
                         'exact': bool(ex), 'S': st.get('S'),
                         'L': st.get('L'), 'nodes': st.get('nodes'),
                         'cut': st.get('cut'), 'plc': st.get('placements_total'),
                         'status': st['status'], 'time': round(st['time'], 3)})
        print(json.dumps(rows[-1]), flush=True)
    json.dump(rows, open('exp/v27/res_sound.json', 'w'), indent=1)
    bad = [r for r in rows if r['bfs'] == 'NO' and r['exact']]
    print('FALSE_NO', len(bad), 'of', len(rows))


def synth_s(ncase=12):
    rows = []
    s = 0
    while len(rows) < ncase and s < 60:
        inst = gen(12, 2, seed=9000 + s, pedge=0.15)
        s += 1
        try:
            opt = opt_of(inst)
        except TO:
            continue
        h = opt - 1
        q = B.tails(inst)
        ch, cp = C.critical_path(inst, (1 << inst['n']) - 1, [0] * inst['n'], q)
        S = h - cp
        if S < 5:
            continue
        r, st = bfs(inst, h)
        rows.append({'s': s, 'opt': opt, 'S': S, 'L': len(ch),
                     'bfs': 'NO' if r is False else ('YES' if r else 'UNK'),
                     'plc': st.get('placements_total'), 'nodes': st.get('nodes'),
                     'cut': st.get('cut'), 'levels': st.get('level_widths'),
                     'status': st['status'], 'time': round(st['time'], 3)})
        print(json.dumps(rows[-1]), flush=True)
    json.dump(rows, open('exp/v27/res_synthS.json', 'w'), indent=1)


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'sound'
    if which == 'sound':
        soundness()
    else:
        synth_s()
