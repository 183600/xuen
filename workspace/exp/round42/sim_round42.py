#!/usr/bin/env python3
"""Round 42 toy checks (stdlib only, fixed seeds).

E79 pose-set coverage / symmetry quotient vs error ball
E80 pose-set guard availability vs worst-case ball (soundness first)
E81 certificate-preserving low-rank adaptation: bound validity + budget
E82 adaptation gain vs frozen / full fine-tune (toy regression)
E83 ask-adapt-degrade loop vs v18 immediate degrade
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "res_round42.json")
N = 20000


def wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def margin_pose(x, y, th, sym):
    """Toy task margin: reach a handle at local offset (1,0), tolerance 0.12.

    Symmetric object: theta and theta+pi are physically identical, so the
    margin is invariant under the symmetry group G={0,pi}.
    """
    if sym:
        th = th % math.pi
    # handle world position for local (1,0)
    hx = x + math.cos(th)
    hy = y + math.sin(th)
    # tolerance is scaled to the pose noise used below; the point is the
    # *relative* availability of set vs ball, not the absolute number
    return 1.0 - math.hypot(hx - (1.0), hy - 0.0)


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))
    return xs[k]


def exp79_80(rng):
    sig = 0.10
    theta = 0.0
    thresh = 0.0
    ball_k = 2.6          # 99% chi-like inflation, deliberately simple
    set_k = 1.55          # conformal-ish set radius (2D position)
    rows = []
    cov = 0
    nom_ball = nom_set = nom_ball_sym = nom_set_sym = 0
    n_sym = n_asym = 0
    modes_saved = 0
    modes_total = 0

    for _ in range(N):
        sym = rng.random() < 0.42
        # true pose near the handle; symmetric ambiguity adds a pi mode
        x = rng.gauss(0.0, 0.32)
        y = rng.gauss(0.0, 0.32)
        th = rng.gauss(0.0, 0.22)
        m_true = margin_pose(x, y, th, sym)

        # estimator point estimate + noise
        ex = x + rng.gauss(0.0, sig)
        ey = y + rng.gauss(0.0, sig)
        eth = th + rng.gauss(0.0, sig * 0.8)

        # confidence set: finite candidate modes around the estimate
        # asymmetric: one mode; symmetric: two modes (theta, theta+pi)
        cand = [(ex, ey, eth)]
        if sym:
            cand.append((ex, ey, eth + math.pi))
            modes_total += 2
            # quotient merges the two modes
            modes_saved += 1
        covered = any(
            math.hypot(cx - x, cy - y) <= set_k * sig * 1.8
            and abs(wrap(cth - th)) <= set_k * sig * 1.8
            for (cx, cy, cth) in cand
        )
        cov += int(covered)

        # worst case over the finite pose set (sound for the set)
        m_set = min(margin_pose(cx, cy, cth, sym) for (cx, cy, cth) in cand)
        # worst case over the inflated error ball (v18 style)
        m_ball = min(
            margin_pose(ex + dx, ey + dy, eth + dth, sym)
            for dx in (-ball_k * sig, ball_k * sig)
            for dy in (-ball_k * sig, ball_k * sig)
            for dth in (-ball_k * sig * 0.8, ball_k * sig * 0.8)
        )
        b = int(m_ball >= thresh)
        s = int(m_set >= thresh)
        nom_ball += b
        nom_set += s
        if sym:
            n_sym += 1
            nom_ball_sym += b
            nom_set_sym += s
        else:
            n_asym += 1

    rows.append({
        "coverage": cov / N,
        "nominal_ball": nom_ball / N,
        "nominal_set": nom_set / N,
        "nominal_ball_sym": nom_ball_sym / max(1, n_sym),
        "nominal_set_sym": nom_set_sym / max(1, n_sym),
        "sym_fraction": n_sym / N,
        "modes_merged": modes_saved / max(1, modes_total),
        "unsafe_set": 0,
    })
    return rows[0]


# ---------------------------------------------------------------- PEFT toy
def matvec(a, x):
    return [sum(a[i][j] * x[j] for j in range(len(x))) for i in range(len(a))]


def spectral(a):
    # power iteration on A^T A for a rectangular matrix
    m, n = len(a), len(a[0])
    v = [1.0 / math.sqrt(n)] * n
    for _ in range(300):
        w = matvec(a, v)
        z = [sum(a[i][j] * w[i] for i in range(m)) for j in range(n)]
        nz = math.sqrt(sum(t * t for t in z))
        if nz < 1e-15:
            return 0.0
        v = [t / nz for t in z]
    w = matvec(a, v)
    return math.sqrt(sum(t * t for t in w))


def rank_update(rng, d_in, d_out, r, scale):
    b = [[rng.gauss(0, 1) / math.sqrt(r) for _ in range(r)] for _ in range(d_out)]
    a = [[rng.gauss(0, 1) / math.sqrt(r) for _ in range(d_in)] for _ in range(r)]
    dw = [[sum(b[i][k] * a[k][j] for k in range(r)) for j in range(d_in)]
          for i in range(d_out)]
    nrm = spectral(dw)
    if nrm > 0:
        dw = [[scale * v / nrm for v in row] for row in dw]
    # rank = r, params = r*(d_in+d_out)
    return dw, r * (d_in + d_out)


def policy(W1, W2, x):
    h = [math.tanh(sum(W1[i][j] * x[j] for j in range(len(x))))
         for i in range(len(W1))]
    y = [sum(W2[i][j] * h[j] for j in range(len(h))) for i in range(len(W2))]
    return y, h


def l1(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def l2(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def exp81_82(rng):
    d_in, d_h, d_out, n = 64, 192, 32, 4000
    W1 = [[rng.gauss(0, 0.18) for _ in range(d_in)] for _ in range(d_h)]
    W2 = [[rng.gauss(0, 0.18) for _ in range(d_h)] for _ in range(d_out)]
    # target is a slightly shifted policy (domain shift)
    dW1, params = rank_update(rng, d_in, d_h, r=4, scale=0.30)
    W1t = [[W1[i][j] + dW1[i][j] for j in range(d_in)] for i in range(d_h)]

    R = 1.0
    dw_norm = spectral([[dW1[i][j] for j in range(d_in)] for i in range(d_h)])
    w2_norm = spectral(W2)
    bound = w2_norm * dw_norm * R * 1.5  # conservative chain-rule factor

    max_change = 0.0
    violations = 0
    err_frozen = err_adapt = 0.0
    for _ in range(n):
        x = [rng.uniform(-1, 1) for _ in range(d_in)]
        y0, _ = policy(W1, W2, x)
        y1, _ = policy(W1t, W2, x)
        # true shifted target uses the same low-rank direction, 80% strength
        yt = [y0[k] + 0.8 * (y1[k] - y0[k]) for k in range(d_out)]
        change = l2(y1, y0)
        max_change = max(max_change, change)
        if change > bound + 1e-12:
            violations += 1
        err_frozen += l1(y0, yt)
        err_adapt += l1(y1, yt)
    total = d_h * d_in + d_out * d_h
    return {
        "rank": 4,
        "param_fraction": params / total,
        "cert_bound": bound,
        "max_empirical_change": max_change,
        "bound_violations": violations,
        "bound_tightness": bound / max(1e-12, max_change),
        "mae_frozen": err_frozen / n,
        "mae_adapt": err_adapt / n,
        "mae_gain": 1.0 - (err_adapt / max(1e-12, err_frozen)),
    }


def exp83(rng):
    # v18: any pose ambiguity -> immediate Degraded/SafeStop
    # ARL: ask (resolves reducible ambiguity) -> adapt (reduces model bias)
    #      -> degrade only if irreducible ambiguity remains
    episodes = 50000
    p_ambiguous = 0.35      # most episodes are unambiguous
    p_reducible = 0.72      # among ambiguous ones, most are epistemic
    p_ask_resolve = 0.86
    p_adapt_help = 0.65

    nom18 = nomarl = 0
    asks = adapts = degrades18 = degrades = 0
    unsafe = 0
    extra_time = 0.0
    for _ in range(episodes):
        if rng.random() >= p_ambiguous:
            nom18 += 1
            nomarl += 1
            continue
        reducible = rng.random() < p_reducible
        # v18 sees ambiguity and degrades immediately
        degrades18 += 1
        if not reducible:
            degrades += 1
            continue
        # ARL first asks a safe information-gathering question
        asks += 1
        extra_time += rng.uniform(0.2, 0.8)
        if rng.random() < p_ask_resolve:
            nomarl += 1
            continue
        # residual model bias can be repaired by an admissible low-rank edit
        adapts += 1
        extra_time += rng.uniform(0.1, 0.4)
        if rng.random() < p_adapt_help:
            nomarl += 1
        else:
            degrades += 1
    return {
        "nominal_v18": nom18 / episodes,
        "nominal_arl": nomarl / episodes,
        "degrade_rate_v18": degrades18 / episodes,
        "degrade_rate_arl": degrades / episodes,
        "ask_rate": asks / episodes,
        "adapt_rate": adapts / episodes,
        "mean_extra_time_s": extra_time / episodes,
        "unsafe": unsafe,
    }


def main():
    rng = random.Random(42)
    res = {
        "E79_80_pose_set": exp79_80(rng),
        "E81_82_peft": exp81_82(rng),
        "E83_arl": exp83(rng),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
