"""Live round-synchronous frontier for the fixed-horizon decision.

A node is a box F (forbidden (job,start) pairs).  One round processes
all currently open leaves of the partition tree in parallel:

  * LP infeasible -> closed NO leaf with a Farkas certificate;
  * LP integral and replayable -> global YES schedule;
  * otherwise -> split on a fractional job at its weighted median.

If every leaf closes NO, the collected leaves form a FrontierProof;
if a leaf yields YES, the probe is YES; otherwise the remaining open
leaves are a partial frontier.  This is the live version of the tree
that v9.0 only replayed from BranchProof objects.
"""
import sys
import time

sys.path[:0] = ['exp/v9dfr', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import FrontierProof, CertLeafProof, cmax
from pact import (pact_decide, _integral_schedule, _singleton_leaf,
                  _elig_aware)
from sdecc import SDLP
from po import heads_tails
from sage import _domain
from cert import integer_certificate, integer_certificate_from_lp, verify
from rdf import check_schedule


class FNode:
    __slots__ = ('F', 'h', 'status', 'proof', 'children', 'split',
                 'width')

    def __init__(self, F, h):
        self.F = frozenset(F)
        self.h = int(h)
        self.status = 'open'
        self.proof = None
        self.children = None
        self.split = None
        self.width = None


def _allowed_times(lp, i, F):
    return sorted({key[-1] for key in lp.cols
                   if key[0] == i and (key[0], key[-1]) not in F})


def _choose_split(lp, res, F):
    n = lp.inst['n']
    best = None
    for i in range(n):
        times = _allowed_times(lp, i, F)
        if len(times) <= 1:
            continue
        dist = []
        for t in times:
            v = sum(res.x[c] for c, key in enumerate(lp.cols)
                    if key[0] == i and key[-1] == t
                    and (key[0], key[-1]) not in F)
            dist.append((t, v))
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac > 1e-7:
            mass = sum(v for _, v in dist)
            acc = 0.0
            mid = dist[0][0]
            for t, v in dist:
                acc += v
                if acc >= 0.5 * mass:
                    mid = t
                    break
            lo = [t for t in times if t > mid]
            hi = [t for t in times if t <= mid]
            if lo and hi and (best is None or frac > best[0]):
                best = (frac, i, mid)
    if best is not None:
        return best[1], best[2]
    for i in range(n):
        times = _allowed_times(lp, i, F)
        if len(times) > 1:
            mid = times[len(times) // 2 - 1]
            return i, mid
    return None, None


def _leaf_step(inst, h, F):
    """One parallel leaf evaluation.  Returns (kind, payload, stats)."""
    n = inst['n']
    elig = _elig_aware(inst)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig,
              forbid=F)
    base = [(0, 1)] * lp.N
    res = lp.solve(base)
    stats = dict(lp=1, cert_lp=0, nodes=1, split_lp=1)
    if res.status == 2:
        # Reuse the already-solved infeasible LP to build the Farkas
        # certificate; only fall back to the reference leaf if this
        # fails.  This avoids a second search LP per NO leaf.
        cert = integer_certificate_from_lp(lp, inst, h)
        stats['cert_lp'] += 1
        if cert is not None and verify(inst, h, cert, forbid=F):
            return 'no', CertLeafProof(inst, h, F, cert), stats
        r = pact_decide(inst, h, depthcap=0, forbid0=F)
        stats['lp'] += r.get('lp_solves', 0)
        stats['cert_lp'] += r.get('cert_lp', 0)
        if r['verdict'] is False:
            return 'no', r['proof'], stats
        return 'unknown', None, stats
    if res.status != 0:
        return 'unknown', None, stats
    frac = False
    for c, key in enumerate(lp.cols):
        if 1e-7 < res.x[c] < 1 - 1e-7:
            frac = True
            break
    if not frac:
        got = _integral_schedule(inst, lp, res.x, elig)
        if got is not None:
            return 'yes', got, stats
        single = _singleton_leaf(inst, h, F, lp, base)
        if single is not None:
            return 'yes', (single[1], single[2]), stats
    i, mid = _choose_split(lp, res, F)
    if i is None:
        return 'unknown', None, stats
    times = _allowed_times(lp, i, F)
    lo_t = [t for t in times if t > mid]
    hi_t = [t for t in times if t <= mid]
    if not lo_t or not hi_t:
        return 'unknown', None, stats
    return 'split', (i, mid, frozenset(F | {(i, t) for t in lo_t}),
                     frozenset(F | {(i, t) for t in hi_t})), stats


def _make_children(nd, split):
    i, mid, Flo, Fhi = split
    nd.split = (i, mid)
    lo = FNode(Flo, nd.h)
    hi = FNode(Fhi, nd.h)
    lo.width = sum(len(_allowed_times_domain(lo.h, lo.F, j))
                   for j in range(1))
    nd.children = (lo, hi)
    return lo, hi


def _allowed_times_domain(h, F, i):
    lo, hi = _domain(None, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _measure(inst, h, F):
    s = 0
    for i in range(inst['n']):
        lo, hi = _domain(inst, h, i)
        s += sum(1 for t in range(lo, hi + 1) if (i, t) not in F)
    return s


def _to_tree(nd):
    if nd.status == 'no':
        return ('leaf', frozenset(nd.F), nd.h, nd.proof)
    if nd.children is not None:
        i, mid = nd.split
        return ('split', i, mid, frozenset(nd.F),
                _to_tree(nd.children[0]), _to_tree(nd.children[1]))
    return ('open', frozenset(nd.F), nd.h, None)


def frontier_decide(inst, h, max_rounds=64, max_leaves=512,
                    max_nodes=20000):
    t0 = time.time()
    root = FNode(frozenset(), h)
    frontier = [root]
    rounds = leaves = splits = no = yes = unknown = 0
    lp_total = cert_lp_total = node_total = 0
    schedule = machine = None
    stop = None
    while frontier and rounds < max_rounds and leaves < max_leaves:
        rounds += 1
        nxt = []
        for nd in frontier:
            leaves += 1
            kind, payload, st = _leaf_step(inst, h, nd.F)
            lp_total += st['lp']
            cert_lp_total += st['cert_lp']
            node_total += st['nodes']
            if node_total > max_nodes:
                stop = 'nodecap'
                break
            if kind == 'no':
                nd.status = 'no'
                nd.proof = payload
                no += 1
            elif kind == 'yes':
                nd.status = 'yes'
                schedule, machine = payload
                yes += 1
                stop = 'yes'
                break
            elif kind == 'split':
                i, mid, Flo, Fhi = payload
                nd.status = 'split'
                nd.split = (i, mid)
                lo = FNode(Flo, h)
                hi = FNode(Fhi, h)
                nd.children = (lo, hi)
                splits += 1
                nxt.extend([lo, hi])
            else:
                nd.status = 'open'
                unknown += 1
                nxt.append(nd)
        if stop in ('yes', 'nodecap'):
            break
        frontier = nxt
    all_no = bool(frontier or rounds) and all(
        nd.status == 'no' for nd in _walk(root)
        if nd.children is None)
    if all_no:
        tree = _to_tree(root)
        proof = FrontierProof(inst, h, tree)
        ok = bool(proof.audit_rdf())
        return dict(verdict=False, proof=proof, proof_ok=ok,
                    schedule=None, machine=None, rounds=rounds,
                    leaves=leaves, splits=splits, no=no, yes=yes,
                    unknown=unknown, lp=lp_total, cert_lp=cert_lp_total,
                    nodes=node_total, stop=stop,
                    t=round(time.time() - t0, 5))
    if yes:
        c = cmax(inst, schedule)
        ok = bool(check_schedule(inst, c, schedule, machine))
        return dict(verdict=True, proof=None, proof_ok=ok,
                    schedule=schedule, machine=machine, rounds=rounds,
                    leaves=leaves, splits=splits, no=no, yes=yes,
                    unknown=unknown, lp=lp_total, cert_lp=cert_lp_total,
                    nodes=node_total, stop=stop,
                    t=round(time.time() - t0, 5))
    return dict(verdict=None, proof=None, proof_ok=False,
                schedule=None, machine=None, rounds=rounds,
                leaves=leaves, splits=splits, no=no, yes=yes,
                unknown=unknown, lp=lp_total, cert_lp=cert_lp_total,
                nodes=node_total, stop=stop or 'roundcap',
                t=round(time.time() - t0, 5))


def _walk(nd):
    stack = [nd]
    while stack:
        x = stack.pop()
        yield x
        if x.children:
            stack.extend(x.children)
