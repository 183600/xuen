"""v9.1 GALE-PACT: global-lift adaptive ledger frontier.

State:
    (T, G, piG, U, s, m, budgets)

T is a partition tree of start-time boxes.  Each leaf has a local bound
L_f and a local proof pi_f : NO(L_f-1 | F_f).  G is a *global floor* with
a proof piG : NO(G-1) for the root.  The schedule (s,m) has Cmax=U.

The invariant is the v9.0 partial certificate for the floor:

    piG : NO(G-1),  Cmax(s)=U,  G<=U,

plus the search invariant that every leaf's effective bound
max(L_f, G) is valid (the global proof covers leaves below G).

Two new transitions:

  SCOUT     : probe the root at h=G.  NO raises G and is broadcast to
              every leaf below the new floor in O(1) semantic time;
              YES lowers U; UNKNOWN switches to local refinement.
  LIFT      : if every leaf's effective bound is > G, the frontier's
              partition tree itself is a root proof at Lmin-1.  Promote
              G to Lmin and use the tree as the global proof.

The implementation materialises the floor into local leaves (O(leaves)
per scout) for audit simplicity; the formal data structure keeps a lazy
floor tag and a floor bucket, so the broadcast is O(1) plus lazy
deletion.

This module is deliberately a prototype: it runs serially, with the
same PACT oracle as v9.0.  The parallel BSP schedule is described in the
artifact and simulated by batching independent local probes.
"""
import sys
import time
import heapq

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from sage import _domain
from rdf import check_schedule
from icf import (PartialCertificate, ICFCertificate, cmax,
                 _choose_h)
from pact import PACT, pact_decide
from tamo import (Leaf, Split, collect_leaves, split_leaf, close_empty,
                  allowed_times, box_measure, snapshot, tree_depth,
                  TamoFrontier, TamoCertificate, pact_initial,
                  _choose_split)


def _eff_L(leaf):
    return leaf.L if not leaf.closed else leaf.h + 1


def _open_leaves(root):
    out = []
    def walk(x):
        if isinstance(x, Leaf):
            if not x.closed:
                out.append(x)
        else:
            walk(x.lo)
            walk(x.hi)
    walk(root)
    return out


def _all_leaves(root):
    out = []
    collect_leaves(root, out)
    return out


def _probe_task(task):
    """Top-level worker for a BSP batch (picklable arguments/results)."""
    inst, F, h, nodecap = task
    r = pact_decide(inst, h, depthcap=None, nodecap=nodecap,
                    forbid0=F)
    # Some LP branches return numpy.bool_; normalise so the batch merge
    # can use identity tests (``is True`` / ``is False``).
    v = r.get('verdict')
    if v is not None:
        r['verdict'] = bool(v)
    return r


class GaleState:
    """Mutable ledger: heap, live leaves and per-leaf budgets."""

    def __init__(self, inst, root, G, piG, U, s, m):
        self.inst = inst
        self.holder = [root]
        self.G = int(G)
        self.piG = piG
        self.U = int(U)
        self.s = list(s)
        self.m = list(m)
        self.heap = []
        self.live = set()
        self.byid = {}
        self.budgets = {}
        self._reheap()

    def _reheap(self):
        self.heap = []
        self.live.clear()
        self.byid.clear()
        for l in _all_leaves(self.holder[0]):
            if l.closed:
                continue
            self.live.add(id(l))
            self.byid[id(l)] = l
            heapq.heappush(self.heap, (l.L, -l.mu, id(l)))

    def push(self, l):
        self.live.add(id(l))
        self.byid[id(l)] = l
        heapq.heappush(self.heap, (l.L, -l.mu, id(l)))

    def remove(self, l):
        self.live.discard(id(l))
        self.byid.pop(id(l), None)
        self.budgets.pop(id(l), None)

    def pop_min(self):
        while self.heap:
            L, _, lid = self.heap[0]
            l = self.byid.get(lid)
            if l is None or lid not in self.live:
                heapq.heappop(self.heap)
                continue
            if l.L != L:
                heapq.heappop(self.heap)
                continue
            heapq.heappop(self.heap)
            return l
        return None

    def materialize(self, G, piG):
        """Raise every leaf below the new floor to G with the global proof."""
        self.G = int(G)
        self.piG = piG
        changed = False
        for l in _all_leaves(self.holder[0]):
            if l.closed:
                if l.h < G - 1:
                    l.closed = False
                    l.h = None
                    l.L = G
                    l.proof = piG
                    changed = True
                continue
            if l.L < G:
                l.L = G
                l.proof = piG
                changed = True
        if changed:
            self._reheap()

    def prune(self, U):
        """Close leaves dominated by U.  Returns True if no open leaves."""
        self.U = int(U)
        H = U - 1
        for l in _all_leaves(self.holder[0]):
            if l.closed:
                continue
            if close_empty(self.inst, l, H):
                self.remove(l)
            elif l.L >= U:
                l.closed = True
                l.h = l.L - 1
                self.remove(l)
        return not self.live

    def frontier_L(self):
        ls = _all_leaves(self.holder[0])
        if not ls:
            return None
        return min(_eff_L(l) for l in ls)

    def frontier_proof(self, target):
        fp = TamoFrontier(self.inst, target,
                          snapshot(self.holder[0]))
        fp.h = int(target)
        return fp


def run_gale(inst, known, name, idx, initial=None,
             scout=True, scout_gap=5, scout_cap=8, scout_max=64,
             B0=1, Bmax=8, policy='lower', max_probes=200000,
             audit_every=True, include_tree=False, debug=False,
             scout_batch=1, pool=None):
    """Run GALE serially and return a benchmark row."""
    t0 = time.time()
    if initial is None:
        try:
            L0, U0, s, m, proof0 = pact_initial(inst)
        except Exception as exc:
            return dict(name=name, idx=idx, known=known, ok=False,
                        error='init:%s' % exc, t=0.0)
    else:
        L0, U0, s, m, proof0 = initial
    L0, U0 = int(L0), int(U0)
    s, m = list(s), list(m)
    if not check_schedule(inst, cmax(inst, s), s, m):
        return dict(name=name, idx=idx, known=known, ok=False,
                    error='bad-initial-schedule', t=0.0)

    H0 = U0 - 1
    Mmax = box_measure(inst, H0, frozenset())
    root = Leaf(frozenset(), L0, proof0, Mmax)
    st = GaleState(inst, root, L0, proof0, U0, s, m)
    st.budgets[id(root)] = B0

    probes = scouts = scout_no = scout_yes = scout_unknown = 0
    yes = no = unknown = escalations = 0
    splits = closes_lift = closes_empty = 0
    lp = nodes = cert_lp = 0
    max_leaves = 1
    partial_checks = partial_fail = 0
    lifts = 0
    scout_streak = 0
    scout_enabled = bool(scout)
    scout_budget = None if (U0 - L0) <= scout_gap else scout_cap

    def audit_state():
        nonlocal partial_checks, partial_fail
        if not audit_every:
            return
        pc = PartialCertificate(inst, st.G, st.U, st.s, st.m,
                                st.piG, probe=probes)
        partial_checks += 1
        if not pc.audit_rdf():
            partial_fail += 1
            if debug:
                import traceback
                print('PARTIAL FAIL', probes, st.G, st.U,
                      type(st.piG).__name__, 'pi.h', getattr(st.piG,'h',None),
                      'pi_audit', getattr(st.piG,'audit_rdf',lambda:None)(),
                      'cmax', cmax(inst, st.s),
                      'sched', check_schedule(inst, st.U, st.s, st.m),
                      flush=True)

    audit_state()

    while st.G < st.U and probes < max_probes:
        progressed = False

        # ---------------------------------------------------------- SCOUT
        if scout_enabled and st.G < st.U:
            W = max(1, int(scout_batch))
            hs = list(range(st.G, min(st.G + W, st.U)))
            tasks = [(inst, frozenset(), h, scout_budget) for h in hs]
            if W == 1 or pool is None:
                rs = [_probe_task(t) for t in tasks]
            else:
                rs = pool.map(_probe_task, tasks)
            probes += len(hs)
            scouts += len(hs)
            lp += sum(r.get('lp_solves', 0) for r in rs)
            nodes += sum(r.get('nodes', 0) for r in rs)
            cert_lp += sum(r.get('cert_lp', 0) for r in rs)
            no_items = [(h, r) for h, r in zip(hs, rs)
                        if r['verdict'] is False]
            yes_items = [(h, r) for h, r in zip(hs, rs)
                         if r['verdict'] is True]
            unk_items = [(h, r) for h, r in zip(hs, rs)
                         if r['verdict'] is None]
            if unk_items:
                scout_unknown += len(unk_items)
            if no_items:
                hno, rno = max(no_items, key=lambda x: x[0])
                scout_no += len(no_items)
                st.materialize(hno + 1, rno['proof'])
                progressed = True
                scout_streak += 1
                if scout_streak >= 2:
                    scout_enabled = False
                    scout_streak = 0
                if st.prune(st.U):
                    break
            if yes_items:
                hy, ry = min(yes_items, key=lambda x: x[0])
                scout_yes += len(yes_items)
                c = cmax(inst, ry['schedule'])
                if c < st.U and check_schedule(inst, c, ry['schedule'],
                                               ry['machine']):
                    st.U = c
                    st.s = list(ry['schedule'])
                    st.m = list(ry['machine'])
                scout_streak = 0
                progressed = True
                if st.prune(st.U):
                    break
            if unk_items:
                if not no_items and not yes_items:
                    scout_enabled = False
                    scout_streak = 0
                    if (scout_budget is not None and
                            scout_budget < scout_max):
                        scout_budget = min(scout_max, 2 * scout_budget)
                        scout_enabled = True
            audit_state()
            if st.G >= st.U:
                break

        # ------------------------------------------------------ FRONTIER LIFT
        Lmin = st.frontier_L()
        if Lmin is not None and Lmin > st.G:
            target = Lmin - 1
            fp = st.frontier_proof(target)
            if fp.audit_rdf() and fp.L is not None:
                # The tree may prove a stronger bound than the leaf
                # minimum; rebuild at the actual horizon so that
                # piG.h == G-1 exactly.
                if fp.L > Lmin:
                    target = int(fp.L) - 1
                    fp2 = st.frontier_proof(target)
                    if fp2.audit_rdf() and fp2.L == fp.L:
                        fp = fp2
                st.G = int(fp.L)
                st.piG = fp
                lifts += 1
                progressed = True
                scout_enabled = bool(scout)
                scout_streak = 0
                if st.G >= st.U:
                    audit_state()
                    break
                audit_state()

        # -------------------------------------------------------- LOCAL PROBE
        if st.G < st.U:
            leaf = st.pop_min()
            if leaf is not None and leaf.L < st.U:
                if policy == 'lower':
                    h = leaf.L
                elif policy == 'upper':
                    h = st.U - 1
                elif policy == 'target':
                    h = st.U - 1
                else:
                    h = _choose_h(policy, leaf.L, st.U, False)
                if h >= st.U:
                    h = st.U - 1
                if h < st.G:
                    h = st.G
                b = st.budgets.get(id(leaf), B0)
                r = pact_decide(inst, h, depthcap=None, nodecap=b,
                                forbid0=frozenset(leaf.F))
                probes += 1
                lp += r.get('lp_solves', 0)
                nodes += r.get('nodes', 0)
                cert_lp += r.get('cert_lp', 0)
                progressed = True
                if r['verdict'] is False:
                    no += 1
                    leaf.proof = r['proof']
                    leaf.L = h + 1
                    if h >= st.U - 1 or leaf.L >= st.U:
                        leaf.closed = True
                        leaf.h = h
                        st.remove(leaf)
                        closes_lift += 1
                    else:
                        st.push(leaf)
                elif r['verdict'] is True:
                    yes += 1
                    c = cmax(inst, r['schedule'])
                    if c < st.U and check_schedule(inst, c, r['schedule'],
                                                   r['machine']):
                        st.U = c
                        st.s = list(r['schedule'])
                        st.m = list(r['machine'])
                    if leaf.L < st.U:
                        st.push(leaf)
                    else:
                        leaf.closed = True
                        leaf.h = leaf.L - 1
                        st.remove(leaf)
                        closes_lift += 1
                    if st.prune(st.U):
                        break
                else:
                    unknown += 1
                    if b < Bmax:
                        st.budgets[id(leaf)] = min(Bmax, 2 * b)
                        escalations += 1
                        st.push(leaf)
                    else:
                        pair = _choose_split(inst, leaf, st.U - 1, r,
                                             'oracle')
                        if pair is None:
                            st.push(leaf)
                        else:
                            i, mid = pair
                            sp = split_leaf(inst, leaf, i, mid,
                                            st.U - 1, H0)
                            if sp is None:
                                st.push(leaf)
                            else:
                                splits += 1
                                if leaf.parent is None:
                                    st.holder[0] = sp
                                st.remove(leaf)
                                for c in (sp.lo, sp.hi):
                                    if close_empty(inst, c, st.U - 1):
                                        closes_empty += 1
                                    else:
                                        st.budgets[id(c)] = B0
                                        st.push(c)
                                max_leaves = max(max_leaves,
                                                 len(_all_leaves(
                                                     st.holder[0])))
                audit_state()

        if not progressed and not scout_enabled:
            break

    # ------------------------------------------------------------- FINAL
    Lmin = st.frontier_L()
    if Lmin is not None and Lmin > st.G:
        target = Lmin - 1
        fp = st.frontier_proof(target)
        if fp.audit_rdf() and fp.L is not None:
            if fp.L > Lmin:
                target = int(fp.L) - 1
                fp2 = st.frontier_proof(target)
                if fp2.audit_rdf() and fp2.L == fp.L:
                    fp = fp2
            st.G = int(fp.L)
            st.piG = fp
            lifts += 1

    if st.G == st.U:
        final = ICFCertificate(inst, st.U, st.s, st.m, st.piG)
        final_ok = bool(final.audit_rdf())
    else:
        final_ok = False
    partial = PartialCertificate(inst, st.G, st.U, st.s, st.m,
                                 st.piG, probe=probes)
    partial_final = bool(partial.audit_rdf())

    dt = time.time() - t0
    out = dict(
        name=name, idx=idx, known=known,
        L0=L0, U0=U0, G=st.G, L=st.G, U=st.U, opt=st.U,
        probes=probes, scouts=scouts, scout_no=scout_no,
        scout_yes=scout_yes, scout_unknown=scout_unknown,
        yes=yes, no=no, unknown=unknown, escalations=escalations,
        splits=splits, closes_lift=closes_lift,
        closes_empty=closes_empty, lifts=lifts,
        lp=lp, nodes=nodes, cert_lp=cert_lp,
        leaves=len(_all_leaves(st.holder[0])),
        open=sum(1 for l in _all_leaves(st.holder[0]) if not l.closed),
        max_leaves=max_leaves,
        depth=tree_depth(st.holder[0]),
        partial_checks=partial_checks, partial_fail=partial_fail,
        certified=bool(st.G == st.U and final_ok),
        audit=final_ok, proof=final_ok,
        partial_final=partial_final,
        cert_h=(st.U - 1 if st.G == st.U else None),
        t=round(dt, 4),
        ok=bool(st.G == st.U == known and final_ok and
                partial_fail == 0),
    )
    if include_tree:
        out['tree'] = snapshot(st.holder[0])
        out['schedule'] = st.s
        out['machine'] = st.m
    return out
