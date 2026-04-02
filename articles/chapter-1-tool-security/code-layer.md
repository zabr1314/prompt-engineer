# 代码层的安全兜底：当 Prompt 的"建议"失效时

> Prompt 告诉模型"不要用 sed"——但如果模型就是用了呢？Claude Code 的回答是：**代码层有 20+ 道独立的安全检查**。这篇文章深入 `bashSecurity.ts`、`commandSemantics.ts`、`pathValidation.ts` 等核心安全模块，看看这些"沉默的守卫"是如何工作的。

---

## 一、安全检查的执行管线

BashTool 的代码层安全检查不是简单的"if-else"——它是一个**分层管线（Pipeline）**，每一层有不同的职责和失败策略：

```
命令输入
  │
  ├─ 1. 控制字符检查（空字节、不可打印字符）→ block
  ├─ 2. shell-quote 单引号 bug 检测 → block
  ├─ 3. heredoc 安全剥离
  ├─ 4. quote 内容提取（withDoubleQuotes / fullyUnquoted）
  │
  ├─ [Early Validators] 快速通道
  │   ├─ 空命令 → allow
  │   ├─ 不完整命令（tab 开头、- 开头） → ask
  │   ├─ 安全 heredoc 替换 → allow（直接放行）
  │   └─ git commit 安全检查 → allow 或 passthrough
  │
  ├─ [Main Validators] 主检查链
  │   ├─ jq 命令安全（system() 阻止、危险 flag 检查）
  │   ├─ 混淆 flag 检测（ANSI-C quoting、空引号、split-quote）
  │   ├─ Shell 元字符检查（; | &）
  │   ├─ IFS 注入检测
  │   ├─ 注释反引号脱同步检测
  │   ├─ 引用换行检测
  │   ├─ 回车符差异检测
  │   ├─ 换行分隔检测
  │   ├─ 输入/输出重定向检测
  │   ├─ 反斜杠转义空白检测
  │   ├─ 反斜杠转义操作符检测
  │   ├─ Unicode 空白检测
  │   ├─ 中间词 # 检测
  │   ├─ 大括号展开检测
  │   ├─ Zsh 危险命令检测
  │   └─ 畸形 token 注入检测
  │
  ├─ [Non-misparsing] → passthrough 或延迟返回
  │
  └─ 最终结果: passthrough / ask / deny
```

关键是：**这个管线的执行顺序是有意设计的**。`earlyValidators` 里的检查如果返回 `allow`，整个管线就短路返回，不执行后续检查。这既是为了性能（safe heredoc 和 git commit 是常见模式），也是为了安全（空命令和不完整命令应该尽早拦截）。

---

## 二、核心安全检查详解

### 2.1 引号内容提取：一切的基础

在讨论任何安全检查之前，必须先理解 `extractQuotedContent()` 函数（`bashSecurity.ts`）——它是几乎所有后续检查的前置步骤：

```typescript
function extractQuotedContent(command: string, isJq = false): QuoteExtraction {
  // 返回三个变体：
  // - withDoubleQuotes: 保留双引号内的内容，剥离单引号
  // - fullyUnquoted: 剥离所有引号内容
  // - unquotedKeepQuoteChars: 保留引号字符本身（用于检测引号相邻的攻击）
}
```

为什么需要三个变体？因为不同的安全检查需要不同的"视角"：

- `withDoubleQuotes`：用于检测 shell 元字符（`;`, `|`, `&`）——这些在双引号内仍然会执行
- `fullyUnquoted`：用于检测重定向（`<`, `>`）——这些在任何引号内都不会执行
- `unquotedKeepQuoteChars`：用于检测 `'x'#` 这种引号紧邻 `#` 的攻击模式

这是一个很好的设计洞察：**安全分析需要"多视角"的命令解析**。不同的安全威胁需要不同的"剥离层级"才能检测到。

### 2.2 混淆 Flag 检测：防"障眼法"

`validateObfuscatedFlags()` 是整个安全检查链中**最复杂**的单个检查器。它的目标是检测各种"障眼法"技术：

**攻击 1：ANSI-C quoting（`$'...'`）**
```bash
grep $'-exec' file    # $'...' 可以编码任何字符
```
检查代码：`if (/\$'[^']*'/.test(originalCommand))` → ask

**攻击 2：空引号 + 连字符（`""-exec`）**
```bash
find . -name ""-exec    # bash 拼接 "" + "-exec" = "-exec"
```
检查代码：`if (/(?:''|"")+\s*-/.test(originalCommand))` → ask

**攻击 3：引号链（`"-""exec"`）**
```bash
find . -name "-""exec"  # 拼接后 = "-exec"
```
这个检查需要一个复杂的 quote-state tracker：

```typescript
// 跟踪引号状态，逐字符扫描
for (let i = 0; i < originalCommand.length - 1; i++) {
  // 更新引号状态（处理单引号、双引号、反斜杠转义）
  // 只在非引号状态下检测 flag 模式
  if (currentChar === '-' && /\s/.test(prevChar)) {
    // 检查是否有引号内的 flag 内容
    // 检查是否有引号链延续
  }
}
```

**攻击 4：同质空引号对（`"""-f"`）**
```bash
jq """-f evil    # "" + "" + "-f" = "-f"
```
正则：`(?:""|'')+['"]-` — 匹配一个或多个同质空引号对后紧跟引号字符和连字符。

**攻击 5：三连引号（`"""x"`）**
```bash
cmd """x"-f    # "" + "x" + "-f" → 任何我们没枚举到的模式
```
正则：`/(?:^|\s)['"]{3,}/` — 在词首出现三个以上连续引号字符。

为什么需要这么多层？因为**攻击者会不断发现新的混淆变体**。每一层都是对已知攻击模式的补丁。`"""-"exec"` 的修复（SubId 10）就是在发现 `"""` 拼接绕过之前的所有检查后添加的。

### 2.3 引号跟踪的一致性问题

在阅读 `bashSecurity.ts` 时，你会发现一个反复出现的模式：**多个函数都在实现几乎相同的引号状态跟踪逻辑**。

- `validateObfuscatedFlags()` — 有 quote-state tracker
- `hasBackslashEscapedWhitespace()` — 有 quote-state tracker
- `hasBackslashEscapedOperator()` — 有 quote-state tracker
- `validateCommentQuoteDesync()` — 有 quote-state tracker
- `validateQuotedNewline()` — 有 quote-state tracker

每个 tracker 都有微妙的差异。例如，`hasBackslashEscapedOperator()` 有一个非常详细的注释解释了**为什么必须先处理反斜杠再处理引号切换**：

```typescript
// 处理反斜杠 FIRST，在引号切换之前。在 bash 中，双引号内 `\"` 
// 是转义序列产生字面量 `"` — 它不会关闭引号。如果我们先处理引号切换：
// `\"` 在 `"..."` 内：
//   - `\` 被忽略（被 !inDoubleQuote 限制）
//   - `"` 切换 inDoubleQuote 为 FALSE（错误 — bash 说仍在内部）
//   - 下一个 `"`（真正的关闭引号）切换回 TRUE — 永久脱同步
```

这种重复实现是一个 trade-off：**共享代码可能导致安全漏洞**（一个函数的 bug 会影响所有使用者），而重复实现虽然增加了维护成本，但每个检查器可以根据自己的需求做精确的处理。

### 2.4 反斜杠转义操作符：splitCommand 的双重解析 Bug

`validateBackslashEscapedOperators()` 检查的是一个非常微妙的安全问题：

```bash
cat safe.txt \; echo ~/.ssh/id_rsa
```

在 bash 中，这是**一个命令**：`cat` 读取 `safe.txt` 和 `;` 和 `echo` 和 `~/.ssh/id_rsa` 作为文件参数。但 `splitCommand` 会把 `\;` 规范化为 `;`，产生两个子命令：

```
"cat safe.txt" 和 "echo ~/.ssh/id_rsa"
```

第一个子命令看起来是只读操作（safe），第二个看起来也是只读操作（echo 只输出）。但如果下游的路径验证只检查 `cat` 命令的参数，而 `echo ~/.ssh/id_rsa` 的路径没被检查——**SSH 私钥就被泄露了**。

```typescript
function hasBackslashEscapedOperator(command: string): boolean {
  // 只在双引号外检测 \<operator>
  // 双引号内 ;|&<> 本来就不是特殊字符，\; 无害
  if (char === '\\' && !inSingleQuote) {
    if (!inDoubleQuote) {
      if (nextChar && SHELL_OPERATORS.has(nextChar)) {
        return true  // ← 检测到 \; → 阻止
      }
    }
    i++  // 无条件跳过转义字符
  }
}
```

一个已知的 false positive：`find . -exec cmd {} \;`。注释说"用户只需批准一次"——这是安全工具的经典取舍：宁可多问一次，也不要漏过一个真实的攻击。

### 2.5 花括号展开：bash 和 parser 的差异利用

`validateBraceExpansion()` 检测的是一种利用 bash 展开和 parser 差异的攻击：

```bash
git ls-remote {--upload-pack="touch /tmp/test",test}
```

Parser（shell-quote/tree-sitter）把整个 `{...}` 看作一个字面量字符串参数。但 bash 会执行花括号展开，变成两个参数：`--upload-pack="touch /tmp/test"` 和 `test`。这绕过了所有基于 parser 的安全检查。

检查逻辑有三层防御：

**第一层：平衡花括号检查**
```typescript
// 检测引号剥离后 } 比 { 多的情况
if (unescapedOpenBraces > 0 && unescapedCloseBraces > unescapedOpenBraces) {
  return ask  // 引号花括号被剥离，表明可能是混淆
}
```

**第二层：原始命令中引号花括号检测**
```typescript
if (/['"][{}]['"]/.test(orig)) {
  return ask  // 原始命令包含 '{' 或 '}' 在引号内
}
```

**第三层：深度匹配的花括号扫描**
```typescript
// 找到匹配的 }，跟踪嵌套深度
// 只在最外层检查 , 和 ..
let innerDepth = 0
for (let k = i + 1; k < matchingClose; k++) {
  if (innerDepth === 0) {
    if (ch === ',' || (ch === '.' && content[k+1] === '.')) {
      return ask  // 这是一个花括号展开
    }
  }
}
```

三层防御说明了同一个模式：**同一种攻击可能有不同的变体**（引号剥离、引号内花括号、正常花括号展开），需要多种检测策略。

---

## 三、权限模型：三层过滤

权限检查（`bashPermissions.ts`）是安全管线的最后一环。它不像安全检查那样直接阻止，而是**决定是自动放行、询问用户、还是拒绝**：

```
命令 → 模式检查 → 安全检查 → 路径约束 → sed 约束 → 权限规则 → 最终决策
         │           │           │          │          │
      modeVali-   bashSecur-  pathVali-  sedVali-  用户自定义
      dation      ity.ts      dation.ts  dation.ts  规则
```

### 3.1 模式检查（`modeValidation.ts`）

在 `acceptEdits` 模式下，以下文件系统命令被自动放行：

```typescript
const ACCEPT_EDITS_ALLOWED_COMMANDS = [
  'mkdir', 'touch', 'rm', 'rmdir', 'mv', 'cp', 'sed',
] as const
```

注意 `sed` 在这里——在 acceptEdits 模式下，sed 是自动允许的。这和 prompt 层的"Edit > sed"偏好形成了有趣的对比：**代码层在特定模式下反而信任 sed**。原因是在 acceptEdits 模式下，用户已经明确授权了文件编辑操作，sed 作为编辑工具是合理的。

### 3.2 路径约束（`pathValidation.ts`）

路径验证是权限模型中**最硬性的约束**——不管 prompt 怎么说，也不管权限规则怎么写，某些路径就是不能碰：

```typescript
// 危险路径列表
function isDangerousRemovalPath(path: string): boolean {
  // /, /usr, /etc, /System 等系统关键目录
  // 永远不允许 rm 操作，即使是显式授权
}
```

路径验证还处理 `--` POSIX 分隔符：

```typescript
function filterOutFlags(args: string[]): string[] {
  // rm -- -/../.claude/settings.local.json
  // "--" 之后的所有参数都视为位置参数，即使以 "-" 开头
  // 防止攻击者用 "--" 绕过路径提取
}
```

### 3.3 sed 约束（`sedValidation.ts`）

sed 的安全验证是代码层中最复杂的白名单系统：

**Pattern 1：行打印命令**（只读）
```bash
sed -n '5p' file        # 允许
sed -n '1,10p' file     # 允许
sed -n '1p;2p;3p' file  # 允许（分号分隔的打印命令）
```
白名单正则：`/^(?:\d+|\d+,\d+)?p$/`

**Pattern 2：替换命令**（编辑）
```bash
sed -i 's/old/new/g' file   # acceptEdits 模式允许
sed 's/old/new/g' file      # 非编辑模式允许（stdout 输出）
```
白名单：只允许 `s` 命令 + 限定 flag（`g, p, i, I, m, M, 1-9`）

**拒绝列表**（`containsDangerousOperations`）：
```typescript
// w/W 命令（写文件）→ 拒绝
// e/E 命令（执行命令）→ 拒绝
// 非 ASCII 字符（Unicode 同形字）→ 拒绝
// 花括号（复杂逻辑块）→ 拒绝
// 换行（多行命令）→ 拒绝
// ! 取反操作符 → 拒绝
// ~ 波浪号（GNU step 地址）→ 拒绝
```

这个白名单 + 拒绝列表的组合设计得非常精细：**允许的模式足够宽松以覆盖常见用例，拒绝的模式足够严格以防止已知攻击**。

---

## 四、命令语义：exit code 不是万能的

`commandSemantics.ts` 处理的是一个经常被忽略的问题：**不是所有非零 exit code 都是错误**。

```typescript
const COMMAND_SEMANTICS: Map<string, CommandSemantic> = new Map([
  ['grep', (exitCode) => ({
    isError: exitCode >= 2,    // 1 = 无匹配（不是错误）
  })],
  ['diff', (exitCode) => ({
    isError: exitCode >= 2,    // 1 = 文件不同（不是错误）
  })],
  ['test', (exitCode) => ({
    isError: exitCode >= 2,    // 1 = 条件为假（不是错误）
  })],
  ['find', (exitCode) => ({
    isError: exitCode >= 2,    // 1 = 部分目录不可访问（警告）
  })],
])
```

这个模块虽然不在"安全"主线，但它体现了同一个设计哲学：**对不同工具有不同的语义理解**，而不是用通用的规则一刀切。

---

## 五、破坏性命令警告：不阻止，只提醒

`destructiveCommandWarning.ts` 是一个有趣的模块——它**不阻止任何命令**，只在检测到潜在破坏性操作时返回警告字符串：

```typescript
const DESTRUCTIVE_PATTERNS: DestructivePattern[] = [
  { pattern: /\bgit\s+reset\s+--hard\b/, warning: 'Note: may discard uncommitted changes' },
  { pattern: /\bgit\s+push\b...--force/, warning: 'Note: may overwrite remote history' },
  { pattern: /\bkubectl\s+delete\b/, warning: 'Note: may delete Kubernetes resources' },
  { pattern: /\bterraform\s+destroy\b/, warning: 'Note: may destroy Terraform infrastructure' },
  { pattern: /rm\s+-[a-zA-Z]*[rR][a-zA-Z]*f/, warning: 'Note: may recursively force-remove files' },
]
```

这个模块的设计意图是**信息透明**而非安全阻断。当用户看到 "Note: may discard uncommitted changes" 时，他们可以做出更知情的决定。这是**安全和用户体验的平衡**：不阻止工作流程，但确保用户知道潜在风险。

---

## 六、sedEditParser：代码层的"偏好链执行者"

`sedEditParser.ts` 是连接 prompt 层"Edit > sed"偏好和代码层实际行为的桥梁：

```typescript
export function parseSedEditCommand(command: string): SedEditInfo | null {
  // 解析 sed -i 's/pattern/replacement/flags' file
  // 提取：filePath, pattern, replacement, flags
  // 如果是简单的 sed -i 替换，返回结构化信息
  // 如果是复杂命令（多表达式、未知 flag），返回 null
}
```

如果解析成功，Claude Code 可以将 sed 命令**渲染为类似 Edit 工具的 diff 预览**，而不是显示原始的 bash 命令。这既提升了用户体验（更好的可读性），也增强了安全性（用户看到的是具体的文件修改，而不是晦涩的 sed 表达式）。

同时，`applySedSubstitution()` 函数可以在**本地模拟** sed 的行为，这意味着可以在不实际执行命令的情况下预览修改效果。这是一个很好的安全模式：**用模拟替代执行**。

---

## 七、设计洞察

### 7.1 检查器的独立性

每个安全检查器（`validateXxx()` 函数）都返回统一的 `PermissionResult`：

```typescript
type PermissionResult = {
  behavior: 'allow' | 'ask' | 'deny' | 'passthrough'
  message?: string
  isBashSecurityCheckForMisparsing?: boolean  // 关键字段
}
```

`passthrough` 意味着"这个检查器没有意见，交给下一个检查器"。`ask` 意味着"这个检查器发现了一个问题，需要用户确认"。`allow` 意味着"这个检查器明确允许，跳过后续检查"。

关键的是 `isBashSecurityCheckForMisparsing` 字段——它区分了两种 `ask` 结果：

- **有这个标志**：这是 parser 差异导致的安全问题，必须阻断
- **没有这个标志**：这是正常模式（如重定向），只需要提醒

### 7.2 非误解析检查器的延迟返回

`nonMisparsingValidators`（`validateNewlines`, `validateRedirections`）的结果不会立即返回，而是被"延迟"：

```typescript
let deferredNonMisparsingResult: PermissionResult | null = null
for (const validator of validators) {
  const result = validator(context)
  if (result.behavior === 'ask') {
    if (nonMisparsingValidators.has(validator)) {
      if (deferredNonMisparsingResult === null) {
        deferredNonMisparsingResult = result
      }
      continue  // ← 不立即返回，继续检查
    }
    return { ...result, isBashSecurityCheckForMisparsing: true }
  }
}
if (deferredNonMisparsingResult !== null) {
  return deferredNonMisparsingResult  // ← 只有在没有更严重的错误时才返回
}
```

这意味着：如果一个命令同时触发了重定向（非误解析）和反斜杠转义操作符（误解析），**只有后者会被报告**。这确保了最严重的安全问题优先被处理。

### 7.3 20+ 检查器的维护成本

代码层有超过 20 个独立的安全检查器，每个都有详细的注释解释它在防什么攻击。这是一个**高维护成本**的设计——每发现一个新的攻击模式，可能需要：

1. 添加一个新的检查器
2. 修改现有检查器的正则表达式
3. 调整检查器的执行顺序（以防新检查器和旧检查器的交互）

但这也是最安全的设计——**每个检查器只负责一件事**，出问题时可以独立修复，不会影响其他检查。

---

*下一篇我们将探讨 prompt 层和代码层如何协同工作——当一个系统失败时，另一个系统如何兜底。*
