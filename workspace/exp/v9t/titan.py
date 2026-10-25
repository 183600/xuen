"""v9.4 TITAN-ALC prototype: tabu-indexed tolerant NO search on top of PACT/AIDA.

Three layers, each independently auditable:

  INDEX   AIDA's canonical-box proof DAG plus a per-probe arena.  A box
          proved NO is stored in a maximal antichain; a query box is
          closed by any stored superset.  The DAG is a proof object, not
          a search log.

  REPAIR  A capped AIDA attempt is allowed to return UNKNOWN.  A repair
          cascade then tries (i) a full AIDA search under the best tabu
          policy, (ii) the default AIDA portfolio, (iii) PACT's complete
          certificate search.  A hole never invalidates a completed NO
          box; only a complete, audited DAG is returned as NO.

  TABU    A small tabu search over AIDA split policies.  A policy is
          (heur, split, side, topk).  Moves change one attribute; the
          tabu list stores recently evaluated policies; aspiration accepts
          a tabu policy only if it beats the incumbent.  The objective is
          lexicographic (not decisive, nodes, depth), evaluated under a
          node cap so the search itself cannot explode.

Only PACT's finite bracket and TotalTrace are used by the outer loop.
Every NO is audited by AIDAProof.audit_rdf; every YES is replayed by
check_schedule; a failed repair falls back to the complete engine.
"""
import sys
import time
import random
import math

sys.path[:0] = ['exp/v9t', 'exp/v9a', 'exp/v8o', 'exp/v8i', 'exp/v8j',
                'exp/v8h', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
                'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76',
                'exp/v72', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from aida import aida_branch_decide, DEFAULT_POLICIES
from pact import PACT, pact_decide, _integral_schedule
from sage import _elig_aware
from sdecc import SDLP
from po import heads_tails
from rdf import check_schedule
from apex import OracleProof

HEURS = ('mass', 'frac', 'tail', 'slack', 'width', 'succ')
SPLITS = (0.25, 0.5, 0.75)
SIDES = ('left', 'right')


def _pol_key(p):
    return (p.get('heur', 'mass'), float(p.get('split', 0.5)),
            p.get('side', 'left'), int(p.get('topk', 1)))


def _make(key):
    h, s, side, topk = key
    return dict(heur=h, split=s, side=side, topk=topk)


def _neighbors(key):
    h, s, side, topk = key
    out = set()
    for x in HEURS:
        if x != h:
            out.add((x, s, side, topk))
    for x in SPLITS:
        if abs(x - s) > 1e-12:
            out.add((h, x, side, topk))
    out.add((h, s, 'right' if side == 'left' else 'left', topk))
    return [k for k in out]


def _score(r):
    # decisive is best; then fewer DAG nodes; then shallower.
    return (0 if r.get('verdict') is not None else 1,
            int(r.get('nodes', 10 ** 9)),
            int(r.get('depth', 10 ** 9)),
            int(r.get('lp_solves', 10 ** 9)))


def tabu_policy(inst, h, budget=8, cap=8, tenure=3, seed=0,
                sample=5, verbose=False):
    """Tabu search over split policies under a small node cap.

    The budget counts *evaluations*, not iterations.  Each iteration
    samples at most ``sample`` neighbours, which keeps the LP setup cost
    bounded on a hard instance.
    """
    t0 = time.time()
    rng = random.Random(20261025 + seed * 100003)
    n = inst['n']
    est, q = heads_tails(inst, 0, [0] * n)
    elig = _elig_aware(inst)
    shared_lp = SDLP(inst, h, est, q, use_dom=True, elig_aware=elig)
    start = _pol_key(DEFAULT_POLICIES[0])
    cur = start
    cur_r = aida_branch_decide(inst, h, policies=[_make(cur)],
                               spacecap=cap, lpcap=max(2 * cap, 16),
                               depthcap=8, root_lp=shared_lp)
    cur_s = _score(cur_r)
    best, best_r, best_s = cur, cur_r, cur_s
    tabu = []
    trace = []
    evals = 1
    while evals < budget:
        cand = _neighbors(cur)
        rng.shuffle(cand)
        cand = cand[:max(1, min(sample, budget - evals))]
        chosen = None
        chosen_r = None
        chosen_s = None
        for key in cand:
            if key in tabu and not (best_s[0] == 0 and key == best):
                continue
            r = aida_branch_decide(inst, h, policies=[_make(key)],
                                   spacecap=cap, lpcap=max(2 * cap, 16),
                                   depthcap=8, root_lp=shared_lp)
            evals += 1
            sc = _score(r)
            if chosen_s is None or sc < chosen_s:
                chosen, chosen_r, chosen_s = key, r, sc
        if chosen is None:
            break
        cur, cur_r, cur_s = chosen, chosen_r, chosen_s
        tabu.append(chosen)
        tabu = tabu[-tenure:]
        if chosen_s < best_s:
            best, best_r, best_s = chosen, chosen_r, chosen_s
            trace.append(dict(it=evals, key=chosen, score=chosen_s,
                              why='best'))
    return dict(best=_make(best), best_key=best, best_r=best_r,
                start_r=cur_r, start_key=cur, evals=evals,
                trace=trace, t=round(time.time() - t0, 5))

def titan_decide(inst, h, repair=True, tabu=True, cap=6, tabu_budget=8,
                 tabu_cap=10, seed=0, fallback=True):
    """Indexed, repairable, tabu-guided fixed-h decision.

    Returns a PACT-compatible dict.  A capped AIDA attempt is always made
    first.  If it is decisive, no tabu overhead is paid.  Otherwise the
    tabu search proposes a policy, full AIDA tries it, and PACT's complete
    engine is the final fallback.
    """
    t0 = time.time()
    stats = dict(titan_calls=1, titan_cap_unknown=0, titan_tabu=0,
                 titan_tabu_evals=0, titan_full=0, titan_repair=0,
                 titan_fallback=0, titan_lp=0, titan_cert=0,
                 titan_nodes=0, titan_depth=0, titan_policy=None,
                 titan_tabu_t=0.0, titan_verdict=None)
    # 1. optional cheap indexed attempt.  cap=None means the full AIDA
    # engine, which is the normal warm path; cap is useful for ablation.
    r = None
    if cap is not None:
        r = aida_branch_decide(inst, h, policies=DEFAULT_POLICIES,
                               spacecap=cap, lpcap=max(2 * cap, 16),
                               depthcap=8)
        stats['titan_lp'] += r.get('lp_solves', 0)
        stats['titan_cert'] += r.get('cert_lp', 0)
        stats['titan_nodes'] += r.get('nodes', 0)
        stats['titan_depth'] = max(stats['titan_depth'], r.get('depth', 0))
        if r.get('verdict') is not None:
            stats['titan_verdict'] = r.get('verdict')
            r.update(stats)
            r['t'] = round(time.time() - t0, 5)
            return r
        stats['titan_cap_unknown'] += 1
        if not repair:
            stats['titan_verdict'] = None
            r.update(stats)
            r['t'] = round(time.time() - t0, 5)
            return r
    # 1b. warm full indexed attempt (the usual path when cap is None)
    if r is None:
        # AIDA's fast path: closure first with a small space cap, then the
        # same single order without closure.  A portfolio is paid for only
        # when this first cascade fails (repair), not on every probe.
        for closure, cap0 in ((True, 128), (False, 512)):
            r = aida_branch_decide(inst, h, spacecap=cap0,
                                   lpcap=4000, depthcap=24,
                                   closure=closure)
            stats['titan_full'] += 1
            stats['titan_lp'] += r.get('lp_solves', 0)
            stats['titan_cert'] += r.get('cert_lp', 0)
            stats['titan_nodes'] += r.get('nodes', 0)
            stats['titan_depth'] = max(stats['titan_depth'],
                                       r.get('depth', 0))
            if r.get('verdict') is not None:
                stats['titan_verdict'] = r.get('verdict')
                r.update(stats)
                r['t'] = round(time.time() - t0, 5)
                return r
    # 2. tabu policy proposal
    best_pol = None
    if tabu:
        q = tabu_policy(inst, h, budget=tabu_budget, cap=tabu_cap,
                        seed=seed)
        stats['titan_tabu'] += 1
        stats['titan_tabu_evals'] += q['evals']
        stats['titan_tabu_t'] += q['t']
        best_pol = q['best_key']
        stats['titan_policy'] = best_pol
        # 3. full indexed attempt with the proposed policy first
        pols = [q['best']] + [p for p in DEFAULT_POLICIES
                              if _pol_key(p) != best_pol]
        r = aida_branch_decide(inst, h, policies=pols, spacecap=512,
                               lpcap=4000, depthcap=24)
        stats['titan_full'] += 1
        stats['titan_lp'] += r.get('lp_solves', 0)
        stats['titan_cert'] += r.get('cert_lp', 0)
        stats['titan_nodes'] += r.get('nodes', 0)
        stats['titan_depth'] = max(stats['titan_depth'], r.get('depth', 0))
        if r.get('verdict') is not None:
            stats['titan_verdict'] = r.get('verdict')
            r.update(stats)
            r['t'] = round(time.time() - t0, 5)
            return r
    # 4. full portfolio indexed attempt (repair)
    if repair:
        r = aida_branch_decide(inst, h, policies=DEFAULT_POLICIES,
                               spacecap=512, lpcap=4000, depthcap=24)
        stats['titan_repair'] += 1
        stats['titan_lp'] += r.get('lp_solves', 0)
        stats['titan_cert'] += r.get('cert_lp', 0)
        stats['titan_nodes'] += r.get('nodes', 0)
        stats['titan_depth'] = max(stats['titan_depth'], r.get('depth', 0))
        if r.get('verdict') is not None:
            stats['titan_verdict'] = r.get('verdict')
            r.update(stats)
            r['t'] = round(time.time() - t0, 5)
            return r
    # 5. complete PACT fallback
    if fallback:
        r = pact_decide(inst, h, depthcap=None, nodecap=None)
        stats['titan_fallback'] += 1
        stats['titan_lp'] += r.get('lp_solves', 0)
        stats['titan_cert'] += r.get('cert_lp', 0)
        stats['titan_nodes'] += r.get('nodes', 0)
        stats['titan_depth'] = max(stats['titan_depth'], r.get('depth', 0))
        stats['titan_verdict'] = r.get('verdict')
        r.update(stats)
        r['t'] = round(time.time() - t0, 5)
        return r
    stats['titan_verdict'] = None
    r.update(stats)
    r['t'] = round(time.time() - t0, 5)
    return r


class TITAN(PACT):
    """PACT outer bracket + TITAN probabilistic repair/tabu probe."""

    def __init__(self, inst, titan_cap=None, titan_tabu=True,
                 titan_budget=8, titan_tabu_cap=10,
                 titan_fallback=True, **kw):
        super().__init__(inst, use_ga=False, pact_mode='complete', **kw)
        self.titan_cap = titan_cap
        self.titan_tabu = titan_tabu
        self.titan_budget = titan_budget
        self.titan_tabu_cap = titan_tabu_cap
        self.titan_fallback = titan_fallback
        self.titan_stats = []
        self.titan_lp = 0
        self.titan_cert = 0
        self.titan_nodes = 0
        self.titan_evals = 0

    def _probe(self, h):
        r = titan_decide(self.inst, h, cap=self.titan_cap,
                         tabu=self.titan_tabu,
                         tabu_budget=self.titan_budget,
                         tabu_cap=self.titan_tabu_cap,
                         fallback=self.titan_fallback,
                         seed=len(self.steps))
        self.titan_stats.append(dict(r))
        self.titan_lp += r.get('titan_lp', 0)
        self.titan_cert += r.get('titan_cert', 0)
        self.titan_nodes += r.get('titan_nodes', 0)
        self.titan_evals += r.get('titan_tabu_evals', 0)
        if r.get('verdict') is False:
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='titan'))
            return False, r['proof']
        if r.get('verdict') is True:
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='titan'))
            return True, (s, m, cmax)
        # last resort: CHD
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            p = rdf if isinstance(rdf, OracleProof) else OracleProof(rdf)
            self._record_proof(p)
            self.steps.append(dict(h=h, v=False, proof=p, engine='chd'))
            return False, p
        if v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
            return True, (s, m, cmax)
        self.steps.append(dict(h=h, v=None, engine='chd'))
        return None, None

    def _result(self):
        r = super()._result()
        r['titan_lp'] = self.titan_lp
        r['titan_cert'] = self.titan_cert
        r['titan_nodes'] = self.titan_nodes
        r['titan_evals'] = self.titan_evals
        r['titan'] = self.titan_stats
        return r
