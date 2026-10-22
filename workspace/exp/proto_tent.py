"""Prototype: mandatory-piece (tent) packing certificate vs v0.5 window packing."""
import sys, random, time, json, pickle
sys.path.insert(0, '.')
import exp_da as E

def tent_items(inst, S, A, c, H, a, b, est, q):
    n, p = inst['n'], inst['p']
    items = []
    for i in range(n):
        if (S >> i) & 1:
            continue
        u = a - est[i]
        if u < 0:
            u = 0
        v = H - q[i] - b
        if v < 0:
            v = 0
        e = p[i] - u - v
        if e > 0:
            items.append(e)
    return items

def tent_infeasible(inst, S, A, c, H, a, b, est, q):
    caps = [max(0, b - max(a, Ak)) for Ak in A]
    items = tent_items(inst, S, A, c, H, a, b, est, q)
    if not items:
        return False
    return not E.packable(items, caps)

def tent_windows(inst, S, A, c, H, est, q, full=False):
    n, p = inst['n'], inst['p']
    R = [i for i in range(n) if not ((S >> i) & 1)]
    avals = {0}
    bvals = {H}
    for i in R:
        avals.add(est[i]); avals.add(est[i] + p[i])
        bvals.add(H - q[i]); bvals.add(H - q[i] - p[i])
        bvals.add(est[i] + p[i])
    for k in range(len(A)):
        avals.add(A[k]); bvals.add(A[k])
    avals = sorted(a for a in avals if 0 <= a < H)
    bvals = sorted(b for b in bvals if 0 < b <= H)
    out = []
    for a in avals:
        for b in bvals:
            if b > a:
                out.append((a, b))
    return out

def tent_scan(inst, S, A, c, H, est, q, windows=None):
    if windows is None:
        windows = tent_windows(inst, S, A, c, H, est, q)
    best = None
    for (a, b) in windows:
        caps = [max(0, b - max(a, Ak)) for Ak in A]
        items = tent_items(inst, S, A, c, H, a, b, est, q)
        if items and not E.packable(items, caps):
            # record margin: total item - total cap, and window
            margin = sum(items) - sum(caps)
            rec = (margin, a, b, len(items))
            if best is None or rec > best:
                best = rec
    return best

def old_scan(inst, S, A, c, H, est, q, wins=None):
    if wins is None:
        wins, _, _ = E.make_windows(inst, S, A, c, H + 1)
    for (a, b, ub) in wins:
        if E.window_infeasible_at(inst, S, A, c, H, a, b, est, q):
            return (a, b)
    return None

def main():
    rng = random.Random(2026)
    pool = pickle.load(open('pool30.pkl', 'rb'))
    rows = []
    t0 = time.time()
    for k, (inst, opt, nd) in enumerate(pool[:12]):
        # sample random prefix states, evaluate at H = opt-1 and H = U-1
        for trial in range(6):
            S, A, c = E.random_prefix(inst, rng, rng.choice([0.3, 0.45, 0.6]))
            est, q = E.heads_tails(inst, S, c)
            U = E.guide(inst, S, A, c)
            L0 = E.lower_L0(inst, S, A, c)
            if L0 >= U:
                continue
            for H, tag in ((opt - 1, 'opt-1'), (U - 1, 'U-1')):
                if H < L0:
                    continue
                t = time.time()
                old = old_scan(inst, S, A, c, H, est, q)
                to = time.time() - t
                t = time.time()
                # use windows fixed at H (for point test)
                new = tent_scan(inst, S, A, c, H, est, q, tent_windows(inst, S, A, c, H, est, q))
                tn = time.time() - t
                rows.append(dict(k=k, trial=trial, tag=tag, H=H, L0=L0, U=U,
                                 old=bool(old), new=bool(new),
                                 old_t=round(to,5), new_t=round(tn,5),
                                 margin=(new[0] if new else None),
                                 nw=len(tent_windows(inst, S, A, c, H, est, q))))
        print('inst', k, 'done', len(rows), flush=True)
    json.dump(rows, open('proto_tent.json','w'), indent=1)
    print('elapsed', round(time.time()-t0,2))
    for tag in ('opt-1','U-1'):
        rr=[r for r in rows if r['tag']==tag]
        print(tag, 'n', len(rr),
              'old', sum(r['old'] for r in rr),
              'new', sum(r['new'] for r in rr),
              'new_only', sum(r['new'] and not r['old'] for r in rr),
              'old_only', sum(r['old'] and not r['new'] for r in rr),
              'both', sum(r['old'] and r['new'] for r in rr),
              'avg_new_ms', round(1000*sum(r['new_t'] for r in rr)/max(1,len(rr)),3),
              'avg_old_ms', round(1000*sum(r['old_t'] for r in rr)/max(1,len(rr)),3))

if __name__ == '__main__':
    main()
