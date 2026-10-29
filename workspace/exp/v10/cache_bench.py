"""Small cache simulations for the COSA move engine and proof audit."""
import sys
import json
import random
from collections import OrderedDict

sys.path[:0] = ['exp/v10']


def veb_order(nodes):
    n = len(nodes)
    if n <= 1:
        return list(nodes)
    h = n.bit_length()
    ht = (h + 1) // 2
    top = nodes[:(1 << ht) - 1]
    rest = nodes[(1 << ht) - 1:]
    chunk = (1 << (h - ht)) - 1
    out = veb_order(top)
    for i in range(0, len(rest), chunk):
        out.extend(veb_order(rest[i:i + chunk]))
    return out


def preorder(n, root=0):
    out = []
    stack = [root]
    while stack:
        i = stack.pop()
        out.append(i)
        r = 2 * i + 1
        l = 2 * i + 2
        if l < n:
            stack.append(l)
        if r < n:
            stack.append(r)
    return out


def lru_misses(seq, cap, line=4):
    cache = OrderedDict()
    miss = 0
    for addr in seq:
        cl = addr // line
        if cl in cache:
            cache.move_to_end(cl)
        else:
            miss += 1
            cache[cl] = 1
            if len(cache) > cap:
                cache.popitem(last=False)
    return miss


def audit_bench(n=4095):
    seq = preorder(n)
    pos_bfs = list(range(n))
    pos_veb = {node: i for i, node in enumerate(veb_order(list(range(n))))}
    out = []
    for cap in (8, 32, 128, 512):
        mb = lru_misses([pos_bfs[i] for i in seq], cap)
        mv = lru_misses([pos_veb[i] for i in seq], cap)
        out.append(dict(cap_lines=cap, bfs=mb, veb=mv,
                        ratio=round(mv / max(1, mb), 3)))
    return out


def move_trace(n, moves, seed=0, p=0.7, flat=False):
    rng = random.Random(seed)
    seq = []
    touched = 0
    for _ in range(moves):
        if flat:
            seq.extend(rng.sample(range(n), 2))
            touched += 2
        else:
            lev = 0
            while rng.random() > p and lev < n.bit_length():
                lev += 1
            bs = min(n, 1 << lev)
            a = rng.randrange(max(1, n - bs + 1))
            seq.extend(range(a, a + bs))
            touched += bs
    return seq, touched


def move_bench(n=4096, moves=4000):
    out = []
    for cap in (8, 32, 128):
        for flat in (True, False):
            seq, touched = move_trace(n, moves, flat=flat)
            miss = lru_misses(seq, cap)
            out.append(dict(cap_lines=cap, mode='flat' if flat else 'dyadic',
                            accesses=len(seq), touched=touched,
                            miss=miss,
                            miss_per_access=round(miss / len(seq), 3)))
    return out


def main():
    res = dict(audit=audit_bench(), moves=move_bench())
    print(json.dumps(res, indent=1))
    json.dump(res, open('exp/v10/cache_bench.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
