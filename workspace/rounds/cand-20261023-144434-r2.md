# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 0. 本轮结论

> 最值得押注的不是“再训一个更大的端到端 VLA”，而是给开源 VLA 加一层竞赛层：把官方评分点编译成可验证的阶段进度，用已校正的双目做物体中心 3D，把示范里几乎不动的 pivot 变成受平衡保护约束的腰部/底盘/高度补偿，再用检查点条件化的离线 RL/优势加权把关键过渡学出来。简称 **RUBICON**（RUBric-conditioned, Object-centric, BalanCe-aware）。

三条随机词的落点：

- **数据标注**：把 32k 条示范自动拆成“阶段 + 物体 3D + 接触 + 检查点进度 + 语言”，这是所有后续模块的燃料。
- **平衡控制**：不直接学步态；把 pivot 与操作策略解耦，用“安全先验 + 平衡 shield + 小范围腰部/底盘/高度补偿”扩展可达空间，默认保持示范中的稳定站姿。
- **强化学习**：不做真机在线 RL；做“检查点条件化的离线 RL/优势加权 + 仿真残差技能”，把 RL 用在关键接触阶段和恢复上。

## 1. 评分表告诉我们的策略事实

- 32 个任务，12 Easy / 12 Medium / 8 Hard；检查点数 2–5 个。
- 首检查点平均 **35.47 分**；11 个 2 检查点任务的首点就是 **50 分**。
- 排行榜按“平均成功率 + 步骤分”综合排序（官网原文）；公开榜截至 2026-10-23 仍为 Coming Soon，“榜首 <30%”只能作为工作假设。
- 推论：
  1. 成功率仍是主战场，不能只刷首点；但首点高、检查点少的任务（T01/T02/T03/T05/T08/T14/T19/T23/T24/T30/T32）是“高地板”，应优先保证稳定拿到。
  2. 对 3–5 检查点任务，阶段推进、防 premature stop、失败重试比“多训一点”更值钱。
  3. 官方 `score_steps` 是公开的稠密监督，不用它等于把最便宜的竞赛信息扔掉。

## 2. 创新点排序（按落地顺序，不是按重要性）

| 顺序 | 创新点 | 价值 | 风险 | 依赖 |
|---|---|---|---|---|
| P0 | Rubric Compiler + Progress Verifier | 高 | 低 | `info.json` |
| P0 | DemoCompiler 自动标注引擎 | 高 | 中 | 数据集 + 开源视觉模型 |
| P0 | 阶段重试 + 干扰感知恢复 | 高 | 低 | 进度头/检测器 |
| P1 | Pivot 解耦的全身控制 + Balance Shield | 高 | 中 | 调试探针 |
| P1 | 双目 3D 物体中心 VLA | 高 | 中 | 标定/立体匹配 |
| P1 | 检查点条件化离线 RL / 优势加权 BC | 中高 | 中 | 自动标注 |
| P2 | 精密技能库（插入/拉链/倾倒） | 高（硬任务） | 中 | 3D/视觉伺服 |
| P2 | 检索增强动作先验 | 中 | 低 | 标注/索引 |
| P2 | 3D 场景重组增广 | 中 | 中 | 分割/深度 |
| P3 | 仿真残差/恢复 RL | 中高 | 高 | 仿真资产 |

## 3. 核心押注 RUBICON

### 3.1 Rubric Compiler + Progress Verifier（P0）

- **动机**：32 个任务、2–5 个检查点，长程任务需要知道“现在在哪个阶段、何时该停/该重试”。评测只给一句语言，不给阶段；纯 BC 容易提前停或错过检查点。官方评分点公开且精确，是最便宜的稠密监督。
- **做法**：离线把每个任务的 `score_steps` 编译成结构化阶段：`{phase_id, instruction, target_object, target_location, success_predicate, max_steps, retry_policy}`。训练时把“任务 + 阶段 + 检查点”拼进 prompt，并加辅助头（阶段分类、进度回归）。测试时用语言 + 首帧做任务匹配，进度头推进阶段；停滞触发重试/恢复。
- **差异**：多数队伍只用评测给的语言；我们把公开评分表变成训练信号和运行时监视器，既提高完整成功率，也保住步骤分。
- **可行性/资源**：离线 LLM 编译 + 小头；无需运行时 LLM API；1 张 GPU、3–5 天。模糊步骤（“摆正”“整理好”）需要 VLM/人工抽查定义谓词。
- **落地步骤**：① 抓取 32 个 `info.json`；② 定义阶段 schema；③ 用示范自动对齐阶段；④ 训练阶段/进度头；⑤ 接入策略循环；⑥ 单任务调试校准阈值。
- **风险**：评分点歧义、过拟合评分表、规则不允许任务特定逻辑。缓解：用学习到的进度头而非硬编码状态机；任务逻辑只做 prompt/阶段，不硬编码坐标；先读规则。

### 3.2 DemoCompiler 自动标注引擎（P0）

- **动机**：数据集有 4 路视频、proprio、action，但**没有语言字段**，也没有阶段、物体框/3D、接触、检查点进度、失败样本。原始 BC 只用了数据的一小部分信息。
- **做法**：统一 32 个 LeRobot v3 数据集；从 `info.json` 生成中英语言与复述；用双目深度 + SAM2/GroundingDINO 做物体掩码与 3D 跟踪；用夹爪开合、EE 速度、物体运动做阶段切分；用 LLM/VLM 对齐到评分点；输出阶段、物体 3D、接触、检查点时间、抓取/放置位姿；再做背景/位置/干扰物/人手合成增广。
- **差异**：别人“喂原始轨迹”，我们“喂结构化轨迹”。同一份数据可同时用于辅助损失、进度头、离线 RL、检索和定向增广。
- **可行性/资源**：169 小时、32k episodes；标注时降采样到 5–10fps，用跟踪传播；4–8 张 GPU、1–2 周；存储数 TB。抓取/放置位姿可直接用示范 EE 位姿，减少物体标注成本。
- **落地步骤**：① 统一数据集与 task ID；② 生成语言；③ 双目深度；④ 物体跟踪；⑤ 阶段/检查点；⑥ 增广；⑦ 导出 WebDataset/parquet。
- **风险**：标注噪声、计算量大、合成数据不真实。缓解：置信度加权、VLM 抽检、只用高置信标签做 RL、增广与真实数据混合。

### 3.3 Pivot 解耦的全身控制 + Balance Shield（P1）

- **动机**：提交接口的下半身只有 `action.pivot[7]`，示范里 base 几乎静止、`pivot_4` 恒为 0.15、height 基本 0.738；多数队伍会直接输出零/常数。这个通道可以用来扩展可达空间、适配桌面高度、在人为干扰后重新对准，也可以用来防止摔倒——但用不好会摔。
- **做法**：**把 pivot 从 VLA 里解耦**。VLA 只出双臂 + 夹爪；单独的 Pivot Controller 输出 base/waist/height：默认安全先验；目标超出可达时小范围转 base/waist；桌面过高/过低时调 height；检测到 lower_body 偏离站姿时进入 Balance Shield，清零 base 速度、回中性 waist、保持 height、暂停手臂，稳定后恢复。若 pivot 的 3 个未知维确实是 waist，则用它们做腰部辅助；否则只用 base/height。
- **差异**：示范是静态的，所以这是 OOD，但也是被忽视的自由度。解耦后不需要重训 VLA 就能获得全身适应，且比让 VLA 直接学 base 动作安全。
- **可行性/资源**：先用不计分单任务调试做小步探针（每维 ±0.02–0.05），确认语义/符号/限位；规则式/MPC 即可；1 周；无额外硬件。
- **落地步骤**：① 探针确认 `pivot[3:6]` 语义；② 安全先验；③ Balance Shield；④ 可达/高度补偿；⑤ 与 VLA 动作合并；⑥ 调试。
- **风险**：base 运动可能被规则禁止/危险；腰部映射未知；摔倒。缓解：默认静态、保守限幅、先探针、急停、人在环。

### 3.4 双目 3D 物体中心 VLA（P1）

- **动机**：头部双目已校正，基线约 58.25mm、`fx≈282.37`，可算真实深度；多数队伍只用 RGB。任务需要精确抓取/放置/插入，评测又考位置、背景、未见物体，3D 比 2D 外观更稳。
- **做法**：亚像素立体匹配（FoundationStereo/RAFT-Stereo）得到深度；用 SAM2/GroundingDINO 得到目标物体掩码并提升到 3D；跟踪物体 3D 位姿；从示范 EE 轨迹提取抓取/放置 affordance；把 3D token/深度图/目标 3D 子目标喂给 VLA；腕部相机做近距离验证。
- **差异**：度量 3D + 物体中心，而不是纯 RGB 端到端；对背景/位置/遮挡更稳，对插入/挂杯/拉链更准。
- **可行性/资源**：数据集自带相机内参/外参；立体匹配开源；1m 处 0.1px 视差约 6mm 深度误差，0.5m 处约 1.5mm（需亚像素）；4–8 张 GPU、2 周。
- **落地步骤**：① 验证校正/极线；② 深度管线；③ 物体跟踪；④ 抓取/放置位姿；⑤ 3D 条件训练；⑥ 在位置/背景/未见物体上评测。
- **风险**：透明/反光物体（杯子、瓶子）深度空洞；评测相机标定漂移；算力。缓解：多视角、置信度门控、单目深度兜底、腕部近景。

### 3.5 阶段重试 + 干扰感知恢复（P0/P1）

- **动机**：BC 没有恢复行为；评测会移动物体、拿走物体、打开/关上已完成的部件；一次抓空/滑落就整任务失败。`info.json` 甚至公开了 `human_1/human_4` 的扰动方向，可直接做定向测试。
- **做法**：进度头停滞/下降 → 开夹爪、沿接近方向退、重新观测、换抓取位姿重试；人手/物体位移检测 → 暂停、等待稳定、重定位、更新目标、继续；用合成人手/物体瞬移训练恢复模式；按任务备注建立扰动测试集。
- **差异**：把“恢复”当一等行为，而不是指望 VLA 从成功示范里学会；直接打人为干扰这一评分轴。
- **可行性/资源**：检测器 + 规则/检索恢复；1 周；无需额外数据。
- **落地步骤**：① 枚举 32 任务扰动备注；② 人手/位移检测；③ 暂停-重定位-恢复脚本；④ 合成增广；⑤ 调试。
- **风险**：误检导致停顿；时间预算。缓解：滞回、超时、只在高置信时暂停。

### 3.6 检查点条件化离线 RL / 优势加权 BC（P1/P2）

- **动机**：示范全是成功轨迹，BC 对所有帧等权；真正难的是抓取、插入、拉链、放置这些关键过渡。评分点提供了天然的分段目标。
- **做法**：用自动标注得到每个检查点达成时间；训练 goal-conditioned value `V(s, g_i)` 或进度分类器；把帧按“距下一个检查点”重标注；用优势加权 BC（`w=exp(β·(V(s',g)-V(s,g)))`）强调推进关键帧；进度头用于阶段推进/恢复；有余力再做 best-of-N 或仿真残差。
- **差异**：不是真机在线 RL，而是“评分点即回报”的离线 RL-lite；不需要失败数据也能用，风险和算力可控。
- **可行性/资源**：离线；2–4 张 GPU、1–2 周；仿真残差另算。
- **落地步骤**：① 检查点标签；② 训练 value/progress；③ 加权 BC；④ 评测；⑤ 可选仿真残差。
- **风险**：全成功数据限制 RL 上限；value 校准差；过拟合。缓解：以监督进度 + 加权 BC 为主，纯 RL 为辅；留出任务/回合验证。

### 3.7 精密技能库（P2）

- **动机**：Hard 任务多为接触密集/变形/小公差：拔插网线、插插头、开锁、拧药瓶、叠毛巾、装耳机、装手机、拉拉链。没有力/触觉，只能靠视觉伺服。
- **做法**：VLA 负责接近，技能负责最后几厘米：腕部/头部双目估计插头-插座、拉链头-齿、瓶盖-瓶身的相对位姿；小步伺服；检测位姿停滞/图像接触；微搜索（wiggle）或重试；完成后验证。
- **差异**：混合式“VLA 接近 + 经典视觉伺服精调”，比纯端到端更容易在硬任务上拿到检查点。
- **可行性/资源**：先做 2–3 个技能（插入、拉链、倾倒）；2 周；任务特定风险。
- **落地步骤**：选任务；实现技能；接入阶段控制器；评测。
- **风险**：任务特定、规则限制、鲁棒性。缓解：技能保持通用（插入/拉链/对位），用学习残差增强，先确认规则。

### 3.8 检索增强动作先验（P2）

- **动机**：32k 示范是现成的非参数记忆；OOD 状态下参数模型可能不如“找相似示范”。
- **做法**：用物体中心特征建索引；测试时检索相似帧/动作块；与 VLA 动作融合或作为低置信度兜底；恢复时检索“从相似状态回到任务”的示范片段。
- **差异**：非参数、数据效率高；与 VLA 互补。
- **可行性/资源**：向量库 + 轻量特征；1 周；注意延迟。
- **落地步骤**：索引；检索；融合；评测。
- **风险**：检索错配、延迟、背景偏移。缓解：物体中心特征、置信度门控、只在关键阶段用。

### 3.9 3D 场景重组增广（P2）

- **动机**：评测考位置/背景/干扰物/未见物体，而示范视觉多样性有限。
- **做法**：分割 + 深度 + 扩散修补/3D 重渲染；替换背景、移动物体、加干扰物、叠人手；保持深度/掩码/时序一致；与真实数据混合训练。
- **差异**：针对评分轴的定向增广，而不是通用颜色抖动。
- **可行性/资源**：2 周；可能有合成痕迹。
- **落地步骤**：管线；增广；训练；评测。
- **风险**：不真实、sim-to-real gap。缓解：小比例混合、一致性损失、真实数据优先。

### 3.10 仿真残差/恢复 RL（P3）

- **动机**：接触密集技能和平衡恢复在真实数据里覆盖不足；仿真可以生成失败和扰动。
- **做法**：Isaac Lab/MuJoCo 搭简化桌面任务；检查点奖励；域随机化；训练残差/恢复；蒸馏回 VLA 或作为技能。
- **差异**：用仿真补真实数据缺口，而不是在真机在线试错。
- **可行性/资源**：资产/对齐成本高；2–4 周；高风险。
- **落地步骤**：先做 1–2 个硬任务；验证 sim-to-real；再扩展。
- **风险**：仿真不真实、资产不匹配、时间不够。缓解：只做残差/恢复，不做全任务从零 RL；作为 P3。

## 4. 不建议/暂缓

- **从零训练大模型**：资源打不过 Unitree，且竞赛瓶颈不在参数量。
- **真机在线 RL**：样本效率、安全、评测时间都不允许。
- **依赖运行时 LLM/VLM API**：延迟、网络、规则风险；所有 rubric 编译离线完成。
- **额外传感器/硬件**：接口只给 4 路 RGB + proprio；不要假设有力/触觉。
- **任务特定硬编码轨迹**：泛化差，且可能违反“单模型/通用”精神；用阶段 prompt + 学习进度头替代。
- **激进使用 pivot**：未探针前默认静态；平衡优先于炫技。

## 5. 8 周执行顺序

| 周 | 目标 | 交付 |
|---|---|---|
| 1 | 规则/接口/基线；rubric compiler；pivot 探针 | 可跑 baseline、32 任务 rubric JSON、pivot 语义报告 |
| 2 | DemoCompiler v1：语言、阶段、检查点 | 结构化标注 v1、数据加载器 |
| 3 | VLA 微调：多视角 + proprio + rubric prompt；joint vs EE | 首个可评测 checkpoint |
| 4 | 进度头、阶段控制器、重试；干扰检测 | 闭环策略 v1 |
| 5 | pivot/balance shield；双目 3D；精密技能 | 全身/3D/硬任务增强 |
| 6 | 离线 RL/优势加权；增广；消融 | 策略 v2 + 消融报告 |
| 7 | 单任务调试 + 计分多任务提交 | 首个榜单成绩 |
| 8 | 迭代/latency/credibility；可选仿真 RL | 最终提交 |

## 6. 必须先解决的问题

1. **Feishu 参赛手册**（当前不可读）：评分公式权重、每任务 trial 数、是否允许外部数据/预训练模型、是否允许任务特定逻辑、base/waist 运动限制、单任务时间限制、N 台机器人。
2. **pivot 语义与安全限位**：`pivot[3:6]` 到底是什么；base 运动是否允许；height 范围。
3. **评测语言分布**：是否与数据集/任务描述一致；不一致时任务匹配要更鲁棒。
4. **调试名额**：不计分单任务调试每任务几次；优先测 T01/T04/T10/T16/T24/T30。
5. **仿真资产**：是否有 G1 + 桌面物体；没有就砍掉 P3。
6. **截止日期**：<4 周只做 P0 + pivot shield；4–6 周加双目/干扰/技能；>6 周再加 RL/增广。

## 7. 一句话押注

**把官方评分点编译成可验证的阶段进度，用已校正双目做物体中心 3D，并把 pivot 从示范里的常数变成受平衡 shield 约束的腰部/底盘/高度补偿——即 RUBICON：Rubric 条件化、物体中心、平衡感知的全身 VLA 竞赛层；先做 Rubric + 重试 + 平衡 shield，再加立体 3D 与离线 RL。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## A. 结论

本轮最值得做的不是“再训一个更大的 VLA”，而是给现有开源 VLA 加一层**竞赛层**：官方评分点 → 可验证阶段进度；已校正双目 → 物体中心 3D；示范里几乎不动的 `pivot` → 受平衡保护约束的腰部/底盘/高度补偿；检查点 → 离线 RL/优势加权与恢复信号。核心方案代号 **RUBICON**。下面所有事实、评分表、架构、实验与风险均以 2026-10-23 可访问的公开页面/文件为准。

## B. 已核实事实（检索日期 2026-10-23）

| # | 事实 | 证据/来源 |
|---|---|---|
| 1 | 32 个真实桌面任务、32000 条示范、169 小时；4 路相机（头部双目 + 左右腕），480×640×3，30fps | 挑战赛页 `challenges.html`；HF 数据集 README |
| 2 | 头部双目为 rectified；左右腕为单目彩色；HangCup 标定：`fx_left≈282.369`、`fx_right≈281.874`，基线 `T≈[-58.25,-0.17,0.58] mm`；深度近似 `Z(m)≈16.44/disparity(px)` | `G1_Dex1_HangCup/meta/info.json` 的 `camera_params` |
| 3 | 数据为 LeRobot v3.0；`lower_body[15]` = 双腿 6+6 + 腰 3；`action.pivot[7]`；**特征里没有 language 字段**，只有 `task_index`；每个任务一个 HF 数据集 | `meta/info.json`；数据集 README |
| 4 | HangCup 的 `action.pivot` 统计：`vx/vy≈0`，`angle_z∈[-0.8,0.8]`（均值≈0），`pivot_3=0`，`pivot_4=0.15`，`pivot_5=0`，`height∈[0.654,0.740]`（均值 0.738）；腰部 yaw/roll 很小，pitch 约 0.096–0.204 | `meta/stats.json` |
| 5 | 提交接口：obs 含 4 图、双臂 7+7、EE pose 6+6、夹爪 1+1、`lower_body[15]`、language 字符串；action 为 `joint` 或 `ee` 二选一，双臂/夹爪 + `action.pivot[7]`；metadata 含 `control_space/obs_delta_indices/image_resize/action_chunk_size/token`；N 台机器人 → N 个连续端口；评测记录延迟并检查动作规律性 | `unibot_submission` README、`example_policy.py` |
| 6 | 评测两种模式：① 计分多任务覆盖全部 32 任务；② 不计分单任务调试只测 1 个任务。排行榜按“平均成功率 + 步骤分”综合排序；截至 2026-10-23 公开榜仍为 Coming Soon | `profile.html`、`leaderboard.html` |
| 7 | 32 任务评分表已抓全；首检查点平均 35.47 分；检查点数 11×2、14×3、5×4、2×5；难度 12 Easy/12 Medium/8 Hard | `tasks_v2/<slug>/info.json?v=2026-07` |
| 8 | 基线：UnifoLM-WLA-1.0 为 6B、约 2500h 真机数据、64 任务；UnifoLM-VLA-0 开源（Qwen2.5-VL 系，训练/推理/权重，12 类任务）；UnifoLM-ER-1-4B 基于 Qwen3-VL-4B | 项目页、GitHub README |
| 9 | 参赛手册为飞书文档，curl/webfetch 均拿不到正文；评分权重、trial 数、外部数据/预训练模型、任务特定逻辑、base/waist 运动、时间限制均**未核实** | 飞书链接（见 K） |
| 10 | “榜首成功率 <30%”为用户提供的工作假设；公开榜 Coming Soon，无法验证 | 用户输入；`leaderboard.html` |

**标定注意**：`camera_params.head_stereo.rectified=true`，但左右 `cx` 相差约 18.4px（311.5 vs 330.0），不能直接假设已完全校正；使用前用 `stereoRectify`/极线误差/已知物体尺寸验证，必要时重投影。深度公式按 `fx≈282.12`、`B≈58.26mm` 估算。

**明确未核实**：`pivot[3:6]` 的真实语义；评测用的语言字符串分布；每任务 trial 数；计分公式中成功率/步骤分的权重；是否允许外部数据或任务特定逻辑；是否允许 base/waist 运动；单任务时间限制；N 的具体值；HangCup 以外任务的相机标定是否一致；评测端 `cam_left_high/cam_right_high` 是否与数据集 `head_stereo_left/right` 完全同一对双目（名称不同，需调试确认）；评测端相机分辨率/校正是否与数据集一致。

## C. 32 任务评分表

| ID | 任务（中/英） | 难度 | 评分点（分） | 首点分 | 检查点数 |
|---|---|---|---|---|---|
| T01 | 挂杯子 / HangCup | Easy | 50+50 | 50 | 2 |
| T02 | 水果收集 / FruitCollection | Easy | 50+50 | 50 | 2 |
| T03 | 装娃娃 / PackDoll | Easy | 50+50 | 50 | 2 |
| T04 | 水果分类 / FruitSorting | Easy | 30+30+40 | 30 | 3 |
| T05 | 拔网线 / DisconnectEthernet | Hard | 50+50 | 50 | 2 |
| T06 | 颜色排列 / ColorArrangement | Easy | 30+30+40 | 30 | 3 |
| T07 | 摆放相框 / PlacePhotoFrame | Medium | 30+30+40 | 30 | 3 |
| T08 | 整理书架 / OrganizeBookshelf | Easy | 50+50 | 50 | 2 |
| T09 | 工具箱收纳 / ToolboxStorage | Hard | 25×4 | 25 | 4 |
| T10 | 插插头 / PlugCharger | Hard | 30+30+40 | 30 | 3 |
| T11 | 挑出电池 / PickOutBatteries | Medium | 30+30+40 | 30 | 3 |
| T12 | 开锁 / Unlock | Hard | 30+30+40 | 30 | 3 |
| T13 | 整理试管 / ArrangeTestTubes | Easy | 30+30+40 | 30 | 3 |
| T14 | 倒出药品 / PourOutMedicine | Hard | 50+50 | 50 | 2 |
| T15 | 整理工具 / OrganizeTools | Medium | 25×4 | 25 | 4 |
| T16 | 叠毛巾 / FoldTowel | Hard | 20×5 | 20 | 5 |
| T17 | 整理文具 / OrganizeStationery | Easy | 20×5 | 20 | 5 |
| T18 | 收拾书包 / PackBag | Medium | 25×4 | 25 | 4 |
| T19 | 拉上拉链 / ZipUp | Medium | 50+50 | 50 | 2 |
| T20 | 纸杯堆叠 / PaperCupStacking | Easy | 30+30+40 | 30 | 3 |
| T21 | 餐盘排列 / ArrangePlates | Easy | 30+30+40 | 30 | 3 |
| T22 | 字母拼写 / SpellRobot | Medium | 25×4 | 25 | 4 |
| T23 | 球拍收纳 / StorePaddle | Medium | 50+50 | 50 | 2 |
| T24 | 传送带分拣 / ConveyorSorting | Medium | 50+50 | 50 | 2 |
| T25 | 整理纸杯 / StoreCups | Easy | 30+30+40 | 30 | 3 |
| T26 | 插网线 / PlugInEthernet | Medium | 30+30+40 | 30 | 3 |
| T27 | 碗具堆叠 / StackBowls | Easy | 30+30+40 | 30 | 3 |
| T28 | 装耳机 / StoreEarphones | Hard | 25×4 | 25 | 4 |
| T29 | 装手机 / PackPhone | Hard | 30+30+40 | 30 | 3 |
| T30 | 移除固定便签 / RemovePinnedNote | Medium | 50+50 | 50 | 2 |
| T31 | 整理文具袋 / OrganizePencilCase | Medium | 30+30+40 | 30 | 3 |
| T32 | 针管转移液体 / SyringeWaterTransfer | Medium | 50+50 | 50 | 2 |

### C.1 评分结构

- **难度**：Easy 12（T01/02/03/04/06/08/13/17/20/21/25/27）；Medium 12（T07/11/15/18/19/22/23/24/26/30/31/32）；Hard 8（T05/09/10/12/14/16/28/29）。
- **检查点数**：2 个 11 任务；3 个 14 任务；4 个 5 任务；5 个 2 任务。
- **首检查点**：2 检查点任务首点 50；3 检查点 30；4 检查点 25；5 检查点 20。总和 1135，平均 **35.47**。
- **高地板任务**（首点 50）：T01/T02/T03/T05/T08/T14/T19/T23/T24/T30/T32。优先保证“抓住/拿起/摆正/放进”这一步稳定。
- **硬骨头**：T05 拔网线、T09 工具箱锁、T10 插插头、T12 开锁、T14 拧药瓶、T16 叠毛巾、T28 装耳机、T29 装手机。接触密集/变形/小公差，适合精密技能 + 离线 RL。
- **注意**：步骤分是“平均成功率 + 步骤分”综合排序的一部分，权重未知；不能为了首点牺牲完整成功率。
- **期望分示例**：2 检查点任务若 `P(首点)=0.9`、`P(完整|首点)=0.3`，期望 ≈ `0.9×50 + 0.27×50 = 58.5`；3 检查点任务若 `0.8/0.5/0.3`，期望 ≈ `0.8×30 + 0.4×30 + 0.12×40 = 40.8`。这说明：高地板任务先稳首点，硬任务冲“第二/第三点”的边际收益更大。

### C.2 泛化备注（`info.json` 公开部分）

> 这些备注只覆盖 `unseen_object_3`、`human_1`、`human_4`，不代表全部评测变体；但足以做定向测试与增广。原文照录/略缩。

| ID | unseen_object_3 | human_1 | human_4 |
|---|---|---|---|
| T01 | 缺少红色杯子和塑料架子 | 杯子向后 | 杯子向右 |
| T02 | 缺少不同果篮 | 水果向前 | 水果向右 |
| T03 | 缺少绿色和紫色娃娃 | 娃娃向前 | 娃娃向右 |
| T04 | 缺少其他款式的盘子 | 橘色盘子向左移动 | 把梨往右移动 |
| T05 | 缺少其他颜色的短网线 | 把网线另一头也插上 | 移动道具手握网口 |
| T06 | 没有其他积木，只有塑料积木 | 绿色积木向右移动 | 红色积木向前移动 |
| T07 | 只有一种相框 | 相框向上移动 | 相框向上移动 |
| T08 | — | 抓到书后挪动架子 | 书向右 |
| T09 | — | 胶带向后移动 | 胶带向右移动 |
| T10 | 缺少其他颜色的插排 | 抓插头前进行移动 | 将插头拔起 |
| T11 | 缺少黑色电池 | 抓取电池之前动底座 | 抓电池之后动绿色盒子 |
| T12 | 缺少一把绿色锁 | 锁向左移动 | 中途把锁拿走 |
| T13 | 不同类型的试管 | 试管向右移动 | 试管向左移动 |
| T14 | 缺少不同颜色的药品收纳盒 | 拧开盖子之后拧动回来 | 把瓶子向左移动 |
| T15 | — | 钳子向左移动 | 螺丝刀向右移动 |
| T16 | — | 将叠完的毛巾翻开 | 将叠完的毛巾翻开 |
| T17 | 缺少黑色的文件盒 | 荧光笔向后 | 笔盒合上之后手动打开 |
| T18 | 缺少其他颜色的文具盒 | 把文具盒向上移动 | 把书包向左移动 |
| T19 | — | 把包向左边移动 | 拉上拉链之后拉开 |
| T20 | 缺少不同类型纸杯 | 把左边的纸杯向上移动 | 把右上角的纸杯向右移动 |
| T21 | 缺少不同类型的盘子 | 把盘子向前移动 | 把架子向左边移动 |
| T22 | 缺少不同颜色的字母 | 字母上移动 | 字母向左边移动 |
| T23 | 缺少不同的球拍套装 | 球拍向前移动 | 球拍向左移动 |
| T24 | 缺少不同的零食 | 可乐快到了然后放回传送带起点 | 薯片快到了然后放回传送带起点 |
| T25 | 缺少不同颜色的纸杯 | 把纸杯向左移动 | 放了第一个马上放第二个挪一下底座 |
| T26 | 不同的网线跟端口 | 把网线移开 | 把插口移开 |
| T27 | 除了塑料类型 | 把粉色碗向下移动 | 叠了第二个之后拿下第二个 |
| T28 | 缺少不同的收纳盒以及耳机托盘 | 把黄色盒子的耳机向前移动 | 把红盒子的耳机向右移动 |
| T29 | — | 手机向上移动 | 外壳盖移开 |
| T30 | — | 把黄色钉子移到中间 | 把绿色钉子向下移动 |
| T31 | — | — | — |
| T32 | — | — | — |

**用法**：① 按备注在仿真/真机调试中复现扰动；② 生成定向增广（物体位移、拿走、开合、人手入镜）；③ 训练“暂停-重定位-恢复”策略；④ 评估时按扰动类型分桶，而不是只看总分。

## D. 瓶颈诊断

1. **数据是“成功且静态”的**：32k episodes / 169h，每任务约 1000 条；HangCup 1043 条、194,564 帧、约 6.2s/episode。示范 base 几乎静止、`pivot_4` 恒定；没有失败、滑落、抓空、人为干扰后的恢复样本。纯 BC 会遇到分布漂移。
2. **没有语言标签**：数据集特征没有 language，只有 `task_index`；提交接口却给语言。必须从 `info.json` 生成指令/复述，否则训练/评测语言分布不一致。
3. **没有阶段/物体/检查点标签**：原始轨迹只有状态-动作；评分点、物体 3D、接触、检查点时间都没有。BC 对所有帧等权，长程信用分配差。
4. **长程 + 多检查点**：2–5 个检查点；T16/T17 有 5 个；T09/T15/T18/T22/T28 有 4 个。提前停、漏检查点、失败后不重试都会丢分。
5. **接触密集/变形/小公差**：拔插网线、插头、开锁、拧瓶盖、拉链、叠毛巾、装耳机、针管。没有力/触觉，只有 4 路 RGB + proprio；RGB 端到端很难稳定过最后几毫米。
6. **人为干扰是评分轴**：`human_1/human_4` 会移动物体、拿走物体、打开已完成部件；BC 没有“暂停-重定位-恢复”的行为。
7. **平衡/全身自由度被浪费**：`action.pivot[7]` 含 base 速度、height、3 个未知维；示范几乎不动。多数队伍会输出零/常数。用得好可以扩展可达/适配高度/抗扰动；用不好会摔。
8. **接口/部署约束**：N 台机器人 → N 个连续端口；共享后端要并发、状态隔离；记录延迟并检查动作规律性；action chunk 要覆盖推理时间。
9. **评分结构**：成功率 + 步骤分；首点平均 35.47，2 检查点任务首点 50。高地板任务要稳，硬任务要冲完整成功；权重未知，不能偏科。

## E. RUBICON 架构

### E.1 离线

```text
32 × LeRobot v3 数据集
        │
        ├─ 语言生成（info.json 名称/描述/评分点 → 指令 + 复述）
        ├─ DemoCompiler：双目深度 + SAM2/GroundingDINO + 阶段切分 + 检查点标签
        ├─ 增广：背景/位置/干扰物/人手/物体瞬移
        ▼
结构化数据集（阶段、物体 3D、接触、检查点、抓取/放置位姿）
        │
        ├─ VLA 微调（多视角 + proprio + rubric prompt + 3D token）
        ├─ 辅助头：阶段分类 / 进度回归 / 深度/关键点
        ├─ 离线 RL：goal-conditioned value + 优势加权 BC
        └─ 检索索引：物体中心帧/动作块
        ▼
策略包：VLA + 进度头 + 物体跟踪 + rubric DB + pivot controller + skills
```

### E.2 在线

```text
obs（4 图 + proprio + language）
        │
        ├─ 感知：双目深度、物体 3D、桌面平面、人手/位移检测
        ├─ 任务匹配：language + 首帧 → 32 任务之一
        ├─ Rubric/阶段：当前 phase 的 instruction/target/predicate
        ├─ VLA：多视角 + proprio + phase prompt → 双臂/夹爪动作
        ├─ 精密技能：插入/拉链/倾倒的最后几厘米
        ├─ Pivot Controller：安全先验 + 可达/高度补偿
        ├─ Balance Shield：风险时清零 base、回中性 waist、保持 height、暂停手臂
        ├─ 进度头：推进 phase / 触发重试 / 触发恢复
        ▼
action（joint 或 ee + grippers + pivot + meta.token）
```

### E.3 伪代码

```python
class RubiconPolicy:
    def __init__(self):
        self.token = os.environ["UNIBOT_SUBMISSION_TOKEN"]
        self.control_space = "joint"          # 或 "ee"，由实验决定
        self.chunk = 8
        self.vla = load_vla(...)
        self.progress = load_progress_head(...)
        self.perception = Perception(...)     # stereo, SAM2, human detector
        self.rubrics = load_rubrics("rubrics.json")
        self.pivot = PivotController(...)
        self.skills = SkillLibrary(...)

    def reset(self):
        self.phase = 0
        self.memory = SceneMemory()
        self.retry = 0
        self.mode = "NORMAL"                  # NORMAL / WAIT / RECOVER

    def get_action(self, obs):
        task = match_task(obs["observation.language"], obs)
        rubric = self.rubrics[task]
        scene = self.perception.update(obs)
        self.memory.update(scene)

        if scene.human_in_workspace or self.memory.object_moved():
            self.mode = "WAIT"
            return self.hold_action(obs, scene)

        if self.pivot.balance_risk(obs):
            self.mode = "RECOVER"
            return self.hold_action(obs, scene)

        self.mode = "NORMAL"
        phase = rubric.phases[self.phase]
        prompt = compose_prompt(task, phase)
        action = self.vla.act(obs, scene.tokens, prompt)
        action = self.skills[phase.skill].refine(action, scene, phase)
        action["action.pivot"] = self.pivot.command(scene, phase, obs)
        action = smooth_and_clip(action)

        p = self.progress.done(obs, phase)
        if p > 0.8:
            self.phase = min(self.phase + 1, len(rubric.phases) - 1)
            self.retry = 0
        elif self.progress.stalled(obs, phase):
            self.retry += 1
            self.recover_or_retry(scene, phase)

        action["meta.token"] = self.token
        return action
```

### E.4 模块规格

| 模块 | 输入 | 输出 | 频率/算力 | 备注 |
|---|---|---|---|---|
| 双目深度 | head L/R | 度量深度 | 30fps 可选 10fps | 亚像素；透明/反光有空洞 |
| 物体跟踪 | 4 图 + 深度 | 物体 mask/3D/位姿 | 5–10fps | 目标物体优先，非全场景 |
| 任务匹配 | language + 首帧 | task_id | 一次/回合 | embedding + 关键词兜底 |
| Rubric/阶段 | task_id + 进度 | phase instruction | 每步 | 离线 JSON，无 API |
| VLA | 多视角 + proprio + prompt | 双臂/夹爪 chunk | 5–15Hz | 8B 级，LoRA |
| 进度头 | VLA 特征 + proprio | 阶段完成概率 | 30Hz | 小 MLP/Transformer |
| Pivot Controller | 物体 3D + 相位 + 平衡状态 | pivot[7] | 30Hz | 规则/MPC，可解耦 |
| Balance Shield | lower_body + pivot | 安全 pivot/暂停 | 30Hz | 状态机 |
| 精密技能 | 腕部/头部近景 | 残差动作 | 30Hz | 插入/拉链/倾倒 |
| 服务层 | N 端口 | 动作/延迟 | 并发 | 共享后端 + 状态隔离 |

### E.5 控制空间：joint vs EE

- `metadata.control_space` 在握手时固定，**不能按任务/阶段运行时切换**；必须二选一。
- **joint**：输出 7+7 关节目标 + 夹爪 + pivot。与示范同空间，最容易复现；限位/平滑好做；缺点是可能过拟合关节配置，跨物体泛化弱。
- **ee**：输出 6+6 base-frame EE 位姿 + 夹爪 + pivot。更适合物体中心 3D 子目标/视觉伺服；缺点是要依赖评测端 IK，且 waist/base 动了以后 base-frame 目标必须补偿（内部用 torso-frame 再转 base-frame）。
- **建议**：离线同时训练两个头，单任务调试各测一次；若评测端 IK 延迟/精度未知，默认 joint；若 3D 精密技能是核心，选 ee。无论选哪个，pivot 都由独立控制器输出，不交给 VLA 学。

## F. DemoCompiler 数据标注引擎

### F.1 管线

1. **统一数据集**：32 个 HF 数据集，统一 schema；建立 `global_task_id`；读取 `meta/info.json`、`meta/stats.json`、parquet、视频。
2. **语言生成**：从 `info.json` 的 `zh_name/en_name/zh_desc/en_desc/scoring_points` 生成指令与 5–10 条复述；把评分点作为阶段描述；训练时随机拼接。
3. **双目深度**：用 `camera_params` 做校正/校验；亚像素立体匹配；输出深度图与置信度；对透明/反光做空洞填充/多视角融合。
4. **物体跟踪**：GroundingDINO 开词检测 + SAM2 分割；用深度提升到 3D；用光流/卡尔曼跟踪；抓取后物体位姿 = 夹爪位姿 + 偏移。
5. **阶段切分**：夹爪开合事件 + EE 速度/加速度 + 物体运动 + 变化点检测（ruptures）；得到 reach/grasp/lift/transport/place/open/close/insert/zip/pour 等阶段。
6. **Rubric 对齐**：用 LLM 把阶段序列对齐到 `score_steps`；用 VLM 抽检关键帧；得到每个检查点的完成时间与谓词。
7. **抓取/放置位姿**：抓取时刻的 EE 位姿（相对物体）作为正样本；放置/释放时刻的 EE 位姿（相对目标区域）作为正样本；训练 affordance head。
8. **增广**：背景替换、物体位移、干扰物、人手合成、光照/颜色/相机抖动、物体瞬移；保持深度/掩码/时序一致。
9. **导出**：WebDataset/parquet + 标签 JSON；训练/验证按 episode 切分，避免帧泄漏。

### F.2 标签 schema

```text
episode_id, task_id, t, images[4], state, action, language,
phase_id, phase_name, checkpoint_id, progress,
objects: [{id, name, mask, xyz, rpy, bbox, visibility, contact}],
grasp: {left/right, object_id, pose},
target: {object_id, region, pose},
disturbance: {type, human_bbox, object_id, t}
```

### F.3 阶段切分启发式

- 夹爪 `5.5→0` 为闭合，`0→5.5` 为打开；闭合且物体随夹爪运动 = grasp；闭合且物体不动 = 抓空/滑落候选。
- EE 线速度高 + 夹爪打开 = reach；EE 低速 + 夹爪闭合 = lift/transport；EE 低速 + 夹爪打开 = place/release。
- 物体 mask 与夹爪 mask 重叠 + 物体 3D 位移 = contact；重叠消失 + 物体仍在 = slip。
- 变化点检测在 `left_arm/right_arm/EE pose/gripper` 上做，再用视觉特征校验；阶段数应与 rubric 检查点数一致或可合并。
- 对 4/5 检查点任务，允许“一个 rubric 步骤 = 多个动作阶段”，对齐时用动态规划/LLM。

### F.4 语言生成

- 训练集没有 language；必须生成。模板：
  - `"Put all the fruits into the fruit basket."`
  - `"Task: fruit collection. Step 1/2: grab fruit 1 and put it into the basket."`
  - `"当前子任务：抓住水果1放入果篮。"`
- 每条轨迹 5–10 条复述；随机拼接任务描述 + 当前阶段 + 评分点；避免模型只记住一种句式。
- 评测语言可能更短/更泛；用任务匹配（embedding + 关键词 + 首帧物体检测）兜底。

### F.5 增广

- **背景**：分割桌面/物体，扩散修补或换背景；保持阴影/深度一致。
- **位置**：物体在桌面平面内平移/旋转；用深度重投影；避免越界/碰撞。
- **干扰物**：随机加非目标物体；确保不遮挡目标抓取点。
- **人手**：合成手/手臂入镜、移动/拿走物体；训练干扰检测与恢复。
- **瞬移**：在关键帧把物体移到新位置；模拟 human_1/human_4。
- **一致性**：深度/分割/时序一致性损失；合成比例 ≤30%，真实数据优先。

### F.6 算力/规模

- 169h、32k episodes；标注降采样到 5–10fps；物体跟踪只跑头部双目 + 关键帧腕部。
- 32k × ~200 帧 × 2 头 = ~12.8M 帧；SAM2 批处理 + 跟踪传播，4–8 张 A100/H100，1–2 周。
- 存储：原始 AV1 数 TB；标签/索引 GB 级；不要重复编码视频。

## G. 平衡/全身控制

### G.1 接口事实

- 提交 action 只暴露 `action.pivot[7]` 作为下半身/ pivot 目标；没有 `lower_body` 或 `waist_action_joint` 动作键。
- `pivot` 命名：`[vx, vy, angle_z, pivot_3, pivot_4, pivot_5, height]`；`pivot_3..5` 语义未公开。
- 观测 `lower_body[15]` = 双腿 12 + 腰 3（yaw, roll, pitch），可用于平衡监视。
- 示范统计：base 几乎静止；`pivot_4=0.15` 恒定；height 均值 0.738；腰部 pitch 约 0.16–0.20。说明 pivot 的大部分维度在示范中未被使用。
- 注意：数据集里 `action.waist_action_joint` 与 `action.lower_body[12:15]` 一致，是另一套通道；`action.pivot` 是独立通道，不能因为 `pivot_4=0.15` 就把它直接当 waist pitch（实际 waist pitch 约 0.18）。这正是必须做探针的原因。

### G.2 Pivot 统计（HangCup）

| 维度 | 范围 | 均值 | 解读 |
|---|---|---|---|
| vx | ≈0 | ≈0 | 示范不走 |
| vy | ≈0 | ≈0 | 示范不横移 |
| angle_z | -0.8 – 0.8 | ≈0 | 可能可转，但示范不用 |
| pivot_3 | 0 | 0 | 未知 |
| pivot_4 | 0.15 | 0.15 | 恒定；可能是腰部/俯仰偏置 |
| pivot_5 | 0 | 0 | 未知 |
| height | 0.654 – 0.740 | 0.738 | 示范基本固定 |

### G.3 探针协议（必须先做）

1. 只用**不计分单任务调试**；机器人站稳、桌面清空、急停可用、无人在侧。
2. 默认输出安全先验：`pivot=[0,0,0,0,0.15,0,0.738]`。
3. 一维一维试：`vx=+0.02`、`vy=+0.02`、`angle_z=+0.05`、`pivot_3=±0.05`、`pivot_4=0.15±0.05`、`pivot_5=±0.05`、`height=0.738±0.01`；每步保持 1–2s，记录 base/waist/height 响应。
4. 观察：机器人是否移动/转腰/升降/前倾；是否触发保护；是否摔倒趋势。
5. 重复 2–3 次确认符号/限位；再在有空物体的情况下试。
6. 如果 `pivot_3..5` 不是 waist，就只使用 base/height；不要硬猜。

### G.4 安全先验 + Balance Shield

- **安全先验**：`[0,0,0,0,0.15,0,0.738]`；所有 pivot 输出先过限幅（如 `|vx|,|vy|≤0.05`、`|angle_z|≤0.1`、height ±0.01、未知维 ±0.05，具体以探针为准）。
- **风险判据**：lower_body 关节偏离站姿均值超过阈值；腰部 tilt/roll 超阈值；连续多帧 base 速度指令与姿态不一致；EE 位姿相对 base 突变。
- **Shield 状态机**：`NORMAL → CAUTION（限幅/减速）→ RECOVER（base 清零、waist 中性、height 标称、手臂保持、等待稳定）→ NORMAL`。
- **恢复后**：重新观测物体，更新目标；不要直接继续原动作块。

### G.5 可达/高度补偿

- **可达**：目标 3D 在双臂工作空间边缘时，小范围 `angle_z` 转向 + `vx/vy` 靠近；一次只动一点，动完重新感知。
- **高度**：用双目估计桌面/目标高度；height 调整到舒适区间；不要大幅升降。
- **腰部**：若 `pivot_3..5` 确认为 waist，优先用 waist yaw/pitch 做近场微调；base 只做粗定位。
- **桌面边缘/传送带**：T24 传送带可能需要沿带移动；先用调试确认 base 运动允许且安全。

### G.6 Torso-frame EE

- 提交只给 base-frame EE 位姿；如果 waist/base 动了，base-frame 目标要补偿。
- 内部用 torso-frame 目标（数据集有 `*_ee_pose_gripper_torso` 和 waist 角），再转 base-frame 输出；避免“腰动了但手没跟上”。
- 需要 G1 腰部正运动学；可从数据集/URDF 获取。

### G.7 安全

- 默认静态 pivot；只在探针通过后启用。
- 人在工作区时零 base 速度；等待人离开。
- 任何异常（NaN、超限、通信延迟）→ 安全先验 + 保持。
- 不要在评测中做大幅度 base 运动；优先 waist/height 小补偿。

## H. 强化学习

### H.1 形式化

- 检查点 `g_i`（i=1..K）；`p_t = max{i: checkpoint i achieved by t}`。
- 训练 `V(s_t, g_i) ≈ P(checkpoint i 在 H 步内达成)` 或“距检查点还差多少步”。
- 对每条示范，t 在 `g_i` 之前为正样本，之后为负样本；可为不同 `g_i` 重复标注（goal relabeling）。
- 进度头输出 `p̂_t`；阶段推进/重试/恢复都用它。

### H.2 优势加权 BC

```text
w_t = clip(exp(β * (V(s_{t+1}, g_i) - V(s_t, g_i))), 0.1, 10)
L = E[ w_t * ||π(s_t) - a_t||^2 ] + λ1 * L_phase + λ2 * L_progress + λ3 * L_smooth
```

- `β` 从小到大调；权重裁剪防止爆炸。
- 全成功示范下，优势多为正；重点是让“关键过渡帧”权重更高。
- 不做纯 CQL/IQL 也能获益；如果做，先用小网络验证。

### H.3 测试时

- **阶段推进**：`V(s_t,g_i)>τ` 连续 N 帧 → 进入下一阶段；滞回避免抖动。
- **重试**：`V` 停滞/下降 K 步 → 重试当前阶段；抓空则换抓取位姿。
- **Best-of-N（可选）**：采样 K 个动作块，用 action-conditioned Q/一步动力学 + V + 平滑度选优；没有可靠 Q 就不要做，避免延迟。
- **集成不确定性**：多视角/多 seed 的 action chunk 方差大时，减速/重观测；比盲目 best-of-N 稳。

### H.4 仿真残差（P3）

- Isaac Lab/MuJoCo 搭 1–2 个硬任务（插入/拉链）；检查点奖励 + 域随机化；训练残差/恢复；蒸馏回 VLA。
- 只做残差/恢复，不做全任务从零 RL；资产不匹配就砍掉。

### H.5 不要做

- 真机在线 RL；评测时间/安全都不允许。
- 从零训练大模型；打不过 Unitree 的 2500h/6B 基线。
- 用 RL 替代 BC；示范仍是主监督，RL 只做加权/残差/恢复。

## I. 实验设计

### I.1 基线

| 编号 | 基线 | 目的 |
|---|---|---|
| B0 | 零样本开源 VLA（UnifoLM-VLA-0 / π0 / GR00T） | 下限 |
| B1 | B0 + 32k 示范全量微调（RGB + proprio，pivot 零） | 主基线 |
| B2 | B1 + 多视角 + 语言复述 | 语言/视角增益 |
| B3 | B2 + rubric prompt + 阶段/进度头 | 核心增益 |
| B4 | B3 + 双目 3D/物体中心 | 3D 增益 |
| B5 | B4 + pivot controller/balance shield | 全身/平衡增益 |
| B6 | B5 + 干扰检测/恢复 | 人为干扰增益 |
| B7 | B6 + 离线 RL/优势加权 | RL 增益 |

### I.2 消融

- 双目 vs 单目；有/无深度 token；有/无物体跟踪。
- rubric prompt vs 仅语言；阶段头 vs 无；进度阈值。
- pivot 静态 vs 主动；shield 开/关；height/waist 分别消融。
- 干扰检测开/关；重试开/关；恢复策略。
- 优势加权 vs 普通 BC；β；是否加仿真残差。
- 增广开/关；增广类型逐项。

### I.3 指标

- 全任务成功率；按难度/泛化轴分桶（位置、背景、未见物体、干扰物、人为干扰）。
- 步骤分；首检查点达成率；检查点推进准确率；平均完成时间。
- 抓取成功率、滑落率、重试成功率、恢复成功率、摔倒率。
- 延迟 p50/p95；动作平滑度；NaN/超限率；token/握手成功率。
- 离线：阶段分类准确率、进度校准（ECE）、物体 3D 误差、抓取/放置位姿误差。

### I.4 调试任务优先级

- T01（Easy，2 检查点，高地板）——验证基本闭环。
- T04（Easy，3 检查点）——验证多阶段。
- T10（Hard，插入）——验证精密技能。
- T16（Hard，5 检查点，变形）——验证长程/重试。
- T24（Medium，传送带）——验证动态/位置。
- T30（Medium，细钉）——验证小物体/干扰。
- 若每任务只有 1 次调试，优先这 6 个；其余用离线/仿真。

### I.5 算力/时间

- 数据引擎：4–8×A100/H100，1–2 周；存储数 TB。
- VLA 微调：8×A100/H100（LoRA/部分解冻），1–2 周；全量微调 2–4 周。
- 双目/物体跟踪：1–2 张 GPU 常驻；训练 2–3 天。
- 离线 RL/进度头：2–4 张 GPU，1–2 周。
- 仿真残差：2–4 周（可选）。
- 总：6–8 周；<4 周只做 P0 + pivot shield。

### I.6 时间不够时的决策树

- **<4 周**：B1/B2 + rubric prompt + 进度头 + 重试 + pivot shield。砍掉双目/RL/增广。
- **4–6 周**：加双目 3D/物体中心 + 干扰检测/恢复 + 1–2 个精密技能。
- **>6 周**：加离线 RL/优势加权 + 3D 增广 + 仿真残差。
- **任何情况下**：先读规则、先探针 pivot、先跑通 baseline；不要先训大模型。

## J. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 规则禁止任务特定逻辑/外部数据 | 中 | 高 | 先读手册；用学习进度头/阶段 prompt；只用挑战数据 + 开源权重；保留纯端到端回退 |
| `pivot[3:6]` 语义不明/不安全 | 高 | 高 | 先探针；默认静态；保守限幅；shield；只启用确认维度 |
| base 运动被禁止/导致摔倒 | 中 | 高 | 默认零 base；优先 waist/height；急停；人在环 |
| 无真机/调试名额少 | 中 | 高 | 离线 + 仿真；优先代表任务；用单任务调试做探针 |
| 双目标定/透明反光 | 中 | 中 | 校验极线；亚像素；多视角；单目兜底；腕部近景 |
| 标注噪声 | 高 | 中 | 置信度加权；VLM 抽检；只用高置信标签做 RL |
| 延迟/算力 | 中 | 高 | 轻量头；action chunk；共享后端；异步；p95 监控 |
| 检测误报导致停顿 | 中 | 中 | 滞回；超时；高置信才暂停 |
| 仿真到现实差距 | 高 | 中 | 真实数据微调；域随机化；只做残差 |
| 过拟合评分表/任务 | 中 | 中 | 留出任务/回合；学习头；不硬编码坐标 |
| 评测方差 | 高 | 中 | 多次 trial；稳健动作；重试；置信区间 |
| 动作规律性/可信度被标记 | 低 | 高 | 平滑/限幅；延迟稳定；避免常数动作；token 正确 |
| 语言分布不一致 | 中 | 中 | 复述训练；任务匹配；首帧视觉兜底 |

## K. 来源

**赛事/接口**

- https://unibot.unitree.com/index.html
- https://unibot.unitree.com/challenges.html
- https://unibot.unitree.com/leaderboard.html
- https://unibot.unitree.com/profile.html
- https://github.com/unitreerobotics/unibot_submission
- https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md
- https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/example/example_policy.py
- 任务 JSON 模式：`https://unibot.unitree.com/tasks_v2/<slug>/info.json?v=2026-07`（32 个 slug 见 C 表）

**数据/标定**

- https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup/raw/main/meta/info.json
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup/raw/main/meta/stats.json

**基线/相关工作**

- https://unigen-x.github.io/unifolm-wla.github.io/
- https://github.com/unitreerobotics/unifolm-vla
- https://arxiv.org/abs/2511.14759（π*0.6 / RECAP：advantage-conditioned RL；硬任务吞吐翻倍、失败率约减半）
- https://arxiv.org/abs/2512.21970（StereoVLA：GeoSem 编码器；真实世界绝对成功率 +33.4%）
- https://arxiv.org/abs/2501.15830（SpatialVLA：Ego3D 位置编码；空间泛化）
- https://huggingface.co/docs/lerobot/en/unitree_g1（LeRobot G1 文档）

**规则（正文不可读，需登录/JS）**

- 中文：https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh
- 英文：https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh
- 赛事支持：challenge_support@unitree.com

**备注**：公开榜 Coming Soon；“榜首 <30%”未验证；Feishu 规则未读到正文；以上未知项应在第一周内通过邮件/规则页/调试探针解决。
<!-- ARTIFACT:END -->
