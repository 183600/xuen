### 

<!-- ARTIFACT:START -->
# 玄 · 第 3 轮灵感循环 · WOV-VLA 进度世界模型-在线专家-视觉语言溯源 三重增补

## 0. 结论与边界

### 0.1 一句话结论

第 1 轮让系统「信不信当前策略」，第 2 轮让系统「懂需求、对意图、稳抓取」，本轮让系统「预知进度、溯源视线、自适应聚合」：以计数式零参数世界模型 `Ω` 把第 2 轮拍脑袋的运动学外推换成可校准的统计预测（直接处置上轮最大风险），以语言-视觉注意力溯源 `r_ground` 把 OOD-E 检测从动作侧前移到感知侧，以 Hedge + ACI 把固定残差权重与静态 conformal 分位换成带经典后悔/覆盖保证的在线自适应——三者全部只动标量与查表，单模型、零新参数、零梯度更新，且每条退化路径精确还原第 2 轮（第 2 轮是下界）。

### 0.2 证据等级（延续 A/B/C/D/U）

| 等级 | 含义 | 本轮例子 |
|---|---|---|
| A | 经典文献、官方文档、数据集元数据直接核实 | 乘法权重更新（Hedge）的后悔界、ACI 的长期误覆盖性质（均为教科书级经典结果，具体常数以实现为准）；32 任务动词词表；33,276 episodes 元数据 |
| B | 本轮公式/可复现合成分析 | `exp/zest_sim_round3.py`：计数表覆盖率、转移惊讶 PIT 校准、注意力质心重识别准确率、Hedge 权重轨迹、ACI 误覆盖率实测（**预注册，待运行**） |
| C | 设计假设，需 G26–G28 验证 | 预算预警提前 ≥3 块、OOD-E 提前 2 块、非平稳场景收益 ≥3pp、代理标签与真实失败相关 |
| D | 设计思路或哲学论述 | 「把 VLA 当 VLM 用」「在线标量统计 ≠ 权重更新」的合规论证、世界模型符号化哲学 |
| U | 未核验，不得进入论证链 | 形如 `2609.xxxxx` 的编造 arXiv 编号；任何未实际运行却声称的「实验结果」 |

### 0.3 本轮不做什么（续）

- 不训练世界模型（无神经 WM、无 latent rollout、无 dream 规划）；不引入第二个 VLM；不做任何梯度/权重更新
- 不承诺解决 OOD-G（注意力溯源与地图共享同一错误先验，继承第 1 轮命题 7 边界）
- 不在单块决策中做 >10 步规划；horizon ≤5 块；附加延迟 <2ms
- 不假设腕部相机内参/深度/F-T；质心→地图投影不可得时自动降级为纯跟踪模式
- 不把合成实验当真机证据；「待运行」条目在门通过前不进入论证链

## 1. 承接：前人基础上的增量（累积）

### 1.1 已解决（累积）

- 第 10 轮：FACT-VLA 相位化 BC，降低长程漂移
- 第 11 轮：GEO-RESIDUAL 几何残差 + 编辑检测
- 第 12 轮：30 步开环 → 5 步闭环；DG-KEYFRAME 相对目标
- 第 13 轮：WAVE-SERVO 虚拟力 + TD-PC 无源性与限幅
- 第 14 轮：VOI-MAP 语言 grounding + 预算调度
- 第 1 轮：ZEST-VLA 胜任力层（`r_anom`、`θ_prim`、生命周期状态机）
- 第 2 轮：`Ψ_demand` 需求解析、`r_intent` 意图残差、`Π_grasp` + `σ^iso` 状态隔离、消融框架 G20–G25、MPC 预算/动作前瞻
- **第 3 轮（本轮）**：`Ω` 进度-预算世界模型（取代 `r_MPC` 同槽位）、`r_ground` 视觉语言溯源（新增第 8 通道）、OE 在线专家聚合（Hedge 权重 + ACI 分位）

### 1.2 保留 / 升级 / 剪枝

**保留**：单模型合规、预注册统计纪律、FACT-VLA 相位化、CHUNK-SERVO 双频、WAVE-SERVO TD-PC、VOI-MAP grounding/预算、`Ψ_demand`、`Π_grasp` + `σ^iso`、生命周期状态机、CUSUM 信任门结构与复检规则。

**升级**：`r_MPC`（线性外推）→ `r_wm`（校准统计预测 + 外推 backoff，同槽位）；五/六通道固定权重 → 八专家在线混合权重；静态 `q_α` → ACI 动态分位 `q_b`；OOD-E 检测从「计划-观测不一致（动作侧，事后）」前移到「指令-视线不一致（感知侧，事中最早信号）」。

**剪枝**：不做神经世界模型/latent rollout；不接外置 VLM；不做任何梯度或权重更新；不把合成实验当真机证据。

## 2. 符号与形式化（累积 + 本轮新增）

### 2.1 冻结层（不变）

VLA `π_θ` 冻结；30 步动作块、5 步执行块 `b=0..5`；残差按块计算；生命周期 `σ ∈ {INIT, GROUND, TRACK, RECOVER, HOLD}`；`Π_grasp` 子阶段 `γ ∈ {PREGRASP, APPROACH, CONTACT, LIFT, VERIFY, FAIL}`；`σ^iso` 隔离标记；`Ψ_demand` 结构化需求 `D`——全部沿用第 2 轮定义，本轮零改动。

### 2.2 本轮新增符号

**世界模型 `Ω`**：
- 世界状态桶 `s_b = (φ_b, π_b, p̂_b, κ_b)`：`φ ∈ {APPROACH, PRECONTACT, CONTACT, CARRY, VERIFY}`（执行相位）；`π ∈` 原语类型（≤8 种）；`p̂ = f(progress)` 四分位桶（4 档）；`κ ∈ {0,1}` 接触标志（`r_anom > θ_low` 判定）。`|S| ≤ 5×8×4×2 = 320`。
- `Ω` 表内容（每状态）：`N(s)` 访问计数、`N(s→s′)` 转移计数、`m(s)` 到任务成功的平均剩余块数、`v(s)` 方差、`ρ(s)` 平均每块预算消耗。
- `P̂(s′|s) = (N(s→s′) + δ) / (N(s) + δ|S|)`，δ=0.5（Dirichlet 平滑）。
- `N_min = 20`：稀疏阈值；`N(s) < N_min` 时 backoff。
- `ℓ_b = −log P̂(s_b | s_{b−1})`：转移惊讶；`R̂_b = m(s_b)`：预计剩余块数；`β_b = 1[R̂_b·ρ(s_b) > B_rem]`：预算耗尽预警。

**注意力溯源（视觉语言落地）**：
- `Attn_lv ∈ R^{L×N_v}`：冻结 checkpoint 最后层、头平均的语言→视觉交叉注意力；`N_v = h_p × w_p` 为视觉 patch 网格（布局由 checkpoint config 给出）。
- `K_obj ⊂ {1..L}`：目标名词 token 索引集（由 `Ψ_demand` 模板槽位映射，承接第 2 轮 32 词表）。
- `c_b ∈ R²`：关键词注意力质心（patch 网格坐标）；绝对模式下经第 14 轮已有相机→地图投影得 `c_b^map`。
- `r_ground_b`：感知-指令对齐残差（第 8 通道）。

**在线聚合（OE）**：
- 专家集 `E = {dyn, tmp, geo, goal, anom, intent, wm, ground}`，`|E| = 8`。
- `f^k_b = 1[z^k_b > 1]`：专家 k 的块级旗标；`y_b ∈ {0,1}`：延迟代理标签（见 2.5）。
- `w_b ∈ Δ^7`（8 维单纯形）：Hedge 混合权重；`η = 0.1`，混合系数 `ε_mix = 0.05`。
- `q_b`：ACI 动态分位；`γ_aci ∈ {1e−3, 1e−2}`（预注册网格）；`q_0` = 第 2 轮静态 (1−α) 经验分位；截断区间 `[q_min, q_max]`。

### 2.3 `Ω` 的构造与 `r_wm` 定义（取代 `r_MPC`，同槽位）

**校准（离线、冻结优先）**：从 ID 校准集成功轨迹（同一 33,276 episodes 元数据的子集）按块提取 `(s_{b−1} → s_b, 剩余块数, 块预算消耗)`，填表。可选在线增量 `n(s) ← λ_n·n(s) + 1`（`λ_n = 0.999` 遗忘），**默认冻结**（保 conformal 可交换性论证见 7.1）。

**预测与预警（块开始时）**：
- `R̂_b = m(s_b)`；`β_b = 1[R̂_b·ρ(s_b) > B_rem]`——预算预警从第 2 轮的外推改为查表，接口不变。

**转移惊讶与世界模型残差（块结束时）**：

```math
ℓ_b = −log P̂(s_b | s_{b−1})
```

```math
r^{\mathrm{wm}}_b = \max\Big(0, \frac{ℓ_b − μ^{ID}_ℓ}{σ^{ID}_ℓ + ε}\Big) + c_{bg}·\mathbb{1}[β_{b−1}=1 ∧ Δp_b < Δp_{\min}]
```

其中 `μ/σ` 为 ID 校准集上 `ℓ` 的总体均值/标准差，`c_bg = 0.5`，`Δp_b` 为本块进度增量，`Δp_min = 0`（被预警「该省预算」的块却没有进展）。

**backoff（继承第 2 轮）**：若 `N(s_{b−1}) < N_min`，`r_wm` 槽位回填第 2 轮运动学外推残差 `r_MPC`（代码路径复用，行为精确一致）。

### 2.4 `r_ground` 定义（视觉语言溯源）

**注意力质心**（k\* 取注意力质量最大的目标名词，处理指令含多个名词）：

```math
k^* = \arg\max_{k∈K_{obj}} \textstyle\sum_v Ā[k,v], \qquad
c_b = \frac{\sum_v Ā[k^*,v]·\mathrm{pos}(v)}{\sum_v Ā[k^*,v]}
```

**两种模式（自动降级）**：
- **绝对模式**（第 14 轮相机→地图投影可用）：`d_b = ‖c_b^map − c_target^map‖ / diag(bbox_target)`，

```math
r^{\mathrm{ground}}_b = \max\Big(0, \frac{d_b − μ^{ID}_d}{σ^{ID}_d + ε}\Big)
```

- **跟踪模式**（投影不可得/不假设内参，零新假设）：`J_b = ‖c_b − c_{b−1}‖ / (‖c_{b−1}‖ + ε)`，

```math
r^{\mathrm{ground}}_b = \max\Big(0, \frac{J_b − μ^{ID}_J}{σ^{ID}_J + ε}\Big)
```

**实体交换预警（OOD-E 前移）**：`r_ground_b > θ_ground` 连续 2 块且计划未变 ⇒ 触发复检（仅 APPROACH/PRECONTACT 允许，继承第 1 轮复检规则，不破坏接触）。

### 2.5 八通道融合与在线聚合（OE）

**归一化**沿用第 2 轮自归一化（滑窗 MAD）：`σ_{k,b} = 1.4826·MAD({r^k}) + ε_k`，`z^k_b = r^k_b / σ_{k,b}`。

**融合分数**（固定权重 → 在线权重）：

```math
s_b = \sum_{k∈E} w^k_b · z^k_b
```

**Hedge 混合更新**（在线学习落地之一）：

```math
ℓ^k_b = \mathbb{1}[f^k_b ≠ y_b], \qquad
w_{b+1} = (1−ε_{mix})·\mathrm{normalize}\big(w_b ⊙ e^{−η ℓ_b}\big) + ε_{mix}·\tfrac{1}{8}
```

初始化 `w_0 ∝` 第 2 轮固定权重 `(dyn=3, tmp=geo=goal=anom=intent=ground=1, wm=0.5)` 归一化——从前任出发，而非重置。

**延迟代理标签 `y_b`**：
- 仿真：未来 `H_w = 6` 块内出现硬失败证据（接触异常确认 / 编辑检测触发 / 任务失败终局回溯归因）
- 真机：未来 `H_w` 块内 FALLBACK/RECOVER 由主证据（`r_anom`、geo edit、任务终局失败）确认；窗口内均匀归因（不做精确归因的拍脑袋假设）
- `H_w ∈ {3,6,10}` 敏感性预注册

**ACI 自适应分位**（在线学习落地之二，取代静态 `q_α`）：

```math
e_b = \mathbb{1}[s_b > q_b], \qquad
q_{b+1} = \mathrm{clip}\big(q_b + γ_{aci}(α − e_b),\, q_{\min},\, q_{\max}\big)
```

`q_0` = 第 2 轮静态分位：平稳场景下 `q_b` 围绕静态值小幅波动（近似退化为第 2 轮），分布漂移时 `q_b` 朝当前分布追赶。

### 2.6 信任门与滞回/复检（继承 + 新触发）

CUSUM 不变：`S_b = max(0, S_{b−1} + e_b − α − k)`。
触发条件（第 2 轮四条 + 一条新增）：`S_b > h` ∨ `r_anom > θ_anom` ∨ `r_intent > θ_intent` ∨ `r_wm(或 backoff 的 r_MPC) > θ_wm` ∨ **`r_ground > θ_ground` 连续 2 块** → FALLBACK。
软胜任力 `c_b`、FALLBACK dwell、复检规则全部沿用。

### 2.7 生命周期交互（增量）

- `Ω` 的 `β_b` 预警沿用第 2 轮「预测预算耗尽 → surprise+1」接口，仅预测器从外推换成查表；`σ^iso=1` 且 `β_b=1` 时仍强制 `cycle_sigma ← RECOVER`（继承第 2 轮交互 3）
- `r_ground` 预警在 `σ^iso=1` 时仅通道独立计分（继承隔离规则），不并入全局融合
- Hedge/ACI 是 L4 内部标量状态更新，不改变任何状态机转移；计数表可选在线增量默认关闭

## 3. 算法

### 3.1 分层结构（L4 更新）

```text
┌────────────────────────────────────────────────────────────────┐
│ L5 ROBUSTNESS: lifecycle σ + timeout + Ω 预警(β_b) + status    │
├────────────────────────────────────────────────────────────────┤
│ L4 ZEST-WOV 胜任力层（第 3 轮）                                 │
│   八通道残差 {dyn,tmp,geo,goal,anom,intent,wm,ground}           │
│   ├─ wm:     Ω 计数式世界模型  ──backoff──▶ 第 2 轮运动学外推    │
│   ├─ ground: Attn_lv 语言-视觉质心溯源 ──backoff──▶ 通道关闭     │
│   └─ OE:     Hedge 权重 + ACI 分位 ──backoff──▶ 固定权重+静态分位 │
│   → 融合 s_b → conformal(e_b) → CUSUM → TRUST/FALLBACK/HOLD    │
├────────────────────────────────────────────────────────────────┤
│ L3 VOI-MAP: grounding + 预算调度 + Ψ_demand 注入（第 2 轮不变）  │
├────────────────────────────────────────────────────────────────┤
│ L2 WAVE-SERVO + Π_grasp + σ^iso（第 2 轮不变）                  │
├────────────────────────────────────────────────────────────────┤
│ L1 VLA server（唯一学习模型，冻结；同一次前向产出 Attn_la+Attn_lv）│
└────────────────────────────────────────────────────────────────┘
```

### 3.2 算法步骤总览（累积 20 步）

1–8（基础轮）、9–13（第 1 轮）、14–17（第 2 轮）沿用，新增：

18. **`Ω` 世界模型查询**：块开始时桶化 `s_b ← (φ,π,p̂,κ)`，查 `Ω` 得 `R̂_b`、`β_b`；`N(s) < N_min` 则 backoff 外推；`β_b=1` 走既有 surprise+1 接口。
19. **`r_ground` 溯源**：VLA 推理后与 `Attn_la` 同步读出 `Attn_lv`，算质心 `c_b` 与 `d_b`/`J_b`，得 `r_ground`；连续 2 块超阈且计划未变 → 复检。
20. **在线聚合**：块结束算八通道 `z`、延迟代理标签 `y_b`，Hedge 更新 `w`、ACI 更新 `q`；下一块的 `s_b` 与 `e_b` 用最新 `w`、`q`。

### 3.3 主循环伪代码（关键增量；其余与第 2 轮逐行相同）

```python
class WovPolicy(ZestPolicy):   # 继承第 2 轮全部字段与行为
    def __init__(self, ..., use_omega=True, use_ground=True, use_online=True,
                 omega_path=..., N_min=20, H_w=6,
                 eta=0.1, eps_mix=0.05, gamma_aci=1e-2, q_init=None):
        super().__init__(...)
        self.omega = CountWorldModel.load(omega_path)      # 冻结计数表
        self.hedge = HedgeAggregator(EXPERTS, w0=ROUND2_WEIGHTS,
                                     eta=eta, eps_mix=eps_mix)
        self.q = q_init if q_init is not None else self.static_q_alpha
        self.centroid_prev = None
        self.ground_streak = 0
        self.s_prev = None

    # ---- 步骤 18：Ω 查询（接管第 2 轮 _mpc_predict 的预算职责）----
    def _omega_predict(self, obs):
        s = self._bucket_state(obs)                        # (φ,π,p̂,κ)
        if not self.use_omega or self.omega.n(s) < N_min:
            return self._mpc_predict(obs, self.plan, H=5)  # 第 2 轮 backoff，行为不变
        ell = (-log(self.omega.trans_prob(s, self.s_prev))
               if self.s_prev is not None else 0.0)
        R_hat = self.omega.m(s)
        beta = 1.0 if R_hat * self.omega.rho(s) > self.budget_remaining else 0.0
        self.s_prev = s
        return ell, beta

    # ---- 步骤 19：视觉语言溯源 ----
    def _compute_r_ground(self, attn_lv):
        if not self.use_ground or attn_lv is None:
            return 0.0
        k = argmax_mass(attn_lv, self.K_obj)
        c = centroid(attn_lv[k], self.patch_pos)
        if self.map_projection_ok:                         # 绝对模式
            d = dist(project_to_map(c), self.M.target_centroid) / self.M.target_diag
            return max(0.0, (d - MU_D_ID) / (SIGMA_D_ID + 1e-6))
        J = rel_shift(c, self.centroid_prev)               # 跟踪模式
        self.centroid_prev = c
        return max(0.0, (J - MU_J_ID) / (SIGMA_J_ID + 1e-6))

    # ---- 步骤 20：在线聚合 ----
    def _online_step(self, z_vec, s_score, confirmed_fail=False):
        y = self._delayed_label(confirmed_fail)            # 事件登记 + H_w 窗口回填
        self.hedge.update(z_vec, y)                        # w ← 混合 Hedge
        e = 1 if s_score > self.q else 0
        self.q = clip(self.q + self.gamma_aci * (self.alpha - e), Q_MIN, Q_MAX)
        return e

    def get_action(self, obs):
        # ...第 2 轮全部逻辑不变：map/phase/edit/生命周期/Π_grasp/σ^iso...
        ell, beta = self._omega_predict(obs)
        if beta and self.use_omega:
            self.predicted_penalty = 1.0                   # 沿用第 2 轮预测惩罚接口
        # VLA 分支：与 Attn_la 同一次前向读出 Attn_lv，零额外推理
        ...
```

### 3.4 残差计算（八通道）

```python
def compute_residuals(obs0, obs1, plan, prev_plan, M, phase,
                      attn_la=None, attn_lv=None, omega_pred=None):
    r = {}
    # dyn/tmp/geo/goal/anom/intent 六通道与第 2 轮 compute_residuals 逐行相同
    r["tmp"] = normalized_action_diff(plan, prev_plan) if prev_plan else 0.0
    ...                                                      # 此处省略，零改动
    # 第 7 通道：世界模型（第 2 轮 MPC 升级为查表 + backoff，同槽位）
    if omega_pred is not None:
        ell, beta = omega_pred
        r["wm"] = max(0.0, (ell - MU_L_ID) / (SIGMA_L_ID + 1e-6)) \
                  + C_BG * beta_flag(beta, progress_delta(obs0, obs1))
    else:
        r["wm"] = mpc_residual_round2(obs0, obs1)            # backoff 槽位
    # 第 8 通道：视觉语言溯源
    r["ground"] = wov_policy._compute_r_ground(attn_lv)
    return r

def normalized_score(r, scales, w, ...):
    z = {k: r[k] / (scales[k] + EPS) for k in r}
    return sum(w[k] * z.get(k, 0.0) for k in z)
    # w 由 Hedge 在线给出；OE 关闭时 w = 第 2 轮固定权重（3,1,1,1,1,1,0.5,1 归一化）
```

### 3.5 在线聚合器

```python
class HedgeAggregator:
    def __init__(self, experts, w0, eta=0.1, eps_mix=0.05):
        self.k = len(experts)
        self.w = normalize(w0)                # 从第 2 轮固定权重出发
        self.eta, self.eps = eta, eps_mix
        self.pending = deque()                # 延迟标签回填队列 (block_idx, flags)

    def update(self, z_vec, y_b):
        f = (z_vec > 1.0).astype(float)       # 专家旗标
        loss = (f != y_b).astype(float)
        w = self.w * np.exp(-self.eta * loss)
        w = normalize(w)
        self.w = (1 - self.eps) * w + self.eps / self.k   # 混合均匀先验，防饿死
```

### 3.6 调度器增量

`select_action` 中 VLA 选项的成本项沿用第 2 轮「需求感知成本 × 预测惩罚」，其中预测惩罚来源从 `_mpc_predict` 换成 `Ω` 的 `β_b`（接口不变）。可选微调：`LOOK` 的边际收益乘 `(1 − 0.3·z_ground)`（视线已对齐时降低 LOOK 价值）——标注为可选项，G28 后评估，默认关闭。

## 4. 复杂度分析

| 组件 | 时间复杂度 | 空间复杂度 | 说明 |
|---|---|---|---|
| `Ω` 查表 | `O(1)` | `O(|S|) = O(320)` | 桶化 + 查表；校准离线完成，在线默认冻结 |
| `r_wm` | `O(1)` | `O(1)` | 一次查表 + 一次除法 |
| backoff（外推） | `O(H) = O(5)` | `O(1)` | 第 2 轮原路径，行为不变 |
| `r_ground` | `O(L·N_v)` 只读 + `O(N_v)` | `O(N_v)` | 注意力矩阵是前向已有输出仅读取；L≈20、N_v≈14×14=196 |
| Hedge | `O(8)` | `O(8)` | 逐块 8 次乘加 + 归一化 |
| ACI | `O(1)` | `O(1)` | 一次标量更新 |
| 桶化/旗标/延迟标签队列 | `O(1)` 摊销 | `O(H_w)` | 事件登记 + 窗口回填 |

**总体**：单块附加延迟 <1.5ms（注意力读取 ~0.5ms + 查表/聚合 ~0.1ms + 常数项），远低于 5 步块 ~100ms 预算；**不增加任何 VLA 前向调用次数**（`Attn_lv` 与 `Attn_la` 同一次推理读出）。

## 5. 正确性论证

### P3.1 ACI 长期误覆盖率（对抗性保证）

**命题**：对任意（甚至对抗的）分数序列 `{s_b}`，截断 ACI 更新 `q_{b+1} = clip(q_b + γ(α − e_b))` 满足 `(1/T)Σ_{b≤T} e_b ≤ α + |q_{T+1} − q_0|/(γT)`，故长期误覆盖率 → α。

**证明**：对更新式做望远镜求和；截断失效的步里等号换为把增量朝区间内拉回的不等号，故 `Σ_b (q_{b+1} − q_b) ≤ γΣ_b (α − e_b)`，即 `Σ_b e_b ≤ Tα − (q_{T+1} − q_0)/γ`。除以 T，由 `q` 有界（截断区间）得右端第二项为 `O(1/T)` → 0。∎

**推论**：平稳场景下 `q_b` 围绕静态分位小幅波动（`q_0` 即静态分位），近似退化为第 2 轮；漂移场景下 `q_b` 追赶当前分布——这是用「长期误覆盖率保证」换掉「单步可交换性假设」的标准代价，也正是静态 conformal 在非平稳下做不到的。

### P3.2 Hedge 混合权重的后悔界（就代理损失而言）

**命题**：对任意旗标/标签序列，混合 Hedge 的累计代理损失 ≤ `min_k Σ_b ℓ^k_b + O(√(T log 8)) + O(ε_mix·T)`。

**证明**：标准乘法权重更新的势函数论证给出未混合情形 `O(√(T ln 8))` 后悔界（经典结果，教科书级）；混合均匀先验 `ε_mix` 等价于对聚合器施加先验混合，额外代价上界 `ε_mix·T + (ln(1/ε_mix))/η` 量级（正则化视角）。合计 regret = `O(√(T log 8) + ε_mix·T)`。∎

**诚实的边界声明**：该保证只针对**代理损失序列本身**，不依赖其语义；「代理标签是否与真实失败相关」是经验问题，由 G28 的随机标签阴性对照与真实协议把关。理论管「追上最佳专家」，实验管「最佳专家值得追」。

### P3.3 优雅降级下界（本轮最重要的结构性质）

**命题**：三条退化路径各自精确还原第 2 轮行为；`r_wm`、`r_ground` 仅以加性方式进入 surprise/CUSUM 输入流。因此任一新组件失败或被门禁关闭时，本轮系统最坏不劣于第 2 轮。

**证明**：
1. `Ω` 稀疏（`N(s) < N_min`）⇒ `r_wm` 槽位回填第 2 轮 `r_MPC`，代码路径共用，行为逐位一致；
2. `Attn_lv` 不可得 ⇒ `r_ground ≡ 0`（恒零损失专家在 Hedge 下权重单调不增，混合下界使贡献 ≤ `ε_mix/8 · sup z`，趋近于零），融合在极限下等价第 2 轮槽位集合；
3. OE 关闭 ⇒ `w` 固定为第 2 轮权重、`q` 固定为静态分位，L4 链路逐行回到第 2 轮；
4. 加性进入：`r_wm`/`r_ground` 与第 2 轮 `r_MPC` 同构（加性、非乘性、不改分位数定义方式、不改状态机转移），沿用第 2 轮命题 5.1 的保守单调性论证。∎

### P3.4 终止性与隔离保持（继承）

**命题**：生命周期与 `Π_grasp` 的终止性、`σ^iso` 的隔离健全性在本轮保持。

**证明**：`Ω`/`r_ground`/OE 只改 CUSUM 的输入流（残差通道与分位数值），不改任何状态机转移图与动作集收缩规则；第 2 轮命题 5.3 的状态空间有限性与转移无环性论证逐字继承；`β_b` 预警仅经既有 surprise 接口加性生效。∎

## 6. 实验设计与门

### 6.1 继承门

G0–G19（基础与 ZEST 第 1 轮）、G20–G22（第 2 轮组件消融）、G23–G25（第 2 轮消融/MPC/隔离）全部继续有效；G25 中 `r_MPC` 的处置条款（AUROC < 0.6 即砍）由 G26 接管升级。

### 6.2 新增门 G26–G28（对应预注册假设 H26–H28）

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| **G26** (H26) | `Ω` 是否优于第 2 轮外推 | OOD 检测 AUROC ≥ 0.65；FALLBACK 频率相对第 2 轮不升（+10% 内）；预算预警提前 ≥ 3 块；稀疏状态占比 < 20% | 稀疏率高 → 加密桶化；整体不过 → 全量 backoff 回第 2 轮外推 |
| **G27** (H27) | `r_ground` 是否有效 | OOD-E（实体交换）检测提前 ≥ 2 块且 AUROC ≥ 0.70；随机注意力阴性对照不提升 | 关绝对模式只留跟踪模式；再不过 → 整体关闭第 8 通道 |
| **G28** (H28) | 在线聚合是否有效 | 非平稳协议成功率 ↑ ≥ 3pp 且平稳场景回归 ≤ 1pp；ACI 实测长期误覆盖率 ∈ [α−2%, α+5%]；随机标签 Hedge 阴性对照不提升 | `γ_aci` 换网格点重试一次；仍不过 → 回退固定权重 + 静态分位（第 2 轮形态） |

### 6.3 非平稳协议（本轮新增，测 ACI/Hedge 的存在意义）

- **扰动注入**：episode 内块 `k* ∈ {5,10,15}`（随机）施加一种 {光照跳变、目标纹理替换、目标物体交换（OOD-E 注入）、新阻挡物出现}；对照组无扰动
- **指标**：扰动后 10 块内检测率、恢复率、episode 成功率、`q_b` 相对静态分位的偏移轨迹、Hedge 权重熵与最优专家命中率（专家归因的可解释性副产品）
- **预注册脚本**：`exp/zest_sim_round3.py`（计数表覆盖率、转移惊讶 PIT 校准、质心重识别准确率、代理标签-真实失败相关系数）。结果**待运行**，通过前不得进入论证链（证据纪律，见 0.2 U 级）

### 6.4 真机单任务 A/B（更新）

| 项 | 设计 |
|---|---|
| 任务 | 第 2 轮 8 任务 + 非平稳敏感任务 2 个（自 {PourWater, TransportFragile, GraspThin} 按第 2 轮结果取 2）+ 中途扰动版 2 个（光照/实体交换各一） |
| 配对 | ZEST-R2(full) vs R3(Ω) vs R3(ground) vs R3(online) vs R3(full) vs R3(全关=第 2 轮复核) |
| 主端点 | 成功率；次端点：OOD-E 提前量、FALLBACK 频率、p99、`q_b` 偏移、权重熵、稀疏率、预算预警提前量 |
| 统计 | 配对差值 + bootstrap 95% CI；每格 ≥5 次 |

### 6.5 全量（更新）

32×10；新增指标：`Ω` 稀疏率、`r_ground` AUROC、ACI 实测误覆盖率、Hedge 最优专家命中率；p99 ≤ 150ms（含注意力读取）继续有效。

### 6.6 消融与阴性对照（累积 + 新增）

| 消融/对照 | 目的 | 预期 |
|---|---|---|
| 去 `Ω`（回外推） | 世界模型是否有用 | 预算预警提前量下降；G26 不通过 |
| 去 `r_ground` | 溯源是否有用 | OOD-E 提前量/AUROC 下降；G27 不通过 |
| 去 Hedge（固定权重） | 在线权重是否有用 | 非平稳收益消失；G28 不通过 |
| 去 ACI（静态分位） | 自适应分位是否有用 | 非平稳误覆盖率漂移；G28 不通过 |
| 全去（=第 2 轮） | 基线复核 | 应与第 2 轮逐项一致（P3.3 的经验验证） |
| 打乱计数表 | `Ω` 阴性对照 | 不应提升 |
| 随机注意力 | `r_ground` 阴性对照 | 不应提升 |
| 随机标签 Hedge | 反馈回路检验 | 不应提升 |
| `q_b` 冻结但声称在线 | ACI 安慰剂对照 | 与静态分位无差异 |

## 7. 风险与合规

### 7.1 单模型合规（更新）

| 模式 | 本轮做法 | 风险 | 建议 |
|---|---|---|---|
| C1 确定性几何 | 残差、CUSUM、原语、FSM、隔离、`Ω` 计数表（冻结） | 最低 | 主推 |
| C2 符号 backchannel | 质心/桶化/旗标由注意力与计数派生 | 低 | 主推 |
| C3 同 checkpoint 特征 | `Attn_lv` 与 `Attn_la` 同一次前向读出，零新参数 | 低–中 | G27 把关，写清 |
| 在线标量统计（新增条目） | Hedge 8 标量 + ACI 1 标量 + 可选计数增量 | 需论证 | 见下方专节 |
| 禁止 | 神经世界模型、外置 VLM、任何梯度/权重更新、第二个学习模型 | — | 不做 |

**「在线标量统计 ≠ test-time 权重更新」的合规论证（D 级，最终以评审为准）**：第 2 轮已在用滑窗 MAD 与滑窗分位（`σ_{k,b}` 每块重算），它们本身就是在线统计量；本轮只是把「隐式窗口统计」换成「带经典保证的显式更新规则」，量级相同（≤9 个标量），无梯度、无反向传播、无网络参数变化、无新模型。计数表默认冻结；开启在线增量时也只更新频数（充分统计量），与禁令对象（微调 VLA/训练检测器的神经权重）不同类。

### 7.2 风险表（新增项）

| 风险 | 影响 | 缓解 |
|---|---|---|
| 计数稀疏 | backoff 频繁，`Ω` 收益蒸发 | 桶化粒度预注册；稀疏率 <20% 由 G26 把关 |
| 质心→地图投影误差 | 绝对模式系统性偏移 | 跟踪模式自动降级；投影误差先在校准集上测量 |
| `Attn_lv` 无语义对齐 | `r_ground` 全程噪声 | G27 阴性对照；AUROC <0.7 即关（同第 2 轮 `r_intent` 处置先例） |
| ACI `γ` 振荡 / `q` 触界 | 误覆盖率失控 | 网格 {1e−3, 1e−2}；触界率 >10% 停用 ACI 回静态分位 |
| **Hedge 反馈回路** | 专家自我强化，检测偏置 | 随机标签阴性对照；`ε_mix` 混合防饿死；G28 把关 |
| 代理标签归因噪声 | 权重学错 | `H_w ∈ {3,6,10}` 敏感性；真机保守归因（仅主证据确认） |
| 在线计数污染（若开启） | 表漂移破坏校准论证 | 默认冻结；遗忘因子 0.999 + 冻结开关 |
| OOD-G 固有盲区 | 共享先验错误，溯源同样瞎 | 继承命题 7 边界，本轮明确不解决 |

## 8. 一句话押注（累积）

第 2 轮让系统「懂需求、对意图、稳抓取」，本轮让系统「预知进度、溯源视线、自适应聚合」：零参数世界模型把 MPC 的拍脑袋外推换成可校准统计，注意力溯源把 OOD-E 检测前移到感知侧，Hedge+ACI 把固定权重与静态分位换成带后悔/覆盖保证的在线自适应——且第 2 轮是所有退化路径的下界，本轮在最坏情况下只可能不差于上一轮。

## 9. 本轮最大的风险（一句话）

**Hedge 的自监督代理标签来自系统自身的恢复事件，存在「自我实现」反馈回路：早期参与触发 FALLBACK 的专家会分到正标签而自我强化，可能把权重学向系统性偏置**——以随机标签阴性对照与 G28 双门把关，不过即回退第 2 轮固定权重 + 静态分位（P3.3 保证无回归下界）。
<!-- ARTIFACT:END -->

<!-- IDEA:START -->
# 玄 · 第 3 轮灵感循环 · WOV-VLA 进度世界模型-在线专家-视觉语言溯源 三重增补

## 0. 前文承接与本轮划分

### 0.1 前人基础（第 1–2 轮累积）

- **第 1 轮 ZEST-VLA**：四通道自监督残差（时序/几何/目标进度/接触异常 `r_anom`）、self-normalized conformal + CUSUM 信任门、任务条件化原语参数 `θ_prim(u,M)`、显式生命周期状态机（INIT/GROUND/TRACK/RECOVER/HOLD）、几何原语语法降级、OOD-E/OOD-S 可检测边界、OOD-G 固有盲区。
- **第 2 轮**：语义需求解析 `Ψ_demand` 注入 VOI-MAP、动作-意图一致性残差 `r_intent`（第 5 通道）、自适应抓取策略库 `Π_grasp` + `σ^iso` 状态隔离、消融框架（G20–G25）、MPC 预算/动作前瞻（`r_MPC`，运动学线性外推）。
- 所有硬约束继续生效：单模型（UnifoLM-WLA-1.0 冻结）、无新参数、无 test-time 权重更新、单块附加延迟 <2ms、horizon ≤5 块、不承诺解决 OOD-G、不假设腕部相机内参/深度/F-T 传感器。

**第 2 轮自认的最大风险**：`r_MPC` 依赖「平均速度 × h、恒加速度为 0」的拍脑袋线性外推，真实动力学一旦偏离（接触/滑移/重力变化）就假阳性泛滥。这一自留软肋恰好是本轮第一个灵感词的靶子——迭代而非另起炉灶。

### 0.2 三个灵感词的落地点

| 词 | 膝跳反应 | 约束审查（为什么不行） | 降维后的落地 | 与现有架构的关系 |
|---|---|---|---|---|
| **世界模型** | 训练 latent dynamics model，rollout 未来观测，dream 式规划 | 违反「不训练任何新网络」「无新参数」；长 rollout 违反 <2ms/≤5 块延迟约束 | **计数式符号世界模型 `Ω`**：从 ID 校准轨迹统计（状态→转移频率、到成功的剩余步数、每块预算消耗率），查表预测；`r_wm` 取代 `r_MPC` 占据同一残差槽位 | 不新增任何学习组件；用可校准的统计预测替换上轮的外推预测；稀疏状态自动 backoff 回第 2 轮外推 |
| **视觉语言模型** | 外接一个 VLM 做目标重识别 / grounding 校验 | 违反「单模型」「不训练第二个模型」 | **把自家 VLA 当 VLM 用**：读出冻结 checkpoint 的语言-视觉交叉注意力 `Attn_lv`，对指令目标名词做注意力质心溯源，与语义地图信念目标比对得 `r_ground`（第 8 通道） | 零额外前向（`Attn_lv` 与第 2 轮 `Attn_la` 同一次推理的输出）；`r_intent` 管动作侧对齐，`r_ground` 管感知侧对齐，把 OOD-E 检测前移到「眼睛看错」阶段 |
| **在线学习** | test-time SGD / 在线微调残差权重 | 违反「不做 test-time weight update」 | **在线标量统计（非权重）**：Hedge 乘法权重聚合 8 个残差专家（8 个标量，经典后悔界）+ ACI 自适应 conformal 分位（1 个标量，长期误覆盖率保证） | 与第 2 轮已在用的滑窗 MAD/滑窗分位同一合规级别；固定权重 `w_k` → 在线混合权重，静态 `q_α` → 动态 `q_b`；其余结构零改动 |

### 0.3 迭代而非重建：新模块与第 2 轮的挂载关系

| 新模块 | 挂载/替换的第 2 轮部件 | 退化路径（组件失败或被门禁关闭时） |
|---|---|---|
| `Ω` 进度-预算世界模型 | `r_MPC` 槽位（第 7 通道原主人）：查表统计预测取代运动学外推 | `n(s) < N_min`（稀疏）→ 精确回退第 2 轮外推，代码路径共用，行为逐位一致 |
| `r_ground` 视觉语言溯源 | 新增第 8 通道；补 `r_intent` 只看动作侧的空缺 | checkpoint 不暴露 `Attn_lv` → `r_ground ≡ 0`，融合权重重归一，等价第 2 轮槽位集合 |
| `OE` 在线聚合（Hedge + ACI） | 固定残差权重 `w_k` 与静态分位 `q_α` | 开关关闭 → 固定权重 + 静态分位（第 2 轮形态，逐行还原） |

由此得到本轮最强的结构性承诺：**第 2 轮系统是本轮所有退化路径的下界**——任何新组件失败，系统退化回第 2 轮，而不是崩溃。

### 0.4 本轮不做什么

- 不训练世界模型：无神经 WM、无 latent rollout、无 dream 规划；`Ω` 只是一张冻结优先的计数表
- 不引入第二个 VLM：`Attn_lv` 是同一冻结 checkpoint 的免费读出（C3 级复用），G27 把关
- 不做任何梯度更新：在线更新仅限 ≤9 个标量（8 个专家权重 + 1 个分位）与默认冻结的计数表
- 不承诺解决 OOD-G：`Attn_lv` 与语义地图共享同一错误先验，若语言-视觉对齐本身错了，`r_ground` 同样瞎——继承第 1 轮命题 7 边界
- horizon 仍 ≤5 块；单块附加延迟仍 <2ms；不假设腕部相机内参/深度/F-T（质心→地图投影不可得时降级为纯跟踪模式）
- 不伪造实验结果：所有「待运行」的合成实验在 G26–G28 通过前不得进入论证链

### 0.5 本轮最大风险（先立此存照）

Hedge 的自监督代理标签来自系统自身的恢复事件，存在「自我实现」反馈回路：专家一旦早期参与触发 FALLBACK 就分到正标签而自我强化，可能把权重学向系统性偏置。若 G28 非平稳收益 <3pp 或平稳场景回归 >1pp，立即回退第 2 轮固定权重 + 静态分位（0.3 节退化路径保证无回归下界）。
<!-- IDEA:END -->
