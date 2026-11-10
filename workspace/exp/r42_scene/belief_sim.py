"""Synthetic check for the scene-understanding half of round 42.

Question: when a task-critical object is occluded and a human may move it out of
view, does an explicit object-permanence belief + information-gain ("look")
policy beat (a) acting on the last-seen pose and (b) always looking?

1-D Gaussian belief, Monte Carlo. Toy, not benchmark evidence.
"""
import json
import numpy as np

SCALE0 = 1.0       # std of prior after object leaves view
TOL = 0.35         # grasp tolerance
SIG_LOOK = 0.30    # wrist-camera measurement noise
MOVE_STD = 0.50    # displacement when a human moves the object
MAX_LOOKS = 4
LAMBDA_STEP = 0.05  # value of one step in success units
N_EP = 30000


def posterior_std(sig):
    return 1.0 / np.sqrt(1.0 / sig**2 + 1.0 / SIG_LOOK**2)


def p_success(sig):
    # P(|estimate - x| < TOL) for estimate = posterior mean, error ~ N(0,sig^2)
    # (fractional; use normal cdf)
    from math import erf
    z = TOL / max(sig, 1e-9)
    return erf(z / np.sqrt(2.0))


def simulate2(hazard, policy, rng):
    x = rng.normal(0.0, 0.3, size=N_EP)       # true object position
    mu = np.zeros(N_EP)                        # belief mean (last seen = 0)
    sig = np.full(N_EP, SCALE0)
    steps = np.zeros(N_EP)
    looks = np.zeros(N_EP)
    done = np.zeros(N_EP, dtype=bool)
    success = np.zeros(N_EP, dtype=bool)

    for t in range(25):
        active = ~done
        if not active.any():
            break
        move = (rng.random(N_EP) < hazard) & active
        x = np.where(move, x + rng.normal(0.0, MOVE_STD, size=N_EP), x)

        p_act = np.array([p_success(s) for s in sig])
        sig_post = np.array([posterior_std(s) for s in sig])
        p_after = np.array([p_success(s) for s in sig_post])
        if policy == "nolook":
            look = np.zeros(N_EP, dtype=bool)
        elif policy == "always":
            look = active & (looks < MAX_LOOKS)
        else:
            look = active & (looks < MAX_LOOKS) & ((p_after - p_act) > LAMBDA_STEP)

        # observation update
        z = x + rng.normal(0.0, SIG_LOOK, size=N_EP)
        prec_prior = 1.0 / sig**2
        prec_obs = 1.0 / SIG_LOOK**2
        mu_post = (mu * prec_prior + z * prec_obs) / (prec_prior + prec_obs)
        sig_post_real = np.sqrt(1.0 / (prec_prior + prec_obs))
        mu = np.where(look, mu_post, mu)
        sig = np.where(look, sig_post_real, sig)

        act = active & ~look
        ok = np.abs(mu - x) <= TOL
        success = np.where(act, ok, success)
        done = done | act
        steps += active
        looks += look

        # if we somehow never act, force an act at t=20
        if t == 20:
            act = active
            ok = np.abs(mu - x) <= TOL
            success = np.where(act, ok, success)
            done = done | act
            steps += active
    return {
        "success": float(success.mean()),
        "steps": float(steps.mean()),
        "looks": float(looks.mean()),
        "success_per_step": float(success.mean() / max(steps.mean(), 1e-9)),
    }


rng = np.random.default_rng(7)
out = {"config": {"tol": TOL, "sig_look": SIG_LOOK, "move_std": MOVE_STD,
                  "lambda_step": LAMBDA_STEP, "n_ep": N_EP}, "hazards": {}}
for h in [0.0, 0.05, 0.15, 0.30]:
    out["hazards"][str(h)] = {}
    for pol in ["nolook", "always", "vol"]:
        out["hazards"][str(h)][pol] = simulate2(h, pol, rng)

with open("belief_results.json", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
