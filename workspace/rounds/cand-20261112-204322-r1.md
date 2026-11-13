# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。
<!-- IDEA:START -->
# 第 62 轮（承接第 61 轮「具身语义进化闭环」ESEC IP-173~182；灵感循环第 1 轮；本轮灵感：「语音交互」×「文化适应性」）

> 第 61 轮把场景、意图、阻抗、证据统一进 USR，并用 MEL 提供零样本物理先验、用 DMS 做多轮对话、用 SRT-Dual 解耦语义流与实时流。但**它默认了两个不该默认的东西**：
> 1. **「语言 = 文本」的降维**：MEL/DMS 中的语言输入 L 被当作字符串。真实语音里，「轻一点」用上扬的试探语调说、用急促的高音量喊、还是停顿后小声补一句，**对应完全不同的力/速度/安全裕度**。ASR 置信度、部分假设（partial hypothesis）、打断（barge-in）、韵律（prosody）与情绪，全被丢掉了。
> 2. **「意图→物理约束」被假设为文化无关**：USR 的 `intent_emb` 是「文化无标」的。同一句「靠近一点」，在低接触文化中合适的距离/力度，与高接触文化中合适的值不同；「轻」是一个**相对于文化规范**的形容词。第 61 轮的 CAS（可容许集）只有物理安全边界，没有社会规范边界。
> 3. **对话策略只有一种语用规范**：DMS 的澄清/协商默认「直接、低语境、低权力距离」。在高语境/面子敏感语境中，反复 yes/no 澄清会造成失礼，用户会用间接暗示而非明说「不」。
> 4. **语音流与实时安全环脱节**：ERTC 只消费语义锚点，没有「喊停/打断」的高优先级旁路；语音的 50–300ms 时延与 1ms 控制环相差 2 个数量级，**急停不能等 ASR 出最终文本**。

## 0. 直觉与动机

**灵感 1（语音交互 → 韵律-语用副语言编码器 PVSE）**
直觉：语音不只是「说了什么」，还携带「有多急、多确定、多委婉、多生气」。同一个词法意图，配上不同韵律，应映射到不同的约束修正量：高唤醒+高音高斜率+短停顿 ⇒ 紧急/停止；低能量+拖长音+填充词（「嗯……那个……」）⇒ 犹豫/不确定，应主动澄清而非贸然执行。**关键洞见：把语音当作一条独立于文本的安全信道**——即使 ASR 把「停」听成「听」，短促高能量的爆破音也应触发减速；反之，ASR 高置信文本也不能在用户明显恐慌的语调下继续执行。

**灵感 2（文化适应性 → 文化语用隐变量 CPL）**
直觉：文化不是贴在用户身上的标签，而是**一组隐式的「物理-社会先验」**：多远的距离算冒犯、多大的力算粗暴、多频繁的解释算啰嗦、拒绝要不要留面子、左右手/头部能否触碰。把这些先验写成连续的隐变量 c（直接性、权力距离、接触许可、近距舒适、不确定性回避、面子取向、时间节奏……）与一组**硬禁忌标签** H_hard（饮食、宗教洁净、性别互动、用手禁忌等）。关键洞见：**软维度可推断、可协商；硬禁忌只能显式声明并硬约束，绝不由模型「猜」**。

**灵感 3（两灵感合流 → 文化可容许集 CAS）**
直觉：既然文化最终要落到「力多大、离多远、碰哪里、说多快」，就把它翻译成阻抗/运动约束上的**社会阻抗（social impedance）**：`K_culture = K_safe ∩ H_hard`，并在软规范上加入社会代价 `J_social`。例如高接触许可文化允许更近的接近距离与更小的阻尼（更「跟手」），低接触文化则自动增大最小距离、提高阻尼、降低接近速度。**物理安全是硬约束，文化规范是软约束 + 少数硬禁忌**，两者分层，绝不混淆。

**灵感 4（分层个人化 → 文化是群体先验，个人是后验 HCP）**
直觉：把「文化」直接当策略会滑向刻板印象。正确姿势是**分层贝叶斯**：群体文化先验 p(c) → 个人偏好 θ_i ~ p(θ_i|c)；机器人维护联合信念 b(c, θ_i)，只在证据足够时更新，且对 c 的偏移设 KL 上限。这样既能在冷启动时用文化先验少犯错，又不会把「你是某国人所以你一定……」写死。**关键洞见：可证伪、可纠正、可退出——用户一句话就能推翻文化先验。**

**灵感 5（语音打断 → 实时安全门 VIG）**
直觉：人说话会重叠、会打断、会中途改口。需要一个**优先级状态机**：`alarm > stop > barge_in > 语义更新`。急停与「等一下」走独立旁路，直接进入实时流，不经过 MEL/ASR 最终文本；部分假设只能「软暂停」，不能授权不可逆动作。实时流保证：从检测到急停事件到进入柔顺停止 ≤ 150ms。

**灵感 6（文化感知对话 + 预算 → CDM × PCE++++++）**
直觉：澄清也是一种文化行为。高语境文化下应「给选项、留余地、少逼问」，低语境文化下可显式确认。文化探索（试探距离/力度）会消耗交互预算，必须纳入认知预算：`B_culture` 限制探测次数与信念更新频率，`B_voice` 限制 ASR/TTS/部分假设计算量；预算耗尽时退回群体先验并主动询问，而非偷偷试错。

## 1. 形式化定义（增量：定义 173–184）

**定义 173（韵律-语用语音编码器 PVSE）** PVSE = (Enc_txt, Enc_pros, Fuse_v, Head_prag, Head_unc, D_alarm)。对时刻 t 的流式音频 A_{1:t}：
- **文本假设**：ASR 输出格 L_t = {(w^(k), p_t^(k))}，含部分假设与置信度；`U_asr = H(p_t)`
- **韵律特征**：ψ_t = (F0_mean, F0_slope, energy, speech_rate, pause_ratio, jitter, shimmer, HNR, voiced_ratio) ∈ ℝ^{d_ψ}
- **语用状态**：g_t = (urgency, certainty, valence, arousal, hesitation, politeness, dominance) ∈ [0,1]^7，由 `Head_prag(Enc_pros(ψ_t), Enc_txt(L_t))` 预测
- **语音嵌入**：v_t = Fuse_v(Enc_pros(ψ_t), Enc_txt(L_t)) ∈ ℝ^{d_us}
- **意图融合**：`intent_emb_t = E_intent(L_t, H_diag) ⊕ W_v·[v_t; g_t]`
- **急停告警分**：`a_t = σ(f_alarm(ψ_t, w_t))`，`a_t > τ_alarm ⇒ alarm`（与 ASR 文本解耦）
- **约束修正**：`ΔK_p = -κ_u·urgency - κ_c·certainty`、`Δv_max = -κ_a·arousal`，作为 CAS 的社会先验输入而非直接控制量

**定义 174（文化语用先验 CPL）** C = (D_soft, H_hard, p_0, T_c, d_c)。其中：
- **软维度**：c_soft ∈ [0,1]^{d_c}，含 (directness, power_distance, touch_permissiveness, proxemic_comfort, uncertainty_avoidance, face_orientation, time_pacing, formality)
- **硬禁忌**：H_hard ⊆ 𝒯（dietary, religious_purity, gender_interaction, hand_use, head_touch, …），**只能由用户显式声明或权威配置注入，不参与统计推断**
- **群体先验**：p_0(c_soft)；**文化信念**：b_t(c) ∈ Δ(C)
- **证据**：e_t ∈ {自述, 语言/地区, 敬语/称呼, 韵律, 用户对距离的调整, 退缩/皱眉, 语气转冷, 显式纠正}
- **更新**：`b_{t+1}(c) ∝ p(e_t | c) · b_t(c)`（贝叶斯滤波），硬标签以确定性掩码方式覆盖采样

**定义 175（分层文化个人化 HCP）** 个人偏好 θ_i（如偏好距离、偏好解释频率）满足生成模型 `θ_i ~ N(μ(c), Σ(c))`。机器人维护联合信念 `b_t(c, θ_i)`，预测时边缘化：
```
p(θ_i | h_{1:t}) = ∫ p(θ_i | c) · b_t(c) dc
```
- **反刻板约束**：`KL(b_t(c) || b_0(c)) ≤ κ_kl`，除非累计 ≥ n_min 条**独立**证据；每类证据至多计一次，防止回声室
- **可纠正性**：用户显式纠正 e_correct 以似然 `p(e_correct|c) ∝ exp(-‖c - c_user‖²/2σ_c²)` 直接拉回，并把该用户置于「个体模式」优先

**定义 176（文化可容许集 CAS）** 对给定文化信念 b_t 与交互区域 r：
```
K_culture(b_t) = { K ∈ K_safe : H_hard(K, r) = true ∧ J_social(K, r; b_t) ≤ δ_social }
J_social = λ_prox·max(0, d_min(b_t) - d)² + λ_F·max(0, F_max(b_t, r) - F)²
         + λ_touch·𝕀[r ∉ allowed_regions(b_t)] + λ_speed·max(0, v - v_max(b_t))²
d_min(b_t) = d_0 + w_prox·E_{b_t}[c_prox]
F_max(b_t, r) = F_0(r) · (1 - w_F·(1 - E_{b_t}[c_touch]))
```
- **社会阻抗**：`K_p^c = K_p·(1 - γ_p·E[c_touch])`、`K_d^c = K_d·(1 + γ_d·(1 - E[c_touch]))`
- **分层**：H_hard 为硬约束（违反 ⇒ 证书无效）；软规范只进入目标函数，**绝不放宽 ERTC 物理安全边界**

**定义 177（语音打断与急停门 VIG）** VIG = (Σ_v, E_v, π_prio, Δ_stop)。其中：
- **事件**：E_v = {partial(w,p,τ), endpoint(w,p), barge_in, alarm(a), user_stop}
- **优先级**：π_prio: alarm ≻ stop ≻ barge_in ≻ semantic_update；语义流不可抢占前两者
- **状态机**：Σ_v = {listening, speaking, executing, yielded, stopped}
- **截止期**：τ_stop ≤ 150ms（急停 → 柔顺/卸载），τ_yield ≤ 300ms（说话权让渡），τ_endpoint ≤ 700ms
- **提交规则**：不可逆动作仅在 `endpoint ∧ p > θ_commit ∧ ¬alarm ∧ 未过期` 时提交；partial 假设仅可触发「软暂停/降速」
- **语音锚点**：VoiceAnchor = (token ∈ {STOP, SLOW, SOFTER, WAIT, RESUME}, priority, ts, ttl, speaker_id)，以 CAS 写入，实时流非阻塞读取

**定义 178（文化感知对话管理 CDM）** 扩展第 61 轮 DMS：
- **状态**：S = (H_diag, b_intent, C_exec, C_pending, U_mel, b_culture, b_pref, lang_id, turn_id)
- **动作**：A⁺ = A ∪ {explain, apologize, offer_options, defer, switch_language, use_hint}
- **策略条件**：澄清阈值 `θ_clar(b_culture)` 随 E[c_direct] 升高而升高（高语境 ⇒ 少直问、多给选项）；面子代价 `face_threat(a, b_culture)` 进入策略
- **奖励**：`R = 𝕀[complete] - λ_cog·load - λ_safe·risk - λ_lat·latency - λ_face·face_threat - λ_norm·norm_violation - λ_over·over_adaptation`
- **安全优先例外**：涉及安全/急停的语句必须**显式、直白、无歧义**，不受礼貌/面子约束（safety over face）

**定义 179（八维认知-语音-文化预算 PCE++++++）** `B_cog8 = (B_scene, B_intent, B_ros, B_exec, B_mel, B_usr, B_voice, B_culture)`。其中：
- **B_voice** = (ASR_chunk_ms, ASR_beam, TTS_latency_ms, partial_count, alarm_ops, endpoint_ms)
- **B_culture** = (probe_budget, belief_updates, norm_checks, adaptation_iters, entropy_target)
- **成本**：
```
cost_cog8 = cost_cog5
          + λ_v·(ASR_latency/τ_asr + partial_count/Partial_max + TTS_latency/τ_tts)
          + λ_c·(adapt_iters/Max_adapt + norm_checks/Max_norm)
```
- **降级**：语音 full ASR → 关键词+韵律告警 → **仅急停词**；文化 主动适应 → 群体先验 → 主动询问/弃权。**安全通道永不降级**
- **文化探测 VOI**：仅当 `voi_cog8(probe) > 0` 且非安全关键时允许试探

**定义 180（文化规范对账 CNR）** 升级第 61 轮 XMC+++：
- **期望社会信号**：`ŝ = (d_min, F_max, expected_latency, expected_politeness) = f(b_culture, task)`
- **观测社会信号**：`s = (用户后退距离, 退缩/护住, 语气转冷, 要求重复, 主动缩短距离)`，由视觉/触觉/语音联合估计
- **规范分歧**：`D_social = Σ_i w_i·d_i(ŝ_i, s_i)`，`C_culture = exp(-D_social/σ_s)`
- **触发**：`D_social > τ_norm` ⇒ 文化信念更新 + 解释/道歉 + CAS 保守扩展；用「同文化反事实」区分任务失败与规范失败（同一动作在本文化是否也会失败）

**定义 181（文化-语音-具身闭环 CVEC）** 在第 61 轮 SRT-Dual 上增加第三条语音流：
```
VoiceStream (20–50ms chunk):
  L_t, ψ_t, g_t, a_t ← PVSE(A_{1:t})
  event ← VIG.alarm_or_barge_in(a_t, onset, ASR_stability)
  VoiceAnchor ← {STOP/SLOW/SOFTER/WAIT, priority, ttl}
  b_culture ← CPL.update(e_t);  b_pref ← HCP.marginalize(b_culture)
SemanticStream (10–100Hz):
  intent_emb ← E_intent(L_t, H_diag) ⊕ W_v·[v_t; g_t]
  MEL.infer(V,T,P,L_t) → φ_phys, z_scene, U
  CDM.step(b_culture, b_pref, U, EV_exec) → a_diag
  USR.commit(anchor with culture belief hash, priority)
RealtimeStream (1–10kHz):
  if VoiceAnchor.priority ≥ STOP: enter_stopped_within(τ_stop)   # 旁路 MEL
  K_culture ← CAS(b_culture, r) ∩ Π_ctx(anchor)
  K_safe ← EEIS.compile(K_culture, φ_phys, U)
  ERTC.dispatch(K_safe);  EV_exec ← build_evidence()
  CNR.update(EV_exec, social_obs);  CAJ ← build_certificate(...)
```
三流通过「优先级继承」同步：语音锚点的 STOP 会临时提升为实时流的最高优先级，语义锚点的版本号保证无撕裂读。

**定义 182（文化-语音联合证书 CAJ）** 扩展第 61 轮 J_sem_exec：
```
J_caj = (J_sem_exec,
         culture_belief_hash, H_entropy, hard_tag_compliance, norm_margin,
         voice_uncertainty_U_asr, alarm_pending, prosody_urgency,
         consent_flag, lang_id, explain_hash, policy_hash)
Valid(J_caj) ⇔ Valid(J_sem_exec)
             ∧ H_hard satisfied
             ∧ norm_margin ≥ 0
             ∧ ¬alarm_pending
             ∧ (¬high_contact_action ∨ consent_flag)
             ∧ (H_entropy ≤ τ_H ∨ human_confirmed)
```
- **可争议性**：用户纠正写入 `culture_belief_hash` 的审计链，证书可回放、可申诉
- **不可抵赖**：策略哈希 + 解释哈希保证「机器人为何这样靠近/用力」可追溯

## 2. 关键算法伪代码

### IP-183 PVSE（韵律-语用语音编码器）

```python
class ProsodicVoiceSemanticEncoder:
    def __init__(self, d_us=256, d_psi=9, tau_alarm=0.85):
        self.txt = TextEncoder(d_us)
        self.pros = ProsodyEncoder(d_psi, 128)
        self.fuse = VoiceFusion(d_us, 128)
        self.prag = PragmaticHead(d_in=384, d_out=7)      # urgency..dominance
        self.unc = ASRUncertaintyHead()
        self.alarm = AlarmDetector(d_in=d_psi + 32)       # 独立于文本
        self.tau_alarm = tau_alarm

    def encode(self, audio_chunk, lattice, history_emb):
        w_probs = [p for _, p in lattice.hypotheses]
        u_asr = entropy(w_probs)
        psi = extract_prosody(audio_chunk)                 # F0/energy/rate/pause...
        v_emb = self.fuse(self.pros(psi), self.txt(lattice.top()))
        g = sigmoid(self.prag(torch.cat([self.pros(psi), self.txt(lattice.top())])))
        a = self.alarm(torch.cat([psi, spectral_context(audio_chunk)]))
        return VoiceState(v_emb=v_emb, g=g, u_asr=u_asr,
                          alarm=float(a), alarm_flag=(a > self.tau_alarm),
                          urgency=g[0], certainty=g[1])

    def constraint_modifier(self, vs):
        # 只产生「先验修正」，不直接下发控制
        dKp = -0.3 * vs.urgency - 0.2 * (1 - vs.certainty)
        dv  = -0.5 * vs.g[3]                                # arousal 降速
        return {'dKp': dKp, 'dv_max': dv, 'need_clarify': vs.g[4] > 0.6}
```

### IP-184/185 CPL + HCP（文化信念与分层个人化）

```python
class CulturalPragmaticLatent:
    SOFT_DIMS = ['directness','power_distance','touch_permissiveness',
                 'proxemic_comfort','uncertainty_avoidance','face_orientation',
                 'time_pacing','formality']
    def __init__(self, prior_path, n_particles=512):
        self.p0 = load_population_prior(prior_path)
        self.particles = sample(self.p0, n_particles)
        self.hard_tags = set()          # 只能显式注入

    def update(self, evidence):
        # 硬标签确定性覆盖，不参与推断
        if evidence.kind == 'declaration':
            self.hard_tags |= evidence.hard_tags
        self.particles = bayes_reweight(self.particles, evidence, self.hard_tags)
        self.particles = resample(self.particles)
        return self.belief()

    def belief(self):
        return ParticleBelief(self.particles, hard_tags=self.hard_tags)

class HierarchicalCulturalPersonalization:
    def __init__(self, cpl, kappa_kl=0.5, n_min=3):
        self.cpl, self.kappa_kl, self.n_min = cpl, kappa_kl, n_min
        self.independent_evidence = defaultdict(set)

    def marginalize(self):
        # p(theta_i|h) = ∫ p(theta_i|c) b(c) dc
        return mixture([N(mu(c), Sigma(c)) for c in self.cpl.particles],
                       weights=[c.w for c in self.cpl.particles])

    def guard_stereotype(self, b_new, b_old):
        if kl(b_new.soft, b_old.soft) > self.kappa_kl:
            if len(self.independent_evidence) < self.n_min:
                return b_old            # 退回，避免刻板锁定
        return b_new

    def correct(self, c_user, sigma=0.1):
        # 用户显式纠正 → 个体模式优先
        return bayes_reweight(self.cpl.particles, GaussianEvidence(c_user, sigma))
```

### IP-186 CAS（文化可容许集）

```python
class CultureAdmissibleSet:
    def __init__(self, hard_constraints, delta_social=0.2):
        self.hard = hard_constraints          # 不可协商
        self.delta_social = delta_social

    def build(self, b_culture, region):
        e = b_culture.expectation()           # 软维度期望
        d_min = 0.4 + 0.6 * e['proxemic_comfort']
        F_max = self.hard.force_cap(region) * (1 - 0.3 * (1 - e['touch_permissiveness']))
        allowed = self.hard.allowed_regions(e, region)
        v_max = 0.25 * (1 - 0.4 * e['uncertainty_avoidance'])
        return CultureBounds(d_min, F_max, allowed, v_max)

    def project(self, K_safe, bounds):
        if not self.hard.compatible(K_safe, bounds):
            return None                        # 硬禁忌 ⇒ 拒绝，证书无效
        K = K_safe.copy()
        K['K_p'] *= (1 - 0.25 * bounds.touch_factor)
        K['K_d'] *= (1 + 0.25 * (1 - bounds.touch_factor))
        K['F_max'] = min(K['F_max'], bounds.F_max)
        K['d_min'] = bounds.d_min
        K['v_max'] = min(K['v_max'], bounds.v_max)
        return K

    def social_cost(self, trajectory, bounds):
        return (0.5 * max(0, bounds.d_min - trajectory.d_min_actual) ** 2
                + 0.5 * max(0, trajectory.F_peak - bounds.F_max) ** 2
                + 1.0 * int(trajectory.contact_region not in bounds.allowed)
                + 0.2 * max(0, trajectory.v - bounds.v_max) ** 2)
```

### IP-187 VIG（语音打断与急停门）

```python
class VoiceInterruptGate:
    PRIORITY = {'alarm': 3, 'stop': 2, 'barge_in': 1, 'semantic': 0}
    def __init__(self, tau_stop=0.150, tau_yield=0.300):
        self.tau_stop, self.tau_yield = tau_stop, tau_yield
        self.anchor = VoiceAnchor(token='RESUME', priority=0, ts=now(), ttl=0.5)

    def on_event(self, event):
        if event.type == 'alarm' or event.type == 'user_stop':
            self.anchor = VoiceAnchor('STOP', self.PRIORITY['stop'], now(), ttl=1.0)
        elif event.type == 'barge_in':
            self.anchor = VoiceAnchor('WAIT', self.PRIORITY['barge_in'], now(), ttl=0.5)
        elif event.type == 'partial' and event.is_urgency and event.p > 0.8:
            self.anchor = VoiceAnchor('SLOW', self.PRIORITY['barge_in'], now(), ttl=0.3)
        # endpoint 才允许语义提交
        return self.anchor

    def realtime_check(self):
        if self.anchor.expired():
            return None
        if self.anchor.token == 'STOP':
            return 'stop'                      # 旁路 MEL，直接柔顺/卸载
        return 'yield' if self.anchor.token in ('WAIT', 'SLOW') else None
```

### IP-188 CDM（文化感知对话）

```python
class CultureAwareDialogueManager(DialogueManagementSystem):
    def step(self, U_mel, b_culture, b_pref):
        e = b_culture.expectation()
        theta_clar = 0.4 + 0.4 * e['directness']          # 高语境 ⇒ 少直问
        a_rule = self.rule_policy.select(self._encode_state(U_mel), b_culture)
        if a_rule.type == 'ask_clarify' and e['directness'] < 0.4:
            a_rule = DialogueAction('offer_options',       # 间接、留面子
                                    options=self._candidate_options(),
                                    reason='high_context_clarify')
        if self._is_safety(a_rule):
            a_rule = self._make_explicit(a_rule)           # 安全 > 面子
        chat = self._social_ok(a_rule, e)
        return a_rule, self.C_pending, self.b_intent, chat

    def _social_ok(self, a, e):
        face = self._face_threat(a, e['face_orientation'])
        if face > 0.7 and self._is_refusal(a):
            a = DialogueAction('explain', text=self._polite_refusal(e))
        return a
```

### IP-189 PCE++++++（八维预算）

```python
class VoiceCulturalBudget(CognitiveSemanticBudget):
    def __init__(self, voice=None, culture=None, **kw):
        super().__init__(**kw)
        self.B_voice = voice or dict(chunk_ms=40, beam=4, tts_ms=200,
                                     partial_max=8, alarm_ops=3, endpoint_ms=700)
        self.B_culture = culture or dict(probe=5, updates=50, norm_checks=100,
                                         adapt_iters=10, entropy_target=0.5)
        self.voice_mode, self.culture_mode = 'full', 'adapt'

    def voice_degrade(self):
        # full → keyword+prosody → stop-only；安全通道不降级
        self.voice_mode = {'full': 'keyword', 'keyword': 'stop_only',
                           'stop_only': 'stop_only'}[self.voice_mode]

    def culture_degrade(self):
        self.culture_mode = {'adapt': 'population',
                             'population': 'ask', 'ask': 'ask'}[self.culture_mode]

    def voi_cog8(self, action):
        base = self.voi_cog5(action)
        cost = 0.0
        if action.type == 'probe_culture':
            cost = 0.2 * (action.iters / self.B_culture['adapt_iters'])
        elif action.type == 'asr_full':
            cost = 0.2 * (action.latency / (self.B_voice['chunk_ms'] / 1000))
        return base - cost
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| PVSE | O(d_ψ + d_us) ≈ 5–15ms/chunk | O(d_us) | 急停告警召回 ≥ 99%，误报 ≤ 1% |
| CPL | O(N_particles·d_c) ≈ 1–3ms | O(N_particles·d_c) | 文化信念校准 ECE ≤ 0.05；KL 偏移受控 |
| HCP | O(N_particles) 边缘化 | O(N_particles·d_θ) | 个体后验收敛；n_min 证据前不漂移 |
| CAS | O(|K|·d_c) ≈ 0.1ms | O(|K|) | H_hard 零违反；软规范代价有界 |
| VIG | O(1) 事件处理 | O(1) | 急停响应 ≤ 150ms；partial 不授权不可逆动作 |
| CDM | O(1) 每轮 | O(N_turns) | 安全语句显式；任务完成率 ≥ 90% |
| PCE++++++ | O(1) 预算检查 | O(1) | 降级正确；安全通道不降级 |
| CNR | O(d_social) | O(1) | 规范违反检出率 ≥ 90%，误报 ≤ 10% |
| CAJ | O(1) 证书构建 | O(1) | 证书验证通过率 ≥ 99.9%，可回放 |

**正确性定理（CVEC-Complete）**：在 A61–A70 基础上增加：
- **(A71)** PVSE 的韵律急停检测器在背景噪声 ≤ 75dB 下召回 ≥ 0.99、误报 ≤ 0.01；ASR 置信度校准 ECE ≤ 0.05。
- **(A72)** CPL 的证据在给定 c 下条件独立；硬禁忌标签由用户/权威正确注入；文化先验覆盖目标人群。
- **(A73)** HCP 的层次模型良定，且存在 KL 上限使 `b_t(c)` 不会在证据不足时偏离先验。
- **(A74)** CAS 的 H_hard 可在 ≤ 0.1ms 内校验；软社会代价 J_social 关于 K 是 L_social-Lipschitz 的。
- **(A75)** VIG 的急停路径使用独立实时线程，最坏响应时间 ≤ τ_stop = 150ms；语义流不可抢占。
- **(A76)** CDM 的安全语句生成器无条件绕过面子/礼貌约束；规则策略在安全子空间内支配 RL。
- **(A77)** PCE++++++ 各维预算单调消耗；降级路径（voice: full→keyword→stop-only；culture: adapt→population→ask）安全不退化。
- **(A78)** CNR 的社会信号估计器偏差 ≤ δ_social，且能区分任务失败与规范失败。

则：
1. **语音安全优先**：任意 `alarm ∨ user_stop` 事件在 τ_stop 内触发柔顺/停止，即使 ASR 与 MEL 全部失效（A71, A75）。
2. **文化安全分层**：`K_safe ∈ H_hard` 恒成立；软规范违反的期望代价 ≤ δ_social + L_social·ε_proj（A74）。
3. **个人化不刻板**：在独立证据 < n_min 前，`KL(b_t(c)||b_0(c)) ≤ κ_kl`；用户显式纠正后个体后验优先（A73）。
4. **规范失败可证伪**：CNR 在 D_social > τ_norm 时触发纠正，且 CAJ 在 norm_margin < 0 且无同意时判无效（A78）。
5. **实时性**：语音流不阻塞实时流；急停旁路 ≤ 150ms；语义锚点版本号保证无撕裂读（A75）。
6. **预算安全**：B_voice / B_culture 耗尽只降级非安全能力，不放松 H_hard 与 ERTC（A77）。

## 4. 实验设计 E211–E220

| 实验 | 指标 | 目标 |
|---|---|---|
| E211 PVSE | 韵律语用（紧急/确定/犹豫）F1；急停召回/误报；ASR ECE | F1 ≥ 0.85；召回 ≥ 99%，误报 ≤ 1%；ECE ≤ 0.05 |
| E212 CPL | 文化维度预测 MAE；留一文化泛化；ECE | MAE ≤ 0.15；留一文化不劣于 −10%；ECE ≤ 0.05 |
| E213 HCP | 个体偏好预测；刻板漂移 KL；纠正后收敛轮次 | 优于群体先验 ≥ 20%；KL ≤ κ_kl；≤ 2 轮 |
| E214 CAS | 原生评审「距离/力度/接触」得体率；H_hard 违反率 | ≥ 85%；= 0% |
| E215 VIG | 急停响应时延；误打断率；partial 误授权率 | P95 ≤ 150ms；≤ 5%；= 0% |
| E216 CDM | 任务完成率；澄清轮次；面子威胁评分；高语境得体率 | ≥ 90%；≤ 3 轮；−40%；≥ 85% |
| E217 PCE++++++ | B_voice/B_culture 降级正确性；VOI 单调性 | 100%；单调递减 |
| E218 CNR | 规范违反检出率；误报率；纠正成功率 | ≥ 90%；≤ 10%；≥ 85% |
| E219 CAJ | 证书通过率；审计回放完整性；异议处理 | ≥ 99.9%；100%；≤ 1 轮 |
| E220 端到端 | vs 第 61 轮：急停时延、文化得体率、澄清轮次、任务成功率 | −60%；+35%；−30%；+10% |

**消融设计**：
- A1 去掉 PVSE 韵律（仅文本）→ 验证韵律对紧急/犹豫判定的贡献；
- A2 去掉 CPL（单一通用语用）→ 验证文化先验必要性；
- A3 去掉 HCP（直接套用文化标签）→ 验证刻板漂移与个体损失；
- A4 去掉 VIG 旁路（语音走语义流）→ 验证急停时延；
- A5 去掉 CNR（不检测规范失败）→ 验证闭环纠正价值；
- A6 去掉 CAJ（无文化/语音证书）→ 验证可审计性。

**跨文化验证协议**：至少覆盖 4 个文化簇 × 3 种语言/口音 × 2 类接触场景（递物 / 搀扶），采用「本地母语评审 + 双盲视频评分 + 规范违反标注」，并做留一文化簇（leave-one-culture-out）泛化测试，避免只在训练文化上自证。

## 5. 本轮最大风险

**一句话**：若文化隐变量在证据不足时被过度更新、或韵律告警在不同语言/口音/情绪表达习惯下系统性偏移（某些文化本就高音量、快语速、频繁重叠说话），系统就会要么把「正常热情」误判为紧急而频繁急停（保守瘫痪），要么把「真正的恐慌」当作文化常态而错过停车窗口，同时把刻板印象固化成「可审计的偏见」——因此必须以「韵律告警独立于文本 + 硬禁忌显式注入 + KL/证据门控 + CNR 反事实纠偏 + 人类一键否决」构成不可绕过的文化-语音安全护栏，并坚持跨文化留出验证。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 62 轮产物 · 创新点清单 v2：CAVE（文化-语音具身适应闭环：韵律语用×文化先验×分层个人化×社会阻抗×语音急停门，PVSE×CPL×HCP×CAS×VIG×CDM×PCE++++++×CNR×CVEC×CAJ）

> 承接第 61 轮 IP-173~182（ESEC：USR×MEL×DMS×SRT-Dual×PCE+++++）。本轮把第 61 轮被压缩成「文本」的语音重新展开为**副语言安全信道**，把被假设为「文化无标」的意图→约束映射重新展开为**文化可容许集**，并用分层贝叶斯把文化从「标签」降格为「可证伪的群体先验」。实现 **「语音可听、文化可译、约束可分层、急停可旁路、适应可退出」**。

> IP 编号：IP-183~IP-192（共 10 个），新增 6 项核心能力：韵律语用编码、文化先验推断、分层个人化、社会阻抗、语音急停门、文化规范对账。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-183 | PVSE Prosodic Voice-Semantic Encoder | 新增 | 流式 ASR 格 + 韵律特征 + 语用状态 + 独立告警头；意图嵌入接受韵律门控；只产生约束修正先验 |
| IP-184 | CPL Cultural Pragmatic Latent | 新增 | 8 个连续文化维度 + 硬禁忌标签 + 群体先验 + 贝叶斯信念更新 |
| IP-185 | HCP Hierarchical Cultural Personalization | 新增 | 群体先验→个体后验的分层模型；KL/证据门控反刻板；用户纠正即退出 |
| IP-186 | CAS Culture-Admissible Set | 新增 | 把文化翻译成距离/力/接触/速度约束；H_hard 硬约束 + J_social 软代价；社会阻抗 |
| IP-187 | VIG Voice Interrupt Gate | 新增 | alarm≻stop≻barge_in≻semantic 优先级；急停旁路 MEL；partial 不授权不可逆动作 |
| IP-188 | CDM Culture-aware Dialogue Management | 升级 IP-175 | 高语境少直问多给选项；面子代价入奖励；安全语句无条件显式化 |
| IP-189 | PCE++++++ Voice-Cultural Budget | 升级 IP-177 | 八维预算 B_cog8，新增 B_voice/B_culture；安全通道永不降级 |
| IP-190 | CNR Cultural Norm Reconciliation | 升级 IP-180 | 期望/观测社会信号对账 D_social；用同文化反事实区分任务失败与规范失败 |
| IP-191 | CVEC Culture-Voice-Embodied Closure | 升级 IP-182 | 语音流 20–50ms + 语义流 10–100Hz + 实时流 1–10kHz 三流优先级继承闭环 |
| IP-192 | CAJ Culture-Aware Joint Certificate | 升级 IP-181 | 硬禁忌合规、规范裕度、语音不确定度、告警挂起、同意标志、可回放审计 |

## 1. 符号体系增量（定义 173–184）

| 符号 | 含义 |
|---|---|
| `PVSE = (Enc_txt, Enc_pros, Fuse_v, Head_prag, Head_unc, D_alarm)` | 韵律-语用语音编码器 |
| `ψ_t = (F0, F0_slope, energy, rate, pause, jitter, shimmer, HNR, voiced)` | 韵律特征 |
| `g_t = (urgency, certainty, valence, arousal, hesitation, politeness, dominance)` | 语用状态 |
| `U_asr = H(p_t)` | ASR 不确定性（假设分布熵） |
| `a_t = σ(f_alarm(ψ_t, w_t))` | 与文本解耦的急停告警分 |
| `C = (D_soft, H_hard, p_0, T_c, d_c)` | 文化语用先验 |
| `c_soft = (directness, power_distance, touch_permissiveness, proxemic_comfort, uncertainty_avoidance, face_orientation, time_pacing, formality)` | 文化软维度 |
| `H_hard ⊆ 𝒯` | 硬禁忌标签（显式注入，不参与统计推断） |
| `b_t(c) ∈ Δ(C)` | 文化信念 |
| `θ_i ~ N(μ(c), Σ(c))` | 个人偏好生成模型 |
| `b_t(c, θ_i)` | 文化-个人联合信念 |
| `K_culture(b_t) = {K ∈ K_safe : H_hard ∧ J_social ≤ δ_social}` | 文化可容许集 |
| `J_social` | 社会规范代价（距离/力/接触/速度） |
| `d_min, F_max, allowed_regions, v_max` | 文化导出的约束边界 |
| `VIG = (Σ_v, E_v, π_prio, Δ_stop)` | 语音打断与急停门 |
| `VoiceAnchor = (token, priority, ts, ttl, speaker_id)` | 语音锚点 |
| `τ_stop = 150ms, τ_yield = 300ms, τ_endpoint = 700ms` | 语音安全截止期 |
| `CDM` | 文化感知对话管理 |
| `A⁺ = A ∪ {explain, apologize, offer_options, defer, switch_language, use_hint}` | 扩展动作集 |
| `B_cog8 = (B_scene, B_intent, B_ros, B_exec, B_mel, B_usr, B_voice, B_culture)` | 八维认知-语音-文化预算 |
| `B_voice = (chunk_ms, beam, tts_ms, partial_count, alarm_ops, endpoint_ms)` | 语音预算 |
| `B_culture = (probe, updates, norm_checks, adapt_iters, entropy_target)` | 文化预算 |
| `D_social, C_culture = exp(-D_social/σ_s)` | 文化规范分歧与一致性 |
| `CVEC = VoiceStream ∘ SemanticStream ∘ RealtimeStream` | 文化-语音-具身闭环 |
| `J_caj = (J_sem_exec, culture_hash, H_entropy, hard_compliance, norm_margin, U_asr, alarm_pending, urgency, consent, lang_id, explain_hash)` | 文化-语音联合证书 |

## 2. 关键算法伪代码

### IP-183 PVSE（韵律-语用语音编码器）

```python
class ProsodicVoiceSemanticEncoder:
    def __init__(self, d_us=256, d_psi=9, tau_alarm=0.85):
        self.txt = TextEncoder(d_us)
        self.pros = ProsodyEncoder(d_psi, 128)
        self.fuse = VoiceFusion(d_us, 128)
        self.prag = PragmaticHead(d_in=384, d_out=7)
        self.unc = ASRUncertaintyHead()
        self.alarm = AlarmDetector(d_in=d_psi + 32)   # 独立于 ASR 文本
        self.tau_alarm = tau_alarm

    def encode(self, audio_chunk, lattice, history_emb):
        u_asr = entropy([p for _, p in lattice.hypotheses])
        psi = extract_prosody(audio_chunk)
        v_emb = self.fuse(self.pros(psi), self.txt(lattice.top()))
        g = sigmoid(self.prag(torch.cat([self.pros(psi), self.txt(lattice.top())])))
        a = self.alarm(torch.cat([psi, spectral_context(audio_chunk)]))
        return VoiceState(v_emb=v_emb, g=g, u_asr=u_asr,
                          alarm=float(a), alarm_flag=(a > self.tau_alarm))

    def constraint_modifier(self, vs):
        # 只产生「先验修正」，不直接下发控制量
        return {'dKp': -0.3 * vs.g[0] - 0.2 * (1 - vs.g[1]),
                'dv_max': -0.5 * vs.g[3],
                'need_clarify': vs.g[4] > 0.6,
                'certainty': vs.g[1], 'u_asr': vs.u_asr}
```

### IP-184/185 CPL + HCP（文化信念与分层个人化）

```python
class CulturalPragmaticLatent:
    SOFT_DIMS = ['directness', 'power_distance', 'touch_permissiveness',
                 'proxemic_comfort', 'uncertainty_avoidance', 'face_orientation',
                 'time_pacing', 'formality']

    def __init__(self, prior_path, n_particles=512):
        self.p0 = load_population_prior(prior_path)
        self.particles = sample(self.p0, n_particles)
        self.hard_tags = set()                    # 只接受显式注入

    def update(self, evidence):
        if evidence.kind == 'declaration':
            self.hard_tags |= evidence.hard_tags  # 硬禁忌确定性覆盖
        self.particles = resample(bayes_reweight(self.particles, evidence,
                                                 self.hard_tags))
        return self.belief()


class HierarchicalCulturalPersonalization:
    def __init__(self, cpl, kappa_kl=0.5, n_min=3):
        self.cpl, self.kappa_kl, self.n_min = cpl, kappa_kl, n_min
        self.independent_evidence = defaultdict(set)

    def marginalize(self):
        # p(theta_i|h) = ∫ p(theta_i|c) b(c) dc
        return mixture([N(c.mu_theta, c.Sigma_theta) for c in self.cpl.particles],
                       weights=[c.w for c in self.cpl.particles])

    def guard_stereotype(self, b_new, b_old):
        if kl(b_new.soft, b_old.soft) > self.kappa_kl:
            if len(self.independent_evidence) < self.n_min:
                return b_old                      # 证据不足，拒绝漂移
        return b_new

    def correct(self, c_user, sigma=0.1):
        # 用户显式纠正 → 个体模式优先，并记入审计链
        return bayes_reweight(self.cpl.particles,
                              GaussianEvidence(c_user, sigma))
```

### IP-186 CAS（文化可容许集）

```python
class CultureAdmissibleSet:
    def __init__(self, hard_constraints, delta_social=0.2):
        self.hard = hard_constraints              # 不可协商
        self.delta_social = delta_social

    def build(self, b_culture, region):
        e = b_culture.expectation()
        return CultureBounds(
            d_min=0.4 + 0.6 * e['proxemic_comfort'],
            F_max=self.hard.force_cap(region) * (1 - 0.3 * (1 - e['touch_permissiveness'])),
            allowed=self.hard.allowed_regions(e, region),
            v_max=0.25 * (1 - 0.4 * e['uncertainty_avoidance']),
            touch_factor=e['touch_permissiveness'])

    def project(self, K_safe, bounds):
        if not self.hard.compatible(K_safe, bounds):
            return None                            # 硬禁忌 ⇒ 证书无效
        K = K_safe.copy()
        K['K_p'] *= (1 - 0.25 * bounds.touch_factor)
        K['K_d'] *= (1 + 0.25 * (1 - bounds.touch_factor))
        K['F_max'] = min(K['F_max'], bounds.F_max)
        K['d_min'] = bounds.d_min
        K['v_max'] = min(K['v_max'], bounds.v_max)
        return K

    def social_cost(self, tr, bounds):
        return (0.5 * max(0, bounds.d_min - tr.d_min_actual) ** 2
                + 0.5 * max(0, tr.F_peak - bounds.F_max) ** 2
                + 1.0 * int(tr.contact_region not in bounds.allowed)
                + 0.2 * max(0, tr.v - bounds.v_max) ** 2)
```

### IP-187 VIG（语音打断与急停门）

```python
class VoiceInterruptGate:
    PRIORITY = {'alarm': 3, 'stop': 2, 'barge_in': 1, 'semantic': 0}

    def __init__(self, tau_stop=0.150, tau_yield=0.300):
        self.tau_stop, self.tau_yield = tau_stop, tau_yield
        self.anchor = VoiceAnchor('RESUME', 0, now(), ttl=0.5)

    def on_event(self, event):
        if event.type in ('alarm', 'user_stop'):
            self.anchor = VoiceAnchor('STOP', self.PRIORITY['stop'], now(), ttl=1.0)
        elif event.type == 'barge_in':
            self.anchor = VoiceAnchor('WAIT', self.PRIORITY['barge_in'], now(), ttl=0.5)
        elif event.type == 'partial' and event.urgency and event.p > 0.8:
            self.anchor = VoiceAnchor('SLOW', self.PRIORITY['barge_in'], now(), ttl=0.3)
        return self.anchor

    def realtime_check(self):
        if self.anchor.expired():
            return None
        if self.anchor.token == 'STOP':
            return 'stop'                          # 旁路 MEL/ASR 终文本
        return 'yield' if self.anchor.token in ('WAIT', 'SLOW') else None
```

### IP-188 CDM（文化感知对话）

```python
class CultureAwareDialogueManager(DialogueManagementSystem):
    def step(self, U_mel, b_culture, b_pref):
        e = b_culture.expectation()
        a = self.rule_policy.select(self._encode_state(U_mel), b_culture)
        if a.type == 'ask_clarify' and e['directness'] < 0.4:
            a = DialogueAction('offer_options',          # 高语境：给选项、留余地
                               options=self._candidate_options(),
                               reason='high_context_clarify')
        elif a.type == 'ask_clarify':
            a = self._direct_confirm(a)                  # 低语境：显式确认
        if self._is_safety(a):
            a = self._make_explicit(a)                   # 安全 > 面子
        if self._face_threat(a, e['face_orientation']) > 0.7:
            a = DialogueAction('explain', text=self._polite_refusal(e))
        return a, self.C_pending, self.b_intent
```

### IP-189 PCE++++++（八维预算）

```python
class VoiceCulturalBudget(CognitiveSemanticBudget):
    def __init__(self, voice=None, culture=None, **kw):
        super().__init__(**kw)
        self.B_voice = voice or dict(chunk_ms=40, beam=4, tts_ms=200,
                                     partial_max=8, alarm_ops=3, endpoint_ms=700)
        self.B_culture = culture or dict(probe=5, updates=50, norm_checks=100,
                                         adapt_iters=10, entropy_target=0.5)
        self.voice_mode, self.culture_mode = 'full', 'adapt'

    def voice_degrade(self):
        self.voice_mode = {'full': 'keyword', 'keyword': 'stop_only',
                           'stop_only': 'stop_only'}[self.voice_mode]

    def culture_degrade(self):
        self.culture_mode = {'adapt': 'population', 'population': 'ask',
                             'ask': 'ask'}[self.culture_mode]

    def voi_cog8(self, action):
        base = self.voi_cog5(action)
        if action.type == 'probe_culture':
            return base - 0.2 * action.iters / self.B_culture['adapt_iters']
        if action.type == 'asr_full':
            return base - 0.2 * action.latency / (self.B_voice['chunk_ms'] / 1000)
        return base
```

### IP-190 CNR（文化规范对账）

```python
class CulturalNormReconciler:
    def __init__(self, tau_norm=0.6, sigma_s=0.2):
        self.tau_norm, self.sigma_s = tau_norm, sigma_s

    def reconcile(self, expected, observed, counterfactual_task_fail):
        d_social = sum(w * dist(expected[k], observed[k])
                       for k, w in {'d_min': 1.0, 'F_max': 1.0,
                                    'latency': 0.5, 'politeness': 0.5}.items())
        c_culture = exp(-d_social / self.sigma_s)
        if d_social > self.tau_norm and not counterfactual_task_fail:
            return {'violation': True, 'D_social': d_social,
                    'C_culture': c_culture,
                    'update': 'culture_belief', 'action': 'explain_or_apologize'}
        return {'violation': False, 'D_social': d_social, 'C_culture': c_culture}
```

### IP-191 CVEC（三流闭环集成）

```python
def CVEC(M, A_chunk, V, T, P, delta_f_req):
    # ---- 语音流（20–50ms）----
    vs = PVSE.encode(A_chunk, ASR.stream(A_chunk), M.H_diag)
    va = VIG.on_event(make_voice_event(vs))
    e = extract_cultural_evidence(vs, ASR.lattice, social_sensors)
    M.b_culture = CPL.update(e)
    M.b_pref = HCP.marginalize()
    # ---- 语义流（10–100Hz）----
    intent_emb = M.usr.intent_encoder.encode(ASR.top(), M.H_diag) \
                 + W_v @ concat(vs.v_emb, vs.g) * gate(vs)
    M.phi_phys, M.z_scene, M.U = MEL.infer(V, T, P, ASR.top(), M.scene_emb,
                                            M.evidence_emb, vs.v_emb)
    a_diag = CDM.step(M.U, M.b_culture, M.b_pref)
    M.anchor = USR.commit(M.z_scene, intent_emb, M.phi_phys, M.U,
                          culture_hash=hash(M.b_culture))
    # ---- 实时流（1–10kHz，单步示意）----
    if VIG.realtime_check() == 'stop':
        return enter_compliant_stop(deadline=VIG.tau_stop)
    bounds = CAS.build(M.b_culture, region=M.region)
    K_prior = USR.project(M.anchor)
    K_culture = CAS.project(K_prior, bounds)
    if K_culture is None:
        return abstain_and_ask(bounds.conflict)          # 硬禁忌冲突
    K_safe = EEIS.compile(delta_f_req, V, T, P, K_culture, M.phi_phys, M.U)
    dispatch(K_safe)
    EV = wait_contact_and_build_evidence()
    M.evidence_emb = E_evidence(EV)
    cnr = CNR.reconcile(expected=bounds.expected_signal(),
                        observed=estimate_social_signal(EV, social_sensors),
                        counterfactual_task_fail=EV.task_fail)
    if cnr['violation']:
        M.b_culture = CPL.update(evidence_from(cnr))
        action = 'explain_or_apologize'
    M.J_caj = CAJ.build(EV, M, cnr, vs, VIG.anchor, consent=M.consent)
    return M, K_safe, EV, M.J_caj
```

### IP-192 CAJ（文化-语音联合证书）

```python
def build_caj(EV, M, cnr, vs, va, consent):
    valid = (valid_sem_exec(M.J_sem_exec)
             and M.hard_tags.compliant()
             and cnr['norm_margin'] >= 0
             and not va.active_or_alarm
             and (not is_high_contact(EV) or consent)
             and (entropy(M.b_culture) <= TAU_H or M.human_confirmed))
    return CultureAwareCertificate(
        sem_exec=M.J_sem_exec,
        culture_belief_hash=hash(M.b_culture),
        H_entropy=entropy(M.b_culture),
        hard_tag_compliance=M.hard_tags.compliance_vector(),
        norm_margin=cnr['norm_margin'],
        voice_uncertainty=vs.u_asr,
        alarm_pending=va.active_or_alarm,
        prosody_urgency=vs.g[0],
        consent_flag=consent,
        lang_id=M.lang_id,
        explain_hash=hash(M.last_explanation),
        valid=valid)
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| PVSE | O(d_ψ+d_us) ≈ 5–15ms/chunk | O(d_us) | 急停召回 ≥ 99%，误报 ≤ 1% |
| CPL | O(N_p·d_c) ≈ 1–3ms | O(N_p·d_c) | 校准 ECE ≤ 0.05；KL 偏移受控 |
| HCP | O(N_p) 边缘化 | O(N_p·d_θ) | 个体后验收敛；n_min 前不漂移 |
| CAS | O(|K|·d_c) ≈ 0.1ms | O(|K|) | H_hard 零违反；软代价有界 |
| VIG | O(1) | O(1) | 急停响应 ≤ 150ms；partial 不授权不可逆动作 |
| CDM | O(1)/轮 | O(N_turns) | 安全语句显式；完成率 ≥ 90% |
| PCE++++++ | O(1) | O(1) | 降级正确；安全通道不降级 |
| CNR | O(d_social) | O(1) | 规范违反检出 ≥ 90%，误报 ≤ 10% |
| CAJ | O(1) | O(1) | 验证通过率 ≥ 99.9%，可回放 |

**正确性定理（CVEC-Complete）**：在 A61–A70 基础上增加 A71–A78（见想法区）。则：
1. **语音安全优先**：任意 `alarm ∨ user_stop` 在 τ_stop=150ms 内触发柔顺/停止，即使 ASR 与 MEL 失效（A71, A75）。
2. **文化安全分层**：`K_safe ∈ H_hard` 恒成立；软规范期望代价 ≤ δ_social + L_social·ε_proj（A74）。
3. **个人化不刻板**：独立证据 < n_min 前 `KL(b_t(c)||b_0(c)) ≤ κ_kl`；用户纠正后个体后验优先（A73）。
4. **规范失败可证伪**：CNR 检出 D_social > τ_norm；CAJ 在 norm_margin < 0 且无同意时无效（A78）。
5. **实时性**：语音流不阻塞实时流；语义锚点版本号保证无撕裂读（A75）。
6. **预算安全**：B_voice/B_culture 耗尽只降级非安全能力，不放松 H_hard 与 ERTC（A77）。

## 4. 实验设计 E211–E220

| 实验 | 指标 | 目标 |
|---|---|---|
| E211 PVSE | 语用 F1；急停召回/误报；ASR ECE | ≥ 0.85；99%/1%；≤ 0.05 |
| E212 CPL | 文化维度 MAE；留一文化泛化；ECE | ≤ 0.15；≥ −10%；≤ 0.05 |
| E213 HCP | 个体预测提升；刻板 KL；纠正收敛 | +20%；≤ κ_kl；≤ 2 轮 |
| E214 CAS | 原生评审得体率；H_hard 违反 | ≥ 85%；= 0% |
| E215 VIG | 急停 P95；误打断；partial 误授权 | ≤ 150ms；≤ 5%；= 0% |
| E216 CDM | 完成率；澄清轮次；面子威胁；高语境得体 | ≥ 90%；≤ 3；−40%；≥ 85% |
| E217 PCE++++++ | 降级正确性；VOI 单调性 | 100%；单调递减 |
| E218 CNR | 检出率；误报；纠正成功 | ≥ 90%；≤ 10%；≥ 85% |
| E219 CAJ | 通过率；审计回放；异议处理 | ≥ 99.9%；100%；≤ 1 轮 |
| E220 端到端 | vs 第 61 轮：急停时延、文化得体、澄清轮次、成功率 | −60%；+35%；−30%；+10% |

**消融**：A1 去韵律；A2 去 CPL；A3 去 HCP；A4 去 VIG 旁路；A5 去 CNR；A6 去 CAJ。

**跨文化协议**：≥ 4 文化簇 × 3 语言/口音 × 2 接触场景（递物/搀扶）；本地母语评审 + 双盲视频评分 + 规范违反标注；留一文化簇泛化测试；所有文化原型仅用于**先验初始化**，最终以个体后验与硬禁忌为准。

## 5. 本轮最大风险

**一句话**：若文化隐变量在证据不足时被过度更新、或韵律告警在不同语言/口音/情绪表达习惯下系统性偏移（某些文化本就高音量、快语速、频繁重叠说话），系统就会要么把「正常热情」误判为紧急而频繁急停，要么把「真正的恐慌」当作文化常态而错过停车窗口，并把刻板印象固化成「可审计的偏见」——因此必须以「韵律告警独立于文本 + 硬禁忌显式注入 + KL/证据门控 + CNR 反事实纠偏 + 人类一键否决」构成不可绕过的文化-语音安全护栏，并坚持跨文化留出验证。
<!-- ARTIFACT:END -->
