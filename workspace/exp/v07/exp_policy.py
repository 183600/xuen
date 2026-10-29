import sys, json, pickle, time
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import search
from proto_full import run_full

def main():
    pool = pickle.load(open('../pool30.pkl', 'rb'))
    variants = {
        'base': None,
        'A': dict(root='TENT'),
        'D8': dict(root='TENT', ge_point=True, band=-1, ge_small=8),
        'D9': dict(root='TENT', ge_point=True, band=-1, ge_small=9),
        'R': dict(root='TENT', ge_root=True, ge_nodes=20000),
        'RD8': dict(root='TENT', ge_root=True, ge_nodes=20000, ge_point=True, band=-1, ge_small=8),
        'F': dict(root='TENT', ge_point=True, band=2),
    }
    rows = []
    for k, (inst, opt, nd) in enumerate(pool):
        row = {'k': k, 'opt': opt}
        for tag, kw in variants.items():
            if kw is None:
                r = run_full(inst, budget=900, delta=0, root_bound='TENT')
                row[tag] = dict(steps=r['steps'], t=round(r['time'], 4), Lg=r['Lg'])
            else:
                r = search.run(inst, **kw)
                row[tag] = dict(steps=r['steps'], t=round(r['time'] + r['t_ge'], 4),
                                Lg=r['Lg'], gn=r['ge_nodes'], tg=round(r['t_ge'], 4))
            assert r['U'] == opt, (k, tag, r['U'], opt)
        rows.append(row)
        print(k, 'opt', opt, ' '.join(f"{t}:{row[t]['steps']}/{row[t]['t']}" for t in variants), flush=True)
    json.dump(rows, open('policy.json', 'w'), indent=1)
    for tag in variants:
        print(tag, 'steps', sum(r[tag]['steps'] for r in rows),
              'time', round(sum(r[tag]['t'] for r in rows), 3),
              'Lg==opt', sum(1 for r in rows if r[tag]['Lg'] == r['opt']),
              'ge_nodes', sum(r[tag].get('gn', 0) for r in rows))

if __name__ == '__main__':
    main()
