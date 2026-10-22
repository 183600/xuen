import sys, json, pickle, time, random
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import exp_da as E, kern, ge, ref
from states import gen_states
from proto_tent_root import tent_thresh

def main():
    pool, states = gen_states()
    rows = json.load(open('states.json'))
    gaps = [r for r in rows if r.get('mus') is not None]
    out = []
    # ---- 1. gap cases: GE closes?
    for r in gaps:
        inst = pool[r['k']][0]
        S, A, c = r['S'], r['A'], r['c']
        U = E.guide(inst, S, A, c)
        LTH = r['LTH']; so = r['sopt']
        t0 = time.time()
        lb, st = ge.state_threshold(inst, S, A, c, U, nodecap=400_000)
        dt = time.time() - t0
        est, q, sl, bars = kern.zero_slack(inst, S, c, so - 1)
        nR = bin((((1 << inst['n']) - 1) ^ S)).count('1')
        # independent check of the infeasibility at so-1 (the claim GE relies on)
        iv = ref.ref_feasible(inst, S, A, c, so - 1)
        row = dict(kind='state', k=r['k'], trial=r['trial'], nR=nR, sopt=so,
                   LTH=LTH, L0=r['L0'], U=U, LB=lb, closed=(lb == so),
                   bars=bin(bars).count('1'),
                   nodes=st.get('nodes'), calls=st.get('calls'),
                   memo_bad=st.get('memo_bad'), t=round(dt, 4), indep_infeas=(iv is False))
        out.append(row)
        print('state', r['k'], r['trial'], 'nR', nR, 'LTH', LTH, 'opt', so, 'GE', lb,
              'closed', row['closed'], 'nodes', row['nodes'], 't', row['t'], flush=True)
    # ---- 2. k=29 root
    inst, opt, nd = pool[29]
    S, A, c = 0, (0, 0), (-1,) * inst['n']
    U = E.guide(inst, S, A, c)
    t0 = time.time(); lb, st = ge.state_threshold(inst, S, A, c, U, nodecap=400_000); dt = time.time() - t0
    iv = ref.ref_feasible(inst, S, A, c, opt - 1)
    out.append(dict(kind='root', k=29, nR=inst['n'], sopt=opt, LTH=34,
                    L0=E.lower_L0(inst, S, A, c), U=U, LB=lb, closed=(lb == opt),
                    bars=0, nodes=st.get('nodes'), calls=st.get('calls'),
                    memo_bad=st.get('memo_bad'), t=round(dt, 4), indep_infeas=(iv is False)))
    print('root29', lb, opt, st, round(dt, 4), flush=True)
    json.dump(out, open('cert.json', 'w'), indent=1)

    # ---- 3. soundness sweep: random states x random H
    rng = random.Random(777)
    claims = []; feas = []; bad = 0
    for _ in range(60):
        k = rng.randrange(len(pool))
        inst = pool[k][0]
        S, A, c = E.random_prefix(inst, rng, rng.choice([0.2, 0.35, 0.5, 0.65]))
        L0 = max(E.lower_L0(inst, S, A, c), ge.head_bound(inst, S, A, c))
        U = E.guide(inst, S, A, c)
        if L0 >= U:
            continue
        H = rng.randint(L0, U - 1)
        memo = {'bad': {}, 'reuse': 0, 'internal': 0}
        t0 = time.time()
        stt, sched, s = ge.decide(inst, S, A, c, H, nodecap=400_000, memo=memo)
        dt = time.time() - t0
        if stt is False:
            claims.append((k, H, round(dt, 5), s.get('nodes')))
            iv = ref.ref_feasible(inst, S, A, c, H)
            if iv is not False:
                bad += 1
                print('FALSE CLAIM', k, H, iv)
        elif stt is True:
            ok = ref.verify_schedule(inst, S, A, c, H, sched)
            feas.append((k, H, ok))
            if not ok:
                bad += 1
                print('BAD WITNESS', k, H)
    print('soundness: infeasible claims', len(claims), 'feasible witnesses',
          len(feas), 'bad', bad, flush=True)
    json.dump(dict(claims=claims, feas=feas, bad=bad), open('soundness.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
