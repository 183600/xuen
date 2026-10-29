"""v1.6 OMD: 38-instance benchmark.

Compares
  v1.5  : published PACE-S numbers (loaded from exp/v16/res_sop.json)
  base  : the same search with the sound PACK-front repair (omd=False)
  omd   : sound PACK front + online machine dominance (omd=True on fully
          eligible instances, off otherwise)

Writes exp/v17/res_omd.json and exp/v17/summary_omd.json.
"""
import sys, pickle, json, time
sys.path.insert(0, 'exp/v13'); sys.path.insert(0, 'exp/v14')
sys.path.insert(0, 'exp/v15'); sys.path.insert(0, 'exp/v16'); sys.path.insert(0, 'exp/v17')
import po, pace_omd

SETS = [('hard3', 'exp/v13/hard3.pkl'), ('large_b', 'exp/v14/large_b.pkl'),
        ('large_a', 'exp/v14/large_a.pkl'), ('large_het', 'exp/v14/large_het.pkl')]
CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=True, sop_nodecap=200000)


def load(path):
    d = pickle.load(open(path, 'rb'))
    return [x if isinstance(x, dict) else {'inst': x[0], 'opt': x[1]} for x in d]


def full_elig(inst):
    return all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))


def one(inst, h, omd):
    t = time.time()
    (ok, out), st = pace_omd.decide(inst, h, omd=omd, **CFG)
    return ok, st, time.time() - t


def main():
    v15 = {(r['tag'], r['idx']): r for r in json.load(open('exp/v16/res_sop.json'))['v15']}
    rows = []
    T = {'base': 0.0, 'omd': 0.0}
    N = {'v15': 0, 'base': 0, 'omd': 0}
    TB = {'v15': 0, 'base': 0, 'omd': 0}
    for tag, path in SETS:
        for k, rec in enumerate(load(path)):
            inst, h = rec['inst'], rec['opt'] - 1
            fe = full_elig(inst)
            okb, sb, tb = one(inst, h, False)
            oko, so, to = one(inst, h, fe)
            assert okb == oko == False, (tag, k, okb, oko)
            v = v15[(tag, k)]
            rows.append(dict(tag=tag, idx=k, n=inst['n'], m=inst['m'],
                             full_elig=fe, opt=rec['opt'],
                             v15_nodes=v['nodes'], base_nodes=sb['nodes'],
                             omd_nodes=so['nodes'],
                             base_tables=sb['tables'], omd_tables=so['tables'],
                             base_time=round(tb, 5), omd_time=round(to, 5)))
            N['v15'] += v['nodes']; N['base'] += sb['nodes']; N['omd'] += so['nodes']
            TB['v15'] += v['tables']; TB['base'] += sb['tables']; TB['omd'] += so['tables']
            T['base'] += tb; T['omd'] += to
    # h = OPT must stay YES
    false_no = []
    for tag, path in SETS:
        for k, rec in enumerate(load(path)):
            inst = rec['inst']
            ok, st, _ = one(inst, rec['opt'], full_elig(inst))
            if not ok:
                false_no.append((tag, k))
    summary = dict(nodes=N, tables=TB, time={k: round(v, 4) for k, v in T.items()},
                   node_ratio=round(N['base'] / N['omd'], 3),
                   time_ratio=round(T['base'] / T['omd'], 3),
                   false_no_at_opt=false_no,
                   changed=[r for r in rows if r['base_nodes'] != r['omd_nodes']])
    json.dump(dict(rows=rows, summary=summary), open('exp/v17/res_omd.json', 'w'),
              indent=1)
    json.dump(summary, open('exp/v17/summary_omd.json', 'w'), indent=1)
    print('nodes', N)
    print('tables', TB)
    print('time', summary['time'], 'ratio', summary['node_ratio'], summary['time_ratio'])
    print('changed', [(r['tag'], r['idx'], r['base_nodes'], r['omd_nodes']) for r in summary['changed']])
    print('false NO at OPT', false_no)


if __name__ == '__main__':
    main()
