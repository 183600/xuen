#!/usr/bin/env python3
"""MATS audit: material-typed rubric structure vs. published success/step score.

Inputs are REAL public artefacts already in exp/ (retrieved 2026-11-04):
  - lb_2026_11_04.json : leaderboard_data.json snapshot
                         (8 generalist models x 32 tasks; success_rate + step_score)
  - r16_task_profile.json : official per-task scoring weights + slugs

It computes, per task:
  * mean success / mean step over the 8 models
  * the step-score "premium" (mean_step - mean_success)
  * the across-model affine map step = a + b * success (OLS), R^2
It then groups tasks by a hand-assigned material/articulation class and by
rubric topology (ordered chain vs. independent-set), and reports the same
summary per group.

This is an *audit of published numbers*, not a robot result.  The material
labels are the author's annotations for hypothesis generation, not official.
"""
import json
import math
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
lb = json.loads((HERE / "lb_20261102.json").read_text())
prof = json.loads((HERE / "r16_task_profile.json").read_text())["tasks"]


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


slug_by_norm = {norm(v["name"]): v for v in prof.values()}
# leaderboard names occasionally differ from HF dataset names
alias = {
    "hangthecup": "hangcup",
    "fruitbasketcollection": "fruitcollection",
    "packthedoll": "packdoll",
    "fruitsorting": "fruitsorting",
    "disconnectethernet": "disconnectethernet",
    "colorarrangement": "colorarrangement",
    "placephotoframes": "placephotoframe",
    "organizebookshelf": "organizebookshelf",
    "toolboxstorage": "toolboxstorage",
    "plugcharger": "plugcharger",
    "pickoutbattery": "pickoutbatteries",
    "unlock": "unlock",
    "arrangetesttubes": "arrangetesttubes",
    "openpillbottle": "pouroutmedicine",
    "organizetools": "organizetools",
    "foldtowel": "foldtowel",
    "organizestationery": "organizestationery",
    "packbag": "packbag",
    "zipup": "zipup",
    "papercupstacking": "papercupstacking",
    "clearplates": "arrangeplates",
    "spellrobot": "spellrobot",
    "storeracket": "storepaddle",
    "conveyorfoodsorting": "conveyorsorting",
    "stackcups": "storecups",
    "pluginethernet": "pluginethernet",
    "stackbowls": "stackbowls",
    "storeearphones": "storeearphones",
    "packphone": "packphone",
    "removepinnednote": "removepinnednote",
    "organizepencilcase": "organizepencilcase",
    "syringewatertransfer": "syringewatertransfer",
}

# primary material / mechanism class (author annotation, hypothesis only)
MAT = {
    "HangCup": "rigid+insertion",
    "FruitCollection": "rigid/deformable",
    "PackDoll": "deformable",
    "FruitSorting": "rigid/deformable",
    "DisconnectEthernet": "compliant+cable",
    "ColorArrangement": "rigid",
    "PlacePhotoFrame": "rigid+hinge",
    "OrganizeBookshelf": "rigid+place",
    "ToolboxStorage": "rigid+hinge",
    "PlugCharger": "compliant+insertion",
    "PickOutBatteries": "rigid+clutter",
    "Unlock": "metal+articulation",
    "ArrangeTestTubes": "transparent+insertion",
    "PourOutMedicine": "granular",
    "OrganizeTools": "rigid",
    "FoldTowel": "deformable",
    "OrganizeStationery": "rigid+deformable",
    "PackBag": "deformable+zipper",
    "ZipUp": "deformable+zipper",
    "PaperCupStacking": "thin-film+stack",
    "ArrangePlates": "rigid+stack",
    "SpellRobot": "rigid+place",
    "StorePaddle": "rigid+zipper",
    "ConveyorSorting": "deformable+moving",
    "StoreCups": "thin-film",
    "PlugInEthernet": "compliant+insertion",
    "StackBowls": "rigid+stack",
    "StoreEarphones": "cable+small-parts",
    "PackPhone": "rigid+thin",
    "RemovePinnedNote": "thin-film+adhesion",
    "OrganizePencilCase": "deformable+zipper",
    "SyringeWaterTransfer": "fluid",
}

# rubric topology: "chain" = later milestones presuppose earlier ones;
# "set" = interchangeable items whose order can be permuted; "mixed" = chain
# with an internal set of interchangeable items (e.g. store N tools then close).
TOP = {
    "HangCup": "chain", "FruitCollection": "set", "PackDoll": "chain+set",
    "FruitSorting": "set", "DisconnectEthernet": "chain",
    "ColorArrangement": "set", "PlacePhotoFrame": "chain",
    "OrganizeBookshelf": "chain", "ToolboxStorage": "chain+set",
    "PlugCharger": "chain", "PickOutBatteries": "set", "Unlock": "chain",
    "ArrangeTestTubes": "set", "PourOutMedicine": "chain",
    "OrganizeTools": "set", "FoldTowel": "chain",
    "OrganizeStationery": "chain+set", "PackBag": "chain",
    "ZipUp": "chain", "PaperCupStacking": "chain", "ArrangePlates": "set",
    "SpellRobot": "chain+set", "StorePaddle": "chain",
    "ConveyorSorting": "chain", "StoreCups": "set", "PlugInEthernet": "chain",
    "StackBowls": "chain", "StoreEarphones": "chain+set",
    "PackPhone": "chain", "RemovePinnedNote": "chain+set",
    "OrganizePencilCase": "chain", "SyringeWaterTransfer": "chain",
}


def ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


# collect per-task series across models
series = {}
for m in lb["models"]:
    for tm in m["task_metrics"]:
        key = norm(tm["task"])
        series.setdefault(key, {"succ": [], "step": [], "dur": []})
        series[key]["succ"].append(tm["success_rate"])
        series[key]["step"].append(tm["step_score"])
        series[key]["dur"].append(tm["avg_duration_sec"])

rows = []
for key, v in series.items():
    canon = alias.get(key, key)
    p = slug_by_norm.get(canon)
    if p is None:
        # fallback: match by normalised slug
        p = next((x for x in prof.values() if norm(x["slug"]) == canon), None)
    if p is None:
        print("UNMATCHED", key)
        continue
    a, b, r2 = ols(v["succ"], v["step"])
    rows.append({
        "task": p["name"], "display": next(t["task"] for t in lb["models"][0]["task_metrics"]
                                           if norm(t["task"]) == key),
        "diff": p["diff"], "w": p["w"],
        "mean_succ": st.mean(v["succ"]), "mean_step": st.mean(v["step"]),
        "premium": st.mean(v["step"]) - st.mean(v["succ"]),
        "a": a, "b": b, "r2": r2,
        "mat": MAT[p["name"]], "topo": TOP[p["name"]],
    })

rows.sort(key=lambda r: r["premium"], reverse=True)
print(f"n_tasks={len(rows)}  n_models={len(lb['models'])}")
print(f"mean success={st.mean(r['mean_succ'] for r in rows):.2f}  "
      f"mean step={st.mean(r['mean_step'] for r in rows):.2f}  "
      f"mean premium={st.mean(r['premium'] for r in rows):.2f}")
print(f"median slope b={st.median(r['b'] for r in rows):.3f}  "
      f"median R2={st.median(r['r2'] for r in rows):.3f}")
print()
print(f"{'task':22s} {'diff':6s} {'w':18s} {'succ':>6s} {'step':>6s} "
      f"{'prem':>6s} {'b':>6s} {'R2':>5s}  mat | topo")
for r in rows:
    print(f"{r['task']:22s} {r['diff']:6s} {str(r['w']):18s} "
          f"{r['mean_succ']:6.2f} {r['mean_step']:6.2f} {r['premium']:6.2f} "
          f"{r['b']:6.3f} {r['r2']:5.3f}  {r['mat']} | {r['topo']}")


def group(field):
    out = {}
    for r in rows:
        out.setdefault(r[field], []).append(r)
    print("\n== grouped by", field, "==")
    for g, rs in sorted(out.items(), key=lambda kv: -st.mean(r["mean_step"] for r in kv[1])):
        print(f"{g:26s} n={len(rs):2d} succ={st.mean(r['mean_succ'] for r in rs):6.2f} "
              f"step={st.mean(r['mean_step'] for r in rs):6.2f} "
              f"prem={st.mean(r['premium'] for r in rs):6.2f} "
              f"b={st.mean(r['b'] for r in rs):5.3f}")


group("topo")
group("diff")

# rubric concentration (Herfindahl) vs premium
def hhi(ws):
    tot = sum(ws)
    return sum((w / tot) ** 2 for w in ws)


xs = [hhi(r["w"]) for r in rows]
ys = [r["premium"] for r in rows]
a, b, r2 = ols(xs, ys)
print(f"\npremium ~ HHI(weights): a={a:.2f} b={b:.2f} R2={r2:.3f}")
xs = [len(r["w"]) for r in rows]
a, b, r2 = ols(xs, ys)
print(f"premium ~ n_steps     : a={a:.2f} b={b:.2f} R2={r2:.3f}")

# duration vs success: are long tasks penalised?
xs = [st.mean(r["mean_succ"] for r in [])] if False else None
dur_rows = []
for key, v in series.items():
    canon = alias.get(key, key)
    p = slug_by_norm.get(canon)
    if p:
        dur_rows.append((st.mean(v["dur"]), st.mean(v["succ"]), st.mean(v["step"])))
a, b, r2 = ols([x[0] for x in dur_rows], [x[2] for x in dur_rows])
print(f"step ~ duration       : a={a:.2f} b={b:.3f} R2={r2:.3f}")

out = {
    "source": "exp/lb_20261102.json (= live leaderboard_data.json snapshot, both success and step per task) + exp/r16_task_profile.json; material/topology labels are author annotations",
    "n_tasks": len(rows),
    "n_models": len(lb["models"]),
    "means": {
        "success": st.mean(r["mean_succ"] for r in rows),
        "step": st.mean(r["mean_step"] for r in rows),
        "premium": st.mean(r["premium"] for r in rows),
        "median_b": st.median(r["b"] for r in rows),
        "median_r2": st.median(r["r2"] for r in rows),
    },
    "tasks": rows,
}
(HERE / "mats_stepscore_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("\nwrote exp/mats_stepscore_audit.json")
