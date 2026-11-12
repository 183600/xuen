#!/usr/bin/env python3
"""Material-typed teacher selection audit.

Question: the published leaderboard shows per-task disagreement between 8
generalist models.  Is that disagreement organised by *material/mechanism
class* (so a single-material expert / teacher can capture it), or is it
task-idiosyncratic (so only a 32-way router helps and distillation is hopeless)?

Inputs (real public snapshot, 2026-11-04):
  exp/lb_20261102.json        -- 8 models x 32 tasks, success + step
  exp/r16_task_profile.json   -- official rubric weights / slugs

Outputs per-router average success and step:
  * best single model
  * per-task oracle (upper bound)
  * per-material-class oracle (one teacher per material class)
  * per-rubric-topology oracle
  * per-difficulty oracle
and the fraction of task-oracle headroom captured by each coarse router.

Author's material labels are hypothesis-generating annotations, not official.
"""
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
lb = json.loads((HERE / "lb_20261102.json").read_text())
prof = json.loads((HERE / "r16_task_profile.json").read_text())["tasks"]


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


alias = {
    "hangthecup": "hangcup", "fruitbasketcollection": "fruitcollection",
    "packthedoll": "packdoll", "fruitsorting": "fruitsorting",
    "disconnectethernet": "disconnectethernet",
    "colorarrangement": "colorarrangement",
    "placephotoframes": "placephotoframe",
    "organizebookshelf": "organizebookshelf", "toolboxstorage": "toolboxstorage",
    "plugcharger": "plugcharger", "pickoutbattery": "pickoutbatteries",
    "unlock": "unlock", "arrangetesttubes": "arrangetesttubes",
    "openpillbottle": "pouroutmedicine", "organizetools": "organizetools",
    "foldtowel": "foldtowel", "organizestationery": "organizestationery",
    "packbag": "packbag", "zipup": "zipup", "papercupstacking": "papercupstacking",
    "clearplates": "arrangeplates", "spellrobot": "spellrobot",
    "storeracket": "storepaddle", "conveyorfoodsorting": "conveyorsorting",
    "stackcups": "storecups", "pluginethernet": "pluginethernet",
    "stackbowls": "stackbowls", "storeearphones": "storeearphones",
    "packphone": "packphone", "removepinnednote": "removepinnednote",
    "organizepencilcase": "organizepencilcase",
    "syringewatertransfer": "syringewatertransfer",
}
slug_by_norm = {norm(v["name"]): v for v in prof.values()}

# coarse material/mechanism class
MAT6 = {
    "HangCup": "INSERTION", "FruitCollection": "RIGID", "PackDoll": "DEFORMABLE",
    "FruitSorting": "RIGID", "DisconnectEthernet": "INSERTION",
    "ColorArrangement": "RIGID", "PlacePhotoFrame": "ARTICULATION",
    "OrganizeBookshelf": "RIGID", "ToolboxStorage": "ARTICULATION",
    "PlugCharger": "INSERTION", "PickOutBatteries": "CLUTTER",
    "Unlock": "ARTICULATION", "ArrangeTestTubes": "INSERTION",
    "PourOutMedicine": "FLOW", "OrganizeTools": "CLUTTER",
    "FoldTowel": "DEFORMABLE", "OrganizeStationery": "DEFORMABLE",
    "PackBag": "DEFORMABLE", "ZipUp": "DEFORMABLE",
    "PaperCupStacking": "THIN", "ArrangePlates": "THIN",
    "SpellRobot": "RIGID", "StorePaddle": "DEFORMABLE",
    "ConveyorSorting": "DEFORMABLE", "StoreCups": "THIN",
    "PlugInEthernet": "INSERTION", "StackBowls": "THIN",
    "StoreEarphones": "DEFORMABLE", "PackPhone": "THIN",
    "RemovePinnedNote": "THIN", "OrganizePencilCase": "DEFORMABLE",
    "SyringeWaterTransfer": "FLOW",
}
TOPO = {
    "HangCup": "chain", "FruitCollection": "set", "PackDoll": "mixed",
    "FruitSorting": "set", "DisconnectEthernet": "chain",
    "ColorArrangement": "set", "PlacePhotoFrame": "chain",
    "OrganizeBookshelf": "chain", "ToolboxStorage": "mixed",
    "PlugCharger": "chain", "PickOutBatteries": "set", "Unlock": "chain",
    "ArrangeTestTubes": "set", "PourOutMedicine": "chain",
    "OrganizeTools": "set", "FoldTowel": "chain",
    "OrganizeStationery": "mixed", "PackBag": "chain",
    "ZipUp": "chain", "PaperCupStacking": "chain", "ArrangePlates": "set",
    "SpellRobot": "mixed", "StorePaddle": "chain",
    "ConveyorSorting": "chain", "StoreCups": "set", "PlugInEthernet": "chain",
    "StackBowls": "chain", "StoreEarphones": "mixed",
    "PackPhone": "chain", "RemovePinnedNote": "mixed",
    "OrganizePencilCase": "chain", "SyringeWaterTransfer": "chain",
}

models = [m["model_name"] for m in lb["models"]]
succ, step, meta = {}, {}, {}
for m in lb["models"]:
    for tm in m["task_metrics"]:
        key = norm(tm["task"])
        canon = alias.get(key, key)
        p = slug_by_norm.get(canon) or next(
            (x for x in prof.values() if norm(x["slug"]) == canon), None)
        if p is None:
            print("UNMATCHED", key)
            continue
        name = p["name"]
        succ.setdefault(name, {})[m["model_name"]] = tm["success_rate"]
        step.setdefault(name, {})[m["model_name"]] = tm["step_score"]
        meta[name] = {"mat": MAT6[name], "topo": TOPO[name], "diff": p["diff"]}

tasks = sorted(succ)


def score(pick):
    """pick: task -> model. Return mean success, mean step."""
    return (st.mean(succ[t][pick(t)] for t in tasks),
            st.mean(step[t][pick(t)] for t in tasks))


def best_single():
    best = None
    for m in models:
        s = st.mean(succ[t][m] for t in tasks)
        z = st.mean(step[t][m] for t in tasks)
        if best is None or s > best[1]:
            best = (m, s, z)
    return best


def group_router(field):
    pick = {}
    table = []
    for g in sorted({meta[t][field] for t in tasks}):
        ts = [t for t in tasks if meta[t][field] == g]
        m = max(models, key=lambda mm: st.mean(succ[t][mm] for t in ts))
        table.append((g, len(ts), m,
                      st.mean(succ[t][m] for t in ts),
                      st.mean(step[t][m] for t in ts)))
        for t in ts:
            pick[t] = m
    return score(lambda t: pick[t]), table


def task_oracle():
    pick = {t: max(models, key=lambda m: succ[t][m]) for t in tasks}
    return score(lambda t: pick[t]), {
        t: max(models, key=lambda m: succ[t][m]) for t in tasks}


bs = best_single()
oracle, opick = task_oracle()
print(f"best single: {bs[0]:14s} succ={bs[1]:6.2f} step={bs[2]:6.2f}")
print(f"task oracle:             succ={oracle[0]:6.2f} step={oracle[1]:6.2f}  "
      f"(headroom +{oracle[0]-bs[1]:.2f}pp / +{oracle[1]-bs[2]:.2f})")
print("\nwinner counts:",
      {m: sum(1 for t in tasks if opick[t] == m) for m in models})
print()
for field in ["mat", "topo", "diff"]:
    sc, table = group_router(field)
    cap = (sc[0] - bs[1]) / (oracle[0] - bs[1]) * 100 if oracle[0] != bs[1] else 0
    print(f"-- router by {field}: succ={sc[0]:6.2f} step={sc[1]:6.2f}  "
          f"captures {cap:5.1f}% of task-oracle success headroom")
    for g, n, m, s, z in table:
        print(f"   {g:14s} n={n:2d} -> {m:14s} succ={s:6.2f} step={z:6.2f}")
    print()

out = {
    "source": "exp/lb_20261102.json + exp/r16_task_profile.json (public snapshot 2026-11-04)",
    "note": "material labels are author annotations; numbers are published leaderboard, not robot reruns",
    "best_single": {"model": bs[0], "success": bs[1], "step": bs[2]},
    "task_oracle": {"success": oracle[0], "step": oracle[1],
                    "success_headroom": oracle[0] - bs[1],
                    "step_headroom": oracle[1] - bs[2]},
    "winner_counts": {m: sum(1 for t in tasks if opick[t] == m) for m in models},
}
for field in ["mat", "topo", "diff"]:
    sc, table = group_router(field)
    out[f"router_{field}"] = {
        "success": sc[0], "step": sc[1],
        "headroom_capture": (sc[0] - bs[1]) / (oracle[0] - bs[1]) if oracle[0] != bs[1] else 0,
        "table": [{"group": g, "n": n, "model": m, "success": s, "step": z}
                  for g, n, m, s, z in table],
    }
(HERE / "mats_teacher_selection.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1))
print("wrote exp/mats_teacher_selection.json")
