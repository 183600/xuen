"""Final experiments for X-DUB/IDB (round 4)."""
import sys, random, time, json, pickle
sys.path.insert(0, '.')
import pcb, exp_da as E

CAP = 2_000_000


def r_from_c(inst, S, c):
    n = inst['n']
    r = [0] * n
    for i in range(n):
        if (S >> i) & 1:
            continue
        e = 0
        for j in inst['pred'][i]:
            if (S >> j) & 1 and c[j] > e:
                e = c[j]
        r[i] = e
    return r


def cdfs(inst, budget=200000):
    """Exact memo on (S,A,c); same bound kernel and child order."""
    n, m, full = inst['n'], inst['m'], inst['full']
    qs = inst['q_static']
    U = [pcb.upper_bound(inst)]
    memo = set()
    cnt = [0]
    exp = [0]

    def rec(S, A, c):
        cnt[0] += 1
        if cnt[0] > budget:
            raise RuntimeError
        key = (S, A, c)
        if key in memo:
            return
        memo.add(key)
        exp[0] += 1
        if S == full:
            if max(A) < U[0]:
                U[0] = max(A)
            return
        R = full ^ S
        r = r_from_c(inst, S, c)
        if pcb.lb_local(inst, R, r, A, U[0]) >= U[0]:
            return
        ch = E.gen_children(inst, S, A, c)
        ch.sort(key=lambda z: (-qs[(z[0] ^ S).bit_length() - 1],
                               max(z[1]), (z[0] ^ S).bit_length() - 1))
        for (S2, A2, c2) in ch:
            if max(A2) >= U[0]:
                continue
            rec(S2, A2, c2)

    try:
        rec(0, (0,) * m, (-1,) * n)
        ok = True
    except RuntimeError:
        ok = False
    return U[0], cnt[0], exp[0], ok


def fill_anytime(a, total, budgets):
    out = {}
    for b in budgets:
        vals = [v for k, v in a.items() if int(k) <= b]
        out[b] = min(vals) if vals else None
    return out


def main():
    pool = pickle.load(open('pool30.pkl', 'rb'))
    print('pool', len(pool), flush=True)

    rows = []
    for k, (inst, opt, nd) in enumerate(pool):
        row = {'k': k, 'n': inst['n'], 'ep': inst['ep'], 'pmax': inst['pmax'],
               'opt': opt, 'bf_ref': None, 'dp_nodes': nd}
        # ---- best-first family
        for tag, dom, inh in (('bf', True, True), ('bf_nodom', False, True),
                              ('bf_noinh', True, False)):
            s = pcb.Solver(inst, front='off')
            s.dom = dom
            t = time.time()
            r = s.search_bf(200000, inherit=inh)
            row[tag] = (r['nodes'], round(time.time() - t, 4), r['U'])
            assert r['U'] == opt, (tag, r['U'], opt)
            if tag == 'bf':
                row['bf_any'] = fill_anytime(r['anytime'], r['nodes'], (10, 25, 50, 100))
        # ---- interface memo DFS, greedy U0
        s = pcb.Solver(inst, front='off')
        t = time.time()
        r = s.search(400000)
        row['idb'] = (r['expanded'], round(time.time() - t, 4), r['U'])
        row['idb_any'] = fill_anytime(r['anytime'], r['nodes'], (10, 25, 50, 100))
        assert r['U'] == opt, ('idb', r['U'], opt)
        # ---- interface memo DFS + region front
        s = pcb.Solver(inst, front='weak')
        t = time.time()
        r = s.search(400000)
        row['idb_front'] = (r['expanded'], round(time.time() - t, 4), r['U'],
                            r['front_hits'], r['front_size'])
        assert r['U'] == opt
        # ---- c-key memo DFS
        uc, nc, ec, okc = cdfs(inst, 400000)
        row['cdfs'] = (ec, nc, uc)
        assert uc == opt
        # ---- ACO primal + interface memo DFS (proof checked)
        t0 = time.time()
        ub, ubp, tau = pcb.aco(inst, iters=4, ants=6, seed=1000 + k)
        aco_t = time.time() - t0
        s = pcb.Solver(inst, front='off', U0=ub)
        s.inc_path = ubp
        t = time.time()
        r = s.search(400000)
        search_t = time.time() - t
        chk = pcb.check_proof(inst, s.proof, r['root_pid'], r['U'], s.inc_path)
        row['aco'] = {'u0': ub, 'gap0': ub - opt, 'aco_t': round(aco_t, 4),
                      'exp': r['expanded'], 't': round(aco_t + search_t, 4),
                      'check': chk[0], 'nproof': len(s.proof),
                      'any': fill_anytime(r['anytime'], r['nodes'], (10, 25, 50))}
        assert r['U'] == opt, ('aco', r['U'], opt)
        row['bf_ref'] = row['bf'][0]
        rows.append(row)
        print(k, {kk: row[kk] for kk in ('n', 'opt', 'bf_ref')},
              'bf', row['bf'][0], 'idb', row['idb'][0],
              'front', row['idb_front'][0], 'cdfs', row['cdfs'][0],
              'aco_exp', row['aco']['exp'], 'chk', row['aco']['check'],
              flush=True)

    out = {'rows': rows, 'pool_tries': 0}
    json.dump(out, open('final_idb.json', 'w'), indent=1)
    # ---------------- aggregate
    def S(tag):
        return sum(r[tag][0] for r in rows)
    print('\n=== totals (30 instances) ===')
    print('bf', S('bf'), 'bf_nodom', S('bf_nodom'), 'bf_noinh', S('bf_noinh'),
          'idb', S('idb'), 'idb_front', S('idb_front'), 'cdfs', S('cdfs'))
    print('aco sum exp', sum(r['aco']['exp'] for r in rows),
          'check pass', sum(1 for r in rows if r['aco']['check']))
    print('aco gap0', sum(r['aco']['gap0'] for r in rows),
          'aco opt hits', sum(1 for r in rows if r['aco']['gap0'] == 0))
    print('wall bf', round(sum(r['bf'][1] for r in rows), 3),
          'idb', round(sum(r['idb'][1] for r in rows), 3),
          'aco+idb', round(sum(r['aco']['t'] for r in rows), 3))
    for b in (10, 25, 50, 100):
        gb = [r['bf_any'][b] - r['opt'] for r in rows if r['bf_any'][b] is not None]
        gi = [r['idb_any'][b] - r['opt'] for r in rows if r['idb_any'][b] is not None]
        print('anytime', b, 'bf gap', round(sum(gb) / len(gb), 3),
              'idb gap', round(sum(gi) / len(gi), 3))
    print('front hits total', sum(r['idb_front'][3] for r in rows),
          'front size', sum(r['idb_front'][4] for r in rows))
    print('wins idb vs bf', sum(1 for r in rows if r['idb'][0] < r['bf'][0]),
          'ties', sum(1 for r in rows if r['idb'][0] == r['bf'][0]))


if __name__ == '__main__':
    main()
