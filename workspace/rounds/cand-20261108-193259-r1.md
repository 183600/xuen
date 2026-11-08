# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 33 轮 · 现实校准：接口暴露边界下的「机器人基础模型 × 技术融合 × 任务分解」

## 0. 联网核实结果（先事实，后推理；检索口径 2026-11-08）

本轮开工先按任务要求做外部核实，得到三条**改变全局的事实**：

- **事实 1（接口 / github unitreerobotics/unibot_submission，2026-11-08 抓取）**：策略以 websocket + msgpack-numpy 远程接入，评测方为客户端、选手为服务端（`PolicyService`，端口 8765 起）。可观测键（obs catalog）**只有**：4 路相机（`cam_left_high` / `cam_right_high` / `cam_left_wrist` / `cam_right_wrist`，480×640×3 uint8）、双臂关节（`left/right_arm` [7]）、双末端位姿（`*_ee_pose_gripper_base` [6]）、双夹爪开合（[1]）、下身本体（`lower_body` [15]）、语言指令（str）。动作键为：joint 或 ee **二选一**控制空间 + 共享的左右夹爪 + `pivot`[7]；动作以 chunk（`action_chunk_size=T_a`）返回；`obs_delta_indices` 决定"发哪些观测 + 每键时序堆叠"；`image_resize` 决定分辨率；`token` 双向校验；真机评测跨 **N 台机器人**，须暴露 **N 个连续端口（8765 起）**，并要求逐端口并发、逐端口状态隔离。
- **事实 2（数据 / HF collection unitreerobotics/unibot-v1-challenge-dataset）**：32 个任务的 LeRobot v3.0 仓库，`robot_type=unitree_g1`，30 fps，480×640 AV1；单任务约 ~1000 episodes（例：`G1_Dex1_HangCup` = 1043 episodes / 194564 帧 / 均值 ~13.7s）。挑战赛页口径：**32 任务 / 32000 episodes / 169 小时**。数据相机键为 `head_stereo_left/right` + `wrist_left/right`；本体键含 arms/grippers/lower_body、ee_pose（base 与 torso 两系）、waist、d435 等；动作键含 arms/grippers/lower_body/ee_pose/base_command/pivot/gripper_controls。
- **事实 3（榜单与规则）**：challenges/leaderboard/runs 页面在 2026-11-08 均为 "Coming Soon"（JS 动态、无可读数据），故用户前提"**榜首成功率不到 30%**"**本轮无法核实**（诚实标注）。参赛手册（feishu 文档）返回 `{"code":5,"message":"Login Required"}`，**登录墙拦截，未取得全文**；参赛流程仅从公开页读到摘要（邮件注册 → 提交模型 → 预约时段 → 本地部署 obs→action API → 真机评测 → 成功率+步骤分排名）。"5 类泛化场景"亦未从公开页核实，暂作**待验假设**（按用户口径：位置/干扰物/背景/未见物品/人为干扰）。

**结论：UniBot 指向确认无误（宇树科技 unitree.com 的 UniBot-V1 挑战赛），无需改指。但本轮外审暴露了一个比任何"新灵感词"都更优先的架构性错配，必须先修。**

## 1. 自我审查：前 32 轮的架构性错配（诚实登记，不掩饰）

- **错配 A（致命）：力觉/触觉通道在官方接口层不可达。** 第 31–32 轮的 IP-16（动量观测器 `r_obs`、载荷状态位 `l_load`、`μ̂_s` 材质表）与 IP-17（指尖触觉阵列 `τ_tac`、`tactile_alarm`、力觉 fail-safe OR）全部以"能读到关节力矩 / 指尖力"为前提；但官方 obs catalog **没有任何力矩/触觉/电流/接触键**，且选手只运行**远端策略服务器**，无法为宇树评测机队加装传感器。→ 这两项在**官方赛道上不可实现**，从主链路退役。
- **错配 B：安全盾的"力反馈闭环"前提不成立。** CBF-QP fallback、停止距离方程、ISO/TS 15066 `δ_allow`、执行器升力时限，都假设策略能实时读回接触/力并改写下一步。官方是"obs → action chunk"的**开环逐块**交互，且明示"延迟与动作统计规律会被记录为可信度指标"。→ 安全须重定义为：**动作块级的事前约束 + 返回动作统计规律的稳定性**，而非控制回路内的力反馈盾。
- **错配 C：社会/文化/对话维度缺少观测支撑。** `κ̂`、`h_γ`、`w_grasp`、社会代价、文化条件化——都需要交互对象状态或人类反馈通道，obs catalog 都没有。→ 退役。
- **保留资产（与通道无关、仍有效）**：IP-2（对齐得分点）、IP-3（本地评测）、IP-4（多端口部署/回滚）、IP-8（步骤分效率）、IP-10（成本记账）。第 32 轮的 **DELAY-LEDGER 思想不废**，但语义由"控制回路时延账本"改写为"**推理时延 SLO**"（见 IP-25）。

> 一句话自审：前 32 轮把一场"视觉+本体+语言的模仿学习基础模型赛"误当成了"力控安全盾赛"。本轮不是推倒重来，而是**把主链路从力觉安全盾重锚到机器人基础模型**，并把错配项诚实降级。

## 2. 灵感词 → 重锚后的三条主线

- 「**机器人基础模型**」→ **IP-21 UNIBOT-RFM**：单一参数共享的 VLA 覆盖全部 32 任务；双系统（System-2 语言/子目标规划 + System-1 少步流匹配动作专家）；语言条件化 + 动作分块。参照 GR00T N1（2503.14734，双系统人形基础模型）、G0.5（2608.11739，单一自回归流同时出推理与动作 token）、Concertina（2611.07513，认知与操作同体）。
- 「**技术融合**」→ **IP-22 TRI-FUSE**：三源 token 级融合 = 视觉（4 相机，含立体伪深度）× 本体（关节+ee 位姿+夹爪+下身，token 化）× 语言（指令/子目标）；可选 **world-model 辅助头**提供稠密监督（DSWAM 2607.04927 路线）。融合在 token 级而非简单 concat。
- 「**任务分解**」→ **IP-23 TASK-DAG**：用 32 任务的**得分点（scoring steps）**反推子目标分段做伪标签，训练"子目标流"作为 System-2 输出，System-1 以子目标为条件执行；直接对齐步骤分。参照 Beyond Flat Policies（2608.05999）、HAF 分层动作（2608.16837）、CoEvolve 可执行代码策略（2610.23288）。

## 3. 三条主线的耦合与关键决断

- **耦合**：TASK-DAG 产出"当前子目标"注入 TRI-FUSE 的语言侧 token；TRI-FUSE 把多视图+本体压成 System-2 可用表征；UNIBOT-RFM 的 System-1 以该表征+本体+噪声动作块为输入输出动作块。**技术融合管"看什么/是什么"，任务分解管"现在该做什么"，基础模型管"怎么动"。**
- **关键决断**：
  1. **控制空间**：以 `ee` 为主（跨位姿 / 未见物更可迁移），同时训练 `joint` 头做一致性正则与备用；两空间共享躯干表征。数据两套动作齐全（`action.left_arm` 与 `action.left_ee_pose_gripper_base`），据此做**双表示一致性损失**（技术融合的又一处落点）。
  2. **实时动作头**：为满足真机节拍，动作头用 flow-matching **蒸馏到 1–4 步**（GR00T N1.7 drifting head，2609.18108），而非 10–100 步扩散。
  3. **失败预警替代安全盾**：以 OpenVLA 失败前内部激活探针（2606.29699）为蓝本，做**仅依赖可观测状态**的 failure monitor，触发重规划/保守动作，替代力反馈制动。
  4. **数据统一 schema**：建立 dataset 键 ↔ API 键的显式映射（`head_stereo_left↔cam_left_high`、`wrist_left↔cam_left_wrist` 等），并核实立体外参与图像校正（未确认 → A9）。

## 4. 本轮最大风险一句话

最大风险不在模型，而在**接口映射与实时性**：数据集相机名/分辨率与 API 键的语义对应（尤其"头立体 vs 高位相机"、腕相机内参）若映射错，训练-推理分布错位会系统性压低成功率；同时"N 端口并发 + 30 fps 控制节拍"下，若推理时延或动作统计规律异常，会**同时伤成功率与可信度指标**——须以 IP-3 本地闭环 + IP-25 时延 SLO 先行验证。

## 一句话结论

本轮最值得押注：把 32 任务统一训成**单个双系统 VLA**（System-2 子目标规划 + System-1 少步流匹配动作头，多视图×本体×语言 token 级融合，ee/joint 双表示），用"**得分点**"监督的任务分解切长程任务，并以可观测状态的**失败预警**替代已不可达的力觉安全盾。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 33 轮产物 · 创新点清单 v10：现实校准版 —— UNIBOT-RFM（机器人基础模型 × 技术融合 × 任务分解）

## 0. 结论

本轮按联网核实（2026-11-08）执行**主链路重锚 + 诚实修剪**：清单由 v9（20 项，含力觉/触觉/社会/对话扩展）收敛为 **v10（旗舰 1 + 核心 5 + 保留 6 + 退役 8）**。

- **旗舰 IP-21 UNIBOT-RFM（P0，新增）**：单一双系统 VLA 覆盖全部 32 任务。依据：官方接口与数据**只**支撑"视觉 + 本体 + 语言 → 动作"的模仿学习范式。
- **核心新增**：IP-22 TRI-FUSE（技术融合：多视图×本体×语言 token 级融合 + world-model 辅助）、IP-23 TASK-DAG（任务分解：得分点驱动的子目标分段 + 分层策略）、IP-24 FAILURE-MONITOR（可观测状态失败预警，替代力觉安全盾）、IP-25 LATENCY-SLO（推理时延/多端口/动作平滑，DELAY-LEDGER 语义改写）、IP-26 GENERALIZE-SUITE（泛化增广与评测）。
- **退役并登记原因**：IP-13 / IP-16 / IP-17 / IP-18 / IP-19 / IP-20（力觉/触觉/社会/对话——接口不可达）；IP-1（桌面任务无 SLAM）；IP-11 社交意图层退役（其"干扰鲁棒性"外延并入 IP-26）。
- **保留**：IP-2 SCORE-ALIGN、IP-3 LOCAL-EVAL、IP-4 SUBMISSION-OPS（重构为多端口）、IP-8 STEP-EFF、IP-9 SWARM-DECODE、IP-10 COST-LADDER。
- **净效果**：算力/工程从"力觉+触觉+时延+分割四合一"大幅回收，集中投入"数据统一 + 基础模型 + 任务分解 + 接口工程"。
- **路线无关原则**：任何新想法**不得依赖官方未暴露的通道**（力/触觉/社会反馈）；做不到就退役，不许"假设能读到"。

## 1. 事实卡（联网核实，检索日期 2026-11-08）

- **F24（官方接口）**：`github.com/unitreerobotics/unibot_submission`。obs 键见 §3.1；action 控制空间 `joint`/`ee` 互斥 + 共享 `left/right_gripper` + `pivot[7]`；`action_chunk_size≥1` 前导时间轴；`obs_delta_indices` 决定发送键集合与时序堆叠（offset ≤0、严格递增，缺帧用首帧补齐）；`image_resize` 决定分辨率（缺省 480×640）；`token` 双向校验；N 机器人 → 端口 `8765..8765+N-1`，须并发 + 状态隔离；延迟与动作统计规律被记录为**可信度指标**。
- **F25（数据集结构）**：LeRobot `v3.0`，`robot_type=unitree_g1`，30 fps，480×640 AV1；obs 相机 `head_stereo_left/right` + `wrist_left/right`；obs 本体 arms[7]×2、grippers[1]×2、lower_body[15]、ee_pose(base/torso)[6]、waist[3]；action arms/grippers/lower_body/ee_pose/base_command[4]/pivot[7]/gripper_controls[4]。例：`G1_Dex1_HangCup` 1043 episodes / 194564 帧 / ~13.7s 均值 / ~410 帧每 episode。
- **F26（32 任务清单，来自 HF collection）**：HangCup、ArrangePlates、ArrangeTestTubes、ZipUp、ColorArrangement、Unlock、DisconnectEthernet、ConveyorSorting、FruitCollection、FoldTowel、OrganizeBookshelf、FruitSorting、SpellRobot、OrganizePencilCase、OrganizeStationery、StackBowls、StoreCups、OrganizeTools、PackDoll、PackBag、PackPhone、StoreEarphones、StorePaddle、PaperCupStacking、PickOutBatteries、ToolboxStorage、PlugCharger、SyringeWaterTransfer、PlugInEthernet、PlacePhotoFrame、RemovePinnedNote、PourOutMedicine（共 32）。总计口径 32000 episodes / 169 h（challenges.html）。
- **F27（榜单，未核实）**：leaderboard/runs 均为 "Coming Soon"（2026-11-08）；"榜首成功率 <30%"**无法核实**。
- **F28（规则，未获取）**：参赛手册（feishu）返回 `code:5 Login Required`；仅公开流程摘要可得（challenges.html）。
- **F29（形态先验，文献级）**：G1 类人形——双臂 7-DOF、三自由度腰（yaw/roll/pitch）、`lower_body`[15] 含双腿(6+6)+腰(3)；`pivot`[7] ≈ 底盘/腰的复合命令（vx, vy, angle_z, p1..p3, height，据 stats 推断，待 A11 核实）。

**行动项**：A9 相机键/内外参/校正映射核实（最高优先）；A10 参赛手册全文获取（需账号）；A11 控制节拍/评测超时/pivot 语义核实；A12 32 任务**得分点 rubric** 文本收集（IP-23 前置）；A13 本地复现一份 LeRobot→obs/action 回放闭环（IP-3 前置）。

## 2. 创新点清单 v10 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-21 | **UNIBOT-RFM** | 单一双系统 VLA 覆盖 32 任务（System-2 规划 + System-1 少步流匹配动作头） | **P0** | A9,A13 | 机器人基础模型 | 算力(重,一次性) | 主成功率 | **新增/旗舰** |
| IP-22 | TRI-FUSE | 多视图×本体×语言 token 级融合 + 立体伪深度 + world-model 辅助头（可选） | P0 | IP-21 | **技术融合** | 算力(中) | 未见物/位置泛化 | 新增 |
| IP-23 | TASK-DAG | 得分点驱动子目标分段 + 分层策略，对齐步骤分 | P1 | A12,IP-21 | **任务分解** | 数据(标注轻) | 步骤分 + 长程任务 | 新增 |
| IP-24 | FAILURE-MONITOR | 内部激活失败预警（可观测状态）+ 重规划触发，替代力觉安全盾 | P1 | IP-21 | 泛化监控×安全 | 算力(轻) | 鲁棒性/可信度 | 新增 |
| IP-25 | LATENCY-SLO | 推理时延 SLO + 少步动作头 + QAT + N 端口并发 + 动作平滑（DELAY-LEDGER 改写） | P0 | IP-4,A11 | 接口工程/通信延迟 | 算力(部署机) | 掉请求→0、可信度 | 新增 |
| IP-26 | GENERALIZE-SUITE | 位置/干扰/背景/未见物/人为干扰五轴的增广与评测套件 | P1 | IP-2,IP-3 | 泛化能力 | 数据(近零) | 全场景 | 新增 |
| IP-2 | SCORE-ALIGN v4 | 对齐 32 任务得分点与步骤分（原力觉软通道→rubric 对齐） | P0 | 无 | 评测指标 | 数据(近零) | 步骤分 | 保留/重锚 |
| IP-3 | LOCAL-EVAL | `run_server/run_client` 本地闭环 + 回放复现 | P0 | IP-2,A13 | 评测基准 | 算力(1 GPU) | 迭代速度=生命线 | 保留 |
| IP-4 | SUBMISSION-OPS v3 | 多端口（Approach1/2）+ 单元状态隔离 + 版本回滚 | P0 | 无 | 接口工程 | 算力(部署机) | 掉请求→0 | 保留/重构 |
| IP-8 | STEP-EFF | 步骤分效率（少步动作头 + 早停 + 平滑） | P1 | IP-21 | 步骤分 | 零额外 | 步骤分 | 保留 |
| IP-9 | SWARM-DECODE | 集成/自洽投票 + 蒸馏到单模型 | P1 | IP-2 | 泛化能力 | 算力(一次性) | 全场景 +2~5pt | 保留 |
| IP-10 | COST-LADDER | 三账户记账（训练/服务/工程） | P0(纪律) | 无 | 成本控制 | 全账户 | 防负 ROI | 保留 |
| IP-1 | SLAM-MAP | 桌面任务无 SLAM 需求 | — | — | SLAM | — | — | **退役** |
| IP-11 | INTENT-GUARD | 无人类反馈/交互通道 | — | — | 手势/共享控制 | — | — | **退役（并入 IP-26）** |
| IP-13 | SOCIAL-MOTION-LITE | 无社会交互观测 | — | — | 运动×社会 | — | — | **退役** |
| IP-16 | FORCE-CONTINUAL-LITE | **接口无力矩/触觉** → 不可实现 | — | — | 力矩/持续学习 | — | — | **退役** |
| IP-17 | SEG-TAC-SYNC-LITE | **接口无触觉/力** → 不可实现 | — | — | 通信延迟×触觉×分割 | — | — | **退役（时延思想→IP-25）** |
| IP-18/19/20 | 对话调度/几何细化/可靠性记账 | 无对话/交互通道 | — | — | 对话管理 | — | — | **退役** |

## 3. 重点展开：IP-21 UNIBOT-RFM（旗舰）

### 3.1 接口契约（policy 侧，照官方 schema）

| 观察键 | 形状 | 说明 |
|---|---|---|
| `observation.images.cam_left_high` / `cam_right_high` | [480,640,3] u8 | 头部（近似立体）高位相机 |
| `observation.images.cam_left_wrist` / `cam_right_wrist` | [480,640,3] u8 | 双腕相机 |
| `observation.state.left_arm` / `right_arm` | [7] f32 | 关节位置（shoulder×3, elbow, wrist×3） |
| `observation.state.*_ee_pose_gripper_base` | [6] f32 | 末端位姿 xyz+rpy（base 系） |
| `observation.state.left_gripper` / `right_gripper` | [1] f32 | 夹爪开合（0~4.5 量纲，据 stats） |
| `observation.state.lower_body` | [15] f32 | 双腿 6+6 + 腰 3 |
| `observation.language` | str | 任务指令（单串，无时间轴，offset 固定 [0]） |

动作键（`control_space` 二选一 + 共享键）：`action.left/right_gripper[1]`、`action.pivot[7]`，以及 joint=`action.left/right_arm[7]` 或 ee=`action.left/right_ee_pose_gripper_base[6]`。

### 3.2 数据统一 schema（A9 前置，最高风险）

| 数据集键 | API 键 | 处理 |
|---|---|---|
| `head_stereo_left` / `head_stereo_right` | `cam_left_high` / `cam_right_high` | 图像校正/去畸变（若已 rectified 则近似恒等）；建立立体基线→伪深度 |
| `wrist_left` / `wrist_right` | `cam_left_wrist` / `cam_right_wrist` | 保持内参 |
| `left_arm`/`right_arm`（obs） | 同名 state | 单位/零位核对 |
| `*_ee_pose_gripper_base`（obs/act） | 同名 state/action | FK 复核（与 joints 一致） |
| `left/right_gripper`（obs/act） | 同名 | 量纲映射 |
| `lower_body`（obs） | 同名 | 15 维直通 |
| `base_command[4]` / `pivot[7]` | `action.pivot[7]` | 语义对齐（A11） |
| `left/right_ee_pose_gripper_torso` | 辅助监督 | torso 系一致性正则（可选） |

**风险点**：字典序与语义差异（"high" 是否即立体头）、图像是否 rectified、夹爪量纲、pivot 语义——任一错位都会造成训练-推理分布错配，须 A9 用少量真机/回放校验。

### 3.3 架构（双系统 + 双表示动作头）

```
输入: 4×RGB(可选 resize) ─┐
      本体向量(arms/ee/grip/lower_body) ─┤→ TRI-FUSE token 编码器
      语言指令 + 上一子目标 ──────────────┘
                │
         System-2 (VLM backbone, LoRA): 语言 grounding + 子目标 token z_t (TASK-DAG)
                │
         System-1 (少步流匹配动作专家): 输入 [视觉token, 本体token, z_t, 噪声动作块] → 动作块 chunk (T_a,·)
                │
         双表示: 同时输出 joint 头与 ee 头（一致性损失 L_cons）
```

### 3.4 离线训练伪代码

```python
def build_release_v10():
    # 1) 数据统一：32 个 LeRobot v3 仓库 → API schema
    tasks = load_task_list()                     # F26 的 32 个 G1_Dex1_*
    D = []
    for t in tasks:
        ds = LeRobotDataset(f"unitreerobotics/{t}")   # 30fps, 480x640
        D += remap_to_api_schema(ds, MAP, rectify=A9_params)

    # 2) 子目标伪标签（TASK-DAG）：得分点 rubric 反推分段
    D = pseudo_segment_by_rubric(D, rubric=load_rubric(tasks))   # 每段一个子目标

    # 3) 训练：冻结/ LoRA 微调 VLM，训练融合器 + 少步动作头
    backbone = load_pretrained_vlm()
    fuse     = TriFuseEncoder(depth_from_stereo=True, proprio_tokens=True)
    system2  = SubgoalPlanner(backbone, rank=LORA_R)
    system1  = FlowActionExpert(steps=4, chunk=T_a, dual=("joint","ee"))
    wmhead   = WorldModelAux()                    # 可选（IP-22/DWAM 路线）
    for batch in D:
        f   = fuse(batch.images, batch.proprio, batch.lang)
        z_t = system2(f, batch.lang, batch.prev_subgoal)
        a_hat = system1.sample_train(f, batch.proprio, z_t, batch.action)
        loss = flow_matching_loss(a_hat, batch.action) \
             + LAM_ROBUST * robust_loss(system1, augment(batch)) \
             + LAM_CONS   * consistency(system1.joint, system1.ee) \
             + LAM_SUB    * subgoal_ce(system2, batch.subgoal) \
             + LAM_AUX    * wm_loss(wmhead, batch)          # 可关
        update(system2.lora, fuse, system1, loss)
    # 4) 失败预警探针（IP-24）：冻结 backbone，在分布移位子集上拟合线性探针
    probe = fit_failure_probe(frozen=system2, data=shift_subset(D))
    return fuse, system2, system1, probe
```

### 3.5 在线服务伪代码（N 端口，共用模型 + 状态隔离）

```python
class UniBotPolicy:
    def metadata(self):
        return {"control_space":"ee",
                "obs_delta_indices":{"observation.language":[0],
                    "observation.images.cam_left_high":[-2,0],
                    "observation.images.cam_left_wrist":[-2,0],
                    # ... 其余同；负 offset 提供短时序上下文
                    },
                "image_resize":{"observation.images.cam_left_wrist":[128,128], "..."},
                "action_chunk_size": T_a, "token": TOKEN}

    def get_action(self, obs):
        assert obs["meta"]  # token 校验由框架完成
        f = self.fuse(obs.images, obs.proprio, obs.lang)
        if self._steps_since_plan % K_PLAN == 0:          # 子目标不必每步重估
            self.z = self.system2(f, obs.lang, self.z)     # TASK-DAG
        chunk = self.system1.sample(f, obs.proprio, self.z, steps=1..4)
        chunk = temporal_smooth(chunk)                     # 动作平滑（可信度）
        chunk = clip_to_limits(chunk)                      # 关节/位姿限幅
        if self.probe(f) > TAU_FAIL:                       # IP-24 失败预警
            chunk = self.recover_or_replan(chunk, f)
        return pack(chunk, token=TOKEN)

    def reset(self):
        self.z = None; self._steps_since_plan = 0          # 每端口独立状态
```

> 多端口：Approach 1（每端口独立进程/副本，稳）或 Approach 2（共享推理后端 + 并发批处理 + 逐端口状态隔离）。IP-25 给出 SLO 与实现细则。

### 3.6 成本与复杂度（相对 v9 回收）

- 训练一次性：预估 **2–4 GPU·周**（VLM LoRA + 少步动作头 + 融合器；world-model 辅助按算力开关），较 v9 的"力觉+触觉+分割"组合更聚焦但数据规模大（~32k episodes / 169h）。
- 服务：**<100 ms/步（P99）**为目标（视 GPU），T_a 覆盖一拍；N 端口并发按 GPU 数扩展。
- 内存/显存：主力在 VLM backbone；量化 + 一步动作头是满足节拍的关键（IP-25）。

## 4. 其余核心项（简版设计）

- **IP-22 TRI-FUSE**：视觉侧 token 化 4 视图并做**跨视图注意力**；立体基线产出伪深度 token（未见物/位置泛化的关键）；本体向量经 MLP→token 与视觉/语言拼接；可选 world-model 头在潜空间预测下一帧/子目标变化作为稠密监督（DSWAM 2607.04927）。**token 级融合 ≠ concat**（消融 E35）。
- **IP-23 TASK-DAG**：System-2 输出离散子目标 `z_t`；用得分点 rubric + 示范分段得到弱标签（change-point/夹爪开合/物体位移作为分段线索）；长程任务（如 OrganizeBookshelf、PackBag、FoldTowel）收益最大；对齐步骤分。参照 2608.05999 / 2608.16837 / 2610.23288。
- **IP-24 FAILURE-MONITOR**：冻结网络、记录每步某层 MLP 激活，拟合线性探针（2606.29699 报告失败前 AUROC 0.97 级）；探针触发 → 降低动作幅度 / 回退到上一安全块 / 请求重规划（**只依赖可观测状态**，不做力反馈）。fail-safe 默认：探针不确定 → 保守动作（慢速小块），不作激进探索。
- **IP-25 LATENCY-SLO**：把 DELAY-LEDGER 从"控制回路时延"改写为"**推理时延账本**"——每步 P50/P99 时延、chunk 吞吐、N 端口并发下的排队；手段：少步动作头（1–4 步）、QAT（LoopQ 2611.05093 / 2611.06710 佐证量化与内核优化的交互）、CUDA graph、请求批处理；返回动作做**统计规律整形**（平滑、限幅、避免离群），因为可信度指标会看这些。
- **IP-26 GENERALIZE-SUITE**：五轴增广与评测——位置（初始位姿扰动）、干扰物（桌面杂波）、背景（纹理/光照）、未见物（留出物体/类别）、人为干扰（评测中的人手入镜/移动物体）。数据侧用域随机化 + 指令改写（指令泛化）；评测侧按 F27 待核实的榜单口径分轴报告。

## 5. 实验设计

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E30 数据统一 sanity | 走 A9 映射，训练小模型并做离线动作 MSE；接头立体伪深度 | 动作 MSE、子目标准确率 | 映射错位可被检出（错映射 MSE 显著更高） |
| E31 接口闭环 | `run_server.py`+`run_client.py` 端到端；多端口并发 | token verified、无 ACTION REJECTED、逐端口隔离 | 全绿 |
| E32 泛化套件 | IP-26 五轴，留出集/真机（若可得） | 分轴成功率 | 五轴不回退；OOD 轴有可解释降幅 |
| E33 时延 SLO | N 端口（N=1/3）并发压测 | P50/P99 时延、动作离群率 | P99 < SLO；离群率 < 阈值 |
| E34 失败预警 | 分布移位子集 + 探针 | 失败步前 AUROC/AUPRC | AUROC ≥ 0.9（对标 2606.29699） |
| E35 消融 | concat vs TRI-FUSE；单表示 vs 双表示；flat vs TASK-DAG；扩散 vs 少步 | 成功率/步骤分/时延 | 各分项正贡献 |

**降级机制**：A9 映射存疑 → 冻结对应相机通道（退化为 3 视图或纯本体+腕）；world-model 辅助不过 → 关闭（无负收益）；IP-24 探针 AUROC 不足 → 仅遥测不介入；少步动作头精度不够 → 增加步数（时延换精度）；TASK-DAG 子目标不稳 → 退化为 flat 策略（=IP-21 基础版）。

## 6. 风险登记簿

| 风险 | 等级 | 缓解 |
|---|---|---|
| **相机键/内外参映射错位（A9）——训练-推理分布错配** | **高** | A9 用真机/回放校验 + 逐通道消融 + 映射错位自动检测（E30）；存疑则冻结该通道 |
| **推理时延/动作统计规律异常（伤成功率与可信度）** | 高 | IP-25 SLO + 少步动作头 + QAT + 平滑/限幅 + E33 压测 |
| 得分点 rubric 不可得（A12）→ 子目标弱标签噪声 | 中高 | 退化为示范分段（change-point/夹爪/物体位移）；TASK-DAG 可关 |
| 榜单口径未知（F27）/规则未读（F28）→ 目标错配 | 中高 | A10 获取手册；先按"成功率+步骤分"通用假设；预注册评测口径 |
| 数据规模与算力（169h/32k episodes） | 中高 | LoRA + 少步动作头 + 分级训练；world-model 按算力开关 |
| 多端口状态隔离/并发 | 中 | Approach1 稳妥；Approach2 加锁/批处理；E31 专项 |
| VLM 泛化到未见物/背景 | 中 | IP-26 增广 + IP-22 伪深度 + IP-24 预警 |
| 长程任务中间失败难恢复 | 中 | TASK-DAG 子目标重规划 + IP-24 触发重试 |
| 关节/位姿限幅与坐标系统一 | 中 | clip + FK 一致性 + 双表示一致性损失 |
| 立体伪深度精度 | 中低 | 仅作辅助 token；缺省回退单目 |
| 量化精度损失 | 中 | QAT + 校准集 + 重测（E33/E35） |
| pivot/底盘语义未核实（A11） | 中低 | 先固定 pivot 默认值，核实后放开 |

## 7. 来源清单（引用口径：2026-11-08）

- **官方/数据（一手）**：
  - S1 挑战赛官网 `https://unibot.unitree.com`（首页/挑战赛/排行榜/运行记录，2026-11-08 抓取）——32 任务/32000 episodes/169h；榜单 Coming Soon。
  - S2 提交模板 `https://github.com/unitreerobotics/unibot_submission`（README, README.zh.md, example/*.py, policy/，2026-11-08 抓取）——接口契约、控制空间、多端口、可信度指标。
  - S3 数据集 collection `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset` 与单任务仓 `unitreerobotics/G1_Dex1_HangCup`（meta/info.json, README.md, meta/stats.json，2026-11-08 抓取）——LeRobot v3、键 schema、30fps/480×640。
  - S4 参赛手册（feishu）`.../Uz7OdFBcDoqP1dxgH62cHW1CnMh`——**Login Required，未获取**（诚实标注）。
- **文献（arXiv，检索日期 2026-11-08）**：
  - R41 GR00T N1: An Open Foundation Model for Generalist Humanoid Robots, arXiv:2503.14734。
  - R42 GR00T N1.7 One-Step Drifting Action Heads, arXiv:2609.18108（少步/一步动作头 + 异步 chunk）。
  - R43 G0.5: One Autoregressive Stream for Robot Reasoning and Action, arXiv:2608.11739（单流推理+动作 + 任务分解 CoT）。
  - R44 Concertina: Embodying Manipulation and Cognition in One Diffusion VLM, arXiv:2611.07513（认知与操作同体）。
  - R45 DSWAM: A Dual-System World Action Foundation Model, arXiv:2607.04927（world-model 稠密监督 + 语言规划）。
  - R46 Beyond Flat Policies: Hierarchical Post-Training for Embodied Agents, arXiv:2608.05999（分层后训练/任务分解）。
  - R47 HAF: Adapting Generalist VLAs to Humanoid Whole-Body Loco-manipulation via Hierarchical Action, arXiv:2608.16837。
  - R48 CoEvolve: Self-Evolving Code Policies from Skills to Strategies for Humanoid Robots, arXiv:2610.23288（技能→策略）。
  - R49 Early Warning Signals for OpenVLA Failure under Visual Distribution Shift, arXiv:2606.29699（内部激活失败探针）。
  - R50 Where Is VLA Inference Time Spent? arXiv:2611.06710；LoopQ: Fair, Closed-Loop Evaluation of Quantized VLAs, arXiv:2611.05093（时延/量化评测）。
  - R51 EyeRobot 2.0: Active Gaze for Precise Manipulation without Wrist Cameras, arXiv:2610.03710；VREgo, arXiv:2611.07272（腕相机/多视图相关）。
- **诚实记录**：S4 未获取（登录墙）；F27 榜单数据为空（Coming Soon）；"榜首<30%""5 类泛化"为**用户口径/待验假设**，本轮未获一手证据；R41–R51 均为 arXiv API 实时检索所得（含标题/编号/日期），未逐篇读全文。

## 8. 清单迭代规则（继承 + 第 33 轮增补）

- 继承第 28–32 轮规则 12–26（评测防博弈、量化确界、成本记账、失败留痕等），但**规则 24–26 中依赖力/触觉通道的条款随之退役**（登记原因：接口不可达）。
- **27（新增）：接口优先 / 通道诚实**——任何创新点不得依赖官方未暴露的观测/执行通道（力、触觉、社会反馈等）；"假设能读到 X"一律视为未成立；退役项须写明不可达原因。
- **28（新增）：映射验证纪律**——dataset 键 ↔ API 键的映射（含内参/校正/量纲/坐标系）必须经 A9 校验并留证据；未验证通道默认冻结，不得进入主训练。
- **29（新增）：时延-可信度 SLO**——每步 P50/P99 推理时延、动作离群率、平滑度入账本；P99 超 SLO 或离群率超阈 → 告警 + 降级（更小 T_a / 更保守动作）；随版本发布。
- **30（新增）：失败预警 fail-safe**——IP-24 探针只增触发不做否决式激进动作；不确定 → 保守动作；探针不过门槛 → 仅遥测。

**本轮最大风险一句话**：最大风险不在模型而在接口映射与实时性——dataset 键与 API 键（尤其头立体 vs 高位相机、腕内参）映射错位会造成训练-推理分布错配并系统性压低成功率，而 N 端口并发 + 30fps 节拍下推理时延/动作统计规律异常会同时伤成功率与官方可信度指标；须以 A9 映射校验 + IP-3 本地闭环 + IP-25 时延 SLO 先行验证。

**当前最值得押注**：把 32 任务统一训成单个双系统 VLA（System-2 子目标规划 + System-1 少步流匹配动作头，多视图×本体×语言 token 级融合，ee/joint 双表示），用得分点监督的任务分解切长程任务，以可观测状态的失败预警替代已不可达的力觉安全盾。
<!-- ARTIFACT:END -->
