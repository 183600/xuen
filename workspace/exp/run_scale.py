import sys, random, time, json
sys.path.insert(0, '.')
import pcb

def main():
    rng = random.Random(424242)
    rows = []
    tries = 0
    while len(rows) < 8 and tries < 300:
        tries += 1
        n = rng.choice([12, 13])
        inst = pcb.gen_instance(n, rng.choice([0.18, 0.22, 0.26]), 8, rng, 2)
        # best-first with a cap
        s = pcb.Solver(inst, front='off'); s.dom = True
        t = time.time()
        rb = s.search_bf(20000)
        bf_t = time.time() - t
        # idb + aco
        t0 = time.time()
        ub, ubp, tau = pcb.aco(inst, iters=10, ants=8, seed=9000 + len(rows))
        aco_t = time.time() - t0
        s2 = pcb.Solver(inst, front='off', U0=ub); s2.inc_path = ubp
        t = time.time()
        r = s2.search(300000)
        idb_t = time.time() - t
        chk = pcb.check_proof(inst, s2.proof, r['root_pid'], r['U'], s2.inc_path)
        row = {'n': n, 'ep': inst['ep'], 'bf_nodes': rb['nodes'],
               'bf_cap': rb['nodes'] >= 20000, 'bf_t': round(bf_t, 3),
               'bf_U': rb['U'], 'aco_gap0': ub - r['U'], 'aco_t': round(aco_t, 3),
               'idb_exp': r['expanded'], 'idb_t': round(idb_t, 3),
               'U': r['U'], 'check': chk[0],
               'total_t': round(aco_t + idb_t, 3)}
        rows.append(row)
        print(row, flush=True)
    json.dump(rows, open('final_scale.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
