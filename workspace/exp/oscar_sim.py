"""Synthetic mechanism check for OSCAR (round 61).

NOT benchmark evidence.  Isolates one question:
with open-source components running behind transactional state isolation,
can a deterministic counterfactual replay attribute a safety violation to
the *causing* component (and expose the component that masks it), where a
round-60-style reactive telemetry baseline cannot?

Declared generative model (not fit to data):
  - a 6-stage tracking pipeline; every stage is an "open-source component"
    with hidden mutable state.  Each stage has a certified reference
    implementation (ref) and a live implementation (live) that may carry an
    injected fault at cycle t0.
  - pipeline: sensor_bridge -> frame_calib -> state_estimator ->
    trajectory_gen -> impedance_ctrl -> telemetry_sender.
  - the plant tracks a moving setpoint; the controller integrates the
    tracking error, so a component fault turns into integrator wind-up and
    finally an impedance-force envelope violation |F| > F_MAX.
  - faults: 'calib' (scale jump), 'stale' (estimator returns a frozen
    measurement), 'gain' (trajectory gain drift), 'nan' (non-finite cmd),
    'clip' (controller clamps its output: a MASKER that hides the
    violation behind a saturated safety envelope).
  - observation regimes:
      opaque      - only the end-to-end EV telemetry is observed
                    (third-party internals are black boxes)
      observable  - every component topic is logged and a golden
                    reference trace exists (only possible for components
                    whose behaviour we already certified)
  - ref coverage: set of components for which a certified reference
    implementation exists.  Counterfactual attribution needs it.

Everything is deterministic given the seed: external inputs are recorded
in the trace, so replay uses recorded values, not regenerated ones.
"""
import json
import math
import os
import random
import statistics

CIDS = ["c0_sensor", "c1_frame", "c2_est", "c3_traj", "c4_ctrl", "c5_telem"]
DEPTH = {cid: i for i, cid in enumerate(CIDS)}          # upstream -> downstream
F_MAX = 1.5
EPS_ADMIT = 0.02                                        # fingerprint admission threshold
EPS_DEV = 0.02                                          # shadow deviation threshold
N_CYCLES = 240
T0 = 20


def setpoint(t):
    return 0.5 + 0.4 * math.sin(0.05 * t)


def raw_signal(t, rng):
    return setpoint(t) + 0.02 * math.sin(0.5 * t) + 0.003 * rng.gauss(0.0, 1.0)


# --------------------------------------------------------------------------
# components: ref_step is the certified behaviour, live_step may carry a fault
# --------------------------------------------------------------------------
def init_state(cid):
    return {
        "c0_sensor": {"ema": 0.5},
        "c1_frame": {"scale": 1.0},
        "c2_est": {"buf": 0.5},
        "c3_traj": {"phase": 0.0},
        "c4_ctrl": {"integral": 0.0},
        "c5_telem": {"n": 0},
    }[cid].copy()


def ref_step(cid, state, x, t):
    """Certified reference behaviour.  Returns (new_state, output)."""
    s = dict(state)
    if cid == "c0_sensor":
        s["ema"] = 0.7 * x + 0.3 * s["ema"]
        out = s["ema"]
    elif cid == "c1_frame":
        out = x * s["scale"]
    elif cid == "c2_est":
        out = 0.8 * x + 0.2 * s["buf"]
        s["buf"] = x
    elif cid == "c3_traj":
        s["phase"] += 0.2
        out = x
    elif cid == "c4_ctrl":
        err = x - setpoint(t)
        s["integral"] = 0.99 * s["integral"] + 0.01 * err
        out = 6.0 * s["integral"]
    else:
        s["n"] += 1
        out = x
    return s, out


def live_step(cid, state, x, t, faults):
    """Live behaviour; faults is a dict cid -> (kind, t0)."""
    kind = None
    f = faults.get(cid)
    if f is not None and t >= f[1]:
        kind = f[0]
    s = dict(state)
    if cid == "c0_sensor":
        s["ema"] = 0.7 * x + 0.3 * s["ema"]
        out = s["ema"]
    elif cid == "c1_frame":
        if kind == "calib":
            s["scale"] = 1.6
        out = x * s["scale"]
    elif cid == "c2_est":
        if kind == "stale":
            if "frozen" not in s:
                s["frozen"] = s["buf"]
            out = s["frozen"]
        else:
            out = 0.8 * x + 0.2 * s["buf"]
            s["buf"] = x
    elif cid == "c3_traj":
        s["phase"] += 0.2
        if kind == "nan":
            out = float("nan")
        elif kind == "gain":
            out = 1.8 * x
        else:
            out = x
    elif cid == "c4_ctrl":
        err = x - setpoint(t)
        s["integral"] = 0.99 * s["integral"] + 0.01 * err
        out = 6.0 * s["integral"]
        if kind == "clip":
            out = F_MAX if math.isnan(out) else min(out, F_MAX)
    else:
        s["n"] += 1
        out = x
    return s, out


def norm_dev(a, b):
    if math.isnan(a) or math.isnan(b):
        return float("inf")
    return abs(a - b) / (1.0 + abs(b))


# --------------------------------------------------------------------------
# episode execution: live loop + shadow reference lane
# --------------------------------------------------------------------------
def run_episode(rng, faults, n_cycles=N_CYCLES, shadow=True):
    live = {cid: init_state(cid) for cid in CIDS}
    ref = {cid: init_state(cid) for cid in CIDS}
    trace = {"raw": [], "outs": [], "refouts": [], "dev": [], "force": []}
    deviating = set()
    first_violation = None
    for t in range(n_cycles):
        x = raw_signal(t, rng)
        trace["raw"].append(x)
        outs, refs, devs = {}, {}, {}
        sig_live, sig_ref = x, x
        for cid in CIDS:
            live[cid], o_live = live_step(cid, live[cid], sig_live, t, faults)
            o_ref = None
            if shadow:
                ref[cid], o_ref = ref_step(cid, ref[cid], sig_ref, t)
                d = norm_dev(o_live, o_ref)
                devs[cid] = d
                if d > EPS_DEV:
                    deviating.add(cid)
            outs[cid] = o_live
            refs[cid] = o_ref
            sig_live = o_live
            sig_ref = o_ref if o_ref is not None else sig_ref
        f = outs["c4_ctrl"]
        trace["outs"].append(outs)
        trace["refouts"].append(refs)
        trace["dev"].append(devs)
        trace["force"].append(f)
        if first_violation is None and (math.isnan(f) or abs(f) > F_MAX):
            first_violation = t
    return {"trace": trace, "deviating": deviating, "first_violation": first_violation}


def replay(trace, interventions, faults):
    """Deterministic replay with do(cid := ref) interventions.

    Runs a shadow reference lane alongside, so the proactive signal
    (deviation set) is recomputed under the intervention.
    """
    live = {cid: init_state(cid) for cid in CIDS}
    ref = {cid: init_state(cid) for cid in CIDS}
    forces = []
    deviating = set()
    first = None
    for t in range(len(trace["raw"])):
        x = trace["raw"][t]
        outs = {}
        sig_live, sig_ref = x, x
        for cid in CIDS:
            if cid in interventions:
                live[cid], outs[cid] = ref_step(cid, live[cid], sig_live, t)
            else:
                live[cid], outs[cid] = live_step(cid, live[cid], sig_live, t, faults)
            ref[cid], o_ref = ref_step(cid, ref[cid], sig_ref, t)
            if norm_dev(outs[cid], o_ref) > EPS_DEV:
                deviating.add(cid)
            sig_live = outs[cid]
            sig_ref = o_ref
        f = outs["c4_ctrl"]
        forces.append(f)
        if first is None and (math.isnan(f) or abs(f) > F_MAX):
            first = t
    return {"violated": first is not None, "first": first,
            "forces": forces, "deviating": deviating}


# --------------------------------------------------------------------------
# OSCAR-M: deviation-localised counterfactual causal peeling
# --------------------------------------------------------------------------
def suppresses(trace, cid):
    """Signature pre-filter for MASKER candidates.

    A masker hides an upstream violation.  Its observable signature against
    the reference world is a *saturated / frozen* output: the live output
    sticks to a constant (a clamp, a frozen buffer, a NaN sanitiser) while
    the reference output keeps moving.  We also accept the direct case
    where the live magnitude is attenuated relative to the reference.
    """
    prev = None
    flat = 0
    for outs, refs in zip(trace["outs"], trace["refouts"]):
        lo, ro = outs.get(cid), refs.get(cid)
        if lo is None or ro is None:
            prev = lo
            continue
        if math.isnan(lo) and not math.isnan(ro):
            return True
        if math.isnan(lo) or math.isnan(ro):
            prev = lo
            continue
        if abs(lo) < abs(ro) - 1e-9:
            return True
        if prev is not None and abs(lo - prev) <= 1e-9 and abs(ro - lo) > 1e-6:
            flat += 1
        prev = lo
    return flat >= 2


def cfa_m(trace, deviating, ref_coverage, mode, base_violation=None, faults=None):
    """Upstream-first necessity pass + downstream-first masker pass.

    mode='reactive'  : the fault signal is the end-to-end EV violation
    mode='proactive' : the fault signal is the shadow deviation set
                       (used when a masker hides the EV violation)
    """
    candidates = [cid for cid in CIDS
                  if cid in deviating and cid in ref_coverage]
    replays = 0
    cause = None
    # --- necessity pass: upstream first (a cause is upstream of its effects)
    for cid in candidates:
        res = replay(trace, {cid}, faults)
        replays += 1
        if mode == "reactive":
            removed = not res["violated"]
        else:
            removed = not res["deviating"]
        if removed:
            cause = cid
            break
    unresolved = cause is None
    maskers = []
    if cause is not None:
        # --- masker pass: keep the cause live, revert downstream suspects
        for cid in reversed([c for c in CIDS if c in deviating and c in ref_coverage]):
            if DEPTH[cid] <= DEPTH[cause]:
                continue
            if not suppresses(trace, cid):
                continue
            res = replay(trace, {cid}, faults)
            replays += 1
            base = base_violation
            if res["violated"] and base is None:
                maskers.append(cid)          # reverting it reveals a hidden violation
            elif res["violated"] and base is not None:
                if abs(res["forces"][base]) - abs(trace["force"][base]) > 0.5 * F_MAX:
                    maskers.append(cid)      # reverting it changes the magnitude a lot
    return {"cause": cause, "maskers": maskers, "replays": replays,
            "unresolved": unresolved}


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------
def baseline_reactive(ep, observable=False):
    """Round-60 style: only end-to-end EV telemetry (+ timestamps).

    In the opaque regime the only observable topic is the telemetry
    itself, so the heuristic always lands on the last internal stage.
    """
    if ep["first_violation"] is None:
        return {"cause": None, "maskers": [], "replays": 0, "detected": False}
    if observable:
        devs = [cid for cid in CIDS if cid in ep["deviating"]]
        return {"cause": devs[0] if devs else None, "maskers": [],
                "replays": 0, "detected": True}
    return {"cause": "c4_ctrl", "maskers": [], "replays": 0, "detected": True}


# --------------------------------------------------------------------------
# E192: behavioural fingerprint admission gate
# --------------------------------------------------------------------------
def behavioral_distance(fa, fb):
    worst = 0.0
    for a, b in zip(fa, fb):
        if math.isnan(a) or math.isnan(b):
            return float("inf")
        worst = max(worst, abs(a - b) / (1.0 + abs(b)))
    return worst


def admission_gate():
    suite = [round(-1.0 + 0.05 * i, 3) for i in range(41)]
    holdout = [round(-1.0 + 0.037 * i, 3) for i in range(55)]

    def base(x):
        return 0.7 * x + 0.3 * math.tanh(x)

    def benign(x):                       # rename + extra log + reordering
        return 0.7 * x + 0.3 * math.tanh(x)

    def semantic(x):                     # gain drift
        return 1.08 * (0.7 * x + 0.3 * math.tanh(x))

    def adversarial(x):                  # identical on the suite, differs off-suite
        if abs(x * 20 - round(x * 20)) < 1e-9:
            return base(x)
        return base(x) + 0.4 * math.sin(11.0 * x)

    rows = []
    for name, patch in (("benign_refactor", benign),
                        ("semantic_patch", semantic),
                        ("adversarial_patch", adversarial)):
        d_suite = behavioral_distance([patch(x) for x in suite],
                                      [base(x) for x in suite])
        d_hold = behavioral_distance([patch(x) for x in holdout],
                                     [base(x) for x in holdout])
        rows.append({"patch": name,
                     "d_F_suite": round(d_suite, 6),
                     "d_F_holdout": round(d_hold, 6),
                     "admitted": d_suite <= EPS_ADMIT,
                     "behaviour_changed_offsuite": d_hold > EPS_ADMIT})
    return rows


# --------------------------------------------------------------------------
# E193: state isolation and hidden channels
# --------------------------------------------------------------------------
def isolation_check(n=400, seed=7):
    rng = random.Random(seed)
    mediated = 0
    hidden = 0
    os_detected = 0
    for _ in range(n):
        if rng.random() < 0.4:
            mediated += 1                      # write goes through the broker
        else:
            hidden += 1                        # write smuggled through a global
            if rng.random() < 0.97:            # OS audit coverage (audit gaps)
                os_detected += 1
    return {
        "episodes": n,
        "broker_mediated_writes": mediated,
        "hidden_channel_writes": hidden,
        "hidden_channel_detection_rate_ISOL1": 0.0,
        "hidden_channel_detection_rate_ISOL2": round(os_detected / hidden, 3),
        "note": "ISOL-1 tracks only broker-mediated writes, so a global write "
                "is invisible; ISOL-2 adds an OS-level side-effect audit and "
                "catches it except for a small audit gap",
    }


# --------------------------------------------------------------------------
# E194-E197: attribution experiments
# --------------------------------------------------------------------------
FAULTS = ["calib", "stale", "gain", "nan"]
CAUSE_CID = {"calib": "c1_frame", "stale": "c2_est",
             "gain": "c3_traj", "nan": "c3_traj"}


def attribution_experiment(n_episodes=200, ref_coverage=None, seed=11):
    rng = random.Random(seed)
    ref_cov = set(CIDS) if ref_coverage is None else set(ref_coverage)
    stats = {}
    for scen in ("single", "masked"):
        n_det_reactive = 0
        n_det_proactive = 0
        n_confirmed = 0
        n_confirmed_correct = 0
        n_unresolved = 0
        n_window_contains = 0
        n_masker_found = 0
        n_masker_total = 0
        quarantine_sizes = []
        replays = []
        base_detected = 0
        base_correct = 0
        for _ in range(n_episodes):
            cause_kind = rng.choice(FAULTS)
            faults = {CAUSE_CID[cause_kind]: (cause_kind, T0)}
            if scen == "masked":
                faults["c4_ctrl"] = ("clip", T0)
            ep = run_episode(rng, faults)
            tr = ep["trace"]
            truth = CAUSE_CID[cause_kind]

            # baseline: reactive telemetry only (opaque third-party internals)
            b = baseline_reactive(ep, observable=False)
            if b["detected"]:
                base_detected += 1
                if b["cause"] == truth:
                    base_correct += 1

            reactive_signal = ep["first_violation"] is not None
            if reactive_signal:
                n_det_reactive += 1
            if ep["deviating"]:
                n_det_proactive += 1
            mode = "reactive" if reactive_signal else "proactive"
            res = cfa_m(tr, ep["deviating"], ref_cov, mode,
                        base_violation=ep["first_violation"], faults=faults)
            replays.append(res["replays"])
            if res["unresolved"]:
                n_unresolved += 1
                # honest fallback: quarantine the whole suspect window
                window = sorted((c for c in CIDS if c in ep["deviating"]),
                                key=lambda c: DEPTH[c])
                quarantine_sizes.append(len(window))
                if truth in window:
                    n_window_contains += 1
            else:
                quarantine_sizes.append(1)
                n_confirmed += 1
                if res["cause"] == truth:
                    n_confirmed_correct += 1
            if scen == "masked":
                n_masker_total += 1
                if "c4_ctrl" in res["maskers"]:
                    n_masker_found += 1
        stats[scen] = {
            "episodes": n_episodes,
            "reactive_detection_rate": round(n_det_reactive / n_episodes, 3),
            "proactive_detection_rate": round(n_det_proactive / n_episodes, 3),
            "confirmed_attribution_top1": round(n_confirmed_correct / n_episodes, 3),
            "confirmed_rate": round(n_confirmed / n_episodes, 3),
            "unresolved_rate": round(n_unresolved / n_episodes, 3),
            "fallback_window_contains_cause": round(n_window_contains / n_episodes, 3),
            "masker_identified_rate": (round(n_masker_found / n_masker_total, 3)
                                       if n_masker_total else None),
            "mean_replays": round(statistics.mean(replays), 3),
            "mean_quarantine_size": round(statistics.mean(quarantine_sizes), 3),
            "baseline_reactive_detected": round(base_detected / n_episodes, 3),
            "baseline_reactive_top1": round(base_correct / n_episodes, 3),
        }
    return stats


if __name__ == "__main__":
    out = {}
    print("=== E192 admission gate (behavioural fingerprint) ===")
    rows = admission_gate()
    out["E192_admission"] = rows
    for r in rows:
        print(" ", r)

    print("\n=== E193 state isolation / hidden channel ===")
    iso = isolation_check()
    out["E193_isolation"] = iso
    print(" ", iso)

    print("\n=== E194/E195/E196 attribution (full ref coverage) ===")
    full = attribution_experiment(200, None, seed=11)
    out["E194_attribution_full_ref"] = full
    for scen, r in full.items():
        print(f"  [{scen}] {r}")

    print("\n=== E197 partial ref coverage (only c0,c1,c4 certified) ===")
    part = attribution_experiment(200, {"c0_sensor", "c1_frame", "c4_ctrl"}, seed=23)
    out["E197_attribution_partial_ref"] = part
    for scen, r in part.items():
        print(f"  [{scen}] {r}")

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "oscar_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print("\nwrote", path)
