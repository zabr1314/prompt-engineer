# Prompt Type Reference

Five fundamentally different prompt types. Each has different failure modes and different writing strategies.

---

## Type 1: System Prompt (Kernel)

**Core question:** How to install an operating system on the model?

**What it does:** Defines the model's worldview the moment it "wakes up."

**Key traits:**
- First thing the model sees. Sets personality baseline.
- Must cover: identity → rules → how to work → how to talk.
- One setting, cross-user shared → naturally fits prompt cache.
- Too much → model forgets. Too little → behavior uncontrolled.

**Recommended structure (7-segment):**

```
① Identity & Safety (who am I, where are the red lines)
② System Behavior Rules (how output renders, how permissions interact)
③ Task Execution Guide (how to do the core task)
④ Risk Operation Confirmation (what needs human approval)
⑤ Tool Usage Preference (which tool to prefer)
⑥ Tone & Style (how to speak)
⑦ Output Efficiency (how much to say)
```

**Static/dynamic split:**
- Segments ①-⑦ go BEFORE the boundary marker → cacheable
- Session-specific info (date, env, memory, MCP) goes AFTER → dynamic

**Writing mindset:** You're not "telling the model rules." You're "installing an operating system." Each segment is a kernel module with one job.

**Common mistakes:**
- Mixing identity definition with tool usage rules
- Writing behavioral rules that belong in a Skill prompt
- Not splitting static/dynamic, destroying cache efficiency

---

## Type 2: Tool Prompt (Driver)

**Core question:** How to make the model use this tool well, not just correctly?

**What it does:** Each tool carries its own prompt. Model reads it when deciding to call the tool.

**Key traits:**
- Must be precise to parameter level: when to use, how to use, edge cases.
- Needs preference chain guidance — not "this tool is good" but "in this scenario, use this instead of that."
- Failure modes and fallback paths must be explicit.

**Recommended structure:**

```
Layer 0: One-line description (what it does)
Layer 1: Preference chain (don't use me for X, use Y instead)
Layer 2: Usage guide (parameters, chaining, parallel calls)
Layer 3: Domain-specific details (e.g., Git workflow for Bash)
Layer 4: Sandbox/restrictions (default behavior, how to escape, what not to whitelist)
```

**Preference chain template:**

```
Do NOT use [general way] when [specific way] is available:
  - [Scenario 1]: use [specific] instead of [general]
  - [Scenario 2]: use [specific] instead of [general]
This is because [why specific is better].
If [extreme case], fallback to [general way].
```

**Writing mindset:** You're not writing a manual. You're designing UX. The tool prompt's quality determines whether the model "can use" the tool vs. "uses it well." Preference chains are key — don't ban bad choices, make good choices obviously better.

**Common mistakes:**
- Only saying "don't use X" without saying "use Y"
- Using "never" without escape hatches
- Not explaining WHY the preference exists

---

## Type 3: Agent Prompt (Process)

**Core question:** How to brief a smart colleague who just walked in with zero context?

**What it does:** Provides everything a sub-agent needs to execute independently.

**Key traits:**
- Sub-agent starts with NO conversation history from the parent.
- Prompt must be self-contained: task + background + constraints + output format.
- Information density must be extremely high — too much wastes tokens, too little produces bad work.
- Different agent types need completely different prompt strategies.

**Recommended structure:**

```
Identity: [Who you are — one sentence]
Task: [What to do — specific, not abstract]
Background: [Why it matters — context for judgment calls]
What I've tried: [What's been ruled out]
Constraints: [What NOT to do]
Output format: [Exact structure expected]
```

**For specialized agents, add adversarial elements:**

```
Known failure modes:
1. [Mode 1] → Countermeasure: [specific requirement]
2. [Mode 2] → Countermeasure: [specific requirement]

Your likely excuses for skipping checks — recognize them, do the opposite:
- "[Excuse 1]" → [What to actually do]
- "[Excuse 2]" → [What to actually do]
```

**Writing mindset:** You're not "assigning a task." You're "briefing a cold-start executor." The agent knows nothing. Say everything once, say it precisely. The more specific the agent, the narrower the prompt should be — one job done well beats ten jobs done mediocre.

**Common mistakes:**
- Delegating understanding: "based on your findings, fix the bug" — no, YOU synthesize, agent executes
- Being too abstract: "make it better" — specific file paths, line numbers, what to change
- Not specifying output format — agent returns whatever it feels like

---

## Type 4: Skill Prompt (Application)

**Core question:** How to design a mode switch on top of the existing kernel?

**What it does:** Changes behavior pattern when triggered, without replacing the system prompt.

**Key traits:**
- NOT a replacement for system prompt — it's an incremental patch.
- Must define clear trigger conditions and exit conditions.
- Usually injected as an additional block, not a full rewrite.
- Output-style skills need format templates.

**Recommended structure:**

```
Entry condition: [When this mode activates]
Behavior delta: [What changes from default behavior]
Format template: [If output format changes]
Exit condition: [When this mode deactivates]
```

**Example — Learning mode:**

```
You are still you, but now you're a teacher:
- Identify 2-10 line self-contained code snippets
- Let the user write them
- Give enough guidance to succeed, but leave room for challenge
- After their contribution, share one insight connecting to broader patterns
```

**Writing mindset:** You're not "writing new rules." You're "designing a mode switcher." Skill = system prompt delta, not replacement. Write the minimum that changes behavior. Everything else stays from the kernel.

**Common mistakes:**
- Restating system prompt rules that already exist
- Not defining exit conditions — model stays in skill mode forever
- Making the skill too broad — one skill = one mode switch

---

## Type 5: Memory Prompt (Filesystem)

**Core question:** What's worth remembering vs. what should be forgotten?

**What it does:** Defines cross-session persistence — schema, save/load rules, trust model.

**Key traits:**
- Not a traditional prompt — it's a data schema + operation protocol.
- Must define types with clear scope, save conditions, usage scenarios.
- Has hard limits (e.g., 200 lines / 25KB) — memory must be lossy.
- Critical design: trust degradation — "If memory contradicts codebase, trust codebase."

**Recommended types:**

| Type | Scope | Save | Don't Save |
|:---|:---|:---|:---|
| User | Private | Role, preferences, knowledge level | Negative judgments about user |
| Feedback | Default private | User corrections/confirmations | Pure style preferences |
| Project | Team-leaning | Ongoing work, goals, bugs | Derivable from code/git |
| Reference | Flexible | Long-lived conventions, infrastructure | Things re-discoverable in 30s |

**The "What NOT to save" list is MORE important than "What to save":**

```
Don't save: patterns derivable from code, git history, file structure
Anything re-discoverable in 30 seconds → don't save
```

**Writing mindset:** You're not "defining a storage format." You're "designing a lossy compression algorithm." The core tradeoff: how much to store to be useful without bloat? Answer: type classification + hard limits + trust degradation.

**Common mistakes:**
- Not defining what NOT to save — leads to memory bloat
- No trust degradation — stale memory overrides current reality
- Storing things the model can re-derive in seconds
