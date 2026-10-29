"""Tabu search on the Pi-table.

TABU-P: find an m-partition whose parts are all single-machine feasible.
TABU-W: find a small witness subset W with beta(W) > m.
Both use the exact profile f[]; every accepted certificate is rechecked by
an independent DP, so tabu only controls *search*, never soundness.
"""
import random
INF = 10 ** 9


def _cost(f, masks, h):
    c = 0
    for S in masks:
        v = f[S]
        if v >= INF:
            c += 10 ** 6
        elif v > h:
            c += v - h
    return c


def _beta_local(f, k, m):
    """beta for a local task set given by a k-bit mask, using f on local bits."""
    # f is indexed by the *global local table* of the parent; here k == len(f)
    # bits, so this is only used when the caller passes the restricted table.
    pass


def tabu_partition(f, n, m, h, iters=400, tenure=7, stall=40, seed=0):
    """Return masks (list of m local bit masks) with cost 0, or None."""
    rng = random.Random(seed)
    p = [0] * n
    # recover sizes is not needed; LPT order by f[{i}] is meaningless, so use
    # a deterministic task order and random restarts.
    best = None
    for restart in range(8):
        masks = [0] * m
        order = list(range(n))
        rng.shuffle(order)
        for i in order:
            cand = []
            for k in range(m):
                v = f[masks[k] | (1 << i)]
                cand.append((max(0, v - h), k))
            cand.sort()
            masks[cand[0][1]] |= 1 << i
        cur = _cost(f, masks, h)
        if cur == 0:
            return masks
        tabu = {}
        for it in range(iters):
            best_move = None
            for i in range(n):
                src = 0
                for k in range(m):
                    if (masks[k] >> i) & 1:
                        src = k
                        break
                for k in range(m):
                    if k == src:
                        continue
                    nm = list(masks)
                    nm[src] ^= 1 << i
                    nm[k] |= 1 << i
                    c = _cost(f, nm, h)
                    is_tabu = tabu.get((i, src), -1) > it
                    if is_tabu and not (best is not None and c < best[0]):
                        continue
                    key = (c, rng.random())
                    if best_move is None or key < best_move[0]:
                        best_move = (key, i, src, nm)
            if best_move is None:
                break
            _, i, src, nm = best_move
            masks = nm
            tabu[(i, src)] = it + tenure
            cur = _cost(f, masks, h)
            if best is None or cur < best[0]:
                best = (cur, list(masks))
            if cur == 0:
                return masks
            if it > stall and best is not None and cur >= best[0]:
                break
    return None


def _beta_restricted(f_parent, n, W):
    """beta(W) using the parent profile f_parent on n bits."""
    idx = [i for i in range(n) if (W >> i) & 1]
    k = len(idx)
    M = 1 << k
    feas = [False] * M
    for L in range(1, M):
        S = 0
        for j in range(k):
            if (L >> j) & 1:
                S |= 1 << idx[j]
        feas[L] = f_parent[S] < INF
    g = [255] * M
    g[0] = 0
    for L in range(1, M):
        low = L & -L
        T = L
        best = 255
        while T:
            if (T & low) and feas[T]:
                v = g[L ^ T] + 1
                if v < best:
                    best = v
            T = (T - 1) & L
        g[L] = best
    return g[M - 1]


def tabu_witness(f, n, m, h, iters=200, tenure=5, seed=0):
    """Minimize |W| subject to beta(W) > m.  Returns (best_W, beta) or None."""
    rng = random.Random(seed)
    full = (1 << n) - 1
    beta = _beta_restricted(f, n, full)
    if beta <= m:
        return None
    bestW, bestb = full, beta
    W = full
    tabu = {}
    for it in range(iters):
        cand = [i for i in range(n) if (W >> i) & 1]
        rng.shuffle(cand)
        moved = False
        for i in cand:
            if tabu.get(i, -1) > it:
                continue
            W2 = W ^ (1 << i)
            if W2 == 0:
                continue
            b2 = _beta_restricted(f, n, W2)
            if b2 > m:
                W = W2
                moved = True
                if W.bit_count() < bestW.bit_count() or (W.bit_count() == bestW.bit_count() and b2 > bestb):
                    bestW, bestb = W, b2
                break
            else:
                tabu[i] = it + tenure
        if not moved:
            # one uphill removal (breaks the certificate), then try to repair
            cand = [i for i in range(n) if (W >> i) & 1 and tabu.get(i, -1) <= it]
            if not cand:
                break
            i = rng.choice(cand)
            W ^= 1 << i
            tabu[i] = it + tenure
    return bestW, _beta_restricted(f, n, bestW)
