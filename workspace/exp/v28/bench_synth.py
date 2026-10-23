"""Tight synthetic states: does OS ever lose to CPS inside the gate?"""
import sys, time, json, random, signal
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, pace_v25 as P, cps_lib, sgs


def fe(inst):
    return all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))


def decide_exact(inst, h, nodecap=2_000_000):
    st = {}
    (ok, _), st = P.decide(inst, h, nodecap=nodecap, dhd=True, dcd=True,
                           hpack_on=True, map_on=True, cps_on=False,
                           packset_on=True, sop_on=False, omd=False, stats=st)
    if ok is None or st.get('timeout'):
        return None
    return bool(ok)


def opt_of(inst, hi):
    lo = max(inst['p'])
    while lo < hi:
        mid = (lo + hi) // 2
        v = decide_exact(inst, mid)
        if v is None:
            return None
        if v:
            hi = mid
        else:
            lo = mid + 1
    return lo


rng = random.Random(2026)
rows = []
t0 = time.time()
for seed in range(60):
    n = rng.randint(12, 16); m = rng.choice([3, 3, 4])
    p = [rng.randint(1, 4) for _ in range(n)]
    pe = rng.choice([0.12, 0.18, 0.25])
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < pe:
                pred[j].append(i)
    inst = po.make_inst(p, m, pred)
    ub = sum(p)
    opt = opt_of(inst, ub)
    if opt is None:
        continue
    h = opt - 1
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    S = h - cp
    if S > 4:
        continue
    A = tuple([0] * m); rem = inst['full']
    # CPS
    stc = {}
    tc = time.time()
    vc = cps_lib.cps_certify(inst, rem, A, est, q, h, tau=4, nodecap=300000, stats=stc)
    tc = time.time() - tc
    # OS with a 10k budget
    sto = {}
    to = time.time()
    vo, _ = sgs.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q, nodecap=10000, stats=sto)
    to = time.time() - to
    rows.append(dict(seed=seed, n=n, m=m, S=S, L=stc.get('cps_len'),
                     cps_nodes=stc.get('cps_res_nodes'), cps_plc=stc.get('cps_placements'),
                     cps_v=vc, cps_t=round(tc, 4),
                     os_nodes=sto.get('nodes'), os_v=vo, os_t=round(to, 4)))
    print(json.dumps(rows[-1]))
print('elapsed', round(time.time() - t0, 1), 'cases', len(rows))
json.dump(rows, open('exp/v28/res_synth.json', 'w'), indent=1)
