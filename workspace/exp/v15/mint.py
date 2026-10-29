"""MINT: Multi-window INTegral certificate, and PACK-SET.

Both are *non-preemptive* certificates: a task runs as one contiguous block on
one machine.  INT (v1.3) is the preemptive / energy relaxation; MINT and
PACK-SET charge the same task to several windows / to a bin, which the
fractional relaxation cannot do.  All arrays below are local to the state:
ps[j], r[j], d[j] for j in 0..n-1, and el[j] the eligible machines.
"""


def _ov(s, p, a, b):
    lo = s if s > a else a
    hi = s + p if s + p < b else b
    return hi - lo if hi > lo else 0


def _cands(r, d, p, S):
    """A minimum of the piecewise-linear s -> sum_j overlap([s,s+p], S_j)
    is attained at a breakpoint, so only these O(|S|) starts matter."""
    lo, hi = r, d - p
    if hi < lo:
        return [lo]
    out = {lo, hi}
    for (a, b) in S:
        for v in (a, b, a - p, b - p):
            if lo <= v <= hi:
                out.add(v)
    return list(out)


def beta(j, ps, r, d, S):
    best = None
    p = ps[j]
    for s in _cands(r[j], d[j], p, S):
        v = 0
        for (a, b) in S:
            v += _ov(s, p, a, b)
        if best is None or v < best:
            best = v
    return best if best is not None else 0


def cap_union(S, A, m):
    c = 0
    for (a, b) in S:
        for k in range(m):
            lo = a if a > A[k] else A[k]
            if b > lo:
                c += b - lo
    return c


def union_slack(S, n, ps, r, d, A, m):
    W = 0
    for j in range(n):
        W += beta(j, ps, r, d, S)
    return cap_union(S, A, m) - W, W


def mint_pairs(tight, n, ps, r, d, A, m, max_pairs=3000, max_tight=20):
    """tight: [(a,b,slack)].  Try unions of two disjoint near-tight intervals."""
    chosen = []
    for (a, b, sl) in sorted(tight, key=lambda t: t[2]):
        if all(b <= a2 or b2 <= a for (a2, b2, _) in chosen):
            chosen.append((a, b, sl))
        if len(chosen) >= max_tight:
            break
    best = (0, None)
    npair = 0
    for x in range(len(chosen)):
        for y in range(x + 1, len(chosen)):
            a1, b1, _ = chosen[x]
            a2, b2, _ = chosen[y]
            if b1 > a2:
                a1, b1, a2, b2 = a2, b2, a1, b1
            if b1 >= a2:
                continue
            S = [(a1, b1), (a2, b2)]
            npair += 1
            if npair > max_pairs:
                return best, npair
            sl, W = union_slack(S, n, ps, r, d, A, m)
            if -sl > best[0]:
                best = (-sl, (S, W, cap_union(S, A, m)))
    return best, npair


def packset_window(n, ps, r, d, el, a, b, A, m, nodecap=20000):
    """Exact non-preemptive packing of Omega(a,b)={j: r_j>=a, d_j<=b}.
    Returns (infeasible, info, tree_size)."""
    omega = [j for j in range(n) if r[j] >= a and d[j] <= b]
    if not (2 <= len(omega) <= 12):
        return False, None, 0
    caps = [max(0, b - max(a, A[k])) for k in range(m)]
    items = sorted(((ps[j], j) for j in omega), reverse=True)
    if sum(x for x, _ in items) > sum(caps):
        return False, None, 0          # INT already owns this
    bins = [0] * m
    nodes = [0]
    # Symmetry breaking is only sound when the bins are truly interchangeable:
    # equal capacities AND the same eligibility for every remaining item.
    uniform = (len(set(caps)) == 1) and all(el[j] == list(range(m)) for j in omega)

    def dfs(pos):
        nodes[0] += 1
        if nodes[0] > nodecap:
            return None
        if pos == len(items):
            return True
        s, j = items[pos]
        seen = set()
        for k in el[j]:
            if bins[k] + s > caps[k]:
                continue
            if uniform and bins[k] in seen:
                continue
            if uniform:
                seen.add(bins[k])
            bins[k] += s
            rr = dfs(pos + 1)
            bins[k] -= s
            if rr:
                return True
            if rr is None:
                return None
            if uniform and bins[k] == 0:
                break
        return False

    ok = dfs(0)
    if ok is False:
        return True, (a, b, [ps[j] for j in omega], caps, nodes[0]), nodes[0]
    return False, None, nodes[0]


def check_mint(S, n, ps, r, d, A, m, W, cap):
    W2 = sum(beta(j, ps, r, d, S) for j in range(n))
    c2 = cap_union(S, A, m)
    return (W2 == W and c2 == cap and W2 > cap)


def packset_tree(n, ps, r, d, el, a, b, A, m, nodecap=200000):
    """Full branching tree for the packing refutation (no symmetry breaking),
    so that a checker can replay it without trusting any search."""
    omega = [j for j in range(n) if r[j] >= a and d[j] <= b]
    caps = [max(0, b - max(a, A[k])) for k in range(m)]
    items = sorted(((ps[j], j) for j in omega), reverse=True)
    if sum(x for x, _ in items) > sum(caps):
        return None
    bins = [0] * m
    nodes = [0]

    def dfs(pos):
        nodes[0] += 1
        if nodes[0] > nodecap:
            raise TimeoutError
        if pos == len(items):
            return ('OK',)
        s, j = items[pos]
        kids = []
        for k in el[j]:
            if bins[k] + s <= caps[k]:
                bins[k] += s
                kids.append((k, dfs(pos + 1)))
                bins[k] -= s
        if not kids:
            return ('LEAF', pos)
        return ('NODE', pos, kids)

    try:
        tree = dfs(0)
    except TimeoutError:
        return None
    if tree[0] == 'OK':
        return None                    # feasible; no certificate
    return {'a': a, 'b': b, 'items': [x for x, _ in items],
            'caps': caps, 'A': list(A), 'tree': tree, 'nodes': nodes[0]}


def check_packset(cert, n, ps, r, d, el, m):
    """Replay a packing refutation tree.  Returns True iff the tree is a valid
    proof that Omega(a,b) cannot be packed into the m machine windows."""
    a, b = cert['a'], cert['b']
    caps = cert['caps']
    if [max(0, b - max(a, cert['A'][k])) for k in range(m)] != caps:
        return False
    omega = [j for j in range(n) if r[j] >= a and d[j] <= b]
    items = sorted(((ps[j], j) for j in omega), reverse=True)
    if [x for x, _ in items] != cert['items']:
        return False
    if len(caps) != m:
        return False
    bins = [0] * m

    def rec(node, pos):
        if node[0] == 'LEAF':
            if node[1] != pos or pos >= len(items):
                return False
            s, j = items[pos]
            return all(bins[k] + s > caps[k] for k in el[j])
        if node[0] != 'NODE' or node[1] != pos or pos >= len(items):
            return False
        s, j = items[pos]
        feasible = {k for k in el[j] if bins[k] + s <= caps[k]}
        got = [k for k, _ in node[2]]
        if set(got) != feasible or len(got) != len(set(got)):
            return False
        for k, child in node[2]:
            bins[k] += s
            ok = rec(child, pos + 1)
            bins[k] -= s
            if not ok:
                return False
        return True

    return rec(cert['tree'], 0)
