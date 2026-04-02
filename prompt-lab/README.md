# Prompt Engineering Skill — 实验评估体系

两层评估框架：
- **第一层（静态）**：Prompt 结构质量 — 用 audit-checklist 打分
- **第二层（动态）**：实际运行效果 — 跑任务算通过率

## 目录结构

```
prompt-lab/
├── README.md                  ← 本文件
├── tasks/                     ← 标准化测试任务
│   ├── task-01-json-output.yaml
│   ├── task-02-preference-chain.yaml
│   ├── task-03-agent-briefing.yaml
│   └── task-04-anti-pattern.yaml
├── experiments/               ← 实验记录
│   └── exp-001/
│       ├── prompt.md          ← 被测 prompt
│       ├── runs/              ← 运行记录
│       └── results.yaml       ← 汇总结果
├── scorers/                   ← 评分脚本
│   ├── json_validator.py      ← 确定性评分：JSON 格式检查
│   └── llm_judge_prompt.md    ← 模型裁判 prompt
└── dashboard.md               ← 结果总览
```

## 使用方法

1. 选一个 task
2. 用 prompt-engineer skill 生成 prompt → 写入 experiments/exp-XXX/prompt.md
3. 跑 5 次实验 → 记录到 runs/
4. 用 scorer 打分 → 写入 results.yaml
5. 更新 dashboard.md
