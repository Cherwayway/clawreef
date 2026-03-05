---
name: claw-pool-agent
description: Claw Pool agent that automatically joins a lobster pool and executes distributed tasks. Use when setting up a lobster for pool participation, handling pool registration, task execution, or managing pool agent status. Triggers on pool-related operations like "join pool", "register lobster", "execute pool tasks", or "pool agent status".
metadata:
  openclaw:
    emoji: "🦞"
    os: ["darwin", "linux", "win32"]
    requires:
      config: ["pool.agent.enabled"]
---

# Claw Pool Agent

Claw Pool Agent 是安装在每只龙虾上的核心组件，负责自动发现并接入 Pool Controller，接收和执行分配的任务。

## 主要功能

### 1. 自动发现和注册
- 通过 Bonjour/mDNS 发现本地网络中的 Pool Controller
- 支持 Tailscale 网络中的自动发现
- 手动配置 Pool Gateway 地址
- 使用 OpenClaw Device Pairing 进行安全认证

### 2. 能力注册和管理
- 上报龙虾的技能列表（python, web-scraping, data-analysis 等）
- 报告硬件资源信息（CPU、内存、存储、GPU）
- 设置定价信息（市场模式下）
- 地理位置和网络区域标识

### 3. 任务执行
- 接收 Pool Controller 分配的任务
- 使用 OpenClaw 标准工具执行任务
- 返回执行结果和性能指标
- 错误处理和重试机制

### 4. 状态管理
- 定期心跳上报（默认每30秒）
- 状态同步：idle/busy/error/maintenance
- 资源使用情况监控
- 自动重连和故障恢复

## 快速开始

### 1. 启用 Pool Agent

在 OpenClaw 配置中添加：

```json
{
  "pool": {
    "agent": {
      "enabled": true,
      "autoDiscovery": true,
      "controllerUrl": "auto",
      "displayName": "数据分析龙虾",
      "capabilities": ["python", "web-scraping", "data-analysis"],
      "resources": {
        "cpu": 8,
        "memory": "16GB",
        "disk": "1TB",
        "gpu": "NVIDIA RTX 4090"
      }
    }
  }
}
```

### 2. 手动注册到 Pool

```bash
python scripts/register.py --controller-url ws://pool-controller:18789
```

### 3. 查看当前状态

```bash
python scripts/heartbeat.py --status-only
```

### 4. 手动发现 Pool Controllers

```bash
python scripts/discover.py --scan
```

## 脚本说明

### scripts/discover.py
发现网络中的 Pool Controller：
- mDNS/Bonjour 本地发现
- Tailscale 网络扫描
- 手动验证指定地址

### scripts/register.py
向 Pool Controller 注册龙虾：
- 发送设备信息和能力
- 处理认证和授权
- 存储注册凭证

### scripts/heartbeat.py
维护与 Pool 的连接：
- 定期心跳上报
- 状态同步
- 资源使用率监控
- 连接故障检测

### scripts/task_handler.py
任务执行引擎：
- 接收任务分配
- 调用 OpenClaw 工具执行
- 结果返回和错误处理
- 性能指标收集

## 配置文件

### config/pool.json
```json
{
  "agent": {
    "displayName": "My Lobster",
    "capabilities": ["python", "web", "analysis"],
    "resources": {
      "cpu": 4,
      "memory": "8GB",
      "disk": "500GB"
    },
    "controllerUrl": "auto",
    "heartbeatInterval": 30000,
    "maxConcurrentTasks": 3,
    "pricing": {
      "enabled": false,
      "hourlyRate": 0.5,
      "currency": "USD"
    }
  },
  "discovery": {
    "methods": ["mdns", "tailscale", "manual"],
    "timeout": 5000,
    "retryInterval": 30000
  },
  "security": {
    "devicePairing": true,
    "tokenRefreshInterval": 3600000
  }
}
```

## 通信协议

Pool Agent 使用 OpenClaw 的 sessions_spawn 机制与 Controller 通信：

### 注册请求
```javascript
{
  "method": "agent",
  "params": {
    "agentId": "pool-controller",
    "messages": [{
      "role": "user",
      "content": JSON.stringify({
        "action": "register",
        "lobster": {
          "deviceId": "dev_abc123",
          "displayName": "数据分析龙虾",
          "capabilities": ["python", "web-scraping"],
          "resources": {
            "cpu": 8,
            "memory": "16GB"
          }
        }
      })
    }]
  }
}
```

### 心跳上报
```javascript
{
  "action": "heartbeat",
  "lobster": {
    "deviceId": "dev_abc123",
    "status": "idle",
    "currentTask": null,
    "resources": {
      "cpuUsage": 25,
      "memoryUsage": 8.5
    }
  }
}
```

## 故障排除

### 无法发现 Pool Controller
1. 检查网络连接：`ping pool-controller.local`
2. 验证 mDNS 服务：`dns-sd -B _openclaw._tcp`
3. 手动指定 Controller 地址

### 注册失败
1. 检查 Device Pairing 状态
2. 验证认证凭证
3. 查看 Controller 日志

### 任务执行失败
1. 检查能力匹配
2. 验证资源可用性
3. 查看任务执行日志

## 监控和日志

Pool Agent 会记录所有关键事件：
- 连接状态变化
- 任务执行记录
- 错误和异常
- 性能指标

日志位置：`~/.openclaw/logs/pool-agent.log`

## 最佳实践

1. **资源管理**：准确报告系统资源，避免过度承诺
2. **能力声明**：只声明确实支持的能力
3. **网络稳定**：确保与 Controller 的网络连接稳定
4. **定期维护**：定期重启和清理，保持最佳性能
5. **安全更新**：及时更新 OpenClaw 和 Pool Agent

## 与 Pool Controller 配合

Pool Agent 需要与 `claw-pool-controller` Skill 配合使用：
- Controller 管理整个 Pool 的运行
- Agent 专注于单个龙虾的任务执行
- 通过 OpenClaw 的安全通信机制连接