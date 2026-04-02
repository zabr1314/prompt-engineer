# Design Patterns Reference

Eight patterns extracted from Claude Code's prompt engineering. Each solves a specific problem. Apply all 8 when writing or auditing a prompt.

---

## Pattern 1: Identity Anchor

**Problem solved:** Model doesn't know who it is; behavior is erratic.

**Principle:** One sentence. Define the role. No fluff.

**Template:**

```
You are a [specific role] that [core responsibility]. Your strengths: [2-3 key capabilities].
```

**Examples from Claude Code:**

| Agent | Identity Anchor |
|:---|:---|
| Main | "You are an interactive agent that helps users with software engineering tasks." |
| Explore | "You are a file search specialist." |
| Plan | "You are a software architect and planning specialist." |
| Verification | "You are a verification specialist. Your job is not to confirm — it's to try to break it." |
| Guide | "You are the Claude guide agent." |

**Internal version goes further — defines role relationship:**

```
You're a collaborator, not just an executor — users benefit from your judgment, not just your compliance.
```

**Common mistake:** Writing a paragraph. Identity anchor = one sentence.

---

## Pattern 2: Red Line Declaration

**Problem solved:** Safety boundaries are vague; model might execute destructive operations.

**Principle:** White list + Black list + Grey area conditions. Not just "don't do bad things."

**Template:**

```
IMPORTANT: [White list scenarios]. Refuse [Black list scenarios]. [Grey area] requires [specific condition].
```

**Claude Code's example:**

```
IMPORTANT: Assist with authorized security testing, defensive security, CTF challenges, 
and educational contexts. Refuse requests for destructive techniques, DoS attacks, 
mass targeting, supply chain compromise, or detection evasion for malicious purposes. 
Dual-use security tools (C2 frameworks, credential testing, exploit development) 
require clear authorization context: pentesting engagements, CTF competitions, 
security research, or defensive use cases.
```

**Structure:**
- ✅ White list: pentesting, CTF, security research
- ❌ Black list: DoS, mass targeting, supply chain
- ⚠️ Grey area: C2 frameworks, credential testing → needs explicit authorization

**Common mistake:** Only writing the black list. Model over-refuses in grey areas.

---

## Pattern 3: Preference Chain

**Problem solved:** Model has multiple ways to do the same task; needs guidance to pick the best one.

**Principle:** Don't ban — guide. Make the better option obviously better. Leave a fallback.

**Template:**

```
Do NOT use [general approach] when [specific approach] is available:
  - [Scenario 1]: use [specific] instead of [general]
  - [Scenario 2]: use [specific] instead of [general]
This is because [why specific is better — UX/visibility/safety reason].
If [extreme case], fallback to [general approach].
```

**Claude Code's example:**

```
Do NOT use Bash when a relevant dedicated tool is provided:
  - Read files → Read (NOT cat/head/tail/sed)
  - Edit files → Edit (NOT sed/awk)
  - Create files → Write (NOT cat heredoc/echo redirect)
  - Find files → Glob (NOT find/ls)
  - Search content → Grep (NOT grep/rg)
Using dedicated tools allows the user to better understand and review your work.
Reserve Bash for system commands that require shell execution.
```

**Why it works:**
1. Uses "NOT...when..." not "never" — preserves fallback
2. Lists concrete alternatives, not abstract principles
3. Explains WHY the specific approach is better
4. Gives escape hatch: "only fallback if absolutely necessary"

**Common mistake:** "Don't use X" without "use Y instead." Or using "never" without fallback.

---

## Pattern 4: Anti-pattern Catalog

**Problem solved:** Telling the model what to do isn't enough. Must precisely tell it what NOT to do.

**Principle:** Each anti-pattern targets one specific LLM failure mode. Be at behavior level, not principle level.

**Template:**

```
DON'T:
- [Specific anti-pattern 1] — [one-line explanation of why]
- [Specific anti-pattern 2] — [one-line explanation of why]  
- [Specific anti-pattern 3] + [concrete number/example to anchor judgment]
```

**Claude Code's best examples:**

```
Don't add features, refactor code, or make "improvements" beyond what was asked.
Don't add error handling for scenarios that can't happen.
Don't create helpers for one-time operations.
Three similar lines of code is better than a premature abstraction.
```

**Internal version targets comment behavior:**

```
Default to writing no comments. Only add one when the WHY is non-obvious.
Don't explain WHAT the code does, since well-named identifiers already do that.
```

**Why "three similar lines" works:** It gives a concrete number. "Don't over-abstract" is too vague. "Three lines" anchors the judgment.

**Common mistake:** Writing "don't over-engineer" (abstract principle). Must be at behavior level: "don't create helpers for one-time operations."

---

## Pattern 5: Risk Gradient

**Problem solved:** Not all operations need equal confirmation. Model either asks everything or asks nothing.

**Principle:** Two dimensions — reversibility × blast radius. Different levels get different confirmation strategies.

**Template:**

```
[Low risk — local, reversible]: Execute freely
[Medium risk — hard to reverse or affects shared state]: Describe first, wait for confirmation
[High risk — destructive or public-facing]: Must confirm, one approval ≠ permanent approval

When encountering [obstacle]: try [safe approach] first. Only use [destructive approach] when [condition].
```

**Claude Code's risk matrix:**

| Level | Examples | Strategy |
|:---|:---|:---|
| Free | Edit files, run tests | Execute without asking |
| Confirm | Push code, create PR, send messages | Describe + wait |
| Never auto | Force push, delete branch, rm -rf | Always confirm |

**Key detail:**

```
A user approving an action once does NOT mean they approve it in all contexts.
Authorization stands for the scope specified, not beyond.
```

**Common mistake:** Treating all operations equally. Or: "user approved once = always approved."

---

## Pattern 6: Adversarial Verification

**Problem solved:** LLM self-verification is unreliable. Systematic self-deception.

**Principle:** Independent adversarial process. Preempt the model's excuses. Require command evidence.

**Template:**

```
Your job is not to confirm [X] works — it's to try to break it.

Known failure modes:
1. [Verification avoidance]: [what the model does to skip] → [countermeasure]
2. [First 80% seduction]: [what the model does to pass prematurely] → [countermeasure]

Every PASS must include:
  Command run: [exact command]
  Output observed: [actual output, not paraphrased]
  Result: PASS/FAIL

Your likely excuses — recognize them, do the opposite:
- "[Excuse 1]" → [what to actually do]
- "[Excuse 2]" → [what to actually do]
```

**Claude Code's Verification Agent preemptive excuses:**

```
- "The code looks correct based on my reading" → Reading is not verification. Run it.
- "The implementer's tests already pass" → The implementer is an LLM. Verify independently.
- "This is probably fine" → Probably is not verified. Run it.
- "I don't have a browser" → Check for MCP tools first. Don't invent your own "can't do this."
```

**Why it works:** It doesn't just say "verify carefully." It predicts exactly HOW the model will try to skip verification, then blocks each escape route.

**Common mistake:** "Please verify carefully" (soft constraint). Must be structural: independent process + command evidence + preempted excuses.

---

## Pattern 7: Context Isolation

**Problem solved:** Main context window is expensive. Research noise fills it up.

**Principle:** Move high-noise work to isolated context. Don't peek at intermediate results. Don't predict/fabricate outcomes.

**Template:**

```
When [scenario], use [isolation mechanism] to move work to independent context.
Rules:
  - Do not read intermediate results while [isolated work] is running
  - Do not predict or fabricate [isolated work]'s output
  - On completion, return only [summary/key findings], not raw data
```

**Claude Code's Fork rules:**

```
Don't peek: Do NOT Read or tail the fork's output file unless user explicitly asks.
Don't race: Never fabricate or predict fork results — not as prose, summary, or structured output.
```

**Sub-agent isolation:**

```
Agent threads always have their cwd reset between bash calls.
Share file paths (always absolute, never relative).
Include code snippets only when the exact text is load-bearing — do not recap code you merely read.
```

**Common mistake:** Launching a sub-agent, then immediately reading its partial output — defeating the purpose of isolation.

---

## Pattern 8: Output Contract

**Problem solved:** Model output format is unstable. Too verbose, too terse, or unstructured.

**Principle:** Number-anchored constraints. Structural requirements. Explicit prohibitions.

**Template:**

```
Output format:
- Length: [specific constraint with numbers]
- Structure: [required sections/fields]
- Style: [concise/detailed/structured]
- Prohibited: [things not to do, e.g., "don't restate user's question"]
```

**Claude Code's three layers:**

**Layer 1 — General efficiency:**
```
If you can say it in one sentence, don't use three.
Do not restate what the user said — just do it.
Lead with the answer or action, not the reasoning.
```

**Layer 2 — Number anchors (internal):**
```
Keep text between tool calls to ≤25 words.
Keep final responses to ≤100 words unless the task requires more detail.
```

**Layer 3 — Structural enforcement (Verification Agent):**
```
### Check: [what you're verifying]
**Command run:** [command]
**Output observed:** [actual output]
**Result:** PASS/FAIL

VERDICT: PASS/FAIL/PARTIAL
```

**Anti-semantic-backtracking (internal):**
```
Structure each sentence so a person can read it linearly, 
building up meaning without having to re-parse what came before.
```

**Common mistake:** "Be concise" (no number). Must be: "≤25 words between tool calls."
