import sys, json, time
sys.path[:0] = ['exp/pano']
import pano

BUDGETS = [4, 8, 12, 16, 24, 32]

def main():
    rows = list(pano.synthetic_corpus())
    out = []
    t0 = time.time()
    for n, (corpus, name, idx, inst, known) in enumerate(rows):
        for B in BUDGETS:
            r = pano.run_frontier(inst, known, name, idx, policy='geometric',
                                  max_probes=B, max_leaves=64, cap=0,
                                  init='chip', audit=False)
            out.append(dict(name=name, idx=idx, known=known, budget=B,
                            L=r.get('L'), U=r.get('U'), cost=r.get('cost'),
                            probes=r.get('probes'), exact=r.get('exact'),
                            certified=r.get('certified'), audit=r.get('audit'),
                            stop_reason=r.get('stop_reason')))
        if (n + 1) % 10 == 0:
            print(n + 1, '/', len(rows), 't', round(time.time() - t0, 1), flush=True)
    with open('exp/pano/frontier_budget.json', 'w') as f:
        json.dump(dict(budgets=BUDGETS, rows=out), f, indent=1)
    print('wrote', len(out), 'wall', round(time.time() - t0, 2))

if __name__ == '__main__':
    main()
