# Prompt Engineer Skill — 评估计划

## 总目标

验证 prompt-engineer skill 是否真的能帮助写出好 prompt。两层评估：

```
Layer 1（静态）：prompt 本身结构好不好 → audit-checklist 打分
Layer 2（动态）：prompt 实际跑起来效果如何 → 任务通过率
```

## 4 个实验

| Exp | 任务 | 测什么 | 难度 | 状态 |
|:---|:---|:---|:---|:---|
| exp-001 | JSON 输出格式遵循 | Output Contract pattern | easy | ✅ 5/5 通过 |
| exp-002 | 工具偏好链遵循 | Preference Chain pattern | medium | ⬜ 待跑 |
| exp-003 | Agent 冷启动 Briefing | Identity + 多 pattern 组合 | hard | ⬜ 待跑 |
| exp-004 | 反模式约束有效性 | Anti-pattern Catalog pattern | medium | ⬜ 待跑 |

## 每个实验的步骤

```
1. 用 skill 分析任务 → 判断需要哪些 pattern
2. 生成 prompt v1 → 写入 experiments/exp-XXX/prompt.md
3. 用 prompt 跑 3-5 次 → 记录 transcript
4. 评分 → 第一层静态 + 第二层动态
5. 如果不过 → 迭代 v2 → 重新跑
6. 记录结果到 dashboard
```

## 完成后做什么

4 个实验跑完后：
1. 分析哪些 pattern 有效、哪些没用
2. 找到 skill 的盲区
3. 迭代 SKILL.md 和 references
4. 推送最终版到 GitHub

## 当前进度

```
[████░░░░░░░░] exp-001 ✅ → exp-002 ⬜ → exp-003 ⬜ → exp-004 ⬜
```
