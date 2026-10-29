"""v9.2 DFR-ICF: dataflow-round sublinear ICF.

The v9.0 state is a certified bracket

    C = (L, U, s, m, pi),   pi : NO(L-1),  Cmax(s)=U,  L<=U.

This module adds a *round* layer.  A round probes a batch H of horizons
without updating the bracket between probes; the batch facts are then
joined by monotone closure:

    L' = max(L, 1 + max{h in H : NO(h)})
    U' = min(U, min{Cmax(s_h) : YES(s_h) in H})

Equivalently, view the horizons as a monotone dataflow chain with facts

    NO(h)  ->  NO(h') for every h' <= h
    YES(c) ->  YES(h') for every h' >= c.

The compressed certificate keeps only the two frontier witnesses
(strongest NO, best YES).  All other batch facts are derivations.

The batch policy ``par:w`` probes w evenly spaced horizons, or all
remaining horizons when the gap is at most w+1.  With a gap of g this
uses at most w probes per round and leaves a gap of at most
ceil((g-w)/(w+1)), hence O(log_{w+1} g) rounds and O(log g) probes.
"""
import math
import sys
import time

sys.path[:0] = ['exp/v9dfr', 'exp/v8u', 'exp/v8o', 'exp/v8i',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from icf import (PartialCertificate, ICFCertificate, cmax, corpora)
from pact import PACT, pact_decide
from rdf import check_schedule


def balanced_batch(L, U, w):
    """Balanced w-probe batch for the candidate horizons [L, U-1].

    If the gap is at most w+1 the whole interval is probed, which closes
    the bracket in one round.  Otherwise choose w probe positions so
    that the w+1 groups of unprobed candidates have sizes differing by
    at most one.  The worst surviving gap is ceil((g-w)/(w+1)).
    """
    L, U, w = int(L), int(U), int(w)
    g = U - L
    if g <= 0 or w <= 0:
        return []
    if g <= w + 1:
        return list(range(L, U))
    w = min(w, g - 1)
    base, rem = divmod(g - w, w + 1)
    sizes = [base + 1] * rem + [base] * (w + 1 - rem)
    idx = []
    pos = sizes[0]
    for j in range(1, w + 1):
        idx.append(pos)
        if j < w:
            pos += 1 + sizes[j]
    return [L + p for p in idx]

def choose_batch(policy, L, U, first, round_no, pin_lp=0, gap0=0):
    if policy == 'seq-lower-first':
        return [L if first else (L + U) // 2]
    if policy == 'seq-binary':
        return [(L + U) // 2]
    if policy == 'seq-upper-first':
        return [U - 1]
    if policy.startswith('par:'):
        w = int(policy.split(':')[1])
        return balanced_batch(L, U, w)
    if policy.startswith('par-lower:'):
        w = int(policy.split(':')[1])
        b = balanced_batch(L, U, w)
        if first and b and b[0] != L:
            b = [L] + b[:w - 1]
        return b
    if policy in ('adaptive-work', 'adaptive-round', 'adaptive-round3',
                  'adaptive-mix'):
        tight = (pin_lp > 0 and gap0 <= 5)
        if tight:
            return [L if first else (L + U) // 2]
        if policy == 'adaptive-work':
            return [(L + U) // 2]
        if policy == 'adaptive-round':
            return balanced_batch(L, U, 2)
        if policy == 'adaptive-round3':
            return balanced_batch(L, U, 3)
        g = U - L
        if g <= 5:
            return [(L + U) // 2]
        if g <= 8:
            return balanced_batch(L, U, 2)
        return balanced_batch(L, U, 3)
    raise ValueError('unknown policy %r' % (policy,))


class Fact:
    """One horizon observation."""
    __slots__ = ('h', 'verdict', 'proof', 'schedule', 'machine',
                 'cmax', 'lp', 'nodes', 'cert_lp')

    def __init__(self, h, verdict, proof=None, schedule=None, machine=None,
                 cmax=None, lp=0, nodes=0, cert_lp=0):
        self.h = int(h)
        self.verdict = verdict          # 'NO' | 'YES' | 'UNK'
        self.proof = proof
        self.schedule = schedule
        self.machine = machine
        self.cmax = cmax
        self.lp = int(lp)
        self.nodes = int(nodes)
        self.cert_lp = int(cert_lp)

    def audit(self, inst):
        try:
            if self.verdict == 'NO':
                return (self.proof is not None and
                        self.proof.h == self.h and
                        bool(self.proof.audit_rdf()))
            if self.verdict == 'YES':
                if self.schedule is None or self.machine is None:
                    return False
                c = cmax(inst, self.schedule)
                return (c == self.cmax and
                        bool(check_schedule(inst, c, self.schedule,
                                            self.machine)))
            return True
        except Exception:
            return False


class BatchCertificate:
    """A certified bracket plus the facts of the last round.

    ``audit_rdf`` is the full derivation check.  ``audit_compressed``
    checks only the two frontier witnesses; by the closure lemma they
    imply the same bracket, so the other facts are redundant.
    """
    kind = 'dfr-batch'

    def __init__(self, inst, L, U, schedule, machine, lb_proof,
                 facts=(), round_no=0, initial_L=None, initial_U=None):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.facts = list(facts)
        self.round_no = int(round_no)
        self.initial_L = self.L if initial_L is None else int(initial_L)
        self.initial_U = self.U if initial_U is None else int(initial_U)

    def frontier(self):
        no = [f for f in self.facts if f.verdict == 'NO']
        yes = [f for f in self.facts if f.verdict == 'YES']
        worst_no = max(no, key=lambda f: f.h) if no else None
        best_yes = min(yes, key=lambda f: f.cmax) if yes else None
        return worst_no, best_yes

    def _base_audit(self):
        if self.lb_proof is None:
            return False
        if self.lb_proof.h != self.L - 1:
            return False
        if not self.lb_proof.audit_rdf():
            return False
        if self.L > self.U:
            return False
        if self.schedule is None or self.machine is None:
            return False
        if cmax(self.inst, self.schedule) != self.U:
            return False
        return bool(check_schedule(self.inst, self.U, self.schedule,
                                   self.machine))

    def audit_compressed(self):
        """Check only the two frontier witnesses and the bracket."""
        try:
            if not self._base_audit():
                return False
            worst_no, best_yes = self.frontier()
            if worst_no is not None and worst_no.h >= self.L:
                return False
            if best_yes is not None and best_yes.cmax < self.U:
                return False
            if worst_no is not None and not worst_no.audit(self.inst):
                return False
            if best_yes is not None and not best_yes.audit(self.inst):
                return False
            return True
        except Exception:
            return False

    def audit_rdf(self):
        """Full derivation audit: all batch facts plus the bracket."""
        try:
            if not self._base_audit():
                return False
            no = [f for f in self.facts if f.verdict == 'NO']
            yes = [f for f in self.facts if f.verdict == 'YES']
            if no:
                top = max(f.h for f in no)
                if top + 1 != self.L and self.L != self.initial_L:
                    return False
            if yes:
                best = min(f.cmax for f in yes)
                if min(best, self.initial_U) != self.U:
                    return False
            for f in self.facts:
                if not f.audit(self.inst):
                    return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _init_state(inst, initial):
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        return int(L), int(U), sched, mach, lb_proof, None
    co = PACT(inst, pact_mode='complete', use_ga=False)
    L, U, sched, mach = co.initial_bounds()
    if U is None:
        return None
    L, U = int(L), int(U)
    lb_proof = co._ensure_lb_proof(L)
    if lb_proof is None:
        r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
        if r['verdict'] is False:
            lb_proof = r['proof']
    return L, U, sched, mach, lb_proof, co


def run_dfr(inst, known, name, idx, policy='par:2', max_probes=64,
            initial=None, collect_facts=False, oracle='pact',
            frontier_kwargs=None):
    t0 = time.time()
    st = _init_state(inst, initial)
    if st is None or st[4] is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-initial-state', t=0.0)
    L, U, sched, mach, lb_proof, co = st
    sched = list(sched) if sched is not None else None
    mach = list(mach) if mach is not None else None
    L0, U0 = L, U
    probes = rounds = 0
    inner_rounds = 0
    lp = nodes = cert_lp = unknown = 0
    partial_ok = partial_fail = 0
    round_log = []
    first = True

    def audit_round(facts):
        nonlocal partial_ok, partial_fail
        cert = BatchCertificate(inst, L, U, sched, mach, lb_proof,
                                facts=facts, round_no=rounds,
                                initial_L=L0, initial_U=U0)
        ok = cert.audit_rdf()
        okc = cert.audit_compressed()
        if ok and okc:
            partial_ok += 1
        else:
            partial_fail += 1
        return cert, ok, okc

    facts0 = []
    audit_round(facts0)
    while L < U and probes < max_probes:
        batch = choose_batch(policy, L, U, first, rounds,
                             pin_lp=getattr(co, 'pin_lp', 0) if co else 0,
                             gap0=U0 - L0)
        batch = [int(h) for h in batch if L <= int(h) < U]
        batch = sorted(set(batch))
        if not batch:
            break
        room = max_probes - probes
        batch = batch[:room]
        L_before, U_before = L, U
        facts = []
        for h in batch:
            if oracle == 'frontier':
                from frontier_round import frontier_decide
                kw = dict(frontier_kwargs or {})
                rf = frontier_decide(inst, h, **kw)
                inner_rounds += int(rf.get('rounds', 0))
                r = dict(verdict=rf['verdict'], proof=rf['proof'],
                         schedule=rf['schedule'], machine=rf['machine'],
                         lp_solves=rf['lp'], nodes=rf['nodes'],
                         cert_lp=rf['cert_lp'])
            else:
                r = pact_decide(inst, h, depthcap=None, nodecap=None)
            probes += 1
            lp += r.get('lp_solves', 0)
            nodes += r.get('nodes', 0)
            cert_lp += r.get('cert_lp', 0)
            v = r['verdict']
            if v is False:
                f = Fact(h, 'NO', proof=r['proof'],
                         lp=r.get('lp_solves', 0),
                         nodes=r.get('nodes', 0),
                         cert_lp=r.get('cert_lp', 0))
                facts.append(f)
                if h + 1 > L:
                    L = h + 1
                    lb_proof = r['proof']
                    if co is not None:
                        co._record_proof(r['proof'])
            elif v is True:
                s2, m2 = r['schedule'], r['machine']
                c2 = cmax(inst, s2)
                f = Fact(h, 'YES', schedule=list(s2), machine=list(m2),
                         cmax=c2, lp=r.get('lp_solves', 0),
                         nodes=r.get('nodes', 0),
                         cert_lp=r.get('cert_lp', 0))
                facts.append(f)
                if c2 < U and check_schedule(inst, c2, s2, m2):
                    U = c2
                    sched, mach = list(s2), list(m2)
            else:
                unknown += 1
                facts.append(Fact(h, 'UNK', lp=r.get('lp_solves', 0),
                                  nodes=r.get('nodes', 0),
                                  cert_lp=r.get('cert_lp', 0)))
        rounds += 1
        first = False
        # A YES at c can make U < L only if L was raised in this same
        # batch above c; soundness rules this out.  Guard anyway.
        if L > U:
            L = U
            lb_proof = max((f.proof for f in facts
                            if f.verdict == 'NO' and f.h == U - 1),
                           key=lambda p: getattr(p, 'h', -1),
                           default=lb_proof)
        cert, ok, okc = audit_round(facts)
        round_log.append(dict(round=rounds, batch=batch,
                              L0=L_before, U0=U_before, L1=L, U1=U,
                              facts=[(f.h, f.verdict, f.cmax)
                                     for f in facts],
                              lp=sum(f.lp for f in facts),
                              nodes=sum(f.nodes for f in facts),
                              audit=ok, compressed=okc,
                              stored_facts=len(facts)))
        if not ok or not okc:
            break
        if not any(f.verdict in ('NO', 'YES') for f in facts):
            break
    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof)
    partial_final = bool(partial.audit_rdf())
    gap0 = U0 - L0
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy, oracle=oracle,
        opt=U, lb=L, lb0=L0, ub0=U0, gap0=gap0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes, rounds=rounds,
        inner_rounds=inner_rounds,
        batch_sizes=[len(x['batch']) for x in round_log],
        pact_lp=lp, pact_nodes=nodes, pact_cert_lp=cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_final, unknown=unknown,
        steps=round_log if collect_facts else [],
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_final),
    )


def round_profile(proof):
    """BFS level profile of a BranchProof/Proof tree."""
    if proof is None or not hasattr(proof, 'tree'):
        return []
    levels = []
    cur = [proof.tree]
    while cur:
        levels.append(len(cur))
        nxt = []
        for nd in cur:
            if nd[0] == 'node':
                nxt.extend([nd[4], nd[5]])
        cur = nxt
    return levels
