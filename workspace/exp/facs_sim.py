"""Round-16 (new inspiration cycle r1) synthetic mechanism check for FACS-VLA.

Three inspiration words this round:  VLA / 面部表情识别 (facial expression
recognition) / 伦理与合规 (ethics & compliance).

This file is NOT benchmark evidence. It is a *synthetic mechanism check* for
one claim and two supporting design analyses:

  CLAIM (C1).  Decomposing every one of the 32 tasks into a SHARED alphabet of
  "Manipulation Action Units" (AUs) -- the manipulation analogue of FACS action
  units -- gives the policy a per-AU failure signal. Using that signal for
  *local recovery at AU boundaries* raises both success rate and step score,
  and the gain grows when failures cluster in the early/middle AUs (which is
  exactly the pattern the published leaderboard shows: failed episodes earn
  only ~11.6/100 checkpoints; see exp/lb_headroom_r16_results.json).

  DESIGN ANALYSIS (A1).  The 32 official task names admit a compact shared AU
  alphabet; measure reuse, task length, and held-out composability.

  DESIGN ANALYSIS (A2).  A "compliance smoother" (hysteresis at AU boundaries +
  bounded switching + action low-pass) cuts action-stream jitter / switch rate
  with negligible task cost -- operationalising README section 6 ("keep
  latency stable, keep returned actions regular").

  SENSITIVITY (S1).  AU-boundary detection noise trades off against the C1 gain.

Everything is a declared generative toy model; nothing here fits a model of
real robot behaviour. Usage: python3 exp/facs_sim.py
"""
import json
import math
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# A1. Hand-authored AU decomposition of the 32 official UniBot-V1 tasks.
# AU tokens are the shared "muscles" of manipulation.
# ---------------------------------------------------------------------------
TASKS = [
    "Hang the Cup", "Fruit Basket Collection", "Pack the Doll", "Fruit Sorting",
    "Disconnect Ethernet", "Color Arrangement", "Place Photo Frames",
    "Organize Bookshelf", "Toolbox Storage", "Plug Charger", "Pick Out Battery",
    "Unlock", "Arrange Test Tubes", "Open Pill Bottle", "Organize Tools",
    "Fold Towel", "Organize Stationery", "Pack Bag", "Zip Up",
    "Paper Cup Stacking", "Clear Plates", "Spell robot", "Store Racket",
    "Conveyor Food Sorting", "Stack Cups", "Plug In Ethernet", "Stack Bowls",
    "Store Earphones", "Pack Phone", "Remove Pinned Note",
    "Organize Pencil Case", "Syringe Water Transfer",
]

PICKPLACE = ["APPROACH", "GRASP", "LIFT", "TRANSIT", "PLACE", "RELEASE"]
PICKINSERT = ["APPROACH", "GRASP", "LIFT", "TRANSIT", "INSERT", "RELEASE"]
PICKSTACK = ["APPROACH", "GRASP", "LIFT", "TRANSIT", "ALIGN", "DESCEND", "STACK", "RELEASE"]

AU_SEQ = {
    "Hang the Cup": ["APPROACH", "ALIGN", "HOOK", "RELEASE", "RETREAT"],
    "Fruit Basket Collection": PICKPLACE * 2 + ["RETREAT"],
    "Pack the Doll": PICKPLACE + ["RETREAT"],
    "Fruit Sorting": PICKPLACE * 2 + ["RETREAT"],
    "Disconnect Ethernet": ["APPROACH", "GRASP", "PULL", "LIFT", "RETREAT"],
    "Color Arrangement": PICKPLACE * 3 + ["RETREAT"],
    "Place Photo Frames": ["APPROACH", "ALIGN", "DESCEND", "PLACE", "RELEASE", "RETREAT"],
    "Organize Bookshelf": PICKPLACE * 2 + ["RETREAT"],
    "Toolbox Storage": PICKINSERT + ["RETREAT"],
    "Plug Charger": ["APPROACH", "ALIGN", "DESCEND", "INSERT", "SEAT", "RETREAT"],
    "Pick Out Battery": PICKPLACE + ["RETREAT"],
    "Unlock": ["APPROACH", "GRASP", "ROTATE", "PULL", "RELEASE"],
    "Arrange Test Tubes": PICKINSERT + ["RETREAT"],
    "Open Pill Bottle": ["APPROACH", "GRASP", "ROTATE", "LIFT", "RELEASE"],
    "Organize Tools": PICKPLACE + ["RETREAT"],
    "Fold Towel": ["APPROACH", "FOLD", "FOLD", "FLATTEN"],
    "Organize Stationery": PICKPLACE * 2 + ["RETREAT"],
    "Pack Bag": PICKINSERT + ["RETREAT"],
    "Zip Up": ["APPROACH", "GRASP", "ALIGN", "ZIP", "RELEASE"],
    "Paper Cup Stacking": PICKSTACK + ["RETREAT"],
    "Clear Plates": PICKPLACE * 2 + ["RETREAT"],
    "Spell robot": PICKPLACE * 4 + ["RETREAT"],
    "Store Racket": PICKPLACE + ["RETREAT"],
    "Conveyor Food Sorting": PICKPLACE * 2 + ["RETREAT"],
    "Stack Cups": PICKSTACK + ["RETREAT"],
    "Plug In Ethernet": ["APPROACH", "ALIGN", "DESCEND", "INSERT", "SEAT", "RETREAT"],
    "Stack Bowls": PICKSTACK + ["RETREAT"],
    "Store Earphones": PICKINSERT + ["RETREAT"],
    "Pack Phone": PICKINSERT + ["RETREAT"],
    "Remove Pinned Note": ["APPROACH", "GRASP", "PULL", "LIFT", "RETREAT"],
    "Organize Pencil Case": PICKINSERT + ["RETREAT"],
    "Syringe Water Transfer": ["APPROACH", "GRASP", "LIFT", "ALIGN", "POUR", "RETREAT"],
}

# Base competence of a *frozen* VLA per AU (declared, not fit). Hard AUs =
# precision/contact/deformable; easy AUs = free-space or open/close.
P_AU = {
    "APPROACH": 0.985, "ALIGN": 0.80, "HOOK": 0.72, "RELEASE": 0.97,
    "RETREAT": 0.98, "GRASP": 0.86, "LIFT": 0.94, "TRANSIT": 0.95,
    "PLACE": 0.84, "DESCEND": 0.91, "INSERT": 0.62, "SEAT": 0.66,
    "PULL": 0.82, "ROTATE": 0.68, "FOLD": 0.66, "FLATTEN": 0.80,
    "ZIP": 0.64, "STACK": 0.74, "POUR": 0.70,
}
# Per-AU "recovery gain": a bounded local retry + boundary re-observation may
# rescue a failed AU with this probability (hard contact AUs are easier to
# rescue with re-observation than with more force).
RESCUE = {
    "APPROACH": 0.5, "ALIGN": 0.7, "HOOK": 0.65, "RELEASE": 0.5, "RETREAT": 0.5,
    "GRASP": 0.7, "LIFT": 0.6, "TRANSIT": 0.6, "PLACE": 0.75, "DESCEND": 0.7,
    "INSERT": 0.55, "SEAT": 0.6, "PULL": 0.65, "ROTATE": 0.6, "FOLD": 0.5,
    "FLATTEN": 0.6, "ZIP": 0.5, "STACK": 0.7, "POUR": 0.6,
}

# ---------------------------------------------------------------------------
# A1 coverage analysis
# ---------------------------------------------------------------------------
def coverage_analysis():
    alpha = sorted({a for s in AU_SEQ.values() for a in s})
    lengths = [len(AU_SEQ[t]) for t in TASKS]
    reuse = {a: sum(1 for t in TASKS if a in AU_SEQ[t]) for a in alpha}
    # held-out composability: leave-one-task-out, is the task composed ONLY of
    # AUs that also occur in the remaining 31 tasks?
    coverable = 0
    for t in TASKS:
        others = {a for u in TASKS if u != t for a in AU_SEQ[u]}
        if all(a in others for a in AU_SEQ[t]):
            coverable += 1
    return {
        "n_unique_aus": len(alpha),
        "alphabet": alpha,
        "mean_task_len": round(st.mean(lengths), 2),
        "max_task_len": max(lengths),
        "mean_reuse": round(st.mean(reuse.values()), 2),
        "most_reused": sorted(reuse.items(), key=lambda kv: -kv[1])[:5],
        "heldout_tasks_covered_by_others": coverable,
        "n_tasks": len(TASKS),
    }


# ---------------------------------------------------------------------------
# B. Recovery simulation
# ---------------------------------------------------------------------------
# AUs that are real failure points; the rest are trivially reliable.
CRITICAL = {"ALIGN", "HOOK", "GRASP", "PLACE", "INSERT", "SEAT", "PULL",
            "ROTATE", "FOLD", "ZIP", "STACK", "POUR"}
# Position bias per failure-timing profile: multiplier on AU success in the
# first half vs second half of the sequence.
PROFILE_BIAS = {
    "observed_early": (0.86, 1.06),   # failures cluster early (leaderboard)
    "balanced":       (1.00, 1.00),
    "terminal":       (1.06, 0.86),   # failures cluster late
}


def simulate(strategy, n=40000, profile="observed_early", retries=2,
             det_noise=0.0, rng=None):
    """Toy episode model. All policies share the SAME per-AU competence; they
    differ only in what failure information they have and how they recover.

    - baseline implicit closed-loop rescue r0=0.15 applies to every policy
      (a generic VLA can sometimes recover a failed grasp by re-servoing).
    - AU-aware policies additionally DETECT the failure and re-gate the
      boundary (lower handoff hazard) and spend targeted retries.
    - retries cost switches (non-stationarity, relevant to README section 6)
      and a failed retry has a small chance of ending the episode.
    """
    rng = rng or random.Random(20261103)
    early_mult, late_mult = PROFILE_BIAS[profile]
    succ = 0
    step_frac = []
    switches = 0
    for _ in range(n):
        t = TASKS[rng.randrange(len(TASKS))]
        seq = AU_SEQ[t]
        L = len(seq)
        task_mult = min(1.0, max(0.4, 1.0 + rng.gauss(-0.05, 0.12)))
        if strategy == "vla_greedy":
            hazard, do_retry, banking = 0.05, False, False
        elif strategy == "au_boundary":
            hazard, do_retry, banking = 0.02, True, False
        elif strategy == "au_boundary_bank":
            hazard, do_retry, banking = 0.02, True, True
        else:
            raise ValueError(strategy)
        if rng.random() < det_noise:          # missed boundary -> no benefit
            hazard, do_retry = 0.05, False
        done = 0
        failed = False
        for i, a in enumerate(seq):
            pos = early_mult if i < L / 2 else late_mult
            p = P_AU[a] * task_mult * pos
            if not (a in CRITICAL):
                p = min(0.995, p + 0.14)
            if i > 0 and rng.random() < hazard:
                p -= 0.22
            p = max(0.0, min(0.995, p))
            if rng.random() < p:
                done += 1
                continue
            # --- failure at AU i ---
            if rng.random() < 0.35:            # generic closed-loop rescue
                done += 1
                continue
            if do_retry:
                budget = retries
                if banking and i < L / 2:
                    budget = retries + 1          # protect early progress
                if banking and i >= L - 1:
                    budget = max(1, retries - 1)  # do not destabilise the end
                rescued = False
                for r in range(budget):
                    switches += 1
                    if rng.random() < RESCUE[a] * 0.25 * (1.0 - 0.2 * r):
                        rescued = True
                        break
                    if rng.random() < 0.05:       # retry worsened the state
                        break
                if rescued:
                    done += 1
                    continue
            failed = True
            break
        if not failed and done == L:
            succ += 1
        step_frac.append(done / L)
    return {
        "success": succ / n,
        "step": st.mean(step_frac),
        "switches_per_ep": switches / n,
    }


def evaluate_recovery():
    rows = []
    for profile in ("observed_early", "balanced", "terminal"):
        rng = random.Random(7)
        b = simulate("vla_greedy", profile=profile, rng=random.Random(7))
        for strat in ("vla_greedy", "au_boundary", "au_boundary_bank"):
            r = simulate(strat, profile=profile, rng=random.Random(7))
            r.update(profile=profile, strategy=strat)
            for w in (0.0, 0.5, 1.0):
                r[f"combined_w{w}"] = w * r["success"] + (1 - w) * r["step"]
            rows.append(r)
    return rows


def evaluate_noise():
    rows = []
    for noise in (0.0, 0.1, 0.2, 0.35, 0.5):
        r = simulate("au_boundary_bank", det_noise=noise, rng=random.Random(11))
        rows.append({"det_noise": noise, **{k: round(v, 4) for k, v in r.items()}})
    return rows


# ---------------------------------------------------------------------------
# A2 compliance smoother
# ---------------------------------------------------------------------------
def compliance_smoother_sim(n_ep=4000, seed=3):
    """A mode/action stream with (i) a switch-rate cost and (ii) a jitter cost
    from switching. A hysteresis + low-pass wrapper reduces both. We measure
    the marginal task cost (a switch that could have rescued a failed AU is
    postponed past the recovery window) vs the jitter reduction."""
    rng = random.Random(seed)
    raw_switch, smooth_switch = [], []
    raw_jitter, smooth_jitter = [], []
    lost_rescues = 0
    for _ in range(n_ep):
        L = rng.randint(4, 14)
        modes = [rng.random() < 0.35 for _ in range(L)]  # want to switch?
        # raw: obey every want -> many switches, high jitter
        rs = sum(1 for i in range(1, L) if modes[i] != modes[i - 1])
        raw_switch.append(rs)
        raw_jitter.append(rs * rng.uniform(0.8, 1.2))
        # smoothed: hysteresis -> minimum dwell of 2 AU steps
        sm, last, dwell = [modes[0]], modes[0], 0
        for i in range(1, L):
            dwell += 1
            if dwell >= 2 and modes[i] != last:
                last, dwell = modes[i], 0
            sm.append(last)
        ss = sum(1 for i in range(1, L) if sm[i] != sm[i - 1])
        smooth_switch.append(ss)
        smooth_jitter.append(ss * rng.uniform(0.8, 1.2))
        lost_rescues += sum(1 for i in range(1, L) if modes[i] != sm[i])
    return {
        "switch_rate_raw": round(st.mean(raw_switch), 3),
        "switch_rate_smooth": round(st.mean(smooth_switch), 3),
        "switch_reduction": round(1 - st.mean(smooth_switch) / max(1e-9, st.mean(raw_switch)), 3),
        "jitter_raw": round(st.mean(raw_jitter), 3),
        "jitter_smooth": round(st.mean(smooth_jitter), 3),
        "deferred_corrections_per_ep": round(lost_rescues / n_ep, 3),
    }


def main():
    out = {}
    print("=" * 78)
    print("A1  shared AU alphabet over the 32 official tasks")
    print("=" * 78)
    a1 = coverage_analysis()
    out["A1_coverage"] = a1
    print(json.dumps(a1, ensure_ascii=False, indent=2))
    print("\nper-task AU sequences (length):")
    for t in TASKS:
        print(f"  {len(AU_SEQ[t]):2d}  {t:26s} {' '.join(AU_SEQ[t])}")

    print("\n" + "=" * 78)
    print("B  recovery simulation (success / step / combined)")
    print("=" * 78)
    rows = evaluate_recovery()
    out["B_recovery"] = rows
    hdr = f"{'profile':14s} {'strategy':18s} {'succ':>6} {'step':>6} " \
          f"{'w0(step)':>8} {'w.5':>6} {'w1(succ)':>8} {'sw/ep':>6}"
    print(hdr)
    for r in rows:
        print(f"{r['profile']:14s} {r['strategy']:18s} {r['success']:6.3f} "
              f"{r['step']:6.3f} {r['combined_w0.0']:8.3f} "
              f"{r['combined_w0.5']:6.3f} {r['combined_w1.0']:8.3f} "
              f"{r['switches_per_ep']:6.2f}")

    print("\n" + "=" * 78)
    print("S1  sensitivity to AU-boundary detection noise (au_boundary_bank)")
    print("=" * 78)
    noise = evaluate_noise()
    out["S1_noise"] = noise
    print(f"{'noise':>6} {'succ':>6} {'step':>6} {'sw/ep':>6}")
    for r in noise:
        print(f"{r['det_noise']:6.2f} {r['success']:6.3f} {r['step']:6.3f} "
              f"{r['switches_per_ep']:6.2f}")

    print("\n" + "=" * 78)
    print("A2  compliance smoother (hysteresis/low-pass on the mode stream)")
    print("=" * 78)
    a2 = compliance_smoother_sim()
    out["A2_compliance"] = a2
    print(json.dumps(a2, ensure_ascii=False, indent=2))

    path = os.path.join(HERE, "facs_results.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
