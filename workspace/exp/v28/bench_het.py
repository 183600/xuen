import pickle, sys, time, json
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, pace_v25 as P, sgs

D = pickle.load(open('exp/v14/large_het.pkl', 'rb'))
rows = []
for idx, x in enumerate(D):
    inst, opt = x['inst'], x['opt']
    for tag, h in [('hM1', opt - 1), ('h0', opt)]:
        st = {}
        t0 = time.time()
        v, sch = sgs.sgs_solve(inst, h, nodecap=200000, stats=st)
        dt = time.time() - t0
        row = dict(idx=idx, n=inst['n'], m=inst['m'], tag=tag, v=v,
                   nodes=st.get('nodes'), t=round(dt, 4))
        if v is True:
            row['valid'] = sgs.validate(inst, h, sch)[0]
        if v is False:
            # exact engine check (relaxation must be sound on NO)
            st2 = {}
            (ok, _), st2 = P.decide(inst, h, nodecap=2_000_000, dhd=True, dcd=True,
                                    hpack_on=True, map_on=True, cps_on=False,
                                    packset_on=True, sop_on=False, omd=False, stats=st2)
            row['exact'] = ok
        rows.append(row)
        print(json.dumps(row))
json.dump(rows, open('exp/v28/res_het.json', 'w'), indent=1)
