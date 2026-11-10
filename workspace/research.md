# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 46 轮（承接第 45 轮 v10；本轮灵感：双臂协作 × 传感器融合） · BiFuse-Cert：双臂相对姿态证书 × 认证异步多传感器融合的协作过程保证（四层架构 v11）

> 承接第 45 轮 v10 Energy-Context-Depth。v10 用能量租约、上下文预测与深度门控守住了“感知是否可用、姿态证书是否覆盖”，但隐含假设 H5：只有一个操作臂，且各传感器被视作**独立、时间同步、可单独认证**的观测源。UniBot 是双臂平台：抓取-交接-协同搬运中，安全量不再是两个臂各自在世界系里的位姿盒，而是两臂之间的**相对位姿** T_rel；单臂各自 sound 的证书叠加，相对误差仍可能被放大。同时 RGB、深度、关节编码器、力矩/触觉以不同频率与延迟到达，融合结果若未经时间对齐与交叉一致性认证，会给出比真值更窄的半径。两个灵感词精确命中 H5：**双臂协作**把证书对象从“绝对位姿”扩展为“相对位姿 + 闭链一致性”，并让一臂的证书失效级联到另一臂的安全谓词；**传感器融合**把“条件覆盖”升级为“认证融合”，必须同时认证时间对齐、创新一致性与跨源交叉覆盖。二者耦合出新问题：**如何让融合出的相对姿态证书在异步、异构、可能交叉不一致的传感器流下保持 sound，并防止闭链过约束与共模偏差让双臂协作在“两个单臂证书都有效”的表象下静默越界**。

## 0. 直觉与动机

**灵感 1（双臂协作 → 相对姿态证书与闭链一致性）**
直觉：交接水杯时，决定成败的是“两爪相对位置/朝向”，不是各自在世界系里有多准。设两臂端帧 A、B，相对变换 T_rel=T_A^{-1}T_B。世界系独立证书只给保守界 rad(P_rel)≤rad(P_A)+rad(P_B)，在两者共享同一底盘/定位共模误差时，这个界既可能过松（浪费）也可能因错误地假设独立而过窄（危险）。因此必须**直接在相对变换数据上共形校准**相对证书 P_rel，并把闭链约束单独认证：双爪刚性抓同一物体时，T_A^{-1}T_B 应接近固定 T_grasp；若相对证书宽度超过闭链容差 ε_cl，就说明“刚性双臂”假设不成立，必须降级为柔顺或单臂，而不是继续按刚性链放行。

**灵感 2（传感器融合 → 认证融合而非简单融合）**
直觉：融合不是把协方差一加。真正伤人的是**时间不对齐**与**交叉不一致**：深度帧晚到 30ms，快速运动下直接引入 L_v·ε_ts 的位置误差；某路传感器被遮挡/反光时，其“名义协方差”仍然很小，融合反而被坏源拖窄。认证融合要求四件事同时成立：(a) 每个源的覆盖证书本身有效；(b) 时间对齐误差 ε_ts 有上界并计入半径 r_fuse=r_stat+L_v·ε_ts+r_quant；(c) 创新残差马氏距离超过 χ² 门限即判融合不健康（fail-closed）；(d) 跨源覆盖在独立审计集上校准，而不是用同一融合估计自证。

**灵感 3（耦合 → 共模偏差与“自证陷阱”）**
直觉：双臂和融合共享同一套标定与同一时间基准，误差会**共模**：两臂用了同一条被污染的外参标定，或融合门用融合后的估计去检验融合后的估计，就会“自证正确”。所以认证必须引入**外部独立度量**（如标定板/外部动捕/关节编码器冗余一致性）作为锚点，并让相对证书与融合健康度由不同数据源交叉校验；一旦锚点缺失或共模偏差超阈，双臂协作退化为单臂或保持，而非硬撑。

**耦合升级**：在 v10 四层架构上插入**相对-融合证书层**，四层 v11：根信任层（姿态租约 ℓ_p + 能量租约 ℓ_e + **融合租约 ℓ_f** + 相对租约 ℓ_r），L1 几何层（单臂盒 P_A/P_B 与相对盒 P_rel 并列），L2 上下文层（上下文同时预测传感器退化与双臂协作阶段），L2.5 融合层（认证时间对齐、创新门、交叉覆盖），L3 CAR（守卫相对证书、闭链一致性、自碰撞与受力裕度），L4 DCL（采集时间失配/融合不一致/共模偏差样本）。一臂或融合任一失效，级联冻结双臂。

## 1. 形式化定义（增量：定义 54–58）

**定义 54（双臂相对姿态证书）**
端帧 A、B 的位姿 T_A,T_B∈SE(3)，相对位姿 T_rel=T_A^{-1}T_B。相对证书 P_rel⊂SE(3) 若满足
P( T_rel ∈ P_rel | 融合链有效 ∧ 相对租约 ℓ_r 有效 ) ≥ 1-α_r
则称其 sound。**性质**：由单臂世界系证书仅得保守三角界 rad(P_rel) ≤ rad(P_A)+rad(P_B)；当两臂共享共模误差时该界不可直接使用，必须用相对变换独立校准的 r_rel 取代。相对租约 ℓ_r=(t_τ,r_rel,ε_cl,τ_r)，超时或超宽即失效。

**定义 55（认证传感器融合与时间对齐）**
异构流 S_i={(z_i^{(k)},t_i^{(k)})}，频率 f_i、延迟 l_i。选定时间基 t_0 后同步误差 ε_ts=max_i |t_i^*-t_0|，插值/外推速度上界 L_v。融合估计
x̂=F({z_i,Σ_i},ε_ts)，融合半径
r_fuse = r_stat + L_v·ε_ts + r_quant，
**融合 soundness**：P(‖x−x̂‖ ≤ r_fuse) ≥ 1−α_f。
**创新门**：d²=r^T S^{-1} r ≤ χ²_{1-α_i}；超阈即 fusion_unhealthy。认证融合需同时满足：各源证书有效 ∧ ε_ts≤ε_max ∧ 创新门通过 ∧ 跨源覆盖 q_cross≥1−α_c（在独立审计集上校准）。

**定义 56（双臂闭链一致性与协作证书）**
双臂刚性共抓物体时闭链约束 T_A^{-1}T_B ≈ T_grasp，残差
e_cl = log( T_grasp^{-1} T_A^{-1} T_B )。
**闭链一致性证书**：‖e_cl‖_Σ ≤ ε_cl。若 r_rel>ε_cl/κ，则“刚性双臂”假设不成立，必须切到柔顺或单臂。**协作证书** C_t=(P_rel,e_cl,G_t)，其中 G_t 为受力/触觉融合的力闭合裕度证书（接触力旋量可行域非空）。

**定义 57（双臂协作联合证书）**
J^B_t=(P_A,P_B,P_rel,F_t,G_t,ℓ_p,ℓ_e,ℓ_f,ℓ_r,m_t)，F_t 为融合证书（含 ε_ts、d²、q_cross）。**联合 soundness**：
P( X_t∈P_rel ∧ ‖e_cl‖≤ε_cl ∧ 力闭合 | 融合有效,ℓ_p,ℓ_e,ℓ_f,ℓ_r 有效 ) ≥ 1−α_p−α_r−α_f。
任一租约失效或共模锚点缺失，即冻结双臂并进入保守保持/单臂。

**定义 58（融合-协作降级策略）**
动作 a=(sensor_subset, arm_mode)，arm_mode∈{dual_rigid, dual_compliant, single_A, single_B, hold, fail_closed}。效用
U(a)= [Δrad(P_rel|a)·S_φ] / [c_fuse(a)+c_energy(a)+c_switch]
约束：J^B 在该模式下可 sound。**单调降级梯子**：dual_rigid → dual_compliant → single_arm → hold → fail_closed，只允许在证书重新覆盖后才单向回升，回升需最小驻留时间防抖。

## 2. 三大新增产出与既有 IP 升级

**IP-66 REL-CERT ENGINE（双臂相对姿态证书引擎）**
- 相对变换独立共形校准 r_rel（按协作阶段/载荷/速度分层）
- 世界系单臂盒与相对盒并列签发，共模误差检测
- 相对租约 ℓ_r 与超宽/超时级联失效

**IP-67 FUSION-CERT（认证异步多传感器融合）**
- 认证时间对齐：ε_ts 上界、延迟补偿、插值误差计入 r_fuse
- 创新门与跨源交叉覆盖：d² 卡方门 + q_cross 独立审计校准
- 共模锚点：外部标定/动捕/编码器冗余交叉校验；锚点缺失即降级

**IP-68 COORD-GUARD（双臂协作过程守卫）**
- 闭链一致性检查 e_cl 与过约束检测
- 自碰撞盒与力闭合裕度守卫
- 交接状态机：释放前双证书覆盖、释放后单臂重认证
- 单调降级梯子与最小驻留防抖

**既有 IP 升级**
IP-60 PSE：同时输出 P_A/P_B 与 P_rel，半径按融合链分层
IP-63 ECPS：模态效用加入融合算力/延迟成本 c_fuse，传感器子集可选
IP-64 Depth-Cert Adapter：深度- RGB 时间对齐误差计入深度半径
IP-61 DCL：采集时间失配、融合创新超阈、共模偏差与闭链冲突样本
IP-62 CCA：新增时间戳注入、帧错位、传感器掉线、共模标定污染红队
IP-51 CAR：守卫相对证书、ε_ts、d²、e_cl、力闭合与模式一致性
IP-45 总线：新增 rel-pose-cert / fusion-health / sync-error / closure-residual 话题

## 3. 算法骨架

每控制周期：
1. 读各流时间戳、ℓ_p、ℓ_e、ℓ_f、ℓ_r、当前 arm_mode
2. 认证融合：估 ε_ts、算 r_fuse、过创新门与跨源覆盖 → F_t
3. 由融合结果与外部锚点算 T_rel、P_rel、e_cl、力闭合 G_t
4. 若 F_t 不健康 ∨ ε_ts>ε_max ∨ r_rel>ε_cl/κ ∨ 锚点缺失 → 按定义 58 降级
5. 在可行模式下选最大效用 a*，签发 J^B_t
6. CAR 用 J^B_t 守卫；任一租约失效 → 冻结双臂 fail-closed
PSE 签发相对证书，ECPS 分配传感器子集与能量，COORD-GUARD 决定模式迁移。

## 4. 本轮最大风险

**一句话**：双臂与融合共享同一套标定和时间基准，共模偏差会让相对证书与创新门“自证正确”而实际半径被低估，闭链过约束又会在“两个单臂证书都有效”的表象下把误差放大成越界或过力，因此必须用外部独立锚点交叉校验、把 ε_ts 与共模偏差显式计入 r_fuse，并在锚点缺失或闭链残差超阈时单调降级到单臂/保持而非硬撑。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 46 轮产物 · 创新点清单 v23：BiFuse-Cert（Rel-Cert Engine × Fusion-Cert × Coord-Guard）× 双臂相对姿态-认证融合联合证书（四层架构 v11）

> 承接第 45 轮产物 v22。本轮增量插入 IP-66/67/68，并升级 IP-60/61/62/63/64/51/45。不推倒 v10：在根信任层增加融合租约 ℓ_f 与相对租约 ℓ_r，L1 几何层并列签发单臂盒与相对盒，L2 上下文层预测传感器退化与协作阶段，L3 CAR 守卫闭链一致性、时间对齐与力闭合，L4 DCL 采集时间失配与共模偏差样本。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-66 | REL-CERT ENGINE | 新增 | 相对变换 T_rel 独立共形校准、P_rel 与单臂盒并列、共模误差检测、相对租约 ℓ_r |
| IP-67 | FUSION-CERT | 新增 | 认证时间对齐 ε_ts、创新门 d²、跨源覆盖 q_cross、共模锚点交叉校验、融合租约 ℓ_f |
| IP-68 | COORD-GUARD | 新增 | 闭链一致性 e_cl、过约束检测、自碰撞/力闭合守卫、交接状态机、单调降级梯子 |
| IP-60 | POSE-CERT-ENGINE | 升级 | 同时输出 P_A/P_B/P_rel，半径按融合链与协作阶段分层 |
| IP-63 | ECPS | 升级 | 模态效用加入融合算力/延迟 c_fuse，支持传感器子集选择与共享 |
| IP-64 | DEPTH-CERT ADAPTER | 升级 | 深度-RGB 时间对齐误差计入深度半径 |
| IP-61 | DATA-CERT-LOOP | 升级 | 采集时间失配、创新超阈、共模偏差、闭链冲突样本；护照新增 sync_snapshot/closure_residual |
| IP-62 | CERT-COVERAGE-AUDITOR | 升级 | 时间戳注入、帧错位、传感器掉线、共模标定污染、闭链过约束红队 |
| IP-51 | CAR | 升级 | 守卫 P_rel、ε_ts、d²、e_cl、力闭合与 arm_mode 一致性 |
| IP-45 | 总线 | 升级 | rel-pose-cert / fusion-health / sync-error / closure-residual 话题 |

## 1. 符号体系（增量：定义 54–58）

| 符号 | 含义 |
|---|---|
| `T_A,T_B` | 两臂端帧位姿 |
| `T_rel=T_A^{-1}T_B` | 双臂相对位姿 |
| `P_rel` / `r_rel` | 相对姿态证书 / 相对半径 |
| `ℓ_r=(t_τ,r_rel,ε_cl,τ_r)` | 相对租约 |
| `S_i={(z_i,t_i)}` | 异构传感器流 |
| `ε_ts` | 时间对齐误差上界 |
| `r_fuse=r_stat+L_v·ε_ts+r_quant` | 融合半径 |
| `d²=r^T S^{-1} r` | 创新马氏距离 |
| `q_cross` | 跨源交叉覆盖 |
| `ℓ_f=(t_τ,ε_max,α_i,α_c,τ_f)` | 融合租约 |
| `T_grasp` / `e_cl` | 闭链标称变换 / 闭链残差 |
| `G_t` | 力闭合裕度证书 |
| `J^B_t=(P_A,P_B,P_rel,F_t,G_t,ℓ_p,ℓ_e,ℓ_f,ℓ_r,m_t)` | 双臂协作联合证书 |
| `arm_mode` | dual_rigid/dual_compliant/single_A/single_B/hold/fail_closed |

## 2. 关键算法 伪代码

### IP-67 Fusion-Cert 认证融合
```
def certified_fusion(streams, t0, lease_f, calib):
    # 1) 时间对齐：插值到公共时间基，估同步误差
    z_al, eps_ts = time_align(streams, t0)
    if eps_ts > lease_f.eps_max:
        return FusionState(healthy=False, reason='sync')
    # 2) 各源证书必须有效
    if not all(src_valid(s, t0) for s in streams):
        return FusionState(healthy=False, reason='source_cert')
    # 3) 融合 + 创新门
    x_hat, Sigma = gaussian_fuse(z_al)
    r = innovation(z_al, x_hat)
    d2 = r.T @ inv(Sigma) @ r
    if d2 > chi2_threshold(lease_f.alpha_i):
        return FusionState(healthy=False, reason='innovation', d2=d2)
    # 4) 跨源交叉覆盖（独立审计集校准）
    if calib.q_cross < 1 - lease_f.alpha_c:
        return FusionState(healthy=False, reason='cross_coverage')
    Lv = calib.speed_bound
    r_fuse = calib.r_stat + Lv*eps_ts + calib.r_quant
    return FusionState(healthy=True, x=x_hat, r=r_fuse, eps_ts=eps_ts, d2=d2)
```

### IP-66 Rel-Cert Engine
```
def relative_cert(T_A, T_B, fusion, calib, anchor):
    T_rel = inv(T_A) @ T_B
    r_world = rad(fusion.r)                    # 世界系保守界
    r_rel = calib.relative_r[fusion.stage]     # 相对变换独立校准，非三角叠加
    # 共模检测：外部锚点与融合估计的偏差
    common_mode = dist(anchor.T_rel, T_rel)
    if anchor.missing or common_mode > calib.cm_max:
        return RelCert(sound=False, reason='common_mode')
    r_rel = max(r_rel, common_mode)            # 共模偏差计入半径
    P_rel = ball(T_rel, r_rel, metric=calib.metric)
    lease_r = RelLease(tau=now, r_rel=r_rel, eps_cl=calib.eps_cl)
    return RelCert(P_rel, lease_r, r_rel, sound=True)

def rel_lease_valid(lease_r, t):
    return (t - lease_r.tau) <= lease_r.life and lease_r.r_rel <= lease_r.eps_cl
```

### IP-68 Coord-Guard 闭链与降级
```
def closure_check(T_A, T_B, T_grasp, cert_rel, calib):
    e_cl = log(inv(T_grasp) @ inv(T_A) @ T_B)
    ok = norm(e_cl, Sigma=calib.Sigma_cl) <= calib.eps_cl
    over = cert_rel.r_rel > calib.eps_cl / calib.kappa
    return ok and not over, e_cl

def force_closure(tactile, tactile_sigma, calib):
    W = contact_wrenches(tactile)              # 接触力旋量
    return convex_hull_contains_origin(W) and margin(W) >= calib.eta_g

def degrade(mode, fusion, cert_rel, closure_ok, g_ok, anchors_ok):
    # 单调降级：只在证据失效时下移，回升需重新覆盖 + 驻留
    if not fusion.healthy or not anchors_ok:
        return 'hold' if mode in ('dual_rigid','dual_compliant') else 'fail_closed'
    if not closure_ok or not g_ok:
        return {'dual_rigid':'dual_compliant',
                'dual_compliant':'single_A',
                'single_A':'hold','single_B':'hold'}.get(mode, 'hold')
    return mode
```

### IP-51 CAR 升级守卫
```
def car_guard_v7(e, x, certB, persona, lease_p, lease_e, lease_f, lease_r, t):
    if not (pose_lease_valid(lease_p,t) and energy_lease_valid(lease_e,t,E_min(e))
            and fusion_lease_valid(lease_f,t) and rel_lease_valid(lease_r,t)):
        cascade_invalidate('pose_energy_fusion_rel')
        return FailClosed()
    r = radius_lookup(x.stratum, certB.m_t, certB.calib)
    m_pose  = L_phi[e] * r
    m_rel   = L_rel[e] * certB.P_rel.r
    m_sync  = L_v[e] * certB.F_t.eps_ts
    m_energy= L_e * max(0.0, B_min - E(t))
    m = min(certB.lookup, lease_p.m, persona_cap) - m_pose - m_rel - m_sync - m_energy
    return m >= theta(e) and certB.mode_consistent
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| Fusion-Cert | O(Σ|S_i|·d) 每周期 | O(d²) | ε_ts≤ε_max ∧ 各源有效 ∧ d²≤χ² ∧ q_cross≥1−α_c ⇒ P(‖x−x̂‖≤r_fuse)≥1−α_f |
| Rel-Cert Engine | O(1) SE(3) 运算 | O(1) 查表 | 相对变换独立共形 + 共模上界 ⇒ P(T_rel∈P_rel)≥1−α_r |
| Coord-Guard | O(K) 接触点 | O(K) | e_cl≤ε_cl ∧ 力闭合裕度≥η_g ⇒ 闭链约束一致、无过约束放行 |
| 联合证书 J^B | O(1) | O(V+E) | 各租约有效 ∧ P_rel 覆盖 ∧ 闭链一致 ⇒ φ^B 在协作模式 sound |
| 降级梯子 | O(1) | O(1) | 单调下移 + 回升需重新覆盖 ⇒ 无“未认证回升” |

正确性定理：若 pose/energy/fusion/relative 四类租约均有效，认证融合满足时间对齐、创新一致与跨源覆盖，相对证书 P_rel 在独立锚点校验下满足定义 54 的条件覆盖，闭链残差满足 ‖e_cl‖_Σ≤ε_cl 且力闭合裕度达标，则双臂协作联合证书 J^B_t 对协作谓词 φ^B 保持 sound；任一条件失效则 Coord-Guard 单调降级或 fail-closed，不发放未认证的双臂执行权。

## 4. 实验设计 E109–E114

| 实验 | 指标 | 门槛 |
|---|---|---|
| E109 相对证书 soundness | 相对位姿越界率；P_rel 条件覆盖率 | 0 起；≥1−α_r |
| E110 认证融合与同步 | ε_ts 估计误差；创新门漏报率；融合越界率 | <20%；<1%；0 起 |
| E111 闭链一致性 | 过约束误放行率；e_cl 超阈检出率 | 0 起；≥99% |
| E112 双臂交接安全 | 掉件/碰撞/过力次数；交接成功率 | 0 起；≥98% |
| E113 降级与恢复 | 传感器掉线/帧错位下 fail-closed 及时率；误降级率 | ≥99.9%；<5% |
| E114 100h 双臂闭环 | 协作任务成功率；安全违例；相对证书平均宽度；能耗 | 下降<5%；0 起；≤v10 单臂×1.15；增幅<10% |

回退：E110 同步/创新门失效 → 关闭多源融合，回退固定低延迟子集 + 保守半径；E111 闭链误放行 → 禁 dual_rigid，强制 dual_compliant；E113 误降级过高 → 放宽门限并加入驻留滞环；E114 位移越界 → 回退 v10 单臂模式。

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 共模标定/时间基准污染使融合自证正确 | 高 | 外部独立锚点交叉校验 + 共模偏差计入 r_fuse + 锚点缺失即降级 |
| 闭链过约束把误差放大为越界/过力 | 高 | e_cl 检查 + 超宽禁刚性双臂 + 力闭合裕度守卫 |
| 时间失配（深度/力矩晚到）导致半径低估 | 高 | ε_ts 上界 + L_v·ε_ts 计入 + 创新门 fail-closed |
| 双臂频繁降级/回升造成抖动 | 中 | 单调梯子 + 最小驻留 + 滞环 |
| 相对证书校准数据不足产生族偏差 | 中 | 分阶段共形 + DCL 定向采集 + 独立审计再校准 |
| 融合算力/延迟挤占控制周期 | 中 | 子集选择 + 异步融合 + 延迟预算纳入 c_fuse |

## 6. 本轮最大风险

**一句话**：双臂与多源融合共享同一套标定与时间基准，共模偏差会让相对证书和创新门“自证正确”而实际半径被低估，闭链过约束又会在“两个单臂证书都有效”的表象下把误差放大成越界或过力；因此必须以外部独立锚点交叉校验、把 ε_ts 与共模偏差显式计入 r_fuse，并在锚点缺失或闭链残差超阈时单调降级到单臂/保持而非硬撑。
<!-- ARTIFACT:END -->
