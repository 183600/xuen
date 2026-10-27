"""v9.0 ICF-PACT: invariant-carrying frontier for certified scheduling.

The state of the algorithm is a *partial certificate*:

    (L, U, s, m, pi)

where pi is a NO(L-1) proof, s is a schedule with Cmax(s)=U, and L<=U.
The loop invariant is exactly

    pi proves NO(L-1) and (s,m) proves Cmax=U.

Every probe preserves this invariant.  If the loop stops because L=U,
the state is an optimality certificate: NO(U-1) plus Cmax(s)=U.  If it
stops earlier (budget, interrupt), the same state is still a valid
certified bracket [L,U].  This is the partial-correctness part.

The full frontier version keeps a partition tree and local bounds; this
module implements the one-leaf specialization, which is enough for the
252-instance corpus.  The tree/proof classes below are the certificate
format used by the general version.
"""
import sys
import time

sys.path[:0] = ['exp/v8u', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import BranchProof, SubsumptionProof, _domain
from cert import verify
from rdf import check_schedule
from pact import PACT, pact_decide


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


def _proof_forbid(p):
    """Root forbidden set of a NO proof, if it exposes one."""
    seen = set()
    while p is not None and id(p) not in seen:
        seen.add(id(p))
        f = getattr(p, 'forbid0', None)
        if f is not None:
            return frozenset(f)
        p = getattr(p, 'source', None)
    return frozenset()


class CertLeafProof(Proof):
    """A Farkas/empty leaf lifted into the frontier proof language."""

    kind = 'icf-leaf'

    def __init__(self, inst, h, F, cert):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.cert = cert

    def audit_rdf(self):
        try:
            c = self.cert
            if c is None:
                return False
            if c.get('kind') == 'empty':
                i = c['job']
                lo, hi = _domain(self.inst, self.h, i)
                return all((i, t) in self.forbid0
                           for t in range(lo, hi + 1))
            return bool(verify(self.inst, self.h, c,
                               forbid=self.forbid0))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def branch_to_frontier(proof):
    """Convert a BranchProof tree into a FrontierProof tree at the same h."""

    def conv(node):
        tag = node[0]
        if tag == 'leaf':
            _, F, cert = node
            return ('leaf', frozenset(F), proof.h,
                    CertLeafProof(proof.inst, proof.h, F, cert))
        if tag == 'empty':
            _, F, i = node
            return ('leaf', frozenset(F), proof.h,
                    CertLeafProof(proof.inst, proof.h, F,
                                  {'kind': 'empty', 'job': i}))
        _, i, mid, parent_F, lo, hi = node
        return ('split', i, mid, frozenset(parent_F),
                conv(lo), conv(hi))

    return FrontierProof(proof.inst, proof.h, conv(proof.tree))


class PartialCertificate:
    """A certified bracket L <= OPT <= U, plus the local witnesses."""

    kind = 'icf-partial'

    def __init__(self, inst, L, U, schedule, machine, lb_proof,
                 probe=0):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.probe = int(probe)

    def _sched_ok(self):
        if self.schedule is None or self.machine is None:
            return False
        c = cmax(self.inst, self.schedule)
        if c != self.U:
            return False
        return bool(check_schedule(self.inst, c, self.schedule,
                                   self.machine))

    def audit_rdf(self):
        try:
            if self.lb_proof is None:
                return False
            if self.lb_proof.h != self.L - 1:
                return False
            if not self.lb_proof.audit_rdf():
                return False
            if self.L > self.U:
                return False
            return self._sched_ok()
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class FrontierProof(Proof):
    """A partition tree whose leaves are NO proofs at local horizons.

    Node forms:
      ('leaf', F, h, proof)          proof is NO(h) for a box F0 subset F
      ('split', i, mid, F, lo, hi)   children partition F on job i

    The target horizon is self.h.  A leaf is sound if its proof has
    horizon >= target and its root forbidden set is contained in F.
    """

    kind = 'icf-frontier'

    def __init__(self, inst, target, tree):
        super().__init__(inst, target)
        self.target = int(target)
        self.tree = tree

    def _domain_times(self, i, F):
        lo, hi = _domain(self.inst, self.target, i)
        return [t for t in range(lo, hi + 1) if (i, t) not in F]

    def _check(self, node, F):
        tag = node[0]
        if tag == 'leaf':
            _, leaf_F, h, proof = node
            if set(leaf_F) != set(F):
                return False
            if proof is None or proof.h != h:
                return False
            if h < self.target:
                return False
            if not proof.audit_rdf():
                return False
            return set(_proof_forbid(proof)) <= set(F)
        if tag == 'split':
            _, i, mid, parent_F, lo, hi = node
            if set(parent_F) != set(F):
                return False
            times = sorted(self._domain_times(i, F))
            lo_t = [t for t in times if t > mid]
            hi_t = [t for t in times if t <= mid]
            if not lo_t or not hi_t:
                return False
            loF = F | {(i, t) for t in lo_t}
            hiF = F | {(i, t) for t in hi_t}
            return self._check(lo, loF) and self._check(hi, hiF)
        return False

    def audit_rdf(self):
        try:
            return self._check(self.tree, frozenset())
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


class ICFCertificate:
    """Final one-leaf frontier: NO(U-1) plus a schedule of length U."""

    kind = 'icf-opt'

    def __init__(self, inst, opt, schedule, machine, lb_proof):
        self.inst = inst
        self.opt = int(opt)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.frontier = FrontierProof(
            inst, self.opt - 1,
            ('leaf', frozenset(), lb_proof.h if lb_proof else -1,
             lb_proof))

    def audit_rdf(self):
        try:
            if self.lb_proof is None or self.lb_proof.h != self.opt - 1:
                return False
            if not self.lb_proof.audit_rdf():
                return False
            if not self.frontier.audit_rdf():
                return False
            if self.schedule is None or self.machine is None:
                return False
            if cmax(self.inst, self.schedule) != self.opt:
                return False
            return bool(check_schedule(self.inst, self.opt,
                                       self.schedule, self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def _choose_h(policy, L, U, first):
    if U - L <= 0:
        return L
    if policy == 'lower-first':
        return L if first else (L + U) // 2
    if policy == 'upper-first':
        return U - 1
    if policy == 'binary':
        return (L + U) // 2
    if policy == 'pact':
        return L if U - L <= 4 else (L + U) // 2
    if policy == 'lower-then-binary':
        return L if first else (L + U) // 2
    if policy.startswith('gap:'):
        thr = int(policy.split(':')[1])
        if U - L <= thr:
            return L if first else (L + U) // 2
        return (L + U) // 2
    raise ValueError('unknown policy %r' % (policy,))


def run_icf(inst, known, name, idx, policy='lower-first', max_probes=64,
            use_pact_init=True, initial=None, collect_proof=False):
    """Run the one-leaf ICF loop and return a benchmark row."""
    t0 = time.time()
    if initial is not None:
        L, U, sched, mach, lb_proof = initial
        L, U = int(L), int(U)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        co = None
    else:
        co = PACT(inst, pact_mode='complete', use_ga=False)
        lb, ub, sched, mach = co.initial_bounds()
        if ub is None:
            return dict(name=name, idx=idx, known=known, policy=policy,
                        ok=False, error='no-initial-ub', t=0.0)

        L, U = int(lb), int(ub)
        sched = list(sched) if sched is not None else None
        mach = list(mach) if mach is not None else None
        lb_proof = co._ensure_lb_proof(L)
        if lb_proof is None:
            r = pact_decide(inst, L - 1, depthcap=None, nodecap=None)
            if r['verdict'] is False:
                lb_proof = r['proof']
    if lb_proof is None:
        return dict(name=name, idx=idx, known=known, policy=policy,
                    ok=False, error='no-lb-proof', t=0.0)

    probes = 0
    pact_lp = 0
    pact_nodes = 0
    pact_cert_lp = 0
    unknown = 0
    partial_ok = 0
    partial_fail = 0
    steps = []
    first = True
    lb0, ub0 = L, U

    def audit_state():
        nonlocal partial_ok, partial_fail
        pc = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                probe=probes)
        if pc.audit_rdf():
            partial_ok += 1
        else:
            partial_fail += 1
        return pc

    audit_state()
    while L < U and probes < max_probes:
        L0, U0 = L, U
        h = _choose_h(policy, L, U, first)
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        probes += 1
        first = False
        pact_lp += r.get('lp_solves', 0)
        pact_nodes += r.get('nodes', 0)
        pact_cert_lp += r.get('cert_lp', 0)

        if r['verdict'] is False:
            proof = r['proof']
            L = h + 1
            lb_proof = proof
            if co is not None:
                co._record_proof(proof)
            steps.append(dict(h=h, v=False, kind=proof.kind,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        elif r['verdict'] is True:
            s2, m2 = r['schedule'], r['machine']
            c2 = cmax(inst, s2)
            if c2 < U and check_schedule(inst, c2, s2, m2):
                U = c2
                sched, mach = list(s2), list(m2)
            steps.append(dict(h=h, v=True, cmax=c2,
                              lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
        else:
            unknown += 1
            steps.append(dict(h=h, v=None, lp=r.get('lp_solves', 0),
                              nodes=r.get('nodes', 0),
                              L0=L0, U0=U0, L1=L, U1=U))
            break
        audit_state()

    final = ICFCertificate(inst, U, sched, mach, lb_proof) \
        if L == U else None
    final_ok = bool(final is not None and final.audit_rdf())
    partial = PartialCertificate(inst, L, U, sched, mach, lb_proof,
                                 probe=probes)
    partial_ok_final = bool(partial.audit_rdf())
    dt = time.time() - t0
    return dict(
        name=name, idx=idx, known=known, policy=policy,
        opt=U, lb=L, lb0=lb0, ub0=ub0,
        certified=bool(L == U and final_ok),
        audit=final_ok, proof=final_ok,
        cert_h=(U - 1 if L == U else None),
        queries=probes, probes=probes,
        pact_lp=pact_lp, pact_nodes=pact_nodes,
        pact_cert_lp=pact_cert_lp,
        pin_lp=getattr(co, 'pin_lp', 0),
        partial_ok=partial_ok, partial_fail=partial_fail,
        partial_final=partial_ok_final,
        unknown=unknown, steps=steps,
        proof_kind=(final.lb_proof.kind if final is not None else
                    getattr(lb_proof, 'kind', None)),
        total_audit=final_ok,
        t=round(dt, 4),
        schedule=list(sched) if sched is not None else None,
        machine=list(mach) if mach is not None else None,
        lb_proof=(lb_proof if collect_proof else None),
        ok=bool(L == U and U == known and final_ok and
                partial_fail == 0 and partial_ok_final),
    )


def corpora():
    from chip import base_corpus, pert_corpus, stress_corpus
    for tag, rows in (('base', base_corpus()),
                      ('pert', pert_corpus()),
                      ('stress', stress_corpus())):
        for row in rows:
            if len(row) == 4:
                name, idx, inst, known = row
            else:
                idx, known, inst = row
                name = tag
            yield tag, name, idx, inst, known
