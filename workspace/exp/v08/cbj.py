"""v0.8 prototype: exact DEC with conflict-directed backjumping (CBJ).

Conflict sets are bitmasks of decision levels (0..n-1).  A deadline failure at
job i has conflict set = support(est_i), the decisions that produced the value
of est_i.  Energy / packing / memo failures depend on the whole prefix, so their
conflict set is ALL.
"""
import sys
sys.path.insert(0, '..'); sys.path.insert(0, '.'); sys.path.insert(0, '../v07')
import exp_da as E
from kern import bits

NEG = -1


def _pack2_sizes(sizes, caps):
    if not sizes:
        return True
    tot = sum(sizes)
    if tot > caps[0] + caps[1]:
        return False
    lo = max(0, tot - caps[1]); hi = caps[0]
    if lo > hi:
        return False
    b = 1
    for s in sizes:
        b |= b << s
    mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return (b & mask) != 0


def pack_feasible(inst, rem, A, est, q, H, m):
    p = inst['p']
    caps = [H - A[k] for k in range(m)]
    if any(c < 0 for c in caps):
        return False
    flex = []
    for i in bits(rem):
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        if not el:
            return False
        if len(el) == 1:
            k = el[0]
            if p[i] > caps[k]:
                return False
            caps[k] -= p[i]
        else:
            flex.append(i)
    if m == 2:
        return _pack2_sizes([p[i] for i in flex], caps)
    items = []
    for i in flex:
        el = [k for k in range(m) if max(A[k], est[i]) + p[i] + q[i] <= H]
        items.append((len(el), -p[i], i, el))
    items.sort()
    bins = caps[:]
    ln = len(items)
    def dfs(idx):
        if idx == ln:
            return True
        _, negp, i, el = items[idx]
        s = -negp
        for k in el:
            if bins[k] < s:
                continue
            bins[k] -= s
            if dfs(idx + 1):
                bins[k] += s
                return True
            bins[k] += s
        return False
    return dfs(0)


def decide(inst, S0, A0, c0, H, nodecap=500_000, use_sym=True, memo=None,
           use_energy=True, use_pack=True, use_cbj=True):
    n, p, m = inst['n'], inst['p'], len(A0)
    full = (1 << n) - 1
    if (full ^ S0) == 0:
        return (max(A0) <= H, [], {'nodes': 0, 'cbj': 0})
    if max(A0) > H:
        return (False, None, {'nodes': 0, 'cbj': 0})
    if memo is None:
        memo = {'bad': {}}
    bad = memo['bad']
    gid = [-1] * n
    if use_sym:
        groups = {}
        for i in bits(full ^ S0):
            sig = (p[i], tuple(inst['pred'][i]), tuple(inst['succ'][i]))
            groups.setdefault(sig, []).append(i)
        for gi, g in enumerate(groups.values()):
            if len(g) > 1:
                for i in g:
                    gid[i] = gi
    nodes = [0]; hits = [0]; packs = [0]; jumps = [0]
    pred = inst['pred']; succ = inst['succ']; pm = inst['pmask']

    def supports(S, c, csup):
        est = [0] * n; se = [0] * n
        for i in range(n):
            if (S >> i) & 1:
                est[i] = c[i]; se[i] = csup[i]
                continue
            best = 0; sb = 0
            for j in pred[i]:
                if (S >> j) & 1:
                    t = c[j]; st = csup[j]
                else:
                    t = est[j] + p[j]; st = se[j]
                if t > best:
                    best = t; sb = st
                elif t == best:
                    sb |= st
            est[i] = best; se[i] = sb
        return est, se

    def tails(S):
        q = [0] * n
        for i in range(n - 1, -1, -1):
            if not ((S >> i) & 1):
                bb = 0
                for j in succ[i]:
                    if not ((S >> j) & 1):
                        bb = max(bb, p[j] + q[j])
                q[i] = bb
        return q

    def rec(S, A, c, csup, asup, q, h, sump):
        rem = full ^ S
        depth = bin(S).count('1')
        cur = (1 << (depth - 1)) if depth else 0
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if rem == 0:
            return [], 0
        est, se = supports(S, c, csup)
        key = (rem, A) + tuple(est[i] for i in bits(rem))
        b = bad.get(key, NEG)
        if h <= b:
            hits[0] += 1
            return None, ((1 << depth) - 1)
        viol = [i for i in bits(rem) if est[i] + p[i] + q[i] > h]
        if viol:
            i = min(viol, key=lambda x: (bin(se[x]).count('1'), x))
            if h > bad.get(key, NEG):
                bad[key] = h
            return None, se[i]
        if use_energy and (sump + sum(A) + m - 1) // m > h:
            if h > bad.get(key, NEG):
                bad[key] = h
            return None, ((1 << depth) - 1)
        if use_pack and not pack_feasible(inst, rem, A, est, q, h, m):
            if h > bad.get(key, NEG):
                bad[key] = h
            return None, ((1 << depth) - 1)
        ready = [i for i in bits(rem) if not (pm[i] & rem)]
        ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        seen = set()
        conf = 0
        for i in ready:
            if use_sym and gid[i] >= 0:
                if gid[i] in seen:
                    continue
                seen.add(gid[i])
            for k in range(m):
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h:
                    continue
                nA = list(A); nA[k] = t + p[i]; nA = tuple(nA)
                nc = list(c); nc[i] = t + p[i]; nc = tuple(nc)
                if A[k] > est[i]:
                    st = asup[k]
                elif est[i] > A[k]:
                    st = se[i]
                else:
                    st = asup[k] | se[i]
                ncs = list(csup); ncs[i] = st | (1 << depth)
                nas = list(asup); nas[k] = ncs[i]
                sub, csub = rec(S | (1 << i), nA, nc, tuple(ncs), tuple(nas), q, h, sump - p[i])
                if sub is not None:
                    return [(i, k, t)] + sub, 0
                conf |= csub
                if use_cbj and cur and not (csub & cur):
                    jumps[0] += 1
                    if h > bad.get(key, NEG):
                        bad[key] = h
                    return None, conf
        if h > bad.get(key, NEG):
            bad[key] = h
        if use_cbj and cur:
            conf &= ~cur
        return None, conf

    est0, se0 = supports(S0, c0, tuple([0] * n))
    q0 = tails(S0)
    sump0 = sum(p[i] for i in bits(full ^ S0))
    try:
        out, conf = rec(S0, tuple(A0), tuple(c0), tuple([0] * n), tuple([0] * m), q0, H, sump0)
    except TimeoutError:
        return (None, None, {'nodes': nodes[0], 'hits': hits[0], 'packs': packs[0],
                             'cbj': jumps[0], 'timeout': True})
    return (out is not None, out,
            {'nodes': nodes[0], 'hits': hits[0], 'packs': packs[0], 'cbj': jumps[0],
             'conf': conf})
