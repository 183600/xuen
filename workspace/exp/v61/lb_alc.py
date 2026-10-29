"""ALC anytime lower-bound profile on the holdout set."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v61', 'exp/v60', 'exp/v13']
from alc import ALC

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
            a = ALC(inst, h, cert_on=False)
            v, st = a.decide(nodecap=2000)
            calls += 1
            lp += st['lp_solves']
            nodes += st['nodes']
            if v is not False:
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
    json.dump(dict(rows=rows, total=tot), open('exp/v61/lb_alc_holdout.json', 'w'), indent=1)
    print(tot)
    for r in rows:
        if r['lb'] != r['opt']:
            print('miss', r)

if __name__ == '__main__':
    main()
