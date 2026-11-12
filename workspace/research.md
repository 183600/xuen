# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。
<!-- IDEA:START -->
# 第 59 轮（承接第 58 轮「KG-SFT-UX」IP-139~144；灵感循环第 1 轮；本轮灵感：「碰撞检测」×「Isaac Sim」）

> 第 58 轮把安全论证架在结构化记忆 𝒢 上，同时自陈了它的共模风险：KG 若存在系统性结构错误，会同时污染检索、OOD、微调、证据合成与心智预测。本轮两个灵感从「几何」和「仿真」两侧各捅了同一层窗户纸。**碰撞检测**是机器人学里最成熟的「宁可保守、不可漏检」机器：broad-phase/narrow-phase、保守推进、连续碰撞检测（CCD）、有符号距离场（SDF）、安全裕度——它暴露出第 58 轮一个被忽略的隐含假设：**证据门只在离散检查点上被求值，而物理安全活在整条连续轨迹上**；检查点之间的薄壁、快速摆动与可变形体可以「隧穿」一次点证据。**Isaac Sim** 是当代最廉价的反事实引擎：GPU 并行 rollout、PhysX 5、USD 场景图、域随机化、逼真传感器——它暴露出相反的假设：**仿真是一个模型，模型内的「无碰撞/物理一致」不等于世界的「无碰撞/物理一致」**；同一引擎的所有 rollout 共享同一份物理偏差（单引擎共谋），域随机化也只覆盖它声明的支撑集。本轮把命题从「结构化记忆守护下的证据承诺」升级为 **「连续可证、分层保守、仿真可对账的物理证据承诺」**：安全从检查点布尔谓词变成扫掠轨迹上的带符号安全距离下界；用分层碰撞检测决定「哪里值得花精算预算」；用 Isaac Sim 做反事实探针的**提议器**，但仿真证据必须与真实残差共形对账，且永不进入不可逆接触必要证据集。

核心矛盾：
- **H29（离散检查 vs 连续越界）**：点证据只说「此刻安全」，不说「到下一检查点之前安全」；薄壁、高速摆动、可变形地面会在两次采样之间隧穿。把检查加密到足够细可缓解，但验证预算与实时性不允许；用保守界覆盖整段轨迹又会过度保守、导致「安全到无法行动」。
- **H30（碰撞检测器 vs 世界）**：碰撞检测的「无碰撞」永远是相对于一个几何模型的断言——凸分解会填平凹槽、碰撞边距会放大物体、离散步进会漏掉薄物、透明/可变形/柔性体没有干净网格。**证书的可靠性不超过几何模型的可靠性**，这与第 57 轮「证据的可靠性不超过先验」同构。
- **H31（仿真证据 vs 现实）**：Isaac Sim 能给出海量反事实，但同一物理引擎的偏差被所有 rollout 共享——把同一引擎跑一万遍，只是把同一个偏差问一万遍；域随机化把「参数扰动下的稳健」误读成「现实中的安全」，而真实分布可能落在随机化支撑集之外。
- **H32（分层剪枝 vs 零漏检）**：broad-phase 靠保守包围体省算力，代价是必须**零假阴性**；一个错误的包围体或失效的 Lipschitz 界会把「真碰撞」剪成「安全」。剪枝越激进，单点几何错误被放大的范围越大。

## 0. 直觉与动机

**灵感 1（碰撞检测 → 扫掠证据与保守推进）**
直觉：只在检查点检查碰撞，就像只在电影关键帧检查演员有没有穿墙。碰撞检测的答案是**扫掠体与连续碰撞检测**：把整段运动 [0,T] 的机器人扫掠体积与障碍求交，并用保守推进（conservative advancement）给出一个**可证明的下界**——若在 t 时刻最近距离为 d、最近点相对速度上界为 L，则至少可以安全推进 d/(L+ε) 而不发生接触。映射到本体系：证据门不应只回答「位姿 q_k 是否安全」，而应回答「调度 σ 的整条轨迹是否满足 min_t s_σ(t) ≥ δ_sweep」，其中 s_σ 是带符号安全距离（正=分离，负=穿透）。但几何模型是新的先验：证书必须携带**几何溯源**（真实深度/触觉重建 vs 仿真网格）与**几何不确定半径**，真实几何才可支撑不可逆接触。

**灵感 2（分层碰撞检测 → 证据级联与预算分配）**
直觉：碰撞检测的快来自「便宜的保守粗筛 + 只在边界附近才做昂贵精算」：broad-phase 用 AABB/BVH/SDF 下界，narrow-phase 用 GJK/EPA 求精确穿透深度。它的正确性契约是不对称的——**broad-phase 允许假阳性（多说危险），绝不允许假阴性（漏说危险）**。这正好是证据预算的正确花法：先用廉价证书扫整条路线，只有当保守下界落进裕度带 θ_narrow 时才升级到真实探针/精确几何。于是「在哪里花探针」从启发式变成**由可证明的几何下界驱动**：远离边界的地方不需要探针，贴边的地方才值得。

**灵感 3（Isaac Sim → 反事实探针引擎与仿真证据类）**
直觉：真实接触不可逆且昂贵，而 Isaac Sim 可以在接触前把成千上万条候选轨迹在随机化物理参数下跑一遍，告诉你「哪一条最可能撞、哪一个探针最能区分」。但仿真只能做**提议器**，不能做**判据**：把仿真结果作为 EV-sim 之前，必须先在「仿真与真实都观测过的探针」上估计 sim-real 残差，并用共形分位把它变成偏差球——只有决策裕度大于偏差球时，仿真结论才有资格作为 L1 证据；一旦观测动力学落在域随机化支撑集之外，立即 OOD 退回真实探针。多引擎/解析模型交叉检查用于打破单引擎共谋。

**灵感 4（数字孪生 → KG 的物理一致性校验器）**
直觉：Isaac Sim 的 USD 场景图是几何真值的结构化表示，第 58 轮的 KG 是语义真值的结构化表示。两者对齐后，碰撞检测可以反过来当 KG 的**物理一致性 oracle**：若 KG 断言「该表面可通行/与邻区相似」，而数字孪生里按同一调度做 CCD 得到穿透，则产生一次矛盾事件——要么语义边错、要么几何/对齐错。高对齐置信度下的矛盾触发 KG 边回溯；低置信度下只标记不确定，不贸然删知识。这把第 58 轮「仅证据门可写入」补成了「写入后仍可被物理反证」。

**灵感 5（合流 → 证据门从六类到八类、从点证据到扫掠证据）**
直觉：第 58 轮六类证据门 EV-probe*/visit/margin/xmodal/human/ft/ux 都是「点/片段证据」。本轮新增 **EV-swept**（真实几何支撑的连续扫掠证书）与 **EV-sim**（经 sim-real 对账的仿真反事实，仅 L1）。不可逆接触必要证据集升级为 `{EV-probe* ∨ EV-margin ∨ EV-swept_real} ∧ 佐证`，显式排除 EV-sim、EV-xmodal、EV-ft、EV-ux。击穿安全需要：点证据错 ∧ 扫掠界失效 ∧ broad-phase 漏检 ∧ 几何模型系统性错误 ∧ sim-real 对账失效 ∧ 人错——纵深从五层到七层。

## 1. 形式化定义（增量：定义 145–150）

**定义 145（扫掠证据证书 SEC）** 调度 σ 在 [0,T] 上的机器人扫掠体 𝒮_σ(t)=R(q(t))⊕B_{r_infl}；带符号安全距离 s_σ(t)=sd(𝒮_σ(t),𝒪)，sd>0 为分离。保守推进：若在 t_i 处 d_i=s_σ(t_i)，最近点相对速度上界为 L_i，则对任意 Δt≤d_i/(L_i+ε) 有 s_σ(t_i+Δt)≥0；对整条轨迹取 `\underline{s}_σ = min_i (d_i − L_i·Δ_i)` 得可证明下界。证书 `C_sw=( \underline{s}_σ, provenance, geom_version, r_geom, L_max, δ_sweep, T)`，其中 provenance∈{real_depth, real_tactile, sim_usd, hybrid}，r_geom 为几何共形不确定半径。EV-swept ⇔ `\underline{s}_σ ≥ δ_sweep = δ_margin + κ_g·r_geom`；provenance≠real 时仅可作 L1 证据。

**定义 146（分层碰撞证据级联 LCEC）** 三级：①broad-phase 用包围体/SDF-Lipschitz 下界 `\underline{s}_B(t) ≤ s_σ(t)`（**构造性保守**，零假阴性是硬约束）；②若 `\underline{s}_B ≥ δ_sweep` 全轨迹通过，直接签 SEC，不花窄相；③若 `\underline{s}_B < θ_narrow`（进入裕度带），升级 narrow-phase 求精确 `s_σ` 与穿透深度，再判 SEC。预算 `B_coll = c_B·|σ| + c_N·N_near`，N_near 由 θ_narrow 控制。契约：broad-phase 假阳性可接受（多花窄相），假阴性不可接受（漏报碰撞）；Lipschitz 界与包围体必须带版本与审计。

**定义 147（仿真-现实对账 SRR）** Isaac Sim 由物理参数 θ_sim（摩擦/质量/恢复系数/网格/时延/接触模型）参数化，域随机化分布 Θ_sim。对候选调度做 N 次 GPU 并行 rollout 得 `O_sim(σ)={o_i}`。在「仿真与真实共同观测过的探针集」上计算残差 `r_sr=d(o_sim,o_real)`，共形分位 `q_sr(α_sim)` 给出偏差球。EV-sim ⇔ `θ_sim∈support(Θ_sim)`（否则 sim-OOD）∧ `margin_decision(o_sim) > q_sr(α_sim)` ∧ 多引擎/解析交叉检查不反号；仅 L1，且**永不进入不可逆接触必要证据集**。单引擎共谋：同引擎偏差 b_sim 对所有 rollout 同号，故只增加置信度不增加独立信息；独立性只来自不同引擎/解析模型/真实探针。

**定义 148（数字孪生场景图 DTSG）** USD 场景图 `𝒰=(𝒫,ℳ,𝒯)`（prim/mesh/transform），对齐映射 `A: 𝒢_geom ↔ 𝒰` 带锚点置信 `a∈[0,1]`。物理一致性测试：对 KG 断言 e=(h,r,t)（如 similar_to、traversable、deceives_modality）实例化对应调度并在 Isaac Sim 跑 CCD；若 `\underline{s}_σ<δ_sweep` 产生矛盾事件 `κ(e,σ)`。规则：`a≥a_0` 且矛盾可复现 ⇒ 触发 e 的回溯降权/删除；`a<a_0` ⇒ 只记不确定性，不删边（避免几何/对齐错误误杀语义知识）。DTSG 同时为 SEC 提供几何溯源与校准集。

**定义 149（反事实探针调度 CPS）** 仿真先验只用于**提议**真实探针：`VOI_ps(π)=min_{b∈B_sim} E[ΔRisk_swept | do(π), b]`，其中 B_sim 为 sim-real 偏差球；选 `π*=argmax_π[VOI_ps(π)−cost(π)]`，且要求该探针的判别信息不是单纯来自同一引擎重复采样。仿真预算 B_sim 独立于真实探针预算 B_probe，只可重排优先级，不可替代真实接触。若 sim-OOD 或偏差球吞掉决策裕度，CPS 退化为第 58 轮纯真实 VOI。

**定义 150（探-诺-演+++ PCX+++ 与八类证据门）** 每检查点：①KG/数字孪生检索；②元推断；③LCEC 扫掠预检；④对账（xmodal + sim-real）；⑤UX 前置；⑥反事实提议选真实探针；⑦八类证据门。证据类 `EV-probe*/visit/margin/xmodal/human/ft/ux/swept/sim`；不可逆必要集 `{EV-probe* ∨ EV-margin ∨ EV-swept_real} ∧ 佐证`，排除 EV-sim/EV-xmodal/EV-ft/EV-ux。证书 `J_p+++` 继承 J_p++ 并加 `swept_cert, geom_provenance, sim_version, sr_residual, usd_anchor, collision_log, sim_log`。承诺 ⇔ 存在步态 g 使 R≤δ_f(g) ∧ 扫掠证书过 ∧ 证据门过；否则按 VOI_ps 探询→绕行→降档→L2 协商/安全停。

## 2. 关键算法伪代码（完整版见产物区）

```python
def swept_certificate(sigma, geom, T, dt):
    # 保守推进：返回整条轨迹的可证明安全距离下界
    lb, t = +inf, 0.0
    while t < T:
        d = signed_distance(swept_volume(sigma, t), geom)
        L = velocity_bound(sigma, t, geom) + EPS
        lb = min(lb, d - L * dt)
        if d <= 0: return SweptCert(lb, provenance=geom.provenance, ok=False)
        t += max(dt, d / L)          # 自适应推进
    return SweptCert(lb, provenance=geom.provenance,
                     ok=(lb >= delta_sweep + kappa_g * geom.r_geom))

def layered_collision_cascade(sigma, geom, theta_narrow):
    if broad_phase_lower_bound(sigma, geom) >= delta_sweep:
        return swept_certificate(sigma, geom)          # 粗筛直接过
    return narrow_phase_sweep(sigma, geom)             # 只在裕度带精算

def sim_real_reconcile(sim_rollouts, real_residuals, theta_sim_support):
    if not in_support(sim_rollouts.params, theta_sim_support):
        return SimEvidence(ok=False, reason='sim_ood')
    q = conformal_quantile(real_residuals, alpha_sim)
    if decision_margin(sim_rollouts) <= q:
        return SimEvidence(ok=False, reason='bias_ball_swallows_margin')
    if cross_engine_disagrees(sim_rollouts):
        return SimEvidence(ok=False, reason='engine_collusion_suspect')
    return SimEvidence(ok=True, q_sr=q, level='L1')
```

## 3. 复杂度与正确性（要点）

| 组件 | 时间 | 空间 | 正确性关键 |
|---|---|---|---|
| SEC | O(\|σ\|·N_adv·d_sd) | O(\|𝒪\|+几何索引) | 保守推进界有效、Lipschitz 诚实、几何半径保守 |
| LCEC | 粗筛 O(\|σ\|·log\|𝒪\|)；窄相仅 N_near | O(BVH/SDF) | broad-phase **零假阴性**、假阳性可容忍 |
| SRR | O(N·d_sim)/批量（GPU 并行） | O(N·d_o) | sim-real 覆盖 ≥1−α_sim、支撑集 OOD 诚实 |
| DTSG | O(\|𝒢_v\|+\|𝒰_v\|) 对齐 | O(\|𝒫\|+\|ℳ\|) | 锚点置信诚实、低置信不误删边 |
| CPS | O(\|Π\|·(C_sim+C_VOI)) | O(\|Π\|) | 仿真只提议、偏差球悲观 |
| PCX+++ | O(\|CP\|·(k_p+k_c+k_sim+k_ft+k_ux)·(C_VOI+d_GNN)+\|CP\|·A\*) | O(\|V\|+\|σ\|+\|𝒢\|+\|𝒰\|) | 八类门硬禁令、四态完备、预算单调 |

**正确性定理（Swept-Collision Physical Soundness, SCPS 概要）**：在 A22–A45 上加 (A46) SEC：保守推进下界有效、Lipschitz 界与几何共形半径诚实；(A47) LCEC：broad-phase 构造性保守、零假阴性，窄相精确到 ε_narrow；(A48) SRR：sim-real 共形覆盖 ≥1−α_sim、域随机化支撑集 OOD 诚实、偏差球不缩水；(A49) DTSG：锚点置信诚实、低置信矛盾不删边；(A50) CPS：仿真只提议、VOI 对偏差球取悲观。则：(i) 扫掠健全性：EV-swept 通过 ⇒ 真实轨迹接触概率 ≤δ_sweep+δ_geom+δ_num；(ii) 不可逆承诺失效率 ≤δ_f+ε_meta+δ_probe+ε_h+δ_sweep+δ_geom，EV-sim 仅经 L1 贡献且 ≤δ_sr；(iii) 交互单调性：碰撞/仿真机制只能使信念更准（含加宽）或动作更保守；(iv) 终止性：在 k_probes+k_cons+k_sim+k_ft+k_ux 内终止；(v) 部署界对检查点与连续轨迹取联合界。

## 4. 实验设计 E182–E186

| 实验 | 指标 | 目标 |
|---|---|---|
| E182 扫掠 vs 检查点证据 | 薄壁/可变形/高速摆动场景的隧穿假承诺率；额外计算 | ↓≥80%；≤+20% |
| E183 分层碰撞级联 | broad-phase 假阴性数；剪枝率；总碰撞检测时间 vs 全窄相 | 0；≥90%；↓≥50% |
| E184 sim-real 对账 | sim-real 残差 ECE/覆盖；EV-sim 假自信率；单引擎共谋检出；sim-OOD 检出 | ECE≤0.05、覆盖≥1−α；0；≥90%；≥95% |
| E185 数字孪生一致性 | KG 矛盾检出率；误删边率；回溯时延 | ≥90%；≤1%；≤1 到访 |
| E186 端到端 | 薄壁/透明/可变形场地 vs 第 58 轮：成功率/假承诺率/探针时间/仿真预算 | +10%/↓≥70%/−20%/有界 |

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 几何模型系统性简化（凸分解填凹、薄壁漏检、柔性体无网格） | 高 | 真实几何溯源 + 几何共形半径 + 薄壁/可变形专项测试 + 保守膨胀 |
| broad-phase 漏检被剪枝放大 | 高 | 零假阴性硬约束 + 区间/Lipschitz 证书 + 版本审计 + 定期全窄相抽检 |
| 单引擎共谋 / 域随机化支撑集外 | 高 | 多引擎/解析交叉 + sim-OOD 门 + EV-sim 仅 L1 + 永不入不可逆必要集 |
| 数字孪生对齐错误误删 KG 边 | 中高 | 锚点置信门 + 低置信只记不确定 + 矛盾可复现才回溯 |
| 保守界过紧导致「安全到无法行动」 | 中 | 自适应裕度 + LCEC 只在边界精算 + 可退回第 58 轮点证据路径 |

## 6. 本轮最大风险

**一句话**：本轮把安全的最终证人从「KG 的语义边」换成了「几何模型 + 仿真引擎」的联合假设——碰撞检测的「无碰撞」只是该几何模型内的无碰撞，Isaac Sim 的「物理一致」只是该引擎内的物理一致；若几何模型系统性简化（薄壁、可变形、透明体）或仿真偏差恰好落在域随机化支撑集之外，扫掠证书与 EV-sim 会共同制造一种「连续且仿真一致」的虚假安全感，而 broad-phase 的剪枝会把单点几何错误放大到整条路线；必须以真实几何溯源、broad-phase 零漏检硬约束、sim-real 共形对账、EV-sim 永不进入不可逆必要集四重护栏，宁可退回又慢又保守的真实探针，绝不把「模型里的无碰撞」当成「世界里的无碰撞」。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 59 轮产物 · 创新点清单 v35：PAVE（虚实分账证据承诺×增广不变性证书×仿真可证伪×承重假设审计，EPL×CAA×SVC×LBA×PAE×SAPCE）

> 承接第 58 轮 IP-139~144（KGMM/SFT-KG/UXSE/KGES/ACC/PCX++）、第 57 轮 IP-133~138（MFSL/XMC/PTM/MXI/FSE/PCE+）与第 56 轮 IP-127~132（SMM/PCE/BVK/ISE/TAF/MEC）。第 58 轮把安全论证押在结构化记忆 𝒢 上，最大风险是 KG 共模失效；本轮指出 KG 之所以危险，一半是因为真实接触样本稀缺，而**数据增强**与**仿真训练**这两味「解药」生产的是**证据的影子而非证据本身**。因此本轮把「证据从哪来」提升为一等公民：用**证据血统 DAG**记录每条证据的真实根与生成溯源，用**不变性证书增广代数**约束增广只能先验化/保守化，用**仿真有效域与虚实差证书**给仿真划出「只在域内、只按折扣」的适用域，用**承重假设审计**检查安全论证到底在靠哪几条假设相信，再用**虚实分账证据门**把合成证据硬性挡在不可逆承诺之外。核心命题由「结构化记忆守护下的安全自适应」升级为 **「真实可承诺、合成只收紧、生成器可证伪的虚实分账证据承诺」**。
> IP 编号：IP-145~IP-150（共 6 个），并升级 IP-139/140/143/144 以纳入血统、合成溯源与锚点预算。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-145 | EPL Evidence Provenance Ledger | 新增 | 证据血统 DAG：real/aug/sim 三类、真实根、生成器版本、n_eff、批量回溯与污染微调定位 |
| IP-146 | CAA Certified Augmentation Algebra | 新增 | 不变性证书、乐观/悲观增广不对称、增广球最坏情形、群组共形 |
| IP-147 | SVC Simulation Validity Certificate | 新增 | 有效域 V_S、虚实差 Δ_S、信任折减 τ_S、真实锚点、域外沉默、收缩与回溯 |
| IP-148 | LBA Load-Bearing Assumption Audit | 新增 | 假设消融 g_{¬α}、承重性 λ_α、锚点可区分覆盖、未锚定承重假设禁入 |
| IP-149 | PAE Provenance-Aware Evidence Gate | 新增 | 真实/合成分账、合成单向性、不可逆必要集仅真实、四规则硬禁令 |
| IP-150 | SAPCE Sim-Augment-Probe-Commit-Evolve | 升级 IP-144 | 血统检索、合成先验、锚点调度、real-only 门、四预算耦合、四态完备 |

**升级点**：IP-139 KGMM 增「虚拟子图」与边级 `src∈{real,aug,sim}` 标记，仅 real 边可承重；IP-140 SFT-KG 升级为 **SFT-KG+**，记录训练数据血统、支持按生成器版本回滚受污染检查点；IP-143 ACC 增「群组共形」重载；IP-144 PCX++ 升级为 SAPCE，新增 B_anchor。

## 1. 符号体系增量（定义 145–150）

| 符号 | 含义 |
|---|---|
| `e=(id,y_e,c_e,par(e),g_e,a_e,v_e,anc(e),ℓ_e)` | 证据项：类别/父证据/生成器/算子/版本/锚定/血统折减 |
| `c_e∈{real,aug,sim}` | 真实证据 / 增广证据 / 仿真证据 |
| `Root(e), n_eff(e)=|{r∈Root(e):anc(r)=1}|` | 真实祖先根集合与有效独立样本数 |
| `w(e)=ℓ_e·Π_{path}discount` | 合成证据可用权重；依赖未锚定承重假设时为 0 |
| `retract(g,v)` | 批量软删除生成器 g 的 ≤v 版本全部后代合成证据 |
| `G_a, ε_a, 𝒰_a(x)` | 增广不变群、标签保真风险界、增广球 |
| `a^- / a^+` | 悲观增广（只收紧）/ 乐观增广（须证书、仅先验） |
| `S, V_S⊆Z, Δ̂_S(z), τ_S(z)` | 仿真器、有效域、虚实差估计、信任折减 |
| `A_real, Δ_max, τ_min` | 真实锚点集、允许最大虚实差、最低信任阈值 |
| `𝒜={α_i}, g_{¬α}, λ_α, θ_λ` | 生成器假设集、消融变体、承重性、承重阈值 |
| `U` | 未锚定承重假设集合 |
| `EV-aug, EV-sim` | 新增合成证据类（仅先验/候选/校准/悲观压力） |
| `B_probe, B_anchor, B_sim, B_aug` | 四重预算：真实探针/真实锚点/仿真/增广 |
| `J_p+++` | 扩展证书：provenance_id, lineage_weight, gen_version, sim_envelope_id, sim_gap, anchor_set, load_bearing_assumptions, retracted_gens, aug_cert_id, ft_provenance |

## 2. 关键算法伪代码

### IP-145 EPL（证据血统账本）

```python
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class Evidence:
    id: str
    payload: dict
    cls: str                 # 'real' | 'aug' | 'sim'
    parents: list            # 血统父节点
    gen: str | None          # 生成器/仿真器版本；real 为 None
    op: str | None           # 增广算子
    version: int
    anchored: bool           # 根是否为真实锚点
    lineage_weight: float    # ℓ_e ∈ [0,1]

class EvidenceProvenanceLedger:
    def __init__(self, kg):
        self.kg = kg
        self.items = {}
        self.children = defaultdict(set)
        self.gen_index = defaultdict(set)     # gen -> evidence ids
        self.ft_runs = []                     # 微调血统记录
        self.blocked_gens = set()             # 被 LBA/回溯封禁的生成器

    def add(self, e: Evidence):
        assert e.cls == 'real' or e.parents, "synthetic must have a real root"
        self.items[e.id] = e
        for p in e.parents:
            self.children[p].add(e.id)
        if e.gen:
            self.gen_index[e.gen].add(e.id)
        # KG：合成边进虚拟子图，只有 real 边可承重
        self.kg.tag_edge(e, weight=self.effective_weight(e),
                         src=e.cls, gen=e.gen, version=e.version)

    def roots(self, eid):
        seen, stack = set(), [eid]
        while stack:
            i = stack.pop()
            e = self.items[i]
            if e.cls == 'real':
                seen.add(i)
            stack.extend(e.parents)
        return seen

    def effective_weight(self, e):
        if e.cls == 'real':
            return 1.0
        if e.gen in self.blocked_gens:
            return 0.0
        rs = self.roots(e.id)
        if not rs or not any(self.items[r].anchored for r in rs):
            return 0.0
        return e.lineage_weight * min(self.route_discount(e, r) for r in rs)

    def descendants(self, eid):
        out, stack = set(), [eid]
        while stack:
            i = stack.pop()
            for c in self.children[i]:
                if c not in out:
                    out.add(c); stack.append(c)
        return out

    def retract(self, gen, version, reason):
        """事后证伪：批量删除该生成器版本的全部后代合成证据。"""
        doomed = [eid for eid in self.gen_index[gen]
                  if self.items[eid].version <= version]
        for eid in doomed:
            for d in self.descendants(eid):
                self.items[d].lineage_weight = 0.0   # 软删除，保留审计
                self.kg.retract_edge(d, reason='synthetic_retract')
        self.blocked_gens.add(f"{gen}@{version}")
        for run in self.ft_runs:                     # 定位受污染微调
            if gen in run.used_gens and run.gen_version <= version:
                run.contaminated = True
        return doomed
```

### IP-146 CAA（带不变性证书的增广代数）

```python
class CertifiedAugmentation:
    def __init__(self, eps_max=0.02, w_aug_max=0.1):
        self.eps_max, self.w_aug_max = eps_max, w_aug_max
        self.certs = {}

    def certify(self, op, val_set, risk_fn):
        """不变性证书：增广前后风险差的上界。"""
        err = max(abs(risk_fn(op(x), y) - risk_fn(x, y)) for x, y in val_set)
        if err <= self.eps_max and not increases_favorable_evidence(op):
            self.certs[op] = Cert(op, err, group=invariance_group(op))
            return True
        return False

    def apply(self, prior, group, mode, op=None):
        """悲观：只加宽/扩失败集；乐观：须证书，只进先验且权重封顶。"""
        if mode == 'pessimistic':
            # 增广球内最坏情形：只会让安全状态更保守
            return widen_at_least(prior, worst_case_over(op_aug_ball(group)))
        assert mode == 'optimistic' and op in self.certs, "uncertified optimistic aug"
        w = min(self.w_aug_max, self.certs[op].eps / self.eps_max)
        return mixture(prior, op_aug(group), w)

    def group_conformal(self, residuals_by_parent, alpha):
        """群组共形：同一父样本的所有增广只算一个校准单元。"""
        groups = [weighted_mean(v) for v in residuals_by_parent.values()]
        q = weighted_quantile(groups, 1 - alpha)
        return q, len(groups)        # n_eff = #groups ≠ #augmented samples
```

### IP-147 SVC（仿真有效域与虚实差证书）

```python
class SimulationValidityCertificate:
    def __init__(self, sim, delta_max=0.15, tau0=0.9, tau_min=0.3):
        self.sim, self.delta_max = sim, delta_max
        self.tau0, self.tau_min = tau0, tau_min
        self.V = sim.declared_envelope          # V_S
        self.anchors = []                       # (z, y_real, y_sim)

    def in_envelope(self, z):
        return self.V.contains(z)

    def gap(self, z):
        if not self.anchors:
            return float('inf')                 # 无锚点 ⇒ 沉默，不是默认安全
        w = [sim_kernel(z, a.z) for a in self.anchors]
        return weighted_quantile(
            [abs(a.y_real - a.y_sim) for a in self.anchors], 0.9, w)

    def tau(self, z):
        if not self.in_envelope(z):
            return 0.0
        d = self.gap(z)
        return clip(1 - d / self.delta_max, 0, self.tau0) if isfinite(d) else 0.0

    def prior(self, z):
        # 域外或虚差过大 ⇒ 不给先验（沉默），绝不返回自信的错先验
        return self.sim.predict(z) if self.tau(z) >= self.tau_min else None

    def add_anchor(self, z):
        a = Anchor(z, execute_real_probe(z), self.sim.predict(z))
        self.anchors.append(a)
        if self.gap(z) > self.delta_max:
            self.V = self.V.shrink_around(z)    # 收缩有效域
            return Retract(gen=self.sim.gen, version=self.sim.version)
        return None

    def assess(self, c, ledger, lba):
        if not self.in_envelope(c.region) or self.tau(c.region) < self.tau_min:
            return ('reject', 'sim_out_of_envelope')
        if lba.unanchored(self.sim.gen, ledger, c.val_batch):
            return ('reject', 'load_bearing_unanchored')
        return ('ok', c)
```

### IP-148 LBA（承重假设审计）

```python
class LoadBearingAssumptionAudit:
    def __init__(self, assumptions, theta_lambda=0.05, n_anc=3):
        self.A = assumptions          # 可枚举的生成器假设（摩擦/接触/噪声/材质/失效模式）
        self.theta_lambda, self.n_anc = theta_lambda, n_anc
        self.registry = set(assumptions)

    def load_bearing(self, gen, X_val):
        lb = {}
        for a in self.registry:
            g_neg = gen.ablate(a)                 # 去掉/反转假设 a
            lb[a] = mean(tv(gen.predict(x), g_neg.predict(x)) for x in X_val)
        return {a for a, v in lb.items() if v > self.theta_lambda}

    def unanchored(self, gen, ledger, X_val):
        U = set()
        for a in self.load_bearing(gen, X_val):
            # 锚点必须“能区分该假设”：在该假设下真实与仿真可分辨
            if ledger.anchor_count(a, distinguishable=True) < self.n_anc:
                U.add(a)
        if U:
            ledger.blocked_gens.add(gen)          # 未锚定承重 ⇒ 合成证据权重 0
        return U
```

### IP-149 PAE（虚实分账证据门）

```python
def provenance_evidence_gate(c, ledger, sim, lba, region):
    if c.cls == 'real':
        return round58_gate(c, ledger)            # 原有六类真实证据门

    if c.cls == 'aug':
        if not (c.cert_ok and c.group_weighted and
                c.channel in ('prior', 'calib', 'pessimism')):
            return ('reject', 'aug_without_certificate_or_channel')
    elif c.cls == 'sim':
        verdict = sim.assess(c, ledger, lba)
        if verdict[0] != 'ok':
            return verdict
    else:
        return ('reject', 'unknown_evidence_class')

    # 合成单向性硬禁令
    if c.irreversible:
        return ('reject', 'synthetic_on_irreversible')
    if c.counted_as_xmodal_independent or c.replaces_human_corroboration:
        return ('reject', 'synthetic_independence_violation')
    if c.raises_evidence_threshold:
        return ('reject', 'synthetic_may_not_weaken_threshold')
    return ('ok', c)

def admissible_actions(E_real, E_syn, ledger):
    """合成单向性：合成证据只能收缩可接受动作集。"""
    A = real_evidence_admissible(E_real)
    A_syn = perturb_by_synthetic(A, E_syn, ledger)   # 只缩小/加宽
    assert A_syn.issubset(A)                         # 运行时断言（A50）
    return A_syn
```

### IP-150 SAPCE（探-诺-演+++）

```python
def sapce_checkpoint(cp, M, meta, sim, aug, lba, budget):
    # ① 血统检索：real 边承重，合成边进虚拟子图
    E = M.epl.retrieve(cp.region)
    V = M.kg.virtual_subgraph(cp.region)
    assert V.heavy_edges_are_real(), "虚拟边不得承重"

    # ② 合成先验/候选：仿真+certified 增广，只进 prior；悲观增广只收紧
    prior = None
    if sim.in_envelope(cp.region):
        prior = sim.prior(cp.region)
        if prior is not None:
            prior = aug.apply(prior, E, mode='optimistic')
    prior = aug.apply(prior, E, mode='pessimistic')

    # ③ 承重假设审计与锚点调度
    U = lba.unanchored(sim.gen, M.epl, M.val[cp.region])
    while U and budget.anchor_left > 0:
        cands = anchor_candidates(U)
        z = argmax(cands, key=lambda z: voi_anchor(z, U, sim, M) - cost_anchor(z))
        if voi_anchor(z, U, sim, M) < theta_anchor:
            break
        ret = sim.add_anchor(z)
        budget.anchor_spend()
        if ret:
            M.epl.retract(ret.gen, ret.version, reason='sim2real_gap')
            M.sft.rollback_contaminated(ret.gen)
        E = M.epl.retrieve(cp.region)
        U = lba.unanchored(sim.gen, M.epl, M.val[cp.region])

    # ④ 门用 real-only 后验；未锚定承重存在时连先验也不给
    b_real = infer_from_real(E, prior=prior if not U else None, tau=sim.tau(cp.region))
    M.b[cp.region] = b_real

    # ⑤ 跨模态对账：独立性只认真实根
    M, fused, D = xmodal_reconcile(M, cp.region, E, independent_roots_only=True)
    if D > theta_D and 'consensus' not in cp.done:
        p2 = most_disagreeing_real_modality(M, cp.region)
        M, _, D = xmodal_reconcile(M, cp.region,
                                   E + execute_probe(p2, cap=F_abs),
                                   independent_roots_only=True)
        cp.done.add('consensus')

    # ⑥ PAE 证据门
    ev = tag_evidence(cp, E, b_real)
    gate = provenance_evidence_gate(ev, M.epl, sim, lba, cp.region)
    if select_gait(schedule_risk(foothold_schedule(M, cp), M)) != 'halt' and gate[0] == 'ok':
        return commit(cp, M)

    # ⑦ 探询/绕行/降档/L2/安全停
    while budget.probe_left > 0 and select_gait(schedule_risk(...)) == 'halt':
        p = argmax(admissible_real_probes(cp, M, F_abs) + ['anchor'],
                   key=lambda q: voi_provenance(q, M, E, U) - cost(q))
        if p == 'anchor':
            budget.anchor_spend(); sim.add_anchor(pick_anchor(U))
        elif voi_provenance(p, M, E, U) < theta_voi:
            break
        else:
            E = M.epl.add(execute_probe(p, cap=F_abs)); budget.probe_spend()
    return reroute_degrade_or_stop(cp, M, E, gate)
```

### IP-140→SFT-KG+（合成数据血统与污染回滚）

```python
def sft_kg_plus(meta, run, ledger):
    """微调前登记数据血统；证伪后回滚到未污染检查点。"""
    ledger.ft_runs.append(FTRun(
        run_id=run.id,
        used_gens={e.gen for e in run.data if e.gen},
        gen_version=run.max_gen_version,
        base_checkpoint=meta.checkpoint_id,
        data_ids=[e.id for e in run.data],
        contaminated=False,
    ))
    return shadow_finetune_audited(meta, run)

def rollback_contaminated(ledger, gen, version):
    for run in reversed(ledger.ft_runs):
        if run.contaminated or (gen in run.used_gens and run.gen_version <= version):
            meta.restore(run.base_checkpoint)     # 回到未受污染的检查点
            ledger.ft_runs.remove(run)            # 该次微调作废
            log_rollback(run, reason=f"{gen}@{version} falsified")
            return True
    return False
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| EPL | O(\|V\|+\|E\|) 维护；回溯 O(后代数) | O(\|证据\|+\|DAG\|) | 合成必挂真实根、根 n_eff 诚实、批量回溯完备 |
| CAA | O(\|G_a\|·\|X_val\|) 认证；查询 O(1) | O(\|op\|) | 组间可交换、组内权重和≤1、乐观仅先验 |
| SVC | O(\|A_real\|) 虚实差 | O(\|V_S\|+\|A_real\|) | 域外沉默、Δ̂ 覆盖 ≥1−α_gap、收缩即时 |
| LBA | O(m·\|X_val\|)/次审计 | O(m) | 承重假设可枚举、锚点可区分、未锚定即封禁 |
| PAE | O(\|σ\|) | O(\|σ\|) | 合成单向性、不可逆必要集仅真实 |
| SAPCE | O(\|CP\|·(k_p+k_a+k_s+k_g)·(C_VOI+d_φ)+\|CP\|·A*) | O(\|V\|+\|σ\|+\|DAG\|) | 四预算单调、锚点不可被合成替代、四态完备 |

**正确性定理（PAVE Soundness, PAVES）**
假设 A22–A45（第 53–58 轮）成立，并新增：
**(A46) 血统诚实**：每个合成证据至少有一个真实根；`w(e)` 随回溯单调不增；`retract(g,v)` 覆盖 g 的 ≤v 版本全部后代；KG 合成边永不承担承重推理。
**(A47) 增广证书诚实且群组共形**：证书验证集与部署同分布；组间可交换、组内权重和≤1；乐观增广只进 prior，悲观增广只做增广球内最坏情形。
**(A48) 仿真有效域与虚实差诚实**：域外一律沉默；Δ̂_S 的 0.9 分位数覆盖真实偏差的概率 ≥1−α_gap；Δ̂>Δ_max 立即收缩 V_S 并回溯。
**(A49) 承重假设审计完备**：𝒜 覆盖生成器全部影响安全结论的假设；承重 α 若无可区分真实锚点，则依赖它的合成证据权重为 0 且禁入不可逆门。
**(A50) 不可逆分账**：不可逆接触必要证据集只含真实类；合成证据不得计入 EV-xmodal 独立声明或替代 EV-human 佐证。

则：

1. **合成单向性（核心）**：对任意真实证据集 E_real 与合成证据集 E_syn，`A_adm(E_real∪E_syn) ⊆ A_adm(E_real)`。证明要点：合成证据只经三个通道改变信念——(i) 先验/候选：不改变门阈值，只影响搜索顺序；(ii) 群组校准：组内权重和≤1 且认证增广风险漂移 ≤ε_a，故覆盖不升；(iii) 悲观压力：只取增广球内最坏情形，只会加宽。三者均不产生新的真实证据类，故不可逆门判定与 E_syn 无关，可接受集只可能因不确定性加宽而收缩。
2. **真实路径覆盖下界**：未使用合成时退化为第 58 轮界；使用认证增广时 `P(Y∈C) ≥ 1−α−ε_a−δ_anchor`；使用悲观增广时覆盖率单调不降。
3. **证伪可回溯**：若真实锚点判定 g@v 失真，则一个检查点内 `retract(g,v)` 删除全部后代，任何依赖被删证据的后验退回真实共形带最坏值；受污染微调回滚到不含 g@v 的最近检查点，回滚后再次通过第 58 轮审计。
4. **终止性**：SAPCE 在 `k_probes+k_anchor+k_sim+k_aug` 内终止于 {承诺, 绕行, 降档, L2 协商, 安全停}；B_anchor 与 B_probe 受续航硬约束，B_sim/B_aug 不能替代 B_anchor；影子仿真/增广不阻塞主流程。
5. **部署界**（对检查点取联合界）：

```
P_safe ≥ 1 − Σ_cp (δ_f + ε_meta(k) + δ_probe + ε_h + δ_ood·α_conf + δ_xm·1[L1]
                   + δ_ft·1[回滚窗口] + δ_kg·1[检索失败] + δ_ux·1[μ_mis>θ_mis]
                   + ε_a·1[认证增广用于先验] + δ_anchor·1[锚点不足]
                   + δ_gap·1[Δ̂ 低估] + δ_lba·1[承重假设漏审])
         − P(生成器共模未被锚点发现) − P(护盾回退失败) − P(τ_int 超时 ∧ 安全停失效)
```

关键：**血统把「证据」与「影子」分开**（真实根/生成器版本/可回溯）；**增广只做先验与悲观压力**（群组共形 + 不变性证书 + 增广球最坏情形）；**仿真只做域内折扣先验**（V_S/Δ_S/τ_S + 域外沉默）；**承重假设审计决定我们能否相信生成器**（假设消融 + 可区分锚点 + 未锚定即封禁）；**分账证据门保证合成永不越过不可逆线**（合成单向性）。

## 4. 实验设计 E182–E186

| 实验 | 指标 | 目标 |
|---|---|---|
| E182 增广群组共形 | 朴素增广 vs 群组共形的覆盖误差、n_eff 虚增倍数；乐观增广假承诺率；悲观增广失败检出率 | 覆盖误差 ≤0.02；n_eff 虚增=1；假承诺 0；失败检出 ↑≥30% |
| E183 仿真有效域与虚实差 | Δ̂ 与实测偏差误差；仿真-only 迁移失败率；域外误用次数；新材质锚点数 | 误差 ≤0.03；PAE 下 0；0；≤8 |
| E184 承重假设审计 | 共享错误假设（错误摩擦模型）检出率；未锚定承重拦截率；额外探针成本 | ≥90%；100%；≤10% |
| E185 分账门与回溯 | 合成-only 承诺数；证伪后回溯时延；受污染微调回滚正确率 | 0；≤1 检查点；100% |
| E186 端到端 | 季度漂移场地 vs 第 58 轮：成功率/真实探针数/首访承诺时延/合成先验利用率/回溯次数 | +8%/−25%/−20%/+35%/≤1 |

## 5. 集成更新：v16*** → v16**** 体系

```
根信任 + 能力格
│
├─ L0 分布式底座与执行边 (GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX,XFR,CRC,SFE,FDR,RAB,DST,SBC)
├─ L0.5+ 鲁棒性层 (TRO,RXC,RCO,REX,RTA,TRC,RUR)
├─ L0.5++ 动作-协同层 (ACS,SCOM,CEC,AEC,JTC)
├─ L0.5* 证据-交互层 (SMM,PCE,BVK,ISE,TAF,MEC)
├─ L0.5*⁺ 元认知-信任层 (MFSL,XMC,PTM,MXI,FSE,J_p)
├─ L0.5*⁺⁺ 结构化自适应层 (KGMM,SFT-KG,UXSE,KGES,ACC,J_p++)
├─ L0.5*⁺⁺⁺ 虚实分账层 (EPL,CAA,SVC,LBA,PAE,SAPCE,J_p+++) ← v59 新增
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
...
└─ L6 原型证伪/XFER/LFF/IXD
```

JCPS 输出扩展为：
`(v,a,m,q,ι,κ,g,λ,τ,σ,ρ,Explain,RUR_state,α_S,A_cert,γ_ce,δ_a, Σ/C+ 结构, 𝓜_core, J_m, probe_log, consent_state, w_h, q_φ/k\*, D(r), ρ_ℳ, s_op/auth, m_E, ood_state, J_p, kg_subgraph_id, ft_version, mental_snapshot, misunderstanding_prob, ft_log, ux_log, provenance_id, lineage_weight, gen_version, sim_envelope_id, sim_gap, anchor_set, load_bearing_assumptions, retracted_gens, aug_cert_id, ft_provenance)`

其中新增：`provenance_id` 证据血统根；`lineage_weight` 合成证据可用权重；`gen_version` 生成器/仿真器版本；`sim_envelope_id` 当前有效域；`sim_gap` 虚实差估计；`anchor_set` 真实锚点；`load_bearing_assumptions` 承重假设清单；`retracted_gens` 已回溯生成器；`aug_cert_id` 增广证书；`ft_provenance` 微调数据血统。

云边协议 CEB+++ → **CEB++++**：云端可下发**仿真器/增广器增量**，但必须随包附上「有效域 V_S、假设清单 𝒜、生成器版本」三件套；边缘收到后先做**影子锚点校验**（在少量真实锚点上测 Δ_S 与承重假设可区分性），通过才进入先验池，且**任何合成增量都不得直接扩大不可逆动作集**。边端回传：真实锚点观测、虚实差残差、承重假设未锚定告警、被证伪生成器版本与回溯记录，作为云端生成器修正与 V_S 收缩的依据。**第 58 轮「知识图谱也要走隔离」在本轮扩展为「生成器也要走隔离——合成证据必须挂真实根、标生成器版本、接受真实锚点证伪与批量回溯」**。

## 6. 本轮最大风险

**一句话**：本轮把「真实证据稀缺」换成了「生成器可信」——若增广器、仿真器与承重假设审计共享同一套未被现实检验的假设，系统会生成并审计通过一个在内部完全自洽、在现实中并不存在的世界；因此合成证据必须被硬性禁止跨越不可逆承诺门，且任何承重假设若无真实锚点就必须显式判定为「不可信」而不是「默认成立」，否则系统会自信地走进一个只存在于仿真器里的悬崖。
<!-- ARTIFACT:END -->