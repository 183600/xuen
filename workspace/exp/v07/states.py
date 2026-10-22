import sys, random, json, pickle, time
sys.path.insert(0, '..'); sys.path.insert(0, '.')
import exp_da as E
import kern
from proto_tent_root import tent_thresh

def gen_states():
    rng = random.Random(5150)
    pool = pickle.load(open('../pool30.pkl', 'rb'))
    out = []
    for k, (inst, opt, nd) in enumerate(pool):
        for trial in range(3):
            S, A, c = E.random_prefix(inst, rng, rng.choice([0.25, 0.4, 0.55]))
            out.append(dict(k=k, trial=trial, S=S, A=A, c=c))
    return pool, out

def main():
    pool, states = gen_states()
    rows = []
    t0 = time.time()
    for st in states:
        inst, opt, _ = pool[st['k']]
        S, A, c = st['S'], st['A'], st['c']
        L0 = E.lower_L0(inst, S, A, c)
        if L0 >= opt:
            continue
        LTH, nt, nw = tent_thresh(inst, S, A, c, opt + 2, L0)
        row = dict(st, L0=L0, LTH=LTH, iopt=opt)
        if LTH < opt:
            # genuine gap: exact state OPT
            so = kern.state_opt(inst, S, A, c)
            est, q, sl, bars = kern.zero_slack(inst, S, c, so - 1)
            nR = bin((1 << inst['n']) - 1 ^ S).count('1')
            t1 = time.time()
            K = kern.mus(inst, S, A, c, so - 1)
            tmus = time.time() - t1
            t2 = time.time()
            ok = kern.kernel_feasible(inst, S, A, c, so - 1, (1 << inst['n']) - 1 ^ S)
            tfull = time.time() - t2
            row.update(sopt=so, nR=nR, nbars=bin(bars).count('1'),
                       mus=(bin(K).count('1') if K is not None else None),
                       mus_ids=(list(kern.bits(K)) if K is not None else None),
                       tmus=round(tmus, 4), tfull=round(tfull, 4), fullok=ok)
        rows.append(row)
        print(st['k'], st['trial'], 'L0', L0, 'LTH', LTH, 'iopt', opt,
              row.get('sopt'), 'nR', row.get('nR'), 'bars', row.get('nbars'),
              'mus', row.get('mus'), 't', row.get('tfull'), flush=True)
    json.dump(rows, open('states.json', 'w'), indent=1)
    print('elapsed', round(time.time() - t0, 2))
    g = [r for r in rows if r.get('mus') is not None]
    print('gaps', len(g), 'mus sizes', [r['mus'] for r in g], 'nR', [r['nR'] for r in g])

if __name__ == '__main__':
    main()
