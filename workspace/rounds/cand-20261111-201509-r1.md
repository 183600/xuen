# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 56 轮（承接第 55 轮「语义-接触接地与全身生存核」IP-121~126；灵感循环第 2 轮；本轮灵感：「四足机器人」×「交互设计」×「语义地图」）

> 第 55 轮把"感知标签"升级为"接触约束"，用生存核 + 护盾 + 证书把语义不确定性挡在不可逆接触之前；但它的风险自陈已点出软肋——soundness 三重依赖分割置信校准、κ 跨域迁移、核外近似紧致，而护盾面对不确定性只有两个动作：**保守或制动**，缺少第三个动作"把不确定性变少"；且语义 Σ 是单帧的，每次到访都从零支付全部不确定性。本轮三个灵感各补一条腿：**四足机器人**给探询一个物理载体（闲着的腿就是传感器，步态就是裕度的变速箱），**交互设计**给拒绝一个出口（可读、分级、有界的人类影响），**语义地图**给证据一个居所（持久、溯源、可积累、可版本化的信念载体）。核心命题由"模型说可信"升级为 **"证据说可信"**。

核心矛盾：
- **H24**：第 55 轮的可行性判定建立在"单帧置信"之上，而置信不是证据——边界处一次过度自信的分割足以让护盾在伪生存核内放行；系统只能被动容忍不确定性，不能主动交易它。
- **H25**：无人参与的安全系统在部署上不可持续——只会急停且说不清为什么的机器人会被操作者绕过或关机；但人类影响若无界，又把新的单点故障引入安全回路。交互设计的要求恰是"**可读但有界**"。

## 0. 直觉与动机

**灵感 1（四足机器人 → 探询成为第一类动作，步态是不确定性变速箱）**
直觉：四足 crawl 步态天然三点支撑、闲出一条腿——这条腿不只是备用支撑，更是 **仪器**：轻点（tap）测滑移与刚度、偏载（shift）在非完全承诺下预支部分体重、换视角（view）补一次分割。于是动作空间从纯运动扩为 **运动 × 探询 × 沟通** 三元组。更妙的是步态与不确定性之间存在天然兑换率：crawl 静态裕度大、可吸收单点失误但慢；trot 动态、快但每个接触都不可失——**步态就是不确定性预算的变速箱**：语义风险高 → 降档买裕度；证据到位 → 升档买速度。

**灵感 2（交互设计 → 拒绝必须可读，人类影响必须有界）**
直觉：护盾的每次拒绝/降档/绕行都必须输出 **接地解释**——指认地图区域、信念摘要、被违反的约束，而不是一句 "infeasible"。同意按（风险 × 可逆性）矩阵分级：常规步态 L0 自动、中等风险 L1 异步通知、不可逆高险接触 L2 同步确认且超时保守停。人类的角色被严格限定为 **证据提供者而非决策者**：标注只能以有界权重进入信念，决策规则本体不可触碰——人可以让系统"知道得更多"，不能让系统"更冒险"。

**灵感 3（语义地图 → 从单帧 Σ 到持久 𝓜：证据有了居所）**
直觉：地图让语义 **跨到访积累**：区域信念 `b_r` 由边端探针、云端先验、人类标注三方证据贝叶斯融合，带溯源（到访次数/最近时间/来源集）、带陈旧衰减、带版本。地图同时是 **交互界面**（人读图、标图）与 **云边共享对象**（版本化同步）。第 55 轮"κ 跨域迁移"的风险由此获得结构性缓解：不再盲信迁移来的可供性，而是用本地探针与多次到访把 κ 长成区域自己的后验。

**灵感 4（三源证据 + 证据门 → 从"模型置信"到"证据承诺"）**
直觉：第 55 轮承诺接触的依据是模型置信（conf ≥ θ_conf），一次过度自信就击穿。本轮立 **证据门**：每个被承诺的接触必须挂证据类 `EV-probe / EV-visit / EV-margin / EV-human` 之一——探针实证、多访融合、足额裕度、或经校准操作者且获佐证的标注。击穿安全需要三层同时失守（模型误校准 ∧ 无探针无裕度 ∧ 人也错），防御从单层变为纵深。

**灵感 5（探-诺-演 PCE → 把信息价值写进控制回路）**
直觉：每个检查点上，排程风险 ≤ δ_f 则承诺；否则选"VOI 扣除代价后最大"的探针，探完融合、重估、再决策；探不动则绕行，绕不动则降档，降不动则 L2 协商或安全停。不确定性不再只是被容忍的对象，而是被 **交易** 的对象——用时间与能量买信息，用信息买承诺。

## 1. 形式化定义（增量：定义 127–132）

**定义 127（语义-可供性地图）** `𝓜 = (G, {b_r}, κ_𝓜, prov, ver)`：拓扑图 `G=(V,E)`；区域信念 `b_r` 为标签与接触参数 `(μ, k, F_bear)` 的后验；`κ_𝓜(r,c)=P(接触 c 成功 | b_r)`；溯源 `prov(r)=(n_visits, t_last, src_set)`；证据源 `E = E_seg ∪ E_probe ∪ E_cloud ∪ E_human`，融合 `b_r ← Bayes(b_r, like(e), w(src))`，人类权重 `w_h ≤ w_max` 且随操作者校准分衰减。

**定义 128（探询动作与非破坏性公理）** `A = A_loco × A_epis × A_comm`；探针 `π ∈ {view, tap, shift, revisit}`，各有代价 `(τ_p, e_p)` 与似然模型 `p(e | r, θ_true)`。非破坏性：`F_probe ≤ F_abs` 且 `P(探针自身引发失效) ≤ δ_probe`——探针必须不改写它要测量的世界。

**定义 129（信念空间生存核）** 接触排程 `σ = {(r_i, p_i, F_i)}`，`P_fail(r,p,F) = P(μ_r < μ_req(F) ∨ F_bear(r) < F_peak ∨ m_s(p) < θ_m | b_r)`。机会约束可行：`viable_b(x,σ,𝓜) ⇔ ∀i: P_fail ≤ δ_f(g) ∧ 全身动力学可行 ∧ x∈𝒳_safe`；`K_B(𝓜) = {x | ∃σ: viable_b}`。步态预算 `δ_f(g)` 随动态性单调递减：`δ_f(crawl) ≥ δ_f(pace) ≥ δ_f(trot) ≥ δ_f(bound)`。

**定义 130（探-诺-演策略 PCE）** 每检查点决策：承诺 ⇔ ∃g 使 `R(σ) ≤ δ_f(g)`（取最快满足者）；否则选 `argmax_π [VOI(π) − cost(π)] ≥ θ_voi` 的探针，探 + 融合 + 重估；探尽 → 绕行；绕尽 → 降档；降尽 → L2 协商或安全停。探针预算 `k_probes` 保证终止。

**定义 131（交互契约）** 同意阶梯 L0（低险可逆，自动）/ L1（异步通知，不阻塞）/ L2（同步确认，超时保守停）；接地解释 `Exp = (r, b_r 摘要, 违反约束, 裕度, 建议动作{确认/绕行/标注})`；标注隔离区：新标注挂起，待一次探针或到访佐证后生效；**决策规则与人类输入隔离**，人类只经有界信念更新起作用。

**定义 132（地图-证据证书 J_m）** `J_m = (𝓜_core, C_core, K_margin, ρ_sem, δ_s, probe_log, consent_log, evidence)`；每个承诺接触必须带证据类（无类即拒绝）；继承第 55 轮 SCC 全部检查（`K_margin ≥ θ_K`、`ρ_sem ≥ ρ_min`、`δ_s < Θ_s`、置信校准）；同意日志完备（每个 L2 有决议）。

## 2. 关键算法伪代码（完整版见产物区）

### IP-127 SMM（Semantic Map Maintenance）

```python
def map_fuse(M, batch):
    for e in batch:                                  # e=(region,type,payload,t,src)
        r = e.region
        if e.type == 'human':                        # A35: 有界 + 隔离
            if not M.quarantine[r].admit(e):
                M.quarantine[r].hold(e); continue    # 待一次探针/到访佐证后生效
            like, w = human_likelihood(e), min(w_max, w_h(e.src.cal))
        elif e.type == 'probe':
            like, w = probe_likelihood(e), 1.0
        elif e.type == 'seg':                        # 第 55 轮 SCG 单帧输出入图
            like, w = seg_likelihood(e), w_seg(e.conf)
        else:
            like, w = cloud_prior(e), w_cloud(e.ver)
        M.b[r] = staleness_decay(bayes_update(M.b[r], like, w), age(e, M.prov[r]))
        M.prov[r] = touch(M.prov[r], e)              # n_visits / t_last / src_set
    return M, changed(M, batch)
```

### IP-128 PCE（Probe-Commit-Evolve，含不确定性变速箱）

```python
def probe_commit_evolve(x0, M, task, budget, consent):
    route = plan_on_map(M, task, risk_model)         # 拓扑图上的风险感知路径
    sched, log = [], []
    for cp in route.checkpoints:
        sigma = foothold_schedule(x0, cp, M); R = schedule_risk(sigma, M)
        while select_gait(R) == 'halt' and budget.probes_left > 0:
            cands = admissible_probes(cp, M, F_abs)  # 非破坏性过滤（A34）
            if not cands: break
            p = argmax(cands, key=lambda q: voi(q, M, R) - cost(q))
            if voi(p, M, R) < theta_voi: break
            M, _ = map_fuse(M, [execute_probe(p, cap=F_abs)])
            sigma = reselect_footholds(x0, cp, M); R = schedule_risk(sigma, M)
            budget.spend(p)
        g = select_gait(R)                           # 变速箱: R≤δ_f(g) 的最快步态
        if g != 'halt':
            sched.append(commit(sigma, g)); log.append(tag_evidence(sigma, M)); continue
        alt = reroute(M, cp, risk_model)
        if alt and select_gait(schedule_risk(alt, M)) != 'halt': route = alt; continue
        return negotiate_or_stop(cp, M, sigma, R, consent)   # L2 协商 / 安全停+解释
    return sched, log, M
```

### IP-130 ISE（Interaction Safety Envelope）

```python
def interaction_shield(u_nom, x, M, sched, consent):
    u, st = semantic_shield(u_nom, x, K_in, C_plus, W)    # 第 55 轮 SSF 为底座
    failc = failing_constraint(x, u, sched, M)
    if st != 'ok' or risk(u) > consent.threshold(failc):
        exp = grounded_explanation(M, sched, failc)       # 指认区域+信念+违反约束
        lvl = consent.level(failc, u)                     # 风险×可逆性 → L0/L1/L2
        if lvl == 'L2' and not confirm(exp, timeout=tau_int):
            return safe_brake(x), exp, 'L2_denied_or_timeout'
        if lvl == 'L1': notify(exp)                       # 异步，不阻塞节拍
    return u, exp_if_any, st
```

## 3. 复杂度与正确性（要点）

| 组件 | 时间 | 空间 | 正确性关键 |
|---|---|---|---|
| SMM | O(|ΔE|·d_r) 增量 | O(|V|·d_b) | 源权重诚实、融合保校准 |
| PCE | O(|CP|·k_p·(C_VOI+|E|)) | O(|V|+|σ|) | 悲观 VOI、k_p 预算终止 |
| BVK | O(N_sc·T_dyn+QP-SOCP) | O(|X|+|σ|) | 机会约束内近似 sound、δ_f(g) 单调 |
| ISE | O(QP)+O(1) | O(|Exp|) | 拒绝必有接地解释、超时保守停 |
| TAF | O(1)+O(H_op) | O(|标注|) | w_h 有界、隔离区延迟生效 |
| MEC | O(|σ|+|probe_log|) | O(|σ|) | 无证据类即拒绝、L2 日志完备 |

**正确性定理（Evidence-Grounded Commitment Soundness）**：在 A29–A32 基础上加 **(A33)** 融合后区域信念校准（ECE ≤ ε_cal）且融合保校准；**(A34)** 探针似然诚实且非破坏；**(A35)** `w_h ≤ w_max`、标注隔离、决策规则与人类输入隔离；**(A36)** 交互时延 ≤ τ_int、超时保守停。则：(i) 承诺接触经验失效率 `≤ δ_f + ε_cal + δ_probe + ε_h(w_max)`；(ii) **安全单调引理**：交互与探针只能经信念更新或触发更保守动作影响系统，不存在升险交互路径；(iii) PCE 在 `k_probes` 内终止于 {承诺, 绕行, 协商, 安全停} 之一。

## 4. 实验设计 E167–E171

| 实验 | 指标 | 目标 |
|---|---|---|
| E167 地图融合校准与抗污染 | 多访融合 ECE；注入 20% 错误标注后承诺失效率增幅 | ECE ≤ 0.05；增幅 ≤ 1% |
| E168 探询效率与非破坏性 | 每探针风险降幅 vs 随机探针；探针致损次数；时延开销 | ≥ 2×；0 次；≤ 15% |
| E169 证据门承诺健全性 | 承诺接触失效率 vs δ_f=0.05；假承诺率；vs 第 55 轮置信基线 | ≤ 0.06；≤ 2%；降幅 ≥ 50% |
| E170 交互质量与时延 | 解释可读性；校准操作者标注精度；L2 P95；超时安全停成功率 | ≥ 0.8；≥ 0.85；≤ 300ms；100% |
| E171 端到端四足部署 | 成功率 / 跌倒率 / 完成时间 / 降档恰当率 vs 第 55 轮基线 | +10% / −40% / ≤ +20% / ≥ 90% |

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 探针非破坏假设被打破（薄冰上轻点即塌） | 高 | 绝对力帽 F_abs + 承载下界预检 + 不可逆性审计 |
| 高置信错误标注污染持久地图 | 高 | 标注隔离区 + 校准权重 w_h ≤ w_max + 佐证生效 |
| VOI 依赖同一可能失准的信念模型（循环性） | 中 | 悲观 VOI（信念方差悲观界）+ 探后校验 |
| 地图陈旧："旧证据"放行今日风险 | 中 | 陈旧半衰期 + 高险区域强制重探 |
| L2 警报疲劳 → 无脑确认 | 中 | 解释分级 + 确认率监控 + 超阈回退保守停 |

## 6. 本轮最大风险

**一句话**：本轮把安全的赌注从"模型置信"换到"证据质量"，但地图的持久性让坏证据长寿——一根在薄冰上"非破坏"轻点即塌的探针、或一条高置信错误的人工标注，会在隔离与衰减护栏生效前污染区域信念，并经多访融合把局部错误放大为全图系统性偏差，使之后所有证据门都"诚实地为坏证据放行"——因此必须以 **探针绝对力帽+不可逆审计、标注隔离区+校准权重、溯源版本+陈旧衰减** 三重护栏，宁可重访重探，绝不采信"无溯源的确定"。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 56 轮产物 · 创新点清单 v32：MapProbe-Negotiate（证据地图×主动探询×信任协商，SMM×PCE×BVK×ISE×TAF×MEC）

> 承接第 55 轮 IP-121~126（SCG/WBV/SSF/SCC/SRS/CEB）与第 54 轮 v31 云边动作体系。本轮把部署前提从"模型置信"升级为 **"证据承诺"**：语义从单帧 Σ 升级为持久地图 𝓜，动作从纯运动升级为 **运动×探询×沟通** 三元组，护盾从单边保守升级为 **探-诺-演协商闭环**，人类以有界、经校准、可审计的方式进入安全回路。
> IP 编号：IP-127~IP-132（共 6 个新增），升级 IP-121/123/124/126 以纳入地图信念与交互维度。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-127 | SMM Semantic Map Maintenance | 新增 | 区域信念 `b_r` 三源贝叶斯融合 + 溯源/陈旧/版本 |
| IP-128 | PCE Probe-Commit-Evolve | 新增 | 检查点 VOI 探询 + 承诺/绕行/降档/协商四态决策 |
| IP-129 | BVK Belief Viability Kernel | 升级 IP-122/124 | 机会约束生存核 + 步态不确定性变速箱 `δ_f(g)` |
| IP-130 | ISE Interaction Safety Envelope | 升级 IP-123 | 护盾 + 同意阶梯 + 接地解释 + 超时保守停 |
| IP-131 | TAF Trust-calibrated Annotation Fusion | 新增 | 操作者校准权重 + 标注隔离区 + 审计日志 |
| IP-132 | MEC Map-Evidence Certificate | 升级 IP-124 | 证据门 `EV-probe/visit/margin/human` + L2 日志完备 |

## 1. 符号体系增量（定义 127–132）

| 符号 | 含义 |
|---|---|
| `𝓜 = (G,{b_r},κ_𝓜,prov,ver)` | 语义-可供性地图（拓扑图/区域信念/可供性/溯源/版本） |
| `b_r` | 区域 r 上 (标签, μ, k, F_bear) 的后验 |
| `A = A_loco × A_epis × A_comm` | 动作三元组：运动 × 探询 × 沟通 |
| `π ∈ {view,tap,shift,revisit}` | 探针（代价 τ_p,e_p；似然 p(e\|r,θ_true)） |
| `F_abs, δ_probe` | 探针绝对力帽与探针致失效上界（非破坏性公理） |
| `P_fail(r,p,F)` | 信念导出的接触失效概率 |
| `δ_f(g)` | 步态 g 的失效率预算，crawl ≥ pace ≥ trot ≥ bound |
| `VOI(π)` | 探针信息价值（悲观界） |
| `L0/L1/L2` | 同意阶梯（自动/通知/确认） |
| `Exp` | 接地解释对象（区域+信念+违反约束+建议动作） |
| `w_h ≤ w_max` | 人类标注权重上界，随操作者校准分衰减 |
| `EV-probe/visit/margin/human` | 证据门四类 |
| `J_m` | 地图-证据证书 |

## 2. 关键算法伪代码

### IP-127 SMM（Semantic Map Maintenance）

```python
def map_fuse(M, batch):
    changed = []
    for e in batch:                                   # e=(region,type,payload,t,src)
        r = e.region
        if e.type == 'human':                         # A35: 有界 + 隔离
            if not M.quarantine[r].admit(e, op_cal=e.src.cal):
                M.quarantine[r].hold(e); continue     # 待一次 probe/visit 佐证后生效
            like, w = human_likelihood(e), min(w_max, w_h(e.src.cal))
        elif e.type == 'probe':                       # A34: 探针证据权重最高
            like, w = probe_likelihood(e), 1.0
        elif e.type == 'seg':                         # 第 55 轮 SCG 单帧输出入图
            like, w = seg_likelihood(e), w_seg(e.conf)
        else:                                         # E_cloud: 云端先验（带版本）
            like, w = cloud_prior(e), w_cloud(e.ver)
        post = bayes_update(M.b[r], like, weight=w)
        M.b[r] = staleness_decay(post, age=t_now - M.prov[r].t_last, half=tau_stale)
        M.prov[r] = touch(M.prov[r], e)               # n_visits / t_last / src_set
        M.ver.bump(r); changed.append(r)
    return M, changed

def staleness_gate(M, r, now):
    return (now - M.prov[r].t_last <= tau_stale) or risk_class(r) == 'low'
```

### IP-128 PCE（Probe-Commit-Evolve，含不确定性变速箱）

```python
def select_gait(R):
    for g in ['trot', 'pace', 'crawl']:               # 由快到慢
        if R <= delta_f_of_gait(g): return g          # δ_f: trot < pace < crawl
    return 'halt'                                     # 全部超预算：停

def probe_commit_evolve(x0, M, task, budget, consent):
    route = plan_on_map(M, task, risk_model)          # 拓扑图上的风险感知 A*
    sched, log = [], []
    for cp in route.checkpoints:
        if not staleness_gate(M, cp.region, t_now):   # 陈旧区域先补一次 view
            M, _ = map_fuse(M, [execute_probe(view_probe(cp.region), cap=F_abs)])
        sigma = foothold_schedule(x0, cp, M)          # 步态+落脚点候选（可达集内）
        R = schedule_risk(sigma, M)                   # Σ_i P_fail(r_i,p_i,F_i)
        while select_gait(R) == 'halt' and budget.probes_left > 0:
            cands = admissible_probes(cp, M, F_abs)   # 非破坏性过滤（A34）
            if not cands: break
            p = argmax(cands, key=lambda q: voi_pessimistic(q, M, R) - cost(q))
            if voi_pessimistic(p, M, R) < theta_voi: break
            M, _ = map_fuse(M, [execute_probe(p, cap=F_abs)])
            sigma = reselect_footholds(x0, cp, M); R = schedule_risk(sigma, M)
            budget.spend(p)
        g = select_gait(R)
        if g != 'halt':
            sched.append(commit(sigma, g))
            log.append(tag_evidence(sigma, M))        # 打证据类标签
            continue
        alt = reroute(M, cp, risk_model)
        if alt and select_gait(schedule_risk(alt, M)) != 'halt':
            route = alt; continue
        return negotiate_or_stop(cp, M, sigma, R, consent)   # L2 协商 / 安全停
    return sched, log, M
```

### IP-129 BVK（信念空间生存核 + 机会约束）

```python
def belief_viability(x, sigma, M, gait):
    delta_f = delta_f_of_gait(gait)
    pf_max = 0.0
    for (r, p, F) in sigma:
        mu_req = friction_demand(F, posture(x))
        pf = P_post(M.b[r], mu_r < mu_req or F_bear_r < F.peak or m_s(p) < theta_m)
        pf_max = max(pf_max, pf)
        if pf > delta_f: return KernelInfeasible(pf)
    feas, u, lam = solve_contact_dynamics(x, sigma, FC(mu_lower_conf(M, sigma)))
    return KernelApprox(feas=feas, pf_max=pf_max,
                        margin=dist_to_chance_boundary(x, sigma, M))
# K_in/K_out：机会约束经 Cantelli/场景近似凸化（SOCP）；外近似仍须 sound（A30 继承）
```

### IP-130 ISE（Interaction Safety Envelope）

```python
def consent_level(failc, u):
    if failc is None and reversibility(u) == 'high': return 'L0'      # 自动
    if failc.risk <= theta_L1 or reversibility(u) == 'high': return 'L1'
    return 'L2'                                                       # 不可逆/高险

def interaction_shield(u_nom, x, M, sched, consent):
    u, st = semantic_shield(u_nom, x, K_in, C_plus, W)   # 第 55 轮 SSF 为底座
    failc = failing_constraint(x, u, sched, M)
    if st != 'ok' or risk(u) > consent.threshold(failc):
        exp = grounded_explanation(M, sched, failc)      # Exp=(r,b_r,违反约束,裕度,建议)
        lvl = consent_level(failc, u)
        if lvl == 'L2':
            ok = confirm_request(exp, timeout=tau_int)   # A36: 时延上界
            if not ok: return safe_brake(x), exp, 'L2_denied_or_timeout'
        elif lvl == 'L1': notify(exp)                    # 异步，不阻塞节拍
    return u, exp_if_any, st
```

### IP-131 TAF（Trust-calibrated Annotation Fusion）

```python
def trust_fuse(M, ann, op_hist, audit):
    cal = calibration_score(op_hist)                     # 历史标注 vs 事后探针/实测
    w_h = min(w_max, w0 * cal)                           # A35: 影响有界
    e = annotation_evidence(ann, weight=w_h)
    M, chg = map_fuse(M, [e])
    M.quarantine[ann.region].hold(ann)                   # 佐证前不参与承诺判定
    audit.append((ann, ann.op, cal, t_now))              # 可审计
    return M, chg
```

### IP-132 MEC（Map-Evidence Certificate）

```python
def map_evidence_certificate(sched, log, M, consent_log, budgets):
    for c in contacts(sched):
        if   c.ev == 'EV-probe':  ok = c.probe.passed and c.probe.nondestructive
        elif c.ev == 'EV-visit':  ok = M.prov[c.region].n_visits >= k_v
        elif c.ev == 'EV-margin': ok = c.m_s >= theta_m_strict
        elif c.ev == 'EV-human':  ok = c.op_cal >= theta_cal and c.corroborated
        else: return ('reject', 'no_evidence_class', c)  # 证据门：无证据不承诺
        if not ok: return ('reject', 'evidence_insufficient', c)
    if min(x.K_margin for x in sched) < budgets.theta_K: return ('reject', 'K_margin')
    if rho_sem(sched, M) < budgets.rho_min:              return ('reject', 'rho_sem')
    if semantic_perturbation(M.core) > budgets.Theta_s:  return ('reject', 'delta_s')
    if not all(l2.resolved for l2 in consent_log):       return ('reject', 'consent_open')
    return ('ok', MapCert(M.core, core_contacts(sched), K_margin, rho_sem,
                          delta_s, probe_log, consent_log))
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| SMM | O(\|ΔE\|·d_r) 增量 | O(\|V\|·d_b) | 源权重诚实、融合保校准（A33） |
| PCE | O(\|CP\|·k_p·(C_VOI+\|E\|)+\|CP\|·A*) | O(\|V\|+\|σ\|) | 悲观 VOI、k_p 终止、四态完备 |
| BVK | O(N_sc·T_dyn + QP-SOCP) | O(\|X\|+\|σ\|) | 机会约束内近似 sound、δ_f(g) 单调（A29 继承） |
| ISE | O(QP)+O(1) | O(\|Exp\|) | 拒绝必有接地解释、超时保守停（A36） |
| TAF | O(1)+O(H_op) | O(\|标注\|) | w_h ≤ w_max、隔离区延迟生效（A35） |
| MEC | O(\|σ\|+\|probe_log\|) | O(\|σ\|) | 无证据类即拒绝、L2 日志完备 |

**正确性定理（Evidence-Grounded Commitment Soundness, EGCS）**
假设 A22–A28（第 53/54 轮）、A29–A32（第 55 轮）成立；**(A33)** 融合后区域信念校准 `ECE ≤ ε_cal` 且融合算子保校准（共轭/加权似然 + 诚实源权重）；**(A34)** 探针似然诚实且非破坏（`F_probe ≤ F_abs`，`P(探针致失效) ≤ δ_probe`）；**(A35)** `w_h ≤ w_max`、标注隔离、决策规则与人类输入隔离；**(A36)** 交互时延 `≤ τ_int` 且超时触发保守停。则：

1. **承诺健全性**：PCE 承诺的每个接触满足 `P(fail) ≤ δ_f + ε_cal + δ_probe + ε_h(w_max)`；
2. **交互单调性**：任何 L1/L2/探针路径只经（a）有界信念更新或（b）触发更保守动作影响系统，不存在升险交互路径；
3. **终止性**：PCE 在每检查点 `k_probes` 内终止于 {承诺, 绕行, L2 协商, 安全停}；
4. **部署界**（对检查点取联合界）：

```
P_safe ≥ 1 − Σ_cp (δ_f + ε_cal + δ_probe + ε_h)
             − P(𝓜 陈旧 > τ_stale 未检出) − P(护盾回退失败) − P(τ_int 超时 ∧ 安全停失效)
```

关键：**证据门使单点过度自信不再足以产生承诺**（模型误校准 ∧ 无探针无裕度 ∧ 人也错，三层同时失守才会击穿）；**决策规则固定而信念流动**（人/云/探针只能改信念，不能改规则）；**护盾兜底与超时保守停继承第 55 轮 A30/A32**。

## 4. 实验设计 E167–E171

| 实验 | 指标 | 目标 |
|---|---|---|
| E167 地图融合校准与抗污染 | 多访融合 ECE；注入 20% 错误标注后承诺失效率增幅 | ECE ≤ 0.05；增幅 ≤ 1% |
| E168 探询效率与非破坏性 | 每探针风险降幅 vs 随机探针；探针致损次数；时延开销 | ≥ 2×；0 次；≤ 15% |
| E169 证据门承诺健全性 | 承诺接触失效率 vs δ_f=0.05；假承诺率；vs 第 55 轮置信基线 | ≤ 0.06；≤ 2%；降幅 ≥ 50% |
| E170 交互质量与时延 | 解释可读性；校准操作者标注精度；L2 P95；超时安全停成功率 | ≥ 0.8；≥ 0.85；≤ 300ms；100% |
| E171 端到端四足部署 | 成功率 / 跌倒率 / 完成时间 / 降档恰当率 vs 第 55 轮基线 | +10% / −40% / ≤ +20% / ≥ 90% |

## 5. 集成更新：v16++ → v16* 体系

```
根信任 + 能力格
│
├─ L0 分布式底座与执行边 (GPC/SEN/TBC)
├─ L0.5 任务迁移与仿真证据 (TIX,XFR,CRC,SFE,FDR,RAB,DST,SBC)
├─ L0.5+ 鲁棒性层 (TRO,RXC,RCO,REX,RTA,TRC,RUR)
├─ L0.5++ 动作-协同层 (ACS,SCOM,CEC,AEC,JTC)
├─ L0.5* 证据-交互层 (SMM,PCE,BVK,ISE,TAF,MEC) ← v56 新增
├─ L1 几何感知
├─ L2 任务/上下文/记忆/语音
...
└─ L6 原型证伪/XFER/LFF/IXD
```

JCPS 输出扩展为：
`(v,a,m,q,ι,κ,g,λ,τ,σ,ρ,Explain,RUR_state,α_S,A_cert,γ_ce,δ_a, Σ/C+ 结构, 𝓜_core, J_m, probe_log, consent_state, w_h)`

其中新增：`𝓜_core` 地图核心区信念与溯源；`J_m` 地图-证据证书；`probe_log` 探针证据日志；`consent_state` 同意阶梯状态；`w_h` 人类标注权重。

云边协议升级：第 55 轮 CEB（IP-126）→ **CEB+**：边界重剖分不再直接改 Σ，而是作为带版本号的地图证据写入 𝓜（与探针/人工标注同走 SMM 融合与隔离逻辑）；云端可下发 **探针建议**（哪片区域值得先探），边端回传 probe_log 作为云端先验的校准集。

## 6. 本轮最大风险

**一句话**：证据地图-探询-协商把安全赌注从"模型置信"换成"证据质量"，但地图的持久性使坏证据长寿——一次被"非破坏"假设掩盖的破坏性探针或一条高置信错误标注，会在隔离与衰减护栏生效前污染区域信念、并经多访融合放大为全图系统性偏差，让之后所有证据门都"诚实地为坏证据放行"；必须以探针力帽+不可逆审计、标注隔离+校准权重、溯源版本+陈旧衰减三重护栏，宁可重访重探，绝不采信"无溯源的确定"。
<!-- ARTIFACT:END -->
