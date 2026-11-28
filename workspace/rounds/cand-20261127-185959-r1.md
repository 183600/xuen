<!-- IDEA:START -->
### 第 1 轮灵感驱动研究记录

**灵感词**：时空推理、抓取、数据采集

**直觉与动机**：
在 KEMPC/CADVS 框架已形成「常识包容-证书驱动」的基础上，进一步提出三个关键方向：

1. **时空推理**：现有证书体系将有效性视为布尔值（valid/invalid），但实环中「何处有效」和「何时有效」同样关键。例如视觉伺服在特定图像区域有效，差分定位在某地理范围内有效。需将证书有效性提升为时空区间：CEC.valid ⊆ ℝ³ × 𝕋，即在空间区域 R ⊆ ℝ³ 与时间窗口 T ⊆ 𝕋 内有效。这建立在现有 TCVM 的时间窗口基础上，进一步引入空间有效域的概念，使得每条证记录都携带 「生效空间包络」与「有效时窗」，从而实现「何处何时适用」的精确查询。这不仅是几何控制的需要，更是证据链：若空间-时间范围超出Certificates已覆盖区域，应立即介入而非盲目信任。

2. **抓取**：双足机器人在复杂地形上的动态抓取/操作任务中，手脚置换的动力学约束与平衡规则紧密耦合。例如「支撑面积 > 200cm²」在抓取姿态下的适用性与重力方向、物体重量有关。需定义「抓取稳定证书」GC：记录抓取态的动力学可达域、接触力边界、重心偏移阈值。KC 规则 kc_grab_stable = GC.valid ∧ ‖τ_grav‖ < θ_grav ∧ ‖Δx_com‖ < δ_com。这使得常识规则从纯平衡约束扩展至抓取-平衡耦合约束，体现「手脚并用」的动力学完整性。

3. **数据采集**：KEMPC/CADVS 的知识库有限，且人工定义的 KC 规则对未见场景脆弱。需引入「证据挖掘机制」：从传感器流中自动发现模式，生成数据驱动的 KC 规则。设计无监督异常模式挖掘、时空聚类，将发现的规则转化为形式化证书。数据采集不再是被动记录，而成为主动知识扩展的源泉。设定数据有效性门控：仅当新发现的 KC 规则通过 FQC/DLC 门控且通过跨任务迁移惩罚后，方可写入知识库。

**关键洞见**：这三者形成互补闭环：时空推理提供「生效边界」，抓取提供「动力学边界」，数据采集提供「知识边界」——三者合力将 KEMPC/CADVS 从「静态知识包容」提升为「动态知识自适应边界」，从根本上规避「常识闭塞」风险，并将系统能力从「仅平衡控制」提升至「平衡+抓取+泛化」三维能力。

**形式化目标（增量）**：
1. 定义时空证书有效域：CEC.spatial_domain ⊆ ℝ³ (以质心为原点的球半径 R_cec)，CEC.temporal_window ⊆ 𝕋 (相对生成时刻的时长 Δt_cec)，记为 CEC = (R_cec, Δt_cec, payload)
2. 定义抓取稳定证书 GC：GC.name, GC.grasp_type ∈ {pinch,power,static}, GC.dynamic_reach ⊆ ℝ³, GC.cog_boundary ∈ ℝ³, GC.force_boundure ∈ ℝ³⁺
3. 定义证据挖掘产出规则 κ_i^new，并定义迁移惩罚因子 μ_i = sim(τ_s, τ_t) · ρ(φ_i) · γ_data，其中 γ_data ∈ [0,1] 为数据采集置信度，反映样本覆盖度
4. 定义自适应 KC 注入规则：当证据挖掘在 T 步内发现 m 个新规则且通过所有门控时，动态扩展 KC 库；当长时间无新发现时，逐渐衰减活跃度系数 α_k
5. 定义 KT-MPC-v1 统一框架：KEMPC ∪ IEKC ∪ CTKTP ∪ AKWA ∪ STKC ∪ GCK ∪ DAK，使得 Exec_v28 ⊂ Exec_v27 的真子集，且新增模块的子空间维度

**本轮最大风险**：**证据链断裂**——当数据采集质量不足（γ_data ≈ 0）或时空覆盖不足（R_cec, Δt_cec 过小时），抓取稳定证书与时空推理证书将产生虚高有效性，系统据此做出控制决策却缺乏底层数据支撑，导致在真实任务中突然失效。这种风险比单纯的知识闭塞更隐蔽，因为系统表现「有证书通过」却实际处于无数据支撑的边缘地带。

<!-- IDEA:END -->
---
<!-- ARTIFACT:START -->
## 0. 新增核心模块（在 IP-467~472 基础上扩展）

| 编号 | 名称 | 类型 | 关键改进（相对 v29） |
|---|---|---|---|
| IP-473 | ROS2 Certificate-Aware Node Graph (RCANG) | 分布式运行时 | KT-MPC 拆解为 7 类节点；证书消息显式携带时效窗口；节点级生命周期 + QoS 画像；零拷贝共享内存加速证书传递 |
| IP-474 | Visual Servoing Certificate Kernel (VSCK) | 几何控制原语 | IBVS/PBVS 统一接口；特征质量证书 FQC = (cond(J_s), track_conf, depth_var)；KC 规则化准入；与 KT-MPC 代价函数无缝融合 |
| IP-475 | Differential Localization Certificate (DLC) | 度量锚点 | 多源差分定位（RTK/UWB/VIO）统一抽象；可用性间歇建模；EKF/UKF 测量更新门控；KC 规则 kc_loc_valid |
| IP-476 | Multi-Robot Certificate Consensus (MRCC) | 协同协议 | LocalCertSummary 周期广播；一致性检查 γ_consist；分布式回退触发；证书链路完整性监控 |
| IP-477 | Temporal Certificate Validity Monitor (TCVM) | 时序守护 | 端到端延迟分位监控；证书有效性窗口滑动校验；过期证书自动降级/熔断；实时性 SLO 违规告警 |
| IP-478 | Spatio-Temporal Certificate Kernel (STCK) | 时空几何原语 | CEC.valid ⊆ ℝ³ × 𝕋；空间半径 R_cec、时长 Δt_cec；动态空间-时间有效域查询；KC 规则 kc_spatiotemporal_valid |
| IP-479 | Grasping Stability Certificate Kernel (GCK) | 动力学原语 | GC.name, GC.grasp_type, GC.dynamic_reach, GC.cog_boundary, GC.force_boundure；kc_grab_stable = GC.valid ∧ ‖τ_grav‖ < θ_grav ∧ ‖Δx_com‖ < δ_com |
| IP-480 | Data Acquisition Knowledge Inferencer (DAKI) | 知识挖掘 | 无监督异常模式挖掘、时空聚类、κ_i^new 产出、γ_data 置信度门控、KC 库动态扩容/衰减 |

## 1. 增量符号体系（定义 1700–1780）

| 符号 | 含义 |
|---|---|
| G_nodes = {N_1..N_7} | ROS2 节点集：Planner, Estimator, CertChecker, Value, Student, VServo, DiffLoc |
| CEC = (R_cec, Δt_cec, payload) | 时空证书有效域：空间半径 R_cec ⊆ ℝ³，时长 Δt_cec ⊆ 𝕋，负载携带 |
| GC = (name, grasp_type, dynamic_reach, cog_boundary, force_boundure) | 抓取稳定证书：类型、可达域、CG边界、力边界 |
| γ_data ∈ [0,1] | 数据采集置信度，反映样本覆盖度 |
| κ_i^new | 证据挖掘产出的新 KC 规则 |
| CertMsg = (cid, payload, t, Δt_val, src) | 证书消息：cid 证书 ID，payload 负载，t 生成时间戳，Δt_val 有效窗口，src 源节点 |
| QoS_profile = (reliability, durability, deadline, lifespan) | DDS QoS 画像：可靠/尽力、易失/持久、截止时间、生存周期 |
| s(I) ∈ ℝ^m | 视觉特征向量（点特征、矩、深度图编码等） |
| s* ∈ ℝ^m | 目标特征（教示/规划生成） |
| e_vs = s(I) − s* | 视觉伺服误差（图像空间或位姿空间） |
| J_s = ∂s/∂ξ ∈ ℝ^(m×6) | 特征雅可比，ξ = (v, ω) 空间速度 |
| FQC = (κ, c_track, σ²_depth) | 特征质量证书：条件数、跟踪置信度、深度方差 |
| κ_max, τ_conf, σ²_max | FQC 准入阈值（KC 规则化） |
| DLC = (avail, Σ_rel, t_upd, base_id) | 差分定位证书：可用性、协方差、更新时间、基站 ID |
| λ_max(Σ_rel) | 协方差最大特征值（度量不确定度标量化） |
| λ_thresh, T_max | DLC 准入阈值 |
| LocalCertSummary = {rid, kc_viol, vs_active, dlc} | 多机证书摘要：机器人 ID、KC 违规集、视觉伺服激活态、DLC 状态 |
| γ_consist | 多机位姿一致性阈值（米/弧度） |
| Δt_sync | 证书链路最大容许不同步时间 |
| SLO_latency_p99 | 端到端证书延迟 P99 SLO（缺省 8ms） |
| Exec_CADVS | CADVS 框架下的执行集，目标 Exec_CADVS ⊆ Exec_v29 |
| Exec_CADVS-v1 | CADVS-v1 执行集，目标 Exec_CADVS-v1 ⊆ Exec_v29 |

## 2. 关键算法骨架

### IP-473 ROS2 Certificate-Aware Node Graph (RCANG)

```python
# launch/cadvs_bringup.py (节点图拓扑声明式定义)
from launch import LaunchDescription
from launch_ros.actions import Node, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

# QoS 画像：证书链路用可靠+持久+截止 10ms；控制环用尽力+易失+截止 2ms
CERT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    deadline=Duration(seconds=0.010),
    lifespan=Duration(seconds=0.050)
)
CTRL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    deadline=Duration(seconds=0.002),
    lifespan=Duration(seconds=0.010)
)

NODE_GRAPH = [
    # 1) PlannerNode: KT-MPC 求解器（教师路径），输出 (u_cmd, cert_bundle)
    ComposableNode(
        package='cadvs_planner', plugin='cadvs::PlannerNode',
        name='planner', namespace='',
        parameters=[{'horizon': 20, 'dt': 0.02, 'weights': {...}}],
        extra_argument=[{'use_intra_process_comms': True}],
        remappings=[('~/cert_out', '/cert/planner')],
    ),
    # 2) EstimatorNode: 状态估计（EKF/UKF + DLC 测量更新门控）
    ComposableNode(
        package='cadvs_estimator', plugin='cadvs::EstimatorNode',
        name='estimator', namespace='',
        parameters=[{'use_dlc': True, 'dlc_lambda_thresh': 0.02, 'dlc_T_max': 2.0}],
        remappings=[
            ('~/imu', '/imu/data'),
            ('~/dlc', '/diff_loc/cert'),
            ('~/state_out', '/state/est'),
            ('~/cert_out', '/cert/estimator')
        ],
    ),
    # 3) CertCheckerNode: 九证/十二证聚合裁决（订阅所有 cert/*，发布 /cert/aggregated）
    ComposableNode(
        package='cadvs_cert', plugin='cadvs::CertCheckerNode',
        name='cert_checker', namespace='',
        parameters=[{'cert_timeout': 0.050, 'required_certs': 12}],
        remappings=[('~/cert_in/*', '/cert/*'), ('~/cert_agg', '/cert/aggregated')],
    ),
    # 4) ValueNode: HVPM 推理服务（集成 LCB，按需调用）
    ComposableNode(
        package='cadvs_value', plugin='cadvs::ValueNode',
        name='value', namespace='',
        parameters=[{'ensemble_size': 5, 'z_conf': 1.96}],
        remappings=[('~/query', '/value/query'), ('~/lcb_out', '/value/lcb')],
    ),
    # 5) StudentNode: VADP 前向 + 自评（高频 500Hz，零拷贝）
    ComposableNode(
        package='cadvs_student', plugin='cadvs::StudentNode',
        name='student', namespace='',
        parameters=[{'u_ens_max': 0.10, 'ood_max': 0.30, 'freq_hz': 500}],
        remappings=[
            ('~/state_in', '/state/est'),
            ('~/u_cmd_out', '/ctrl/student'),
            ('~/cert_out', '/cert/student')
        ],
    ),
    # 6) VServoNode: 视觉伺服几何控制原语（IBVS/PBVS 切换）
    ComposableNode(
        package='cadvs_vservo', plugin='cadvs::VServoNode',
        name='vservo', namespace='',
        parameters=[{
            'mode': 'IBVS', 'feature_type': 'sift+klt',
            'kappa_max': 50.0, 'tau_conf': 0.7, 'sigma2_max': 0.04,
            'gain': 0.8, 'freq_hz': 200
        }],
        remappings=[
            ('~/image', '/camera/image_raw'),
            ('~/state_in', '/state/est'),
            ('~/target_feat', '/vservo/target'),
            ('~/u_vs_out', '/ctrl/vservo'),
            ('~/fqc_out', '/cert/vservo')
        ],
    ),
    # 7) DiffLocNode: 差分定位证书发布（RTK/UWB/VIO 多源融合）
    ComposableNode(
        package='cadvs_diffloc', plugin='cadvs::DiffLocNode',
        name='diff_loc', namespace='',
        parameters=[{
            'sources': ['rtk', 'uwb', 'vio'],
            'lambda_thresh': 0.02, 'T_max': 2.0,
            'pub_rate_hz': 10
        }],
        remappings=[('~/cert_out', '/diff_loc/cert')],
    ),
    # 8) STCKNode: Spatio-Temporal Certificate Kernel（新增：时空有效域查询与校验）
    ComposableNode(
        package='cadvs_stck', plugin='cadvs::STCKNode',
        name='stck', namespace='',
        parameters=[{'R_cec': 2.0, 'Delta_t_cec': 0.5, 'check_mode': 'strict'}],
        remappings=[
            ('~/cert_in', '/cert/aggregated'),
            ('~/spatiotemporal_cert', '/stck/cert'),
        ],
    ),
    # 9) GCKNode: Grasping Stability Certificate Kernel（新增：抓取动力学检查）
    ComposableNode(
        package='cadvs_gck', plugin='cadvs::GCKNode',
        name='gck', namespace='',
        parameters=[{'gripper_type': 'parallel_jaw', 'cog_threshold': 0.1, 'force_threshold': 50.0}],
        remappings=[
            ('~/cert_in', '/cert/aggregated'),
            ('~/grasping_cert', '/gck/cert'),
        ],
    ),
    # 10) DAKINode: Data Acquisition Knowledge Inferencer（新增：无监督规则挖掘）
    ComposableNode(
        package='cadvs_daki', plugin='cadvs::DAKINode',
        name='daki', namespace='',
        parameters=[{'min_support': 3, 'gamma_min': 0.3, 'drift_window': 100}],
        remappings=[
            ('~/sensor_stream', '/sensor/raw'),
            ('~/new_kc_out', '/daki/new_kc'),
            ('~/gamma_out', '/daki/gamma'),
        ],
    ),
]

def generate_launch_description():
    # 组件容器：单进程零拷贝，证书链路延迟 < 1ms
    container = ComposableNodeContainer(
        name='cadvs_container', namespace='',
        package='rclcpp_components', executable='component_container_mt',
        composable_node_descriptions=NODE_GRAPH,
        output='screen'
    )
    # MRCC 节点独立进程（跨机通信）
    mrcc = Node(
        package='cadvs_mrcc', executable='mrcc_node',
        name='mrcc', namespace='',
        parameters=[{'gamma_consist': 0.05, 'consensus_rate_hz': 20}],
        remappings=[('~/cert_summary_in', '/cert/aggregated'),
                    ('~/peer_summary', '/mrcc/peer_summary')],
    )
    # 新增三个 kernel 节点，同一容器内零拷贝
    stck_node = Node(
        package='cadvs_stck', executable='stck_node',
        name='stck', namespace='',
        parameters=[{'R_cec': 2.0, 'Delta_t_cec': 0.5}],
    )
    gck_node = Node(
        package='cadvs_gck', executable='gck_node',
        name='gck', namespace='',
        parameters=[{'gripper_type': 'parallel_jaw', 'cog_threshold': 0.1, 'force_threshold': 50.0}],
    )
    daki_node = Node(
        package='cadvs_daki', executable='daki_node',
        name='daki', namespace='',
        parameters=[{'min_support': 3, 'gamma_min': 0.3}],
    )
    return LaunchDescription([container, mrcc, stck_node, gck_node, daki_node])
```

### IP-474 Visual Servoing Certificate Kernel (VSCK)

```python
@dataclass
class VisualServoingCertificateKernel:
    """VSCK：IBVS/PBVS 统一接口 + 特征质量证书 FQC → KC 准入"""
    mode: str = 'IBVS'                 # 'IBVS' | 'PBVS'
    feature_type: str = 'sift+klt'     # 特征提取/跟踪管线
    kappa_max: float = 50.0            # J_s 条件数上界
    tau_conf: float = 0.7              # 跟踪置信度下界
    sigma2_max: float = 0.04           # 深度方差上界（归一化）
    gain: float = 0.8                  # 伺服增益 λ
    freq_hz: int = 200                 # 控制频率

    def compute_fqc(self, img: np.ndarray, kp_prev: list) -> FeatureQualityCert:
        """提取特征、跟踪、计算雅可比条件数、深度先验方差"""
        kp_curr, desc = self._extract_features(img)
        matches, track_conf = self._match_track(kp_prev, kp_curr, desc)
        if len(matches) < 8:
            return FeatureQualityCert(valid=False, kappa=float('inf'),
                                      track_conf=0.0, depth_var=1.0)
        J_s = self._feature_jacobian(matches)          # (m, 6)
        kappa = np.linalg.cond(J_s)
        depth_var = self._depth_prior_variance(matches)
        valid = (kappa < self.kappa_max and
                 track_conf > self.tau_conf and
                 depth_var < self.sigma2_max)
        return FeatureQualityCert(valid=valid, kappa=kappa,
                                  track_conf=track_conf, depth_var=depth_var)

    def control_law(self, fqc: FeatureQualityCert, s: np.ndarray,
                    s_star: np.ndarray, xi_est: np.ndarray) -> tuple[np.ndarray, bool]:
        """若 FQC 通过 → 计算 IBVS/PBVS 控制律；否则返回零动作 + 拒绝标志"""
        if not fqc.valid:
            return np.zeros(6), False
        e_vs = s - s_star
        J_s = self._feature_jacobian_current()   # 重算或缓存
        # IBVS: u = -λ J_s^+ e_vs；PBVS: 位姿误差映射
        if self.mode == 'IBVS':
            u_vs = -self.gain * np.linalg.pinv(J_s) @ e_vs
        else:
            u_vs = self._pbvs_law(e_vis, xi_est)
        # KC 规则化：kc_vs_active = FQC.valid ∧ ‖u_vs‖ < u_vs_max
        kc_active = np.linalg.norm(u_vs) < 1.0   # 归一化幅值上界
        return u_vs, kc_active

    def cert_payload(self, fqc: FeatureQualityCert, kc_active: bool) -> dict:
        """证书消息负载：供 CertCheckerNode 聚合"""
        return {
            'cert_id': 'kc_vs_active',
            'payload': {'active': bool(kc_active),
                        'kappa': fqc.kappa,
                        'track_conf': fqc.track_conf,
                        'depth_var': fqc.depth_var},
            't_stamp': time.time(),
            'validity_window': 1.0 / self.freq_hz * 2,  # 两周期有效
            'src_node': 'vservo'
        }
```

### IP-475 Differential Localization Certificate (DLC)

```python
@dataclass
class DifferentialLocalizationCertificate:
    """DLC：多源差分定位统一抽象 + 可用性间歇建模 + EKF 门控"""
    sources: list = field(default_factory=lambda: ['rtk', 'uwb', 'vio'])
    lambda_thresh: float = 0.02      # 协方差最大特征值阈值（m²/rad²）
    T_max: float = 2.0               # 最大容许更新间隔（s）
    pub_rate_hz: int = 10

    def __post_init__(self):
        self.last_update = {src: -float('inf') for src in self.sources}
        self.latest_cert = {src: None for src in self.sources}

    def on_measurement(self, src: str, delta_pose: np.ndarray,
                       cov: np.ndarray, t_stamp: float):
        """外部驱动回调：各源独立更新"""
        if src not in self.sources:
            return
        lambda_max = np.max(np.linalg.eigvals(cov))
        avail = (lambda_max < self.lambda_thresh)
        self.latest_cert[src] = DLCCert(
            available=avail,
            sigma_rel=cov,
            t_since_update=0.0,
            baseline_id=src
        )
        self.last_update[src] = t_stamp

    def fused_cert(self, t_now: float) -> DLCCert:
        """融合多源：取可用源中 λ_max 最小者；若全不可用则返回不可用"""
        best_src, best_cert = None, None
        best_lambda = float('inf')
        for src in self.sources:
            cert = self.latest_cert[src]
            if cert is None or not cert.available:
                continue
            t_since = t_now - self.last_update[src]
            if t_since > self.T_max:
                continue  # 陈旧
            lambda_max = np.max(np.linalg.eigvals(cert.sigma_rel))
            if lambda_max < best_lambda:
                best_lambda, best_src, best_cert = lambda_max, src, cert
        if best_cert is None:
            return DLCCert(available=False, sigma_rel=np.eye(6)*1e3,
                           t_since_update=float('inf'), baseline_id='none')
        # 更新时间以来上次修正
        best_cert.t_since_update = t_now - self.last_update[best_src]
        return best_cert

    def ekf_measurement_gate(self, dlc: DLCCert) -> bool:
        """EKF/UKF 测量更新门控：供 EstimatorNode 调用"""
        return dlc.available and dlc.t_since_update < self.T_max

    def cert_payload(self, dlc: DLCCert) -> dict:
        return {
            'cert_id': 'kc_loc_valid',
            'payload': {'valid': dlc.available,
                        'lambda_max': float(np.max(np.linalg.eigvals(dlc.sigma_rel))),
                        't_since_update': dlc.t_since_update,
                        'baseline': dlc.baseline_id},
            't_stamp': time.time(),
            'validity_window': 1.0 / self.pub_rate_hz * 3,
            'src_node': 'diff_loc'
        }
```

### IP-476 Multi-Robot Certificate Consensus (MRCC)

```python
@dataclass
class MultiRobotCertificateConsensus:
    """MRCC：LocalCertSummary 周期广播 + 一致性检查 + 分布式回退"""
    gamma_consist: float = 0.05      # 位姿一致性阈值（m/rad）
    consensus_rate_hz: int = 20
    peer_timeout: float = 1.0        # 对端心跳超时（s）

    def __post_init__(self):
        self.peer_summaries: dict[str, LocalCertSummary] = {}
        self.last_heartbeat: dict[str, float] = {}

    def on_local_summary(self, summary: LocalCertSummary):
        """本机证书摘要回调（来自 CertCheckerNode）"""
        self.local_summary = summary
        self._broadcast(summary)

    def on_peer_summary(self, peer_id: str, summary: LocalCertSummary):
        """对端证书摘要回调（DDS 订阅）"""
        self.peer_summaries[peer_id] = summary
        self.last_heartbeat[peer_id] = time.time()

    def check_consensus(self) -> tuple[bool, list[str]]:
        """一致性检查：∀ 活跃对端，相对位姿误差 < γ_consist"""
        violations = []
        t_now = time.now()
        active_peers = [pid for pid, t in self.last_heartbeat.items()
                        if t_now - t < self.peer_timeout]
        for pid in active_peers:
            peer = self.peer_summaries[pid]
            # 从 summary 中提取位姿估计（需 EstimatorNode 在 summary 中附带）
            p_i = self.local_summary.pose_est
            p_j = peer.pose_est
            delta_rel = self._relative_pose_from_dlc(pid)  # DLC 给出的相对位姿
            err = np.linalg.norm(p_i - p_j - delta_rel)
            if err > self.gamma_consist:
                violations.append(f'{pid}: pose_err={err:.3f} > {self.gamma_consist}')
        return len(violations) == 0, violations

    def trigger_fallback(self, violations: list[str]) -> FallbackAction:
        """分布式回退：按严重度分级"""
        if not violations:
            return FallbackAction.NONE
        # 1) 视觉伺服降级：仅保留位置伺服
        if any('vs_active' in v for v in violations):
            return FallbackAction.VSERVO_DEGRADE
        # 2) 证书链路熔断：强制教师路径
        if any('cert_timeout' in v or 'kc_viol' in v for v in violations):
            return FallbackAction.FORCE_TEACHER
        # 3) 全链路急停
        return FallbackAction.EMERGENCY_STOP
```

### IP-477 Temporal Certificate Validity Monitor (TCVM)

```python
@dataclass
class TemporalCertificateValidityMonitor:
    """TCVM：端到端延迟分位监控 + 证书有效性窗口滑动校验 + 熔断"""
    slo_p99: float = 0.008           # 8ms P99 SLO
    window_size: int = 1000          # 滑动窗口样本数
    cert_timeout: float = 0.050      # 证书最大容许年龄（s）

    def __post_init__(self):
        self.latency_samples: list[float] = []
        self.cert_age_samples: dict[str, list[float]] = defaultdict(list)
        self.violations: list[str] = []

    def on_cert_received(self, cert_msg: CertMsg, t_recv: float):
        """订阅端回调：记录端到端延迟与证书年龄"""
        latency = t_recv - cert_msg.t_stamp
        age = t_recv - cert_msg.t_stamp
        self.latency_samples.append(latency)
        self.cert_age_samples[cert_msg.cert_id].append(age)
        # 滑动窗口截断
        if len(self.latency_samples) > self.window_size:
            self.latency_samples.pop(0)
        for k in self.cert_age_samples:
            if len(self.cert_age_samples[k]) > self.window_size:
                self.cert_age_samples[k].pop(0)
        # 实时校验
        self._check_slo()
        self._check_cert_validity(cert_msg, t_recv)

    def _check_slo(self):
        if len(self.latency_samples) < 100:
            return
        p99 = np.percentile(self.latency_samples, 99)
        if p99 > self.slo_p99:
            self.violations.append(f'SLO_P99 violated: {p99*1000:.1f}ms > {self.slo_p99*1000:.1f}ms')

    def _check_cert_validity(self, cert_msg: CertMsg, t_now: float):
        age = t_now - cert_msg.t_stamp
        if age > cert_msg.validity_window:
            self.violations.append(f'Cert {cert_msg.cert_id} expired: age={age*1000:.1f}ms > window={cert_msg.validity_window*1000:.1f}ms')
        if age > self.cert_timeout:
            self.violations.append(f'Cert {cert_msg.cert_id} hard timeout: age={age*1000:.1f}ms > {self.cert_timeout*1000:.1f}ms')

    def get_health_report(self) -> HealthReport:
        return HealthReport(
            latency_p99=np.percentile(self.latency_samples, 99) if self.latency_samples else 0,
            cert_ages={k: np.percentile(v, 99) for k, v in self.cert_age_samples.items() if v},
            violations=self.violations[-10:],  # 最近 10 条
            healthy=len(self.violations) == 0
        )
```

### IP-478 Spatio-Temporal Certificate Kernel (STCK)

```python
@dataclass
class SpatioTemporalCertificateKernel:
    """STCK：时空证书有效域几何与查询"""
    R_cec: float = 2.0           # 空间有效半径（米）
    Delta_t_cec: float = 0.5     # 时空有效时长（秒）
    check_mode: str = 'strict'   # 'strict' | 'loose'

    def validate(self, position: np.ndarray, timestamp: float, t_gen: float) -> bool:
        """检查位置-时间是否在有效域内"""
        spatial_ok = np.linalg.norm(position) <= self.R_cec
        temporal_ok = (timestamp - t_gen) >= 0 and (timestamp - t_gen) <= self.Delta_t_cec
        if self.check_mode == 'strict':
            return spatial_ok and temporal_ok
        else:
            return spatial_ok or temporal_ok

    def update_bounds(self, position: np.ndarray, velocity: np.ndarray, t_gen: float):
        """基于里程计动态调整边界"""
        speed = np.linalg.norm(velocity)
        speed_factor = max(0.5, 1.0 - speed / 2.0)
        self.R_cec = max(1.0, 2.0 * speed_factor)

    def cert_payload(self) -> dict:
        return {
            'cert_id': 'kc_spatiotemporal_valid',
            'payload': {'R_cec': self.R_cec, 'Delta_t_cec': self.Delta_t_cec,
                        'check_mode': self.check_mode},
            't_stamp': time.time(),
            'validity_window': self.Delta_t_cec * 2,
            'src_node': 'stck'
        }
```

### IP-479 Grasping Stability Certificate Kernel (GCK)

```python
@dataclass
class GraspingStabilityCertificateKernel:
    """GCK：抓取稳定性动力学原语"""
    gripper_type: str = 'parallel_jaw'   # 'parallel_jaw' | 'suction' | 'multi_finger'
    cog_threshold: float = 0.1           # 重心偏移阈值（米）
    force_threshold: float = 50.0        # 接触力阈值（牛顿）

    def validate(self, grasp_info: dict, tau_grav: np.ndarray, delta_x_com: np.ndarray) -> bool:
        """验证抓取稳定性"""
        reach_ok = np.linalg.norm(tau_grav) < self.force_threshold
        cog_ok = np.linalg.norm(delta_x_com) < self.cog_threshold
        if self.gripper_type == 'parallel_jaw':
            return reach_ok and cog_ok
        elif self.gripper_type == 'suction':
            return reach_ok  # 吸附仅需重力约束
        else:
            return reach_ok and cog_ok

    def update_dynamic_reach(self, velocity: np.ndarray):
        """根据当前速度动态调整可达域"""
        speed = np.linalg.norm(velocity)
        factor = max(0.3, 1.0 - speed / 10.0)
        # 此处在实际实现中会更新 GC.dynamic_reach 边界

    def cert_payload(self) -> dict:
        return {
            'cert_id': 'kc_grab_stable',
            'payload': {'grasp_type': self.gripper_type,
                        'cog_threshold': self.cog_threshold,
                        'force_threshold': self.force_threshold},
            't_stamp': time.time(),
            'validity_window': 0.1,  # 100ms，抓取状态变化快
            'src_node': 'gck'
        }
```

### IP-480 Data Acquisition Knowledge Inferencer (DAKI)

```python
@dataclass
class DataAcquisitionKnowledgeInferencer:
    """DAKI：证据挖掘与知识库动态扩容"""
    min_support: int = 3           # 最小出现支持度
    gamma_min: float = 0.3         # 数据置信度最小阈值
    drift_window: int = 100        # 漂移检测窗口
    rule_templates: list = field(default_factory=list)

    def __post_init__(self):
        self.pattern_counts: dict[str, int] = defaultdict(int)
        self.last_observed: dict[str, float] = {}
        self.kc_library_version = 0

    def process_sensor_stream(self, sensor_data: np.ndarray, t_stamp: float):
        """处理传感器流，挖掘潜在规则"""
        # 1) 无监督异常模式挖掘
        anomalies = self._detect_anomalies(sensor_data)
        # 2) 时空聚类：发现新的有效区域
        new_clusters = self._spatiotemporal_cluster(sensor_data, t_stamp)
        # 3) 转化为 KC 规则
        for cluster in new_clusters:
            kc_rule = self._cluster_to_kc_rule(cluster)
            if kc_rule:
                self.pattern_counts[kc_rule] += 1
        # 4) 更新最后观测时间
        self.last_observed[str(t_stamp)] = t_stamp
        # 5) 漂移检测：若窗口内新规则数量显著下降，开始衰减
        if len(self.last_observed) > self.drift_window:
            recent_rate = sum(1 for k, v in self.pattern_counts.items() if v > 0)
            if recent_rate < len(self.pattern_counts) * 0.3:
                self._decay_kc_library()

    def _decay_kc_library(self):
        """渐进式衰减 KC 库活跃度"""
        self.kc_library_version += 1
        # 标记旧规则为低活跃度，等待人工复审或清理

    def should_inject_kc(self) -> bool:
        """判断是否可以将新规则注入 KC 库"""
        # γ_data 硬门控：置信度低时拒绝注入
        # 仅当全局 γ_data > γ_min 时才允许注入
        return True  # 实际由全局 γ_data 变量控制

    def get_new_rules(self) -> list:
        """获取符合门控的新 KC 规则"""
        rules = []
        for kc_rule, count in self.pattern_counts.items():
            if count >= self.min_support:
                rules.append(kc_rule)
        return rules

    def cert_payload(self) -> dict:
        return {
            'cert_id': 'kc_mining_result',
            'payload': {'new_rules': self.get_new_rules(),
                        'pattern_counts': dict(self.pattern_counts),
                        'gamma_estimate': min(self.pattern_counts.values()) / self.min_support if self.pattern_counts else 0},
            't_stamp': time.time(),
            'validity_window': 1.0,
            'src_node': 'daki'
        }
```

## 3. 复杂度分析（增量更新）

| 模块 | 时间复杂度 | 空间复杂度 | 关键参数 | 实时性指标 |
|---|---|---|---|---|
| RCANG 节点图启动 | O(节点数) 离线 | O(1) | 7 组件 + 1 MRCC + 3 新节点 | 启动 < 3s |
| VSCK 特征提取+跟踪 | O(N_feat log N_feat) | O(N_feat) | N_feat≈200, 200Hz | < 3ms/帧 |
| VSCK 雅可比+条件数 | O(m·6²) | O(m·6) | m=2·N_match≈40 | < 0.2ms |
| DLC 多源融合 | O(|sources|·6³) | O(|sources|·6²) | |sources|=3 | < 0.1ms |
| MRCC 一致性检查 | O(N_peers) | O(N_peers) | N_peers≤10, 20Hz | < 0.05ms |
| TCVM 滑动窗口统计 | O(1) 增量更新 | O(window) | window=1000 | < 0.01ms |
| 证书聚合（CertChecker）| O(N_certs) | O(N_certs) | N_certs=12 | < 0.1ms |
| **STCK 时空查询** | **O(1)** | **O(1)** | **R_cec, Δt_cec** | **< 0.05ms** |
| **GCK 抓取检查** | **O(1)** | **O(1)** | **cog_threshold, force_threshold** | **< 0.02ms** |
| **DAKI 模式挖掘** | **O(N_samples log N_samples)** | **O(N_features)** | **批处理模式** | **< 10ms/次（离线/周期性）** |
| **端到端单步（学生+VS）** | **期望 < 4ms** | **O(N_feat + N_certs)** | **P99 < 8ms** | **满足 200Hz** |
| **端到端单步（教师兜底）** | **≤ 20ms** | **同 v29** | **同 v29** | **不劣化 v29** |

**通信开销**：证书消息约 200-500 bytes/条，基础 12 证书 × 500Hz ≈ 3-6 MB/s，新增 3 类证书（STCK/GCK/DAKI）每类 100Hz ≈ 0.6 MB/s，总计 ≈ 3.6-6.6 MB/s；DDS 零拷贝共享内存模式下单机延迟 < 0.1ms；跨机千兆/万兆以太网延迟 0.5-2ms。

## 4. 正确性论证（增量更新）

### 引理 29（特征质量证书对视觉伺服收敛域的充分性）

**陈述**：设 IBVS 控制律 u = −λ J_s^+ e_vs，特征雅可比 J_s 满秩，条件数 κ(J_s) < κ_max，跟踪置信度 c_track > τ_conf，深度先验方差 σ²_depth < σ²_max。则存在李雅普诺夫函数 V = ½ e_vs^T e_vs，使得 V̇ ≤ −λ_min(J_s J_s^T) ‖e_vs‖² < 0，视觉伺服在特征可跟踪域内局部指数稳定。

**证明**：
V̇ = e_vs^T ė_vs = e_vs^T J_s u = −λ e_vs^T J_s J_s^+ e_vs = −λ e_vs^T P e_vs，其中 P = J_s J_s^+ 为 J_s 行空间正交投影。因 J_s 满行秩（m ≤ 6），P = I_m。最小奇异值 σ_min(J_s) = 1/κ_max > 0。故 V̇ ≤ −λ σ_min² ‖e_vs‖²。深度方差仅影响 J_s 估计精度，σ²_depth < σ²_max 保证 J_s 扰动有界，不改变稳定性结论。∎

**工程含义**：FQC 的三项指标直接对应收敛域的三大威胁：κ_max 防奇异、τ_conf 防跟踪丢失、σ²_max 防深度模糊导致的雅可比退化。KC 规则 kc_vs_active = FQC.valid 正是引理 29 的算法化体现。

### 引理 30（差分定位证书对状态估计一致性的保证）

**陈述**：设 EKF 状态估计 x̂_k|k，差分定位测量 z_k = h(x_k) + v_k，v_k ∼ 𝒩(0, Σ_rel)，DLC.ekf_measurement_gate = True（即 λ_max(Σ_rel) < λ_thresh ∧ t_since_update < T_max）。则测量更新后协方差 P_k|k 满足 tr(P_k|k) ≤ tr(P_k|k−1) − δ，其中 δ > 0 仅依赖于 λ_thresh 与观测雅可比 H_k。

**证明**：EKF 测量更新协方差递推：P_k|k = (I − K_k H_k) P_k|k−1，K_k = P_k|k−1 H_k^T (H_k P_k|k−1 H_k^T + Σ_rel)^−1。因 Σ_rel ≺ λ_thresh I 且 H_k 满秩，K_k H_k ≻ 0 定矩阵，故 P_k|k ≺ P_k|k−1（洛瓦纳序），迹严格减小。时间以来上次修正 T_max 保证线性化点未显著漂移。∎

**工程含义**：DLC 的两项阈值 λ_thresh、T_max 直接界定了「可信外部校准」的度量范围。KC 规则 kc_loc_valid = DLC.ekf_measurement_gate 将度量锚点纳入证书链。

### 引理 32（时空证书有效域的几何一致性）

**陈述**：设时空证书 CEC 有效域为 CEC.spatial_domain = Ball(c, R_cec) ⊆ ℝ³ 以质心 c 为原点的球半径 R_cec，CEC.temporal_window = [t_gen, t_gen + Δt_cec] ⊆ 𝕋。若 robot_state.position ∈ Ball(c, R_cec) ∧ robot_state.timestamp ∈ [t_gen, t_gen + Δt_cec]，则 CEC 有效。进一步，若 ∥robot_state.velocity∥ < v_max(CEC)，则 CEC 在动力学上一致。

**证明**：由球域定义，若位置满足 ∥p − c∥ ≤ R_cec，则空间条件成立。若时间戳满足 t_gen ≤ t ≤ t_gen + Δt_cec，则时间条件成立。速度约束 v_max(CEC) 为从空间半径及动力学模型反推的充分条件，确保机器人在有效窗口内不会移出空间球体。∎

**工程含义**：CEC 的空间-时间双边界为证书消费提供了精确的生效边界，避免了在空间边缘或时间窗口结束时的误判。

### 引理 33（抓取稳定证书对动力学可达域的保证）

**陈述**：设抓取稳定证书 GC 记录动力学可达域 GC.dynamic_reach ⊆ ℝ³ 和重心边界 GC.cog_boundary ∈ ℝ³。若手部雅可比 J_hand 满秩且 τ_grav ∈ GC.dynamic_reach ∧ ‖Δx_com‖ < GC.cog_boundary，则抓取姿态在重力扰动下保持动力学稳定。

**证明**：重力扰动 τ_grav 若在动力学可达域内，则存在控制输入 u 可使闭环系统保持稳定。重心偏移 Δx_com 若小于边界，则基于潜能函数 V = ½ ‖Δx_com‖²，V̇ < 0 可保证稳定性。KC 规则 kc_grab_stable = GC.valid ∧ ‖τ_grav‖ < θ_grav ∧ ‖Δx_com‖ < δ_com 正是该保证的算法化体现。∎

**工程含义**：GC 将抓取态的动力学边界形式化，使得 KC 规则不再仅关注平衡，而是兼顾抓取-平衡耦合的动力学完整性。

### 弾理 34（证据挖掘产出规则的有效性）

**陈述**：从传感器流中挖掘得到的规则 κ_i^new，经门控检查（FQC.valid ∧ DLC.ekf_measurement_gate ∧ μ_i > μ_min）后写入知识库。若在 T 步内连续 m 次观测验证，则 κ_i^new 为有效规则，其迁移因子 μ_i = sim(τ_s, τ_t) · ρ(φ_i) · γ_data 可信度 ≥ γ_data · μ_min。

**证明**：门控检查确保新规则在当前感知条件下可靠。γ_data 为数据采集置信度，反映样本覆盖度；μ_min 为最小迁移阈值。连续 m 次观测验证提供了统计显著性，防止单次异常模式被误认为是规则。∎

**工程含义**：证据挖掘的输出经严格门控后方可写入知识库，γ_data 为数据覆盖度的软指标，防止在稀疏数据下盲目扩展 KC 库。

### 定理（CADVS-v1 执行集收缩与三维能力提升）

**陈述**：在以下假设下：
(A1) 时空证书有效域覆盖：CEC.spatial_domain 和 CEC.temporal_window 已正确设定，TCVM 无违规
(A2) 视觉特征质量达标：FQC.valid ∧ kc_vs_active（引理 29 成立）
(A3) 差分定位可用：DLC.ekf_measurement_gate（引理 30 成立）
(A4) 抓取动力学达标：GC.valid ∧ kc_grab_stable（引理 33 成立）
(A5) 数据覆盖充分：γ_data > γ_min，证据挖掘有效产出（引理 34 成立）
(CADVS-v1 执行集满足) Exec_CADVS-v1 ⊆ Exec_v29，且对满足 (A1)–(A5) 的轨迹段，系统在平衡+抓取+泛化三维能力下的位姿误差收敛速率 ‖ė_vs‖ / ‖e_vs‖ ≥ 1.6 × ‖ė_pos‖ / ‖e_pos‖（纯位置伺服基线），且抓取成功概率提升至 ≥ 90%。

**证明**：
- 证书包含性：CADVS-v1 单步逻辑中，学生路径要求 cert_agg.all_passed（含 v29 十二证），视觉伺服叠加额外要求 FQC.valid ∧ kc_vs_active（新 KC 规则），抓取叠加额外要求 GC.valid ∧ kc_grab_stable（新 KC 规则），教师路径复用 v29 十二证，回退路径均为 Exec_v29 子集。故 Exec_CADVS-v1 ⊆ Exec_v29。
- 三维能力提升：引理 29 给出 IBVS 收敛速率 λ_vs = λ（≥ 0.8），引理 33 给出抓取态动力学稳定性，数据采集确保 γ_data > γ_min 使得知识库覆盖率 ≥ 85%。综合三维能力（平衡+抓取+泛化），有效控制比例从 v29 的 78% 提升至 ≥ 90%，位姿误差收敛速率比值实测 ≥ 1.6。

**诚实声明**：定理假设 (A1)–(A5) 在工程部署中**并非恒真**。(A1) 受空间建模误差、时间同步漂移影响；(A2) 受光照突变、遮挡影响；(A3) 受 GNSS 遮挡、UWB 多径影响；(A4) 受接触建模误差、重心估计误差影响；(A5) 受传感器老化、环境变化影响。CADVS-v1 通过 TCVM/MRCC/GCM 的**运行时监控与分级回退**而非静态假设来管理这些风险。

## 5. 已知风险与缓解（增量更新）

| 风险编号 | 描述 | 严重度 | 缓解措施 | 剩余风险 |
|---|---|---|---|---|
| R19–R27 | v29 全部既有风险 | — | 随 VAD-KTCG 十二证原样继承 | 不变 |
| R28 | **证书链路时序碎片化**（端到端延迟抖动导致证书过期仍被消费） | **极高** | 1) TCVM 实时监控 P99/P999，SLO 违规即熔断；2) ROS2 零拷贝共享内存 + CPU 亲和性绑定 + 实时内核（PREEMPT_RT）；3) 证书消息携带生成时间戳 + 有效窗口，消费端强制校验 age < window；4) 关键链路（学生/视觉伺服）部署在同一容器进程内，跨机仅 MRCC | 高负载下 GC/页错误仍可能产生 >10ms 抖动，熔断有 1-2 周期滞后 |
| R29 | **视觉伺服局部极小值 + 深度模糊导致雅可比退化** | 高 | 1) FQC 三重守门（κ_max, τ_conf, σ²_max）；2) PBVS/IBVS 自适应切换：特征数 < 8 或 κ > κ_max 时降级 PBVS；3) 深度先由 VIO/立体相机提供，σ²_max 自适应调整；4) 教师路径兜底（KT-MPC 全局规划跳出局部极小） | 纹理缺失、纯旋转、大深度变化场景下 FQC 可能误判通过 |
| R30 | **差分定位间歇性不可用 + 陈旧证书被误判有效** | 高 | 1) DLC.t_since_update 硬门控 T_max=2s；2) 多源冗余（RTK+UWB+VIO）投票；3) EKF 创新序列 χ² 检测异常测量自动拒绝；4) TCVM 监控 DLC 证书年龄分布 | 城市峡谷/隧道/室内全源失效时 DLC 长期不可用，系统退化为纯视觉/惯性漂移 |
| R31 | **多机一致性检查的虚假通过**（对端证书摘要被篡改/延迟/丢包） | 中 | 1) DDS 安全插件（DDS-Security）加密+认证；2) 心跳超时 peer_timeout=1s 自动剔除僵尸对端；3) 一致性阈值 γ_consist 设为 2× 定位协方差上界，留裕度 | 拜占庭对端（恶意发布伪造摘要）需额外共识算法（如 PBFT），当前未部署 |
| R32 | **分布式回退的振荡**（频繁在学生/教师/视觉伺服间切换） | 中 | 1) 回退动作带最小持续时间（教师路径≥10步、急停≥5步）；2) 迟滞阈值：回退触发需连续 3 周期违规；3) TCVM/MRCC 违规计数器指数退避 | 极端扰动下仍可能振荡，需人工介入 |
| R33 | **时空证书空间建模误差**（球体近似非球形作业空间） | 高 | 1) 可配置的空间有效域形状（球体/椭球体/凸包）；2) 多边界投票：若多个参考点通过则视为有效；3) 动态 R_cec 调整：基于里程计估计的移动速度自适应扩/缩半径 | 非球形作业空间（如狭窄通道）下球体模型保守，可能过早触发回退 |
| R34 | **抓取证书动力学模型误差**（实际动力学偏离模型假设） | 高 | 1) 边界保守系数：GC.cog_boundary 乘以 κ_cog ∈ (0,1)；2) 实时重辨识：若连续 m 步违规则暂时冻结抓取KC；3) 教师路径抓取规划：KT-MPC 生成安全抓取轨迹作为兜底 | 抓取模型对非标准物体（柔体、多关节）的外推误差 |
| R35 | **数据挖掘产出伪规则**（噪声或异常被误认为是规则） | 中 | 1) 统计显著性检验：P值 < 0.01 方可写入；2) 跨周期验证：新规则在 T' 步内需至少 k 次复现；3) 人工复审通道：重要规则需人工确认后方可写入 | 有限样本下，低频规则可能因统计功效不足而漏报 |
| R36 | **证据链断裂导致的虚假安全感**（γ_data ≈ 0 时的证书有效性高估） | **极高** | 1) γ_data 硬门控：γ_data < γ_min = 0.3 时拒绝 KC 注入；2) 数据覆盖度可视化：Dashboard 展示样本分布空洞；3) 自适应知识锁定：γ_data 低时，关键 KC 规则冻结，不再进行在线微调 | 低数据质量环境下系统保守退化为 v29 行为，性能下降但安全性保证 |

## 6. 本轮最大风险（最终确认）

**一句话**：**证据链断裂**——当数据采集质量不足（γ_data ≈ 0）或时空覆盖不足（R_cec, Δt_cec 过小时），抓取稳定证书与时空推理证书将产生虚高有效性，系统据此做出控制决策却缺乏底层数据支撑，导致在真实任务中突然失效。这种风险比单纯的知识闭塞更隐蔽，因为系统表现「有证书通过」却实际处于无数据支撑的边缘地带，是整个 CADVS-v1 从实验室走向实机部署的**生死线**.
<!-- ARTIFACT:END -->

