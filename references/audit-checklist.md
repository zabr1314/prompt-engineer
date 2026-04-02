# Prompt Audit Checklist

Score each pattern 1-5. Total out of 40.

---

## Scoring Rubric

| Score | Meaning |
|:---|:---|
| 1 | Missing or actively harmful |
| 2 | Present but vague or wrong approach |
| 3 | Correct principle, but not actionable |
| 4 | Actionable with minor gaps |
| 5 | Precise, preemptive, with fallbacks |

---

## Audit Items

### 1. Identity Anchor (/5)

- [ ] One sentence defines the role
- [ ] Role is specific, not generic ("software engineer" > "assistant")
- [ ] Includes at least one strength or differentiator

**Score: ___/5**

### 2. Red Line Declaration (/5)

- [ ] White list exists (what IS allowed)
- [ ] Black list exists (what is NOT allowed)
- [ ] Grey area has explicit conditions
- [ ] Uses `IMPORTANT:` or equivalent emphasis marker

**Score: ___/5**

### 3. Preference Chain (/5)

- [ ] Identifies the preferred approach
- [ ] Lists specific scenarios for each preference
- [ ] Explains WHY the preference exists
- [ ] Provides fallback for edge cases

**Score: ___5**

### 4. Anti-pattern Catalog (/5)

- [ ] Lists specific behaviors to avoid (not abstract principles)
- [ ] Each anti-pattern targets one LLM failure mode
- [ ] Includes concrete numbers or examples to anchor judgment
- [ ] Covers at least 3 distinct anti-patterns

**Score: ___/5**

### 5. Risk Gradient (/5)

- [ ] Defines at least 2 risk levels
- [ ] Each level has a specific confirmation strategy
- [ ] Addresses the "one approval = permanent approval" fallacy
- [ ] Provides safe-first, destructive-last approach to obstacles

**Score: ___/5**

### 6. Adversarial Verification (/5)

- [ ] Defines what verification means (not just "check it")
- [ ] Requires command evidence, not just assertions
- [ ] Preempts at least 2 known self-deception patterns
- [ ] Specifies output format for verification results

**Score: ___/5**

### 7. Context Isolation (/5)

- [ ] Identifies which work should be isolated
- [ ] Defines isolation rules (don't peek, don't predict)
- [ ] Specifies what to return from isolated context

**Score: ___/5**

### 8. Output Contract (/5)

- [ ] Length constraints use specific numbers
- [ ] Structure requirements are explicit
- [ ] Prohibited behaviors are listed
- [ ] Format matches the prompt type (structural for verification, flowing for communication)

**Score: ___/5**

---

## Total Score

| Total | Rating | Action |
|:---|:---|:---|
| 32-40 | Excellent | Ship it |
| 24-31 | Good | Fix the weak patterns |
| 16-23 | Needs work | Rewrite using templates from design-patterns.md |
| 8-15 | Poor | Start over. Classify the type first, then apply patterns |
| <8 | Missing | No prompt engineering present |

---

## Type-Specific Checks

After scoring the 8 universal patterns, add type-specific checks:

### System Prompt

- [ ] Static/dynamic split exists (boundary marker)
- [ ] Each segment has one responsibility
- [ ] No tool-specific details in system prompt

### Tool Prompt

- [ ] Preference chain exists (this tool vs alternatives)
- [ ] Parameter-level precision
- [ ] Failure mode and fallback documented

### Agent Prompt

- [ ] Fully self-contained (no dependency on parent context)
- [ ] Task is specific (file paths, line numbers)
- [ ] Output format is explicitly defined
- [ ] Does NOT delegate synthesis ("based on your findings, do X")

### Skill Prompt

- [ ] Entry condition is clear
- [ ] Behavior delta is minimal (only what changes)
- [ ] Exit condition is defined

### Memory Prompt

- [ ] Types defined with scope, save conditions, usage
- [ ] "What NOT to save" list exists and is specific
- [ ] Trust degradation rule exists
