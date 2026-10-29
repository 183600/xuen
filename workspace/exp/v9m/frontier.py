"""v9.1 MTF-PACT prototype: live memoized trie frontier.

Fixed-h frontier over interval boxes.  Each open leaf is decided by a
budgeted PACT call; UNKNOWN leaves are split using an SDLP fractional
solution.  Closed NO boxes enter an antichain cache and are reused by
subsumption.  The final object is a FrontierProof whose leaves are
PACT BranchProofs (or reused proofs).
"""
import sys, time, collections
sys.path[:0] = ['exp/v8u', 'exp/v8j', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pact import pact_decide
from prism import root_box, tighten, box_forbid
from sdecc import SDLP
from sage import _elig_aware, _domain
from po import heads_tails
from icf import FrontierProof
from rdf import check_schedule


def _subset(a, b):
    return all(a[0][i] >= b[0][i] and a[1][i] <= b[1][i]
               for i in range(len(a[0])))


def _cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def _decode(inst, lp, z):
    n = inst['n']; elig = _elig_aware(inst)
    starts = [None] * n; machs = [None] * n
    for c, key in enumerate(lp.cols):
        if z[c] > 1 - 1e-7:
            i, t = key[0], key[-1]
            if starts[i] is not None:
                return None
            starts[i] = t
            if elig:
                machs[i] = key[1]
    if any(x is None for x in starts):
        return None
    if not elig:
        busy = [[] for _ in range(inst['m'])]
        for i in sorted(range(n), key=lambda i: (starts[i], i)):
            for k in inst['elig'][i]:
                if all(starts[i] + inst['p'][i] <= a or starts[i] >= b
                       for a, b in busy[k]):
                    machs[i] = k
                    busy[k].append((starts[i], starts[i] + inst['p'][i]))
                    break
            if machs[i] is None:
                return None
    if check_schedule(inst, _cmax(inst, starts), starts, machs):
        return starts, machs
    return None


def _split(inst, h, lo, hi):
    n, m, p = inst['n'], inst['m'], inst['p']
    F = box_forbid(inst, h, lo, hi)
    est, q = heads_tails(inst, 0, [0] * n)
    lp = SDLP(inst, h, est, q, use_dom=True,
              elig_aware=_elig_aware(inst), forbid=F)
    if lp.N == 0:
        return ('no', None)
    res = lp.solve()
    if res.status == 2:
        return ('no', None)
    if res.status != 0:
        return ('unknown', None)
    z = res.x
    frac = False
    for c, key in enumerate(lp.cols):
        if 1e-7 < z[c] < 1 - 1e-7:
            frac = True
            break
    if not frac:
        got = _decode(inst, lp, z)
        if got is not None:
            return ('yes', got)
        # ambiguous but integral columns; choose a job with >1 allowed t
        for i in range(n):
            times = sorted({key[-1] for c, key in enumerate(lp.cols)
                            if key[0] == i and z[c] > 1e-7})
            if len(times) > 1:
                mid = times[len(times) // 2 - 1]
                return ('split', (i, mid))
        return ('unknown', None)
    best = None
    for i in range(n):
        dist = []
        mass = 0.0
        for c, key in enumerate(lp.cols):
            if key[0] == i:
                v = z[c]
                if v > 1e-9:
                    dist.append((key[-1], v)); mass += v
        if len(dist) <= 1:
            continue
        frac = sum(v for _, v in dist if 1e-7 < v < 1 - 1e-7)
        if frac <= 1e-7:
            continue
        if best is None or (mass, frac, -i) > (best[0], best[1], -best[2]):
            best = (mass, frac, i, dist)
    if best is None:
        return ('unknown', None)
    _, _, i, dist = best
    dist.sort()
    total = sum(v for _, v in dist)
    acc = 0.0; mid = dist[0][0]
    for t, v in dist:
        acc += v
        if acc >= 0.5 * total:
            mid = t
            break
    times = [t for t, _ in dist]
    if all(t <= mid for t in times) or all(t > mid for t in times):
        mid = times[len(times) // 2 - 1]
    return ('split', (i, mid))


def _child_boxes(lo, hi, i, mid):
    llo, lhi = list(lo), list(hi)
    lhi[i] = mid
    rlo, rhi = list(lo), list(hi)
    rlo[i] = mid + 1
    return (llo, lhi), (rlo, rhi)


def certify_frontier(inst, h, cap=1, max_leaves=2000, order='dfs'):
    t0 = time.time()
    n = inst['n']
    rlo, rhi = root_box(inst, h)
    root = tighten(inst, h, rlo, rhi, True)
    if root is None:
        # Precedence closure already emptied the root box.  A cheap PACT
        # call turns this into an auditable CP/Farkas proof.
        rr = pact_decide(inst, h, depthcap=None, nodecap=None)
        lp0 = rr.get('lp_solves', 0)
        if rr['verdict'] is False:
            return dict(verdict=False, proof=rr['proof'], schedule=None,
                        machine=None, leaves=1, lp=lp0, memo_hits=0,
                        sub_hits=0, splits=0, t=0.0,
                        audit=bool(rr['proof'].audit_rdf()))
        if rr['verdict'] is True:
            return dict(verdict=True, proof=None,
                        schedule=rr['schedule'], machine=rr['machine'],
                        leaves=1, lp=lp0, memo_hits=0, sub_hits=0,
                        splits=0, t=0.0, audit=False)
        return dict(verdict=None, proof=None, schedule=None, machine=None,
                    leaves=1, lp=lp0, memo_hits=0, sub_hits=0,
                    splits=0, t=0.0, audit=False)
    # node = dict(box=(lo,hi), children=[...], proof=..., reused=...)
    root_node = dict(box=(tuple(root[0]), tuple(root[1])),
                     children=None, proof=None, reused=False)
    open_nodes = [root_node]
    closed = []          # list of (box, proof)
    lp_total = 0
    memo_hits = sub_hits = splits = 0
    leaves = 0
    yes = None
    while open_nodes:
        if leaves > max_leaves:
            break
        node = open_nodes.pop() if order == 'dfs' else open_nodes.pop(0)
        lo, hi = node['box']
        # subsumption lookup
        hit = None
        for b, pr in closed:
            if _subset((lo, hi), b):
                if hit is None or _subset(b, hit[0]):
                    hit = (b, pr)
        if hit is not None:
            node['proof'] = hit[1]
            node['reused'] = True
            sub_hits += 1
            leaves += 1
            continue
        F = box_forbid(inst, h, lo, hi)
        r = pact_decide(inst, h, depthcap=None, nodecap=cap,
                        forbid0=F)
        lp_total += r.get('lp_solves', 0)
        if r['verdict'] is False:
            node['proof'] = r['proof']
            closed.append(((tuple(lo), tuple(hi)), r['proof']))
            leaves += 1
        elif r['verdict'] is True:
            yes = (r['schedule'], r['machine'])
            break
        else:
            sp = _split(inst, h, lo, hi)
            if sp[0] == 'no':
                # LP says NO but no proof; use a full PACT call for a proof
                rr = pact_decide(inst, h, depthcap=None, nodecap=None,
                                 forbid0=F)
                lp_total += rr.get('lp_solves', 0)
                if rr['verdict'] is False:
                    node['proof'] = rr['proof']
                    closed.append(((tuple(lo), tuple(hi)), rr['proof']))
                    leaves += 1
                    continue
                break
            if sp[0] == 'yes':
                yes = sp[1]
                break
            if sp[0] == 'unknown':
                # fall back to a full proof for this leaf
                rr = pact_decide(inst, h, depthcap=None, nodecap=None,
                                 forbid0=F)
                lp_total += rr.get('lp_solves', 0)
                if rr['verdict'] is False:
                    node['proof'] = rr['proof']
                    closed.append(((tuple(lo), tuple(hi)), rr['proof']))
                    leaves += 1
                    continue
                if rr['verdict'] is True:
                    yes = (rr['schedule'], rr['machine'])
                break
            i, mid = sp[1]
            splits += 1
            (llo, lhi), (rlo2, rhi2) = _child_boxes(lo, hi, i, mid)
            lchild = dict(box=(tuple(llo), tuple(lhi)), children=None,
                          proof=None, reused=False)
            rchild = dict(box=(tuple(rlo2), tuple(rhi2)), children=None,
                          proof=None, reused=False)
            node['children'] = (lchild, rchild)
            node['split'] = (i, mid)
            if order == 'dfs':
                open_nodes.extend([rchild, lchild])
            else:
                open_nodes.extend([lchild, rchild])
    # build frontier tree
    def build(nd):
        if nd['proof'] is not None:
            lo, hi = nd['box']
            F = box_forbid(inst, h, lo, hi)
            return ('leaf', frozenset(F), h, nd['proof'])
        if nd['children'] is None:
            return None
        i, mid = nd['split']
        lo, hi = nd['box']
        F = box_forbid(inst, h, lo, hi)
        l = build(nd['children'][0]); r = build(nd['children'][1])
        if l is None or r is None:
            return None
        return ('split', i, mid, frozenset(F), l, r)

    proof = None
    if yes is None:
        tree = build(root_node)
        if tree is not None:
            proof = FrontierProof(inst, h, tree)
    audit = bool(proof is not None and proof.audit_rdf())
    return dict(verdict=(True if yes is not None else
                         (False if audit else None)),
                proof=proof, schedule=(yes[0] if yes else None),
                machine=(yes[1] if yes else None), leaves=leaves,
                lp=lp_total, memo_hits=memo_hits, sub_hits=sub_hits,
                splits=splits, t=round(time.time() - t0, 4),
                audit=audit)
