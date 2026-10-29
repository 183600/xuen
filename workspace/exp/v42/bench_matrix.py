import sys, pickle, time, json, statistics
sys.path[:0] = ['exp/v42', 'exp/v41', 'exp/v31', 'exp/v30', 'exp/v29',
                'exp/v13', 'exp/v20', 'exp/v25', 'exp/v16', 'exp/v15', 'exp/v24']
import root_v42, root_v30, root_v41

CASES = {'holdout50': 'exp/v20/holdout_cases50.pkl',
         'hard3': 'exp/v13/hard3.pkl',
         'deep8': 'exp/v18/deep.pkl',
         'large_a': 'exp/v14/large_a.pkl',
         'large_b': 'exp/v14/large_b.pkl',
         'large_het': 'exp/v14/large_het.pkl',
         'synth45': 'exp/v28/synth2_45.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt']) for x in d]

CFG = {
 'v30':        None,  # special
 'mpc':        {'comps': ['ICC', 'MPC', 'WOS', 'PACE']},
 'combo':      {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE']},
 'hetpace':    {'comps': ['HEC', 'PACE']},
 'hecicc':     {'comps': ['HEC', 'ICC', 'PACE']},
 'iccpace':    {'comps': ['ICC', 'PACE']},
 'mpcpace':    {'comps': ['MPC', 'PACE']},
 'hecmpc':     {'comps': ['HEC', 'MPC', 'PACE']},
 'heccmpc':    {'comps': ['HEC', 'ICC', 'MPC', 'PACE']},
 'combo_est':  {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'], 'mpc_order': 'estdesc'},
 'combo_tp':   {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'],
                'pace': {'mint_on': False, 'hpack_on': False, 'cps_on': False}},
 'hetpace_tp': {'comps': ['HEC', 'PACE'],
                'pace': {'mint_on': False, 'hpack_on': False, 'cps_on': False}},
 'combo_tpe':  {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'], 'mpc_order': 'estdesc',
                'pace': {'mint_on': False, 'hpack_on': False, 'cps_on': False}},
 'mpc_nogate': {'comps': ['ICC', 'MPC', 'WOS', 'PACE'], 'mpc_gate': 'n16'},
 'combo_allmpc': {'comps': ['HEC', 'ICC', 'MPC', 'WOS', 'PACE'], 'mpc_gate': 'all'},
}

def run_one(name, inst, h):
    st = {}
    t0 = time.perf_counter()
    if name == 'v30':
        ok, st = root_v30.bb_solve(inst, h, stats=st)
    elif name == 'v41':
        ok, st = root_v41.bb_solve(inst, h, stats=st)
    else:
        ok, st = root_v42.bb_solve(inst, h, cfg=CFG[name], stats=st)
    dt = time.perf_counter() - t0
    st['ok'] = ok
    st['perf'] = dt
    return ok, st

def main():
    rows = []
    for name, f in CASES.items():
        for idx, (inst, opt) in enumerate(load(f)):
            for hmod in (-1, 0):
                h = opt + hmod
                if h < 1:
                    continue
                for cfg in CFG:
                    ok, st = run_one(cfg, inst, h)
                    rows.append(dict(fam=name, idx=idx, hmod=hmod, cfg=cfg,
                                     ok=ok, perf=st['perf'], verdict=st.get('verdict'),
                                     os=st.get('os_nodes'), mpc=st.get('mpc_nodes'),
                                     pace=st.get('pace_nodes'), n=inst['n'], m=inst['m'],
                                     full=st.get('full'), S=st.get('S')))
        print(name, 'done', flush=True)
    pickle.dump(rows, open('exp/v42/matrix.pkl', 'wb'))

if __name__ == '__main__':
    main()
