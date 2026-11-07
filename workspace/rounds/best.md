# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 1 轮 · UniBot 锚定与灵感词裁决：先核实、再挖掘，最后才谈押注

## 0. 开场立场（为什么本轮不是延续第 28 轮的社机器人设）

第 28 轮及之前的清单（IP-1~IP-13，SOCIAL-MOTION-LITE）是在「有可靠人体手部关键点通道、QP 仲裁、维护窗口」这套假设下长出来的；那套假设在 UniBot 已核实的接口面前**大部分不成立**：评测观测只有 4 路相机 + 本体感知 + 一条语言字符串，没有人体骨架、没有音频、没有单独的手部通道。所以本轮第一件事不是发明新算法，而是**把清单重新锚定到已核实的事实上**——该留的留、该改锚的改锚、该剪的剪，这才符合「优先深化与修剪，而不是推倒重来」的迭代纪律。

## 1. 检索实录（全部检索于 2026-11-07，见产物区来源清单）

**拿到的（已核实）：**
- 赛事官网四页在线；排行榜与运行记录均标注 Coming Soon → 截至检索日**不存在任何公开的头部方案数据**，「榜首成功率不到 30%」只能记作用户口径（F12），不能当事实卡用。
- 挑战赛页：32 项真实桌面任务、32000 episodes、169 小时；单模型多任务通用性评测（"single-model, multi-task general performance"）。
- HF 数据集合集：32 个 `G1_Dex1_<Task>` 数据集（HangCup/ArrangePlates/ZipUp/PourOutMedicine…各约 1000 集，30fps，4 相机 640×480 AV1，Dex1 平行夹爪，apache-2.0）。
- 提交模板仓库 `unibot_submission`：policy 三成员接口（metadata/get_action/reset）、websocket+msgpack、相机帧 JPEG q95 4:4:4 过网、动作 chunk、token 每步校验、N 台机器人对应 N 个连续端口（8765 起）、**逐步延迟与动作统计规律性会被记录并可能随成绩发布**。
- Unitree 自家底座：UnifoLM-VLA-0（Qwen2.5-VL 血脉，VLM-Base 8B，2026-01-29 开源训练/推理代码，CC BY-NC-SA 4.0）；UnifoLM-WMA-0（世界模型-动作架构，明确定位为「(a) 交互式模拟器产合成数据 (b) 预测未来以增强策略」，license 标注自相矛盾：卡片文本 NC-SA / HF 元数据 apache-2.0）。

**拿不到的（诚实记录）：**
- 参赛规则手册在飞书且**需要登录**（Jina 代理被重定向到登录页）→ 步骤分公式、5 类泛化场景的官方定义、单 episode 时限、N 的确切值、是否允许录制自身观测，**全部无法公开核实**，只能记用户口径或列为待办。

**三个改变研究重心的意外发现：**
1. 训练集里**每个任务自带 5 条同义指令**（`meta/tasks.parquet` 用 `@` 连接），而每条 episode 只有 `task_index`——指令要自己挂，且换句就是现成的泛化增强种子。评测段的 `observation.language` 是明文字符串，指令口径是否一致无人知晓。
2. Runs 页明示「点击详情查看完整评测视频」→ **官方每次评测都会产出带分数与完整视频的公开运行记录**：失败视频=免费标注，官方步骤分=免费偏好标签。这是 IP-19 的由来。
3. 接口本身就是分数：相机通道改名（`head_stereo_left→cam_left_high`）、Dex1 夹爪 5.5=开/0=闭的**反相约定**、`pivot` 7 维通道（vx,vy,angle_z,pivot_3/4/5,height，遥操杆量，乱输出会改变机器人姿态）、缺失状态（torso/d435/waist/recomputed_ee_valid 在评测段不存在）——任何一处静默错映射，成功率直接归零，且**在本地毫无症状**。

## 2. 瓶颈重判：在无法核实榜单的前提下，用可核实事实推头部方案的墙

头部方案不可考，我不编造。把「单模型 32 任务、遥操演示数据、真实硬件、按成功率+步骤分排名」这几个硬事实摆在一起，墙上必然有这五块砖：
- **砖一：静默错映射**（上面第 3 点）——不是模型问题，是系统问题； everyone 都暴露。
- **砖二：开环 BC 的复合误差 + 零恢复数据**——遥操演示是干净的，真实闭环一偏就回不来；32 个任务里长程任务（ZipUp/PlugCharger/SyringeWaterTransfer）尤其脆。
- **砖三：遥操演示不 step-optimal**——6 秒量级的人操轨迹含大量停留与绕路，直接拟合就把步骤分拱手让人；而步骤分与成功率**并列进入排序口径**（官网原文）。
- **砖四：五类场景 shift**（位置/干扰物/背景/未见物品/人为干扰，用户口径）——演示数据是受控桌面，一条平移或一只手入画就出分布。
- **砖五：语言口径 shift**——训练侧 5 条同义句、评测侧指令措辞未知，指令编码稍有偏差就是「做对了物体、做错了目标」。

## 3. 三个灵感词的裁决（这是本轮的筛子，也是产出清单的根据）

**「创新点挖掘」→ 采纳，且它就是本轮的方法论本身。** 我按「排序指标 → 因子分解 → 每因子的候选机制 → 期望边际分 × 可行性」的顺序机械地过一遍，得到的不再是拍脑袋清单，而是一张带依赖和门槛的地图（产物区 §2）。收益：清单从 13 项收敛为「2 项 P0 + 5 项 P1 + 若干改锚/冻结/修剪」，且每一项都能回答「动了排序口径里的哪个因子」。

**「语音合成」→ 修剪，本轮明确拒绝，理由写入规则防止后续轮次反复追问。** 核实过的事实：动作目录只有夹爪+臂+EE+pivot；观测目录里视频流 `has_audio: false`、唯一的语言字段是**输入**字符串； Runs 页只展示视频。即：TTS 在评测闭环里既无输出通道也无感知通道，投入产出为零。唯一残余价值是开发期给调试视频配音这类纯工具性用途，降格为「可选工具项」，不进评分路线。与它相邻的**语言侧真问题**（指令改写鲁棒性）由 IP-16 接手——这是把灵感词「翻译」成有效问题的标准动作。

**「强化学习」→ 采纳，但全程带闸。** 没有官方仿真器、没有真实机器人随时可蹭，所以「仿真里 PPO 再 sim-to-real」这条路对 No 队是空头支票。两条可落地路径：
- **路径 A（推理时，不训练）**：用 WMA-0 世界模型当「动作候选的异步裁判」——采样多个 chunk，用世界模型预测未来帧，选让场景状态最接近任务目标的执行。本质是 MPC/verifier，不是 RL，风险可控、可消融。
- **路径 B（离线偏好，无环境交互）**：metric-DPO——把「同一任务、我们自己的多次预约运行」按官方评分（成功率/步骤分）组成偏好对，直接对 VLA 做偏好优化。数据来自官方计分本身，零人工标注。这是「强化学习」思想在「无仿真器、少真机」约束下的正确退化形态。
两条路径的共同闸门（继承第 28 轮规则 12 并加强）：任何学习出来的组件上线即可消融，消融后系统回退到 BC 基线且不得更差。

## 4. 与旧清单的关系：一个改锚，两个新增，一个修剪

- **改锚**：IP-11/13（INTENT-GUARD / SOCIAL-MOTION-LITE）的输入通道从「可靠手部关键点」改为「4 路相机的视觉干扰检测」，防御动作从「让位」改为「冻结/保持/收手」——双轨兜底与可消融思想全部保留，QP/LQR 那套重机械全部拆除。
- **新增**：IP-14（桥接与干跑）、IP-15（步骤分目标）、IP-19（运行记录挖掘）——全部来自本轮挖掘，不是旧清单的自然延伸，这正是「推倒重来」与「重新锚定」的区别：保留旧结构（纪律、账户、可消融），替换旧内容（通道、机制、数据源）。
- **修剪**：语音合成（§3）；SLAM-MAP 降级（无 LiDAR，纯视觉记忆）；SWARM-DECODE 降 P2（先把单模型做对）。

## 5. 本轮押注

**IP-14 BRIDGE-0（桥接 + 干跑 + 预约时段影子录制）**：它同时是「防止成功率归零的保险」和「把稀缺的预约评测变成持续数据资产的飞轮入口」——榜单未公开的混沌期，这是唯一同时满足低成本、高确定性收益、且能滋养后续所有创新点的动作。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 1 轮产物 · 创新点清单 v6：UniBot 锚定版（事实驱动重锚 + 灵感词裁决）

## 0. 结论

第 1 轮完成「核实 → 重锚 → 挖掘 → 裁决」四步，将前 28 轮的 13 项清单重构为 UniBot 锚定的 16 项：

- **新增 P0 ×2**：IP-14 BRIDGE-0（训练/评测接口桥 + 三层干跑 + 影子录制）、IP-15 STEPSCORE-OBJ（步骤分-aware 早停与 chunk 调度）。
- **新增 P1 ×4**：IP-16 INSTRUCT-AUG（指令改写鲁棒性）、IP-17 WM-VERIFY（世界模型推理时裁判 + metric-DPO）、IP-18 LATENCY-STRICT（延迟稳定性工程）、IP-19 RUN-VIDEO-MINE（官方运行记录挖掘）。
- **改锚 ×2**：IP-11R INTENT-GUARD（干扰感知从手部关键点改为 4 相机视觉检测；防御动作=冻结/保持）、IP-13R SAFE-ARB-LITE（拆除 TV-LQR/QP 重机械，仅保留「异常检测→冻结回退」双轨思想）。
- **降级/冻结 ×4**：IP-1 SLAM-MAP→视觉场景记忆版（P2）；IP-9 SWARM-DECODE（P2）；IP-5 DUAL-HEAD（维持冻结）；IP-12 PREDICT-MAINT 保留为端口健康件（P1，细节已按 N 端口事实更新）。
- **修剪 ×1**：语音合成——评测闭环无音频输出/输入通道，产出为零，仅降格为开发期工具项；相邻的语言侧真问题交由 IP-16。
- **保留 P0 纪律件**：IP-3 LOCAL-EVAL（重定义为干跑+影子+开环三位一体）、IP-2 SCORE-ALIGN（指标分解）、IP-10 COST-LADDER（账户改为 GPU·时/端口/预约时段/延迟预算）。
- 榜单与 Runs 页截至 2026-11-07 均为 Coming Soon：**任何「头部方案」分析本轮不写死，只写挖掘计划（IP-19）**；「榜首成功率<30%」记为用户口径（F12）。

## 1. 事实卡（全部检索/核实于 2026-11-07，来源见 §7）

| # | 事实 | 状态 |
|---|---|---|
| F1 | 赛事官网四页在线；排行榜、运行记录均 Coming Soon，无任何公开成绩 | 已核实 [R1][R2] |
| F2 | 32 项桌面任务、32000 episodes、169 小时；单模型多任务泛化评测口径 | 已核实 [R2] |
| F3 | 数据集=32 个 `G1_Dex1_<Task>`（LeRobot v3.0，各约 1000 集，30fps，4 相机 640×480 AV1，Dex1 平行夹爪，apache-2.0） | 已核实 [R3] |
| F4 | 观测：4 相机 + 双臂关节[7]×2 + EE 位姿(base)[6]×2 + 夹爪[1]×2 + lower_body[15] + language 字符串；**无人体骨架、无音频（视频流 has_audio=false）** | 已核实 [R4][R9] |
| F5 | 动作：夹爪[1]×2 + pivot[7] +（joint 臂[7]×2 或 ee 位姿[6]×2，二选一）；action_chunk_size≥1；token 握手+每步校验 | 已核实 [R4] |
| F6 | 传输：websocket + msgpack；相机帧 JPEG q95 4:4:4 有损过网；obs_delta_indices 决定观测子集与时序叠帧；image_resize 客户端侧 cv2.resize | 已核实 [R4] |
| F7 | 部署：N 台机器人随机顺序，须暴露 8765 起 N 个连续端口；端口间进程隔离或共享后端（需并发+状态隔离） | 已核实 [R4] |
| F8 | 逐步延迟被记录；**延迟均值/波动与动作统计规律性可能随成绩发布**（可信度评估） | 已核实 [R4 §6] |
| F9 | Runs 页将公开每次运行的完整评测视频（可按用户/模型/任务过滤） | 已核实 [R2] |
| F10 | 训练集 episode 仅有 task_index；任务语言=5 条同义句以 `@` 连接于 meta/tasks.parquet（HangCup 实证） | 已核实 [R9] |
| F11 | 训练动作含 pivot=[vx,vy,angle_z,pivot_3,pivot_4,pivot_5,height]（遥操杆量，height≈0.74）与 base_command；Dex1 约定 **5.5=全开→0=全闭** | 已核实 [R10] |
| F12 | 「榜首成功率<30%」「5 类泛化场景（位置/干扰物/背景/未见物品/人为干扰）」 | **用户口径，未公开核实** |
| F13 | 规则手册（飞书）需登录；步骤分公式、单 episode 时限、N 值、是否允许录制观测均无法核实 | 已核实「不可核实」[R5] |
| F14 | UnifoLM-VLA-0：Qwen2.5-VL 骨干、GR00T/openvla-oft 血脉训练框架、2026-01-29 开源、CC BY-NC-SA 4.0；WMA-0 世界模型定位「模拟器+策略增强」，license 标注矛盾（卡片 NC-SA / HF 元数据 apache-2.0），gated | 已核实 [R6][R7][R8] |

**行动项**：A1 注册拿规则手册（解 F13 全部未知）；A2 影子录制核对相机身份（`cam_*_high` vs `head_stereo_*` 是否同物理相机未在文档中确认）；A3 确认 NC-SA 许可证用于比赛/后续开源的合规边界；A4 榜单发布后立即跑 IP-19。

## 2. 创新点清单 v6 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 动的排序因子 | 状态 |
|---|---|---|---|---|---|---|---|
| IP-14 | BRIDGE-0 | 训练/评测键映射桥 + 三层干跑 + 预约时段影子录制 | **P0** | 无 | 创新挖掘 | 成功率（防归零） | 新增 |
| IP-15 | STEPSCORE-OBJ | 完成检测早停 + chunk 调度 + 轨迹级偏好 | **P0** | IP-14 | 强化学习 | 步骤分（+成功率尾部保护） | 新增 |
| IP-3 | LOCAL-EVAL | 干跑回放/开环指标/影子数据三位一体 | P0 | IP-14 | 继承 | 迭代速度 | 重定义 |
| IP-2 | SCORE-ALIGN | 成功率×步骤分双因子分解，驱动所有决策 | P0 | 无 | 继承 | 两者 | 维持 |
| IP-10 | COST-LADDER | 账户=GPU·时/端口/时段/延迟预算 | P0 | 无 | 继承 | 防负 ROI | 改锚 |
| IP-4 | SUBMISSION-OPS | N 端口/令牌/掉线恢复/延迟遥测 | P1 | 无 | 继承 | 可信度 | 维持 |
| IP-12 | PREDICT-MAINT | 端口健康/进程守护/慢查询降级 | P1 | IP-4 | 继承 | 可信度 | 维持 |
| IP-16 | INSTRUCT-AUG | 5×32 种子指令 → LLM 改写覆盖 + held-out 鲁棒性测试 | P1 | 无 | 语音合成(裁剪后迁移) | 成功率（语言 shift） | 新增 |
| IP-17 | WM-VERIFY | 世界模型推理时裁判 + metric-DPO 离线偏好 | P1 | IP-14,IP-16 | 强化学习 | 两者（恢复能力+步骤） | 新增 |
| IP-18 | LATENCY-STRICT | P99 延迟确界 + 推理前移 + 端口级隔离 | P1 | IP-4 | 继承+挖掘 | 可信度 | 新增 |
| IP-19 | RUN-VIDEO-MINE | 官方运行记录→失败分类学→数据优先级 | P1 | F9 公开 | 创新挖掘 | 成功率（定向补数据） | 新增 |
| IP-11R | INTENT-GUARD | 相机流视觉干扰检测 → 冻结/保持/收手 | P1 | IP-14 | 继承 | 人为干扰场景 | 改锚 |
| IP-13R | SAFE-ARB-LITE | 异常检测→冻结回退双轨（拆 TV-LQR/QP） | P1 | IP-11R | 继承 | 干扰场景+安全 | 改锚 |
| IP-1 | SCENE-MEM | 视觉场景记忆/物体中心状态追踪 | P2 | IP-14 | 继承 | 长程任务 | 降级 |
| IP-9 | SWARM-DECODE | 推理时 population 投票 | P2 | IP-17 | 继承 | 全场景 | 降级 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | A3 合规 | 继承 | 视合规 | 冻结 |
| — | 语音合成(TTS) | 评测闭环无音频通道 | — | — | **裁剪** | 零 | 修剪记录 |

## 3. 重点展开

### 3.1 IP-14 BRIDGE-0：桥接 + 三层干跑 + 影子录制（P0，本轮核心）

**动机**：F4/F5/F6/F10/F11 合起来意味着训练数据与评测接口之间存在 6 类系统性差异（相机改名、缺状态、夹爪反相约定、pivot 通道、指令挂载、JPEG/resize 往返）。任何一处静默错映射在本地零症状、在真机上直接归零，且这类错误与模型能力无关——它是当前期望损失最大、成本最低的一项。

**与现有方案的差异**： Unifolm-VLA 训练管线只解决「数据格式→模型」，不解决「模型→本赛事评测 API」；官方模板只给零动作 stub。Bridge-0 是显式的第三块：可测试、可版本化、可回放的映射层，而不是塞在 `get_action` 里的几行 glue code。

**可行性**：纯工程；全部依据已核实的接口文档与数据集 schema 编写；唯一的未知（相机物理身份）由影子录制消除（A2）。

**所需资源**：数据=32 个数据集的 `meta/stats.json`（归一化统计量）+ `meta/tasks.parquet`；算力=0（干跑 1 CPU 小时级）；接口=官方 run_server/run_client + example_env 校验器。

**落地步骤**：
1. 写 `bridge.py`（下述伪代码），单元测试过 example_env 全部校验。
2. 回放级干跑：从数据集抽 200 episode 末帧，经 JPEG q95 4:4:4 往返 + resize 往返，断言归一化/反归一化数值误差 < 1e-3。
3. 影子级：预约时段内录制真实 obs 流 + 每步延迟；运行结束后对齐 Runs 页视频核对相机身份、夹爪方向、pivot 实效、episode 终止模式（验证 A-1/A-2 假设）。

```python
# ---------- 观测侧：训练键 <- 评测键 ----------
KEY_MAP = {  # 左：训练(LeRobot v3.0)键，右：评测 API 键
    "observation.images.head_stereo_left":  "observation.images.cam_left_high",
    "observation.images.head_stereo_right": "observation.images.cam_right_high",
    "observation.images.wrist_left":         "observation.images.cam_left_wrist",
    "observation.images.wrist_right":        "observation.images.cam_right_wrist",
}
SAME_NAME = ["observation.state.left_arm", "observation.state.right_arm",
             "observation.state.left_ee_pose_gripper_base", "observation.state.right_ee_pose_gripper_base",
             "observation.state.left_gripper", "observation.state.right_gripper",
             "observation.state.lower_body"]
DROP_OBS  = ["observation.state.state_torso", "observation.state.state_d435",
             "observation.state.left_ee_pose_gripper_torso", "observation.state.right_ee_pose_gripper_torso",
             "observation.state.waist_state_joint", "observation.state.recomputed_ee_valid",
             "observation.state.left_leg", "observation.state.right_leg"]  # 评测侧不存在→训练期即丢弃/常量占位

def obs_to_model(obs_eval):
    o = {}
    for k_train, k_eval in KEY_MAP.items():          # 相机：传输层已 JPEG 解码；训练侧主动做同款轻压缩增强
        o[k_train] = jpeg_roundtrip(obs_eval[k_eval])
    for k in SAME_NAME:
        o[k] = obs_eval[k]
    for k in DROP_OBS:
        o[k] = CONST_IMPUTE[k]                        # 与训练期占位一致
    o["task_text"] = obs_eval["observation.language"] # 明文字符串
    return stack_and_normalize(o, stats=meta_stats)   # 统计量必须来自 meta/stats.json

# ---------- 动作侧：模型 -> 评测动作 ----------
DEFAULT_PIVOT = dataset_mode("action.pivot")          # 例：[0,0,0,0,0.15,0,0.74]；冻结防误驱动

def model_to_action(a_model, control_space, chunk_T):
    a = {}
    if control_space == "joint":                      # 默认：离训练信号最近，避开外部 IK 意外
        a["action.left_arm"]  = np.clip(a_model.arm_l,  *JOINT_LIMITS).astype(np.float32)
        a["action.right_arm"] = np.clip(a_model.arm_r,  *JOINT_LIMITS).astype(np.float32)
    else:                                             # ee 模式： ablation 项，先验证再切
        a["action.left_ee_pose_gripper_base"]  = a_model.ee_l.astype(np.float32)
        a["action.right_ee_pose_gripper_base"] = a_model.ee_r.astype(np.float32)
    a["action.left_gripper"]  = to_dex1(a_model.grip_l)  # 5.5=开,0=闭；反相即灾难
    a["action.right_gripper"] = to_dex1(a_model.grip_r)
    a["action.pivot"] = np.tile(DEFAULT_PIVOT, (chunk_T, 1)).astype(np.float32)  # 冻结
    return with_time_axis(a, T=chunk_T)               # (T,d) float32 + meta.token
```

**风险**：① 相机物理身份不符（A2 未验证前不得宣称映射正确）→ 影子录制核对；② pivot 冻结导致某些任务无法完成（若任务需要 base 机动）→ 首批 slots  ablation；③ 归一化统计量用错来源 → 干跑第 2 层断言拦截。

### 3.2 IP-15 STEPSCORE-OBJ：步骤分是第一等公民（P0）

**动机**：排序口径=平均成功率与步骤分综合（F:官网原文）；挑战赛页每任务「得分点（满分 100）」。遥操演示约 6 秒/集、含停留与绕路；BC 直接拟合=主动放弃步骤分。且成功率尾部（放置成功后碰翻、抓稳后脱落二次尝试）同样吃步骤分。

**与现有方案的差异**：主流 VLA 训练只优化动作似然；本项把「步数」作为显式优化对象：完成检测早停（L1）+ chunk 大小调度（L2）+ 轨迹级偏好优化（L3 → IP-17b）。三杠杆都不需要新硬件。

**假设（待影子验证）**：A-1 步骤分随步数单调不增；A-2 episode 可能因静止/超限终止。设计对两种公式都稳：成功优先前提下最小化步数。

```python
def stepscore_policy(obs_hist, a_chunk, p_done, steps_used, chunk_T, distractor_flag):
    # L1 早停：连续 k 步高置信完成 → 输出零速保持（不再申请新 chunk 的有效动作）
    if p_done.ewm(alpha=0.5)[-1] > TAU_DONE and hold_streak >= K_DONE:
        return hold_action()                    # 原地保持，杜绝成功后破坏场景
    # L2 chunk 调度：开环 MSE 曲线定 T*；干扰场景缩 chunk（缩短开环暴露）
    T_eff = T_SMALL if distractor_flag else T_STAR
    # L3 偏好信号由 IP-17b 提供；此处只负责产出可比较的行为变体
    return a_chunk[:T_eff]
```

**可行性**：L1 需要一个 done 检测头——特征可用夹爪开合量变化、EE 速度、接触持续性、指令-观测对齐分（小型 MLP/集成，训练用数据集 episode 末段标注自动生成：末段 k 步前的稳定帧=正样本）。L2 纯离线。L3 见 IP-17。

**所需资源**：数据=数据集自带时间戳（免费正样本）；算力=done 头 ~0.1 GPU·天。

**风险**：过早早停误判任务完成→直接失败；用 hold 而非「放弃式静止」，且 done 头要求连续 k 步高置信+滞后阈值；本地以「模拟误停代价」评测门槛（E4）。

### 3.3 IP-17 WM-VERIFY：无仿真器约束下的两条 RL 退化路径（P1）

**动机**：无官方仿真器、无随时可用的真机，「仿真 PPO→sim-to-real」不可行；但 RL 的思想（用奖励筛选/优化行为）仍有两个可落地载体：推理时验证（路径 A）与离线偏好（路径 B）。

**路径 A（推理时，零训练）**：WMA-0 自我定位即「交互式模拟器 + 策略增强」[R8]。采样 K 个候选 chunk → 世界模型前滚 k 帧 → 用轻量任务状态评估器（物体是否在目标区的启发式/学习式判别）给候选打分 → 执行最优 chunk。本质 MPC，天然可消融（关掉即单 chunk 直出）。

**路径 B（离线偏好，零环境交互）metric-DPO**：把我们**自己的多次预约运行**按官方评分（成功率/步骤分）组成同任务偏好对，直接对 VLA 做 DPO。数据来自官方计分本身，零人工标注；约束：仅同任务内配对、仅当两者场景分布可比（场景信息若不可见则只按任务配对并记录噪声）。

**差异**：与通用 RLHF 不同——奖励不是人评模型而是**赛事官方计分函数本身**，与排名指标完全对齐；与「世界模型合成数据 RL」不同——不需要仿真器保真到能训练，只要求在「候选区分」上保真。

**可行性**：A 中：世界模型对接触富集任务（Dex1 夹持、插拔）的保真度是未知数 → E5 专门测；B 中：需要足够多次预约运行（每次=一次数据事件，频率受规则限制，A1 待确认）。

**所需资源**：算力=世界模型推理 K×k 帧/步（预算大，仅对关键步骤启用，IP-10 记账）；数据=自身运行记录（影子录制）+ 公开 Runs 页（F9）。

**风险**：世界模型幻觉导致「选错 chunk 比不选更差」→ E5 门槛：WM 裁判在本地代理指标上必须显著优于随机选 chunk，否则路径 A 冻结；DPO 对同一 checkpoint 重复拟合可能过拟合到场景噪声 → 配对样本加场景桶约束 + 早停。

### 3.4 IP-16 INSTRUCT-AUG：把语音合成的残余价值迁移到语言侧（P1）

**动机**：F10——训练侧每任务 5 条同义句（卡在 meta/tasks.parquet，episode 只挂 task_index）；评测侧 `observation.language` 措辞未知。指令编码稍偏=「做对物体做错目标」。

**方案**：160 句种子 → LLM 句法改写（保持物体/目标槽位不变）→ 嵌入聚类去重保覆盖 → 训练时每 episode 随机采样一条（指令与轨迹解耦=免费增强）；保留 2 句/任务 held-out 只评不训。

**风险**：改写引入物体/目标漂移（改写后的句子指错物体）→ 槽位校验器（改写句必须与原句实体集合一致）强制过滤。可行性：纯离线，~0.05 GPU·天+LLM 调用费。

### 3.5 IP-18 LATENCY-STRICT 与 IP-19 RUN-VIDEO-MINE（P1，简述）

- **IP-18**：F8——延迟均值/波动可能随成绩发布。手段：单模型共享后端+端口级状态隔离（F7 方案 2）、推理异步流水线（obs 到达即预测下一 chunk）、P99 确界测试（继承旧规则 14）、N 端口健康看板。差异：把「延迟」从工程指标升级为可能影响可信度披露的评分邻接量。
- **IP-19**：F9——Runs 页公开完整评测视频。手段：定期抓取自身（及公开可见的他人）运行记录 → 失败视频分类学（抓取滑脱/抓错物体/目标错位/放置碰翻/超时/异常抖动）→ 映射为数据优先级（哪个任务、哪类失败、补什么数据/增强）→ 反哺 IP-7 场景编辑增强。前置于榜单公开，先行搭好抓取与分类骨架。

### 3.6 改锚说明：IP-11R / IP-13R（继承双轨思想，拆除重机械）

- **IP-11R INTENT-GUARD**：输入通道从「可靠手部关键点」改为 4 相机流的轻量视觉干扰检测（人形/手部进入工作区的检出与轨迹，~1MB 级检测器，<2ms）；威胁度驱动模式 m∈{EXEC,DEFEND}。动机：F4 已证实评测侧无人体现成通道。
- **IP-13R SAFE-ARB-LITE**：拆除 TV-LQR/QP/LUT 全链条，仅保留双轨兜底思想：异常检测（动作幅度/熵/重复模式异常 + 干扰标志）→ 冻结回退（零速保持+夹爪维持），回退率遥测（继承 13-3）。动机：竞赛里「冻结」几乎总是比「让位」更安全也更 step-友好。

## 4. 实验设计（门槛制，任一不过即冻结对应 IP）

| 实验 | 设置 | 指标 | 门槛 |
|---|---|---|---|
| E1 桥接三层干跑 | 单元/回放/影子三级 | 映射零错、数值往返误差<1e-3、影子与视频对齐 | 全过方可提交（IP-14 上线条件） |
| E2 开环基准 | 留出 episode 的动作 MSE / 任务状态分类 | MSE、完成时刻误差 | 不低于 BC 基线（后续所有项的公共基线） |
| E3 joint vs ee 模式 | 同模型两种 control_space 各 2 任务 | 成功率/步骤分/异常率 | 显著差异才切换，否则默认 joint |
| E4 早停验证 | done 头 + 模拟误停代价 | 误停率、每任务平均步数降幅 | 误停导致的失败=0；步数降幅≥10% |
| E5 世界模型裁判 | 本地候选集 + WM 打分 vs 随机 vs 单发 | 候选区分准确率 | 显著优于随机，否则路径 A 冻结 |
| E6 metric-DPO | 同任务配对运行 + DPO | 成功率/步骤分变化 | 不得低于 DPO 前基线（可一键回退） |
| E7 指令鲁棒性 | held-out 改写句 | 同模型两种措辞的成功率差 | 差值 <5pt |

**降级机制**：全部组件满足「可一键消融、消融后不低于 BC 基线」（规则 19）；不满足即冻结，系统回退 BC+桥接，无负收益。

## 5. 风险登记簿

| 风险 | 等级 | 缓解 |
|---|---|---|
| 静默错映射（相机身份/夹爪反相/pivot） | **高** | E1 三层干跑；影子录制对齐 Runs 视频（A2） |
| 步骤分公式/终止模式未知（A-1/A-2） | 高 | 假设显式化+影子验证；设计对两公式均稳 |
| WMA-0 世界模型对接触任务保真不足 | 高 | E5 门槛不过即冻结路径 A |
| DPO 配对受场景分布噪声污染 | 中 | 同任务+场景桶约束+早停 |
| 影子录制的合规性（规则未公开） | 中 | A1 拿手册确认前只录不传、仅自用 |
| UnifoLM-VLA NC-SA 许可边界 | 中 | A3 合规确认；必要时自训小模型备胎 |
| 榜单/头部方案不可核实导致决策盲飞 | 中 | IP-19 骨架先行；不引用未核实数字（规则 18） |
| N 端口/N 机器人资源配置未知 | 中 | 按 3~8 规划，共享后端方案 2 |
| 训练算力不足（8B VLA 全参） | 中 | LoRA 优先（冻结视觉编码器）；IP-10 记账 |

## 6. 来源清单（检索/核实于 2026-11-07）

- R1 官网首页 https://unibot.unitree.com （单模型多任务口径）
- R2 挑战赛页 https://unibot.unitree.com/challenges.html （32 任务/32000 集/169 小时；每任务步骤分满分 100；提交流程 7 步）
- R3 排行榜页 https://unibot.unitree.com/leaderboard.html （Coming Soon；按平均成功率与步骤分综合排序）
- R4 提交模板 https://github.com/unitreerobotics/unibot_submission （README/example_policy/example_env/web_policy 源码：接口、JPEG q95 4:4:4、N 端口、延迟可信度条款）
- R5 规则手册（飞书，需登录，不可核实）https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cCW1CnMh
- R6 运行记录页 https://unibot.unitree.com/runs.html （Coming Soon；完整评测视频）
- R7 数据集集合 https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset （32 个 G1_Dex1_*，更新于 Sep 11）
- R8 HangCup 数据集卡+meta（tasks.parquet 五句同义@分隔；info.json 30fps/4 相机/AV1；Dex1 5.5→0）
- R9 UnifoLM-VLA-0 https://huggingface.co/unitreerobotics/UnifoLM-VLA-Base 与 https://github.com/unitreerobotics/unifolm-vla （Qwen2.5-VL 骨干、Jan 29 2026、单策略 12 类任务、CC BY-NC-SA 4.0）
- R10 UnifoLM-WMA-0 https://huggingface.co/unitreerobotics/UnifoLM-WMA-0-Base （世界模型=模拟器+策略增强；license 标注矛盾；gated）
- R11 HangCup 数据行实证（datasets-server rows API：pivot 语义、base_command、无 per-episode 语言字段、动作/观测全键清单）

## 7. 清单迭代规则（继承 + 第 1 轮新增）

- 继承：12（一切新策略必须双轨兜底）、13-1~13-4、14（P99 确界报告）、15。
- **16（新增）**：一切键映射/单位/方向/符号约定必须过 E1 三层干跑，未过不得上线；映射表即代码，纳入版本管理。
- **17（新增）**：影子录制数据仅用于自身迭代；对外发布前必须确认规则手册许可（A1 行动项闭环）。
- **18（新增）**：任何未公开/未核实的榜单或第三方成绩数字不得写入事实卡；用户口径必须显式标注。
- **19（新增）**：任何训练出来的组件必须可一键消融，消融后系统能力不低于 BC+桥接基线；不满足即冻结并登记降级路径。

---

**本轮最大风险一句话**：规则手册不可核实使「步骤分公式/episode 终止模式/相机物理身份」全部悬置——在这些假设被影子录制验证前，所有上层优化都建立在流沙上。

**本轮最值得押注**：IP-14 BRIDGE-0（桥接+三层干跑+影子录制）——它是防归零的保险，也是把稀缺预约评测变成持续数据资产的飞轮入口。
<!-- ARTIFACT:END -->
