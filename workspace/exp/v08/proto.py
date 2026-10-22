"""v0.8 prototype: PACK certificate inside exact DEC + core extraction."""
import sys, time
sys.path.insert(0, '..'); sys.path.insert(0, '.'); sys.path.insert(0, '../v07')
import exp_da as E
from kern import bits

NEG = -1


def eligible(inst, i, A, est, q, H):
    p = inst['p']
    out = []
    for k in range(len(A)):
        if max(A[k], est[i]) + p[i] + q[i] <= H:
            out.append(k)
    return out


def pack2_sizes(sizes, caps):
    """Exact 2-bin subset-sum, caps are (c0,c1)."""
    if not sizes:
        return True
    tot = sum(sizes)
    if tot > caps[0] + caps[1]:
        return False
    lo = max(0, tot - caps[1]); hi = caps[0]
    if lo > hi:
        return False
    bits_ = 1
    for s in sizes:
        bits_ |= bits_ << s
    mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return (bits_ & mask) != 0


def pack_feasible(inst, rem, A, est, q, H, m=None):
    """Necessary capacity/integrality condition at a DEC node.
    Returns (ok, witness assignment or None)."""
    p = inst['p']
    m = m or len(A)
    caps = [H - A[k] for k in range(m)]
    if any(c < 0 for c in caps):
        return False, None
    forced = [None] * m
    flex = []
    for i in bits(rem):
        el = eligible(inst, i, A, est, q, H)
        if not el:
            return False, None
        if len(el) == 1:
            k = el[0]
            if p[i] > caps[k]:
                return False, None
            caps[k] -= p[i]
            forced[k] = i
        else:
            flex.append(i)
    if m == 2:
        sizes = [p[i] for i in flex]
        ok = pack2_sizes(sizes, caps)
        return ok, None
    # general small-m DFS with L2 lower bound + symmetry
    sizes = sorted([p[i] for i in flex], reverse=True)
    caps = sorted(caps, reverse=True)
    if sum(sizes) > sum(caps):
        return False, None
    # L2: items > c/2
    n = len(sizes)
    for t in range(n):
        big = [s for s in sizes if 2 * s > caps[0]]
    # simpler exact DFS
    bins = caps[:]
    def dfs(idx):
        if idx == n:
            return True
        s = sizes[idx]
        seen = set()
        for k in range(m):
            if bins[k] < s or bins[k] in seen:
                continue
            seen.add(bins[k])
            bins[k] -= s
            if dfs(idx + 1):
                bins[k] += s
                return True
            bins[k] += s
        return False
    ok = dfs(0)
    return ok, None


def decide(inst, S, A, c, H, nodecap=200_000, use_sym=True, memo=None,
           use_energy=True, use_pack=True):
    n, p, m = inst['n'], inst['p'], len(A)
    full = (1 << n) - 1
    R = full ^ S
    if R == 0:
        return (max(A) <= H, [], {})
    est, q = E.heads_tails(inst, S, c)
    if max(A) > H:
        return (False, None, {})
    if memo is None:
        memo = {'bad': {}}
    bad = memo['bad']
    cls = {}
    if use_sym:
        for i in bits(R):
            sig = (p[i], tuple(inst['pred'][i]), tuple(inst['succ'][i]))
            cls.setdefault(sig, []).append(i)
        cls = {i: g[0] for g in cls.values() if len(g) > 1 for i in g}
    nodes = [0]; hits = [0]; packs = [0]
    stat = {'pack_prunes': 0}
    sump_all = sum(p[i] for i in bits(R))

    def rec(rem, A, est, h, sump):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if rem == 0:
            return []
        key = (rem, A) + tuple(est[i] for i in bits(rem))
        b = bad.get(key, NEG)
        if h <= b:
            hits[0] += 1
            return None
        for i in bits(rem):
            if est[i] + p[i] + q[i] > h:
                if h > bad.get(key, NEG):
                    bad[key] = h
                return None
        if use_energy and (sump + sum(A) + m - 1) // m > h:
            if h > bad.get(key, NEG):
                bad[key] = h
            return None
        if use_pack:
            packs[0] += 1
            ok, _ = pack_feasible(inst, rem, A, est, q, h, m)
            if not ok:
                stat['pack_prunes'] += 1
                if h > bad.get(key, NEG):
                    bad[key] = h
                return None
        ready = [i for i in bits(rem) if not (inst['pmask'][i] & rem)]
        ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        seen = set()
        for i in ready:
            r = cls.get(i, i)
            if use_sym and r in seen:
                continue
            seen.add(r)
            for k in range(m):
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h:
                    continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(nA)
                nest = list(est)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                sub = rec(rem & ~(1 << i), nA, tuple(nest), h, sump - p[i])
                if sub is not None:
                    return [(i, k, t)] + sub
        if h > bad.get(key, NEG):
            bad[key] = h
        return None

    try:
        out = rec(R, tuple(A), tuple(est), H, sump_all)
    except TimeoutError:
        return (None, None, {'nodes': nodes[0], 'hits': hits[0], 'packs': packs[0],
                             'pack_prunes': stat['pack_prunes'], 'timeout': True})
    return (out is not None, out,
            {'nodes': nodes[0], 'hits': hits[0], 'packs': packs[0],
             'pack_prunes': stat['pack_prunes']})
