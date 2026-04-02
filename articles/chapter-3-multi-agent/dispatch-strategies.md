# Claude Code 多 Agent 编排（一）：三种派发策略的实现

> 深入分析 Claude Code 的 Agent 派发机制，从源码级别拆解 spawn、fork、direct 三种策略的实现差异。

## 架构总览

Claude Code 的 Agent 工具（`AgentTool`）是整个多 Agent 系统的核心入口。在 `AgentTool.tsx` 的 `call()` 方法中，根据输入参数的不同组合，走完全不同的三条路径：

```
用户/AI 调用 Agent({ prompt, subagent_type?, ... })
           │
           ├─ team_name + name 存在 ──→ Teammate Spawn（独立进程/面板）
           │
           ├─ subagent_type 指定 ──→ Spawn 模式（独立上下文）
           │
           ├─ subagent_type 省略 + fork gate on ──→ Fork 模式（共享 cache）
           │
           └─ subagent_type 省略 + fork gate off ──→ 默认 general-purpose
```

关键决策逻辑在 `AgentTool.tsx` 第 ~280-290 行：

```typescript
const effectiveType = subagent_type ?? (isForkSubagentEnabled() ? undefined : GENERAL_PURPOSE_AGENT.agentType);
const isForkPath = effectiveType === undefined;
```

一句话总结三种策略：
- **Spawn**：`subagent_type` 指定 → 全新上下文，从零开始
- **Fork**：`subagent_type` 省略 + fork 实验开启 → 继承父上下文，共享 prompt cache
- **Direct**：不派发 Agent 工具，主 agent 自己做

## 一、Spawn 模式：独立上下文的"新员工"

### 核心特征

Spawn 模式是最传统的子 agent 派发方式。当你指定 `subagent_type: "Explore"` 时，系统会：

1. **从 agent 注册表中查找对应的 AgentDefinition**（`AgentTool.tsx` 第 ~305 行）
2. **构建全新的 system prompt**（不继承父 agent 的 prompt）
3. **创建独立的对话历史**（从空上下文开始）
4. **使用独立的工具池**（`assembleToolPool` 为 worker 单独构建）

### 关键代码路径

在 `AgentTool.tsx` 的 `call()` 方法中，spawn 路径的核心逻辑：

```typescript
// AgentTool.tsx 第 ~335-350 行
const allAgents = toolUseContext.options.agentDefinitions.activeAgents;
const found = agents.find(agent => agent.agentType === effectiveType);
if (!found) {
  throw new Error(`Agent type '${effectiveType}' not found.`);
}
selectedAgent = found;
```

找到 agent 定义后，构建独立的 system prompt：

```typescript
// AgentTool.tsx 第 ~430-450 行
const agentPrompt = selectedAgent.getSystemPrompt({ toolUseContext });
enhancedSystemPrompt = await enhanceSystemPromptWithEnvDetails(
  [agentPrompt], resolvedAgentModel, additionalWorkingDirectories
);
promptMessages = [createUserMessage({ content: prompt })];
```

注意这里的 `promptMessages` 只包含一条简单的 user message，**不包含任何父 agent 的对话历史**。这意味着 spawn 出来的 agent 完全不知道之前发生了什么——你需要在 prompt 中完整描述背景。

### 工具池隔离

Spawn 模式使用独立的工具池，由 `assembleToolPool` 在独立的 permission context 下构建：

```typescript
// AgentTool.tsx 第 ~370-375 行
const workerPermissionContext = {
  ...appState.toolPermissionContext,
  mode: selectedAgent.permissionMode ?? 'acceptEdits'
};
const workerTools = assembleToolPool(workerPermissionContext, appState.mcp.tools);
```

这意味着子 agent 的工具权限可以独立于父 agent。例如，`verification` agent 的 `permissionMode` 被设为 `'bubble'`，权限提示会冒泡到父终端显示。

### 模型选择

Spawn 模式允许通过 `model` 参数覆盖 agent 定义中的模型。模型解析逻辑在 `runAgent.ts` 的 `getAgentModel()` 中：

```typescript
// runAgent.ts 第 ~240 行
const resolvedAgentModel = getAgentModel(
  agentDefinition.model,
  toolUseContext.options.mainLoopModel,
  model,  // 用户传入的覆盖值
  permissionMode
);
```

不同 agent 有不同默认模型：
- **Explore**：外部用户默认 `haiku`（追求速度），内部 ant 使用 `inherit`
- **Plan**：默认 `inherit`（继承父模型）
- **verification**：默认 `inherit`
- **general-purpose**：不指定 model，使用子 agent 默认模型

## 二、Fork 模式：共享上下文的"分身术"

### 核心特征

Fork 模式是 Claude Code 中最精妙的设计之一。当 `subagent_type` 被省略且 fork 实验门开启时：

1. **继承父 agent 的完整对话上下文**
2. **共享 prompt cache**（API 请求前缀字节级一致）
3. **强制异步执行**（`forceAsync = true`）
4. **子 agent 禁止再 fork**（递归 fork 防护）

### Fork 的"合成 Agent"

Fork 路径使用一个特殊的合成 agent 定义 `FORK_AGENT`（`forkSubagent.ts` 第 ~60-80 行）：

```typescript
export const FORK_AGENT = {
  agentType: FORK_SUBAGENT_TYPE,  // 'fork'
  tools: ['*'],
  maxTurns: 200,
  model: 'inherit',
  permissionMode: 'bubble',
  source: 'built-in',
  baseDir: 'built-in',
  getSystemPrompt: () => '',  // 未使用 — 实际走 override.systemPrompt
} satisfies BuiltInAgentDefinition;
```

关键点：`getSystemPrompt` 返回空字符串——实际的 system prompt 通过 `override.systemPrompt` 传入父 agent 的已渲染 prompt 字节，确保 cache 一致性。

### 消息构建：`buildForkedMessages()`

这是 fork 模式的核心魔法。在 `forkSubagent.ts` 第 ~110-170 行：

```typescript
export function buildForkedMessages(
  directive: string,
  assistantMessage: AssistantMessage,
): MessageType[] {
  // 1. 克隆父 agent 的完整 assistant message（所有 tool_use 块）
  const fullAssistantMessage: AssistantMessage = {
    ...assistantMessage,
    uuid: randomUUID(),
    message: {
      ...assistantMessage.message,
      content: [...assistantMessage.message.content],
    },
  };

  // 2. 收集所有 tool_use 块
  const toolUseBlocks = assistantMessage.message.content.filter(
    (block): block is BetaToolUseBlock => block.type === 'tool_use',
  );

  // 3. 为每个 tool_use 创建占位 tool_result（全部使用相同文本）
  const toolResultBlocks = toolUseBlocks.map(block => ({
    type: 'tool_result' as const,
    tool_use_id: block.id,
    content: [{ type: 'text' as const, text: FORK_PLACEHOLDER_RESULT }],
  }));

  // 4. 组装：占位 results + 指令文本
  const toolResultMessage = createUserMessage({
    content: [
      ...toolResultBlocks,
      { type: 'text' as const, text: buildChildMessage(directive) },
    ],
  });

  return [fullAssistantMessage, toolResultMessage];
}
```

**所有 fork 子 agent 的 tool_result 占位符文本完全一致**（`"Fork started — processing in background"`），只有最后的指令文本不同。这样做的效果是：API 请求的前缀字节级相同，最大化 prompt cache 命中率。

### Fork 子 Worker 的行为约束

Fork 子 worker 收到的行为指令非常严格（`buildChildMessage()` 函数，`forkSubagent.ts` 第 ~180-215 行）：

```
1. 你是 forked worker。你不是主 agent。
2. 禁止再 spawn 子 agent
3. 禁止对话、提问、建议下一步
4. 直接使用工具，不要在工具调用之间输出文本
5. 如果修改了文件，先 commit 再报告
6. 报告以 "Scope:" 开头，500 字以内
```

### 递归 Fork 防护

系统有两层防递归机制：

1. **querySource 检查**（`AgentTool.tsx` 第 ~295 行）：检查 `toolUseContext.options.querySource` 是否为 `agent:builtin:fork`
2. **消息扫描兜底**（`forkSubagent.ts` 的 `isInForkChild()`）：扫描对话中是否包含 `<forked-worker>` 标签

```typescript
export function isInForkChild(messages: MessageType[]): boolean {
  return messages.some(m => {
    if (m.type !== 'user') return false;
    const content = m.message.content;
    if (!Array.isArray(content)) return false;
    return content.some(
      block => block.type === 'text' && block.text.includes(`<${FORK_BOILERPLATE_TAG}>`),
    );
  });
}
```

### Prompt Cache 共享的工程细节

Fork 模式在 `runAgent.ts` 中通过 `useExactTools: true` 实现工具定义的字节级一致：

```typescript
// AgentTool.tsx 第 ~460-465 行
...(isForkPath && { useExactTools: true }),
```

当 `useExactTools` 为 true 时，`runAgent.ts` 跳过 `resolveAgentTools()` 过滤，直接使用父 agent 的工具数组，并且继承父 agent 的 `thinkingConfig` 和 `isNonInteractiveSession`：

```typescript
// runAgent.ts 第 ~310 行
const resolvedTools = useExactTools
  ? availableTools
  : resolveAgentTools(agentDefinition, availableTools, isAsync).resolvedTools;
```

## 三、Direct 模式：自己动手

Direct 模式不是一个代码路径——它是一种使用模式。主 agent 选择不使用 Agent 工具，而是直接调用 Read、Write、Bash 等工具完成任务。

从编排角度看，direct 模式的优势是：
- **零派发开销**：不需要创建新 agent 上下文
- **完整上下文**：主 agent 拥有全部对话历史
- **即时反馈**：不需要等待子 agent 完成

劣势是：
- **上下文污染**：工具调用的中间结果会占用主 agent 的上下文窗口
- **无法并行**：串行执行，不能同时做多件事

## 四、同步 vs 异步执行

三种策略都可以选择同步或异步执行，决策逻辑在 `AgentTool.tsx` 第 ~380-390 行：

```typescript
const forceAsync = isForkSubagentEnabled();  // Fork 模式强制异步
const shouldRunAsync = (
  run_in_background === true ||
  selectedAgent.background === true ||
  isCoordinator ||
  forceAsync ||
  assistantForceAsync ||
  (proactiveModule?.isProactiveActive() ?? false)
) && !isBackgroundTasksDisabled;
```

**异步路径**（`shouldRunAsync === true`）：
- 注册为 `registerAsyncAgent`（独立 abort controller）
- 通过 `runAsyncAgentLifecycle` 驱动执行
- 返回 `{ status: 'async_launched', agentId, outputFile }`
- 完成后通过 `enqueueAgentNotification` 发送通知

**同步路径**（`shouldRunAsync === false`）：
- 注册为 `registerAgentForeground`（可随时转后台）
- 在当前调用栈中迭代 agent 消息
- 支持运行中转后台（`backgroundSignal` 竞态）
- 返回 `{ status: 'completed', content, ... }`

### 同步转后台的"竞态"机制

同步 agent 支持在执行中被用户转为后台。这通过 `Promise.race` 实现：

```typescript
// AgentTool.tsx 第 ~530-540 行
const raceResult = backgroundPromise
  ? await Promise.race([
      nextMessagePromise.then(r => ({ type: 'message' as const, result: r })),
      backgroundPromise
    ])
  : { type: 'message' as const, result: await nextMessagePromise };
```

当用户触发 `backgroundAll()` 时，`backgroundPromise` resolve，系统：
1. 终止当前的同步迭代器
2. 重新启动一个异步的 `runAgent` 执行
3. 返回 `async_launched` 状态

## 五、并发控制

### maxConcurrent

Claude Code 的 prompt 中明确鼓励并行派发：

```
- Launch multiple agents concurrently whenever possible, to maximize performance;
  to do that, use a single message with multiple tool uses
```

`AgentTool` 的 `isConcurrencySafe()` 返回 `true`，意味着同一轮消息中可以并行调用多个 Agent 工具。系统没有显式的 `maxConcurrent` 参数限制——并发上限由模型的工具调用能力和上下文窗口自然决定。

### 防止后台任务滥用

环境变量 `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` 可以全局禁用后台 agent：

```typescript
const isBackgroundTasksDisabled = isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS);
```

此外，进程内 teammate（in-process teammate）不能 spawn 后台 agent：

```typescript
if (isInProcessTeammate() && teamName && run_in_background === true) {
  throw new Error('In-process teammates cannot spawn background agents.');
}
```

## 六、Worktree 隔离

三种策略都支持 `isolation: "worktree"`，创建一个临时 git worktree 让 agent 在隔离的工作副本中操作：

```typescript
if (effectiveIsolation === 'worktree') {
  const slug = `agent-${earlyAgentId.slice(0, 8)}`;
  worktreeInfo = await createAgentWorktree(slug);
}
```

Fork 模式下使用 worktree 时，还会注入一条路径转换通知：

```typescript
if (isForkPath && worktreeInfo) {
  promptMessages.push(createUserMessage({
    content: buildWorktreeNotice(getCwd(), worktreeInfo.worktreePath)
  }));
}
```

agent 完成后，如果 worktree 没有变更，自动清理：

```typescript
const changed = await hasWorktreeChanges(worktreePath, headCommit);
if (!changed) {
  await removeAgentWorktree(worktreePath, worktreeBranch, gitRoot);
}
```

## 策略选择决策矩阵

| 维度 | Spawn | Fork | Direct |
|------|-------|------|--------|
| 上下文 | 独立，从零开始 | 继承父上下文 | 完整上下文 |
| Prompt Cache | 不共享 | 共享（字节级一致） | N/A |
| 执行模式 | 同步/异步 | 强制异步 | 同步 |
| 并行能力 | ✅ 多个并行 | ✅ 多个并行 | ❌ 串行 |
| 上下文污染 | 无 | 无（独立执行） | 有 |
| 适用场景 | 需要专业 agent | 可拆分的调研/实现 | 简单任务 |
| Token 开销 | 高（全新 prompt） | 低（cache 命中） | 中 |

**最佳实践**：
- 需要专业能力（Explore/Plan/verification）→ Spawn
- 可以拆分的独立调研 → Fork（便宜、快、并行）
- 简单几步行 → Direct（零开销）
