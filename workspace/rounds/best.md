# 玄 · 寻找参加UniBot的创新点

> 本文件由 xuen 维护：『想法区』『产物区』跨轮保留，每次写入会整体覆盖对应区块。编辑时请保留标记行。

<!-- IDEA:START -->
# 第 23 轮（研究线累计）· MVP-3D-SHIELD（M3S）：用「最小可行产品」纪律先出货，用「三维感知」把立体几何锚进 VLA，用「伦理审查」把每个动作在执行前送进审查门

> 检索日期：2026-11-05。灵感词：**伦理审查 / 最小可行产品 / 三维感知**。
> 本轮是一次「再基线化」：在对 ZEST 家族做了 22 轮不断加码之后，三个词共同指向一个反直觉但更值钱的方向——**先收敛、先出货，再把创新预算投到竞赛接口已经免费给你、却被大家忽略的两处杠杆上。**

## 0. 三分钟直觉：三个词正好是三次「止损」

先对齐事实（来源见 §8）：

- **赛制**：UniBot-V1 挑战赛，32 项真机桌面任务（抓取/放置/双手协调），32000 条演示、169 小时，Unitree G1 + Dex1 夹爪，**单模型通才赛道**，按「平均成功率 + 步骤分」综合排名；选手本地部署模型，评测系统按**固定端口**远程接入，N 台机器人并发、随机顺序（`unibot.unitree.com`；`github.com/unitreerobotics/unibot_submission`）。
- **观测量**：4 路 RGB + 左右臂关节 7 维 + 左右 EE 位姿 6 维（base 系）+ 左右夹爪 1 维 + 下半身 15 维 + 语言 str。**没有力觉/触觉**。
- **数据集的隐藏事实（本轮新核实，极关键）**：头部的两路相机是 **`head_stereo_left` / `head_stereo_right`，且数据卡明确写着「rectified」**——即**已立体矫正的双目对**；此外数据集还含评测接口**不暴露**的「特权状态」：`*_ee_pose_gripper_torso`（躯干系 EE）、`state_d435`（D435 相机位姿）、`recomputed_ee_valid`（`huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel`）。
- **动作量**：`joint` 或 `ee` **二选一**，返回长度 `action_chunk_size` 的动作块；块内按索引顺序执行，块边界才回调 `get_action`（同 repo README）。
- **官方在意的「可信度」**：明文把「每步响应延迟及其波动」与「返回动作的统计规律性」作为结果可信度依据（`unibot_submission` §6）。
- **泛化五轴**：位置 / 干扰物 / 背景 / 未见物品 / 人为干扰。
- **榜单现状**：`leaderboard.html` / `runs.html` 仍为 **Coming Soon**；用户与公开信息称榜首成功率 **<30%**。
- **已经存在的免费基座（本轮新核实）**：宇树开源了 **UnifoLM-VLA-0**（Apache-2.0，Qwen2.5-VL + GR00T 系，单策略完成 12 类 G1 操作，含训练/推理/权重；`github.com/unitreerobotics/unifolm-vla`），另有 UnifoLM-WMA-0（世界模型-动作）、UnifoLM-WLA-1.0。
- **近邻 SOTA 信号**：SOTA2 的「Unitree G1 真机操作」聚合榜上，LingBot-VA（因果世界建模、闭环 rollout、异步推理）平均 66.7，Flash-WAM（世界动作模型步蒸馏）60/50，LingBot-VA 降低 NFE 后掉到 40/23.3（`sota2.com/.../robot-manipulation-on-unitree-g1-real-world`）。

三个词分别是一次「止损」，而且互相咬合：

> **最小可行产品**：22 轮里我们造了 PC→MP→CG→CPC 一套套宏体系，但没有一行代码真正上过机、上过榜。**在一个榜首不到 30%、榜单还空着的比赛里，「能出货的 20 分」严格优于「不能出货的 80 分」。** MVP 纪律是：把研究预算先锁到一条「可真机跑、可提交、可迭代」的脊柱上。

> **三维感知**：竞赛只给 4 路 RGB，看起来是「3D 盲区」；但**双目头相机是已矫正的**——深度不是缺传感，而是缺一个把 `disparity` 变成 `metric cloud` 的薄模块。三维几何恰好正对泛化五轴里最「几何」的四条：位置、干扰物、背景、未见物品；也正对最吃精度的插拔/堆叠任务。

> **伦理审查**：机器人竞赛没有 IRB，但**「伦理审查」有一个极其贴切的技术同构**——在执行之前，由一个独立于「行动提案者（VLA）」的「审查者」对动作块做**安全与分布外审查**，可否决、可修复、可留痕。它同时解决三件真事：(a) 人为干扰轴下的人—机安全；(b) 药瓶/玻璃/电子等易损或不可逆对象的「财产完整性」；(c) 官方 §6 要求的「动作统计规律性」。**把伦理审查落成「动作审查门 + 审查留痕」，是本轮最诚实、也最可交付的解读。**

一句话押注：

> **先按 MVP 纪律把「UnifoLM-VLA-0 微调 + 合规 N 端口服务」这条脊柱出货（M1）；然后只投两处高杠杆：(M2) 用已矫正双目免费造出机器人系点云、做视图规范化与特权蒸馏，专治几何泛化；(M3) 在动作块提交前加一道「审查门」，做安全/OOD 否决、人—机让行与动作留痕，专治人为干扰与可信度。其余一律延后，直到这三样真的上了榜。**

三个可验证创新点：

1. **MVP-SPINE（最小可行脊柱 + 门控交付）**：一条三级门控的交付流水线——G0「接口冒烟」（跑通官方 example、验证 N 端口与块语义）→ G1「能上榜的基线」（用 Apache-2.0 的 UnifoLM-VLA-0 在 32k 演示上微调，joint 空间、动作块 + 时序集成、按子目标早停省步骤）→ G2「加三维/加审查」。每一级都以一个**可提交 checkpoint** 收尾，任何新想法必须先证明它能让某个既有关卡变绿，否则不入主线。这是把「研究」当「产品」经营。

2. **3D-ANCHOR（三维锚定 + 特权蒸馏）**：`f_geo` 把 `cam_left_high/cam_right_high`（矫正双目）经轻量立体匹配→度量视差→头坐标系点云→机器人坐标系；腕相机用度量单目深度，并用已知 EE 位姿 + 夹爪几何做尺度对齐；再与 FK 连杆云融合成**机器人系场景点云**。用 **GC-MAE 式自监督**（重建当前点云 + 预测下一时刻几何）把它压成 token；既可用 Canonical 正交视图渲染喂给 2D 主干（OG-VLA/BridgeVLA 思路），也可直接注入动作专家（PointVLA 思路）。**并做特权蒸馏**：离线用数据集里评测端拿不到的 `torso` 系 EE / `state_d435` 当 teacher，监督只用 API 模态的 student。

3. **REVIEW-GATE（动作审查门 + 审查留痕）**：在 `get_action` 的返回块被真实执行前，过一道三层审查——(T1) 确定性安全规则（关节/速度/加速度限、胶囊体自碰撞、工作空间包络、桌面穿透、不可逆单发保护）；(T2) 学习式风险/分布外 critic（集成不确定性 + 潜密度）给出 `risk·p_fail`；(T3) 人体在场检测（来自头部双目 3D）触发减速/让行包络。审查结论只有三种：放行 / 修复（裁剪到安全包络）/ 否决（回退到安全保持或重查询），并输出**审查留痕**作为可审计产物与 §6 可信度证据。

三个词怎么落地：

| 词 | 落地 | 不做什么 |
|---|---|---|
| **最小可行产品** | 三级门控交付、每级可提交 checkpoint、默认 joint + 动作块时序集成 + 子目标早停、任何新点先过「让关卡变绿」测试 | 不再新造大框架；不为未验证的模块写长篇推导；不做无法在两周内上机的组件 |
| **三维感知** | 矫正双目→度量点云、腕相尺度对齐、机器人系融合、GC-MAE 自监督、正交视图规范化、特权蒸馏 | 不假设有深度传感器或触觉；不做需要额外硬件/标定的重型 SLAM |
| **伦理审查** | 动作审查门（规则+学习+人体三层）、否决/修复/回退、审查留痕、人—机让行、§6 动作规律性 | 不做纯哲学讨论；不做会大量误杀成功动作的过度保守；不引入评测端看不到的输入 |

## 1. 研究日志：本轮先做「事实再基线化」

### 1.1 参赛对象核对（避免答错比赛）

搜索确认存在**同名多义**：`unibot.org` 是加密货币的 Telegram 交易机器人（`unibot.org/training.jsp`、Unibot V2 迁移），与机器人无关；另有若干同名软件。**用户所指、本报告所研究的是「宇树科技 UniBot 世界挑战赛」（`unibot.unitree.com`）**，即以 Unitree G1 为平台的具身智能泛化操作评测（32 项桌面任务、5 类泛化、单模型通才赛道、远程标准化 API 接入）。下文一律按此展开。

### 1.2 竞赛接口硬约束（复述，作为一切设计的边界）

```text
C1. 观测目录（仅声明者才发送）：4×RGB（cam_left_high/cam_right_high/cam_left_wrist/
    cam_right_wrist）+ left/right_arm[7] + left/right_ee_pose_gripper_base[6]
    + left/right_gripper[1] + lower_body[15] + language[str]。
C2. 动作目录：共享键 left/right_gripper[1]、pivot[7]；joint 模式加 left/right_arm[7]，
    ee 模式加 left/right_ee_pose_gripper_base[6]；二者互斥；每个数组形如 (T_a,·)。
C3. metadata 一次握手：control_space / obs_delta_indices（选通道+时间堆叠）/ image_resize /
    action_chunk_size / token。
C4. N 台机器人→从 8765 起的 N 个连续端口；每端口独立 episode、并发、可各自实现（单进程/
    共享后端），但必须状态隔离、互不阻塞。
C5. §6：延迟与抖动、返回动作的统计规律性，均作为可信度依据并可随榜单展示。
```

### 1.3 本轮新增的「可利用事实」（这是 M3S 的支点）

```text
N1. 头部双目是 rectified（矫正）对 → 可直接做稠密立体匹配得到度量视差；
    数据卡给出相机尺寸 480×640×3、30fps、AV1 编码、LeRobot v3.0。
N2. 数据集含评测端不暴露的特权状态：*_ee_pose_gripper_torso、state_d435、
    recomputed_ee_valid；动作侧还含 base_command、pivot、gripper_controls 等。
    → 可在「特权蒸馏」里当 teacher 信号，学一个只用 API 模态的 student。
N3. UnifoLM-VLA-0 开源（Apache-2.0）：单策略、12 类 G1 任务、RLDS 训练栈、
    constants 里有 NUM_ACTIONS_CHUNK / ACTION_DIM / PROPRIO_DIM / 归一化。
    → 这是 MVP 的最短路径基座（但挑战数据是 LeRobot v3.0，其训练栈期望 v2.1，需转码）。
N4. 3D-aware VLA 已有成熟范式可直接借用：PointVLA（向动作专家注入 3D）、
    BridgeVLA（3D→多正交视图+2D heatmap，样本高效，真机均值 +32%）、
    OG-VLA（多视 RGBD→点云→canonical 正交视图→扩散，泛化 +40% 相对）、
    Lift3D-VLA（几何+动力学自监督 GC-MAE 式）。
N5. 近邻 SOTA 仍是「世界动作模型 + 闭环 rollout + 异步推理」一脉；其在真机上亦非碾压
    （LingBot-VA 降低 NFE 后骤降），说明**实时性与保真度的缺口尚未被填平**，
    「轻量、可出货」仍有空间。
```

### 1.4 对前 22 轮 ZEST 家族的诚实剪枝（MVP 纪律的第一次应用）

```text
KEEP（进入主线，必须能出货）：
  - 接口合规与 N 端口服务（这是参赛前提，M1 必做）。
  - 「越不确定越保守」的内核 → 降维成 REVIEW-GATE 的一个阈值策略。
  - 失败/预后思想 → 只保留一个 <1M 的 p_fail 小头，并入审查门，不做独立大模块。
DEMOTE（降为旁路，等主线绿色再碰）：
  - 事件触发块内闭环：其收益强依赖「评测端是否每步回调」这一未证实前提；
    在证实前不作为主线（见 §5 第一风险）。
  - 双臂协同流形、多端口投机预取：价值真实，但排在 M2/M3 之后。
PRUNE（删除）：
  - 力/触觉模态（接口无此通道）；5 秒物体声纹探测（耗步骤、无通道）；
    云端 VLA 三级级联（给 §6 延迟埋雷）；繁复多模块（C-MAP/KCL/AHD/DRS…）。
NEW（本轮三词带来）：
  - MVP-SPINE、3D-ANCHOR（+特权蒸馏）、REVIEW-GATE（+审查留痕）。
```

一句话：**把研究清单从「加法」切换到「先收敛、再精选「两个真杠杆」」。**

## 2. 直觉深化：三个词怎样咬合成一个飞轮

```text
最小可行产品（M1）——出货脊柱：有基线 → 才谈得上「让关卡变绿」。
        │ 绿色基线提供：可交互接口、可回归的失败样本、可信的延迟基线
        ▼
三维感知（M2）——几何杠杆：用免费双目把「外观」换成「度量几何」，
        专治位置/干扰物/背景/未见物品四条几何泛化轴，并利于插拔/堆叠。
        │ 3D 同时给审查门提供：碰撞几何、人体 3D 位置、不可逆接触几何
        ▼
伦理审查（M3）——安全杠杆：用 3D 审查每个动作块，否决/修复/让行，留痕。
        │ 审查门把风险反馈回数据与策略：哪些状态该补数据、哪些动作该收缩
        ▼
回到 M1：飞轮 —— 出货的基线 → 3D 提升 → 审查保护 → 更多成功样本 → 更强基线。
```

三处耦合的「甜点」非常具体：

1. **立体双目 → 审查门**：自碰撞与人体让行都需要几何；双目免费给几何。
2. **特权蒸馏 → 三维锚定**：数据集里评测端没有的 `torso` 系 EE 与 D435 位姿，是训练 3D student 的免费监督。
3. **审查留痕 → §6 可信度**：审查门不是「遮挡失败的补丁」，而是官方明确考核项的加分位——判据是「动作规律、延迟稳定」，审查门恰好保证这两点。

## 3. 三个创新点的正式化（动机 / 差异 / 可行性 / 资源 / 步骤 / 风险）

### 3.1 MVP-SPINE（最小可行脊柱）

```text
目标：在最短时间内产出「可真机跑、可提交、可回归」的 checkpoint，并据此校准研究优先级。
三级门控（每级结束都必须有一个绿色 checkpoint 可提交）：
  G0 接口冒烟：跑通官方 example server+client；用自写 client 逆向验证 C1–C5；
             确认端口数 N 与 URL/握手/token 行为。产出：可交互空策略 + 接口语义备忘。
  G1 能上榜的基线：微调 UnifoLM-VLA-0（或备选 GR00T/pi0 系）于 32k 演示；
             joint 空间、动作块 + 时序集成、按子目标/夹爪信号早停省步骤分。
             产出：全 32 任务单模型 checkpoint + 离线/仿真回归分数。
  G2 加 3D-ANCHOR、再加 REVIEW-GATE（见 3.2/3.3）。
门控规则：新想法只有在「让某个既有关卡变绿」时才进主线；否则进旁路清单。
```

**动机**：榜首 <30%，榜单还空着——**先上桌**。
**与现有方案的差异**：前 22 轮是「先造框架、再想落地」；M1 是「先落地、再决定造什么」。
**可行性**：极高（基座、数据、接口都在）。
**资源**：基座权重 + 32k 演示 + 1–8 张 GPU + 约 1–2 周。
**落地步骤**：见产物区 §2。
**风险**：数据格式转码（LeRobot v3.0 → UnifoLM 训练栈期望的 v2.1/RLDS）；32k 演示的训练算力。

### 3.2 3D-ANCHOR（三维锚定 + 特权蒸馏）

```text
输入：I_head = (I_L, I_R)（矫正双目）、I_wrist(2)、q/ee/gripper（FK 可得）、语言 l
步骤：
  1) 立体匹配：D = StereoNet(I_L, I_R) → 视差 → 头系度量点云 X_head
                （需要基线 b 与焦距 f；若未知则离线自标定，见产物区 §3.2）
  2) 腕相深度：d_wrist = MetricMonoDepth(I_wrist)，用 EE 位姿 + 夹爪几何做尺度对齐
                （夹爪指尖在图像中可见 → 给出尺度锚点）
  3) 机器人系融合：X_base = FK 变换(X_head) ∪ FK 变换(X_wrist) ∪ 连杆胶囊云
  4) 表示： (a) 点云 token 注入动作专家（PointVLA 式）；或
           (b) canonical 正交视图渲染后喂 2D 主干（OG-VLA/BridgeVLA 式）
  5) 自监督：L_geo = 重建当前点云 + 预测 t+1 点云（GC-MAE 式，无需标注）
  6) 特权蒸馏：teacher 用 torso 系 EE / state_d435；student 只用 API 模态；
               L_kd = 对齐 teacher/student 的几何 token 与抓取关键点分布
```

**动机**：三维几何是泛化五轴里「最几何」的四轴的正解，且双目矫正使成本极低。
**与现有方案的差异**：不用任何额外传感器；把「双目」这件被数据卡低调标注的事实**显式兑现**；并首次利用数据集的**特权状态**。
**可行性**：高（立体/深度网络现成且轻；矫正双目省去极线校正）。
**资源**：预训练立体/深度网络；一次离线标定；约 1 GPU 周。
**落地步骤**：视差正确性测试（对已知物体尺寸/桌面平面）→ 标定 → 编码 → GC-MAE 预训练 → 特权蒸馏 → 消融。
**风险**：反光/透明物体（药瓶、玻璃、网口）深度失败；评测端 `image_resize` 降采样损伤视差；双目基线/内参未公开需自标定；AV1 压缩伪影。

### 3.3 REVIEW-GATE（动作审查门 + 审查留痕）

先把「伦理」落成一个精确的技术对象：**一个独立于生成器的审查者**。

```text
T1 确定性安全规则（廉价、可证明）：关节限位；速度/加速度上限；胶囊体自碰撞；
   工作空间包络（桌面高度、前伸/侧伸边界）；桌面穿透；不可逆单发保护
   （如断网口/拔线缆/倒药等「一次性」动作需更严的预检）。
T2 学习式风险 critic：r_θ(o, A) = 集成不确定性 + 潜空间密度 + p_fail（<1M 小头）；
   触发「修复」或「否决」。标签：演示内自监督（成功/越界/超时/抖动）标定。
T3 人体在场：由头部双目 3D 检测人体/手 → 减速—让行—必要时安全保持包络
   （对应「人为干扰」轴）。
审查结论三态：PASS / REPAIR（把块投影回安全包络）/ VETO（回退安全保持或重查询）。
审查留痕：每步给出 (decision, reason_code, margin)，既作可审计产物，也作 §6 可信度证据。
```

**动机**：人为干扰轴、易损/不可逆对象、以及官方 §6 的「动作规律性与延迟稳定」。
**与现有方案的差异**：不是被动地按风险缩放动作（旧 round 的 α 收缩），而是**主动否决/修复并留痕**；审查者的输入来自免费的 3D。
**可行性**：T1 高；T2 中；T3 中（用现成检测器 + 双目 3D）。
**资源**：Pinocchio/自研运动学与胶囊碰撞；现成人体/手检测器；离线标定标签。
**落地步骤**：先只上 T1 → 在演示上测「误杀率」（应≈0）→ 加 T2 → 仿真里做人–机让行回归 → 出货。
**风险**：误杀成功动作（必须极度保守：只否决明确越界）；人体检测延迟；corner case 多。

## 4. 持续迭代的创新点清单（本轮修订）

> 🟢 保留推进　🔵 新增　🟡 降级/旁路　🔴 剪枝

| # | 创新点 | 状态 | 动机 | 与现有方案差异 | 可行性 | 所需资源 | 落地步骤 | 风险 |
|---|---|---|---|---|---|---|---|---|
| 1 | MVP-SPINE（门控交付脊柱） | 🔵 | 榜首空榜、需先上桌 | 把研究当产品；每级可提交 checkpoint | 极高 | 基座+32k 演示+1–8 GPU | G0 接口冒烟→G1 基线微调→G2 加 3D/审查 | 转码/算力 |
| 2 | 3D-ANCHOR（矫正双目→机器人系点云+特权蒸馏） | 🔵 | 免费双目几何，治四轴泛化 | 首次兑现 rectified stereo + 特权状态 | 高 | 立体/深度网+标定 | 视差校验→标定→编码→GC-MAE→蒸馏 | 反光/透明/降采样 |
| 3 | REVIEW-GATE（动作审查门+留痕） | 🔵 | 人为干扰/易损/§6 可信度 | 主动否决/修复/留痕，而非被动缩放 | 中高 | 运动学碰撞+检测器 | T1 规则→误杀率→T2 critic→T3 让行 | 误杀/延迟 |
| 4 | 动作块 + 时序集成 + 子目标早停 | 🟢 | MVP 最低成本的稳定性与步骤分收益 | ACT/时序集成是成熟基线；早停省步骤 | 极高 | 无 | 接入基线→回归 | 集成滞后 |
| 5 | joint 控制空间优先 | 🟢 | 与演示/蒸馏一致，规避 IK 误差 | 明确默认 + ee 消融 | 高 | 无 | — | 少数任务 ee 更优 |
| 6 | 多端口共享服务 + 状态隔离 | 🟢 | 接口前提 + §6 延迟稳定 | 从工程升为「可信度得分项」 | 高 | 部署环境 | 连续批处理+隔离+优先级 | 并发串扰 |
| 7 | 事件触发块内闭环 | 🟡 | 理论收益大 | 依赖评测是否每步回调 | 中 | — | 先验证接口语义再定强度 | 前提未证实 |
| 8 | 双臂协同流形 + 互预测 | 🟡 | 官方明列双臂任务 | 显式跨臂约束 | 中高 | 双臂子集 | 排在 M2/M3 之后 | 约束过紧 |
| 9 | p_fail 预后小头 | 🟡 | 失败前兆 | 并入审查门，不再独立成篇 | 中 | 自监督标签 | 与 T2 critic 合并 | 标签噪声 |
| 10 | 力/触觉模态 | 🔴 | — | 接口无此通道 | 不可行 | — | 删除 | — |
| 11 | 5 秒物体声纹探测 | 🔴 | 耗步骤、无验证 | — | — | — | 删除 | — |
| 12 | 云端 VLA 级联 | 🔴 | 给 §6 延迟埋雷 | — | — | — | 删除 | — |

## 5. 风险与未证实前提（本轮只列「决定路线」的几条）

| 风险/未知 | 为什么关键 | 何时必须解决 | 缓解 |
|---|---|---|---|
| **评测端是「每步回调」还是「整块执行」** | 决定块内闭环是强收益还是空谈，也决定审查门的粒度 | G0 | 用官方 example client 逆向验证；双模式兼容设计 |
| **双目基线/内参是否可得** | 无它则 3D-ANCHOR 需自标定 | G2 前 | 离线自标定（棋盘/已知物）；用桌面平面与已知物尺寸交叉校验 |
| **步骤分具体口径未公开** | 决定「早停/省步」是否划算 | 尽早 | 先按「子目标完成 + 少无效步」保守优化；留意规则文档更新 |
| **数据 LeRobot v3.0 vs 基座期望 v2.1** | 直接卡住 G1 | G1 前 | 写转码适配；或用原生支持 v3 的 LeRobot 训练栈 |
| **反光/透明物体立体失败** | 直接影响插拔/倒药等关键任务 | G2 | 多帧时序滤波 + 腕相近距离兜底 + 审查门降级 |
| **审查门误杀** | 会直接掉成功率 | M3 始终 | 只否决「确定性越界」；学习式 critic 只做「修复」不做「否决」 |

## 6. 本轮最大的风险

**「三维感知」的收益高度依赖一个未公开的硬件事实：双目是否真的可用于度量重建（基线是否稳定、是否与数据卡一致、评测端降采样后是否还够用）。如果双目在评测数据上不可靠，3D-ANCHOR 会退化为「多视角 2D 特征增强」——仍有价值，但不再享有「免费度量几何」的红利。** 因此本轮把「**用 G1 基线的真实回传图像做一次双目视差正确性验证**」列为与「接口语义验证」并列的**第一优先实验**；它决定 3D-ANCHOR 是「强杠杆」还是「弱增强」。

## 7. 灵感词贯通

> **最小可行产品**：不是一句口号，而是一条门控流水线（G0/G1/G2）与一条硬规则——「新想法必须先让某个关卡变绿」。它把前 22 轮的「加法」扭成「先收敛、再精选两个真杠杆」。
> **三维感知**：把数据卡里低调标注的「rectified stereo」显式兑现为机器人系度量点云；用 canonical 正交视图/点云 token 注入 VLA；用 GC-MAE 自监督与「特权状态蒸馏」把 3D 知识灌进只用 API 模态的 student。
> **伦理审查**：落成「动作审查门」——独立于生成器的审查者，三层（确定性安全 / 学习式风险 / 人体在场）三态（放行/修复/否决）并留痕；既守住人—机安全与财产完整性，又把官方 §6 的可信度变成显式产物。

## 8. 参考来源（检索日期 2026-11-05）

- UniBot 世界挑战赛首页：https://unibot.unitree.com/
- 挑战赛任务集（32 任务 / 32000 episodes / 169h）：https://unibot.unitree.com/challenges.html
- 排行榜（Coming Soon）：https://unibot.unitree.com/leaderboard.html
- 运行记录（Coming Soon）：https://unibot.unitree.com/runs.html
- 提交模板与接口规范（观测/动作目录、metadata、N 端口、§6 可信度）：https://github.com/unitreerobotics/unibot_submission
- 数据集（LeRobot v3.0、30fps、4 相机、**head_stereo_left/right rectified**、特权状态、Dex1 夹爪 5.5–0.0）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- 挑战数据集集合（32 个 G1_Dex1_*）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- UnifoLM-VLA-0 开源（Apache-2.0、单策略 12 类、RLDS/LeRobot、constants）：https://github.com/unitreerobotics/unifolm-vla
- UnifoLM-WMA-0 集合（世界模型-动作）：https://huggingface.co/collections/unitreerobotics/unifolm-wma-0
- Unitree G1 真机操作聚合榜（LingBot-VA 66.7；Flash-WAM 60/50）：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world
- PointVLA（向 VLA 注入 3D，arXiv:2503.07511）：https://arxiv.org/abs/2503.07511
- BridgeVLA（3D→多正交视图+heatmap，NeurIPS 2025，真机均值 +32%，arXiv:2506.07961）：https://bridgevla.github.io/home_page.html
- OG-VLA（多视 RGBD→点云→canonical 正交视图→扩散，ICRA 2026 投稿）：https://og-vla.github.io/
- Lift3D-VLA（几何+动力学自监督，arXiv:2607.06564）：https://arxiv.org/abs/2607.06564
- 社区赛制拆解仓库（赛制/32 任务总表/训练路线/接口验证；检索到但直连 404，需谨慎引用）：https://github.com/Ed-gjd/unibot-challenge
- 同名歧义提示（与机器人无关）：https://unibot.org/training.jsp

> 本轮一句话押注：**最值得押注的是创新点 1（MVP-SPINE）——先用开源 UnifoLM-VLA-0 在 32k 演示上出货一条可提交基线；它是唯一能让其余一切创新「有分数可依附」的支点，其次才是 3D-ANCHOR 这个用免费矫正双目换来的几何杠杆。**
<!-- IDEA:END -->

<!-- ARTIFACT:START -->
# 第 23 轮产物 · MVP-3D-SHIELD（M3S）技术报告：最小可行脊柱 + 三维锚定 + 动作审查门

> 检索日期：2026-11-05。本文给出 M3S 的门控交付计划、3D-ANCHOR 的可运行设计、REVIEW-GATE 的规则与算法、接口合规的策略骨架、实验协议、预期结果与风险。所有结论以 §1 的接口硬约束与 §9 的公开来源为界；未见实测的数值一律标注为「设计目标」。

## 0. 结论

不新造大框架。M3S 是一条**门控交付脊柱**上加两处「竞赛接口已经免费给、却常被忽略」的杠杆：

1. **MVP-SPINE**：G0 接口冒烟 → G1 用开源 **UnifoLM-VLA-0（Apache-2.0）** 在 32k 演示上微调出可提交基线 → G2 加 3D 与审查。每级收尾一个绿色 checkpoint，任何新想法必须先让某个关卡变绿。
2. **3D-ANCHOR**：`head_stereo_left/right` 是**已矫正**双目 → 免费度量点云；腕相用度量单目深度 + EE 尺度锚；融合成机器人系点云；GC-MAE 自监督；**特权蒸馏**用评测端拿不到的 `torso` 系 EE / `state_d435` 当 teacher。
3. **REVIEW-GATE**：动作块真实执行前的三层审查（确定性安全 T1 / 学习式风险 T2 / 人体在场 T3），三态输出（PASS / REPAIR / VETO）+ **审查留痕**；把「伦理审查」落成可交付的安全与可信度机制。

对齐硬约束：观测仅 4×RGB + 关节/EE(base)/夹爪/下半身 + 语言；动作 joint 或 ee 互斥、块式返回；N 连续端口；§6 考核延迟/抖动与动作规律性（来源见 §9）。

## 1. 接口硬约束与模态映射

### 1.1 提交接口（一次握手 + 逐步调用）

| 项 | 规范 | M3S 的遵守 |
|---|---|---|
| `metadata` | `control_space` / `obs_delta_indices`（选通道 + 时间堆叠）/ `image_resize` / `action_chunk_size` / `token` | 固定；3D/审查模块不改接口 |
| `get_action(obs)` | 返回 chunk；含 `meta.token` + 共享键 + 对应控制空间双键 | 严格按 §5 打包 |
| `reset()` | 每 episode 起始调用一次 | 清空历史、点云缓存、审查状态 |
| 端口 | N 机器人 → 8765..8765+N−1，状态隔离、并发不互相阻塞 | 共享后端 + 每端口状态隔离 |
| §6 | 延迟/抖动/动作统计规律性 = 可信度 | 审查留痕 + 优先级调度 + 稳定打包 |

### 1.2 数据集模态 vs 评测端模态（关键：特权信息）

| 数据集键（`G1_Dex1_FoldTowel`） | 评测 API 是否暴露 | M3S 用法 |
|---|---|---|
| `head_stereo_left` / `head_stereo_right`（**rectified**） | 是（`cam_left_high` / `cam_right_high`） | 立体匹配 → 度量点云 |
| `wrist_left` / `wrist_right` | 是（`cam_left_wrist` / `cam_right_wrist`） | 度量单目深度 + 尺度对齐 |
| `left/right_arm`、`left/right_gripper`、`lower_body` | 是 | 本体 + FK |
| `*_ee_pose_gripper_base` | 是 | 动作/状态 |
| `*_ee_pose_gripper_torso` | **否** | 特权 teacher（蒸馏） |
| `state_d435` | **否** | 特权 teacher（相机外参/视角） |
| `recomputed_ee_valid` | **否** | 数据清洗/有效性门 |
| `base_command` / `action_torso` / `action_d435` / `gripper_controls` | **否** | 训练时辅助监督 |

> 结论：训练可以「看得更多」，但**推理必须只用 API 模态**。这正是特权蒸馏的用武之地。

## 2. MVP-SPINE：三级门控交付计划

```text
G0（接口冒烟，1–3 天）——产出：可交互空策略 + 接口语义备忘
  1. 跑通官方 example：run_server.py + run_client.py，确认 token 校验、端口。
  2. 自写 client 逆向验证「每步回调 vs 整块执行」，并记录 N 端口并发行为。
  3. 记录单次 get_action 的基线时延分布（p50/p95），作为 §6 参照线。
  Go 条件：官方 example 端到端无 ACTION REJECTED；接口语义备忘写入仓库。

G1（能上榜的基线，1–2 周）——产出：全 32 任务单模型 checkpoint
  1. 数据：32 个 G1_Dex1_* 演示（LeRobot v3.0）→ 转码到训练栈所需格式。
  2. 基座：UnifoLM-VLA-0（Apache-2.0），Qwen2.5-VL 主干 + 动作专家。
     在 constants 里设 NUM_ACTIONS_CHUNK / ACTION_DIM / PROPRIO_DIM 与归一化。
  3. 控制空间：默认 joint（与演示一致，规避 IK 误差）；ee 作为消融。
  4. 稳定化：动作块 + 时序集成（ACT 式指数加权）+ 子目标/夹爪信号早停省步骤。
  Go 条件：在留出集/仿真回归上不低于「未微调基座」，且延迟满足 G0 基线。

G2（加杠杆，2–4 周）——产出：M3S 完整策略
  G2a 加 3D-ANCHOR；G2b 加 REVIEW-GATE。每个子步各有一个 checkpoint 与消融。
硬规则：任何新想法必须先证明「能让 G0/G1/G2 某关卡变绿」，否则进旁路清单。
```

**为什么基座选 UnifoLM-VLA-0**：Apache-2.0、专为 G1 单策略多任务设计（12 类含插拔/放置）、自带训练/推理/部署（server-client 形态与挑战赛天然吻合）。**风险**：其训练栈期望 LeRobot v2.1/RLDS，而挑战数据是 v3.0 → 需写 `v3.0→v2.1/RLDS` 转码；或改用具原生 v3 支持的数据加载层。

## 3. 3D-ANCHOR：从矫正双目到机器人系点云

### 3.1 流水线与符号

```text
输入：双目对 (I_L, I_R)（矫正），腕相 I_{w1}, I_{w2}，本体状态 s（含 EE 位姿、关节角）
(1) 立体：  D = g_stereo(I_L, I_R)            # 视差图
            X_head = π^{-1}_head(D; f, c, b)  # 头系度量点云（f 焦距, c 主点, b 基线）
(2) 腕相：  Z_w = g_depth(I_w)                # 度量单目深度（或尺度不定，见 3.2）
            尺度锚：夹爪指尖已知几何长度 L_gripper 在图像中的投影 → 解尺度因子 σ_w
            X_wrist = π^{-1}_wrist(Z_w · σ_w; K_w, T_w)  # 腕系点云
(3) 融合：  X_base = T_head→base · X_head  ∪  T_wrist→base · X_wrist  ∪  X_links(FK)
(4) 表示：  E_geo = Enc_point(X_base, s, l)    # 轻量 Point-Transformer/VoxelNet
            A) 注入式：E_geo 作为额外 token 拼到动作专家输入（PointVLA 式）
            B) 渲染式：把 X_base 渲染为 K 张 canonical 正交视图，喂 2D 主干
                       （OG-VLA/BridgeVLA 式，利于复用 2D 预训练）
(5) 自监督：L_geo = ||Dec(E_geo) − X_base||² + λ_f ||Pred(E_geo, a_{t:t+H}) − X_base^{t+1}||²
            （GC-MAE 式：重建当前 + 预测未来几何，零人工标注）
(6) 蒸馏：  teacher 用特权状态（torso 系 EE / state_d435）算几何监督；
            L_kd = KL(E_geo^stu || E_geo^tea) + λ_kp ||kp_stu − kp_tea||²
```

### 3.2 双目是否可信：第一优先验证（对应想法区 §6）

```text
V1. 内参/基线未知时的自标定：
    - 用已知物体尺寸（如测试管直径、纸杯口直径、药瓶高度）标定 b·f 的组合量；
    - 用桌面平面做单应性，验证视差→深度的单调性与平面度；
    - 交叉校验：头系点云中「手腕 EE 位置」应与本体 EE 位姿（投影到头系）吻合。
V2. 降采样鲁棒性：分别用 native 480×640 与 240×320 跑立体，比较平面度误差，
    决定 metadata.image_resize 是否是 3D 的敌人。
V3. 反光/透明兜底：多帧时序中值滤波 + 腕相近距离补洞 + 审查门降级（视差置信低则信赖 2D）。
Go 条件：桌面平面 RMS 误差与已知物尺寸误差在可接受区间；否则 3D-ANCHOR 降级为
「多视角 2D 特征增强」，不宣称度量几何。
```

### 3.3 可运行骨架（只列关键件，其余略）

```python
import numpy as np
import torch
import torch.nn as nn


class StereoDepth(nn.Module):
    """轻量立体匹配：输出视差，再反投影为头系点云。可用预训练权重初始化。"""

    def __init__(self, backbone="minimal"):
        super().__init__()
        self.net = nn.Sequential(  # 占位：实际用 IGEV/RAFT-Stereo/FoundationStereo 轻量版
            nn.Conv2d(6, 32, 3, padding=1), nn.SiLU(),
            nn.Conv2d(32, 32, 3, padding=1), nn.SiLU(),
            nn.Conv2d(32, 1, 3, padding=1),
        )

    def forward(self, i_l, i_r):
        x = torch.cat([i_l, i_r], dim=1)
        return self.net(x)  # [B,1,H,W] 视差

    @staticmethod
    def backproject(disp, f, cx, cy, b):
        # Z = f*b/disp; X = (u-cx)Z/f; Y = (v-cy)Z/f
        B, _, H, W = disp.shape
        u = torch.arange(W, device=disp.device).view(1, 1, W)
        v = torch.arange(H, device=disp.device).view(1, H, 1)
        Z = f * b / disp.clamp_min(1e-3)
        X = (u - cx) * Z / f
        Y = (v - cy) * Z / f
        return torch.stack([X, Y, Z], dim=-1)  # [B,H,W,3] 头系


class GeoEncoder(nn.Module):
    """机器人系点云编码 + GC-MAE 自监督头。"""

    def __init__(self, d_out=256, n_pts=1024):
        super().__init__()
        self.n_pts = n_pts
        self.pt = nn.Sequential(
            nn.Linear(3 + 4, 128), nn.SiLU(),   # xyz + 本体(FK/关节)4维占位
            nn.Linear(128, 256), nn.SiLU(),
            nn.Linear(256, d_out),
        )
        self.recon = nn.Linear(d_out, 3)
        self.future = nn.Linear(d_out, 3)

    def forward(self, pts, proprio):
        # pts: [B,N,3] 机器人系; proprio: [B,P]
        f = proprio.unsqueeze(1).expand(-1, pts.size(1), -1)
        h = self.pt(torch.cat([pts, f], dim=-1))     # [B,N,d]
        e = h.mean(dim=1)                            # 池化为几何 token
        return e, self.recon(e), self.future(e)      # token, 重建, 未来几何预测
```

## 4. REVIEW-GATE：动作审查门

### 4.1 三层审查

```text
T1 确定性安全（可证明、零学习）：
   c1 joint 限位：  q_min ≤ q_target ≤ q_max
   c2 速度/加速度：  |Δq|/Δt ≤ v_max,  |Δ²q|/Δt² ≤ a_max
   c3 自碰撞：      胶囊体近似，任意两连杆距离 ≥ d_min（用 FK，来自 q_target）
   c4 工作空间包络： 桌面平面之上、前伸/侧伸界内
   c5 不可逆保护：   对「拔线缆/断网口/倒药/开锁」等一次性动作，要求更高置信与更慢速率
T2 学习式风险 critic：
   r_θ(o, A) = w1·Σ_ens Var[f_k(o,A)] + w2·(−log p_θ(z_t)) + w3·p_fail(o,A)
   阈值 τ_r：低→PASS；中→REPAIR（向安全包络投影）；高→VETO（安全保持/重查询）
   标签：演示自监督——成功/越界/超时/抖动/高惊喜 自动标注
T3 人体在场：
   由头部双目 3D 检测人/手 → 距离 d_human
   若 d_human < d_slow：降速；若 d_human < d_stop：安全保持（让行）
```

### 4.2 审查决策与留痕

```text
决策三态： PASS / REPAIR / VETO
REPAIR 实现：A' = Proj_Safe(A)，S = {c1..c5} 的交（逐段裁剪、限幅、回退到上一安全点）
VETO 实现：  返回安全保持块（保持位姿/缓慢回撤），并标记 reason_code 触发重查询
审查留痕：   trace_t = (decision, {margin_c}, r_θ, d_human)
```

**关键约束**：T2 学习式 critic **只允许 REPAIR，不允许 VETO**（避免误杀成功动作）；VETO 仅由 T1 的**确定性越界**或 T3 的**人体过近**触发。这条纪律把「掉成功率」的风险压到最低。

### 4.3 可运行骨架

```python
class ReviewGate:
    def __init__(self, q_min, q_max, v_max, a_max, d_min=0.02,
                 critic=None, human_det=None, tau_repair=0.5, d_slow=0.8, d_stop=0.4):
        self.q_min, self.q_max = q_min, q_max
        self.v_max, self.a_max, self.d_min = v_max, a_max, d_min
        self.critic, self.human = critic, human_det
        self.tau_repair, self.d_slow, self.d_stop = tau_repair, d_slow, d_stop

    def _rule_violations(self, A, q_prev, dt):
        v = np.abs(A[:, :14] - q_prev[None, :14]) / dt
        bad = {
            "limits": bool((A[:, :14] < self.q_min).any() or (A[:, :14] > self.q_max).any()),
            "velocity": bool((v > self.v_max).any()),
            "self_collision": not self._capsules_clear(A),
            "workspace": not self._inside_envelope(A),
        }
        return bad

    def _capsules_clear(self, A):
        # 用 FK 把关节块映射为胶囊体，检查任意间距 >= d_min（实现略）
        return True

    def _inside_envelope(self, A):
        return True  # 桌面平面之上、前伸/侧界内（实现略）

    def review(self, obs, A, q_prev, dt):
        bad = self._rule_violations(A, q_prev, dt)
        if any(bad.values()):
            return self._repair(A, bad), {"decision": "REPAIR", "rule": bad}
        d_human = self.human(obs) if self.human else np.inf
        if d_human < self.d_stop:
            return self._hold(obs), {"decision": "VETO", "reason": "human", "d": d_human}
        if self.critic is not None:
            r = self.critic(obs, A)
            if r > self.tau_repair:
                return self._repair(A, {"risk": r}), {"decision": "REPAIR", "risk": r}
        return A, {"decision": "PASS", "d": d_human}

    def _repair(self, A, why):
        A = A.copy()
        A[:, :14] = np.clip(A[:, :14], self.q_min, self.q_max)
        # 限速：把相邻步差分按 v_max 截断（实现略）
        return A

    def _hold(self, obs):
        return np.repeat(obs_current_joint(obs)[None], 8, axis=0)  # 安全保持（占位）
```

## 5. 接口合规策略骨架（含 N 端口共享服务）

```python
import os
import numpy as np
import torch


class M3SPolicy:
    def __init__(self, base_policy, geo_encoder=None, review_gate=None):
        self._token = os.environ["UNIBOT_SUBMISSION_TOKEN"]
        self._space = os.environ["UNIBOT_CONTROL_SPACE"]  # joint | ee
        self.base, self.geo, self.gate = base_policy, geo_encoder, review_gate
        self.T_a = 8
        self.reset()

    @property
    def metadata(self):
        return {
            "control_space": self._space,
            "obs_delta_indices": {
                "observation.language": [0],
                "observation.images.cam_left_high": [-6, -3, 0],
                "observation.images.cam_right_high": [-6, -3, 0],
                "observation.images.cam_left_wrist": [-6, -3, 0],
                "observation.images.cam_right_wrist": [-6, -3, 0],
                "observation.state.left_arm": [-4, 0],
                "observation.state.right_arm": [-4, 0],
                "observation.state.left_ee_pose_gripper_base": [-4, 0],
                "observation.state.right_ee_pose_gripper_base": [-4, 0],
                "observation.state.left_gripper": [-4, 0],
                "observation.state.right_gripper": [-4, 0],
                "observation.state.lower_body": [-4, 0],
            },
            "image_resize": {
                # 双目保留较高分辨率以护视差；腕相可更小
                "observation.images.cam_left_high": [240, 320],
                "observation.images.cam_right_high": [240, 320],
                "observation.images.cam_left_wrist": [160, 160],
                "observation.images.cam_right_wrist": [160, 160],
            },
            "action_chunk_size": self.T_a,
            "token": self._token,
        }

    def reset(self):
        self.hist.clear() if hasattr(self, "hist") else None
        self.q_prev = None
        return None

    def _pack(self, A):
        d = {
            "meta.token": self._token,
            "action.left_gripper": A[:, 14:15].astype(np.float32),
            "action.right_gripper": A[:, 15:16].astype(np.float32),
            "action.pivot": A[:, 16:23].astype(np.float32),
        }
        if self._space == "joint":
            d["action.left_arm"] = A[:, 0:7].astype(np.float32)
            d["action.right_arm"] = A[:, 7:14].astype(np.float32)
        else:
            d["action.left_ee_pose_gripper_base"] = A[:, 0:6].astype(np.float32)
            d["action.right_ee_pose_gripper_base"] = A[:, 6:12].astype(np.float32)
        return d

    def get_action(self, obs):
        with torch.no_grad():
            geo = self.geo(obs) if self.geo is not None else None
            A = self.base(obs, geo=geo)[0]           # [T_a, 23] joint 或 [T_a,21] ee
        q_prev = np.concatenate([
            obs["observation.state.left_arm"][-1],
            obs["observation.state.right_arm"][-1],
        ])
        if self.gate is not None:
            A, trace = self.gate.review(obs, A, q_prev, dt=1.0 / 30.0)
            self.last_trace = trace                   # 审查留痕（可信度证据）
        self.q_prev = q_prev
        return self._pack(A)
```

**N 端口共享服务**（对应硬约束 C4 与 §6）：

```text
拓扑：N 个轻量端点（8765..8765+N−1）→ 单推理后端（连续批处理）
隔离：每端口的 obs 历史、点云缓存、审查状态、q_prev 独立
优先级：REPAIR/VETO/重查询 请求优先；对 p95 延迟设 SLO
预取：执行当前块时，预生成「若继续」的候选块，缓冲可能的回退
```

## 6. 实验协议与预期结果（设计目标）

### 6.1 第一优先（决定路线）

| 实验 | 做法 | 判据 |
|---|---|---|
| E1 接口语义 | 自写 client 模拟「每步回调 vs 整块执行」 | 确定闭环粒度与审查粒度 |
| E2 双目可信度 | 3.2 的 V1/V2/V3 | 平面 RMS / 已知物尺寸误差；决定 3D 是强/弱杠杆 |

### 6.2 离线与仿真消融

```text
指标：
  - 动作误差：留出集的 MSE/DTW（joint 空间）
  - 成功代理：LIBERO/RoboTwin 仿真 SR（若可得）
  - 泛化分桶：位置/干扰物/背景/未见物品/人为干扰 五轴分别报告
  - 3D：平面 RMS、抓取关键点误差、点云重建/预测 Chamfer
  - 审查：误杀率（应≈0）、真阳性否决率、T3 让行响应延迟
消融网格：
  {纯基座开环, +时序集成, +3D注入, +3D渲染, +特权蒸馏, +审查T1, +审查T2/T3}
  × {joint, ee}
```

### 6.3 预期结果（设计目标，非声称）

| 模块 | 指标 | 目标 |
|---|---|---|
| G1 基线 | 留出动作误差 | 优于未微调基座（相对 −20% 量级） |
| 3D-ANCHOR | 桌面平面 RMS / 已知物尺寸误差 | 亚厘米级（视立体质量） |
| 3D-ANCHOR | 几何泛化分桶 SR | 相对纯 2D 基线 +5~10pt（预期集中在位置/背景/未见物品） |
| 特权蒸馏 | student vs 无蒸馏 | +2~5pt |
| REVIEW-GATE | 演示误杀率 | ≈0（<0.5%） |
| REVIEW-GATE | 人为干扰轴 | 无碰撞事故、让行成功率↑ |
| 多端口 | p95 延迟/抖动 | 不劣于单端口基线；抖动↓ |

### 6.4 真机/评测（若获资格）

双臂子集（FoldTowel/ArrangePlates/ZipUp/PackBag/ToolboxStorage/PaperCupStacking 等）与非双臂子集分别报告；泛化五轴分桶；延迟 p50/p95/抖动；审查留痕统计（PASS/REPAIR/VETO 比例）。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 评测端整块执行、块内不回调 | 审查门放在块边界；闭环相关创新降为旁路（见想法区 §5） |
| 双目基线/内参不可得或不可靠 | 3.2 自标定 + E2 判据；不可靠则 3D 降级为多视 2D 增强 |
| image_resize 降采样伤视差 | 双目保 240×320 或更高；E2 V2 验证 |
| 数据 v3.0 与基座栈 v2.1 不兼容 | 写转码层或改用支持 v3 的加载器 |
| 反光/透明物体深度失败 | 时序中值 + 腕相兜底 + 审查门按深度置信降级 |
| 审查门误杀 | T2 只 REPAIR 不 VETO；VETO 仅由确定性越界/人体过近触发 |
| 训练算力 | 先 LoRA/部分解冻小规模验证，再全量；分级 checkpoint |

## 8. 时间线（建议，随关卡 Go/Kill 调整）

```text
D1–D3   ：G0 接口冒烟 + E1 接口语义 + E2 双目可信度（两个第一优先实验）
D3–D7   ：数据转码 + 3D-ANCHOR 离线预训练（GC-MAE、特权蒸馏）
D7–D14  ：G1 基线微调 + 时序集成 + 早停；产出第一个可提交 checkpoint
D14–D21 ：G2a 接入 3D-ANCHOR，五轴分桶消融
D21–D28 ：G2b REVIEW-GATE（先 T1，再 T2/T3）；多端口延迟压测
D28+    ：预约评测；按分桶复盘，回到「让关卡变绿」的循环
```

## 9. 参考来源（检索日期 2026-11-05）

- 提交模板与接口规范（观测/动作目录、metadata、N 端口、§6）：https://github.com/unitreerobotics/unibot_submission
- 挑战赛任务集（32 任务 / 32000 episodes / 169h）：https://unibot.unitree.com/challenges.html
- 首页与赛事愿景：https://unibot.unitree.com/
- 数据集（LeRobot v3.0、4 相机、**head_stereo rectified**、特权状态、Dex1 夹爪）：https://huggingface.co/datasets/unitreerobotics/G1_Dex1_FoldTowel
- 挑战数据集集合（32 个 G1_Dex1_*）：https://huggingface.co/collections/unitreerobotics/unibot-v1-challenge-dataset
- UnifoLM-VLA-0（Apache-2.0、单策略 12 类、RLDS/LeRobot、constants）：https://github.com/unitreerobotics/unifolm-vla
- UnifoLM-WMA-0 集合：https://huggingface.co/collections/unitreerobotics/unifolm-wma-0
- Unitree G1 真机操作聚合榜（LingBot-VA 66.7；Flash-WAM 60/50）：https://www.sota2.com/research/sota/robot-manipulation-on-unitree-g1-real-world
- PointVLA（arXiv:2503.07511）：https://arxiv.org/abs/2503.07511
- BridgeVLA（NeurIPS 2025，真机均值 +32%，样本高效，arXiv:2506.07961）：https://bridgevla.github.io/home_page.html
- OG-VLA（canonical 正交视图 + 扩散，ICRA 2026 投稿）：https://og-vla.github.io/
- Lift3D-VLA（GC-MAE 式几何+动力学自监督，arXiv:2607.06564）：https://arxiv.org/abs/2607.06564

> 本轮产物一句话：**M3S = 一条门控交付脊柱（MVP）＋ 用免费矫正双目换来的度量几何（3D）＋ 一道独立于生成器的动作审查门（Review）。先让 G1 变绿，再谈 3D，最后上审查。**
<!-- ARTIFACT:END -->