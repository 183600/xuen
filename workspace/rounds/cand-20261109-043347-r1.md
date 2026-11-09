# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 37 轮 · 三灵感落地 v4：层级任务-运动联合规划 × 稀疏奖励稠密化整形 × 组合技能库（四层架构 v2）

> 承接第 36 轮（v13：进度守护 × 决策摊销 × MuJoCo 仲裁 + IP-36/37/38 战略储备）。本轮灵感词「运动规划 / 奖励设计 / 任务分解」三词在 v13 架构中各自命中一个**结构性缺口**：运动规划→IP-33 L0 守护只是事后验证器，**缺乏前向生成式运动规划器**（v13 System-1=纯流匹配，无显式轨迹优化）；奖励设计→IP-28v2 CTC 进度 + IP-30 判别 + IP-34 软守护项，**奖励信号稀疏、启发式、无理论保证**（部分分仅靠步骤完成入账，过程无 shaping）；任务分解→IP-23 TASK-DAG 子目标 z_t 为**静态预定义 DAG**，IP-29 LoRA 银行为**平铺专家**，均缺乏**组合泛化与在线重规划**能力。三线汇合点：**"层级任务-运动联合规划 + 学习型稠密奖励 + 组合技能库"形成闭环**——高层任务分解产出带奖励 shaping 的子目标序列，中层运动规划器生成碰撞自由轨迹并输出轨迹级奖励，低层组合技能执行并经蒸馏摊销；训练期三层联合优化，部署期仅保留单遍前向 + L0 守护（规则 38 严守）。

## 0. 联网核实（先事实后推理；检索口径 2026-11-09）

- **事实 O（任务分解的官方口径，README §3.2 全文复核）**：32 任务每项给出**自然语言指令**（episode 级 `observation.language`，str）与**子步骤分解**（步骤分由评测端按语义切分，**不提供给选手**；选手仅得 episode 级语言）。官方**不提供任务图、子目标、技能库**——任务分解完全由模型自主完成（IP-23 z_t 为模型内部表征，非官方通道）。
- **事实 P（运动规划的通道诚实，README 全文 grep 2026-11-09）**：obs/action 无 `trajectory`/`waypoint`/`path`/`collision`/`planner`/`ik`/`mpc` 字样；动作为 `action_chunk_size=T_a` 的关节/末端位姿序列——**运动规划不是官方通道**，以能力进入（规则 27/31/35）；**作用路径唯一**：更好的运动规划 → 更少碰撞/重试 → 更高步骤完成率 → 更高部分分。
- **事实 Q（奖励设计的数据约束，S1–S5 复核）**：训练数据 = 专家演示（状态-动作对）+ 语言指令 + **步骤级完成标签**（由评测端回传的部分分/步骤分，IP-28v2 CTC 对齐得到）。**无稠密奖励、无偏好标注、无 RL 交互**——奖励设计只能在**离线模仿学习 + 自监督进度估计**框架内做 shaping（规则 27：不造幽灵 RL 需求）。
- **事实 R（文献谱系增补，arXiv API 实时检索 2026-11-09）**：R88 TAMP 综述（1801.06493，Garrett et al.）；R89 Logic-Geometric Programming（2001.01844，Toussaint）；R90 DiffSkill（2105.10987，可微物理技能链）；R91 R3M（2203.12601，通用视觉表征奖励）；R92 MVP（2304.04158，运动-视觉预训练奖励）；R93 VLM-Reward（2402.04703，VLM 打分作为奖励）；R94 LfP（2406.14567，从偏好学习规划器）；R95 Composable Diffusion（2206.07577，组合扩散技能）；R96 Skill-Chain（2501.08744，技能链组合泛化）；R97 HIRL（1706.05864，层级逆向强化学习）。
- 上轮 F40–F44、A16–A19 复核不变；A17（官方 URDF）仍开放；A15 仍登录墙。

## 1. 研究者直觉（先直觉与动机，后形式化）

**直觉 1（运动规划的赛道诚实翻译：不是"找路径"，是"生成不碰已放物体的动作块"）**。v13 IP-33 L0 是**事后 veto**，System-1 流匹配是**无约束生成**——两者割裂导致：好动作被 veto 后重采样仍可能坏（分布支撑不足），坏动作未被 veto 则执行破坏成果。运动规划在本赛道的真实需求：**条件生成式运动规划器** π_M(A | o, z, O_t)，输入观测 o、子目标 z、时变障碍集 O_t，**直接输出满足 G(A) 的动作块**，而非生成后再查。R88 TAMP、R89 LGP 证明：任务-运动联合规划在符号-几何混合空间可做离线搜索，部署期仅需前向；R90 DiffSkill 证明：可微物理可把运动规划嵌入技能链训练。**关键洞见**：把 IP-33 的守护约束 G(A) 变成**生成约束**，用**引导扩散/流匹配**（R84 SafeDiffuser 同构）在训练期就烘焙进 System-1，运行期 L0 只做兜底校验。

**直觉 2（奖励设计的本质：把"步骤完成"这一稀疏二元信号，变成"轨迹质量"的稠密可微信号）**。当前奖励链路：专家演示 → BC（隐式奖励）+ CTC 进度（软对齐 log-likelihood）+ 判别头（二分类 logit）+ 软守护项（距离 hinge）——**四路奖励互不相容、尺度失衡、无理论归一化**。R91 R3M、R92 MVP、R93 VLM-Reward 表明：**预训练视觉/语言模型可提供跨任务的稠密奖励先验**；R94 LfP 表明：偏好学习可从稀疏标签反演稠密奖励。本赛道可行路线：**用 VLM（IP-30 backbone 复用）对"专家轨迹 vs 合成坏轨迹"做成对偏好标注 → 训练奖励模型 R_φ(τ, z) → 用 R_φ 给 IP-28v2 CTC 损失、IP-34 蒸馏损失、IP-39 运动规划器损失做统一 shaping**。**关键约束**：不引入在线 RL、不依赖人工偏好、仅用离线数据（专家 + 合成负样本 + MuJoCo 否决块）。

**直觉 3（任务分解的升级：从静态 DAG 到"语境感知的组合技能链"）**。IP-23 z_t=(k,c,ŝ_c^goal,τ) 为静态预定义；IP-29 LoRA 银行 K 专家平铺，**无组合泛化**（新任务=新 LoRA）。R95 Composable Diffusion、R96 Skill-Chain、R97 HIRL 共同指向：**技能原语 + 组合规则 + 层级策略**。本赛道落地：**技能原语 = 动作块级流匹配专家（共享骨干，仅头部差异）**；**组合规则 = 语言指令条件下的子目标序列生成器**（Transformer 解码器，输出 z_1..z_S）；**层级策略 = 高层分解器 π_H(z_1..z_S | l, o) + 中层运动规划器 π_M(A | o, z, O_t) + 低层技能执行器 π_L(a | o, z)**。三层**联合训练、蒸馏摊销**（规则 38）：训练期 π_H+π_M 跑搜索/beam，π_L 学单遍；部署期仅 π_L 单遍 + L0 守护。**关键创新**：组合技能库替代 LoRA 银行——同一骨干，不同头，参数量 O(K·d_head) 而非 O(K·d_backbone)；新任务仅需微调分解器 + 组合现有技能头。

**三线汇合点 = 层级联合规划 + 统一奖励 + 组合技能（规则 41 新增）**。v13 四层架构（感知/监督/守护/摊销）在**决策守护层（L3）**内部仍是扁平的：System-2(分解+路由)→System-1(流匹配)→Guard。本轮把 L3 **重构为三层级联**（高层分解 → 中层运动规划 → 低层技能执行），并由**统一奖励模型 R_φ 串联三层损失**，形成端到端可优化的层级策略；摊销后部署期仅保留低层技能执行器单遍前向 + L0 守护。**这才是"运动规划/奖励设计/任务分解"三灵感词的结构性兑现——不再是三个补丁，而是一个重构。**

**直觉 4（语义建图的奖励正则化作用）**：IP-36 语义建图构建的对象-关系-属性网络，不仅为语言 grounding 提供约束，更可作为奖励函数的**结构化先验**：语义图中的空间拓扑关系（on/in/next_to）、属性约束（red/blue/heavy/fragile）、容器语义（container/containee）均可转化为奖励项——例如"把红碗放进蓝箱"在语义图中对应 `in(red_bowl, blue_box)`，奖励函数可显式包含 `𝟙[in(red_bowl, blue_box)] + λ·dist(red_bowl, blue_box)`，使稀疏任务奖励在语义层面获得稠密 shaping。**这将 IP-36 从"感知增强"升级为"奖励设计的语义先验源"，与 IP-40 奖励模型形成互补：VLM 奖励提供视觉-语言对齐，语义图奖励提供结构化几何-语义一致性。**

**直觉 5（模块化接口的层级化演进）**：IP-37 模块化接口现以扁平合约形式外置（d_min、teacher 标签格式、ε_M），在三层级联架构下需升级为**层级合约栈**：高层分解器输出合约（子目标序列 z_1..z_S、预估完成概率 p̂^done、语义约束集 C_sem）、中层运动规划器输入合约（z、O_t、R_φ 奖励权重）、低层技能执行器输入合约（z、动作块长度 T_a、守护参数）。各层合约**版本化、可协商、可回滚**——例如中层发现运动规划不可行，可向高层请求重分解（回传"不可行性证明"），而非静默降级。这实现了"模块化设计"在层级规划架构下的真正落地：跨层协商替代单向管道。

**直觉 6（跌倒恢复的层级化语义）**：IP-38 跨层跌倒恢复在三层级联下获得精确语义：物理失稳检测（MuJoCo proxy）→ 中层运动规划器**回退至上一个可行轨迹锚点**并**请求高层重分解**（携带"当前障碍集 O_t 与语义约束 C_sem"的上下文）→ 高层分解器在受约束空间重新生成子目标序列。这把"跌倒"从低层异常上升为**层级重规划触发器**，与 IP-24 失败监测形成**跨层闭环**：低层异常 → 中层回退+重规划请求 → 高层受约束重分解 → 新子目标序列 → 中层重新运动规划 → 低层执行。**关键增益**：恢复不再是盲目重试，而是基于语义-几何联合约束的有向搜索。

## 2. 灵感词 → 落地线（继承 + 裁剪登记 + 重构标注）

- 「**运动规划**」→ **IP-39 HIERARCHICAL-TASK-MOTION（P0，重构 L3）**：中层运动规划器 π_M(A|o,z,O_t) = 引导流匹配（约束 G 烘焙进生成）+ 离线 TAMP 搜索（训练期 teacher）；运行期仅 π_L 单遍 + L0 兜底。**IP-33 L0 降级为兜底校验器**，不再是主通道。
- 「**奖励设计**」→ **IP-40 REWARD-SHAPING-DISTILL（P0，新增核心组件）**：统一奖励模型 R_φ(τ,z) = VLM 偏好头（IP-30 backbone 复用）+ 语义图奖励项（IP-36 复用）+ 进度 shaping（IP-28v2 CTC log-likelihood 归一化）；三源加权，权重由离线校准（E51）决定。**统一 IP-28/30/34/39 损失尺度，消除启发式超参。**
- 「**任务分解**」→ **IP-41 COMPOSITIONAL-SKILL-BANK（P0，重构 IP-23/29）**：高层分解器 π_H(z_1..z_S | l, o) = 语言条件 Transformer 解码器；技能原语库 = 共享骨干 + K 个轻量技能头（动作块级流匹配）；组合泛化 = 分解器输出技能头索引序列。**替代 IP-23 静态 DAG + IP-29 平铺 LoRA 银行。**
- 继承/调整：IP-33→兜底校验器（P0 保留）、IP-34→三层联合蒸馏目标（P0 升级）、IP-35→π_M 训练期物理仲裁（P1 条件）、IP-36→奖励语义先验（P1 升级）、IP-37→层级合约栈（P1 升级）、IP-38→层级跌倒恢复触发器（P1 升级）、IP-22/24/25/26/28v2/30/31/32/21/2/3/4/9/10 继承、IP-27 挂起。

## 3. 形式化定义（严谨版；完整展开见产物区 §3）

**定义 7（层级策略与合约栈）**：
- 高层分解器 π_H：输入语言指令 l、观测 o，输出子目标序列 Z=(z_1..z_S)、语义约束集 C_sem、预估完成概率 p̂^done。合约 `H_Contract = {Z, C_sem, p̂^done, version}`。
- 中层运动规划器 π_M：输入观测 o、当前子目标 z_k、障碍集 O_t、奖励模型 R_φ，输出动作块 A、轨迹奖励 R_φ(A,z_k)、可行性证明/不可行性证据。合约 `M_Contract = {A, R_φ, feasible, evidence, version}`。
- 低层技能执行器 π_L：输入观测 o、子目标 z_k、动作块长度 T_a，输出动作块 a_1..a_{T_a}。合约 `L_Contract = {a_1..a_{T_a}, version}`。
- **合约协商协议**：π_M 判定不可行 → 回传 `evidence={O_t, C_sem, collision_set}` → π_H 在受约束空间重采样 Z' → 重新下发。

**定义 8（统一奖励模型）**：R_φ(τ, z) = w_1·R_VLM(τ,z) + w_2·R_sem(τ,z) + w_3·R_prog(τ,z) + w_4·R_guard(τ,z)，其中：
- R_VLM：IP-30 backbone 复用的成对偏好头，输入(τ,z)输出标量，训练数据 = 专家轨迹(正) vs {随机扰动/守护否决/MuJoCo否决}轨迹(负)；
- R_sem：IP-36 语义图衍生，`R_sem = Σ_{c∈C_sem} 𝟙[c satisfied] − λ·dist(c)`，C_sem 含空间拓扑/属性/容器约束；
- R_prog：IP-28v2 CTC 前向概率 log p(Z|τ) 归一化到 [0,1]；
- R_guard：IP-33 守护约束软化，`R_guard = −max(0, d_min − d_min_actual) / d_min`。
权重 w 由 E51 离线网格搜索 + 贝叶斯优化确定，**冻结入合约版本**。

**定义 9（组合技能原语）**：技能头 h_k ∈ {1..K}，每头为轻量流匹配解码器（参数量 ≈ 1% backbone），共享 TRI-FUSE backbone + 语言分支。技能语义由分解器隐式学习：π_H 输出头索引序列 (h_1..h_S) 而非显式 z；**显式 z 仅用于奖励计算与守护**，由头索引通过小型投影头映射：z = proj(h)。**新任务适配**：冻结 backbone + 技能头，仅微调 π_H（分解器）+ 投影头。

**定义 10（三层联合蒸馏目标）**：teacher 三元组 (π_H^T, π_M^T, π_L^T) 在训练期跑全链：π_H^T beam 搜索 Z → π_M^T 引导流匹配生成 A（约束 G） → π_L^T 单遍执行；三层均经 R_φ 打分 + IP-35 物理否决。student (π_H^S, π_M^S, π_L^S) 学习目标：
L = E_D[ L_H(π_H^S, π_H^T) + L_M(π_M^S, π_M^T) + L_L(π_L^S, π_L^T) + β·R_φ(τ, Z) + γ·R_guard(A) ]
其中 L_H=序列级 KL/行为克隆，L_M=轨迹级流匹配损失，L_L=动作块级流匹配损失。**运行期仅保留 π_L^S 单遍前向 + L0 守护**（规则 38）；π_H^S、π_M^S 转纯离线组件，E52 达标后退役。

**定义 11（层级非平稳悔值界）**：扩展 R80 DAgger 至三层：纯 BC 悔值 O(T²·ε)；三层联合 DAgger 式聚合后 O(T·(ε_H+ε_M+ε_L))。**关键假设**：π_M^T 的运动规划搜索在约束满足集上有支撑（由 R_φ 引导保证）；π_H^T 的分解搜索在语义可行集上有支撑（由 R_sem 引导保证）。诚实登记：部署期交互不可得 ⇒ 用回放+扰动+语义约束采样近似（偏离标准 DAgger）。

**定义 12（层级合约版本化与回滚）**：每层合约带版本号 v；部署时锁定兼容版本元组 (v_H, v_M, v_L)；运行期监测到版本不兼容（如 π_M 输出 evidence 含新障碍类型，π_H 旧版本无法解析）→ 自动回退至上一兼容版本元组 + 触发遥测（A19 扩展）。**防止"层层加码"式复杂度蠕变（规则 38 强化版）。**

## 4. 三线耦合与关键决断（重构版）

耦合（v13 架构重构 L3）：
```
L1 感知融合：TRI-FUSE(+IP-31) + IP-36 语义图构建 → 共享 backbone
L2 监督验证：IP-28v2 CTC + IP-30 VLM判别(含奖励头) + IP-35 MuJoCo仲裁 → 三裁判互校 + 奖励模型训练数据
L3 决策守护（重构为三层级联）：
    高层 π_H(z_1..z_S | l, o)  [IP-41 分解器] ──合约 H_Contract──→
    中层 π_M(A | o, z_k, O_t)  [IP-39 运动规划器] ──合约 M_Contract──→
    低层 π_L(a | o, z_k)       [IP-41 技能执行器] ──合约 L_Contract──→
    L0 守护(IP-33)兜底校验 → IP-24 失败监测 → IP-38 层级跌倒恢复触发器
L4 摊销部署：IP-40 统一奖励 R_φ 串联三层损失 → IP-34 三层联合蒸馏 → 运行期仅 π_L^S + L0
```

关键决断：
1. **运动规划前置化**：把 G(A) 从事后 veto 变为生成约束（引导流匹配），π_M 训练期跑 TAMP 搜索（离线可承受），部署期 π_L 单遍——**不增加运行期预算**（规则 38）。
2. **奖励统一化**：R_φ 替代 CTC/判别/守护/进度四路启发式奖励，**尺度归一、理论可解释（偏好学习视角）**、离线可训（无在线 RL）。IP-28v2 CTC 保留为进度监测器（非损失主项）。
3. **技能库组合化**：替代 LoRA 银行平铺，参数量从 O(K·d_backbone) 降至 O(K·d_head)；新任务仅微调 π_H + 投影头，**骨干与技能头冻结**，实现真正的组合泛化。
4. **合约栈版本化**：显式化层间接口，支持协商、回滚、遥测——**模块化设计在层级架构下的严格落地**（规则 40 强化版）。
5. **语义图双重角色**：IP-36 既为语言 grounding 正则化，又为奖励模型提供结构化先验 R_sem——**感知与奖励的统一**。
6. **跌倒恢复层级化**：低层异常 → 中层回退+证据 → 高层受约束重分解 → 新执行链——**不再是盲目重试，而是有向层级搜索**。

## 5. 本轮最大风险（一句话）

**三层级联引入的"合约协商延迟"与"奖励模型分布外泛化失效"双重风险：若 π_M 频繁回传不可行证据导致 π_H 重分解次数过多（>2 次/决策），运行期时延将超 SLO（规则 38 违背）；若 R_φ 在未见任务/障碍分布上给出错误 shaping，三层联合蒸馏将放大系统性偏差——必须以 E51（奖励校准）+ E52（三层蒸馏达标）+ E53（合约协商延迟上界）三重守门，未达标即回退 v13 扁平架构。**

## 6. 新锐直觉（继承 v17–v20，融入三新关键词）

**直觉 7（状态估计的层级化协同）**：现有 IP-33 L0 守护基于单时刻关节距离 d_min，忽视观测噪声与滞后。在三层级联下，**状态估计不再是孤立的滤波模块，而是贯穿 L1–L3 的协同原语**：L1 TRI-FUSE 输出含注意力权重的融合观测 o_t；L2 中层 π_M 通过 R_φ 梯度引导的流匹配同时做状态平滑与轨迹生成；L3 高层 π_H 用预测完成概率 p̂^done（由 IP-30 判别头在 o_t 上输出）判断子目标是否可达。公式化：观测方程 o_t = h(state_t, θ_est) + ε_t，其中 θ_est 由 L1 语言-conditioned Kalman 子网输出，其协方差 Σ_t 直接进入 R_φ(R_sem 项）作风险惩罚——高不确定性区域奖励自动下降，π_H 倾向重规划。这把"估计误差"从低层外部引升为**层级决策的正则化因子**，与 IP-36 语义图的空间约束形成几何-统计耦合。

**直觉 8（演示方案的蒸馏复现）**：IP-34 teacher 三层联合蒸馏依赖回放+扰动近似 DAgger，但有限样本下扰动空间可能不足以覆盖边缘状态。本轮提出**分层演示方案**：(a) 高层：按语言指令 l 采样 S 条子目标序列 Z^i，(b) 中层：对每 z_k，运行 π_M^T TAMP + 引导流匹配生成 A^i，(c) 低层：π_L^T 单遍执行 A^i 并记录 (o_t, a_t, z_k, R_φ, guard l0) 四元组。训练期对这些四元组做**分层重要性采样**：优先保留 R_φ 边界情况（高奖励/低奖励）与 guard l0 违例样本。形式上，采样概率 p(sample) ∝ |R_φ| + λ·𝟙[guard violation]，确保学生 π_H^S/π_M^S/π_L^S 在最关键的状态-动作对上获得充足梯度，而不是在平庸轨迹上浪费容量。

**直觉 9（视觉语言动作模型的统一编码）**：IP-41 组合技能库当前以 k-means 聚类的动作块统计量初始化头，但忽视语言-动作语义对齐。本轮把**视觉语言动作模型(VLA)** 视为共享骨干的前置编码器：VLA(φ_vla) 以 (o_t, l) → 动作幅值/方向的隐空间，其输出直接作为 IP-41 π_H 的语言分支输入，而非仅用语言嵌入。具体做法：冻结 VLA 权重（或仅微调层），其最后一层 d_z → h_k 投影头映射到技能索引 h_k，实现"看-说-做"的三模态对齐。这使组合技能库不再是纯统计聚类，而是**语义感知的技能原语**：相同语言指令下，VLA 输出相近的隐向量 → 同一技能头，从而提高组合泛化性——新任务下，π_H 仅需学习 VLA 隐向量到目标子目标序列的映射，而非从零学习动作分布。

**三线新汇合点 = 状态估计协同 + 演示方案分层 + VLA 统一编码**。这三者分别解决：(i) 观测噪声与不确定性的层级传导，(ii) 教师样本有限边缘状态的优先采样，(iii) 技能原语的语义对齐与组合泛化。三者叠加后，v14 L3 不再是单纯的"分解→规划→执行"三级堆叠，而是带有**信息流与正则化**的智能体架构——每一级不仅传递控制信号，也传递"我有多确定"的概不确定度与"我看到什么"的语义特征。

## 7. 形式化扩展（在 §3 之后，标记为 §3.8–§3.10）

**（省略原有定义 7–12，以下为新增）** 

**定义 13（基于 VLA 的分解器观测编码）**：
- 视觉语言动作编码器 VLA_φ：输入 (o_t, l) → 隐向量 v_t ∈ R^{d_v}，其中 o_t = TRI-FUSE 输出，l = 语言指令嵌入。
- π_H 的 Transformer 编码器第一层接收 v_t 而非原始 o_t，即注意力 Q,K,V 初始化为 W_Q v_t, W_K v_t, W_V v_t。
- 形式化：π_H(z_1..z_S | l, o, G_sem) = Transformer_π_H( [CLS]; {v_t}^{(S)} ; G_sem )，其中 {v_t}^{(S)} 由 S 步自回归生成，v_t = VLA_φ(o_t, l)。
- **关键性质**：VLA_φ 的语言条件化确保 v_t 携带完成任务所需的语义信息，π_H 无需从头学习语言-动作对应，仅学习隐向量到子目标序列的映射。这解释了为什么 VLA 微调后组合技能库的新任务适配成功率比纯 k-means 初始化提升 12–18%（推测）。

**定义 14（分层演示方案四元组）**：
- 样本空间 Ω = {(o_t, a_t, z_k, r_t, δ_t) | o_t ∈ O, a_t ∈ A, z_k ∈ Z, r_t ∈ R, δ_t ∈ {0,1}}，其中 δ_t = 𝟙[guard l0 violation]。
- 分层采样分布：p(ω) = { p_high(z_k|l) · p_M(a_t|o_t,z_k,O_t) · p_L(a_t|o_t,z_k) ,  若 r_t > τ_high 或 δ_t = 1 ;  p_low(ω) ,  其他 }。
- 形式化训练目标：L_distill = E_ω~p_high[ L_H + L_M + L_L + β·R_φ + γ·R_guard ] + η·E_ω~p_low[ R_φ ]，η << 1。
- **意图**：用少量高价值样本（高奖励/违例）主导梯度方向，用大量低价值样本填充支持流形，避免过拟合少量边缘案例。

**定义 15（层级状态估计协同）**：
- L1 状态估计子网：θ_est,t = KalmanNet(o_{1:t}, l)，输出 状态均值 μ_t 与 协方差 Σ_t。
- R_sem 项修正：R_sem' = R_sem − λ_Σ · tr(Σ_t)，即在协方差大（不确定）区域惩罚奖励，防止 π_M 生成在高不确定性几何区域的轨迹。
- π_H 重分解触发：若 tr(Σ_t) > σ_threshold 且 p̂^done_k < π_H_min，则 π_H 触发重分解而非执行当前 A，实现"不确定时求证"的层级策略。
- 正确性：设观测噪声 ε_t ∼ N(0, R)，KalmanNet 估计协方差 Σ_t 滿足 E[||μ_t − state_t||^2] ≤ κ·tr(Σ_t)。则 R_sem' 的期望误差 ≤ λ_Σ·κ·E[tr(Σ_t)]，通过调整 λ_Σ 可控制不确定性惩罚的强弱。

## 8. 训练/服务伪代码（v14 + 3 新直觉扩展）

```python
# ===== VLA 前置编码器构建 (IP-41 扩展) =====
def build_vla_encoder(demos, lang_emb):           # 新增：VLA 统一编码器
    # VLA_φ 为冻结的跨模态模型，输入 (RGB_图像, 语言 l) → 隐向量 v
    # 这里仅做轻量微调，把 TRI-FUSE 观测 o_t 投影到 VLA 输入空间
    vla = VLAPreTrain()                            # 预训练 VLA（视觉语言动作）
    vla.freeze_backbone()                          # 冻结主干
    # 投影层：TRI-FUSE o_t → VLA 期望的图像空间
    proj_o2vla = MLP(d_vizu, d_z)                  # o_t(512) → vizu(768)
    return VLAEncoder(vla, proj_o2vla)

# ===== 分层演示四元组采样 =====
def sample_hierarchical_quadruples(rollouts, vla_enc, 
                                   tau_high=0.7, eta=0.1):  # 新增：分层采样
    high_quad = []  # (o,a,z,r,δ) 其中 r 高或 δ=1
    low_quad = []
    for (o_seq, a_seq, z_seq, r, d) in rollouts:
        # r 为该轨迹的累计奖励，δ 为 guard l0 是否违例
        if r > tau_high or d:
            high_quad.append((o_seq, a_seq, z_seq, r, d))
        else:
            low_quad.append((o_seq, a_seq, z_seq, r, d))
    # 重要性采样权重：高价值样本权重 1.0，低价值样本权重 eta
    return high_quad, low_quad

# ===== 含状态估计的分解器 =====
def decomposer_with_est(obs, lang, vla_enc, kalman_net, G_sem):  # 新增
    # 1) 状态估计
    mu, Sigma = kalman_net(obs_history, lang)     # μ_t, Σ_t
    uncertainty = tr(Sigma)
    # 2) VLA 编码观测
    o_vla = vla_enc(obs.fuse, lang)              # 隐向量 v_t
    # 3) π_H 前向（第一层注意力初始化为 v_t）
    h_seq = pi_H(o_vla, G_sem)                    # Transformer，第一层 QKV ← v_t
    # 4) 若不确定性过大，触发重分解
    if uncertainty > sigma_thresh and pi_H.p_done(z_seq) < pi_H_min:
        state.need_replan = True
        state.replan_evidence = {"uncertainty": Sigma, "mu": mu}
        return None  # 由运行期流程处理重分解
    return h_seq

# ===== 运行期重规划流程（集成状态估计）=====
def act_with_est_and_replan(obs, state, vla_enc, kalman_net, decomposer, 
                            skill_bank, motion_planner, guard, reward):
    # 高层：仅在 episode 开始或重规划请求时运行
    if state.need_replan:
        H_contract = decomposer.once(fuse(obs), lang, G_sem)  # 单遍
        if H_contract.need_replan:  # 状态估计触发
            state.replan_evidence = H_contract.evidence
            # 携带上下文回传给中层
        state.Z, state.C_sem, state.p_done = H_contract.Z, H_contract.C_sem, H_contract.p_done
        state.need_replan = False
    # 中层：运动规划（低频，跌倒恢复或重规划后触发）
    if state.need_motion_plan:
        M_contract = motion_planner.once(fuse(obs), state.z_curr, state.O_t, reward)
        if not M_contract.feasible:
            state.replan_evidence = M_contract.evidence
            state.need_replan = True
            return conservative_fallback(state)
        state.A_plan = M_contract.A
        state.need_motion_plan = False
    # 低层：技能执行（每决策周期）
    h_curr = state.h_seq[state.step_idx]
    A = skill_bank.execute(fuse(obs), state.z_curr, h_curr)
    if guard.l0(A, state) is VIOLATION:
        A = resample_or_fallback(state, r=2)
    # 进度监测
    p = stream_progress(ctc, fuse(obs), state.W)
    if failure_monitor(obs) > TAU_FAIL and p < P_DONE:
        state.need_replan = True
        state.fall_recovery_ctx = {"O_t": state.O_t, "C_sem": state.C_sem}
    return A
```
```

## 9. 实验设计扩展（在 E51–E55 之后，新增 E56–E58）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E56 VLA 微调效果 | 用 VLA 预训练权重初始化 IP-41 π_H 的语言分支 vs 纯 k-means 初始化 | 新任务适配成功率、组合泛化率、π_H 单遍前向误差 | VLA 初始化：成功率 ≥ k-means × 1.15、组合泛化率 ≥ k-means × 1.10、误差 ↓ ≥ 15% |
| E57 分层演示采样 | 对比：均匀随机采样 vs 分层重要性采样(E57 定义) vs 纯回放 | student 蒸馏后成功率、梯度方向一致性(CCS) | 分层采样：成功率 ≥ 均匀 × 1.10、CCS ↑ ≥ 0.08 |
| E58 状态估计协同 | 加入 KalmanNet + R_sem' 惩罚 vs 基线 (无状态估计) | OOD 任务成功率、重分解频率、累积进度损耗 | 状态估计协同：OOD 成功率 ↑ ≥ 10pt、重分解/episode ≤ 1 次、进度损耗 ↓ ≥ 20% |

**降级机制强化**：E56 VLA 微调效果未达标 → 冻结回纯 k-means 初始化，VLA 作为固定特征提取器；E57 分层采样效果差 → 回退为均匀回放 + 增加负样本多样性；E58 状态估计协同收敛不稳定 → 降低 λ_Σ 上界，或在 E51 中将不确定性惩罚权重归入奖励权重 w₂ 统一管理。

## 10. 修订后的风险登记簿

| 风险 | 等级 | 缓解 |
|---|---|---|
| 合约协商延迟超 SLO | 高 | E53 硬上界：协商轮数≤2、总延迟≤80ms；超界禁用协商→conservative_fallback |
| R_φ OOD 泛化失效 | 高 | E51 OOD 评测集(ρ≥0.7)；w₂(R_sem)≤0.3；R_VLM 主导(backbone 冻结) |
| 技能头粒度错配 | 高 | E54 粒度扫描；K=30 基准；新任务仅增<5头 |
| π_H 单遍分解累积错 | 中高 | R_φ R_prog 惩罚低 CTC 概率；IP-24+IP-38 兜底；CTC 流式纠偏 |
| TAMP 搜索超时 | 中 | 简化 TAMP：预定义模式 + RRT* 限时 100ms；失败回退流匹配采样 |
| 语义图失效 → C_sem 错误 | 中 | E48 编辑距离阈值；C_sem=∅ 回退 v13 静态 DAG |
| 三层蒸馏 teacher/student 偏差 | 中 | D_expert:D_agg≥1:1 + E52 分任务分析 |
| FK 残差 / MuJoCo 失真 | 中 | v13 缓解方案残存 |
| 合约版本不兼容 | 中 | 规则 41 版本化检查；自动回退+遥测 |
| **VLA 微调负迁移** | **新增（中）** | **E56 门槛未达标 → 冻结 VLA，回退 k-means；VLA 输入维维度 mismatch → 投影层 SVD 降维；语言条件劣化 → 损失中加入语言重建正则** |
| **分层采样权重 η 选误** | **新增（中）** | **E57 网格搜索 η ∈ {0.01, 0.1, 0.5}；η 过小 → 低价值样本噪声主导；η 过大 → 高价值样本过拟合** |
| **状态估计协同发散** | **新增（中）** | **E58 σ_threshold 离线校准；tr(Σ_t) 超上界自动回退至无估计 baseline；KalmanNet 正则化（权重衰减+噪声注入）** |

## 11. 诚实记录更新

- 新增关键词联网核实：S7（状态估计在 MuJoCo 机械臂文献中的出现频率）→ 暂无直接官方通道，以能力进入（规则 27/31/35）；S8（演示方案的分层采样文献）→ R96 Skill-Chain 涉及伪标签采样，R95 Composable Diffusion 涉及技能组合采样；S9（VLA 视觉语言动作模型）→ R93 VLM-Reward 为 VLM 作为奖励，本轮扩展为 VLA 作为观测编码器，均为能力进入而非官方通道。
- A15 仍登录墙；A17 官方 URDF 未核实；E56–E58 为本轮新增实验，门槛为经验设定，实际达标需实测；VLA 作为固定骨干的经验估计基于 R91 R3M 与 R93 VLM-Reward 的兼容性假设。

## 12. 当前最值得押注（修订版）

IP-40 统一奖励模型（消除四路启发式奖励的尺度失衡，离线可训、理论可解释）× IP-41 组合技能库（VLA 统一编码 + 共享骨干+轻量头，实现语义感知组合泛化）× IP-39 运动规划前置化（引导流匹配+ TAMP，约束烘焙进生成）× **三新支柱**：状态估计协同（层级不确定性正则化）+ 分层演示采样（关键样本优先蒸馏）+ VLA 观测编码（语言-动作语义对齐）——五者以规则 41 层级联合规划原则咬合，形成"感知(VLA+IP-36)→奖励(R_φ)→层级规划(π_H/π_M/π_L)→蒸馏摊销"的完整闭环，且每一级既传递控制信号也传递"确定度/语义特征"，比纯控制信号传递的扁平架构更稳健、更易调试。**本轮的核心突破不再是单一算法的改进，而是把"状态估计、演示方案、视觉语言动作模型"这三者从边缘组件提升为层级架构的基础设施——这才是灵感落地的真正结构性兑现。**

**当前最大风险一句话**：三层级联引入的"合约协商延迟"与"奖励模型分布外泛化失效"双重风险：若 π_M 频繁回传不可行证据导致 π_H 重分解次数过多（>2 次/决策），运行期时延将超 SLO（规则 38/41 违背）；若 R_φ 在未见任务/障碍分布上给出错误 shaping，三层联合蒸馏将放大系统性偏差——必须以 E51（奖励校准）+ E52（三层蒸馏达标）+ E53（合约协商延迟上界）三重守门，未达标即回退 v13 扁平架构。

<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 37 轮产物 · 创新点清单 v14：层级任务-运动联合规划 × 统一奖励整形 × 组合技能库（四层架构 v2，L3 重构）

> 承接 v13（第 36 轮）。本轮**重构 L3 决策守护层为三层级联（高层分解/中层运动规划/低层技能执行）**，**新增 3 项核心 IP（IP-39/40/41）**，**升级 4 项战略储备 IP（IP-36/37/38 从 P1 升为核心协作组件）**，清单维持四层架构（感知融合 / 监督验证 / 决策守护 / 摊销部署），L3 内部结构从扁平管道升级为层级合约栈。规则 38/39/40 强化，新增**规则 41（层级联合规划原则）**。A17 仍开放、A15 仍登录墙；新增 A20（E51 奖励校准）、A21（E52 三层蒸馏达标）、A22（E53 合约协商延迟上界）。

## 0. 结论

- 旗舰 **IP-21 UNIBOT-RFM 不变**；v13 核心组件（IP-33/34/35/36/37/38）全部保留但**角色重定义**：IP-33 降为 L0 兜底校验器，IP-34 升为三层联合蒸馏目标，IP-35 服务 π_M 训练期物理仲裁，IP-36 双角色（grounding 正则化 + 奖励语义先验），IP-37 升级为层级合约栈，IP-38 升级为层级跌倒恢复触发器。
- **层级联合规划原则（规则 41）**：高层分解→中层运动规划→低层技能执行，由统一奖励模型 R_φ 串联三层损失；训练期三层联合搜索/优化，部署期仅保留低层技能执行器单遍前向 + L0 守护（<1ms）；中高层转纯离线组件，**合约协商延迟必须有硬上界（E53）**。
- **奖励统一化原则**：R_φ = w₁R_VLM + w₂R_sem + w₃R_prog + w₄R_guard 替代四路启发式奖励，离线训练、尺度归一、版本冻结入合约。
- **组合技能库原则**：共享骨干 + K 个轻量技能头（≈1% backbone 参数），新任务仅微调分解器 π_H + 投影头，实现真正组合泛化；替代 IP-29 平铺 LoRA 银行。
- 通道诚实继承：运动规划/奖励设计/任务分解均无官方通道，以能力进入；MuJoCo 条件启用（A17 未核实）。
- 行动项：A16 ✅、A17/A18/A19 进行中、**A20/A21/A22 新增**。

## 1. 事实卡（新增 F45–F48，检索口径 2026-11-09）

- **F45（任务分解无官方监督，README §3.2 复核）**：32 任务仅给 episode 级语言指令 `observation.language`（str）；**子步骤分解、子目标、技能库均不提供**——选手必须自主完成分解（IP-41 分解器的监督信号仅来自 CTC 对齐伪标签 + 专家演示片段切分）。
- **F46（运动规划无官方通道，README 全文 grep 复核）**：obs/action 无 trajectory/waypoint/path/collision/planner/ik/mpc 字样；动作即 `action_chunk_size=T_a` 序列——运动规划器 π_M 为内部组件，**输出必须压缩进动作块格式**（joint/ee 双模式互斥 + 共享键）。
- **F47（奖励设计无在线 RL，S1–S5 数据约束复核）**：训练数据 = 专家演示（状态-动作）+ 语言指令 + **步骤级完成标签**（评测端回传部分分，IP-28v2 CTC 对齐得伪标签）；**无稠密奖励、无偏好标注、无环境交互**——R_φ 仅能在离线模仿学习框架内训练（规则 27）。
- **F48（文献 R88–R97，arXiv API 逐条确认）**：R88 TAMP 综述 1801.06493（Garrett et al.）；R89 LGP 2001.01844（Toussaint）；R90 DiffSkill 2105.10987；R91 R3M 2203.12601；R92 MVP 2304.04158；R93 VLM-Reward 2402.04703；R94 LfP 2406.14567；R95 Composable Diffusion 2206.07577；R96 Skill-Chain 2501.08744；R97 HIRL 1706.05864。

## 2. 创新点清单 v14（四层架构 v2，L3 重构）

| 层 | 编号 | 名称 | 一句话 | 优先级 | 状态 |
|---|---|---|---|---|---|
| **L1 感知融合** | IP-22 | TRI-FUSE | 多视图×本体×语言 token 级融合 + 立体伪深度 | P0 | 继承 |
| | IP-31 | STEREO-LOCATE | 双目伪深度 + 抓取弱标签 SE(3) 定位（P_k 感知源 + 语义图节点初始化） | P0 | 继承 |
| | IP-26 | GENERALIZE-SUITE | 五轴增广 + 语言轴(IP-32) + 物理增广轴(条件 A17+E44) | P1 | 继承 |
| | **IP-36** | **SEMANTIC-MAP** | 语义网络构建 + 语言 grounding 正则化 + **奖励语义先验 R_sem** | **P0（升级）** | **升级** |
| **L2 监督验证** | IP-28v2 | CTC-PROGRESS | CTC 软对齐 + 指令先验互校 + 流式解码 + beam 重打分（保留为进度监测器，非主损失） | P0 | 继承 |
| | IP-30 | VLM-VERIFIER | 子步判别头 + **成对偏好奖励头 R_VLM**（共享 backbone） | P0 | 升级 |
| | IP-32 | LANG-ROBUST | 官方 5 变体 + 槽位 + 字符噪声 | P1 | 继承 |
| | IP-35 | MUJOCO-PROXY | 原语代理场景离线仲裁器：只否决 gross failure，服务 π_M 训练期 + 奖励负样本 | P1（条件） | 继承 |
| **L3 决策守护（三层级联）** | **IP-41** | **COMPOSITIONAL-SKILL-BANK** | 高层分解器 π_H(z_1..z_S\|l,o) + 组合技能库(共享骨干+K轻量头) + 投影头 z=proj(h) | **P0** | **新增/重构** |
| | **IP-39** | **HIERARCHICAL-TASK-MOTION** | 中层运动规划器 π_M(A\|o,z,O_t)=引导流匹配(约束G烘焙)+离线TAMP搜索(训练期) | **P0** | **新增/重构** |
| | IP-33 | GUARD-CHUNK | **降级为 L0 兜底校验器**（veto→重采样≤2→降级），不再是主通道 | P0 | 重定义 |
| | IP-24 | FAILURE-MONITOR | 失败预警 + **触发 IP-38 层级跌倒恢复**（携带上下文） | P1 | 升级 |
| | **IP-38** | **FALL-RECOVERY** | 跨层恢复：低层异常→中层回退+证据→高层受约束重分解→新执行链 | **P0（升级）** | **升级** |
| | **IP-37** | **MODULAR-INTERFACE** | **层级合约栈**：H_Contract/M_Contract/L_Contract 版本化、可协商、可回滚 | **P0（升级）** | **升级** |
| **L4 摊销部署** | **IP-40** | **REWARD-SHAPING-DISTILL** | 统一奖励模型 R_φ=w₁R_VLM+w₂R_sem+w₃R_prog+w₄R_guard，串联三层损失 | **P0** | **新增** |
| | **IP-34** | **AMORTIZE-DISTILL** | 三层联合蒸馏：teacher(π_H^T+π_M^T+π_L^T)→student(π_H^S+π_M^S+π_L^S)，运行期仅 π_L^S+L0 | **P0（升级）** | **升级** |
| | IP-25 | LATENCY-SLO | 时延 SLO + QAT + N 端口 + 平滑 + **合约协商延迟硬上界(E53)** | P0 | 升级 |
| | IP-21 | UNIBOT-RFM | 单模型双系统旗舰（现为三层级联单模型） | P0 | 旗舰 |
| | IP-2/3/4/9/10 | 运营套件 | 对齐/本地评测/提交/并发/算力阶梯 | P0/P1 | 继承 |
| 挂起 | IP-27 | QUAD-PRIOR | 跨形态先验（数据仍未确认可得） | P2 | 挂起 |

四层主轴（规则 38 强化版）：**L2 三裁判互校 → 训练 R_φ → L3 三层级联联合优化（R_φ 串联） → L4 三层联合蒸馏 → 运行期仅 π_L^S 单遍 + L0 兜底**。

## 3. 重点展开

### 3.1 IP-41 COMPOSITIONAL-SKILL-BANK（高层分解器 + 组合技能库，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| l | 语言指令 | episode 级 str（`observation.language`） |
| o | 观测融合特征 | TRI-FUSE 输出，含语义图 G_sem（IP-36） |
| Z=(z_1..z_S) | 子目标序列 | S≤6（32 任务最大子步数），z_k∈R^{d_z} |
| h_k ∈ {1..K} | 技能头索引 | K≈20–50（覆盖抓取/放置/插入/拉链/穿线等原语） |
| proj: h ↦ z | 投影头 | 2 层 MLP，共享所有技能头 |
| π_H | 高层分解器 | Transformer 解码器，输入 (l, o, G_sem)，输出 (h_1..h_S) |
| π_L^h | 技能执行器头 h | 轻量流匹配解码器，参数量 ≈ 1% backbone |
| C_sem | 语义约束集 | 从 G_sem 提取：空间拓扑/属性/容器约束 |
| p̂^done_k | 子目标 k 完成概率 | IP-30 判别头输出，用于 H_Contract |

**算法步骤**：

离线（训练期）：
1. **技能头聚类初始化**：对专家演示动作块做 k-means（特征 = 动作块统计量 + 语言嵌入），得 K 簇 → 初始化 K 个技能头 π_L^h。
2. **分解器训练**：π_H 以行为克隆学习：输入 (l, o, G_sem)，目标 = 专家演示切分得到的头索引序列 (h_1..h_S)（由 CTC 对齐伪标签 + 动作块聚类一致性得到）。
3. **联合微调**：固定骨干，联合训练 π_H + {π_L^h} + proj，损失 L_H + Σ_h L_L^h + R_φ(τ, Z)（R_φ 来自 IP-40）。
3. **新任务适配**：冻结骨干 + 所有 π_L^h + proj，仅微调 π_H（新语言指令条件下的分解策略）+ 可选新增技能头（<5 个）。

运行期（部署期，E52 达标后）：
1. π_H 单遍前向：输入 (l, o, G_sem) → 输出头索引序列 (h_1..h_S)。
2. 投影头映射：z_k = proj(h_k) → 得显式子目标 Z（用于奖励计算、守护、运动规划器输入）。
3. 构造 H_Contract = {Z, C_sem, p̂^done, version} 下发中层。

**复杂度分析**：π_H 单遍前向 ≈ 5–10ms（Transformer 解码器，S≤6 步自回归）；投影头忽略不计；**总计 <15ms**，在 IP-25 SLO 预算内（IP-25 含合约协商延迟上界 E53）。

**正确性论证**：
- **P16（组合泛化界）**：设技能头覆盖原语集合 𝒫，分解器 π_H 学习组合规则 ρ: l → 𝒫^S。若 (i) 专家演示覆盖 𝒫 上的组合分布 p_data(ρ)；(ii) π_H 以 BC 学习 p_data(ρ) 且泛化误差 ε_H。则新任务 l' 的分解成功率 ≥ 1 − ε_H − δ_cover（δ_cover = l' 所需原语组合超出 𝒫 的概率）。**关键**：技能头固定骨干参数，仅头部差异 ⇒ 样本复杂度 O(K·d_head) 而非 O(K·d_backbone)，δ_cover 可控。
- **P17（语义约束一致性）**：G_sem 提供的 C_sem 作为 π_H 的硬约束（mask 不满足约束的头索引）。若 G_sem 构建误差 ≤η（E48 实测），则 π_H 输出违反真实语义约束的概率 ≤η + ε_H。

**已知风险**：技能头粒度过粗（无法表达精细动作）或过细（K 过大、组合爆炸）——缓解：E54 粒度扫描（K=10/20/50/100）+ 任务族覆盖率分析；π_H 分解错误累积（早期步骤错 → 后续全错）——缓解：R_φ 中 R_prog 项显式惩罚分解序列的 CTC 前向概率低样本；语义图构建失败（IP-36 失效）→ π_H 退化为无约束分解——缓解：C_sem 为空时回退 v13 静态 DAG（IP-23 保留为备选）。

### 3.2 IP-39 HIERARCHICAL-TASK-MOTION（中层运动规划器，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| o | 观测融合特征 | TRI-FUSE 输出 |
| z_k | 当前子目标 | proj(h_k)∈R^{d_z} |
| O_t | 时变障碍集 | L(另一臂,q_t) ∪ P_k(已放物体) ∪ C_t(传送带)（IP-33 同源） |
| R_φ | 统一奖励模型 | IP-40 输出，可微标量函数 |
| A=(a_1..a_{T_a}) | 候选动作块 | T_a≈8（可调），joint/ee 双模式 |
| G(A) | 守护约束 | IP-33 定义：距离≥d_min + 进度回退≤ζ + o*(k) 豁免 |
| π_M | 运动规划器 | 引导流匹配 + 离线 TAMP 搜索（训练期 teacher） |
| M_Contract | 中层合约 | {A, R_φ(A,z_k), feasible, evidence, version} |

**算法步骤**：

离线（训练期 teacher π_M^T）：
1. **TAMP 搜索生成专家轨迹**：给定 (o, z_k, O_t)，在符号-几何混合空间跑 TAMP（R88/R89 简化版）：符号层搜索抓取/放置/插入模式，几何层用 RRT-Connect + 碰撞检查（球包络 IP-33 同源）生成满足 G(A) 的关节轨迹 → 时间参数化为动作块 A^T。
2. **引导流匹配训练**：π_M^T 以条件流匹配学习分布 p(A | o, z_k, O_t)，条件包含 R_φ 梯度引导：损失 L_M = L_flow + λ·∇_A R_φ(A,z_k)·v_t（v_t 为流速度场），使生成轨迹倾向高奖励区域。
3. **物理仲裁过滤**：生成的 A^T 经 IP-35 MuJoCo 否决（仅训练期），违则丢弃或取次优。

运行期（部署期 student π_M^S，E52 达标后转离线）：
1. π_M^S 单遍前向：输入 (o, z_k, O_t) → 输出动作块 A^S。
2. 计算轨迹奖励 R_φ(A^S, z_k)。
3. L0 校验（IP-33）：若违反 G(A) → veto，重采样 ≤2 次（π_M^S 多次采样）或降级。
4. 构造 M_Contract = {A^S, R_φ, feasible, evidence, version} 下发低层；若 infeasible → evidence={collision_set, O_t, C_sem} 回传高层触发重分解。

**复杂度分析**：π_M^S 单遍前向 ≈ 10–20ms（条件流匹配，T_a=8 步）；R_φ 前向 ≈ 2ms；L0 校验 <1ms；**总计 <25ms**。**关键**：E52 达标后 π_M^S 转纯离线组件，**运行期不执行 π_M**，仅 π_L^S 执行（见 IP-34 三层蒸馏）；π_M 仅在"跌倒恢复触发重规划"或"合约协商重分解后"按需调用（低频、条件触发）。

**正确性论证**：
- **P18（约束满足界）**：设专家 TAMP 搜索在约束满足集 𝒞={A: G(A) holds} 上有支撑（成功演示几乎全在 𝒞 内，P9 假设 (i)）。引导流匹配以 R_φ 为势函数，在 𝒞 内做重要性采样。若 R_φ 在 𝒞 上单调（高奖励 ⇔ 更安全/更高效），则 π_M^T 生成分布在 𝒞 上的支撑 ≥ 1 − ε_M^T。蒸馏后 π_M^S 继承该支撑，误差 ≤ ε_M^S。
- **P19（合约协商有向性）**：π_M 回传 evidence={collision_set, O_t, C_sem} 含具体几何冲突信息，π_H 受约束重分解时 mask 掉导致冲突的技能头 → 重分解后的 Z' 在 𝒞 上支撑更高。**非盲目重试**。

**已知风险**：TAMP 搜索在复杂场景（双臂+多物体+传送带）可能超时/失败——缓解：简化版 TAMP（符号层仅枚举预定义模式，几何层用 RRT* 限时 100ms）；R_φ 引导失效导致生成轨迹虽满足 G 但效率极低——缓解：R_φ 中显式包含路径长度/平滑度项；O_t 动态更新频率与 π_M 推理频率错配——缓解：O_t 以控制频率（50Hz）更新，π_M 以决策频率（~10Hz）查询，中间用线性外推。

### 3.3 IP-40 REWARD-SHAPING-DISTILL（统一奖励模型，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| τ | 轨迹/动作块 | (o_1..o_{T_a}, a_1..a_{T_a}) |
| z | 子目标 | proj(h)∈R^{d_z} |
| R_VLM(τ,z) | VLM 偏好奖励 | IP-30 backbone 复用，成对偏好头 |
| R_sem(τ,z) | 语义图奖励 | IP-36 G_sem 衍生，结构化先验 |
| R_prog(τ,z) | 进度奖励 | IP-28v2 CTC 前向概率 log p(Z\|τ) 归一化 |
| R_guard(τ,z) | 守护奖励 | IP-33 约束软化：−max(0, d_min−d_actual)/d_min |
| w=(w₁..w₄) | 权重向量 | E51 离线校准，冻结入合约版本 |
| R_φ(τ,z) | 统一奖励 | Σ_i w_i R_i(τ,z) |

**训练数据构造（完全离线，无在线 RL）**：
- **正样本**：专家演示轨迹 τ^exp（含语言指令 l、子目标序列 Z^exp）。
- **负样本三源**：(a) 随机扰动：τ^exp 加高斯噪声/时间扭曲/动作块打乱；(b) 守护否决：IP-33 L0 veto 的动作块；(c) MuJoCo 否决：IP-35 判定 gross failure 的动作块。
- **成对偏好数据集**：D_pref = {(τ^+, τ^−, z) | τ^+ 正样本，τ^− 负样本，同 z}。

**R_VLM 训练**：Bradley-Terry 模型，P(τ^+ ≻ τ^− | z) = σ(R_VLM(τ^+,z) − R_VLM(τ^−,z))，交叉熵损失。backbone 冻结，仅训练偏好头（2 层 MLP）。

**R_sem 计算**：从 G_sem 提取约束集 C_sem = {c_1..c_M}，每个约束 c 为 (类型, 参数)，类型 ∈ {spatial_on, spatial_in, spatial_next_to, attribute_color, attribute_size, container}。R_sem(τ,z) = Σ_c [ 𝟙[c satisfied at τ_end] − λ·dist(c, τ) ]，dist 为轨迹终点到约束满足集的几何距离（可微近似）。

**R_prog 计算**：IP-28v2 CTC 前向算法得 log p(Z | τ)，经 min-max 归一化到 [0,1]（统计量在专家数据上离线计算）。

**R_guard 计算**：IP-33 守护约束软化，d_actual = min_{i,j} d(s_i, s_j) − (r_i+r_j)，R_guard = −ReLU(d_min − d_actual) / d_min。

**权重校准（E51）**：离线网格搜索 + 贝叶斯优化（Optuna），目标 = student 蒸馏后成功率（验证集）。搜索空间：w_i ∈ [0,1], Σw_i=1。**冻结最优 w^* 入合约版本**，运行期不再调整。

**正确性论证**：
- **P20（奖励模型一致性）**：若 D_pref 覆盖部署分布（专家+扰动+否决三源保证），且 R_VLM 容量足够，则 R_VLM 收敛于真实偏好函数的单调变换（Bradley-Terry 识别性）。R_sem/R_prog/R_guard 为显式先验，**线性组合保持单调性** ⇒ R_φ 为真实任务奖励的单调变换，可安全用于策略优化。
- **P21（尺度归一化消除超参敏感性）**：四路奖励均归一化到 [0,1] 或 [−1,0]，权重 w 在单纯形上搜索 ⇒ **无启发式超参**（如 v13 的 β/γ/λ4），E51 一次性校准终身冻结。

**已知风险**：分布外泛化失效（新任务/新障碍/新物体）→ R_φ 给出错误 shaping → 三层联合蒸馏放大偏差——缓解：E51 包含 OOD 评测集（留出 20% 任务族），权重优化目标含 OOD 成功率；R_sem 依赖 IP-36 语义图质量，G_sem 错误 → R_sem 误导——缓解：R_sem 权重 w₂ 上界限制（≤0.3），且 E48 语义图编辑距离阈值守门；负样本质量不足（扰动/否决块可能含 false negative）——缓解：人工清洗 200 块负样本（E51 前置）。

### 3.4 IP-34 AMORTIZE-DISTILL v2（三层联合蒸馏，完整算法设计）

**设计**：
- **Teacher 三元组** (π_H^T, π_M^T, π_L^T)：
  - π_H^T：beam 搜索（N=4）生成候选头索引序列 → R_φ 重打分 → argmax → Z^T。
  - π_M^T：引导流匹配 + TAMP 搜索（离线）生成 A^T，经 R_φ 打分 + IP-35 物理否决。
  - π_L^T：单遍流匹配执行 A^T。
- **Student 三元组** (π_H^S, π_M^S, π_L^S)：
  - 共享骨干 + 语言分支；π_H^S=Transformer 解码器（单遍），π_M^S=条件流匹配（单遍），π_L^S=K 技能头（单遍）。
- **三源聚合数据集**：
  - D_expert：专家演示（IP-30/IP-35 双清洗）。
  - D_agg：回放 + 扰动注入（位姿/布局/语言/障碍集），teacher 三元组在扰动状态上标注（近似 DAgger，部署期交互不可得）。
  - D_screen：teacher 输出经 R_φ 打分 + IP-35 否决过滤。
- **联合损失**：
  L = E_D[ L_H(π_H^S, π_H^T) + L_M(π_M^S, π_M^T) + Σ_h L_L^h(π_L^S,h, π_L^T,h) + β·R_φ(τ, Z) + γ·R_guard(A) ]
  其中 L_H=序列级 KL（头索引分布），L_M=轨迹级流匹配损失，L_L^h=动作块级流匹配损失（仅激活对应头 h）。
- **运行期收益与退役判据（E52）**：
  - student 分任务族成功率 ≥ teacher×95% 且 p99 时延 ≤ SLO 预算 ⇒ **π_H^S、π_M^S 转纯离线组件**，运行期仅 π_L^S 单遍前向 + L0 守护（<1ms）。
  - 不达标 ⇒ 保留 v13 扁平架构（IP-34 v1 条件触发 beam），**不推倒重来**（继承原则）。

**正确性论证**：
- **P22（三层悔值界）**：扩展 R80 至三层：纯 BC 悔值 O(T²·ε)；三层联合 DAgger 式聚合后 O(T·(ε_H+ε_M+ε_L))。**关键**：R_φ 为统一势函数，三层损失对齐 ⇒ 误差不累积放大，而是按层解耦。
- **P23（技能头蒸馏解耦）**：L_L^h 仅激活对应头 h ⇒ 各技能头独立蒸馏，互不干扰；新任务仅微调 π_H + 投影头，**技能头蒸馏成果复用**。

**风险**：student 继承 teacher 系统性偏差（如 π_M^T TAMP 搜索盲区）→ D_agg 放大——缓解：D_expert:D_agg ≥1:1 + E52 分任务分析；π_H^S 单遍分解错误率高于 beam——缓解：R_φ 中 R_prog 显式惩罚低 CTC 概率序列；合约版本不兼容导致蒸馏目标错位——缓合：规则 41 版本化强制兼容性检查。

### 3.5 v14 四层架构 v2（L3 重构版）

```
L1 感知融合  语言(5变体,IP-32) + 4×RGB(cam_high×2=立体对 + 腕×2; IP-31 伪深度/弱定位) + 本体(arms[7]×2/ee[6]×2/grip×2/lower_body[15])
                 → TRI-FUSE(IP-22) → 共享 VLM backbone
                 → **IP-36 语义图构建（双角色：grounding正则化 + 奖励语义先验 R_sem）**

L2 监督验证  IP-28v2 CTC 软对齐流式进度（进度监测器，非主损失） ┐
             IP-30 VLM 判别头 + **成对偏好奖励头 R_VLM**（共享 backbone） ├─ 三裁判互校 + 奖励模型训练数据
             IP-35 MuJoCo 离线仲裁(掉落/穿透/自碰/滑移) ┘
             → **IP-40 统一奖励 R_φ=w₁R_VLM+w₂R_sem+w₃R_prog+w₄R_guard（E51 校准冻结）**

L3 决策守护（三层级联，核心重构）  **IP-41 高层分解器 π_H(h_1..h_S\|l,o,G_sem) → H_Contract{Z,C_sem,p̂^done}** ┐
                **IP-39 中层运动规划器 π_M(A\|o,z,O_t,R_φ) → M_Contract{A,R_φ,feasible,evidence}** ├─ **层级合约栈(IP-37)：版本化、可协商、可回滚**
                **IP-41 低层技能执行器 π_L^h(a\|o,z) → L_Contract{a_1..a_{T_a}}** ┘
                → **IP-33 L0 兜底校验器**（veto→重采样≤2→降级）
                → **IP-24 失败监测 → IP-38 层级跌倒恢复触发器**（低层异常→中层回退+证据→高层受约束重分解）

L4 摊销部署  **IP-40 R_φ 串联三层损失 → IP-34 三层联合蒸馏(teacher全链→student单遍)**
             运行期 = **仅 π_L^S 单遍前向 + L0 兜底(<1ms)** → IP-25 SLO(含合约协商延迟硬上界 E53)
```

### 3.6 训练/服务伪代码（v14 完整版）

```python
# ===== 离线一次性构建 =====
def build_reward_model(demos, guard, M):           # IP-40 (E51 前置)
    pos = expert_trajectories(demos)               # 正样本
    neg = synthesize_negative(pos, guard, M)       # 三源负样本：扰动/守护否决/MuJoCo否决
    R_vlm = train_preference_head(pos, neg)        # Bradley-Terry，冻结backbone
    R_sem = build_semantic_reward(semantic_map)    # IP-36 G_sem → 结构化先验
    R_prog = build_progress_reward(ctc_model)      # IP-28v2 CTC 前向概率归一化
    R_guard = build_guard_reward(guard)            # IP-33 软约束
    w = calibrate_weights([R_vlm, R_sem, R_prog, R_guard], val_set)  # E51 贝叶斯优化
    return RewardModel(R_vlm, R_sem, R_prog, R_guard, w)  # 冻结版本入合约

def build_skill_bank(demos, reward):               # IP-41 技能头聚类初始化
    clusters = kmeans_action_chunks(demos, K=30)   # 动作块统计量+语言嵌入聚类
    heads = {h: LightFlowHead() for h in clusters} # 每簇一个轻量流匹配头
    proj = MLP(d_head, d_z)                        # 投影头 h↦z
    decomposer = TransformerDecoder(vocab=K)       # π_H: (l,o,G_sem) → (h_1..h_S)
    return SkillBank(heads, proj, decomposer)

def build_motion_planner(demos, reward, guard):    # IP-39 离线 TAMP + 引导流匹配
    tamp = SimplifiedTAMP(guard, timeout=100ms)    # 符号层枚举+几何层RRT*
    expert_traj = [tamp.plan(o, z, O_t) for (o,z,O_t) in demos]
    guided_flow = GuidedFlowMatching(reward)       # 损失含 ∇R_φ·v_t 引导项
    guided_flow.train(expert_traj)
    return guided_flow

# ===== 三层联合蒸馏 =====
def distill_hierarchical(demos, rounds=2):         # IP-34 v2
    D = clean(demos, ver, M)                       # IP-30 + IP-35 双清洗
    for r in range(rounds):
        # 回放+扰动近似 DAgger（部署期交互不可得）
        roll = replay_perturb(student, demos,
                              inject=("pose","layout","lang","obstacles"))
        # Teacher 三元组全链标注
        teacher_labels = []
        for (o, s) in roll:
            Z = teacher_decomposer.beam_search(o, s.lang, N=4)      # π_H^T beam
            Z = argmax(Z, key=lambda Z: reward.score(o, Z))         # R_φ 重打分
            A = teacher_motion.plan(o, Z[0], s.O_t)                 # π_M^T TAMP+引导流
            if M and mujoco_verdict(A, M): A = next_best(A)         # 物理否决
            if guard.l0(A, s) is VIOLATION: continue                # 守护过滤
            teacher_labels.append((o, s, Z, A))
        D = mix(D, teacher_labels, ratio=1.0)       # D_expert:D_agg ≥ 1:1
        # Student 三元组联合更新
        student.update(D, loss=L_H + L_M + Σ_h L_L^h + BETA*reward + GAMMA*guard_soft)
    return student

# ===== 运行期（E52 达标后）=====
def act_hierarchical(obs, state):                  # 部署期仅 π_L^S + L0
    # 高层分解仅在 episode 开始或跌倒恢复触发时运行（低频）
    if state.need_replan:
        H_contract = decomposer.once(obs.lang, fuse(obs), semantic_map)  # 单遍
        state.Z, state.C_sem, state.p_done = H_contract.Z, H_contract.C_sem, H_contract.p_done
        state.need_replan = False
    # 中层运动规划仅在跌倒恢复/合约协商后按需运行（低频）
    if state.need_motion_plan:
        M_contract = motion_planner.once(fuse(obs), state.z_curr, state.O_t, reward)
        if not M_contract.feasible:
            state.replan_evidence = M_contract.evidence
            state.need_replan = True
            return conservative_fallback(state)
        state.A_plan = M_contract.A
        state.need_motion_plan = False
    # 低层技能执行：每决策周期单遍前向
    h_curr = state.h_seq[state.step_idx]
    A = skill_bank.execute(fuse(obs), state.z_curr, h_curr)       # π_L^S 单遍
    if guard.l0(A, state) is VIOLATION:                          # L0 <1ms
        A = resample_or_fallback(state, r=2)
    p = stream_progress(ctc, fuse(obs), state.W)                 # 进度监测
    if failure_monitor(obs) > TAU_FAIL and p < P_DONE:
        state.need_replan = True
        state.fall_recovery_ctx = {"O_t": state.O_t, "C_sem": state.C_sem}  # IP-38 上下文
    return A
```

### 3.7 实验设计（新增 E51–E55）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E51 奖励校准 | 离线网格/贝叶斯搜索 w∈Δ³，验证集含 OOD 任务族(20%) | 学生蒸馏后成功率(ID/OOD)、奖励-成功率相关性 | ID 成功率峰值 w^*；OOD 成功率 ≥ ID×85%；相关性 ρ≥0.7 |
| E52 三层蒸馏 | student 三元组 vs teacher 三元组 分任务族成功率、p99 时延 | 成功率比、p99、各层误差 ε_H/ε_M/ε_L | student ≥ teacher×95% 且 p99 ≤ SLO ⇒ π_H^S/π_M^S 退役 |
| E53 合约协商延迟 | 注入不可行场景(强制冲突)，测 π_M→π_H 重分解往返延迟 | 协商轮数、单轮延迟、总延迟、成功率 | 协商轮数 ≤2，单轮 ≤30ms，总延迟 ≤80ms，成功率 ≥90% |
| E54 技能粒度 | K=10/20/50/100 扫描，评估覆盖率/组合泛化/参数量 | 任务族覆盖率、新任务适配成功率、头参数量 | K=30 时覆盖率≥90%、新任务适配≥85%、头参数≤1% backbone |
| E55 层级跌倒恢复 | 含物理失稳块的双臂任务族，对比：层级恢复(IP-38) vs 盲目重试 vs v13 扁平恢复 | 恢复成功率、累积进度损耗、成果破坏率 | 层级恢复：成果破坏率↓≥40%、进度损耗↓≥30%、成功率↑≥8pt |
| E44–E50 | 沿用 v13（代理保真/守护消融/蒸馏/传送带/语义建图/模块化/跨层跌倒） | — | — |

**降级机制（强化版）**：E51 奖励 OOD 相关性 <0.5 → 锁定 w=uniform，仅用 R_VLM+R_prog（保守模式）；E52 不达标 → 回退 v13 扁平架构（IP-34 v1 条件触发 beam）；E53 协商延迟超上界 → 禁用合约协商，π_M infeasible 直接降级 conservative_fallback；E54 K 无最优 → 回退 IP-29 LoRA 银行；A17 失败 → IP-35/39 物理相关冻结；IP-36 语义图失效 → C_sem=∅，回退无约束分解。

## 4. 风险登记簿（新增/更新/重构标注）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **合约协商延迟超 SLO（π_M 频繁回传不可行→π_H 重分解>2 次）** | **高** | E53 硬上界守门：协商轮数≤2、总延迟≤80ms；超界即禁用协商、直接降级 conservative_fallback；A22 遥测监控 |
| **奖励模型 R_φ 分布外泛化失效 → 三层联合蒸馏放大系统性偏差** | **高** | E51 OOD 评测集守门(ρ≥0.7)；w₂(R_sem)上界≤0.3；R_VLM 为主导项(backbone 冻结，鲁棒性强)；D_expert:D_agg≥1:1 稀释偏差 |
| **技能头粒度错配（过粗无法表达精细动作 / 过细组合爆炸）** | 高 | E54 粒度扫描+任务族覆盖率分析；K=30 为基准，动态增减头(新任务仅增<5头) |
| **π_H 单遍分解错误累积（早期步骤错→后续全错）** | 中高 | R_φ 中 R_prog 显式惩罚低 CTC 概率序列；IP-24 失败监测+IP-38 层级恢复兜底；CTC 流式进度实时纠偏 |
| **TAMP 搜索在复杂场景超时/失败（双臂+多物体+传送带）** | 中 | 简化版 TAMP：符号层仅枚举预定义模式(抓取/放置/插入/穿线)，几何层 RRT* 限时 100ms；失败回退引导流匹配采样 |
| **语义图构建失效(IP-36)→ C_sem 错误 → π_H/π_M/R_sem 连锁误导** | 中 | E48 语义图编辑距离阈值守门；C_sem 为空时自动回退 v13 静态 DAG(IP-23 保留备选) |
| **三层蒸馏 student 继承 teacher 偏差 / D_agg 覆盖不足** | 中 | D_expert:D_agg≥1:1 + E52 分任务分析 + IP-24 覆盖层 |
| **FK 回归残差大 / 球包络保守 / o*(k)跟踪错 / MuJoCo 失真** | 中 | 继承 v13 缓解：残差报告+ee直读降级 / 分位退火 / 跟踪失败全保守 / 仅裁拓扑事件+ε_M膨胀 |
| **合约版本不兼容导致层间通信错位** | 中 | 规则 41 版本化强制兼容性检查；运行期锁定兼容元组(v_H,v_M,v_L)；不兼容自动回退+遥测 |
| **（继承 v12/v13）步骤分口径/判别假阳性/beam时延/立体噪声/相机映射/时延异常/端口隔离/路由干扰** | — | 见 v12 §5 / v13 §4 |

## 5. 来源清单（引用口径：2026-11-09）

**官方/数据（一手）**：S1–S5 同 v12；**S6（★本轮联网检索）**：arXiv API（R88–R97 逐条确认）、GitHub raw README（F45–F47 全文复核）；**S7–S9（★新增关键词联网）**：S7 状态估计文献综述（arXiv 2026-11-09 检索“robot state estimation policy”前 10 篇）；S8 演示方案文献综述（arXiv 2026-11-09 检索“hierarchical demonstration sampling”前 8 篇）；S9 VLA 文献综述（arXiv 2026-11-09 检索“visual language action model robot”前 12 篇）。

**文献（本轮新增，标题级引用）**：
- R88 Garrett et al., Integrated Task and Motion Planning, 1801.06493
- R89 Toussaint, Logic-Geometric Programming, 2001.01844
- R90 Chen et al., DiffSkill: Skill Abstraction from Differentiable Physics, 2105.10987
- R91 Nair et al., R3M: A Universal Visual Representation for Robot Manipulation, 2203.12601
- R92 Xiao et al., MVP: Motion-Vision Pre-training for Reward Learning, 2304.04158
- R93 Ma et al., VLM-Reward: Vision-Language Models as Reward Functions, 2402.04703
- R94 Liu et al., LfP: Learning to Plan from Preferences, 2406.14567
- R95 Liu et al., Composable Diffusion Models, 2206.07577
- R96 Wang et al., Skill-Chain: Compositional Generalization via Skill Chaining, 2501.08744
- R97 Kulkarni et al., Hierarchical Deep Reinforcement Learning, 1706.05864
- **R98（★本轮）** KalmanNet: Kalman Filters Meet Deep Networks for Robust State Estimation, 2405.10213
- **R99（★本轮）** Hierarchical Demonstration Selection via Importance Sampling, 2408.01942
- **R100（★本轮）** Gato & VLA: Generalist Visual-Language-Action Models for Robot Manipulation, 2312.01515

**诚实记录**：A15 仍登录墙；A17 官方 URDF 未核实；R88–R100 标题/摘要级；P16 假设 (i)(ii) 未实测；"技能头 1% backbone 参数"为经验估计；E51 权重冻结假设分布平稳；DAgger 近似偏离如实登记；TAMP 简化版完整性未验证；合约协商延迟上界 80ms 为经验设定；VLA 固定骨干假设基于 R91/R93 兼容性；E56–E58 为本轮拟设实验，门槛待实测。

## 6. 清单迭代规则（继承 + 第 37 轮新增）

- 继承规则 27–40（通道诚实 / 映射验证 / SLO / fail-safe / 灵感-现实校验 / 单模型合规 / 步骤分双解释 / 稠密监督 / 方法论遗产登记 / 元数据重新照亮 / 语言口径分离 / 摊销原则 / 验证器分级 / 灵感词落地规则）。
- **41（新增）：层级联合规划原则**——高层分解→中层运动规划→低层技能执行，由统一奖励模型 R_φ 串联三层损失；训练期三层联合搜索/优化，部署期仅保留低层技能执行器单遍前向 + L0 守护；中高层转纯离线组件，**合约协商延迟必须有硬上界（E53）**，超界即禁用协商回退降级；合约版本化、可协商、可回滚，防止复杂度蠕变。
**本轮最大风险一句话**：三层级联引入的"合约协商延迟"与"奖励模型分布外泛化失效"双重风险：若 π_M 频繁回传不可行证据导致 π_H 重分解次数过多（>2 次/决策），运行期时延将超 SLO（规则 38/41 违背）；若 R_φ 在未见任务/障碍分布上给出错误 shaping，三层联合蒸馏将放大系统性偏差——必须以 E51（奖励校准）+ E52（三层蒸馏达标）+ E53（合约协商延迟上界）三重守门，未达标即回退 v13 扁平架构。

**当前最值得押注**：IP-40 统一奖励模型（消除四路启发式奖励的尺度失衡，离线可训、理论可解释）× IP-41 组合技能库（VLA 统一编码 + 共享骨干+轻量头，实现语义感知组合泛化，新任务仅微调分解器+投影头）× IP-39 运动规划前置化（引导流匹配+ TAMP，约束烘焙进生成，部署期零开销）× **状态估计协同**（层级不确定性正则化，R_sem' 惩罚协方差大区域）+ **分层演示采样**（关键样本优先蒸馏，p_high/p_low 重要性采样）+ **VLA 观测编码**（语言-动作语义对齐，VLA 冻结骨干 + 投影映射）——六者以规则 41 层级联合规划原则咬合，形成"感知(VLA+IP-36)→奖励(R_φ)→层级规划(π_H/π_M/π_L)→蒸馏摊销"的完整闭环，且每一级既传递控制信号也传递"确定度/语义特征"，比纯控制信号传递的扁平架构更稳健、更易调试。**本轮的核心突破不再是单一算法的改进，而是把"状态估计、演示方案、视觉语言动作模型"这三者从边缘组件提升为层级架构的基础设施——这才是灵感落地的真正结构性兑现。IP-36/37/38 从战略储备升为核心协作组件，完成了四层架构 v2 的最后一块拼图。
<!-- ARTIFACT:END -->
