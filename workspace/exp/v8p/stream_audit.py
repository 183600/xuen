"""One-pass audit for residual certificate trees.

The recursive checker in residual.py traverses a tree twice: _check
validates structure and _measure recomputes the ledger.  This module
emits a post-order event stream and validates the same tree with a
stack, computing the ledger in the same pass.  The stack depth is the
certificate height, not the tree size.
"""
import sys
import time

sys.path[:0] = ['exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _domain
from cert import verify
from rdf import check_schedule


def events(node):
    if node.tag == 'node':
        yield from events(node.children[0])
        yield from events(node.children[1])
        yield ('node', node)
    else:
        yield (node.tag, node)


def _allowed(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _empty_measure(depth):
    return dict(nodes=1, expanded=0, closed_leaves=0, open_leaves=0,
                cert_lp=0, lp=0, height=depth, holes=0)


def _leaf_measure(node):
    m = _empty_measure(node.depth)
    if node.tag == 'open':
        m['open_leaves'] = 1
        m['holes'] = 1
        m['expanded'] = 1 if node.lp_done else 0
        m['lp'] = 1 if node.lp_done else 0
        m['cert_lp'] = node.cert_tries
    elif node.tag in ('leaf', 'empty'):
        m['closed_leaves'] = 1
        m['expanded'] = 1
        m['lp'] = 1 if node.lp_done else 0
        m['cert_lp'] = node.cert_tries
    elif node.tag == 'yes':
        m['expanded'] = 1
        m['lp'] = 1 if node.lp_done else 0
    return m


def audit_stream(inst, h, root, expected=None):
    """Return (ok, ledger, max_stack, n_events).

    The verifier consumes events one at a time.  It never recurses into a
    subtree after the subtree has been reduced, so the live stack is a
    cut of the tree and has size at most height+1.
    """
    stack = []
    max_stack = 0
    ne = 0
    t0 = time.time()
    try:
        for tag, node in events(root):
            ne += 1
            if tag in ('open', 'leaf', 'empty', 'yes'):
                if tag == 'open':
                    if node.reason not in ('budget', 'depth', 'cert', 'lp',
                                           'choice', 'machine', 'width'):
                        return False, None, max_stack, ne
                    for i in range(inst['n']):
                        if not _allowed(inst, h, i, node.F):
                            return False, None, max_stack, ne
                elif tag == 'leaf':
                    if node.cert is None:
                        return False, None, max_stack, ne
                    if node.cert.get('kind') == 'empty':
                        if _allowed(inst, h, node.cert['job'], node.F):
                            return False, None, max_stack, ne
                    elif not verify(inst, h, node.cert, forbid=node.F):
                        return False, None, max_stack, ne
                elif tag == 'empty':
                    if _allowed(inst, h, node.job, node.F):
                        return False, None, max_stack, ne
                else:
                    s, m = node.starts, node.machines
                    if s is None or m is None:
                        return False, None, max_stack, ne
                    cmax = max(s[i] + inst['p'][i]
                               for i in range(inst['n']))
                    if cmax > h or not check_schedule(inst, cmax, s, m):
                        return False, None, max_stack, ne
                stack.append((node.F, node.depth, _leaf_measure(node)))
            elif tag == 'node':
                if len(stack) < 2:
                    return False, None, max_stack, ne
                rf, rd, rm = stack.pop()
                lf, ld, lm = stack.pop()
                if (rf != node.children[1].F or rd != node.depth + 1 or
                        lf != node.children[0].F or ld != node.depth + 1):
                    return False, None, max_stack, ne
                allowed = _allowed(inst, h, node.i, node.F)
                lo_t = [t for t in allowed if t > node.mid]
                hi_t = [t for t in allowed if t <= node.mid]
                if not lo_t or not hi_t:
                    return False, None, max_stack, ne
                want_l = node.F | {(node.i, t) for t in lo_t}
                want_r = node.F | {(node.i, t) for t in hi_t}
                if lf != want_l or rf != want_r:
                    return False, None, max_stack, ne
                m = _empty_measure(node.depth)
                for k in m:
                    if k != 'height':
                        m[k] += lm[k] + rm[k]
                m['expanded'] += 1
                m['lp'] += 1 if node.lp_done else 0
                m['height'] = max(lm['height'], rm['height'])
                stack.append((node.F, node.depth, m))
            else:
                return False, None, max_stack, ne
            max_stack = max(max_stack, len(stack))
        if len(stack) != 1:
            return False, None, max_stack, ne
        F, depth, led = stack[0]
        if F != frozenset() or depth != 0:
            return False, None, max_stack, ne
        if expected is not None:
            for k in ('nodes', 'expanded', 'closed_leaves', 'open_leaves',
                      'cert_lp', 'lp', 'height'):
                if expected.get(k) != led.get(k):
                    return False, led, max_stack, ne
        return True, led, max_stack, ne
    except Exception:
        return False, None, max_stack, ne
