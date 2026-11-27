## 0. 新增核心模块（在 IP-425–439 基础上扩展）

| 编号 | 名称 | 类型 | 关键改进（相对 MetricVoiceGauge-NCD-HUTDH-v23） |
|---|---|---|---|
| IP-440 | Map-Anchored Certificate Ledger (MACL) | 地图锚定证书账本 | 证书挂子图锚点，世界界 = ε_loc + ε_map；L_obs 只增（静态长挂/动态短 TTL）、L_free 有证赎回可撤销；回环→重锚定+撤销，永不篡改历史证据 |
| IP-441 | Scenario Profile & Landing Protocol (SPLP) | 场景谱系与落地协议 | 场景=签名六元组 S；LC(S) 场景实测 κ_c/覆盖；影子证书差异保守判定；分阶段激活；每场景离线证书包（直接缓解 v23-R1） |
| IP-442 | Proactive Clarification Protocol (PCP) | 主动澄清协议 | 询问=被认证行动（与运动同过门）；V_ask 信息-成本决策；回答 conformal 校准与手势同门槛；超时=最保守；预算+滞回防洪泛 |
| IP-443 | HPC-E+S (Unified Quint-Certificate Gate) | 统一准入门升级 | HPC-E+ ∪ MACL ∧ SPLP ∧ PCP 五证一体；Exec_v24 = Exec_v23 ∩ Fil_mac ∩ Fil_slp ∩ Fil_pcp ⊆ Exec_v23 |

## 0. 增量符号体系（定义 1000–1063）

| 符号 | 含义 |
|---|---|
| G_M = (V_M, E_M) | 子图位姿图：节点=子图 m，边=里程计/回环约束 |
| T_m ∈ SE(3), Σ_m | 子图 m 的世界位姿估计与协方差 |
| ε_map(m,t) | 子图 m 在时刻 t 的位姿漂移上界（沿位姿图路径协方差合成的保守界；SLAM 退化 → ∞） |
| eps_snap | 证书签发时刻的 ε_map 快照（障碍条目永不变小；自由条目被当前值校验） |
| ε_anchor = ε_loc(s_k) + ε_map(anchor(k),t) | 证书 k 的世界坐标膨胀界 |
| L_obs = {⟨k, anchor, CertBox_w, src, kind, ttl⟩} | 障碍证书账本：kind ∈ {static, dynamic}（dynamic 条目短 TTL），场景内只增 |
| L_free = {⟨R, AbsCert_ref, anchor, eps_snap, TTL_exp, cond⟩} | 自由空间账本：赎回/撤销双向变化 |
| revoke(e) | 撤销：条目移出 L_free，对应区域回保守"可能有人" |
| ΔT / corrected(m) | 回环修正：位姿图优化产生的子图位姿变化 |
| S = (v_rule, v_prior, v_calib, v_map, v_prompt, v_energy) | 场景版本六元组（云端签名 + Merkle 根） |
| LC(S) ≜ κ̂_c(S) ≥ κ_min ∧ CoverHoeff ≥ 1-α ∧ ShadowDiff(S, S_active) ✓ ∧ OfflineBundle(S) ready | 落地证书谓词（κ̂_c 为场景对抗测试集实测召回下界） |
| ShadowDiff | 影子模式：并行运行 S_new 与 S_active 证书管线，比较证书集（障碍 ⊇ ∧ 自由 ⊆ ∧ 参数域 ⊆ 才算保守） |
| OfflineBundle(S) | 离线证书包：冻结规则树根哈希 + 校准器 + 地图 + 预编译降级决策树 |
| a_q = (m_q, c_q, τ_q, hold) | 澄清询问：模态（语音/灯光/屏）/内容/超时/保持策略 |
| V_ask = p̂_resp · ΔRisk − c_ask | 询问期望净值：响应概率 × 灰区消解风险减量 − 询问成本 |
| Γ_r | 回答的 conformal 预测集（与手势 Γ 同构融合，P36 门槛不变） |
| B_q, H_q, Q_budget_t | 单位时间询问预算（次/分）/ 同灰区滞回窗口 / 剩余配额 |
| ζ_msi = ζ_ce ∪ (G_M, L_obs, L_free, S_active, Q_budget, q_state) | MSI 层共享状态 |
| MapValid(π) ≜ 途经区域均有有效锚定证书 ∨ 区域在 L_free 有效成员内 ∨ 区域保守处理 | 锚定有效性过滤器 Fil_mac 的核心谓词 |
| ScenarioValid ≜ LC(S_active) 缓存有效 ∧ 当前 ε_map(m,t) ≤ eps_snap 对所有被引用子图成立 | 场景有效性过滤器 Fil_slp 的核心谓词 |
| QueryPolicy(π) ≜ ¬π.is_query ∨ (SAFE 保持态 ∧ Q_budget>0 ∧ V_ask>0 ∧ 能量 ≥ τ_q 保持预算) | 询问策略过滤器 Fil_pcp 的核心谓词 |
| Exec_v24 = Exec_v23 ∩ {π: MapValid(π) ∧ ScenarioValid ∧ QueryPolicy(π)} | 五证门计划集 |

## 1. 关键算法骨架（在 IP-431–439 骨架上扩展）

```python
# ============================================================
# IP-440 Map-Anchored Certificate Ledger (MACL) — 地图锚定证书账本
# ============================================================
@dataclass
class LedgerEntryObs:
    cert_id: int
    anchor: int              # 子图 id
    certbox_w: 'AABB'        # 世界坐标盒: T_m·box_local, 膨胀 ε_loc + eps_snap
    src: str                 # 'hull' | 'sdc' | 'dcl-forbidden'
    kind: str                # 'static'(结构, 长挂账) | 'dynamic'(人/移动物, 短 TTL)
    ttl_exp: float           # dynamic: 帧间短时效; static: inf

@dataclass
class LedgerEntryFree:
    region_id: int
    anchor: int
    region_w: 'AABB'
    abscert_ref: int         # 签发依据的 AbsCert (v20 CAC)
    eps_snap: float          # 签发时刻 ε_map 快照; 当前值超出即撤销
    ttl_exp: float
    cond: dict               # 覆盖条件: 手势无在场翻转、召回下界 κ_c 成立等

class MapAnchoredLedger:
    def __init__(self, pose_graph, ttl_free: float = 30.0):
        self.G = pose_graph                  # 子图位姿图
        self.L_obs: list[LedgerEntryObs] = []
        self.L_free: dict[int, LedgerEntryFree] = {}
        self.ttl_free = ttl_free

    def eps_map(self, m: int, t: float) -> float:
        """O(1) 查表: 沿位姿图路径协方差合成的保守漂移上界; SLAM 退化 → inf"""
        return self.G.drift_bound(m, t)      # 图优化低频离线跑, 在线仅查表

    def add_obstacle(self, box_local, anchor, eps_loc, src, kind):
        eps_snap = self.eps_map(anchor, now())          # 签发快照, 永不缩小
        self.L_obs.append(LedgerEntryObs(
            ..., anchor, transform(self.G.T(anchor), inflate(box_local, eps_loc + eps_snap)),
            src, kind, now() + (DYN_TTL if kind == 'dynamic' else INF)))

    def redeem_free(self, region_w, anchor, abscert) -> bool:
        """AbsCert 赎回自由空间: 仅当覆盖条件全成立(含手势在场翻转检查);
        人类活动区(kind='crowd')拒绝入账, 只有结构区可赎回 (R1 缓解)"""
        if region_w.kind == 'crowd' or not abscert.valid_now():
            return False
        self.L_free[region_w.id] = LedgerEntryFree(
            region_w.id, anchor, region_w, abscert.id,
            self.eps_map(anchor, now()), now() + self.ttl_free, abscert.cond)
        return True

    def query_free(self, x_w) -> bool:
        """x 是否在有效赎回区内: 空间哈希 O(1) + TTL/漂移双检查"""
        for e in self._index.lookup(x_w):
            if e.ttl_exp < now():                        # 时间失效
                self.revoke(e); continue
            if self.eps_map(e.anchor, now()) > e.eps_snap:  # 漂移超快照 → 撤销
                self.revoke(e); continue
            return True
        return False

    def revoke(self, e: LedgerEntryFree):
        self.L_free.pop(e.region_id, None)               # 回保守"可能有人"

    def on_loop_closure(self, corrected: dict[int, 'SE3']):
        """回环修正: 静态障碍重锚定(刚体平移, eps_snap 不变, 永不缩小膨胀),
        自由条目全撤销 —— 历史证据宁可作废, 不容位姿修正顺手放宽 (P43)"""
        for m, T_new in corrected.items():
            for e in self.L_obs:
                if e.kind == 'static' and e.anchor == m:
                    e.certbox_w = apply_T(T_new, e.certbox_w)
        for e in list(self.L_free.values()):
            if e.anchor in corrected:
                self.revoke(e)

    def obs_union(self) -> 'AABBSet':
        """当前有效障碍集 = L_obs 有效条目 ∪ 本帧 Hull∪CertBox (v23 逐帧层保留)"""
        return union(e.certbox_w for e in self.L_obs
                     if e.ttl_exp > now()) | self.frame_level_obs

# ============================================================
# IP-441 Scenario Profile & Landing Protocol (SPLP) — 场景谱系与落地协议
# ============================================================
@dataclass
class ScenarioTuple:
    v_rule: int; v_prior: int; v_calib: int
    v_map: int; v_prompt: int; v_energy: int
    sig: bytes; merkle_root: bytes
    def verify(self, pk) -> bool: ...        # 同 CESC 验签 + 版本覆盖检查

class ScenarioLandingProtocol:
    def __init__(self, cesc: 'CloudEdgeSyncCertificate', fsvc: 'FewShotValidator',
                 pk_cloud: 'PublicKey'):
        self.cesc = cesc                     # 复用 v23 原子切换协议
        self.fsvc = fsvc
        self.pk_cloud = pk_cloud
        self.S_active: ScenarioTuple | None = None
        self.offline_bundles: dict = {}      # v_map -> 冻结包

    def land(self, S_new, artifacts, test_suite) -> bool:
        """落地四步: 编译 → 实测 → 影子 → 原子激活"""
        if not S_new.verify(self.pk_cloud):
            return False
        # (1) 实测: κ_c 与 conformal 覆盖必须在场景对抗测试集上重做, 不得继承
        #     (儿童/轮椅/蹲姿/逆光等系统性漏检场景) —— κ_c 从假设变实测
        if measure_recall_lower_bound(test_suite) < KAPPA_MIN:
            return False
        if not self.fsvc.recalibrate(artifacts['D_calib_scenario']):
            return False
        # (2) 影子: 并行跑 S_new 管线, 证书差异必须保守
        if not self.shadow_diff(S_new, artifacts):
            return False
        # (3) 离线证书包预置: 断联/共振崩塌保底 (缓解 v23-R1)
        self.offline_bundles[S_new.v_map] = self._freeze_bundle(artifacts)
        # (4) 走 CESC 同款原子切换: 双轨 + T_switch + 失败回滚
        return self.cesc.atomic_switch_with(S_new, artifacts)

    def shadow_diff(self, S_new, artifacts) -> bool:
        """新场景证书集必须覆盖旧场景的保守性:
        障碍 ⊇ ∧ 自由 ⊆ ∧ 参数域 ⊆ (影子期上限 SHADOW_TIMEOUT, 超时判不通过)"""
        certs_new = self._run_pipeline_shadow(artifacts, timeout=SHADOW_TIMEOUT)
        certs_old = self._run_pipeline_shadow(self.S_active, timeout=SHADOW_TIMEOUT)
        return (certs_new.obs >= certs_old.obs and
                certs_new.free <= certs_old.free and
                certs_new.param_domain <= certs_old.param_domain)

    def scenario_valid(self) -> bool:
        """ScenarioValid 谓词: O(1) 缓存查询, 供五证门调用"""
        return self.S_active is not None and self._lc_cache.valid()

    def on_cloud_disconnect(self):
        # 断联即激活当前场景冻结包: 证书基于 OfflineBundle 继续签发
        self._activate_bundle(self.offline_bundles[self.S_active.v_map])

# ============================================================
# IP-442 Proactive Clarification Protocol (PCP) — 主动澄清协议
# ============================================================
class ProactiveClarifier:
    def __init__(self, conformal_voice, B_q: float = 4.0,
                 H_q: float = 5.0, tau_q: float = 8.0):
        self.voice = conformal_voice         # 回答的 conformal 校准器
        self.B_q = B_q                       # 询问预算: 次/分钟
        self.H_q = H_q                       # 同灰区滞回: 秒
        self.tau_q = tau_q                   # 保持态等待上限
        self.Q_budget = B_q
        self.q_state = 'idle'
        self.last_ask: dict = {}

    def gray_zone(self, certs) -> bool:
        """灰区判定: AbsCert 将到期 ∨ 占用置信度中段 ∨ 意图预测集过大"""
        return (certs.abscert_expiring() or certs.occupancy_ambiguous()
                or certs.intent_set_large())

    def ask_value(self, certs) -> float:
        """V_ask = p̂_resp·ΔRisk − c_ask; ΔRisk = 灰区宽度 × 激进计划集活性增益"""
        return self.p_resp_hat * self.delta_risk(certs) - self.C_ASK

    def maybe_ask(self, plan, certs, gate: 'HPCEPlusS'):
        """询问是行动: 必须过五证门, 且预算/滞回/净值三重闸门"""
        if not self.gray_zone(certs):
            return None
        if (self.Q_budget <= 0 or self.ask_value(certs) <= 0
                or now() - self.last_ask.get(certs.zone, -INF) < self.H_q):
            return None
        hold = make_hold_plan(plan, tau=self.tau_q)      # SAFE 保持态
        if not gate.admits(hold, include_query=True):    # 与运动同权过门 (P45)
            return None
        self.Q_budget -= 1
        self.last_ask[certs.zone] = now()
        self.q_state = 'waiting'
        emit_query(self.modality, self.content, timeout=self.tau_q)
        return hold

    def on_response(self, r) -> 'Evidence':
        """回答 → conformal 预测集 → 与手势同门槛融合;
        超时/无应答/拒答 → 最保守证据: 代码路径上不存在 '沉默→许可'"""
        if self.q_state != 'waiting':
            return conservative_evidence()
        self.q_state = 'idle'
        if r is None or r.timed_out or r.refused:
            return conservative_evidence()               # 沉默 ≠ 没人
        gamma_r, s = self.voice.calibrate(r)             # (Γ_r, 置信分)
        return merge_intent_evidence(gamma_r, s, channel='voice')  # P36 门槛不变

# ============================================================
# IP-443 HPC-E+S — 五证一体统一准入门
# ============================================================
@dataclass
class HPCEPlusS:
    hpc_e_plus: 'HPCEPlus'               # v23 四证门 (几何∧规范∧负信息∧能量∧云边)
    macl: MapAnchoredLedger
    splp: ScenarioLandingProtocol
    pcp: ProactiveClarifier

    def admits(self, plan, x, v, z, E_res, margin_req, modules) -> bool:
        if not self.hpc_e_plus.admits(plan, x, v, z, E_res, margin_req, modules):
            return False                              # 证1-4: HPC-E+ 四证
        if not self.splp.scenario_valid():            # 证5a: 场景落地有效
            return False
        if not self.macl.map_valid_for(plan):         # 证5b: 途经锚定有效/漂移有限
            return False
        if plan.is_query and not self.pcp.query_permitted(plan):
            return False                              # 证5c: 询问策略合规
        return True

# ============================================================
# 端到端流水线集成（v23 PerceptionComplianceEnergyPipeline 之上叠加 MSI 层）
# ============================================================
class MSIAugmentedPipeline(PerceptionComplianceEnergyPipeline):
    def __init__(self, config: dict):
        super().__init__(config)
        self.macl = MapAnchoredLedger(config['pose_graph'])
        self.splp = ScenarioLandingProtocol(self.cesc, self.fsvc, config['pk_cloud'])
        self.pcp = ProactiveClarifier(config['conformal_voice'])
        self.gate = HPCEPlusS(self.hpc_e_plus, self.macl, self.splp, self.pcp)

    def step(self, sensor_data: dict, cloud_update: Optional[dict] = None):
        # 0. 场景事件 (异步, 非阻塞): 落地/断联/切换
        if cloud_update and 'scenario' in cloud_update:
            self.splp.land(cloud_update['scenario'], cloud_update['artifacts'],
                           cloud_update['test_suite'])
        if cloud_update and cloud_update.get('disconnected'):
            self.splp.on_cloud_disconnect()
        # 1. v23 管线: 感知 → 证书生成 → CESC/FSVC → CFC+++ 共识
        admitted_v23, info = super().step(sensor_data, cloud_update)
        # 2. MSI 层: 检测入障碍账本 (static/dynamic 分账), AbsCert 赎回自由区
        self.macl.ingest_detections(info['certs'])
        if info.get('abscert'):
            self.macl.redeem_free(info['abscert'].region,
                                  info['abscert'].anchor, info['abscert'])
        # 3. 灰区 → 主动澄清 (询问本身过五证门)
        query = self.pcp.maybe_ask(info['plan'], info['certs'], self.gate)
        if query is not None:
            info['plan'] = query                       # 本拍执行 SAFE 保持+询问
        # 4. 五证准入 (在 v23 四证之上追加 Fil_mac/Fil_slp/Fil_pcp)
        admitted = self.gate.admits(info['plan'], sensor_data['x'],
                                    sensor_data['v'], sensor_data['z'],
                                    sensor_data['E_res'], sensor_data['margin_req'],
                                    info['modules'])
        return admitted, {**info, 'scenario': self.splp.S_active,
                          'free_ledger': len(self.macl.L_free),
                          'q_budget': self.pcp.Q_budget}
```

## 2. 复杂度分析

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 |
|---|---|---|---|
| MACL 障碍入账 | O(log|L_obs|)（空间索引插入） | O(|L_obs|) | 静态长挂 + 动态 TTL 短 |
| MACL 自由查询 | O(1) 摊还（空间哈希 + 双检查） | O(|L_free|) | TTL=30s, 漂移快照校验 |
| MACL 回环重锚定 | O(|受影响条目|) 偶发摊还 | O(1) 增量 | 受影响子图 ≤ k, 回环低频 |
| ε_map 查询 | O(1) 查表 | O(|V_M|) | 图优化离线/低频 |
| SPLP 落地四步 | O(|测试集|) 一次性 | O(|bundle|) | 测试集 ≥10⁴ 帧, 影子双跑 2× |
| SPLP 场景有效谓词 | O(1) | O(1) | 在线仅查 LC 缓存 |
| PCP 灰区判定 + V_ask | O(1) | O(1) | B_q=4/min, H_q=5s |
| HPCEPlusS 准入 | O(|modules|)（五连言短路求值） | O(1) 增量 | 在 v23 四证上 +O(1) |
| 端到端单步 | v23 基础 + O(1) | O(|L_obs| + |L_free| + |bundle|) | 50Hz 实时约束 <20ms 保持 |

**实时性保证**：MACL 在线路径只有 O(1) 查询/入账，回环重锚定在低频事件里摊还；SPLP 在线仅 O(1) 缓存查询（落地/影子全在异步侧）；PCP 判定 O(1)。控制路径仍无阻塞 I/O，云端与落地流程完全异步，满足 50Hz。

## 3. 正确性论证

### 引理 5（锚定证书的漂移可靠性）
**陈述**：若 ε_map(m,t) ≥ 实际位姿误差范数（置信 1-δ_m），则 L_obs 中锚定于 m 的证书在世界坐标下以 ≥1-δ_m-δ_loc 概率包含真实物体。
**证明**：世界坐标误差由位姿误差与局部定位误差经三角不等式合成：‖T_real ⊖ T̂‖ ≤ ε_map + ε_loc；CertBox_w = T_m·inflate(box_local, ε_loc + eps_snap) 以 ≥1-δ_loc 包含局部真物，位姿项以 ≥1-δ_m 成立，union bound 给 ≥1-(δ_m+δ_loc)。障碍条目膨胀界取签发快照且永不缩小，故后续 ε_map 下降不削弱该界。∎

### 引理 6（回环修正下的账本单调性）
**陈述**：任意回环/位姿修正后：(i) L_obs 无任何删除，静态条目仅刚体重锚、膨胀界保持签发快照；(ii) L_free 只减不增（修正仅触发 revoke，无任何路径在修正中签发新自由条目）；(iii) 故同一估计状态内 Obs 单调不减、自由集单调不增，且每个存续条目在新估计下仍满足引理 5 的有效性，Fil_mac 是 Exec_v23 逐帧保守语义的子集。
**证明**：(i) on_loop_closure 对 static 条目仅施加 apply_T 并保留 eps_snap，代码中不存在缩小膨胀界的路径；(ii) 修正分支对 L_free 的唯一动作是 revoke；(iii) MapValid 的查询语义 = L_free 有效成员 ∧ 当前 ε_map ≤ eps_snap，等价于"赎回条件在当前估计下仍成立"，故通过 Fil_mac 的计划在 v23 的逐帧保守语义下同样可执行。∎

### 引理 7（场景切换的安全等价与可回退）
**陈述**：若 LC(S_new) 通过且 ShadowDiff 保守（障碍 ⊇ ∧ 自由 ⊆ ∧ 参数域 ⊆），则激活后 Exec_v24 不扩张；切换失败、断联或 LC 缓存失效 ⇒ 回退 S_active 完整包，Exec_v24 单调不增。
**证明**：影子保守性保证新场景的参数域与证书集是旧场景的过滤器子集；原子切换复用 CESC 的双轨+T_switch+回滚（v23 引理 1 的纪律原样适用）；OfflineBundle 预置使断联时 ScenarioValid 仍基于冻结版本可验证（LC 缓存不依赖云端在线）。∎

### 引理 8（询问行动的安全与沉默失效安全）
**陈述**：(i) 任何询问 a_q 发起时机器人处于已认证 SAFE 保持态且持有 τ_q 能量预算；(ii) 回答证据只经 P36 非对称门槛进入规范状态，PCP 无独立许可权；(iii) 超时/无应答/拒答 ⇒ 保守证据。
**证明**：(i) maybe_ask 中 gate.admits(hold, include_query=True) 是硬前置，保持计划与运动同权过五证门；(ii) on_response 中 merge_intent_evidence 复用 GIC 的非对称门槛与 ≥2 模态独立佐证要求，PCP 只是新增证据通道，许可高门槛不变；(iii) r is None / timed_out / refused 三分支均直接返回 conservative_evidence，控制流上不存在"沉默→许可"路径。∎

### 定理（HPC-E+S 五证门的单调完备性）
**陈述**：对任意计划 π，HPCEPlusS.admits(π)=True ⟺ π ∈ Exec_v23 ∧ MapValid(π) ∧ ScenarioValid ∧ QueryPolicy(π)；故 Exec_v24 = Exec_v23 ∩ Fil_mac ∩ Fil_slp ∩ Fil_pcp ⊆ Exec_v23 ⊆ Exec_v22 ⊆ Exec_v21 ⊆ Exec_v20 ⊆ Exec_v19 ⊆ Exec_v18，且任意单点/组合失效的退化方向均为更保守。
**证明**：由五连言定义与引理 5–8 直接得。必要性：任一过滤器缺失即对应一类风险（时-空证书失效/情境参数失配/询问无序）未被缓解。充分性：五条件全满足时，执行集仍落在 v23 保守语义之内。失效接口见 idea §3 退化表：MACL 失效→撤销全部锚定证书、SPLP 失效→回退 S_active 包、PCP 失效→禁止询问，每项失效都使某过滤器收紧而非放宽。∎

## 4. 已知风险与缓解

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R1 | 时间性缺席幻觉：TTL 内动态环境使已赎回区域实际被占 | 最高 | 1) 人类活动区（crowd）永不入 L_free，只有结构区可赎回；2) TTL 保守默认 30s + 高频人流区自适应缩短；3) 当前 ε_map 超签发快照即撤销；4) 重访区域 AbsCert 必须重新赚取才可续期；5) AbsCert 签发仍需手势通道翻转确认 | 遮挡路径的快速侵入快于重验节奏 |
| R2 | ε_map 合成误差在长回环/退化几何（长走廊、低纹理）下低估真实漂移 | 高 | 1) 协方差合成取保守上界 + 自适应膨胀因子；2) ε_map 无界即全撤销回 v23 逐帧；3) 场景地图在落地时用高精度建图预先固化 | 低纹理场景在线建图质量差 |
| R3 | 影子模式差异判定阈值不当：阻塞落地或放水激活 | 中 | 1) 差异三条件（⊇/⊆/⊆）形式化 + 单测覆盖；2) 影子期上限 SHADOW_TIMEOUT，超时判不通过；3) 灰度期人工复核点 | 边缘场景测试集覆盖不足 |
| R4 | 询问骚扰与用户疲劳（预算/滞回失当）致用户故意不答，PCP 退化 | 中 | 1) B_q=4/min 上限 + 同灰区滞回 5s；2) 多模态轮换（语音→灯光→屏）；3) 无答率监控触发参数回调；4) 沉默本身失效安全 | 高密度人群中询问价值密度下降 |
| R5 | 场景数量爆炸导致证书包维护成本（每场景全套校准/测试集/地图） | 中 | 1) 场景谱系继承（共享骨干校准，仅场景层重做）；2) 差异化最小测试集；3) 包内容 Merkle 指纹去重 | 长尾小场景落地成本仍高 |

## 5. 实验设计（验证指标）

| 指标 | 基线 (v23) | 目标 (v24) | 测试协议 |
|---|---|---|---|
| 锚定证书世界坐标包含率（注入漂移） | N/A | ≥1-δ（δ=0.01） | 位姿图注入高斯漂移+随机回环，10⁶ 证书样本统计 |
| 回环后自由空间扩张次数 | N/A | 0（账本不变量断言） | 故障注入：随机回环修正 × 10⁴ 次，断言 L_free 单调 |
| AbsCert 持久化收益（活性） | 每帧重赚 | 赎回存活时间中位数 ≥25s/TTL30s；灰区收缩时间占比下降 ≥40% | 动态人流仿真，对照 v23 逐帧模式 |
| 场景落地通过率与时延 | N/A | 10 场景 ≥9 通过；落地 <30min | 场景对抗测试集实测 κ_c、影子双跑、灰度激活 |
| 断联场景下服务不中断率 | 依赖单 V_last_valid | 100%（每场景离线包） | 断联注入 × 场景切换交叉 100 组合 |
| PCP 灰区消解率 / 询问次数 | N/A | 灰区消解 ≥60%；询问 ≤4/min | 人机交互仿真 + 真人 20 名，含无应答对抗 |
| 询问超时保守率 | N/A | 100%（沉默→假设有人） | 超时/拒答/噪声回答注入 |
| 安全单调性违反次数 | 0 | 0 | SLAM 失效/场景切换失败/交互通道故障组合注入 |
| 端到端单步延迟 (P99) | <20ms | <20ms（不退化） | 50Hz 实测含 MACL/PCP/场景谓词 |

## 6. 本轮最大风险（最终确认）

**一句话**：L_free 账本把"过去在某锚点、某漂移快照、某覆盖条件下见过没人"兑换成"现在没人"的通行证，而其全部可靠性押在 TTL 窗口内环境静态这一隐藏假设上——一旦人或障碍经遮挡路径在被赎回区域内移动且快于 TTL/回环重验节奏，机器人将拿着时间上未过期、地图上已作证的证书撞上真实的人，即时间性缺席幻觉。
