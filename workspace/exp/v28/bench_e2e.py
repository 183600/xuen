import sys, time, json, pickle
sys.path[:0] = ['exp/v13', 'exp/v15', 'exp/v16', 'exp/v20', 'exp/v24', 'exp/v25', 'exp/v28']
import po, pace_v25 as P, cps_lib
import sgs_certify as SG
import hybrid

CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000,
           dhd=True, dcd=True, hpack_on=True, odom=False,
           map_on=True, map_tau=4, map_ncap=16,
           cps_on=True, cps_tau=4, cps_depth=0, cps_ncap=16,
           cps_nodecap=300000, cps_gate_fan=0)


def fe(inst):
    return all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))


def run(inst, h, tag):
    cfg = dict(CFG); cfg['omd'] = fe(inst)
    st = {}
    t0 = time.time()
    (ok, sched), st = P.decide(inst, h, stats=st, **cfg)
    dt = time.time() - t0
    return dict(tag=tag, ok=ok, nodes=st['nodes'], tables=st['tables'],
                t=round(dt, 4), cps_calls=st.get('cps_calls', 0),
                sgs=st.get('sgs_nodes', 0), resn=st.get('cps_res_nodes', 0))


def main():
    d = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    orig = cps_lib.cps_certify
    out = {}
    for variant in ['cps', 'sgs', 'hybrid']:
        cps_lib.cps_certify = (orig if variant == 'cps' else
                              (SG.sgs_certify if variant == 'sgs' else hybrid.hybrid_certify))
        rows = []; t0 = time.time()
        for idx, (inst, opt) in enumerate(d):
            r = run(inst, opt - 1, variant); r['idx'] = idx
            rows.append(r)
        out[variant] = dict(rows=rows, nodes=sum(r['nodes'] for r in rows),
                            tables=sum(r['tables'] for r in rows),
                            t=round(time.time() - t0, 4),
                            cps=sum(r['cps_calls'] for r in rows),
                            sgs=sum(r['sgs'] for r in rows))
        print(variant, json.dumps({k: out[variant][k] for k in ['nodes', 'tables', 't', 'cps', 'sgs']}))
    cps_lib.cps_certify = orig
    json.dump(out, open('exp/v28/res_e2e.json', 'w'), indent=1)
    # deltas
    diffs = [(a['idx'], a['nodes'], b['nodes']) for a, b in zip(out['cps']['rows'], out['sgs']['rows']) if a['nodes'] != b['nodes']]
    print('diffs', diffs[:10])


if __name__ == '__main__':
    main()
