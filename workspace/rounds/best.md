# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 53 轮（承接第 52 轮 v29 GroundEdge-GenSim；灵感驱动研究循环·新循环第 1 轮；本轮灵感：LoRA × 视觉问答 × 场景泛化） · UniBot-V1 参赛研究：VQA 监督的因子化场景泛化 × LoRA 适配器联邦 × reset() 摊销与测试时场景绊线

> 承接第 52 轮 v29。v29 把安全证书升级为"带可判定适用域与迁移风险预算的泛化证书"，把仿真降格为"有校准包络、只能否决不能单独批准"的仪器——但它服务的对象始终是"可认证的安全系统"：soundness 是目标，真机是稀缺资源，慢是美德。本轮任务被用户明确改写为：**寻找参加 UniBot 的创新点**——一个计分规则几乎正交的博弈：不比证书是否 sound，比 32 个桌面任务 × 5 类泛化场景格子上的**平均成功率与步骤分**；真机评测是别人（主办方）按时段租给你的稀缺品，而你的模型必须在一次提测里同时装下全部 32 个任务。本次转折的诚实表述是**换轨复用，不是推倒重来**：v29 用两轮建成的"泛化工程学"（任务描述符、适用域、迁移预算、仿真证伪、真实锚点、选择偏差校正、域漂移绊线）恰好是这场比赛中多数队伍缺失的地基——他们缺的不是又一个 VLA，而是**把"泛化"变成可测量、可归因、可逐步修复的工程对象**的方法论；v29 的安全执行栈（SEN/TBC/GPC/CE/IGC/ILM）在排行榜上不计分，本轮归档。三个灵感词精确命中新靶心：**LoRA** 回答"单模型如何装下 32 个任务而不互相稀释"；**视觉问答**回答"用什么仪器把 5 类泛化场景的失败归因说清楚"；**场景泛化**就是计分板本身。三者耦合并被平台接口放大出一个反直觉结论：**这场比赛的高分解大概率不是更大的模型，而是把重计算全部摊销到 reset() 与"不计分单任务调试"跑上、把每步延迟压稳的"场景感知适配器联邦"**——因为榜单是 160 个格子的平均值，任何一类格子系统性崩塌都会吃掉通才梦。

## 0. 情报核实（检索日期：2026-11-11；所有结论以下列链接为准，未核实处明确标注）

| # | 核实到的事实 | 来源 | 检索日期 |
|---|---|---|---|
| 1 | UniBot 世界挑战赛=宇树科技官方赛事（unibot.unitree.com，"Embodied AI · Manipulation · 2026"），隶属"世界物理AI大赛"体系（unitree.com/cn/challenge/World_Physical_AI_Competition/，年度投入 $10M、8+ 类目，含 DEXTERITY 灵巧操作类目）；2026-07-10 启动 | unibot.unitree.com；unitree.com；sohu.com/a/1048612018_122135404；ifeng tech.ifeng.com/c/8ueO0H1KMK7 | 2026-11-11 |
| 2 | UniBot-V1：32 项真实世界桌面操作任务（抓取/放置/双手协调），平台为 Unitree G1 + Dex1 夹爪；官方评测数据 32,000 演示样本、累计 169 小时（"DAPTO 2 挑战套任务集"） | 同上；zhizaozx.cn/articles/2qv-unitree-unibot-physical-ai-world-challenge.html | 2026-11-11 |
| 3 | 五类泛化场景：位置变化、干扰物存在、桌面背景差异、未见物品、人为干扰；按**平均成功率与平均步骤分**计分，排行榜按两者综合排序 | ifeng/sohu/zhizaozx（均引凤凰网科技 2026-07-10 稿）；unibot.unitree.com/challenges.html 与 leaderboard.html | 2026-11-11 |
| 4 | 32 个任务名已逐条核实：官方 HuggingFace collection "UniBot-V1 Challenge Dataset" 含 32 个 per-task LeRobot 数据集（G1_Dex1_HangCup / ArrangePlates / ArrangeTestTubes / ZipUp / ColorArrangement / Unlock / DisconnectEthernet / ConveyorSorting / FruitCollection / FoldTowel / OrganizeBookshelf / FruitSorting / SpellRobot / OrganizePencilCase / OrganizeStationery / StackBowls / StoreCups / OrganizeTools / PackDoll / PackBag / PackPhone / StoreEarphones / StorePaddle / PaperCupStacking / PickOutBatteries / ToolboxStorage / PlugCharger / SyringeWaterTransfer / PlugInEthernet / PlacePhotoFrame / RemovePinnedNote / PourOutMedicine）；单卡示例 G1_Dex1_HangCup：1.04k episodes、30 fps、4 相机 AV1 640×480、LeRobot v3.0、apache-2.0 | huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset；huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup | 2026-11-11 |
| 5 | 用户提示中的 unitreerobotics/unibot-v1-challenge 数据集页返回 HTTP 401（不存在或门控）；公开入口是上述 32-dataset collection，不是单一数据集 | 直接抓取该 URL 得 401 | 2026-11-11 |
| 6 | 提交接口（github.com/unitreerobotics/unibot_submission）：policy 类三成员 `metadata`/`get_action(obs)`/`reset()`；观测=4 相机（左右高位+左右手腕，480×640）+双臂 7DoF 状态+双臂 EE pose(6)+双夹爪开度+lower_body(15)+language（整局不变的字符串）；动作=joint 或 ee 二选一 + 双夹爪 + pivot(7)；`action_chunk_size≥1`；websockets+msgpack 协议；N 台评测机对应自 8765 起 N 个连续端口，允许多端口共享一个模型后端（须自行保证并发与逐端口状态隔离）；token 握手+逐步校验；**官方明示：逐步响应延迟及其波动、返回动作的统计规律性會被记录，并可能随成绩一并展示** | github.com/unitreerobotics/unibot_submission（README） | 2026-11-11 |
| 7 | 提测双模式（unibot.unitree.com/profile.html）：①计分多任务——单次覆盖全部 32 任务、计入排行榜；②**不计分单任务调试**——只测 1 个任务、不计入排行榜、"仅供了解模型大概能力"；两者均需预约时段并等管理员确认；模型登记需先经管理员确认 | unibot.unitree.com/profile.html | 2026-11-11 |
| 8 | 宇树开源模型生态：UnifoLM-WMA-0（World-Model-Action：世界模型同时充当交互式仿真引擎产合成数据 + 作为策略增强器预测未来交互；含 G1 真机部署示例；CC BY-NC-SA 4.0；代码 github.com/unitreerobotics/unifolm-world-model-action）；UnifoLM-VLA-0 为门控（登录才可见），无法核实细节 | huggingface.co/unitreerobotics/UnifoLM-WMA-0-Base | 2026-11-11 |
| 9 | 官方数据页 unitree.com/data（G1+Dex1/Dex3/Brainco，覆盖家居收纳/厨房/装配/清洁/衣物/流水线分拣）；社区资源 Unitree G1 Handbook（yfrobotics.github.io/unitree-g1-handbook/learning/datasets/，资源核对日 2026-09-13） | unitree.com/data；G1 Handbook | 2026-11-11 |
| 10 | **榜单与运行记录页当前均为"即将发布 / Coming Soon"**；GitHub 搜索未见有分量的参赛队伍仓库（仅官方模板与无关同名项目）；社区拆解仓库 Ed-gjd/unibot-challenge（曾含"赛制拆解/32任务总表"）检索时已 404 | unibot.unitree.com/leaderboard.html 与 runs.html；api.github.com/search/repositories?q=unibot | 2026-11-11 |
| 11 | 参赛手册/规则在飞书 docx（中文 Uz7OdFBcDoqP1dxgH62cHW1CnMh，英文 ZNHIdaGx0oPOlBxNVxkcswqqnnh），网页渲染拿不到正文 | challenges.html 内链接直取失败 | 2026-11-11 |

**因此必须对用户先验做降级处理**：题库描述中"榜首成功率也不到 30%"本轮**无法独立核实**（榜单未发布），只能作为待检验的先验 H0；对"头部方案做法"的一切陈述均为**约束推断**而非事实。未核实的四件套（步骤分公式、每格尝试次数/是否允许重试、是否允许测试时自适应与在线学习、评测机数量 N 与排期异构性）被列为下轮最高优先级的"规则锚点"。

## 1. 从 v29 到 v30：为什么是"换轨复用"而不是"另起炉灶"

v29 问的是"如何证明一个系统在可判定任务域内安全"，UniBot 问的是"如何让一个系统在 160 个格子上平均成功率最高、步骤更省"。对象不同，度量工具同构：适用域→格子覆盖；迁移证书→适配器迁移预算；仿真保真包络→生成数据/世界模型保真；真实锚点→留出集+不计分调试跑；选择偏差校正→同一代理集上比较 N 个候选；域漂移绊线→测试时场景 OOD。**v29 的全部数学都可以降级复用到比赛，唯独"安全执行栈"整体不计分。** 所以本轮做三件事：①把 v29 的泛化度量层改制为比赛工程协议（见产物区 v30）；②把 v15 的交互共地/主动权机构从"安全证书"复活为**计分功能**（人为干扰是 5 类场景之一）；③把其余安全 IP 归档，注明理由，留待产品线时取回。

## 2. 头部方案的约束推断（H1–H6，全部标注为推断）与瓶颈坐标系

**推断**：H1 头部主力是在官方 32×~1k episodes 上微调的主流开源 VLA（π0/π0.5、RDT-1B、OpenVLA(-OFT)、GR00T N1.x，或门控的 UniFoLM 系），joint 或 ee 单空间，chunk 8–50；H2 因规则强制单模型，多数队伍不做任务路由，靠语言条件+多任务混训硬吃；H3 泛化失败集中于未见物品、桌面背景、干扰物、工作空间边缘位置；H4 长程双手任务（Pack*/Fold*/Arrange*/ConveyorSorting）与精密插装（PlugCharger/PlugInEthernet/SyringeWaterTransfer）是成功率洼地；H5 无恢复机制，一步错则步步错；H6 人为干扰场景几乎无人专门设计行为。由此得到**瓶颈坐标系**（也就是创新空间的坐标系）：

- **B1 数据因子贫困**：官方数据单实验室、单一桌面布置，每任务 ~1k episodes 的视觉/因子覆盖窄 → 对背景、未见物、干扰物系统性过拟合。
- **B2 任务干扰**：32 任务共享容量互相稀释；难任务与易任务梯度冲突。
- **B3 无归因仪器**：队伍只有一个总分，无法回答"哪个因子在哪一阶段杀死哪类任务"，修复靠猜。
- **B4 测试时算力浪费**：`reset()` 与首帧里躺着整局的静态信息（语言指令+完整场景），大多数策略每步同权同构，从不做慢规划。
- **B5 接口工程裸奔**：延迟不稳、动作异常值、N 端口并发没做，会被官方记录并可能影响成绩可信度；步骤分（效率）无人优化。
- **B6 选择偏差**：在自己的调试/仿真代理上比 N 个候选取最优，赢家诅咒把"看起来的提升"当真，上真机就塌。

## 3. 灵感词 × 靶心的精确对位

- **LoRA** → B2/B1：32 个 per-task 适配器 + 若干因子特化适配器组成"适配器联邦"；用 ΔW 几何做迁移预算（只能检索不能当证明）；合并前过融合干扰检查。
- **视觉问答** → B3/B1/B5：VLM 不当聊天玩具，当**仪器**用：失败归因（VQA-Diag）、数据单向准入（VQA-Curate）、场景绊线（SGT）、人为干扰感知（HIR）、检索键（RAP）。
- **场景泛化** → 计分板本体：把 5 类场景变成 5 根可观测坐标轴（FSM），覆盖度逐轴记账，缺口定向补，测试时 unknown 即 out。
- **平台接口的隐藏红利**（本轮最关键的工程直觉）：`reset()` 是每局一次的**免费思考时间**；"不计分单任务调试"是**免费的真机锚点通道**；N 端口可共享一个模型后端。三者合起来意味着：重计算（VQA 审计、检索、世界模型推演）全部可以移出 `get_action` 的热路径。

## 4. 直觉与动机

**灵感 1（LoRA → 32 个任务不必在一个权重里打架）**
直觉：通才赛制逼着所有队伍把 32 个任务塞进一份权重，容量战争。LoRA 联邦把"任务"变成可插拔模块：任务专家保证深度，因子专家保证广度（背景不变性、干扰物鲁棒性各有一个专门适配器），路由在 `reset()` 时静态场景上跑一次即可——这是把 v29"适用域"思想翻译成比赛语言：**每个适配器只在自己被训练覆盖的因子域里说话，未知场景走绊线而不是硬猜**。

**灵感 2（视觉问答 → 没有归因仪器就没有泛化工程）**
直觉：科学里"没有测量就没有改进"。现在的队伍只有总分，失败是黑盒；VQA 把失败从"总分 −3%"变成"任务×因子×阶段归因矩阵里哪个格子红了"，并把修复清单按**期望格子增益**排序。这把 v29 的 DDA 十二源归因从"安全事故调查"改制成"排行榜故障排查"。

**灵感 3（场景泛化 → 覆盖是账本，不是口号）**
直觉：五类泛化场景=五根可观测轴；"泛化好"必须能写成"每个 (任务, 轴, 水平) 格子里的训练样本数 ≥ k"。数据缺口可以逐轴审计、定向补（生成式扩增+VQA 准入），而不是笼统地"多加数据"。

**灵感 4（接口红利 → reset() 是免费的，调试跑是免费的，延迟是贵的）**
直觉：评测方只记录 `get_action` 的延迟与规律性；`reset()` 每局只调一次；不计分调试跑不占排行榜。最优化策略因此极其清晰：**把 VLM/VQA/检索/世界模型全搬到 reset() 与 chunk 边界的异步流水线里，热路径只留一个小前向 + 适配器加权**。这与 v29"蒸馏只损失效率、不损失 soundness"同构：慢系统做决策，快系统做执行。

**灵感 5（单向准入从仿真搬到生成数据）**
直觉：生成式换背景/换物、世界模型合成 rollout，都是"便宜但可能说谎"的来源。v29 的 FDR 纪律原样搬过来：**生成/仿真可否决（语义校验不过就丢、预测失败就降权），不能自批准（生成集上的成功率永远不作为接受依据）；接受永远由真实锚点闭合。**

**灵感 6（人为干扰 → v15 交互安全的计分复活）**
直觉：5 类场景里有 1 类是人。多数策略会无视人继续动。v15 花整轮建的"主动权/共地"在安全语境里是证书，在比赛里是**行为**：进人→停→让→等→重规划。这是少数几个"不烧算力、纯靠设计"就能赢下的格子。

**耦合升级**：v29 的 L0.5"任务迁移与仿真证据层"整体改制成 v30 的**泛化工程协议层**（FSM/AMoA/AGE/VQA-Diag/VQA-Curate/SGT/RAP/WMR/EDP），架在"数据层（XDP）—部署层（IFE）—计分层（EDP）"之间；v15 的交互机构以 HIR 形式单点复活。核心不对称再次变轨：**慢系统（VQA/世界模型/检索）只许提议与证伪，快系统与真实锚点才许放行；生成数据可否决不能自批准；unknown 场景按 out 处理。**

## 5. 形式化定义（增量：定义 107–118）

**定义 107（格子、因子轴与场景描述符）**
任务表 𝒯={T_1,…,T_32}（名称已核实）。因子轴 ℱ={pos, dis, bg, unobs, human}：pos=位置变化、dis=干扰物存在、bg=桌面背景差异、unobs=未见物品、human=人为干扰。格子 c=(T,f,ℓ)，ℓ∈L_f 为轴水平。场景描述符 s(o)∈𝔇 由可解释字段构成：语言指令、物体集合（VQA 计数/类别）、背景标签、干扰物存在与位置、人/人手在场与距离、目标位姿、任务阶段。𝔇 上嵌入距离只用于检索与路由预热，**不单独构成任何接受依据**（继承 v29：learned distance ≠ soundness）。

**定义 108（覆盖账本与最小-k 覆盖）**
对语料 D，cov(D,T,f) 为按 s(o) 归纳的 (T,f) 轴水平直方图；最小-k 覆盖 cov_min-k(D,T)=|{ℓ : count(D,T,f,ℓ)≥k}|。缺口集合 𝔾(D)=argmin cov_min-k，按计分权重 w(c) 排序生成补数清单。目标函数：maximize min_{c∈C_scored} cov_min-k（先补最可能被计分的格子），而非总样本量。

**定义 109（适配器联邦与路由）**
基座 π_θ 冻结或半冻结；适配器库 𝒜=任务专家 {a_T}_{T∈𝒯} ∪ 因子专家 {a_f}_{f∈ℱ} ∪ 交叉专家。路由 r(s)→w，w≥0、Σw=1、top-k 稀疏；有效增量 ΔW_eff=Σ_a w_a·ΔW_a（低秩增量相加，合并成本可忽略）。**融合干扰约束**：合并后在冻结干扰检查集上，每任务指标不低于其最优单适配器 −ε_merge，否则拒绝该组合并降级为单适配器（运行期 fail-safe，不是性能保证）。

**定义 110（适配器几何与迁移预算（仅检索））**
g(A_i,A_j)=cos(ΔW_i,ΔW_j) 或子空间主角；迁移预算 τ_tr(i→j)=1−g 的经验分位数。**用途被明确限制为**：新任务的 warm-start 选择、合并相容性预筛、路由候选裁剪。任何以 g 为依据的性能声明必须经定义 113 的锚点闭合后方可写入报告。

**定义 111（VQA 归因算子）**
对 rollout 帧序列 V 与问题库 Q（"夹爪是否接触目标？""干扰物是否被误抓？""人手是否进入工作区？""处于哪一阶段（reach/grasp/transport/place）？"），归因 A(V,Q)→M[T,f,phase]，元素为失败概率。修复清单 L 按期望格子增益排序：E[Δscore_c]=w(c)·P(fail|c)·P(fix|c)。归因器以人工标注子集校准，precision/recall 必须报告；低精度问题库条目禁用。

**定义 112（生成/仿真数据的单向准入）**
生成器 G（换背景/换物）与世界模型 W（UnifoLM-WMA 类）。Adm_G：语义校验失败→丢弃（否决）；通过→候选池，混合比例 λ 由**真实锚点**上的收益曲线 argmax 决定；**禁止**以生成集成功率作为接受依据。仿真保真 ε_W(T)=真实/预测未来差的经验分位数；W 对未来失败的预测只能否决（候选块降权），不能单独批准任何动作。

**定义 113（真实锚点协议）**
锚点集 A 有两来源：①官方数据分层留出（按 task×factor 分层，永不进训练/调参/路由选择）；②**不计分单任务调试跑**（每任务多次，记录完整视频与分步结果）。接受门：权重/适配器库/路由/提示库/数据清单任一变更 → 在 A 上回归，回退 >θ_anchor 即拒绝上线。锚点预注册、与调参过程隔离。

**定义 114（选择偏差与格子可信增益）**
同一代理集上比较 N 个候选取最优，表观增益乐观有偏；报告增益须扣除 α_sel(N,m)=√(2(ln N+ln(1/β))/m)（m=独立锚点数）；N 越大所需锚点越多；禁止在锚点上早停或事后挑选。计分跑预约本身是稀缺锚点，只允许花在预注册候选上。

**定义 115（场景绊线与保守模式）**
每个 chunk 边界（及 reset）重算 s(o)；若任一轴取 unseen_level、路由置信低于阈值、或人/人手在场 → 切换保守模式：chunk 缩短、速度缩放、转 RAP 引导或 HIR。**unknown 一律按 out 处理**（fail-safe 方向：宁可慢与保守，不可盲进）。

**定义 116（延迟/步骤预算）**
每步推理时延约束 P(t_get_action ≤ B_step) ≥ 1−β_lat（官方记录 p50/p99 与规律性）；重算（VQA/检索/世界模型）只允许在 reset() 或 chunk 边界异步发生；每格步数上限 H_c（步骤分），子目标在 reset() 前置规划以减少振荡与重复抓取。

**定义 117（人为干扰反应合约）**
状态机 NORMAL→（人进入工作区/抓取被拉扯）→YIELD（停；若被拉扯则让物）→WAIT（清场监测）→RESUME（重过定义 115 后重规划）或 ABORT（收拢/安全姿态）。触发须检测器与 VQA 双证据；恢复重规划必须重新过绊线。

**定义 118（版本六元组（竞赛版））**
(基座权重, 适配器库, 路由器, 问题/提示库, 数据清单 h_D, 接口配置) 六元组任一变更 → 定义 113 回归 → 定义 114 重算校正 → 才允许预约计分跑。

## 6. 算法骨架（比赛管线宏周期）

每轮迭代（对应产物区 v30 的实验编号）：
1. **规则闭环**：先读飞书手册+邮件问询+首次不计分调试跑，补齐"步骤分/尝试次数/是否允许测试时自适应/N 台机器"四项未知；未闭环前不预约计分跑。
2. **数据层**：FSM 覆盖审计（定义 108）→ VQA-Curate 定向扩增（定义 112，λ 由锚点曲线定）→ XDP 两阶段预训练 → AMoA 训练（定义 109）。
3. **诊断层**：VQA-Diag 跑仿真+调试跑视频 → 归因矩阵 → 按期望格子增益排序的修复清单（定义 111）→ 回灌 2。
4. **部署层**：IFE 端口/异步分块/延迟与步骤预算（定义 116）；reset() 内完成：场景审计（s(o)）、路由与合并、检索与子目标规划、VQA 基线提问。
5. **执行层**：`get_action` 只做快路径；chunk 边界做 SGT 绊线（定义 115）与 WMR 候选块重排（定义 112）；人场走 HIR（定义 117）。
6. **计分层**：EDP 预注册 → 锚点闭合（定义 113）→ α_sel 校正（定义 114）→ 才预约计分多任务跑；任何一步不合 → 回退到上一注册版本，绝不上未闭合候选。

## 7. 本轮最大风险

**一句话**：v30 的整个经济学建立在三个未核实的平台变量上——**步骤分公式、是否允许 reset()/测试时重算与在线自适应、评测机数量 N 与排期异构性**；若规则与推断相反（例如"不计分调试跑"也被计入某种统计、或步骤分把保守 pause 罚得很惨、或 N 台机器逐机异构到路由失灵），"把重算摊销到 reset()/调试跑"的收益就要重算，而榜单为空意味着我们连"头部到底长什么样"都还没有事实——因此下轮第一优先级是把飞书手册、一次真实不计分调试跑与主办方问询当作"规则锚点"来抓，在拿到它们之前，任何计分跑都不预约，任何基于榜单先验的豪赌都不加注。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 53 轮产物 · 创新点清单 v30：UniBot-V1 参赛创新（FSM × AMoA × AGE × VQA-Diag × VQA-Curate × SGT × RAP × WMR × HIR × IFE × XDP × EDP）+ v29 泛化度量层改制与安全栈归档

> 承接第 52 轮产物 v29。本轮任务改写为"寻找参加 UniBot 的创新点"，清单随之**换轨复用**：v29 的泛化度量层（TIX/XFR/CRC/SFE/FDR/RAB/DST/SBC）逐件改制为比赛工程协议，v15 的交互共地/主动权机构以 HIR 形式**计分复活**，其余安全执行栈归档（不计分）。新增 IP-107..IP-119（IP-119 为规则依赖的条件项）。核心架构位移：**从"证明系统在域内安全"转向"把 32 任务 × 5 场景的 160 个格子变成可覆盖、可归因、可修复、可 preregister 的工程对象"；慢系统（VQA/世界模型/检索）只许提议与证伪，快系统与真实锚点才许放行；生成数据可否决不能自批准；unknown 场景按 out 处理。** 情报与来源见想法区第 0 节（检索日期 2026-11-11）；榜单为空，"榜首 <30%"为用户先验 H0，未核实。

## 0. 核心 IP 总表

| 编号 | 名称 | 类型 | 关键改进 |
|---|---|---|---|
| IP-107 | FSM Factorized Scene Manifold | 新增（v29 IP-99 TIX 改制） | 5 因子轴 × 32 任务的格子坐标系 + 最小-k 覆盖账本；缺口按计分权重定向补 |
| IP-108 | AMoA Adapter Mixture-of-Adapters | 新增 | 任务×因子 LoRA 适配器联邦 + reset() 路由 + 融合干扰检查；单模型合规 |
| IP-109 | AGE Adapter-Geometry Transfer Map | 新增（v29 IP-100 XFR 降级改制） | ΔW 几何迁移图，仅用于 warm-start/合并预筛/路由裁剪，绝不作 soundness |
| IP-110 | VQA-Diag VQA 归因仪器 | 新增（v29 IP-77 DDA 改制） | rollout 视频 → 任务×因子×阶段失败矩阵 → 按期望格子增益排序的修复清单 |
| IP-111 | VQA-Curate VQA 保真扩增 | 新增（v29 IP-102/103 改制） | 生成式换背景/换物 + VQA 语义单向准入；混合比例由真实锚点曲线定 |
| IP-112 | WMR World-Model Re-ranker | 新增（v29 虚拟仿真灵感产品化） | UnifoLM-WMA 类世界模型对候选动作块做事后重排；预测失败只否决 |
| IP-113 | SGT Scene Generalization Tripwire | 新增（v29 IP-105 DST 改制） | 测试时场景 OOD 绊线 → 保守模式/适配器切换；unknown=out |
| IP-114 | RAP Retrieval-Augmented Execution | 新增 | reset() 检索最近演示 → VLM 子目标 + 适配器提示 + 动作先验；未见物品的救命绳 |
| IP-115 | HIR Human-Interference Reactor | 新增（v15 IGC/ILM 计分复活） | 停-让-等-恢复状态机，专打"人为干扰"这 1/5 计分格子 |
| IP-116 | IFE Interface & Fidelity Engineering | 新增 | 控制空间选择 + 异步分块流水线 + N 端口并发 + 延迟/步骤预算纪律 |
| IP-117 | XDP Cross-Dataset Pretraining | 新增 | 宇树全系开源 G1 数据一阶段 + 官方 32 任务二阶段，破官方数据因子贫困 |
| IP-118 | EDP Eval-Discipline Protocol | 新增（v29 IP-104/106 改制） | 留出锚点+调试跑锚点账本 + 预注册选型 + α_sel 选择偏差校正 |
| IP-119 | TTA-lite 测试时快速适配 | 新增（条件项） | 规则允许才做的 per-robot/在线微调；规则未闭环前冻结 |
| v29 安全栈 | GPC/CE/PFV/CAR/MRC/SIC/IPC/UCC/RRP/CCL + v15 IGC/ILM/XTC/SEN/TBC | 归档 | 排行榜不计分；留待产品线；仅 HIR 单点复活 |

## 1. 逐点详表（动机 / 差异 / 可行性 / 资源 / 落地 / 风险）

### IP-107 FSM Factorized Scene Manifold（因子化场景坐标与覆盖账本）
- **动机**：B1 数据因子贫困 + B3 无归因。"泛化"必须先变成可记账的对象，否则一切修复都是猜。
- **与现有方案差异**：现有队伍按"任务"组织数据与训练；FSM 按 (任务 × {pos,dis,bg,unobs,human}) 组织，覆盖度逐轴记账，缺口定向补；描述符可解释（VQA 可判），嵌入距离只用于检索。
- **技术可行性**：高。VQA/CLIP 对背景、干扰物、人手、物体集合的判定在当前 VLM 能力内可靠；官方 4 相机+EE+夹爪观测足够支撑大多数轴的在线判定（人手距离需深度近似或用腕部相机遮挡线索兜底）。
- **所需资源**：官方 32 dataset（~8.8GB/任务，共约 280GB）+ VQA 推理（离线批处理为主）；算力可忽略。
- **落地步骤**：①对全量官方 episode 抽帧跑 VQA 标签；②建 32×5 覆盖矩阵；③标注计分权重 w(c)（未知，先用均匀先验）；④生成补数清单驱动 IP-111。
- **风险**：VQA 标签噪声→覆盖矩阵假性丰满（用人工抽检校准精度）；w(c) 未知→补数优先级错（下轮用规则+调试跑校准）。

### IP-108 AMoA Adapter Mixture-of-Adapters（LoRA 适配器联邦）
- **动机**：B2 任务干扰。单模型硬吃 32 任务必然稀释难任务容量；LoRA 让任务可插拔、因子可特化。
- **与现有方案差异**：非"一份权重吃全部"，也非"32 个独立模型"（违规且贵）；而是共享基座 + top-k 适配器加权合并；路由在 reset() 静态场景上跑一次，剧中近乎免费；每任务保留"单适配器回退"作为 fail-safe。
- **技术可行性**：高。LoRA 在 π0/OpenVLA-OFT/RDT 上均有成熟用法；ΔW 相加的合并成本可忽略；路由可用 SigLIP/DINOv2 场景嵌入 + VQA 标签的浅层 MLP，或干脆查表（场景标签 → 预计算权重）。
- **所需资源**：32 任务 × ~1k episodes 微调（可串行，每任务数十分级 on 单卡 A100 级；或按因子专家并行）；路由训练用抽帧标签；显存只需一份基座+小适配器。
- **落地步骤**：①选基座（优先开源且许可宽松者；UnifoLM-VLA-0 门控不可靠）；②训 32 个任务 LoRA + 5 个因子 LoRA + 交叉专家；③冻结集上训路由并做融合干扰检查；④部署为单一 policy（接口合规）。
- **风险**：合并噪声伤害某些任务（用 ε_merge 门+单适配器回退兜底）；路由误判在 unseen 场景上更糟（与 IP-113 联动：OOD 时走保守模式而非合并）。

### IP-109 AGE Adapter-Geometry Transfer Map（ΔW 几何迁移图）
- **动机**：v29 教训"learned distance ≠ soundness"要在比赛里找到建设性出口：任务相似度不能当证明，但能当**调度与预筛**。
- **与现有方案差异**：不用文本相似度或人工先验排任务亲缘，而用训练出的 ΔW 子空间几何；迁移预算 τ_tr 只影响 warm-start 顺序、合并白名单、路由候选集。
- **技术可行性**：高（g=cos(ΔW_i,ΔW_j) 或子空间主角，训练完一次算好）；与实测迁移成功率做相关性审计即可得到 τ_tr 分位数。
- **所需资源**：仅适配器权重；无额外数据。
- **落地步骤**：①算全对几何矩阵；②在调试跑上验证 g 与"i→j 微调收敛速度/收益"的相关性；③把 τ_tr 写进路由与合并规则；④任何性能声明必须过 IP-118 锚点。
- **风险**：把 g 当证明用（制度上禁止：所有 AGE 输出只进"检索/调度"通道，报告里必须标注）。

### IP-110 VQA-Diag VQA 归因仪器
- **动机**：B3 无归因仪器。失败必须被定位到 任务×因子×阶段 才能在 160 格子上做有效修复。
- **与现有方案差异**：队伍普遍只看标量成功率；少数用 LLM judge 判"成没成"；VQA-Diag 输出**结构化因果矩阵**（哪个因子、哪个阶段、以多大概率致死），并把修复动作按期望格子增益排序。
- **技术可行性**：高（Qwen-VL/Gemini/GPT-4o 级 API 或本地开源 VLM；问题库可版本化）。
- **所需资源**：仿真 rollout + 官方不计分调试跑视频（平台 runs 详情页即完整评测视频——官方明示可看）；API 费用中低；人工标注小样本校准集（~200 条）。
- **落地步骤**：①定义问题库 Q（覆盖 5 轴 × 4 阶段）；②校准 precision/recall，禁低精度条目；③每轮对全部 rollout 跑归因；④修复清单直接排进下周训练/数据计划；⑤归因矩阵进 EDP 复盘。
- **风险**：VQA 幻觉把修复带偏（双证据：同一帧至少两问交叉验证；与分步日志一致性检查）；只解释可见失败、不解释"该做而没做"（补动作意图问题）。

### IP-111 VQA-Curate VQA 保真的因子化扩增
- **动机**：B1。官方数据因子贫困，而计分偏偏打在因子泛化上；定向扩增是性价比最高的数据侧创新。
- **与现有方案差异**：不是笼统 domain randomization，而是**按 FSM 缺口逐轴定向生成**（缺哪种背景补哪种背景、缺哪类未见物补哪类），且生成样本必须过 VQA 语义校验（换背景后"物还在、可抓、任务仍成立"）；混合比例 λ 由真实锚点收益曲线定，**绝不用生成集成功率自批准**（v29 FDR 纪律）。
- **技术可行性**：中高。背景替换可用 inpainting/2D 生成 + 透视适配；物体替换用分割+重合成+阴影近似；对 4 相机统一生效有工作量但可控。VQA 门可挡多数语义破坏样本。
- **所需资源**：生成算力（图像扩散批量推理）；VQA 门推理；官方 episode 抽帧；无新真机数据。
- **落地步骤**：①按 𝔾(D) 排优先级；②每轴建 3–5 个生成模板；③VQA 门（否决语义破坏）；④λ∈{0, 0.1, 0.3, 0.5} 在留出锚点+sweep；⑤记录"生成集成功率 vs 锚点成功率差"作为审计留痕。
- **风险**：生成图域差（颜色/光照/边缘伪影）教出"生成分布偏置"（λ 上限由锚点曲线决定，且优先做**保真度高的轴**：背景>位置>干扰物，未见物次之）；人手生成慎用（假人误导 HIR，人手轴优先走仿真+真实视频增强而非图像生成）。

### IP-112 WMR World-Model Re-ranker（世界模型重排器）
- **动机**：B4/H4。接触密集与长程任务的失败常在"动作块级别"可见（预测会把抓滑、对位偏差显式化）；chunk 执行前重排比事后恢复省步骤。
- **与现有方案差异**：多数队伍对 chunk 不做未来一致性检查；WMR 用宇树开源 UnifoLM-WMA-0 的世界模型对 top-k 候选块做事后预测并按任务进度打分；**预测失败只否决、不批准**（v29 仿真认识论）。
- **技术可行性**：中。WMA-0 为开源（CC BY-NC-SA 4.0，需评估许可与比赛场景适配）；在 G1 上有真机部署先例；把 WP 接到本任务观测键上需要适配层。
- **所需资源**：WMA-0 权重+推理算力（仅 chunk 边界/相位切换时触发，摊销后可承受）；官方数据里已有的多帧序列可用于校准 ε_W(T)。
- **落地步骤**：①适配观测键→世界模型输入；②在官方 episode 上估 ε_W(T)（分位数）；③定义进度打分（物体-目标距离、抓持一致性、稳定性）；④与 chunk 执行异步化；⑤仅在 ε_W(T) 达标的任务开启（插装/双手优先）。
- **风险**：世界模型分布外任务上乱否决造成过度保守（按 ε_W(T) 分任务开关+保守率上限）；许可条款需确认（NC 条款与比赛合规性问主办方）。

### IP-113 SGT Scene Generalization Tripwire（测试时场景绊线）
- **动机**：B1/B6。未知场景里"硬猜"是平均成功率的最大杀手；v29 DST 的 fail-closed 直觉直接迁移为计分行为。
- **与现有方案差异**：现有方案在 unseen 场景继续照常推理；SGT 在每个 chunk 边界重判场景轴，OOD→缩 chunk、降速、切 RAP 引导/单适配器/或保守暂停；不是"更鲁棒的策略"，而是"知道自己不行的策略"。
- **技术可行性**：高。判定复用 IP-107 的描述符（reset 全量 + chunk 增量）；OOD 分数=场景嵌入到训练分布边界的距离 + 路由置信。
- **所需资源**：VQA/嵌入推理（可摊销）；FSM 覆盖矩阵；无新数据。
- **落地步骤**：①定义每轴的"已见水平"集合（来自 FSM）；②OOD 打分与阈值（在调试跑上校准误报/漏报）；③保守模式行为清单（缩 chunk/降速/重路由/暂停）；④与 HIR 共享检测前端。
- **风险**：误报把可做格子变保守（阈值按"保守代价≤该格失败代价"校准；记录保守率上报 EDP）；漏报在危险方向（OOD 判成 in-domain）——阈值偏保守、双证据（嵌入+VQA）。

### IP-114 RAP Retrieval-Augmented Execution（检索增强执行）
- **动机**：H3/H4。未见物品与长程任务里，"找到最像的那次演示"往往比泛化推理更可靠；VLM 规划器需要示范来锚定子目标。
- **与现有方案差异**：端到端 VLA 无记忆；RAP 在 reset() 用（语言嵌入 × 场景嵌入）检索官方数据 top-k 演示，转化为：①VLM 规划器的 few-shot 子目标序列，②适配器提示（AGE 预热），③动作先验（末端目标距离统计）；检索库可含自采仿真数据。
- **技术可行性**：高（FAISS/向量库 + 开源 VLM 规划；演示轨迹回放只作先验不作控制）。
- **所需资源**：官方 32k episode 索引（键：instruction + 首帧嵌入）；VLM API 或本地；无新数据。
- **落地步骤**：①建索引；②规划器 prompt 模板（任务分解+子目标+失败恢复提示）；③先验融合权重在锚点上调；④仅当 SGT 判定 in-domain 低置信或 unobs 轴活跃时强化使用。
- **风险**：检索到误导性演示（相似≠可迁移，v29 教训；仅作先验，最终以策略+VQA 一致性校验为准）；规划延迟（全部放 reset()）。

### IP-115 HIR Human-Interference Reactor（人为干扰反应堆）
- **动机**：H6/定义 117。"人为干扰"是 5 类计分场景之一，而多数策略会无视人继续动——这是少数"纯设计、不烧算力"就能赢的格子；同时它是 v15 交互安全机构在比赛中的计分复活。
- **与现有方案差异**：现有方案无"人"的概念；HIR 是显式状态机 NORMAL→YIELD→WAIT→RESUME/ABORT，触发需检测器+VQA 双证据，让物策略按抓持状态分派。
- **技术可行性**：高（人体/人手检测成熟；VQA 判"人手是否进入工作区/是否拉扯物体"；恢复即重过 SGT 重规划）。
- **所需资源**：含人片段的数据（可在仿真+官方视频增强中构造人手进入/拉扯片段，VQA 保真）；无新真机需求。
- **落地步骤**：①检测前端（4 相机各自判据 + 融合）；②状态机与让物/松手策略；③仿真+视频增强训练/标定；④调试跑里专测 human 格（若调试跑可指定场景，需规则确认）；⑤与步骤分权衡（恢复步数计入预算）。
- **风险**：规则未明（干扰的判定与计分细则、是否允许 pause）——**规则未闭环前只做"最小安全版"（停+让人+恢复），不做花式交互**；误触发打断正常执行（双证据+滞回）。

### IP-116 IFE Interface & Fidelity Engineering（接口与工程保真）
- **动机**：B5 + 官方明示记录延迟/动作规律性。N 台机器、websockets、chunk 语义、端口并发——比赛里"模型对但工程崩"是常见死法。
- **与现有方案差异**：多数队伍用模板裸署；IFE 把接口当优化对象：控制空间选型、异步分块流水线（执行 chunk k 时算 chunk k+1）、N 端口共享后端 + 逐 episode 状态隔离、固定 batch/shape 的稳定延迟、动作异常值过滤，以及**步骤经济**（reset 前置规划减少振荡/重复抓取）。
- **技术可行性**：高（纯工程）；关键决策：ee 空间（降维、可借 IK 与先验）vs joint 空间（免 IK、直接监督官方动作）；pivot/lower_body 建议置零或缓变，除非任务确需（官方数据动作含 lower_body，但桌面任务基本不需要）。
- **所需资源**：GPU×1（共享后端即可，README 明示 Approach 2 可行）；本地 run_server/run_client 验证工具（模板自带）；压测脚本。
- **落地步骤**：①用模板跑通零动作基线；②接入模型+选定 control_space/chunk；③异步流水线+延迟压测（p50/p99<B_step，异常值率=0）；④N 端口并发与状态隔离测试；⑤计分跑前 24h 冻结工程配置进版本六元组。
- **风险**：延迟抖动被记录甚至影响可信度（固定 shape/prealloc，禁动态图）；N 端口共享后端互相阻塞（README 已警告并发与隔离，须压测）；chunk 过大→无法响应干扰/失败（与 SGT 联动动态缩块）。

### IP-117 XDP Cross-Dataset Pretraining（跨数据集两阶段预训练）
- **动机**：B1。官方数据是单实验室窄因子样本；宇树自家开源的全系 G1 数据（Dex1/Dex3/Brainco、家居/厨房/装配/清洁/衣物/流水线）提供因子多样性，是"别人没有的数据红利"。
- **与现有方案差异**：不是只微调官方 32 任务，而是官方外数据做一阶段（视觉/技能多样性）+ 官方数据做二阶段（任务对齐）；数据键名/动作语义差异用适配层吸收。
- **技术可行性**：中高（要处理相机名、动作键、频率、手型差异；Dex1 夹爪与官方一致是关键利好——UniBot 数据同为 Dex1）。
- **所需资源**：宇树开源 G1 数据集下载（数十~数百 GB 级）；训练算力（一阶段可用 LoRA 低成本）。
- **落地步骤**：①盘点键空间差异，建统一 schema；②一阶段 LoRA 续训；③在官方留出锚点验证无负迁移；④二阶段 AMoA 化。
- **风险**：异构数据稀释官方任务性能（分阶段+锚点门）；许可差异（数据集 apache-2.0 友好，模型另有条款）；存储/带宽成本。

### IP-118 EDP Eval-Discipline Protocol（评测纪律：锚点、预注册、选择校正）
- **动机**：B6。在自己代理上比 N 个候选必中赢家诅咒；计分跑是稀缺锚点。v29 的 RAB/SBC 在比赛里的用处比在安全里还大。
- **与现有方案差异**：普遍做法是"本地指标涨了就约真机"；EDP 规定：①分层留出锚点（永不进训练/调参）；②不计分调试跑=真机锚点账本（逐任务记录，构造 per-task real success 估计）；③任何改动先过锚点回归；④报告增益须扣 α_sel(N,m)；⑤计分跑只花在预注册候选上。
- **技术可行性**：高（纯流程+记录）。
- **所需资源**：存储与台账；无额外算力。
- **落地步骤**：①建台账（变更-锚点结果-校正增益-预约记录）；②预注册模板（每轮只允许一个主假设+若干对照）；③泄漏审计（训练∩留出=∅）；④计分跑前门（锚点回归 + 校正增益 > 阈值）。
- **风险**：流程变官僚拖慢迭代（门要轻：锚点回归自动化）；调试跑机会本身也稀缺（按任务轮转，优先高风险格子）。

### IP-119 TTA-lite 测试时快速适配（条件项，规则未闭环前冻结）
- **动机**：若规则允许，利用调试跑/计分跑间隙对**具体评测机**（相机标定/光照/桌面）做 LoRA 快速适配，是把 fleet 异构变成优势的唯一途径。
- **与现有方案差异**：多数方案部署后不可变；TTA-lite 保持"单模型"合规（同一套权重+按机器位次条件化的适配器），仅在规则明确的在线学习窗口内更新。
- **技术可行性**：中（LoRA-drop + 少步微调在部署工程上成熟）。
- **所需资源**：调试跑数据留存；规则许可。
- **落地步骤**：**先问主办方**（飞书手册+challenge_support@unitree.com）是否允许测试时更新与数据留存；允许才启用，否则冻结。
- **风险**：违规风险（可能被判作弊/不可信——官方已明示关注交互规律性）；过拟合到单台机器损害其他机器泛化（需 per-port 隔离与回退门）。

## 2. v29 改制与归档对照（不推倒，只换轨）

| v29 原件 | 本轮处置 | 说明 |
|---|---|---|
| IP-99 TIX 任务指纹/适用域 | 改制为 IP-107 FSM | 描述符思想原样继承；"域"变成"格子覆盖"，unknown=out 原样保留 |
| IP-100 XFR 迁移证书 | 降级改制为 IP-109 AGE | soundness 分量在比赛里无处安放，只保留"检索/调度"用途并制度化禁止滥用 |
| IP-101 CRC 组合代数 | 局部保留 | 双手/多阶段组合的适配义务简化为 AMoA 的组合专家 + VQA 阶段一致性检查 |
| IP-102 SFE 仿真保真 | 改制为 IP-112 的 ε_W(T) | 世界模型保真按任务条件化估计 |
| IP-103 FDR 单向证伪 | 改制为定义 112 | 生成/仿真否决而不批准 |
| IP-104 RAB 真实锚点 | 改制为 IP-118 EDP | 锚点来源=留出集+不计分调试跑 |
| IP-105 DST 域漂移绊线 | 改制为 IP-113 SGT | 在线绊线，fail-closed 方向改为"保守模式" |
| IP-106 SBC 选择校正 | 并入 IP-118 | α_sel(N,m) 原样保留 |
| IP-77 DDA 十二源归因 | 改制为 IP-110 VQA-Diag | 归因从安全事故改为排行榜故障排查 |
| v15 IGC/ILM/主动权 | **复活为 IP-115 HIR** | 共地与主动权从证书变行为，专打"人为干扰"格子 |
| IP-94 GPC / IP-96 CE / IP-83 PFV(安全) / IP-51 CAR / IP-85 MRC / IP-79 SIC / IP-82 IPC / IP-86 UCC / IP-72 RRP / IP-76 CCL / v15 SEN/TBC/XTC 与其余安全栈 | 归档 | 排行榜不计分；留待产品线时取回；归档原因=计分规则不含安全性维度 |

## 3. 符号体系（增量）

| 符号 | 含义 |
|---|---|
| 𝒯, ℱ, c=(T,f,ℓ) | 32 任务表 / 5 因子轴 / 格子 |
| w(c), H_c | 格子计分权重（待规则核实，先用均匀先验）/ 每格步数上限 |
| s(o)∈𝔇, d_𝔇 | 场景描述符（VQA 可解释字段）/ 描述符距离（仅检索） |
| cov_min-k, 𝔾(D) | 最小-k 覆盖数 / 覆盖缺口集合 |
| π_θ, ΔW_a, 𝒜 | 冻结基座 / 适配器 a 的权重增量 / 适配器库（任务×因子×交叉专家） |
| r(s)→w | 路由（reset() 计算，top-k 稀疏，Σw=1） |
| ε_merge | 融合干扰容差（超限即拒绝合并，回退单适配器） |
| g, τ_tr | ΔW 几何相似度 / 迁移预算（仅调度） |
| A(V,Q)→M[T,f,phase] | VQA 归因算子与失败矩阵 |
| G, Adm_G, λ | 生成器 / 生成数据单向准入 / 混合比例（锚点曲线定） |
| W, ε_W(T) | 世界模型（WMA-0 类）/ 任务条件化保真分位数 |
| A_anchor, m, θ_anchor | 真实锚点集（留出+调试跑）/ 锚点数 / 回归回退门 |
| N, α_sel(N,m) | 同代理集上比较的候选数 / 选择偏差扣除项 |
| B_step, β_lat | 每步延迟预算 / 违规概率 |
| 版本六元组 | (基座, 适配器库, 路由, 提示库, 数据清单 h_D, 接口配置) |

## 4. 关键算法 伪代码

### IP-107 FSM + IP-108 AMoA（覆盖账本与适配器联邦）
```
def scene_descriptor(obs, vqa):            # 定义 107：可解释字段
    return {
        "task": obs.language,              # 整局不变
        "objects": vqa.count_and_name(obs.frames),      # 含未见物
        "bg": vqa.background_tag(obs.frames),
        "distractor": vqa.distractor(obs.frames),
        "human": vqa.human_presence(obs.frames),        # 人/人手在场+距离
        "phase": vqa.phase(obs.frames),                 # reach/grasp/transport/place
    }

def coverage_ledger(dataset, k):           # 定义 108
    cov = Counter()
    for ep in dataset:
        s = scene_descriptor(ep.frames[0], VQA_OFFLINE)
        for f in FACTORS:
            cov[(s.task, f, s[f])] += 1
    gaps = sort_by_weight([(T,f) for T in TASKS for f in FACTORS
                            if cov_min_k(cov, T, f) < k], key=w, reverse=True)
    return cov, gaps

def reset_cognition(obs, bank, rag):       # 定义 109/116：重算全部摊销到 reset()
    s = scene_descriptor(obs, VQA_ONLINE_FAST)
    w = router(s, bank)                    # top-k，场景嵌入+VQA标签；OOD→保守档
    demos = rag.retrieve(s, k=4)           # IP-114：语言×场景嵌入
    plan = vlm_planner(s, demos)           # 子目标+失败恢复提示
    eps = merge_check(bank, w, freeze_set) # 融合干扰检查
    return (w if eps <= EPS_MERGE else single_best_adapter(s, bank)), plan, s

def get_action(obs, state):                # 热路径：只做快前向+合并推理
    a_chunk = policy(obs, state.w, state.plan)   # ΔW_eff=Σ w_a ΔW_a
    if tripwire(obs, state.s):             # IP-113：OOD/人场
        return conservative(a_chunk)       # 缩块/降速/切引导/暂停
    return wmr_rerank(obs, a_chunk, state) if world_model_enabled else a_chunk
```

### IP-109 AGE（ΔW 几何，仅调度）
```
def adapter_geometry(bank):                # 定义 110
    G = {(i,j): cos(dW[i], dW[j]) for i in bank for j in bank}
    tau_tr = quantiles(1 - G[i,j] for ..., q=[0.5, 0.9])
    return G, tau_tr                        # 只进 warm-start/合并预筛/路由候选

def warm_start(task_new, bank, G, tau_tr):
    cand = top_k(G, task_new, k=3)
    return [c for c in cand if tau_tr(task_new, c) <= TAU_BUDGET]
```

### IP-110 VQA-Diag（归因仪器）
```
def vqa_diagnose(rollouts, Q):             # 定义 111
    M = zeros((len(TASKS), len(FACTORS), len(PHASES)))
    for r in rollouts:                     # 仿真 + 不计分调试跑视频
        ans = vqa.ask(r.frames, Q)         # 阶段判定+因子致死证据
        if r.failed:
            for (f, ph, p) in ans.evidence:
                M[r.task, f, ph] = max(M[r.task, f, ph], p)
    fixlist = sorted(TASKS, key=lambda T: expected_gain(T, M, w), reverse=True)
    return M, fixlist                      # 修复清单按期望格子增益排序
```

### IP-111 VQA-Curate（单向准入的因子扩增）
```
def curated_augment(official, gaps, lam_grid):     # 定义 112
    pool = []
    for (T, f) in gaps:                    # 按覆盖缺口定向生成
        for tmpl in GENERATORS[f]:
            img2 = tmpl(ep.frames)         # 换背景/换物/加干扰
            if not vqa.semantic_ok(img2, T):  # "物还在/可抓/任务仍成立"
                continue                   # 否决（唯一允许的处置）
            pool.append((img2, T, f, tmpl.id))
    curve = []
    for lam in lam_grid:                   # 混合比例只由真实锚点定
        mixed = mix(official, pool, lam)
        model = train(mixed)               # 复用既有训练配方
        curve.append((lam, eval_on_anchors(model, A_anchor)))
    lam_star = argmax(curve)               # 生成集成功率只作留痕，不作依据
    return pool, lam_star, curve
```

### IP-113 SGT + IP-115 HIR（绊线与人干扰反应堆）
```
def tripwire(obs, s_prev):                 # 定义 115
    s = scene_descriptor(obs, VQA_ONLINE_FAST)
    unseen = [f for f in FACTORS if s[f] not in SEEN_LEVELS[s.task][f]]
    if unseen or router_conf(s) < THETA_ROUTE:
        return conservative_mode(s, unseen)
    if s.human.present:
        return hir(obs, s)                 # 定义 117
    return normal(s)

def hir(obs, s):                           # NORMAL→YIELD→WAIT→RESUME/ABORT
    if detect_two_evidence(obs, s):        # 检测器+VQA 双证据，防误触
        hold_joints()                      # 停
        if gripper_loaded() and pulled(s): open_gripper()   # 让物
        while human_present():             # 等清场
            sleep()
        return replan()                    # 恢复：重过 SGT 与子目标
    return normal(s)
```

### IP-112 WMR（世界模型重排，只否决）
```
def wmr_rerank(obs, chunks, state):        # 定义 112
    if eps_W(state.task) > EPS_W_MAX:      # 该任务保真不达标→不开
        return chunks[0]
    picks = []
    for c in chunks:
        fut = world_model.predict(obs, c)  # 未来若干帧
        if fut.predicts_failure(c):        # 抓滑/对位崩/物体消失
            continue                      # 否决：降权丢弃
        picks.append((progress_score(fut, state.plan), c))
    return max(picks)[1] if picks else chunks[0]
```

### IP-116 IFE（异步流水线与步骤预算）
```
class PolicyService:                       # 定义 116
    def __init__(self, model, N_ports):
        self.backend = SharedBackend(model)   # N 端口共享一个后端
        self.queues = [Queue() for _ in range(N_ports)]
    def serve(self, port, obs_queue):      # 每端口：reset/get_action，状态隔离
        while True:
            ev = obs_queue.get()
            if ev.kind == "reset":
                self.state[port] = reset_cognition(ev.obs, ...)   # 慢算在这
                self.prefetch[port] = self.backend(ev.obs, self.state[port])
            else:
                self.queues[port].put(self.prefetch[port])        # 立即返回上块
                self.prefetch[port] = self.backend(ev.obs, self.state[port])  # 异步算下块
```

### IP-118 EDP（锚点闭合与选择校正）
```
def accept_change(chg):                    # 定义 113/114/118
    assert not leaks(chg.data, A_anchor)   # 泄漏审计
    base = eval_on_anchors(current_model, A_anchor)
    new  = eval_on_anchors(candidate_model, A_anchor)
    if base - new > THETA_ANCHOR: return ("reject", new)
    alpha_sel = sqrt(2*(log(len(compared_this_round)) + log(1/BETA))/len(A_anchor))
    if gain(new, base) - alpha_sel <= 0: return ("hold", gain)
    log_ledger(chg, base, new, alpha_sel)  # 入台账；计分跑只约 preregistered 候选
    return ("accept_preregister", gain - alpha_sel)
```

## 5. 复杂度与正确性（比赛版"保证"）

| 组件 | 额外时延 | 存储 | 保证（工程口径，非 soundness） |
|---|---|---|---|
| FSM | reset O(1) 查表；chunk 增量 O(1) | O(格子数) | 覆盖可解释、缺口可定向 |
| AMoA | get_action 与大模型一次前向同阶；合并可忽略 | 基座 1 份+小适配器 | 单模型合规；融合超限即回退单适配器 |
| AGE | 离线一次 | O(\|𝒜\|²) | 只进调度通道；性能声明必须锚点闭合 |
| VQA-Diag | 离线/异步 | 视频+矩阵 | precision/recall 报告后才可信 |
| VQA-Curate | 离线 | 生成池 | 生成集成功率不作接受依据；λ 由锚点定 |
| WMR | chunk 边界/相位切换异步 | 模型权重 | 只否决不批准；ε_W 分任务开关 |
| SGT | 每 chunk 边界 O(1) | 已见水平集 | unknown=out；保守代价有上限监控 |
| RAP | reset() 一次 | 演示索引 | 检索仅作先验，VQA 一致性校验后才进规划 |
| HIR | 触发即停 | 无 | 双证据触发；恢复必须重过绊线 |
| IFE | p50/p99 预算内 | N×小状态 | 端口隔离压测通过；异常值率=0 |
| EDP | 无 | 台账 | 泄漏=∅；增益报告带 α_sel 扣除 |

**竞赛版核心命题（非定理）**：在版本六元组冻结、锚点闭合、选择校正、绊线 conservative 的四重纪律下，160 个格子的平均成功率改进可以被**归因到具体格子与具体因子**，从而把"调参玄学"变成"覆盖-修复-验证"的闭环节奏；任何绕过锚点/预注册/绊线的所谓提升按未验证处理，不计入版本决策。

## 6. 实验设计 E151–E160

| 实验 | 指标 | 门槛 |
|---|---|---|
| E151 FSM 覆盖审计 | 每 (任务,轴) 最小-k 覆盖；缺口清单收敛速度 | 5 轴全部有量化覆盖；高权重缺口 100% 有补数计划 |
| E152 AMoA vs 单LoRA vs 全量FT | 锚点代理集（160 格抽样）平均成功率；任务间负迁移率 | AMoA ≥ 最优基线 +5% 绝对值；负迁移任务数为 0 |
| E153 SGT | OOD 检出/误报/漏报；保守模式格子损失 | 漏报≈0（按 out 兜底）；保守代价 ≤ 该格失败代价的 30% |
| E154 VQA-Diag | 归因 precision/recall vs 人工标注；修复清单命中率 | precision ≥ 0.85；top-5 修复带来 ≥8% 格子增益 |
| E155 VQA-Curate | λ-sweep 锚点收益曲线；生成集-锚点成功率差（留痕） | 存在 λ*>0 且锚点增益显著；无语义破坏样本漏过 |
| E156 WMR | 接触密集任务成功率；中位步数；异步开销 | Plug*/Syringe 类 ≥ +10%；延迟不侵入热路径 |
| E157 HIR | human 格成功率；不安全事件；恢复步数 | 不安全事件 0；恢复步数 ≤ 预算 30%；正常任务误触率 ≤ 2% |
| E158 IFE | p50/p99 延迟；N 端口并发吞吐；1h 漂移；动作异常值率 | p99 < B_step；异常值率=0；1h 无状态泄漏 |
| E159 全流程彩排（门） | 用不计分单任务调试逐任务彩排 32 次 | 每任务中位成功率 ≥ 阈值才允许预约计分跑；方差记录 |
| E160 EDP | 泄漏审计；α_sel 校正前后报告差异；预注册合规率 | 泄漏=∅；所有计入版本的增益均带校正；合规率 100% |

回退策略：E152 负迁移 → 回退单 LoRA 基线并冻结合并；E153 漏报安全方向问题 → 阈值收紧+双证据；E155 生成域差 → λ 降档或只保留高保真轴；E156 世界模型乱否决 → 按任务关闭（ε_W 门）；E157 误触 → 滞回+双证据收紧；E158 延迟/异常值 → 冻结工程配置回退模板参数；E159 彩排不过 → 不约计分跑，回到 IP-110 归因循环；E160 泄漏或违规 → 该版本作废重训，章程记入台账。

## 7. 路线图（相对周；所有"计分跑"节点均在 EDP 门之后）

- W1 规则锚点：飞书手册+邮件问询（步骤分/尝试/是否允许 TTA/N）；模板基线跑通；IFE v0（零动作→单 VLA）。
- W2 XDP v0（统一 schema+一阶段）+FSM v0（覆盖矩阵）+VQA-Diag v0（问题库+校准）。
- W3 AMoA v0（32 任务 LoRA+因子专家）+AGE v0+SGT v0+EDP v0（留出锚点+台账）。
- W4 VQA-Curate v0（按缺口扩增+λ sweep）；WMR v0（ε_W 估计+接触任务开启）。
- W5 HIR v0+ RAP v0；E159 彩排门第一次执行。
- W6–W8 归因-修复循环两轮；预注册第一次计分跑（仅当 W5 门通过）。
- 全程 E160 台账周更；任何规则回音（尤其 W1 问询结果）触发版本六元组重审。

## 8. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 规则未知（步骤分/尝试次数/TTA 许可/N 台异构）颠覆方案经济学 | 高 | W1 规则锚点优先；未闭环不约计分跑；方案按"无需 TTA 也可用"设计 |
| 榜单为空，"头部 <30%"先验错误导致对标失误 | 高 | 所有竞品陈述标注推断；用调试跑自建 per-task 真实基线替代榜单想象 |
| VQA 归因/准入幻觉带偏修复与数据 | 高 | 双证据+人工校准+precision 门槛；低精度问题禁用 |
| 生成数据域差教出偏置策略 | 高 | 单向准入+λ 由锚点定+优先高保真轴；生成集成功率只作留痕 |
| LoRA 合并干扰伤害单任务 | 中高 | ε_merge 门+单适配器回退；负迁移任务记入 AGE 黑名单 |
| SGT 误报把可做格子变保守 | 中高 | 阈值按"保守代价≤失败代价"校准；保守率上报 EDP |
| 接口工程（延迟/并发/状态泄漏）翻车 | 中高 | IFE 压测门+工程配置冻结+README 警告逐条核对 |
| 世界模型/开源模型许可（NC 条款）与比赛合规性 | 中 | 问主办方；必要时替换为自训/宽松许可模型 |
| 异构 fleet 下路由与绊线失灵 | 中 | per-port 状态隔离+每机锚点子集；调试跑轮转覆盖多机 |
| 流程官僚化拖慢迭代 | 中 | EDP 门全自动化；一周一个主假设 |
| 数据许可/存储成本 | 低 | 数据集 apache-2.0 友好；Xet 增量下载；按需取子集 |

## 9. 本轮最大风险

**一句话**：v30 把"泛化"变成了可覆盖、可归因、可 preregister 的工程对象，但整套经济学压在三个未核实的平台变量上（**步骤分公式、是否允许 reset()/测试时重算与在线自适应、评测机数量与异构性**），且榜单为空意味着连"头部到底长什么样"都还没有事实——一旦规则与推断相反，"把重算摊销到 reset()/调试跑"的主线就要重算，因此在下轮抓到"规则锚点"之前，本清单的任何一项都只许进锚点与彩排，不许进计分跑。

**当前最值得押注的创新点（一句话）**：押注 IP-111 × IP-110 × IP-108 组合成的"**VQA 监督的因子化覆盖管线**"——用 VQA 把五类场景变成可记账的五根轴、把失败归因成矩阵、把 LoRA 适配器联邦按轴路由，因为它直接攻击榜单一共计分的那 160 个格子，且全部重算可摊销到 reset() 与不计分调试跑上，是算力约束下唯一"每一分投入都落在计分面上"的打法。
<!-- ARTIFACT:END -->
