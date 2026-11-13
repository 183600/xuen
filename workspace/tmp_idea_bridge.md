# 第 66 轮（承接第 65 轮「VISTA 视觉知情的安全时序归因」IP-214~223；新一轮灵感循环第 1 轮；本轮灵感：「虚实迁移」×「UniBot-V1」）

> 第 65 轮把「几何可证伪」升级为「故障可归因」，其自述的最大风险是：归因依赖有限故障假设集与「视觉/几何失效相互独立」这两个假设；真实故障常是未知类型的组合，透明/镜面/对抗 patch 会让视觉与几何共享同一个分布外失效源，于是 FIR 会把未知复合故障强行归入最近假设、只膨胀错误的球——系统因为「已经归因」而更自信地继续执行。**根因是：VISTA 只能在已经发生的真实世界里取证，无法对「如果 H 为真，世界会怎样」做反事实实验，也没有一个独立世界来打破共因。** 本轮把「第二世界」引入闭环，核心命题是：
>
> **把数字孪生从训练数据源升级为「可证伪的反事实证人」：用虚实迁移生成安全的虚拟探针，用 UniBot-V1 的统一动作/状态接口做「同动作、双世界」配对，用迁移证书把仿真中的安全承诺有条件下放到真实世界；并首次把「现实间隙」本身拆成可归因故障。**

## 0. 直觉与动机

**灵感 1（虚实迁移 → 反事实证据，而不只是数据增广）**
直觉：VISTA 的主动故障归因（AFA）只能从真实物理探针里选，代价是接触、力、甚至压坏易损物；更致命的是，真实世界只能告诉你「发生了什么」，不能告诉你「如果几何幻觉为真，这个世界会怎样」。数字孪生恰好能对每个故障假设做反事实 rollout：在孪生里注入 H_geo/H_force/H_model/H_gap，跑同一组候选探针，看哪种证据最能分开它们。于是探针选择从「真实试错」变成「**虚拟探针拍卖（VPA）**：先在孪生里免费试遍所有探针，再在真实世界只执行信息量/风险比最高的那一两个」。但必须诚实：孪生有现实间隙，越自信的孪生越危险；所以孪生**不是新真值，而是第三位可错证人**，它的证据必须与真实证据配对校验。

**灵感 2（虚实迁移 → 现实间隙本身就是一种故障）**
直觉：VISTA 把「几何/力/模型/视觉/策略」当作故障，却把 sim-to-real gap 当噪声或 domain randomization。可 gap 是有结构的：物理参数错、渲染/光照错、执行器增益/延迟错、接触模型错、具身/动作空间错。这些结构在真实与孪生的配对残差里留下不同签名，完全可以像 H_geo/H_force 一样被归因。把 gap 升格为 **H_gap_phys / H_gap_vis / H_gap_act / H_gap_lat / H_gap_emb** 后，系统第一次能回答「到底是真实世界坏了，还是孪生坏了，还是两者共享了同一个坏假设」。这也是对第 65 轮共因风险的正面对冲。

**灵感 3（UniBot-V1 → 统一动作接口创造「同动作、双世界」的可配对性）**
直觉：没有公共动作坐标，就无法把仿真和真实逐帧对齐：同样的任务，仿真里是关节力矩，真实里是末端增量，残差里混着接口差异，gap 根本估不准。UniBot-V1 的规范把不同具身映射到 **54 维动作 / 60 维状态 / 默认 H=30 的动作块（30fps）**，并支持二指夹爪与多种五指手；UnifoLM-WLA-1.0 又在约 2500 小时真机数据上给出跨桌面与全身任务的先验。于是可以构造 **UAI（UniBot Action Interface）配对缓冲**：同一动作块 a_{t:t+H} 在孪生与真实各 rollout 一次，逐维比较状态/接触/视觉后果，得到干净的 gap 签名。注意：6B 基础模型只在语义流做先验，实时流用蒸馏块策略；基础模型本身也可错，记为 H_foundation，绝不当作真值。

**灵感 4（三灵感合流 → BRIDGE：双向现实间隙识别与数字孪生接地的安全执行闭环）**
直觉：VISTA 是「真实世界内的故障归因」；BRIDGE 是「跨世界的故障归因 + 证书迁移」。闭环为：
**DTG（孪生参数后验/可信集）→ RGI（间隙签名与扩展故障假设）→ VPA（虚拟探针拍卖）→ UAI（同动作双世界配对）→ TCC（迁移证书）→ DTA（真实证据回灌孪生）→ RSC-W（只膨胀被归因的球）→ CSP-W（块级跨世界技能规划）→ AIC-W（跨世界对抗认证）→ J_bridge**。
其中 **sim→real** 的方向是「证书迁移」：只有间隙上界小于安全裕度/李普希茨常数时才下放；**real→sim** 的方向是「孪生校准」：用真实残差更新 θ 后验。两个方向互为约束，缺一不可。

**灵感 5（GRIP/VISTA 组件的原位升级）**
- **VPG → VPG-W**：视觉世界模型在孪生里做反事实 rollout，给 VCV 提供「如果接触斑在这里，孪生会看到什么」的前置对照。
- **ACH → ACH-U**：直接采用 UniBot-V1 的 54/60 维动作/状态与 H=30 块，块间一致性在跨世界配对后计算。
- **FIR → FIR-W**：故障假设集扩为 ℋ⁺ = ℋ ∪ {H_gap_phys, H_gap_vis, H_gap_act, H_gap_lat, H_gap_emb, H_foundation, H_unknown}；未知故障用 SBI 后验预测与开集检验。
- **VCV → VCV-W**：视觉接触验证先在孪生中预演；若孪生与真实都看不到接触，判 `visual_unobservable`，不得否定几何。
- **APP/AFA → VPA**：探针目标从「故障假设互信息」升级为「单位真实风险的迁移感知互信息」，并允许零真实探针回退。
- **CSC → CSC-W**：认证前缀前加一道 **迁移证书**；k* 只在证书可迁移时生效。
- **RSC-V → RSC-W**：不确定球拆为 r_geo / r_force / r_model / r_gap / r_foundation，只膨胀被归因者。
- **WCV-V → WCV-W**：搜索域增孪生可信集 Θ_δ 与迁移半径约束。
- **CSP-V → CSP-W**：技能同时绑定「仿真块签名」与「真实块签名」，两者都通过才入图。
- **AIC-V → AIC-W**：干扰集增物理/渲染/执行器/延迟/具身错配与共因故障；共因下不要求归因正确，只要求拒绝迁移并安全降级。
- **J_vista → J_bridge**：证书增 twin_posterior、transfer_radius、gap_bound、real_probe_budget、unibot_iface_ver、H_unknown_flag。

**与既有路线的区别（为什么不是「sim2real + domain randomization」）**
- 域随机化把 gap 当作要覆盖的分布，追求平均鲁棒；BRIDGE 把 gap 当作要归因的故障，追求「这一次能不能迁移」的可判定性。
- 系统辨识估计 θ，但不回答「证书能不能下放」；TCC 用 Lipschitz + conformal 给出可检查的迁移条件。
- 数字孪生通常用于训练/评测；BRIDGE 把它用作反事实探针生成器与最小真实实验的设计器。
- 基础模型通常被当作策略先验；BRIDGE 把它当作可错假设 H_foundation，不允许它直接产生安全证书。

## 1. 形式化定义（增量：定义 233–248）

- **定义 233（BRIDGE 闭环）**：BRIDGE = (VISTA, DTG, RGI, VPA, UAI, TCC, DTA, RSC-W, CSP-W, AIC-W, J_bridge)。定位：VISTA 的「跨世界故障归因 + 安全证书迁移」升级。不变式：**孪生推断、SBI、虚拟探针拍卖、迁移证书只在语义流；实时流只做配对残差采集、认证前缀执行与早停，零学习写操作。**
- **定义 234（数字孪生集合与参数后验）**：世界参数 θ ∈ Θ（质量/摩擦/恢复系数/接触刚度/执行器增益/延迟/相机内外参等）；先验 p(θ)；孪生 T_θ。用真实配对数据 D 通过 SBI/ABC 得后验 p(θ|D)，并取可信集 Θ_δ={θ: p(θ|D)≥δ}；孪生集合 {T_{θ_i}}_{i=1..M} 表示认知不确定度。
- **定义 235（UniBot 跨世界接口 UAI）**：采用 UniBot-V1 规范：动作 a∈ℝ^54、状态 s∈ℝ^60、默认块长 H=30、30fps，带有效性 mask；同一动作块在孪生与真实各执行一次，得配对轨迹 (s^sim_{t:t+H}, s^real_{t:t+H})。UAI 是 gap 估计与迁移证书的公共坐标；基础模型 UnifoLM-WLA-1.0 仅作语义流先验。
- **定义 236（现实间隙签名）**：配对残差 e_gap(t,h)=d_U(s^sim_{t+h}, s^real_{t+h})，按通道分解为物理/视觉/执行器/延迟/具身五类，按接触阶段聚合为 γ∈ℝ^{d_g}。γ 是 H_gap 类的证据；同时定义证书相关间隙 d_cert(θ_sim, θ_real)=‖θ_sim−θ_real‖_{Σ_θ^{-1}}。
- **定义 237（扩展故障假设集）**：ℋ⁺ = {H0, H_geo, H_force, H_model, H_vis, H_policy, H_gap_phys, H_gap_vis, H_gap_act, H_gap_lat, H_gap_emb, H_foundation, H_unknown}。H_unknown 用开集似然/后验预测覆盖；H_foundation 表示基础模型先验错（动作 token 化、具身错配、幻觉）。
- **定义 238（孪生反事实证据）**：对候选探针 a 与后验样本 θ~p(θ|D)，孪生 rollout 得 ρ_sim(a,θ)；其分布 p_sim(ρ|H,a)=∫p(ρ|θ,H,a)p(θ|D)dθ 是 H 的模拟似然。模拟似然只用于**设计探针与排序假设**，不直接当作真实后验。
- **定义 239（虚拟探针拍卖 VPA）**：候选探针集 A={visual_probe, null_test, press, rub, tap, lift, sim_probe}；对每个 a 计算迁移感知互信息
  I_τ(a)=I_sim(ℋ⁺; ρ_real(a)|D)·λ_τ(γ)，
  其中 λ_τ∈[0,1] 由间隙签名 γ 与孪生可信度给出；真实风险 r(a) 由力/形变/停止距离上界给出。选择
  a*=argmax_{a∈A} I_τ(a)/(r(a)+λ_r)，s.t. r(a*)≤B_probe；
  若 I_τ(a*)<δ_vpa 或 B_probe<r_min，则返回 **no_probe**，退化为纯被动观测。真实世界只执行 a*（通常 0–2 次），其余全部在孪生中完成。
- **定义 240（迁移半径与证书迁移）**：设策略 π 的安全裕度 m(π,θ)=min_{s≤k}ρ_safe(s;θ)，关于 θ 在证书度量下 L_m-Lipschitz。定义迁移半径 r_τ=(m(π,θ_sim)−ε)/L_m。若真实参数以 ≥1−α_gap 的概率落在 B(θ_sim,r_τ) 内（由 DTG 可信集/conformal 给出），则仿真证书可迁移；否则拒绝迁移。
- **定义 241（迁移证书 TCC）**：TCC(π,k)=(θ_sim, r_τ, δ_gap, m_sim, m_lb=m_sim−L_m δ_gap, α_gap, UAI_ver)。可迁移 ⇔ δ_gap≤r_τ ⇔ m_lb≥ε；执行时只用 m_lb 作为真实裕度下界，绝不用 m_sim 冒充真实裕度。
- **定义 242（跨世界故障归因 FIR-W）**：证据 = 真实阶段签名 ρ_real ⊕ 间隙签名 γ ⊕ 孪生模拟似然 p_sim；后验 P(H|ρ_real,γ)∝p(ρ_real|H)p(γ|H)P(H)，其中 H∈ℋ⁺。若 max_H P(H|·)≥1−δ_fi 且拟合优度通过，则定向处置；若后验不集中或所有已知 H 的拟合都很差，则判 H_unknown；若 H_gap 占优，则先更新 DTA、暂缓迁移。
- **定义 243（数字孪生在线适配 DTA）**：用真实配对残差按递归贝叶斯/SBI 更新 p(θ|D)；维护间隙变点检测，一旦 γ 的分布漂移超过阈值，立即作废当前 TCC 并重估 r_τ。只在语义流更新，实时流不写。
- **定义 244（RSC-W 归因定向球）**：维护 r_geo、r_force、r_model、r_gap、r_foundation；只膨胀被 FIR-W 归因的那个半径，融合 r=√(r_geo²+r_force²+r_model²+r_gap²+r_foundation²) 进入 WCV-W。H_gap 时只膨胀 r_gap，不误降级正确几何；H_foundation 时只降基础模型权重。
- **定义 245（CSP-W 跨世界技能规划）**：每条块边需 Valid(J_bridge) 且 TCC 可迁移且 k*≥1；技能 σ 同时绑定仿真块签名分布 𝒟_σ^sim 与真实块签名分布 𝒟_σ^real，实际块签名对两者的 Mahalanobis 距离都需 ≤τ_chunk。可插入 `sim_probe`、`real_probe`、`null_test`、`visual_probe` 元技能。
- **定义 246（AIC-W 跨世界对抗认证）**：干扰集 ℰ_W=ℰ_F×ℰ_vis×ℰ_time×ℰ_sim×ℰ_common；ℰ_sim 含物理参数/渲染/执行器增益与延迟/具身错配；ℰ_common 表示孪生与真实共享同一建模偏差。ρ_dir 在 ℰ_W 上重算（n_cert 128→192，其中 64 给跨世界/共因）；**共因下不要求归因正确，只要求判 H_unknown 并拒绝迁移**。
- **定义 247（BRIDGE 证书 J_bridge）**：J_bridge=(J_vista, twin_posterior, transfer_radius, gap_bound, transfer_margin, real_probe_budget, unibot_iface_ver, H_unknown_flag)。Valid(J_bridge) ⇔ Valid(J_vista) ∧ (δ_gap≤r_τ) ∧ (H_unknown 未触发 ∨ 已安全降级) ∧ k*≥1 ∧ UAI 版本一致 ∧ 共因风险已显式标注。
- **定义 248（BRIDGE 闭环算子）**：语义流 [LiDAR→LSF→USR/MEL→VPG-W 反事实前瞻→ACH-U 生成 UniBot 块→阶段切分→VCV-W→UAI 配对→RGI 间隙签名→FIR-W 跨世界归因→VPA 虚拟探针拍卖→DTA 孪生适配→TCC 迁移证书→WCV-W→CSP-W 块规划→CSC-W 认证前缀→AIC-W]；实时流 [锚点读→真实残差采集→阶段判定→TCC 校验→CSC-W 早停→前缀派发→J_bridge 构建]。

## 2. 关键算法骨架

```python
# DTG + RGI：配对残差 → 孪生后验 → 间隙签名（语义流）
D_paired = uai.collect_paired_rollouts(policy, H=30)      # 同动作，双世界
theta_post = dtg.sbi_update(prior, D_paired)              # p(theta | D)
gamma = rgi.gap_signature(D_paired)                       # 物理/视觉/执行/延迟/具身
gap_bound = dtg.conformal_gap_bound(theta_post, alpha_gap)

# VPA：虚拟探针拍卖（语义流选，真实流只执行一次安全探针）
best, best_score = None, -inf
for a in A:
    rho_sim = dtg.rollout_ensemble(theta_post, a, H=30)
    ig = info_gain(hypotheses=H_PLUS, rho_sim=rho_sim, lam=lam_tau(gamma))
    risk = risk_upper(a, theta_post, f_safe)
    if risk <= B_probe and ig / (risk + lam_r) > best_score:
        best, best_score = a, ig / (risk + lam_r)
if best is None or best_score < delta_vpa:
    probe = None                                              # 纯被动观测
else:
    probe = shield.execute_length_one(best)                   # 长度 1 的认证技能
    gamma = rgi.refresh(gamma, probe.real_residual)

# FIR-W + TCC + CSC-W
post = fir_w.attribute(rho_real, gamma, p_sim)                # H in H_PLUS
h_star, ambiguous = argmax(post), post.max() < 1 - delta_fi
if h_star == "H_unknown" or ambiguous:
    return safe_idle_or_compliant_retreat()
if h_star == "H_gap":
    dtg.adapt(probe.real_residual); return re_certify_later()
m_sim = sim_margin(tau, theta_post.mean())
r_tau = max(0.0, (m_sim - eps) / L_m)
tcc = TransferCertificate(m_sim, gap_bound, r_tau, alpha_gap)
k_star = csc_w.certified_prefix(tau.A, post, m, alpha_chunk, tcc)
if not tcc.transferable:
    return fallback_real_only_vista()                        # 不迁移，回到第 65 轮
execute(tau.A[:k_star]); monitor_and_re_attempt()
```

## 3. 保证概要与推导要点（完整推导见产物区）

- **引理 9（孪生可信集覆盖）**：若配对样本可交换且间隙残差按 split-conformal 校准，则 P[θ_real∈Θ_δ]≥1−α_gap；SBI 后验经 simulation-based calibration 后给名义覆盖。于是 gap_bound 是证书相关距离的分布无关上界。
- **引理 10（迁移证书的可靠性）**：若 m(π,·) 关于 θ 在证书度量下 L_m-Lipschitz，且 d(θ_sim,θ_real)≤δ，则 m(π,θ_real)≥m(π,θ_sim)−L_m δ。故当 m_sim−L_m δ≥0 时仿真证书可迁移；否则必须拒绝。迁移证书只使用下界 m_lb，绝不用 m_sim 冒充真实裕度。
- **引理 11（虚拟探针的风险单调性）**：VPA 的候选集包含全部真实探针与零真实风险的虚拟探针，且真实探针的最终执行仍受 Shield 的力/形变约束。因此 VPA 的真实风险不超过同一风险预算下的真实-only BOED；当孪生无间隙（δ=0）时可把真实探针数降到 0，当间隙增大时 λ_τ→0 自动退回真实-only。**仿真只降低真实试错，不替代真实安全约束。**
- **定理 9（BRIDGE 端到端跨世界安全）**：在 A94–A99 下，Valid(J_bridge) ⇒ 几何/力/模型/间隙被归因（或显式 H_unknown 并安全降级）∧ 只在间隙上界小于迁移半径时下放证书 ∧ 块前缀安全 ∧ 未知/复合故障不被静默接受 ∧ GRIP/VISTA 有效。真实越界概率 ≤ α_chunk+δ_fi+α_vis+α_gap+α_unknown（联合界）。
- **定理 10（迁移感知的真实样本复杂度）**：设 |ℋ⁺|=M，单次真实探针的迁移感知互信息为 I_τ。要把归因错误率压到 ε，所需真实探针数 N_real≤(log M−H(ε))/I_τ；孪生无间隙时 I_τ 可由虚拟探针获得，N_real=0；间隙为 δ_info 时 I_τ≈(1−δ_info)I_sim，故 N_real 只按 1/(1−δ_info) 增长，而真实-only BOED 需 (log M)/I_real。**孪生的价值不是「替代真实」，而是「把真实探针从 O(log M) 压到 O(1)」。**
- **命题（降低过度保守）**：VISTA 对任何拒绝都膨胀单一 r；BRIDGE 在 H_gap 时只膨胀 r_gap，正确几何与已标定力传感器保持原精度；若真实故障是 gap 而几何可信，几何搜索域体积仅为总膨胀方案的 1/κ_infl^{d_φ}（几何分量），避免「因仿真不准而误降级真实几何」。

## 4. 实验概览（完整设计见产物区 E241–E250）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E241 RGI 间隙识别 | 物理/视觉/执行器/延迟/具身 gap 能否被分开 | 分类准确率 ≥85%，gap 估计误差 ≤15% |
| E242 TCC 迁移证书 | 证书下放是否可靠、是否过度保守 | 虚假迁移=0，可迁移率随 gap 单调下降 |
| E243 VPA 虚拟探针 | 虚拟试错能否省真实探针 | 真实探针 −60%，风险 −50%，准确率不降 |
| E244 UAI 跨具身对齐 | 54/60 维接口能否支撑配对 | 动作/状态对齐误差 ≤10%，跨具身迁移 +20% |
| E245 未知/复合故障 | 开集能否拒绝强行归类 | 未知召回 ≥90%，误归因 ≤10% |
| E246 共因间隙 | 孪生与真实同错时能否拒绝迁移 | 虚假迁移 ≤5%，安全降级=100% |
| E247 DTA 在线适配 | gap 漂移后能否快速恢复 | 3 个 episode 内重发证书，安全不破 |
| E248 端到端 vs VISTA | UniBot-V1 桌面/全身任务 | 成功率 +20%，损伤=0，误降级 −60% |
| E249 消融 | 去掉 DTG/RGI/VPA/TCC/UAI | 每项都有独立贡献，去 TCC 最危险 |
| E250 压力测试 | 对抗 patch+具身错配+30s 延迟 | 安全率 100%，证书正确作废，恢复 ≤2s |

## 5. 本轮最大风险

**一句话**：若孪生与真实共享同一建模偏差（同一接触模型、同一训练分布、同一视觉渲染假设），「虚实对照」会把共因误差当成一致证据，迁移证书会在最需要时给出虚假安全感；而独立第三通道（力/触觉/外部标定）一旦也失效，BRIDGE 就无法仅凭两个世界辨识共因——这是本轮全部迁移保证共同依赖的隐藏假设（A99）。
