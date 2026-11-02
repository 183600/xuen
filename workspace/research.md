# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 玄 · 第 2 轮灵感循环 · ZEST-VLA 语义-意图-抓取 三重增补

## 0. 前文承接与本轮划分

### 0.1 前人基础
在第 1 轮 ZEST-VLA 突量增补基础上：已有四通道自监督残差（时序/几何/目标进度/接触异常 `r_anom`）、self-normalized conformal + CUSUM 信任门、任务条件化原语参数调整 `θ_prim(u,M)`、显式生命周期状态机（INIT/GROUND/TRACK/RECOVER/HOLD）、几何原语语法降级、OOD-E/OOD-S 可检测边界、OOD-G 固有盲区。所有约束（单模型、无新参数、无 test-time 权重更新）继续生效。

### 0.2 三个灵感词的落地点

| 词 | 落地位置 | 与现有架构的关系 |
|---|---|---|
| **需求洞察** | 语义需求解析器 `Ψ_demand(u, M)` → 结构化任务需求 `D`；注入 VOI-MAP 信念初始化与预算调度 | 在 VOI-MAP grounding 之上增加一层显式需求建模，不改变地图结构，仅丰富先验 |
| **意图理解** | 动作-意图一致性残差 `r_intent`（残差五元组第 5 通道）；CUSUM 门控的语义对齐信号 | 复用 VLA encoder 的语言-动作交叉注意力权重，零新参数提取意图对齐分数 |
| **机械臂抓取** | 自适应抓取策略库 `Π_grasp`：预抓姿态选择、接触形成验证、力闭合评估、滑移在线补偿 | 扩展几何原语库 GRASP 分支，复用 `r_anom` 和 `θ_prim`，新增确定性规则 |

### 0.3 本轮不做什么

- 不训练任何新网络/新损失/新模型；`Ψ_demand` 是模板化解析，`r_intent` 复用已有注意力权重，`Π_grasp` 是确定性规则集
- 不做 test-time weight update；不微调 VLA；不做自监督预训练
- 不假设腕部相机有内参、不假设有深度图、不假设有 F/T 传感器
- 不把合成实验当作真机证据
- 不承诺解决 OOD-G（VLA 和地图共享同一错误先验）；本轮明确保留该边界

## 1. 需求洞察增量：语义需求解析器 Ψ_demand

### 1.1 直觉
VOI-MAP 将语言指令 `u` grounding 为地图上的目标分布 `b_t`，但「把杯子放在盘子上」与「小心地把易碎杯子放在盘子中央」在目标分布上可能相近，后者却隐含了：速度约束、位置容差收紧、优先 LOOK 确认、失败代价高。这些「隐性需求」在指令语义中显性存在，却被 grounding 过程压缩丢失。引入一个轻量级模板化解析器，从 `u` 抽取结构化需求 `D = {约束集, 成功准则, 优先级, 风险等级}`，注入 VOI-MAP 的信念初始化与预算调度，可在零参数前提下显著提升长程任务的语义一致性。

### 1.2 形式化定义
设指令 `u` 为自然语言字符串。定义需求模式库 `ℒ = {ℓ_1, ..., ℓ_K}`，每个模式 `ℓ_k = (触发正则, 需求模板)`。解析器 `Ψ_demand` 为确有限状态转换器：

```math
Ψ_{\mathrm{demand}}(u) = D = \bigcup_{k: \mathrm{match}(\ell_k.\mathrm{regex}, u)} \mathrm{instantiate}(\ell_k.\mathrm{template}, u)
```

需求对象 `D` 包含四个字段：

| 字段 | 类型 | 示例 |
|---|---|---|
| `constraints` | `Dict[str, float]` | `{"max_vel": 0.1, "pos_tol": 0.005, "force_limit": 2.0}` |
| `success_criteria` | `List[Predicate]` | `[OnTable(cup), Upright(cup), NoSpill()]` |
| `priority` | `Dict[str, float]` | `{"safety": 1.0, "speed": 0.3, "precision": 0.8}` |
| `risk_level` | `Enum{LOW, MEDIUM, HIGH}` | `HIGH`（易碎/液体/昂贵） |

模板库预置 20 条规则（如「小心/轻轻/slowly」→ `max_vel ↓, precision ↑`，「稳稳/securely」→ `force_limit ↑, risk_level=HIGH`，「快速/quickly」→ `speed ↑, precision ↓`），正式评测前冻结，不学习。

### 1.3 注入 VOI-MAP 的两个注入点

**注入点 1：信念初始化偏移**
原 VOI-MAP 目标信念 `b_0` 由 grounding 分布给定。引入需求偏移：

```math
b_0^{\prime}(x) \propto b_0(x) \cdot \exp\big( \beta_{\mathrm{pos}} \cdot \mathbb{1}[x \in \mathrm{target\_region}] + \beta_{\mathrm{risk}} \cdot \mathbb{1}[\mathrm{risk\_level}=HIGH] \big)
```

其中 `β_pos, β_risk` 为固定超参（验证集手工调优后冻结）。高风险任务在目标区域附近分配更高先验，诱导更多 LOOK/SERVO 精细动作。

**注入点 2：预算调度的动作成本重加权**
原调度器动作成本 `C(a)` 为固定表。引入需求感知成本：

```math
C^{\prime}(a) = C(a) \cdot \big( 1 + \gamma_{\mathrm{speed}} \cdot \mathbb{1}[a \in \{\mathrm{VLA}, \mathrm{COMMIT}\}] \cdot (1 - D.\mathrm{priority}[\mathrm{speed}]) \big)
```

低速度优先级任务下，VLA/COMMIT 成本升高，调度器倾向于更多 SERVO/LOOK 闭环步骤。

### 1.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H12 | `Ψ_demand` 能从指令中提取至少 80% 的显性约束关键词（召回率） | 召回率 < 60% | 主 |
| H13 | 需求注入后，高风险任务（易碎/液体）的成功率相对无注入基线提升 ≥ 4pp | 无提升或 ID 任务回归 | 主 |
| H14 | 需求感知成本重加权使得高精度任务的 LOOK 比例显著上升（≥ 15%），且不增加总步数 > 5% | LOOK 比例无变化或总步数激增 | 次 |

## 2. 意图理解增量：动作-意图一致性残差 r_intent

### 2.1 直觉
VLA 输出 30 步动作块 `A_t` 时，其内部的语言-动作交叉注意力矩阵 `Attn_{lang→act} ∈ ℝ^{L×30}` 隐含了「哪些词指导了哪些步骤」的软对齐。若 VLA 因分布外输入产生幻觉动作，注意力往往呈现弥散、无焦点或指向无关词元的模式。利用这一已有信号（零新参数、零额外前向），构造第 5 个残差通道 `r_intent`，直接度量动作块与指令语义的对齐质量，作为 OOD-E 的早期预警。

### 2.2 形式化定义
设 VLA encoder 最后一层交叉注意力权重为 `Attn ∈ ℝ^{L×30}`，其中 `L` 为指令 token 数。定义意图焦点熵：

```math
H_{\mathrm{intent}} = -\frac{1}{30} \sum_{t=1}^{30} \sum_{\ell=1}^{L} \mathrm{Attn}_{\ell,t} \log \mathrm{Attn}_{\ell,t}
```

定义关键词覆盖率：预先标注指令中的关键动作词集 `K ⊂ {1..L}`（如「抓取、放置、插入、旋转、推、拉、打开、关闭、叠、折」等 32 任务动词词表）。注意力在关键词上的边际质量：

```math
Q_{\mathrm{key}} = \frac{1}{30} \sum_{t=1}^{30} \sum_{\ell \in K} \mathrm{Attn}_{\ell,t}
```

定义动作-意图一致性残差：

```math
r^{\mathrm{intent}}_b = \underbrace{\frac{H_{\mathrm{intent}} - \mu_{H}^{\mathrm{ID}}}{\sigma_{H}^{\mathrm{ID}}}}_{\text{熵异常项}} + \underbrace{\max\Big(0, \frac{\mu_{Q}^{\mathrm{ID}} - Q_{\mathrm{key}}}{\sigma_{Q}^{\mathrm{ID}}}\Big)}_{\text{关键词缺失项}}
```

其中 `μ_H^ID, σ_H^ID, μ_Q^ID, σ_Q^ID` 为 ID 校准集上的经验均值标准差（冻结）。`r_intent` 越大表示注意力越弥散或关键动作词被忽视。

### 2.3 与 conformal/CUSUM 的集成
五通道融合扩展为：

```math
s_b = w_{\mathrm{tmp}} z^{\mathrm{tmp}}_b + w_{\mathrm{geo}} z^{\mathrm{geo}}_b + w_{\mathrm{goal}} z^{\mathrm{goal}}_b + w_{\mathrm{anom}} z^{\mathrm{anom}}_b + w_{\mathrm{intent}} z^{\mathrm{intent}}_b
```

固定权重 `w_{\mathrm{intent}} = 1`（与其他非动力学通道相同）。校准集收集五通道分数，split conformal 取 `(1-α)` 分位数，理论性质不变——维度从 4 扩到 5，交换性假设仅依赖残差序列 i.i.d.，与维度无关。

### 2.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H15 | `r_intent` 能区分 OOD-E（未见指令/幻觉动作）与 ID，AUROC ≥ 0.75 | AUROC < 0.6 | 主 |
| H16 | ZEST+`r_intent` 在 OOD-E 上成功率相对无 `r_intent` 基线提升 ≥ 3pp | 无提升 | 主 |
| H17 | `r_intent` 在指令含否定词/复合指令时（如「不要抓红色的」）比 `r_tmp/r_geo` 更早触发（提前 ≥ 2 个块） | 无提前优势 | 次 |

## 3. 机械臂抓取增量：自适应抓取策略库 Π_grasp

### 3.1 直觉
当前 GRASP 原语仅有一个参数化握幅 `w_b = θ_prim`，缺乏：预抓姿态选择（顶抓/侧抓/底抓）、接触形成验证（双指接触时序、力闭合判断）、滑移在线补偿（基于 `r_anom` 的微调）。真实抓取失败多源于：预抓姿态与物体几何不匹配、接触形成不对称导致力闭合失败、抓起瞬间滑移未补偿。在单模型、无新参数约束下，设计一个确定性的抓取策略库，复用已有 `r_anom`（接触一致性）、`θ_prim`（尺寸调整）、语义地图 `M`（物体几何、姿态、摩擦估计），在 GRASP 原语内部展开为 4 个子阶段，每阶段有明确的通过/失败判据，失败即触发 RECOVER。

### 3.2 形式化定义
GRASP 原语扩展为有限状态机 `Π_grasp`，状态 `γ ∈ {PREGRASP, APPROACH, CONTACT, LIFT, VERIFY, FAIL}`：

| 子阶段 | 行为 | 通过判据 | 失败转移 |
|---|---|---|---|
| **PREGRASP** | 根据 `M.obj_geometry` 选择预抓姿态：顶抓（扁平物体）、侧抓（细长物体）、底抓（杯状） | 姿态可达性 `IK(q_pregrasp) < ∞` ∧ 碰撞检测通过 | `FAIL` → 触发 `RECOVER` 重规划 |
| **APPROACH** | WAVE-SERVO 移动至预抓位置，夹爪预张开 `w_b + δ` | 位置误差 `‖x - x_pregrasp‖ < θ_pos` | `FAIL` |
| **CONTACT** | 闭合夹爪至目标握幅 `w_b`，监控 `r_anom` | `r_anom < θ_anom` ∧ 双指接触时间差 `Δt_contact < 0.1s` | `FAIL` → 微调握幅 `w_b ← w_b · 0.95` 重试 1 次 |
| **LIFT** | 抬升 `h_lift = θ_prim(LIFT)`，监控 `r_anom` 与滑移指示 | `r_anom < θ_anom` ∧ `slip_score < θ_slip` | `FAIL` → `RECOVER` |
| **VERIFY** | 静止 0.5s，末端位姿漂移检查 | `‖x_{t+10} - x_t‖ < 0.002m` | `FAIL` → `RECOVER` |

**滑移指示** 复用第 11 轮 edit/slip 分数与 `r_anom` 组合：

```math
\mathrm{slip\_score} = \mathrm{edit\_score} + \lambda_{\mathrm{anom}} \cdot r^{\mathrm{anom}}
```

**预抓姿态选择规则**（确定性，基于语义地图包围盒 `bbox = (w, d, h)` 和姿态 `R`）：

```math
\mathrm{grasp\_type} = 
\begin{cases}
\mathrm{TOP}, & \text{if } h / \max(w,d) < 0.5 \text{ (扁平)} \\
\mathrm{SIDE}, & \text{if } \max(w,d) / \min(w,d) > 3 \text{ (细长)} \\
\mathrm{BOTTOM}, & \text{if } \text{cup\_like}(M) \text{ (杯状/有把手)} \\
\mathrm{SIDE}, & \text{otherwise}
\end{cases}
```

所有阈值 `θ_pos, θ_anom, θ_slip, λ_anom` 在验证集手工调优后冻结，不学习。

### 3.3 与现有组件的集成

- **`θ_prim` 复用**：GRASP 握幅 `w_b` 直接使用第 1 轮 `θ_prim` 调整后的值
- **`r_anom` 复用**：CONTACT/LIFT/VERIFY 阶段的通过判据直接读取 `r_anom`
- **生命周期联动**：任一子阶段 `FAIL` → 设置 `cycle_sigma = RECOVER`，触发 `PROBE_ANOM` 探针
- **域检查扩展**：`dom(σ(u))` 增加 `grasp_feasible` 判定（IK 可达、碰撞自由、握幅在物理范围内）

### 3.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H18 | `Π_grasp` 四子阶段通过率在 ID 抓取任务上 ≥ 90%（单阶段） | 任一阶段通过率 < 80% | 主 |
| H19 | 完整 `Π_grasp` 相对原单阶段 GRASP，抓取成功率提升 ≥ 6pp | 无提升或回归 | 主 |
| H20 | CONTACT 阶段基于 `r_anom` 的重试机制能挽回 ≥ 30% 的初次接触失败 | 挽回率 < 15% | 次 |

## 4. 更新的证伪假设表（累积）

| 编号 | 假设 | 主/次 | 证伪条件 |
|---|---|---|---|
| H1 | 残差三元组区分 OOD-E/OOD-S（地图对） | 主 | AUROC < 0.65 或 ID 假警报 > 10% |
| H2 | ZEST 在 OOD 上 +5pp，ID 不回归，成本 ≤ 3% | 主 | 相对 VLA-only 无提升或 ID 回归 |
| H3 | 复检/滞回优于永久 fallback | 主（恢复） | 复检不优于永久 fallback |
| H6 | `r_anom` 能区分接触内部异常，AUROC ≥ 0.7 | 主 | AUROC < 0.55 |
| H7 | ZEST+`r_anom` 在含接触异常的 OOD 上成功率相对提升 ≥ 3pp | 主 | 相对无 `r_anom` 无提升 |
| H8 | `θ_prim` 调整后的几何原语在几何可分解的跨任务上成功率 ≥ +5pp | 主 | 域检查通过率下降或成功率无提升 |
| H9 | 任务条件化参数调整在物体尺寸差异 ≥ 30% 的任务上有正收益 | 主 | 调整无效或负收益 |
| H10 | 生命周期状态机 p99 ≤ 150ms | 主 | p99 > 150ms |
| H11 | RECOVER 模式复钵探针 2块内确认清除 | 主 | 探针连续 3 块仍惊讶 |
| H12 | `Ψ_demand` 关键词召回率 ≥ 80% | 主 | 召回率 < 60% |
| H13 | 需求注入后高风险任务成功率相对提升 ≥ 4pp | 主 | 无提升或 ID 回归 |
| H14 | 需求感知成本使高精度任务 LOOK 比例 ↑ ≥ 15% | 次 | 无变化或总步数激增 |
| H15 | `r_intent` 区分 OOD-E AUROC ≥ 0.75 | 主 | AUROC < 0.6 |
| H16 | ZEST+`r_intent` 在 OOD-E 上成功率相对提升 ≥ 3pp | 主 | 无提升 |
| H17 | `r_intent` 在否定/复合指令上提前 ≥ 2 块触发 | 次 | 无提前优势 |
| H18 | `Π_grasp` 单阶段通过率 ≥ 90% | 主 | 任一阶段 < 80% |
| H19 | 完整 `Π_grasp` 抓取成功率相对提升 ≥ 6pp | 主 | 无提升或回归 |
| H20 | CONTACT 重试挽回率 ≥ 30% | 次 | 挽回率 < 15% |

## 5. 风险表更新（累积）

| 风险 | 影响 | 缓解 |
|---|---|---|
| **OOD-G 不可检测** | 目标错时系统自信执行 | 命题 7 明确边界；独立语义检查/任务清单/复检 |
| **`r_anom` 前端太弱** | 无 F/T 传感器下接触一致性代理噪声大 | 多模态组合（视觉穿透+电流+动力学）；辅助通道定位 |
| **`θ_prim` 调整过激** | 语义地图尺寸估计误差导致原语前置条件失效 | `α_max` 截断；域检查把关 |
| **生命周期状态 desync** | 真机网络抖动导致状态机与实际状态不匹配 | `τ_max` 超时 guards；心跳检测；掉线默认 HOLD |
| **复检破坏接触** | RECOVER 探针在接触阶段引入滑落 | 仅 APPROACH/PRECONTACT/原语边界探针 |
| **VLA 推理超时** | VLA server 无响应或返回错误形状 | 生命周期层设定超时，超时进入 HOLD/RECOVER |
| **`Ψ_demand` 误解析** | 关键词触发错误约束（如「快速」被误触发为「小心」） | 模板库人工审核；冻结后不更新；低优先级约束可被 VOI 覆盖 |
| **`r_intent` 注意力不可靠** | VLA 注意力权重在某些 checkpoint 无语义对齐意义 | 校准集验证 ID 分布；若 AUROC 低则 G17 砍掉该通道 |
| **`Π_grasp` 状态机过刚性** | 特殊物体（软体/变形/透明）不符合预设分支 | `FAIL` 即触发 RECOVER 降级至 VLA/LOOK；不强制完成 |
| **抓取类型误判** | 包围盒估计误差导致选错预抓姿态（如高杯误判为扁平） | 语义地图类别标签辅助判断；PREGRASP 碰撞检测兜底 |

## 6. 本轮最大的风险

**注意力语义对齐的不可靠性**：`r_intent` 完全依赖 VLA 冻结 checkpoint 的交叉注意力权重具有「语言 token → 动作步骤」的语义对齐性。但现实中，许多 VLA checkpoint 的注意力矩阵呈现近均匀分布、或关注停用词、或与动作因果关系微弱。若 ID 校准集上 `r_intent` 无法形成可分离的分布（AUROC < 0.6），该通道将被 G17 砍掉，导致本轮「意图理解」增量归零，且可能引入额外的计算开销与假阳性干扰现有四通道融合。这是本轮三个增量中唯一**依赖模型内部未经验证属性**的风险点，必须在合成实验 G17 阶段严格把关。
<!-- IDEA:END -->
<!-- ARTIFACT:START -->
# 玄 · 第 2 轮灵感循环 · ZEST-VLA 语义-意图-抓取 三重增补

## 0. 结论与边界（续）

### 0.1 一句话结论（续）
第 1 轮将执行治理提升为结构化鲁棒系统，本轮在「需求显性化、意图对齐度量、抓取策略精细化」三个维度深化零样本泛化：从「信不信当前策略」进化到「懂不懂真实需求、对不对真实意图、稳不稳真实抓取」，仍坚持单模型、零新参数、零 test-time 学习。

### 0.2 本轮新增证据等级

| 等级 | 含义 | 本报告中的例子 |
|---|---|---|
| A | 官方文档、提交模板、数据集元数据、经典文献直接核实 | 32 任务动词词表、WLA encoder 注意力维度、33,276 eps |
| B | 本轮公式/合成实验/逻辑推导分析，可复现 | `exp/zest_sim_round2.py` 需求解析覆盖率、注意力熵分布、抓取子阶段通过率 |
| C | 设计假设，需 G17–G22 验证 | 真机高风险任务收益、OOD-E 提前检测、抓取成功率提升 |
| D | 设计思路或哲学论述，非形式化证明 | 直觉动机、注意力语义对齐假设、抓取策略库设计哲学 |
| U | 未核验，不得进入论证链 | 形如 `2609.xxxxx` 的异常 arXiv 编号 |

### 0.3 本轮不做什么（续）

- 不训练第二个检测/分割/语言/失败检测模型；`Ψ_demand` 模板解析、`r_intent` 注意力复用、`Π_grasp` 确定性规则
- 不做 test-time weight update；不微调 VLA；不做自监督预训练
- 不承诺解决 OOD-G（VLA 和地图共享同一错误先验）；明确保留该信息论边界

## 1. 承接：前人基础上的增量（累积）

### 1.1 已解决（累积）

- 第 10 轮：FACT-VLA 相位化 BC，降低长程漂移
- 第 11 轮：GEO-RESIDUAL 几何残差 + 编辑检测
- 第 12 轮：30 步开环 → 5 步闭环；DG-KEYFRAME 相对目标
- 第 13 轮：WAVE-SERVO 虚拟力 + TD-PC 无源性与限幅
- 第 14 轮：VOI-MAP 语言 grounding + 预算调度
- **第 1 轮（上轮）**：ZEST-VLA 胜任力层 + `r_anom` + `θ_prim` + 生命周期状态机
- **第 2 轮（本轮）**：语义需求解析 `Ψ_demand`、动作-意图一致性残差 `r_intent`、自适应抓取策略库 `Π_grasp`

**保留**：单模型合规、预注册统计纪律、FACT-VLA 相位化、CHUNK-SERVO 双频、WAVE-SERVO TD-PC、VOI-MAP grounding/预算、ZEST-VLA 信任门/降级/生命周期

**升级**：从「执行胜任力不确定性」升级到「需求-意图-动作全链路语义一致性」；从「固定参数原语」升级到「子阶段验证的自适应策略库」；从「事后异常检测」升级到「事前需求约束 + 事中意图对齐 + 事后接触验证」三重保障

**剪枝**：不做自监督预训练；不做 test-time weight update；不训练失败检测器；不引入第二个学习模型

## 2. 更新的符号与形式化（累积）

### 2.1 冻结的 VLA 与执行层（续）

设 VLA 为 `π_θ`，`θ` 冻结。给定观测 `o_t` 和指令 `u`，输出 30 步动作块 `A_t = (a_{t,0},...,a_{t,29})`。执行层按 5 步块执行，块索引 `b=0,...,5`。

**新增符号（本轮）**：
- `D = Ψ_demand(u)`：结构化需求对象 `{constraints, success_criteria, priority, risk_level}`
- `r^{\mathrm{intent}}_b`：第 `b` 个块的动作-意图一致性残差（第 5 通道）
- `γ ∈ {PREGRASP, APPROACH, CONTACT, LIFT, VERIFY, FAIL}`：抓取策略库子阶段状态
- `Attn ∈ ℝ^{L×30}`：VLA encoder 最后一层语言-动作交叉注意力权重
- `K ⊂ {1..L}`：关键动作词索引集（32 任务动词词表）

### 2.2 五通道自监督残差向量（更新）

在块 `b` 结束后，五个残差并行计算：

**接触异常残差（anomaly，第 1 轮）**

```math
r^{\mathrm{anom}}_b =
\frac{\|K_p (x^{\mathrm{des}}_b - \mathrm{fk}(q_b)) - c^{\mathrm{obs}}_b \mu |I(q_b)|\|}
{\|K_p (x^{\mathrm{des}}_b - \mathrm{fk}(q_b))\| + \epsilon}
```

**动作-意图一致性残差（intent，本轮新增）**

```math
H_{\mathrm{intent}} = -\frac{1}{30}\sum_{t=1}^{30}\sum_{\ell=1}^{L} \mathrm{Attn}_{\ell,t}\log\mathrm{Attn}_{\ell,t}
```

```math
Q_{\mathrm{key}} = \frac{1}{30}\sum_{t=1}^{30}\sum_{\ell \in K} \mathrm{Attn}_{\ell,t}
```

```math
r^{\mathrm{intent}}_b = \frac{H_{\mathrm{intent}} - \mu_{H}^{\mathrm{ID}}}{\sigma_{H}^{\mathrm{ID}}} + \max\Big(0, \frac{\mu_{Q}^{\mathrm{ID}} - Q_{\mathrm{key}}}{\sigma_{Q}^{\mathrm{ID}}}\Big)
```

**目标进度残差（goal-progress，既有）**

```math
r^{\mathrm{goal}}_b = 
\begin{cases}
\frac{(d_0 - d_1) - \Delta d^{\mathrm{plan}}}{\Delta d^{\mathrm{plan}} + \epsilon}, & \phi_b \in \{\mathrm{APPROACH},\mathrm{PRECONTACT}\} \\
\mathrm{edit\_score}(o_{b-1}, o_b), & \text{otherwise}
\end{cases}
```

**几何残差（geometric，既有）**

```math
r^{\mathrm{geo}}_b = \frac{\|\mathrm{fk}(q_b) - \mathrm{fk}(q_{b-1}) - \Delta x^{\mathrm{plan}}_b\|}{\|\Delta x^{\mathrm{plan}}_b\| + \epsilon} + \lambda_F \cdot \frac{\|\mathrm{flow}_{\mathrm{obs}} - \mathrm{flow}_{\mathrm{pred}}\|}{\sigma_{\mathrm{flow}}}
```

**动力学残差（dynamic，既有）**

```math
r^{\mathrm{dyn}}_b = \max\big(0, \max(\|qdot_b\|/\dot{q}_{\max}, \|qddot_b\|/\ddot{q}_{\max}) - 1\big)
```

**归一化与融合（五通道）**

```math
\sigma_{k,b} = 1.4826 \cdot \mathrm{MAD}(\{r^k_{b-W+1},...,r^k_b\}) + \epsilon_k
```

```math
z^k_b = r^k_b / \sigma_{k,b}, \qquad
s_b = \sum_{k \in \{\mathrm{dyn,tmp,geo,goal,anom,intent}\}} w_k z^k_b
```

固定权重：`w_dyn = 3`，`w_tmp = w_geo = w_goal = w_anom = w_intent = 1`。五通道全部固定权重，均不训练。

### 2.3 自归一化与 Conformal 校准（更新）

ID 校准集收集五通道融合分数，取 `(1-α)` 经验分位数：

```math
q_\alpha = \mathrm{Quantile}_{1-\alpha}\{s_b^{\mathrm{cal}}\}, \qquad s_b = \sum_k w_k z^k_b
```

测试块惊讶指示：`e_b = \mathbb{1}[s_b > q_\alpha]`。边际保证不变：`\Pr(s_{B+1} > q_\alpha) \le \alpha`。

### 2.4 CUSUM 信任门与滞回/复检（更新）

```math
S_b = \max(0, S_{b-1} + e_b - \alpha - k), \quad S_0 = 0
```

触发条件扩展：`S_b > h` **或** `r^{\mathrm{anom}}_b > \theta_{\mathrm{anom}}` **或** `r^{\mathrm{intent}}_b > \theta_{\mathrm{intent}}` → 进入 `FALLBACK`。

复检规则不变：仅 APPROACH/PRECONTACT/原语边界允许，CONTACT/CARRY 禁止。

软胜任力：`c_b = 1 - \frac{1}{W}\sum_{i=0}^{W-1} e_{b-i}`。

### 2.5 语义需求解析器 Ψ_demand（本轮新增）

#### 2.5.1 模板库形式化
模式库 `ℒ = {ℓ_1,...,ℓ_K}`，每个 `ℓ_k = (R_k, T_k)`：
- `R_k`：正则触发规则（如 `r"小心|轻轻|slowly|carefully"`）
- `T_k`：需求模板，映射匹配组到 `D` 字段更新

示例模板（冻结，共 20 条）：
| 触发正则 | 约束更新 | 优先级更新 | 风险等级 |
|---|---|---|---|
| `小心|轻轻|slowly|carefully` | `max_vel←0.1, pos_tol←0.005` | `precision↑0.8, speed↓0.2` | `HIGH` |
| `稳稳|securely|firmly` | `force_limit←3.0` | `safety↑1.0` | `HIGH` |
| `快速|quickly|fast` | `max_vel←0.5` | `speed↑0.9, precision↓0.3` | `LOW` |
| `易碎|fragile|玻璃|glass` | `force_limit←1.5, max_vel←0.05` | `safety↑1.0, precision↑0.9` | `HIGH` |
| `液体|water|倒|pour` | `pos_tol←0.003, max_vel←0.08` | `precision↑0.9` | `HIGH` |
| `重|heavy` | `force_limit←5.0` | `safety↑0.8` | `MEDIUM` |

解析算法（确定性、线性时间）：

```python
def psi_demand(u: str) -> Demand:
    D = Demand.default()  # 默认约束：max_vel=0.3, pos_tol=0.01, force_limit=3.0
    for regex, template in TEMPLATE_LIBRARY:  # 冻结的 20 条规则
        if re.search(regex, u, re.IGNORECASE):
            D = template.apply(D, u)
    return D
```

#### 2.5.2 注入 VOI-MAP：信念初始化偏移

```math
b_0^{\prime}(x) \propto b_0(x) \cdot \exp\big( \beta_{\mathrm{pos}} \mathbb{1}[x \in \mathcal{X}_{\mathrm{target}}] + \beta_{\mathrm{risk}} \mathbb{1}[D.\mathrm{risk\_level}=\mathrm{HIGH}] \big)
```

其中 `β_pos = 1.5`, `β_risk = 1.0`（验证集冻结）。归一化后作为 VOI-MAP 初始信念。

#### 2.5.3 注入 VOI-MAP：动作成本重加权

```math
C^{\prime}(a) = C(a) \cdot \Big( 1 + \gamma_{\mathrm{speed}} \mathbb{1}[a \in \{\mathrm{VLA},\mathrm{COMMIT}\}] (1 - D.\mathrm{priority}[\mathrm{speed}]) \Big)
```

其中 `γ_speed = 2.0`（验证集冻结）。低速度优先级时，VLA/COMMIT 成本最高 3 倍，调度器倾向 SERVO/LOOK。

### 2.6 自适应抓取策略库 Π_grasp（本轮新增）

#### 2.6.1 子阶段有限状态机

```math
\gamma \in \{\mathrm{PREGRASP}, \mathrm{APPROACH}, \mathrm{CONTACT}, \mathrm{LIFT}, \mathrm{VERIFY}, \mathrm{FAIL}\}
```

转移规则（每个 5 步块边界评估）：

```math
\gamma_{b+1} = 
\begin{cases}
\mathrm{APPROACH}, & \gamma_b = \mathrm{PREGRASP} \land \mathrm{IK}(q_{\mathrm{pregrasp}}) < \infty \land \neg \mathrm{collision} \\
\mathrm{CONTACT}, & \gamma_b = \mathrm{APPROACH} \land \|x_b - x_{\mathrm{pregrasp}}\| < \theta_{\mathrm{pos}} \\
\mathrm{LIFT}, & \gamma_b = \mathrm{CONTACT} \land r^{\mathrm{anom}}_b < \theta_{\mathrm{anom}} \land \Delta t_{\mathrm{contact}} < 0.1 \\
\mathrm{VERIFY}, & \gamma_b = \mathrm{LIFT} \land r^{\mathrm{anom}}_b < \theta_{\mathrm{anom}} \land \mathrm{slip\_score} < \theta_{\mathrm{slip}} \\
\mathrm{DONE}, & \gamma_b = \mathrm{VERIFY} \land \|x_{b+1} - x_b\| < 0.002 \\
\mathrm{FAIL}, & \text{otherwise (任一判据不通过)}
\end{cases}
```

**FAIL 处理**：`FAIL` 即触发 `cycle_sigma ← RECOVER`，`fallback_dwell ← 0`，下一块执行 `PROBE_ANOM`。

#### 2.6.2 预抓姿态选择（确定性规则）

```python
def select_pregrasp_pose(M, target_id) -> SE3:
    bbox = M.get_bbox(target_id)      # (w, d, h) in object frame
    R = M.get_orientation(target_id)  # 物体朝向
    category = M.get_category(target_id)  # 语义类别
    
    aspect_flat = bbox[2] / max(bbox[0], bbox[1])  # h / max(w,d)
    aspect_long = max(bbox[0], bbox[1]) / min(bbox[0], bbox[1])
    
    if category in {"cup", "mug", "bowl"} or M.has_handle(target_id):
        return compute_bottom_grasp(M, target_id)
    elif aspect_flat < 0.5:
        return compute_top_grasp(M, target_id)
    elif aspect_long > 3.0:
        return compute_side_grasp(M, target_id)
    else:
        return compute_side_grasp(M, target_id)  # 默认侧抓
```

#### 2.6.3 接触形成验证

```python
def verify_contact_formation(obs_before, obs_after, w_target) -> bool:
    # 双指接触时间差
    t_left = obs_after.left_finger_contact_time
    t_right = obs_after.right_finger_contact_time
    delta_t = abs(t_left - t_right)
    
    # 接触力一致性
    r_anom = compute_anomaly_residual(obs_before, obs_after)
    
    return (delta_t < 0.1) and (r_anom < theta_anom)
```

#### 2.6.4 滑移在线补偿（CONTACT 阶段重试）

```python
def contact_with_retry(obs, w_target, max_retry=1):
    for attempt in range(max_retry + 1):
        w_try = w_target * (0.95 ** attempt)  # 每次重试握幅减 5%
        chunk = execute_grasp_close(obs, w_try)
        obs_after = execute_and_observe(chunk)
        if verify_contact_formation(obs, obs_after, w_try):
            return True, obs_after
        obs = obs_after
    return False, obs  # 触发 FAIL → RECOVER
```

### 2.7 显式生命周期与鲁棒性层（更新：新增 GRASP 子阶段感知）

生命周期状态机 `σ ∈ {INIT, GROUND, TRACK, RECOVER, HOLD}` 不变。

**新增交互**：当 `Π_grasp` 任一子阶段进入 `FAIL`，强制 `σ ← RECOVER`，且 `PROBE_ANOM` 探针专门针对抓取接触状态诊断。

**TRACK 状态下的动作集修正**：
- `Π_grasp` 处于 `CONTACT/LIFT/VERIFY` 子阶段时，禁用 `LOOK` 和 `VLA`（防止抓取中断），仅允许 `SERVO`（执行子阶段）和 `HOLD`

## 3. 更新的算法（累积）

### 3.1 分层结构（更新）

```text
                    ┌─────────────────────────────────────────────┐
                    │ Evaluator (N ports, delayed websocket)      │
                    └──────────────────┬──────────────────────────┘
                                       │ obs / action chunk
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Per-port PolicyService (CPU)                             │
        │                                                          │
        │  ┌────────────────────────────────────────────────────┐  │
        │  │ L4  ZEST-VLA 胜任力层（两轮增量）                   │  │
        │  │  residual quintet → conformal/CUSUM → trust gate   │  │
        │  │  TRUST / FALLBACK / HOLD + soft competence c_b     │  │
        │  │  + r_anom + r_intent + θ_prim + Ψ_demand           │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ allowed action set           │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L3  VOI-MAP（第 14 轮 + 本轮需求注入）              │  │
        │  │  semantic map, grounding, budget scheduler         │  │
        │  │  + belief bias (Ψ_demand) + cost reweight (Ψ_demand)│
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ selected action              │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L2  WAVE-SERVO + Π_grasp（本轮）                    │  │
        │  │  virtual force, TD-PC, phase impedance, clamps     │  │
        │  │  + grasp sub-phase FSM + contact verification      │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ 30/5 chunk                   │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L1  VLA server（唯一学习模型，冻结）                 │  │
        │  │  UnifoLM-WLA-1.0, 30-step plan + cross-attn        │  │
        │  └────────────────────────────────────────────────────┘  │
        └──────────────────────────────────────────────────────────┘
                                                                     │
                                                                        ▼
                                                   ┌───────────────────────┐
                                                   │ L5 ROBUSTNESS 层        │
                                                   │ lifecycle σ + timeout   │
                                                   │ topic status publish    │
                                                   └───────────────────────┘
```

### 3.2 算法步骤总览（累积 13 步）

在原有 8 步 + 第 1 轮 5 步基础上增：

14. **语义需求解析**：任务开始时 `D ← Ψ_demand(u)`，注入 VOI-MAP 信念偏移与成本重加权。
15. **意图一致性残差计算**：每块 VLA 推理后提取 `Attn`，计算 `r_intent_b`，并入五通道融合。
16. **抓取策略库执行**：FALLBACK 中 GRASP 原语展开为 `Π_grasp` 子阶段 FSM，每阶段验证通过才推进，失败触发 RECOVER。

### 3.3 更新后的主循环伪代码（关键增量）

```python
class ZestPolicy:
    def __init__(self, calib_scores, lambda_grasp, lambda_insert, lambda_lift):
        # ... existing fields ...
        self.psi_demand = DemandParser(TEMPLATE_LIBRARY)  # 冻结模板库
        self.D = None                    # 当前任务需求
        self.gamma = "IDLE"              # Π_grasp 子阶段
        self.grasp_target = None         # 当前抓取目标
        self.grasp_retry_count = 0
        self.theta_intent = None         # 经校准的 r_intent 阈值

    def on_task_start(self, instruction: str):
        """任务开始时调用：解析需求、注入 VOI-MAP"""
        self.D = self.psi_demand.parse(instruction)
        self.M.inject_demand(self.D)     # 信念偏移 + 成本重加权
        self.gamma = "IDLE"

    def get_action(self, obs):
        # 1. update map / phase / edit detector
        self.M = update_map(self.M, obs, self.plan)
        self.phase = observe_phase(self.M, obs)
        if edit_detected(obs):
            self.phase = "RECOVER"
            self.cycle_sigma = "GROUND"

        # 2. update lifecycle state
        self._update_cycle_state(obs)

        # 3. 如果在 GRASP 子阶段中，优先执行 Π_grasp
        if self.gamma != "IDLE" and self.gamma != "DONE":
            return self._execute_grasp_phase(obs)

        # 4. 正常动作选择
        act = self.select_action(obs)

        if act == "SERVO":
            chunk = self._wave_servo_chunk(obs, self.plan)
            self._record_pending_residual_check(obs, chunk)
            return chunk

        if act == "FALLBACK":
            adapted = self._adapt_primitive_params(self.plan)
            if adapted is None:
                act = "HOLD"
            else:
                # 检查是否包含 GRASP 原语
                for prim, args in adapted:
                    if prim == "GRASP":
                        self._init_grasp_fsm(args)
                        return self._execute_grasp_phase(obs)
            chunk = self._execute_next_primitive(obs, adapted)
            self._record_pending_residual_check(obs, chunk, fallback=True)
            return chunk

        if act == "LOOK":
            return self._look_action(obs)

        if act == "VLA":
            # VLA 推理后提取注意力用于 r_intent
            self._request_plan_async(obs)
            return self._safe_hold_or_last_chunk()

        if act == "HOLD":
            return self._safe_hold()

        if act == "PROBE_ANOM":
            return self._probe_anom(obs)

        return self._commit_action(obs)

    def _on_vla_response(self, plan, attn_weights):
        """VLA 异步回调：保存 plan 与注意力权重"""
        self.plan = plan
        self.prev_plan = self.plan
        self.attn_weights = attn_weights  # (L, 30) cross-attention
        # 立即计算 r_intent（不等待块结束）
        if self.attn_weights is not None:
            self.r_intent = self._compute_intent_residual(self.attn_weights)

    def _compute_intent_residual(self, attn: np.ndarray) -> float:
        """计算 r_intent：注意力熵 + 关键词覆盖"""
        # attn: (L, 30), row-wise softmax 已归一化
        H = -np.mean(np.sum(attn * np.log(attn + 1e-8), axis=0))  # 平均每步熵
        Q_key = np.mean(np.sum(attn[KEYWORD_INDICES, :], axis=0))  # 关键词平均注意力
        
        z_H = (H - self.mu_H_id) / (self.sigma_H_id + 1e-6)
        z_Q = max(0, (self.mu_Q_id - Q_key) / (self.sigma_Q_id + 1e-6))
        return z_H + z_Q

    def _init_grasp_fsm(self, grasp_args):
        """初始化 Π_grasp 有限状态机"""
        self.gamma = "PREGRASP"
        self.grasp_target = grasp_args["target"]
        self.grasp_width_target = grasp_args["width"]  # 已含 θ_prim 调整
        self.grasp_retry_count = 0
        self.pregrasp_pose = select_pregrasp_pose(self.M, self.grasp_target)

    def _execute_grasp_phase(self, obs):
        """执行 Π_grasp 当前子阶段，返回 5 步 chunk"""
        if self.gamma == "PREGRASP":
            # 移动至预抓位置，夹爪预张开
            chunk = self._wave_servo_to_pose(obs, self.pregrasp_pose, 
                                             gripper_width=self.grasp_width_target + 0.02)
            # 到达判据在 on_block_finished 中检查
            return chunk

        elif self.gamma == "APPROACH":
            # 精细对齐至预抓位置
            chunk = self._wave_servo_to_pose(obs, self.pregrasp_pose,
                                             gripper_width=self.grasp_width_target + 0.02)
            return chunk

        elif self.gamma == "CONTACT":
            # 闭合夹爪至目标握幅，支持重试
            w_try = self.grasp_width_target * (0.95 ** self.grasp_retry_count)
            chunk = self._wave_servo_gripper_close(obs, w_try)
            return chunk

        elif self.gamma == "LIFT":
            # 抬升
            lift_height = self.lambda_lift * self.mu_ref_lift  # 简化
            chunk = self._wave_servo_lift(obs, lift_height)
            return chunk

        elif self.gamma == "VERIFY":
            # 静止验证
            chunk = self._wave_servo_hold(obs, duration=5)  # 5 步 ≈ 0.5s
            return chunk

        return self._safe_hold()

    def on_block_finished(self, obs_before, obs_after, executed):
        # 1. 计算残差（含 r_intent）
        if executed in ("SERVO", "GRASP_SUBPHASE"):
            r = compute_residuals(obs_before, obs_after, self.plan,
                                  self.prev_plan, self.M, self.phase)
            r["intent"] = self.r_intent if hasattr(self, 'r_intent') else 0.0
            r["anom"] = self._compute_anomaly_residual(r, obs_before, obs_after)
            s = self._normalized_score(r)
            surprise = int(s > self.q_alpha)
            self.surprise_window.append(surprise)
            self.cusum = max(0.0, self.cusum + surprise - ALPHA - K)
            self._update_mode(surprise)

        # 2. Π_grasp 子阶段判据检查
        if self.gamma != "IDLE" and self.gamma != "DONE":
            self._check_grasp_phase_transition(obs_before, obs_after)

        # 3. 生命周期更新
        self._update_cycle_state({})

    def _check_grasp_phase_transition(self, obs_before, obs_after):
        """Π_grasp 子阶段通过/失败判据"""
        if self.gamma == "PREGRASP":
            # 检查 IK 可达 + 无碰撞 + 位置到达
            if self._check_pregrasp_ready(obs_after):
                self.gamma = "APPROACH"
            else:
                self.gamma = "FAIL"

        elif self.gamma == "APPROACH":
            pos_err = np.linalg.norm(fk(obs_after.q)[:3] - self.pregrasp_pose[:3, 3])
            if pos_err < self.theta_pos:
                self.gamma = "CONTACT"
            else:
                self.gamma = "FAIL"

        elif self.gamma == "CONTACT":
            r_anom = self._compute_anomaly_residual({}, obs_before, obs_after)
            delta_t = self._contact_time_diff(obs_after)
            if r_anom < self.theta_anom and delta_t < 0.1:
                self.gamma = "LIFT"
                self.grasp_retry_count = 0
            elif self.grasp_retry_count < 1:
                self.grasp_retry_count += 1  # 重试一次，握幅减 5%
            else:
                self.gamma = "FAIL"

        elif self.gamma == "LIFT":
            r_anom = self._compute_anomaly_residual({}, obs_before, obs_after)
            slip = self._compute_slip_score(obs_before, obs_after)
            if r_anom < self.theta_anom and slip < self.theta_slip:
                self.gamma = "VERIFY"
            else:
                self.gamma = "FAIL"

        elif self.gamma == "VERIFY":
            drift = np.linalg.norm(fk(obs_after.q)[:3] - fk(obs_before.q)[:3])
            if drift < 0.002:
                self.gamma = "DONE"
            else:
                self.gamma = "FAIL"

        if self.gamma == "FAIL":
            self.cycle_sigma = "RECOVER"
            self.fallback_dwell = 0
```

### 3.4 更新后的残差计算（五通道）

```python
def compute_residuals(obs0, obs1, plan, prev_plan, M, phase, attn_weights=None):
    r = {}
    # temporal
    r["tmp"] = normalized_action_diff(plan, prev_plan) if prev_plan else 0.0

    # geometric
    dx_obs = fk(obs1.q) - fk(obs0.q)
    dx_cmd = planned_cartesian_delta(plan, obs0)
    r["geo"] = norm(dx_obs - dx_cmd) / (norm(dx_cmd) + EPS)
    if obs1.depth is not None and target_visible(M, obs1):
        flow_pred = project_motion(dx_cmd, obs1.depth, obs1.camera)
        r["geo"] += LAMBDA_F * norm(obs1.flow - flow_pred) / SIGMA_FLOW

    # goal
    if phase in ("APPROACH", "PRECONTACT"):
        d0 = distance(fk(obs0.q), M.target_pose)
        d1 = distance(fk(obs1.q), M.target_pose)
        r["goal"] = goal_residual(d0, d1, planned_distance_delta(plan))
    else:
        r["goal"] = edit_score(obs0, obs1)

    # dynamic
    r["dyn"] = max(0.0, max_ratio(obs1.qdot, obs1.qddot) - 1.0)

    # anomaly (contact)
    r["anom"] = compute_anomaly_residual(obs0, obs1)

    # intent (attention alignment)
    if attn_weights is not None:
        H = -np.mean(np.sum(attn_weights * np.log(attn_weights + 1e-8), axis=0))
        Q_key = np.mean(np.sum(attn_weights[KEYWORD_INDICES, :], axis=0))
        z_H = (H - MU_H_ID) / (SIGMA_H_ID + 1e-6)
        z_Q = max(0, (MU_Q_ID - Q_key) / (SIGMA_Q_ID + 1e-6))
        r["intent"] = z_H + z_Q
    else:
        r["intent"] = 0.0

    return r

def normalized_score(r, scales):
    z = {k: r[k] / (scales[k] + EPS) for k in r}
    return (3.0 * z["dyn"] + z["tmp"] + z["geo"] + z["goal"] + z["anom"] + z["intent"])
```

### 3.5 更新后的信任门（五通道触发）

```python
def _update_mode(self, surprise):
    if self.mode == "TRUST":
        if self.cusum > H:
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
        elif self.r_anom > self.theta_anom:
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
        elif self.r_intent > self.theta_intent:  # 新增：意图不一致触发
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
    elif self.mode == "FALLBACK":
        self.fallback_dwell += 1
        if self.fallback_dwell >= RECHECK_EVERY:
            self.mode = "PROBE"
            self.fallback_dwell = 0
    elif self.mode == "PROBE":
        if not surprise and self.r_anom <= self.theta_anom and self.r_intent <= self.theta_intent:
            self.mode = "TRUST"
            self.cusum = 0.0
        else:
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
```

### 3.6 更新后的调度器（需求感知成本）

```python
def select_action(self, obs):
    allowed = self._allowed_actions()
    if not allowed:
        return "HOLD"

    # Π_grasp 进行中时的动作集限制
    if self.gamma in ("CONTACT", "LIFT", "VERIFY"):
        allowed = allowed & {"SERVO", "HOLD"}  # 禁用 LOOK/VLA/FALLBACK

    b = self.target_belief
    p = self.progress
    c = self.soft_competence()
    bmax = max(b)

    opts = []
    if "SERVO" in allowed:
        gain = c * bmax * (f(p + DELTA) - f(p))
        opts.append(("SERVO", gain, C_SERVO))
    if "LOOK" in allowed and self.phase in ("APPROACH", "PRECONTACT"):
        gain = look_gain(b, self.M, self.phase)
        opts.append(("LOOK", gain, C_LOOK))
    if "VLA" in allowed and self.budget >= C_VLA:
        c_after = c + (1 - c) * Q_VLA
        gain = (c_after - c) * bmax * f(p) + DELTA_PLAN
        # 需求感知成本
        cost = C_VLA * (1 + GAMMA_SPEED * (1 - self.D.priority.get("speed", 0.5)) 
                       if self.D else C_VLA)
        opts.append(("VLA", gain, cost))
    if "FALLBACK" in allowed:
        g = self.g_prim.get(self.current_primitive, G_PRIOR)
        gain = bmax * g * (f_geo(p + DELTA) - f_geo(p))
        opts.append(("FALLBACK", gain, C_FALLBACK))
    if "PROBE_ANOM" in allowed and self.cycle_sigma == "RECOVER":
        opts.append(("PROBE_ANOM", 1.0, C_PROBE_ANOM))

    if not opts:
        return "HOLD"
    act, gain, cost = max(opts, key=lambda o: o[1] / o[2])
    if gain / cost < LAMBDA_OPPORTUNITY:
        return "COMMIT" if "COMMIT" in allowed else "HOLD"
    return act
```

## 4. 复杂度分析

| 组件 | 时间复杂度 | 空间复杂度 | 说明 |
|---|---|---|---|
| `Ψ_demand` 解析 | `O(|u| + K)` | `O(1)` | K=20 模板，线性扫描指令字符串 |
| `r_intent` 计算 | `O(L × 30)` | `O(L × 30)` | 注意力矩阵已在 VLA 前向中产生，仅额外读取 |
| 五通道残差融合 | `O(1)` | `O(W)` | W=滑动窗口大小（如 10），常数级 |
| `Π_grasp` 状态机 | `O(1)` | `O(1)` | 确定性规则，每块常数判据 |
| VOI-MAP 需求注入 | `O(|X|)` | `O(|X|)` | 信念重归一化，X=地图栅格数（离线/异步可做） |

**总体**：单块决策延迟增加 < 2ms（注意力读取 + 残差融合 + 状态机判据），远低于 5 步块预算（~100ms），满足实时性。

## 5. 正确性论证

### 5.1 统计性质保持
**命题**：五通道残差融合后的 conformal/CUSUM 保证与四通道时相同。

**证明**：
1. `r_intent` 为确定性函数（注意力权重固定、关键词索引固定、ID 统计量冻结），不引入学习参数
2. 残差序列 `{r_b}` 在 ID 分布下仍满足交换性（维度扩展不破坏 i.i.d. 假设）
3. Split conformal 的边际覆盖保证 `\Pr(s_{B+1} > q_α) ≤ α` 仅依赖校准集与测试集交换性，与残差维度无关
4. CUSUM 的 ARL（平均运行长度）性质在增加独立通道时单调改善（更多证据源）
∎

### 5.2 需求注入的单调性
**命题**：`Ψ_demand` 的约束注入单调改善高风险任务的安全性指标。

**证明**：
1. 信念偏移 `b_0' ∝ b_0 · exp(β_risk)` 在高风险区域增加先验质量，诱导 VOI 分配更多预算给 LOOK/SERVO
2. 成本重加权 `C'(VLA) = C(VLA) · (1 + γ(1-p_speed))` 单调抑制开环动作，迫使闭环执行
3. 两者均为正向单调变换，不引入新的局部最优
∎

### 5.3 Π_grasp 终止性
**命题**：`Π_grasp` 有限状态机在有限步内必终止于 `{DONE, FAIL}`。

**证明**：
1. 状态空间有限：`|Γ| = 6`
2. 转移图无环（除 CONTACT 重试自环，但重试计数有上界 `max_retry=1`）
3. 每个块最多推进一步或触发 FAIL
4. 最大步数：`PREGRASP→APPROACH→CONTACT(≤2次)→LIFT→VERIFY→DONE` = 6 个块
∎

## 6. 更新的实验设计与门（累积）

### 6.1 继承门（G0–G12 + G17–G19 继续有效）

### 6.2 新增门 G20–G22

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| **G20** | `Ψ_demand` 解析覆盖率与需求注入收益 | 32 任务指令关键词召回 ≥ 80%；高风险任务成功率 ↑ ≥ 4pp | 砍掉 `Ψ_demand`，恢复原始 VOI-MAP |
| **G21** | `r_intent` 校准与 OOD-E 检测力 | ID 惊讶率 ≤ 0.15；OOD-E AUROC ≥ 0.75；提前 ≥ 2 块触发 | 砍掉 `r_intent` 通道，恢复四通道 ZEST |
| **G22** | `Π_grasp` 子阶段通过率与抓取收益 | 单阶段通过率 ≥ 90%；完整流程抓取成功率 ↑ ≥ 6pp | 砍掉 `Π_grasp`，恢复单阶段 GRASP |

### 6.3 预注册假设（累积 H1–H20，见想法区 §4）

### 6.4 真机单任务 A/B（更新）

| 项 | 设计 |
|---|---|
| 任务 | PlugInEthernet、HangCup、StackBowls、OpenDrawer、FoldTowel、**PourWater**、**TransportFragile**、**GraspThin** 新增 3 个高风险/精细抓取任务 |
| 次数 | 每任务 5 次，配对：ZEST-R1 vs ZEST-R2(Ψ_demand) vs ZEST-R2(r_intent) vs ZEST-R2(Π_grasp) vs ZEST-R2(full) |
| 主端点 | 成功率；次端点：成功率/成本、OOD 检测延迟、恢复率、fallback 率、p99、LOOK 比例、抓取子阶段通过率 |
| 统计 | 配对差值 + bootstrap 95% CI |
| 门 | G20：召回 ≥ 80% & 高风险 ↑ 4pp；G21：AUROC ≥ 0.75 & 提前 2 块；G22：单阶段 ≥ 90% & 整体 ↑ 6pp |

### 6.5 全量（更新）

| 项 | 设计 |
|---|---|
| 任务 | 32×10 |
| 指标 | 总成功率、步骤分、p99、timeout、平均 VLA 调用、fallback 率、OOD 检测率、`r_anom` AUROC、`r_intent` AUROC、`θ_prim` 调整后成功率、抓取子阶段通过率、需求解析召回率 |
| 门 | G6 继续有效；新增 p99 ≤ 150ms（含注意力提取开销） |

### 6.6 消融与阴性对照（更新）

| 消融 | 目的 | 预期 |
|---|---|---|
| 去掉 `Ψ_demand` | 需求解析是否有用 | 高风险任务成功率下降；G20 不通过 |
| 去掉 `r_intent` | 意图残差是否有用 | OOD-E AUROC 下降；G21 不通过 |
| 去掉 `Π_grasp` | 抓取策略库是否有用 | 抓取成功率下降；G22 不通过 |
| 随机注意力 | `r_intent` 阴性对照 | 不应提升 |
| 打乱模板库 | `Ψ_demand` 阴性对照 | 不应提升 |
| 固定单阶段 GRASP | `Π_grasp` 阴性对照 | 不应提升 |

## 7. 更新的风险与合规（累积）

### 7.1 单模型合规（更新）

| 模式 | 做法 | 风险 | 建议 |
|---|---|---|---|
| C1 确定性几何 | 残差、融合、conformal/CUSUM、原语、需求解析、抓取 FSM | 最低 | 主推 |
| C2 符号 backchannel | 相位/子目标/需求/意图符号由几何/注意力/语法派生 | 低 | 主推 |
| C3 同 checkpoint 特征 | 注意力权重复用、VLA encoder 特征复用 | 低–中 | 需时用，写清 |
| C5 接触代理无 F/T | 关节电流 + 虚拟力预测 | 中 | 声明近似 |
| 禁止 | 第二个学习模型；在线学习残差；训练失败检测器；微调 VLA | 高 | 不做 |

### 7.2 更新的风险表（累积关键项）

| 风险 | 影响 | 缓解 |
|---|---|---|
| **OOD-G 不可检测** | 目标错时系统自信执行 | 命题 7 边界；独立语义检查/任务清单/复检 |
| **`r_anom` 前端太弱** | 无 F/T 下接触代理噪声大 | 多模态组合；辅助通道定位 |
| **`θ_prim` 调整过激** | 尺寸估计误差导致前置条件失效 | `α_max` 截断；域检查把关 |
| **生命周期 desync** | 网络抖动导致状态不匹配 | `τ_max` guards；心跳；掉线默认 HOLD |
| **复检破坏接触** | 探针引入滑落 | 仅 APPROACH/PRECONTACT/边界探针 |
| **`Ψ_demand` 误解析** | 关键词触发错误约束 | 模板人工审核；冻结；低优先级可被 VOI 覆盖 |
| **`r_intent` 注意力不可靠** | checkpoint 注意力无语义对齐 | G21 校准把关；AUROC 低即砍掉 |
| **`Π_grasp` 过刚性** | 特殊物体不符合预设分支 | FAIL 即 RECOVER 降级；不强制完成 |
| **抓取类型误判** | 包围盒误差选错预抓姿态 | 语义类别辅助；PREGRASP 碰撞检测兜底 |

## 8. 一句话押注（累积）

**第 1 轮用「动作-观测一致性」决定信不信策略；本轮用「需求显性化约束预算、意图注意力度量对齐、抓取子阶段验证接触」构建三重语义护栏：让零样本失败从「结构化受控退步」进化为「需求感知、意图对齐、接触验证」的全链路语义一致性保障。**

## 9. 本轮最大的风险

**注意力语义对齐的不可靠性**：`r_intent` 完全依赖 VLA 冻结 checkpoint 的交叉注意力权重具有「语言 token → 动作步骤」的语义对齐性。但现实中，许多 VLA checkpoint 的注意力矩阵呈现近均匀分布、或关注停用词、或与动作因果关系微弱。若 ID 校准集上 `r_intent` 无法形成可分离的分布（AUROC < 0.6），该通道将被 G21 砍掉，导致本轮「意图理解」增量归零，且可能引入额外的计算开销与假阳性干扰现有四通道融合。这是本轮三个增量中唯一**依赖模型内部未经验证属性**的风险点，必须在合成实验 G21 阶段严格把关。
<!-- ARTIFACT:END -->
