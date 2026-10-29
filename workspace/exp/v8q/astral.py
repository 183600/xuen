"""v9.1 ASTRAL: preconditioned LP-guided A*/DFS certificate search.

ASTRAL keeps PACT's LP bracket and proof algebra, and replaces the
complete closing probe by a guided depth-first search over interval
states.  Two ingredients are new:

  * a Hall-type energy precondition: if some machine subset cannot carry
    the jobs that are eligible only inside it, NO(h) is proved without
    solving an LP (certificate replayed by scale.verify_prep);
  * an LP-guide branch order: at a split the side carrying at least
    `guide_conf` of the LP mass goes first; otherwise PACT's left-first
    order is kept.  The guide only changes order, never prunes a state.

The search is still complete: if a precondition fails or a node is not
decided, it falls back to the complete PACT decision procedure.
"""
import sys
import time

sys.path[:0] = ['exp/v8q', 'exp/v8o', 'exp/v8i', 'exp/v8h', 'exp/v8f',
                'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c',
                'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71',
                'exp/v61', 'exp/v60', 'exp/v13']

from pact import PACT, pact_decide, run_pact
from pns import pns_decide


class ASTRAL(PACT):
    def __init__(self, inst, guide_conf=0.8, fallback=True, **kw):
        super().__init__(inst, **kw)
        self.guide_conf = guide_conf
        self.astral_fallback = fallback
        self.astral_lp = 0
        self.astral_cert_lp = 0
        self.astral_nodes = 0
        self.astral_calls = 0
        self.astral_no = 0
        self.astral_yes = 0
        self.astral_unknown = 0
        self.astral_pre_energy = 0
        self.astral_time = 0.0

    def _probe(self, h):
        if self.pact_mode == 'closing' and self.opt - self.lb > 1:
            return super()._probe(h)
        if self.pact_mode != 'closing':
            return super()._probe(h)
        t0 = time.time()
        r = pns_decide(self.inst, h, mode='guide_dfs', nodecap=None,
                       policy={'guide_conf': self.guide_conf})
        self.astral_time += time.time() - t0
        self.astral_calls += 1
        self.astral_lp += r['lp_solves']
        self.astral_cert_lp += r.get('cert_lp', 0)
        self.astral_nodes += r['nodes']
        self.astral_pre_energy += r.get('pre_energy', 0)
        if r['verdict'] is False:
            self.astral_no += 1
            self._record_proof(r['proof'])
            self.steps.append(dict(h=h, v=False, proof=r['proof'],
                                   engine='astral', pre_energy=r.get(
                                       'pre_energy', 0)))
            return False, r['proof']
        if r['verdict'] is True:
            self.astral_yes += 1
            s, m = r['schedule'], r['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='astral'))
            return True, (s, m, cmax)
        self.astral_unknown += 1
        if not self.astral_fallback:
            self.steps.append(dict(h=h, v=None, engine='astral'))
            return None, None
        t0 = time.time()
        q = pact_decide(self.inst, h, depthcap=None, nodecap=None)
        self.astral_time += time.time() - t0
        self.pact_lp += q['lp_solves']
        self.pact_cert_lp += q.get('cert_lp', 0)
        self.pact_nodes += q['nodes']
        self.stats['complete_fallback'] += 1
        if q['verdict'] is False:
            self._record_proof(q['proof'])
            self.steps.append(dict(h=h, v=False, proof=q['proof'],
                                   engine='fallback'))
            return False, q['proof']
        if q['verdict'] is True:
            s, m = q['schedule'], q['machine']
            cmax = max(s[i] + self.inst['p'][i]
                       for i in range(self.inst['n']))
            self.steps.append(dict(h=h, v=True, schedule=s, machine=m,
                                   cmax=cmax, engine='fallback'))
            return True, (s, m, cmax)
        self.steps.append(dict(h=h, v=None, engine='fallback'))
        return None, None


def run_astral(inst, known, name, idx, **kw):
    t0 = time.time()
    co = ASTRAL(inst, **kw)
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
    r['astral_lp'] = getattr(co, 'astral_lp', 0)
    r['astral_cert_lp'] = getattr(co, 'astral_cert_lp', 0)
    r['astral_nodes'] = getattr(co, 'astral_nodes', 0)
    r['astral_calls'] = getattr(co, 'astral_calls', 0)
    r['astral_no'] = getattr(co, 'astral_no', 0)
    r['astral_yes'] = getattr(co, 'astral_yes', 0)
    r['astral_unknown'] = getattr(co, 'astral_unknown', 0)
    r['astral_pre_energy'] = getattr(co, 'astral_pre_energy', 0)
    r['astral_time'] = round(getattr(co, 'astral_time', 0.0), 4)
    r['ok'] = bool(r['certified'] and r['opt'] == known
                   and r['audit'] and r['proof'] and r['total_audit']
                   and r['cert_h'] == known - 1)
    return r
