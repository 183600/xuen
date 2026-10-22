import sys, random, time, pickle
sys.path.insert(0, '.')
import pcb

def main():
    rng = random.Random(20261022)
    cands = []
    tries = 0
    while len(cands) < 60 and tries < 5000:
        tries += 1
        n = rng.choice([9, 10])
        inst = pcb.gen_instance(n, rng.choice([0.2, 0.3, 0.4]),
                                rng.choice([6, 8, 10]), rng, 2)
        s = pcb.Solver(inst, front='off'); s.dom = True
        rb = s.search_bf(20000)
        if rb['nodes'] >= 40:
            cands.append(inst)
        if tries % 200 == 0:
            print('tries', tries, 'cands', len(cands), flush=True)
    print('cands', len(cands), 'tries', tries, flush=True)
    pool = []
    for k, inst in enumerate(cands):
        t = time.time()
        opt, nd, ok = pcb.exact_dp_iface(inst, 400000)
        dt = time.time() - t
        if ok:
            pool.append((inst, opt, nd))
        print(k, inst['n'], ok, nd, round(dt, 2), 'pool', len(pool), flush=True)
        if len(pool) >= 30:
            break
    pickle.dump(pool, open('pool30.pkl', 'wb'))
    print('saved', len(pool), flush=True)

if __name__ == '__main__':
    main()
