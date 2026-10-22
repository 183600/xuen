import sys, json, pickle
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import exp_da as E, ge
from proto_full import run_full

def root_ge(inst, use_sym=True, use_energy=True, cap=2_000_000):
    n = inst['n']
    S0, A0, c0 = 0, (0, 0), (-1,) * n
    U = E.guide(inst, S0, A0, c0)
    memo = ge.make_memo()
    pr, U2, st = ge.ge_step(inst, S0, A0, c0, U, memo, nodecap=cap,
                            use_sym=use_sym, use_energy=use_energy)
    return pr, U2, st['nodes'], st['calls'], st['internal']

def main():
    pool = pickle.load(open('../pool30.pkl', 'rb'))
    rows = []
    for k, (inst, opt, nd) in enumerate(pool):
        a = root_ge(inst, True, True)
        b = root_ge(inst, True, False)
        c = root_ge(inst, False, True)
        rows.append(dict(k=k, opt=opt, nd_ref=nd,
                         energy=a[2], noenergy=b[2], nosym=c[2],
                         calls=a[3], internal=a[4], ok=(a[1] == opt and b[1] == opt)))
        print(k, 'opt', opt, 'ref', nd, '| E', a[2], '| noE', b[2], '| noSym', c[2], flush=True)
    json.dump(rows, open('abl.json', 'w'), indent=1)
    print('sum E', sum(r['energy'] for r in rows), 'noE', sum(r['noenergy'] for r in rows),
          'noSym', sum(r['nosym'] for r in rows), 'ref exact', sum(r['nd_ref'] for r in rows))
    print('all ok', all(r['ok'] for r in rows))
    print('noE/E ratio', round(sum(r['noenergy'] for r in rows) / max(1, sum(r['energy'] for r in rows)), 2))

if __name__ == '__main__':
    main()
