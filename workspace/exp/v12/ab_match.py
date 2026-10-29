"""AB-MATCH: alpha-beta budgeted matching-guided branching.

The fixed-h decision procedure is `pact_decide` from exp/v8o/pact.py.
AB-MATCH keeps the exact tree/proof layer and changes only the branching
oracle:

  MATCH-SPLIT
      Among jobs with a fractional LP support, pick the job with the
      largest fractional start-time spread (tie: more fractional columns,
      then larger p*frac).  Split at the median of its currently allowed
      start times.  This is a minimax cut: it targets the most ambiguous
      job-time matching and balances the two children in time, not in
      fractional mass.

  AB-PORTFOLIO
      Run the old mass-median tree first with a tiny node budget kappa.
      If it returns a verdict, use it (alpha probe).  Otherwise discard
      the partial tree and rerun with MATCH-SPLIT (beta search).  The
      wasted work is at most kappa LP solves per hard probe.

Both passes are exact invocations of pact_decide, so every returned
verdict carries a checked BranchProof or a checked schedule.  The ICF
partial-certificate invariant is unchanged.
"""
from pact import pact_decide

DEFAULT_CAP = 5
MATCH_POLICY = {'split_mode': 'time', 'weights': {'spread': 1.0}}


def _merge(policy, mode):
    p = dict(policy or {})
    p['split_mode'] = mode
    if mode == 'time':
        w = dict(p.get('weights') or {})
        w.setdefault('spread', 1.0)
        p['weights'] = w
    return p


def ab_decide(inst, h, depthcap=None, nodecap=None, policy=None,
              cap=DEFAULT_CAP, **kw):
    """Drop-in replacement for pact_decide with the AB-MATCH portfolio.

    The returned dict has the pact_decide fields plus:
      portfolio : 1 if the cheap mass pass decided, 2 if MATCH-SPLIT ran
      wasted_lp : LP solves spent in the discarded cheap pass
    The reported lp_solves/nodes/cert_lp are the *total* cost, including
    the discarded pass, so benchmarks charge the portfolio honestly.
    """
    r1 = pact_decide(
        inst, h, depthcap=depthcap, nodecap=cap,
        policy=_merge(policy, 'mass'), **kw)
    if r1.get('verdict') is not None:
        r1['portfolio'] = 1
        r1['wasted_lp'] = 0
        return r1

    r2 = pact_decide(
        inst, h, depthcap=depthcap, nodecap=nodecap,
        policy=_merge(policy, 'time'), **kw)
    r2['portfolio'] = 2
    r2['wasted_lp'] = r1.get('lp_solves', 0)
    for k in ('lp_solves', 'nodes', 'cert_lp'):
        r2[k] = r1.get(k, 0) + r2.get(k, 0)
    r2['t'] = r1.get('t', 0.0) + r2.get('t', 0.0)
    return r2


def match_decide(inst, h, **kw):
    """Pure MATCH-SPLIT, used as an ablation."""
    kw.pop('policy', None)
    return pact_decide(inst, h, policy=MATCH_POLICY, **kw)
