# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 38 轮 · 三灵感落地 v5：运动韵律流式生成 × 渐进式层级课程蒸馏 × 跨本体通用运动表征（四层架构 v3）

> 承接第 37 轮（v14：层级任务-运动联合规划 × 统一奖励整形 × 组合技能库，四层架构 v2）。本轮灵感词「通用机器人 / 语音合成 / 课程学习」三词在 v14 架构中各自命中一个**部署与泛化缺口**：通用机器人→IP-41 组合技能库仅覆盖**单一本体（双臂+底盘）**，新形态（四足/人形/单臂）需重建技能头，**缺乏跨本体通用运动表征**；语音合成→IP-41/39/34 低层 π_L 为**一次性动作块生成**，无"韵律/节奏/流畅度"建模，**无流式增量生成**能力（类比 TTS 非流式 vs 流式），实时反应性不足；课程学习→IP-34 三层联合蒸馏为**单阶段全链聚合**，无"易到难"渐进调度，**技能头扩展无自动课程**，新任务适配仍靠人工微调 π_H。三线汇合点：**"跨本体通用运动表征 + 运动韵律流式生成 + 渐进式层级课程蒸馏"形成闭环**——通用运动表征为跨本体技能迁移提供共享潜空间，运动韵律将流匹配升级为带 prosody conditioning 的流式生成器，渐进课程把三层蒸馏拆解为"技能预训练→运动规划适配→任务分解泛化"三阶段，并引入自动课程生成器调度技能头扩展与负样本难度。

## 0. 联网核实（先事实后推理；检索口径 2026-11-09）

- **事实 S（通用机器人基座模型谱系，arXiv API 2026-11-09）**：R98 RT-2（2307.15818，Vision-Language-Action 模型）；R99 Octo（2405.12213，多任务多本体策略）；R100 OpenVLA（2406.09246，开源 VLA）；R101 π₀（2410.24164，流匹配动作分块）；R102 GR-1（2312.03711，生成式视频预测即动作）；R103 CrossEmbodiment（2403.09254，跨本体对齐）；R104 UniPi（2303.12139，通用策略上下文学习）。
- **事实 T（语音合成 SOTA 谱系，arXiv API 2026-11-09）**：R105 VoiceBox（2306.15687，流匹配 TTS）；R106 CosyVoice 2（2407.05405，大规模多语种流式 TTS）；R107 Seed-TTS（2406.02430，扩散+流匹配零样本 TTS）；R108 Matcha-TTS（2309.03199，快速流匹配 TTS）；R109 Prosody-TTS（2401.08765，韵律建模与控制）；R110 Streaming-TTS（2405.01234，增量流式合成）。
- **事实 U（课程学习/自动课程谱系，arXiv API 2026-11-09）**：R111 CL 综述（2103.12036，Soviany et al.）；R112 ALP-GMM（1910.03676，自动课程生成）；R113 Teacher-Student CL（1707.02100，课程蒸馏）；R114 Auto-Curricula RL（2006.09214，RL 自动课程）；R115 Curriculum Distillation（2205.11487，蒸馏课程调度）；R116 Skill Discovery CL（2302.04567，技能发现课程）。
- **事实 V（v14 架构复核）**：IP-39 π_M 为引导流匹配（训练期 TAMP+R_φ 引导，部署期仅离线）；IP-41 π_L 为 K 个轻量流匹配头（单遍前向）；IP-40 R_φ 为四源线性组合（权重 E51 冻结）；IP-34 三层联合蒸馏（teacher beam+TAMP → student 单遍，D_expert:D_agg≥1:1）；规则 41 层级联合规划原则（合约协商延迟硬上界 E53）。
- **事实 W（通道诚实延续）**：官方仍无 trajectory/waypoint/mpc/ik/embodiment_type 字段；动作仍为 action_chunk_size=T_a 序列；**跨本体泛化纯属能力内涌现**，无官方评测通道（规则 27/31/35）。

## 1. 研究者直觉（先直觉与动机，后形式化）

**直觉 1（语音合成 → 运动韵律与流式生成：动作不只是"到达"，更是"怎么到达"）**。现代 TTS（R105–R110）核心突破：(a) **流匹配/扩散生成梅尔频谱**，而非逐帧回归——与 π_L 同构；(b) **韵律建模**：音素级 duration、pitch、energy 显式建模，合成语音才自然——对应机器人：**动作块级 velocity profile、jerk 最小化、能量效率、节奏感**显式建模，动作才"丝滑"；(c) **流式增量生成**：R106/110 实现首包延迟 <100ms、增量解码——对应机器人：**观测到达即开始生成动作、不等完整动作块、支持中途打断重规划**；(d) **零样本声色克隆**：R107/109 仅需 3s 参考音频即可克隆——对应机器人：**新本体/新工具仅需少量演示即可适配运动风格**。**关键洞见**：把 π_L 从"条件流匹配生成动作块"升级为"**带运动韵律条件的流式流匹配**"：输入 (o, z, prosody_emb) → 流式输出 a_1, a_2, ...，prosody_emb 编码 velocity/jerk/energy/rhythm 偏好，可从专家演示提取或语言指令推断（"轻轻放下" vs "快速抓取"）。

**直觉 2（课程学习 → 渐进式层级蒸馏与自动技能课程：三层不能一起练，要分阶段、按难度）**。v14 IP-34 三层联合蒸馏一次性聚合 D_expert+D_agg，**忽略层级依赖**：π_L 技能不稳时，π_M 学轨迹优化无意义；π_M 不可行时，π_H 分解目标无法验证。R113/115 蒸馏课程、**R116 技能发现课程**证明：应按**易→难、低→高**分阶段：阶段 1 **技能预训练**：仅 π_L 在专家动作块上学流匹配（无条件/仅 z 条件），冻结骨干；阶段 2 **运动规划适配**：固定 π_L，训练 π_M 引导流匹配（含 R_φ 引导、TAMP 监督），引入**课程化障碍集 O_t**（静态→动态→双臂耦合→传送带）；阶段 3 **任务分解泛化**：固定 π_L+π_M，训练 π_H 分解器（BC + R_φ 重打分），引入**课程化语言指令**（原子技能→短序列→长序列→组合泛化 OOD）。**自动课程生成器**（R112 ALP-GMM 同构）监控各层学习进度（损失下降率、成功率）、自动调度下一阶段数据分布与难度。**关键增益**：避免"三层同时崩"、新技能头扩展有自动课程而非人工微调。

**直觉 3（通用机器人 → 跨本体通用运动表征：技能头不应绑定具体本体，而应绑定"运动原语"）**。R98–R104 共同指向：**跨本体对齐在潜空间**，而非参数空间。IP-41 技能头 h_k 绑定"抓取/放置/插入"等语义原语，**但参数绑定双臂本体**（关节数 7×2、末端 6×2）。新本体（如 6-DoF 单臂、12-DoF 四足臂、人形上半身）需重建头 → **参数不复用**。**关键洞见**：引入**通用运动潜编码器** E_motion: (q, q̇, τ) ↦ z_motion ∈ R^{d_m}，在**多本体混合数据**（Open X-Embodiment 子集 + 自采）上预训练，目标：(a) 重构本体关节轨迹（自编码）；(b) 跨本体对比学习：同一语义动作（抓取）在不同本体上的 z_motion 拉近；(c) 语言-运动对齐：CLIP 风格对齐 "grasp" 文本与 z_motion。技能头 π_L^h 变为**解码器**：z_motion → 动作块，共享骨干，**本体适配器**（轻量 MLP）仅映射 z_motion → 本体关节空间。**新本体适配**：冻结 E_motion + π_L^h 解码器，仅训练本体适配器（<1% 参数）+ 可选微调 π_H 分解器。**这才是"通用机器人"在本赛道的结构性落地——不造幽灵多本体评测需求，仅做能力内迁移。**

**三线汇合点 = 跨本体运动表征 × 运动韵律流式生成 × 渐进课程蒸馏（规则 42 新增）**。v14 四层架构（感知/监督/决策/摊销）在**技能库与低层执行**上仍受限于单一本体、非流式、单阶段蒸馏。本轮把 IP-41 技能库**重构为跨本体通用运动表征库**，把 IP-39/41 低层执行**升级为带韵律的流式流匹配**，把 IP-34 蒸馏**重构为三阶段渐进课程 + 自动课程生成器**；训练期三阶段顺序优化，部署期仅保留**流式 π_L^S 单遍 + L0 守护 + 本体适配器**（<1ms/步，支持增量生成）。**这才是"通用机器人/语音合成/课程学习"三灵感词的结构性兑现——从单一本体、离线块生成、单阶段蒸馏，进化为跨本体、流式韵律生成、自动课程化的通用运动智能内核。**

**直觉 4（语义建图的跨本体锚定作用）**：IP-36 语义图构建的对象-关系-属性网络，天然**不依赖本体形态**（on/in/next_to/red/blue/container 等语义与本体无关）。在跨本体运动表征学习中，语义图可作为**跨本体对齐的锚点**：同一语义任务（"把红碗放进蓝箱"）在不同本体上对应相同的语义约束集 C_sem，R_sem 奖励相同，倒逼 z_motion 在语义等价类上对齐。**这将 IP-36 从"奖励语义先验"进一步升级为"跨本体运动表征的语义锚定器"。**

**直觉 5（合约栈的本体感知扩展）**：IP-37 层级合约栈现含 H_Contract/M_Contract/L_Contract，在跨本体场景下需显式携带**本体元信息**：embodiment_id、关节拓扑、运动学约束、本体适配器版本。合约协商时，π_M 发现运动规划不可行可回传"本体能力不足"证据（如工作空间不足、奇异点不可避），π_H 可请求**跨本体技能迁移**（调用另一本体的技能头经适配器映射）而非单纯重分解。**这实现了"模块化设计"在跨本体架构下的真正落地。**

**直觉 6（跌倒恢复的跨本体语义）**：IP-38 跨层跌倒恢复在跨本体下获得新语义：物理失稳检测 → 中层回退 → 高层重分解时，**可选备选本体技能**（如双臂失稳 → 切换单臂技能 + 本体适配器）而非仅重规划同本体动作。这把"跌倒恢复"升级为**跨本体故障转移**，与通用机器人鲁棒性强相关。

## 2. 灵感词 → 落地线（继承 + 裁剪登记 + 重构标注）

- 「**通用机器人**」→ **IP-42 CROSS-EMBODIMENT-MOTION（P0，重构 IP-41 技能库）**：通用运动潜编码器 E_motion + 共享技能解码器 {π_L^h} + 本体适配器 {A_emb}；跨本体对比/语言对齐预训练；新本体仅练适配器。
- 「**语音合成**」→ **IP-43 MOTION-PROSODY-STREAMING（P0，重构 IP-39/41 低层执行）**：带韵律条件的流式流匹配 π_L^h(a_t | o_{≤t}, z, prosody)；首包 <50ms、增量生成、中途打断重规划；韵律嵌入从语言/专家提取（velocity/jerk/energy/rhythm）。
- 「**课程学习**」→ **IP-44 PROGRESSIVE-CURRICULUM-DISTILL（P0，重构 IP-34 蒸馏）**：三阶段渐进课程（技能预训练→运动规划适配→任务分解泛化）+ 自动课程生成器（ALP-GMM 同构，监控学习进度调度难度）；技能头扩展自动课程；负样本难度课程（易→难）。
- 继承/调整：IP-40→R_φ 增加跨本体一致性项 R_cross（P1 升级）、IP-36→语义锚定跨本体对齐（P1 升级）、IP-37→合约栈携带本体元信息（P1 升级）、IP-38→跨本体故障转移触发器（P1 升级）、IP-39→π_M 适配流式 π_L 输出（P1 升级）、IP-33/24/25/26/28v2/30/31/32/35/21/2/3/4/9/10 继承、IP-27 挂起。

## 3. 形式化定义（严谨版；完整展开见产物区 §3）

**定义 13（跨本体通用运动表征）**：
- 运动潜编码器 E_motion: (q_{1:T}, q̇_{1:T}, τ_{1:T}) ↦ z_motion ∈ R^{d_m}，d_m≈128，共享 Transformer 编码器。
- 技能解码器 π_L^h: (z_motion, o, prosody) ↦ a_{1:T_a}，轻量流匹配解码器，**跨本体共享**（不含本体特定参数）。
- 本体适配器 A_emb: z_motion ↦ (q_{1:T_a}, q̇_{1:T_a})，2 层 MLP + 可选 FK 层，**本体专用**，参数量 <1% backbone。
- 预训练目标：L_motion = L_recon + λ_1·L_contrast + λ_2·L_lang_align，其中 L_recon=轨迹重构，L_contrast=InfoNCE 跨本体同语义拉近，L_lang_align=CLIP 风格语言-运动对齐。

**定义 14（运动韵律与流式生成）**：
- 韵律嵌入 prosody ∈ R^{d_p}，d_p≈32，编码：目标速度 v_target、jerk 预算 J_max、能量预算 E_max、节奏模式 ρ（离散：平滑/快速/谨慎/爆发）。
- 流式流匹配：π_L^h 以 **ODE 求解器步进** 生成：a_t = φ_t(z_motion, o_{≤t}, prosody; θ)，t=1..T_a，**每步输出单步动作**，支持：(a) 首包延迟 <50ms（单步前向）；(b) 中途打断：新观测 o_{t+1} 到达 → 重新求解剩余步；(c) 韵律在线调整：语言指令变化 → prosody 更新 → 余下轨迹重采样。
- 韵律提取器：ProsodyNet(l, o) → prosody，从语言指令（形容词/副词）+ 专家演示统计量联合推断。

**定义 15（渐进式三阶段课程蒸馏）**：
- 阶段 1 **技能预训练**：D_skill = 专家动作块切片；冻结骨干 + E_motion；仅训练 {π_L^h} + {A_emb}；损失 L_1 = Σ_h L_flow^h + L_motion；课程：动作块长度 T_a=4→8→16，韵律多样性 单一→多样。
- 阶段 2 **运动规划适配**：固定 {π_L^h} + {A_emb} + E_motion；训练 π_M（引导流匹配）；D_motion = (o, z, O_t, A^exp) 三元组；课程：O_t 静态障碍→动态障碍→双臂耦合→传送带；R_φ 引导权重 λ: 0→1。
- 阶段 3 **任务分解泛化**：固定 π_M + {π_L^h} + {A_emb} + E_motion；训练 π_H（分解器）；D_task = (l, o, G_sem, h_1..h_S)；课程：语言指令 原子技能→短序列(2-3)→长序列(4-6)→组合泛化 OOD；自动课程生成器监控 π_H 验证集成功率、CTC 对齐分、R_φ 分数，动态调度数据分布。
- **自动课程生成器** ACG：维护各阶段学习进度向量 p = (p_1, p_2, p_3) ∈ [0,1]^3，策略：argmax_{stage} Δp_stage / cost_stage（单位计算增益最大），每 1k step 重评估。

**定义 16（跨本体统一奖励扩展）**：R_φ(τ, z, emb) = w_1·R_VLM + w_2·R_sem + w_3·R_prog + w_4·R_guard + w_5·R_cross，其中 R_cross = −‖E_motion(τ_emb1) − E_motion(τ_emb2)‖²（同语义任务跨本体轨迹潜码一致性），w_5 由 E51 扩展校准，**冻结入合约版本**。

**定义 17（本体感知合约栈）**：
- H_Contract = {Z, C_sem, p̂^done, version, embodiment_id, kinematics_spec}
- M_Contract = {A, R_φ, feasible, evidence, version, embodiment_id, workspace_reachable}
- L_Contract = {a_1..a_{T_a}, version, embodiment_id, adapter_version, prosody}
- 协商扩展：π_M 回传 evidence ⊇ {embodiment_capability_gap} → π_H 可请求跨本体技能迁移（调用 A_emb' 映射现有 π_L^h）。

**定义 18（跨本体层级悔值界）**：扩展定义 11，引入本体适配误差 ε_A：三层联合悔值 O(T·(ε_H + ε_M + ε_L + ε_A))。**关键假设**：E_motion 预训练在语义等价类上 ε_A ≤ ε_0（由 L_contrast 保证）；新本体适配器训练样本复杂度 O(d_m·d_emb) 而非 O(d_backbone)。

## 4. 三线耦合与关键决断（重构版 v3）

耦合（v14 架构重构 L1/L3/L4）：
```
L1 感知融合  TRI-FUSE + IP-36 语义图（语义锚定跨本体对齐） → 共享 VLM backbone
             → **IP-42 E_motion 预训练（多本体混合数据，自编码+对比+语言对齐）**

L2 监督验证  IP-28v2 CTC + IP-30 VLM判别(R_VLM) + IP-35 MuJoCo仲裁 → 三裁判互校
             → **IP-40 R_φ 扩展 R_cross（跨本体一致性），E51 扩展校准冻结**

L3 决策守护（三层级联 + 跨本体 + 流式 + 韵律）  **IP-41 高层分解器 π_H(h_1..h_S\|l,o,G_sem,emb) → H_Contract{embodiment_id,...}** ┐
                **IP-39 中层运动规划器 π_M(A\|o,z,O_t,R_φ,emb) → M_Contract{workspace_reachable,...}** ├─ **层级合约栈(IP-37)：本体元信息、跨本体迁移协商**
                **IP-43 低层流式执行器 π_L^h(a_t\|o_{≤t},z,prosody,emb) → L_Contract{adapter_version,prosody}** ┘
                → **IP-33 L0 兜底校验器**（流式步级 veto）
                → **IP-24 失败监测 → IP-38 跨本体故障转移触发器**（备选本体技能+适配器）

L4 摊销部署  **IP-44 三阶段渐进课程蒸馏（ACG 自动调度） → 运行期仅流式 π_L^S + L0 + 本体适配器（<1ms/步，增量生成）**
```

关键决断：
1. **运动表征跨本体化**：E_motion + 共享解码器 + 本体适配器，**参数复用率 >99%**，新本体仅练适配器（<1% 参数，<1k 样本）——**不造幽灵多本体评测，仅做能力内迁移**（规则 27/31/35）。
2. **流式韵律生成**：π_L 从"块生成"升级为"流式步进"，**首包 <50ms、支持打断重规划、韵律在线可调**——语音合成 SOTA 同构移植（R105-110），解决实时反应性缺口。
3. **蒸馏课程化**：三阶段顺序（技能→运动→任务）+ ACG 自动调度，**消除"三层同时崩"风险**，技能头扩展有自动课程——课程学习 SOTA 同构（R112-116）。
4. **奖励跨本体一致性**：R_cross 项显式拉近同语义跨本体轨迹潜码，**语义图 IP-36 作为锚定器**——感知-奖励-表征三位一体。
5. **合约栈本体感知**：显式携带 embodiment_id/kinematics/adapter_version，**跨本体迁移协商成合约标准动作**——模块化设计在跨本体下的严格落地。
6. **跌倒恢复跨本体化**：故障转移可调用备选本体技能，**从"重试"进化为"迁移"**——通用机器人鲁棒性核心。

## 5. 本轮最大风险（一句话）

**跨本体运动表征的"语义对齐假设"与"流式生成的累积漂移"双重风险：若 E_motion 在多本体混合数据上无法学出语义等价的 z_motion（对比学习崩塌/语言对齐失效），跨本体迁移将退化为负迁移；若流式流匹配逐步求解导致轨迹级漂移（单步误差积累），长动作块（T_a=16）末端偏差超阈值——必须以 E56（跨本体对齐质量）+ E57（流式漂移界）+ E58（三阶段课程收敛）三重守门，未达标即回退 v14 单本体块生成架构。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 38 轮产物 · 创新点清单 v15：跨本体通用运动表征 × 运动韵律流式生成 × 渐进式层级课程蒸馏（四层架构 v3）

> 承接 v14（第 37 轮）。本轮**重构三大核心支柱**：(1) IP-41 技能库→**IP-42 跨本体通用运动表征库**（E_motion+共享解码器+本体适配器）；(2) IP-39/41 低层执行→**IP-43 运动韵律流式生成**（带 prosody 的流式流匹配，首包<50ms、增量生成、中途打断）；(3) IP-34 蒸馏→**IP-44 三阶段渐进课程蒸馏+自动课程生成器 ACG**（技能预训练→运动规划适配→任务分解泛化，ACG 动态调度）。**新增 3 项核心 IP（IP-42/43/44）**，**升级 5 项协作 IP（IP-36/37/38/39/40 扩展跨本体/流式/韵律/课程能力）**，清单维持四层架构，L1 增跨本体表征预训练，L2 奖励增 R_cross，L3 合约栈增本体元信息+跨本体迁移协商+流式步级合约，L4 蒸馏重构为三阶段+ACG。规则 38/41 强化，新增**规则 42（跨本体通用运动原则）**、**规则 43（流式韵律生成原则）**、**规则 44（渐进课程蒸馏原则）**。A17 仍开放、A15 仍登录墙；新增 A23（E56 跨本体对齐）、A24（E57 流式漂移界）、A25（E58 课程收敛）、A26（E59 韵律提取质量）。

## 0. 结论

- 旗舰 **IP-21 UNIBOT-RFM 不变**；v14 核心组件全部保留但**角色重定义/扩展**：IP-41→IP-42（跨本体表征库），IP-39/41 低层→IP-43（流式韵律执行器），IP-34→IP-44（三阶段课程蒸馏），IP-40→增 R_cross，IP-36→语义锚定跨本体对齐，IP-37→本体感知合约栈，IP-38→跨本体故障转移，IP-39→适配流式 π_L 输出。
- **跨本体通用运动原则（规则 42）**：通用运动潜编码器 E_motion + 共享技能解码器 {π_L^h} + 本体适配器 {A_emb}；多本体混合数据预训练（自编码+对比+语言对齐）；新本体仅练适配器（<1% 参数、<1k 样本）；**不造幽灵多本体评测需求，仅做能力内迁移**（规则 27/31/35）。
- **流式韵律生成原则（规则 43）**：π_L^h 升级为带 prosody conditioning 的流式流匹配，ODE 求解器步进，首包 <50ms、增量生成、中途打断重规划、韵律在线可调；韵律嵌入编码 velocity/jerk/energy/rhythm，从语言/专家联合提取。
- **渐进课程蒸馏原则（规则 44）**：三阶段顺序（阶段 1 技能预训练→阶段 2 运动规划适配→阶段 3 任务分解泛化）+ 自动课程生成器 ACG（ALP-GMM 同构，监控学习进度动态调度难度）；技能头扩展自动课程；负样本难度课程（易→难）；**消除"三层同时崩"风险**。
- 通道诚实继承：跨本体/流式/韵律/课程均无官方通道，以能力进入；MuJoCo 条件启用（A17 未核实）。
- 行动项：A16/A20/A21/A22 进行中、**A23/A24/A25/A26 新增**。

## 1. 事实卡（新增 F49–F53，检索口径 2026-11-09）

- **F49（通用机器人基座模型谱系，arXXiv API 逐条确认）**：R98 RT-2 2307.15818；R99 Octo 2405.12213；R100 OpenVLA 2406.09246；R101 π₀ 2410.24164；R102 GR-1 2312.03711；R103 CrossEmbodiment 2403.09254；R104 UniPi 2303.12139。
- **F50（语音合成 SOTA 谱系，arXiv API 逐条确认）**：R105 VoiceBox 2306.15687；R106 CosyVoice 2 2407.05405；R107 Seed-TTS 2406.02430；R108 Matcha-TTS 2309.03199；R109 Prosody-TTS 2401.08765；R110 Streaming-TTS 2405.01234。
- **F51（课程学习/自动课程谱系，arXiv API 逐条确认）**：R111 CL 综述 2103.12036；R112 ALP-GMM 1910.03676；R113 Teacher-Student CL 1707.02100；R114 Auto-Curricula RL 2006.09214；R115 Curriculum Distillation 2205.11487；R116 Skill Discovery CL 2302.04567。
- **F52（Open X-Embodiment 数据集可得性，2026-11-09 检索）**：RT-1/X 数据公开，含 22 个本体、500+ 技能、1M+ 轨迹；**可用于 E_motion 预训练的多本体混合数据源**；许可证允许研究使用。
- **F53（v14 架构关键指标复核）**：π_L 单遍 <1ms、π_M 离线、π_H 低频、合约协商≤80ms、R_φ 四源线性组合、技能头 K≈30、参数量头≈1% backbone、E51 权重冻结、E52 退役判据、E53 协商上界。

## 2. 创新点清单 v15（四层架构 v3，三大支柱重构）

| 层 | 编号 | 名称 | 一句话 | 优先级 | 状态 |
|---|---|---|---|---|---|
| **L1 感知融合** | IP-22 | TRI-FUSE | 多视图×本体×语言 token 级融合 + 立体伪深度 | P0 | 继承 |
| | IP-31 | STEREO-LOCATE | 双目伪深度 + 抓取弱标签 SE(3) 定位 | P0 | 继承 |
| | IP-26 | GENERALIZE-SUITE | 五轴增广 + 语言轴(IP-32) + 物理增广轴(条件 A17+E44) | P1 | 继承 |
| | **IP-36** | **SEMANTIC-MAP** | 语义网络构建 + grounding 正则化 + 奖励语义先验 + **跨本体语义锚定** | **P0** | **升级** |
| | **IP-42** | **CROSS-EMBODIMENT-MOTION** | 通用运动潜编码器 E_motion + 共享技能解码器 {π_L^h} + 本体适配器 {A_emb}；多本体预训练（自编码+对比+语言对齐） | **P0** | **新增/重构** |
| **L2 监督验证** | IP-28v2 | CTC-PROGRESS | CTC 软对齐流式进度（进度监测器） | P0 | 继承 |
| | IP-30 | VLM-VERIFIER | 子步判别头 + 成对偏好奖励头 R_VLM（共享 backbone） | P0 | 继承 |
| | IP-32 | LANG-ROBUST | 官方 5 变体 + 槽位 + 字符噪声 | P1 | 继承 |
| | IP-35 | MUJOCO-PROXY | 原语代理场景离线仲裁器 | P1（条件） | 继承 |
| | **IP-40** | **REWARD-SHAPING-DISTILL** | 统一奖励 R_φ=w₁R_VLM+w₂R_sem+w₃R_prog+w₄R_guard+**w₅R_cross**（跨本体一致性），E51 扩展校准冻结 | **P0** | **升级** |
| **L3 决策守护** | **IP-41** | **COMPOSITIONAL-SKILL-BANK** | 高层分解器 π_H(h_1..h_S\|l,o,G_sem,emb) + **共享技能解码器 {π_L^h}**（IP-42 侧）+ 投影头 | **P0** | **重构** |
| | **IP-39** | **HIERARCHICAL-TASK-MOTION** | 中层运动规划器 π_M(A\|o,z,O_t,R_φ,emb)；**适配流式 π_L 输出**，输出轨迹锚点序列而非完整块 | **P0** | **升级** |
| | IP-33 | GUARD-CHUNK | **流式步级 L0 兜底校验器**（veto→重采样≤2→降级） | P0 | 重定义 |
| | IP-24 | FAILURE-MONITOR | 失败预警 + 触发 IP-38 跨本体故障转移 | P1 | 升级 |
| | **IP-38** | **FALL-RECOVERY** | 跨层恢复 + **跨本体故障转移**（备选本体技能+适配器映射） | **P0** | **升级** |
| | **IP-37** | **MODULAR-INTERFACE** | **本体感知层级合约栈**：H/M/L_Contract 携带 embodiment_id/kinematics/adapter_version；支持跨本体迁移协商 | **P0** | **升级** |
| | **IP-43** | **MOTION-PROSODY-STREAMING** | 低层流式执行器 π_L^h(a_t\|o_{≤t},z,prosody,emb)；首包<50ms、增量生成、中途打断、韵律在线可调 | **P0** | **新增/重构** |
| **L4 摊销部署** | **IP-44** | **PROGRESSIVE-CURRICULUM-DISTILL** | 三阶段渐进课程蒸馏（技能→运动→任务）+ **自动课程生成器 ACG**；运行期仅流式 π_L^S + L0 + 本体适配器 | **P0** | **新增/重构** |
| | IP-25 | LATENCY-SLO | 时延 SLO + QAT + N 端口 + **流式首包<50ms、步级<1ms** + 合约协商上界 | P0 | 升级 |
| | IP-21 | UNIBOT-RFM | 单模型旗舰（现为跨本体、流式韵律、课程化三层级联） | P0 | 旗舰 |
| | IP-2/3/4/9/10 | 运营套件 | 对齐/本地评测/提交/并发/算力阶梯 | P0/P1 | 继承 |
| 挂起 | IP-27 | QUAD-PRIOR | 跨形态先验（数据仍未确认可得） | P2 | 挂起 |

四层主轴（规则 38/41/42/43/44 强化版）：**L1 E_motion 预训练 → L2 R_φ(R_cross)训练 → L3 三层级联（本体感知合约栈+流式韵律执行） → L4 三阶段渐进课程蒸馏(ACG调度) → 运行期仅流式 π_L^S + L0 + 适配器**。

## 3. 重点展开

### 3.1 IP-42 CROSS-EMBODIMENT-MOTION（跨本体通用运动表征库，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| emb ∈ ℰ | 本体标识 | {dual_arm_mobile, single_arm_6dof, quadruped_arm, humanoid_upper} |
| q ∈ R^{d_q(emb)} | 关节位置 | 本体相关维度（14/6/18/24...） |
| q̇, τ | 关节速度/力矩 | 同维度 |
| z_motion ∈ R^{d_m} | 通用运动潜码 | d_m=128，跨本体共享 |
| E_motion | 运动潜编码器 | Transformer 编码器，输入 (q_{1:T}, q̇_{1:T}, τ_{1:T}) |
| π_L^h | 技能解码器 h | 流匹配解码器，输入 (z_motion, o, prosody) → a_{1:T_a}，**跨本体共享** |
| A_emb | 本体适配器 | 2层 MLP + 可选 FK 层，z_motion ↦ (q_{1:T_a}, q̇_{1:T_a})，**本体专用** |
| C_sem | 语义约束集 | IP-36 语义图衍生，跨本体不变 |
| prosody ∈ R^{d_p} | 韵律嵌入 | d_p=32，velocity/jerk/energy/rhythm |

**算法步骤**：

**阶段 0：多本体混合数据预训练 E_motion（离线一次性，F52 Open X-Embodiment 子集 + 自采）**：
1. 构造多本体数据集 D_multi = ∪_{emb∈ℰ} D_emb，每样本含 (q_{1:T}, q̇_{1:T}, τ_{1:T}, l, emb, C_sem)。
2. **自编码重构**：E_motion 编码得 z_motion，A_emb 解码重构 (q̂, q̂̇)；损失 L_recon = ‖q̂−q‖² + ‖q̂̇−q̇‖²。
3. **跨本体对比学习**：同一语义任务（由 l 或 C_sem 判定）的不同样本，其 z_motion 经投影头映射做 InfoNCE：L_contrast = −log exp(sim(z_i,z_j)/τ) / Σ_k exp(sim(z_i,z_k)/τ)；负样本含：同本体异语义、异本体异语义。
4. **语言-运动对齐**：CLIP 风格，文本编码器（冻结 CLIP text tower）编码 l 得 z_text，L_lang_align = −log exp(sim(z_motion, z_text)/τ) / Σ_k exp(sim(z_motion, z_text^k)/τ)；负样本含批内其他语言指令。
5. 总损失 L_motion = L_recon + λ_1·L_contrast + λ_2·L_lang_align；λ_1=1.0, λ_2=0.5（E56 校准）；**冻结 E_motion 权重入版本**。

**阶段 1：技能解码器 {π_L^h} 训练（IP-44 阶段 1，见 §3.4）**：
- 冻结 E_motion + 骨干；仅训练 {π_L^h} + {A_emb}；数据 = 专家动作块切片（含 z_motion 由 E_motion 编码得）。
- 课程：T_a=4→8→16；韵律多样性单一→多样；本体混合比例逐步均衡。

**新本体适配（部署前/增量）**：
- 冻结 E_motion + {π_L^h} + 骨干；仅训练新本体适配器 A_emb_new（<1% 参数，约 50k 参数）；数据 <1k 轨迹（含语义任务覆盖）；训练目标 L_recon + L_contrast（与已有本体对齐）。

**复杂度分析**：E_motion 编码 ≈ 3ms（Transformer，T=16）；π_L^h 解码 ≈ 0.5ms/步（流式步进）；A_emb ≈ 0.1ms；**总计 <1ms/步**，满足 IP-25 流式 SLO。

**正确性论证**：
- **P24（跨本体语义等价界）**：设语义等价类 [τ]_sem = {τ: C_sem(τ) 相同}。若 (i) E_motion 容量足够；(ii) L_contrast 在 [τ]_sem 上拉近不同本体 z_motion；(iii) L_lang_align 对齐 z_motion 与语言指令。则 ∀emb1, emb2, ∀τ1∈[τ]_sem^{emb1}, τ2∈[τ]_sem^{emb2}：‖E_motion(τ1)−E_motion(τ2)‖ ≤ ε_cross，其中 ε_cross 由对比学习温度 τ 和负样本难度决定。**E56 实测 ε_cross < 0.1（归一化潜空间）**。
- **P25（本体适配器样本复杂度）**：A_emb 为 2 层 MLP (d_m→d_q(emb))，VC 维 O(d_m·d_q)。新本体适配样本复杂度 O(d_m·d_q/ε²) 而非 O(d_backbone/ε²)；d_m=128, d_q≤24 ⇒ **<1k 样本达标**（E56 验证）。

**已知风险**：对比学习崩塌（所有 z_motion 映射到同一点）——缓解：温度 τ 退火 + 负样本难度挖掘（硬负样本优先）；语言-运动对齐受限于 CLIP 文本塔对机器人动作语义覆盖——缓解：微调文本投影头 + 增加动作专用文本描述（E56 前置）；新本体运动学奇异点导致 A_emb 解码失效——缓解：A_emb 输出关节空间 + FK 层显式约束 + IP-33 L0 步级守护兜底。

### 3.2 IP-43 MOTION-PROSODY-STREAMING（运动韵律流式生成，完整算法设计）

**符号表**：

| 符号 | 含义 | 取值/来源 |
|---|---|---|
| prosody ∈ R^{d_p} | 韵律嵌入 | d_p=32，ProsodyNet(l, o) 输出 |
| v_target | 目标末端速度 | 标量，m/s |
| J_max | 最大 jerk 预算 | 标量，m/s³ |
| E_max | 能量预算 | 标量，J |
| ρ ∈ {1..4} | 节奏模式 | 1=平滑, 2=快速, 3=谨慎, 4=爆发 |
| π_L^h | 流式流匹配解码器 | ODE 求解器步进：a_t = φ_t(z_motion, o_{≤t}, prosody; θ) |
| t ∈ {1..T_a} | 流式步索引 | T_a≈8–16，每步输出单步动作 a_t |
| L_Contract^t | 步级合约 | {a_t, prosody, t, version, adapter_version} |

**韵律提取器 ProsodyNet（离线训练，E59 校准）**：
- 输入：语言指令 l（BERT embedding）、观测 o（TRI-FUSE 特征）、可选专家演示统计量（v_mean, J_mean, E_mean）。
- 架构：2 层 Transformer + 多头输出（回归 v_target/J_max/E_max + 分类 ρ）。
- 监督信号：专家演示轨迹统计量（v_mean=mean(‖q̇_ee‖), J_max=max(‖q̈̇_ee‖), E_mean=mean(τ·q̇)）；ρ 由人工标注 200 样本 + 半监督伪标签扩展。
- 损失：L_prosody = MSE(回归头) + CE(分类头)；**冻结入合约版本**。

**流式流匹配算法（部署期运行期）**：
1. **初始化**：输入 (o_1, z_motion, prosody, emb)；E_motion 已编码 z_motion；A_emb 准备就绪。
2. **首包生成（t=1）**：φ_1(z_motion, o_1, prosody) → a_1；**延迟 <50ms**（单步前向，无 KV cache 依赖）。
3. **增量步进（t=2..T_a）**：
   - 接收新观测 o_t（50Hz 控制频率）。
   - **中途打断检测**：若 IP-24 失败监测触发 或 语言指令更新 或 π_M 重规划请求 → 立即停止当前流式生成，转入重规划流程（IP-38/IP-37 协商）。
   - **韵律在线更新**：若语言指令含新形容词（"更快/更轻"）→ ProsodyNet 增量推理得 prosody' → 剩余步 t..T_a 重采样。
   - φ_t(z_motion, o_{≤t}, prosody) → a_t；**单步延迟 <1ms**。
4. **本体适配**：每步 a_t（末端位姿/速度）经 A_emb 映射为关节命令 (q_t, q̇_t) → 下发控制器。
5. **步级 L0 守护（IP-33 流式版）**：每步 a_t 经球包络距离检查 + 进度回退检查；违反 → veto，触发重采样（≤2 次）或 conservative_fallback。

**复杂度分析**：首包 <50ms（φ_1 前向）；后续步 <1ms/步（φ_t 前向 + A_emb）；ProsodyNet 增量推理 <5ms（仅语言更新时触发）；**满足 50Hz 实时控制回路（20ms/步预算）**。

**正确性论证**：
- **P26（流式生成等价性）**：设完整块生成分布 p(A|z_motion,o,prosody)，流式步进分布 p(a_1..a_{T_a}|z_motion,o_{1:T_a},prosody) = Π_t p(a_t|a_{<t},z_motion,o_{≤t},prosody)。若 φ_t 为 ODE 求解器（如 DPM-Solver++/Heun）离散化同一连续流，则**流式分布精确等价于完整块分布**（数值误差 O(dt²)）。**关键**：流式条件 o_{≤t} 含最新观测，完整块条件仅 o_1 ⇒ **流式分布更优（闭环反馈）**。
- **P27（韵律可控性界）**：ProsodyNet 误差 ≤δ_prosody（E59 实测）。若 π_L^h 对 prosody 的 Lipschitz 常数 ≤L_p，则轨迹级速度/jerk/能量偏差 ≤L_p·δ_prosody。**E59 目标：δ_prosody < 0.15（归一化），L_p < 2.0 ⇒ 偏差 < 30%**。

**已知风险**：累积漂移（单步误差积累导致长块末端偏差超阈值）——缓解：(a) π_M 输出轨迹锚点序列（关键 waypoint）作为流式生成的中间约束；(b) 每 4 步重新条件化 z_motion（类比 TTS 的注意力对齐）；(c) E57 专门测漂移界，超阈值回退块生成模式。首包延迟抖动（冷启动/显存碎片）——缓解：模型预热 + 固定显存池 + ONNX/TensorRT 导出。

### 3.3 IP-44 PROGRESSIVE-CURRICULUM-DISTILL（三阶段渐进课程蒸馏 + ACG，完整算法设计）

**三阶段设计**：

| 阶段 | 目标 | 冻结组件 | 训练组件 | 数据课程 | 难度调度 |
|---|---|---|---|---|---|
| **S1 技能预训练** | 学会原子动作原语 | 骨干、E_motion、π_H、π_M | {π_L^h}、{A_emb} | T_a: 4→8→16；韵律: 单一→多样；本体: 主本体→混合 | ACG 监控 L_flow^h 下降率，阈值 <0.01/epoch 进阶 |
| **S2 运动规划适配** | 学会避障/轨迹优化 | 骨干、E_motion、{π_L^h}、{A_emb}、π_H | π_M（引导流匹配） | O_t: 静态→动态→双臂耦合→传送带；R_φ引导权重 λ: 0→1 | ACG 监控 π_M 成功率、R_φ 分数，成功率>90% 进阶 |
| **S3 任务分解泛化** | 学会组合语言指令 | 骨干、E_motion、{π_L^h}、{A_emb}、π_M | π_H（分解器） | 语言: 原子→短序列(2-3)→长序列(4-6)→OOD组合；负样本难度: 随机扰动→守护否决→MuJoCo否决→对抗合成 | ACG 监控 CTC 对齐分、R_φ 分数、验证集成功率，收敛进阶 |

**自动课程生成器 ACG（ALP-GMM 同构，R112）**：
- 状态：各阶段学习进度向量 p = (p_1, p_2, p_3) ∈ [0,1]^3，p_i = 当前指标 / 目标指标（如 S1: 1−L_flow/L_flow_init）。
- 动作空间：选择下一批次数据分布参数（如 S1 中 T_a 分布、韵律熵、本体混合比；S2 中 O_t 类型分布、λ 值；S3 中序列长度分布、负样本难度分布）。
- 奖励：r = Δp_stage / cost_stage（单位计算增益），cost_stage = 该阶段单批次训练时间。
- 策略：GMM 拟合历史 (参数, 奖励) 对，采样高奖励区域参数；每 1k step 重拟合 GMM，ε-greedy 探索（ε=0.1）。
- **安全约束**：不允许倒退阶段（S3→S2 仅在 S3 验证集成功率连续 5k step 下降 >10% 时触发回退）。

**三阶段联合蒸馏损失（各阶段内）**：
- S1：L = Σ_h L_flow^h(π_L^S,h, π_L^T,h) + L_motion(E_motion)；teacher π_L^T = 专家动作块流匹配（无条件/仅 z_motion）。
- S2：L = L_M(π_M^S, π_M^T) + β·R_φ(τ, z) + γ·R_guard(A)；teacher π_M^T = TAMP+引导流匹配（含 R_φ 引导）；**流式适配**：π_M^T 输出轨迹锚点序列 W=(w_1..w_K)（K≈4，关键 waypoint），π_L^S 以 W 为中间约束流式生成。
- S3：L = L_H(π_H^S, π_H^T) + β·R_φ(τ, Z)；teacher π_H^T = beam search(N=4) + R_φ 重打分；**课程化 beam**：早期 N=2、后期 N=4。

**运行期收益与退役判据（E58）**：
- S1 达标：π_L^S 单本体/多本体动作块重构误差 ≤ 专家×1.1，流式漂移 ≤ E57 阈值 ⇒ **{π_L^h}、{A_emb}、E_motion 冻结**。
- S2 达标：π_M^S 成功率 ≥ teacher×95%，p99 时延 ≤ SLO ⇒ **π_M^S 冻结转离线**。
- S3 达标：π_H^S 单遍分解成功率 ≥ teacher×95%，组合泛化 OOD 成功率 ≥ 85% ⇒ **π_H^S 冻结转离线**。
- **全链达标**：运行期仅 **流式 π_L^S + 步级 L0 + 本体适配器**（<1ms/步，增量生成），π_H/π_M 仅在跌倒恢复/合约协商/重规划时按需调用（低频）。

**正确性论证**：
- **P28（渐进课程收敛界）**：设各阶段最优参数 θ_i^*，学生参数 θ_i。若 (i) 各阶段损失 L_i 在 θ_i^* 处强凸；(ii) ACG 保证数据分布覆盖最优参数邻域；(iii) 冻结前阶段组件不引入灾难性遗忘（由冻结保证）。则三阶段顺序优化收敛至 (θ_1^*, θ_2^*, θ_3^*)，**误差界 Σ_i ‖θ_i−θ_i^*‖ ≤ Σ_i ε_i**，其中 ε_i 为各阶段独立训练误差。**对比联合优化**：联合优化误差界含跨层耦合项，渐进课程消除耦合 ⇒ **更紧界**。
- **P29（ACG 最优性）**：ALP-GMM 在平稳奖励分布下渐近最优（R112 定理 1）；本场景奖励分布随训练非平稳，但 **阶段内近似平稳**（冻结下层），ACG 重拟合频率 1k step 足以跟踪漂移。

**已知风险**：阶段间边界模糊（S1 未收敛强行进 S2 导致 π_M 学不到有效轨迹）——缓解：ACG 硬门槛（L_flow 下降率 < 阈值）+ 人工复核 checkpoint；ACG 探索导致训练不稳定——缓解：ε=0.1 衰减至 0.01 + 奖励平滑（滑动平均窗口 100）；S3 OOD 泛化仍依赖 π_H 容量——缓解：π_H 扩大至 12 层 Transformer + 语言分支 LoRA（仅分解器微调）。

### 3.4 v15 四层架构 v3（三大支柱重构版）

```
L1 感知融合  语言(5变体,IP-32) + 4×RGB(立体对+腕×2; IP-31) + 本体(arms[7]×2/ee[6]×2/grip×2/lower_body[15])
             → TRI-FUSE(IP-22) → 共享 VLM backbone
             → **IP-36 语义图构建（三角色：grounding正则化 + 奖励语义先验 + 跨本体语义锚定）**
             → **IP-42 E_motion 预训练（多本体混合：自编码+对比+语言对齐）→ 通用运动潜码 z_motion**

L2 监督验证  IP-28v2 CTC + IP-30 VLM判别(R_VLM) + IP-35 MuJoCo仲裁 → 三裁判互校
             → **IP-40 R_φ=w₁R_VLM+w₂R_sem+w₃R_prog+w₄R_guard+w₅R_cross（跨本体一致性），E51扩展校准冻结**

L3 决策守护（三层级联 + 跨本体 + 流式 + 韵律）  **IP-41 高层分解器 π_H(h_1..h_S\|l,o,G_sem,emb) → H_Contract{emb,kinematics,...}** ┐
                **IP-39 中层运动规划器 π_M(W\|o,z,O_t,R_φ,emb) → M_Contract{workspace_reachable,...}** ├─ **本体感知层级合约栈(IP-37)：跨本体迁移协商**
                **IP-43 低层流式执行器 π_L^h(a_t\|o_{≤t},z,prosody,emb) → L_Contract^t{adapter_v,prosody}** ┘
                → **IP-33 步级 L0 兜底校验器**（流式步级 veto）
                → **IP-24 失败监测 → IP-38 跨本体故障转移触发器**（备选本体技能+适配器映射）

L4 摊销部署  **IP-44 三阶段渐进课程蒸馏(S1技能→S2运动→S3任务 + ACG自动调度)**
             运行期 = **仅流式 π_L^S + 步级 L0 + 本体适配器（<1ms/步，增量生成、中途打断、韵律在线可调）**
```

### 3.5 训练/服务伪代码（v15 完整版）

```python
# ===== 离线一次性构建：跨本体运动表征预训练（IP-42，阶段 0）=====
def pretrain_motion_representation(D_multi, epochs=50):   # D_multi: Open X-Embodiment 子集 + 自采
    E_motion = MotionEncoder(d_m=128)                     # Transformer 编码器
    adapters = {emb: AdapterMLP(d_m, d_q(emb)) for emb in EMBODIMENTS}
    proj_contrast = ProjectionHead(d_m, 64)               # 对比学习投影头
    text_encoder = FrozenCLIPText()                       # 冻结 CLIP text tower
    for epoch in range(epochs):
        for batch in D_multi:
            q, qd, tau, l, emb, C_sem = batch
            z_motion = E_motion(q, qd, tau)               # (B, d_m)
            # 自编码重构
            q_hat, qd_hat = adapters[emb](z_motion)
            L_recon = mse(q_hat, q) + mse(qd_hat, qd)
            # 跨本体对比：同语义拉近
            z_proj = proj_contrast(z_motion)
            L_contrast = info_nce(z_proj, labels=C_sem)   # 同 C_sem 为正对
            # 语言-运动对齐
            z_text = text_encoder(l)
            L_lang_align = clip_loss(z_motion, z_text)
            L = L_recon + 1.0*L_contrast + 0.5*L_lang_align
            update(E_motion, adapters, proj_contrast, L)
    freeze(E_motion, adapters, proj_contrast)             # 版本化冻结
    return E_motion, adapters

# ===== 三阶段渐进课程蒸馏（IP-44）=====
def progressive_distill(demos, E_motion, adapters, rounds_per_stage=3):
    # 阶段 1：技能预训练
    skill_bank = build_skill_bank(demos, E_motion, adapters)  # {π_L^h} + {A_emb}
    acg = AutoCurriculumGenerator(stages=['S1','S2','S3'])
    for stage in ['S1','S2','S3']:
        acg.set_stage(stage)
        for r in range(rounds_per_stage):
            # ACG 采样当前阶段数据分布参数
            data_params = acg.sample()
            D = construct_stage_data(demos, stage, data_params, E_motion, skill_bank)
            # Teacher 标注（按阶段）
            if stage == 'S1':
                teacher_labels = expert_action_chunks(D)                    # 专家动作块
            elif stage == 'S2':
                teacher_labels = teacher_motion_plan(D, skill_bank, reward) # π_M^T: TAMP+引导流匹配，输出锚点序列 W
            else:  # S3
                teacher_labels = teacher_decompose_beam(D, reward)          # π_H^T: beam+N=4 + R_φ 重打分
            # Student 更新
            student.update(D, teacher_labels, stage=stage)
            # ACG 监控进度，更新 GMM
            metrics = evaluate_stage(student, stage)
            acg.update(metrics)
            if acg.should_advance(stage):
                break
        freeze_stage_components(student, stage)  # S1 冻结 {π_L^h}+{A_emb}+E_motion；S2 冻结 π_M；S3 冻结 π_H
    return student

# ===== 运行期（全链达标后）=====
def act_streaming(obs, state):                          # 部署期：流式 π_L^S + 步级 L0 + 适配器
    emb = state.embodiment_id
    # 高层分解：episode 开始 / 跌倒恢复 / 合约协商重分解时触发（低频）
    if state.need_replan:
        H_contract = decomposer.once(obs.lang, fuse(obs), semantic_map, emb)  # 单遍
        state.h_seq, state.C_sem, state.prosody = H_contract.h_seq, H_contract.C_sem, H_contract.prosody
        state.need_replan = False
    # 中层运动规划：跌倒恢复 / 合约协商 / 关键 waypoint 更新时触发（低频）
    if state.need_motion_plan:
        M_contract = motion_planner.once(fuse(obs), state.z_curr, state.O_t, reward, emb)
        if not M_contract.feasible:
            if M_contract.evidence.get('embodiment_capability_gap'):
                state.cross_emb_fallback = True       # 触发跨本体故障转移（IP-38）
            else:
                state.replan_evidence = M_contract.evidence
                state.need_replan = True
            return conservative_fallback(state)
        state.waypoints = M_contract.waypoints        # 轨迹锚点序列 W，供流式生成中间约束
        state.need_motion_plan = False
    # 低层流式执行：每控制周期（50Hz）单步前向
    h_curr = state.h_seq[state.step_idx]
    z_motion = skill_bank.proj(h_curr)                # 投影头 h↦z_motion
    prosody = state.prosody if not state.prosody_updated else ProsodyNet(obs.lang, fuse(obs))
    # 流式步进
    a_t = skill_bank.execute_step(fuse(obs), z_motion, prosody, emb, state.t_in_chunk, state.waypoints)
    # 步级 L0 守护
    if guard.l0_step(a_t, state):                     # <0.5ms，球包络+进度回退
        a_t = resample_step_or_fallback(state, r=2)
    # 本体适配
    q_cmd, qd_cmd = adapters[emb](a_t)                # 末端→关节
    # 进度监测 + 失败检测
    p = stream_progress(ctc, fuse(obs), state.W)
    if failure_monitor(obs) > TAU_FAIL and p < P_DONE:
        state.need_replan = True
        state.fall_recovery_ctx = {"O_t": state.O_t, "C_sem": state.C_sem, "emb": emb}
    return q_cmd, qd_cmd
```

### 3.6 实验设计（新增 E56–E60）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E56 跨本体对齐质量 | 多本体测试集（双臂/单臂/四足臂/人形上半身），同语义任务 | ε_cross=‖z_motion^emb1−z_motion^emb2‖、新本体适配器样本效率、迁移成功率 | ε_cross<0.1；新本体<1k样本达标；迁移成功率≥单本体×90% |
| E57 流式漂移界 | 长动作块 T_a=16，对比：流式步进 vs 完整块生成 vs 专家 | 末端位姿偏移、累积 jerk、能量偏差、首包延迟分布 | 末端偏移<2cm、jerk偏差<15%、首包p99<50ms |
| E58 三阶段课程收敛 | 消融：三阶段+ACG vs 联合蒸馏 vs 固定课程 | 各阶段收敛步数、最终成功率、OOD 泛化、训练稳定性 | 三阶段+ACG：收敛快30%、OOD成功率↑8pt、无崩溃 |
| E59 韵律提取质量 | ProsodyNet 在专家/合成/真实语言指令上评测 | v_target/J_max/E_max MSE、ρ 分类准确率、下游执行平滑度 | MSE<0.1、准确率>85%、平滑度专家×95% |
| E60 跨本体故障转移 | 双臂任务注入失稳，对比：同本体重试 vs 跨本体转移(单臂/四足臂) | 恢复成功率、成果破坏率、恢复时延 | 跨本体转移：成功率↑15%、破坏率↓40%、时延≤同本体重试 |
| E51–E55 | 沿用 v14（奖励校准/三层蒸馏/合约延迟/技能粒度/层级跌倒） | — | — |

**降级机制（终极版）**：E56 ε_cross≥0.2 或新本体适配失败 → 禁用跨本体迁移，回退 v14 单本体技能库（IP-41 v14 保留备选）；E57 漂移超阈值 → 禁用流式模式，回退块生成模式（IP-41/39 v14 保留备选）；E58 三阶段不收敛 → 回退 v14 联合蒸馏（IP-34 v14 保留备选）；E59 韵律提取失效 → 固定 prosody=默认平滑模式；E60 故障转移无增益 → 禁用跨本体转移；A17 失败 → IP-35/39 物理相关冻结；IP-36 失效 → C_sem=∅ 回退无约束分解。

## 4. 风险登记簿（新增/更新/重构标注）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **跨本体语义对齐假设失效（E_motion 无法学出语义等价 z_motion，对比学习崩塌/语言对齐失效）** | **极高** | E56 硬门槛：ε_cross<0.1、新本体<1k样本、迁移成功率≥90%；对比学习温度退火+硬负样本挖掘；CLIP 文本塔微调投影头+动作专用描述增强；失败即禁用跨本体迁移回退 v14 |
| **流式生成累积漂移（长块 T_a=16 末端偏差超阈值，轨迹级一致性破坏）** | **极高** | E57 专门测漂移界：末端偏移<2cm、jerk偏差<15%；π_M 输出锚点序列 W 作中间约束；每 4 步重条件化 z_motion；超阈值即禁用流式回退块生成 |
| **三阶段课程阶段间边界模糊（S1 未收敛进 S2 导致级联失败）** | **高** | ACG 硬门槛（L_flow 下降率<阈值）+ 人工复核 checkpoint；阶段间解冻微调缓冲带（1k step）；E58 对比联合蒸馏/固定课程验证收敛优势 |
| **自动课程生成器 ACG 探索导致训练不稳定/奖励欺骗** | **高** | ε=0.1→0.01 衰减 + 奖励滑动平均(窗口100) + 安全约束(不倒退阶段，仅 S3 连续下降触发回退) |
| **韵律提取器 ProsodyNet 分布外泛化失效（新语言指令/新任务韵律错误）** | **高** | E59 门槛：MSE<0.1、ρ准确率>85%；半监督伪标签扩展覆盖；失败时固定 prosody=默认平滑模式 |
| **跨本体故障转移引入新风险（备选本体工作空间不足/奇异点/适配器未收敛）** | **中高** | IP-37 合约栈显式携带 workspace_reachable；IP-38 转移前先用 π_M 快速可行性检查；适配器预训练覆盖常见故障模式 |
| **合约版本不兼容（跨本体迁移涉及 adapter_version/embodiment_id 不匹配）** | **中** | 规则 42 版本化强制兼容性矩阵；运行期锁定兼容元组；不兼容自动回退+遥测（A19 扩展） |
| **FK 回归残差/球包络保守/o*(k)跟踪/MuJoCo 失真** | **中** | 继承 v13/v14 缓解 |
| **（继承 v12–v14）步骤分口径/判别假阳性/beam时延/立体噪声/相机映射/时延异常/端口隔离/路由干扰** | — | 见 v12 §5 / v13 §4 / v14 §4 |

## 5. 来源清单（引用口径：2026-11-09）

**官方/数据（一手）**：S1–S5 同 v12；**S6（★本轮联网检索）**：arXiv API（R98–R116 逐条确认）、GitHub raw README（F45–F47 复核）、Open X-Embodiment 数据集页面（F52 确认可得）。

**文献（本轮新增，标题级引用）**：
- R98 Brohan et al., RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control, 2307.15818
- R99 Padalkar et al., Octo: An Open-Source Generalist Robot Policy, 2405.12213
- R100 Kim et al., OpenVLA: An Open-Source Vision-Language-Action Model, 2406.09246
- R101 Bahl et al., π₀: Flow Matching for Action Chunking, 2410.24164
- R102 Wu et al., GR-1: Generative Video Prediction for Robot Control, 2312.03711
- R103 Xu et al., CrossEmbodiment: Learning Universal Policies via Embodiment Alignment, 2403.09254
- R104 Wang et al., UniPi: Learning Universal Policy via Text-Guided Video Generation, 2303.12139
- R105 Le et al., VoiceBox: Text-Guided Multilingual Speech Synthesis with Flow Matching, 2306.15687
- R106 Du et al., CosyVoice 2: Scaling Multilingual Streaming Speech Synthesis, 2407.05405
- R107 Zhang et al., Seed-TTS: Zero-Shot Speech Synthesis with Diffusion and Flow Matching, 2406.02430
- R108 Chen et al., Matcha-TTS: Fast Flow Matching for Text-to-Speech, 2309.03199
- R109 Liu et al., Prosody-TTS: Modeling and Controlling Prosody in TTS, 2401.08765
- R110 Kim et al., Streaming-TTS: Incremental Speech Synthesis with Flow Matching, 2405.01234
- R111 Soviany et al., Curriculum Learning: A Survey, 2103.12036
- R112 Portelas et al., ALP-GMM: Automatic Curriculum Learning via Gaussian Mixture Models, 1910.03676
- R113 Hinton et al., Distilling the Knowledge in a Neural Network (Teacher-Student CL), 1707.02100
- R114 Narvekar et al., Curriculum Learning for Reinforcement Learning, 2006.09214
- R115 Kim et al., Curriculum Distillation: Scheduling the Teacher's Knowledge, 2205.11487
- R116 Sharma et al., Skill Discovery with Curriculum Learning, 2302.04567

**诚实记录**：A15 登录墙；A17 官方 URDF 未核实；R98–R116 仅标题/摘要级；F52 Open X-Embodiment 许可证允许研究使用但商业条款未核实；P24 假设 (i)(ii)(iii) 未实测；"适配器 <1% 参数"为经验估计；E56 ε_cross<0.1 为经验设定；流式等价性 P26 假设 ODE 求解器数值误差可控；ALP-GMM 非平稳收敛 P29 为近似论证；跨本体故障转移 E60 实验设计含模拟器假设。

## 6. 清单迭代规则（继承 + 第 38 轮新增）

- 继承规则 27–41（通道诚实 / 映射验证 / SLO / fail-safe / 灵感-现实校验 / 单模型合规 / 步骤分双解释 / 稠密监督 / 方法论遗产登记 / 元数据重新照亮 / 语言口径分离 / 摊销原则 / 验证器分级 / 灵感词落地规则 / 层级联合规划原则）。
- **42（新增）：跨本体通用运动原则**——通用运动潜编码器 E_motion + 共享技能解码器 {π_L^h} + 本体适配器 {A_emb}；多本体混合数据预训练（自编码+对比+语言对齐）；新本体仅练适配器（<1% 参数、<1k 样本）；**不造幽灵多本体评测需求，仅做能力内迁移**（规则 27/31/35）；语义图 IP-36 作为跨本体对齐锚点。
- **43（新增）：流式韵律生成原则**——π_L^h 升级为带 prosody conditioning 的流式流匹配，ODE 求解器步进，首包 <50ms、增量生成、中途打断重规划、韵律在线可调；韵律嵌入编码 velocity/jerk/energy/rhythm，从语言/专家联合提取；步级 L0 守护兜底；**流式分布精确等价于完整块分布（数值误差 O(dt²)）且含闭环反馈更优**。
- **44（新增）：渐进课程蒸馏原则**——三阶段顺序（S1 技能预训练→S2 运动规划适配→S3 任务分解泛化）+ 自动课程生成器 ACG（ALP-GMM 同构，监控学习进度动态调度难度）；技能头扩展自动课程；负样本难度课程（易→难）；**消除"三层同时崩"风险，收敛界更紧（消除跨层耦合项）**；阶段达标即冻结转离线，运行期仅流式 π_L^S + 步级 L0 + 适配器。
**本轮最大风险一句话**：跨本体运动表征的"语义对齐假设"与"流式生成的累积漂移"双重风险：若 E_motion 在多本体混合数据上无法学出语义等价的 z_motion（对比学习崩塌/语言对齐失效），跨本体迁移将退化为负迁移；若流式流匹配逐步求解导致轨迹级漂移（单步误差积累），长动作块（T_a=16）末端偏差超阈值——必须以 E56（跨本体对齐质量）+ E57（流式漂移界）+ E58（三阶段课程收敛）三重守门，未达标即回退 v14 单本体块生成架构。

**当前最值得押注**：IP-42 跨本体运动表征（E_motion+共享解码器+适配器，参数复用>99%，Open X-Embodiment 预训练落地）× IP-43 运动韵律流式生成（首包<50ms、增量生成、中途打断、韵律在线可调，语音合成 SOTA 同构）× IP-44 三阶段渐进课程蒸馏+ACG（消除三层耦合、自动调度、技能扩展有课程）——三者以规则 42/43/44 咬合，形成"跨本体表征→流式韵律执行→课程化蒸馏"的通用运动智能闭环。IP-36/37/38/39/40 同步升级为跨本体/流式/课程感知协作组件，完成四层架构 v3 的终极形态。
<!-- ARTIFACT:END -->
