# 🏝️ ClawReef

**Distributed AI Agent Pool for OpenClaw**

ClawReef enables multiple OpenClaw instances to work together, sharing compute resources and task execution capabilities. Think of it as a coral reef where lobsters 🦞 gather, collaborate, and thrive.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-Compatible-blue.svg)](https://github.com/openclaw/openclaw)

---

## ✨ Features

- **🦞 Agent Registration** - OpenClaw instances automatically discover and join the pool
- **📋 Task Scheduling** - DAG workflows, dependencies, priorities
- **⚖️ Load Balancing** - Geographic, affinity, multi-constraint optimization
- **🌐 Federation** - Multi-pool collaboration and resource sharing
- **🔌 WebSocket Communication** - Real-time agent-controller messaging
- **🛡️ Production Ready** - Retry, circuit breaker, connection pooling

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [OpenClaw](https://github.com/openclaw/openclaw) installed
- `websockets` library

### Installation

```bash
git clone https://github.com/cherwayway/clawreef.git
cd clawreef
pip install -r requirements.txt
```

### 🌊 ClawReef CLI - The Easy Way

Create and join lobster pools with simple commands:

#### Create a Lobster Pool
```bash
# Start a controller and get an invite code
uv run python scripts/reef_cli.py create --name "My Reef"

# Output includes an invite code like:
# 📋 邀请码: reef_eyJuYW1lIjogIk15IFJlZWYiLCAiaG9zdHMiOiBbIjE5Mi4xNjguMS4xMDAiXSwgInBvcnQiOiAxODc4OSwgImNyZWF0ZWQiOiAxNzA5NjI1NjAwfQ==
```

#### Join a Lobster Pool
```bash
# Connect using the invite code
uv run python scripts/reef_cli.py join reef_eyJuYW1lIjogIk15IFJlZWYiLCAiaG9zdHMiOiBbIjE5Mi4xNjguMS4xMDAiXSwgInBvcnQiOiAxODc4OSwgImNyZWF0ZWQiOiAxNzA5NjI1NjAwfQ==
```

**Features:**
- 🌐 Auto-detects local & Tailscale IPs
- 🌍 **NEW: Cross-network tunneling** (ngrok, Cloudflare Tunnel)
- 🔐 Base64 encoded invite codes
- ⚡ Instant WebSocket connections
- 🦞 Agent auto-registration & task execution

See [REEF_CLI_USAGE.md](REEF_CLI_USAGE.md) for detailed usage.

### 🌍 Cross-Network Tunneling

ClawReef now supports cross-network connections through various tunneling solutions:

```bash
# Auto-detect and use available tunnels
uv run python scripts/reef_cli.py create --name "Global Reef"

# Force specific tunnel type
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel ngrok
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel cloudflare
uv run python scripts/reef_cli.py create --name "My Reef" --tunnel none
```

**Supported tunnels:**
- 🚀 **ngrok** - Easy setup, free tier available
- ☁️ **Cloudflare Tunnel** - Free and stable (requires setup)
- 🔒 **Tailscale** - Private network (auto-detected)

See [TUNNEL_USAGE.md](TUNNEL_USAGE.md) for comprehensive tunneling guide.

### Run Verification Tests

```bash
# Local memory-mode test
uv run python verify_minimal.py

# Cross-process WebSocket test
uv run python tests/cross_process_test.py

# CLI core functionality test
uv run python test_reef_cli.py
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│           ClawReef Controller           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Registry │ │Scheduler│ │ Monitor │   │
│  └─────────┘ └─────────┘ └─────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Balancer │ │Federation│ │ Network │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────┬───────────────────────┘
                  │ WebSocket (port 18789)
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐    ┌───▼───┐    ┌───▼───┐
│Agent 1│    │Agent 2│    │Agent N│
│  🦞   │    │  🦞   │    │  🦞   │
└───────┘    └───────┘    └───────┘
```

## 📁 Project Structure

```
clawreef/
├── README.md                    # This file
├── PROJECT_SUMMARY.md           # Development summary
├── REEF_CLI_USAGE.md           # CLI usage guide
├── verify_minimal.py            # Local verification test
├── test_reef_cli.py            # CLI functionality test
├── requirements.txt             # Python dependencies
├── scripts/
│   └── reef_cli.py             # 🌊 Main CLI tool
├── tests/
│   └── cross_process_test*.py  # WebSocket communication tests
├── skills/
│   ├── claw-pool-agent/         # Agent OpenClaw Skill
│   │   ├── SKILL.md
│   │   └── scripts/
│   └── claw-pool-controller/    # Controller OpenClaw Skill
│       ├── SKILL.md
│       ├── scripts/
│       └── web-ui/
└── research/
    └── recommendation.md        # Architecture design docs
```

## 🧪 Test Results

### Phase 2.5: Local Verification
- ✅ 7/7 tests passed
- Controller initialization, agent registration, task execution

### Phase 3: Cross-Process Communication
- ✅ 4/4 tests passed
- WebSocket communication: 100% success rate
- Dual agent parallel execution

## 🗺️ Roadmap

- [x] Phase 1: Basic Agent + Controller Skills
- [x] Phase 2: Advanced scheduling, federation, production utils
- [x] Phase 2.5: Local verification testing
- [x] Phase 3: Cross-process WebSocket testing
- [x] **Phase 3.5: User-friendly CLI** 🌊
  - ✅ Simple create/join commands
  - ✅ Auto network detection
  - ✅ Base64 invite codes
  - ✅ Multi-address failover
- [x] **Phase 3.6: Cross-network tunneling** 🌍
  - ✅ ngrok integration
  - ✅ Cloudflare Tunnel support
  - ✅ Tailscale auto-detection
  - ✅ Auto tunnel selection
- [ ] Phase 4: Real multi-machine deployment
- [ ] Phase 5: OpenClaw core integration
- [ ] Phase 6: Web management UI
- [ ] Phase 7: Token economy & marketplace 🚀

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [OpenClaw](https://github.com/openclaw/openclaw) - The AI agent framework
- The 🦞 lobster community

---

*Built with 🦞 by the ClawReef team*
