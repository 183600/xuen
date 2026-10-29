"""Validation v2: timeout-aware exact oracle, soundness + S>=5 coverage."""
import sys, json, time, signal, random
sys.path.insert(0, 'exp/v27')
sys.path.insert(0, 'exp/v25')
sys.path.insert(0, 'exp/v24')
sys.path.insert(0, 'exp/v16')
sys.path.insert(0, 'exp/v13')
sys.path.insert(0, 'exp/v15')
import bfs_pc as B
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


def decide_exact(inst, h, nodecap=2_000_000, tl=8):
    """True/False, or None if the engine hit its node cap / wall clock."""
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    try:
        (ok, _), st = P.decide(inst, h, nodecap=nodecap, dhd=True, dcd=True,
                               hpack_on=True, map_on=True, cps_on=False,
                               packset_on=True, sop_on=False, omd=False,
                               stats=st)
    except TO:
        ok = None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if ok is None or st.get('timeout'):
        return None
    return bool(ok)


def opt_of(inst, tl=8):
    lo, hi = max(inst['p']), sum(inst['p'])
    while lo < hi:
        mid = (lo + hi) // 2
        v = decide_exact(inst, mid, tl=tl)
        if v is None:
            return None
        if v:
            hi = mid
        else:
            lo = mid + 1
    return lo


def bfs(inst, h, budget=3000, nodecap=50000, tl=8):
    st = {}
    signal.setitimer(signal.ITIMER_REAL, tl)
    t = time.time()
    try:
        r = B.bfs_pc(inst, h, budget=budget, nodecap=nodecap, stats=st)
        ok = True
    except TO:
        r, ok = None, False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    st['time'] = round(time.time() - t, 3)
    st['timeout'] = not ok
    st['v'] = 'NO' if r is False else ('YES' if r is True else 'UNK')
    return st


def soundness(ncase=30):
    rows = []
    for s in range(ncase):
        n = 8 + s % 3
        m = 2 + s % 2
        inst = gen(n, m, seed=5000 + s, pedge=0.3)
        opt = opt_of(inst)
        if opt is None:
            print('skip opt', s, flush=True)
            continue
        for h in (opt - 1, opt):
            ex = decide_exact(inst, h)
            if ex is None:
                print('skip exact', s, h, flush=True)
                continue
            st = bfs(inst, h)
            rows.append({'s': s, 'n': n, 'm': m, 'h': h, 'off': h - opt,
                         'bfs': st['v'], 'exact': ex, 'S': st.get('S'),
                         'L': st.get('L'), 'nodes': st.get('nodes'),
                         'cut': st.get('cut'), 'plc': st.get('placements_total'),
                         'timeout': st['timeout']})
            print(rows[-1], flush=True)
    bad = [r for r in rows if r['bfs'] == 'NO' and r['exact']]
    bady = [r for r in rows if r['bfs'] == 'YES' and not r['exact']]
    print('states', len(rows), 'FALSE_NO', len(bad), 'FALSE_YES', len(bady))
    json.dump(rows, open('exp/v27/res_sound2.json', 'w'), indent=1)


def synth(ncase=10):
    rows = []
    s = 0
    while len(rows) < ncase and s < 80:
        seed = 9000 + s
        inst = gen(12, 2, seed=seed, pedge=0.15)
        s += 1
        opt = opt_of(inst)
        if opt is None:
            continue
        h = opt - 1
        st = bfs(inst, h, budget=3000, nodecap=50000, tl=10)
        if st.get('S') is None or st['S'] < 5:
            continue
        # independent confirmation that h is infeasible
        ex = decide_exact(inst, h)
        if ex is None:
            continue
        rows.append({'s': s, 'seed': seed, 'opt': opt, 'S': st['S'], 'L': st['L'],
                     'bfs': st['v'], 'exact_at_h': ex,
                     'plc': st.get('placements_total'), 'nodes': st.get('nodes'),
                     'cut': st.get('cut'), 'levels': st.get('level_widths'),
                     'time': st['time']})
        print(rows[-1], flush=True)
    print('kept', len(rows), 'all_infeasible',
          all(not r['exact_at_h'] for r in rows))
    json.dump(rows, open('exp/v27/res_synthS3.json', 'w'), indent=1)


if __name__ == '__main__':
    (soundness if sys.argv[1] == 'sound' else synth)()
