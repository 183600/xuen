import sys, json, pickle, random, time
sys.path.insert(0, '..'); sys.path.insert(0, '.'); sys.path.insert(0, '../v07')
import exp_da as E, ip, cbj
from kern import bits

# ---------------- families
def mk(p, m, pred=None):
    n = len(p)
    if pred is None:
        pred = [[] for _ in range(n)]
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'ep': 0.0 if pred is None else 0.05, 'pmax': max(p)}
    E.compute_desc(inst)
    inst['pmask'] = [sum(1 << j for j in inst['pred'][i]) for i in range(n)]
    return inst

def bin_opt(p, m):
    states = {(0,) * m}
    for s in p:
        ns = set()
        for L in states:
            for k in range(m):
                t = list(L); t[k] += s
                ns.add(tuple(sorted(t)))
        states = ns
    return min(max(L) for L in states)

def gen_part(n, m, rng, maxp=9):
    for _ in range(50000):
        p = [rng.randint(2, maxp) for _ in range(n)]
        tot = sum(p)
        if tot % m:
            continue
        # target: OPT = ceil(tot/m)+1 and no packing at H=ceil(tot/m)
        H = (tot + m - 1) // m
        # exact bin opt
        opt = bin_opt(p, m)
        if opt == H + 1:
            return p, H, opt
    return None

def gen_part2(n, rng):
    # m=2 exact-volume: total even, no subset half, opt = half+1
    for _ in range(50000):
        p = [rng.randint(2, 9) for _ in range(n)]
        tot = sum(p)
        if tot % 2:
            continue
        h = tot // 2
        b = 1
        for s in p:
            b |= b << s
        if (b >> h) & 1:
            continue
        states = {(0, 0)}
        # direct subset-sum opt
        opt = min(max(s, tot - s) for s in range(tot + 1) if (b >> s) & 1)
        if opt == h + 1:
            return p, h, opt
    return None

def run(inst, opt, H):
    n = inst['n']; S = 0; A = (0,) * inst['m']; c = (-1,) * n
    L0 = E.lower_L0(inst, S, A, c)
    LD = ip.dff_lb(inst, S, A, c)
    t0 = time.time(); LP = ip.pack_lb(inst, S, A, c, L0, opt); t_lp = time.time() - t0
    out = dict(n=n, m=inst['m'], p=inst['p'], OPT=opt, H=H, L0=L0, LDFF=LD,
               LPACK=LP, t_packlb=round(t_lp, 5))
    for name, pack, cb in (('base', False, False), ('pack', True, False),
                           ('pack_cbj', True, True)):
        t0 = time.time()
        st, sc, s = cbj.decide(inst, S, A, c, H, nodecap=3_000_000,
                               use_pack=pack, use_cbj=cb)
        out[name] = dict(status=st, nodes=s.get('nodes'), t=round(time.time() - t0, 4),
                         cbj=s.get('cbj', 0), timeout=s.get('timeout', False))
    return out

def main():
    rng = random.Random(20261022)
    dense = pickle.load(open('../pool30.pkl', 'rb'))
    D = []
    for k, (inst, opt, nd) in enumerate(dense):
        r = run(inst, opt, opt - 1); r['k'] = k; D.append(r)
        print('D', k, r['L0'], r['LDFF'], r['LPACK'], opt,
              r['base']['nodes'], r['pack']['nodes'], r['pack_cbj']['nodes'], flush=True)
    P2 = []
    while len(P2) < 30:
        n = rng.choice([10, 11, 12, 13])
        g = gen_part2(n, rng)
        if not g:
            continue
        p, H, opt = g
        inst = mk(p, 2)
        r = run(inst, opt, H); r['k'] = len(P2); P2.append(r)
        print('P2', r['k'], n, H, opt, r['L0'], r['LDFF'], r['LPACK'],
              r['base']['nodes'], r['pack']['nodes'], flush=True)
    P3 = []
    while len(P3) < 20:
        n = rng.choice([9, 10, 11, 12])
        g = gen_part(n, 3, rng, maxp=7)
        if not g:
            continue
        p, H, opt = g
        inst = mk(p, 3)
        r = run(inst, opt, H); r['k'] = len(P3); P3.append(r)
        print('P3', r['k'], n, H, opt, r['L0'], r['LDFF'], r['LPACK'],
              r['base']['nodes'], r['pack']['nodes'], flush=True)
    json.dump(dict(dense=D, part2=P2, part3=P3), open('results.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
