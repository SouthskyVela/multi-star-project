# 空间天文小卫星群相关调度机制与算法开发

面向空间天文观测的小卫星群分布式调度与阵列合成研究原型。项目以三颗主星与可配置数量末端小卫星构成的编队为对象，研究主控选举与接管、观测任务编排、星间状态一致性、故障隔离与恢复，以及超大视场低频阵列的构型设计与点扩散函数评估。

代码代号 `multi-star-sim`，当前版本 **0.2.7**。

## 研究内容

- **调度机制**：基于租约的主控选举与任期隔离；命令携带 `epoch / plan_version / command_id`，实现幂等与前缀拒绝；续约与调度解耦，避免长任务阻塞选主。
- **观测编排**：巡天、定源、定标三类模式的状态机与切换；天文事件触发定源观测、频率分配与事件去重。
- **阵列算法**：环形、Y 形、螺旋等构型布局，远场 `uvw` 与共轭 uv 采样，dirty beam/PSF、覆盖率与旁瓣指标。
- **可靠性**：小卫星故障保持与显式恢复、主控接管、命令重放保护、分块上传与断点续传。
- **可视化**：实时面板展示编队位置、uv 覆盖、PSF、调度日志与关键指标，并支持故障注入与事件注入。

## 系统组成

| 角色 | 职责 |
|---|---|
| 主星 ×3 | 租约选主、全局计划生成、命令下发、状态持久化；同一时刻仅一个 leader 生效 |
| 小卫星 ×N（默认 9） | 变轨、采集、分块上传；独立持久卷；故障状态可保持并等待显式恢复 |
| dashboard | 查询各主星状态、定位当前 leader 并转发请求；无 leader 或任期冲突时明确返回不可用 |
| 科学计算 | 共享引擎计算可见度与 PSF；NumPy 为基线，可选 GPU 后端加速 |

## 目录结构

```text
.
├── config/                 # 运行时与仿真配置（相对路径）
├── deploy/
│   ├── docker/             # 主星、小卫星镜像定义
│   ├── k3d/                # 集群与镜像源配置
│   └── kubernetes/         # StatefulSet、Service、dashboard 清单
├── docs/                   # 面板使用说明
├── scripts/                # 环境初始化、部署、巡检与验收脚本
├── src/multi_star/         # 调度、阵列、上传与面板实现
├── tests/                  # 单元与服务测试
├── start.cmd / stop.cmd    # Windows 快捷启停
└── pyproject.toml
```

运行数据统一写入 `runtime/`（已由版本控制忽略），包含虚拟磁盘、镜像缓存、kubeconfig 与验收输出。

## 运行环境

| 组件 | 要求 |
|---|---|
| 操作系统 | Windows 11 + WSL2；脚本以 Linux 为运行环境 |
| WSL 发行版 | Ubuntu 24.04，独立发行版，避免影响其他环境 |
| 容器 | Docker Engine + Buildx |
| 编排 | k3d 5.9.0、K3s 与 kubectl 1.37.2（1 server + 3 agents） |
| Python | 3.12，NumPy 2.5.5 |
| 磁盘 | 建议预留 20 GiB 以上；虚拟磁盘与镜像缓存均位于 `runtime/` |
| 网络 | 可访问 Ubuntu 源、GitHub、容器镜像源与 PyPI；受限网络需自行配置代理 |
| GPU（可选） | 批量 PSF 可用 CUDA 环境加速；核心调度不依赖 GPU |

脚本依据自身位置推导仓库根目录，仓库可放在任意路径；也可用环境变量 `PROJECT_ROOT` 显式覆盖。

## 快速开始

以下命令均在仓库根目录执行，路径均为相对路径；Windows 侧使用 Git Bash。初始化脚本只允许在专用 Ubuntu 24.04 环境运行。

### 1. 获取代码

```bash
git clone https://github.com/SouthskyVela/multi-star-project.git
cd multi-star-project
```

### 2. 准备 WSL 基础系统

```bash
mkdir -p runtime/downloads runtime/wsl
curl --fail --location \
  https://releases.ubuntu.com/24.04.5/ubuntu-24.04.5-wsl-amd64.wsl \
  --output runtime/downloads/ubuntu-24.04.5-wsl-amd64.wsl

printf '%s  %s\n' \
  'bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e' \
  'runtime/downloads/ubuntu-24.04.5-wsl-amd64.wsl' | sha256sum -c -
```

```bash
MSYS_NO_PATHCONV=1 wsl.exe --install \
  --from-file "$(pwd -W)\\runtime\\downloads\\ubuntu-24.04.5-wsl-amd64.wsl" \
  --name multi-star-sim \
  --location "$(pwd -W)\\runtime\\wsl\\multi-star-sim" \
  --no-launch --version 2
```

### 3. 下载集群工具

```bash
curl --fail --location \
  https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64 \
  --output runtime/downloads/k3d-linux-amd64
curl --fail --location \
  https://github.com/k3d-io/k3d/releases/download/v5.9.0/checksums.txt \
  --output runtime/downloads/k3d-checksums.txt
curl --fail --location \
  https://dl.k8s.io/release/v1.37.2/bin/linux/amd64/kubectl \
  --output runtime/downloads/kubectl
curl --fail --location \
  https://dl.k8s.io/release/v1.37.2/bin/linux/amd64/kubectl.sha256 \
  --output runtime/downloads/kubectl-v1.37.2.sha256
```

### 4. 初始化容器工具链

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u root -- bash scripts/bootstrap_runtime.sh
wsl.exe --terminate multi-star-sim
```

该步骤只修改专用发行版：校验安装包哈希，安装 Docker、containerd、Buildx、k3d、kubectl，创建普通用户并配置镜像源与主机名解析。

### 5. 创建并固定集群

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/smoke_cluster.sh
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/pin_cluster_ips.sh
```

固定各节点地址，避免发行版重启后动态节点占用 server 地址。Docker 与 K3s 内层 containerd 的镜像配置相互独立，两层都需要配置。

### 6. 部署业务与面板

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/deploy_small_satellites.sh
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/deploy_main_satellites.sh
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u root -- bash scripts/install_dashboard_service.sh
```

完成后访问 `http://127.0.0.1:18082`。

## 启动与停止

Windows 下双击根目录脚本即可，脚本会按当前检出位置自动解析路径：

- `start.cmd`：恢复集群、等待业务就绪、检查面板，并保持控制台常驻；看到 `START_OK` 后再打开面板。
- `stop.cmd`：停止面板转发并终止专用发行版；不删除镜像、持久卷、虚拟磁盘或历史结果。

等价的手工方式：

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/start_all.sh
MSYS_NO_PATHCONV=1 wsl.exe -d multi-star-sim -u msim -- bash scripts/stop_all.sh
```

完全停止后 K3s 需要重新初始化数据库，恢复可能需要数分钟；启动器只在 API、节点与工作负载真实就绪后返回。残留的 Unknown 业务 Pod 会被定向重建，业务侧的故障状态不会被自动清除。

## 面板

面板可查看编队位置、uv 覆盖、PSF、调度日志与健康指标，并支持：

- 小卫星故障注入与显式恢复；
- 主控暂停并观察接管；
- 单个事件提交或 CSV/JSON 文件批量导入；
- 巡天、定源、定标模式切换。

详细操作、文件格式与故障排查见 [docs/panel-guide.md](docs/panel-guide.md)。

## 测试与验收

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

当前版本通过 69 项单元与服务测试，并在真实集群完成三类端到端验收：主控接管与旧任期拒绝、小卫星故障后的计划重构与恢复、事件触发的定源观测与模式切换。

验收输出写入 `runtime/results/`，不随仓库分发：

- `acceptance-latest.json`：端到端验收；
- `panel-operations.json`：面板操作链路；
- `formation-preview.png`：构型、uv 与 PSF 预览；
- `benchmark-numpy.json`、`benchmark-jax.json`：CPU/GPU 基准。

## 配置

- `config/runtime.json`：发行版名称、集群与镜像仓库、端口、组件版本；路径均相对仓库根目录。
- `config/simulation.json`：编队规模、轨道与阵列参数。
- `scripts/verify_layout.py`：校验运行目录未越出仓库范围。

仓库不保存主机绝对路径：部署脚本以自身位置推导根目录，`start.cmd` / `stop.cmd` 通过 `wslpath` 解析当前检出位置。

## 分支与开发

- `main`：可运行稳定版本。
- `develop`：持续开发分支，建议使用独立 worktree：

```bash
git worktree add ../multi-star-worktrees/develop -b develop
```

提交前运行完整测试，稳定后合回 `main`。`.gitattributes` 已固定脚本与源码为 LF、Windows 批处理为 CRLF，避免跨平台换行符问题。

## 已验证范围与边界

当前验证覆盖容器化功能、主控接管、事件编排、模式状态机与简化射电几何。它不构成任意非对称网络分区下的飞行安全证明，也尚未完成近场传播建模与完整高保真成像复核，相关模型仍在推进。
