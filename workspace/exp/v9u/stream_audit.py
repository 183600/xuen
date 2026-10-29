"""One-pass audit for PACT BranchProof trees.

The recursive checker in v8i/sage.py walks a tree with Python recursion.
This module serialises the same tree as a post-order event stream and
verifies it with an explicit stack.  The live stack is a cut of the tree,
so its size is height+1, not the number of nodes.  The checker never
trusts the generator's flags: every leaf is replayed with cert.verify,
and every internal node re-checks the F partition.
"""
import sys
import time

sys.path[:0] = ['exp/v9u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _domain
from cert import verify


def events(node):
    """Post-order event stream (leaves first, parent last)."""
    if node[0] in ('leaf', 'empty'):
        yield node
        return
    _, i, mid, F, lo, hi = node
    yield from events(lo)
    yield from events(hi)
    yield node


def allowed(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def audit_stream(inst, h, tree):
    """Return (ok, max_stack, n_events, t_seconds)."""
    t0 = time.time()
    stack = []
    max_stack = 0
    ne = 0
    try:
        for node in events(tree):
            ne += 1
            tag = node[0]
            if tag == 'leaf':
                F = node[1]
                cert = node[2]
                if cert.get('kind') == 'empty':
                    ok = not allowed(inst, h, cert['job'], F)
                else:
                    ok = bool(verify(inst, h, cert, forbid=F))
                if not ok:
                    return False, max_stack, ne, time.time() - t0
                stack.append(('leaf', frozenset(F)))
            elif tag == 'empty':
                F = node[1]
                ok = not allowed(inst, h, node[2], F)
                if not ok:
                    return False, max_stack, ne, time.time() - t0
                stack.append(('empty', frozenset(F)))
            else:
                _, i, mid, F, lo, hi = node
                if len(stack) < 2:
                    return False, max_stack, ne, time.time() - t0
                right = stack.pop()
                left = stack.pop()
                if left[1] != frozenset(F) or right[1] != frozenset(F):
                    # child F is checked below; this quick guard catches
                    # a parent that did not pass its own F down.
                    pass
                allowed_t = allowed(inst, h, i, F)
                lo_t = [t for t in allowed_t if t > mid]
                hi_t = [t for t in allowed_t if t <= mid]
                if not lo_t or not hi_t:
                    return False, max_stack, ne, time.time() - t0
                loF = frozenset(F) | {(i, t) for t in lo_t}
                hiF = frozenset(F) | {(i, t) for t in hi_t}
                if left[1] != loF or right[1] != hiF:
                    return False, max_stack, ne, time.time() - t0
                stack.append(('node', frozenset(F)))
            max_stack = max(max_stack, len(stack))
        return (len(stack) == 1 and stack[0][1] == frozenset()), \
            max_stack, ne, time.time() - t0
    except Exception:
        return False, max_stack, ne, time.time() - t0


def tree_stats(tree):
    if tree[0] in ('leaf', 'empty'):
        return 1, 0, 1
    _, _, _, _, lo, hi = tree
    nl, hl, ll = tree_stats(lo)
    nr, hr, lr = tree_stats(hi)
    return nl + nr + 1, max(hl, hr) + 1, ll + lr
