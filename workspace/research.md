# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 24 轮（研究线累计）· PLAN-GATE（规划门）：用「路径规划」给伦理审查装上执行引擎，用「子目标抽象」把泛化从记忆搬到规划

> 检索日期：2026-11-05。灵感词：**伦理审查 / 泛化能力 / 路径规划**。
> 本轮是对第 23 轮 M3S 的**深化与修剪**，不是推倒重来。上一轮立了三根柱子（MVP-SPINE / 3D-ANCHOR / REVIEW-GATE），但 REVIEW-GATE 只有一个「裁剪器」，缺一个真正的**执行引擎**；而「泛化能力」这一竞赛核心，还没被定义成可测量的账本。本轮三个词正好补齐：**路径规划**给审查门装引擎，**伦理审查**给不可逆/人机安全装上「可逆性证书」，**泛化能力**把五轴变成账本，并接上一条由审查留痕驱动的数据飞轮。

## 0. 三分钟直觉：上一轮的门缺一个引擎

先对齐本轮新核实的事实（来源见 §7；⚠ = 本轮新增或更正）：

- ⚠ **官方接口细节复核**（`unibot_submission` README）：观测原生分辨率 `[480,640,3]`；`obs_delta_indices` 同时决定**发哪些通道**与**时间堆叠**；`image_resize` 由评测端 `cv2.resize` 预缩后再发；`action_chunk_size=T_a`、动作数组形如 `(T_a,·)`、**index 0 先执行**；N 端口从 8765 起、N 另行公布；§6 明确记录**每步时延与波动 + 返回动作的统计规律性**。
- ⚠ **UnifoLM-VLA-0 训练栈确切路径**：要求 **LeRobot V2.1** → 先 `convert_lerobot_to_hdf5.py` → 再 `tfds build` 成 **RLDS**；基座 `UnifoLM-VLM-Base` / `UnifoLM-VLA-Base` / `UnifoLM-VLA-LIBERO` 均已开源。挑战数据是 **LeRobot v3.0** → 转码是 G1 的现实工作量；但 Agent 还给了现成的 **LIBERO 仿真评测脚本**（可当泛化的离线代理）。
- ⚠ **规则正文在飞书（Feishu）文档**：本轮抓到页面壳，但正文为 JS 动态渲染/需登录（中文 `Uz7OdFBcDo...` / 英文 `ZNHIdaGx...`），**未能机读**。所以「步骤分」细则仍属未证实口径，设计上保持「少无效步 + 子目标完成即停」的保守假设。
- ⚠ **数据集特权状态复核**：`*_ee_pose_gripper_torso`、`state_d435`、`recomputed_ee_valid`、`state_torso`、`waist_state_joint` 都在数据集里、评测 API 不暴露 → 仍是「特权蒸馏」的免费监督。
- ⚠ **决定本轮优先级的硬证据（新增）**：
  - **MPVI（Georgia Tech, 2026）**：把「经典运动规划 + VLA」交错（interleaving），在 **BEHAVIOR-1K** 上相对最强端到端 VLA **任务进度 +109%**，且**无需额外训练**。论文明确点出：即便任务在演示分布内、数据再多也会失败——失败**不是数据不够**，而是长程执行误差累积。
  - **MoManipVLA（CVPR 2025）**：VLA 只生成 **EE 路点**，再用**双层运动规划**（基座 + 机械臂）优化轨迹可行性；真实世界 **+4.2% SR**，部署仅需约 50 次真机成本，靠的是「VLA 泛化 + 规划保证可行性」。
  - **Shielding（AAAI 2018）**：给出「审查者」的严格形式化——挂在决策器之后，对**违反时序逻辑规范的动作**才纠正（correct only if violation），并讨论保持收敛性的条件。这正是「伦理审查」的技术同构。

一个反直觉但更值钱的判断：

> **上一轮的 REVIEW-GATE 只会「裁剪到安全包络」（clip），这不是修复，是阉割——clip 后的轨迹往往仍不可达、仍碰撞，只是把失败藏起来。而「路径规划」是让它变成真修复的唯一引擎：给一个目标，规划器能在碰撞约束下造出一条**可行**轨迹。更妙的是，规划器同时是**泛化杠杆**：把 VLA 的输出从「关节轨迹」改成「子目标」，OOD 位姿就不再需要记忆，而变成一个可求解的规划问题（MPVI / MoManipVLA 已证）。**

一句话押注：

> **把 REVIEW-GATE 升级为 PLAN-GATE：VLA（含 3D-ANCHOR）只负责提出「子目标」；一个轻量关节空间运动规划器负责把子目标变成可行、平滑、碰撞自由的执行轨迹（reproject / replan / recover）；伦理审查负责在**不可逆动作前**要求规划器给出一张「可逆性恢复证书」，并把每一步审查留痕，作为泛化五轴的**数据飞轮燃料**与 §6 可信度证据。**

## 1. 为什么「路径规划」是「泛化能力」的正解，而不是又一个补丁

竞赛的口号就是「真实世界泛化性不足」，五轴 = 位置 / 干扰物 / 背景 / 未见物品 / 人为干扰。这五轴里，真正几何/动力学硬的是四条；而端到端 VLA 的失效模式（MPVI 已实证）不是「没见过」，而是：

```text
F1 长程误差累积：块与块之间即使每步误差很小，几十步后偏离可行域 → 碰撞/漏抓。
F2 位姿泛化脆弱：训练分布内的新位置也会失败（数据再多也不解决）。
F3 不可行动作：VLA 输出的是「像演示」的关节序列，不是「物理可行」的轨迹
   （自碰撞、桌面穿透、超速、双臂互撞）。
F4 人为干扰：人进入工作空间后，VLA 没有「让行」这一动作类别。
F5 §6 可信度：抖动、突跳、块边界不连续 → 被判为「动作异常」。
```

**路径规划同时命中 F1–F5**：

- 对 F2/F3/F4：把输出接口从「关节块」降维为「子目标（SE(3) 抓取/放置位姿 + 少量关键点约束）」。语义泛化交给 VLA，运动实现交给规划器——**泛化不再靠记忆，而靠可求解性**。
  - 这正是 **ReKep** 的思路：用「关系关键点约束」表达任务，再用现成求解器实时优化出 EE 轨迹；VLM 负责从语言 + RGB-D 生成约束，无需任务专用数据。
  - 也是 **MoManipVLA** 的思路：VLA 出 waypoint、运动规划保可行性；/ 以及 **VoxPoser**：VLM 组合 3D value map，再用 model-based planning 合成闭环轨迹。
- 对 F1：规划器在**每个块边界**把当前真实状态接上目标，误差**不跨块累积**（MPVI 的 core claim）。
- 对 F5：规划输出天然平滑（shortcut + 时间参数化），直接提升 §6 的「统计规律性」，且**不改变接口**（仍返回 `(T_a,·)` 关节块）。

一句话：**规划器是「审查门的引擎」，也是「泛化的减维器」，还是「§6 的平滑器」——一份投入，三处收益，且全是经典算法、无需额外数据、可离线在 LIBERO 里验证。**

## 2. 研究日志：本轮的事实再基线化与「修剪」

### 2.1 对第 23 轮三柱的诚实修剪（PLAN-GATE 纪律的第一次应用）

```text
KEEP（主线不动的脊柱）：
  - MVP-SPINE 三级门控：G0 接口冒烟 → G1 UnifoLM-VLA-0 微调出可提交基线 → G2 加杠杆。
  - 3D-ANCHOR：保留，但本轮从「G2a 首发」下调为「G2b」（原因：收益依赖未证实的双目
    基线/内参；而规划器不依赖任何未公开硬件事实）。
  - joint 控制空间优先、动作块 + 时序集成 + 子目标早停、多端口共享服务。
PROMOTE（本轮新证据带来的升格）：
  - 路径规划（MOTION-SHIELD）升为 G2a 首发：有 MPVI +109% / MoManipVLA +4.2% 的近邻
    证据、纯经典、无额外数据、离线可在 LIBERO 验证、且直接利好 §6。
DEMOTE（保留但降级/合并）：
  - REVIEW-GATE 原「clip 式修复」合并进 MOTION-SHIELD 的 reproject 步骤；
    原 T2 学习式 critic 继续只做「触发修复」，不独立成篇。
  - 事件触发块内闭环：仍为旁路，依赖「评测端是否每步回调」这一未证实前提。
MAJORIZE（本轮新定义）：
  - 子目标抽象接口（SUBGOAL）：泛化的减维器，替代「端到端关节块」的默认输出。
  - 可逆性证书（REVERSIBILITY CERT）：伦理审查从「安全」升到「可逆/知情」。
  - 泛化五轴账本 + 审查留痕数据飞轮（GEN-LEDGER）：让「泛化能力」可测量、可运营。
```

### 2.2 三个词如何咬合成一个新飞轮

```text
泛化能力（GEN-LEDGER）——定义与度量：五轴账本 + 子目标抽象
        │ 账本指出「哪条轴在漏分」；子目标接口把泛化从记忆搬到规划
        ▼
路径规划（MOTION-SHIELD）——执行引擎：reproject / replan / recover
        │ 保证每个子目标都有可行解；误差不跨块累积；动作平滑（§6）
        ▼
伦理审查（SHIELD + REVERSIBILITY）——把关：物理合法 / 可逆性 / 人体在场
        │ 审查留痕 → 标记 OOD 与「规划失败态」→ 回灌数据/增强/补毕业场景
        ▼
回到 GEN-LEDGER：漏分轴被定位 → 定向补数据/增强 → 下一轮泛化账本上升
```

三处「甜点」很具体：

1. **规划失败 = 泛化的探针**：规划器给出的是**确定性可行性**判据；某个子目标若规划失败，说明它几何上不可达/碰撞，而不是模型「不确定」。这比学习式 OOD 分数**更干净**，是账本的理想信号源。
2. **可逆性证书 = 伦理审查的可证明内核**：在 R2（不可逆）动作提交前，要求规划器在「当前场景 + 扰动集」下造出一条回到安全态的恢复路径；造不出就不许提交。这是把「知情同意 / 可撤销」落成算法。
3. **审查留痕 = §6 可信度产物 + 数据飞轮**：留痕同时是官方考核证据与下一轮定向补数据的清单。

## 3. 四个创新点的正式化（动机 / 差异 / 可行性 / 资源 / 步骤 / 风险）

### 3.1 SUBGOAL（子目标抽象接口）

```text
思想：VLA 不直接回归 T_a×d 的关节块，而是输出一个低维「子目标」：
      s* = { left/right 夹爪目标位姿 (SE(3))，可选的关键点约束 K（ReKep 式），
             夹爪开合，是否双臂协同 }。
      运动实现由 MOTION-SHIELD 规划。两种实现梯度：
      (a) 零重训版：把基座 VLA 的块「末位 waypoint」当作隐式子目标（A[-1] 的 EE 位姿）。
      (b) 训练版：在基座上挂一个 <5M 的子目标头，监督用数据集里的
          *_ee_pose_gripper_torso / 关键点（特权状态，评测端看不到）。
动机：F1/F2/F3 都源于「用轨迹记忆代替可求解性」；减维接口把语义与运动解耦。
差异：与纯端到端动作块相比，本方案显式承认「VLA 管 what、规划器管 how」；
      与纯 VLM+规划器（VoxPoser/ReKep）相比，本方案保留 VLA 作为数据驱动的子目标先验，
      因而能吃到 32k 演示的分布，而不是只靠零样本 VLM。
可行性：高。零重训版今天就能接；训练版只加小头。
资源：数据集特权状态（已有）+ 1 次小规模训练。
步骤：零重训接 plan → 离线比较「块末位 vs 全块」的可达率 → 再训子目标头。
风险：块末位在演示中可能有抖动/噪声；训练版需防止子目标头过拟合训练位姿。
```

### 3.2 MOTION-SHIELD（规划即审查引擎）

```text
输入：当前关节 q0（左右臂 14 维，waist 固定/锁）、子目标 s*、场景几何 S、
      扰动集 D（人体/干扰物可能出现的区域）
三档处理（由廉价到昂贵，逐级升级）：
  (P0) reproject（重投影）：把 VLA 关节块按「速度/加速度/加加速度限」时间参数化
       （time-optimal retiming）+ shortcut 平滑；若全程无碰撞 → 放行。解决 F5、F3(超速)。
  (P1) replan（重规划）：P0 失败或不可达 → 以 s* 为目标，在关节空间跑
       BiRRT-Connect（碰撞模型 = FK 胶囊连杆 ∪ 场景点云/桌面先验），
       再 shortcut + 时间参数化，重采样为 T_a。解决 F1、F2、F3(碰撞)。
  (P2) recover（恢复）：R2 不可逆动作提交前，规划一条「逆动作回到安全态」的路径；
       若在扰动集 D 下无恢复路径 → 不许提交（升级为安全保持，联机重询问）。
碰撞与可行性：胶囊体自碰撞 + 左右臂互撞 + 桌面/物体穿透 + 关节限位 + 工作空间包络。
输出：恰好一个 (T_a, d) 关节块 + 一份 (mode∈{P0,P1,P2,fallback}, 证书, margin)。
目标函数：min  代价 = w_t·轨迹时长 + w_j·加加速度积分(平滑) + w_s·到 s* 的距离
        s.t. 碰撞(轨迹, 场景) = ∅, 关节限位, 速度/加速度/加加速度限。
```

**动机**：这是 REVIEW-GATE 缺的引擎（对 F1–F5 全命中），也是唯一有强近邻证据（MPVI / MoManipVLA）、且不依赖未公开硬件事实的 G2 杠杆。
**与现有方案的差异**：不是「给动作乘一个保守系数」，而是**在可行域内重新求解**；不是「独立于 VLA 的新策略」，而是**夹在 VLA 与执行之间的门**，因此对任何基线都即插即用。
**可行性**：高（BiRRT-Connect / STOMP / TOP 全是成熟件；碰撞用胶囊近似足够）。
**资源**：CPU 规划器（可多核）+ FK/碰撞模型；无需训练、无需新数据。
**落地步骤**：G0 里先测单次规划时延 → 在 32k 演示上做「块末位可达率」离线统计 → 接进三档 → 在 LIBERO 回归 → 真机。
**风险**：规划时延撞 §6（必须**异步**：在执行上一块时预算下一块，规划未完成则退回 P0 fallback，绝不阻塞）；胶囊碰撞模型与真机有偏差；透明/反光物体的场景几何缺失（可退化为「桌面先验 + 检测框凸包」）。

### 3.3 ETHIC-SHIELD（伦理审查：物理合法 / 可逆性 / 人体在场）

```text
把「伦理」落成一个独立于生成器的审查者（Shielding 的形式化）：
  A. 物理合法性（零学习，可证明）：关节/速度/加速度/加加速度限、自碰撞、桌面穿透、
     工作空间包络 —— 直接复用 MOTION-SHIELD 的可行性判定。
  B. 可逆性审查（本轮新增，最有「伦理」味）：给每个原子动作标一个可逆性等级
     R0 完全可逆 / R1 有代价可逆 / R2 不可逆（断网口、拔线、倒药、开锁、推倒堆叠）。
     仅对 R2：要求 MOTION-SHIELD 出具「恢复证书」——存在一条在扰动集 D 下
     回到上一安全态的可行路径，且置信裕度 ≥ τ。否则允许的结论只有：
     安全保持 / 重新询问（重抽样）/ 降速靠近再复核。
  C. 人体在场：头部双目 3D 检测人/手 → 距离 d_human；d_human<d_slow 降速、
     d_human<d_stop 触发 P2 让行（规划退避路径），对「人为干扰」轴。
结论三态：PASS / REPAIR（由 MOTION-SHIELD 规划修复，而非 clip）/ HOLD（安全保持+重询问）。
留痕：trace_t = (decision, mode, reason_code, {margin_c}, recovery_cert, d_human)。
```

**动机**：伦理审查的诚实技术同构；同时命中「人为干扰」轴与易损/不可逆对象的财产完整性，并把 §6 可信度变成显式产物。
**与现有方案的差异**：上一轮是「风险缩放 + clip」；本轮是**可证明的可行性 + 可逆性证书 + 规划修复**；审查者不再只是否决者，而是**修复提案者**。
**可行性**：A 极高；B 高（规划器已在）；C 中（现成检测器 + 双目 3D）。
**资源**：动作可逆性标注（32 任务，人工 1 天）；规划器；检测器。
**落地步骤**：先 A → 演示上测误杀率（应≈0）→ B（只对 R2）→ C 让行回归。
**风险**：R2 判定错误会误伤成功；恢复证书在杂乱场景可能造不出→过度 HOLD；人体检测延迟。

### 3.4 GEN-LEDGER（泛化五轴账本 + 审查留痕数据飞轮）

```text
账本：对 5 轴分别建「留出评测协议」并各记一列：
  位置 | 干扰物 | 背景 | 未见物品 | 人为干扰
  每列记：SR、步骤分、规划失败率(P1/P2)、PASS/REPAIR/HOLD 比例、恢复证书成功率。
训练侧：轴定向增强 —— 位置轴做目标位姿/物体位姿抖动；干扰物轴在场景点云里
        注入虚拟障碍；背景轴做表观替换；未见物品轴用检测框凸包做陌生几何。
推理侧：对 OOD 子目标做「最近演示检索」给出候选备选位姿，规划器选可行者。
飞轮：规划失败(P1/P2) 与 HOLD 的留痕 → 汇总成「补数据清单」→ 定向增强/补采 →
      下一轮账本复测。
```

**动机**：竞赛就是评泛化；没有账本，所有改进都是盲调。
**与现有方案的差异**：把「泛化」从口号变成**分轴、可归因、可与规划失败挂钩**的量表；审查留痕同时是数据飞轮的入口。
**可行性**：高（离线即可做；LIBERO 可做部分代理）。
**资源**：评估脚本 + 增强管线 + 少量标注。
**落地步骤**：先建 5 轴留出协议 → 记 G1 基线 → 逐轴归因 → 定向增强 → 复测。
**风险**：离线账本与真机分布有差距；增强可能引入伪相关。

## 4. 持续迭代的创新点清单（本轮修订）

> 🟢 保留推进　🔵 新增　🟡 降级/旁路　🔴 剪枝　⬆️ 升格

| # | 创新点 | 状态 | 动机 | 与现有方案差异 | 可行性 | 所需资源 | 落地步骤 | 风险 |
|---|---|---|---|---|---|---|---|---|
| 1 | MVP-SPINE（门控交付脊柱） | 🟢 | 先上桌 | 每级可提交 checkpoint | 极高 | 基座+32k+1–8 GPU | G0→G1→G2 | 转码/算力 |
| 2 | **MOTION-SHIELD（规划即审查引擎）** | 🔵⬆️ | F1–F5 全命中，近邻 +109% | 在可行域重求解，非 clip | 高 | CPU 规划器+FK/碰撞 | P0 reproject→P1 replan→P2 recover | 时延/碰撞模型偏差 |
| 3 | **SUBGOAL（子目标抽象接口）** | 🔵 | 泛化减维：what 与 how 解耦 | VLA 出子目标而非轨迹 | 高 | 特权状态+小头 | 零重训块末位→训练头 | 末位噪声 |
| 4 | **GEN-LEDGER（五轴账本+数据飞轮）** | 🔵 | 让泛化可测量可运营 | 分轴归因 + 规划失败探针 | 高 | 评估脚本+增强 | 协议→基线→归因→增强→复测 | 离线-真机 gap |
| 5 | **ETHIC-SHIELD（可逆性审查+留痕）** | 🔵（由 REVIEW-GATE 升级） | 伦理同构/人机安全/§6 | 可行性+可逆性证书+规划修复 | 中高 | 可逆性标注+检测器 | A→B(R2)→C 让行 | R2 误判/HOLD 过度 |
| 6 | 3D-ANCHOR（矫正双目→点云+特权蒸馏） | ⬇️🟢 | 几何泛化 | 首次兑现 rectified stereo | 高 | 立体/深度网+标定 | 视差校验→编码→蒸馏 | 反光/透明/降参 |
| 7 | joint 空间优先 + 动作块 + 时序集成 + 子目标早停 | 🟢 | 稳定与步骤分 | 成熟基线 | 极高 | 无 | 接入→回归 | 集成滞后 |
| 8 | 多端口共享服务 + 状态隔离 + 异步规划预算 | 🟢 | 接口前提+§6 | 规划异步化保 p95 | 高 | 部署环境 | 连续批处理+优先级 | 并发串扰 |
| 9 | 事件触发块内闭环 | 🟡 | 理论收益大 | 依赖每步回调前提 | 中 | — | 先验证接口语义 | 前提未证实 |
| 10 | 双臂协同流形 + 互预测 | 🟡 | 双臂任务 | 与规划器 P0/P1 部分重叠 | 中高 | 双臂子集 | 排在规划之后 | 约束过紧 |
| 11 | 学习式 p_fail / OOD critic | 🟡 | 触发修复 | 并入 ETHIC-SHIELD，规划失败优先 | 中 | 自监督标签 | 与审查合并 | 标签噪声 |
| 12 | 力/触觉 / 声纹 / 云端级联 | 🔴 | — | 无通道/耗步/坏时延 | 不可行 | — | 删除 | — |

## 5. 风险与未证实前提（只列决定路线者）

| 风险/未知 | 为什么关键 | 何时解决 | 缓解 |
|---|---|---|---|
| **评测端「每步回调」还是「整块执行」** | 决定块边界能否重规划/让行 | G0 | 自写 client 逆向；双模式兼容 |
| **规划时延 vs §6** | 规划重了会拖垮 p95/抖动 | G0 起 | 异步预算（执行中算下一块）+ P0 fallback，绝不阻塞 |
| **碰撞模型与真机偏差** | 直接影响修复是否真安全 | G2a | 保守胶囊膨胀 + 桌面先验 + 真机小样本校准 |
| **子目标（块末位）噪声** | 训练分布内末位可能抖 | G2a | 中值滤波 + 最近演示检索 + 规划器容差 |
| **双目基线/内参不可得** | 3D-ANCHOR 需自标定 | G2b | 自标定 + E2 判据；否则降级为多视 2D |
| **步骤分口径未公开（飞书正文不可机读）** | 决定早停/省步是否划算 | 尽早 | 保守优化「子目标完成 + 少无效步」；人工查阅飞书 |
| **数据 v3.0 vs 基座期望 v2.1** | 卡 G1 | G1 前 | 写转码层（lerobot→hdf5→RLDS）或原生 v3 加载器 |

## 6. 本轮最大的风险

**规划器把「动作分布」改变了。** §6 明确把「返回动作的统计规律性」当可信度依据；规划器输出的轨迹可能**比 VLA 更平滑但更「不像演示」**（例如大幅绕行）。需要证明：规划后轨迹的统计量（步长、连续块边界差、加加速度）**落在演示分布的合理范围内**，否则可能被判异常。缓解：在 P0 reproject 里尽量贴近 VLA 原块（最小改动原则，与 Shielding 的「仅在违反时纠正」一致）；规划轨迹做分布对齐（限幅到演示的步长/加加速度分位）。**这把「伦理审查」的正确姿势钉死为：能不动就不动，只在越界/不可逆/人体在场时才接管。**

## 7. 参考来源（检索日期 2026-11-05）

- 提交模板与接口规范（观测/动作目录、metadata、N 端口、§6）：https://github.com/unitreerobotics/unibot_submission
- 挑战赛任务集（32 任务 / 32000 episodes / 169h）与参赛方式：https://unibot.unitree.com/challenges.html
- 首页（榜单「Coming Soon」、按平均成功率与步骤分排序）：https://unibot.unitree.com/
- 排行榜（Coming Soon）：https://unibot.unitree.com/leaderboard.html
- 运行记录（Coming Soon）：https://unibot.unitree.com/runs.html
- 参赛规则（飞书，本轮抓到页面壳、正文 JS 渲染/需登录，未机读）：https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh
- 数据集（LeRobot v3.0、4 相机、**head_stereo rectified**、特权状态、Dex1 5.5–0.0）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- 挑战数据集集合（32 个 G1_Dex1_*）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- UnifoLM-VLA-0（Apache-2.0、单策略 12 类、LeRobot v2.1→HDF5→RLDS、LIBERO 评测脚本）：https://github.com/unitreerobotics/unifolm-vla
- UnifoLM-WMA-0 / UnifoLM 集合：https://huggingface.co/collections/unitreerobotics/unifolm-wma-0
- MPVI：Make Your VLA More Robust Without More Data By Interleaving Motion Planning（Georgia Tech, 2026；BEHAVIOR-1K 进度 +109%）：https://robotdangerlab.me.gatech.edu/projects/vla-motion-planning/
- MoManipVLA（CVPR 2025，VLA waypoint + 双层运动规划，真机 +4.2% SR，arXiv:2503.13446）：https://arxiv.org/abs/2503.13446
- VoxPoser（VLM 组合 3D value map + model-based planning，arXiv:2307.05973）：https://arxiv.org/abs/2307.05973
- ReKep（关系关键点约束 + 分层优化出 EE 轨迹，arXiv:2409.01652）：https://arxiv.org/abs/2409.01652
- Safe RL via Shielding（审查者的形式化，AAAI 2018，arXiv:1708.08611）：https://arxiv.org/abs/1708.08611
- Unitree G1 真机操作聚合榜（LingBot-VA 66.7；Flash-WAM 60/50）：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world
- 3D-aware VLA 参照：PointVLA https://arxiv.org/abs/2503.07511 ；BridgeVLA https://bridgevla.github.io/home_page.html ；OG-VLA https://og-vla.github.io/

> 本轮一句话押注：**最值得押注的是创新点 2（MOTION-SHIELD 路径规划引擎）——它有 MPVI（+109%）/ MoManipVLA（+4.2%）的强近邻证据、纯经典、无需新数据、可用现成 LIBERO 离线验证，并且一份投入同时解决长程累积、位姿泛化、不可行动作、人为干扰与 §6 平滑；它也是让创新点 5（伦理审查）从「否决者」变成「修复者」的前提。3D-ANCHOR 顺延为第二杠杆。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 24 轮产物 · PLAN-GATE 技术报告：子目标抽象 + 规划即审查引擎 + 可逆性伦理审查 + 泛化五轴账本

> 检索日期：2026-11-05。本文是 M3S（第 23 轮）的演进版：保留「门控交付脊柱」，把 REVIEW-GATE 的「clip」替换为真正的**运动规划引擎**，并新增**子目标抽象**、**可逆性证书**与**泛化账本**。所有数值目标标注为「设计目标」；未见实测的结论均以接口硬约束与 §10 公开来源为界。

## 0. 结论

不新造大框架。PLAN-GATE = 一条门控交付脊柱 + 一个夹在 VLA 与执行之间的**规划门** + 一套把泛化做成账本的评测/数据闭环：

1. **MVP-SPINE（保留）**：G0 接口冒烟 → G1 UnifoLM-VLA-0 微调出可提交基线 → G2 加杠杆。
2. **SUBGOAL（新增）**：VLA 输出低维子目标（SE(3) 抓取/放置位姿 + 关键点约束 + 夹爪 + 是否双臂），运动实现交给规划器。零重训版用「块末位 waypoint」即可上线。
3. **MOTION-SHIELD（新增，G2a 首发）**：三档规划——P0 reproject（时间参数化+shortcut）/ P1 replan（BiRRT-Connect 到子目标）/ P2 recover（可逆性恢复路径）。
4. **ETHIC-SHIELD（升级 REVIEW-GATE）**：物理合法（可证明）+ 可逆性审查（R2 需恢复证书）+ 人体在场（双目 3D 让行）；结论三态 PASS / REPAIR / HOLD；全程留痕。
5. **GEN-LEDGER（新增）**：泛化五轴分账 + 以「规划失败率 / HOLD 率」为探针的数据飞轮。

对齐硬约束：观测仅 4×RGB + 关节/EE(base)/夹爪/下半身 + 语言；动作 joint 或 ee 互斥、块式 `(T_a,·)`；N 连续端口；§6 考核延迟/抖动与动作规律性（来源见 §10）。

## 1. 接口复核与模态映射

### 1.1 提交接口（本轮从官方 README 逐条复核）

| 项 | 官方规范（复核） | PLAN-GATE 遵守 |
|---|---|---|
| `metadata` | `control_space` / `obs_delta_indices`（选通道+堆叠）/ `image_resize` / `action_chunk_size` / `token` | 固定；规划/审查不改接口 |
| `obs_delta_indices` | 键决定**发哪些通道**，值是**帧偏移列表**（旧→新，须严格递增、≤0） | 只声明必要通道 |
| `image_resize` | 评测端 `cv2.resize(frame,(w,h))` 预缩后再发 | 双目保留较高分辨率以护后续 3D |
| `get_action` | 返回 `(T_a,·)`，**index 0 先执行**，块边界才再次回调 | 规划输出重采样为恰好 `T_a` 帧 |
| 端口 | N 端口 8765..8765+N−1，状态隔离、并发不互阻 | 异步规划预算 + 每端口隔离 |
| §6 | 记录每步时延与波动、动作统计规律性 | 计划：异步规划 + 最小改动 + 分布对齐 |

### 1.2 数据模态 vs 评测模态（特权信息复核）

| 数据集键 | 评测 API | PLAN-GATE 用法 |
|---|---|---|
| `head_stereo_left/right`（**rectified**） | 是（`cam_left_high/right_high`） | 3D-ANCHOR 立体 → 场景几何 |
| `wrist_left/right` | 是 | 腕相深度 + 尺度锚 |
| `left/right_arm`、gripper、`lower_body` | 是 | 本体 + FK |
| `*_ee_pose_gripper_base` | 是 | 状态/动作 |
| `*_ee_pose_gripper_torso`、`state_d435`、`state_torso`、`recomputed_ee_valid` | **否** | 特权 teacher（子目标头/3D 蒸馏） |
| `base_command`、`action_torso`、`pivot`、`gripper_controls` | **否** | 训练辅助监督 |

> 结论不变：**训练可多看，推理只用 API 模态**。

## 2. 门控交付计划（本轮修订）

```text
G0（接口冒烟，1–3 天）
  1. 跑通 example server/client；自写 client 验证「每步回调 vs 整块执行」、N 端口行为。
  2. 记录单次 get_action 时延 p50/p95/抖动，作为 §6 参照线。
  3. 新增：测「单次 BiRRT-Connect 从 q0 到块末位的时延与成功率」（决定 P1 是否可达实时）。
  Go：官方 example 无 ACTION REJECTED；规划时延预算表成形。

G1（能上榜的基线，1–2 周）
  1. 数据：32×G1_Dex1_*（LeRobot v3.0）→（转码）HDF5 → RLDS。
  2. 基座：UnifoLM-VLA-0（Apache-2.0；base=UnifoLM-VLM-Base）。
  3. joint 空间 + 动作块 + 时序集成 + 子目标/夹爪早停。
  Go：离线回归不低于未微调基座；延迟达标。

G2a（规划门，1–2 周；本轮首发）—— 产出：带 MOTION-SHIELD 的策略
  P0 reproject → P1 replan → P2 recover；先离线统计「块末位可达率」，再接入。
G2b（3D-ANCHOR，1–2 周）—— 为规划提供场景几何与人体 3D。
G2c（SUBGOAL 头 + GEN-LEDGER，1–2 周）—— 子目标训练版 + 五轴账本日报。
硬规则：任何新想法先证明「能让某关卡变绿」，否则进旁路清单。
```

> **为什么把规划排在 3D 前面（本轮关键调度判断）**：规划不依赖任何未公开的硬件事实（双目基线/内参是否可得），且已有强近邻证据（MPVI +109% / MoManipVLA +4.2%）与现成 LIBERO 离线验证栈；3D-ANCHOR 仍受制于「双目是否可用于度量重建」这一未证实前提。**先用确定性杠杆换分，再赌几何红利。**

## 3. SUBGOAL：子目标抽象接口

```text
两种实现梯度（先零重训、再训练）：
  (a) 零重训：s* := EE 位姿(A[-1], 由 q 经 FK 得到)  ← 把基座块的末位当隐式子目标
  (b) 训练版：s* := Head(h_VLA, proprio)  ← <5M 小头，监督用特权状态
      监督：left/right_ee_pose_gripper_torso（评测端拿不到）+ 关键点检测
表示：s* = { p_L, p_R ∈ SE(3), g_L, g_R ∈ [0,1], k ∈ R^{K×3}(可选关键点), bimanual∈{0,1} }
```

```python
import numpy as np


def subgoal_from_chunk(chunk, fk, mode="terminal"):
    """零重训子目标：取关节块的末位 waypoint 的 EE 位姿。"""
    q_T = chunk[-1, :14]
    p_L, p_R = fk.left_ee(q_T[:7]), fk.right_ee(q_T[7:14])
    g_L, g_R = chunk[-1, 14], chunk[-1, 15]
    return {"p_L": p_L, "p_R": p_R, "g_L": g_L, "g_R": g_R,
            "bimanual": float((np.linalg.norm(p_L - p_R) < 0.35))}
```

**泛化论证**：子目标空间维数远低于关节轨迹空间，且语义（往哪抓/放）比运动（怎么绕）更跨位姿稳定；运动不确定性由规划器在**每个块边界**重新消解，故误差不跨块累积。

## 4. MOTION-SHIELD：规划即审查引擎（核心）

### 4.1 三档处理与目标函数

```text
输入：q0（14 维双臂，waist 锁）、s*、场景几何 S、扰动集 D、VLA 原块 A
(P0) reproject：对 A 做 time-optimal retiming + shortcut，检查无碰撞 → 放行
(P1) replan  ：以 s* 为目标跑 BiRRT-Connect → shortcut → 时间参数化 → 重采样 T_a
(P2) recover ：为 R2 动作规划「逆动作回到安全态」的路径（扰动集 D 下）
目标：min  w_t·T(轨迹) + w_j·∫|d³q/dt³|² + w_s·d(轨迹末端, s*)
 s.t. 胶囊自碰撞=∅、臂-臂=∅、桌面/物体穿透=∅、关节限位、v/a/jerk 限、轨迹⊂工作空间
```

### 4.2 可运行骨架

```python
import numpy as np


class MotionShield:
    def __init__(self, fk, collision, q_min, q_max, v_max, a_max, j_max,
                 ta=8, dt=1 / 30.0, dev_max=0.15, tau_cert=0.6):
        self.fk, self.coll, self.q_min, self.q_max = fk, collision, q_min, q_max
        self.v_max, self.a_max, self.j_max = v_max, a_max, j_max
        self.ta, self.dt = ta, dt
        self.dev_max = dev_max          # 允许偏离 VLA 原块的最大步长（最小改动原则）
        self.tau_cert = tau_cert        # 恢复证书裕度

    def feasible(self, Q, S):
        if (Q < self.q_min).any() or (Q > self.q_max).any():
            return False
        for t in range(1, len(Q)):
            v = (Q[t] - Q[t - 1]) / self.dt
            if (np.abs(v) > self.v_max).any():
                return False
        for q in Q:
            if not self.coll.clear(self.fk.capsules(q), S):   # 自碰撞 + 臂臂 + 场景
                return False
        return True

    def reproject(self, A, q0, S):
        Q = np.vstack([q0, A[:, :14]])                     # P0：以原块为参照
        Q = self.retime(Q)                                 # 满足 v/a/jerk（TOP）
        Q = self.shortcut(Q, S)                            # 无碰撞捷径平滑
        Q = self.limit_deviation(Q, A)                     # 最小改动：贴回原块
        return Q

    def replan(self, s_star, q0, S):
        goal = self.fk.ik(s_star)                          # 子目标 → 关节目标
        if goal is None or not self.coll.clear(self.fk.capsules(goal), S):
            return None                                    # 子目标本身不可达/碰撞
        Q = self.birrt_connect(q0, goal, S)                # P1
        if Q is None:
            return None
        Q = self.shortcut(self.retime(Q), S)
        return self.resample(Q, self.ta)

    def recover(self, q_now, q_safe, S, D):
        """P2：在扰动集 D 下，是否存在回到安全态的可行路径 → 恢复证书。"""
        for obstacle in D.samples():
            Q = self.birrt_connect(q_now, q_safe, S.union(obstacle))
            if Q is None or not self.feasible(Q, S.union(obstacle)):
                return None
        return {"to": q_safe, "margin": self.min_clearance(q_now, S)}  # 证书

    def gate(self, A, s_star, q0, S, reversibility, human_d, D):
        # 最小改动优先（Shielding：仅在违反时纠正）
        if human_d < self.dev_max and not self.would_collide(A, S):
            pass                                           # 人体近？交给上层 HOLD
        Q = self.reproject(A, q0, S)
        if self.feasible(Q, S) and self.max_dev(Q, A) <= self.dev_max:
            return self.pack(Q, A), {"mode": "P0"}
        Q = self.replan(s_star, q0, S)
        if Q is not None:
            cert = None
            if reversibility == "R2":
                cert = self.recover(Q[-1], q0, S, D)
                if cert is None:
                    return self.hold(q0), {"mode": "HOLD", "reason": "no_recovery_cert"}
            return self.pack(Q, A), {"mode": "P1", "recovery_cert": cert}
        return self.hold(q0), {"mode": "HOLD", "reason": "no_plan"}

    # --- 以下为占位，工程实现用现成库 ---
    def retime(self, Q): return Q
    def shortcut(self, Q, S): return Q
    def limit_deviation(self, Q, A): return Q
    def resample(self, Q, n): return Q[:n]
    def birrt_connect(self, q0, goal, S): return np.vstack([q0, goal])
    def min_clearance(self, q, S): return 0.05
    def max_dev(self, Q, A): return 0.0
    def would_collide(self, A, S): return False
    def pack(self, Q, A):
        out = A.copy()
        out[:, :14] = Q                                          # 只改双臂关节，其余沿用
        return out
    def hold(self, q0):
        return np.tile(np.concatenate([q0, [0, 0], np.zeros(1)]), (self.ta, 1))
```

### 4.3 时延预算（保护 §6 的硬约束）

```text
关键：规划绝不阻塞 get_action。
  1. get_action(t) 立即返回「已预算好的」块；
  2. 在机器人执行该块的 T_a·dt 期间，异步为 t+1 规划下一个块；
  3. 规划未在 deadline 前完成 → 退回 P0/上一块的时间外推（fallback），
     并记录 mode=fallback 供账本统计。
预算目标（设计）：单块 P1 规划 ≤ T_a·dt（≈0.27s @T_a=8,30fps）的 80%；否则降用 P0。
```

## 5. ETHIC-SHIELD：可逆性伦理审查

### 5.1 三层与可逆性等级

```text
A 物理合法（零学习，可证明）：直接复用 MOTION-SHIELD.feasible（限位/速度/加速度/加加速度/
  自碰撞/臂臂/桌面/工作空间）。
B 可逆性审查（伦理内核）：原子动作等级
    R0 完全可逆（自由空间移动、开合夹爪）
    R1 有代价可逆（抓取/放置；掉落后可重试）
    R2 不可逆（断网口、拔线缆、倒药、开锁、推倒堆叠、液体倾洒）
  仅对 R2：要求 MotionShield.recover 出具恢复证书（存在回安全态的可行路径，
  且在扰动集 D 下 margin ≥ τ_cert）。无证书 → 只允许 {安全保持 / 重抽样 / 降速靠近再复核}。
C 人体在场：头部双目 3D 检测人/手 → d_human；<d_slow 降速、<d_stop 触发 P2 让行。
结论：PASS / REPAIR（规划修复）/ HOLD（安全保持+重询问）。
留痕：trace_t=(decision, mode, reason_code, {margin}, recovery_cert, d_human, latency)。
```

**与上一轮 REVIEW-GATE 的关键差异**：REPAIR 从「clip 到包络」（可能造出不可达轨迹）变为「规划出可行轨迹」；VETO 从「凭学习式 critic 否决」变为「凭确定性可行性 + 可逆性证书 HOLD」，误杀风险大幅下降。

## 6. GEN-LEDGER：泛化五轴账本 + 数据飞轮

```text
五轴留出协议（离线可做，LIBERO 可做部分代理）：
  位置 | 干扰物 | 背景 | 未见物品 | 人为干扰
每轴指标：
  SR、步骤分代理（子目标完成步数）、P1/P2 规划失败率、PASS/REPAIR/HOLD 比例、
  恢复证书成功率、块边界不连续度（§6 代理）。
训练侧轴定向增强：
  位置轴→目标/物体位姿抖动；干扰物轴→点云注入虚拟障碍；背景轴→表观替换；
  未见物品轴→检测框凸包当陌生几何；人为干扰轴→仿真里注入移动人手。
推理侧：OOD 子目标 → 最近演示检索出候选位姿集 → 规划器选可行者（bounded fallback）。
飞轮：规划失败/HOLD 留痕 → 补数据清单 → 定向增强 → 下一轮账本复测。
```

## 7. 实验协议

### 7.1 第一优先（决定路线）

| 实验 | 做法 | 判据 |
|---|---|---|
| E1 接口语义 | 自写 client 模拟每步回调 vs 整块执行 | 确定规划/让行粒度 |
| E2 双目可信度（承上轮） | 桌面平面单应 + 已知物尺寸 + EE 交叉校验 | 决定 3D 是强/弱杠杆 |
| **E3 规划时延/可达（本轮新增）** | 32k 演示上统计「q0→块末位」BiRRT 成功率与 p95 时延 | 决定 P1 是否实时可用 |
| **E4 子目标 vs 全块（本轮新增）** | 同一基座，块输出 vs 子目标+规划，比较五轴 SR | 「减维接口」是否提升泛化 |

### 7.2 消融网格与指标

```text
消融：{纯基座开环, +P0, +P1, +P2, +子目标(零重训), +子目标(训练头),
       +3D-ANCHOR, +ETHIC-SHIELD B/C} × {joint, ee}
指标：留出动作误差(MSE/DTW)、五轴 SR、步骤分代理、规划失败率、恢复证书成功率、
      误杀率（应≈0）、p50/p95 时延与抖动、块边界不连续度、加加速度分位。
```

### 7.3 预期结果（设计目标，非声称）

| 模块 | 目标 |
|---|---|
| G1 基线 | 留出动作误差优于未微调基座（相对 −20% 量级） |
| P0 reproject | 块边界不连续度与加加速度下降（§6 受益），误改率低 |
| P1 replan | 长程/新位置任务 SR 相对纯端到端提升（对齐 MPVI/ MoManipVLA 方向） |
| SUBGOAL | 位置/未见物品轴 SR 提升（泛化减维） |
| ETHIC-SHIELD | 演示误杀率 ≈0；R2 动作零事故 |
| 多端口 | p95 延迟与抖动不劣于单端口；异步规划不阻塞 |

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 规划时延撞 §6 | 异步预算 + deadline fallback + P0 优先；p95 SLO |
| 规划改变动作分布 | 最小改动原则（Shielding 式仅在违反时纠正）+ 分布对齐限幅 |
| 碰撞模型与真机偏差 | 保守胶囊膨胀 + 桌面先验 + 真机小样本校准 |
| 块末位子目标噪声 | 中值滤波 + 最近演示检索 + 规划器容差 |
| 透明/反光物几何缺失 | 检测框凸包兜底；3D 置信低则退 2D 先验 |
| R2 误判 / HOLD 过度 | 可逆性人工审核（32 任务 1 天）+ 只对 R2 用证书 |
| 数据 v3.0→v2.1/RLDS 转码 | 复用仓库 prepare_data 脚本改适配；或原生 v3 加载器 |
| 训练算力 | LoRA/部分解冻先验证，分级 checkpoint |

## 9. 时间线（建议，随关卡 Go/Kill 调整）

```text
D1–D3   ：G0 接口冒烟 + E1 接口语义 + E3 规划时延/可达
D4–D7   ：数据转码；P0/P1 规划器接入（离线在演示/LIBERO 回归）
D8–D14  ：G1 基线微调 + 时序集成 + 早停 → 第一个可提交 checkpoint
D14–D18 ：G2a MOTION-SHIELD 三档 + E4 子目标对比 + 五轴账本首测
D18–D24 ：G2b 3D-ANCHOR（先 E2 验证双目）+ 场景几何
D24–D30 ：G2c SUBGOAL 训练头 + ETHIC-SHIELD B/C + 多端口压测
D30+    ：预约评测；按账本分轴复盘，回到「让关卡变绿」的循环
```

## 10. 参考来源（检索日期 2026-11-05）

- 提交模板与接口规范：https://github.com/unitreerobotics/unibot_submission
- 挑战赛任务集与参赛方式：https://unibot.unitree.com/challenges.html
- 首页 / 排行榜 / 运行记录（榜单 Coming Soon）：https://unibot.unitree.com/ ；https://unibot.unitree.com/leaderboard.html ；https://unibot.unitree.com/runs.html
- 参赛规则（飞书，正文 JS 渲染/需登录，未机读）：https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh
- 数据集（LeRobot v3.0、stereo rectified、特权状态、Dex1 5.5–0.0）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- 挑战数据集集合：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- UnifoLM-VLA-0（训练/推理/权重、V2.1→HDF5→RLDS、LIBERO 评测）：https://github.com/unitreerobotics/unifolm-vla
- MPVI：Interleaving Motion Planning with VLA（Georgia Tech 2026，BEHAVIOR-1K 进度 +109%）：https://robotdangerlab.me.gatech.edu/projects/vla-motion-planning/
- MoManipVLA（CVPR 2025，waypoint + 双层运动规划，arXiv:2503.13446）：https://arxiv.org/abs/2503.13446
- VoxPoser（arXiv:2307.05973）：https://arxiv.org/abs/2307.05973
- ReKep（arXiv:2409.01652）：https://arxiv.org/abs/2409.01652
- Safe RL via Shielding（arXiv:1708.08611）：https://arxiv.org/abs/1708.08611
- Unitree G1 真机操作聚合榜：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world
- PointVLA https://arxiv.org/abs/2503.07511 ；BridgeVLA https://bridgevla.github.io/home_page.html ；OG-VLA https://og-vla.github.io/

> 本轮产物一句话：**PLAN-GATE = 「VLA 提子目标 + 运动规划保证可行执行 + 可逆性证书守住不可逆动作 + 五轴账本运营泛化」；上一轮的 REVIEW-GATE 缺的正是这个规划引擎。**
<!-- ARTIFACT:END -->