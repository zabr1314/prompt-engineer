# OpenClaw System Prompt 审计报告

> 使用 prompt-engineer skill 的 audit-checklist 审计
> 日期: 2026-04-02

## Prompt 类型判断

**类型：System Prompt（内核）**

这是标准的 system prompt，定义 agent 的身份、工具、行为规则、输出风格。

## 8 Pattern 评分

### 1. Identity Anchor — 2/5

**当前**: `You are a personal assistant running inside OpenClaw.`

**问题**:
- "personal assistant" 太泛——和 ChatGPT、Claude、Gemini 没有区分度
- 没有说"你的优势是什么"
- "running inside OpenClaw" 是环境信息，不是身份

**Claude Code 对比**: `You are an interactive agent that helps users with software engineering tasks.` — 至少说了核心任务领域

**改进建议**: 应该包含核心能力定位，比如 "You are a personal assistant with tools for file management, web search, automation, and multi-agent orchestration."

### 2. Red Line Declaration — 3/5

**当前**: 有 `[safetySection]` 条件注入，但具体内容取决于配置

**问题**:
- 安全指令是条件性的，不是硬编码的
- 没有白名单+黑名单+灰色地带的结构化声明
- 依赖模型自带的安全训练

**Claude Code 对比**: 有专门的 `cyberRiskInstruction.ts`，由 Safeguards 团队维护，白名单+黑名单结构

**改进建议**: 即使模型自带安全训练，也应该有显式的红线声明，特别是针对 OpenClaw 特有的风险（如 config 修改、gateway 重启、发消息等）

### 3. Preference Chain — 3/5

**当前**: 工具偏好链有，但比较弱

**已有**:
- "When a first-class tool exists for an action, use the tool directly instead of asking the user to run equivalent CLI or slash commands."
- "TOOLS.md does not control tool availability"

**缺失**:
- 没有 Claude Code 那样的 "Read > cat, Edit > sed, Grep > grep" 精确偏好链
- 没有解释"为什么专用工具更好"
- 没有给回退口

**改进建议**: 针对 OpenClaw 的核心工具（exec、browser、web_search、web_fetch）写明确的偏好链

### 4. Anti-pattern Catalog — 3/5

**当前**: 有一些，但不够系统

**已有**:
- "Do not invent commands" (CLI)
- "Do not poll subagents list in a loop"
- "Do not narrate routine tool calls"
- "Do not run config.apply unless explicitly requested"

**缺失**:
- 没有针对 LLM 常见失败模式的反模式（gold-plating、过度设计、不必要的错误处理）
- 没有"不要重复问已经回答过的问题"
- 没有"不要在群聊中代替用户说话"（AGENTS.md 里有但 system prompt 没有）

**改进建议**: 把 AGENTS.md 里的一些核心规则提升到 system prompt 层级

### 5. Risk Gradient — 4/5

**当前**: 这是 OpenClaw 做得比较好的部分

**已有**:
- `allow-once` vs `allow-always` 的区分
- 保留完整命令/脚本给用户确认
- "Treat allow-once as single-command only"
- Self-update 需要显式请求
- config 修改需要 schema.lookup 先检查

**缺失**:
- 没有显式的风险分级矩阵（哪些操作自由执行、哪些要确认）
- 没有"用户确认一次不等于永久确认"的声明

**改进建议**: 添加显式的风险分级，类似于 Claude Code 的 "Executing actions with care" 段

### 6. Adversarial Verification — 1/5

**当前**: 完全缺失

**问题**:
- 没有任何验证要求
- 没有"运行代码后验证输出"的约束
- 没有对抗性测试的要求

**Claude Code 对比**: 有完整的 Verification Agent + "Before reporting complete, verify it actually works"

**改进建议**: 添加 "After making changes, verify they work: run the test, check the output, confirm the behavior." 至少在基础层面

### 7. Context Isolation — 4/5

**当前**: 这是 OpenClaw 的特色

**已有**:
- "If a task is more complex or takes longer, spawn a sub-agent. Completion is push-based."
- "Do not poll subagents list in a loop; only check status on-demand."
- ACP harness spawn rules

**缺失**:
- 没有"Don't peek"规则（spawn 后不要读中间输出）
- 没有"Don't race"规则（不要伪造子 agent 的结果）

**改进建议**: 从 Claude Code 的 Fork 模式规则里借鉴 "Don't peek" 和 "Don't race"

### 8. Output Contract — 3/5

**当前**: 有基本的输出风格指导

**已有**:
- "When you have nothing to say, respond with ONLY: HEARTBEAT_OK"
- "Keep narration brief and value-dense"
- Reply tags 系统
- Silent replies 规则

**缺失**:
- 没有数字锚定（如 Claude Code 的 "≤25 words between tool calls"）
- 没有针对不同场景的输出格式约束
- 没有 "Don't restate what the user said" 规则

**改进建议**: 添加更精确的输出长度约束

## 总分

| Pattern | 分数 |
|:---|:---:|
| Identity Anchor | 2/5 |
| Red Line Declaration | 3/5 |
| Preference Chain | 3/5 |
| Anti-pattern Catalog | 3/5 |
| Risk Gradient | 4/5 |
| Adversarial Verification | 1/5 |
| Context Isolation | 4/5 |
| Output Contract | 3/5 |
| **平均** | **2.9/5** |

## 总结

**2.9/5 — 中等偏下，有明显盲区。**

**最强项**: Risk Gradient (4/5) 和 Context Isolation (4/5) — OpenClaw 的多 agent 架构和权限模型做得不错

**最弱项**: Adversarial Verification (1/5) — 完全缺失，这是最大的盲区。Identity Anchor (2/5) — 太泛，没有区分度

**核心问题**: OpenClaw 的 system prompt 更像一个"功能列表"而不是"行为操作系统"——它列出了能做什么，但没有足够约束"怎么做"和"不要做什么"。
