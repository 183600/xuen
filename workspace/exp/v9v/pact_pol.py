"""v9.3 POL-PACT: bracket-state-aware branching policy on top of PACT-C.

The complete search is unchanged; only the split score is selected by the
outer bracket state.  Two resource-aware policies are used:

  late : weight on the earliest allowed start (schedule construction)
  tail : weight on the tail q (lower-bound / critical-path pressure)

Both use a 25% mass split instead of the median split.  The policy does
not change soundness or completeness; every returned NO proof is still a
BranchProof and every YES is still checked by check_schedule.
"""
import sys, time
sys.path[:0] = ['exp/v9v', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide
from sage import ga_schedule
from rdf import check_schedule

POLICIES = {
    'mass': ({}, 0.5),
    'late': ({'lo': 1}, 0.25),
    'tail': ({'q': 1}, 0.25),
    'frac': ({'frac': 1}, 0.25),
    'succ': ({'succ': 1}, 0.25),
}


class PolicyPACT(PACT):
    def __init__(self, inst, policy_bracket='late', policy_closing='tail',
                 **kw):
        super().__init__(inst, pact_depth=None, use_ga=False,
                         complete_fallback=True, **kw)
        self.policy_bracket = policy_bracket
        self.policy_closing = policy_closing
        self.policy_counts = {}

    def _policy_for(self, h):
        bracketing = (self.opt - self.lb > 1)
        name = self.policy_bracket if bracketing else self.policy_closing
        self.policy_counts[name] = self.policy_counts.get(name, 0) + 1
        return name

    def _probe(self, h):
        name = self._policy_for(h)
        w, split = POLICIES[name]
        r = pact_decide(self.inst, h, depthcap=None, nodecap=None,
                        policy={'weights': w, 'split': split})
        self.pact_calls += 1
        self.pact_lp += r['lp_solves']
        self.pact_cert_lp += r.get('cert_lp', 0)
        self.pact_nodes += r['nodes']
        self.stats['complete_fallback'] += 1
        if r['verdict'] is False:
            self.pact_no += 1
            self.stats['pact_no'] += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='complete', policy=name))
            return False, r['proof']
        if r['verdict'] is True:
            self.pact_yes += 1
            self.stats['pact_yes'] += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='complete',
                                   policy=name))
            return True, (s, m, cmax)
        # A complete search should not return UNKNOWN on this corpus.
        self.pact_unknown += 1
        self.stats['pact_unknown'] += 1
        self.stats['chd_fallback'] += 1
        v, st, rdf = self._decide(h)
        self.queries += 1
        self._absorb(st)
        self._record(h, v, st)
        if v is False:
            self.steps.append(dict(h=h, v=False, proof=rdf,
                                   engine='chd'))
        elif v is True:
            s, m = rdf.schedule, rdf.machine
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='chd'))
        else:
            self.steps.append(dict(h=h, v=None, engine='chd'))
        return v, rdf

    def _result(self):
        r = super()._result()
        r['policy_counts'] = dict(self.policy_counts)
        r['policy_bracket'] = self.policy_bracket
        r['policy_closing'] = self.policy_closing
        return r


def run_pol(inst, known, name, idx, **kw):
    t0 = time.time()
    co = PolicyPACT(inst, **kw)
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
