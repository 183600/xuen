# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 65 轮（承接第 64 轮「GRIP 接触接地四层闭环」IP-204~213；灵感循环第 2 轮；本轮灵感：「视觉感知」×「动作分块」）

> 第 64 轮用 F/T 与触觉把几何先验变成可证伪假设，其自述的最大风险一针见血：**力/触觉存在未建模偏置、漂移、饱和，且接触模型本身错误（软接触、未建模动力学、接触点歧义）时，CGG 会把「传感器/模型错误」误判为「几何幻觉」——在正确几何上主动降级、在错误几何上放行，力觉从「接地真值」反变为新的单点故障与物理伤害源；APP 的主动探测还可能压坏易损物体。** 本轮不叠加第 5 个模态，而是换一个提问方式：第 64 轮问「先验对不对」，VISTA 问「**到底哪一层坏了、该膨胀哪个球、该不该继续执行**」。本轮核心命题是：
>
> **把「几何可证伪」升级为「故障可归因」：用视觉感知提供接触之前/之外的可错证据，用动作分块的时间阶段创造故障可辨识性，并用「长预测、短执行」把时序承诺的伤害压回单步水平。**

## 0. 直觉与动机

**灵感 1（视觉感知 → 接触之前 / 接触之外的第三条证据）**
直觉：第 64 轮把力觉当"接地真值"，但它有一个隐藏前提——必须先有接触，而且传感器本身可信。视觉恰好补两个空档：(i) **接触之前**——视觉能在还没碰上去时判断"那里是否真有一个面、接触斑会落在哪、法向对不对"，为几何先验提供前置证伪；(ii) **接触之外**——外部相机能看物体的**形变**，在小力下就反推刚度与接触力，是一种"非接触的力代理"，可在施力前估出 f_safe。但必须诚实：视觉是学习的，透明/镜面/对抗 patch/遮挡正是它的盲区，所以视觉**不是新的真值，而是第三条可错证据**。关键从"该信谁"转为"**用不同错误结构去分离故障**"。

**灵感 2（动作分块 → 时间分离创造可辨识性）**
直觉：第 64 轮 CGG 的根本缺陷是**不可辨识**：一个大的力残差，几何幻觉、F/T 偏置、接触模型错都能产生，单时刻无法区分，于是只能二选一。动作分块把一段运动切成宏动作，自然形成三种阶段：**自由空间接近（零力窗）→ 轻触（小载荷）→ 承载（大载荷/滑移）**。不同故障在这三阶段留下**不同的时间签名**：F/T 偏置在零力窗就露出 DC 偏置（而几何幻觉不会）；几何幻觉在接近段就与视觉足迹冲突、接触落点错（而模型错不会）；接触模型错在轻触时正常、加载后才偏。**分块不只是提速，它免费提供了故障隔离所需的受控激励。**

**灵感 3（动作分块 → 长预测、短执行）**
直觉：分块策略（ACT/扩散策略）一次预测 H 步、执行 k 步再重规划，用时间集成降方差、抗复合误差；但 k 太长就是"承诺过深"——故障在块内发生时，要等到块边界才纠正，可能越过不可逆点。于是把**预测视界 H 与执行前缀 k 解耦**：H 尽量长（只用于前瞻与一致性），k 不超过不可逆视界 m（只用于安全）。这正是"长预测、短执行"。

**灵感 4（三灵感合流 → VISTA：Visual-Informed Safe Temporal Attribution，视觉知情的安全时序归因闭环）**
闭环：视觉世界模型预测块级视觉后果（VPG）→ 视觉接触验证（VCV）为 CGG 加前置门 → 阶段化残差签名（三阶段）→ 故障归因（FIR）输出后验"谁坏了" → 归因模糊时做**主动判别探针 AFA**（探针目标从"估 φ 的 Fisher 信息"改为"降低故障假设熵的互信息"）→ 定向膨胀对应球（RSC-V）而非总膨胀几何球 → 块级认证前缀（CSC）只执行 k* 步 → 实时早停与重归因。第 64 轮是"几何-技能-干扰-接触"四层，VISTA 把"接触"这一层拆成"**接触前/接触中/接触后**"，并让每一层都对应一个可归因的故障源。

**灵感 5（GRIP 组件的原位升级）**
- **CGG → CGG-VCV**：增加视觉前置门；未观测到接触时不得以力残差否定几何，避免第 64 轮的头号误判。
- **APP → AFA**：探针选择从 D-最优参数信息升级为故障假设互信息；易损物体先走"视觉-only 探针"。
- **RSC → RSC-V**：把单一不确定球拆成 r_geo / r_force / r_model，只膨胀被归因的那个。
- **WCV → WCV-V**：搜索域增视觉可观测性约束 𝒱；归因模糊时对后验做边缘化尾部。
- **CSP → CSP-V**：在块而非单步上规划；技能与块签名绑定，偏离即判 OOD。
- **OLP / DIR / SSB**：投影输入增视觉预测残差与块不一致；在线学习只在语义流，实时流不写。
- **AIC → AIC-V**：干扰集增视觉对抗、块重放/时序错位，并显式建模**共因故障**（同一 OOD 物体同时骗几何与视觉）。
- **J_grip → J_vista**：证书增 fault_posterior、fault_entropy、k*、visual_grounding_hash、chunk_sig_hash。

## 1. 形式化定义（增量：定义 217–232）

- **定义 217（VISTA 闭环）**：VISTA = (GRIP, VPG, ACH, FIR, VCV, VSP/AFA, CSC, RSC-V/WCV-V, CSP-V, AIC-V, J_vista)。定位：GRIP 的"故障可归因 + 视觉前瞻"升级。不变式：**世界模型推断、故障归因、主动判别探针、证书只在语义流；实时流只做阶段化残差采集、安全前缀执行与早停，零学习写操作。**
- **定义 218（视觉任务观测量与视觉预测残差）**：视觉感知 f_vis（RGB/深度/光流）→ 任务观测量 y_t ∈ ℝ^{d_v}（物体 6D 位姿、末端位姿、接触斑中心与面积、低维形变嵌入）。视觉世界模型 g_vis 由 y_t 与动作块 A_t=(a_t,…,a_{t+H−1}) 预测 ŷ_{t+h}；残差 e_vis(t,h)=‖ŷ_{t+h}−y_{t+h}‖²_{Σ_vis⁻¹}。采用 split-conformal 给分布无关上界 q_vis(α)，不假设高斯（世界模型漂移、非高斯）。
- **定义 219（动作分块与块间一致性）**：π_θ(s_t) 输出 A_t∈ℝ^{H×d_a}，执行前 k≤H 步后以新观测重规划。块间不一致 d_chunk(t)=D(π_t(·|s_t),π_{t+k}(·|s_{t+k})) 取重叠视界平均 KL/离散度；M 个块策略集成给认知不确定度 u_chunk=Var_m[A_t^{(m)}]。二者只作"策略 OOD"证据，绝不当作真值。
- **定义 220（阶段化残差签名）**：按接触状态与力阈值把块切为 P={approach 零力窗, touch 轻触, load 承载}。每阶段证据向量 ρ_p=[ē_vis, ē_force, ē_torque, d̄_chunk, ū_chunk]ᵀ；整块签名 ρ=(ρ_approach,ρ_touch,ρ_load) ∈ ℝ^{15}。
- **定义 221（故障假设与归因 FIR）**：ℋ={H0 健康, H_geo 几何幻觉, H_force F/T 偏置/漂移, H_model 接触模型错, H_vis 视觉错, H_policy 策略 OOD}。离线故障注入 + 真实标定拟合 p(ρ|H)（高斯混合/归一化流）；后验 P(H|ρ)∝p(ρ|H)P(H)。若 max_H P(H|ρ)≥1−δ_fi 则定向处置，否则 ambiguous 并触发 AFA。
- **定义 222（阶段证据的可辨识性）**：线性化 E[ρ|θ]=Sθ、ρ∼N(Sθ,Σ_ρ)，θ 为各故障幅度。可辨识 ⇔ SᵀΣ_ρ⁻¹S≻0；可辨识裕度 κ_fi=λ_min(SᵀΣ_ρ⁻¹S)/λ_max(·)。三阶段使 S 近似块三角：H_force 列仅在 approach 出现（零力 DC），H_geo 列在 approach 与 touch 出现，H_model 列仅在 load 出现——列近正交。
- **定义 223（视觉接触验证 VCV）**：给定预测接触集 C 与法向 n_j，视觉在末端邻域检验接触斑是否存在、中心偏差 Δc、面积相对误差、法向夹角 Δθ，得证据 ℓ_contact=[Δc,|a−â|/â,cosΔθ]。若遮挡/透明/无纹理 → `visual_unobservable`，**不得据此否定 C**。VCV 是 CGG 的前置门：未观测到接触且力残差高时，优先归因 H_force 而非 H_geo。
- **定义 224（视觉力代理与刚度低力估计）**：对可视形变物体，外部相机跟踪表面标记/纹理位移 u(x,t)，低阶模型 f_n≈k·u+c·u̇，仅在小形变线性区估 k、c 与力代理 f̂_vis。用途：施力前估 f_safe；为 FPE 提供先验；交叉验证 F/T。透明/镜面/无纹理时 f̂_vis 不可用，退化回 F/T。
- **定义 225（视觉伺服安全探测 VSP + 主动判别归因 AFA）**：探针带阶段模板（视觉接近→轻触→加载），选择 a*=argmax_a I(ℋ;ρ_{1:3}(a)|ρ_{1:2})，s.t. 预测 f_n≤f_safe(φ̂,f̂_vis)、预测形变≤ε_strain、视觉可早停。即从第 64 轮"最大化 φ 的 Fisher 信息"升级为"最大化故障假设互信息"——探针首要目的从"估参数"变成"分清楚谁坏了"。边际信息<δ_fi 或 f_safe<f_min_probe 时放弃物理探针，改视觉-only 探针/被动观测。
- **定义 226（块级安全证书与认证前缀 CSC）**：对块 A_t 与执行前缀 k，在归因后验的支持集上逐一验证 ρ_safe≥0；用 conformal 选最小 k 使 P[前缀 k 步内某通道越界]≤α_chunk，输出 k*(A_t) 与最小安全裕度。执行器只执行 k* 步即强制重规划与再归因——"长预测、短执行"。
- **定义 227（RSC-V 归因定向球校准）**：维护 r_geo、r_force、r_model 与视觉信任权重 w_vis。只膨胀被归因者：H_geo→r_geo↑；H_force→r_force↑ 并触发零力窗重标定（**不降级几何**）；H_model→r_model↑ 并切柔顺；H_vis→w_vis↓；H_policy→H 缩短、k↓。融合半径 r=√(r_geo²+r_force²+r_model²) 进 WCV-V，避免第 64 轮"总膨胀同一个球"的过度保守。
- **定义 228（WCV-V 视觉-力-模型联合压缩）**：搜索域 B(φ̂,r)∩𝒢(g)∩K(μ̂)∩ℱ(f_lim)∩𝒱（𝒱 为视觉可观测性约束）。CVaR 尾部 n_worst=8；归因模糊时按后验加权做"归因边缘化尾部"；交集为空则回退 B(φ̂,r) 并置 `attribution_conflict=True`。
- **定义 229（CSP-V 块级技能规划）**：在块而非单步上规划；每条块边需 Valid(J_vista) 且 k*≥1；TSL 技能绑定典型块签名分布，实际块签名 Mahalanobis 距离>τ_chunk 即判 OOD、不入图；可插入 `null_test`（零力窗）、`visual_probe`、`fi_probe` 元技能。
- **定义 230（AIC-V 视觉/时序对抗认证）**：ℰ_V=ℰ_F×ℰ_vis×ℰ_time，ℰ_vis 含对抗 patch、光照/反光、透明、遮挡；ℰ_time 含块重放/时序错位/延迟；并含**共因故障**（同一 OOD 物体同时骗几何与视觉）。ρ_dir 在 ℰ_V 上重算（n_cert 96→128，其中 32 给视觉/时序），ρ_force 在最坏偏置与最坏视觉遮挡下取最坏；J_dir 增 visual_calib_ver、chunk_sync_ver。
- **定义 231（VISTA 证书 J_vista）**：J_vista=(J_grip, fault_posterior, fault_entropy, k*, visual_grounding_hash, chunk_sig_hash, visual_unobservable, aic_v_ver)。Valid ⇔ Valid(J_grip) ∧ (归因确定 ∨ 已执行 AFA 判别探针) ∧ k*≥1 ∧ 块签名与执行前缀一致 ∧ 视觉不可观测已显式标注且未用于否决接触。
- **定义 232（VISTA 闭环算子）**：语义流 [LiDAR→LSF→USR/MEL→VPG 视觉前瞻→ACH 生成块→阶段切分→VCV→FIR 归因→AFA/FPE→WCV-V→CSP-V/TSL 块规划→CSC 认证前缀→Shield→执行 k* 步→EV_exec→RSC-V→OLP→DIR→SSB→AIC-V]；实时流 [锚点读→视觉/力残差采集→阶段判定→CSC 早停→WCV-V 编译→π_σ 前缀派发→J_vista 构建]。

## 2. 关键算法骨架

```python
# FIR：阶段化签名 → 故障后验 → 定向处置（语义流）
rho = signature(phases)                       # [approach, touch, load] × 5 维
post = softmax({h: log lik[h](rho) + log prior[h] for h in HYP})
h_star, ambiguous = argmax(post), post[argmax(post)] < 1 - delta_fi
if not ambiguous:
    balls, w_vis, H = directed_demote(h_star, balls, w_vis, H)   # 只膨胀被归因的球
else:
    a = afa.choose_probe(post, phi_hat, f_safe)  # 最大化故障假设互信息

# CSC：长预测、短执行
A = policy.propose_chunk(obs, H)               # H 长视界
k_star = csc.certified_prefix(A, post, m, alpha_chunk)
for a in A[:k_star]:
    dispatch(a)
    if csc.monitor_step(a, post).abort: break  # 实时早停 → 重归因

# VCV + 视觉力代理：接触前的低伤害证据
info = vcv.verify(contact_pred, img, depth, flow)
if info['observed'] and info['dc'] > tau_c:
    rho_approach[0] += info['dc'] / sigma_c      # 几何幻觉证据
f_vis, k_hat = visual_force_proxy.estimate(markers, dt)
f_safe = safe_force(k_hat) if f_vis is not None else f_safe_default
```

## 3. 保证概要与推导要点（完整推导见产物区）

- **引理 7（三阶段可辨识性）**：若零力窗、轻触、加载三阶段都被激励，且视觉与力的共因项被显式建模，则签名矩阵 S 的列近正交、SᵀΣ_ρ⁻¹S≻0，故障幅度 θ 可辨识；Laplace 近似下归因后验错误率 ≤ exp(−n·κ_fi/2)。因此"几何幻觉 / 力偏置 / 模型错"第一次可被**分离**，而不是挤在一个 ‖e‖ 里。
- **引理 8（认证前缀的执行安全）**：若 k*≤m（不可逆视界）且对后验支持集内每个假设都验证了 k* 步安全，则单块内越界概率 ≤ α_chunk + δ_fi + α_vis（conformal 覆盖）。故块承诺不引入超出单步安全的新风险。
- **定理 7（VISTA 端到端归因-安全）**：在 A88–A92 下，故障被归因（或显式 ambiguous 并触发 AFA）且只膨胀正确的球；Valid(J_vista) ⇒ 几何"接受/降级/力偏置重标定" ∧ φ 球含真值 ∧ 滑移/力限安全 ∧ 块前缀安全 ∧ GRIP 有效。证书链从"几何-技能-干扰-接触"扩到"几何-技能-干扰-接触-归因"。
- **定理 8（长预测、短执行的近最优性）**：设块长 H 使动作估计方差 ∼σ_π²/H，故障不可逆视界为 m，单步检出率 q。则风险 R(H,k)=c₁σ_π²/H + c₂·1[k>m]；对 k≤m，R 关于 k 不变、关于 H 单调不增。故最优策略是 H 尽量长、k*=min(H,m)——**把"长视界"只用于前瞻与一致性，把"短前缀"用于安全承诺**。
- **实时性**：VPG/世界模型、FIR、AFA、CSP-V 全在语义流；实时流只增 ROI 光流残差（<0.2ms）、阶段判定（<0.05ms）、CSC 早停（<0.02ms），并把 OLP-F 重路径移出实时环，目标 ≤2.5ms（A93 修订契约，需视觉 ROI 与 LSF 共享编码）。

## 4. 实验概览（完整设计见产物区 E231–E240）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E231 VCV 接触验证 | 视觉能否为 CGG 挡住误降级 | 误降级降 ≥60%，透明/遮挡仍安全 |
| E232 FIR 故障归因 | 5 类故障能否被分离 | 归因准确率 ≥90%，未知故障召回 ≥85% |
| E233 阶段可辨识性 | 三阶段是否让 S 满秩 | 条件数降 ≥5×，去阶段即退化 |
| E234 AFA 判别探针 | 主动性是否更省更安全 | 判别接触次数 −50%，累计力 −60% |
| E235 视觉力代理 | 非接触估 k / f_safe | k 误差 ≤25%，易损损伤 =0 |
| E236 CSC 认证前缀 | 早停能否压住块承诺风险 | 违规=0，成功率不降，k* 自适应 |
| E237 长预测短执行消融 | H/k 解耦是否有效 | H↑ 方差↓，k>m 违规↑ |
| E238 端到端 vs 第 64 轮 | 幻觉+偏置+易损+透明 | 成功率 +25%，误降级 −60%，损伤=0 |
| E239 共因故障 | 几何与视觉同时被骗 | 正确判 ambiguous，不强行归因 |
| E240 压力测试 | 未知故障/时序错位/延迟 | 安全降级，entropy 有界，恢复 ≤2s |

## 5. 本轮最大风险

**一句话**：VISTA 的归因能力依赖"故障属于有限假设集、且视觉与几何的失效相互独立"这两个假设；真实故障常是未知类型的组合，且透明/镜面/对抗 patch 会让视觉与几何**共享同一个分布外失效源**，此时 FIR 会把未知的复合故障强行归入最近假设、只膨胀错误的球——**第 64 轮的单点故障由此升级为"归因错误的复合故障"，而且系统会因为"已经归因"而更自信地继续执行**，这是本轮全部可辨识性与认证前缀论证共同依赖的隐藏假设（A88）。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
--- 产物区 ---
# 第 65 轮产物 · 创新点清单 v3：VISTA（Visual-Informed Safe Temporal Attribution：视觉前瞻 × 动作分块的故障可归因安全时序抽象；VPG×ACH×FIR×VCV×VSP/AFA×CSC×RSC-V×WCV-V×CSP-V×AIC-V×J_vista）

> 承接第 64 轮 IP-204~213（GRIP：CGG×MWS×FPE×APP×TSL×SLD×FCS×RSC-F×OLP-F×WCV-F×CSP-F×AIC-F×J_grip）。第 64 轮把几何先验变成"可证伪"，但其最大风险是**不可辨识**：力/触觉偏置、漂移、饱和与错误接触模型会让 CGG 把"传感器/模型错误"误判为"几何幻觉"，从而在正确几何上主动降级、在错误几何上放行；主动探测还可能压坏易损物体。本轮不做推倒，而是把"可证伪"升级为"**可归因**"：用**视觉感知**补上接触之前/之外的可错证据，用**动作分块**的时间阶段创造故障可辨识性，用**主动判别探针**把"估参数"改成"分清楚谁坏了"，用**长预测、短执行**把时序承诺的伤害压回单步水平。实现 **「故障可分离、球只膨胀对的、执行只到不可逆点」**。
>
> IP 编号：IP-214~IP-223（共 10 个），全部为第 64 轮组件的原位升级或挂载式新增。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 64 轮） |
|---|---|---|---|
| IP-214 | VPG Visual Predictive Grounding | 新增 | 视觉世界模型预测块级视觉后果，给分布无关 conformal 残差；外部相机看形变作非接触力代理 |
| IP-215 | ACH Action-Chunk Hypothesis | 升级策略层 | H 步块 + 时间集成 + 块间不一致/集成方差，作为"策略 OOD"证据 |
| IP-216 | FIR Fault Isolation & Re-attribution | 新增 | 阶段化残差签名（零力窗/轻触/加载）+ 6 假设贝叶斯归因，**分离**几何/力/模型/视觉/策略故障 |
| IP-217 | VCV Visual Contact Verification | 新增 | 接触斑存在性/落点/法向的视觉前置门；`visual_unobservable` 不得否决接触 |
| IP-218 | VSP/AFA Visual-Servoed Probing & Active Fault Attribution | 升级 APP | 探针目标从 φ 的 Fisher 信息改为故障假设互信息；先视觉-only 探针，形变早停 |
| IP-219 | CSC Chunk-level Safety Certificate | 新增 | 块级 conformal 认证前缀 k*；执行 k* 步即强制重规划——长预测、短执行 |
| IP-220 | RSC-V / WCV-V | 升级 RSC-F/WCV-F | 不确定球拆为 r_geo/r_force/r_model，只膨胀被归因者；搜索域增视觉可观测性 𝒱 |
| IP-221 | CSP-V / TSL-chunk | 升级 CSP-F/TSL | 在块上规划；技能绑定块签名分布，偏离即 OOD；插入 null_test/visual_probe/fi_probe |
| IP-222 | AIC-V | 升级 AIC-F | 干扰集增视觉对抗、块重放/时序错位，并显式建模共因故障 |
| IP-223 | VISTA Operator + J_vista | 整合 | 语义/实时流新增阶段化归因与认证前缀；证书增加 fault_posterior、fault_entropy、k* |

## 1. 符号体系增量（定义 217–232）

| 符号 | 含义 |
|---|---|
| `VISTA = (GRIP, VPG, ACH, FIR, VCV, VSP/AFA, CSC, RSC-V, WCV-V, CSP-V, AIC-V, J_vista)` | 视觉知情的安全时序归因闭环 |
| `y_t ∈ ℝ^{d_v}` | 视觉任务观测量（位姿/接触斑/形变嵌入） |
| `g_vis(y_t, A_t)`，`ŷ_{t+h}` | 视觉世界模型与块级预测 |
| `e_vis(t,h) = ‖ŷ_{t+h}−y_{t+h}‖²_{Σ_vis⁻¹}` | 视觉预测残差 |
| `q_vis(α)` | split-conformal 视觉残差上界（分布无关） |
| `A_t = (a_t,…,a_{t+H−1}) ∈ ℝ^{H×d_a}` | 动作块；H 为预测视界 |
| `k`，`k*` | 执行前缀长度与认证前缀长度；`k* ≤ m` |
| `m` | 不可逆视界（由力/几何裕度与停止距离决定） |
| `d_chunk(t)`，`u_chunk(t)` | 块间不一致 / 集成方差 |
| `P = {approach, touch, load}` | 块内三阶段（零力窗/轻触/承载） |
| `ρ_p = [ē_vis, ē_force, ē_torque, d̄_chunk, ū_chunk]ᵀ`，`ρ ∈ ℝ^{15}` | 阶段证据与整块签名 |
| `ℋ = {H0, H_geo, H_force, H_model, H_vis, H_policy}` | 故障假设集 |
| `P(H|ρ) ∝ p(ρ|H)P(H)` | 故障后验 |
| `δ_fi` | 归因确定阈值；`max_H P(H|ρ) ≥ 1−δ_fi` 才定向处置 |
| `S`，`κ_fi = λ_min(SᵀΣ_ρ⁻¹S)/λ_max(·)` | 签名矩阵与可辨识裕度 |
| `ℓ_contact = [Δc, |a−â|/â, cosΔθ]` | 视觉接触验证证据 |
| `f̂_vis = k̂·u + ĉ·u̇` | 视觉力代理（小形变线性区） |
| `a* = argmax_a I(ℋ; ρ_{1:3}(a) | ρ_{1:2})` | 故障判别探针（AFA） |
| `k*(A_t)`，`α_chunk` | 认证前缀与块级越界预算 |
| `r_geo, r_force, r_model`，`r = √(r_geo²+r_force²+r_model²)` | 归因定向球与融合半径 |
| `w_vis` | 视觉信任权重（H_vis 时下调） |
| `𝒱` | 视觉可观测性约束 |
| `ℰ_V = ℰ_F × ℰ_vis × ℰ_time` | 视觉/时序/共因故障干扰集 |
| `J_vista = (J_grip, fault_posterior, fault_entropy, k*, visual_grounding_hash, chunk_sig_hash, visual_unobservable, aic_v_ver)` | 五层安全证书 |

## 2. 形式化定义（完整版）

**定义 217（VISTA 闭环）** VISTA 是 GRIP 的"故障可归因 + 视觉前瞻"升级：在 GRIP 的第 64 轮"语义流 ∘ 实时流"骨架上挂载 VPG（视觉预测）、ACH（动作分块）、FIR（故障归因）、VCV（视觉接触验证）、VSP/AFA（视觉伺服探测与主动判别）、CSC（块级认证前缀），并原位升级 RSC-F→RSC-V、WCV-F→WCV-V、CSP-F→CSP-V、AIC-F→AIC-V、J_grip→J_vista。不变式：**所有世界模型推断、故障归因、主动判别探针、证书构建只发生在语义流与低频线程；实时路径只做阶段化残差采集、安全前缀执行、早停与派发，零学习写操作。**

**定义 218（视觉任务观测量与视觉预测残差）** 视觉感知 f_vis 把 RGB/深度/光流映射为任务观测量 y_t ∈ ℝ^{d_v}（物体 6D 位姿、末端位姿、接触斑中心 c 与面积 a、低维形变嵌入）。视觉世界模型 g_vis 由 y_t 与动作块 A_t 预测 ŷ_{t+h}=g_vis(y_t,A_t^{1:h})。视觉预测残差
e_vis(t,h)=‖ŷ_{t+h}−y_{t+h}‖²_{Σ_vis⁻¹}。
由于世界模型存在分布漂移且噪声非高斯，采用 split-conformal：在标定集上取非一致性分数 s_i=e_vis^{(i)}，令 q_vis(α) 为其 ⌈(n+1)(1−α)⌉/n 分位数，则对任意新样本 P[e_vis ≤ q_vis(α)] ≥ 1−α（可交换性下）。**视觉残差只产生"与预测不符"的证据，不产生"物理真值"。**

**定义 219（动作分块与块间一致性）** 块策略 π_θ(s_t) 输出 A_t∈ℝ^{H×d_a}，执行前 k≤H 步后以新观测重规划（receding horizon）。定义块间不一致
d_chunk(t)=D(π_t(·|s_t), π_{t+k}(·|s_{t+k}))，
D 为重叠视界上的平均对称 KL 或动作离散度；M 个独立块策略的集成给出 u_chunk(t)=Var_m[A_t^{(m)}]。二者刻画**策略认知不确定度**，是 H_policy 的主要证据；它们不进入物理真值，只影响 H 与 k 的选择。

**定义 220（阶段化残差签名）** 按接触状态与法向力阈值自动切分块内阶段 P={approach（无接触，f_n≈0）, touch（0<f_n≤f_light）, load（f_n>f_light）}。每阶段聚合证据
ρ_p=[ē_vis, ē_force, ē_torque, d̄_chunk, ū_chunk]ᵀ ∈ ℝ⁵，其中 ē_force=‖Σ_w^{-1/2}e_t‖ 为第 64 轮力残差均值。整块签名 ρ=(ρ_approach,ρ_touch,ρ_load)∈ℝ^{15}。阶段切分只依赖可实时获得的接触状态与力阈值，不依赖学习模型。

**定义 221（故障假设与归因 FIR）** 故障假设集 ℋ={H0 健康, H_geo 几何幻觉, H_force F/T 偏置/漂移/饱和, H_model 接触模型错（软接触/未建模动力学/接触点歧义）, H_vis 视觉感知错（对抗/光照/透明/遮挡）, H_policy 块策略 OOD}。用离线故障注入（仿真 + 真机标定台）拟合各假设下的签名似然 p(ρ|H)（高斯混合或小归一化流）。后验
P(H|ρ)=p(ρ|H)P(H) / Σ_{H'}p(ρ|H')P(H')。
定向处置规则：
- **H_geo**：r_geo←min(r_max,κ_infl·r_geo)，并要求 VCV 观测到接触斑落点/法向确实不符（否则降级归因可信度）。
- **H_force**：r_force←min(r_max,κ_infl·r_force)，触发**零力窗重标定**（自由空间读数为偏置 b̂），**不降级几何**，更新 Σ_w 与 fcs 力限的有效值。
- **H_model**：r_model←min(r_max,κ_infl·r_model)，切柔顺控制、增大接触模型不确定集。
- **H_vis**：w_vis←max(0,κ_vis·w_vis)，VCV 结论降权，退回 F/T 主导。
- **H_policy**：H←max(H_min,H/2)，k↓，强制重规划。
- **ambiguous**（max_H P(H|ρ)<1−δ_fi）：不处置，进入 AFA（定义 225）。

**定义 222（阶段证据的可辨识性）** 设故障幅度 θ∈ℝ^{d_H}，线性化 E[ρ|θ]=Sθ、ρ∼N(Sθ,Σ_ρ)。Fisher 信息 J_fi=SᵀΣ_ρ⁻¹S；θ 可辨识 ⇔ J_fi≻0，可辨识裕度 κ_fi=λ_min(J_fi)/λ_max(J_fi)。三阶段使 S 近似块三角：
- H_force 列仅在 approach 非零（零力窗的 DC 偏置，且**不伴随视觉形变**）；
- H_geo 列在 approach（视觉足迹/落点冲突）与 touch（接触落点偏差）非零；
- H_model 列仅在 load 非零（轻触正常、加载后偏离）。
因此列近正交、κ_fi 由阶段对比度控制。若缺少零力窗（approach 缺失）或缺少轻触阶段，对应列坍缩，归因退化为第 64 轮的不可辨识二分。

**定义 223（视觉接触验证 VCV）** 给定几何先验预测的接触集 C 与法向 n_j，视觉在末端邻域检验：接触斑是否存在、中心偏差 Δc、面积相对误差 |a−â|/â、法向夹角 Δθ，得 ℓ_contact=[Δc,|a−â|/â,cosΔθ]。若遮挡/透明/镜面/无纹理导致检测失败，输出 `visual_unobservable`，**不得据此否定 C**（避免把"看不见"误判为"不存在"）。VCV 作为 CGG 的**前置门**：当未观测到接触而力残差高时，优先归因 H_force（力传感器偏置），而非 H_geo；只有"视觉确实看到接触斑落点/法向不符"才允许 H_geo 定向膨胀几何球。

**定义 224（视觉力代理与刚度低力估计）** 对可视形变物体，外部相机跟踪表面标记/纹理位移 u(x,t)，用低阶 Kelvin-Voigt 模型 f_n≈k·u+c·u̇，仅在小形变线性区辨识 k、c 与力代理 f̂_vis。用途：(i) 在施加危险力之前估 f_safe(≈f_lim(a)/安全系数)；(ii) 为 FPE 提供低成本刚度先验；(iii) 与 F/T 交叉验证，f̂_vis 与 W 的一致性作为 H_force/H_vis 的附加证据。透明/镜面/无纹理时 f̂_vis 不可用，退化为纯 F/T。

**定义 225（视觉伺服安全探测 VSP + 主动判别归因 AFA）** 探针动作带阶段模板 a=(visual_approach, light_touch, load)，探针集 A={press,rub,tap,lift,visual_probe,null_test}。选择
a*=argmax_{a∈A} I(ℋ; ρ_{1:3}(a) | ρ_{1:2})，
s.t. 预测 f_n≤f_safe(φ̂,f̂_vis)、预测形变≤ε_strain、支持视觉早停。
即把第 64 轮 APP 的"最大化 φ 的 Fisher 信息（D-最优）"升级为"**最大化故障假设的互信息**"——探针首要目的从"估参数"变成"分清楚谁坏了"。若边际信息增益<δ_fi、或物体被判易损（f_safe<f_min_probe），放弃物理探针，改走 visual_probe（motion parallax/主动视觉）或 null_test（零力窗标定），从而把物理伤害预算压到最低。

**定义 226（块级安全证书与认证前缀 CSC）** 对块 A_t 与执行前缀 k，在归因后验的支持集 supp_δ(post)={H:P(H|ρ)≥δ} 上逐一验证：∀H∈supp_δ、∀s≤k，ρ_safe(s)≥0（沿用第 64 轮 ρ_rob/ρ_slip/ρ_force，并在 H_force 下用偏置上界）。用 conformal 选最小 k 使
P[∃s≤k: 某通道越界] ≤ α_chunk，
输出 k*(A_t) 与最小安全裕度。执行器只执行 k* 步，然后强制重规划与再归因。约束 k*≤m（不可逆视界）：m 由 f_lim 与停止距离反解，保证即使故障在块首发生，也能在越过不可逆点前停下。

**定义 227（RSC-V 归因定向球校准）** 维护三个独立不确定半径：r_geo（几何先验）、r_force（F/T 标定/偏置）、r_model（接触模型），以及视觉信任权重 w_vis。RSC-V 只膨胀**被归因**的那个半径（定义 221），并按下式融合进 WCV-V：
r=√(r_geo²+r_force²+r_model²)。
相比第 64 轮"任何拒绝都膨胀同一个 r"，RSC-V 在 H_force 时保持 r_geo 不变（正确几何不被误降级），在 H_geo 时保持 r_force 不变（不因几何错而怀疑已标定的力传感器）。这直接对冲第 64 轮的"在正确几何上主动降级"。

**定义 228（WCV-V 视觉-力-模型联合压缩）** 搜索域
B(φ̂,r) ∩ 𝒢(g) ∩ K(μ̂) ∩ ℱ(f_lim) ∩ 𝒱，
其中 𝒱 为视觉可观测性约束：若 e_vis≤q_vis(α) 或标记 visual_unobservable 则通过；若视觉与力/几何一致但超出 conformal 界，收紧 𝒱 或降低 w_vis。CVaR 尾部采样 n_worst=8；归因模糊时按后验加权做"归因边缘化尾部"（对每个 H 采样并按 P(H|ρ) 加权）。交集为空则回退 B(φ̂,r)，置 `attribution_conflict=True` 写入 J_vista。

**定义 229（CSP-V 块级技能规划）** 在 CSP 的层级 A* 上以**块**为边：每条块边需 Valid(J_vista) 且 k*≥1。TSL 技能 σ 绑定一个典型块签名分布 𝒟_σ（离线统计）；实际块签名 ρ 到 𝒟_σ 的 Mahalanobis 距离>τ_chunk 即判 OOD，该技能不入图。规划器可插入元技能：`null_test`（自由空间零力标定，识别 H_force）、`visual_probe`（主动视觉，识别 H_geo/H_vis）、`fi_probe`（AFA 判别探针）。软约束代价增 λ_fi·H(P(H|ρ))（归因熵）与 λ_k·Σ hinge(k*−k_req)。

**定义 230（AIC-V 视觉/时序对抗认证）** 干扰集
ℰ_V=ℰ_F×ℰ_vis×ℰ_time，
ℰ_vis 含视觉对抗 patch、光照/反光、透明、遮挡；ℰ_time 含块重放、时序错位、通信延迟；并新增共因故障 ℰ_common（同一 OOD 物体同时骗过几何与视觉）。ρ_dir 在 ℰ_V 上重算（n_cert 96→128，其中 32 用于视觉/时序/共因），ρ_force 在最坏偏置与最坏视觉遮挡下取最坏；J_dir 增 visual_calib_ver、chunk_sync_ver。**共因故障下不要求归因正确，只要求能被判为 ambiguous 并安全降级。**

**定义 231（VISTA 证书 J_vista）** J_vista=(J_grip, fault_posterior, fault_entropy, k*, visual_grounding_hash, chunk_sig_hash, visual_unobservable, aic_v_ver)。验证规则：
Valid(J_vista) ⇔ Valid(J_grip)
∧ (max_H P(H|ρ)≥1−δ_fi ∨ 已执行 AFA 判别探针)
∧ k*≥1 ∧ 块签名与执行前缀一致
∧ (visual_unobservable ⇒ 未以视觉否定接触)
∧ aic_v_ver 为当前版本。
审计链新增：为何膨胀这个球（fault_posterior）、为何只执行 k* 步（CSC）、视觉是否可用（visual_unobservable）。

**定义 232（VISTA 闭环算子）** 见 IP-223 伪代码。语义流：[LiDAR→LSF→USR/MEL→VPG 视觉前瞻→ACH 生成块→阶段切分→VCV→FIR 归因→AFA/FPE→WCV-V→CSP-V/TSL 块规划→CSC 认证前缀→Shield-Skill→OCB-Skill→执行 k* 步→EV_exec→RSC-V→OLP→DIR→SSB→AIC-V]；实时流：[锚点读→视觉/力残差采集→阶段判定→CSC 早停→WCV-V 编译→π_σ 前缀派发→J_vista 构建]。

## 3. 关键算法伪代码

### IP-216 FIR（故障归因）

```python
class FaultIsolation:
    """阶段化签名 → 6 假设后验 → 定向处置。实时只采集 ρ，归因在语义流。"""
    HYP = ('H0', 'H_geo', 'H_force', 'H_model', 'H_vis', 'H_policy')

    def __init__(self, lik, prior=None, delta_fi=0.15, kappa_infl=2.0, kappa_vis=0.5):
        self.lik = lik                         # p(rho|H)，离线故障注入标定
        self.prior = prior or {h: 1.0 / len(self.HYP) for h in self.HYP}
        self.delta_fi, self.kappa_infl, self.kappa_vis = delta_fi, kappa_infl, kappa_vis

    def signature(self, phases):
        return np.concatenate([np.asarray(phases[p]) for p in ('approach', 'touch', 'load')])

    def attribute(self, phases):
        rho = self.signature(phases)
        logp = {h: np.log(self.lik[h](rho) + 1e-12) + np.log(self.prior[h])
                for h in self.HYP}
        z = np.array(list(logp.values()))
        z -= z.max()
        post = {h: float(np.exp(v) / np.exp(z).sum()) for h, v in logp.items()}
        h_star = max(post, key=post.get)
        return post, h_star, post[h_star] < 1.0 - self.delta_fi

    def directed_demote(self, h_star, balls, w_vis, H):
        if h_star == 'H_geo':
            balls['r_geo'] = min(R_MAX, self.kappa_infl * balls['r_geo'])
        elif h_star == 'H_force':
            balls['r_force'] = min(R_MAX, self.kappa_infl * balls['r_force'])
            request_null_window_recalibration()       # 零力窗重标定，不动几何
        elif h_star == 'H_model':
            balls['r_model'] = min(R_MAX, self.kappa_infl * balls['r_model'])
            switch_compliant_control()
        elif h_star == 'H_vis':
            w_vis = max(0.0, self.kappa_vis * w_vis)
        elif h_star == 'H_policy':
            H = max(H_MIN, H // 2)
        return balls, w_vis, H

    def entropy(self, post):
        return -sum(p * np.log(p + 1e-12) for p in post.values())
```

### IP-217 VCV + IP-214 视觉力代理

```python
class VisualContactVerifier:
    def verify(self, contact_pred, img, depth, flow):
        patch = detect_contact_patch(img, depth, flow, contact_pred.center)
        if patch is None:
            return {'observed': False,
                    'reason': 'occluded/transparent/untextured',
                    'gate': 'visual_unobservable'}
        return {'observed': True,
                'dc': float(np.linalg.norm(patch.center - contact_pred.center)),
                'darea': abs(patch.area - contact_pred.area) / max(contact_pred.area, 1e-6),
                'dtheta': float(np.arccos(np.clip(patch.normal @ contact_pred.normal, -1, 1)))}

    def gate_geo_demotion(self, info, force_residual_T):
        if not info['observed']:
            return 'prefer_H_force'                  # 看不见 ≠ 不存在
        mismatch = (info['dc'] > TAU_C or info['darea'] > TAU_A
                    or info['dtheta'] > TAU_THETA)
        if mismatch and force_residual_T > CHI2_6:
            return 'allow_H_geo'
        return 'inconclusive'


class VisualForceProxy:
    """外部相机看形变，作非接触力代理；只在小形变线性区有效。"""
    def estimate(self, marker_flow, dt, valid):
        if not valid:
            return None, np.inf, None
        u, du = marker_flow.u, marker_flow.du_dt
        k_hat, c_hat = fit_kelvin_voigt(u, du)
        f_vis = k_hat * u.mean() + c_hat * du.mean()
        return float(f_vis), float(k_hat), (k_hat, c_hat)
```

### IP-218 VSP/AFA（故障判别探针）

```python
class ActiveFaultAttribution:
    PROBES = ('visual_probe', 'null_test', 'press', 'rub', 'tap', 'lift')

    def choose_probe(self, post, phi_hat, f_safe, object_fragile):
        if object_fragile:
            # 易损：只用零接触探针
            return ('visual_probe' if self._vis_reduces_entropy(post) > DELTA_FI
                    else 'null_test'), self._entropy_after(post, 'null_test')
        best, best_ig = None, -np.inf
        for a in self.PROBES:
            traj = predict_probe_traj(a, phi_hat)
            if np.max(traj.f) > f_safe or np.max(traj.strain) > EPS_STRAIN:
                continue
            ig = expected_mutual_info(post, a, self.lik)   # I(H; rho_new)
            if ig > best_ig:
                best, best_ig = a, ig
        if best_ig < DELTA_FI:
            return None, best_ig
        return best, best_ig
```

### IP-219 CSC（块级认证前缀）

```python
class ChunkSafetyCertificate:
    def certified_prefix(self, A, post, m, alpha_chunk, delta=0.05):
        support = {h: p for h, p in post.items() if p >= delta}
        # 只在前 2 个最可能假设上做最坏，控制组合爆炸
        top = sorted(support, key=support.get, reverse=True)[:2]
        k_best = 0
        for k in range(1, min(len(A), m) + 1):
            ok = True
            for h in top:
                for s in range(k):
                    if safety_margin(A[s], h) < 0:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
            if self._violation_prob(A[:k], top) <= alpha_chunk:
                k_best = k
            else:
                break
        return k_best

    def monitor_step(self, a, post):
        # 实时：阶段化残差是否越界
        rho_now = acquire_phase_evidence()
        return AbortFlag(abort=any_cusum_exceeded(rho_now, post))
```

### IP-220 WCV-V（归因定向鲁棒编译）

```python
def wcv_v_compile(olp, x_prime, phi_hat, balls, post, G_set,
                  mu_hat, delta_mu, f_lim, w_vis, n_worst=8, eps=0.05):
    r = np.sqrt(balls['r_geo']**2 + balls['r_force']**2 + balls['r_model']**2)
    candidates = []
    for _ in range(n_worst):
        H = sample_from(post)                      # 归因边缘化
        phi_c = sample_ball_intersect(phi_hat, r, G_set, mu_hat, delta_mu, f_lim, H)
        if phi_c is None:
            return None, -np.inf, True
        K = olp.project(x_prime)
        K_c = eeis.compile_with_phys_constraint(K, phi_c)
        m = safety_margin(K_c, phi_c) * (1.0 if w_vis > 0 else 1.0)
        candidates.append((phi_c, K_c, m, execution_loss_estimate(K_c, phi_c)))
    candidates.sort(key=lambda z: z[3], reverse=True)
    tail = candidates[:max(1, int(eps * n_worst))]
    K_safe = intersect_shrink([c[1] for c in tail])
    rho_rob = min(c[2] for c in tail)
    return K_safe, rho_rob, False
```

### IP-223 VISTA 闭环算子（整合）

```python
def VISTA_round(M, obs, delta_f_req):
    V, T, P, L, P_cloud, W_meas, tactile, img, depth, flow = obs
    # ———— 语义流（10–100Hz）————
    M.lsf.update_geometry(P_cloud)
    x_prime = M.lsf.fuse(M.usr.fuse(V, T, P, L))
    y_vis = M.f_vis(img, depth, flow)
    phi_hat_geo, *_ = M.mel.infer_by_mode(M.ocb_skill.choose().mel_mode,
                                          V, T, P, L, x_prime)

    # 1) ACH：生成块（长视界 H）
    A = M.ach.propose(x_prime, H=M.H)
    # 2) VPG + VCV：接触前视觉证据
    visual = M.vpg.verify_and_predict(y_vis, A, M.mws.last_contacts)
    f_vis, k_hat, _ = M.vfp.estimate(visual['flow'], M.dt, visual['valid'])
    # 3) 阶段化证据 + FIR 归因
    phases = M.stage.split(M.residual_log, visual)
    post, h_star, ambiguous = M.fir.attribute(phases)
    if ambiguous:
        a, ig = M.afa.choose_probe(post, phi_hat_geo, M.f_safe, M.object_fragile)
        if a is not None:
            M.execute_probe(a); phases = M.stage.split(M.residual_log, visual)
            post, h_star, ambiguous = M.fir.attribute(phases)
    # 4) 定向处置：只膨胀被归因的球
    if not ambiguous:
        M.balls, M.w_vis, M.H = M.fir.directed_demote(
            h_star, M.balls, M.w_vis, M.H)
    # 5) 规划（块级）+ 认证前缀
    goal = M.dms.parse_goal((M.usr.U_ep, M.usr.U_al))
    tau = M.csp_v.plan_chunks(goal, x_prime, phi_hat_geo, M.balls, post)
    k_star = M.csc.certified_prefix(tau.A, post, M.m, M.alpha_chunk)
    shield = skill_precondition_shield(tau.theta[0], tau.skills[0], phi_hat_geo,
                                       M.balls['r_geo'])
    # 6) 实时执行 + 力觉/视觉早停
    K_safe, EV_exec, cert_exec = realtime_step_vista(
        M, delta_f_req, tau, k_star, x_prime, f_vis)
    # 7) 在线更新（纯语义流）
    evidence = M.olp.fuse_evidence(x_prime, W_meas, tactile, visual, post)
    M.olp.online_step(evidence, execution_loss_grad(K_safe, EV_exec, M.balls))
    M.rsc_v.update(EV_exec, W_meas, phi_hat_geo, post, M.balls)
    M.dir.update(sample_batch_from_history(32))
    rho_dir = M.aic_v.certify(tau, x_prime, phi_hat_geo, M.balls, M.post)
    return M, K_safe, EV_exec, build_j_vista(
        cert_exec, J_grip=M.j_grip, fault_posterior=post,
        fault_entropy=M.fir.entropy(post), k_star=k_star,
        visual_grounding_hash=hash(visual), chunk_sig_hash=hash(phases),
        visual_unobservable=(not visual['observed']), aic_v_ver=AIC_V_VERSION)
```

## 4. 推导

**引理 7（三阶段可辨识性）** 设故障幅度 θ，线性化 E[ρ|θ]=Sθ、ρ∼N(Sθ,Σ_ρ)。则 Fisher 信息 J_fi=SᵀΣ_ρ⁻¹S，后验协方差（Laplace）≈J_fi⁻¹；θ 可辨识当且仅当 J_fi≻0。三阶段结构使 S 分块：
- approach 段：H_force 只引入零力 DC 偏置（无视觉形变），H_geo 引入视觉足迹/落点冲突，故二者在 approach 的列彼此不同、近正交；
- touch 段：H_geo 的落点偏差持续，H_model 尚未显现（轻触近似线性）；
- load 段：H_model 的模型误差随载荷显现，H_force 的偏置被常量项吸收。
故 S 近似块三角，κ_fi=λ_min(J_fi)/λ_max(J_fi) 由阶段对比度（零力窗的信噪比、轻触/加载的载荷比）控制。若删除零力窗，H_force 与 H_geo 在观测上不可分，J_fi 奇异——这正是第 64 轮 CGG 的不可辨识性。∎

**引理 8（认证前缀的执行安全）** 设 k*≤m。对后验支持集 supp_δ 内每个假设 H，CSC 已验证前 k* 步 ρ_safe≥0；对不在支持集内的假设，其总后验质量 ≤δ_fi。视觉 conformal 以 ≥1−α_vis 覆盖 e_vis。由联合界，单块执行 k* 步内发生越界（力/滑移/几何）的概率
P[越界] ≤ α_chunk + δ_fi + α_vis + α_geo。
由于 k*≤m，即使故障在块首激活，检出或强制重规划也发生在越过不可逆点之前。故块承诺不引入超出单步安全的新风险。∎

**定理 7（VISTA 端到端归因-安全）** 在 A88–A92 下：
1. **故障可分离**：三阶段被激励时，ρ 的经验协方差非奇异、J_fi≻0，归因后验以速率 O(exp(−n·κ_fi/2)) 集中（引理 7）；归因正确时只膨胀被归因的球（定义 221/227），不会在正确几何上误降级。
2. **视觉是前置而非真值**：VCV 只在观测到接触斑不符时允许 H_geo；`visual_unobservable` 时默认 H_force/被动观测（定义 223），避免"看不见当不存在"。
3. **物理伤害受控**：AFA 在易损物体上禁用接触探针，改用 visual_probe/null_test；CSC 限制 k*≤m（定义 225/226）。
4. **证书五层链**：Valid(J_vista) ⇔ GRIP 有效 ∧ 归因确定或已判别 ∧ k*≥1 ∧ 块签名一致 ∧ 视觉不可观测已标注。
5. **优雅降级**：视觉失效→w_vis↓、退回 GRIP；F/T 失效→归因 H_force、视觉主导；两者同时失效→判 ambiguous、safe_idle + compliant retreat；未知故障→判 ambiguous（若后验不集中）并保守降级。
6. **实时性**：实时路径 ≤2.5ms，零学习写操作（A93）。∎

**定理 8（长预测、短执行的近最优性）** 设块长 H 使动作估计方差 ∼σ_π²/H（时间集成的标准结论），故障不可逆视界为 m，单步检出概率 q。定义风险
R(H,k)=c₁·σ_π²/H + c₂·1[k>m]，
其中第二项表示执行前缀越过不可逆点后故障可能造成不可逆伤害。对 k≤m，第二项为 0，R 关于 k 不变、关于 H 单调递减；对 k>m，风险跃升且随 k−m 增加。故最优策略为
H* 取计算允许的最大值、k*=min(H,m)。
这给出"长预测、短执行"的严格理由：**把长视界只用于方差缩减与前瞻一致性，把执行承诺严格截断在不可逆视界内。** ∎

**命题（归因降低过度保守）** 第 64 轮对任意 CGG 拒绝都将单一 r 膨胀 κ_infl 倍，球体积膨胀 κ_infl^{d_φ}。VISTA 在 H_force 时只膨胀 r_force，r_geo 不变；若真实故障为 H_force 而几何正确，VISTA 的几何搜索域体积仅为第 64 轮的 1/κ_infl^{d_φ}（几何分量），避免了"正确几何被错误保守化"。反之 H_geo 时 r_force 不变，保留已标定力传感器的精度。∎

## 5. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| VPG 视觉预测残差（实时 ROI） | 光流 ROI + 编码 **<0.2ms** | O(ROI) | split-conformal 覆盖 ≥1−α_vis |
| 阶段切分（实时） | 阈值 + 缓冲 **<0.05ms** | O(1) | 仅依赖接触状态/力阈值 |
| VCV（语义流） | 分割/形变检测 **<3ms** | O(ROI) | `visual_unobservable` 显式安全退化 |
| FIR 归因（语义流） | 15 维 × 6 假设 **<0.5ms** | O(1) | 引理 7：J_fi≻0 时可辨识 |
| AFA 判别探针（语义流） | 6 探针 × 互信息 **<30ms** | O(|A|·d_H) | 互信息最大化，s.t. 力/形变安全 |
| CSC 认证前缀（语义流） | O(m·|supp|) **<1ms** | O(m) | 引理 8：P[越界]≤α_chunk+δ_fi+α_vis |
| RSC-V | O(1) **<0.01ms** | O(1) | 定向膨胀、r 有界 |
| WCV-V 编译（实时） | n_worst=8 **<1ms** | O(n_worst) | 归因边缘化 CVaR |
| OLP 证据融合（语义流） | 输入 +视觉/块特征 **<0.2ms** | O(m·d_out) | 定理 8 方差界 |
| CSP-V 块规划（语义流） | 块级 A* **<5ms** | O(|V_skills|·|blocks|) | 技能块签名 OOD 检测 |
| AIC-V 认证（语义流） | n_cert=128 **<50ms** | O(n_cert) | 视觉/时序/共因最坏 |
| VISTA 实时路径 | 视觉 0.2 + 阶段 0.05 + CSC 0.02 + 其余同 GRIP ≈ **<2.5ms** | — | 零学习写操作（A93）；语义流卸载世界模型 |

**正确性定理（VISTA-Complete）** 见定理 7；核心是**把第 64 轮不可辨识的"几何 vs 传感器 vs 模型"二分，升级为三阶段可辨识的故障归因**，并新增"长预测、短执行"使块级时序承诺不放大风险。

## 6. 实验设计 E231–E240

| 实验 | 设计 | 指标 | 目标 |
|---|---|---|---|
| E231 VCV 接触验证 | 透明/镜面/遮挡/正常物体；注入几何幻觉，对比有/无 VCV 门控 | CGG 误降级率 / 接触存在 AUC / 安全退化 | 误降级 −60% / ≥0.95 / 全覆盖 |
| E232 FIR 故障归因 | 注入 5 类故障（几何幻觉、F/T 偏置、软接触模型错、视觉 patch、策略 OOD）+ 未知故障 | 混淆矩阵 / 归因准确率 / 未知故障 OOD 召回 | ≥90% / ≥85% |
| E233 阶段可辨识性 | 消融阶段（去掉零力窗/轻触/加载）；测 S 条件数与归因准确率 | κ_fi / 条件数 / 准确率 | 条件数降 ≥5×，去阶段退化 ≥30% |
| E234 AFA 判别探针 | 对比第 64 轮 D-最优 APP、随机探针；记录判别所需接触次数与累计力 | 判别接触次数 / 累计力 / 伤害 | 次数 −50% / 累计力 −60% / =0 |
| E235 视觉力代理 | 软体/易损物体（蛋/纸杯/软果）非接触估 k 与 f_safe；含透明退化 | k 相对误差 / f_safe 保守性 / 损伤 | ≤25% / 不冒进 / =0 |
| E236 CSC 认证前缀 | 对比固定 k=H、k=1、CSC 自适应 k*；注入块内故障 | 违规率 / 成功率 / 平均 k* | 违规=0 / 不降 / 自适应 |
| E237 长预测短执行消融 | H∈{4,8,16,32}×k∈{1,4,8,16}，测方差、违规、恢复 | 动作方差 / 越界率 / 恢复时间 | H↑方差↓，k>m 违规↑ |
| E238 端到端 vs 第 64 轮 | 几何幻觉 + F/T 偏置 + 易损物体 + 透明 + 多接触 | 成功率 / 误降级 / 损伤违规 / 归因正确率 | +25% / −60% / =0 / ≥90% |
| E239 共因故障 | 同一透明/对抗物体同时骗过几何与视觉，分"力正常/力也坏" | ambiguous 判定率 / 安全降级 / 误归因 | ≥90% / 100% / ≤10% |
| E240 压力测试 | 未知故障类型、视觉 patch、块重放/时序错位、延迟 30s | 安全率 / fault_entropy 有界 / 恢复时间 | 100% / 有界 / ≤2s |

## 7. 已知风险

**一句话**：VISTA 的归因能力依赖"故障属于有限假设集、且视觉与几何的失效相互独立"两个假设；真实故障常是未知类型的组合，且透明/镜面/对抗 patch 会让视觉与几何**共享同一个分布外失效源**，此时 FIR 会把未知复合故障强行归入最近假设、只膨胀错误的球——**第 64 轮的单点故障升级为"归因错误的复合故障"，且系统因"已经归因"而更自信地继续执行**，这是本轮全部可辨识性与认证前缀论证共同依赖的隐藏假设（A88）。

**次级风险与缓解**：
1. **未知故障被强行归类**：有限假设集的固有缺陷；缓解：设 ambiguous 阈值与后验熵上界，熵过高即拒绝归因、走最保守联合膨胀 + safe_idle；离线持续扩充故障库。
2. **视觉与几何共因失效**：透明/镜面/对抗 patch 同时骗过两者；缓解：AIC-V 显式建共因模型，共因下不要求归因正确、只要求判 ambiguous 并降级；引入第三个物理独立通道（IMU/本体感觉）作为未来工作。
3. **世界模型长视界误差累积**：H 越大，e_vis 与 d_chunk 越被模型误差主导，误判 H_policy；缓解：conformal 只承诺边际覆盖、分视界校准 q_vis(α,h)；H 上限按模型验证误差设定。
4. **阶段切分依赖接触状态**：自由空间与轻触边界模糊，零力窗被污染，H_force 签名减弱；缓解：用力阈值 + 视觉接近速度双判据；null_test 显式插入，不依赖自然阶段。
5. **视觉力代理适用域窄**：仅小形变线性区、需纹理，透明/软塑退化；缓解：只用于 f_safe 下界估计，与 F/T 交叉校验，失效即回退。
6. **CSC 组合爆炸**：需对后验每个假设×每步验证；缓解：只取 top-2 假设 + 最坏边界；其余质量按 δ_fi 计入风险预算。
7. **实时预算**：视觉 ROI 与阶段判定逼近 2.5ms；缓解：ROI 降采样、事件相机触发、与 LSF 共享编码、把世界模型全部留在语义流。
8. **conformal 在分布漂移下失准**：覆盖率下降导致 α_vis 名不副实；缓解：在线重校准 + 漂移检测（e_vis 分位数漂移即触发重标定）。
<!-- ARTIFACT:END -->