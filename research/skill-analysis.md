# OpenClaw Skills 系统深度分析

> **研究目标**：为 Claw Pool 项目分析 OpenClaw 的 Skills 开发机制，找出可复用的架构模式和实现路径。

## 1. Skills 系统架构概览

### 1.1 三层目录结构

```
OpenClaw Skills 加载优先级（高到低）：

1. 工作区技能     ~/project/skills/          (最高优先级，开发测试)
2. 托管技能       ~/.openclaw/skills/        (本地安装，可覆盖内置)
3. 内置技能       npm包内/skills/            (54个官方技能)
4. 插件技能       extensions/*/skills/       (第三方扩展)
```

**实际路径示例**：
- 内置：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/skills/`
- 插件：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/extensions/*/skills/`

### 1.2 标准 Skill 目录结构

```
my-skill/
├── SKILL.md                  # 必需：元数据 + 文档（<5000字）
├── scripts/                  # 可选：可执行脚本
│   ├── main.py              # Python 脚本
│   ├── helper.sh            # Bash 脚本
│   └── test_*.py            # 测试文件
├── references/               # 可选：详细文档（按需加载）
│   ├── api_docs.md
│   └── examples.md
└── assets/                   # 可选：输出资源（不加载到上下文）
    └── templates/
```

### 1.3 Progressive Disclosure 设计原则

**三级加载系统（最小化 Token 成本）**：

```
Level 1: 元数据         (~100字，始终在上下文)
  ├─ name + description
  └─ metadata.openclaw

Level 2: SKILL.md主体    (<5000字，skill触发时加载)
  ├─ 工作流说明
  └─ 代码示例

Level 3: 脚本和参考     (按需加载，无限制)
  ├─ references/*.md
  └─ scripts/*
```

## 2. SKILL.md 格式规范

### 2.1 YAML 前置元数据（必需）

```markdown
---
name: my-skill-name                          # kebab-case 格式
description: "清楚说明何时使用这个skill"      # 系统提示用，<200字
homepage: https://example.com                # 可选，文档链接
user-invocable: true                         # 默认true，用户是否可调用
disable-model-invocation: false              # 默认false，是否隐藏
command-dispatch: tool                       # 可选，命令分发方式
command-tool: tool-name                      # 与dispatch配合使用

metadata:
  openclaw:
    emoji: "🎯"                             # UI 显示图标
    os: ["darwin", "linux"]                 # 平台限制
    requires:                               # 加载条件
      bins: ["gh", "git"]                   # 必需二进制
      anyBins: ["cmd1", "cmd2"]             # 至少一个存在
      env: ["API_KEY"]                      # 环境变量
      config: ["github.enabled"]           # 配置路径
    primaryEnv: "GITHUB_TOKEN"              # API密钥映射
    install:                                # 安装选项
      - id: "brew"
        kind: "brew"
        formula: "gh"
        bins: ["gh"]
        label: "Install GitHub CLI"
        os: ["darwin"]
---
```

### 2.2 文档主体结构

```markdown
# Skill 标题

## 概述
[1-2句说明作用和使用时机]

## 主要工作流

### 工作流 1：XXX操作
[详细步骤说明]

```bash
# 脚本调用示例（使用 {baseDir} 占位符）
python {baseDir}/scripts/process.py --input data.json
uv run {baseDir}/scripts/main.py --prompt "任务描述"
```

## 关键配置

### 环境变量
- `API_KEY`: API访问密钥
- `DEBUG`: 调试模式开关

### 配置项
- `github.enabled`: 是否启用GitHub集成
```

## 3. Skills 能力类别分析

### 3.1 六大能力类型

| 类型 | 描述 | 代表案例 | 复杂度 |
|------|------|----------|--------|
| **工具集成** | CLI/API封装 | `github`(gh), `apple-notes`(memo) | ⭐⭐ |
| **工作流编排** | 多步骤流程 | `healthcheck`(安全审计) | ⭐⭐⭐ |
| **脚本执行** | Python/Bash | `model-usage`, `nano-banana-pro` | ⭐⭐⭐ |
| **文档操作** | 第三方平台 | `feishu-doc`, `notion` | ⭐⭐⭐⭐ |
| **AI代理协调** | 多代理编排 | `prose`(虚拟机), `coding-agent` | ⭐⭐⭐⭐⭐ |
| **安全加固** | 系统评估 | `healthcheck` | ⭐⭐⭐⭐ |

### 3.2 具体案例剖析

#### 案例1：简单工具集成 - `apple-notes`

```
apple-notes/
└── SKILL.md                  # 仅63行，无脚本

特点：
- 纯文档指导，无代码执行
- 调用系统CLI：memo notes -a "标题"
- 主要提供工作流模板
```

**核心价值**：标准化常见操作的调用方式。

#### 案例2：中等脚本执行 - `model-usage`

```
model-usage/
├── SKILL.md                  # 工作流说明（43行）
└── scripts/
    ├── model_usage.py        # 主脚本（370行）
    └── test_model_usage.py   # 测试文件
```

**调用方式**：
```bash
python {baseDir}/scripts/model_usage.py \
  --provider claude \
  --mode current \
  --format json
```

**技术特点**：
- 支持多种输入：CLI参数、文件、stdin
- 数据处理：JSON解析、成本聚合
- 输出格式化：文本或JSON

#### 案例3：复杂代理协调 - `coding-agent`

```markdown
---
name: coding-agent
requires: { anyBins: ["claude", "codex", "opencode"] }
---

# 特殊能力：
- 后台执行：background:true
- 交互式终端：pty:true
- 进程管理：process action:log/poll/kill
```

**后台执行流程**：
```bash
# 1. 启动后台任务
bash pty:true workdir:~/project background:true \
  command:"codex exec --auto 'Build feature'"
# 返回：sessionId

# 2. 监控状态
process action:poll sessionId:abc123

# 3. 动态交互
process action:submit sessionId:abc123 data:"yes"

# 4. 终止任务
process action:kill sessionId:abc123
```

#### 案例4：超复杂虚拟机 - `prose` (OpenProse)

```
prose/
├── SKILL.md                 # 入口路由（200行）
├── prose.md                 # VM语义定义（2000+行）
├── compiler.md              # 验证器（500行）
├── state/                   # 4种状态管理
│   ├── filesystem.md
│   ├── sqlite.md
│   └── postgres.md
├── guidance/                # 设计模式
└── examples/                # 37个示例程序
    ├── 01-hello-world.prose
    └── 28-gas-town.prose
```

**虚拟机特性**：
- 定义完整的编程语言
- 支持并行代理执行
- 4种状态持久化方式
- 丰富的示例库

**示例程序**：
```prose
session "analysis" with claude-opus-4-6 {
  task("市场分析", priority=high)
}

agent researcher {
  analyze(topic) -> report
}

parallel {
  researcher.analyze("区块链")
  researcher.analyze("AI")
}
```

## 4. Skills 如何访问 OpenClaw 功能

### 4.1 工具接口映射

Skills 通过在 SKILL.md 中指导模型使用 OpenClaw 的标准工具：

```markdown
# 在skill文档中指导工具使用：

使用 `bash` 工具执行命令：
bash command:"gh repo list --limit 10"

使用 `message` 工具发送消息：
message channel:"discord" text:"任务完成"

使用 `sessions_spawn` 启动子代理：
sessions_spawn task:"处理数据" model:"claude-opus-4-6"
```

**常见工具映射**：

| 工具 | Skill 用途 | 示例 |
|-----|-----------|------|
| `bash` | CLI工具调用 | `gh`, `git`, `curl` |
| `message` | 平台消息发送 | Discord, Slack通知 |
| `browser` | 浏览器自动化 | 登录、数据抓取 |
| `web_fetch` | HTTP API | REST调用 |
| `sessions_spawn` | 子代理协调 | 并行任务处理 |
| `read`/`write` | 文件操作 | 配置、状态管理 |

### 4.2 环境变量注入机制

**配置映射**（`openclaw.json`）：
```json
{
  "skills": {
    "entries": {
      "github": {
        "enabled": true,
        "apiKey": {"source": "env", "id": "GITHUB_TOKEN"},
        "env": {
          "GITHUB_TOKEN": "ghp_xxx...",
          "DEBUG": "true"
        }
      }
    }
  }
}
```

**运行时流程**：
```
1. 会话启动 → 读取skill元数据
2. 应用环境变量注入
3. 脚本执行时可访问 process.env
4. 会话结束 → 恢复原始环境
```

### 4.3 配置依赖检查

```markdown
# SKILL.md 中声明配置要求
---
metadata:
  openclaw:
    requires:
      config: ["github.enabled", "channels.discord.token"]
---
```

**Gating 机制**：只有配置存在且为真值时，skill才会被加载到会话中。

## 5. Skills 生命周期管理

### 5.1 发现与加载流程

```
会话启动时：

1. 目录扫描
   ├─ workspace/skills/      (优先)
   ├─ ~/.openclaw/skills/    (本地)
   ├─ bundled skills/        (内置)
   └─ extensions/*/skills/   (插件)

2. 元数据解析
   ├─ 读取 SKILL.md YAML 头
   ├─ 检查平台兼容性 (OS)
   ├─ 验证二进制依赖 (bins)
   ├─ 检查环境变量 (env)
   ├─ 验证配置要求 (config)
   └─ 应用白名单过滤 (allowBundled)

3. 会话快照生成
   └─ 缓存符合条件的skills列表

4. 系统提示编译
   └─ 生成XML格式的skills清单 (~1500 tokens)
```

### 5.2 配置控制

```json
{
  "skills": {
    "allowBundled": ["github", "model-usage"],    // 内置白名单
    "load": {
      "extraDirs": ["~/custom-skills"],          // 额外目录
      "watch": true,                             // 热重载
      "watchDebounceMs": 250
    },
    "entries": {
      "github": {"enabled": true},              // 启用
      "deprecated-skill": {"enabled": false}    // 禁用
    }
  }
}
```

### 5.3 沙箱环境支持

**Docker 沙箱配置**：
```json
{
  "agents": {
    "defaults": {
      "sandbox": {
        "docker": {
          "setupCommand": "apt-get install -y gh git",
          "env": {
            "GITHUB_TOKEN": "ghp_xxx"
          }
        }
      }
    }
  }
}
```

**限制**：
- 主机加载时检查 `requires.bins`
- 沙箱内同样需要安装依赖
- 通过 `setupCommand` 预装

## 6. Token 成本优化

### 6.1 系统提示开销分析

**Skills 清单格式**（注入到每次对话）：
```xml
<skills>
  <skill>
    <name>github</name>
    <description>GitHub operations via gh CLI...</description>
    <location>bundled</location>
  </skill>
  <!-- 重复54个内置skills... -->
</skills>
```

**成本估算**：
```
基础开销 = 195字符
每个skill = 97 + name长度 + description长度 + location长度

粗算：24-30 tokens/skill
54个内置skills ≈ 1300-1600 tokens
```

### 6.2 优化策略

1. **精简描述**：重点说明"何时使用"，避免冗长说明
2. **白名单过滤**：
   ```json
   {"skills": {"allowBundled": ["essential-skill-1", "essential-skill-2"]}}
   ```
3. **Gating 机制**：通过条件过滤减少加载的skills
4. **会话缓存**：同一会话内复用skills快照

## 7. 插件集成模式

### 7.1 插件声明格式

**openclaw.plugin.json**：
```json
{
  "id": "feishu",
  "name": "Feishu Integration",
  "skills": ["./skills"],           // 指向skills目录
  "configSchema": {
    "properties": {
      "apiKey": {"type": "string"}
    }
  }
}
```

### 7.2 实际案例

**飞书插件** (`extensions/feishu/`):
```
feishu/
├── openclaw.plugin.json
└── skills/
    ├── feishu-doc/SKILL.md      # 文档操作
    ├── feishu-drive/SKILL.md    # 文件管理
    ├── feishu-perm/SKILL.md     # 权限控制
    └── feishu-wiki/SKILL.md     # Wiki页面
```

**加载机制**：插件skills参与正常的优先级排序，可被workspace skills覆盖。

## 8. 安全考虑

### 8.1 主要风险

1. **恶意代码执行**：第三方scripts可能包含有害代码
2. **秘密泄露**：环境变量可能被记录到日志
3. **API滥用**：无限制的CLI工具访问

### 8.2 缓解措施

```json
{
  "skills": {
    "allowBundled": ["trusted-skill-only"],      // 严格白名单
    "entries": {
      "third-party-skill": {
        "enabled": false                         // 默认禁用
      }
    }
  },
  "agents": {
    "defaults": {
      "sandbox": {"docker": {...}}              // 沙箱隔离
    }
  }
}
```

**最佳实践**：
- 审读第三方skill代码
- 使用Docker沙箱
- 避免在verbose模式下包含秘密
- 使用 `primaryEnv` 映射密钥

## 9. CLI 管理命令

### 9.1 Skills 管理

```bash
# 列出所有skills（含过滤状态）
openclaw skills list [--eligible]

# 显示具体skill详情
openclaw skills info <skill-name>

# 检查依赖满足情况
openclaw skills check

# ClawHub 市场集成
clawhub install <skill-package>
clawhub update --all
clawhub sync --all
```

### 9.2 系统工具（skills调用）

```bash
# 安全审计（healthcheck skill使用）
openclaw security audit [--deep] [--fix]

# 系统状态（多个skills使用）
openclaw status [--deep]
openclaw health --json

# 定时任务管理
openclaw cron add --name task-name --schedule "0 */6 * * *" --command "..."
openclaw cron list
```

## 10. 对 Claw Pool 的启示

### 10.1 可复用架构

1. **三层加载系统**：workspace > managed > bundled
2. **Progressive Disclosure**：元数据 → 文档 → 脚本
3. **Gating机制**：平台、依赖、配置检查
4. **环境变量注入**：动态配置管理

### 10.2 Claw Pool Skills 设计建议

#### `claw-pool-agent` skill 结构：
```
claw-pool-agent/
├── SKILL.md                  # 注册流程 + 心跳机制
├── scripts/
│   ├── register.py          # 池注册脚本
│   ├── heartbeat.py         # 心跳上报
│   └── receive_task.py      # 任务接收
└── references/
    └── pool_protocol.md     # 池协议文档
```

#### `claw-pool-controller` skill 结构：
```
claw-pool-controller/
├── SKILL.md                 # 管理界面 + 调度逻辑
├── scripts/
│   ├── pool_manager.py     # 龙虾目录管理
│   ├── task_dispatcher.py  # 任务分发
│   └── billing.py          # 计费记录
└── assets/
    └── web-ui/             # 可选的Web界面
```

### 10.3 关键技术要点

1. **会话隔离**：每个龙虾独立的会话空间
2. **权限控制**：基于Agent ID的访问控制
3. **状态管理**：利用 OpenClaw 的持久化机制
4. **工具复用**：充分利用现有的通信工具
5. **沙箱安全**：对外部龙虾使用Docker隔离

---

## 总结

OpenClaw 的 Skills 系统提供了：

✅ **模块化架构**：独立skill包，易于开发和分发
✅ **渐进式加载**：最小化token成本，提高性能
✅ **灵活配置**：条件过滤、环境注入、热重载
✅ **安全机制**：沙箱、权限、依赖检查
✅ **生态集成**：插件系统、市场、CLI管理

**对 Claw Pool 的价值**：完全符合"复用 OpenClaw"的设计原则，可以直接基于 Skills 系统构建龙虾池的管理和协作逻辑。

---

*报告生成时间: 2026-03-05*
*基于 OpenClaw v5.17.0 分析*