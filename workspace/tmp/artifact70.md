# 第 70 轮产物 · 创新点清单 v1：ATLAS-RAS（Adaptive Trust-aware Layered Avoidance with Semantics：语义假设账本 × 语义鲁棒避障 × 决策相关主动建图；HMap×STL×SRC×REL×DR-VoI×ASM×SMC×SMT×LRF）

> 承接第 69 轮 IP-253~263（FLUID-RAS）。R69 让系统学会「看/问/触」来消解动作模态的 epistemic 歧义，但它对世界的表征仍是一张平的地图：几何占据 + 被融合进来的语义标签。它没有问：地图上的一个标签，是测量，还是**断言**？是谁写的、什么时候写的、凭什么可信、错了会怎样？在避障里，这个问题不是哲学，而是碰撞：玻璃门被标成墙（该停不停）、人被标成模特（该让不让）、窗帘被标成墙（能过不过）、湿地被标成干地（该慢不慢）、对手往地图注入一条「可通行」（直接撞）。
>
> 本轮把 R69 的「不确定性二分」下沉到**世界标签层**：语义地图不再是确定性真值，而是一组带空间索引、出处、时间戳、可被反驳的断言；避障用**语义鲁棒 CBF** 对所有未退休假设取安全集交集；语义只能加约束，只有通过**可恢复释放证书 REL** 才能局部扩大安全集；主动建图按**决策相关 VoI** 而非地图熵分配预算；地图投毒作为一等威胁建模，其危害方向被结构性地限制为 DoS。
>
> 定位：R66 问「谁控制」，R67 问「未来怎样」，R68 问「我的测量还准吗」，R69 问「我该向谁求证」，R70 问「**我脚下这块地，真的像地图说的那样吗？如果地图错了，我还安全吗**」。
>
> IP 编号：IP-264~IP-276（共 13 个）。理论姿态：**R69 是 ATLAS 在「零释放 + 语义不可信」边界上的严格退化**；安全侧不让步，效率侧获得 resolution bonus。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对第 69 轮） |
|---|---|---|---|
| IP-264 | HMap Semantic Hypothesis Map | 新增 | 地图从「标签图」升级为「假设图」：每区域保留类别/affordance/动态/几何多假设 + 永远保留的 `h_∅` |
| IP-265 | STL Semantic Trust Ledger | 新增 | 断言只追加账本：来源、时间、哈希、证据链、可信度；信任分只做门控，不冒充概率 |
| IP-266 | SRC Semantic-Robust Control | 新增 | 多假设 CBF-QP：对所有可信假设取安全集交集；语义只能加约束 |
| IP-267 | REL Semantic Release Certificate | 新增 | 语义扩大安全集的唯一出口：k 源一致 + conformal risk control + 可恢复逃逸 |
| IP-268 | DR-VoI Decision-Relevant VoI | 升级 R69 MINT | 从「动作模态 VoI」升级为「空间语义决策相关 VoI」；只建会改变避障动作的地图 |
| IP-269 | ASM Active Semantic Mapper | 升级 R69 主动交互 | 下一最佳视角/探针/问句/他机查询；决策前沿优先，保留探索下限 |
| IP-270 | SMC Semantic-Geometric Consistency | 新增 | 几何/动态/跨模态/时序一致性 + 漂移检测；复用 R69 FMA 区分「世界变了」与「地图一开始就错」 |
| IP-271 | SMT Semantic Map Trust Gate | 升级 R69 MCG | 按来源/区域/年龄校准；ECE 或异常越界即关闭释放通道 |
| IP-272 | LRF Layered Risk Fallback | 升级 R69 两级退避 | L0 完整 / L1 只加约束 / L2 忽略语义 / L3 最小风险机动；安全集单调收缩 |
| IP-273 | AIC-ATLAS | 升级 AIC-FLUID | `ℰ_ATLAS = ℰ_FLUID × ℰ_map × ℰ_sem`：注入/删除/重放/冻结/小步漂移 + 物理语义欺骗/共谋 |
| IP-274 | VQAuditor-M | 升级 VQAuditor-I | 审计断言出处、释放一致性、退休假设真伪、语义后悔、异常编辑；回灌信任先验 |
| IP-275 | J_ATLAS | 升级 J_FLUID | + map_version、|H^cred|、release_count、max ε_rel、SMC_violation、U_dec_p95、semantic_ECE、fallback_level |
| IP-276 | ATLAS Pipeline | 新增 | R69 闭环 + 「快照读 → 可信假设 → 多假设 CBF → 信任门/退避 → DR-VoI 异步建图 → 审计」 |

## 1. 符号体系增量（定义 310–326）

| 符号 | 含义 |
|---|---|
| `ATLAS-RAS = (HMap, STL, SRC, REL, DRV, ASM, SMC, SMT, LRF)` | 语义鲁棒避障闭环 |
| `M_t = {(r, H_r, π_r, E_r, c_r)}` | 语义假设地图（非标签图） |
| `h = (class, affordance, dynamics, geom)` | 语义假设；`h_∅` 为未知，永远保留 |
| `T(c,t)` | 断言信任分（门控用，非真实概率） |
| `H_r^cred(t)` | 可信假设集（含 `h_∅`） |
| `C_base` | 几何基线安全集（占据 + 未知膨胀 + 动态最坏） |
| `C_cons = C_base ∩ ⋂_{h∈H^cred} C_h` | 语义约束安全集（只缩不扩） |
| `C_sem = C_cons ∪ R_rel` | 实际安全集；释放是唯一扩张出口 |
| `REL_r = (r, h_pass, E_rel, ε_rel, h_e, esc_r)` | 语义释放证书 |
| `U_dec(r) = Σ_h π_r(h)[Δ_r(h)]_+` | 决策相关语义不确定性 |
| `DR-VoI(g)` | 信息动作的决策相关信息增益 − 成本 |
| `SMC(r)` | 语义-几何/动态/跨模态/时序一致性 |
| `D_r(t)` | 语义漂移 |
| `ℰ_ATLAS = ℰ_FLUID × ℰ_map × ℰ_sem` | 地图投毒 + 物理语义欺骗威胁模型 |
| `J_ATLAS = (J_FLUID, map_version, …, semantic_ECE, fallback_level, atlas_ver)` | 证书 |
| `L0/L1/L2/L3` | 完整 / 只加约束 / 忽略语义 / 最小风险机动 |

## 2. 形式化定义（要点版）

**定义 310（总览与五不变式）** `ATLAS-RAS = (HMap, STL, SRC, REL, DRV, ASM, SMC, SMT, LRF)`。继承 R69 零学习写操作、非阻塞语义、交互预算、证据纪律；新增：(i) 语义非底座——安全认证只依赖几何/动力学 + 所有未退休假设，语义只能加约束或走 REL；(ii) 假设单调性——无 REL 时可信集只增不减、`C_cons` 只缩不扩；(iii) 决策相关注意——建图预算按 `U_dec` 分配，保留探索下限；(iv) 出处与原子性——每条断言有来源/时间/哈希/版本，控制只读快照；(v) 退避单调性——信任下降时安全集逐级收缩到几何基线。

**定义 311（HMap）** `M_t = {(r,H_r,π_r,E_r,c_r)}`；`H_r` 含类别、affordance、动态、几何参数；`h_∅` 永远保留；`π_r∈Δ(H_r)`；查询 `Q(r)`，快照 `Snapshot()` 不可变。**地图是假设图，不是标签图。**

**定义 312（STL）** 断言 `c=(r,h,src,t_q,t_r,hash,parent,ver)`；账本只追加，退休/撤销显式记录。`T(c,t)=σ(θ·φ)`，`φ` 含校准、跨模态一致、几何/动态一致、来源信誉、年龄、异常、投毒分。`T` 只做门控；释放用 conformal risk control 给有限样本上界。

**定义 313（可信假设集）** `H_r^cred(t)={h:T≥τ_trust ∧ π≥π_min ∧ age≤A_max} ∪ {h_∅}`；`h_∅` 按最坏情况（未知=障碍）处理。开放世界也能安全兜底。

**定义 314（SRC）** `C_h={x:b_h(x)≥0}`；`C_base` 为几何基线；`C_cons=C_base∩⋂_{h∈H^cred}C_h`；`C_sem=C_cons∪R_rel`。控制解多假设 CBF-QP：对所有 `h∈H^cred`，`L_f b_h+L_g b_h u+α_h(b_h)≥0`；释放区域加逃逸约束；不可行则 LRF 退避。无 REL 时 `C_sem⊆C_base`。

**定义 315（REL）** `REL_r=(r,h_pass,E_rel,ε_rel,h_e,esc_r)`。有效条件：(1) `h_pass` 由 `k` 个正交源支持且 `SMC≥τ_smc`；(2) conformal 风险控制满足 `P(h*_r∉保留集)≤ε_rel`；(3) 出处/版本/投毒标记通过；(4) 存在 `esc_r` 在 `h_e` 内退回 `C_cons` 且过 R69 C-RAS-WM 认证。REL 不是真理证书，而是有界风险 + 可回滚的许可。

**定义 316–317（DRU 与 DR-VoI）** `Δ_r(h)=L(x,a*(x,H))−L(x,a*(x,H|h))`，`U_dec(r)=Σ_h π_r(h)[Δ_r(h)]_+`；解析 `r` 不改变动作/活跃约束集则 `U_dec=0`。`DR-VoI(g)=E[U_dec(r)−U_dec(r|y)]−c(g)−c_risk(g)`，s.t. 过 R69 信息动作认证与预算；最大收益 ≤0 则不建图。

**定义 318（ASM）** 敏感度 `S(r)=U_dec(r)/(c_obs+ε)`；按 `DR-VoI` 贪心选下一最佳视角/探针/问句/他机查询；保留覆盖率下限；异步发布原子快照。目标不是建全图，而是把决策边界建准。

**定义 319（SMC）** `SMC(r)=w_g·geo_cons+w_d·dyn_cons+w_c·cross_modal+w_t·temporal_cons`；漂移 `D_r(t)=||P(s_t|M_{t−1},a)−o_t^{sem}||`。越界则分裂假设、衰减信任、撤销 REL、重观测。复用 R69 `(r_res↓,Δa↑)` 区分世界变化与地图初始错误。

**定义 320（AIC-ATLAS）** `ℰ_ATLAS=ℰ_FLUID×ℰ_map×ℰ_sem`；`ℰ_map={inject,delete,replay,freeze,salami}`；`ℰ_sem={patch,spoofed sign,cross-modal collusion,social lie,Byzantine update}`。A102：最多 `f` 个共谋源、哈希不可伪造、版本单调。

**定义 321–323（审计 / 证书 / 信任门）** VQAuditor-M 审出处链、k 源一致、退休真伪、语义后悔、异常编辑；J_ATLAS 在 J_FLUID 上加地图版本、可信假设数、释放次数/风险、SMC 违规、`U_dec_p95`、`semantic_ECE`、`fallback_level`；SMT 按来源/区域/年龄校准，ECE 或异常越界即关闭释放（L1），严重则 L2。

**定义 324–326（退避 / 快照 / 时序判别）** LRF：L0 完整、L1 只加约束、L2 忽略语义、L3 最小风险机动，安全集单调收缩；降级需重新认证。快照 `M_t=(V_t,τ_t,hash_t)`，双缓冲原子切换，超龄撤销 REL。时序签名 `(SMC,Δa,provenance)` 区分漂移（先一致后不一致）、投毒（插入即不一致/出处异常）、冻结（无新证据且覆盖停滞）。

## 3. 关键算法伪代码

```python
# IP-264/265 HMap + STL
class HypothesisMap:
    def query(self, r):            return self.regions[r].H, self.regions[r].pi
    def snapshot(self):            return Snapshot(self.version, self.tau, self.hash, self.regions)
    def apply(self, claims):
        for c in claims: self.ledger.append(c); self.regions[c.r].reweight(c)
        self.version += 1; self.publish_atomic(self.snapshot())

def trust(claim, t, evidence):
    phi = [cal(claim.src, t - claim.t_q), agreement(claim, evidence),
           geo_consistency(claim), dyn_consistency(claim),
           reputation(claim.src), -(t - claim.t_q) / A_max(claim.r),
           -anomaly(claim), -poison_score(claim)]
    return sigmoid(dot(theta, phi))

# IP-266 SRC：多假设 CBF-QP（语义只能加约束）
def semantic_robust_qp(x, u_ref, H_cred, C_base, R_rel):
    cons  = [cbf_constraint(b_h, x, u) for h in H_cred]
    cons += [escape_constraint(r, x, u) for r in R_rel]
    return solve_qp(min_norm(u - u_ref), cons, input_bounds=True, baseline=C_base)

# IP-267 REL：可恢复的语义释放证书
def try_release(r, h_pass, evidence, escape_plan):
    if trust(h_pass, now, evidence) < TAU_TRUST:      return None
    if not cross_modal_agree(h_pass, evidence, k=2):  return None
    if not smc_ok(r, evidence):                        return None
    if not escape_plan.feasible(r, horizon=h_e):       return None
    eps = conformal_release_risk(r, h_pass, alpha=EPS_REL)
    return REL(r, h_pass, evidence, eps, h_e, escape_plan)

# IP-268 DR-VoI：只建会改变避障动作的地图
def decision_relevant_voi(x, H, candidates):
    a0 = semantic_robust_qp(x, u_ref(x), H, C_base, R_rel)
    best = None
    for g in candidates:
        gain = 0.0
        for h, p in hypotheses(H):
            ah = semantic_robust_qp(x, u_ref(x), resolve(H, h), C_base, R_rel)
            gain += p * max(0.0, loss(x, a0) - loss(x, ah))
        score = gain - cost(g) - risk_cost(g)
        if best is None or score > best.score: best = (g, score)
    return best if best and best.score > 0 else None

# IP-276 ATLAS 主闭环（异步建图，实时只读快照）
def ATLAS_round(x, obs):
    M = map_bus.snapshot()                          # 原子快照 + 版本
    H_cred = credible_hypotheses(M, obs, t)         # 含 h_∅
    health = semantic_health(obs, M)                # IP-270 SMC
    if health.requires_quarantine():
        M = quarantine(M, health.regions)           # 撤销 REL，只留约束
    if trust_gate.closed(M, health):
        return LRF_level_up(x)                      # 只收紧，绝不扩大
    u_ref = policy(x, obs)
    u = semantic_robust_qp(x, u_ref, H_cred, C_base(M), R_rel(M))
    if not u.feasible:
        return LRF_level_up(x)                      # 不可行即退避
    g = decision_relevant_voi(x, H_cred, info_candidates)
    if g is not None:
        async_submit(g)                             # 复用 R69 MINT，非阻塞
        audit.submit_async(M.version, H_cred, u, g)
    return u
```

## 4. 推导

假设 A99–A104：世界模型语义误差有界；`b_h` 为合法 CBF；真实假设 `h*_r∈H_r`（`h_∅` 兜底）；语义来源按区域/年龄校准且 conformal 有界；最多 `f` 个共谋源；释放存在可认证逃逸；快照原子、更新有界。

**引理 19（语义鲁棒安全性）** 若控制器对所有 `h∈H^cred` 满足 CBF 条件，且无有效 REL 退休真实假设，则 `x(t)∈C_{h*_r}`。系：未消解歧义只会增加约束，可能保守/绕路/死锁，但不会违反真实约束。

**引理 20（DRU 稀疏性与上界）** `U_dec(r) ≤ L_a·E||a*(H)−a*(H|h)||`；`r` 不在活跃约束边界、解析不改变活跃集时 `U_dec=0`。故 `Σ_r U_dec(r) ≤ L_h·Σ_{r∈F_t} diam(H_r)+ε_a`，而全图熵可任意更大。系：建图预算应集中在决策前沿 `F_t`。

**引理 21（释放风险累积上界）** 若第 `i` 次释放假退休概率 ≤ `ε_rel,i`、逃逸失败概率 ≤ `ε_esc,i`，则 `N_rel` 次释放累计风险 ≤ `Σ_i(ε_rel,i+ε_esc,i)`，且每次释放后可退回 `C_cons`。取 `ε_rel,i=ε_esc,i=budget/(2N_rel)`，总风险 ≤ `budget`。系：释放预算是可声明、可审计的安全开销。

**引理 22（投毒方向性）** (1) 只加约束的投毒只能缩小 `C_cons`，造成可用性损失，不直接碰撞；(2) 想扩大安全集必须让假「可通行」通过 `k` 源共识 + SMC + REL，成功概率 ≤ `δ_map·ρ^{k−1}+ε_hash+ε_smc`；(3) 删除/冻结/重放主要影响可用性与新鲜度，可由版本/出处/时序签名定位。系：**投毒默认是 DoS，不是碰撞**；升级为安全事件需多源共谋 + 一致性欺骗 + 可恢复性失败同时发生。

**定理 18（ATLAS 对 R69 的严格包含）** L2 与 R69 几何避障逐指令相同；L1 满足 `C_cons⊆C_base`，安全性不低于 R69、可用性不高于 R69；L0 只在 `R_rel` 上以 `ε_rel+ε_esc` 的可声明风险扩张，受释放预算约束；释放预算为 0 时 L0 逐指令退化为 L1。故 R69 是「零释放 + 语义不可信」边界，ATLAS 安全侧不让步，效率侧获得 resolution bonus。

**定理 19（闭环一致性与无突变）** 原子快照 + CBF 裕度调度保证地图更新/释放/撤销/回滚引起的控制变化连续；信任门关闭时系统有限时间内单调进入 L1/L2，安全集只缩不扩；同一控制周期不会同时看到新旧地图版本。

## 5. 复杂度分析

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| HMap 查询/更新（|H|≤4） | < 0.05 ms | 20 MB | 定义 311 |
| STL 信任评估（证据≤8） | < 0.02 ms | 5 MB | 定义 312 |
| SR-CBF QP（n_h≤4） | < 0.30 ms | O(n_h²) | 定义 314；引理 19 |
| DR-VoI 枚举（候选≤8） | < 0.15 ms | O(1) | 定义 317；引理 20 |
| SMC 一致性/漂移 | < 0.10 ms | O(|ℛ|) | 定义 319 |
| 快照/版本切换 | < 0.01 ms | O(1) | 定义 325 |
| **实时环路总延迟** | **< 2.8 ms**（K=1，R69 基线 2.6 ms） | — | 定理 18–19 |
| ASM 主动建图（异步 20 Hz） | 不占实时预算 | — | 定义 318 |

## 6. 实验设计 E301–E315

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E301 语义假设地图校准 | 假设集覆盖真实类别（含未知） | 覆盖率 ≥ 95%，ECE < 0.05 |
| E302 标签错误下的避障 | 玻璃门/窗帘/模特/湿地/镜面 | 碰撞 = 0（未知按障碍），近失 ≤ 基线 |
| E303 DR-VoI vs 熵/随机/全覆盖 | 建图预算该花在哪 | 同等成功率下建图预算 −40% |
| E304 affordance 收益 | 可通行/可推开语义是否被安全利用 | 不必要停车 −30%，通过率 +20% |
| E305 地图投毒 | 注入/删除/重放/冻结/小步漂移 | 注入成功率 ≤ 1%，DoS 检出 ≥ 90% |
| E306 语义漂移 | 物体移动/门关闭/地面变湿 | 漂移检出 ≥ 90%，误报 ≤ 5% |
| E307 跨模态一致性 | 视觉/语言/触觉/他机互校 | 共谋欺骗检出 ≥ 85% |
| E308 释放风险校准 | conformal 上界是否可信 | 经验释放风险 ≤ 声明 `ε_rel` |
| E309 对 R69 严格包含 | 语义关闭时是否逐指令一致 | 行为差 = 0 |
| E310 实时预算 | 多假设 QP 是否守时 | P99 < 2.8 ms，无超时 |
| E311 消融 | HMap/STL/SRC/REL/DR-VoI 贡献 | 去 REL 退 L1；去 DR-VoI 建图预算 +50% |
| E312 24h 长时程 | 地图老化、交互疲劳、漂移叠加 | 零释放诱发碰撞，可用性稳定 |
| E313 仿真到现实 | 语义噪声/标定误差迁移 | 性能下降 ≤ 10% |
| E314 对抗补丁/伪造标牌 | 物理世界语义欺骗 | 释放拒绝率 ≥ 95% |
| E315 多机器人地图共识 | Byzantine 地图更新 | 单源污染不进入可信集 |

## 7. 本轮最大风险

**一句话**：ATLAS-RAS 的全部效率收益都押在「语义释放证书」上——一旦一条被自信签发、实际错误的释放（玻璃门被当成可通行、人被当成模特、湿地被当成干地）把安全集扩进真实障碍，鲁棒 CBF 的保证就在**被退休的假设**之外失效，语义建图会把避障从「保守但安全」变成「高效但会撞」——**信错，比不信更危险**。

**次级风险与缓解**：多假设 CBF 过保守/不可行（硬/软约束分层 + slack + DR-VoI 消解 + L3 兜底）；校准尾部风险（按区域/年龄/来源条件校准 + conformal + 硬释放预算）；地图投毒/重放/冻结（STL + k 源 + SMC + 审计，结构性限制为 DoS）；观测动作危险（R69 信息动作认证 + 逃逸包络）；开放世界新语义（`h_∅` 按障碍 + 更强释放证据）；实时性（假设数上限 + 异步建图 + 快照 + QP 热启动）。
