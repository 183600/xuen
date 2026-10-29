"""v4.0 three negative probes: dominance, cores, direction."""
import sys, json, pickle, math, statistics
sys.path[:0] = ['exp/v34', 'exp/v30', 'exp/v13']
import po, wos
from bench_wos import load


def rev(inst):
    n = inst['n']; z = dict(inst)
    z['pred'] = [list(inst['succ'][i]) for i in range(n)]
    z['succ'] = [list(inst['pred'][i]) for i in range(n)]
    return z


def dominance():
    d = pickle.load(open('exp/v32/states_holdout.pkl', 'rb'))

    def decode(inst, h, keys):
        n, m = inst['n'], inst['m']
        cw = max(1, m.bit_length())
        est, q = po.heads_tails(inst, 0, [0] * n)
        rw = max(1, max([h] + list(est)).bit_length())
        kshift = cw * h; mshift = kshift + rw * n
        out = []
        for k in keys:
            cp = k & ((1 << kshift) - 1)
            rp = (k >> kshift) & ((1 << (rw * n)) - 1)
            mask = k >> mshift
            out.append((mask, [(cp >> (cw * t)) & ((1 << cw) - 1) for t in range(h)],
                        [(rp >> (rw * i)) & ((1 << rw) - 1) for i in range(n)]))
        return out

    def dom(a, b):  # a dominates b
        return all(x >= y for x, y in zip(a[1], b[1])) and \
               all(x <= y for x, y in zip(a[2], b[2]))

    tot = domin = masks = 0
    fronts = []
    for inst, h, keys in d:
        by = {}
        for s in decode(inst, h, keys):
            by.setdefault(s[0], []).append(s)
        for mask, lst in by.items():
            masks += 1
            front = []
            for s in lst:
                if any(dom(f, s) for f in front):
                    domin += 1; continue
                front = [f for f in front if not dom(s, f)]
                front.append(s)
            tot += len(lst); fronts.append(len(front))
    return dict(states=tot, dominated=domin, pct=round(100 * domin / tot, 1),
                masks=masks, avg_front=round(sum(fronts) / len(fronts), 2),
                max_front=max(fronts))


def sub_est_q(inst, rem):
    n, p, pred, succ = inst['n'], inst['p'], inst['pred'], inst['succ']
    est = [0] * n
    for i in range(n):
        if (rem >> i) & 1:
            est[i] = max([est[j] + p[j] for j in pred[i] if (rem >> j) & 1] + [0])
    q = [0] * n
    for i in range(n - 1, -1, -1):
        if (rem >> i) & 1:
            q[i] = max([p[j] + q[j] for j in succ[i] if (rem >> j) & 1] + [0])
    return est, q


def cores():
    cases = load('exp/v20/holdout_cases50.pkl')
    sizes = []
    for inst, opt in cases:
        h = opt - 1; rem = inst['full']
        for i in range(inst['n']):
            if (rem >> i) & 1:
                cand = rem & ~(1 << i)
                est, q = sub_est_q(inst, cand)
                ok, _ = wos.sgs_solve(inst, h, rem=cand, est=est, q=q,
                                      nodecap=300000, force=True)
                if ok is False:
                    rem = cand
        sizes.append(bin(rem).count('1'))
    ns = [inst['n'] for inst, _ in cases]
    return dict(sizes=sizes, diff=[n - k for n, k in zip(ns, sizes)],
                full=sum(1 for n, k in zip(ns, sizes) if n == k))


def direction():
    cases = load('exp/v20/holdout_cases50.pkl')
    rows = []
    for inst, opt in cases:
        n = inst['n']; h = opt - 1
        est, q = po.heads_tails(inst, 0, [0] * n)
        sf = {}; wos.sgs_solve(inst, h, est=est, q=q, force=True, nodecap=300000, stats=sf)
        sb = {}; wos.sgs_solve(rev(inst), h, est=q, q=est, force=True, nodecap=300000, stats=sb)
        rows.append(dict(f=sf['nodes'], b=sb['nodes'], sump=sum(inst['p']),
                         se=sum(est), sq=sum(q), me=max(est), mq=max(q), n=n))

    def corr(x, y):
        mx = sum(x) / len(x); my = sum(y) / len(y)
        sx = math.sqrt(sum((a - mx) ** 2 for a in x))
        sy = math.sqrt(sum((a - my) ** 2 for a in y))
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy + 1e-12)

    ratio = [math.log(r['b'] / r['f']) for r in rows]
    cs = {k: round(corr([r[k] for r in rows], ratio), 3)
          for k in ['sump', 'se', 'sq', 'me', 'mq', 'n']}
    cs['se-sq'] = round(corr([r['se'] - r['sq'] for r in rows], ratio), 3)
    cs['me-mq'] = round(corr([r['me'] - r['mq'] for r in rows], ratio), 3)
    probe = {}
    for C in [50, 100, 300, 800, 1200]:
        probe[C] = dict(b_then_f=sum(r['b'] if r['b'] <= C else C + r['f'] for r in rows),
                        f_then_b=sum(r['f'] if r['f'] <= C else C + r['b'] for r in rows))
    return dict(fwd=sum(r['f'] for r in rows), bwd=sum(r['b'] for r in rows),
                bwd_wins=sum(1 for r in rows if r['b'] < r['f']),
                ratio_min=round(min(r['b'] / r['f'] for r in rows), 3),
                ratio_max=round(max(r['b'] / r['f'] for r in rows), 3),
                corr=cs, probe=probe)


if __name__ == '__main__':
    out = dict(dominance=dominance(), cores=cores(), direction=direction())
    print(json.dumps(out, indent=1))
    json.dump(out, open('exp/v34/res_neg.json', 'w'), indent=1)
