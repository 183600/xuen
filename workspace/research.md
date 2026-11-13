# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。
<!-- IDEA:START -->
# 第 63 轮（承接第 62 轮「ROSE 鲁棒在线场景进化闭环」IP-183~192；本轮灵感：「故障诊断」×「安全交互」）

> 第 62 轮 ROSE 把对齐变成在线学习（OLP）、把偏差变成 CVaR 球（WCV+RSC）、把经验变成场景银行（SBR+SHC），并自称最大风险是 A72：**RSC 靠执行残差反演物理偏差，若 J_φ 病态或残差被控制回路吸收，球半径 r_t 系统性低估，全部安全保证退化为纸面**。第 63 轮认为，ROSE 的残差框架还缺四个更根本的维度：
> 1. **残差无类型**：ROSE 把所有异常压缩成一个标量 e_t，再经 J_φ⁺ 反演成单一参数球。它只回答「偏了多少」，不回答「哪里坏了」。传感器偏置、执行器增益损失、接触滑移、模型参数漂移在残差里可能长成同一个样子，但它们的容错动作、安全集收缩方向、可恢复性完全不同——**用同一个球兜底四类病，必然要么过保守、要么漏检**。
> 2. **A72 的自证循环仍在**：残差由被控系统自己产生，控制器越强，越会把偏差吸收进零残差；单残差 + 伪逆对病态 J_φ 无免疫。ROSE 用「更大的 r_t」兜底，但「更保守」≠「诊断正确」，系统无法判断保守是否已经足够。
> 3. **安全交互只有「拦截」，没有「诊断-恢复」**：Shield 只把约束投影回单一安全集，不区分故障类型；没有故障隔离、没有容错控制重构、没有安全降级/交接的语义。安全集是「一个球」，而不是「一张按故障分型的表」。
> 4. **人只在回路外**：ROSE 的 DMS 在正常交互中问需求，但异常时人不参与诊断；而很多故障（「你刚才是不是感到打滑？」）只有人能提供关键证据。反过来，「问人」本身也是一种交互动作，可能分心、可能危险——ROSE 没有「安全可问」的概念。

## 0. 直觉与动机

**灵感 1（故障诊断 → 从「偏差大小」到「故障类型」）**
直觉：诊断的核心不是把残差做大，而是设计一组「各管一段」的残差，让每类故障在残差空间留下可区分的签名。用奇偶空间/未知输入观测器把未知扰动（负载、坡度、人的外力）从残差中解耦，只留下故障方向。关键洞见：ROSE 要求「J_φ 良态」（每个参数都可辨识），这太强；故障诊断只要求「**每类故障的签名可区分**」（isolability），这是一个更弱、更可设计、也可在线检验的条件。把 A72 从「参数可辨识」降级为「故障可隔离」，等于把信仰换成工程上可复核的性质。

**灵感 2（故障诊断 → 开集拒识：错误的自信最危险）**
直觉：最危险的不是「没诊断出来」，而是「把未知故障误诊成已知故障」。后者会让系统带着错误的自信进入错误的安全集。所以诊断必须带**开集监控**：当残差落在已知故障签名张成的子空间之外时，拒绝隔离，标记「未建模故障」，退回被动安全核。宁可诚实地说「我不知道」，也不要自信地错。

**灵感 3（安全交互 → 两层安全：物理层不依赖诊断，任务层才依赖诊断）**
直觉：安全必须分层。**物理安全层**（力矩/力/速度/人机距离的硬件包络 + 原始测量级不变量）永不依赖诊断，误诊也不能突破；**任务安全层**（不滑落、不碰撞、不越界）才允许由故障条件安全集来放宽性能。这样，「诊断错了」最坏只导致任务失败，不会导致人身/硬件伤害。这是安全交互的底线，也是把 ROSE 的「球兜底」升级为「分型兜底」的关键。

**灵感 4（安全交互 → 安全可问：人既是监督者也是传感器）**
直觉：人能在异常时提供机器拿不到的证据（「我感觉到抖了一下」），但「问人」是一个有代价的交互动作。因此只在**安全可问态**发问：机器人已进入被动核、任务暂停、人不在危险接触中、问题的信息增益足够高、交互预算允许。人的回答只作为**有界可信度**的诊断证据，必须与物理残差互证，单次回答不能翻案。人是最后的否决者，但不是安全保证的必要条件。

**灵感 5（故障诊断 → 安全主动诊断）**
直觉：有些故障只能靠主动激励区分（传感器偏置 vs 执行器增益损失）。但激励必须安全：在被动核内选一个「最能把两个假设分开」的动作，且风险增量受控。这把诊断从「被动看残差」变成「受约束的主动实验」，也把「诊断需要激励」与「交互需要安全」这对矛盾显式化。

**灵感 6（合流 → FIDES）**
闭环：结构化残差 → 检测 → 类型化隔离/开集拒识 → 可诊断性评估 →（安全主动诊断 | 安全询问）→ 故障条件安全集 → 容错恢复/安全交接 → 证据回流签名库。三者不是并列而是咬合：**诊断回答「哪里坏了」，安全交互回答「坏了以后怎么和人一起安全地降级、询问、恢复」**。第 62 轮 ROSE 是「偏差驱动保守」，FIDES 是「**故障驱动分型、分型驱动安全交互**」。

## 1. 形式化定义（增量：定义 185–197）

- **定义 185（FIDES 闭环）**：FIDES = (ROSE, SRD, DET, TFI, OSM, DGM, FSC, PSI, ADX, SafeAsk, FTR, J_fides)。定位：ROSE 的「可诊断化 × 交互安全化」升级，不推翻既有接口；诊断与学习只在语义流/后台，实时流零学习写。
- **定义 186（故障假设空间与签名）**：ℱ = ℱ_known ∪ {f_∅} ∪ {unknown}；每类故障 f 的签名 s_f = E[r_t | f, θ_f=1] ∈ ℝ^q；签名矩阵 S = [s_f]；θ_f 为故障幅值。
- **定义 187（结构化残差 SRD）**：r_t = P(y_t − C x̂_t)，P 为奇偶/未知输入观测器投影，满足 P E_d = 0（对未知扰动 d 解耦），且各通道对设计的故障子集敏感，形成结构化签名。
- **定义 188（检测 DET）**：逐通道 CUSUM/GLR 统计量 g_t^j = max(0, g_{t-1}^j + |r_t^j|/σ_j − ν_j)；报警当 max_j g_t^j > h_j。
- **定义 189（类型化隔离 TFI）**：b_t(f) ∝ b_{t-1}(f)·exp(ℓ_f(r_t))，ℓ_f 为故障 f 的残差似然；θ̂_f 为幅值 MLE；输出故障类型、幅值与后验。
- **定义 190（开集监控 OSM）**：ν_t = ‖(I−P_S)r_t‖ / (‖r_t‖+ε)，P_S 为已知签名张成子空间的投影；ν_t > τ_os ⇒ 拒绝隔离，A_t ∋ unknown。
- **定义 191（可诊断性 DGM）**：D_t = min_{f≠g∈A_t} ‖s_f−s_g‖_Σ / 2；D_t < γ_d ⇒ 触发 ADX 或 SafeAsk。
- **定义 192（故障条件安全集 FSC 与被动核 𝒞_0）**：𝒞_hw 为硬件包络；𝒞_0 ⊆ 𝒞_safe(f) ⊆ 𝒞_hw，𝒞_0 在所有有界故障下任务安全；𝒞_safe(A_t) = ∩_{f∈A_t} 𝒞_safe(f)，unknown ∈ A_t ⇒ 𝒞_safe = 𝒞_0。
- **定义 193（交互安全不变量 PSI）**：z_t = (d_h, v, F_c, τ, slip, power)；h_int(z) ≥ 0；实施 ḣ_int ≥ −α h_int + 扰动界，测量延迟按预测界处理；由低层硬件强制。
- **定义 194（安全可问态 SafeAsk）**：SafeAsk_t = 𝟙[K ∈ 𝒞_0 hold] ∧ 𝟙[task paused] ∧ 𝟙[human safe] ∧ 𝟙[ΔH ≥ δ_H] ∧ 𝟙[cost ≤ B_int]；人证据 LLR 截断 + 物理残差互证。
- **定义 195（安全主动诊断 ADX）**：u* = argmax_{u∈𝒰_adx} I(ℱ; r_{t+1} | u, b_t) s.t. u 的后果在 𝒞_0 内、风险增量 ≤ δ_risk、交互预算 ≤ B_adx。
- **定义 196（容错恢复 FTR）**：模式机 {NORMAL, DEGRADED(f), SAFE_HOLD, ASK, HANDOVER, RECOVER}；转移守卫要求目标模式的安全集已被认证。
- **定义 197（证书 J_fides 与闭环算子）**：J_fides = (J_rose, DET ids, b_t/A_t, ν_t, D_t, ρ_0, ρ_int, mode, ask_log, recovery_ver, coverage_decl)；Valid ⇔ 见产物区；算子见产物区。

## 2. 关键算法骨架（完整伪代码见产物区）

```python
# 语义流：诊断（低频，全部学习/推理在此）
r = srd.residual(y, u, x_hat)                    # 对扰动解耦的结构化残差
alarm, ids = det.cusum(r)                         # 逐通道 CUSUM
b, A, nov = tfi.isolate(r, alarm)                 # 类型化隔离
if nov: A = A | {'unknown'}                       # 开集拒识：只信被动核
if dgm.separation(A) < gamma_d:                   # 诊断不清楚
    u = adx.safe_probe(A, core=C0) or safe_ask(A) # 安全主动诊断/安全询问
K = fsc.compile(A, core=C0)                       # 故障条件安全集 ∩ 被动核
mode = ftr.transition(b, A, K)                    # 降级/保持/交接/恢复
# 实时流：物理安全（高频，零学习写）
K = clip_to_hw_env(K, hw)                         # 硬件包络不可绕过
assert psi.invariant(z_meas)                      # 原始测量级不变量
dispatch(K)
```

## 3. 保证概要与推导要点（完整推导见产物区）

- **命题 1（隔离错误率）**：高斯残差下 ML 隔离 P_err(f) ≤ Σ_{g≠f} exp(−‖s_f−s_g‖²/(8σ²))；签名间隔越大，误隔离越低。
- **命题 2（检测）**：CUSUM 在 K_f = μ_f²/(2σ²) 下 E_f[delay] ≤ (h+O(1))/K_f，ARL_0 ≥ e^{h}（近似界）。
- **定理 1（物理安全与诊断解耦）**：若部署 K_t 始终在 𝒞_hw 且 PSI 在扰动/延迟界内有效，则 z_t ∈ 𝒮_int 对所有 t 成立，**与诊断对错无关**。
- **定理 2（任务安全的诊断条件）**：若真故障 f* ∈ A_t 对所有 t 成立，则 K_t ∈ 𝒞_safe(A_t) ⊆ 𝒞_safe(f*) ⇒ 任务安全；若误隔离使 f* ∉ A_t，物理安全仍由定理 1 保证，但任务安全可能失败。
- **命题 3（开集兜底）**：ν_t > τ_os ⇒ unknown ∈ A_t ⇒ K ∈ 𝒞_0；在未建模故障幅值有界时，任务+物理安全同时保持。
- **命题 4（主动诊断安全）**：𝒰_adx ⊆ 𝒞_0 且风险预算约束 ⇒ 探测不破坏 PSI；互信息近似次模 ⇒ 贪心 (1−1/e)。
- **命题 5（询问可信度封顶）**：单次人证据 LLR 截断 + 需物理残差互证 ⇒ 单次（甚至对抗性）回答不能翻转隔离结论。
- **实时性**：PSI/硬件裁剪 O(1)，诊断/学习全在语义流，实时路径保持 ≤1ms 且零学习写。

## 4. 实验概览（完整设计见产物区 E211–E220）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E211 SRD | 扰动解耦是否把故障签名分开 | 签名间隔 ≥4σ，扰动泄漏 <10% |
| E212 TFI | 四类故障能否正确分型 | 隔离准确率 ≥95%，幅值误差 <10% |
| E213 OSM | 未知故障是否被拒识 | 误隔离率 →0，未知召回 ≥90% |
| E214 被动核 | 误诊注入下物理安全是否守住 | 力/接触违规 =0（对照 ROSE >0） |
| E215 DET | 检测延迟 vs 误报权衡 | 检测延迟 <200ms，ARL₀ >10⁴ 步 |
| E216 FSC | 分型后性能是否比单球高 | 任务成功率 +15pp，保守代价 −30% |
| E217 PSI | 人接近/意外接触下不变量 | 违规 =0，测量延迟 20ms 仍成立 |
| E218 SafeAsk | 噪声/对抗人回答是否污染诊断 | 误隔离增量 ≤2pp，交互成本 ≤预算 |
| E219 ADX | 传感器 vs 执行器故障能否区分 | 区分率 ≥90%，探测期零违规 |
| E220 端到端 vs ROSE | 复合故障 + 人机交互 | 违规 =0，恢复时间 −40%，任务 +20% |

## 5. 本轮最大风险

**一句话**：若未建模故障恰好落在已知签名子空间附近（ν_t 低于 τ_os），TFI 会自信地误隔离，A_t 排除真故障，FSC 编译出错误的任务安全集；一旦该故障幅值又超出被动核 𝒞_0 的设计包络，定理 1 的物理安全前提也被击穿——「诊断只放宽、不承担安全」的两层设计同时失效，J_fides 变成「有签名、有证书、但错得自信」。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 63 轮产物 · 创新点清单 v1：FIDES（故障隔离驱动的安全交互闭环：结构化残差 × 类型化诊断 × 开集拒识 × 故障条件安全集 × 被动安全核 × 安全询问，SRD×TFI×OSM×DGM×FSC×PSI×ADX×SafeAsk×FTR×J_fides）

> 承接第 62 轮 IP-183~192（ROSE：OLP×WCV×RSC×ARA×SBR×SHC×MEL-OA×Shield×OCB×J_rose）。第 62 轮把安全押在 A72（J_φ 良态 + 残差可观测）上，并用一个标量球 B(φ̂_t, r_t) 兜住全部偏差。本轮不换球、不调参，而是**给异常加上「类型」、给安全加上「层级」、给人加上「安全可问的接口」**：结构化残差把未知扰动与故障解耦；类型化诊断回答「哪里坏了」；开集拒识防止「自信误诊」；故障条件安全集把「一个球」变成「一张按故障分型的表」；被动安全核把物理安全从诊断中解耦；安全可问态让人的反馈成为有界诊断证据而不是安全前提。实现 **「故障可分型、误诊不伤人、未知不硬猜、问人有边界、恢复有守卫」**。

> IP 编号：IP-193~IP-202（共 10 个），全部挂在 ROSE 骨架上，不推翻既有接口；诊断与学习只在语义流/后台，实时路径仍零学习写、≤1ms。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 62 轮） |
|---|---|---|---|
| IP-193 | SRD Structured Residual Decoupling | 新增 | 奇偶/未知输入观测器残差，未知扰动解耦 + 结构化故障签名，替代单标量 e_t |
| IP-194 | TFI Typed Fault Isolation | 新增 | 贝叶斯签名匹配，输出故障类型、幅值与后验 b_t，替代「只有一个 r_t」 |
| IP-195 | OSM Open-Set Fault Monitor | 新增 | 未知故障拒识（签名子空间外检测），防止把新故障误诊成已知故障 |
| IP-196 | DGM Diagnosability Guarantee Monitor | 新增 | 在线可隔离性度量 D_t，低于阈值触发主动诊断/安全询问 |
| IP-197 | FSC Fault-conditioned Safe Set Compiler | 升级 WCV | 按故障类型与模糊集 A_t 编译安全集，保留被动核 𝒞_0，替代单球 |
| IP-198 | PSI Passive Safety Invariant | 升级 Shield | 原始测量级交互不变量，硬件强制、与诊断解耦，守住物理安全底线 |
| IP-199 | ADX Active Diagnosis eXcitation | 新增 | 在 𝒞_0 内选信息增益最大的安全探针，区分「只能靠激励分开」的故障 |
| IP-200 | SafeAsk Human-in-the-loop Protocol | 升级 DMS | 安全可问态门控 + 有界人证据 + 物理残差互证，人作为诊断传感器而非安全前提 |
| IP-201 | FTR Fault-Tolerant Recovery | 新增 | 模式机：降级/保持/询问/交接/恢复，转移守卫要求目标安全集已认证 |
| IP-202 | J_fides Certificate & FIDES Loop | 升级 J_rose/ROSE | 双层安全证书 + 诊断覆盖声明 + 故障分型审计，实时流零学习 |

## 1. 符号体系增量（定义 185–197）

| 符号 | 含义 |
|---|---|
| `FIDES = (ROSE, SRD, DET, TFI, OSM, DGM, FSC, PSI, ADX, SafeAsk, FTR, J_fides)` | 故障隔离驱动的安全交互闭环 |
| `ℱ = ℱ_known ∪ {f_∅} ∪ {unknown}` | 故障假设空间（f_∅ 表示无故障） |
| `s_f = E[r_t \| f, θ_f=1] ∈ ℝ^q`，`S = [s_f]` | 故障签名与签名矩阵 |
| `r_t = P(y_t − C x̂_t)`，`P E_d = 0` | 结构化残差；P 为奇偶/未知输入观测器投影，解耦未知扰动 d |
| `g_t^j = max(0, g_{t-1}^j + \|r_t^j\|/σ_j − ν_j)` | 逐通道 CUSUM 检测统计量 |
| `b_t(f) ∝ b_{t-1}(f)·exp(ℓ_f(r_t))` | 类型化隔离后验；ℓ_f 为故障 f 的残差似然 |
| `θ̂_f = max(0, s_fᵀr_t / s_fᵀs_f)` | 故障幅值 MLE |
| `ν_t = ‖(I−P_S)r_t‖ / (‖r_t‖+ε)` | 开集新颖度；P_S 为已知签名子空间投影 |
| `A_t = {f : b_t(f) ≥ τ_amb} ∪ ({unknown} if ν_t > τ_os)` | 模糊故障集 |
| `D_t = min_{f≠g∈A_t} ‖s_f−s_g‖_Σ / 2` | 可诊断性（最小签名间隔） |
| `𝒞_hw` | 硬件/物理包络（力矩、力、速度、人机距离、能量），低层强制 |
| `𝒞_0 ⊆ 𝒞_safe(f) ⊆ 𝒞_hw` | 被动安全核 / 故障条件安全集 / 硬件包络 |
| `𝒞_safe(A_t) = ∩_{f∈A_t} 𝒞_safe(f)` | 模糊集下的安全集；unknown ∈ A_t ⇒ 𝒞_safe = 𝒞_0 |
| `z_t = (d_h, v, F_c, τ, slip, power)` | 交互安全状态（原始测量或低层估计） |
| `h_int(z) ≥ 0`，`ḣ_int ≥ −α h_int + 扰动界` | PSI 交互安全屏障（CBF） |
| `SafeAsk_t = 𝟙[K∈𝒞_0 hold]∧𝟙[task paused]∧𝟙[human safe]∧𝟙[ΔH≥δ_H]∧𝟙[cost≤B_int]` | 安全可问态 |
| `u* = argmax_{u∈𝒰_adx} I(ℱ; r_{t+1} \| u, b_t)` | 安全主动诊断的信息增益目标 |
| `L_max` | 单次人证据对数似然比截断上界 |
| `Modes = {NORMAL, DEGRADED(f), SAFE_HOLD, ASK, HANDOVER, RECOVER}` | 容错交互模式机 |
| `coverage_decl` | 证书显式声明的已知故障集与未建模故障幅值上界 |
| `J_fides = (J_rose, DET ids, b_t/A_t, ν_t, D_t, ρ_0, ρ_int, mode, ask_log, recovery_ver, coverage_decl)` | 诊断-安全证书 |

## 2. 形式化定义（完整版）

**定义 185（FIDES 闭环）** FIDES 是 ROSE 的「可诊断化 × 交互安全化」升级。不变式有三条：
1. **诊断与安全分层**：物理安全（𝒞_hw + PSI）永不依赖诊断；任务安全（𝒞_safe(A_t)）允许依赖诊断。
2. **诊断可拒识**：当未知故障不能被已知签名解释时，拒绝隔离并退回 𝒞_0，不允许「强行归类」。
3. **实时零学习**：SRD 残差生成、PSI 检查、硬件裁剪在实时路径；CUSUM、TFI、OSM、DGM、ADX、SafeAsk、FTR 全在语义流/后台，与 ROSE 的 A75 一致。

**定义 186（故障假设空间与签名）** ℱ_known 覆盖本轮声明的故障类：传感器偏置/漂移/卡死（f_S^b, f_S^st）、执行器增益损失/饱和/死区（f_A^g, f_A^s）、接触滑移/低摩擦（f_C^slip）、模型参数漂移（f_M^μ, f_M^k）、异常人接触/交互扰动（f_H）。每类故障 f 在残差空间的签名 s_f = E[r | f, θ_f=1]；θ_f ∈ Θ_f 为幅值（区间）。签名矩阵 S 的列可预先由辨识实验/物理模型获得，并在语义流低频重标定。`coverage_decl = (ℱ_known, {Θ_f}, δ_u)` 显式声明覆盖范围与未建模故障幅值上界 δ_u。

**定义 187（结构化残差 SRD）** 线性化观测模型 y_t = C x_t + E_d d_t + E_f θ_f + ε_t，d_t 为未知扰动（负载、坡度、人外力），θ_f 为故障幅值。取投影 P 满足 P E_d = 0（奇偶空间）或采用未知输入观测器（UIO）使状态估计误差对 d 解耦，则
r_t = P(y_t − C x̂_t) = P E_f θ_f + P ε_t。
进一步把 P 的行设计成「结构化」：第 i 个残差通道对故障子集 ℱ_i 敏感、对其余故障不敏感（S_{ij}=0/1 的签名编码）。这样隔离不必依赖单个标量的幅值，而依赖多通道的**符号/支持模式**。非线性系统用局部线性化 + 滑模/自适应残差观测器近似，声明线性化误差界。

**定义 188（检测 DET）** 每个通道 j 归一化后做 CUSUM：g_t^j = max(0, g_{t-1}^j + |r_t^j|/σ_j − ν_j)，报警当 max_j g_t^j > h_j。对缓变故障（漂移）可换 GLR；对突发故障 CUSUM 更快。检测器输出报警时刻 t_d 与触发通道集合 ids。

**定义 189（类型化隔离 TFI）** 对每个 f ∈ ℱ_known，取幅值 MLE θ̂_f = max(0, s_fᵀr_t / s_fᵀs_f)，残差似然
ℓ_f(r_t) = −½‖r_t − θ̂_f s_f‖²_Σ − ½ log det Σ + log prior_f。
后验 b_t(f) ∝ b_{t-1}(f)·exp(ℓ_f(r_t))，再做温度/遗忘因子平滑。输出 f̂_t = argmax b_t、θ̂_{f̂}、以及模糊集 A_t。对「无故障」的 f_∅ 也保留假设，避免把噪声当故障。

**定义 190（开集监控 OSM）** 令 P_S 为向 span{s_f : f∈ℱ_known} 的正交投影。新颖度 ν_t = ‖(I−P_S)r_t‖/(‖r_t‖+ε)。当报警且 ν_t > τ_os 时，认为残差不能被任何已知签名解释，令 A_t ∋ unknown，拒绝给出 f̂。unknown 不是「一类故障」，而是「拒绝归类的占位」，其唯一安全语义是退回 𝒞_0。τ_os 由标定集上的已知故障重构误差分位数确定。

**定义 191（可诊断性 DGM）** D_t = min_{f≠g∈A_t} ‖s_f−s_g‖_Σ / 2，即当前模糊集内最接近的两个签名在半噪声尺度下的间隔。D_t < γ_d 表示「现有观测不足以分开剩余假设」，触发 ADX（若存在安全探针）或 SafeAsk（若问题可被人回答）。D_t 同时是 J_fides 的一个显式字段：证书不隐瞒「诊断有多确定」。

**定义 192（故障条件安全集 FSC 与被动核 𝒞_0）** 令 𝒞_hw 为硬件包络。对每类 f 与幅值区间 Θ_f，定义
𝒞_safe(f) = {K ∈ 𝒞_hw : ∀θ_f∈Θ_f，任务约束与 PSI 均成立}。
被动核 𝒞_0 = {K : ∀f∈ℱ_known∪ℱ_unmodeled, ‖θ_f‖≤δ_u，任务约束与 PSI 均成立}，即「在所有声明故障下都任务安全」的保守集合。构造上保证 𝒞_0 ⊆ 𝒞_safe(f) ⊆ 𝒞_hw。模糊集下
𝒞_safe(A_t) = ∩_{f∈A_t} 𝒞_safe(f)，且 unknown∈A_t ⇒ 𝒞_safe(A_t)=𝒞_0。
单调性：A ⊆ A' ⇒ 𝒞_safe(A') ⊆ 𝒞_safe(A)。因此**诊断越确定，安全集越大、性能越高；诊断不确定时自动退回保守核**。这与 ROSE 的「r_t 越大越保守」方向一致，但粒度从「一维半径」变成「按故障类型的交集」。

**定义 193（交互安全不变量 PSI）** z_t 为原始测量/低层估计的交互状态：人机距离 d_h、速度 v、接触力 F_c、关节力矩 τ、滑移速度 slip、功率 power。定义归一化裕度
h_int(z) = min{ (d_h−d_min)/d_min, (F_max−F_c)/F_max, (v_max−v)/v_max, (τ_max−|τ|)/τ_max, (slip_max−slip)/slip_max, (P_max−P)/P_max }。
执行层要求 ḣ_int ≥ −α h_int + w_bound，其中 w_bound 覆盖测量噪声、延迟与未建模故障的扰动界；测量延迟 τ_d 用预测界 h_int(z_{t+τ_d}) ≥ 0 保守处理。PSI 由低层驱动/嵌入式层实现，**上层（含诊断、RL、对话）不可绕过**（A79）。

**定义 194（安全可问态 SafeAsk）** 仅在
SafeAsk_t = 𝟙[K_t∈𝒞_0 的 safe-hold 模式] ∧ 𝟙[任务已暂停] ∧ 𝟙[人不在危险接触/危险距离] ∧ 𝟙[问题信息增益 ΔH ≥ δ_H] ∧ 𝟙[交互成本 ≤ B_int]
时允许发问。问题 q 从「能最大区分 A_t 中剩余假设」的模板集中选。人回答 y_h 的似然用可靠性模型 p(y_h | f, q)（含混淆矩阵与可靠性区间），更新时对单次 LLR 截断 |log(p(y_h|f)/p(y_h|g))| ≤ L_max，并要求物理残差互证：只有当 b_t 与残差似然不矛盾时，才允许人证据改变隔离结论。这样单次（甚至对抗性/错误的）回答不能翻案。

**定义 195（安全主动诊断 ADX）** 探针库 𝒰_adx 是「经认证的、执行后仍处于 𝒞_0 的动作原语」（小幅度、低力、慢速、可立即停止的激励，如轻微往复、阻抗微调、单关节低幅扫频）。选择
u* = argmax_{u∈𝒰_adx} I(ℱ; r_{t+1} | u, b_t)
s.t. C0.admits(u)，risk(u) ≤ δ_risk，cost(u) ≤ B_adx，且不延迟紧急 safe-hold。
互信息用当前后验与签名的局部高斯近似计算；若 u* 的信息增益低于阈值，则不发探针（避免无意义扰动）。

**定义 196（容错恢复 FTR）** 模式机：
- NORMAL：b_t(f_∅) ≥ τ_norm 且 D_t ≥ γ_d；
- DEGRADED(f)：f 已隔离（b_t(f) ≥ τ_iso）且 f∈ℱ_known，K_t∈𝒞_safe(f)；执行容错控制（传感器偏置补偿、执行器增益重分配、阻抗重配、冗余关节再分配）；
- SAFE_HOLD：unknown∈A_t 或 D_t<γ_d 或 b_t 未达隔离阈值；K_t∈𝒞_0 的 safe-hold；
- ASK：满足 SafeAsk_t 且诊断可被人区分；
- HANDOVER：故障不可恢复或人要求接管；
- RECOVER：在 SAFE_HOLD 后重新检测，残差清除且 J_fides 复验通过才回 NORMAL。
转移守卫是硬性的：任何目标模式必须已有认证的安全集；任何不确定都只能进更保守的模式，不能「跳级」。

**定义 197（J_fides 证书与 FIDES 闭环算子）** 证书字段与验证规则见第 5 节。闭环算子：
- 语义流（10–100Hz）：SRD 残差 → DET → TFI/OSM → DGM →（ADX | SafeAsk）→ FSC → FTR → J_fides 构建 → 事件回流。
- 后台：签名重标定、人可靠性模型更新、被动核随磨损/负载重新认证、红队故障注入测试。
- 实时流（1–10kHz）：读锚点 → SRD 残差（只读）→ PSI 检查 → 硬件裁剪 → fault-aware shield → 派发；零学习写。

## 3. 关键算法伪代码

### IP-193 SRD + IP-188 DET（结构化残差与检测）

```python
class StructuredResidualGenerator:
    """P E_d = 0：对未知扰动解耦；各通道设计成结构化故障签名。"""
    def __init__(self, P, C, sigma, nu, h):
        self.P, self.C = P, C
        self.sigma, self.nu, self.h = sigma, nu, h
        self.g = np.zeros(P.shape[0])

    def residual(self, y, u, x_hat):
        e = y - self.C @ x_hat
        return self.P @ e                       # q 维结构化残差

    def cusum(self, r):
        z = np.abs(r) / self.sigma
        self.g = np.maximum(0.0, self.g + z - self.nu)
        return bool((self.g > self.h).any()), np.where(self.g > self.h)[0]
```

### IP-194 TFI + IP-195 OSM（类型化隔离与开集拒识）

```python
def typed_isolate(r, S, A_known, sigma, prior, tau_os, tau_amb, K_amb=3):
    P_S = projector(S)                               # 已知签名子空间投影
    nov = np.linalg.norm((np.eye(len(r)) - P_S) @ r) / (np.linalg.norm(r) + 1e-9)
    if nov > tau_os:                                 # 开集：拒绝归类
        return prior.copy(), set(A_known) | {'unknown'}, nov, True

    loglik = []
    theta_hat = {}
    for f in A_known:
        s = S[f]
        th = max(0.0, float(s @ r) / float(s @ s + 1e-12))   # 幅值 MLE
        theta_hat[f] = th
        resid = r - th * s
        loglik.append(-0.5 * float(resid @ resid) / sigma**2 + np.log(prior[f] + 1e-12))
    b = softmax(np.asarray(loglik))
    order = np.argsort(-b)
    A = {A_known[i] for i in order[:K_amb] if b[i] >= tau_amb}
    return dict(zip(A_known, b)), A, nov, False
```

### IP-196 DGM（可诊断性监控）

```python
def diagnosability(A, S, sigma):
    if 'unknown' in A or len(A) < 2:
        return 0.0
    return min(np.linalg.norm(S[f] - S[g]) / (2.0 * sigma)
               for f in A for g in A if f != g)
```

### IP-197 FSC（故障条件安全集编译）

```python
def compile_safe_set(A, C0, safe_sets, hw_env):
    if 'unknown' in A:                               # 未知故障：只信被动核
        return C0 & hw_env
    C = intersect([safe_sets[f] for f in A])         # 模糊集下取交集
    return (C & hw_env) if C is not None else C0     # 永不超过硬件包络
```

### IP-198 PSI（交互安全不变量）

```python
def psi_check(z, zdot, alpha, delay_bound, z_bound):
    h = min_margin(z)                                # 原始测量：力/速度/距离/滑移/功率
    h_pred = h - delay_bound * z_bound               # 延迟下的保守下界
    if h_pred < 0.0 or (zdot + alpha * h) < -z_bound:
        return 'safe_hold'                           # 低层硬件同时裁剪，不可绕过
    return 'ok'
```

### IP-199 ADX（安全主动诊断）

```python
def safe_probe(A, b, C0, probes, risk_budget, B_adx):
    if len(A) < 2 or 'unknown' in A:
        return None
    best, best_gain = None, 0.0
    for u in probes:
        if not C0.admits(u):                         # 只允许落在被动核内的探针
            continue
        if probe_risk(u, A) > risk_budget or probe_cost(u) > B_adx:
            continue
        gain = mutual_info_faults(A, b, u)           # I(ℱ; r_{t+1} | u, b_t)
        if gain > best_gain:
            best, best_gain = u, gain
    return best if best_gain >= DELTA_I else None
```

### IP-200 SafeAsk（安全询问协议）

```python
def safe_ask(state, b, A, question, budget):
    if not (state.in_C0_hold and state.task_paused and state.human_safe):
        return b, None
    if question.information_gain(b, A) < DELTA_H:
        return b, None
    if question.cost > budget:
        return b, None

    y_h = state.dms.ask(question)                    # 只在安全可问态发问
    llr = np.clip(np.log(human_likelihood(y_h, A) + 1e-12), -L_MAX, L_MAX)
    b_new = normalize(b * np.exp(llr))

    if not physical_residual_corroborates(y_h, b_new, A):   # 必须物理互证
        return b, y_h                                # 单次回答不能翻案
    return b_new, y_h
```

### IP-201 FTR（容错恢复模式机）

```python
def ftr_transition(b, A, safe_sets, C0, D, mode_now):
    if 'unknown' in A:
        return 'SAFE_HOLD'
    f_hat = max(b, key=b.get)
    if b[f_hat] < TAU_ISO or D < GAMMA_D:
        return 'ASK' if safe_ask_possible else 'SAFE_HOLD'
    if safe_sets[f_hat].certified and f_hat in RECOVERABLE:
        return f'DEGRADED({f_hat})'
    return 'HANDOVER'
```

### IP-202 FIDES 闭环算子（整合）

```python
def FIDES_round(M, obs):
    # ———— 语义流（10–100Hz：诊断、学习、记账）————
    r = M.srd.residual(obs.y, obs.u, M.observer.state)
    alarm, ids = M.det.cusum(r)
    b, A, nov, rejected = M.tfi.typed_isolate(
        r, M.S, M.A_known, M.sigma, M.prior, TAU_OS, TAU_AMB)
    if rejected:
        A = A | {'unknown'}
    D = M.dgm.diagnosability(A, M.S, M.sigma)

    if alarm and D < GAMMA_D and 'unknown' not in A:
        u_adx = M.adx.safe_probe(A, b, M.C0, M.probes, RISK_BUDGET, B_ADX)
        if u_adx is not None:
            M.queue_probe(u_adx)                     # 执行期仍受 PSI/硬件裁剪
        else:
            b, _ = M.safeask.safe_ask(M.state, b, A, M.question(A), B_ASK)

    K = M.fsc.compile_safe_set(A, M.C0, M.safe_sets, M.hw_env)
    M.mode = M.ftr.ftr_transition(b, A, M.safe_sets, M.C0, D, M.mode)

    # ———— 实时流（1–10kHz：物理安全，零学习写）————
    K = M.hw.clip(K)                                 # 硬件包络不可绕过
    if M.psi.check(M.state.z, M.state.zdot) != 'ok':
        K = M.C0.safe_hold()                         # 被动核兜底
    cert_exec = M.ertc.dispatch(K)

    return M, K, M.build_j_fides(cert_exec, ids, A, b, nov, D)
```

## 4. 推导

**命题 1（隔离错误率上界）** 设残差在故障 f 下 r ~ 𝒩(s_f, σ²I)，隔离规则为最近签名（ML）。对 g≠f，误判 f→g 等价于 ‖r−s_g‖ ≤ ‖r−s_f‖，即 (s_g−s_f)ᵀr ≥ (‖s_g‖²−‖s_f‖²)/2。令 Δ = s_g−s_f，则 (Δᵀr − Δᵀs_f) ~ 𝒩(0, σ²‖Δ‖²)（在 f 下），误判概率 = P[𝒩(0,1) ≥ ‖Δ‖/(2σ)] ≤ exp(−‖Δ‖²/(8σ²))（高斯尾 Chernoff 界）。对全部 g 取并集界：
P_err(f) ≤ Σ_{g≠f} exp(−‖s_f−s_g‖²/(8σ²))。
因此只要最小签名间隔 D_t = min‖s_f−s_g‖/(2σ) 足够大，误隔离率指数下降。**可隔离性取代了 A72 的参数可辨识性，且是可在线检验的**。∎

**命题 2（CUSUM 检测延迟与误报，近似）** 设故障后残差均值由 0 变为 μ_f，方差 σ²。取参考值 ν = μ_f/2，KL 散度 K_f = μ_f²/(2σ²)。CUSUM 阈值 h 的经典 Wald/Lorden 近似给出 E_f[t_d − t_0] ≤ (h + O(1))/K_f，且无故障平均运行长度 ARL_0 ≥ e^{h}（量级）。因此检测延迟与误报可通过 h 显式权衡，并写入证书的检测时限字段。∎

**定理 1（物理安全与诊断解耦）** 假设：(i) 低层硬件对 τ、F_c、v、d_h 等实施不可绕过的包络裁剪，故任意部署 K_t ∈ 𝒞_hw；(ii) PSI 屏障 h_int 在扰动界 w_bound、测量延迟 τ_d 与未建模故障幅值 ‖θ_f‖≤δ_u 下满足 ḣ_int ≥ −α h_int + w_bound；(iii) 初始 z_0 ∈ 𝒮_int = {z : h_int(z) ≥ 0}。则对任意诊断输出（包括完全错误的 f̂、错误的 A_t、甚至诊断线程死亡），闭环状态满足 z_t ∈ 𝒮_int, ∀t≥0。证明：标准 CBF 前向不变性；诊断只影响 K_t 的选择，但 K_t 始终被投影到 𝒞_hw，且 PSI/硬件层在 K_t 之后、执行器之前独立校验；诊断不在物理安全的证明链中。∎

**定理 2（任务安全的诊断条件）** 若真故障 f* ∈ A_t 对所有 t 成立，且 K_t ∈ 𝒞_safe(A_t)，则由定义 192，K_t ∈ 𝒞_safe(f*)，故在 f* 与 θ_{f*}∈Θ_{f*} 下任务约束与 PSI 均成立。若因误隔离使 f* ∉ A_t，则 K_t 可能落在 𝒞_safe(f*) 之外，任务安全不再有保证；但定理 1 的物理安全仍成立。**两层安全的依赖关系被显式分离：诊断错了，任务可能失败，但人不会受伤、硬件不会越界。** ∎

**命题 3（开集兜底）** 若 ν_t > τ_os，则 A_t ∋ unknown，由定义 192，𝒞_safe(A_t)=𝒞_0。由 𝒞_0 的定义，它在所有声明故障（含有界未建模故障）下任务安全且满足 PSI。因此开集拒识把「可能误隔离」转化为「保守但双层安全」。代价是性能下降，收益是避免「自信地错」。∎

**命题 4（主动诊断的安全性与近似最优）** 探针 u 只从 C0.admits(u) 的库中选，且风险/交互预算受限，因此执行探针后状态仍在 𝒞_0 ⊆ 𝒮_int，PSI 不被破坏。若故障假设上的互信息函数 I(ℱ; r|u,b) 在探针集合上近似次模（自适应 submodular），则基数约束下的贪心选择达到 (1−1/e) 近似；ADX 用贪心/UCB 实现，复杂度 O(|𝒰_adx|·|A|)。∎

**命题 5（人证据的可信度封顶）** 单次询问的 LLR 被截断到 [−L_max, L_max]，故单次回答对后验对数比的改变有界：|log(b_{t+1}(f)/b_{t+1}(g)) − log(b_t(f)/b_t(g))| ≤ 2L_max。再要求 physical_residual_corroborates：若残差似然强烈反对人证据给出的假设，则不更新。因此单次错误/对抗性回答不能把隔离结论从 f 翻到 g（除非物理残差同向），人的影响是「有界证据」而非「安全前提」。∎

**命题 6（检测-隔离-恢复时间链）** 从故障发生到进入安全模式的时间 T_react = t_d + t_iso + t_mode，其中 t_d 由 CUSUM 界（命题 2）控制，t_iso 由 DGM/ADX/SafeAsk 决定，t_mode 为一次模式转移。若 T_react ≤ T_react^max，则在故障演化为不可恢复前进入 DEGRADED/SAFE_HOLD。证书 J_fides 记录 T_react 的实测/上界；若超时，降级为 HANDOVER/硬件急停。∎

**实时性** 实时路径只包含：SRD 残差（一次矩阵乘）、PSI 低维 min/max、硬件裁剪、派发；均为 O(1)~O(q·d)，无梯度、无优化、无学习写。CUSUM 也可放在实时路径（O(q)），但 TFI/OSM/ADX/SafeAsk/FTR 全在语义流。保持 ROSE 的 ≤1ms 契约（A75）。∎

## 5. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| SRD 残差 | O(q·d_y)（实时） | O(q·d_y) | 对 d 解耦；扰动泄漏受 ‖P E_d‖ 界控制 |
| CUSUM | O(q)（实时） | O(q) | 命题 2：延迟-误报权衡 |
| TFI | O(\|ℱ_known\|·q)（语义流） | O(\|ℱ_known\|·q) | 命题 1：误隔离指数界 |
| OSM | O(q²) 投影（可预计算） | O(q²) | 命题 3：未知 ⇒ 退回 𝒞_0 |
| DGM | O(\|A\|²) | O(\|A\|) | D_t 显式写入证书 |
| FSC | O(\|A\|·n_c) | O(n_c) | 定理 2：f*∈A ⇒ 任务安全；unknown ⇒ 𝒞_0 |
| PSI | O(1)（实时） | O(1) | 定理 1：物理安全与诊断解耦 |
| ADX | O(\|𝒰_adx\|·\|A\|)（语义流） | O(\|A\|) | 命题 4：(1−1/e) + 探测安全 |
| SafeAsk | O(\|A\|·\|Q\|) + 一次对话 | O(\|A\|) | 命题 5：单次回答不能翻案 |
| FTR | O(\|A\|) | O(1) | 守卫：只进已认证安全集的模式 |
| FIDES 实时路径 | ≤1ms（继承 ROSE） | — | **零学习写**（A75/A83） |

**正确性定理（FIDES-Complete）** 假设 A61–A76（第 62 轮）及：
- **(A77) 故障覆盖声明**：真实故障 f* ∈ ℱ_known ∪ {f_∅} ∪ ℱ_unmodeled，未建模故障幅值 ‖θ_{f*}‖ ≤ δ_u；`coverage_decl` 显式记录该声明，证书只在声明范围内有效。
- **(A78) 残差可解耦**：存在 P 使 P E_d = 0（或 UIO 的扰动解耦误差有界 ε_d），残差噪声零均值、协方差 σ²I（或已知 Σ），σ 由标定获得。
- **(A79) 硬件包络强制**：𝒞_hw 由低层驱动/嵌入式层实施，任何上层指令（含诊断、RL、对话、被攻陷的语义流）不能绕过；PSI 在扰动界与测量延迟界内是有效 CBF。
- **(A80) 开集可分（显式缺口）**：若 f* 未建模且其残差方向到已知签名子空间的距离 > d_os，则 ν_t > τ_os 以高概率成立；反之若未知故障落在已知签名附近，OSM 无法保证拒识——这是证书必须声明的残余风险。
- **(A81) 人证据有界**：单次询问 LLR 截断 L_max，且隔离翻转需物理残差互证；人可靠性模型 p(y_h|f,q) 在声明区间内。
- **(A82) 探针安全**：ADX 探针库 𝒰_adx 的每个动作执行后仍在 𝒞_0，且风险/交互预算受限。
- **(A83) 实时零学习**：实时路径无在线学习写操作；诊断/学习只在语义流与后台（继承 A75）。

则：
1. **检测与隔离**：报警后，若 f*∈ℱ_known 且签名间隔满足 D_t ≥ γ_d，则 P[正确隔离] ≥ 1 − Σ_{g≠f*} exp(−D_t²/2)（由命题 1 的尺度重写）；若 f*∉ℱ_known 且满足 A80，则 P[OSM 拒识] ≥ 1−β_os，系统进入 unknown/𝒞_0。
2. **物理安全（诊断无关）**：z_t∈𝒮_int, ∀t，即使诊断完全错误、语义流死亡或锚点过期（定理 1）。这是 FIDES 的硬底线。
3. **任务安全（诊断条件）**：若 f*∈A_t 对所有 t 成立，则 K_t∈𝒞_safe(f*)，任务约束与 PSI 同时成立（定理 2）；若误隔离，任务安全可能失败，但物理安全不变（定理 1），且证书必须标记 `coverage_decl` 与置信度。
4. **未知故障优雅降级**：unknown∈A_t ⇒ K_t∈𝒞_0 ⇒ 在 A77 的幅值界内任务+物理安全（命题 3）；超出幅值界则只余硬件包络的物理安全。
5. **容错恢复**：模式转移只进入已认证安全集的模式；RECOVER 需残差清除 + J_fides 复验，避免「带病复出」。
6. **人交互安全**：SafeAsk 只在安全可问态触发；单次人回答不能单独翻案（命题 5）；人是最后否决者，但不是安全链的必要条件。
7. **实时性不变**：实时路径零学习写，≤1ms 与锚点新鲜度契约与 ROSE 一致。

## 6. 实验设计 E211–E220

| 实验 | 设计 | 指标 | 目标 |
|---|---|---|---|
| E211 SRD 解耦 | 注入负载/坡度/人外力扰动 + 四类故障；对比单残差 RSC | 签名间隔 / 扰动泄漏 | ≥4σ / <10%（单残差泄漏 >40%） |
| E212 TFI 分型 | 传感器偏置、执行器增益损失、接触滑移、模型漂移各 100 次 | 隔离准确率 / 幅值误差 | ≥95% / <10% |
| E213 OSM 开集 | 留出 3 类未见故障（如线缆拖拽、关节异响） | 误隔离率 / 未知召回 / 任务失败率 | →0 / ≥90% / 可控 |
| E214 被动核抗误诊 | 人为注入错误 f̂（把 A 故障报成 B），对比 ROSE | 力/接触违规 / 硬件越界 | =0（ROSE >0） |
| E215 DET 权衡 | 扫 CUSUM 阈值与参考值 | 检测延迟 / ARL₀ | <200ms / >10⁴ 步 |
| E216 FSC 性能 | 分型安全集 vs ROSE 单球 vs 纯 𝒞_0 | 任务成功率 / 保守代价 | +15pp / −30% |
| E217 PSI 交互 | 人靠近、意外碰撞、测量延迟 0/10/20ms | 不变量违规 / 误停率 | =0 / ≤5% |
| E218 SafeAsk | 人回答噪声 10%/30%、对抗回答、无回答 | 误隔离增量 / 交互成本 / 恢复时间 | ≤2pp / ≤预算 / −20% |
| E219 ADX 主动诊断 | 传感器偏置 vs 执行器增益损失（被动不可分） | 区分率 / 探测期违规 / 附加磨损 | ≥90% / =0 / ≤阈值 |
| E220 端到端 vs ROSE | 复合故障 + 非平稳 + 人机协作 + 语义流死亡 60s | 违规 / 任务成功率 / 恢复时间 / 实时抖动 | =0 / +20% / −40% / ≤0.2ms |

补充细项：
- E213 必须报告「未知故障靠近已知签名」时的失败案例，不允许只报平均。
- E214 的「误诊注入」应覆盖最坏情况：把最危险故障 f_A^g 误报成最温和故障 f_∅，检验物理层是否仍守住。
- E218 的人因素需 IRB/知情同意；对抗回答模拟「人误判/故意误导」，检验 L_max 与互证机制。
- E220 的语义流死亡测试：杀死诊断/对话线程 60s，实时流只靠 SRD+PSI+硬件裁剪，验证定理 1 的「诊断无关」并非纸面。

## 7. 已知风险

**一句话**：若未建模故障恰好落在已知签名子空间附近（ν_t 低于 τ_os，违反 A80），TFI 会自信地误隔离，A_t 排除真故障，FSC 编译出错误的任务安全集；一旦该故障幅值又超出被动核 𝒞_0 的设计包络 δ_u（违反 A77），定理 1 的物理安全前提也被击穿——「诊断只放宽、不承担安全」的两层设计同时失效，J_fides 变成「有签名、有证书、但错得自信」。

**次级风险与缓解**：
1. **扰动解耦不完美**：P E_d=0 依赖线性化模型，非线性/未建模扰动会泄漏进残差，抬高误报。缓解：滑模/自适应残差观测器 + 在线估计泄漏项；泄漏超过阈值时降低隔离置信度并进 SAFE_HOLD。
2. **签名漂移**：磨损、温变、负载会改变 s_f；签名矩阵需低频重标定。缓解：把签名重标定纳入后台任务，重标定期间扩大 A_t（更保守），并记录签名版本到 J_fides。
3. **被动核过保守**：若 𝒞_0 太小，诊断带来的性能增益消失，系统退化为「永远保守」。缓解：E216 显式量化安全-性能 Pareto；对可证明安全的故障类收缩 𝒞_0 的冗余，但不得削弱物理层。
4. **安全询问延误恢复**：SafeAsk 可能拖慢处理。缓解：设置 T_react^max，超时直接 SAFE_HOLD/HANDOVER；询问只在信息增益足够高时触发。
5. **人的可靠性模型失配**：人可能误判、疲劳、对抗。缓解：L_max 截断 + 物理互证 + 可靠性模型在线校准（仅在非对抗标定集），并对人证据单独审计（ask_log）。
6. **主动诊断的磨损/干扰代价**：探针可能加速磨损或干扰任务。缓解：探针库限制在低幅、低频、短时；风险/交互预算硬约束；E219 记录附加磨损。
7. **多故障并发**：TFI 的单一签名匹配假设一次一个故障；并发故障会让签名叠加、OSM 可能误判为未知。缓解：先按 OSM 拒识退回 𝒞_0，再用组合签名/稀疏分解做离线诊断；证书显式声明「单故障假设」，多故障只承诺物理层安全。
<!-- ARTIFACT:END -->