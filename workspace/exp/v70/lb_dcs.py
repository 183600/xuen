"""DCS anytime lower-bound profile on the holdout set."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v70', 'exp/v61', 'exp/v60', 'exp/v13']
from dcs import DCS

def main():
    cases = pickle.load(open('exp/v20/holdout_cases50.pkl', 'rb'))
    epc = {r['idx']: r for r in json.load(open('exp/v60/lb_holdout50.json'))}
    rows = []
    t00 = time.time()
    for idx, (inst, opt) in enumerate(cases):
        h = epc[idx]['epc_lb']
        lp = nodes = calls = 0
        t0 = time.time()
        reached = h
        while h < opt:
            a = DCS(inst, h, cert_on=False)
            root, _ = a.build_look(frozenset(), 2000, look_budget=8)
            calls += 1
            lp += a.lp_solves
            nodes += a.stats(root)['nodes']
            if root.status != 'no':
                break
            reached = h + 1
            h += 1
        rows.append(dict(idx=idx, opt=opt, epc_lb=epc[idx]['epc_lb'],
                         lb=reached, lp=lp, nodes=nodes, calls=calls,
                         t=time.time() - t0))
    tot = dict(n=len(rows), lb_opt=sum(r['lb'] == r['opt'] for r in rows),
               gap=sum(r['opt'] - r['lb'] for r in rows),
               lp=sum(r['lp'] for r in rows), nodes=sum(r['nodes'] for r in rows),
               calls=sum(r['calls'] for r in rows), t=time.time() - t00)
    json.dump(dict(rows=rows, total=tot), open('exp/v70/lb_dcs_holdout.json', 'w'), indent=1)
    print(tot)
    for r in rows:
        if r['lb'] != r['opt']:
            print('miss', r)

if __name__ == '__main__':
    main()
