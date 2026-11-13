--- 产物区 ---
# 第 66 轮产物 · 创新点清单 v1：RAS（Risk-aware Adaptive Closure：情绪驱动的闭环控制；ERG×ACH-RAS×EFS×FRAS×C-RAS×ERS）

> 承接第 65 轮 IP-214~223（VISTA：视觉感知 × 动作分块的故障可归因）。第 65 轮解决了「哪一层坏了」，但未触及「谁要控制、该控制多少」。本轮把「被动故障响应闭环」升级为「主动意图感知闭环」：**用面部表情识别捕获风险态度，用时空推理抑制感知误差，用风险缩放实现控制自适应**。
>
> IP 编号：IP-224~IP-233（共 10 个），全部为 RAS 的核心组件。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 65 轮） |
|---|---|---|---|
| IP-224 | ERG Emotion Recognition Gateway | 新增 | 主动捕获面部表情，用 EMG-风险估计 + 时序滤波输出 `emotion_gate`；`face_unobservable` 时不降极处置 |
| IP-225 | ACH-RAS Action-Chunk Hypothesis-RAS | 升级 ACH | 把块拆为「行为承诺块」+「情绪响应块」；块间加入情绪一致性 |
| IP-226 | EFS Emotion-Fault Synthesis | 新增 | 把情绪当作故障维度，加入 4 类 H_emotion；输出 7×4 联合后验 |
| IP-227 | FRAS Fault Re-Attribution with RAS | 升级 FIR | 在 H_emotion 归因时，**不膨胀几何球，而是调整 λ_risk** |
| IP-228 | FAS Fault Awareness Switch | 新增 | 根据 H_emotion 后验决定是否启动情绪探针；探针从 `null_test` 类推 |
| IP-229 | C-RAS Certified-RAS prefix | 新增 | 认证前缀 k*RAS = min(k_VISTA, k_emotion, m_ras)；满足情绪容差 |
| IP-230 | ERG-ERS Emotion-Response Shaping | 新增 | 控制律 τ_cmd = τ_desired - γ∇R_emotion；闭环塑造情绪-风险共振 |
| IP-231 | AIC-V → AIC-RAS | 升级 AIC | 干扰集扩充 ℰ_emotion，新增共因故障 ℰ_common_emotion |
| IP-232 | J_vista → J_RAS | 整合 | 证书增 λ_risk、fault_emotion_posterior、face_quality、expression_hash |

## 1. 符号体系增量（定义 233–250）

| 符号 | 含义 |
|---|---|
| `RAS = (ERG, ACH-RAS, EFS, FRAS, FAS, C-RAS, ERG, ERS)` | 情绪驱动的闭环控制 |
| `π ∈ Δ^4` | 4 类情绪概率 {neutral, tense, fear, pain} |
| `R_emotion(r, π) = 1 - π(neutral) - 0.3·π(tense) - 0.8·π(fear) - π(pain) + ε` | EMG-风险估计 |
| `d_temporal = KL(π_t || π_{t-T})` | 时空表情一致性 |
| `E = {E0, E1, E2, E3}` | 情绪假设集 |
| `λ_risk = 1 - α_risk·R_emotion - β_risk·H_face` | 风险缩放系数 |
| `m_ras = min(m_VISTA, m_emotion)` | RAS 不可逆视界 |
| `k*RAS` | 情绪认证前缀 |
| `joint_post((H,E))` | 故障-情绪联合后验 |
| `J_RAS = (J_vista, λ_risk, fault_emotion_posterior, face_quality, expression_hash, aic_ras_ver)` | RAS 证书 |

## 2. 形式化定义（完整版）

**定义 233（RAS 总览）** RAS 是 VISTA 的「故障闭环」升级为「意图闭环」：
```
RAS = (ERG, ACH-RAS, EFS, FRAS, FAS, C-RAS, ERG, ERS)
```
不变式：所有情绪观测、故障-情绪联合归因、风险缩放、证书构建只在语义流；实时流只采集面部ROI残差、阶段判定、情绪容差早停，零学习写操作。

**定义 234（面部表情观测量）** 面部检测器 `f_face` 把 RGB 图像映射为 `face = (r ∈ ℝ^{d_r}, l ∈ ℝ^{68×2}, a ∈ ℝ^{512})`。情绪概率 `π_t = f_face(face_t)`，输出 `π ∈ Δ^4`。

**定义 235（EMG-风险估计）** 风险函数
```
R_emotion(r, π) = 1 - π(neutral) - 0.3·π(tense) - 0.8·π(fear) - π(pain) + ε
```

**定义 236（时空表情一致性）** 跨帧 KL 散度
```
d_temporal(t) = KL(π_t || π_{t-T})
```
若 `d_temporal > τ_temporal`，标记 `face_temporal_unstable = True`。

**定义 237（故障-情绪联合假设）** 联合假设集合
```
ℋ_RAS = ℋ × E, 其中 E = {E0 正常, E1 延迟, E2 隐蔽, E3 误判}
```
联合后验：
```
P(H, E | ρ, face) ∝ p(ρ | H) · p(face | E) · P(H) · P(E | H)
```

**定义 238（情绪引导的风险缩放）** 控制缩放因子：
```
λ_risk(t) = 1 - α_risk·R_emotion(t) - β_risk·H_face(t)
```

**定义 239（C-RAS 认证前缀）** 认证前缀 k*RAS 需满足：
1. `∀s≤k: λ_risk(s)·ρ_safe(s) ≥ 0`；
2. 跨模态一致性：`KL(π_{t-s:t} || π_pred) < τ_consistency`；
3. `k*RAS ≤ m_ras`。

**定义 240（ERS 情绪响应塑造）** 控制律：
```
τ_cmd = τ_desired - γ·∇_{τ} R_emotion(π(τ))
```

**定义 241（ERG Emotion Recognition Gateway）** ERG 由面部检测、EMG-风险估计、时序滤波器构成。若 `face_unobservable`，ERG 输出 `HIGH_RISK` 但不降极处置。

**定义 242（FAS Fault Awareness Switch）** FAS 根据 `P(H_emotion | post) ≥ τ_fas` 决定是否激活情绪探针。

**定义 243（AIC-RAS 干扰与共因）**
```
ℰ_RAS = ℰ_V × ℰ_emotion × ℰ_temporal × ℰ_common_emotion
```
其中 ℰ_common_emotion 捕获「几何误差 → 面部表情紧张」的因果链。

**定义 244（J_RAS 证书）**
```
J_RAS = (J_vista, λ_risk, fault_emotion_posterior, face_quality, expression_hash, aic_ras_ver)
```
Valid ⇔ Valid(J_vista) ∧ λ_risk ≥ 0.6 ∧ face_quality ≥ 0.8 ∨ (H_emotion = E0)。

## 3. 关键算法伪代码

```python
# IP-224 ERG
class EmotionRecognitionGateway:
    def recognize(self, face_img, prev_pi=None):
        region = extract_face_region(face_img)
        landmarks = detect_landmarks(region)
        appearance = encode_appearance(region)
        face = (region, landmarks, appearance)
        pi = emotion_classifier(face)      # ∈ Δ^4
        R = 1 - pi[0] - 0.3*pi[1] - 0.8*pi[2] - pi[3]
        temporal_unstable = (prev_pi and kl_div(pi, prev_pi) > 0.5)
        gate = 'HIGH_RISK' if R > 0.4 or not landmarks else 'SAFE'
        return {'pi': pi, 'risk': R, 'gate': gate,
                'unobservable': landmarks is None,
                'temporal_unstable': temporal_unstable}


# IP-226 EFS
class EmotionFaultSynthesis:
    def synthesize(self, rho, face_gate):
        post_H = self.fir.attribute(rho)
        post_E = {e: 1.0 for e in ['E0', 'E1', 'E2', 'E3']}
        if face_gate['unobservable']:
            post_E = {'E0': 0.05, 'E1': 0.7, 'E2': 0.2, 'E3': 0.05}
        joint = {}
        for (h, e), p in product(post_H.keys(), post_E.items()):
            joint[(h, e[0])] = p[0] * p[1]
        return normalize(joint)

    def risk_scale(self, joint):
        λ = 1.0
        for (h, e), p in joint.items():
            if e == 'E1': λ *= (1 - 0.3*p)
            elif e == 'E2': λ *= (1 + 0.2*p)
            elif e == 'E3': λ *= (1 - 0.5*p)
        return max(0.5, min(1.2, λ))


# IP-229 C-RAS
class ChunkSafetyCertificateRAS(ChunkSafetyCertificate):
    def certified_prefix_ras(self, A, joint_post, m_ras, alpha_chunk):
        top_pairs = sorted(joint_post.items(), key=lambda x: x[1], reverse=True)[:3]
        k_best = 0
        for k in range(1, min(len(A), m_ras) + 1):
            ok = True
            for (h, e), p in top_pairs:
                if not self._safety_with_risk(A[s], h, e, p):
                    ok = False; break
            if ok: k_best = k
            else: break
        return k_best


# IP-230 ERS
def emotion_response_shaping(tau_cmd, joint_post, gamma=0.1):
    grad_R = compute_risk_gradient(joint_post)  # ∇_τ R_emotion
    return tau_cmd - gamma * grad_R


# IP-232 RAS闭环
def RAS_round(M, obs):
    V, T, P, L, P_cloud, W_meas, tactile, img, depth, flow = obs
    M.lsf.update_geometry(P_cloud)
    x_prime = M.lsf.fuse(M.usr.fuse(V, T, P, L))
    y_vis = M.f_vis(img, depth, flow)

    face_gate = M.er.recognize(img)
    A = M.vista.ach.propose(x_prime, H=M.vista.H)
    rho = M.vista.fir.signature(M.vista.stage.split(M.vista.residual_log))
    joint_post, _ = M.efs.synthesize(rho, face_gate)

    m_ras = min(M.vista.m, M.er.max_m_emotion)
    k_ras = M.csc_ras.certified_prefix_ras(A, joint_post, m_ras, M.alpha_chunk)
    λ_risk = M.efs.risk_scale(joint_post)

    tau_cmd = M.vista.pi_sigma.prefix_dispatch(A[:k_ras])
    tau_cmd = tau_cmd * λ_risk
    tau_cmd = emotion_response_shaping(tau_cmd, joint_post)

    return k_ras, λ_risk, joint_post, face_gate
```

## 4. 推导

**引理 9（情绪风险缩放收敛）** λ_risk(t) = ∏_t (1 - α_risk·R_emotion)。若情绪稳定，λ_risk 收敛到 λ_∞ ∈ [0.5, 1.2]。

**引理 10（时空一致性抑制误判）** d_temporal > τ_temporal → H_face_delay 可将联合误判概率降至 ε_e·exp(-γ_temporal·τ_temporal)。

**定理 9（RAS 端到端风险一致性）** 在 A87-A91 下，τ_cmd 满足：
1. `P(|τ_cmd - τ*| > ε) ≤ α_chunk + δ_fi + α_emotion`；
2. λ_risk ≥ 0.6 ⇔ 实际执行风险 ≤ 设定上限 × 1.2；
3. `face_unobservable ⇒ λ_risk ≥ 0.8`。

**定理 10（联合可分离性）** S_RAS = diag(S_H, S_E)，κ_fi_RAS = min(κ_fi, κ_ri)。

## 5. 实验设计 E241–E250

| 实验 | 关键问题 | 目标 |
|---|---|---|
| E241 ERG情绪精度 | 遮挡/光照下 R 的可靠性 | R MAE < 0.15，误判 < 5% |
| E242 EFS联合归因 | H_emotion 分离 | 7 类准确率 ≥ 85% |
| E243 时空一致性 | 误判抑制 | τ_temporal 取 0.5 时误判降 70% |
| E244 λ_risk 缩放 | 高风险下容差收紧 | λ_risk ≥ 0.6 时违规率 ≤ 1% |
| E245 C-RAS前缀 | k_ras 保守性 | k_ras ≥ k_vista·0.9，违规 = 0 |
| E246 ERG-FAS | 主动探针 | 次数 −40%，后验集中度 ↑ 30% |
| E247 端到端RAS | 复杂情绪干扰 | 成功率不降、误降级 −40% |
| E248 共因故障 | 几何→情绪链 | 正确判 H_geo+E1 |
| E249 实时性 | 面部ROI 是否卡顿 | <2ms |
| E250 鲁棒性 | 30s 连续遮挡 | λ_risk ≥ 0.8，归因不受影响 |

## 6. 本轮最大风险

**一句话**：RAS 将「情绪」当作可观测的故障维度来建模，但实际场景中「情绪」常被面部遮挡、光照欺骗或刻意设计（假笑、僵硬表情），导致情绪观测噪声甚至恶意攻击——此时 RAS 会把「真实的几何故障」误判为「情绪安全」，从而**过度放宽容差**，把原本可被VISTA 降级的故障，变成更严重的「误判放行」——这是该轮所有理论依赖的核心假设：**情绪是故障-安全的可靠信号，且其观测噪声可被时空一致性约束所抑制**。