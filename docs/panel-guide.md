# 小卫星群调度面板使用说明

## 1. 快速启动与关闭

### 启动

1. 在文件管理器中打开项目根目录。
2. 双击 `start.cmd`；Linux 环境执行 `bash scripts/start_all.sh`。
3. 控制台会依次检查 Docker、K3s 节点、系统 Pod、三主星、九小星和 dashboard。**完全停止后的恢复可能需要数分钟**，因为 K3s 还可能执行 SQLite 初始化和 VACUUM；不要只凭容器 Running 就提前开始使用。看到 `START_OK` 后，访问：
   - **http://127.0.0.1:18082**
4. 保持该控制台开启。它只用于保持专用 WSL 会话，不需要在其中输入命令。

重复执行 `start.cmd` 不会重新安装环境或重复创建集群；已有集群会做恢复和就绪检查。若完全停止后留下明确的 Unknown/NodeLost 业务 Pod，启动器会只重建这些失效 Pod；PVC、镜像、配置和历史结果不会删除。启动要求九个小星的进程级 healthz 均可访问，但允许业务 failed 状态继续存在，不会为通过启动检查而自动恢复故障星。

### 关闭

双击项目根目录的 `stop.cmd`。

关闭操作只停止 dashboard 转发并终止 `multi-star-sim`：

- 不调用全局 `wsl --shutdown`，不影响其他 WSL 发行版。
- 不删除集群配置、容器镜像、PVC、VHDX 或测试报告。
- 再次运行 `start.cmd` 即可恢复。

主机或电脑重启后，也使用同一方式恢复。

## 2. 面板各区域怎么看

| 区域 | 含义 |
|---|---|
| 主控 ID | 当前实际持有主控 Lease 的主星 |
| EPOCH | 主控任期；切换后应单调增加 |
| PLAN VERSION | 全局观测计划版本；事件、故障重构和模式切换应产生新版本 |
| 模式 | 当前为 SURVEY、FIXED_SOURCE 或 CALIBRATION |
| 小卫星相对位置 | 九颗小星的等轴测投影；颜色表示健康状态，可点击选择 |
| UV 覆盖 | 当前健康小星形成的基线采样，包含共轭点 |
| PSF | 根据当前 uv 采样实时计算的点扩散函数，不是预制图片 |
| 输入测试频谱 | 由事件表单的频率、通量和谱指数生成的 synthetic input；不是实测数据 |
| 主控事件终端 | 按 seq 倒序显示真实事件、选主、重构和模式切换日志 |

面板每秒读取一次 `/api/snapshot`。断线时保留最近真实快照并显示连接异常，不把缓存当成新数据。

## 3. 注入小卫星故障

1. 在故障操作区选择目标小星，例如 `small-sat-8`。
2. 点击“注入故障”，并在确认框中确认。
3. 等待面板刷新和主控重构：
   - 该星健康状态变为 `failed`；
   - 健康小星从 9 颗降为 8 颗；
   - 默认小星阵列基线从 36 降为 28；
   - 主控生成新的 plan_version，并调整其余小星的阵列任务。
4. 查看终端日志和小星任务状态。

故障状态是持久的：Pod 或主机重启不会自动把故障星变回健康。

### 显式恢复

选择同一颗小星，点击“显式恢复”。恢复后健康小星和基线数应恢复为 9 颗、36 条。

恢复不会把故障期间的 UNKNOWN 在途任务擅自改成成功，也不会自动重放不可逆变轨。

## 4. 注入主控失联/暂停故障

1. 记录当前主控 ID 和 EPOCH。
2. 点击“暂停当前主控 22 秒（测试切换）”，并确认。
3. 被暂停的主控立即停止续约和下发新命令。
4. 在当前 Lease 过期后，其他主星接管。现有实测切换时间约 15～16 秒，但不是固定保证值。
5. 检查：
   - 主控 ID 改变；
   - EPOCH 增加；
   - plan_version 不回退；
   - 旧主恢复后不会直接抢回控制权。

该按钮模拟的是主控暂停/失联，不是永久硬件损毁。小星端的旧 epoch 命令仍会被拒绝。

## 5. 注入单个天文事件

在“提交观测事件”区域填写：

| 字段 | 含义 | 示例 |
|---|---|---|
| event_id | 唯一事件标识，用于去重 | `demo-event-001` |
| target_id | 目标源标识 | `synthetic-deep-space-target` |
| frequency_hz | 事件频率，Hz | `140000000` |
| flux_jy | 合成通量，Jy | `25` |
| confidence | 置信度，0～1 | `0.97` |
| spectral_index | 合成谱指数 | `-0.7` |
| expiry_s | 从当前仿真时刻起的有效时长，秒 | `600` |

点击“提交事件”后，正常响应应包括：

1. 事件被持久化；
2. 主控自动进入 FIXED_SOURCE；
3. 生成包含该 event_id 的新计划；
4. 小星收到观测任务；
5. 面板频率、uv/PSF 和终端日志更新。

再次提交相同 event_id 会按重复事件处理，不应再次增加 plan_version。

## 6. 从 CSV/JSON 文件批量传入测试事件

### 操作步骤

1. 点击面板上的“下载示例 CSV”，或直接使用项目中的 `src/multi_star/static/test-events.csv`。
2. 在“测试数据文件”区域选择 `.csv` 或 `.json` 文件。
3. 点击“读取/预览”，确认解析条数和事件摘要。
4. 点击“注入文件事件”。
5. 查看真实返回统计：accepted、duplicate、failed。任何失败都会显示，不会把失败改写为成功。

限制：单个文件不超过 **1 MiB**，一次最多 **100 条事件**。文件事件按顺序逐条提交，便于追踪和去重。

### CSV 格式

表头必须包含：

```text
event_id,target_id,frequency_hz,flux_jy,confidence,spectral_index,expiry_s
```

示例：

```csv
event_id,target_id,frequency_hz,flux_jy,confidence,spectral_index,expiry_s
file-event-001,synthetic-target-a,80000000,12.5,0.95,-0.7,600
file-event-002,synthetic-target-b,140000000,25.0,0.97,-0.7,600
```

### JSON 格式

可以使用事件数组：

```json
[
  {
    "event_id": "json-event-001",
    "target_id": "synthetic-target-json",
    "frequency_hz": 140000000,
    "flux_jy": 20.0,
    "confidence": 0.95,
    "spectral_index": -0.7,
    "expiry_s": 600
  }
]
```

也支持 `{"events": [...]}` 包装。

**边界**：当前文件导入用于事件和调度测试，不是 FITS 高保真天空模型导入。用于多频成像比较时，各频段必须使用一致的天空结构和光度尺度，不能通过换频段重新随机生成天空来人为提高响应。

## 7. 观测模式切换

### SURVEY

常规广域巡天模式，使用当前健康小星维持巡天计划和阵列。

### FIXED_SOURCE

源观测模式。进入该模式需要一个仍存在且未过期的事件；可通过单个事件或文件事件触发。事件到期后，不应继续把它当作有效定点观测依据。

### CALIBRATION

射电标定模式。当前用于验证标定任务的调度和模式状态机。副主单口径链路与干涉阵列复增益标定需要区分；简单 ON/OFF 不等于完整阵列相位标定。

模式切换以最新真实快照为准，并生成新的 plan_version。如果存在 UNKNOWN 的在途任务，模式切换可能被拒绝；应先在终端中检查原因，不要反复点击。

## 8. 验收输出位置

| 内容 | 路径 |
|---|---|
| 最近一次端到端验收 | `runtime/results/acceptance-latest.json` |
| 面板故障/文件/模式/主控操作验收 | `runtime/results/panel-operations.json` |
| ring/Y/spiral 阵列、uv 与 PSF 预览 | `runtime/results/formation-preview.png` |
| GPU 基准 | `runtime/results/benchmark-jax.json` |
| CPU 基准 | `runtime/results/benchmark-numpy.json` |
| 最近一次启动时间 | `runtime/results/last-start.txt` |
| 最近一次正常关闭时间 | `runtime/results/last-stop.txt` |

## 9. 常见问题

### 面板无法连接

1. 确认启动控制台仍在运行。
2. 重新运行 `start.cmd`，它会执行恢复和就绪检查。
3. 不要启动多个会争用 18082 端口的自定义转发进程。

### 主控长时间无响应

若刚点击过主控暂停，请等待 Lease 超时和接管完成。若超过约 30 秒仍无 leader，查看终端日志并重新运行启动检查。

### 小星故障重启后仍存在

这是设计行为，不是状态丢失。确认需要恢复后，使用“显式恢复”。

### 文件事件部分失败

查看 file-status 中每条事件的真实结果。常见原因是缺字段、数值非法、文件超限或 event_id 重复。修正文件后重新读取，再执行注入。

## 10. 当前验证边界

本系统当前验证的是容器化功能仿真、故障切换、事件编排和模式状态机。它不是任意非对称网络分区下的飞行安全证明，也尚未完成近场/磁层传播建模和完整高保真成像复核。
