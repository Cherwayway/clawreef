# Claw Pool Controller

Claw Pool Controller 是 Claw Pool 项目的核心控制组件，负责管理整个龙虾池的运行，包括龙虾注册、任务调度、负载均衡和状态监控。

## 功能特性

- 🦞 **龙虾管理**: 处理龙虾注册、认证和状态维护
- 📋 **智能调度**: 基于能力匹配和负载均衡的任务调度
- ⚖️ **负载均衡**: 多种负载均衡策略和资源优化
- 📊 **实时监控**: 全面的状态监控、告警和性能指标
- 🌐 **Web UI**: 直观的管理界面和实时仪表板
- 🔌 **API 接口**: 完整的 REST API 和 WebSocket 支持

## 快速开始

### 1. 配置 Pool Controller

编辑 `config/pool.json`：

```json
{
  "controller": {
    "poolId": "main-pool",
    "maxLobsters": 100,
    "taskTimeout": 300000
  },
  "gateway": {
    "bind": {
      "port": 18789,
      "host": "0.0.0.0"
    }
  },
  "webui": {
    "enabled": true,
    "port": 8080
  }
}
```

### 2. 启动核心服务

```bash
# 启动注册服务
python scripts/registry.py --start

# 启动任务调度器
python scripts/scheduler.py --start

# 启动监控服务
python scripts/monitor.py --start
```

### 3. 访问 Web UI

打开浏览器访问：`http://localhost:8080`

### 4. 查看池状态

```bash
python scripts/monitor.py --status
```

## 核心组件

### Registry Service (注册服务)

管理龙虾的注册、认证和状态维护：

```bash
# 查看已注册龙虾
python scripts/registry.py --list

# 查看统计信息
python scripts/registry.py --stats

# 强制注销龙虾
python scripts/registry.py --unregister <device-id>

# 导出注册表
python scripts/registry.py --export registry.json
```

### Task Scheduler (任务调度器)

智能任务调度和队列管理：

```bash
# 启动调度服务
python scripts/scheduler.py --start

# 提交任务
python scripts/scheduler.py --submit task.json

# 查看队列状态
python scripts/scheduler.py --queue

# 查看任务历史
python scripts/scheduler.py --tasks

# 取消任务
python scripts/scheduler.py --cancel <task-id>
```

示例任务文件 `task.json`：
```json
{
  "type": "data-analysis",
  "content": "分析附件中的销售数据",
  "capabilities": ["python", "data-analysis"],
  "priority": 2,
  "metadata": {
    "timeout": 600,
    "userId": "user123"
  }
}
```

### Monitor Service (监控服务)

全面的系统监控和告警：

```bash
# 启动监控服务
python scripts/monitor.py --start

# 查看实时状态
python scripts/monitor.py --status

# 查看龙虾详情
python scripts/monitor.py --lobster <device-id>

# 生成状态报告
python scripts/monitor.py --report > report.json
```

### Load Balancer (负载均衡)

智能负载分布和资源优化：

```bash
# 测试负载均衡算法
python scripts/balancer.py --test

# 查看负载分布
python scripts/balancer.py --distribution

# 调整均衡策略
python scripts/balancer.py --strategy least_connections

# 模拟任务分配
python scripts/balancer.py --simulate 100
```

## 负载均衡策略

### 1. Round Robin (轮询)
```python
# 简单轮询，依次分配给每个龙虾
strategy = "round_robin"
```

### 2. Weighted Round Robin (加权轮询)
```python
# 基于龙虾资源权重的轮询
strategy = "weighted_round_robin"
```

### 3. Least Connections (最少连接)
```python
# 分配给当前活跃任务最少的龙虾
strategy = "least_connections"
```

### 4. Resource Based (资源导向)
```python
# 基于CPU、内存等资源情况选择
strategy = "resource_based"
```

### 5. Capability Aware (能力感知)
```python
# 基于任务需求和龙虾能力匹配
strategy = "capability_aware"
```

### 6. Hybrid (混合算法)
```python
# 综合考虑多个因素的智能分配（推荐）
strategy = "hybrid"
```

## Web UI 功能

### 仪表板
- 实时统计数据显示
- 龙虾状态概览
- 任务队列监控
- 系统健康度评估

### 龙虾管理
- 在线龙虾列表
- 龙虾详细信息
- 能力和资源查看
- 任务执行历史

### 任务管理
- 任务队列状态
- 任务提交和取消
- 执行结果查看
- 性能统计分析

### 监控告警
- 实时事件日志
- 告警通知
- 性能指标图表
- 系统状态监控

## API 使用

### REST API

```javascript
// 获取池状态
const status = await fetch('/api/v1/pool/status').then(r => r.json());

// 提交任务
const task = {
  type: 'python',
  content: 'print("Hello World")',
  priority: 2
};
const result = await fetch('/api/v1/tasks', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(task)
}).then(r => r.json());

// 获取龙虾列表
const lobsters = await fetch('/api/v1/lobsters').then(r => r.json());
```

### WebSocket API

```javascript
const ws = new WebSocket('ws://localhost:18789/ws');

ws.onopen = function() {
  // 订阅事件
  ws.send(JSON.stringify({
    type: 'subscribe',
    data: { events: ['task_completion', 'lobster_status'] }
  }));
};

ws.onmessage = function(event) {
  const message = JSON.parse(event.data);
  console.log('收到事件:', message);
};
```

## 配置选项

### 调度配置
```json
{
  "scheduling": {
    "strategy": "hybrid",
    "maxQueueSize": 1000,
    "priorityLevels": 4,
    "schedulingInterval": 5000
  }
}
```

### 负载均衡配置
```json
{
  "loadBalancing": {
    "algorithm": "hybrid",
    "healthCheckInterval": 60000,
    "failoverEnabled": true,
    "weightFactors": {
      "cpu_weight": 0.3,
      "memory_weight": 0.3,
      "capability_weight": 0.2,
      "performance_weight": 0.2
    }
  }
}
```

### 监控配置
```json
{
  "monitoring": {
    "checkInterval": 10000,
    "alerting": {
      "thresholds": {
        "lobster_offline_minutes": 5,
        "task_queue_size": 50,
        "task_failure_rate": 0.2
      }
    }
  }
}
```

## 故障排除

### 龙虾连接问题

**症状**: 龙虾无法注册或连接断开

**解决方案**:
1. 检查网络连通性：`ping <controller-host>`
2. 验证端口开放：`telnet <controller-host> 18789`
3. 查看防火墙设置
4. 检查 Controller 日志

### 任务调度异常

**症状**: 任务长时间处于 pending 状态

**解决方案**:
1. 检查可用龙虾数量：`python scripts/registry.py --list`
2. 验证能力匹配：确保有龙虾支持所需能力
3. 检查调度器状态：`python scripts/scheduler.py --queue`
4. 重启调度器服务

### 负载不均衡

**症状**: 某些龙虾负载过重，其他龙虾空闲

**解决方案**:
1. 查看负载分布：`python scripts/balancer.py --distribution`
2. 调整均衡策略：`python scripts/balancer.py --strategy hybrid`
3. 检查龙虾资源配置
4. 验证权重计算

### Web UI 无法访问

**症状**: 无法打开管理界面

**解决方案**:
1. 检查 Web 服务是否启动
2. 验证端口绑定：`netstat -an | grep 8080`
3. 检查防火墙配置
4. 查看 Web 服务日志

## 监控和告警

### 关键指标

- **龙虾健康度**: 在线率、响应时间、错误率
- **任务性能**: 执行时间、成功率、吞吐量
- **队列状态**: 队列长度、等待时间、积压情况
- **系统资源**: CPU使用率、内存占用、网络延迟

### 告警规则

```json
{
  "thresholds": {
    "lobster_offline_minutes": 5,     // 龙虾离线超过5分钟告警
    "task_queue_size": 50,            // 队列积压超过50个任务告警
    "task_failure_rate": 0.2,         // 任务失败率超过20%告警
    "avg_execution_time_minutes": 10  // 平均执行时间超过10分钟告警
  }
}
```

### 告警渠道

- **控制台日志**: 实时显示在终端
- **Web UI**: 在管理界面显示告警消息
- **Webhook**: 发送到指定的 HTTP 端点
- **邮件通知**: SMTP 邮件告警（需配置）

## 扩展功能

### 多 Pool 联邦

支持多个 Pool Controller 组成联邦：

```json
{
  "features": {
    "multiPool": {
      "enabled": true,
      "federation": [
        {"poolId": "pool-1", "url": "ws://pool1.example.com:18789"},
        {"poolId": "pool-2", "url": "ws://pool2.example.com:18789"}
      ]
    }
  }
}
```

### 插件系统

支持自定义插件扩展功能：

```json
{
  "features": {
    "plugins": {
      "enabled": true,
      "directory": "~/.openclaw/pool_plugins"
    }
  }
}
```

### 计费模式

支持按使用量计费：

```json
{
  "features": {
    "billing": {
      "enabled": true,
      "currency": "USD",
      "defaultRate": 0.1
    }
  }
}
```

## 性能优化

### 数据库优化

1. **定期清理**: 清理过期的任务历史和日志
2. **索引优化**: 确保关键查询有适当的索引
3. **备份策略**: 定期备份注册表和任务数据

### 网络优化

1. **连接池**: 复用 WebSocket 连接
2. **心跳优化**: 适当调整心跳间隔
3. **负载均衡**: 使用反向代理分发请求

### 内存优化

1. **缓存策略**: 缓存常用的龙虾信息
2. **队列管理**: 限制内存中的任务队列大小
3. **垃圾回收**: 及时清理无用的数据结构

## 最佳实践

1. **容量规划**: 根据预期负载配置合适的龙虾数量
2. **监控告警**: 配置完善的监控和告警系统
3. **故障转移**: 确保关键服务的高可用性
4. **安全配置**: 启用认证和访问控制
5. **定期维护**: 定期备份数据和清理日志
6. **性能测试**: 定期进行负载测试和性能评估

## 与 Pool Agent 配合

Pool Controller 需要与 `claw-pool-agent` Skill 配合使用：

- **Agent 负责**: 自动发现、注册、心跳、任务执行
- **Controller 负责**: 注册管理、任务调度、负载均衡、监控告警

两者通过 WebSocket 和 OpenClaw 的通信机制协同工作，构成完整的分布式龙虾池系统。

---

更多信息请参考：
- [API 文档](docs/API.md)
- [Claw Pool 项目文档](../../../research/recommendation.md)
- [Web UI 使用指南](web-ui/README.md)

## 版本历史

- **v1.0.0**: 基础功能实现
  - 龙虾注册和管理
  - 任务调度系统
  - 负载均衡算法
  - 监控告警系统
  - Web UI 管理界面
  - REST API 和 WebSocket 支持