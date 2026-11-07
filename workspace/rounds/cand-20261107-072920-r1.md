# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 25 轮（新灵感循环第 1 轮）· SEM-PLAY：把「语义地图 × 机器人竞赛 × 评测指标」拧成一股绳，直面 UniBot 五类场景泛化

## 0. 课题切换声明与信息核实（先严谨，再发散）

先交代循环状态：上一循环（至第 24 轮）的课题是移动操作体的力接触导航（FORCE-NAV 线）。本轮按用户主题「寻找参加 UniBot 的创新点」**切换课题、开启新循环**。上一循环沉淀的三条方法论随身携带，作为可迁移资产：

1. **评测先行**：先有可复现基准、再有系统（第 23 轮 FORCE-NAV-BENCH 的纪律）；
2. **显式结构优于隐式堆料**：模块化技能库对端到端单体的论证（第 24 轮 MOD-STACK）；
3. **OOD 思维**：把「分布外」显式建模并纳入度量（第 24 轮 OOD-GUARD）——而本轮的五类泛化场景，恰恰就是一场大规模 OOD 考试。

本轮检索核实（检索日期均为 2026-11-07）：

- **赛事确认**：UniBot = 宇树科技「物理 AI UniBot 世界挑战赛」（unibot.unitree.com），2026-07-10 启动 [来源 2/6/7]。以 Unitree G1 人形机器人为统一平台，任务集为 DAPTO 2 挑战套，32 项真实世界桌面操作任务（抓取/放置/双手协调），32000 条演示样本、169 小时真机数据，五类泛化场景（位置变化、干扰物存在、桌面背景差异、未见物品、人为干扰），按**平均成功率 + 平均步骤分**综合排序 [来源 1/2]。
- **数据集**：HuggingFace collection「UniBot-V1 Challenge Dataset」下 32 个数据集与 32 任务逐一对应，每任务约 1k episodes（合计约 32k / 194k+ 帧），LeRobot v3.0 格式，4 路 RGB 相机（头部双目左右 + 左右手腕，640×480@30fps AV1），Dex1 夹爪（5.5→0.0 开→闭），本体状态丰富（ee pose 含 base/torso 两坐标系、lower_body 15 维、waist 3 维等），Apache-2.0 [来源 3/4]。
- **提交接口（白盒）**：github.com/unitreerobotics/unibot_submission 规定：单 policy 类（metadata / get_action(obs) / reset()）；control_space 取 "joint" 或 "ee" 且互斥；obs_delta_indices 同时决定「发送哪些观测」与「历史帧堆叠方式」；image_resize 可降分辨率；action_chunk_size ≥ 1，每步返回动作块；评测时平台连接 N 台真机（随机顺序），参赛方必须暴露 8765 起 N 个连续端口、每端口独立完成交互（可独立进程或共享后端自行调度，需自行处理并发与状态隔离）；**每步响应延迟与其波动、返回动作的统计规律都会被记录，可能计入「结果可信度」** [来源 5]。
- **重要核查（诚实记录）**：官方排行榜页与运行记录页在本轮检索时均显示「即将发布 Coming Soon」[来源 1b/1c]。用户口径「榜首成功率也不到 30%」本轮**无法从公开渠道独立核实**。本轮按「头部方案成功率 <30%」作为工作假设处理，并把「榜单上线后第一时间的对手分析」列为最高优先行动项。这恰好强化了 IP-3：榜单黑箱期，本地评测与榜上校准是生命线。
- 官方参赛手册为飞书文档（JS 渲染），本轮抓取失败，已列入行动项 [来源 1a]。

**结论：用户所指的 UniBot 就是宇树这一赛事，无歧义，按此展开。**

## 1. 先给直觉：三个灵感词拼出的那张图

拿到「语义地图、机器人竞赛、评测指标」三个词，第一反应是它们分别回答三个不同层面的问题，拼起来恰好是一张完整的参赛作战图：

> **机器人竞赛**回答「博弈结构是什么」：这不是一篇论文的 open review，而是一个目标函数公开、资源稀缺（提交次数、测试时段预约、GPU）、信息逐步释放（榜单即将上线、对手未知）的博弈。竞赛工程学告诉我们：分差往往不在「模型好不好」，而在「同样的模型有没有把可拿的分拿满」。
> **评测指标**回答「目标函数长什么样」：官方挑战赛页明确写着每任务「得分点（满分 100）Scoring Steps (100 pts)」[来源 1a]——即任务内部是**多阶段部分计分**，而非二值成功/失败；再叠加跨任务的「平均步骤分」。所以官方目标函数 ≈ **E[各得分点之和] × 完成效率**，不是成功率。多数队伍的训练目标（二值 BC 损失）与这个目标函数之间存在系统性错位——这个认知差本身就是分。
> **语义地图**回答「扰动打在哪里、用什么表征接住」：把五类泛化场景逐个解剖——位置变化（物体节点坐标变）、干扰物存在（场景图多出无关节点）、桌面背景差异（纯低层纹理变）、未见物品（场景图出现新节点）、人为干扰（场景图在运行时被改写）——**除背景外全部是「物体-空间-关系层」的扰动**。端到端 VLA 用几十层卷积+注意力隐式地学这些结构，样本效率天然低；而一个显式的、持续更新的工作区语义地图，把这五类扰动统一吸收在符号层，让策略面对的是「结构稳定」的输入。

核心类比（本轮灵魂）：**UniBot 考的不是「背题」（见过的任务），而是「考场上课桌换了、笔被人挪了、卷子换了新题型」——语义地图就是把考场结构记在脑子里的那张草稿纸；评测指标是阅卷标准（按步骤给分）；机器人竞赛是「懂得阅卷标准的考生如何分配复习时间」。**

一句话押注：

> **本轮建立 UniBot 参赛创新点清单 v1（8 项），主押两项：SEM-MAP——以「头部双目自建深度 + 开放词汇检测跟踪 + 持续更新的物体级语义工作区地图」作为 VLA 的可声明前置结构，用一张持续更新的场景图同时吸收五类泛化扰动（尤其是人为干扰的运行时变化检测→重规划）；SCORE-ALIGN——把官方「每任务 100 分得分点」结构反向工程成本地过程奖励，对齐训练目标与「E[得分点]×效率」的真实目标函数，并复刻本地评测器解决榜单黑箱期的校准问题。**

三个可验证创新点（概要，完整清单见产物区）：

1. **SEM-MAP：物体级语义工作区地图作为「外挂工作记忆」**。接口观测只有 4 路 RGB + 本体、无深度通道 → 用头部双目（数据集证明是校正过的 stereo）在策略侧自建深度；开放词汇检测（YOLO-World/Grounded-SAM2 类）+ 时序跟踪 + VLM 属性接地 → 维护物体级场景图（id、类别、3D 位置、抓取候选、状态）；地图 token 化后注入 VLA（前缀 token / cross-attention）。五类扰动的吸收机制：位置变化=坐标更新、干扰物=图上无关节点被指令接地过滤、背景=物体中心表征天然免疫、未见物品=开放词汇+形状先验+抓取候选合成、人为干扰=变化检测触发即时重规划（不等 chunk 耗尽）。
2. **SCORE-ALIGN：得分点过程奖励对齐 + 本地评测器**。从官方演示数据自动回归每任务的「得分点骨架」（对演示按相位聚类，找出与 100 分结构对应的关键状态），训练时把二值成功损失替换/加权为「得分点进度」过程奖励（chunk 级优势加权）；同时复刻本地评分器（example_env.py 已给校验 stub），用 5 类扰动注入器生成本地探针集，每次真实提交后校准本地-榜上相关性。
3. **SUBMISSION-OPS：竞赛工程分**。N 端口共享后端 + 每端口独立 episode 状态；延迟预算表（感知异步化、动作块预取、确定性解码降抖动）；动作 sanitize（clip/NaN 防护，越界即 ACTION REJECTED 的零容忍）；冒烟测试 CI。官方明确「延迟平稳性与动作统计规律可能计入可信度」——这是白送的工程分，也是纯研究团队最容易丢的分。

三个词怎么落地：

| 词 | 落地 | 不做什么 |
|---|---|---|
| **语义地图** | SEM-MAP 场景图服务 + 双目自建深度 + 变化检测重规划 + 地图 token 接口 | 不做像素级 3D 重建全家桶（SLAM 级建图）；不做无置信度门控的感知直通；不为地图而地图（每个字段必须有下游消费者） |
| **机器人竞赛** | SUBMISSION-OPS 工程分 + 提交梯子 + 对手分析流程 + 规则澄清行动项 | 不做超时长一次性豪赌提交；不做未过冒烟测试的提交；不做违反「单模型」精神的规则擦边（待手册澄清前不部署外挂脚本路由） |
| **评测指标** | SCORE-ALIGN 得分点过程奖励 + 本地评测器 + 榜上校准 + 步骤分效率工程 | 不做只看二值成功率的训练；不做与官方指标无关的内部指标军备竞赛；不在本地指标未校准前批量调参 |

## 2. 研究日志：头部 <30% 的分差从哪来（推断，待榜单核实）

榜单未公开，无法做真正的对手分析。但可以基于赛事结构与 VLA 领域公开常识，把「为什么通才模型在 32 个桌面任务上平均成功率低」做四层分解（每层标注证据强度）：

| 层 | 失败机制假设 | 证据强度 | 对应创新点 |
|---|---|---|---|
| 数据层 | 每任务仅 ~1k 演示，对 32 任务通才模型而言总量偏小；且演示是「成功轨迹」，无失败恢复数据 → 模型不会「错了再来」 | 高（32000 episodes/169h 为官方口径 [来源 1]） | IP-7 干扰增强、SCORE-ALIGN 部分分利用 |
| 表征层 | 4 路 RGB 无深度、腕部相机剧烈视角变化、场景结构扰动全靠隐式学习 → 位置/干扰物/未见物场景下定位与抓取位姿估计漂移 | 高（接口规范明示无深度通道 [来源 5]） | **SEM-MAP**、IP-6 未见物品 |
| 目标函数层 | 训练用二值成功损失，评测按「得分点部分分 × 步骤效率」计分 → 训练-评测错位；失败 episode 的中间分被浪费；步骤分惩罚犹豫与冗余动作 | 中（得分点结构为官方页面明示 [来源 1a]；「多数队错位」为推断） | **SCORE-ALIGN**、IP-8 步骤分工程 |
| 工程层 | N 端口并发、延迟抖动、动作越界 REJECTED、状态泄漏 → 直接丢分或可信度扣分 | 高（提交规范白盒 [来源 5]） | **SUBMISSION-OPS** |

关键判断：**四层里「表征层」是唯一能同时改善五类泛化场景的结构性抓手，其余三层是「拿满已有水平应得的分」**。新循环第 1 轮，先把结构性抓手立起来，同时把「白送的分」捡干净。

## 3. 灵感词贯通（从词到机制）

> **语义地图**：SEM-MAP 把「考场」显式化——双目深度补接口之缺，物体级场景图补 VLA 工作记忆之缺，变化检测补「人为干扰」场景之缺。地图的每个字段都有明确消费者：位置→抓取位姿、类别→指令接地、抓取候选→参数头、变化时间戳→重规划触发。
> **机器人竞赛**：SUBMISSION-OPS + 提交梯子 + 榜单上线后的对手分析流程；「单模型」约束下的合规边界先澄清再设计（IP-5 双解码头是合规前提下的「内路由」方案）。
> **评测指标**：SCORE-ALIGN 把「按步骤给分」翻译成训练信号；本地评测器 + 5 类扰动注入器 + 榜上校准，让每一次珍贵的提交都携带最大信息量（A/B 单变量）。

## 4. 与上一循环的资产迁移表（不推倒重来，是搬运）

| 上一循环资产 | 本轮去向 |
|---|---|
| 评测先行纪律（FORCE-NAV-BENCH） | 变身为本地评测器 + 榜上校准（IP-3/SCORE-ALIGN） |
| OOD 三信号思维（OOD-GUARD） | 迁移为「五类泛化场景 = 五种已知 OOD 类型」的分类框架，SEM-MAP 按类型逐个设防 |
| 模块化接口思维（MOD-STACK 标准接口） | 迁移为「感知前置模块 + VLA 主干」的 token 接口设计（SEM-MAP） |
| 过程性监控条件 κ_z（第 24 轮原语监控） | 迁移为得分点骨架的「关键状态检测器」思想（SCORE-ALIGN） |
| 数据飞轮（失败→演示→入库） | 迁移为「本地探针失败→定向补数据/补增强」（IP-7 与 SCORE-ALIGN 联动） |

## 5. 风险与本轮最大风险

本轮最大的风险：**「语义地图前置」与「端到端 Scaling」可能是两条此消彼长的路线——如果头部队伍靠更大规模 VLA + 更多自采演示数据把成功率推上去，SEM-MAP 的感知模块反而可能成为延迟与误差的来源；且官方对「策略内部结构」的合规边界（是否允许策略内含控制逻辑、外部感知服务）尚待参赛手册澄清，SEM-MAP 的部分设计可能需要回炉。**

缓解：SCORE-ALIGN 与 SUBMISSION-OPS 是路线无关的（无论最终走哪条技术路线都成立），先把这两项做厚；SEM-MAP 以「可消融的附加 token 源」形式接入（开/关对比），而不是把系统绑死在地图上；参赛手册澄清列为本周行动项。

## 6. 下一轮展望（第 2 轮灵感未知）

- 若灵感指向「世界模型/想象」→ 在 SEM-MAP 上加轻量前向预测（物体级动力学想象），做 chunk 间的重规划预演，并回应「人为干扰」场景的预测性避让；
- 若灵感指向「数据/增强」→ 深化 IP-7：官方演示的物体轨迹重定时/重定位合成、失败注入、回放式人为干扰；
- 若灵感指向「多智能体/协同」→ N 端口并行评测的「集成策略」：多解码器投票/多 checkpoint 集成（仍单模型口径，需合规确认）；
- 若榜单上线 → 本轮最大行动项兑现：头部方案逐任务拆解（哪些任务谁强、五类场景谁掉分），清单全面修订。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 25 轮产物 · UniBot 参赛创新点清单 v1 + 三大重点方案（SEM-MAP / SCORE-ALIGN / SUBMISSION-OPS）

## 0. 结论

本轮建立**可持续迭代的参赛创新点清单 v1（8 项）**，并重点展开三项：

- **SEM-MAP（P0）**：策略侧自建深度（头部双目）+ 开放词汇检测跟踪 + 持续更新的物体级语义工作区地图，token 化注入 VLA；一张场景图同时吸收五类泛化扰动，尤其是「人为干扰」的运行时变化检测→即时重规划。
- **SCORE-ALIGN（P0）**：反向工程官方「每任务 100 分得分点」结构为本地过程奖励，训练目标从二值成功率对齐到「E[得分点]×步骤效率」；配套本地评测器 + 5 类扰动注入器 + 榜上校准，破解榜单黑箱期。
- **SUBMISSION-OPS（P1）**：N 端口部署拓扑、延迟预算、动作 sanitize、提交梯子——把官方明示计入「结果可信度」的工程分捡干净。

路线无关原则：SCORE-ALIGN 与 SUBMISSION-OPS 不依赖「语义地图路线」成立，无论最终架构如何都应执行；SEM-MAP 以可消融的附加 token 源形式接入，不绑死系统。

## 1. 赛事事实卡（全部信息检索于 2026-11-07）

| # | 事实 | 来源 |
|---|---|---|
| F1 | 赛事：物理 AI UniBot 世界挑战赛，2026-07-10 启动，Unitree G1 平台，任务集 DAPTO 2，32 项桌面任务（抓取/放置/双手协调），32000 演示 / 169h 真机数据，五类泛化场景（位置变化/干扰物/背景/未见物品/人为干扰），按平均成功率 + 平均步骤分综合排序 | unibot.unitree.com（首页/挑战赛页）；新浪财经/凤凰科技 2026-07-10 报道 |
| F2 | 每任务「得分点（满分 100）Scoring Steps (100 pts)」——任务内多阶段部分计分 | unibot.unitree.com/challenges.html |
| F3 | 数据集：HF collection「UniBot-V1 Challenge Dataset」32 个数据集逐一对应 32 任务，每任务约 1k episodes；LeRobot v3.0，4 路 RGB（head_stereo_left/right 校正双目 + 双腕）640×480@30fps AV1；Dex1 夹爪 5.5→0.0；状态含 ee pose（base/torso）、lower_body 15 维、waist 3 维；动作含 ee pose、torso、d435、base_command、pivot；Apache-2.0 | huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset；unitreerobotics/G1_Dex1_HangCup 数据卡 |
| F4 | 32 任务名单（据数据集名）：HangCup, ArrangePlates, ArrangeTestTubes, ZipUp, ColorArrangement, Unlock, DisconnectEthernet, ConveyorSorting, FruitCollection, FoldTowel, OrganizeBookshelf, FruitSorting, SpellRobot, OrganizePencilCase, OrganizeStationery, StackBowls, StoreCups, OrganizeTools, PackDoll, PackBag, PackPhone, StoreEarphones, StorePaddle, PaperCupStacking, PickOutBatteries, ToolboxStorage, PlugCharger, SyringeWaterTransfer, PlugInEthernet, PlacePhotoFrame, RemovePinnedNote, PourOutMedicine | HF collection 逐项 [来源 3] |
| F5 | 提交接口：单 policy 类（metadata/get_action/reset）；control_space ∈ {joint, ee} 互斥；obs_delta_indices 决定观测子集 + 历史堆叠（负偏移）；image_resize；action_chunk_size ≥1；token 双重校验；N 台测试机器人 → 8765 起 N 个连续端口、每端口独立交互、并发与状态隔离自行负责；每步延迟与波动、动作统计规律被记录并可能计入「结果可信度」 | github.com/unitreerobotics/unibot_submission README |
| F6 | 观测目录无深度/点云通道（仅 4 路 RGB + 本体 + 语言指令）；action 支持 joint 或 ee 位姿 | 同 F5 |
| F7 | **官方排行榜与运行记录页为「即将发布」；用户口径「榜首成功率 <30%」无法独立核实，按工作假设处理** | unibot.unitree.com/leaderboard.html、/runs.html |
| F8 | 参赛手册为飞书文档，本轮抓取失败（JS 渲染 + WAF）；规则细节（单模型边界、提交频次、步骤分公式）待人工查阅 | challenges.html 上的飞书链接 |

行动项（本周）：A1 人工查阅两份飞书参赛手册，补齐 F8；A2 注册账号流程走通；A3 榜单上线监控 + 首日对手分析。

## 2. 创新点清单 v1（持续迭代；每项含动机/差异/可行性/资源/步骤/风险）

优先级：P0 = 本周启动，P1 = 两周内，P2 = 视榜单与消融结果。状态：NEW（本轮新建）。

### IP-1 · SEM-MAP：物体级语义工作区地图（P0，NEW）
- **动机**：五类泛化场景中四类是物体-空间-关系层扰动（F1）；端到端 VLA 隐式学习这些结构样本效率低；接口无深度通道（F6）是几何瓶颈；「人为干扰」要求运行时场景更新能力，而帧堆叠只覆盖极短历史（F5）。
- **与现有方案差异**：主流参赛路线预计是「官方 32k 演示 + 通用 VLA 底座微调」，感知与记忆全部隐式；本项把场景结构显式化为持续更新的物体级场景图，并作为**可声明、可消融**的前置 token 源。
- **技术可行性**：高——全部组件有开源实现（立体匹配 RAFT-Stereo 类、YOLO-World/Grounded-SAM2、TAP/CoTracker 类跟踪、AnyGrasp 类抓取候选、VLM 属性接地）；头部双目在数据集里明确是校正过的 stereo pair（F3），策略侧自建深度合规（obs 发给策略后内部处理不受限）。
- **所需资源**：数据——官方 32k 演示（自动伪标注物体轨迹）+ 本地少量补采（可选）；算力——感知栈 1×4090 级，VLA 底座另计；接口——obs_delta_indices 声明 head_stereo 双路 + 双腕 + 本体，地图状态按端口隔离（reset() 清空）。
- **落地步骤**：①官方数据伪标注流水线（检测+跟踪+双目深度→3D 物体轨迹）→ ②地图服务与变化检测状态机 → ③地图 token 化接口设计 → ④VLA 底座接入（前缀 token）微调 → ⑤五类扰动本地探针消融（开/关地图）。
- **风险**：感知误差传导（缓解：置信度门控 + 地图与原始观测双通道并存）；延迟预算（缓解：感知异步化，见 SUBMISSION-OPS）；与 VLA 特征冗余导致增益为零（缓解：严格消融，若无增益则降级为「人为干扰场景专用」模块）。

### IP-2 · SCORE-ALIGN：得分点过程奖励对齐（P0，NEW）
- **动机**：官方按「每任务 100 分得分点」计分（F2），训练却普遍用二值成功损失——失败 episode 的中间分被浪费，且「冒险策略 vs 保守策略」的最优解在部分计分下完全不同（保守策略在难任务上期望分更高）。
- **与现有方案差异**：把评测指标结构翻译为训练信号；失败数据从「负样本」升级为「带过程标注的部分分样本」。
- **技术可行性**：中高——得分点骨架可从演示自动回归（演示相位聚类 + 与得分点结构的对齐由 VLM 辅助核对）；过程奖励加权是成熟技术。不确定性：官方得分点具体定义未知（F8），先按「可从观测/状态推断的关键状态」假设设计，手册查阅后修订。
- **所需资源**：数据——官方 32k 演示（重标注相位/关键状态）；算力——标注流水线 CPU/GPU 轻量；接口——无特殊要求。
- **落地步骤**：①得分点骨架自动发现（演示聚类）→ ②本地评分器（复刻 100 分结构）→ ③过程奖励加权训练（chunk 级优势 = 得分点进度增量）→ ④本地-官方相关性验证（每次提交后回归）。
- **风险**：本地得分点模型与官方评分器不一致（缓解：只用于相对排序与加权，不追求绝对值；每次真实提交校准相关性）。

### IP-3 · LOCAL-EVAL：本地评测器 + 榜上校准（P0，NEW）
- **动机**：提交与测试时段是稀缺资源（F5：预约制 + N 台真机随机顺序）；榜单黑箱期（F7）无外部参照 → 迭代速度 = 竞赛生命线。
- **差异**：多数队伍「训完就提交」；本项把每次提交当作校准本地代理指标的数据点，建立「本地分 → 榜上分」的回归模型。
- **可行性**：高——官方 example_env.py 提供校验 stub；5 类扰动注入器为纯工程（随机摆放/干扰物生成/背景替换/物品替换/干扰回放）。
- **资源**：无真机依赖的本地复现（视觉回放 + 动作校验 + 得分点评分）；1 台 GPU 跑批量探针。
- **步骤**：①扰动注入器 → ②本地评分器（与 IP-2 共用）→ ③提交 A/B 梯子（单变量原则）→ ④相关性看板（按任务×场景维度）。
- **风险**：本地仿真与真机偏差（缓解：以「相对排序」为准；首个真实提交后立即校准）。

### IP-4 · SUBMISSION-OPS：竞赛工程与可信度分（P1，NEW）
- **动机**：官方明示每步延迟及其波动、动作统计规律计入可信度（F5）；N 端口并发 + 状态隔离是硬要求；动作越界直接 ACTION REJECTED。
- **差异**：纯研究团队常忽视的「工程分」；对同样的模型，这是免费分层。
- **可行性**：高，纯工程。
- **资源**：部署机 1-2 台 + N 端口服务框架；CI 冒烟测试。
- **步骤**：①端口路由 + 共享推理后端 + 每端口独立 episode 状态 → ②延迟预算表与异步感知 → ③动作 sanitize（clip/NaN/shape）→ ④冒烟 CI（run_client 全流程）→ ⑤确定性解码降抖动。
- **风险**：共享后端延迟互踩（缓解：请求队列 + 超时降级）；漏掉某个端口的 reset 状态泄漏（缓解：端口隔离测试用例）。

### IP-5 · DUAL-HEAD：单模型双解码头（参数头 + 自由头内路由）（P2，NEW，合规待确认）
- **动机**：抓取/放置类任务用「物体 6D 位姿→结构化抓取参数→ee 空间跟踪控制器」可拿高成功率与高步骤分；长尾/双手任务用自由 VLA 头兜底。两者统一在**一个模型内**（两个动作头 + 学习型门控），满足通才赛道「单模型」精神。
- **差异**：对比纯 VLA（上限低）与「模型+外挂脚本」（可能违反单模型规则，F8 未澄清前不部署）。
- **可行性**：中——参数头的监督可从官方演示自动提取（抓取时刻 ee 位姿 + 物体位姿配对）；门控用地图置信度 + 任务指令嵌入。
- **资源**：训练算力同 VLA 底座；无需额外数据。
- **步骤**：①演示中自动提取「参数化可解」子集 → ②参数头训练 → ③门控联合微调 → ④合规确认 → ⑤消融。
- **风险**：规则对策略内控制逻辑的界定不明（行动项 A1 优先澄清）；门控错误选择（缓解：门控置信度阈值 + 失败回退到自由头）。

### IP-6 · UNSEEN-GRASP：未见物品开放词汇管线（P1，NEW，可并入 IP-1 特化模块）
- **动机**：「未见物品」是五类场景之一（F1）；封闭类别检测器直接失效。
- **差异**：开放词汇检测 + VLM 属性接地 + 形状条件抓取候选（AnyGrasp 类）+ 「先看后抓」注视策略（腕部相机近景确认后再闭合）。
- **可行性**：高（组件开源）；风险在细长/透明/反光物品的检测与深度质量。
- **资源**：与 IP-1 共享感知栈；少量本地物品集测试。
- **步骤**：①开放词汇检测接入 → ②抓取候选合成 → ③腕部近景再确认策略 → ④本地未见物品探针集。
- **风险**：透明/反光物体双目深度失效（缓解：近景 + 多帧融合 + 抓候选保守化）。

### IP-7 · DISTURB-AUG：人为干扰回放与扰动合成（P1，NEW，数据侧）
- **动机**：「人为干扰」场景需要「chunk 执行中途被改变世界」的恢复能力；官方数据是干净成功轨迹，此能力最缺。
- **差异**：把官方演示做「时间重定时 + 物体轨迹扰动 + 干扰物插入」合成受扰训练数据；配合缩短 chunk / 自适应重规划频率；与 IP-1 变化检测联动（检测到变化即提前终止当前 chunk 重观测）。
- **可行性**：中高——视频级物体框内贴换（video inpainting/paste）有开源工具；真值一致性需人工抽检。
- **资源**：数据合成流水线 CPU/GPU 轻量；标注抽检人力。
- **步骤**：①扰动算子库（移动物体/插入干扰物/遮挡手臂）→ ②合成 + 过滤 → ③混合训练 → ④本地探针验证。
- **风险**：合成分布与真实干扰偏差（缓解：以真机/视频观察归纳干扰类型清单，覆盖性优先）。

### IP-8 · STEP-EFF：步骤分效率工程（P1，NEW）
- **动机**：排名按「平均成功率 + 平均步骤分」（F1）；步骤分大概率与完成效率相关（步数/时长）。
- **差异**：动作块自适应（自由空间大步长、接近目标小步长）；减少犹豫动作（重复抓放抖动）；确定性解码；首帧预热（模型加载/缓存）降低首步延迟。
- **可行性**：高；与 IP-4 共享工程面。
- **资源**：无额外。
- **步骤**：①步骤分机制确认（A1 手册）→ ②自适应 chunk 策略 → ③解码确定性 → ④本地效率探针。
- **风险**：步骤分定义未知前盲目优化（先确认再动）。

### 清单一览表

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 主要灵感词 | 状态 |
|---|---|---|---|---|---|---|
| IP-1 | SEM-MAP | 物体级语义地图 = VLA 的外挂工作记忆 | P0 | 无 | 语义地图 | NEW |
| IP-2 | SCORE-ALIGN | 得分点结构 → 过程奖励 | P0 | 无 | 评测指标 | NEW |
| IP-3 | LOCAL-EVAL | 本地评测器 + 榜上校准 | P0 | IP-2 | 评测指标×竞赛 | NEW |
| IP-4 | SUBMISSION-OPS | N 端口/延迟/校验工程分 | P1 | 无 | 机器人竞赛 | NEW |
| IP-5 | DUAL-HEAD | 单模型内参数头+自由头 | P2 | IP-1 | 语义地图×竞赛 | NEW（合规待确认） |
| IP-6 | UNSEEN-GRASP | 开放词汇+抓取候选 | P1 | IP-1 | 语义地图 | NEW |
| IP-7 | DISTURB-AUG | 人为干扰回放合成 | P1 | 无 | 评测指标（场景维度） | NEW |
| IP-8 | STEP-EFF | 步骤分效率工程 | P1 | A1 手册 | 评测指标 | NEW |

## 3. 重点展开一：SEM-MAP 技术方案

### 3.1 架构

```
[评测平台 N 端口] --obs--> [每端口 PolicyService 实例]
                                │
        ┌───────────────────────┼─────────────────────────┐
        ▼                       ▼                         ▼
  [双目深度模块]          [检测+跟踪模块]            [本体状态]
  head_stereo L/R         开放词汇检测器              ee pose 等
  → 视差 → 深度           + 跨帧跟踪                 (直接用)
        │                       │
        └───────────┬───────────┘
                    ▼
        [SEM-MAP 物体级场景图]（每端口独立，reset() 清空）
        slot = {id, 类别/属性, 3D 位置(基座系), 尺寸, 抓取候选,
                置信度, 最后更新时刻, 变化标志}
                    │
                    ▼ token 化（每个 slot → K 个 token：类别+位姿+属性+状态）
                    ▼
        [VLA 底座] ← 原始 4 路 RGB + 本体 + 语言指令 + 地图 token 前缀
                    │
                    ▼
        [动作头] → get_action 返回 chunk（joint 或 ee 空间）
```

### 3.2 关键设计决策

1. **深度自建**：接口无深度通道（F6），但 head_stereo_left/right 是数据集明示的「校正」双目（F3）→ 策略侧跑轻量立体匹配（RAFT-Stereo 类或 SGBM 起步）得深度图；深度只服务于地图 3D 定位，不进入 VLA 输入（保持 VLA 输入与预训练分布一致）。
2. **地图更新状态机**：`INIT → TRACKING → (变化检测: 位置突变/消失/新增) → REMAP → TRACKING`；变化检测用 slot 级马氏距离阈值 + 跟踪器级联（检测器每 T_detect 帧全图重扫一次兜底）。变化标志置位 → 当前 chunk 提前终止 → 重新观测 → 重规划（这是「人为干扰」场景的核心机制）。
3. **Token 接口**：每物体 slot → 3~4 个 token（类别嵌入、3D 位置 FFT 编码、属性/状态、置信度），最多 M=10 物体 → ≤40 token 前缀；VLA 底座用 cross-attention 或前缀拼接消化。**开/关地图是第一消融**。
4. **置信度门控**：slot 置信度 < τ 的物体 token 置为「低置信」嵌入，避免错误感知劫持策略；地图与原始图像双通道并存，策略可学会「地图只是提示」。
5. **指令接地**：语言指令 → VLM/开放词汇匹配到 slot id（"the red block"→slot#3），接地结果作为额外 token 注入；干扰物过滤发生在接地层（未被指令提及且非目标容器的物体降权）。

### 3.3 伪标注流水线（离线，一次性）

```
输入: 官方 32 任务演示数据（LeRobot parquet + AV1 视频）
1. 每 episode 抽帧（每 5 帧）→ 双目深度（SGBM 快速版）→ 检测（YOLO-World 开放词汇，提示词=任务名+常见物品表）
2. 跨帧跟踪（CoTracker/ByteTrack）→ 3D 中心轨迹（深度反投影 + ee-torso 位姿外参）
3. 抓取时刻自动标注: gripper 开度 5.5→<1.0 的时刻 ± 0.3s 窗口 → 抓取位姿样本（物体 id ↔ ee pose 配对，供 IP-5 参数头）
4. 输出: 物体轨迹伪标注 + 抓取配对 + 每任务物体清单 → 训练检测/跟踪微调 + 地图先验（各任务常见物体布局）
```

### 3.4 Python 骨架（地图服务与变化检测核心）

```python
import numpy as np
from dataclasses import dataclass, field
from enum import Enum

@dataclass
class Slot:
    sid: int
    label: str                      # 类别/开放词汇标签
    pos_xyz: np.ndarray             # 基座系 3D 中心
    size_xyz: np.ndarray
    grasp_candidates: np.ndarray    # [G,7] 位姿候选（ee 系）
    conf: float                     # 跟踪置信度（EMA）
    last_seen: int                  # 帧号
    changed: bool = False           # 变化标志（人为干扰触发）

class MapState(Enum):
    INIT = 0; TRACKING = 1; REMAP = 2

class SemanticWorkspaceMap:
    """每端口独立实例；reset() 清空（合规：状态隔离）。
    更新频率受延迟预算约束：跟踪 10Hz、全图重扫 T_detect=30 帧。"""
    def __init__(self, max_slots=10, move_th=0.04, appear_th=0.5,
                 miss_ttl=45, detect_every=30):
        self.slots: list[Slot] = []
        self.state = MapState.INIT
        self.frame = 0
        self.move_th, self.appear_th = move_th, appear_th   # 4cm 位移阈值
        self.miss_ttl, self.detect_every = miss_ttl, detect_every

    def reset(self):
        self.slots, self.state, self.frame = [], MapState.INIT, 0

    def update(self, dets, depth_xyz):
        """dets: [(bbox, label, det_conf)]；depth_xyz: [H,W,3] 双目反投影点云。
        返回 (changed_any, events)；事件供 chunk 提前终止决策。"""
        self.frame += 1
        events = []
        # 1) 匹配：检测 ↔ slot（3D 距离 + 标签一致性贪心）
        for d in dets:
            c3 = depth_xyz[d.bbox].mean(0)
            j = self._nearest(c3, d.label)
            if j is not None and np.linalg.norm(c3 - self.slots[j].pos_xyz) < 0.15:
                s = self.slots[j]
                moved = np.linalg.norm(c3 - s.pos_xyz) > self.move_th
                s.pos_xyz = 0.7 * s.pos_xyz + 0.3 * c3          # EMA 平滑
                s.conf = min(1.0, s.conf + 0.1)
                s.last_seen, s.changed = self.frame, moved
                if moved:
                    events.append(("moved", s.sid))
            else:
                events += self._spawn(d, c3)                    # 新物体
        # 2) 消失检测（miss_ttl 帧未见 → 标记 changed 并保留 tombstone）
        for s in self.slots:
            if self.frame - s.last_seen > self.miss_ttl:
                if not s.changed:
                    s.changed, s.conf = True, 0.0
                    events.append(("vanished", s.sid))
        # 3) 周期性全图重扫兜底（检测器漂移自愈）
        if self.state is MapState.TRACKING and self.frame % self.detect_every == 0:
            events += self._rescan(dets)
        if self.state is MapState.INIT and len(self.slots) > 0:
            self.state = MapState.TRACKING
        changed_any = any(e[0] in ("moved", "vanished") for e in events)
        return changed_any, events

    def tokenize(self, lang_emb_fn):
        """slot → token 序列（类别+位姿+属性+置信度），低置信 slot 用
        「低置信」嵌入防劫持；接地结果（指令→slot id）额外注入。"""
        toks = []
        for s in sorted(self.slots, key=lambda s: -s.conf)[: self.max_slots]:
            toks.append(dict(kind="obj", label=s.label, xyz=s.pos_xyz,
                             conf=s.conf, changed=s.changed))
        return toks

    def _nearest(self, c3, label):
        best, bd = None, 0.20
        for i, s in enumerate(self.slots):
            if s.label == label:
                d = np.linalg.norm(s.pos_xyz - c3)
                if d < bd: best, bd = i, d
        return best

    def _spawn(self, d, c3):
        if d.det_conf < self.appear_th: return []
        s = Slot(self._next_id(), d.label, c3, np.zeros(3),
                 np.zeros((0, 7)), conf=d.det_conf, last_seen=self.frame,
                 changed=True)
        self.slots.append(s)
        return [("appeared", s.sid)]

    def _rescan(self, dets):
        return []   # 骨架：全图重扫 = 检测器置信度复核 + slot 合并去重

    _next_id = property(lambda self: len(self.slots) + 1)
```

### 3.5 与 get_action 的集成（chunk 提前终止机制）

```
每步 get_action(obs):
    if step_in_chunk == 0:  # chunk 起点：全量感知
        depth = stereo_depth(obs.head_stereo_L, obs.head_stereo_R)
        dets  = open_vocab_detect(obs.head_stereo_L)
        changed, events = sem_map.update(dets, depth)
        map_tokens = sem_map.tokenize()
    else:                    # chunk 中间：轻量跟踪校验（变化检测便宜路径）
        changed = light_track_check(obs.head_stereo_L, sem_map.slots)
    if changed:              # 人为干扰：放弃剩余 chunk，立即重观测重规划
        return short_chunk(hold_still(), T=2)   # 原地微调，等下一 chunk 全量感知
    actions = vla(obs, map_tokens, language)
    return sanitize(actions)
```

## 4. 重点展开二：SCORE-ALIGN 技术方案

### 4.1 得分点骨架自动发现

```
输入: 每任务 ~1k 条成功演示
1. 相位特征: [|gripper|, ee 速度, ee→最近物体距离, 抓握状态(5.5→0)]
2. 变化点分段（滑动窗口似然比，同上一循环 BOCPD 思路迁移）→ 相位序列
3. 跨 episode 相位对齐（DTW）→ 相位词表（如: 靠近/对准/下压/闭合/提起/平移/放置/松开）
4. 与官方「100 分得分点」对齐: 用 VLM 读任务名+示例图，猜测得分点语义
   （例 StackBowls: 拿起碗 20 / 对准 20 / 叠放 40 / 稳定 20）；
   手册查阅（行动项 A1）后替换为官方定义
输出: 得分点骨架 {(phase_i, detector_i, weight_i)}，Σ weight = 100
```

### 4.2 过程奖励加权训练

```
每 episode 得分向量: g_t ∈ [0,1]^P（P 个得分点，detector_i 在 t 时刻的达成度）
chunk 级优势: A_k = Σ_i w_i · (g_{t_k+1,i} − g_{t_k,i})   # 得分点进度增量
损失: L = L_BC(成功演示) + λ1 · L_BC_weighted(失败演示, 权重=已获过程分)
            + λ2 · L_progress(A_k 与模型 chunk 的预测进度回归)
策略含义: 失败演示不再只有「负样本」价值——它携带「拿到 40/100 分」的过程信息；
       保守策略（稳拿低阶得分点）与冒险策略（搏最终成功）的期望分
       由加权自动平衡，与官方计分口径一致。
```

### 4.3 本地评分器与榜上校准（与 IP-3 合流）

```
本地评测器 = 官方校验规则（动作形状/越界/token，源自 example_env.py）
           + 得分点评分（4.1 骨架，作用在本地回放/真机录像上）
           + 5 类扰动注入器:
             G1 位置: 物体初始位置网格采样 ±15cm
             G2 干扰物: 注入 1-3 个无关物体（从其他任务物体库抽取）
             G3 背景: 桌面纹理替换（视频级 inpaint）
             G4 未见物品: 目标物替换为外形相似的未训练物品
             G5 人为干扰: 回放式干扰（t=随机 时刻移动物体 5-10cm）
提交梯子（每次真实提交单变量）: 基线 → +SCORE-ALIGN → +SEM-MAP → +STEP-EFF …
校准: 每次提交后记录 (本地分, 官方分) 对 → 按任务×场景维度的相关系数看板；
     相关性 <0.5 的维度，本地指标降权，只信榜上。
```

## 5. 重点展开三：SUBMISSION-OPS 技术方案

### 5.1 N 端口部署拓扑

```
部署机（1-2 台，GPU 池化）
  :8765 ─┐
  :8766 ─┤ 轻量端点（每端口独立进程，仅做收发+状态隔离）
  :8767 ─┼─→ 共享推理后端（单模型实例 + 请求队列）
   ...   │      ├─ 感知服务（SEM-MAP，异步，结果缓存 ≤100ms 新鲜度）
  :876N ─┘      └─ VLA 推理（batch 融合多端口请求）
状态隔离铁律: (port_id, episode_id) → 独立 {sem_map, 跟踪状态, chunk 缓存}；
             reset() 事件必须清空对应 port 的全部状态（CI 用例覆盖）。
```

### 5.2 延迟预算表（每步 get_action 目标 <300ms，波动 <±30%）

| 环节 | 预算 | 手段 |
|---|---|---|
| obs 接收+反序列化 | 20ms | msgpack 流式解析 |
| 双目深度 | 40ms | SGBM 起步 / RAFT-Stereo 蒸馏版；每 chunk 仅首步执行 |
| 检测+跟踪 | 50ms | 轻量检测器 10Hz + 帧间跟踪 |
| VLA 推理（T_a=8 chunk） | 150ms | chunk 摊薄；fp16/int8；CUDA graph |
| 动作 sanitize+回传 | 10ms | 预分配缓冲 |
| 余量 | 30ms | — |

### 5.3 动作 sanitize（零容忍 REJECTED）

```python
def sanitize(act, meta):
    for k, (lo, hi) in ACTION_LIMITS[meta["control_space"]].items():
        a = np.nan_to_num(act[k], nan=0.0, posinf=hi, neginf=lo)
        act[k] = np.clip(a, lo, hi).astype(np.float32)   # 越界→裁剪而非拒收
    assert act["action.left_arm"].shape[0] == meta["action_chunk_size"]
    act["meta.token"] = TOKEN                            # 每步必带
    return act
```

## 6. 实验设计（本地，先行）

| 实验 | 设置 | 指标 | 预期 |
|---|---|---|---|
| E1 地图消融 | VLA 基线 vs +SEM-MAP，5 类扰动 × 8 任务本地探针 | 平均成功率 / 各场景成功率 | G1/G2/G4/G5 场景 +5~15pt，G3（背景）持平 |
| E2 过程奖励消融 | 二值 BC vs +SCORE-ALIGN（同数据同底座） | 本地得分点分 / 真实成功率 | 得分点分 +10%+，成功率不降 |
| E3 变化检测 | 人为干扰注入时刻 ∈ {chunk 25%, 50%, 75%} | 干扰后恢复成功率 | 提前终止机制 > 固定 chunk ≥50% |
| E4 延迟-成绩 | chunk 大小 {4, 8, 16} × 解码确定性 on/off | 步骤分代理（完成步数）/ 成功率 | T_a=8 + 确定性解码最优平衡 |
| E5 感知误差传导 | 地图 slot 注入位姿噪声 σ ∈ {0,2,5,10cm} | 成功率衰减曲线 | 置信度门控下 σ=5cm 衰减 <3pt |
| E6 提交梯子 | 真实提交 ×3（基线/+MAP/+MAP+ALIGN） | 官方分 vs 本地分 | 建立首个校准点 |

提交纪律：每次提交前过冒烟 CI（run_client 全流程 + sanitize 单测 + 端口隔离测试）；单变量原则；提交后 48h 内完成校准报告。

## 7. 风险登记簿

| 风险 | 等级 | 缓解 |
|---|---|---|
| 规则边界不明（单模型定义、步骤分公式、得分点定义）——影响 IP-5 合法性与 IP-2 精度 | 高 | 行动项 A1 人工查阅飞书手册；澄清前 IP-5 不部署 |
| 「榜首 <30%」口径未核实，对手分析缺位 | 高 | 榜单上线监控；上线首日做逐任务×逐场景拆解，全面修订清单 |
| SEM-MAP 增益为零（VLA 隐式能力足够） | 中 | 严格消融 E1；若整体无增益，降级为「人为干扰场景专用模块」（E3 单独验证） |
| 感知误差传导劣化基线 | 中 | 置信度门控 + 双通道并存 + E5 误差曲线定阈值 |
| 本地-官方指标偏差导致错误调参 | 中 | 相关性看板；相关性 <0.5 维度只信榜上 |
| 共享后端并发延迟抖动触发可信度扣分 | 中 | 请求队列 + 延迟看板 + 压测（N 端口同时打满） |
| 算力不足（VLA 微调 + 感知栈 + 本地评测并行） | 中 | 底座选 3B 级 VLA 起步；感知轻量化；评测错峰 |

## 8. 来源清单（全部检索于 2026-11-07）

1. UniBot 官网首页/挑战赛页：https://unibot.unitree.com （含 F1/F2）；挑战赛页 https://unibot.unitree.com/challenges.html；排行榜页（即将发布）https://unibot.unitree.com/leaderboard.html；运行记录页（即将发布）https://unibot.unitree.com/runs.html
1a. 参赛手册（飞书，本轮抓取失败）：https://scnhkkqlu12w.feishu.cn/docx/Uz7OdFBcDoqP1dxgH62cHW1CnMh （中）与 https://scnhkkqlu12w.feishu.cn/docx/ZNHIdaGx0oPOlBxNVxkcswqqnnh （英）
2. 赛事启动报道（2026-07-10）：新浪财经 https://finance.sina.com.cn/tech/it/2026-07-10/doc-inihinfx8458209.shtml；腾讯新闻 https://news.qq.com/rain/a/20260710A09S2Q00；行业解读 https://zhizaozx.cn/articles/2qv-unitree-unibot-physical-ai-world-challenge.html（DAPTO 2 / 五类场景 / 32000 样本口径）；https://myxmr.com/news/unitree-launches-unibot-world-challenge（两大评测任务口径）
3. 数据集 collection：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset（32 项；每任务约 1k episodes）
4. 数据格式样例：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup（LeRobot v3.0、4 相机、Dex1 夹爪、状态/动作键全表）
5. 提交接口规范：https://github.com/unitreerobotics/unibot_submission（README：接口/观测/动作/token/端口/可信度条款）
6. https://www.jqman.com/ai/490067.html（DAPTO 2 任务集名称佐证）
7. https://post.smzdm.com/p/aom7nmp7/（双维度评分与五类场景佐证）

## 9. 清单迭代规则（后续轮次遵守）

1. 每轮先核对事实卡（F1-F8）有无变化，特别是榜单上线（F7 解除）与手册澄清（F8 解除）——两者触发清单强制修订；
2. 新灵感词优先映射到现有清单项的深化（改动机/差异/步骤），其次才是新增项；连续两轮无证据支持的项降级或删除；
3. 每项始终维护六个字段：动机 / 与现有方案差异 / 技术可行性 / 所需资源（数据/算力/接口）/ 落地步骤 / 风险；
4. 榜单数据到手后新增「对手锚定」字段：每项标注「头部队伍是否已做 / 做到什么程度 / 我方剩余空间」。
<!-- ARTIFACT:END -->