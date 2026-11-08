# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮（循环 B）· 力矩传感 × 视觉伺服 × LoRA：把「SFT 通才」改造成「感知—伺服—适配」三层闭环机

> 新循环第 1 轮（灵感词：**力矩传感 / 视觉伺服 / LoRA**）。前一轮（灵感词 UniBot-V1 / 泛化能力 / 场景理解）的清单 IP-1…IP-10 作为底座**继承并修剪**，本轮不推倒重来：新增 1 项（IP-11 CONTACT-SENSE）、重构 1 项（IP-2 → SERVO-STACK）、降级 1 项（IP-3 → 观察项 O-1）、具体化 2 项（IP-6 → LoRA-ROUTE、IP-7 → LoRA-DPO）、修订 2 项（IP-1 延迟预算、IP-5 多模态检测）。全部新事实 2026-11-07 联网核实，来源见产物区 §9。

## 0. 本轮方法论：灵感词先过「事实核查闸」，再进「清单」

研究者真实流程是：灵感词触发直觉 → 立刻去查这个词在**本赛题的接口/数据约束**下是否成立 → 成立的进清单，不成立的改写为可成立的等价命题。本轮三个词各过了一次闸，且每一次核查都改写了清单：

- **「力矩传感」→ 字面证伪、本质重构**。接口 obs 目录（unibot_submission README §2，逐键核实）只有 4×RGB + 双臂 7-DoF 位置 + EE pose + 夹爪开度 + lower_body[15] + language——**没有 effort、没有 torque**（F11）；数据集 parquet schema（HF datasets-server API，HangCup 全部 33 特征逐项核对）同样**无力矩字段**（F12）。G1 关节电机本身具备力矩估计（Unitree DDS 遥测惯例，背景知识未单独核实），但评测接口不透传——参赛者在接口内**拿不到任何力读数**。上轮 IP-2 中「数据集 effort 蒸馏力头」的设想随之作废。但「力矩传感」的本质诉求是**接触与外力的早期感知**，而接口里藏着两处免费代理信号：(a) 夹爪指令-观测差——Dex1 夹爪 5.5(开)→0.0(合)，action 与 obs 各有一通道，合拢指令下观测卡住=夹到了东西（F13）；(b) 关节指令-观测跟踪残差——我方返回的动作块是已知的，下次 obs 回来的实际状态与它的偏差=接触/被推的物理证据。灵感词于是重构为 **CONTACT-SENSE：把位置残差当力矩传感器**。
- **「视觉伺服」→ 价值上调**。F8 模型卡本轮新暴露：`use_length=50`、单块 50 步、4090 上单块推理 0.35s（F14）——头部方案一次开环执行 50 步（30fps 下 ≈1.7s），对毫米级对准任务是结构性暴露；其 ArrangePlates 开环验证 MSE 0.229 / MAE 0.176 再次佐证 B1。接口侧 ee 空间与 joint 空间互斥可二选一、EE pose 观测齐备、G1 臂运动学公开——**解析视觉伺服（IBVS + J⁺）在接口内完全可实现，无需评测方任何配合**。裁决：剪掉上轮 IP-2 的「学习式 Δee 残差修正头」，换成解析伺服定律——**感知用学习（从数据自动伪标签蒸馏），控制用定律（零训练、跨任务同一套数学）**。
- **「LoRA」→ 从微调技巧升格为架构杠杆**。F8 证明 LoRA(r64) 是唯一被验证能在单卡 4090 上做出 32 任务通才的路线；LoRA 的低秩结构另有两件免费的事：任务组 adapter 的**权重空间插值**（未见物品 = 语义最近任务组的 adapter 内插；机理同源线性模式连通性/model soups——推断，非核实事实）与 **RL 后训练的参数载体**（LoRA-DPO/GRPO 单卡可行）。同时模型卡暴露 canonical space 含 waist(4)+base(3)——**上轮 B3「头部置零全身通道」被部分证伪**，IP-3 PIVOT-GATE 差异化前提削弱，降级（§4）。

## 1. 新事实卡（编号续接前轮 F1–F10；全部 2026-11-07 检索核实）

- **F11 接口无任何力/力矩观测**：obs 目录全表 = 4×RGB(480×640) + left/right_arm[7] + left/right_ee_pose_gripper_base[6] + left/right_gripper[1] + lower_body[15] + language。无 effort/torque/frc 键。
- **F12 数据集无力矩字段**：HangCup parquet 33 特征逐项核对（state.*：arm/gripper/lower_body/leg/ee_pose base+torso/state_torso/state_d435/waist/recomputed_ee_valid；action.*：arm/gripper/lower_body/pivot/gripper_controls/leg/base_command/ee_pose base+torso/action_torso/action_d435/waist）——无 effort。→ 「力矩白捡」在数据层同样失败，改走动力学残差路线。
- **F13 夹爪是双通道闭环信号**：action.left/right_gripper（我方指令，shared 键）+ observation.state.left/right_gripper（实际开度）；Dex1 量程 5.5(开)→0.0(合)。指令-观测差 = 免费的接触/抓取确认/滑移检测器——零训练、零接口改动、完全合法。
- **F14 头部方案画像修正与新暴露面**（模型卡逐条核实）：LoRA r64/α32 于 q/v/o_proj（65M 可训练），**已 merge 成单 safetensors**；canonical space = arms(14) + grippers(2) + **waist(4) + base(3)**，arm 为 state-relative delta；`use_length=50, chunk_ret=True`；4090 单块（50 步）推理 0.35s；ArrangePlates 开环验证 MSE 0.229 / MAE 0.176；模型卡中的参赛 wrapper 外链（github.com/ezhoureal/unibot_submission）**已 404 失效**（GitHub API 核实该账号无此仓库，仅存 lingbot-vla-v2，2026-08-02 推送）。
- **F15 官方 32 任务清单全部核实**（collection 页面逐项抓取）：ArrangePlates / ArrangeTestTubes / ColorArrangement / ConveyorSorting / DisconnectEthernet / FoldTowel / FruitCollection / FruitSorting / HangCup / OrganizeBookshelf / OrganizePencilCase / OrganizeStationery / OrganizeTools / PackBag / PackDoll / PackPhone / PaperCupStacking / PickOutBatteries / PlacePhotoFrame / PlugCharger / PlugInEthernet / PourOutMedicine / RemovePinnedNote / SpellRobot / StackBowls / StoreCups / StoreEarphones / StorePaddle / SyringeWaterTransfer / ToolboxStorage / Unlock / ZipUp。其中接触丰富/毫米级对准类 **≥11/32 ≈ 34%**（PlugCharger、PlugInEthernet、DisconnectEthernet、ZipUp、Unlock、RemovePinnedNote、SyringeWaterTransfer、PickOutBatteries、StoreEarphones、ArrangeTestTubes、PourOutMedicine）——SERVO-STACK + CONTACT-SENSE 的射程覆盖三分之一赛题，而榜单按平均成功率排序、短板任务决定名次。
- **F16 排行榜仍 "Coming Soon"**（leaderboard.html 2026-11-07）；「榜首成功率 <30%」仍为用户先验（F10 沿用：弱证据、高置信，榜单公开后复核）。

## 2. 瓶颈清单修订（v1 → v2）

| 瓶颈 | v1 判断 | v2 修订 | 依据 |
|---|---|---|---|
| B1 损失-成功鸿沟 | 成立 | **强化**：开环 MAE 0.176 再添证 | F14 |
| B2 深度缺失 | 成立 | 不变（接口 RGB-only） | F11 |
| B3 全身闲置 | 头部置零 pivot | **降级**：头部 canonical space 已含 waist4+base3，可能已用 | F14 |
| B4 块内开环 | 成立 | **强化**：头部 50 步/块 ≈1.7s 开环窗口 | F14 |
| B5 任务互扰 | 成立 | 不变，但解法落到 LoRA-ROUTE | F8 |
| B6 步骤分无人优化 | 成立 | 不变 | F1 |
| **B7 接触盲目（新）** | （v1 未单列） | 接口与数据均无力反馈，头部方案对接触状态无感知通道——抓取确认靠猜、插入推进靠开环蛮进 | F11–F13 |

## 3. 本轮策略结构：三把新刀 + 原有地基

- **感知层 CONTACT-SENSE（IP-11，新）**：T1 免费信号（夹爪捏合差 + 跟踪残差，零训练）+ T2 学习式动力学残差模型（33k episodes 训练，<2ms）——给全栈装上「力觉」。消费方：IP-5 干扰检测、IP-10 卡死/重试触发、IP-1 进展特征、插入任务的力轮廓（推进-遇阻-横移微调-再推进）。
- **伺服层 SERVO-STACK（IP-2 重构）**：深度蒸馏保留；学习式残差修正头被解析 IBVS 替换；感知=深度头+任务条件关键点头（全部离线自动伪标签，评测时只跑小头 ≤25ms）；**伺服相位跳过 VLA 前向，单步延迟从 ~350ms 降至 ~25ms——伺服不仅提成功率，还改善 F5 延迟稳定性**。切换由进展模型（IP-1）门控，接触信号（IP-11）裁决插入相位。
- **适配层 LoRA-ROUTE（IP-6 具体化）+ LoRA-DPO（IP-7 具体化）**：任务组 adapter + 语言条件权重插值（reset 时一次混合，运行时零开销）；未见物品 = 语义最近组插值 + 基座保留系数；RL 后训练以 LoRA 为载体、以数据集自然失败/重试片段为离线偏好对。
- **地基保留**：IP-8 SERVE-N（F4/F5）、IP-9 LOCAL-BENCH、IP-4 AUG-PANO 原样推进；IP-1 PROGRESS 增加接触特征，并修订 best-of-n 的延迟预算（v1 没算 n 次动作头采样 ≈ n×0.35s 的账——本轮自纠：只在导航/接近相位用、伺服相位禁用）。

## 4. 修剪记录（执行「修剪优先」原则）

1. **剪**：v1 IP-2 的学习式 Δee 末段残差修正头 → 换成解析 IBVS。理由：修正头要为 11 个接触任务各学一种修正行为（数据低频、梯度被 B5 淹没），解析定律零训练、跨任务同一套数学、对感知噪声的失败模式可解析（增益衰减而非发散）。
2. **降级**：IP-3 PIVOT-GATE（P2 → 观察项 O-1）。理由：F14 显示头部 canonical space 已含 waist/base，差异化前提削弱；改为复现时检查 norm_stats 与 deploy 代码中 pivot 映射是否非零（F-O6），数据说话。
3. **剪**：v1 IP-2 中「数据集 effort 蒸馏力头」步骤 → F12 证伪，替换为动力学残差模型（T2）。
4. **修订**：IP-1 best-of-n 加相位门控与延迟预算（n 次采样 ≈ n×0.35s 只在非伺服相位使用）。
5. **沿用**：v1 对「动态 chunk」的修剪（与 metadata 静态申报冲突）继续有效。

## 5. 本轮最大风险一句话

伺服栈的三处依赖——腕部相机外参链（F-O1）、关键点伪标签质量、评测端视觉 OOD 下小头（深度/关键点）的稳健性——任何一处塌掉都会把「解析伺服」退化为「更贵的基线」；因此每层独立可关、以 E6/E7 离线验证为合并门槛，而 IBVS 对深度绝对误差的天然鲁棒（Z 估计只缩放收敛增益、不改图像误差下降方向）是整条路线最值得先验证的假设。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 1 轮（循环 B）产物 · UniBot 创新点清单 v2：感知—伺服—适配三层闭环

## 0. 结论

- **v2 = v1 继承 + 1 新增（IP-11）+ 1 重构（IP-2 → SERVO-STACK）+ 1 降级（IP-3 → 观察项 O-1）+ 2 具体化（IP-6 → LoRA-ROUTE、IP-7 → LoRA-DPO）+ 2 修订（IP-1 延迟预算、IP-5 多模态检测）**。
- 默认 backbone 不变：LingBot-VLA 2.0 (6.3B) LoRA（F8/F14）；复现入口 `github.com/ezhoureal/lingbot-vla-v2`（模型卡里的 wrapper 外链已 404，需自建参赛包装）。
- 优先级：**P0** = IP-8 SERVE-N、IP-9 LOCAL-BENCH、IP-4 AUG-PANO；**P1** = IP-2 SERVO-STACK、IP-11 CONTACT-SENSE、IP-5 CHUNK-RESCUE、IP-1 PROGRESS、IP-6 LoRA-ROUTE、IP-10 RESCUE-LIB；**P2** = IP-7 LoRA-DPO。
- 成本不变式：LoRA 基线复现 1×RTX 4090（F8/F14 佐证）；策略内新增前向（深度+关键点+T2 残差模型）合计 ≤25ms/步；接口零改动；每项增强独立可关。
- **最值得押注（一句话见 §8）**：IP-2 SERVO-STACK——用「解出来的图像雅可比」替换「学出来的动作均值」，以 IP-11 的免费接触信号为眼睛，攻 11/32 的接触对准任务。

## 1. 清单 v2 总表

| 编号 | 名称 | v1→v2 变化 | 一句话 | 优先级 | 依赖 | 灵感词 | 资源 | 风险 |
|---|---|---|---|---|---|---|---|---|
| IP-8 | SERVE-N | 保留 | N 端口共享后端+并发调度+量化+延迟稳定性预算 | **P0** | 无 | UniBot-V1 | 1×A100/2×4090 | 低 |
| IP-9 | LOCAL-BENCH | 保留 | 步骤分代理+5 类泛化变换库+难度谱系 | **P0** | IP-1(弱) | UniBot-V1 | 1 GPU+人工抽检 | 中 |
| IP-4 | AUG-PANO | 保留 | 视觉 OOD/语义 OOD/EE 重定向三类增强（同步作用于伺服小头训练集） | **P0** | 无 | 泛化能力 | ~0.5 GPU·天 | 中 |
| **IP-2** | **SERVO-STACK** | **重构** | 蒸馏感知（深度+关键点）+ 解析 IBVS/J⁺ 末段伺服 + 相位切换 | **P1 主力** | IP-9, IP-1 | **视觉伺服** | ~1.5 GPU·天 | 中高 |
| **IP-11** | **CONTACT-SENSE** | **新增** | 夹爪捏合差+跟踪残差（T1 免费信号）→ 动力学残差模型（T2）= 接口内的「力觉」 | **P1** | IP-9 | **力矩传感** | ~0.2 GPU·天 | 中 |
| IP-5 | CHUNK-RESCUE | 修订 | T_a 帕累托申报 + 多模态偏差检测（视觉残差×跟踪残差×捏合差）+ 恢复编译进块 | P1 | IP-1, IP-11, IP-9 | UniBot-V1 | 近零 | 中 |
| IP-1 | PROGRESS | 修订 | 进展模型 P_φ：+接触特征；best-of-n 加相位门控与延迟预算；兼任伺服切换门 | P1 | IP-9 | UniBot-V1 | ~0.3 GPU·天 | 中 |
| **IP-6** | **LoRA-ROUTE** | **具体化** | K 个任务组 adapter + 语言条件权重插值（reset 时混合）；未见物品=语义插值 | P1 | IP-4 | **LoRA** | ~2 GPU·天 | 中 |
| IP-10 | RESCUE-LIB | 修订 | 重试片段挖掘 + 卡住检测（P_φ 不涨 + T1 接触信号）+ 恢复库 | P1 | IP-1, IP-11 | 泛化能力 | 近零 | 低 |
| **IP-7** | **LoRA-DPO** | **具体化** | LoRA 载体的离线偏好优化：数据集自然失败/重试片段为负例、专家段为正例 | P2 | IP-1, IP-9 | LoRA | 1–2 GPU·天 | 高 |
| IP-3 | PIVOT-GATE | **降级→O-1** | 全身 pivot 差异化前提被 F14 削弱，转为复现时的检查项 | 观察项 | F-O6 | UniBot-V1 | 0 | 低 |

## 2. 重点展开 A：IP-11 CONTACT-SENSE——把位置残差当力矩传感器

### 2.1 动机与差异

- 动机：F11/F12 证明接口与数据都拿不到力/力矩；F13 证明夹爪指令-观测双通道存在；B7 指出头部方案对接触状态完全盲目——抓取是否成功靠视觉复核甚至靠猜、插入是否受阻全靠开环蛮进。接触感知是 11/32 接触任务的公共瓶颈。
- 与现有差异：F8 类方案只消费 obs 的当前值；本方案把「我方上一块返回的动作」也当作可观测的一部分（客户端自有缓冲），构造**指令-观测残差**这一评测接口内免费的物理信号。无需评测方配合、不新增 obs 键、零接口改动。

### 2.2 信号分层

**T1a 夹爪捏合差（零训练，逐调用可得）**

```python
# Dex1: 5.5(开) -> 0.0(合)；cmd=我方上一块返回值，obs=本轮观测
pinch[t] = max(0, close_amount(cmd_gripper) - obs_gripper)      # >0 即夹着东西
width_hold = obs_gripper when cmd≈0                              # 稳态夹持宽度 ≈ 物体尺寸特征
slide[t]   = d(width_hold)/dt > τ_s while cmd closed             # 宽度回增 = 滑脱前兆
grasp_ok   = pinch>ε and wrist_img_change_correlates_with_ee_motion   # 夹住后提升，腕图应随动
```

**T1b 关节跟踪残差（零训练，需 F-O4 时序对齐校准）**

```python
# 我方在第 k 次调用返回了动作块 A_k=(a_0..a_{T_a-1})；第 k+1 次观测 s_{k+1}
# 自由空间中 G1 位置控制跟踪紧密：预测 ŝ ≈ a_{T_a-1}（或一阶指数趋近模型）
r_arm[t] = ||s_obs.arms − ŝ(A_k)||        # 接触/被推 → 残差尖峰（逐臂、逐关节可定位）
r_base[t] = ||s_obs.lower_body − ŝ_lower||  # 躯干/下肢同理，覆盖「人为干扰推身体」
# 鲁棒化：滚动基线 z-score + 滞回，避免对时序错位 δ（F-O4）敏感
```

**T2 动力学残差模型（33k episodes 离线训练，<2ms）**

- 输入：(堆叠 proprio 历史，我方动作块 A_k，任务/语言嵌入)；输出：下一观测状态预测 ŝ_{t+T_a} 逐关节 + 三类头 {自由运动 / 物体接触 / 外部扰动}。
- 弱标签自动挖掘：夹爪合拢窗口=抓取接触；插入类任务的末段=插入接触；其余=自由运动。演示数据以成功为主 → 失败检测按**一类分类**（偏离学习到的成功动力学即为异常），诚实标注此局限（产物区 §6 E6）。
- 价值：T1 是阈值启发式，T2 把「多大残差算异常」变成数据驱动的逐任务校准，且残差向量带方向（哪个关节、哪个方向被顶住 → 横移微调的方向）。

### 2.3 消费方（一份投入四处回收）

1. **IP-5 干扰检测**：扰动触发条件 = max(视觉流残差, r_arm, r_base, 捏合异常) 越限 + 滞回；
2. **IP-10 卡死/重试**：r 振荡小幅 + P_φ 不涨 = 卡住；插入类 r 持续横向分量 = 受阻 → 触发「退-横移-再进」恢复库；轴向残差骤降 = 滑入 → 恢复推进；
3. **IP-1 进展特征**：P_φ 输入加 [pinch, r_stats, width_hold]——抓取确认与插入进度直接可微调；
4. **插入力轮廓**（本 IP 独有产出）：PlugCharger/PlugInEthernet/ZipUp/Unlock 的「推进-遇阻-横移 wiggle-再推进」行为模板，由 r 的方向/幅值驱动——位置接口上对阻抗控制的最小近似。

### 2.4 实验 E6（离线，先于一切真机投入）

- 数据：32 任务 × 每任务 5 episodes 回放 + 本地 example_env 时序测量（F-O4）。
- 指标：接触检测 AUC（以自动相位标签为准）；扰动检测 AUC（对 obs 关节状态注入脚本化瞬态偏移合成「被推」信号——诚实标注：这是对信号的仿真不是真机）；捏合宽度与 episode 结局的相关性。
- 门槛：接触 AUC ≥0.85；r_arm 误报率（自由运动段）<5%；T1 全链路计算 <1ms。
- 降级：T2 不过 → 只留 T1（仍全程免费）；F-O4 时序不可辨识 → r_arm 改用逐块聚合统计量。

### 2.5 风险

- 演示数据以成功 episode 为主 → 失败/扰动正例稀缺（一类分类的精度上限）；评测端扰动分布未知；
- obs 与动作的时序对齐 δ 未知（F-O4）→ 鲁棒统计 + 本地 example_env 先校准；
- 伺服/恢复行为误触发 → 滞回 + P_φ 门控双保险。

## 3. 重点展开 B：IP-2 SERVO-STACK——感知用学习、控制用定律

### 3.1 动机与差异

- 动机：11/32 接触对准任务成败在毫米级；B1（复合误差）+ B2（RGB 无深度）+ F14（头部 50 步开环块 + MAE 0.176）三重证据。
- 与现有差异：F8 类方案端到端学「观测→动作」，末段精度是均值回归的副产品；本方案把末段拆成「学习感知 + 解析控制」——关键点/深度用数据蒸馏的小头，控制律用图像雅可比，零训练、跨 11 个任务同一套数学。

### 3.2 三层结构

**S1 感知（全部离线伪标签，评测时只跑小头 ≤20ms）**

```python
# 深度（沿用 v1）：head_stereo 已校正 → RAFT-Stereo+SGBM 融合伪标签 → 蒸馏 DepthAnything-V2-S
#   腕部视角自举依赖外参链（F-O1），失败则降级 head-only（可关）
# 关键点（新增）：任务条件 2D 关键点头（~5-10M 参数，~3-5ms）
#   伪标签全自动：持握物功能点 = EE pose + 夹爪几何常量偏移 → 投影到腕图（需 F-O1 标定）
#   目标点（孔位/卡槽）= 数据集内多视角三角化（离线全状态可得）→ 投影
#   评测端文本提示的开放词检测（GroundingDINO 类）只做离线教师，蒸馏到小头——评测时无大模型
```

**S2 控制（解析，零训练）**

```python
# IBVS：特征误差 e = [u_hole−u_peg, v_hole−v_peg, z_err]（腕图 + 蒸馏深度）
# 点特征交互矩阵 L(u,v,Z)，v_cam = −λ L⁺ e；T_base←cam 由外参链给出（F-O1）
# joint 空间输出：Δq = J⁺(q) · [Δp; Δθ]（G1 臂 URDF 运动学，q 来自 obs）
# 关键鲁棒性：Z 估计偏差只缩放切向收敛增益、不改变图像误差下降方向；
#   仅沿轴接近速度调度需要粗对深度 —— 整条路线对 F-O1 的暴露面因此大幅缩小
```

**S3 切换与门控**

- P_φ（IP-1）判定「接近/对准相位」→ 切换 VLA→伺服；接触信号（IP-11）裁决插入推进/横移/回退；超时或 P_φ 回落 → 交还 VLA（基线兜底）。
- **异构计算红利**：伺服相位跳过 VLA 前向，单步 ~350ms → ~25ms；回程调用率 = 1/(T_a/30 + 0.025)，T_a=4 时 ≈7.5Hz——伺服响应率足够，且 F5 延迟稳定性同时受益（伺服段延迟更低更稳）。

### 3.3 推理伪代码（get_action 内部，全部可逐位关闭）

```python
def get_action(obs):
    if not servo_enabled or not P_phi.in_phase(obs, task):
        return vla_chunk(obs)                      # 基线路径（n_samples 按相位预算）
    K = kpt_head(obs["wrist"], obs["head"], task)  # ~4ms
    D = depth_head(obs["wrist"])                   # ~12ms（256×320 + 量化，可 k 步复用）
    if K.conf < τ_conf: return vla_chunk(obs)      # 感知不确定 → 交还基线（安全回退）
    chunk = []
    for i in range(T_a):                           # T_a 小块，块内按 S2 递推（开环段内预测）
        dx = ibvs_step(K, D, ee_state, gains)      # 解析
        chunk.append(to_joint(dx, q) if space=="joint" else to_ee(dx))
    return format(chunk, token)
```

### 3.4 实验 E7（离线回放，先于真机）

- 关键点头：留出 10% episodes，像素误差 <8px 帧占比 ≥80% 为合并门槛；
- 深度头：对 RAFT-Stereo 伪标签 AbsRel <0.15；
- 伺服律回放：留出末段 20 步，从每状态开环执行伺服 Δee，与专家 Δee 的方向余弦 ≥0.8；混合回放（状态按专家动力学推进、动作按伺服）下特征误差单调收敛；
- 延迟：伺服全链路 P99 ≤25ms（E3 v2）。

### 3.5 风险

- 外参链（F-O1）失败 → 降级 head-only 深度条件化（不投影、不做几何伺服），保留 IP-11/恢复库收益；
- 评测端光照/背景 OOD 下小头漂移 → IP-4 增强同步作用于小头训练集 + S3 置信度门（K.conf 低即回退基线，永不比基线差）；
- T_a 静态申报与伺服响应率的矛盾 → E4 联合扫描（T_a × image_resize × 相位占比）。

## 4. 重点展开 C：LoRA-ROUTE（IP-6）与 LoRA-DPO（IP-7）

### 4.1 LoRA-ROUTE：任务组 adapter + 语言条件插值

- **分组**：数据驱动聚类 32 任务（按接触占比/相位结构/难度谱系），K=4 原型组：放置类、接触对准类、双手协调类、小物件精密类。
- **训练**：共享冻结基座 + 每组 LoRA r=32–64（~65M/组，4 组 ≈260M 增量，bf16 ~0.5GB）——单卡 4090 可行（F8 同量级）。
- **部署（reset 时混合，运行时零开销）**：新 episode 拿到 language → 语言嵌入 → α = softmax(sim(e_lang, 组锚点)) → 一次性物化 W = W0 + Σ α_k B_k A_k（只触碰 q/v/o_proj 模块，秒级）；整个 episode 用同一组混合权重——是「语言条件化的单模型」，与内部 MoE 语义等价但便宜得多。
- **未见物品泛化**：语义最近组的插值 + 基座保留系数（α 封顶 ~0.8，保留通才底座能力）——把「零样本任务泛化」变成权重空间插值（机理依据：同基座 LoRA 增量的线性插值良态性，属推断，E8 验证）。
- **合规边界与回退**：若规则将「单模型」解释为静态权重（F-O2 待确认），回退 = 各组 α 取先验固定的静态合并（损失自适应性，仍优于单全局 LoRA 的组间折中）。

### 4.2 LoRA-DPO：离线偏好对，无需仿真器

- 正例：数据集专家段；负例三源：(a) 同任务自然失败/重试片段（v1 IP-10 挖掘管线复用）；(b) 当前策略在数据集状态上的采样块（K 个候选，按 P_φ 期望进展排序取低者）；(c) 伺服回退前的失败段。
- 奖励/标签 = P_φ 进展增量 + 接触轮廓匹配（IP-11）；LoRA-only 更新，参考策略 = 冻结基座+旧 adapter（增量小，显存可行）。
- 定位：P2 期权——先把 IP-1/2/11 的确定性收益落袋，DPO 作为第二级增益。

### 4.3 实验 E8

- 4 组 adapter vs 单全局 LoRA：逐任务 val loss 对比（接触组预期显著优）；
- 插值泛化：val 集物体贴图替换（IP-4 管线），插值 α vs 最近组硬路由 vs 单 adapter；
- reset 时混合开销 <3s/episode（不占调用延迟）。

## 5. 其余条目修订简表

| 编号 | v2 修订点 | 落地步骤 | 风险 |
|---|---|---|---|
| IP-1 PROGRESS | P_φ 输入 + [pinch, r_stats, width_hold]；best-of-n 加相位门控（n≤4 仅导航/接近相位，伺服相位禁用——n×0.35s 延迟账）；兼任 S3 切换门 | 同 v1 + 特征拼接 | best-of-n 延迟超预算 → 相位白名单 |
| IP-5 CHUNK-RESCUE | 检测器 = max(视觉残差, r_arm, r_base, 捏合异常)+滞回；F14 证据：头部 50 步块 ≈1.7s 开环，我方 T_a=4–8 + 检测 = 响应性护城河 | 同 v1 + 接入 IP-11 | 误触发 → 滞回+P_φ 双门 |
| IP-10 RESCUE-LIB | 卡住检测加 T1 信号；插入类恢复模板由 r 方向驱动（退-横移-再进） | 同 v1 | 恢复抖振 → 滞回 |
| IP-8 SERVE-N | 不变；伺服相位跳 VLA 反而降低后端负载 | 同 v1 | 并发阻塞 → E0 压测 |
| IP-9 LOCAL-BENCH | 增加 E6/E7 的离线校验台（example_env 时序测量、关键点/深度精度、伺服回放） | 同 v1 | 代理鸿沟 → 仅回归信号 |
| IP-4 AUG-PANO | 增强管线同步作用于深度/关键点小头训练集 | 同 v1 | 过强 → E2 消融 |
| O-1（原 IP-3） | 复现时检查 norm_stats/unibot_full.json 与 deploy 代码中 pivot 映射是否非零（F-O6）；若头部已用且有效 → 无差异化，关闭 | 0.5 天 | 无 |

## 6. 实验设计 v2（E0–E8；E0–E5 同 v1，增量如下）

| 实验 | 设置 | 指标 | 门槛 |
|---|---|---|---|
| **E6 CONTACT** | 160 episodes 回放 + example_env 时序校准 + 合成扰动 | 接触 AUC、误报率、T1 计算耗时 | AUC≥0.85；自由段误报<5%；<1ms |
| **E7 SERVO** | 关键点/深度小头训练 + 伺服律开环/混合回放 | 像素误差<8px 占比、AbsRel、Δee 方向余弦、P99 延迟 | ≥80%；<0.15；≥0.8；≤25ms |
| **E8 LoRA-ROUTE** | 4 组 adapter vs 全局 LoRA + 插值泛化 | 逐任务 val loss、OOD val 成功率代理、reset 混合耗时 | 接触组显著优；混合<3s |
| E4 v2 | T_a ∈ {2,4,8,16} × image_resize × 相位占比 | 伺服响应率 × 延迟稳定性的帕累托 | 记录申报值与理由 |

降级机制升级：每项增强独立开关不变；新增**相位级回退**——S1 置信度不足即整段交还基线，SERVO-STACK 与 CONTACT-SENSE 在任何感知失效下都退化为纯基线，无负收益。

## 7. 风险登记簿 v2（相对 v1 的增量）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 伺服栈三依赖（外参 F-O1/伪标签/小头 OOD）任一塌掉 | **高（本轮最大）** | Z 偏差只影响增益不改方向（先验证该假设）；置信度门控回退基线；E7 门槛 |
| 演示数据以成功为主 → 接触检测正例稀缺 | 中 | 一类分类 + 合成扰动；诚实标注局限 |
| obs-动作时序对齐 δ 未知（F-O4 新） | 中 | example_env 本地先测；鲁棒统计 |
| LoRA-ROUTE 与「单模型」细则的解释冲突（F-O2 扩展） | 中 | 回退静态合并；优先邮件/官方渠道确认 |
| best-of-n 延迟超预算 | 中 | 相位白名单（v1 缺陷本轮已修） |
| T2 模型输入含我方动作块 → 训练-推理分布差（训练时动作=专家，推理时=自己） | 中 | 用当前策略 rollout 数据回流微调 T2（自举一轮） |
| （沿用 v1 全部条目） | — | — |

## 8. 一句话押注 + 开放问题

**最值得押注**：IP-2 SERVO-STACK——用「解出来的图像雅可比」替换「学出来的动作均值」，攻 11/32 接触对准任务，并以 IP-11 的免费接触信号（夹爪捏合差 + 跟踪残差）为眼睛；两者都在接口内零改动、逐层可关，且伺服相位跳过 VLA 前向后延迟反而更低更稳（F5 受益）。

开放问题（续 F-O1/F-O2/F-O3，新增）：
- **F-O4**：评测端 obs 返回与动作块执行的时序对齐 δ——用仓库自带 example_env 本地测量，决定 T1b 的统计形式；
- **F-O5**：lingbot-vla-v2 代码的深度特征注入点（其 Depth 变体接口），决定蒸馏深度以「特征拼接」还是「输入替换」方式接入；
- **F-O6**：F8 的 pivot/waist/base 通道是否实际非零输出（norm_stats + deploy 代码检查），决定 O-1 关闭或复活。

## 9. 来源清单（全部检索/核实于 2026-11-07）

1. 官网挑战赛页：https://unibot.unitree.com/challenges.html （32 任务 / 32,000 episodes / 169h / 每任务得分点满分 100；任务卡片 JS 动态加载，静态页只见表头）
2. 官网排行榜页：https://unibot.unitree.com/leaderboard.html （仍"Coming Soon"，F16）
3. 提交模板 README（逐节核实）：https://github.com/unitreerobotics/unibot_submission —— obs 目录全表（无 effort/torque，F11）、obs_delta_indices/image_resize/action_chunk_size 语义、N 端口规则、§6 可信度考核、example_env 本地验证工具
4. 数据集 schema（HF datasets-server info API）：https://datasets-server.huggingface.co/info?dataset=unitreerobotics%2FG1_Dex1_HangCup （33 特征逐项核对，无 effort，F12）
5. 数据集卡：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup （LeRobot v3.0、AV1 480×640@30、head_stereo 已校正、Dex1 夹爪 5.5→0.0、194,564 行 / 1.04k episodes / 8.8GB，F13）
6. 头部方案模型卡：https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora （r64/α32 q/v/o_proj 65M、已 merge 单 safetensors、33,276 episodes、10K steps、单卡 4090、val/loss 0.085、canonical space arms14+grippers2+waist4+base3、use_length=50、0.35s/50 步块、ArrangePlates MSE 0.229/MAE 0.176、wrapper 外链 404，F14）
7. 官方数据 collection：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset （32 个 G1_Dex1_* 数据集逐项抓取，F15）
8. GitHub API（ezhoureal 仓库列表）：https://api.github.com/users/ezhoureal/repos （仅 lingbot-vla-v2 存在，2026-08-02 推送；unibot_submission fork 不存在）
9. 训练/部署代码：https://github.com/ezhoureal/lingbot-vla-v2 （复现入口）
10. 规则文档（仍未核实，需登录）：https://scnhkkkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh （中）/ https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh （英）——诚实记录：仅获 JS 壳
11. 「榜首成功率 <30%」：用户先验，官网榜单未公开（F10/F16，弱证据高置信采用）

## 10. 清单迭代规则（v1 五条沿用，追加第 6 条）

1. 每项创新点必含：动机/与现有差异/可行性/资源/落地步骤/风险六要素；
2. 接口红线：不新增 obs 键、不改评测方行为、所有增强独立可关（逐位回退基线）；
3. 合规红线：不做评测操纵，进展模型只优化我方期望动作选择；
4. 先证后立：头部方案画像仅基于可证样本与公开文献，推断必须标注；
5. 修剪优先：每轮先深化/修剪/修正，再新增（v1：动态 chunk→T_a 扫描；本轮：残差头→解析 IBVS、IP-3 降级、effort 蒸馏→动力学残差）；
6. **（新）灵感词先过事实核查闸**：词义在本赛题接口/数据约束下不成立时，重构为可成立的等价命题再入清单（本轮：力矩传感→位置残差力觉）。
<!-- ARTIFACT:END -->
