# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 30 轮 · 思维深化：SERVO-ADAPT-LITE —— 视觉伺服护盾、有界真机适配与防博弈冻结基准

## 直觉锚点与动机链条（承接第 29 轮）

- **弱点诊断 → 灵感映射**：本轮灵感词「视觉伺服 / 迁移学习 / 评测指标」不是三个孤立装饰，而逐一命中第 29 轮 CULTURA-SIM-LITE 的三个结构性弱点，构成改进链：
  - 弱点 1（真机感知"开环于标定"）：第 29 轮在 SOC-SIM 内闭环了人类反应，但真机侧的 ξ 与安全层仍全部工作在度量空间——d_max、d_comfort、CBF 约束、硬裁剪都直接或间接依赖外参与深度标定，而 F9（相机映射/校正未确认）自第 26 轮起持续高危未决；ξ 又是瞬时快照，感知时延使威胁演化滞后一个控制周期。"仿真里闭环了，真机上的感知对误差模型仍然开环。" → **「视觉伺服」U1 VS-SHIELD：特征空间安全层**。像平面量对手部检测与相机内参稳健、对外参/深度误差一阶不敏感 [R25, R26]；交互矩阵 L̂_s 滑窗 RLS 在线估计、由渲染器真值热启动（IP-7 v7 提供 s/L_s 标签）；伺服一致性新息 r_vs（机器人运动补偿后的特征跟踪残差）成为第四个回退触发器——κ-free，守住规则 16。π_lite"自信地错"时，输出空间（‖Δu_lite‖）与策略空间（熵）都抓不到，特征空间能。
  - 弱点 2（sim-to-real 只有"验证+回退"，没有"吸收"）：第 29 轮最大风险（SOC-SIM 保真度）的处置是 E18c 不过就降级——防御有余、进取不足，真实数据进不了管线。而残差网络 Δf_θ 建模的是**动力学**（臂动力学、线缆拖拽、未建模摩擦），由真机自身状态转移 (x_t, u_t, x_{t+1}) 直接可监督——不需要人类模型、不需要专家真值。这是整条管线里唯一"真机自监督可达"的迁移面。→ **「迁移学习」U2 SAFE-ADAPT：信任域微调 + 验证门**。Δf_obs = x_{t+1} − x_t − (A x_t + B u_t) 直接可得；信任域 ‖Δθ‖≤Θ_max、验证门（held-out 真机缓冲上验证误差单调不升）、维护窗口批量执行（复用 IP-12）、θ 与 γ_anom 捆绑原子 OTA（复用 IP-4，CUSUM 回滚）；覆盖指数 C_cov 把真实 (ξ,κ) 分布与课程末段分布的差距反馈给第 29 轮课程采样——评测→训练闭环，同时缓解"课程过拟合于仿真难度轴"。
  - 弱点 3（评测散点、可博弈、跨轮不可比）：E12–E19 八组实验各自为政；单标量门槛诱发 Goodhart——冻结机器人可刷低 C_social、永不触发可刷低 fallback_rate、调阈值可刷任何"率"；无冻结测试集，跨轮比较被基准漂移污染；无功效分析，"−20%"可能是噪声。→ **「评测指标」U3 FROZEN-BENCH：防博弈冻结基准**。任务进度分层 Pareto 比较（层内消融"冻结收益"）、触发器作为二元分类器评 AUC/PR@工作点/可靠性图、预注册 + bootstrap CI + 配对置换检验 [R28, R29]、版本化冻结 S_bench（dev/hold 双套）——跨轮回归的唯一口径。

- **U1 的设计决断——增量约束，不是替代**：图像空间约束 h_img = d_img − ρ_K·r0 以"带松弛的次级约束"并入 CBF-QP（度量约束为硬、图像约束带松弛 s_img 入目标），v6 度量层恒在线作为安全地板；QP 可行性永不因新增约束而破坏（松弛吸收）。特征置信度门（置信 < c_min 或遮挡 > T_occ）→ 特征层整体 abstain，σ_feat=0 时执行器逐位退回 v6。新增触发器与 abstain 判据全部 κ-free。
- **U2 的设计决断——只动 θ，不动安全**：适配不变性公理（新规则 19）：任何适配/OTA 不得触及 γ_safe、H_max、CBF 约束、硬裁剪；γ_anom 仅允许与 θ 捆绑原子 OTA（离线再标定留痕，线上仍是 κ-free 常数）。冷启动鸡生蛋：semi-real（A6 回放 + 真机日志合成 Δf_obs）先把管线跑通；真机存量 < n_min 时管线空转（安全默认 = 不更新）。
- **U3 的设计决断——每个指标配"作弊者画像"**：S_bench v1 = {500 固定种子 SOC-SIM episode（held-out κ* 网格）+ 100 真人回放片段（A6）+ 50 对抗场景}，版本冻结；改动必须升版本并重跑历史；hold 集禁止用于任何调参；合并主张必须预注册（假设/指标/检验/n）。诚实条款：无指标族能对抗一切作弊——预注册 + oracle 季度轮换把 Goodhart 从"结构漏洞"降为"需持续审计的残余风险"。
- **三者耦合**：U1 把真机感知从"开环度量"升级为"标定鲁棒的特征闭环"（把 F9 对安全路径的依赖降为"仅内参"）；U2 给残余 sim-to-real 差距一个有界吸收通道（把第 29 轮"无法采信就废弃"的困境变成"无法采信就在真机上吸收"）；U3 让 U1/U2 的收益声称可证伪、跨轮可比。三者把第 29 轮的"验证条件"升级为"验证 + 吸收 + 审计"三件套。

## 形式化定义的深化（继承第 29 轮全部符号）

### 6.1 特征空间与伺服层符号（v7 新增）
- s_t = (u_t, v_t, ρ_t) ∈ R³：威胁手像平面特征（归一化质心 + log 归一化包围盒面积）；由既有手感知输出算术级导出，零新增感知前向。
- s*：安全像平面目标/边界带，由 d_comfort(κ_d) 与内参 K 反解；e = s − s*。
- L_s ∈ R^{3×6}：交互矩阵（ṡ_ee = L_s·v_ee）；L̂_s 滑窗 RLS 在线估计（W_RLS=30，信噪门 ‖v_ee‖>v_min + Huber 鲁棒化，人手自运动作为回归噪声被抑制），渲染真值热启动。
- d_img = ‖proj_ee − proj_hand‖（仅内参参与投影）；h_img = d_img − r_img，r_img = ρ_K·r0；ρ_K = 1 + c_K·ε_K,max/r0 覆盖内参误差界（c_K 由标定报告推得）。
- r_vs(t)：机器人运动补偿后的特征跟踪新息，窗口化 Mahalanobis（Σ̂ 滑窗白化），门限 χ²₃(1−α)，持续 n_win=3 步判触发；ŝ_{t+1|t} = s_t + L̂_s·v_ee·δt + 特征级 CV 外推（相机时延 δ_cam 补偿）。
- c_min、T_occ：特征置信度门。Θ_max、ε_acc、n_min：U2 信任域/验证门裕量/最小样本。
- G(θ,D) = E_D‖Δf_θ(x,ξ) − Δf_obs‖²；Δ_transfer = G(θ*, D_real,hold) − G(θ*, D_sim,hold)；C_cov = 1 − KL_norm(real (ξ,κ) 直方图 ‖ sim 课程末段直方图) ∈ [0,1]。

### 6.2 伺服项 Lyapunov（诚实版）
灰区 (0.15 < d_max < γ_safe) 激活 u_vs = −λ L̂⁺e；V = ½‖e‖²，V̇ = −λ eᵀL̂L̂⁺e + 交叉项——L̂ 估计误差使负定性仅在 PE 条件 + 误差界内成立；伺服项永不越过硬裁剪，灰区外禁用。诚实条款入命题 7 失效模式。

### 6.3 新增公理：适配不变性（规则 19）与图像层可弃性
- 适配不变性：∂(安全层)/∂θ ≡ 0——γ_safe、H_max、CBF 约束、硬裁剪右端不含 θ 与任何可 OTA 量；γ_anom 捆绑再标定但仍是 κ-free 常数。
- 图像层可弃性：∃σ_feat ∈ {0,1}，σ_feat=0 时执行器逐位等于 v6（由伪代码结构直接可验证，纳入规则 13-1 审计）。

### 6.4 防博弈分层的最小形式化
按任务进度分位（四分位）分层，层内比较 C_social 与舒适违规率——层内任务进度同分布，"冻结刷 C_social"在低进度层被 oracle 审计（任务失败）暴露、在高进度层失去比较资格；触发器校准以离线 oracle（后续 K=10 步约束违反或专家分歧）为标签、γ_anom 触发为预测，评 AUC/PR@工作点 + 可靠性图 [R29]。

## 算法步骤精炼（离线在 v6 六步上加第 5/6 步；在线六步上加 0.6 步）

- 离线（+0.2 GPU·天一次性）：第 5 步 FROZEN-BENCH 烧录（固定种子 + dev/hold 双套 + 预注册）；第 6 步 SAFE-ADAPT 管线（Δf_obs 监督 → 信任域微调 → 验证门 → γ_anom 再标定 → 捆绑原子 OTA，维护窗口内执行、CUSUM 回滚）。IP-7 渲染即标签 v7：s_t 轨迹、L_s 真值、特征置信模拟（零额外 GPU）。
- 在线 social_motion_lite_step_v7：v6 全部步骤保留；插入 0.6 特征伺服层（置信度门 → abstain 或 RLS + r_vs + 外推）；双轨表新增两行（r_vs 触发、abstain），均 κ-free；CBF-QP 在 vs_active 时叠加图像约束（次级带松弛）。签名不变；κ 与特征双缺省 → v7→v6→v5 完整退化链。

## 复杂度分析（相对第 29 轮增量）
- 在线：RLS O(3×6²)≈0.02ms + r_vs 0.01ms + CBF-QP 图像约束项 0.02ms = +0.05ms；仲裁增量 0.36 → 0.41ms，P99 <0.5ms 维持（规则 14 确界重测）。特征计算复用手感知前向，零新增感知。
- 离线：训练账户 1.4 → 1.6 GPU·天（适配管线 0.1 + 基准烧录 0.1，一次性）；SAFE-ADAPT 每次执行 0.05 GPU·天（维护账户）；回归评测 0.3 GPU·天/发布（新设评测账户）。全部入 IP-10 记账。
- LUT 14MB 不变；关键帧总预算 15.3ms 不变。

## 正确性论证（命题 7–10 新增，1–6 继承；诚实版）
- 命题 7（图像约束标定不敏感 + 可弃 + 不可破坏可行性）：内参误差一阶进入且有界（ρ_K 保守化）、外参/深度误差一阶不进入；图像约束为带松弛次级约束 → QP 可行域不变；σ_feat=0 → 逐位 v6。失效：手部"自信地错检" → 图像层收益归零（不倒扣安全）。
- 命题 8（r_vs 检测力/误报）：设计检出 ≥1−β @ 分歧 δ_div 持续 3 步、FPR ≤ α/h（χ² 分位数 + Σ̂ 白化）；诚实条款：相关噪声使白化残差保守、检出力下降但误报受控；E20b 不过 → 触发器冻结 OFF。
- 命题 9（适配有界/单调不劣化）：信任域 + 验证门 → G(θ_new, D_val) ≤ G(θ_old, D_val)；SpectralNorm → ‖π(x;θ_new) − π(x;θ_old)‖ ≤ L_π·Θ_max；γ_anom 捆绑再标定保持双轨语义；安全层 ∂/∂θ ≡ 0（规则 19）。失效：验证门拒绝 → 不更新（安全默认）。
- 命题 10（防博弈分层性，诚实版）：进度分层消解"冻结刷分"，oracle 标签消解"永不触发"；Goodhart 只能降级不能根除——oracle 季度轮换 + hold 禁调参为持续缓解。

## 风险登记簿（继承 + 新增；完整表见产物区）
新增六项，本轮最大：腕部相机手部特征鲁棒性（遮挡/模糊/光照下"自信地错检"，高）。继承第 29 轮全部九项；其中 SOC-SIM 保真度因 U1/U2/U3 三重新增缓解 高→中（E18c 仍为确认条件）；F9 相机映射因图像层解耦外参依赖，但 A4 仍最高优先；课程过拟合因 C_cov 反馈通道进一步缓解。

**本轮最大风险一句话**：腕部相机在遮挡/运动模糊/光照扰动下对威胁手"自信地错检"（置信度门只兜"知道不知道"，不兜"错得自信"），使图像空间约束与 r_vs 触发的收益归零甚至误发——安全由 v6 度量层地板与松弛优先级兜底，但新增层收益可能打折，叠加 U2 真机遥测冷启动的鸡生蛋问题，须以 E20a/b/c 注入式扫描与 E21 semi-real 回放验证后方可采信，任一不过即整层 abstain 冻结退回 v6，无负收益。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 30 轮产物 · 创新点清单 v7：SERVO-ADAPT-LITE 完整算法设计（伺服×迁移×防博弈评测版）

## 0. 结论

第 29 轮清单 v6（14 项）本轮完成「执行层升级 + 真机适配 + 评测基建」迭代，产出 v7（15 项）：

- **IP-15 SERVO-ADAPT-LITE（P1，新增）**：VS-SHIELD 特征空间安全层（视觉伺服）+ SAFE-ADAPT 信任域真机适配（迁移学习）+ FROZEN-BENCH 防博弈冻结基准（评测指标）；作为 IP-13/14 的执行层升级与评测基建，**在线执行器签名与延迟预算不变**（增量 +0.05ms 内）。
- **IP-13 SOCIAL-MOTION-LITE 微修订**：执行器 v6 → v7（0.6 特征伺服层 + 第四触发器 r_vs + abstain 门）；双轨 κ-free 扩展；σ_feat=0 逐位退回 v6。
- **IP-7 DISTURB-AUG 微修订**：渲染即标签 v7——s_t 特征轨迹、L_s 交互矩阵真值、特征置信模拟通道。
- **IP-2 微修订**：S_bench 指标（进度分层舒适违规率、触发器校准 AUC）进入 p_fail 软通道，严格模式不启用。
- **IP-3 微修订**：承载 S_bench 烧录与回归执行（dev/hold 分离）。
- **IP-12 微修订**：维护窗口内执行 SAFE-ADAPT 适配与 OTA。
- IP-1/4/5/6/8/9/10/11/14 维持（IP-5 冻结），无删除项。
- 成本变化：一次性训练账户 1.4 → 1.6 GPU·天（IP-10 记账）；SAFE-ADAPT 每次 0.05 GPU·天（维护账户）；回归评测 0.3 GPU·天/发布（新设评测账户）；推理 P99 <0.5ms 维持；关键帧总预算 15.3ms 不变。

路线无关原则不变：σ_feat=0 即 v6；适配管线空转即 v6；S_bench 只增审计不加风险。冻结即回退 v5/v3 能力，无负收益。

## 1. 事实卡（继承与核实状态）

F1–F15 继承（2026-11-07 检索口径）。本轮新增 **F16（文献级）**：视觉伺服稳定性与标定鲁棒性——IBVS 交互矩阵与 Lyapunov 稳定性 [R25]、2.5D VS 对深度估计误差的鲁棒性 [R26]，用作图像空间安全约束的依据，标注"文献级先验，非真机测量"。**F17（文献级）**：sim-to-real 迁移方法分类（域随机化/域适配/模仿/元学习/蒸馏）[R27] 与深度 RL 统计评测规范（区间估计、显著性检验、预注册）[R28, R29]。行动项：A4 最高优先不变（图像层把 F9 的安全依赖降为"仅内参"，A4 的内参验证部分相对提权）；A6 扩展——真人回放片段作为 S_bench held-out 组成部分与 E21 semi-real 数据源；E12/E13/E17/E18 系列门槛验证为上线前置条件。

## 2. 创新点清单 v7 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v2.1 | 四件套 + 维护窗口调度 | P0 | 无 | SLAM(26轮) | 算力(轻) | 三类 +5~15pt | 维持 |
| IP-2 | SCORE-ALIGN v2 | +S_bench 指标软通道 + 触发器校准输入 | P0 | 无 | 25/27/30轮 | 数据(近零) | 步骤分 + 仲裁质量 | 微修订 |
| IP-3 | LOCAL-EVAL | +S_bench 烧录与回归执行（dev/hold 分离） | P0 | IP-2 | 26/28/29/30轮 | 算力(1 GPU) | 迭代速度=生命线 | 微修订 |
| IP-4 | SUBMISSION-OPS v2 | +CUSUM 预测性故障转移（+OTA 回滚承接适配） | P1 | 无 | 25/27轮 | 算力(部署机) | 掉请求→0 | 维持 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 指针：并入 IP-1 腕-头闭环 | P1 | IP-1 | 26轮 | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG v3 | 渲染即标签 v7：+s_t/L_s 真值 + 特征置信模拟 | P1 | 无 | 25/28/29/30轮 | 数据(近零) | 人为干扰场景 | 微修订 |
| IP-8 | STEP-EFF | 步骤分效率工程（含 π_lite 推理记账） | P1 | A1 | 25/27/28轮 | 零额外 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | population/蒸馏+自洽投票；dev 选拔/hold 报告 | P1 | IP-2 | 26/28/30轮 | 算力(一次性) | 全场景 +2~5pt | 维持 |
| IP-10 | COST-LADDER | 三账户记账（本轮 +0.2 训练 +0.05/适配 +0.3/发布） | P0(纪律) | 无 | 26/28/30轮 | 全账户 | 防负 ROI | 维持 |
| IP-11 | INTENT-GUARD v2 | 手势感知+意图预测+π_lite 仲裁（执行器换 v7，签名不变） | P1 | IP-1,IP-7,IP-13 | 手势×共享控制×运动×轻量×社会 | 算力(0.7+1.6 GPU·天) | 干扰场景 +5~10pt | 维持 |
| IP-12 | PREDICT-MAINT | 三级健康+维护窗口（+窗口内执行适配） | P1 | IP-4 | 预测性维护 | 线上 <2ms/步 | 掉请求→0；感知 −30% | 微修订 |
| IP-13 | SOCIAL-MOTION-LITE | 执行器 v7：0.6 特征伺服层 + 第四触发器 + abstain | P1 | IP-11,IP-14,IP-15 | **运动×轻量×社会** | 算力(复用 IP-15 产物) | 同 v6 + 标定鲁棒 | 微修订 |
| IP-14 | CULTURA-SIM-LITE | SOC-SIM + 课程蒸馏 + 文化条件化（继承第 29 轮） | P1 | IP-13 | 虚拟仿真×课程×文化 | 算力(1.4 GPU·天，一次性) | 社会分↑、OOD 回退率↓ | 维持 |
| IP-15 | SERVO-ADAPT-LITE | VS-SHIELD 特征空间安全层 + SAFE-ADAPT 信任域适配 + FROZEN-BENCH 防博弈基准 | P1 | IP-13,IP-14 | **视觉伺服×迁移学习×评测指标** | 算力(0.2 GPU·天一次性 + 0.05/适配 + 0.3/发布) | 标定鲁棒、真机差距吸收、评测可信 | **新增** |

## 3. 重点展开：SERVO-ADAPT-LITE 完整算法设计（IP-15，接第 29 轮 IP-14 骨架）

### 3.1 符号定义（继承 + v7 新增）

继承第 29 轮全部符号（ξ、κ、Q(ξ,κ)、D(ζ)、p_s、γ_anom(s)、o_t、κ̂_t、μ_c/Δ_κ、K_bin）。

| 符号 | 定义 | 精确性质 |
|---|---|---|
| s=(u,v,ρ) ∈ R³ | **威胁手像平面特征**：归一化质心 + log 归一化面积 | 由既有手感知算术导出，零新增前向 |
| s*, e=s−s* | **伺服目标/误差** | s* 由 d_comfort(κ_d) 与内参 K 反解 |
| L_s ∈ R^{3×6}，L̂_s | **交互矩阵**（ṡ_ee = L_s·v_ee）与其在线估计 | 滑窗 RLS（W=30）+ 信噪门 + Huber；渲染真值热启动 |
| d_img, h_img, r_img=ρ_K·r0 | **图像空间裕量/CBF 函数** | 仅内参参与投影；ρ_K = 1 + c_K·ε_K,max/r0 覆盖内参误差界 |
| r_vs | **伺服一致性新息**（运动补偿后特征跟踪残差） | 窗口 Mahalanobis + Σ̂ 白化；χ²₃(1−α) 门限；n_win=3；**κ-free** |
| c_min, T_occ | **特征置信度门** | 不过 → σ_feat=0 → 逐位 v6 |
| Θ_max, ε_acc, n_min | **信任域/验证门裕量/最小样本** | U2 适配三参数；n_min 未达 → 空转 |
| G(θ,D), Δ_transfer, C_cov | **迁移误差泛函/差距/覆盖指数** | Δf_obs 真机自监督可得；C_cov ∈ [0,1] 馈回课程 |
| S_bench v1 | **冻结基准**：500 sim 种子 + 100 真人回放 + 50 对抗 | dev/hold 双套；版本化；改动必升版 |
| y_oracle | **真异常标签**：后续 K=10 步约束违反或专家分歧 | 离线计算；触发器校准用 |

### 3.2 离线算法：FROZEN-BENCH 烧录 + SAFE-ADAPT 管线（+0.2 GPU·天一次性）

```python
def build_release_v7():   # 在第 29 轮 generate_expert_dataset_v6 产物 (φ*, θ*, K_lut) 之后
    # 第 5 步：FROZEN-BENCH 烧录（评测指标灵感落地；+0.1 GPU·天）
    S_bench = freeze_benchmark(
        sim=sample_seeded(SOC_SIM_eval, n=500, seeds=SEEDS_V1,
                          kappa_grid=HELD_OUT_KAPPA_GRID),   # held-out κ* 网格
        real=A6_replay_clips(n=100),                          # 真人回放（A6）
        adv=adversarial_scenarios(n=50),
        split=dict(dev=0.5, hold=0.5))                        # 防隐性调参
    preregister(S_bench.hold, hypotheses=SERVO_INDEX_AXES,
                stats=dict(ci="bootstrap95", test="paired_permutation",
                           power=dict(alpha=0.05, beta=0.2)))  # 规则 20

    # 第 6 步：SAFE-ADAPT 适配管线（迁移学习灵感落地；+0.1 GPU·天）
    def adapt_residual(theta, telemetry):
        D_fit, D_val = split_real(telemetry, holdout=0.2)
        if len(D_fit) < N_MIN:                                 # 冷启动安全默认
            return theta, REJECT("insufficient", n=len(D_fit))
        # 真机自监督：动力学残差由状态转移直接可得（无需人类模型/专家真值）
        Δf_obs = [x2 - x1 - (A @ x1 + B @ u)
                  for (x1, u, x2) in D_fit]                    # (x, ξ, Δf_obs)
        Δθ = trust_region_solve(
            loss=Σ‖Δf_θ(x,ξ) − Δf_obs‖² + μ‖Δθ‖², bound=Θ_MAX)  # 信任域
        θ_new = theta + Δθ
        if G(θ_new, D_val) <= G(theta, D_val) - EPS_ACC:        # 验证门：单调不升 + 裕量
            γ_anom_new = recalibrate_anom(θ_new, D_val, SOC_SIM_dev)  # 离线再标定，κ-free
            return atomic_ota(params=θ_new, gamma_anom=γ_anom_new), ACCEPT  # 捆绑原子更新
        return theta, REJECT("validation_gate")                 # 拒绝遥测计数（规则 19）
    # 执行：IP-12 维护窗口内；传输/回滚复用 IP-4（CUSUM 监控适配后异常率漂移）

    # IP-7 渲染即标签 v7（追加，零额外 GPU）
    for frame in rendered_seq:
        frame.feature_traj = [(u_t, v_t, ρ_t)]                  # 像平面特征真值
        frame.interaction_matrix = L_s_truth(p_hand, Z, K)      # 渲染器已知位姿 → 3×6 真值
        frame.feature_conf = simulate_conf(occlusion, blur, light)  # 置信度门训练/评测
    return S_bench, adapt_pipeline
```

### 3.3 在线算法：social_motion_lite_step_v7（签名兼容，<0.5ms/步）

```python
def social_motion_lite_step_v7(self, x_ee, a_pol, threat_ctx, t):
    # 0. ξ 编码（继承 v6；伺服特征与 ξ 共享同一次手感知前向，零新增感知）
    ξ = self.encode_threat_ctx(threat_ctx)
    ξ_changed = (‖ξ - ξ_last‖_∞ > ε_ξ) or (self.mode != self.mode_last)

    # 0.5 κ 观测/更新（继承 v6，O(1) 标量，<0.01ms）
    o = self.observe_implicit_feedback(threat_ctx)
    self.kappa_hat = self.update_kappa(self.kappa_hat, o)
    κ = self.kappa_hat

    # 0.6 特征伺服层（新增；全部 κ-free；+0.05ms）
    s = self.extract_hand_feature(threat_ctx)          # 复用手感知输出，算术级
    if self.feat_conf(s) < C_MIN or self.occlusion_span > T_OCC:
        self.vs_active = False                          # abstain：行为逐位退回 v6
    else:
        self.vs_active = True
        if ‖self.v_ee‖ > V_MIN:                         # 信噪门：仅机器人真实运动时更新
            self.L_hat = rls_update(self.L_hat, s, self.v_ee, huber=True)  # 0.02ms
        self.s_pred = predict_feature(s, self.L_hat, self.v_ee, δ_cam)  # 时延补偿外推

    # 1. 稀疏重规划 LUT（继承 v6，索引 (ξ, κ-bin)）
    if (t % T_replan == 0) or ξ_changed or (kappa_bin(κ) != self.k_bin_last):
        self.K_mpc = self.tvlqr_lut.lookup(ξ, kappa_bin(κ))     # O(1)

    # 2. 蒸馏策略前向（继承 v6，输入 (x, ξ, κ)）
    Δu_lite = self.π_lite.forward(x_ee, ξ, κ)
    a_lite = self.K_mpc @ x_ee + Δu_lite

    # 3. 早退出（继承 v6，条件不依赖 κ）
    if ξ.d_max < 0.15 and ξ.τ_min > 1.0:
        a_lite = self.early_exit_policy(x_ee, ξ, κ)

    # 4. 双轨安全回退（v6 三触发一字不改 + 第四触发 r_vs；全部 κ-free）
    is_high_threat = ξ.d_max > γ_safe
    is_anomaly = (‖Δu_lite‖ > self.gamma_anom) or (self.π_lite.entropy() > H_max)
    is_servo_diverge = (self.vs_active and
                        sustained(self.r_vs > chi2_gate, n_win=3))     # 新增，κ-free
    if is_high_threat or is_anomaly or is_servo_diverge:
        a_lite = self.cbf_qp_fallback(x_ee, threat_ctx,
                                      img_constraint=self.vs_active)   # 图像约束叠加

    # 5. 共享控制融合 + 6. 硬安全裁剪（均继承 v5/v6，不引用 κ）
    a_cmd = (1 - self.u) * a_pol + self.u * a_lite
    a_cmd = self.hard_safety_clip(a_cmd, x_ee, threat_ctx)
    return a_cmd
```

κ 缺省 + 特征字段缺省（σ_feat=0）→ 行为精确退化为第 29 轮 v6；再 κ 固定 μ_c → v5。退化链 v7→v6→v5 完整。

### 3.4 图像空间 CBF 约束与一致性监测构造

```python
def add_image_space_constraint(cbf_qp, s, L_hat, v_ee, r0, c_K, eps_K_max):
    # 图像约束：h_img = d_img − ρ_K·r0 ≥ 0；ḣ_img ≥ −α_img(h_img)
    d_img  = ‖proj_hand(s) − proj_ee‖          # 仅内参参与投影（外参/深度误差一阶不进入）
    ρ_K    = 1 + c_K * eps_K_max / r0          # 内参误差保守因子（标定报告推得）
    A_img  = ∇d_imgᵀ @ L_hat @ J_x⁺            # 特征误差对 EE 指令的雅可比（伺服标准形式）
    # 次级带松弛约束：度量约束（v6）为硬，图像约束带松弛 s_img 入目标——
    # 可行域永不因新增约束而空（松弛吸收），图像层错误最多"约束退化到松弛"
    cbf_qp.add_soft(A_img @ v_ee ≥ -α_img(d_img - ρ_K*r0) + hand_motion_comp,
                    slack=s_img, weight=w_img)
    if cbf_qp.infeasible: drop(s_img_constraint); telemetry.log("img_constraint_dropped")

def servo_consistency(s, s_pred, Sigma_hat):
    # r_vs = 运动补偿后的特征跟踪新息（Kalman innovation 等价形式）
    r = (s - s_pred)ᵀ @ inv(Sigma_hat) @ (s - s_pred)     # Σ̂ 滑窗白化，0.01ms
    return r                                              # 门限 χ²₃(1−α)，持续 3 步触发
```

### 3.5 SAFE-ADAPT 适配管线要点（规则 19 落地）

| 机制 | 规格 | 失效防护 |
|---|---|---|
| 监督信号 | Δf_obs = x_{t+1} − x_t − (A x_t + B u_t)，真机状态日志 | 动力学不文化化（第 29 轮决断）；无需人类模型 |
| 信任域 | ‖Δθ‖₂ ≤ Θ_max + μ 正则 | SpectralNorm 下 ‖Δπ‖ ≤ L_π·Θ_max |
| 验证门 | G(θ_new, D_val) ≤ G(θ_old, D_val) − ε_acc | 拒绝即不更新（安全默认）+ 遥测计数 |
| 最小样本 | n_min（未达 → 空转） | 冷启动鸡生蛋防护；semi-real 先行 |
| γ_anom 再标定 | θ_new 在 SOC-SIM dev 上重算 ‖Δu‖ P99 | 与 θ 捆绑原子 OTA；κ-free 常数语义不变 |
| 执行/回滚 | IP-12 维护窗口 + IP-4 OTA/CUSUM | 适配后异常率漂移 → 自动回滚 |

### 3.6 复杂度与延迟预算表（P99 确界，对比 v3/v5/v6/v7）

| 环节 | v3 (CBF-QP) | v5 (SML) | v6 (CSL) | v7 (SAL) | 说明 |
|---|---|---|---|---|---|
| 仲裁核心 | ~1.0ms | 0.35ms | 0.36ms（κ 更新 0.01） | **0.41ms**（RLS 0.02 + r_vs 0.01 + 图像约束 0.02） | 特征复用手感知前向 |
| LUT 内存 | 无（在线求解） | 2.8MB | 14MB | 14MB 不变 | O(1) 查表不变 |
| 早退出 | 无 | 0.1ms (60%) | 不变 | 不变 | 条件不依赖 κ/特征 |
| 双轨回退 | 主路径 | <5% | 不变（文化不变） | 不变 + 第四触发 r_vs（κ-free） | 触发语义 κ-free 扩展 |
| 特征感知 | — | — | — | **0 新增**（复用手感知） | 关键帧预算不变 |
| **合计仲裁增量** | +1.0ms | +0.3ms | +0.3ms (P99<0.5ms) | **+0.35ms (P99<0.5ms 维持)** | 规则 14 确界重测 |
| 训练成本 (IP-10) | 0 | 0.3 GPU·天 | 1.4 GPU·天（一次性） | **1.6 GPU·天（一次性）+ 0.05/适配 + 0.3/发布** | 三账户分别入账 |

关键帧总预算不变：15.3ms（手感知不变），仍在 >100ms 余量内。

### 3.7 正确性论证（命题 1–10；1–6 继承第 29 轮，7–10 新增，诚实版）

- **命题 7（图像约束标定不敏感 + 可弃 + 不破坏可行性，新增核心）**：(a) d_img 仅依赖内参与手部检测，内参误差 ε_K → d_img 扰动 ≤ c_K·ε_K（有界，标定报告可推），ρ_K 保守化后图像约束不劣于 v6 度量约束，外参/深度误差一阶不进入；(b) 图像约束为带松弛次级约束 → CBF-QP 可行域不变，松弛吸收图像层错误；(c) σ_feat=0 → 执行器逐位等于 v6。*失效模式*：手部"自信地错检"（假手/错框）→ 图像层收益归零（不倒扣安全，v6 地板恒在）。
- **命题 8（r_vs 检测力与误报）**：H1（模型/感知分歧 ≥ δ_div 持续 3 步）下检出概率 ≥ 1−β，FPR ≤ α/h（χ²₃ 分位数 + Σ̂ 滑窗白化设计）。*诚实条款*：相关噪声（全局抖动）使白化残差保守、检出力下降但误报受控；E20b 门槛不过 → 触发器冻结 OFF（零侵入）。
- **命题 9（适配单调不劣化 + 有界影响）**：信任域 + 验证门 → G(θ_new, D_val) ≤ G(θ_old, D_val)；SpectralNorm 结构 → ‖π(x;θ_new) − π(x;θ_old)‖ ≤ L_π·Θ_max；γ_anom 与 θ 捆绑原子再标定 → 双轨语义保持；安全层 ∂/∂θ ≡ 0（规则 19）。*失效模式*：验证门拒绝 → 不更新；OTA 后 CUSUM 漂移 → 自动回滚。
- **命题 10（评测防博弈分层性，诚实版）**：任务进度分层比较消解"冻结刷 C_social"（层内进度同分布）；oracle 标签（K 步约束违反/专家分歧）消解"永不触发"；预注册 + bootstrap CI + 配对置换检验消解"噪声当收益"[R28, R29]。*诚实条款*：Goodhart 只能降级不能根除——oracle 季度轮换、hold 禁调参、S_bench 版本化是持续缓解而非一次性免疫。
- **命题 1–6 继承**第 29 轮文本（安全文化不变性 / 实时性 / 课程方差优势 / κ̂ 一致性 / 平滑性 / 可消融）；其中命题 2 的 WCET 组合更新为 0.3 + 0.05 + 0.01 + 0.05 + 0.1(60% 案例) < 0.5ms，按规则 14 重测出具报告；命题 1 的"触发条件不含 κ"扩展为"触发条件不含 κ 与任何可 OTA 量"（规则 16+19 联合）。

### 3.8 双轨安全回退表 v7（文化/适配双不变性标注）

| 触发条件 | 行为 | κ 依赖 | 可 OTA 依赖 | E 门槛关联 |
|---|---|---|---|---|
| ξ.d_max > γ_safe=0.8 | cbf_qp_fallback | 无 | 无 | 安全覆盖率 ≥99.5% |
| ‖Δu_lite‖ > γ_anom | cbf_qp_fallback | 无 | γ_anom 随 θ 原子 OTA（离线再标定留痕） | 异常率 <1% (P99) |
| π_lite 熵 > H_max | cbf_qp_fallback | 无 | 无 | 熵逸出率 <0.5% |
| **r_vs > χ²₃ 门 持续 3 步（新增）** | cbf_qp_fallback（vs_active 时叠加图像约束） | **无** | **无** | E20b：AUC≥0.8、FPR≤α/h、检出 ≤3 步 |
| **特征置信门不过（新增）** | 特征层 abstain → 逐位 v6 + 遥测 | **无** | **无** | E20c：abstain 正确率 ≥99% |
| 连续 3 步回退 | 遥测 + 模型复审 + OTA | 无 | — | fallback_rate >5% 告警 |
| κ̂ 越带尝试 | clip 拒绝 + 遥测计数 | 仅 κ | — | 越带次数=0（E19） |
| **适配验证门拒绝（新增，离线）** | θ/γ_anom 不更新 + 遥测 | 无 | 仅此 | 规则 19 留痕 |

### 3.9 与其他 IP 的接口（零破坏性变更清单）

- **IP-13/IP-11**：执行器 v6 → v7，签名不变；threat_ctx 可选携带特征字段（s、置信度），缺省 → abstain → v6。
- **IP-7**：渲染管线追加 s_t / L_s / 置信度三通道（§3.2），零额外 GPU。
- **IP-2**：S_bench 指标（进度分层舒适违规率、触发器校准 AUC）进入 p_fail 软通道，严格模式不启用。
- **IP-3**：S_bench 烧录与回归执行环境；dev/hold 分离；回归报告版本化落盘。
- **IP-4/IP-12**：OTA 通道承接 (θ, γ_anom) 捆绑原子更新；CUSUM 监控适配后异常率漂移并自动回滚；维护窗口执行适配。
- **IP-9**：population 学生在 S_bench dev 上选拔、hold 上报告（防选拔泄漏）。
- **IP-10**：训练账户 +0.2（一次性）+ 适配 0.05/次（维护账户）+ 回归 0.3/发布（新设评测账户），ROI 复核自动触发。

## 4. IP-7 渲染即标签 v7（特征伺服通道）

```python
def augment_feature_labels_v7(rendered_seq):
    for frame in rendered_seq:
        frame.social_cost = compute_v6_labels(frame)          # 继承第 29 轮 κ 化标签
        frame.feature_traj.append((u, v, ρ))                  # 像平面特征真值
        frame.interaction_matrix = L_s_truth(p_hand, Z, K)    # 渲染器已知位姿 → 3×6 真值
        frame.feature_conf = simulate_conf(occlusion, blur, light)  # 置信度门标定数据
    return render_with_feature_labels_v7
```

成本：纯 CPU 算术，~0.5ms/帧，零额外 GPU。

## 5. 实验设计（新增 E20/E21/E22，接 E12–E19）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| **E20a 标定误差注入（视觉伺服核心）** | 外参旋转 ±3°、平移 ±30mm、深度尺度 ±15% 全因子扫描（SOC-SIM + IP-7 渲染） | 安全覆盖率、d_img 约束违规率、任务分 vs v6 | 图像层不劣于 v6 且至少一个误差档显著更优（配对置换 p<0.05）；安全事件=0；否则 VS-SHIELD 冻结 |
| **E20b r_vs 触发器 ROC** | 注入感知攻击/模型失配/正常噪声三类场景 | AUC、PR@工作点、FPR/h、检出时延 | AUC≥0.8、FPR≤α（设计值）、检出 ≤3 步；不过则触发器冻结 OFF |
| **E20c 特征消融** | 遮挡/模糊/光照扰动轴（IP-7） | abstain 正确率、abstain 后与 v6 逐位一致性 | ≥99%；逐位一致=100% |
| **E21 适配管线** | semi-real（A6 回放 + 真机日志合成 Δf_obs）→ 信任域微调全流程 | Δ_transfer 前后比、样本效率曲线、验证门拒绝率、γ_anom 再标定后异常率 | 验证误差单调不升；适配后 Δ_transfer ≤0.5×；异常率 <1%（P99）维持；不过则 SAFE-ADAPT 关闭 |
| **E22 基准与防博弈审计** | 冻结 S_bench v1；三恶意策略（冻结机器人/永不触发/阈值 gaming）审计 | Pareto 报告暴露性、触发器校准可靠性图、预注册 CI/效应量 | 三恶意策略全部被暴露；v7 全轴 ≥ v6（任一轴显著劣化 → 回退审查） |
| **E17/E18 系列重跑** | S_bench v1 上回归（π_lite v7 + 适配管线） | 同第 28/29 轮 | 同门槛（碰撞=0、P99<0.5ms、社会代价 ≤CBF−15%、回退率<5%、E18c τ≥0.7） |

**降级机制**：E20a/c 任一不过 → VS-SHIELD 冻结（σ_feat=0，行为=v6）；E20b 不过 → r_vs 触发器冻结 OFF；E21 不过 → SAFE-ADAPT 关闭（θ* 冻结于 v6，仅离线迭代）；E22 不过 → 相应轴不作为合并门槛并启动基准审查；E17 系列任一不过 → IP-13/14/15 整体冻结，IP-11 回退 CBF-QP。均无负收益。

## 6. 风险登记簿（完整表）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **腕部相机手部特征鲁棒性（遮挡/模糊/光照下"自信地错检"）——本轮最大** | **高** | 置信度门 + abstain 优雅退化；图像层为增量约束非替代（v6 度量层地板恒在、松弛保证可行性）；oracle 审计捕捉错检；E20c 门禁 |
| **U2 真机遥测冷启动（鸡生蛋：适配需要真机数据，上线前没有）** | **中高** | semi-real 回放先行；n_min 门（不足即空转）；A6 采集；门拒绝率遥测 |
| 检测误差污染图像约束（假手/错框） | 中 | 置信度门 + ρ_K 保守因子 + 次级带松弛（可行性不破坏）+ oracle 审计 |
| r_vs 相关噪声误报（全局抖动） | 中 | Σ̂ 滑窗白化 + χ² 分位数设计 + E20b FPR 门槛 + 触发器可冻结 OFF |
| S_bench 隐性过拟合（跨轮隐性调参） | 中 | 版本冻结 + dev/hold 双套 + 预注册 + oracle 季度轮换 + hold 禁调参 |
| θ/γ_anom OTA 版本不一致 | 低 | 捆绑原子更新 + 规则 18/19 审计 + IP-4 CUSUM 回滚 |
| SOC-SIM 人类反应保真度（继承第 29 轮最大风险） | 中（U1/U2/U3 三重新增缓解；E18c 仍为确认条件） | E18c 三级对照 + 真机适配吸收通道 + 特征层真机闭环 |
| κ 归因误差（继承） | 中 | 带限 clip + E19 门槛 + κ̂ 冻结机制 |
| 文化先验表有偏（继承） | 中 | 防刻板印象三条款 + A6 少样本校准 |
| 课程过拟合于仿真难度轴（继承，进一步缓解） | 中 | **C_cov 反馈通道（新增）** + 课程后期混入真实回放 + E18b 消融 |
| 蒸馏策略 OOD 安全退化（继承） | 中 | 双轨兜底 + E17 门槛 + 适配通道 |
| 奖励模型偏差（继承） | 中 | A6 校准 + 双轨兜底 + 分层 DPO |
| 量化精度损失（继承） | 中 | QAT 校准集扩展 + 确界重测（规则 14） |
| TV-LQR 线性化误差（继承） | 中 | 残差补偿（不文化化）+ 域边界回退 |
| 早退出/κ-bin/r_vs 抖振（继承+扩展） | 低 | 滞回 + 低通 + n_win=3 持续判据 |
| F9 相机映射/校正未确认（继承；**图像层把安全依赖降为"仅内参"**） | 高（A4 仍最高优先） | A4 内参验证相对提权 + 图像层外参不敏感 + E12/E13 |
| 合成手域差距 + 意图误判（继承） | 高 | 双轨兜底 + B_def + E12/E13 + A6 |
| LUT 插值误差（继承，κ 维扩展） | 中 | 双线性插值 + 容错带 δ_lut + E17d 扩展 |

## 7. 来源清单（检索/核实于 2026-11-07）

- 继承第 27/28/29 轮 R1–R24，口径不变。
- 本轮新增：
  - R25 Visual Servo Control. Part I: Basic Approaches / Part II: Advanced Approaches（Chaumette & Hutchinson, IEEE Robotics & Automation Magazine 2006/2007）：经典教程，无 arXiv，如实标注——IBVS 交互矩阵与 Lyapunov 稳定性出处
  - R26 2 1/2 D Visual Servoing: A New Approach...（Malis, Chaumette, Boudet, IEEE T-RA 1999）：经典论文，无 arXiv，如实标注——对深度估计误差的鲁棒性出处
  - R27 Sim-to-Real Transfer in Deep Reinforcement Learning for Robotics: a Survey（Zhao, Peña Queralta, Westerlund, IEEE SSCI 2020）: https://arxiv.org/abs/2009.13303 ✓（arXiv API 核实）
  - R28 Deep Reinforcement Learning that Matters（Henderson et al., AAAI 2018）: https://arxiv.org/abs/1709.06560 ✓（核实）
  - R29 Deep Reinforcement Learning at the Edge of the Statistical Precipice（Agarwal et al., NeurIPS 2021, rliable）: https://arxiv.org/abs/2108.13264 ✓（核实）
- **诚实记录**：本轮曾凭记忆引用 arXiv:2006.15364 为 sim-to-real 综述，经 arXiv 页面核实为无关论文（Multiple Chaotic Attractors in Coupled Lorenz Systems），已废弃并经 API 检索换用正确编号 arXiv:2009.13303。R25/R26 为经典文献、无 arXiv 编号，如实标注。

## 8. 清单迭代规则（继承 + 第 30 轮增补）

- 继承第 28/29 轮规则 12–18（双轨上线强制、社会代价可审计、量化确界、fallback 遥测、E17 门槛、P99 确界、LUT 精度、安全层文化不变、κ 带限防刻板印象、课程判据留痕）。
- **19（新增）：适配不变性**——任何在线/OTA 适配不得触及 γ_safe、H_max、CBF 约束、硬裁剪与回退触发语义；γ_anom 仅允许与 θ 捆绑原子 OTA 且离线再标定留痕；适配更新必须通过验证门并遥测 accept/reject 计数；n_min 未达时管线必须空转。
- **20（新增）：评测防博弈**——合并主张必须在冻结版 S_bench 上预注册（假设/指标/统计检验/样本量），报告 bootstrap CI 与效应量 [R29]；任何指标修改必须附"作弊者画像"分析；跨轮比较仅在同一 S_bench 版本内有效；hold 集禁止用于任何调参与选拔。

---

**本轮最大风险一句话**：腕部相机在遮挡/运动模糊/光照扰动下对威胁手"自信地错检"（置信度门只兜"知道不知道"，不兜"错得自信"），使图像空间约束与 r_vs 触发的收益归零甚至误发——安全由 v6 度量层地板与松弛优先级兜底，但新增层收益可能打折，叠加 U2 真机遥测冷启动的鸡生蛋问题，须以 E20a/b/c 注入式扫描与 E21 semi-real 回放验证后方可采信，任一不过即整层 abstain 冻结退回 v6，无负收益。
<!-- ARTIFACT:END -->
