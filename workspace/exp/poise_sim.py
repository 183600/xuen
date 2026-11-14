"""Synthetic mechanism check for EQUIPOISE-RAS (round 70).

NOT benchmark evidence.  Isolates three claims:
  A. Palpation detection power scales with the overlap between the
     null-space probe direction and the unmodeled-support direction beta.
     At beta=0 the probe is *blind*; a certificate that reads low residual
     as 'verified clear' has false-certificate probability 1.
  B. A null-space probe pays zero balance margin but pays posture effort
     ~ 1/beta^2; a borrowed (out-of-null-space) probe pays margin ~1.
     This is the tradeoff the ledger has to price.
  C. Repeated orthogonal probes reduce support-hypothesis error, matching
     the k-orthogonal-evidence discipline inherited from R69.
Pure Python, deterministic seed.
"""
import json, math, random, statistics

SEED = 20261114
N = 20000

def normal(rng, mu=0.0, sigma=1.0):
    return rng.gauss(mu, sigma)

def auc(pos, neg):
    # Mann-Whitney U / (n_pos*n_neg); average ranks for ties.
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
    idx = min(len(neg_sorted) - 1, max(0, int(math.ceil((1.0 - fpr) * len(neg_sorted))) - 1))
    tau = neg_sorted[idx]
    return sum(1 for x in pos if x > tau) / len(pos), tau

def part_a(betas, A=2.0, sigma=1.0):
    rng = random.Random(SEED)
    rows = []
    neg = [normal(rng, 0.0, sigma) for _ in range(N)]
    for beta in betas:
        pos = [beta * A + normal(rng, 0.0, sigma) for _ in range(N)]
        a = auc(pos, neg)
        tpr, tau = tpr_at_fpr(pos, neg, 0.05)
        rows.append({"beta": beta, "auc": a, "tpr_at_fpr5": tpr, "tau": tau})
    return rows

def part_b(betas, target_snr=3.0, rho=1.0):
    # null-space probe: zero margin, effort ~ (target/beta)^2
    # borrowed probe: unit margin, effort ~ target^2
    rows = []
    for beta in betas:
        if beta <= 1e-9:
            rows.append({"beta": beta, "free_probe_effort": None,
                         "margin_cost": 0.0, "must_borrow": True})
            continue
        effort_free = rho * (target_snr / beta) ** 2
        effort_borrow = rho * target_snr ** 2
        rows.append({"beta": beta,
                     "free_probe_effort": effort_free,
                     "free_vs_borrow_effort": effort_free / effort_borrow,
                     "margin_cost": 0.0,
                     "must_borrow": effort_free > 4.0 * effort_borrow})
    return rows

def part_c(ns, gap=1.2, sigma=1.0, prior=0.5, trials=20000):
    # two contact hypotheses; each probe is a noisy observation with
    # mean gap under H1 and 0 under H0. Bayes error after n probes.
    rng = random.Random(SEED + 7)
    rows = []
    for n in ns:
        err = 0
        for _ in range(trials):
            true_h = 1 if rng.random() < prior else 0
            # posterior log-odds from n iid Gaussian observations
            llr = 0.0
            for _ in range(n):
                y = (gap if true_h else 0.0) + normal(rng, 0.0, sigma)
                llr += (gap * y - 0.5 * gap * gap) / (sigma * sigma)
            pred = 1 if llr > 0 else 0
            err += (pred != true_h)
        rows.append({"n_probes": n, "bayes_error": err / trials})
    return rows

def main():
    betas = [1.0, 0.7, 0.4, 0.0]
    out = {
        "seed": SEED,
        "note": "synthetic mechanism check; not benchmark evidence",
        "A_camouflage": part_a(betas),
        "B_nullspace": part_b(betas),
        "C_evidence": part_c([1, 2, 3, 5, 10]),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open("/tmp/poise_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
