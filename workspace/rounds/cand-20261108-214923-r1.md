# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 36 轮 · 三灵感落地：真实立体视觉 × 交互契约工程 × 面部表情识别的诚实退役

> 承接第 35 轮（v12：开源基座雷达 × 跨 episode 记忆检索 × 门禁式路线图）。本轮灵感词「面部表情识别 / 交互设计 / 视觉感知」。
> 先联网核实，再谈创新。本轮最硬的一手事实：挑战数据集的 `meta/info.json` **公开了 `camera_params`**——头部双目完整标定（内参、畸变、R、T、基线 58.25 mm、`rectified=true`），而提交接口的 `cam_left_high / cam_right_high` 正是这对头双目。这把 v12 里含糊的"伪深度"升级为**可计算的真实米制深度**，也让「视觉感知」第一次有了硬着力点。同时我们精确读完提交 README §1–§6，把「交互设计」从"泛泛而谈的体验"沉淀为一个**可执行、可量化、直连排名的工程创新点**。至于「面部表情识别」，它是本轮被**诚实退役**的灵感。

## 0. 联网核实（先事实后推理；检索口径 2026-11-08）

本轮复核 + 新增事实（编号续接 v12）：

- **S1 复核（unibot.unitree.com）**：首页与 `/leaderboard` 现返回 **HTTP 567 + 腾讯云 EdgeOne「Access Restricted」拦截页**（7352B，含 requestId、内在 i18n 脚本），已**不再是** v12 记录的"静态占位页"。含义：官网挂了 WAF/CDN 风控（或对我们的请求做了地域/UA 过滤）。**结论不变：排行榜/手册仍不可得**；"榜首<30%""5 类泛化场景""步骤分口径"仍是**待验假设**（A15 继续开放）。变化本身记入 F43，不假装我们看到了榜单。
- **F24′ 复核（github unitreerobotics/unibot_submission，README 逐条直取）**：仓库仍是 2 commits、2026-08-21 后无新提交。**接口契约与 v12 完全一致，且更精确**：(a) 观测相机键名是 `cam_left_high / cam_right_high / cam_left_wrist / cam_right_wrist`，**不是**数据集里的 `head_stereo_*` → **A9 相机映射（`cam_left_high↔head_stereo_left`）现在有官方文本依据**；(b) 动作 = 共享 `left/right_gripper` + `pivot[7]`，二选一 `joint`（`left/right_arm[7]`）或 `ee`（`left/right_ee_pose_gripper_base[6]`）；(c) **接口内没有头部/颈/躯干主动控制**（无 head/neck action）；(d) N 个测试机器人 → 必须开 N 个连续端口（8765..），**每端口的 `reset` 与历史状态必须互相隔离**；(e) `obs_delta_indices` 既是选键又是时序堆叠，`image_resize` 是**静态**每键分辨率；(f) token 在 handshake 与每步 `meta.token` 各校验一次；(g) §6：时延及其波动、返回动作的**统计规律**都会作为可信度指标展示。→ **"交互设计"是有官方指名的打分表面。**
- **F41（★本轮最关键新事实：真实双目标定，HF `meta/info.json` 直取）**：`camera_params.head_stereo` 含 `camera_matrix_left/right`、`dist_coeffs_left/right`、`R`、`T`（T[0]=**-58.25 mm** 基线）、`rectified: true`；`wrist_left/right` 含 `color + ir1 + ir2 + extrinsics_to_color`（腕部是带 IR 双目的 RealSense 类模组）。→ **头双目已标定+已校正，米制深度可在策略侧直接重建，无需学习式单目深度**。这是 IP-34 的地基。
- **F42（★32 任务 episode 表，HF 集合直取）**：逐仓 `totalEpisodes` 求和 = **33,276**，与 v12 引用的 F39 第三方元数据**分毫不差**。→ **F39 的 33,276 从"第三方口径"升级为"HF 官方 API 复核通过"**。任务分布：`ColorArrangement` 最多 1,533 episodes，`Unlock`/`StackBowls`/`PourOutMedicine` 最少 970–979；`ToolboxStorage` 单任务帧数最高（1,199,136 帧）。长程/多物任务（OrganizePencilCase、ToolboxStorage、StoreCup/StoreEarphones、PackDoll/PackBag、SpellRobot、ConveyorSorting）确在列。
- **F43（新：官网风控化）**：见上 S1——`567 / EdgeOne` 拦截页取代静态占位。**榜单与规则依然不可得**，且我们无法区分"站点加了风控"与"我们被风控误伤"。
- **F44（★接口/数据 schema 精确化，HF `info.json` 直取）**：数据集 action 列出 `action.pivot[7]`、`action.waist_action_joint[3]`、`action.base_command[4]`、`action.lower_body[15]`、`action.gripper_controls[4]`、`observation.state.state_d435[6]`、`waist_state_joint[3]`、`recomputed_ee_valid[1]`。→ **强假设 H1：`pivot[7]` = `waist(3) ⊕ base_command(4)`（3+4=7）；`lower_body[15]` = `waist(3) ⊕ left_leg(6) ⊕ right_leg(6)`（3+12=15）**。而 v12 记的 LingBot 规范是 `waist(4)+base(3)=7`——**分组维数不同（3/4 vs 4/3）**，A18 转换器必须解出 `pivot` 的真实打包顺序，不能想当然。这是"错一格=全盘皆输"的精确落点。
- **F45（新：UnifoLM 许可复核，HF API）**：`UnifoLM-ER-Flow` = apache-2.0、`UnifoLM-WLA-1.0-Base` = apache-2.0、`UnifoLM-WMA-0-Base` = **gated(auto)**、`UnifoLM-VLA-Base` 的 API `cardData` **无 license 标签**（v12 记录其卡面为 CC BY-NC-SA 4.0，故 A17 审计更必要：连 HF 元数据都没有明确许可字段）。`ezhoureal/lingbot-vla-v2-unibot-lora` = apache-2.0（复核）。
- **文献（arXiv API 实时检索，2026-11-08；标题+编号，摘要级）**：为本轮三灵感词新检索到集群 R85–R100（详见产物区 §8）。要点：**立体/主动/注视**方向已有成熟分解——`ExStereo` 2610.04805（把 2D VLA 提升为显式立体表征）、`EATR-Stereo` 2608.17453（**人形 VLA** 的成对立体证据按本体感知路由 token）、`StereoEngine` 2610.12734（无立体相机也能扩增双腕立体数据）、`FoveaVLA` 2610.20064（**用注视动作替代腕相机**）、`ROI-Foveated Attention` 2603.20668、`Artificial Foveated Perception` 2607.10655（**抑制捷径学习**）、`AWAM` 2610.23396 / `Look Before You Act` 2610.23378 / `ActiveWAM` 2610.01698（主动视角与观察对齐）；**世界模型/遮挡**方向：`SCOUT` 2611.01600（物体中心世界模型规划穿遮挡）、`La-JEPA` 2611.08156、`HiFOR` 2610.40373、`PRIME W0` 2610.39528；**语言/交互**方向：`In-Context VLA` 2608.05738、`Grounded Semantic Re-Binding` 2608.02497、`LIBERO-Para` 2603.28301、`GIVE` 2606.13435（手势 grounding）。**「面部表情识别」方向在本竞技语境下几乎检索不到相关操作文献**（仅 2020 年一条隐式反馈旧作）——这本身就是退役信号。

## 1. 灵感词 → 三条落地线（含一条诚实退役）

- 「**视觉感知**」→ **IP-34 STEREO-FOVEA-PERCEPTION（本轮技术主攻）**：F41 给了**已校正头双目**，F44 给了 `state_d435` 作真值核对。设计分三层：(i) **米制深度层**——用 K/R/T(Q) 对 `cam_left_high/right_high` 做 SGBM/学习式立体匹配，得到与标定一致的深度图；(ii) **显式立体 token 层**——把深度/视差编码为 token 注入 VLM（ExStereo/EATR-Stereo 式，按手臂本体状态路由，避免"立体证据被当纹理"）；(iii) **软件注视层**——因接口**不暴露头部动作**，主动物理注视不可行，故改为**策略内 ROI 裁剪/多尺度聚焦**（FoveaVLA/ROI-Foveated 的"软件版"），由 System-2 子目标引导关注区域。目标：未见物、位置、背景/干扰物三类泛化的同时改善（几何优先于纹理，R89/R90 抑制捷径）。
- 「**交互设计**」→ **IP-33 INTERACTION-CONTRACT（本轮工程主攻）**：README §1–§6 把"交互"具象成一组**会被扣分的旋钮**：双动作空间互斥、共享夹爪/`pivot`、`obs_delta_indices`（选键+堆叠）、静态 `image_resize`、`action_chunk_size`、N 端口并发与**各端口状态隔离 + 每 episode `reset`**、token 双点校验、§6 的**时延波动 + 动作统计规律**。设计一个**契约层**：动作空间仲裁与运动学一致性、时延自适应 chunk 执行 + 平滑/离群钳制（直击 §6 "动作异常"扣分）、N 端口共享后端的分发与状态隔离（**这是记忆 IP-31 能否上线的硬前置**）、任务状态机 + 扰动检测/恢复。差异：v12 把这些散落在 IP-4/IP-25 里当实现细节，本轮**升格为一等设计对象**。
- 「**面部表情识别**」→ **诚实退役，仅做两处有益残值**：(a) 机器人没有脸、接口没有表情输入、数据集无面部通道、arXiv 无相关操作文献 → **字面版退役**（规则 39）；(b) 唯一可迁移的类比是"G1 的头双目 = 它的眼睛"→ 并入 IP-34；"读懂人" → 降维成 IP-33 里的**扰动/异物检测**（检测入侵的手/物，而非表情）。**不把退役灵感硬掰成创新点。**

## 2. 三线耦合与关键决断

- **耦合**：IP-34 为 IP-22 TRI-FUSE 提供真实深度分支（替换"伪深度"）→ 深度/立体 token 提升 System-2（IP-21）的空间推理与 IP-28 进度探针的几何条件 → 注视 ROI 由 IP-23 子目标驱动，形成"子目标 → 关注区域 → 动作"闭环 → IP-33 契约层承接 IP-31 记忆的**每端口状态隔离**与 IP-25 的时延/统计规则 → IP-32 门禁决定三层是否保留。
- **关键决断**：
  1. **深度走几何、不走猜**：有标定（F41）与真值（`state_d435`）就**优先立体几何**，学习式单目深度仅作缺失相机时的兜底（R89：几何比纹理更抗背景/物体泛化）。
  2. **不做物理主动视角**：接口无头/颈动作 → IP-34 的"注视"只能是**软件 ROI/多尺度**，绝不假设能转头。这纠正了 AWAM/Look-Before-You-Act 类工作在 UniBot 上的直接迁移。
  3. **契约层是记忆的前置**：IP-31 服务端记忆必须先满足"每端口状态隔离 + 每 episode `reset`"（README §4 明文要求），否则 N>1 时记忆会串台。故 IP-33 优先级与 IP-31 绑定。
  4. **A18 由假设升维**：F44 的 H1（`pivot[7]=waist(3)⊕base(4)`）必须先被数据证实，再谈转换；用 `norm_stats/unibot_full.json` + `info.json` 分组维数交叉校验。
  5. **§6 当 KPI**：把"每步时延方差最小 + 动作离群率≈0"写成 IP-33 的验收指标，而非事后补救。

## 3. 诚实标注（未解决项，不假装解决）

- 排行榜、参赛手册、步骤分口径、5 类泛化定义**仍不可得**（F43：官网已风控化）；"榜首<30%"仍是用户口径而非已核实事实。
- F44 的 H1（`pivot` 打包顺序）是**由维度巧合推出的强假设**，未经数据验证——列入 A18，不得当作已知。
- `state_d435` 只是 6 维位姿/状态，**数据集未提供 D435 深度图**；它只能作稀疏真值核对，不能当监督深度源。
- 文献均为标题/摘要级引用；`FoveaVLA` 等未逐篇读全文。

## 4. 本轮最大风险

1. **立体深度"算得出但用不好"**：标定给的 R/T 是双目间外参，但深度还需 Q 矩阵与极线校正一致性；若视频帧本身已被裁切/缩放，深度会系统性偏。缓解：先用 `state_d435` 对少量帧回归验证比例尺，再进训练。
2. **注视 ROI 引入捷径**：裁剪可能放大数据集偏置（R90 警告）。缓解：ROI 随机化 + 与全帧分支互补消融（E46）。
3. **契约层变成"过度工程"**：陷入端口/格式细节而不产出分数。缓解：规则 38 门禁 + §6 指标必须可量化。
4. **再次追风口**：Face 退役说明"灵感词≠机会"；防重蹈覆辙（规则 39）。

## 5. 一句话结论

本轮最值得押注：**IP-34 真实立体视觉**——利用挑战数据集**已公开的头双目标定（F41）**重建米制深度并做软件注视/立体 token，用最低新增成本同时改善未见物、位置与背景三类泛化；**IP-33 交互契约**为其与记忆栈提供合规、抗扣分的运行底座。
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 36 轮产物 · 创新点清单 v13：真实立体视觉 × 交互契约工程（面部表情识别退役）

> 承接 v12（第 35 轮）。本轮**新增 IP-33 INTERACTION-CONTRACT、IP-34 STEREO-FOVEA-PERCEPTION（均 P0/P1）**；**升级 IP-22**（伪深度→真实立体深度分支）；**F39 因 F42 由第三方口径升为官方复核**；**新开 A19（立体深度验证）/A20（N 端口状态隔离）**；**「面部表情识别」灵感诚实退役**。灵感词：面部表情识别 / 交互设计 / 视觉感知。

## 0. 结论

- **旗舰 IP-21 UNIBOT-RFM 保留**；本轮真正的新增在"感知底座"与"运行底座"两处。
- **新增 IP-34 STEREO-FOVEA-PERCEPTION（P0，本轮技术主攻）**：`camera_params` 已给头双目完整标定（F41）→ 真实米制深度（几何优先）+ 显式立体 token（ExStereo/EATR-Stereo 式）+ **软件注视 ROI**（因接口无头部动作，删除物理主动视角假设）。直接对齐未见物/位置/背景三类泛化。
- **新增 IP-33 INTERACTION-CONTRACT（P0，本轮工程主攻）**：把 README §1–§6 的接口旋钮升格为一等设计对象——动作空间仲裁、时延自适应 chunk、§6 动作统计离群钳制、N 端口共享后端 + **每端口状态隔离**、任务状态机 + 扰动检测。是 IP-31 记忆上线的硬前置。
- **升级 IP-22 TRI-FUSE**：v12 的"立体伪深度"→ 真实立体深度分支（几何/学习双路，几何优先）。
- **F39 置信度升级**：F42 用 HF 官方 API 逐仓 `totalEpisodes` 求和 = **33,276**，与第三方完全一致。
- **「面部表情识别」退役**（规则 39 首次执行）：字面版无接口/无数据/无文献支撑；残值并入 IP-34（"头双目=眼睛"）与 IP-33（"读人"→扰动检测）。

## 1. 事实卡（联网核实；检索日期 2026-11-08）

- **F24′（接口契约，README 逐条直取；复核）**：相机键 `cam_left_high/right_high/left_wrist/right_wrist`（**A9 映射获官方文本依据**）；共享 `left/right_gripper`+`pivot[7]`，二选一 `joint`(`left/right_arm[7]`) / `ee`(`left/right_ee_pose_gripper_base[6]`)；**无头/颈/躯干动作**；N 端口连续 8765..，**每端口状态隔离 + 每 episode `reset`**；`obs_delta_indices` 选键+堆叠；`image_resize` 静态；token handshake+每步双校验；§6 时延波动与**动作统计规律**=可信度指标。
- **F25/F30–F33（数据 schema，沿用 v12）**：LeRobot v3.0、30fps、480×640；桌面任务 `pivot`≈常数 → 实质定基座。
- **F34/F43（榜单/规则，未核实）**：官网现返回 **HTTP 567 + EdgeOne 拦截页**（v12 时是静态占位）→ 榜单/手册/口径仍不可得。**A15 继续开放**。
- **F35（文献集群 R52–R64，沿用）**；**R65–R84（沿用 v12）**。
- **F36（指令改写，沿用）**：每任务恰 5 条英文改写（`@` 连接）。
- **F37（宇树开源 VLA 家族，沿用）**：`UnifoLM-VLA-Base`（G1-Dex1 继续预训练）、`UnifoLM-ER-Flow`、`UnifoLM-WLA-1.0-Base`、`UnifoLM-WMA-0-Base`。
- **F38（72 仓 G1-Dex1 开放集，沿用）**：g1-dex1 集合 72 仓（本轮再确认）。
- **F39（第三方全量参考配方，★置信度升级）**：`ezhoureal/lingbot-vla-v2-unibot-lora`（apache-2.0）：LingBot-VLA-V2 6.3B 上 LoRA r64/α32、**全量 33,276 episodes**、10K 步、单张 4090、单一 checkpoint、公开 `norm_stats/unibot_full.json`。
- **F41（★新：真实双目标定）**：`meta/info.json` → `camera_params.head_stereo`：K_l/K_r、dist_l/r、R、**T[0]=-58.25mm 基线**、`rectified: true`；腕相机含 `color+ir1+ir2+extrinsics`。→ 米制深度可算。
- **F42（★新：episode 表，官方复核）**：32 仓 `totalEpisodes` 求和 **= 33,276**（= F39）。最少 `Unlock` 970、`StackBowls` 979、`PourOutMedicine` 979；最多 `ColorArrangement` 1,533。`ToolboxStorage` 帧数最高 1,199,136。
- **F44（★新：schema 精确化 → 强假设 H1）**：数据集 action = `pivot[7]`、`waist_action_joint[3]`、`base_command[4]`、`lower_body[15]`、`gripper_controls[4]`、`state_d435[6]`、`waist_state_joint[3]`、`recomputed_ee_valid[1]`。**H1：`pivot[7]=waist(3)⊕base(4)`；`lower_body[15]=waist(3)⊕leg(6)⊕leg(6)`。** 与 LingBot `waist(4)+base(3)` 分组不同 → A18 必须解出真实打包。
- **F45（★新：许可复核）**：`UnifoLM-ER-Flow`/`UnifoLM-WLA-1.0-Base` = apache-2.0；`UnifoLM-WMA-0-Base` = **gated(auto)**；`UnifoLM-VLA-Base` API 无 license 标签（卡面记 CC BY-NC-SA 4.0 → A17 更必要）。
- **S9（数据许可，沿用）**：挑战仓 apache-2.0；**数据自由 ≠ 基座自由**。

**行动项更新**：**A18 深化**（H1 待验）；**A19 新增**：立体深度管线的尺度/极线一致性验证（用 `state_d435` 稀疏核对）；**A20 新增**：N 端口共享后端的并发 + 状态隔离压测（对接 IP-31 记忆）；A9 **半关闭**（`cam_left_high↔head_stereo_left` 映射有官方文本）；A14/A15/A17 沿用。

## 2. 创新点清单 v13 一览

| 编号 | 名称 | 一句话 | 优先级 | 依赖 | 灵感词 | 主成本账户 | 边际分预期 | 状态 |
|---|---|---|---|---|---|---|---|---|
| IP-21 | UNIBOT-RFM | 单模型双系统 VLA 覆盖 32 任务 | P0 | A9,A18 | 机器人基础模型 | 算力(中) | 主成功率 | 旗舰 |
| **IP-34** | **STEREO-FOVEA-PERCEPTION** | 真实立体米制深度 + 显式立体 token + 软件注视 ROI，几何优先 | **P0** | F41,IP-22,IP-3 | **视觉感知** | 算力(中)+工程(中) | 未见物/位置/背景泛化 | **新增** |
| **IP-33** | **INTERACTION-CONTRACT** | 接口旋钮一等公民：动作仲裁/时延 chunk/动作离群钳制/N 端口状态隔离/扰动恢复 | **P0** | F24′,IP-25,IP-31 | **交互设计** | 工程(中) | 可信度 + 不掉请求 + 记忆合规 | **新增** |
| IP-31 | MEMORY-RETRIEVAL | 工作记忆账本 + 跨 episode 检索银行 + 失败经验检索 | P0 | IP-3,IP-28,IP-29 | 记忆检索 | 算力(轻)+工程(中) | 长程/未见物/恢复 | 继承（+A20 前置） |
| IP-30 | OPEN-STACK-RADAR | 开源基座登记册 + 一键复适 + 许可台账 + B0 锚定 | P0 | A17,A18 | 开源软件 | 工程(中) | 选型正确率 + 迭代速度 | 继承 |
| IP-32 | ROADMAP-GATES | P0–P4 门禁 + 量化 go/no-go + 止损 + 三账户 | P0 | IP-10 | 技术路线图 | 近零 | 防负 ROI | 继承 |
| IP-29 | LoRA-EXPERT-BANK | 共享 VLM + K 能力 LoRA + 语言/首帧路由（键=5 改写平均嵌入） | P0 | IP-21 | LoRA | 算力(中) | 全域成功率 | 继承 |
| IP-28 | PROGRESS-CRITIC | 自监督进度/子步骤 + 卡住重试 + 部分分 | P0 | A15,IP-3 | 步骤分 | 数据(标注轻) | 步骤分 + 长程 | 继承 |
| IP-25 | LATENCY-SLO | 时延 SLO + 少步动作头 + QAT + 动作平滑 | P0 | IP-4,A11 | 接口工程 | 部署机 | 可信度 | 继承（并入 IP-33 接口面） |
| **IP-22** | **TRI-FUSE** | 多视图×本体×语言融合 + **真实立体深度分支**（替换伪深度） | P0 | IP-21,IP-34 | 技术融合 | 算力(中) | 未见物/位置泛化 | **升级** |
| IP-24 | FAILURE-MONITOR | 失败预警 + 触发恢复（恢复 LoRA 由 M3 选） | P1 | IP-21,IP-29,IP-31 | 泛化×安全 | 算力(轻) | 鲁棒性/可信度 | 继承 |
| IP-23 | TASK-DAG | 得分点驱动子目标分段 + 分层 | P1 | IP-28,IP-21 | 任务分解 | 数据(轻) | 步骤分 + 长程 | 继承（+驱动 IP-34 注视） |
| IP-26 | GENERALIZE-SUITE | 五轴增广与评测 | P1 | IP-2,IP-3 | 泛化 | 数据(近零) | 全场景 | 继承 |
| IP-2/3/4/10 | SCORE-ALIGN / LOCAL-EVAL / SUBMISSION-OPS / COST-LADDER | 沿用 | P0 | — | — | — | — | 继承 |
| IP-9 | SWARM-DECODE | 开源候选池集成→蒸馏单模型 | P1 | IP-2,IP-30 | 泛化 | 算力(一次性) | +2~5pt | 继承 |
| IP-27 | QUAD-PRIOR | 跨形态表征先验，不做运动控制 | P2 | IP-22 | 四足 | 算力(低) | 未见物 | 继承 |
| IP-8 | STEP-EFF | 并入 IP-28/IP-25 | — | — | — | — | — | 合并 |
| IP-1/11/13/16/17/18/19/20 | SLAM/社交/力觉/触觉/对话 | 接口不可达或赛道无需求 | — | — | — | — | — | 退役 |
| **FACE-EXPR** | **面部表情识别** | 无脸/无输入/无数据/无文献 | — | — | 面部表情识别 | — | — | **退役（规则 39）** |

## 3. 重点展开

### 3.1 IP-34 STEREO-FOVEA-PERCEPTION（灵感：视觉感知）

**动机**：F41 提供**已校正头双目标定**（基线 58.25mm），F44 提供 `state_d435[6]` 作稀疏真值；F36 的 32 任务大量涉及未见物/位置/干扰（背景与物体是排名暗礁）。立体几何比单目纹理更抗背景与外观变化（R89 ExStereo、R90 抑制捷径）。

**设计（三层 + 一路兜底）**：
- **L1 米制深度层**：由 K_l/K_r + R + T 构造 Q，对校正后的 `cam_left_high/right_high` 做 SGBM（或轻量学习式立体如 StereoEngine 式扩展）；输出与标定同一尺度的深度图。**尺度/极线一致性用 `state_d435` 稀疏核对（A19）**。
- **L2 显式立体 token 层**：深度/视差编码为 token 与 RGB token 成对注入 VLM（ExStereo/EATR-Stereo 式）；**按手臂本体状态（`left/right_arm`）做 embodiment-aware 路由**（EATR-Stereo），避免立体证据被当纹理。
- **L3 软件注视层（关键约束）**：接口**不暴露头部动作**（F24′）→ **不做物理主动视角**。改为策略内 ROI：由 System-2 子目标（IP-23）给出关注框/尺度，对高分辨率输入做多尺度 crop/attention（FoveaVLA/ROI-Foveated 的软件化），并把 ROI 通过 `image_resize` 之外的方式在策略内部实现。
- **兜底**：若某相机缺失/退化，回退学习式单目深度（仅兜底，不默认）。

**与现有方案差异**：v12 的 IP-22 只提"立体伪深度"，无标定、无 token 路由、无注视、无真值核对。IP-34 把"感知"变成有标定、可验证、有文献锚点的工程。

**可行性/资源**：标定已在数据集中（零采集成本）；SGBM 在 480×640 上可实时；token 层复用 IP-22。风险：视频码流裁切导致的尺度偏差（A19 防）。

```python
class StereoFovea:
    def __init__(self, cam_params):            # F41: 已校正头双目
        self.Q = stereo_rectify_to_Q(cam_params)   # K,R,T -> Q
        self.matcher = SGBM()
    def depth(self, left, right):
        disp = self.matcher.compute(left, right)
        return cv2.reprojectImageTo3D(disp, self.Q)
    def perceive(self, obs, subgoal_roi):
        d  = self.depth(obs.high_l, obs.high_r)
        roi = crop_multiscale(obs.high_l, subgoal_roi)   # L3 软件注视
        return stereo_tokens(obs.high_l, d, roi, embodiment=obs.arm_state)  # L2
```

### 3.2 IP-33 INTERACTION-CONTRACT（灵感：交互设计）

**动机**：README §1–§6 把"交互"明确成会被扣分的旋钮：双动作空间互斥、共享夹爪/`pivot`、`obs_delta_indices`、静态 `image_resize`、`action_chunk_size`、**N 端口并发 + 每端口状态隔离 + 每 episode `reset`**、token 双校验、**§6 时延波动与动作统计规律=可信度**。v12 把这些当实现细节——本轮升格。

**设计（五个契约区）**：
- **C1 动作契约**：joint/ee 双表示仲裁；共享夹爪/`pivot` 与手臂动作的**运动学一致性**；`pivot[7]` 打包按 A18 解出的真实顺序（勿信 H1）。
- **C2 时延契约**：`action_chunk_size` T_a 自适应 + 少步动作头（IP-25）+ 平滑/限幅；**目标=每步时延方差最小**（§6）。
- **C3 动作统计契约**：离群/跳变检测与钳制，保证"返回动作无明显异常"（§6 直接扣分项）。
- **C4 多端口契约**：N 端口共享单模型后端（省显存）+ 请求分发；**每端口 `reset` 与历史/记忆状态彻底隔离**（IP-31 前置，A20）；并发不互阻、时延不膨胀。
- **C5 任务/扰动契约**：每 episode 状态机（对齐 IP-28 进度）+ 扰动/异物检测与恢复（"读人"的降维残值：检测入侵手/物，而非表情）。

**差异**：v12 有 IP-25（时延）与 IP-4（多端口运维），但无统一的"接口即设计"观；C3（动作统计离群）是 v12 完全遗漏的官宣扣分点。

**风险**：过度工程 → 每区必须绑一个可量化 §6 指标 + 一条 E47/E48 实验。

### 3.3 IP-22 TRI-FUSE 升级（原：伪深度 → 真实立体）

把 v12 的"立体伪深度"替换为 IP-34 的 L1/L2 真实立体分支；保留多视图×本体×语言融合骨架；世界模型辅助（F37 ER-Flow/SCOUT）仍为可选。差异：感知从"猜深度"变"算深度"。

## 4. v13 整合架构

```
输入: 4×RGB (cam_left/right_high=头双目, cam_left/right_wrist) ─┐
     本体(arms/ee/grip/lower_body/pivot) ┤→ TRI-FUSE (IP-22, 升级)
     语言指令 ×5 改写 (F36) ─────────────┘   ▲
        │                                   │ L1 米制深度 (IP-34, F41 标定 + state_d435 核对)
        │                                   │ L2 显式立体 token (ExStereo/EATR-Stereo)
        │                                   │ L3 软件注视 ROI (子目标驱动, 接口无头部动作)
 System-2 = 开源基座(默认 LingBot-VLA-V2 apache-2.0)
          + LoRA-EXPERT-BANK (IP-29) + 检索先验/物体账本 (IP-31 M1/M2) ──→ 子目标 z_t (IP-23)
        │                                                                     │
 System-1 = 少步流匹配动作头 (joint/ee 双表示)
        │
 INTERACTION-CONTRACT (IP-33):
   C1 动作仲裁(joint/ee, pivot @A18) · C2 时延 chunk · C3 动作离群钳制(§6)
   C4 N 端口共享后端 + 每端口状态隔离(A20, IP-31 前置) · C5 状态机+扰动恢复
 A18 转换器(pivot/lower_body 打包 @H1 待验) 在所有 I/O 边界
 ROADMAP-GATES (IP-32) 门禁每层去留；OPEN-STACK-RADAR (IP-30) 供基座与数据
```

## 5. 训练/服务伪代码（增量）

```python
def build_v13():
    base = load_open_base("lingbot-vla-v2")          # IP-30; apache-2.0
    sf   = StereoFovea(cam_params)                   # IP-34 (F41)
    fuse = TriFuseEncoder(stereo=sf)                 # IP-22 升级
    bank = LoRABank(base, K=6, paraphrase_keys=True) # IP-29 + F36 键
    mem  = MemoryStack(bank_episodes=ALL_33K)        # IP-31 (F42: 33,276)
    system2 = SubgoalPlanner(bank, memory=mem)       # IP-23 -> ROI
    system1 = FlowActionExpert(steps=4, dual=("joint","ee"))
    prog = ProgressHead(p2_probes=True)              # IP-28
    for batch in D:
        for v in batch.lang_variants:                # 5× 增广 (F36)
            roi = system2.roi(batch, v)              # L3 注视
            f   = fuse(batch.images, batch.proprio, v, roi)   # L1/L2
            z   = system2(f, v, mem.retrieve(v, batch.first_frame))
            a   = system1.sample_train(f, batch.proprio, z, batch.action)
            loss = flow_loss(a, A18.convert(batch.action)) \
                 + LAM_PROG*prog_loss(prog(f, mem.ledger), batch.pseudo_progress) \
                 + LAM_ROUT*router_lb(bank) + LAM_PAR*para_invariance(bank)
    mem.build_failure_bank()
    return sf, fuse, bank, system2, system1, prog, mem, A18.converter

def get_action(obs):                 # 每端口独立进程/上下文 (C4)
    roi  = subgoal_roi(obs)
    f    = fuse(obs, roi)                        # 含 IP-34 立体
    a    = system1(...)
    a    = contract_clamp(a)                     # C3: §6 动作离群钳制
    return chunk_schedule(a, T_a_adaptive)       # C2: §6 时延方差最小
```

## 6. 实验设计（新增 E45–E48；E30–E44 沿用）

| 实验 | 设置 | 指标 | 门槛/预期 |
|---|---|---|---|
| E45 立体深度 | SGBM/学习式 vs 单目；与 `state_d435` 稀疏核对 | 深度尺度误差、未见物/位置成功率 | 尺度误差 <τ；泛化子集 +≥3pt（A19） |
| E46 软件注视 | 全帧 vs ROI vs 多尺度；ROI 随机化 | 背景/干扰物子集成功率、捷径指标、p99 | 泛化子集 +≥3pt 且不掉主集（R90 防捷径） |
| E47 交互契约 | T_a 扫描、离群钳制开/关、N=3 端口共享后端 | 每步时延方差、动作离群率（§6）、有效动作率 | 方差↓、离群率≈0、无非法请求 |
| E48 扰动/状态隔离 | 扰动注入 vs 无；N 端口并发 + 串台检测 | 恢复率、记忆串台率 | 串台 = 0（IP-31 前置 A20） |
| E40–E44 | 沿用（基座/改写/检索/失败/门禁） | — | — |
| E30–E39 | 沿用 | — | — |

**降级机制**：E45 不过 → IP-34 退为纯 RGB + 学习式深度兜底；E46 引入捷径 → 删注视只留全帧；E47 离群率不降 → 回退更小 T_a 与更强平滑；A20 串台 → IP-31 在该端口配置下关闭。

## 7. 风险登记簿（更新）

| 风险 | 等级 | 缓解 |
|---|---|---|
| **立体深度尺度偏差**（视频码流裁切/缩放破坏极线） | **高** | A19：`state_d435` 稀疏回归校准；先证伪再进训练 |
| **注视 ROI 放大数据集捷径** | 中高 | ROI 随机化 + E46 互补消融（R90） |
| **N 端口记忆串台**（IP-31 上线前置） | **高** | A20 压测 + 每端口独立 `reset`/上下文隔离（README §4） |
| **§6 动作统计离群扣分**（v12 遗漏） | **中高** | C3 钳制 + E47 量化 |
| **A18 `pivot`/`lower_body` 打包错位**（F44 H1 未验） | **高** | 分组维数交叉校验 + norm_stats + IP-3 回放 |
| **A17 基座许可**（UnifoLM-VLA-Base 无明确许可标签，F45） | **高** | 默认 apache-2.0 基座；NC-SA 仅对照 |
| 记忆检索注入错误先验 | 中高 | 置信门限 + 回退纯基座（E42） |
| 步骤分口径未核实（A15/F43） | 高 | rubric 无关设计 + 保守阈值 |
| （沿用）相机映射、时延异常、算力 | 中 | 见 v10–v12 |

## 8. 来源清单（引用口径：2026-11-08）

**官方/开源（一手，本轮直取）**
- S1 `https://unibot.unitree.com`（/、/leaderboard）——**HTTP 567 + 腾讯云 EdgeOne Access Restricted**（F43），榜单仍不可得。
- S2 `https://github.com/unitreerobotics/unibot_submission`——README §1–§6 全文（F24′）；2 commits、2026-08-21 后无更新。
- S3 `https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset`（32 仓）+ 各仓 `meta/info.json`（**F41 camera_params**、**F44 action schema**）/`totalEpisodes`（**F42=33,276**）；`G1_Dex1_HangCup` 1043 eps / 194,564 帧 / 30fps / 头双目+腕双目。
- S4 参赛手册（feishu）——Login Required，未获取。
- S5 `https://huggingface.co/unitreerobotics/UnifoLM-VLA-Base` + `github.com/unitreerobotics/unifolm-vla` + `UnifoLM-ER-Flow`/`UnifoLM-WLA-1.0-Base`/`UnifoLM-WMA-0-Base`（**F45 许可标签**）。
- S6 `https://huggingface.co/collections/unitreerobotics/g1-dex1-datasets-68bae98bf0a26d617f9983ab`——72 仓（复核）。
- S7 `https://huggingface.co/ezhoureal/lingbot-vla-v2-unibot-lora`（apache-2.0，33,276 eps）+ `robbyant/lingbot-vla-v2-6b`。
- S8 GitHub repository search（`unibot`）——无公开提交/榜单。

**文献（arXiv API 实时检索 2026-11-08；标题+编号，摘要级）**
- **视觉感知/立体/注视**：R85 ExStereo 2610.04805；R86 EATR-Stereo 2608.17453（人形 VLA 成对立体路由）；R87 StereoEngine 2610.12734；R88 FoveaVLA 2610.20064；R89 ROI-Driven Foveated Attention 2603.20668；R90 Artificial Foveated Perception 2607.10655（抑制捷径）；R91 AWAM 2610.23396；R92 Look Before You Act 2610.23378；R93 ActiveWAM 2610.01698。
- **世界模型/遮挡**：R94 SCOUT 2611.01600；R95 La-JEPA 2611.08156；R96 HiFOR 2610.40373；R97 PRIME W0 2610.39528。
- **语言/交互**：R98 In-Context VLA 2608.05738；R99 Grounded Semantic Re-Binding 2608.02497；R100 LIBERO-Para 2603.28301；GIVE 2606.13435（手势）。
- （R65–R84 沿用 v12；R41–R64 沿用 v10/v11。）

**诚实记录**：S1 榜单、S4 手册不可得（官网已风控化）；F44 的 H1 是维度巧合推出的**未验证假设**；`state_d435` 仅为位姿/状态、**无深度图**；文献为摘要级引用。

## 9. 清单迭代规则（本轮增补 39–41）

- 继承规则 27–38（通道诚实 / 映射验证 / 时延 SLO / fail-safe / 灵感-现实校验 / 单模型专家化 / 步骤分双解释 / 稠密监督不依赖 rubric / 基座许可审计 / 记忆外置优先 / 指令 5× 一等公民 / 门禁纪律）。
- **39（灵感诚实退役/剪枝）**：灵感词若在本竞技语境下无接口、无数据、无文献支撑（如"面部表情识别"），明确退役或降维为可验证的接口杠杆（"头双目=眼睛"），不得硬掰。
- **40（接口即设计表面）**：`control_space`/`obs_delta_indices`/`image_resize`/`action_chunk_size`/N 端口/`reset`/token 是**一等设计变量**；任一接口变更必须通过 §6 时延方差与动作统计离群检查。
- **41（几何优先于纹理）**：有标定（F41）时优先米制立体几何而非学习式单目深度；几何分支须用真值（`state_d435`）验证尺度后方可进训练。

**当前最值得押注**：**IP-34 真实立体视觉**——挑战数据集**已公开头双目标定（F41）**，可用近零采集成本把感知从"猜深度"升级为"算深度 + 软件注视"，同时改善未见物/位置/背景三类泛化；由 **IP-33 交互契约**保证其在本轮新暴露的 §6 可信度指标与 N 端口状态隔离纪律下不掉分、可上线。
<!-- ARTIFACT:END -->
