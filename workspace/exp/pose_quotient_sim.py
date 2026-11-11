"""Toy mechanism check for symmetry-quotient pose certificates (round 55).

NOT benchmark evidence. Isolates one question:
When a 6D pose estimator is ambiguous across a physical symmetry (e.g. a
cylinder's yaw), should a safety certificate measure pose error in raw SE(3),
in the object-symmetry quotient SE(3)/G_obj, or in the *action-relevant*
quotient SE(3)/G_act?

Generative model (declared, not fit):
  - object: vertical cylinder, radius R = 0.05 m;
  - error state xi = (dt in R^3, dpsi in R);
  - a two-finger side grasp succeeds iff ||dt|| <= TAU_T and the yaw error
    modulo pi is <= TAU_PSI (the gripper is 180-degree symmetric);
  - hence the true action symmetry is G_act = {0, pi}, while the object
    symmetry is the full SO(2) (continuous yaw).
Three metrics:
  - raw   : d = sqrt(||dt||^2 + (R * wrap_pi(dpsi))^2)
  - obj   : d = ||dt||                         (quotient by SO(2))
  - act   : d = sqrt(||dt||^2 + (R * dist_pi(dpsi))^2)  (quotient by {0, pi})
For each metric we compute the largest *certified* radius eps such that every
pose within eps provably satisfies the success predicate (worst case over the
error set), then measure, on a held-out mixture of yaw modes:
  accept rate, false-reject-among-success, unsafe-accept (accept & fail).
"""
import json
import math
import random

R = 0.05
TAU_T = 0.015
TAU_PSI = math.radians(10.0)
N_TEST = 200_000
SEED = 20261111


def wrap_pi(x):
    return (x + math.pi) % (2.0 * math.pi) - math.pi


def dist_pi(x):
    y = x % math.pi
    return min(y, math.pi - y)


def d_raw(dt, dpsi):
    return math.hypot(math.sqrt(sum(v * v for v in dt)), R * wrap_pi(dpsi))


def d_obj(dt, dpsi):
    return math.sqrt(sum(v * v for v in dt))


def d_act(dt, dpsi):
    return math.hypot(math.sqrt(sum(v * v for v in dt)), R * dist_pi(dpsi))


def success(dt, dpsi):
    return (math.sqrt(sum(v * v for v in dt)) <= TAU_T
            and dist_pi(dpsi) <= TAU_PSI)


def certified_radius(metric, n_dir=400, n_r=400, r_max=0.25):
    """Largest r such that a dense worst-case shell at radius r succeeds."""
    # Candidate radii; for each, test the worst yaw within the yaw part of the
    # ball plus the translation boundary. Because success is monotone in the
    # distance to the nearest multiple of pi, it is enough to scan.
    def shell_all_succeed(r):
        # translation vectors on a sphere of radius r (yaw part zero)
        for i in range(n_dir):
            th = 2 * math.pi * i / n_dir
            # also off-axis translations: scan a few polar angles
            for ph in (0.0, math.pi / 4, math.pi / 2):
                dt = (r * math.sin(ph) * math.cos(th),
                      r * math.sin(ph) * math.sin(th), r * math.cos(ph))
                if not success(dt, 0.0):
                    return False
        # Only yaw error at radius r: translate the metric into yaw.
        # Solve metric(0, dpsi) = r on the relevant branch.
        for branch in (0.0, math.pi):
            lo, hi = 0.0, math.pi
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if metric((0.0, 0.0, 0.0), branch + mid) <= r:
                    lo = mid
                else:
                    hi = mid
            dpsi = branch + (lo if branch == 0.0 else mid)
            if not success((0.0, 0.0, 0.0), dpsi - branch if branch == 0.0 else dpsi):
                return False
        # Mixed boundary: translation and yaw simultaneously can break success
        # earlier only through the joint metric; scanning the two pure axes is
        # the conservative envelope for this separable predicate.
        return True

    best = 0.0
    for k in range(1, n_r + 1):
        r = r_max * k / n_r
        if shell_all_succeed(r):
            best = r
        else:
            break
    return best


def sample_error(rng):
    # mixture of estimator ambiguity modes: 0, pi, and a dangerous pi/2 mode
    u = rng.random()
    if u < 0.40:
        mode = 0.0
    elif u < 0.80:
        mode = math.pi
    else:
        mode = math.pi / 2.0
    dpsi = mode + rng.gauss(0.0, math.radians(8.0))
    dt = (rng.gauss(0.0, 0.004), rng.gauss(0.0, 0.004), rng.gauss(0.0, 0.004))
    return dt, dpsi


def evaluate(metric, eps, errors):
    acc = succ = false_rej = unsafe = 0
    for dt, dpsi in errors:
        ok = success(dt, dpsi)
        a = metric(dt, dpsi) <= eps
        acc += a
        succ += ok
        if ok and not a:
            false_rej += 1
        if a and not ok:
            unsafe += 1
    n = len(errors)
    return {
        "eps": eps,
        "accept_rate": acc / n,
        "success_rate": succ / n,
        "false_reject_among_success": false_rej / max(1, succ),
        "unsafe_accept_rate": unsafe / n,
        "accepted_and_success_rate": (acc - unsafe) / n,
    }


def main():
    rng = random.Random(SEED)
    errors = [sample_error(rng) for _ in range(N_TEST)]
    # Object quotient has no sound positive radius for this action because the
    # ball contains arbitrary yaw; use the naive translation-only radius.
    eps_obj = TAU_T
    out = {
        "seed": SEED,
        "n_test": N_TEST,
        "R": R,
        "tau_t": TAU_T,
        "tau_psi_deg": math.degrees(TAU_PSI),
        "yaw_mode_mixture": {"0": 0.40, "pi": 0.40, "pi/2": 0.20},
        "certified": {
            "raw": evaluate(d_raw, certified_radius(d_raw), errors),
            "obj_naive": evaluate(d_obj, eps_obj, errors),
            "act": evaluate(d_act, certified_radius(d_act), errors),
        },
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
