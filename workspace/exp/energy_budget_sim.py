"""Toy check for UIP-18 EBW: does score-weighted, option-aware energy allocation
beat uniform/direct-weight allocation under a fixed per-episode energy budget?

The success envelope p_i(b) is deliberately *inverted-U*: too little energy
cannot finish the step, too much energy knocks things over / triggers the human
disturbance.  This is the core hypothesis (H1) of the energy round; the numbers
below are a design sanity check, NOT real-robot evidence.
"""
import json
import numpy as np

# representative scored-step structures from tasks_v2/<slug>/info.json
TASKS = {
    "T01_HangCup":       [50, 50],
    "T04_FruitSorting":  [30, 30, 40],
    "T12_Unlock":        [30, 30, 40],
    "T09_Toolbox":       [25, 25, 25, 25],
    "T16_FoldTowel":     [20, 20, 20, 20, 20],
}


def p_step(b):
    """Success probability of one scored step vs normalised energy b.

    b = 1.0 means 'energy used by the average successful demonstration'.
    Peak is ~0.93 around b~0.95, then overshoot/contact damage pulls it down.
    """
    rise = 1.0 / (1.0 + np.exp(-(b - 0.55) / 0.12))
    over = 0.38 / (1.0 + np.exp(-(b - 1.45) / 0.15))
    return np.clip(0.99 * rise * (1.0 - over), 0.0, 0.99)


def eval_alloc(alloc, w):
    """Expected success and expected step score for a fixed allocation."""
    s, v, reach = 1.0, 0.0, 1.0
    for b, wi in zip(alloc, w):
        p = p_step(b)
        reach *= p
        v += wi * reach
        s *= p
    return s, v


def uniform_alloc(w, B):
    n = len(w)
    return np.minimum(np.full(n, B / n), 2.0)


def weight_alloc(w, B):
    w = np.asarray(w, float)
    return np.minimum(B * w / w.sum(), 2.0)


def demo_alloc(w, B):
    n = len(w)
    a = np.minimum(np.full(n, B / n), 2.0)
    return a


def dp_alloc(w, B, grid=0.02, M=1e6):
    """Exact lexicographic-ish DP. J(i,b)=max_b_i p_i(b_i)*(w_i+J(i+1,b-b_i)),
    terminal J(n+1,.)=M so the all-success bonus is counted once.
    n<=5, so this is trivially cheap.
    """
    n = len(w)
    levels = np.arange(0.0, B + 1e-9, grid)
    nb = len(levels)
    J = np.full((n + 1, nb), M)
    choice = np.zeros((n, nb), dtype=int)
    for i in range(n - 1, -1, -1):
        for j, b in enumerate(levels):
            best, best_k = -1.0, 0
            for k, bi in enumerate(levels):
                if bi > b + 1e-12:
                    break
                val = p_step(bi) * (w[i] + J[i + 1, np.searchsorted(levels, b - bi)])
                if val > best:
                    best, best_k = val, k
            J[i, j] = best
            choice[i, j] = best_k
    alloc, j = [], nb - 1
    for i in range(n):
        k = choice[i, j]
        alloc.append(levels[k])
        j = np.searchsorted(levels, levels[j] - levels[k])
    return np.array(alloc)


def run():
    rows = []
    for name, w in TASKS.items():
        w = np.array(w, float)
        n = len(w)
        for mult in (0.5, 0.75, 1.0, 1.25, 1.5):
            B = mult * n
            res = {}
            for tag, fn in (("uniform", uniform_alloc), ("weight", weight_alloc),
                            ("demo", demo_alloc)):
                a = fn(w, B)
                s, v = eval_alloc(a, w)
                res[tag] = {"E": float(a.sum()), "S": round(float(s), 4),
                            "V": round(float(v), 3), "alloc": np.round(a, 3).tolist()}
            a = dp_alloc(w, B)
            s, v = eval_alloc(a, w)
            res["dp"] = {"E": float(a.sum()), "S": round(float(s), 4),
                         "V": round(float(v), 3), "alloc": np.round(a, 3).tolist()}
            rows.append({"task": name, "mult": mult, "B": B, **res})
            print(f"{name:20s} B={B:4.1f} "
                  f"U:{res['uniform']['S']:.3f}/{res['uniform']['V']:.1f} "
                  f"W:{res['weight']['S']:.3f}/{res['weight']['V']:.1f} "
                  f"D:{res['dp']['S']:.3f}/{res['dp']['V']:.1f} "
                  f"alloc={res['dp']['alloc']}")
    # aggregate deltas vs uniform
    print("\nAggregate (mean over 5 tasks): delta S / delta V vs uniform")
    for mult in (0.5, 0.75, 1.0, 1.25, 1.5):
        sub = [r for r in rows if r["mult"] == mult]
        ds = np.mean([r["dp"]["S"] - r["uniform"]["S"] for r in sub])
        dv = np.mean([r["dp"]["V"] - r["uniform"]["V"] for r in sub])
        dw = np.mean([r["dp"]["V"] - r["weight"]["V"] for r in sub])
        print(f"B/n={mult:4.2f}  dS={ds:+.4f}  dV(uniform)={dv:+.2f}  dV(weight)={dw:+.2f}")
    json.dump(rows, open("energy_budget_sim.json", "w"), indent=1)


if __name__ == "__main__":
    run()
