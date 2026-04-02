# Prompt Engineering Skill — 实验结果总览

> 最后更新: 2026-04-02

## 实验记录

| Exp ID | Task | Prompt 版本 | Pass@N | 第一层(静态) | 第二层(动态) | 状态 |
|:---|:---|:---|:---|:---|:---|:---|
| exp-001 | task-01 JSON输出 | v1 | 5/5 (100%) | 4.0/5 | 4.0/4 | ✅ 完成 |

## 两层评估交叉分析

```
第一层高 + 第二层高 = ✅ Skill 有效
第一层高 + 第二层低 = ⚠️ Prompt好看但不好用 → 检查 pattern 是否脱离实际
第一层低 + 第二层高 = ⚠️ Prompt丑但能用 → 检查是否有隐藏盲区
第一层低 + 第二层低 = ❌ Skill 需要重写
```

## 薄弱 Pattern 追踪

| Pattern | 平均分 | 趋势 | 备注 |
|:---|:---|:---|:---|
| Identity Anchor | — | — | |
| Red Line Declaration | — | — | |
| Preference Chain | — | — | |
| Anti-pattern Catalog | — | — | |
| Risk Gradient | — | — | |
| Adversarial Verification | — | — | |
| Context Isolation | — | — | |
| Output Contract | — | — | |
