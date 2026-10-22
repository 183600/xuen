"""v1.2 PO-LC: Pareto-front memo for the capacity layer of DEC.

The state of a DEC node is sigma = (R, A, est) with a deadline h.
PACK(sigma, h) is monotone: if A' <= A componentwise and est' <= est, then
PACK(A) = YES  =>  PACK(A') = YES.  Hence the NO region is an up-set and is
generated exactly by its minimal elements (the Pareto frontier).

This module implements four memo strategies so they can be compared:
  exact   : hash memo on (R, A, est)                     (v1.1 baseline)
  canon   : + twin-machine canonicalisation of A
  front   : + Pareto front of certified PACK-NO vectors, keyed (R, h)
  sub     : + Pareto front of certified subtree-NO (est, A) pairs, keyed (R, h)
and a ladder switch (greedy / forcing / DFF before the exact table).
"""
import sys, time, json, random, itertools

NEG = -1


def bititer(x):
    while x:
        b = x & -x
        yield b.bit_length() - 1
        x ^= b


# ------------------------------------------------------------------ instance
def make_inst(p, m, pred=None, elig=None):
    n = len(p)
    if pred is None:
        pred = [[] for _ in range(n)]
    succ = [[] for _ in range(n)]
    for j in range(n):
        for i in pred[j]:
            succ[i].append(j)
    if elig is None:
        elig = [list(range(m)) for _ in range(n)]
    inst = {'n': n, 'm': m, 'p': p, 'pred': pred, 'succ': succ,
            'elig': elig}
    inst['pmask'] = [sum(1 << j for j in inst['pred'][i]) for i in range(n)]
    inst['desc'] = [0] * n
    for i in range(n - 1, -1, -1):
        d = 0
        for j in succ[i]:
            d |= (1 << j) | inst['desc'][j]
        inst['desc'][i] = d
    inst['full'] = (1 << n) - 1
    return inst


def heads_tails(inst, S, c):
    n, p, pred, succ = inst['n'], inst['p'], inst['pred'], inst['succ']
    est = [0] * n
    for i in range(n):
        if (S >> i) & 1:
            est[i] = c[i]
        else:
            e = 0
            for j in pred[i]:
                if (S >> j) & 1:
                    if c[j] > e:
                        e = c[j]
                else:
                    t = est[j] + p[j]
                    if t > e:
                        e = t
            est[i] = e
    q = [0] * n
    for i in range(n - 1, -1, -1):
        if (S >> i) & 1:
            continue
        b = 0
        for j in succ[i]:
            if not ((S >> j) & 1):
                t = p[j] + q[j]
                if t > b:
                    b = t
        q[i] = b
    return est, q


def tails(inst, rem):
    n, p, succ = inst['n'], inst['p'], inst['succ']
    q = [0] * n
    for i in range(n - 1, -1, -1):
        if not ((rem >> i) & 1):
            continue
        b = 0
        for j in succ[i]:
            if (rem >> j) & 1:
                t = p[j] + q[j]
                if t > b:
                    b = t
        q[i] = b
    return q


def node_elig(inst, i, A, est, h, q):
    p = inst['p']
    out = []
    for k in inst['elig'][i]:
        if max(A[k], est[i]) + p[i] + q[i] <= h:
            out.append(k)
    return out


# ------------------------------------------------------------------ capacity
def _pack2(sizes, caps):
    if not sizes:
        return True
    tot = sum(sizes)
    if tot > caps[0] + caps[1]:
        return False
    lo = max(0, tot - caps[1])
    hi = caps[0]
    if lo > hi:
        return False
    b = 1
    for s in sizes:
        b |= b << s
    mask = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
    return (b & mask) != 0


def _forced(inst, rem, A, est, q, h):
    """Resolve |E_i| = 1 tasks.  Returns (caps, flex) or None on overflow."""
    p = inst['p']
    caps = [h - A[k] for k in range(inst['m'])]
    if any(c < 0 for c in caps):
        return None
    flex = []
    for i in bititer(rem):
        el = node_elig(inst, i, A, est, h, q)
        if not el:
            return None
        if len(el) == 1:
            k = el[0]
            if p[i] > caps[k]:
                return None
            caps[k] -= p[i]
        else:
            flex.append((i, el))
    return caps, flex


def pack_exact(inst, rem, A, est, q, h, stats=None):
    r = _forced(inst, rem, A, est, q, h)
    if r is None:
        return False
    caps, flex = r
    if not flex:
        return True
    sizes = [inst['p'][i] for i, _ in flex]
    if sum(sizes) > sum(caps):
        return False
    m = inst['m']
    if m == 2:
        return _pack2(sizes, caps)
    eligs = [el for _, el in flex]
    order = sorted(range(len(sizes)), key=lambda j: (len(eligs[j]), -sizes[j]))
    sizes = [sizes[j] for j in order]
    eligs = [eligs[j] for j in order]
    n = len(sizes)
    bins = caps[:]
    # suffix volume for a cheap cut
    suf = [0] * (n + 1)
    for j in range(n - 1, -1, -1):
        suf[j] = suf[j + 1] + sizes[j]

    def dfs(j):
        if j == n:
            return True
        s = sizes[j]
        seen = set()
        for k in eligs[j]:
            b = bins[k]
            if b < s or b in seen:
                continue
            seen.add(b)
            bins[k] = b - s
            if dfs(j + 1):
                bins[k] = b
                return True
            bins[k] = b
        return False

    return dfs(0)


def pack_greedy(inst, rem, A, est, q, h):
    """tier 0: BFD on the flexible tasks after forcing.  True => PACK=YES."""
    r = _forced(inst, rem, A, est, q, h)
    if r is None:
        return False
    caps, flex = r
    load = [0] * len(caps)
    order = sorted(flex, key=lambda t: -inst['p'][t[0]])
    for i, el in order:
        s = inst['p'][i]
        cand = [k for k in el if load[k] + s <= caps[k]]
        if not cand:
            return False
        k = min(cand, key=lambda k: caps[k] - load[k] - s)
        load[k] += s
    return True


def pack_dff(inst, rem, A, est, q, h, stats=None):
    """tier 1: scalar DFF bound.  True => PACK=NO."""
    r = _forced(inst, rem, A, est, q, h)
    if r is None:
        return True
    caps, flex = r
    if not flex:
        return False
    Cmax = max(caps)
    sizes = [inst['p'][i] for i, _ in flex]
    for t in range(1, max(sizes) + 1):
        B = 0
        for s in sizes:
            B += s // t
        if B == 0:
            continue
        if t * ((B + inst['m'] - 1) // inst['m']) > Cmax:
            return True
    return False


# ------------------------------------------------------------------ frontier
def dominates(a, b):
    for x, y in zip(a, b):
        if x > y:
            return False
    return True


def front_query(front, A, cap=None):
    for a in front:
        if dominates(a, A):
            return True
    return False


def front_insert(front, A, K=48):
    """Insert into an antichain; returns True iff A carried new information."""
    for a in front:
        if dominates(a, A):
            return False
    keep = [a for a in front if not dominates(A, a)]
    keep.append(A)
    if K and len(keep) > K:
        # drop the element whose up-set [a, H]^m is smallest (least coverage)
        def vol(a):
            v = 1
            for x in a:
                v *= (1 + x)
            return v
        keep.sort(key=vol, reverse=True)
        keep = keep[:K]
    front[:] = keep
    return True


# ------------------------------------------------------------------ DEC
def decide(inst, h, mode='plain', nodecap=2_000_000, K=48, stats=None,
           greedy_order=False):
    """Exact DEC.  mode in {plain, canon, front, sub, ladder, ladder_front}."""
    n, p, m = inst['n'], inst['p'], inst['m']
    if 'full' not in inst:
        inst['full'] = (1 << n) - 1
    if 'pmask' not in inst:
        inst['pmask'] = [sum(1 << j for j in inst['pred'][i]) for i in range(n)]
    if 'elig' not in inst:
        inst['elig'] = [list(range(m)) for _ in range(n)]
    full = inst['full']
    if stats is None:
        stats = {}
    st = {'nodes': 0, 'memo_hits': 0, 'pack_calls': 0, 'pack_front_hits': 0,
          'per_rem': {},
          'sub_front_hits': 0, 'tables': 0, 'table_states': 0,
          'front_sizes': [], 'inserts': 0, 'greedy_yes': 0, 'dff_no': 0}
    use_canon = mode in ('canon', 'front', 'sub', 'subonly', 'subeq', 'ladder_front', 'full')
    use_pack_front = mode in ('front', 'sub', 'ladder_front', 'full')
    use_sub_front = mode in ('sub', 'subonly', 'subeq', 'full')
    use_ladder = mode in ('ladder', 'ladder_front', 'full')
    bad = {}                       # (rem, A, est) -> failed deadline
    F_pack = {}                    # (rem, h) -> [A]
    F_sub = {}                     # (rem, h) -> [(est, A)]
    twin_cache = {}

    def twins(rem):
        key = rem
        r = twin_cache.get(key)
        if r is not None:
            return r
        groups = {}
        for k in range(m):
            col = tuple(sorted(i for i in bititer(rem) if k in inst['elig'][i]))
            groups.setdefault(col, []).append(k)
        blocks = [g for g in groups.values() if len(g) > 1]
        twin_cache[key] = blocks
        return blocks

    def canonA(rem, A):
        blocks = twins(rem)
        if not blocks:
            return A
        out = list(A)
        for g in blocks:
            vals = sorted((out[k] for k in g), reverse=True)
            for k, v in zip(g, vals):
                out[k] = v
        return tuple(out)

    def rec(rem, A, est, sump):
        st['nodes'] += 1
        if st['nodes'] > nodecap:
            raise TimeoutError
        if rem == 0:
            return []
        q = tails(inst, rem)
        estt = tuple(est[i] for i in bititer(rem))
        keyA = canonA(rem, A) if use_canon else A
        key = (rem, keyA, estt)
        if bad.get(key, NEG) >= h:
            st['memo_hits'] += 1
            return None
        # deadline / heads+tails failure
        for i in bititer(rem):
            if est[i] + p[i] + q[i] > h:
                bad[key] = h
                return None
        if (sump + sum(A) + m - 1) // m > h:
            bad[key] = h
            return None
        Af = canonA(rem, A) if use_canon else A
        # subtree Pareto front: (est', A') <= (est, A) failed => this fails
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            hit = False
            eq = (mode == 'subeq')
            for e2, a2 in fr:
                if eq:
                    cond = (e2 == estt) and dominates(a2, Af)
                else:
                    cond = dominates(a2, Af) and all(e2[t] <= estt[t] for t in range(len(estt)))
                if cond:
                    hit = True
                    break
            if hit:
                st['sub_front_hits'] += 1
                bad[key] = h
                return None
        # capacity layer
        st['pack_calls'] += 1
        if use_pack_front:
            fr = F_pack.setdefault((rem, h), [])
            if front_query(fr, Af):
                st['pack_front_hits'] += 1
                bad[key] = h
                return None
        ok = None
        if use_ladder and pack_greedy(inst, rem, A, est, q, h):
            st['greedy_yes'] += 1
            ok = True
        if ok is None and use_ladder and pack_dff(inst, rem, A, est, q, h):
            st['dff_no'] += 1
            ok = False
        if ok is None:
            st['tables'] += 1
            ok = pack_exact(inst, rem, A, est, q, h)
        if not ok:
            st['per_rem'][rem] = st['per_rem'].get(rem, 0) + 1
            if use_pack_front:
                fr = F_pack.setdefault((rem, h), [])
                if front_insert(fr, Af, K):
                    st['inserts'] += 1
                st['front_sizes'].append(len(fr))
            bad[key] = h
            return None
        ready = [i for i in bititer(rem) if not (inst['pmask'][i] & rem)]
        ready.sort(key=lambda i: (h - q[i] - p[i]) - est[i])
        seen = set()
        for i in ready:
            for k in range(m):
                t = max(A[k], est[i])
                if t + p[i] + q[i] > h:
                    continue
                if k not in inst['elig'][i]:
                    continue
                nA = list(A)
                nA[k] = t + p[i]
                nA = tuple(nA)
                nest = list(est)
                for j in inst['succ'][i]:
                    if (rem >> j) & 1 and t + p[i] > nest[j]:
                        nest[j] = t + p[i]
                sub = rec(rem & ~(1 << i), nA, tuple(nest), sump - p[i])
                if sub is not None:
                    return [(i, k, t)] + sub
        if use_sub_front:
            fr = F_sub.setdefault((rem, h), [])
            # insert only if no existing element already dominates it
            if mode == 'subeq':
                hit = any((e2 == estt) and dominates(a2, A) for e2, a2 in fr)
            else:
                hit = any(dominates(a2, A) and all(e2[t] <= estt[t] for t in range(len(estt)))
                          for e2, a2 in fr)
            if not hit:
                fr.append((estt, Af))
                if K and len(fr) > K:
                    fr.sort(key=lambda ea: -sum(ea[0]))
                    del fr[K:]
                st['inserts'] += 1
        bad[key] = h
        return None

    try:
        est0, _q0 = heads_tails(inst, 0, [0] * n)
        out = rec(full, tuple([0] * m), tuple(est0), sum(p))
        res = (out is not None, out)
    except TimeoutError:
        res = (None, None)
        st['timeout'] = True
    return res, st
