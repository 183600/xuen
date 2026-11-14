# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 3 轮（灵感循环第 3 轮；本轮灵感：「具身智能」×「数据增强」）

> **基线继承**：第 2 轮 **ToolGauge**（IP-315–320；定义 416–431；引理 46–50；实验 E426–E440）。
> 本轮纪律：**在 ToolGauge 上继续增量升级，不推倒重来**——L-Box / T-Box+TCV / MP-Φ+AP-Cal
> 分别沿「具身」与「增强」两条轴升级；MODGAUGE 五不变式与 ToolGauge 的四层探测防线全部保留；
> 同时审计并修复第 2 轮遗留的七处过度主张与实现缺口（§5）。
> 集成链延长为：**MODGAUGE ⊃ LeanGauge ⊃ ToolGauge ⊃ EmbodiedGauge**。

## 双轴映射（升级而非重写）

| 灵感词 | 第 2 轮对象 | 升级为 | 一句话动机 |
|---|---|---|---|
| 具身智能 | L-Box 只从外部回执猜原因；T-Box 只探测外部世界 | **E-Box**：覆盖矩阵扩为 R_emb = R_world × R_body；自运动即自我测量，身体参数 θ_body 与外部世界联合标定 | 第一把没标定的尺子是身体；身体坐标系错了，外部探测再准也表达在错坐标系里 |
| 数据增强 | MP-Φ 用固定仿真集预训练；AP-Cal 只用少量有效回执 | **A-Box + EA-Cal**：增强 = 规范群作用，只接受带「等变证书」的增强；具身重观测提供真实新噪声实现 | 数字增强买方差、不买信息；只有身体能制造新的独立测量 |

**核心命题**：把 ToolGauge 的「外部盲区 → 契约化外部探测 → 摊销校准」升级为
「**身体先标定 → 具身重观测制造信息 → 规范群内增强只做正则 → 证据溯源可传递失效**」。
一句话：**先标定身体，再标定世界；增强只在规范群内合法，且数字增强不创造信息。**

**不变式保持声明**：
- MODGAUGE 五不变式（契约完整性、组合单调性、反作用通道完备、主张绑定、严格退化链）全部保留；
- **新增不变式 I6（增强可容许性）**：任何进入校准/预训练证据集的增强必须携带有效证书 Cert_aug；未认证增强只能进入「正则项」，不得进入「证据项」；
- **新增不变式 I7（溯源真值维护）**：证据图中任一祖先（回执、证书、body_calibration_version）失效，其后代证据必须传递性失效，且不得继续支撑热替换；
- **严格退化链延长**：EmbodiedGauge 失效（身体不可辨识 / ASE 违规 / 证书全失效 / n_eff 不足 / A-Quarantine 暂停）⇒ ToolGauge（只做外部物理探测，不做自探测与增强）⇒ LeanGauge ⇒ MODGAUGE。身体与增强都是增强项，不是依赖项。

## 0. 直觉与动机

### 灵感 1（具身智能 → 身体是第一等测量通道）

直觉：ToolGauge 把盲区全部放在「外部世界」的覆盖矩阵里，默认机器人自己的身体是已知、稳定、免费的测量平台。
但真实具身系统里，**运动学偏置、连杆柔顺、IMU 零偏、相机外参、工具磨损、负载与温漂**共同定义了
「动作 → 观测」的映射；这个映射一旦错了，所有外部回执都会被表达在错误的坐标系里。
具身智能的第一条工程启示因此是：**身体本身就是一把未标定的尺子，自运动是最便宜也最容易被忽视的测量动作。**

由此得到三个设计决定：
(a) 覆盖矩阵从 R_world 扩展为 R_emb = R_world × R_body，身体格子 b=(关节/传感通道/工况) 与外部格子同级；
(b) 新增自探测工具库 T_self（重力姿态、关节换向、腕部旋转、自接触、负载移位、双目自检），
   用持续激励（persistent excitation）让身体参数可辨识；
(c) 身体标定带版本号 body_version；身体漂移时，所有依赖旧版本的增强证书与校准证据**传递性失效**。

### 灵感 2（数据增强 → 增强是规范群作用，不是免费样本）

直觉：数据增强在数据稀缺时几乎总是「有效」的，但它有两种完全不同的作用，工程上经常混为一谈：
(i) **正则/先验**：让模型对 nuisance 变换不变，改善泛化；
(ii) **证据**：把增强样本当成独立观测去收缩后验。
把 (ii) 当真的后果是灾难性的——**伪样本会缩小报告方差，却不缩小真实误差**，这正是 ToolGauge 最怕的「自信地组合错误世界」的增强版。

严谨化的关键是把增强看成**测量算子的规范变换**：g 可容许 ⇔ 存在表示 ρ(g) 使 M(g·x) = ρ(g)·M(x)。
水平翻转在量测对象有手性/文字时不可容许；颜色抖动在颜色本身是 measurand 时不可容许；任意裁剪在会切掉被测物时不可容许。
更关键的是一个「不免费」引理：**对已知可逆变换，已观测样本的增强不增加关于参数的 Fisher 信息**（引理 52）——
增强只能通过「未知 nuisance 边缘化」或「正则」起作用，不能降低 Cramér–Rao 下界。真正的新信息只能来自**具身重观测**：
身体换一个位姿/光照/接触方式重新测一次，得到新的独立噪声实现。

### 灵感 3（合流：身体制造信息，增强只做正则）

合流后的系统不是「给 ToolGauge 加一个增强模块」，而是重新分工：
- **E-Box** 负责「身体是否可信」与「去哪里动一下能获得最多身体信息」；
- **A-Box** 负责「哪些增强是规范变换」与「证书是否仍有效」；
- **EA-Cal** 负责「把具身重观测当证据、把合成增强当正则」，用轨道加权与 n_eff 防止伪样本冒充独立证据；
- **MP-Φ^G** 负责「规范等变」的预训练先验：增强只进等变正则项，物理锚仍是 KL 锚；
- **7C** 把 A（Augment）作为一等阶段插在 E 与 C(alibrate) 之间，并在 V 阶段做「增强一致性」检查。

这样两个灵感词不是并列的两个模块，而是**一条因果链**：身体重观测生产信息 → 证书界定哪些数字变换合法 →
合法增强改善先验与鲁棒性 → 溯源图保证一旦身体错了，所有派生证据一起作废。

## 1. 形式化定义（增量：定义 432–447）

**定义 432（具身覆盖与体感盲区）** 具身覆盖矩阵 R_emb = R_world × R_body，
R_body 以格子 b=(j,k,e) 索引：j 为关节/连杆，k 为传感通道，e=(负载, 温度, 磨损, 速度, 接触模式) 为工况。
身体模型 h_body(a, θ_body) 预测在动作 a 下的本体/外感受观测；body 格子 b 覆盖 ⇔ 存在有效回执 r 使
‖r.obs − h_body(a_r, θ_body)‖ ≤ κ_body·σ_r，且该回执的 body_version 与当前版本一致。
不满足者为**体感盲区** B ⊆ R_body。θ_body ∈ Θ_body ⊂ ℝ^{d_b} 包括运动学偏置、连杆柔顺、IMU 零偏、
相机外参、工具磨损与负载参数。

**定义 433（自探测工具与本体契约）** 自探测工具 t_self = (Schema, Pre, Post, c, τ, ASE, O_t)：
- Schema/Pre/Post 继承定义 416，但 Pre 额外包含关节限位、力矩上限、工作空间、自碰撞与负载包络；
- ASE 为具身安全包络（定义 446）；O_t 为可观测性算子；
- 自探测轨迹 ξ = (a_1,…,a_H) 的观测矩阵 O(ξ) = Σ_{t=1..H} J_tᵀ Σ_obs^{-1} J_t，J_t = ∂h_body/∂θ_body|_{a_t}。
  **持续激励条件**：λ_min(O(ξ)) ≥ ε_obs；不满足则不得宣称任何身体格子被覆盖（防止「动了就算标定」的假覆盖）。
工具库 T_self = {gravity.pose, joint.reversal, wrist.rotate, self.contact, mass.shift, stereo.selfcheck}。

**定义 434（增强规范群与可容许性缺陷）** 设测量算子 M 把场景状态 x 映为观测 y；增强群 G_aug 中元素 g 可容许 ⇔
存在已知可逆表示 ρ(g) 使对所有 x∈D_probe 有 M(g·x)=ρ(g)·M(x)，且标签变换已知。
**可容许性缺陷** δ(g)=sup_{x∈D_probe} ‖M(g·x) − ρ(g)M(x)‖ / scale(x)。
给定阈值 δ*，G_cert = {g : δ(g) ≤ δ*}。D_probe 必须是**物理执行**得到的配对样本（身体真的执行了 g），而不是数字伪造的配对。

**定义 435（增强证书与再验证）** Cert_aug(g) = (g, ρ, D_probe, δ̂(g), CI_δ, n_probe, body_version, expiry, sig)。
证书只在同一 body_version 与未过期时有效；身体漂移（定义 444）或到期触发再验证。
**未认证增强只能进入正则项，不得进入证据项**（不变式 I6）。

**定义 436（具身增强与合成增强）** 对同一场景 x 的轨道 O(x)：
- **具身增强**：g 由身体物理执行，回执含实际动作、测得变换、时间戳、签名 ⇒ 标签变换由本体感觉精确给出，provenance 完整；
- **合成增强**：g 数字作用于已存观测，必须由 Cert_aug 担保；其证据权重按定义 437 折减。
证据集 E = E_phys ⊎ E_syn（物理重观测 ≻ 合成增强），两类样本在溯源图中带不同节点类型。

**定义 437（轨道加权与有效样本量）** 物理样本 i 的轨道 O_i={g·x_i : g∈G_cert}，m_i=|O_i|。
权重 w_{i,g}=1/m_i（或 w_{i,g}=1/(1+(m_i−1)ρ_intra)，ρ_intra 为轨内相关系数）；
有效样本量 n_eff = (Σ_{i,g} w_{i,g})² / Σ_{i,g} w_{i,g}²。
**报告方差不得低于 σ²/n_eff 与物理噪声底 κ_phys 的较大者**；n_eff 小于 N_min 时不得热替换（AugContract）。

**定义 438（轨道共形覆盖）** 在轨道可交换性下（物理样本 i.i.d.；g 的选取独立于标签且 g∈G_cert），
用权重 w 的加权 split-conformal 分位数构造预测集 C，则 P(Y_new∈C) ≥ 1−α；
若每个 g 的可容许缺陷 ≤ δ*，则覆盖 ≥ 1−α−L_M·δ*，L_M 为 score 对观测扰动的 Lipschitz 常数。
覆盖跌破 SLA（继承第 2 轮引理 48 的 1−α−2η′ 口径）⇒ H_s:={UNKNOWN}，退化到 ToolGauge 纯物理路径。

**定义 439（规范等变预训练先验 MP-Φ^G）**
元训练目标：min_θ Σ_m E[−log p(u*_m|ctx_m)] + λ_eq·E_{g∈G_cert}[d(q_θ(g·ctx), ρ(g)q_θ(ctx))] + β_KL·KL(q_θ‖p_phys)。
第一项为任务损失，第二项为规范等变正则，第三项为物理锚。**增强只进入第二项**；
训练数据仍以具身重观测为主，合成增强按 n_eff 降权。保守性夹紧 Σ_θ ≽ κ_phys·I 继承定义 420。
η（sim→real 偏移）由预注册配对校准集估计 η̂，并给出置信区间（修复第 2 轮缺陷 6）。

**定义 440（EA-Cal 具身增强校准）** EA-Cal(receipts, E, certs, body_version)：
① 过滤 body_version 不一致或证书失效的证据；② 构建轨道并按定义 437 加权；③ 计算 n_eff 与报告方差下限；
④ 调 MP-Φ^G 得 (μ,Σ)；⑤ 用定义 438 的加权共形给出预测集与覆盖审计；⑥ 通过 A-Quarantine（定义 443）后输出。
任一环节失败 ⇒ 返回 None，触发退化链，不产生 stub 之外的数值写入。

**定义 441（7C 闭环）** 修复循环 = H → C → E → A → C → V → U：
1. H：发现世界盲区 s 与体感盲区 b；L-Box 给外部假设，E-Box 给身体假设；
2. C：编译 Π_s（可含 T_self）并由 TCV+ASE 验证；
3. E：在 PROBING 态执行，收集物理回执与具身重观测；
4. A：A-Box 认证/复用证书，构建轨道，去重，计算 n_eff，跑 A-Quarantine；
5. C：EA-Cal 输出摊销后验与共形预测集；
6. V：**三条独立检查**——跨通道独立回执、增强一致性（后验在 G_cert 下等变）、契约回归；
7. U：热替换 + 语言修复证书（定义 427 扩展为引用回执与证书）+ 溯源图更新。
V 失败 ⇒ 夹紧重试 1 次 ⇒ 再失败 stub + RED。

**定义 442（AugContract 增强预算契约）** AC = (B_aug, m_max, n_eff_min, τ_aug, recovery)：
增强探针预算、单轨最大长度、最小有效样本量、增强阶段时延上限、恢复条件（预算耗尽 / n_eff 不足 / 证书全失效 ⇒ stub + RED + 排队）。
AC 是 TB-Contract（定义 424）的增强级细化，时序结论继承引理 50 与引理 56。

**定义 443（A-Quarantine 增强泄漏监控）** 维护两个统计量：
(i) **收缩比** ρ_shrink = 报告方差下降 / 物理证据支持的方差下降；
(ii) **物理留出覆盖率** ĉov = 在未参与拟合的物理回执上的经验覆盖率。
用双侧 CUSUM/SPRT 监控 (ρ_shrink−1) 与 (ĉov−(1−α))；若 ρ_shrink>1+τ 或 ĉov<1−α−ε，
判定合成增强正在伪造证据：丢弃全部 E_syn，只用 E_phys 重新校准；连续 q 次触发 ⇒ 暂停 A-Box 并重认证。
A-Quarantine 是「增强版 P-Quarantine」，专防**伪样本冒充独立证据**。

**定义 444（B-Quarantine 体感漂移监控）** 对 θ_body 的后验残差序列做双侧 CUSUM；漂移超包络 ⇒
body_version ← body_version+1，**所有依赖旧 body_version 的回执、证书、增强样本、校准后验传递性失效**；
系统退回 ToolGauge，直到重新自标定通过定义 433 的持续激励门槛。这是「身体错了，所有增强一起错」的在线断路器。

**定义 445（证据溯源图与真值维护）** 证据图 DAG 节点类型：
physical_receipt、self_probe_receipt、aug_certificate、augmented_point、body_calibration、posterior、claim。
边表示「由…派生」。每个节点记录祖先集合与最小 body_version。
失效规则：任一祖先失效 ⇒ 后代递归失效；失效为单调操作（失效节点不得被后续步骤重新激活，除非显式重测并生成新节点）。
**热替换的前置条件**：支撑该替换的所有证据节点均有效，且至少有一条 physical_receipt 不在任何增强轨道内。

**定义 446（具身安全包络 ASE 与有界残余副作用）**
自探测/物理增强必须满足：关节力矩 ≤ τ_max、速度 ≤ v_max、工作空间 ⊆ W_safe、接触力 ≤ F_max、无自碰撞；
执行期间系统处于显式 PROBING 态（继承定义 430），带看门狗与可中断点。
**修正第 2 轮「零副作用」的过度主张**：任何真实探测都有副作用；我们只保证「无未登记副作用」，
且中止后的残余运动/扰动 ≤ RS-Envelope（由 ASE 与制动距离给出上界），并写入回执。

**定义 447（退化链与继承）** 未被重定义的第 2 轮记号沿用定义 416–431。
退化条件与顺序：EmbodiedGauge 失效（身体不可辨识 / ASE 违规 / 证书全失效 / n_eff<n_eff_min / A-Quarantine 暂停）
⇒ ToolGauge（仅外部物理探测，G={id}，无自探测）⇒ LeanGauge ⇒ MODGAUGE。
形式化退化：令 T_self=∅、G_cert={id}、body_version 固定且 λ_min(O)<ε_obs ⇒ EmbodiedGauge ≡ ToolGauge。

## 2. 关键算法骨架

```python
# IP-321 E-Box：体感盲区 + 自标定（含可辨识性门槛）
@dataclass
class SelfProbe:
    name: str
    schema: Callable[[dict], bool]
    pre: Callable[[Snapshot], bool]          # 含 ASE：力矩/限位/自碰撞
    post: Callable[[Raw], "Receipt | None"]
    cost: float; tau: float
    jacobian: Callable[[dict, "ThetaBody"], "Matrix"]

class EBox:
    def detect(self, R_world, R_body, body_version):
        return [b for b in R_body
                if (not covered(b, body_version))
                or body_residual(b) > KAPPA_BODY * sigma(b)]      # 定义 432

    def plan_self_calibration(self, B, budget):
        xi = argmax_xi(expected_info(theta_body, y_xi))           # 信息增益
        if lambda_min(observability(xi)) < EPS_OBS:
            return None                                           # 不可辨识 ⇒ 保持盲区
        if (not ase_ok(xi)) or cost(xi) > budget:
            return None                                           # 定义 433/446
        return xi

# IP-322 A-Box：增强规范群 + 证书
class ABox:
    def certify(self, g, probe_pairs, body_version):
        d_hat, ci = equivariance_residual(g, probe_pairs)         # 定义 434
        if d_hat + ci > DELTA_STAR:
            return None                                           # 不可容许
        return Cert(g=g, rho=g.rho, d_hat=d_hat, ci=ci,
                    n=len(probe_pairs), body_version=body_version,
                    expiry=NOW + TTL, sig=sign(g, d_hat))

    def build_orbit(self, x, certs):
        return [(c.g, c.rho @ x, c) for c in certs if valid(c)]   # 定义 436/437

# IP-323 EA-Cal：轨道加权 + 有效样本量 + 覆盖审计
class EACal:
    def calibrate(self, receipts, orbits, certs, body_version):
        ev = [e for e in merge(receipts, orbits)
              if (not e.is_syn)
              or (valid(e.cert) and e.body_version == body_version)]  # 定义 440.①
        if not ev:
            return None
        w = orbit_weights(ev)                                     # w = 1/m_i
        n_eff = (sum(w) ** 2) / sum(wi ** 2 for wi in w)          # 定义 437
        if n_eff < self.contract.n_eff_min:
            return None                                           # AugContract
        mu, Sig = self.mp_phi_G(featurize_ctx(ev, receipts))      # 定义 439
        Sig = clamp_min(Sig, max(KAPPA_PHYS, SIGMA2 / n_eff))     # 方差下限
        cov = weighted_conformal(ev, w, alpha=self.alpha)         # 定义 438
        if not self.aquar.check(Sig, n_eff, cov):
            return None                                           # 定义 443
        return mu, Sig, cov

# IP-324 MP-Φ^G：规范等变预训练（增强只进正则项）
class MPPhiG:
    def loss(self, batch):
        task = -log_likelihood(self.theta, batch.ctx, batch.u_star)
        eq   = mean(d(self.theta(g @ batch.ctx), g.rho @ self.theta(batch.ctx))
                    for g in batch.certified)
        kl   = kl(self.theta, PHYSICAL_PRIOR)
        return task + LAMBDA_EQ * eq + BETA_KL * kl                # 定义 439

# IP-325 7C 闭环（含 A 阶段与溯源失效）
def embodied_7c(M, s):
    H_world = M.lbox.hypothesize(s, M.dbox.R_world[s])            # H
    B_body  = M.ebox.detect(M.dbox.R_world, M.dbox.R_body, M.body_version)
    prog    = M.tbox.compile(H_world, B_body, M.tools, M.t_self)  # C
    if not (tcv_ok(prog) and ase_ok(prog)):                        # 定义 441.2/446
        return stub_and_red(s, "unsafe_or_invalid_program")
    receipts, embodied = M.tcv.execute(prog, M.env)                # E（PROBING）
    certs    = M.abox.certify_or_reuse(embodied, M.body_version)   # A
    orbits   = M.abox.build_orbit_from(receipts, certs)
    ea       = M.eacal.calibrate(receipts, orbits, certs, M.body_version)  # C
    if ea is None:
        return stub_and_red(s, "insufficient_effective_evidence")
    mu, Sig, cov = ea
    new_ec = M.apcal.update_contract(M.dpe, mu, Sig, s)
    if not (M.apcal.cross_validate(mu, Sig, M.cross_receipt_indep(s))      # V.1
            and M.eacal.aug_consistent(mu, Sig, certs)                     # V.2
            and contract_regression(new_ec)):                              # V.3
        return stub_and_red(s, "verification_failed")
    M.mreg.hot_replace(M.dpe, new_ec)                              # U
    M.dbox.update_from_posterior(s, mu, Sig)
    M.provenance.bind(new_ec, receipts, certs, orbits, M.body_version)   # 定义 445
    bind_claims(new_ec, H_world, B_body, receipts, certs)          # 定义 427 扩展
    M.aquar.record(reported_shrink(Sig, n_eff), physical_shrink(receipts), cov)
    return True

# IP-326 主闭环：身体漂移 ⇒ 版本升级 + 传递失效
def EmbodiedGauge_round(M, obs, audio, tac, depth, det):
    if M.bquar.triggered():                                        # 定义 444
        M.body_version += 1
        M.provenance.invalidate_older_than(M.body_version)         # 传递失效
        M.abox.invalidate_all(); M.eacal.use_physical_only = True
        M.ebox.request_recalibration()
    for s in M.dbox.detect_blind_spot():
        if s not in M.inflight:
            M.inflight.add(s); submit_async(embodied_7c, M, s)     # 离开 50Hz
    return MODGAUGE_round(M, obs, audio, tac, depth, det)          # 主控不变
```

## 3. 推导

**引理 51（自标定的可辨识性与误差界）** 设 y_t = h_body(a_t, θ*) + ε_t，ε_t 独立 σ-亚高斯，
J_t=∂h_body/∂θ_body。若轨迹 ξ 满足 λ_min(O(ξ)) ≥ ε_obs > 0，则加权最小二乘估计 θ̂ 满足
‖θ̂−θ*‖₂ ≤ (2σ/λ_min(O))·√(d_b·log(2d_b/δ)) + O(ℓ·r²)
以概率 ≥1−δ，其中 ℓ 为 h_body 的 Lipschitz 常数、r 为线性化半径。
证明：局部线性化 → 加权最小二乘 → 矩阵 Chernoff 下界 λ_min(O) → 二次型控制；非线性项由 ℓ、r 吸收。
系：λ_min<ε_obs 的自探测**不得**把任何 body 格子标记为已覆盖；不可辨识参数只能留在先验中。
这把第 2 轮「有回执即证据」的漏洞堵到身体层：动了不等于标定成功。

**引理 52（已知可逆增强的信息中性）** 设 g 已知、ρ(g) 可逆，且 y'=ρ(g)y 是 y 的确定性函数。
则 Fisher 信息 I(θ; y, y') = I(θ; y)，增强似然 p(y|θ)p(y'|θ) 的 Fisher 矩阵只增加一个秩亏项。
故**对固定数据集的数字增强不能降低 θ 的 Cramér–Rao 下界**。
证明：y' 不含超出 y 的新随机性；对 (y,y') 的联合分布做变量替换即可。
系 52.1：数字增强只能通过 (i) 未知 nuisance 的边缘化、(ii) 正则/先验、(iii) 鲁棒性起作用；
真正的信息增量只能来自**新的物理噪声实现**——这正是 E-Box 与具身重观测的理论依据。
系 52.2：若增强 g 的分布依赖 θ（例如 g 由含噪执行产生且噪声与 θ 耦合），则信息可能增加；
该情形必须显式建模，不能默默把增强当独立样本。

**引理 53（轨道共形的覆盖保持）** 在轨道可交换性下，加权 split-conformal（权重 w=1/m_i）满足
P(Y_new∈C) ≥ 1−α；若所有 g∈G_cert 的缺陷 ≤δ*，则覆盖 ≥ 1−α−L_M·δ*。
证明：加权可交换性给出加权分位数的有限样本覆盖；缺陷把 score 的最大扰动限制为 L_M·δ*，用三角不等式吸收。
系：δ*=0 时退化为标准共形（第 2 轮引理 48）；δ*>0 时覆盖保证按可容许性缺陷线性折减，
因此证书的 CI_δ 必须进入覆盖账本，而不是只报告名义 1−α。

**引理 54（增强泄漏的偏差-方差界）** 设有效证据中合成增强占比 p，合成样本共享偏差 b 与轨内相关 ρ_intra，
物理样本 n_phys、噪声 σ。则后验均值误差满足
E‖μ̂−μ*‖ ≤ (1−p)·σ/√n_phys + p·b + O(ρ_intra)，
而报告方差可低至 σ²/n_eff（n_eff 最高约 n_phys/(1−p)）。
故当 b>0 时，**更多增强不能把均值误差压到 p·b 以下**；报告方差却可以继续缩小——这就是「增强泄漏」。
证明：偏差-方差分解 + 轨内相关系数对 n_eff 的折减；偏差项与样本量无关。
系：必须用物理留出集做覆盖率审计（A-Quarantine），否则系统会对伪证据过度自信。

**引理 55（具身重观测的样本效率优势）** 场景潜变量 z 共享，观测 y=z+ε，Var(z)=τ²，Var(ε)=σ²，
轨内相关 ρ=τ²/(τ²+σ²)。m 次独立重观测的均值有效样本量 n_eff^emb = m/(1+(m−1)ρ)；
而数字增强副本共享同一 ε，ρ=1 ⇒ n_eff^syn=1。
故 n_eff^emb ≥ n_eff^syn，等号仅当 m=1 或 ρ=1。
证明：随机效应方差分解 / 设计效应（design effect）。
系：具身重观测的价值不是「多了一个变换」，而是「多了一次独立噪声实现」；
这也解释了为什么 A-Box 必须给合成增强降权、为什么 E-Box 是信息源而 A-Box 只是合法化器。

**引理 56（7C 的时序、预算与安全）** 自探测与增强证书都在 50Hz 路径之外异步执行；
50Hz 周期只新增回执验证与 body_version 比较，O(1)<0.2ms；
单盲区 7C 时延 ≤ Στ_self + τ_probe + τ_cert + τ_EA ≤ τ_aug + τ_repair（AugContract 界定）；
ASE 违规或看门狗触发时中止，残余扰动 ≤ RS-Envelope。
**修正**：不存在「零副作用」；存在的是「有界且已登记的残余副作用」。硬实时（引理 45）与预算不变式保持。

**引理 57（五不变式与退化链保持）** 增强节点只在 A 阶段进入，且必须带有效证书或仅进入正则项；
溯源失效是单调的，不会重新激活旧证据；V 阶段三条检查全过才允许热替换；
退化映射 T_self=∅、G_cert={id} ⇒ EmbodiedGauge ≡ ToolGauge，故 MODGAUGE 五不变式与第 2 轮引理 49/50 全部保持。
证明：对 7C 各阶段做结构归纳；数值路径只读取通过有效性过滤的证据节点；claims 仍为纯投影。

## 4. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| body 覆盖扫描 | 50Hz 内联 | O(1) 残差查表 + O(\|R_body\|) 异步 | O(\|R_body\|) | 定义 432 |
| 自探测规划 | 异步 | O(H·d_b² + \|T_self\|·d_b) ≈ 10–50ms | O(d_b²) | 定义 433、引理 51 |
| 物理探测 | 物理域 | Στ ≤ B_aug（秒级） | O(H) | ASE、定义 446 |
| 证书验证 | 异步 | O(n_probe·d) 每 g，缓存 | O(\|G_cert\|) | 定义 434/435 |
| 轨道构建 | 异步 | O(N·m) | O(N·m) | 定义 437 |
| EA-Cal | 异步 | O(n_eff·d_ctx) 单前向 < 10ms | O(d_ctx) | 定义 440、引理 53 |
| A/B Quarantine | 异步 | O(1) CUSUM | O(K) | 定义 443/444 |
| 溯源失效 | 异步 | 摊还 O(\|D\|)（版本索引） | O(\|D\|) | 定义 445 |
| U 热替换 | 计量域 | < 1ms | O(1) | 引理 57 |

**相对第 2 轮**：50Hz 路径没有新增重计算（只多一次 body_version 比较）；新增成本集中在异步的自探测、证书验证与轨道构建。
物理探测是「真信息」的代价，不能像数字增强那样免费复制；AugContract 用预算显式买这份信息。

## 5. 对第 2 轮缺陷的审计与修复清单

| # | 第 2 轮缺陷 | 本轮处置 |
|---|---|---|
| 1 | 引理 46 系「TCV 拒绝/闸门未过 ⇒ 零副作用」过度主张：探测本身有物理副作用，前缀执行也有 | 定义 446：ASE + RS-Envelope，改称「无未登记副作用」；引理 56 给界 |
| 2 | V 阶段「独立回执」只断言未定义；cross.modal 与主通道可能共模 | 定义 445：provenance-disjoint + 通道独立；共模偏差 b_cm 进入覆盖账本 |
| 3 | TCV 伪代码只查扁平列表，定义 418 允许 DAG，但未做引用存在性/类型校验 | 定义 433/441：类型化数据流图验证，未解析引用直接拒绝；循环检测按声明等价类 |
| 4 | AP-Cal cross_validate 用标量 z，Sig 实为协方差；`last_gain` 未赋值 | 定义 440/443：Mahalanobis 距离；预测/实际收缩比显式计算并记录 |
| 5 | P-Quarantine 只看符号游程，忽略幅度与慢漂移，K=q=3 未校准，且无恢复准则 | 定义 443/444：双侧 CUSUM/SPRT + ARL 校准 + 恢复条件；新增 B-Quarantine |
| 6 | 引理 47 的 η 只声明不估计；M→∞、N_bl=1 的表述掩盖 d_u 与有限样本修正 | 定义 439：η̂ 估计协议（配对校准集 + 有效样本量 + CI）；CI 过宽则判定界不可用，不得进入安全论证 |
| 7 | 定义 426 在 ε≥σ_0 时右侧为负，且 σ_obs 未知时不可用；「证据不足」无饥饿界 | 定义 437：n_eff/σ_obs 在线估计，n_min=max(0,·)+夹紧；给出预算内饥饿概率上界 |

## 6. 本轮最大风险（一句话）

**一句话**：EmbodiedGauge 的**证书-先验-溯源三层共享同一个 body_version 依赖**——一次未被 B-Quarantine 及时捕获的身体标定偏差，
会同时污染所有以该版本签发的增强证书、规范等变先验与校准后验，使「局部修复、误差局部化」的安全论证整体失效；
而证书与溯源图会让这些伪证据显得比裸猜测更可信（E443/E446/E452/E454 为证伪实验，B-Quarantine + A-Quarantine + 物理留出覆盖审计为三重断路器）。

**次级风险与缓解**：
1. **身体不可辨识** → 引理 51 门槛直接保持盲区，不产生假覆盖；
2. **增强泄漏** → A-Quarantine + 物理留出覆盖率审计 + n_eff 方差下限；
3. **证书过期/漂移** → TTL + body_version + 再认证；
4. **自探测物理风险** → ASE + PROBING 显式态 + 看门狗 + RS-Envelope；
5. **溯源图爆炸** → 版本索引 + 轨道去重 + 摊还失效；
6. **过度依赖合成增强的正则价值** → MP-Φ^G 的 λ_eq 与物理锚 KL 夹紧；
7. **退化切换抖动** → 滞回 + 最小驻留时间。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 3 轮产物 · 创新点清单 v3：**EmbodiedGauge**（Embodied Re-observation with Gauge-Certified Augmentation）

> 背景：第 2 轮 ToolGauge（IP-315–320）把 LeanGauge 的盲区修复升级为「语义假设 → 契约化工具调用 → 摊销校准」，
> 但仍遗留三个结构性弱点：**身体被默认为已知且稳定的测量平台**；**数据增强只被当作数据量，未被审计**；
> **证据独立性只靠断言**。本轮以「具身智能 × 数据增强」为灵感，在 ToolGauge 之上做增量升级：
>
> **集成链：MODGAUGE ⊃ LeanGauge ⊃ ToolGauge ⊃ EmbodiedGauge。**
> 身体是第一等测量通道（E-Box），增强是带证书的规范群作用（A-Box），
> 具身重观测生产新信息、数字增强只做正则与合法化（EA-Cal / MP-Φ^G），
> 证据溯源图保证身体版本一变、所有派生证据传递性失效。
> IP 编号：IP-321–326（共 6 个）。定义增量 432–447；引理增量 51–57；实验增量 E441–E456。
> 理论姿态：不改变 MODGAUGE 五不变式，新增 I6（增强可容许性）与 I7（溯源真值维护），退化链延长一级。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进（相对 ToolGauge） |
|---|---|---|---|
| IP-321 | E-Box 具身覆盖与自标定 | 核心模块 | 覆盖矩阵扩为 R_world×R_body；自探测轨迹受可观测性门槛 λ_min(O)≥ε_obs 约束；不可辨识就不覆盖 |
| IP-322 | A-Box 增强规范群与证书 | 核心模块 | 增强 = 测量算子规范变换；δ(g)≤δ* 才发证书；未认证增强只进正则、不进证据 |
| IP-323 | EA-Cal 轨道感知具身增强校准 | 核心模块 | 轨道加权 + n_eff + 方差下限 + 物理留出覆盖率审计；防止伪样本冒充独立证据 |
| IP-324 | MP-Φ^G 规范等变预训练先验 | 核心模块 | 增强只进等变正则项；物理锚 KL 保留；η̂ 有估计协议与 CI；先验质量可审计 |
| IP-325 | EmbodiedGauge-7C 闭环 | 设计模式 | H→C→E→A→C→V→U；A 为一等阶段；V 增加「增强一致性」检查；语言证书引用回执+证书 |
| IP-326 | EmbodiedGauge 主闭环 | 集成 | 50Hz 路径不动；B-Quarantine 触发 body_version 升级与传递失效；退化链 EmbodiedGauge→ToolGauge→LeanGauge→MODGAUGE |

**退化链声明**：身体不可辨识 / ASE 违规 / 证书全失效 / n_eff 不足 / A-Quarantine 暂停 ⇒ ToolGauge（仅外部物理探测，G={id}）；
ToolGauge 再失效 ⇒ LeanGauge ⇒ MODGAUGE。身体与增强都是增强项，不是依赖项（引理 57）。

**一句话主张**：**先标定身体，再标定世界；增强只在规范群内合法，且数字增强不创造信息。**

## 1. 符号体系增量（定义 432–447）

| 符号 | 含义 |
|---|---|
| `R_emb = R_world × R_body` | 具身覆盖矩阵；body 格子 `b=(j,k,e)` = 关节/传感通道/工况（定义 432） |
| `θ_body, Θ_body, d_b` | 身体参数（运动学偏置、柔顺、IMU 零偏、外参、磨损、负载）及其空间/维度 |
| `h_body(a, θ_body)` | 身体模型：动作 → 本体/外感受预测 |
| `T_self` | 自探测工具库：gravity.pose / joint.reversal / wrist.rotate / self.contact / mass.shift / stereo.selfcheck |
| `O(ξ), λ_min(O), ε_obs` | 自探测轨迹的可观测性 Gramian、最小特征值与持续激励门槛（定义 433） |
| `G_aug, ρ(g), δ(g), δ*` | 增强群、表示、可容许性缺陷与阈值；`G_cert={g:δ(g)≤δ*}`（定义 434） |
| `Cert_aug(g)` | 增强证书 `(g,ρ,δ̂,CI_δ,n_probe,body_version,expiry,sig)`（定义 435） |
| `E_phys / E_syn` | 具身重观测证据 / 合成增强证据（定义 436） |
| `O_i, m_i, w_{i,g}, n_eff` | 轨道、轨道长度、轨道权重、有效样本量（定义 437） |
| `MP-Φ^G` | 规范等变预训练先验（定义 439） |
| `EA-Cal` | 具身增强校准器（定义 440） |
| `7C` | H→C→E→A→C→V→U 七段闭环（定义 441） |
| `AC=(B_aug,m_max,n_eff_min,τ_aug,recovery)` | AugContract 增强预算契约（定义 442） |
| `A-Quarantine / B-Quarantine` | 增强泄漏监控 / 体感漂移监控（定义 443/444） |
| `DAG(D), body_version` | 证据溯源图与身体标定版本（定义 445） |
| `ASE, RS-Envelope` | 具身安全包络与有界残余副作用（定义 446） |
| `ρ_intra` | 轨内相关系数；`n_eff = (Σw)²/Σw²` |

## 2. 形式化定义（要点）

**定义 432（具身覆盖/体感盲区）** body 格子 b 覆盖 ⇔ 存在有效回执 r 使 `‖r.obs−h_body(a_r,θ_body)‖ ≤ κ_body·σ_r` 且 `r.body_version` 为当前版本；否则 b 属于体感盲区 B。
**定义 433（自探测契约）** 自探测 = 带 ASE 前置条件的工具调用；轨迹必须满足 `λ_min(O(ξ))≥ε_obs`，否则不得宣称覆盖（动了 ≠ 标定成功）。
**定义 434（增强可容许性）** g 可容许 ⇔ `M(g·x)=ρ(g)M(x)`（ρ 已知可逆、标签变换已知）；缺陷 `δ(g)=sup‖M(g·x)−ρ(g)M(x)‖/scale`；D_probe 必须物理执行得到。
**定义 435（增强证书）** 证书绑定 g、ρ、δ̂、CI_δ、探针数、body_version、TTL 与签名；过期或 body_version 变化即失效。
**定义 436（具身 vs 合成增强）** 具身增强由身体真实执行、provenance 完整；合成增强必须持证，且证据权重按 n_eff 折减。
**定义 437（轨道加权/n_eff）** `w=1/m_i` 或 `1/(1+(m_i−1)ρ_intra)`；`n_eff=(Σw)²/Σw²`；报告方差 ≥ max(κ_phys, σ²/n_eff)。
**定义 438（轨道共形）** 轨道可交换下覆盖 ≥1−α；缺陷 δ* 使覆盖折减为 ≥1−α−L_M·δ*；跌破 SLA ⇒ H_s={UNKNOWN}。
**定义 439（MP-Φ^G）** `min_θ Σ E[−log p(u*|ctx)] + λ_eq·E_g[d(q_θ(g·ctx),ρ(g)q_θ(ctx))] + β_KL·KL(q_θ‖p_phys)`；增强只进第二项；η̂ 带 CI。
**定义 440（EA-Cal）** 过滤失效证据 → 轨道加权 → n_eff 与方差下限 → MP-Φ^G → 加权共形 → A-Quarantine 通过才输出。
**定义 441（7C）** H（世界+身体假设）→ C（TCV+ASE 编译）→ E（PROBING 执行）→ A（认证/建轨/去重/审计）→ C（EA-Cal）→ V（跨通道独立回执 + 增强一致性 + 回归）→ U（热替换 + 语言证书 + 溯源更新）。
**定义 442（AugContract）** 增强预算 B_aug、轨长 m_max、n_eff_min、时延 τ_aug、恢复条件；TB-Contract 的增强级细化。
**定义 443（A-Quarantine）** 监控收缩比 ρ_shrink 与物理留出覆盖率 ĉov；异常 ⇒ 丢弃 E_syn，只用 E_phys 重校准；连续 q 次 ⇒ 暂停 A-Box。
**定义 444（B-Quarantine）** 对 θ_body 残差做双侧 CUSUM；漂移 ⇒ body_version+1，旧版本派生证据传递性失效，退回 ToolGauge。
**定义 445（溯源真值维护）** 证据 DAG 节点含 physical_receipt / self_probe_receipt / aug_certificate / augmented_point / body_calibration / posterior / claim；祖先失效 ⇒ 后代递归失效；热替换要求至少一条非轨道内物理回执。
**定义 446（ASE/RS-Envelope）** 力矩、速度、工作空间、接触力、自碰撞约束；PROBING 态 + 看门狗 + 可中断；无「零副作用」，只有「无未登记副作用」与有界残余。
**定义 447（退化链/继承）** `T_self=∅, G_cert={id}` ⇒ EmbodiedGauge ≡ ToolGauge；再退化到 LeanGauge / MODGAUGE。

## 3. 关键算法骨架

```python
# IP-321 E-Box：体感盲区 + 可辨识性约束的自标定
class EBox:
    def detect(self, R_world, R_body, body_version):
        return [b for b in R_body
                if (not covered(b, body_version))
                or body_residual(b) > KAPPA_BODY * sigma(b)]
    def plan_self_calibration(self, B, budget):
        xi = argmax_xi(expected_info(theta_body, y_xi))
        if lambda_min(observability(xi)) < EPS_OBS: return None   # 不可辨识 ⇒ 保持盲区
        if (not ase_ok(xi)) or cost(xi) > budget: return None
        return xi

# IP-322 A-Box：规范群 + 证书（未认证只进正则）
class ABox:
    def certify(self, g, probe_pairs, body_version):
        d_hat, ci = equivariance_residual(g, probe_pairs)
        if d_hat + ci > DELTA_STAR: return None
        return Cert(g, g.rho, d_hat, ci, len(probe_pairs),
                    body_version, expiry=NOW+TTL, sig=sign(g, d_hat))
    def build_orbit(self, x, certs):
        return [(c.g, c.rho @ x, c) for c in certs if valid(c)]

# IP-323 EA-Cal：轨道加权 + n_eff + 覆盖审计
class EACal:
    def calibrate(self, receipts, orbits, certs, body_version):
        ev = [e for e in merge(receipts, orbits)
              if (not e.is_syn) or (valid(e.cert) and e.body_version == body_version)]
        if not ev: return None
        w = orbit_weights(ev)                                   # 1/m_i
        n_eff = (sum(w) ** 2) / sum(wi ** 2 for wi in w)
        if n_eff < self.contract.n_eff_min: return None
        mu, Sig = self.mp_phi_G(featurize_ctx(ev, receipts))
        Sig = clamp_min(Sig, max(KAPPA_PHYS, SIGMA2 / n_eff))
        cov = weighted_conformal(ev, w, alpha=self.alpha)
        return (mu, Sig, cov) if self.aquar.check(Sig, n_eff, cov) else None

# IP-324 MP-Φ^G：增强只进等变正则
def mp_phi_g_loss(theta, batch):
    task = -log_likelihood(theta, batch.ctx, batch.u_star)
    eq   = mean(d(theta(g @ batch.ctx), g.rho @ theta(batch.ctx))
                for g in batch.certified)
    return task + LAMBDA_EQ * eq + BETA_KL * kl(theta, PHYSICAL_PRIOR)

# IP-325 7C 闭环
def embodied_7c(M, s):
    H = M.lbox.hypothesize(s, M.dbox.R_world[s])                  # H
    B = M.ebox.detect(M.dbox.R_world, M.dbox.R_body, M.body_version)
    prog = M.tbox.compile(H, B, M.tools, M.t_self)                # C
    if not (tcv_ok(prog) and ase_ok(prog)):
        return stub_and_red(s, "unsafe_or_invalid_program")
    receipts, embodied = M.tcv.execute(prog, M.env)               # E（PROBING）
    certs  = M.abox.certify_or_reuse(embodied, M.body_version)    # A
    orbits = M.abox.build_orbit_from(receipts, certs)
    ea     = M.eacal.calibrate(receipts, orbits, certs, M.body_version)  # C
    if ea is None: return stub_and_red(s, "insufficient_effective_evidence")
    mu, Sig, cov = ea
    new_ec = M.apcal.update_contract(M.dpe, mu, Sig, s)
    if not (M.apcal.cross_validate(mu, Sig, M.cross_receipt_indep(s))    # V.1
            and M.eacal.aug_consistent(mu, Sig, certs)                   # V.2
            and contract_regression(new_ec)):                            # V.3
        return stub_and_red(s, "verification_failed")
    M.mreg.hot_replace(M.dpe, new_ec)                             # U
    M.dbox.update_from_posterior(s, mu, Sig)
    M.provenance.bind(new_ec, receipts, certs, orbits, M.body_version)
    bind_claims(new_ec, H, B, receipts, certs)
    M.aquar.record(reported_shrink(Sig, n_eff), physical_shrink(receipts), cov)
    return True

# IP-326 主闭环：body 漂移 ⇒ 版本升级 + 传递失效
def EmbodiedGauge_round(M, obs, audio, tac, depth, det):
    if M.bquar.triggered():
        M.body_version += 1
        M.provenance.invalidate_older_than(M.body_version)
        M.abox.invalidate_all(); M.eacal.use_physical_only = True
        M.ebox.request_recalibration()
    for s in M.dbox.detect_blind_spot():
        if s not in M.inflight:
            M.inflight.add(s); submit_async(embodied_7c, M, s)
    return MODGAUGE_round(M, obs, audio, tac, depth, det)
```

## 4. 推导

**引理 51（自标定可辨识性）** 在局部线性化与 σ-亚高斯噪声下，若 `λ_min(O(ξ))≥ε_obs`，则
`‖θ̂−θ*‖₂ ≤ (2σ/λ_min(O))√(d_b log(2d_b/δ)) + O(ℓr²)` 以概率 ≥1−δ。
系：`λ_min<ε_obs` 的自探测不得标记任何 body 格子为已覆盖；不可辨识参数只能留在先验中。

**引理 52（已知可逆增强的信息中性）** 对已知可逆 g，`y'=ρ(g)y` 是 y 的确定性函数，故
`I(θ;y,y')=I(θ;y)`；增强似然只增加秩亏 Fisher 项。**数字增强不能降低 Cramér–Rao 下界。**
系 52.1：数字增强只通过未知 nuisance 边缘化、正则/先验、鲁棒性起作用；真正信息增量来自新的物理噪声实现。
系 52.2：若 g 的分布依赖 θ（含噪执行且噪声与 θ 耦合），信息可能增加；必须显式建模，不能默默当独立样本。

**引理 53（轨道共形覆盖）** 轨道可交换 + 权重 1/m_i ⇒ 覆盖 ≥1−α；可容许缺陷 ≤δ* ⇒ 覆盖 ≥1−α−L_M·δ*。
系：δ*=0 退化为第 2 轮引理 48；证书 CI_δ 必须进入覆盖账本。

**引理 54（增强泄漏偏差-方差界）** 合成增强占比 p、共享偏差 b、轨内相关 ρ_intra、物理样本 n_phys、噪声 σ：
`E‖μ̂−μ*‖ ≤ (1−p)σ/√n_phys + p·b + O(ρ_intra)`，而报告方差可低至 σ²/n_eff（n_eff≤n_phys/(1−p)）。
系：b>0 时增强不能把均值误差压到 p·b 以下；必须做物理留出覆盖率审计（A-Quarantine）。

**引理 55（具身重观测样本效率）** 共享场景潜变量 z、独立噪声 ε，轨内相关 ρ=τ²/(τ²+σ²)；
m 次具身重观测 `n_eff^emb=m/(1+(m−1)ρ)`，而数字增强副本 ρ=1 ⇒ `n_eff^syn=1`。故 `n_eff^emb≥n_eff^syn`。
系：具身重观测的价值是「新的独立噪声实现」，不是「多了一个变换」。

**引理 56（7C 时序/预算/安全）** 自探测与证书全异步于 50Hz 路径外；周期新增 O(1)<0.2ms；
单盲区时延 ≤ τ_aug+τ_repair；ASE/看门狗中止后残余扰动 ≤ RS-Envelope。修正「零副作用」为「有界且已登记的残余副作用」。

**引理 57（不变式/退化链）** 增强只在 A 阶段进入且受证书门控；溯源失效单调；V 三检查全过才热替换；
`T_self=∅, G_cert={id}` ⇒ EmbodiedGauge≡ToolGauge；故五不变式与第 2 轮引理 49/50 保持。

## 5. 复杂度分析

| 组件 | 域 | 时间 | 空间 | 正确性锚 |
|---|---|---|---|---|
| body 覆盖扫描 | 50Hz 内联 | O(1) 查表 + O(\|R_body\|) 异步 | O(\|R_body\|) | 定义 432 |
| 自探测规划 | 异步 | O(H·d_b²+\|T_self\|d_b) ≈10–50ms | O(d_b²) | 定义 433、引理 51 |
| 物理探测 | 物理域 | Στ≤B_aug（秒级） | O(H) | 定义 446 |
| 证书验证 | 异步 | O(n_probe·d)/g，缓存 | O(\|G_cert\|) | 定义 434/435 |
| 轨道构建 | 异步 | O(N·m) | O(N·m) | 定义 437 |
| EA-Cal | 异步 | O(n_eff·d_ctx)<10ms | O(d_ctx) | 定义 440、引理 53 |
| A/B Quarantine | 异步 | O(1) CUSUM | O(K) | 定义 443/444 |
| 溯源失效 | 异步 | 摊还 O(\|D\|) | O(\|D\|) | 定义 445 |
| U 热替换 | 计量域 | <1ms | O(1) | 引理 57 |

**相对第 2 轮**：50Hz 路径无新增重计算；新增成本在异步的自探测、证书、轨道与溯源。
数字增强可免费复制但信息中性；物理重观测有成本但带来真信息，AugContract 用预算显式购买后者。

## 6. 实验设计 E441–E456（RAS-Baselines v4 协议）

| 实验 | 核心问题 | 关键目标 |
|---|---|---|
| E441 | 体感盲区检测与自标定收敛 | θ_body 误差按 1/√n 下降；body 盲区召回 ≥95% |
| E442 | 可辨识性门槛 | λ_min<ε_obs 时不产生假覆盖；不可辨识参数 0 误报 |
| E443 | 增强证书有效性 | 不可容许变换拒绝率 ≥95%；δ̂ 的 CI 覆盖率 ≥90% |
| E444 | 数字增强信息中性验证 | 固定数据集增强不改善 CRLB；与引理 52 一致 |
| E445 | 具身 vs 合成增强 | 同预算下 n_eff^emb ≥ 2× n_eff^syn；样本效率显著 |
| E446 | 增强泄漏/覆盖审计 | 伪证据注入下 A-Quarantine 检出 ≥90%，覆盖不膨胀 |
| E447 | 轨道共形覆盖 | 名义 ≥0.9；δ*>0 时按 L_M·δ* 折减且不低于 SLA |
| E448 | MP-Φ^G 泛化 | M_eff 随认证增强提升；η̂ 与实测偏移一致 |
| E449 | 7C 收敛与预算 | ≤5 次迭代；AugContract 内完成率 ≥95% |
| E450 | 时序保全 | 50Hz 99.9% 周期<20ms；修复时延 P99≤τ_repair |
| E451 | 对抗盲区/伪造/注入 | 四层防线 + 溯源后注入成功率<5% |
| E452 | B-Quarantine 体感漂移 | 磨损/温漂/负载阶跃 3 次内告警；旧证据传递失效 100% |
| E453 | A-Quarantine 在线检测 | ARL0/ARL1 校准；慢漂移与幅度异常均可检出 |
| E454 | 溯源失效传递 | body_version 升级后旧证书/增强点/后验全部失效，无残留 |
| E455 | ASE 安全性 | 力矩/接触/工作空间违规 0；中止残余 ≤ RS-Envelope |
| E456 | 消融 | 去 E-Box / A-Box / EA-Cal / MP-Φ^G / 溯源 各自贡献量化 |

## 7. 与第 2 轮的差异与继承

- **继承**：R/盲区判定（定义 398/399）、风险门 λ（400）、M_ver（401）、热替换（引理 44）、IV/TB-Contract（407/424）、6C（421，扩展为 7C）、契约回归、L-Box/T-Box/TCV/AP-Cal/P-Quarantine 全部保留。
- **修复（第 2 轮缺陷）**：零副作用 → ASE+RS-Envelope；V 独立性 → provenance-disjoint；TCV DAG 引用未校验 → 类型化数据流图；标量 z/last_gain → Mahalanobis + 显式收缩比；P-Quarantine 符号游程 → CUSUM/SPRT + 恢复；η 只声明 → η̂+CI；定义 426 边界/饥饿 → n_min 夹紧 + 饥饿界。
- **新增**：E-Box 具身自标定、A-Box 增强证书、EA-Cal 轨道校准、MP-Φ^G 规范等变先验、A/B-Quarantine、证据溯源 DAG、7C、AugContract、I6/I7 不变式。

## 8. 本轮最大风险

**一句话**：EmbodiedGauge 的证书-先验-溯源三层共享同一个 `body_version` 依赖，一次未被及时捕获的身体标定偏差会同时污染该版本下所有增强证书、等变先验与校准后验，使「局部修复、误差局部化」的整体安全论证失效；而证书与溯源图会让伪证据显得比裸猜测更可信。
**兜底**：B-Quarantine（体感漂移）+ A-Quarantine（增强泄漏）+ 物理留出覆盖率审计 + 引理 51 可辨识性门槛 + E443/E446/E452/E454 证伪实验。
<!-- ARTIFACT:END -->
