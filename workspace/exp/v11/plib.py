"""v1.1 capacity layer library.

Tier 0  greedy_pack      : sufficient YES (O(n log n)), witness = assignment
Tier 1  dff_cert         : necessary NO  (O(n log H)), witness = dual weights
Tier 2  profile_*        : exact table DP, only built when 0 and 1 both fail
        - profile_base   : v1.0 reference (tuple set)
        - profile_prune  : incremental dual-pool pruning
        - profile_bitset : bit-parallel (full cube, no canonicalisation)
"""
import math
from math import gcd

# ---------------------------------------------------------------- helpers
def canon(r, blocks):
    out = list(r)
    for a, b in blocks:
        out[a:b] = sorted(out[a:b], reverse=True)
    return tuple(out)

def _lcm(a, b):
    return a // gcd(a, b) * b


# ---------------------------------------------------------------- tier 0
def greedy_pack(sizes, caps, elig=None, tries=4, rng=None):
    """Sufficient check.  Returns an assignment list or None.
    Best-fit-decreasing + a few perturbed orders.  Never a false YES."""
    n = len(sizes); m = len(caps)
    if elig is None:
        elig = [list(range(m))] * n
    if any(not e for e in elig):
        return None
    best = None
    orders = [sorted(range(n), key=lambda i: -sizes[i])]
    if rng is not None:
        for _ in range(tries - 1):
            o = list(range(n)); rng.shuffle(o)
            o.sort(key=lambda i: -sizes[i] + rng.random() * sizes[i])
            orders.append(o)
    for order in orders:
        load = [0] * m
        asg = [-1] * n
        ok = True
        for i in order:
            s = sizes[i]
            cand = [k for k in elig[i] if load[k] + s <= caps[k]]
            if not cand:
                ok = False; break
            k = min(cand, key=lambda k: caps[k] - load[k] - s)   # best fit
            load[k] += s; asg[i] = k
        if ok:
            return asg
    return None


# ---------------------------------------------------------------- tier 1
def dff_weights(sizes, caps):
    """w_i = 1/floor(Cmax/p_i) is dual feasible for any caps <= Cmax.
    Returned as exact integers: w_i = L // floor(Cmax/p_i)."""
    Cmax = max(caps)
    ks = [max(1, Cmax // s) for s in sizes]
    L = 1
    for k in set(ks):
        L = _lcm(L, k)
    return [L // k for k in ks], L, ks


def dff_bound(sizes, caps, elig=None):
    """Scalar DFF bound: max_t t*ceil(sum_i floor(p_i/t)/m)."""
    m = len(caps)
    if not sizes:
        return 0
    best = 0
    for t in range(1, max(sizes) + 1):
        st = sum(s // t for s in sizes)
        best = max(best, t * ((st + m - 1) // m))
    return best


# ---------------------------------------------------------------- weights
def build_pool(sizes, caps, elig, ntests=4):
    """Pool of dual-feasible weight vectors (integer, exact).
    Returns list of (name, w, W) with W[k] an array over 0..caps[k]."""
    n = len(sizes); m = len(caps)
    Cmax = max(caps)
    pool = []
    w, L, ks = dff_weights(sizes, caps)
    if L > 0:
        pool.append(('dff', w, _knap_W(sizes, caps, elig, w)))
    # threshold indicators: w_i = 1[p_i > t]
    ts = sorted({max(1, Cmax // 2), max(1, Cmax // 3), max(1, Cmax // 4)})
    for t in ts[:max(0, ntests - 1)]:
        w = [1 if s > t else 0 for s in sizes]
        W = []
        for k in range(m):
            cnt = sum(1 for i in range(n) if w[i] and k in elig[i])
            W.append([min(cnt, c // (t + 1)) for c in range(caps[k] + 1)])
        pool.append(('thr%d' % t, w, W))
    return pool


def _knap_W(sizes, caps, elig, w):
    """W_k[c] = max total weight of an eligible subset fitting in c."""
    n = len(sizes)
    W = []
    for k in range(len(caps)):
        C = caps[k]
        dp = [0] * (C + 1)
        for i in range(n):
            if k not in elig[i]:
                continue
            s = sizes[i]; wi = w[i]
            if s > C or wi == 0:
                continue
            for c in range(C, s - 1, -1):
                v = dp[c - s] + wi
                if v > dp[c]:
                    dp[c] = v
        W.append(dp)
    return W


# ---------------------------------------------------------------- tier 2
def profile_base(sizes, caps, elig=None, blocks=None, want_layers=True):
    """v1.0 reference implementation (tuple set + canonical sort)."""
    m = len(caps); n = len(sizes)
    if blocks is None:
        blocks = [(0, m)]
    if elig is None:
        elig = [list(range(m))] * n
    idx = sorted(range(n), key=lambda i: (-sizes[i], i))
    start = canon(tuple(caps), blocks)
    cur = {start}; layers = [cur] if want_layers else None
    tot = 1
    for i in idx:
        s = sizes[i]; nxt = set()
        for r in cur:
            for k in elig[i]:
                if r[k] >= s:
                    t = list(r); t[k] -= s
                    nxt.add(canon(t, blocks))
        tot += len(nxt)
        if want_layers:
            layers.append(nxt)
        cur = nxt
        if not cur:
            return False, layers, tot
    return True, layers, tot


def profile_prune(sizes, caps, elig=None, blocks=None, pool=None,
                  want_layers=False, stats=None):
    """Tier 2 with incremental dual-pool pruning.

    Each profile carries its own RHS vector s(r) = (sum_k W^k_t(r_k))_t.
    Moving to r' = r - s*e_k only changes term k, so the update is O(|pool|).
    A profile is dropped when for some test t:  lhs_t > s_t(r).
    """
    m = len(caps); n = len(sizes)
    if blocks is None:
        blocks = [(0, m)]
    if elig is None:
        elig = [list(range(m))] * n
    if pool is None:
        pool = build_pool(sizes, caps, elig)
    T = len(pool)
    idx = sorted(range(n), key=lambda i: (-sizes[i], i))
    # suffix weight of the remaining tasks, per test
    suf = [[0] * (n + 1) for _ in range(T)]
    for t, (_, w, _) in enumerate(pool):
        for j in range(n - 1, -1, -1):
            suf[t][j] = suf[t][j + 1] + w[idx[j]]
    def rhs(r):
        return tuple(sum(pool[t][2][k][r[k]] for k in range(m)) for t in range(T))
    start = canon(tuple(caps), blocks)
    cur = {start: rhs(start)}
    layers = [set(cur)] if want_layers else None
    tot = 1; pruned = 0
    for j, i in enumerate(idx):
        s = sizes[i]; nxt = {}
        need = [suf[t][j + 1] for t in range(T)]
        for r, svec in cur.items():
            for k in elig[i]:
                if r[k] < s:
                    continue
                t_ = list(r); t_[k] -= s
                t_ = canon(t_, blocks)
                # incremental RHS: only coordinate k changes; but canon may
                # permute coordinates inside a block, so recompute defensively
                sv = rhs(t_)
                bad = False
                for t in range(T):
                    if need[t] > sv[t]:
                        bad = True; break
                if bad:
                    pruned += 1; continue
                old = nxt.get(t_)
                if old is None:
                    nxt[t_] = sv
                else:
                    nxt[t_] = tuple(max(a, b) for a, b in zip(old, sv))
        tot += len(nxt)
        if want_layers:
            layers.append(set(nxt))
        cur = nxt
        if not cur:
            if stats is not None:
                stats.update(states=tot, pruned=pruned)
            return False, layers, tot
    if stats is not None:
        stats.update(states=tot, pruned=pruned)
    return True, layers, tot


def profile_prune_fast(sizes, caps, elig=None, blocks=None, pool=None,
                       want_layers=False):
    """Same decision, but RHS carried incrementally: only W_k is updated when
    no canonicalisation is needed (single block, or block-local move)."""
    m = len(caps); n = len(sizes)
    if blocks is None:
        blocks = [(0, m)]
    if elig is None:
        elig = [list(range(m))] * n
    if pool is None:
        pool = build_pool(sizes, caps, elig)
    T = len(pool)
    idx = sorted(range(n), key=lambda i: (-sizes[i], i))
    suf = [[0] * (n + 1) for _ in range(T)]
    for t, (_, w, _) in enumerate(pool):
        for j in range(n - 1, -1, -1):
            suf[t][j] = suf[t][j + 1] + w[idx[j]]
    single = (len(blocks) == 1)
    def rhs(r):
        return [sum(pool[t][2][k][r[k]] for k in range(m)) for t in range(T)]
    start = canon(tuple(caps), blocks)
    cur = {start: rhs(start)}
    layers = [set(cur)] if want_layers else None
    tot = 1
    for j, i in enumerate(idx):
        s = sizes[i]; nxt = {}
        need = [suf[t][j + 1] for t in range(T)]
        for r, sv in cur.items():
            for k in elig[i]:
                if r[k] < s:
                    continue
                t_ = list(r); t_[k] -= s
                if single:
                    sv2 = [sv[t] - pool[t][2][k][r[k]] + pool[t][2][k][t_[k]]
                           for t in range(T)]
                else:
                    t_ = canon(t_, blocks)
                    sv2 = rhs(t_)
                if any(need[t] > sv2[t] for t in range(T)):
                    continue
                key = tuple(t_)
                old = nxt.get(key)
                if old is None:
                    nxt[key] = sv2
                else:
                    for t in range(T):
                        if sv2[t] > old[t]:
                            old[t] = sv2[t]
        tot += len(nxt)
        if want_layers:
            layers.append(set(nxt))
        cur = nxt
        if not cur:
            return False, layers, tot
    return True, layers, tot


def _repeat(u, period, cnt):
    """bit pattern u (occupying one period) repeated cnt times at stride period"""
    res = u; filled = 1
    while filled < cnt:
        take = min(filled, cnt - filled)
        blk = res & ((1 << (period * take)) - 1)
        res |= blk << (period * filled)
        filled += take
    return res


def _box_mask(m, B, caps):
    """bits kept iff load_k <= caps_k for every k"""
    M = None
    for k in range(m):
        st = B ** k
        u = (1 << ((caps[k] + 1) * st)) - 1
        Mk = _repeat(u, B * st, B ** (m - 1 - k))
        M = Mk if M is None else (M & Mk)
    return M


def profile_bitset(sizes, caps, elig=None, bit_limit=1 << 25):
    """Bit-parallel exact decision on the load cube.

    Radix B = 2^b with B > H: no carry can occur inside the kept box, and
    states leaving the box are dead (loads only grow), so a single AND with
    the box mask per transition is exact.  No canonicalisation.
    Returns (feasible, bits) or (None, 0) when the cube exceeds bit_limit.
    """
    m = len(caps); n = len(sizes)
    if n == 0:
        return True, 0
    H = max(caps) + max(sizes) + 1   # a shift must not carry before masking
    b = max(1, (H - 1).bit_length())
    B = 1 << b
    total = B ** m
    if total > bit_limit:
        return None, 0
    stride = [B ** k for k in range(m)]
    box = _box_mask(m, B, caps)
    if elig is None:
        elig = [list(range(m))] * n
    bits = 1                                   # all loads zero
    for i in range(n):
        s = sizes[i]; nb = 0
        for k in elig[i]:
            nb |= bits << (s * stride[k])
        bits = nb & box
        if bits == 0:
            return False, 0
    return True, total
