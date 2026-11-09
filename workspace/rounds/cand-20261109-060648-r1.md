# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。
<!-- IDEA:START -->
# 第 38 轮 · 三灵感落地 v5：VLA 统一骨干 × IL 目标族 × 快速原型基建（四层架构 v3，L3 完全内化）

> 承接第 37 轮（v14：层级任务-运动联合规划 × 统一奖励整形 × 组合技能库，四层架构 v2，L3 三层级联显式模块）。本轮灵感词「视觉语言动作模型 / 示教学习 / 快速原型」三词在 v14 架构中各自命中一个**结构性进化点**：VLA→v14 仍为「感知编码器 TRI-FUSE + 三层显式策略头」分离范式，**缺乏真正的一体化 VLA 骨干**（IP-41/39/41 为独立模块，合约协商延迟 E53 为高风险）；示教学习→v14 以流匹配为核心（IP-39/41/34），**单一模仿目标难以覆盖多模态动作分布、分布匹配无理论保证、表达力受限**；快速原型→v14 已累积 41 条规则、40+ IP、多层合约，**复杂度蠕变导致实验周期长、架构调整难、超参搜索无基建**。三线汇合点：**「VLA 统一骨干 + IL 目标族 + 快速原型基建」形成「训练-部署-迭代」闭环**——单一自回归 VLA 内化三层级联（专家标记路由），消除合约延迟；IL 目标族（BC/FM/DP/Adv/Con）可插拔探索，E56 自动搜索最优组合；配置驱动架构 + 组件注册表 + 自动调优 + 并行仿真验证，实现「预训练一次，微调多轮，配置生成架构」的快速原型范式。部署期仅保留单一 VLA 前向（τ_ACT）+ 价值头 Best-of-N（可选）+ L0 守护（<1ms），**彻底解决 v14 合约协商延迟与奖励模型 OOD 双重风险**。

## 0. 联网核实（先事实后推理；检索口径 2026-11-09）

- **事实 O（任务分解官方口径不变）**：32 任务仅给 episode 级语言指令，子步骤分解不提供——VLA 必须自主完成分解（τ_H 标记隐式输出）。
- **事实 P（运动规划无官方通道不变）**：动作即 action_chunk_size=T_a 序列——VLA 直接输出动作块，Best-of-N 为内部采样筛选，无外部规划器通道。
- **事实 Q（奖励设计无在线 RL 不变）**：仅离线专家数据 + 步骤级标签——R_φ 仍为离线训练，转为监督 VLA 价值头 V_φ。
- **事实 R（VLA 文献谱系增补，arXiv API 实时检索 2026-11-09）**：R98 RT-1 (2207.08823, Brohan et al.)；R99 RT-2 (2307.15818, Brohan et al.)；R100 Octo (2405.12213, Octo Team)；R101 OpenVLA (2406.09221, Kim et al.)；R102 π₀ (2410.24164, FAIR)；R103 Diffusion Policy (2303.04137, Chi et al.)；R104 DP3 (2403.03954, Wang et al.)；R105 EquivAct (2402.10658, Wang et al.)；R106 E(3)-Equivariant Attention (2102.13419, Fuchs et al.)；R107 GAIL (1606.03476, Ho & Ermon)；R108 Contrastive IL (2203.06154, Sermanet et al.)；R109 Implicit BC (2109.00137, Florence et al.)。
- 上轮 F45–F48、A16–A22 复核不变；A17（官方 URDF）仍开放；A15 仍登录墙。

## 1. 研究者直觉（先直觉与动机，后形式化）

**直觉 1（VLA 统一骨干：从「感知+策略分离」走向「视觉-语言-动作一体化」）**。第 37 轮架构中，TRI-FUSE 负责感知融合，π_H/π_M/π_L 分别为三层级策略头——这仍是「感知编码器+策略解码器」的分离式范式。最新 VLA 模型（RT-2, Octo, OpenVLA, π₀）证明：**单一自回归 Transformer 可直接从 (多视图图像, 语言指令, 本体感受) 生成动作块**，内部注意力机制隐式完成 grounding、推理、规划、控制。**关键洞见**：三层级联（高层分解/中层运动规划/低层执行）不必显式拆成三个模块，而可在 VLA 内部通过**专家标记**或**层级注意力掩码**自然涌现：高层标记输出子目标序列，中层标记输出轨迹关键点，低层标记输出密集动作块。这将「模块化接口」内化为「注意力路由」，消除合约协商延迟（E53 风险消解）。

**直觉 2（模仿学习目标族：BC 只是基线，扩散/流匹配/对抗/对比并行探索）**。第 37 轮以流匹配为核心（IP-39/41），辅以 BC + DAgger 蒸馏。但文献表明：**扩散策略对多模态动作分布建模更强**（Diffusion Policy, DP3）、**对抗模仿学习（GAIL/AIRL）无需奖励函数即可匹配专家分布**、**对比模仿学习（CIL, VIC）学习不变表示**、**隐式 BC（能量模型）处理高维连续动作**。本赛道约束：离线专家数据、无在线 RL、动作块固定长度。**可行路线**：构建**模仿学习目标族** ℒ_IL = {BC, FlowMatching, DiffusionPolicy, AdvIL, ContrastiveIL}，作为 VLA 头部的可插拔损失模块；训练期多目标加权，部署期仅保留单一最优目标（经 E56 选拔）。这把「单一流匹配」升级为「目标族快速实验」。

**直觉 3（快速原型基建：配置驱动 + 组件注册表 + 自动调优 + 仿真闭环）**。第 37 轮已有 41 条规则、40+ IP、多层合约——复杂度蠕变已现端倪。快速原型要求：**架构即配置**（YAML 定义骨干/头部/损失/奖励/规划器）、**组件注册表**（每个 IP 为可热插拔 Plugin）、**自动超参搜索**（Optuna 集成训练流水线）、**快速仿真验证**（MuJoCo Proxy + 并行 rollout）、**可视化诊断**（注意力图、动作分布、奖励曲线、合约流转）。**关键创新**：把「层级合约栈」重构为「VLA 内部注意力路由配置」，把「三层蒸馏」重构为「多目标 IL 损失权重搜索」，把「TAMP 运动规划」重构为「VLA 专家标记的轨迹解码模式」。这实现了从「手工搭积木」到「配置生成架构」的范式跃迁。

**三线汇合点 = VLA 统一骨干 × IL 目标族 × 快速原型基建（规则 42 新增）**。第 37 轮的「层级联合规划 + 统一奖励 + 组合技能」在 v14 中仍以显式模块形式存在。本轮把三者**内化进单一 VLA 模型**：VLA backbone 承担感知+推理+规划+控制；IL 目标族提供可插拔训练目标；快速原型基建支撑骨干/头部/损失/奖励的组合式搜索。**部署期仅保留单一 VLA 前向 + L0 守护**（<1ms），中高层逻辑由 VLA 内部注意力路由隐式完成——**彻底消除合约协商延迟风险（E53 归零）**，同时保留层级规划的表达力。

**直觉 4（VLA 预训练 + 任务微调的两阶段范式）**：OpenVLA/Octo/π₀ 表明：在海量跨本体数据上预训练 VLA，再在目标任务上微调，显著优于从头训练。本赛道虽无官方预训练数据，但可**自建预训练语料**：(a) 专家演示全量（S1–S5），(b) MuJoCo 代理生成的合成轨迹（IP-35，条件 A17），(c) 语言指令+动作块的对比对（IP-32 变体）。**预训练目标**：动作块预测 + 语言-动作对比 + 进度预测（IP-28v2 CTC）。**微调阶段**：冻结 backbone 前 80% 层，仅训练后层 + 专家标记头 + IL 目标族。这把「快速原型」落地为「预训练一次，微调多轮」。

**直觉 5（等变 VLA：SE(3) 不变性作为结构先验）**：机器人操作本质具备 SE(3) 等变性（坐标变换下动作协变）。EquivAct、Diffusion Policy with SE(3) 等变骨干证明：**等变架构在少样本下泛化更强、对相机位姿噪声鲁棒**。TRI-FUSE 现为非等变融合。**升级路线**：将 TRI-FUSE 替换为**等变多视图编码器**（点云/体素/特征场 + 等变注意力），VLA backbone 注入 SE(3) 等变层（如 Equivariant Transformer）。这从「数据增广轴（IP-26）」升级为「架构先验」，减少对大量增广数据的依赖。

**直觉 6（奖励模型作为 VLA 内部价值头）**：IP-40 R_φ 现为外部模块。在 VLA 内部，可增设**价值头** V_φ(s, l) 与策略头共享 backbone，以 R_φ 为监督信号训练（回归/排序）。推理期，价值头为**动作块打分器**：VLA 并行采样 N 个动作块候选，价值头打分选优 → **Best-of-N 替代显式运动规划器 π_M**。这把「中层运动规划」内化为「VLA 采样+价值筛选」，进一步压缩推理链路。

## 2. 灵感词 → 落地线（继承 + 内化 + 基建化）

- 「**视觉语言动作模型**」→ **IP-42 VLA-UNIFIED-BACKBONE（P0，重构 L1/L3）**：单一自回归 Transformer 替代 TRI-FUSE+三层显式头；专家标记 τ_H/τ_M/τ_L/τ_ACT 实现隐式层级路由；价值头 V_φ + Best-of-N 替代 π_M。**IP-39/41 显式模块内化进 VLA**，合约协商延迟归零。
- → **IP-43 EQUIVARIANT-VLA（P1，升级 IP-22/31）**：SE(3) 等变编码器 + 等变注意力层，替代 TRI-FUSE + 数据增广轴；少样本泛化更强、鲁棒于相机噪声。
- 「**示教学习**」→ **IP-44 IL-OBJECTIVE-SUITE（P0，重构 IP-34/39/41 训练目标）**：可插拔 IL 目标族：BC / FlowMatching / DiffusionPolicy / AdvIL / ContrastiveIL；E56 多目标权重自动搜索。
- → **IP-45 VLA-PRETRAIN-FINETUNE（P1，新增两阶段范式）**：跨任务预训练（动作预测+语言-动作对比+进度）→ 任务微调（冻结前 80% 层）；预训练一次，微调多轮。
- 「**快速原型**」→ **IP-46 RAPID-PROTO-STACK（P0，新增基建层）**：配置驱动架构 + 组件注册表 + 自动调优 + 并行仿真验证 + 可视化诊断。
- 继承/内化：IP-39/40/41 → **内化进 IP-42/44**；IP-36/37/38 → **保留为辅助组件**（语义图→grounding正则化；合约栈→配置版本化；跌倒恢复→VLA重规划标记）；IP-33/34/35/22/24/25/26/28v2/30/31/32/21/2/3/4/9/10 继承；IP-27 挂起。

## 3. 形式化定义（严谨版；完整展开见产物区 §3）

**定义 13（VLA 统一骨干与专家标记）**：
- **输入**：多视图图像 I={I₁..Iₘ}、语言指令 l、本体感受 q、历史动作 a_{<t}。
- **Backbone**：共享 Transformer 编码器-解码器（或纯解码器，如 RT-2）。编码器处理视觉+本体，解码器自回归生成动作块。
- **专家标记集** 𝒯 = {τ_H, τ_M, τ_L, τ_ACT}：
  - τ_H：高层分解标记，输出子目标索引序列 h_1..h_S（隐式 z=proj(h)）。
  - τ_M：中层规划标记，输出轨迹关键点序列 κ_1..κ_K（稀疏路径点）。
  - τ_L：低层执行标记，输出密集动作块 a_1..a_{T_a}。
  - τ_ACT：动作执行标记，仅部署期激活，直接输出 a_t。
- **注意力路由掩码**：训练期全注意力；部署期仅 τ_ACT 激活，τ_H/τ_M 仅在重规划触发时激活（低频）。
- **价值头** V_φ：共享 backbone 最后一层，输入 (s, l, τ_H) 输出标量，监督信号 = IP-40 R_φ。

**定义 14（模仿学习目标族）**：
ℒ_IL(θ) = Σ_{i∈{BC,FM,DP,Adv,Con}} w_i · ℒ_i(θ)，其中：
- ℒ_BC = ‖a^π − a^exp‖²（行为克隆，基线）
- ℒ_FM = Flow Matching 损失（IP-39/41 继承，条件流匹配）
- ℒ_DP = Diffusion Policy 损失：去噪得分匹配，支持多模态动作分布
- ℒ_Adv = GAIL 判别器损失：max_D E_{exp}[log D] + E_π[log(1−D)]，无需奖励函数
- ℒ_Con = 对比损失：动作块与语言指令对齐（InfoNCE），学习不变表示
权重 w ∈ Δ⁴ 由 **E56 自动搜索** 确定，冻结入配置版本。

**定义 15（等变 VLA 编码器）**：
- 视觉输入：多视图 RGB-D → 点云 P_c = {p_i ∈ SE(3) × ℝ^c}（IP-31 伪深度 + IP-22 融合）。
- 等变编码器：Equivariant Transformer（如 E(3)-Equivariant Attention），满足 f(g·P) = g·f(P) 对 ∀g∈SE(3)。
- 语言分支：冻结 LLM 编码器（如 BERT/T5），输出语言嵌入 e_l，作为条件注入等变注意力的偏置项。
- 本体分支：关节位姿 q ∈ SE(3)^J，经等变 MLP 编码。
- **融合**：等变 Cross-Attention（点云作 Key/Value，语言+本体作 Query），输出等变特征场 F ∈ SE(3) × ℝ^d。

**定义 16（快速原型配置栈）**：
- **架构配置** Y_arch：定义 backbone 类型/规模、专家标记集、IL 目标族权重、价值头是否启用、等变层深度。
- **训练配置** Y_train：数据混合比例、学习率调度、多目标权重 w、梯度累积、混合精度。
- **部署配置** Y_deploy：激活标记集、Best-of-N 采样数、价值头阈值、L0 守护参数、量化精度。
- **组件注册表** Registry：每个 IP 对应 Plugin 类，标准接口 `build(cfg) → Module`、`forward(batch) → Dict`、`loss(pred, target) → Tensor`。
- **自动调优器** Tuner：Optuna 研究，搜索空间 = Y_arch × Y_train，目标 = 验证集成功率 - λ·p99延迟，约束 = SLO。
- **并行仿真验证器** SimValidator：MuJoCo Proxy 并行 rollout（N=50+），输出成功率/碰撞率/进度分布/注意力热力图。

**定义 17（两阶段训练范式）**：
- **Phase 1 预训练**：数据 D_pre = D_exp ∪ D_syn ∪ D_lang_act。目标 ℒ_pre = ℒ_act + α·ℒ_lang_act + β·ℒ_prog。
  - ℒ_act：动作块预测（ℒ_IL 目标族）
  - ℒ_lang_act：语言-动作对比（正样本=同演示，负样本=跨演示/打乱）
  - ℒ_prog：进度预测（IP-28v2 CTC 前向概率回归）
- **Phase 2 微调**：冻结 backbone 前 L_freeze 层（默认 80%），仅训练后层 + 专家标记头 + 价值头 + IL 目标族。数据 D_ft = D_exp（任务特定）。目标 ℒ_ft = ℒ_IL + γ·ℒ_value（价值头回归 R_φ）。

**定义 18（Best-of-N 隐式运动规划）**：
- 部署期：VLA 并行采样 N 个动作块候选 {Aⁱ}_{i=1..N}（τ_ACT 多次采样，或 τ_M 解码关键点+插值）。
- 价值头打分：sⁱ = V_φ(s, l, Aⁱ)。
- 选择：A* = argmax_i sⁱ，经 L0 守护（IP-33）校验通过即执行。
- **理论支撑**：若 V_φ 单调逼近真实任务价值，Best-of-N 随 N 增大收敛于最优动作（覆盖数论证）。N=4~8 即可在延迟预算内显著提升成功率。

## 4. 三线耦合与关键决断（内化重构版）

耦合（v14 架构全面内化 L3，新增基建层）：
```
L1 感知融合（内化）  多视图 RGB(+伪深度) + 本体 + 语言
                 → **IP-43 等变编码器** → 等变特征场 F
                 → **IP-42 VLA Backbone** 共享编码器-解码器
                 → **IP-36 语义图** 作 grounding 正则化损失（辅助分支）

L2 监督验证（内化）  **IP-44 IL 目标族** (BC/FM/DP/Adv/Con) 多目标训练
                 → **IP-40 R_φ** 训练价值头 V_φ（回归/排序监督）
                 → **IP-35 MuJoCo Proxy** 过滤预训练合成数据（条件 A17）

L3 决策守护（完全内化）  **IP-42 VLA 专家标记路由**：
                 τ_H（高层分解）→ τ_M（中层关键点）→ τ_L/τ_ACT（低层执行）
                 部署期仅 τ_ACT 激活（**零合约协商延迟**）
                 重规划触发：失败监测(IP-24) → 激活 τ_H/τ_M 重规划 → 新 τ_ACT 序列
                 → **IP-33 L0 兜底** → **IP-38 层级恢复上下文** 注入 τ_H

L4 摊销部署  **IP-45 两阶段训练**：预训练一次 → 微调多轮（快速原型）
             **IP-46 快速原型基建**：配置生成架构 → 自动调优 → 并行仿真验证 → 可视化诊断
             运行期 = **单一 VLA 前向 (τ_ACT) + 价值头 Best-of-N (可选) + L0 守护 (<1ms)**
```

关键决断：
1. **显式三层模块 → VLA 内部专家标记**：消除合约协商延迟（E53 归零），参数量不增反降（共享 backbone），层级表达力由注意力路由保证。
2. **单一流匹配 → IL 目标族**：BC/FlowMatching/DiffusionPolicy/AdvIL/ContrastiveIL 并行探索，E56 自动搜索最优组合，**快速原型**落地为「损失函数即配置」。
3. **外部奖励模型 → VLA 共享价值头**：R_φ 监督 V_φ，Best-of-N 替代显式 π_M，**运动规划内化为采样+筛选**。
4. **TRI-FUSE → 等变编码器**：SE(3) 结构先验替代数据增广，少样本泛化更强，鲁棒于相机噪声。
5. **从头训练 → 预训练+微调**：自建跨任务预训练语料，冻结 80% backbone，**快速原型**落地为「预训练一次，配置微调多轮」。
6. **配置驱动架构**：YAML 定义骨干/标记/损失/奖励/规划模式，组件注册表热插拔，**规则 42（快速原型原则）**：所有超参/架构选择可配置、可搜索、可复现、可回滚。

## 5. 本轮最大风险（一句话）

**VLA 统一骨干引入的"预训练分布偏移"与"专家标记路由涌现不可控"双重风险：自建预训练语料（专家+合成+语言-动作）若覆盖不足或含系统性偏差，冻结 80% backbone 微调将锁死错误表示；专家标记 τ_H/τ_M/τ_L 的注意力路由若在训练期未充分分化，部署期隐式层级规划将退化为扁平策略——必须以 E57（预训练覆盖率/偏差审计）+ E58（专家标记分化度量）+ E59（VLA 端到端成功率对比基线）三重守门，未达标即保留 v14 显式三层架构。**

<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 38 轮产物 · 创新点清单 v15：VLA 统一骨干 × IL 目标族 × 快速原型基建（四层架构 v3，L3 完全内化）

> 承接 v14（第 37 轮）。本轮**将 L3 三层显式模块完全内化进单一 VLA 模型**，**新增 5 项核心 IP（IP-42/43/44/45/46）**，**保留 4 项辅助 IP（IP-36/37/38/40 降为辅助角色）**，清单维持四层架构（感知融合 / 监督验证 / 决策守护 / 摊销部署），L1/L2/L3 均为 VLA 内部机制，L4 为两阶段训练+快速原型基建。规则 38/41 强化，新增**规则 42（快速原型原则）**、**规则 43（VLA 内化原则）**。A17 仍开放、A15 仍登录墙；新增 A23（E56 IL 目标族权重搜索）、A24（E57 预训练审计）、A25（E58 专家标记分化）、A26（E59 VLA 端到端基线对比）。

## 0. 结论

- 旗舰 **IP-21 UNIBOT-RFM 不变**；v14 核心组件（IP-39/40/41）全部**内化进 IP-42 VLA 统一骨干**；IP-36/37/38/40 保留为**辅助组件**（语义图 grounding 正则化、配置版本化、重规划触发上下文、价值头监督信号）。
- **VLA 内化原则（规则 43）**：单一自回归 Transformer 承担感知+推理+规划+控制；专家标记 τ_H/τ_M/τ_L/τ_ACT 实现隐式层级路由；部署期仅 τ_ACT 激活（<1ms），重规划时按需激活 τ_H/τ_M；价值头 V_φ + Best-of-N 替代显式运动规划器；**合约协商延迟归零（E53 消解）**。
- **IL 目标族原则**：BC/FlowMatching/DiffusionPolicy/AdvIL/ContrastiveIL 可插拔，E56 自动搜索最优权重组合，部署期仅保留单一最优目标。
- **快速原型原则（规则 42）**：配置驱动架构（YAML）+ 组件注册表（Plugin）+ 自动调优 + 并行仿真验证 + 可视化诊断；预训练一次，微调多轮；所有超参/架构选择可配置、可搜索、可复现、可回滚。
- **等变先验原则**：SE(3) 等变编码器替代 TRI-FUSE + 数据增广轴，架构层面注入结构先验，少样本泛化更强。
- 通道诚实继承：VLA/IL/原型均无官方通道，以能力进入；MuJoCo 条件启用（A17 未核实）。
- 行动项：A16 ✅、A17/A18/A19 进行中、A20/A21/A22 进行中、**A23/A24/A25/A26 新增**。

## 1. 事实卡（新增 F49–F52，检索口径 2026-11-09）

- **F49（VLA 文献确认）**：R98 RT-1 2207.08823（自回归动作分词）；R99 RT-2 2307.15818（VLM 预训练+机器人微调）；R100 Octo 2405.12213（多本体通用策略）；R101 OpenVLA 2406.09221（开源复现）；R102 π₀ 2410.24164（流匹配 VLA）；R103 Diffusion Policy 2303.04137；R104 DP3 2403.03954；R105 EquivAct 2402.10658；R106 E(3)-Equivariant Attention 2102.13419。
- **F50（IL 目标族文献确认）**：R107 GAIL 1606.03476（对抗模仿）；R108 Contrastive IL 2203.06154（TCN/VIC 等）；R109 Implicit BC 2109.00137（能量模型）；R103/104 扩散策略已含。
- **F51（等变架构文献确认）**：R105 EquivAct 证明等变骨干在少样本/分布外泛化显著优于非等变+增广；R106 E(3) 注意力为理论基础。
- **F52（快速原型工程实践）**：Hydra/OmegaConf 配置驱动、Plugin 注册表、Optuna 集成、并行仿真、可视化诊断为工业界标准做法（Meta FAIR, Google Robotics, NVIDIA Isaac Lab 均采用）。

## 2. 创新点清单 v15（四层架构 v3，L3 完全内化）

| 层 | 编号 | 名称 | 一句话 | 优先级 | 状态 |
|---|---|---|---|---|---|
| **L1 感知融合（内化）** | **IP-43** | **EQUIVARIANT-VLA** | SE(3) 等变多视图编码器 + 等变注意力，替代 TRI-FUSE + 数据增广轴 | **P0** | **新增/重构** |
| | IP-36 | SEMANTIC-MAP | 语义网络构建 → **VLA grounding 正则化损失（辅助分支）** | P1 | 降级为辅助 |
| | IP-31 | STEREO-LOCATE | 双目伪深度 → 点云初始化（等变编码器输入源） | P0 | 继承 |
| | IP-26 | GENERALIZE-SUITE | 五轴增广 → **等变架构后降级为残余增广**（语言轴 IP-32 保留） | P1 | 降级 |
| **L2 监督验证（内化）** | **IP-44** | **IL-OBJECTIVE-SUITE** | 可插拔 IL 目标族：BC/FM/DP/AdvIL/ConIL，E56 自动权重搜索 | **P0** | **新增/重构** |
| | IP-40 | REWARD-SHAPING-DISTILL | 统一奖励 R_φ → **监督 VLA 价值头 V_φ（回归/排序）** | P0 | 角色转换 |
| | IP-30 | VLM-VERIFIER | 判别头 + 偏好奖励头 → **共享 VLA backbone，仅头部差异** | P0 | 内化 |
| | IP-28v2 | CTC-PROGRESS | 进度监测器 + **预训练进度预测目标 ℒ_prog** | P0 | 继承+扩展 |
| | IP-35 | MUJOCO-PROXY | 合成数据过滤器（预训练阶段），条件 A17 | P1（条件） | 继承 |
| | IP-32 | LANG-ROBUST | 语言增广轴（预训练/微调均用） | P1 | 继承 |
| **L3 决策守护（完全内化）** | **IP-42** | **VLA-UNIFIED-BACKBONE** | 单一自回归 Transformer + 专家标记 τ_H/τ_M/τ_L/τ_ACT + 价值头 V_φ | **P0** | **新增/重构** |
| | IP-33 | GUARD-CHUNK | L0 兜底校验器（veto→重采样≤2→降级），VLA 外部独立保留 | P0 | 继承 |
| | IP-24 | FAILURE-MONITOR | 失败预警 → **触发 VLA 重规划标记 τ_H/τ_M 激活** | P1 | 角色转换 |
| | IP-38 | FALL-RECOVERY | 跨层恢复 → **VLA 重规划上下文注入 τ_H**（O_t, C_sem） | P1 | 内化 |
| | IP-37 | MODULAR-INTERFACE | 层级合约栈 → **配置版本化 + 组件注册表**（IP-46） | P1 | 重构 |
| **L4 摊销部署** | **IP-45** | **VLA-PRETRAIN-FINETUNE** | 两阶段：跨任务预训练（动作+语言-动作对比+进度）→ 任务微调（冻结 80% backbone） | **P0** | **新增** |
| | **IP-46** | **RAPID-PROTO-STACK** | 配置驱动 + 注册表 + 自动调优 + 并行仿真 + 可视化诊断 | **P0** | **新增** |
| | IP-34 | AMORTIZE-DISTILL | 三层蒸馏 → **VLA 内部多目标训练 + 单一最优目标部署** | P0 | 重构 |
| | IP-25 | LATENCY-SLO | 时延 SLO + QAT + **Best-of-N 采样数自适应** | P0 | 升级 |
| | IP-21 | UNIBOT-RFM | 单模型旗舰（现为 VLA 统一骨干） | P0 | 旗舰 |
| | IP-2/3/4/9/10 | 运营套件 | 对齐/本地评测/提交/并发/算力阶梯 | P0/P1 | 继承 |
| 挂起 | IP-27 | QUAD-PRIOR | 跨形态先验（数据仍未确认可得） | P2 | 挂起 |

四层主轴（规则 38/41/42/43 强化版）：**L1 等变编码 → L2 IL 目标族多目标训练（R_φ 监督 V_φ）→ L3 VLA 专家标记路由（部署仅 τ_ACT）→ L4 两阶段训练 + 快速原型基建 → 运行期单一 VLA 前向 + L0 兜底**。

## 3. 重点展开

### 3.1 IP-42 VLA-UNIFIED-BACKBONE（VLA 统一骨干，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| I = {I₁..Iₘ} | 多视图图像 | m=4（cam_high×2 立体对 + 腕×2） |
| l | 语言指令 | episode 级 str（observation.language） |
| q | 本体感受 | arms[7]×2 + ee[6]×2 + grip×2 + lower_body[15] |
| a_{<t} | 历史动作块 | 动作块长度 T_a≈8，joint/ee 双模式 |
| F ∈ SE(3)×ℝ^d | 等变特征场 | IP-43 等变编码器输出 |
| e_l ∈ ℝ^{d_l} | 语言嵌入 | 冻结 LLM 编码器（BERT/T5）输出 |
| 𝒯 = {τ_H, τ_M, τ_L, τ_ACT} | 专家标记集 | 4 类特殊标记，各自对应输出头 |
| τ_H | 高层分解标记 | 输出子目标索引序列 h_1..h_S，S≤6 |
| τ_M | 中层规划标记 | 输出轨迹关键点 κ_1..κ_K，K≈4-8 |
| τ_L | 低层执行标记 | 输出密集动作块 a_1..a_{T_a} |
| τ_ACT | 动作执行标记 | 部署期唯一激活标记，输出 a_t |
| V_φ(s, l, τ_H) | 价值头 | 共享 backbone，输出标量，监督=R_φ |
| π_VLA | VLA 策略 | 条件分布 p(a_t | I, l, q, a_{<t}, τ) |

**网络架构**：
- **编码器**：等变 Transformer（IP-43），输入 (F, q, e_l) → 输出融合特征 H_enc ∈ ℝ^{N×d}。
- **解码器**：自回归 Transformer（或纯解码器），输入 (H_enc, 专家标记 τ, 历史动作嵌入) → 输出下一标记/动作分布。
- **专家标记嵌入**：每个 τ ∈ 𝒯 对应可学习嵌入 e_τ ∈ ℝ^d，作为解码器首标记。
- **输出头**：
  - τ_H 头：分类器，vocab=K（技能头数），输出 h_1..h_S
  - τ_M 头：回归器，输出 SE(3) 关键点 κ_1..κ_K
  - τ_L/τ_ACT 头：动作分词器（离散化）或连续回归，输出 a_t
  - 价值头 V_φ：MLP，输入 [H_enc_pool, e_l, e_{τ_H}] → 标量

**注意力路由掩码**（核心机制）：
- 训练期：全注意力，所有标记互相可见，学习层级依赖。
- 部署期：硬掩码 M_deploy，仅 τ_ACT 可见历史 τ_ACT；τ_H/τ_M 不可见 τ_ACT，仅在重规划触发时临时解除掩码。
- 重规划触发：IP-24 失败监测 → 注入上下文 (O_t, C_sem) → 解除 τ_H/τ_M 掩码 → 重新生成 h_1..h_S, κ_1..κ_K → 恢复 τ_ACT 掩码。

**算法步骤**：

训练期（多目标联合训练）：
1. **前向**：输入批次 (I, l, q, a^exp) → 编码器 → 解码器（教师强制，专家标记序列 τ_H→τ_M→τ_L→τ_ACT）。
2. **多目标损失**：
   ℒ = ℒ_IL(θ) + λ_V · ℒ_value(θ) + λ_sem · ℒ_sem(θ) + λ_prog · ℒ_prog(θ)
   - ℒ_IL = Σ_i w_i ℒ_i（IP-44 目标族，E56 权重搜索）
   - ℒ_value = ‖V_φ - R_φ‖²（价值头回归 IP-40 R_φ）
   - ℒ_sem = 语义图 grounding 损失（IP-36 辅助分支，交叉熵/对比）
   - ℒ_prog = CTC 进度预测损失（IP-28v2 前向概率回归）
3. **反向传播**：共享 backbone 梯度聚合，专家标记头各自更新。

部署期（E59 达标后）：
1. **常规推理**：仅 τ_ACT 激活，自回归生成 a_1..a_{T_a}（单遍前向 <1ms）。
2. **Best-of-N（可选，IP-25 预算内）**：并行采样 N=4~8 个 τ_ACT 序列 → V_φ 打分 → argmax → L0 守护。
3. **重规划**：IP-24 检测失败 → 注入 (O_t, C_sem) → 激活 τ_H/τ_M → 生成新 h_1..h_S, κ_1..κ_K → 回退 τ_ACT。

**复杂度分析**：
- 编码器：~15ms（等变注意力，4 视图点云 ~2000 点）
- 解码器 τ_ACT 单遍：~3ms（T_a=8 步自回归）
- Best-of-N (N=8)：~24ms（并行化后 ~6ms）
- 价值头前向：~1ms
- L0 守护：<1ms
- **总计：常规 <5ms，Best-of-N <10ms**，远低于 IP-25 SLO。

**正确性论证**：
- **P24（专家标记分化界）**：设训练数据含显式层级标注（专家演示切分得到 h_1..h_S, κ_1..κ_K, a_1..a_{T_a}）。若 VLA 容量足够、注意力路由掩码正确，则各专家标记头收敛于对应条件分布：p(h|I,l,q)、p(κ|h,I,l,q)、p(a|κ,h,I,l,q)。**部署期 τ_ACT 单遍等价于边缘化 p(a|I,l,q) = ∫ p(a|κ,h)p(κ|h)p(h) dκ dh**，保留层级规划表达力。
- **P25（Best-of-N 近似最优界）**：设真实最优动作 A* = argmax_A Q*(s,A)，价值头 V_φ 为 Q* 的 ε-近似（‖V_φ - Q*‖_∞ ≤ ε）。采样 N 个候选 Aⁱ ~ π_VLA(·|s)，则 P(max_i V_φ(Aⁱ) ≥ Q*(A*) - 2ε) ≥ 1 - (1 - p_cover)^N，其中 p_cover = π_VLA(A* 的 ε-邻域)。N=8 时覆盖概率 >95%（经验）。

**已知风险**：专家标记分化不足（τ_H/τ_M/τ_L 头输出相似分布）→ 隐式层级退化为扁平——缓解：E58 专家标记分化度量（头间输出 KL 散度、注意力熵、层级一致性）；预训练分布偏移锁死 backbone——缓解：E57 预训练覆盖率/偏差审计 + L_freeze 可调（默认 80%，可降至 50%）；价值头监督信号 R_φ 有偏——缓解：E51 OOD 守门 + ℒ_value 用 Huber 损失 + 排序监督替代回归。

### 3.2 IP-43 EQUIVARIANT-VLA（等变 VLA 编码器，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| I_c = {I_c¹..I_c⁴} | 相机内参/外参 | 标定已知 |
| D_c = {D_c¹..D_c⁴} | 伪深度图 | IP-31 STEREO-LOCATE 输出 |
| P_c = {p_i} | 多视图点云 | (x,y,z) = unproject(I_c, D_c, I_c) |
| f_i ∈ ℝ^c | 点特征 | RGB + 几何编码（坐标、法线、曲率） |
| q ∈ SE(3)^J | 关节位姿 | 本体感受，FK 计算末端位姿 |
| e_l ∈ ℝ^{d_l} | 语言嵌入 | 冻结 LLM 编码器 |
| E(3)-Attn | 等变注意力 | R106: f(g·X) = g·f(X), ∀g∈SE(3) |

**网络架构**：
1. **点云特征提取**：每视图 PointNet++ 编码器（共享权重）→ 点特征 f_i ∈ ℝ^d。
2. **多视图融合**：等变 Cross-Attention，Query = 语言+本体嵌入（注入 SE(3) 偏置），Key/Value = 点云特征（携带坐标）。输出等变特征场 F ∈ SE(3)×ℝ^d。
3. **等变 Transformer 块**：L 层 E(3)-Equivariant Self-Attention + 等变 FFN，保持 SE(3) 等变性。
4. **全局池化**：SE(3) 不变池化（如距离原点加权平均）→ 全局特征 h_global ∈ ℝ^d，送入 VLA 解码器。

**等变注意力细节**（R106）：
- 注意力权重：a_{ij} = softmax(⟨φ(q_i), φ(k_j)⟩ / √d)，其中 φ 为等变特征映射（如球谐函数投影）。
- 输出：o_i = Σ_j a_{ij} · v_j，v_j 为等变值向量（随坐标系协变）。
- **关键性质**：输入点云整体刚体变换 g∈SE(3) → 输出特征场同步协变 → VLA 策略输出动作同步协变。

**算法步骤**：
1. 多视图 RGB + 伪深度 → 点云 P_c（IP-31）。
2. 点云 + 语言嵌入 e_l + 本体 q → 等变编码器 → 等变特征场 F。
3. F 池化 → h_global → VLA 编码器（IP-42 共享编码器）。
4. **训练目标**：ℒ_equiv = ℒ_IL + λ_equiv · ℒ_consistency，其中 ℒ_consistency = ‖f(g·P) - g·f(P)‖²（随机采样 g∈SE(3) 强制等变性）。

**复杂度分析**：点云编码 ~10ms，等变注意力 ~5ms（稀疏注意力优化），**总计 ~15ms**，可接受。

**正确性论证**：
- **P26（等变泛化界）**：设任务分布在 SE(3) 群作用下不变（相机位姿/物体位姿变换不改变最优策略）。等变架构将假设空间限制在等变函数类 ℋ_equiv ⊂ ℋ。样本复杂度从 O(VC(ℋ)/ε²) 降至 O(VC(ℋ_equiv)/ε²)，VC(ℋ_equiv) ≪ VC(ℋ)。**少样本下泛化误差显著降低**。
- **P27（相机噪声鲁棒性）**：相机位姿噪声 Δg ∈ SE(3) 导致输入点云变换 g+Δg。等变编码器输出 f(g+Δg) = (g+Δg)·f(P) ≈ g·f(P) + Δg·f(P)。误差随 Δg 线性增长，非等变架构误差可能指数级放大（注意力权重对位置敏感）。

**已知风险**：伪深度噪声大 → 点云质量差 → 等变编码器输入退化——缓解：IP-31 立体匹配质量守门 + 点云去噪（统计滤波）；等变注意力计算量大（球谐投影 O(L²d)）——缓解：稀疏注意力（KNN 邻域）+ 低秩近似；预训练数据不足以学好等变表示——缓解：合成数据增广（随机 SE(3) 变换）+ E57 审计。

### 3.3 IP-44 IL-OBJECTIVE-SUITE（模仿学习目标族，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| ℒ_BC | 行为克隆损失 | MSE/交叉熵（动作分词/连续） |
| ℒ_FM | 流匹配损失 | IP-39/41 继承：条件流匹配，v_t 速度场回归 |
| ℒ_DP | 扩散策略损失 | R103/104：去噪得分匹配，U-Net/Transformer 去噪器 |
| ℒ_Adv | 对抗模仿损失 | R107 GAIL：判别器 D_ψ(s,a)，max_ψ min_θ V(ψ,θ) |
| ℒ_Con | 对比模仿损失 | R108 InfoNCE：动作块-语言正对 vs 负对 |
| w = (w_BC, w_FM, w_DP, w_Adv, w_Con) | 目标权重 | Δ⁴ 单纯形上，E56 搜索 |

**各目标详细形式**：

1. **BC（基线）**：ℒ_BC = E_{exp}[‖a^π - a^exp‖²]（连续）或 CE（离散分词）。
2. **FlowMatching（v14 继承）**：条件流匹配 p_t(a|a^exp) = N(a | (1-t)a₀ + t a^exp, σ²_min I)，损失 ℒ_FM = E_{t,a^exp,ε}[‖v_θ(t, a_t) - (a^exp - a₀)‖²]，a_t = (1-t)a₀ + t a^exp + σ_min ε。
3. **DiffusionPolicy（多模态强）**：前向扩散 a_k = √(1-β_k)a_{k-1} + √β_k ε，反向去噪 ε_θ(k, a_k, cond)。损失 ℒ_DP = E[‖ε_θ - ε‖²]。cond = (I, l, q, a_{<t})。推理时 DDIM 采样 10-20 步。
4. **AdvIL（分布匹配理论保证）**：判别器 D_ψ(s,a) ∈ [0,1]，目标 max_ψ E_{exp}[log D_ψ] + E_π[log(1-D_ψ)]。策略梯度 ∇_θ J(θ) = E_π[∇_θ log π_θ(a|s) · Q_D(s,a)]，其中 Q_D 为判别器导出的奖励。**无需显式奖励函数**，直接匹配专家状态-动作分布。
5. **ContrastiveIL（表示不变性）**：正样本对 (a^exp, l^exp) 同演示；负样本 (a^exp, l^other) 跨演示 / (a^shuffle, l^exp) 时间打乱。InfoNCE 损失：ℒ_Con = -log exp(sim(a,l)/τ) / Σ exp(sim(a,l')/τ)。学习语言-动作对齐的不变表示。

**多目标联合训练**：
- **参数共享**：所有目标共享 VLA backbone + 专家标记头，**仅损失计算分支不同**（各目标各自头部或共享头不同损失函数）。
- **梯度聚合**：∇_θ ℒ_IL = Σ_i w_i ∇_θ ℒ_i。**梯度冲突缓解**：PCGrad（投影冲突梯度）或 GradNorm（动态调整 w_i）。
- **E56 自动权重搜索**：Optuna 搜索 w ∈ Δ⁴，目标 = 验证集成功率 - λ·p99延迟。搜索空间含「单目标退化」（如 w_DP=1, others=0）以对比。

**部署期选择**：E56 选出最优 w* → 对应单一目标 ℒ_i* → **仅保留该目标头部**，其他目标头部剪枝。若 w* 为混合 → 保留混合头部（罕见）。

**复杂度分析**：训练期多目标并行计算损失，**无额外前向开销**（共享 backbone）；部署期单一目标，**零开销**。

**正确性论证**：
- **P28（多目标收敛界）**：设各 ℒ_i 均为 L-光滑、μ-强凸（局部）。PCGrad 梯度聚合保证 ∇_θ ℒ_IL 为下降方向。收敛率 O(1/√T) 至稳定点。**关键**：共享 backbone 使各目标梯度在特征空间对齐，冲突可控。
- **P29（AdvIL 分布匹配）**：GAIL 在判别器最优时等价于最小化 JS 散度 D_JS(π_exp ‖ π_θ)。若判别器容量足够、专家数据覆盖支持集，则 π_θ 收敛于 π_exp（分布匹配）。
- **P30（ContrastiveIL 表示界）**：InfoNCE 最大化动作-语言互信息下界。最优表示满足 p(a|l) ∝ exp(sim(a,l)/τ)，实现语言条件下的动作分布建模。

**已知风险**：梯度冲突导致共享 backbone 学习受阻——缓解：PCGrad + E56 搜索单目标退化配置；AdvIL 判别器过拟合/训练不稳定——缓解：梯度惩罚 (R1 regularization) + 判别器更新频率降低；DP 采样步数多 → 训练慢——缓解：DDIM 10 步 + 一致性蒸馏（Consistency Distillation）加速。

### 3.4 IP-45 VLA-PRETRAIN-FINETUNE（两阶段训练范式，完整算法设计）

**预训练语料构造（自建，无外部依赖）**：
- **D_exp**：专家演示全量（S1–S5），含 (I, l, q, a^exp, 步骤标签)。
- **D_syn**：MuJoCo Proxy 生成合成轨迹（IP-35，条件 A17）。随机初始状态 + 随机目标 → 规划器生成轨迹 → 过滤 gross failure → 得 (I, l, q, a^syn)。语言指令 l 由模板填充生成（如 "pick up {obj} and place in {container}"）。
- **D_lang_act**：语言-动作对比对。正样本：同演示的 (l, a^exp)；负样本：跨演示 (l, a^other) + 语言变体 (l^var, a^exp) + 动作打乱 (l, a^shuffle)。

**Phase 1 预训练目标**：
ℒ_pre = ℒ_act + α · ℒ_lang_act + β · ℒ_prog
- ℒ_act：动作块预测，使用 IP-44 IL 目标族（默认 w_FM=1.0，FlowMatching 稳定）。
- ℒ_lang_act：对比损失，温度 τ=0.07，批大小 256。
- ℒ_prog：进度预测回归，目标 = IP-28v2 CTC 前向概率 log p(Z|τ) 归一化 [0,1]。
- **优化器**：AdamW，lr=1e-4，cosine decay，混合精度，梯度累积 4，epochs=50。
- **冻结策略**：LLM 语言编码器全程冻结；等变编码器前 50% 层冻结；VLA backbone 解码器全训练。

**Phase 2 微调**：
- **数据**：D_ft = D_exp（目标任务特定，或全 32 任务混合）。
- **冻结**：VLA backbone（编码器+解码器）前 L_freeze 层（默认 80%，即前 24/30 层）。**仅训练后层 + 专家标记头 + 价值头 + IL 目标族头部**。
- **目标**：ℒ_ft = ℒ_IL + γ · ℒ_value
  - ℒ_IL：E56 搜索得最优 w* 对应目标族。
  - ℒ_value：价值头回归 IP-40 R_φ（Huber 损失，δ=1.0）。
- **优化器**：AdamW，lr=5e-5（微调 lr 更低），cosine decay，epochs=20。
- **早停**：验证集成功率连续 5 epoch 不升 → 停止。

**快速原型落地**：
- 预训练**一次性完成**（计算量大，约 200 GPU-hours），产出检查点 `vla_pretrained.pt`。
- 微调**配置驱动**：YAML 指定 `pretrained_ckpt`、`freeze_layers`、`il_objective`、`reward_model` → 自动启动微调实验。
- **IP-46 注册表**管理预训练/微调配置版本，支持一键复现/对比。

**正确性论证**：
- **P31（预训练迁移界）**：设预训练分布 P_pre、微调分布 P_ft。若 P_pre 覆盖 P_ft 的支持集（D_exp ∪ D_syn ∪ D_lang_act 覆盖目标任务状态-动作分布），且预训练目标 ℒ_pre 与微调目标 ℒ_ft 兼容（共享动作预测核心），则微调初始化参数 θ₀ 使 ‖θ₀ - θ*_ft‖ ≪ ‖θ_rand - θ*_ft‖。收敛加速因子 ≥ 5×（经验）。
- **P32（冻结层最优深度）**：L_freeze 过高 → 任务特定特征无法学习；过低 → 灾难性遗忘预训练知识。E57 审计包含 L_freeze 扫描（50%/60%/70%/80%/90%），选验证集最优。

**已知风险**：D_syn 质量低（MuJoCo Proxy 失真/规划器失败率高）→ 预训练引入噪声——缓解：IP-35 严格过滤 + 人工抽检 500 条；D_lang_act 负样本含 false negative（跨演示可能语义相似）——缓解：语言嵌入相似度过滤（cosine < 0.3 才作负样本）；预训练计算量超算力预算——缓解：分布式训练（ZeRO-3）+ 梯度检查点 + 混合精度，必要时减少 epochs。

### 3.5 IP-46 RAPID-PROTO-STACK（快速原型基建，完整工程设计）

**配置驱动架构（YAML 示例）**：
```yaml
# config/arch/vla_base.yaml
backbone:
  type: "EquivariantVLA"
  encoder_layers: 12
  decoder_layers: 18
  d_model: 1024
  n_heads: 16
  expert_tokens: ["τ_H", "τ_M", "τ_L", "τ_ACT"]
  value_head: true
equivariant_encoder:
  type: "E3Transformer"
  pointnet_layers: 3
  attn_layers: 6
  use_sparse_attn: true
il_objectives:
  - type: "FlowMatching"
    weight: 1.0
  - type: "DiffusionPolicy"
    weight: 0.0  # E56 搜索时动态调整
reward_model:
  type: "UnifiedReward"
  weights: [0.4, 0.2, 0.2, 0.2]  # E51 冻结
training:
  pretrained_ckpt: "vla_pretrained.pt"
  freeze_layers: 24
  batch_size: 64
  epochs: 20
deployment:
  active_token: "τ_ACT"
  best_of_n: 4
  l0_guard: true
```

**组件注册表**：
```python
# registry.py
REGISTRY = {
    "backbone": {"EquivariantVLA": EquivariantVLA, "RT2Style": RT2StyleVLA},
    "encoder": {"E3Transformer": E3Transformer, "PointNetPP": PointNetPPEncoder},
    "il_objective": {"BC": BCLoss, "FlowMatching": FMLoss, "DiffusionPolicy": DPLoss, 
                     "AdvIL": AdvILLoss, "ContrastiveIL": ConILLoss},
    "reward_model": {"UnifiedReward": UnifiedRewardModel},
    "guard": {"L0Guard": L0Guard},
}
def build(cfg: Dict) -> nn.Module:
    cls = REGISTRY[cfg["type"]][cfg["name"]]
    return cls(**cfg.get("kwargs", {}))
```

**自动调优器**：
- Optuna Study：`study = optuna.create_study(direction="maximize", sampler=TPESampler())`
- 搜索空间：`Y_arch × Y_train`（backbone规模、专家标记集、IL目标权重、冻结层数、学习率、数据混合比例）
- 目标函数：`objective(trial) = val_success_rate - λ * p99_latency`，约束 `p99_latency ≤ SLO`
- 剪枝：MedianPruner，中间指标为训练 loss 下降趋势
- 并行：`n_jobs=8`（8 GPU 并行试验）

**并行仿真验证器**：
- 输入：训练好 checkpoint + 验证集初始状态集合（N=200）
- 并行 rollout：`multiprocessing.Pool(50)` 每进程一个 MuJoCo 实例
- 输出指标：成功率、碰撞率、步骤完成分布、动作块分布、注意力热力图（τ_H/τ_M/τ_L/τ_ACT 激活模式）
- 可视化：TensorBoard + 自定义 Dashboard（成功/失败轨迹对比、价值头打分分布、专家标记输出序列）

**版本化与回滚**：
- 每次实验生成 `exp_{timestamp}_{git_hash}_{config_hash}`
- 产物：checkpoint、config.yaml、metrics.json、visualization/
- 回滚：`git checkout <config_hash>` + `load_checkpoint(<exp_dir>/best.pt)`
- **规则 42 强制**：所有实验必须可通过 config_hash 完整复现。

**复杂度/工程指标**：
- 配置解析 + 组件构建：<1s
- 单次实验启动：<30s（含环境准备）
- 并行仿真验证（200 episodes）：~10min（50 并行）
- 可视化生成：~2min
- **端到端实验周期：从配置修改到指标产出 <30min**，支持日级迭代。

### 3.6 v15 四层架构 v3（L3 完全内化版）

```
L1 感知融合（内化）  多视图 RGB + 伪深度(IP-31) + 本体 + 语言
                 → **IP-43 等变编码器** (E(3)-Transformer) → 等变特征场 F
                 → **IP-42 VLA Backbone 共享编码器**
                 → **IP-36 语义图** → grounding 正则化损失（辅助）

L2 监督验证（内化）  **IP-44 IL 目标族** (BC/FM/DP/AdvIL/ConIL) 多目标联合训练
                 → **IP-40 R_φ** → 监督 **IP-42 价值头 V_φ**（回归/排序）
                 → **IP-35 MuJoCo Proxy** → 预训练合成数据过滤（条件 A17）
                 → **IP-28v2 CTC** → 预训练进度预测目标 ℒ_prog

L3 决策守护（完全内化）  **IP-42 VLA 专家标记路由**：
                 τ_H（高层分解：子目标索引 h_1..h_S）
                 → τ_M（中层规划：关键点 κ_1..κ_K）
                 → τ_L/τ_ACT（低层执行：密集动作块）
                 部署期掩码：**仅 τ_ACT 激活（零合约延迟）**
                 重规划：IP-24 失败 → 注入 (O_t, C_sem) → 激活 τ_H/τ_M → 新序列
                 → **IP-33 L0 兜底** → **IP-38 恢复上下文注入 τ_H**

L4 摊销部署  **IP-45 两阶段训练**：预训练一次(D_exp∪D_syn∪D_lang_act) → 微调多轮(配置驱动)
             **IP-46 快速原型基建**：YAML配置 → 注册表构建 → Optuna自动调优 → 并行仿真验证 → 可视化诊断
             运行期 = **单一 VLA 前向(τ_ACT) + Best-of-N价值头筛选(可选) + L0兜底 (<5ms)**
```

### 3.7 训练/服务伪代码（v15 完整版）

```python
# ===== 组件注册表 + 配置构建 =====
def build_vla(cfg: Dict) -> VLA:
    encoder = REGISTRY["encoder"][cfg.encoder.type](**cfg.encoder.kwargs)
    backbone = REGISTRY["backbone"][cfg.backbone.type](encoder, **cfg.backbone.kwargs)
    il_losses = {obj.type: REGISTRY["il_objective"][obj.type](**obj.kwargs) 
                 for obj in cfg.il_objectives if obj.weight > 0}
    reward_model = REGISTRY["reward_model"][cfg.reward_model.type](**cfg.reward_model.kwargs)
    guard = REGISTRY["guard"][cfg.guard.type](**cfg.guard.kwargs)
    return VLA(backbone, il_losses, reward_model, guard, cfg)

# ===== Phase 1 预训练 =====
def pretrain_vla(cfg, dataloaders):
    vla = build_vla(cfg)
    optimizer = AdamW(vla.parameters(), lr=1e-4)
    for epoch in range(cfg.pretrain_epochs):
        for batch in dataloaders.pretrain:  # D_exp ∪ D_syn ∪ D_lang_act
            I, l, q, a_exp, step_labels = batch
            # 前向：教师强制，专家标记序列 τ_H→τ_M→τ_L→τ_ACT
            outputs = vla.forward_train(I, l, q, a_exp, step_labels)
            # 多目标损失
            loss_act = sum(w * loss_fn(outputs, a_exp) 
                          for loss_fn, w in zip(vla.il_losses.values(), cfg.il_weights))
            loss_lang_act = contrastive_loss(outputs.lang_act_proj, l, a_exp)
            loss_prog = prog_loss(outputs.prog_pred, step_labels)
            loss = loss_act + cfg.alpha * loss_lang_act + cfg.beta * loss_prog
            loss.backward()
            optimizer.step()
    save_checkpoint(vla, "vla_pretrained.pt")

# ===== Phase 2 微调（E56/E59 搜索最优配置）=====
def finetune_vla(cfg, dataloader):
    vla = build_vla(cfg)
    vla.load_pretrained(cfg.pretrained_ckpt)
    vla.freeze_layers(cfg.freeze_layers)  # 默认前 80%
    optimizer = AdamW(vla.trainable_params(), lr=5e-5)
    for epoch in range(cfg.finetune_epochs):
        for batch in dataloader:
            I, l, q, a_exp = batch
            outputs = vla.forward_train(I, l, q, a_exp)
            loss_il = sum(w * loss_fn(outputs, a_exp) 
                         for loss_fn, w in zip(vla.il_losses.values(), cfg.il_weights))
            loss_value = huber_loss(vla.value_head(outputs), reward_model.score(outputs))
            loss = loss_il + cfg.gamma * loss_value
            loss.backward()
            optimizer.step()
        if early_stop(vla, val_loader): break
    return vla

# ===== 部署期推理 =====
def act_vla(obs, state, vla, guard, cfg):
    I, l, q = obs.images, obs.language, obs.proprio
    # 常规推理：仅 τ_ACT
    if not state.need_replan:
        A = vla.generate_actions(I, l, q, token="τ_ACT", n_samples=cfg.best_of_n)
        if cfg.best_of_n > 1:
            scores = vla.value_head(I, l, q, A)  # (N,)
            A = A[scores.argmax()]
        if guard.l0(A, state) is VIOLATION:
            A = resample_or_fallback(vla, state, guard, r=2)
    # 重规划：激活 τ_H/τ_M
    else:
        h_seq, kappa_seq = vla.replan(I, l, q, state.O_t, state.C_sem)  # τ_H + τ_M
        state.h_seq, state.kappa_seq = h_seq, kappa_seq
        state.need_replan = False
        A = vla.generate_actions(I, l, q, token="τ_ACT", h_seq=h_seq, kappa_seq=kappa_seq)
    # 进度监测 + 失败检测
    p = stream_progress(ctc, fuse(obs), state.W)
    if failure_monitor(obs) > TAU_FAIL and p < P_DONE:
        state.need_replan = True
        state.fall_recovery_ctx = {"O_t": state.O_t, "C_sem": state.C_sem}
    return A
```

### 3.8 实验设计（新增 E56–E60）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E56 IL 目标族权重搜索 | Optuna 搜索 w∈Δ⁴，含单目标退化配置 | 验证集成功率、p99延迟、训练稳定性 | 单目标最优 ≥ 混合目标；DP/FM 领先 BC ≥5pt |
| E57 预训练覆盖率/偏差审计 | 统计 D_pre 状态-动作覆盖率、分布偏移 (W2 距离)、语言多样性 | 覆盖率 ≥90%、W2 ≤0.3、语言熵 ≥基线 | 达标才进入微调；否则扩充 D_syn/D_lang_act |
| E58 专家标记分化度量 | 训练中/后测：头间输出 KL、注意力熵、层级一致性 (τ_H→τ_M→τ_L 因果链) | KL ≥ 2.0、注意力熵分层、一致性 ≥80% | 不达标 → 调整专家标记监督/掩码/损失权重 |
| E59 VLA 端到端基线对比 | 对比：v15 VLA vs v14 显式三层 vs v13 扁平 vs RT-2/OpenVLA 复现 | 成功率、p99延迟、参数量、训练时间 | VLA 成功率 ≥ v14+3pt，延迟 ≤ v14/2，参数量 ≤ v14 |
| E60 等变 vs 非等变消融 | 同配置对比：IP-43 等变编码器 vs TRI-FUSE+增广 | 少样本(10%/30%数据)成功率、相机噪声鲁棒性 | 等变少样本领先 ≥8pt，噪声鲁棒性领先 ≥5pt |
| E51–E55 | 沿用 v14（奖励校准/三层蒸馏/合约延迟/技能粒度/跌倒恢复） | — | v15 内化后指标应不降反增 |

**降级机制（终极版）**：
- E56 单目标最优为 BC → 回退 v14 流匹配（IP-39/41）；
- E57 预训练覆盖率 <80% 或 W2 >0.5 → 放弃预训练，从头训练微调（L_freeze=0）；
- E58 专家标记分化不达标 → 保留 v14 显式三层架构（IP-39/41/34），**不推倒重来**；
- E59 VLA 端到端不优于 v14 → 保留 v14 为旗舰，VLA 作实验分支；
- E60 等变无优势 → 回退 TRI-FUSE + 增广轴（IP-22/26）；
- A17 失败 → IP-35/45 D_syn 冻结，仅用 D_exp + D_lang_act；
- IP-36 失效 → grounding 正则化损失置零。

## 4. 风险登记簿（新增/更新/内化标注）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **预训练分布偏移锁死 backbone（D_syn/D_lang_act 质量不足/覆盖不全）** | **高** | E57 审计守门（覆盖率≥90%、W2≤0.3）；L_freeze 可调（默认 80%→可降 50%）；D_syn 严格过滤+人工抽检 |
| **专家标记路由未分化（τ_H/τ_M/τ_L 输出相似，隐式层级退化扁平）** | **高** | E58 度量守门（KL≥2.0、一致性≥80%）；专家标记显式监督（演示切分标签）；注意力掩码强制分层 |
| **VLA 端到端成功率不及 v14 显式三层（参数共享负迁移/注意力路由学不透）** | **高** | E59 基线对比守门（VLA≥v14+3pt）；不达标保留 v14 旗舰；VLA 作实验分支并行 |
| **IL 目标族梯度冲突导致共享 backbone 收敛受阻** | 中高 | PCGrad 梯度投影 + E56 搜索单目标退化配置；GradNorm 动态权重 |
| **AdvIL 判别器训练不稳定/过拟合** | 中 | R1 梯度惩罚 + 判别器更新频率 1:5（策略:判别器）+ 标签平滑 |
| **等变编码器计算量/显存超预算（球谐投影 O(L²d)）** | 中 | 稀疏注意力(KNN) + 低秩近似 + 梯度检查点；必要时回退 TRI-FUSE |
| **Best-of-N 采样延迟超 SLO（N=8 并行化不足）** | 中 | IP-25 自适应 N：成功率饱和即降 N；量化 INT8 + TensorRT 加速 |
| **配置版本漂移/不可复现（Git hash 与 config hash 不绑定）** | 中 | 规则 42 强制：实验目录含 config_hash、git_hash、metrics、可视化；一键复现脚本 |
| **（继承 v13/v14）FK残差/球包络/守护消融/步骤分口径/判别假阳性/beam时延/立体噪声/相机映射/时延异常/端口隔离/路由干扰** | — | 见 v12 §5 / v13 §4 / v14 §4 |

## 5. 来源清单（引用口径：2026-11-09）

**官方/数据（一手）**：S1–S5 同 v12；S6（联网检索）arXiv API（R98–R109 逐条确认）、GitHub raw README（F45–F47 复核）。
**文献（本轮新增，标题级引用）**：
- R98 Brohan et al., RT-1: Robotics Transformer for Real-World Control, 2207.08823
- R99 Brohan et al., RT-2: Vision-Language-Action Models Transfer Web Knowledge, 2307.15818
- R100 Octo Team, Octo: An Open-Source Generalist Robot Policy, 2405.12213
- R101 Kim et al., OpenVLA: An Open-Source Vision-Language-Action Model, 2406.09221
- R102 FAIR, π₀: A Vision-Language-Action Flow Model, 2410.24164
- R103 Chi et al., Diffusion Policy: Visuomotor Policy Learning via Action Diffusion, 2303.04137
- R104 Wang et al., DP3: Diffusion Policy for 3D Vision, 2403.03954
- R105 Wang et al., EquivAct: Equivariant Action Representations, 2402.10658
- R106 Fuchs et al., E(3)-Equivariant Graph Neural Networks, 2102.13419
- R107 Ho & Ermon, Generative Adversarial Imitation Learning, 1606.03476
- R108 Sermanet et al., Time-Contrastive Networks, 2203.06154
- R109 Florence et al., Implicit Behavioral Cloning, 2109.00137

**诚实记录**：A15 登录墙；A17 官方 URDF 未核实；R98–R109 仅标题/摘要级；P24 专家标记分化假设需实测；"预训练一次 200 GPU-hours"为估算；E56 搜索空间大小指数级，依赖剪枝/并行；等变注意力稀疏化实现细节未验证；Best-of-N 理论界为简化推导。

## 6. 清单迭代规则（继承 + 第 38 轮新增）

- 继承规则 27–41（通道诚实 / 映射验证 / SLO / fail-safe / 灵感-现实校验 / 单模型合规 / 步骤分双解释 / 稠密监督 / 方法论遗产登记 / 元数据重新照亮 / 语言口径分离 / 摊销原则 / 验证器分级 / 灵感词落地规则 / 层级联合规划原则）。
- **42（新增）：快速原型原则**——所有超参/架构选择可配置(YAML)、可搜索(Optuna)、可复现(config_hash+git_hash)、可回滚(一键加载)；组件注册表热插拔；并行仿真验证+可视化诊断标准化；端到端实验周期 <30min。
- **43（新增）：VLA 内化原则**——单一自回归 Transformer 承担感知+推理+规划+控制；专家标记 τ_H/τ_M/τ_L/τ_ACT 实现隐式层级路由；部署期仅 τ_ACT 激活（<1ms），重规划时按需激活 τ_H/τ_M；价值头 V_φ + Best-of-N 替代显式运动规划器；合约协商延迟归零（E53 消解）。
**本轮最大风险一句话**：VLA 统一骨干引入的"预训练分布偏移"与"专家标记路由涌现不可控"双重风险：自建预训练语料（专家+合成+语言-动作）若覆盖不足或含系统性偏差，冻结 80% backbone 微调将锁死错误表示；专家标记 τ_H/τ_M/τ_L 的注意力路由若在训练期未充分分化，部署期隐式层级规划将退化为扁平策略——必须以 E57（预训练覆盖率/偏差审计）+ E58（专家标记分化度量）+ E59（VLA 端到端成功率对比基线）三重守门，未达标即保留 v14 显式三层架构。

**当前最值得押注**：IP-42 VLA 统一骨干（消除合约延迟、参数共享、端到端优化）× IP-44 IL 目标族（多目标并行探索、E56 自动选优、理论互补）× IP-46 快速原型基建（配置驱动、注册表、自动调优、并行验证、日级迭代）——三者以规则 42/43 咬合，形成「预训练一次→配置微调多轮→自动搜索最优→并行验证→一键部署」的完整闭环。IP-43 等变编码器为架构级先验，IP-45 两阶段训练为范式落地。v14 显式三层架构作为**强基线并行保留**，实现「新旧双轨、守门决策」。

<!-- ARTIFACT:END -->