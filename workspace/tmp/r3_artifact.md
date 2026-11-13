# 第 3 轮产物 · UniBot 创新点清单 v3（UIP-16~21）：CARE —— 场景合约 × 排名保真评测

> 承接 v2（UIP-01′~15）。本轮主线不是"再造一个策略"，而是**把比赛当成一个可设计的测量问题**：先定义场景从哪来（合约 + 扰动代数），再定义怎样用有限 episode 把排名测准（配对 / 分层 / cluster），最后才在正确的目标上优化。
> 事实：沿用 v2（32 任务计分点、`human_*`=反向撤回、开环动作块、单模型工作假设），并新增 README §5/§6 两条（N 机器人随机顺序、每机器人固定端口；逐步延迟/动作规律性计入可信度）。检索日期 2026-11-12。**本轮不新增外部依赖、不在评测期调用任何外部模型。**

---

## 0. 清单总表（v3）

| 编号 | 名称 | 状态 | 命中词 | 一句话动机 | 权限内? |
|---|---|---|---|---|---|
| **UIP-16** | **CARE 场景-评测闭环**（旗舰） | 新增 | 场景+评测 | 合约→扰动代数→排名保真评测→指标感知优化，形成可测回路 | ✅ 纯离线 |
| **UIP-17** | SCC 场景合约编译器 | 新增 | 场景驱动 | 把 32 个 `info.json` + 数据 meta 编译成机器可读合约 | ✅ |
| **UIP-18** | SCX 场景闭包 / 因子扩展器 | 新增 | 场景驱动 | 用五轴算子造闭包，用因子设计测**轴间交互** | ✅ 离线仿真 |
| **UIP-19** | SAI 场景原型不变策略 | 新增 | 场景驱动 | 单骨干 + 场景图/可供性条件化，学"计划骨架"而非像素匹配 | ✅ 部署期不变 |
| **UIP-20** | RFE 排名保真评测器 | 新增·次旗舰 | 评测指标 | 配对 CRN + 分层 Neyman + cluster bootstrap，专门把**序**测准 | ✅ 离线 |
| **UIP-21** | MAO 指标感知优化 | 新增 | 评测指标 | 直接优化官方部分分，报 Pareto 前沿；只对硬失败做风险约束 | ✅ |
| UIP-05′ | SG-LCAG 场景图 + 可供性语言分解 | 升级 | 场景驱动 | 未见物品靠可供性相似性路由，而非类别记忆 | ✅ |
| UIP-11′ | GSO-F 因子化计分神谕 | 升级 | 场景+Gazebo | 从"单条 rollout 打分"升级为"按因子单元给步骤分" | ✅ 离线 |
| UIP-12′ | DRF-A 轴化扰动数据工厂 | 升级 | 场景+Gazebo | 从"只造撤回"扩展为五轴算子的统一采样器 | ✅ 离线 |
| UIP-15′ | CSG-C 可信度约束 | 升级 | 评测指标 | 延迟 p95/CV、动作异常率从"护栏"改为**硬约束** | ✅ |
| UIP-02′ / 08′ / 13′ / 14′ | SSG / LAT-ENG / ACS / MSGR | 保留 | — | v2 的计分安全网、多端口工程、块长调度、技能图 | ✅ |

**一句话关系**：UIP-16 是回路，UIP-17/18 供"场景"，UIP-19 是被优化的策略，UIP-20/21 供"测量与目标"；v2 的组件全部成为回路中的可替换部件。

---

## 1. 旗舰深潜：UIP-16 · CARE 闭环

### 1.1 数据流

```
官方 info.json ──► UIP-17 SCC ──► 场景合约 C_i (可审阅的 JSON/YAML)
                                      │
                                      ▼
                         UIP-18 SCX（五轴算子 + 因子设计）
                                      │  场景银行 S = {(cell, seed, 资产, 扰动)}
                                      ▼
候选策略 π_1..π_K ──► UIP-20 RFE（配对 CRN + 分层 + cluster bootstrap）
                                      │  (成功率, 步骤分) 估计 + 排名 CI + Pareto 前沿 + 轴归因
                                      ▼
                         UIP-21 MAO（部分分奖励 / Pareto / 硬约束）
                                      │
                                      └──► 新候选策略 & 新谓词假设 ──▶ 回到 SCC 修合约
```

### 1.2 为什么它是旗舰

- 它把"造数据（v2 DRF）→ 判分（v2 GSO）→ 调参"从**线性流水线**变成**带误差反馈的闭环**：评测器不仅给分，还告诉你是**哪个场景轴**、**哪个计分谓词**、**哪一对策略**的差异最不确定。
- 它完全离线：RFE 只连本地策略端点，不碰官方评测端口；部署期策略仍是单个 checkpoint。
- 它的目标函数是 **RF（排名保真）**，而不是"分数拟合得准"——这直接对齐比赛的排序本质。

### 1.3 反模式（明确不做）

- 不把 32 个任务各训一个模型（违反单模型精神，且 32× 显存不可并发）。
- 不把"最优步骤顺序"当主攻（其它轮的合成实验已显示重排收益在噪声级）。
- 不把 CVaR/方差惩罚当通用目标（本轮 Q2 显示等均值下不改变期望排名，均值差 0.005 就压不过）。

---

## 2. 形式化定义

### 2.1 场景合约（UIP-17）

```json
{
  "task_id": "T26",
  "language": "plug the ethernet cable into the port",
  "objects": [
    {"name": "ethernet", "role": "manipuland", "pose_prior": "table_center"},
    {"name": "port",     "role": "receptacle", "pose_prior": "dock_right"}
  ],
  "goal": {"predicate": "inserted(rj45, port, depth>=D)"},
  "steps": [
    {"id": 1, "weight": 30, "predicate": "grasped(ethernet)"},
    {"id": 2, "weight": 30, "predicate": "aligned(rj45, port)"},
    {"id": 3, "weight": 40, "predicate": "inserted(rj45, port, depth>=D)"}
  ],
  "operators": {
    "u_obj":  ["swap(cable, unseen_cable_pool)"],
    "u_pos":  ["shift(port, ±3cm)", "rotate(cable, ±15deg)"],
    "u_dis":  ["place(distractor, free_space)"],
    "u_bg":   ["texture(bg, pool)", "lighting(±20%)"],
    "u_human":["take_away(port)", "push_back(ethernet)"]
  },
  "disturbance": {"schedule": "reversal", "target": "any_completed_step", "timing": "after_completion"}
}
```

**合约有效性检查**（任何一条不过即拒绝该合约）：`Σ weights == 100`；每个 `predicate` 能在仿真里被求值；每个算子在给定 seed 下确定；`u_human` 的语义确实是"反向撤回"。

### 2.2 场景闭包与因子设计（UIP-18）

`Cl(C_i)` 为五轴算子的闭包。全因子 `2^5 = 32` 单元/任务，若算力紧则用 **16-run 分辨率 V 部分因子**（可估所有主效应 + 全部 2 阶交互，假设 3 阶及以上可忽略）。对每个单元、每个策略、每个 seed 记录 `(success, step_score, latency, action_stats)`。

**轴归因**：用 ANOVA / Shapley 把步骤分损失分解为

```
Δscore = Σ_a ME_a + Σ_{a<b} INT_{ab} + ε
```

若 `INT_{ab} < 0`（交互使损失更大），则"一次只动一个轴"的评测会**低估**真实损失（高估鲁棒性）。这正是 H2 的可检验形式。

### 2.3 官方指标族与鲁棒序（UIP-21）

```
m_f(s;π) = f(χ_s, σ_s),  f 单调不减;   M_f(π) = E_{s∼P_test}[m_f(s;π)]
```

`f` 的权重未知 ⇒ 不强行选一个标量。定义 Pareto 支配 `π ≻ π′` 当且仅当 `χ̄(π) ≥ χ̄(π′)` 且 `σ̄(π) ≥ σ̄(π′)`，至少一个严格。评测输出**前沿**，并把选择留给"可能的 `f`"（通常成功率优先）。

### 2.4 排名保真与配对估计（UIP-20）

```
RF = P[ rank(M̂) = rank(M) ]              （主指标；备选：期望 Kendall τ、top-1 概率）
PC = P[ sign(M̂_π − M̂_π′) = sign(M_π − M_π′) ]   （两两排序正确率）
```

对同一场景 `s` 同时评 `π, π′`：

```
Var(Δ) = Var(m_π) + Var(m_π′) − 2ρ√(Var_π Var_π′)
等方差时：Var(Δ) = 2(1−ρ)Var(m)，有效样本量 × 1/(1−ρ)
```

**分层 Neyman 分配**：设任务/场景层 `i` 内"最大策略对差值方差"为 `V_i^Δ`，预算 `B` 时

```
n_i = B · √(V_i^Δ) / Σ_j √(V_j^Δ)
```

这比按"任务难度"或"任务数量"平均分配更省，因为排序误差由**差值方差**而非绝对分数方差决定。

### 2.5 N 端口 = N 个 cluster

记端口/机器人 `r` 的均值为 `y_r`，组内相关

```
ICC = σ²_between / (σ²_between + σ²_within)
```

点数少（README 示例 `N=3`）时，i.i.d. 置信区间会**严重过窄**。用 **cluster bootstrap**：对机器人有放回重采样、机器人内对 episode 有放回重采样，重算排名，得到 `P(top-1)` 与名次区间。评测器遇到"领先但 CI 跨 0"时必须输出 **insufficient evidence**，而不是宣布胜出。

### 2.6 可信度 = 硬约束（UIP-15′）

```
maximize  E[M_f(π)]
s.t.      p95(latency) ≤ B,  CV(latency) ≤ c,
          action_anomaly_rate ≤ a,  P(timeout) ≤ ε
```

这些**不是**软惩罚项。理由见 Q2：在均值口径下，为降方差而牺牲均值不会提升期望排名；只有"会直接判零/被拒"的量才值得用约束处理。

---

## 3. 组件细节

### 3.1 UIP-17 · SCC（Scenario Contract Compiler）

- **输入**：32 个 `info.json` 的 `scoring_points` 与 `generalization`；HF 数据集 `meta/info.json`（相机键、state/action 维度）；数据集视频首帧（用于核对物体/容器）。
- **输出**：带 schema 校验的合约；对每个 `human_*` 文本标注其"撤回目标 / 撤回动作 / 期望时机"。
- **现实约束**：官网是客户端渲染，部分字段可能缺失。因此维护一个**人工审阅的 overlay**（YAML，带版本号与来源链接），缺失处显式标 `TODO`，**绝不静默猜测**。
- **验收**：抽取 8 个代表任务（T05/T09/T14/T16/T19/T26/T27/T29），合约谓词在仿真里可执行率 ≥ 90%。

### 3.2 UIP-18 · SCX（Scenario Closure eXpander）

五类算子库：

| 轴 | 实现（示例） | 关键随机化 |
|---|---|---|
| `u_obj` | 从公开未见物品池换资产（尺寸/质量/摩擦/纹理） | 尺寸 ±20%，摩擦 ±30% |
| `u_pos` | SE(2) 平移/旋转物体或容器 | 平移 ±3–5cm，旋转 ±15–30° |
| `u_dis` | 碰撞感知地加干扰物 | 数量 0–3，位置在自由区 |
| `u_bg` | 背景纹理、光照、相机轻微位姿 | 亮度 ±20%，纹理池 10 种 |
| `u_human` | 脚本化撤回（合→开、拉→松、叠→翻、放→拿、拧→回） | 目标∈已完成步，时刻∈[完成, +2s]，速度×{0.5,1,2} |

- **设计**：每任务 16-run 部分因子 × 3 seeds；先做 8 个代表任务，再扩到 32。
- **产物**：`scenario_bank.parquet`（cell、seed、资产、扰动标签、仿真器版本）+ 轴归因报告。
- **与 v2 DRF 的关系**：`u_human` 就是 v2 DRF 的推广；v2 只造"撤回+恢复"，这里把它变成五轴之一，并与其他轴**联合**采样。

### 3.3 UIP-19 · SAI（Scenario-Archetype Invariant policy）

- **单骨干**：4 路图像 + proprio + language → 共享 trunk。
- **场景图头**（轻量）：预测物体节点（带可供性标签：graspable / insertable / foldable / stackable / openable）、容器节点、空间关系（on/in/near/aligned）。**只用内部权重，不调用外部 VLM。**
- **条件化**：把图 token 与语言一起送入动作头，使"未见物品"通过**可供性相似性**路由到已知技能，而不是依赖类别记忆。
- **计划骨架**：每个"场景原型"（archetype）对应一条骨架（如 `grasp→lift→align→insert→release`），骨架由 UIP-17 的计分步顺序直接生成；策略只学"骨架内的参数化技能"。
- **训练**：32 公开数据集模仿学习 + SCX 增强（五轴）+ 伪标签场景图（可用数据集物体标注，或自监督一致性）。
- **合规**：部署时只有一个 checkpoint；场景图头是同一网络的一部分。

### 3.4 UIP-20 · RFE（Rank-Fidelity Evaluator）

- **输入**：候选策略的本地端点（可复用 v2 的多端口隔离工程）、场景银行、总预算 `B`。
- **流程**：① 用少量 pilot 估 `V_i^Δ`；② Neyman 分配；③ 每轮对所有存活策略在同一场景 seed 上**配对**执行；④ **successive halving**：每轮淘汰后一半（保留"可能是前 k"的策略）；⑤ cluster bootstrap 估排名 CI；⑥ 停止条件：`P(top-1) ≥ 0.9` 或预算耗尽。
- **输出**：每个策略的 `(χ̄, σ̄)`、排名、名次区间、两两胜率矩阵、Pareto 前沿、轴归因表。
- **关键**：所有比较都基于**同一批场景**；跨策略的排序用**差值**，不是各自绝对分。

### 3.5 UIP-21 · MAO（Metric-Aware Optimization）

- **奖励**：`r = w_step·(step_score/100) + w_succ·success`，在一组权重 `{(0.5,0.5), (0.3,0.7), (0.7,0.3)}` 上分别优化，得到 Pareto 候选集。
- **训练**：模仿学习打底；用 `(success, step)` 的离线偏好/排序目标微调（DPO 风格），避免单一标量把"高步骤分但未成功"的样本浪费掉。
- **硬约束**：只对超时、可信度异常、零分做 chance constraint；**不做**通用 CVaR 惩罚。
- **与 v2 的连接**：`action_chunk_size` / `obs_delta_indices` 的控制仍是达成延迟约束的手段（v2 ACS / LAT-ENG），但目标从"平均值最优"改为"满足 p95/CV 约束下最大化期望分"。

---

## 4. 关键伪代码

```python
# ---------- UIP-20 RFE: paired, stratified, cluster-aware ----------
def rfe(policies, bank, B, alpha=0.9):
    strata = bank.group_by(["task", "cell"])          # task × 因子单元
    V = {s: max_pairwise_diff_var(s, policies, pilot=8) for s in strata}
    n = neyman_allocate(B, V)                         # n_s ∝ sqrt(V_s)
    alive, log = list(policies), []
    while len(alive) > 1:
        for s, k in n.items():
            for seed in range(k):
                scen = bank.sample(s, seed)           # 同一 seed 对所有策略
                for p in alive:                       # 配对 CRN
                    log.append((p, s, seed, run(p, scen)))
        alive = successive_halving(alive, log)        # 淘汰后一半
    rank, ci = cluster_bootstrap_rank(log, cluster="robot_port")
    return rank, ci, pareto_front(log), axis_attribution(log)


def neyman_allocate(B, V):
    tot = sum(math.sqrt(v) for v in V.values())
    n = {s: max(1, int(B * math.sqrt(v) / tot)) for s, v in V.items()}
    while sum(n.values()) < B:
        s = max(V, key=lambda j: math.sqrt(V[j]) / n[j]); n[s] += 1
    while sum(n.values()) > B:
        s = max((j for j in V if n[j] > 1), key=lambda j: n[j] / math.sqrt(V[j])); n[s] -= 1
    return n


# ---------- UIP-18 SCX: factorial closure ----------
def expand(contract, design="frac16", seeds=(0, 1, 2)):
    cells = fractional_factorial(axes=contract.operators.keys(), runs=16)
    for cell in cells:
        for seed in seeds:
            scene = contract.base_scene
            for axis, level in cell.items():
                if level == 1:
                    scene = apply(contract.operators[axis], scene, rng(seed))
            yield Scenario(scene=scene, labels=cell, seed=seed)


# ---------- UIP-21 MAO: metric-aware objective ----------
def objective(traj, w_step, w_succ):
    step = traj.step_score / 100.0
    succ = 1.0 if traj.success else 0.0
    return w_step * step + w_succ * succ
# hard constraints are checked outside the objective (reject if violated)
```

---

## 5. 合成实验结果（可复现，非真机）

脚本 `tmp/r3_rank_sim.py` → `tmp/r3_rank_sim.json`。设定：32 任务严格按官方分值分布；8 策略 × 8 技能类别；共享场景难度耦合；240 次重复/预算。**这是方法论 sanity check，不是机器人证据。**

### 5.1 Q1：排名保真 vs episode 预算（两两排序正确率）

| 预算/策略 | 独立均匀 | 配对均匀 (CRN) | 配对 + 分层 (Neyman) |
|---:|---:|---:|---:|
| 32 | 0.9035 | **0.9622** | 0.9582 |
| 64 | 0.9408 | 0.9762 | 0.9743 |
| 128 | 0.9638 | 0.9857 | 0.9844 |
| 256 | 0.9756 | 0.9920 | 0.9927 |
| 512 | 0.9875 | 0.9958 | 0.9961 |

对应 Kendall τ：独立 `0.807→0.975`，配对 `0.924→0.992`，分层 `0.916→0.992`；top-1 正确率：独立在 32 时 `0.633`、128 时 `0.879`，配对在 32 时已 `0.883`、128 时 `0.992`。

**读法**：配对在低预算段把"排序正确率"直接抬高一个档；达到 0.96 两两正确率，独立约需 128，配对约需 32 ⇒ **约 4× episode 效率**。分层与配对接近，说明**主要收益来自共享场景（降差值方差），分层是在此之上的小幅精修**。

### 5.2 Q1b：为什么是 4×——实测相关系数

同一场景下策略对之间的平均分数相关系数 `ρ̄ = 0.6224`，理论有效样本量放大 `1/(1−ρ̄) ≈ 2.65×`；与实测的约 4× 同量级（差异来自 top-1/τ 对不同预算段的敏感度不同）。

### 5.3 Q2：策略侧方差 vs 排名（等均值/微差）

| 情形（A vs B） | N=1 | N=3 | N=10 | N=32 |
|---|---:|---:|---:|---:|
| 等均值，A 低方差 | 0.501 | 0.498 | 0.501 | 0.498 |
| A 均值 −0.005，A 低方差 | 0.479 | 0.465 | 0.438 | 0.392 |
| A 均值 +0.010，A 低方差 | 0.540 | 0.565 | 0.622 | 0.708 |
| A 均值 +0.010，A 高方差 | 0.537 | 0.566 | 0.622 | 0.711 |

**读法**：① 等均值时方差对胜率**没有影响**（≈0.50）；② 均值落后 0.005 时，低方差**救不回来**，且 N 越大越明显；③ 均值领先时，高低方差的胜率几乎一致。⇒ **策略侧"稳"不是排名杠杆**；真正该降的是**评测器估计方差**（Q1）。这也纠正了"为排名优化 CVaR"的直觉错误——CVaR 只对硬失败（超时/判零/拒收）有意义。

### 5.4 局限

泊松/伯努利式场景模型、独立步、已知真值排名；真实 `P_test` 与官方 `f` 均未知；`u_human` 的真实撤销语义需真机确认。因此以上只用于**方法排序与预算规划**，不作为榜单增益承诺。

---

## 6. 实验设计 E301–E310

| 实验 | 对照 | 指标 | 目标 / 判据 |
|---|---|---|---|
| E301 | 合约自动编译 vs 人工审阅 | 谓词可执行率、错误率 | ≥90% 可执行；错误可定位 |
| E302 | 单轴评测 vs 全因子/部分因子 | 轴主效应 + 2 阶交互 | 交互显著 ⇒ H2 成立 |
| E303 | 独立均匀 vs 配对 CRN | 两两排序正确率 @ 固定预算 | 配对在低预算段显著更高（已由合成实验支持） |
| E304 | 均匀配对 vs Neyman 分层 | top-1 正确率 / 名次 CI 宽度 | 分层不劣且 CI 更窄 |
| E305 | `Δ_{ab}` vs `Δ_a+Δ_b` | 交互量级 | 量化单轴评测的高估幅度 |
| E306 | i.i.d. bootstrap vs cluster bootstrap | 名次 CI 覆盖率 | cluster 版本在 ICC>0 时覆盖更准 |
| E307 | 基线 vs SAI | 未见物品 / 位置轴成功率 | 明确 +Δ，且不牺牲基础任务 |
| E308 | 单标量 MAO vs Pareto MAO | 在多种 `f` 下的排名 | Pareto 版本对 `f` 更稳健 |
| E309 | v2 流水线 vs CARE | 留出场景银行上的综合分 | CARE 在排序保真与轴覆盖上更优 |
| E310 | 本地 RFE 排名 vs 官方榜单 | Spearman / top-1 一致 | **外部校准**，榜单一开立即执行 |

> 所有结论在 E310 之前一律标注为 **离线代理**，不得写成真机/榜单结论。

---

## 7. 合规与风险

- **单模型合规**：SAI 只有一个 checkpoint；场景图头是内部模块；RFE/SCX/SCC 全部离线，评测期不新增模型或外部 API。
- **接口红线**：部署期仍只实现 `reset()/get_action(obs)/metadata`；`action_chunk_size` 握手声明一次；N 端口连续且状态隔离。
- **仿真过拟合**：SCX 造的场景是"我们的 `P_test` 假设"，不是官方 `P_test`；必须保留 E310 外部锚点，并把仿真结论降级为"结构/排序"证据。
- **合约错误**：客户端渲染导致字段缺失；用 overlay + 显式 `TODO` + 双人复核，避免"把猜测写成事实"。
- **可信度硬约束**：延迟 p95/CV 与动作异常率是**门槛**，不能用"平均分更高"去交换；这是 v2 CSG 的升级方向。
- **统计诚实**：样本不足时输出"证据不足"，不输出虚假的 top-1。

## 8. 资源与时间线（粗排）

- **第 1–2 周**：SCC 打通 8 个代表任务（T05/T09/T14/T16/T19/T26/T27/T29）；RFE 骨架 + 合成数据自测。
- **第 3–4 周**：SCX 算子库 + 16-run 部分因子；生成首批场景银行；E302/E305。
- **第 5–6 周**：RFE 完整闭环（配对/分层/cluster/racing）；E303/E304/E306。
- **第 7–8 周**：SAI 训练（公开数据 + SCX 增强）；MAO Pareto 微调；E307/E308。
- **第 9 周起**：E309 端到端；**榜单一开或真机时段**立即做 E310 外部校准并回填合约。
- **算力**：headless Gazebo/Isaac 多实例（CPU）；1 张推理卡训 SAI；RFE 的吞吐瓶颈是仿真步进，不是策略前向。

## 9. 本轮最大风险 & 押注

**一句话**：CARE 的一切收益都建立在"场景合约 + 因子闭包 ≈ 官方隐藏 `P_test`"这一假设上；若官方评测远比我们假设的更"窄"（固定任务、少量扰动），则整套场景工程会沦为**精致的自我评测**，真实排名提升有限——因此 `E310` 的外部校准不是可选项，而是整个方案成立的前提。

**→ 本轮最值得押注：UIP-20 RFE（配对 + 分层 + cluster 的排名保真评测）× UIP-18 SCX（五轴因子场景银行）**——它不依赖新模型、不违反接口与单模型约束，直接对准"评测噪声大 + 场景分布未知"这两个所有参赛者共同面对、却最少有人系统处理的结构性缺口。
