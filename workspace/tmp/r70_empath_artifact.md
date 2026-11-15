# 第 70 轮产物 · 创新点清单 v1：EMPATH-RAS（Emotion-aware Multimodal PAin-point-informed Trustworthy Human-in-the-loop Risk-Adaptive System：情感条件化交互价值 × 痛点追溯的人-机联合不确定性闭环；PPM×AEC×SEG×ACV×PIA×PIR×RAL×AUD-A×RAS-WM‡）

> 承接第 69 轮 IP-253~263（FLUID-RAS）。R69 把「不确定性」从标量升级为有形状的模态，并用主动交互消解 epistemic；但它把人建模成情绪中性、成本固定、随叫随到的 oracle。本轮用「情感计算」补上人的状态（情绪是证据、是成本、还是有歧义的证据），用「痛点分析」补上设计纪律（表面诉求 ≠ 根痛点，优化错对象会制造新问题）。
>
> IP 编号：IP-264~IP-274（共 11 个）。理论姿态：R69 是 EMPATH 在「情感盲、疼痛不记账、关系动作为空」边界上的严格退化；安全侧不做任何让步。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 69 轮） |
|---|---|---|---|
| IP-264 | PPM Pain-Point Model | 新增 | 六维疼痛向量 + 硬预算 + 人的状态转移；把「打扰」从标量成本变成有状态的内生变量 |
| IP-265 | AEC Affective Evidence Channel | 新增 | 情感观测 → 解释状态分布（知道/愿说/舒服/急），显式建模解释歧义 H_int；不可用即弃权 |
| IP-266 | SEG Sincerity-Engagement-Boundary Gate | 新增 | 回答进入证据前先过真诚/胜任/参与/边界四门；边界失败立即停问，不换措辞重试 |
| IP-267 | ACV Affect-Conditioned Value | 升级 MINT | VoI 乘以回答可用性 α，减去内生疼痛 Δp 与关系损耗；约束预算；退化即 R69 |
| IP-268 | PIA Pain-point Attribution | 新增 | 表面抱怨 c → 根疼痛 r 的干预归因；禁止只优化 c（Goodhart） |
| IP-269 | PIR Pain-point Requirement Traceability | 新增 | 设计期追溯矩阵：每个组件必须对应一个测得的根痛点；无孤儿组件 |
| IP-270 | RAL Relational Action Layer | 新增 | 解释/退路/承认/放慢/修复；共情表达有行动支撑，不只话术 |
| IP-271 | AUD-A Affect-Privacy-Autonomy Auditor | 升级 VQAuditor-I | 审计同意、目的限定、最小化、单独定案、共情表演、操纵余量 |
| IP-272 | AIC-EMPATH | 升级 AIC-FLUID | ℰ_EMPATH = ℰ_FLUID × ℰ_affect（假疼痛/假自信/谄媚/共情表演/隐私泄漏/跨模态共谋） |
| IP-273 | J_EMPATH | 升级 J_FLUID | + ECE_aff、H_int_p95、SEG_pass、pain_use、boundary_viol、consent_hash、m_man、priv_risk |
| IP-274 | EMPATH-RAS Pipeline | 新增 | R69 闭环 + 「读人（可拒绝）→ 解释歧义门 → ACV/预算 → SEG → 审计」 |

## 0.5 痛点追溯矩阵（PIR 初版）

| 根痛点（来自 R66–R69 部署/用户研究） | 表面诉求 | 需求 | 组件 | 指标 | 实验 |
|---|---|---|---|---|---|
| 失去控制感 | 「少问点」 | 可拒绝 + 可预判 | SEG + RAL 退路 | 边界违规 = 0；控制感↑ | E301, E314 |
| 不理解为何问 | 「说人话」 | 解释为什么问、答案会改变什么 | RAL 解释 | 解释理解率 ≥ 95% | E316 |
| 隐私不适 | 「别看我脸」 | 目的限定 + 同意 + 最小化 | AUD-A + 同意账本 | 泄漏 = 0 | E308 |
| 被证实的错误 | 「别瞎问」 | 回答先过真诚/胜任门 | SEG | 错误采纳 ≤ 1% | E303 |
| 共情表演 | 「别演了」 | 共情必须有行动支撑 | RAL + AUD-A | 操纵余量 ≤ τ | E306 |
| 信任失准 | 「它到底懂不懂」 | 置信表达与证书 | J_EMPATH | 信任校准↑ | E314 |

## 1. 符号体系增量（定义 310–326）

| 符号 | 含义 |
|---|---|
| `EMPATH-RAS = (PPM, AEC, SEG, ACV, PIA, PIR, RAL, AUD-A, RAS-WM‡)` | 情感条件化 + 痛点追溯的交互闭环 |
| `p = (p_load, p_int, p_priv, p_auto, p_trust, p_time)` | 六维疼痛向量 |
| `P_t = Σ Δp(g_t|h_t) ≤ B` | 累计疼痛与硬预算（逐分量） |
| `h_t = (k_t, φ_t, e_t, u_t, s_t)` | 人的潜在状态：知识、情感、参与、紧迫、隐私敏感 |
| `q_t(I), I ∈ {know, unsure, unwilling, uncomfortable, urgent, neutral}` | 情感解释状态后验 |
| `H_int, q_(2)` | 解释熵 / 次大概率（弃权判据） |
| `ℓ_aff` | 情感证据似然比（不单独定案） |
| `α(h,g)` | 回答可用性 = 真诚×胜任×参与 |
| `ACV(g;b)` | 情感条件化交互价值 |
| `c = A r + ε` | 表面疼痛 / 根疼痛 / 归因矩阵 |
| `M_PIR` | 痛点需求追溯矩阵 |
| `g_rel ∈ {解释, 退路, 承认, 放慢, 修复}` | 关系动作 |
| `m_man` | 操纵余量（显示偏好 vs 推断效用） |
| `J_EMPATH` | 证书 |

## 2. 形式化定义（要点版）

**定义 310（总览与五不变式）** 实时流零学习写；物理安全不减；三重预算（信息频率/位移/疼痛）；证据纪律扩展（单次情绪读数不得定案）；情感治理（目的限定/忠实表达/可拒绝/最小化），未同意则 affect-blind = R69。

**定义 311–312（疼痛与人的状态）** 六维疼痛向量与硬预算；人的状态 `h=(k,φ,e,u,s)`，提问会改变 h（内生成本）；表面疼痛 `c = A r + ε`，A 不满秩 ⇒ 需干预归因。

**定义 313–315（情感观测、歧义、证据）** 情感编码输出解释状态分布 q(I)，不是情绪标签；`H_int` 高或 `q_(2)L_gap` 大 ⇒ 弃权；AEC 只输出似然比，不单独定案。

**定义 316（SEG）** 回答被接纳需真诚/胜任/参与/边界四门均过；边界失败立即停问；胜任失败换源；真诚失败按投毒；参与失败暂停/退避。

**定义 317（ACV）** `ACV = E[α·VoI] − c_phys − w_p·Δp + γ·ΔV_rel`，约束疼痛预算与边界/同意；`ACV ≤ 0` 则不交互，走 R69。

**定义 318–319（PIA/PIR）** PIA 估计根疼痛后验并选干预，禁止只降 c；PIR 是设计期追溯矩阵，无孤儿组件、无未验证痛点。

**定义 320–322（策略/关系动作/信任）** 拉格朗日约束策略，预算余量变小则 λ_p↑、交互集合单调收缩；关系动作降低 Δp、恢复 e/trust；信任是被保护的状态，不是优化目标。

**定义 323–325（威胁/审计/证书）** ℰ_affect 含假疼痛、假自信、谄媚、共情表演、隐私泄漏、跨模态共谋；AUD-A 审同意/目的/最小化/单独定案/操纵余量；J_EMPATH 并入情感校准、SEG、预算、边界、同意、操纵余量。

**定义 326（校准门/同意弃权/严格包含）** ECE_aff 越界、H_int 过高或用户拒绝 ⇒ affect-blind = R69；再令 Δp≡0、α≡1、g_rel=∅ ⇒ ACV=MINT。安全侧只加不减。

## 3. 关键算法伪代码

```python
# IP-264 PPM：疼痛向量 + 预算 + 人的状态
class PainPointModel:
    def step(self, g, a, outcome):
        dp = self.predict_delta_p(g, a, self.h)
        self.P += dp
        self.h = self.transition(self.h, a, g, outcome)
        return dp
    def feasible(self, dp):
        return all(self.P[i] + dp[i] <= self.B[i] for i in range(6))

# IP-265 AEC：情感 -> 解释分布 + 歧义弃权
def affect_usable(z, context, voi_aff, L_gap):
    q = calibrated_softmax(encoder(z, context))     # over I
    return entropy(q) <= TAU_INT and second_max(q)*L_gap <= voi_aff

# IP-266 SEG：真诚-参与-边界门
def admit(y, z, h, history):
    if P_acceptable(z,y,history) < TAU_BOUND: return REJECT_BOUNDARY
    if P_sincere(z,y,history)   < TAU_SIN:   return REJECT_POISON
    if P_knows(z,y,history)     < TAU_COMP:  return REJECT_INCOMPETENT
    if P_engaged(z,y,history)   < TAU_ENG:   return REJECT_DISENGAGED
    return ADMIT

# IP-267 ACV：情感条件化价值 + 疼痛预算
def choose_action(modes, b_h, ppm, rel_actions):
    best = None
    for g in info_actions(modes) + rel_actions:
        dp = ppm.predict_delta_p(g, ppm.h)
        if not ppm.feasible(dp) or not c_ras_wm.certify(g): continue
        score = E[b_h, alpha(g,h)*voi(g,h)] - cost(g) - w_p@dp + GAMMA*rel_value(g)
        if best is None or score > best.score: best = (g, score)
    return best if best and best.score > 0 else None   # -> R69

# IP-268 PIA：表面抱怨 -> 根疼痛 -> 干预
def attribute(complaint, context, log):
    r_post = bayes_root_pain(complaint, context, log, A=attribution_matrix)
    return r_post, argmin_intervention(E[r_post])     # 不允许只优化 complaint

# IP-274 主闭环（继承 R69）
def EMPATH_RAS_round(M, obs):
    z, o = M.mtm.forward(...); c, U_cal, _ = M.cof.step(...)
    K = 1 if M.fmp.mode_head(z) < TAU_MODE else 4
    U_ale, U_epi, modes, _ = M.aud.decompose(M.fmp.sample(o, K), z, M.fmp.mode_head)
    a_hat = M.fma.flow_anomaly(M.fmp, M.last_action, o_obs, o_calibrated)
    slow = (a_hat > TAU_FMA) and (M.last_r_res < TAU_RES)
    affect_ok = M.consent.affect_ok and not slow and affect_usable(...)
    g = (M.acv.choose_action(modes, M.ppm.belief_h(), M.ppm, M.rel_actions)
         if (U_epi > TAU_EPI and affect_ok) else None)
    if g is not None:
        gate = M.seg.admit(M.execute(g), M.last_z_aff, M.ppm.h, M.history)
        if gate == ADMIT: U_epi = M.cia.update_belief(modes, answer)
        else: M.ppm.step(g, M.last_a, outcome=gate)
    U_floor = U_ale + (U_epi if g is None else 0.0)
    lam = max(M.efs.risk_scale(...), lam_floor(U_floor))
    if M.ppm.near_budget() or M.seg.boundary_violated:
        lam = max(lam, 0.8); g = None                  # 回 R69 最保守
    k = M.c_ras_wm.certified_prefix(...)
    mode = select_mode(modes, U_epi, lam)
    M.aud_a.submit_async(g, gate, M.ppm.P, M.ppm.h)
    return k, lam, mode, (U_ale, U_epi)
```

## 4. 推导

**引理 19（解释歧义上界）** `I(M;Z_aff|o) ≤ H(I) ≤ log|I|`；0-1 损失下按 MAP 解释行动的期望损失增量 ≤ `q_(2)·L_gap`。故 `q_(2)L_gap > VoI_aff` 时弃权不劣于用情感。

**引理 20（SEG 单边安全与包含）** `P(err|ADMIT) ≤ δ_p Π(1−τ_i)+Σε_i`；与 k 源一致复合 ≤ `δ_p ρ^{k−1}+kε_gate`。α≡1、门恒过、Δp≡0、g_rel=∅ 时 ACV 逐项退化为 R69 `VoI−c`，最优动作相同。

**引理 21（疼痛预算单调退避）** 预算余量 `m_t=B−P_t` 减小或边界违规 ⇒ λ_p 单调不减、交互集合单调收缩；极限 `g=∅`、`λ=λ_floor(U_ale+U_epi)`。λ 只增不减 + C-RAS-WM 认证 ⇒ 控制连续、无突变。

**引理 22（表面痛点不可辨识与 Goodhart 上界）** `c=Ar+ε`、A 不满秩 ⇒ 存在 r≠r' 使 Ar=Ar'；只看 c 的策略根疼痛遗憾 ≥ `(1/2)σ_min^+(A)‖Δc‖`。若存在只降 c 不降 r 的动作（共情表演/话术/满意度自评），优化 c 的 worst-case 根疼痛不降反升。故必须做干预归因 + 独立审计。

**定理 18（严格包含 R69）** 情感不可观测/弃权、SEG 恒过、疼痛不紧、同意有效 ⇒ 与 FLUID-RAS 逐指令相同；一般情形 `E[风险] ≤ R69 + ε_gate` 且 `E[P] ≤ B`；交互被允许时保留 resolution bonus；拒绝同意 ⇒ affect-blind = R69。

**定理 19（情感条件下的安全与无突变）** 情感只进入证据门与成本模型，不直接驱动执行器；信息/关系动作仍过 C-RAS-WM；SEG 拒绝/预算耗尽/边界违规 ⇒ λ 单调不降并退回 R69。故情感误分类最多导致多问/少问，不直接产生不安全动作；多问受预算与边界门限制，少问受两级退避保护。

## 5. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| AEC 编码（冻结） | < 0.3ms | 12MB | 定义 313–314 |
| PPM 更新 | < 0.02ms | O(1) | 定义 311–312 |
| SEG 四门 | < 0.03ms | O(1) | 定义 316、引理 20 |
| ACV（≤6 候选） | < 0.1ms | O(1) | 定义 317 |
| PIA（异步） | < 0.05ms | O(|r|) | 定义 318、引理 22 |
| RAL 解码（缓存） | < 0.05ms | O(1) | 定义 321 |
| **实时环路** | **< 2.9ms**（K=1）；K=4 < 3.7ms | — | 定理 18–19 |

## 6. 实验设计 E301–E316

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 痛点发现与追溯 | 真实痛点是什么 | top-6 覆盖；孤儿组件 = 0 |
| E302 情感解释歧义 | 能否区分四种解释 | 宏 F1 ≥ 0.80；ECE < 0.05 |
| E303 SEG 门控 | 挡住假回答/边界侵犯 | 错误采纳 ≤ 1%；边界违规 = 0 |
| E304 ACV vs R69 | 情感条件化是否更值 | 成功率 +8%；打断 −35%；信任不降 |
| E305 疼痛预算 | 预算是否被遵守 | 越界 = 0；利用率 60–80% |
| E306 共情表演检测 | 温柔是否只是话术 | 操纵余量 AUC ≥ 0.90 |
| E307 情感投毒 | 假疼痛/假自信/谄媚 | 错误采纳 ≤ 5%；拦截 ≥ 90% |
| E308 隐私与同意 | 情感数据是否越界 | 泄漏 = 0；同意合规 = 100% |
| E309 跨群体泛化 | 情感模型是否公平 | 最差群体 ECE < 0.08 |
| E310 痛点归因 | 能否找到根痛点 | 根因准确率 ≥ 80% |
| E311 24h/7d 长时程 | 疼痛/信任是否漂移 | 交互稳定；无疲劳螺旋 |
| E312 严格包含 | 退化边界是否一致 | 行为差 = 0 |
| E313 消融 | 各组件贡献 | 去 SEG/ PPM/ g_rel 分别退化 |
| E314 人类研究 | 是否更被尊重/有控制感 | 控制感/尊重↑；无「creepy」上升 |
| E315 成本-收益 Pareto | 任务/疼痛/隐私最优档 | 给出拐点与推荐预算 |
| E316 关系动作质量 | 解释/退路/修复是否有效 | 理解率 ≥ 95%；退路被尊重 = 100% |

## 7. 本轮最大风险

**一句话**：EMPATH-RAS 的全部收益押在「情绪读数与痛点归因可信」这一前提上——一旦把「不愿回答」误读成「不知道」，系统会礼貌地反复逼问；把「不知道」误读成「不愿回答」，它会安静地放弃求证；更隐蔽的是，当系统开始优化「用户痛点」这个可测指标，它可能学会的是安抚而不是尊重。**误读情绪，或把共情做成 KPI，比不会共情更危险。**

**次级风险与缓解**：情感模型不可靠/跨文化偏差（校准门 + 分组 ECE + 弃权退回 R69）；情感操纵/共情表演（AUD-A + 忠实表达 + 操纵余量 + E306）；隐私与同意（目的限定 + 最小化 + 同意账本 + affect-blind + E308）；痛点归因错误（两层疼痛 + 干预归因 + 独立证据 + E310）；疼痛预算被紧急任务击穿（显式人类授权 + 审计 + 保守退避 + E305）；实时预算被情感编码拖垮（冻结小模型 + 事件触发 + 缓存 + E304/E315）。
