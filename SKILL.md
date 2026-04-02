---
name: prompt-engineer
description: "Design and write high-quality prompts for AI agents and coding assistants. Use when (1) creating new system prompts, tool prompts, agent prompts, skill prompts, or memory prompts, (2) reviewing or auditing existing prompts for quality, (3) debugging prompt behavior issues like model ignoring instructions or gold-plating, (4) migrating prompts between frameworks. Triggers on phrases like write a prompt, improve this prompt, prompt engineering, system prompt, agent prompt, prompt audit."
---

# Prompt Engineer

Design prompts that install operating systems, not deliver lectures.

## Core Philosophy

A prompt is not a set of instructions — it's a runtime environment. The model doesn't "listen" to your prompt; it "runs" inside it.

```
System Prompt  = kernel (behavior rules + scheduling policy)
Tool Prompt    = driver (how each hardware device operates)
Agent Prompt   = process (isolated execution context)
Skill Prompt   = application (mode switch on top of the kernel)
Memory Prompt  = filesystem (cross-session persistence)
```

Each type has different failure modes, different quality criteria, and different writing strategies. Never use one type's writing style for another.

## Step 1: Classify the Prompt Type

Before writing anything, determine which type you're building. See [references/prompt-types.md](references/prompt-types.md) for full details.

| Type | Core Question | Key Trait |
|:---|:---|:---|
| System | How to install an operating system? | Stable, cacheable, modular |
| Tool | How to make the model use this tool well? | Precise, comparative, with fallbacks |
| Agent | How to brief a cold-start executor? | Self-contained, high density, adversarial |
| Skill | How to design a mode switch? | Minimal delta, clear entry/exit |
| Memory | What's worth remembering? | Lossy compression, trust degradation |

## Step 2: Apply the 8 Design Patterns

For each prompt, check all 8 patterns. See [references/design-patterns.md](references/design-patterns.md) for templates and examples.

1. **Identity Anchor** — One sentence: who are you?
2. **Red Line Declaration** — White list + black list + grey area conditions
3. **Preference Chain** — Guide to optimal path, with fallback
4. **Anti-pattern Catalog** — Specific "don't do this" at behavior level
5. **Risk Gradient** — Different confirmation strategies by risk level
6. **Adversarial Verification** — Independent validation, preempt self-deception
7. **Context Isolation** — Move noisy work out of main context
8. **Output Contract** — Number-anchored format constraints

## Step 3: Quality Audit

Score the prompt 1-5 on each pattern. See [references/audit-checklist.md](references/audit-checklist.md) for the full rubric.

```
Score 8/8: Claude Code level quality
Score 5-7: Good but has blind spots
Score <5:  Rewrite needed
```

## Key Rules

- **Type determines style.** System prompts should be stable and modular. Agent prompts should be dense and self-contained. Never write a system prompt like an agent prompt.
- **Specific beats abstract.** "Three similar lines of code is better than a premature abstraction" > "Don't over-engineer."
- **Preempt, don't just prohibit.** List the model's likely excuses for bypassing rules, then block each one.
- **One sentence per rule.** If you need a paragraph to explain a rule, the rule is too complex.
- **Leave escape hatches.** "Never" is almost always wrong. "Do X instead of Y, unless Z" is right.
