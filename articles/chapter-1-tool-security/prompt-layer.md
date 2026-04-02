# Prompt 层的安全设计：Claude Code BashTool 的"第一道防线"

> 当你在 Claude Code 里输入 `rm -rf /`，你会看到什么？不是冰冷的拒绝，而是一个**精心设计的 prompt**——它引导模型"优先用 Edit 而不是 sed"、"不要跳过 git hooks"、"在沙箱里运行"。这篇文章拆解 BashTool 的 prompt 设计，看看 Anthropic 是如何用"文字"构建第一道安全防线的。

---

## 一、Prompt 的完整结构：三层设计

BashTool 的 prompt（`src/tools/BashTool/prompt.ts`）是一个典型的"三层蛋糕"结构：

```
┌─────────────────────────────────────────┐
│  第一层：工具描述 + 偏好链               │  ← 告诉模型"用什么工具"
│  Executes a given bash command...        │
│  Read files: Use Read (NOT cat)          │
│  Edit files: Use Edit (NOT sed)          │
├─────────────────────────────────────────┤
│  第二层：使用指令 + 命令约束              │  ← 告诉模型"怎么用"
│  - 使用绝对路径保持 cwd                  │
│  - 独立命令并行，依赖命令 && 链接         │
│  - sleep N (N≥2) 被禁止                  │
├─────────────────────────────────────────┤
│  第三层：Git 安全协议 + 沙箱指令          │  ← 告诉模型"什么不能做"
│  NEVER skip hooks (--no-verify)          │
│  NEVER force push to main/master         │
│  NEVER update git config                 │
│  沙箱模式的详细使用规则                    │
└─────────────────────────────────────────┘
```

这个结构不是随意排列的。第一层是**最常被触发的规则**（每个 bash 调用都需要检查是否应该用专用工具替代），放在最前面可以最大化 attention 权重。第三层是最危险的操作保护（git 破坏性操作、沙箱绕过），放在最后但用 `NEVER` 和 `IMPORTANT` 等大写强调词强化。

### 1.1 激活函数：`getSimplePrompt()`

整个 prompt 通过 `getSimplePrompt()` 动态生成。这不是一个静态字符串——它根据以下条件动态组装：

- **是否内嵌搜索工具**（`hasEmbeddedSearchTools()`）：如果是，跳过 Glob/Grep 的偏好链（因为 ant 版本已内嵌 bfs/ugrep）
- **是否禁用后台任务**（`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`）：决定是否包含 `run_in_background` 指令
- **沙箱是否启用**（`SandboxManager.isSandboxingEnabled()`）：决定是否包含沙箱指令块
- **Git 指令是否启用**（`shouldIncludeGitInstructions()`）：决定是否包含 Git 安全协议

这种动态组装的设计意味着：**同一个"工具"在不同环境下，给模型看到的 prompt 是不同的**。这是一个非常重要的 design pattern——prompt 不是一次性的工程，而是一个根据上下文条件变化的"活"系统。

---

## 二、偏好链设计：用"更好体验"引导模型

BashTool prompt 最精妙的设计之一是**偏好链（Preference Chain）**：

```typescript
const toolPreferenceItems = [
  ...(embedded ? [] : [
    'File search: Use Glob (NOT find or ls)',
    'Content search: Use Grep (NOT grep or rg)',
  ]),
  'Read files: Use Read (NOT cat/head/tail)',
  'Edit files: Use Edit (NOT sed/awk)',
  'Write files: Use Write (NOT echo >/cat <<EOF)',
  'Communication: Output text directly (NOT echo/printf)',
]
```

这段 prompt 的关键在于**措辞策略**：

1. **"NOT" 全大写** — 视觉上强化了"不要这样做"的信号
2. **提供正向替代** — 不只是说"别用 sed"，而是说"用 Edit"，给了模型一个明确的行动指引
3. **用"用户体验"而非"安全"作为理由** — `"better user experience" and "make it easier to review tool calls and give permission"`。这不是说"sed 不安全"，而是说"Edit 更好用"。这非常聪明：模型的训练数据中，"安全"可能会触发过度保守的行为，而"更好的体验"是一个更精确的引导。

### 2.1 偏好链背后的权力机制

值得注意的是，这个偏好链**没有强制力**。它只是"建议"。模型完全可以选择用 `sed` 而不用 `Edit`。那安全怎么保证？

答案是：**代码层有独立的兜底机制**（详见 code-layer.md）。`sedEditParser.ts` 会检查 sed 命令是否可以用 Edit 替代；`sedValidation.ts` 会对 sed 的危险操作（w/W/e/E 命令）进行白名单验证。

这就是 **"Prompt 引导 + Code 兜底"** 的核心设计哲学：prompt 让模型"想"用安全的方式，code 确保即使模型"不想"，也跑不出去。

---

## 三、Git 安全协议：从"NEVER"到"几乎不可能"

Git 相关的 prompt 指令是 BashTool 中**最详细的子系统**。它被分为两个层级：

### 3.1 简版（`getSimplePrompt` 中的 Git 子项）

在主 prompt 的 `# Instructions` 部分，有简短的三条 Git 约束：

```typescript
const gitSubitems = [
  'Prefer to create a new commit rather than amending an existing commit.',
  'Before running destructive operations (e.g., git reset --hard, git push --force, git checkout --), consider whether there is a safer alternative.',
  'Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, -c commit.gpgsign=false) unless the user explicitly asked for it.',
]
```

### 3.2 详细版（`getCommitAndPRInstructions`）

当用户要求创建 commit 时，prompt 会注入完整的 Git 提交流程指引，包含**七条 NEVER 规则**：

```
Git Safety Protocol:
- NEVER update the git config
- NEVER run destructive git commands (push --force, reset --hard, checkout ., restore ., clean -f, branch -D) unless explicitly requested
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless explicitly requested
- NEVER run force push to main/master, warn the user if they request it
- CRITICAL: Always create NEW commits rather than amending
- prefer adding specific files by name rather than "git add -A"
- NEVER commit changes unless the user explicitly asks
```

这里的 `NEVER` 用得非常精确。注意它不是说"不要"或"避免"，而是"NEVER"——这是 prompt engineering 中最强的否定语气词。配合"unless explicitly requested by the user"的例外条件，形成了一个安全的引导框架。

### 3.3 版本差异：外部用户 vs 内部用户

`getCommitAndPRInstructions()` 函数展示了 Anthropic 的一个内部策略：

- **外部用户**：完整的 inline Git 指令（详细的提交流程、PR 创建模板、HEREDOC 格式示例）
- **内部用户（ant）**：简短版，指向 `/commit` 和 `/commit-push-pr` skills

这反映了一个深层理念：**安全 prompt 不是"一刀切"的**。外部用户面对未知仓库环境，需要更多引导；内部用户使用标准 workflow，简化指令反而减少 token 消耗。

---

## 四、沙箱模式的 Prompt 设计：从"默认安全"到"优雅降级"

沙箱模式的 prompt 是 BashTool 中最具创新性的部分：

```typescript
function getSimpleSandboxSection(): string {
  // ...获取沙箱配置...
  return [
    '## Command sandbox',
    'By default, your command will be run in a sandbox.',
    'The sandbox has the following restrictions:',
    restrictionsLines.join('\n'),
    // ...详细的沙箱使用规则...
  ].join('\n')
}
```

### 4.1 动态配置注入

沙箱配置不是写死的——它通过 `SandboxManager` 获取实际的文件系统和网络限制，然后注入到 prompt 中：

```typescript
const filesystemConfig = {
  read: { denyOnly: dedup(fsReadConfig.denyOnly) },
  write: { allowOnly: normalizeAllowOnly(fsWriteConfig.allowOnly) },
}
const networkConfig = {
  allowedHosts: dedup(networkRestrictionConfig.allowedHosts),
}
```

这里有个细节值得注意：`dedup()` 函数。注释说得很清楚——"SandboxManager merges config from multiple sources without deduping"，所以 prompt 中需要手动去重。**一个去重操作就节省了 ~150-200 tokens/request**。这说明 Anthropic 在 prompt 设计时是精确计算过 token 消耗的。

### 4.2 降级策略

沙箱 prompt 有两种模式：

**允许降级模式**（`allowUnsandboxedCommands === true`）：
```
Do NOT attempt to set `dangerouslyDisableSandbox: true` unless:
  - The user *explicitly* asks you to bypass sandbox
  - A specific command just failed AND you see evidence of sandbox restrictions

When you see evidence of sandbox-caused failure:
  - Immediately retry with `dangerouslyDisableSandbox: true` (don't ask, just do it)
  - Briefly explain what sandbox restriction likely caused the failure
```

**禁止降级模式**（`allowUnsandboxedCommands === false`）：
```
All commands MUST run in sandbox mode - the `dangerouslyDisableSandbox` parameter is disabled by policy.
Commands cannot run outside the sandbox under any circumstances.
```

这是一个很好的对比：同样是一个"安全"特性，在不同环境下的 prompt 策略完全不同。允许模式使用"条件触发 + 立即重试"的策略（`don't ask, just do it`）——这意味着沙箱失败时不需要额外的用户交互，提升体验。禁止模式则使用了绝对化的措辞（`MUST`、`under any circumstances`），传达出"这不是体验优化，而是政策要求"。

### 4.3 安全路径保护

一个容易忽略但很重要的细节：

```
Do not suggest adding sensitive paths like ~/.bashrc, ~/.zshrc, ~/.ssh/*, or credential files to the sandbox allowlist.
```

这行 prompt 直接防止了模型"建议把敏感路径加入白名单"的行为。如果没有这行，一个好奇的模型可能会建议："既然沙箱阻止了 ~/.ssh 的访问，我们把它加到白名单吧？"——这会直接破坏安全边界。

---

## 五、与其他工具 Prompt 的对比

### 5.1 PowerShellTool vs BashTool

PowerShellTool 的 prompt（`src/tools/PowerShellTool/prompt.ts`）和 BashTool 有几个关键差异：

1. **版本感知**：PowerShell prompt 区分 Windows PowerShell 5.1 和 PowerShell 7+，给出不同的语法指导（如 `&&` 只在 7+ 可用）。BashTool 没有类似的版本区分。

2. **工具偏好链**：PowerShell 的偏好链是统一的一句话："DO NOT use it for file operations"，而 BashTool 是逐条列出 Read>cat, Edit>sed 等。

3. **安全指令**：PowerShell prompt 的安全指令更少——没有 Git 安全协议、没有 sleep 约束、没有沙箱说明。这可能是因为 PowerShell 主要用于 Windows 环境，攻击面不同。

### 5.2 FileEditTool vs BashTool

FileEditTool 的 prompt（`src/tools/FileEditTool/prompt.ts`）展示了另一种设计思路：

```
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- The edit will FAIL if `old_string` is not unique in the file.
```

注意这里的 `FAIL`——FileEditTool 不是说"建议这样做"，而是说"如果你不这样做，工具会**失败**"。这是 prompt + code 配合的另一种形式：prompt 告诉模型"失败"的后果，code 实际执行检查。

### 5.3 设计模式总结

| 维度 | BashTool | PowerShellTool | FileEditTool |
|------|----------|----------------|--------------|
| 安全引导方式 | 偏好链 + NEVER 规则 | 版本感知 + 语法指导 | 失败后果警告 |
| 破坏性操作保护 | Git 协议 + 沙箱 | 无显式保护 | 隐式（工具会 FAIL） |
| Token 效率优化 | dedup, 动态组装 | 静态 | 静态 |
| 降级策略 | 条件触发 | 无 | 无 |

---

## 六、设计洞察

### 6.1 "提示即代码"的思维

BashTool 的 prompt 不是在写"文档"——它是在写"规范"。每一行都有明确的行为目标：

- `"Avoid using this tool to run find, grep, cat..."` → 减少 bash 调用频率
- `"NEVER skip hooks"` → 防止 Git 安全绕过
- `"sleep N (N≥2) is blocked"` → 防止无限等待（注意这里用了 "blocked"，暗示 code 层有实际拦截）

### 6.2 Token 预算是第一公民

`dedup()` 的存在、条件化组装（只在沙箱启用时注入沙箱 prompt）、内嵌搜索工具时跳过 Glob/Grep 偏好——这些都是 token 预算优化的体现。在 LLM 应用中，**prompt 的长度不是"写多少就行"，而是要精确计算每一个 token 的投入产出比**。

### 6.3 安全 vs 体验的平衡

沙箱模式的降级策略是最好的例子。纯粹的安全设计会让模型在沙箱失败时停下来问用户；而 Anthropic 选择让它"立即重试"（`don't ask, just do it`），同时要求它"简要解释失败原因"。这是一个**以用户体验为优先的安全设计**——安全是必须的，但不应该成为用户完成任务的障碍。

---

*下一篇我们将深入代码层，看看当 prompt 的"建议"失效时，代码是如何兜底的。*
