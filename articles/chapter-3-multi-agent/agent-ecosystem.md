# Claude Code 多 Agent 编排（二）：Agent 生态系统

> 深入分析 Claude Code 的 6 个内置 agent、外部 agent 加载机制、生命周期管理和 agent 间通信协议。

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                  Agent 生态系统                        │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  内置 Agent    │  │  外部 Agent   │  │ 插件 Agent  │ │
│  │  (built-in)   │  │  (markdown)  │  │  (plugin)   │ │
│  │  6 个硬编码    │  │  .claude/    │  │  插件目录    │ │
│  │  source:      │  │  agents/     │  │  source:    │ │
│  │  'built-in'   │  │  source:     │  │  'plugin'   │ │
│  │               │  │  'user'/'    │  │             │ │
│  │               │  │  project'    │  │             │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘ │
│         │                  │                  │       │
│         └──────────────────┼──────────────────┘       │
│                            │                          │
│                   getActiveAgentsFromList()            │
│                   去重 + 优先级合并                      │
│                            │                          │
│                   ┌────────▼────────┐                 │
│                   │  AgentRegistry   │                 │
│                   │  activeAgents[]  │                 │
│                   └────────┬────────┘                 │
│                            │                          │
│              ┌─────────────┼─────────────┐            │
│              │             │             │            │
│         ┌────▼────┐  ┌────▼────┐  ┌────▼────┐      │
│         │ SendMessage│ │ TeamCreate│ │ ResumeAgent│  │
│         │  通信工具   │ │  团队管理  │ │  恢复机制   │  │
│         └─────────┘  └─────────┘  └─────────┘      │
└─────────────────────────────────────────────────────┘
```

## 一、6 个内置 Agent 的设计哲学

Claude Code 的 6 个内置 agent 代表了 LLM 编排的六种经典角色。它们在 `builtInAgents.ts` 中注册，在各自的 `built-in/*.ts` 文件中定义。

### 1. general-purpose（万能工）

**定位**：默认 agent，什么都能做。

```typescript
// built-in/generalPurposeAgent.ts
export const GENERAL_PURPOSE_AGENT: BuiltInAgentDefinition = {
  agentType: 'general-purpose',
  whenToUse: 'General-purpose agent for researching complex questions...',
  tools: ['*'],  // 所有工具
  source: 'built-in',
  getSystemPrompt: getGeneralPurposeSystemPrompt,
}
```

**设计哲学**：兜底方案。当没有更合适的 agent 时使用。tools 设为 `['*']`（通配符），拥有所有可用工具。

**Prompt 特点**：
- 鼓励完成任务但不过度工程（"don't gold-plate, but don't leave it half-done"）
- 强调搜索和分析能力
- 禁止主动创建文档文件

### 2. Explore（搜索专家）

**定位**：只读的代码搜索 agent，追求速度。

```typescript
// built-in/exploreAgent.ts
export const EXPLORE_AGENT: BuiltInAgentDefinition = {
  agentType: 'Explore',
  disallowedTools: [
    AGENT_TOOL_NAME, EXIT_PLAN_MODE_TOOL_NAME,
    FILE_EDIT_TOOL_NAME, FILE_WRITE_TOOL_NAME, NOTEBOOK_EDIT_TOOL_NAME,
  ],
  model: process.env.USER_TYPE === 'ant' ? 'inherit' : 'haiku',
  omitClaudeMd: true,
  getSystemPrompt: () => getExploreSystemPrompt(),
}
```

**设计哲学**：
- **严格只读**：prompt 中用 `=== CRITICAL: READ-ONLY MODE ===` 反复强调，禁止 Write/Edit/Bash 写操作
- **追求速度**：外部用户默认使用 `haiku` 模型（更快更便宜）
- **省 token**：`omitClaudeMd: true` 跳过 CLAUDE.md 注入，省 ~5-15 Gtok/周
- **省 gitStatus**：`runAgent.ts` 中对 Explore/Plan 类型跳过 gitStatus 注入

```typescript
// runAgent.ts 第 ~280-285 行
const resolvedSystemContext =
  agentDefinition.agentType === 'Explore' || agentDefinition.agentType === 'Plan'
    ? systemContextNoGit  // 跳过 gitStatus（可达 40KB）
    : baseSystemContext;
```

这些 token 优化在 3400 万+ 次/周的 Explore 调用量下意义重大。

### 3. Plan（架构师）

**定位**：只读的架构规划 agent。

```typescript
// built-in/planAgent.ts
export const PLAN_AGENT: BuiltInAgentDefinition = {
  agentType: 'Plan',
  disallowedTools: [ /* 与 Explore 相同 */ ],
  model: 'inherit',
  omitClaudeMd: true,
  getSystemPrompt: () => getPlanV2SystemPrompt(),
}
```

**设计哲学**：与 Explore 类似的只读限制，但定位不同。Explore 回答"这里有什么"，Plan 回答"应该怎么做"。

**Prompt 特点**：
- 要求输出结构化计划：步骤、依赖、挑战
- 强制输出 `### Critical Files for Implementation` 列表
- 从多个视角分析（"apply your assigned perspective"）

### 4. verification（对抗性验证者）

**定位**：不是确认能用，而是试图搞坏。

```typescript
// built-in/verificationAgent.ts
export const VERIFICATION_AGENT: BuiltInAgentDefinition = {
  agentType: 'verification',
  color: 'red',
  background: true,  // 强制后台执行
  disallowedTools: [AGENT_TOOL_NAME, EXIT_PLAN_MODE_TOOL_NAME, FILE_EDIT_TOOL_NAME, FILE_WRITE_TOOL_NAME, NOTEBOOK_EDIT_TOOL_NAME],
  model: 'inherit',
  criticalSystemReminder_EXPERIMENTAL: 'CRITICAL: This is a VERIFICATION-ONLY task...',
  getSystemPrompt: () => VERIFICATION_SYSTEM_PROMPT,
}
```

**设计哲学**：这是最有趣的 agent。它的 prompt 识别了 LLM 验证者的两个已知失败模式：

1. **验证回避**：面对检查时找理由不执行——读代码、叙述要测什么、写"PASS"然后继续
2. **被前 80% 迷惑**：看到漂亮的 UI 或通过的测试套件就想放行，没注意到一半按钮没功能

Prompt 中包含了每种变更类型的详细验证策略（前端、后端、CLI、移动端、数据库迁移等），以及必须执行的对抗性探测（并发、边界值、幂等性、孤儿操作）。

**输出格式**强制要求：
```
### Check: [验证内容]
**Command run:** [执行的命令]
**Output observed:** [实际输出]
**Result: PASS** (或 FAIL)
```

最后一行必须是 `VERDICT: PASS/FAIL/PARTIAL`。

### 5. claude-code-guide（文档专家）

**定位**：Claude Code / Claude Agent SDK / Claude API 的文档查询 agent。

```typescript
// built-in/claudeCodeGuideAgent.ts
export const CLAUDE_CODE_GUIDE_AGENT: BuiltInAgentDefinition = {
  agentType: 'claude-code-guide',
  tools: ['Glob', 'Grep', 'Read', 'WebFetch', 'WebSearch'],
  model: 'haiku',
  permissionMode: 'dontAsk',
  getSystemPrompt: () => CLAUDE_CODE_GUIDE_SYSTEM_PROMPT,
}
```

**设计哲学**：最小工具集（只有搜索和读取），`permissionMode: 'dontAsk'` 自动批准，`haiku` 模型追求速度。

**Prompt 特点**：维护了三个文档源的 URL（Claude Code docs、Agent SDK docs、Claude API docs），通过 WebFetch 动态获取。

### 6. statusline-setup（状态栏配置）

**定位**：专门用于配置 Claude Code 状态栏。

```typescript
// built-in/statuslineSetup.ts
export const STATUSLINE_SETUP_AGENT: BuiltInAgentDefinition = {
  agentType: 'statusline-setup',
  tools: ['Read', 'Edit'],
  model: 'sonnet',
  color: 'orange',
  getSystemPrompt: () => STATUSLINE_SYSTEM_PROMPT,
}
```

**设计哲学**：极小工具集（只有 Read 和 Edit），专注单一任务。能将用户的 shell PS1 配置转换为 Claude Code 的 statusLine 命令。

### 内置 Agent 注册逻辑

`builtInAgents.ts` 的 `getBuiltInAgents()` 函数控制哪些 agent 被激活：

```typescript
export function getBuiltInAgents(): AgentDefinition[] {
  // SDK 用户可通过环境变量禁用所有内置 agent
  if (isEnvTruthy(process.env.CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS) && getIsNonInteractiveSession()) {
    return [];
  }

  const agents: AgentDefinition[] = [GENERAL_PURPOSE_AGENT, STATUSLINE_SETUP_AGENT];

  if (areExplorePlanAgentsEnabled()) {
    agents.push(EXPLORE_AGENT, PLAN_AGENT);
  }

  // Claude Code Guide 仅在非 SDK 入口时包含
  if (isNonSdkEntrypoint) {
    agents.push(CLAUDE_CODE_GUIDE_AGENT);
  }

  // Verification agent 通过 GrowthBook 实验门控
  if (feature('VERIFICATION_AGENT') && getFeatureValue_CACHED_MAY_BE_STALE('tengu_hive_evidence', false)) {
    agents.push(VERIFICATION_AGENT);
  }

  return agents;
}
```

## 二、外部 Agent 的加载机制

### Markdown Agent 定义

用户可以在 `.claude/agents/` 目录下放置 markdown 文件定义自定义 agent。文件的 frontmatter 定义元数据，正文是 system prompt。

加载流程在 `loadAgentsDir.ts` 的 `getAgentDefinitionsWithOverrides()` 中：

```typescript
export const getAgentDefinitionsWithOverrides = memoize(
  async (cwd: string): Promise<AgentDefinitionsResult> => {
    const markdownFiles = await loadMarkdownFilesForSubdir('agents', cwd);
    
    const customAgents = markdownFiles
      .map(({ filePath, baseDir, frontmatter, content, source }) => {
        return parseAgentFromMarkdown(filePath, baseDir, frontmatter, content, source);
      })
      .filter(agent => agent !== null);

    const pluginAgents = await loadPluginAgents();
    const builtInAgents = getBuiltInAgents();

    const allAgentsList = [...builtInAgents, ...pluginAgents, ...customAgents];
    const activeAgents = getActiveAgentsFromList(allAgentsList);

    return { activeAgents, allAgents: allAgentsList };
  },
);
```

### Frontmatter 字段

`parseAgentFromMarkdown()` 解析以下 frontmatter 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string (必填) | agent 类型名 |
| `description` | string (必填) | 何时使用此 agent |
| `tools` | string[] | 允许的工具列表，`['*']` 为全部 |
| `disallowedTools` | string[] | 禁止的工具 |
| `model` | string | 模型，`'inherit'` 继承父模型 |
| `permissionMode` | string | 权限模式 |
| `background` | boolean | 是否强制后台执行 |
| `maxTurns` | number | 最大轮次 |
| `memory` | 'user'/'project'/'local' | 持久记忆作用域 |
| `isolation` | 'worktree' | 隔离模式 |
| `mcpServers` | array | agent 专属 MCP 服务器 |
| `hooks` | object | session 作用域的 hooks |
| `skills` | string[] | 预加载的 skill 名 |
| `color` | string | UI 颜色 |
| `effort` | string/number | 努力级别 |

### Agent 优先级去重

`getActiveAgentsFromList()` 按以下优先级合并 agent（后注册覆盖先注册）：

```typescript
const agentGroups = [
  builtInAgents,    // 1. 内置（最低优先级）
  pluginAgents,     // 2. 插件
  userAgents,       // 3. 用户设置
  projectAgents,    // 4. 项目设置
  flagAgents,       // 5. CLI 标志
  managedAgents,    // 6. 策略管理（最高优先级）
];
```

### JSON Agent 定义

除了 markdown，还支持通过 JSON 定义 agent（`parseAgentFromJson()`），主要用于 SDK/API 场景。

## 三、Agent 的生命周期

### 完整生命周期

```
创建 → 初始化 → 执行 → 完成 → 清理
  │        │        │       │       │
  │    构建 system  │    收集结果  │   清理 MCP
  │    prompt      │    finalize  │   清理 hooks
  │    初始化 MCP   │    AgentTool │   清理文件缓存
  │    注册 hooks   │              │   清理 perfetto
  │    加载 skills  │              │   清理 todos
  │    写入 transcript             │   kill shell tasks
  │                                │
  createAgentId()          enqueueAgentNotification()
  runAgent()               completeAsyncAgent()
       │                        │
  query() 迭代 ─────────→ 通知父 agent
```

### 创建阶段

`runAgent.ts` 的 `runAgent()` 函数是执行引擎。创建阶段包括：

1. **生成 agent ID**：`createAgentId()` 或使用 override 的 ID
2. **注册 Perfetto 追踪**：用于层级可视化
3. **过滤父消息**：`filterIncompleteToolCalls()` 移除未完成的 tool call
4. **初始化 MCP 服务器**：`initializeAgentMcpServers()` 连接 agent 专属的 MCP 服务器
5. **注册 frontmatter hooks**：`registerFrontmatterHooks()` 注册 session 作用域的 hooks
6. **预加载 skills**：通过 `getSkillToolCommands()` 加载 agent frontmatter 中声明的 skills
7. **写入 transcript**：`recordSidechainTranscript()` 持久化初始消息
8. **写入 metadata**：`writeAgentMetadata()` 保存 agent 类型和 worktree 路径

### 执行阶段

核心执行通过 `query()` 函数的异步迭代完成：

```typescript
// runAgent.ts 第 ~430-460 行
for await (const message of query({
  messages: initialMessages,
  systemPrompt: agentSystemPrompt,
  userContext: resolvedUserContext,
  systemContext: resolvedSystemContext,
  canUseTool,
  toolUseContext: agentToolUseContext,
  querySource,
  maxTurns: maxTurns ?? agentDefinition.maxTurns,
})) {
  // 记录新消息到 transcript
  await recordSidechainTranscript([message], agentId, lastRecordedUuid);
  yield message;
}
```

每条消息都会被记录到 sidechain transcript，用于后续的 resume。

### 清理阶段

`runAgent()` 的 `finally` 块执行全面清理：

```typescript
finally {
  await mcpCleanup();                        // 清理 agent 专属 MCP 服务器
  clearSessionHooks(rootSetAppState, agentId); // 清理 session hooks
  cleanupAgentTracking(agentId);              // 清理 prompt cache 追踪
  agentToolUseContext.readFileState.clear();   // 释放文件状态缓存
  initialMessages.length = 0;                  // 释放 fork 上下文消息
  unregisterPerfettoAgent(agentId);           // 释放 Perfetto 追踪
  clearAgentTranscriptSubdir(agentId);        // 释放 transcript 子目录映射
  // 清理 todos
  rootSetAppState(prev => {
    const { [agentId]: _removed, ...todos } = prev.todos;
    return { ...prev, todos };
  });
  killShellTasksForAgent(agentId, ...);        // kill 后台 shell 任务
}
```

## 四、Agent 间通信协议

### SendMessage 工具

Agent 间通信通过 `SendMessageTool` 实现，支持三种消息类型：

1. **点对点消息**：`to: "agent-name"` — 发送到指定 agent 的 mailbox
2. **广播消息**：`to: "*"` — 发送给团队所有成员
3. **结构化消息**：shutdown_request / shutdown_response / plan_approval_response

### Mailbox 机制

消息通过文件系统 mailbox 传递：

```typescript
await writeToMailbox(recipientName, {
  from: senderName,
  text: content,
  summary,
  timestamp: new Date().toISOString(),
  color: senderColor,
}, teamName);
```

### 对正在运行的 agent 发消息

SendMessage 还支持直接向正在运行的子 agent 发送消息（无需团队上下文）：

```typescript
// SendMessageTool.ts 第 ~280-300 行
const registered = appState.agentNameRegistry.get(input.to);
const agentId = registered ?? toAgentId(input.to);
if (agentId) {
  const task = appState.tasks[agentId];
  if (isLocalAgentTask(task) && !isMainSessionTask(task)) {
    if (task.status === 'running') {
      queuePendingMessage(agentId, input.message, ...);
      // 消息在下一个工具轮次被消费
    } else {
      // agent 已停止 — 自动恢复
      await resumeAgentBackground({ agentId, prompt: input.message, ... });
    }
  }
}
```

### 广播协议

广播消息遍历 team file 中的所有成员（跳过发送者自己）：

```typescript
for (const member of teamFile.members) {
  if (member.name.toLowerCase() === senderName.toLowerCase()) continue;
  recipients.push(member.name);
  await writeToMailbox(member.name, { ... }, teamName);
}
```

## 五、团队模式

### TeamCreate / TeamDelete

团队通过 `TeamCreateTool` 创建，`TeamDeleteTool` 删除。团队信息持久化在 team file 中。

### Teammate 系统 prompt 附加

当 agent 以 teammate 模式运行时，system prompt 末尾附加通信指令：

```
# Agent Teammate Communication

IMPORTANT: You are running as an agent in a team. To communicate with anyone on your team:
- Use the SendMessage tool with `to: "<name>"` to send messages to specific teammates
- Use the SendMessage tool with `to: "*"` sparingly for team-wide broadcasts

Just writing a response in text is not visible to others on your team - you MUST use the SendMessage tool.
```

### Spawning Teammate

团队成员的创建通过 `spawnMultiAgent.ts` 的 `spawnTeammate()` 函数。支持三种后端：

1. **In-process**：在同一 Node.js 进程中运行，通过 AsyncLocalStorage 隔离
2. **Tmux split-pane**：在 tmux 窗口中创建分屏
3. **Tmux separate window**：为每个 teammate 创建独立窗口

### 团队生命周期管理

团队支持 shutdown 协议——lead 可以请求 teammate 关闭，teammate 可以批准或拒绝：

```
Lead ──shutdown_request──→ Teammate
Lead ←──shutdown_response── Teammate (approve/reject)
```

以及 plan 审批协议：

```
Teammate ──plan──→ Lead
Teammate ←──plan_approval_response── Lead (approve/reject + feedback)
```

## 六、Agent 记忆系统

### 三种作用域

通过 frontmatter 的 `memory` 字段启用持久记忆：

```typescript
export type AgentMemoryScope = 'user' | 'project' | 'local'
```

| 作用域 | 路径 | 共享范围 |
|--------|------|---------|
| user | `~/.claude/agent-memory/<agent>/` | 跨项目，用户私有 |
| project | `.claude/agent-memory/<agent>/` | 项目内，VCS 共享 |
| local | `.claude/agent-memory-local/<agent>/` | 项目内，不入 VCS |

### 记忆加载

`loadAgentMemoryPrompt()` 在 agent 的 system prompt 末尾注入记忆内容：

```typescript
export function loadAgentMemoryPrompt(agentType: string, scope: AgentMemoryScope): string {
  const memoryDir = getAgentMemoryDir(agentType, scope);
  void ensureMemoryDirExists(memoryDir);
  return buildMemoryPrompt({
    displayName: 'Persistent Agent Memory',
    memoryDir,
    extraGuidelines: [scopeNote],
  });
}
```

### 记忆快照

`agentMemorySnapshot.ts` 支持将 agent 记忆从项目快照初始化，以及检测是否有更新的快照可用。

### memory + tools 自动注入

当 agent 启用 memory 且限制了 tools 列表时，系统自动注入 Write/Edit/Read 工具：

```typescript
if (isAutoMemoryEnabled() && memory && tools !== undefined) {
  const toolSet = new Set(tools);
  for (const tool of [FILE_WRITE_TOOL_NAME, FILE_EDIT_TOOL_NAME, FILE_READ_TOOL_NAME]) {
    if (!toolSet.has(tool)) {
      tools = [...tools, tool];
    }
  }
}
```

## 七、Agent 恢复（Resume）

### 恢复机制

`resumeAgent.ts` 的 `resumeAgentBackground()` 支持恢复已停止的 agent：

1. 从磁盘读取 transcript（消息历史）
2. 读取 agent metadata（agentType, worktreePath, description）
3. 过滤无效消息（空白 assistant、未解析的 tool_use、孤立 thinking）
4. 重建 content replacement state（prompt cache 稳定性）
5. 用新的 user message 续写

```typescript
const resumedMessages = filterWhitespaceOnlyAssistantMessages(
  filterOrphanedThinkingOnlyMessages(
    filterUnresolvedToolUses(transcript.messages),
  ),
);
```

恢复时可以检测原始 worktree 是否仍然存在，如果已删除则 fallback 到父目录。

## 小结

Claude Code 的 Agent 生态系统展现了几个核心设计原则：

1. **分层架构**：内置 → 插件 → 用户 → 项目 → 策略，逐层覆盖
2. **约束即能力**：通过 disallowedTools 和只读 prompt 限制 agent 行为，反而提高了特定任务的可靠性
3. **Token 经济**：Explore/Plan 跳过 CLAUDE.md 和 gitStatus，每周节省数十 Gtok
4. **通信原语**：mailbox + SendMessage 提供了轻量级的 agent 间通信
5. **生命周期完整性**：从创建到清理，每个资源都有对应的释放逻辑
