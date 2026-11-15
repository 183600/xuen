"""Synthetic mechanism check for MetricVoiceGauge-ProFlow (v10, this round).

NOT benchmark evidence. Claims isolated here:
  A. One-sided gate: K_eff^v10 = min(K_eff^v9, K_prog) can only shrink, so
     late-abort steps never exceed v9 (structural, not statistical).
  B. Lead-time sufficiency: benefit grows with precursor lead L and saturates;
     with no precursor (missed shift) v10 == v9 exactly (the residual v9 risk).
  C. Flow generation accounting: ODE error scales ~1/NFE; the certified error
     bound deflates the admissible chunk length monotonically.
Stdlib only, seeded, ~2s.
"""
import json
import math
import random

SEED = 20261115
K_MAX = 10
N_CHUNKS = 20000


def run_stream(lead, p_shift=0.15, p_miss=0.0, sigma=1.0, z_q=1.0,
               neutral=False, rng=None):
    rng = rng or random.Random(SEED)
    late9 = late10 = 0
    chunks_late9 = chunks_late10 = 0
    k10_sum = 0
    worse = better = same = 0
    for _ in range(N_CHUNKS):
        # a shift, if any, would invalidate the certificate at step s.
        # h = s - 1 is the number of steps that are still safe.
        # All draws happen unconditionally so every lead shares the same stream.
        u_miss = rng.random()
        shift = rng.random() < p_shift
        s = rng.randint(1, K_MAX) if shift else K_MAX + 1
        noise = rng.gauss(0.0, sigma)
        h = min(K_MAX, s - 1)
        k9 = K_MAX                                  # v9: dDom=0 at chunk start
        l9 = max(0, k9 - h)
        if neutral:
            k10 = k9                                # one-sided neutral element
        else:
            # precursor fires at s - lead; only useful if it fires by step 0.
            detected = shift and (lead >= s) and (u_miss >= p_miss)
            if not detected:                        # no lead -> v9, no harm
                k10 = k9
            else:
                s_hat = s + noise                   # noisy onset estimate
                k_prog = max(1, int(math.floor(s_hat - z_q * sigma)) - 1)
                k10 = min(k9, k_prog)               # P13: shrink only
        l10 = max(0, k10 - h)
        late9 += l9
        late10 += l10
        chunks_late9 += (l9 > 0)
        chunks_late10 += (l10 > 0)
        k10_sum += k10
        if l10 > l9:
            worse += 1
        elif l10 < l9:
            better += 1
        else:
            same += 1
    n = N_CHUNKS
    return dict(
        lead=lead,
        late_steps_per_chunk_v9=round(late9 / n, 4),
        late_steps_per_chunk_v10=round(late10 / n, 4),
        late_chunk_frac_v9=round(chunks_late9 / n, 4),
        late_chunk_frac_v10=round(chunks_late10 / n, 4),
        mean_K_v10=round(k10_sum / n, 3),
        worse=worse, better=better, same=same,
    )


def part_a():
    neutral = run_stream(lead=0, neutral=True, rng=random.Random(SEED + 2))
    rows = [run_stream(lead=L, p_miss=0.2, rng=random.Random(SEED + 2))
            for L in (0, 4, 8, 12, 16, 24)]
    return dict(neutral_equivalence=neutral, lead_sweep=rows)


def flow_error(lam, nfe, x0=1.0):
    x = x0
    for _ in range(nfe):
        x += (-lam * x) / nfe
    return abs(x - x0 * math.exp(-lam))


def part_b(delta_budget=0.05, kappa=0.2):
    out = {}
    for lam in (0.5, 1.0, 2.0):
        rows = []
        for nfe in (1, 2, 4, 8, 16, 32):
            err = max(flow_error(lam, nfe, x0) for x0 in
                      (-2.0, -1.0, 0.5, 1.0, 2.0))
            delta = kappa * err
            k_gen = max(1, int(math.floor(K_MAX * (1.0 - min(1.0,
                                                         delta / delta_budget)))))
            rows.append(dict(nfe=nfe, max_err=round(err, 6),
                             delta=round(delta, 6), K_gen=k_gen))
        out[str(lam)] = rows
    return out


if __name__ == "__main__":
    result = dict(part_a=part_a(), part_b=part_b())
    with open("/home/runner/work/xuen/xuen/workspace/exp/proflow_results.json",
              "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))
