# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
## 0. 本轮结论

> 上一轮的 RUBICON 方向成立，但“物体中心 3D”还缺一块：真正的问题不是“物体在哪”，而是**所有位姿在运动中都可能失效**——腰部一动，头部双目外参变了；底盘一动，桌面平面和 3D 子目标变了；人手一进工作区，绝对轨迹就危险。本轮把 RUBICON 升级为 **RUBICON 2.0**，在原有“评分点→阶段进度”的骨架上加三个端口：
>
> - **EcoPort（能耗优化）**：把“能耗”拆成算力、延迟、物理动作三种预算；运输/接近走便宜路径，接触/恢复走全量 VLA；pivot 默认不动，动则计入能量代价。
> - **PosePort（姿态估计）**：维护一张全身姿态图 `base → torso → head_stereo → object → gripper → target → human`；运输用绝对位姿，接触用相对位姿，腰部运动后重投影，人手进入时降速/暂停。
> - **SERB（伦理审查）**：Safety / Evaluation integrity / Reproducibility / Bio-legal 四类可执行门禁，把“不撞人、不违规、可复现”变成运行时和提交前的检查。
>
> 底座选 **UnifoLM-WLA-1.0-Base（Apache-2.0，6B，G1，约 2500h，64 任务）**，不再从零训大模型；UnifoLM-VLA-0 的许可证在 HF/GitHub 上未见明确文件，不把它当默认底座。

## 1. 本轮新增/修正的事实

- **语言不是没有，而是被忽略了**：每个任务的 `meta/tasks.parquet` 有 **5 条英文复述**（用 `@` 分隔）。例如 HangCup 是 5 条 “Hang/Hook the cup…”；ArrangePlates 明确 “from right to left in the order of red, green, and blue”；PaperCupStacking 明确 “two on the bottom and one on top”；SpellRobot 明确拼 “robot”。上一轮“数据集没有语言、需要 LLM 生成”的判断需要修正：语言可直接用，重点转为**复述鲁棒性 + 语言约束解析**。
- **pivot 语义基本坐实**：在 OrganizeTools 的单文件 parquet（113 episodes / 122,499 帧）上，`pivot_3 ≈ waist yaw`（r≈0.73，slope 0.307，R²=0.532），`pivot_4 ≈ waist pitch`（r≈0.86，slope 0.6497，R²=0.737），`pivot_5` 全 0（很可能是 waist roll）；`angle_z=±0.8` 只占 0.018% 帧，疑为哨兵/伪影。**腰部是真实连续控制通道，不是噪声。**
- **pivot 使用高度任务相关**：OrganizeTools 持续用 waist yaw+pitch（std_p3=0.147，std_p4=0.118，p3∈[-0.516,0.569]，p4∈[0,0.627]）；StorePaddle/FoldTowel 的 p4 是回合级偏移（0→0.15）；PaperCupStacking/PickOutBatteries/Unlock 是 height 回合级偏移；OrganizeBookshelf/ZipUp 偶发 base 位移；多数任务近静态（p3=0，p4=0.15，height≈0.737）。**不能全局假设 pivot 常数，也不能全局假设它会动。**
- **头部相机/腰部本身也在动**：数据集同时有 `state_d435`/`action_d435`（头部 D435 的 6D 位姿）、`state_torso`/`action_torso`、`waist_state_joint`/`action.waist_action_joint`。OrganizeTools 的 D435 pitch std≈0.093、yaw std≈0.081，HangCup 也有 std≈0.014–0.019。**“固定头部双目”的假设不成立**；姿态图必须含 neck/head 动态。
- **标定不是全局统一**：32 任务至少 **10 组**不同头部双目标定；`fx` 186.03–296.15，基线（norm T）46.716–64.864mm，`cx` 左 302.45–365.43 / 右 315.98–384.27。`rectified=true` 不能直接信；必须按任务读 `camera_params` 并做极线/重投影验证。
- **时长差异大**：6.2s（HangCup）到 37.6s（ToolboxStorage）；StorePaddle 34.1s、SpellRobot 31.2s、PackPhone 29.2s、FoldTowel 25.8s、OrganizeTools 25.0s。长任务对 chunk/latency/阶段推进更敏感。
- **公开榜仍是占位**：`leaderboard.html` 的内联脚本自述 “The real, randomly-generated leaderboard is rendered here purely to sit (blurred) behind the … overlay”；搜索索引到的 GigaBrain-0/DM0/DreamZero/PI-0.5/WALL-OSS/MolmoAct2 详情页是合成演示，不是真实排名。**不能据此分析榜首。**
- **底座许可证**：数据集 Apache-2.0；UnifoLM-WLA-1.0-Base 的 HF/GitHub 明确 Apache-2.0，6B、约 2500h、64 任务、12.5GB、单卡 24GB 可微调/LoRA；UnifoLM-VLA-0 的 HF/GitHub 未见明确 license 文件（上一轮记录为 CC BY-NC-SA 4.0，需复核）。默认选 WLA-1.0。
- **规则仍未核实**：Feishu 不可读；评分权重、trial 数、外部数据/模型、任务特定逻辑、base/waist 限制、单任务时限、N 未知。

## 2. 竞争格局与“最可能强基线”的推断

- 真实榜首不可见；以下是对“最可能强基线”的分析，不是对排名的断言。公开榜的“GigaBrain-0 / DM0 / DreamZero / PI-0.5 / WALL-OSS / MolmoAct2”是随机占位，不是真实提交。
- **最强基线**：UnifoLM-WLA-1.0 微调（G1/2500h/64 任务/全身动作 token，Apache-2.0）；GigaBrain-0（world-model 数据、RGBD、CoT，3.5B/4B）；π0.5 / GR00T / OpenVLA-OFT。它们都可能用多视角、action chunk、5 条语言复述、外部数据和较大模型。
- 它们大概率仍会输在：
  1. 接触密集/小公差（插头、网线、锁、拉链、药瓶）最后几毫米；
  2. 长程 2–5 检查点的阶段推进、premature stop、失败重试；
  3. 人为干扰后的“暂停-重定位-恢复”；
  4. 腰部/头部运动导致的相机外参失效与平衡风险；
  5. 延迟/抖动/动作规律性；
  6. 许可证与可复现性（非商用权重、外部数据、硬编码）。
- 因此边际收益不在“再大一点的 VLA”，而在**竞赛层**：评分点/语言→阶段约束，姿态图→精密伺服，阶段化算力/能量预算，SERB 安全门禁。
- 没有真机时，先建 **Local Proxy Leaderboard（LPL）**：按 `info.json` 的 `unseen_object_3/human_1/human_4` 备注做留出扰动，离线看动作/进度/姿态，真机调试名额优先做单任务闭环。不要把公开榜当迭代信号。

## 3. 三条灵感词的落点

### 3.1 能耗优化 → EcoPort

- 评测环境是长任务（25–37s）、4 路视频、30fps、N 台机器人可能并发。全程跑最大 VLA 既慢又抖，且多机器人会互相拖延迟。
- **算力能量**：按阶段分配预算——运输/接近用缓存 chunk/小策略/检索；接触/恢复用全量 VLA + 多视角 + 相对位姿。`action_chunk_size` 可调：运输长、接触短。
- **物理能量**：pivot 默认保持示范中的稳定值；只有目标超出可达/视角/高度时才小范围动 waist/base；动作代价 `λ_v|v| + λ_ω|ω| + λ_h|Δh| + λ_w|Δwaist| + λ_a|Δa|²`。
- **多机器人**：N 个端口共享后端，按阶段优先级批处理；接触阶段优先；保持 p99 延迟 < chunk 时长，避免抖动。
- 指标：VLA calls/episode、p50/p95/p99 latency、jitter、energy per success、steps/episode。即使官方不计“能耗”，这些也直接影响完成率和稳定性。

### 3.2 姿态估计 → PosePort

- 不是“再加一个 6D pose 模型”，而是**一张运行时姿态图**：
  `base → torso → head_stereo → object → gripper → target → human`。
- 运输：绝对位姿（双目 + 任务标定 + 桌面平面）。
- 接触：相对位姿（腕部相机 + 夹爪 FK + 目标几何/关键点），对绝对标定误差不敏感。
- 腰部/头部一动：用 `waist_state_joint`/`state_torso`/`state_d435` 更新 head 相机位姿，重投影 3D 子目标；若重投影误差超阈值，暂停/重观测。
- 人手：RTMW/RTMW3D 关键点 → 人手-机器人最小距离 → SSM 降速/暂停。
- 语言：把 “right to left / red, green, blue / two on bottom, one on top / spell robot” 解析成**约束图**（顺序、颜色、数量、方向、空间关系），作为进度验证器的一部分。
- 精度直觉：桌面 1m 处 stereo 0.1px 视差≈6.2mm；0.5m≈1.5mm；腕部近景 + 相对位姿把接触误差压到毫米级。

### 3.3 伦理审查 → SERB

- 不做形式化 IRB；做**可执行的四类门禁**：
  - **S**afety：工作空间/速度/关节/腰部限位、平衡包络、人机分离、急停、watchdog、NaN/超限检查。
  - **E**valuation integrity：不硬编码任务坐标/轨迹；不针对评分表作弊；进度用学习头；披露所有外部数据/模型/人工干预。
  - **R**eproducibility：seed、config、模型卡、数据版本、审计日志、失败回放。
  - **B**io-legal：数据集 Apache-2.0、底座 Apache-2.0、第三方 NOTICE、人脸/人手隐私、非商用权重禁用。
- 运行时：人手进入工作区 → SSM 降速/暂停；离开 → 重定位 → 恢复；全程记录事件。
- 提交前：许可证清单、红队报告、安全案例、审计回放；缺一项不放行。

## 4. 创新点排序

| 顺序 | 创新点 | 价值 | 风险 | 依赖 |
|---|---|---|---|---|
| P0 | Rubric Compiler 2.0（score_steps + 语言约束）+ Progress Verifier | 高 | 低 | `info.json` + `tasks.parquet` |
| P0 | PoseGraph（全身/相机/物体/夹爪/人手） | 高 | 中 | 标定 + 双目/腕部 |
| P0 | SERB 安全/伦理门禁 + 人机 SSM | 高 | 低 | 规则 + 姿态 |
| P0 | Waist/Pivot Controller + Balance Shield | 高 | 中 | pivot 探针 |
| P1 | EcoScheduler（阶段化算力/能量 + 多机器人） | 高 | 中 | latency 预算 |
| P1 | 接触阶段相对位姿伺服（插/拉链/倒） | 高 | 中 | 腕部 + 技能 |
| P1 | 人为干扰恢复（暂停-重定位-重试） | 高 | 低 | 人手/位移检测 |
| P2 | 检查点条件化离线 RL / 优势加权 BC | 中高 | 中 | 阶段标签 |
| P2 | 语言复述鲁棒性 + 任务匹配 | 中 | 低 | 5 条复述 |
| P2 | 3D/世界模型增广 | 中 | 中 | 分割/深度/生成 |
| P3 | 仿真残差/恢复 RL | 中高 | 高 | 仿真资产 |

## 5. 核心押注 RUBICON 2.0

### 5.1 Rubric Compiler 2.0（P0）

- **动机**：`score_steps` 是公开稠密监督；语言里还有顺序/颜色/数量/方向约束。两者结合，能同时提高完整成功率和步骤分。
- **做法**：离线把每个任务编译成 `{phase_id, instruction, constraint_graph, success_predicate, max_steps, retry_policy}`；`constraint_graph` 从语言解析（顺序、颜色、计数、方向、空间关系），`success_predicate` 尽量用可观测变量（物体在架/在盒/在杯、夹爪状态、相对位姿）。
- **差异**：多数队伍只用一句语言；我们把评分表 + 5 条复述 + 约束图变成训练信号和运行时验证器。
- **资源**：离线 LLM/规则 + 小分类头；1 张 GPU、3–5 天。
- **风险**：评分点歧义、规则禁止任务特定逻辑。缓解：学习进度头为主，约束图只做 prompt/验证；先读规则。

### 5.2 PoseGraph（P0）

- **动机**：腰部/头部运动使 head 相机外参失效；每任务标定不同；接触需要毫米级相对位姿；人手需要安全距离。
- **做法**：节点 base/torso/head/object/gripper/target/human；静态边来自 `camera_params`，动态边来自 `waist_state_joint`/`state_torso`/`state_d435`/FK；视觉边来自 stereo/SAM2/6D pose/RTMW；每步更新并检查重投影/极线一致性；运输用绝对位姿，接触用相对位姿。
- **差异**：把“物体中心 3D”升级为“全身姿态一致性”；腰部/头部一动就重投影，而不是让策略在错误坐标系里硬做。
- **资源**：双目/腕部 + 开源模型；2 周；1–2 张 GPU 推理。
- **风险**：透明/反光物体深度空洞、标定漂移、人手遮挡。缓解：多视角、置信度门控、单目深度兜底、腕部近景。

### 5.3 Waist/Pivot Controller + Balance Shield（P0/P1）

- **动机**：pivot 不是常数；OrganizeTools 已证明 p3/p4≈waist yaw/pitch。用得好扩展可达/视角/高度；用不好摔。
- **做法**：VLA 只出双臂+夹爪；独立控制器出 waist/base/height。默认保持示范稳定值；目标超出可达/视角/高度时小范围动；能量代价 + 限幅 + 速率限制；平衡 shield 检测 lower_body/torso 偏移 → 清零 base、回中性 waist、保持 height、暂停手臂。
- **差异**：示范里几乎静态，所以这是 OOD，但也是被忽视的自由度；解耦后不用重训 VLA。
- **资源**：不计分单任务探针（每维 ±0.02–0.05）；1 周。
- **风险**：base 运动可能被规则禁止；腰部映射未官方确认；摔倒。缓解：默认静态、保守限幅、先探针、急停。

### 5.4 EcoScheduler（P1）

- **动机**：长任务 + 多机器人并发使延迟/抖动成为工程约束；全程大 VLA 会抖、会慢。
- **做法**：阶段预算表；运输/接近走缓存 chunk/小策略/检索；接触/恢复走全量 VLA；自适应 chunk（运输长、接触短）；多机器人按阶段优先级批处理；p99 延迟守门；能量/调用次数日志。
- **差异**：把“能耗优化”从模型压缩扩展到**运行时调度**；与 PoseGraph/阶段控制器共享信号。
- **资源**：1 周；无需重训。
- **风险**：模式切换抖动、缓存错配。缓解：滞回、固定调度、只在低风险阶段走便宜路径。

### 5.5 SERB（P0）

- **动机**：人机干扰是评分轴；许可证/外部数据/硬编码可能直接取消资格；可信度也重要。
- **做法**：四类门禁 + 运行时 monitor + 提交前 checklist；人手 SSM；审计日志；模型/数据许可证清单；红队测试。
- **差异**：把伦理/安全从“文档”变成“运行时 + 提交门禁”，既防事故也防 disqualification。
- **资源**：1 周；规则式。
- **风险**：误检导致停顿；规则不允许额外监控。缓解：高置信才停、超时恢复、只用机载相机。

### 5.6 接触阶段相对位姿伺服（P1）

- **动机**：Hard 任务的最后几毫米是纯 RGB 端到端的短板；没有力/触觉。
- **做法**：VLA 接近；腕部相机估计 gripper-target 相对位姿（插头-插座、拉链头-齿、瓶盖-瓶身、钥匙-锁）；小步伺服 + 微搜索 + 完成验证；失败回退到 VLA 重试。
- **差异**：混合式“VLA 接近 + 相对位姿精调”，比纯端到端稳。
- **资源**：先做 2–3 个技能；2 周。
- **风险**：任务特定、规则限制。缓解：技能保持通用（插入/对位/拉链），先确认规则。

### 5.7 人为干扰恢复（P1）

- **动机**：`human_1/human_4` 会移动/拿走/打开已完成部件；BC 没有恢复样本。
- **做法**：人手/物体位移检测 → 暂停 → 重观测 → 更新姿态图 → 重定位 → 重试；用合成人手/瞬移增广；按备注建扰动测试集。
- **差异**：把恢复当一等行为；直接打人为干扰评分轴。
- **资源**：1 周；检测器 + 规则。
- **风险**：误检、时间预算。缓解：滞回、超时、只在高置信时暂停。

## 6. 修剪/暂缓

- **从零训练大模型**：不划算；WLA-1.0/GigaBrain-0 已开源。
- **真机在线 RL**：样本效率/安全/时间都不允许。
- **运行时 LLM/VLM API**：延迟/网络/规则风险；离线编译。
- **任务特定硬编码轨迹**：泛化差，可能违规；用约束图 + 学习进度头。
- **激进 pivot**：未探针前默认静态；平衡优先。
- **完整仿真 RL**：P3；规则/资产/时间不确定，先不做。
- **大规模 3D 生成增广**：P2；先把真实数据 + 轻量增广做好。
- **“再大一点的 VLA”**：不是本轮边际收益所在。

## 7. 8 周执行顺序

| 周 | 目标 | 交付 |
|---|---|---|
| 1 | 规则/接口/基线；Rubric 2.0；pivot 探针；许可证审计 | 可跑 baseline、32 任务 rubric JSON、pivot 报告、SERB checklist |
| 2 | PoseGraph + 标定验证；语言约束解析；数据加载器 | 姿态图 v1、10 组标定表、约束图 |
| 3 | WLA-1.0/GigaBrain-0 微调（多视角+proprio+语言） | 首个可评测 checkpoint |
| 4 | 进度头 + 阶段控制器 + 重试；人手 SSM；SERB runtime | 闭环策略 v1 |
| 5 | Waist/Pivot + Balance Shield；EcoScheduler；接触技能 | 全身/能效/硬任务增强 |
| 6 | 相对位姿伺服；干扰恢复；消融 | 策略 v2 + 消融报告 |
| 7 | 单任务调试 + 计分多任务；latency/energy profiling | 首个榜单成绩 |
| 8 | 迭代；最终提交；审计/复现 | 最终提交包 |

## 8. 必须先解决的问题

1. Feishu 规则（不可读）：评分权重、trial 数、外部数据/模型、任务特定逻辑、base/waist 限制、单任务时限、N。
2. `pivot[3:6]` 提交端语义：数据集映射已强，但需不计分探针确认符号/限位。
3. 评测语言：是否用同样 5 条复述，还是未见复述/中文；决定语言增强强度。
4. 评测相机：是否与数据集同一标定；10 组差异如何处理。
5. 榜单口径：平均成功率/步骤分权重；是否按任务归一化。
6. 人机干扰：脚本化还是自适应；是否允许主动暂停。
7. 底座许可：WLA-1.0 Apache-2.0 是否被规则允许；第三方 NOTICE。
8. 调试名额：优先 T01/T04/T10/T15/T16/T24/T30。

## 9. 一句话押注

**以 Apache-2.0 的 UnifoLM-WLA-1.0 为底座，叠加 RUBICON 2.0 竞赛层：评分点/语言→阶段约束，全身姿态图→精密伺服，阶段化算力/能量预算，SERB 安全门禁——不再从零训更大的端到端 VLA。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
## A. 结论

本轮把上一轮的 **RUBICON**（Rubric 条件化、物体中心、平衡感知）升级为 **RUBICON 2.0**：保留“官方评分点 → 可验证阶段进度”的骨架，新增三条与随机灵感词对应的工程线：

1. **EcoPort（能耗优化）**：把能耗拆成算力、延迟、物理动作三种预算；按阶段调度 VLA/缓存/小策略，pivot 默认静态、动则计成本。
2. **PosePort（姿态估计）**：维护 `base → torso → head_stereo → object → gripper → target → human` 的运行时姿态图；运输用绝对位姿，接触用相对位姿，腰部/头部运动后重投影。
3. **SERB（伦理审查）**：Safety / Evaluation integrity / Reproducibility / Bio-legal 四类门禁；人手进入工作区时 SSM 降速/暂停，提交前做许可证/红队/审计检查。

底座优先 **UnifoLM-WLA-1.0-Base（Apache-2.0，6B，G1，约 2500h，64 任务）**；不再从零训更大的端到端 VLA。以下所有事实、表格、架构、实验与风险均以 2026-10-23 可访问的公开页面/文件为准；无法核实的地方明确标注“未核实”。

## B. 本轮新增/修正事实（检索日期 2026-10-23）

| # | 事实 | 证据/来源 |
|---|---|---|
| 1 | 每个任务的 `meta/tasks.parquet` 含 **5 条英文复述**（`@` 分隔），不是“没有语言” | `G1_Dex1_HangCup/meta/tasks.parquet`、`OrganizeTools`、`FoldTowel`、`PlugCharger` 等 32 个数据集逐一抽取 |
| 2 | `pivot_3 ≈ waist yaw`、`pivot_4 ≈ waist pitch`、`pivot_5` 全 0；OrganizeTools 单文件 113 episodes/122,499 帧上 r≈0.73/0.86，R²=0.532/0.737 | `G1_Dex1_OrganizeTools/data/chunk-000/file-000.parquet` 的 `action.pivot` 与 `observation.state.waist_state_joint` 回归 |
| 3 | pivot 使用高度任务相关：OrganizeTools 连续用 waist；StorePaddle/FoldTowel 用 p4 回合级偏移；PaperCupStacking/PickOutBatteries/Unlock 用 height 偏移；OrganizeBookshelf/ZipUp 偶发 base | 32 个 `meta/stats.json` 的 `action.pivot` min/max/std/q01/q99 |
| 4 | 头部相机本身在动：`state_d435`/`action_d435` 存在，OrganizeTools 的 D435 pitch std≈0.093、yaw std≈0.081；HangCup 也有 0.014–0.019 | `meta/info.json` 特征表；各任务 `stats.json` |
| 5 | 32 任务至少 **10 组**不同头部双目标定；`fx` 186.03–296.15，基线 norm(T) 46.716–64.864mm，`cx` 左 302.45–365.43 / 右 315.98–384.27 | 32 个 `meta/info.json` 的 `camera_params.head_stereo` |
| 6 | Episode 时长 6.2s（HangCup）–37.6s（ToolboxStorage）；长任务还有 StorePaddle 34.1s、SpellRobot 31.2s、PackPhone 29.2s、FoldTowel 25.8s、OrganizeTools 25.0s | `frame_index.count` / `episode_index` / fps=30 |
| 7 | 公开榜仍是 Coming Soon；`leaderboard.html` 内联脚本自述 “The real, randomly-generated leaderboard is rendered here purely to sit (blurred) behind the … overlay” | `https://unibot.unitree.com/leaderboard.html`（2026-10-23，Chrome UA 抓取 12,226 字节） |
| 8 | 搜索索引到的 GigaBrain-0/DM0/DreamZero/PI-0.5/WALL-OSS/MolmoAct2 详情页是合成演示，不能当真实排名 | 榜单占位脚本 + 详情页无真实提交数据（2026-10-23） |
| 9 | 数据集 license 为 Apache-2.0；UnifoLM-WLA-1.0-Base 为 Apache-2.0（6B，约 2500h，64 任务，12.5GB，单卡 24GB 可微调/LoRA）；UnifoLM-VLA-0 的 HF/GitHub 未见明确 license 文件 | HF dataset card；`github.com/unitreerobotics/unifolm-wla`；`huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base`；`unitreerobotics/UnifoLM-VLA-Base` |
| 10 | GigaBrain-0.7-3.5B-Base 的 HF 标注为 Apache-2.0 | `huggingface.co/open-gigaai/GigaBrain-0.7-3.5B-Base` |
| 11 | 数据集约 1k episodes/任务（HangCup 1043、ArrangePlates 1069、ArrangeTestTubes 1004、ConveyorSorting 1049、OrganizeStationery 1028、FoldTowel 1053、PlugCharger 1022、ToolboxStorage 1064），30fps；官方页称 32k/169h，按 32 个 `stats.json` 求和为 **33,276 episodes / 169.3h**（ColorArrangement 1533 是 outlier） | 各任务 `meta/info.json`/`stats.json`；HF 数据集 README；挑战赛页 |
| 12 | Feishu 规则正文仍不可读；评分权重、trial 数、外部数据/模型、任务特定逻辑、base/waist 限制、单任务时限、N 均未核实 | 飞书链接（见 Q）；curl/webfetch 失败 |

**关键修正**：上一轮把“数据集没有语言”当作核心瓶颈，这是不准确的。数据特征里确实没有 language 字段，但 `meta/tasks.parquet` 提供了 5 条复述。真正的问题是**评测语言是否使用同样 5 条、是否留出未见复述、是否出现中文**，以及如何把语言里的顺序/颜色/数量/方向约束变成运行时验证器。

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
- **硬骨头**：T05 拔网线、T09 工具箱锁、T10 插插头、T12 开锁、T14 拧药瓶、T16 叠毛巾、T28 装耳机、T29 装手机。接触密集/变形/小公差，适合相对位姿 + 精密技能 + 离线 RL。
- **注意**：步骤分是“平均成功率 + 步骤分”综合排序的一部分，权重未知；不能为了首点牺牲完整成功率。
- **期望分示例**：2 检查点任务若 `P(首点)=0.9`、`P(完整|首点)=0.3`，期望 ≈ `0.9×50 + 0.27×50 = 58.5`；3 检查点任务若 `0.8/0.5/0.3`，期望 ≈ `0.8×30 + 0.4×30 + 0.12×40 = 40.8`。高地板任务先稳首点，硬任务冲“第二/第三点”的边际收益更大。

### C.2 时长与 pivot 活动度（按 avg episode 时长降序）

| 任务 | avg s | episodes | pivot 模式 |
|---|---:|---:|---|
| ToolboxStorage | 37.6 | 1064 | 近静态（p4=0.15, h≈0.736） |
| StorePaddle | 34.1 | 1047 | p4 回合级偏移（0→0.15） |
| SpellRobot | 31.2 | 1018 | 近静态（p4=0.15, h≈0.739） |
| PackPhone | 29.2 | 1016 | 近静态（p4=0.15, h≈0.737） |
| FoldTowel | 25.8 | 1053 | p4 回合级偏移（0→0.15） |
| OrganizeTools | 25.0 | 1032 | **连续 waist yaw+pitch**（p3∈[-0.516,0.569], p4∈[0,0.627]） |
| StoreEarphones | 24.1 | 982 | 近静态（p4=0.15, h≈0.740） |
| OrganizeStationery | 23.9 | 1028 | 近静态（p4=0.15, h≈0.740） |
| PourOutMedicine | 21.8 | 979 | 近静态（p4=0.15, h≈0.740） |
| ArrangePlates | 21.3 | 1069 | 近静态（p4=0.15, h≈0.737） |
| OrganizePencilCase | 20.5 | 1024 | 近静态（p4=0.15, h≈0.738） |
| StoreCups | 19.8 | 1025 | 近静态（p4=0.15, h≈0.740） |
| PackDoll | 19.6 | 1060 | 近静态（p4=0.15, h≈0.737） |
| RemovePinnedNote | 19.6 | 1026 | 近静态（p4=0.15, h≈0.740） |
| ArrangeTestTubes | 17.8 | 1004 | 近静态（p4=0.15, h≈0.738） |
| PlugInEthernet | 16.4 | 1009 | 近静态（p4=0.15, h≈0.738） |
| PickOutBatteries | 16.1 | 993 | height 回合级偏移（h≈0.729） |
| SyringeWaterTransfer | 15.3 | 1034 | 近静态（p4=0.15, h≈0.738） |
| PlugCharger | 15.1 | 1022 | 近静态（p4=0.15, h≈0.740） |
| PackBag | 15.1 | 1067 | 近静态（p4=0.15, h≈0.740） |
| Unlock | 14.5 | 970 | height 回合级偏移（h≈0.733） |
| ZipUp | 14.1 | 1006 | 偶发 base（vx/vy 极值 0.2–0.37） |
| PaperCupStacking | 13.9 | 969 | height 回合级偏移（h≈0.727） |
| ColorArrangement | 13.6 | 1533 | 近静态（p4=0.15, h≈0.738） |
| ConveyorSorting | 12.2 | 1049 | 近静态（p4=0.15, h≈0.739） |
| PlacePhotoFrame | 11.2 | 1041 | 近静态（p4=0.15, h≈0.736） |
| FruitCollection | 10.8 | 1050 | 近静态（p4=0.15, h≈0.739） |
| FruitSorting | 10.7 | 1032 | 近静态（p4=0.15, h≈0.731） |
| DisconnectEthernet | 10.5 | 1025 | 近静态（p4=0.15, h≈0.739） |
| OrganizeBookshelf | 10.3 | 1027 | 偶发 base（vx/vy 极值 0.2–0.37） |
| StackBowls | 10.1 | 979 | 近静态（p4=0.15, h≈0.740） |
| HangCup | 6.2 | 1043 | 近静态（p4=0.15, h≈0.738） |

> 结论：**pivot 不是全局常数，也不是全局活动**。OrganizeTools 是唯一持续使用 waist yaw+pitch 的任务；StorePaddle/FoldTowel 用 p4 回合级偏移；PickOutBatteries/Unlock/PaperCupStacking 用 height 偏移；ZipUp/OrganizeBookshelf 偶发 base；其余近静态。控制器必须**按任务配置**，不能一刀切。

### C.3 头部双目标定分组（32 任务，10 组）

| 组 | fx | fy | cxL | cxR | baseline norm(T) mm | 任务 |
|---|---:|---:|---:|---:|---:|---|
| G1 | 282.37 | 282.75 | 311.53 | 329.96 | 58.26 | ArrangePlates, ArrangeTestTubes, ConveyorSorting, FruitCollection, FruitSorting, HangCup, OrganizePencilCase, OrganizeTools, PackPhone, PickOutBatteries |
| G2 | 263.38 | 262.78 | 314.70 | 342.33 | 56.51 | ColorArrangement, OrganizeStationery, PackBag, PourOutMedicine |
| G3 | 227.74 | 235.07 | 331.68 | 371.73 | 61.50 | DisconnectEthernet, PlacePhotoFrame, PlugInEthernet, RemovePinnedNote, SpellRobot |
| G4 | 276.00 | 275.47 | 310.45 | 322.51 | 57.06 | FoldTowel |
| G5 | 186.03 | 186.50 | 361.87 | 375.01 | 54.88 | OrganizeBookshelf, StackBowls, ZipUp |
| G6 | 296.15 | 264.05 | 304.06 | 326.39 | 64.86 | PackDoll, PaperCupStacking, StoreEarphones, ToolboxStorage, Unlock |
| G7 | 238.56 | 244.50 | 302.45 | 315.98 | 46.72 | PlugCharger |
| G8 | 273.66 | 273.88 | 338.23 | 384.27 | 58.86 | StoreCups |
| G9 | 279.22 | 278.91 | 339.91 | 336.73 | 58.63 | StorePaddle |
| G10 | 275.52 | 278.12 | 365.43 | 373.30 | 52.56 | SyringeWaterTransfer |

> 影响：`fx` 相差 1.6×，baseline 相差 1.39×，`cx` 相差 80+px。单一“已校正双目”模型不能跨任务硬套；必须按任务读 `camera_params`，并做极线/重投影验证。G5/G7 的 `fB` 最小，1m 处 0.1px 视差约 9–10mm；G1 约 6.1mm；0.5m 处分别约 2.4mm 和 1.5mm。

## D. 数据集与语言

- LeRobot v3.0；32 个任务各一个 HF 数据集；`lower_body[15]` = 双腿 6+6 + 腰 3；`action.pivot[7]`；4 路相机（头部双目 + 左右腕），480×640×3，30fps；约 33.3k episodes / 169.3h（官方页称 32k/169h）。
- `meta/tasks.parquet` 每个任务 1 行，`task_index=0`，`task` 字段是 5 条英文复述用 `@` 分隔。32 个数据集逐一确认均为 5 条。
- 语言示例（首条）：
  - HangCup: “Hang the cup on the marked spot on the cup rack.”
  - ArrangePlates: “Place the plates on the rack from right to left in the order of red, green, and blue.”
  - PaperCupStacking: “Stack the paper cups in front of you with two on the bottom and one on top.”
  - SpellRobot: “Arrange the letter blocks to spell "robot".”
  - ConveyorSorting: “Pick up the food items moving on the conveyor belt and sort them onto the rack on the right by category.”
  - ToolboxStorage: “Store all the tools on the table in the toolbox and lock the toolbox.”
- 训练用途：① 5 条复述全用，做语言条件；② 留一法（leave-one-paraphrase-out）验证；③ 用 LLM 离线解析顺序/颜色/数量/方向/空间关系，生成 `constraint_graph`；④ 评测若出现中文/未见复述，用翻译/复述增广兜底（是否允许外部数据需先读规则）。
- 注意：数据特征表里没有 `language` 列，只有 `task_index`；提交接口的 `observation.language` 是字符串。训练时需要把 `task_index → task.parquet` 的复述映射进来，不要只喂 task id。

## E. Pivot 语义分析

### E.1 数据与方法

- 文件：`G1_Dex1_OrganizeTools/data/chunk-000/file-000.parquet`（约 100MB，122,499 行，113 episodes；**不是全量 1032 episodes**）。
- 列：`action.pivot[7]`、`observation.state.waist_state_joint[3]`（yaw, roll, pitch）、`observation.state.state_torso[6]`、`observation.state.state_d435[6]`。
- 方法：逐帧对齐，计算 Pearson r、线性回归 `pivot_i ~ waist_j`；检查 p5、angle_z、height。
- 结果：
  - `pivot_3` vs waist yaw：r≈0.73，slope 0.307，intercept -0.0219，R²=0.532。
  - `pivot_4` vs waist pitch：r≈0.86，slope 0.6497，intercept 0.1042，R²=0.737。
  - `pivot_5` 全 0（很可能是 waist roll，但数据里没有变化，无法回归确认）。
  - `angle_z=±0.8` 只占 0.0253%（>0.5）/0.018%（±0.8）帧，疑为哨兵/伪影；不要把它当真实转向指令。
  - `height` 0.6946–0.740；与 torso/D435 z 弱相关（r≈0.25–0.27），更像独立的升降通道。
- 解释：`pivot_3/4/5` 很可能是 waist yaw/pitch/roll 的缩放目标；`pivot_0/1/2` 是 base vx/vy/angle_z；`pivot_6` 是 height。提交端 README 只写 “Lower-body / pivot target”，没有逐维文档；**数据集证据强，但官方语义仍需不计分探针确认**。

### E.2 任务相关模式

| 模式 | 任务 | 证据 | 控制建议 |
|---|---|---|---|
| 连续 waist yaw+pitch | OrganizeTools | p3 std 0.147，p4 std 0.118；p3∈[-0.516,0.569]，p4∈[0,0.627]；113/113 回合内变化 | 用 waist 跟随工具架左右/上下；小步、限速、平衡 shield |
| p4 回合级偏移 | StorePaddle, FoldTowel | p4 q50 0.1132/0.1198，max 0.15，min 0，q01–q99 很窄 | 回合开始设定一次 waist pitch，过程保持 |
| height 回合级偏移 | PaperCupStacking, PickOutBatteries, Unlock | height std 0.019–0.025，q01–q99 很窄；均值 0.727/0.729/0.733 | 回合开始升降一次，过程保持 |
| 偶发 base | OrganizeBookshelf, ZipUp | vx/vy 极值 0.2–0.37，q01–q99 很窄 | 默认静态；仅在够不到时短脉冲 |
| 近静态 | 其余 26 任务 | p3=0，p4=0.15，height≈0.736–0.740 | 默认保持示范值；不要为了“用上 pivot”而乱动 |

### E.3 提交端探针建议

1. 选 HangCup（近静态）和 OrganizeTools（连续 waist）各一个不计分单任务。
2. 逐维小步测试 `pivot[3]`、`pivot[4]`、`pivot[5]`：±0.02、±0.05，观察 `waist_state_joint`/`state_torso`/`state_d435` 的响应符号、限位、延迟。
3. 测试 `pivot[0/1/2]` 的 base 响应；确认是否被规则允许、是否触发安全限制。
4. 测试 `pivot[6]` height 的范围/速率；确认 0.6946–0.740 是否安全。
5. 记录“命令→状态”的延迟/死区/饱和；把结果写进控制器配置，不要用默认假设。
6. 若 base/waist 被禁止，退回“静态 pivot + 双臂 + 相对位姿”方案；RUBICON 2.0 仍成立。

## F. 头部姿态与标定审计

### F.1 头部相机在动

`action_d435`/`state_d435` 是 6D 头部相机位姿。统计（std，xyz+rpy）：

| 任务 | σx | σy | σz | σroll | σpitch | σyaw |
|---|---:|---:|---:|---:|---:|---:|
| HangCup | 0.007 | 0.003 | 0.002 | 0.014 | 0.018 | 0.019 |
| OrganizeTools | 0.038 | 0.013 | 0.015 | 0.035 | 0.093 | 0.081 |
| FoldTowel | 0.021 | 0.004 | 0.005 | 0.018 | 0.050 | 0.037 |
| ConveyorSorting | 0.009 | 0.003 | 0.003 | 0.012 | 0.022 | 0.024 |

> 即使 HangCup 这种 6.2s 的“近静态”任务，头部也有 1–2cm/1–2° 的运动；OrganizeTools 的 pitch/yaw 达 5–9°。**固定外参假设会让 3D 子目标在长任务里漂移。**

### F.2 深度误差

`Z = fB/d`，`dZ/dd = -Z²/(fB)`。对 G1（f≈282.37px，B≈58.26mm，fB≈16.45 m·px）：

- Z=1.0m：0.1px 视差 ≈ 6.1mm 深度误差；Z=0.5m：≈1.5mm。
- G5（f≈186.03，B≈54.88mm，fB≈10.21）：Z=1.0m ≈ 9.8mm/0.1px；Z=0.5m ≈ 2.5mm。
- G7（f≈238.56，B≈46.72mm，fB≈11.15）：Z=1.0m ≈ 9.0mm/0.1px；Z=0.5m ≈ 2.2mm。

> 结论：桌面 0.5–1m 的头部双目只能给“厘米级”粗定位；接触最后几毫米必须靠腕部近景 + 相对位姿，不能只靠头部 stereo。

### F.3 处理策略

- 按任务读 `camera_params`，不要用全局常量；`rectified=true` 也要检查极线误差。
- 双目只用于**粗定位/物体中心/桌面平面**；接触用**腕部相对位姿**。
- 腰部/头部运动后，用 `state_torso`/`state_d435`/`waist_state_joint` 更新 `T_base_head`，重投影 3D 子目标；重投影误差 > 阈值就暂停/重观测。
- 透明/反光物体（杯子、瓶子、药瓶）深度空洞：用多视角、单目深度兜底、腕部近景、轮廓/关键点。
- 评测相机若与数据集不同，先在调试任务上做一次外参/尺度校验；不要假设同名相机就是同一标定。

## G. 榜单审计与竞争分析

### G.1 公开榜仍是占位

- `https://unibot.unitree.com/leaderboard.html`（2026-10-23）仍显示 “排行榜即将公开 / Coming Soon”。
- 页面内联脚本原文：*“The real, randomly-generated leaderboard is rendered here purely to sit (blurred) behind the "排行榜即将公开" overlay. The board container is blurred + inert via inline style in the markup, so it is masked from the first frame — this script only fills it in; it never unmasks anything.”*
- 因此：榜单上的名字/分数是随机生成的背景，不是真实提交；搜索索引里的 GigaBrain-0/xembody、DM0/Embodied AI Institute、DreamZero/World Model Lab、PI-0.5/RoboReasoner、WALL-OSS-0.5/Generalist Robotics、MolmoAct2/DexHacker 详情页是合成演示。**不要据此做“榜首方案分析”。**

### G.2 最可能强基线（推断，不是排名）

| 基线 | 优势 | 可能短板 | 许可证 |
|---|---|---|---|
| UnifoLM-WLA-1.0-Base 微调 | G1/2500h/64 任务/全身动作 token；Apache-2.0；单卡 24GB 可微调 | 无公开成功率；服务器默认只支持两指夹爪格式；挑战 32 任务需再微调 | Apache-2.0 |
| GigaBrain-0 / 0.7 微调 | world-model 数据、RGBD、CoT、real2real/human/view/sim2real | 3.5B/4B 推理成本；挑战数据分布不同；需核实动作接口 | 0.7-3.5B-Base 为 Apache-2.0 |
| π0.5 / GR00T / OpenVLA-OFT | 强通用 VLA、action chunk、多视角 | 非 G1 专用；接触精度/腰部控制弱；许可证各异 | 需逐个核实 |
| 从零/大小模型 | 可定制 | 数据/算力打不过 Unitree；泛化差 | — |

### G.3 他们大概率仍会输的地方

1. **接触密集/小公差**：T05/T10/T12/T14/T16/T19/T28/T29 的最后几毫米。
2. **长程检查点**：T09/T15/T16/T17/T18/T22/T28 的 4–5 检查点；premature stop、漏点、失败不重试。
3. **人为干扰**：`human_1/human_4` 移动/拿走/打开已完成部件；BC 没有恢复样本。
4. **腰部/头部运动**：外参失效、3D 子目标漂移、平衡风险。
5. **延迟/抖动/多机器人并发**：长任务 + 4 路视频 + N 端口。
6. **许可证/可复现性**：非商用权重、外部数据、硬编码、审计缺失。

### G.4 Local Proxy Leaderboard（LPL）

公开榜不可用，先建本地代理榜：

- **离线**：留出 episode（每任务 10–20%），看动作 L1/DTW、阶段分类、进度回归、物体 3D/相对位姿误差。
- **半离线**：用 `info.json` 的 `unseen_object_3/human_1/human_4` 备注，构造留出扰动（物体位移、拿走、开合、人手入镜），在仿真或真机调试中跑。
- **真机**：优先 T01/T04/T10/T15/T16/T24/T30；每任务 5–10 trials；记录成功率、检查点、恢复率、延迟。
- **语言**：5 条复述留一法；若允许，加中文/同义复述。
- **报告**：按难度、接触密度、时长、pivot 模式、扰动类型分桶；不要只看总分。

## H. 底座与许可证审计

| 资产 | 许可证 | 证据 | 用法 |
|---|---|---|---|
| UniBot 数据集 | Apache-2.0 | HF dataset card | 可商用/可改；保留 NOTICE |
| UnifoLM-WLA-1.0-Base | Apache-2.0 | GitHub README、HF card；12.5GB/24GB 来自 2026-10-10 二手报道，需以官方为准 | **默认底座**；6B/2500h/64 任务；单卡 24GB 可微调/LoRA（待官方复核） |
| UnifoLM-VLA-0 | 未见明确 license（上一轮记录 CC BY-NC-SA 4.0，需复核） | HF `unitreerobotics/UnifoLM-VLA-Base` 无 license 字段；GitHub 无 LICENSE | 不默认使用；若用，先书面确认 |
| GigaBrain-0.7-3.5B-Base | Apache-2.0 | HF API | 可选底座/数据生成；需核实动作接口 |
| Qwen2.5-VL | Apache-2.0 | 公开模型卡 | 可作为 VLM backbone |
| Qwen3-VL | 需核实 | 公开模型卡 | WLA-1.0 的 ER 底座；以官方为准 |
| 第三方组件 | 各自许可证 | `NOTICE`/`THIRD_PARTY_LICENSES.md` | 提交前逐项核对 |

> 结论：**优先 WLA-1.0-Base**。它同时满足 G1、全身动作、Apache-2.0、单卡可微调四点；UnifoLM-VLA-0 的许可证不清晰，不作为默认底座。若规则允许外部预训练模型，WLA-1.0 是最干净的起点；若不允许，则用挑战数据从头微调一个小模型，RUBICON 2.0 的竞赛层仍然适用。

## I. RUBICON 2.0 架构

### I.1 离线

```text
32 × LeRobot v3 数据集（32k episodes / 169h）
        │
        ├─ 语言：meta/tasks.parquet 的 5 条复述
        ├─ Rubric Compiler 2.0：score_steps + 语言约束 → phase/constraint_graph
        ├─ DemoCompiler：双目深度 + SAM2/GroundingDINO + 阶段切分 + 检查点标签
        ├─ 姿态监督：state_torso / state_d435 / waist_state_joint / EE pose
        ├─ 增广：背景/位置/干扰物/人手/物体瞬移（规则允许时）
        ▼
结构化数据集（阶段、约束图、物体 3D、接触、检查点、抓取/放置位姿）
        │
        ├─ VLA 微调（WLA-1.0/GigaBrain-0；多视角 + proprio + 语言 + 3D token）
        ├─ 辅助头：阶段分类 / 进度回归 / 深度/关键点 / 相对位姿
        ├─ 离线 RL：goal-conditioned value + 优势加权 BC（P2）
        ├─ 检索索引：物体中心帧/动作块（EcoPort 的便宜路径）
        └─ 审计：数据版本、许可证、seed、config
        ▼
策略包：VLA + 进度头 + 姿态图 + rubric DB + pivot controller + skills + SERB
```

### I.2 在线

```text
obs（4 图 + proprio + language）
        │
        ├─ 感知：双目深度、物体 3D、桌面平面、人手/位移检测
        ├─ 任务匹配：language + 首帧 → 32 任务之一
        ├─ Rubric/阶段：当前 phase 的 instruction/constraint/predicate
        ├─ PoseGraph：base→torso→head→object→gripper→target→human
        ├─ VLA：多视角 + proprio + phase prompt → 双臂/夹爪动作
        ├─ EcoScheduler：按 phase 选 VLA/缓存/小策略；自适应 chunk
        ├─ 精密技能：插入/拉链/倾倒的最后几厘米（相对位姿）
        ├─ Pivot Controller：安全先验 + 可达/高度补偿 + 能量代价
        ├─ Balance Shield：风险时清零 base、回中性 waist、保持 height、暂停手臂
        ├─ 进度头：推进 phase / 触发重试 / 触发恢复
        ├─ SERB：关节/速度/工作空间/人机距离/NaN/watchdog/审计
        ▼
action（joint 或 ee + grippers + pivot + meta.token）
```

### I.3 伪代码

```python
class RubiconPolicy:
    def __init__(self):
        self.token = os.environ["UNIBOT_SUBMISSION_TOKEN"]
        self.control_space = "joint"          # 或 "ee"，由实验决定
        self.chunk = 8
        self.vla = load_vla("UnifoLM-WLA-1.0-Base")
        self.progress = load_progress_head(...)
        self.perception = Perception(...)     # stereo, SAM2, human detector
        self.pose_graph = PoseGraph(...)
        self.rubrics = load_rubrics("rubrics.json")
        self.pivot = PivotController(...)
        self.eco = EcoScheduler(...)
        self.serb = SERBMonitor(...)
        self.skills = SkillLibrary(...)

    def reset(self):
        self.phase = 0
        self.memory = SceneMemory()
        self.retry = 0
        self.mode = "NORMAL"                  # NORMAL / WAIT / RECOVER
        self.pose_graph.reset()
        self.eco.reset()
        self.serb.reset()

    def get_action(self, obs):
        task = match_task(obs["observation.language"], obs)
        rubric = self.rubrics[task]
        scene = self.perception.update(obs)
        self.pose_graph.update(obs, scene)
        self.serb.update(obs, scene)

        if self.serb.human_in_workspace():
            self.mode = "WAIT"
            return self.hold_action(obs, scene)

        if self.mode == "WAIT" and self.serb.human_clear():
            self.mode = "RECOVER"
            self.pose_graph.reobserve()

        if self.mode == "RECOVER":
            action = self.skills.recover(obs, scene, self.pose_graph)
            if action is not None:
                self.mode = "NORMAL"
                return self.pack(action, obs)

        phase = rubric.phases[self.phase]
        plan = self.eco.plan(phase, scene, self.vla)
        if plan.use_cache:
            action = plan.cached_action
        else:
            action = self.vla.act(obs, scene, phase, self.pose_graph)
        action = self.skills.refine(phase, action, scene, self.pose_graph)
        action = self.pivot.control(phase, action, scene, self.pose_graph)
        action = self.serb.clamp(action, obs)

        progress = self.progress.step(obs, scene, phase)
        if progress.done:
            self.phase = min(self.phase + 1, len(rubric.phases) - 1)
            self.retry = 0
        elif progress.stuck:
            self.retry += 1
            if self.retry >= rubric.retry_policy.max_retries:
                self.mode = "RECOVER"
                self.retry = 0

        self.serb.log(obs, action, scene, progress)
        return self.pack(action, obs)
```

> `pack` 按提交 README 拼 `action.left_arm/right_arm/left_gripper/right_gripper/pivot`（joint）或 `action.*_ee_pose_gripper_base`（ee），并带 `meta.token`；每个动作数组保留 `T_a` 时间轴。

## J. Rubric Compiler 2.0

### J.1 Schema

```json
{
  "task_id": "T21",
  "name": "ArrangePlates",
  "instruction": "Place the plates on the rack from right to left in the order of red, green, and blue.",
  "constraints": {
    "order": ["red", "green", "blue"],
    "direction": "right_to_left",
    "target": "plate_rack",
    "count": 3,
    "spatial": ["on_rack"]
  },
  "phases": [
    {"id": 0, "predicate": "red_plate_on_rack", "score": 30, "max_steps": 900},
    {"id": 1, "predicate": "green_plate_on_rack", "score": 30, "max_steps": 900},
    {"id": 2, "predicate": "blue_plate_on_rack", "score": 40, "max_steps": 900}
  ],
  "retry_policy": {"max_retries": 2, "on_stuck": "reobserve_and_retry"}
}
```

> `phases` 与 `score_steps` 的 1:1 对齐需离线校准；语言顺序是强先验，但不能假设评分点一定按颜色切。对 `ConveyorSorting` 这类动态任务，phase 应按“类别/物体”而不是固定时间切。

### J.2 语言约束示例

| 任务 | 语言约束 | 运行时验证 |
|---|---|---|
| ArrangePlates | 顺序 red→green→blue；方向 right→left；目标 rack | 检测三种颜色盘子在 rack 上的相对位置/顺序 |
| ColorArrangement | 顺序 red→green→yellow；right→left | 检测积木颜色序列 |
| PaperCupStacking | 2 个在下、1 个在上；在身前 | 检测杯子堆叠拓扑/数量 |
| SpellRobot | 拼 “robot” | 检测字母块序列/OCR |
| FruitSorting | 按颜色匹配盘子 | 检测水果-盘子颜色配对 |
| ConveyorSorting | 按类别放到右侧 rack；物体在动 | 跟踪传送带物体、类别、放置位置 |
| ToolboxStorage | 所有工具进工具箱并上锁 | 检测工具在箱内、锁扣状态 |
| FoldTowel | 叠好并放到旁边 | 检测毛巾折叠次数/最终位姿 |
| PackDoll | 所有娃娃进包，包直立 | 检测包内物体、包姿态 |
| StoreCups | 纸杯逐个上架 | 检测杯子在架、顺序 |

### J.3 Progress Verifier

- **输入**：当前 4 图、物体检测/3D、夹爪状态、EE pose、phase。
- **输出**：`done`、`progress∈[0,1]`、`stuck`、`phase_confidence`。
- **训练**：用 `score_steps` + 语言约束自动对齐 phase 标签；小 Transformer/MLP 在物体中心特征上训练；辅助损失（phase 分类、进度回归、物体在目标区域二分类）。
- **运行时**：置信度阈值 + 滞回 + 最小 dwell time；`stuck` 触发重试/恢复；不要用硬编码坐标。
- **防作弊**：不针对评分表写死状态机；约束图只做 prompt/验证；所有阈值在留出任务上校准。

## K. PoseGraph

### K.1 节点与边

| 节点 | 来源 | 频率 |
|---|---|---|
| base | 机器人基座（固定） | — |
| torso | `state_torso` / `action_torso` | 30Hz |
| head | `state_d435` / `action_d435` + 标定 | 30Hz |
| object_i | stereo + SAM2/GroundingDINO + 6D pose | 10–30Hz |
| gripper_l/r | FK + `*_ee_pose_gripper_torso/base` | 30Hz |
| target_j | 任务约束图 + 物体检测 | 按需 |
| human_k | RTMW/RTMW3D + depth | 10–30Hz |

| 边 | 来源 | 备注 |
|---|---|---|
| `T_base_torso` | `state_torso` | 腰部/底盘运动后更新 |
| `T_torso_head` | `state_d435` | 头部/颈部运动后更新 |
| `T_head_object` | stereo/SAM2/6D pose | 绝对粗定位 |
| `T_torso_gripper` | FK/EE pose | 双臂 |
| `T_gripper_target` | 腕部相对位姿 | 接触精调 |
| `T_base_human` | RTMW + depth | 安全距离 |

### K.2 一致性检查

```text
T_base_object = T_base_torso * T_torso_head * T_head_object
T_base_target = T_base_torso * T_torso_head * T_head_target
T_gripper_target = inv(T_base_gripper) * T_base_target
```

- 每步重投影物体 3D 点，检查像素误差；> 阈值（如 8–12px）→ 降置信度/重观测。
- 腰部/头部运动后，`T_base_torso`/`T_torso_head` 变化，必须重算 `T_base_object`；不能缓存旧 3D 子目标。
- 运输用 `T_base_object`（绝对）；接触用 `T_gripper_target`（相对）；人手移动物体后，重新估计 `T_base_object` 并更新 phase 目标。
- 透明/反光物体：立体匹配置信度低 → 用单目深度/轮廓/腕部；相对位姿优先。
- 标定：按任务 `camera_params`；`rectified=true` 仍做极线检查；必要时 `stereoRectify` 或自标定。

### K.3 人手与 SSM

- RTMW/RTMW3D 输出 133 关键点（含手/脸/脚）；取双手/前臂/头部。
- 计算人手到机器人 EE/前臂/躯干的最小距离 `d_min`；估计人手速度 `v_h`。
- SSM：`v_robot ≤ (d_min - d_safe) / T_reaction`；低于阈值 → 降速；进入工作区 → 暂停；离开 → 重定位 → 恢复。
- 记录事件：时间、距离、速度、动作、恢复时间；用于审计和红队。

## L. EcoScheduler

### L.1 阶段预算（示例，按实测调整）

| 阶段 | 策略 | 视角 | chunk | 目标延迟 |
|---|---|---|---:|---:|
| Transport | 缓存 chunk / 小策略 / 检索 | 1 head + 1 wrist | 16–32 | 10–20ms |
| Approach | VLA | 2 head + 2 wrist | 8–16 | 30–50ms |
| Contact | VLA + 相对位姿 | 2 wrist + head | 4–8 | 50–80ms |
| Recovery | VLA + PoseGraph | all | 4–8 | 80–120ms |

### L.2 自适应 chunk

- 运输/远离接触：长 chunk（16–32），减少 VLA 调用；用缓存/插值。
- 接近/接触：短 chunk（4–8），提高反应；接触阶段必须短。
- 触发全量 VLA 的条件：phase=contact、夹爪状态变化、物体距离 < 阈值、姿态图一致性低、人手进入、进度停滞。
- 滞回：模式切换加冷却时间，避免抖动；chunk 长度渐变。

### L.3 多机器人

```python
def schedule(requests, batch_size=8):
    # 接触/恢复优先；同阶段按 deadline 排序
    requests.sort(key=lambda r: (r.phase not in ("CONTACT", "RECOVERY"), r.deadline))
    batch = requests[:batch_size]
    return model_server.infer_batch(batch)
```

- 每个端口独立状态（`reset()` 清空）；模型 server 无状态、可批处理。
- 保持 p99 延迟 < 当前 chunk 时长；否则降级到缓存/小策略。
- 记录每端口 VLA calls、延迟、jitter；用于容量规划。

### L.4 指标

- VLA calls/episode、p50/p95/p99 latency、jitter、energy per success、steps/episode。
- 物理能量代理：`Σ(|vx|+|vy|+|ω|+|Δh|+|Δwaist|+|Δa|²)`；与成功率一起看，避免“省电但做不成”。

## M. SERB

### M.1 四类门禁

| 门禁 | 检查项 | 证据/工具 |
|---|---|---|
| Safety | 关节/速度/工作空间/腰部限位；平衡包络；人机分离；急停；watchdog；NaN/超限 | 运行时 monitor + 日志 |
| Evaluation integrity | 不硬编码任务坐标/轨迹；不针对评分表作弊；进度用学习头；披露外部数据/模型/人工干预 | 代码审计 + 模型卡 |
| Reproducibility | seed、config、数据版本、模型版本、审计日志、失败回放 | 提交包 |
| Bio-legal | 数据集/底座/第三方许可证；人脸/人手隐私；非商用权重禁用 | 许可证矩阵 + NOTICE |

### M.2 运行时 monitor

```python
class SERBMonitor:
    def update(self, obs, scene):
        self.check_nan(obs)
        self.check_joint_limits(obs)
        self.check_workspace(scene)
        self.check_balance(obs)
        self.check_human(scene)
        self.check_watchdog()

    def clamp(self, action, obs):
        action = clip_joint_velocity(action)
        action = clip_workspace(action)
        action = scale_for_human(action, self.human_distance)
        return action
```

### M.3 审计日志 schema

```json
{
  "ts": "2026-10-23T12:34:56.789Z",
  "episode": 42,
  "task": "T21",
  "phase": 1,
  "model_version": "wla-1.0-ft-20261020",
  "data_version": "unibot-v1-20260911",
  "action": [0.1, 0.2, 0.3],
  "ee_pose": [0.4, 0.0, 0.2, 0.0, 0.0, 0.0],
  "human_distance_m": 0.85,
  "latency_ms": 38,
  "safety_event": null,
  "progress": 0.62
}
```

### M.4 提交前 checklist

- [ ] 数据集/底座/第三方许可证清单 + NOTICE
- [ ] 模型卡（训练数据、版本、已知失败）
- [ ] 数据卡（来源、许可、隐私处理）
- [ ] 红队报告（人手干扰、物体位移、抓空、滑落、碰撞）
- [ ] 安全案例（限位、SSM、急停、watchdog、恢复）
- [ ] 可复现配置（seed、config、依赖、硬件）
- [ ] 审计回放（至少 3 个任务的成功/失败样例）
- [ ] 规则合规声明（外部数据/模型、任务特定逻辑、base/waist 运动）

## N. 实验设计 B0–B9

| 编号 | 变量 | 假设 | 主要指标 | 成本 |
|---|---|---|---|---|
| B0 | WLA-1.0 微调（多视角+proprio+5 复述） | 强基线 | 成功率/检查点 | 3–5 天 |
| B1 | + 语言约束 prompt / 留一复述 | 语言约束提升长程顺序 | 顺序正确率/完整成功 | +2 天 |
| B2 | + Rubric/Progress + 重试 | 阶段推进减少 premature stop | 检查点分/完整成功 | +3 天 |
| B3 | + PoseGraph 绝对（stereo/object 3D） | 3D 提升位置/背景泛化 | 抓取/放置成功率 | +4 天 |
| B4 | + PoseGraph 相对（腕部接触） | 相对位姿提升硬任务 | T05/T10/T12/T19/T29 | +5 天 |
| B5 | + waist/pivot + Balance Shield | 腰部扩展可达且不摔 | pivot 任务成功率/平衡事件 | +3 天 |
| B6 | + EcoScheduler | 阶段化算力降延迟/抖动 | p99/jitter/VLA calls | +2 天 |
| B7 | + 人手 SSM/恢复 | 干扰后恢复 | human_1/4 成功率 | +3 天 |
| B8 | + 离线 RL/优势加权 | 关键过渡提升 | 硬任务检查点 | +4 天 |
| B9 | + 增广/世界模型 | 外观/位置/视角泛化 | unseen 分桶 | +5 天 |

> 顺序原则：先 B0–B2（低成本、高确定性），再 B3–B5（核心差异化），最后 B6–B9。若规则不允许外部模型/数据，B0 改为“挑战数据从头微调小模型”，其余不变。

### N.1 任务分桶

- **高地板/短任务**：T01/T02/T03/T08/T21/T24/T30/T32。
- **接触密集**：T05/T10/T12/T14/T19/T26/T29。
- **变形/长程**：T16/T17/T18/T28/T31。
- **pivot 活动**：T15（连续 waist）、T23/T16（p4 偏移）、T20/T11/T12（height 偏移）。
- **动态/顺序**：T24（传送带）、T04/T06/T21/T27（颜色/顺序）、T22（拼写）。
- **人为干扰**：所有有 `human_1/human_4` 备注的任务。

### N.2 Local Proxy Leaderboard 评分

- 每个任务 5–10 trials；记录 `first_checkpoint`、`full_success`、`checkpoint_score`、`steps`、`latency`、`recovery`。
- 分桶报告；用 bootstrap 置信区间；不要用单次最好成绩。
- 离线代理：动作 L1/DTW、phase 分类 F1、进度 MAE、物体 3D 误差、相对位姿误差、重投影误差。
- 真机代理：成功率、检查点、干扰恢复率、平衡事件、碰撞/急停次数。

## O. 指标

| 类别 | 指标 | 目标/说明 |
|---|---|---|
| 任务 | full success rate | 主指标；按 32 任务平均 |
| 任务 | checkpoint score | 官方步骤分；按任务归一化 |
| 任务 | first-checkpoint rate | 高地板任务优先 |
| 任务 | full success given first | 衡量长程推进 |
| 恢复 | recovery rate after human/object move | `human_1/4` 分桶 |
| 精度 | object 3D error (mm) | 头部 stereo 粗定位 |
| 精度 | relative pose error (mm/deg) | 腕部接触 |
| 精度 | reprojection error (px) | 姿态图一致性 |
| 效率 | p50/p95/p99 latency (ms) | 按阶段 |
| 效率 | jitter (ms) | 延迟标准差/尾延迟 |
| 效率 | VLA calls/episode | EcoScheduler |
| 效率 | energy per success (proxy) | 计算+物理动作 |
| 安全 | safety violations / e-stops | 目标 0 |
| 可信 | audit completeness | 提交 checklist 100% |

## P. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 规则不可读（Feishu） | 可能做错方向/违规 | 先发邮件 `challenge_support@unitree.com`；做“规则无关”的 P0（PoseGraph/SERB/进度）；保留静态 pivot 回退 |
| pivot 提交语义未官方确认 | 腰部动作错误/摔倒 | 不计分单任务探针；默认静态；限幅/限速/平衡 shield |
| 标定 10 组差异 | 3D 漂移 | 按任务读 `camera_params`；极线/重投影检查；腕部相对位姿 |
| 透明/反光物体深度空洞 | 抓取/插入失败 | 多视角、单目深度兜底、轮廓/关键点、腕部近景 |
| 人手检测误报 | 停顿/超时 | 高置信才停；滞回；超时恢复；只用机载相机 |
| 延迟/抖动 | 完成率下降 | 阶段化 chunk；p99 守门；缓存/小策略；多机器人批处理 |
| 许可证不清晰 | 取消资格 | 默认 WLA-1.0 Apache-2.0；VLA-0 先书面确认；NOTICE |
| 过拟合评分表 | 泛化差/违规 | 学习进度头为主；约束图只做 prompt；留出任务验证 |
| 算力不足 | 训不动 6B | LoRA/单卡 24GB；先小模型验证竞赛层；WLA-1.0 微调 |
| 时间不够 | 做不完 | 4 周只做 B0–B2+B5；6 周加 B3/B4/B7；8 周再加 B6/B8/B9 |

## Q. 来源（检索日期 2026-10-23）

**挑战赛/提交**

- https://unibot.unitree.com/challenges.html
- https://unibot.unitree.com/leaderboard.html
- https://unibot.unitree.com/runs.html
- https://unibot.unitree.com/profile.html
- https://github.com/unitreerobotics/unibot_submission
- https://raw.githubusercontent.com/unitreerobotics/unibot_submission/main/README.md
- https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- 飞书参赛手册（正文不可读）：https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh
- 支持邮箱：challenge_support@unitree.com

**数据集**

- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_OrganizeTools
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- https://huggingface.co/datasets/unitreerobotics/G1_Dex1_PlugCharger
- `meta/info.json`、`meta/stats.json`、`meta/tasks.parquet`、`data/chunk-000/file-000.parquet`

**底座/模型**

- https://github.com/unitreerobotics/unifolm-wla
- https://unigen-x.github.io/unifolm-wla.github.io/
- https://huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base
- https://github.com/unitreerobotics/unifolm-vla
- https://unigen-x.github.io/unifolm-vla.github.io/
- https://huggingface.co/unitreerobotics/UnifoLM-VLA-Base
- https://gigabrain0.github.io/
- https://huggingface.co/open-gigaai/GigaBrain-0.7-3.5B-Base

**论文/技术**

- GigaBrain-0: https://gigabrain0.github.io/
- Adaptive Action Chunking: arXiv 2604.04161v2
- EcoVLA: arXiv 2608.15502v1
- ActTune: arXiv 2610.08444
- Realtime-VLA FLASH: arXiv 2605.13778
- VLA-Cache: NeurIPS 2025
- PICES: arXiv 2610.19656
- VLA-ULAP: arXiv 2609.18663
- MAPRPose: arXiv 2604.20650
- BOP 6D pose leaderboard: https://bop.felk.cvut.cz/leaderboards/
- RTMW: arXiv 2407.08634
- EmbodiedGovBench: arXiv 2604.11174
- SafeStage: arXiv 2609.21223
- ManiGuard: arXiv 2608.17386
- SSM survey: Robotics 2025, 14, 41
- ISO 10218-2:2025; ISO/TS 15066

## R. 开放问题

1. Feishu 规则的评分权重、trial 数、外部数据/模型、任务特定逻辑、base/waist 限制、单任务时限、N 分别是什么？
2. 提交端 `pivot[3:6]` 是否就是 waist yaw/pitch/roll？符号/限位/死区如何？
3. 评测语言是否使用同样 5 条复述？是否留出未见复述/中文？
4. 评测相机是否与数据集同一标定？10 组差异如何处理？
5. 公开榜何时开放？榜单按平均成功率、步骤分还是归一化综合？
6. 人为干扰是脚本化还是自适应？是否允许机器人主动暂停/等待？
7. WLA-1.0/GigaBrain-0 等外部预训练模型是否被允许？许可证如何申报？
8. 不计分单任务调试每任务几次？能否用于 pivot/相机/延迟探针？
<!-- ARTIFACT:END -->
