# Claw Pool Controller API 文档

Claw Pool Controller 提供了完整的 REST API 和 WebSocket API 用于第三方集成和管理。

## 基础信息

- **Base URL**: `http://localhost:8080/api/v1`
- **WebSocket URL**: `ws://localhost:18789/ws`
- **Content-Type**: `application/json`
- **认证**: 可选的 Token 认证（默认关闭）

## REST API

### 1. Pool 状态管理

#### GET /pool/status
获取 Pool 整体状态

**响应示例:**
```json
{
  "timestamp": "2026-03-05T10:30:00Z",
  "poolId": "main-pool",
  "lobsters": {
    "total": 15,
    "online": 12,
    "offline": 3,
    "statusCounts": {
      "online": 10,
      "busy": 2,
      "offline": 3
    }
  },
  "tasks": {
    "total": 1245,
    "queueSize": 5,
    "running": 8,
    "completed": 1200,
    "failed": 32
  },
  "performance": {
    "avgExecutionTime": 45.2,
    "successRate": 0.974,
    "throughput": 2.3
  },
  "health": {
    "score": 92.5,
    "status": "excellent"
  }
}
```

#### GET /pool/statistics
获取详细统计信息

**查询参数:**
- `period`: 统计周期 (`1h`, `24h`, `7d`, `30d`)
- `include`: 包含的数据 (`tasks`, `lobsters`, `performance`)

### 2. 龙虾管理

#### GET /lobsters
获取龙虾列表

**查询参数:**
- `status`: 过滤状态 (`online`, `offline`, `busy`, `idle`)
- `capabilities`: 过滤能力 (逗号分隔)
- `limit`: 限制数量
- `offset`: 偏移量

**响应示例:**
```json
{
  "total": 15,
  "lobsters": [
    {
      "deviceId": "lobster_abc123",
      "displayName": "数据分析龙虾",
      "capabilities": ["python", "data-analysis"],
      "status": "online",
      "resources": {
        "cpu": 8,
        "memory": "16GB"
      },
      "activeTasks": 2,
      "registrationTime": "2026-03-05T08:00:00Z",
      "lastHeartbeat": "2026-03-05T10:29:30Z"
    }
  ]
}
```

#### GET /lobsters/{deviceId}
获取指定龙虾详情

**响应示例:**
```json
{
  "deviceId": "lobster_abc123",
  "displayName": "数据分析龙虾",
  "capabilities": ["python", "data-analysis", "web-scraping"],
  "resources": {
    "cpu": 8,
    "memory": "16GB",
    "disk": "1TB"
  },
  "status": "busy",
  "activeTasks": 2,
  "registrationTime": "2026-03-05T08:00:00Z",
  "lastHeartbeat": "2026-03-05T10:29:30Z",
  "currentTask": {
    "taskId": "task_xyz789",
    "taskType": "data-analysis",
    "startTime": "2026-03-05T10:25:00Z"
  },
  "taskHistory": [
    {
      "taskId": "task_abc123",
      "taskType": "python",
      "status": "completed",
      "duration": 32.5
    }
  ],
  "performance": {
    "totalTasks": 156,
    "completedTasks": 152,
    "failedTasks": 4,
    "avgExecutionTime": 28.7,
    "successRate": 0.974
  }
}
```

#### DELETE /lobsters/{deviceId}
强制注销指定龙虾

**响应:**
```json
{
  "success": true,
  "message": "龙虾已注销"
}
```

### 3. 任务管理

#### GET /tasks
获取任务列表

**查询参数:**
- `status`: 过滤状态
- `type`: 过滤任务类型
- `assignedTo`: 过滤分配的龙虾
- `limit`: 限制数量
- `offset`: 偏移量
- `sortBy`: 排序字段 (`createdTime`, `priority`, `duration`)
- `sortOrder`: 排序方向 (`asc`, `desc`)

**响应示例:**
```json
{
  "total": 1245,
  "tasks": [
    {
      "taskId": "task_xyz789",
      "taskType": "data-analysis",
      "status": "running",
      "priority": 2,
      "createdTime": "2026-03-05T10:20:00Z",
      "assignedTime": "2026-03-05T10:25:00Z",
      "assignedTo": "lobster_abc123",
      "metadata": {
        "timeout": 300,
        "userId": "user123"
      }
    }
  ]
}
```

#### POST /tasks
提交新任务

**请求体:**
```json
{
  "type": "data-analysis",
  "content": "分析附件中的销售数据",
  "capabilities": ["python", "data-analysis"],
  "priority": 2,
  "metadata": {
    "timeout": 600,
    "userId": "user123",
    "model": "claude-opus-4-6"
  }
}
```

**响应:**
```json
{
  "taskId": "task_new123",
  "status": "pending",
  "queuePosition": 3,
  "estimatedWait": 45
}
```

#### GET /tasks/{taskId}
获取指定任务详情

#### PUT /tasks/{taskId}/priority
更新任务优先级

**请求体:**
```json
{
  "priority": 3
}
```

#### DELETE /tasks/{taskId}
取消任务

### 4. 队列管理

#### GET /queue
获取任务队列状态

**响应:**
```json
{
  "queueSize": 12,
  "processing": 8,
  "strategies": {
    "current": "hybrid",
    "available": ["round_robin", "least_connections", "hybrid"]
  },
  "performance": {
    "avgWaitTime": 23.5,
    "throughput": 2.1
  }
}
```

#### PUT /queue/strategy
更新调度策略

**请求体:**
```json
{
  "strategy": "least_connections"
}
```

### 5. 监控和告警

#### GET /monitoring/alerts
获取告警列表

**查询参数:**
- `severity`: 过滤严重程度 (`info`, `warning`, `error`, `critical`)
- `since`: 起始时间
- `limit`: 限制数量

#### GET /monitoring/metrics
获取监控指标

**查询参数:**
- `metrics`: 指标列表 (逗号分隔)
- `period`: 时间周期
- `interval`: 聚合间隔

### 6. 配置管理

#### GET /config
获取当前配置

#### PUT /config
更新配置

**请求体:**
```json
{
  "scheduling": {
    "strategy": "hybrid",
    "maxQueueSize": 200
  },
  "monitoring": {
    "checkInterval": 5000
  }
}
```

## WebSocket API

WebSocket 连接用于实时通信和事件推送。

### 连接
```javascript
const ws = new WebSocket('ws://localhost:18789/ws');
```

### 消息格式
所有消息都使用 JSON 格式：

```json
{
  "type": "message_type",
  "data": { ... },
  "timestamp": "2026-03-05T10:30:00Z",
  "requestId": "optional_request_id"
}
```

### 客户端 → 服务器消息

#### 订阅事件
```json
{
  "type": "subscribe",
  "data": {
    "events": ["lobster_status", "task_completion", "queue_update", "alerts"]
  }
}
```

#### 取消订阅
```json
{
  "type": "unsubscribe",
  "data": {
    "events": ["lobster_status"]
  }
}
```

#### 获取实时状态
```json
{
  "type": "get_status",
  "data": {
    "include": ["lobsters", "tasks", "queue"]
  },
  "requestId": "status_001"
}
```

### 服务器 → 客户端事件

#### 龙虾状态变化
```json
{
  "type": "lobster_status",
  "data": {
    "deviceId": "lobster_abc123",
    "status": "busy",
    "activeTasks": 2,
    "timestamp": "2026-03-05T10:30:00Z"
  }
}
```

#### 任务完成
```json
{
  "type": "task_completion",
  "data": {
    "taskId": "task_xyz789",
    "status": "completed",
    "duration": 45.2,
    "assignedTo": "lobster_abc123"
  }
}
```

#### 队列更新
```json
{
  "type": "queue_update",
  "data": {
    "queueSize": 8,
    "processing": 12,
    "waitTime": 23.5
  }
}
```

#### 告警通知
```json
{
  "type": "alert",
  "data": {
    "severity": "warning",
    "message": "龙虾 ABC123 心跳延迟",
    "details": {
      "deviceId": "lobster_abc123",
      "heartbeatLag": 300
    }
  }
}
```

## 错误处理

### HTTP 错误码
- `200`: 成功
- `201`: 创建成功
- `400`: 请求错误
- `401`: 未认证
- `403`: 无权限
- `404`: 资源不存在
- `429`: 请求过于频繁
- `500`: 服务器内部错误

### 错误响应格式
```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "指定的任务不存在",
    "details": {
      "taskId": "task_invalid"
    }
  }
}
```

## 认证和授权

当启用认证时，需要在请求头中包含访问令牌：

```http
Authorization: Bearer <access_token>
```

### 获取访问令牌
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}
```

**响应:**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiresIn": 3600,
  "tokenType": "Bearer"
}
```

## 速率限制

默认速率限制：
- **未认证用户**: 每15分钟100个请求
- **认证用户**: 每15分钟1000个请求

超过限制时返回 HTTP 429 状态码：

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "请求过于频繁，请稍后再试",
    "retryAfter": 900
  }
}
```

## SDK 和示例

### JavaScript/Node.js 示例

```javascript
const axios = require('axios');
const WebSocket = require('ws');

// REST API 客户端
class ClawPoolClient {
  constructor(baseURL = 'http://localhost:8080/api/v1') {
    this.baseURL = baseURL;
    this.axios = axios.create({ baseURL });
  }

  async getPoolStatus() {
    const response = await this.axios.get('/pool/status');
    return response.data;
  }

  async submitTask(task) {
    const response = await this.axios.post('/tasks', task);
    return response.data;
  }

  async getLobsters(filters = {}) {
    const response = await this.axios.get('/lobsters', { params: filters });
    return response.data;
  }
}

// WebSocket 客户端
class ClawPoolWebSocket {
  constructor(url = 'ws://localhost:18789/ws') {
    this.url = url;
    this.ws = null;
    this.handlers = {};
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.on('message', (data) => {
      const message = JSON.parse(data);
      const handler = this.handlers[message.type];
      if (handler) {
        handler(message.data);
      }
    });

    return new Promise((resolve, reject) => {
      this.ws.on('open', resolve);
      this.ws.on('error', reject);
    });
  }

  subscribe(events) {
    this.send('subscribe', { events });
  }

  on(eventType, handler) {
    this.handlers[eventType] = handler;
  }

  send(type, data) {
    this.ws.send(JSON.stringify({ type, data }));
  }
}

// 使用示例
async function example() {
  const client = new ClawPoolClient();

  // 获取池状态
  const status = await client.getPoolStatus();
  console.log('Pool Status:', status);

  // 提交任务
  const task = {
    type: 'python',
    content: 'print("Hello from Claw Pool!")',
    priority: 2
  };
  const result = await client.submitTask(task);
  console.log('Task submitted:', result);

  // WebSocket 连接
  const ws = new ClawPoolWebSocket();
  await ws.connect();

  ws.on('task_completion', (data) => {
    console.log('Task completed:', data);
  });

  ws.subscribe(['task_completion', 'lobster_status']);
}
```

### Python 示例

```python
import asyncio
import json
import requests
import websockets

class ClawPoolClient:
    def __init__(self, base_url="http://localhost:8080/api/v1"):
        self.base_url = base_url
        self.session = requests.Session()

    def get_pool_status(self):
        response = self.session.get(f"{self.base_url}/pool/status")
        return response.json()

    def submit_task(self, task):
        response = self.session.post(f"{self.base_url}/tasks", json=task)
        return response.json()

    def get_lobsters(self, **filters):
        response = self.session.get(f"{self.base_url}/lobsters", params=filters)
        return response.json()

class ClawPoolWebSocket:
    def __init__(self, url="ws://localhost:18789/ws"):
        self.url = url
        self.handlers = {}

    async def connect(self):
        self.websocket = await websockets.connect(self.url)

    async def listen(self):
        async for message in self.websocket:
            data = json.loads(message)
            handler = self.handlers.get(data['type'])
            if handler:
                await handler(data['data'])

    def on(self, event_type, handler):
        self.handlers[event_type] = handler

    async def subscribe(self, events):
        await self.websocket.send(json.dumps({
            "type": "subscribe",
            "data": {"events": events}
        }))

# 使用示例
async def main():
    client = ClawPoolClient()

    # 获取状态
    status = client.get_pool_status()
    print("Pool Status:", status)

    # WebSocket 监听
    ws = ClawPoolWebSocket()
    await ws.connect()

    async def on_task_completion(data):
        print("Task completed:", data)

    ws.on('task_completion', on_task_completion)
    await ws.subscribe(['task_completion', 'lobster_status'])
    await ws.listen()

if __name__ == "__main__":
    asyncio.run(main())
```

## 最佳实践

1. **批量操作**: 尽可能使用批量 API 减少请求数量
2. **WebSocket**: 对于实时更新使用 WebSocket 而不是轮询
3. **错误处理**: 始终处理 API 错误和网络异常
4. **缓存**: 缓存不经常变化的数据如龙虾列表
5. **分页**: 大列表使用分页避免超时
6. **监控**: 监控 API 调用和错误率

更多信息请参考 [Claw Pool 项目文档](../../../research/recommendation.md)。