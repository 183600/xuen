"""Finite-horizon MDP for the probe-height decision.

State is the certified bracket [L,U]; a probe at h has two outcomes:

    NO  : theta > h, new bracket [h+1,U], cost cN(h)
    YES : theta <= h, new bracket [L,h],  cost cY(h)

where theta is the unknown optimum.  The exact expected-cost DP is

    E(a,b) = min_h [ pY * (cY(h) + E(a,h))
                     + (1-pY) * (cN(h) + E(h+1,b)) ],   E(a,a)=0.

The LP relaxation supplies a hint `pin` (the largest h at which the root
LP is still infeasible).  The prior puts mass p0 on theta = pin and the
rest uniformly on the other points of [L,U]:

    w(pin) = p0,   w(t) = (1-p0)/(G-1)  for t != pin.

This prior is closed under threshold observations: restricting to a
subinterval either excludes pin (then the posterior is uniform) or keeps
it (then it is the same point-mass + uniform mixture with the same p0).
Hence [a,b] plus the fixed (pin,p0) is a sufficient state, and the DP
above is exact.  p0=0 is uniform (binary-like); p0>0 at pin=L gives
lower-first on the first probe, then binary.

The costs encode the LP hint: NO is cheap below the pin and expensive
above it; YES is cheap above the pin and expensive below it:

    cN(h) = 1 + ln * max(0, h - pin) / (U-L+1)
    cY(h) = 1 + ly * max(0, pin - h) / (U-L+1).

The minimax variant is kept for the phase diagram; it is prior-free.
"""
from functools import lru_cache

INF = 10 ** 12


def _costs(L, U, pin, ln, ly):
    G = max(1, U - L + 1)
    cN = {}
    cY = {}
    for h in range(L, U):
        cN[h] = 1.0 + ln * max(0.0, (h - pin) / G)
        cY[h] = 1.0 + ly * max(0.0, (pin - h) / G)
    return cN, cY


def _p_yes(a, b, h, pin, p0):
    if b <= a:
        return 1.0
    G = b - a + 1
    if pin is None or pin < a or pin > b:
        return (h - a + 1) / G
    if h < pin:
        return (h - a + 1) * (1.0 - p0) / (G - 1) if G > 1 else 0.0
    return p0 + (h - a) * (1.0 - p0) / (G - 1) if G > 1 else 1.0


def expected_pin(L, U, pin=None, p0=0.5, ln=2.0, ly=2.0,
                 want_table=False):
    """Expected-cost DP with the point-mass-at-pin prior."""
    if U <= L:
        return L, 0.0, {}
    pin = L if pin is None else max(L, min(U, pin))
    p0 = max(0.0, min(1.0, float(p0)))
    cN, cY = _costs(L, U, pin, ln, ly)
    E = {}
    act = {}
    for g in range(0, U - L + 1):
        for a in range(L, U - g + 1):
            b = a + g
            if g == 0:
                E[(a, b)] = 0.0
                act[(a, b)] = a
                continue
            best = INF
            bh = a
            for h in range(a, b):
                py = _p_yes(a, b, h, pin, p0)
                pn = 1.0 - py
                z = py * (cY[h] + E[(a, h)]) \
                    + pn * (cN[h] + E[(h + 1, b)])
                if z < best:
                    best = z
                    bh = h
            E[(a, b)] = best
            act[(a, b)] = bh
    if want_table:
        return act[(L, U)], E[(L, U)], act
    return act[(L, U)], E[(L, U)], {}


def minimax(L, U, pin=None, ln=2.0, ly=2.0, want_table=False):
    if U <= L:
        return L, 0.0, {}
    pin = L if pin is None else max(L, min(U, pin))
    cN, cY = _costs(L, U, pin, ln, ly)
    W = {}
    act = {}
    for g in range(0, U - L + 1):
        for a in range(L, U - g + 1):
            b = a + g
            if g == 0:
                W[(a, b)] = 0.0
                act[(a, b)] = a
                continue
            best = INF
            bh = a
            for h in range(a, b):
                v = cY[h] + W[(a, h)]
                w = cN[h] + W[(h + 1, b)]
                z = v if v > w else w
                if z < best:
                    best = z
                    bh = h
            W[(a, b)] = best
            act[(a, b)] = bh
    if want_table:
        return act[(L, U)], W[(L, U)], act
    return act[(L, U)], W[(L, U)], {}


@lru_cache(maxsize=4096)
def _cached(policy, L, U, pin, p0, ln, ly):
    if policy == 'mdp':
        return expected_pin(L, U, pin, p0, ln, ly)[0]
    if policy == 'mdp-mm':
        return minimax(L, U, pin, ln, ly)[0]
    raise ValueError(policy)


def choose_h(policy, L, U, first, cfg=None):
    cfg = cfg or {}
    if U <= L:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy in ('mdp', 'mdp-mm'):
        pin = cfg.get('pin', L)
        ln = cfg.get('ln', 2.0)
        ly = cfg.get('ly', 2.0)
        p0 = cfg.get('p0', 0.5)
        return _cached(policy, L, U, pin, p0, ln, ly)
    raise ValueError('unknown policy %r' % (policy,))
