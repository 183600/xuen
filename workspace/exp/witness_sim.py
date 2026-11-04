"""Round-16 mechanism simulation: independent witnesses vs self-consistency, and
the statistical price of pooling state across ports/episodes.

This is a MECHANISM CHECK, not a benchmark result. It answers:
  Q1 how much of the *silent* grounding-failure class (OOD-G) any independent
     witness can catch at all -> the detectability ceiling (function of the
     geometry-detectable fraction zeta and the gesture-mismatch rate eta);
  Q2 whether a self-consistency gate (round-15 ZEST) can add anything there;
  Q3 what pooling calibration across N ports/episodes does to the conformal
     false-alarm rate, versus per-port-per-episode isolation.

Output: exp/witness_sim_results.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUT = EXP / "witness_sim_results.json"
RNG = np.random.default_rng(20261104)

# ---------------- declared model ----------------
N_TASKS = 32
BLOCKS = 120          # 5-step blocks per episode (30-step VLA chunk / 5-step execution)
NEED = 45             # progress units required to succeed
N_EP = 3000           # episodes per configuration
ALPHA = 0.10          # per-block conformal target false-alarm rate
ALPHA_W = 0.10        # per-block witness false-alarm rate on ID
C_FALLBACK = 1.25     # cost multiplier of the geometric fallback path
G_PRIM = 0.55         # success probability per block of the geometric fallback
RHO_G = 0.35          # probability that the episode starts with a grounding error
ZETA = 0.45           # fraction of grounding errors that leave a geometric trace
ETA = 0.60            # probability that a (wrongly grounded) gesture mismatches the verb prior
DELTA_GEO = 0.75      # P(witness fires | geometric trace present)
P_EXEC_BASE = 0.42    # per-block VLA execution competence (ID)
P_EXEC_OOD_E = 0.08   # per-block competence once an execution error is detected


def task_table(rng: np.random.Generator):
    c = rng.beta(2.2, 3.3, size=N_TASKS) * 0.75          # per-task competence spread
    zeta = rng.uniform(0.15, 0.75, size=N_TASKS)          # geometry-detectable fraction
    return c, zeta


def run_policy(policy: str, c_task: float, zeta: float, rng: np.random.Generator) -> dict:
    """One episode under the given gating policy."""
    grounding_error = rng.random() < RHO_G
    trace = grounding_error and (rng.random() < zeta)      # geometric / gesture trace exists
    if grounding_error and not trace:
        competence = 0.0                                    # silent OOD-G: VLA acts on wrong target
    else:
        competence = c_task
    progress = 0
    fallback = False
    false_fire = False
    fired = False
    for b in range(BLOCKS):
        # ---- gate decision at block start
        if policy in ("witness", "both") and not fired and b in (0, 1, 2):
            if trace and rng.random() < DELTA_GEO * ETA:
                fired = True
            elif (not grounding_error) and rng.random() < ALPHA_W:
                fired = True
                false_fire = True
        if policy == "zest" and not fired and b in (0, 1, 2):
            # self-consistency gate: fires only on execution inconsistency (OOD-E),
            # which is independent of grounding errors -> never fires on OOD-G
            if (not grounding_error) and rng.random() < 0.06:
                fired = True
                false_fire = True
        if policy == "oracle" and grounding_error:
            fired = True

        if fired:
            fallback = True
            succ = rng.random() < (G_PRIM if not grounding_error else G_PRIM * 0.6)
            progress += int(succ)
        else:
            progress += int(rng.random() < competence)
        if progress >= NEED:
            break
    return {"success": progress >= NEED,
            "false_fire": false_fire,
            "fallback": fallback,
            "grounding_error": grounding_error,
            "trace": trace}


def eval_policy(policy: str, c_task: float, zeta: float, n: int) -> dict:
    rng = np.random.default_rng(int(RNG.integers(1 << 30)))
    rows = [run_policy(policy, c_task, zeta, rng) for _ in range(n)]
    succ = np.mean([r["success"] for r in rows])
    ff = np.mean([r["false_fire"] for r in rows])
    fb = np.mean([r["fallback"] for r in rows])
    return {"success_rate": float(succ), "false_fallback_rate": float(ff),
            "fallback_rate": float(fb)}


def conformal_pooling_experiment(n_ports: int = 3, n_ep: int = 400, blocks: int = 120,
                                 alpha: float = ALPHA) -> dict:
    """Per-block scores from ID episodes; compare pooled vs isolated calibration."""
    rng = np.random.default_rng(7)
    # ID block scores: iid-ish positive distribution
    calib = rng.normal(0.0, 1.0, size=2000)
    q_pool = np.quantile(calib, 1 - alpha)
    test = rng.normal(0.0, 1.0, size=(n_ports * n_ep, blocks))
    pooled_fire = test > q_pool

    # isolated: calibrate per (port, episode) with n=... not possible without labels ->
    # emulate per-episode threshold from the first 30 blocks of that episode (legitimate:
    # within-episode calibration), then apply to the remaining 90 blocks
    iso_fire = np.zeros_like(pooled_fire)
    per_ep_fire_rates = []
    for i in range(test.shape[0]):
        head = test[i, :30]
        q_ep = np.quantile(head, 1 - alpha)
        tail = test[i, 30:] > q_ep
        iso_fire[i, 30:] = tail
        per_ep_fire_rates.append(tail.mean())
    M = pooled_fire.size
    out = {
        "n_ports": n_ports, "n_episodes_per_port": n_ep, "blocks_per_episode": blocks,
        "alpha_target": alpha,
        "pooled_per_block_fire_rate": float(pooled_fire.mean()),
        "pooled_any_fire_per_episode": float((pooled_fire.any(axis=1)).mean()),
        "isolated_per_block_fire_rate_tail": float(iso_fire[:, 30:].mean()),
        "isolated_any_fire_per_episode": float((iso_fire[:, 30:].any(axis=1)).mean()),
        "theoretical_pooled_any": 1 - (1 - alpha) ** M,
        "theoretical_isolated_any": 1 - (1 - alpha) ** (blocks - 30),
        "M_blocks_total": int(M),
    }
    return out


def main() -> None:
    c_tab, zeta_tab = task_table(RNG)
    policies = ["vla", "zest", "witness", "both", "oracle"]
    base = {p: {"success_rate": 0.0, "false_fallback_rate": 0.0, "fallback_rate": 0.0} for p in policies}
    per_task = []
    for t in range(N_TASKS):
        row = {"task": t, "c_task": float(c_tab[t]), "zeta": float(zeta_tab[t])}
        for p in policies:
            r = eval_policy(p, float(c_tab[t]), float(zeta_tab[t]), N_EP // 16)
            for k in base[p]:
                base[p][k] += r[k] / N_TASKS
            row[p] = r
        per_task.append(row)

    # sensitivity: geometry-detectable fraction
    sens = []
    for z in (0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        globals()["ZETA"] = z
        c0, z0 = 0.35, z
        r_w = eval_policy("witness", c0, z0, 4000)
        r_v = eval_policy("vla", c0, z0, 4000)
        r_o = eval_policy("oracle", c0, z0, 4000)
        sens.append({"zeta": z, "vla": round(r_v["success_rate"], 4),
                     "witness": round(r_w["success_rate"], 4),
                     "oracle": round(r_o["success_rate"], 4),
                     "gain_pp": round((r_w["success_rate"] - r_v["success_rate"]) * 100, 2)})
    # pooling experiment
    pool = conformal_pooling_experiment()

    out = {
        "model": {"N_TASKS": N_TASKS, "BLOCKS": BLOCKS, "NEED": NEED, "N_EP": N_EP,
                  "ALPHA": ALPHA, "ALPHA_W": ALPHA_W, "RHO_G": RHO_G, "ZETA": GLOBAL_ZETA,
                  "ETA": ETA, "DELTA_GEO": DELTA_GEO, "G_PRIM": G_PRIM,
                  "P_EXEC_BASE": P_EXEC_BASE},
        "aggregate": {p: {k: round(v, 4) for k, v in base[p].items()} for p in policies},
        "gain_vs_vla_pp": {p: round((base[p]["success_rate"] - base["vla"]["success_rate"]) * 100, 2)
                           for p in policies},
        "sensitivity_zeta": sens,
        "pooling_experiment": pool,
        "per_task": per_task,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out["aggregate"], indent=2))
    print("gain pp:", out["gain_vs_vla_pp"])
    print("zeta sensitivity:", json.dumps(sens, indent=1))
    print("pooling:", json.dumps(pool, indent=1))


if __name__ == "__main__":
    main()
