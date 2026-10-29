"""Final PRISM runs: selected policy, closure ablation, no-GA ablation."""
import sys
sys.path[:0] = ['exp/v8j', 'exp/v8i', 'exp/v8h', 'exp/v8f', 'exp/v8e',
                'exp/v8g', 'exp/v8c', 'exp/v9d', 'exp/v9c', 'exp/v9b',
                'exp/v8a', 'exp/v76', 'exp/v72', 'exp/v71', 'exp/v61',
                'exp/v60', 'exp/v13']
from bench_prism import run_all

SEL = dict(heur='frac', split=0.5, side='left', closure=True)
NOC = dict(heur='frac', split=0.5, side='left', closure=False)
LOW = dict(heur='frac', split=0.25, side='left', closure=True)

if __name__ == '__main__':
    run_all('selected', branch_policy=SEL)
    run_all('selected_noclose', branch_policy=NOC)
    run_all('selected_low25', branch_policy=LOW)
    run_all('selected_no_ga', branch_policy=SEL, use_ga=False)
