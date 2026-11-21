"""UniBot-CAIRN 第 2 轮探针：把 32 个任务按"物理常识关系"编码，
检验关系负载是否解释 teaser 榜的成功率分层。

数据：exp/r16_leaderboard_data.json（teaser/占位表，8 模型 x 32 任务）。
编码：人工规则，单标注。两种口径：
  TAGS   —— 多标签（一个任务可命中多个原语）
  PRIMARY—— 单标签（每任务只取最主要的关系），用于稳健性检查
原语：
  M = mating/insertion（公母配合/插入/拔出）
  A = articulation（关节/旋转/开合/卡扣）
  C = containment（包容/装箱/收纳）
  S = support/stacking/hanging（支撑/堆叠/悬挂）
  D = deformable（可变形）
  P = plain pick-place（无特殊关系的抓放）
注意：这是探索性证据（n=32、单标注、teaser 占位表），不是因果结论。
"""
import json
import random
import statistics as st
from itertools import combinations

PATH = '/home/runner/work/xuen/xuen/workspace/exp/r16_leaderboard_data.json'
OUT = '/home/runner/work/xuen/xuen/workspace/exp/commonsense_ood/cs_relation_probe.json'
D = json.load(open(PATH))
tasks, models = D['tasks'], D['models']

TAGS = {
    'Hang the Cup': ['S'], 'Fruit Basket Collection': ['C', 'P'],
    'Pack the Doll': ['C', 'D'], 'Fruit Sorting': ['P'],
    'Disconnect Ethernet': ['M', 'A'], 'Color Arrangement': ['P'],
    'Place Photo Frames': ['S', 'P'], 'Organize Bookshelf': ['C', 'S'],
    'Toolbox Storage': ['C'], 'Plug Charger': ['M'],
    'Pick Out Battery': ['C', 'M'], 'Unlock': ['A', 'M'],
    'Arrange Test Tubes': ['C', 'S'], 'Open Pill Bottle': ['A'],
    'Organize Tools': ['C'], 'Fold Towel': ['D'],
    'Organize Stationery': ['C'], 'Pack Bag': ['C', 'D'],
    'Zip Up': ['A', 'D'], 'Paper Cup Stacking': ['S'],
    'Clear Plates': ['P', 'S'], 'Spell robot': ['S'],
    'Store Racket': ['C'], 'Conveyor Food Sorting': ['P'],
    'Stack Cups': ['S'], 'Plug In Ethernet': ['M'],
    'Stack Bowls': ['S'], 'Store Earphones': ['C'],
    'Pack Phone': ['C'], 'Remove Pinned Note': ['M', 'P'],
    'Organize Pencil Case': ['C'], 'Syringe Water Transfer': ['M'],
}

PRIMARY = {
    'Hang the Cup': 'S', 'Fruit Basket Collection': 'C', 'Pack the Doll': 'C',
    'Fruit Sorting': 'P', 'Disconnect Ethernet': 'M', 'Color Arrangement': 'P',
    'Place Photo Frames': 'S', 'Organize Bookshelf': 'C', 'Toolbox Storage': 'C',
    'Plug Charger': 'M', 'Pick Out Battery': 'M', 'Unlock': 'A',
    'Arrange Test Tubes': 'C', 'Open Pill Bottle': 'A', 'Organize Tools': 'C',
    'Fold Towel': 'D', 'Organize Stationery': 'C', 'Pack Bag': 'C',
    'Zip Up': 'A', 'Paper Cup Stacking': 'S', 'Clear Plates': 'P',
    'Spell robot': 'S', 'Store Racket': 'C', 'Conveyor Food Sorting': 'P',
    'Stack Cups': 'S', 'Plug In Ethernet': 'M', 'Stack Bowls': 'S',
    'Store Earphones': 'C', 'Pack Phone': 'C', 'Remove Pinned Note': 'P',
    'Organize Pencil Case': 'C', 'Syringe Water Transfer': 'M',
}

per, rng = {}, {}
for t in tasks:
    vals = [m['task_metrics'][[x['task'] for x in m['task_metrics']].index(t)]['success_rate']
            for m in models]
    per[t] = {'mean': st.mean(vals), 'std': st.pstdev(vals),
              'range': max(vals) - min(vals), 'vals': vals}
    rng[t] = max(vals) - min(vals)


def mean(vals):
    return st.mean(vals)


def pear(x, y):
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** .5
    return num / den if den else float('nan')


def perm_diff(pred, B=50000, seed=0):
    random.seed(seed)
    yes = [per[t]['mean'] for t in tasks if pred(t)]
    no = [per[t]['mean'] for t in tasks if not pred(t)]
    obs = mean(yes) - mean(no)
    pool = yes + no
    n = len(yes)
    c = 0
    for _ in range(B):
        random.shuffle(pool)
        if abs(mean(pool[:n]) - mean(pool[n:])) >= abs(obs):
            c += 1
    return {'n_hit': len(yes), 'hit': mean(yes), 'n_miss': len(no), 'miss': mean(no),
            'diff': obs, 'p': (c + 1) / (B + 1)}


def kendall(a, b):
    n, c, d = len(a), 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (a[i] - a[j]) * (b[i] - b[j])
            c += s > 0
            d += s < 0
    return (c - d) / (c + d) if c + d else float('nan')


def ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0] * len(vals)
    for rank, i in enumerate(order):
        r[i] = rank
    return r


def subset_tau(pred):
    ts = [t for t in tasks if pred(t)]
    R = []
    for m in models:
        vals = [m['task_metrics'][[x['task'] for x in m['task_metrics']].index(t)]['success_rate']
                for t in ts]
        R.append(ranks(vals))
    taus = [kendall(R[i], R[j]) for i, j in combinations(range(len(models)), 2)]
    return {'n': len(ts), 'mean_tau': mean(taus), 'std_tau': st.pstdev(taus)}


# 多标签口径
multi = {}
for f in ['M', 'A', 'C', 'S', 'D', 'P']:
    multi[f] = perm_diff(lambda t, f=f: f in TAGS[t])
multi['M_union_A'] = perm_diff(lambda t: bool({'M', 'A'} & set(TAGS[t])))
multi['M_union_A_union_D'] = perm_diff(lambda t: bool({'M', 'A', 'D'} & set(TAGS[t])))
load = {t: len(set(TAGS[t]) - {'P'}) for t in tasks}
multi['load_corr'] = pear([load[t] for t in tasks], [per[t]['mean'] for t in tasks])

# 单标签口径（稳健性）
prim = {}
for f in ['M', 'A', 'C', 'S', 'D', 'P']:
    prim[f] = perm_diff(lambda t, f=f: PRIMARY[t] == f)
prim['M_union_A'] = perm_diff(lambda t: PRIMARY[t] in {'M', 'A'})
prim['M_union_A_union_D'] = perm_diff(lambda t: PRIMARY[t] in {'M', 'A', 'D'})

# 跨模型一致性
tau_all = subset_tau(lambda t: True)
tau_ma = subset_tau(lambda t: bool({'M', 'A'} & set(TAGS[t])))
tau_p = subset_tau(lambda t: 'P' in TAGS[t])

out = {
    'source': PATH, 'note': 'teaser/placeholder table; single-annotator rule-based coding; exploratory',
    'tags_multi': TAGS, 'tags_primary': PRIMARY,
    'per_task': {t: {k: per[t][k] for k in ('mean', 'std', 'range')} for t in tasks},
    'multi_label': multi, 'primary_label': prim,
    'kendall_tau': {'all': tau_all, 'M_or_A': tau_ma, 'P': tau_p},
    'best_single': {'model': max(models, key=lambda m: m['avg_success_rate'])['model_name'],
                    'succ': max(m['avg_success_rate'] for m in models)},
    'oracle': mean([max(m['task_metrics'][[x['task'] for x in m['task_metrics']].index(t)]['success_rate']
                        for m in models) for t in tasks]),
}
json.dump(out, open(OUT, 'w'), ensure_ascii=False, indent=2)

if __name__ == '__main__':
    print('=== 单标签口径（主分析）===')
    for k in ['M', 'A', 'M_union_A', 'M_union_A_union_D', 'C', 'S', 'P']:
        v = prim[k]
        print(f"{k:16s} n={v['n_hit']:2d} hit={v['hit']:5.2f} miss={v['miss']:5.2f} "
              f"diff={v['diff']:+5.2f} p={v['p']:.4f}")
    print('\n=== 多标签口径（稳健性）===')
    for k in ['M', 'A', 'M_union_A', 'M_union_A_union_D', 'P']:
        v = multi[k]
        print(f"{k:16s} n={v['n_hit']:2d} hit={v['hit']:5.2f} miss={v['miss']:5.2f} "
              f"diff={v['diff']:+5.2f} p={v['p']:.4f}")
    print(f"\nload~success r={multi['load_corr']:+.3f}")
    print(f"Kendall tau: all={tau_all['mean_tau']:+.3f}, M_or_A={tau_ma['mean_tau']:+.3f}, P={tau_p['mean_tau']:+.3f}")
    print(f"best_single={out['best_single']['model']} {out['best_single']['succ']:.2f}  oracle={out['oracle']:.2f}")
