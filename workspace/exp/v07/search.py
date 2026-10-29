"""v0.7 search: v0.6 focal + L_A at every node + optional GE certificates."""
import sys, time
sys.path.insert(0, '..'); sys.path.insert(0, '.')
import exp_da as E
import ge


def LB(inst, S, A, c):
    return max(E.lower_L0(inst, S, A, c), ge.head_bound(inst, S, A, c))


def run(inst, budget=900, omega=2, Bf=32, Kdom=60, root='TENT',
        ge_root=False, ge_point=False, ge_nodes=200_000, band=2, ge_small=0):
    n = inst['n']; full = (1 << n) - 1
    def G(S, A, c):
        return min(E.greedy(inst, S, A, c, r) for r in ('CP', 'LPT', 'MWKR'))
    S0, A0, c0 = 0, (0, 0), (-1,) * n
    U = G(S0, A0, c0)
    L0 = float('-inf')
    if root == 'TENT':
        L0, _, _ = __import__('proto_tent_root').tent_thresh(inst, S0, A0, c0, U, LB(inst, S0, A0, c0))
        L0 = max(L0, LB(inst, S0, A0, c0))
    else:
        L0 = LB(inst, S0, A0, c0)
    t_ge = 0.0; ge_nodes_total = 0; ge_ok = 0
    gmemo = ge.make_memo()
    if ge_root and L0 < U:
        proved, U2, st = ge.ge_step(inst, S0, A0, c0, U, gmemo, nodecap=ge_nodes)
        t_ge += st.get('time', 0.0)
        ge_nodes_total += st.get('nodes', 0)
        if proved:
            L0 = U2
        U = U2
    F0 = L0
    rootv = {'S': S0, 'A': A0, 'c': c0, 'F': F0, 'f': max(max(A0), F0), 'id': 0}
    Open = [rootv]; nxt = 1
    Dom = {0: [(A0, tuple([0] * n))]}
    steps = 0; t0 = time.time()
    while Open and steps < budget:
        fmin = min(v['f'] for v in Open)
        if fmin >= U:
            break
        phi = [v for v in Open if v['f'] <= fmin + omega]
        phi.sort(key=lambda v: (v['f'], v['id']))
        cand = phi[:Bf]
        bestv = None; bestg = None
        for v in cand:
            g = G(v['S'], v['A'], v['c'])
            if g < U:
                U = g
            if bestv is None or (g, v['f'], v['id']) < (bestg, bestv['f'], bestv['id']):
                bestv, bestg = v, g
        v = bestv; Open.remove(v); steps += 1
        for (cs, ca, cc) in E.gen_children(inst, v['S'], v['A'], v['c']):
            if cs == full:
                if max(ca) < U:
                    U = max(ca)
                continue
            l0 = LB(inst, cs, ca, cc)
            if l0 >= U:
                continue
            wins, est0, q0 = E.make_windows(inst, cs, ca, cc, U)
            if wins and E.infeasible_at(inst, cs, ca, cc, U - 1, est0, q0, wins):
                continue
            if ge_point and ((U - max(max(ca), max(v['F'], l0))) <= band
                             or (ge_small and bin(((1 << n) - 1) ^ cs).count('1') <= ge_small)):
                proved, U2, st = ge.ge_step(inst, cs, ca, cc, U, gmemo, nodecap=ge_nodes)
                t_ge += st.get('time', 0.0)
                ge_nodes_total += st.get('nodes', 0)
                if U2 < U:
                    U = U2
                if proved:
                    ge_ok += 1
                    continue
            g = G(cs, ca, cc)
            if g < U:
                U = g
            Fw = max(v['F'], l0); fw = max(max(ca), Fw)
            if fw >= U:
                continue
            est = est0
            bucket = Dom.setdefault(cs, [])
            dom = False
            for (A2, e2) in bucket:
                if all(A2[k] <= ca[k] for k in range(len(ca))) and \
                   all(e2[i] <= est[i] for i in range(n) if not ((cs >> i) & 1)):
                    dom = True; break
            if dom:
                continue
            bucket[:] = [(A2, e2) for (A2, e2) in bucket
                         if not (all(ca[k] <= A2[k] for k in range(len(ca))) and
                                 all(est[i] <= e2[i] for i in range(n) if not ((cs >> i) & 1)))]
            if len(bucket) < Kdom:
                bucket.append((ca, est))
            Open.append({'S': cs, 'A': ca, 'c': cc, 'F': Fw, 'f': fw, 'id': nxt})
            nxt += 1
    L = max(L0, min((x['f'] for x in Open), default=L0))
    return {'steps': steps, 'U': U, 'L': L, 'Lg': L0, 'open': len(Open),
            'time': time.time() - t0, 't_ge': t_ge, 'ge_nodes': ge_nodes_total,
            'ge_pruned': ge_ok, 'memo_internal': gmemo.get('internal', 0),
            'memo_reuse': gmemo.get('reuse', 0), 'memo_bad': len(gmemo['bad'])}
