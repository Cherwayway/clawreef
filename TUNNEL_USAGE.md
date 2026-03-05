# ClawReef 跨网络穿透使用指南

ClawReef 现在支持跨网络穿透，让龙虾池可以在不同网络之间连接！

## 🌐 支持的隧道类型

1. **ngrok** - 最简单，免费版够用
2. **Cloudflare Tunnel** - 免费且稳定 (需要预配置)
3. **Tailscale** - 自动检测 Tailscale IP
4. **none** - 仅局域网连接

## 🚀 使用方法

### 创建支持跨网络的龙虾池

```bash
# 自动检测并使用可用的隧道 (推荐)
uv run python scripts/reef_cli.py create --name "My Global Reef"

# 强制使用 ngrok
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel ngrok

# 强制使用 Cloudflare Tunnel (需要预配置)
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel cloudflare

# 仅局域网连接
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel none
```

### 示例输出（使用 ngrok）

```
🚀 启动龙虾池: My Global Reef
📡 监听端口: 18789
🌐 可用地址: 192.168.1.100, 100.64.0.1
🔍 检测隧道工具...
🔗 创建 ngrok 隧道...
✅ ngrok 隧道已创建: wss://abc123.ngrok.io
📡 公网地址: wss://abc123.ngrok.io
============================================================
🎯 邀请码生成成功！
📋 邀请码: reef_eyJuYW1lIjogIk15IEdsb2JhbCBSZWVmIiwgImhvc3RzIjogWyIxOTIuMTY4LjEuMTAwIiwgIjEwMC42NC4wLjEiXSwgInBvcnQiOiAxODc4OSwgInR1bm5lbF91cmwiOiAid3NzOi8vYWJjMTIzLm5ncm9rLmlvIiwgImNyZWF0ZWQiOiAxNzA5NjI1NjAwfQ==
============================================================
```

### 加入跨网络龙虾池

```bash
# 使用包含隧道信息的邀请码（客户端会自动优先尝试隧道连接）
uv run python scripts/reef_cli.py join <带隧道的邀请码>
```

## 🔧 预装要求

### 使用 ngrok
```bash
# macOS
brew install ngrok

# 或从官网下载: https://ngrok.com/download
```

### 使用 Cloudflare Tunnel
```bash
# macOS
brew install cloudflared

# 需要预先配置隧道，参考: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
```

### 使用 Tailscale
```bash
# 安装 Tailscale 并登录
# https://tailscale.com/download

# 确保设备已连接到 Tailscale 网络
tailscale status
```

## 🔍 自动检测优先级

当使用 `--tunnel auto`（默认）时，系统按以下优先级检测：

1. **ngrok** - 如果检测到 ngrok 命令，自动创建隧道
2. **Cloudflare Tunnel** - 如果检测到 cloudflared（需要预配置）
3. **Tailscale** - 如果检测到活跃的 Tailscale 连接
4. **局域网** - 仅使用检测到的本地 IP 地址

## 📊 邀请码格式更新

新的邀请码包含隧道信息：
```json
{
  "name": "My Global Reef",
  "hosts": ["192.168.1.100", "100.64.0.1"],
  "port": 18789,
  "tunnel_url": "wss://abc123.ngrok.io",
  "created": 1709625600
}
```

客户端连接时会：
1. **优先尝试隧道连接**（如果有 tunnel_url）
2. **回退到局域网地址**（按 hosts 列表顺序）

## 🛡️ 安全说明

- ngrok 隧道是公开的，任何知道 URL 的人都可以连接
- Cloudflare Tunnel 可以配置访问策略
- Tailscale 仅在您的私有网络内可访问
- 建议在生产环境中使用 Cloudflare Tunnel 或 Tailscale

## 🎯 使用场景

- **跨公司网络协作** - 不同办公网络的团队协作
- **远程工作** - 家庭网络连接到公司龙虾池
- **云端部署** - 连接到云服务器上的龙虾池
- **演示展示** - 快速分享给外部用户

---

🦞 现在您的龙虾池可以游向更远的海域了！
