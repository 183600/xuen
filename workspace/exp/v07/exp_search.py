import sys, json, pickle, time
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import exp_da as E, search
from proto_full import run_full

def main():
    pool = pickle.load(open('../pool30.pkl', 'rb'))
    rows = []
    for k, (inst, opt, nd) in enumerate(pool):
        b = run_full(inst, budget=900, delta=0, root_bound='TENT')
        assert b['U'] == opt, (k, 'base', b['U'], opt)
        a = search.run(inst, root='TENT')
        assert a['U'] == opt, (k, 'l0a', a['U'], opt)
        c = search.run(inst, root='TENT', ge_root=True)
        assert c['U'] == opt, (k, 'ge', c['U'], opt)
        d = search.run(inst, root='TENT', ge_root=True, ge_point=True, band=2)
        assert d['U'] == opt, (k, 'gept', d['U'], opt)
        e = search.run(inst, root='TENT', ge_root=True, ge_point=True, band=2, ge_small=8)
        assert e['U'] == opt, (k, 'ges', e['U'], opt)
        row = dict(k=k, n=inst['n'], opt=opt,
                   b_steps=b['steps'], b_t=round(b['time'], 4), b_Lg=b['Lg'],
                   a_steps=a['steps'], a_t=round(a['time'], 4), a_Lg=a['Lg'],
                   c_steps=c['steps'], c_t=round(c['time'] + c['t_ge'], 4),
                   c_ge=round(c['t_ge'], 4), c_gn=c['ge_nodes'], c_Lg=c['Lg'],
                   c_gnod=round(c['time'], 4),
                   d_steps=d['steps'], d_t=round(d['time'] + d['t_ge'], 4),
                   d_ge=round(d['t_ge'], 4), d_gn=d['ge_nodes'], d_Lg=d['Lg'],
                   d_gnod=round(d['time'], 4),
                   e_steps=e['steps'], e_t=round(e['time'] + e['t_ge'], 4),
                   e_ge=round(e['t_ge'], 4), e_gn=e['ge_nodes'], e_Lg=e['Lg'],
                   e_gnod=round(e['time'], 4),
                   mi=c['memo_internal'], mr=c['memo_reuse'])
        rows.append(row)
        print(k, 'opt', opt, '| base', b['steps'], '| A', a['steps'],
              '| GE', c['steps'], row['c_t'], '| GEP', d['steps'], row['d_t'],
              '| GES', e['steps'], row['e_t'], flush=True)
    json.dump(rows, open('search.json', 'w'), indent=1)
    for tag in ('b_steps', 'a_steps', 'c_steps', 'd_steps', 'e_steps'):
        print(tag, sum(r[tag] for r in rows))
    for tag in ('b_t', 'a_t', 'c_t', 'd_t', 'e_t'):
        print(tag, round(sum(r[tag] for r in rows), 3))
    print('Lg==opt', {tag: sum(1 for r in rows if r[tag] == r['opt'])
                      for tag in ('b_Lg', 'a_Lg', 'c_Lg', 'd_Lg', 'e_Lg')})
    for x, y in (('a', 'b'), ('c', 'a'), ('d', 'c'), ('e', 'c')):
        print(f'{x} vs {y} win', sum(1 for r in rows if r[x + '_steps'] < r[y + '_steps']),
              'loss', sum(1 for r in rows if r[x + '_steps'] > r[y + '_steps']))
    print('memo internal', sum(r['mi'] for r in rows), 'reuse', sum(r['mr'] for r in rows))

if __name__ == '__main__':
    main()
