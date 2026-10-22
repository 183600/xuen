"""v1.2 audit: is the v1.1 'gap' real, or an artifact of an unsound LP?

Regenerates the exact 101 heterogeneous instances of v1.1 e3 (Random(5)),
then compares four progressively stronger sound tiers:

  DFF      : scalar t * ceil(B_t/m) > Cmax
  SUBCUT   : for every machine subset M, subset volume and subset DFF
  ALP      : assignment LP (sound, per-machine capacities)
  PACK     : exact profile DP

and the old v1.1 LP (v09 frac_pack), which is *not* per-machine.
"""
import sys, json, random, time
sys.path.insert(0, 'exp/v11')
sys.path.insert(0, 'exp/v09')
sys.path.insert(0, 'exp/v12')
import plib
from lp import frac_pack
from lp2 import assignment_lp

OUT = {}


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


def old_lp(p, caps, elig, m):
    em = [set() for _ in range(m)]
    for i in range(len(p)):
        for k in elig[i]:
            em[k].add(i)
    tau, w, info = frac_pack(p, caps, eligible=em)
    return tau


def subset_cuts(p, caps, elig, m):
    """Return (closed, best_kind, best_M, best_t, best_val, best_cap)."""
    best = (0, None, None, 0, 0, 0)
    for mask in range(1, 1 << m):
        ks = [k for k in range(m) if (mask >> k) & 1]
        S = [p[i] for i in range(len(p)) if set(elig[i]) <= set(ks)]
        if not S:
            continue
        q = len(ks)
        Cmax = max(caps[k] for k in ks)
        # t=1 volume
        B = sum(S)
        val = (B + q - 1) // q
        if val > best[0]:
            best = (val, 'vol', ks, 1, B, Cmax)
        for t in range(2, max(S) + 1):
            B = sum(x // t for x in S)
            if B == 0:
                continue
            val = t * ((B + q - 1) // q)
            if val > best[0]:
                best = (val, 'sdff', ks, t, B, Cmax)
    return best, best


def audit_instance(p, caps, elig, m):
    if elig is None:
        elig = [list(range(m))] * len(p)
    ok, layers, ns = plib.profile_base(p, caps, elig, [(k, k + 1) for k in range(m)])
    dff = plib.dff_bound(p, caps)
    closed, best = subset_cuts(p, caps, elig, m)
    # subset_cuts currently compares to min caps for the return flag; recompute
    # exactly: best val > Cmax of its own subset.
    sub_closed = best[0] > best[5] if best[1] else False
    try:
        alp_ok, _, _ = assignment_lp(p, caps, elig)
    except Exception as e:
        alp_ok = None
    tau = old_lp(p, caps, elig, m)
    return dict(p=p, caps=caps, elig=[sorted(e) for e in elig],
                pack=(1 if ok else 0), states=ns, dff=dff,
                dff_closes=(dff > max(caps)),
                sub_closes=bool(sub_closed), sub=best,
                alp_feasible=(None if alp_ok is None else bool(alp_ok)),
                old_tau=tau, old_lp_feasible=(tau <= m + 1e-9))


def regenerate():
    rng = random.Random(5)
    pure = []
    for _ in range(120):
        m = rng.choice([2, 3]); n = rng.randint(8, 13); cap = rng.randint(6, 20)
        p = [rng.randint(1, cap) for _ in range(n)]
        L = lpack(p, m)
        H = L - 1
        if H < max(p):
            continue
        pure.append((p, [H] * m, None, m, L))
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
        elig_rows.append((p, [H] * m, elig, m, L))
    return pure, elig_rows


if __name__ == '__main__':
    t0 = time.time()
    pure, elig_rows = regenerate()
    print('regenerated', len(pure), len(elig_rows), 'in', round(time.time() - t0, 1), 's', flush=True)
    rows = []
    for j, (p, caps, elig, m, L) in enumerate(elig_rows):
        r = audit_instance(p, caps, elig, m)
        r['L'] = L
        rows.append(r)
        if j % 10 == 0:
            print(' ', j, 'pack', r['pack'], 'old_lp', r['old_lp_feasible'],
                  'alp', r['alp_feasible'], 'sub', r['sub_closes'], flush=True)
    OUT['elig'] = rows
    OUT['pure'] = []
    for (p, caps, elig, m, L) in pure:
        r = audit_instance(p, caps, elig, m)
        r['L'] = L
        OUT['pure'].append(r)
    json.dump(OUT, open('exp/v12/audit.json', 'w'), indent=1)
    print('saved', round(time.time() - t0, 1), 's')
