# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 27 轮 · 「碰撞避免 × 夹爪控制 × 强化学习」：三词全部落在"最后一厘米"——SAFE-FILTER 护盾 / GRIP-GATE 夹爪门控 / GRIP-RL 窄域世界模型优化

## 0. 轮次编号与信息核实（先严谨，再发散）

**编号说明**：状态文件已保留第 26 轮（灵感词：低成本方案/群体智能/SLAM）；本轮模板仍写"第 1 轮"。按「优先深化与修剪、不推倒重来」元规则，本轮记为**第 27 轮**，三个新灵感词作为对 v2 清单（10 项）的深化输入。

**本轮检索核实（全部检索于 2026-11-07）**：

- **官方三页重验**：排行榜/运行记录仍"Coming Soon"[R1/R2]；challenges 页口径不变（32 任务/32000 演示/169h/得分点 100 分/七步提交流程）[R1a]。F7/F8 未解除。
- **接口 repo 未变**：仍 2 commits（最新 2026-08-21 "version 2, support observation-based frame-skipping stacking"），README 全文重读 [R3]，消化出三个此前未点破、且**全部利好本轮灵感词**的事实：
  1. 评测观测含 `observation.state.left_arm/right_arm[7]`（双臂**关节角**，"Left arm joint state"）→ 我方可在评测端做正运动学，双臂胶囊体自碰撞建模完全可行（F15；上两轮只盯 ee pose，漏了关节角这个键）；
  2. 评测观测含 `observation.state.left_gripper/right_gripper[1]`（描述为"**gripper opening**"，即实测开度）→ 夹爪**闭环**（指令 vs 实开度）与闭合后验证可行（F15）；
  3. `obs_delta_indices` 的键即传输选择器（只声明才传输），任意**状态键**可做 ≤0 偏移时间堆叠（不足补首帧）→ 速度/加速度特征零成本获取；`image_resize` 由评测端服务侧完成（F17）。
- **数据集卡片重读**：**Dex1 夹爪为连续行程 5.5（开）→ 0.0（合）**；数据集动作表另有 `gripper_controls[4]`（left/right trigger+squeeze）**但评测动作目录无此键**——评测侧夹爪只有 1 维连续指令，训练监督直接用 `action.left/right_gripper`（F16）。HangCup 规模不变（1.04k episodes/194,564 行/8.8 GB），collection 32 项更新日期仍 2026-09-11 [R4]。
- **文献锚点（arXiv API 逐一核实，https 修正后全部命中）**：iRe-VLA [R6a]、VLA-RL [R6b]、SimpleVLA-RL [R6c]、RIPT-VLA [R6d]、GRAPE [R6e]、Recovery RL [R6f]、CBF 无碰撞食品操作 [R6g]、双臂全身运动规划（重叠运动链自碰撞）[R6h]、不确定性感知预测 CBF（人机交互）[R6i]、AnyGrasp [R6j]、VILAS（VLA 一体化软抓取架构）[R6k]、未来观测估计抓取成功 [R6l]、TD-MPC2 [R6m]。

**结论**：无与上轮冲突的事实；F7/F8 仍是最大信息缺口；F15-F17 是本轮三个"白捡"的接口利好，全部直接服务三个灵感词。

## 1. 三个灵感词拼出的图（直觉先行）

> **碰撞避免**回答「怎么不输掉整局」：32 任务含双手协调，双臂在头顶共享工作区；VLA 在演示分布内很少自碰，但五类扰动场景把策略推进 OOD，一次双臂互锁或撞翻干扰物=整局归零。<30% 的头部格局下，**尾部风险的结构性保护**比期望值提升更便宜。且碰撞避免不止"自保"：人为干扰场景里人手会伸进工作区——检测人手→预测轨迹→让位缓冲区，正是第 26 轮展望预告的"干扰响应链"的动作端。锚点：CBF 食品操作 [R6g]、双臂重叠运动链规划 [R6h]、预测 CBF-HRI [R6i]、Recovery RL [R6f]。
> **夹爪控制**回答「最后一厘米」：抓取族任务的失败大多不在"去哪儿"，而在"合拢那一刻"——合早了物体没到位、合晚了碰飞、开度不对夹空或夹飞。**F16 是本轮最大红利：Dex1 是连续行程（5.5→0.0），不是二值开合**——"何时合、合多拢"两个连续决策都可供工程；且观测回报实测开度，闭环验证与失败重抓成为可能。演示数据还送一份免费监督：闭合触达瞬间的指令开度≈物体宽度，(腕图 crop, 开度) 对就是现成的宽度回归训练集——零标注成本。
> **强化学习**回答「示范没教的部分」：全量 VLA RL（iRe-VLA/VLA-RL/SimpleVLA-RL 路线 [R6a/R6b/R6c]）需要环境与奖励——评测无环境、真机无自采（COST-LADDER 红线），**整策略 RL 进拒绝清单**。但"最后一厘米"恰好是个例外：动作空间极窄（闭合时机偏移+开度+±2cm 修正）、视界 ≤2s、奖励可自监督（抓取成功分类器+IP-2 进度增量+几何碰撞罚）——**用演示+合成扰动训一个结构化（任务级）世界模型，在里面优化这个窄动作空间，再蒸馏回 GRIP-GATE 头**。这是 RL 唯一能过成本账的入场方式。锚点：TD-MPC2 [R6m]、RIPT-VLA [R6d]、GRAPE [R6e]。

核心类比（本轮灵魂）：**碰撞避免是"考试先保证不涂破答题卡"；夹爪控制是"最后落笔那一格要又准又稳"；强化学习是"没有标准答案的题，先在心里搭一个出题人（世界模型），自己出题自己练，练会了只把手感带进考场"。**

一句话押注：

> **本轮新增 IP-11 SAFE-FILTER（动作护盾）/ IP-12 GRIP-GATE（夹爪门控）/ IP-13 GRIP-RL（窄域世界模型 RL），三者共享"最后一厘米"微管线；最值得押注 GRIP-GATE——近零成本、不依赖 F9 深度链路、直击抓取族任务与未见物品场景，且 F15/F16 两个接口事实刚刚证实其全部可行性。**

## 2. 研究日志：三词各自戳中哪个瓶颈（承接四层分解）

| 瓶颈层 | 碰撞避免的戳点 | 夹爪控制的戳点 | 强化学习的戳点 |
|---|---|---|---|
| 数据层（无失败恢复数据） | 合成碰撞/人手轨迹=免费尾部数据 | 演示自带 (腕图, 开度) 免费标签；失败重抓可规则化 | 世界模型+CEM 在演示静默区自造经验 |
| 表征层（无结构化扰动表征） | 地图加碰撞层（keep-out 体积） | 腕图 crop+开度序列=接触态表征 | 结构化世界模型=任务级动力学表征 |
| 目标函数层（训练-评测错位） | 几何约束不依赖训练分布 | 抓取成功分类器=可验证代理奖励 | 窄域+代理奖励=错位最小化 |
| 工程层（尾部风险/可信度） | 最小介入投影+delta 限幅+遥测 | 闭环验证+重抓状态机 | 蒸馏回门控头=评测零额外延迟 |

观察：三词罕见地汇聚在同一个子系统（approach→grasp→lift→carry→place 的末段），而不是各开一条战线——本轮的"创新密度"来自**把三个词焊在同一条微管线上**，且三个新 IP 全部挂在已有资产（IP-1 地图/IP-2 奖励/IP-4 挂载点/IP-7 扰动合成）上，符合 COST-LADDER。

## 3. 灵感词交点（组合即创新）

- **碰撞避免 × 夹爪控制 = 携行安全**：抓着物体时物体成为手臂的延伸胶囊（held-object capsule）；放置前最后 3cm 降速接近；非目标 slot 全程 keep-out（防撞飞干扰物——干扰物场景可能的隐性扣分点）。
- **夹爪控制 × 强化学习 = 最后一英寸 RL**：动作空间 (t_close 偏移, 开度, ±2cm 修正) 足够窄，世界模型奖励 (P_grasp+Δprogress) 足够可验证——RL 在这里不是豪赌而是精修。
- **碰撞避免 × 强化学习 = 安全评论家**：Recovery RL 式 Q_risk(s,a) [R6f] 作解析过滤器的兜底（几何覆盖不了的柔性接触情形），P2 可选不投入主线。
- **三词交点 = grasp-carry-place 微管线**：GRIP-GATE（何时合/合多拢/失败即重抓）→ SAFE-FILTER（携行穿越共享工作区）→ WM-RL（离线在世界模型里联合优化微决策后蒸馏回门控头）。三者全部离线可训、部署为轻量插件、不新增稀缺资源消耗。

## 4. 与第 26 轮清单的深化/修剪决策

| 清单项 | 本轮处置 | 依据 |
|---|---|---|
| IP-1 SLAM-MAP | 深化：地图新增**碰撞层**（keep-out 体积：桌面/非目标 slot/人手预测缓冲区），供 SAFE-FILTER 消费 | 灵感词 碰撞避免 |
| IP-2 SCORE-ALIGN | 深化：进度预测器新增第三消费者——GRIP-RL 奖励项 | 灵感词 RL |
| IP-3 LOCAL-EVAL | 维持；新增回放验证 FK 胶囊/开度语义的接口探针（A6/E12 前置） | 本轮 F15/F16 |
| IP-4 SUBMISSION-OPS | 维持；sanitize() 扩展为 SAFE-FILTER 挂载点+delta 遥测 | 灵感词 碰撞避免 |
| IP-5 DUAL-HEAD | 冻结维持 P2 | F8 未解 |
| IP-6 UNSEEN-GRASP | 维持指针；GRIP-GATE 承接其"动作端"（先看后抓→合拢验证） | 去重协同 |
| IP-7 DISTURB-AUG | 深化：合成扰动额外产出**失败邻近状态**（world model 训练集）与安全评论家标签 | 灵感词 RL×碰撞 |
| IP-8 STEP-EFF | 维持 P1 | F8 未解 |
| IP-9 SWARM-DECODE | 维持 P1 | — |
| IP-10 COST-LADDER | 深化：拒绝清单新增 #7/#8（§5）；三个新 IP 过记账 | 纪律 |
| — | **新增 IP-11 SAFE-FILTER** | 碰撞避免 |
| — | **新增 IP-12 GRIP-GATE** | 夹爪控制 |
| — | **新增 IP-13 GRIP-RL**（P2，门控） | 强化学习 |

无删除项；v2 十项全部保留，本轮净增三项且都挂在已有资产上。

## 5. 风险与本轮最大风险

**最大风险：IP-13 的「世界模型被利用」——CEM 优化器会精准攻击结构化世界模型的误差（尤其抓取成功分类器的过自信区），离线指标漂亮、真机拉胯；而本地-官方相关性（F8）未验证，无法兜底。** 缓解：①动作空间与视界压到最小（3 维、≤2s、±2cm）；②held-out 真演示回放为唯一验收通道，合成 rollout 分数只作参考；③OOD 动作频次监控（模型利用检测器）；④产出以"蒸馏回 GRIP-GATE 头"为唯一出口，不过阈即整体回退模仿门控（沉没成本封顶 2-4 GPU·天）。

其余新增风险：④SAFE-FILTER 过保守降低成功率/步骤分（缓解：只约束四类硬约束，目标物接触豁免；delta 限幅+斜坡；E12 消融）；⑤运行时改动作触碰 §6 可信度条款（缓解：delta 平滑限幅+全量遥测+提交材料声明安全模块，待 A1/A5 澄清）；⑥夹爪开度值域语义（评测端是否同样 5.5→0.0）未实测（缓解：A6 用 example_env 桩+数据集回放验证，P1）。

## 6. 下一轮展望（灵感未知）

- 若灵感指向「触觉/力控」→ Dex1 无触觉通道，深化"视觉代偿触觉"（腕图微振动/光流滑移检测），与 GRIP-GATE verify 串联成完整接触感知链；
- 若灵感指向「课程学习/自动课程」→ GRIP-RL 的世界模型天然支持难度课程（扰动幅度递增），与 IP-7 注入器合并成课程化训练；
- 若 F7/F8 解除 → 立即触发强制修订：榜单+评测视频拆解对手的抓取时机与碰撞行为（对手是否也有安全层，视频里一眼可见）。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 27 轮产物 · 创新点清单 v3：SAFE-FILTER / GRIP-GATE / GRIP-RL——"最后一厘米"微管线

## 0. 结论

第 26 轮清单 v2（10 项）本轮完成「深化 + 净增三项」迭代，产出 v3（13 项）：

- **IP-11 新增 SAFE-FILTER（P1）**：模型无关的动作护盾——FK 胶囊体自碰撞 + 桌面/非目标 slot/人手预测 keep-out 的 CBF-lite 最小介入投影；CPU <5ms，尾部风险的结构性保护。
- **IP-12 新增 GRIP-GATE（P0，本轮押注）**：Dex1 连续行程上的三合一夹爪门控——宽度自适应开度 + 闭合时机预测头 + 闭合验证/失败重抓；近零成本，不依赖 F9 深度链路。
- **IP-13 新增 GRIP-RL（P2，门控）**：窄域世界模型 RL——3 维动作（闭合时机/开度/±2cm 修正）、≤2s 视界、结构化世界模型 + CEM、蒸馏回 GRIP-GATE 头；全策略 RL 进拒绝清单。
- IP-1 加碰撞层、IP-2 加第三消费者、IP-7 加失败邻近状态、IP-10 拒绝清单 +2 条；无删除项。

三词全部落在"最后一厘米"微管线（approach→grasp→lift→carry→place 末段），三个新 IP 共享资产、互为上下游，是本轮创新密度来源。路线无关原则不变：IP-11/12/13 均以可消融插件接入，不绑死主模型。

## 1. 事实卡更新（检索日期 2026-11-07）

F1-F14 与第 26 轮一致（本轮重验：官方三页仍 Coming Soon [R1/R1a/R2]；repo 仍 2 commits，最新 2026-08-21 [R3]）。新增：

| # | 事实 | 来源 |
|---|---|---|
| F15 | 评测观测含双臂关节角 `observation.state.left_arm/right_arm[7]`（joint state）与夹爪实测开度 `observation.state.left_gripper/right_gripper[1]`（"gripper opening"）→ 评测端 FK 自碰撞建模与夹爪闭环验证可行 | [R3] |
| F16 | Dex1 夹爪连续行程 5.5（开）→0.0（合）；数据集动作表有 `gripper_controls[4]`（trigger/squeeze）但评测动作目录无此键 → 评测侧仅 1 维连续夹爪指令；训练监督直接用 `action.left/right_gripper` | [R3][R4] |
| F17 | `obs_delta_indices` 键=传输选择器，任意状态键可做 ≤0 偏移堆叠（不足补首帧）→ 速度特征零成本；`image_resize` 由评测端服务侧完成 | [R3] |
| F18 | 官方三页重验仍 Coming Soon；repo 仍 2 commits，规则未变；HangCup 规模与 collection 更新日期不变 | [R1/R2/R3][R4] |

行动项：A1-A5 不变；**A6（新增，P1）**：example_env 桩+数据集回放验证 (a) FK 所用关节角量纲/顺序，(b) 评测开度值域是否同样 5.5→0.0（决定 GRIP-GATE 指令映射）。

## 2. 创新点清单 v3 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-1 | SLAM-MAP v3 | 四件套+碰撞层（keep-out 体积） | P0 | 无 | SLAM×碰撞 | 算力(轻)+伪标注 | 位置/未见/人为干扰 +5~15pt | 深化 |
| IP-2 | SCORE-ALIGN | 过程奖励+进度裁判+RL 奖励源 | P0 | 无 | 评测指标 | 重标注近零 | 步骤分+部分分 | 深化 |
| IP-3 | LOCAL-EVAL | 零真机闭环+群体/接口探针 | P0 | IP-2 | 低成本×群体 | 算力(1 GPU) | 迭代速度=生命线 | 维持 |
| IP-4 | SUBMISSION-OPS | N端口/延迟/容错+安全挂载点 | P1 | 无 | 竞赛×群体 | 部署机 | 免费工程分层 | 深化 |
| IP-5 | DUAL-HEAD | 单模型双解码头 | P2(冻结) | IP-1 | 25轮 | 算力 | 视合规 | 维持 |
| IP-6 | UNSEEN-GRASP | 先看后抓（闭环+动作端） | 指针 | IP-1/12 | SLAM | 共享 | 未见物品 | 维持 |
| IP-7 | DISTURB-AUG | 扰动合成+失败邻近状态+安全标签 | P1 | 无 | 25轮×RL | 数据(合成) | 人为干扰 | 深化 |
| IP-8 | STEP-EFF | 步骤分效率工程 | P1 | A1 | 25轮 | 零 | 步骤分 | 维持 |
| IP-9 | SWARM-DECODE | soup/蒸馏+自洽投票 | P1 | IP-2 | 群体智能 | LoRA×K 一次性 | +2~5pt | 维持 |
| IP-10 | COST-LADDER | 三账户+拒绝清单(+2 条) | P0(纪律) | 无 | 低成本 | 全账户 | 防负 ROI | 深化 |
| IP-11 | SAFE-FILTER | CBF-lite 动作护盾 | P1 | IP-4(+IP-1 部分) | 碰撞避免 | CPU <5ms | 尾部风险保护+人为干扰 | **新增** |
| IP-12 | GRIP-GATE | 何时合/合多拢/失败重抓 | P0 | 无(IP-1 可选) | 夹爪控制 | 1-2 GPU·天 | 抓取族 +3~8pt | **新增（押注）** |
| IP-13 | GRIP-RL | 窄域世界模型 RL→蒸馏回门控 | P2(门控) | IP-2/7/12 | 强化学习 | 2-4 GPU·天 | 扰动场景 +2~5pt | **新增** |

## 3. 重点展开一：IP-11 SAFE-FILTER（碰撞避免）

### 3.1 约束集合——只管四类硬约束，任务必需接触豁免

| 约束 | 几何建模 | 数据来源（全部评测可得） |
|---|---|---|
| 双臂自碰 | 每臂 3 段胶囊（上臂/前臂/手+held-object），FK 由关节角直算，最小间距 d_min≈6cm | F15 关节角 [R3] + 开源 G1 URDF |
| 臂-桌面 | 胶囊 vs 桌面平面（TABLE_Z 先验） | 任务先验 |
| 臂-非目标物 | 胶囊 vs slot keep-out 圆柱（半径=slot 半宽+3cm 裕量） | IP-1 碰撞层 |
| 臂-人手 | 胶囊 vs 人手预测缓冲区（头图检测框经外参反投影 + 匀速外推 300ms） | 头图检测 + IP-1 外参（锚点 [R6i]） |

**目标 slot 的接触不进约束集**——抓取/放置必须接触，过滤器豁免之（防过保守）。

### 3.2 CBF-lite 最小介入投影

对每个约束维持 h_i(x)≥0；动作修正解一阶 CBF 条件的投影：

```
a' = argmin_a ||a - a_raw||²
     s.t. h_i(x_{t+1}(a)) + γ·h_i(x_t) ≥ 0   ∀i∈C    （线性化后每约束一条标量不等式）
```

4-8 个标量不等式的低维 QP，解析/少迭代可解，<5ms CPU。附加两道保险：**delta 限幅**（|a'-a_raw|≤DELTA_MAX）与**斜坡限频**（连续步 delta 变化率受限）——保证返回动作统计平滑，规避 §6 可信度条款（[R3] §6）。锚点：CBF 食品操作 [R6g]（安全集公式与 γ 调法）、双臂重叠运动链 [R6h]（胶囊建模）、Recovery RL [R6f]（安全评论家兜底，P2）。

### 3.3 伪代码

```python
def shield(action_chunk, obs, sem_map):
    q = fk_state(obs.state.arm_l, obs.state.arm_r, obs.state.lower_body)   # F15
    caps = arm_capsules(q)
    if sem_map.held is not None:
        caps += held_object_capsule(obs.state.gripper_l, sem_map.held)     # 携行延伸胶囊
    hand_zone = predict_hand_zone(obs.images.cam_high, sem_map)            # 人手外推 300ms
    for t, a in enumerate(action_chunk):
        q_next = integrate(q, a)                     # joint 模式直积分; ee 模式走增量 IK
        C = violations(q_next, caps, sem_map.keepout, hand_zone, TABLE_Z)
        if C:
            a2 = project_cbf_lite(a, C, step_limit=DELTA_MAX)              # 最小介入
            a2 = ramp_limit(a2, prev_action)                               # 斜坡限频
            telemetry.log_delta(a, a2)                                     # §6 遥测
            a = a2
        q = q_next
    return action_chunk
```

### 3.4 成本账（COST-LADDER）

算力-推理 +<5ms/步（CPU）；数据 0（几何+地图复用）；评测时段 0。边际分预期：不提升上限、抬高地线——碰撞导致的整局失败→0（E12 验证成功率降幅 <0.5pt），人为干扰场景受益于人手缓冲区。

## 4. 重点展开二：IP-12 GRIP-GATE（夹爪控制，本轮押注）

### 4.1 三组件

1. **宽度估计（免深度，不依赖 F9）**：腕图 bbox 高度 × 标定距离→公制宽度。距离来源：腕相机刚连于 ee，抓取平面距离≈ee 高度−桌面高度（F15 的 ee pose 直得）。**训练集免费**：演示中闭合触达瞬间的指令开度≈物体宽度（F16 连续行程给分辨率），(腕图 crop, 开度) 对即自监督回归标签。锚点：AnyGrasp 的视觉抓取宽度 [R6j]。
2. **闭合时机头**：轻量 aux head，输入 chunk 内腕图堆叠 + ee/夹爪速度序列（F17 免费堆叠）→ 预测 chunk 内最优闭合步 t*；标签=演示夹爪指令的下降沿（5.5→x 的跳变点），焦点 CE 损失。
3. **验证-重抓状态机**：闭合后 3 帧检查：实测开度 vs 指令开度差 < 阈（物体真的被夹住）且腕图目标仍在视野；失败→微策略：重开→退 2.5cm→再进（最多 1 次，防步骤分崩坏）。锚点：未来观测估计抓取成功 [R6l]。

### 4.2 伪代码

```python
class GripGate:
    def modulate(self, chunk, obs, slot=None):
        w = self.width_est(obs.images.cam_wrist, obs.state.ee_pose)   # 公制物宽（免深度）
        ap = clamp(w + MARGIN, lo=AP_MIN, hi=5.5)                     # 目标开度; 0=全闭禁用
        t_close = self.head(obs.wrist_stack, obs.ee_vel)              # chunk 内最优闭合步
        for t, a in enumerate(chunk):
            a.gripper = OPEN_CMD if t < t_close else ap
        ok = self.verify(obs, slot)          # 实开度≈指令 且 目标仍在腕图
        if not ok:
            chunk = self.regrasp(chunk, off=2.5)                      # 重开-退-再进（≤1 次）
        return chunk
```

### 4.3 边界与合规

- **不替换 VLA 的抓取决策**（何时抓哪个由主模型+地图定），只在夹爪通道做窄域调制——与 VILAS 式软抓取 [R6k] 的区别：不引入外部抓取检测器，保持单模型。
- 连续开度避免"全闭合指令怼进物体"（0.0 指令在未触达时是空合、触达后是推挤）——软抓取行为的免费来源。
- 训练 1-2 GPU·天（aux head，LoRA 级）；推理 <10ms；数据 0。边际分预期：抓取族任务 +3~8pt，未见物品场景受益于宽度自适应。
- A6 未验证开度值域前，不进入正式训练队列（迭代规则 9）。

## 5. 重点展开三：IP-13 GRIP-RL（强化学习，P2 门控）

### 5.1 为什么只有窄域 RL 过成本账

```
全策略 RL:  需要环境(评测无环境/真机红线) + 奖励(官方只给终局) + 算力(>>40 GPU·天)  → 拒绝清单 #7
窄域 RL:   动作 3 维(t_close 偏移, 开度, ±2cm 修正) + 视界≤2s + 奖励自监督 + 结构化世界模型 → 2-4 GPU·天 ✓
```

### 5.2 结构化世界模型 W（任务级，非像素级）

```
输入 s_feat = slot 特征(IP-1: 位置/尺寸/外观) + ee/夹爪运动特征(F17 免费堆叠) + 任务嵌入(语言编码)
输出 Δ = { P_grasp, Δprogress, collide_count }        # 抓取成功概率/进度增量/碰撞计数
训练集 = 32k 官方演示 + IP-7 合成扰动 rollout（失败邻近状态——演示分布静默区）
锚点: TD-MPC2 的"在习得模型中规划"思想 [R6m]; 表征为结构化特征而非隐空间像素(拒绝清单 #8)
```

### 5.3 优化与蒸馏出口

```
a* = CEM(W, R),  R = P_grasp + λ1·Δprogress + λ2·collide_penalty     # CEM 在 3 维动作上极快
蒸馏: 最优 (t_close, ap, Δee) 决策回归进 GRIP-GATE 头 → 评测时零额外延迟、交付仍是单模型单权重
```

### 5.4 模型利用守则（四道闸，对应本轮最大风险）

1. held-out 真演示回放为**唯一**验收通道（合成 rollout 分数只作参考）；
2. OOD 动作频次监控——CEM 解偏离演示动作流形的比例 <1%；
3. 奖励分量消融——防抓取成功分类器过自信区被利用；
4. 不过阈即整体回退模仿门控（沉没成本封顶 2-4 GPU·天）。

### 5.5 与 RL-VLA 文献的关系

iRe-VLA/VLA-RL/SimpleVLA-RL/RIPT-VLA [R6a/R6b/R6c/R6d] 证明"RL 后训练提升 VLA"这一方向真实有效，但它们的共同前提是**可交互环境**——本赛制恰好不提供；GRIP-RL 是把该方向压缩到"无环境也能做"的最小子问题上的翻译，GRAPE [R6e] 的偏好对齐思想则保留为未来若获环境后的升级路径。

## 6. 其余 IP 修订摘要（v2→v3 增量）

- **IP-1**：地图服务新增 `register_keepout(volume)` 接口（桌面/非目标 slot/人手缓冲区），SAFE-FILTER 消费；外参前向模型同步服务人手反投影。
- **IP-2**：进度预测器第三消费者=GRIP-RL 奖励项；代理奖励与官方得分点的一致性继续依赖 A1 回填。
- **IP-3**：新增接口探针（A6：FK 量纲/开度值域）；群体探针不变。
- **IP-4**：sanitize() 扩展为 SAFE-FILTER 挂载点；遥测新增 delta 统计（§6 可信度自证材料）。
- **IP-5/IP-8/IP-9**：维持。
- **IP-6**："先看后抓"的感知端在 IP-1 腕-头闭环，动作端由 GRIP-GATE 承接（闭合验证即"看"的最后一个消费点）。
- **IP-7**：注入器新增产出类型——失败邻近状态（供 world model）与约束违反标签（供安全评论家，P2）。
- **IP-10**：拒绝清单新增 **#7 不做全策略 VLA RL（无环境/无奖励/超预算）——RL 只进"最后一厘米"窄域**；**#8 不做像素级世界模型/视频生成——世界模型只做结构化特征级**。

## 7. 实验设计（新增 E12-E15，接第 26 轮 E1-E11）

| 实验 | 设置 | 指标 | 预期 |
|---|---|---|---|
| E12 安全过滤器 | 回放评测+注入双臂冲突/越桌/撞非目标物轨迹（合成 OOD chunk） | 碰撞事件率 / 成功率降幅 / delta 分布平滑度 | 碰撞→0；成功率降幅 <0.5pt；delta 分布纳入冒烟 CI |
| E13 夹爪门控 | 演示回放：固定规则夹爪 vs 宽度自适应+时机头 | 抓取成功代理率（开度-视觉一致性）/ 误闭合率 | 代理成功率 +5pt；误闭合 -50% |
| E14 世界模型 RL | held-out 真演示+合成扰动 rollout；模仿门控 vs RL 门控（四道闸全开） | 扰动态代理成功率 / OOD 动作频次 / 真演示验收分 | 扰动态 +3pt；OOD 频次 <1%；不过阈即回退 |
| E15 人手避让 | 合成人手轨迹注入（速度/角度扫频） | 干扰引发失败率 / 让位触发率 / 误让位率 | 干扰失败 -30%；误让位 <5% |

提交纪律不变：冒烟 CI + 单变量 + 48h 校准报告；E12 的 delta 分布与 E13 的开度序列纳入 CI 检查项。

## 8. 风险登记簿（增量；第 26 轮其余行继续有效）

| 风险 | 等级 | 缓解 |
|---|---|---|
| IP-13 世界模型被利用（离线好真机差） | **高（本轮最大）** | 四道闸（§5.4）+ 沉没成本封顶 + 蒸馏头可整体回退 |
| SAFE-FILTER 过保守拉低成功率/步骤分 | 中 | 任务必需接触豁免 + delta 限幅 + E12 消融 |
| 运行时改动作触碰 §6 可信度条款 | 中 | delta 平滑限频 + 全量遥测 + 提交材料声明安全模块（待 A1/A5） |
| 评测开度值域语义未实测（F16 侧） | 中 | A6 探针；未过验不进训练队列（迭代规则 9） |
| GRIP-GATE 重抓微策略与步骤分冲突 | 低 | 重抓限 1 次；步骤分公式确认后（IP-8/A1）再定阈值 |

## 9. 来源清单（全部检索于 2026-11-07）

- R1 排行榜页（重验仍 Coming Soon）：https://unibot.unitree.com/leaderboard.html
- R1a 挑战赛页（32 任务/32000 演示/169h；七步提交流程）：https://unibot.unitree.com/challenges.html
- R2 运行记录页（重验仍 Coming Soon；"完整评测视频"承诺）：https://unibot.unitree.com/runs.html
- R3 提交接口规范（重读：§2 观测目录含 left/right_arm[7] 与 left/right_gripper[1]；§3 动作目录；obs_delta_indices 键=传输选择器；§6 可信度条款；repo 仍 2 commits，最新 2026-08-21）：https://github.com/unitreerobotics/unibot_submission
- R4 数据集卡片（Dex1 Gripper 行程 5.5→0.0；gripper_controls[4] 仅数据集侧；1.04k/194,564 行/8.8 GB）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup ；collection：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- R6 文献锚点（arXiv API 核实，2026-11-07）：
  - R6a iRe-VLA（在线 RL 改进 VLA）: https://arxiv.org/abs/2501.16664
  - R6b VLA-RL: https://arxiv.org/abs/2505.18719
  - R6c SimpleVLA-RL: https://arxiv.org/abs/2509.09674
  - R6d RIPT-VLA（Interactive Post-Training）: https://arxiv.org/abs/2505.17016
  - R6e GRAPE（偏好对齐泛化机器人策略）: https://arxiv.org/abs/2411.19309
  - R6f Recovery RL（学习恢复区）: https://arxiv.org/abs/2010.15920
  - R6g Safety-Critical Manipulation for Collision-Free Food Preparation（CBF）: https://arxiv.org/abs/2205.01026
  - R6h Dual-Arm Whole-Body Motion Planning（重叠运动链）: https://arxiv.org/abs/2511.08778
  - R6i Uncertainty-Aware Predictive CBF（HRI 概率运动预测）: https://arxiv.org/abs/2508.20812
  - R6j AnyGrasp（时空抓取感知）: https://arxiv.org/abs/2212.08333
  - R6k VILAS（VLA 一体化低成本软抓取）: https://arxiv.org/abs/2605.02037
  - R6l 生成未来观测估计抓取成功: https://arxiv.org/abs/2403.07877
  - R6m TD-MPC2: https://arxiv.org/abs/2310.16828
- 第 25/26 轮来源（R5a-R5g 等）本轮未逐一重抓，口径以对应轮记录为准。

## 10. 清单迭代规则（增补，继承第 25/26 轮 §10）

0-8.（继承）事实卡核对 / COST-LADDER 记账 / 对手视频锚定等规则全部有效；
9.（新增）**接口事实依赖校验**：新 IP 立项时必须声明所依赖的接口事实（本轮 F15/F16/F17）；该事实被证伪时，相关 IP 24h 内降级或改道；A6 未完成前 GRIP-GATE 不进正式训练队列；
10.（新增）**窄域原则**：任何"训练类"新 IP 必须先回答"动作空间多窄、视界多短、奖励是否自监督"——三者任一不满足即默认进拒绝清单。
<!-- ARTIFACT:END -->