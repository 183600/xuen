"""v1.1 experiments: the ladder, pruning, parallel sweep, and the negative results."""
import sys, json, random, time, math
sys.path.insert(0, 'exp/v11')
import plib

OUT = {}


def lp_pack(p, caps, elig, m):
    """v0.9 configuration LP (exponential; only for tiny n)."""
    sys.path.insert(0, 'exp/v09')
    from lp import frac_pack
    em = [set() for _ in range(m)]
    for i in range(len(p)):
        for k in elig[i]:
            em[k].add(i)
    tau, w, info = frac_pack(p, caps, eligible=em)
    return tau


def lpack(p, m, elig=None):
    lo = max(max(p), (sum(p) + m - 1) // m)
    hi = sum(p)
    blocks = [(0, m)] if elig is None else [(k, k + 1) for k in range(m)]
    if not plib.profile_base(p, [hi] * m, elig, blocks)[0]:
        return hi + 1
    while lo < hi:
        mid = (lo + hi) // 2
        if plib.profile_base(p, [mid] * m, elig, blocks)[0]:
            hi = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------- E1 correctness
def e1():
    rng = random.Random(1)
    bad = 0; tested = 0
    for _ in range(1500):
        m = rng.choice([2, 3, 4]); n = rng.randint(3, 9); H = rng.randint(4, 24)
        p = [rng.randint(1, H) for _ in range(n)]
        caps = [H] * m
        ref, _, ns = plib.profile_base(p, caps)
        a, _, na = plib.profile_prune(p, caps)
        b, _, nb = plib.profile_prune_fast(p, caps)
        c, _ = plib.profile_bitset(p, caps)
        tested += 1
        if not (ref == a == b) or (c is not None and c != ref):
            bad += 1
    # eligibility: reference must not canonicalise
    rng = random.Random(9); bad2 = 0; t2 = 0
    for _ in range(800):
        m = rng.choice([2, 3]); n = rng.randint(3, 8); H = rng.randint(4, 20)
        p = [rng.randint(1, H) for _ in range(n)]
        caps = [H] * m
        elig = [[k for k in range(m) if rng.random() < 0.75] for _ in range(n)]
        if any(not e for e in elig):
            continue
        ref = plib.profile_base(p, caps, elig, [(k, k + 1) for k in range(m)])[0]
        c = plib.profile_bitset(p, caps, elig)[0]
        t2 += 1
        if c is not None and c != ref:
            bad2 += 1
    return dict(uniform=(tested, bad), elig=(t2, bad2))


# ---------------------------------------------------------------- E2 the v1.0 wall
def e2():
    rng = random.Random(3); rows = []
    for (m, n, H) in [(2, 200, 200), (3, 50, 100), (3, 200, 200), (4, 50, 100), (5, 50, 100)]:
        cap = (m * H) // n
        p = [rng.randint(1, max(1, cap)) for _ in range(n)]
        t = time.time(); g = plib.greedy_pack(p, [H] * m); tg = time.time() - t
        t = time.time(); d = plib.dff_bound(p, [H] * m); td = time.time() - t
        if m <= 4 and (H + 1) ** m <= (1 << 25):
            t = time.time(); ok, _, _ = plib.profile_base(p, [H] * m); tb = time.time() - t
        else:
            ok, tb = None, None
        rows.append(dict(m=m, n=n, H=H, greedy=(g is not None), t_greedy=tg,
                         dff=d, dff_ge_H=d >= H, t_dff=td, base_ok=ok, t_base=tb))
    return rows


# ---------------------------------------------------------------- E3 ladder closure
def e3():
    rng = random.Random(5)
    # (a) pure bin packing at the critical H = L_PACK - 1
    pure = []
    for _ in range(120):
        m = rng.choice([2, 3]); n = rng.randint(8, 13); cap = rng.randint(6, 20)
        p = [rng.randint(1, cap) for _ in range(n)]
        L = lpack(p, m)
        H = L - 1
        if H < max(p):
            continue
        g = plib.greedy_pack(p, [H] * m) is not None
        d = plib.dff_bound(p, [H] * m)
        tau = lp_pack(p, [H] * m, [list(range(m))] * n, m)
        _, _, ns = plib.profile_base(p, [H] * m)
        pure.append(dict(m=m, n=n, L=L, H=H, greedy=g, dff=d, dff_closes=d >= L,
                         lp=tau, lp_closes=tau > m + 1e-9, states=ns))
    # (b) heterogeneous eligibility, critical H
    elig_rows = []
    for _ in range(160):
        m = rng.choice([2, 3]); n = rng.randint(6, 10); H0 = rng.randint(6, 16)
        p = [rng.randint(1, H0) for _ in range(n)]
        elig = [[k for k in range(m) if rng.random() < 0.7] for _ in range(n)]
        if any(not e for e in elig):
            continue
        L = lpack(p, m, elig)
        H = L - 1
        if H < 1:
            continue
        caps = [H] * m
        g = plib.greedy_pack(p, caps, elig) is not None
        d = plib.dff_bound(p, caps)
        tau = lp_pack(p, caps, elig, m)
        _, _, ns = plib.profile_base(p, caps, elig, [(k, k + 1) for k in range(m)])
        elig_rows.append(dict(m=m, n=n, L=L, H=H, greedy=g, dff_closes=d >= L,
                              lp=tau, lp_closes=tau > m + 1e-9, states=ns))
    return dict(pure=pure, elig=elig_rows)


# ---------------------------------------------------------------- E4 table cost / pruning
def e4():
    rng = random.Random(11); rows = []
    for (m, n, cap) in [(3, 24, 16), (3, 40, 14), (4, 24, 10), (5, 20, 8), (3, 120, 10)]:
        p = [rng.randint(1, cap) for _ in range(n)]
        L = lpack(p, m); H = L - 1
        t = time.time(); okb, _, nsb = plib.profile_base(p, [H] * m); tb = time.time() - t
        t = time.time(); okp, _, nsp = plib.profile_prune(p, [H] * m); tp = time.time() - t
        rows.append(dict(m=m, n=n, H=H, states=nsb, prune_states=nsp,
                         ratio=nsp / max(1, nsb), t_base=tb, t_prune=tp, ok=okb))
    return rows


# ---------------------------------------------------------------- E5 negative results
def e5():
    # majorisation is NOT a valid dominance: balanced can be worse
    p = [4, 4, 4]; m = 2
    def opt_from(A):
        best = sum(A) + 99
        import itertools
        for asg in itertools.product(range(m), repeat=len(p)):
            load = list(A)
            for s, k in zip(p, asg):
                load[k] += s
            best = min(best, max(load))
        return best
    A1 = (1.5, 1.5); A2 = (2, 1)          # A1 more balanced (majorised by A2)
    # integer version: multiply by 2
    p2 = [8, 8, 8]; A1i = (3, 3); A2i = (4, 2)
    return dict(task=p2, balanced=A1i, opt_balanced=opt_from(A1i),
                spread=A2i, opt_spread=opt_from(A2i))
