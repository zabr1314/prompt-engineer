# Claude Code 多 Agent 编排（三）：编排设计模式

> 从派发到回收的完整流程分析，深入探讨前台/后台管理、记忆传递、对抗性编排，以及对其他多 agent 系统的设计启示。

## 架构全景：从派发到结果回收

```
主 Agent (Main Loop)
    │
    │  Agent({ prompt, subagent_type, run_in_background })
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│                   AgentTool.call()                         │
│                                                           │
│  1. 解析参数 → 确定策略 (spawn/fork/teammate)             │
│  2. 查找 AgentDefinition                                  │
│  3. 构建 system prompt / forked messages                  │
│  4. 组装 worker 工具池                                     │
│  5. 决定 sync/async                                       │
│                                                           │
│  ┌─────────────────┐     ┌─────────────────────────────┐ │
│  │  同步路径         │     │  异步路径                     │ │
│  │  registerAgent-  │     │  registerAsyncAgent()        │ │
│  │  Foreground()    │     │  void runAsyncAgent-         │ │
│  │                  │     │  Lifecycle()                 │ │
│  │  for await {     │     │                              │ │
│  │    agentIterator │     │  返回 async_launched         │ │
│  │    .next()       │     │  后台执行...                  │ │
│  │  }               │     │  → enqueueAgentNotification  │ │
│  │                  │     │                              │ │
│  │  可随时转后台 ─────┼──→ │                              │ │
│  └─────────────────┘     └─────────────────────────────┘ │
│                                                           │
│  6. finalizeAgentTool() → 收集结果                        │
│  7. classifyHandoffIfNeeded() → 安全分类                   │
│  8. 返回 tool_result 给主 agent                           │
└───────────────────────────────────────────────────────────┘
    │
    │  tool_result: { content, agentId, usage, ... }
    │
    ▼
主 Agent 继续执行（总结子 agent 结果给用户）
```

## 一、前台 vs 后台 Agent 的管理

### 前台 Agent

前台 agent 阻塞主 agent 的执行，直到完成。它们通过 `registerAgentForeground()` 注册到 task 系统：

```typescript
// AgentTool.tsx 第 ~490-500 行
const registration = registerAgentForeground({
  agentId: syncAgentId,
  description,
  prompt,
  selectedAgent,
  setAppState: rootSetAppState,
  toolUseId: toolUseContext.toolUseId,
  autoBackgroundMs: getAutoBackgroundMs() || undefined,
});
foregroundTaskId = registration.taskId;
backgroundPromise = registration.backgroundSignal;
```

前台 agent 有一个精妙的设计：**可以随时被转为后台**。通过 `Promise.race` 实现：

```typescript
const raceResult = backgroundPromise
  ? await Promise.race([
      nextMessagePromise.then(r => ({ type: 'message', result: r })),
      backgroundPromise  // 用户触发 backgroundAll() 时 resolve
    ])
  : { type: 'message', result: await nextMessagePromise };

if (raceResult.type === 'background' && foregroundTaskId) {
  // 转后台：重新启动异步执行
  void runWithAgentContext(syncAgentContext, async () => {
    for await (const msg of runAgent({ ...runAgentParams, isAsync: true })) {
      // 后台迭代...
    }
  });
  return { data: { status: 'async_launched', ... } };
}
```

### 后台 Agent

后台 agent 在独立的执行上下文中运行，不阻塞主 agent：

1. **独立的 AbortController**：不与父 agent 共享，ESC 键不会 kill 后台 agent
2. **通过 notification 回报**：`enqueueAgentNotification()` 将结果作为 user message 插入主循环
3. **可通过 chat:killAgents 显式终止**

### 自动后台化

系统支持自动将长时间运行的前台 agent 转为后台：

```typescript
function getAutoBackgroundMs(): number {
  if (isEnvTruthy(process.env.CLAUDE_AUTO_BACKGROUND_TASKS) ||
      getFeatureValue_CACHED_MAY_BE_STALE('tengu_auto_background_agents', false)) {
    return 120_000;  // 2 分钟后自动转后台
  }
  return 0;
}
```

### 后台 hint UI

前台 agent 运行超过 2 秒后，显示"可转后台"的提示：

```typescript
if (!backgroundHintShown && elapsed >= PROGRESS_THRESHOLD_MS && toolUseContext.setToolJSX) {
  backgroundHintShown = true;
  toolUseContext.setToolJSX({
    jsx: <BackgroundHint />,
    shouldHidePromptInput: false,
    shouldContinueAnimation: true,
    showSpinner: true,
  });
}
```

## 二、Agent 记忆和上下文传递

### 三种上下文传递模式

```
模式 1: Spawn（独立上下文）
┌─────────────┐     ┌─────────────┐
│   父 Agent    │     │   子 Agent    │
│  [msg1,msg2,  │     │  [user_msg:  │
│   msg3,tool_  │ ──→ │   "搜索X"]    │
│   use,result] │     │              │
│              │     │  零历史       │
└─────────────┘     └─────────────┘

模式 2: Fork（共享上下文 + 占位 results）
┌─────────────┐     ┌─────────────┐
│   父 Agent    │     │  Fork Worker  │
│  [msg1,msg2,  │     │  [msg1,msg2,  │
│   assistant:  │     │   assistant:  │
│   tool_use_1, │ ──→ │   tool_use_1, │
│   tool_use_2] │     │   tool_use_2, │
│              │     │   user:       │
│              │     │   [result_1:  │
│              │     │    "placeholder",│
│              │     │    result_2:  │
│              │     │    "placeholder",│
│              │     │    directive] │
└─────────────┘     └─────────────┘

模式 3: Teammate（独立进程 + mailbox 通信）
┌─────────────┐     ┌─────────────┐
│   父 Agent    │     │  Teammate    │
│  独立进程     │     │  独立进程     │
│              │     │              │
│  mailbox ─────┼──→ │ inbox poller │
│              │     │              │
│  mailbox ←────┼─── │ SendMessage  │
└─────────────┘     └─────────────┘
```

### Fork 的 Cache 优化工程

Fork 模式在上下文传递上做了极致的工程优化。核心目标是**让所有 fork 子 worker 的 API 请求前缀字节级相同**。

在 `runAgent.ts` 中，`useExactTools: true` 触发了一系列 cache 友好行为：

```typescript
// runAgent.ts 第 ~310 行
const resolvedTools = useExactTools
  ? availableTools  // 直接使用父 agent 的工具数组（不重新过滤/排序）
  : resolveAgentTools(agentDefinition, availableTools, isAsync).resolvedTools;

// runAgent.ts 第 ~325-330 行
thinkingConfig: useExactTools
  ? toolUseContext.options.thinkingConfig  // 继承父 agent 的 thinking 配置
  : { type: 'disabled' },                 // 普通子 agent 禁用 thinking

isNonInteractiveSession: useExactTools
  ? toolUseContext.options.isNonInteractiveSession  // 继承
  : isAsync ? true : (toolUseContext.options.isNonInteractiveSession ?? false),
```

这意味着 fork 子 worker 的 system prompt、工具定义、thinking 配置都与父 agent 完全一致，只有最后的 user message 不同。

### Sidechain Transcript

每个子 agent 的消息被记录到 sidechain transcript，用于 resume：

```typescript
// runAgent.ts 第 ~400-410 行
void recordSidechainTranscript(initialMessages, agentId).catch(...);

// runAgent.ts 第 ~445-455 行（执行循环中）
for await (const message of query(...)) {
  await recordSidechainTranscript([message], agentId, lastRecordedUuid);
  if (message.type !== 'progress') {
    lastRecordedUuid = message.uuid;
  }
  yield message;
}
```

消息以 UUID 链表形式存储，`lastRecordedUuid` 确保父子关系正确。

## 三、Verification Agent 的对抗性编排

### 编排模式

Verification agent 代表了一种"对抗性编排"模式——不是让 agent 协作，而是让一个 agent 故意挑战另一个 agent 的成果。

```
用户: "实现一个登录 API"
    │
    ▼
主 Agent: 实现代码 ──→ 完成
    │
    │  spawn verification agent
    │  prompt: 原始任务描述 + 改动文件 + 实现方法
    │
    ▼
Verification Agent:
  1. 构建项目（检查是否编译通过）
  2. 运行测试（检查是否测试通过）
  3. 运行 linter
  4. 对抗性探测（并发、边界值、幂等性）
  5. 输出 VERDICT: PASS/FAIL/PARTIAL
    │
    ▼
主 Agent: 根据 VERDICT 决定是否修改
```

### Verification 的约束设计

Verification agent 通过多重约束确保"真正验证"：

1. **禁止修改项目**：`disallowedTools` 包含 FileEdit、FileWrite 等
2. **强制执行命令**：每个 check 必须有 `Command run:` 和 `Output observed:`
3. **强制对抗性探测**：必须包含至少一个对抗性测试
4. **防止被前 80% 迷惑**：prompt 明确识别了这个 LLM 失败模式
5. **结果可审计**：主 agent 可以 spot-check verification 的命令输出

### criticalSystemReminder 机制

Verification agent 使用 `criticalSystemReminder_EXPERIMENTAL` 字段，这个字段会在**每个 user turn** 被重新注入：

```typescript
// loadAgentsDir.ts 中定义
criticalSystemReminder_EXPERIMENTAL:
  'CRITICAL: This is a VERIFICATION-ONLY task. You CANNOT edit, write, or files IN THE PROJECT DIRECTORY...'
```

这防止 agent 在长对话中"忘记"自己的约束。

## 四、工具过滤与权限隔离

### 分层过滤

子 agent 的工具池经过多层过滤：

```typescript
// agentToolUtils.ts 的 filterToolsForAgent()
export function filterToolsForAgent({ tools, isBuiltIn, isAsync, permissionMode }) {
  return tools.filter(tool => {
    // 1. MCP 工具始终允许
    if (tool.name.startsWith('mcp__')) return true;
    
    // 2. ExitPlanMode 仅在 plan 模式允许
    if (toolMatchesName(tool, EXIT_PLAN_MODE_V2_TOOL_NAME) && permissionMode === 'plan') return true;
    
    // 3. 全局禁止列表（所有 agent）
    if (ALL_AGENT_DISALLOWED_TOOLS.has(tool.name)) return false;
    
    // 4. 自定义 agent 额外禁止列表
    if (!isBuiltIn && CUSTOM_AGENT_DISALLOWED_TOOLS.has(tool.name)) return false;
    
    // 5. 异步 agent 的工具白名单
    if (isAsync && !ASYNC_AGENT_ALLOWED_TOOLS.has(tool.name)) {
      // 特殊：进程内 teammate 允许 Agent 和 task 工具
      if (isAgentSwarmsEnabled() && isInProcessTeammate()) {
        if (toolMatchesName(tool, AGENT_TOOL_NAME)) return true;
        if (IN_PROCESS_TEAMMATE_ALLOWED_TOOLS.has(tool.name)) return true;
      }
      return false;
    }
    return true;
  });
}
```

### 权限模式继承

子 agent 的权限模式可以独立于父 agent：

```typescript
// runAgent.ts 第 ~295-310 行
const agentPermissionMode = agentDefinition.permissionMode;
if (agentPermissionMode &&
    state.toolPermissionContext.mode !== 'bypassPermissions' &&
    state.toolPermissionContext.mode !== 'acceptEdits') {
  toolPermissionContext = { ...toolPermissionContext, mode: agentPermissionMode };
}
```

父 agent 在 `bypassPermissions` 或 `acceptEdits` 模式时，子 agent 的权限模式不会被覆盖——安全的"向下兼容"。

### 异步 agent 的权限处理

异步 agent 不能显示 UI，所以权限提示自动被拒绝：

```typescript
const shouldAvoidPrompts = agentPermissionMode === 'bubble' ? false : isAsync;
if (shouldAvoidPrompts) {
  toolPermissionContext = {
    ...toolPermissionContext,
    shouldAvoidPermissionPrompts: true,
  };
}
```

但 `bubble` 模式是个例外——它会将权限提示冒泡到父终端显示。

## 五、对其他多 Agent 系统的设计启示

### 1. 分层约束优于全局约束

Claude Code 的工具过滤是分层的：全局禁止 → agent 类型禁止 → agent 实例禁止。这比"给所有 agent 相同工具集"更灵活。

**启示**：设计多 agent 系统时，应该支持多层约束，让每个 agent 只拥有完成任务所需的最小工具集。

### 2. Token 经济应该是架构级别的考虑

Explore agent 跳过 CLAUDE.md（省 5-15 Gtok/周），跳过 gitStatus（省 40KB/次），使用 haiku 模型。这些不是小优化——在数千万次调用的规模下，它们决定了系统的经济可行性。

**启示**：设计 agent prompt 时，认真考虑每个 token 的必要性。只读 agent 不需要编辑相关的上下文。

### 3. 对抗性验证是必需的

Verification agent 的存在说明了一个重要观点：**LLM 实现者的自我验证不可靠**。Prompt 中精确识别了"验证回避"和"被前 80% 迷惑"两个 LLM 固有弱点。

**启示**：任何严肃的多 agent 系统都应该有独立的验证 agent，而且验证 agent 的 prompt 需要对抗 LLM 的固有行为模式。

### 4. Prompt Cache 共享是 Fork 的核心价值

Fork 模式的所有工程复杂性（占位 tool_result、useExactTools、继承 thinkingConfig）都服务于一个目标：**让 API 请求前缀字节级相同**。这不是锦上添花——这是 fork 比 spawn 便宜的根本原因。

**启示**：如果你的多 agent 系统需要并行执行相似任务，投入工程让它们共享 prompt cache 是值得的。

### 5. 生命周期完整性防止资源泄漏

`runAgent.ts` 的 `finally` 块清理了 8 种资源：MCP 连接、hooks、文件缓存、Perfetto 追踪、transcript 映射、todos、shell 任务、monitor 任务。每一种都对应一个潜在的泄漏路径。

**启示**：多 agent 系统中，每个 agent 的创建都必须对应完整的清理。遗漏任何一种资源清理都会在长时间运行的系统中累积。

### 6. 通信应该是显式的

Teammate 的 system prompt 附加了明确的通信指令："Just writing a response in text is not visible to others on your team - you MUST use the SendMessage tool." 这种显式声明比隐式假设可靠得多。

**启示**：agent 间通信协议应该在 prompt 中显式声明，不要假设 agent 会自然地发现通信方式。

## 六、可复用的编排模式总结

### 模式 1：Worker Pool

```
主 Agent → spawn N 个相同类型的 agent（并行）
         → 收集所有结果
         → 合并/总结
```

**Claude Code 实现**：在一条消息中发送多个 Agent tool_use 块，每个 fork 一个独立调研任务。

### 模式 2：Pipeline

```
Agent A → 结果 → Agent B → 结果 → Agent C
```

**Claude Code 实现**：主 agent 先 spawn Explore（搜索），再 spawn Plan（规划），最后自己实现。

### 模式 3：Supervisor-Worker

```
主 Agent（supervisor）
  ├→ Worker 1（实现模块 A）
  ├→ Worker 2（实现模块 B）
  └→ Worker 3（测试）
```

**Claude Code 实现**：Team 模式，lead agent 通过 SendMessage 分配任务给 teammates。

### 模式 4：Adversarial

```
Agent A（实现）→ 成果 → Agent B（验证）→ VERDICT → Agent A（修复）
```

**Claude Code 实现**：主 agent 实现后 spawn verification agent，根据 VERDICT 决定是否修改。

### 模式 5：Fork-Join

```
主 Agent
  ├→ Fork 1（调研子问题 A）
  ├→ Fork 2（调研子问题 B）
  └→ Fork 3（调研子问题 C）
     ↓
  全部完成 → 主 Agent 合并结果
```

**Claude Code 实现**：省略 subagent_type 触发 fork，多个 fork 在一条消息中并行启动，通过 task notification 回收结果。

### 模式 6：Resume Chain

```
Spawn Agent → 完成 → 后续通过 SendMessage 续写
                  → 如果已停止 → 自动 resume
```

**Claude Code 实现**：SendMessage 检测到 agent 已停止时自动调用 `resumeAgentBackground()`，从 transcript 恢复执行。

## 七、工程权衡与取舍

### 同步 vs 异步

Claude Code 选择了**默认同步 + 可选异步 + 可运行中转后台**的混合模型，而非全异步。这是因为：

1. **同步更简单**：主 agent 可以直接使用子 agent 的结果
2. **异步有开销**：需要 notification 机制、transcript 持久化、resume 支持
3. **混合最灵活**：简单任务同步，复杂任务异步，长任务运行中转后台

### Fork vs Spawn

Fork 省 token 但更复杂：
- **省**：共享 prompt cache、不需要重新描述上下文
- **贵**：buildForkedMessages 的工程复杂性、递归 fork 防护、占位 tool_result 的设计

### 进程内 vs 进程外 Teammate

```
进程内（AsyncLocalStorage）：
  ✅ 低延迟（无 IPC）
  ✅ 共享内存（可读写 AppState）
  ❌ 不能独立崩溃（一个挂全挂）
  ❌ 不能有独立的后台 agent

进程外（Tmux/iTerm2）：
  ✅ 完全隔离（独立进程）
  ✅ 可以有独立后台 agent
  ❌ 通信延迟（mailbox 文件系统）
  ❌ 需要终端 multiplexer
```

## 结语

Claude Code 的多 Agent 编排系统展示了几个核心工程原则：

1. **约束即能力**：通过限制 agent 的工具和行为，反而提高了系统的可靠性
2. **Cache 是第一公民**：fork 模式的所有设计都服务于 prompt cache 共享
3. **生命周期完整性**：从创建到清理，每个资源都有对应的释放
4. **渐进复杂性**：从简单的同步 spawn，到 fork、team、resume，复杂性逐步递增
5. **对抗性思维**：verification agent 的存在说明——不要信任任何单个 agent 的自我验证

这些模式不仅适用于 Claude Code，也是构建任何多 agent 系统的可复用设计蓝图。
