"""Critical-Path Skeleton (CPS), v2.2.

MAP (v2.1) is a partition/matching relaxation: it compiles each machine's
single-machine postcondition f_k[S] and asks for an injective block->machine
assignment.  It deliberately forgets how blocks overlap in time, which is why
five held-out instances at h=OPT-1 have MAP=1 but are infeasible.

CPS fixes one *critical path* P of the precedence DAG and enumerates all of its
placements in the horizon.  For a fixed placement s:

  * every remaining task gets a release r_j and deadline d_j obtained by
    longest-path propagation through the fixed chain;
  * the chain occupies one machine on each interval [s_t, s_t+p_t), so the
    residual capacity is c(t) = #available machines at t - chain occupancy;
  * the residual tasks must be packed non-preemptively into [r_j,d_j) with
    residual precedence, at most c(t) overlapping.

If no placement admits a residual schedule, the state is NO.  This is a
certificate by case analysis on a chain: every feasible schedule has *some*
placement of P, and restricting it to R\\P gives a residual schedule.

For full eligibility the residual check is exact (interval graphs are perfect:
at most m overlapping intervals are m-colourable), so CPS is a complete
decision procedure on full-eligibility states (up to the node cap).  With
heterogeneous eligibility the capacity model is a relaxation; CPS=NO remains
sound, CPS=YES is only "unknown".
"""
from functools import lru_cache

INF = 10**9


def _topo(inst, rem):
    n = inst['n']
    indeg = [0] * n
    nodes = [i for i in range(n) if (rem >> i) & 1]
    for i in nodes:
        for j in inst['succ'][i]:
            if (rem >> j) & 1:
                indeg[j] += 1
    q = [i for i in nodes if indeg[i] == 0]
    out = []
    while q:
        u = q.pop()
        out.append(u)
        for v in inst['succ'][u]:
            if (rem >> v) & 1:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    return out


def critical_path(inst, rem, est, q):
    """Return (path, cp) with cp = max_i est_i+p_i+q_i and p(path)=cp-est_first."""
    n, p = inst['n'], inst['p']
    best, bi = -1, None
    for i in range(n):
        if (rem >> i) & 1:
            v = est[i] + p[i] + q[i]
            if v > best:
                best, bi = v, i
    if bi is None:
        return [], 0
    path = [bi]
    i = bi
    while True:
        cand = [j for j in inst['pred'][i]
                if ((rem >> j) & 1) and est[j] + p[j] == est[i]]
        if not cand:
            break
        j = max(cand, key=lambda z: est[z])
        path.append(j)
        i = j
    path.reverse()
    i = path[-1]
    while True:
        cand = [j for j in inst['succ'][i]
                if ((rem >> j) & 1) and p[j] + q[j] == q[i]]
        if not cand:
            break
        j = max(cand, key=lambda z: q[z])
        path.append(j)
        i = j
    return path, best


def _compositions(total, k, prefix=()):
    if k == 1:
        yield prefix + (total,)
        return
    for x in range(total + 1):
        yield from _compositions(total - x, k - 1, prefix + (x,))


def _windows(inst, rem, A, est, q, h, chain, s):
    """Release/deadline propagation with the chain times fixed."""
    n, p = inst['n'], inst['p']
    pos = {i: a for a, i in enumerate(chain)}
    P = set(chain)
    top = _topo(inst, rem)
    r = [est[i] for i in range(n)]
    d = [h - q[i] for i in range(n)]
    for i in top:
        if i in P:
            r[i] = s[pos[i]]
        else:
            v = est[i]
            for u in inst['pred'][i]:
                if (rem >> u) & 1:
                    t = r[u] + p[u]
                    if t > v:
                        v = t
            r[i] = v
    for i in reversed(top):
        if i in P:
            d[i] = s[pos[i]] + p[i]
        else:
            v = h - q[i]
            for vv in inst['succ'][i]:
                if (rem >> vv) & 1:
                    t = d[vv] - p[vv]
                    if t < v:
                        v = t
            d[i] = v
    for i in range(n):
        if not ((rem >> i) & 1):
            continue
        if r[i] + p[i] > d[i]:
            return None
        for j in inst['succ'][i]:
            if (rem >> j) & 1:
                if r[i] + p[i] > r[j] or d[i] > d[j] - p[j]:
                    return None
    return r, d


def _residual_feasible(inst, rem, A, est, q, h, chain, s,
                       nodecap=300000, stats=None):
    """Exact backtracking for the residual packing (full eligibility model).

    Returns True/False, or None if nodecap is hit.
    """
    w = _windows(inst, rem, A, est, q, h, chain, s)
    if w is None:
        return False
    r, d = w
    p, m = inst['p'], inst['m']
    P = set(chain)
    # capacity profile: available machines minus chain occupancy
    cap = [0] * h
    for t in range(h):
        cap[t] = sum(1 for k in range(m) if A[k] <= t)
    for a, i in enumerate(chain):
        for t in range(s[a], min(h, s[a] + p[i])):
            cap[t] -= 1
    if any(c < 0 for c in cap):
        return False
    res = [i for i in range(inst['n']) if ((rem >> i) & 1) and i not in P]
    rmask = 0
    for i in res:
        rmask |= 1 << i
    predm = {i: sum(1 << j for j in inst['pred'][i] if (rmask >> j) & 1)
             for i in res}
    seen = set()
    nodes = [0]

    def dfs(mask, cap, rel):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if mask == 0:
            return True
        key = (mask, tuple(cap),
               tuple(rel[i] for i in res if (mask >> i) & 1))
        if key in seen:
            return False
        if sum(p[i] for i in res if (mask >> i) & 1) > sum(cap):
            seen.add(key)
            return False
        avail = [i for i in res if (mask >> i) & 1 and not (predm[i] & mask)]
        best, bestopts = None, None
        for i in avail:
            lo, hi = rel[i], d[i] - p[i]
            opts = []
            for t in range(lo, hi + 1):
                if all(cap[t + u] > 0 for u in range(p[i])):
                    opts.append(t)
            if best is None or len(opts) < len(bestopts):
                best, bestopts = i, opts
                if not opts:
                    break
        if not bestopts:
            seen.add(key)
            return False
        i = best
        for t in bestopts:
            ncap = list(cap)
            for u in range(p[i]):
                ncap[t + u] -= 1
            nrel = list(rel)
            for j in inst['succ'][i]:
                if (mask >> j) & 1 and t + p[i] > nrel[j]:
                    nrel[j] = t + p[i]
            if dfs(mask ^ (1 << i), ncap, nrel):
                return True
        seen.add(key)
        return False

    try:
        ok = dfs(rmask, cap, list(r))
    except TimeoutError:
        ok = None
    if stats is not None:
        stats['cps_res_nodes'] = stats.get('cps_res_nodes', 0) + nodes[0]
        stats['cps_memo'] = max(stats.get('cps_memo', 0), len(seen))
    return ok


def cps_certify(inst, rem, A, est, q, h, tau=4, depth_cap=10**9,
                nodecap=300000, stats=None, residual='exact'):
    """Return False (certified NO), True (a schedule exists, full eligibility),
    or None (gate off / node cap / heterogeneous YES not verified).

    Only False is used as a pruning verdict by the search.
    """
    if stats is None:
        stats = {}
    nrem = bin(rem).count('1')
    if nrem == 0:
        return True
    if nrem > 22:
        return None
    chain, cp = critical_path(inst, rem, est, q)
    S = h - cp
    stats.update(cps_cp=cp, cps_S=S, cps_len=len(chain))
    if S < 0:
        return False
    if S > tau:
        return None
    if len(chain) > depth_cap:
        return None
    full_elig = all(len(set(inst['elig'][i])) == inst['m']
                    for i in range(inst['n']) if (rem >> i) & 1)
    L = len(chain)
    seen_place = 0
    unknown = False
    for g in _compositions(S, L + 1):
        s = []
        t = est[chain[0]] + g[0]
        ok = True
        for a, i in enumerate(chain):
            if a > 0:
                t = s[-1] + inst['p'][chain[a - 1]] + g[a]
            if t < est[i] or t + inst['p'][i] > h - q[i]:
                ok = False
                break
            s.append(t)
        if not ok:
            continue
        seen_place += 1
        if residual == 'flow':
            rr = _residual_flow(inst, rem, A, est, q, h, chain, s)
        else:
            rr = _residual_feasible(inst, rem, A, est, q, h, chain, s,
                                    nodecap=nodecap, stats=stats)
        if rr is True:
            stats['cps_placements'] = seen_place
            real = (residual == 'exact' and full_elig)
            stats['cps_result'] = 'YES' if real else 'UNK'
            return True if real else None
        if rr is None:
            unknown = True
    stats['cps_placements'] = seen_place
    if unknown:
        stats['cps_result'] = 'UNK'
        return None
    stats['cps_result'] = 'NO'
    return False


# ------------------------------------------------------------------ flow ablation
class _Dinic:
    def __init__(self, n):
        self.n = n
        self.g = [[] for _ in range(n)]

    def add(self, u, v, c):
        self.g[u].append([v, c, len(self.g[v])])
        self.g[v].append([u, 0, len(self.g[u]) - 1])

    def flow(self, s, t):
        from collections import deque
        res = 0
        while True:
            lvl = [-1] * self.n
            lvl[s] = 0
            q = deque([s])
            while q:
                u = q.popleft()
                for v, c, r in self.g[u]:
                    if c > 0 and lvl[v] < 0:
                        lvl[v] = lvl[u] + 1
                        q.append(v)
            if lvl[t] < 0:
                return res
            it = [0] * self.n

            def dfs(u, f):
                if u == t:
                    return f
                while it[u] < len(self.g[u]):
                    e = self.g[u][it[u]]
                    v, c, r = e
                    if c > 0 and lvl[v] == lvl[u] + 1:
                        d = dfs(v, min(f, c))
                        if d > 0:
                            e[1] -= d
                            self.g[v][r][1] += d
                            return d
                    it[u] += 1
                return 0

            while True:
                f = dfs(s, 10**9)
                if not f:
                    break
                res += f


def _residual_flow(inst, rem, A, est, q, h, chain, s):
    """Polynomial preemptive relaxation used only for the ablation."""
    w = _windows(inst, rem, A, est, q, h, chain, s)
    if w is None:
        return False
    r, d = w
    p, m = inst['p'], inst['m']
    P = set(chain)
    cap = [0] * h
    for t in range(h):
        cap[t] = sum(1 for k in range(m) if A[k] <= t)
    for a, i in enumerate(chain):
        for t in range(s[a], min(h, s[a] + p[i])):
            cap[t] -= 1
    if any(c < 0 for c in cap):
        return False
    tasks = [i for i in range(inst['n']) if ((rem >> i) & 1) and i not in P]
    if not tasks:
        return True
    S = 0
    T = 1 + len(tasks) + h
    din = _Dinic(T + 1)
    tot = 0
    for a, i in enumerate(tasks):
        din.add(S, 1 + a, p[i])
        tot += p[i]
        for t in range(max(0, r[i]), min(h, d[i])):
            din.add(1 + a, 1 + len(tasks) + t, 1)
    for t in range(h):
        if cap[t] > 0:
            din.add(1 + len(tasks) + t, T, cap[t])
    return din.flow(S, T) == tot
