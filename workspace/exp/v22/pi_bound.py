"""Pi-bound: exact single-machine partition lower bound for PACE.

For a residual state (rem, est, q, h) and a task subset S, define f[S] as the
minimum completion time of one machine that processes exactly S, respecting
release est_i, deadline h-q_i and precedence inside S.  f is computed by the
last-task recurrence

    f[0] = 0
    f[S] = min_{i in sink(S)} max(f[S-{i}], est_i) + p_i
           subject to the completion being <= h-q_i.

The partition number beta is the minimum number of single-machine-feasible
parts covering rem.  Any feasible parallel schedule induces such a partition
(one part per machine), hence beta > m certifies infeasibility.

Complexity: O(n 2^n) for f, O(3^n) for beta; memory O(2^n).
"""
import os, sys, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
C_SRC = os.path.join(HERE, 'part_bound.c')
C_BIN = os.path.join(HERE, 'pi_bound')
sys.path.insert(0, os.path.join(HERE, '..', 'v13'))
import po

INF = 10 ** 9


def _ensure_bin():
    if os.path.exists(C_BIN):
        return C_BIN
    try:
        subprocess.run(['gcc', '-O3', '-o', C_BIN, C_SRC], check=True)
        return C_BIN
    except Exception:
        return None


def build_sub(inst, rem, est, q):
    """Restrict an instance to rem; return local arrays and index map."""
    idx = [i for i in range(inst['n']) if (rem >> i) & 1]
    pos = {v: j for j, v in enumerate(idx)}
    n = len(idx)
    p = [inst['p'][i] for i in idx]
    e = [est[i] for i in idx]
    qq = [q[i] for i in idx]
    succ = [0] * n
    for j, i in enumerate(idx):
        s = 0
        for t in inst['succ'][i]:
            if (rem >> t) & 1:
                s |= 1 << pos[t]
        succ[j] = s
    return idx, pos, n, p, e, qq, succ


def pi_beta(inst, h, rem=None, est=None, q=None, witness=None, use_c=True):
    """Return (beta, parts) for the residual state.

    parts is a minimum partition (list of masks in the *global* task indexing)
    when beta is finite; otherwise None.  witness is an optional global mask
    restricting the partition problem (a certificate subset).
    """
    n0 = inst['n']
    if rem is None:
        rem = inst['full']
    if est is None or q is None:
        est, q = po.heads_tails(inst, 0, [0] * n0)
    idx, pos, n, p, e, qq, succ = build_sub(inst, rem, est, q)
    if n == 0:
        return 0, []
    # local witness mask
    wl = (1 << n) - 1
    if witness is not None:
        wl = 0
        for j, i in enumerate(idx):
            if (witness >> i) & 1:
                wl |= 1 << j
        if wl == 0:
            wl = (1 << n) - 1
    if use_c:
        binp = _ensure_bin()
        if binp is not None:
            txt = [f"{n} {inst['m']} {h}"]
            txt.append(' '.join(map(str, p)))
            txt.append(' '.join(map(str, e)))
            txt.append(' '.join(map(str, qq)))
            txt.append(' '.join(map(str, succ)))
            data = '\n'.join(txt) + '\n'
            r = subprocess.run([binp, str(wl)], input=data, text=True,
                               capture_output=True)
            if r.returncode == 0 and r.stdout.strip():
                lines = r.stdout.strip().splitlines()
                beta = int(lines[0])
                parts = []
                if len(lines) > 1:
                    for tok in lines[1].split():
                        lm = int(tok)
                        gm = 0
                        for j in range(n):
                            if (lm >> j) & 1:
                                gm |= 1 << idx[j]
                        parts.append(gm)
                return beta, parts
    return _pi_beta_py(inst, h, rem, est, q, witness)


def _pi_beta_py(inst, h, rem, est, q, witness=None):
    n0 = inst['n']
    idx, pos, n, p, e, qq, succ = build_sub(inst, rem, est, q)
    if witness is not None:
        # restrict to witness, but keep global est/q
        keep = [j for j, i in enumerate(idx) if (witness >> i) & 1]
        idx = [idx[j] for j in keep]
        pos = {v: j for j, v in enumerate(idx)}
        n = len(idx)
        p = [inst['p'][i] for i in idx]
        e = [est[i] for i in idx]
        qq = [q[i] for i in idx]
        succ = [0] * n
        for j, i in enumerate(idx):
            s = 0
            for t in inst['succ'][i]:
                if (rem >> t) & 1 and t in pos:
                    s |= 1 << pos[t]
            succ[j] = s
    N = 1 << n
    f = [INF] * N
    f[0] = 0
    for S in range(1, N):
        best = INF
        T = S
        while T:
            lb = T & -T
            i = lb.bit_length() - 1
            T ^= lb
            if succ[i] & S:
                continue
            pm = S ^ lb
            if f[pm] >= INF:
                continue
            st = f[pm] if f[pm] > e[i] else e[i]
            en = st + p[i]
            if en > h - qq[i]:
                continue
            if en < best:
                best = en
        f[S] = best
    feas = [f[S] < INF for S in range(N)]
    g = [255] * N
    ch = [0] * N
    g[0] = 0
    for S in range(1, N):
        low = S & -S
        T = S
        best = 255
        arg = 0
        while T:
            if (T & low) and feas[T]:
                v = g[S ^ T] + 1
                if v < best:
                    best = v
                    arg = T
            T = (T - 1) & S
        g[S] = best
        ch[S] = arg
    beta = g[N - 1]
    parts = []
    S = N - 1
    while S:
        T = ch[S]
        gm = 0
        for j in range(n):
            if (T >> j) & 1:
                gm |= 1 << idx[j]
        parts.append(gm)
        S ^= T
    return beta, parts


def check_partition(inst, h, rem, est, q, parts):
    """Independent O(3^n)-free checker: each part is 1-machine feasible."""
    cover = 0
    for S in parts:
        if S & ~rem:
            return False
        if cover & S:
            return False
        cover |= S
        # independent last-task DP on S only
        idx = [i for i in range(inst['n']) if (S >> i) & 1]
        k = len(idx)
        pos = {v: j for j, v in enumerate(idx)}
        N = 1 << k
        f = [INF] * N
        f[0] = 0
        succ = [0] * k
        for j, i in enumerate(idx):
            for t in inst['succ'][i]:
                if (S >> t) & 1:
                    succ[j] |= 1 << pos[t]
        for M in range(1, N):
            best = INF
            T = M
            while T:
                lb = T & -T
                j = lb.bit_length() - 1
                T ^= lb
                if succ[j] & M:
                    continue
                pm = M ^ lb
                if f[pm] >= INF:
                    continue
                st = max(f[pm], est[idx[j]])
                en = st + inst['p'][idx[j]]
                if en > h - q[idx[j]]:
                    continue
                best = min(best, en)
            f[M] = best
        if f[N - 1] >= INF:
            return False
    return cover == rem


def pi_profile(inst, h, rem=None, est=None, q=None):
    """Return (f, idx) where f[local mask] is the single-machine profile."""
    n0 = inst['n']
    if rem is None:
        rem = inst['full']
    if est is None or q is None:
        est, q = po.heads_tails(inst, 0, [0] * n0)
    idx, pos, n, p, e, qq, succ = build_sub(inst, rem, est, q)
    binp = _ensure_bin()
    if binp is None:
        return None, idx
    txt = [f"{n} {inst['m']} {h}"]
    txt.append(' '.join(map(str, p)))
    txt.append(' '.join(map(str, e)))
    txt.append(' '.join(map(str, qq)))
    txt.append(' '.join(map(str, succ)))
    data = '\n'.join(txt) + '\n'
    r = subprocess.run([binp, '-', 'dump'], input=data, text=True,
                       capture_output=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None, idx
    lines = r.stdout.strip().splitlines()
    f = [int(x) for x in lines[2].split()] if len(lines) > 2 else []
    return f, idx
