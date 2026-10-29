"""Benchmark QNC vs ALC on the 141 NO instances (h=OPT-1)."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC
from alc import ALC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]

def main():
    out = {}
    for name, f in FILES.items():
        rows = []
        for idx, (inst, opt) in enumerate(load(f)):
            h = opt - 1
            t0 = time.time(); q = QNC(inst, h); v, st = q.decide()
            tq = time.time() - t0
            t0 = time.time(); a = ALC(inst, h); va, sa = a.decide()
            ta = time.time() - t0
            rows.append(dict(idx=idx, v=v, audit=q.audit(), lp=st['lp_solves'],
                             nodes=st['nodes'], leaves=st['leaves'],
                             prunes=st['prunes'], empty=st['empty_prunes'],
                             clauses=st['clauses'],
                             force={i: len(s) for i, s in st['force'].items()},
                             cert_t=st['cert_t'], t=tq,
                             alc_v=va, alc_lp=sa['lp_solves'],
                             alc_nodes=sa['nodes'], alc_t=ta,
                             cert_scale=(st['cert'] or {}).get('scale')))
        out[name] = dict(
            n=len(rows), no=sum(r['v'] is False for r in rows),
            unknown=sum(r['v'] is None for r in rows),
            audit=sum(r['audit'] for r in rows),
            lp=sum(r['lp'] for r in rows), nodes=sum(r['nodes'] for r in rows),
            leaves=sum(r['leaves'] for r in rows),
            prunes=sum(r['prunes'] for r in rows),
            empty=sum(r['empty'] for r in rows),
            force=sum(len(r['force']) for r in rows),
            t=sum(r['t'] for r in rows), cert_t=sum(r['cert_t'] for r in rows),
            alc_lp=sum(r['alc_lp'] for r in rows),
            alc_nodes=sum(r['alc_nodes'] for r in rows),
            alc_t=sum(r['alc_t'] for r in rows), rows=rows)
        print(name, {k: v for k, v in out[name].items() if k != 'rows'},
              flush=True)
    keys = ['n', 'no', 'unknown', 'audit', 'lp', 'nodes', 'leaves', 'prunes',
            'empty', 'force', 't', 'cert_t', 'alc_lp', 'alc_nodes', 'alc_t']
    out['_total'] = {k: sum(out[n][k] for n in FILES) for k in keys}
    out['_branch_rows'] = [dict(name=n, **r) for n in FILES for r in out[n]['rows']
                           if r['alc_nodes'] > 1 or r['nodes'] > 1]
    json.dump(out, open('exp/v71/qnc_stats.json', 'w'), indent=1)
    print('TOTAL', out['_total'])
    for r in out['_branch_rows']:
        print('case', r['name'], r['idx'], 'QNC lp', r['lp'], 'nodes', r['nodes'],
              'leaves', r['leaves'], 'force', r['force'], '| ALC lp',
              r['alc_lp'], 'nodes', r['alc_nodes'], 'audit', r['audit'])
    print('wall', round(sum(out[n]['t'] for n in FILES), 2))

if __name__ == '__main__':
    main()
