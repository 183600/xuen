import sys, json, pickle, time
sys.path.insert(0, '/home/runner/work/xuen/xuen/workspace/exp')
import exp_da as E
from exp_ro import rollout, search, broad_pool

def roll4(inst):
    vals = []
    pv = None
    for inner in ('CP', 'LPT', 'MWKR', 'LST'):
        u, p = rollout(inst, inner=inner)
        vals.append((u, inner, p))
    vals.sort()
    return vals[0][0], vals[0][1], vals[0][2]

def main():
    hard = pickle.load(open('/home/runner/work/xuen/xuen/workspace/exp/hard17.pkl', 'rb'))
    broad = broad_pool()
    rows = []
    t0 = time.time()
    for tag, pool in (('hard', hard), ('broad', broad)):
        for st, inst, r in pool:
            opt = r['U']
            ur, inner, pv = roll4(inst)
            b = search(inst, None)
            p = search(inst, ur)
            assert b['U'] == opt and p['U'] == opt
            rows.append({'pool': tag, 'n': inst['n'],
                         'edges': sum(len(x) for x in inst['pred']),
                         'opt': opt, 'L0': r['L0'], 'ag': st,
                         'roll': ur, 'roll_inner': inner,
                         'base': b['steps'], 'pv': p['steps'],
                         'base_any': {k: b['anytime'][k] for k in (0,1,2,5,10,20)},
                         'pv_any': {k: p['anytime'][k] for k in (0,1,2,5,10,20)}})
    out = {'rows': rows, 'wall': time.time() - t0}
    json.dump(out, open('/home/runner/work/xuen/xuen/workspace/exp/final.json', 'w'), indent=1)
    for tag in ('hard', 'broad'):
        rs = [x for x in rows if x['pool'] == tag]
        n = len(rs)
        print(f"== {tag} n={n}")
        print('nodes base', sum(x['base'] for x in rs), 'pv', sum(x['pv'] for x in rs))
        print('wins/ties/losses', sum(x['pv'] < x['base'] for x in rs),
              sum(x['pv'] == x['base'] for x in rs), sum(x['pv'] > x['base'] for x in rs))
        print('roll hits', sum(x['roll'] == x['opt'] for x in rs),
              'mean excess', sum(x['roll'] - x['opt'] for x in rs) / n)
        for k in (0,1,2,5,10,20):
            gb = sum(x['base_any'][k] - x['opt'] for x in rs) / n
            gp = sum(x['pv_any'][k] - x['opt'] for x in rs) / n
            print(f'  budget {k:>2}: base {gb:.3f}  pv {gp:.3f}')
        print()
    rs = rows
    n = len(rs)
    print('== combined', n)
    print('nodes', sum(x['base'] for x in rs), '->', sum(x['pv'] for x in rs),
          f"({100*(1-sum(x['pv'] for x in rs)/sum(x['base'] for x in rs)):.1f}% less)")
    print('roll hits', sum(x['roll'] == x['opt'] for x in rs), '/', n)
    print('wall', round(time.time()-t0, 2))

if __name__ == '__main__':
    main()
