"""v1.6 OMD differential tests.

(a) fully-eligible, base vs OMD, h in {OPT-1, OPT}
(b) heterogeneous eligibility, gate on (must not change) and forced OMD
    (documents that the rule is unsound without full eligibility)
(c) independent time-indexed brute force for n <= 7
"""
import sys, random, json, time
sys.path.insert(0, 'exp/v13'); sys.path.insert(0, 'exp/v14')
sys.path.insert(0, 'exp/v15'); sys.path.insert(0, 'exp/v16'); sys.path.insert(0, 'exp/v17')
import po, pace_omd
CFG = dict(mode='pot', nodecap=3_000_000, mint_on=True, mint_depth=0,
           packset_on=True, packset_depth=0, sop_on=False)


def gen(rng, n, m, ep, het=False):
    p = [rng.randint(2, 9) for _ in range(n)]
    pred = [[] for _ in range(n)]
    for j in range(n):
        for i in range(j):
            if rng.random() < ep:
                pred[j].append(i)
    elig = None
    if het:
        elig = []
        for i in range(n):
            while True:
                s = [k for k in range(m) if rng.random() < 0.75]
                if s:
                    break
            elig.append(s)
    return po.make_inst(p, m, pred, elig)


def full_elig(inst):
    return all(len(set(inst['elig'][i])) == inst['m'] for i in range(inst['n']))


def brute(inst, h):
    """Time-indexed brute force; valid because all-eligible (capacity only)."""
    n, m, p = inst['n'], inst['m'], inst['p']
    indeg = [len(inst['pred'][i]) for i in range(n)]
    st = [i for i in range(n) if indeg[i] == 0]
    topo = []
    while st:
        i = st.pop(0); topo.append(i)
        for j in inst['succ'][i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                st.append(j)
    starts = [0] * n
    cnt = [0] * (h + 1)

    def go(k):
        if k == n:
            return True
        i = topo[k]
        lo = max([starts[j] + p[j] for j in inst['pred'][i]] + [0])
        for s in range(lo, h - p[i] + 1):
            if all(cnt[t] < m for t in range(s, s + p[i])):
                for t in range(s, s + p[i]):
                    cnt[t] += 1
                starts[i] = s
                if go(k + 1):
                    return True
                for t in range(s, s + p[i]):
                    cnt[t] -= 1
        return False

    return go(0)


def opt_of(inst, hi=70):
    for h in range(max(inst['p']), hi):
        if brute(inst, h):
            return h
    return None


def main():
    rng = random.Random(777)
    out = {}
    # (a) all eligible
    tot = bad = 0
    t0 = time.time()
    for it in range(3000):
        n = rng.randint(5, 11); m = rng.choice([2, 3, 4])
        inst = gen(rng, n, m, rng.choice([0.15, 0.3, 0.45]))
        opt = None
        for h in range(max(inst['p']), 64):
            (ok, _), _ = pace_omd.decide(inst, h, omd=False, **CFG)
            if ok:
                opt = h; break
        if opt is None:
            continue
        for h in (opt - 1, opt):
            (a, _), _ = pace_omd.decide(inst, h, omd=False, **CFG)
            (b, _), _ = pace_omd.decide(inst, h, omd=True, **CFG)
            tot += 1
            if a != b:
                bad += 1
    out['all_eligible'] = dict(cases=tot, mismatch=bad, seconds=round(time.time() - t0, 1))
    # (b) heterogeneous: gated and forced
    tot2 = bad2 = forced_changed = 0
    t0 = time.time()
    for it in range(800):
        n = rng.randint(5, 9); m = rng.choice([2, 3])
        inst = gen(rng, n, m, rng.choice([0.2, 0.4]), het=True)
        opt = None
        for h in range(max(inst['p']), 60):
            (ok, _), _ = pace_omd.decide(inst, h, omd=False, **CFG)
            if ok:
                opt = h; break
        if opt is None:
            continue
        for h in (opt - 1, opt):
            (a, _), _ = pace_omd.decide(inst, h, omd=False, **CFG)
            (b, _), _ = pace_omd.decide(inst, h, omd=full_elig(inst), **CFG)
            (c, _), _ = pace_omd.decide(inst, h, omd=True, **CFG)
            tot2 += 1
            if a != b:
                bad2 += 1
            if a != c:
                forced_changed += 1
    out['heterogeneous'] = dict(cases=tot2, gated_mismatch=bad2,
                                forced_omd_mismatch=forced_changed,
                                seconds=round(time.time() - t0, 1))
    # (c) brute force
    tot3 = bad3 = 0
    t0 = time.time()
    for it in range(400):
        n = rng.randint(4, 7); m = rng.choice([2, 3])
        inst = gen(rng, n, m, rng.choice([0.2, 0.4, 0.6]))
        opt = opt_of(inst, 40)
        if opt is None:
            continue
        for h in (opt - 1, opt):
            b = brute(inst, h)
            (a, _), _ = pace_omd.decide(inst, h, omd=False, **CFG)
            (c, _), _ = pace_omd.decide(inst, h, omd=True, **CFG)
            tot3 += 1
            if not (a == b == c):
                bad3 += 1
    out['brute_force'] = dict(cases=tot3, mismatch=bad3, seconds=round(time.time() - t0, 1))
    json.dump(out, open('exp/v17/diff_omd.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
