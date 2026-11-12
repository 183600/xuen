# 第 58 轮产物 · 创新点清单 v34：Fleet-Epistemic-Constitution（认知血缘×能力检疫×证据溯源×集体责任，ELD×CQ×EPD×CRL×FGE×PCE+++）

> 承接第 57 轮 IP-133~138（MFSL/XMC/PTM/MXI/FSE/PCE+）与第 56 轮 IP-127~132（SMM/PCE/BVK/ISE/TAF/MEC）。本轮把部署前提从"少样本可校准、跨模态可对账、个性化有界的证据承诺"升级为 **"跨具身可兑现、跨机可溯源、认知可多样、承诺可分割的集体证据承诺"**：证据从单机私产变为带血缘与根的账本，能力从"会/不会"变为带检疫态的具身契约，协作从"投票"变为"独立证人 + 责任 + 否决"；第 57 轮"一切判定器走隔离"在本轮推广为"**一切能力发布走检疫、一切跨机证据走溯源、一切不可逆承诺只认本机身体与本地否决**"。
> IP 编号：IP-139~IP-144（共 6 个），升级 IP-131/132/137/138 以纳入认知血缘、能力检疫与集体责任维度。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-139 | ELD Epistemic Lineage & Diversity | 新增 | 谱系签名、误差相关上界、有效独立见证数 n_eff、先验多样性 D_π、单文化警报 |
| IP-140 | CQ Capability Quarantine | 新增 | 具身条件化能力契约、单向迁移、shadow/canary/released/revoked、能力接触者追踪 |
| IP-141 | EPD Evidence Provenance DAG | 新增 | 证据有向无环图、根集不相交、循环引证检测、负证据规则、EV-peer（限 L1） |
| IP-142 | CRL Collective Responsibility Ledger | 新增 | 集体承诺、暴露集与责任份额、绝对本地否决、分区安全默认 |
| IP-143 | FGE Fleet Evidence Gate | 升级 IP-137 | 证据门七类、EV-body 本机证书、EV-peer 仅 L1、舰队证书 J_f |
| IP-144 | PCE+++ Collective Probe-Commit-Evolve | 升级 IP-138 | 集体 VOI、异源复探、多样性预算、检疫前置、分区退化 |

## 1. 符号体系增量（定义 139–144）

| 符号 | 含义 |
|---|---|
| `ℓ_i=(π_version,h_shard,sim_version,sensor_batch,calib_lineage,q_φ_version)` | 成员 i 的认知血缘签名 |
| `sim_ℓ(i,j), ρ_ij, ρ̂_ij` | 谱系相似度、真实误差相关、相关上置信界 |
| `n_eff=(Σw)²/ΣΣw_iw_jρ̂_ij` | 有效独立见证数（设计效应折算后） |
| `D_π, D_0` | 先验多样性与其下限 |
| `C_σ(e,c), e'≼e` | 具身条件化能力契约、具身偏序 |
| `Q(C)∈{shadow,canary,released,revoked}` | 能力检疫状态 |
| `G=(V,E), Roots(v), κ(S)` | 证据溯源 DAG、根集、独立根簇数 |
| `EV-peer, EV-body` | 跨机互证（限 L1）、本机具身能力证书 |
| `c=(σ,A_c,E_c,J_f,{λ_i},V_c,mode)` | 集体承诺与责任账本 |
| `J_exp, κ_couple` | 联合暴露上界与耦合系数 |
| `VOI_F, k_fleet, λ_div` | 集体 VOI、舰队互证预算、多样性权重 |
| `J_f` | 舰队级证书 |

## 2. 关键算法伪代码

### IP-139 ELD（认知血缘与有效独立度）

```python
def lineage_audit(fleet, region, calib_log):
    rho = {}
    for i, j in pairs(fleet):
        eps_i = residual_stream(i, region, calib_log)
        eps_j = residual_stream(j, region, calib_log)
        rho[i][j] = upper_confidence(corr(eps_i, eps_j), 0.95)  # 宁可高估
    w = [m.weight for m in fleet]
    den = sum(w[i] * w[j] * (1.0 if i == j else rho[i][j])
              for i in fleet for j in fleet)
    n_eff = (sum(w) ** 2) / max(den, EPS)
    Dpi = 1.0 - max(lineage_sim(i, j) for i, j in pairs(fleet))
    if Dpi < D_0:
        fleet.audit.alarm('monoculture', {'D_pi': Dpi, 'clusters': lineage_clusters(fleet)})
        fleet.corroboration_mode = 'single_root'   # 一致不再升格
    return n_eff, Dpi, rho
```

### IP-140 CQ（跨具身能力契约与检疫）

```python
def capability_quarantine(C, e, fleet):
    if C.state == 'shadow':
        return 'suggest_only'                       # 只出建议，不出承诺
    if C.state == 'revoked':
        revoke_dependents(C, fleet.ledger)          # 能力接触者追踪
        return 'reject'
    if C.state == 'canary':
        st = canary_stats(C)
        if st.ece_not_worse and st.fail_rate <= C.delta_fwd \
           and st.embodiment_clusters >= M_EMB and st.lineage_clusters >= M_LIN:
            C.state = 'released'; fleet.audit.log(('release', C.id))
        else:
            return 'canary_only'
    if not leq(e, C.e):                             # 向上迁移：现场重挣
        d = transfer_debt(C.e, e)
        return 'revalidate' if d > 0 else 'ok'
    return 'ok' if C.state == 'released' else 'suggest_only'

def revalidate_capability(C, e, n_re, obs):
    C.debt[e] = max(0, C.debt.get(e, 0) - n_re * obs.success_rate)
    if observed_fail_rate(obs) > C.delta_fwd + SLACK:
        C.state = 'revoked'                         # 负迁移即撤销
        revoke_dependents(C, ledger)
    return C
```

### IP-141 EPD（证据溯源 DAG 与非循环互证）

```python
def add_evidence(G, v):
    if not all(r in G.nodes for r in v.parents):
        return None                                 # 非法父节点
    G.add_node(v)
    G.add_edges(v, v.parents)
    if reaches(G, v, v):                            # 自环 / 循环引证
        G.remove_node(v)
        audit.flag('evidence_cycle', v.id)
        return None
    return v

def cross_agent_corroborate(G, S, level):
    if level != 'L1':
        return None                                 # 借用证据只进可逆层
    if not roots_disjoint(G, S):
        return None                                 # 共享原始观测，不算独立
    if any(cycle_through(G, v) for v in S):
        return None                                 # 证据洗白
    n_eff, Dpi = lineage_audit(G.fleet, S.region)
    if Dpi < D_0 or n_eff < n_min(level):
        return None                                 # 单文化 → 只算一个根
    if not versions_compatible(S, G.fleet):
        return None                                 # 版本/时效不相容
    return Evidence(kind='EV-peer', n_eff=n_eff,
                    roots=root_clusters(G, S), level='L1')

def silent_is_not_evidence(comm_state, model):
    return model.explicit_failure_likelihood(comm_state) is not None
```

### IP-142 CRL（集体承诺与责任账本）

```python
def collective_commit(cp, fleet, local_ev):
    if not local_ev.gate_ok:
        return ('reject', 'local_evidence')
    if cp.irreversible:
        if any(veto(i, cp) for i in cp.exposed):
            return ('reject', 'local_veto')         # 多数不可翻盘
        if not local_ev.body_cert(cp.actor, cp.tool):
            return ('reject', 'no_local_body_cert')
    if partitioned(fleet) or stale(fleet):
        return local_only_degrade(cp)               # 静默 ≠ 同意
    if not quorum_independent(cp, fleet):
        return ('probe', 'need_independent_witness')
    shares = responsibility_shares(cp, fleet)       # 暴露 × 因果贡献
    return ('commit', ResponsibilityLedger(cp, shares))

def local_only_degrade(cp):
    cp.mode = 'local_only'
    cp.gait = downgrade(cp.gait)                    # 降档
    return ('degrade', cp)
```

### IP-143 FGE（舰队证据门与证书 J_f）

```python
def fleet_evidence_gate(c, fleet, ledger, cap_reg):
    if c.ev == 'EV-probe*':
        ok = (c.inf.cls == 'ID'
              and c.inf.ece_k <= eps_meta(c.k, c.embodiment))
    elif c.ev == 'EV-body':
        C = cap_reg[c.sigma]
        ok = (C.state == 'released' and C.e == c.embodiment
              and C.tool == c.tool)
    elif c.ev == 'EV-peer':
        ok = cross_agent_corroborate(ledger, c.sources, c.level) is not None
    elif c.ev == 'EV-xmodal':
        ok = c.level == 'L1'
    elif c.ev == 'EV-human':
        ok = c.auth >= 'A1' and c.corrob >= quarantine_exit(c.auth)
    elif c.ev in ('EV-visit', 'EV-margin'):
        ok = round57_checks(c, ledger.map)
    else:
        return ('reject', 'no_evidence_class', c)
    if not ok:
        return ('reject', 'evidence_insufficient', c)
    if c.irreversible and c.ev in ('EV-peer', 'EV-xmodal'):
        return ('reject', 'borrowed_evidence_on_irreversible', c)
    return ('ok', c)

def fleet_certificate(Jp, ledger, cap_reg, resp, partition, diversity):
    if not cap_reg.quarantine_closed():
        return ('reject', 'capability_quarantine_open')
    if not ledger.is_dag():
        return ('reject', 'evidence_cycle')
    if diversity.D_pi < D_0 and not diversity.single_root_declared:
        return ('reject', 'monoculture_undeclared')
    if partition.state != 'connected' and not resp.local_only:
        return ('reject', 'partition_unsafe')
    return ('ok', Jf(Jp, ledger, cap_reg, resp, partition, diversity))
```

### IP-144 PCE+++（协作探询与集体 VOI）

```python
def probe_commit_evolve_fleet(x0, fleet, task, budget, personas):
    route = plan_on_map(fleet.map, task, risk_model)
    for cp in route.checkpoints:
        owner = assign_owner(cp, fleet)
        inf = meta_few_shot_infer(fleet.map, cp.region, owner.obs[cp.region], meta)
        n_eff, Dpi, rho = lineage_audit(fleet, cp.region)
        if capability_quarantine(cap_reg[cp.sigma], owner.embodiment, fleet) != 'ok':
            route = downgrade_or_reroute(cp); continue
        sigma = foothold_schedule(x0, cp, fleet.map); R = schedule_risk(sigma)
        while select_gait(R) == 'halt' and budget.fleet_left > 0:
            cands = [(i, p) for i in fleet for p in admissible(i, cp)]
            i, p = argmax(cands, key=lambda z: voi_fleet(z, n_eff, Dpi) - cost(z))
            if voi_fleet((i, p), n_eff, Dpi) < theta_fleet:
                break
            obs = execute_probe(i, p, cap=F_abs)
            ev = add_evidence(ledger, EvidenceEvent(i, p, cp.region, obs, owner.lineage))
            budget.spend(i, p)
            if Dpi < D_0 or suspicious_agreement(ledger, cp.region):
                i2 = most_lineage_distant(fleet, cp, n_eff)
                add_evidence(ledger, EvidenceEvent(i2, heterogeneous_probe(p),
                                                   cp.region, execute_probe(i2, p), i2.lineage))
                budget.spend(i2, 'hetero')
            sigma = reselect_footholds(x0, cp, fleet.map)
            R = schedule_risk(sigma, fleet.map)
        st = fleet_evidence_gate(core_contact(cp), fleet, ledger, cap_reg)
        vote = collective_commit(cp, fleet, st) if st[0] == 'ok' else st
        if vote[0] == 'commit':
            schedule_commit(cp, sigma, vote[1]); continue
        alt = reroute(fleet.map, cp, risk_model)
        if alt and select_gait(schedule_risk(alt, fleet.map)) != 'halt':
            route = alt; continue
        return negotiate_or_stop(cp, fleet, sigma, R, personas,
                                 tau_int=tau_int(personas.active.auth))
    return schedule, ledger, fleet.map
```

### IP-131→PTM-F（操作者×同伴的单向有界信任，继承）

```python
def trust_update(s, ev, source):                    # source ∈ {human, peer}
    s.cal = proper_score_update(s.cal, ev)
    if ev == 'falsified':
        s.auth = demote(s.auth)                     # 降级实时
        s.collateral = max(0, s.collateral - penalty(ev))
    if ev == 'verified':
        s.n_verify += ev.correct
        if s.n_verify >= N_up(s.auth) and s.cal >= theta_cal(s.auth) \
           and upgrade_rate_ok(s):
            s.auth = promote(s.auth)                # 升级慢且有界
    s.w = min(W_MAX_GLOBAL, w0 * s.cal)
    if source == 'peer':
        s.w = min(s.w, W_PEER_MAX)                  # 同伴权重全局更严
    audit.log(s)
    return s
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| ELD | O(\|F\|²·d_ℓ+N_cal²)/区域 | O(\|F\|²) | ρ 上界、n_eff 保守、单文化警报（A41/A45） |
| CQ | O(1)+O(\|𝒟_rev\|) | O(\|C\|·\|F\|) | 状态机完备、撤销可达（A42） |
| EPD | O(\|V\|+\|E\|) 增量 | O(\|V\|+\|E\|) | 根不相交、无环、负证据（A43） |
| CRL | O(\|F\|·\|E_c\|) | O(\|F\|·\|CP\|) | 本地否决、分区默认（A44） |
| FGE | O(\|σ\|·\|F\|) | O(\|σ\|) | 不可逆仅本机证据 |
| PCE+++ | O(\|CP\|·k_f·(C_VOI+\|F\|)) | O(\|V\|+\|σ\|) | 多样性预算单调、k_f 终止 |

**正确性定理（Fleet Institutional Soundness, FIS）**
假设 A33–A40 成立；**(A41)** 谱系声明诚实，`ρ̂_ij` 为真实相关上置信界，n_eff 保守；**(A42)** 能力检疫态机完备，未 released 契约不可进入承诺，撤销沿依赖图可达；**(A43)** 证据 DAG 边集完整，根独立与无环检查诚实；**(A44)** 集体承诺 C1–C4 强制执行，本地否决不可投票覆盖，分区默认 local-only；**(A45)** 多样性契约 `D_π≥D_0` 被监测且单文化警报不失效。则：

1. **相关共识界**：同一谱系簇的一致最多贡献一个独立根；`N` 机一致的有效证人数不超过 `n_eff`，其假信念概率 ≤ 单机界 `+ε_ρ`；且 `n_eff` 对 `ρ̂` 单调不增，估计越保守结论越保守。
2. **能力传染界**：未 released / revoked 的契约不能授权任何承诺；跨具身失败率 ≤ `δ_fwd+P(检疫逃逸)+δ_reval`；撤销传播在单会话内完成，派生承诺全部回溯降级。
3. **非循环互证**：EV-peer 的置信不超过其独立根簇所支持的量；G 完整且无环时，循环引证、转述与证据洗白不能提升置信。
4. **不可逆隔离**：EV-peer/EV-xmodal 仅进入 L1；不可逆层失效率仍由本机 `δ_f+ε_meta(k)+δ_probe+ε_h` 决定，集体治理与同伴证据不增加其赌注。
5. **交互单调性强化**：ELD/CQ/EPD/CRL 只能经 (a) 校准信念更新（含强制加宽）或 (b) 更保守动作参数（降档、绕行、分区退化、否决、检疫拒用）影响系统；多样性预算只消耗探针，不放松安全界。
6. **终止性**：每检查点 PCE+++ 在 `k_probes+k_cons+k_fleet` 内终止于 {承诺, 绕行, L2 协商, 安全停}。

**部署界（对检查点取联合界）**：

```
P_safe ≥ 1 − Σ_cp (δ_f + ε_meta(k) + δ_probe + ε_h + δ_ood·α_conf)
             − P(ρ 低估)·P_false_consensus
             − P(检疫逃逸) − P(G 不完整) − P(分区误判)
             − P(D_π 监测失效)·P_shared_blindspot
```

关键：**人数不是证据**——先折算血缘再谈一致；**能力不是标签**——先过检疫再谈复用；**协作不是投票**——先溯源、再分割责任、再保留否决；**通用不是免费**——世界信念可借，具身兑现必须本地重挣。

## 4. 实验设计 E177–E182

| 实验 | 指标 | 目标 |
|---|---|---|
| E177 认知血缘与相关折价 | ρ∈{0,0.5,0.9,1} 的舰队假信念率、n_eff 估计误差；同主干 vs 异构谱系 | ρ=1 退化为单机；n_eff 误差 ≤15%；假共识 ↓≥70% vs 朴素投票 |
| E178 认知多样性预算 | D_π vs 探针预算；单文化崩塌率；共享盲区检出率 | 维持 D_π≥D_0 额外探针 ≤20%；盲区检出 ↑≥50% |
| E179 能力检疫与跨具身 | 未 released 误授权数；跨体迁移失败率；撤销传播时延；负迁移检出率 | 0 次误授权；失败率 ≤1%；撤销 ≤1 会话；负迁移检出 ≥90% |
| E180 证据溯源与循环互证 | 循环引证/转述/洗白攻击检出率；EV-peer 越级 L2 次数；根集冲突检出率 | 检出 ≥95%；越级 0；冲突检出 ≥95% |
| E181 集体承诺与分区 | 本地否决正确率；分区安全停/降档率；责任账本一致率；联合假承诺率 | 不可逆否决 100%；静默不视为同意；联合假承诺 ≤1% |
| E182 端到端异构机队 | 异构四足/工具/模型版本 vs 第 57 轮单机、朴素舰队：成功率/探针数/首访时延/不可逆假承诺 | +10%/−30%/−20%/0 次 |

## 5. 集成更新：v16** → v16*** 体系

```
根信任 + 能力格
│
├─ L0 分布式底座与执行边 (GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX,XFR,CRC,SFE,FDR,RAB,DST,SBC)
├─ L0.5+ 鲁棒性层 (TRO,RXC,RCO,REX,RTA,TRC,RUR)
├─ L0.5++ 动作-协同层 (ACS,SCOM,CEC,AEC,JTC)
├─ L0.5* 证据-交互层 (SMM,PCE,BVK,ISE,TAF,MEC)
├─ L0.5*⁺ 元认知-信任层 (MFSL,XMC,PTM,MXI,FSE,J_p)
├─ L0.5*⁺⁺ 认知-协作制度层 (ELD,CQ,EPD,CRL,FGE,J_f) ← v58 新增
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
...
└─ L6 原型证伪/XFER/LFF/IXD
```

JCPS 输出扩展为：
`(v,a,m,q,ι,κ,g,λ,τ,σ,ρ,Explain,RUR_state,α_S,A_cert,γ_ce,δ_a,Σ/C+ 结构,𝓜_core,J_m,probe_log,consent_state,w_h,q_φ/k*,D(r),ρ_ℳ,s_op/auth,m_E,ood_state,J_p, ℓ_i,n_eff,D_π, G/root_clusters, Q(C_σ), {λ_i}, partition_state, veto_log, J_f)`

其中新增：`ℓ_i` 认知血缘；`n_eff` 有效独立见证数；`D_π` 先验多样性；`G/root_clusters` 证据溯源 DAG 与独立根簇；`Q(C_σ)` 能力检疫状态；`{λ_i}` 责任份额；`partition_state` 通信分区状态；`veto_log` 本地否决日志；`J_f` 舰队证书。

云边协议 CEB++ → **CEB+++**：云端可下发基础模型/元模型增量，但**舰队级更新视为一次能力发布**——必须带血缘清单（训练分片、仿真器版本、校准谱系）进入检疫区，先在影子模式与哨兵机体上运行，通过"校准不劣化 ∧ 跨具身簇/谱系簇独立验证 ∧ 无循环证据依赖"后才允许接管承诺判定；边端回传共享区域残差用于 ρ 估计、回传证伪事件用于能力撤销与语料补盲。**任何全队同步更新不得绕过检疫，也不得把同步后的"一致"当作独立证据。**

## 6. 本轮最大风险

**一句话**：本轮把安全托付给机队的"证据制度"，而制度最脆弱的假设是**血缘可观测**——一旦训练数据、仿真器、传感器批次与校准谱系无法诚实披露或审计，机队就会把同源的 N 个错误当成 N 个独立证人，在"多样性已维护"的假象下比单机更快、更一致地踏进同一个盲区；因此必须以相关上界、无环溯源、能力检疫、本地否决与异源复探五重护栏，宁可承认"我们只有一个证人"，绝不把人数当证据。
