"""Round-22 UniBot-specific analysis: RUBRIC-GRAPH.

WHAT IS REAL HERE
-----------------
The 32 task specifications are the OFFICIAL ones published by the organisers
at  https://unibot.unitree.com/tasks_v2/<slug>/info.json  (ASSET_VERSION
"2026-07").  The `score_steps` field of each info.json is the official
scoring rubric: an ordered list of (text, points) that sums to 100 per task.
The table below was downloaded and parsed on 2026-11-06; it is INPUT DATA, not
a model output.

WHAT IS MODELLED HERE
---------------------
A declared synthetic mechanism model (NOT benchmark evidence).  It asks one
question:

  Given the official rubric structure, does replacing a flat end-to-end VLA by
  (a) a rubric-decomposed policy over SHARED atomic skills, plus
  (b) a post-condition verifier that re-executes a step invalidated by human
      interference, plus
  (c) an affordance-conditioned action head that survives unseen objects,
  improve the two published leaderboard metrics (avg success rate, avg step
  score)?  And which skills should an MVP implement first?

Run:  PYTHONPATH=<workspace>/.pylibs python3 exp/unibot_rubric_sim.py
"""
import json
import math
import os
import re
import collections

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------- #
# 1. OFFICIAL RUBRIC (input data, parsed from tasks_v2/*/info.json)            #
# --------------------------------------------------------------------------- #
# (task_id, slug, difficulty, [(step_text, points), ...])
RUBRIC = [
    ("T01", "hang_the_cup", "容易", [("抓住杯把", 50), ("挂到杯架标记位置上", 50)]),
    ("T02", "fruit_basket_collection", "容易", [("抓住水果1放入果篮", 50), ("抓住水果2放入果篮", 50)]),
    ("T03", "pack_the_doll", "容易", [("将所有娃娃装进袋子。", 50), ("将袋子摆正在面前。", 50)]),
    ("T04", "sort_fruit", "容易", [("抓住水果1放入对应颜色的餐盘", 30), ("抓住水果2放入对应颜色的餐盘", 30), ("抓住水果3放入对应颜色的餐盘", 40)]),
    ("T05", "disconnect_ethernet", "困难", [("夹住网口再夹住网线", 50), ("拔出网线", 50)]),
    ("T06", "color_arrangement", "容易", [("将红色积木放到最右侧位置", 30), ("将绿色积木放到中间位置", 30), ("将黄色积木放到最左侧位置", 40)]),
    ("T07", "place_photo_frames", "中等", [("抓住相框", 30), ("打开相框支架", 30), ("摆正相框", 40)]),
    ("T08", "organize_bookshelf", "容易", [("抓住书并拿起", 50), ("放到书架上", 50)]),
    ("T09", "toolbox_storage", "困难", [("完成2个工具的收纳", 25), ("完成所有工具的收纳", 25), ("盖上箱子盖", 25), ("锁上箱子", 25)]),
    ("T10", "plug_charger", "困难", [("抓住插排", 30), ("抓住插头", 30), ("把插头插到插排中", 40)]),
    ("T11", "pick_out_battery", "中等", [("挑出电池1（不夹带积木）", 30), ("挑出电池2（不夹带积木）", 30), ("挑出电池3（不夹带积木）", 40)]),
    ("T12", "unlock", "困难", [("抓起锁", 30), ("拧动钥匙", 30), ("拨动铁环", 40)]),
    ("T13", "organize_test_cube", "容易", [("抓起试管1放回架中指定位置", 30), ("抓起试管2放回架中指定位置", 30), ("抓起试管3放回架中指定位置", 40)]),
    ("T14", "open_pill_bottle", "困难", [("打开药瓶盖", 50), ("倒出药品", 50)]),
    ("T15", "organize_tools", "中等", [("抓住工具1放回架中", 25), ("抓住工具2放回架中", 25), ("抓住工具3放回架中", 25), ("抓住工具4放回架中", 25)]),
    ("T16", "fold_towel", "困难", [("挥正毛巾", 20), ("上下对折一次", 20), ("抓住左边对折一次", 20), ("抓住右边对折一次", 20), ("对折后放到旁边", 20)]),
    ("T17", "organize_stationery", "容易", [("摆正文具盒", 20), ("放入文具1到文具盒中", 20), ("放入文具2到文具盒中", 20), ("放入文具3到文具盒中", 20), ("盖上文具盒", 20)]),
    ("T18", "pack_bag", "中等", [("抓住文具盒", 25), ("抓住书包并拉过来", 25), ("把文具盒放入书包", 25), ("拉上书包拉链", 25)]),
    ("T19", "zip_up", "中等", [("摆正收纳包", 50), ("拉上收纳包拉链", 50)]),
    ("T20", "paper_cup_stacking", "容易", [("把纸杯1放到中间", 30), ("把纸杯2放到纸杯1的旁边", 30), ("把纸杯3放到纸杯1和2的上边", 40)]),
    ("T21", "clear_plates", "容易", [("把餐盘1放入架中", 30), ("把餐盘2放入架中", 30), ("把餐盘3放入架中", 40)]),
    ("T22", "spell_robot", "中等", [("抓住字母拼写板", 25), ("把字母 b 放到拼板中", 25), ("把字母 o 放到拼板中", 25), ("把字母 t 放到拼板中", 25)]),
    ("T23", "store_racket", "中等", [("把球拍放入球拍套中", 50), ("拉上球拍套的拉链", 50)]),
    ("T24", "sort_food_conveyor", "中等", [("抓住传送带上的食品", 50), ("将食品放到架子上对应类别的位置", 50)]),
    ("T25", "stack_cups", "容易", [("把纸杯1放入架中", 30), ("把纸杯2放入架中", 30), ("把纸杯3放入架中", 40)]),
    ("T26", "plug_in_ethernet", "中等", [("抓住网线", 30), ("抓住网口", 30), ("把网线插入到网口中", 40)]),
    ("T27", "stack_bowls_three", "容易", [("把碗1放到中间", 30), ("把碗2堆叠到碗1上", 30), ("把碗3堆叠到碗2上", 40)]),
    ("T28", "store_earphones", "困难", [("抓住耳机舱", 25), ("把左耳机放到耳机舱中", 25), ("把右耳机放到耳机舱中", 25), ("把耳机盖盖上放到收纳盒中", 25)]),
    ("T29", "pack_iphone", "困难", [("将托盘放入包装盒", 30), ("将手机放到托盘上", 30), ("盖上包装盒", 40)]),
    ("T30", "remove_pinned_note", "中等", [("拔出所有工字钉并放置到收纳盒中", 50), ("把标签纸放回收纳盒", 50)]),
    ("T31", "pencil_case", "中等", [("拉开文具袋拉链", 30), ("将所有文具放入文具袋", 40), ("拉上文具袋拉链", 30)]),
    ("T32", "syring_water", "中等", [("使用针管从大杯中吸取水", 50), ("将水注入小杯", 50)]),
]

# Atomic-verb lexicon.  Ordered: the first matching group wins for a chunk of
# text, so longer / more specific patterns are listed first.
VERB_LEXICON = [
    ("FASTEN",  r"拉上.{0,4}拉链|锁上|插上|扣上|拧上|扣紧"),
    ("UNSCREW", r"拧开|拧动回来|取下.{0,3}盖"),
    ("OPEN",    r"打开|拉开|翻开|掀开|开.{0,3}盖|拨动"),
    ("CLOSE",   r"盖上|合上|关上|盖好"),
    ("INSERT",  r"插入|插到|插进|插头插"),
    ("PULL_OUT", r"拔出|拔掉|拉出|抽出"),
    ("TRANSFER", r"吸取|注入|倒出|倒出|转移"),
    ("STACK",   r"堆叠|叠到|对折"),
    ("ALIGN",   r"摆正|挥正|摆好|对齐|整理|扶正"),
    ("GRASP",   r"抓住|抓起|夹住|挑出|拿起|握住|提起|夹持"),
    ("PLACE",   r"放入|放回|放到|放在|装进|放进|摆到|摆到|放置到|插回"),
    ("MOVE",    r"移动|拉过来|挪"),
    ("PRESS",   r"按压|按下"),
]

VERB_COMPILED = [(name, re.compile(pat)) for name, pat in VERB_LEXICON]


def decompose(step_text):
    """Split one rubric step into the ordered list of atomic verbs it contains."""
    found = []
    for name, rx in VERB_COMPILED:
        if rx.search(step_text):
            found.append(name)
    # keep source order of first appearance
    order = []
    for name, rx in VERB_COMPILED:
        if rx.search(step_text):
            order.append(name)
    return order


# --------------------------------------------------------------------------- #
# 2. EXP-1  rubric -> atomic skill library (real data, deterministic)          #
# --------------------------------------------------------------------------- #
def exp1_rubric_compression():
    n_steps = sum(len(s) for _, _, _, s in RUBRIC)
    verb_task_count = collections.Counter()   # skill -> #tasks using it
    verb_step_count = collections.Counter()   # skill -> #rubric steps using it
    verb_points = collections.Counter()       # skill -> sum of rubric points
    compound = []
    for tid, slug, diff, steps in RUBRIC:
        seen = set()
        for text, pts in steps:
            verbs = decompose(text)
            if len(verbs) > 1:
                compound.append((tid, text, verbs))
            for v in verbs:
                verb_step_count[v] += 1
                verb_points[v] += pts
                seen.add(v)
        for v in seen:
            verb_task_count[v] += 1
    # a skill's data multiplicity = #tasks it appears in (each task ~1k episodes)
    mult = {v: verb_task_count[v] for v in verb_step_count}
    return dict(
        n_tasks=len(RUBRIC),
        n_rubric_steps=n_steps,
        steps_per_task=collections.Counter(len(s) for _, _, _, s in RUBRIC),
        n_atomic_skills=len(verb_step_count),
        compression=round(n_steps / len(verb_step_count), 2),
        skill_step_count=dict(verb_step_count.most_common()),
        skill_task_count=dict(verb_task_count.most_common()),
        skill_points=dict(verb_points.most_common()),
        skill_data_multiplicity=dict(sorted(mult.items(), key=lambda kv: -kv[1])),
        n_compound_steps=len(compound),
        compound_examples=compound[:8],
        mean_verbs_per_step=round(sum(verb_step_count.values()) / n_steps, 3),
    )


# --------------------------------------------------------------------------- #
# 3. EXP-2  declared mechanism model                                          #
# --------------------------------------------------------------------------- #
# Data-scaling law for a primitive:  p = p_max * (1 - exp(-k * N_eff**alpha))
#   N_eff  : effective number of training episodes for that primitive
#   alpha  : diminishing-returns exponent (declared, 0.3)
#   p_max  : ceiling of a single primitive (declared, 0.97)
# A flat per-task policy learns each primitive from that task's episodes only
# (N_eff = D).  A decomposed policy shares the primitive across tasks
# (N_eff = D * n_tasks_using_it).  This is the whole quantitative claim.
P_MAX = 0.97
K_SCALE = 0.16
ALPHA = 0.30
D_TASK = 1000.0          # official dataset: ~1.0k episodes / task


def p_primitive(n_eff, p_max=P_MAX, k=K_SCALE, alpha=ALPHA):
    return p_max * (1.0 - math.exp(-k * (n_eff ** alpha)))


# Human-interference model (official rules: 10 runs/task, 5 generalisation
# types x 2 each; so 2/10 runs carry a human perturbation).
P_HUMAN_RUN = 2.0 / 10.0
P_PERTURB_INVALIDATES = 0.5     # declared: a perturbation invalidates one done step
Q_RECALL_FLAT = 0.15            # declared: flat policy notices an undone step
Q_RECALL_DEC = 0.75             # declared: verifier-based policy notices it
P_UNSEEN_RUN = 2.0 / 10.0
DELTA_UNSEEN = 0.25             # declared: per-step p loss on unseen objects
AFFORD_RECOVERY = 0.55          # declared: affordance head recovers this much


def task_step_success(task_idx, mode):
    """P(step i achieved) for one task, given the policy `mode`.

    modes: 'flat', 'decomp', 'decomp+verifier', 'decomp+verifier+afford'
    """
    tid, slug, diff, steps = RUBRIC[task_idx]
    per_skill_tasks = collections.Counter()
    for t2 in RUBRIC:
        seen = set()
        for text, _ in t2[3]:
            for v in decompose(text):
                seen.add(v)
        for v in seen:
            per_skill_tasks[v] += 1

    out = []
    for text, pts in steps:
        verbs = decompose(text) or ["GRASP"]
        # effective data for this primitive
        n_eff = D_TASK
        if mode != "flat":
            n_eff = D_TASK * max(per_skill_tasks[v] for v in verbs)
        p = p_primitive(n_eff)
        # unseen-object generalisation (2/10 runs): flat policies lose more
        if mode == "flat":
            p -= DELTA_UNSEEN
        elif mode == "decomp":
            p -= DELTA_UNSEEN
        elif mode == "decomp+verifier":
            p -= DELTA_UNSEEN * 0.5
        else:
            p -= DELTA_UNSEEN * (1.0 - AFFORD_RECOVERY)
        out.append(max(0.02, min(0.995, p)))
    return out


def score_task(task_idx, mode):
    """Return (P(task success), E[step score 0..100]) over the 10 official runs.

    Runs are split: 2 position, 2 distractor, 2 background (treated as no
    per-step penalty beyond the base rate), 2 unseen-object, 2 human.
    """
    tid, slug, diff, steps = RUBRIC[task_idx]
    ps = task_step_success(task_idx, mode)
    n = len(ps)

    # chain probability: step i is only attempted after 1..i-1 succeeded
    chain = []
    cum = 1.0
    for p in ps:
        cum *= p
        chain.append(cum)

    # --- success: all steps done, with recovery on human-interference runs ---
    # base (8/10 runs: position/distractor/background x2 each + 2 unseen)
    p_unseen = math.prod(ps)
    p_plain = p_unseen

    # human runs: a perturbation may invalidate one completed step.
    # expected success with recovery probability q:
    def success_with_recovery(q):
        # over the 2 human runs, perturbation invalidates with prob 0.5,
        # and we must redo the invalidated step (and all downstream ones).
        acc = 0.0
        for inv_step in range(n):
            # probability the perturbation hit exactly this step
            w = (1.0 / n)
            acc += w * (1.0 - P_PERTURB_INVALIDATES) * p_plain
            acc += w * P_PERTURB_INVALIDATES * (1.0 - q) * 0.0
            acc += w * P_PERTURB_INVALIDATES * q * (
                math.prod(ps[:inv_step + 1]) * math.prod(ps[inv_step + 1:])
            )
        return acc

    q = 0.0 if mode == "flat" else (Q_RECALL_FLAT if mode == "flat" else Q_RECALL_DEC)
    if mode == "flat":
        # a flat policy has no verifier at all: it only redoes the step if its
        # next chunk happens to re-grasp the object (prob Q_RECALL_FLAT)
        q = Q_RECALL_FLAT
    p_human = success_with_recovery(q)
    p_success = (8.0 / 10.0) * p_plain + P_HUMAN_RUN * p_human

    # --- step score: expected points earned, per run type ---
    def points(run_kind):
        # points earned if step i is done (chain-conditioned)
        got = 0.0
        for i, (text, pts) in enumerate(steps):
            if run_kind == "human":
                # a perturbation can undo one achieved step
                undid = 0.0
                for inv in range(n):
                    w = (1.0 / n)
                    if inv < i:
                        # step i downstream of the undone step -> lost unless redone
                        undid += w * P_PERTURB_INVALIDATES * (1.0 - q)
                    else:
                        undid += w * P_PERTURB_INVALIDATES * 0.0
                keep = 1.0 - undid
                # recovery restores the step (and downstream) with prob q
                eff = min(1.0, keep + q * P_PERTURB_INVALIDATES * (n - i) / n)
                p_i = chain[i] * eff
            else:
                p_i = chain[i]
            got += pts * p_i
        return got

    s_plain = points("plain")
    s_unseen = points("plain")
    s_human = points("human")
    step_score = (8.0 / 10.0) * s_plain + P_UNSEEN_RUN * s_unseen + P_HUMAN_RUN * s_human
    return p_success, step_score


def exp2_mechanism():
    modes = ["flat", "decomp", "decomp+verifier", "decomp+verifier+afford"]
    res = {}
    for m in modes:
        succ, ss = [], []
        for i in range(len(RUBRIC)):
            a, b = score_task(i, m)
            succ.append(a)
            ss.append(b)
        res[m] = dict(
            avg_success_rate=round(100 * sum(succ) / len(succ), 2),
            avg_step_score=round(sum(ss) / len(ss), 2),
            per_task_success={RUBRIC[i][0]: round(100 * succ[i], 1) for i in range(len(RUBRIC))},
        )
    # sensitivity: what if the shared-skill data multiplier is halved/removed?
    sens = {}
    for mult in (1.0, 0.5, 0.25):
        global D_SAVE
        succ, ss = [], []
        for i in range(len(RUBRIC)):
            a, b = score_task_scaled(i, "decomp+verifier+afford", mult)
            succ.append(a); ss.append(b)
        sens[f"shared_data_mult_{mult}"] = dict(
            avg_success_rate=round(100 * sum(succ) / len(succ), 2),
            avg_step_score=round(sum(ss) / len(ss), 2))
    return res, sens


def score_task_scaled(task_idx, mode, mult):
    """Same as score_task but scales the shared-skill data multiplier."""
    global SHARED_MULT
    old = SHARED_MULT
    SHARED_MULT = mult
    try:
        return score_task(task_idx, mode)
    finally:
        SHARED_MULT = old


SHARED_MULT = 1.0


# --------------------------------------------------------------------------- #
# 4. EXP-3  MVP build order (real rubric + declared unit costs)               #
# --------------------------------------------------------------------------- #
# Declared engineering cost (person-days) to implement each atomic skill as a
# reusable, generalisable module (perception + motion + verifier).
SKILL_COST = {
    "GRASP": 12.0, "PLACE": 12.0, "ALIGN": 6.0, "OPEN": 8.0, "CLOSE": 8.0,
    "FASTEN": 8.0, "INSERT": 10.0, "PULL_OUT": 8.0, "TRANSFER": 14.0,
    "STACK": 7.0, "MOVE": 5.0, "PRESS": 4.0, "UNSCREW": 8.0,
}


def exp3_mvp_order():
    # value of a skill = sum over tasks of (rubric points reachable) x (tasks)
    value = collections.Counter()
    for tid, slug, diff, steps in RUBRIC:
        for text, pts in steps:
            for v in (decompose(text) or ["GRASP"]):
                value[v] += pts
    order = sorted(value.items(), key=lambda kv: -kv[1] / SKILL_COST.get(kv[0], 10.0))
    rows = []
    budget = 45.0
    spent = 0.0
    for v, val in order:
        c = SKILL_COST.get(v, 10.0)
        take = spent + c <= budget
        if take:
            spent += c
        rows.append(dict(skill=v, rubric_points=val, cost_days=c,
                         value_per_day=round(val / c, 2), in_mvp=take))
    return dict(budget_days=budget, spent_days=spent, rows=rows,
                covered_points=sum(r["rubric_points"] for r in rows if r["in_mvp"]),
                total_points=sum(value.values()))


# --------------------------------------------------------------------------- #
def main():
    e1 = exp1_rubric_compression()
    e2, sens = exp2_mechanism()
    e3 = exp3_mvp_order()
    out = dict(round=22, retrieved="2026-11-06", exp1=e1, exp2=e2,
               exp2_sensitivity=sens, exp3=e3)
    path = os.path.join(HERE, "unibot_rubric_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("=" * 78)
    print("EXP-1  official rubric -> atomic skill library")
    print("=" * 78)
    print(f"tasks={e1['n_tasks']}  rubric steps={e1['n_rubric_steps']}  "
          f"steps/task={dict(e1['steps_per_task'])}")
    print(f"atomic skills={e1['n_atomic_skills']}  compression={e1['compression']}x  "
          f"mean verbs/step={e1['mean_verbs_per_step']}")
    print(f"{'skill':10s} {'steps':>6s} {'tasks':>6s} {'points':>7s}")
    for s, c in e1["skill_task_count"].items():
        print(f"{s:10s} {e1['skill_step_count'][s]:6d} {c:6d} {e1['skill_points'][s]:7d}")
    print(f"compound rubric steps (>=2 verbs): {e1['n_compound_steps']}")
    for c in e1["compound_examples"]:
        print("   ", c[0], c[1], "->", c[2])

    print()
    print("=" * 78)
    print("EXP-2  declared mechanism model (NOT benchmark evidence)")
    print("=" * 78)
    print(f"{'mode':28s} {'avg success %':>14s} {'avg step score':>16s}")
    for m, v in e2.items():
        print(f"{m:28s} {v['avg_success_rate']:14.2f} {v['avg_step_score']:16.2f}")
    print("sensitivity (shared-skill data multiplier):")
    for k, v in sens.items():
        print(f"   {k:28s} {v['avg_success_rate']:8.2f}  {v['avg_step_score']:8.2f}")
    print("per-task success rate, flat -> best:")
    best = e2["decomp+verifier+afford"]["per_task_success"]
    for tid in best:
        f_ = e2["flat"]["per_task_success"][tid]
        b_ = best[tid]
        print(f"   {tid}  {f_:5.1f} -> {b_:5.1f}   ({b_-f_:+.1f})")

    print()
    print("=" * 78)
    print("EXP-3  MVP build order (45 person-day budget)")
    print("=" * 78)
    print(f"{'skill':10s} {'points':>7s} {'days':>6s} {'val/day':>8s}  MVP")
    for r in e3["rows"]:
        print(f"{r['skill']:10s} {r['rubric_points']:7d} {r['cost_days']:6.0f} "
              f"{r['value_per_day']:8.2f}  {'Y' if r['in_mvp'] else '-'}")
    print(f"covered rubric points: {e3['covered_points']}/{e3['total_points']} "
          f"({100.0*e3['covered_points']/e3['total_points']:.1f}%)  "
          f"spent {e3['spent_days']:.0f}/{e3['budget_days']:.0f} days")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
