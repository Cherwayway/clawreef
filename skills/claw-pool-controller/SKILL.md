---
name: claw-pool-controller
description: Claw Pool controller that manages a distributed pool of lobsters (OpenClaw instances). Use when setting up pool management, handling lobster registration, task scheduling, load balancing, or pool monitoring. Triggers on pool management operations like "manage pool", "schedule tasks", "balance load", "monitor lobsters", or "pool controller dashboard".
metadata:
  openclaw:
    emoji: "🎛️"
    os: ["darwin", "linux"]
    requires:
      config: ["pool.controller.enabled"]
---

# Claw Pool Controller

Claw Pool Controller 是 Claw Pool 项目的核心控制组件，负责管理整个龙虾池的运行，包括龙虾注册、任务调度、负载均衡和状态监控。

## 主要功能

### 1. 龙虾管理
- 处理龙虾注册请求和设备认证
- 维护龙虾能力和状态数据库
- 龙虾健康检查和故障检测
- 动态龙虾接入和移除

### 2. 任务调度
- 接收用户任务请求
- 基于能力和负载的智能匹配
- 任务队列管理和优先级调度
- 超时处理和故障转移

### 3. 负载均衡
- 实时负载监控和分析
- 多种均衡策略（轮询、加权、最少连接）
- 动态负载调整
- 资源利用率优化

### 4. 监控和统计
- 实时龙虾状态监控
- 任务执行统计和性能指标
- 系统健康度评估
- 告警通知和事件推送

### 5. 用户接口
- Web UI 管理界面
- REST API 第三方集成
- CLI 命令行管理工具
- WebSocket 实时通信

## 快速开始

### 1. 启用 Pool Controller

在 OpenClaw 配置中添加：

```json
{
  "pool": {
    "controller": {
      "enabled": true,
      "poolId": "main-pool",
      "maxLobsters": 100,
      "taskTimeout": 300000,
      "heartbeatInterval": 30000
    }
  },
  "gateway": {
    "bind": {
      "port": 18789,
      "host": "0.0.0.0"
    }
  }
}
```

### 2. 启动 Controller 服务

```bash
# 启动注册服务
python scripts/registry.py --start

# 启动任务调度器
python scripts/scheduler.py --start

# 启动监控服务
python scripts/monitor.py --start
```

### 3. 查看 Pool 状态

```bash
python scripts/monitor.py --status
```

### 4. 启动 Web UI（可选）

```bash
python scripts/web_server.py --port 8080
```

## 脚本详解

### scripts/registry.py - 注册管理

管理龙虾注册表：

```bash
# 启动注册服务
python scripts/registry.py --start

# 查看注册的龙虾
python scripts/registry.py --list

# 强制注销指定龙虾
python scripts/registry.py --unregister <device-id>

# 导出注册表
python scripts/registry.py --export registry.json
```

### scripts/scheduler.py - 任务调度

管理任务队列和调度：

```bash
# 启动调度器
python scripts/scheduler.py --start

# 提交新任务
python scripts/scheduler.py --submit task.json

# 查看任务队列
python scripts/scheduler.py --queue

# 取消任务
python scripts/scheduler.py --cancel <task-id>
```

### scripts/monitor.py - 状态监控

监控整个 Pool 的运行状态：

```bash
# 启动监控服务
python scripts/monitor.py --start

# 查看实时状态
python scripts/monitor.py --status

# 查看龙虾详情
python scripts/monitor.py --lobster <device-id>

# 生成状态报告
python scripts/monitor.py --report
```

### scripts/balancer.py - 负载均衡

实现智能负载均衡：

```bash
# 测试负载均衡算法
python scripts/balancer.py --test

# 查看负载分布
python scripts/balancer.py --distribution

# 调整均衡策略
python scripts/balancer.py --strategy round-robin
```

## 架构设计

### 核心组件

```
┌─────────────────────────────────────┐
│          Pool Controller             │
├─────────────────────────────────────┤
│ Registry Service  │ Task Scheduler  │
│ - 龙虾注册管理     │ - 任务队列管理   │
│ - 能力匹配        │ - 智能调度分发   │
│ - 状态同步        │ - 负载均衡      │
├─────────────────────────────────────┤
│ Monitor Service   │ Web UI Service  │
│ - 实时状态监控     │ - 管理界面      │
│ - 健康检查        │ - API 接口      │
│ - 告警通知        │ - 事件推送      │
└─────────────────────────────────────┘
```

### 数据流

```
用户任务请求 → 任务调度器 → 能力匹配 → 负载均衡 → 选择龙虾 → 任务分发
     ↑                                                      ↓
状态监控 ← 注册服务 ← 心跳接收 ← WebSocket连接 ← 任务执行 ← 龙虾代理
```

## 任务调度策略

### 1. 能力匹配

基于龙虾声明的能力进行任务匹配：

```python
def match_capabilities(task_requirements, lobster_capabilities):
    return all(req in lobster_capabilities for req in task_requirements)
```

### 2. 负载均衡算法

#### Round Robin（轮询）
```python
def round_robin_select(available_lobsters):
    return available_lobsters[current_index % len(available_lobsters)]
```

#### Weighted（加权）
```python
def weighted_select(lobsters_with_weights):
    return random.choices(lobsters, weights=weights)[0]
```

#### Least Connections（最少连接）
```python
def least_connections_select(lobsters):
    return min(lobsters, key=lambda l: l.active_tasks)
```

### 3. 优先级调度

- **High Priority**: 立即执行
- **Normal Priority**: 正常队列
- **Low Priority**: 空闲时执行

## 通信协议

### 龙虾注册协议

```javascript
// 龙虾注册请求
{
  "action": "register",
  "lobster": {
    "deviceId": "lobster_abc123",
    "displayName": "数据分析龙虾",
    "capabilities": ["python", "data-analysis"],
    "resources": {
      "cpu": 8,
      "memory": "16GB"
    }
  }
}

// Controller 响应
{
  "action": "register_ack",
  "status": "approved",
  "registrationId": "reg_xyz789",
  "poolInfo": {
    "poolId": "main-pool",
    "version": "1.0.0"
  }
}
```

### 任务分发协议

```javascript
// 任务分配
{
  "action": "task_assignment",
  "task": {
    "id": "task_001",
    "type": "data-analysis",
    "content": "分析附件中的数据",
    "metadata": {
      "priority": "high",
      "timeout": 300,
      "model": "claude-opus-4-6"
    }
  }
}

// 任务结果
{
  "action": "task_result",
  "result": {
    "taskId": "task_001",
    "status": "completed",
    "result": {...},
    "duration": 45.2
  }
}
```

### 心跳监控协议

```javascript
// 心跳上报
{
  "action": "heartbeat",
  "lobster": {
    "deviceId": "lobster_abc123",
    "status": "idle",
    "resources": {
      "cpuUsage": 25,
      "memoryUsage": 8.5
    }
  }
}
```

## Web UI 管理界面

Pool Controller 提供了完整的 Web 管理界面：

### 主要页面

- **Dashboard**: 概览和实时状态
- **Lobsters**: 龙虾管理和监控
- **Tasks**: 任务队列和历史
- **Analytics**: 统计分析和报告
- **Settings**: 系统配置和设置

### 功能特性

- 实时状态更新（WebSocket）
- 拖拽式任务分配
- 可视化负载监控
- 历史数据图表
- 导出和报告生成

访问地址：`http://localhost:8080`

## API 接口

### RESTful API

```
GET    /api/v1/pool/status          # 获取 Pool 状态
GET    /api/v1/lobsters              # 获取龙虾列表
POST   /api/v1/lobsters/{id}/tasks   # 分配任务给指定龙虾
GET    /api/v1/tasks                 # 获取任务列表
POST   /api/v1/tasks                 # 提交新任务
DELETE /api/v1/tasks/{id}            # 取消任务
```

### WebSocket API

```javascript
// 连接
ws://localhost:18789/ws

// 订阅事件
{
  "action": "subscribe",
  "events": ["lobster_status", "task_completion", "pool_stats"]
}

// 接收事件
{
  "event": "lobster_status",
  "data": {
    "deviceId": "lobster_abc123",
    "status": "busy"
  }
}
```

## 配置文件

### config/pool.json

```json
{
  "controller": {
    "poolId": "main-pool",
    "maxLobsters": 100,
    "taskTimeout": 300000,
    "heartbeatInterval": 30000,
    "scheduling": {
      "strategy": "least-connections",
      "maxQueueSize": 1000,
      "priorityLevels": 3
    },
    "loadBalancing": {
      "algorithm": "weighted",
      "healthCheckInterval": 60000,
      "failoverEnabled": true
    }
  },
  "webui": {
    "enabled": true,
    "port": 8080,
    "host": "0.0.0.0",
    "auth": {
      "enabled": false,
      "users": []
    }
  },
  "api": {
    "enabled": true,
    "rateLimiting": {
      "enabled": true,
      "requests": 100,
      "window": 900
    }
  },
  "monitoring": {
    "metricsEnabled": true,
    "alerting": {
      "enabled": true,
      "webhooks": []
    }
  }
}
```

## 故障排除

### 龙虾连接问题
1. 检查网络连通性
2. 验证 WebSocket 端口开放
3. 查看防火墙设置

### 任务调度失败
1. 检查能力匹配配置
2. 验证龙虾可用性
3. 查看调度器日志

### 负载均衡异常
1. 检查龙虾负载数据
2. 验证均衡算法配置
3. 重启负载均衡服务

### Web UI 无法访问
1. 检查服务端口绑定
2. 验证防火墙配置
3. 查看 Web 服务日志

## 监控和告警

### 关键指标

- 活跃龙虾数量
- 任务队列长度
- 平均任务执行时间
- 系统资源使用率
- 错误率和成功率

### 告警规则

- 龙虾离线超过阈值
- 任务队列积压
- 任务执行失败率过高
- 系统资源不足

### 告警渠道

- Webhook 通知
- 邮件告警
- Slack 消息
- 系统事件

## 扩展性设计

### 多 Pool 支持

- Pool 联邦管理
- 跨 Pool 任务路由
- 统一计费和统计

### 插件系统

- 自定义调度算法
- 扩展任务类型
- 第三方集成

### 高可用部署

- Controller 集群
- 数据持久化
- 故障切换

## 最佳实践

1. **资源规划**: 根据预期负载配置合适的龙虾数量
2. **监控告警**: 配置完善的监控和告警系统
3. **定期维护**: 定期清理任务历史和日志
4. **安全配置**: 启用认证和访问控制
5. **备份策略**: 定期备份配置和数据

---

更多信息请参考 [Claw Pool 项目文档](../../../research/recommendation.md)。