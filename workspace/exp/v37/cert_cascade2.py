"""CERT-CASCADE/2: route small full instances to WOS probe + LP, large to LP + greedy + PACE."""
import sys, time
sys.path[:0] = ['exp/v37', 'exp/v35', 'exp/v30', 'exp/v29', 'exp/v13',
                'exp/v16', 'exp/v20', 'exp/v25']
import root_v31, cert_cascade


def decide(inst, h, stats=None):
    if stats is None:
        stats = {}
    full = all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))
    if full and inst['n'] <= 16:
        return root_v31.bb_solve(inst, h, stats=stats)
    return cert_cascade.decide(inst, h, stats=stats)
