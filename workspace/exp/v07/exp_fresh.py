import sys, json, random, time
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import exp_da as E, kern, search, ge
from proto_full import run_full

def main():
    rng = random.Random(90210)
    rows = []
    for t in range(60):
        n = rng.choice([9, 10])
        inst = E.gen_instance(n, rng.choice([0.2, 0.3, 0.4]),
                              rng.choice([6, 8, 10]), rng)
        S0, A0, c0 = 0, (0, 0), (-1,) * n
        inst['pmask'] = [sum(1 << j for j in inst['pred'][i]) for i in range(n)]
        opt = kern.state_opt(inst, S0, A0, c0)
        b = run_full(inst, budget=900, delta=0, root_bound='TENT')
        r = search.run(inst, root='TENT', ge_root=True, ge_nodes=400_000)
        ok = (b['U'] == opt and r['U'] == opt)
        rows.append(dict(t=t, n=n, ep=inst['ep'], pmax=inst['pmax'], opt=opt,
                         b_steps=b['steps'], b_t=round(b['time'], 4),
                         r_steps=r['steps'], r_t=round(r['time'] + r['t_ge'], 4),
                         r_gn=r['ge_nodes'], r_Lg=r['Lg'], ok=ok))
        print(t, n, inst['ep'], inst['pmax'], 'opt', opt, '| base', b['steps'],
              round(b['time'], 4), '| R', r['steps'], rows[-1]['r_t'], 'ok', ok, flush=True)
    json.dump(rows, open('fresh.json', 'w'), indent=1)
    print('all correct', all(r['ok'] for r in rows))
    print('base steps', sum(r['b_steps'] for r in rows), 't', round(sum(r['b_t'] for r in rows), 3))
    print('R steps', sum(r['r_steps'] for r in rows), 't', round(sum(r['r_t'] for r in rows), 3))
    print('base wins', sum(1 for r in rows if r['b_steps'] < r['r_steps']),
          'R wins', sum(1 for r in rows if r['r_steps'] < r['b_steps']),
          'ties', sum(1 for r in rows if r['r_steps'] == r['b_steps']))
    print('Lg==opt base', sum(1 for r in rows if r['b_steps'] == 0 or True))

if __name__ == '__main__':
    main()
