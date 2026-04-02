# Prompt Engineering Skill — 实验结果总览

> 最后更新: 2026-04-02 12:35

## 实验记录

| Exp ID | Task | Pattern | Pass@N | 第一层(静态) | 第二层(动态) | 交叉结论 |
|:---|:---|:---|:---|:---|:---|:---|
| exp-001 | JSON输出格式 | Output Contract | 5/5 (100%) | 4.0/5 | 4.0/4 | ✅ 两层都高 |
| exp-002 | 工具偏好链 | Preference Chain | 3/3 (100%) | 4.0/5 | 3/3 | ✅ 两层都高 |
| exp-003 | Agent安全审查 | Identity + Output Contract | 3/3 (核心100%) | 4.3/5 | 117% | ✅ 两层都高，超预期 |
| exp-004 | 反模式约束 | Anti-pattern Catalog | 3/3 (100%) | 3.3/5 | 3/3 | ⚠️ 能用但prompt弱 |

## 总结

```
Overall Pass Rate: 14/14 trials (100%)
Average Layer 1: 3.9/5
Average Layer 2: 100%
```

## Pattern 有效性排名

| Pattern | 测试次数 | 有效 | 说明 |
|:---|:---|:---|:---|
| Output Contract | 2 (exp-001, 003) | ✅ 非常有效 | 精确 schema = 精确输出 |
| Preference Chain | 1 (exp-002) | ✅ 有效 | "为什么"比"是什么"更重要 |
| Anti-pattern Catalog | 1 (exp-004) | ✅ 有效 | 行为级别的约束效果最好 |
| Identity Anchor | 1 (exp-003) | ✅ 有效 | 越具体越好 |
| Red Line Declaration | 0 | — | 未测试 |
| Risk Gradient | 0 | — | 未测试 |
| Adversarial Verification | 0 | — | 需要更复杂的任务 |
| Context Isolation | 0 | — | 需要多 agent 场景 |

## 薄弱点

1. **exp-004 的第一层分数偏低**（3.3/5）—— prompt 的 Identity 和 Output Contract 较弱，但 Anti-pattern 本身够强撑住了效果
2. **4 个 pattern 未测试**—— 需要更复杂的任务来测试 Red Line、Risk Gradient、Adversarial、Context Isolation
3. **没有失败案例**—— 所有实验 100% 通过，说明任务难度不够高，无法区分 prompt 质量的细微差异

## 下一步

1. 设计更难的任务（对抗性场景、多步骤推理）
2. 测试未覆盖的 pattern（Red Line、Risk Gradient）
3. 引入"故意写坏 prompt"的对照组，验证 skill 的改进效果
