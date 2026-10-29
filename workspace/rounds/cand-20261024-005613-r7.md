# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 7 轮 · PILOT：放置是闸门，少样本是上下文，产学研是数据农场

> 检索/复核日期：2026-10-24（UTC）。赛事身份确认不变：用户所指是宇树科技的 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1、32 项桌面任务、通才单模型赛道、选手自部署 + 官方远程真机 API 评测。本轮三个灵感词是「产学研合作」「少样本学习」「放置」。我先各自钉到本轮核实到的官方事实上，再合成主判断：**评测的最后一公里（终局放置/终局操作）同时是成功率的闸门和步骤分的大头，而且它跨全部 5 个泛化轴同时起作用；用"少样本上下文 + 放置位姿迁移"去攻它，比继续在单个泛化轴上抠点更划算；产学研则是把外部实验室变成背景/位置轴的补数据农场和样本高效的验证回路。** 上一轮（FLEET-GPR，评 6.0 被拒）的教训也在这里：把部署工程当工程保留，研究火力重新集中到与评分结构对齐的能力上。

## 0. 本轮先核实：七个新事实

### 0.1 32 个任务的评分步骤与权重已经全部公开

所有 32 个任务的 `tasks_v2/<slug>/info.json` 都在 `score_steps` 字段里给出了逐步分值，且满分统一 100。我抓全了 32 个文件（[S2]），合计 3200 分。用关键词分类做粗统计：

- **终局步骤合计 1275 分，占 39.8%**；每个任务的成功闸门都是终局步骤（成功=所有步骤完成）。
- **放置/插入/堆叠/闭合/倾倒类步骤合计约 1910 分，占 59.7%**（粗略分类）。
- 32 个终局步骤里，28 个是放置/插入/堆叠/闭合类动作；另外 4 个（T05 拔出网线、T11 挑出电池、T12 翻金属环、T14 倒药）是拔出/取出/翻转/倾倒类终局操作——它们的前置步骤里同样有大量放置动作。
- 难度分布：12 Easy / 12 Medium / 8 Hard。步骤数 2–5 个。

这比上一轮的认知前进了一大步：以前我们知道"有步骤分"，现在知道**哪一步值多少分**。T27 StackBowls 的 30/30/40、T07 PlacePhotoFrame 的 30/30/40（抓 30、开支架 30、摆正 40）、T10 PlugCharger 的 30/30/40（抓插排、抓插头、插入）全部可见。**"摆正"、"插入"、"堆叠"这些终局动作正是模型现在最容易丢分的地方（对应占位榜的成功分与步骤分之差）。**

### 0.2 每条指令在数据集里带 5 条英文复述

我下载了 HangCup / StackBowls / ZipUp / PlugCharger 的 `meta/tasks.parquet`（[S4][S5]），每个任务的 task 字段是 5 条复述用 `@` 连接，例如 HangCup：`Hang the cup on the marked spot ... @ ... marked position ... @ Hook the cup onto ... @ ... at the marked place ... @ ...`。这回答了第 5 轮开放问题（"语言用几条复述？"）：**评测很可能在这些复述里采样**，语言鲁棒性有明确的 5 条先验。对"评分步骤图"的字符串匹配要覆盖全部 32×5=160 条。

### 0.3 数据集已经扩容到约 33k（2026-10-14 前后）

本轮实测：`unibot-v1-challenge-dataset` collection 的 32 个数据集每个 969–1,530 条，HangCup 1,043 条 / 194,564 帧；HangCup 数据集 `lastModified` 为 **2026-10-14**（[S3][S4]）。对照 2026-08-18 一篇社区帖子还在质疑"HangCup 只有 44 条、数据又小又不均，是不是要等全量发布"（[S29]）——现在可以确认：**全量发布已经落地**（每个任务约 1k 条、约 30fps、head stereo ×2 + wrist ×2 四路相机、EE 位姿在 base 与 torso 两套坐标里都有）。第 5 轮的"33k"判断保持成立，且时间线清楚了：这是最近两周发生的事。

### 0.4 人类干扰与未见物体条件有逐任务公开备注

每个任务的 `info.json` 的 `generalization` 字段直接写明了 `human_1_note`、`human_4_note`、`unseen_object_3`（[S2]）。例如：

- T27：human_1 =「把粉色碗向下移动」；human_4 =「叠了第二个之后拿下第二个」（先叠后撤=undo）。
- T19：human_1 =「把包向左边移动」；human_4 =「拉上拉链之后拉开」。
- T14：human_1 =「拧开盖子之后拧动回来」；T17：human_4 =「笔盒合上之后手动打开」。
- T24：human 备注 =「可乐/薯片快到了然后放回传送带起点」（干扰运动中的目标）。
- 少数任务备注为空（T31/T32 的人类备注、T08/T09/T15/T16/T29/T30 的未见物体备注）。

编号含义（是轴编号还是试次编号）官方没有解释，但**这些备注事实上给出了人类干扰轴的逐任务剧本**：绝大多数是"对某个对象做一次 1-DOF 平移"或"在某一步完成后撤销它"。这是可以直接转成场景和数据的东西——第 5 轮 RB（恢复库）从"自造干扰原语"升级为"官方备注忠实回放"。

### 0.5 平台有"不计分单任务调试"模式

`profile.html` 的提交测试说明（[S8]）：评测分两种模式——① 计分多任务（覆盖 32 任务、进排行榜）；② **不计分单任务调试（只测 1 个任务、不计分、仅供了解模型大致能力）**，需要预约时段，管理员确认后占用排期。这意味着**真机反馈回路不只存在于正式评测**：只要我们按时段预约，就可以在 T27、T10 这类高价值任务上做真机 A/B。第 5 轮的 TCLB（本地孪生评测台）因此从"真机校准的主要替代"降级为"离线相对比较工具"，主回路改为平台调试槽 + 少量计分跑。

### 0.6 榜单 / 运行记录 / 详情页仍是占位

- `leaderboard.html` 仍是「即将发布 / Coming Soon」；`leaderboard_data.json` 的 `generated_from` 仍是 `gen_leaderboard.py`，8 个模型 256 条 task_metrics 仍是脚本生成（[S9][S10]）。
- 新出现的 `runs.html`（运行记录）同样是占位：`256 / 256` 条记录、8 个模型 × 32 任务，详情页明确写「测试视频占位，后续可替换为真实视频文件」（[S9]）。

所以占位数据的唯一用途仍是"难度先验"，绝不能用来判断谁强谁弱或推理轴级瓶颈。唯一可谨慎使用的量：8 个占位模型里，步骤分平均比成功率高约 8.6 个百分点（39.0 vs 29.7、38.9 vs 28.5、……28.1 vs 20.5）——**如果这个结构在真实数据里也成立，说明大部分失败发生在"做完大部分步骤、倒在最后一步"**。这与 0.1 的评分结构相互呼应，但必须标"未核实"。

### 0.7 提交接口 v2 的观测目录足够支撑放置闭环

`unibot_submission` README（[S6]，仓库最近一次提交是 2026-08-21 的 v2）给出：

- 观测四路 RGB（左右高位 + 左右腕部，480×640）、双臂关节/EE 位姿（base 系）、夹爪开度、下半身、**`observation.language` 单字符串**（整段 episode 不变，无时间轴）；
- `obs_delta_indices` 由我们声明"传哪些键 + 每键堆叠几帧"；`image_resize` 由我们指定每路分辨率；`action_chunk_size` 自定；动作空间二选一（joint 或 ee，互斥）；
- `reset()` 每 episode 调一次；token 双处校验。

这确认：我们完全控制推理侧的观测裁剪、时序堆叠、图像缩放与 chunk 长度——**在观测里做锚点渲染、在 chunk 上做检索条件化，都是接口内允许的**。关节/EE 双动作空间也意味着放置位姿迁移（EE 空间）可以直接落。

## 1. 三个灵感词，各自钉到官方事实上

### 1.1 放置：评分结构决定的"闸门 + 大头 + 跨轴杠杆"

把 0.1 的算术写清楚：

```text
成功率 = 所有步骤完成的 episode 比例（终局步骤是 32/32 任务的闸门）
步骤分 = 逐步部分分（放置类步骤约 59.7%，终局约 39.8%）
排名 = 成功率与步骤分综合排序
```

于是任何"让终局步骤更容易成功"的改进，同时赚三份：成功率的闸门、步骤分的最大单项、以及——**最重要的一点**——它不挑泛化轴。位置、干扰物、背景、未见物品、人为干扰五个轴的评测里，模型都要做最后那一下放置；放置能力是**跨轴资产**。对比第 5 轮"补最弱轴"的算术：

| 改进类型 | 作用范围 | 总分增益近似 |
|---|---|---|
| 单轴成功率 +Δ | 该轴（1/5 权重） | Δ/5 |
| 终局放置成功率 +Δ | 所有轴、所有任务 | ≈ Δ ×（到达终局步的通过率 q，约 0.5–0.7） |

也就是说，**终局放置 +15pp 的期望总分增益 ≈ +7~10pp；而单轴 +15pp 只有 +3pp**。这不是小差异，是 2–3 倍的杠杆差。（q 需要用调试槽实测校准。）

从演示数据看时间预算充足：HangCup 1,043 条 episode 时长中位数 177 帧 ≈ 5.9s（94–411 帧，30fps）；官方限时 180s，意味着**放点重试/落点校验有充裕预算**——这是"最后 3 厘米做闭环"的物理基础。

### 1.2 少样本学习：不是改权重，是"取回上下文 + 迁移位姿"

一提到少样本，容易想到"每任务微调几个样本"。但 UniBot 的约束把这条路堵住（单模型、未公布的微调规则）且收益存疑（评测 100% OOD）。2026 年的证据更支持另一条路——**推理时冻结权重、用少量演示做上下文条件化/位姿迁移**：

- **ICI-VLA**（武汉大学，[S17]）：把长轨迹切成"语义子任务微演示"，用 DTW 对齐检索，Target Action Masking 防抄轨迹；LIBERO 97.7%、RoboTwin 2.0 60.4%（比最强基线 +19.3pp）、真机双臂 83.2%。**推理期参数固定**。
- **RA-VLA**（POSTECH，[S18]）：行为对齐检索 + 上下文遵循损失，1–5 条演示/task 的 buffer，"training-free adaptation"，LIBERO +17.6pp、UR5e +20.8pp；**每段独立预编码缓存，推理延迟几乎不随检索数量增长**。
- **Retrieval-VLA**（CVPRF 2026，[S20]）：物件中心稀疏关键点做检索键，"discarding irrelevant visual clutter"——正对背景轴。
- **FlowRetrieval**（PMLR，[S21]）：光流运动相似度检索，比视觉/语言相似度都更跨场景；真机 Pen-in-Cup 3.7× 于用全部数据训练。
- **HSR**（[S19]）：层级技能检索 + 行为特征重排，长程任务收益最大（真机 +21.3pp）。
- **SAIL**（[S22]）：把上下文模仿做成"测试时算力可扩展"的迭代精化（MCTS），复杂任务最高 95%。
- **Retrieve, Don't Retrain**（NAVER，[S23]）：新任务=往检索池里加数据，不是更新参数。

映射到 UniBot：官方 33k 名义演示就是现成的"少样本库"；缺的是**一个抗 OOD 的检索键 + 一个可迁移的放置量**。检索键必须是关系中心化（物体/容器相对位姿 + 相位的运动特征），不能是全局外观（否则背景轴一来就崩）；迁移量不是"动作块复制"，而是**终局放置的相对位姿统计**（见 1.1 闸门：把 K 条演示的"释放位姿相对容器坐标系"的中位数迁移到当前场景，用离散度决定伺服/柔顺程度）。这条路线零梯度、可缓存、单模型，且证据链完整。

### 1.3 产学研合作：不是挂名，是"数据农场 + 方法供给 + 验证回路"

宇树自己就在大规模做产学研：青岛城市学院产业学院（2025-12 揭牌，1 万平米实训基地、30 余台套机器人含 G1）、河南理工大学具身智能学院、柳州城市职业学院、厦门工学院、香港大学上海智能计算研究院、武汉大学数智教育通关实验室、重庆大渡口"人形机器人数据采集中心"等（[S27]）。高校侧也已经有成熟的 G1 遥操作与数据采集流水线（PICO4 VR 遥操作、SONIC 运控、Unitree_XR 采集、LeRobot 部署；[S28]）。这给参赛者一个真实的组织杠杆：

1. **数据农场（学→产）**：背景轴/位置轴的评测条件，本质是"实验室多样性"。拥有 G1 的高校实验室按统一协议采集 1–2 个任务、100–200 条场景多样的放置演示，贡献的是官方数据集最缺的东西——**不同实验室的桌面、光照、背景、布局**。数据是合规的自采数据（非第三方黑箱数据），许可可谈。
2. **方法供给（学→研）**：检索/上下文、视觉锚点、高精度注意、同轴迁移这些模块都有公开论文可复现（[S12]–[S24]），我们做集成商而不是重新发明。
3. **验证回路（平台→团队）**：不计分单任务调试槽 + 真机评测，是比自建孪生更可信的外部验证；约定"每次大版本变更预留 1 个调试槽"，把真机反馈做成 release gate。
4. **赛后反哺**：采集协议、步骤图、评测脚本以联合署名形式开源（比赛期间不开源核心技术，避免削弱优势）。

一句话：**产学研在 UniBot 里不是务虚，而是把"背景/位置轴的多样性"外包给实验室网络、把"验证"外包给平台调试槽、把"方法"外包给论文生态。**

## 2. 本轮主判断：预算从"补最弱轴"改为"攻终局放置"，用少样本方式攻

### 2.1 一个更锋利的失败模型

结合官方备注（0.4）、Spa-Bench 的结论（执行能力往往不是瓶颈，空间 grounding 是：ID 67.5–73.3% → OOD 40.7–52.0%，把空间指令换成直接操作指令后成功率 +28–40pp，[S13]）、以及放置专项证据（AnySlot：图像生成式显式视觉目标优于 VLM 坐标输出，真机 82%；[S12]；SpaceVLA：显式抓/放锚点把放置误差降 5 倍到 0.7cm，[S15]；ActGaze：反事实视觉干预做"动作注意力"监督，四个毫米级任务 77.0→91.5%，[S14]），我给出放置失败的六类根因假设：

| # | 失败模式 | 证据来源 | 对策组件 |
|---|---|---|---|
| P1 | 目标槽位/落点 grounding 错（选错位置/挡位） | Spa-Bench、AnySlot | 放置目标阶梯（槽位→锚点→位姿） |
| P2 | 接近路径碰撞（拿着物体撞到容器/其他物体） | 备注里的干扰物多为平移物 | 相对位姿迁移 + 碰撞感知接近 |
| P3 | 姿态不对（叠碗不平、相框没摆正、药瓶倒不进） | 评分步骤明说"straighten/order" | 位姿统计 + 伺服收尾 |
| P4 | 释放过早/过高（掉落、弹跳、滚动） | 终局步骤权重最大 | settle 闭环 |
| P5 | 插入深度/力不够（插头、网线、试管） | T10/T26 备注"拔起/移开" | 柔顺插入 + 到位判定 |
| P6 | 不验证就以为完成（掉了也不知道） | 成功=全步骤 | 谓词校验 + 重试 |

六类里有一半（P1/P3/P4/P6）不依赖新数据，靠"显式目标 + 闭环校验"就能吃到。

### 2.2 为什么这比第 6 轮（被拒的 FLEET）更该做

第 6 轮把"部署分布"当第六轴，素材是对的（N 端口、跨机差异、延迟），但作为研究贡献太软、且很大一部分是官方已经规定好的工程形态。本轮的判断是：**把 FLEET 的事实降级成工程检查单（N 端口并发、状态隔离、RTC 式延迟弹性、健康检查），研究火力集中到"评分结构里权重最大、且跨轴起作用"的终局放置上。** 放置是研究问题，部署只是前提条件。

### 2.3 与第 5 轮 TS-GPR 的关系

- **保留**：GPR-VLA 主干（目标→残差→动作专家→可逆信念）、WLA-1.0-Base 底座、TLE/ACP/GF 数据引擎、AH-TP、合规开关。
- **升级**：RB → **官方备注忠实恢复库**；TCLB → 降级为离线相对比较；"补最弱轴"的预算逻辑 → **放置优先 + 跨轴杠杆**。
- **新增**：评分步骤图门控（SSG）、放置目标阶梯（PGL）、少样本放置位姿迁移（OPT）、推理期上下文检索（ICR）、落点 settle 闭环（SVL）、产学研数据协议（L2L）、平台调试回路。
- **修剪**：FLEET 作为"第六轴"的框架；全 32 任务高保真孪生；自由仿真数据；运行时仿真/MPC；仿真 RL；布料/拉链/透明全物理；WMA-0 进主路径；每任务 LoRA。

## 3. 方案轮廓：PILOT-GPR（细节在产物区）

```text
语言(160条复述之一) → SSG 评分步骤图（公开逐任务步骤+权重）→ 当前步骤 s
                                 │
                     ┌───────────▼───────────┐
                     │ PGL 放置目标阶梯        │  槽位/区域 → 2D 锚点 → 6D 位姿
                     │ OPT 少样本位姿迁移      │  K条演示的"容器系释放位姿"中位数+离散度
                     │ ICR 上下文检索          │  关系中心键 + 相位对齐 + 缓存编码
                     └───────────┬───────────┘
                                 ▼
   GPR-VLA（单一 checkpoint）：目标 z* − 部件信念 b → 残差 r → Action Expert → chunk
                                 ▼
                     SVL 落点闭环：伺服→缓放→稳定性校验→重试/重抓
                                 ▼
                     NRB：官方备注剧本（先叠后撤/拉链拉开/拧回瓶盖…）→ 恢复
```

一句话：**把公开的评分步骤当骨架，把官方 33k 当少样本库，把放置位姿迁移和落点闭环当主武器，把实验室网络当数据农场和验证回路。**

## 4. 风险与合规（先立后破）

- **规则未读部分**：外部数据/仿真是否允许仍未确认（手册 2.3 之后未读到）；L2L 合作数据要挂在合规开关后（默认只做协议设计与法务准备，不并入训练）。
- **检索在透明/布料任务上可能失效**（关键点/光流在试管、拉链、毛巾上不稳）→ 分桶回退：这些任务只做"相位检索 + 动作先验"，不做位姿迁移。
- **锚点渲染的域差**：训练时锚点必须来自与推理同分布的目标（演示的真实目标 + 仿真目标混合），否则模型学会"看渲染纹理"。
- **闭环耗时**：SVL 每个放置点多花 1–3s，180s 预算内可承受，但长程任务（T16/T17/T31）要限次数。
- **调试槽稀缺且规则未明**：把调试槽当"发布门"而不是"调参器"，每个大版本最多 1 槽。
- **单模型合规**：SSG/PGL/SVL 全部是确定性代码；ICR 的库是数据不是模型；学习组件只在唯一 checkpoint 里。守卫规则写进提交模型卡。

## 5. 一句话押注

**把评分结构当第一性依据：终局放置是 32/32 任务的成功闸门、~60% 步骤分和唯一跨五轴同时起作用的杠杆；用"公开步骤图门控 + 少样本放置位姿迁移 + 视觉锚点 + 落点闭环"去攻它，用实验室网络补背景/位置轴，用平台调试槽做发布门。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 7 轮产物区 · PILOT-GPR 技术报告（放置优先 + 少样本上下文 + 产学研数据协议）

> 目标赛事：宇树科技 **UniBot 世界挑战赛**（unibot.unitree.com），G1 + Dex1，32 项桌面任务，通才单模型赛道，选手自部署、官方远程真机 API 评测。检索/复核日期：**2026-10-24（UTC）**。本报告在第 5 轮 TS-GPR（孪生=标注器+反事实发生器）基础上做聚焦迭代；第 6 轮 FLEET 的正确素材保留为工程检查单，不再当作研究主轴。**本报告最重要的新证据：官方已公开 32 任务的全部评分步骤与权重，终局步骤合计占 39.8% 且是成功闸门；放置类步骤约占 59.7%。**

---

## 0. 产物摘要

### 0.1 一句话

**把评分结构当第一性依据：终局放置是 32/32 任务的成功闸门、约 60% 步骤分、唯一跨五轴同时起作用的杠杆；用「公开步骤图门控（SSG）+ 少样本放置位姿迁移（OPT）+ 视觉锚点（PGL）+ 落点闭环（SVL）」去攻它，用实验室网络（L2L）补背景/位置轴，用平台调试槽做发布门。**

### 0.2 组件与是否进推理

| 组件 | 作用 | 进推理？ |
|---|---|---|
| SSG 评分步骤图门控 | 官方公开步骤→任务图；状态机与谓词校验；防跳步/假完成 | 是（确定性代码） |
| PGL 放置目标阶梯 | 槽位/区域 → 2D 锚点（渲染）→ 6D 位姿目标 | 是（确定性代码+渲染） |
| OPT 少样本位姿迁移 | K 条演示的"容器系释放位姿"稳健统计 → 当前场景目标 | 是（查表+统计，无梯度） |
| ICR 上下文检索条件化 | 关系中心键 + 相位对齐 + 缓存编码，喂给 policy | 是（数据，不是模型） |
| SVL 落点 settle-verify 闭环 | 伺服→缓放→稳定性校验→微调/重抓/重试 | 是（控制循环） |
| NRB 官方备注忠实恢复库 | 用公开 human 备注构造破坏→恢复对 | 否（只在训练数据） |
| L2L 实验室数据协议 | 伙伴实验室采集背景/位置多样性数据 | 否 |
| DebugLoop 平台调试回路 | 不计分单任务调试槽作发布门 | 否（流程） |
| GPR-VLA 主干 + WLA 底座 | 单一 checkpoint：目标残差→动作 chunk | 是（唯一学习模型） |

### 0.3 预期收益（可证伪）

- 终局放置成功率 +Δ ⇒ 全局成功率约 +Δ×q（q=到达终局步的通过率，估计 0.5–0.7），**且是所有轴同时受益**；对照第 5 轮"单轴 +Δ ⇒ +Δ/5"。
- 目标：终端步 +15pp ⇒ 总分期望 +7–10pp；保守目标 +3–5pp（在 320 计分 trials、p≈0.3、SE≈2.56pp 下，+3pp 约 80% 概率排名更高，+5pp 约 90%）。
- 可证伪点：若 T27/T10 调试槽里终局步提升 <5pp，则 OPT/PGL 假设不成立，回退到纯 SSG+SVL。

### 0.4 与上一轮（TS-GPR）的关系

| 关系 | 内容 |
|---|---|
| 保留 | WLA-1.0-Base 底座、GPR-VLA（目标残差+可逆信念）、TLE/ACP/GF 数据引擎、AH-TP、Endurance Governor、Compliance Compiler |
| 升级 | RB → NRB（官方备注忠实化）；TCLB → 降级为离线相对比较；"补最弱轴"预算逻辑 → 放置优先跨轴逻辑 |
| 新增 | SSG、PGL、OPT、ICR、SVL、L2L、DebugLoop |
| 修剪 | FLEET"第六轴"框架（降为工程检查单）；全 32 任务高保真孪生；自由仿真数据；运行时仿真/MPC；仿真 RL；布料/拉链/透明全物理；WMA-0 进主路径；每任务 LoRA |

---

## 1. 事实核对（本轮新增，全部一手；来源表见 §12）

### 1.1 32 任务评分步骤与权重全部公开

`tasks_v2/<slug>/info.json` 的 `score_steps` 给出逐步分值（满分 100）。已在 2026-10-24 抓全 32 个文件（[S2]）。表 A 为逐任务明细；表 B 为同文件的 `generalization` 备注。

**关键聚合**：终局步骤合计 1275/3200 = **39.8%**；放置/插入/堆叠/闭合类步骤合计约 1910/3200 = **59.7%**（关键词粗分类）；32 个终局步骤中 28 个为放置类，4 个为拔出/取出/翻转/倾倒类终局操作（T05/T11/T12/T14）。难度：12 Easy / 12 Medium / 8 Hard。

**表 A / 表 B（本轮抓取的官方数据，原样整理）：**

### 表 A：32 任务评分步骤（2026-10-24 抓取，来源 tasks_v2/<slug>/info.json）

| ID | 任务 | 难度 | 步骤数 | 终局步骤（权重） | 其他步骤 |
|---|---|---|---:|---|---|
| T01 | HangCup | Easy | 2 | Hang it on the marked spot on the rack（50） | Grab the cup handle（50） |
| T02 | FruitCollection | Easy | 2 | Grab fruit 2 and put it into the basket（50） | Grab fruit 1 and put it into the basket（50） |
| T03 | PackDoll | Easy | 2 | Place the bag upright in front of you.（50） | Pack all the dolls into the bag.（50） |
| T04 | FruitSorting | Easy | 3 | Grab fruit 3 and place it onto the plate with the matching color（40） | Grab fruit 1 and place it onto the plate with the matching color（30）；Grab fruit 2 and place it onto the plate with the matching color（30） |
| T05 | DisconnectEthernet | Hard | 2 | Unplug the Ethernet cable（50） | Hold the network port, then grip the Ethernet cable（50） |
| T06 | ColorArrangement | Easy | 3 | Place the yellow block in the leftmost position（40） | Place the red block in the rightmost position（30）；Place the green block in the middle position（30） |
| T07 | PlacePhotoFrame | Medium | 3 | Straighten the photo frame（40） | Grab the photo frame（30）；Open the frame stand（30） |
| T08 | OrganizeBookshelf | Easy | 2 | Place it on the bookshelf（50） | Grab the book and pick it up（50） |
| T09 | ToolboxStorage | Hard | 4 | Lock the toolbox.（25） | Store two tools in the toolbox.（25）；Store all the remaining tools in the toolbox.（25）；Close the toolbox lid.（25） |
| T10 | PlugCharger | Hard | 3 | Plug it into the power strip（40） | Grab the power strip（30）；Grab the plug（30） |
| T11 | PickOutBatteries | Medium | 3 | Pick out battery 3 (without grabbing any block)（40） | Pick out battery 1 (without grabbing any block)（30）；Pick out battery 2 (without grabbing any block)（30） |
| T12 | Unlock | Hard | 3 | Flip the metal ring（40） | Pick up the lock（30）；Turn the key（30） |
| T13 | ArrangeTestTubes | Easy | 3 | Pick up test tube 3 and return it to its designated spot in the rack（40） | Pick up test tube 1 and return it to its designated spot in the rack（30）；Pick up test tube 2 and return it to its designated spot in the rack（30） |
| T14 | PourOutMedicine | Hard | 2 | Pour out the medicine（50） | Open the pill bottle cap（50） |
| T15 | OrganizeTools | Medium | 4 | Grab tool 4 and return it to the rack（25） | Grab tool 1 and return it to the rack（25）；Grab tool 2 and return it to the rack（25）；Grab tool 3 and return it to the rack（25） |
| T16 | FoldTowel | Hard | 5 | Fold and set it aside（20） | Straighten the towel（20）；Fold it in half top to bottom once（20）；Grab the left side and fold once（20）；Grab the right side and fold once（20） |
| T17 | OrganizeStationery | Easy | 5 | Close the pencil case（20） | Straighten the pencil case（20）；Put stationery 1 into the case（20）；Put stationery 2 into the case（20）；Put stationery 3 into the case（20） |
| T18 | PackBag | Medium | 4 | Zip up the backpack（25） | Grab the pencil case（25）；Grab the backpack and pull it over（25）；Put the pencil case into the backpack（25） |
| T19 | ZipUp | Medium | 2 | Zip up the pouch（50） | Straighten the pouch（50） |
| T20 | PaperCupStacking | Easy | 3 | Place paper cup 3 on top of cups 1 and 2（40） | Place paper cup 1 in the middle（30）；Place paper cup 2 next to cup 1（30） |
| T21 | ArrangePlates | Easy | 3 | Place plate 3 into the rack（40） | Place plate 1 into the rack（30）；Place plate 2 into the rack（30） |
| T22 | SpellRobot | Medium | 4 | Place letter t onto the board（25） | Grab the spelling board（25）；Place letter b onto the board（25）；Place letter o onto the board（25） |
| T23 | StorePaddle | Medium | 2 | Zip up the paddle case（50） | Put the paddle into the case（50） |
| T24 | ConveyorSorting | Medium | 2 | Place it at the position corresponding to its category on the rack（50） | Grab the food item on the conveyor belt（50） |
| T25 | StoreCups | Easy | 3 | Place paper cup 3 into the rack（40） | Place paper cup 1 into the rack（30）；Place paper cup 2 into the rack（30） |
| T26 | PlugInEthernet | Medium | 3 | Plug the cable into the network port（40） | Grab the ethernet cable（30）；Hold the network port（30） |
| T27 | StackBowls | Easy | 3 | Stack bowl 3 onto bowl 2（40） | Place bowl 1 in the middle（30）；Stack bowl 2 onto bowl 1（30） |
| T28 | StoreEarphones | Hard | 4 | Close the earphone case lid and put the case into the storage box（25） | Grab the earphone case（25）；Put the left earphone into the case（25）；Put the right earphone into the case（25） |
| T29 | PackPhone | Hard | 3 | Close the box（40） | Place the tray into the box（30）；Put the phone onto the tray（30） |
| T30 | RemovePinnedNote | Medium | 2 | Put the note back into the storage box（50） | Pull out all the push pins and place them into the storage box（50） |
| T31 | OrganizePencilCase | Medium | 3 | Close the zipper（40） | Open the pencil case zipper（30）；Put all stationery items into the pencil case（30） |
| T32 | SyringeWaterTransfer | Medium | 2 | Inject the water into the small cup（50） | Draw water from the large cup using the syringe（50） |

### 表 B：逐任务泛化备注（info.json 的 generalization 字段，未解读编号含义）

| ID | 任务 | unseen_object_3 | human_1_note | human_4_note |
|---|---|---|---|---|
| T01 | HangCup | 缺少红色杯子和塑料架子 | 杯子向后 | 杯子向右 |
| T02 | FruitCollection | 缺少不同果篮 | 水果向前 | 水果向右 |
| T03 | PackDoll | 缺少绿色和紫色娃娃 | 娃娃向前 | 娃娃向右 |
| T04 | FruitSorting | 缺少其他款式的盘子 | 橘色盘子向左移动移动 | 把梨往右移动 |
| T05 | DisconnectEthernet | 缺少其他颜色的短网线 | 把网线另一头也插上 | 移动道具手握网口 |
| T06 | ColorArrangement | 没有其他积木 只有塑料积木 | 绿色积木向右移动 | 红色积木向前移动 |
| T07 | PlacePhotoFrame | 只有一种相框 | 相框向上移动 | 相框向上移动 |
| T08 | OrganizeBookshelf | — | 抓到书后挪动架子 | 书向右 |
| T09 | ToolboxStorage | — | 胶带向后移动 | 胶带向右移动 |
| T10 | PlugCharger | 缺少其他颜色的插排 | 抓插头前进行移动 | 将插头拔起 |
| T11 | PickOutBatteries | 缺少黑色电池 | 抓取电池之前动底座 | 抓电池之后动绿色盒子 |
| T12 | Unlock | 缺少一把绿色锁 | 锁向左移动 | 中途把锁拿走 |
| T13 | ArrangeTestTubes | 不同类型的试管 | 试管向右移动 | 试管向左移动 |
| T14 | PourOutMedicine | 缺少不同颜色的药品收纳盒 | 拧开盖子之后拧动回来 | 把瓶子向左移动 |
| T15 | OrganizeTools | — | 钳子向左移动 | 螺丝刀向右移动 |
| T16 | FoldTowel | — | 将叠完的毛巾翻开 | 将叠完的毛巾翻开 |
| T17 | OrganizeStationery | 缺少黑色的文件盒 | 荧光笔向后 | 笔盒合上之后手动打开 |
| T18 | PackBag | 缺少其他颜色的文具盒 | 把文具盒向上移动 | 把书包向左移动 |
| T19 | ZipUp | — | 把包向左边移动 | 拉上拉链之后拉开 |
| T20 | PaperCupStacking | 缺少不同类型纸杯 | 把左边的纸杯向上移动 | 把右上角的纸杯向右移动 |
| T21 | ArrangePlates | 缺少不同类型的盘子 | 把盘子向前移动 | 把架子向左边移动 |
| T22 | SpellRobot | 缺少不同颜色的字母 | 字母上移动 | 字母向左边移动 |
| T23 | StorePaddle | 缺少不同的球拍套装 | 球拍向前移动 | 球拍向左移动 |
| T24 | ConveyorSorting | 缺少不同的零食 | 可乐快到了然后放回传送带起点 | 薯片快到了然后放回传送带起点 |
| T25 | StoreCups | 缺少不同颜色的纸杯 | 把纸杯向左移动 | 放了第一个马上放第二个挪一下底座 |
| T26 | PlugInEthernet | 不同的网线跟端口 | 把网线移开 | 把插口移开 |
| T27 | StackBowls | 除了塑料类型 | 把粉色碗向下移动 | 叠了第二个之后拿下第二个 |
| T28 | StoreEarphones | 缺少不同的收纳盒以及耳机托盘 | 把黄色盒子的耳机向前移动 | 把红盒子的耳机向右移动 |
| T29 | PackPhone | — | 手机向上移动 | 外壳盖移开 |
| T30 | RemovePinnedNote | — | 把把黄色钉子移到中间 | 把绿色钉子向下移动 |
| T31 | OrganizePencilCase | — | — | — |
| T32 | SyringeWaterTransfer | — | — | — |

合计：3200 分；终局步骤合计 1275 分（39.8%）。

### 1.2 逐任务泛化备注公开

每个任务的 `human_1_note`、`human_4_note`、`unseen_object_3` 直接写明（[S2]）。备注编号含义（轴编号还是试次编号）官方未解释，标"未核实"；但内容本身是可直接场景化的干扰剧本：多数是"对某对象做一次 1-DOF 平移"或"在某步完成后撤销它"。

### 1.3 每条指令 5 条英文复述（存在数据集里）

`meta/tasks.parquet` 中每个任务的 task 字段是 5 条复述用 `@` 连接（实测 HangCup / StackBowls / ZipUp / PlugCharger 均为 5 条；[S4][S5]）。评测指令很可能在这些复述中采样 → SSG 的指令匹配必须覆盖 32×5=160 条（外加中文描述映射）。

### 1.4 数据规模与时间线

- Collection `unibot-v1-challenge-dataset`（[S3]）：32 个数据集，969–1,530 条/任务，合计约 33k、169h。
- HangCup 实测：1,043 条、194,564 帧、30fps；episode 时长 94–411 帧（中位 177 ≈ 5.9s）；数据集 `lastModified` = **2026-10-14**（[S4]）。
- 对照：2026-08-18 社区帖子仍在质疑"HangCup 只有 44 条"（[S29]）→ 可以确认全量发布是最近两周内完成的事件。
- 数据结构：LeRobot v3；四路相机 `head_stereo_left/right` + `wrist_left/right`；EE 位姿在 base 与 torso 两套坐标；每任务一个 task_id。

### 1.5 平台有"不计分单任务调试"模式（新发现）

`profile.html`（[S8]）：提交测试分两种——① 计分多任务（32 任务、进榜）；② **不计分单任务调试（1 个任务、不计分）**，预约时段、管理员确认。真机反馈回路因此不唯一依赖正式评测。可用次数/成本未公开，标"未核实"。

### 1.6 榜单/运行记录/详情页仍为占位

`leaderboard.html` + `leaderboard_data.json` 仍是脚本生成占位（8 模型/256 条 task_metrics；[S10]）；新增 `runs.html` 也是占位（256/256、详情页写"视频占位"；[S9]）。占位数据里 8 个模型的"步骤分 − 成功率"差值平均约 **+8.6pp**（39.0−29.7 等），只能当"失败集中在后段步骤"的弱先验，标"未核实"。

### 1.7 提交接口 v2 对方案的约束与自由度

README（[S6]；v2 提交 2026-08-21，[S7]）：

- 观测：4×RGB 480×640、双臂关节/EE 位姿（base 系）、夹爪、下半身、`observation.language` 单字符串（episode 内不变）。
- 自由度：`obs_delta_indices` 决定"传哪些键+每键堆叠几帧"；`image_resize` 自定；`action_chunk_size` 自定；动作空间 joint 或 ee 互斥。
- `reset()` 每 episode 一次；token 双处校验。

→ 观测裁剪、时序堆叠、图像缩放、锚点渲染、chunk 检索条件化全部在接口允许范围内；EE 动作空间支持位姿级放置迁移。

### 1.8 事实与推断分界

| 事项 | 状态 |
|---|---|
| 评分步骤/权重、泛化备注、5 复述、数据规模、调试模式、API 目录 | 已核实（一手） |
| 备注编号含义（轴/试次）、调试槽可用次数、步骤分聚合公式、N 台机器人数 | 未核实 |
| 占位榜数字可用性 | 仅难度先验 |
| "终局放置是瓶颈" | 假设（由评分结构 + Spa-Bench/占位数据支撑），必须用调试槽证伪 |

---

## 2. 评分算术：为什么放置是第一目标

### 2.1 闸门与权重

```text
成功率 = P(所有步骤完成)              # 32/32 任务的闸门都是终局步骤
步骤分 = Σ 步骤权重 × P(该步完成)     # 放置类 ≈59.7%，终局 ≈39.8%
排名   = 成功率与步骤分综合排序
```

### 2.2 跨轴杠杆（本轮核心论点）

五轴评测（位置/干扰物/背景/未见物品/人为干扰）里，模型都要做终局放置；放置能力是**跨轴资产**：

| 改进 | 作用范围 | 总分增益近似 |
|---|---|---|
| 单轴成功率 +Δ | 1/5 权重 | Δ/5 = 0.2Δ |
| 终局放置成功率 +Δ | 全部轴×全部任务 | ≈ Δ×q（q≈0.5–0.7） |

**终局放置的杠杆约为单轴改造的 2.5–3.5 倍。**

### 2.3 部分分结构（弱先验）

占位榜"步骤分−成功率"≈ +8.6pp，与"多数失败发生在后段步骤"一致；若真实榜单结构相同，资源应向后段（含终局）倾斜。标"未核实"。

### 2.4 时间预算

演示中位数约 6–10s/任务；官方限时 180s → 每个放置点允许 1–2 次重试 + 0.5s 级 settle 校验；长程任务（T16/T17/T31，4–5 步）需要次数上限（建议 ≤2 次重试/task）。

### 2.5 预算分配建议（修订第 5 轮）

```text
放置专项（PGL/OPT/SVL/SSG）      40%
恢复与干扰（NRB + ACP-human）     20%
数据与孪生（TLE/GF + 分桶）       20%
工程与部署（含调试回路）          20%
```

---

## 3. PILOT-GPR 架构

### 3.1 总览

```text
┌──────────────────────── Offline（训练与标定）─────────────────────────┐
│ 官方 33k（LeRobot v3, 四路相机, EE base 位姿, 5 复述）                  │
│   ├─ TLE：步骤相位切分 + 谓词/接触标签 + 放置位姿库 H_i                 │
│   ├─ OPT 库：每任务每步骤的容器系释放位姿 {H_i} + 容差 τ_task          │
│   ├─ ICR 库：相位段微演示 → 关系/运动键 + 缓存上下文编码 + 动作先验    │
│   ├─ ACP（第 5 轮）：位置/干扰物/背景/未见物品配对 —— 收窄到放置场景   │
│   └─ NRB：官方备注剧本（先叠后撤/拉上再拉开/拧回瓶盖…）的破坏→恢复对   │
└──────────────────────────────────────────────────────────────────────┘
                                   │
┌──────────────────────── Inference（单一 checkpoint）──────────────────┐
│ observation.language（160 复述之一）                                    │
│        │                                                              │
│        ▼  SSG：指令→任务→步骤图；状态机 s_t；谓词头                    │
│  obs（4 相机+proprio）─► PGL：槽位/区域→2D 锚点→6D 位姿（OPT 统计）    │
│        │                     │                                        │
│        │                     ▼ 锚点渲染进头/腕图像                     │
│        └─► ICR.retrieve(step, obs, k=4) ──► 上下文 token + 动作先验    │
│                          │                                            │
│                          ▼                                            │
│   GPR-VLA（WLA-1.0-Base + LoRA/action expert）                        │
│     语言→z*；4 视图+部件→b；r = z* − b；Action Expert→chunk/horizon    │
│                          │                                            │
│                          ▼                                            │
│   SVL：伺服接近→缓放→稳定性/谓词校验→nudge/regrasp/retry（≤N 次）      │
│                          │                                            │
│   NRB 触发：谓词从 1→0（被撤销/移走）→ 重置步骤 s_t → 复用 ICR/OPT     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 SSG：评分步骤图门控（Score-Step Graph）

- 输入：`info.json` 的 `score_steps`（已抓全，表 A）+ 5 条复述/中文描述。
- 构建：每任务一个线性图 `s0 → s1 → … → s_k`，附权重 w_i；指令匹配 = 精确串匹配（160 条）+ 规范化（小写/去标点）+ 嵌入兜底。
- 运行：`s_t` 仅在"谓词头 + 事件校验"确认完成后前进；未确认则重试/回退；`human` 撤销事件触发 `s_t ← s_{t-1}`。
- 收益：(a) 防跳步/防假完成（直接提成功率）；(b) 把每步的"完成概率"显式化 → 重试预算按 w_i 分配；(c) 给 OPT/ICR 提供相位标签。
- 谓词标签来源：第 5 轮 TLE 的接触/谓词标签（真实演示自动产）；少量人工抽检。

### 3.3 PGL：放置目标阶梯

三级目标，逐级显式化（证据：AnySlot 显式视觉目标 > VLM 坐标 [S12]；Spa-Bench OOD 空间 grounding 是主要瓶颈 [S13]；SpaceVLA 锚点把放置误差降 5× [S15]）：

1. **槽位/区域（语义级）**：SSG 给出官方步骤文本（如"place the yellow block in the leftmost position"）；用容器/目标检测（SAM 类）+ 相对关系确定候选槽位。
2. **2D 锚点（视觉级）**：把 6D 目标投影到头/腕相机，渲染十字 + 朝向 + 容差圈（训练时用演示真实目标做同一渲染 → 同分布 overlay）。
3. **6D 位姿（度量级）**：来自 OPT 的 K 条演示统计（§3.4），作为 EE 空间（base 系）目标；接近路径加碰撞规避（拿着的物体不撞容器）。

### 3.4 OPT：少样本放置位姿迁移

**离线**：对任务 t 的每条演示 i，用 TLE 估计容器系 `R_i`（标定 + 6D 位姿/关键点），取释放时刻 EE 位姿 `T_B^{G_i}(t_i^rel)`（数据集直接有 `*_ee_pose_gripper_base` 流）：

```text
H_i = (T_B^{R_i})^{-1} · T_B^{G_i}(t_i^rel)        # 容器系下的释放位姿
```

**线上**：视觉估计容器系 `T̂_B^R`；检索 K 条行为对齐演示（ICR 键，§3.5），

```text
xyz：H̄ = median_i(H_i.xyz)（稳健）
rot：四元数弦均值（或 L2 投影均值）
离散度：σ_xyz = std_i(H_i.xyz)；σ_θ = 角离散
目标：T̂_B^G = T̂_B^R · H̄
```

**决策规则**（离散度驱动控制风格）：

```text
σ < τ1                 → 直接执行（快）
τ1 ≤ σ < τ2            → 慢速 + 腕部视觉伺服到锚点
σ ≥ τ2                 → 放弃迁移 → 退化为"锚点伺服 + 保守放置"
τ_task（任务容差）     ← 同任务演示间 H_i 的 95 分位差
                          （叠碗大、插头小；用于谓词判定的放置误差阈值）
```

**为什么是"少样本"**：迁移的是 K 条（K=1–4）演示的**相对位姿统计**，不是动作轨迹复制；零梯度、可缓存、跨外观/背景/位置。对应证据：FlowRetrieval 运动相似度 > 视觉/语言相似度 [S21]；ICI-VLA 的相位对齐 + 防复制 [S17]。

### 3.5 ICR：上下文检索条件化

- **库**：官方 33k → 按 任务×步骤相位 切段（抓取段 + 终局放置段 + 闭合/插入段），每段 1–2s；估算 ~26 万段。
- **键（只取关系与运动，不取全局外观）**：指令复述嵌入；相位标签；目标物体关键点相对容器关键点（位移/朝向）；容器相对底座；最近 1s 光流统计/EE 速度。证据：Retrieval-VLA 的物件中心关键点抗 clutter [S20]；RA-VLA 的行为对齐键 [S18]。
- **值**：缓存上下文编码（独立预编码，RA-VLA 式）+ 动作先验（K 段动作的稳健均值，作为初始化/残差锚）。
- **注入**：上下文 token 拼接（长度有界）+ 动作先验与 policy 输出融合（小权重，防覆盖）。
- **延迟预算**：HNSW 检索 <5ms；编码全离线；目标 `get_action` p99 <100ms（单卡 + 多端口批量）；不满足则降 K 或降 key 维度。

### 3.6 SVL：落点 settle-verify 闭环

```python
def place_and_verify(step, obs, plan, budget=2):
    for attempt in range(budget + 1):
        anchor = PGL.render(plan, obs)               # 槽位→锚点→位姿
        ctx    = ICR.retrieve(step, obs, k=4)
        for chunk in stream(policy.act(obs, anchor, ctx, s=step)):
            send(chunk)                              # 30Hz
            if predicate_met(step, obs):             # 放置关系谓词
                break
        if not predicate_met(step, obs):
            plan = revise(plan, obs, reason=diagnose(step, obs)); continue
        open_gripper(slow=True); sleep(0.5)          # 缓放 + 静置
        if stable(step, obs, window=0.5):            # 位移<eps 且谓词保持
            return True
        if repairable(step, obs):
            plan = nudge_plan(step, obs)             # 推正/轻压
        else:
            regrasp(step)                            # 重抓
    return False
```

- `stable`：物体相对位姿在 0.5s 内位移 <ε_rel（ε 由演示统计给出）+ 谓词保持。
- `predicate_met`：SSG 谓词头 + 事件（接触/静止）。
- 预算：普通任务 ≤2 次；长程任务（T16/T17/T31）≤1 次；总时长守卫（Endurance Governor）兜底。

### 3.7 NRB：官方备注忠实恢复库

用公开备注（表 B）构造破坏→恢复对（可离线合成：对场景做备注描述的刚体操作），并把恢复段作为单独加权样本训练 GPR-VLA 的可逆信念（`b: 1→0→1`）：

| 任务 | 官方备注（节选） | 场景化 | 恢复目标 |
|---|---|---|---|
| T27 | 叠了第二个之后拿下第二个 | 移除 bowl2 | 重新放置 bowl2 → 继续 bowl3 |
| T19 | 拉上拉链之后拉开 | 拉开拉链 | 重新拉合 |
| T14 | 拧开盖子之后拧动回来 | 盖回瓶盖 | 再拧开 → 倒药 |
| T17 | 笔盒合上之后手动打开 | 打开盒盖 | 重新合上（终局步） |
| T24 | 物品快到了然后放回传送带起点 | 目标远离 | 重新抓取→放置 |
| T10 | 将插头拔起 | 拔出插头 | 重新抓取→插入 |
| T12 | 中途把锁拿走 | 锁被移走 | 重新定位锁→继续翻环 |
| T02/T04/T11/T25 | 移动水果/盘子/底座/挪底座 | 目标或底座平移 | 重新定位→继续当前步 |

这些**大概率就是 human 轴的真实评测剧本**（编号含义未核实）；即使不是，也是分布内的高价值扰动。

### 3.8 与 GPR-VLA 的接口与新增损失

```text
L = L_flow + λ1 L_pred + λ2 L_part + λ3 L_axis + λ4 L_rec + λ5 L_twin + λ6 L_reg
    + λ7 L_anchor + λ8 L_step + λ9 L_ctx
```

| 项 | 含义 | 起始权重 |
|---|---|---:|
| L_anchor | 锚点目标/位姿与演示 GT 一致（只在前若干维/末端） | 0.1 |
| L_step | SSG 谓词 BCE | 0.2 |
| L_ctx | 检索上下文与动作先验的一致性（训练时同分布注入检索上下文） | 0.05 |

**训练时必须注入检索上下文**（否则推理期首次见到检索 token 会崩）——ICR 库在训练时同步构建、抽样。

---

## 4. 数据引擎（TS-GPR 修剪版）

### 4.1 保留件与范围缩小

| 件 | 第 5 轮定位 | 本轮定位 |
|---|---|---|
| TLE | 全任务密集标签 | 只做两件事：步骤相位切分 + 放置相关标签（容器 pose/关键点、接触、谓词） |
| ACP | 五轴配对 | 收窄：位置（放置点平移）、背景（渲染替换）、干扰物（放置路径旁插入）；未见物品只对刚体任务 |
| GF | 四类 gap 软权重 | 保留；放置场景专用阈值（容器/目标几何） |
| 全孪生 | 12 任务 | 砍到 **放置关键 8 任务**（T07/T08/T10/T13/T20/T21/T25/T27） |
| C 类任务 | 2.5D 编辑 | 不变（布料/拉链/透明不做物理） |

### 4.2 放置位姿库构建

1. 标定（第 5 轮 §4.2）：相机重投影 <5px、桌面 <5mm、EE 回放 <2cm。
2. 对每个任务抽样 100–300 条演示（不是全部 1k），TLE 估计容器系 + 释放时刻。
3. 输出 `poses/<task>/<step>.npz`：{H_i, τ_task, 分位表, 场景元数据}。
4. 抽检 10%：位姿误差 <1cm 才入库。

### 4.3 合成规模（修订）

| 桶 | 任务 | 每任务/轴 | 轴 | 样本 |
|---|---:|---:|---:|---:|
| 放置关键 A/B 类 | 16 | 150 | 4 | 9,600 |
| C 类（2.5D） | 8 | 100 | 3 | 2,400 |
| NRB 恢复对 | 32 | 2 剧本 × 50 | — | 3,200 |
| 合计 | — | — | — | ~15,200 |

通过 GF 预计 50–70%；相对 33k 真实数据约 23–32%，仍满足"合成不主导"。

---

## 5. 产学研 L2L 协议（Lab-to-Leaderboard）

### 5.1 三方角色

| 角色 | 承担方 | 交换物 |
|---|---|---|
| 产 | 宇树平台（G1/数据/WLA/评测集群） | 公开数据与模型、真机评测、调试槽 |
| 学 | 拥有 G1 的高校实验室（宇树已有合作网络；[S27][S28]） | 场景多样的采集数据（背景/位置轴）、复现与评估人力 |
| 研 | 我们（集成与核心方法） | 采集协议、标注工具、模型、论文与开源产物 |

### 5.2 数据协议（关键：与官方格式逐字段对齐）

- LeRobot v3；`robot_type=unitree_g1`；30fps；四路相机键与官方同名（`head_stereo_left/right`、`wrist_left/right`）；EE base/torso 位姿、夹爪、lower_body 同 schema。
- 每任务写入 5 条官方英文复述 + 中文映射；步骤标签（SSG 序号 + 完成帧）。
- `scene.yaml`：灯光/背景/桌面高度/相机外参近似；**只采刚体/容器类任务的放置段**（第一轮不碰布料/拉链）。
- 每实验室每任务 100–200 条；首轮 3 实验室 × 2 任务 ≈ 600–1,200 条。

### 5.3 QA 与法务

- 自动 QA：四路同步、时长、动作平滑/加加速度、夹爪闭合事件、步骤覆盖、复述匹配；人工抽检 10%；单批拒绝率 >20% 停采。
- 协议：数据使用许可（本赛事 + 研究，不转售、不再分发）；无个人数据；合成/派生标签归属写在 NOTICE。
- **合规开关**：外部数据默认 OFF；邮件问 `challenge_support@unitree.com` 确认后 ON（若禁止，L2L 仅用于赛后研究）。

### 5.4 激励

赛后联合署名论文 + 开源"UniBot 放置标注工具链"；比赛期间不开源核心权重与检索库。这个机制是把"产学研"变成"可持续数据供给"的关键。

---

## 6. 训练配方（增量部分）

### 6.1 课程

| 阶段 | 数据 | 目标 | 退出条件 |
|---|---|---|---|
| 0 | 真实 100% | 复现 WLA 基线 | 真实 held-out 不降 |
| 1 | +SSG/TLE 标签 | 谓词/步骤状态稳 | 谓词 F1 +5 |
| 2 | +PGL 锚点渲染 | 学会用锚点 | 离线锚点跟随误差达标 |
| 3 | +ICR 上下文 | 不崩、增益>0 | 终局段离线误差 −10% |
| 4 | +OPT 位姿（推理统计） | 放置误差降 | 见 7.1 验收 |
| 5 | +SVL 策略（重试/修复） | 终局成功率涨 | 本地 +5pp |
| 6 | +NRB 恢复 | 撤销后可恢复 | 恢复成功率 >50% |
| 7 | 全量 + 蒸馏/量化 | 延迟达标 | p99 <100ms |

### 6.2 超参（沿用第 5 轮）

WLA-1.0-Base 6B；LoRA rank 64/alpha 128；action expert 全量或 LoRA；AdamW，lr 1e-4（LoRA）/2e-5（全量），cosine，warmup 3%；global batch 64–128；bf16；chunk 16–32、horizon 1–2s；早停看真实 held-out + 轴诊断，不看仿真成功率。

### 6.3 算力

TLE 抽样标注（32 任务 × 300 条）8×H100 约 4–6 天；OPT/ICR 库构建 2–3 天；全课程 LoRA 2–3 周；ICR 缓存编码 1–2 天。单卡 24GB 仍可走"SSG+PGL+OPT+SVL"的纯推理增强路线（无检索/无重训），是最小可运行版。

---

## 7. 评测协议：平台调试回路 + TCLB 降级

### 7.1 三级评测

1. **离线（每天）**：held-out 演示上的放置位姿误差、锚点跟随误差、谓词 F1。验收：OPT 迁移后释放位姿在 τ_task 内的比例 ≥80%。
2. **本地（每周）**：TCLB 降级为"离线相对比较台"（32×5×2，孪生/回放混合），只做失败挖掘，不做模型选择；保留真机校准子集存在性，但不再是主回路。
3. **平台（版本门）**：不计分单任务调试槽。约定：每个大版本 1 槽；首选 T27（叠碗=放置门控）、T10（插排=插入力控）、必要时 T19（拉链=闭合终局）。判定：终局步成功率 ≥ +10pp 且无回归才允许进计分跑。

### 7.2 计分跑策略

- 计划 2 次：W7 中期、W8 终期；若只允许 1 次，则 W8 唯一一次。
- 提交前 4h soak：N 端口并发、状态隔离、健康检查、延迟 p99；把 FLEET 的事实做成检查单（不是研究轴）。

---

## 8. 实验矩阵与消融

### 8.1 主实验

| ID | 配置 | 验证 |
|---|---|---|
| E0 | WLA 基线 | 复现 |
| E1 | +SSG | 步骤状态/防跳步 |
| E2 | E1+PGL 锚点 | 锚点使用增益 |
| E3 | E2+OPT | 放置误差/终局成功率 |
| E4 | E3+ICR | 上下文增益/延迟 |
| E5 | E4+SVL | 释放/稳定性 |
| E6 | E5+NRB | 撤销恢复 |
| E7 | 全量 + 蒸馏 | 部署 |

### 8.2 消融

K∈{1,2,4,8}；锚点 on/off；关系键 vs 全局外观键（验证背景轴）；SVL on/off/预算；OPT 迁移 vs 直接 policy 输出；NRB 备注剧本 vs 随机扰动；SSG 门控 vs 无门控。

### 8.3 诊断矩阵

任务 × 轴热力图 + **步骤级成功率表**（每任务每步的完成率，直接来自评分步骤定义）——这是本轮新增的最有价值的诊断视图：它可以直接指出"钱丢在哪一步"。

---

## 9. 创新点清单（持续迭代；动机/差异/可行性/资源/步骤/风险/状态）

> 状态说明：押注=本轮主线；保留=沿用；升级=旧点被改造；降级=保留但不再是主回路；砍=不做。

### I1 SSG 评分步骤图门控（新增，押注）
- 动机：官方已公开步骤+权重；成功=全步骤；防跳步/假完成，且给出"钱丢在哪步"。
- 差异：现有 VLA 无显式步骤状态；我们不改官方指令，只在内部把指令翻译成步骤图。
- 可行性：确定性代码 + 一个学习谓词头；32×5 复述可精确匹配。
- 资源：无额外数据；CPU；1 人周。
- 步骤：解析 info.json → 图 → 谓词头（TLE 标签）→ reset 状态机接线。
- 风险：谓词噪声 → 用演示统计校准；语言未覆盖 → 嵌入兜底。

### I2 PGL 放置目标阶梯 + 锚点渲染（新增，押注）
- 动机：Spa-Bench 证明 OOD 空间 grounding 是主要瓶颈；AnySlot/SpaceVLA 证明显式视觉目标显著提放置精度。
- 差异：把"语言→坐标"换成"语言→槽位→渲染锚点→度量位姿"三级；训练/推理同分布 overlay。
- 可行性：渲染与投影都是确定性代码；评测接口允许我们缩放/裁剪图像。
- 资源：SAM 类检测器（许可逐个核）；无重训也有效（最小版）。
- 步骤：投影工具 → 演示 overlay 生成 → 混入训练 → 调试槽验证。
- 风险：锚点域差（训练/推理渲染不一致）→ 双层一致性检查。

### I3 OPT 少样本放置位姿迁移（新增，押注）
- 动机：33k 演示里已有"释放位姿"；K 条统计即可跨场景迁移，零梯度、单模型。
- 差异：迁移的是容器系相对位姿统计+离散度（控制风格），不是轨迹复制；τ_task 从演示分布自动估。
- 可行性：数据字段齐（EE base 位姿 + 容器可检测）；已有同构证据（FlowRetrieval/ICI-VLA）。
- 资源：容器 6D 位姿估计（FoundationPose 类或关键点 PnP）；8×H100 数天建库。
- 步骤：TLE 容器位姿 → H_i 库 → 在线检索 K → 执行/伺服/退化三级。
- 风险：透明/布料容器失效 → 分桶回退到 ICR 相位先验。

### I4 ICR 上下文检索条件化（新增，押注）
- 动机：2026 检索式 VLA 证据一致（+17~21pp 级别）；官方 33k 是现成少样本库。
- 差异：键=关系+运动（抗背景/位置 OOD），相位用 SSG 标签对齐；训练期同步注入上下文。
- 可行性：缓存独立编码（RA-VLA）控延迟；26 万段缓存 <1GB。
- 资源：编码算力（8×H100 1–2 天）；ANN（HNSW）。
- 步骤：切段 → 建键 → 缓存 → 训练注入 → 延迟压测。
- 风险：延迟 p99 超标 → 降 K/降维/预取；透明任务键失效 → 回退。

### I5 SVL 落点 settle-verify 闭环（新增，押注）
- 动机：终局步是闸门；释放失败（掉落/弹跳/未到位）靠"放完就完"无法发现。
- 差异：把"释放"当成需要验证与修复的阶段（缓放→稳定检测→nudge/regrasp）。
- 可行性：腕部相机 + 谓词头即可；180s 预算够 1–2 次。
- 资源：无新增数据（演示含自然重试片段可挖）。
- 步骤：稳定性检测器 → 修复动作库 → 预算守卫 → 与 SSG/NRB 接线。
- 风险：耗时 → 长程任务限 1 次；误判 → 双阈值（位移+谓词）。

### I6 NRB 官方备注忠实恢复（升级 RB）
- 动机：human 轴备注公开，且多为"平移/撤销"剧本；直接对应评测。
- 差异：从"自造干扰原语"升级为"官方剧本回放 + 通用扰动兜底"。
- 可行性：备注多为 1-DOF 刚体变换，合成/回放便宜。
- 资源：ACP/孪生 2.5D 管线（第 5 轮）。
- 步骤：备注表→场景脚本→恢复对→加权训练→可逆信念联动。
- 风险：备注编号含义未核实 → 训练同时覆盖通用扰动。

### I7 L2L 产学研数据协议（新增，中优先）
- 动机：背景/位置轴的本质是场景多样性；实验室网络是最便宜的多样性来源。
- 差异：把"合作"变成逐字段对齐的采集协议 + QA + 许可 + 署名激励。
- 可行性：高校 G1 保有量与遥操作管线已被公开证实（[S27][S28]）。
- 资源：3 实验室 × 2 任务 × 100–200 条；协调 2–3 人。
- 步骤：协议→试点 1 实验室→QA→合规开关→并入训练。
- 风险：规则未明确（外部数据）→ 默认 OFF；硬件异构 → 限定 G1+Dex1。

### I8 DebugLoop 平台调试回路（新增，工程策略）
- 动机：比自建孪生更可信的真机反馈；发布门控。
- 差异：把"不计分单任务调试"模式制度化使用（预算、任务选择、判定标准）。
- 可行性：官方 profile 页已提供（[S8]）；次数未知。
- 资源：预约与管理；少量真机时段。
- 步骤：任务选择（T27→T10→T19）→ 判定标准 → 记录表单。
- 风险：资源稀缺/规则变化 → 每个大版本最多 1 槽。

### I9 GPR-VLA 主干 + WLA 底座（保留）
- 动机：谓词残差 + 可逆信念与评分结构天然对齐；Apache-2.0、单卡可微调。
- 差异：不变，作为唯一学习模型承接 SSG/PGL/OPT/ICR 的接口。
- 风险：底座微调不充分 → LoRA 分级。

### I10 TLE/ACP/GF 数据引擎（保留，修剪）
- 动机：真实锚定的反事实仍是最便宜的轴数据。
- 差异：本轮只服务放置场景（容器/目标/路径邻近）。
- 风险：合成负迁移 → GF 软权重 + 真实混采。

### I11 AH-TP / Endurance Governor / Compliance Compiler（保留）
- 作用：谓词时长监督、180s/长时服务守卫、数据来源开关与单模型审计。

### I12 TCLB（降级）
- 从"主评测台"降为"离线相对比较台"；不再承诺真机校准子集为主回路。

### I13 FLEET 工程检查单（降级｜第 6 轮遗产）
- 保留事实：N 端口连续 8765、每端口独立、状态隔离、RTC 式延迟弹性、健康检查。
- 不再当作"第六轴"研究贡献。

### 已砍清单（跨轮）
- 全 32 任务高保真孪生；自由仿真数据；运行时仿真/MPC；仿真 RL；布料/拉链/透明全物理；WMA-0 进主路径；每任务 LoRA/模型合并。

---

## 10. 风险、合规与开关

| 风险 | 概率 | 影响 | 缓解 | 停止条件 |
|---|---|---|---|---|
| 终局瓶颈假设不成立 | 中 | 高 | 先用离线步骤级诊断 + 1 个调试槽验证 | 终局步提升 <5pp → 回退 SSG+SVL |
| OPT 容器位姿估计失败（透明/小件） | 高 | 中 | 分桶回退到 ICR/锚点伺服 | 位姿误差 >1cm → 该任务退出 OPT |
| ICR 延迟超标 | 中 | 高 | 缓存/降 K/降维/预取 | p99 >100ms → 关 ICR |
| 锚点域差 | 中 | 中 | 训练/推理同渲染管线；双层一致性抽检 | 离线跟随误差不降 → 关锚点 |
| 调试槽不可用/成本高 | 中 | 中 | TCLB 降级兜底；发布门改为离线+小规模 | 无法验证 → 保守提交 |
| 外部数据/合作违规 | 低 | 高 | 邮件确认；默认 OFF | 明确禁止 → L2L 转赛后 |
| SVL 误判/耗时 | 中 | 中 | 双阈值 + 预算守卫 | 触发总时长超限 → 关闭 SVL |
| 单模型审计 | 中 | 高 | 学习组件唯一；其余确定性代码；模型卡写清 | 审计不过 → 去 ICR 动作先验 |
| 统计噪声 | 高 | 中 | 320 trials + 配对种子 + bootstrap | CI 跨 0 → 不上线 |

```yaml
policy:
  data_policy: labels_only | counterfactuals | full     # 默认 labels_only
  external_lab_data: false                              # 邮件确认后开
  retrieval_context: true                               # 数据，不是模型
  anchor_overlay: true
  settle_verify: true
  debug_loop_budget_per_release: 1
```

---

## 11. 修订版 8 周计划

| 周 | 目标 | 交付 | Go/No-Go |
|---|---|---|---|
| W1 | SSG + 脚手架 + 基线 | 32 任务步骤图；指令映射（160 复述）；E0 基线；预约调试槽 | 步骤谓词 F1 起步 |
| W2 | TLE 抽样 + OPT 库 | 8 放置任务 H_i 库与 τ_task；离线锚点渲染 | 释放位姿 τ 内 ≥80% |
| W3 | PGL+ICR 离线 | overlay 训练；检索键与缓存；延迟压测 | p99 <100ms |
| W4 | SVL + NRB | 修复/重试策略；官方备注剧本 32 集 | 本地终局步 +5pp |
| W5 | 训练 E1–E5 | 课程 1–5；调试槽 #1（T27） | 真机终局步 +10pp |
| W6 | L2L 首轮 + E6 | 1–2 实验室数据并入；恢复训练；调试槽 #2（T10） | 恢复 >50%；无回归 |
| W7 | 全量 + 计分跑 #1 | E7 训练；soak；提交 | 总分 +3pp 目标 |
| W8 | 迭代 + 最终提交 | 修复计分跑暴露的问题；模型卡；终版提交 | 部署稳定；审计通过 |

**里程碑**：M1（W2）OPT 离线达标；M2（W4）本地终局 +5pp；M3（W5/W6）调试槽真机 +10pp；M4（W7）计分跑；M5（W8）冻结。

---

## 12. 来源（检索/核对日期 2026-10-24）

| 编号 | 来源 | URL | 用途/备注 |
|---|---|---|---|
| S1 | UniBot 挑战赛任务页 | `https://unibot.unitree.com/challenges.html` | 32 任务、32k/169h、任务视频与描述 |
| S2 | 任务 specs（32 个） | `https://unibot.unitree.com/tasks_v2/<slug>/info.json`（例：`stack_bowls_three`、`place_photo_frames`） | score_steps 权重、难度、generalization 备注 |
| S3 | HF collection | `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset` | 32 数据集、约 33k、169h |
| S4 | HangCup 数据集 | `https://huggingface.co/datasets/unitreerobotics/G1_Dex1_HangCup` | meta/info.json（1043 条/194,564 帧/30fps）；lastModified 2026-10-14 |
| S5 | tasks.parquet（HangCup/StackBowls/ZipUp/PlugCharger） | 同数据集仓库 `meta/tasks.parquet` | 每任务 5 条英文复述（`@` 分隔） |
| S6 | 提交模板 README | `https://github.com/unitreerobotics/unibot_submission` | 观测/动作目录、obs_delta_indices、image_resize、chunk、token |
| S7 | 提交仓库提交历史 | `https://github.com/unitreerobotics/unibot_submission/commits/main` | v2：2026-08-21（跳帧堆叠/图像缩放/序列化） |
| S8 | 我的主页（提交测试） | `https://unibot.unitree.com/profile.html` | 计分多任务 / 不计分单任务调试两种模式 |
| S9 | 运行记录 | `https://unibot.unitree.com/runs.html`、`https://unibot.unitree.com/details.html?...` | 256/256 占位；详情页视频占位 |
| S10 | 排行榜 | `https://unibot.unitree.com/leaderboard.html`、`https://unibot.unitree.com/leaderboard_data.json` | 仍 Coming Soon；`gen_leaderboard.py` 占位 |
| S11 | 首页 | `https://unibot.unitree.com/index.html` | "按平均成功率与步骤分综合排序"；多机评测集群愿景 |
| S12 | AnySlot | `https://arxiv.org/html/2604.10432v2` | 语言→生成式视觉目标→goal-conditioned VLA；零样本槽位放置；UR10e 82% |
| S13 | Spa-Bench | `https://arxiv.org/html/2610.12696` | 真机空间 grounding 基准；ID 67.5–73.3% → OOD 40.7–52.0%；直接操作指令 +28–40pp |
| S14 | ActGaze | `https://arxiv.org/html/2609.28955` | 反事实视觉干预的动作注意力监督；4 个毫米级任务 77.0→91.5% |
| S15 | SpaceVLA | `https://arxiv.org/html/2608.05730` | 抓/放锚点 overlay；放置误差 0.7cm；错锚点误差 5× |
| S16 | Acting in Meters | `https://arxiv.org/html/2609.18243` | 度量交互 token/场；RoboTwin 2.0 +3.59pp |
| S17 | ICI-VLA | `https://arxiv.org/pdf/2609.07581` | 微演示检索+DTW 对齐+防复制；RoboTwin 2.0 60.4%（+19.3pp）；真机双臂 83.2% |
| S18 | RA-VLA | `https://arxiv.org/html/2608.25585` | 检索增强 VLA 测试时适配；LIBERO +17.6pp、UR5e +20.8pp；缓存编码控延迟 |
| S19 | HSR | `https://arxiv.org/html/2608.24042v1` | 层级技能检索；LIBERO +10.3%、真机 +21.3% |
| S20 | Retrieval-VLA | `https://openaccess.thecvf.com/content/CVPR2026F/papers/Zhang_Retrieval-VLA_Training-Free_In-Context_Adaptation_for_Vision-Language-Action_Models_CVPRF_2026_paper.pdf` | 训练免费、物件中心关键点检索、抗 clutter |
| S21 | FlowRetrieval | `https://proceedings.mlr.press/v270/lin25a.html` | 光流运动相似度检索；比最佳检索前作 +27%；真机 3.7× |
| S22 | SAIL | `https://arxiv.org/abs/2603.08269v1` | 上下文模仿的测试时算力扩展（MCTS）；最高 95% |
| S23 | Retrieve, Don't Retrain | `https://arxiv.org/html/2606.15631` | 新任务=索引数据而非更新参数（NAVER） |
| S24 | Pointing-VLA | `https://arxiv.org/html/2608.23138` | 类型化空间 pointing 接口（抓点/接触点/目标区坐标） |
| S25 | WLA-1.0-Base | `https://huggingface.co/unitreerobotics/UnifoLM-WLA-1.0-Base`、`https://github.com/unitreerobotics/unifolm-wla` | 6B、Apache-2.0、24GB 微调 |
| S26 | 官方仿真/训练栈 | `https://github.com/unitreerobotics/unitree_sim_isaaclab`、`https://github.com/unitreerobotics/unitree_lerobot`、`https://github.com/unitreerobotics/unitree_mujoco` | 孪生/训练/快速物理 |
| S27 | 宇树产学研网络 | `https://www.qdc.edu.cn/unitree-college/`、`https://www.iedumedia.com/news/newsinfo/1675`、`https://www.iedumedia.com/news/newsinfo/1702`、`https://www.xit.edu.cn/stjq/2026/0526/c326a89066/page.htm`、`https://kjj.wuhan.gov.cn/xwzx_8/kjspxw/202601/t20260106_2707153.html`、`https://mp.weixin.qq.com/s/HhQkc9isqfwdkSzsXLYFtA` | 高校产业学院/联合实验室/数据采集中心 |
| S28 | 深蓝具身智能实验室 | `https://www.shenlanxueyuan.com/EmbodiedLab` | 高校侧 G1 遥操作/数据采集/GR00T 部署流水线示例 |
| S29 | 社区观察帖 | `https://www.linkedin.com/posts/leo-mrl_unitree-unitreerobotics-has-officially-start-activity-7495465349350420480-aIaz` | 2026-08-18：当时公开数据 "44 条"预览、远端评测形态描述 |
| S30 | GeoPredict（CVPR 2026） | `https://openaccess.thecvf.com/content/CVPR2026/html/Qian_GeoPredict_Leveraging_Predictive_Kinematics_and_3D_Gaussian_Geometry_for_Precise_CVPR_2026_paper.html` | 预测几何先验；训练监督、推理轻量 |

> 说明：`unibot.unitree.com` 直连 JSON 会间歇性触发风控（返回 HTML），本轮通过带浏览器 UA 的 curl + `r.jina.ai` 双通道抓取；HF 页面部分走直连 API。占位榜/运行记录的所有数字均不作排名依据。

---

## 13. 开放问题

1. 备注编号（human_1/human_4/unseen_object_3）是轴编号还是试次编号？评测是否就在这些剧本里采样？
2. 不计分单任务调试的可用次数/成本/是否随机化泛化条件？
3. 步骤分聚合公式（按 episode 部分分平均？取最好？）；排名中成功率与步骤分的权重。
4. N 台评测机器人的准确数量；每端口并发/延迟上限。
5. 语言指令是英文 5 复述之一，还是中文，还是未见复述？SSG 匹配的兜底强度需要知道。
6. 外部数据（自采/实验室数据）是否允许？预训练权重（含论文方法）是否允许？——邮件已备好。
7. 评测中允许的连续重试/自我中断上限（180s 之内）是否有隐藏规则。
8. 单模型定义边界：确定性代码（SSG/PGL/SVL）与检索库是否需在模型卡中披露。（倾向：全部披露。）
9. Isaac 资产与 SAM 类检测器的许可逐个核对。
10. 真实榜单发布后，重跑"终局闸门"假设（占位先验换真实数据）。

---

## 14. 一句话押注

**把评分结构当第一性依据：终局放置是 32/32 任务的成功闸门、约 60% 步骤分和唯一跨五轴同时起作用的杠杆；用"公开步骤图门控（SSG）+ 少样本放置位姿迁移（OPT）+ 视觉锚点（PGL）+ 落点闭环（SVL）"去攻它——这是本轮最值得押注的方向。**
<!-- ARTIFACT:END -->
