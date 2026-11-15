# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 70 轮（承接第 69 轮「FLUID-RAS 流匹配交互消歧」IP-253~263；灵感循环新循环第 3 轮；本轮灵感：「仿真到现实」×「UniBot世界挑战赛」）

> R69 把不确定性一分为二（aleatoric / epistemic），并让系统学会「问」：看、探、问句都是动作，VoI 决定值不值得问。但 R69 的每一个保证——模态权重 ECE、VoI 校准、流似然阈值 τ_FMA、C-RAS-WM 动作认证——都建立在**同一个生成模型**上，而这个模型是在**仿真**里学出来的。仿真到现实不是又一种噪声，而是**模型形式本身的错位（model-form error）**：世界不是「更吵的仿真」，而是「另一个世界」。于是 R69 可以做到**在仿真里完美校准、在现实里自信地错**；而且系统越自洽、证书越紧，静默迁移失败越危险。
>
> 本轮两个灵感正好各补一刀：
> - **仿真到现实**告诉我们：要建模的是「差距的结构」（观测/动力学/语义/具身），而不是域随机化的一个标量预算；域随机化覆盖的是参数，不是现实。
> - **UniBot 世界挑战赛**告诉我们：标准化公开任务 + 排行榜既是可比性的来源，也是 Goodhart 与记忆化的压力源；同时它提供了从 S0 纯仿真到 S3 真机的**迁移阶梯**，正好用来检验「证书是否只在仿真里成立」。
>
> 核心命题：把不确定性从二分升级为**三分**——U_ale（噪声，不可约）、U_epi（任务歧义，可用交互消解）、**U_sim（模型形式 / 迁移差距，只能靠现实锚点与桥接探针消解，不能靠向同一个模型多问）**；并用三件套守住它：(i) **迁移风险证书**（密度比 + 保形风险控制；达不到就诚实地「不认证」）；(ii) **无模型安全底座**（因为用有 gap 的模型去认证动作是循环论证）；(iii) **反 Goodhart 的隐藏元分割**（按生成因子而非实例划分）。命名 **BRIDGE-RAS**（Bridged-Reality Identifiability with Dual-channel Gap Evidence）。
>
> 一句话定位：R66 问「谁控制」，R67 问「未来怎样」，R68 问「我的测量还准吗」，R69 问「我该向谁求证、还能问什么」，R70 问「**我求证时所处的那个世界，是真实世界吗**」——比「问错」更危险的是「在错的世界里，把问题问对了」。

## 0. 直觉与动机

**灵感 1（仿真到现实是模型形式误差，不是标量噪声）**
直觉：R69 的 U 是在「给定模型 p_θ」的前提下度量不确定性。但 sim-to-real 改变的是 p_θ 本身：渲染的镜面反射让透明物体看起来像两个物体（观测 gap）；轮子在地毯上的摩擦与仿真不同（动力学 gap）；挑战赛把「成功」定义为推出区域，而人认为该轻放（语义 gap）；真机的关节间隙与通信延迟（具身 gap）。把这四件事压成一个域随机化范围，等于用「参数覆盖」冒充「现实覆盖」——仿真里每一次采样都在自己的世界里自洽，唯独不在部署世界里自洽。
严谨地说：存在一个**桥接算子**把真实观测映回仿真等价观测，gap 是这个算子在四类因子上的**可辨识残差**；不可辨识的部分不能被更多仿真数据或更多交互样本消掉。

**灵感 2（UniBot 挑战赛是双刃剑：可比性 vs Goodhart）**
直觉：公开排行榜让方法可比、可复现，这是科学进步必需的；但一旦把排行榜当成目标，优化压力就会寻找仿真漏洞（穿模、利用摩擦参数、卡住判定器）与任务记忆（记住固定布局/种子），而不是迁移能力。竞赛要赢，研究要真——两者只在「评估协议不可被优化」时才一致。
所以我们不交一个标量名次，而交一条**迁移阶梯向量** (S0 纯仿真, S1 域随机化, S2 硬件在环, S3 真机)，每一步附证书；并按**生成因子**（光照/摩擦/具身/物体类别/指令族）而不是按实例做隐藏元分割，让「跨因子泛化」无法靠记住实例通过。

**灵感 3（第三类不确定性 U_sim：问同一个模型，问不出模型外的答案）**
直觉：R69 的交互（看/问/触）能消解 U_epi，是因为它引入了**新的真实证据**。但对 U_sim，向同一个仿真器再多采 K 个模态、再多问人一句，都不会告诉你「你的摩擦模型错了」。消解 U_sim 的唯一途径是**桥接探针**：轻敲听声/测柔顺、在已知几何区做一次已知动作测延迟、低风险扫掠测摩擦、放置标定物测观测偏移。这类动作与 R69 的信息动作本质不同：前者的信息目标是**任务模态 M**，后者是**迁移参数 φ**。前者可以向人求证，后者只能向物理世界求证。

**灵感 4（用模型认证模型是循环论证 → 必须有不会说谎的底座）**
直觉：R69 的 C-RAS-WM 用世界模型预测未来、认证动作前缀。这在模型可信时是对的；但 sim-to-real gap 恰恰使模型不可信——**用一个有 gap 的模型去证明「这个动作在有 gap 的真实世界里安全」，是循环论证**。因此 BRIDGE-RAS 必须引入一条**不依赖学习模型的**安全通道：仅由本体感觉、关节限位、自碰撞几何、力矩/电流上界、看门狗构成的**无模型安全底座（MFSF）**。它保守、能力弱，但它不会因为 sim-to-real 而失效。
这里提炼出一条跨轮原则：**每加一层，都要加一条该层无法自我认证的独立通道**——R69 用流似然对冲标定吸收，R70 用无模型底座对冲模型形式误差。

**灵感 5（静默失败：证书会把「仿真里的自信」洗成「带证书的自信」）**
直觉：R69 最大的风险是「问错比不问更危险」。R70 把它推进一格：当系统能签发一张「已认证可迁移」的证书时，失败不再表现为犹豫，而表现为**自信且可审计的错误**。尤其当锚点只在策略已经成功的状态附近采集（幸存者偏差）、当隐藏元分割发生泄漏时，U_sim 会被系统性低估，证书变成一张不可证伪的通行证。因此本轮把「锚点覆盖」与「泄漏审计」当成与安全同等级的一等公民，而不是事后检查。

## 1. 形式化定义（增量：定义 310–326）

**定义 310（BRIDGE-RAS 总览）** BRIDGE-RAS = (FLUID-RAS†, SGE, TRC, MFSF, DCC, BPA, PIM, HGX, ILD, TILA, AIC-S2R)。四不变式：
(i) 继承 FLUID-RAS 定义 293 的三不变式（零学习写操作、交互预算硬约束、证据纪律）；
(ii) **模型形式诚实性**：任何依赖学习模型的保证，必须显式标注其适用的 gap 区域；未认证区域内不得以 WM 证书单独放行；
(iii) **无模型兜底**：真实提交的动作必须同时通过 MFSF；DCC 冲突时取更保守者；
(iv) **可迁移性证据纪律**：单次真机锚点、单一因子覆盖、单一公开任务不得单独支撑「已迁移」结论，需跨因子锚点集与隐藏元分割一致。

**定义 311（结构化 gap 分解）** 设仿真联合分布 P_S(o,ξ)、真实 P_R(o,ξ)。gap 分解为四类算子：
- 观测 gap：B_o: O_R→O_S（光度/传感器/标定），残差 r_obs = E_{o~P_R}‖B_o(o) − o_S‖；
- 动力学 gap：B_d 作用于转移核 P(dx'|x,a)，参数 φ_d（摩擦、质量、柔顺、延迟）；
- 语义 gap：B_y 定义成功/失败标签与奖励的映射差异，参数 φ_y；
- 具身 gap：B_m 定义形态/关节限位/传动差异，参数 φ_m。
记 φ = (φ_d, φ_y, φ_m)。**gap 不是标量**：它是作用在分布与转移核上的算子族，只能在其可辨识子空间上被估计。

**定义 312（桥接与迁移风险）** 部署策略由仿真策略经桥接复合：π_R(·|o) = π_S(·|B_o(o))。迁移风险 gap 定义为
ε_gap(π) = sup_{π∈Π_cert} |R_R(π) − R_S(π)|，
其中 R_R、R_S 为真实/仿真期望风险，Π_cert 为待认证策略类。BRIDGE 的目标不是把 ε_gap 压到 0（通常不可能），而是**在置信度 1−δ 下给出上界 ε̂_gap 并在其上决策**。

**定义 313（三分不确定性）** U_ale = 模态内不可约方差（继承定义 297）；U_epi = 任务模态可约歧义（继承定义 297）；**U_sim** 由 gap 上界与未辨识迁移参数后验共同定义：U_sim = ε̂_gap + λ_φ·tr(Cov(φ | D_anchor))，其中 D_anchor 为现实锚点集。三者语义正交，**不做标量加和**：U_ale 进 λ floor；U_epi 进交互；U_sim 进「认证 / 探针 / 无模型兜底」三选一（定义 325）。

**定义 314（迁移风险证书 TRC）** 对锚点集 D_anchor 与密度比估计 ŵ(o) = p̂_R(o)/p̂_S(B_o(o))，用保形风险控制给出
R_R(π) ≤ R̂_S^w(π) + q_{1−δ}({ℓ_i}) + D_f(P_R‖P_S)，
其中 R̂_S^w 为重要性加权的仿真风险，q 为保形分位，D_f 为 f-散度（Rényi/TV）上界。**若任一前提不成立（锚点覆盖不足、密度比支撑外、f-散度上界不可估），TRC 输出 Uncertified，而不是给一个好看的数**。Uncertified 是一等输出。

**定义 315（锚点覆盖与可交换域）** 锚点集必须覆盖声明域 Ω_cert（按因子分层：光照×摩擦×具身×类别），覆盖率 ρ_cov(Ω_cert) ≥ 1−δ_cov。仅当部署观测 o 落入 Ω_cert 且密度比有界时 TRC 才可认证，否则降级（定义 325）。**声明域之外的迁移结论一律无效**。

**定义 316（无模型安全底座 MFSF）** 安全集 S_0 由与学习模型无关的量定义：关节限位、速度/加速度/力矩上界、自碰撞几何、支撑多边形、命令-反馈一致性看门狗。存在控制障碍函数 h_0(x)（仅用本体感觉与已知几何）使得对任意有界扰动 d∈D_max，ḣ_0 + α(h_0) ≥ 0。MFSF 输出安全动作集 K_0(x)。它保守且能力有限，但其有效性**不依赖** p_θ。

**定义 317（双通道证书 DCC）** 对动作前缀 A，WM 通道给出 k_wm = certified_prefix_WM(A)（依赖学习世界模型），无模型通道给出 k_mf = certified_prefix_MFSF(A)（不依赖模型）。联合证书：
- 若 TRC 认证 ε̂_gap ≤ ε_cert：k = k_wm（R69 行为），MFSF 仅作最后防线；
- 若未认证：k = min(k_wm·χ_gap, k_mf)，两通道冲突时取更保守（更短前缀 / 更低速度）。
语义：**安全 = (WM 认证 ∧ 已认证 gap) ∨ MFSF**；在 gap 未认证时，MFSF 是唯一可单独放行的通道。

**定义 318（桥接探针空间与可辨识性）** 桥接探针 g_b ∈ 𝒜_bridge ⊂ 𝒜_+：轻敲/挤压测柔顺（激励 φ_d）、已知位姿往返测延迟、低风险扫掠测摩擦、放置标定物测观测偏移。探针必须持续激励（persistent excitation）：对迁移参数 φ 的 Fisher 信息矩阵满足 I(φ; g_b) ⪰ ε_pe·I 时 φ 才可辨识；否则探针「做了但不长知识」，不计入 U_sim 下降。探针本身必须落在 S_0 内（定义 316）。

**定义 319（分层 VoI）** 交互预算在两类信息动作间分配：
- 任务 VoI：VoI_task(g)（继承定义 298，目标是模态身份 M）；
- 迁移 VoI：VoI_sim(g_b) = E[U_sim | D_anchor] − E[U_sim | D_anchor ∪ y(g_b)]（目标是迁移参数 φ 与 gap 上界）。
选择 argmax(β_task·VoI_task − c) 与 argmax(β_sim·VoI_sim − c) 中净收益更大者；两者共享同一硬预算（定义 293-ii）。当 U_sim 高时 β_sim 自动上调——**先确认世界，再决定动作**。

**定义 320（隐藏元分割 HGX）** 任务按生成因子 F = (光照, 摩擦, 具身, 物体类别, 指令族) 分组，公开集与隐藏集在因子层正交（同一因子组合不跨集）。评测输出迁移阶梯向量 sc = (sc_S0, sc_S1, sc_S2, sc_S3) 与各步证书，**不输出单一标量名次**；跨因子泛化取 sc 在隐藏因子上的最差值（min-over-factors），而非均值。

**定义 321（不变性责任检测 ILD）** 对同一任务施加保语义的物理扰动族 T_inv（微小摩擦/质量/光照/延迟变化）。若成功率在 T_inv 下骤降而仿真奖励不降，判为**仿真漏洞利用（sim exploit）**：它优化了仿真器伪影而非任务本身。ILD 输出 exploit_score，作为 HGX 的一票否决项。

**定义 322（任务身份泄漏审计 TILA）** 检测策略是否使用了与任务实例身份相关、但与任务语义无关的特征（固定种子、布局哈希、贴图 ID、排行榜元数据）。用「打乱身份但保持语义」的对照集测性能差 Δ_id；Δ_id 显著 > 0 ⇒ 记忆化，排行榜分数不可用于迁移结论。

**定义 323（对抗分布 AIC-S2R）** ℰ_S2R = ℰ_FLUID × {渲染欺骗, 动力学参数漂移, 硬件延迟/丢帧, 语义错标, 探针致伤, 锚点投毒, 隐藏集泄漏}。特别地，**锚点投毒**（现实中给出错误标定）可使 U_sim 被低估，需与 R69 的 ℰ_poison 联合防御。

**定义 324（证书 J_BRIDGE）** J_BRIDGE = (J_FLUID, ε̂_gap, TRC_state, ρ_cov, U_sim, probe_FIM_min, ladder_vector, exploit_score, Δ_id, mfsf_active, bridge_ver)。Valid ⇔ Valid(J_FLUID) ∧ (TRC Certified ⇒ 全链一致) ∧ (¬Certified ⇒ MFSF 全程激活且 λ 满足定义 325)。**Uncertified 是合法且必须被记录的证书状态**。

**定义 325（迁移感知退避律）** 三级：
- L0（认证）：ε̂_gap ≤ ε_cert ⇒ λ = λ_floor(U_ale)，行为同 R69（resolution bonus 保留）；
- L1（可探）：未认证但存在 g_b 使 VoI_sim(g_b) > c(g_b) 且可辨识 ⇒ 执行桥接探针，更新后重判；探针期间 λ ≥ λ_floor(U_ale + U_epi + U_sim)；
- L2（兜底）：未认证且探针无利可图/不可辨识/超预算 ⇒ λ = λ_floor(U_ale + U_epi + U_sim)，动作前缀取 DCC 保守值，必要时只允许 MFSF 内的反射动作。
单调性：L0→L1→L2 λ 单调不降，安全侧永不弱于 R69。

**定义 326（时序与预算）** 默认每轮不触发 gap 估计（复用缓存 ε̂_gap 与 φ 后验）；仅当 (a) 观测落入 Ω_cert 边界、(b) 模态分布突变、(c) TRC 临近过期、(d) ILD 报警 时重估。桥接探针与任务信息动作共享 ≤1 次/单位时间预算；探针不得挤占紧急安全动作。

## 2. 关键算法骨架

```python
# IP-264 SGE：结构化 gap 估计（密度比 + 保形 + 系统辨识后验）
def estimate_gap(anchors, policy, bridge):
    w = density_ratio(anchors.obs, sim_ref)
    if not support_ok(w, anchors.region):        # 定义 315
        return GapEstimate.uncertified()
    eps_hat   = conformal_transfer_bound(policy, anchors, w)   # 定义 314
    phi_post  = system_id_posterior(anchors, transfer_model)  # 观测/动力/具身
    return GapEstimate(eps_hat, phi_post, certified=eps_hat <= EPS_CERT)

# IP-268 BPA + IP-269 PIM：分层 VoI（先确认世界，再消歧任务）
def choose_info_action(modes, gap, budget, beta_task, beta_sim):
    best = None
    for g in bridge_probe_candidates(gap.phi_post):        # 轻敲/往返/扫掠
        if not budget.allow(g) or not mfsf.inside(g):      continue
        if lambda_min(fim(g, gap.phi_post)) < EPS_PE:      continue  # 不可辨识
        score = beta_sim * voi_sim(g, gap) - cost(g)
        if best is None or score > best.score: best = (g, "bridge", score)
    for g in info_action_candidates(modes):                # 继承 R69
        if not budget.allow(g) or not c_ras_wm.certify_info(g, o_t): continue
        score = beta_task * voi_task(g, modes) - cost(g)
        if best is None or score > best.score: best = (g, "task", score)
    return best if best and best.score > 0 else None       # 无利可图 → 不交互

# IP-266 MFSF：无模型安全前缀（仅本体感觉 + 几何 + 看门狗）
def mfsf_prefix(self, A):
    k = 0
    for a in A:
        if not (self.joint_ok(a) and self.torque_ok(a) and self.self_col_ok(a)):
            break
        if not self.watchdog_consistent(a): break
        k += 1
    return k                                               # 不依赖 p_θ

# IP-274 主闭环：FLUID 层不变，外包一层「认证 / 探针 / 兜底」
def BRIDGE_RAS_round(M, obs):
    z, o = M.mtm.forward(...); c, U_cal, thr = M.cof.step(...)   # R69
    U_ale, U_epi, modes = M.aud.decompose(M.fmp.sample(o, K), z)
    # 1) gap 估计（缓存；仅触发时重估，定义 326）
    gap = M.sge.maybe_update(o, M.anchors, M.fmp)
    U_sim = gap.eps_hat + LAM_PHI * trace(gap.phi_cov)
    # 2) 分层交互：U_sim 高则先探世界
    g = M.bpa.choose_info_action(modes, gap, M.budget,
                                 beta_task=1.0,
                                 beta_sim=(1.0 if U_sim > TAU_SIM else 0.2))
    if g is not None and g.kind == "bridge":
        M.anchors.add(M.execute_probe(g)); gap = M.sge.update(g)
    elif g is not None:
        U_epi = M.cia.update_belief(modes, M.cia.execute(g))
    # 3) 三级退避（定义 325）
    A = M.ach.propose(x_prime, H=M.vista.H)
    k_wm = M.c_ras_wm.certified_prefix(A, ..., wm_preds)
    if gap.certified:                                   # L0 = R69
        lam, k = lam_floor(U_ale), k_wm
    else:
        k_mf = M.mfsf.mfsf_prefix(A)
        if M.bpa.probe_profitable(gap) and not budget_exhausted:   # L1
            lam, k = lam_floor(U_ale + U_epi + U_sim), min(k_wm, k_mf)
        else:                                           # L2
            lam, k = lam_floor(U_ale + U_epi + U_sim), k_mf
            if k == 0: return reflex_only()
    # 4) 反 Goodhart 审计（异步，不阻塞实时环）
    M.ild.check(A, T_inv); M.tila.audit(obs); M.hgx.log(M.ladder)
    return k, lam, select_mode(modes, U_epi, lam), \
           J_BRIDGE(M.fma, gap, U_ale, U_epi, U_sim, k_wm, k)
```

## 3. 推导

**引理 19（迁移证书的可靠性）** 在 A99（锚点可交换域）、A100（密度比有界且支撑覆盖）、A101（保形可交换）下，定义 314 的 ε̂_gap 满足 P(R_R(π) > R̂_S^w(π) + q_{1−δ} + D_f) ≤ δ，对 Π_cert 一致成立。要点：**证书的价值在于它敢输出 Uncertified**——当支撑或覆盖前提破裂时，任何有限上界都不成立，此时「不认证」本身是正确的统计结论，而非失败。

**引理 20（模型认证的循环性 / gap 放大）** 设 WM 对转移核的误差 ≤ ε_m，真实 gap ≤ ε_gap。则 WM 认证前缀的真实风险上界膨胀为 L_c·(ε_m + ε_gap)（L_c 为证书对模型误差的 Lipschitz 常数）；当 ε_gap 未知时**不存在有限保证**。故任何纯 WM 证书在 sim-to-real 下都不可单独作为放行依据，必须由一条不依赖 p_θ 的通道（MFSF）兜底。这是「每加一层必须有独立通道」原则的形式化。

**引理 21（探针可辨识性）** 若探针 g_b 的 Fisher 信息 I(φ; g_b) ⪰ ε_pe·I，则其后验协方差满足 tr(Cov(φ|D∪y)) ≤ tr(Cov(φ|D)) − c·ε_pe，U_sim 至少下降 c·ε_pe。若 I(φ; g_b) 在 φ 的某方向上奇异（非持续激励），该方向上 U_sim **不下降**：敲一个刚体听不出摩擦。系：探针的「值钱」不是由动作幅度决定，而是由它对 φ 的激励方向决定。

**引理 22（反 Goodhart 的因子分割界）** 在定义 320 的因子正交分割下，公开集与隐藏集之间不存在共享因子组合，故记忆化只能提升公开集分数；若 TILA 测得 Δ_id > 0，则公开集分数对 S3 真机表现的条件相关性 ≤ 0（排行榜不再有预测力）。ILD 的 T_inv 进一步把「利用仿真伪影」与「完成任务」分离：exploit_score 高者，其 S0 分数与 S3 分数呈负相关。

**定理 18（BRIDGE 严格包含 FLUID）** 取 ε̂_gap ≡ 0（已认证）、无桥接探针、MFSF 不收紧（k_mf ≥ k_wm），则 BRIDGE 的 L0 路径与 R69 逐指令相同：λ = λ_floor(U_ale)，交互仍由 VoI_task 决定，resolution bonus 保留。因此 FLUID 是 BRIDGE 在「gap 已认证为零」边界上的严格退化；安全侧只增不减，效率侧只在认证成立时才获得。

**定理 19（双通道安全的纵深界）** 部署安全失败要求 (WM 通道 ∧ 已认证 gap) 与 MFSF 同时失效。若两通道失效事件在给定状态下的相关性 ≤ ρ_c，则
P_fail ≤ P_wm·P_mf + ρ_c·min(P_wm, P_mf)，
且 P_mf 由 A102（扰动有界 |d| ≤ D_max）单独界定，与 p_θ 无关。故即使 WM 因 gap 完全失效（P_wm→1），只要 MFSF 的扰动界成立，失败率仍被 P_mf 封顶——这是 R69 单通道所没有的下界。

**定理 20（迁移感知的单调保守性）** 沿 L0→L1→L2，λ 单调不降；且对任意状态，BRIDGE 的期望风险 ≤ R69 在「把 U_sim 误当 0」时的风险，而 ≥ R69 的真实安全下界。即：**认证失败时，BRIDGE 比「假装 gap 不存在」的 R69 更安全；认证成功时，二者等价**。安全与效率的交换只发生在证书允许的地方。

## 4. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| MFSF 前缀认证（本体感觉 + 几何） | < 0.1ms（与 K 无关） | O(1) | 定义 316；不依赖 p_θ |
| DCC 联合判定 + 三级退避 | < 0.05ms | O(1) | 定义 317、325；定理 19–20 |
| 分层 VoI（候选 ≤ 6） | < 0.12ms | O(1) | 定义 319 |
| SGE gap 重估（触发式，异步） | 80–300ms（环外） | O(|D_anchor|) | 定义 314–315；不占实时环 |
| 保形迁移证书（离线/增量） | 秒级，离线 | O(|D_anchor|·d) | 引理 19 |
| 桥接探针执行 | 0.1–2s（物理动作，占预算） | — | 定义 318；须过 MFSF |
| HGX / ILD / TILA 审计 | 异步 | — | 定义 320–322 |
| **实时环路总延迟** | **< 2.75ms**（缓存 gap、K=1；比 R69 多 0.15ms） | — | 定理 18–20 |

## 5. 实验设计 E301–E316

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 结构化 gap 归因 | 四类 gap 能否被分别估计 | 归因误差 < 15%，优于标量域随机化 |
| E302 TRC 覆盖率 | 迁移证书是否保守可信 | 经验覆盖 ≥ 1−δ，且在缺口场景输出 Uncertified |
| E303 诚实拒证 | 该说「不认证」时是否会说 | 缺口场景误认证率 < 2% |
| E304 MFSF 独立性 | 无模型底座在 WM 失效时是否仍安全 | 注入 WM 错误后违规率 ≤ 基线 1/10 |
| E305 探针可辨识性 | 有激励才长知识 | 可辨识探针使 U_sim 降 ≥ 40%；非激励探针 ≈ 0 |
| E306 探针成本-收益 | 桥接探针是否值得 | 找到 VoI_sim/成本拐点，净任务收益 ≥ +8% |
| E307 分层 VoI | 先确认世界再动作是否更好 | 相对 R69 任务成功率 +10%，错误执行 −30% |
| E308 公开 vs 隐藏排名 | 排行榜是否预测真机 | 隐藏因子最差值与公开排名相关 ≤ 0.3 |
| E309 仿真漏洞利用 | ILD 能否识别 exploit | exploit AUC ≥ 0.9；S0 高分/exploit 高分者 S3 失败 ≥ 80% |
| E310 任务记忆化 | TILA 能否测出身份泄漏 | Δ_id 与隐藏集掉分相关 ≥ 0.8 |
| E311 迁移阶梯 | S0→S3 是否给出一致结论 | 阶梯向量可复现，步间方差 < 5% |
| E312 锚点幸存者偏差 | 只在成功处采样会怎样 | 偏差锚点使 U_sim 低估 ≥ 30%，覆盖率检验可检出 |
| E313 锚点投毒 | 错误标定能否骗过证书 | 投毒检出 ≥ 90%，误认证 ≤ 3% |
| E314 跨具身迁移 | 换机器人是否仍成立 | 未重新锚定时自动降级到 L2 |
| E315 真机长时程 | 24h 内 gap 漂移与探针疲劳 | 零探针致伤；U_sim 漂移可追踪 |
| E316 对 FLUID 的严格包含 | ε_gap=0 时是否逐指令一致 | 行为差 = 0，延迟增量 ≤ 0.15ms |

## 6. 本轮最大风险

**一句话**：BRIDGE-RAS 把「仿真里的自信」升级为「带证书的自信」——**若锚点集存在幸存者偏差（只在策略已成功的状态采样）、或隐藏元分割发生泄漏、或锚点被投毒，U_sim 会被系统性低估，TRC 会在最需要承认「我不在真实世界」的时刻签发一张不可证伪的通行证**；此时系统不是犹豫地错，而是**有审计日志、有证书、有排行榜名次地错**——这比 R69 的「问错」更难被发现，也更难被纠正。

**次级风险与缓解**：
1. **证书不可证伪地过度自信** → TRC 强制输出 Uncertified + 锚点覆盖率检验 + E303/E312/E313；
2. **WM 与 MFSF 相关失效**（同一物理假设被两边共享）→ 定理 19 的相关性惩罚项 + E304 独立注入实验；
3. **探针致伤或挤占安全动作** → 定义 318 的 S_0 约束 + 预算硬隔离 + E315；
4. **排行榜 Goodhart / 记忆化** → 因子正交隐藏分割 + TILA + ILD + 只报阶梯向量（E308–E310）；
5. **MFSF 过于保守导致任务不可用** → L0/L1 只在认证成立时放宽，用 E306/E307 量化能力损失，绝不以安全换分数。

**结论一句话**：本轮把「我该问谁」推进到「我凭什么相信我所处的世界」，并给出可证伪的迁移证书；但它最大的风险恰是——**证书本身可能只是把不确定性从系统内部转移到了评估协议里，而非真正消除。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 70 轮产物 · 创新点清单 v1：BRIDGE-RAS（Bridged-Reality Identifiability with Dual-channel Gap Evidence：仿真到现实迁移风险证书 × 无模型安全底座 × 反 Goodhart 隐藏元分割的三分不确定性闭环；SGE×TRC×MFSF×DCC×BPA×PIM×HGX×ILD×TILA×AIC-S2R）

> 承接第 69 轮 IP-253~263（FLUID-RAS）。R69 把不确定性一分为二（aleatoric / epistemic），并让系统学会「问」；但它所有保证——模态 ECE、VoI、流似然阈值、C-RAS-WM 动作认证——都建立在**同一个仿真里学出的生成模型**上。仿真到现实不是更大的噪声，而是**模型形式误差**：世界不是「更吵的仿真」，而是「另一个世界」。于是 R69 可以**在仿真里完美校准、在现实里自信地错**。
>
> 本轮把不确定性升级为**三分**：U_ale（噪声）、U_epi（任务歧义，交互消解）、**U_sim（模型形式/迁移差距，只能靠现实锚点与桥接探针消解）**。并用三件套守住：**迁移风险证书**（达不到就诚实地「不认证」）、**无模型安全底座**（用有 gap 的模型认证动作是循环论证）、**反 Goodhart 隐藏元分割**（按生成因子而非实例划分）。定位：R66 问「谁控制」，R67 问「未来怎样」，R68 问「我的测量还准吗」，R69 问「我该向谁求证」，R70 问「**我求证时所处的世界，是真实世界吗**」。
>
> IP 编号：IP-264~IP-274（共 11 个）。理论姿态不变：**当迁移 gap 被认证为零且不触发探针时，BRIDGE 逐指令退化为 FLUID**；安全侧只增不减，效率只在证书允许处获得。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 69 轮） |
|---|---|---|---|
| IP-264 | SGE Sim-to-real Gap Estimator | 新增 | 四类结构化 gap（观测/动力/语义/具身）；密度比 + 保形 + 系统辨识后验；缺口即 Uncertified |
| IP-265 | TRC Transfer Risk Certificate | 新增 | 重要性加权仿真风险 + 保形分位 + f-散度上界；把「不认证」作为一等输出 |
| IP-266 | MFSF Model-Free Safety Floor | 新增 | 仅用本体感觉/关节限位/自碰撞/力矩上界/看门狗的 CBF 前缀；不依赖 p_θ |
| IP-267 | DCC Dual-Channel Certificate | 新增 | WM 认证与 MFSF 认证并联；gap 未认证时以 MFSF 为唯一可单独放行者，冲突取保守 |
| IP-268 | BPA Bridging Probe Allocator | 新增 | 桥接探针（轻敲/往返/扫掠/标定物）+ 分层 VoI：先确认世界，再消解任务 |
| IP-269 | PIM Probe Identifiability Monitor | 新增 | Fisher 信息/持续激励检查；非激励探针不计入 U_sim 下降 |
| IP-270 | HGX Hidden-factor Generalization eXam | 新增 | 按生成因子做隐藏元分割；只报迁移阶梯向量，不报单一标量名次 |
| IP-271 | ILD Invariance Liability Detector | 新增 | 保语义扰动族下性能骤降 ⇒ 仿真漏洞利用；HGX 一票否决 |
| IP-272 | TILA Task-Identity Leakage Auditor | 新增 | 打乱任务身份、保持语义，测 Δ_id；识别排行榜记忆化 |
| IP-273 | AIC-S2R | 升级 AIC-FLUID | ℰ_S2R = ℰ_FLUID × {渲染欺骗, 动力学漂移, 延迟丢帧, 语义错标, 探针致伤, 锚点投毒, 隐藏集泄漏} |
| IP-274 | J_BRIDGE + BRIDGE-RAS Pipeline | 新增 | FLUID 闭环外包「gap 估计 → 分层交互 → 三级退避 → 反 Goodhart 审计」 |

## 1. 符号体系增量（定义 310–326）

| 符号 | 含义 |
|---|---|
| `BRIDGE-RAS = (FLUID-RAS†, SGE, TRC, MFSF, DCC, BPA, PIM, HGX, ILD, TILA, AIC-S2R)` | 迁移风险感知闭环 |
| `B_o, B_d, B_y, B_m` | 观测 / 动力学 / 语义 / 具身 桥接算子 |
| `φ = (φ_d, φ_y, φ_m)` | 迁移参数（摩擦/质量/柔顺/延迟、标签映射、形态） |
| `ε_gap = sup_π |R_R(π) − R_S(π)|` | 迁移风险 gap |
| `ε̂_gap` | 置信度 1−δ 下的 gap 上界（TRC 输出） |
| `ŵ(o) = p̂_R(o)/p̂_S(B_o(o))` | 密度比 |
| `U_sim = ε̂_gap + λ_φ·tr(Cov(φ|D_anchor))` | 模型形式/迁移不确定性 |
| `D_anchor, Ω_cert, ρ_cov` | 现实锚点集 / 声明域 / 覆盖 |
| `h_0(x), K_0(x)` | 无模型 CBF / MFSF 安全动作集 |
| `k_wm, k_mf, χ_gap` | WM 前缀 / 无模型前缀 / gap 折扣 |
| `g_b, I(φ; g_b), ε_pe` | 桥接探针 / Fisher 信息 / 持续激励阈值 |
| `VoI_sim(g_b)` | 迁移信息增益 |
| `F = (光照,摩擦,具身,类别,指令族)` | 生成因子（隐藏元分割） |
| `sc = (sc_S0, sc_S1, sc_S2, sc_S3)` | 迁移阶梯向量 |
| `exploit_score, Δ_id` | 仿真漏洞利用分 / 身份泄漏分 |
| `J_BRIDGE = (J_FLUID, ε̂_gap, TRC_state, ρ_cov, U_sim, probe_FIM_min, ladder_vector, exploit_score, Δ_id, mfsf_active, bridge_ver)` | 证书 |

## 2. 形式化定义（要点版）

**定义 310（总览与四不变式）** 继承 FLUID 三不变式；新增模型形式诚实性（未认证区域不得以 WM 证书单独放行）、无模型兜底（真实动作须过 MFSF，冲突取保守）、可迁移性证据纪律（单锚点/单因子/单任务不得单独支撑「已迁移」）。

**定义 311–312（结构化 gap 与迁移风险）** gap 分解为观测 `B_o`、动力学 `B_d`、语义 `B_y`、具身 `B_m` 四类算子，只能在其可辨识子空间估计；`ε_gap = sup_π|R_R−R_S|`，目标不是压到 0，而是给出 `ε̂_gap` 并据此决策。

**定义 313（三分不确定性）** `U_ale`、`U_epi`、`U_sim` 语义正交、不做标量加和；分别走 λ floor、交互、认证/探针/兜底。

**定义 314–315（TRC 与锚点覆盖）** `R_R ≤ R̂_S^w + q_{1−δ} + D_f`；前提不成立即输出 **Uncertified**；仅当 `o ∈ Ω_cert` 且密度比有界才可认证，声明域外结论无效。

**定义 316–317（MFSF 与 DCC）** `h_0` 仅用本体感觉/几何/看门狗；安全 = `(WM 认证 ∧ 已认证 gap) ∨ MFSF`；未认证时 `k = min(k_wm·χ_gap, k_mf)`。

**定义 318–319（桥接探针与分层 VoI）** 探针须持续激励 `I(φ;g_b) ⪰ ε_pe I` 且落在 `S_0` 内；预算在 `VoI_task` 与 `VoI_sim` 间分配，`U_sim` 高时 `β_sim` 上调。

**定义 320–322（HGX / ILD / TILA）** 按生成因子正交分割公开/隐藏集；只报 `sc` 阶梯向量，取隐藏因子最差值；保语义扰动下骤降判为 sim exploit；身份打乱测 `Δ_id` 识别记忆化。

**定义 323–324（对抗与证书）** `ℰ_S2R = ℰ_FLUID × {渲染欺骗, 动力学漂移, 延迟丢帧, 语义错标, 探针致伤, 锚点投毒, 隐藏集泄漏}`；`J_BRIDGE` 显式记录 Uncertified 为合法状态。

**定义 325–326（三级退避与时序）** L0 认证 ⇒ 同 R69；L1 可探 ⇒ 探针后重判；L2 兜底 ⇒ `λ=λ_floor(U_ale+U_epi+U_sim)`、前缀取 DCC 保守值、必要时仅反射。gap 重估触发式、环外异步，探针与信息动作共享 ≤1 次/单位时间预算。

## 3. 关键算法伪代码

```python
# IP-264 SGE：结构化 gap 估计（缺口即 Uncertified）
def estimate_gap(anchors, policy, bridge):
    w = density_ratio(anchors.obs, sim_ref)
    if not support_ok(w, anchors.region): return GapEstimate.uncertified()
    eps_hat  = conformal_transfer_bound(policy, anchors, w)     # 定义 314
    phi_post = system_id_posterior(anchors, transfer_model)
    return GapEstimate(eps_hat, phi_post, certified=eps_hat <= EPS_CERT)

# IP-268 BPA + IP-269 PIM：分层 VoI（先确认世界，再消歧任务）
def choose_info_action(modes, gap, budget, beta_task, beta_sim):
    best = None
    for g in bridge_probe_candidates(gap.phi_post):
        if not budget.allow(g) or not mfsf.inside(g): continue
        if lambda_min(fim(g, gap.phi_post)) < EPS_PE: continue  # 不可辨识
        s = beta_sim * voi_sim(g, gap) - cost(g)
        if best is None or s > best.score: best = (g, "bridge", s)
    for g in info_action_candidates(modes):
        if not budget.allow(g) or not c_ras_wm.certify_info(g, o_t): continue
        s = beta_task * voi_task(g, modes) - cost(g)
        if best is None or s > best.score: best = (g, "task", s)
    return best if best and best.score > 0 else None

# IP-266 MFSF：无模型前缀（不依赖 p_θ）
def mfsf_prefix(self, A):
    k = 0
    for a in A:
        if not (self.joint_ok(a) and self.torque_ok(a)
                and self.self_col_ok(a) and self.watchdog_consistent(a)):
            break
        k += 1
    return k

# IP-274 主闭环：FLUID 层不变，外包认证/探针/兜底
def BRIDGE_RAS_round(M, obs):
    z, o = M.mtm.forward(...); c, U_cal, thr = M.cof.step(...)
    U_ale, U_epi, modes = M.aud.decompose(M.fmp.sample(o, K), z)
    gap   = M.sge.maybe_update(o, M.anchors, M.fmp)             # 定义 326
    U_sim = gap.eps_hat + LAM_PHI * trace(gap.phi_cov)
    g = M.bpa.choose_info_action(modes, gap, M.budget, 1.0,
                                 beta_sim=(1.0 if U_sim > TAU_SIM else 0.2))
    if g is not None and g.kind == "bridge":
        M.anchors.add(M.execute_probe(g)); gap = M.sge.update(g)
    elif g is not None:
        U_epi = M.cia.update_belief(modes, M.cia.execute(g))
    A    = M.ach.propose(x_prime, H=M.vista.H)
    k_wm = M.c_ras_wm.certified_prefix(A, ..., wm_preds)
    if gap.certified:                                           # L0 = R69
        lam, k = lam_floor(U_ale), k_wm
    else:
        k_mf = M.mfsf.mfsf_prefix(A)
        if M.bpa.probe_profitable(gap):                         # L1
            lam, k = lam_floor(U_ale + U_epi + U_sim), min(k_wm, k_mf)
        else:                                                   # L2
            lam, k = lam_floor(U_ale + U_epi + U_sim), k_mf
            if k == 0: return reflex_only()
    M.ild.check(A, T_inv); M.tila.audit(obs)                    # 异步
    return k, lam, select_mode(modes, U_epi, lam), \
           J_BRIDGE(M.fma, gap, U_ale, U_epi, U_sim, k_wm, k)
```

## 4. 推导

**引理 19（迁移证书可靠性）** A99–A101 下，`P(R_R(π) > R̂_S^w + q_{1−δ} + D_f) ≤ δ` 对 `Π_cert` 一致成立。要点：**证书的价值在于它敢输出 Uncertified**；前提破裂时任何有限上界都不成立，「不认证」是正确统计结论而非失败。

**引理 20（模型认证循环性 / gap 放大）** WM 误差 `ε_m`、真实 gap `ε_gap` 时，认证前缀真实风险上界膨胀 `L_c(ε_m+ε_gap)`；`ε_gap` 未知则无有限保证。⇒ 纯 WM 证书在 sim-to-real 下不可单独放行，必须由不依赖 `p_θ` 的 MFSF 兜底（「每加一层必须有独立通道」的形式化）。

**引理 21（探针可辨识性）** `I(φ;g_b) ⪰ ε_pe I` ⇒ `tr(Cov(φ|D∪y)) ≤ tr(Cov(φ|D)) − c·ε_pe`，U_sim 至少降 `c·ε_pe`；非持续激励方向上 U_sim **不下降**——敲刚体听不出摩擦。系：探针价值由对 φ 的激励方向决定，而非动作幅度。

**引理 22（反 Goodhart 因子分割界）** 因子正交分割下公开/隐藏集不共享因子组合，记忆化只能抬高公开分；若 `Δ_id>0`，公开分对 S3 表现的条件相关 ≤ 0。ILD 的 `T_inv` 进一步使 exploit_score 高者 S0 分与 S3 分负相关。

**定理 18（BRIDGE 严格包含 FLUID）** `ε̂_gap≡0`、无探针、MFSF 不收紧时，L0 与 R69 逐指令相同：`λ=λ_floor(U_ale)`，交互仍由 `VoI_task` 决定，resolution bonus 保留。FLUID = BRIDGE 在「gap 已认证为零」边界的严格退化。

**定理 19（双通道纵深界）** 失败要求 WM 通道（含已认证 gap）与 MFSF 同时失效：`P_fail ≤ P_wm·P_mf + ρ_c·min(P_wm,P_mf)`；`P_mf` 由扰动有界 `|d|≤D_max` 单独界定、与 `p_θ` 无关。即使 WM 因 gap 完全失效，失败率仍被 `P_mf` 封顶。

**定理 20（迁移感知单调保守性）** 沿 L0→L1→L2 `λ` 单调不降；BRIDGE 风险 ≤ 「把 U_sim 误当 0」的 R69 风险，且 ≥ R69 真实安全下界。认证失败时比「假装 gap 不存在」更安全，认证成功时与 R69 等价。

## 5. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| MFSF 前缀认证（本体感觉 + 几何） | < 0.1ms（与 K 无关） | O(1) | 定义 316；不依赖 p_θ |
| DCC + 三级退避 | < 0.05ms | O(1) | 定义 317、325；定理 19–20 |
| 分层 VoI（候选 ≤6） | < 0.12ms | O(1) | 定义 319 |
| SGE gap 重估（触发式、异步） | 80–300ms（环外） | O(|D_anchor|) | 定义 314–315 |
| 保形迁移证书（离线/增量） | 秒级，离线 | O(|D_anchor|·d) | 引理 19 |
| 桥接探针执行 | 0.1–2s（物理，占预算） | — | 定义 318；须过 MFSF |
| HGX / ILD / TILA 审计 | 异步 | — | 定义 320–322 |
| **实时环路总延迟** | **< 2.75ms**（缓存 gap、K=1；比 R69 多 0.15ms） | — | 定理 18–20 |

## 6. 实验设计 E301–E316

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 结构化 gap 归因 | 四类 gap 能否分别估计 | 归因误差 < 15%，优于标量域随机化 |
| E302 TRC 覆盖率 | 证书是否保守可信 | 经验覆盖 ≥ 1−δ，缺口场景输出 Uncertified |
| E303 诚实拒证 | 该拒时是否拒 | 缺口场景误认证率 < 2% |
| E304 MFSF 独立性 | WM 失效时底座是否仍安全 | 注入 WM 错误后违规率 ≤ 基线 1/10 |
| E305 探针可辨识性 | 有激励才长知识 | 可辨识探针使 U_sim 降 ≥ 40%；非激励 ≈ 0 |
| E306 探针成本-收益 | 桥接是否值得 | 找到 VoI_sim/成本拐点，净任务收益 ≥ +8% |
| E307 分层 VoI | 先确认世界再动作 | 相对 R69 成功率 +10%，错误执行 −30% |
| E308 公开 vs 隐藏排名 | 排行榜能否预测真机 | 隐藏因子最差值与公开排名相关 ≤ 0.3 |
| E309 仿真漏洞利用 | ILD 能否识别 exploit | AUC ≥ 0.9；S0 高分 + exploit 高者 S3 失败 ≥ 80% |
| E310 任务记忆化 | TILA 能否测身份泄漏 | Δ_id 与隐藏集掉分相关 ≥ 0.8 |
| E311 迁移阶梯 | S0→S3 结论一致 | 阶梯向量可复现，步间方差 < 5% |
| E312 锚点幸存者偏差 | 只在成功处采样 | U_sim 低估 ≥ 30%，覆盖率检验可检出 |
| E313 锚点投毒 | 错误标定能否骗过证书 | 检出 ≥ 90%，误认证 ≤ 3% |
| E314 跨具身迁移 | 换机器人是否成立 | 未重新锚定自动降级到 L2 |
| E315 真机长时程 | 24h gap 漂移与探针疲劳 | 零探针致伤；U_sim 漂移可追踪 |
| E316 对 FLUID 严格包含 | ε_gap=0 是否逐指令一致 | 行为差 = 0，延迟增量 ≤ 0.15ms |

## 7. 本轮最大风险

**一句话**：BRIDGE-RAS 把「仿真里的自信」升级为「带证书的自信」——**若锚点集有幸存者偏差、隐藏元分割泄漏或锚点被投毒，U_sim 会被系统性低估，TRC 会在最需要承认「我不在真实世界」时签发一张不可证伪的通行证**；系统不是犹豫地错，而是**有审计日志、有证书、有排行榜名次地错**——这比 R69 的「问错」更难发现、更难纠正。

**次级风险与缓解**：证书过度自信（TRC 强制 Uncertified + 覆盖率检验 + E303/E312/E313）；WM 与 MFSF 相关失效（定理 19 相关性惩罚 + E304）；探针致伤或挤占安全动作（S_0 约束 + 预算硬隔离 + E315）；排行榜 Goodhart/记忆化（因子正交隐藏分割 + TILA + ILD + 阶梯向量）；MFSF 过保守致任务不可用（仅在认证成立时放宽，E306/E307 量化能力损失）。

**结论一句话**：本轮把「我该问谁」推进到「我凭什么相信我所处的世界」，并给出可证伪的迁移证书；但它最大的风险恰是——**证书本身可能只是把不确定性从系统内部转移到了评估协议里，而非真正消除。**
<!-- ARTIFACT:END -->
