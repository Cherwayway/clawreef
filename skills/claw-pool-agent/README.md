# Claw Pool Agent

Claw Pool Agent 是 Claw Pool 项目的核心组件之一，负责将单个龙虾（OpenClaw 实例）接入龙虾池，执行分布式任务。

## 功能特性

- 🔍 **自动发现**: 通过 mDNS、Tailscale 或手动配置发现 Pool Controller
- 🔐 **安全认证**: 使用 OpenClaw Device Pairing 进行安全认证
- 📊 **资源监控**: 实时监控 CPU、内存、磁盘使用情况
- 💓 **心跳维持**: 定期向 Pool Controller 报告状态
- ⚡ **任务执行**: 接收并执行各类分布式任务
- 🔄 **自动重连**: 网络故障时自动重连

## 快速开始

### 1. 配置龙虾

编辑 `config/pool.json`：

```json
{
  "agent": {
    "displayName": "数据分析龙虾",
    "capabilities": ["python", "data-analysis", "web-scraping"],
    "resources": {
      "cpu": 8,
      "memory": "16GB",
      "disk": "1TB"
    },
    "controllerUrl": "auto"
  }
}
```

### 2. 发现 Pool Controller

```bash
python scripts/discover.py --scan
```

### 3. 注册到池

```bash
# 自动发现并注册
python scripts/register.py

# 或指定 Controller 地址
python scripts/register.py --controller-url ws://pool-controller.local:18789
```

### 4. 启动心跳服务

```bash
python scripts/heartbeat.py
```

### 5. 监听任务（可选）

```bash
python scripts/task_handler.py --listen
```

## 脚本详解

### discover.py - 发现服务

自动发现网络中的 Pool Controller：

```bash
# 全方位扫描
python scripts/discover.py --scan

# 仅 mDNS 发现
python scripts/discover.py --mdns

# 仅 Tailscale 发现
python scripts/discover.py --tailscale

# 验证手动地址
python scripts/discover.py --manual ws://192.168.1.100:18789
```

### register.py - 注册服务

向 Pool Controller 注册龙虾：

```bash
# 使用配置文件注册
python scripts/register.py

# 查看注册状态
python scripts/register.py --status

# 测试连接
python scripts/register.py --test --controller-url ws://host:port

# 强制重新注册
python scripts/register.py --force
```

### heartbeat.py - 心跳服务

维持与 Pool 的连接：

```bash
# 启动心跳服务
python scripts/heartbeat.py

# 发送一次心跳
python scripts/heartbeat.py --once

# 查看当前状态
python scripts/heartbeat.py --status-only

# 自定义心跳间隔（秒）
python scripts/heartbeat.py --interval 60
```

### task_handler.py - 任务处理

执行分配的任务：

```bash
# 监听任务分配
python scripts/task_handler.py --listen

# 执行指定任务文件
python scripts/task_handler.py --task-file task.json

# 测试执行环境
python scripts/task_handler.py --test

# 查看处理器状态
python scripts/task_handler.py --status
```

## 任务类型支持

Claw Pool Agent 支持以下任务类型：

- **general**: 通用任务，直接调用 OpenClaw
- **python**: Python 代码执行
- **data-analysis**: 数据分析和处理
- **web-scraping**: 网页抓取和数据提取
- **document-processing**: 文档处理和转换
- **code-generation**: 代码生成和重构
- **text-processing**: 文本处理和分析

## 配置说明

### 基础配置

```json
{
  "agent": {
    "displayName": "龙虾显示名称",
    "capabilities": ["能力1", "能力2"],
    "resources": {
      "cpu": 核心数,
      "memory": "内存大小",
      "disk": "磁盘大小"
    },
    "controllerUrl": "Controller地址",
    "heartbeatInterval": 30000,
    "maxConcurrentTasks": 3
  }
}
```

### 发现配置

```json
{
  "discovery": {
    "methods": ["mdns", "tailscale", "manual"],
    "timeout": 5000,
    "retryInterval": 30000
  }
}
```

### 任务配置

```json
{
  "tasks": {
    "supportedTypes": ["支持的任务类型"],
    "defaultTimeout": 300000,
    "maxExecutionTime": 1800000,
    "retryPolicy": {
      "maxRetries": 2,
      "retryDelay": 5000
    }
  }
}
```

## 故障排除

### 无法发现 Pool Controller

1. 检查网络连接
2. 验证 mDNS 服务：`dns-sd -B _openclaw._tcp`
3. 手动指定 Controller 地址

### 注册失败

1. 检查 Device Pairing 状态
2. 验证 Controller 地址和端口
3. 查看 Controller 日志

### 心跳失败

1. 检查网络连接稳定性
2. 验证 WebSocket 连接
3. 调整心跳间隔

### 任务执行失败

1. 检查任务类型匹配
2. 验证系统资源
3. 查看任务执行日志

## 日志和监控

Pool Agent 会记录所有关键事件：

- 连接状态变化
- 任务执行记录
- 错误和异常
- 性能指标

日志位置：`~/.openclaw/logs/pool-agent.log`

## 开发和调试

### 测试环境

```bash
python scripts/task_handler.py --test
```

### 调试模式

设置环境变量启用详细日志：

```bash
export PYTHONPATH=.
export LOG_LEVEL=DEBUG
python scripts/heartbeat.py
```

### 任务模拟

创建测试任务文件 `test_task.json`：

```json
{
  "id": "test-001",
  "type": "python",
  "content": "print('Hello from Pool Agent!')",
  "metadata": {
    "timeout": 30,
    "model": "claude-opus-4-6"
  }
}
```

执行测试：

```bash
python scripts/task_handler.py --task-file test_task.json
```

## 与 Pool Controller 配合

Pool Agent 需要与 `claw-pool-controller` Skill 配合使用：

1. **Controller 负责**：
   - 龙虾注册管理
   - 任务调度分发
   - 负载均衡
   - 状态监控

2. **Agent 负责**：
   - 自动发现和注册
   - 心跳维持
   - 任务执行
   - 资源监控

## 最佳实践

1. **资源配置**: 准确配置系统资源，避免过度承诺
2. **能力声明**: 只声明确实支持的能力类型
3. **网络稳定**: 确保与 Controller 的网络连接稳定
4. **定期维护**: 定期重启服务，保持最佳性能
5. **监控告警**: 监控日志文件，及时发现问题

## 版本历史

- v1.0.0: 基础功能实现
  - 自动发现和注册
  - 心跳维持
  - 基础任务执行

---

更多信息请参考 [Claw Pool 项目文档](../../../research/recommendation.md)。