# 第 58 轮产物 · 创新点清单 v34：PlaceGround-AffectAdvice（有址证据×无权威表情，SEA×TEL×AAC×AIC×CG×PCX-MF）

> 承接第 57 轮 IP-133~138（MFSL/XMC/PTM/MXI/FSE/PCE+）与第 56 轮 IP-127~132（SMM/PCE/BVK/ISE/TAF/MEC）。第 57 轮把证据质量做成"少样本可校准、跨模态可对账、个性化有界"；本轮再补两个更靠前的前提：**证据必须有地址与谱系，才知道它能否跨区域旅行、何时该被召回**；**人的表情只能改变"怎么问"，不能改变"信不信"与"是否同意"**。核心命题由"证据说可信"升级为 **"有址的证据、可续的同意、无权威的表情"**：地图给证据地址与迁移许可证，表情给交互节奏与理解检查，二者都被严格挡在证据门与授权门之外。
> IP 编号：IP-139~IP-144（共 6 个），升级 IP-127（SMM→SEA）、IP-130（ISE→ISE-F）、IP-132（J_m→J_q）以纳入地址、谱系、同意地理与表情非干涉维度。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-139 | SEA Semantic Evidence Atlas | 升级 IP-127 | 几何/拓扑/语义/证据/谱系/版本六层地图；语义-证据矛盾与别名关系显式登记 |
| IP-140 | TEL Transfer Evidence License | 新增 | 一跳迁移 + 衰减 + 本地探针建边；`EV-map` 仅限 L1；证伪谱系闭包隔离 |
| IP-141 | AAC Affect Advisory Channel | 新增 | FER 只进咨询通道；保守动作集 `A_adv`；表情非干涉与分组公平 |
| IP-142 | AIC Affect-triggered Inquiry Check | 新增 | 表情检测"没听懂"而非"同意了"；理解探询只改渲染/节奏 |
| IP-143 | CG Consent Geography | 新增 | 区域×接触级别×材料版本的同意状态；拒绝持久、授权过期、重问有界 |
| IP-144 | PCX-MF + J_q | 升级 IP-128/132 | 探-诺-演-问闭环；迁移许可证、别名审计、同意地理、表情日志合入证书 |

## 1. 符号体系增量（定义 139–144）

| 符号 | 含义 |
|---|---|
| `𝓜=(G,T,S,E,L,ν)` | 分层证据地图：几何/拓扑/语义/证据账本/谱系 DAG/版本向量 |
| `C_𝓜(r), r≈r'` | 语义-证据矛盾度、别名关系（感知不可区分） |
| `E_tr, L_tr, w_tr, γ` | 迁移边集、最大深度、迁移权重、衰减因子 |
| `TL(r→r')` | 迁移证据许可证（结构/语义/非别名/覆盖/版本/未隔离） |
| `EV-map` | 迁移证据类（仅 L1，至多替代一次佐证，不入不可逆必要集） |
| `Q(L)` | 源证据被证伪后的谱系-迁移闭包隔离 |
| `a_t=(AU,valence,arousal,uncertainty,engagement)` | 表情咨询观测（表达层，不是状态层） |
| `A_adv, ⪯_c` | 保守咨询动作集、交互参数保守偏序 |
| `κ_comp, θ_comp, k_comp` | 理解失败分、阈值与每 L2 理解探询预算 |
| `c(r,ℓ,κ), T_grant, T_deny` | 同意地理状态、授权有效期、拒绝持久期 |
| `J_q` | 地址-同意-表情联合证书 |

## 2. 关键算法伪代码

### IP-139 SEA（分层证据地图：地址、谱系、矛盾、别名）

```python
def sea_update(M, e):
    # e=(region,type,payload,src,t,w,ver,parent_ids)
    parents = M.lineage.parents_of(e)                 # 显式谱系，不猜来源
    M.E.append(e.with_parents(parents)); M.L.add(e.id, parents)
    if e.type == 'human':
        e.w = min(W_MAX_H, w0 * e.src.cal)            # 继承第 57 轮有界人类权重
    M.b[e.region] = staleness_decay(
        bayes_update(M.b[e.region], e.like, e.w), age(e, M.prov[e.region]))
    M.S[e.region] = bayes_update(M.S[e.region], e.sem_like, e.w)
    M.C[e.region] = semantic_evidence_contradiction(M.S[e.region],
                                                    M.b[e.region],
                                                    M.G.neighbors(e.region))
    if M.C[e.region] > theta_c:                       # 矛盾区域先隔离再解释
        M.quarantine.flag(e.region, 'semantic_contradiction')
    M.alias.audit(e.region, M.embed)                  # 更新 r≈r' 邻域
    M.ver.bump(e.region, e.ver.src); return M

def alias_audit(M, r):
    for r2 in M.G.candidates(r):
        if place_embed_dist(r, r2) <= theta_alias:
            M.alias.add(r, r2)                        # 别名边：禁止直接迁移
            M.MAT[r].append(('alias', r2, t_now))
    return M.alias
```

### IP-140 TEL（迁移证据许可证与证伪闭包）

```python
def transfer_evidence(M, r, r2, level, contact_type):
    if level > 1: return None                         # 硬规则：迁移只服务非不可逆层
    if M.alias.aliased(r, r2): return None            # 别名区域禁迁
    if not TL(M, r, r2, contact_type): return None   # 结构/语义/覆盖/版本/隔离全检
    w = min(W_MAX_TR, M.b[r].w * (GAMMA_TR ** depth(r, r2)))
    e = Evidence('EV-map', r2, like=M.b[r].like, w=w,
                 parents=[M.lineage.root(r)], level=level)
    M.E_tr.add(r, r2, w, created_by='local_probe')   # 只能由本地探针确认类比后建边
    M.audit.log(('transfer', r, r2, w, level)); return e

def falsify_closure(M, e_bad):
    victims = M.L.descendants(e_bad) | M.E_tr.descendants(e_bad.region)
    for v in victims:                                # 一个版本周期内全量隔离
        M.quarantine.flag(v, 'lineage_falsified'); M.ver.bump(v, 'quarantine')
    return M                                          # 重新本地取证后才可解隔离
```

### IP-141 AAC（表情咨询通道：只许降险，不授权、不作证）

```python
def affect_advise(a_t, s_op, ctx, audit):
    assert not stores_raw_frame(a_t)                  # 端侧临时特征，原始帧不落盘
    if not s_op.face_opt_in: return s_op.params       # 可退出，不惩罚
    adv = g(a_t, s_op, ctx)                           # 从 A_adv 中取一个动作
    if adv not in A_ADV: adv = 'notify'               # 白名单兜底
    new = apply_conservative(s_op.params, adv,
                             order=PREC_CONSERVATIVE) # corrob↑ τ_int↓ clarity↑
    audit.log(adv, only_demotions=True)               # 日志不含面部特征原文
    return new                                        # 证据门/同意状态不可达

def affect_noninterference_test(policy, traces):
    for tr in traces:                                 # 固定证据与同意，替换任意表情
        base = policy(tr.evidence, tr.consent, a0)
        for a in tr.affect_variants:
            assert commits(policy(tr.evidence, tr.consent, a)) <= commits(base)
    return True                                       # 任何升险即阻断上线
```

### IP-142 AIC（表情触发理解探询：发现"没听懂"，不是"同意了"）

```python
def comprehension_check(a_t, exp, hist, persona):
    k = comprehension_score(a_t, exp, hist)           # 困惑微表情/凝视漂移/重复看图
    if k <= theta_comp: return None
    if persona.comp_budget <= 0: return None
    persona.comp_budget -= 1
    q = explicit_question("你看到的是哪一块？需要换触觉/语音解释吗？")
    return switch_render(exp, q, allowed={'map','haptic','voice','text'})
    # 只改 Exp/渲染/节奏；不产生 EV-*，不改变 c(r,ℓ,κ)，不改变 auth
```

### IP-143 CG（同意地理：拒绝持久、授权可续、重问有界）

```python
def consent_transition(c, event, ctx):
    if event.kind == 'human_explicit':                # 唯一可放松的入口
        if event.answer == 'grant': return Consent('granted', exp=ctx.now + T_GRANT)
        if event.answer == 'deny':  return Consent('denied',  until=ctx.now + T_DENY)
    if event.kind in ('timeout', 'face_advice'):      # 只可更保守
        return conservative(c)                        # → denied / unknown
    if c.material_version != ctx.material_version:    # 力包络/任务/环境变了
        return Consent('expired')
    if c.exp < ctx.now: return Consent('expired')
    return c

def may_ask(c, ctx):
    if c.state == 'denied' and not ctx.material_change: return False   # 不许问到同意
    return ctx.reask_budget[(c.region, c.level, c.kappa)] > 0
```

### IP-144 PCX-MF（探-诺-演-问：地址、迁移、表情、同意四账合流）

```python
def probe_commit_evolve_mf(x0, M, task, budget, consent, personas):
    route = plan_on_map(M, task, risk_model)
    sched, log = [], []
    for cp in route.checkpoints:
        inf = meta_few_shot_infer(M, cp.region, M.obs[cp.region], meta)   # 第 57 轮
        M.b[cp.region] = inf.post if inf.cls == 'ID' else worst_in(inf.belt)
        for r2 in M.transfer_candidates(cp.region):                      # IP-140
            e = transfer_evidence(M, r2, cp.region, level=contact_level(cp),
                                  contact_type=cp.contact_type)
            if e: M = sea_update(M, e)
        sigma = foothold_schedule(x0, cp, M); R = schedule_risk(sigma, M)
        while select_gait(R) == 'halt' and budget.probes_left > 0:
            cands = admissible_probes(cp, M, F_abs)
            if not cands: break
            p = argmax(cands, key=lambda q: voi_meta_pessimistic(q, M, inf) - cost(q))
            if voi_meta_pessimistic(p, M, inf) < theta_voi: break
            M = sea_update(M, execute_probe(p, cap=F_abs))
            if M.C[cp.region] > theta_c or M.alias.aliased_here(cp.region):
                M.quarantine.flag(cp.region, 'prefer_local_probe')       # 本地优先
            sigma = reselect_footholds(x0, cp, M); R = schedule_risk(sigma, M)
            budget.spend(p)
        params = affect_advise(cp.face, personas.active, cp, audit)      # IP-141
        consent_c = consent_transition(consent[cp.region], cp.event, cp)
        exp = grounded_explanation(M, sigma, failing_constraint(cp, M))
        if consent_c.state != 'granted' and cp.level == 'L2':
            if not may_ask(consent_c, cp): return safe_brake(cp), exp, 'consent_denied'
            if not explicit_confirm(exp, params): return safe_brake(cp), exp, 'timeout'
        comp = comprehension_check(cp.face, exp, cp.hist, personas.active)  # IP-142
        if comp: exp = comp
        if few_shot_evidence_gate_q(cp, M, personas, contact_level(cp), ood_reg)[0] == 'ok':
            sched.append(commit(sigma, select_gait(R))); log.append(tag_evidence_q(...))
            continue
        alt = reroute(M, cp, risk_model)
        if alt and select_gait(schedule_risk(alt, M)) != 'halt': route = alt; continue
        return negotiate_or_stop(cp, M, sigma, R, consent_c, tau_int=params.tau_int)
    return sched, log, M
```

### IP-132→J_q（地址-同意-表情联合证书）

```python
def few_shot_evidence_gate_q(c, M, personas, level, ood_reg):
    if c.ev == 'EV-map':
        ok = level == 'L1' and c.transfer_license and c.depth <= L_TR_MAX \
             and not M.alias.aliased(c.src, c.dst) and M.C[c.dst] <= theta_c
        if c.irreversible: return ('reject', 'map_on_irreversible', c)  # 硬禁令
    elif c.ev == 'EV-face':
        return ('reject', 'face_is_not_evidence', c)                    # 永不入证
    else:
        ok = round57_gate(c, M, personas, ood_reg)                      # 继承第 57 轮
    return ('ok', c) if ok else ('reject', 'evidence_insufficient', c)

def map_consent_affect_certificate(sched, log, M, consent_geo, affect_log, audit):
    for c in core_contacts(sched):
        st = few_shot_evidence_gate_q(c, M, persona_of(c), contact_level(c), ood_reg)
        if st[0] != 'ok': return st
    if not M.lineage.audit_complete():        return ('reject', 'lineage_incomplete')
    if not M.alias.audit_passed(sched):       return ('reject', 'alias_unresolved')
    if any(consent_geo.refused(c) for c in core_contacts(sched)):
        return ('reject', 'consent_denied')
    if not affect_noninterference_test(policy, affect_log.traces):
        return ('reject', 'affect_interference')
    if affect_log.raw_frames_retained:        return ('reject', 'privacy_violation')
    return ('ok', Jq(M.ver, M.lineage, M.E_tr, consent_geo, affect_log, fairness_audit))
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| SEA | O(\|ΔE\|·log\|V\|+d_s) 增量；谱系 O(\|E_L\|) | O(\|V\|·d_b+\|E_L\|) | 来源/版本诚实、矛盾/别名显式、隔离可回滚 |
| TEL | O(deg(r)·L_tr) | O(\|E_tr\|) | 一跳、衰减、仅 L1、证伪闭包完整 |
| AAC | O(1)/帧 + 摊还校准 | O(\|操作者\|) | 非干涉、分组校准、原始帧不落盘（A42） |
| AIC | O(1)+O(k_comp) | O(\|Exp\|) | 只改渲染/节奏，不改证据/同意 |
| CG | O(1) 查表 | O(\|V\|·\|ℓ\|) | 显式动作才放松、拒绝持久、授权过期（A43） |
| PCX-MF | O(\|CP\|·(k_p+k_c+k_r)·(C_VOI+d_φ+\|E_tr\|)) | O(\|V\|+\|σ\|) | 悲观 VOI、三预算终止、四态完备 |

**正确性定理（Place-indexed Affect-monotone Commitment Soundness, PACS）**
假设 A22–A32（第 53–55 轮）、A33–A40（第 56–57 轮）成立；**(A41)** 地图谱系与版本诚实，`TL` 充分，别名/矛盾检测召回满足声明，迁移深度 `≤L_tr`；**(A42)** 表情咨询只含 `A_adv`，非干涉回归测试通过，分组校准诚实，原始帧不落盘；**(A43)** 同意地理持久，只有显式人类动作可放松，拒绝跨会话、授权遇材料变化过期。则：

1. **有址承诺健全性**：ID 路径 `P(fail) ≤ δ_f + ε_meta(k) + δ_probe + ε_h(w_max) + δ_tr·1[EV-map∧L1] + δ_ood·α_conf`；不可逆接触因硬禁 `EV-map/EV-xmodal`，其界不含 `δ_tr/δ_xm`。
2. **表情非干涉**：固定证据与同意时，表情通道不改变不可逆承诺集合的上界，只可缩小；`δ_face` 只进入可用性/时延项，不进入 `P_fail` 的安全项；任何检测到的升险路径即阻断上线。
3. **同意单调性**：无显式人类动作时所需同意级别不下降；拒绝跨会话持久；授权遇材料变化/超期自动过期；重问预算有限，禁止"问到同意"。
4. **传染有界**：`L_tr=1` 且 outdeg 有界 ⇒ 单条误标的迁移污染半径 `≤1+outdeg_max`；源证伪后谱系闭包隔离在一个版本周期内完成。
5. **终止性**：每检查点 `k_probes+k_cons+k_comp+k_reask` 有限，PCX-MF 终止于 {承诺, 绕行, L2 协商, 安全停}。

**部署界**（对检查点与迁移边取联合界）：

```
P_safe ≥ 1 − Σ_cp (δ_f + ε_meta(k) + δ_probe + ε_h + δ_tr·1[EV-map∧L1] + δ_ood·α_conf)
             − P(𝓜 版本冲突未检出) − P(别名检测漏检) − P(谱系闭包未完成)
             − P(护盾回退失败) − P(τ_int ∧ τ_mm 超时 ∧ 安全停失效)
             − P(同意地理日志失效)          # 表情项不出现：它无权升险
```

关键：**地址把"坏证据长寿"变成"坏证据可召回"**（迁移有许可证、有深度、有谱系、有闭包）；**表情把"人机交互"从读心变成咨询**（只降险、不作证、不授权、可退出）；**同意地理把"一次同意"变成"可续、可拒、可过期"的显式契约**。三者都经"更保守或更会问"两个安全通道起作用，不存在靠表情或地图"更敢赌"的路径。

## 4. 实验设计 E177–E181

| 实验 | 指标 | 目标 |
|---|---|---|
| E177 语义迁移的收益与误迁移 | 跨区域先验校准/覆盖；误迁移率；同风险探针数；vs 无地图、朴素相似度迁移、第 57 轮 | 误迁移 ↓≥50%；探针数 ↓≥30%；不可逆失效率不增；覆盖不低于第 57 轮 |
| E178 语义传染与别名 | 注入单区域误标后的污染区域数/深度；隔离与回滚时延；别名检测 AUROC/召回；矛盾检测召回 | 污染半径 ≤1+outdeg；回滚 ≤1 版本；别名召回 ≥95%；矛盾召回 ≥90% |
| E179 表情非干涉与公平 | 固定证据下表情改变承诺次数；理解探询命中率/误报率；worst-group ECE；原始帧留存审计；退出率 | 0 次升险；命中 ≥85%、误报 ≤15%；worst-group ECE ≤0.15；0 留存；退出不受罚 |
| E180 同意地理 | 拒绝跨会话持久率；授权过期/材料变化重问率；"问到同意"违规数；日志完整性 | 100%；100%；0；100% |
| E181 端到端 | 新场地四足 vs 第 57 轮：成功率/探针时间/首访承诺时延/解释理解率/同意违规/操作者信任 | +6%/−25%/−20%/+15%/0/不下降 |

## 5. 集成更新：v16** → v16***

```
根信任 + 能力格
│
├─ L0 分布式底座与执行边 (GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX,XFR,CRC,SFE,FDR,RAB,DST,SBC)
├─ L0.5+ 鲁棒性层 (TRO,RXC,RCO,REX,RTA,TRC,RUR)
├─ L0.5++ 动作-协同层 (ACS,SCOM,CEC,AEC,JTC)
├─ L0.5* 证据-交互层 (SMM,PCE,BVK,ISE,TAF,MEC)
├─ L0.5*⁺ 元认知-信任层 (MFSL,XMC,PTM,MXI,FSE,J_p)          ← v57
├─ L0.5*⁺⁺ 地址-同意层 (SEA,TEL,AAC,AIC,CG,J_q)             ← v58 新增
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
...
└─ L6 原型证伪/XFER/LFF/IXD
```

JCPS 输出扩展为：
`(v,a,m,q,ι,κ,g,λ,τ,σ,ρ,Explain,RUR_state,α_S,A_cert,γ_ce,δ_a, Σ/C+ 结构, 𝓜_core, J_m, probe_log, consent_state, w_h, q_φ/k*, D(r), ρ_ℳ, s_op/auth, m_E, ood_state, J_p, map_ver/lineage, E_tr, C_𝓜/alias, consent_geo, a_t/advice, comp_log, fairness_audit, J_q)`

其中新增：`map_ver/lineage` 地图版本与证据谱系；`E_tr` 迁移边与许可证；`C_𝓜/alias` 语义矛盾与别名审计；`consent_geo` 区域同意状态；`a_t/advice` 表情咨询观测与动作；`comp_log` 理解探询日志；`fairness_audit` 分组校准审计；`J_q` 地址-同意-表情联合证书。

云边协议 CEB++ → **CEB^A**：云端可同步语义先验与迁移候选，但**迁移边只能在边端由本地探针确认后创建**；云端可下发 FER 模型增量，但**必须过隔离区**——影子模式运行，分组校准不劣化 ∧ 非干涉回归通过 ∧ 原始帧零留存才可接管咨询通道；边端只回传脱敏的咨询动作计数、理解探询结果与同意地理状态，不回传面部帧。第 57 轮"一切判定器走隔离"在本轮扩展为"**一切地图迁移与一切表情模型都走隔离，且地图只给址、表情只给度、人给权**"。

## 6. 本轮最大风险

**一句话**：本轮最大的风险是**地图把局部误标变成可迁移的共识、表情把"看见"误当成"理解"**——若迁移许可证与别名检测失守、且表情被误读为同意，系统会在证据没有增加、同意没有给出时显得更确定、更体贴，实际却把错误传播得更快、把拒绝绕过得更顺；必须以一跳迁移、谱系闭包隔离、表情只降险不授权、同意地理显式可续四重护栏，宁可让地图"少知道一点"、让人"多被问一句"，也不让地址变成谣言、表情变成授权。
