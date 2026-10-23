"""BFS-PC (v2.3 prototype): breadth-first prefix-cut chain decomposition.

v2.2 (CPS) enumerated *all* full placements of a chain P and ran an exact
residual search at every leaf.  This file keeps the same soundness contract
(only a definite NO is returned as False) but replaces the flat placement
enumeration with a level-synchronous BFS over the prefix tree of P:

  * a node at depth t is a valid partial placement s_1..s_t;
  * every node is tested by a *monotone* necessary condition
    (windows + interval/energetic reasoning on the residual);
  * a failing node is a cut leaf: its whole subtree is discarded;
  * a surviving node at depth L (a full placement) is decided by the exact
    residual search of v2.2.

The pruned nodes form a cut of the placement tree.  When the search finishes
with NO, the cut is the certificate.  When the node budget is exhausted, the
*live* frontier (prefixes that pass every test and still admit a chain
completion) is a certified lower bound: no cut of the same test class can be
smaller than the number of live frontier nodes, and none can be shallower.

Full eligibility only (the capacity model is exact there); A is a machine
availability vector, est_i = min_k A_k at the root.
"""
import sys
sys.path.insert(0, 'exp/v25')
import cps_lib as C


def tails(inst):
    n, p = inst['n'], inst['p']
    q = [0] * n
    top = C._topo(inst, (1 << n) - 1)
    for i in reversed(top):
        best = 0
        for j in inst['succ'][i]:
            v = p[j] + q[j]
            if v > best:
                best = v
        q[i] = best
    return q


def windows_prefix(inst, rem, h, q, chain, s):
    """Windows with the chain prefix fixed at s; returns (r,d) or None."""
    n, p = inst['n'], inst['p']
    pos = {i: a for a, i in enumerate(chain[:len(s)])}
    top = C._topo(inst, rem)
    r = [0] * n
    d = [h - q[i] for i in range(n)]
    for i in top:
        if i in pos:
            r[i] = s[pos[i]]
        else:
            v = 0
            for u in inst['pred'][i]:
                if (rem >> u) & 1:
                    t = r[u] + p[u]
                    if t > v:
                        v = t
            r[i] = v
    for i in reversed(top):
        if i in pos:
            d[i] = s[pos[i]] + p[i]
        else:
            v = h - q[i]
            for w in inst['succ'][i]:
                if (rem >> w) & 1:
                    t = d[w] - p[w]
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


def er_ok(inst, rem, r, d, cap, fixed, max_intervals=400):
    """Mandatory-energy (energetic reasoning) necessary condition.

    For every interval [a,b), the processing that is *forced* inside [a,b)
    must fit into the residual capacity of [a,b).  Returns (ok, witness).
    """
    n, p = inst['n'], inst['p']
    tasks = [i for i in range(n)
             if ((rem >> i) & 1) and not ((fixed >> i) & 1)]
    if not tasks:
        return True, None
    pre = [0] * (len(cap) + 1)
    for t in range(len(cap)):
        pre[t + 1] = pre[t] + cap[t]
    pts = sorted(set([0, len(cap)] +
                     [r[i] for i in tasks] + [d[i] for i in tasks]))
    cnt = 0
    for ai, a in enumerate(pts):
        for b in pts[ai + 1:]:
            cnt += 1
            if cnt > max_intervals:
                return True, None
            dem = 0
            for i in tasks:
                m = p[i] - max(0, a - r[i]) - max(0, d[i] - b)
                if m > 0:
                    dem += m
            sup = pre[b] - pre[a]
            if dem > sup:
                return False, (a, b, dem, sup)
    return True, None


def clique_ok(inst, rem, r, d, m, fixed):
    """Pairwise-overlap (clique) necessary condition.

    Tasks whose window is inside [a,b) and whose processing exceeds (b-a)/2
    pairwise overlap in time, hence need distinct machines.
    """
    n, p = inst['n'], inst['p']
    tasks = [i for i in range(n)
             if ((rem >> i) & 1) and not ((fixed >> i) & 1)]
    if not tasks:
        return True, None
    pts = sorted(set([0] + [r[i] for i in tasks] + [d[i] for i in tasks]))
    for ai, a in enumerate(pts):
        for b in pts[ai + 1:]:
            half = (b - a) / 2.0
            cnt = 0
            for i in tasks:
                if r[i] >= a and d[i] <= b and p[i] > half:
                    cnt += 1
            if cnt > m:
                return False, (a, b, cnt, m)
    return True, None


def greedy_chain_live(inst, h, q, chain, s):
    """Can the fixed prefix be completed to a valid full placement of P?"""
    p = inst['p']
    end = s[-1] + p[chain[len(s) - 1]] if s else 0
    for a in range(len(s), len(chain)):
        i = chain[a]
        if end + p[i] > h - q[i]:
            return False
        end += p[i]
    return True


def enumerate_placements(inst, h, q, chain):
    """All valid full placements (only for small S; used to validate cuts)."""
    p = inst['p']
    L = len(chain)
    out = []

    def rec(a, prev_end, s):
        if a == L:
            out.append(tuple(s))
            return
        i = chain[a]
        lo = prev_end
        hi = h - q[i] - p[i]
        for t in range(lo, hi + 1):
            s.append(t)
            rec(a + 1, t + p[i], s)
            s.pop()

    rec(0, 0, [])
    return out


def bfs_pc(inst, h, budget=200000, er=True, clique=False, nodecap=300000,
           use_exact=True, stats=None):
    """Return False (certified NO), True (feasible schedule found), or None.

    Only False is a certificate; None means budget/cap/unknown.
    """
    if stats is None:
        stats = {}
    n, m, p = inst['n'], inst['m'], inst['p']
    rem = (1 << n) - 1
    q = tails(inst)
    chain, cp = C.critical_path(inst, rem, [0] * n, q)
    S = h - cp
    stats.update(S=S, L=len(chain), chain=chain)
    if S < 0:
        return False
    L = len(chain)
    stats['placements_total'] = len(enumerate_placements(inst, h, q, chain)) \
        if S <= 12 and L <= 12 else None

    # residual capacity of the empty prefix: all m machines
    base_cap = [m] * h
    cut = []
    depth_expanded = 0
    seen_res_nodes = 0

    # root test: the empty prefix is a node like any other
    w = windows_prefix(inst, rem, h, q, chain, ())
    if w is None:
        stats.update(nodes=1, cut=0, verdict='NO-root')
        stats['cut_nodes'] = [()]
        return False
    if er:
        ok, _wit = er_ok(inst, rem, w[0], w[1], base_cap, 0)
        if not ok:
            stats.update(nodes=1, cut=1, verdict='NO-root-er')
            stats['cut_nodes'] = [()]
            return False
    if clique:
        ok, _wit = clique_ok(inst, rem, w[0], w[1], m, 0)
        if not ok:
            stats.update(nodes=1, cut=1, verdict='NO-root-clique')
            stats['cut_nodes'] = [()]
            return False
    frontier = [()]
    stats['level_widths'] = []
    stats['live_widths'] = []
    while frontier:
        depth = len(frontier[0])          # nodes at this depth
        stats['level_widths'].append(len(frontier))
        # live lower bound for this frontier (all nodes passed the tests)
        live = [s for s in frontier if greedy_chain_live(inst, h, q, chain, s)]
        stats['live_widths'].append(len(live))
        if sum(stats['level_widths']) > budget:
            stats['verdict'] = 'UNK-budget'
            stats['lb_depth'] = depth + 1
            stats['lb_size'] = len(live)
            stats['frontier'] = frontier
            return None
        if depth == L:
            # full placements: exact residual at every leaf
            unknown = False
            for s in frontier:
                seen_res_nodes += 1
                fixed = 0
                for i in chain:
                    fixed |= 1 << i
                cap = list(base_cap)
                for a, i in enumerate(chain):
                    for t in range(s[a], min(h, s[a] + p[i])):
                        cap[t] -= 1
                rr = C._residual_feasible(inst, rem, (0,) * m, [0] * n, q, h,
                                          list(chain), list(s),
                                          nodecap=nodecap, stats=stats)
                depth_expanded += 1
                if rr is True:
                    stats.update(nodes=depth_expanded, cut=len(cut),
                                 verdict='YES')
                    return True
                if rr is None:
                    unknown = True
                else:
                    cut.append(s)
            if unknown:
                stats['verdict'] = 'UNK-rescap'
                stats['cut'] = len(cut)
                return None
            stats.update(nodes=depth_expanded, cut=len(cut), verdict='NO')
            stats['cut_nodes'] = cut
            return False

        # expand one level
        nxt = []
        i_next = chain[depth]
        for s in frontier:
            end = s[-1] + p[chain[depth - 1]] if s else 0
            used = end - sum(p[chain[u]] for u in range(depth))
            for g in range(0, S - used + 1):
                t = end + g
                if t + p[i_next] > h - q[i_next]:
                    continue
                sn = s + (t,)
                depth_expanded += 1
                w = windows_prefix(inst, rem, h, q, chain, sn)
                if w is None:
                    cut.append(sn)
                    continue
                if er:
                    fixed = 0
                    for a in range(len(sn)):
                        fixed |= 1 << chain[a]
                    cap = list(base_cap)
                    for a in range(len(sn)):
                        ii = chain[a]
                        for tt in range(sn[a], min(h, sn[a] + p[ii])):
                            cap[tt] -= 1
                    ok, wit = er_ok(inst, rem, w[0], w[1], cap, fixed)
                    if not ok:
                        cut.append(sn)
                        continue
                    if clique:
                        ok, wit = clique_ok(inst, rem, w[0], w[1], m, fixed)
                        if not ok:
                            cut.append(sn)
                            continue
                nxt.append(sn)
        frontier = nxt
    stats.update(nodes=depth_expanded, cut=len(cut), verdict='NO')
    stats['cut_nodes'] = cut
    return False


def cut_covers(inst, h, q, chain, cut):
    """Independent check: every valid placement has a prefix in cut."""
    cutset = set(cut)
    for s in enumerate_placements(inst, h, q, chain):
        ok = False
        for t in range(len(s) + 1):
            if tuple(s[:t]) in cutset:
                ok = True
                break
        if not ok:
            return False
    return True


def check_cut(inst, h, chain, cut, er=True, clique=False, nodecap=300000):
    """Replay checker: every cut node must *fail* a sound test, and the cut
    must cover every valid placement.  Returns (ok, reason)."""
    n, m, p = inst['n'], inst['m'], inst['p']
    rem = (1 << n) - 1
    q = tails(inst)
    L = len(chain)
    base_cap = [m] * h
    for c in cut:
        if len(c) > L:
            return False, ('depth', c)
        w = windows_prefix(inst, rem, h, q, chain, c)
        if w is None:
            continue
        if len(c) < L:
            fixed = 0
            for a in range(len(c)):
                fixed |= 1 << chain[a]
            cap = list(base_cap)
            for a in range(len(c)):
                ii = chain[a]
                for tt in range(c[a], min(h, c[a] + p[ii])):
                    cap[tt] -= 1
            if er:
                ok, _ = er_ok(inst, rem, w[0], w[1], cap, fixed)
                if not ok:
                    continue
            if clique:
                ok, _ = clique_ok(inst, rem, w[0], w[1], m, fixed)
                if not ok:
                    continue
            return False, ('node-passes', c)
        rr = C._residual_feasible(inst, rem, (0,) * m, [0] * n, q, h,
                                  list(chain), list(c), nodecap=nodecap)
        if rr is False:
            continue
        return False, ('leaf-not-no', c)
    if not cut_covers(inst, h, q, chain, cut):
        return False, 'not-covering'
    return True, 'ok'
