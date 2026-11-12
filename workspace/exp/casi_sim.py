"""Synthetic mechanism check for Context-Aware State Isolation (CASI).

NOT benchmark evidence. Isolates one question: under scene/intent
misclassification and stale context epochs, does routing every cross-layer
read through a context-gated *projection* (instead of shared mutable state)
reduce safety-critical contamination without paying the full opportunity
cost of always-private (L0) isolation?

Architectures compared:
  shared   : round-60 style -- observed scene writes K_safe directly.
  staticL0 : always isolate -> fixed conservative K_safe.
  casi     : isolation level chosen by inferred context; projection gated by
             scene confidence + context-epoch consistency.
"""
import json, math, random, statistics, os

SCENES = ["smooth", "wet", "stairs"]
K_SAFE = {"smooth": 1.0, "wet": 0.4, "stairs": 0.6}
K_CONS = min(K_SAFE.values())
TAU_CONF = 0.70
TAU_CTX = 1.0

def observe(true, rng, acc=0.85):
    if rng.random() < acc:
        obs = true
        conf = rng.uniform(0.80, 0.98)
    else:
        obs = rng.choice([s for s in SCENES if s != true])
        # misleadingly confident a minority of the time
        conf = rng.uniform(0.30, 0.65) if rng.random() < 0.8 else rng.uniform(0.70, 0.80)
    return obs, conf

def success(K, ideal):
    return math.exp(-abs(K - ideal) / 0.35)

def danger(K, true):
    return K > K_SAFE[true] * 1.10

def episode(arch, rng):
    true = rng.choice(SCENES)
    obs, conf = observe(true, rng)
    ctx = "grasp" if rng.random() < 0.40 else "approach"
    stale = rng.random() < 0.05          # ROS epoch arrives late

    shared = False
    if arch == "shared":
        K = K_SAFE[obs]; shared = True
    elif arch == "staticL0":
        K = K_CONS
    else:  # casi
        if ctx == "grasp":
            K = K_CONS                    # critical phase -> L0 private
        else:
            if conf >= TAU_CONF and not stale:
                K = K_SAFE[obs]; shared = True
            else:
                K = K_CONS                # projection rejected / stale -> conservative
    return dict(true=true, obs=obs, conf=conf, ctx=ctx, stale=stale,
                K=K, success=success(K, K_SAFE[true]),
                danger=danger(K, true), shared=shared)

def run(arch, n=40000, seed=7):
    rng = random.Random(seed)
    eps = [episode(arch, rng) for _ in range(n)]
    return dict(
        arch=arch,
        success=statistics.mean(e["success"] for e in eps),
        danger_rate=statistics.mean(e["danger"] for e in eps),
        mean_abs_K_err=statistics.mean(abs(e["K"] - K_SAFE[e["true"]]) for e in eps),
        shared_state_ratio=statistics.mean(e["shared"] for e in eps),
    )

if __name__ == "__main__":
    rows = [run(a) for a in ("shared", "staticL0", "casi")]
    out = {"seed": 7, "n": 40000, "tau_conf": TAU_CONF, "eps": rows}
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "casi_results.json"), "w") as f:
        json.dump(out, f, indent=2)
    for r in rows:
        print(f"{r['arch']:9s} success={r['success']:.3f} "
              f"danger={r['danger_rate']:.4f} "
              f"|Kerr|={r['mean_abs_K_err']:.3f} "
              f"shared={r['shared_state_ratio']:.3f}")

def sweep():
    rows = []
    global TAU_CONF
    orig = TAU_CONF
    for tau in (0.5, 0.6, 0.7, 0.8, 0.9):
        TAU_CONF = tau
        r = run("casi")
        r["tau_conf"] = tau
        rows.append(r)
    TAU_CONF = orig
    return rows
