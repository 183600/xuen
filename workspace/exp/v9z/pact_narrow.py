"""v9.0 NARROW-PACT: singleton-pivot pruning after cheap YES strategies.

NARROW-PACT keeps the hybrid bracket (rounding -> KARST -> complete) and
adds one more step before the complete closing probe:

    try a ranked list of singleton pivots, Search(h, {i});

if one returns NO, the result is a width-1 (one-dimensional interval)
certificate; if one returns YES, it is a checked schedule.  If none
closes, the complete PACT search runs unchanged.  The pivot phase is a
restriction of the complete search, so every accepted answer is still a
PACT answer; the only new thing is the certificate width.
"""
import sys
import time

sys.path[:0] = ['exp/v9z', 'exp/v9y', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from pact import pact_decide
from pact_round import _dist
from pact_hybrid import HybridPACT


def proof_width(proof):
    """Number of distinct jobs used as branch variables in a BranchProof."""
    if proof is None or not hasattr(proof, 'tree'):
        return None
    jobs = set()

    def walk(node):
        if not isinstance(node, tuple):
            return
        if node[0] == 'node':
            jobs.add(node[1])
            walk(node[4])
            walk(node[5])
    walk(proof.tree)
    return len(jobs)


def pivot_order(inst, h, lp, res, est, q):
    n = inst['n']
    d = _dist(lp, res)
    frac = [sum(v for v in d[i].values()
                 if 1e-7 < v < 1 - 1e-7) for i in range(n)]
    score = [frac[i] * q[i] for i in range(n)]
    return sorted(range(n), key=lambda i: (-score[i], i))


class NarrowPACT(HybridPACT):
    def __init__(self, inst, narrow_attempts=1, **kw):
        super().__init__(inst, **kw)
        self.narrow_attempts = narrow_attempts
        self.narrow_calls = 0
        self.narrow_yes = 0
        self.narrow_no = 0
        self.narrow_fail = 0
        self.narrow_attempts_total = 0
        self.narrow_widths = []
        self.narrow_hook = self._narrow
        self._narrow_overhead = [0, 0, 0, 0]
        self.stats.update(narrow_calls=0, narrow_yes=0, narrow_no=0,
                          narrow_fail=0, narrow_attempts=0)

    def _narrow(self, h, lp, res, est, q):
        n = self.inst['n']
        if res.status != 0:
            return None
        order = pivot_order(self.inst, h, lp, res, est, q)
        attempts = []
        for i in order[:self.narrow_attempts]:
            r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                            root_lp=lp, root_res=res, branch_jobs=[i])
            attempts.append(dict(job=int(i), verdict=r['verdict'],
                                 nodes=r['nodes'], lp=r['lp_solves'],
                                 cert=r['cert_lp'], depth=r['depth']))
            if r['verdict'] is None:
                continue
            self.narrow_calls += 1
            self.narrow_attempts_total += len(attempts)
            self.stats['narrow_calls'] += 1
            self.stats['narrow_attempts'] += len(attempts)
            if r['verdict'] is False:
                w = proof_width(r['proof'])
                self.narrow_no += 1
                self.narrow_widths.append(w)
                self.stats['narrow_no'] += 1
                self.pact_lp += sum(a['lp'] for a in attempts)
                self.pact_cert_lp += sum(a['cert'] for a in attempts)
                self.pact_nodes += 1 + sum(a['nodes'] - 1 for a in attempts)
                self.pact_no += 1
                self.stats['pact_no'] += 1
                self._record_proof(r['proof'])
                self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                       engine='narrow', pivot=int(i),
                                       width=w, attempts=len(attempts)))
                return False, r['proof']
            s, m = r['schedule'], r['machine']
            cmax = max(s[j] + self.inst['p'][j] for j in range(n))
            self.narrow_yes += 1
            self.stats['narrow_yes'] += 1
            self.pact_lp += sum(a['lp'] for a in attempts)
            self.pact_cert_lp += sum(a['cert'] for a in attempts)
            self.pact_nodes += 1 + sum(a['nodes'] - 1 for a in attempts)
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='narrow',
                                   pivot=int(i), attempts=len(attempts)))
            return True, (s, m, cmax)
        self.narrow_calls += 1
        self.narrow_fail += 1
        self.stats['narrow_calls'] += 1
        self.stats['narrow_fail'] += 1
        self.narrow_attempts_total += len(attempts)
        # Fall through to complete search, but keep the pivot attempt cost.
        self._narrow_overhead[0] += len(attempts)
        self._narrow_overhead[1] += sum(a['lp'] for a in attempts)
        self._narrow_overhead[2] += sum(a['cert'] for a in attempts)
        self._narrow_overhead[3] += sum(a['nodes'] - 1 for a in attempts)
        return None

    def _probe(self, h):
        before_lp = self.pact_lp
        before_cert = self.pact_cert_lp
        before_nodes = self.pact_nodes
        self._narrow_overhead = [0, 0, 0, 0]
        got = super()._probe(h)
        if self._narrow_overhead[0]:
            self.pact_lp += self._narrow_overhead[1]
            self.pact_cert_lp += self._narrow_overhead[2]
            self.pact_nodes += self._narrow_overhead[3]
        return got

    def _result(self):
        r = super()._result()
        r['narrow_calls'] = self.narrow_calls
        r['narrow_yes'] = self.narrow_yes
        r['narrow_no'] = self.narrow_no
        r['narrow_fail'] = self.narrow_fail
        r['narrow_attempts'] = self.narrow_attempts_total
        r['narrow_widths'] = list(self.narrow_widths)
        return r


def run_narrow(inst, known, name, idx, **kw):
    t0 = time.time()
    co = NarrowPACT(inst, **kw)
    r = co.optimize()
    dt = time.time() - t0
    r.update(name=name, idx=idx, known=known, t=round(dt, 4))
    b = getattr(co, 'chip', None) or {}
    p = getattr(co, 'pin', None) or {}
    r['chip_lb'] = b.get('lb')
    r['chip_ub'] = b.get('ub')
    r['pin_lb'] = p.get('lb')
    r['pin_solves'] = p.get('solves')
    r['pin_lp'] = getattr(co, 'pin_lp', 0)
    r['bb_lp'] = getattr(co, 'bb_lp', 0)
    r['cert_lp'] = getattr(co, 'cert_lp_total', 0)
    r['ga_stats'] = getattr(co, 'ga_stats', [])
    r['proof_kind'] = getattr(getattr(co, 'lb_proof', None),
                              'kind', None)
    r['stats2'] = getattr(co, 'stats', {})
    r['lns'] = getattr(co, 'lns_stats', None)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
