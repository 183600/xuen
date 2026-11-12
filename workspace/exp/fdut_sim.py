"""Synthetic mechanism check for FDUT (round 62: user-testing x fault-diagnosis).

NOT benchmark evidence. Isolates one question:
when a user's complaint ("too stiff / it slipped") is observationally
confounded between *intent mismatch* and *system fault*, does an explicit
fault-diagnostic observer + VOI-scheduled user-test/probe policy resolve the
confusion with less user burden than fixed schedules?

Generative model (declared, not fit):
  - intent i in {soft, firm}; fault f in {none, force_bias, mel_bias,
    actuator_gain, dms_misrule, tactile_stuck}; user reliability kappa in
    {0.6, 0.9}.
  - 6 residual channels r ~ N(mu(i,f), sigma^2 I). Intent shifts channel 0
    by +-0.8; force_bias shifts it by +2.5 -> the intended confusion.
  - ask returns a complaint y in {ok,bad} whose likelihood mixes the true
    "bad" probability with 0.5 by (1-kappa) (unreliable user).
  - probe_sensor separates {force_bias, actuator_gain, tactile_stuck};
    replay separates {mel_bias, dms_misrule}; neither separates intent.
  - repair removes the fault iff the MAP fault is correct, else may worsen.
  - success depends on intent match, residual fault, and fallback.
"""
import json
import math
import os
import random
import statistics

random.seed(20261112)

INTENTS = ["soft", "firm"]
FAULTS = ["none", "force_bias", "mel_bias", "actuator_gain",
          "dms_misrule", "tactile_stuck"]
KAPPAS = [0.6, 0.9]
SENSOR_FAULTS = {"force_bias", "actuator_gain", "tactile_stuck"}
MODEL_FAULTS = {"mel_bias", "dms_misrule"}
SEVERE = SENSOR_FAULTS | MODEL_FAULTS

SIG = {
    "none":          [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "force_bias":    [2.5, 0.0, 0.5, 0.0, 0.0, 0.0],
    "mel_bias":      [0.0, 2.5, 0.0, 1.0, 0.0, 0.0],
    "actuator_gain": [0.8, 0.0, 2.5, 0.0, 0.0, 0.0],
    "dms_misrule":   [0.0, 0.0, 0.0, 2.5, 1.0, 0.0],
    "tactile_stuck": [0.0, 0.5, 0.0, 0.0, 0.0, 2.5],
}
INTENT_SHIFT = 0.8
SIGMA = 1.0
COST = {"ask": 1.0, "probe": 2.0, "replay": 2.0, "repair": 1.5}


def normpdf(x, mu, sd):
    return math.exp(-0.5 * ((x - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))


def gauss_vec(r, mu, sd):
    p = 1.0
    for a, b in zip(r, mu):
        p *= normpdf(a, b, sd)
    return p


def intent_mu(i):
    v = [0.0] * 6
    v[0] = INTENT_SHIFT if i == "soft" else -INTENT_SHIFT
    return v


def state_mu(i, f):
    return [a + b for a, b in zip(intent_mu(i), SIG[f])]


def sample_state():
    i = random.choice(INTENTS)
    r = random.random()
    if r < 0.62:
        f = "none"
    else:
        f = random.choice(FAULTS[1:])
    kappa = random.choices(KAPPAS, weights=[0.35, 0.65])[0]
    return i, f, kappa


def emit_residual(i, f):
    mu = state_mu(i, f)
    return [random.gauss(m, SIGMA) for m in mu]


def bad_prob(i_true, f, i_plan):
    """True probability the user says 'bad' given latent state and plan."""
    p = 0.08
    if i_true != i_plan:
        p = 0.85 if i_true == "soft" else 0.60
    if f in SEVERE:
        p = max(p, 0.70)
    return p


def emit_user(i_true, f, kappa, i_plan):
    p = bad_prob(i_true, f, i_plan)
    p = kappa * p + (1.0 - kappa) * 0.5
    return "bad" if random.random() < p else "ok"


def emit_probe(f):
    p = 0.9 if f in SENSOR_FAULTS else 0.1
    return "abnormal" if random.random() < p else "normal"


def emit_replay(f):
    p = 0.9 if f in MODEL_FAULTS else 0.1
    return "abnormal" if random.random() < p else "normal"


# ----------------------------- belief -----------------------------
def prior_belief():
    b = {}
    for i in INTENTS:
        for f in FAULTS:
            pf = 0.62 if f == "none" else 0.38 / 5.0
            for k in KAPPAS:
                b[(i, f, k)] = 0.5 * pf * (0.35 if k == 0.6 else 0.65)
    return b


def normalize(b):
    s = sum(b.values())
    if s <= 0:
        return prior_belief()
    return {k: v / s for k, v in b.items()}


def update_residual(b, r):
    nb = {s: p * gauss_vec(r, state_mu(s[0], s[1]), SIGMA) for s, p in b.items()}
    return normalize(nb)


def marginal_fault(b):
    out = {f: 0.0 for f in FAULTS}
    for (i, f, k), p in b.items():
        out[f] += p
    return out


def marginal_intent(b):
    out = {i: 0.0 for i in INTENTS}
    for (i, f, k), p in b.items():
        out[i] += p
    return out


def entropy(b):
    return -sum(p * math.log(p + 1e-12) for p in b.values())


def likelihoods(b, action, i_plan):
    """Return {observation: probability} for a diagnostic action."""
    obs = {"ask": ["ok", "bad"], "probe": ["normal", "abnormal"],
           "replay": ["normal", "abnormal"]}[action]
    dist = {o: 0.0 for o in obs}
    for (i, f, k), p in b.items():
        if action == "ask":
            pb = k * bad_prob(i, f, i_plan) + (1.0 - k) * 0.5
            dist["bad"] += p * pb
            dist["ok"] += p * (1.0 - pb)
        elif action == "probe":
            pa = 0.9 if f in SENSOR_FAULTS else 0.1
            dist["abnormal"] += p * pa
            dist["normal"] += p * (1.0 - pa)
        else:
            pa = 0.9 if f in MODEL_FAULTS else 0.1
            dist["abnormal"] += p * pa
            dist["normal"] += p * (1.0 - pa)
    return dist


def post_update(b, action, o, i_plan):
    nb = {}
    for (i, f, k), p in b.items():
        if action == "ask":
            pb = k * bad_prob(i, f, i_plan) + (1.0 - k) * 0.5
            lik = pb if o == "bad" else (1.0 - pb)
        elif action == "probe":
            pa = 0.9 if f in SENSOR_FAULTS else 0.1
            lik = pa if o == "abnormal" else (1.0 - pa)
        else:
            pa = 0.9 if f in MODEL_FAULTS else 0.1
            lik = pa if o == "abnormal" else (1.0 - pa)
        nb[(i, f, k)] = p * lik
    return normalize(nb)


def expected_entropy(b, action, i_plan):
    dist = likelihoods(b, action, i_plan)
    return sum(p * entropy(post_update(b, action, o, i_plan))
               for o, p in dist.items() if p > 1e-12)


def best_action(b, i_plan):
    h = entropy(b)
    best, best_gain = None, 0.0
    for a in ("ask", "probe", "replay"):
        gain = (h - expected_entropy(b, a, i_plan)) / COST[a]
        if gain > best_gain:
            best, best_gain = a, gain
    return best, best_gain


def observe(action, i_true, f, kappa, i_plan):
    if action == "ask":
        return emit_user(i_true, f, kappa, i_plan)
    if action == "probe":
        return emit_probe(f)
    return emit_replay(f)


# ----------------------------- outcomes -----------------------------
def success_prob(i_true, i_plan, f, fallback):
    base = 0.95 if i_true == i_plan else (0.45 if i_true == "soft" else 0.40)
    if f in SEVERE:
        pen = {"force_bias": 0.30, "mel_bias": 0.25, "actuator_gain": 0.35,
               "dms_misrule": 0.30, "tactile_stuck": 0.30}[f]
        if fallback:
            pen *= 0.5
        base -= pen
    return max(0.05, base)


def run_episode(policy, budget=3):
    i_true, f_true, kappa = sample_state()
    r = emit_residual(i_true, f_true)
    b = update_residual(prior_belief(), r)
    i_plan = max(marginal_intent(b), key=marginal_intent(b).get)
    n_inter = 0
    fallback = False
    repaired = False
    attempts = []

    if policy == "no_diag":
        pass
    elif policy == "threshold":
        if math.sqrt(sum(x * x for x in r)) > 4.0:
            fallback = True
    elif policy == "random":
        for _ in range(budget):
            a = random.choice(["ask", "probe", "replay"])
            o = observe(a, i_true, f_true, kappa, i_plan)
            b = post_update(b, a, o, i_plan)
            n_inter += 1
    elif policy == "always_ask":
        for _ in range(min(2, budget)):
            o = observe("ask", i_true, f_true, kappa, i_plan)
            b = post_update(b, "ask", o, i_plan)
            n_inter += 1
    elif policy == "voi":
        while n_inter < budget:
            a, gain = best_action(b, i_plan)
            if a is None or gain < 0.08:
                break
            o = observe(a, i_true, f_true, kappa, i_plan)
            b = post_update(b, a, o, i_plan)
            n_inter += 1
            attempts.append(a)
            i_plan = max(marginal_intent(b), key=marginal_intent(b).get)

    # decision: repair if fault posterior strong, else execute
    mf = marginal_fault(b)
    mi = marginal_intent(b)
    f_map = max(mf, key=mf.get)
    i_plan = max(mi, key=mi.get)
    if policy in ("random", "always_ask", "voi") and f_map != "none" and mf[f_map] > 0.55:
        if f_map == f_true:
            repaired = True
            f_eff = "none"
        else:
            f_eff = f_true if f_true != "none" else random.choice(FAULTS[1:])
    else:
        f_eff = f_true

    if policy == "threshold" and fallback:
        pass

    p = success_prob(i_true, i_plan, f_eff, fallback)
    success = random.random() < p

    # safety violation: executed severe fault with high stiffness & no fallback
    safety = int((f_eff in {"force_bias", "actuator_gain"} and
                  i_plan == "firm" and not fallback))

    isolated = None
    if f_true != "none" and policy in ("random", "always_ask", "voi"):
        isolated = int(f_map == f_true)
    confused = None
    if f_true == "force_bias":
        confused = int(i_plan == i_true and f_map == "force_bias")

    return {
        "success": int(success), "safety": safety, "interventions": n_inter,
        "repaired": int(repaired), "isolated": isolated, "confused": confused,
        "fault": f_true,
    }


def summarize(rows, policy):
    n = len(rows)
    faults = [r for r in rows if r["fault"] != "none"]
    iso = [r["isolated"] for r in faults if r["isolated"] is not None]
    conf = [r["confused"] for r in rows if r["confused"] is not None]
    return {
        "policy": policy,
        "success": round(100.0 * sum(r["success"] for r in rows) / n, 1),
        "safety_viol": round(100.0 * sum(r["safety"] for r in rows) / n, 1),
        "interventions": round(statistics.mean(r["interventions"] for r in rows), 2),
        "isolation_top1": round(100.0 * sum(iso) / len(iso), 1) if iso else None,
        "confusion_resolved": round(100.0 * sum(conf) / len(conf), 1) if conf else None,
        "repair_rate": round(100.0 * sum(r["repaired"] for r in rows) / n, 1),
    }


# ----------------------- incipient-fault drift -----------------------
def drift_experiment(policy, steps=24, episodes=600):
    """Slow MEL bias ramps up; measure CUSUM detection latency."""
    lat = []
    fa = 0
    n_faulty = 0
    n_clean = 0
    for _ in range(episodes):
        faulty = random.random() < 0.5
        n_faulty += int(faulty)
        n_clean += int(not faulty)
        s = 0.0
        detected_at = None
        for t in range(steps):
            level = (t / steps) * 2.2 if faulty else 0.0
            x = random.gauss(level, 1.0)
            if policy == "cusum":
                s = max(0.0, s + x - 0.5)
                if s > 5.0:
                    detected_at = t
                    break
            else:  # single-threshold on instantaneous value
                if x > 2.0:
                    detected_at = t
                    break
        if faulty and detected_at is not None:
            lat.append(detected_at)
        if not faulty and detected_at is not None:
            fa += 1
    return {
        "policy": policy,
        "detect_rate": round(100.0 * len(lat) / max(1, n_faulty), 1),
        "mean_latency": round(statistics.mean(lat), 1) if lat else None,
        "false_alarm": round(100.0 * fa / max(1, n_clean), 1),
    }


if __name__ == "__main__":
    N = 6000
    policies = ["no_diag", "threshold", "random", "always_ask", "voi"]
    table = []
    for p in policies:
        rows = [run_episode(p) for _ in range(N)]
        table.append(summarize(rows, p))
    drift = [drift_experiment("cusum"), drift_experiment("threshold")]

    out = {"n": N, "episode_policies": table, "drift": drift}
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fdut_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
