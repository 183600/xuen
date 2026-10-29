"""v1.6 OMD: node reduction on random fully-eligible instances."""
import sys, random, json, time
sys.path.insert(0, 'exp/v13'); sys.path.insert(0, 'exp/v14')
sys.path.insert(0, 'exp/v15'); sys.path.insert(0, 'exp/v16'); sys.path.insert(0, 'exp/v17')
import po, pace_omd
CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=False)


def gen(rng, n, m, ep):
    p = [rng.randint(2, 9) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < ep:
                pred[j].append(i)
    return po.make_inst(p, m, pred, None)


def main():
    rng = random.Random(20261022)
    rows = []
    while len(rows) < 150:
        n = rng.randint(10, 14); m = rng.choice([2, 3])
        inst = gen(rng, n, m, rng.choice([0.15, 0.25, 0.35]))
        opt = None
        for h in range(max(inst['p']), 70):
            (ok, _), st = pace_omd.decide(inst, h, omd=False, **CFG)
            if ok:
                opt = h; break
        if opt is None:
            continue
        row = dict(n=n, m=m, opt=opt)
        for h in (opt - 1, opt):
            (a, _), sa = pace_omd.decide(inst, h, omd=False, **CFG)
            (b, _), sb = pace_omd.decide(inst, h, omd=True, **CFG)
            if a != b:
                print('MISMATCH', n, m, h, a, b); return
            row['base_%d' % h] = sa['nodes']; row['omd_%d' % h] = sb['nodes']
        rows.append(row)
    base = sum(r['base_%d' % (r['opt'] - 1)] for r in rows)
    omd = sum(r['omd_%d' % (r['opt'] - 1)] for r in rows)
    red = [r for r in rows if r['omd_%d' % (r['opt'] - 1)] < r['base_%d' % (r['opt'] - 1)]]
    ratio = [r['base_%d' % (r['opt'] - 1)] / max(1, r['omd_%d' % (r['opt'] - 1)]) for r in rows]
    out = dict(count=len(rows), base_nodes=base, omd_nodes=omd,
               total_ratio=round(base / omd, 3),
               reduced_instances=len(red),
               max_ratio=round(max(ratio), 2),
               geomean_ratio=round(__import__('math').exp(sum(__import__('math').log(x) for x in ratio) / len(ratio)), 3))
    json.dump(dict(rows=rows, summary=out), open('exp/v17/rand_omd.json', 'w'), indent=1)
    print(out)


if __name__ == '__main__':
    main()
