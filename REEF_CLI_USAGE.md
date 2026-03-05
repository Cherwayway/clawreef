# ClawReef CLI 使用说明

极简的龙虾池连接工具，实现了分布式龙虾池的创建和加入功能。

## 快速开始

### 1. 创建龙虾池

```bash
uv run python scripts/reef_cli.py create --name "My Reef"
```

这会：
- 启动 WebSocket Controller 服务
- 自动检测可用网络地址（局域网 IP + Tailscale IP）
- 生成邀请码（base64 编码的连接信息）
- 显示邀请码供用户分享

示例输出：
```
🚀 启动龙虾池: My Reef
📡 监听端口: 18789
🌐 可用地址: 192.168.1.100, 100.64.0.1
============================================================
🎯 邀请码生成成功！
📋 邀请码: reef_eyJuYW1lIjogIk15IFJlZWYiLCAiaG9zdHMiOiBbIjE5Mi4xNjguMS4xMDAiLCAiMTAwLjY0LjAuMSJdLCAicG9ydCI6IDE4Nzg5LCAiY3JlYXRlZCI6IDE3MDk2MjU2MDB9
============================================================
📤 分享此邀请码给其他用户，他们可以使用以下命令加入:
   python reef_cli.py join reef_eyJuYW1lIjogIk15IFJlZWYiLCAiaG9zdHMiOiBbIjE5Mi4xNjguMS4xMDAiLCAiMTAwLjY0LjAuMSJdLCAicG9ydCI6IDE4Nzg5LCAiY3JlYXRlZCI6IDE3MDk2MjU2MDB9
============================================================
```

### 2. 加入龙虾池

```bash
uv run python scripts/reef_cli.py join <邀请码>
```

这会：
- 解析邀请码获取连接信息
- 依次尝试连接到所有可用地址
- 自动注册为 Agent
- 保持心跳连接
- 接收和执行任务

示例输出：
```
🏊 ClawReef - 加入龙虾池
🌊 准备加入龙虾池: My Reef
🌐 可选地址: 192.168.1.100, 100.64.0.1
📡 端口: 18789
📅 池创建时间: 2026-03-05 17:13:03
🔗 尝试连接: 192.168.1.100:18789
✅ WebSocket 连接成功
📝 发送注册请求
✅ 注册成功!
   🏊 Pool: final-test-pool
   📊 总 Agents: 1
```

## 邀请码格式

邀请码采用 `reef_<base64(JSON)>` 格式：

```json
{
  "name": "My Reef",
  "hosts": ["192.168.1.100", "100.64.0.1"],
  "port": 18789,
  "created": 1709625600
}
```

## 功能特性

### 网络地址自动检测
- 自动获取本地局域网 IP
- 自动检测 Tailscale IP（100.x.x.x 网段）
- 提供多个备选连接地址

### 容错连接机制
- 依次尝试所有可用地址
- 自动选择可连接的地址
- 详细的错误提示和诊断信息

### WebSocket 通信
- 基于已验证的跨进程通信机制
- 支持心跳保持连接
- 自动任务分配和执行
- 实时状态监控

## 高级选项

### 自定义端口
```bash
uv run uv run python scripts/reef_cli.py create --name "My Reef" --port 9999
```

### 详细日志
```bash
uv run uv run python scripts/reef_cli.py create --name "My Reef" --verbose
uv run python scripts/reef_cli.py join <invite_code> --verbose
```

## 故障排除

### 连接失败
1. 检查网络连接是否正常
2. 确认 Controller 服务正在运行
3. 验证邀请码是否有效
4. 检查防火墙是否阻止了端口

### 端口冲突
使用 `--port` 参数指定不同的端口：
```bash
uv run uv run python scripts/reef_cli.py create --name "My Reef" --port 19999
```

### 依赖问题
确保已安装项目依赖：
```bash
uv pip install -r requirements.txt
```

## 技术实现

- **语言**: Python 3.9+
- **通信**: WebSocket (websockets 库)
- **网络检测**: socket + subprocess
- **邀请码**: Base64 + JSON
- **架构**: Controller-Agent 模式

## 下一步计划

- [ ] 添加池管理 Web UI
- [ ] 支持任务负载均衡
- [ ] 实现持久化存储
- [ ] 添加安全认证机制
