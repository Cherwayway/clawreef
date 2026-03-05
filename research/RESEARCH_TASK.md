# CC 研究任务：OpenClaw 架构深度分析

## 目标

为 Claw Pool 项目进行 OpenClaw 架构调研，找出可复用的机制和最佳实现路径。

## 研究清单

### 1. Skill 开发机制
- 阅读 `/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/docs/` 下的 skill 相关文档
- 分析现有 skill 源码：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/skills/`
- 回答：
  - Skill 的目录结构是什么？
  - SKILL.md 的格式规范？
  - Skill 能提供什么？（工具、定时任务、启动钩子？）
  - Skill 如何访问 OpenClaw 的功能？

### 2. Agent 间通信
- 研究 `sessions_spawn`、`sessions_send` 的实现
- 研究 `subagents` 工具
- 分析 MCP (Model Context Protocol) 集成
- 回答：
  - 同一机器上多个 OpenClaw 实例能通信吗？
  - 不同机器上的 OpenClaw 能通信吗？
  - 有没有现成的远程调用机制？

### 3. Node Pairing 机制
- 研究 `nodes` 工具和 pairing 流程
- 查看 `openclaw pairing` 命令实现
- 回答：
  - Pairing 是如何工作的？
  - 能否复用这套机制让龙虾加入 Pool？
  - Node 之间是怎么发现和通信的？

### 4. Gateway API
- 研究 Gateway 的 WebSocket API
- 查看 `/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/docs/` 中的 API 文档
- 回答：
  - Gateway 暴露哪些 API？
  - 能否远程控制一个 OpenClaw 实例？
  - 认证机制是什么？

### 5. 插件系统
- 研究 `@openclaw/feishu` 等插件的结构
- 查看 `/Users/appdev/.openclaw/extensions/` 或内置插件
- 回答：
  - 插件和 Skill 有什么区别？
  - 哪种方式更适合 Claw Pool？

## 输出要求

在 `/Users/appdev/clawd/projects/claw-pool/research/` 下创建：
1. `skill-analysis.md` - Skill 机制分析
2. `inter-agent-communication.md` - Agent 间通信分析
3. `node-pairing.md` - Node Pairing 机制分析
4. `gateway-api.md` - Gateway API 分析
5. `recommendation.md` - 综合建议：Claw Pool 最佳实现路径

## 参考路径
- OpenClaw 源码：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/`
- OpenClaw 文档：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/docs/`
- 现有 Skills：`/Users/appdev/.nvm/versions/node/v22.22.0/lib/node_modules/openclaw/skills/`
- 用户 Skills：`/Users/appdev/clawd/skills/`

---

开始研究吧！完成后在 recommendation.md 中给出你的最终建议。
