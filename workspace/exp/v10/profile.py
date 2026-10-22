"""Profile DP: exact capacity-layer decision by a canonical state table.

State after assigning the first i tasks = sorted tuple of residual capacities.
Transitions: task i -> machine k, if p_i <= r_k.  Machines with equal A are
interchangeable, so we canonicalize by sorting within each equal-A block.
The whole computation is deterministic: the emitted layers ARE the certificate.
"""

def _canon(r, blocks):
    out = list(r)
    for (a, b) in blocks:          # block = [lo, hi)
        out[a:b] = sorted(out[a:b], reverse=True)
    return tuple(out)


def profile_dec(sizes, caps, blocks=None, order=None):
    """sizes: list of p_i (uniform eligibility). caps: initial capacities.
    Returns (feasible, layers, nstates)."""
    m = len(caps)
    if blocks is None:
        blocks = [(0, m)]
    idx = list(range(len(sizes)))
    if order is None:
        idx.sort(key=lambda i: (-sizes[i], i))
    start = _canon(tuple(caps), blocks)
    layers = [{start}]
    cur = {start}
    for i in idx:
        s = sizes[i]
        nxt = set()
        for r in cur:
            for k in range(m):
                if r[k] >= s:
                    t = list(r); t[k] -= s
                    nxt.add(_canon(t, blocks))
        layers.append(nxt)
        cur = nxt
        if not cur:
            return False, layers, sum(len(L) for L in layers)
    return True, layers, sum(len(L) for L in layers)


def check_profile_cert(sizes, caps, layers, blocks=None):
    """Independent checker: recompute the canonical layers from caps and
    compare with the claimed table, entry by entry.  No search."""
    if blocks is None:
        blocks = [(0, len(caps))]
    idx = list(range(len(sizes)))
    idx.sort(key=lambda i: (-sizes[i], i))
    cur = {_canon(tuple(caps), blocks)}
    if set(layers[0]) != cur:
        return False, 'layer0 mismatch'
    for j, i in enumerate(idx):
        s = sizes[i]; nxt = set()
        for r in cur:
            for k in range(len(caps)):
                if r[k] >= s:
                    t = list(r); t[k] -= s
                    nxt.add(_canon(t, blocks))
        if set(layers[j + 1]) != nxt:
            return False, 'layer %d mismatch (%d vs %d)' % (j + 1, len(layers[j + 1]), len(nxt))
        cur = nxt
        if not cur:
            # an early empty layer is a valid NO certificate; the table must stop here
            return (len(layers) == j + 2), 'ok (early empty)'
    return (len(layers) == len(idx) + 1), 'ok'


def profile_dec_elig(sizes, caps, elig, A, blocks=None):
    """Labeled version: task i can use k only if k in elig[i]; machines in the
    same equal-A block are canonically sorted.  caps[k] = H - A[k]."""
    m = len(caps)
    if blocks is None:
        blocks = [(0, m)]
    start = _canon(tuple(caps), blocks)
    cur = {start}; layers = [cur]
    idx = sorted(range(len(sizes)), key=lambda i: (-sizes[i], i))
    for i in idx:
        s = sizes[i]; nxt = set()
        for r in cur:
            for k in elig[i]:
                if r[k] >= s:
                    t = list(r); t[k] -= s
                    nxt.add(_canon(t, blocks))
        layers.append(nxt); cur = nxt
        if not cur:
            return False, layers
    return True, layers


def check_profile_cert_elig(sizes, caps, elig, blocks, layers):
    """Checker for the labeled/eligibility version: recompute successors of the
    claimed current layer and compare with the claimed next layer."""
    cur = {_canon(tuple(caps), blocks)}
    if set(layers[0]) != cur:
        return False, 'layer0'
    idx = sorted(range(len(sizes)), key=lambda i: (-sizes[i], i))
    for j, i in enumerate(idx):
        nxt = set()
        for r in cur:
            for k in elig[i]:
                if r[k] >= sizes[i]:
                    t = list(r); t[k] -= sizes[i]
                    nxt.add(_canon(t, blocks))
        if set(layers[j + 1]) != nxt:
            return False, 'layer %d' % (j + 1)
        cur = nxt
        if not cur:
            return (len(layers) == j + 2), 'ok'
    return (len(layers) == len(idx) + 1), 'ok'
