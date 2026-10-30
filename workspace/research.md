# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 12 轮 · CHUNK-SERVO：把 30 步开环 chunk 改成「30 步规划 + 5 步视觉伺服」，用演示检索和虚实标定补上最后 3 厘米

> 检索/复核日期：**2026-10-28（UTC）**。赛事身份不变：宇树 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API。本轮是灵感循环第 2 轮，三个词是「虚实迁移」「视觉伺服」「竞赛策略」。本轮不推倒第 10 轮 FACT-VLA 和第 11 轮 GEO-RESIDUAL，而是把它们从「观测/标注层」推进到「控制层」：**VLA 负责 30 步规划，确定性视觉伺服负责每 5 步的闭环修正，数字孪生只负责标定延迟与增益，竞赛策略负责把 320 trials 投到最可能涨分的任务上。**

## 0. 先给结论：榜首不到 30%，缺的不是更大的模型，而是最后 3 厘米的闭环

截至 2026-10-28，官网首页/榜单显示：MolmoAct2 29.7%、WALL-OSS-0.5 28.5%、DreamZero 27.9%、Spirit-v1.5 25.9%、DM0 23.5%、π0.5 22.8%、GigaBrain-0 22.6%、GR00T N1.5 20.5%。头尾只差 9.2pp，说明这不是“某个架构领先”，而是**所有模型共享同一个执行瓶颈**。

我的判断是：这个共享瓶颈不是语义理解，也不是 3D 感知，而是——

1. **VLA 以 1 秒开环 chunk 执行**。官方 UnifoLM-WLA-1.0 的 action horizon 是 **30 步 @ 30Hz**，正好覆盖 `[0, 29/30]` 秒；挑战赛 API 的 `action_chunk_size` 又是固定值，evaluator 按 chunk 顺序执行，chunk 内不重新看世界。接触、插入、挂杯、拉拉链、拧瓶盖、开锁，恰恰发生在最后 3 厘米、最后 0.3 秒。
2. **远程 API 的 RTT 把反馈延迟放大**。选手自部署、官方远程调用；RTT 可能是 10ms，也可能是 150ms。chunk 越长越稳，但越不反应；chunk 越短越反应，但越容易被网络抖动打断。**chunk size 不是推理参数，是控制参数。**
3. **单模型规则堵死了“再加一个学习模型”的捷径**。不能为每个任务训一个残差策略；但可以加一个**无学习权重的确定性视觉伺服控制器**——它不是第二个模型，而是控制器。

所以本轮的押注是 **CHUNK-SERVO**：

> 用官方 WLA/VLA 做 30 步语义规划；把 30 步切成 6 个 5 步的执行块；每个执行块用腕部/头部视觉做一次闭环修正；修正的目标不是绝对图像，而是从 33k 条成功演示里检索出的「目标-夹爪相对位姿 + 目标图」；数字孪生只用来标定相机外参、伺服增益和 RTT，不用来训练大模型。

一句话：**把“预测 1 秒的动作”改成“预测 1 秒的意图，执行 167 毫秒的闭环块”（含 RTT 端到端约 200–320ms）。**

三个可验证创新点（不是三个宏大名目）：

1. **双频 chunk**：VLA 30 步规划 + 伺服 5 步执行；用 G2/G7 验证 5 步是否真的优于 30 步，以及增益/RTT 稳定域。
2. **DG-KEYFRAME**：从 33k 成功演示检索“受器→夹爪”相对位姿/腕部目标图；用 G1/G3 验证相对目标是否优于绝对目标，位置/人为干扰是否真的涨点。
3. **虚实标定 + 竞赛组合**：数字孪生只标定外参/增益/RTT/扰动；单任务通道按 `q_t×Δ/cost` 选任务；用 G0/G4/G5 验证标定、恢复、延迟是否过门。

三个灵感词怎么落到方案里：

| 灵感词 | 落到哪里 | 不做什么 |
|---|---|---|
| **虚实迁移** | 用 G1 URDF + 官方 IsaacLab/MuJoCo 搭轻量数字孪生，标定相机外参/焦距尺度/伺服增益/RTT，注入位置/遮挡/背景/目标移动扰动做风洞 | 不在仿真里训 6B 策略；不假设 sim 成功率能预测真机 |
| **视觉伺服** | 5 步执行块内做 IBVS/PBVS 混合修正；目标来自演示检索的相对位姿/目标图；接触段法向缩幅 | 不做 30Hz 广域网伺服；不做第二个学习残差模型 |
| **竞赛策略** | 320 trials 当投资组合；单任务不计分通道做 A/B；先交安全基线锁 tie-break；按 `q_t×Δ/cost` 分配工程 | 不把预览榜单任务排名当难度表；不 32 个任务各训一个策略 |

## 1. 本轮新核实的事实（只列会改变方案的）

### 1.1 规则：单模型、32 任务、10 次/任务、5 类泛化各 2 次、单任务不计分通道

官方参赛手册（2026-10-28 重新抓取，中文/英文两版一致）明确：

- 所有任务须基于**同一模型**完成，不得混合多个模型一起测试；模型类型不限（World Model、VLA 均可）。
- 32 个任务，每个任务 10 次独立运行；5 类泛化各 2 次：位置、干扰物、桌面背景、未见物品、人为干扰。
- 单次真机执行上限 **180 s**；排名先看 32 任务总平均成功率，成功率相同看总平均步骤分，再相同看更早提交。
- 评测跨 **N 台机器人**；提交须从 **8765** 起暴露 N 个连续端口；每端口独立交互，`reset()` 状态必须隔离。
- 比赛只设通才模型赛道；另有**不计分的单任务测试通道**，可用于单任务成功率/步骤分验证。

**对方案的约束**：CHUNK-SERVO 必须每端口独立、CPU 轻量、不抢 GPU；VLA 是唯一学习模型；伺服是确定性控制器；单任务通道是唯一敢做 A/B 的地方。

### 1.2 API：四路 RGB、无深度/力/触觉，`action_chunk_size` 决定反馈周期

提交模板（2026-10-28 复核）给出：

- 观测：`cam_left_high`、`cam_right_high`、`cam_left_wrist`、`cam_right_wrist` 四路 RGB 480×640；双臂关节 `[7]`、EE 位姿 `[6]`（xyz+rpy，base 系）、夹爪 `[1]`、下身体 `[15]`、语言 `str`。
- 动作：`joint` 或 `ee` 互斥；`action_chunk_size` 固定；`meta.token` 每次 `get_action` 都要带。
- `obs_delta_indices` 决定传哪些键、堆叠几帧；`image_resize` 可缩放。**没有 depth、camera_info、force/torque、tactile。**
- README 明确：`action_chunk_size` 是每次 `get_action` 返回的 leading time-axis 长度；index 0 先执行，其余按顺序执行，直到 evaluator 再次调用 `get_action`。**chunk 内没有新的观测，也没有打断机制。**
- 评测端逐调用记录延迟、波动和动作统计规律，作为结果可信度的一部分。

**关键推论**：如果 chunk=30、控制频率 30Hz，那么一次 `get_action` 之后有 **1 秒的开环执行**；如果 RTT=100ms，实际“看到的世界”比动作晚 100ms 以上。视觉伺服要生效，必须把 chunk 降到 3–8 步，或者把 VLA 规划与伺服执行拆成双频。这是本轮最硬的接口事实。

### 1.3 数据：33,276 条 / 169.28 h，32 任务；头双目有标定，腕部相机没有内参

32 个 HF 数据集合计（2026-10-28 逐数据集读取 `meta/info.json`）：

| 项 | 数值 |
|---|---:|
| episodes | **33,276** |
| frames | **18,282,246** |
| 时长 | **169.28 h**（30 fps） |
| 任务数 | 32 |
| 评分步骤总数 | 94 |
| 难度 | Easy 12 / Medium 12 / Hard 8 |
| 单任务 episodes | 969–1,533 |
| 单任务平均时长 | 6.2 s（HangCup）–37.6 s（ToolboxStorage） |

关键细节：

- 四路视频：`head_stereo_left/right`、`wrist_left/right`，均 480×640。
- `head_stereo` 有完整内参、畸变、R/T、基线 **58.2526 mm**、`rectified: true`；示例 HangCup 的 `fx≈282.37`。
- `wrist_left/right` 的 `camera_params` 只有 `color/ir1/ir2`，**没有内参矩阵**。这意味着腕部视觉伺服必须先做一次标定，或用 D435 型号先验 + 头部双目做深度。
- `state_d435` 是头相机在 base 系的 6D 位姿；`lower_body[-3:]` 与 `waist_state_joint` 一致；线上 API 给 `lower_body`，所以头相机外参可以在线恢复（第 11 轮已验证）。
- 任务文本里至少 **17/32** 明确出现插入、拔出、拧、拉拉链、合盖、倒、夹等接触动词；按“终局是否需要毫米级对齐”我们先验地把 **19/32** 列为 A 档（含挂/叠/拉链/锁/插入）。**最后 3 厘米不是少数任务的特例，而是通才模型的主战场。**

### 1.4 官方基线：UnifoLM-WLA-1.0 已经把“大模型”这件事做完了

这是本轮最重要的战略事实，前几轮没有充分展开：

- **UnifoLM-WLA-1.0**：6B 参数，约 2,500 小时真机数据，64 个任务（桌面操作 + 全身操作），支持二指夹爪和五指灵巧手；2026-09-28 开源 Base 权重、微调代码、模型服务器；发布仅一个月。
- 动作专家默认 **`chunk_size=30`、`target_fps=30`**，覆盖约 `[0, 29/30]` 秒；4 步扩散去噪；微调时冻结 VLM，只训 DiT action head + robot-state projector，**单张 24GB GPU 可跑**。
- 统一动作空间 **54 维**：左右 EE 各 6（相对 xyz + rotvec，在当前 EE 系）、左右夹爪各 1、左右灵巧手各 6、腰 3、躯干 3、base 平移 2、base yaw 1、base pose 6、左右腿各 6；统一状态 60 维。
- 模型服务器输出 30 步 chunk，输入是 `cam_left_high` + 左右腕部三路图；动作是相对 EE + gripper + lower_body + base_command + pivot。
- **UnifoLM-VLA-0**：另一条 VLA 基线，12 个 G1 任务，LeRobot v2.1 数据格式。
- **UnifoLM-WMA-0**：World-Model-Action，世界模型可作仿真引擎/策略增强；说明官方自己也押注世界模型，但榜单头部仍是 VLA。
- 官方仿真：`unitree_sim_isaaclab`、`unitree_mujoco`、`unitree_rl_mjlab`、`unitree_rl_lab`，足够搭一个轻量数字孪生。

**战略结论**：不要再从零训 6B/14B。把官方 WLA 基座拿来做 action-head 微调，把省下的算力投到**执行层**和**单任务评测**。官方 WLA 是否已经包含挑战赛 32 个任务的数据、是否直接适配挑战赛 API，必须先在单任务通道实测，不能假设它已适配。

### 1.5 榜单：29.7% 是“预览上限”，不是可复现的实验结果

官网首页/榜单（2026-10-28）显示 8 个模型：

| 排名 | 模型/用户 | 平均成功率 | 步骤分 |
|---|---|---:|---:|
| 1 | MolmoAct2 / DexHacker | **29.7%** | 39.0 |
| 2 | WALL-OSS-0.5 / Generalist Robotics | 28.5% | 38.9 |
| 3 | DreamZero / World Model Lab | 27.9% | 37.9 |
| 4 | Spirit-v1.5 / VLAGO | 25.9% | 34.4 |
| 5 | DM0 / Embodied AI Institute | 23.5% | 31.7 |
| 6 | π0.5 / RoboReasoner | 22.8% | 30.6 |
| 7 | GigaBrain-0 / xembody | 22.6% | 29.5 |
| 8 | GR00T N1.5 / Humanoid Dynamics | 20.5% | 28.1 |

但必须同时记录三条“不可用”证据：

1. `leaderboard_data.json` 的 `generated_from` 是 `gen_leaderboard.py`；对 8 个模型 ×32 任务做 `step ~ success` 回归，**R² > 0.999999，最大残差 <0.006**，形式是 `step ≈ k_model × success`。这不是实测的步骤分，是脚本生成的线性缩放。
2. 详情页 `details.html?model=MolmoAct2&user=DexHacker` 的 32 个任务视频全部是“测试视频占位，后续可替换为真实视频文件”。
3. 8 个模型的 32 维任务成功率两两相关，**平均 off-diagonal 相关系数只有 0.098**；而每个任务只有 10 次 trial，成功率却不是 10% 的整数倍（如 27.29%、27.85%）。真实 10 次 trial 的成功率只能是 0/10、1/10、…、10/10。

**结论**：把 29.7% 当作赛事方给的“预览上限/难度信号”可以；把它当 SOTA、当任务难度表、当失败分布，都不可以。本轮不从榜单任务排名里挖创新点，只从**公开模型家族的技术路线**和**官方数据/规则**里挖。

### 1.6 头部方案的做法与瓶颈：四种路线，同一个最后 3 厘米

榜单头部的名字对应的是真实的公开模型家族（分数是预览，但路线是真实的）：

| 模型家族 | 公开路线 | 优势 | 瓶颈（与本轮相关） |
|---|---|---|---|
| **MolmoAct2** | Ai2 的 action reasoning model；Molmo 2-ER + 专用 action expert + adaptive depth reasoning；大规模双臂数据；强调 3D 空间推理、推理加速、无 per-task 微调 | 3D/空间语义强；推理快；双臂 | 仍然是开环 chunk；最后插入/挂/拉链的接触精度与恢复 |
| **WALL-OSS-0.5** | X Square 的 4B VLA（3B VLM + action expert）；公开材料称 15 个真机任务上 60.5% average task progress | 预训练直接可用；progress 高 | progress ≠ success；最后一步失败就 0 分；4B 的实时性 |
| **DreamZero** | 14B Wan2.1 video-diffusion world-action model；世界模型预测未来视频再出动作 | 长程预测/规划 | 14B 推理重；世界模型不直接解决接触力/毫米级对齐；1 秒 chunk 更危险 |
| **π0.5** | Physical Intelligence 的开放世界泛化 VLA | 语义/新场景泛化 | 接触密集任务的精度；远程部署延迟 |
| **GigaBrain-0** | 世界模型生成数据 + VLA；用世界模型降真机数据依赖 | 数据效率/泛化 | 生成数据的物理保真度；最后 3 厘米 |
| **GR00T N1.5** | NVIDIA 通用人形 VLA | 生态/embodiment | 任务特定精度；数据覆盖 |

共同点：

- **没有一个是“接触闭环”模型**。它们都输出 action chunk，chunk 内不看新图；接触事件发生在 chunk 内部时，模型只能等下一个 chunk。
- **模型越大，chunk 越长，越不反应**。DreamZero 14B、WLA 6B、WALL 4B；推理越重，越倾向长 chunk；长 chunk 与接触精度直接冲突。
- **世界模型解决“想象未来”，不解决“现在偏了 2mm”**。世界模型可以预测“插入后是什么样”，但伺服需要的是“现在孔在图像里偏左 3px，往右修正 0.4mm”。
- **单模型规则让“再加一个学习残差”变得危险**；但“确定性视觉伺服”不是模型，是控制器。

### 1.7 为什么现在能做：官方基座 + 33k 演示 + 双目 + 数字孪生 + 近期工作

- 官方 WLA 基座 + 24GB 微调：不用从零训。
- 33k 成功演示：不只是 imitation 数据，也是**目标图/相对位姿库**。
- 头双目已标定；腕部相机可一次标定；EE 位姿 30Hz 可得。
- 官方 IsaacLab/MuJoCo 仓库：可搭轻量数字孪生，做延迟/增益/扰动测试。
- 近期工作证明“双频/异步/视觉反馈”是活跃方向：D²-VLA（双记忆双频 VLA）、VGM-VS（视觉几何模型做高精度伺服）、VLaRL（仿真训练 latent residual RL）、Action Chunk Scheduling（chunk 执行长度与反应性）、Catch Me If You Can（实时反馈去噪，公开摘要称端到端 71ms、反馈仅 1.95ms）、RTC（异步执行 action chunk）。这些工作说明：**“VLA 规划 + 快速反馈”是 2026 年的前沿，但还没有人把它做成“单模型合规 + 演示检索目标 + 竞赛 chunk 策略”的组合。**

以上事实的完整链接与检索日期见产物区 §11；核心来源是挑战赛官网/榜单 JSON、提交 README、HF 数据集元数据、WLA 仓库与官方文档、飞书参赛手册。榜单的“预览/合成”判断是我们在公开 JSON 上做的回归与相关性分析（B 级），不是官方声明。

## 2. 诊断：三个“1 秒”叠在一起

把一次失败拆开看：

```text
t0: 观测 → VLA 推理 (100-300ms) → 返回 30 步 chunk
t0+0.1s: evaluator 开始执行 chunk
t0+0.1s … t0+1.1s: 机器人开环执行 30 步
        ↑ 接触/滑移/人移动物体都发生在这一段
t0+1.1s: 才看到下一帧 → 已经晚了
```

三个“1 秒”：

1. **规划 1 秒**：30 步 chunk。
2. **推理/网络 0.1–0.3 秒**：6B/14B + 远程 websocket + JPEG。
3. **恢复 1 秒**：下一个 chunk 才能纠正。

视觉伺服的价值不是“更准的感知”，而是把第 3 个“1 秒”降到最后 3 厘米内的 **167ms 执行块**（5 步 @30Hz；含 RTT 端到端约 200–320ms），并且用**目标相对位姿**而不是绝对动作来抗位置/人为干扰。

## 3. 方法：CHUNK-SERVO

### 3.1 总架构

```text
                    ┌─────────────────────────────────────┐
                    │  Evaluator (N ports 8765..8765+N-1) │
                    └──────────────┬──────────────────────┘
                                   │ websocket: obs / action chunk
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  Per-port PolicyService (CPU)       │
                    │  ├─ phase/edit observer (GEO-RES.)  │
                    │  ├─ goal retrieval (demo library)   │
                    │  ├─ visual servo (IBVS/PBVS)        │
                    │  ├─ plan cache (30-step VLA plan)   │
                    │  └─ action adapter (WLA 54D → API)  │
                    └──────────────┬──────────────────────┘
                                   │ async, batched
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  Shared VLA server (GPU)            │
                    │  UnifoLM-WLA-1.0 / VLA-0, 30-step   │
                    └─────────────────────────────────────┘
```

- **唯一学习模型**：VLA（官方 WLA 微调 action head）。
- **确定性控制器**：视觉伺服；无学习权重；不违反单模型。
- **数据资产**：33k 成功演示 → 目标图/相对位姿库；不是第二个模型，是检索索引。
- **数字孪生**：只做标定/压力测试，不训练策略。

### 3.2 演示引导的相对目标（DG-KEYFRAME）

不要把“目标”定义成一张绝对图片。定义成**目标物/受器的相对位姿**：

```text
离线：
  对每个任务、每个阶段，从成功演示中取关键帧 k：
    T_base_target(k)  # 受器（杯架/网口/试管架/拉链头/锁孔）在 base 系
    T_base_ee(k)      # 夹爪在 base 系
    T_target_ee*(k) = T_base_target(k)^-1 · T_base_ee(k)
    I_wrist(k)        # 腕部目标图
    d(k)              # 视觉描述子（VLA encoder 或 ORB/颜色直方图）

在线：
  估计当前受器位姿 T_base_target(t)（头双目 + 局部 ICP / 第 11 轮几何）
  期望夹爪位姿：
    T_base_ee^d(t) = T_base_target(t) · T_target_ee*
  伺服误差：
    e(t) = log( T_base_ee(t)^-1 · T_base_ee^d(t) )
```

这样：

- **位置泛化**：受器移动 → `T_base_target(t)` 变 → 期望位姿跟着变。
- **人为干扰**：人移动受器/物体 → 重新估计 → 期望位姿跟着变。
- **未见物品**：只要受器/任务几何不变，相对目标不变；外观变化由 VLA 处理。
- **背景/干扰物**：伺服只用局部 ROI/目标图，不依赖全局背景。

`I_wrist(k)` 用于两种回退：

1. 当 `T_base_target(t)` 估计不可靠（透明/反光/遮挡）时，用腕部图像特征匹配（IBVS）直接对齐目标图；
2. 当目标被夹爪挡住时，用头双目 + 相对位姿（PBVS）。

### 3.3 视觉伺服：前馈 VLA + 反馈伺服

动作空间用 `ee`（与官方 WLA 的相对 EE 动作一致）。每个执行块：

```text
a_ff = VLA plan[t : t+H_c]          # H_c = 5，来自 30 步 plan
e = servo_error(obs_t, goal)         # 6D：xyz + rotvec
Δ = clip(K_p e + K_d ė, ±δ_p, ±δ_r) # 每块最多 1cm / 0.05rad
a_cmd = a_ff ∘ exp(Δ)                # 在 EE 局部系叠加
```

- **IBVS**：用腕部图像点/轮廓；`v = -λ L_s^+ (s - s*)`；`L_s` 由相机内参和深度决定；适合最后 1–2cm 的横向对齐。
- **PBVS**：用头双目/ICP 估计 `T_base_target`；`e = log(T_ee^-1 T_ee^d)`；适合 3–5cm 的接近和插入轴对齐。
- **混合**：远距离用 PBVS（稳定、全局），近距离用 IBVS（抗标定误差、直接看孔/边）；切换由 `d_t` 和特征置信度决定。
- **接触感知**：用第 11 轮的 `d_t, n_t, r_static, r_grasp`；接触段把 `Δ` 分解为法向/切向，法向缩幅/低通，切向保留；`r_grasp` 突变 → 滑移 → 重抓。
- **延迟补偿**：用测量的 RTT `τ` 做 Smith 预测/卡尔曼预测；`e_{t+τ} ≈ e_t + J_v v τ`；增益按 `τ/H_c` 降档；仿真里扫 0/50/100/150ms。

### 3.4 双频执行：plan 30, execute 5

```text
VLA:   每 30 步（1s）产出一个 30 步 plan；后台线程；不阻塞 get_action
Servo: 每 5 步（167ms）用最新腕部/头部图修正一次；返回 5 步 chunk
API:   metadata.action_chunk_size = 5；evaluator 执行 5 步后再次调用
```

为什么是 5？

- 5 步 @30Hz = 167ms，足够慢速接触的 1–2 次修正；
- 30 步 plan 摊薄 VLA 推理；1 次 VLA 推理服务 6 次伺服；
- 网络 payload 可控：腕部 128×128、头部 240×320，4 路图 JPEG 后约几十 KB/次；
- 如果实测 RTT 高（>100ms）或控制频率低（10Hz），把 `H_c` 调到 8；如果 RTT 低且任务动态，调到 3。**chunk size 是提交前要扫的超参数，不是拍脑袋的常数。**

### 3.5 人为干扰恢复：检测 → 停 → 重定位 → 重规划

第 11 轮的 GEO-RESIDUAL 已经给了“机器人动作解释不了的三维残差”。本轮把它接到控制环：

```text
if edit_score > θ_e for K frames:
    hold position
    re-localize T_base_target with head stereo
    if target visible:
        update goal; resume servo with conservative gain
    else:
        request VLA re-plan with new image + language
    if retries > max: fail gracefully
```

人为干扰轴占 20%（64/320 trials）；这是性价比最高的单项。恢复不需要“识别人类”，只需要“场景动了，而且不是我的动作解释的”。

### 3.6 虚实迁移：数字孪生只做三件事

不做“sim-to-real 训一个大模型”。做三件小事：

1. **标定**：用 G1 URDF + 头双目内参 + 腕部相机模型，拟合相机外参修正、焦距尺度、腕部安装误差；用真实演示的 EE 位姿/重投影误差做最小二乘。
2. **调参**：在 MuJoCo/IsaacLab 里搭 3 个任务族（peg-in-hole、hang/stack、zip/unlock），扫 `H_c`、`K_p/K_d`、RTT、噪声；找稳定域，不找“最高成功率”。
3. **压测**：在仿真里注入位置偏移、遮挡、背景变化、目标被移动/拿走；测检测延迟、恢复成功率、超调；把“人类扰动”建模成一个宽分布，而不是一个精确模型。

数字孪生是**控制器的风洞**，不是策略的训练场。这样 sim-to-real gap 只影响“标定/调参”，不影响“策略分布”。

## 4. 竞赛策略：320 trials 是投资组合，不是 32 个独立任务

### 4.1 算术

- 总分 `S = (1/32) Σ_t p_t`，`p_t` 是任务 t 的 10 次平均成功率。
- 320 trials 下，`p≈0.25` 的单次标准误约 `sqrt(0.25×0.75/320)=2.42pp`；配对设计会低一些，但**不要声称 +1–2pp 是结论**。
- 人为干扰轴 = 2/10 = **20%**；如果恢复把 human 轴从 `p_h` 提到 `p_h+Δh`，全局约 `+0.2 Δh`。
- 如果 10 个接触任务各 +15pp，全局 `+10/32×15=+4.7pp`；如果 16 个各 +10pp，`+5.0pp`。
- 两项叠加的保守区间 **+4–7pp**；乐观 +8–10pp；但必须用配对 A/B 和重复实验证明。

### 4.2 失败模式分诊

| 失败模式 | 典型任务 | 该投什么 | 不该投什么 |
|---|---|---|---|
| 最后接触/插入/挂/叠/拉链/锁 | PlugInEthernet、HangCup、ZipUp、StackBowls、Unlock、ArrangeTestTubes、ToolboxStorage | 视觉伺服 + 相对目标 + 接触相位 | 更大 VLA、更多语义数据 |
| 位置/人为干扰 | 5 类泛化轴；human_1/4 | 重定位 + 恢复 + 相对目标 | 固定轨迹、开环 chunk |
| 背景/干扰物/未见物品 | FruitSorting、ColorArrangement、OrganizeTools | VLA 数据增强/微调 + 局部 ROI | 纯几何伺服 |
| 变形/语义/长程 | FoldTowel、PackBag、SpellRobot、ConveyorSorting | VLA 基座 + 任务数据 | 6D 物体位姿网络 |

### 4.3 任务组合（先验，待单任务通道更新）

把 32 个任务按“最后 3 厘米杠杆”分三档：

- **A 档：伺服优先（19 个）**：HangCup、DisconnectEthernet、ToolboxStorage、PlugCharger、Unlock、ArrangeTestTubes、PourOutMedicine、OrganizeStationery、PackBag、ZipUp、PaperCupStacking、StorePaddle、StoreCups、PlugInEthernet、StackBowls、StoreEarphones、PackPhone、OrganizePencilCase、SyringeWaterTransfer。
- **B 档：VLA 优先（13 个）**：FruitCollection、PackDoll、FruitSorting、ColorArrangement、PlacePhotoFrame、OrganizeBookshelf、PickOutBatteries、OrganizeTools、FoldTowel、ArrangePlates、SpellRobot、ConveyorSorting、RemovePinnedNote。
- **C 档：低投入/观察**：在单任务通道里 `p_t` 接近 0 且失败在早期感知/抓取的任务；不投入伺服工程，保留 VLA 基线。

这张表是**先验**，不是结论。单任务通道测完后，用 `q_t`（失败发生在最后 3 厘米的比例）× `Δ`（伺服条件增益）/ `cost_t` 重排；每测 3–5 个任务更新一次。

### 4.4 单任务通道协议（不计分，但决定是否烧正式提交）

1. 选 5 个代表任务：PlugInEthernet（插入）、HangCup（挂）、ZipUp（拉链）、StackBowls（叠）、FoldTowel（变形，防回归）。
2. 每个任务 5 次 A/B：servo off / servo on；同一初始条件；记录成功、步骤分、耗时、p99 延迟。
3. 通过标准：至少 3 个任务 +10pp，FoldTowel 不回归 >5pp；否则不提交 servo 版本。
4. 再扫 `H_c ∈ {3,5,8}` 和 `image_resize` 两档；选 p99 延迟和成功率的最佳折中。
5. 最后才跑 32×10 的正式评测。

### 4.5 提交节奏

- 若允许多次提交（需邮件确认）：先交**安全基线**（官方 WLA + chunk 30 + 官方 API 适配），锁定“更早提交”的 tie-break；再交 CHUNK-SERVO 版本。
- 若只允许一次：先用单任务通道把 servo 版本打磨到稳定，再交最终版。
- 不要把 320 trials 浪费在“从零训 6B”“完整世界模型”“32 个任务各训一个策略”上；这些都不是本轮的最优边际收益。

## 5. 与第 10/11 轮的关系：保留、升级、剪枝

**保留**：

- FACT-VLA 的相位化 BC、CAC 柔顺执行、EGP 证据门控；
- GEO-RESIDUAL 的动作条件化残差、米制表面距离、编辑检测；
- 官方 WLA 基座、33k 演示、官方 rubric、单任务通道。

**升级**：

- 观测层 → 控制层：GEO-RESIDUAL 从“标注接触”变成“伺服触发/法向分解/编辑恢复”；
- 开环 chunk → 双频闭环：30 步规划 + 5 步伺服；
- 绝对动作 → 相对目标：从演示检索 `T_target_ee*`，抗位置/人为干扰；
- 手工相位 → 自动相位 + 置信度；
- 单个大模型 → 一个学习模型 + 一个确定性控制器（合规）。

**剪枝**：

- 不做从零训 VLA/World Model（官方 WLA 已做完，算力不划算）；
- 不做完整 sim-to-real 策略训练（sim gap + 算力；只做控制器风洞）；
- 不做 30Hz 广域网伺服（RTT 不允许；用 5 步 chunk / 双频）；
- 不做第二个学习模型/残差策略（单模型风险；用确定性伺服）；
- 不做 6D 物体位姿网络（透明/变形不可靠；用相对目标 + 局部对齐）；
- 不做力/触觉闭环（API 没有）；
- 不把预览榜单的任务排名当难度表（已证伪）；
- 不做 32 个任务各一个策略（规则禁止，且不泛化）。

**明确不建议继续投**：从零训通用 VLA/World Model、完整 sim-to-real 策略训练、30Hz 广域网视觉伺服、逐任务学习策略、6D 物体位姿网络、力/触觉闭环（API 没有）。这些方向要么已被官方 WLA 覆盖，要么被规则/接口/延迟/数据限制，边际收益低于执行层。

## 6. 实验门 G0–G7

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| G0 | 腕部相机能否标定？ | 重投影 ≤5px；头双目 ROI 有效 ≥70% | 只用头双目 PBVS；腕部仅做 2D 粗对齐 |
| G1 | 演示检索是否可信？ | top-5 含几何有效目标 ≥80%；相对位姿误差 ≤5mm/2° | 改用任务级固定相对目标 |
| G2 | 仿真伺服是否收敛？ | 横向 ≤2mm、深度 ≤3mm、2s 内 ≥95%；RTT 0–150ms 稳定 | 降增益/加 chunk；只做 PBVS |
| G3 | 真机单任务是否涨点？ | 3/5 任务 +10pp；FoldTowel 不回归 | 不提交 servo 版本 |
| G4 | 人为干扰能否恢复？ | 检测 ≤200ms；仿真恢复 ≥70% | 只做离线标注/不线上触发 |
| G5 | 延迟是否可接受？ | p99 ≤150ms；timeout 不升 | 加 chunk/降分辨率/关伺服 |
| G6 | 32 任务干跑是否稳定？ | N 端口隔离、reset 干净、内存不涨 | 回退基线 |
| G7 | 消融是否支持因果？ | 相对目标 > 绝对目标；5 步 > 30 步；伺服 > 无伺服 | 保留有效部分，砍掉无效部分 |

所有门先在离线回放和单任务不计分通道上过；没有过门，不烧正式提交。

## 7. 风险与合规

| 风险 | 影响 | 缓解 |
|---|---|---|
| 单模型解释 | 被判定为第二个模型 | 伺服无学习权重；C1 离线标注 / C2 确定性控制器 / C3 同 checkpoint 特征；提交材料写清楚 |
| 远程 RTT 高 | 伺服带宽不足 | 5 步 chunk；RTT 测量；预测补偿；失败回退 chunk 8–10 |
| 腕部无内参 | 2D 伺服不准 | 一次性棋盘格标定；D435 先验；头双目 PBVS 兜底 |
| 目标检索 mismatch | 错误目标 | 任务/阶段/相对位姿过滤；top-k 重打分；置信度低回退 VLA |
| 透明/反光/变形 | 深度/特征失败 | 只对刚体任务启用；腕部 2D + 夹爪滞止兜底 |
| 标定漂移/换机器人 | 残差变大 | 每机器人一次重投影校准；夹爪 PnP 自标定；误差大关伺服 |
| 人为干扰不在视野 | 漏检 | 本体/夹爪/任务状态兜底；不声称 100% |
| 安全 | 回撤/重抓碰撞 | 限速/限幅/最大重试；编辑检测即停 |
| 评测噪声 | +1–2pp 假阳性 | 配对 A/B、bootstrap、重复实验；320 trials SE≈2.4pp |
| 数据泄漏 | 离线指标虚高 | 按 session/物体/背景分组划分；相邻帧不跨 split |

## 8. 一句话押注

**用官方 WLA 做 30 步规划，用 33k 成功演示检索“目标-夹爪相对位姿”，用无学习权重的视觉伺服每 5 步闭环一次，用轻量数字孪生标定 RTT/增益，用单任务通道决定把工程投到哪些任务——在不违反单模型规则的前提下，把最后 3 厘米从开环变成闭环。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 12 轮产物 · CHUNK-SERVO 技术报告

> 检索/复核日期：**2026-10-28（UTC）**。对象：宇树 **UniBot 世界挑战赛**（G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署 + 官方远程真机 API）。本报告是第 12 轮想法区「CHUNK-SERVO」的工程化产物；不替换第 10 轮 FACT-VLA 和第 11 轮 GEO-RESIDUAL，而是把它们接到控制环。

## 0. 结论与边界

### 0.1 一句话结论

官方 WLA 的 30 步 action chunk 是吞吐优势，也是接触精度的结构性弱点；把 30 步切成 6 个 5 步执行块，用演示检索的相对目标和确定性视觉伺服在每块内修正，可以在不新增学习模型的前提下，把最后 3 厘米的反馈周期从 1s 降到 167ms 执行块（含 RTT 端到端约 200–320ms）；数字孪生只用于标定 RTT/增益/外参，竞赛策略只把工程投到 `q_t×Δ/cost` 最高的任务。

### 0.2 证据等级

| 等级 | 含义 | 本报告中的例子 |
|---|---|---|
| A | 官方文档、提交模板、数据集元数据、排行榜 JSON 直接核实 | 规则、API、33,276 eps、WLA `chunk_size=30`、榜单 29.7% |
| B | 我们在公开数据/网页上做的分析，可复现 | 榜单 `step~success` 回归、跨模型任务相关、每任务平均时长 |
| C | 设计假设，需 G0–G7 验证 | 5 步伺服 +10pp、RTT 150ms 稳定、相对目标 top-5≥80% |

### 0.3 本轮不做什么

- 不从零训 VLA/World Model；官方 WLA 已开源 6B 基座。
- 不做完整 sim-to-real 策略训练；数字孪生只做控制器风洞。
- 不做第二个学习模型/残差策略；伺服是确定性控制器。
- 不做 6D 物体位姿网络；用目标相对位姿 + 局部特征。
- 不做力/触觉闭环；API 没有。
- 不把预览榜单的任务排名当实测难度；只当先验。
- 不做 30Hz 广域网伺服；用 5 步 chunk/双频。
- 不把 ROS2 当提交接口；官方只认 `PolicyService` 的 Python 接口。

## 1. 事实核对

### 1.1 比赛规则（A）

官方参赛手册（飞书 docx，2026-10-28 通过 `r.jina.ai` 抓取；稳定拿到 §1.1–§2.2，后续章节可能截断，最终以官方页面为准）核实：

| 项 | 规则 |
|---|---|
| 模型 | 所有任务须基于**同一模型**完成，不得混合多个模型一起测试；模型类型不限 |
| 任务 | 32 项桌面任务 |
| 次数 | 每任务 10 次独立运行 |
| 泛化 | 5 类各 2 次：位置、干扰物、桌面背景、未见物品、人为干扰 |
| 时限 | 单次真机执行上限 **180 s** |
| 排名 | 先比 32 任务总平均成功率；相同看总平均步骤分；再相同看更早提交 |
| 部署 | 评测跨 **N 台机器人**；提交须从 **8765** 起暴露 N 个连续端口；每端口独立交互，`reset()` 状态必须隔离 |
| 测试通道 | 另有**不计分的单任务测试通道**，可用于单任务成功率/步骤分验证 |

**对方案的约束**：CHUNK-SERVO 必须是每端口独立、CPU 轻量、不抢 GPU 的控制器；不能是第二个策略模型。若官方对“模型”作最宽解释，走 §10 的 C1/C2/C3 合规模式。

### 1.2 提交 API（A）

提交模板 README（2026-10-28 复核）给出：

| 项 | 规格 |
|---|---|
| 观测图像 | `cam_left_high`、`cam_right_high`、`cam_left_wrist`、`cam_right_wrist` 四路 RGB **480×640** |
| 本体 | 双臂关节 `[7]`、EE 位姿 `[6]`（xyz+rpy，base 系）、夹爪 `[1]`、下身体 `[15]`、语言 `str` |
| 动作空间 | `control_space` 仅 `"joint"` 或 `"ee"`，二者互斥 |
| 共享动作 | `action.left_gripper [1]`、`action.right_gripper [1]`、`action.pivot [7]` |
| EE 动作 | `action.left_ee_pose_gripper_base [6]`、`action.right_ee_pose_gripper_base [6]`（绝对目标位姿，xyz+rpy，base 系） |
| chunk | `action_chunk_size` ≥1，固定；index 0 先执行，其余顺序执行，直到 evaluator 再次调用 `get_action` |
| token | `metadata.token` 握手校验一次；每次 `get_action` 的 `meta.token` 都要匹配 |
| 缺失 | **没有 depth、camera_info、force/torque、tactile** |
| 监控 | 评测端逐调用记录延迟、波动、动作统计规律，作为结果可信度的一部分 |

**关键推论**：`action_chunk_size=30`、控制频率 30Hz 时，一次 `get_action` 之后有 **1 秒开环执行**；chunk 内没有新观测，也没有打断机制。视觉伺服要生效，必须把 chunk 降到 3–8 步，或把 VLA 规划与伺服执行拆成双频。控制频率未在 README 中写死；本报告默认 30Hz，必须在单任务通道实测。

### 1.3 数据规模与任务结构（A）

32 个 HF 数据集（2026-10-28 逐数据集读取 `meta/info.json`）合计：

| 项 | 数值 |
|---|---:|
| episodes | **33,276** |
| frames | **18,282,246** |
| 时长 | **169.28 h**（30 fps） |
| 任务数 | 32 |
| 评分步骤总数 | 94 |
| 难度 | Easy 12 / Medium 12 / Hard 8 |
| 单任务 episodes | 969–1,533 |
| 单任务平均时长 | 6.2 s（HangCup）–37.6 s（ToolboxStorage） |

关键元数据（HangCup 示例，2026-10-28）：

```text
fps = 30
camera_params.head_stereo.camera_matrix_left  = [282.3693, 0, 311.5250; 0, 282.7521, 256.6277; 0, 0, 1]
camera_params.head_stereo.camera_matrix_right = [281.8743, 0, 329.9582; 0, 282.3186, 249.5120; 0, 0, 1]
camera_params.head_stereo.T = [-58.25257484955571, 0, 0] mm
camera_params.head_stereo.rectified = true
wrist_left/right.camera_params = color/ir1/ir2 only, no intrinsic matrix
state_d435 = [0.13014, 0.01778, 0.45645, -0.00704, 1.01141, -0.01591]
waist_state_joint = lower_body[-3:] = [-0.00995, -0.00373, 0.18065]
```

含义：

- 头部双目已校正，基线 **58.2526 mm**，焦距约 **282 px**；0.5–1.0 m 工作距离上视差约 16–33 px，足够局部毫米级深度。
- 腕部相机**没有内参矩阵**；2D 伺服前必须一次性标定，或用 D435 型号先验 + 头部双目深度兜底。
- `state_d435` 是头相机在 base 系的 6D 位姿；`lower_body[-3:]` 是腰部关节；线上 API 给 `lower_body`，因此头相机外参可以在线恢复（第 11 轮已验证）。

#### 32 任务统计（A，episodes/frames/hours 来自 `meta/info.json`；“最后接触”与“组合”是我们的先验分类）

| # | 任务 | 中文 | episodes | 平均时长 | 最后接触 | 组合 |
|---|---|---|---:|---:|:---:|:---:|
| T01 | Hang the Cup | 挂杯子 | 1043 | 6.2s | H | A |
| T02 | Fruit Basket Collection | 水果收集 | 1050 | 10.8s | L | B |
| T03 | Pack the Doll | 装娃娃 | 1060 | 19.6s | M | B |
| T04 | Fruit Sorting | 水果分类 | 1032 | 10.7s | L | B |
| T05 | Disconnect Ethernet | 拔网线 | 1025 | 10.5s | H | A |
| T06 | Color Arrangement | 颜色排列 | 1533 | 13.6s | L | B |
| T07 | Place Photo Frames | 摆放相框 | 1041 | 11.2s | M | B |
| T08 | Organize Bookshelf | 整理书架 | 1027 | 10.3s | M | B |
| T09 | Toolbox Storage | 工具箱收纳 | 1064 | 37.6s | H | A |
| T10 | Plug Charger | 插插头 | 1022 | 15.1s | H | A |
| T11 | Pick Out Battery | 挑出电池 | 993 | 16.1s | M | B |
| T12 | Unlock | 开锁 | 970 | 14.5s | H | A |
| T13 | Arrange Test Tubes | 整理试管 | 1004 | 17.8s | H | A |
| T14 | Open Pill Bottle | 倒出药品 | 979 | 21.8s | H | A |
| T15 | Organize Tools | 整理工具 | 1032 | 25.0s | M | B |
| T16 | Fold Towel | 叠毛巾 | 1053 | 25.8s | L | B |
| T17 | Organize Stationery | 整理文具 | 1028 | 23.9s | H | A |
| T18 | Pack Bag | 收拾书包 | 1067 | 15.1s | H | A |
| T19 | Zip Up | 拉上拉链 | 1006 | 14.1s | H | A |
| T20 | Paper Cup Stacking | 纸杯堆叠 | 969 | 13.9s | H | A |
| T21 | Clear Plates | 餐盘排列 | 1069 | 21.3s | M | B |
| T22 | Spell robot | 字母拼写 | 1018 | 31.2s | M | B |
| T23 | Store Racket | 球拍收纳 | 1047 | 34.1s | H | A |
| T24 | Conveyor Food Sorting | 传送带分拣 | 1049 | 12.2s | L | B |
| T25 | Stack Cups | 整理纸杯 | 1025 | 19.8s | H | A |
| T26 | Plug In Ethernet | 插网线 | 1009 | 16.4s | H | A |
| T27 | Stack Bowls | 碗具堆叠 | 979 | 10.1s | H | A |
| T28 | Store Earphones | 装耳机 | 982 | 24.1s | H | A |
| T29 | Pack Phone | 装手机 | 1016 | 29.2s | H | A |
| T30 | Remove Pinned Note | 移除固定便签 | 1026 | 19.6s | M | B |
| T31 | Organize Pencil Case | 整理文具袋 | 1024 | 20.5s | H | A |
| T32 | Syringe Water Transfer | 针管转移液体 | 1034 | 15.3s | H | A |

“最后接触”是任务语义的先验：H=终局需要毫米级插入/挂/叠/拉链/锁/拧；M=有接触但对齐容差较大；L=以搬运/分类/变形/动态为主。它不是实测失败率。

### 1.4 官方基线与 WLA 事实（A）

| 项 | 核实结果 |
|---|---|
| 模型 | UnifoLM-WLA-1.0，**6B** 参数 |
| 数据 | 约 **2,500 h** 真机数据 |
| 任务 | **64** 个任务（桌面操作 + 全身操作） |
| 末端 | 二指夹爪 + 多种五指灵巧手 |
| 动作空间 | 统一 **54 维** action；统一 **60 维** state；robot-state projector 接收 60+60 |
| chunk | 默认 `chunk_size=30`、`target_fps=30`，覆盖约 `[0, 29/30]` 秒 |
| 扩散 | 默认 `num_inference_timesteps=4` |
| 微调 | 冻结 VLM（`qwen_vl_interface`），只训 DiT action head + robot-state projector；默认单张 **24GB** GPU |
| 模型服务器 | 输出 30 步 chunk；输入 `cam_left_high` + 左右腕部三路图（`cam_right_high` 用于双目深度/伺服，不一定要进 VLA） |
| 动作语义 | EE 相对 xyz + rotvec（当前 EE 系）、gripper、waist、torso、base、legs |
| 开源时间 | 2026-09-28 发布 Base 权重与微调代码 |
| 相关基线 | UnifoLM-VLA-0（12 个 G1 任务，LeRobot v2.1）；UnifoLM-WMA-0（World-Model-Action） |
| 仿真 | `unitree_sim_isaaclab`、`unitree_mujoco`、`unitree_rl_mjlab`、`unitree_rl_lab` |

**54 维动作布局**（官方 `robot_action_state_processing_en.md`）：

| slice | 维度 | 含义 | 语义 |
|---|---:|---|---|
| `[0:6]` | 6 | left EE | 相对当前左 EE 的 xyz + rotvec |
| `[6:7]` | 1 | left gripper | 原始标量 |
| `[7:13]` | 6 | left dexterous hand | 前 6 维 |
| `[13:19]` | 6 | right EE | 相对当前右 EE 的 xyz + rotvec |
| `[19:20]` | 1 | right gripper | 原始标量 |
| `[20:26]` | 6 | right dexterous hand | 前 6 维 |
| `[26:29]` | 3 | waist | 前 3 维 |
| `[29:32]` | 3 | torso | 前 3 维 |
| `[32:34]` | 2 | base translation | `vx, vy` |
| `[34:35]` | 1 | base rotation | `omega_z` |
| `[35:41]` | 6 | base pose | 相对当前 base 的 xyz + rotvec |
| `[41:42]` | 1 | height | 高度 |
| `[42:48]` | 6 | left leg | 6 关节 |
| `[48:54]` | 6 | right leg | 6 关节 |

**战略结论**：不要从零训 6B/14B。用官方 WLA Base 做 action-head 微调，把算力投到执行层和单任务评测。挑战赛 API 的 `ee` 动作是 **2×6 EE + 2×1 gripper + 7 pivot = 21 维**；WLA 的 54 维需要 adapter：EE 相对动作 compose 到当前绝对位姿，gripper 直通，pivot 从 base/waist/height 组合。官方 WLA 是否已覆盖挑战赛 32 任务、`pivot` 语义是否与挑战赛一致，必须在单任务通道实测。

### 1.5 榜单取证（A+B）

官网首页/榜单（2026-10-28）8 个模型：

| 排名 | 模型/用户 | 平均成功率 | 平均时长 | 步骤分 |
|---|---|---:|---:|---:|
| 1 | MolmoAct2 / DexHacker | **29.7%** | 44.02 s | 39.0 |
| 2 | WALL-OSS-0.5 / Generalist Robotics | 28.5% | 43.74 s | 38.9 |
| 3 | DreamZero / World Model Lab | 27.9% | 44.59 s | 37.9 |
| 4 | Spirit-v1.5 / VLAGO | 25.9% | 45.19 s | 34.4 |
| 5 | DM0 / Embodied AI Institute | 23.5% | 45.11 s | 31.7 |
| 6 | π0.5 / RoboReasoner | 22.8% | 43.88 s | 30.6 |
| 7 | GigaBrain-0 / xembody | 22.6% | 43.76 s | 29.5 |
| 8 | GR00T N1.5 / Humanoid Dynamics | 20.5% | 44.71 s | 28.1 |

取证分析（B）：

1. `leaderboard_data.json` 的 `generated_from` 是 `"gen_leaderboard.py"`。
2. 对 8 个模型 ×32 任务做 `step_score ~ success_rate` 回归，**R² > 0.999999，最大残差 <0.006**；每个模型的斜率不同，形式是 `step ≈ k_model × success`。这不是实测步骤分，是脚本生成的线性缩放。
3. 详情页 `details.html?model=MolmoAct2&user=DexHacker` 的 32 个任务视频全部是“测试视频占位，后续可替换为真实视频文件”。
4. 8 个模型的 32 维任务成功率两两相关，**平均 off-diagonal 相关系数约 0.098**；如果任务难度是真实的，不同模型的任务级成功率应该正相关。
5. 每任务只有 10 次 trial，但成功率出现 27.29%、27.85%、38.43% 等非 10% 整数倍；真实 10 次 trial 只能是 0/10、1/10、…、10/10。

**结论**：29.7% 可以作为“赛事方预览上限/难度信号”；不能作为 SOTA、任务难度表或失败分布。本轮不从榜单任务排名挖创新点，只从公开模型家族的技术路线和官方数据/规则挖。

### 1.6 头部方案的做法与瓶颈（A+B）

| 模型家族 | 公开路线 | 优势 | 与本轮相关的瓶颈 |
|---|---|---|---|
| **MolmoAct2** | Ai2 的 action reasoning model；Molmo 2-ER + 专用 action expert + adaptive depth reasoning；大规模双臂数据；强调 3D 空间推理、推理加速、无 per-task 微调 | 3D/空间语义强；推理快；双臂 | 仍然是开环 chunk；最后插入/挂/拉链的接触精度与恢复 |
| **WALL-OSS-0.5** | X Square 的 4B VLA（3B VLM + action expert）；公开材料称 15 个真机任务上 60.5% average task progress | 预训练直接可用；progress 高 | progress ≠ success；最后一步失败就 0 分；4B 的实时性 |
| **DreamZero** | 14B Wan2.1 video-diffusion world-action model；世界模型预测未来视频再出动作 | 长程预测/规划 | 14B 推理重；世界模型不直接解决接触力/毫米级对齐；1 秒 chunk 更危险 |
| **π0.5** | Physical Intelligence 的开放世界泛化 VLA | 语义/新场景泛化 | 接触密集任务的精度；远程部署延迟 |
| **GigaBrain-0** | 世界模型生成数据 + VLA；用世界模型降真机数据依赖 | 数据效率/泛化 | 生成数据的物理保真度；最后 3 厘米 |
| **GR00T N1.5** | NVIDIA 通用人形 VLA | 生态/embodiment | 任务特定精度；数据覆盖 |

共同点：

- 都是 action chunk 开环执行；chunk 内不看新图。
- 模型越大，chunk 越长，越不反应；长 chunk 与接触精度直接冲突。
- 世界模型解决“想象未来”，不解决“现在偏了 2mm”。
- 单模型规则让“再加一个学习残差”危险；但“确定性视觉伺服”不是模型，是控制器。

### 1.7 未核实/未解决

- 评测端实际控制频率（本报告假设 30Hz；必须实测）。
- 网络 RTT 分布（同城/跨城/跨洲；必须实测）。
- 腕部相机内参（数据缺失；必须标定）。
- 是否允许多次提交、提交次数上限（需邮件确认）。
- 官方 WLA 与挑战赛 API 的 `pivot` 语义是否完全一致。
- 挑战赛 32 任务是否都包含在 WLA 的 64 任务训练集中。
- 人为干扰的具体协议（何时、如何介入；手册未完全展开）。
- 真实任务成功率/失败分布（榜单是预览，不能反推）。

## 2. 问题形式化

### 2.1 评分与不确定性

总分：

```math
S = \frac{1}{32}\sum_{t=1}^{32} p_t,\qquad
p_t = \frac{1}{10}\sum_{j=1}^{10} y_{t,j},\quad y_{t,j}\in\{0,1\}.
```

320 trials 下，若 `p≈0.25`，单次标准误：

```math
\mathrm{SE}(S)\approx \sqrt{\frac{p(1-p)}{320}}\approx 0.0242.
```

配对 A/B 的方差取决于任务内相关；若同一初始条件的 A/B 成功高度相关，配对差值方差可显著降低。报告必须给配对差值的 bootstrap 置信区间，而不是只报两个平均值。

人为干扰轴：

```math
\Delta S_{\mathrm{human}} = \frac{2}{10}\,\Delta p_h = 0.2\,\Delta p_h.
```

即 human 轴成功率 +10pp → 全局 +2pp（每个任务 10 次里 2 次是 human；32 任务平均后仍为 0.2 倍）。

### 2.2 接口时间模型

设：

- `f_c`：evaluator 控制频率（假设 30Hz）；
- `H_c`：提交的 `action_chunk_size`；
- `τ`：网络 RTT + 推理 + 图像传输的等效延迟；
- `T_fb`：从“世界变化”到“策略看到变化”的反馈周期。

则：

```math
T_{\mathrm{fb}} \approx \frac{H_c}{f_c} + \tau.
```

| 场景 | `H_c` | `f_c` | `τ` | `T_fb` | 评价 |
|---|---:|---:|---:|---:|---|
| 官方 WLA 默认 | 30 | 30 | 50ms | **1050ms** | 接触段基本开环 |
| 本方案保守 | 5 | 30 | 50ms | **217ms** | 可做 1–2 次接触修正 |
| 本方案乐观 | 5 | 30 | 20ms | **187ms** | 需低 RTT |
| 本方案高延迟 | 5 | 30 | 150ms | **317ms** | 增益降档 |
| 低控制频率 | 5 | 10 | 50ms | **550ms** | 改 `H_c=3` 或只做 PBVS |
| 极低延迟 | 3 | 30 | 20ms | **120ms** | 动态任务可用 |

**结论**：`H_c` 必须按实测 `f_c` 和 `τ` 选；不能把 30 步默认值直接搬到远程 API。

### 2.3 相对目标

定义：

- `T_base_target(t)`：受器（杯架/网口/试管架/拉链头/锁孔）在 base 系的位姿；
- `T_base_ee(t)`：夹爪在 base 系的位姿；
- `T_target_ee*`：从成功演示检索出的“受器→夹爪”相对目标；
- `T_base_ee^d(t) = T_base_target(t)\,T_target_ee*`：当前期望夹爪位姿。

误差：

```math
e(t) = \log\!\left(T_{\mathrm{base},ee}(t)^{-1}T_{\mathrm{base},ee}^{d}(t)\right)
     = \begin{bmatrix} e_p \\ e_r \end{bmatrix}\in\mathbb R^6.
```

为什么用相对目标：

- 位置泛化：受器移动，`T_base_target` 变，期望位姿跟着变。
- 人为干扰：人移动受器/物体，重新估计 `T_base_target` 即可。
- 未见物品：受器/任务几何不变，相对目标不变；外观由 VLA 处理。
- 背景/干扰物：伺服只用局部 ROI/目标图，不依赖全局背景。

### 2.4 可辨识性条件

视觉伺服只在以下条件同时满足时启用：

1. 受器/目标在头部双目或腕部视野内；
2. 深度/视差有效（双目 ROI 有效像素 ≥70%，或腕部特征 inlier ≥15）；
3. 相机标定误差在门限内（重投影 ≤5px）；
4. 目标相对位姿的估计协方差低于阈值；
5. 任务/阶段属于刚体接触类（A 档）。

任一条不满足 → 回退 VLA 开环或 PBVS 粗对齐；不硬做 IBVS。

## 3. 系统设计

### 3.1 进程/端口拓扑

```text
                    ┌─────────────────────────────────────┐
                    │  Evaluator (N ports 8765..8765+N-1) │
                    └──────────────┬──────────────────────┘
                                   │ websocket: obs / action chunk
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  Per-port PolicyService (CPU)       │
                    │  ├─ phase/edit observer (GEO-RES.)  │
                    │  ├─ goal retrieval (demo library)   │
                    │  ├─ visual servo (IBVS/PBVS)        │
                    │  ├─ plan cache (30-step VLA plan)   │
                    │  └─ action adapter (WLA 54D → API)  │
                    └──────────────┬──────────────────────┘
                                   │ async, batched
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  Shared VLA server (GPU)            │
                    │  UnifoLM-WLA-1.0 / VLA-0, 30-step   │
                    └─────────────────────────────────────┘
```

- 每个端口一个 `PolicyService` 实例，独立 `reset()`、独立 plan cache、独立 goal 状态。
- 伺服/检索是 CPU 线程，不阻塞 websocket；VLA 请求异步、可批处理。
- 共享 VLA server 用 session ID 区分端口；模型权重只有一份，不违反单模型。
- GPU 6B bf16 约 12GB；一张 24GB/40GB GPU 可服务多个端口，具体并发取决于 batch 和序列长度。

### 3.2 接口契约

提交 metadata 示例：

```python
{
    "control_space": "ee",
    "obs_delta_indices": {
        "observation.language":                         [0],
        "observation.images.cam_left_high":             [0],
        "observation.images.cam_right_high":            [0],
        "observation.images.cam_left_wrist":            [0],
        "observation.images.cam_right_wrist":           [0],
        "observation.state.left_ee_pose_gripper_base":  [0],
        "observation.state.right_ee_pose_gripper_base": [0],
        "observation.state.left_gripper":               [0],
        "observation.state.right_gripper":              [0],
        "observation.state.lower_body":                 [0],
    },
    "image_resize": {
        "observation.images.cam_left_high":  [240, 320],
        "observation.images.cam_right_high": [240, 320],
        "observation.images.cam_left_wrist": [128, 128],
        "observation.images.cam_right_wrist":[128, 128],
    },
    "action_chunk_size": 5,
    "token": os.environ["UNIBOT_SUBMISSION_TOKEN"],
}
```

注意：`observation.language` 的 offset 必须是 `[0]`（标量字符串，无时间轴）；其余键先用 `[0]` 取当前帧。若 WLA 训练配置要求多帧堆叠，按配置改成 `[-4,-2,0]` 等，并保持 offset ≤0、严格递增。

**观测/语言适配**：挑战赛 `*_ee_pose_gripper_base` 是 xyz+rpy；WLA server 的 `*_ee_6d` 实际是 **xyz+rot6d（9 维）**，obs adapter 必须做 rpy→rot6d。图像映射为 `cam_left_high` + 左右腕部三路；`cam_right_high` 只用于双目深度/伺服。语言方面，WLA server 用 `unnorm_key`/固定 prompt，不直接吃挑战赛的 `observation.language`；需要把 32 任务语言映射到 WLA 的任务 key（或空 prompt），并在单任务通道验证。

动作返回（`ee` 模式）：

```python
{
    "meta.token": token,
    "action.left_gripper":  np.float32 (5,1),
    "action.right_gripper": np.float32 (5,1),
    "action.pivot":         np.float32 (5,7),
    "action.left_ee_pose_gripper_base":  np.float32 (5,6),  # absolute xyz+rpy
    "action.right_ee_pose_gripper_base": np.float32 (5,6),  # absolute xyz+rpy
}
```

注意：挑战赛 API 的 EE 动作是**绝对目标位姿**；WLA 输出的是**相对当前 EE** 的 xyz+rotvec。adapter 必须先 compose 到当前 EE 绝对位姿，再叠加伺服修正。

### 3.3 `get_action` 伪代码

```python
class ChunkServoPolicy:
    def get_action(self, obs):
        self._tick(obs)
        self._maybe_request_plan(obs)

        if self.plan is None:
            # cold start: synchronous VLA, safe hold if timeout
            self.plan = self.vla.predict(obs)
            self.plan_age = 0

        if self.mode == "SERVO" and self.goal is not None:
            a_ff = self.plan[self.plan_idx : self.plan_idx + self.H_c]
            delta = self.servo.compute(obs, self.goal)
            a_cmd = compose_relative(a_ff, delta)
        else:
            a_cmd = self.plan[self.plan_idx : self.plan_idx + self.H_c]

        self.plan_idx += self.H_c
        if self.plan_idx >= len(self.plan):
            self.plan_idx = 0
            self.plan = None  # force next async request
        return self.adapter.to_api(a_cmd, obs, self.token)
```

`_maybe_request_plan`：

```python
def _maybe_request_plan(self, obs):
    if self._future is not None and not self._future.done():
        return
    if self._future is not None:
        self.plan = self._future.result()
        self.plan_age = 0
        self._future = None
    if self.plan is None or self.plan_age >= self.plan_ttl:
        snapshot = copy_obs(obs)
        self._future = self.executor.submit(self.vla.predict, snapshot)
```

规则：

- VLA 永远不阻塞 `get_action`（除冷启动）；plan 过期就用旧 plan + 伺服。
- 每个 chunk 只做一次伺服；伺服失败不影响返回合法动作。
- 任何异常 → 返回上一组合法 chunk 或安全 hold；绝不返回 NaN/错误形状。

### 3.4 动作适配（WLA 54D → 挑战赛 21D）

```text
WLA 54D:
  left_ee_rel[6], left_gripper[1], left_hand[6],
  right_ee_rel[6], right_gripper[1], right_hand[6],
  waist[3], torso[3], base_vxvy[2], base_wz[1],
  base_pose_rel[6], height[1], left_leg[6], right_leg[6]

挑战赛 ee 21D:
  left_ee_abs[6], right_ee_abs[6],
  left_gripper[1], right_gripper[1], pivot[7]
```

映射：

1. `left_ee_abs = compose(T_base_ee_left_current, exp(left_ee_rel))`；转 xyz+rpy。
2. `right_ee_abs` 同理。
3. gripper 直通（按挑战赛的 0–1 方向校验）。
4. `pivot = [vx, vy, wz, yaw, pitch, roll, height]`，从 WLA base/waist 组合；具体符号/顺序必须用 `example_env.py` 和单任务通道验证。
5. 腿部/灵巧手在挑战赛 `ee` 模式下不直接下发；若 `pivot` 需要下身体，按官方 WLA server 的 `action.pivot` 语义映射。

**关键细节**：WLA 的每个未来动作是“相对 plan-time 当前 EE”的位姿（compose 后才是 base 系绝对目标），不是累积增量；adapter 必须先把整个 30 步 compose 成 base 系绝对目标，再按 5 步切片。否则切片后的第 6–30 步会以错误的锚点解释，产生系统性偏移。

**帧/TCP 风险**：WLA 的 EE 帧与挑战赛的 `*_ee_pose_gripper_base` 帧可能差一个 TCP/夹爪长度偏移；必须用 `example_env.py` 的观测和真实数据做一次手眼/工具坐标校准（平移 ≤1cm、旋转 ≤2°）。这是 G6 的第一验证项。

**风险**：`pivot` 的 7 维语义在挑战赛 README 中只写“Lower-body / pivot target”，没有逐维定义；这是 adapter 的第一验证项（G6）。若 `pivot` 语义不匹配，先返回全零 pivot（保持下身体不动），只验证双臂；不要猜符号。

### 3.5 状态机

```text
INIT ──first obs──▶ PLAN ──plan ready──▶ SERVO
  ▲                   ▲                    │
  │                   │                    ├─ d_t < d_c ──▶ CONTACT
  │                   │                    │                 │
  │                   │                    │                 └─ contact released ──▶ SERVO
  │                   │                    │
  │                   └── replan ◀── RECOVER ◀── edit_score > θ_e
  │                                      │
  └──────────────────────────────────────┘
任意状态 ──task success / max steps──▶ DONE
```

- `SERVO`：正常接近，PBVS 主导，IBVS 辅助。
- `CONTACT`：`d_t < d_c` 或相位=接触；法向增益降低、切向保留；`r_grasp` 突变 → 滑移处理。
- `RECOVER`：编辑检测触发；先停，再重定位；目标可见 → 更新 goal；不可见 → VLA 重规划。
- `DONE`：任务成功/最大步数；清理状态，等待 `reset()`。

## 4. 视觉伺服推导

### 4.1 IBVS

相机系 3D 点 `P = (X,Y,Z)`，像素 `s = (u,v)`。归一化 `x=X/Z, y=Y/Z`。单点交互矩阵：

```math
L_s =
\begin{bmatrix}
-\dfrac{1}{Z} & 0 & \dfrac{x}{Z} & xy & -(1+x^2) & y\\[6pt]
0 & -\dfrac{1}{Z} & \dfrac{y}{Z} & 1+y^2 & -xy & -x
\end{bmatrix}.
```

像素形式（`u=f_x x+c_x`, `v=f_y y+c_y`）：

```math
L_s^{px} =
\begin{bmatrix}
-\dfrac{f_x}{Z} & 0 & \dfrac{u-c_x}{Z} &
\dfrac{(u-c_x)(v-c_y)}{f_y} &
-\dfrac{f_x^2+(u-c_x)^2}{f_x} &
\dfrac{(v-c_y)f_x}{f_y}\\[8pt]
0 & -\dfrac{f_y}{Z} & \dfrac{v-c_y}{Z} &
\dfrac{f_y^2+(v-c_y)^2}{f_y} &
-\dfrac{(u-c_x)(v-c_y)}{f_x} &
-\dfrac{(u-c_x)f_y}{f_x}
\end{bmatrix}.
```

控制律：

```math
\mathbf v_c = -\lambda\,L_s^{+}(\mathbf s-\mathbf s^*),\qquad
L_s^{+}=(L_s^{\top}L_s)^{-1}L_s^{\top}.
```

- 单点只有 2 个约束，不能唯一确定 6D 速度；用 ≥3 个点/轮廓/线特征，或只控制任务相关子空间（如 x/y/插入轴）。
- `Z` 用头双目深度或腕部目标图的先验深度；透明/反光物体 → 置信度低 → 回退 PBVS/VLA。
- 目标图 `I_wrist(k)` 提供 `s*`；特征用 ORB/轮廓/颜色块；不要用需要第二个学习模型的描述子（除非用同一 VLA checkpoint 的 encoder，C3）。

### 4.2 PBVS

位姿误差：

```math
T_{err} = T_{ee}^{-1}T_{ee}^{d},\qquad
e = \begin{bmatrix} t_{err} \\ \log(R_{err}) \end{bmatrix}.
```

控制律：

```math
\mathbf v_c = -\lambda\,K\,e,\qquad
K=\mathrm{diag}(k_x,k_y,k_z,k_{rx},k_{ry},k_{rz}).
```

- `T_ee^d` 来自 `T_base_target(t)·T_target_ee*`；`T_base_target` 用头双目 + 局部 ICP/第 11 轮几何估计。
- 远距离（>5cm）用 PBVS；近距离（<2cm）用 IBVS；中间用置信度加权。
- 旋转误差用 rotvec；大角度时先对齐插入轴，再做横向对齐。
- 位姿估计协方差大时，降低 `K` 或只做平移。

### 4.3 前馈 + 反馈

```math
a_{cmd} = a_{ff}\circ\exp(\Delta),\qquad
\Delta = \mathrm{clip}\!\left(K_p e + K_d\dot e,\ \pm\delta_p,\ \pm\delta_r\right).
```

性质：

- `a_ff` 是 VLA 的 30 步相对动作；`Δ` 是伺服修正；本报告默认 `Δ` 在 EE 局部系，右乘到绝对目标上（`T_cmd = T_target · exp(Δ)`）；若改用 base 系误差，则左乘。
- `δ_p` 每块最多 1cm，`δ_r` 最多 0.05rad；避免伺服压过 VLA 的语义意图。
- 接触段：`Δ = Δ_n + Δ_t`；`Δ_n` 乘 `0.3–0.5` 并低通；`Δ_t` 保留；法向力不可测，用 `d_t` 和 `r_static` 代理。
- 若 `||Δ||` 连续 3 块 > 阈值，判定目标估计/标定异常，回退 VLA 或重定位。

### 4.4 延迟与稳定性

简化离散积分器：

```math
e_{k+1}=e_k-K H_c\,e_{k-d},
```

其中 `d=τ/(H_c/f_c)` 是延迟块数。特征方程：

```math
z^{d+1}-z^{d}+K H_c=0.
```

- `d=0`：`|1-KH_c|<1` → `0<KH_c<2`。
- `d=1`：`z^2-z+KH_c=0`；稳定域 `0<KH_c<1`；增益裕度约减半。
- `d=2`：稳定域进一步缩小；必须降增益或加预测。

实践：

- 用 `τ` 测量值做 Smith 预测：`e_{k+d} ≈ e_k + J_v v\,τ`。
- 增益调度：`K_eff = K_0 / (1 + τ/τ_0)`；`τ_0` 取 50ms。
- 仿真扫 `τ ∈ {0,50,100,150}ms`，记录超调/收敛/振荡；真机只允许在稳定域内。
- 如果 `T_fb > 300ms`，关闭 IBVS，只做 PBVS 粗对齐 + VLA；不要用高增益追。

### 4.5 接触/滑移/编辑

沿用第 11 轮信号：

- `d_t`：夹爪到局部表面的米制距离；
- `n_t`：表面法向；
- `r_static`：物体静止假设下的刚体运动残差；
- `r_grasp`：物体随夹爪刚性运动假设下的残差；
- `edit_score`：两者都解释不了的场景运动。

控制策略：

| 信号 | 判定 | 动作 |
|---|---|---|
| `d_t > d_far` | 自由接近 | PBVS，正常增益 |
| `d_far ≥ d_t > d_c` | 预接触 | PBVS + IBVS 混合，降速 |
| `d_t ≤ d_c` | 接触 | 法向缩幅/低通，切向保留 |
| `r_grasp` 突变 | 滑移 | 停止切向，重抓/加大夹持 |
| `r_static` 大、`r_grasp` 小 | 物体被夹住 | 搬运，正常闭环 |
| `edit_score > θ_e` | 人为编辑 | 停 → 重定位 → 重规划 |
| 深度/特征置信度低 | 感知失败 | 回退 VLA/PBVS，不硬做 IBVS |

## 5. 演示引导的目标库

### 5.1 离线管线

```text
for each episode:
    phases = segment(episode)                  # FACT-VLA CPT / GEO-RESIDUAL
    for each phase:
        k = select_keyframe(phase)             # last pre-contact / closest to target
        T_base_target = estimate_target(episode, k)   # stereo + object/target pose
        T_base_ee = episode.state[k].ee_pose
        T_target_ee = inv(T_base_target) @ T_base_ee
        I_wrist = episode.wrist[k]
        d = descriptor(I_wrist)                # ORB/color/VLA encoder
        index.add(task, phase, T_target_ee, d, I_wrist, quality)
```

关键帧选择：

- 接触任务：取“首次接触前 1–3 帧”和“接触稳定后 1 帧”；
- 挂/叠/插入：取“目标进入腕部视野且夹爪距离 <5cm”的帧；
- 拉链/锁：取“夹爪咬合前”的帧；
- 变形任务：不建精确相对目标，只建相位/语义目标，伺服不启用。

目标位姿估计：

- 刚体受器：头双目 + 局部 ICP/平面/圆/线拟合；
- 透明/反光：用腕部目标图 + 头双目粗深度；置信度低不建库；
- 目标被夹爪挡住：用演示的 EE 位姿反推，或只存腕部目标图；
- 人为干扰：目标位姿在线重估，不依赖离线绝对位姿。

### 5.2 检索

```text
candidates = index.filter(task=task_id, phase=phase_id)
if target_pose_valid:
    candidates = candidates.rerank(pose_prior=T_target_ee_prior, top=50)
topk = candidates.topk(descriptor_distance, k=5)
goal = rerank(topk, pose_consistency, image_quality, phase)
if goal.confidence < θ_c:
    fallback()
```

- 任务/阶段过滤优先于外观；不要让颜色直方图把“插网线”匹配到“拔网线”。
- 相对位姿先验来自当前 `T_base_target` 和任务几何；只用于 rerank，不用于硬筛。
- top-k 重打分：描述子距离、相对位姿一致性、目标图清晰度、相位置信度。
- 检索库按任务/阶段分片；N 端口只读，内存共享（copy-on-write）。

### 5.3 回退

```text
if target_pose_valid and wrist_features_valid:  PBVS + IBVS
elif target_pose_valid:                          PBVS
elif wrist_features_valid:                       IBVS (with prior depth)
else:                                            VLA open-loop
```

回退不是失败：它保证 `get_action` 永远返回合法动作；伺服的边际收益在 A 档任务，B 档任务回退 VLA 是预期行为。

### 5.4 规模估算

- 33,276 episodes；A 档 19 任务约 19k episodes；
- 每 episode 1–2 个伺服关键帧 → 约 20–40k 目标；
- 128×128 JPEG 约 5–10KB → 200–400MB；
- 描述子 256–512 floats → 40–80MB；
- 索引/元数据 <100MB；
- 总 <1GB，可随提交包分发或预加载。

## 6. 虚实迁移测试台

### 6.1 数字孪生

- **机器人**：G1 29-DoF URDF + Dex1 夹爪；关节限位/速度/加速度。
- **场景**：桌面 + 3 个任务族：
  1. peg-in-hole（网线/充电器/试管）；
  2. hang/stack（杯架/碗/纸杯）；
  3. zip/unlock（拉链/锁/瓶盖）。
- **相机**：头部双目（含基线/内参/外参）+ 左右腕部（先用 D435 先验，再标定）。
- **控制**：30Hz；evaluator 延迟队列；chunk 执行；RTT 注入。
- **扰动**：位置偏移、遮挡、背景纹理、目标移动/拿走、人手进入视野、光照变化。
- **指标**：收敛时间、稳态误差、超调、成功率、恢复时间、p99 延迟。

### 6.2 系统辨识

待辨识参数：

| 参数 | 含义 | 先验/范围 | 数据 |
|---|---|---|---|
| `δT_head` | 头相机外参修正 | <2cm/2° | 真实演示重投影 |
| `δT_wrist` | 腕部相机安装修正 | <1cm/3° | 棋盘格/已知 EE 运动 |
| `s_f` | 焦距尺度 | 0.9–1.1 | 重投影/已知尺寸 |
| `K_p,K_d` | 伺服增益 | 0.2–1.0 | 仿真阶跃/真机小步 |
| `τ` | 等效延迟 | 0–200ms | 时间戳/互相关 |
| `d_c` | 接触距离阈值 | 1–10mm | 第 11 轮几何 |

方法：

- 重投影误差最小二乘：`min_{δT,s_f} Σ ||π(δT,s_f,X)-u||²`；
- 阶跃响应拟合：`min_{K,τ} Σ ||e(t)-e_model(t)||²`；
- 用真实演示的 EE 位姿/腕部图做验证；不用测试集调参。

### 6.3 实验矩阵

| 维度 | 取值 | 目的 |
|---|---|---|
| `H_c` | 3, 5, 8, 30 | 反馈周期 vs 稳定性 |
| `τ` | 0, 50, 100, 150ms | 延迟鲁棒性 |
| `K_p` | 0.3, 0.5, 0.8 | 增益裕度 |
| 扰动 | 位置/遮挡/背景/目标移动/人手 | 泛化/恢复 |
| 目标 | 固定/移动/透明/反光 | 可辨识性 |
| 任务族 | peg/hang/zip | 接触类型 |

每个组合至少 50 次仿真；报告成功率、收敛时间、超调、恢复率、p99。仿真只用于找稳定域和相对排序，不用于预测真机绝对成功率。

### 6.4 sim-to-real gap 预算

| 项 | 允许误差 | 超过后的动作 |
|---|---|---|
| 相机外参 | ≤2cm/2° | 重新标定；关闭 IBVS |
| 焦距尺度 | ≤10% | 用头双目深度；腕部只做粗对齐 |
| 延迟 | ≤30ms 估计误差 | 降增益/加 chunk |
| 目标位姿 | ≤5mm/2° | 只用腕部目标图 |
| 物体刚性 | 刚体 | 变形任务不启用伺服 |
| 光照/纹理 | 中等变化 | 用轮廓/深度，不用颜色 |

## 7. 竞赛策略

### 7.1 失败模式分诊

| 失败模式 | 典型任务 | 该投什么 | 不该投什么 |
|---|---|---|---|
| 最后接触/插入/挂/叠/拉链/锁 | PlugInEthernet、HangCup、ZipUp、StackBowls、Unlock、ArrangeTestTubes、ToolboxStorage | 视觉伺服 + 相对目标 + 接触相位 | 更大 VLA、更多语义数据 |
| 位置/人为干扰 | 5 类泛化轴；human_1/4 | 重定位 + 恢复 + 相对目标 | 固定轨迹、开环 chunk |
| 背景/干扰物/未见物品 | FruitSorting、ColorArrangement、OrganizeTools | VLA 数据增强/微调 + 局部 ROI | 纯几何伺服 |
| 变形/语义/长程 | FoldTowel、PackBag、SpellRobot、ConveyorSorting | VLA 基座 + 任务数据 | 6D 物体位姿网络 |

### 7.2 任务组合（先验）

- **A 档：伺服优先（19 个）**：T01 HangCup、T05 DisconnectEthernet、T09 ToolboxStorage、T10 PlugCharger、T12 Unlock、T13 ArrangeTestTubes、T14 OpenPillBottle、T17 OrganizeStationery、T18 PackBag、T19 ZipUp、T20 PaperCupStacking、T23 StoreRacket、T25 StackCups、T26 PlugInEthernet、T27 StackBowls、T28 StoreEarphones、T29 PackPhone、T31 OrganizePencilCase、T32 SyringeWaterTransfer。
- **B 档：VLA 优先（13 个）**：T02 FruitCollection、T03 PackDoll、T04 FruitSorting、T06 ColorArrangement、T07 PlacePhotoFrame、T08 OrganizeBookshelf、T11 PickOutBatteries、T15 OrganizeTools、T16 FoldTowel、T21 ArrangePlates、T22 SpellRobot、T24 ConveyorSorting、T30 RemovePinnedNote。
- **C 档：低投入/观察**：单任务通道里 `p_t` 接近 0 且失败在早期感知/抓取的任务；保留 VLA 基线，不投入伺服工程。

组合规则：

```text
priority_t = q_t * Δ_t / cost_t
```

- `q_t`：失败发生在最后 3 厘米的比例（先用语义先验，单任务通道后更新）；
- `Δ_t`：伺服条件增益（A/B 差值）；
- `cost_t`：工程/评测成本（目标库/标定/调参）。

先做 A 档中 `q_t` 最高、`cost_t` 最低的 3–5 个任务；不要一次铺 19 个。

### 7.3 单任务通道协议

| 项 | 设计 |
|---|---|
| 任务 | PlugInEthernet、HangCup、ZipUp、StackBowls、FoldTowel |
| 次数 | 每任务 5 次 A/B（servo off/on） |
| 初始条件 | 同一位置/背景；尽量配对 |
| 指标 | 成功率、步骤分、耗时、p99 延迟、恢复次数 |
| chunk | 先固定 5；通过后扫 3/8 |
| 通过 | ≥3/5 任务 +10pp；FoldTowel 不回归 >5pp |
| 失败 | 不提交 servo 版本；只保留离线分析 |

统计：

- 配对差值 `Δ_t = p_on - p_off`；5 次/任务只能看方向，不能看显著性；
- 汇总 5 任务用 bootstrap；报告 95% CI；
- 若 CI 跨 0，继续测或放弃；不要用 +1–2pp 做结论。

### 7.4 边际收益与预算

| 方案 | 成本（估算） | 预期收益 | 建议 |
|---|---|---|---|
| 官方 WLA 直接适配 | 1–2 人周 | 基线；可能 20–30% | 必做；先锁基线 |
| WLA action-head 微调 | 2–3 GPU 周 + 1 人周 | +1–3pp（未知） | 做；但不要指望它解决最后 3cm |
| CHUNK-SERVO | 3–4 人周 + 1 GPU 周 | A 档 +10–15pp → 全局 +3–5pp；human +1–2pp | 主投 |
| 完整世界模型 | 8+ GPU 周 | 不确定；延迟更差 | 不做 |
| 32 任务各训策略 | 规则禁止 | — | 不做 |

收益算术：

- A 档 19 任务各 +10pp → `19/32×10=+5.9pp`；各 +5pp → +3.0pp；
- human 轴 +10pp → +2pp（20% 权重）；
- 保守合计 +4–7pp；乐观 +8–10pp；
- 若只有 10 个任务生效，+3.1pp + human +2pp ≈ +5pp。

这些是设计目标，不是承诺；G3/G7 不过就不提交。

### 7.5 提交节奏

1. **W0**：官方 WLA + API adapter + chunk 30 基线；单任务通道跑 1 个任务，确认接口/`pivot`/token。
2. **W1**：安全基线提交（若允许多次）；锁“更早提交”tie-break。
3. **W2–W4**：伺服/目标库/仿真；单任务 A/B。
4. **W5**：chunk/gain 扫描；全量干跑。
5. **W6**：最终提交；保留回滚开关。

若只允许一次提交：跳过 W1，W5 后再交；不要用正式 320 trials 做未验证的 A/B。

## 8. 实验设计与门

### 8.1 离线

| 实验 | 数据 | 指标 | 门 |
|---|---|---|---|
| 目标检索 | 32 任务演示，按 session 划分 | top-5 几何有效 ≥80%；相对位姿 ≤5mm/2° | G1 |
| 相位分割 | 人工标签子集 | 边界 F1 ≥0.75 | G1 |
| 伺服回放 | 成功/失败演示 | 修正方向正确率、稳态误差 | G2 |
| 编辑检测 | 合成编辑 + 正常 | AUROC ≥0.85；误报 ≤5% | G4 |

### 8.2 仿真

| 实验 | 变量 | 指标 | 门 |
|---|---|---|---|
| 收敛 | `H_c`/`K`/`τ` | 横向 ≤2mm、深度 ≤3mm、2s ≥95% | G2 |
| 延迟 | `τ` 0–150ms | 超调、振荡、稳定域 | G2 |
| 扰动 | 位置/遮挡/背景/目标移动/人手 | 恢复率、检测延迟 | G4 |
| 消融 | 相对/绝对目标；5/30 chunk；IBVS/PBVS | 成功率、误差 | G7 |

### 8.3 真机单任务

| 项 | 设计 |
|---|---|
| 任务 | 5 个代表任务 |
| 次数 | 5 次 A/B |
| 指标 | 成功、步骤分、耗时、p99、恢复 |
| 统计 | 配对差值 + bootstrap 95% CI |
| 门 | ≥3/5 +10pp；FoldTowel 不回归 |

### 8.4 全量

| 项 | 设计 |
|---|---|
| 任务 | 32×10 |
| 端口 | N 个连续端口 |
| 指标 | 总平均成功率、步骤分、p99、timeout、内存 |
| 门 | 无端口串扰；reset 干净；内存不涨；p99 ≤150ms |

### 8.5 消融

1. 相对目标 vs 绝对目标（同任务/同初始条件）。
2. 5 步 chunk vs 30 步 chunk。
3. servo on/off。
4. edit recovery on/off。
5. IBVS vs PBVS vs 混合。
6. WLA Base vs WLA 微调。
7. 目标库 top-1 vs top-5 rerank。
8. 延迟补偿 on/off。

### 8.6 门 G0–G7

| 门 | 问题 | 通过标准 | 失败动作 |
|---|---|---|---|
| G0 | 腕部相机能否标定？ | 重投影 ≤5px；头双目 ROI 有效 ≥70% | 只用头双目 PBVS；腕部仅做 2D 粗对齐 |
| G1 | 演示检索是否可信？ | top-5 含几何有效目标 ≥80%；相对位姿误差 ≤5mm/2° | 改用任务级固定相对目标 |
| G2 | 仿真伺服是否收敛？ | 横向 ≤2mm、深度 ≤3mm、2s 内 ≥95%；RTT 0–150ms 稳定 | 降增益/加 chunk；只做 PBVS |
| G3 | 真机单任务是否涨点？ | 3/5 任务 +10pp；FoldTowel 不回归 | 不提交 servo 版本 |
| G4 | 人为干扰能否恢复？ | 检测 ≤200ms；仿真恢复 ≥70% | 只做离线标注/不线上触发 |
| G5 | 延迟是否可接受？ | p99 ≤150ms；timeout 不升 | 加 chunk/降分辨率/关伺服 |
| G6 | 32 任务干跑是否稳定？ | N 端口隔离、reset 干净、内存不涨 | 回退基线 |
| G7 | 消融是否支持因果？ | 相对目标 > 绝对目标；5 步 > 30 步；伺服 > 无伺服 | 保留有效部分，砍掉无效部分 |

## 9. 资源与时间表

| 阶段 | 时间 | 交付 | 退出条件 |
|---|---:|---|---|
| P0 基线/接口 | 1 周 | WLA + API adapter；token/`pivot` 验证；chunk 30 基线 | 单任务通道 1 任务跑通 |
| P1 标定/目标库 | 2 周 | 腕部标定；32 任务目标库；检索评测 | G0/G1 |
| P2 伺服/仿真 | 2 周 | IBVS/PBVS；延迟/增益扫描；扰动套件 | G2/G4 |
| P3 集成/单任务 | 2 周 | 双频执行；状态机；5 任务 A/B | G3/G5 |
| P4 全量干跑 | 1 周 | 32×10 干跑；N 端口；p99/内存 | G6 |
| P5 提交 | 1 周 | 提交包、合规说明、回滚开关 | G7 + 全部门 |

**算力**：

- 1×24GB GPU：WLA Base 微调/单端口推理；
- 1×40GB/80GB GPU（可选）：多端口共享 VLA server/批处理；
- 16–32 CPU 核：伺服/目标检索/离线回放；
- 存储：视频缓存 1–2TB（估算）；只缓存关键帧/腕部 ROI 可降到 <100GB。

**人员**：

- 1 人：视觉伺服/标定/几何；
- 1 人：WLA 微调/推理/部署；
- 1 人：评测/统计/竞赛策略；
- 可兼职；总计 9–10 周。

## 10. 风险与合规

### 10.1 单模型合规的三种模式

| 模式 | 做法 | 风险 | 建议 |
|---|---|---|---|
| C1 离线标注 | GEO-RESIDUAL 只离线生成相位/接触标签；线上只有 VLA | 最低 | 保守首选 |
| C2 确定性控制器 | 伺服是几何/控制律，无学习权重；VLA 是唯一学习模型 | 低；需向官方说明 | 主推 |
| C3 同 checkpoint 特征 | 目标描述子用 VLA 同一 checkpoint 的 encoder，不加载第二个模型 | 低–中；需说明 | 需要强描述子时用 |

禁止：加载第二个学习策略/残差网络/独立视觉编码器做在线决策。

### 10.2 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| 单模型解释 | 被判定为第二个模型 | C1/C2/C3；提交材料写清楚；伺服无学习权重 |
| 远程 RTT 高 | 伺服带宽不足 | 5 步 chunk；RTT 测量；预测补偿；回退 chunk 8–10 |
| 腕部无内参 | 2D 伺服不准 | 一次性棋盘格标定；D435 先验；头双目 PBVS 兜底 |
| 目标检索 mismatch | 错误目标 | 任务/阶段/相对位姿过滤；top-k 重打分；置信度低回退 |
| 透明/反光/变形 | 深度/特征失败 | 只对刚体任务启用；腕部 2D + 夹爪滞止兜底 |
| 标定漂移/换机器人 | 残差变大 | 每机器人一次重投影校准；夹爪 PnP 自标定；误差大关伺服 |
| 人为干扰不在视野 | 漏检 | 本体/夹爪/任务状态兜底；不声称 100% |
| 安全 | 回撤/重抓碰撞 | 限速/限幅/最大重试；编辑检测即停 |
| 评测噪声 | +1–2pp 假阳性 | 配对 A/B、bootstrap、重复实验；320 trials SE≈2.4pp |
| 数据泄漏 | 离线指标虚高 | 按 session/物体/背景分组划分；相邻帧不跨 split |
| `pivot` 语义不一致 | 动作被拒/机器人不动 | 先用 `example_env.py`/单任务通道验证；保留零 pivot 回退 |
| 提交次数限制 | 无法多次 A/B | 邮件确认；单任务通道先验证；一次提交则保守 |

## 11. 来源

官方/数据（检索日期均为 **2026-10-28**）：

- UniBot 世界挑战赛官网：<https://unibot.unitree.com/>
- 赛事页：<https://unibot.unitree.com/challenges.html>
- 排行榜页：<https://unibot.unitree.com/leaderboard.html>
- 排行榜 JSON：<https://unibot.unitree.com/leaderboard_data.json>
- 详情页示例：<https://unibot.unitree.com/details.html?model=MolmoAct2&user=DexHacker>
- 提交模板：<https://github.com/unitreerobotics/unibot_submission>
- 提交 README：<https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md>
- 参赛手册（飞书，`r.jina.ai` 抓取）：<https://r.jina.ai/https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh>
- 数据集集合：<https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset>
- HangCup 示例：<https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup>
- WLA 仓库：<https://github.com/unitreerobotics/unifolm-wla>
- WLA 动作/状态规范：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/robot_action_state_processing_en.md>
- WLA 微调文档：<https://github.com/unitreerobotics/unifolm-wla/blob/main/docs/train_action_expert_en.md>
- WLA Base 权重：<https://huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base>
- VLA 仓库：<https://github.com/unitreerobotics/unifolm-vla>
- WMA 仓库：<https://github.com/unitreerobotics/unifolm-world-model-action>
- 官方仿真：<https://github.com/unitreerobotics/unitree_sim_isaaclab>、<https://github.com/unitreerobotics/unitree_mujoco>
- 提交示例：<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_policy.py>、<https://github.com/unitreerobotics/unibot_submission/blob/main/example/example_env.py>

相关论文/工作（按标题检索；本报告不依赖其具体数值）：

- D²-VLA：双记忆双频 VLA，arXiv 2609.34792。
- VLaRL：仿真训练 latent-conditioned residual RL，arXiv 2609.30868。
- VGM-VS：视觉几何模型做高精度视觉伺服，arXiv 2609.28312。
- Action Chunk Scheduling：chunk 执行长度与反应性，arXiv 2608.00337。
- Catch Me If You Can：实时反馈去噪，公开摘要称端到端 71ms、反馈 1.95ms，arXiv 2609.21022。
- Real-Time Execution of Action Chunking Flow Policies（RTC），arXiv 2506.07339。
- ResiP：残差 RL 做精确视觉装配，arXiv 2407.16677。
- Track2Act：ECCV 2024。
- 第 10 轮 FACT-VLA、第 11 轮 GEO-RESIDUAL 及历史候选（PRISM、TVC、CARE-VLA、PACT、CO-HASM、SODT、SCOPE、PSALM、CORE-VLA）：本报告在其上做控制层增量，不重复其状态机/评分卡/位姿图主题。

## 12. 一句话押注

**用官方 WLA 做 30 步规划，用 33k 成功演示检索“目标-夹爪相对位姿”，用无学习权重的视觉伺服每 5 步闭环一次，用轻量数字孪生标定 RTT/增益，用单任务通道决定把工程投到哪些任务——在不违反单模型规则的前提下，把最后 3 厘米从开环变成闭环。**
<!-- ARTIFACT:END -->
