"""Pure-Python fallback for the machine-partition certificate (n <= 12)."""
INF = 255


def mpc_no(inst, h, est, q, budget=None):
    n, m, p = inst['n'], inst['m'], inst['p']
    if n > 12 or h > 63:
        return None
    d = [h - q[i] for i in range(n)]
    succ = [0] * n
    for i in range(n):
        for j in inst['succ'][i]:
            succ[i] |= 1 << j
    N = 1 << n
    f = bytearray([INF]) * N
    f[0] = 0
    for S in range(1, N):
        best = INF
        ss = S
        while ss:
            b = ss & -ss
            i = b.bit_length() - 1
            ss ^= b
            if succ[i] & S:
                continue
            prev = f[S ^ b]
            if prev == INF:
                continue
            st = prev if prev > est[i] else est[i]
            fin = st + p[i]
            if fin <= d[i] and fin < best:
                best = fin
        f[S] = best
    order = sorted(range(n), key=lambda i: (-p[i], d[i]))
    memo = {}
    calls = [0]

    def can(rem, k):
        if rem == 0:
            return True
        if k == 0:
            return False
        key = (rem, k)
        v = memo.get(key)
        if v is not None:
            return v
        calls[0] += 1
        if budget is not None and calls[0] > budget:
            raise TimeoutError
        i = next(j for j in order if (rem >> j) & 1)
        rest = rem ^ (1 << i)
        sub = rest
        while True:
            T = sub | (1 << i)
            if f[T] != INF:
                free = rem ^ T
                maximal = True
                ff = free
                while ff:
                    b = ff & -ff
                    j = b.bit_length() - 1
                    ff ^= b
                    if f[T | b] != INF:
                        maximal = False
                        break
                if maximal and can(free, k - 1):
                    memo[key] = True
                    return True
            if sub == 0:
                break
            sub = (sub - 1) & rest
        memo[key] = False
        return False

    try:
        ok = can(N - 1, m)
    except TimeoutError:
        return None
    return not ok
