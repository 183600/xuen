# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 玄 · 第 1 轮灵感循环 · ZEST-VLA 突量增补

## 0. 前文承接与本轮划分

### 0.1 前人基础
在第 15 轮 ZEST-VLA 基础上：VOI-MAP 之上的胜任力层，三个自监督残差（时序/几何/目标进度），self-normalized conformal + CUSUM 信任门，几何原语语法降级，OOD-E/OOD-S 可检测边界，OOD-G 固有盲区。所有约束（单模型、无新参数、无 test-time 权重更新）继续生效。

### 0.2 三个灵感词的落地点

| 词 | 落地位置 | 与现有架构的关系 |
|---|---|---|
| **异常检测** | 残差四元组的第 4 个通道 `r_anom`；CUSUM 门控的异常输入 | 在现有三个残差基础上增加，无新参数、确定性函数 |
| **跨任务泛化** | 任务条件化原语参数调整 `θ_prim(u,M)`；几何语法的参数空间 | 手写语法的参数化扩展，不学习、不改变结构 |
| **机器人操作系统** | 显式生命周期状态机 + 超时 guards + 主题状态发布 | 部署层，不改变核心决策算法 |

### 0.3 本轮不做什么

- 不训练任何新网络/新损失/新模型；`r_anom` 是确定性函数，`θ_prim` 是几何映射，生命周期是状态机
- 不做 test-time weight update；不微调 VLA；不做自监督预训练
- 不假设腕部相机有内参、不假设有深度图、不假设有 F/T 传感器
- 不把合成实验当作真机证据
- 不承诺解决 OOD-G（VLA 和地图共享同一错误先验）；本轮明确保留该边界

## 1. 异常检测增量：r_anom  contact anomaly residual

### 1.1 直觉
VLA 的 30 步块可能在几何上“一致”，但在接触层面已经错了——例如抓取时物体已经滑动、或者插入时已经碰撞。这些在观测上是‘隐形’的，因为没有人工标签，但机器人的关节电流和运动学本身就携带了关于接触一致性的信号。利用已有的虚拟力控制器预测的接触力与关节电流推导的接触力代理之间的差异，可以在不增加任何硬件的情况下得到一个免费的接触一致性评分。

### 1.2 形式化定义
设 VLA 输出的 30 步块在第 `b` 个 5 步块结束时，观测 `o_b` 包含关节位置 `q_b`、速度 `qdot_b`，以及头双目 RGB/深度信息。虚拟力控制器在第 `b` 块内产生预测接触力：

```math
F^{\mathrm{pred}}_b = K_p \cdot (x^{\mathrm{des}}_b - x_b)
```

其中 `K_p` 是笛卡尔刚度矩阵、`x^{\mathrm{des}}_b` 是期末目标位姿、`x_b = \mathrm{fk}(q_b)` 是正向运动学得到的当前位姿。当发生接触时，定义接触指示：

```math
c^{\mathrm{obs}}_b = \mathbb{1}\big[\|qdot_b\| < \theta_{\mathrm{vel}} \land \mathrm{penetration}_b > \theta_{\mathrm{pen}}\big]
```

其中 `penetration_b` 通过头双目视觉估计的视差突变检测得到。随后构造接触力代理：

```math
F^{\mathrm{proxy}}_b = c^{\mathrm{obs}}_b \cdot \mu \cdot |I(q_b)|
```

其中 `I(q_b)` 是关节电流向量，`\mu` 是一个固定的摩擦系数近似（如 0.3）。最后定义异常残差：

```math
r^{\mathrm{anom}}_b = \frac{\|F^{\mathrm{pred}}_b - F^{\mathrm{proxy}}_b\|}{\|F^{\mathrm{pred}}_b\| + \epsilon}
```

该残差在无接触时趋于 0（因为 `c^{\mathrm{obs}}_b = 0`），在接触不一致时取值增大。所有计算均使用已有传感器，无需新增硬件。

### 1.3 与 conformal/CUSUM 的集成
`r^{\mathrm{anom}}_b` 与其他三个残差一并归一化融合：

```math
\sigma_{\mathrm{anom},b} = 1.4826 \cdot \mathrm{MAD}\big(\{r^{\mathrm{anom}}_{b-W+1},\dots,r^{\mathrm{anom}}_b\}\big) + \epsilon_{\mathrm{anom}}
```

```math
z^{\mathrm{anom}}_b = r^{\mathrm{anom}}_b / \sigma_{\mathrm{anom},b}, \qquad
s_b = w_{\mathrm{tmp}} z^{\mathrm{tmp}}_b + w_{\mathrm{geo}} z^{\mathrm{geo}}_b + w_{\mathrm{goal}} z^{\mathrm{goal}}_b + w_{\mathrm{anom}} z^{\mathrm{anom}}_b
```

固定权重 `w_{\mathrm{anom}} = 1`（与其他三个通道 `w=1` 相同）。因为 `r^{\mathrm{anom}}_b` 是确定性函数，`s_b` 的 self-normalized conformal 校准和 CUSUM 变点检测保持不变的理论性质——只是统计空间从 3 维扩展到了 4 维，这并不违反任何假设，因为交换性仅依赖于残差序列的 i.i.d. 性质，而不是维度数量。

### 1.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H6 | `r_anom` 能区分接触内部异常（滑动、碰撞）与正常接触，AUROC ≥ 0.7 | AUROC < 0.55 | 主 |
| H7 | ZEST+`r_anom` 在含接触异常的 OOD 上成功率相对提升 ≥ 3pp | 相对无 `r_anom` 无提升 | 主 |

## 2. 跨任务泛化增量：任务条件化原语参数调整

### 2.1 直觉
几何原语库是手写的、确定性的，覆盖了 32 个任务的典型情况。但真实任务中物体尺寸、容器几何形状可能与训练任务不同。例如「抓取一个 5cm 宽的盒子」vs「抓取一个 12cm 宽的盒子」，GRASP 原语的握幅参数需要调整。既然不可以学习新参数，就利用语义地图已经估计的目标尺寸信息，通过一个固定的几何缩放因子来微调原语参数——这还是「免费的」，因为目标尺寸 already 在语义地图上了。

### 2.2 形式化定义
设每个原语 `prim` 有基础参数 `θ_base^{prim}`（如 GRASP 的握幅、INSERT 的插入深度）。语义地图 `M` 为每个标记对象提供估计的包围盒半径 `r_{\mathrm{obj}}`。定义任务条件化参数调整因子：

```math
\alpha^{\mathrm{prim}}_b = \lambda^{\mathrm{prim}} \cdot \frac{|r_{\mathrm{obj}}(b)| - \mu^{\mathrm{prim}}_{\mathrm{ref}}}{\mu^{\mathrm{prim}}_{\mathrm{ref}}}
```

其中 `\lambda^{\mathrm{prim}}` 是原语专用的固定敏感度系数（预先在小验证集上手工调优，正式评测前冻结），`\mu^{\mathrm{prim}}_{\mathrm{ref}}` 是该原语的参照物理尺寸。最终使用的参数为：

```math
\theta^{\mathrm{prim}}_b = \theta^{\mathrm{base}}_{\mathrm{prim}} \cdot (1 + \alpha^{\mathrm{prim}}_b)
```

关键限制：`|\alpha^{\mathrm{prim}}_b| \leq \alpha_{\max}^{\mathrm{prim}}`（每个原语预先设定的最大调整比例，防止过度调整导致几何不可行）。所有调整都是打开-loop的、确定性的，不涉及任何权重学习。

### 2.3 域检查的修正
参数调整后的原语在域检查阶段仍需通过 `dom(\sigma(u))` 的几何判定。参数调整仅影响具体的数值（如握幅大小），不改变语法结构。如果调整后的参数使得原语前置条件不满足（如握幅过宽导致无法闭合），域检查判定为 `unknown`，FALLBACK 自动不可用。

### 2.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H8 | `θ_prim` 调整后的几何原语在几何可分解的跨任务上，成功率相对固定参数至少 +5pp | 域检查通过率下降或成功率无提升 | 主 |
| H9 | 任务条件化参数调整在物体尺寸差异 ≥ 30% 的任务上有正收益；在差异 < 10% 的任务上无效 | 调整比例超出 `\alpha_{\max}` 截断区域 | 主 |

## 3. 机器人操作系统增量：显式生命周期与鲁棒性层

### 3.1 直觉
真实机器人部署不是一个函数调用那么简单。网络抖动、话题超时、参数服务竞争、节点崩溃都会发生。当前的 monolithic `get_action` 设计没有任何容错机制——一旦 VLA 推理超时或返回错误形状，系统就会进入未定义状态。灵感词「机器人操作系统」提醒我们应该给算法提供原生的鲁棒性基础设施：生命周期状态、超时守护、话题状态发布，这些是 ROS2 时代的基础设施模式，可以移植到任何机器人软件栈中。

### 3.2 形式化定义
定义政策的生命周期状态机 `\sigma \in \{\mathrm{INIT}, \mathrm{GROUND}, \mathrm{TRACK}, \mathrm{RECOVER}, \mathrm{HOLD}\}`：

- **INIT**：初始状态。等待第一帧观测，完成语义地图初始化，转移至 `GROUND`。超时时间 `\tau_{\mathrm{INIT}} = 5` 秒。
- **GROUND**：地图就绪状态。VOI-MAP 可用，任务指令解析可进行。在此状态下周期性发布 `map_ready` 话题。若 CUSUM 连续 `r` 个块触发，转移至 `RECOVER`。
- **TRACK**：正常跟踪状态。每个块执行完毕后发布 `block_done` 话题，携带当前 `S_b`、模式、成功率估计。若检测到 `r_anom` 异常或 CUSUM 达阈，转移至 `RECOVER`；若预算 `B_b` 耗尽，转移至 `HOLD`。
- **RECOVER**：恢复状态。执行 anomal  探针（类似 FALLBACK 中的 SERVO 探针），检测当前是否恢复正常。不惊讶则 `σ ← TRACK`，持续惊讶则 `σ ← HOLD`。超时时间 `\tau_{\mathrm{RECOVER}} = 10` 秒，超时则直接 `σ ← HOLD`。
- **HOLD**：安全停止状态。所有执行停止，发布 `safe_stop` 话题，保持当前关节位置。仅通过外部复位请求恢复。

形式化转移规则：

```math
\sigma_{t+1} = 
\begin{cases}
\mathrm{RECOVER}, & \text{if } CUSUM_t > h \lor r^{\mathrm{anom}}_t > \theta_{\mathrm{anom}} \\
\mathrm{HOLD}, & \text{if } B_t \leq 0 \lor \sigma_t = \mathrm{RECOVER} \land \tau_{\mathrm{RECOVER}} \text{ elapsed} \\
\mathrm{TRACK}, & \text{if } \sigma_t = \mathrm{RECOVER} \land \text{probe not surprised} \\
\mathrm{TRACK}, & \text{if } \sigma_t = \mathrm{GROUND} \land \text{planning complete} \\
\mathrm{TRACK}, & \text{otherwise}
\end{cases}
```

所有状态转移都是确定性的，由门控逻辑驱动，不涉及学习。

### 3.3 与核心算法的解耦
生命周期层只在以下层面与核心算法交互：

1. **输入**：每个块的 `S_b`, `c_b`, `r_anom_b`, `B_b`（已在 ZEST-VLA 计算好）
2. **输出**：允许执行的动作集 `A_adm(\sigma)` 的修正（仅在 `RECOVER`/`HOLD` 时修正，`TRUST`/`FALLBACK` 的动作集不变）
3. **状态发布**：不影响决策逻辑，仅提供监控和安全网

具体而言，`A_adm(\sigma)` 的修正仅在 `\sigma = \mathrm{RECOVER}` 时将 `SERVO` 替换为 `PROBE`（探针块），在 `\sigma = \mathrm{HOLD}` 时将整个动作集限制为 `HOLD`。在 `\sigma = \mathrm{TRACK}` 和 `\sigma = \mathrm{GROUND}` 下，动作集完全由 ZEST-VLA 的信任门决定，不受生命周期层影响。

### 3.4 可证伪假设

| 编号 | 假设 | 证伪条件 | 级别 |
|---|---|---|---|
| H10 | 生命周期状态机在真机部署中，p99 延迟 ≤ 150ms（不因状态转移抖动导致） | p99 > 150ms 或 状态频繁抖动 | 主 |
| H11 | `\sigma = \mathrm{RECOVER}` 模式下，复钵探针在 2 个块内能确认异常清除，恢复 TRACK 模式 | 探针连续 3 个块仍惊讶，或恢复时间超过 `\tau_{\mathrm{RECOVER}}` | 主 |

## 4. 更新的证伪假设表

原有假设 H1–H5 继续生效，新增假设 H6–H11 与本轮增量相关。原有的 H4（Beta 后验）已在上一轮被证伪并从主算法中剪枝，本轮不重复审议。

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

## 5. 风险表更新

| 风险 | 影响 | 缓解 |
|---|---|---|
| **OOD-G 不可检测** | 目标错时系统自信执行 | 命题 7 明确边界；独立语义检查/任务清单/复检 |
| **`r_anom` 前端太弱** | 无 F/T 传感器下接触一致性代理噪声大 | 多模态组合（视觉穿透检测+电流异常+动力学突变）；`r_anom` 为辅通道，非主诊断 |
| **`θ_prim` 调整过激** | 语义地图尺寸估计误差导致原语前置条件失效 | `|\alpha^{\mathrm{prim}}_b| \leq \alpha_{\max}` 截断；域检查把关 |
| **生命周期状态 desync** | 真机网络抖动导致状态机与实际状态不匹配 | `\tau_{\max}` 超时 guards；每个状态的心跳检测；掉线默认 HOLD |
| **复检在 CONTACT 中破坏接触** | RECOVER 探针在接触阶段引入滑落 | 只在 APPROACH/PRECONTACT 或原语边界探针；CONTACT/CARRY 禁止 |
| **VLA 推理超时** | VLA server 无响应或返回错误形状 | 生命周期层设定 `VLA` 调用超时，超时后自动进入 `HOLD` 或 `RECOVER` |
<!-- IDEA:END -->
<!-- ARTIFACT:START -->
# 玄 · 第 1 轮灵感循环 · ZEST-VLA 突量增补

## 0. 结论与边界（续）

### 0.1 一句话结论（续）
第 15 轮将 VLA 执行治理提升为风险受控的信任门，本轮将「接触一致性、任务条件化参数调整、生命周期鲁棒性」三个增量编入算法，仍不训练任何新参数、不引入第二个学习模型，零样本泛化从「系统级降级」升级为「结构化鲁棒系统」。

### 0.2 本轮新增证据等级

| 等级 | 含义 | 本报告中的例子 |
|---|---|---|
| A | 官方文档、提交模板、数据集元数据、经典文献直接核实 | 规则/API、32 任务、33,276 eps、WLA `chunk_size=30`、无 depth/force |
| B | 本轮在公式/合成实验/逻辑推导上做的分析，可复现 | `exp/zest_sim.py` 的静态 OOD、瞬态恢复、残差消融、灵敏度；公式推导见 §§1–4 |
| C | 设计假设，需 G0–G16 验证 | 真实桌面残差分布、几何原语覆盖率、真机零样本收益、生命周期真机 A/B |
| D | 设计思路或哲学论述，非形式化证明 | 直觉动机、跨任务泛化边界、ROS2 移植方案 |
| U | 未核验，不得进入论证链 | 形如 `2609.xxxxx` 的异常 arXiv 编号 |

### 0.3 本轮不做什么（续）

- 不训练第二个检测/分割/语言/失败检测模型；残差、融合、门控全是确定性函数与在线一维统计
- 不做 test-time weight update；不微调 VLA；不做自监督预训练
- 不承诺解决 OOD-G（VLA 和地图共享同一错误先验）；本报告明确保留该信息论边界
- 不在无 F/T 传感器环境下把 `r_anom` 当作绝对诊断；其地位为「辅助通道」

## 1. 承接：前人基础上的增量

### 1.1 已解决（续）

- 第 10 轮：FACT-VLA 把单模型 BC 相位化，降低长程漂移。
- 第 11 轮：GEO-RESIDUAL 用几何残差 + 编辑检测识别执行中的异常。
- 第 12 轮：30 步开环 → 5 步闭环；DG-KEYFRAME 相对目标。
- 第 13 轮：WAVE-SERVO 用虚拟力 + TD-PC 给出离散时延下的无源性与限幅。
- 第 14 轮：VOI-MAP 把语言 grounding 成地图上的目标分布，用边际信息增益/成本在 `SERVO/LOOK/VLA/COMMIT` 间分配预算。
- **第 15 轮（本轮）：ZEST-VLA 在原有胜任力层上增量扩展**，增加接触异常残差 `r_anom`、任务条件化原语参数调整 `θ_prim`、显式生命周期状态机。

**保留**：FACT-VLA 的相位化 BC、GEO-RESIDUAL 的几何残差与编辑检测、CHUNK-SERVO 的 30/5 双频、WAVE-SERVO 的 TD-PC 与相位阻抗表、VOI-MAP 的语义地图/语音 grounding/预算调度、单模型合规、预注册统计纪律。

**升级**：从「目标不确定性」升级到「执行者胜任力不确定性」；从「固定调度」升级到「带硬约束的信任门 + 软 VoI」；从「模型级零样本」升级到「系统级零样本降级」；**新增：从「无鲁棒性保障」升级到「结构化鲁棒性层」**。

**剪枝**：不做自监督预训练；不做 test-time weight update；不训练失败检测器；不引入第二个学习模型；Beta 后验下界经合成实验证伪后从主门控中移除。

## 2. 更新的符号与形式化

### 2.1 冻结的 VLA 与执行层（续）

设 VLA 为 `π_θ`，`θ` 冻结。给定观测 `o_t` 和指令 `u`，它输出 30 步动作块 `A_t = (a_{t,0},...,a_{t,29})`。执行层按 5 步块执行，块索引 `b=0,...,5`。第 13 轮的 WAVE-SERVO 把每个块映射为安全的关节/末端轨迹；本轮不改变这个映射。

**新增符号**：
- `r^{\mathrm{anom}}_b`：第 `b` 个 5 步块结束后的接触异常残差
- `θ^{\mathrm{prim}}_b`：第 `b` 个块执行的几何原语参数调整量
- `\sigma_t \in \{\mathrm{INIT},\mathrm{GROUND},\mathrm{TRACK},\mathrm{RECOVER},\mathrm{HOLD}\}`：生命周期状态
- `\tau_{\max}^{\cdot}`：各状态的最大驻留时间/超时阈值

### 2.2 四个自监督残差向量（续）

在块 `b` 结束后，在之前的三个残差基础上增加：

**接触异常残差（anomaly）**

```math
r^{\mathrm{anom}}_b =
\frac{\|K_p \cdot (x^{\mathrm{des}}_b - \mathrm{fk}(q_b)) - c^{\mathrm{obs}}_b \cdot \mu \cdot |I(q_b)|\|}
{\|K_p \cdot (x^{\mathrm{des}}_b - \mathrm{fk}(q_b))\| + \epsilon}
```

其中 `K_p` 是虚拟力控制器的笛卡尔刚度，`x^{\mathrm{des}}_b` 是期末目标位姿，`\mathrm{fk}(q_b)` 是正向运动学位姿，`c^{\mathrm{obs}}_b = \mathbb{1}[\|qdot_b\| < \theta_{\mathrm{vel}} \land \mathrm{penetration}_b > \theta_{\mathrm{pen}}]` 是观测到的接触指示（视差突变 + 关节速度临界），`\mu` 是固定的摩擦系数近近似（如 0.3），`I(q_b)` 是关节电流向量。该残差在无接触时趋于 0，在接触不一致时取值增大。

**目标进度残差（goal-progress，续）**

见 existing 2.2；在 CONTACT/CARRY 仍复用第 11 轮的 edit/slip 分数。

**动力学残差（dynamic，续）**

见 existing 2.2。

**归一化与融合（续）**

每个通道用滑动 MAD 估计尺度：

```math
\sigma_{k,b}=1.4826\cdot \mathrm{MAD}(\{r^k_{b-W+1},...,r^k_b\})+\epsilon_k
```

```math
z^k_b = r^k_b/\sigma_{k,b},\qquad
s_b = \sum_k w_k z^k_b
```

固定权重，`w_dyn=3`，`w_tmp=w_geo=w_goal=w_anom=1`。四个通道全部固定权重，均不训练。

### 2.3 自归一化与 conformal 校准（续）

用一个 ID 校准集（例如 5 个已知 ID 任务 × 10 episodes）收集四个通道的残差分数，取 `(1-α)` 经验分位数：

```math
q_\alpha = \mathrm{Quantile}_{1-\alpha}\{s_b^{\mathrm{cal}}\}
```

其中 `s_b = Σ w_k z^k_b` 包含四个通道。对测试块定义惊讶指示：

```math
e_b = \mathbb{1}[s_b > q_\alpha]
```

在 ID 与测试残差可交换的假设下，split conformal 给出边际保证：

```math
\Pr(s_{B+1} > q_\alpha) \le \alpha
```

这是边际保证，不是条件保证；校准集与测试分布不可交换（真实 OOD）时，保证失效，此时靠 CUSUM 和在线尺度估计兜底。

### 2.4 CUSUM 信任门与滞回/复检（续）

定义 CUSUM 与之前一致：

```math
S_b = \max(0, S_{b-1} + e_b - \alpha - k), \qquad S_0 = 0
```

当 `S_b > h` 时触发 OOD，进入 `FALLBACK` 模式。`k` 是漂移容忍量，`h` 是阈值。触发后的行为包含：

- 在 `FALLBACK` 模式中禁用 `SERVO`（复检探针除外）；
- 每 `r` 个块执行一次 `SERVO` 探针；若探针不惊讶，则 `S_b ← 0`，回到 `TRUST`；
- 若连续 `r` 次探针都惊讶，保持 `FALLBACK`；
- **新增**：当 CUSUM 触发或 `r_anom_b > \theta_{\mathrm{anom}}`（经校准的异常阈值）时，同时视为 OOD 信号，加速进入 FALLBACK；
- 复检只在 APPROACH/PRECONTACT 或几何原语的边界允许，CONTACT/CARRY 禁止。

软胜任力用于 VOI 的成功模型，不用于触发：

```math
c_b = 1 - \frac{1}{W}\sum_{i=0}^{W-1} e_{b-i}
```

### 2.5 胜任力感知的 VOI 调度（续）

状态：

```math
x_b = (b_b, p_b, \phi_b, B_b, M_b, c_b, S_b, r^{\mathrm{anom}}_b)
```

动作与成本表增加一条：

| 动作 | 成本 | 作用 | 门控约束 |
|---|---|---|---|
| ...（existing rows）| ... | ... | ... |
| **`PROBE_ANOM`** | **`c_p`** | **发送异常探针块，诊断 `r_anom`** | 仅 `\sigma = RECOVER`；在 RECOVER 中每 `r` 块触发 |

调度规则中，`TRUST` 的动作集 unchanged；`FALLBACK` 中除了几何原语外，也可选 `PROBE_ANOM`；`RECOVER` 中的动作集被限制为 `{PROBE_ANOM, HOLD}`，其他动作被屏蔽。

### 2.6 任务条件化原语参数调整

#### 2.6.1 几何原语库（续）

见 existing 2.6；每个原语 `prim` 有基础参数 `θ_base^{prim}`。现额外定义：

- GRASP：基础握幅 `w_base`，调整后握幅 `w_b = w_base · (1 + α_b)`，`α_b = λ_grasp · (|r_obj(b)| - μ_ref) / μ_ref`
- INSERT：基础插入深度 `d_base`，调整后插入深度 `d_b = d_base · (1 + α_b)`，`α_b = λ_insert · (|r_obj(b)| - μ_ref) / μ_ref`
- LIFT：基础升高高度 `h_base`，调整后高度 `h_b = h_base · (1 + α_b)`，`α_b = λ_lift · (|r_obj(b)| - μ_ref) / μ_ref`

#### 2.6.2 参数调整的域检查修正

在 `plan_primitives` 规划器运行后，于最终确定的原语序列上再进行一次参数适配检查：

```python
def adapt_and_check_primitives(seq, M):
    seq_adapted = []
    for prim, args in seq:
        # 几何参数适配
        args_prim = adapt_primitive_params(prim, args, M)
        # 前置条件检查
        if not precondition(args_prim, M):
            return None  # 域检查失败，FALLBACK 不可用
        seq_adapted.append((prim, args_prim))
    return seq_adapted
```

所有适配都是打开-loop的、确定性的、无学习的。`λ_grasp`, `λ_insert`, `λ_lift` 在小验证集上手工调优后必须在正式评测前冻结。

### 2.7 显式生命周期与鲁棒性层

#### 2.7.1 生命周期状态机

```math
\sigma \in \{\mathrm{INIT},\mathrm{GROUND},\mathrm{TRACK},\mathrm{RECOVER},\mathrm{HOLD}\}
```

状态转移图：

```text
INIT → GROUND → TRACK ⇄ RECOVER → HOLD
     ▲              │
     │              └─⇅ (外部复位)
     └─ 编辑检测/编辑检测 → GROUND
```

形式化转移规则（每个块结束后执行）：

```math
\sigma_{t+1} = 
\begin{cases}
\mathrm{RECOVER}, & \text{if } CUSUM_t > h \lor r^{\mathrm{anom}}_t > \theta_{\mathrm{anom}} \\
\mathrm{HOLD}, & \text{if } B_t \leq 0 \lor (\sigma_t = \mathrm{RECOVER} \land \tau_{\mathrm{RECOVER}} \text{ elapsed}) \\
\mathrm{TRACK}, & \text{if } \sigma_t = \mathrm{RECOVER} \land \text{probe not surprised} \\
\mathrm{TRACK}, & \text{if } \sigma_t = \mathrm{GROUND} \land \text{planning complete} \\
\mathrm{TRACK}, & \text{if } \sigma_t = \mathrm{INIT} \land \text{map initialized} \\
\mathrm{TRACK}, & \text{otherwise}
\end{cases}
```

其中 `\theta_{\mathrm{anom}}` 是经 conformal 校准得到的异常阈值的第 90% 分位数（或经验确定的固定值），`\tau_{\mathrm{RECOVER}}` 是重新探针的最大驻留时间（如 10 个块）。

#### 2.7.2 各状态的详细行为

- **INIT**：
  - 等待第一帧观测，初始化语义地图 `M`（第 14 轮 VOI-MAP 流程）
  - 发布 `map_ready` 话题
  - 当地图中至少有 3 个标记对象且初始化无误 → `σ ← GROUND`
  - 超时 `\tau_{\mathrm{INIT}} = 5` 秒 → 强制 `σ ← GROUND`（即使地图不完全）

- **GROUND**：
  - VOI-MAP 调度完全可用：`SERVO/LOOK/VLA/COMMIT`
  - 周期性发布 `map_ready` 话题（包含当前目标分布 `b_t`）
  - 若 CUSUM 连续 `r` 个块触发 → `σ ← RECOVER`
  - 若编辑检测到结构性变化 → `σ ← GROUND`（重新 ground）

- **TRACK**：
  - 核心决策循环：ZEST-VLA 信任门 → VOI-MAP 调度 → WAVE-SERVO 执行
  - 每个块结束后发布 `block_done` 话题，载荷：`{S_b, mode, c_b, selected_action, success_estimate}`
  - 若 `r_anom_b > \theta_{\mathrm{anom}}` → `σ ← RECOVER`（加速路径）
  - 若预算 `B_t` 耗尽 → `σ ← HOLD`
  - 若 VLA 推理超时（p99 > 150ms） → `σ ← HOLD`，返回上一合法 chunk

- **RECOVER**：
  - 核心行为：发送 `PROBE_ANOM` 块，即用 SERVO 探针执行一小段虚拟力控制，诊断当前接触状态是否恢复正常
  - 探针结果：`r_anom_probe` 计算后与 `\theta_{\mathrm{anom}}` 比较
    - 不惊讶 (`r_anom_probe ≤ \theta_{\mathrm{anom}}`) → `σ ← TRACK`，`S_b ← 0`
    - 惊讶 (`r_anom_probe > \theta_{\mathrm{anom}}`) → 继续保持 RECOVER，`fallback_dwell += 1`
  - 超时 `\tau_{\mathrm{RECOVER}} = 10` 个块 → 直接 `σ ← HOLD`
  - 发布 `recovering` 话题，载荷：`{current_mode, anomaly_score, dwell}`

- **HOLD**：
  - 所有执行停止，发布 `safe_stop` 话题
  - 保持当前关节位置，不发送新的末端轨迹
  - 仅通过外部复位请求（服务调用或重启）恢复至 `GROUND`
  - 发布 `hold` 话题

#### 2.7.3 与核心算法的解耦

生命周期层只在以下层面与核心算法交互：

1. **输入**：每个块的 `S_b`, `c_b`, `r_anom_b`, `B_b`（已在 ZEST-VLA 计算好），以及当前状态 `\sigma_t`
2. **输出**：
   - 允许执行的动作集 `A_{adm}(\sigma)` 的修正
   - 状态发布话题（`map_ready`, `block_done`, `recovering`, `safe_stop`, `hold`）
3. **状态不直接影响决策逻辑**：在 `\sigma = \mathrm{TRACK}` 和 `\sigma = \mathrm{GROUND}` 下，动作集完全由 ZEST-VLA 的信任门决定，不受生命周期层影响。只有 `\sigma = \mathrm{RECOVER}`/`\mathrm{HOLD}` 时，动作集才被修正。

**安全继承**：生命周期层不新增执行通路，只在已有的安全动作集内进行状态管理和超时保护。所有状态下的执行仍经过 WAVE-SERVO 的 TD-PC 与限幅。

## 3. 更新的算法

### 3.1 分层结构（续）

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
        │  │ L4  ZEST-VLA 胜任力层（本轮增量）                   │  │
        │  │  residual quartet → conformal/CUSUM → trust gate   │  │
        │  │  TRUST / FALLBACK / HOLD + soft competence c_b     │  │
        │  │  + r_anom channel + θ_prim parameter adaptation   │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ allowed action set           │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L3  VOI-MAP（第 14 轮）                             │  │
        │  │  semantic map, grounding, budget scheduler          │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ selected action              │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L2  WAVE-SERVO（第 13 轮）                          │  │
        │  │  virtual force, TD-PC, phase impedance, clamps      │  │
        │  └───────────────────────┬────────────────────────────┘  │
        │                          │ 30/5 chunk                   │
        │  ┌───────────────────────▼────────────────────────────┐  │
        │  │ L1  VLA server（唯一学习模型，冻结）                 │  │
        │  │  UnifoLM-WLA-1.0, 30-step plan                      │  │
        │  └────────────────────────────────────────────────────┘  │
        └──────────────────────────────────────────────────────────┘
                                                                     │
                                                                        ▼
                                                   ┌───────────────────────┐
                                                   │ L5 ロबUSTNESS 层        │
                                                   │ lifecycle σ + timeout   │
                                                   │ topic status publish    │
                                                   └───────────────────────┘
```

**算法步骤（总览，续）**

在原有 8 步基础上增：

9. **接触异常残差计算**：每块结束后计算 `r_anom_b`（见 §2.2），并入归一化融合得到 `s_b`。
10. **任务条件化参数调整**：在 FALLBACK 原语规划前，依据语义地图目标尺寸计算 `θ_prim_b` 并适配原语参数（见 §2.6）。
11. **生命周期状态转移**：依据 `S_b`, `r_anom_b`, `B_b` 以及超时时间更新 `\sigma_t`（见 §2.7）。
12. **动作集修正**：根据 `\sigma_t` 修正 `A_adm`（见 §2.7.2）。
13. **状态发布**：发布对应的 ROS2 话题（见 §2.7.2）。

### 3.2 更新后的主循环伪代码

```python
class ZestPolicy:
    def __init__(self, calib_scores, lambda_grasp, lambda_insert, lambda_lift):
        self.M = SemanticMap()              # round 14
        self.plan = None
        self.prev_plan = None
        self.mode = "TRUST"                 # TRUST / FALLBACK / HOLD
        self.cusum = 0.0
        self.q_alpha = conformal_quantile(calib_scores, alpha=0.12)
        self.surprise_window = deque(maxlen=W)
        self.fallback_dwell = 0
        self.phase = "APPROACH"
        self.budget = BUDGET0
        self.primitive_queue = []
        self.g_prim = {}                    # historical success per primitive
        self.lambda_grasp = lambda_grasp    # 固定敏感度，冻结
        self.lambda_insert = lambda_insert  # 固定敏感度，冻结
        self.lambda_lift = lambda_lift      # 固定敏感度，冻结
        self.theta_anom = None              # 经校准的异常阈值，冻结
        self.cycle_sigma = "INIT"           # 生命周期状态
        self.cycle_dwell = 0                # 当前状态驻留计数
        self.timeout_counters = {
            "INIT": 0, "GROUND": 0, "TRACK": 0,
            "RECOVER": 0, "HOLD": 0
        }
        self.max_timeouts = {"INIT": 5, "GROUND": None, "TRACK": None,
                             "RECOVER": 10, "HOLD": None}  # 秒或块数

    def get_action(self, obs):
        # 1. update map / phase / edit detector (rounds 11/14)
        self.M = update_map(self.M, obs, self.plan)
        self.phase = observe_phase(self.M, obs)
        if edit_detected(obs):
            self.phase = "RECOVER"
            self.cycle_sigma = "GROUND"  # 编辑检测重新 ground

        # 2. update lifecycle state
        self._update_cycle_state(obs)

        # 3. execute one 5-step block of the currently allowed action
        act = self.select_action(obs)

        if act == "SERVO":
            chunk = self._wave_servo_chunk(obs, self.plan)
            self._record_pending_residual_check(obs, chunk)
            return chunk

        if act == "FALLBACK":
            # 4. 参数适配后的原语规划
            adapted = self._adapt_primitive_params(self.plan)
            if adapted is None:
                # 域检查失败，回退
                act = "HOLD"
            chunk = self._execute_next_primitive(obs, adapted)
            self._record_pending_residual_check(obs, chunk, fallback=True)
            return chunk

        if act == "LOOK":
            return self._look_action(obs)

        if act == "VLA":
            self._request_plan_async(obs)
            return self._safe_hold_or_last_chunk()

        if act == "HOLD":
            return self._safe_hold()

        if act == "PROBE_ANOM":
            return self._probe_anom(obs)

        return self._commit_action(obs)

    def _update_cycle_state(self, obs):
        """根据 CUSUM、r_anom、预算更新生命周期状态"""
        # 检查是否应进入 RECOVER
        if self.cusum > H or self.r_anom > self.theta_anom:
            if self.cycle_sigma == "TRACK":
                self.cycle_sigma = "RECOVER"
                self.cycle_dwell = 0
        # 检查是否应进入 HOLD
        if self.budget <= 0:
            self.cycle_sigma = "HOLD"
            self.cycle_dwell = 0
        # 检查 RECOVER 超时
        if self.cycle_sigma == "RECOVER":
            self.cycle_dwell += 1
            if self.cycle_dwell >= self.timeout_counters["RECOVER"]:
                self.cycle_sigma = "HOLD"
                self.cycle_dwell = 0
        # 检查 INIT 超时
        if self.cycle_sigma == "INIT":
            self.cycle_dwell += 1
            # INIT 超时由 map initialization 完成，此处仅作兜底
        
        # 记录时间戳用于超时检查
        self.timeout_counters[self.cycle_sigma] += 1

    def on_block_finished(self, obs_before, obs_after, executed):
        # 3. self-supervised residuals (only SERVO blocks are diagnostic)
        if executed == "SERVO":
            r = compute_residuals(obs_before, obs_after, self.plan,
                                  self.prev_plan, self.M, self.phase)
            # 新增：提取 r_anom
            r_anom = self._compute_anomaly_residual(r, obs_before, obs_after)
            s = self._normalized_score(r)
            surprise = int(s > self.q_alpha)
            self.surprise_window.append(surprise)
            self.cusum = max(0.0, self.cusum + surprise - ALPHA - K)
            self._update_mode(surprise)
        elif self.mode == "FALLBACK" and executed == "PROBE":
            r = compute_residuals(obs_before, obs_after, self.plan,
                                  self.prev_plan, self.M, self.phase)
            s = self._normalized_score(r)
            surprise = int(s > self.q_alpha)
            self._recheck(surprise)

        # 5. 生命周期状态更新（每块结束后）
        self._update_cycle_state({})

    def _compute_anomaly_residual(self, r, obs_before, obs_after):
        """计算接触异常残差 r_anom"""
        q_before = obs_before.q
        q_after = obs_after.q
        qdot_after = obs_after.qdot
        
        # 虚拟力预测的接触力
        F_pred = self.K_p @ (self.x_des - self.fk(q_after))
        
        # 接触指示
        penetration = self._compute_penetration(obs_after)  # 视差突变
        c_obs = 1 if (np.linalg.norm(qdot_after) < self.theta_vel and penetration > self.theta_pen) else 0
        
        # 接触力代理
        F_proxy = c_obs * self.mu * np.abs(self.I(q_after))
        
        # 异常残差
        r_anom = np.linalg.norm(F_pred - F_proxy) / (np.linalg.norm(F_pred) + 1e-4)
        return r_anom

    def _adapt_primitive_params(self, plan):
        """任务条件化原语参数调整"""
        # 从语义地图获取目标物体的估计尺寸
        adapted_seq = []
        for prim, args in plan.primitive_sequence:
            if prim == "GRASP":
                r_obj = self.M.get_object_size(args["target"])
                alpha = self.lambda_grasp * (abs(r_obj) - self.mu_ref_grasp) / self.mu_ref_grasp
                alpha = np.clip(alpha, -self.alpha_max_grasp, self.alpha_max_grasp)
                args["width"] = args["width_base"] * (1 + alpha)
            elif prim == "INSERT":
                r_obj = self.M.get_object_size(args["target"])
                alpha = self.lambda_insert * (abs(r_obj) - self.mu_ref_insert) / self.mu_ref_insert
                alpha = np.clip(alpha, -self.alpha_max_insert, self.alpha_max_insert)
                args["depth"] = args["depth_base"] * (1 + alpha)
            elif prim == "LIFT":
                r_obj = self.M.get_object_size(args["target"])
                alpha = self.lambda_lift * (abs(r_obj) - self.mu_ref_lift) / self.mu_ref_lift
                alpha = np.clip(alpha, -self.alpha_max_lift, self.alpha_max_lift)
                args["height"] = args["height_base"] * (1 + alpha)
            adapted_seq.append((prim, args))
        # 域检查
        if self.domain_check(adapted_seq) != "geometric":
            return None
        return adapted_seq

    def _probe_anom(self, obs):
        """发送异常探针块，诊断接触状态"""
        # 发送一小段 SERVO 块用于探针
        chunk = self._wave_servo_chunk(obs, self.plan, probe_mode=True)
        return chunk
```

### 3.3 更新后的残差计算伪代码

```python
def compute_residuals(obs0, obs1, plan, prev_plan, M, phase):
    r = {}
    # temporal: only if a previous plan overlaps
    if prev_plan is not None and plan is not None:
        r["tmp"] = normalized_action_diff(plan, prev_plan)
    else:
        r["tmp"] = 0.0

    # geometric: FK + head stereo tracking + optional flow
    dx_obs = fk(obs1.q) - fk(obs0.q)
    dx_cmd = planned_cartesian_delta(plan, obs0)
    r["geo"] = norm(dx_obs - dx_cmd) / (norm(dx_cmd) + EPS)
    if obs1.depth is not None and target_visible(M, obs1):
        flow_pred = project_motion(dx_cmd, obs1.depth, obs1.camera)
        r["geo"] += LAMBDA_F * norm(obs1.flow - flow_pred) / SIGMA_FLOW

    # goal: distance progress in approach; edit/slip in contact
    if phase in ("APPROACH", "PRECONTACT"):
        d0 = distance(fk(obs0.q), M.target_pose)
        d1 = distance(fk(obs1.q), M.target_pose)
        r["goal"] = goal_residual(d0, d1, planned_distance_delta(plan))
    else:
        r["goal"] = edit_score(obs0, obs1)   # round 11

    # dynamic: hard limits
    r["dyn"] = max(0.0, max_ratio(obs1.qdot, obs1.qddot) - 1.0)

    # anomaly: contact consistency
    r["anom"] = self._compute_anomaly_residual(obs0, obs1)

    return r

def normalized_score(r, scales):
    z = {k: r[k] / (scales[k] + EPS) for k in r}
    return (3.0 * z["dyn"] + z["tmp"] + z["geo"] + z["goal"] + z["anom"])
```

注意：`normalized_score` 中原来的 4 个通道系数（3.0, 1, 1, 1）现在变成了 5 个通道，但权重仍然是固定的、`不学习`的。五个通道的 MAD 尺度各自独立计算，融合时直接相加。

### 3.4 更新后的信任门伪代码

```python
def _update_mode(self, surprise):
    if self.mode == "TRUST":
        if self.cusum > H:
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
        elif self.r_anom > self.theta_anom:
            # 新增：r_anom 异常也直接触发 FALLBACK
            self.mode = "FALLBACK"
            self.fallback_dwell = 0
    elif self.mode == "FALLBACK":
        self.fallback_dwell += 1
        if self.fallback_dwell >= RECHECK_EVERY:
            self.mode = "PROBE"
            self.fallback_dwell = 0
    elif self.mode == "PROBE":
        if not surprise and self.r_anom <= self.theta_anom:
            self.mode = "TRUST"
            self.cusum = 0.0
        else:
            self.mode = "FALLBACK"
            self.fallback_dwell = 0

def _recheck(self, surprise):
    if not surprise and self.r_anom <= self.theta_anom:
        self.mode = "TRUST"
        self.cusum = 0.0
    else:
        self.mode = "FALLBACK"
        self.fallback_dwell = 0
```

### 3.5 更新后的调度器伪代码

```python
def select_action(self, obs):
    allowed = self._allowed_actions()      # gate as hard constraint
    if not allowed:
        return "HOLD"

    b = self.target_belief                 # round 14
    p = self.progress
    c = self.soft_competence()             # 1 - surprise rate
    bmax = max(b)

    opts = []
    if "SERVO" in allowed:
        gain = c * bmax * (f(p + DELTA) - f(p))
        opts.append(("SERVO", gain, C_SERVO))
    if "LOOK" in allowed and self.phase in ("APPROACH", "PRECONTACT"):
        gain = look_gain(b, self.M, self.phase)   # round 14
        opts.append(("LOOK", gain, C_LOOK))
    if "VLA" in allowed and self.budget >= C_VLA:
        c_after = c + (1 - c) * Q_VLA
        gain = (c_after - c) * bmax * f(p) + DELTA_PLAN
        opts.append(("VLA", gain, C_VLA))
    if "FALLBACK" in allowed:
        g = self.g_prim.get(self.current_primitive, G_PRIOR)
        gain = bmax * g * (f_geo(p + DELTA) - f_geo(p))
        opts.append(("FALLBACK", gain, C_FALLBACK))
    if "PROBE_ANOM" in allowed and self.cycle_sigma == "RECOVER":
        # 生命周期 RECOVER 模式下的异常探针
        opts.append(("PROBE_ANOM", 1.0, C_PROBE_ANOM))

    if not opts:
        return "HOLD"
    act, gain, cost = max(opts, key=lambda o: o[1] / o[2])
    if gain / cost < LAMBDA_OPPORTUNITY:
        return "COMMIT" if "COMMIT" in allowed else "HOLD"
    return act

def _allowed_actions(self):
    if self.mode == "TRUST":
        return {"SERVO", "LOOK", "VLA", "COMMIT"}
    if self.mode == "FALLBACK":
        acts = {"LOOK", "VLA", "HOLD"}
        if self.domain_check(self.instruction) == "geometric":
            acts.add("FALLBACK")
        return acts
    if self.mode == "RECOVER":
        # 仅在 RECOVER 模式下允许 PROBE_ANOM 和 HOLD
        return {"PROBE_ANOM", "HOLD"}
    return {"HOLD"}
```

### 3.6 新增命题与证伪假设

#### 3.6.1 接触异常检测命题

**命题 9（`r_anom` 标识接触内部异常）**：在 ID 条件下，`r_anom` 的分布与正常接触残差在统计上可区分，即 `AUROC(r_anom; OOD-contact, ID-normal) ≥ 0.7`。

**证明思路**：合成实验中注入接触扰动（滑动、碰撞），测量 `r_anom` 的 AUROC；本轮合成实验 (G13) 的验证通过方可列入主假设。

**边界**：若接触扰动小于虚拟力控制器的容差带，`r_anom` 可能无法区分；此时仍回退到 CUSUM+复检的组合判断。

#### 3.6.2 跨任务参数调整命题

**命题 10（`θ_prim` 跨任务泛化）**：在几何可分解的跨任务上，`θ_prim` 参数调整后的几何原语成功率相对固定参数至少提升 5pp，前提是语义地图中的目标尺寸估计误差 ≤ 20%。

**证明思路**：实验对比固定参数 vs. 调整后参数在跨任务几何任务上的成功率差异；本轮 G14 的验证通过方可列入主假设。

**边界**：若语义地图目标尺寸估计误差 > 20%，参数调整可能适得其反；此时域检查会把关，FALLBACK 自动不可用。

#### 3.6.3 生命周期鲁棒性命题

**命题 11（生命周期状态机鲁棒性）**：在真机部署中，生命周期状态机 `\sigma` 的 p99 延迟 ≤ 150ms，且状态在 1 个块内从 TRACK 转移至 RECOVER/HOLD 的概率 ≥ 95%。

**证明思路**：真机 A/B 实验，测量状态转移延迟和转移概率；本轮 G15 的验证通过方可列入主假设。

**边界**：极端网络分区可能导致状态不同步；`\tau_{\max}` 超时 guards 是兜底方案。

## 4. 更新的实验设计与门

### 4.1 继承门（续）

G0–G12 继续有效（标定、检索、仿真收敛、真机涨点、干扰恢复、延迟、32 任务稳定、消融、无源、可复现、grounding、预算、语义地图）。

**新增门 G17–G19**：

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| **G17** | `r_anom` 是否校准且有信号？ | ID 惊讶率 ≤ 0.15（α=0.1）；`r_anom` AUROC ≥ 0.7（接触内部异常）；ID 假阳性 ≤ 5% | 砍掉 `r_anom` 通道，恢复原有三通道 ZEST |
| **G18** | `θ_prim` 调整在跨任务几何任务上有效？ | ≥ 3/5 跨任务几何任务成功率提升 ≥ 5pp；域检查通过率 ≥ 90% | 砍掉 `θ_prim` 调整，恢复固定参数 |
| **G19** | 生命周期状态机是否鲁棒？ | 真机 p99 ≤ 150ms；状态转移延迟 ≤ 1 个块；TRACK→RECOVER 转移概率 ≥ 95% | 砍掉生命周期层，恢复单纯 ZEST-VLA |

### 4.2 预注册假设（续）

原有 H1–H5 继续生效，新增 H6–H11 与本轮增量相关。

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

**预注册内容**：假设、主/次端点、分析计划、停止规则、排除标准，必须在正式评测前写入仓库并打时间戳。

### 4.3 真机单任务 A/B（续）

| 项 | 设计 |
|---|---|
| 任务 | PlugInEthernet、HangCup、StackBowls、OpenDrawer、FoldTowel（覆盖插入/挂/叠/开/变形） |
| 次数 | 每任务 5 次，配对：VLA-only vs ZEST+anomaly vs ZEST+θ_prim vs ZEST+lifecycle，同初始条件 |
| 主端点 | 成功率；次端点：成功率/成本、OOD 检测延迟、恢复率、fallback 率、p99、生命周期状态转移次数 |
| 统计 | 配对差值 + bootstrap 95% CI；pilot 不宣称显著性 |
| 门 | G17：`r_anom` AUROC ≥ 0.7；G18：≥3/5 跨任务几何任务 +5pp；G19：p99 ≤ 150ms |

### 4.4 全量（续）

| 项 | 设计 |
|---|---|
| 任务 | 32×10 |
| 端口 | N 个连续端口，独立 reset |
| 指标 | 总成功率、步骤分、p99、timeout、平均 VLA 调用数、fallback 率、OOD 检测率、新增指标：`r_anom` AUROC、`θ_prim` 调整后成功率、生命周期状态驻留统计 |
| 门 | G6：无端口串扰；reset 干净；内存不涨；p99 ≤ 150ms |

### 4.6 消融与阴性对照（续）

| 消融 | 目的 | 预期 |
|---|---|---|
| 去掉 `r_anom` | 异常残差是否有用 | OOD-contact AUROC 下降；G17 不通过 |
| 去掉 `θ_prim` | 参数调整是否有用 | 跨任务几�任务成功率下降；G18 不通过 |
| 去掉生命周期层 | 鲁棒性层是否有用 | p99 升高；状态转移延迟增加；G19 不通过 |
| 随机残差 | 阴性对照 | 不应提升 |
| 打乱残差 | 阴性对照 | 不应提升 |
| 门常开 | 过保守对照 | ID 成功率下降 |
| 门常关 | VLA-only 对照 | OOD 成功率下降 |

## 5. 更新的风险与合规

### 5.1 单模型合规（续）

| 模式 | 做法 | 风险 | 建议 |
|---|---|---|---|
| C1 确定性几�几何 | 残差、融合、conformal/CUSUM、几�原语 | 最低 | 主推 |
| C2 符号 backchannel | 相位/子目标符号由几何/夹爪派生 | 低 | 主推 |
| C3 同 checkpoint 特征 | 若需要视觉跟踪描述子，用 VLA encoder | 低–中 | 需要时用，写清 |
| C5 接触代理无 F/T | 用关节电流 + 虚拟力预测作为接触力代理 | 中 | 声明：`r_anom` 是近似，非绝对诊断 |
| 禁止 | 第二个学习检测/分割/语言模型；在线学习残差；训练失败检测器 | 高 | 不做 |

**关键声明**：ZEST 不训练任何新参数；`r_anom` 是已有传感器（关节位置、速度、电流）的确定性函数组合；`θ_prim` 是几何缩放因子，`λ` 系数在验证集上手工调优后冻结；生命周期状态机是确定性的有限状态机，无学习权重。若评审认为「在线更新分位数」也算学习，可退化为**固定校准分位数 + 固定 CUSUM 参数 + 固定 `\theta_{\mathrm{anom}}`**，牺牲对尺度漂移的适应性，保持合规。

### 5.2 更新的风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| **OOD-G 不可检测** | 目标错时系统自信执行 | 命题 7 明确边界；独立语义检查/任务清单/复检；不承诺解决 |
| **`r_anom` 前端太弱** | 无 F/T 传感器下接触一致性代理噪声大 | 多模态组合（视觉穿透检测+电流异常+动力学突变）；`r_anom` 为辅通道，非主诊断 |
| **`θ_prim` 调整过激** | 语义地图尺寸估计误差导致原语前置条件失效 | `|\alpha^{\mathrm{prim}}_b| \leq \alpha_{\max}` 截断；域检查把关 |
| **生命周期状态 desync** | 真机网络抖动导致状态机与实际状态不匹配 | `\tau_{\max}` 超时 guards；每个状态的心跳检测；掉线默认 HOLD |
| **复检在 CONTACT 中破坏接触** | RECOVER 探针在接触阶段引入滑落 | 只在 APPROACH/PRECONTACT 或原语边界探针；CONTACT/CARRY 禁止 |
| **VLA 推理超时** | VLA server 无响应或返回错误形状 | 生命周期层设定 `VLA` 调用超时，超时后自动进入 `HOLD` 或 `RECOVER` |
| **OOD-G 不可检测（重申）** | 如果 VLA 和语义地图共享同一个错误先验 | 命题 7 明确边界；必须靠独立语义信号突破 |

### 5.3 已知失效模式（续）

| 场景 | 会发生什么 | 门控行为 | 结果 |
|---|---|---|---|
| 透明杯子（OOD-G） | 立体视觉失败，地图 ground 到旁边盘子；VLA 也抓盘子 | 残差像 ID，不触发 | **自信地抓错**；只能靠外部语义检查 |
| 未见物体颜色（OOD-E） | VLA 动作不匹配外观 | `r_tmp/r_geo` 高，触发 fallback | 几何原语 reach/grasp；可能成功 |
| 未见空间关系（OOD-S，地图对） | VLA 语义错，但地图目标对 | `r_goal` 高，触发 fallback | 几何原语 place；可能成功 |
| 变形任务 FoldTowel（语义） | 语法不覆盖 | 域检查判 `semantic`，不启用 fallback | VLA 或 HOLD；不盲目降级 |
| 瞬态执行失败 | VLA 短暂不一致，随后恢复 | CUSUM 触发，复检后恢复 | 少量 fallback 成本，避免永久保守 |
| 传感器噪声尖峰 | 残差尺度瞬变 | self-normalized 抑制；CUSUM 需持续证据 | 不误触发 |
| **接触异常漏检** | 接触滑动/碰撞但 `r_anom` 仍然偏小 | `r_anom` 阈值 `\theta_{\mathrm{anom}}` 设定保守；CUSUM+复检兜底 | 少量漏检成本，优于漏报 |
| **参数调整适得其反** | `θ_prim` 调整后的握幅/深度超出原语可行范围 | `|\alpha| \leq \alpha_{\max}` 截断；域检查失败，FALLBACK 不可用 | 退回 VLA/LOOK/HOLD，安全但可能效率降低 |
| **生命周期频繁抖动** | 状态在 TRACK/RECOVER/HOLD 间频繁切换 | `\tau_{\max}` 最小驻留时间；将多次连续触发视为一次事件 | 避免因瞬态噪声导致的过度保守 |

## 6. 更新的来源

官方/数据（检索日期 2026-11-02，沿用第 14 轮已核实）：

- UniBot 世界挑战赛官网：<https://unibot.unitree.com/>
- 赛事页：<https://unibot.unitree.com/challenges.html>
- 排行榜 JSON：<https://unibot.unitree.com/leaderboard_data.json>
- 提交模板：<https://github.com/unitreerobotics/unibot_submission>
- 提交 README：<https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md>
- 数据集集合：<https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset>
- WLA 仓库：<https://github.com/unitreerobotics/unifolm-wla>
- WLA 动作/状态规范：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/robot_action_state_processing_en.md>
- 官方仿真：<https://github.com/unitreerobotics/unitree_sim_isaaclab>、<https://github.com/unitreerobotics/unitree_mujoco>
- 提交示例：<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_policy.py>、<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_env.py>

经典/方法（作者-年份，未在本轮逐篇复核；复现包需补 DOI）：

- Page, E. S. (1954). Continuous inspection schemes. *Biometrika*.
- Lorden, G. (1971). Procedures for reacting to a change in distribution. *Annals of Mathematical Statistics*.
- Vovk, V., Gammerman, A., & Shafer, G. (2005). *Algorithmic Learning in a Random World*. Springer.
- Angelopoulos, A. N., & Bates, S. (2023). Conformal prediction: A gentle introduction. *Foundations and Trends in Machine Learning*.
- Gibbs, I., & Candès, E. J. (2021). Adaptive conformal inference under distribution shift. *NeurIPS*.
- Bajcsy, R. (1988). Active perception. *Proceedings of the IEEE*.
- Thrun, S., Burgard, W., & Fox, D. (2005). *Probabilistic Robotics*. MIT Press.
- Chaumette, F., & Hutchinson, S. (2006/2007). Visual servo control, Parts I–II. *IEEE Robotics & Automation Magazine*.
- Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady*.
- Jurafsky, D., & Martin, J. H. *Speech and Language Processing*.
- Doersch, C., Gupta, A., & Efros, A. A. (2015). Unsupervised visual representation learning by context prediction. *ICCV*.
- He, K., Fan, H., Wu, Y., Xie, S., & Girshick, R. (2020). Momentum contrast for unsupervised visual representation learning. *CVPR*.
- Sun, Y., Wang, X., Liu, Z., Miller, J., Efros, A. A., & Hardt, M. (2020). Test-time training with self-supervision for generalization under distribution shifts. *ICML*.
- Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., & Zhou, D. (2022). Self-consistency improves chain of thought reasoning in language models. *ICLR*.

**UNVERIFIED（不得进入论证链）**：第 10–14 轮中形如 `2609.xxxxx`、`2608.xxxxx` 的 arXiv 编号，年份前缀异常，本轮不采用。

## 7. 一句话押注（续）

**第 14 轮用「目标分布 + 预算」决定买什么信息；本轮用「动作-观测一致性」决定信不信当前策略：三个自监督残差 + conformal/CUSUM 信任门 + 几何原语降级 + 接触异常检测 + 任务条件化参数调整 + 生命周期鲁棒性，让零样本失败从「自信地错下去」变成「结构化受控退步」。**

## 8. 本轮最大的风险

**跨任务参数调整与地图估计误差的耦合**：`θ_prim` 的有效性完全依赖语义地图对目标尺寸的估计精度。若语义地图已存在系统性的尺寸偏差（如透明/反光物体的体积低估），参数调整会推原语进入不可行区域，域检查会把关但也可能在错误的方向上把关（即：错误的尺寸估计导致错误的域判定，把几何可分解的任务错误地归类为 `unknown`，从而禁止 FALLBACK 且未能提供降级路径）。这是本轮三个增量中最关键的相互作用风险，**既可能因过度调整导致原语前置条件失效，也可能因调整不足而无法获益**，两者都需要在真机评测中精确校准 `\alpha_{\max}` 和 `\lambda` 系数，且必须将 `θ_prim` 视为**有条件的增益而非保证**——若地图尺寸不可信，系统应退回固定参数的保守模式，而不是盲目依赖调整后的参数。
<!-- ARTIFACT:END -->
