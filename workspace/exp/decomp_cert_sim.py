"""DECOMP-CERT synthetic mechanism check.

Inspiration words this cycle: task decomposition / UniBot World Challenge.

Question.  The certificate stack (v21) composes safety predicates.  At the
*task* level the scored quantity is different: average success rate and
average step score over 32 tabletop tasks under 5 generalization axes.  If we
decompose a long task into n skills and claim "the task succeeds", what is a
sound composition bound, and how do checkpoints / retries change it?

Claims checked here (declared generative model, never fitted):
  A1  The distribution-free lower bound on joint success is the Frechet /
      union bound  LB(n,p) = max(0, n*p - (n-1)).  The independence product
      p**n is NOT a lower bound; it overestimates under negative dependence.
  A2  LB collapses to 0 once n > 1/(1-p)+1, i.e. long-horizon tasks have
      vacuous sound guarantees unless the chain is broken.
  A3  Checkpointing (re-observe + re-plan) resets the common cause; with one
      retry per block the task success becomes composable again, but every
      checkpoint costs steps, so there is a finite optimal block length b*
      under the competition's success/step-score objective.

NOT benchmark evidence.  Numbers are properties of a stated copula model.
"""
import json
import math
import os
import random
import statistics as st
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "decomp_cert_results.json")
ND = NormalDist()
random.seed(20261110)


def frechet_lb(n, p):
    return max(0.0, n * p - (n - 1.0))


def product(n, p):
    return p ** n


def mc_joint(n, p, rho, trials=120000):
    """Equicorrelated Gaussian copula, valid for rho in [-1/(n-1), 1].

    U = sqrt(c1) * Z/sqrt(n) + sqrt(c2) * (E - mean(E)),
    c1 = 1+(n-1)*rho, c2 = 1-rho.  Then Var(U_i)=1, Cov(U_i,U_j)=rho.
    """
    if n == 1:
        return p
    lo = -1.0 / (n - 1)
    assert lo <= rho <= 1.0, (n, rho, lo)
    thr = ND.inv_cdf(1.0 - p)
    c1 = 1.0 + (n - 1.0) * rho
    c2 = 1.0 - rho
    a = math.sqrt(c1) / math.sqrt(n)
    b = math.sqrt(c2)
    ok = 0
    for _ in range(trials):
        z = random.gauss(0.0, 1.0)
        e = [random.gauss(0.0, 1.0) for _ in range(n)]
        m = sum(e) / n
        good = True
        for i in range(n):
            u = a * z + b * (e[i] - m)
            if u <= thr:
                good = False
                break
        ok += good
    return ok / trials


def part_a_bounds():
    rows = []
    for p in (0.99, 0.97, 0.95, 0.90):
        for n in (1, 5, 10, 20, 50, 100, 200):
            lb = frechet_lb(n, p)
            prod = product(n, p)
            rho_pos = 0.5 if n > 1 else 0.0
            rho_neg = (-0.5 / (n - 1)) if n > 1 else 0.0
            emp_pos = mc_joint(n, p, rho_pos, trials=40000)
            emp_neg = mc_joint(n, p, rho_neg, trials=40000)
            rows.append({
                "p": p, "n": n,
                "frechet_lb": lb, "product": prod,
                "mc_rho_pos": emp_pos, "mc_rho_neg": emp_neg,
                "product_overestimates_neg": max(0.0, prod - emp_neg),
                "lb_is_sound_pos": emp_pos >= lb - 0.01,
                "lb_is_sound_neg": emp_neg >= lb - 0.01,
            })
    return rows


def block_joint(n, p, rho, trials=60000):
    return mc_joint(n, p, rho, trials)


def part_b_checkpoint(n=40, p=0.97, rho=0.5, c_ckpt=2.0, lam=0.08):
    """Score = success - lam * (steps / n).  One retry per failed block.

    Re-observation at a checkpoint resets the common cause, so blocks are
    independent and each failed block gets one fresh attempt.  The
    no-checkpoint baseline has neither reset nor retry.  Every checkpoint
    costs c_ckpt extra steps, which the competition's step score penalises.
    """
    per_skill = p
    no_ckpt_succ = block_joint(n, per_skill, rho, trials=80000)
    no_ckpt_steps = n * (1.0 + (1.0 - no_ckpt_succ))
    rows = []
    for b in range(1, n):
        if n % b != 0:
            continue
        p_block = block_joint(b, per_skill, rho, trials=80000) if b > 1 else per_skill
        p_block_retry = 1.0 - (1.0 - p_block) ** 2
        m = n // b
        succ = p_block_retry ** m
        steps = m * (b + c_ckpt) * (1.0 + (1.0 - p_block))
        rows.append({"block": b, "blocks": m, "p_block": p_block,
                     "success": succ, "steps_per_skill": steps / n})
    no_ckpt = {"block": n, "blocks": 1, "p_block": no_ckpt_succ,
               "success": no_ckpt_succ,
               "steps_per_skill": no_ckpt_steps / n}
    cands = rows + [no_ckpt]
    lam_sweep = []
    for L in (0.02, 0.05, 0.08, 0.10, 0.20, 0.35):
        scored = [dict(r, lam=L, score=r["success"] - L * r["steps_per_skill"])
                  for r in cands]
        best = max(scored, key=lambda r: r["score"])
        lam_sweep.append({"lam": L, "best_block": best["block"],
                          "score": best["score"],
                          "success": best["success"],
                          "steps_per_skill": best["steps_per_skill"]})
    rows = [dict(r, lam=lam, score=r["success"] - lam * r["steps_per_skill"])
            for r in rows]
    no_ckpt = dict(no_ckpt, lam=lam,
                   score=no_ckpt["success"] - lam * no_ckpt["steps_per_skill"])
    best = max(rows + [no_ckpt], key=lambda r: r["score"])
    return {"n": n, "p": p, "rho": rho, "c_ckpt": c_ckpt, "lam": lam,
            "no_checkpoint": no_ckpt, "best": best, "rows": rows,
            "lambda_sweep": lam_sweep}


def part_c_collapse_threshold():
    out = []
    for p in (0.99, 0.98, 0.97, 0.95, 0.90):
        out.append({"p": p, "n_collapse": math.floor(1.0 / (1.0 - p)) + 1})
    return out


def main():
    a = part_a_bounds()
    b = part_b_checkpoint()
    c = part_c_collapse_threshold()
    res = {
        "note": "synthetic mechanism check; declared copula model, not benchmark data",
        "seed": 20261110,
        "part_a_bounds": a,
        "part_b_checkpoint": b,
        "part_c_collapse_threshold": c,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)

    print("A) bounds: p,n | frechet_lb | product | mc(rho=+.5) | mc(rho=-)")
    for r in a:
        if r["n"] in (10, 50, 100, 200):
            print(f"  p={r['p']:.2f} n={r['n']:3d} | {r['frechet_lb']:.4f} | "
                  f"{r['product']:.4f} | {r['mc_rho_pos']:.4f} | {r['mc_rho_neg']:.4f}")
    print("C) collapse threshold n>1/(1-p)+1:")
    for r in c:
        print(f"  p={r['p']:.2f} -> n_collapse={r['n_collapse']}")
    bb = b
    print(f"B) checkpoint search n={bb['n']} p={bb['p']} rho={bb['rho']} "
          f"c_ckpt={bb['c_ckpt']} lam={bb['lam']}")
    print(f"  no-checkpoint: success={bb['no_checkpoint']['success']:.4f} "
          f"steps/skill={bb['no_checkpoint']['steps_per_skill']:.3f} "
          f"score={bb['no_checkpoint']['score']:.4f}")
    print(f"  best b*={bb['best']['block']} blocks={bb['best']['blocks']} "
          f"success={bb['best']['success']:.4f} "
          f"steps/skill={bb['best']['steps_per_skill']:.3f} "
          f"score={bb['best']['score']:.4f}")
    for r in bb["rows"]:
        print(f"    b={r['block']:2d} m={r['blocks']:2d} p_b={r['p_block']:.4f} "
              f"succ={r['success']:.4f} steps/skill={r['steps_per_skill']:.3f} "
              f"score={r['score']:.4f}  (lam={bb['lam']})")
    print("  lambda sweep -> best block (granularity vs step-score weight):")
    for r in bb["lambda_sweep"]:
        print(f"    lam={r['lam']:.2f} -> b*={r['best_block']:2d} "
              f"succ={r['success']:.4f} steps/skill={r['steps_per_skill']:.3f} "
              f"score={r['score']:.4f}")
    print(f"[decomp_cert_sim] wrote {OUT}")


if __name__ == "__main__":
    main()
