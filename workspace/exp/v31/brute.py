"""Brute force: assign (machine, start) to every job, DFS with pruning."""
def feasible(inst, h, est, q):
    n, m, p = inst['n'], inst['m'], inst['p']
    d = [h - q[i] for i in range(n)]
    E = [list(inst['elig'][i]) for i in range(n)]
    order = []
    indeg = [len(inst['pred'][i]) for i in range(n)]
    st = [i for i in range(n) if indeg[i] == 0]
    while st:
        i = st.pop(); order.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0: st.append(j)
    if len(order) < n: return False
    busy = [0] * m          # bitmask over time of machine occupancy
    fin = [0] * n
    def rec(k):
        if k == n: return True
        i = order[k]
        lo = est[i]
        for j in inst['pred'][i]:
            if fin[j] > lo: lo = fin[j]
        for t in range(lo, d[i] - p[i] + 1):
            for mk in E[i]:
                if busy[mk] & (((1 << p[i]) - 1) << t): continue
                busy[mk] |= ((1 << p[i]) - 1) << t
                fin[i] = t + p[i]
                if rec(k + 1): return True
                busy[mk] &= ~(((1 << p[i]) - 1) << t)
        return False
    return rec(0)

def true_opt(inst, hmax=40):
    import sys; sys.path[:0]=['exp/v13']
    import po
    est, q = po.heads_tails(inst, 0, [0] * inst['n'])
    for h in range(1, hmax + 1):
        if feasible(inst, h, est, q): return h
    return None
