# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 52 轮（承接第 51 轮 v15 GroundEdge；灵感循环第 3 轮；本轮灵感：跨任务泛化 × 虚拟仿真） · GroundEdge-GenSim：适用域证书 × 迁移风险预算 × 仿真保真包络与单向证伪（十层架构 v16）

> 承接第 51 轮 v15 GroundEdge。v15 把安全从"大脑里的证书"改写成"沿 ROS 图流动、在执行器边缘被强制的证书连续统"，用 IGC/ILM/XTC/GPC/SEN/CE/TBC 把共地、主动权、图钉、零信任信封与边缘租约接进九层栈，并把安全论证写成"蒸馏只损失效率、不损失 soundness"。但它仍隐含两个未被点破的承重假设：**H16：证书是"单任务、单部署"的一次性产物——每个新任务都要从零再认证；任务族之间的相似性、技能复用、组合泛化的风险被当作 0 或不可言说，"任务"被当成一个没有邻域的点**。**H17：仿真是外部可信的便宜证伪器——仿真保真度由他人保证，仿真结果只在 PFV 里"找反例"；一旦把仿真用于跨任务筛选、课程、蒸馏、回归与选型，它的分布就悄悄变成了验收通道，而"仿真通过"从未被认证**。两个灵感词精确命中：**跨任务泛化**要求安全从"单任务证书"升级为**带适用域与迁移风险预算的泛化证书**——证书不是"永远正确"，而是"在可判定的任务域内、以显式间隙成立"，跨域必须付费；**虚拟仿真**要求把仿真器当**有校准证书的仪器**而非神谕——保真度是任务条件化的函数，仿真只能单向证伪（失败即拒绝，通过不等于批准），规模化搜索还要付**选择偏差**的代价。二者耦合出一个反直觉、且最容易骗过所有局部检查的失效：**仿真越搜越"安全"、任务越测越"泛化"，可能只是把策略过拟合到了仿真器的偏置与任务采样偏差上**——证书齐全、指标漂亮，却在真实任务族的边缘系统性地错。于是本轮把证书升级为 `C=(claim, domain, tolerance, evidence)`，把"泛化"变成可判定的适用域 + 可入账的迁移/仿真/选择三重风险，并坚持：**仿真可否决，不可单独批准；跨域可迁移，不可免费继承**。

## 0. 直觉与动机

**灵感 1（跨任务泛化 → 证书是"带适应症与禁忌症的药品说明书"，不是万能真理）**
直觉：v15 的证书像一句"这药有效"，却不写适应症、剂量与禁忌。真实部署面对的是**任务流**：今天是递物、明天是引路、后天是狭窄空间避让；用户还会问"那这个新任务行不行"。若每个任务都从零认证，成本不可承受；若把旧证书直接复用，又会把"在 A 任务上成立"悄悄说成"在 B 上也成立"。正确的对象不是任务点，而是**带结构的任务族**：证书必须声明可判定的**适用域** `D(C)`，域内以显式容差成立，域外必须走**迁移证书**或任务本地再认证。关键是：任务相似度只能用于调度与检索，**绝不能用嵌入最近邻冒充 soundness**；域判定必须是对可解释任务描述符的可检查谓词，`unknown` 一律按 `out` 处理（fail-closed）。

**灵感 2（虚拟仿真 → 仿真器是有校准证书的仪器，不是神谕）**
直觉：科学里没有"这台仪器总是对的"，只有"在量程、工况、校准期内误差 ≤ ε"。仿真同理：刚体接触、摩擦、线缆、柔性、传感器噪声、执行器饱和在不同任务上误差不同；同一仿真器在平整地面很准，在软地毯上可能完全错。因此必须给出**任务条件化的仿真保真包络** `ε_S(T)`：在经认证的测试分布上，以 `1−β_S(T)` 覆盖真实与仿真的风险差。更要命的是不对称：**仿真报失败**可能只是仿真太保守（损失可用性，安全方向）；**仿真报通过**却无法排除真实失败（危险方向）。所以仿真可以**否决**，但**不能单独批准**；通过只有在"已校准 `ε_S` + 独立真实锚点"闭合后才可进入放行，否则只是提议。

**灵感 3（耦合 → 仿真规模化搜索的"赢家诅咒"与选择偏差）**
直觉：跨任务泛化天然要在仿真里**批量生成**任务与候选策略，再挑最好看的那个。可一旦从 `N` 个候选里挑"最安全"的，观测到的安全就是乐观有偏的——这正是多重比较/赢家诅咒。仿真越能搜，越容易挑到"恰好迎合仿真偏置"的策略；同时用同一批场景既做搜索又做验收，等于把考卷提前泄题。因此 `N` 必须成为一等风险资源：**搜索预算越大，真实锚点预算也必须越大**；证书必须扣除可计算的 `α_sel(N,m)`（anytime-valid e-process 或均匀收敛界），并且验收锚点必须**预注册、与搜索独立、不可复用**。

**灵感 4（仿真证伪的单向性 → 只用仿真扩"边界"，不用仿真造"真理"）**
直觉：把仿真当"找反例的猎犬"而不是"发证书的法官"。给定源证书与候选适用域，用对抗式任务/策略搜索去**扩大失败边界**：仿真找到反例就收缩域或拒绝（可能是假警报，但方向安全）；仿真搜不到反例只说明"在当前搜索预算内没找到"，不能说明域可扩。于是适用域不是"训练集覆盖"，而是**经对抗搜索未被击穿、且真实锚点通过的最大邻域**。这把 v15 的 `A_est/A_lb` 不对称再推一层：**仿真/学生只允许"提议与证伪"，精确守卫与真实锚点才允许"放行"**。

**灵感 5（组合泛化 → 技能组合的"药物相互作用"）**
直觉：把两个各自认证的技能接起来，可能产生部件层面都不存在的失效：抓取技能与行走技能各自安全，组合后却在交接瞬间遮挡视野、改变支撑多边形、触发新的接触。组合证书不能只做风险相加，必须显式承担**交互项** `α_int` 与**适配义务**（坐标系、共地、接触模型、时序、参数域），并按"组合类"做仿真证伪 + 真实锚点。泛化不是"把零件拼起来就自动成立"，而是"每次新组合都生成新声明、新域、新证据"。

**耦合升级**：v15 九层之上插入 **L0.5 任务迁移与仿真证据层（TIX + XFR + CRC + SFE + FDR + RAB + DST + SBC）**，作为连接"底座/执行边"与"感知/任务"的证据平面。十层 v16：根信任+能力格 + L0 分布式底座与执行边 + **L0.5 任务迁移与仿真证据** + L1 几何感知 + L2 任务/上下文/记忆/语音 + L2.5 交互共地与共创契约 + L3 关节证书/抽象/决策 + L3.5 动力可行（HVC/CRM）+ L4 CAR/Shield/CBG+/KDX + L5 DCL/真机/HCI 评测 + L6 原型证伪/XFER/LFF/IXD。JCPS 输出扩为 `(v,a,m,q,ι,κ,g,λ,τ,σ)`（`τ`=任务指纹/适用域判定，`σ`=仿真证据等级与保真包络句柄）。

## 1. 形式化定义（增量：定义 97–106）

**定义 97（任务、任务族与可判定适用域）**
任务 `T=(O,E,G,W,Emb,Ctx)`：对象/场景、环境分布、目标规格、用户契约、本体/ embodiment、上下文。任务族 `ℱ` 由**可解释描述符** `d(T)∈𝔇` 描述（对象类别、几何/动力学工况、接触/地面类别、交互协议、人群/语言、负载与速度域等）。任务距离 `d_ℱ` 只用于检索与调度，**单独不构成 soundness 依据**。证书 `C=(claim, D(C), tolerance, evidence)` 携带**可判定适用域** `D(C)⊆ℱ`，由谓词 `dom_C:𝔇→{in,out,unknown}` 判定，要求 `dom_C(T)=in ⇒ T∈D(C)`；`unknown` 按 `out` 处理。域判定必须在承诺前完成且可因上下文歧义而撤销。域外执行必须走迁移证书或任务本地再认证，禁止"默认继承"。

**定义 98（迁移证书与任务条件化泛化间隙）**
任务态射 `φ:(z_t,u_t)→(z_s,u_s)` 携带适配义务 `κ_ad`：`Inv_s∘φ⇒Inv_t`、`Z_safe^s` 拉回包含于 `Z_safe^t`、契约前置条件保持、执行包络 `A_lb` 映射不放大。迁移证书
`TC=(C_s,φ,D,δ_tr,κ_ad,h_T)` 满足：`∀T∈D, dom_{C_s}(φ(T))=in ∧ κ_ad(T) ⇒ P(z_t∈Z_safe^t, ∀t≤H) ≥ 1−α_s−δ_tr(T)`。
`δ_tr(T)` 必须至少含一个**sound 分量**（对动力学/接触失配的 Lipschitz/收缩界、barrier 鲁棒性界、或经形式化验证的最坏失配仿真），统计残差只可用 conformal 下界修正；禁止只用学到的任务嵌入距离。`δ_tr(T)` 可超过风险预算 → 迁移无效（负迁移），必须拒绝而非折中。无适用域谓词 → 无迁移证书。

**定义 99（证书组合与适配义务）**
技能 `S_i=(Pre_i,Post_i,Inv_i,A_lb,i,C_i)`。组合 `S_1⊗S_2` 可接受当且仅当 `Post_1⇒Pre_2`、接口上 `Inv` 保持、且适配义务 `κ_ad^⊗`（共享物体、接触、坐标、时序、共地、参数域）被清偿。组合风险
`α_⊗=α_1+α_2+α_int(⊗)`，其中 `α_int` 是**部件层面不存在、组合才出现的交互失效**，不可由各部分相加推出，必须按组合类用仿真证伪 + 真实锚点给出上界。组合产生新声明、新适用域与新证据义务，**不是旧证书的免费并集**。

**定义 100（仿真保真包络与仿真证据等级）**
仿真器 `S=(engine,assets,scenarios,seeds,h_S)` 视为仪器。对风险泛函 `R`（安全裕量、违例率、成功率），任务条件化保真度
`ε_S(T)=sup_{π∈Π_T}|R_real(T,π)−R_sim(T,π)|`，在经认证测试分布 `D_test(T)` 上以 `1−β_S(T)` 覆盖；仿真证书 `SC=(h_S,D_test,ε_S(T),β_S,coverage,seeds,asset_sbom)`。保真度**不是全局标量**，必须按任务族给出。证据等级：**E0** 仅仿真反例（只可拒绝）；**E1** 仿真结果 + 校准 `ε_S` + 独立真实锚点（可带膨胀支持认证）；**E2** 任务本地真实认证（完整）。**无 E2 的接受必须经 E1 闭合；E0 永不接受。**

**定义 101（仿真证据的单向准入 / 证伪优先）**
准入函数 `Adm(⋅)`：`Adm(sim_fail)=reject` 或收缩域（假警报只损失可用性，方向安全）；`Adm(sim_pass)=proposal_only`，除非满足 E1（`ε_S` 有效 ∧ 锚点完成）。形式化要求**单调性**：仿真证据只能使已认证域/置信度**单调不增**（`D′⊆D`），除非 `ε_S` + 真实锚点另行闭合。因此被投毒或过度乐观的仿真最多造成过度保守，不能造成未认证放行；反之，仿真漏报是危险方向，绝不能由仿真单独接受。

**定义 102（真实锚点预算与预注册采样）**
真实锚点集 `A(T)={a_1,…,a_m}` 由**预注册**采样从 `D(T)` 抽取，采样过程与仿真搜索独立，且不得复用为模型选择。若采用"零失败"规则，需 `m ≥ ln(β_a)/ln(1−α_a)` 才能以 `1−β_a` 声称违例率 `≤α_a`；更一般地可用 anytime-valid e-process 停止。锚点预算 `B_real`（时间/成本）是一等约束：**预算不足则不得扩域**，只能留在已锚定域内或 fail-closed。**禁止用仿真单独扩张适用域。**

**定义 103（联合再认证与版本六元组）**
守卫校验 `(h(κ_c),h_G,v_student,v_interaction,h_T,h_S)` 六元组（`h_T`=任务指纹/适用域哈希，`h_S`=仿真器/资产/场景版本）。任一不匹配即 fail-closed。契约、部署图、学生、交互策略、任务域、仿真器/资产任一变更 → 重解 → 重蒸馏 → **域重判 → 迁移界重算 → 仿真保真复核 → 必要时重跑锚点** → 再认证后方可服役。

**定义 104（域漂移绊线与负迁移）**
在线监控任务描述符 `d(T)`、成功率/安全残差与预测之差、共地与上下文；用 anytime-valid e-process 检验 `T∈D` 与迁移界 `δ_tr`。检验拒绝即：撤销迁移证书、收缩域、回退任务本地认证或 CRM，**绝不带病继续**。要求检测延迟 `≤τ_shift`、误报 `≤α_shift`；负迁移一旦被证据支持，旧 `TC` 永久失效并记入账本。

**定义 105（选择偏差与搜索预算）**
若用仿真从 `N` 个候选策略/域中选出最优，表观安全有乐观偏差。证书必须扣除
`α_sel(N,m) ≥ sqrt(2(ln N+ln(1/β))/m)`（或等价的 anytime-valid/e-value 修正），其中 `m` 为独立锚点数。搜索预算 `N` 是风险资源：仿真搜得越多，所需真实锚点越多。禁止在验收锚点上做早停、挑选或多次比较而不校正。

**定义 106（账本与十二源归因）**
`CCL⁴` 在 `CCL+++` 上追加：任务域判定/扩张/撤销、迁移使用与负迁移、组合交互项、仿真证据等级、保真漂移、锚点结果与泄漏审计、搜索预算 `N`、域漂移绊线。DDA 归因扩为**十二源**：感知 / 关节 / 边界 / 意图 / 接触 / 传输 / 动力 / 蒸馏 / 交互 / 底座 / **迁移（域·组合·负迁移）** / **仿真（保真·选择·资产）**。任一来源的置信折损显式入账并参与抽象、速度缩放与自主权缩放，不得静默吸收。

## 2. 新增产出与既有 IP 升级

**IP-99 TIX（Task Index & Applicability Domain）**：任务指纹、可解释描述符格、可判定适用域谓词；`unknown` 即 out，域外禁止默认继承。
**IP-100 XFR（Cross-task Transfer Certificate）**：任务态射 + 适配义务 + 任务条件化 `δ_tr`；至少一个 sound 分量；负迁移直接拒绝。
**IP-101 CRC（Certificate Reuse Composer）**：技能/证书组合代数、适配义务清偿、交互项 `α_int`；组合必须新生证据。
**IP-102 SFE（Simulation Fidelity Envelope）**：任务条件化 `ε_S(T)`、覆盖与版本钉住、场景/资产 SBOM；仿真作为带校准的仪器。
**IP-103 FDR（Falsification-Only Discipline）**：仿真证据单向准入；失败即拒绝/收缩，通过默认只是提议。
**IP-104 RAB（Reality Anchor Budget）**：预注册、与搜索独立的真实锚点与统计功效；预算不足不得扩域。
**IP-105 DST（Domain-Shift Tripwire）**：在线 e-process 域漂移/负迁移绊线；撤销迁移、回退本地认证或 CRM。
**IP-106 SBC（Search-Budget Correction）**：把搜索预算 `N` 计入风险，扣除 `α_sel(N,m)`，抑制赢家诅咒。

**既有 IP 升级**
IP-94 GPC：图钉追加 `h_T`（任务域）与 `h_S`（仿真器/资产/场景）及资产 SBOM；图/任务/仿真任一变更即失效。
IP-96 CE：信封携带 `h_T`、迁移证书摘要、仿真证书摘要、证据等级与搜索预算 `N`；任务域成为证书语义的一部分。
IP-83 PFV：仿真自身进入证伪对象——仿真保真包络、场景采样偏差、资产/引擎投毒、过拟合到仿真；仍无定罪权。
IP-84 XFER：δ 从标量升级为任务条件化三元 `(δ_tr, ε_S, α_sel)`，并显式报告锚点覆盖。
IP-77 DDA：十源 → 十二源（+迁移、+仿真）。
IP-61 DCL：采集域判定失败/扩张、迁移失败、负迁移、仿真-真实残差、锚点结果、泄漏审计、漂移事件、搜索预算。
IP-62 CCA：新增仿真器/资产投毒、场景挑樱桃、基准过拟合、Goodhart、锚点泄漏、域欺骗、旧迁移重放、负迁移注入红队。
IP-51 CAR：守卫加"`dom_C(T)=in` ∧ 迁移有效 ∧ 证据等级可准入 ∧ 锚点已完成 ∧ 绊线未触发"。
IP-45 总线：新增 task-fingerprint / applicability-domain / transfer-cert / sim-cert / sim-evidence-class / domain-shift / reality-anchor 话题。
IP-85 MRC：新增"域漂移绊线/迁移失效/仿真保真漂移/锚点失败"触发；CRM 作为本地默认。
IP-79 SIC：联合状态扩为 `z=(x_r,x_h,x_e,κ,g,λ,τ,σ)`；屏障条件含任务域与仿真证据等级。
IP-82 IPC：协议并入任务/域协商与证据披露（向用户说明"此能力仅在某域内、证据等级为何"）。
IP-75 ASC：抽象只在适用域内可行；跨域强制细化/迁移/再认证，禁止用大模型"感觉相似"扩域。
IP-74 HTD-Cert：分解节点携带任务域约束、仿真证据等级与组合适配义务节点。
IP-86 UCC：共创条款只在域内生效；新任务请求必须走迁移或再认证，并如实解释不确定性。
IP-72 RRP：e-process 纳入域成员、迁移残差、仿真保真、选择偏差与锚点证据；跨层仍带 δ。
IP-76 CCL：升级为 `CCL⁴`（定义 106），只追加。

## 3. 算法骨架

每个宏周期：
1. **任务索引**：由上下文构建 `d(T)`，计算任务指纹 `h_T`；检索候选证书、迁移证书与仿真证书；解析六元组，任一失效 → fail-closed。
2. **底座自检**：承接 v15，验证 SROS2 enclave、图清单 `h_G`、包签名/SBOM、SEN/看门狗；不通过即 hold。
3. **域判定**：对每个候选证书计算 `dom_C(T)`；`unknown` 按 out。域外候选只能进入迁移/再认证分支，禁止默认复用。
4. **仿真证据**：以对抗任务/策略搜索做 E0 证伪，扩大失败边界；任一反例 → 收缩域或拒绝；仿真通过只登记为提议，不进入放行。
5. **迁移与组合**：计算 `δ_tr(T)` 的 sound 分量与 conformal 残差；清偿适配义务；组合时计入 `α_int` 并生成新声明/新域。
6. **选择校正**：记录搜索预算 `N`，扣除 `α_sel(N,m)`；若验收锚点被搜索污染 → 判定泄漏、重采。
7. **锚点闭合**：E1 必须在预注册、独立真实锚点上通过；预算不足 → 不扩域，回退已锚定域或任务本地认证。
8. **共地与主动权**：承接 v15，`B_g<θ_ground` 只许澄清/示范/最小动作；IL 单写者、交接保持 `Z_hold`。
9. **计划与驱动**：承接 v15 的 PSC/CRT/ACC/JDA/EDR；计划骨架与 `A_lb` 复核，及时条件不满足即重规划。
10. **精确处置与签发**：KDX 提议 → `G_exact` 在 `A_lb`、`h_G`、`h_T`、`h_S`、`h(κ_c)` 与证据等级下精确求值；通过后签发 CE 与 AL；只有 SEN 能在边缘验证并授权执行器。
11. **执行与绊线**：SEN 监控期限/看门狗/租约；DST 在线检验域成员与迁移界；任一失败 → 本地 CRM，撤销迁移证书并入账。
12. **归因与回灌**：DDA 十二源归因；负迁移/仿真漏报/锚点失败回灌 DCL/CCA；必要时收缩域、重蒸馏、重认证。
13. 所有路径不可行 → 技能合成/人工接管/保护姿态/fail-closed；绝不绕过 SEN、`G_exact`、L3.5，也绝不用仿真单独扩域。

## 4. 本轮最大风险

**一句话**：v16 把"泛化"从一句口号变成了可计算的适用域与风险预算，但整条论证现在悬挂在两个"自指"的估计上——**适用域谓词与 `δ_tr` 是用有限任务样本学/估出来的，仿真保真包络 `ε_S(T)` 又是在同一批仿真分布上校准的**；一旦任务族被错误划分、仿真器被投毒或过拟合、或锚点与搜索发生泄漏，"域内成立"的证书就会变成**证书齐全的过度泛化**——所有局部检查都通过，却在真实任务族的边缘系统性失效，因此必须以独立预注册锚点、单调证伪纪律、选择偏差校正和持续域漂移绊线来证伪"泛化"本身，宁可拒绝扩域，绝不把相似当等价。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 52 轮产物 · 创新点清单 v29：GroundEdge-GenSim（TIX × XFR × CRC × SFE × FDR × RAB × DST × SBC）× 适用域证书、迁移风险预算与仿真保真/单向证伪（十层架构 v16）

> 承接第 51 轮产物 v28。本轮增量插入 IP-99/100/101/102/103/104/105/106，并升级 IP-94/96/83/84/77/61/62/51/45/85/79/82/75/74/86/72/76。不推倒 v15 GroundEdge 的 IGC/ILM/XTC/GPC/SEN/CE/TBC 框架；新增 L0.5 任务迁移与仿真证据层，把"单任务证书"升级为"带可判定适用域、迁移风险预算与仿真保真包络的泛化证书"。第 3 轮灵感循环聚焦 H16/H17：认证单元的任务泛化性、仿真证据的认识论地位。核心架构位移：**证书从"在某任务上为真"变成"在可判定域内、以可入账容差为真"；仿真从"可信证伪器"降格为"有校准包络的仪器"，只能否决、不能单独批准**。核心不对称再次扩展：**学生/仿真只许提议与证伪，精确守卫、真实锚点与 SEN 才许放行；跨域可迁移，但绝不免费继承**。

## 0. 核心 IP 设计

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-99 | TIX Task Index & Applicability Domain | 新增 | 任务指纹 + 可解释描述符格 + 可判定域谓词；`unknown`=out，域外禁止默认继承 |
| IP-100 | XFR Cross-task Transfer Certificate | 新增 | 任务态射 + 适配义务 + 任务条件化 `δ_tr`；至少一个 sound 分量；负迁移直接拒绝 |
| IP-101 | CRC Certificate Reuse Composer | 新增 | 组合代数 + 适配义务清偿 + 交互项 `α_int`；组合必须新生证据 |
| IP-102 | SFE Simulation Fidelity Envelope | 新增 | 任务条件化 `ε_S(T)` + 覆盖/版本钉住 + 场景资产 SBOM；仿真=带校准仪器 |
| IP-103 | FDR Falsification-Only Discipline | 新增 | 仿真证据单向准入；失败即拒绝/收缩，通过默认只是提议 |
| IP-104 | RAB Reality Anchor Budget | 新增 | 预注册、搜索独立的真实锚点与统计功效；预算不足不得扩域 |
| IP-105 | DST Domain-Shift Tripwire | 新增 | 在线 e-process 域漂移/负迁移绊线；撤销迁移、回退本地认证/CRM |
| IP-106 | SBC Search-Budget Correction | 新增 | 搜索预算 `N` 计入风险，扣除 `α_sel(N,m)`，抑制赢家诅咒 |
| IP-94 | GPC | 升级 | 图钉加 `h_T`/`h_S`/资产 SBOM；图·任务·仿真任一变更即失效 |
| IP-96 | CE | 升级 | 信封加 `h_T`、迁移/仿真证书摘要、证据等级、搜索预算 `N` |
| IP-83 | PFV | 升级 | 仿真自身成为证伪对象：保真包络/采样偏差/投毒/过拟合；无定罪权 |
| IP-84 | XFER | 升级 | δ 升级为 `(δ_tr, ε_S, α_sel)` 三元 + 锚点覆盖报告 |
| IP-77 | DDA | 升级 | 十源 → 十二源（+迁移、+仿真） |
| IP-61 | DCL | 升级 | 采域失败/扩张/迁移失败/负迁移/仿真-真实残差/锚点/泄漏/漂移/N |
| IP-62 | CCA | 升级 | 仿真投毒/挑樱桃/基准过拟合/Goodhart/锚点泄漏/域欺骗/旧迁移重放/负迁移注入 |
| IP-51 | CAR | 升级 | 守卫加域成员∧迁移有效∧证据等级可准入∧锚点完成∧绊线未触发 |
| IP-45 | 总线 | 升级 | task-fingerprint / applicability-domain / transfer-cert / sim-cert / sim-evidence-class / domain-shift / reality-anchor |
| IP-85/79 | MRC/SIC | 升级 | 新触发（漂移/迁移失效/保真漂移/锚点失败）；状态含 `τ,σ`，屏障含域 |
| IP-82/86 | IPC/UCC | 升级 | 协议并入域协商与证据披露；共创条款只在域内生效，新任务须迁移/再认证 |
| IP-75/74 | ASC/HTD-Cert | 升级 | 抽象只在域内；分解节点带域约束、证据等级、组合适配义务 |
| IP-72/76 | RRP/CCL | 升级 | e-process 纳入域/迁移/保真/选择/锚点；`CCL⁴`（定义 106） |

## 1. 符号体系（定义 97–106 见想法区；符号增量）

| 符号 | 含义 |
|---|---|
| `T=(O,E,G,W,Emb,Ctx)` | 任务：对象/场景、环境分布、目标、用户契约、本体、上下文 |
| `d(T)∈𝔇, d_ℱ` | 可解释任务描述符 / 任务距离（仅检索，不单独作 soundness） |
| `D(C), dom_C(T)` | 证书适用域 / 域判定谓词（`in/out/unknown`，unknown→out） |
| `φ, κ_ad` | 任务态射 / 适配义务 |
| `TC=(C_s,φ,D,δ_tr,κ_ad,h_T)` | 迁移证书 |
| `δ_tr(T)` | 任务条件化泛化间隙（含 sound 分量 + conformal 残差） |
| `S_i=(Pre_i,Post_i,Inv_i,A_lb,i,C_i)` | 可组合技能证书 |
| `α_int(⊗)` | 组合交互失效项（不由部件相加得出） |
| `S=(engine,assets,scenarios,seeds,h_S)` | 仿真器仪器与版本 |
| `ε_S(T), β_S(T)` | 任务条件化仿真保真包络 / 未覆盖概率 |
| `SC=(h_S,D_test,ε_S,β_S,coverage,seeds,asset_sbom)` | 仿真证书 |
| `E0/E1/E2` | 仿真反例 / 校准仿真+锚点 / 任务本地真实认证 |
| `Adm(⋅)` | 仿真证据单向准入函数 |
| `A(T), m, B_real` | 真实锚点集 / 样本数 / 预算 |
| `α_a, β_a` | 锚点可证违例率 / 置信失败概率 |
| `N, α_sel(N,m)` | 仿真搜索预算 / 选择偏差修正项 |
| `τ_shift, α_shift` | 域漂移检测延迟 / 误报率 |
| `(h(κ_c),h_G,v_student,v_interaction,h_T,h_S)` | 版本六元组（守卫强制校验） |
| `h_T, h_S` | 任务域哈希 / 仿真器与资产版本哈希 |
| `α_transfer, α_sim, α_select, α_shift` | 迁移 / 仿真保真 / 选择偏差 / 域漂移失效项 |
| `τ, σ` | JCPS 输出中的任务域判定 / 仿真证据等级句柄 |

## 2. 关键算法 伪代码

### IP-99 TIX（任务索引与可判定适用域）
```
def task_index(T, descriptors):
    d = interpretable_descriptors(T, descriptors)   # 对象/几何/工况/交互/人群
    h_T = H(canonical(d))
    return d, h_T

def domain_check(C, d):
    # 只认可解释谓词；嵌入最近邻仅供调度，不作 soundness
    r = C.dom_predicate(d)
    if r == 'unknown':
        return 'out'                                 # fail-closed
    return r

def certified_for(C, d):
    return domain_check(C, d) == 'in'
```

### IP-100 XFR（迁移证书与泛化间隙）
```
def transfer_certify(C_s, phi, d, kappa_ad, graph, sim_cert):
    if not sound_morphism(phi, C_s):                 # Inv 拉回/安全集包含
        return ('reject', 'morphism_unsound')
    if not discharge(kappa_ad, d):                   # 适配义务未清偿
        return ('reject', 'adapter_unmet')
    delta_sound = max(lyapunov_mismatch_bound(phi, graph),
                      barrier_robustness_loss(phi, C_s),
                      worst_case_mismatch_sim(phi, sim_cert))
    delta_stat = conformal_upper(transfer_residuals(d), alpha=ALPHA_TR)
    delta_tr = delta_sound + delta_stat              # 只可加，不可抵消
    if delta_tr > DELTA_BUDGET:
        return ('reject', 'negative_transfer', delta_tr)
    return ('ok', TC(C_s, phi, D=d.nbr_region, delta_tr=delta_tr,
                     kappa_ad=kappa_ad, h_T=d.h_T))
```

### IP-101 CRC（组合与交互项）
```
def compose(S1, S2, adapter):
    if not implies(S1.Post, S2.Pre):
        return ('reject', 'pre_post_mismatch')
    if not preserves_invariants(S1, S2, adapter.interface):
        return ('reject', 'invariant_break')
    if not discharge(adapter.obligations, context()):
        return ('reject', 'adapter_unmet')
    a_int = interaction_term(S1, S2, adapter.cls)    # 组合类上单独估计
    return ('ok', Skill(S1, S2, alpha=a_int,
                        evidence=require_new_evidence(S1, S2, adapter)))
```

### IP-102 SFE + IP-103 FDR（仿真保真与单向准入）
```
def sim_fidelity(sim, T, R, D_test):
    scores = [abs(R.real(x) - R.sim(sim, x)) for x in sample(D_test, T)]
    eps = conformal_upper(scores, beta=BETA_S)       # 任务条件化，非全局标量
    return SC(h_S=sim.version, D_test=D_test, eps_T=eps, beta=BETA_S,
              coverage=len(scores), seeds=sim.seeds,
              asset_sbom=audit_assets(sim))

def admit(evidence, sc, anchors_done, N):
    # 单调、单向：仿真只能收缩已认证域/置信度
    if evidence.kind == 'counterexample':
        return ('reject_or_shrink', evidence)        # 假警报只损可用性
    if evidence.kind == 'pass':
        if sc is None or sc.eps_T is None:
            return ('proposal_only', 'no_fidelity_envelope')
        if not anchors_done:
            return ('proposal_only', 'no_reality_anchor')   # E1 未闭合
        return ('support_E1', sc, alpha_sel(N, m=anchors_done))
    if evidence.kind == 'real_cert':
        return ('support_E2', evidence)
    return ('reject', 'unknown_evidence')
```

### IP-104 RAB + IP-106 SBC（锚点与选择偏差）
```
def reality_anchor(T, D, alpha_a, beta_a, budget):
    m_req = ceil(log(beta_a) / log(1 - alpha_a))     # 零失败规则（或 e-process）
    if budget < cost(m_req, T):
        return ('insufficient_budget', m_req)       # 不得扩域
    A = preregistered_sample(D, m_req, seed=PRE_SEED)  # 与仿真搜索独立
    for a in A:
        if violates(a, T):
            return ('anchor_fail', a)               # 撤销扩域
    return ('anchor_pass', m_req)

def alpha_sel(N, m, beta=0.05):
    return sqrt(2.0 * (log(max(N, 1)) + log(1.0 / beta)) / max(m, 1))
    # 或用 anytime-valid e-value；禁止在验收锚点上做未校正的选择/早停
```

### IP-105 DST（域漂移绊线）
```
def domain_shift_watch(T_stream, C, TC, eproc):
    d, h_T = task_index(T_stream.latest(), DESCRIPTORS)
    e = eproc.update(evidence=(d, residual(T_stream), success_rate(T_stream)))
    if domain_check(C, d) != 'in':
        return revoke(TC, reason='out_of_domain')    # 不等拒绝检验
    if e.rejects(H0='T in D and delta_tr holds'):
        return revoke(TC, reason='negative_transfer_or_shift')
    return ('ok', e.value)
```

### IP-73 JCPS（v16：任务域-迁移-仿真联合调度）
```
def groundedge_gensim_schedule(goal, ctx, certs, leases, graph, now):
    if not base_selfcheck(graph, now):               # v15 L0
        return ('fail_closed', 'substrate')
    d, h_T = task_index(ctx.task, DESCRIPTORS)
    cand = retrieve(certs, d)                        # 距离仅用于检索
    live = []
    for C in cand:
        if not domain_check(C, d) == 'in':
            continue                                 # 域外不默认继承
        if not version_six_ok(C, h_T, graph, now):   # h(κ),h_G,h_T,h_S,...
            continue
        live.append(C)
    if not live:
        # 迁移或任务本地再认证，绝不用"相似"直接放行
        tc = best_transfer_certificate(cand, d, graph)
        if tc is None or tc.delta_tr > DELTA_BUDGET:
            return ('reverify_or_fail_closed', None)
        sim_sc = best_sim_certificate(tc, d)
        adm = admit(sim_evidence(tc, sim_sc), sim_sc,
                    anchors_done=anchors_for(d), N=search_budget())
        if adm[0] not in ('support_E1', 'support_E2'):
            return ('reverify_or_crm', adm)
        live = [inflate(tc, adm)]
    bg = calibrated_Bg(current_g(), history())
    if bg < THETA_GROUND:
        return repair_or_act(current_g(), minimal(goal), history())  # v15
    il = acquire_or_renew_initiative(current_holder(), scope_of(goal), now, current_z())
    if il[0] == 'reject':
        return ('hold_and_propose', certified_hold_set(scope_of(goal)))
    dag = htd_cert(goal, live, contracts, leases, graph)  # 含域/组合/证据节点
    if dag is None:
        return ('synthesize_or_fail_closed', None)
    if not viability_ok_A(current_z(), current_mode(), A_lb(current_drive())):
        return ('crm', sen_local_crm())
    for s in student.propose(o, ctx, current_g()):
        if not guard.exact_check(s, h_T=h_T, h_S=sim_version(), hG=graph_hash(),
                                 il=il[1], evidence_class=evidence_class(live), now=now):
            continue
        ce = issue_envelope(s, cert_of(s), graph, now, h_T=h_T,
                            transfer_digest=tc_digest(live),
                            sim_digest=sim_digest(live),
                            evidence_class=evidence_class(live), N=search_budget())
        if not temporal_sound(ce, graph):
            continue
        return ('actuate', ce, issue_actuation_lease(ce, il[1], now))
    return ('crm', sen_local_crm())
```

## 3. 复杂度与正确性

| 组件 | 时间 | 空间 | 正确性保证 |
|---|---|---|---|
| TIX | O(|d|) 指纹，O(1) 谓词 | O(|certs|) | `unknown`=out；域外不继承；嵌入距离仅检索 |
| XFR | O(|φ|+标定表) | O(|D|) | 至少一个 sound 分量；`δ_tr>预算` 即拒绝 |
| CRC | O(|obligations|) | O(|skills|) | Pre/Post/Inv 清偿 + 交互项单独取证 |
| SFE | 离线 O(|D_test|)，在线 O(1) 查表 | O(|T|·|scenarios|) | 任务条件化覆盖；版本/资产钉住 |
| FDR | O(1)/证据 | O(1) | 仿真单调收缩；E0 永不接受，通过仅提议 |
| RAB | O(m) 真实试验 | O(m) | 预注册独立采样；预算不足不得扩域 |
| DST | O(1)/更新，e-process | O(1) | 检测延迟 ≤`τ_shift`；撤销后回退本地认证/CRM |
| SBC | O(1) | O(1) | `α_sel(N,m)` 扣除；N 越大锚点需求越大 |
| v15 组件 | 承接 v15 | 承接 v15 | GPC/CE/SEN/TBC/IGC/ILM 全部保留 |

**正确性定理（Domain-Scoped, Sim-Falsified, Anchor-Closed Generalization Soundness）**
假设 (A1)–(A16) 承接 v15；
**(A17)** 域谓词 sound：`dom_C(T)=in ⇒ T∈D(C)`，且域判定在承诺前完成、`unknown` 按 out 处理；任务描述符可观测且不可被未授权方伪造；
**(A18)** 仿真保真包络 sound 且任务条件化：在 `D_test(T)` 上 `P(|R_real−R_sim|≤ε_S(T))≥1−β_S(T)`，`h_S`/资产 SBOM 被守卫校验，仿真供应链受保护；
**(A19)** 迁移 `δ_tr(T)` 的 sound 分量成立（态射保持不变式、barrier/Lyapunov 失配界、最坏失配仿真），统计分量用 conformal 下界，适配义务被清偿；组合交互项 `α_int` 按组合类单独取证；
**(A20)** 仿真证据只经单向准入；E1 接受必须由**预注册、与搜索独立**的真实锚点闭合，锚点不漏用、不早停；搜索预算 `N` 经 `α_sel(N,m)` 校正；
**(A21)** DST 以延迟 `≤τ_shift`、误报 `≤α_shift` 检测域漂移/负迁移，拒绝后撤销迁移并回退本地认证或 CRM。
则对任意目标任务 `T` 与任务序列，
`P(∀t≤T: z(t)∈Z_safe) ≥ 1 − Σ_i α_i − Σ_i ε_hand,i − α_lease − α_intent − α_user − α_viable − α_cap − α_ground − α_expl − α_take − α_graph − α_comm − α_sen − α_transfer − α_sim − α_select − α_shift − α_δ`，
其中 `α_δ` 汇总跨层 δ。**关键不对称仍不破**：student/仿真只能提议与证伪；放行要求 `dom_C(T)=in`、六元组匹配、`G_exact` 在 `A_lb` 下精确通过、证据等级可准入、锚点闭合、且 SEN 边缘验证成功。**跨域迁移的每一分泛化都对应一笔显式风险预算；仿真无法通过"搜得多、看起来好"抬高安全上界。**

**关键推论（泛化不免费）**：在 (A17)–(A21) 下，若目标任务落在已锚定域外，系统只能选择"迁移并付费（`δ_tr+ε_S+α_sel`）"或"任务本地再认证"或"拒绝"，**不存在"因为像所以行"的第四条路**；任何通过仿真单独扩域、复用旧证书、或忽略选择偏差的路径都被 fail-closed。这把 v15 的"图/传输/共地任一不匹配即失效"扩展为"域/迁移/仿真/选择任一不匹配即失效"。

## 4. 实验设计 E145–E150

| 实验 | 指标 | 门槛 |
|---|---|---|
| E145 适用域与跨任务迁移 | 域外误放行率；`δ_tr` 覆盖率；负迁移检出率；跨任务成功率 vs 任务本地重认证 | 域外放行 0；覆盖率 ≥ 95%；负迁移全拒；成功率差可解释 |
| E146 仿真保真包络 | `ε_S(T)` 任务条件覆盖率；按任务族的误差散布；保真漂移检出；投毒/挑樱桃检出 | 覆盖率 ≥ 95%；漂移可检；投毒检出；无静默漏报 |
| E147 单向证伪 vs 仿真作证明 | 对抗仿真偏置下的假安全率；E0/E1/E2 准入合规率；过度保守代价 | 本方案假安全 0；违规准入 0；保守代价可量化 |
| E148 选择偏差与锚点 | 未校正 vs `α_sel` 校正的泛化虚高；锚点泄漏检出；预算-功效曲线 | 校正后虚高 ≤ 目标；泄漏全检；功效达标 |
| E149 组合泛化与交互项 | 组合类新失效检出率；`α_int` 覆盖；适配义务漏检；组合复用 vs 逐技能重认证 | 新失效检出 ≥ 95%；漏检 0；复用显著省成本 |
| E150 全栈跨任务 sim-to-real 长程 | 跨任务族成功率；域漂移检测延迟；MRC/违例；主观信任与解释一致性 | 成功 ≥ 90%；延迟 ≤ `τ_shift`；违例 0；信任校准良好 |

回退策略：E145 域外误放行 → 立即冻结该域扩域、收紧谓词、重跑锚点，绝不靠相似度补洞；E146 保真包络失准 → 冻结该 `h_S` 版本与资产、扩大 `ε_S`、加真实对标，禁止用其支撑 E1；E147 出现仿真假安全 → 回退到 E0-only 或 E2，重建证据等级门；E148 选择偏差超界 → 减小 `N`、增加独立锚点、启用 anytime-valid 校正；E149 组合漏检 → 禁用该组合类、逐技能回退、补交互测试；E150 漂移或 MRC 超标 → 收缩工作域与共创范围、回退任务本地认证，绝不放松域判定与边缘守卫。

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 任务族/域谓词被错误划分，出现语义 OOD | 高 | 可解释描述符 + 谓词审计 + `unknown`=out + 在线 DST + 对抗域欺骗红队 |
| `δ_tr` 的统计分量在相关/对抗漂移下低估 | 高 | 至少一个 sound 分量 + conformal 下界 + 分层任务族 + 负迁移即拒 |
| 仿真保真包络 `ε_S(T)` 校准偏差或只覆盖窄分布 | 高 | 任务条件化校准 + 对抗场景采样 + 资产/引擎 SBOM + 真实对标 + 版本钉住 |
| 赢家诅咒/选择偏差导致"仿真越搜越安全" | 高 | `α_sel(N,m)` 校正 + 预注册独立锚点 + 禁止锚点复用/早停 + anytime-valid e-process |
| 锚点预算不足被"放宽" | 高 | 预算是一等约束；不足即不扩域、回退已锚定域或 fail-closed |
| 组合交互失效未被部件证据覆盖 | 高 | 交互项 `α_int` 单独取证 + 适配义务 + 按组合类仿真证伪与锚点 |
| 仿真器/资产投毒或基准过拟合 | 高 | 资产 SBOM + 可复现构建 + 红队 + 多仿真器交叉 + 独立锚点 |
| 域漂移检测延迟/误报 | 中 | e-process + 多信号（描述符/残差/共地）+ 保守回退 + 定期演练 |
| 证书与域组合爆炸、部署脆弱 | 中 | 域格分级（关键域强钉、外围弱钉）+ 证书复用组合 + 渐进扩域流水线 |
| 解释把"域内能力"说成"通用能力" | 中 | XTC 解释保真扩展到域/证据等级；证据披露；过度信任监测 |

## 6. 本轮最大风险

**一句话**：GroundEdge-GenSim 的 soundness 现在依赖两个自指估计——**适用域谓词与迁移间隙是用有限任务样本学出来的，仿真保真包络又是在同一批仿真分布上校准的**；一旦任务族被错误划分、仿真器被投毒或过拟合、或验收锚点与搜索发生泄漏，"域内成立"就会退化成**证书齐全的过度泛化**：每一层局部检查都通过，却在真实任务族边缘系统性失效，因此必须用独立预注册锚点、仿真单向证伪、选择偏差校正与持续域漂移绊线来证伪"泛化"本身——**宁可拒绝扩域，绝不把相似当等价**。
<!-- ARTIFACT:END -->
