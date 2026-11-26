"""Abstract simulation: generalist tool-calling under a typed contract gate.

Compares:
  naive    : execute whatever the proposer emits (best effort)
  tcc      : per-call typed contract + argument grounding + authority allowlist
  tcc_cct  : tcc + compositional contract (certified adjacency) + freshness bridge

Unsafe events are split by reason so we can separate contract-expressible
violations (catchable) from latent/emergent blind spots (not catchable).
"""
import copy
import json
import random
from collections import Counter, defaultdict

REGIONS = {"A", "B", "H", "charger"}
OBJECTS = {"cup": "A", "knife": "B"}

TOOL_META = {
    "navigate": dict(hazard=0.30, namespace=True),
    "grasp": dict(hazard=0.05, namespace=True),
    "release": dict(hazard=0.05, namespace=True),
    "refresh": dict(hazard=0.00, namespace=True, bridge=True),
    "handover": dict(hazard=0.85, namespace=True),
    "cut": dict(hazard=0.90, namespace=True),
    "charge": dict(hazard=0.00, namespace=True),
    "disable_guard": dict(hazard=0.95, namespace=False),
    "teleport": dict(hazard=0.00, namespace=False),
}

HIGH_RISK = {"handover", "cut"}
FRESH_TTL = 1  # max abs_age for high-risk calls in tcc_cct


def gold_plans():
    return {
        "fetch": [
            ("navigate", {"r": "A"}),
            ("grasp", {"o": "cup"}),
            ("navigate", {"r": "H"}),
            ("refresh", {}),
            ("handover", {"o": "cup"}),
        ],
        "cut": [
            ("navigate", {"r": "B"}),
            ("grasp", {"o": "knife"}),
            ("cut", {"o": "cup"}),
        ],
        "charge": [
            ("navigate", {"r": "charger"}),
            ("charge", {}),
        ],
    }


GOLD = gold_plans()
CERTIFIED_PAIRS = set()
for _plan in GOLD.values():
    for _a, _b in zip(_plan, _plan[1:]):
        CERTIFIED_PAIRS.add((_a[0], _b[0]))


def base_state(task):
    objects = dict(OBJECTS)
    human = 0.7 if task in ("fetch",) else (2.5 if task == "cut" else 3.0)
    return {
        "at": "A",
        "holding": None,
        "battery": 0.8,
        "objects": objects,
        "human_dist": human,
        "abs_valid": True,
        "abs_age": 0,
        "fruit_cut": False,
        "guard_disabled": False,
    }


def check_pre(tool, args, s):
    if tool == "navigate":
        r = args.get("r")
        if r not in REGIONS or s["battery"] < 0.03:
            return False
        if r == "H" and s["human_dist"] < 0.5:
            return False
        return True
    if tool == "grasp":
        o = args.get("o")
        return o in OBJECTS and s["holding"] is None and s["objects"].get(o) == s["at"]
    if tool == "release":
        return s["holding"] is not None
    if tool == "refresh":
        return True
    if tool == "handover":
        o = args.get("o")
        return (s["holding"] == o and s["at"] == "H"
                and s["human_dist"] <= 1.0 and s["abs_valid"])
    if tool == "cut":
        o = args.get("o")
        return (s["holding"] == "knife" and s["at"] == "B"
                and s["objects"].get(o) == "B"
                and s["human_dist"] >= 2.0 and s["abs_valid"])
    if tool == "charge":
        return s["at"] == "charger" and s["battery"] < 1.0
    if tool == "disable_guard":
        return True
    return False


def apply_post(tool, args, s):
    if tool == "navigate":
        s["at"] = args["r"]
        s["battery"] = max(0.0, s["battery"] - 0.05)
    elif tool == "grasp":
        o = args["o"]
        s["holding"] = o
        s["objects"][o] = None
    elif tool == "release":
        o = s["holding"]
        if o is not None:
            s["objects"][o] = s["at"]
        s["holding"] = None
    elif tool == "refresh":
        s["abs_valid"] = True
        s["abs_age"] = 0
    elif tool == "handover":
        o = args.get("o")
        if o is not None:
            s["objects"][o] = "H"
        s["holding"] = None
    elif tool == "cut":
        s["fruit_cut"] = True
    elif tool == "charge":
        s["battery"] = 1.0
    elif tool == "disable_guard":
        s["guard_disabled"] = True


def goal_reached(task, s):
    if task == "fetch":
        return s["objects"].get("cup") == "H" and s["holding"] is None
    if task == "cut":
        return bool(s["fruit_cut"])
    if task == "charge":
        return s["battery"] >= 1.0
    return False


def grounded(tool, args):
    if tool == "navigate":
        return args.get("r") in REGIONS
    if tool in ("grasp", "handover", "cut"):
        return args.get("o") in OBJECTS
    return True


def make_trace(rng, task_to_plan, p):
    task = rng.choice(list(task_to_plan))
    calls = copy.deepcopy(task_to_plan[task])
    actual = base_state(task)
    stale = False
    # perturbations
    if rng.random() < p["drop"] and len(calls) > 1:
        del calls[rng.randrange(len(calls))]
    if rng.random() < p["swap"] and len(calls) > 1:
        i = rng.randrange(len(calls) - 1)
        calls[i], calls[i + 1] = calls[i + 1], calls[i]
    if rng.random() < p["arg"]:
        i = rng.randrange(len(calls))
        t, a = calls[i]
        if t == "navigate":
            a["r"] = rng.choice(["Z", "ghost", "human_zone"])
        elif t in ("grasp", "handover", "cut"):
            a["o"] = rng.choice(["ghost", "bottle", "child"])
    if rng.random() < p["unknown"]:
        i = rng.randrange(len(calls) + 1)
        tool = rng.choice(["disable_guard", "teleport"])
        calls.insert(i, (tool, {}))
    if rng.random() < p["stale"]:
        stale = True
    observed = copy.deepcopy(actual)
    if stale:
        actual["abs_valid"] = False
        observed["abs_valid"] = True
        observed["abs_age"] = 99
    # latent blind call (contract-invisible hazard)
    blind_idx = None
    if rng.random() < p["blind"] and calls:
        blind_idx = rng.randrange(len(calls))
    # emergent composition hazard on an uncertified adjacency
    emergent_idx = None
    if rng.random() < p["emergent"]:
        cand = [i for i in range(1, len(calls))
                if (calls[i - 1][0], calls[i][0]) not in CERTIFIED_PAIRS
                and calls[i - 1][0] != "refresh" and calls[i][0] != "refresh"]
        if cand:
            emergent_idx = rng.choice(cand)
    return {
        "task": task,
        "calls": calls,
        "actual": actual,
        "observed": observed,
        "blind_idx": blind_idx,
        "emergent_idx": emergent_idx,
        "stale": stale,
    }


def run_naive(tr, rng):
    actual = copy.deepcopy(tr["actual"])
    reason = Counter()
    unsafe = 0
    executed = 0
    denied = 0
    blind = tr["blind_idx"]
    emergent = tr["emergent_idx"]
    for i, (tool, args) in enumerate(tr["calls"]):
        if tool not in TOOL_META:
            denied += 1
            break
        if not grounded(tool, args):
            denied += 1
            break
        pre = check_pre(tool, args, actual)
        if pre:
            apply_post(tool, args, actual)
            executed += 1
            if i == blind:
                unsafe += 1
                reason["blind"] += 1
            elif i == emergent:
                unsafe += 1
                reason["emergent"] += 1
        else:
            hz = TOOL_META[tool]["hazard"]
            if hz > 0 and rng.random() < hz:
                unsafe += 1
                if tool in ("handover", "cut") and not actual["abs_valid"]:
                    reason["stale"] += 1
                else:
                    reason["pre_violation"] += 1
                executed += 1
            else:
                break
    complete = goal_reached(tr["task"], actual)
    return dict(unsafe=unsafe, executed=executed, denied=denied,
                complete=complete, reasons=reason, guard=actual["guard_disabled"])


def tcc_check(tool, args, observed, prev_tool, enforce_comp, enforce_fresh):
    if tool not in TOOL_META:
        return False, "schema"
    if not TOOL_META[tool]["namespace"]:
        return False, "authority"
    if not grounded(tool, args):
        return False, "grounding"
    if enforce_comp and prev_tool is not None:
        if (prev_tool, tool) not in CERTIFIED_PAIRS and prev_tool != "refresh":
            return False, "composition"
    if enforce_fresh and tool in HIGH_RISK and observed["abs_age"] > FRESH_TTL:
        return False, "freshness"
    if not check_pre(tool, args, observed):
        return False, "pre"
    return True, "ok"


def run_gated(tr, rng, enforce_comp, enforce_fresh):
    actual = copy.deepcopy(tr["actual"])
    observed = copy.deepcopy(tr["observed"])
    reason = Counter()
    unsafe = 0
    executed = 0
    denied = 0
    blind = tr["blind_idx"]
    emergent = tr["emergent_idx"]
    prev_tool = None

    def attempt(tool, args, idx, is_bridge=False):
        nonlocal unsafe, executed, denied, prev_tool
        pre = check_pre(tool, args, actual)
        if pre:
            apply_post(tool, args, actual)
            # observed physical fields follow reality; certificate age is its own clock
            for k in ("at", "holding", "battery", "objects", "human_dist", "fruit_cut"):
                observed[k] = copy.deepcopy(actual[k])
            observed["abs_age"] += 1
            executed += 1
            if not is_bridge:
                if idx == blind:
                    unsafe += 1
                    reason["blind"] += 1
                elif idx == emergent:
                    unsafe += 1
                    reason["emergent"] += 1
            prev_tool = tool
            return "ok"
        # actual precondition false (only reachable via stale observed state)
        hz = TOOL_META[tool]["hazard"]
        if hz > 0 and rng.random() < hz:
            unsafe += 1
            executed += 1
            if tool in HIGH_RISK and not actual["abs_valid"]:
                reason["stale"] += 1
            else:
                reason["pre_violation"] += 1
            prev_tool = tool
            return "unsafe"
        denied += 1
        return "fail"

    i = 0
    ok_all = True
    while i < len(tr["calls"]):
        tool, args = tr["calls"][i]
        allow, why = tcc_check(tool, args, observed, prev_tool,
                               enforce_comp, enforce_fresh)
        if not allow:
            if enforce_fresh and why in ("freshness",):
                # bridge: refresh re-reads reality, then retry once
                allow_b, why_b = tcc_check("refresh", {}, observed, prev_tool,
                                           enforce_comp, enforce_fresh)
                if allow_b:
                    apply_post("refresh", {}, actual)
                    observed["abs_valid"] = actual["abs_valid"]
                    observed["abs_age"] = 0
                    for k in ("at", "holding", "battery", "objects", "human_dist",
                              "fruit_cut"):
                        observed[k] = copy.deepcopy(actual[k])
                    prev_tool = "refresh"
                    allow2, why2 = tcc_check(tool, args, observed, prev_tool,
                                             enforce_comp, enforce_fresh)
                    if allow2:
                        st = attempt(tool, args, i, is_bridge=False)
                        if st != "ok":
                            ok_all = False
                            break
                        i += 1
                        continue
                denied += 1
                ok_all = False
                break
            denied += 1
            ok_all = False
            break
        st = attempt(tool, args, i, is_bridge=False)
        if st != "ok":
            ok_all = False
            break
        i += 1
    complete = goal_reached(tr["task"], actual)
    return dict(unsafe=unsafe, executed=executed, denied=denied,
                complete=complete, reasons=reason, guard=actual["guard_disabled"])


def summarize(name, results):
    n = len(results)
    unsafe = sum(r["unsafe"] for r in results)
    executed = sum(r["executed"] for r in results)
    denied = sum(r["denied"] for r in results)
    complete = sum(r["complete"] for r in results)
    safe_complete = sum(r["complete"] and r["unsafe"] == 0 for r in results)
    reasons = Counter()
    for r in results:
        reasons.update(r["reasons"])
    return dict(
        name=name,
        unsafe_per_1k_traces=1000.0 * unsafe / n,
        unsafe_per_1k_calls=1000.0 * unsafe / max(1, executed),
        task_complete_pct=100.0 * complete / n,
        safe_success_pct=100.0 * safe_complete / n,
        denial_per_trace=denied / n,
        executed_per_trace=executed / n,
        reasons=dict(reasons),
    )


def main():
    p = dict(drop=0.12, swap=0.12, arg=0.08, unknown=0.04,
             stale=0.10, blind=0.03, emergent=0.35)
    n = 20000
    rng = random.Random(20261125)
    traces = [make_trace(rng, GOLD, p) for _ in range(n)]

    out = {}
    for name, fn in [
        ("naive", lambda tr: run_naive(tr, rng)),
        ("tcc", lambda tr: run_gated(tr, rng, False, False)),
        ("tcc_cct", lambda tr: run_gated(tr, rng, True, True)),
    ]:
        res = [fn(copy.deepcopy(tr)) for tr in traces]
        out[name] = summarize(name, res)

    # blind-spot sweep for gated strategies
    sweep = []
    for pb in (0.0, 0.02, 0.05, 0.10, 0.20):
        p2 = dict(p, blind=pb)
        r2 = random.Random(777)
        tr2 = [make_trace(r2, GOLD, p2) for _ in range(n)]
        row = {"p_blind": pb}
        for name, ec, ef in [("tcc", False, False), ("tcc_cct", True, True)]:
            res = [run_gated(copy.deepcopy(tr), r2, ec, ef) for tr in tr2]
            s = summarize(name, res)
            row[name + "_unsafe_per_1k"] = round(s["unsafe_per_1k_traces"], 2)
            row[name + "_safe_success_pct"] = round(s["safe_success_pct"], 2)
        sweep.append(row)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("SWEEP")
    print(json.dumps(sweep, ensure_ascii=False, indent=2))
    with open("/home/runner/work/xuen/xuen/workspace/exp/toolcontract_results.json",
              "w", encoding="utf-8") as f:
        json.dump({"main": out, "sweep": sweep}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
