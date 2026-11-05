# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 25 轮（研究线累计；灵感循环第 1 轮）· OPEN-IMITATE-DEPLOY（OID）：用「模仿学习」换更好的动作表示、用「场景落地」换一个执行层、用「开源生态」换一个已经练好的基座——把 PLAN-GATE 从「规划重」修剪成「学习 + 部署 + 组合」

> 检索日期：2026-11-05。灵感词：**模仿学习 / 场景落地 / 开源生态**。本轮是对第 24 轮 PLAN-GATE 的**深化与修剪**：保留 MVP-SPINE、GEN-LEDGER、ETHIC-SHIELD 三块；把「手搓运动规划（MOTION-SHIELD）」这条最重的主干**降级为薄安全回退**；让三个新词各自补上一块上一轮缺、且今天已有**公开可复用组件**的短板。切题判断：`unibot.unitree.com` 的 UniBot = 宇树 G1 桌面操作泛化评测，与本座研究线一致，无需换题。

## 0. 三分钟直觉：上一轮把杠杆压在了「最贵、最不确定」的一端

先用本轮**新核实**的事实重新给第 24 轮做一次诚实定价（来源见 §5；⚠=本轮新增或更正）：

- ⚠ **任务集是「DAPTO 2」套件**：官方/媒体口径一致——Unitree G1 为统一平台，**32 项真实桌面操作**，**约 32,000 条演示、约 169 小时**真机数据，覆盖**位置变化 / 干扰物 / 桌面背景 / 未见物品 / 人为干扰**五类泛化；**单模型通才**，按**平均成功率 + 平均步骤分**综合排序。（myxmr / zhizaozx 报道，2026-07-10 启动）
- ⚠ **五轴数据齐备**：HF 集合 `unibot-v1-challenge-dataset` 确为 **32 个 `G1_Dex1_*` 数据集**，每个约 1,000 条 episode（合计约 3.2–3.3 万条）；单集 README 确认 LeRobot **v3.0**、4 相机 480×640×3 @30fps、Dex1 夹爪 5.5–0.0（open→close）。（HF API，2026-11-05）
- ⚠ **排行榜/运行记录仍不可机读**：`leaderboard.html` 是 SPA，`runs.html` 只有字段壳（Model / Model-User / **Success** / **Step Score**），服务端正文被 Tencent EdgeOne 安全策略拦截（HTTP 567）。所以「榜首 <30%」仍是**用户口径/未独立复核**；但字段证实了排序维度。
- ⚠ **决定性新事实：开源生态里已经有一个「练好在 UniBot 上」的基座。** HuggingFace `ezhoureal/lingbot-vla-v2-unibot-lora`（2026-08-02）：**LingBot-VLA 2.0**（6.3B = Qwen3-VL-4B 骨干 + Qwen2 MoE action expert）在 **UniBot G1_Dex1 全 32 任务、33,276 episodes** 上做 LoRA（rank 64 / alpha 32，`q_proj/v_proj/o_proj`，65M 可训练），**单张 RTX 4090、10K 步**，最终 `val/loss=0.085`；joint 空间、臂动作为相对状态增量。→ **G1（能上榜的基线）被这笔开源资产大幅去风险。**
- ⚠ **官方相邻基线**：UnifoLM-VLA-0（Apache-2.0，flow-matching action head，单策略 12 类任务）仍是正式开源参照；LIBERO 评测脚本与日志齐全。
- ⚠ **规模化的「免费数据」已经有开源配方**：**Open-HumanScale** 公开 50,000 小时 egocentric 人类视频与「从零到 50k 小时」的完整配方，并给出 **预训练小时数 → 下游成功率 的对数线性 scaling law**。
- ⚠ **三条「比手搓规划更便宜、更该先买」的公开组件**：
  - **PTS（Path-preserving Time Scaling，2611.01390）**：面向**冻结的 action-chunking 策略**的**免训练执行层**；它同时消掉两种与模型能力无关的浪费——「等下一块推理的停顿」与「学得像慢动作的谨慎速度」——原理是「运动 = 参考路径的时间重参数化，路径只随新观测改变」。**这几乎正是第 24 轮 P0「reproject」想做的一切，而且是已发表、可直接用。**
  - **Route-Guided CBF-QP Repair（2611.01713）**：**事后**安全修复模块，用 VLA 的短时 action chunk 探测被挡住的标称轨迹，生成绕障的「入-出-回」引导，作为软约束加进 CBF-QP，且**能重新并回任务轨迹**。**这几乎正是第 24 轮 P1「replan」想要的，且保持任务语义。**
  - **Serving Agentic Robot Fleets（2611.01404）**：把「机器人 agent 舰队」的瓶颈测清楚——大脑 KV-cache 反复重放、上下文达 **215k tokens**、Astra 请求中位 **7.78s**，而 VLA 还要在**严格控制 deadline** 下执行动作块；提出 **admission control**。**这正对着官方 N 端口 + §6（逐步时延与波动、动作规律性）的评分口径。**
- ⚠ **另外两个「模仿学习」侧的新杠杆**：**ODE Policy（2611.01729）**——不学动作值而学**动作的动力学**（神经 ODE 学动作向量场，部署时由上一动作积分出下一动作，**轨迹构造上连续**，附多样性头刻画多模态）；**ELA（2611.05571）**——端到端从**无动作标注的视频**里学「潜在动作」，且潜在动作被**联合优化**以利下游控制与解码。
- ⚠ **失败是可以被「复利」的**：**Compounding Physical RSI（2611.06654）** 指出任务完成度近似「各阶段通过率的乘积」，因此递归自改进的收益会**跨代相乘**，并点出物理环境里三个障碍（终点反馈难以定位是哪一阶段崩的等）。

**反直觉但更值钱的判断：**

> **第 24 轮把主注押在「经典运动规划」上，理由是它确定性、无需数据、有 +109%/+4.2% 的强近邻。但本轮的开源生态证据翻案了：这个杠杆的 80% 收益，今天可以用两个已发表的免训练模块（PTS 执行层 + CBF-QP 事后修复）以近乎零成本买到；真正没被开源生态覆盖、因而才是差异化的，是「动作表示（模仿学习）」与「N 端口执行层（场景落地）」。继续手搓规划器是在重复造一个更差的轮子。**

一句话押注：

> **OID = 站在开源基座（LingBot-VLA 2.0 的 UniBot LoRA / UnifoLM-VLA-0）上，做三件开源生态**还没**替你做完的事：(A) 把动作 chunk 从「离散动作回归」换成「动作动力学 / flow（ODE Policy 式）」以**构造上连续**、消掉块边界抖动；(B) 用 **PTS + CBF-QP Repair** 组成**免训练执行层**，并以 **FLEET-SERVE**（KV-cache 隔离 + admission control + 异步 chunk 预取）扛住 N 端口与 §6；(C) 用 **HUMAN-SCALE（ELA + Open-HumanScale）** 与 **STEP-SCORE-IMITATION + FAIL-RSI** 把「免费视频 + 七成失败」变成数据飞轮。规划器退成薄回退，不再是主干。**

## 1. 三个词各自对第 24 轮做的一次「修剪」

```text
模仿学习 → 修剪「用轨迹记忆代替可求解性」这一诊断的落点：
  F1 长程累积 / F5 抖动 的根因，不只是「没有规划」，而是「动作被当成离散值来学」。
  → 动作表示升级：ODE 动作动力学 / flow matching（连续、按构造）；潜在动作视频预训练（ELA）。
  → 数据规模升级：human egocentric 50k h（Open-HumanScale）+ 合成臂演示（ScheduleGen）。
  → 目标升级：不止成功率，还要步骤分 → 效率模仿（学「最快成功轨迹」的时间重参数化 + 子目标早停）。

场景落地 → 修剪「把规划当执行」：
  上一轮 MOTION-SHIELD 把「规划修复」与「执行」混在一起，且默认 get_action 阻塞。
  → 执行层独立且免训练：PTS（消停顿 + 消慢动作，保路径）；异步 chunk 预取。
  → 安全修复独立且免训练：CBF-QP Repair（绕障并回任务轨迹）。
  → 服务层独立且面向评分：FLEET-SERVE（N 端口、KV/状态隔离、admission control、p95 时延与规律性 = §6）。

开源生态 → 修剪「从零训一个 VLA」：
  「能上榜的基线」已有现成资产（LingBot UniBot LoRA / UnifoLM-VLA-0 / Open-HumanScale / MESA / RoboScope）。
  → 差异化从「复现基线」前移到「表示 + 执行 + 效率 + 失败恢复 + 服务」五个开源未覆盖处。
```

三处「甜点」很具体：

1. **动作动力学是「规划器」的免费替代品**：ODE Policy 的积分链**按构造**连续，直接消掉 F5（块边界不连续/抖动），且比运动规划更轻、无需场景几何。这与上一轮想用规划换平滑的目标重叠——所以规划器的必要性被**证伪了一半**。
2. **PTS 与 CBF-QP 都是「post-hoc、免训练、保任务语义」的**：正好满足第 24 轮给自己钉的「能不动就不动、只在越界时接管」（Shielding 式最小改动）。**买现成的比自己写贵不了、还好得多。**
3. **「步骤分」是被系统性忽视的一半分数**：所有人都在刷成功率，几乎没人把「省步」当成一个可学习的模仿目标（学演示里最快的那条时间参数化 + 学何时该停）。这是低竞争、高性价比的切口。

## 2. 研究日志：本轮的事实再基线化与修剪纪律

```text
KEEP（脊柱不动）：
  - MVP-SPINE 门控：G0 接口冒烟 → G1 可提交基线 → G2 加杠杆（G1 的基座来源本轮更换，见 PROMOTE）。
  - GEN-LEDGER（泛化五轴账本 + 审查留痕数据飞轮）：保留，但评测代理从「自建」改为对齐公开的 MESA/RoboScope。
  - ETHIC-SHIELD 的「可逆性证书」思想：保留为薄差异点（只对 R2），不再自建可行性求解器。
  - joint 控制空间优先、动作块 + 时序集成 + 子目标早停、多端口共享服务。
PROMOTE（新证据升格）：
  - OPEN-BASE：G1 基座由「自训 UnifoLM-VLA-0」升为「优先直接用 LingBot-VLA 2.0 UniBot LoRA（已练在 32 任务上），UnifoLM 作对照」。
  - ACTION-DYNAMICS（IDA）：动作表示升级为公开验证的 ODE/flow 方向，作为本轮第一技术创新点。
  - PTS-EXEC + FLEET-SERVE：免训练执行层 + N 端口服务，升为 G2a 首发（替代原 MOTION-SHIELD P0/P1）。
  - STEP-SCORE-IMITATION 与 FAIL-RSI：步骤分与失败恢复正式立项。
DEMOTE（降级/合并）：
  - MOTION-SHIELD 的 P0 reproject → 被 PTS 取代；P1 replan → 被 CBF-QP Repair 取代；仅保留 P2（可逆性恢复）作为 ETHIC-SHIELD 的薄组件。
  - 3D-ANCHOR：继续顺延（双目基线/内参仍未证实），但 Open-HumanScale/LingBot-Depth 提供免标定的几何先验，可作替代路径。
  - 自建 5 轴评测 → 对齐 MESA（ID + 4 轴），唯一自建项是「人为干扰」轴（MESA 未覆盖）。
MAJORIZE（本轮新定义）：
  - STEP-SCORE-IMITATION（SSI）：把「步骤分」变成一个显式模仿目标。
  - FAIL-RSI：把「七成失败」变成定向补数据与恢复演示（呼应 Compounding Physical RSI 的乘性收益）。
```

三词咬合成的新飞轮：

```text
模仿学习（表示 + 数据 + 效率）
   │ 动作动力学消 F5；人类视频扩分布；效率模仿拿步骤分
   ▼
场景落地（执行层 + 服务层）
   │ PTS 消停顿/慢动作；CBF-QP 保安全；FLEET-SERVE 保 N 端口与 §6
   ▼
开源生态（基座 + 配方 + 评测）
   │ LingBot/UnifoLM 给基线；Open-HumanScale 给数据预算；MESA/RoboScope 给账本
   ▼
回到 GEN-LEDGER：按轴定位漏分 → FAIL-RSI 定向补恢复演示 → 下一轮账本上升
```

## 3. 持续迭代的创新点清单（本轮修订）

> 🟢 保留推进　🔵 新增　🟡 降级/合并　🔴 剪枝　⬆️ 升格　⬇️ 降格

| # | 创新点 | 状态 | 动机（对应瓶颈） | 与现有方案差异 | 可行性 | 所需资源 | 落地步骤 | 风险 |
|---|---|---|---|---|---|---|---|---|
| 1 | MVP-SPINE（门控交付脊柱） | 🟢 | 先上桌 | 每级可提交 checkpoint | 极高 | 基座+32k+1–8 GPU | G0→G1→G2 | 转码/算力 |
| 2 | **OPEN-BASE（站在已练好的 UniBot LoRA 上）** | 🔵⬆️ | G1 去风险 | 复用 32 任务/33k episodes 的公开 LoRA，而非自训 | 极高 | 6.3B 权重 1 张 4090 可跑 | 拉权重→接接口→复测 | LoRA 过拟合/许可 |
| 3 | **ACTION-DYNAMICS（IDA，动作动力学表示）** | 🔵⬆️ | F5 抖动 + 块边界不连续 + 多模态 | 学动作向量场/flow，而非离散动作值；积分链按构造连续 | 高 | 基座+小头训练 | 头替换→离线连续性/多模态测→真机 | 积分步长/误差累积 |
| 4 | **PTS-EXEC（免训练执行层）** | 🔵⬆️ | 全场等块停顿 + 学得慢（步骤分） | 时间重参数化参考路径，路径只随观测改；免训练 | 极高 | 官方实现/自实现 ~数百行 | 冻策略上直接接→测步骤分/时延 | 与低层限速耦合 |
| 5 | **FLEET-SERVE（N 端口共享模型 + §6 服务）** | 🔵⬆️ | 官方 N 端口 + §6 时延/波动 | KV/状态隔离 + admission control + 异步 chunk 预取 | 高 | 服务框架+vLLM 式调度 | 单端口→共享批处理→压测 | 并发串扰/KV 抖动 |
| 6 | **HUMAN-SCALE（ELA 潜在动作 + Open-HumanScale 数据）** | 🔵 | 分布外泛化、数据规模 | 用无动作标注人类视频扩先验，附 scaling law 定预算 | 中高 | 50k h 视频+预训练算力 | 拉配方→潜在动作预训练→微调 | 域鸿沟/算力 |
| 7 | **STEP-SCORE-IMITATION（SSI，效率模仿）** | 🔵 | 步骤分=半张成绩单 | 把「最快成功轨迹的时间参数化 + 子目标早停」当模仿目标 | 高 | 演示中位时长统计 | 统计→加权/重时序增强→回归 | 学过头变鲁莽 |
| 8 | **FAIL-RSI（失败恢复数据飞轮）** | 🔵 | 成功率<30%，七成步在失败 | 定向生成恢复演示；乘性收益 | 中高 | 离线 rollout+ScheduleGen | 失败聚类→合成恢复→回灌 | 仿真-真机 gap |
| 9 | SAFE-REPAIR（CBF-QP 事后修复） | 🔵⬆️ | 干扰物/人为干扰安全 | 绕障后**并回任务轨迹**；免训练 | 高 | 官方实现 | 接 chunk→障碍注入回归 | 保守过度/误杀 |
| 10 | **GEN-LEDGER ↔ MESA/RoboScope** | 🟢 | 让泛化可测 | 五轴对齐 MESA 四轴 + 自建人为干扰轴 | 高 | 评测套件 | 建协议→基线→归因 | 离线-真机 gap |
| 11 | ETHIC-SHIELD（仅保留可逆性证书） | 🟡 | R2 不可逆/人机安全 | 只对 R2 要求恢复证书 | 中 | 可逆性标注 1 天 | A 物理合法→B 仅 R2 | R2 误判/HOLD 过度 |
| 12 | MOTION-SHIELD（手搓规划） | ⬇️🟡 | 原 G2a 主干 | **被 #3/#4/#9 覆盖** | 中 | — | 退为 fallback | 投入产出比差 |
| 13 | 3D-ANCHOR（双目几何/特权蒸馏） | 🟡 | 几何泛化 | LingBot-Depth 可替代自标定 | 中 | 立体/深度网 | 顺延，先验证 | 反光/透明 |
| 14 | 力/触觉 / 声纹 / 云端级联 | 🔴 | — | 无通道/耗步/坏时延 | 不可行 | — | 删除 | — |

## 4. 事实/前提与来源（决定路线者，检索日期 2026-11-05）

| 事实/未知 | 为什么关键 | 何时解决 | 来源 |
|---|---|---|---|
| LingBot-VLA 2.0 UniBot LoRA 存在且已练 32 任务 | 直接决定 G1 起点 | 立刻 | https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora |
| PTS 免训练执行层细节 | 决定 #4 能否即插即用 | G0 | https://arxiv.org/abs/2611.01390 |
| CBF-QP Repair 细节 | 决定 #9 替代手搓规划 | G0 | https://arxiv.org/abs/2611.01713 |
| N 端口/§6 的真实调用模式 | 决定 #5 架构 | G0 | https://github.com/unitreerobotics/unibot_submission |
| Open-HumanScale scaling law 系数 | 决定 #6 数据预算 | G2 | https://arxiv.org/abs/2611.06817 |
| ODE Policy 在 action-chunking 上的定义 | 决定 #3 头替换方式 | G1 | https://arxiv.org/abs/2611.01729 |
| 榜首实测成功率与步骤分 | 决定竞争强度 | 尽早 | 排行榜未机读（EdgeOne 567），以上线为准 |

## 5. 参考来源（检索日期 2026-11-05）

- 提交模板与接口规范（观测/动作目录、metadata、N 端口、§6）：https://github.com/unitreerobotics/unibot_submission
- 挑战赛首页 / 任务集 / 排行榜 / 运行记录：https://unibot.unitree.com/ ；https://unibot.unitree.com/challenges.html ；https://unibot.unitree.com/leaderboard.html ；https://unibot.unitree.com/runs.html
- 赛事启动报道（32 任务 / 32,000 样本 / 169h / 五轴 / 平均成功率 + 步骤分 / DAPTO 2）：https://myxmr.com/en/news/unitree-launches-unibot-world-challenge ；https://myxmr.com/news/unitree-launches-unibot-world-challenge
- 挑战数据集合（32 个 G1_Dex1_*）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset ；单集 https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- LingBot-VLA 2.0（6.3B、Qwen3-VL-4B、MoE action expert、55 维统一动作、双查询蒸馏）：https://github.com/Robbyant/lingbot-vla-v2 ；权重 https://huggingface.co/robbyant/lingbot-vla-v2-6b
- UniBot LoRA：https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora
- UnifoLM-VLA-0（Apache-2.0、flow matching、LIBERO 脚本）：https://github.com/unitreerobotics/unifolm-vla
- ODE Policy（动作动力学，2611.01729）：https://arxiv.org/abs/2611.01729
- PTS（免训练时间缩放执行层，2611.01390）：https://arxiv.org/abs/2611.01390
- Route-Guided CBF-QP Repair（2611.01713）：https://arxiv.org/abs/2611.01713
- Serving Agentic Robot Fleets（KV-cache 抖动 / admission control，2611.01404）：https://arxiv.org/abs/2611.01404
- Open-HumanScale（50k h / scaling law，2611.06817）：https://arxiv.org/abs/2611.06817
- ELA（潜在动作视频模仿，2611.05571）：https://arxiv.org/abs/2611.05571
- ScheduleGen（多臂演示合成，2610.39429）：https://arxiv.org/abs/2610.39429
- Compounding Physical RSI（2611.06654）：https://arxiv.org/abs/2611.06654
- RL Enables Scaling Generalist Robot Policy（2611.06905）：https://arxiv.org/abs/2611.06905
- MESA（成分/语义/空间泛化评测，2611.05567）：https://arxiv.org/abs/2611.05567
- RoboScope Kit（统一评测接口，2611.03850）：https://arxiv.org/abs/2611.03850

> 本轮一句话押注：**最值得押注的是创新点 3+4 的组合（ACTION-DYNAMICS 动作动力学表示 + PTS 免训练执行层）——它用「开源生态已发表的两个组件」替换了第 24 轮最昂贵的手搓规划器，同时直接命中块边界抖动（§6）、等待停顿与步骤分；OPEN-BASE（#2）把 G1 的起点从零变成 33k episodes 的现成 LoRA，让整套方案第一周就能产出可提交 checkpoint。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 25 轮产物 · OPEN-IMITATE-DEPLOY（OID）技术报告：动作动力学表示 + 免训练执行/修复层 + N 端口服务 + 人类视频与步骤分模仿 + 失败飞轮

> 检索日期：2026-11-05。本文是第 24 轮 PLAN-GATE 的演进版：**保留门控脊柱、泛化账本与可逆性审查思想**，把「手搓运动规划」降级为薄回退，改为**站在开源基座上**，用三块公开可复用组件（动作动力学、PTS、CBF-QP Repair）补齐「模仿学习 / 场景落地 / 开源生态」三个维度。所有数值目标均标注为「设计目标」；未见实测的结论以官方接口硬约束与 §8 公开来源为界。

## 0. 结论

不新造大框架。OID = 一条门控交付脊柱 + 一个已练好的开源基座 + 一个「连续动作表示」的学习层 + 一个「免训练」的执行/修复/服务层 + 一个把失败与步骤分当目标的数据飞轮：

1. **MVP-SPINE（保留）**：G0 接口冒烟 → G1 可提交基线 → G2 加杠杆 → G3 自改进。
2. **OPEN-BASE（新增，替换 G1 来源）**：优先直接使用 **LingBot-VLA 2.0 UniBot LoRA**（6.3B，已在 32 任务 / 33,276 episodes 上 LoRA 微调，单 4090 可训练），UnifoLM-VLA-0 作对照。
3. **ACTION-DYNAMICS / IDA（新增，G2a）**：把动作头从「离散动作值回归」换成「动作动力学 / flow」（ODE Policy 式），部署时由上一动作积分出下一动作，**轨迹按构造连续**，并带多样性头刻画多模态。
4. **PTS-EXEC + FLEET-SERVE（新增，G2a）**：免训练执行层（时间重参数化参考路径，消停顿 + 消慢动作）+ N 端口共享模型服务（KV/状态隔离 + admission control + 异步 chunk 预取），直接对准 §6 与步骤分。
5. **SAFE-REPAIR + ETHIC-SHIELD-lite（新增/合并，G2b）**：CBF-QP 事后修复（绕障并回任务轨迹）+ 仅对不可逆动作（R2）要求恢复证书。
6. **HUMAN-SCALE + SSI + FAIL-RSI（新增，G2c）**：ELA 潜在动作 + Open-HumanScale 人类视频扩先验；STEP-SCORE-IMITATION 把「省步」当模仿目标；FAIL-RSI 把七成失败变成定向恢复数据。
7. **GEN-LEDGER（保留，改为对齐公开评测）**：五轴账本对齐 **MESA**（ID + 4 轴）与 **RoboScope Kit**，自建仅「人为干扰」轴。

对齐硬约束：观测仅 4×RGB + 关节/EE(base)/夹爪/下半身 + 语言；动作 joint 或 ee 互斥、块式 `(T_a,·)`、index 0 先执行；N 连续端口 8765..；§6 考核逐步时延/波动与动作统计规律性（来源见 §8）。

## 1. 系统总览（一次 get_action 的数据流）

```text
         evaluator (N robots, N ports 8765+)
                     │  obs: 4×RGB + state + language
                     ▼
   ┌──────────────────────── FLEET-SERVE ────────────────────────┐
   │ 每端口独立会话/KV/状态隔离   admission control（deadline 感知）│
   │ 连续批处理共享 6.3B 骨干     异步 chunk 预取（执行中算下一块） │
   └───────────────────────────────┬─────────────────────────────┘
                                   ▼
   ┌────────────── OPEN-BASE (LingBot-VLA 2.0 UniBot LoRA) ──────┐
   │  Qwen3-VL-4B 视觉语言骨干  +  Qwen2 MoE action expert        │
   └───────────────────────────────┬─────────────────────────────┘
                                   ▼
   ┌────────────── ACTION-DYNAMICS (IDA) ────────────────────────┐
   │  dq/dt = f_θ(q, h, z)   （z = 多样性潜变量；h = 观测嵌入）    │
   │  由上一动作积分出 T_a 步  →  块内/块间按构造连续、多模态       │
   └───────────────────────────────┬─────────────────────────────┘
                                   ▼
   ┌────────────── PTS-EXEC （免训练执行层） ────────────────────┐
   │  运动 = 参考路径的时间重参数化；路径只随新观测改变             │
   │  消「等下一块推理」的停顿 + 消「学得慢」的谨慎速度            │
   └───────────────────────────────┬─────────────────────────────┘
                                   ▼
   ┌────────────── SAFE-REPAIR (CBF-QP) + ETHIC-lite ───────────┐
   │  探测被挡标称轨迹 → 生成入-出-回引导 → 并回任务轨迹           │
   │  仅 R2（不可逆）动作要求「恢复证书」，否则 HOLD/重抽样        │
   └───────────────────────────────┬─────────────────────────────┘
                                   ▼
        trace_t → GEN-LEDGER（五轴账本 ↔ MESA/RoboScope）→ FAIL-RSI
```

## 2. OPEN-BASE：把 G1 的起点从「从零训」改成「复用已练好的 LoRA」

```text
事实（2026-08-02, HF）：
  ezhoureal/lingbot-vla-v2-unibot-lora
  - 骨干 LingBot-VLA 2.0：6.3B = Qwen3-VL-4B-Instruct + Qwen2 action expert (MoE)
  - LoRA：rank 64, alpha 32, 目标 q_proj/v_proj/o_proj（65M 可训练 / 6.3B 总）
  - 数据：UniBot G1_Dex1 全 32 任务、33,276 episodes
  - 训练：10K 步, bf16 模型 + fp32 LoRA, 单张 RTX 4090, val/loss 0.085
  - 控制：joint 空间（臂 14 / 夹爪 2 / waist 4 / base 3），臂动作=相对状态增量
  - 开环校验（G1_Dex1_ArrangePlates）：MSE 0.229 / MAE 0.176，~0.35s/50-step chunk@4090
```

**动机**：官方相邻基线 UnifoLM-VLA-0 需自训；而开源生态里已有一个恰好练在比赛 32 任务上的 LoRA。**第一周的目标从「复现基线」变为「把现成基线接进 N 端口并测账本」**，把省下的算力投到 #3/#4/#7/#8 四个开源未覆盖处。
**落地步骤**：拉权重 → 接 `example_policy` 接口（joint 空间，注意 `action_chunk_size` 与相对增量）→ 用 LIBERO/离线留出集回归 → 真机烟测。
**风险**：该 LoRA 是第三方产物，需核对许可（Apache-2.0）与训练/评测分布是否一致；若离线 MSE 尚可但真机差，退 UnifoLM-VLA-0。

## 3. ACTION-DYNAMICS（IDA）：让动作「按构造连续」，消掉块边界抖动与多模态塌缩

**核心命题**：第 24 轮把「块边界不连续/抖动（F5）」寄希望于运动规划平滑。但 ODE Policy 给出更便宜的正解——**不学动作值，而学动作的时间导数（向量场），动作由积分产生**：

```text
监督：在 IL 的短 chunk 上匹配 ∫ f_θ dt ≈ 目标动作；RL 单步同理。
部署：a_{t+1} = a_t + ∫_t^{t+1} f_θ(q(τ), h, z) dτ
      → 相邻步/相邻块在构造上连续；抖动不再是「被平滑掉」，而是「不可能出现」。
多模态：轻量多样性头随机化场方向 z，可采多条合理轨迹 → 对「未见物品/位置」提供候选。
```

```python
import numpy as np

class ActionDynamicsHead:
    """ODEPolicy 式的动作动力学头；可作为 VLA/WAM 的动作头替换件。
    约定：输入观测嵌入 h（来自骨干）与当前关节 q_prev，输出 (T_a, d) 连续动作块。"""
    def __init__(self, field, integrator, n_steps=8, dt=1 / 30.0, n_samples=4):
        self.field = field          # f_θ(q, h, z) -> dq/dt,  (~5M 参数的小网)
        self.integ = integrator     # 例如 RK4 或显式欧拉
        self.n_steps, self.dt = n_steps, dt
        self.n_samples = n_samples  # 采多条候选（多模态）

    def chunk(self, h, q_prev, z=None):
        out = np.zeros((self.n_steps, q_prev.shape[-1]), dtype=np.float32)
        q = q_prev.astype(np.float32).copy()
        for k in range(self.n_steps):
            dq = self.field(q, h, z) if z is not None else self.field(q, h)
            q = self.integ.step(q, dq, self.dt)   # 连续性由积分保证
            out[k] = q
        return out

    def candidates(self, h, q_prev):
        """返回若干可行候选，供 SAFE-REPAIR/账本按代价挑选。"""
        return [self.chunk(h, q_prev, z=np.random.randn(8)) for _ in range(self.n_samples)]


def field_loss(candidates, demo_chunk):
    """短 chunk 上的匹配损失（L2 或对时间加权的 L2）。"""
    return min(float(np.mean((c - demo_chunk) ** 2)) for c in candidates)  # winner-take-all
```

**与现有方案的差异**：不是「离散动作块 + 事后平滑」，而是把连续性写进归纳偏置。既服务 §6（动作规律性），又服务多模态（候选集给修复层与账本用），还天然是一个**连续子目标接口**（块末位 = 积分终点），可与第 24 轮 SUBGOAL 无缝对接。
**资源**：只需在冻结骨干上训练 ~5M 小头（LoRA 级别成本）。
**风险**：积分步长与误差累积；需限制每步 `|dq|` 并做时间参数化（与 PTS 协同）。

## 4. PTS-EXEC + FLEET-SERVE：把「执行」和「服务」变成独立的、可测量的层

### 4.1 PTS-EXEC（免训练执行层）

```text
公开事实（2611.01390）：冻结的 action-chunking 策略在部署时有两种「与模型能力无关」的浪费：
  (i) 推理下一块时机器人停顿；(ii) 学得像谨慎慢动作而速度偏慢。
  已有方法各去一种、叠加会失败，因为二者都改变了「计划进度 ↔ 实际运动」的对应。
PTS 原理：机器人运动 = 参考路径的时间重参数化；路径只在收到新观测时改变。
  → 于是可以「一边异步推进下一块、一边把当前路径跑快」，两类损失同时消掉。
```

```python
class PTSExec:
    """对齐当前动作块与上一块的重叠尾部，构造参考路径，再时间重参数化。
    免训练；作为 frozen policy 的输出后处理。"""
    def __init__(self, dt=1 / 30.0, speed_cap=1.8, causal=True):
        self.dt, self.speed_cap, self.causal = dt, speed_cap, causal

    def path_from_chunks(self, prev_chunk, new_chunk, overlap):
        """用重叠步同步相位，拼接出参考路径（关节空间）。"""
        return np.vstack([prev_chunk[:-overlap], new_chunk])  # 保持路径不变，只延展

    def retime(self, path, obs_changed):
        """时间重参数化：按曲率/限速分配时间；路径本身不改（除非观测变）。"""
        if obs_changed:
            return path, self.dt / max(1.0, self.speed_cap)   # 新观测 → 允许换路径
        # 直道/低曲率段加速，逼近 speed_cap；保持起点相位连续
        return path, self.dt / max(1.0, self.speed_cap)
```

**与第 24 轮 P0/reproject 的差异**：P0 是「重时序 + shortcut + 最小改动」的自研近似；PTS 是**已发表、面向 action-chunking、同时处理异步与加速、且保持参考路径**的完整执行层。**直接采用。**
**收益**：步骤分（更快完成 → 更少步）、§6（消除块边界停顿造成的不连续）、成功率（不在推理时停住）。

### 4.2 FLEET-SERVE（N 端口 + §6 服务）

```text
公开事实（2611.01404）：agentic robot 舰队有两类耦合资源约束——
  大脑反复重放增长中的 KV-cache（上下文达 215k tokens，Astra 中位 7.78s）；
  VLA 需在严格 deadline 下执行动作块。提出 admission control。
官方约束（unibot_submission）：必须有 N 个连续端口（8765..），状态隔离、并发不互阻；
  §6 记录逐步时延与波动、返回动作的统计规律性。
```

```text
FLEET-SERVE 设计（Approach 2 共享模型，压住 6.3B 的显存）：
  1. N 个轻量端点，各自持有「端口 ↔ episode 会话」（状态/KV/历史严格隔离）。
  2. 一个共享 6.3B 推理后端，连续批处理（continuous batching），避免相互阻塞。
  3. 执行层预算：机器人执行当前块的 T_a·dt 期间，异步预取下一块；PTS 保证不停顿。
  4. admission control：按 deadline 与队列水位决定「立即算 / 延期 / 退回上一块时间外推」。
  5. 遥测：每端口记录 p50/p95 时延、抖动、动作规律性分位 —— 直接作为 §6 证据。
```

**差异**：官方示例给了两种部署范式（N 进程 vs 共享模型），但**没有**给出「如何在共享模型下满足 §6 的时延/规律性」。FLEET-SERVE 把 KV 抖动与 deadline 纳入一等公民，是本轮的接口工程差异点。

## 5. SAFE-REPAIR + ETHIC-SHIELD-lite：规划器退为薄回退

```text
公开事实（2611.01713）：CBF-QP 局部把不安全动作投影到安全集，可能把机器人推离任务轨迹、
  让策略失去可靠恢复方向。Route-Guided 用 VLA 的短时 chunk 探测被挡标称轨迹，
  生成绕障的「入-出-回」引导，作为软项加入 CBF-QP，并保持安全约束。
→ 结论：这正是第 24 轮 P1「replan」想要的效果（绕障 + 并回任务轨迹），且免训练、已发表。
```

```text
SAFE-REPAIR 的三态（沿用 Shielding 的「仅在越界时纠正」）：
  PASS  ：chunk 经 PTS 重时序后无碰撞 → 原样放行（最小改动）。
  REPAIR：探测到被挡 → CBF-QP 引导绕行并回任务轨迹（替代 BiRRT replan）。
  HOLD  ：仅当动作为 R2（不可逆）且无法给出恢复证书 → 安全保持 / 重抽样 / 降速复核。
ETHIC-SHIELD-lite 只保留：
  A 物理合法（限位/速度/加速度/加加速度，零学习）；
  B 可逆性等级 R0/R1/R2（人工标注 32 任务，约 1 天），仅 R2 要求恢复证书；
  C 人体在场：双目 3D 检测人手距离 → 降速/让行（对「人为干扰」轴）。
MOTION-SHIELD 的 BiRRT/TOP 自研件全部退为「CBF-QP 不可用时的离线 fallback」，不再进实时路径。
```

## 6. HUMAN-SCALE + STEP-SCORE-IMITATION + FAIL-RSI：把「免费视频、省步、失败」都变成数据

### 6.1 HUMAN-SCALE（ELA + Open-HumanScale）

```text
公开事实：
  - Open-HumanScale（2611.06817）：50,000 小时 egocentric 人类视频 + 完整配方；
    给出预训练小时数 → 下游成功率 的对数线性 scaling law。
  - ELA（2611.05571）：从无动作标注视频学「潜在动作」，且潜在动作被联合优化以利控制与解码；
    仅需少量有动作标注的机器人演示。
做法：
  1. 用 ELA 式潜在动作在人类视频上做自监督预训练（扩分布：未见物品/背景）。
  2. 按 Open-HumanScale 的 scaling law 估算「多加 X 小时 → 预期 +Y 成功率」，给数据预算以依据。
  3. 采少量有动作标注的 G1 演示做对齐微调。
```

### 6.2 STEP-SCORE-IMITATION（SSI）：把步骤分当模仿目标

**动机**：排名 = 平均成功率 **+** 步骤分。所有人刷成功率，几乎没人显式学「省步」。步骤分可由两处拿：
```text
(1) 时间维省步：学「最快成功演示」的时间参数化 —— 对同一参考路径取演示时长分布的下分位，
    并与 PTS 的速度上限对齐。
(2) 决策维省步：子目标完成即停 —— 用特权状态（*_ee_pose_gripper_torso / recomputed_ee_valid）
    离线标注每个 demo 的「子目标达成帧」，训一个 stop head，达成即触发切换/结束。
```

```python
def ssi_weights(episode_lengths, demo_times, k=0.25):
    """按演示时长给样本加权：越快成功，权重越高（鼓励学省步）。"""
    t = np.asarray(demo_times, dtype=np.float64)
    w = np.exp(-(t - np.quantile(t, k)) / (np.std(t) + 1e-6))
    return w / w.mean()


def stop_head_target(ee_traj, goal_ee_pose, tol=0.02):
    """子目标达成帧：EE 到位且稳定的最早帧。"""
    d = np.linalg.norm(ee_traj - goal_ee_pose[None, :], axis=-1)
    stable = d < tol
    return int(np.argmax(stable)) if stable.any() else len(ee_traj) - 1
```

**差异**：把「步骤分」从一个被动指标，变成**主动的模仿/早停目标**。低竞争、低风险、直接换分。

### 6.3 FAIL-RSI（失败恢复数据飞轮）

```text
公开事实：Compounding Physical RSI（2611.06654）——任务完成度≈各阶段通过率之乘积，
  递归自改进收益跨代相乘；难点在「终点反馈难定位崩在哪一阶段」。
做法（离线为主、训练无关优先）：
  1. 用冻结策略在留出/仿真（LIBERO/MESA）大量 rollout，收集失败态。
  2. 用特权状态与子目标标注对失败**定位到阶段**（哪一步 EE/夹爪偏离）。
  3. 用 ScheduleGen（2610.39429，多臂约束下的演示合成）生成「从失败态回到正确阶段」的恢复演示。
  4. 回灌训练 → 复测账本。
  5. （可选 G3）在真机用 RL Enables Scaling（2611.06905）式迭代自改进。
```

## 7. GEN-LEDGER ↔ 公开评测（本轮修订）

```text
五轴 → 公开评测映射：
  位置变化     → MESA spatial 轴（2611.05567）
  干扰物       → MESA compositional 轴
  背景差异     → MESA semantic/appearance 轴
  未见物品     → MESA semantic/open-vocab 轴
  人为干扰     → 自建（MESA 未覆盖）：双目 3D 检测移动人手，注入退避回归
离线代理：RoboScope Kit（2611.03850，统一 Policy/adapter，加速评测；其 profiling 显示仿真吃 CPU、GPU 仅 14.3% 利用）
每轴指标：SR、步骤分代理、PTS 加速比、REPAIR/HOLD 比例、恢复证书成功率、块边界不连续度（§6 代理）
飞轮：失败/HOLD 留痕 → FAIL-RSI 定向合成恢复演示 → 回灌 → 复测
```

## 8. 门控交付计划（本轮修订）

```text
G0（接口冒烟，1–3 天）
  1. 跑通 example server/client；自写 client 验证「每步回调 vs 整块执行」、N 端口行为。
  2. 记录单次 get_action 时延 p50/p95/抖动，作为 §6 参照线。
  3. 拉 LingBot-VLA 2.0 UniBot LoRA，量测 1 块/多块推理时延与显存（决定 FLEET-SERVE 批大小）。
  Go：官方 example 无 ACTION REJECTED；服务预算表成形。

G1（能上榜的基线，3–7 天；因 OPEN-BASE 而大幅缩短）
  1. 接 LoRA 到 joint 空间接口；核对相对增量与 action_chunk_size。
  2. 离线留出回归（对齐 LoRA 卡片 MSE 0.229 量级）+ LIBERO 回归。
  3. 加 PTS-EXEC，测步骤分代理与块边界不连续度。
  Go：离线不低于 LoRA 未改动的开环指标；时延达标。

G2a（表示 + 执行，1–2 周）
  ACTION-DYNAMICS 小头替换 + 多模态候选；PTS-EXEC + FLEET-SERVE 压测（N=3）。
G2b（安全，1 周）
  SAFE-REPAIR(CBF-QP) + ETHIC-lite（仅 R2 恢复证书）；人为干扰轴回归。
G2c（数据，1–2 周）
  HUMAN-SCALE（ELA/Open-HumanScale）+ SSI + FAIL-RSI；MESA/RoboScope 账本日报。
G3（自改进，可选）
  真机 RSI / RL 迭代（2611.06905 / 2611.06654）。
硬规则：任何新想法先证明「能让某关卡变绿」，否则进旁路清单。
```

## 9. 实验协议

### 9.1 第一优先（决定路线）

| 实验 | 做法 | 判据 |
|---|---|---|
| E1 接口语义 | 自写 client 模拟每步回调 vs 整块执行 | 确定执行层/让行粒度 |
| E2 OPEN-BASE 复现 | LoRA 在留出/LIBERO 上开环 + 闭环 | 能否直接当 G1 |
| **E3 PTS 收益（新）** | 冻结策略 ± PTS，测步骤分代理、边界不连续度、时延抖动 | 是否免训练直接换分 |
| **E4 动作表示对比（新）** | 离散头 vs ODE/flow 头：连续性、多模态、留出误差 | #3 是否成立 |
| **E5 FLEET-SERVE 压测（新）** | N=3 共享模型，测 p95/抖动/串扰 | 是否满足 §6 |
| E6 SSI/FAIL-RSI | ± 时长加权/早停/恢复演示 | 步骤分与 SR 增量 |

### 9.2 消融网格与指标

```text
消融：{LoRA 开环, +PTS, +ACTION-DYNAMICS, +SAFE-REPAIR, +FLEET-SERVE,
       +SSI, +FAIL-RSI, +HUMAN-SCALE} × {joint, ee}
指标：留出动作误差(MSE/DTW)、五轴 SR、步骤分代理、块边界不连续度、加加速度分位、
      PTS 加速比、REPAIR/HOLD 比例、恢复证书成功率、误杀率(≈0)、
      p50/p95 时延与抖动、N 端口串扰。
```

### 9.3 预期结果（设计目标，非声称）

| 模块 | 目标 |
|---|---|
| OPEN-BASE | G1 可在数天内产出可提交 checkpoint |
| PTS-EXEC | 步骤分代理提升；块边界不连续度与抖动下降；误改率低 |
| ACTION-DYNAMICS | 留出连续性/多模态优于离散头；块边界差显著下降 |
| FLEET-SERVE | N=3 时 p95 与抖动不劣于单端口；无串扰 |
| SSI | 步骤分提升而 SR 不降 |
| FAIL-RSI | 在失败高发轴上 SR 有可归因增量 |
| SAFE-REPAIR | 障碍注入下零碰撞；误杀率≈0 |

## 10. 时间线（建议，随关卡 Go/Kill 调整）

```text
D1–D3   ：G0 接口冒烟 + E1 接口语义 + 拉 LoRA + E5 时延预算
D4–D7   ：G1 接 LoRA + PTS-EXEC + E3 步骤分
D8–D14  ：G2a ACTION-DYNAMICS 头 + FLEET-SERVE 压测 + MESA/RoboScope 账本
D14–D18 ：G2b SAFE-REPAIR + ETHIC-lite + 人为干扰轴
D18–D24 ：G2c HUMAN-SCALE + SSI + FAIL-RSI + 分轴复盘
D24–D30 ：G3（可选）真机 RSI；预约评测
```

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| LoRA 许可/分布不一致 | 核对 Apache-2.0 与数据版本；退 UnifoLM-VLA-0 |
| ODE 积分误差累积 | 限步长 `|dq|` + 时间参数化（PTS 协同）+ 候选集重选 |
| PTS 与低层限速耦合 | 速度上限取下层可达域；真机小样本标定 |
| FLEET-SERVE 的 KV 抖动 | admission control + 会话隔离 + 连续批处理；p95 SLO |
| CBF-QP 保守过度 | 仅在探测到阻挡时触发；软引导项权重可调 |
| HUMAN-SCALE 域鸿沟 | 少量 G1 对齐微调；先用 scaling law 估收益再投算力 |
| R2 误判 / HOLD 过度 | 人工审核 32 任务的可逆性；只对 R2 用证书 |
| 步骤分口径未公开 | 保守优化「快 + 子目标完成即停」；人工查飞书规则 |

## 12. 参考来源（检索日期 2026-11-05）

- 提交模板与接口规范：https://github.com/unitreerobotics/unibot_submission
- 挑战赛首页 / 任务集 / 排行榜 / 运行记录：https://unibot.unitree.com/ ；https://unibot.unitree.com/challenges.html ；https://unibot.unitree.com/leaderboard.html ；https://unibot.unitree.com/runs.html
- 赛事启动报道（32 任务 / 32,000 样本 / 169h / 五轴 / 平均成功率 + 步骤分 / DAPTO 2）：https://myxmr.com/en/news/unitree-launches-unibot-world-challenge ；https://myxmr.com/news/unitree-launches-unibot-world-challenge
- 挑战数据集集合（32 个 G1_Dex1_*）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset ；单集 https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- LingBot-VLA 2.0：https://github.com/Robbyant/lingbot-vla-v2 ；权重 https://huggingface.co/robbyant/lingbot-vla-v2-6b
- UniBot LoRA：https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora
- UnifoLM-VLA-0：https://github.com/unitreerobotics/unifolm-vla
- ODE Policy（2611.01729）：https://arxiv.org/abs/2611.01729
- PTS（2611.01390）：https://arxiv.org/abs/2611.01390
- Route-Guided CBF-QP Repair（2611.01713）：https://arxiv.org/abs/2611.01713
- Serving Agentic Robot Fleets（2611.01404）：https://arxiv.org/abs/2611.01404
- Open-HumanScale（2611.06817）：https://arxiv.org/abs/2611.06817
- ELA（2611.05571）：https://arxiv.org/abs/2611.05571
- ScheduleGen（2610.39429）：https://arxiv.org/abs/2610.39429
- Compounding Physical RSI（2611.06654）：https://arxiv.org/abs/2611.06654
- RL Enables Scaling Generalist Robot Policy（2611.06905）：https://arxiv.org/abs/2611.06905
- MESA（2611.05567）：https://arxiv.org/abs/2611.05567
- RoboScope Kit（2611.03850）：https://arxiv.org/abs/2611.03850

> 本轮产物一句话：**OID = 「开源已练好的 UniBot 基座 + 动作动力学表示 + PTS/CBF-QP 免训练执行与修复 + FLEET-SERVE 的 N 端口服务 + 人类视频/步骤分/失败三源数据飞轮」；第 24 轮缺的不是规划引擎，而是对『模仿学习的表示』与『部署执行层』的正面进攻——本轮把重资产规划器换成了便宜且已验证的公开组件。**
<!-- ARTIFACT:END -->