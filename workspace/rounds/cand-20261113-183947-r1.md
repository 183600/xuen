# 玄 · 灵感驱动研究循环

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 67 轮（灵感驱动研究循环 · UniBot 主线第 2 轮；本轮灵感词：「人机协作」×「论文创新点」×「零样本泛化」）

> 轮次说明：提示词模板标注「第 1 轮」，按状态文件递增，本实轮为总第 67 轮、UniBot 参赛主线第 2 轮（承接第 66 轮）。清单 v1→v2 只做深化与修剪，不重开。赛事指向无歧义：unibot.unitree.com 官网在线且页面描述与用户给定赛题一致（G1 平台、32 任务、五轴泛化、单模型通才赛道）。

## 0. 本轮检索核实（检索日期 2026-11-13；重点标出与第 66 轮认知的差异）

1. **榜单/运行记录页**：实测仍为 Coming Soon——工作假设 A0（榜首成功率 <30%）维持；无头部方案公开信息可核。
2. **提交仓库重读**（README + example/example_policy.py；仓库最后推送 2026-08-21）确认三个此前未明确的接口事实：
   - `observation.language` 是一等公民：每集任务指令字符串（例 "move the block to the target position."）随 obs 由评测端下发——**策略侧收到后可在喂给模型前自由改写**，协议内置了「语言条件化模式切换」的合法信道；
   - `obs_delta_indices` 支持非连续负偏移（官方示例 [-10,-5,-2,0]）、`image_resize` 可逐相机降分辨率、观测键自选——**带宽与延迟是可调预算**；
   - `action.pivot`[7] 为 shared 必返键；token 每步校验；§6 可信度条款重读确认（逐步延迟与动作统计可随结果公开）。
3. **数据集**：HF 合集 UniBot-V1 Challenge Dataset 确认存在；32 个任务数据集完整点名（HangCup, ArrangePlates, ArrangeTestTubes, ZipUp, Unlock, ColorArrangement, ConveyorSorting, DisconnectEthernet, FoldTowel, FruitCollection, FruitSorting, OrganizeBookshelf, OrganizePencilCase, SpellRobot, OrganizeStationery, StackBowls, StoreCups, OrganizeTools, PackBag, StoreEarphones, PackDoll, PackPhone, StorePaddle, ToolboxStorage, PaperCupStacking, PickOutBatteries, SyringeWaterTransfer, PlugCharger, PlacePhotoFrame, PlugInEthernet, PourOutMedicine, RemovePinnedNote）。抽查：PlugCharger 1022 ep / 463,451 帧 / 30fps；PaperCupStacking 969 ep / 402,646 帧；相机键 head_stereo_left/right + wrist_left/right；**meta/tasks.parquet 存在（语言指令的落点）**，逐集指令文本待下载核对。
4. **新发现 A：Unitree 自家基座模型线已开源**（github unitreerobotics/unifolm-wla README + docs/robot_action_state_processing_en.md；HF models API 实测 8 个模型公开）：**UnifoLM-WLA-1.0-Base**（2026-09-28 放出）——6B 通用人形基座、~2500h 真机数据、单模型 64 任务、支持 Dex1 夹爪、**含微调代码与 LoRA 微调**；官方《动作/状态统一处理规范》定义 54 维统一动作 / 60 维统一状态 / chunk 30 @ 30fps / 1-99 分位归一化，与挑战赛数据（30fps）和提交接口天然对齐；官方开源计划**明确把 UniBot-V1 Challenge Dataset 列为其数据集**——即官方示范的参赛路径就是 WLA-Base + 该数据微调。另有 UnifoLM-ER-1/ER-Flow、**UnifoLM-WMA-0-Base/Dual（world-model 线；HF 实测 gated，需申请权限）**。→ 基座选型从 v1 的「开源 VLA 泛指」收敛为具体候选。
5. **新发现 B：官方 Isaac Lab 仿真**（github unitreerobotics/unitree_sim_isaaclab，2026-11-11 仍在推送）：G1 29-DoF（Dex1 夹爪、固定底座）多任务平台，支持**数据采集/回放/生成/模型验证**，DDS 与真机同构，对接 xr_teleoperate 遥操作采集；现成任务仅 5 个简单 pick&place/stack。→ **v1 把「系统在环预演台」押给 Gazebo 的定位被 Isaac Lab 覆盖**：更官方、同构、自带回放与模型验证；Gazebo 降级为第三引擎（仅服务多引擎分歧探针 C07）。
6. **文献核实（arXiv API，本轮全部验证）**：失败恢复是 2026 下半年热点簇——RACER 2409.14674（语言引导失败恢复）、LIBERO-RECOVER 2609.05178、Recova 2610.01178、Human-in-the-Loop Failure Recovery in HRC 2609.24055、Causal-History Test-Time Scaling（自回归世界-动作模型恢复）2609.18016、FRAMES 2609.22538、Which Hand Was Late? 2610.37533（双臂失败诊断）。**UniBot 人扰轴恰是该簇的真机考场，接口 language 字段恰是 RACER 式语言恢复的现成入口。** 修正：MimicGen 正确编号 2310.17596（v1 误记 2310.16007）；RoboCasa 2406.02523 复核无误；GemBench 检索不到，弃用该名。
7. 规则手册（飞书）仍需登录；「DAPTO 2」仍无公开技术报告。

## 1. 直觉与动机（三个灵感如何合流）

**灵感 1（人机协作）：「隐性协作痕迹」与「显性人扰轴」是同一枚硬币的两面。** 第五轴把 HRC 写进评分；但 32,000 条演示本身就是大规模人机协作的产物——遥操作者在演示里留下了纠错痕迹（夹空后重抓、接近失败后回撤再抓、放置偏了重新对位）。这些段落被常规 BC 当噪声平均掉，却是评测最稀缺的数据类型：**带真机分布的恢复演示**。第二个馈赠在协议里：评测端每步下发 `observation.language`，策略侧可改写后喂模型——官方把「人给机器人下达恢复指令」的信道做进了接口。人扰轴的解法因此从「扰动数据增广」升级为「演示挖恢复（RecoMine）× 语言条件恢复 × 仿真拟人扰动（HumanPerturber）」三源合一，前两源近乎免费。

**灵感 2（论文创新点）：用文献坐标系给清单做新颖性审计，把参赛系统凝练成一个可证伪主张。** 审计结果：失败恢复簇证明「恢复」有学术市场，但 RACER 假设恢复数据已标注、LIBERO-RECOVER 限于仿真、Recova 靠 agent 生成——**「从人类遥操作演示中挖掘隐性恢复段」在检索范围内未见先例**，是可发表差异点；MimicGen/RoboCasa 程序化增广成熟，我们的差异仍在「以官方演示为真值源 + 信任门控」（TwinCal）；SIMPLER 是「仿真评真策略」，DryRun 门是其参赛特化。审计同时修剪：PortFleet 不构成论文主张、证书类想法继续不碰。凝练主 claim：「固定基座 + 固定数据预算下，**信任门控的三源数据分配**（语义保持×语义扩张×交互恢复）决定零样本泛化分数，而非架构创新」。

**灵感 3（零样本泛化）：五轴 = 两种零样本杠杆，都不是「堆数据」能单独解决的。** 四个场景轴是零样本视觉-语义条件，失败机制有二：训练分布没盖住（→语义扩张：资产变体 C02③、真机像素反事实编辑 C12、场景编译 C01），或**预训练先验被 32k 窄分布微调磨掉**（→语义保持 C13：LoRA + 分域冻结视觉塔 + 回放正则；32k 规模恰小到足以灾难性遗忘，而 WLA-1.0-Base 的语义先验是最大免费资产）。接口侧 language 字段还让未见物品可借语义指代（"把左边那个罐子…"）——提示工程是零样本轴的免费杠杆。结论：**零样本泛化在此语境下主要是「先验保持 + 训练分布设计」问题，不是架构问题。**

**合流 → 本轮核心命题：**
> **UniBot 的零样本五轴是「三源数据杠杆」问题：语义保持（C13 SemLock）× 语义扩张（C12 CounterFact + C02 资产变体）× 交互恢复（C11 RecoMine + C04 仿真扰动 + C08 语言条件恢复）；三源全部经 C02 TwinCal 信任门控进入统一课表（C03）。基座收敛到 UnifoLM-WLA-1.0-Base，官方 Isaac Lab 仿真替换 Gazebo 成为预演台。**

## 2. 从第 66 轮继承什么、深化什么、修剪什么（修剪清单）

- **深化 C01**：主后端 Gazebo→**官方 unitree_sim_isaaclab**（同构 DDS + 自带回放/模型验证）；MuJoCo 仍为接触工厂；Gazebo 降级为第三引擎。
- **深化 C02**：资产变体具体化为「affordance 保持的外观强随机 + 几何容差内变形」，直接服务未见物品轴。
- **深化 C04**：升级为「检测（工作区视觉变化+本体抖动）→ 分类（拟人扰动原语）→ 恢复（语言条件子策略）」闭环，标签空间与 C11 共享。
- **深化 C05**：基座收敛为 **WLA-1.0-Base 首选**（同机器人/同数据格式/官方 LoRA 管线），π0/OpenVLA 为对照。
- **深化 C08**：恢复技能经语言条件注入而非独立策略头；与 test-time recovery 文献（2609.18016）挂钩。
- **降级 C07 CrossPhys** → 可选探针（共模失真 + 验证成本；只做 2 任务，相关性 <0.3 即砍）。
- **标记 C09 PortFleet**：纯工程必做项，不占创新预算、不作论文主张。
- **新增 C11 RecoMine、C12 CounterFact、C13 SemLock**（见产物区）。
- 继续不做：证书体系 / 形式化安全（第 66 轮已修剪，维持）。

## 3. 本轮最大风险

**一句话**：两个新押注都悬在「官方资源与我们的假设是否对得上」——(a) RecoMine 假设 32k 演示含可挖掘恢复段，若数据被清洗得太干净则产出趋零，交互恢复退回仿真单源；(b) SemLock 假设 WLA-1.0-Base 先验可经 LoRA 保持，但 head_stereo↔cam_*_high 的相机映射与 54 维动作适配未验证，基座红利可能打折。两者都有第一周廉价验证（抽样 100 条演示做段挖掘统计；WLA-Base 空载前向联调），风险可在一周内定价。

（次级风险延续 v1：A0 未校准、柔性物孪生不达标、N 端口并发。）

**当前最值得押注的创新点：IP-C11 RecoMine——把「人机协作」的隐性痕迹（遥操作者的纠错动作）变成唯一交互轴的免费真机恢复数据，与 2026 失败恢复文献簇严丝合缝地接口，且第一周就能抽样定价其上限；即使产出低于预期，挖掘管线本身就是数据质量审计，不白做。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 67 轮产物 · UniBot 参赛创新点清单 v2（人机协作 × 论文创新点 × 零样本泛化；IP-C01~C13）

> 清单说明：v1（第 66 轮，IP-C01~C10）→ v2 diff：深化 5（C01/C02/C04/C05/C08）、降级 1（C07→探针）、标记 1（C09 纯工程）、新增 3（**C11/C12/C13**）。C03/C06/C10 保留微调。本清单为持续迭代对象，后续只做深化与修剪。
> 信息来源（检索日期均为 2026-11-13）：unibot.unitree.com（首页/榜单页实测 Coming Soon）；github.com/unitreerobotics/unibot_submission（README + example/example_policy.py，最后推送 2026-08-21）；HF API（作者数据集清单与 UniBot-V1 Challenge Dataset 合集；G1_Dex1_PlugCharger / G1_Dex1_PaperCupStacking 的 meta/info.json；meta/tasks.parquet 存在性）；github.com/unitreerobotics/unifolm-wla（README + docs/robot_action_state_processing_en.md）+ HF models API（8 个 UnifoLM 模型公开，WMA-0 实测 gated）；github.com/unitreerobotics/unitree_sim_isaaclab（README，2026-11-11 推送）；arXiv API 验证：RACER 2409.14674、LIBERO-RECOVER 2609.05178、Recova 2610.01178、2609.24055、2609.18016、FRAMES 2609.22538、2610.37533、MimicGen 2310.17596（纠正 v1 误记的 2310.16007）、RoboCasa 2406.02523。规则手册（飞书）仍需登录；「榜首 <30%」维持工作假设 A0。

## 0.5 头部方案画像与瓶颈推断（A0 下，供对位）

榜单未公开（今日实测 Coming Soon）。若 A0 成立（榜首 <30%），最可能的失败质量分布：
- **任务记忆不缺**：32k 演示 + 基座预训练足以让「训练分布内」成功率不低；
- **失分主体一：未见物品/背景轴**——VLM 语义先验被窄分布微调磨掉（灾难性遗忘），抓取点与语义对齐失效；
- **失分主体二：人扰轴**——演示里没有恢复段，扰动后策略一路错到底，成功率与步骤分同损；
- **失分主体三：接触精密/柔性任务**——物理难度，与泛化无关（PlugCharger/SyringeWaterTransfer/FoldTowel/PackBag）。
v2 的三个新增 IP（C13/C12/C11）恰好对准前两个失分主体；C02/C10 管第三个。**榜单公开后的第一件事：按任务×轴分解的公开分数重排本矩阵，并校准 C03 课表先验。**

## 0. 机会矩阵 v2

| 评测轴/约束 | 性质 | 主杠杆（v2） | 主攻 IP |
|---|---|---|---|
| 位置变化 | 场景级 | 场景编译 + 演示分布匹配 | C01/C02/C03 |
| 干扰物 | 场景级 | 场景编译 + 资产变体 | C01/C02 |
| 桌面背景 | 场景级（渲染） | Isaac 渲染 + 反事实观测编辑 | C01/C12 |
| 未见物品 | 场景级（资产+语义） | 资产变体 + 语义保持 + language 指代 | C02/C12/C13 |
| 人为干扰 | 交互级 | 挖掘恢复段 + 语言条件恢复 + 仿真扰动 | C11/C04/C08 |
| 接触精密/柔性 | 物理级 | 真机数据为主，trust 圈定可信域 | C02/C10 |
| 先验保持（横切） | 训练级 | LoRA + 分域冻结 + 回放正则 | C13 |
| 接口/部署/可信度 | 工程级 | — | C06/C08/C09 |

## 1. 创新点清单 v2（每点：动机 / 差异 / 可行性 / 资源 / 落地步骤 / 风险）

### IP-C01 ScenarioForge v2【v2 深化：后端换 Isaac Lab 优先】
- **动机**：五轴中四轴是场景噪声；训练分布不覆盖评测分布则泛化必然失败。把「收集更多数据」改成「编译目标场景」。
- **差异**：v1 双后端（Gazebo+MuJoCo）改为 **Isaac Lab（主，官方 unitree_sim_isaaclab：G1 29-DoF、Dex1、固定底座、采集/回放/生成/模型验证一体、DDS 同构真机）+ MuJoCo（接触工厂，menagerie G1）**；Gazebo 降级为可选第三引擎。SceneSpec DSL 不变：任务模板/物体集/位姿分布/材质/光照/相机内外参/人扰事件为一等参数，评测五轴可编译。
- **可行性**：高。官方 URDF→USD 转换与回放基础设施现成，桌面任务无需行走。
- **资源**：1–2 人周起步；Isaac 渲染单卡 4090 级；无真机依赖。
- **步骤**：①SceneSpec 定义 ②Isaac Lab 任务模板扩展（官方 5 个简单任务→32 任务模板）③与 LeRobot 数据打通做重放对比 ④每任务×5 轴网格采样生成评测套件（供 C10 预演门）。
- **风险**：腕部小图（128×128 请求分辨率）的渲染-真机域差；资产外观差异（→C02 验收）。

### IP-C02 TwinCal（v1 押注维持：数据集驱动的数字孪生标定与验收）
- **动机**：32,000 条演示是免费真值源（初始位姿分布、桌面几何、相机外参、物体集合）；仿真必须「先对齐、后加宽」才可信。
- **差异**：把对齐质量量化为每任务「仿真信任度」标量（真机动作开环重放误差），低于阈值即禁用该任务仿真增广——预算自动流向可信任务。
- **可行性**：中高。刚体任务 CAD 检索+重纹理起步；柔性物（FoldTowel/PackBag）先标「仿真不信任」。
- **资源**：1–2 人月；少量重建算力；无需真机。
- **步骤**：①每任务抽 ~50 条演示统计初始分布与桌面几何 ②重投影估计相机外参（同时产出 C12 需要的多视角外参！）③资产库：**affordance 保持的外观强随机 + 几何容差内变形**（服务未见物品轴）④开环重放验收→trust∈(0,1) ⑤trust 作为 C01 采样与 C03 课程权重。
- **风险**：柔性物无法刚体化（退到 C10/C12 视频路线）；重放误差含策略闭环效应（只用前 2s 开环段+多次重放取中位）。

### IP-C03 Axis-Bandit（保留微调）
- **动机/差异**：按「任务×泛化轴」二维边际成功率分配训练采样；每次真机评测槽当 bandit 反馈（Thompson 采样）。v2 补充：榜单公开后用公开分数直接替换先验。
- **可行性/资源**：高；无额外数据，少量评测槽。
- **风险**：评测只给总分则退化为 A0 静态配比；评测槽稀缺（仿真 DryRun 套件先行离线课程）。

### IP-C04 HumanPerturber v2【v2 深化：检测-分类-恢复闭环】
- **动机**：唯一交互轴；仿真里可无限次「被干扰」。
- **差异**：v2 升级为闭环——**检测**（工作区视觉变化检测 + 本体速度抖动 + C08 残差门并联）→ **分类**（拟人扰动原语库：推物/抽物/挡相机/碰手臂/换目标位，按任务阶段触发）→ **恢复**（语言条件子策略，与 C11 恢复段共享标签空间）；扰动-恢复配对数据自动生成并带特权真值重标注。
- **可行性**：中；脚本化扰动起步，学习型对抗进阶。
- **资源**：脚本 1–2 人周；数据生成复用 C01/C02 管线。
- **风险**：仿真人扰与真人差异大（参数放宽 + DryRun/真机槽校准）。

### IP-C05 SimDistill v2【v2 深化：基座收敛 WLA-1.0-Base 首选】
- **动机**：仿真特权状态训高成功率教师；学生只看接口允许的 4 路 RGB+本体，直接对齐提交格式。
- **差异**：v2 基座从「开源 VLA 泛指」收敛为 **UnifoLM-WLA-1.0-Base 首选**——同机器人（G1/Dex1）、同数据格式（LeRobot 30fps、54/60 维统一动作/状态规范、chunk 30@30fps）、官方微调+LoRA 代码，且官方已示范以 UniBot-V1 数据微调；π0/OpenVLA 为对照基座。数据三源：真机演示+信任门控仿真增广+恢复段（C11/C04）。
- **可行性**：高，工程量在适配器（head_stereo↔cam_*_high 映射、54 维↔接口 7/6 维映射）。
- **资源**：训练 8×A100 级×1–2 周；部署目标 24G 显存内量化（6B 需验证）；WMA-0（世界模型支线）gated 需申请。
- **步骤**：①第一周空载联调（规格映射验证）②教师仿真 BC/RL ③学生三源联合微调（叠加 C13 语义保持）④按 C03 权重迭代。
- **风险**：规格映射隐藏错位（头号工程风险，第一周定价）；教师-学生鸿沟在腕部遮挡处最大（多视角一致性损失+C06 深度辅助）。

### IP-C06 StereoPrior（保留）
- 免费度量深度：数据集头部为已矫正立体对，接口送左右头部两路图——仿真立体对+完美视差 GT 训轻量匹配头，SGBM 兜底；深度作学生辅助特征/抓取点预筛选/C12 编辑的几何引导；失败静默降级回 RGB。单卡数天，<5ms/帧。风险：弱纹理/高光（只作辅助）。

### IP-C07 CrossPhys【v2 降级：可选探针】
- 同一 SceneSpec 跨 Isaac/MuJoCo/Gazebo 三引擎的行为分歧=迁移风险代理，作训练样本权重与预演告警。v2 只做 2 任务验证「分歧↔迁移损失」Spearman ≥0.5 保留、<0.3 即砍；共模失真（共享错误 URDF/资产）由 C02 资产级不确定性单独覆盖。

### IP-C08 SalvageChunk v2【v2 深化：语言条件恢复注入】
- **动机**：步骤分奖励部分进展；块长摊薄推理调用但扰动后块内无效步≈k/2（命题 2，第 66 轮）。
- **差异**：v2 恢复技能不再走独立策略头，而是**经 observation.language 注入**（策略侧改写指令串，如追加 "[mode: recover:re-grasp]"）——协议合法、零架构改动、与 C11/C04 标签空间统一；并与 test-time recovery 文献（arXiv 2609.18016）对话。迟滞防振荡维持（短块最小持续 8 步）。
- **可行性/资源**：高；复用 C05 管线。
- **风险**：频繁截断降成功率（迟滞缓解）；prompt 切换对基座的行为影响需 DryRun 验证。

### IP-C09 PortFleet【v2 标记：纯工程必做项，不作论文主张】
- N 端口（8765 起）并发服务：单 GPU 共享后端+轻量网关、跨端口动态批+锁步定长稳定延迟、每端口独立 reset/历史隔离、量化控显存、熔断+安全停机回退。服务 §6 可信度条款（延迟平稳、动作规整）。1 台高显存服务器、1–2 人周。

### IP-C10 SimDryRun（保留；反事实增广迁出至 C12）
- (a) 提交前用同一 PolicyService 在仿真五轴套件上回归（接口/延迟/成功率三项门），把「提交即评测」变成「提交前已知分数区间」；Isaac Lab 官方「模型验证」能力直接承接。(b) v2 起 C10 只保留柔性物兜底的总括角色，具体增广管线归 C12。风险：DryRun 分布与真实评测分布有差（A0）——C03 真机反馈持续校准。

### IP-C11 RecoMine【v2 新增 ★ 本轮押注：从官方演示中挖掘隐性「干预-恢复」段】
- **动机**：BC 把演示里的纠错段当噪声平均掉，而评测最缺的就是真机恢复数据；32k 演示是唯一免费且带真机分布的恢复源（若存在）。遥操作者就是第一位「协作干预者」。
- **差异**：RACER（2409.14674）假设恢复数据已标注；LIBERO-RECOVER（2609.05178）限仿真基准；Recova（2610.01178）靠 agent 生成——**检索范围内（2026-11-13）未见「从人类遥操作演示中挖掘隐性恢复段」的先例**；挖出段自带 G1 真机分布，零 sim2real。
- **可行性**：中。段检测启发式（夹爪-接触一致性、末端运动方向反转、放置前二次对位）+人工抽检；产出量未知（头号风险）。
- **资源**：单卡数天；无需真机、无需仿真。
- **步骤**：①全 32 任务抽 ~5% episodes 人工标注「是否存在纠错段」（先定价挖掘上限，1–2 天）②启发式段检测器（三通道：夹爪开合×接触一致性 / 末端速度方向反转 / 二次对位）③检段打恢复类型标签（re-grasp/retreat/re-align/re-place，与 C04 原语库共享）④运动学可行域过滤（关节限位/速度上限）⑤喂 C08 语言条件恢复头训练。
- **风险**：演示太干净产出趋零（先做①再投入；退路：C04 仿真扰动单源）；挖掘段含人因动作偏差（可行域过滤）；段边界噪声（前后各留 1s 上下文）。

### IP-C12 CounterFact【v2 新增：真机像素的多视角一致反事实观测编辑】
- **动机**：未见物品+背景轴的视觉零样本失分；仿真渲染真实感不足（腕部 128×128 尤甚）；在真机演示帧上生成式编辑保真实感，且只改观测、不动动作标签。
- **差异**：RoboCasa/MimicGen 在仿真里换场景；SIMPLER（2405.05941）反方向（仿真评真策略）；本点做**多视角一致**（四路相机同时编辑）：TwinCal 外参把 3D 编辑意图投影到各视角 mask + C06 深度引导修复 + 光流时序平滑。
- **可行性**：中。静态帧编辑成熟；四视角+时序一致是主要工程风险。
- **资源**：生成式算力（inpainting 单卡）；分割掩码自动化（SAM 类工具，记忆未复核）。
- **步骤**：①每任务选 200–500 关键帧 ②分割掩码 ③3D 编辑意图（换物/换背景/换光照）→多视角投影掩码 ④深度引导修复 ⑤一致性过滤（重投影误差+光流）⑥过 C10 DryRun 回归验收后入库。
- **风险**：伪影带偏策略（严格过滤+DryRun 验收）；四视角一致性不足时退化为只增广头部两路（腕部留给仿真）。

### IP-C13 SemLock【v2 新增：语义保持微调，护住基座零样本先验】
- **动机**：32k 窄分布微调会磨掉基座语义先验（未见物品/背景轴的失效机制）；WLA-1.0-Base 的语义先验是最大免费资产。
- **差异**：常规微调全参数；本点把「零样本轴保持」显式作为训练约束：LoRA（官方管线现成）+ **视觉塔分域冻结**（头部塔全冻——与 VLM 预训练分布近；腕部塔解冻末 k 层——视图差异大需适应）+ 预训练分布回放正则（公开图文对）+ 模型选择准则改为「C10 DryRun 未见物品/背景套件优先」而非训练任务成功率。
- **可行性**：高（WLA 官方 LoRA 代码直接承载）。
- **资源**：与 C05 共用训练预算，增量近零。
- **步骤**：①分域冻结小网格（3 配置）②回放正则（KL 对冻结基座）③模型选择换零样本套件④对照全微调消融（E-C11）。
- **风险**：过度冻结伤接触任务视觉特征（腕部适度放开）；回放语料可得性（公开图文对替代）；若命题 4 预言不成立（倒 U 不存在）则降级为普通正则。

## 2. 关键伪代码

```python
# IP-C11 RecoMine：从遥操作演示中挖掘隐性「干预-恢复」段（单卡可跑）
RECOVERY_LABELS = ['re-grasp', 'retreat', 're-align', 're-place']

def mine_recoveries(ep):                       # ep: LeRobot 单条演示（30fps）
    segs = []
    for t in range(1, len(ep)):
        c_grip = grip_contact(ep, t)           # 夹爪开度 × 末端速度的接触一致性
        reversal = dot(v_ee(ep, t-1), v_ee(ep, t)) < -0.5   # 末端运动方向反转
        if (c_grip == 'closed_on_air' or reversal) and stable(ep, t, w=15):
            segs.append((t - 30, t + 60))      # 前后各留 1s 上下文
    return [(label_segment(ep, s), s) for s in segs]   # 启发式打恢复类型标签
# 产出：每任务「恢复段库」→ 与 C04 扰动原语共享标签空间 → C08 语言条件恢复头
```

```python
# IP-C08 + C11：调用时刻自适应分块 + 语言条件恢复（协议允许策略侧改写 language）
class AdaptiveChunkPolicy:
    K_LONG, K_SHORT, HYST = 24, 6, 8
    def get_action(self, obs):
        s = self.tracker.update(obs)                   # 便签级世界状态
        r = self.residual_gate(s)                      # conformal 残差门（第 66 轮）
        if r > self.q_alpha or self.detector.interfered(s):    # C04 检测器并联
            skill = self.recovery_lib.match(s)         # C11 真机段 / C04 仿真段
            lang = obs['observation.language'] + f' [mode: recover:{skill}]'
            k, A = self.K_SHORT, self.policy(obs, lang=lang, k=self.K_SHORT)
        else:
            k, A = self.K_LONG, self.policy(obs, lang=obs['observation.language'], k=self.K_LONG)
        self.steps_in_mode += 1                        # 迟滞：短块至少持续 8 步
        if self.steps_in_mode < self.HYST: k = min(k, self.last_k)
        self.last_k = k
        return {**format_actions(A[:k]), 'meta.token': self.token}
```

```python
# IP-C13 SemLock：语义保持微调（WLA-1.0-Base 官方 LoRA 管线之上）
def train_step(batch, lora, towers):
    loss_task = flow_matching_loss(model_lora(batch.obs, batch.lang), batch.actions)
    replay = vlm_replay_batch()                        # 预训练分布图文对（公开语料）
    loss_lock = kl(model_lora(replay), frozen_base(replay))    # 先验锚定
    for p in towers['head'].parameters():  p.requires_grad_(False)   # 头部塔全冻
    for p in towers['wrist'][-k:].parameters(): p.requires_grad_(True)  # 腕部塔末 k 层解冻
    (loss_task + λ_replay * loss_lock).backward()
    # 模型选择：以 C10 DryRun「未见物品/背景」套件为准，不看训练任务成功率
```

```python
# IP-C12 CounterFact：多视角一致的反事实观测编辑（只改观测，不动动作标签）
def counterfact(ep, t, edit3d):        # edit3d: {'obj':'swap', 'bg':'kitchen', 'light':'warm'}
    masks = {cam: segment(ep[cam, t]) for cam in CAMS}          # SAM 类分割（记忆未复核）
    proj  = {cam: project(TwinCal.extrinsics[cam], edit3d) for cam in CAMS}  # TwinCal 外参
    for cam in CAMS:   # 四路一致：同一 3D 编辑投影到各视角
        ep[cam, t] = depth_guided_inpaint(ep[cam, t], mask=masks[cam] | proj[cam],
                                           depth=StereoPrior.depth(cam, t))
    return temporal_smooth(ep, t)      # 光流跨帧平滑；过 C10 DryRun 回归才入库
```

## 3. 两条新命题（命题 1/2 见第 66 轮，继续有效）

**命题 3（恢复段的分数价值）**：设无恢复能力时任务「干净」成功率为 S_c，单次试验观测到人为干扰的概率 P_int（组织者主动制造干扰，P_int 接近 1），干扰后无恢复即失败。引入恢复策略（恢复成功率 ρ）后：S = S_c·(1 − P_int·(1−ρ))，期望增益 ΔS = S_c·P_int·ρ。当 S_c≈0.5、P_int≈1 时，把 ρ 从 0 提到 0.6 即 +15pp 平均成功率——相对 A0（榜首 <30%），这一单项即可再造半个榜位。步骤分同向：恢复把「中途中止」转为「继续推进」，步骤分增量 ≥ 恢复步数。推论：人扰轴是五轴中**性价比最高**的提分轴（数据近乎免费：C11 挖掘 + C04 仿真），应最先做通。

**命题 4（语义保持的约束形式与可检验预言）**：把微调建模为带先验锚定的正则问题 min_θ L_task(θ) + λ·D(θ, θ0)。全微调等价 λ→0（任务上限高、零样本轴漂移大），冻结等价 λ→∞（反之）。LoRA 把漂移自由度压进低秩子空间（结构锚定），回放正则提供分布锚定。**可检验预言**：DryRun 未见物品套件成功率随 λ 呈倒 U，且峰值点对应的训练任务成功率损失 ≤2pp；若预言不成立（无倒 U 或峰值损失大），说明失分主要不是遗忘，C13 降级为普通正则。

## 4. 实验设计 E-C01~E-C12（v2 修订：E-C05 缩小、E-C08 换基座对照，新增 E-C09/10/11）

| 实验 | 核心问题 | 设置 | 指标 | 目标 |
|---|---|---|---|---|
| E-C01 TwinCal 验收线 | 哪些任务仿真可信 | 32 任务×50 演示开环重放 | 重放误差/trust | 刚体类 ≤2cm/5° 达标 ≥80%；柔性物正确标不信任 |
| E-C02 五轴增广逐轴消融 | 每轴值多少分 | DryRun 上逐轴打开增广 | 分轴成功率 | 位置/干扰/背景 +15pp；未见物品次之 |
| E-C03 恢复源消融（v2） | 恢复数据来源谁更强 | 纯 C04 仿真 vs 纯 C11 挖掘 vs 混合 | 干扰轴成功率/步骤分 | 混合最优；C11 单源 ≥ C04 单源 |
| E-C04 立体深度增益 | 免费深度值多少 | RGB-only vs +StereoPrior | 抓取点误差/成功率 | 误差 −30%，高光不劣化 |
| E-C05 CrossPhys 探针（v2 缩小） | 引擎分歧能否预测迁移 | 2 任务×3 引擎（Isaac/MuJoCo/Gazebo） | 分歧↔实测损失 Spearman | ≥0.5 保留；<0.3 即砍 |
| E-C06 DryRun 一致性 | 预演能否预测真机分数 | DryRun 预测 vs 真机槽 | 每任务成功率误差 | ≤10pp |
| E-C07 PortFleet 延迟 | 并发是否平稳 | N=3 并发评测全流程 | p50/p99 延迟、REJECTED | p99 ≤ 2×p50；REJECTED=0 |
| E-C08 基座与分块 A/B（v2） | 基座/块策略选型 | WLA-1.0-Base vs π0/OpenVLA ×（固定块 vs 自适应块） | 成功率/步骤分/延迟 | 自适应步骤分 ≥ 固定；WLA 综合最优 |
| E-C09 RecoMine 产出与质量（新） | 演示里到底有没有恢复段 | 全 32 任务抽 ~5% episodes 人工标注 + 挖掘器抽 50 段人工核 | 纠错段存在率 / 挖掘 P/R | 每任务 ≥20 段、P ≥0.6；存在率 <5% 则砍 |
| E-C10 CounterFact 收益（新） | 反事实编辑值多少 | 增广前后 DryRun 未见物品/背景轴 | 分轴 Δ + 伪影率（人工抽检 100 帧） | 未见物品 +10pp 且背景轴不降 |
| E-C11 SemLock 消融（新） | 语义保持是否兑现 | 全微调 vs LoRA vs LoRA+回放 | DryRun 零样本套件 + 训练任务成功率 | 零样本轴 +8pp 且训练任务损失 ≤2pp（命题 4） |
| E-C12 language 恢复切换（新，并入 E-C03 观测） | prompt 注入恢复模式是否改变行为 | 同状态带/不带 [mode: recover:*] | 恢复成功率差 | 显著正差；否则退回独立恢复头 |

## 5. 风险表与资源总账（v2）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 演示太干净，RecoMine 产出趋零（本轮头号新风险） | 高 | E-C09 步骤①先定价再投入；退路：C04 仿真扰动单源 |
| WLA-1.0-Base 规格映射错位（head_stereo↔cam_*_high、54 维动作适配、量化显存） | 中高 | 第一周空载联调定价；π0/OpenVLA 对照兜底 |
| 柔性/插拔任务孪生不达标（v1 遗留） | 高 | trust 门禁用仿真；真机+C12 视频反事实兜底 |
| 榜单未公开、评测配比未知（A0） | 高 | C03 bandit 在线纠偏；榜单公开即校准 |
| 生成式编辑伪影带偏策略（C12） | 中 | 深度引导+一致性过滤+DryRun 回归验收 |
| WMA-0 gated 未获权限 | 低 | 只影响世界模型支线（C10 反事实 rollout 候选），主线不依赖 |
| 规则手册细则未公开 | 中 | 预约评测槽前邮件确认 challenge_support@unitree.com |
| 资源：训练 8×A100×1–2 周；部署 1 台高显存服务器（6B 量化后单实例 ~24G 内待验证）；仿真 Isaac 单 4090 起步；人力 2–3 人 | — | 按 C03 边际收益动态增减 |

## 6. 论文主张映射（灵感「论文创新点」的落实）

| 主张 | 证据（实验） | 新颖性依据（检索 2026-11-13） | 风险 |
|---|---|---|---|
| 主张 1：信任门控的仿真数据分配（trust 圈可信域→课程/采样） | E-C01/E-C02 | MimicGen 2310.17596 / RoboCasa 2406.02523 无「以官方演示为真值源+验收线」的分配机制；SIMPLER 2405.05941 方向相反（仿真评真） | 低 |
| 主张 2：从人类遥操作演示挖掘隐性恢复段 | E-C09/E-C03 | RACER 2409.14674 假设恢复数据已标注；LIBERO-RECOVER 2609.05178 限仿真；Recova 2610.01178 靠 agent 生成；检索未见演示挖掘先例 | 中（产出量） |
| 主张 3：语义保持微调决定 VLA 零样本轴 | E-C11 | 持续学习常识充分，但在 VLA 操作+比赛语境的完整证据链空缺 | 中 |
| 主张 4：延迟-反应权衡下的自适应块长+语言条件恢复 | E-C07/E-C08/E-C12 | 工程性强，宜作系统论文一节或 workshop；与 2609.18016（test-time recovery）对话 | 低 |
| 非 claims：PortFleet（工程）、StereoPrior（辅助消融）、CrossPhys（探针） | — | — | — |

## 7. 一句话押注

**当前最值得押注：IP-C11 RecoMine——它把「人机协作」的隐性痕迹（遥操作者的纠错动作）变成五轴中唯一交互轴的免费真机恢复数据，与 2026 年失败恢复文献簇（RACER / LIBERO-RECOVER / Recova）严丝合缝地接口，第一周就能用抽样定价其上限；即使产出低于预期，挖掘管线本身就是数据质量审计，而 C13 SemLock 与 C12 CounterFact 两个新增支点仍独立成立。**
<!-- ARTIFACT:END -->
