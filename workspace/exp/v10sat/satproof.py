"""Proof-carrying SAT decisions for fixed-horizon scheduling.

A `SatNOProof` holds a CaDiCaL DRAT trace.  The audit rebuilds the
canonical CNF from (inst, h, F), checks the trace with a RUP checker, and
requires the final database to be unit-propagation inconsistent.  The
generator's `certified` flag is never trusted.
"""
import sys
import time

sys.path[:0] = ['exp/v10sat', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from satenc import encode, digest, model_schedule, domains
from rup import RUPChecker
from rdf import check_schedule

try:
    from pysat.solvers import Cadical153
except Exception:
    Cadical153 = None


def _expand_forbid(inst, F):
    out = set()
    for (i, t) in F:
        for k in inst['elig'][i]:
            out.add((i, k, t))
    return out


class SatNOProof(Proof):
    """NO(h | F) from a RUP-checkable CNF refutation.

    F is a set of forbidden (job, start-time) pairs.  The CNF is built
    with every (i,k,t) for (i,t) in F removed.  The proof must derive a
    contradiction from that CNF alone.
    """

    kind = 'sat-rup'

    def __init__(self, inst, h, F, lines, nvars=0, clausenum=0,
                 digest_hex=None, stats=None):
        super().__init__(inst, h)
        self.forbid0 = frozenset(F)
        self.lines = list(lines) if lines is not None else None
        self.nvars = int(nvars)
        self.clausenum = int(clausenum)
        self.digest = digest_hex
        self.stats = stats or {}

    def _rebuild(self):
        F3 = _expand_forbid(self.inst, self.forbid0)
        clauses, var, dom = encode(self.inst, self.h, forbid=F3)
        return clauses, var, dom

    def audit_rdf(self):
        try:
            clauses, var, dom = self._rebuild()
            if clauses is None:
                # some job has no allowed start inside the box
                return self.lines is None
            if self.lines is None:
                return False
            if self.digest is not None:
                if digest(clauses, len(var)) != self.digest:
                    return False
            chk = RUPChecker(clauses, nvars=len(var))
            for line in self.lines:
                if not chk.add_drat(line):
                    return False
            # require a unit-propagation contradiction
            return bool(chk.check_rup([]))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def sat_decide(inst, h, F=(), conf_budget=50000, proof_cap=120000,
               time_cap=None, want_stats=False):
    """Return dict(verdict, schedule, machine, proof, stats).

    verdict is True (SAT), False (UNSAT with proof), or None (budget /
    proof cap / solver unavailable).  The SAT side is rechecked by
    check_schedule; the UNSAT side is rechecked by SatNOProof.audit_rdf.
    """
    t0 = time.time()
    stats = dict(engine='sat', sat_t=0.0, proof_lines=0, cnf_vars=0,
                 cnf_clauses=0, rup_t=0.0, reason=None,
                 conf_budget=conf_budget)
    out = dict(verdict=None, schedule=None, machine=None, proof=None,
               stats=stats)
    if Cadical153 is None:
        stats['reason'] = 'no-solver'
        return out
    F3 = _expand_forbid(inst, F)
    clauses, var, dom = encode(inst, h, forbid=F3)
    stats['cnf_vars'] = len(var) if var else 0
    stats['cnf_clauses'] = len(clauses) if clauses else 0
    if clauses is None:
        p = SatNOProof(inst, h, F, None, len(var) if var else 0, 0,
                       None, stats)
        stats['reason'] = 'empty-box'
        out.update(verdict=False, proof=p)
        return out
    try:
        s = Cadical153(bootstrap_with=clauses, with_proof=True)
        s.conf_budget = int(conf_budget)
        ok = s.solve_limited()
        stats['sat_t'] = round(time.time() - t0, 4)
        if ok is True:
            model = s.get_model()
            s.delete()
            got = model_schedule(inst, h, var, model)
            if got is None:
                stats['reason'] = 'bad-model'
                return out
            starts, mach = got
            cmax = max(starts[i] + inst['p'][i] for i in range(inst['n']))
            if cmax > h or not check_schedule(inst, cmax, starts, mach):
                stats['reason'] = 'bad-schedule'
                return out
            stats['reason'] = 'sat'
            out.update(verdict=True, schedule=starts, machine=mach,
                       cmax=cmax)
            return out
        if ok is False:
            lines = s.get_proof()
            s.delete()
            stats['proof_lines'] = len(lines) if lines else 0
            if lines is None:
                stats['reason'] = 'no-proof'
                return out
            if len(lines) > proof_cap:
                stats['reason'] = 'proof-cap'
                return out
            p = SatNOProof(inst, h, F, lines, len(var), len(clauses),
                           digest(clauses, len(var)), stats)
            t1 = time.time()
            good = p.audit_rdf()
            stats['rup_t'] = round(time.time() - t1, 4)
            if not good:
                stats['reason'] = 'rup-fail'
                return out
            stats['reason'] = 'unsat'
            out.update(verdict=False, proof=p)
            return out
        s.delete()
        stats['reason'] = 'budget'
        return out
    except Exception as e:
        stats['reason'] = 'error:%s' % (type(e).__name__,)
        return out


def root_forbid(inst, h):
    """The F=empty root box (all canonical starts allowed)."""
    return frozenset()
