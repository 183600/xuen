"""Hybrid: DFS first (SAT-biased), LLS fallback (UNSAT-biased)."""
import sys, time
sys.path.insert(0, 'exp/v14')
import sp, lls


def solve(inst, h, dfs_budget=None, K=48):
    if dfs_budget is None:
        dfs_budget = 4 * inst['n'] + 32
    t0 = time.time()
    (ok, sched), st = sp.decide(inst, h, mode='sub', nodecap=dfs_budget, K=K)
    td = time.time() - t0
    if not st.get('timeout'):
        return dict(ok=ok, sched=sched, engine='dfs', dfs_nodes=st['nodes'],
                    dfs_t=td, lls_labels=0, lls_t=0.0, t=td, st=st)
    t1 = time.time()
    (ok2, _), st2 = lls.decide_lls(inst, h)
    tl = time.time() - t1
    return dict(ok=ok2, sched=None, engine='lls', dfs_nodes=st['nodes'],
                dfs_t=td, lls_labels=st2['labels'], lls_t=tl, t=td + tl, st=st2)


def rand_inst(rng, n, m, pmax=10, ep=0.18, elig_p=1.0):
    p = [rng.randint(2, pmax) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < ep:
                pred[j].append(i)
        if j > 0 and not pred[j] and rng.random() < 0.7:
            pred[j].append(rng.randrange(j))
    elig = []
    for i in range(n):
        if elig_p >= 1.0:
            elig.append(list(range(m)))
        else:
            e = [k for k in range(m) if rng.random() < elig_p]
            if not e:
                e = [rng.randrange(m)]
            elig.append(e)
    return sp.make_inst(p, m, pred, elig)
