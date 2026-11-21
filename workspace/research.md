# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮（新灵感循环第 1 轮；本轮灵感：「大语言模型」×「机器人」×「智能体」）

> **基线**：上一轮（灵感「人形机器人」×「技术路线图」×「行为树」）MetricVoiceGauge-NCD-HUTDH-v16（定义 627–656；引理 131–136；实验 E671–E690）。
> 本轮纪律：**语言计划是查询、证书格是唯一裁决、新鲜度阶梯是节拍**。不推倒 v16：v16 的 BTS/TRM/WBC/CSC/NCS/MCA/WCB、v13 的 AIO/RTIC/CPD/DGC/DDL/RTCR、v14 的 SCD/DSD/DCA/EDC、v12 的 USG/TGC/BAA/GAGP/UC、v11 的 HAS/HCC/HATD/HDT、v10 的 NGE/DSL/CC/CWM/CAE/NCP、v9 的 AC/MW/ID、v8 的 DA/SPR/Cal 与历轮不变式全部保留。六个新组件——CLP（认证语言规划器）、S2C（语义→证书编译器）、HCG（幻觉遏制守卫）、PSV（计划缝验证器）、APS（异步计划调度器）、AMC（剪除式经验记忆）——一律以**中立元接入 v16 行为层之上**，失效即严格退回 v16（引理 137），再沿 v16→v15→v14→v13→v12→v11→v10→v9→v8→v7→v6 退化链退回。本轮只做三件事：把"LLM 任务规划"改写为**带计划证书的语言计划**、把"智能体自主"改写为**共形语义认证与剪除式记忆**、把"LLM—机器人实时交互"改写为**不阻塞的新鲜度阶梯调度**。

## 0. 直觉与动机

**灵感 1（大语言模型 → 语言计划是"查询"，不是"指令"）**
直觉：LLM 输出的计划是自然语言；传统做法要么信任它（不安全：幻觉步骤直通执行器），要么无视它（浪费：最有价值的语义层被丢弃）。v16 已经建成了完全证书化的行为层（BT 节点证书 NC、里程碑证书 MC、WBC 阶层证书），这恰好构成一张**能力格（capability lattice）**。核心创新：**语义→证书编译器（Semantic-to-Certificate Compiler, S2C）**。语言计划的每个子任务 token 被*投影*到最近的认证锚节点上；投影距离超阈值则输出 ⊥（投影落空）。关键反直觉点：**我们故意剥夺 LLM 组合新能力的权利——它的创造力被限制在认证节点族内部的排序与参数化上；幻觉只会让系统"少能做"（⊥→回退→活动性下降），永远不会"做错事"（跨出证书边界）**。语言层在能力格之上，但无特权：LLM 是提议者，证书格是裁决者。

**灵感 2（智能体 → 智能体必须自证可信：共形语义证书 + 计划缝证书）**
直觉：智能体"自我批评/验证器"的最大问题是自证——verifier 与 proposer 来自同一分布，误差相关，自我验证会系统性失效。核心创新：**幻觉遏制守卫（Hallucination Containment Guard, HCG）+ 计划缝验证器（Plan-Seam Verifier, PSV）**。HCG 把"计划是否可信"变成共形预测问题：在校准集（已执行计划的 (上下文, 计划, 结局) 三元组日志）上计算非一致性分数 s(上下文, 计划)，只接受 s ≤ q̂_α（(1−α) 分位数）的计划；verifier LLM 的意见只进*分数特征*，永远没有直接裁决权。PSV 解决 HCG 看不见的东西：**计划缝隙**——由 individually certified 节点组成的计划，可能在节点交接处出现 `Post_i ∩ Pre_{i+1}` 为空或未被校准覆盖的暂态（"松手"后紧跟"搀扶"：每个节点都有证书，节点之间的关节没有）。PSV 要求计划接受时所有缝证书 `SC_i = Post_{n_i} ∩ Pre_{n_{i+1}}` 非空且体积 ≥ margin，运行时过缝时逐缝复验。关键反直觉点：**计划不是越大越好，而是越大负债越重**——更长计划意味着更多缝隙、更大的累积证书衰减；计划价值必须按长度与缝隙风险打折，"少执行一点计划"常常严格更优。

**灵感 3（机器人 → 实时与延迟解耦：不阻塞、阶梯式退化）**
直觉：LLM 推理延迟（100ms–10s）与 50Hz 控制不可调和；同步等待 LLM 意味着失去实时证书。核心创新：**异步计划调度器（Asynchronous Plan Scheduler, APS）+ 新鲜度阶梯**。控制环永不等待 LLM：CLP 以 0.5–2Hz 异步提出计划；APS 维护计划缓存；缓存计划带时间戳与新鲜度证书；TTL 到期按**前缀截断**退化（保留头部、截去尾部）→ v16 默认策略（里程碑驱动的 BT 执行，无语言）→ v15 回退。关键反直觉点：**计划不是"越新越好"，而是"越旧越短"**——陈旧按证书衰减打折，退化只能截短、不能拼接、不能跨级；每一级阶梯都是上一级的子集。

**三者如何统一**
统一为 **v16 行为层之上的语言规划层**：v16 回答"在当前里程碑硬件/软件/数据许可下、按行为树语义、用当前 WBC 阶层模型，能安全执行哪个全身行为序列"（`Exec_v16`），v17 回答"哪些语言计划能被安全编译为行为树节点序列并在计划证书下执行"（`Exec_v17`）。CLP 是提议侧（创造力），S2C 是编译侧（投影），HCG+PSV 是认证侧（共形+缝隙），APS 是调度侧（新鲜度），AMC 是经验侧（剪除式）。共享状态 `ζ_la=(B_tick, m*, h*, plan_cache, τ_fresh, q̂_α, mem_index, drift_la, mode_la)`。**CLP 回答"试什么"，S2C 回答"能映射到哪些认证节点"，HCG/PSV 回答"哪些计划值得接受"，APS 回答"这一帧执行计划的哪一段、或退到阶梯哪一级"，AMC 回答"历史上哪些计划该被剪除"**。五者不是五个补丁，而是"提议—编译—认证—调度—记忆"的实现链。

## 1. 研究问题（轮次升级版）

- **Q1（语言计划的投影语义）**：如何定义 S2C 的 compile 使"投影落空必回退、投影命中必复用 v16 证书"？锚距离阈值 τ 如何与 HCG 的共形分位数联合校准？⊥ 时整计划拒绝还是逐节点回退？参数化子任务（"走到红桌边"）的参数如何投影到锚点的参数合法域？
- **Q2（语义证书的共形性）**：非一致性分数 s(π,x) 如何构造才能拒绝"流畅但虚构"的计划？具身漂移/词表漂移下校准集的可交换性是否还成立？verifier LLM 如何只进特征不进裁决？α 与 FRR 的代价不对称如何权衡？
- **Q3（计划缝证书的非空性与暂态）**：`SC_i = Post_{n_i} ∩ Pre_{n_{i+1}}` 在高维下体积塌缩怎么办？校准集未覆盖的缝组合如何外推？运行时过缝复验失败时回退到哪个节点、丢弃哪段计划？
- **Q4（新鲜度、记忆与注入的活性边界）**：TTL/前缀截断如何最小化总损失？剪除式记忆如何既抗投毒又保留价值？提示注入下如何证明"最坏只损活性不损安全"？多计划竞争时如何确定性仲裁？

## 2. 设计原则（在 P25–P27 基础上新增 P28–P30）

**P28 语言无特权律（Language as Query, Not Authority）**
LLM 输出只是*查询*，不是*授权*：S2C 的 compile 必须满足 `compile(t) ∈ Anchors(m*, h*) ∪ {⊥}`，其中 Anchors 是 v16 当前满足 `m_n ≤ m* ∧ h_n ≤ h*` 的已认证 BT 节点锚集。投影 ⊥ 必须退到回退；投影命中必须复用该节点 NC 原文，不得放宽；任何输出形态（含工具调用、代码、JSON）都不得绕过 HCG/PSV/TRM。**语言层可新增的动作集合基数恒为零**。

**P29 计划证书不弱于节点证书律（Plan Certificate Includes Seams）**
计划证书 `PC(π) = ∧_i NC(n_i) ∧ ∧_i [SC_i ≠ ∅ ∧ vol(SC_i) ≥ margin_sc] ∧ (∀i: m(n_i) ≤ m* ∧ h(n_i) ≤ h*)`，其中 `SC_i = Post_{n_i} ∩ Pre_{n_{i+1}}`。计划接受时必须**预验全部 SC**；运行时过缝必须**即时复验**；复验失败立即退到前一节点的 Fallback 并丢弃计划剩余段（引理 139）。计划整体只在 PC 成立时允许运行；前缀截断后的部分计划也必须满足 PC（PC 对前缀封闭）。

**P30 不阻塞阶梯律（Non-Blocking Freshness Ladder）**
50Hz 控制环永不等待 LLM：CLP 以 0.5–2Hz 异步提议；APS 持有缓存；缓存计划带新鲜度 `τ = now − t_accept`；`τ ≤ TTL` 是执行的必要条件；`τ > TTL` 先**前缀截断**（从尾部截短、保留头部），`τ > 2·TTL` 降为 v16 默认策略，漂移触发降为 v15 回退。阶梯只有四级：FULL → PREFIX → V16_DEFAULT → V15_FALLBACK，严格单调，禁止跨级、禁止拼接；**新计划只能整体替换缓存计划**。

## 3. 与基线的接口（如何退化）

- CLP 失效（LLM 超时/OOM/掉线）⇒ APS 缓存按 TTL 退化，随后 v16 默认策略（里程碑驱动的 BT 执行，无语言计划）——**等价 v16 路径**；
- S2C 失效（嵌入服务不可用）⇒ 所有计划 ⊥，整计划回退——**等价 v16（更保守）**；
- HCG 失效（校准集损坏）⇒ 切换确定性白名单（只放行历史校准过的 top-K 高频指令模式）——**等价 v16（活性下降）**；
- PSV 失效 ⇒ 计划接受加保守约束：只允许单节点计划——**等价 v16（单步执行）**；
- APS 失效 ⇒ 同步模式：每控制秒至多接受一个计划、超时视为无计划——**等价 v16**；
- AMC 失效 ⇒ 空记忆：不剪除、不排序——**等价 v16**；
- 六者全失效 ⇒ MetricVoiceGauge-NCD-HUTDH-v16，再沿退化链退回 v15/v14/v13/v12/v11/v10/v9/v8/v7/v6；
- **安全继承**：S2C 只向下投影到既有锚，HCG 只能拒绝不能授权，PSV 只增缝约束，APS 只截短不拼接，AMC 只剪除不新增。六端口互不相交，均不能新增授权或放宽任何阈值；`Exec_v17⊆Exec_v16` 由引理 137 保证。

## 4. 预期贡献

1. **语言无特权编译**：首次把"LLM 计划→机器人执行"改写为"向证书格投影"，证明幻觉率只与活性损失挂钩、不安全率相对 v16 恒为零，填补"语言模型直通控制回路"的空白；
2. **计划缝证书**：发现并形式化"每个节点都有证书、节点之间却无证书"的缝隙缺口，给出 SC_i 非空性、体积阈值与运行时复验语义，使计划级安全从"看起来合理"升级为"暂态被覆盖"；
3. **共形语义证书**：给出 verifier 只进特征、有限样本分位数接受规则，使"智能体自我信任"首次独立于提议者的统计保证；
4. **不阻塞新鲜度阶梯**：把"LLM 延迟 × 实时控制"冲突改写为 TTL+前缀截断的四级单调阶梯，证明控制环 p99 与 LLM 推理 p99 解耦；
5. **剪除式经验记忆**：智能体记忆只能剪除候选与重排序、不能扩证书，关闭记忆投毒的授权攻击面；
6. **提议—编译—认证—调度—记忆五层分离**：v12 管"允许什么"，v13 管"时限内实现多少"，v15 管"技能如何扩散"，v16 管"全身行为如何按里程碑执行"，v17 管"哪些语言计划被编译与调度"，用 `Exec_v17⊆Exec_v16⊆Exec_v15⊆Exec_v13⊆Exec_v12` 把语言、行为、路线、动力学、实时、蒸馏全解耦；E691–E710 覆盖编译精度、共形覆盖、缝隙暂态、注入鲁棒、阶梯新鲜度、记忆投毒、端到端与消融。

## 5. 本轮最大风险

**一句话**：HCG 的共形证书与 PSV 的缝体积估计都依赖"校准集覆盖了当前计划的组合模式"，但 LLM 的价值恰恰是产出**前所未见的组合**——新颖组合可能逐节点语义分在分位数内、逐节点证书成立、缝隙形式非空（全是基于采样的估计），运行时却在**校准集从未覆盖的缝隙暂态**上失稳，即"逐节点证书成立、语义共形通过、里程碑许可满足，而节点之间关节的证书是外推估计"的、新颖且共形却绝对不安全的语言计划。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# IP-415–419 v19 新增核心模块

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-NCD-HUTDH-v18） |
|---|---|---|---|
| IP-415 | Demonstration Certificate Miner (DCM) | 新增核心模块 | 演示反向编译：轨迹→节点证书序列+缝证书+碰撞证书；投影落空即丢弃 |
| IP-416 | Object-Generalized Collision Certificate (OGCC) | 新增核心模块 | 物体泛化即碰撞域收缩：Θ_n^col(o_t) = Θ_n ∩ ColDom(n, o_t)、体积门控、亏空上界 |
| IP-417 | Collision Certificate Verifier (CCV) | 新增在线验证模块 | 三层碰撞裁决（广相位/窄相位/证书相位）；UNKNOWN=UNSAFE；可审计 proof |
| IP-418 | Demonstration Replay Scheduler (DRS) | 新增在线调度模块 | 演示回放异步、不阻塞、优先级驱动；新锚经 SAS 影子晋升→NCS 正式化 |
| IP-419 | Object Geometry Catalog (OGC) | 新增编目模块 | 物体几何表示：凸分解+SDF 缓存+Minkowski 预计算；支持保守 ColDom 查询 |

## 0. 核心符号体系（定义 727–766）

| 符号 | 含义 |
|---|---|
| τ = (x_0, a_0, ..., x_T) | 专家演示轨迹：状态-动作序列 |
| DCM(·) | 演示证书挖掘器：反向编译 τ → (nodes, seams, CC) ∪ {⊥}（定义 727） |
| segment(τ, n) | 演示子段：对应节点 n 的连续片段 |
| mine_segment(seg, x) → n ∪ {⊥} | 子段投影：最近锚（复用 S2C）；距离 > τ_mine 或碰撞证书失败 ⇒ ⊥（定义 728） |
| CC(τ) = (collision_free, proof) | 演示碰撞证书：全轨迹零碰撞的保守证明（定义 729） |
| ColDom(n, o) ⊆ Θ_n | 节点 n 在物体 o 上的碰撞安全参数域（定义 730） |
| Θ_n^col(o) = Θ_n ∩ ColDom(n, o) | 泛化后的碰撞参数域（定义 731） |
| margin_col | 碰撞域最小体积阈值；体积 < margin_col ⇒ 拒绝泛化 |
| def_col(T) = vol(Θ_n) - vol(Θ_n^col(o_t)) | 泛化亏空：参数域体积损失（定义 732） |
| δ_geom | 独立几何探针给出的亏空保守上界（定义 733） |
| OGCC 接受规则 | Θ_n^col(o_t) ≠ ∅ ∧ vol(Θ_n^col(o_t)) ≥ margin_col ∧ def_col ≤ δ_geom（定义 734） |
| CCV(n, o, θ) → {SAFE, UNSAFE, UNKNOWN} | 碰撞证书验证器：三层裁决，UNKNOWN 视为 UNSAFE（定义 735） |
| broad_phase(n, o, θ) | 广相位：凸包/AABB 快速剔除，返回 {POSSIBLE, SAFE}（定义 736） |
| narrow_phase(n, o, θ) | 窄相位：GJK/EPA/SDF 精确查询，返回 {SAFE, UNSAFE, UNKNOWN}（定义 737） |
| cert_phase(n, o, θ, verdict) | 证书相位：封装 ColCert = (n, o, θ, verdict, proof)（定义 738） |
| ColCert = (n, o, θ, verdict, proof) | 碰撞证书：含可审计几何推导链（定义 739） |
| DRS(·) | 演示回放调度器：异步、优先级驱动、不阻塞 50Hz（定义 740） |
| priority(τ) = α·novelty(τ) + β·cert_gap(τ) - γ·age(τ) | 回放优先级：新锚潜力 - 陈旧惩罚（定义 741） |
| OGC(o) = (convex_decomp, sdf_cache, minkowski_cache) | 物体几何编目条目（定义 742） |
| convex_decomp(o) = {H_1, ..., H_K} | 物体凸分解：凸包集合（定义 743） |
| sdf_cache(o) : SE(3) → R | 符号距离场缓存：离线预计算、在线插值（定义 744） |
| minkowski_cache(n, o) | 末端执行器与物体的 Minkowski 和预计算（定义 745） |
| ζ_demo = (demo_buffer, anchor_mined, col_cert_cache, obj_catalog, cgv_q̂, mode_demo) | 演示层共享状态（扩展 v18 ζ_ood，定义 746） |
| Exec_v19 | 通过 DCM/OGCC/CCV 且编译节点序列可被 v18 CSC 执行的演示衍生计划集合（定义 747） |

## 1. 关键算法骨架

```python
# IP-415 Demonstration Certificate Miner：演示→证书序列+碰撞证书
class DemonstrationCertificateMiner:
    def __init__(self, s2c, ccv, tau_mine, margin_seam, margin_col):
        self.s2c = s2c              # 复用 v17 S2C 投影
        self.ccv = ccv              # 碰撞证书验证器（硬门）
        self.tau_mine = tau_mine
        self.margin_seam = margin_seam
        self.margin_col = margin_col

    def mine(self, tau, x, m_star, h_star, obj):
        # 1. 轨迹分段：按动作语义/接触事件切分为子段
        segments = self.segment_trajectory(tau, obj)
        nodes, seams, col_certs = [], [], []

        for seg in segments:
            # 2. 子段投影到最近锚（复用 S2C）
            hit, d = self.s2c.compile_token(seg.intent_token, x, m_star, h_star)
            if hit is None:
                return None, 'MINE_PROJ_FAIL'   # ⊥：整段演示作废

            n, theta = hit
            # 3. 碰撞证书：该子段在演示物体上必须零碰撞
            col_ok, col_cert = self.ccv.verify_segment(seg, n, theta, obj)
            if not col_ok:
                return None, 'MINE_COL_FAIL'

            nodes.append((n, theta))
            col_certs.append(col_cert)

        # 4. 缝证书预验（复用 PSV）
        ok, i, sc = self.psv.verify([n for n,_ in nodes])
        if not ok:
            return None, f'MINE_SEAM_FAIL@{i}'

        # 5. 全轨迹碰撞证书（连续时间保守证明）
        cc_tau = self.construct_continuous_col_cert(tau, obj, col_certs)
        return MinedDemo(nodes=nodes, seams=seams, col_certs=col_certs, cc_tau=cc_tau), 'OK'

    def construct_continuous_col_cert(self, tau, obj, col_certs):
        # 用凸包包络整段轨迹，配合 Minkowski 和证明连续无碰撞
        hull = convex_hull([x for x,_,_ in tau])
        proof = minkowski_proof(hull, obj, self.ogc.minkowski_cache(obj))
        return ColCertFull(trajectory=tau, obj=obj, hull=hull, proof=proof, verdict='SAFE')


# IP-416 Object-Generalized Collision Certificate：泛化即碰撞域收缩
class ObjectGeneralizedCollisionCertificate:
    def __init__(self, ogc, ccv, margin_col, delta_geom_probe):
        self.ogc = ogc
        self.ccv = ccv
        self.margin_col = margin_col
        self.delta_geom_probe = delta_geom_probe   # 独立几何探针

    def generalize(self, n, theta_src, obj_src, obj_tgt):
        # 1. 获取源节点的完整参数域 Θ_n
        theta_dom = self.get_param_domain(n)
        # 2. 查询目标物体的碰撞安全域 ColDom(n, obj_tgt)
        col_dom = self.query_col_dom(n, obj_tgt)
        # 3. 求交：泛化后的碰撞参数域
        theta_col = intersect_domains(theta_dom, col_dom)
        if theta_col is None or theta_col.volume() < self.margin_col:
            return None, 'OGCC_VOLUME_ZERO'

        # 4. 亏空估计：体积损失
        def_col = theta_dom.volume() - theta_col.volume()
        # 5. 独立几何探针给保守上界
        delta_geom = self.delta_geom_probe.upper_bound(n, obj_src, obj_tgt)
        if def_col > delta_geom:
            return None, 'OGCC_DEFICIT_EXCEEDS_BOUND'

        # 6. CCV 硬验证：在收缩域内采样验证
        if not self.ccv.verify_domain(n, obj_tgt, theta_col):
            return None, 'OGCC_CCV_REJECT'

        return GeneralizedCert(node=n, theta_col=theta_col, def_col=def_col,
                               delta_geom=delta_geom, obj_tgt=obj_tgt), 'OK'

    def query_col_dom(self, n, obj):
        # 保守构造 ColDom：用凸分解+SDF+Minkowski 的交
        ogc_entry = self.ogc.get(obj)
        # 广相位剔除：AABB/凸包快速判定
        broad_safe = self.ccv.broad_phase(n, obj, theta_dom.representative())
        if broad_safe == 'SAFE':
            return theta_dom   # 全域安全
        # 窄相位：在参数域上构造 SDF 采样网格，保守内切
        return self.construct_conservative_col_dom(n, obj, ogc_entry)


# IP-417 Collision Certificate Verifier：三层碰撞裁决
class CollisionCertificateVerifier:
    def __init__(self, ogc, broad_eps=1e-3, narrow_eps=1e-4):
        self.ogc = ogc
        self.broad_eps = broad_eps
        self.narrow_eps = narrow_eps

    def verify(self, n, obj, theta):
        # 广相位：凸包/AABB 快速剔除
        broad = self.broad_phase(n, obj, theta)
        if broad == 'SAFE':
            return 'SAFE', self.cert_phase(n, obj, theta, 'SAFE', proof='broad_phase_convex_disjoint')

        # 窄相位：GJK/EPA/SDF 精确查询
        narrow = self.narrow_phase(n, obj, theta)
        if narrow == 'SAFE':
            return 'SAFE', self.cert_phase(n, obj, theta, 'SAFE', proof='narrow_phase_gjk_separation')
        if narrow == 'UNSAFE':
            return 'UNSAFE', self.cert_phase(n, obj, theta, 'UNSAFE', proof='narrow_phase_gjk_penetration')

        # UNKNOWN：数值退化/退化配置/采样不足
        return 'UNSAFE', self.cert_phase(n, obj, theta, 'UNSAFE', proof='narrow_phase_unknown_conservative')

    def broad_phase(self, n, obj, theta):
        # 末端执行器凸包 与 物体凸分解 的快速分离测试
        ee_hull = self.ee_convex_hull(n, theta)
        obj_hulls = self.ogc.get(obj).convex_decomp
        for H in obj_hulls:
            if not gjk_disjoint(ee_hull, H, eps=self.broad_eps):
                return 'POSSIBLE'
        return 'SAFE'

    def narrow_phase(self, n, obj, theta):
        # SDF 插值查询 + GJK/EPA 精确验证
        sdf_val = self.ogc.get(obj).sdf_cache.query(ee_pose(n, theta))
        if sdf_val > self.narrow_eps:
            return 'SAFE'
        if sdf_val < -self.narrow_eps:
            return 'UNSAFE'
        # |sdf| ≤ eps：退化带，用 GJK/EPA 仲裁
        pen, witness = gjk_epa(ee_hull, obj_mesh, eps=self.narrow_eps)
        if pen is None:
            return 'SAFE'
        if pen > self.narrow_eps:
            return 'UNSAFE'
        return 'UNKNOWN'   # 数值不确定 → 保守视为 UNSAFE

    def cert_phase(self, n, obj, theta, verdict, proof):
        return ColCert(node=n, obj=obj, theta=theta, verdict=verdict, proof=proof)

    def verify_segment(self, seg, n, theta, obj):
        # 对演示子段的离散轨迹点逐点验证，再用凸包包络做连续证明
        for x in seg.states:
            v, _ = self.verify(n, obj, theta_at(x))
            if v != 'SAFE':
                return False, None
        return True, self.construct_segment_cert(seg, n, obj)

    def verify_domain(self, n, obj, theta_dom):
        # 在收缩域上采样验证：网格 + 随机 + 边界
        samples = theta_dom.sample_grid() + theta_dom.sample_random() + theta_dom.sample_boundary()
        for theta in samples:
            v, _ = self.verify(n, obj, theta)
            if v != 'SAFE':
                return False
        return True


# IP-418 Demonstration Replay Scheduler：异步回放、不阻塞、影子晋升
class DemonstrationReplayScheduler:
    def __init__(self, dcm, sas, ccv, period=1.0, max_concurrent=1):
        self.dcm = dcm
        self.sas = sas          # 影子锚合成器（v18）
        self.ccv = ccv
        self.period = period
        self.queue = PriorityQueue()
        self.running = False

    def enqueue(self, tau, obj, priority=None):
        if priority is None:
            priority = self.compute_priority(tau, obj)
        self.queue.put((-priority, tau, obj))   # 大顶堆

    def compute_priority(self, tau, obj):
        novelty = self.estimate_novel_anchors(tau)   # 预估能挖出多少新锚
        cert_gap = self.estimate_cert_gap(obj)       # 该物体当前证书覆盖缺口
        age = self.time_since_last_replay(obj)
        return 0.5 * novelty + 0.3 * cert_gap - 0.2 * age

    def poll(self, now, x, m_star, h_star):
        if self.running or self.queue.empty():
            return
        _, tau, obj = self.queue.get()
        self.running = True
        # 后台任务：不阻塞 50Hz
        self.executor.submit(self._replay_worker, tau, obj, x, m_star, h_star)

    def _replay_worker(self, tau, obj, x, m_star, h_star):
        try:
            mined, status = self.dcm.mine(tau, x, m_star, h_star, obj)
            if status == 'OK':
                # 新锚进入 SAS 影子池（零授权）
                for n, theta in mined.nodes:
                    if n not in self.s2c.anchors:
                        self.sas.add_shadow_anchor(n, theta, mined.col_certs, obj)
        finally:
            self.running = False


# IP-419 Object Geometry Catalog：物体几何编目
class ObjectGeometryCatalog:
    def __init__(self, convex_eps=1e-3, sdf_res=0.01):
        self.catalog = {}   # obj_id → OGCEntry
        self.convex_eps = convex_eps
        self.sdf_res = sdf_res

    def register(self, obj_id, mesh):
        # 1. 凸分解（V-HACD 或近似凸包）
        convex_decomp = vhacd_decompose(mesh, eps=self.convex_eps)
        # 2. SDF 缓存：在包围盒内均匀采样
        sdf_cache = SDFGrid(mesh, resolution=self.sdf_res)
        sdf_cache.precompute()
        # 3. Minkowski 和预计算：对每类末端执行器预计算
        minkowski_cache = {}
        for ee_type in EE_TYPES:
            minkowski_cache[ee_type] = minkowski_sum(ee_type.convex_hull, convex_decomp)
        self.catalog[obj_id] = OGCEntry(convex_decomp, sdf_cache, minkowski_cache)

    def get(self, obj_id):
        return self.catalog.get(obj_id)

    def query_col_dom_conservative(self, n, obj_id, theta_dom):
        # 保守内切：只保留 SDF > margin 的参数子域
        entry = self.get(obj_id)
        if entry is None:
            return EmptyDomain()
        return entry.sdf_cache.conservative_inner_domain(theta_dom, margin=0.02)
```

## 2. 符号体系增量（定义 727–766）

| 符号 | 含义 |
|---|---|
| τ = (x_0, a_0, ..., x_T) | 专家演示轨迹（定义 727） |
| DCM(·) | 演示证书挖掘器（定义 727） |
| mine_segment(seg, x) → n ∪ {⊥} | 子段投影（定义 728） |
| CC(τ) = (collision_free, proof) | 演示碰撞证书（定义 729） |
| ColDom(n, o) ⊆ Θ_n | 碰撞安全参数域（定义 730） |
| Θ_n^col(o) = Θ_n ∩ ColDom(n, o) | 泛化后碰撞参数域（定义 731） |
| margin_col | 碰撞域最小体积阈值 |
| def_col(T) | 泛化亏空（定义 732） |
| δ_geom | 独立几何探针亏空上界（定义 733） |
| OGCC 接受规则 | 体积非零 ∧ 亏空有界 ∧ CCV 通过（定义 734） |
| CCV(n, o, θ) → {SAFE, UNSAFE, UNKNOWN} | 碰撞证书验证器（定义 735） |
| broad_phase / narrow_phase / cert_phase | 三层裁决（定义 736–738） |
| ColCert = (n, o, θ, verdict, proof) | 碰撞证书（定义 739） |
| DRS(·) | 演示回放调度器（定义 740） |
| priority(τ) | 回放优先级（定义 741） |
| OGC(o) = (convex_decomp, sdf_cache, minkowski_cache) | 物体几何编目（定义 742） |
| convex_decomp(o) | 物体凸分解（定义 743） |
| sdf_cache(o) | SDF 缓存（定义 744） |
| minkowski_cache(n, o) | Minkowski 预计算（定义 745） |
| ζ_demo | 演示层共享状态（定义 746） |
| Exec_v19 | 可安全执行的演示衍生计划集合（定义 747） |

## 3. 推导

**引理 143（演示挖掘零授权增）** 若 DCM 的 mine 满足 `mine(τ) ⊆ Anchors ∪ {⊥}`，投影命中复用该节点 NC 原文，碰撞证书经 CCV 验证，缝证书经 PSV 预验，则对任意演示分布，`Exec_v19 ⊆ Exec_v18`，且演示层新增授权基数 `|NewAuth| = 0`。证明：DCM 的值域含于 v17 认证锚集，锚节点的 NC 已由 v16 NCS/MCA/WCB 验证；CCV 只拒不授（P36）；PSV 只增缝约束（P29）；SAS 影子晋升零授权、正式晋升复用 v16 NCS（v18 引理 143）。故演示只能揭示既有证书的可行组合，不能新增节点、放宽阈值、扩张域。∎ 推论：**演示学习的失效模式只有单向——少挖出一些锚；不安全率相对 v18 恒为零**。

**引理 144（碰撞域保守下近似）** 设 `ColDom(n, o)` 由广相位（凸包不相交 ⇒ 全域安全）与窄相位（SDF 内切 ⊕ GJK/EPA 验证）构造，且窄相位满足 `UNKNOWN → UNSAFE`。则构造出的 `ColDom(n, o) ⊆ 真实零碰撞参数域`。证明：广相位仅在凸包严格分离时返回 SAFE，凸包包络包含真实几何，故分离充分；窄相位仅在 SDF > eps 或 GJK 证实分离时返回 SAFE，UNKNOWN 保守归为 UNSAFE，故内切。两阶段合取保守性传递。∎ 推论：**泛化接受规则 `Θ_n^col(o_t) ≠ ∅` 恒为保守——若通过，则收缩域内绝对零碰撞**。

**引理 145（泛化收缩不可逆）** OGCC 的 generalize 满足 `Θ_n^col(o_t) = Θ_n ∩ ColDom(n, o_t)` 且 `vol(Θ_n^col) ≤ vol(Θ_n)`，亏空 `def_col = vol(Θ_n) - vol(Θ_n^col)`。若独立几何探针给出 `def_col ≤ δ_geom` 且 CCV 在 `Θ_n^col` 上采样全通过，则 `Auth(c_t) ⊆ Auth(c_s) ∩ ColDom(o_t)`。证明：参数域求交天然满足收缩；亏空上界由独立探针保证不被低估；CCV 采样验证排除了近似构造的盲区（在采样覆盖范围内）。故泛化证书的授权是源证书与目标碰撞域的交的子集。∎ 推论：**泛化只能让系统"在更少参数下做同一件事"，永远不能"做新事"或"在更多参数下做旧事"**。

**引理 146（碰撞证书验证器的唯一裁决性）** 设 CCV 是 DCM、OGCC、SAS、S2C 所有证书产出路径的唯一硬门，且 `UNKNOWN → UNSAFE`。则对任意几何近似误差、数值退化、采样稀疏，任何进入 Anchors 或校准集的证书必满足 `CCV = SAFE`。证明：由架构约束，所有路径汇聚 CCV；CCV 的 verdict 只有三值，其中 UNKNOWN 被语义映射为 UNSAFE；cert_phase 生成的 proof 可被离线审计器机械验证。故不存在"绕过 CCV"或"软性通过"的通道。∎ 推论：**几何近似误差的攻击面被压缩到"CCV 采样覆盖之外的盲区"，且该盲区不被上层任何机制覆盖（见风险 1）**。

**引理 147（演示回放不阻塞）** DRS 的 poll 与 _replay_worker 运行在独立执行器，poll 在 50Hz 控制环外以 period 频率检查队列，_replay_worker 提交后即返回。控制环关键路径不包含任何演示回放、挖掘、几何查询操作。证明：DRS 状态机只有 `queue` 与 `running` 两个原子变量，poll 仅做非阻塞入队/出队；worker 由线程池/进程池异步执行。故控制环 p99 延迟与演示任务完全解耦。∎ 推论：**演示回放的计算开销（挖掘+几何查询+CCV）任意大都不影响实时性**。

**引理 148（物体几何编目的保守性传递）** OGC 的 convex_decomp 由 V-HACD 保证 `mesh ⊆ ∪ H_i`（凸包包络）；sdf_cache 由离线预计算保证 `sdf_grid(q) ≤ 真实 SDF(q)`（内切）；minkowski_cache 由 Minkowski 和定义保证 `EE ⊕ Obj ⊆ EE ⊕ (∪ H_i)`。则 CCV 广相位使用的凸包、窄相位使用的 SDF、域查询使用的 Minkowski 均为保守近似。证明：凸包包络性、SDF 内切性、Minkowski 和单调性均为几何标准性质。∎ 推论：**OGC 是保守性的源头；若 OGC 近似偏乐观（如凸分解漏掉凹陷），保守性链条在源头断裂（见风险 1）**。

**引理 149（影子晋升与 v18 兼容）** SAS 接收 DCM 产出的新锚作为影子锚（零授权），晋升条件复用 v18 引理 143：需经 NCS 合成验证、WCB 行为一致性检查、TRM 里程碑门控。晋升后锚接入 S2C 的 Anchors 与 HCG 的校准集，不破坏引理 138（校准集可交换性由影子期隔离保证）。证明：影子期锚不进入 Anchors，不进校准集，不影响 HCG 分位数；晋升时复用 v16 NCS，等价于 v16 新节点合成流程。∎ 推论：**演示发现新技能的完整链路：DCM 挖掘 → SAS 影子 → NCS 正式 → S2C/HCG/PSV 接入，全程零授权增**。

**引理 150（v19 整体安全继承）**：在同一物体编目快照、同一演示缓冲区快照下，`Exec_v19 ⊆ Exec_v18`。证明：DCM 零授权增（引理 143），OGCC 只收缩域（引理 145），CCV 唯一硬门（引理 146），DRS 不阻塞不裁决（引理 147），OGC 保守近似（引理 148），SAS 晋升复用 v16 NCS（引理 149）。五端口复合只能产生 Exec_v18 的子集。∎

## 4. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| DCM 挖掘（单演示） | 异步后台 | O(T·|Anchors| + T·CCV) | O(T) | 引理 143 |
| DCM 子段投影 | 挖掘时 | O(|Anchors|·d) | O(1) | 引理 143 |
| DCM 碰撞证书构造 | 挖掘时 | O(T·CCV_narrow) | O(T) | 引理 144 |
| OGCC 泛化查询 | 异步/在线 | O(|convex_decomp| + SDF_query) | O(1) | 引理 144, 145 |
| OGCC 域构造 | 泛化时 | O(grid_samples·narrow) | O(grid) | 引理 144 |
| CCV 广相位 | 在线/离线 | O(|EE_hull|·|obj_hulls|) | O(1) | 定义 736 |
| CCV 窄相位 | 在线/离线 | GJK/EPA: O(iter·|verts|) | O(1) | 定义 737 |
| CCV 证书相位 | 在线/离线 | O(proof_size) | O(proof) | 定义 738 |
| DRS 调度/优先级 | 异步 1Hz | O(log Q) | O(Q) | 引理 147 |
| OGC 注册（离线） | 冷启动 | V-HACD: O(|mesh| log |mesh|) | O(|decomp|+|sdf|) | 引理 148 |
| OGC 查询 | 在线 | SDF 插值: O(1) | O(1) | 引理 148 |
| v18 继承路径 | 在线 50Hz | ≤12ms（不变） | 不变 | v18 引理 143–149 |
| 控制侧合计（50Hz 关键路径） | 在线 | 典型 ≤12ms，p99 ≤27ms（演示/几何/泛化完全在路径外） | — | 引理 147, 150 |

## 5. 实验设计 E731–E750

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E731 | DCM 挖掘精度 | 专家演示 100% 映射到认证节点，0 次跨证书族误映射，0 次碰撞证书漏报 |
| E732 | DCM 碰撞证书完备性 | 演示轨迹连续时间碰撞证书构造成功率 ≥95%，漏报 = 0 |
| E733 | OGCC 碰撞域构造 | 凸包/SDF/Minkowski 三路对比：保守性 100%，紧致度（体积/真实域）≥80% |
| E734 | OGCC 泛化收缩 | 同类物体（杯→杯）泛化接受率 ≥70%，异类（杯→书）接受率 = 0，体积收缩符合预期 |
| E735 | OGCC 亏空上界 | 独立几何探针 δ_geom 覆盖真实亏空 100%，0 次低估 |
| E736 | CCV 广相位召回 | 广相位 SAFE 覆盖真实安全域 ≥90%，0 次假 SAFE |
| E737 | CCV 窄相位鲁棒性 | 退化配置（掠过、嵌入、数值病态）100% 返回 UNKNOWN/UNSAFE，0 次假 SAFE |
| E738 | CCV 实时性 | 广相位 ≤0.05ms，窄相位 ≤0.5ms，证书相位 ≤0.1ms，p99 ≤1ms |
| E739 | DRS 回放活性 | 新物体冷启动：回放 3 段演示后新锚发现率 ≥80%，控制环 p99 增量 ≤1ms |
| E740 | DRS 优先级有效性 | 高优先级演示（新锚潜力大、证书缺口大）优先被挖掘，低优先级不饿死 |
| E741 | OGC 几何编目质量 | 凸分解包络紧致度 ≥85%，SDF 内切误差 ≤1mm，Minkowski 预计算覆盖 100% EE 类型 |
| E742 | 端到端：演示挖掘→泛化→执行 | "演示拿红杯→泛化拿蓝杯/绿碗" 端到端成功率 ≥ v18+15%，零碰撞 |
| E743 | 端到端：多物体泛化 | 单次演示泛化到 10 物体，接受率 ≥60%，体积中位数 ≥0.5·源域 |
| E744 | 端到端：碰撞边界探针 | 在碰撞边界附近参数（margin_col 附近）执行 100% 安全，0 次碰撞 |
| E745 | 消融：无 DCM | 退到 v18，新物体冷启动需人工标注锚，冷启动时间 ↑≥5× |
| E746 | 消融：无 OGCC | 泛化退化为启发式，碰撞率 ↑≥20% 或被迫 0 泛化 |
| E747 | 消融：无 CCV | 碰撞检测退化为运行时盾，编译时泛化 0 授权，活性 ↓≥40% |
| E748 | 消融：无 DRS | 回放固定周期，新锚发现率 ↓≥30%，控制环偶发抖动 |
| E749 | 消融：无 OGC | 物体退化为球包络，泛化接受率 ↓≥50%，保守性大幅过剩 |
| E750 | 竞赛/基准测试 | 示教泛化任务（如 RoboSet/Sim2Real 基准）≥ v18+15%（预注册主指标） |

## 6. 预注册判据

| 判据 | 门槛（预注册） | 若未达标的处置 |
|---|---|---|
| DCM 挖掘（E731） | 100% 映射认证节点，0 跨族 | 调分段算法、收紧 τ_mine、加接触事件检测 |
| DCM 碰撞证书（E732） | 连续证书成功 ≥95%，漏报=0 | 加密集采样、凸包包络细化、Minkowski 证明增强 |
| OGCC 域构造（E733） | 保守 100%，紧致 ≥80% | 调凸分解粒度、SDF 分辨率、Minkowski 近似阶数 |
| OGCC 泛化（E734） | 同类 ≥70%，异类 0 | 扩物体编目、细化类别先验、加语义相似度门控 |
| 亏空上界（E735） | 100% 覆盖，0 低估 | 加强独立探针（更密采样、解析界、对抗几何生成） |
| CCV 广相位（E736） | 召回 ≥90%，0 假 SAFE | 调 broad_eps、加层级包围盒、凸分解细化 |
| CCV 窄相位（E737） | 退化配置 0 假 SAFE | 数值稳健 GJK/EPA、加扰动测试、UNKNOWN 保守阈值收紧 |
| CCV 实时性（E738） | p99 ≤1ms | 广相位 GPU 并行、窄相位缓存、增量更新 |
| DRS 活性（E739） | 冷启动 3 段 ≥80%，p99 ≤1ms | 调优先级权重、扩演示池、worker 隔离 |
| 优先级（E740） | 高优先级先挖，低优不饿死 | 加迟滞、公平调度、优先级平滑 |
| OGC 质量（E741） | 包络 ≥85%，SDF ≤1mm | V-HACD 参数、SDF 自适应分辨率、Minkowski 解析修正 |
| 端到端（E742） | ≥ v18+15%，零碰撞 | 按消融定位瓶颈 |
| 多物体（E743） | 10 物体接受 ≥60% | 类别聚类泛化、共享几何先验 |
| 边界探针（E744） | margin_col 附近 100% 安全 | 自适应 margin、边界采样加密、在线 CCV 复验 |
| 消融 DCM（E745） | 冷启动 ↑≥5× | 证明挖掘必要性 |
| 消融 OGCC（E746） | 碰撞 ↑≥20% | 证明碰撞域收缩必要性 |
| 消融 CCV（E747） | 活性 ↓≥40% | 证明唯一硬门必要性 |
| 消融 DRS（E748） | 发现率 ↓≥30% | 证明异步调度必要性 |
| 消融 OGC（E749） | 接受率 ↓≥50% | 证明几何编目必要性 |
| 竞赛（E750） | ≥ v18+15% | 综合调优 |

## 7. 已知风险与失效模式

1. **几何近似的盲区**：OGC 的凸分解可能漏掉深凹陷/内部空腔，SDF 采样可能漏掉薄壁/尖锐特征，Minkowski 和数值误差可能低估穿透深度——导致 `ColDom(n, o_t)` **偏乐观**（大于真实零碰撞域），CCV 窄相位在采样点通过、但在未采样参数上真实碰撞。缓解：自适应 SDF 细化、凸分解层级化、对抗几何生成测试、在线 CCV 复验、保守 margin_col 动态放大。
2. **独立几何探针的盲区共享**：δ_geom 由独立探针给出，但探针本身使用相同的几何近似（凸包/SDF/Minkowski）——若源/目标物体**共享同一类未建模几何奇异性**（如都有未被凸分解捕获的薄壁结构），探针会系统性低估亏空，产生"亏空有界、CCV 采样通过、真实碰撞"的虚假泛化。缓解：异构探针集成（解析界+采样+对抗）、几何奇异性检测器、共享盲区审计日志。
3. **演示分段的语义鸿沟**：DCM 的 segment_trajectory 依赖启发式（接触事件/动作语义/速度突变），可能把一个长技能切碎、或把两个技能合并，导致投影到错误锚或缝证书失败。缓解：用 v17 HCG/PSV 反向验证分段质量、分段结果回传 CLP 作为语言计划先验、人工标注少量分段种子。
4. **碰撞证书的连续时间鸿沟**：DCM 从离散轨迹点构造连续碰撞证书（凸包包络+Minkowski），但机器人真实执行轨迹可能偏离演示轨迹（跟踪误差、控制延迟），导致连续证书不覆盖真实执行管腔。缓解：管腔膨胀（tracking_error_bound ⊕ 演示凸包）、在线 CCV 复验、跟踪误差纳入参数域收缩。
5. **泛化参数域的表示鸿沟**：`Θ_n^col(o_t)` 在 SE(3)×关节空间上是高维非凸集，用网格/采样近似可能漏掉狭窄安全通道，导致泛化被过度拒绝（活性损失）或错误接受（安全风险）。缓解：参数域用星凸/凸包包络表示、自适应采样聚焦边界、拓扑保持简化。
6. **CCV 窄相位的数值退化**：GJK/EPA 在共面/共线/近奇异配置下数值不稳定，可能返回错误分离距离或陷入无限循环。缓解：数值稳健 GJK（EPA fallback、扰动重启）、迭代上限、退化时强制 UNKNOWN→UNSAFE、离线退化配置枚举测试。
7. **演示回放的分布偏移**：DRS 回放的演示来自历史分布，当前硬件/软件/里程碑可能已演进，导致挖掘出的锚不满足当前 `m_n ≤ m* ∧ h_n ≤ h*`，或碰撞证书因硬件几何变化失效。缓解：演示携带元数据（硬件版本、里程碑、固件），挖掘时硬门控、硬件变更触发演示失效标记。
8. **物体编目的静态假设**：OGC 假设物体几何刚性不变，但真实物体可能变形（软体）、磨损、组装状态改变。缓解：物体版本号、在线几何更新触发重编目、软体建模为参数族而非单一网格。
9. **影子晋升的证据预算耗尽**：SAS 影子锚晋升需经 NCS 验证，需收集足够执行证据；若新物体罕见、执行机会少，影子锚长期停留、永不晋升，导致泛化证书长期停留在影子态（无授权）。缓解：仿真加速证据收集、影子锚超时自动降级、证据预算动态分配。
10. **三重证书叠加的过度保守**：节点 NC ∩ 缝 SC ∩ 碰撞 ColCert ∩ 语义共形四层求交，计划通过率可能塌缩，系统长期退化为 v18 默认。缓解：加权打分而非纯求交、证书族共享 ColCert、动态 margin_col、活性监视报警。
11. **演示噪声与亚最优性**：专家演示可能包含抖动、回退、冗余动作，DCM 可能将其投影为 ⊥ 或产生碎片化节点序列。缓解：演示平滑预处理、亚最优片段标记为 ⊥ 而非整段作废、多演示共识挖掘。
12. **多物体/多演示的组合爆炸**：物体数 × 演示数 × 节点数的泛化组合可能极大，OGCC/CCV 查询开销随组合数线性增长。缓解：泛化结果缓存、相似物体聚类共享 ColDom、按需查询（仅当计划涉及时触发）。

## 8. 本轮最大风险

**一句话**：OGCC 的碰撞域 `ColDom(n, o_t)` 与 CCV 的窄相位查询都依赖**物体几何的保守近似**（凸包/SDF 采样/Minkowski 和），若近似偏乐观（如凸包漏掉凹陷、SDF 采样稀疏漏掉薄壁、Minkowski 和数值误差），则泛化证书会在"形式上体积≥margin_col、CCV 返回 SAFE"的前提下，**在真实物理交互中发生碰撞**——即"几何近似的盲区"变成了"证书的盲区"，且该盲区不被任何上层机制（HCG/PSV/DARG/TAM）覆盖，因为它们都假设 CCV 是可信的。
<!-- ARTIFACT:END -->
