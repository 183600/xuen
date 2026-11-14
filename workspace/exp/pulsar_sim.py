"""Synthetic mechanism check for PULSAR-RAS (round 71: reward design x event camera).

NOT benchmark evidence.  Isolates three claims:
  A. Reward-event corroboration by an event camera is gated by *testability*
     kappa (fraction of the relevant change above the contrast threshold,
     inside FOV, outside the refractory dead zone).  As kappa -> 0 the
     honest and hacked episodes become statistically identical (AUC -> 0.5):
     "no event" cannot separate "no change" from "sub-threshold change".
  B. Raw event-count reward can be farmed by oscillation; a potential-based
     shaping over the *integrated* (reconstructed) event state cancels any
     closed-loop farming exactly.  A non-conservative (path-dependent)
     potential leaks reward around loops, motivating the cycle-consistency
     (curl) regulariser.
  C. A joint (reward-event, physical-event) channel is needed: a reward-only
     channel accepts hacks as progress; maintaining honest coverage while
     testability falls forces hack acceptance up toward 1.  Conversely the
     physical-event channel is what discovers "unrewarded progress"
     (specification blind spots).
Pure Python, deterministic seed.
"""
import json, math, random, statistics

SEED = 20261114
N = 20000


def normal(rng, mu=0.0, sigma=1.0):
    return rng.gauss(mu, sigma)


def auc(pos, neg):
    """Mann-Whitney U / (n_pos*n_neg) with average ranks for ties."""
    allv = [(x, 1) for x in pos] + [(x, 0) for x in neg]
    allv.sort(key=lambda t: t[0])
    ranks = [0.0] * len(allv)
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r_pos = sum(r for (_, lab), r in zip(allv, ranks) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (r_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def tpr_at_fpr(pos, neg, fpr=0.05):
    neg_sorted = sorted(neg)
    idx = min(len(neg_sorted) - 1,
              max(0, int(math.ceil((1.0 - fpr) * len(neg_sorted))) - 1))
    tau = neg_sorted[idx]
    return sum(1 for x in pos if x > tau) / len(pos), tau


def part_a(kappas, A=2.0, sigma=1.0):
    """Detect a reward hack: honest has the intended physical signature
    with mean kappa*A; a hack has no intended signature (mean 0).
    We score hack-likelihood as -statistic, so higher score = more hacked."""
    rng = random.Random(SEED)
    rows = []
    for kappa in kappas:
        honest = [kappa * A + normal(rng, 0.0, sigma) for _ in range(N)]
        hack = [normal(rng, 0.0, sigma) for _ in range(N)]
        honest_neg = honest            # negative class: honest (high stat)
        hack_pos = [-x for x in hack]  # positive class: hack (low stat)
        honest_pos = [-x for x in honest]
        a = auc(hack_pos, honest_pos)
        tpr, tau = tpr_at_fpr(hack_pos, honest_pos, 0.05)
        rows.append({"kappa": kappa, "auc_detect_hack": a,
                     "tpr_at_fpr5": tpr})
    return rows


def part_b(amps, cycles=10, threshold_C=0.5, eps=0.2):
    """Farming by oscillation of amplitude a over `cycles` cycles.
    raw        : reward proportional to number of threshold-crossing events
    pbrs_cons  : telescoping potential Phi(x)=0.5||x||^2 on integrated state
    pbrs_noncons: same plus non-conservative circulation eps*(-x2, x1)."""
    rows = []
    for a in amps:
        events = cycles * (a / threshold_C)          # crossings ~ A/C per cycle
        raw = events                                 # raw reward (event count)
        phi_start, phi_end = 0.5 * a * a, 0.5 * a * a  # x(0)=x(T)=0 actually
        # closed loop: reconstructed state starts and ends at origin => 0
        pbrs_cons = 0.0
        # circulation of (-x2, x1) around a circle radius a = 2*pi*a^2 per loop
        pbrs_noncons = eps * 2.0 * math.pi * a * a * cycles
        rows.append({"amplitude": a,
                     "raw_event_reward": raw,
                     "pbrs_conservative": pbrs_cons,
                     "pbrs_nonconservative": pbrs_noncons})
    return rows


def part_c(kappas, A=2.0, sigma=1.0, coverage=0.90,
           base=(0.75, 0.10, 0.10, 0.05)):
    """To keep `coverage` of genuine progress certified, the corroboration
    threshold must slide down as kappa falls; hack acceptance then rises.
    Also: blind-spot (unrewarded progress) discovery rate equals kappa."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(coverage)          # 1.2816 for 0.90
    rows = []
    for kappa in kappas:
        tau = kappa * A - z * sigma             # threshold for honest coverage
        # hack stat ~ N(0, sigma); accepted if > tau
        hack_accept = 1.0 - NormalDist().cdf((tau - 0.0) / sigma)
        rows.append({"kappa": kappa,
                     "hack_accept_at_90pct_coverage": hack_accept,
                     "blindspot_discovery": kappa})
    return rows


def main():
    out = {
        "seed": SEED,
        "n": N,
        "part_a_testability_hack_auc": part_a([1.0, 0.7, 0.4, 0.0]),
        "part_b_farming": part_b([0.2, 0.5, 1.0, 2.0]),
        "part_c_joint_channel": part_c([1.0, 0.7, 0.4, 0.0]),
    }
    with open("workspace/exp/pulsar_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
