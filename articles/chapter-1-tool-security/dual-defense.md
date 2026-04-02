# 双重防线架构：Prompt 引导 + Code 兜底

> Claude Code 的安全设计不是"写好 prompt 就完事了"。它有两层完全独立的防线：Prompt 层引导模型"想做对的事"，Code 层确保即使模型"不想"，也做不了坏事。这篇文章分析这两层如何配合，以及这种设计对其他 Agent 系统的启示。

---

## 一、为什么需要双重防线？

LLM 有一个根本性的弱点：**它是概率性的**。同一段 prompt，10 次调用可能产生 10 种不同的行为。你无法通过 prompt 工程达到 100% 的行为一致性。

这意味着：

```
单靠 Prompt = 赌博
单靠 Code = 失去 LLM 的灵活性
Prompt + Code = 引导 + 兜底
```

Claude Code 的设计哲学是：**Prompt 负责"让模型倾向于做对的事"，Code 负责"即使模型做错了，也不造成实际伤害"。**

---

## 二、双重防线的具体案例

### 案例 1：sed 命令 vs Edit 工具

**Prompt 层的引导**（BashTool prompt.ts）：

```
To edit files use Edit instead of sed or awk
```

一句话，告诉模型优先用 Edit。但没有强制力——模型仍然可以选择用 sed。

**Code 层的兜底**（sedEditParser.ts + sedValidation.ts）：

```typescript
// sedEditParser.ts — 检测 sed 命令是否可以替代为 Edit
function parseSedEdit(sedCommand: string): SedEditResult | null {
  // 解析 sed 命令，提取 old_string 和 new_string
  // 如果可以替代，返回 Edit 格式的替换参数
}

// sedValidation.ts — 检查 sed 的危险操作
const DANGEROUS_SED_COMMANDS = ['w', 'W', 'e', 'E']  // 文件写入、命令执行
function validateSedCommand(sedCommand: string): ValidationResult {
  // 如果包含危险命令 → deny
  // 如果可以替代为 Edit → 建议替代
  // 否则 → passthrough
}
```

**两层配合**：
1. Prompt 让模型"想"用 Edit
2. 如果模型用了 sed → Code 检查是否危险
3. 如果 sed 包含 w/e 等危险命令 → Code 直接阻止
4. 如果 sed 可以用 Edit 替代 → Code 给出建议

### 案例 2：Git 破坏性操作

**Prompt 层的引导**：

```
NEVER run destructive git commands (push --force, reset --hard) 
unless the user explicitly requests these actions.
```

**Code 层的兜底**（bashSecurity.ts + commandSemantics.ts）：

```typescript
// commandSemantics.ts — 分析命令语义
function analyzeCommand(cmd: string): CommandSemantics {
  // 解析命令结构，识别：
  // - 是否是 git 命令
  // - 是否包含 --force / --hard 等 flag
  // - 目标分支是否是 main/master
}

// bashSecurity.ts — 安全检查管线
function securityPipeline(cmd: string): 'passthrough' | 'ask' | 'deny' {
  // 管线：控制字符 → shell-quote bug → heredoc → quote → 
  //       早期验证器 → 主验证链 → 最终决策
  // 如果识别为破坏性 git 操作 → ask（需要用户确认）
}
```

**两层配合**：
1. Prompt 用 NEVER 告诉模型不要做
2. 如果模型还是做了 → Code 检测为破坏性操作 → 弹出用户确认
3. 用户确认后才执行

### 案例 3：沙箱绕过

**Prompt 层的引导**：

```
Do NOT attempt to set dangerouslyDisableSandbox: true unless:
  - The user *explicitly* asks you to bypass sandbox
  - A specific command just failed with sandbox restrictions
```

**Code 层的兜底**（shouldUseSandbox.ts + pathValidation.ts）：

```typescript
// shouldUseSandbox.ts — 决定是否使用沙箱
function shouldUseSandbox(command: string, context: Context): boolean {
  // 根据命令类型、用户配置、环境变量决定
  // 即使 prompt 说"可以绕过"，code 仍然检查条件
}

// pathValidation.ts — 路径安全检查
function validatePath(path: string): ValidationResult {
  // 检查路径是否在允许的目录内
  // 检查是否包含 ../ 等路径遍历
  // 检查是否是敏感路径（~/.ssh, ~/.bashrc 等）
}
```

---

## 三、双重防线的设计原则

从 Claude Code 的实现中，可以提炼出 5 个设计原则：

### 原则 1：Prompt 做"软约束"，Code 做"硬约束"

```
Prompt: "prefer X over Y"      → 软约束，可以违反
Code:   if (isY) { check() }   → 硬约束，违反则阻止
```

Prompt 的措辞是 "prefer"、"use X instead of Y"、"avoid"——这些都是引导性的语言，不是命令式的。模型可以忽略它们。Code 则是 if-else 的硬逻辑，不可违反。

### 原则 2：Code 层独立于 Prompt 层

安全检查的代码不依赖于 prompt 的内容。即使完全删除 prompt，code 层的安全检查仍然有效。这意味着：

- Prompt 可以随时修改，不影响安全
- 安全团队可以独立审查 code，不依赖 prompt 团队
- 新增安全检查不需要修改 prompt

### 原则 3：Code 层的检查是管线式的，有优先级

```
控制字符检查 → shell-quote bug → heredoc → quote → 早期验证器 → 主验证链
```

常见的安全操作（git commit、safe heredoc）在管线早期就放行，不浪费后续检查的计算资源。危险操作层层递进检查，不漏过任何一个。

### 原则 4：Code 层给用户选择权，而不是直接拒绝

当 code 层检测到潜在风险时，它不直接拒绝，而是 **ask**（弹出用户确认）。这保留了用户的控制权：

```
破坏性操作 → ask（用户确认）
明确恶意   → deny（直接阻止）
安全操作   → passthrough（直接放行）
```

### 原则 5：Prompt 和 Code 使用不同的"语言"

Prompt 用自然语言，面向 LLM。Code 用程序逻辑，面向确定性检查。它们不需要互相理解——只需要在同一个接口（命令输入）上形成互补。

---

## 四、两层失效的场景分析

双重防线不是万能的。分析两层同时失效的场景，才能真正理解其边界：

### 场景 1：Prompt 失效，Code 兜底成功

**案例**：模型忽略了 "use Edit instead of sed" 的建议，直接用了 `sed -i 's/old/new/g' file.txt`

- Prompt 层：❌ 失败（模型没听）
- Code 层：✅ 成功（sedEditParser 检测到可以替代，给出建议）

### 场景 2：Prompt 成功，Code 不需要

**案例**：模型正确使用了 Read 工具而不是 cat

- Prompt 层：✅ 成功（模型遵循偏好链）
- Code 层：— 不涉及（没有安全风险）

### 场景 3：Prompt 失效，Code 也失效

**案例**：模型构造了一个 code 层无法识别的恶意命令（比如用 Unicode 同形字绕过检测）

- Prompt 层：❌ 失败
- Code 层：❌ 失败（新型攻击模式未被覆盖）

**应对**：这是安全的"最后一公里"问题。Claude Code 通过以下方式缓解：
1. 持续更新安全检查规则（从实际攻击中学习）
2. User confirmation 作为最后防线（即使 code 放行，高风险操作仍需用户确认）
3. 沙箱模式限制实际损害范围

### 场景 4：两层矛盾

**案例**：Prompt 说 "you may disable sandbox"，但 Code 层的 shouldUseSandbox 返回 false

- 这种情况下 Code 层优先。Prompt 的 "may" 是软约束，Code 的返回值是硬约束。

---

## 五、对其他 Agent 框架的启示

Claude Code 的双重防线架构可以抽象为一个通用模式，适用于任何有工具调用能力的 Agent 系统：

### 5.1 通用架构

```
┌─────────────────────────────────────────┐
│              用户请求                     │
│                  │                       │
│                  ▼                       │
│  ┌───────────────────────────────┐       │
│  │  LLM (受 Prompt 引导)         │       │
│  │  输出: 工具调用 + 参数         │       │
│  └───────────────┬───────────────┘       │
│                  │                       │
│                  ▼                       │
│  ┌───────────────────────────────┐       │
│  │  Code 层安全检查 (确定性)      │       │
│  │  ├── 参数验证                 │       │
│  │  ├── 语义分析                 │       │
│  │  ├── 权限检查                 │       │
│  │  └── 结果: allow / ask / deny │       │
│  └───────────────┬───────────────┘       │
│                  │                       │
│                  ▼                       │
│  ┌───────────────────────────────┐       │
│  │  执行 (沙箱/非沙箱)            │       │
│  └───────────────────────────────┘       │
└─────────────────────────────────────────┘
```

### 5.2 可复用的设计模式

| 模式 | Prompt 层 | Code 层 |
|:---|:---|:---|
| 偏好引导 | "use X instead of Y" | 检测 Y 的使用，建议替代 |
| 破坏性操作阻止 | "NEVER do X" | 检测 X，弹出用户确认 |
| 沙箱隔离 | "commands run in sandbox" | 强制执行沙箱限制 |
| 路径安全 | "don't access sensitive paths" | 验证路径白名单 |
| 权限升级 | "ask before doing X" | 检测 X，需要用户授权 |

### 5.3 关键设计教训

1. **永远不要只靠 Prompt 做安全**——概率性的 LLM 不适合做确定性的安全决策
2. **永远不要只靠 Code 做安全**——没有 prompt 引导，模型会产生大量需要 code 兜底的请求，降低效率
3. **Code 层要独立于 Prompt**——安全检查的逻辑不应该依赖 prompt 的措辞
4. **Code 层要给用户选择权**——ask > deny，除非是明确恶意
5. **管线式检查优于全量检查**——常见的安全操作尽早放行，节省资源
6. **两层使用不同的"语言"**——Prompt 对 LLM 说话，Code 对执行环境说话

---

## 六、总结

Claude Code 的 Tool 安全架构的核心洞察是：

> **Prompt 是"你想做对的事"，Code 是"你做不了坏事"。两者缺一不可。**

Prompt 解决了"模型不知道该怎么做"的问题，Code 解决了"模型知道但不按做"的问题。两层防线覆盖了两种不同类型的失败模式，形成了完整的安全保障。

对于构建 Agent 系统的开发者来说，这个架构是一个可复用的模板：**用 Prompt 引导行为，用 Code 确保安全，用沙箱限制损害，用用户确认保留控制权。**
