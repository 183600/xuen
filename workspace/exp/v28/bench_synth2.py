"""More tight synthetic states + heterogeneous soundness check."""
import sys, time, json, random
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, pace_v25 as P, cps_lib, sgs


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


def one(inst, h):
    n, m, p = inst['n'], inst['m'], inst['p']
    est, q = po.heads_tails(inst, 0, [0] * n)
    cp = max(est[i] + p[i] + q[i] for i in range(n))
    S = h - cp
    A = tuple([0] * m); rem = inst['full']
    stc = {}
    tc = time.time()
    vc = cps_lib.cps_certify(inst, rem, A, est, q, h, tau=4, nodecap=300000, stats=stc)
    tc = time.time() - tc
    sto = {}
    to = time.time()
    vo, _ = sgs.sgs_solve(inst, h, rem=rem, A=A, est=est, q=q, nodecap=10000, stats=sto)
    to = time.time() - to
    return dict(S=S, L=stc.get('cps_len'), cps_nodes=stc.get('cps_res_nodes'),
                cps_plc=stc.get('cps_placements'), cps_v=vc, cps_t=round(tc, 4),
                os_nodes=sto.get('nodes'), os_v=vo, os_t=round(to, 4))


rng = random.Random(99)
rows = []
t0 = time.time()
tries = 0
while len(rows) < 45 and tries < 400:
    tries += 1
    n = rng.randint(11, 16); m = rng.choice([3, 3, 4])
    p = [rng.randint(1, 4) for _ in range(n)]
    pe = rng.choice([0.10, 0.15, 0.20, 0.28])
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < pe:
                pred[j].append(i)
    inst = po.make_inst(p, m, pred)
    opt = opt_of(inst, sum(p))
    if opt is None:
        continue
    h = opt - 1
    est, q = po.heads_tails(inst, 0, [0] * n)
    S = h - max(est[i] + p[i] + q[i] for i in range(n))
    if not (0 <= S <= 4):
        continue
    r = one(inst, h); r.update(seed=tries, n=n, m=m)
    r['ratio'] = round(r['L'] / n, 3)
    rows.append(r)
    print(json.dumps(r))
print('elapsed', round(time.time() - t0, 1), 'tries', tries)
json.dump(rows, open('exp/v28/res_synth2.json', 'w'), indent=1)
