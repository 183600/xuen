# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 31 轮 · 思维深化：FORCE-CONTINUAL-LITE —— 力觉带外安全、双门防遗忘适配与物理保真桥

## 直觉锚点与动机链条（承接第 30 轮）

- **先自审再外审**：本轮开工前先复查第 30 轮自己的命题，发现一个**比外部风险更优先的逻辑漏洞**——命题 9（适配单调不劣化）隐含假设"Δf_obs 是干净的模型误差"，但 Δf_obs = x_{t+1} − x_t − (A x_t + B u_t) 把**一切**未建模项都当残差：人手推挤机器人时，接触力也进 Δf_obs；更糟的是验证门拦不住——若遥测中接触片段占比高，D_val 同分布污染，G(θ_new, D_val) 会"改善"，验证门放行，θ 把"人在推"学成"世界常量"——物理错误且安全危险（适配后模型把人当成环境的一部分来补偿，反而可能顶向人）。这是第 30 轮命题 9 的失效模式，必须先修，再谈进取。
- **弱点诊断 → 灵感映射**：本轮灵感词「Isaac Sim / 力矩传感 / 持续学习」逐一命中第 30 轮 SERVO-ADAPT-LITE 的四个结构性弱点，构成改进链：
  - 弱点 W1（Δf_obs 接触污染，命题 9 失效）：→ **「力矩传感」FORCE-CROSS 之一：外力估计清洗门**。动量观测器（De Luca 系经典 [R34]）由关节力矩/电流直接估计广义外力 τ̂_ext，独立于视觉、独立于模型残差本身；仅当 ‖r_obs‖ ≤ ε_free 持续整个转移窗口的样本才进 Δf_obs 监督集，接触转移单独入池、禁用于适配。阈值 κ-free 且保守（宁可丢数据，不带毒数据）。
  - 弱点 W2（视觉单模态证据链断裂：遮挡中的手/视野外碰撞/线缆拉扯时 σ_feat=0 退回 v6，而 v6 度量层同样依赖手感知 → 此时整条安全证据链只剩"看不见"）：→ **「力矩传感」FORCE-CROSS 之二：带外力觉安全监控**。动量观测器作为**带外安全监控器**（与硬裁剪同级的安全处理器，1kHz，不占 0.5ms 仲裁预算）：接触触发 r_obs > τ_gate 持续 2 步 → 置 force_alarm 标志 → 仲裁栈强制 fallback。视觉管"看得到的接近"，力觉管"摸得到的接触"——误差源近似正交（检测/内参/光照 vs 建模/摩擦/温漂），物理定律保证接触必然产生力信号。**fail-safe OR 语义（新规则 21）**：力觉只增触发、不做否决（绝不允许"力觉平静就不触发"）；通道自身故障 → 降级仅遥测 + 告警升级，行为逐位=v7，无负收益。对第 30 轮最大风险"自信地错检"：力觉补的是**接触级盲区**；假手错检仍由 abstain/松弛/v6 地板兜——诚实条款：力觉不能否证视觉的接近判断（接近本不产生力信号），跨模态互证仅限接触类事件与遥测归因。
  - 弱点 W3（单步保证 ≠ 累积保证：验证门每步都过，10 轮 OTA 后 θ 漂移无界；γ_anom 连续再标定可能漂移；IP-4 回滚只有上一版）：→ **「持续学习」CONTINUAL-ADAPT：双门 + 回放 + 族谱**。新增**记忆门** G(θ_new, D_replay) ≤ G(θ_old, D_replay) + ε_forget——"旧记忆不劣化"与第 30 轮"新数据单调不升"构成**双验证门**；回放缓冲按 (ξ, κ-bin, 场景) 分层采样混入损失（主机制 [R31]）；EWC Fisher 正则仅辅助（少数据下 Fisher 估计噪声大，诚实降级 [R30, R32]）；**族谱 lineage**：每次 OTA 记录 (parent, Δθ, D 摘要, 指标)，支持回滚到任意祖先；累积漂移 ‖Σ Δθ‖ ≤ Θ_cum 超界 → 冻结适配、强制全量再评估；γ_anom 序列 CUSUM 漂移 → 冻结并人工审查。
  - 弱点 W4（Δf_θ 冷启动无物理先验；SOC-SIM 物理保真存疑；E 系列注入扫描缺传感器仿真）：→ **「Isaac Sim」ISAAC-BRIDGE：物理层托管，社会层不动**。Isaac（GPU 并行刚体/关节物理 + 域随机化 [R33, R35]）只接管 SOC-SIM 的物理内核（臂动力学/接触/线缆/摩擦），人类反应社会层（E18c 验证过的资产）保持自建：Isaac 生成物理一致的 (x, u, x⁺) 与力矩序列——(a) Δf_θ 预训练（"从零学残差"→"从物理先验微调"，n_min 门槛实质下降，直接缓解第 30 轮冷启动风险）；(b) 力矩传感器仿真（噪声模型注入 → E23 测试床，替真机先行标定 τ_gate/ε_free）；(c) S_bench 对抗场景物理化。诚实条款：Isaac 接口工程量是常见低估点，设 E23 冒烟门 + 降级路径（样本效率 <2× → 预训练不采信，仅保留测试床用途）。
- **三者耦合**：力觉是"独立物理证据"——对内清洗 U2 的数据（W1）、对外兜住 U1 的盲区（W2）、给 U3 的仿真保真提供可对照真值通道；持续学习把 U2 的"一次适配"升级为"终身适配"（W3）；Isaac 给 U2 供先验、给力觉供测试床、给 S_bench 供物理化对抗（W4）。第 30 轮"验证 + 吸收 + 审计"三件套升级为"验证 + 吸收 + 审计 + **独立证据**"四件套。
- **关键设计决断**：(1) 力觉放带外监控器而非仲裁栈——P99 危机不加剧（0.41 → 0.42ms，仅 +0.01ms 标志读取），架构上把"证据采集"与"决策仲裁"分离；(2) 触发 OR 不否决——fail-safe：力觉故障不阻塞仲裁，仅失去新增覆盖；(3) 清洗门宁紧勿松——假阴性预算 η_miss 显式计入 ε_acc 裕量（命题 12）；(4) 双门 + 族谱是"持续学习"的最小可信形态——不引入任务边界假设、不依赖大缓冲，三条机制全部可遥测审计；(5) Isaac 范围限定物理层——社会行为模型不在 Isaac 内复刻，避免重做 E18c 资产。

## 形式化定义的深化（继承第 30 轮全部符号）

### 7.1 力觉通道符号（v8 新增）
- p = M(q)q̇：广义动量；动量观测器 r_obs = K_O(p − ∫(τ_s + Cᵀq̇ + g + r_obs)dt)——τ_ext=0 时 r_obs → 0 指数收敛（速率 λ_O），τ_ext≠0 时 r_obs → τ_ext [R34]；τ_s 为关节力矩传感/电流估计。
- F̂_ext = J(q)⁻ᵀ·LPF(r_obs)：任务空间外力估计；ε_free：自由空间门限；清洗门 gate(转移) ≡ sup_窗口‖r_obs‖ ≤ ε_free。
- τ_gate、n_win_c=2：接触触发门限/持续判据；b̂_noise(t)：空转段自适应噪声底（在线估计基线漂移，门限=μ+3σ 自适应）；force_alarm ∈ {0,1}：带外标志（安全处理器写、仲裁栈读）。
- 独立性论证：视觉误差源 {检测、内参、光照、遮挡} ∩ 力觉误差源 {建模、摩擦、偏置、温漂} ≈ ∅；碰撞事件本身同时驱动两通道——对检测是冗余非风险（诚实标注：独立性是近似，高温下力矩偏置与传感器时漂为残余相关源，E24a 扫描覆盖）。

### 7.2 持续适配符号（v8 新增）
- 双验证门：G(θ_new, D_val) ≤ G(θ_old, D_val) − ε_acc（新数据门，继承第 30 轮）∧ G(θ_new, D_replay) ≤ G(θ_old, D_replay) + ε_forget（记忆门，新增）；Δ_forget = max(0, G(θ_new, D_replay) − G(θ_old, D_replay)) 为遗忘度量。
- EWC 正则（辅助）：L_EWC = λ_EWC·Σ_i F_i(θ_i − θ_i^anc)²，F 为上次 OTA 锚点集上的对角 Fisher；主机制为分层回放 L = L_new + ρ_replay·L_replay，ρ_replay 随新数据量自适应。
- 族谱：θ^(k) 记录 (parent, Δθ, D_fit 摘要, 双门指标, γ_anom^(k))；累积预算 Σ‖Δθ‖ ≤ Θ_cum；γ_anom^(k) 序列 CUSUM(k) > h_γ → 冻结适配。

### 7.3 新增公理（规则 21–23；规则 19 扩展）
- 规则 21（力觉 fail-safe OR）：力觉通道只增触发不做否决；force_alarm 触发级别最高（高于 r_vs/γ_anom/熵，与 d_max 并列第一优先）；通道故障/超时 → 降级仅遥测 + 告警升级，行为=v7。
- 规则 22（数据清洗）：进入 Δf_obs 监督集必须过外力门；接触转移单独入池（可用于安全研究与 oracle，禁用于适配）；门阈值 κ-free、保守；泄漏能量预算 η_miss·E‖τ_ext‖² 计入 ε_acc。
- 规则 23（双门与族谱）：每次 OTA 必须过双门；累积预算超界 → 冻结 + 全量再评估；γ_anom CUSUM 漂移 → 冻结；**门机制本身、τ_gate、ε_free 均不得被 OTA 触及（规则 19 扩展到力觉参数）**。

## 算法步骤精炼（离线在第 30 轮六步上加第 7 步；在线 v7 上加带外监控 + 0.65 读标志）

- 离线（+0.3 GPU·天一次性）：第 7 步 ISAAC-BRIDGE + CONTINUAL-ADAPT 烧录——(a) 物理内核托管冒烟（SOC-SIM 人类轨迹注入 Isaac、动力学一致性校验）；(b) 域随机化 rollout 生成 Δf 预训练集（负载/摩擦/线缆刚度/关节间隙四轴）；(c) 力矩传感器噪声模型烧录（E23 测试床）；(d) S_bench v2 物理化对抗场景替换（30/50，规则 20 升版本）；(e) 持续适配管线升级（双门 + 回放缓冲 + 族谱烧录）。
- 在线：带外 1kHz 动量观测器（安全处理器，增量式 <0.1ms/步，独立预算）→ force_alarm 标志；仲裁栈 social_motion_lite_step_v8 = v7 全部步骤保留 + 0.65 读 force_alarm（+0.01ms）→ 置位即强制 cbf_qp_fallback。签名不变；力觉字段缺省 → v8 逐位 = v7 → v6 → v5，退化链完整。

## 复杂度分析（相对第 30 轮增量）
- 在线仲裁：0.41 → 0.42ms（+0.01 标志读取）；带外监控 <0.1ms @1kHz 独立预算（安全处理器，不入规则 14 的 0.5ms 确界，但需单独出具带外 WCET 报告）；P99 <0.5ms 维持（规则 14 重测）。
- 训练账户 1.6 → 1.9 GPU·天一次性（Isaac 生成 0.2 + 预训练 0.1）；持续适配 0.05 → 0.06 GPU·天/次（+Fisher/回放混入 0.01）；回归评测 0.3 → 0.35 GPU·天/发布（E24/E25 新增）。Isaac 工程 2–3 人周（诚实标注：最大成本不在 GPU 在工程）。
- LUT 14MB 不变；关键帧总预算 15.3ms 不变（力觉走 EtherCAT/CAN 总线，不走感知链路）；回放缓冲为磁盘/内存资产（按 IP-10 记账，不入延迟预算）。

## 正确性论证（命题 11–14 新增；命题 9 修订——诚实记录失效与修复）
- 命题 11（力觉检测力/FPR/证据正交）：r_obs → τ_ext 指数收敛（λ_O 设计）；接触类事件的漏检仅依赖力觉通道（视觉漏检由遮挡独立发生）→ 安全证据链升级为双模态；FPR 由自适应噪声底 b̂_noise + χ² 门 + n_win_c=2 持续判据设计；E24a 门槛不过 → 力觉降级仅遥测（fail-safe 结构，无负收益）。
- 命题 12（清洗门下适配不受接触污染）：设清洗门假阴性率 η_miss，则泄漏进 Δf_obs 的接触能量 ≤ η_miss·E‖τ_ext‖²，显式计入 ε_acc 裕量预算；保守阈值使 η_miss ≪ 假阳性率（宁可丢数据）。**命题 9 修订**：第 30 轮"适配单调不劣化"仅在清洗门前提下成立——含接触遥测时验证门会被同分布污染骗过，本轮以规则 22 修复并重述（失效模式入命题登记）。
- 命题 13（持续适配不遗忘/漂移有界）：双门 → 单步新数据 G 不升、记忆 G 不劣化超 ε_forget；族谱累积预算 → ‖Σ Δθ‖ ≤ Θ_cum；SpectralNorm → 输出漂移 ≤ L_π·Θ_cum；γ_anom CUSUM → 标定漂移即时冻结；失效：双门过严 → 适配长期拒更新（"永远空转"）——拒绝率遥测告警（连续 5 轮 >50% → 人工审查 ε_acc/ε_forget 校准）。
- 命题 14（Isaac 预训练样本效率）：域随机化先验 + 少量真机微调 [R30–R35 文献级先验，非本系统实测]；E23 门禁（semi-real 样本效率 ≥2×）不过 → 预训练不采信，Isaac 降级为仅传感器仿真测试床。

## 风险登记簿（继承 + 新增；完整表见产物区）
新增六项，本轮最大：**真机力矩信号质量**——轻量臂摩擦/建模误差使动量残差基线偏高且随温度/负载漂移，τ_gate 与 ε_free 难以一次标定：过高则接触漏检（W2 证据链断裂）、过低则 FPR 失控（fallback 滥刷）或清洗门过松（接触力漏进适配，命题 12 失效）（高）。继承第 30 轮全部十七项；其中"自信地错检"高→中高（力觉补接触级盲区，假手错检仍靠 abstain）；U2 冷启动中高→中（Isaac 预训练）；SOC-SIM 保真中→中低（物理层托管，E18c 仍为确认条件）；新增 Isaac 接口工程量低估（中高）。

**本轮最大风险一句话**：真机力矩信号质量——轻量臂的摩擦与未建模动力学使动量观测器残差基线偏高且随温度/负载漂移，接触阈值 τ_gate 与清洗门 ε_free 难以一次标定，过高则接触漏检（证据链断裂）、过低则 FPR 失控或接触力漏进适配（命题 12 失效）——以 E23a 传感器仿真保真门 + E24a 注入扫描 + 空转段自适应噪声底 + fail-safe 降级结构兜底，任一不过即力觉降级为仅遥测（行为逐位=v7，无负收益），但"独立证据"收益归零，须 A7 真机力矩采集任务先行。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 31 轮产物 · 创新点清单 v8：FORCE-CONTINUAL-LITE 完整算法设计（力觉×持续学习×物理桥版）

## 0. 结论

第 30 轮清单 v7（15 项）本轮完成「独立证据 + 终身适配 + 物理保真」迭代，产出 v8（16 项）：

- **IP-16 FORCE-CONTINUAL-LITE（P1，新增）**：FORCE-CROSS 力觉带外安全监控 + 外力清洗门（力矩传感）+ CONTINUAL-ADAPT 双门防遗忘持续适配（持续学习）+ ISAAC-BRIDGE 物理保真桥（Isaac Sim）；作为 IP-15 的证据层与持续化升级，**在线仲裁签名与延迟预算不变**（仲裁增量仅 +0.01ms，力觉监控带外运行）。
- **IP-13 SOCIAL-MOTION-LITE 微修订**：执行器 v7 → v8（0.65 读 force_alarm + 带外力觉监控器接入）；触发优先级表扩展；力觉字段缺省 → 逐位 v7。
- **IP-14 CULTURA-SIM-LITE 微修订**：SOC-SIM 物理内核可选 Isaac 托管（社会层不动，E18c 资产保护）。
- **IP-7 DISTURB-AUG 微修订**：渲染即标签 v8——物理引擎直接生成力矩/接触真值标签（零额外 GPU）。
- **IP-4 微修订**：OTA 族谱 lineage 回滚（支持任意祖先，不止上一版）。
- **IP-12 微修订**：维护窗口执行 CONTINUAL-ADAPT（双门 + 回放 + 族谱）。
- **IP-2/IP-3 微修订**：S_bench v1 → v2（规则 20 升版本：力觉触发器校准指标进软通道；30/50 对抗场景物理化替换；v6 锚点在 v2 上重跑保可比）。
- IP-1/5/6/8/9/10/11/15 维持（IP-5 冻结；IP-15 为本轮升级对象，其三项机制全部保留并被继承）。
- 成本变化：训练账户 1.6 → 1.9 GPU·天一次性（IP-10 记账）；持续适配 0.05 → 0.06 GPU·天/次；回归评测 0.3 → 0.35 GPU·天/发布；Isaac 工程 2–3 人周；推理仲裁 P99 <0.5ms 维持（0.42ms，裕量 0.08ms 收窄，规则 14 重测）；关键帧总预算 15.3ms 不变。

路线无关原则不变：力觉字段缺省 → v8 逐位 v7；清洗门拦截 → 数据不入适配（管线空转即 v6 安全语义）；Isaac 预训练不采信 → 降级仅测试床；S_bench v2 只增审计不加风险。冻结即回退 v7/v6/v5 能力，无负收益。

## 1. 事实卡（继承与核实状态）

F1–F17 继承（2026-11-07 检索口径）。本轮新增：
- **F18（文献级）**：动量观测器与碰撞检测——广义动量残差对外力估计的指数收敛性与碰撞检测/隔离方法体系 [R34]，用作带外力觉监控与外力清洗门的依据，标注"文献级先验，非真机测量"。
- **F19（文献级）**：持续学习方法谱系——EWC [R30]、经验回放 [R31]、综述 [R32]；域随机化预训练对 sim-to-real 样本效率的提升 [R33]；Isaac Sim/Isaac Lab 的 GPU 并行物理与域随机化能力 [R35]。

行动项更新：**A7（新增）真机力矩信号采集与噪声底标定**（力觉通道上线前置；与 A4/A6 并列最高优先组）；A4 最高优先不变；A6 扩展——回放片段含同步力矩流（如有），供 E23 保真对照；E12/E13/E17/E18/E20 系列门槛验证仍为上线前置条件。

## 2. 创新点清单 v8 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2.1 | 四件套 + 维护窗口调度 | P0 | 无 | SLAM(26轮) | 算力(轻) | 三类 +5~15pt | 维持 |
| IP-2 | SCORE-ALIGN v2 | +S_bench v2 指标软通道（力觉校准/清洗拦截率） | P0 | 无 | 25/27/30/31轮 | 数据(近零) | 步骤分 + 仲裁质量 | 微修订 |
| IP-3 | LOCAL-EVAL | +S_bench v2 烧录与回归（v6 锚点重跑） | P0 | IP-2 | 26/28/29/30/31轮 | 算力(1 GPU) | 迭代速度=生命线 | 微修订 |
| IP-4 | SUBMISSION-OPS v2 | +OTA 族谱 lineage 回滚（任意祖先） | P1 | 无 | 25/27/31轮 | 算力(部署机) | 掉请求→0 | 微修订 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 指针：并入 IP-1 腕-头闭环 | P1 | IP-1 | 26轮 | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG v3 | 渲染即标签 v8：+力矩/接触物理真值通道 | P1 | 无 | 25/28/29/30/31轮 | 数据(近零) | 人为干扰场景 | 微修订 |
| IP-8 | STEP-EFF | 步骤分效率工程（含 π_lite 推理记账） | P1 | A1 | 25/27/28轮 | 零额外 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票；dev 选拔/hold 报告 | P1 | IP-2 | 26/28/30轮 | 算力(一次性) | 全场景 +2~5pt | 维持 |
| IP-10 | COST-LADDER | 三账户记账（本轮 +0.3 训练 +0.01/适配 +0.05/发布 + 工程人日） | P0(纪律) | 无 | 26/28/30/31轮 | 全账户 | 防负 ROI | 微修订 |
| IP-11 | INTENT-GUARD v2 | 手势感知+意图预测+π_lite 仲裁（执行器换 v8，签名不变） | P1 | IP-1,IP-7,IP-13 | 手势×共享控制×运动×轻量×社会 | 算力(0.7+1.9 GPU·天) | 干扰场景 +5~10pt | 微修订 |
| IP-12 | PREDICT-MAINT | 三级健康+维护窗口（+窗口内执行持续适配） | P1 | IP-4 | 预测性维护 | 线上 <2ms/步 | 掉请求→0；感知 −30% | 微修订 |
| IP-13 | SOCIAL-MOTION-LITE | 执行器 v8：+0.65 读 force_alarm + 带外力觉监控 | P1 | IP-11,IP-14,IP-15,IP-16 | **运动×轻量×社会** | 算力(复用 IP-15/16 产物) | 同 v7 + 接触盲区覆盖 | 微修订 |
| IP-14 | CULTURA-SIM-LITE | SOC-SIM + 课程蒸馏 + 文化条件化（+Isaac 物理内核托管） | P1 | IP-13 | 虚拟仿真×课程×文化×**Isaac Sim** | 算力(1.9 GPU·天，一次性) | 社会分↑、OOD 回退率↓ | 微修订 |
| IP-15 | SERVO-ADAPT-LITE | VS-SHIELD + SAFE-ADAPT + FROZEN-BENCH（第 30 轮，全保留） | P1 | IP-13,IP-14 | 视觉伺服×迁移学习×评测指标 | 算力(已计) | 标定鲁棒、真机差距吸收、评测可信 | 维持 |
| IP-16 | FORCE-CONTINUAL-LITE | FORCE-CROSS 力觉带外监控+清洗门 + CONTINUAL-ADAPT 双门防遗忘 + ISAAC-BRIDGE 物理桥 | P1 | IP-12,IP-14,IP-15 | **力矩传感×持续学习×Isaac Sim** | 算力(0.3 GPU·天一次性 + 0.06/适配 + 0.35/发布) | 接触盲区安全、终身适配、物理先验 | **新增** |

## 3. 重点展开：FORCE-CONTINUAL-LITE 完整算法设计（IP-16，接第 30 轮 IP-15 骨架）

### 3.1 符号定义（继承 + v8 新增）

继承第 30 轮全部符号（ξ、κ、Q(ξ,κ)、D(ζ)、p_s、γ_anom(s)、o_t、κ̂_t、μ_c/Δ_κ、K_bin、s、s*、L_s/L̂_s、d_img、h_img、r_img、r_vs、c_min、T_occ、Θ_max、ε_acc、n_min、G(θ,D)、Δ_transfer、C_cov、S_bench、y_oracle）。

| 符号 | 定义 | 精确性质 |
|---|---|---|
| p = M(q)q̇ | **广义动量** | 由关节状态与动力学模型计算，免加速度测量 |
| r_obs | **动量观测器残差** | r_obs = K_O(p − ∫(τ_s + Cᵀq̇ + g + r_obs)dt)；τ_ext=0 → 指数收敛至 0（速率 λ_O）；τ_ext≠0 → r_obs → τ_ext [R34] |
| F̂_ext = J⁻ᵀ·LPF(r_obs) | **任务空间外力估计** | 清洗门与 oracle 的物理证据 |
| ε_free, gate(·) | **自由空间门限/清洗门** | gate ≡ sup_窗口‖r_obs‖ ≤ ε_free；κ-free；假阴性率 η_miss 计入 ε_acc 预算 |
| τ_gate, n_win_c=2 | **接触触发门限/持续判据** | 门限=μ_b+3σ_b 自适应噪声底；κ-free |
| b̂_noise(t) | **自适应噪声底** | 空转段（无接触声称）在线估计基线漂移，跟踪温度/负载慢漂 |
| force_alarm ∈ {0,1} | **带外接触触发标志** | 安全处理器写、仲裁栈读；触发级别最高（与 d_max 并列） |
| ε_forget, Δ_forget | **记忆门裕量/遗忘度量** | Δ_forget = max(0, G(θ_new,D_replay) − G(θ_old,D_replay)) ≤ ε_forget |
| D_replay | **分层回放缓冲** | 按 (ξ, κ-bin, 场景) 分层环形缓冲；时间衰减防分布陈旧 |
| L_EWC | **EWC 辅助正则** | λ_EWC Σ F_i(θ_i − θ_i^anc)²；仅辅助（少数据 Fisher 噪声大，诚实降级） |
| Θ_cum, lineage | **族谱累积漂移预算/版本族谱** | θ^(k)→(parent, Δθ, D 摘要, 双门指标)；Σ‖Δθ‖ ≤ Θ_cum 超界 → 冻结 + 全量再评估 |
| h_γ | **γ_anom CUSUM 漂移门** | γ_anom^(k) 序列漂移 > h_γ → 冻结适配 + 人工审查 |
| ε_fidelity | **Isaac 物理保真门** | 仿真-真机动力学一致性（能量/频谱误差）；E23a 门槛 |

### 3.2 离线算法：ISAAC-BRIDGE + CONTINUAL-ADAPT 烧录（+0.3 GPU·天一次性）

```python
def build_release_v8():   # 在第 30 轮 build_release_v7 产物 (S_bench v1, adapt_pipeline) 之后
    # 第 7a 步：ISAAC-BRIDGE 物理内核托管（Isaac Sim 灵感落地；+0.2 GPU·天 + 2–3 人周工程）
    soc_sim_phys = isaac_bridge(
        soc_sim=SOC_SIM,                     # 人类反应社会层【不动】——E18c 资产保护
        phys_backend="PhysX5_GPU",           # 仅物理层：臂动力学/接触/线缆/摩擦
        domain_rand=dict(payload=[0.5,1.5], friction=[0.3,0.9],
                         cable_stiffness=[0.7,1.3], joint_backlash=[0,1e-3]))  # 四轴 [R33]
    if fidelity_check(soc_sim_phys, ref=A6_replay) > EPS_FIDELITY:   # E23a 保真门
        soc_sim_phys = SOC_SIM            # 降级：回退自建物理内核
    # Δf_θ 预训练集：物理一致转移 + 力矩序列（冷启动先验）
    D_pre = rollout_dataset(soc_sim_phys, n_steps=1e8, gpu_parallel=True)
    θ_pre = pretrain_residual(Δf_θ, D_pre)          # "从零学残差"→"从物理先验微调"
    # 力矩传感器仿真测试床：噪声模型烧录（真机标定前先行的 τ_gate/ε_free 预标定）
    torque_sim = sensor_model(τ_truth=D_pre.τ, noise=CALIB_REPORT.torque_noise,
                              bias_drift=True, temperature_axis=True)

    # 第 7b 步：CONTINUAL-ADAPT 管线升级（持续学习灵感落地；+0.1 GPU·天）
    def continual_adapt(theta_k, lineage, D_new, D_replay):
        D_fit, D_val = split_real(D_new, holdout=0.2)
        D_fit = [tr for tr in D_fit if gate_clean(tr, torque_sim, EPS_FREE)]  # 规则 22 清洗门
        D_val = [tr for tr in D_val if gate_clean(tr, torque_sim, EPS_FREE)]  # val 同样清洗
        D_pool.contact += [tr for tr in D_fit if not gate_clean(tr, ...)]     # 接触转移单独入池
        if len(D_fit) < N_MIN:
            return lineage, REJECT("insufficient")            # 冷启动安全默认（继承）
        F = diag_fisher(theta_k, anchor_set=D_replay)          # EWC 辅助（权重小）
        Δθ = trust_region_solve(
            loss=L_new(D_fit, θ) + ρ_replay(len(D_new))·L_replay(D_replay, θ)
                 + λ_EWC·Σ F_i(θ_i − θ_i^anc)²,
            bound=Θ_MAX)                                       # 信任域（继承）
        θ_new = theta_k + Δθ
        gate_new = G(θ_new, D_val) <= G(theta_k, D_val) - EPS_ACC          # 门 1：新数据（继承）
        gate_mem = G(θ_new, D_replay) <= G(theta_k, D_replay) + EPS_FORGET # 门 2：记忆（新增）
        if gate_new and gate_mem:                                            # 双验证门（规则 23）
            γ_new = recalibrate_anom(θ_new, D_val, SOC_SIM_dev)              # 离线再标定（继承）
            new_node = ota_lineage_push(lineage, parent=theta_k, dθ=Δθ,
                                        meta=dict(D=D_fit摘要, gates=(gate_new, gate_mem)))
            if cum_drift(new_node) > THETA_CUM:               # 族谱累积预算
                freeze_adapt(); schedule_full_reeval(new_node) # 强制全量再评估
            if cusum(gamma_series(lineage)) > H_GAMMA:        # γ_anom 漂移监控
                freeze_adapt(); alert("gamma_drift")
            return new_node, atomic_ota(θ_new, γ_new), ACCEPT  # 捆绑原子 OTA（继承）
        return lineage, REJECT("gate_new" if not gate_new else "gate_mem")  # 拒绝留痕
    # 执行：IP-12 维护窗口；回滚：IP-4 族谱支持回退到任意祖先（不止上一版）

    # 第 7c 步：S_bench v1 → v2（规则 20 升版本；30/50 对抗场景物理化替换）
    S_bench_v2 = upgrade_benchmark(S_bench_v1,
        torque_labels=contact_truth(soc_sim_phys, torque_sim),   # 接触真值：物理+力觉双确认
        adv_replace=30,                                          # Isaac 物理化对抗场景
        anchor_rerun="v6")                                       # v6 锚点在 v2 上重跑保可比
    return S_bench_v2, θ_pre, torque_sim, continual_adapt
```

### 3.3 带外力觉监控器（安全处理器，1kHz，独立预算 <0.1ms/步）

```python
def momentum_observer_step(self, q, q̇, τ_s):        # 增量式；安全处理器；不入仲裁预算
    self.p = M(q) @ q̇
    self.r_obs += K_O * (self.p - self.p_prev
                         + (self.r_obs + τ_s + Cᵀq̇ + g(q)) * δt)   # 离散化 De Luca 形式
    self.p_prev = self.p
    if self.idle_segment(ξ, force_alarm_history):      # 空转段自适应噪声底
        self.b_noise.update(self.r_obs)                # μ+3σ 慢漂跟踪
    τ_gate = self.b_noise.gate()
    if sustained(self.r_obs > τ_gate, n_win=2):
        self.force_alarm = 1                           # 置位即最高优先级触发（规则 21）
        telemetry.log("contact_event", F_ext_hat=J(q)⁻ᵀ @ lpf(self.r_obs))
    if self.sensor_selfcheck_failed():                 # 自检：掉线/偏置漂移/超时
        self.force_alarm = 0; self.mode = "TELEM_ONLY" # 降级仅遥测 + 告警升级，行为=v7
```

### 3.4 在线算法：social_motion_lite_step_v8（签名兼容，仲裁 +0.01ms）

```python
def social_motion_lite_step_v8(self, x_ee, a_pol, threat_ctx, t):
    # 0–0.6 全部继承 v7（ξ 编码 / κ 更新 / 特征伺服层，逐行不变）
    ξ = self.encode_threat_ctx(threat_ctx); ξ_changed = (‖ξ - ξ_last‖_∞ > ε_ξ) or (self.mode != self.mode_last)
    o = self.observe_implicit_feedback(threat_ctx); self.kappa_hat = self.update_kappa(self.kappa_hat, o); κ = self.kappa_hat
    s = self.extract_hand_feature(threat_ctx)
    if self.feat_conf(s) < C_MIN or self.occlusion_span > T_OCC:
        self.vs_active = False
    else:
        self.vs_active = True
        if ‖self.v_ee‖ > V_MIN: self.L_hat = rls_update(self.L_hat, s, self.v_ee, huber=True)
        self.s_pred = predict_feature(s, self.L_hat, self.v_ee, δ_cam)

    # 0.65 力觉证据接入（新增；仅读带外标志；+0.01ms）
    alarm = self.force_alarm          # 安全处理器写、本栈只读——证据采集与决策仲裁分离

    # 1–3 继承 v7（LUT / 蒸馏前向 / 早退出，逐行不变）
    if (t % T_replan == 0) or ξ_changed or (kappa_bin(κ) != self.k_bin_last):
        self.K_mpc = self.tvlqr_lut.lookup(ξ, kappa_bin(κ))
    Δu_lite = self.π_lite.forward(x_ee, ξ, κ); a_lite = self.K_mpc @ x_ee + Δu_lite
    if ξ.d_max < 0.15 and ξ.τ_min > 1.0: a_lite = self.early_exit_policy(x_ee, ξ, κ)

    # 4. 双轨安全回退（v7 四触发一字不改 + 第五触发 force_alarm；全部 κ-free）
    is_high_threat = ξ.d_max > γ_safe
    is_anomaly = (‖Δu_lite‖ > self.gamma_anom) or (self.π_lite.entropy() > H_max)
    is_servo_diverge = (self.vs_active and sustained(self.r_vs > chi2_gate, n_win=3))
    if alarm or is_high_threat or is_anomaly or is_servo_diverge:    # OR 语义，alarm 最先判
        a_lite = self.cbf_qp_fallback(x_ee, threat_ctx,
                                      img_constraint=self.vs_active)

    # 5–6 继承 v5/v7（共享控制融合 + 硬裁剪，不引用 κ）
    a_cmd = (1 - self.u) * a_pol + self.u * a_lite
    a_cmd = self.hard_safety_clip(a_cmd, x_ee, threat_ctx)
    return a_cmd
```

退化链：力觉字段缺省（TELEM_ONLY 或监控器离线）→ v8 逐位 = v7；κ 缺省 + σ_feat=0 → v6；κ 固定 μ_c → v5。完整。

### 3.5 CONTINUAL-ADAPT 机制要点（规则 22/23 落地；规则 19 扩展）

| 机制 | 规格 | 失效防护 |
|---|---|---|
| 清洗门（规则 22） | sup‖r_obs‖ ≤ ε_free 才入 Δf_obs 监督集；接触转移入 D_pool.contact 禁用于适配 | 假阴性率 η_miss·E‖τ_ext‖² 显式计入 ε_acc；阈值保守（宁丢勿毒）；拦截率遥测 |
| 双验证门（规则 23） | 门 1：G(θ_new,D_val) ≤ G(θ_old,D_val) − ε_acc；门 2：G(θ_new,D_replay) ≤ G(θ_old,D_replay) + ε_forget | 任一不过即不更新；拒绝留痕分类计数；双门本身不得被 OTA 触及（规则 19 扩展） |
| 分层回放（主机制） | D_replay 按 (ξ, κ-bin, 场景) 分层环形缓冲；损失 L_new + ρ_replay·L_replay | 时间衰减 + 周期重建防分布陈旧；ρ_replay 随新数据量自适应 |
| EWC（辅助） | λ_EWC·Σ F_i(θ_i − θ_i^anc)²，锚点=上次 OTA | 小权重；少数据 Fisher 噪声大——诚实降级为辅助，主防遗忘靠回放+双门 |
| 族谱 | θ^(k)→(parent, Δθ, meta)；Σ‖Δθ‖ ≤ Θ_cum | 超界 → 冻结 + 强制全量再评估（S_bench dev + 真机 held-out 上重验累积效果） |
| γ_anom 漂移 | CUSUM(γ_anom^(k) 序列) > h_γ | 冻结适配 + 人工审查；漂移历史留痕 |
| Isaac 保真门 | fidelity_check vs A6 参照 ≤ ε_fidelity | 不过 → 物理内核回退自建；预训练不采信（仅测试床） |
| 执行/回滚 | IP-12 维护窗口 + IP-4 OTA/CUSUM/**族谱任意祖先回滚** | 适配后异常率漂移 → 自动回滚（可跨多代） |

### 3.6 复杂度与延迟预算表（P99 确界，对比 v5/v6/v7/v8）

| 环节 | v5 (SML) | v6 (CSL) | v7 (SAL) | v8 (FCL) | 说明 |
|---|---|---|---|---|---|
| 仲裁核心 | 0.35ms | 0.36ms | 0.41ms | **0.42ms**（+0.01 读 force_alarm） | 带外监控不入此预算 |
| 带外力觉监控 | — | — | — | **<0.1ms @1kHz**（安全处理器，独立 WCET 报告） | 增量式动量观测器 |
| LUT 内存 | 2.8MB | 14MB | 14MB | 14MB 不变 | O(1) 查表不变 |
| 早退出 | 0.1ms (60%) | 不变 | 不变 | 不变 | 条件不依赖 κ/特征/力觉 |
| 双轨回退 | <5% | 不变 | +r_vs 触发 | **+force_alarm 触发（最高优先）** | OR 语义，fail-safe |
| 特征/力觉感知 | — | — | 0 新增（复用手感知） | **0 新增**（力觉走总线不走感知链路） | 关键帧预算不变 |
| **合计仲裁增量** | +0.3ms | +0.3ms | +0.35ms | **+0.36ms (P99<0.5ms 维持，裕量 0.08ms)** | 规则 14 确界重测 |
| 训练成本 (IP-10) | 0.3 GPU·天 | 1.4 | 1.6 | **1.9 一次性 + 0.06/适配 + 0.35/发布 + 2–3 人周工程** | 三账户 + 工程人日入账 |

关键帧总预算不变：15.3ms；仲裁 P99 裕量从 0.09ms 收窄至 0.08ms——诚实标注：后续轮次若再增仲裁内环节将突破预算，届时必须走带外化或分频。

### 3.7 正确性论证（命题 11–14 新增；1–10 继承，命题 9 修订）

- **命题 11（力觉检测力/FPR/证据正交，新增核心）**：(a) r_obs → τ_ext 指数收敛（λ_O 带宽设计）[R34]；(b) 接触类事件漏检仅依赖力觉通道——视觉漏检由遮挡独立发生，两误差源近似不相交 → 安全证据链双模态（碰撞事件同时驱动两通道是检测冗余非风险）；(c) FPR：自适应噪声底 μ+3σ + n_win_c=2 持续判据设计 ≤ α_c/h；自检失败 → TELEM_ONLY 降级（行为=v7）。*失效模式*：摩擦/建模误差使基线偏高 → E24a 门槛不过则降级，无负收益。
- **命题 12（清洗门下适配不受接触污染，修复命题 9）**：清洗门假阴性率 η_miss 下，泄漏进 Δf_obs 的接触能量 ≤ η_miss·E‖τ_ext‖²，显式计入 ε_acc 裕量；**命题 9 修订重述**：第 30 轮"适配单调不劣化"仅在清洗门前提下成立——含接触遥测时 D_val 同分布污染可骗过验证门（G(θ_new,D_val) 虚假改善），本轮以规则 22 修复；失效模式已登记入命题 9 历史。
- **命题 13（持续适配不遗忘/漂移有界）**：双验证门 → 单步新数据 G 降、记忆 G 劣化 ≤ ε_forget；族谱预算 → ‖Σ Δθ‖ ≤ Θ_cum；SpectralNorm → ‖π(·;θ^(k)) − π(·;θ^(0))‖ ≤ L_π·Θ_cum（k 步累积仍有界）；γ_anom CUSUM → 标定漂移即时冻结。*失效模式*：双门过严 → 长期拒更新——拒绝率 >50% 连续 5 轮 → 告警并人工审查 ε 校准（semi-real 扫描定标）。
- **命题 14（Isaac 预训练样本效率，门禁采信）**：域随机化先验 + 少量真机微调的样本效率增益为文献级先验 [R30–R35]，非本系统实测；E23 门禁（semi-real 样本效率 ≥2×、物理保真 ≤ ε_fidelity）不过 → 预训练不采信、物理内核回退、Isaac 仅保留传感器仿真测试床用途。
- **命题 1–10 继承**第 30 轮文本；命题 2 WCET 组合更新为 0.3 + 0.05 + 0.01 + 0.05 + 0.1(60%) + 0.01 < 0.5ms（带外 0.1ms @1kHz 单独出具报告）；命题 1 的"触发条件不含 κ"扩展为"不含 κ 与任何可 OTA 量"——τ_gate/ε_free/双门参数全部加入禁改清单（规则 16+19+23 联合）。

### 3.8 双轨安全回退表 v8（文化/适配/力觉三重不变性标注）

| 触发条件 | 行为 | κ 依赖 | 可 OTA 依赖 | E 门槛关联 |
|---|---|---|---|---|
| ξ.d_max > γ_safe=0.8 | cbf_qp_fallback | 无 | 无 | 安全覆盖率 ≥99.5% |
| **force_alarm=1（新增，最高优先）** | cbf_qp_fallback | 无 | **无**（τ_gate 禁改） | E24a：AUC≥0.9、检出 ≤2 步、FPR ≤ α_c/h |
| ‖Δu_lite‖ > γ_anom | cbf_qp_fallback | 无 | γ_anom 随 θ 原子 OTA（双门+CUSUM 后） | 异常率 <1% (P99) |
| π_lite 熵 > H_max | cbf_qp_fallback | 无 | 无 | 熵逸出率 <0.5% |
| r_vs > χ²₃ 门 持续 3 步 | cbf_qp_fallback（vs_active 叠加图像约束） | 无 | 无 | E20b 门槛（继承） |
| 特征置信门不过 | 特征层 abstain → 逐位 v7 行为 + 遥测 | 无 | 无 | E20c 门槛（继承） |
| **力觉通道自检失败（新增）** | TELEM_ONLY：仅遥测 + 告警升级，行为=v7 | 无 | 无 | E24a 自检注入项 |
| 连续 3 步回退 | 遥测 + 模型复审 + OTA | 无 | — | fallback_rate >5% 告警 |
| κ̂ 越带尝试 | clip 拒绝 + 遥测计数 | 仅 κ | — | 越带次数=0（E19） |
| **双验证门拒绝（新增，离线）** | θ/γ_anom 不更新 + 分类留痕 | 无 | 仅此 | E25 双门通过率 ≥60% |
| **族谱预算超界（新增，离线）** | 冻结适配 + 强制全量再评估 | 无 | 仅此 | 规则 23 留痕 |

### 3.9 与其他 IP 的接口（零破坏性变更清单）

- **IP-13/IP-11**：执行器 v7 → v8，签名不变；threat_ctx 可选携带 force_alarm/TELEM_ONLY 状态，缺省 → 行为逐位 v7。
- **IP-14**：SOC-SIM 暴露 phys_backend 注入口；Isaac 托管为可选后端，保真门不过即回退自建；社会层接口零改动。
- **IP-7**：渲染即标签 v8 追加力矩/接触真值通道——物理引擎直接输出（零额外 GPU，~0.3ms/帧 CPU）。
- **IP-2/IP-3**：S_bench v2（升版本 + v6 锚点重跑）；力觉触发器校准、清洗门拦截率进 p_fail 软通道；回归报告版本化落盘。
- **IP-4**：OTA 族谱数据结构（parent 链 + 全量指标快照）；CUSUM 回滚升级为任意祖先回滚。
- **IP-12**：维护窗口执行 continual_adapt；回放缓冲重建调度；Isaac 保真门复检入窗口任务清单。
- **IP-9**：population 学生继续在 S_bench v2 dev 选拔、hold 报告（防选拔泄漏，继承）。
- **IP-10**：训练 +0.3 一次性、适配 0.06/次、评测 0.35/发布、Isaac 工程 2–3 人周，全部入账并触发 ROI 复核。

## 4. IP-7 渲染即标签 v8（力矩/接触物理通道）

```python
def augment_force_labels_v8(physics_seq):   # 物理引擎真值，非渲染——CPU 算术 ~0.3ms/帧
    for step in physics_seq:
        step.social_cost = compute_v6_labels(step)            # 继承 κ 化标签
        step.feature_traj = compute_v7_labels(step)           # 继承特征/L_s/置信（第 30 轮）
        step.torque_truth = τ_ext_truth(step)                 # 物理引擎已知接触 → 外力真值
        step.contact_truth = contact_map(step)                # 接触事件真值（清洗门/oracle 标定用）
    return physics_with_force_labels_v8
```

## 5. 实验设计（新增 E23/E24/E25，接 E20–E22）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| **E23a Isaac 保真与预训练（Isaac Sim 核心）** | 物理内核托管冒烟；力矩仿真频谱/阶跃 vs A6 真机参照（如有）或 datasheet；Δf_θ 预训练 vs 从零（semi-real 样本效率曲线） | 保真误差 ≤ ε_fidelity；样本效率比 | 保真门不过 → 物理内核回退；样本效率 <2× → 预训练不采信（降级仅测试床）；工程 >3 人周 → 范围收缩 |
| **E24a 力觉触发器（力矩传感核心）** | 注入接触/推挤/线缆拉扯/负载突变 + 自检故障注入（torque_sim 测试床 + semi-real） | AUC、检出时延、FPR/h、基线漂移跟踪误差 | AUC≥0.9、检出 ≤2 步、FPR ≤ α_c/h；不过 → TELEM_ONLY 降级 |
| **E24b 清洗门消融** | 有/无清洗门 × 遥测接触占比 {0,10,30}% 全因子 | 适配后异常率、γ_anom 漂移、G 曲线 | 含接触无门时命题 9 失效复现（对照验证）；有门时异常率 <1% (P99) 维持 |
| **E24c 视觉盲区接触** | 遮挡+接触组合场景（σ_feat=0 且度量层无手信息） | force_alarm 检出率 | ≥95%（v7 在此场景无新增覆盖——本轮核心收益） |
| **E25 持续适配滚动（持续学习核心）** | 10 轮滚动适配模拟；中途注入接触污染遥测 | 双门通过率、Δ_forget、族谱预算触发率、γ_anom CUSUM、清洗拦截率 | Δ_forget ≤ ε_forget 全程；累积输出漂移 ≤ L_π·Θ_cum；污染拦截率 ≥99% |
| **E22b S_bench v2 防博弈重审计** | v2 上重跑三恶意策略审计 + v6 锚点 | Pareto 报告、可靠性图、CI/效应量 | 恶意策略仍全暴露；v6 锚点漂移 <2%（版本变更透明性） |
| **E17/E20 系列重跑** | S_bench v2 上回归（π_lite v8 + 力觉 + 适配） | 同第 30 轮门槛 | 同门槛（碰撞=0、P99<0.5ms、社会代价 ≤CBF−15%、回退率<5%、E18c τ≥0.7） |

**降级机制**：E23a 保真门不过 → 物理内核回退自建、预训练不采信；E23a 样本效率不过 → 预训练冻结（adapt 从零路径，n_min 门恢复原值）；E24a 不过 → 力觉 TELEM_ONLY（行为=v7，无负收益）；E24b 显示清洗门失效 → ε_free 收紧 + 适配冻结；E25 遗忘超界 → 适配冻结 + 全量再评估；E22b 恶意策略未被暴露 → 相应轴不作合并门槛；E17 系列任一不过 → IP-13/14/15/16 整体冻结，IP-11 回退 CBF-QP。均无负收益。

## 6. 风险登记簿（完整表）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **真机力矩信号质量（摩擦/建模误差 → 动量残差基线高且温漂，τ_gate/ε_free 难一次标定）——本轮最大** | **高** | E23a 传感器仿真先行 + E24a 注入扫描 + 空转段自适应噪声底（μ+3σ 跟踪慢漂）+ n_win_c 持续判据 + TELEM_ONLY 降级（fail-safe 无负收益）+ A7 真机采集前置 |
| Isaac 接口工程量低估（常见误判点） | 中高 | 范围限定（仅物理层、社会层不动）+ E23a 冒烟门 + 降级路径（仅测试床）+ 工程人日入 IP-10 复核 |
| 清洗门假阴性（接触力泄漏进适配，命题 12 失效） | 中 | 保守阈值（η_miss ≪ 假阳性率）+ 泄漏能量预算入 ε_acc + E24b 消融 + 拦截率遥测 |
| 双门过严 → 适配长期拒更新（"永远空转"） | 中 | ε_acc/ε_forget semi-real 扫描定标 + 拒绝率遥测（>50% 连续 5 轮 → 人工审查） |
| 腕部相机"自信地错检"（第 30 轮最大风险，继承） | 中高（原高） | 力觉补接触级盲区（E24c）+ oracle 增强；假手错检仍靠 abstain/松弛/v6 地板（诚实：力觉不能否证接近判断） |
| U2 真机遥测冷启动（继承） | 中（原中高） | **Isaac 预训练先验（新增）** + semi-real 回放 + n_min 门 |
| SOC-SIM 人类反应保真度（继承） | 中低（原中） | 物理层 Isaac 托管（新增）+ E18c 三级对照仍为确认条件 + 特征层真机闭环 |
| S_bench 隐性过拟合（继承） | 中 | v2 升版本 + v6 锚点重跑透明性（E22b）+ 预注册 + hold 禁调参 |
| r_vs 相关噪声误报（继承） | 中 | Σ̂ 白化 + χ² 门 + E20b + 可冻结 OFF |
| θ/γ_anom OTA 版本不一致（继承） | 低 | 捆绑原子更新 + **族谱任意祖先回滚（新增）** + CUSUM |
| κ 归因误差（继承） | 中 | 带限 clip + E19 + κ̂ 冻结机制 |
| 文化先验表有偏（继承） | 中 | 防刻板印象三条款 + A6 少样本校准 |
| 课程过拟合于仿真难度轴（继承） | 中 | C_cov 反馈 + 课程后期混真实回放 + E18b |
| 蒸馏策略 OOD 安全退化（继承） | 中 | 双轨兜底 + E17 + 适配通道 |
| 奖励模型偏差（继承） | 中 | A6 校准 + 双轨兜底 + 分层 DPO |
| 量化精度损失（继承） | 中 | QAT 校准集扩展 + 确界重测（规则 14） |
| TV-LQR 线性化误差（继承） | 中 | 残差补偿 + 域边界回退 |
| 早退出/κ-bin/r_vs/force_alarm 抖振（继承+扩展） | 低 | 滞回 + 低通 + 持续判据（n_win=3 / n_win_c=2） |
| 回放缓冲分布陈旧（磨损/漂移后旧数据失真） | 低中 | 时间衰减 + 周期重建 + 分层覆盖监控 |
| EWC Fisher 估计噪声（少数据下不可靠） | 低 | 仅辅助小权重；主机制为回放+双门 |
| F9 相机映射/校正未确认（继承） | 高（A4 最高优先） | A4 内参验证提权 + 图像层外参不敏感 + E12/E13 |
| 合成手域差距 + 意图误判（继承） | 高 | 双轨兜底 + B_def + E12/E13 + A6 |
| LUT 插值误差（继承） | 中 | 双线性插值 + 容错带 + E17d |

## 7. 来源清单（检索/核实于 2026-11-07）

- 继承第 27–30 轮 R1–R29，口径不变。
- 本轮新增：
  - R34 Robot Collisions: A Survey on Detection, Isolation, and Identification（Haddadin, De Luca, Albu-Schäffer, IEEE Transactions on Robotics 2017）：经典综述，无 arXiv，如实标注——动量观测器、外力估计与碰撞检测体系出处
  - R30 Overcoming Catastrophic Forgetting in Neural Networks（Kirkpatrick et al., PNAS 2017, EWC）: https://arxiv.org/abs/1612.00796 ✓（核实）
  - R31 Experience Replay for Continual Learning（Rolnick et al., NeurIPS 2019）: https://arxiv.org/abs/1811.11682 ✓（核实）
  - R32 A Comprehensive Survey of Continual Learning: Theory, Method and Application（Wang et al., TPAMI 2023）: https://arxiv.org/abs/2302.00487 ✓（核实）
  - R33 Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World（Tobin et al., IROS 2017）: https://arxiv.org/abs/1703.06907 ✓（核实）
  - R35 NVIDIA Isaac Sim / Isaac Lab 官方文档与 SDK（无 arXiv，如实标注）——GPU 并行物理、域随机化、传感器仿真能力出处
- **诚实记录**：本轮无 arXiv 编号记忆纠错事件；R34/R35 为经典文献/官方文档，无 arXiv 编号，如实标注；命题 9 的第 30 轮失效模式（接触污染骗过验证门）为本轮自审发现，已登记入命题历史并修复（规则 22）。

## 8. 清单迭代规则（继承 + 第 31 轮增补）

- 继承第 28–30 轮规则 12–20（双轨上线强制、社会代价可审计、量化确界、fallback 遥测、E17 门槛、P99 确界、LUT 精度、安全层文化不变、κ 带限防刻板印象、课程判据留痕、适配不变性、评测防博弈）。
- **21（新增）：力觉 fail-safe OR**——力觉监控只增触发不做否决（严禁"力觉平静就不触发"类否决逻辑）；force_alarm 触发级别最高；通道自检失败/超时 → TELEM_ONLY 降级（仅遥测 + 告警升级，行为=v7）；τ_gate、ε_free、双门参数加入禁 OTA 清单（规则 19 扩展）。
- **22（新增）：数据清洗**——进入 Δf_obs 监督集的转移必须通过外力估计门；接触转移单独入池、禁用于模型适配（可用于安全研究与 oracle）；门阈值 κ-free 且保守；假阴性泄漏能量预算显式计入 ε_acc；拦截率入遥测。
- **23（新增）：双门与族谱**——每次 OTA 必须过双验证门（新数据单调不升 + 记忆不劣化 ≤ ε_forget）；族谱累积漂移 ‖Σ Δθ‖ ≤ Θ_cum 超界 → 冻结适配 + 强制全量再评估；γ_anom 序列 CUSUM 漂移 → 冻结 + 人工审查；门机制本身不得被任何 OTA 触及。

---

**本轮最大风险一句话**：真机力矩信号质量——轻量臂的摩擦与未建模动力学使动量观测器残差基线偏高且随温度/负载漂移，接触阈值 τ_gate 与清洗门 ε_free 难以一次标定，过高则接触漏检（证据链断裂）、过低则 FPR 失控或接触力漏进适配（命题 12 失效）——以 E23a 传感器仿真保真门 + E24a 注入扫描 + 空转段自适应噪声底 + fail-safe 降级结构兜底，任一不过即力觉降级为仅遥测（行为逐位=v7，无负收益），但"独立证据"收益归零，须 A7 真机力矩采集任务先行。
<!-- ARTIFACT:END -->
