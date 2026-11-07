"""Round-28 synthetic mechanism check: RISK-ADMITTED RECONFIGURATION (RAR).

NOT benchmark evidence.  Isolates THREE questions about the round-28 proposal
(reconfigurable mechanism x instance segmentation x action chunking):

  S1  Repair-operator frontier.  A chunk fails mid-execution because a human
      took the target instance.  Repair options: REBIND the failed role to a
      retrieved substitute instance (cheap, but inherits the identity
      corruption p_id of the local instance graph), REPLAN the whole chunk
      (expensive, but re-perceives, so it repairs most identity corruption),
      SUBSTITUTE a different mechanism on the same instance, CONTINUE, WAIT.
      Q: where is the crossover between REBIND and REPLAN, does it match the
      closed-form utility comparison, and does a belief-based admission rule
      with a NOISY estimate of p_id recover the oracle choice?

  S2  Binding retrieval.  The substitute for a failed role is retrieved from
      the local instance set by a score over (semantics, affordance, size,
      geometry, reachability).  Q: what is the top-1 hit rate of each scoring
      variant, and can the top1-top2 margin calibrate P(hit) well enough to
      feed S1?

  S3  Knot granularity.  A chunk is a sequence of action units with verified
      knots; after a failure we rewind to the last verified knot instead of
      the chunk start.  Q: what knot spacing minimises expected wasted steps,
      given verification error rates?

Generative models are DECLARED, not fitted.  All numbers are mechanism checks.

Run:  PYTHONPATH=<workspace>/.pylibs python3 exp/r28_reconfig_sim.py
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261107

# ---------------------------------------------------------------- S2 config
C_CLASSES = 12
AFF_DIM = 4
ROLE_CLS = 5
ROLE_SIZE = 1.0
ROLE_AFF = np.array([1.0, 0.0, 1.0, 0.0])
ROLE_POS = np.array([0.60, 0.40])
SIZE_TOL = 0.35
REACH_R = 1.20
SEM_NOISE = 0.30
AFF_NOISE = 0.20
POS_NOISE = 0.25
SIZE_NOISE = 0.30

W_SEM, W_AFF, W_SIZE, W_POS, W_REACH = 1.0, 0.60, 0.50, 0.80, 0.70

# ---------------------------------------------------------------- S1 config
LAM = 0.02          # score points burned per extra step (step-efficiency price)
HARM_PEN = 2.0      # score points lost by grabbing / manipulating a wrong object
S_TAIL = 0.90       # P(chunk tail succeeds | rebound target is a valid substitute)
S_PLAN = 0.95       # P(freshly planned chunk succeeds | a valid target exists)
Q_AVAIL = 0.90      # P(a valid substitute exists in the scene at all)
CORRUPT_GRAB = 0.80    # P(corrupted identity -> robot acts on the wrong object)
REPLAN_REPAIRS = 0.25  # fraction of identity corruption a fresh re-perception repairs

OPS = ["REBIND", "REPLAN", "SUBSTITUTE", "CONTINUE", "WAIT"]
OP_PARAMS = {
    # op: (base_steps, base_sd, miss_steps, static_success, static_harm)
    "REBIND": dict(c0=2.0, csd=0.6, miss=3.0, s=None, h=None),
    "REPLAN": dict(c0=9.0, csd=1.5, miss=4.0, s=None, h=None),
    "SUBSTITUTE": dict(c0=3.5, csd=0.8, miss=3.0, s=0.45, h=0.02),
    "CONTINUE": dict(c0=4.0, sd=1.0, miss=2.0, s=0.12, h=0.01),
    "WAIT": dict(c0=2.5, csd=0.8, miss=2.0, s=0.30, h=0.005),
}
OP_PARAMS["CONTINUE"]["csd"] = 1.0


def logistic(x):
    return 1.0 / (1.0 + np.exp(-x))


# ---------------------------------------------------------------------- S2
def make_class_emb(rng):
    E = rng.normal(size=(C_CLASSES, 32))
    return E / np.linalg.norm(E, axis=1, keepdims=True)


def gen_scene(rng, class_emb, n_hard=4, n_easy=8):
    insts = []

    def new(cls, size, aff, pos, reach):
        emb = class_emb[cls] + SEM_NOISE * rng.normal(size=class_emb.shape[1])
        emb = emb / np.linalg.norm(emb)
        return dict(cls=cls, size=size, aff=aff, pos=pos, reach=reach,
                    emb=emb, valid=False)

    for _ in range(int(rng.integers(1, 4))):
        it = new(ROLE_CLS,
                 ROLE_SIZE + rng.normal(0, 0.08),
                 np.clip(ROLE_AFF + AFF_NOISE * rng.normal(size=AFF_DIM), 0, 1),
                 ROLE_POS + rng.normal(0, 0.06, 2),
                 True)
        it["valid"] = True
        insts.append(it)

    hard = ["size", "aff", "reach", "pos", "size"]
    for k in hard[:n_hard]:
        if k == "size":
            it = new(ROLE_CLS, ROLE_SIZE + SIZE_TOL + 0.35 + abs(rng.normal(0, 0.15)),
                     ROLE_AFF, ROLE_POS + rng.normal(0, 0.06, 2), True)
        elif k == "aff":
            it = new(ROLE_CLS, ROLE_SIZE + rng.normal(0, 0.08),
                     np.clip(1.0 - ROLE_AFF + AFF_NOISE * rng.normal(size=AFF_DIM), 0, 1),
                     ROLE_POS + rng.normal(0, 0.06, 2), True)
        elif k == "reach":
            it = new(ROLE_CLS, ROLE_SIZE + rng.normal(0, 0.08), ROLE_AFF,
                     ROLE_POS + rng.normal(0, 0.06, 2), False)
        else:
            it = new(ROLE_CLS, ROLE_SIZE + rng.normal(0, 0.08), ROLE_AFF,
                     ROLE_POS + np.array([1.1, 0.0]) + rng.normal(0, 0.08, 2), True)
        insts.append(it)

    for _ in range(n_easy):
        cls = int(rng.integers(0, C_CLASSES))
        it = new(cls,
                 abs(rng.normal(0, 1.0)) + 0.2,
                 (rng.random(AFF_DIM) < 0.4).astype(float),
                 rng.normal(0, 0.8, 2),
                 bool(rng.random() < 0.75))
        insts.append(it)
    return insts


def score_inst(it, role_emb, variant):
    cos_sem = float(np.dot(it["emb"], role_emb))
    cos_aff = float(np.dot(it["aff"], ROLE_AFF) /
                    (np.linalg.norm(it["aff"]) * np.linalg.norm(ROLE_AFF) + 1e-9))
    d_size = abs(it["size"] - ROLE_SIZE)
    d_pos = float(np.linalg.norm(it["pos"] - ROLE_POS))
    unreach = 0.0 if it["reach"] else 1.0
    if variant == "sem_only":
        return cos_sem
    if variant == "sem_aff":
        return W_SEM * cos_sem + W_AFF * cos_aff
    return (W_SEM * cos_sem + W_AFF * cos_aff
            - W_SIZE * d_size - W_POS * d_pos - W_REACH * unreach)


def s2_binding(rng, n_scenes=4000):
    class_emb = make_class_emb(rng)
    role_emb = class_emb[ROLE_CLS] + SEM_NOISE * rng.normal(size=class_emb.shape[1])
    role_emb = role_emb / np.linalg.norm(role_emb)
    variants = ["sem_only", "sem_aff", "full"]
    rows = {v: dict(top1=[], top3=[], marg=[]) for v in variants}
    full_detail = []
    for _ in range(n_scenes):
        insts = gen_scene(rng, class_emb)
        for v in variants:
            sc = np.array([score_inst(it, role_emb, v) for it in insts])
            order = np.argsort(-sc)
            hit1 = bool(insts[order[0]]["valid"])
            hit3 = any(insts[j]["valid"] for j in order[:3])
            rows[v]["top1"].append(hit1)
            rows[v]["top3"].append(hit3)
            rows[v]["marg"].append(float(sc[order[0]] - sc[order[1]]))
            if v == "full":
                full_detail.append((float(sc[order[0]] - sc[order[1]]), hit1))
    out = {}
    for v in variants:
        out[v] = dict(
            top1=float(np.mean(rows[v]["top1"])),
            top3=float(np.mean(rows[v]["top3"])),
            margin=float(np.mean(rows[v]["marg"])),
        )
    det = np.array(full_detail)
    order = np.argsort(det[:, 0])
    d, h = det[order, 0], det[order, 1]
    nb = 10
    bins = np.array_split(np.arange(len(d)), nb)
    cal = []
    ece = 0.0
    brier = 0.0
    for b in bins:
        if len(b) == 0:
            continue
        emp = float(h[b].mean())
        pred = float(d[b].mean())
        cal.append(dict(margin_lo=float(d[b].min()), margin_hi=float(d[b].max()),
                        emp=emp, n=int(len(b))))
        ece += len(b) / len(d) * abs(emp - pred)
        brier += float(np.mean((h[b] - d[b]) ** 2))
    out["calibration_full"] = dict(
        ece=float(ece), brier=float(brier), bins=cal,
        corr_margin_hit=float(np.corrcoef(d, h)[0, 1]),
    )
    out["n_scenes"] = n_scenes
    return out


# ---------------------------------------------------------------------- S1
def op_probs(op, p_id, q_hit):
    pr = OP_PARAMS[op]
    if op == "REBIND":
        h = p_id * CORRUPT_GRAB
        s = (1.0 - p_id) * q_hit * S_TAIL
    elif op == "REPLAN":
        h = p_id * REPLAN_REPAIRS * CORRUPT_GRAB
        s = Q_AVAIL * S_PLAN
    else:
        h = pr["h"]
        s = pr["s"]
    m = max(0.0, 1.0 - h - s)
    return s, h, m


def op_utility(op, p_id, q_hit, lam=LAM, harm=HARM_PEN, scale=1.0):
    pr = OP_PARAMS[op]
    s, h, m = op_probs(op, p_id, q_hit)
    esteps = pr["c0"] * scale + m * pr["miss"]
    return s - harm * h - lam * esteps, s, h, esteps


def s1_frontier(rng, q_hit, lam=LAM, harm=HARM_PEN):
    ps = np.round(np.arange(0.0, 0.61, 0.02), 3)
    analytic = []
    for p in ps:
        utils = {op: op_utility(op, float(p), q_hit, lam, harm)[0] for op in OPS}
        best = max(utils, key=utils.get)
        analytic.append(dict(p_id=float(p), best=best,
                             u_rule=utils[best],
                             u_rebind=utils["REBIND"], u_replan=utils["REPLAN"]))
    # exact affine crossover between REBIND and REPLAN (both affine in p_id)
    u_rb0 = op_utility("REBIND", 0.0, q_hit, lam, harm)[0]
    u_rp0 = op_utility("REPLAN", 0.0, q_hit, lam, harm)[0]
    u_rb1 = op_utility("REBIND", 1.0, q_hit, lam, harm)[0]
    u_rp1 = op_utility("REPLAN", 1.0, q_hit, lam, harm)[0]
    cross = (u_rb0 - u_rp0) / ((u_rb1 - u_rb0) - (u_rp1 - u_rp0))
    cross = float(np.clip(cross, 0.0, 1.0))

    # Monte-Carlo: estimated-parameter admission rule vs oracle and baselines
    n_ev = 20000
    mc = []
    for p in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.45]:
        p_hat = float(np.clip(p + rng.normal(0, 0.06), 0.0, 1.0))
        scale = float(np.clip(1.0 + rng.normal(0, 0.15), 0.6, 1.6))
        u_est = {op: op_utility(op, p_hat, q_hit, lam, harm, scale=scale)[0] for op in OPS}
        chosen = max(u_est, key=u_est.get)
        u_true = {op: op_utility(op, p, q_hit, lam, harm)[0] for op in OPS}
        oracle = max(u_true, key=u_true.get)
        regret = u_true[oracle] - u_true[chosen]
        realized = []
        for _ in range(n_ev):
            op = chosen
            s, h, m = op_probs(op, p, q_hit)
            u = rng.random()
            if u < s:
                realized.append(1.0 - lam * OP_PARAMS[op]["c0"] * scale)
            elif u < s + h:
                realized.append(-harm - lam * OP_PARAMS[op]["c0"] * scale)
            else:
                realized.append(-lam * (OP_PARAMS[op]["c0"] * scale + OP_PARAMS[op]["miss"]))
        mc.append(dict(p_id=p, p_hat=p_hat, chosen=chosen, oracle=oracle,
                       regret=float(regret),
                       u_chosen=float(u_true[chosen]), u_oracle=float(u_true[oracle]),
                       u_always_rebind=float(u_true["REBIND"]),
                       u_always_replan=float(u_true["REPLAN"]),
                       realized_mean=float(np.mean(realized))))
    return dict(curve=analytic, analytic_crossover=round(cross, 4),
                monte_carlo=mc,
                harm_in_step_equivalents=round(harm / lam, 1),
                lam=lam, harm_pen=harm)


# ---------------------------------------------------------------------- S3
def s3_knots(m=12, f_neg=0.05, f_pos=0.05, c_fp=3.0):
    rows = []
    for k in [1, 2, 3, 4, 6, 12, 999]:
        tot = 0.0
        for i in range(1, m + 1):
            if k >= m:
                j = 0
            else:
                j = (i // k) * k
            waste_ok = (i - j) + f_pos * c_fp
            j2 = max(0, j - k)
            waste_bad = (i - j2) + f_pos * c_fp
            tot += (1.0 - f_neg) * waste_ok + f_neg * waste_bad
        rows.append(dict(k=(k if k < 999 else "none"), waste=float(tot / m)))
    base = [r for r in rows if r["k"] == "none"][0]["waste"]
    best = min([r for r in rows if r["k"] != "none"], key=lambda r: r["waste"])
    for r in rows:
        r["saving_vs_none"] = round(base - r["waste"], 3)
        r["saving_pct"] = round(100.0 * (base - r["waste"]) / base, 1)
    return dict(m=m, f_neg=f_neg, f_pos=f_pos, c_fp=c_fp, rows=rows,
                best_k=best["k"], best_waste=best["waste"], no_knot_waste=base)


def sweep_knots():
    return [s3_knots(f_neg=f) for f in (0.0, 0.05, 0.15)]


def main():
    rng = np.random.default_rng(SEED)
    out = {}
    out["s2_binding"] = s2_binding(rng)
    q_hit = out["s2_binding"]["full"]["top1"]
    out["q_hit_used_in_s1"] = q_hit
    out["s1_frontier"] = s1_frontier(rng, q_hit)
    out["s1_sensitivity_mild_harm"] = s1_frontier(rng, q_hit, harm=0.2)
    out["s1_sensitivity_low_step_price"] = s1_frontier(rng, q_hit, lam=0.005)
    out["s3_knots"] = sweep_knots()
    out["config"] = dict(seed=SEED, lam=LAM, harm_pen=HARM_PEN,
                         q_hit=q_hit, s_tail=S_TAIL, s_plan=S_PLAN,
                         q_avail=Q_AVAIL, corrupt_grab=CORRUPT_GRAB,
                         replan_repairs=REPLAN_REPAIRS)
    out["note"] = "B-level synthetic mechanism check; NOT robot benchmark evidence"

    with open(os.path.join(HERE, "r28_reconfig_results.json"), "w") as fh:
        json.dump(out, fh, indent=1)

    print("== S2 binding retrieval (4000 scenes) ==")
    for v in ("sem_only", "sem_aff", "full"):
        r = out["s2_binding"][v]
        print("  %-8s top1=%.3f top3=%.3f margin=%.3f" %
              (v, r["top1"], r["top3"], r["margin"]))
    c = out["s2_binding"]["calibration_full"]
    print("  full-margin calibration: ECE=%.3f Brier=%.3f corr=%.3f" %
          (c["ece"], c["brier"], c["corr_margin_hit"]))

    print("== S1 repair-operator frontier (q_hit=%.3f) ==" % q_hit)
    fr = out["s1_frontier"]
    print("  analytic REBIND/REPLAN crossover p_id*=%.4f" % fr["analytic_crossover"])
    print("  one wrong grab costs %.0f steps of step score" % fr["harm_in_step_equivalents"])
    print("  %-6s %-10s %8s %8s %8s" % ("p_id", "best", "u_best", "u_rebind", "u_replan"))
    for r in fr["curve"]:
        if abs(r["p_id"] * 100 - round(r["p_id"] * 100)) < 1e-9 and \
           int(round(r["p_id"] * 100)) % 5 == 0:
            print("  %-6.2f %-10s %8.4f %8.4f %8.4f" %
                  (r["p_id"], r["best"], r["u_rule"], r["u_rebind"], r["u_replan"]))
    print("  Monte-Carlo admission rule (noisy p_hat):")
    for r in fr["monte_carlo"]:
        print("   p=%.2f p_hat=%.2f chose=%-10s oracle=%-10s regret=%.4f "
              "U(rule)=%.4f U(rebind)=%.4f U(replan)=%.4f" %
              (r["p_id"], r["p_hat"], r["chosen"], r["oracle"], r["regret"],
               r["u_chosen"], r["u_always_rebind"], r["u_always_replan"]))
    print("  mild-harm crossover p*=%.4f ; low-step-price crossover p*=%.4f" %
          (out["s1_sensitivity_mild_harm"]["analytic_crossover"],
           out["s1_sensitivity_low_step_price"]["analytic_crossover"]))

    print("== S3 knot granularity (m=12) ==")
    for s in out["s3_knots"]:
        print("  f_neg=%.2f best_k=%s waste=%.2f (no-knot %.2f, saving %.1f%%)" %
              (s["f_neg"], s["best_k"], s["best_waste"], s["no_knot_waste"],
               100.0 * (s["no_knot_waste"] - s["best_waste"]) / s["no_knot_waste"]))
        print("    " + " ".join("k=%s:%.2f" % (r["k"], r["waste"]) for r in s["rows"]))


if __name__ == "__main__":
    main()
