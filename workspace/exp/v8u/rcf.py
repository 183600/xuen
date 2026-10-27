"""RCF-PACT: robust core-guided frontier for certified scheduling.

RCF keeps the v9.0 ICF bracket invariant and the v9.2 TAMO multi-leaf
frontier.  The new probe combines three ingredients:

  1. a verified Pareto archive and LP-guided primal probe (PTB) for the
     upper-bound side;
  2. a fractional-core analysis of the same root LP, which restricts the
     exact PACT search to the jobs that actually carry fractional start
     times;
  3. an adaptive oracle budget.  If the core search is complete, the leaf
     is closed without a split.  If the budget is exhausted, the leaf is
     refined instead of falling back to an exponential search.

Every transition preserves the partial certificate

    (frontier, archive, U),  L = min leaf bound,  L <= U.

Only audited NO proofs raise L, only check_schedule-verified schedules
raise the archive, and an UNKNOWN answer is absorbed by REFINE.
"""
import sys
import time
import heapq
import collections

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from rdf import check_schedule
from pact import pact_decide
from icf import cmax
from ptb import ParetoArchive, primal_probe
from tamo import (Leaf, collect_leaves, tree_depth, snapshot,
                  close_empty, split_leaf, allowed_times,
                  box_measure, rank_of, rank_lt, _choose_split,
                  TamoFrontier, TamoCertificate,
                  TamoPartialCertificate, pact_initial)


def core_of(lp, res):
    if res is None or res.status != 0:
        return frozenset()
    out = set()
    for c, key in enumerate(lp.cols):
        if 1e-7 < res.x[c] < 1 - 1e-7:
            out.add(int(key[0]))
    return frozenset(out)


def core_mass(lp, res, i):
    total = 0.0
    for c, key in enumerate(lp.cols):
        if key[0] == i and 1e-7 < res.x[c] < 1 - 1e-7:
            total += float(res.x[c])
    return total


def core_split(inst, leaf, H, lp, res, K):
    best = None
    for i in K:
        dist = []
        for c, key in enumerate(lp.cols):
            if key[0] == i and res.x[c] > 1e-9:
                dist.append((key[-1], float(res.x[c])))
        if len(dist) < 2:
            continue
        dist.sort()
        total = sum(v for _, v in dist)
        if total <= 1e-12:
            continue
        acc = 0.0
        mid = dist[0][0]
        for t, v in dist:
            acc += v
            if acc >= 0.5 * total:
                mid = t
                break
        times = allowed_times(inst, H, i, leaf.F)
        le = [t for t in times if t <= mid]
        gt = [t for t in times if t > mid]
        if not le or not gt:
            continue
        score = (min(len(le), len(gt)), core_mass(lp, res, i))
        if best is None or score > best[0]:
            best = (score, i, mid)
    if best is None:
        return None
    return best[1], best[2]


def _probe(inst, leaf, h, archive, core_budget, use_primal,
           samples, repairs, kmax, seed, fallback):
    info = dict(status='direct', K=[], primal_lp=0, primal_kind=None,
                lp=None, res=None, cause=None, fallback=False)
    if use_primal:
        pr = primal_probe(inst, h, archive,
                          forbid0=frozenset(leaf.F),
                          samples=samples, repairs=repairs, kmax=kmax,
                          seed=seed, harvest=True)
        info['primal_lp'] = pr['stats']['lp']
        info['primal_kind'] = pr['kind']
        if pr['kind'] == 'yes':
            info['cause'] = 'primal-yes'
            return (dict(verdict=True, schedule=pr['schedule'],
                         machine=pr['machine'], lp_solves=0,
                         cert_lp=0, nodes=0, branch_jobs=[],
                         primal=True), info, False)
        lp, res = pr['lp'], pr['res']
        info['lp'], info['res'] = lp, res
        if pr['kind'] == 'no_root':
            r = pact_decide(inst, h, depthcap=None, nodecap=1,
                            root_lp=lp, root_res=res,
                            branch_jobs=set(),
                            forbid0=frozenset(leaf.F))
            info['status'] = 'root-infeasible'
            info['cause'] = ('no' if r['verdict'] is False
                             else 'cert-fail')
            return r, info, False
    else:
        lp = res = None

    if lp is None or res is None:
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=frozenset(leaf.F))
        info['cause'] = ('no' if r['verdict'] is False else
                         'yes' if r['verdict'] is True else
                         'search-unknown')
        return r, info, False

    if res.status == 2:
        r = pact_decide(inst, h, depthcap=None, nodecap=1,
                        root_lp=lp, root_res=res, branch_jobs=set(),
                        forbid0=frozenset(leaf.F))
        info['status'] = 'root-infeasible'
        info['cause'] = ('no' if r['verdict'] is False else
                         'cert-fail')
        return r, info, False
    if res.status != 0:
        r = pact_decide(inst, h, depthcap=None, nodecap=None,
                        forbid0=frozenset(leaf.F))
        info['status'] = 'root-unknown'
        info['cause'] = ('no' if r['verdict'] is False else
                         'yes' if r['verdict'] is True else
                         'lp-unknown')
        return r, info, False

    K = core_of(lp, res)
    info['status'] = 'fractional' if K else 'integral'
    info['K'] = sorted(K)
    bj = K if K else None
    r = pact_decide(inst, h, depthcap=None, nodecap=core_budget,
                    root_lp=lp, root_res=res, branch_jobs=bj,
                    forbid0=frozenset(leaf.F))
    if r['verdict'] is not None:
        info['cause'] = 'no' if r['verdict'] is False else 'yes'
        return r, info, bool(K)

    if fallback == 'full' and core_budget is None:
        r2 = pact_decide(inst, h, depthcap=None, nodecap=None,
                         root_lp=lp, root_res=res, branch_jobs=None,
                         forbid0=frozenset(leaf.F))
        for key in ('lp_solves', 'nodes', 'cert_lp'):
            r2[key] = r2.get(key, 0) + r.get(key, 0)
        r2['fallback'] = True
        info['fallback'] = True
        if r2['verdict'] is not None:
            info['cause'] = ('no' if r2['verdict'] is False else 'yes')
            return r2, info, bool(K)
        info['cause'] = 'core-insufficient'
        return r2, info, bool(K)

    if r.get('insufficient'):
        info['cause'] = 'core-insufficient'
    elif core_budget is not None and r.get('nodes', 0) >= core_budget:
        info['cause'] = 'budget'
    else:
        info['cause'] = 'search-unknown'
    return r, info, bool(K)


class RcfCertificate:
    kind = 'rcf-opt'

    def __init__(self, inst, tamo_cert, archive):
        self.inst = inst
        self.tamo = tamo_cert
        self.archive = archive

    def audit_rdf(self):
        try:
            if not self.tamo.audit_rdf():
                return False
            if not self.archive.audit():
                return False
            best = self.archive.best()
            if best is None:
                return False
            cm, s, m, _ = best
            if cm != self.tamo.target + 1:
                return False
            return bool(check_schedule(self.inst, cm, s, m))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class RcfPartialCertificate:
    kind = 'rcf-partial'

    def __init__(self, inst, tamo_partial, archive):
        self.inst = inst
        self.tamo = tamo_partial
        self.archive = archive

    def audit_rdf(self):
        try:
            return bool(self.tamo.audit_rdf() and self.archive.audit())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def run_rcf(inst, known, name, idx, policy='lower', core_budget=None,
            use_primal=True, samples=48, repairs=6, kmax=14,
            split_mode='core', fallback='none', max_probes=200000,
            initial=None, seed=0, audit_every=True, include_tree=False):
    t0 = time.time()
    if initial is None:
        L0, U0, s, m, proof0 = pact_initial(inst)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    archive = ParetoArchive(inst)
    archive.add(s, m, 'initial', U0)
    H0 = U0 - 1
    Mmax = box_measure(inst, H0, frozenset())
    root = Leaf(frozenset(), L0, proof0, Mmax)
    holder = [root]
    U = U0
    H = U - 1
    leaves = []
    collect_leaves(root, leaves)
    heap = [(l.L, -l.mu, id(l)) for l in leaves]
    heapq.heapify(heap)
    live = set(id(l) for l in leaves)
    byid = {id(l): l for l in leaves}

    probes = splits = closes_lift = closes_empty = 0
    yes = no = unknown = 0
    lp = nodes = cert_lp = primal_lp = 0
    primal_calls = primal_yes = primal_fail = 0
    core_probes = core_insufficient = cert_fail = skips = 0
    core_status = collections.Counter()
    failed = {}
    core_k = []
    max_leaves = len(leaves)
    rank_checks = rank_fail = 0
    partial_checks = partial_fail = 0
    rho = rank_of(inst, H0, U, holder[0], Mmax, recompute=True)

    def state_audit():
        nonlocal partial_checks, partial_fail
        if not audit_every:
            return
        fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
        pc = TamoPartialCertificate(inst, U - 1, fp, s, m,
                                    probe=probes)
        if pc.audit_rdf():
            partial_checks += 1
        else:
            partial_fail += 1

    def absorb_archive():
        nonlocal U, H, s, m
        b = archive.best()
        if b is None:
            return False
        cm, bs, bm, _ = b
        if cm < U:
            U = cm
            H = U - 1
            s = list(bs)
            m = list(bm)
            return True
        return False

    def prune():
        nonlocal closes_empty, closes_lift
        leaves_now = []
        collect_leaves(holder[0], leaves_now)
        for x in leaves_now:
            if x.closed:
                continue
            if close_empty(inst, x, H):
                live.discard(id(x))
                byid.pop(id(x), None)
                closes_empty += 1
            elif x.L >= U:
                x.closed = True
                x.h = x.L - 1
                live.discard(id(x))
                byid.pop(id(x), None)
                closes_lift += 1

    state_audit()

    while True:
        while heap and (heap[0][2] not in live or
                        byid.get(heap[0][2]) is None):
            heapq.heappop(heap)
        if not heap:
            break
        Lmin, _, lid = heap[0]
        leaf = byid.get(lid)
        if leaf is None:
            heapq.heappop(heap)
            continue
        if leaf.L != Lmin:
            heapq.heappop(heap)
            continue
        if leaf.L >= U:
            break
        if probes >= max_probes:
            break
        fs = failed.setdefault(id(leaf), set())
        fs = {t for t in fs if leaf.L <= t < U}
        failed[id(leaf)] = fs
        cand = [t for t in range(leaf.L, U) if t not in fs]
        force = not cand
        if force:
            h = None
        elif policy == 'lower' and leaf.L not in fs:
            h = leaf.L
        elif policy == 'upper':
            h = U - 1
        else:
            h = cand[len(cand) // 2]
        before = rho
        if force:
            r = dict(verdict=None, lp_solves=0, cert_lp=0, nodes=0,
                     branch_jobs=[], proof=None)
            info = dict(status='exhausted', K=[], primal_lp=0,
                        primal_kind=None, lp=None, res=None,
                        cause='exhausted')
            used_core = False
            unknown += 1
        else:
            r, info, used_core = _probe(
                inst, leaf, h, archive, core_budget, use_primal,
                samples, repairs, kmax, seed + probes, fallback)
            probes += 1
            lp += r.get('lp_solves', 0)
            nodes += r.get('nodes', 0)
            cert_lp += r.get('cert_lp', 0)
            primal_lp += info.get('primal_lp', 0)
            if use_primal:
                primal_calls += 1
                if info.get('primal_kind') == 'yes':
                    primal_yes += 1
                elif info.get('primal_kind') in ('no_root', 'fail'):
                    primal_fail += 1
            core_status[info.get('status')] += 1
            if info.get('K'):
                core_probes += 1
                core_k.append(len(info['K']))
            if r['verdict'] is None and used_core:
                core_insufficient += 1

        kind = None
        if r['verdict'] is False:
            no += 1
            leaf.proof = r['proof']
            leaf.L = h + 1
            kind = 'probe-no'
            if leaf.L >= U:
                leaf.closed = True
                leaf.h = leaf.L - 1
                live.discard(id(leaf))
                byid.pop(id(leaf), None)
                closes_lift += 1
            else:
                heapq.heappush(heap, (leaf.L, -leaf.mu, id(leaf)))
        elif r['verdict'] is True:
            yes += 1
            c = cmax(inst, r['schedule'])
            if c < U and check_schedule(inst, c, r['schedule'],
                                        r['machine']):
                U = c
                H = U - 1
                s = list(r['schedule'])
                m = list(r['machine'])
                archive.add(s, m, 'exact', c)
                kind = 'probe-yes'
                prune()
                if not live:
                    break
            else:
                kind = 'probe-yes-stale'
        else:
            if not force:
                unknown += 1
            cause = info.get('cause')
            if cause in ('cert-fail', 'lp-unknown') and h is not None:
                fs.add(h)
                failed[id(leaf)] = fs
                skips += 1
                if cause == 'cert-fail':
                    cert_fail += 1
                kind = 'skip'
                if absorb_archive():
                    prune()
                state_audit()
                continue
            pair = None
            if split_mode == 'core' and info.get('K') and info.get('res') is not None:
                pair = core_split(inst, leaf, H, info['lp'],
                                  info['res'], info['K'])
            if pair is None:
                pair = _choose_split(inst, leaf, H, r, 'oracle')
            if pair is None:
                pair = _choose_split(inst, leaf, H, r, 'domain')
            if pair is None:
                break
            i, mid = pair
            sp = split_leaf(inst, leaf, i, mid, H, H0)
            if sp is None:
                break
            splits += 1
            failed.pop(id(leaf), None)
            if leaf.parent is None:
                holder[0] = sp
            live.discard(id(leaf))
            byid.pop(id(leaf), None)
            for c in (sp.lo, sp.hi):
                if close_empty(inst, c, H):
                    closes_empty += 1
                else:
                    live.add(id(c))
                    byid[id(c)] = c
                    heapq.heappush(heap, (c.L, -c.mu, id(c)))
            kind = 'refine'
            leaves = []
            collect_leaves(holder[0], leaves)
            max_leaves = max(max_leaves, len(leaves))

        if absorb_archive():
            prune()

        if kind in ('probe-no', 'probe-yes', 'probe-yes-stale', 'refine'):
            rho2 = rank_of(inst, H0, U, holder[0], Mmax,
                           recompute=True)
            rank_checks += 1
            if not rank_lt(rho2, before):
                rank_fail += 1
            rho = rho2
        state_audit()

    leaves = []
    collect_leaves(holder[0], leaves)
    for x in leaves:
        if not x.closed and x.L >= U:
            x.closed = True
            x.h = x.L - 1
    fp = TamoFrontier(inst, U - 1, snapshot(holder[0]))
    cert = TamoCertificate(inst, U - 1, fp, s, m)
    final_ok = bool(cert.audit_rdf())
    L = fp.L
    partial = TamoPartialCertificate(
        inst, U - 1, TamoFrontier(inst, U - 1, snapshot(holder[0])),
        s, m, probe=probes)
    partial_final = bool(partial.audit_rdf())
    rc = RcfCertificate(inst, cert, archive)
    rcf_ok = bool(rc.audit_rdf())
    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known, policy=policy,
        core_budget=core_budget, use_primal=use_primal,
        split_mode=split_mode, fallback=fallback,
        L0=L0, U0=U0, L=L, U=U, opt=U,
        probes=probes, splits=splits, yes=yes, no=no, unknown=unknown,
        closes_lift=closes_lift, closes_empty=closes_empty,
        primal_calls=primal_calls, primal_yes=primal_yes,
        primal_fail=primal_fail, primal_lp=primal_lp,
        core_probes=core_probes, core_insufficient=core_insufficient,
        cert_fail=cert_fail, skips=skips,
        core_k=(max(core_k) if core_k else 0),
        core_k_mean=(sum(core_k) / len(core_k) if core_k else 0.0),
        core_status=dict(core_status),
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        total_lp=primal_lp + lp + cert_lp,
        leaves=len(leaves), open=sum(1 for x in leaves if not x.closed),
        max_leaves=max_leaves, depth=tree_depth(holder[0]),
        rank_checks=rank_checks, rank_fail=rank_fail,
        partial_checks=partial_checks, partial_fail=partial_fail,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok, rcf_audit=rcf_ok,
        partial_final=partial_final, cert_h=(U - 1 if L == U else None),
        archive=len(archive.items), archive_audit=archive.audit(),
        t=round(dt, 4),
        ok=bool(L == U == known and final_ok and partial_fail == 0
                and rank_fail == 0 and rcf_ok),
    )
    if include_tree:
        out['tree'] = snapshot(holder[0])
        out['schedule'] = s
        out['machine'] = m
    return out
