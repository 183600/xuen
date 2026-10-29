"""Pilot: live sampling-guided frontier on deep NO cases.

Each outer leaf is a box F.  The leaf oracle is pact_decide(F,h) with a
node cap.  If it closes, the whole leaf proof is kept.  If it returns
UNKNOWN, the leaf is split on a job/time chosen from a swarm archive.
The final object is a v9.0 FrontierProof; every leaf proof is replayed.
"""
import sys
import json
import time
import collections

sys.path[:0] = ['exp/v91', 'exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import FrontierProof
from pact import pact_decide
from rdf import check_schedule
from sage import _domain
from sparc import Swarm


def allowed(inst, h, i, F):
    lo, hi = _domain(inst, h, i)
    return [t for t in range(lo, hi + 1) if (i, t) not in F]


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def choose_split(inst, h, F, archive, mode='sample'):
    n = inst['n']
    cand = []
    for i in range(n):
        ts = allowed(inst, h, i, F)
        if len(ts) < 2:
            continue
        cand.append((i, ts))
    if not cand:
        return None
    if mode == 'width':
        i, ts = max(cand, key=lambda x: (len(x[1]), -x[0]))
        mid = ts[len(ts) // 2 - 1]
        return i, mid
    good = []
    for c, s, m in archive:
        if all((i, s[i]) not in F for i in range(n)):
            good.append(s)
    if len(good) < 2:
        good = [s for _, s, _ in archive]
    best = None
    for i, ts in cand:
        vals = [s[i] for s in good if s[i] in set(ts)]
        if len(vals) < 2:
            continue
        cnt = collections.Counter(vals)
        ent = -sum((v / len(vals)) * __import__('math').log(v / len(vals))
                   for v in cnt.values() if v > 0)
        key = (ent, len(ts), -i)
        if best is None or key > best[0]:
            best = (key, i, ts, vals)
    if best is None:
        i, ts = max(cand, key=lambda x: (len(x[1]), -x[0]))
        return i, ts[len(ts) // 2 - 1]
    _, i, ts, vals = best
    mid = _median(vals)
    left = [t for t in ts if t <= mid]
    right = [t for t in ts if t > mid]
    if not left or not right:
        mid = ts[len(ts) // 2 - 1]
    return i, mid


def split_boxes(inst, h, F, i, mid):
    ts = allowed(inst, h, i, F)
    lo_t = [t for t in ts if t > mid]
    hi_t = [t for t in ts if t <= mid]
    if not lo_t or not hi_t:
        return None
    F0 = F | {(i, t) for t in lo_t}
    F1 = F | {(i, t) for t in hi_t}
    return F0, F1


def _tree(node):
    if node.get('proof') is not None:
        return ('leaf', node['F'], node['h'], node['proof'])
    ch = node['children']
    return ('split', node['i'], node['mid'], node['F'],
            _tree(ch[0]), _tree(ch[1]))


def run_frontier(inst, h, archive, mode='sample', leaf_cap=80,
                 max_leaves=64):
    t0 = time.time()
    root = dict(F=frozenset(), h=h, proof=None, children=None,
                i=None, mid=None)
    open_nodes = [root]
    closed = []
    nodes = lp = cert_lp = 0
    splits = 0
    schedule = machine = None
    yes = False
    while open_nodes and len(closed) + len(open_nodes) <= max_leaves:
        node = open_nodes.pop(0)
        r = pact_decide(inst, h, depthcap=None, nodecap=leaf_cap,
                        forbid0=node['F'])
        nodes += r.get('nodes', 0)
        lp += r.get('lp_solves', 0)
        cert_lp += r.get('cert_lp', 0)
        if r['verdict'] is False:
            node['proof'] = r['proof']
            closed.append(node)
            continue
        if r['verdict'] is True:
            schedule, machine = r['schedule'], r['machine']
            yes = True
            break
        sp = choose_split(inst, h, node['F'], archive, mode=mode)
        if sp is None:
            open_nodes.append(node)
            break
        i, mid = sp
        boxes = split_boxes(inst, h, node['F'], i, mid)
        if boxes is None:
            open_nodes.append(node)
            break
        F0, F1 = boxes
        node['i'], node['mid'] = i, mid
        node['children'] = [
            dict(F=F0, h=h, proof=None, children=None, i=None, mid=None),
            dict(F=F1, h=h, proof=None, children=None, i=None, mid=None)]
        splits += 1
        open_nodes.extend(node['children'])
    target = int(h)
    if not open_nodes:
        proof = FrontierProof(inst, target, _tree(root))
        ok = bool(proof.audit_rdf())
    else:
        proof = None
        ok = False
    return dict(
        h=int(h), ok=ok, yes=bool(yes), open=len(open_nodes),
        closed=len(closed), splits=splits,
        nodes=nodes, lp=lp, cert_lp=cert_lp, total_lp=lp + cert_lp,
        schedule=schedule, machine=machine, proof=proof,
        t=round(time.time() - t0, 4))


def load_gap_cases(path='exp/v10c/gap_cases.json'):
    return json.load(open(path))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', default='orig-01,orig-09,orig-10,pert-00,pert-05,pert-11')
    ap.add_argument('--leaf-cap', type=int, default=80)
    ap.add_argument('--mode', default='sample')
    ap.add_argument('--out', default='exp/v91/frontier_pilot.json')
    args = ap.parse_args()
    want = set(x for x in args.cases.split(',') if x)
    rows = []
    for d in load_gap_cases():
        if want and d['case'] not in want:
            continue
        inst, h = d['inst'], int(d['opt']) - 1
        sw = Swarm(inst, d['opt'], None, None, n_particles=8, iters=12,
                   seed=7, stall=4)
        best, st = sw.run()
        archive = sw.archive
        t0 = time.time()
        base = pact_decide(inst, h, depthcap=None, nodecap=None)
        tb = time.time() - t0
        fr = run_frontier(inst, h, archive, mode=args.mode,
                          leaf_cap=args.leaf_cap)
        rows.append(dict(case=d['case'], kind=d['kind'], opt=d['opt'],
                         gap=d['opt_gap'], h=h,
                         base_ok=bool(base['verdict'] is False and
                                      base.get('proof') is not None and
                                      base['proof'].audit_rdf()),
                         base_nodes=base.get('nodes', 0),
                         base_lp=base.get('lp_solves', 0),
                         base_cert=base.get('cert_lp', 0),
                         base_total=base.get('lp_solves', 0) +
                         base.get('cert_lp', 0),
                         base_t=round(tb, 3),
                         fr_ok=fr['ok'], fr_open=fr['open'],
                         fr_splits=fr['splits'], fr_closed=fr['closed'],
                         fr_nodes=fr['nodes'], fr_lp=fr['lp'],
                         fr_cert=fr['cert_lp'], fr_total=fr['total_lp'],
                         fr_t=fr['t'],
                         sample_best=st['best'], sample_evals=st['evals']))
        r = rows[-1]
        print(r['case'], 'gap', r['gap'],
              '| base', r['base_total'], 'LP', r['base_t'], 's',
              '| frontier', r['fr_total'], 'LP', r['fr_t'], 's',
              'splits', r['fr_splits'], 'open', r['fr_open'],
              'ok', r['fr_ok'], flush=True)
    with open(args.out, 'w') as f:
        json.dump(rows, f, indent=1)
    print('saved', args.out)


if __name__ == '__main__':
    main()
