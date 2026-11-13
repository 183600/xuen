# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 70 轮（承接第 69 轮「FLUID-RAS 流匹配多模态交互不确定性二分闭环」IP-253~263；灵感循环新循环第 3 轮；本轮灵感：「力矩传感」×「对比实验」×「并发推理」）

> R69 给系统装上了「会问的嘴巴」，但自陈最大风险写得清楚：全部效率收益押在「流模型的模态分布可信」上——模态权重未校准时，VoI 在错误信念上计算，系统会自信地追问一个幻影，或把人类一个误导性回答盖上「已验证」的章。检查 R69 的缓解手段（MCG 校准门）发现两个洞：它依赖**离线校准集**算 ECE，在线、无校准集时无能为力；且「问」的答案来自**可能说谎的证人**——k 个正交源的相关性 ρ 只是被压低、不是归零，因为证言类证据都出自同一个说谎者的意图。
>
> 本轮三个灵感各堵一个洞：
> - **对比实验**回答「怎么问才对」：消歧的最优形式不是抛出一个问题，而是**设计一个让候选假设必然分歧的实验**。对比度 C(g)（模态间预测结果的 TV 分离）是 VoI 的可计算代理；实验可先在世界模型里**并发预演**（dry-run），真实预算只花在「预演里就分得出胜负」的实验上。
> - **力矩传感**回答「问谁才不会被骗」：扭矩签名受动力学约束——门有多重、抽屉空不空，不取决于任何人的说法，而取决于手腕上 0.5 N·m 的读数。在威胁模型内（A100：排除执行器级构陷），力矩是**范畴上不可伪造的证据通道**；R69 的 g_probe 从「摸一下」升级为「一次有设计的力矩实验」。
> - **并发推理**回答「问得起吗、信得过得起吗」：K 个模态 × |G| 个候选实验的预演**天然可批量**（实时性红利）；N_c 条独立推理路径的**一致性**给出免校准集的在线信任代理（CCG），正面回应 R69 最大风险；代价是共因失败——路径共享 trunk，「一致」可能只是同一次幻觉的回声，用 A101 + 诚实声明兜住。
>
> 核心命题：**把 R69 的「向证人求证」升级为「让物理作证」：消歧动作 = 一场对比实验（CGX 设计 + DRY 并发预演 + 真实执行）；证据按完整性序仲裁（物理 ≻ 观测 ≻ 证言，PEA）；模态分布自身的可信度由并发一致性在线把关（CCG）。** 命名 **TORCH-RAS**（Torque-gROunded Contrastive Hypothesis-testing with Concurrent inference）。
>
> 一句话定位：R66 问「谁控制」，R67 问「未来怎样」，R68 问「我的测量还准吗」，R69 问「我该向谁求证、还能问什么」，R70 问「**谁的答案无法说谎**」——不再问证人，让世界在一场设计好的对比实验里自己作证；证人只保留旁听席。

## 0. 直觉与动机

**灵感 1（对比实验 → 消歧的最优形式是「设计分歧」，不是「提问」）**
直觉：R69 的 MINT 用期望后验熵选交互动作，但 E[H(M|o,y)] 需要一个**学习型答案模型** p̂(y|g,o)——它本身可以错，且其误差无界时能翻转候选排序（在错误的候选上花真实预算）。实验科学的答案是：好实验不是「让答案模型预言结果」，而是「让候选假设的预测**必然分歧**」。定义对比度 C(g) = Σ_{i<j} ŵ_i ŵ_j·TV(p(·|m_i,g), p(·|m_j,g))：候选实验在当前模态分布下能制造的假设分离度。对比度由**认证世界模型（R67 VISTA，已被 R68 认证）的动力学约束预测**给出，误差有界（ε_dr），排序在间隔 > 2ε_dr 时稳定（引理 19b）；VoI 与对比度的关系由 Le Cam/Fano 型界给出（引理 19a）。R69 的「歧义大且分得开，交互才值钱」由此获得一个**可计算、可审计**的操作化。

**灵感 2（力矩传感 → 存在一条说不了谎的证据通道）**
直觉：R69 的证据纪律（k 个正交源一致）面对「共谋欺骗」（表情+语气+证言一起演）时，相关性 ρ 只是被压低、不是归零——所有证言类证据都出自同一个说谎者的意图。力矩传感提供**范畴上不同**的证据：扭矩签名 τ̂_k 是世界模型在模态 m_k 下对动作的动力学预测，测量 τ_meas 由物理定律决定——门框的阻力不会陪人演戏，「容器空还是满」由 0.5 N·m 的腕部读数回答，不取决于任何人的回答意愿。于是 R69 的 g_probe 从「摸一下看看」升级为**有设计的力矩实验 g_tq**：微扰位移 ≤ ε_g、力 ≤ f_probe，读取的却是对手（在 A100 威胁模型内）无法伪造的物理签名。同时力矩残差 τ_res 成为第二条「标定不可吸收」异常通道（定义 324），与 R69 的 (r_res, Δa) 镜像互为备份——单通道被吸收不再等于全盲。

**灵感 3（并发推理 → 实时性与可信度第一次同时成立）**
直觉：并发推理给 TORCH 两个红利。**红利一（实时性）**：K 个模态 × |G| 个候选实验的 dry-run 预演是**天然可批量**的——一次 WM 批量前向（CRN：同一噪声种子跨模态复用，使对比反映假设差而非采样差）替代 R69 逐候选串行的期望熵估计，歧义路径延迟几乎不涨；**红利二（可信度）**：N_c 条独立推理路径（互异条件扰动/dropout 种子/N_step）的模态身份一致性，给出**免校准集的在线信任代理**——R69 的 MCG 需要离线 ECE，CCG 在线即可发现「这次采样的模态集不可信」。代价必须诚实声明：路径共享同一 trunk（A101 只假设部分去相关 ρ_c<1），「N_c 路一致」是**必要非充分**条件，共因失败（同一次幻觉的三次回声）是残余风险，交给 CCG disagree 率监控 + E311/E314 验证。

**灵感 4（仿真不定案 → dry-run 自己的证据纪律）**
直觉：预演再逼真也只是模型意见。dry-run 的结果只允许用于三件事：候选排序、预算门控、安全预检；**任何后验更新、λ 计算、模态定案只能由真实观测驱动**（新不变式 iv）。这与 R69 的「单源不得定案」同构：预演是第 k+1 个「源」，但它是仿真源，完整性永远低于任何真实源。这样 WM gap 的最坏后果被限制在「选了个次优实验」，而不是「信了个错结论」（引理 21）。

**灵感 5（证据完整性序 → 物理锚定仲裁）**
直觉：R69 把所有证据等权送入 k-一致裁决；但证据有**范畴级的可信度差**：物理（力矩）> 观测（视觉/几何）> 证言（人话）。PEA 规则：证言与可采纳物理证据冲突 → 证言丢弃并记投毒嫌疑；定案需 ≥1 个非证言源。这正面回应 R69 自陈的「把误导性回答盖上已验证的章」——**人话可以错、可以说谎，但手腕上的 0.5 N·m 不会**（A100 威胁模型内）。

**灵感 6（严格包含姿态 → 三级退避阶梯）**
直觉：与 R69 包含 R68 同理，TORCH 必须**包含** FLUID 为退化边界：τ 通道不可采纳（TPF 拒绝）∧ N_c=1 ∧ dry-run 关闭 ∧ CGX 退化为 MINT 启发式 ⇒ 逐指令等于 R69；再叠加 VoI−c≤0 ∨ ECE>τ_ece ⇒ 逐指令等于 R68。三级阶梯（TORCH→FLUID→CALM）每级退化确定性、可审计、可复现（E308）。新层不引入任何需要独立信任的黑箱——它的每个新能力都有明确的「关掉即回上一级」开关。

## 1. 形式化定义（增量：定义 310–326）

**定义 310（TORCH-RAS 总览）** TORCH-RAS = (CGX, DRY, CON, TOR/TPF, PEA, CCG, FLUID-RAS†)。继承 R69 三不变式（零学习写操作；交互预算硬约束；k 源证据纪律），新增两条：
(iv) **仿真不定案纪律**：dry-run（定义 314）结果只用于候选排序、预算门控与安全预检；后验、λ、模态定案只由真实观测驱动；
(v) **物理锚定与并发确定性**：证据完整性序 Θ_phys ≻ Θ_obs ≻ Θ_testi（定义 318），证言不得推翻可采纳物理证据；并发汇聚为确定性单写者（定义 315b），竞争态不得写入控制缓冲。

**定义 311（力矩签名与残差）** 模态 m_k 与增广动作 ξ 下，认证 WM 给出预测扭矩轨迹 τ̂_k(ξ) = g_WM(ŝ_{t:t+W}, ξ | m_k)；测量 τ_meas；混合残差 τ_res = τ_meas − Σ_k ŵ_k τ̂_k，逐模态残差 τ_res,k = τ_meas − τ̂_k。力矩空间 Y_τ ⊂ ℝ^{d_τ} 并入结果空间 y = (y_vis, y_geo, y_τ)，对比度在联合空间上计算。

**定义 312（对比度）** C(g) = Σ_{i<j} ŵ_i ŵ_j · TV( p(·|m_i, g, ŝ_t) , p(·|m_j, g, ŝ_t) )，p 为执行 g 后 W 步内的结果分布。C 度量「当前信念下该实验能制造多少假设分离」；A99 保证存在 g 使 C(g) ≥ γ_min > 0（实验可设计性）。

**定义 313（CGX 对比实验设计器）** g* = argmax_{g∈𝒜_info} [C(g) − c(g)] s.t. 预算未超 ∧ C-RAS-WM 认证（信息动作安全，R69 定义 302 保持）。候选类扩展：g_gaze、g_probe、g_ask、**g_tq（力矩探针：位移 ≤ ε_g、力 ≤ f_probe、时长 ≤ t_probe）**。若 max[C−c] ≤ 0 → 不交互，退 FLUID 决策。

**定义 314（DRY 并发仿真预演）** 对候选集 G 与模态集 {m_k}，以 common random numbers（同一噪声种子跨模态复用）批量前向 WM：ŷ_{kj} = WM_{H_d}(·|m_k, g_j, ŝ_t)，得 Ĉ(g_j) 与 bootstrap 置信区间 CI(Ĉ)。用途白名单：{候选排序, 预算门控, 安全预检}（不变式 iv）；禁用清单：{后验更新, λ 计算, 模态定案}。

**定义 315（CON 并发推理调度器）** (a) 批量化：K 个流样本与 N_c 条独立路径（互异条件扰动/dropout 种子/N_step）单批执行；(b) **确定性汇聚**：单写者缓冲，规则「最后通过认证者胜出」，无锁竞争、无部分写入；(c) **降载阶梯**：预测批次超 P99 预算时依序关闭 {dry-run → N_c=1 → K=4→1 → 退 FLUID 决策}，λ 单调不降（定理 19b）。

**定义 316（TOR 证据通道与 TPF 信任滤波）** 力矩证据 admissible ⇔ (a) 力矩标定自身残差 τ_cal_res ∈ 界内；(b) 未检出力矩侧「标定吸收」对偶模式（定义 324：τ_res↓ ∧ Δa_τ↑）。不可采纳时本次弃权（权重 0），通道不弃用、待窗口恢复。

**定义 317（CCG 并发一致性门）** agree ⇔ N_c 条路径的 top-1 模态身份（聚类容差内）一致 ∧ H_mode 分歧 ≤ τ_ccg。disagree ⇒ U_epi 升格为未消解、禁用本次交互决策（λ 走未消解分支）。CCG 是**在线、免校准集**的信任代理，补 R69 MCG 需离线 ECE 之缺；两者并存：MCG 管分布级校准（离线），CCG 管本次采样可信（在线）。

**定义 318（PEA 物理锚定证据仲裁）** (a) 完整性序：Θ_phys ≻ Θ_obs ≻ Θ_testi；(b) 证言与可采纳物理证据冲突 → 证言丢弃 + 投毒嫌疑记录（回灌 AuditBuf）；(c) 定案条件升级 R69 定义 293-iii：需 k−1 个正交源一致**且其中 ≥1 个非证言源**；(d) 物理证据自身须过 TPF（定义 316）。

**定义 319（三级退避阶梯）** L0 TORCH 完全态；L1 → FLUID 决策（触发：CGX 不可行 ∨ CCG disagree ∨ TPF 拒绝且需要交互）；L2 → R68 纯保守（触发：VoI−c≤0 ∨ ECE>τ_ece ∨ slow_fault_suspect）。每级退化逐指令确定、可审计（E308 验证边界等价）。

**定义 320（锚定后验更新）** 输入 (g*, y_real, 证据格)；顺序：物理证据削枝（排除与 τ 签名矛盾的模态）→ 贝叶斯权重更新 → k-一致纪律裁决（R69 引理 18 边界在 PEA 下收紧，见引理 20）。

**定义 321（自适应 K 与 N_c 调度）** mode_head 报歧义 → K=4；K>1 且预算富余 → N_c=3；CCG 历史 disagree 率高 → 冻结交互决策若干步（走 L1）。全部由 P99 预算器仲裁（定义 315c）。

**定义 322（威胁模型 ℰ_TORCH）** ℰ_TORCH = ℰ_FLUID × ℰ_phys × ℰ_conc；ℰ_phys = 力矩通道欺骗 / 配重构陷 / 力矩标定吸收慢变故障；ℰ_conc = 并发共因失败 / 汇聚竞争 / 降载时序错乱。**A100 显式声明执行器级构陷在威胁模型之外**（该前提的脆弱性在风险区诚实声明）。

**定义 323（证书 J_TORCH）** J_TORCH = (J_FLUID, τ_res_p95, contrast_achieved, ccg_agree_rate, dryrun_gap_p95, tpf_admit_rate, torch_ver)。Valid ⇔ Valid(J_FLUID) ∧ τ 通道 admissible ∧ ccg_agree_rate ≥ τ_ccg ∧ 降载事件入审计日志。

**定义 324（力矩-行为对偶：反吸收第二镜像）** 慢变故障被力矩标定吸收 ⇒ τ_res≈0；但若偏移改变负载动力学且方向偏离策略主脊，Δa_τ = |a_score^τ(o) − a_score^τ(o_cal^τ)| 上升。(τ_res↓, Δa_τ↑) = 力矩侧缓变故障判别联合模式——R69 引理 17 在力矩侧的镜像；(r_res, Δa) 与 (τ_res, Δa_τ) 两个镜像互为备份，单通道被吸收不再等于全盲。

**定义 325（风险缩放与预算红利）** λ 语义与 R68/R69 完全一致：λ = max(efs.risk_scale, λ_floor(U_ale + 未消解 U_epi))。resolution bonus 扩展：对比设计提高单位交互的期望熵降（引理 19a）⇒ 同预算内更多歧义被消解 → 纯效率侧收益，安全侧公式不变。

**定义 326（确定性退化保证）** 任何失效事件 e ∈ {超时, 降载, CCG disagree, TPF 拒绝, 投毒嫌疑} 映射到唯一阶梯级别（定义 319）；映射确定性、审计可查；控制连续性由 R68 定理 15（提交/换装不变式）在所有级别保持。

## 2. 关键算法骨架

```python
# IP-264/265 CGX + DRY：对比实验设计与并发预演（CRN：跨模态同种子）
def design_contrastive_experiment(modes, w, state, G, wm, budget):
    best = None
    for g in G:                                        # gaze / probe / ask / g_tq
        if not budget.allow(g) or not c_ras_wm.certify_info(g, state):
            continue
        ys = wm.batch_rollout([m.prototype for m in modes], g, state,
                              H=H_DRY, crn=True)       # [K, W, d_y]，一次批调用
        C_hat = contrast(ys, w)                        # 定义 312；含 bootstrap CI
        score  = C_hat.mean - cost(g)
        if C_hat.ci_upper() - cost(g) <= 0: continue   # CI 含 0 → 无对比价值
        if best is None or score > best.score: best = (g, score, C_hat)
    return best if best and best.score > 0 else None   # 无利可图 → 退 FLUID

# IP-267/268 TOR + TPF：力矩签名、残差与信任滤波
def torque_evidence(wm, modes, w, tau_meas, tau_cal):
    tau_hat = sum(w[k] * wm.torque_signature(modes[k]) for k in range(len(modes)))
    tau_res = tau_meas - tau_hat
    admissible = (abs(tau_cal.residual) < TAU_CAL_BOUND
                  and not tau_cal.absorption_suspect)  # 定义 324 对偶检查
    return tau_res, admissible                         # 不可采纳 → 本次弃权

# IP-269 CCG：并发一致性门（免校准集的在线信任代理）
def concurrent_consensus(fmp, o_t, N_c):
    paths   = fmp.sample_batched(o_t, K, seeds=perturb_seeds(N_c))  # 单批并发
    top_ids = [cluster_top_id(p) for p in paths]
    agree   = (len(set(top_ids)) == 1
               and hmode_spread(paths) <= TAU_CCG)
    return agree, paths[0]                             # disagree → 禁交互、升格 U_epi

# IP-270 PEA：物理锚定证据仲裁
def arbitrate(modes, phys, obs, testi):
    if phys.admissible:
        modes = prune_by_torque(modes, phys)           # 物理证据先削枝
        if testi.conflicts(phys):
            audit.poison_suspect(testi); testi = None  # 证言冲突即弃
    agree = k_orthogonal_agree([phys, obs, testi],
                               k=2, require_non_testimonial=True)
    return bayes_update(modes, agree)                  # 定案需 ≥1 非证言源

# IP-274 主闭环（继承 FLUID_RAS_round，替换其交互决策与证据段）
def TORCH_RAS_round(M, obs):
    z, o = M.mtm.forward(...)                          # R68 一次前向
    c, U_cal, thr = M.cof.step(...)
    # 1) 并发采样 + 一致性门（降载阶梯在 CON 内部执行）
    K = 1 if M.fmp.mode_head(z) < TAU_MODE else 4
    agree, samples = M.con.consent(M.fmp, o, N_c=M.sched.N_c(K, M.budget))
    U_ale, U_epi, modes, _ = M.aud.decompose(samples, z, M.fmp.mode_head)
    # 2) 双对偶异常：行为似然（R69）+ 力矩残差（本轮镜像）
    a_hat = M.fma.flow_anomaly(M.fmp, M.last_action, o_obs, o_cal)
    t_res, t_ok = M.tor.torque_evidence(M.wm, modes, w_of(modes),
                                        obs.tau, M.tau_cal)
    slow = ((a_hat > TAU_FMA and M.last_r_res < TAU_RES)
            or (t_res > TAU_TRES and M.tau_cal.absorption_suspect))
    # 3) 交互决策：CGX 对比设计 + DRY 预演（仿真只排序，不定案）
    g = None
    if U_epi > TAU_EPI and agree and not slow and M.mcga.ece_ok():
        g = M.cgx.design(modes, o, G=info_candidates(modes) + [G_TQ],
                         wm=M.wm, budget=M.budget)     # 含 dry-run 排序
    if g is not None:
        y_real = M.cia.execute(g)                      # 真实交互（认证+预算）
        t_res2, t_ok2 = M.tor.observe(y_real)          # 力矩证据随交互回收
        U_epi_after = M.pea.arbitrate(modes, phys=(t_res2, t_ok2),
                                      obs=y_real, testi=y_real.testi)
    else:
        U_epi_after = U_epi                            # 走 319 阶梯
    # 4) 风险缩放（语义与 R68/R69 完全一致）
    U_floor = U_ale + (U_epi_after if g is None else 0.0)
    lam = max(M.efs.risk_scale(...), lam_floor(U_floor))
    A = M.ach.propose(x_prime, H=M.vista.H)
    k = M.c_ras_wm.certified_prefix(A, ..., wm_preds)
    if slow:
        lam = max(lam, 0.8); k = min(k, k_cal_shrink(A, U_cal))
    mode = select_mode(modes, U_epi_after, lam)
    tau  = M.pi_sigma.prefix_dispatch(mode.a[:k]) * lam
    # 5) 参与式审计 + 证书（新增 dry-run 差距与 CCG 一致率）
    M.vqa_t.submit_async(g, y_real, gap=(C_hat - C_real), agree, t_res, t_ok)
    return k, lam, mode, (U_ale, U_epi_after, M.j_torch.issue())
```

## 3. 推导

**假设 A99（模态结果可分）** 存在信息动作 g 使任意模态对的条件结果分布 TV ≥ γ_min > 0（实验可设计性）。
**假设 A100（物理证据不可伪造）** 威胁模型排除执行器级构陷（对手不能在不触发力/位包络报警的情况下伪造扭矩签名）；WM 动力学辨识误差 ≤ δ_τ。
**假设 A101（并发部分去相关）** N_c 条路径的条件失败相关性 ≤ ρ_c < 1（互异扰动部分生效）；承认共享 trunk 的共因残余。
**假设 A102（dry-run 偏差有界）** |Ĉ − C| ≤ ε_dr，且用于决策的对比间隔 > 2ε_dr。

**引理 19（对比–信息等价与排序稳定性）** 设 A99、A102。
(a)（信息下界）若 C(g) ≥ γ，则执行 g 观测 y 后的最大后验错误概率 P_err ≤ (K−1)(1−γ)/2（Le Cam 两点界 + 并集），且 VoI(g) = I(M;Y|g) ≥ h(γ)（Fano 型单调下界）；故对比度是 VoI 的可计算代理，「可分的歧义才值得实验」与 R69 引理 16 同型。
(b)（排序稳定性）dry-run 误差 |Ĉ−C| ≤ ε_dr 时，若 C(g₁)−C(g₂) > 2ε_dr 则 CGX 排序不变。CGX 相较 R69 MINT 的本质优势：MINT 依赖学习型答案模型 p̂(y|g,o)，其误差 ε_ans 无界时可翻转排序（在错误的候选上花真实预算）；CGX 的对比由认证 WM 的动力学约束预测给出，误差有界（ε_dr），间隔充分即稳定。
系：**歧义越大、模态越分得开，对比实验越值钱；普遍不可分（C 处处 < γ_min）时应直接保守**——与 R69 引理 16 同型的保守边界。

**引理 20（物理锚定的投毒上界收紧）** 在 A100、TPF 可采纳下，PEA 规则 (b) 使纯证言欺骗只能在「与可采纳物理证据一致」的子空间被采纳；设证言欺骗率 δ_p、源相关 ρ<1、力矩一致滤波通过率 γ_τ∈(0,1]，则错误模态采纳率 ≤ δ_p·ρ^{k−1}·γ_τ + ε_σ，严格收紧 R69 引理 18（新增 γ_τ<1 因子）。绕过 γ_τ 需物理构陷，其风险 ≥ C-RAS-WM 包络报警阈值——在 A100 之外，只有计入 ℰ_phys 才可能。

**引理 21（dry-run 不定案界）** 由不变式 iv，dry-run 只进入候选排序与门控；后验只由真实观测驱动。设对比间隔 ΔC = C(g₁)−C(g₂)、dry-run 噪声 σ_dr，则排序翻转概率 P_flip ≤ 2Φ(−ΔC/(2σ_dr))；TORCH 相较「直接按 R69 MINT」的期望风险差 ≤ P_flip·Δc + P_miss·L_res（Δc 为候选成本差，L_res 为分辨率损失），二者随 ΔC 指数衰减。**WM gap 的最坏后果被限制在「选了次优实验」，不是「信了错结论」**。

**定理 18（TORCH 严格包含 FLUID ⊇ CALM）** 在 A99–A102 下：
(a) 退化等价——TPF 拒绝 ∧ N_c=1 ∧ dry-run 关闭 ∧ CGX 退化为 MINT 启发式时，TORCH 逐指令等于 FLUID-R69；再叠加 VoI−c≤0 ∨ ECE>τ_ece 时逐指令等于 R68（定义 319 阶梯；E308 验证）。
(b) 风险支配——任意状态期望风险 ≤ FLUID（每个新增决策都有保守侧回退且 λ 单调不降）；分辨率红利 ≥ 0，可分模态（A99）上由引理 19a 严格为正。
(c) 五不变式（R69 三条 + iv/v）在所有级别保持。

**定理 19（并发安全、无突变与降载单调）** (a) 并发仅在推理侧发生，零学习写操作不变式保持；汇聚为确定性单写者（定义 315b），竞争态不进入控制缓冲。(b) 降载阶梯使 λ 关于资源压力单调不降，任何降载事件等价于沿定义 326 的确定性退化。(c) CCG disagree 只升格 U_epi、只增 λ、不改安全包络；信息动作仍过 C-RAS-WM 认证（R69 定理 17 保持）；提交/换装不变式（R68 定理 15）在所有级别保持 ⇒ 控制连续、无突变。

## 4. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| FMP 批量采样（K≤4 × N_c≤3 单批） | P99 < 1.0ms | 45MB | 定义 315a；K=1 默认路径 |
| CCG 一致性汇聚 | < 0.05ms | O(N_c) | 定义 317；在线信任代理 |
| DRY 批量预演（\|G\|≤3, W=6, 单次 WM 批调用） | < 0.5ms | O(K·W·d_y) | 定义 314；仅歧义且可交互时触发 |
| CGX 对比计算 + CI | < 0.05ms | O(\|G\|·K²) | 定义 313、引理 19 |
| TOR 残差 + TPF（被动读取） | < 0.05ms | O(d_τ) | 定义 311/316 |
| PEA 仲裁 | < 0.05ms | O(k²) | 定义 318 |
| **实时环路总延迟** | **< 2.7ms**（K=1 常规，较 R69 +0.1ms：力矩被动读取与对偶检查）；歧义路径 < 3.9ms（+0.4ms：dry-run 预演与并发一致性）；超支即降载（定义 315c，退 R69 学习型答案模型路径） | — | 定理 18–19 |

## 5. 实验设计 E301–E315

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 力矩签名可分性 | τ̂_k 能否区分模态 | 模态对 τ 签名 TV ≥ γ_min 覆盖率 ≥ 85% |
| E302 对比设计 vs 被动 VoI | CGX 是否选对实验 | 单位交互熵降 ≥ R69 MINT +40%；成功率 +15%（R69 +12% 之上） |
| E303 dry-run 排序保真 | 预演排序 vs 真实排序 | Spearman ρ ≥ 0.8；排序翻转率 ≤ 10% |
| E304 CCG 检出能力 | 并发一致能否抓幻觉/坍缩 | 幻觉模态检出 ≥ 90%；误禁率 ≤ 3%；免校准集（对比 MCG） |
| E305 力矩构陷抵抗 | 视觉共谋 + 证言欺骗 | 物理锚定下错误采纳 ≤ 0.5%（E290 的 ≤1% 之上） |
| E306 物理锚定仲裁 | 冲突时信谁 | 证言-物理冲突判物理正确率 ≥ 98%；错杀正确证言 ≤ 2% |
| E307 实时预算与降载 | 并发是否守时 | 常规 P99 < 2.7ms；歧义 < 3.9ms；降载后行为退 FLUID 且零违例 |
| E308 三级阶梯逐指令一致 | 退化边界等价 | TORCH→FLUID→R68 各级行为差 = 0 |
| E309 分辨红利 | 同预算消解更多歧义 | 交互次数 −25%（同等成功率）；resolution bonus 净增 |
| E310 力矩侧慢变故障 | 配重漂移被力矩标定吸收 | (τ_res↓, Δa_τ↑) AUC ≥ 0.85（引理 17 的力矩镜像） |
| E311 消融 | CGX/DRY/TOR/CCG/PEA 贡献 | 去 CGX 退 R69；去 TOR 构陷抵抗 −60%；去 CCG 幻觉追问 ×3 |
| E312 24h 长时程 | 力矩漂移 × 交互疲劳 | τ 标定漂移下零交互诱发违规；降载事件全程可审计 |
| E313 OOD 力矩分布 | 新物体/新负载 | OOD 检出 ≥ 90%，误报 ≤ 5% |
| E314 并发压力测试 | 负载高峰行为 | P99 超支 = 0；降载触发率与 λ 单调性验证 |
| E315 幻影模态追问（对比门控版） | E300 的 5% 之上 | 追问幻影 ≤ 2%；CI(Ĉ) 含 0 时追问 = 0 |

## 6. 本轮最大风险

**一句话**：TORCH 把「向谁求证」的最终信任押在「物理不会说谎」上——但「力矩不可伪造」只是 A100 的一句**声明**（执行器级构陷被排除在威胁模型之外），一旦对手能通过接触配置/配重/选择性施力制造与某模态一致的扭矩签名，力矩证据就从「不可贿赂的证人」变成「最易被构陷的证人」；同时 N_c 条并发路径共享同一 trunk，「N_c 路一致」可能只是同一次幻觉的三次回声——**一致不等于正确**，而这正是 R69 风险（在错误信念上自信行动）的并发版放大。

**次级风险与缓解**：
1. dry-run 与真实的偏差（WM gap）→ 仿真不定案纪律 + 引理 21 + E303 保真度验证；最坏后果限于「选次优实验」；
2. 力矩标定自身被吸收（R68 教训的力矩版）→ TPF 信任滤波 + 定义 324 对偶 + E310；
3. 并发共因失败（一致 = 回声）→ 互异条件扰动去相关 + CCG disagree 率监控 + E311/E314；诚实声明：一致性是必要非充分条件；
4. 预算击穿 → 降载阶梯（定义 315c）+ E307/E314；
5. 对比度普遍偏低（Δ_min 小、模态不可分）→ 引理 19 系：不可分时直接保守（与 R69 引理 16 同型边界），交互预算不浪费。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 70 轮产物 · 创新点清单 v1：TORCH-RAS（Torque-gROunded Contrastive Hypothesis-testing with Concurrent inference：力矩锚定 × 对比实验设计 × 并发推理的物理证据闭环；CGX×DRY×CON×TOR/TPF×PEA×CCG×FLUID-RAS†）

> 承接第 69 轮 IP-253~263（FLUID-RAS）。R69 让系统「会问」，但全部效率收益押在「流模型模态分布可信」上，且「问」的答案来自可能说谎的证人。本轮把「向证人求证」升级为「让物理作证」：消歧动作 = 对比实验（设计 + 并发预演 + 真实执行），证据按完整性序仲裁（物理≻观测≻证言），模态分布自身可信度由并发一致性在线把关。定位：R69 问「我该向谁求证、还能问什么」，R70 问「**谁的答案无法说谎**」——不再问证人，让世界在一场设计好的对比实验里自己作证。
>
> IP 编号：IP-264~IP-274（共 11 个）；理论姿态：TORCH 以**三级退避阶梯**严格包含 FLUID-R69 ⊇ CALM-R68，安全侧不做任何让步；新增两条不变式（仿真不定案、物理锚定与并发确定性）。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 69 轮） |
|---|---|---|---|
| IP-264 | CGX Contrastive-Guided eXperiment designer | 升级 MINT（IP-255） | VoI 启发式 → 对比度最大化实验设计；对比由认证 WM 动力学约束预测计算（误差有界、排序稳定，引理 19b）；新增力矩探针候选 g_tq |
| IP-265 | DRY in-silico DrY-run renderer | 新增 | K×\|G\| 实验×模态批量预演（CRN 同种子）+ bootstrap CI；只排序不定案（新不变式 iv） |
| IP-266 | CON CONcurrent inference Scheduler | 新增 | 批量化流采样（K×N_c 单批）、确定性单写者汇聚、降载阶梯（dry-run→N_c=1→K=1→退 FLUID） |
| IP-267 | TOR TORque-grounded evidence channel | 新增 | 逐模态力矩签名 τ̂_k + 混合残差 τ_res；威胁模型内不可伪造的物理证据通道（A100） |
| IP-268 | TPF Torque-evidence Trust Filter | 新增 | 力矩通道自身的标定感知可采纳性；防「R68 式吸收」在力矩侧重演；不可采纳 → 本次弃权 |
| IP-269 | CCG Concurrent Consensus Gate | 新增 | N_c 路独立推理的模态身份一致 + H_mode 分歧检查；免校准集在线信任代理，补 R69 MCG 需离线 ECE 之缺 |
| IP-270 | PEA Physics-anchored Evidence Arbiter | 升级证据纪律（R69 定义 293-iii） | 完整性序 物理≻观测≻证言；证言冲突即弃并记投毒嫌疑；定案需 ≥1 非证言源 |
| IP-271 | VQAuditor-T | 升级 VQAuditor-I | 审计实验设计针对性、dry-run/真实对比差距、TPF 弃权率、CCG disagree 率、降载事件 |
| IP-272 | AIC-TORCH | 升级 AIC-FLUID | ℰ_TORCH = ℰ_FLUID × ℰ_phys × ℰ_conc（力矩构陷 / 共因失败） |
| IP-273 | J_TORCH | 升级 J_FLUID | + τ_res_p95、contrast_achieved、ccg_agree_rate、dryrun_gap_p95、tpf_admit_rate |
| IP-274 | TORCH-RAS Pipeline | 新增 | FLUID 闭环 + 并发一致性门 → 对比实验设计 → 并发预演 → 力矩锚定仲裁 → 三级退避阶梯 |

## 1. 符号体系增量（定义 310–326）

| 符号 | 含义 |
|---|---|
| `TORCH-RAS = (CGX, DRY, CON, TOR/TPF, PEA, CCG, FLUID-RAS†)` | 力矩锚定对比实验闭环（FLUID 为退化边界） |
| `τ̂_k(ξ), τ_meas, τ_res` | 模态 k 力矩签名 / 测量扭矩 / 混合残差 |
| `g_tq` | 力矩探针（位移 ≤ ε_g、力 ≤ f_probe 的有设计微扰实验） |
| `C(g) = Σ_{i<j} ŵ_i ŵ_j TV(p(·\|m_i,g), p(·\|m_j,g))` | 对比度（VoI 的动力学约束代理） |
| `Ĉ(g), CI(Ĉ)` | dry-run 对比估计与置信区间（CRN 同种子；只排序不定案） |
| `N_c, agree` | 并发推理路径数 / CCG 一致性判定 |
| `Θ_phys ≻ Θ_obs ≻ Θ_testi` | 证据完整性序（PEA 仲裁） |
| `Δa_τ = \|a_score^τ(o) − a_score^τ(o_cal^τ)\|` | 力矩侧行为似然差（反吸收第二镜像） |
| `(τ_res↓, Δa_τ↑)` | 力矩侧缓变故障判别联合模式（定义 324） |
| `γ_min, ε_dr, γ_τ, ρ_c` | 可分性下界（A99）/ dry-run 偏差界（A102）/ 力矩滤波通过率 / 并发相关上界（A101） |
| `J_TORCH = (J_FLUID, τ_res_p95, contrast_achieved, ccg_agree_rate, dryrun_gap_p95, tpf_admit_rate, torch_ver)` | 证书 |

## 2. 形式化定义（要点版）

**定义 310（总览与五不变式）** TORCH-RAS = (CGX, DRY, CON, TOR/TPF, PEA, CCG, FLUID-RAS†)；继承 R69 三不变式，新增：(iv) 仿真不定案（dry-run 只排序/门控/预检，定案只由真实观测驱动）；(v) 物理锚定与并发确定性（物理≻观测≻证言；单写者汇聚，竞争态不进控制缓冲）。

**定义 311–312（力矩签名与对比度）** τ̂_k 为认证 WM 在模态 m_k 下的扭矩轨迹预测，τ_res 为混合残差；C(g) = Σ_{i<j} ŵ_i ŵ_j·TV(p_i, p_j) 度量实验制造的假设分离，A99 保证可设计性（∃g: C ≥ γ_min）。

**定义 313–314（CGX 与 DRY）** g* = argmax[C(g) − c(g)] s.t. 预算 ∧ C-RAS-WM 认证，候选含力矩探针 g_tq；dry-run 以 CRN 批量预演得 Ĉ + CI，白名单 {排序, 门控, 预检}，禁入 {后验, λ, 定案}。max[C−c] ≤ 0 → 不交互、退 FLUID。

**定义 315–317（CON/TPF/CCG）** 批量化采样 + 确定性单写者汇聚 + 降载阶梯（λ 单调不降）；力矩证据 admissible ⇔ 力矩标定残差在界内 ∧ 无吸收对偶（定义 324）；CCG：N_c 路模态身份一致 ∧ H_mode 分歧 ≤ τ_ccg，disagree ⇒ 禁交互、U_epi 升格（在线免校准集，补 R69 MCG 之缺）。

**定义 318–320（PEA 与锚定后验）** 证言与可采纳物理证据冲突即弃并记投毒嫌疑；定案需 k−1 正交源一致且 ≥1 非证言源；更新顺序：物理削枝 → 贝叶斯更新 → k-一致裁决（R69 引理 18 边界收紧为引理 20）。

**定义 321–323（调度/威胁/证书）** mode_head 报歧义 → K=4、预算富余 → N_c=3、disagree 率高 → 冻结交互；ℰ_TORCH = ℰ_FLUID × ℰ_phys × ℰ_conc（A100 声明执行器级构陷在模型外）；J_TORCH 并入 τ_res_p95、contrast_achieved、ccg_agree_rate、dryrun_gap_p95、tpf_admit_rate。

**定义 324–326（对偶/风险/退化）** (τ_res↓, Δa_τ↑) 为力矩侧缓变故障判别模式（R69 引理 17 的镜像，双镜像互为备份）；λ 语义与 R68/R69 完全一致，对比设计只带来效率侧预算红利；任何失效事件映射到三级阶梯（TORCH→FLUID→CALM）的唯一级别，退化确定性可审计。

## 3. 关键算法伪代码

```python
# IP-264/265 CGX+DRY：对比实验设计 + 并发预演（CRN 跨模态同种子）
def design_contrastive_experiment(modes, w, state, G, wm, budget):
    best = None
    for g in G:                                   # gaze/probe/ask/g_tq(力矩探针)
        if not budget.allow(g) or not c_ras_wm.certify_info(g, state): continue
        ys = wm.batch_rollout([m.prototype for m in modes], g, state,
                              H=H_DRY, crn=True)   # [K,W,d_y] 一次批调用
        C = contrast(ys, w)                        # 定义 312 + bootstrap CI
        if C.ci_upper() - cost(g) <= 0: continue   # CI 含 0 → 无对比价值
        s = C.mean - cost(g)
        if best is None or s > best.s: best = (g, s, C)
    return best if best and best.s > 0 else None   # 无利可图 → 退 FLUID

# IP-267/268 TOR+TPF：力矩证据与信任滤波（防力矩侧标定吸收）
def torque_evidence(wm, modes, w, tau_meas, tau_cal):
    tau_hat = sum(w[k]*wm.torque_signature(modes[k]) for k in range(len(modes)))
    return tau_meas - tau_hat, (abs(tau_cal.res) < TAU_CAL_BOUND
                                and not tau_cal.absorption_suspect)

# IP-269 CCG：并发一致性门（免校准集在线信任代理，补 R69 MCG 之缺）
def concurrent_consensus(fmp, o_t, N_c):
    paths = fmp.sample_batched(o_t, K, seeds=perturb_seeds(N_c))
    top = [cluster_top_id(p) for p in paths]
    return len(set(top)) == 1 and hmode_spread(paths) <= TAU_CCG, paths[0]

# IP-270 PEA：物理锚定证据仲裁（物理≻观测≻证言）
def arbitrate(modes, phys, obs, testi):
    if phys.admissible:
        modes = prune_by_torque(modes, phys)
        if testi.conflicts(phys): audit.poison_suspect(testi); testi = None
    return bayes_update(modes, k_orthogonal_agree(
        [phys, obs, testi], k=2, require_non_testimonial=True))

# IP-274 主闭环（继承 FLUID_RAS_round，替换交互决策与证据段）
def TORCH_RAS_round(M, obs):
    z, o = M.mtm.forward(...); c, U_cal, thr = M.cof.step(...)
    K = 1 if M.fmp.mode_head(z) < TAU_MODE else 4
    agree, samples = M.con.consent(M.fmp, o, N_c=M.sched.N_c(K, M.budget))
    U_ale, U_epi, modes, _ = M.aud.decompose(samples, z, M.fmp.mode_head)
    a_hat = M.fma.flow_anomaly(M.fmp, M.last_action, o_obs, o_cal)
    t_res, t_ok = M.tor.torque_evidence(M.wm, modes, w_of(modes),
                                        obs.tau, M.tau_cal)
    slow = ((a_hat > TAU_FMA and M.last_r_res < TAU_RES)
            or (t_res > TAU_TRES and M.tau_cal.absorption_suspect))  # 双对偶
    g = (M.cgx.design(modes, o, G=info_candidates(modes)+[G_TQ], wm=M.wm,
                      budget=M.budget)
         if (U_epi > TAU_EPI and agree and not slow and M.mcga.ece_ok()) else None)
    if g is not None:
        y = M.cia.execute(g); t2, ok2 = M.tor.observe(y)
        U_epi = M.pea.arbitrate(modes, (t2, ok2), y, y.testi)
    U_floor = U_ale + (U_epi if g is None else 0.0)
    lam = max(M.efs.risk_scale(...), lam_floor(U_floor))
    A = M.ach.propose(x_prime, H=M.vista.H)
    k = M.c_ras_wm.certified_prefix(A, ..., wm_preds)
    if slow: lam = max(lam, 0.8); k = min(k, k_cal_shrink(A, U_cal))
    mode = select_mode(modes, U_epi, lam)
    tau = M.pi_sigma.prefix_dispatch(mode.a[:k]) * lam
    M.vqa_t.submit_async(g, y, gap=(C_hat - C_real), agree, t_res, t_ok)
    return k, lam, mode, (U_ale, U_epi, M.j_torch.issue())
```

## 4. 推导

**假设 A99–A102** 模态结果可分（∃g: TV ≥ γ_min）；物理证据不可伪造（排除执行器级构陷，WM 辨识误差 ≤ δ_τ）；并发部分去相关（ρ_c < 1，承认共因残余）；dry-run 偏差有界（|Ĉ−C| ≤ ε_dr，决策间隔 > 2ε_dr）。

**引理 19（对比–信息等价与排序稳定性）** (a) C(g) ≥ γ ⇒ 单次观测后验错误 P_err ≤ (K−1)(1−γ)/2（Le Cam + 并集），VoI ≥ h(γ)（Fano 型）——对比度是 VoI 的可计算代理；(b) |Ĉ−C| ≤ ε_dr 时 C(g₁)−C(g₂) > 2ε_dr 则排序不变——CGX 修复 R69 MINT 学习型答案模型误差无界、可翻转排序的缺陷。系：普遍不可分时直接保守（与 R69 引理 16 同型边界）。

**引理 20（物理锚定的投毒上界收紧）** A100 + TPF 可采纳下，纯证言欺骗只能在「与物理证据一致」的子空间被采纳：错误采纳率 ≤ δ_p·ρ^{k−1}·γ_τ + ε_σ，严格收紧 R69 引理 18（新增 γ_τ<1 因子）；绕过 γ_τ 需物理构陷（A100 之外）。

**引理 21（dry-run 不定案界）** 不变式 iv 下，WM gap 只影响候选排序：P_flip ≤ 2Φ(−ΔC/(2σ_dr))，期望风险差 ≤ P_flip·Δc + P_miss·L_res，随 ΔC 指数衰减——**最坏后果是「选次优实验」，不是「信错结论」**。

**定理 18（TORCH 严格包含 FLUID ⊇ CALM）** TPF 拒绝 ∧ N_c=1 ∧ dry-run 关 ∧ CGX 退化为 MINT 启发式 ⇒ 逐指令等于 FLUID；叠加 VoI−c≤0 ∨ ECE>τ_ece ⇒ 逐指令等于 R68（E308 验证）。任意状态期望风险 ≤ FLUID，分辨率红利 ≥ 0（A99 上严格为正），五不变式全程保持。

**定理 19（并发安全、无突变与降载单调）** 并发仅在推理侧（零写不变式保持）；确定性单写者汇聚，无竞争态；降载阶梯使 λ 关于资源压力单调不降；CCG disagree 只升格 U_epi、只增 λ、不改安全包络；信息动作仍过 C-RAS-WM 认证、换装不变式（R68 定理 15）保持 ⇒ 控制连续、无突变。

## 5. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| FMP 批量采样（K≤4 × N_c≤3 单批） | P99 < 1.0ms | 45MB | 定义 315a；K=1 默认 |
| CCG 一致性汇聚 | < 0.05ms | O(N_c) | 定义 317 |
| DRY 批量预演（\|G\|≤3, W=6） | < 0.5ms | O(K·W·d_y) | 定义 314；仅歧义且可交互触发 |
| CGX 对比 + CI | < 0.05ms | O(\|G\|·K²) | 定义 313、引理 19 |
| TOR 残差 + TPF（被动） | < 0.05ms | O(d_τ) | 定义 311/316 |
| PEA 仲裁 | < 0.05ms | O(k²) | 定义 318 |
| **实时环路总延迟** | **< 2.7ms**（K=1 常规，较 R69 +0.1ms）；歧义 < 3.9ms（+0.4ms）；超支即降载退 R69 路径 | — | 定理 18–19 |

## 6. 实验设计 E301–E315

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 力矩签名可分性 | τ̂_k 能否区分模态 | 模态对 τ 签名 TV ≥ γ_min 覆盖率 ≥ 85% |
| E302 对比设计 vs 被动 VoI | CGX 是否选对实验 | 单位交互熵降 ≥ MINT +40%；成功率 +15% |
| E303 dry-run 排序保真 | 预演 vs 真实排序 | Spearman ρ ≥ 0.8；翻转率 ≤ 10% |
| E304 CCG 检出能力 | 并发一致能否抓幻觉/坍缩 | 检出 ≥ 90%；误禁率 ≤ 3%；免校准集 |
| E305 力矩构陷抵抗 | 视觉共谋 + 证言欺骗 | 物理锚定下错误采纳 ≤ 0.5%（E290 ≤1% 之上） |
| E306 物理锚定仲裁 | 冲突时信谁 | 判物理正确率 ≥ 98%；错杀正确证言 ≤ 2% |
| E307 实时预算与降载 | 并发是否守时 | 常规 P99 < 2.7ms；歧义 < 3.9ms；降载零违例 |
| E308 三级阶梯逐指令一致 | 退化边界等价 | TORCH→FLUID→R68 行为差 = 0 |
| E309 分辨红利 | 同预算消解更多歧义 | 交互次数 −25%（同等成功率） |
| E310 力矩侧慢变故障 | 配重漂移被力矩标定吸收 | (τ_res↓, Δa_τ↑) AUC ≥ 0.85 |
| E311 消融 | CGX/DRY/TOR/CCG/PEA 贡献 | 去 CGX 退 R69；去 TOR 构陷抵抗 −60%；去 CCG 幻觉追问 ×3 |
| E312 24h 长时程 | 力矩漂移 × 交互疲劳 | 漂移下零交互诱发违规；降载全程可审计 |
| E313 OOD 力矩分布 | 新物体/新负载 | 检出 ≥ 90%，误报 ≤ 5% |
| E314 并发压力测试 | 负载高峰行为 | P99 超支 = 0；降载触发率与 λ 单调性验证 |
| E315 幻影模态追问（对比门控版） | E300 的 5% 之上 | 追问幻影 ≤ 2%；CI(Ĉ) 含 0 时追问 = 0 |

## 7. 本轮最大风险

**一句话**：TORCH 把「向谁求证」的最终信任押在「物理不会说谎」上——但「力矩不可伪造」只是 A100 的一句**声明**（执行器级构陷被排除在威胁模型之外），一旦对手能通过接触配置/配重/选择性施力制造与某模态一致的扭矩签名，力矩证据就从「不可贿赂的证人」变成「最易被构陷的证人」；同时 N_c 条并发路径共享同一 trunk，「N_c 路一致」可能只是同一次幻觉的三次回声——**一致不等于正确**，而这正是 R69 风险（在错误信念上自信行动）的并发版放大。

**次级风险与缓解**：dry-run 偏差（仿真不定案 + 引理 21 + E303，最坏限于选次优实验）；力矩标定被吸收（TPF + 定义 324 对偶 + E310）；并发共因失败（互异扰动去相关 + disagree 率监控 + E311/E314，诚实声明一致≠正确）；预算击穿（降载阶梯 + E307/E314）；对比度普遍偏低（引理 19 系：不可分即保守，不浪费预算）。
<!-- ARTIFACT:END -->
